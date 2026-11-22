"""The first real run's tools (#150, #112): what scripts/devnet-seats.sh and scripts/first-bounty.sh refuse before they
start anything, so these run without Docker (a `docker` that fails the test stands first on the PATH); the issue the
first bounty is about really is one; and the settings that let a slow node join a round. scripts/first-run-e2e.sh runs
all of it end to end."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEATS = ROOT / "scripts" / "devnet-seats.sh"
BOUNTY = ROOT / "scripts" / "first-bounty.sh"
SECRET = "sandbox-validator:" + "ab" * 32
URL = "https://devnet.example"


def _first_bounty():
    spec = importlib.util.spec_from_file_location("first_bounty", ROOT / "scripts" / "first_bounty.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Refusals(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.bin = Path(self.dir.name)
        self.ran_docker = self.bin / "ran-docker"
        shim = self.bin / "docker"
        shim.write_text(f'#!/bin/sh\ncase "$1" in info) exit 0;; esac\ntouch "{self.ran_docker}"\nexit 99\n', encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        base = {k: v for k, v in os.environ.items() if not k.startswith(("DEVNET_", "FIRST_BOUNTY_", "POFCTL_"))}
        self.env = {**base, "PATH": f"{self.bin}:{base['PATH']}", "DEVNET_SEATS_WORK": str(self.bin / "seats")}

    def run_script(self, script, *args, **env):
        return subprocess.run(["bash", str(script), *args], capture_output=True, text=True, timeout=30,
                              env={**self.env, **env})

    def refused(self, script, says, *args, **env):
        r = self.run_script(script, *args, **env)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(says, r.stderr)
        self.assertNotIn("ab" * 32, r.stdout + r.stderr)  # never the credential
        self.assertFalse(self.ran_docker.exists(), "it reached docker before refusing")

    def test_a_credential_in_the_url(self):
        for script, args in ((SEATS, ["up"]), (BOUNTY, [])):
            self.refused(script, "without a credential in it", *args, DEVNET_RPC_URL=f"https://{SECRET}@devnet.example",
                         FIRST_BOUNTY_ANYTIME="1")

    def test_plain_http(self):
        for script, args in ((SEATS, ["up"]), (BOUNTY, [])):
            self.refused(script, "plain HTTP", *args, DEVNET_RPC_URL="http://devnet.example", DEVNET_RPC_AUTH=SECRET)

    def test_plain_http_for_the_relay_alone(self):
        self.refused(SEATS, "plain HTTP", "up", DEVNET_RPC_URL=URL, DEVNET_EXCHANGE_URL="http://devnet.example/exchange",
                     DEVNET_RPC_AUTH=SECRET)

    def test_anvils_public_keys_on_a_real_endpoint(self):
        for script, args in ((SEATS, ["up"]), (BOUNTY, [])):
            self.refused(script, "public keys", *args, DEVNET_RPC_URL=URL, DEVNET_KEYS="insecure-local", DEVNET_RPC_AUTH=SECRET)

    def test_no_credential(self):
        for script, args in ((SEATS, ["up"]), (BOUNTY, [])):
            self.refused(script, "no credential", *args, DEVNET_RPC_URL=URL)

    def test_a_malformed_credential_isnt_printed(self):
        self.refused(SEATS, "<handle>:<key>", "up", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH="ab" * 32)

    def test_no_repository_token(self):
        self.refused(SEATS, "read-only", "up", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET)
        self.refused(BOUNTY, "write:repository", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET)

    def test_first_bounty_needs_the_tokens_user(self):
        self.refused(BOUNTY, "the token's user", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET, FIRST_BOUNTY_TOKEN="ab" * 20)

    def test_no_docker_no_seats(self):
        shim = self.bin / "docker"
        shim.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        r = self.run_script(SEATS, "up", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET, DEVNET_REPO_TOKEN="x",
                            DEVNET_RECORD_V2=str(ROOT / "contracts" / "deployments" / "devnet-aws-v2.json"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("Docker isn't running", r.stderr)

    def test_the_night_stop_is_refused_unless_asked(self):
        fake = self.bin / "date"
        fake.write_text("#!/bin/sh\necho 03\n", encoding="utf-8")
        fake.chmod(0o755)
        self.refused(BOUNTY, "stops 01:00-09:00", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET, FIRST_BOUNTY_TOKEN="x",
                     FIRST_BOUNTY_USER="u")


class SecretsStayOff(unittest.TestCase):
    def test_a_refused_token_is_explained_and_not_printed(self):
        import urllib.error

        fb = _first_bounty()
        e = urllib.error.HTTPError("https://git.example/api/v1/repos/a/b/branches/main", 401, "Unauthorized", {}, None)
        message = fb.refused(e)
        self.assertIn("HTTP 401", message)
        self.assertIn("40 characters", message)
        self.assertNotIn("Authorization", message)

    def test_a_pasted_tokens_whitespace_is_trimmed(self):
        for script in ("first-bounty.sh", "devnet-seats.sh"):
            self.assertIn("TOKEN=${TOKEN//[[:space:]]/}", (ROOT / "scripts" / script).read_text())

    def test_no_key_on_a_command_line(self):
        for script in (SEATS, BOUNTY):
            code = "\n".join(line for line in script.read_text(encoding="utf-8").splitlines()
                             if not line.lstrip().startswith("#"))
            self.assertNotIn("--private-key", code)
            self.assertNotRegex(code, r"docker\s+run[^\n]*(ORACLE_PRIVATE_KEY|\$AUTH|\$TOKEN)")
        seats = SEATS.read_text(encoding="utf-8")
        # Each secret is an assignment before the command, so it's in that process's environment and never its arguments.
        for prefix in ("ORACLE_PRIVATE_KEY=$key", "ORACLE_RPC_TOKEN=$AUTH", "FORGEJO_TOKEN=$TOKEN"):
            self.assertIn(prefix, seats)
        self.assertIn("unset DEVNET_RPC_AUTH", seats)
        self.assertIn("unset DEVNET_REPO_TOKEN", seats)

    def test_the_forges_token_goes_to_git_in_a_header_by_environment(self):
        fb = _first_bounty()
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "git"
            fake.write_text(f'#!/bin/sh\necho "$@" > {tmp}/argv\nenv > {tmp}/env\n', encoding="utf-8")
            fake.chmod(0o755)
            forge = fb.Forge("acme/sandbox", "https://git.example", "writer", "s3cret-token")
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{tmp}:{old}"
            try:
                forge.git(Path(tmp), "push", "-q", "https://git.example/acme/sandbox.git", "HEAD:refs/heads/x")
            finally:
                os.environ["PATH"] = old
            self.assertNotIn("s3cret", (Path(tmp) / "argv").read_text())
            env = (Path(tmp) / "env").read_text()
            self.assertIn("http.extraHeader", env)
            self.assertIn("GIT_TERMINAL_PROMPT=0", env)
            self.assertNotIn("s3cret-token", env)  # base64, in a header


class TheIssueIsReal(unittest.TestCase):
    """The first bounty's fixes against the sandbox's own command, `python -m unittest` at the root: the tree's bug, a
    failing fix, a passing one. In this repository's tree: pof-sandbox is a copy of it."""

    def unittest_in(self, fix: str | None, with_test: bool = True) -> int:
        fb = _first_bounty()
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "bot" / "sample"
            # Writable copies: in the validator's sandbox the run tree is read-only, and so are its files' modes.
            shutil.copytree(ROOT / "bot" / "sample", sample, copy_function=shutil.copyfile)
            sample.chmod(0o755)
            if fix:
                shutil.copy(ROOT / "bot" / "fixes" / fix, sample / "stats.py")
            if with_test:
                (Path(tmp) / "test_issue_median_even.py").write_text(fb.ACCEPTANCE, encoding="utf-8")
            return subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=tmp, capture_output=True, text=True,
                                  timeout=60, env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}).returncode

    def test_the_bug_fails_the_acceptance_test(self):
        self.assertEqual(self.unittest_in(None), 1)

    def test_the_wrong_fix_fails_it(self):
        self.assertEqual(self.unittest_in("bad_stats.py"), 1)

    def test_the_right_fix_passes_it(self):
        self.assertEqual(self.unittest_in("good_stats.py"), 0)

    # unittest exits 5 when it ran no tests only since Python 3.12. That's the sandbox's pinned image, so it's what a real
    # check sees; CI's interpreter here is 3.9, where the same command exits 0.
    @unittest.skipUnless(sys.version_info >= (3, 12), "needs Python 3.12's exit code 5, as in the sandbox's image")
    def test_no_test_at_the_root_is_no_pass(self):
        self.assertNotEqual(self.unittest_in("good_stats.py", with_test=False), 0)


