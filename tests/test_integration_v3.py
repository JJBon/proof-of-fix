"""The v3 integration suite's own pieces that need no devnet (proof-of-fix#256, #251 task 3.27): the release-candidate
record scripts/release_candidate.py writes after every run and resumes from (--resume), what the deploy script then
accepts, its refusal of minute windows, the moved clock's hold on a seat of a validator run outside the harness
(tests/integration/suite_v3.py, `external_hold`), and the scenario sets' rules (tests/integration/scenarios_v3.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rc = load("release_candidate", ROOT / "scripts" / "release_candidate.py")
ds = load("deploy_sepolia_for_rc", ROOT / "scripts" / "deploy_sepolia.py")
import scenarios_v3  # noqa: E402
import suite_v3  # noqa: E402

SHA = "a" * 40
CODE = {n: "0x" + "cd" * 32 for n in ds.CONTRACTS}
LAUNCH = {"operatorCap": "off", "hostCap": "off", "teeCap": "off", "kTop": 3, "challengeSize": "same"}


def run(result: str = "passed", windows: str = "production") -> dict:
    return {"result": result, "sets": {s: result for s in rc.SETS}, "wallSeconds": 1,
            "numbers": {s: {"windowsKind": windows} for s in rc.SETS}}


class TheRecord(unittest.TestCase):
    def test_three_passing_runs_leave_the_external_items_pending(self):
        r = rc.record(SHA, "v3-rc1", [run()] * 3, CODE, LAUNCH, None, 3)
        self.assertEqual(r["result"], "incomplete")
        self.assertEqual(r["checks"]["integration"]["runs"], ["passed"] * 3)
        self.assertEqual(r["checks"]["productionWindows"], "passed")
        for c in ("sevSnpValidator", "realModelRun", "attestedImages"):
            self.assertEqual(r["checks"][c], "pending")
        self.assertEqual(r["panelRules"], LAUNCH)
        self.assertEqual(r["format"], ds.RC_FORMAT)

    def test_items_recorded_earlier_for_the_same_commit_are_kept(self):
        earlier = {"commit": SHA, "checks": {"sevSnpValidator": "passed", "realModelRun": "passed",
                                             "attestedImages": "passed", "attestedImagesEvidence": "evidence/x"}}
        r = rc.record(SHA, "v3-rc1", [run()] * 3, CODE, LAUNCH, earlier, 3)
        self.assertEqual(r["result"], "passed")
        self.assertEqual(r["checks"]["attestedImagesEvidence"], "evidence/x")

    def test_a_failed_run_fails_the_record(self):
        r = rc.record(SHA, "", [run(), run("failed")], CODE, LAUNCH, None, 3)
        self.assertEqual(r["result"], "failed")
        self.assertEqual(r["checks"]["productionWindows"], "failed")

    def test_fewer_runs_than_asked_are_incomplete_until_the_rest_run(self):
        r = rc.record(SHA, "", [run()], CODE, LAUNCH, None, 3)
        self.assertEqual((r["result"], r["checks"]["productionWindows"]), ("incomplete", "pending"))
        with self.assertRaises(ds.Refused):
            self.deploy_reads(r)

    def test_a_set_on_minute_windows_fails_production_windows(self):
        r = rc.record(SHA, "", [run(windows="minutes")] * 3, CODE, LAUNCH, None, 3)
        self.assertEqual(r["checks"]["productionWindows"], "failed")
        self.assertEqual(r["result"], "failed")

    def deploy_reads(self, record: dict, rules=None) -> dict:
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ds, "contains", return_value=True):
            p = Path(d) / "rc.json"
            p.write_text(json.dumps(record), encoding="utf-8")
            return ds.load_release_candidate(str(p), rules=rules)

    def test_the_deploy_accepts_a_complete_record_with_the_launch_rules(self):
        earlier = {"commit": SHA, "checks": {c: "passed" for c in rc.EXTERNAL_CHECKS}}
        r = rc.record(SHA, "v3-rc1", [run()] * 3, CODE, LAUNCH, earlier, 3)
        self.assertEqual(self.deploy_reads(r, rules=ds.panel_rules("launch", 3, "same"))["commit"], SHA)

    def test_the_deploy_refuses_an_incomplete_record(self):
        r = rc.record(SHA, "v3-rc1", [run()] * 3, CODE, LAUNCH, None, 3)
        with self.assertRaises(ds.Refused):
            self.deploy_reads(r)

    def test_the_rules_come_from_the_launch_set(self):
        numbers = {"launch": {"setup": {"rules": dict(LAUNCH)}}}
        self.assertEqual(rc.rules_of(numbers), LAUNCH)
        self.assertIsNone(rc.rules_of({}))


def runs_of(*results: str, invocation: int = 1) -> list:
    return [dict(run(x), invocation=invocation) for x in results]


class TheResume(unittest.TestCase):
    """The record is written after every run, and --resume goes on from its runs (the owner's PC loses power): only
    for the same commit and bytecode, a failure resetting the streak, every run kept, the deploy reading the last 3.
    The suite's runs are mocked: nothing here starts a devnet."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = Path(self.dir.name) / "rc.json"
        self.logs = Path(self.dir.name) / "logs"
        self.results: list = []  # what the mocked runs return, in order
        self.seen: list = []  # the record as each run starts: what a power cut then would leave
        self.code = dict(CODE)
        for target, kw in (("resolve", {"return_value": SHA}), ("checkout", {"return_value": Path(self.dir.name)}),
                           ("drop", {}), ("hashes", {"side_effect": lambda where: dict(self.code)}),
                           ("one_run", {"side_effect": self.fake_run})):
            patcher = mock.patch.object(rc, target, **kw)
            setattr(self, target, patcher.start())
            self.addCleanup(patcher.stop)
        for patcher in (mock.patch("builtins.print"), mock.patch("sys.stderr"),
                        mock.patch.dict("os.environ", {"DEVNET_V3_WINDOWS": "production"})):
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_run(self, where, i, logs, env):
        self.seen.append(json.loads(self.out.read_text()) if self.out.exists() else None)
        if not self.results:
            raise SystemExit(143)  # the power goes (or SIGTERM) during this run
        r = run(self.results.pop(0))
        r["numbers"]["launch"]["setup"] = {"rules": dict(LAUNCH)}
        return r

    def gate(self, *results: str, resume: bool = False, runs: int = 3) -> int:
        self.results = list(results)
        self.seen = []
        argv = [SHA, "--record", str(self.out), "--tag", "v3-rc1", "--logs", str(self.logs), "--runs", str(runs)]
        return rc.main(argv + (["--resume"] if resume else []))

    def doc(self) -> dict:
        return json.loads(self.out.read_text())

    def put(self, *results: str, **over) -> None:
        r = rc.record(SHA, "v3-rc1", runs_of(*results), CODE, LAUNCH, None, 3)
        r.update(over)
        self.out.write_text(json.dumps(r))

    def test_the_record_is_written_after_every_run_incomplete_while_runs_remain(self):
        self.assertEqual(self.gate("passed", "passed", "passed"), 0)
        self.assertIsNone(self.seen[0])
        self.assertEqual([s["checks"]["integration"]["runs"] for s in self.seen[1:]], [["passed"], ["passed"] * 2])
        for s in self.seen[1:]:
            self.assertEqual((s["result"], s["checks"]["productionWindows"]), ("incomplete", "pending"))
            self.assertEqual(s["commit"], SHA)
            self.assertEqual(s["bytecode"], CODE)
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed"] * 3)
        self.assertEqual(doc["checks"]["productionWindows"], "passed")
        self.assertEqual(doc["result"], "incomplete")  # the AWS items are pending
        self.assertEqual(doc["panelRules"], LAUNCH)
        self.assertEqual([d["invocation"] for d in doc["checks"]["integration"]["details"]], [1, 1, 1])
        self.assertEqual(sorted(p.name for p in self.out.parent.iterdir() if p.is_file()), ["rc.json"])  # no temp

    def test_a_failed_run_is_written_failed_and_stops_the_invocation(self):
        self.assertEqual(self.gate("passed", "failed"), 1)
        self.assertEqual(self.one_run.call_count, 2)
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed", "failed"])
        self.assertEqual((doc["result"], doc["checks"]["productionWindows"]), ("failed", "failed"))

    def test_the_write_is_atomic(self):
        self.out.write_text("{\"old\": true}")
        with mock.patch.object(rc.os, "replace", side_effect=OSError("power cut")), self.assertRaises(OSError):
            rc.write_record(self.out, {"new": True})
        self.assertEqual(json.loads(self.out.read_text()), {"old": True})
        self.assertEqual([p.name for p in self.out.parent.iterdir()], ["rc.json"])
        rc.write_record(self.out, {"new": True})
        self.assertEqual(json.loads(self.out.read_text()), {"new": True})

    def test_resume_with_the_same_commit_and_bytecode_runs_only_what_is_missing(self):
        self.put("passed", "passed")
        self.assertEqual(self.gate("passed", resume=True), 0)
        self.assertEqual(self.one_run.call_count, 1)
        self.assertEqual(self.one_run.call_args.args[1], 3)  # its logs are run-3's, after the record's two
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed"] * 3)
        self.assertEqual([d["invocation"] for d in doc["checks"]["integration"]["details"]], [1, 1, 2])
        self.assertEqual(doc["checks"]["productionWindows"], "passed")
        self.assertEqual(doc["panelRules"], LAUNCH)

    def test_resume_with_the_streak_complete_runs_nothing(self):
        self.put("passed", "passed", "passed")
        self.assertEqual(self.gate(resume=True), 0)
        self.one_run.assert_not_called()
        self.assertEqual(self.doc()["checks"]["integration"]["runs"], ["passed"] * 3)

    def test_resume_refuses_another_commit(self):
        self.put("passed", "passed", commit="c" * 40)
        before = self.out.read_text()
        self.assertEqual(self.gate("passed", resume=True), 2)
        self.one_run.assert_not_called()
        self.assertEqual(self.out.read_text(), before)

    def test_resume_refuses_other_bytecode(self):
        self.put("passed", "passed")
        before = self.out.read_text()
        self.code["Panels"] = "0x" + "ef" * 32  # the same commit built to other code (another solc, a dirty cache)
        with mock.patch("builtins.print") as said:
            self.assertEqual(self.gate("passed", resume=True), 2)
        self.assertIn("Panels", " ".join(str(c.args[0]) for c in said.call_args_list))
        self.one_run.assert_not_called()
        self.drop.assert_called_once()  # the worktree still goes
        self.assertEqual(self.out.read_text(), before)

    def test_resume_refuses_without_a_record(self):
        self.assertEqual(self.gate("passed", resume=True), 2)
        self.one_run.assert_not_called()
        self.checkout.assert_not_called()
        self.assertFalse(self.out.exists())

    def test_a_failure_resets_the_streak_and_stays_in_the_record(self):
        self.put("passed", "passed")
        self.assertEqual(self.gate("failed", resume=True), 1)
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed", "passed", "failed"])
        self.assertEqual(doc["result"], "failed")
        with self.assertRaises(SystemExit):  # the power goes during the third run after the failure
            self.gate("passed", "passed", resume=True)
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed", "passed", "failed", "passed", "passed"])
        self.assertEqual((doc["result"], doc["checks"]["productionWindows"]), ("incomplete", "pending"))
        self.assertEqual(self.gate("passed", resume=True), 0)  # the streak was 2 of 3: one run left
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed", "passed", "failed"] + ["passed"] * 3)
        self.assertEqual([d["invocation"] for d in doc["checks"]["integration"]["details"]], [1, 1, 2, 3, 3, 4])
        self.assertEqual(doc["checks"]["productionWindows"], "passed")

    def test_a_run_off_production_windows_resets_the_streak(self):
        self.put("passed", "passed")
        doc = json.loads(self.out.read_text())
        doc["checks"]["integration"]["details"][1]["windows"]["launch"] = "minutes"
        self.out.write_text(json.dumps(doc))
        self.assertEqual(self.gate("passed", "passed", "passed", resume=True), 0)
        self.assertEqual(self.one_run.call_count, 3)

    def test_a_record_from_before_resume_counts_its_runs(self):
        old = rc.record(SHA, "v3-rc1", runs_of("passed", "passed"), CODE, LAUNCH, None, 2)  # a --runs 2 run
        for d in old["checks"]["integration"]["details"]:
            del d["windows"], d["invocation"]
        self.out.write_text(json.dumps(old))
        self.assertEqual(self.gate("passed", resume=True), 0)
        self.assertEqual(self.one_run.call_count, 1)

    def test_without_resume_the_streak_starts_at_zero_and_earlier_runs_go(self):
        self.put("passed", "passed")
        self.assertEqual(self.gate("passed", "passed", "passed"), 0)
        self.assertEqual(self.one_run.call_count, 3)
        doc = self.doc()
        self.assertEqual(doc["checks"]["integration"]["runs"], ["passed"] * 3)
        self.assertEqual([d["invocation"] for d in doc["checks"]["integration"]["details"]], [1, 1, 1])

    def test_the_aws_items_carry_over_on_resume(self):
        r = rc.record(SHA, "v3-rc1", runs_of("passed", "passed"), CODE, LAUNCH,
                      {"commit": SHA, "checks": {"sevSnpValidator": "passed", "attestedImages": "passed",
                                                 "attestedImagesEvidence": "evidence/x", "realModelRun": "pending"}}, 3)
        self.out.write_text(json.dumps(r))
        self.assertEqual(self.gate("passed", resume=True), 0)
        checks = self.doc()["checks"]
        self.assertEqual([checks[c] for c in ("sevSnpValidator", "attestedImages", "realModelRun")],
                         ["passed", "passed", "pending"])
        self.assertEqual(checks["attestedImagesEvidence"], "evidence/x")

    deploy_reads = TheRecord.deploy_reads

    def test_the_deploy_takes_three_passes_after_an_old_failure_and_nothing_less(self):
        """The deploy (scripts/deploy_sepolia.py) reads the last 3 runs: a failure before them is history, a failure
        among or after them refuses, even in a record hand-edited to say passed."""
        aws = {"commit": SHA, "checks": {c: "passed" for c in rc.EXTERNAL_CHECKS}}
        ok = rc.record(SHA, "v3-rc1", runs_of("passed", "failed", "passed", "passed", "passed"), CODE, LAUNCH, aws, 3)
        self.assertEqual(ok["result"], "passed")
        self.assertEqual(ok["checks"]["integration"]["runs"][1], "failed")  # kept, visible
        self.assertEqual(self.deploy_reads(ok, rules=ds.panel_rules("launch", 3, "same"))["commit"], SHA)
        self.assertTrue(rc.runs_passed(ok))
        for bad in (("failed", "passed", "passed"), ("passed", "passed", "passed", "failed"),
                    ("passed", "passed", "failed", "passed", "passed")):
            with self.subTest(bad):
                r = rc.record(SHA, "v3-rc1", runs_of(*bad), CODE, LAUNCH, aws, 3)
                self.assertNotEqual(r["result"], "passed")
                self.assertFalse(rc.runs_passed(r))
                with self.assertRaises(ds.Refused):
                    self.deploy_reads(r)
                r.update(result="passed")
                r["checks"]["productionWindows"] = "passed"
                with self.assertRaises(ds.Refused) as e:
                    self.deploy_reads(r)
                self.assertIn("3 runs in a row", str(e.exception))

    def test_the_aws_items_on_a_record_still_running_keep_it_incomplete(self):
        r = rc.record(SHA, "v3-rc1", runs_of("passed"), CODE, LAUNCH, None, 3)
        self.assertEqual(rc.result_of(r["checks"], rc.runs_passed(r)), "incomplete")
        r = rc.record(SHA, "v3-rc1", runs_of("passed", "failed"), CODE, LAUNCH, None, 3)
        self.assertEqual(rc.result_of(r["checks"], rc.runs_passed(r)), "failed")


class ProductionWindowsOnly(unittest.TestCase):
    def test_minute_windows_are_refused(self):
        with self.assertRaises(rc.Stop) as e:
            rc.windows_env({"DEVNET_V3_WINDOWS": "minutes"})
        self.assertIn("production windows only", str(e.exception))

    def test_production_its_own_devnet_and_no_rules_from_outside(self):
        env = rc.windows_env({"DEVNET_V3_K_TOP": "3", "PATH": "/bin"})
        self.assertEqual(env["DEVNET_V3_WINDOWS"], "production")
        self.assertEqual((env["POF_INTEGRATION_NAME"], env["POF_INTEGRATION_PORT"]), (rc.NAME, rc.PORT))
        self.assertNotIn("DEVNET_V3_K_TOP", env)
        self.assertEqual(env["PATH"], "/bin")


def seat(**kw) -> dict:
    x = {"pid": 7, "slot": 0, "key": "0xAbC", "sealBy": 100, "revealBy": 200, "allSealed": False, "hasSeal": False,
         "revealed": False, "closed": False}
    x.update(kw)
    return x


class TheClockWaitsForAnOutsideValidator(unittest.TestCase):
    EXT = {"0xabc"}

    def test_an_unsealed_seat_holds_its_seal_deadline(self):
        self.assertEqual(suite_v3.external_hold([seat()], self.EXT, 50), [(7, 0, "seal", 100)])

    def test_a_sealed_seat_holds_the_reveal_once_every_seat_sealed(self):
        self.assertEqual(suite_v3.external_hold([seat(hasSeal=True)], self.EXT, 50), [])
        self.assertEqual(suite_v3.external_hold([seat(hasSeal=True, allSealed=True)], self.EXT, 150),
                         [(7, 0, "reveal", 200)])

    def test_nothing_held_once_acted_missed_closed_or_not_outside(self):
        self.assertEqual(suite_v3.external_hold([seat(hasSeal=True, allSealed=True, revealed=True)], self.EXT, 150), [])
        self.assertEqual(suite_v3.external_hold([seat()], self.EXT, 101), [])  # missed: the panel replaces it
        self.assertEqual(suite_v3.external_hold([seat(closed=True)], self.EXT, 50), [])
        self.assertEqual(suite_v3.external_hold([seat(key="0xdef")], self.EXT, 50), [])


class TheSets(unittest.TestCase):
    def test_the_launch_set_is_the_sepolia_record(self):
        s = scenarios_v3.SETS["launch"]
        self.assertEqual(ds.panel_rules(s["caps"], s["kTop"], s["size"]), LAUNCH)
        self.assertEqual(s["layout"], "one")
        self.assertEqual(s["validators"] + 1, 7)
        self.assertEqual(s["scenarios"].split(), ["u", "w", "v", "x", "e", "p"])

    def test_f_and_g_under_both_challenge_sizes(self):
        sizes = {scenarios_v3.SETS[n]["size"] for n in scenarios_v3.SETS if "f" in scenarios_v3.SETS[n]["scenarios"]}
        self.assertEqual(sizes, {"larger", "same"})
        for n in ("few-larger", "few-same"):
            self.assertEqual(scenarios_v3.SETS[n]["families"], ["fake"])
            self.assertEqual(scenarios_v3.SETS[n]["scenarios"].split(), ["f", "g"])

    def test_every_set_runs_in_the_suite_and_the_release_candidate(self):
        text = (ROOT / "scripts" / "integration-v3.sh").read_text(encoding="utf-8")
        self.assertIn("SETS=(story " + " ".join(scenarios_v3.SETS) + ")", text)
        self.assertEqual(rc.SETS, ("story", *scenarios_v3.SETS))


if __name__ == "__main__":
    unittest.main()
