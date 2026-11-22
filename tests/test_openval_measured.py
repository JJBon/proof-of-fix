"""#236 (pof/sim/openval/measured.py): the open-validator network with proof-of-fix#160's measured judges."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from pof.sim.openval import measured as M
from pof.sim.openval import panels as D
from pof.sim.openval import scores as SC
from pof.sim.openval.params import PARAMS


class TestMatrix(unittest.TestCase):
    def test_the_matrix_holds_the_runs_cases_and_no_text(self):
        t = M.table()
        self.assertEqual((len(t["good"]), len(t["hidden"]), len(t["pbw"])), (50, 100, 78))
        self.assertTrue(all(set(v) == set(M.NAMES) and all(isinstance(x, bool) for x in v.values())
                            for pool in t.values() for v in pool))

    def test_the_rates_are_the_judge_reports(self):
        # reports/judges-v2.md, "Each seat on the clean cases"
        self.assertEqual([round(100 * x) for x in M.rates("anthropic", "hidden")], [18, 6])
        self.assertEqual([round(100 * x) for x in M.rates("openai", "pbw")], [19, 30])
        self.assertEqual(round(100 * M.rates("google", "hidden")[0]), 78)
        self.assertEqual(round(100 * M.balanced("anthropic", "hidden")), 88)


class TestVotes(unittest.TestCase):
    def setUp(self):
        self.w = replace(M.world(M.FOUR, "hidden"), weeks=4)
        self.net = SC.run_mode(3, None, self.w, PARAMS)

    def test_a_family_votes_as_its_seat_did_and_the_same_way_every_time(self):
        subs = [s for s in self.net.subs.values() if s.tier == "issue"][:60]
        self.assertTrue(subs)
        by_family = {}
        for v in self.net.reg.validators.values():
            by_family.setdefault(v.family, []).append(v)
        for s in subs:
            cases = M.table()["good" if s.good else "hidden"]
            case = cases[int(D.u(self.net.seed, M.T_CASE, s.sid) * len(cases))]
            for f, seat in M.FOUR:
                votes = {self.net.honest_vote(s, v, role) for v in by_family[f] for role in (0, 1, 2)}
                self.assertEqual(votes, {case[seat]})

    def test_a_repeated_call_can_differ_when_the_world_says_so(self):
        net = SC.run_mode(3, None, replace(self.w, measured_same=0.5), PARAMS)
        v = next(iter(net.reg.validators.values()))
        subs = [s for s in net.subs.values() if s.tier == "issue"][:80]
        self.assertTrue(any(net.honest_vote(s, v, 0) != net.honest_vote(s, v, 1) for s in subs))

    def test_the_default_world_does_not_read_the_matrix(self):
        self.assertEqual(SC.SCORE_WORLD.measured, "")
        self.assertTrue(PARAMS.FAMILY_CAP)
        self.assertEqual(PARAMS.PASS_RULE, "majority")


class TestSwitches(unittest.TestCase):
    def test_without_the_family_cap_one_family_fills_a_panel(self):
        vs = [SimpleNamespace(vid=i, operator=f"op{i}", host=f"h{i}", tee="none", family="anthropic")
              for i in range(3)]
        self.assertFalse(D.fits(vs[:1], vs[1], 3, PARAMS))
        self.assertTrue(D.fits(vs[:2], vs[2], 3, replace(PARAMS, FAMILY_CAP=False)))

    def test_the_known_answer_rank_seats_the_best_families(self):
        w = M.world(M.SEVEN, "hidden")
        top = M.known_answer_rank(w, top=1)
        self.assertEqual([f for f, _ in M.SEVEN if top(f)], ["anthropic"])
        bar = M.known_answer_rank(M.world(M.SEVEN, "pbw"), bar=0.70)
        self.assertEqual([f for f, _ in M.SEVEN if bar(f)], ["anthropic", "openai", "google"])

    def test_every_judge_must_pass_rejects_more_good_fixes(self):
        w = replace(M.world(M.TOP2, "hidden"), weeks=8)
        nocap = replace(PARAMS, FAMILY_CAP=False)
        maj = M.metrics(SC.run_mode(5, None, w, nocap))
        una = M.metrics(SC.run_mode(5, None, w, replace(nocap, PASS_RULE="unanimous")))
        self.assertGreater(una["good_failed_pct"], maj["good_failed_pct"])
        self.assertLessEqual(una["bad_paid_pct"], maj["bad_paid_pct"])


if __name__ == "__main__":
    unittest.main()
