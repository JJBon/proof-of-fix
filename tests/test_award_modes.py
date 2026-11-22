"""proof-of-fix#60 tasks 1.1-1.4: award modes (the race and the claim), the registration check, prices set by
funders, and the project's constitution."""

import unittest
from types import SimpleNamespace

from pof import BPS, credits
from pof.challenges import Challenges, ValidatorSet
from pof.checking import constitution_passes
from pof.ledger import Ledger
from pof.lifecycle import Lifecycle
from pof.market import Market, MarketError, seal
from pof.params import AUCTION, DEFAULTS, ParamsError
from pof.payouts import Releases


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"award_mode": "lottery"}, {"attempt_fee": -1}, {"duplicate_appeal_jury": 4}, {"published_attempts": "some"}, {"registration_fee": -1}, {"size_floor_lines": -1},
                    {"claim_days_percent": 99}, {"claim_min_days": 0}, {"gate_bar_bps": BPS + 1},
                    {"gate_accuracy_bps": -1}, {"mutation_catch_bps": BPS + 1}, {"top_up_bps_per_week": -1}):
            with self.assertRaises(ParamsError, msg=bad):
                DEFAULTS.with_(**bad)
        self.assertEqual((DEFAULTS.award_mode, AUCTION.award_mode), ("race", "auction"))  # the owner's choice (D9)


