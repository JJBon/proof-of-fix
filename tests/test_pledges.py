"""proof-of-fix#19 tasks 1-2: pledged stakes (earned collateral), the spec delta's scenarios for contribution-lifecycle."""

import unittest

from pof import credits, share
from pof.challenges import Proof
from pof.ledger import Ledger
from pof.lifecycle import LifecycleError
from pof.params import LEGACY, ParamsError

from test_fixes import World, later_releases


class TestParams(unittest.TestCase):
    def test_caps_in_range(self):
        for name in ("pledge_max_stake_bps", "pledge_max_escrow_bps"):
            with self.assertRaises(ParamsError):
                LEGACY.with_(**{name: -1})
            with self.assertRaises(ParamsError):
                LEGACY.with_(**{name: 10_001})

    def test_the_balance_part_covers_the_check_fee(self):
        """A pledge covering the whole stake would leave the check fee to be paid out of the pledge."""
        with self.assertRaises(ParamsError):
            LEGACY.with_(pledge_max_stake_bps=10_000)
        LEGACY.with_(pledge_max_stake_bps=10_000 - LEGACY.check_fee_bps)


class Pledges(World):
    def backing(self, who=None):
        """An accepted contribution in clawback, nothing paid yet."""
        _, a = self.accepted(who)
        self.assertTrue(a.in_clawback)
        return a

    def pledge_cap(self):
        return share(LEGACY.stake_for(78), LEGACY.pledge_max_stake_bps)

    def in_beta(self, c, day=20):
        """Checked and shipped in the next release's beta build (closing the open one pays an instalment)."""
        self.life.run_checks(c, True, day)
        self.rel.close_release(self.rel.current, [], day)
        self.rel.ship_beta(self.rel.open_release(day), [c], day)
        return c

    def challenge(self, c, severity, day):
        ch = self.ch.file(c, self.challenger, Proof("bug", c.id), severity, day, "b")
        self.ch.finalize(ch, day)
        return ch

    def drain(self, who, keep):
        self.ledger.transfer(who, self.infra, self.ledger.balance(who) - keep, "fee", "setup", 0)


class TestSubmission(Pledges):
    def test_stake_partly_pledged(self):
        a = self.backing()
        escrow, cash = self.ledger.balance(a.escrow_account), self.ledger.balance(self.dev)
        amount = self.pledge_cap()
        b = self.life.submit(self.dev, 78, 10, pledges=[(a, amount)])
        self.assertEqual(self.ledger.balance(b.stake_account), b.stake)
        self.assertEqual(self.ledger.balance(a.escrow_account), escrow - amount)
        self.assertEqual(self.ledger.balance(self.dev), cash - (b.stake - amount))
        self.assertEqual((b.pledges, a.pledged_out), ({a.id: amount}, amount))
        self.assertTrue(any(e.kind == "pledge" and a.ref in e.detail for e in self.ledger.events))

    def test_pledge_over_the_stake_cap(self):
        a = self.backing()
        before = len(self.life.contributions)
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 78, 10, pledges=[(a, self.pledge_cap() + 1)])
        self.assertEqual((len(self.life.contributions), a.pledged_out), (before, 0))

    def test_pledge_over_the_escrow_cap(self):
        a = self.backing()
        cap = self.life.pledgeable(a)
        self.assertEqual(cap, share(a.reward, LEGACY.pledge_max_escrow_bps))
        big = LEGACY.stake_for(10_000)  # a stake big enough that only the escrow cap binds
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 10_000, 10, pledges=[(a, cap + 1)])
        self.life.submit(self.dev, 10_000, 10, pledges=[(a, min(cap, share(big, LEGACY.pledge_max_stake_bps)))])

    def test_escrow_cap_counts_what_is_already_pledged(self):
        a = self.backing()
        cap = self.life.pledgeable(a)
        each = self.pledge_cap()
        n = 0
        while self.life.pledgeable(a) >= each:
            self.life.submit(self.dev, 78, 10, pledges=[(a, each)])
            n += 1
        self.assertEqual(n, cap // each)
        self.assertLessEqual(a.pledged_out, share(a.reward, LEGACY.pledge_max_escrow_bps))

    def test_backing_contribution_under_challenge(self):
        a = self.backing()
        self.life.challenge_opened(a, 12)
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 78, 12, pledges=[(a, 1)])
        self.assertEqual(self.life.pledgeable(a), 0)

    def test_sponsored_stake(self):
        a = self.backing()
        with self.assertRaises(LifecycleError):
            self.life.submit(self.newcomer, 78, 10, sponsor=self.dev, pledges=[(a, 1)])

    def test_only_own_contributions_back_a_pledge(self):
        a = self.backing()
        self.life.accepted_count[self.challenger] = 1  # the challenger has accepted work too, but not this one
        with self.assertRaises(LifecycleError):
            self.life.submit(self.challenger, 78, 10, pledges=[(a, 1)])

    def test_insufficient_balance(self):
        a = self.backing()
        stake = LEGACY.stake_for(78)
        self.drain(self.dev, stake - self.pledge_cap() - 1)
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 78, 10, pledges=[(a, self.pledge_cap())])
        self.assertEqual(a.pledged_out, 0)

    def test_a_short_balance_covered_by_a_pledge(self):
        a = self.backing()
        stake = LEGACY.stake_for(78)
        self.drain(self.dev, stake - self.pledge_cap())
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 78, 10)
        self.life.submit(self.dev, 78, 10, pledges=[(a, self.pledge_cap())])
        self.assertEqual(self.ledger.balance(self.dev), 0)

    def test_cap_zero_turns_pledges_off(self):
        self.life.params = LEGACY.with_(pledge_max_stake_bps=0)
        a = self.backing()
        with self.assertRaises(LifecycleError):
            self.life.submit(self.dev, 78, 10, pledges=[(a, 1)])


