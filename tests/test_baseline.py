"""Task 6.1: data/gridcraft_baseline.json holds aggregates only, and agrees with the sample on it-ops#14."""

import json
import re
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "gridcraft_baseline.json"
STRINGS = {"source", "fetched", "note"}  # the only string-valued fields; everything else is a number or a count


def leaves(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from leaves(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from leaves(v, path + (str(i),))
    else:
        yield path, node


class TestBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DATA.read_text(encoding="utf-8")
        cls.data = json.loads(cls.text)

    def test_aggregates_only(self):
        for path, value in leaves(self.data):
            if path[0] in STRINGS or path[0] == "window":
                continue
            self.assertIsInstance(value, (int, float), f"{'/'.join(path)} is not a number")
        keys = {k for path, _ in leaves(self.data) for k in path}
        allowed = re.compile(r"^(\d+|p\d+|max|count|<=\d+|>\d+|\d{4}-W\d{2}|[a-z_]+)$")
        self.assertTrue(all(allowed.match(k) for k in keys), sorted(k for k in keys if not allowed.match(k)))

    def test_no_identities(self):
        self.assertNotRegex(self.text, r"github\.com/|https?://|@[A-Za-z0-9-]+|#\d+")
        self.assertEqual(self.data["source"], "storytold/gridcraft")
        self.assertNotIn("author", self.text.replace("distinct_authors", ""))

    def test_matches_the_sample(self):
        # it-ops#14 comment 3323 (40 merged PRs, 2026-10-23): median 78 changed lines
        median = self.data["merged"]["changed_lines"]["p50"]
        self.assertLessEqual(abs(median - 78) / 78, 0.10)

    def test_shape_the_simulation_needs(self):
        merged = self.data["merged"]
        self.assertGreater(merged["count"], 100)
        self.assertEqual(sum(merged["changed_lines_histogram"].values()), merged["count"])
        self.assertTrue(self.data["weekly"])
        self.assertTrue(0 <= merged["human_review_share"] <= 1)


if __name__ == "__main__":
    unittest.main()
