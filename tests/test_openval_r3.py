"""#141 round 3 (task group 8 of #132): D17's round-3 criteria ("not shown to gain", LONE_CATCH_SHARE on the lone
validator's own verdicts, WAIT_CROWD_MAX 20 %) with round 2's kept as a switch; report v3's numbers re-judged; the
silence and withholding slash in proportion to the bounty (SILENCE_SLASH_BPS, SEALED_NO_REVEAL_SLASH_BPS); the
deposit's honest cost; and `python3 -m pof.sim market validators --round3` (reports/open-validators-v3.1.md)."""

import contextlib
import copy
import io
import re
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from pof.sim import __main__ as cli
from pof.sim.openval import actors as A
from pof.sim.openval import pricing as PR
from pof.sim.openval import rerun as RR
from pof.sim.openval import round2 as RM
from pof.sim.openval import round3 as R3M
from pof.sim.openval.params import V2R1, V2R2, V2R3, WORLD, Params, diff_fields, r2_fields, r3_fields

ROOT = Path(__file__).resolve().parent.parent
V3 = ROOT / "reports" / "open-validators-v3.md"
VERDICT = re.compile(r"^\|\s*(.+?)\s*\|\s*\*\*(met|not met)\*\*\s*\|")


def v3_verdicts(text: str):
    """The verdict column of report v3's first acceptance table, in order."""
    out = []
    for line in text.split("## The acceptance table under D17, round 2", 1)[1].splitlines():
        m = VERDICT.match(line)
        if m:
            out.append(m.group(2))
        elif out and not line.startswith("|"):
            break
    return out


# ---------- the criteria (8.1) ----------

class TheCriteria(unittest.TestCase):
    def test_not_shown_to_gain(self):
        ok = RM.not_shown_to_gain
        self.assertTrue(ok(2.7, 1.95))  # the inflaters, +$2.7 ± 3.9: a mean above zero by chance
        self.assertTrue(ok(0.2, 0.35))  # the weak herders, +$0.2 ± 0.7
        self.assertTrue(ok(-1.0, 3.5))  # −$1 ± 7
        self.assertFalse(ok(3.0, 1.0))  # +$3 ± 2: the lower bound, +$1, shows a gain
        self.assertFalse(ok(-34.0, 23.5))  # −$34 ± 47: the upper bound, +$13, is above the tolerance
        self.assertFalse(ok(float("nan"), 1.0))
        # round 2's "doesn't gain", the switch: the sign of the mean decides the first two
        self.assertFalse(RM.doesnt_gain(2.7, 1.95))
        self.assertFalse(RM.doesnt_gain(0.2, 0.35))
        self.assertTrue(RM.doesnt_gain(-1.0, 3.5))

    def test_the_test_follows_the_parameters(self):
        self.assertEqual((V2R3.GAIN_TEST, V2R2.GAIN_TEST), ("not_shown", "doesnt_gain"))
        self.assertTrue(RM.gain_ok(2.7, 1.95, V2R3))
        self.assertFalse(RM.gain_ok(2.7, 1.95, V2R2))
        self.assertEqual(RM.gain_cell(2.7, 1.95, test="not_shown"), "yes")
        self.assertEqual(RM.gain_cell(3.0, 1.0, test="not_shown"), "**no: it gains**")
        self.assertEqual(RM.gain_cell(-34.0, 23.5, test="not_shown"), "**no: up to +13**")

    def test_round_3_changes_the_criteria_only(self):
        self.assertEqual(V2R3, Params())
        self.assertEqual(set(r3_fields()), {"GAIN_TEST", "LONE_CATCH_COUNT", "WAIT_CROWD_MAX"})
        self.assertEqual((V2R3.WAIT_CROWD_MAX, V2R2.WAIT_CROWD_MAX), (0.20, 0.15))
        self.assertEqual((V2R3.LONE_CATCH_COUNT, V2R2.LONE_CATCH_COUNT), ("own", "all"))
        # round 1's set keeps round 2's criteria fields, so round 2's diff is unchanged
        self.assertNotIn("GAIN_TEST", r2_fields())
        self.assertEqual(V2R1.WAIT_CROWD_MAX, 0.15)

    def test_the_same_simulation_under_both_criteria(self):
        a = A.run(A.LoneColluder(), 1, p=V2R2, w=replace(WORLD, weeks=8))
        b = A.run(A.LoneColluder(), 1, p=V2R3, w=replace(WORLD, weeks=8))
        self.assertEqual(dict(a.stats), dict(b.stats))
        self.assertEqual(a.party_net("colluder"), b.party_net("colluder"))

    def test_the_lone_share_counts_its_own_verdicts(self):
        col = {"reversed": [9, 8], "resolved": [10, 10], "own_reversed": [9, 8], "own_resolved": [9, 8]}
        self.assertEqual(RM.lone_share(col, V2R3)[0], 1.0)
        self.assertAlmostEqual(RM.lone_share(col, V2R2)[0], 0.85)


# ---------- report v3 re-judged (8.1, 8.4) ----------

