"""The repository's own test command (proof-of-fix#166 item 3): `.pof/check.json` read at the pull request's base by
the node itself, the acceptance test always run after it, never through a shell, and a fix that can't change its own
check. The parser and the runner here; `Fetcher.file_at` against local bare repositories; the node end to end with
real git and a recording runner; and the runner in the real sandbox where Docker is ready (test_sandbox's rule)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from oracle import checkconfig, fetch, v2  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.sandbox import COMMAND, run_tests  # noqa: E402
from test_fetch import FetchCase, git, make_repo  # noqa: E402
from test_node_evidence import FIXED, Case  # noqa: E402
from test_sandbox import docker_ready  # noqa: E402

HAS_GIT = shutil.which("git") is not None
PROJECT = ["python", "-m", "unittest", "discover", "-s", "bot/sample", "-t", "bot/sample", "-q"]
CONFIG = json.dumps({"commands": [PROJECT]})


def commands_of(argv) -> list:
    """The commands a sandbox argv runs through the runner (the runner's JSON argument), or [] for a plain command."""
    if checkconfig.RUNNER not in argv:
        return []
    return json.loads(argv[argv.index(checkconfig.RUNNER) + 1])


class Parse(unittest.TestCase):
    def test_a_valid_file(self):
        self.assertEqual(checkconfig.parse(CONFIG.encode()), (tuple(PROJECT),))

    def test_what_isnt_valid_and_says_why_without_the_content(self):
        cases = {
            b"\xff\xfe": "isn't JSON",
            b"not json": "isn't JSON",
            b"[]": "one key",
            json.dumps({"commands": [PROJECT], "image": "x"}).encode(): "one key",
            json.dumps({"commands": []}).encode(): "list of 1 to",
            json.dumps({"commands": [PROJECT] * 9}).encode(): "list of 1 to",
            json.dumps({"commands": "python -m unittest"}).encode(): "list of 1 to",
            json.dumps({"commands": [[]]}).encode(): "command 1 must be",
            json.dumps({"commands": [["python", ""]]}).encode(): "command 1 has an argument",
            json.dumps({"commands": [PROJECT, ["python", 3]]}).encode(): "command 2 has an argument",
            json.dumps({"commands": [["python", "a\0b"]]}).encode(): "command 1 has an argument",
            json.dumps({"commands": [["x" * 1025]]}).encode(): "command 1 has an argument",
            json.dumps({"commands": [["a"] * 65]}).encode(): "command 1 must be",
            b" " * 8193: "larger than",
        }
        for data, why in cases.items():
            with self.assertRaises(checkconfig.Invalid, msg=data[:40]) as e:
                checkconfig.parse(data)
            self.assertIn(why, str(e.exception))
            self.assertNotIn("a\0b", str(e.exception))


class TheCommand(unittest.TestCase):
    def test_no_file_is_the_sandbox_s_own_command(self):
        self.assertEqual(checkconfig.command(), COMMAND)
        self.assertEqual(checkconfig.command(()), COMMAND)

    def test_the_repository_s_commands_then_the_acceptance_test(self):
        argv = checkconfig.command((tuple(PROJECT),))
        self.assertEqual(argv[:3], ("python", "-c", checkconfig.RUNNER))
        self.assertEqual(commands_of(argv), [PROJECT, list(COMMAND)])

    def test_the_runner_stops_at_the_first_failure_and_uses_no_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            py = sys.executable
            steps = [[py, "-c", "open('one', 'w').write('1')"],
                     [py, "-c", "import sys; sys.exit(3)"],
                     [py, "-c", "open('three', 'w').write('3')"],
                     ["echo", "$(touch shell)", ";", "touch", "shell"]]
            out = subprocess.run([py, "-c", checkconfig.RUNNER, json.dumps(steps)], cwd=tmp, capture_output=True,
                                 text=True)
            self.assertEqual(out.returncode, 3)
            self.assertTrue((Path(tmp) / "one").exists())
            self.assertFalse((Path(tmp) / "three").exists())
            out = subprocess.run([py, "-c", checkconfig.RUNNER, json.dumps(steps[:1] + steps[3:])], cwd=tmp,
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0)
            self.assertFalse((Path(tmp) / "shell").exists())  # echoed, not run: no shell
            self.assertIn("$ echo $(touch shell)", out.stdout)


@unittest.skipUnless(HAS_GIT, "git isn't installed")
class FileAt(FetchCase):
    def _fetcher(self, url):
        return fetch.Fetcher(url, log=self.logs)

    def test_reads_the_file_at_that_commit(self):
        url, head, first = make_repo(self.tmp, {"README": "x"})
        work = self.tmp / "work"
        (work / ".pof").mkdir()
        (work / ".pof" / "check.json").write_text(CONFIG)
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "config")
        sha = git(work, "rev-parse", "HEAD")
        git(work, "push", "-q", str(self.tmp / "bare.git"), "HEAD:refs/heads/config")
        f = self._fetcher(url)
        self.assertEqual(f.file_at(self.root, sha, ".pof/check.json", 8192), fetch.Blob(CONFIG.encode()))
        self.assertEqual(f.file_at(self.root, head, ".pof/check.json", 8192), fetch.Blob())  # not there: no file
        self.assertEqual(list(self.root.iterdir()), [])  # nothing left behind

    def test_kept_per_commit(self):
        url, head, _ = make_repo(self.tmp, {"x.json": "{}"})
        f = self._fetcher(url)
        self.assertEqual(f.file_at(self.root, head, "x.json", 100).data, b"{}")
        shutil.rmtree(self.tmp / "bare.git")  # the host is gone; a commit's content can't change anyway
        self.assertEqual(f.file_at(self.root, head, "x.json", 100).data, b"{}")

    def test_only_a_regular_file_within_the_limit(self):
        url, head, _ = make_repo(self.tmp, {"big.json": "x" * 200})
        work = self.tmp / "work"
        (work / "link.json").symlink_to("big.json")
        (work / "dir").mkdir()
        (work / "dir" / "inner").write_text("y")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "link")
        linked = git(work, "rev-parse", "HEAD")
        git(work, "push", "-q", str(self.tmp / "bare.git"), "HEAD:refs/heads/link")
        f = self._fetcher(url)
        self.assertIn("larger than 100 bytes", f.file_at(self.root, head, "big.json", 100).refusal)
        self.assertIn("isn't a regular file", f.file_at(self.root, linked, "dir", 100).refusal)
        self.assertIn("isn't a regular file", f.file_at(self.root, linked, "link.json", 1000).refusal)

    def test_a_commit_the_host_doesnt_have_is_tried_again_later(self):
        url, _, _ = make_repo(self.tmp, {"x": "1"})
        f = self._fetcher(url)
        self.assertIsNone(f.file_at(self.root, "1" * 40, ".pof/check.json", 100))
        self.assertTrue(any(".pof/check.json at 111111111111" in m for m in self.logs), self.logs)
        self.assertIsNone(f.file_at(self.root, "1" * 40, ".pof/check.json", 100))  # not every pass: after retry_s
        self.assertEqual(len(self.logs), 1)

    def test_no_base(self):
        url, _, _ = make_repo(self.tmp, {"x": "1"})
        self.assertIn("no base commit", self._fetcher(url).file_at(self.root, "", ".pof/check.json", 100).refusal)