class ModeWorld(unittest.TestCase):
    mode = "race"
    base = DEFAULTS

    def setUp(self):
        self.P = self.base.with_(award_mode=self.mode)
        L = self.ledger = Ledger()
        self.infra, self.insurance, self.owner = L.open("infrastructure"), L.open("insurance"), L.open("actor")
        self.users = [L.open("actor") for _ in range(3)]
        self.solvers = [L.open("actor") for _ in range(3)]
        for a in self.users + self.solvers + [self.owner]:
            L.issue(a, credits(2_000), "endowment", "setup", 0)
        self.life = Lifecycle(L, self.P, self.infra)
        self.vset = ValidatorSet(L)
        for _ in range(12):
            v = L.open("actor")
            L.issue(v, credits(200), "endowment", "setup", 0)
            self.vset.register(v, credits(50), 0)
        self.ch = Challenges(L, self.P, self.life, self.vset, self.insurance, self.infra)
        self.rel = Releases(L, self.P, self.life, self.insurance, self.infra, self.owner, challenges=self.ch)
        self.m = Market(L, self.P, self.life, self.rel, self.infra)

    def tearDown(self):
        self.assertTrue(self.ledger.conserved())

    def funded(self, funds=credits(300), day=1):
        b = self.m.open_bounty(0, day)  # no target in race and claim (#56 D12): funders set it
        for u, amount in zip(self.users, (funds // 2, funds // 3, funds - funds // 2 - funds // 3)):
            self.m.pledge(b, u, amount, day)
        return b


class TestAwardModes(ModeWorld):
    def test_no_price_to_bid(self):
        b = self.funded()
        self.assertEqual((b.state, b.round_deadline), ("open", None))
        with self.assertRaises(MarketError):  # no rounds, so nothing to bid in
            self.m.commit(b, self.solvers[0], seal(100, "s"), 2)
        cap = self.m.price_cap(b)
        e = self.m.race_submit(b, self.solvers[0], 3)
        self.assertEqual(b.price, cap * 7 // 10)  # the funds' rising price on day 3: 50 % + 2 days × 10 %; no reserve
        c = self.m.deliver(e, 50, 3, passes=True)
        self.assertEqual((b.state, b.won_day), ("won", 3))
        self.assertEqual(self.m.payment_for(c)[0], cap * 7 // 10)

    def test_auction_unchanged(self):
        m = Market(self.ledger, AUCTION, self.life, self.rel, self.infra)
        b = m.open_bounty(credits(300), 1)
        m.pledge(b, self.users[0], credits(300), 1)
        self.assertIsNotNone(b.round_deadline)
        m.commit(b, self.solvers[0], seal(100, "s"), 2)  # sealed rounds, as before
        m.register(self.users[1], 2)  # no registration check in the auction
        self.assertEqual(self.ledger.balance(self.users[1]), credits(2_000))


class TestRegistration(ModeWorld):
    def test_poster_pays_the_check(self):
        before = self.ledger.balance(self.infra)
        self.m.register(self.users[0], 1)
        self.assertEqual(self.ledger.balance(self.users[0]), credits(2_000) - self.P.registration_fee)
        self.assertEqual(self.ledger.balance(self.infra), before + self.P.registration_fee)

    def test_without_the_balance(self):
        poor = self.ledger.open("actor")
        with self.assertRaises(MarketError):
            self.m.register(poor, 1)
        self.assertEqual(self.ledger.balance(poor), 0)

    def test_zero_coin(self):
        b = self.m.open_bounty(0, 1)  # passed the check with no funds: open at once
        self.assertEqual((b.state, self.m.price_cap(b)), ("open", 0))
        with self.assertRaises(MarketError):  # the auction still needs a target
            Market(self.ledger, AUCTION, self.life, self.rel, self.infra).open_bounty(0, 1)


class TestRace(ModeWorld):
    def test_first_through_the_gates_wins(self):
        b = self.funded()
        for s in self.solvers[:2]:
            self.m.race_start(b, s)
        self.assertEqual(len(b.attempting), 2)  # published
        self.assertTrue(set(self.solvers[:2]) <= self.m.parties(b))  # racers never check it
        first = self.m.race_submit(b, self.solvers[0], 3)
        self.m.deliver(first, 50, 3, passes=False)  # fails a gate
        self.assertEqual(b.state, "open")  # still open to the others
        self.assertEqual(self.ledger.balance(self.solvers[0]),  # the attempt and its checks; no bond lost
                         credits(2_000) - self.P.attempt_fee - self.P.evaluation_fee)
        second = self.m.race_submit(b, self.solvers[1], 4)
        self.assertIsNotNone(self.m.deliver(second, 50, 4, passes=True))
        self.assertEqual(b.state, "won")

    def test_too_late(self):
        b = self.funded()
        self.m.race_start(b, self.solvers[2])
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3), 50, 3, passes=True)
        before = self.ledger.balance(self.solvers[2])
        self.assertIsNone(self.m.race_submit(b, self.solvers[2], 4))  # not checked; arriving late costs (#64)
        self.assertEqual(before - self.ledger.balance(self.solvers[2]), self.P.evaluation_fee)
        self.assertNotIn(self.solvers[2], b.attempting)

    def _drain(self, who, keep):
        self.ledger.transfer(who, self.users[0], self.ledger.balance(who) - keep, "payout", "test", 3)

    def test_late_without_the_fee_is_refused(self):  # as on-chain (owner, 2026-10-29): nothing charged
        b = self.funded()
        self.m.race_start(b, self.solvers[2])
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3), 50, 3, passes=True)
        self._drain(self.solvers[2], self.P.evaluation_fee - 1)
        with self.assertRaises(MarketError):
            self.m.race_submit(b, self.solvers[2], 4)
        self.assertEqual(self.ledger.balance(self.solvers[2]), self.P.evaluation_fee - 1)

    def test_duplicate_without_the_deposit_is_refused(self):  # the contract takes a duplicate's whole deposit
        b = self.funded()
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=False)
        self._drain(self.solvers[1], self.m.deposit() - 1)
        with self.assertRaises(MarketError):
            self.m.race_submit(b, self.solvers[1], 3, fix="fix-a")
        self.assertEqual(self.ledger.balance(self.solvers[1]), self.m.deposit() - 1)

    def test_idle_bounty_closes(self):
        b = self.funded()
        limit = self.P.bounty_max_rounds * self.P.round_days
        self.assertEqual(self.m.close_idle(1 + limit - 1), [])
        self.assertEqual(self.m.close_idle(1 + limit), [b])
        self.assertEqual(b.state, "unsolved")
        self.assertEqual(self.ledger.balance(b.account), 0)  # funds back by input


