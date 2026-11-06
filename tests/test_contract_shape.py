"""proof-of-fix#56 tasks 2.3 and 2.4: the simulation's side of the local contract. One fix, one payout (D10); idle
bounties sunset (D11); no target and one open bounty per issue (D12); and the contract-shaped configuration the replay
runs (D9)."""

import unittest

from pof import BPS, credits
from pof.challenges import ChallengeError, Proof
from pof.market import MarketError
from pof.params import CONTRACT, DEFAULTS, ParamsError
from pof.sim import market_sim as MS

from tests.test_award_modes import ModeWorld


class Merging(ModeWorld):
    def won(self, b, solver, fix, day):
        """A fix wins the bounty and is merged at the next release: its payment starts."""
        return self.merge(self.m.deliver(self.m.race_submit(b, solver, day, fix=fix), 50, day, passes=True), day)

    def merge(self, c, day):
        if self.rel.current is not None:
            self.rel.close_release(self.rel.current, [], day)
        self.rel.ship_beta(self.rel.open_release(day), [c], day)
        return c

    def votes(self, independent: int):
        return [(self.solvers[2], credits(0.6), i < independent) for i in range(self.P.duplicate_appeal_jury)]


class TestOneOpenPerIssue(Merging):  # D12
    def test_a_similar_issue_is_open(self):
        b = self.m.open_bounty(0, 1, key="issue:7")
        with self.assertRaises(MarketError):  # the registration check refuses it: fund the open one instead
            self.m.open_bounty(0, 2, key="issue:7")
        self.assertIsNotNone(self.m.open_bounty(0, 2, key="issue:8"))
        self.assertIs(self.m.similar_open("issue:7"), b)

    def test_after_it_closes(self):
        b = self.m.open_bounty(0, 1, key="issue:7")
        limit = self.P.bounty_max_rounds * self.P.round_days
        self.assertEqual(self.m.close_idle(1 + limit), [b])  # nobody took it
        self.assertIsNone(self.m.similar_open("issue:7"))
        self.assertEqual(self.m.open_bounty(0, 2 + limit, key="issue:7").state, "open")

    def test_won_and_being_paid_counts_as_open(self):
        b = self.m.open_bounty(0, 1, key="issue:7")
        for u in self.users:
            self.m.pledge(b, u, credits(100), 1)
        self.won(b, self.solvers[0], "fix-a", 3)
        with self.assertRaises(MarketError):
            self.m.open_bounty(0, 4, key="issue:7")


class TestNoTarget(ModeWorld):  # D12: whoever opens a bounty doesn't fund it; the market sets its value
    def test_opens_at_once(self):
        b = self.m.open_bounty(0, 1)
        self.assertEqual((b.state, self.ledger.balance(b.account), self.m.offer(b, 1)), ("open", 0, 0))
        with self.assertRaises(MarketError):
            self.m.open_bounty(credits(300), 1)  # no target to gather

    def test_anyone_funds_it_while_open(self):
        b = self.m.open_bounty(0, 1)
        self.m.pledge(b, self.users[0], credits(100), 1)
        before = self.m.offer(b, 3)
        self.m.pledge(b, self.users[1], credits(200), 3)  # later funders raise the price on offer
        self.assertAlmostEqual(self.m.offer(b, 3), before * 3, delta=3)  # rounding
        self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=True)
        with self.assertRaises(MarketError):  # won: closed to funding
            self.m.pledge(b, self.users[2], credits(100), 4)

    def test_the_auction_keeps_targets(self):
        self.m.params = self.P.with_(award_mode="auction")
        with self.assertRaises(MarketError):
            self.m.open_bounty(0, 1)
        self.assertEqual(self.m.open_bounty(credits(300), 1).state, "pledging")