class Recording:
    def __init__(self, code=0):
        self.argvs, self.code = [], code

    def __call__(self, argv):
        self.argvs.append(argv)
        return self.code, "ok", ""


class TheNode(Case):
    """End to end in the node: what the sandbox is asked to run, from which commit."""

    def _run(self, files_at_base: dict, fix_files: dict, judge=None):
        base = self.up.commit(files_at_base, "the base, with the repository's settings") if files_at_base else ""
        sha = self.up.commit(fix_files, "fix", parent=base)
        host = self._host(sha, self._pull(sha, base=base or None))
        _, node = self._node(sha, host, judge)
        node.runner = rec = Recording()
        c = self._judge(node)
        return c, rec

    def test_the_repository_s_tests_then_the_acceptance_test(self):
        c, rec = self._run({".pof/check.json": CONFIG}, {"stats.py": FIXED})
        self.assertEqual(c.outcome, v2.PASS)
        self.assertEqual(commands_of(rec.argvs[-1]), [PROJECT, list(COMMAND)])

    def test_a_fix_can_t_weaken_its_own_check(self):
        weak = json.dumps({"commands": [["true"]]})
        c, rec = self._run({".pof/check.json": CONFIG}, {"stats.py": FIXED, ".pof/check.json": weak})
        self.assertEqual(commands_of(rec.argvs[-1]), [PROJECT, list(COMMAND)])  # the base's, not the fix's

    def test_without_the_file_nothing_changes(self):
        c, rec = self._run({}, {"stats.py": FIXED})
        self.assertEqual(c.outcome, v2.PASS)
        self.assertEqual(tuple(rec.argvs[-1][-len(COMMAND):]), COMMAND)
        self.assertEqual(commands_of(rec.argvs[-1]), [])

    def test_an_invalid_file_fails_closed_with_no_model_call(self):
        c, rec = self._run({".pof/check.json": "{\"commands\": \"make test\"}"}, {"stats.py": FIXED})
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertEqual(self.model.sent, [])
        self.assertTrue(any("is invalid" in m for m in self.logs), self.logs)

    def test_a_base_it_can_t_fetch_gives_no_verdict(self):
        sha = self.up.commit({"stats.py": FIXED}, "fix")
        host = self._host(sha, self._pull(sha, issue=0, base="2" * 40))
        _, node = self._node(sha, host, FakeJudge())  # the fake judge fetches no diff: only the test command
        node.runner = Recording()
        for _ in range(4):
            node.tick(0)
        self.assertEqual(node.checks[1].outcome, 0)
        self.assertTrue(any("no .pof/check.json from the base 222222222222" in m for m in self.logs), self.logs)