class TestOwnerDecisions(ModeWorld):  # #60 D9
    def test_rising_price_locks(self):
        b = self.funded()
        cap = self.m.price_cap(b)
        self.assertEqual([self.m.offer(b, d) for d in (1, 3, 6, 9)], [cap // 2, cap * 7 // 10, cap, cap])
        self.m.race_start(b, self.solvers[0], 3)  # the first attempt locks the share
        self.assertEqual(self.m.offer(b, 9), cap * 7 // 10)
        e = self.m.race_submit(b, self.solvers[1], 4, fix="fix-a")
        self.assertEqual(b.price, cap * 7 // 10)
        self.m.deliver(e, 50, 4, passes=False)
        self.m.pledge(b, self.users[0], credits(300), 5)  # a later pledge raises the price at the locked share (#56 D14)
        self.assertEqual(self.m.offer(b, 9), self.m.price_cap(b) * 7 // 10)
        self.assertGreater(self.m.price_cap(b), cap)

    def test_duplicate_rejected(self):
        b = self.funded()
        e = self.m.race_submit(b, self.solvers[0], 3, fix="fix-a")
        self.m.deliver(e, 50, 3, passes=False)
        before = self.ledger.balance(self.solvers[1])
        self.assertIsNone(self.m.race_submit(b, self.solvers[1], 3, fix="fix-a"))  # from any account
        self.assertEqual(before - self.ledger.balance(self.solvers[1]), self.P.evaluation_fee)  # the similarity check
        self.assertIsNotNone(self.m.race_submit(b, self.solvers[1], 3, fix="fix-b"))  # a different fix is checked

    def test_one_appeal(self):
        b = self.funded()
        e = self.m.race_submit(b, self.solvers[0], 3, fix="fix-a")
        self.m.deliver(e, 50, 3, passes=False)
        before = self.ledger.balance(self.solvers[0])
        again = self.m.race_appeal(e, 3)
        self.assertTrue(again.appeal)
        self.assertEqual(before - self.ledger.balance(self.solvers[0]),
                         self.P.rerun_appeal_fee + again.stake + again.fee_held)
        with self.assertRaises(MarketError):  # once
            self.m.race_appeal(e, 3)
        self.assertIsNotNone(self.m.deliver(again, 50, 3, passes=True))

    def test_registration_refunded_when_paid(self):
        r = self.m.report_issue(self.users[0], 1, registration=self.m.register(self.users[0], 1))
        b = self.m.open_bounty(0, 1, report=r)
        for u in self.users[1:]:
            self.m.pledge(b, u, credits(150), 1)
        self.assertEqual(r.registration, self.P.registration_fee)
        before = self.ledger.balance(self.users[0])
        self.m._finish(b, 20)
        got = self.ledger.balance(self.users[0]) - before
        self.assertGreaterEqual(got, self.P.registration_fee + self.P.issue_stake)  # with the finder's fee

    def test_bundle_parts_share_the_finders_fee(self):
        parts = [self.m.report_issue(u, 1, registration=self.m.register(u, 1)) for u in self.users[:2]]
        for r in parts:
            self.m.release_unfunded(r, 1)  # bundled: their stakes back
        b = self.m.fund_treasury(credits(200), 1, parts=parts)
        b.price = credits(100)
        before = [self.ledger.balance(r.reporter) for r in parts]
        self.m._finish(b, 20)
        gains = [self.ledger.balance(r.reporter) - x for r, x in zip(parts, before)]
        fee = credits(100) * self.P.finder_fee_bps // BPS
        self.assertEqual(sorted(gains), sorted([fee // 2 + self.P.registration_fee] * 2))


class TestNothingIsFree(ModeWorld):  # #64
    def test_an_attempt_costs(self):
        b = self.funded()
        before = self.ledger.balance(self.solvers[0])
        self.m.race_start(b, self.solvers[0], 2)
        self.assertEqual(before - self.ledger.balance(self.solvers[0]), self.P.attempt_fee)  # never refunded
        self.assertEqual(len(b.attempting), 1)
        poor = self.ledger.open("actor")
        with self.assertRaises(MarketError):
            self.m.race_start(b, poor, 2)
        self.assertEqual(len(b.attempting), 1)

    def votes(self, independent: int):
        return [(self.solvers[2], credits(0.6), i < independent) for i in range(self.P.duplicate_appeal_jury)]

    def test_independent_fix_cleared(self):
        b = self.funded()
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=False)
        self.assertIsNone(self.m.race_submit(b, self.solvers[1], 4, fix="fix-a"))  # flagged as a duplicate
        before = self.ledger.balance(self.solvers[1])
        self.assertTrue(self.m.appeal_duplicate(b, self.solvers[1], "fix-a", 4, self.votes(2)))  # 2 of 3: independent
        self.assertEqual(before - self.ledger.balance(self.solvers[1]),
                         self.P.rerun_appeal_fee + self.P.duplicate_appeal_jury * credits(0.6))
        self.assertIsNotNone(self.m.race_submit(b, self.solvers[1], 4, fix="fix-a"))  # checked like any
        self.assertIsNone(self.m.race_submit(b, self.solvers[2], 4, fix="fix-a"))  # cleared for its submitter only

    def test_duplicate_upheld(self):
        b = self.funded()
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=False)
        self.assertFalse(self.m.appeal_duplicate(b, self.solvers[1], "fix-a", 4, self.votes(1)))
        self.assertIsNone(self.m.race_submit(b, self.solvers[1], 4, fix="fix-a"))
        with self.assertRaises(MarketError):  # the published jury size
            self.m.appeal_duplicate(b, self.solvers[1], "fix-a", 4, self.votes(1)[:2])


class TestPublishedAttempts(ModeWorld):
    def test_trusted_only(self):
        b = self.funded()
        for x in self.solvers[:2]:
            self.m.race_start(b, x, 2)
        self.assertEqual(self.m.published_attempts(b), 2)
        self.m.params = self.P.with_(published_attempts="trusted")
        self.assertEqual(self.m.published_attempts(b), 0)  # neither has earned reputation yet
        self.m.reputation.record(self.solvers[0], "solver", 1, b.ref, 2, "accepted")
        self.assertEqual(self.m.published_attempts(b), 1)


class TestClaim(ModeWorld):
    mode = "claim"

    def test_exclusive_time(self):
        b = self.funded()
        e = self.m.claim(b, self.solvers[0], 2, 6)
        self.assertEqual((b.state, e.deliver_by), ("assigned", 8))
        with self.assertRaises(MarketError):  # nobody else while the claim lasts
            self.m.claim(b, self.solvers[1], 3, 6)

    def test_claim_fails(self):
        b = self.funded()
        held = self.ledger.balance(b.account)
        e = self.m.claim(b, self.solvers[0], 2, 6)
        self.m.deliver(e, 50, 5, passes=False)  # fails a gate: the bond goes to the bounty
        self.assertEqual(self.ledger.balance(b.account), held + e.stake)
        self.assertEqual(b.state, "open")
        self.m.claim(b, self.solvers[1], 6, 6)  # open to claim again

    def test_claim_times_out(self):
        b = self.funded()
        e = self.m.claim(b, self.solvers[0], 2, 6)
        self.m.expire_deliveries(9)
        self.assertEqual((e.state, b.state), ("failed", "open"))


class TestConstitution(ModeWorld):
    def test_gates(self):
        self.assertTrue(constitution_passes(7_000, 7_000, False))
        self.assertFalse(constitution_passes(7_000, 6_999, False))
        self.assertFalse(constitution_passes(7_000, 9_500, True))  # padded tests: the mutation gate catches them

    def test_versioned(self):
        old = self.funded()
        self.m.params = self.P.with_(gate_bar_bps=9_000)
        new = self.funded()
        self.assertEqual((old.gate_bar_bps, new.gate_bar_bps), (7_000, 9_000))

    def test_failed_gate_fails_the_delivery(self):
        b = self.funded()
        e = self.m.race_submit(b, self.solvers[0], 3)
        ok = SimpleNamespace(ref=f"entry:{e.id}", state="closed", outcome=True, members=[])
        jury = SimpleNamespace(ref=f"entry:{e.id}", state="closed", outcome="accept", members=[])
        self.assertIsNone(self.m.deliver_checked(e, 50, 3, ok, jury, gates_pass=False))
        self.assertEqual((e.state, b.state), ("failed", "open"))
        e2 = self.m.race_submit(b, self.solvers[1], 4)
        ok2 = SimpleNamespace(ref=f"entry:{e2.id}", state="closed", outcome=True, members=[])
        jury2 = SimpleNamespace(ref=f"entry:{e2.id}", state="closed", outcome="accept", members=[])
        self.assertIsNotNone(self.m.deliver_checked(e2, 50, 4, ok2, jury2, gates_pass=True))


if __name__ == "__main__":
    unittest.main()
