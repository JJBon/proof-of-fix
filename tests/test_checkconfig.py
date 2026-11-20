"""The repository's own test command (proof-of-fix#166 item 3): `.pof/check.json` read at the pull request's base by
the node itself, the acceptance test always run after it, never through a shell, and a fix that can't change its own
check. The parser and the runner here; `Fetcher.file_at` against local bare repositories; the node end to end with
real git and a recording runner; and the runner in the real sandbox where Docker is ready (test_sandbox's rule)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from oracle import checkconfig, fetch, runtree, v2  # noqa: E402
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
            b"[]": 'the key "commands"',
            json.dumps({"commands": [PROJECT], "image": "x"}).encode(): 'the key "commands"',
            json.dumps({"protected": ["tests/"]}).encode(): 'the key "commands"',
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


# ---------- protected tests (#251 L20, task 4.8) ----------

SUITE = ["python", "-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-q"]
PROTECTING = json.dumps({"commands": [SUITE], "protected": ["tests/"]})
GOOD_TEST = ("import unittest\nfrom stats import median\n\nclass T(unittest.TestCase):\n    def test(self):\n"
             "        self.assertEqual(median([1, 2, 3, 4]), 2.5)\n")
WEAK_TEST = "import unittest\n\nclass T(unittest.TestCase):\n    def test(self):\n        pass\n"


class ProtectedParse(unittest.TestCase):
    def test_the_list_is_read_and_normalized(self):
        cfg = checkconfig.parse_config(json.dumps({"commands": [PROJECT], "protected": ["tests/", "a/b.py", "tests",
                                                                                       ".pof/check.json"]}).encode())
        self.assertEqual(cfg.commands, (tuple(PROJECT),))
        self.assertEqual(cfg.protected, ("tests", "a/b.py", ".pof/check.json"))  # one entry per path
        self.assertEqual(checkconfig.parse_config(CONFIG.encode()).protected, ())  # none: today's behaviour
        self.assertEqual(checkconfig.parse(PROTECTING.encode()), (tuple(SUITE),))  # the commands as before

    def test_an_invalid_list_says_why_without_the_path(self):
        for paths, why in (("tests", '"protected" must be a list'), (["x"] * 33, "at most 32"),
                           ([""], "protected path 1 isn't"), (["ok", 3], "protected path 2 isn't"),
                           (["a\\secret"], "protected path 1 isn't"), (["secret\0"], "protected path 1 isn't"),
                           (["y" * 1025], "protected path 1 isn't"), (["/etc/secret"], "protected path 1 must be"),
                           (["../secret"], "protected path 1 must be"), (["ok", "a/../secret"], "protected path 2"),
                           (["a//secret"], "protected path 1 must be"), (["./secret"], "protected path 1 must be"),
                           ([".git"], "protected path 1 must be"), (["secret//"], "protected path 1 must be"),
                           (["/"], "protected path 1 must be")):
            with self.assertRaises(checkconfig.Invalid, msg=repr(paths)[:40]) as e:
                checkconfig.parse_config(json.dumps({"commands": [PROJECT], "protected": paths}).encode())
            self.assertIn(why, str(e.exception))
            self.assertNotIn("secret", str(e.exception))
        self.assertEqual(len(checkconfig.parse_config(json.dumps({"commands": [PROJECT],
                                                                  "protected": ["x"] * 32}).encode()).protected), 1)

    def test_the_command_without_the_acceptance_test(self):
        self.assertEqual(commands_of(checkconfig.command((tuple(SUITE),), acceptance=False)), [SUITE])
        self.assertEqual(checkconfig.command((), acceptance=False), COMMAND)

    def test_proof_of_fix_s_own_file(self):
        """The repository's own `.pof/check.json` (task 4.8, before the genesis head): its suite, `tests/` protected."""
        cfg = checkconfig.parse_config((ROOT / checkconfig.PATH).read_bytes())
        self.assertEqual(cfg.protected, ("tests",))
        self.assertEqual(cfg.commands, (("python", "-m", "unittest", "discover", "-s", "tests", "-t", "tests"),))


