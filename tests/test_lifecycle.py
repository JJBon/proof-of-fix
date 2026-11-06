"""Tasks 3.1 and 3.2: specs/contribution-lifecycle, one test per scenario, each checking the ledger."""

import unittest

from pof import BPS, credits, share
from pof.ledger import Ledger
from pof.lifecycle import Lifecycle, LifecycleError
from pof.params import LEGACY


class Setup(unittest.TestCase):
    def setUp(self):
        self.ledger = Ledger()
        self.contributor = self.ledger.open("actor")
        self.challenger = self.ledger.open("actor")
        self.infra = self.ledger.open("infrastructure")
        self.insurance = self.ledger.open("insurance")
        self.pool = self.ledger.open("treasury")
        self.ledger.issue(self.contributor, credits(5_000), "endowment", "setup", 0)
        self.ledger.issue(self.pool, credits(1_000), "release_funding", "release:1", 0)
        self.life = Lifecycle(self.ledger, LEGACY, self.infra)

    def tearDown(self):
        self.assertTrue(self.ledger.conserved())

    def in_beta(self, lines=78, reward=credits(40), day=1):
        c = self.life.submit(self.contributor, lines, day)
        self.life.run_checks(c, True, day)
        self.life.enter_beta(c, day, reward, self.pool)
        return c

    def net(self, c):
        return Ledger.net(self.ledger.entries_for(c.ref))


class TestEntryStake(Setup):
    def test_stake_locked_on_submission(self):
        c = self.life.submit(self.contributor, 78, 1)
        self.assertEqual(c.stake, LEGACY.stake_for(78))
        self.assertEqual(self.ledger.balance(c.stake_account), c.stake)
        self.assertEqual(self.ledger.balance(self.contributor), credits(5_000) - c.stake)
        self.assertEqual(c.state, "submitted")

    def test_insufficient_balance(self):
        poor = self.ledger.open("actor")
        self.ledger.issue(poor, LEGACY.stake_for(78) - 1, "endowment", "setup", 0)
        before = self.ledger.entries
        with self.assertRaises(LifecycleError):
            self.life.submit(poor, 78, 1)
        self.assertEqual(self.ledger.entries, before)
        self.assertEqual(self.life.contributions, {})

    def test_larger_contributions_need_larger_stakes(self):
        small, large = self.life.submit(self.contributor, 78, 1), self.life.submit(self.contributor, 1_098, 1)
        self.assertGreater(large.stake, small.stake)
        self.assertGreaterEqual(LEGACY.validators_for(1_098), LEGACY.validators_for(78))


class TestDeterministicGate(Setup):
    def test_checks_pass(self):
        c = self.life.submit(self.contributor, 78, 1)
        self.life.run_checks(c, True, 1)
        self.life.enter_beta(c, 2, credits(40), self.pool)
        self.assertEqual((c.state, c.window_end), ("in_beta", 2 + LEGACY.challenge_window_days))

    def test_checks_fail(self):
        c = self.life.submit(self.contributor, 78, 1)
        self.life.run_checks(c, False, 1)
        fee = share(c.stake, LEGACY.check_fee_bps)
        self.assertEqual(c.state, "failed_checks")
        self.assertEqual(self.net(c), {self.contributor: -fee, c.stake_account: 0, self.infra: fee})
        with self.assertRaises(LifecycleError):
            self.life.enter_beta(c, 2, 0, self.pool)


class TestEscrow(Setup):
    def test_no_early_payout(self):
        c = self.in_beta()
        self.assertEqual(self.ledger.balance(c.escrow_account), credits(40))
        self.assertEqual(self.life.advance(c, c.window_end - 1), "open")
        with self.assertRaises(LifecycleError):
            self.life.withdraw(c, c.window_end - 1)  # neither reward nor stake can be taken out
        self.assertEqual(self.ledger.balance(c.escrow_account), credits(40))
        self.assertEqual(self.ledger.balance(c.stake_account), c.stake - c.check_fee)


