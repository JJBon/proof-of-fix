"""proof-of-fix#160: the pre-registered v2 judge check. The frozen sets (the extension, the passing-but-wrong arm, the
ground truth), the statistics, the plan and its hash, the cost options and the owner's rule, the confirmatory
analysis on hand-written verdicts, and the run's gates. No model is called and nothing reaches the network."""

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path

from pof.judges import dataset as D
from pof.judges import pbw as PBW
from pof.judges import plan as PL
from pof.judges import prereg as PR
from pof.judges import stats as S
from pof.judges.injection import KINDS

ROOT = Path(__file__).resolve().parent.parent
V1 = json.loads((ROOT / "data/judges/manifest.json").read_text(encoding="utf-8"))
MORE = json.loads((ROOT / "data/judges/manifest-more.json").read_text(encoding="utf-8"))
ARM = json.loads((ROOT / "data/judges/manifest-pbw.json").read_text(encoding="utf-8"))
TRUTH = json.loads((ROOT / "data/judges/ground-truth.json").read_text(encoding="utf-8"))
PLAN = json.loads((ROOT / "reports/judges-v2.plan.json").read_text(encoding="utf-8"))
PREREG = (ROOT / "reports/judges-v2.prereg.md").read_text(encoding="utf-8")
REGISTER = (ROOT / "docs/research/hypotheses.md").read_text(encoding="utf-8")


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestExtension(unittest.TestCase):
    def test_fifty_more_pairs_by_v1s_rules(self):
        self.assertEqual(D.check_manifest(MORE), [])
        self.assertEqual(MORE["counts"], {"good": 50, "bad": 50})
        self.assertEqual(MORE["seed"], 160)
        self.assertEqual(MORE["runs"], V1["runs"])

    def test_disjoint_from_v1_and_extends_the_committed_v1(self):
        self.assertFalse({c["instance"] for c in V1["cases"]} & {c["instance"] for c in MORE["cases"]})
        self.assertEqual(MORE["extends"]["sha256"],
                         D.sha256((ROOT / "data/judges/manifest.json").read_text(encoding="utf-8")))

    def test_the_repository_cap_holds_over_the_union(self):
        repos = [c["repo"] for c in V1["cases"] + MORE["cases"] if c["label"] == "bad"]
        self.assertLessEqual(max(repos.count(r) for r in set(repos)), MORE["per_repo_union"])

    def test_select_counts_an_earlier_selection_toward_the_cap(self):
        cands = [D.Candidate(f"r{i % 2}__r-{i}", f"o/r{i % 2}", i % 30, (), ("B",)) for i in range(80)]
        plans = D.select(cands, ("B",), pairs=10, seed=3, per_repo=8, already={"o/r0": 6})
        self.assertLessEqual(sum(p["repo"] == "o/r0" for p in plans), 2)
        self.assertEqual(D.select(cands, ("B",), pairs=10, seed=3), D.select(cands, ("B",), pairs=10, seed=3,
                                                                              already=None))


RQ1 = {"OpenHands": {"a__a-1": {"oracle_pass_model_fail": ["t1"], "difference": "functionality"},
                     "a__a-2": {"oracle_pass_model_fail": ["t2"], "difference": "coding_conventions"}},
       "CodeStory": {"a__a-1": {"oracle_pass_model_fail": ["t1", "t3"], "difference": "functionality"}},
       "LearnByInteract": {}}
RQ34 = [{"tool": "LearnByInteract", "instance_id": "a__a-3", "diff_pattern": "divergent",
         "correctness": "incorrect_partial"},
        {"tool": "OpenHands", "instance_id": "a__a-1", "diff_pattern": "absent", "correctness": "incorrect_regression"},
        {"tool": "OpenHands", "instance_id": "a__a-4", "diff_pattern": "divergent", "correctness": "uncertain"},
        {"tool": "CodeStory", "instance_id": "a__a-5", "diff_pattern": "absent", "correctness": "correct_irrelevant"}]
RESOLVED = {"OpenHands": {"a__a-1", "a__a-2", "a__a-4"}, "CodeStory": {"a__a-1", "a__a-5"},
            "LearnByInteract": {"a__a-3"}}


