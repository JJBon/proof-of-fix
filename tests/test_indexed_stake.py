"""proof-of-fix#23 tasks 1-2: the stake indexed to the expected reward, and the reward cap (spec delta scenarios for
contribution-lifecycle and release-payouts)."""

import re
import unittest

from pof import credits, share
from pof.ledger import Ledger
from pof.params import LEGACY, ParamsError

from test_fixes import World


class TestParams(unittest.TestCase):
    def test_validation(self):
        for bad in ({"stake_floor": 0}, {"stake_floor": LEGACY.base_stake + 1}, {"stake_index_window": 0},
                    {"reward_cap_stake_multiple": -1}, {"stake_per_reward_bps": 10_001}):
            with self.assertRaises(ParamsError, msg=bad):
                LEGACY.with_(**bad)
        LEGACY.with_(stake_per_reward_bps=0, reward_cap_stake_multiple=0)  # both off: the fixed-stake rules

    def test_the_index_is_clamped(self):
        fixed = LEGACY.stake_for(78)
        self.assertEqual(LEGACY.stake_for(78, reward_per_weight=10**12), fixed)  # never above the fixed stake
        self.assertEqual(LEGACY.stake_for(78, reward_per_weight=1), LEGACY.stake_floor)  # never below the floor
        mid = LEGACY.stake_for(78, reward_per_weight=credits(2))
        self.assertEqual(mid, share(credits(2) * 78, LEGACY.stake_per_reward_bps))
        self.assertEqual(LEGACY.stake_for(78, "high", credits(2)), mid * LEGACY.risk_multiplier["high"])


class Index(World):
    def setUp(self):
        super().setUp()
        self.ledger.issue(self.dev, credits(100_000), "endowment", "setup", 0)  # enough for many submissions

    def author(self):
        """A new funded contributor: one author's weight per release is capped (#10), so a busy release needs many."""
        a = self.ledger.open("actor")
        self.ledger.issue(a, credits(1_000), "endowment", "setup", 0)
        return a

    def ship(self, sizes, day):
        """Close the open release (if any), open the next, and ship these contributions, each by its own author, in
        its beta build."""
        if self.rel.current is not None:
            self.rel.close_release(self.rel.current, [], day)
        r = self.rel.open_release(day)
        cs = [self.checked(self.author(), lines=n, day=day) for n in sizes]
        return r, cs, self.rel.ship_beta(r, cs, day)

    def offers(self):
        out = []
        for e in self.ledger.events:
            if e.kind == "stake_index":
                out.append(tuple(int(x) for x in re.findall(r"=(\d+)", e.detail)))
        return out


class TestIndexedStake(Index):
    def test_no_history_yet(self):
        self.assertIsNone(self.life.reward_per_weight)
        c = self.life.submit(self.dev, 78, 1)
        self.assertEqual(c.stake, LEGACY.stake_for(78))

    def test_the_stake_follows_the_reward(self):
        self.ship([78] * 40, 1)
        quiet = self.life.stake_for(78)
        self.assertLess(quiet, LEGACY.stake_for(78))  # already indexed below the fixed stake
        self.ship([78] * 160, 8)  # four times as many contributions share the next release
        busy = self.life.stake_for(78)
        self.assertLess(busy, quiet)
        self.assertGreaterEqual(busy, LEGACY.stake_floor)
        self.ship([78] * 400, 15)
        self.ship([78] * 400, 22)
        self.ship([78] * 400, 29)
        self.assertEqual(self.life.stake_for(78), LEGACY.stake_floor)  # never below the floor

    def test_never_above_the_fixed_stake(self):
        self.ship([1], 1)  # one tiny contribution takes the whole offer: a huge rate per line
        self.assertEqual(self.life.stake_for(78), LEGACY.stake_for(78))

    def test_larger_contributions_still_need_larger_stakes(self):
        self.ship([78] * 40, 1)
        self.assertGreater(self.life.stake_for(1_098), self.life.stake_for(78))

    def test_anyone_can_recompute_the_stake(self):
        for day, sizes in ((1, [78] * 5), (8, [300] * 30), (15, [40] * 12), (22, [78] * 60), (29, [500] * 3)):
            self.ship(sizes, day)
        window = self.offers()[-LEGACY.stake_index_window:]
        index = sum(p for p, _, _ in window) // sum(w for _, w, _ in window)
        self.assertEqual(index, window[-1][2])
        self.assertEqual(self.life.stake_for(78), LEGACY.stake_for(78, reward_per_weight=index))
        self.assertEqual(self.life.submit(self.dev, 78, 30).stake, LEGACY.stake_for(78, reward_per_weight=index))


class TestRewardCap(Index):
    def test_lone_contribution_in_a_sparse_release(self):
        pool = self.rel.contributors_pool
        r = self.rel.open_release(1)
        before = self.ledger.balance(pool)
        c = self.checked(day=1)
        rewards = self.rel.ship_beta(r, [c], 1)
        cap = LEGACY.reward_cap_stake_multiple * c.stake
        self.assertLess(cap, before)  # the whole pool would have been above the cap
        self.assertEqual((rewards[c.id], self.ledger.balance(c.escrow_account)), (cap, cap))
        self.assertEqual(self.ledger.balance(pool), before - cap)  # the rest stays for the next release

    def test_under_the_cap(self):
        _, cs, rewards = self.ship([78] * 100, 1)  # 100 shares, each well under 8 x the stake
        pool = sum(rewards.values())
        for c in cs:
            self.assertLess(rewards[c.id], LEGACY.reward_cap_stake_multiple * c.stake)
        self.assertEqual(len(set(rewards.values())), 1)  # equal weights, equal shares: the division is unchanged
        self.assertGreater(pool, 0)

    def test_nothing_lost(self):
        pool = self.rel.contributors_pool
        r = self.rel.open_release(1)
        before = self.ledger.balance(pool)
        cs = [self.checked(lines=n, day=1) for n in (1, 78, 1_098)]
        rewards = self.rel.ship_beta(r, cs, 1)
        self.assertEqual(sum(rewards.values()) + self.ledger.balance(pool), before)
        escrowed = sum(self.ledger.balance(c.escrow_account) for c in cs)
        self.assertEqual(escrowed, sum(rewards.values()))


if __name__ == "__main__":
    unittest.main()