class TestOneFixOnePayout(Merging):
    def test_same_fix_on_another_bounty(self):
        first, other = self.funded(), self.funded()
        self.won(first, self.solvers[0], "fix-a", 3)
        self.assertEqual(self.m.paid_fixes, {"fix-a": first.id})
        for s in self.solvers[:2]:  # from any account, the winner's own included
            before = self.ledger.balance(s)
            self.assertIsNone(self.m.race_submit(other, s, 4, fix="fix-a"))  # rejected unchecked
            self.assertEqual(before - self.ledger.balance(s), self.P.evaluation_fee)
        self.assertEqual((other.state, other.entries), ("open", []))  # the other bounty stays open

    def test_a_later_bounty_on_the_same_issue(self):
        first = self.m.open_bounty(0, 1, key="issue:7")
        self.m.pledge(first, self.users[0], credits(300), 1)
        self.won(first, self.solvers[0], "fix-a", 3)
        self.m._finish(first, 40)  # paid in full: a new bounty may open for it (a regression, say)
        later = self.m.open_bounty(0, 41, key="issue:7")
        self.m.pledge(later, self.users[1], credits(300), 41)
        self.assertIsNone(self.m.race_submit(later, self.solvers[1], 42, fix="fix-a"))  # the paid fix can't win
        self.assertEqual(later.state, "open")
        self.assertIsNotNone(self.won(later, self.solvers[1], "fix-b", 43))  # a different fix can
        self.assertEqual(later.state, "won")

    def test_not_before_its_merge(self):
        first, other = self.funded(), self.funded()
        self.m.deliver(self.m.race_submit(first, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=True)
        self.assertFalse(self.m.fix_paid_elsewhere(other, "fix-a"))  # won, not merged: nothing paid yet
        self.assertFalse(self.m.fix_paid_elsewhere(first, "fix-a"))  # never "elsewhere" on its own bounty

    def test_appealed(self):
        first, other = self.funded(), self.funded()
        self.won(first, self.solvers[0], "fix-a", 3)
        for s in self.solvers[:2]:
            self.assertIsNone(self.m.race_submit(other, s, 4, fix="fix-a"))
        self.assertFalse(self.m.appeal_duplicate(other, self.solvers[0], "fix-a", 4, self.votes(1)))  # the same fix
        self.assertTrue(self.m.appeal_duplicate(other, self.solvers[1], "fix-a", 4, self.votes(2)))  # independent
        self.assertIsNone(self.m.race_submit(other, self.solvers[0], 4, fix="fix-a"))  # cleared for its submitter only
        self.assertIsNotNone(self.m.race_submit(other, self.solvers[1], 4, fix="fix-a"))  # checked like any

    def test_only_the_race_keeps_the_registry(self):
        b = self.funded()
        c = self.m.deliver(self.m.race_submit(b, self.solvers[0], 3, fix="fix-a"), 50, 3, passes=True)
        self.m.params = self.P.with_(award_mode="claim")
        self.merge(c, 3)
        self.assertEqual(self.m.paid_fixes, {})


class TestIdleSunset(ModeWorld):
    def test_nobody_takes_it(self):
        b = self.funded(day=1)
        limit = self.P.bounty_max_rounds * self.P.round_days
        self.assertEqual(limit, 28)  # the contract's idle_days
        self.assertEqual(self.m.close_idle(limit), [])
        self.assertEqual(self.m.close_idle(1 + limit), [b])
        self.assertEqual((b.state, self.ledger.balance(b.account)), ("unsolved", 0))
        self.assertEqual([self.ledger.balance(u) for u in self.users], [credits(2_000)] * 3)  # shares back

    def test_attempts_dont_keep_it_alive(self):  # owner, 2026-10-29
        b = self.funded(day=1)
        limit = self.P.bounty_max_rounds * self.P.round_days
        for day in range(3, limit, 5):  # attempts, stops and attempts again: none restarts the clock
            self.m.race_start(b, self.solvers[0], day)
            self.m.race_stop(b, self.solvers[0], day + 2)
        self.m.race_start(b, self.solvers[1], limit - 2)
        self.assertEqual(self.m.close_idle(limit), [])
        self.assertEqual(self.m.close_idle(1 + limit), [b])  # with an attempt in progress
        with self.assertRaises(MarketError):  # it ends with the bounty: nothing to submit to, nothing charged
            self.m.race_submit(b, self.solvers[1], 2 + limit, fix="late")


class TestContractShape(Merging):
    base = CONTRACT

    def test_the_shape(self):
        self.assertEqual((CONTRACT.treasury_budget, CONTRACT.bond_discount_bps, CONTRACT.market_fee_bps,
                          CONTRACT.bounty_stake_bps, CONTRACT.challenge_appeals, CONTRACT.award_mode),
                         (0, 0, 0, 0, False, "race"))
        self.assertTrue(DEFAULTS.challenge_appeals and DEFAULTS.bounty_stake_bps and DEFAULTS.market_fee_bps)
        r = self.m.report_issue(self.users[0], 1)
        b = self.m.open_bounty(0, 1, report=r)
        self.m.pledge(b, self.users[1], credits(300), 1)
        # no market fee: the cap leaves room for the finder's fee only, as Race.capOf does
        self.assertEqual(self.m.price_cap(b), credits(300) * BPS // (BPS + CONTRACT.finder_fee_bps))

    def test_no_stake(self):
        b = self.funded()
        before = self.ledger.balance(self.solvers[0])
        e = self.m.race_submit(b, self.solvers[0], 3, fix="fix-a")
        self.assertEqual((e.stake, before - self.ledger.balance(self.solvers[0])), (0, self.m.deposit()))
        c = self.merge(self.m.deliver(e, 50, 3, passes=True), 3)
        self.assertEqual(c.stake, 0)  # the unpaid instalments are the bond

    def test_no_market_fee(self):
        b = self.funded()
        held = self.ledger.balance(b.account)
        c = self.won(b, self.solvers[0], "fix-a", 3)
        self.assertEqual(self.ledger.balance(b.account), held - c.reward)  # only the price left the bounty

    def test_no_treasury(self):
        with self.assertRaises(MarketError):
            self.m.fund_treasury(credits(100), 1)
        self.funded()
        self.assertEqual(self.m.match(1), {})

    def test_challenges_are_final(self):
        b = self.funded()
        c = self.won(b, self.solvers[0], "fix-a", 3)
        challenger = self.users[0]
        ch = self.ch.file(c, challenger, Proof("regression", c.id), "crash", c.beta_day + 1, "x")
        self.assertEqual(ch.state, "decided")
        with self.assertRaises(ChallengeError):  # one final result, so nothing stays open
            self.ch.appeal(ch, c.contributor, c.beta_day + 1)
        self.ch.finalize(ch, c.beta_day + 1)
        self.assertEqual(c.open_challenges, 0)
        self.m.settle(c.beta_day + 2)
        self.assertEqual(b.state, "open")  # a clawback reopens the bounty

    def test_validation(self):
        for bad in ({"award_mode": "auction"}, {"award_mode": "claim"}, {"treasury_budget": credits(10)}):
            with self.assertRaises(ParamsError, msg=bad):  # stakes are only off in the race; with a treasury,
                CONTRACT.with_(**bad)  # the finder's fee must stay below the market fee
        with self.assertRaises(ParamsError):
            DEFAULTS.with_(bounty_stake_bps=0, award_mode="auction")


class TestContractShapedRun(unittest.TestCase):
    def test_four_weeks(self):
        # with no treasury or matching, most pledged bounties miss their target and refund, so a short run has few
        # races: four weeks for some to be paid
        w = MS.run("market", 1, CONTRACT, weeks=4)
        m = w.market
        self.assertTrue(w.ledger.conserved())
        self.assertTrue(m.entries and all(e.stake == 0 for e in m.entries.values()))
        self.assertFalse(any(b.treasury or b.matched for b in m.bounties.values()))
        self.assertTrue(any(b.state == "paid" for b in m.bounties.values()))
        self.assertFalse(any(ch.appealed_by for ch in w.challenges.challenges.values()))
        self.assertFalse(any(e.reason == "payout" and e.target in w.releases.fee_targets().values()
                             and e.source in {b.account for b in m.bounties.values()} for e in w.ledger.entries))
        self.assertLessEqual({b.id for b in m.bounties.values() if b.state == "paid"}, set(m.paid_fixes.values()))


class TestSplit(unittest.TestCase):  # D13
    def test_fifteen_eightyfive(self):
        for p in (DEFAULTS, CONTRACT):
            self.assertEqual(p.finder_fee_bps, 1_765)
            price = credits(85)  # the solver's price; the reporter's fee comes on top of it
            self.assertAlmostEqual(price * p.finder_fee_bps // BPS / (price + price * p.finder_fee_bps // BPS), 0.15,
                                   places=4)
        self.assertLess(DEFAULTS.finder_fee_bps, DEFAULTS.market_fee_bps)  # with a treasury (#34)

    def test_the_sweep(self):
        out = MS.split_sweep([1], weeks=1, shares=(500, 10_000))
        self.assertEqual(set(out["configs"]), {"default", "contract"})
        row = out["configs"]["contract"]["0.500"]  # 50/50, measured though a treasury would refuse it in the default
        self.assertEqual(row["finder_fee_bps"], 10_000)
        self.assertEqual(set(row) - {"finder_fee_bps"}, {"bounties_paid", "days_to_fix", "funder_cost_per_paid_bounty",
                                                         "solver_net_of_effort", "reporter_net", "flood_net",
                                                         "farm_net"})
        with self.assertRaises(ParamsError):  # never published
            DEFAULTS.with_(finder_fee_bps=10_000)


if __name__ == "__main__":
    unittest.main()
