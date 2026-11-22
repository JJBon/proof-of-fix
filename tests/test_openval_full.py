"""#134 task 1.8 (pof/sim/openval/full.py): the full report of v3's open validators, `python3 -m pof.sim market
validators`. Its numbers are reproducible on fixed seeds, it names each acceptance criterion of the incentive-simulation
delta as met or not, and so does reports/open-validators-v1.md. Plus the pieces 1.8 adds: a fixed k of 3, k = 1's
window, and the score factor on the market fee."""

import contextlib
import io
import re
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from pof.sim import __main__ as cli
from pof.sim.openval import full as F
from pof.sim.openval import scores as SC
from pof.sim.openval.net import Net
from pof.sim.openval.params import DAY, WORLD
from pof.sim.openval.params import V1 as PARAMS  # #134's rules: these tests keep them reachable (#141)

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "open-validators-v1.md"

# the criteria of specs/incentive-simulation's "Acceptance criteria for open validators", by a phrase of each row
CRITERIA = ("open-validator attacker loses", "pricing attacker loses", "proof-level attacker loses",
            "scoring attacker", "service fee settles", "sybil just under the published share",
            "sybil at the published share", "colluding lone validator", "constitution waits",
            "every earlier criterion", "adopt the k table")
VERDICT = re.compile(r"\*\*(met|not met)\b")


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


def acceptance_rows(text):
    """{criterion phrase: verdict} from the acceptance table in `text`."""
    rows = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        for phrase in CRITERIA:
            if phrase in cells[0].lower():
                m = VERDICT.search(cells[1])
                if m:
                    rows[phrase] = m.group(1)
    return rows


class TheCommand(unittest.TestCase):
    """`python3 -m pof.sim market validators --v1` (#134's report, which #141 keeps reachable): its output on seed 1,
    captured before #141's change, is tests/data/openval-v1-quick-seed1.md; tests/test_openval_v2.py checks that the
    command still prints it byte for byte."""

    @classmethod
    def setUpClass(cls):
        cls.rc, cls.out = 0, (ROOT / "tests" / "data" / "openval-v1-quick-seed1.md").read_text(encoding="utf-8")

    def test_reproducible_on_fixed_seeds(self):
        self.assertEqual(self.rc, 0)
        self.assertIn("## Acceptance criteria", self.out)
        self.assertRegex(self.out, r"\d")

    def test_names_each_criterion_met_or_not(self):
        rows = acceptance_rows(self.out)
        self.assertEqual(set(rows), set(CRITERIA))
        self.assertEqual(rows["adopt the k table"], "not met" if "not met" in
                         [v for k, v in rows.items() if k != "adopt the k table"] else "met")

    def test_every_section_is_in_it(self):
        for heading in ("### Growth from one validator", "### Each attacker against its honest twin",
                        "### The sybil's majorities", "### The watcher's dilemma", "### The k table compared",
                        "### The window's length", "### Each proof-level attacker", "### The fee finds the validators'",
                        "### The pricing attackers", "### Herding (", "### Herding on the market fee",
                        "### Acceptance criteria for open validators"):
            self.assertIn(heading, self.out)


class TheReport(unittest.TestCase):
    def test_the_report_names_each_criterion_met_or_not(self):
        rows = acceptance_rows(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(set(rows), set(CRITERIA))


class TheVerdicts(unittest.TestCase):
    def test_an_attacker_that_doesnt_lose_significantly_fails_the_criterion(self):
        loses = {"diff": -100.0, "se": 10.0}
        unclear = {"diff": -10.0, "se": 10.0}  # -10 + 2 x 10 > 0: not a significant loss
        self.assertEqual(F._against_twin([("a", loses)])[0], True)
        met, why = F._against_twin([("a", loses), ("b", unclear)])
        self.assertFalse(met)
        self.assertIn("b (-10 ± 20 $)", why)

    def test_a_verdict_says_met_or_not_met_and_any_condition(self):
        self.assertEqual(F.Criterion("x", True, "n").verdict, "met")
        self.assertEqual(F.Criterion("x", False, "n", "for any share").verdict, "not met (for any share)")


class FixedK(unittest.TestCase):
    def test_a_fixed_k_never_judges_with_fewer(self):
        w = replace(WORLD, weeks=6)
        n = F.FixedKNet(1, PARAMS, w, k=3).run()  # growth from one validator: nobody to sit beside it
        self.assertEqual(n.stats["drawn"], 0)
        self.assertGreater(n.stats["waited"], 0)
        g = F.FixedKNet(1, PARAMS, replace(F.GROWN, weeks=3), k=3).run()
        ks = Counter(s.k for s in g.subs.values() if s.draw is not None and s.tier == "issue")
        self.assertGreater(ks[3], 0)
        self.assertEqual(set(ks), {3})

    def test_the_k_table_draws_from_one_validator(self):
        n = Net(1, PARAMS, replace(WORLD, weeks=6)).run()
        self.assertGreater(n.stats["k1"], 0)


class Window(unittest.TestCase):
    def test_k1_window_and_unbonding_follow(self):
        p = F.window_params(336.0, PARAMS)
        self.assertEqual(p.window_h(1), 336.0)
        self.assertEqual(p.window_h(3), PARAMS.window_h(3))
        self.assertEqual(p.CHALLENGE_WINDOW_H["C"], PARAMS.CHALLENGE_WINDOW_H["C"])
        self.assertEqual(p.UNBONDING_DELAY_H, 336.0 + 7 * DAY)
        self.assertEqual(PARAMS.window_h(1), 72.0)  # the design's value is untouched


class FactorOnTheMarketFee(unittest.TestCase):
    def test_the_factor_scales_the_service_fee_not_the_usage(self):
        class Inner:  # a market fee: $0.25 of service plus $0.07 of usage margin
            def fee(self, net, sub, v):
                return 0.32

            def service_part(self, sub):
                return 0.25

        class Flat:
            def fee(self, net, sub, v):
                return 0.05

        class Scores:
            def factor(self, family):
                return 2.0

        class Draw:
            drawn = {7}

        class Sub:
            draw = Draw()

        class V:
            vid, family = 7, "top"

        self.assertAlmostEqual(SC.ScoredFee(Inner(), Scores()).fee(None, Sub(), V()), 0.57)
        self.assertAlmostEqual(SC.ScoredFee(Flat(), Scores()).fee(None, Sub(), V()), 0.10)

    def test_herders_run_on_the_market(self):
        a = F.MarketHerders(False, family="mid", detectable=False)
        n = Net(1, PARAMS, replace(a.world(), weeks=3), [a]).run()
        self.assertIsInstance(n.fee, SC.ScoredFee)
        self.assertEqual(len(n.party_validators("herders")), 4)
        self.assertGreater(n.stats["herded"], 0)


if __name__ == "__main__":
    unittest.main()
