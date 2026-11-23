"""scripts/github_snapshot.py (#175): the scrub, the scan and the refusals, against local git repositories only."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_verbatim_files_keep_the_terms_and_are_counted(self):
        (self.root / "oracle").mkdir()
        (self.root / "oracle" / "rpc.py").write_text(f"see {PRIVATE}\n")
        (self.root / "docs.md").write_text(f"see {PRIVATE}\n")
        counts, kept = [[0, 0]], [[0, 0]]
        self.assertEqual(snap.scrub(self.root, [(PRIVATE, "example.com")], counts, ["oracle/"], kept), 1)
        self.assertEqual((self.root / "oracle" / "rpc.py").read_text(), f"see {PRIVATE}\n")
        self.assertEqual((self.root / "docs.md").read_text(), "see example.com\n")
        self.assertEqual((counts, kept), ([[1, 1]], [[1, 1]]))

    def test_verbatim_files_still_refuse_denied_terms_secrets_and_account_ids(self):
        (self.root / "oracle").mkdir()
        f = self.root / "oracle" / "x.py"
        f.write_text(f"{PRIVATE} " + "plat" + "form#12\n")
        self.assertEqual(snap.scan(self.root, [(PRIVATE, "x")], [], ["oracle/"]), [])
        self.assertEqual(snap.public_scan(self.root, ["oracle/"]), [])
        self.assertEqual(snap.scan(self.root, [(PRIVATE, "x")], []), [("oracle/x.py", "a private term")])
        f.write_text("forbidden-literal\n")
        self.assertEqual(snap.scan(self.root, [], ["forbidden-literal"], ["oracle/"]), [("oracle/x.py", "a denied term")])
        f.write_text("AKIA" + "A" * 16 + "\n")
        self.assertIn(("oracle/x.py", "aws access key"), snap.scan(self.root, [], [], ["oracle/"]))
        f.write_text("the account " + "21098765" + "4321" + "\n")
        self.assertEqual(snap.public_scan(self.root, ["oracle/"]), [("oracle/x.py", "an AWS account id")])

    def test_a_verbatim_file_is_named_exactly_and_a_directory_by_its_slash(self):
        self.assertTrue(snap.is_verbatim("scripts/judge_run.py", snap.IMAGE_INPUTS))
        self.assertFalse(snap.is_verbatim("scripts/judge_run.py.bak", snap.IMAGE_INPUTS))
        self.assertTrue(snap.is_verbatim("oracle/rpc.py", snap.IMAGE_INPUTS))
        self.assertFalse(snap.is_verbatim("oracle-notes.md", snap.IMAGE_INPUTS))

    def test_the_image_inputs_cover_what_the_checker_image_copies(self):
        """The checker image's COPY sources are all kept verbatim: else the public code builds another digest."""
        import re
        dockerfile = (ROOT / "oracle" / "Dockerfile").read_text(encoding="utf-8")
        sources = [m.group(1) for m in re.finditer(r"^COPY\s+(?!--from)(\S+)\s", dockerfile, re.M)]
        self.assertTrue(sources)
        for src in sources:
            with self.subTest(src):
                self.assertTrue(snap.is_verbatim(src, snap.IMAGE_INPUTS), src)
        self.assertEqual(snap.PRESETS["proof-of-fix"]["verbatim"], snap.IMAGE_INPUTS)

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
        self.assertIn("A scrubbed snapshot", readme)
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


FAKE_RAD = """#!/bin/sh
echo "$RAD_HOME|$PWD|$*" >> "$RAD_LOG"
case "$1" in
  --version) echo "${FAKE_RAD_VERSION:-rad 1.10.3 (7e1cb406bb935c3de008d2171e8961f57b4336ea)}" ;;
  self) echo "did:key:z6MkfakeNode2222222222222222222222222222222222" ;;
  init) echo "fake rad init" ;;
  .) echo "rad:z3fakeRid2222222222222222222" ;;
  *) exit 2 ;;
esac
"""