DOCKER_SKIP = docker_ready()


@unittest.skipIf(DOCKER_SKIP, DOCKER_SKIP)
class InTheSandbox(unittest.TestCase):
    """The runner in the real sandbox: a repository's tests in a folder that isn't a package, then the acceptance
    test at the root, as pof-sandbox lays them out."""

    def setUp(self):
        self.src = Path(tempfile.mkdtemp(prefix="pof-checkconfig-"))
        self.src.chmod(0o755)  # the sandbox has no capabilities: it reads only what everyone may (test_sandbox does too)
        (self.src / "bot" / "sample").mkdir(parents=True)
        (self.src / "bot" / "sample" / "stats.py").write_text("def mean(xs):\n    return sum(xs) / len(xs)\n")
        self.write_project_test("self.assertEqual(mean([1, 2, 3]), 2)")
        self.command = checkconfig.command((tuple(PROJECT),))

    def tearDown(self):
        shutil.rmtree(self.src)

    def write_project_test(self, check):
        (self.src / "bot" / "sample" / "test_stats.py").write_text(
            f"import unittest\nfrom stats import mean\n\nclass T(unittest.TestCase):\n    def test(self):\n"
            f"        {check}\n")

    def accept(self, ok=True):
        (self.src / "test_issue.py").write_text(
            "import unittest\n\nclass A(unittest.TestCase):\n    def test(self):\n"
            f"        self.assertTrue({ok})\n")

    def test_both_pass(self):
        self.accept()
        self.assertEqual(run_tests(self.src, command=self.command).exit_code, 0)

    def test_the_repository_s_failing_test_fails_the_check(self):
        self.accept()
        self.write_project_test("self.assertEqual(mean([1, 2, 3]), 99)")
        self.assertNotEqual(run_tests(self.src, command=self.command).exit_code, 0)

    def test_a_failing_or_missing_acceptance_test_fails_the_check(self):
        self.accept(False)
        self.assertNotEqual(run_tests(self.src, command=self.command).exit_code, 0)
        (self.src / "test_issue.py").unlink()
        self.assertEqual(run_tests(self.src, command=self.command).exit_code, 5)  # no tests found at the root


if __name__ == "__main__":
    unittest.main()