class TestChallengeWindow(Setup):
    def test_window_closes_with_no_challenge(self):
        c = self.in_beta()
        self.assertEqual(self.life.advance(c, c.window_end), "accepted")
        self.assertEqual(c.state, "accepted")

    def test_window_extended_for_a_pending_challenge(self):
        c = self.in_beta()
        end = c.window_end
        self.life.challenge_opened(c, end - 1)
        self.assertEqual(self.life.advance(c, end), "extended")
        self.assertEqual(c.window_end, end + LEGACY.extension_days)
        self.assertEqual(self.life.advance(c, c.window_end), "waiting")  # extended once only; still not settled
        self.assertEqual(c.state, "in_beta")
        self.life.challenge_closed(c, c.window_end)  # rejected
        self.assertEqual(self.life.advance(c, c.window_end), "accepted")

    def test_no_challenge_after_the_window(self):
        c = self.in_beta()
        with self.assertRaises(LifecycleError):
            self.life.challenge_opened(c, c.window_end)


class TestSettlement(Setup):
    def test_accepted(self):
        c = self.in_beta()
        self.life.advance(c, c.window_end)
        fee = share(c.stake, LEGACY.check_fee_bps)
        # proof-of-fix#10 (D9): nothing paid at acceptance; instalments start at the next release, and the stake
        # stays locked until the last one
        self.assertEqual(self.net(c), {self.contributor: -c.stake, c.stake_account: c.stake - fee,
                                       c.escrow_account: credits(40), self.infra: fee, self.pool: -credits(40)})
        self.assertEqual([e.reason for e in self.ledger.entries_for(c.ref)], ["stake", "fee", "escrow"])
        self.assertEqual((c.state, c.instalments_left), ("accepted", LEGACY.reward_instalments))
        for _ in range(LEGACY.reward_instalments):
            self.life.pay_instalment(c, c.window_end + 1)
        self.assertEqual(self.net(c)[self.contributor], credits(40) - fee)  # all paid, stake back

    def test_slashed(self):
        c = self.in_beta()
        self.life.challenge_opened(c, c.beta_day + 1)
        split = [(self.challenger, LEGACY.challenger_reward_share_bps),
                 (self.insurance, BPS - LEGACY.challenger_reward_share_bps)]
        forfeited = self.life.slash(c, "wrong_result", c.beta_day + 2, split)
        self.assertEqual(forfeited, share(c.stake, 5_000))
        fee = c.check_fee
        net = self.net(c)
        self.assertEqual(net[self.contributor], -fee - forfeited)  # the reward never reaches them
        self.assertEqual(net[self.pool], 0)  # the escrowed reward went back where it came from
        self.assertEqual(net[self.challenger] + net[self.insurance], forfeited)
        self.assertEqual((self.ledger.balance(c.stake_account), self.ledger.balance(c.escrow_account)), (0, 0))
        self.assertEqual(c.state, "slashed")

    def test_slash_never_exceeds_what_is_locked(self):
        c = self.in_beta()
        forfeited = self.life.slash(c, "crash", c.beta_day + 1, [(self.insurance, BPS)])
        self.assertEqual(forfeited, c.stake - c.check_fee)  # 100 % of the stake, less the fee already paid

    def test_withdrawn_before_beta(self):
        c = self.life.submit(self.contributor, 78, 1)
        self.life.run_checks(c, True, 1)
        self.life.withdraw(c, 2)
        self.assertEqual(self.net(c)[self.contributor], -c.check_fee)
        for step in (lambda: self.life.enter_beta(c, 3, 0, self.pool), lambda: self.life.decline(c, 3)):
            with self.assertRaises(LifecycleError):
                step()  # it can't settle any other way

    def test_withdrawn_before_checks_costs_nothing(self):
        c = self.life.submit(self.contributor, 78, 1)
        self.life.withdraw(c, 1)
        self.assertEqual(self.net(c)[self.contributor], 0)


class TestMaintainers(Setup):
    def test_maintainer_declines(self):
        c = self.life.submit(self.contributor, 1_098, 1)
        self.life.run_checks(c, True, 1)
        self.life.decline(c, 2)
        self.assertEqual(c.state, "declined")
        self.assertEqual(self.net(c)[self.contributor], 0)  # in full, check fee included
        self.assertEqual(self.ledger.balance(self.contributor), credits(5_000))

    def test_mechanism_never_merges_by_itself(self):
        c = self.life.submit(self.contributor, 78, 1)
        with self.assertRaises(LifecycleError):
            self.life.enter_beta(c, 1, 0, self.pool)  # not checked: no beta without the gate
        self.assertEqual(c.state, "submitted")


if __name__ == "__main__":
    unittest.main()
