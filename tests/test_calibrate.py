"""The calibration set and its driver (proof-of-fix#334): every item's protected test fails on its bug and judges its
prepared fix as the driver's data says; main's suite stays green with every bug present; and scripts/calibrate.py
plans, records, resumes, stops at its budget and refuses Sepolia without --yes-spend. No chain, no network."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import calibrate as C  # noqa: E402
import test_calibration as P  # noqa: E402

from calibration import test_visible as V  # noqa: E402


def module(src: str, fixed: bool | None = None):
    m = types.ModuleType("calibration_item")
    exec(compile(src, "<calibration item>", "exec"), m.__dict__)
    if fixed is not None:
        m.FIXED = fixed
    return m


def run(tests, name: str, m) -> unittest.TestResult:
    """Runs class `name` of `tests` (the protected or the visible module) against module `m`."""
    real = tests.item
    tests.item = lambda _name: m
    try:
        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(getattr(tests, name)).run(result)
        return result
    finally:
        tests.item = real


def passed(r: unittest.TestResult) -> bool:
    return r.wasSuccessful() and r.testsRun > 0 and not r.skipped


class Items(unittest.TestCase):
    def setUp(self):
        self.items = C.load_items()

    def test_sixty_items_three_quarters_good(self):
        self.assertEqual(len(self.items), 60)
        self.assertEqual(sum(1 for i in self.items if i.prepared == "good"), 45)
        self.assertEqual(sum(1 for i in self.items if i.prepared == "bad"), 15)
        self.assertEqual(len({i.id for i in self.items}), 60)

    def test_each_item_fails_before_its_fix_and_judges_the_prepared_fix(self):
        for i in self.items:
            with self.subTest(item=i.id):
                name = i.id.upper()
                text = (C.CAL / f"{i.id}.py").read_text(encoding="utf-8")
                fix = module(i.fix)
                self.assertIs(fix.FIXED, True)
                self.assertTrue(passed(run(V, name, fix)), "the prepared fix fails the visible test")
                self.assertEqual(passed(run(P, name, fix)), i.prepared == "good")
                if module(text).FIXED:  # fixed on this branch (a calibration fix merged on the race's main)
                    self.assertTrue(passed(run(P, name, module(text))), "a merged fix fails its protected test")
                    continue
                forced = module(text, fixed=True)
                self.assertFalse(run(P, name, forced).wasSuccessful(), "the protected test passes on the bug")
                self.assertFalse(run(V, name, forced).wasSuccessful(), "the visible test passes on the bug")

    def test_main_stays_green_with_every_bug(self):
        bugs = sum(1 for i in self.items if not module((C.CAL / f"{i.id}.py").read_text(encoding="utf-8")).FIXED)
        for tests in (P, V):
            result = unittest.TestResult()
            unittest.defaultTestLoader.loadTestsFromModule(tests).run(result)
            self.assertTrue(result.wasSuccessful())
            self.assertEqual(len(result.skipped), bugs)

    def test_the_label_is_only_in_the_drivers_data(self):
        for i in self.items:
            with self.subTest(item=i.id):
                for text in (i.title, i.body, i.fix):
                    self.assertIsNone(re.search(r"\b(good|bad|subtly|wrong fix|prepared)\b", text, re.I))
                self.assertIn("calibration issue", i.body)
                self.assertIn(f"calibration/{i.id}.py", i.body)

    def test_the_protected_tests_are_under_the_protected_path(self):
        check = json.loads((ROOT / ".pof" / "check.json").read_text(encoding="utf-8"))
        self.assertIn("tests", [p.rstrip("/") for p in check["protected"]])
        self.assertIn(["python", "-m", "unittest", "discover", "-s", "tests", "-t", "tests"], check["commands"])


# ---------------------------------------------------------------------------------------------------------------------
# The driver, with a fake chain and a fake pofctl


class FakeReader:
    def __init__(self):
        self.checks: dict = {}
        self.scores: dict = {}

    def check(self, s):
        return {"status": 1, "pass": False, "k": 0, "pid": 0, "shadowPid": 0, "held": False, **self.checks.get(s, {})}

    def head(self):
        return "ab" * 20

    def seats(self, pid):
        return ["0x" + "11" * 20] if pid else []

    def shadow_scores(self, spid):
        return self.scores.get(spid, [])

    def validators(self):
        return [{"key": "0x" + "22" * 20, "state": "Candidate", "family": "", "shadowDraws": 4, "shadowReveals": 4,
                 "scored": 4, "agreed": 4, "cooldownUntil": 0}]

    def k_top(self):
        return 3

    def usd_per_call(self, tokens=None):
        return 0.5

    def coins(self):
        return {"registration": 2.5, "fixDeposit": 1.0, "issueStake": 1.0}


class FakeOps:
    def __init__(self):
        self.calls: list = []
        self.n = 0

    def rad_exec(self, role):
        return None

    def pofctl(self, role, *argv):
        self.calls.append((role, argv[:2]))
        if argv[:2] == ("issue", "register"):
            self.n += 1
            return {"issue": self.n, "check": 100 + self.n, "radIssue": f"{self.n:040x}"}
        if argv[:2] == ("issue", "open"):
            return {"bounty": int(argv[3]) + 500}
        if argv[0] == "submit":
            return {"submission": int(argv[2]) + 1000, "salt": "0x" + "00" * 32, "patchCommand": "git push rad x"}
        if argv[0] == "merge":
            return {"merged": True, "head": "cd" * 20}
        return {}

    def commit_fix(self, item, base):
        return "ef" * 20

    def open_patch(self, command):
        return "12" * 20

    def announce(self, role):
        pass


class Driver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = C.Ledger(Path(self.tmp.name) / "ledger.jsonl")
        self.items = C.load_items()
        self.reader, self.ops, self.lines = FakeReader(), FakeOps(), []

    def tearDown(self):
        self.tmp.cleanup()

    def driver(self, items=None, **kw):
        kw.setdefault("max_usd", 1000.0)
        return C.Driver(items or self.items, self.ledger, self.ops, self.reader, say=self.lines.append,
                        sleep=lambda s: None, **kw)

    def registered(self):
        return [r for r, a in self.ops.calls if a == ("issue", "register")]

    def test_plan_counts_checks_and_shadow_verdicts(self):
        lines = C.plan_lines(self.items, 1.5, 2.5, FakeReader().coins(), 60)
        self.assertIn("60 calibration items: 45 prepared fixes good, 15 bad (75 % / 25 %)", lines[0])
        self.assertIn("checks: 120 (60 registration checks, then 60 fixes", lines[1])
        self.assertIn("so 120 from the registrations alone", lines[2])
        self.assertIn("qualifies 6 candidates", lines[2])
        self.assertIn("$90.00 for the registrations, $240.00 with every fix", lines[3])
        self.assertIn("150.00 for every registration", lines[4])

    def test_registers_in_batches_and_resumes_without_repeating(self):
        self.driver(batch=2).step()
        self.assertEqual(len(self.registered()), 2)
        r = self.driver(batch=2).step()  # a new run on the same ledger: a resumed one
        self.assertEqual(len(self.registered()), 4)
        state = self.ledger.items()
        self.assertEqual(sorted(state), ["c01", "c02", "c03", "c04"])
        self.assertEqual([state[x]["check"] for x in ("c01", "c02", "c03", "c04")], [101, 102, 103, 104])
        self.assertEqual(len(r["open"]), 60)

    def test_stops_before_the_budget_is_passed(self):
        d = self.driver(batch=60, max_usd=6.0)  # 4 registration checks at 3 calls of $0.50
        with self.assertRaises(C.Stop) as e:
            d.step()
        self.assertEqual(len(self.registered()), 4)
        self.assertEqual(self.ledger.spent(), 6.0)
        self.assertIn("over --max-usd $6.00", str(e.exception))
        self.assertEqual(self.ledger.events()[-1]["step"], "stopped")
        with self.assertRaises(C.Stop):  # resumed: still nothing more
            self.driver(batch=60, max_usd=6.0).step()
        self.assertEqual(len(self.registered()), 4)

    def test_a_good_fix_passes_and_merges_a_bad_one_fails(self):
        good, bad = [i for i in self.items if i.id in ("c01", "c04")]
        d = self.driver(items=[good, bad])
        d.step()
        self.reader.checks.update({101: {"status": C.HELD, "pass": True, "k": 1, "pid": 7, "shadowPid": 8},
                                   102: {"status": C.HELD, "pass": True, "k": 1, "pid": 9, "shadowPid": 10}})
        self.reader.scores[8] = [{"key": "0x" + "33" * 20, "agreed": True}, {"key": "0x" + "44" * 20, "agreed": True}]
        d.step()
        self.assertEqual(len(self.ledger.items()["c01"]["checkShadows"]), 2)
        self.reader.checks[101]["status"] = self.reader.checks[102]["status"] = C.FINAL
        d.step()  # open, attempt, submit
        st = self.ledger.items()
        self.assertEqual((st["c01"]["bounty"], st["c04"]["bounty"]), (501, 502))
        self.assertEqual((st["c01"]["submission"], st["c04"]["submission"]), (1501, 1502))
        self.assertEqual(self.ledger.spent(), 2 * 1.5 + 2 * 2.5)
        self.reader.checks[1501] = {"status": C.WINDOW, "pass": True, "k": 3, "pid": 11}
        self.reader.checks[1502] = {"status": C.FINAL, "pass": False, "k": 3, "pid": 12}
        d.step()
        st = self.ledger.items()
        self.assertTrue(st["c01"]["asPrepared"] and st["c04"]["asPrepared"])
        self.assertTrue(st["c01"].get("claimed"))
        self.assertFalse(st["c04"].get("claimed"))
        self.reader.checks[1501]["status"] = C.FINAL
        r = d.step()
        self.assertTrue(self.ledger.items()["c01"].get("merged"))
        self.assertEqual(r["open"], [])

    def test_a_failed_registration_check_ends_its_item(self):
        d = self.driver(items=self.items[:1])
        d.step()
        self.reader.checks[101] = {"status": C.FINAL, "pass": False, "k": 3, "pid": 7}
        self.ops.pofctl = lambda role, *argv: {"issue": 1, "bounty": 0}
        r = d.step()
        self.assertTrue(self.ledger.items()["c01"]["rejected"])
        self.assertEqual(r["open"], [])

    def test_a_torn_last_line_is_ignored(self):
        self.ledger.add("c01", "registered", issue=1, check=101, estUsd=1.5)
        with self.ledger.path.open("a", encoding="utf-8") as f:
            f.write('{"item": "c02", "step": "regis')
        self.assertEqual(sorted(self.ledger.items()), ["c01"])
        self.assertEqual(self.ledger.spent(), 1.5)

    def test_pofctl_failures_are_recorded_and_the_pass_goes_on(self):
        def failing(role, *argv):
            raise C.PofctlFailed("pofctl --v3 issue: exit 1: refused")
        self.ops.pofctl = failing
        self.driver(items=self.items[:2]).step()
        st = self.ledger.items()
        self.assertEqual((st["c01"]["errors"], st["c02"]["errors"]), (1, 1))
        self.assertFalse(st["c01"].get("registered"))


class CommandLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = Path(self.tmp.name) / "record.json"
        self.rec.write_text(json.dumps({"race": "0x" + "00" * 20, "block": 1}), encoding="utf-8")
        self.out = []

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, *argv, reader=None):
        def boom():
            raise AssertionError("no chain read before the refusal")
        return C.main([*argv, "--ledger", str(Path(self.tmp.name) / "l.jsonl")],
                      reader_factory=reader or boom, ops_factory=boom, out=self.out.append)

    def test_sepolia_run_is_refused_without_yes_spend(self):
        self.assertEqual(self.main("run", "--target", "sepolia", "--deployment", str(self.rec), "--max-usd", "5"), 2)
        self.assertIn("pass --yes-spend", self.out[-1])

    def test_sepolia_run_needs_an_explicit_budget(self):
        self.assertEqual(self.main("run", "--target", "sepolia", "--deployment", str(self.rec), "--yes-spend"), 2)
        self.assertIn("--max-usd", self.out[-1])

    def test_plan_offline_and_with_prices(self):
        self.assertEqual(self.main("plan"), 0)
        self.assertIn("60 calibration items", self.out[0])
        self.out.clear()
        self.assertEqual(self.main("plan", "--deployment", str(self.rec), reader=FakeReader), 0)
        self.assertIn("$1.50 a registration check, $2.50 a fix", self.out[3])

    def test_no_rpc_url_is_printed(self):
        secret = "https://rpc.example/v3/0123456789abcdef0123"

        class Leaky(FakeReader):
            def validators(self):
                return [{**FakeReader.validators(self)[0], "key": secret}]
        self.assertEqual(self.main("status", "--target", "sepolia", "--deployment", str(self.rec), "--rpc", secret,
                                   reader=Leaky), 0)
        text = "\n".join(self.out)
        self.assertNotIn("0123456789abcdef0123", text)
        self.assertIn("https://rpc.example/…", text)


if __name__ == "__main__":
    unittest.main()
