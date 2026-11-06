"""The oracle stand-in's acceptance test for the issue, kept from solvers until it checks a fix (like the hidden
tests in the simulation)."""

import unittest

from stats import median


class TestMedianEven(unittest.TestCase):
    def test_even_count(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_odd_count_still(self):
        self.assertEqual(median([5, 1, 3]), 3)


if __name__ == "__main__":
    unittest.main()