def write_tree(root: Path, files: dict) -> None:
    for name, data in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)


class RunTreeAlone(unittest.TestCase):
    """oracle/runtree.py on plain folders: the overlay, its refusals and the tree hash."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: [fetch.remove(p) for p in self.tmp.iterdir()] and shutil.rmtree(self.tmp, True))
        self.fix, self.base, self.root = self.tmp / "fix", self.tmp / "base", self.tmp / "root"
        write_tree(self.base, {"stats.py": "old", "tests/test_a.py": "base a", "tests/deep/test_b.py": "base b"})
        write_tree(self.fix, {"stats.py": "new", "tests/test_a.py": "weak", "tests/test_new.py": "added",
                              "test_issue.py": "acceptance", ".git/HEAD": "x"})

    def files(self, root: Path) -> dict:
        return {str(p.relative_to(root)): p.read_text() for p in root.rglob("*") if p.is_file()}

    def test_the_base_s_copies_and_nothing_else_changes(self):
        run = runtree.build(self.fix, self.base, ("tests",), self.root)
        self.assertEqual(self.files(run), {"stats.py": "new", "test_issue.py": "acceptance", "tests/test_a.py": "base a",
                                           "tests/deep/test_b.py": "base b"})  # edited, deleted, added: the base's
        self.assertEqual(self.files(self.fix)["tests/test_a.py"], "weak")  # the fix's tree is untouched
        self.assertFalse(os.access(run / "stats.py", os.W_OK))  # read-only, as the checkout
        self.assertEqual(run.parent, self.root)
        p = runtree.plan(runtree.entries(self.fix), runtree.entries(self.base), ("tests",))
        self.assertEqual(p.changed, ("stats.py", "test_issue.py", "tests/deep/test_b.py", "tests/test_a.py",
                                     "tests/test_new.py"))
        self.assertEqual((p.not_run, p.tests_only), (3, False))

    def test_a_path_the_base_doesnt_have_is_removed(self):
        run = runtree.build(self.fix, self.base, ("test_issue.py", "nothing/here"), self.root)
        self.assertNotIn("test_issue.py", self.files(run))

    def test_a_symlinked_or_file_parent_fails(self):
        shutil.rmtree(self.fix / "tests")
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.fix / "tests").symlink_to(outside)
        with self.assertRaisesRegex(runtree.Unsafe, "protected path 1 is under a symlink in the fix's tree"):
            runtree.build(self.fix, self.base, ("tests/deep",), self.root)
        self.assertEqual(list(outside.iterdir()), [])  # nothing written through the link
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))  # and no run tree left behind
        (self.fix / "tests").unlink()
        (self.fix / "tests").write_text("a file where the base has a folder")
        with self.assertRaisesRegex(runtree.Unsafe, "under a file, not a folder"):
            runtree.build(self.fix, self.base, ("tests/deep",), self.root)
        run = runtree.build(self.fix, self.base, ("tests",), self.root)  # the path itself is replaced, whatever it is
        self.assertEqual(self.files(run)["tests/test_a.py"], "base a")

    def test_a_link_inside_a_protected_folder_is_copied_as_a_link(self):
        (self.base / "tests" / "link.py").symlink_to("/etc/passwd")
        run = runtree.build(self.fix, self.base, ("tests",), self.root)
        self.assertEqual(os.readlink(run / "tests" / "link.py"), "/etc/passwd")

    def test_a_tests_only_fix(self):
        fix = self.tmp / "only"
        write_tree(fix, {"stats.py": "old", "tests/test_a.py": "stronger", "tests/deep/test_b.py": "base b"})
        p = runtree.plan(runtree.entries(fix), runtree.entries(self.base), ("tests",))
        self.assertEqual((p.tests_only, p.not_run, p.protected_changed), (True, 0, ("tests/test_a.py",)))
        same = runtree.plan(runtree.entries(self.base), runtree.entries(self.base), ("tests",))
        self.assertFalse(same.tests_only)  # no change at all isn't a tests-only fix

    @unittest.skipUnless(HAS_GIT, "git isn't installed")
    def test_the_tree_hash_is_git_s(self):
        d = self.tmp / "g"
        write_tree(d, {"a.py": "1", "b/c.py": "2", "b-c.py": "3", "b/d/e": "4", "z": ""})
        (d / "run.sh").write_text("#!/bin/sh\n")
        (d / "run.sh").chmod(0o755)
        (d / "link").symlink_to("b/c.py")
        (d / "empty").mkdir()  # an empty folder isn't in git's tree
        git(d, "init", "-q")
        git(d, "add", "-A")
        self.assertEqual(runtree.tree_hash(d), git(d, "write-tree"))


class Seeing:
    """A sandbox stand-in that records what each run saw: the mounted tree, its files and the commands. `code`:
    the exit code, or a function of (the tree's path, its files)."""

    def __init__(self, code=0):
        self.code, self.seen = code, []

    def __call__(self, argv):
        mount = Path(next(a for a in argv if a.endswith(":/src:ro"))[:-len(":/src:ro")])
        files = {str(p.relative_to(mount)): p.read_text() for p in mount.rglob("*")
                 if p.is_file() and ".git" not in p.relative_to(mount).parts}
        self.seen.append({"tree": mount, "files": files, "commands": commands_of(argv),
                          "timeout": argv[argv.index("timeout") + 1]})
        code = self.code(mount, files) if callable(self.code) else self.code
        return code, "ok", ""


class ProtectedInTheNode(Case):
    """End to end in the v2 node with real git: the base's protected paths are what runs, never the fix's, and the
    shared checkout is never changed. node_v3 runs the same check (`_run_check`)."""

    def setUp(self):
        super().setUp()
        self.base = self.up.commit({".pof/check.json": PROTECTING, "tests/test_stats.py": GOOD_TEST,
                                    "tests/test_more.py": GOOD_TEST}, "the base, with protected tests")

    def change(self, files: dict, delete=(), message="fix") -> str:
        """A commit on the base: `files` written, `delete` removed."""
        work = self.up.work
        git(work, "checkout", "-q", "--detach", self.base)
        for name in delete:
            git(work, "rm", "-q", name)
        sha = self.up.commit(files, message, parent="HEAD") if files else None
        if sha is None:
            git(work, "commit", "-q", "-m", message)
            sha = git(work, "rev-parse", "HEAD")
            git(work, "push", "-q", str(self.up.bare), f"{sha}:refs/heads/c-{sha[:12]}")
        return sha

    def judge(self, sha, code=0, judge=None):
        host = self._host(sha, self._pull(sha, base=self.base))
        _, node = self._node(sha, host, judge or FakeJudge())
        node.runner = seeing = Seeing(code)
        c = self._judge(node)
        receipt = node.store.get(c.receipt_hash) if c.receipt_hash else None
        return c, seeing, receipt

    def test_a_fix_that_edits_deletes_or_adds_under_a_protected_path_runs_the_base_s_copy(self):
        sha = self.change({"stats.py": FIXED, "tests/test_stats.py": WEAK_TEST, "tests/test_extra.py": WEAK_TEST},
                          delete=["tests/test_more.py"])
        c, seeing, receipt = self.judge(sha)
        self.assertEqual(c.outcome, v2.PASS)
        self.assertEqual(len(seeing.seen), 2)  # two runs (L22), on the same run tree
        tree = seeing.seen[0]["tree"]
        self.assertEqual(seeing.seen[1]["tree"], tree)
        files = seeing.seen[0]["files"]
        self.assertEqual(files["tests/test_stats.py"], GOOD_TEST)  # edited: the base's
        self.assertEqual(files["tests/test_more.py"], GOOD_TEST)  # deleted: back
        self.assertNotIn("tests/test_extra.py", files)  # added: gone
        self.assertEqual(files["stats.py"], FIXED)  # the fix's code
        self.assertEqual(seeing.seen[0]["commands"], [SUITE, list(COMMAND)])
        # never the shared checkout, which still holds the fix as it is; the run tree is gone afterwards
        checkout = self.root / sha
        self.assertNotEqual(tree, checkout)
        self.assertEqual(tree.parent, self.root)
        self.assertEqual((checkout / "tests" / "test_stats.py").read_text(), WEAK_TEST)
        self.assertFalse(tree.exists())
        # the receipt: the list and the run tree's git hash, which is the tree of the same fix without the test edits
        same_code = self.change({"stats.py": FIXED}, message="the same fix, tests untouched")
        self.assertEqual(receipt["tests"]["protected"], ["tests"])
        self.assertEqual(receipt["tests"]["run_tree"], git(self.up.work, "rev-parse", f"{same_code}^{{tree}}"))
        self.assertEqual(receipt["tests"]["not_run"], 3)
        self.assertEqual([r["exit_code"] for r in receipt["tests"]["runs"]], [0, 0])

    def test_the_judge_is_told_how_many_changed_files_didn_t_run(self):
        sha = self.change({"stats.py": FIXED, "tests/test_stats.py": WEAK_TEST})
        host = self._host(sha, self._pull(sha, base=self.base))
        _, node = self._node(sha, host)
        node.runner = Seeing(0)
        self._judge(node)
        self.assertIn("The repository protects 1 path(s), so the base's copies of them ran: 1 of the fix's changed "
                      "file(s) were under them and were not run.", self.model.user)

    def test_a_weakened_test_doesn_t_save_a_bad_fix(self):
        bad = "def median(xs):\n    return 1\n"
        fails_on_base_tests = lambda tree, files: 0 if files.get("tests/test_stats.py") == WEAK_TEST else 1  # noqa
        sha = self.change({"stats.py": bad, "tests/test_stats.py": WEAK_TEST})
        c, seeing, _ = self.judge(sha, code=fails_on_base_tests)
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertTrue(all(s["files"]["tests/test_stats.py"] == GOOD_TEST for s in seeing.seen))
        # a fix that only weakens a protected test is a tests-only fix: its own set passes, the base's doesn't
        sha = self.change({"tests/test_stats.py": WEAK_TEST})
        c, seeing, receipt = self.judge(sha, code=fails_on_base_tests)
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertEqual(([r["exit_code"] for r in receipt["tests"]["runs"]],
                          [r["exit_code"] for r in receipt["tests"]["tests_only"]["runs"]]), ([1, 1], [0, 0]))

    def test_a_fix_that_adds_a_test_at_the_root_still_runs_it(self):
        sha = self.change({"stats.py": FIXED, "test_issue.py": WEAK_TEST})
        c, seeing, receipt = self.judge(sha)
        self.assertEqual(seeing.seen[0]["files"]["test_issue.py"], WEAK_TEST)
        self.assertEqual(seeing.seen[0]["commands"][-1], list(COMMAND))  # the acceptance test runs after the suite
        self.assertEqual(receipt["tests"]["not_run"], 0)

    def test_a_symlinked_parent_fails_the_check(self):
        base = self.up.commit({".pof/check.json": json.dumps({"commands": [SUITE], "protected": ["tests/deep"]}),
                               "tests/deep/test_x.py": GOOD_TEST}, "deeper protection")
        self.base = base
        work = self.up.work
        git(work, "checkout", "-q", "--detach", base)
        git(work, "rm", "-q", "-r", "tests")
        (work / "tests").symlink_to("/etc")
        git(work, "add", "-A")
        git(work, "commit", "-q", "-m", "tests is a link now")
        sha = git(work, "rev-parse", "HEAD")
        git(work, "push", "-q", str(self.up.bare), f"{sha}:refs/heads/c-{sha[:12]}")
        c, seeing, receipt = self.judge(sha, judge=None)
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertEqual(seeing.seen, [])  # nothing ran
        self.assertEqual(self.model.sent, [])  # and no model call
        # git's links arrive as files (the fetch keeps no symlinks): a file where the folder was fails the same way
        self.assertTrue(any("protected tests can't be overlaid: protected path 1 is under a" in m for m in self.logs),
                        self.logs)

    def test_a_tests_only_fix_runs_both_sets_and_both_must_pass(self):
        stronger = GOOD_TEST + "\n    def test_more(self):\n        self.assertEqual(median([5]), 5)\n"
        sha = self.change({"tests/test_stats.py": stronger, "tests/test_new.py": GOOD_TEST})
        c, seeing, receipt = self.judge(sha)
        self.assertEqual(c.outcome, v2.PASS)
        self.assertEqual(len(seeing.seen), 4)  # each set twice
        theirs, own = seeing.seen[:2], seeing.seen[2:]
        self.assertEqual(theirs[0]["files"]["tests/test_stats.py"], GOOD_TEST)
        self.assertNotIn("tests/test_new.py", theirs[0]["files"])
        self.assertEqual(own[0]["tree"], self.root / sha)  # its own tests, on its own tree
        self.assertEqual(own[0]["files"]["tests/test_stats.py"], stronger)
        self.assertTrue(all(s["commands"] == [SUITE] for s in seeing.seen))  # no acceptance test at the root
        self.assertTrue(all(s["timeout"] == "75" for s in seeing.seen))  # a quarter of the 300 s each
        self.assertEqual(receipt["tests"]["tests_only"]["run_tree"],
                         git(self.up.work, "rev-parse", f"{sha}^{{tree}}"))
        self.assertEqual(receipt["tests"]["run_tree"], git(self.up.work, "rev-parse", f"{self.base}^{{tree}}"))
        # its own tests failing fails it, though the base's pass
        c, seeing, receipt = self.judge(sha, code=lambda tree, files: 1 if tree == self.root / sha else 0)
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertEqual(receipt["tests"]["exit_code"], 1)
        self.assertEqual(receipt["tests"]["tests_only"]["exit_code"], 1)

    def test_an_invalid_list_fails_closed(self):
        self.base = self.up.commit({".pof/check.json": json.dumps({"commands": [SUITE], "protected": ["../x"]})},
                                   "a bad list")
        sha = self.change({"stats.py": FIXED})
        c, seeing, _ = self.judge(sha, judge=None)
        self.assertEqual(c.outcome, v2.FAIL)
        self.assertEqual(self.model.sent, [])
        self.assertTrue(any("protected path 1 must be relative" in m for m in self.logs), self.logs)

    def test_no_protected_list_is_today_s_behaviour(self):
        self.base = self.up.commit({".pof/check.json": CONFIG}, "commands only")
        sha = self.change({"stats.py": FIXED, "tests/test_stats.py": WEAK_TEST})
        c, seeing, receipt = self.judge(sha)
        self.assertEqual(c.outcome, v2.PASS)
        self.assertEqual({s["tree"] for s in seeing.seen}, {self.root / sha})  # the fix's own checkout
        self.assertEqual(seeing.seen[0]["files"]["tests/test_stats.py"], WEAK_TEST)
        self.assertFalse({"protected", "run_tree", "not_run", "tests_only"} & set(receipt["tests"]))
        self.assertFalse((self.root / self.base).exists())  # the base isn't even checked out

    def test_a_base_it_can_t_check_out_gives_no_verdict_yet(self):
        sha = self.change({"stats.py": FIXED})
        host = self._host(sha, self._pull(sha, base=self.base))
        _, node = self._node(sha, host, FakeJudge())
        node.runner = seeing = Seeing(0)
        real = node.fetcher.ensure
        node.fetcher.ensure = lambda root, s, fix: False if s == self.base else real(root, s, fix)
        for _ in range(4):
            node.tick(0)
        self.assertEqual(node.checks[1].outcome, 0)
        self.assertEqual(seeing.seen, [])
        self.assertTrue(any(f"no checkout of the base {self.base[:12]}" in m for m in self.logs), self.logs)


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
