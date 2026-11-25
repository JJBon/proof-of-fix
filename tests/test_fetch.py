"""The node fetches the fix's code itself (proof-of-fix#115): exactly the claimed commit, verified, read-only, within
a time and a size limit, with the token kept out of argv and logs. Against local bare repositories and fake gits:
no network."""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle import fetch  # noqa: E402
from oracle.v2 import commit_word  # noqa: E402

HAS_GIT = shutil.which("git") is not None
TOKEN = "ghp_secretTOKENvalue123"


def git(cwd, *args):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_TERMINAL_PROMPT": "0"}
    out = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                          "-c", "init.defaultBranch=trunk", *args], cwd=str(cwd), env=env, capture_output=True,
                         text=True, check=True)
    return out.stdout.strip()


def make_repo(tmp: Path, files: dict) -> tuple:
    """A bare repository with one commit of `files` (and an earlier one); returns (url, the head's sha, the first's)."""
    work, bare = tmp / "work", tmp / "bare.git"
    work.mkdir()
    git(work, "init", "-q")
    (work / "README").write_text("first\n")
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "first")
    first = git(work, "rev-parse", "HEAD")
    for name, data in files.items():
        (work / name).write_bytes(data if isinstance(data, bytes) else data.encode())
    git(work, "add", ".")
    git(work, "commit", "-q", "-m", "the fix")
    git(tmp, "init", "-q", "--bare", str(bare))
    git(work, "push", "-q", str(bare), "HEAD:refs/heads/fix")
    return f"file://{bare}", git(work, "rev-parse", "HEAD"), first


def fake_git(tmp: Path, body: str) -> str:
    """An executable standing in for git: Python, with `record` (a JSON file) and `real` (the real git) in scope."""
    path = tmp / "fake-git"
    path.write_text(f"#!{sys.executable}\nimport json, os, sys, time\nrecord = {str(tmp / 'calls.json')!r}\n"
                    f"real = {shutil.which('git') or 'git'!r}\n{body}\n")
    path.chmod(0o755)
    return str(path)


class Logs(list):
    def __call__(self, message):
        self.append(message)


class FetchCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "src"
        self.logs = Logs()

    def tearDown(self):
        for p in self.root.glob("*") if self.root.exists() else []:
            fetch.remove(p)
        shutil.rmtree(self.tmp)