class TestArm(unittest.TestCase):
    def test_only_functional_failures_and_incorrect_reviews_count(self):
        rows = PBW.candidates(RQ1, RQ34, RESOLVED)
        self.assertEqual({(r["tool"], r["instance"]) for r in rows},
                         {("OpenHands", "a__a-1"), ("CodeStory", "a__a-1"), ("LearnByInteract", "a__a-3")})
        ev = {(r["tool"], r["instance"]): PBW.evidence(r) for r in rows}
        self.assertEqual(ev[("OpenHands", "a__a-1")], "both")
        self.assertEqual(ev[("CodeStory", "a__a-1")], "full-tests")
        self.assertEqual(ev[("LearnByInteract", "a__a-3")], "manual")

    def test_a_patch_the_hidden_tests_rejected_is_refused(self):
        with self.assertRaises(ValueError):
            PBW.candidates(RQ1, RQ34, {"OpenHands": {"a__a-1"}, "CodeStory": set(), "LearnByInteract": {"a__a-3"}})

    def test_one_primary_per_issue_strongest_evidence_first(self):
        rows = PBW.candidates(RQ1, RQ34, RESOLVED)
        chosen = PBW.primary(rows)
        self.assertEqual(chosen, {("OpenHands", "a__a-1"), ("LearnByInteract", "a__a-3")})
        self.assertEqual(chosen, PBW.primary(list(reversed(rows))))

    def test_the_committed_arm(self):
        self.assertEqual(PBW.check_pbw_manifest(ARM), [])
        self.assertGreaterEqual(ARM["counts"]["issues"], 40)
        self.assertEqual(ARM["counts"], {"cases": 79, "issues": 57,
                                         "by_evidence": {"both": 11, "full-tests": 57, "manual": 11}})
        self.assertEqual(ARM["label_source"]["package"]["licence"], "CC-BY-4.0")
        for c in ARM["cases"]:
            self.assertEqual(c["hidden_tests"], "pass")
            self.assertNotIn("issue", c)
            self.assertNotIn("author", c)

    def test_broken_arm_manifests_are_caught(self):
        broken = json.loads(json.dumps(ARM))
        broken["cases"][0]["label"] = "good"
        broken["cases"][1]["primary"] = not broken["cases"][1]["primary"]
        errors = PBW.check_pbw_manifest(broken)
        self.assertTrue(any("label" in e for e in errors))
        self.assertTrue(any("primary" in e for e in errors))

    def test_no_person_in_the_new_data(self):
        for blob in (json.dumps(MORE), json.dumps(ARM), json.dumps(TRUTH)):
            self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", blob))


class TestGroundTruth(unittest.TestCase):
    def test_test_names_ignore_parser_formatting(self):
        self.assertEqual(PBW.test_name("test_x (m.C.test_x)"), PBW.test_name("test_x (m.C)"))
        self.assertTrue(PBW.reparse_drops(["test_y (m.C)"], {"FAIL_TO_PASS": ["test_x (m.C.test_x)"]}))
        self.assertFalse(PBW.reparse_drops(["test_x (m.C)"], {"FAIL_TO_PASS": ["test_x (m.C.test_x)"]}))
        self.assertIsNone(PBW.reparse_drops(["t"], None))

    def test_patch_level_verdicts_only_for_patches_patchdiff_judged(self):
        case = {"id": "a__a-1:bad", "instance": "a__a-1", "label": "bad", "source": "x", "patch_sha256": "h1"}
        hashes = {"OpenHands:a__a-1": "h1"}
        judged = PBW.coverage([case], hashes, RESOLVED, RQ1, {}, RQ34, set(), {}, {})[0]
        self.assertEqual(judged["patch_level"]["full_tests"], "fail")
        self.assertEqual(judged["review"], [])  # bad by hidden tests and by the full tests: they agree
        unjudged = PBW.coverage([case], hashes, {"OpenHands": set()}, RQ1, {}, RQ34, set(), {}, {})[0]
        self.assertIsNone(unjudged["patch_level"])

    def test_review_reasons(self):
        good = {"id": "a__a-1:good", "instance": "a__a-1", "label": "good", "source": "run", "patch_sha256": "g"}
        gold = dict(good, id="a__a-1:gold", source="gold")
        rows = PBW.coverage([good, gold], {}, RESOLVED, RQ1, {}, RQ34, set(), {}, {})
        self.assertIn("agent-written good fix", rows[0]["review"][0])
        self.assertEqual(rows[1]["review"], [])

    def test_the_committed_ground_truth(self):
        for name in ("manifest.json", "manifest-more.json"):
            self.assertEqual(TRUTH[name]["summary"]["cases"], 100)
            ids = {r["id"] for r in TRUTH[name]["cases"]}
            manifest = V1 if name == "manifest.json" else MORE
            self.assertEqual(ids, {c["id"] for c in manifest["cases"]})