class TestSettlement(Pledges):
    def pledged(self):
        a = self.backing()
        amount = self.pledge_cap()
        b = self.in_beta(self.life.submit(self.dev, 78, 10, pledges=[(a, amount)]))
        return a, b, amount

    def test_cosmetic_slash_leaves_the_pledge_whole(self):
        a, b, amount = self.pledged()
        escrow = self.ledger.balance(a.escrow_account)
        self.challenge(b, "cosmetic", 22)
        self.assertEqual(b.state, "slashed")
        self.assertEqual(self.ledger.balance(a.escrow_account), escrow + amount)
        self.assertEqual(a.pledged_out, 0)

    def test_wrong_result_reaches_the_pledge_only_by_the_check_fee(self):
        a, b, amount = self.pledged()
        escrow = self.ledger.balance(a.escrow_account)
        self.challenge(b, "wrong_result", 22)
        back = self.ledger.balance(a.escrow_account) - escrow
        self.assertGreaterEqual(back, amount - b.check_fee)
        self.assertLessEqual(back, amount)

    def test_crash_reaches_the_pledge(self):
        a, b, amount = self.pledged()
        escrow, cash = self.ledger.balance(a.escrow_account), self.ledger.balance(self.dev)
        self.challenge(b, "crash", 22)
        self.assertEqual(self.ledger.balance(a.escrow_account), escrow)  # the whole stake was forfeited
        self.assertEqual(self.ledger.balance(self.dev), cash)
        self.assertEqual((a.pledged_out, b.slashed), (0, b.stake - b.check_fee))
        self.assertEqual(b.pledge_slashed, {a.id: amount})

    def test_the_whole_reward_reaches_the_contributor(self):
        """Settled normally, b ends after a (it was accepted later), so the pledge comes back as the dev's reward.
        Returns to a backing escrow still in clawback are the slash and withdraw tests."""
        a, b, amount = self.pledged()
        self.ch.report_review(b, self.ch.reviews[b.id].reviewer, False, 21)
        self.life.advance(b, b.window_end)
        later_releases(self, b, LEGACY.reward_instalments)  # pays a's and b's instalments
        self.assertEqual((b.instalments_left, a.instalments_left), (0, 0))
        self.assertEqual(self.ledger.balance(a.escrow_account), 0)
        paid = sum(e.amount for e in self.ledger.entries_for(a.ref) if e.reason == "reward" and e.target == self.dev)
        self.assertEqual(paid, a.reward)  # the whole reward reaches the dev, recorded under a

    def test_returned_to_the_contributor_after_the_clawback_ended(self):
        a, b, amount = self.pledged()
        later_releases(self, a, LEGACY.reward_instalments)  # a's clawback ends while b is still in beta
        self.assertFalse(a.in_clawback)
        self.life.advance(b, b.window_end)  # no review report: the reviewer is penalized, b is still accepted
        later_releases(self, b, LEGACY.reward_instalments)
        back = [e for e in self.ledger.entries_for(a.ref) if e.source == b.stake_account and e.target == self.dev
                and e.reason == "reward"]
        self.assertEqual([e.amount for e in back], [amount])  # a's reward, paid from b's stake, recorded under a
        self.assertEqual(a.pledged_out, 0)

    def test_withdrawn_before_beta(self):
        a = self.backing()
        escrow = self.ledger.balance(a.escrow_account)
        b = self.life.submit(self.dev, 78, 10, pledges=[(a, self.pledge_cap())])
        self.life.withdraw(b, 11)
        self.assertEqual(self.ledger.balance(a.escrow_account), escrow)
        self.assertEqual((a.pledged_out, b.pledges), (0, {}))