@unittest.skipUnless(HAS_GIT, "git isn't installed")
class TestFetchFromABareRepo(FetchCase):
    def test_fetches_exactly_that_commit_read_only(self):
        url, sha, _ = make_repo(self.tmp, {"stats.py": "def median(xs):\n    return 0\n"})
        f = fetch.Fetcher(url, log=self.logs)
        self.assertTrue(f.ensure(self.root, sha, commit_word(sha)))
        dest = self.root / sha
        self.assertEqual((dest / "stats.py").read_text(), "def median(xs):\n    return 0\n")
        self.assertEqual(git(dest, "rev-parse", "HEAD"), sha)
        self.assertEqual(git(dest, "rev-list", "--count", "HEAD"), "1")  # shallow: that commit only
        # The mode bits, not os.access: root (the CI runner) can write anything, whatever the mode.
        self.assertEqual((dest / "stats.py").stat().st_mode & 0o222, 0)
        self.assertEqual(dest.stat().st_mode & 0o222, 0)
        self.assertEqual([p.name for p in self.root.iterdir()], [sha])  # no temporary directory left behind
        self.assertTrue(f.ensure(self.root, sha, commit_word(sha)))  # a second pass reuses it

    def test_the_range_diff_of_a_rebase(self):
        """#310 RB3: an approved fix and its rebase onto a head that moved, from their merge bases, by this node."""
        url, fix, first = make_repo(self.tmp, {"stats.py": "def median(xs):\n    return sorted(xs)[len(xs) // 2]\n"})
        work = self.tmp / "work"
        git(work, "checkout", "-q", "-b", "head", first)
        (work / "other.py").write_text("x = 1\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "the first fix")
        head = git(work, "rev-parse", "HEAD")
        git(work, "cherry-pick", fix)
        rebased = git(work, "rev-parse", "HEAD")
        git(work, "checkout", "-q", "-b", "smuggled", head)  # the same fix on the same head, and one more line
        (work / "stats.py").write_text("def median(xs):\n    return sorted(xs)[len(xs) // 2]\nsmuggled = True\n")
        git(work, "add", ".")
        git(work, "commit", "-q", "-m", "the fix")
        smuggled = git(work, "rev-parse", "HEAD")
        git(work, "push", "-q", str(self.tmp / "bare.git"), f"{smuggled}:refs/heads/smuggled",
            f"{rebased}:refs/heads/clean")
        f = fetch.Fetcher(url, log=self.logs)
        clean = f.range_diff(self.root, first, fix, head, rebased)
        self.assertEqual(clean.refusal, "")
        self.assertRegex(clean.text, r"1:\s+[0-9a-f]+ = 1:\s+[0-9a-f]+ the fix")
        dirty = f.range_diff(self.root, first, fix, head, smuggled)
        self.assertIn("smuggled = True", dirty.text)
        self.assertEqual(f.range_diff(self.root, first, fix, head, "zz").refusal,
                         "a rebase's range-diff needs four commit ids")
        self.assertFalse([p for p in self.root.iterdir()])  # nothing left behind

    def test_a_fix_the_seal_doesnt_commit_to_is_refused_before_fetching(self):
        url, sha, first = make_repo(self.tmp, {"stats.py": "x = 1\n"})
        f = fetch.Fetcher(url, log=self.logs)
        self.assertFalse(f.ensure(self.root, sha, commit_word(first)))
        self.assertFalse(self.root.exists())
        self.assertIn("isn't the fix the seal commits to", self.logs[-1])

    def test_a_commit_the_host_doesnt_have_is_refused(self):
        url, _, _ = make_repo(self.tmp, {"stats.py": "x = 1\n"})
        missing = "ab" * 20
        f = fetch.Fetcher(url, log=self.logs)
        self.assertFalse(f.ensure(self.root, missing, commit_word(missing)))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIn("git fetch failed", self.logs[-1])

    def test_a_host_serving_another_commit_is_refused(self):
        url, sha, first = make_repo(self.tmp, {"stats.py": "x = 1\n"})
        # The "host" answers a fetch of the fix with its parent instead.
        wrapper = fake_git(self.tmp, f"a = sys.argv[1:]\nif a[0] == 'fetch':\n    a[-1] = {first!r}\n"
                                     "os.execv(real, [real] + a)")
        f = fetch.Fetcher(url, log=self.logs, git=wrapper)
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertFalse((self.root / sha).exists())
        self.assertIn(f"served commit {first[:12]}, not {sha[:12]}", self.logs[-1])

    def test_the_size_limit_holds(self):
        url, sha, _ = make_repo(self.tmp, {"blob.bin": os.urandom(2 << 20)})
        f = fetch.Fetcher(url, max_bytes=256 << 10, log=self.logs)
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIn("larger than the limit", self.logs[-1])

    def test_an_existing_directory_at_another_commit_is_not_used_or_overwritten(self):
        url, sha, _ = make_repo(self.tmp, {"stats.py": "x = 1\n"})
        planted = self.root / sha
        planted.mkdir(parents=True)
        (planted / "stats.py").write_text("planted\n")
        f = fetch.Fetcher(url, log=self.logs)
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertEqual((planted / "stats.py").read_text(), "planted\n")
        self.assertIn("refused (not overwritten)", self.logs[-1])

    def test_two_nodes_fetching_into_one_root(self):
        url, sha, _ = make_repo(self.tmp, {"stats.py": "x = 1\n"})
        a, b = fetch.Fetcher(url, log=self.logs), fetch.Fetcher(url, log=self.logs)
        self.assertTrue(a.ensure(self.root, sha, commit_word(sha)))
        self.assertTrue(b.ensure(self.root, sha, commit_word(sha)))
        self.assertEqual([p.name for p in self.root.iterdir()], [sha])


class TestLimitsAndCredentials(FetchCase):
    def test_the_time_limit_kills_the_fetch(self):
        slow = fake_git(self.tmp, "if sys.argv[1] == 'fetch':\n    time.sleep(30)\n")
        f = fetch.Fetcher("https://git.example/o/r.git", timeout_s=0.5, log=self.logs, git=slow)
        sha = "cd" * 20
        started = time.monotonic()
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertLess(time.monotonic() - started, 10)
        self.assertIn("took longer than the limit", self.logs[-1])
        self.assertEqual(list(self.root.iterdir()), [])

    def test_the_token_is_never_in_argv_urls_or_logs(self):
        spy = fake_git(self.tmp, "calls = json.load(open(record)) if os.path.exists(record) else []\n"
                                 "calls.append({'argv': sys.argv, 'env': dict(os.environ)})\n"
                                 "json.dump(calls, open(record, 'w'))\n"
                                 f"if sys.argv[1] == 'fetch':\n    sys.stderr.write('fatal: denied for {TOKEN}\\n')\n"
                                 "    sys.exit(128)\n")
        f = fetch.Fetcher("https://git.example/o/r.git", token=TOKEN, log=self.logs, git=spy)
        sha = "ef" * 20
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        calls = json.loads((self.tmp / "calls.json").read_text())
        self.assertEqual([c["argv"][1] for c in calls], ["init", "fetch"])
        for c in calls:
            self.assertNotIn(TOKEN, " ".join(c["argv"]))
            self.assertNotIn(base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode(), " ".join(c["argv"]))
        env = calls[1]["env"]
        headers = [env[f"GIT_CONFIG_VALUE_{i}"] for i in range(int(env["GIT_CONFIG_COUNT"]))
                   if env[f"GIT_CONFIG_KEY_{i}"] == "http.extraHeader"]
        self.assertEqual(headers, ["Authorization: Basic " +
                                   base64.b64encode(f"x-access-token:{TOKEN}".encode()).decode()])
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(env["GIT_ALLOW_PROTOCOL"], "https")
        self.assertNotIn("GITHUB_TOKEN", env)  # git gets a clean environment, not the node's
        self.assertTrue(self.logs)
        self.assertFalse([m for m in self.logs if TOKEN in m])
        self.assertIn("***", self.logs[-1])
        self.assertNotIn(TOKEN, repr(f))

    def test_a_failure_is_retried_later_not_every_pass(self):
        spy = fake_git(self.tmp, "calls = json.load(open(record)) if os.path.exists(record) else []\n"
                                 "calls.append(sys.argv[1])\njson.dump(calls, open(record, 'w'))\nsys.exit(1)\n")
        f = fetch.Fetcher("https://git.example/o/r.git", retry_s=3600, log=self.logs, git=spy)
        sha = "12" * 20
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertFalse(f.ensure(self.root, sha, commit_word(sha)))
        self.assertEqual(json.loads((self.tmp / "calls.json").read_text()), ["init"])

    def test_not_a_commit_id(self):
        f = fetch.Fetcher("https://git.example/o/r.git", log=self.logs)
        for bad in ("../../etc", "HEAD", "ab" * 19):
            self.assertFalse(f.ensure(self.root, bad, b"\0" * 32))
        self.assertFalse(self.root.exists())

    def test_clone_urls(self):
        self.assertEqual(fetch.check_url("https://github.com/o/r.git"), "https")
        self.assertEqual(fetch.check_url("http://127.0.0.1:3300/o/r.git"), "http")
        self.assertEqual(fetch.check_url("file:///srv/r.git"), "file")
        for bad in ("http://git.example/o/r.git", "https://user:pw@github.com/o/r.git", "ssh://git@github.com/o/r",
                    "ext::sh -c touch% /tmp/x", "/srv/r.git"):
            with self.assertRaises(ValueError, msg=bad):
                fetch.check_url(bad)


class TestConfiguration(unittest.TestCase):
    def test_github_by_default(self):
        from bot.github import GitHubRepo

        f = fetch.from_env({}, "o/r", GitHubRepo("o/r", token=TOKEN))
        self.assertEqual(f.url, "https://github.com/o/r.git")
        self.assertEqual((f._token, f._user, f.max_bytes, f.timeout_s), (TOKEN, "x-access-token", 200 << 20, 120.0))
        ghes = fetch.from_env({}, "o/r", GitHubRepo("o/r", api="https://ghe.example/api/v3"))
        self.assertEqual(ghes.url, "https://ghe.example/o/r.git")

    def test_forgejo_uses_its_base_and_token(self):
        from bot.forge import repo_for

        host = repo_for("o/r", {"repos": {"o/r": {"host": "forgejo", "api": "http://127.0.0.1:3300"}}},
                        {"FORGEJO_USER": "loop", "FORGEJO_PASSWORD": "pw", "FORGEJO_TOKEN": "ft"})
        f = fetch.from_env({}, "o/r", host)
        self.assertEqual((f.url, f._token, f._user), ("http://127.0.0.1:3300/o/r.git", "ft", "loop"))

    def test_a_host_can_name_its_own_source(self):
        class Seed:  # any host (ADR 0003: not only GitHub): it says where its commits are fetched from
            def clone_source(self, repo_name):
                return f"https://seed.example/{repo_name}.git", "", "anonymous"

        f = fetch.from_env({}, "o/r", Seed())
        self.assertEqual((f.url, f._token, f._user), ("https://seed.example/o/r.git", "", "anonymous"))

    def test_overrides_and_off(self):
        from bot.github import GitHubRepo

        host = GitHubRepo("o/r", token="from-github-token")
        with tempfile.TemporaryDirectory() as tmp:
            token_file = Path(tmp) / "token"
            token_file.write_text(TOKEN + "\n")
            f = fetch.from_env({"ORACLE_GIT_URL": "file:///srv/{repo}.git", "ORACLE_GIT_TOKEN_FILE": str(token_file),
                                "ORACLE_FETCH_MAX_MB": "5", "ORACLE_FETCH_TIMEOUT": "9"}, "o/r", host)
        self.assertEqual((f.url, f._token, f.max_bytes, f.timeout_s), ("file:///srv/o/r.git", TOKEN, 5 << 20, 9.0))
        self.assertEqual(fetch.from_env({"ORACLE_GIT_TOKEN": "t2"}, "o/r", host)._token, "t2")
        self.assertIsNone(fetch.from_env({"ORACLE_FETCH": "0"}, "o/r", host))
        with self.assertRaises(ValueError):
            fetch.from_env({"ORACLE_GIT_URL": "https://u:p@github.com/{repo}.git"}, "o/r", host)

    def test_without_a_fetcher_only_an_existing_checkout_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            sha = "34" * 20
            self.assertFalse(fetch.ensure(Path(tmp), {"head_sha": sha}, commit_word(sha)))
            (Path(tmp) / sha).mkdir()
            self.assertTrue(fetch.ensure(Path(tmp), {"head_sha": sha}, commit_word(sha)))


if __name__ == "__main__":
    unittest.main()
