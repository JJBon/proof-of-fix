"""Task 1.1: the package layout imports (design D3)."""

import importlib
import unittest


class TestPackage(unittest.TestCase):
    def test_modules_import(self):
        for name in ("pof", "pof.ledger", "pof.params", "pof.sim"):
            self.assertIsNotNone(importlib.import_module(name))

    def test_amount_helpers(self):
        from pof import MICRO, credits, share

        self.assertEqual(credits(10), 10 * MICRO)
        self.assertEqual(share(credits(1), 3_333), 333_300)
        self.assertEqual(share(7, 5_000), 3)  # rounds down; the caller places the remainder


if __name__ == "__main__":
    unittest.main()