class ReportV3Rejudged(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = V3.read_text(encoding="utf-8")
        cls.lines = cls.text.splitlines()

    def _line_with(self, key):
        found = [ln for ln in self.lines if key in ln]
        self.assertTrue(found, key)
        return found

    def test_the_numbers_are_report_v3s(self):
        for key, rows in R3M.V3_ROWS.items():
            for name, value, anchor in rows:
                with self.subTest(name):
                    self.assertTrue(any(value in ln for ln in self._line_with(anchor)), (anchor, value))
        for key, (value, anchor) in R3M.V3.items():
            with self.subTest(key):
                self.assertTrue(any(value in ln for ln in self._line_with(anchor)), (anchor, value))

    def test_round_2s_criteria_give_v3s_verdicts(self):
        self.assertEqual(v3_verdicts(self.text), R3M.V3_VERDICTS)
        self.assertEqual([c.verdict for c in R3M.rejudge(V2R2)], R3M.V3_VERDICTS)

    def test_round_3s_criteria_meet_every_one(self):
        crit = R3M.rejudge(V2R3)
        self.assertEqual(len(crit), 14)
        self.assertTrue(all(c.met for c in crit), [c.name for c in crit if not c.met])
        changed = [b.name for a, b in zip(R3M.rejudge(V2R2), crit) if a.met != b.met]
        self.assertEqual(len(changed), 5)  # pricing, scoring, the colluder, the crowding, and adoption

    def test_each_switch_alone_restores_its_failure(self):
        for field, value, phrase in (("GAIN_TEST", "doesnt_gain", "pricing attacker"),
                                     ("LONE_CATCH_COUNT", "all", "colluding lone"),
                                     ("WAIT_CROWD_MAX", 0.15, "crowds into one model")):
            with self.subTest(field):
                crit = R3M.rejudge(replace(V2R3, **{field: value}))
                self.assertFalse(next(c for c in crit if phrase in c.name).met)
                self.assertFalse(crit[-1].met)


# ---------- the acceptance check of a full run under round 3's criteria (8.1) ----------

class TheAcceptanceCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = RM.quick_collect()  # shared with tests/test_openval_r2.py; copied before any change

    def test_round_2s_words_are_unchanged_and_round_3s_follow_the_test(self):
        r2, r3 = RM.acceptance(self.d, V2R2), RM.acceptance(self.d, V2R3)
        self.assertIn("doesn't gain", r2[0].name)
        self.assertIn("isn't shown to gain", r3[0].name)
        self.assertIn("passes itself, as the lone judge", next(c for c in r3 if "colluding lone" in c.name).name)
        rows = RM.counted_rows(self.d)
        for c, key in zip(r3[:4], ("open", "pricing", "levels", "scores")):
            self.assertEqual(c.met, bool(rows[key]) and all(RM.not_shown_to_gain(m, se) for _, m, se in rows[key]))

    def test_a_gain_too_small_to_show_passes_only_round_3(self):
        d = copy.deepcopy(self.d)
        r = d["silent"][0][2]
        r["diff"], r["se"] = 2.7, 1.95  # +$2.7 ± 3.9
        self.assertFalse(RM.acceptance(d, V2R2)[0].met)
        self.assertEqual(RM.acceptance(d, V2R3)[0].met, RM.acceptance(self.d, V2R3)[0].met)
        r["diff"], r["se"] = 3.0, 1.0  # +$3 ± 2: shown
        self.assertFalse(RM.acceptance(d, V2R3)[0].met)

    def test_the_lone_share_is_its_own_verdicts(self):
        d = copy.deepcopy(self.d)
        m = d["colluder"][0][2]
        m["reversed"], m["resolved"] = [8], [10]  # 80 % of every bad fix of its accomplice
        m["own_reversed"], m["own_resolved"] = [10], [10]  # all of its own
        name = "colluding lone"
        self.assertFalse(next(c for c in RM.acceptance(d, V2R2) if name in c.name).met)
        own = next(c for c in RM.acceptance(d, V2R3) if name in c.name)
        self.assertEqual(own.met, RM.gain_ok(*RR.mean_se(m["diff"]), V2R3))


# ---------- the slash in proportion to the bounty (8.2) ----------

class TheSlashSweep(unittest.TestCase):
    def test_the_slash_follows_the_bounty(self):
        p = R3M.sweep_params(5.0)
        self.assertEqual((p.SILENCE_SLASH_BPS, p.SEALED_NO_REVEAL_SLASH_BPS), (500, 500))
        for sealed in (False, True):
            self.assertEqual(V2R3.miss_slash(625.0, sealed), 5.0)  # x = 0: flat
            self.assertEqual(p.miss_slash(50.0, sealed), 5.0)  # 5 % of $50 is under $5
            self.assertAlmostEqual(p.miss_slash(625.0, sealed), 31.25)
            self.assertEqual(p.miss_slash(0.0, sealed), 5.0)  # an ADR has no bounty
        self.assertEqual(replace(V2R3, SILENCE_SLASH_BPS=200).miss_slash(625.0, True), 5.0)  # each its own switch
        self.assertAlmostEqual(replace(V2R3, SILENCE_SLASH_BPS=200).miss_slash(625.0, False), 12.5)

    def test_each_sweep_point_changes_only_what_it_names(self):
        for x in R3M.SWEEP_X + R3M.SWEEP_EXTRA:
            self.assertLessEqual(set(diff_fields(R3M.sweep_params(x), V2R3)),
                                 {"SILENCE_SLASH_BPS", "SEALED_NO_REVEAL_SLASH_BPS"})
        self.assertEqual(R3M.sweep_params(0.0), V2R3)

    def test_x_0_gives_round_2s_numbers(self):
        w = replace(A.SilentJudge().world(), weeks=12)
        for make in (lambda h: A.SilentJudge(h), lambda h: A.SilentJudge(h, sealed=True)):
            self.assertEqual(A.against_twin(make, [1], p=R3M.sweep_params(0.0), w=w)["diff"],
                             A.against_twin(make, [1], p=V2R2, w=w)["diff"])
        a = RR.honest_breakdown(PR.run_market(1, R3M.sweep_params(0.0), replace(RR.MARKET_W, weeks=12)))
        b = RR.honest_breakdown(PR.run_market(1, V2R2, replace(RR.MARKET_W, weeks=12)))
        self.assertEqual(a, b)

    def test_a_bribed_miss_pays_the_bountys_share(self):
        w = replace(A.SilentJudge().world(), weeks=12, reliability=1.0)
        for sealed in (False, True):
            n0 = A.run(A.SilentJudge(sealed=sealed), 1, p=V2R3, w=w)
            n5 = A.run(A.SilentJudge(sealed=sealed), 1, p=R3M.sweep_params(5.0), w=w)
            me0, me5 = n0.party_validators("silent")[0], n5.party_validators("silent")[0]
            k = n5.stats["silences"]
            self.assertGreater(k, 0)
            self.assertAlmostEqual(me0.acct.slashed, 5.0 * n0.stats["silences"])
            self.assertGreater(me5.acct.slashed, 5.0 * k)  # some bounties are above $100
            self.assertGreaterEqual(me5.acct.slashed + 1e-9, me5.acct.gains)  # bribed 5 %: at least the bribe
        p5 = R3M.sweep_params(5.0)
        self.assertGreater(PR.outage_slash(p5, WORLD, 250.0, [(1.0, 625.0)]), PR.outage_slash(V2R3, WORLD, 250.0))
        self.assertEqual(PR.outage_slash(V2R3, WORLD, 250.0, [(1.0, 625.0)]), PR.outage_slash(V2R3, WORLD, 250.0))


# ---------- the deposit's honest cost (8.3) ----------

class TheHonestAuthor(unittest.TestCase):
    def test_it_submits_good_adrs_that_are_judged_and_forfeits_only_on_rejection(self):
        r = R3M.deposit_cost((1,), quick=True)[0][1]
        self.assertGreater(r["submitted"][0], 30)
        self.assertEqual(r["expired"][0], 0)  # 25 active: the constitution tier is drawn
        self.assertGreater(r["passed"][0], r["rejected"][0])
        self.assertAlmostEqual(r["forfeited"][0], 15.0 * r["rejected"][0])
        self.assertAlmostEqual(r["diff"][0], -r["forfeited"][0])  # the same run but for the deposit


# ---------- the command and the report (8.4) ----------

class TheCommand(unittest.TestCase):
    def test_the_command_prints_round_3s_addendum(self):
        out = io.StringIO()
        with mock.patch.object(R3M, "full_report", lambda *a, **k: "ROUND-3 ADDENDUM"), \
                contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["market", "validators", "--round3", "--seeds", "1", "--quick"]), 0)
        self.assertEqual(out.getvalue(), "ROUND-3 ADDENDUM\n")

    def test_the_quick_report_is_reproducible_and_names_each_criterion(self):
        a = R3M.collect((1,), quick=True)
        self.assertEqual(repr(a["silent"]), repr(R3M._section("silent", (1,), True)))
        out = R3M.render(a)
        for heading in ("Report v3 re-judged", "The silence-slash sweep", "The deposit's honest cost"):
            self.assertIn(heading, out)
        self.assertEqual(out.count("| **met** |"), 14)


class TheReport(unittest.TestCase):
    REPORT = ROOT / "reports" / "open-validators-v3.1.md"

    def test_the_report_names_each_criterion_met_or_not(self):
        if not self.REPORT.exists():
            self.skipTest("reports/open-validators-v3.1.md not written yet")
        text = self.REPORT.read_text(encoding="utf-8")
        self.assertIn(R3M.rejudged_md(), text)
        self.assertEqual(R3M.rejudged_md().count("| **met** |"), 14)
        for heading in ("The silence-slash sweep", "The deposit's honest cost", "Commands, seeds and tests"):
            self.assertIn(heading, text)


if __name__ == "__main__":
    unittest.main()
