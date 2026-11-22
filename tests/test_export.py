"""proof-of-fix#56 task 2.6 (design D7): the exporter of race runs for the contract's replay (contracts/test/Replay.t.sol)."""

import io
import json
import os
import unittest
from contextlib import redirect_stdout

from pof.sim import export as X
from pof.sim.__main__ import main

DATA = os.path.join(os.path.dirname(__file__), "..", "contracts", "test", "data")
SEEDS = (1, 2, 3, 4, 8, 9, 10, 15, 60)  # 8: late; 10: split appeals; 15: a failure appealed; 60: a duplicate
TOKEN_SEEDS = (1, 5, 7, 15)  # task 3.4, with the emission on: 15 has an inflated registration


def token_export(seed):
    return X.export(seed, params=X.CONTRACT_TOKENS, token_price=X.REPLAY_TOKEN_PRICE)


class TestExport(unittest.TestCase):
    def test_unpledged_opens_with_no_treasury(self):
        """As the registration check opens it on-chain (owner, 2026-10-29): with no treasury to wait for, an issue
        nobody pledged for opens at once, and sunsets if nobody funds or attempts it."""
        from pof.params import CONTRACT
        from pof.sim import market_sim as MS
        w = MS.run("market", 1, CONTRACT, 2)
        opened = [i for i in w.issues if i.route == "unpledged"]
        self.assertTrue(opened)
        self.assertTrue(all(i.bounty is not None and i.bounty.offer_from == i.day for i in opened))
        self.assertIn("unsolved", {i.bounty.state for i in opened})
        self.assertTrue(all(i.parts for i in w.issues if i.bounty is None and i.route == "unpledged"))

    def test_deterministic(self):
        self.assertEqual(json.dumps(X.export(2), sort_keys=True), json.dumps(X.export(2), sort_keys=True))

    def test_the_replayed_files_are_current(self):
        """The contract replays these files: they must be what the simulation exports now."""
        for seed in SEEDS:
            with open(os.path.join(DATA, f"race-{seed}.json")) as f:
                self.assertEqual(json.load(f), json.loads(json.dumps(X.export(seed))), f"race-{seed}.json is stale")

    def test_the_token_files_are_current(self):
        for seed in TOKEN_SEEDS:
            with open(os.path.join(DATA, f"tokens-{seed}.json")) as f:
                self.assertEqual(json.load(f), json.loads(json.dumps(token_export(seed))), f"tokens-{seed}.json is stale")

    def test_the_token_replay_covers_its_rules(self):
        """Task 3.4: the token seeds have bounties of 0 coin that closed paid, and an inflated registration."""
        zero, inflated = 0, 0
        for seed in TOKEN_SEEDS:
            m = X.record("market", seed, X.CONTRACT_TOKENS, token_price=X.REPLAY_TOKEN_PRICE).market
            paid = [b for b in m.bounties.values() if b.state == "paid"]
            zero += sum(1 for b in paid if not b.pledges)
            inflated += sum(1 for b in paid if b.inflated)
            doc = token_export(seed)["token"]
            self.assertEqual(sum(doc["holders"]["balance"]), doc["supply"])
            self.assertEqual(sum(doc["periods"]["minted"]), doc["supply"])
        self.assertGreater(zero, 0)
        self.assertGreater(inflated, 0)

    def test_a_close_counts_in_its_last_instalments_period(self):
        """As the contract fixes it by date (owner, 2026-10-29): the period of the last instalment's release, from the
        merge day, the window and the instalments, whenever the bounty is settled."""
        for seed in TOKEN_SEEDS:
            ex = X.Exporter(X.record("market", seed, X.CONTRACT_TOKENS, token_price=X.REPLAY_TOKEN_PRICE))
            ex.run()
            merged = {e["bounty"]: e["day"] for e in ex.events if e["kind"] == "merged"}  # the last merge
            p = ex.m.params
            for period, close, _ in ex.m.tokens.history:
                b = int(close.ref.split(":")[1])
                want = (merged[b] + p.challenge_window_days) // p.release_every_days + p.reward_instalments
                self.assertEqual(period, want, f"seed {seed}, {close.ref}")

    def test_zero_coin_runs_its_instalments(self):
        """As on-chain: a fix with no coin reward closes paid, and mints, only after its instalments' releases (the
        clawback period), not when its window ends; pof's own market does the same since 2026-10-30 (owner)."""
        m = X.record("market", 1, X.CONTRACT_TOKENS, token_price=X.REPLAY_TOKEN_PRICE).market
        zero = [b for b in m.bounties.values() if b.state == "paid" and not b.pledges]
        self.assertTrue(zero)
        first = min(period for period, _, _ in m.tokens.history)
        self.assertGreaterEqual(first, 1 + m.params.reward_instalments)  # merged on day 1 at the soonest
        from pof.params import CONTRACT, DEFAULTS
        self.assertTrue(CONTRACT.zero_reward_instalments)
        self.assertTrue(DEFAULTS.zero_reward_instalments)

    def test_every_contract_entry_is_in_an_event(self):
        rec = X.record("market", 60)  # it has a duplicate and its appeal
        ex = X.Exporter(rec)
        ex.run()
        for i, x in enumerate(ex.entries):
            if ex.in_scope(x) and ex.contract_side(x) and not (X.kind_of(x.source) == "bounty"
                                                               and X.kind_of(x.target) == "escrow"):
                self.assertIn(i, ex.covered, f"entry {x.seq}: {x.reason} {x.source} -> {x.target}")
        kinds = {e["kind"] for e in ex.events}
        self.assertTrue({"register", "accept", "pledge", "attempt", "submit", "duplicate", "appealDuplicate", "merged",
                         "instalment", "settle", "sunset", "withdrawIssue"} <= kinds)

    def test_an_unmapped_movement_raises(self):
        rec = X.record("market", 1)
        actor = next(a for a in rec.ledger.accounts() if a.startswith("actor-") and rec.ledger.balance(a))
        rec.ledger.transfer(actor, rec.market.infrastructure, 1, "fee", "bounty:1", 99)  # no call made it
        with self.assertRaises(X.ExportError):
            X.Exporter(rec).run()

    def test_balances_add_up(self):
        """Every account's expected net over the run sums to zero with the pots and deposits: nothing is minted."""
        doc = X.export(4)
        f = doc["final"]
        total = sum(-v if neg else v for neg, v in zip(f["neg"], f["value"]))
        self.assertEqual(total + sum(doc["finalHeld"]["amount"]) + doc["finalDeposits"], 0)

    def test_columns_line_up(self):
        doc = X.export(9)
        for table in ("events", "expects", "held", "fees", "funders", "final", "finalHeld"):
            self.assertEqual(len({len(v) for v in doc[table].values()}), 1, table)
        ev = doc["events"]
        for i in range(len(ev["kind"])):
            for table, lo, hi in (("expects", "expFrom", "expTo"), ("held", "heldFrom", "heldTo"),
                                  ("fees", "feeFrom", "feeTo"), ("funders", "funFrom", "funTo")):
                self.assertTrue(1 <= ev[lo][i] <= ev[hi][i] <= len(next(iter(doc[table].values()))), (i, table))

    def test_quotes(self):
        """Task 3.2: after each event its bounty's quote, as Quoter.quote must read it (Replay.t.sol checks them)."""
        doc = X.export(1)
        q, n = doc["quotes"], len(doc["events"]["kind"])
        self.assertEqual(len({len(v) for v in q.values()}), 1)
        self.assertEqual(q["event"], sorted(q["event"]))
        self.assertTrue(all(0 <= e < n for e in q["event"]))
        self.assertTrue({1, 2, 4} <= set(q["state"]), "open, won and paid bounties are quoted")
        inst = doc["params"]["instalments"]
        for i in range(len(q["event"])):
            self.assertEqual(q["instalment"][i] * (inst - 1) + q["lastInstalment"][i], q["price"][i])
            if q["state"][i] == 1:
                self.assertEqual(q["price"][i], q["cap"][i] * q["offerBps"][i] // 10_000)
                self.assertGreaterEqual(q["sunsetDay"][i], doc["events"]["day"][q["event"][i]])

    def test_the_command(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["market", "run", "--weeks", "2", "--seed", "1", "--export-events"])
        self.assertEqual(json.loads(out.getvalue()), json.loads(json.dumps(X.export(1))))
        out = io.StringIO()
        with redirect_stdout(out):
            main(["market", "run", "--weeks", "2", "--seed", "1", "--export-events", "--tokens"])
        self.assertEqual(json.loads(out.getvalue()), json.loads(json.dumps(token_export(1))))


if __name__ == "__main__":
    unittest.main()
