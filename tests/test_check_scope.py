"""scripts/check_scope.py (proof-of-fix#208): a pull request that touches only documentation no test reads skips the
Python tests; anything else, or anything it can't tell, runs everything."""

import importlib.util
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_scope.py"
spec = importlib.util.spec_from_file_location("check_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class TestClassify(unittest.TestCase):
    def test_specs_adrs_and_markdown_are_docs(self):
        paths = ["openspec/changes/proof-of-fix-186-cycle-pools/design.md",
                 "openspec/changes/proof-of-fix-186-cycle-pools/specs/merit-cycles/spec.md",
                 "docs/adr/0007-records.md", "README.md", "CONSTITUTION.md", "pofctl/README.md",
                 ".claude/skills/x/SKILL.md"]
        self.assertEqual(scope.classify(paths)[0], "docs")

    def test_code_runs_everything(self):
        for p in ("pof/sim/fundertoken.py", "contracts/src/v2/RaceV2.sol", "scripts/check.sh",
                  ".forgejo/workflows/check.yml", "oracle/node_v2.py", "bot/loop.py"):
            with self.subTest(p):
                self.assertEqual(scope.classify(["README.md", p])[0], "full")

    def test_documentation_a_test_reads_runs_everything(self):
        # Each of these is read by a test today: see TESTS_READ.
        for p in ("openspec/config.yaml", "reports/fundertoken-v1.md", "reports/fundertoken-v1.json",
                  "validator-kit/runbook.md", "tests/data/openval-v1-quick-seed1.md", "experiments/zktls/README.md"):
            with self.subTest(p):
                self.assertEqual(scope.classify([p])[0], "full")

    def test_nothing_changed_runs_everything(self):
        self.assertEqual(scope.classify([])[0], "full")

    def test_tests_read_list_matches_the_tests(self):
        """Every documentation path a test reads by name is covered by TESTS_READ (or isn't documentation)."""
        import re
        named = set()
        for t in (ROOT / "tests").glob("test_*.py"):
            if t.name == "test_check_scope.py":  # this file names paths as examples
                continue
            named |= set(re.findall(r"(?:openspec|docs|reports|validator-kit)/[A-Za-z0-9_./-]+\.(?:md|ya?ml|json)",
                                    t.read_text(encoding="utf-8")))
        uncovered = [p for p in named if scope.classify([p])[0] == "docs" and (ROOT / p).is_file()]
        self.assertEqual(uncovered, [], "a test names these documentation files: add them to TESTS_READ")


class TestOnARepository(unittest.TestCase):
    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True)

    def run_scope(self, base):
        out = StringIO()
        cwd = Path.cwd()
        import os
        os.chdir(self.repo)
        try:
            with redirect_stdout(out):
                self.assertEqual(scope.main([base]), 0)
        finally:
            os.chdir(cwd)
        return out.getvalue().splitlines()[-1]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        (self.repo / "README.md").write_text("x\n")
        (self.repo / "code.py").write_text("x = 1\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.git("switch", "-q", "-c", "pr")

    def tearDown(self):
        self.tmp.cleanup()

    def test_docs_only_branch(self):
        (self.repo / "openspec").mkdir()
        (self.repo / "openspec" / "x.md").write_text("spec\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "spec")
        self.assertEqual(self.run_scope("main"), "docs")

    def test_code_branch(self):
        (self.repo / "code.py").write_text("x = 2\n")
        self.git("commit", "-q", "-am", "code")
        self.assertEqual(self.run_scope("main"), "full")

    def test_main_moved_on_with_code_still_docs(self):
        """Only the branch's own changes count, not what main gained since (the merge base)."""
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "a.md").write_text("a\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "doc")
        self.git("switch", "-q", "main")
        (self.repo / "code.py").write_text("x = 3\n")
        self.git("commit", "-q", "-am", "main code")
        self.git("switch", "-q", "pr")
        self.assertEqual(self.run_scope("main"), "docs")

    def test_unknown_base_runs_everything(self):
        self.assertEqual(self.run_scope("no-such-branch"), "full")


if __name__ == "__main__":
    unittest.main()
