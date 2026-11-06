"""Task 2.2: the published parameters (design D5) and their validation."""

import unittest

from pof import BPS
from pof.params import LEGACY, Params, ParamsError


class TestDefaults(unittest.TestCase):
    def test_defaults_are_valid_and_match_design(self):
        p = Params()
        self.assertEqual(sum(p.release_split_bps.values()), BPS)
        self.assertEqual(p.release_split_bps["author"], 1_000)
        self.assertEqual(p.release_split_bps["owner"], 500)
        self.assertEqual((p.challenge_window_days, p.extension_days), (7, 3))

    def test_frozen(self):
        with self.assertRaises(Exception):
            LEGACY.base_stake = 1
        with self.assertRaises(TypeError):
            LEGACY.release_split_bps["owner"] = 9_000


class TestValidation(unittest.TestCase):
    def test_owner_share_above_cap_refused(self):
        split = dict(LEGACY.release_split_bps, owner=600, contributors=4_900)
        with self.assertRaises(ParamsError):
            LEGACY.with_(release_split_bps=split)

    def test_cap_itself_cannot_be_raised(self):
        split = dict(LEGACY.release_split_bps, owner=1_000, contributors=4_500)
        with self.assertRaises(ParamsError):
            LEGACY.with_(release_split_bps=split, owner_share_cap_bps=1_000)

    def test_shares_must_sum_to_the_whole(self):
        with self.assertRaises(ParamsError):
            LEGACY.with_(release_split_bps=dict(LEGACY.release_split_bps, contributors=4_000))

    def test_tiers_ordered(self):
        with self.assertRaises(ParamsError):
            LEGACY.with_(size_tiers=(400, 100, 1500))
        with self.assertRaises(ParamsError):
            LEGACY.with_(stake_multiplier=(1, 5, 2, 10))
        with self.assertRaises(ParamsError):
            LEGACY.with_(validators=(3, 4, 5, 7))  # even panel

    def test_severity_order(self):
        with self.assertRaises(ParamsError):
            LEGACY.with_(severity_slash_bps={"crash": 1_000, "wrong_result": 5_000, "cosmetic": 1_000})

    def test_bps_bounds(self):
        with self.assertRaises(ParamsError):
            LEGACY.with_(check_fee_bps=10_001)


class TestDerived(unittest.TestCase):
    def test_larger_contributions_need_larger_stakes(self):
        # specs/contribution-lifecycle "Larger contributions need larger stakes": merged median vs stale median
        small, large = 78, 1_098
        self.assertGreater(LEGACY.stake_for(large), LEGACY.stake_for(small))
        self.assertGreaterEqual(LEGACY.validators_for(large), LEGACY.validators_for(small))

    def test_tiers(self):
        self.assertEqual([LEGACY.tier(n) for n in (1, 100, 101, 400, 401, 1500, 1501)], [0, 0, 1, 1, 2, 2, 3])
        self.assertEqual(LEGACY.jurors_for(78), 7)

    def test_risk_class(self):
        self.assertEqual(LEGACY.stake_for(78, "high"), 2 * LEGACY.stake_for(78))
        with self.assertRaises(ParamsError):
            LEGACY.stake_for(78, "extreme")


if __name__ == "__main__":
    unittest.main()
