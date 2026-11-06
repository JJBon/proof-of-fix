"""scripts/github_snapshot.py (#175): the scrub, the scan and the refusals, against local git repositories only."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = "acme-" + "internal.test"
TERMS = f"{PRIVATE} => example.com\ndeny: forbidden-literal\n"


def load():
    spec = importlib.util.spec_from_file_location("github_snapshot", ROOT / "scripts" / "github_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snap = load()


def git(*args, cwd=None) -> str:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=trunk"]
    return subprocess.run(["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Terms(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "terms"

    def test_no_file_refuses(self):
        with self.assertRaisesRegex(SystemExit, "nothing would be scrubbed"):
            snap.read_terms(self.path)

    def test_a_file_with_no_replacements_refuses(self):
        self.path.write_text("# only a comment\ndeny: x\n")
        with self.assertRaisesRegex(SystemExit, "no replacements"):
            snap.read_terms(self.path)

    def test_a_malformed_line_refuses(self):
        self.path.write_text("a => b\nnot a term\n")
        with self.assertRaisesRegex(SystemExit, "neither"):
            snap.read_terms(self.path)

    def test_order_and_an_empty_replacement(self):
        self.path.write_text("# comment\nlong term => a\nterm =>\ndeny: x\n")
        self.assertEqual(snap.read_terms(self.path), ([("long term", "a"), ("term", "")], ["x"]))


class ScrubAndScan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_scrub_replaces_text_and_leaves_binary_and_symlinks(self):
        (self.root / "a.txt").write_text(f"see {PRIVATE}\n")
        (self.root / "b.bin").write_bytes(b"\0" + PRIVATE.encode())
        (self.root / "link").symlink_to("a.txt")
        self.assertEqual(snap.scrub(self.root, [(PRIVATE, "example.com")]), 1)
        self.assertEqual((self.root / "a.txt").read_text(), "see example.com\n")
        self.assertTrue((self.root / "link").is_symlink())
        self.assertIn(PRIVATE.encode(), (self.root / "b.bin").read_bytes())

    def test_scan_finds_each_kind_and_never_says_the_value(self):
        secrets = {
            "aws access key": "AKIA" + "A" * 16,
            "github token": "gh" + "p_" + "a" * 36,
            "private key": "-----BEGIN RSA " + "PRIVATE KEY-----\n" + "A" * 40,
            "account in an ARN": "arn:aws:iam::" + "2" * 12 + ":role/x",
            "account in an ECR URL": "2" * 12 + ".dkr.ecr.us-east-1.amazonaws.com",
        }
        for kind, value in secrets.items():
            with self.subTest(kind):
                (self.root / "f.txt").write_text(value)
                found = snap.scan(self.root, [], [])
                self.assertIn(("f.txt", kind), found)
                self.assertNotIn(value, repr(found))

    def test_scan_finds_a_leftover_term_and_a_denied_one(self):
        (self.root / "f.txt").write_text(PRIVATE)
        self.assertEqual(snap.scan(self.root, [(PRIVATE, "x")], []), [("f.txt", "a private term")])
        (self.root / "f.txt").write_text("forbidden-literal")
        self.assertEqual(snap.scan(self.root, [], ["forbidden-literal"]), [("f.txt", "a denied term")])

    def test_scan_passes_what_isnt_a_secret(self):
        fine = ('b"-----BEGIN EC ' + 'PRIVATE KEY-----"\n' + 'arn:aws:iam::123456789012:role/x\n'
                '111111111111.dkr.ecr.us-east-1.amazonaws.com\n' + 'TOKEN = "gh' + 'p_short"\n')
        (self.root / "f.txt").write_text(fine)
        self.assertEqual(snap.scan(self.root, [], []), [])

    def test_this_repository_holds_no_private_term_in_the_script(self):
        text = (ROOT / "scripts" / "github_snapshot.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?<!\d)\d{12}(?!\d)(?<!111111111111)(?<!123456789012)(?<!000000000000)")
        self.assertNotIn("amazonaws.com", text)


@unittest.skipUnless(shutil.which("git") and shutil.which("tar"), "needs git and tar")
class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.terms = base / "terms"
        self.terms.write_text(TERMS)
        self.source = base / "source"
        self.source.mkdir()
        git("init", "-q", cwd=self.source)
        (self.source / "README.md").write_text(f"# title\n\nAt {PRIVATE}.\n")
        (self.source / "code.py").write_text("x = 1\n")
        git("add", "-A", cwd=self.source)
        git("commit", "-q", "-m", "start", cwd=self.source)
        self.target = base / "target.git"
        git("init", "-q", "--bare", str(self.target))
        seed = base / "seed"
        git("clone", "-q", str(self.target), str(seed))
        (seed / "old.txt").write_text("gone after a snapshot\n")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", "first", cwd=seed)
        git("push", "-q", "origin", "HEAD:refs/heads/snapshot", cwd=seed)
        self.before = git("rev-parse", "refs/heads/snapshot", cwd=self.target)

    def run_it(self, *extra) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = snap.main(["proof-of-fix", "--source", str(self.source), "--ref", "HEAD", "--terms", str(self.terms),
                            "--remote-url", str(self.target), *extra])
        return rc, out.getvalue()

    def head(self) -> str:
        return git("rev-parse", "refs/heads/snapshot", cwd=self.target)

    def show(self, name: str) -> str:
        return git("show", f"refs/heads/snapshot:{name}", cwd=self.target)

    def test_a_dry_run_pushes_nothing(self):
        rc, out = self.run_it()
        self.assertEqual(rc, 0)
        self.assertIn("dry run", out)
        self.assertEqual(self.head(), self.before)

    def test_a_push_scrubs_replaces_the_tree_and_adds_the_note(self):
        rc, out = self.run_it("--push", "--trailer", "Trailer: one")
        self.assertEqual(rc, 0, out)
        self.assertNotEqual(self.head(), self.before)
        readme = self.show("README.md")
        self.assertIn("At example.com.", readme)
        self.assertNotIn(PRIVATE, readme)
        self.assertIn("Private snapshot", readme)
        files = git("ls-tree", "--name-only", "refs/heads/snapshot", cwd=self.target).split()
        self.assertEqual(sorted(files), ["README.md", "code.py"])  # old.txt is gone
        self.assertIn("Trailer: one", git("log", "-1", "--format=%B", "refs/heads/snapshot", cwd=self.target))
        self.assertEqual(git("rev-list", "--count", "refs/heads/snapshot", cwd=self.target), "2")  # no source history

    def test_pushing_again_with_nothing_new_makes_no_commit(self):
        self.run_it("--push")
        first = self.head()
        rc, out = self.run_it("--push")
        self.assertEqual((rc, self.head()), (0, first))
        self.assertIn("no changes", out)

    def test_a_finding_stops_the_push_and_doesnt_print_the_value(self):
        leak = "AKIA" + "B" * 16
        (self.source / "code.py").write_text(f"key = '{leak}'\n")
        git("add", "-A", cwd=self.source)
        git("commit", "-q", "-m", "leak", cwd=self.source)
        rc, out = self.run_it("--push")
        self.assertEqual(rc, 1)
        self.assertEqual(self.head(), self.before)
        self.assertIn("FOUND aws access key: code.py", out)
        self.assertNotIn(leak, out)

    def test_a_denied_term_stops_the_push(self):
        (self.source / "code.py").write_text("forbidden-literal\n")
        git("add", "-A", cwd=self.source)
        git("commit", "-q", "-m", "x", cwd=self.source)
        rc, _ = self.run_it("--push")
        self.assertEqual((rc, self.head()), (1, self.before))


if __name__ == "__main__":
    unittest.main()
