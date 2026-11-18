"""#236 (pof/sim/openval/contenders.py): disputes backed by evidence and the attackers, on measured judges."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from pof.sim.openval import actors as A
from pof.sim.openval import contenders as C
from pof.sim.openval import measured as M
from pof.sim.openval.params import PARAMS, WORLD


class TestCover(unittest.TestCase):
    def test_the_counts_are_the_judge_runs(self):
        others = tuple(s for s in C.ALL_SEATS if s != "anthropic")
        c = C.cover(lambda v: v["anthropic"], others, "hidden")
        self.assertEqual((c["bad_passed"], c["bad_flagged"], c["good_passed"], c["good_flagged"]), (18, 11, 47, 30))
        self.assertAlmostEqual(C.per_100(c, 0)[0], 6.0, places=1)
        self.assertLess(C.per_100(c, .5)[0], C.per_100(c, 0)[0])

    def test_a_contender_that_passes_everything_the_panel_passes_reverses_nothing(self):
        c = C.cover(lambda v: v["anthropic"], ("anthropic",), "hidden")
        self.assertEqual((c["bad_flagged"], c["good_flagged"]), (0, 0))


class TestEvidence(unittest.TestCase):
    def run_net(self, **kw):
        w = replace(C.with_evidence(M.world(M.OPUS, "hidden"), **kw), weeks=8)
        return M.run_variant(5, w, C.NOCAP, 1, None)

    def test_off_by_default(self):
        self.assertEqual(WORLD.evidence_find, 0.0)
        net = M.run_variant(5, replace(M.world(M.OPUS, "hidden"), weeks=8), C.NOCAP, 1, None)
        self.assertEqual(net.stats["evidence_reversed"], 0)

    def test_found_evidence_reverses_passed_bad_fixes_only(self):
        net = self.run_net(find=1.0)
        rev = [s for s in net.subs.values() if s.reversed]
        self.assertTrue(rev)
        self.assertEqual(net.stats["evidence_reversed"], len(rev))
        self.assertTrue(all(s.verdict and not s.good and s.final is False for s in rev))
        self.assertEqual(net.stats["evidence_wrong"], 0)
        # every passed bad fix some contender failed is reversed; the others are paid
        paid_bad = [s for s in net.subs.values() if s.final and not s.good]
        self.assertTrue(all(all(M.case_of(net, s)[seat] for seat in C.ALL_SEATS) for s in paid_bad))

    def test_wrong_evidence_can_reverse_a_good_fix_when_the_world_says_so(self):
        net = self.run_net(find=0.5, false=1.0)
        self.assertGreater(net.stats["evidence_wrong"], 0)

    def test_an_adr_keeps_the_assumed_judges(self):
        net = self.run_net(find=0.5)
        net.w = replace(net.w, accuracy=1.0)
        adr = SimpleNamespace(sid=7, good=False, tier="constitution")
        v = SimpleNamespace(vid=3, family="anthropic")
        self.assertIs(net.honest_vote(adr, v, 0), False)


class TestAttackers(unittest.TestCase):
    def test_the_rows_are_distinct_and_v3s_rows_come_in_pairs(self):
        rows = C.attacker_rows()
        self.assertEqual(len({r[0] for r in rows}), len(rows))
        self.assertEqual(len({r[0] for r in C.dispute_rows()}), len(C.dispute_rows()))
        self.assertEqual(sum("assumed judges" in r[0] and r[3] != "solver" for r in rows),
                         sum("measured" in r[0] and r[3] not in ("solver", "herd") for r in rows))

    def test_on_measured_keeps_the_actors_world_and_swaps_the_judges(self):
        a = C.on_measured(lambda h: A.Sybil(h), "pbw")(False)
        w = a.world()
        self.assertEqual((w.measured, w.initial_active, w.joins_week), ("pbw", 20, 0.5))
        self.assertEqual(w.measured_seats, M.FOUR)

    def test_the_bad_fix_solver_submits_and_its_twin_does_nothing(self):
        w = replace(M.world(M.OPUS, "hidden"), weeks=6)
        r = A.against_twin(lambda h: C.BadFixSolver(h, w, top=1), [2], p=C.NOCAP, metrics=C._solver_metrics)
        self.assertEqual((r["twin"], r["twin_submitted"]), (0.0, 0))
        self.assertGreater(r["submitted"], 10)
        self.assertEqual(PARAMS.FAMILY_CAP, True)


if __name__ == "__main__":
    unittest.main()
