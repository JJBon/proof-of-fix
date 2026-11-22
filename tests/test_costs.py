"""proof-of-fix#82 B2: the running-cost model (pof/costs.py) for #85's judges: a check, a paid fix and an ADR."""

import io
import unittest
from contextlib import redirect_stdout
from dataclasses import replace

from pof import costs as C


class TestReview(unittest.TestCase):
    def test_prices_per_million_with_the_cache(self):
        m = C.Model("x", "x", input=2.0, cached=0.2, output=10.0, source="test")
        r = C.Review(input=10_000, cacheable=4_000, output=1_000)
        self.assertAlmostEqual(C.review(m, r, cached=False), (10_000 * 2 + 1_000 * 10) / 1e6)
        self.assertAlmostEqual(C.review(m, r), (6_000 * 2 + 4_000 * 0.2 + 1_000 * 10) / 1e6)

    def test_every_price_is_listed_and_the_cache_never_costs_more(self):
        for grade in C.GRADES.values():
            self.assertEqual(set(grade), set(C.CONSTITUTION_TIER))
            for m in grade.values():
                self.assertGreater(m.input, 0)
                self.assertLessEqual(m.cached, m.input)
                self.assertTrue(m.source)

    def test_the_tiers_seat_distinct_families(self):
        self.assertEqual(len(C.ISSUE_TIER), 3)
        self.assertEqual(len(set(C.CONSTITUTION_TIER)), 7)
        self.assertTrue(set(C.ISSUE_TIER) <= set(C.CONSTITUTION_TIER))


class TestCheckFixAdr(unittest.TestCase):
    def test_a_check_is_its_runs_and_its_three_judges(self):
        for size in C.REVIEWS:
            c = C.check(size)
            self.assertAlmostEqual(c["total"], c["sandbox"] + c["judges"])
            self.assertAlmostEqual(c["judges"], sum(C.review(C.JUDGE[f], C.REVIEWS[size]) for f in C.ISSUE_TIER))
            self.assertLess(C.check(size, "cheap")["total"], c["total"])

    def test_bigger_fixes_cost_more(self):
        sizes = list(C.REVIEWS)
        totals = [C.fix(size)["total"] for size in sizes]
        self.assertEqual(totals, sorted(totals))

    def test_a_fix_adds_up(self):
        f = C.fix("medium")
        self.assertAlmostEqual(f["total"], f["registrations"] + f["checks"] + f["escalations"] + f["gas"])
        self.assertAlmostEqual(f["checks"], C.COUNTS.submissions * C.check("medium")["total"])
        self.assertAlmostEqual(f["escalations"], C.COUNTS.escalations * C.escalation("medium"))

    def test_the_mix_is_a_weighted_mean(self):
        self.assertAlmostEqual(sum(C.SIZE_MIX.values()), 1.0)
        mix = C.fix_mix()
        self.assertAlmostEqual(mix["total"], sum(w * C.fix(s)["total"] for s, w in C.SIZE_MIX.items()))

    def test_gas_is_every_call_at_the_chain_prices(self):
        chain = C.Chain(gwei=1.0, eth_usd=1_000.0, data_fee=0.5)
        calls = C.COUNTS.calls()
        expected = sum(C.GAS[k] * n for k, n in calls.items()) * 1e-9 * 1_000 + 0.5 * sum(calls.values())
        self.assertAlmostEqual(C.gas(C.COUNTS, chain), expected)
        self.assertEqual(set(calls), set(C.GAS))

    def test_more_escalations_cost_more(self):
        more = replace(C.COUNTS, escalations=C.COUNTS.escalations * 2)
        self.assertGreater(C.fix("small", counts=more)["total"], C.fix("small")["total"])

    def test_an_adr_seats_seven_judges(self):
        a = C.adr()
        self.assertAlmostEqual(a["judges"], sum(C.review(C.JUDGE[f], C.ADR) for f in C.CONSTITUTION_TIER))
        self.assertAlmostEqual(a["total"], a["judges"] + a["sandbox"] + a["gas"])

    def test_fees_and_the_operators_margin(self):
        self.assertAlmostEqual(C.fee(2.0, 0.5), 3.0)
        self.assertEqual(C.operator_profit("medium", 0.0), 0.0)
        self.assertAlmostEqual(C.operator_profit("medium", 0.2, verdicts=1),
                               0.2 * C.review(C.JUDGE["anthropic"], C.REVIEWS["medium"]))


class TestOutput(unittest.TestCase):
    def test_the_tables(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(C.main([]), 0)
        for heading in ("Cost per check", "Cost per paid fix", "Cost per ADR", "Sensitivity"):
            self.assertIn(heading, out.getvalue())

    def test_measure_reads_the_simulated_market(self):
        counts = C.measure(2)
        self.assertEqual(set(counts), {"paid", "registrations", "attempts", "submissions", "escalations",
                                       "escalation_rate"})
        self.assertGreater(counts["paid"], 0)
        self.assertGreaterEqual(counts["submissions"], 1.0)
        self.assertTrue(0 <= counts["escalation_rate"] <= 1)


if __name__ == "__main__":
    unittest.main()
