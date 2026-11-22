"""The v3 integration suite's own pieces that need no devnet (proof-of-fix#256, #251 task 3.27): the release-candidate
record scripts/release_candidate.py writes (and what the deploy script then accepts), its refusal of minute windows,
the moved clock's hold on a seat of a validator run outside the harness (tests/integration/suite_v3.py,
`external_hold`), and the scenario sets' rules (tests/integration/scenarios_v3.py)."""

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

    def test_fewer_runs_than_asked_fail(self):
        self.assertEqual(rc.record(SHA, "", [run()], CODE, LAUNCH, None, 3)["result"], "failed")

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
        self.assertEqual(s["scenarios"].split(), ["u", "w", "v", "x"])

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