class TheCorrectFixTarget(unittest.TestCase):
    """--until-owner-on-pass: mean([]) on the main the first bounty left, which is good_stats.py with its test."""

    def run_it(self, fixed: bool) -> int:
        fb = _first_bounty()
        with tempfile.TemporaryDirectory() as tmp:
            sample = Path(tmp) / "bot" / "sample"
            sample.mkdir(parents=True)
            text = (ROOT / "bot" / "fixes" / "good_stats.py").read_text(encoding="utf-8")
            self.assertEqual(text.count(fb.MEAN_BUG), 1)  # the replacement finds exactly the bug
            (sample / "stats.py").write_text(text.replace(fb.MEAN_BUG, fb.MEAN_FIXED, 1) if fixed else text, encoding="utf-8")
            (Path(tmp) / "test_issue_median_even.py").write_text(fb.ACCEPTANCE, encoding="utf-8")
            (Path(tmp) / "test_issue_mean_empty.py").write_text(fb.MEAN_ACCEPTANCE, encoding="utf-8")
            return subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=tmp, capture_output=True, text=True,
                                  timeout=60, env={"PATH": os.environ["PATH"], "PYTHONDONTWRITEBYTECODE": "1"}).returncode

    def test_the_bug_fails_its_acceptance_test(self):
        self.assertEqual(self.run_it(fixed=False), 1)

    def test_the_fix_passes_both_issues_tests(self):
        self.assertEqual(self.run_it(fixed=True), 0)

    def test_the_issue_names_the_reporters_wallet(self):
        self.assertIn("Reporter wallet: 0xabc", _first_bounty().MEAN_ISSUE_BODY.format(reporter="0xabc"))