@unittest.skipUnless(shutil.which("git") and shutil.which("tar"), "needs git and tar")
class RadicleTarget(unittest.TestCase):
    """#251 task 5.1 (design L13): one root commit in a new local repository; a dry run by default with no Radicle
    call; `rad init` only with --publish and the node named; a refused scan creates nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = self.base = Path(self.tmp.name)
        self.terms = base / "terms"
        self.terms.write_text(f"# kind: company domain\n{PRIVATE} => example.com\nunused-term => x\n"
                              "deny: forbidden-literal\n")
        self.source = base / "source"
        self.source.mkdir()
        git("init", "-q", cwd=self.source)
        (self.source / "README.md").write_text(f"# title\n\nAt {PRIVATE}.\n")
        (self.source / "code.py").write_text("x = 1\n")
        git("add", "-A", cwd=self.source)
        git("commit", "-q", "-m", "start", cwd=self.source)
        git("commit", "-q", "--allow-empty", "-m", "history that must not go across", cwd=self.source)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        (bin_dir / "rad").write_text(FAKE_RAD)
        (bin_dir / "rad").chmod(0o755)
        self.log = base / "rad.log"
        self.node = base / "node"
        self.node.mkdir()
        env = mock.patch.dict(os.environ, {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                                           "RAD_LOG": str(self.log)})
        env.start()
        self.addCleanup(env.stop)

    def run_it(self, *extra) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = snap.main(["proof-of-fix", "--target", "radicle", "--source", str(self.source), "--ref", "HEAD",
                            "--terms", str(self.terms), *extra])
        return rc, out.getvalue()

    def rad_calls(self) -> list:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_a_dry_run_makes_one_root_commit_and_calls_no_radicle(self):
        out_dir = self.base / "public"
        rc, out = self.run_it("--out", str(out_dir))
        self.assertEqual(rc, 0, out)
        self.assertIn("a dry run: no Radicle command ran", out)
        self.assertEqual(self.rad_calls(), [])
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=out_dir), "1")
        self.assertEqual(len(git("rev-list", "--max-parents=0", "HEAD", cwd=out_dir).split()), 1)
        self.assertEqual(git("symbolic-ref", "HEAD", cwd=out_dir), "refs/heads/main")
        self.assertEqual(sorted(git("ls-files", cwd=out_dir).split()), ["README.md", "code.py"])
        readme = git("show", "HEAD:README.md", cwd=out_dir)
        self.assertIn("At example.com.", readme)
        self.assertIn("A scrubbed snapshot", readme)
        self.assertEqual(git("log", "-1", "--format=%an <%ae>", cwd=out_dir),
                         "Contributors to proof-of-fix <contributors@proof-of-fix.invalid>")
        self.assertIn(git("rev-parse", "HEAD", cwd=out_dir), out)
        self.assertNotIn(PRIVATE, out)
        self.assertNotIn("unused-term", out)

    def test_the_replaced_terms_are_counted_by_kind_without_their_values(self):
        _, out = self.run_it("--out", str(self.base / "public"))
        self.assertIn("term 1 (company domain): replaced 1 time(s) in 1 file(s)", out)
        self.assertIn("term 2 (company domain): replaced 0 time(s) in 0 file(s)", out)  # the label carries on
        self.assertIn("none of the 2 private and 1 denied term(s) left", out)

    def test_the_same_ref_gives_the_same_root_commit_and_expect_root_refuses_another(self):
        self.run_it("--out", str(self.base / "one"))
        self.run_it("--out", str(self.base / "two"))
        first = git("rev-parse", "HEAD", cwd=self.base / "one")
        self.assertEqual(git("rev-parse", "HEAD", cwd=self.base / "two"), first)
        rc, out = self.run_it("--out", str(self.base / "three"), "--expect-root", "0" * 40)
        self.assertEqual(rc, 1)
        self.assertIn("isn't the expected", out)
        rc, _ = self.run_it("--out", str(self.base / "four"), "--expect-root", first)
        self.assertEqual(rc, 0)

    def test_a_refused_scan_creates_nothing(self):
        leak = "AKIA" + "C" * 16
        (self.source / "code.py").write_text(f"key = '{leak}'\n")
        git("commit", "-q", "-am", "leak", cwd=self.source)
        out_dir = self.base / "public"
        rc, out = self.run_it("--out", str(out_dir), "--publish", "--rad-home", str(self.node), "--record",
                              str(self.base / "record.json"))
        self.assertEqual(rc, 1)
        self.assertIn("FOUND aws access key: code.py", out)
        self.assertIn("nothing created, nothing published", out)
        self.assertNotIn(leak, out)
        self.assertFalse(out_dir.exists())
        self.assertFalse((self.base / "record.json").exists())
        self.assertEqual(self.rad_calls(), [])

    def test_the_scan_patterns_survive_a_scrub_of_platform_references(self):
        # the owner's terms may replace "plat" + "form#" and "~/dev/" + "platform"; the scanner's own source must
        # not contain either literally, or the published copy would scan for the replacement instead
        src = (ROOT / "scripts" / "github_snapshot.py").read_text(encoding="utf-8")
        line = next(l for l in src.splitlines() if l.startswith("PLATFORM_PATTERN"))
        self.assertNotIn("plat" + "form#", line)
        self.assertNotIn("~/dev/" + "platform", line)

    def test_an_account_id_or_a_platform_reference_is_refused(self):
        for name, text, kind in (("plan.md", "the sandbox account, " + "4" * 6 + "5" * 6, "an AWS account id"),
                                 ("ci.yml", "# the runner: plat" + "form#217", "a platform reference")):
            with self.subTest(kind):
                (self.source / name).write_text(text + "\n")
                git("add", "-A", cwd=self.source)
                git("commit", "-q", "-m", name, cwd=self.source)
                rc, out = self.run_it("--out", str(self.base / name))
                self.assertEqual(rc, 1)
                self.assertIn(f"FOUND {kind}: {name}", out)
                (self.source / name).unlink()
                git("commit", "-q", "-am", "gone", cwd=self.source)

    def test_the_public_scan_allows_the_fakes_and_numbers_without_account_wording(self):
        root = self.base / "scan"
        root.mkdir()
        (root / "f.txt").write_text("account 123456789012, AccountId 111111111111\n")
        (root / "g.txt").write_text("a bond of 250000000000 wei; platform 7 and a infra# without a number\n")
        self.assertEqual(snap.public_scan(root), [])

    def test_publish_needs_the_node_and_the_record_named(self):
        for extra in ((), ("--rad-home", str(self.node)), ("--record", str(self.base / "r.json"))):
            with self.subTest(extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    self.run_it("--out", str(self.base / "public"), "--publish", *extra)
                self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.base / "public").exists())
        self.assertEqual(self.rad_calls(), [])

    def test_each_targets_options_are_refused_on_the_other(self):
        with contextlib.redirect_stderr(io.StringIO()):
            for extra in (("--push",), ("--remote-url", "x"), ("--allow-public",)):
                with self.subTest(extra), self.assertRaises(SystemExit):
                    self.run_it(*extra)
            for extra in (("--publish",), ("--out", "x"), ("--rad-home", "x"), ("--record", "x")):
                with self.subTest(extra), self.assertRaises(SystemExit):
                    snap.main(["proof-of-fix", "--terms", str(self.terms), *extra])
            with self.assertRaises(SystemExit):
                snap.main(["pof-devnet-infra", "--target", "radicle", "--terms", str(self.terms)])

    def test_publish_runs_rad_init_on_the_named_node_and_writes_the_record(self):
        out_dir, record = self.base / "public", self.base / "rec" / "publication.json"
        rc, out = self.run_it("--out", str(out_dir), "--publish", "--rad-home", str(self.node), "--record",
                              str(record))
        self.assertEqual(rc, 0, out)
        root = git("rev-parse", "HEAD", cwd=out_dir)
        written = json.loads(record.read_text())
        self.assertEqual(written, {"format": "pof-radicle-publication/1", "rid": "rad:z3fakeRid2222222222222222222",
                                   "rootCommit": root, "nodeId": "z6MkfakeNode2222222222222222222222222222222222",
                                   "radicle": "1.10.3"})
        spec = importlib.util.spec_from_file_location("publication", ROOT / "seed" / "publication.py")
        publication = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publication)
        self.assertEqual(publication.rid(record), written["rid"])
        calls = self.rad_calls()
        self.assertTrue(all(c.startswith(f"{self.node}|") for c in calls), calls)
        init = [c for c in calls if c.split("|")[2].startswith("init ")]
        self.assertEqual(len(init), 1)
        self.assertEqual(init[0].split("|")[1], str(out_dir))
        self.assertIn("--public", init[0])
        self.assertIn("--default-branch main", init[0])
        self.assertIn("published rad:z3fakeRid2222222222222222222", out)

    def test_publish_refuses_another_radicle_release_and_a_recorded_publication(self):
        with mock.patch.dict(os.environ, {"FAKE_RAD_VERSION": "rad 1.11.0 (abc)"}):
            with self.assertRaisesRegex(SystemExit, "not the pinned 1.10.3"):
                self.run_it("--out", str(self.base / "public"), "--publish", "--rad-home", str(self.node),
                            "--record", str(self.base / "r.json"))
        self.assertFalse(any(" init " in f" {c.split('|')[2]} " for c in self.rad_calls()))
        self.assertFalse((self.base / "r.json").exists())
        (self.base / "r.json").write_text("{}")
        with self.assertRaisesRegex(SystemExit, "recorded once"):
            self.run_it("--out", str(self.base / "again"), "--publish", "--rad-home", str(self.node),
                        "--record", str(self.base / "r.json"))
        self.assertFalse((self.base / "again").exists())

    def test_a_non_empty_out_is_refused(self):
        (self.base / "busy").mkdir()
        (self.base / "busy" / "x").write_text("x")
        with self.assertRaisesRegex(SystemExit, "isn't empty"):
            self.run_it("--out", str(self.base / "busy"))


class Visibility(unittest.TestCase):
    """The target's visibility: private always; public only with --allow-public, and never changed by the script."""

    def fake_run(self, visibility):
        def run(args):
            if args[:3] == ["gh", "api", "user"]:
                return '{"login": "someone", "id": 7}'
            if args[:3] == ["gh", "repo", "view"]:
                return '{"visibility": "%s"}' % visibility
            raise AssertionError(f"unexpected command: {args}")
        return run

    def target(self, visibility, allow_public):
        original = snap.run
        snap.run = self.fake_run(visibility)
        try:
            return snap.github_target("proof-of-fix", allow_public)
        finally:
            snap.run = original

    def test_private_is_accepted(self):
        self.assertEqual(self.target("PRIVATE", False)[0], "https://github.com/someone/proof-of-fix.git")

    def test_public_is_refused_by_default(self):
        with self.assertRaises(SystemExit) as caught:
            self.target("PUBLIC", False)
        self.assertIn("isn't private", str(caught.exception))

    def test_public_is_accepted_with_allow_public(self):
        self.assertEqual(self.target("PUBLIC", True)[0], "https://github.com/someone/proof-of-fix.git")


if __name__ == "__main__":
    unittest.main()