class TestStats(unittest.TestCase):
    def test_binomial_intervals(self):
        lo, hi = S.clopper_pearson(5, 10)
        self.assertAlmostEqual(lo, 0.1871, places=3)
        self.assertAlmostEqual(hi, 0.8129, places=3)
        self.assertEqual(S.clopper_pearson(0, 10)[0], 0.0)
        lo, hi = S.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)

    def test_the_doubled_one_sided_p_matches_the_interval(self):
        for k in range(30, 50):
            lo = S.clopper_pearson(k, 56)[0]
            p = 2 * S.binom_greater(k, 56, 0.5)
            self.assertEqual(lo >= 0.5, p <= 0.05, k)

    def test_mcnemar(self):
        self.assertAlmostEqual(S.mcnemar_exact(0, 5), 0.0625)
        self.assertAlmostEqual(S.mcnemar_exact(2, 10), 0.0386, places=4)
        self.assertEqual(S.mcnemar_exact(0, 0), 1.0)

    def test_newcombe_and_its_inversion(self):
        d, lo, hi = S.newcombe_paired(5, 0, 0, 45)
        self.assertEqual(d, 0.0)
        self.assertLess(lo, 0)
        self.assertGreater(hi, 0)
        for cells in ((5, 6, 4, 85), (5, 2, 1, 42), (10, 8, 1, 31)):
            upper = S.newcombe_paired(*cells)[2]
            self.assertEqual(upper < 0.10, S.upper_bound_p(*cells, 0.10) <= 0.05, cells)

    def test_phi_and_holm(self):
        self.assertAlmostEqual(S.phi([True, False, True, False], [True, False, True, False]), 1.0)
        self.assertIsNone(S.phi([True, True], [True, False]))
        h = S.holm({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertTrue(h["a"]["reject"])
        self.assertFalse(h["c"]["reject"])
        self.assertFalse(h["b"]["reject"])
        self.assertAlmostEqual(h["a"]["adjusted"], 0.03)

    def test_bootstrap_is_seeded(self):
        stat = lambda idx: sum(idx) / len(idx) - 4.5  # noqa: E731
        self.assertEqual(S.bootstrap(10, stat, 200, seed=1), S.bootstrap(10, stat, 200, seed=1))

    def test_tost(self):
        self.assertLess(S.tost(0.0, 0.03, 0.10), 0.05)
        self.assertGreater(S.tost(0.0, 0.08, 0.10), 0.05)
        self.assertGreater(S.tost(0.12, 0.01, 0.10), 0.5)
        self.assertEqual(S.tost(None, None, 0.10), 1.0)
        for est, se in ((0.02, 0.04), (0.05, 0.03), (-0.03, 0.05)):  # p <= 0.05 iff the 90 % interval is inside
            inside = est - 1.6449 * se > -0.10 and est + 1.6449 * se < 0.10
            self.assertEqual(S.tost(est, se, 0.10) <= 0.05, inside, (est, se))
        self.assertAlmostEqual(S.power_tost(0.03, 0.10), 0.9, delta=0.1)
        self.assertEqual(S.power_tost(0.05, 0.10, alpha=0.01), 0.0)

    def test_cmh_finds_nothing_in_identical_strata(self):
        r = S.cmh([(5, 15, 20, 60), (5, 15, 20, 60)])
        self.assertAlmostEqual(r["rd"], 0.0)
        self.assertGreater(r["p"], 0.5)
        self.assertLess(S.cmh([(15, 5, 10, 70), (14, 6, 9, 71)])["p"], 0.001)


class TestPlan(unittest.TestCase):
    def test_the_hash_recomputes(self):
        body = {k: v for k, v in PLAN.items() if k != "hash"}
        self.assertEqual(PLAN["hash"], D.sha256(json.dumps(body, sort_keys=True))[:16])

    def test_the_plan_matches_the_frozen_data_and_the_code(self):
        for f, h in PLAN["data"].items():
            self.assertEqual(h, D.sha256((ROOT / f).read_text(encoding="utf-8")), f)
        self.assertEqual(PLAN["analysis"], PR.source_hash(*PR.ANALYSIS_SOURCES),
                         "the analysis or the prompt changed: rerun scripts/judge_run.py plan-v2")
        ids = {c["id"] for m in (V1, MORE, ARM) for c in m["cases"]}
        ids |= {f"{c['id']}+{k}" for m in (V1, MORE) for c in m["cases"] if c["label"] == "bad" for k in KINDS}
        self.assertEqual(set(PLAN["cases"]), ids)

    def test_the_options_and_the_choice_recompute(self):
        self.assertEqual(PR.options(PLAN["cases"]), PLAN["options"])
        self.assertEqual((PLAN["design"]["design"], PLAN["design"]["h3"]), PR.DESIGN)  # the owner's fixed design
        self.assertGreater(PLAN["design"]["estimate"], PR.BUDGET)  # over the budget on paper: --max-usd stops it
        self.assertEqual(PLAN["budget"]["max_usd"], PR.BUDGET)
        self.assertEqual(len(PR.design_calls(PLAN["design"]["design"], PLAN["cases"],
                                             PR.H3_ADDS[PLAN["design"]["h3"]])), PLAN["calls"])

    def test_the_owners_rule(self):
        rows = [{"design": "A", "h3": "none", "bad_fixes": 50, "calls": 10, "estimate": 60.0},
                {"design": "A", "h3": "2 seats", "bad_fixes": 50, "calls": 12, "estimate": 62.0},
                {"design": "B", "h3": "none", "bad_fixes": 100, "calls": 20, "estimate": 95.0},
                {"design": "B", "h3": "2 seats", "bad_fixes": 100, "calls": 22, "estimate": 101.0}]
        self.assertEqual(PR.choose(rows)["design"], "B")  # more bad fixes before more seats
        self.assertEqual(PR.choose(rows)["h3"], "none")
        self.assertEqual(PR.choose(rows, budget=70)["h3"], "2 seats")
        with self.assertRaises(ValueError):
            PR.choose(rows, budget=10)

    def test_the_cost_model(self):
        case = {"input": 1_000_000, "size": "large"}
        m = PR.seat_price("anthropic")
        self.assertAlmostEqual(PR.call_cost("anthropic", case), m.input + PL.OUTPUT["large"] * m.output / 1e6)
        self.assertEqual(PR.limit("openai", "large"), PL.OUTPUT["large"])
        self.assertEqual(PR.limit("anthropic", "large"), PL.OUTPUT["large"])  # sized since the stopped run
        self.assertEqual(PR.limit("mistral", "large"), PR.FLAT_LIMIT)
        self.assertGreater(PR.ceiling([("anthropic", "c")], {"c": case}), PR.calls_cost([("anthropic", "c")],
                                                                                     {"c": case}))

    def test_gemini_asks_for_low_reasoning_effort_and_no_other_seat_does(self):
        JR = load_script("judge_run")
        sent = {}

        class Gateway:
            def call(self, seat, path, body):
                sent[seat.model] = json.loads(body)
                return "{}", {"input_tokens": 1, "output_tokens": 1}

        seats = PR.all_seats()
        answer = JR.answerer_v2(Gateway(), JR.Limits(10**9, 10**6), seats)
        case = {"id": "x:bad", "instance": "x", "label": "bad", "size": "small", "issue": "i", "commit": "c",
                "diff": "d", "context": [], "repo": "r/r"}
        for seat in ("google", "openai", "google-gemma"):
            answer(seat, case)
        self.assertEqual(sent[seats["google"].model]["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", sent[seats["openai"].model])
        self.assertNotIn("reasoning_effort", sent[seats["google-gemma"].model])
        self.assertEqual(PLAN["request_extra"], PR.REQUEST_EXTRA)

    def test_the_oversized_case_is_excluded_by_its_size_alone(self):
        self.assertEqual(list(PLAN["excluded"]), ["sphinx-doc__sphinx-9230:pbw:OpenHands"])
        for i, c in PLAN["cases"].items():
            self.assertEqual("excluded" in c, c["bytes"] > PR.MAX_REQUEST_BYTES, i)

    def test_h3_seats_judge_every_clean_case_the_seven_judge(self):
        calls = PR.design_calls(PLAN["design"]["design"], PLAN["cases"], tuple(PR.H3_SEATS))
        seven = {i for s, i in calls if s in PL.SEATS and PLAN["cases"][i]["arm"] in PR.CLEAN_ARMS}
        for seat in PR.H3_SEATS:
            self.assertEqual({i for s, i in calls if s == seat}, seven)
        self.assertEqual({PR.H3_SEATS[s].family for s in PR.H3_SEATS}, {"google", "openai"})

    def test_every_seat_has_a_price_and_a_limit_within_the_gateways(self):
        for s in PLAN["seats"]:
            self.assertGreater(PR.seat_price(s).output, 0)
            self.assertLessEqual(max(PLAN["limits_by_seat"][s].values()),
                                 PLAN["budget"]["gateway"]["max_tokens_per_request"])


class TestPreregistration(unittest.TestCase):
    def test_the_document_states_the_hash_and_the_design(self):
        self.assertIn(f"**Plan <!-- gen:hash -->`{PLAN['hash']}`<!-- /gen:hash -->**", PREREG.split("\n## ")[0])
        self.assertIn(f"POF_JUDGE_RUN_APPROVED={PLAN['hash']}", PREREG)
        self.assertIn(f"${PLAN['design']['estimate']:.2f}", PREREG)

    def test_the_documents_tables_recompute_from_the_plan(self):
        self.assertEqual(PR.render(PREREG, PLAN), PREREG, "rerun scripts/judge_run.py plan-v2")

    def test_thresholds_are_the_registers_verbatim(self):
        for h, spec in PR.HYPOTHESES.items():
            row = next(line for line in REGISTER.splitlines() if line.startswith(f"| {h} |"))
            self.assertIn(spec["threshold"], row, h)
            self.assertIn(spec["measure"], row, h)
            self.assertIn(spec["threshold"], PREREG, h)


def rec(case, seat, solves, family=None):
    fam = family or PR.all_seats(tuple(PR.H3_SEATS)).get(seat, PL.Seat(seat, "", "chat")).family
    verdict = {"error": "not JSON"} if solves is None else {"solves": solves}
    return {"case": case, "seat": seat, "family": fam, "verdict": verdict}


class TestAnalysis(unittest.TestCase):
    def cases(self):
        c = {}
        for i in range(10):
            c[f"p{i}:pbw"] = {"arm": "pbw", "label": "bad", "primary": True}
            c[f"b{i}:bad"] = {"arm": "v1", "label": "bad", "solver_family": "anthropic" if i < 5 else "openai"}
            c[f"b{i}:good"] = {"arm": "v1", "label": "good", "solver_family": "human"}
            for k in KINDS:
                c[f"b{i}:bad+{k}"] = {"arm": "v1-inj", "label": "bad"}
        return c

    def records(self, panel_catches=8, inj_flips=1):
        rows = []
        for i in range(10):
            for s in PL.SEATS:
                rows.append(rec(f"p{i}:pbw", s, i >= panel_catches))
                rows.append(rec(f"b{i}:bad", s, s == "nvidia" or (s in PR.PANEL and i == 0)))
                rows.append(rec(f"b{i}:good", s, True))
                for k in KINDS:
                    rows.append(rec(f"b{i}:bad+{k}", s, (i < inj_flips) or s == "nvidia"))
            for s in PR.H3_SEATS:
                rows.append(rec(f"p{i}:pbw", s, i >= panel_catches))
                rows.append(rec(f"b{i}:bad", s, False))
                rows.append(rec(f"b{i}:good", s, True))
        return rows

    def test_h1_counts_the_panels_fails_on_primary_cases(self):
        r = PR.evaluate(self.records(), self.cases(), resamples=50)
        self.assertEqual((r["H1"]["caught"], r["H1"]["n"]), (8, 10))
        self.assertAlmostEqual(r["H1"]["low"], S.clopper_pearson(8, 10)[0])

    def test_h2_against_the_best_family(self):
        r = PR.evaluate(self.records(), self.cases(), resamples=50)
        self.assertEqual(r["H2"]["panel_false_passes"], 1)
        self.assertIn(r["H2"]["best"], ("deepseek", "mistral", "qwen"))
        self.assertEqual(r["H2"]["p"], 1.0)  # the panel has more false passes than the best seat: no support

    def test_h4_pairs_injected_with_clean(self):
        r = PR.evaluate(self.records(inj_flips=1), self.cases(), resamples=50)
        for k in KINDS:
            self.assertEqual(r["H4"]["kinds"][k]["n"], 10)
            self.assertAlmostEqual(r["H4"]["kinds"][k]["difference"], 0.0)

    def test_invalid_verdicts_under_both_rules(self):
        rows = [r if not (r["case"].startswith("p") and r["seat"] in PR.PANEL) else dict(r, verdict={"error": "x"})
                for r in self.records()]
        strict = PR.evaluate(rows, self.cases(), invalid_passes=False, resamples=50)
        lenient = PR.evaluate(rows, self.cases(), invalid_passes=True, resamples=50)
        self.assertEqual(strict["H1"]["caught"], 10)
        self.assertEqual(lenient["H1"]["caught"], 0)
        status = PR.decisions(strict, lenient)
        self.assertEqual(status["H1"], "refuted")

    def test_h9_strata_by_solver_family_and_its_equivalence_test(self):
        r = PR.evaluate(self.records(), self.cases(), resamples=50)
        self.assertEqual(r["H9"]["strata"]["anthropic"], (1, 4, 0, 5))
        self.assertEqual(set(r["holm"]), {"H1", "H2", "H3", "H4", "H9"})
        self.assertEqual(r["H9"]["margin"], 0.10)
        self.assertAlmostEqual(r["H9"]["p"], S.tost(r["H9"]["rd"], r["H9"]["se"], 0.10))

    def test_h4_is_exploratory_whatever_it_shows(self):
        r = PR.evaluate(self.records(), self.cases(), resamples=50)
        status = PR.decisions(r, r)
        self.assertEqual(status["H4"], "exploratory")
        self.assertEqual(list(status), ["H1", "H2", "H3", "H4", "H9"])


class TestRunV2(unittest.TestCase):
    def setUp(self):
        self.run = load_script("judge_run")

    def test_calls_follow_the_stages(self):
        calls = self.run.v2_calls(PLAN)
        stages = [st for st, _, _ in calls]
        self.assertEqual(stages, sorted(stages))
        self.assertEqual(len(calls), PLAN["calls"])
        h3 = [st for st, s, _ in calls if s in PR.H3_SEATS]
        more = [st for st, s, i in calls if PLAN["cases"][i]["arm"] == "more" and s in PL.SEATS]
        self.assertGreater(min(h3), max(more))  # more bad fixes before more seats

    def test_report_needs_final(self):
        import argparse
        with self.assertRaises(SystemExit):
            self.run.cmd_report_v2(argparse.Namespace(final=False))

    def test_judging_is_resumable_and_records_seat_and_family(self):
        cases = {"x__x-1:bad": {"id": "x__x-1:bad", "instance": "x__x-1", "label": "bad"}}
        calls = [(1, "openai-oss", "x__x-1:bad"), (1, "anthropic", "x__x-1:bad")]
        seen = []

        def answer(seat, case):
            seen.append(seat)
            return '{"solves": false, "probability": 0.1, "evidence": [{"file": "f", "line": 1}]}', {}, "m"

        with tempfile.TemporaryDirectory() as d:
            self.run.judge_v2(Path(d), calls, cases, answer)
            self.run.judge_v2(Path(d), calls, cases, answer)
            rows = self.run.load_verdicts(Path(d))
        self.assertEqual(seen, ["openai-oss", "anthropic"])
        self.assertEqual({(r["seat"], r["family"]) for r in rows}, {("openai-oss", "openai"), ("anthropic", "anthropic")})

    def test_the_smoke_case_is_not_a_study_case(self):
        self.assertNotIn(PR.SMOKE["id"], PLAN["cases"])
        self.assertTrue(PR.SMOKE["instance"].startswith("smoke__"))


if __name__ == "__main__":
    unittest.main()
