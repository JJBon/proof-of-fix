"""#85 task 4.6: seat bonds against provable faults (pof/sim/oraclenet.py, design S12, S16, S17): every faulty seat
against its honest twin on the same seeds, and the bond at which each fault loses."""

import unittest

from pof.sim import oraclenet as O

SEEDS = range(1, 9)
WORLD = O.SeatWorld(bounty_prices=(60.0, 90.0, 120.0, 180.0))


class TestTwins(unittest.TestCase):
    def test_the_honest_twin_is_deterministic(self):
        self.assertEqual(O.seat_year(WORLD, None, 500, 7), O.seat_year(WORLD, None, 500, 7))

    def test_a_tiny_bond_lets_the_non_revealer_and_the_padding_pair_gain(self):
        """The bond matters: at $25, a bribed silence and a padding pair pay."""
        for name in ("non_revealer", "usage_padders (a pair)"):
            m, se, loses = O.against_twin(WORLD, O.FAULTS[name], 25, SEEDS)
            self.assertGreater(m, 0, name)
            self.assertFalse(loses, name)

    def test_every_fault_loses_at_a_bond_of_1000(self):
        for name, fault in O.FAULTS.items():
            m, se, loses = O.against_twin(WORLD, fault, 1_000, SEEDS)
            self.assertTrue(loses, f"{name}: {m:.0f} ± {se:.0f}")

    def test_a_lone_padder_gains_nothing_from_the_median(self):
        """The median rule: a lone padder is paid the honest usage, so padding only risks its bond."""
        m, se, loses = O.against_twin(WORLD, O.FAULTS["usage_padder (alone)"], 25, SEEDS)
        self.assertLess(m, 0)


class TestBonds(unittest.TestCase):
    def test_the_smallest_bond(self):
        sweep = O.bond_sweep(WORLD, (25, 100, 250, 1_000), SEEDS)
        self.assertIn(O.smallest_bond(sweep), (250, 1_000))

    def test_one_fault_on_one_bounty(self):
        f = O.FAULTS["equivocator"]
        self.assertAlmostEqual(O.one_shot_bond(f, 500), 500 / f.detect)
        self.assertAlmostEqual(O.one_shot_bond(O.FAULTS["non_revealer"], 400), 400 * 0.05 / 0.05)
        self.assertEqual(O.one_shot_bond(O.FAULTS["usage_padder (alone)"], 400), 0.0)


if __name__ == "__main__":
    unittest.main()