class TheDefaults(unittest.TestCase):
    def test_the_seats_wait_for_the_slow_node_as_long_as_platforms_window(self):
        self.assertIn("ROUND_TIMEOUT=${DEVNET_SEATS_ROUND_TIMEOUT:-900}", SEATS.read_text(encoding="utf-8"))
        self.assertRegex(SEATS.read_text(encoding="utf-8"), re.compile(r"JUDGE=\$\{DEVNET_SEATS_JUDGE:-fake\}"))

    def test_a_merge_keeps_the_fix_as_mains_head(self):
        self.assertNotIn("merge", _first_bounty().MERGE_STYLES)  # a merge commit would make the next verdict stale

    def test_the_odds_said_in_the_flow(self):
        doc = _first_bounty().__doc__
        for n, pct in ((2, 67), (5, 94), (8, 99)):
            self.assertEqual(round(100 * (1 - (4 / 7) ** n)), pct)
            self.assertIn(f"{pct} % with {n}", doc)

    def test_nothing_personal_in_the_tools(self):
        for script in (SEATS, BOUNTY, ROOT / "scripts" / "first_bounty.py", ROOT / "scripts" / "first-run-e2e.sh",
                       ROOT / "scripts" / "exchange-image.sh", ROOT / "tests" / "e2e_first_run_owner.py"):
            self.assertNotRegex(script.read_text(encoding="utf-8"), r"\b\d{12}\b")


if __name__ == "__main__":
    unittest.main()