class TestClawbackReach(Pledges):
    def test_defect_found_while_the_reward_is_pledged(self):
        a = self.backing()
        amount = self.pledge_cap()
        b = self.in_beta(self.life.submit(self.dev, 78, 10, pledges=[(a, amount)]))
        source, escrow = a.reward_source, self.ledger.balance(a.escrow_account)
        self.challenge(a, "wrong_result", 21)  # a is clawed back while its reward backs b
        self.assertEqual(a.state, "accepted")
        self.assertEqual(a.clawed_back, escrow)  # what was left in its escrow; the pledge is reached later
        self.assertEqual(self.ledger.balance(b.stake_account), b.stake - b.check_fee)  # b keeps its full stake
        challenger, pool, dev = (self.ledger.balance(x) for x in (self.challenger, source, self.dev))
        self.ch.report_review(b, self.ch.reviews[b.id].reviewer, False, 22)
        self.life.advance(b, b.window_end)
        later_releases(self, b, LEGACY.reward_instalments)
        to_challenger = share(amount, LEGACY.challenger_escrow_share_bps)
        self.assertEqual(self.ledger.balance(self.challenger) - challenger, to_challenger)
        moved = [e for e in self.ledger.entries_for(a.ref) if e.source == b.stake_account and e.target == source]
        self.assertEqual(sum(e.amount for e in moved), amount - to_challenger)  # a's forfeit, recorded under a
        self.assertEqual(a.pledge_clawed, amount)
        net_b = Ledger.net(self.ledger.entries_for(b.ref))
        rewards = sum(e.amount for e in self.ledger.entries_for(b.ref) if e.reason == "reward" and e.target == self.dev)
        self.assertEqual(net_b[self.dev], rewards - b.check_fee)  # the dev got b's reward and its cash, not the pledge
        self.assertEqual(a.pledged_out, 0)


class TestChains(Pledges):
    def test_a_backs_b_then_b_backs_c(self):
        a = self.backing()
        b = self.in_beta(self.life.submit(self.dev, 78, 10, pledges=[(a, self.pledge_cap())]))
        self.ch.report_review(b, self.ch.reviews[b.id].reviewer, False, 21)
        self.life.advance(b, b.window_end)
        self.assertTrue(b.in_clawback)
        cap = self.life.pledgeable(b)
        self.assertEqual(cap, share(b.reward, LEGACY.pledge_max_escrow_bps))
        c = self.in_beta(self.life.submit(self.dev, 78, 30, pledges=[(b, min(cap, self.pledge_cap()))]), day=30)
        # a defect in c (crash) and then in b: every forfeit respects the order and the ledger conserves
        self.challenge(c, "crash", 32)
        self.assertEqual(c.state, "slashed")
        self.challenge(b, "wrong_result", 33)
        self.assertEqual(b.clawed_back > 0, True)
        self.assertEqual((a.pledged_out, b.pledged_out), (0, 0))
        self.assertTrue(a.in_clawback)  # b's stake returned a's pledge to a's escrow
        with self.assertRaises(LifecycleError):  # a stake is never pledgeable, only an accepted reward
            self.life.submit(self.dev, 78, 34, pledges=[(c, 1)])


if __name__ == "__main__":
    unittest.main()
