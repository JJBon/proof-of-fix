"""The AWS devnet's seats host's side in proof-of-fix (#152, platform#219): the role seat's entry in the node's image
(oracle/seat.py) and the images' build script. No network, no Docker, no AWS."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oracle import seat

ROOT = Path(__file__).resolve().parent.parent
KEY = "0x" + "07" * 32
AUTH = "pof-seats:s3cret-api-key"
TOKEN = "s3cret-repo-token"
RACE = "0x" + "ab" * 20


class SeatEntryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.secrets = Path(self.tmp.name) / "secrets"
        self.secrets.mkdir()
        self.work = Path(self.tmp.name) / "work" / "oracle-0"
        for name, value in (("key", KEY + "\n"), ("rpc-auth", AUTH + "\n"), ("repo-token", TOKEN + "\n")):
            (self.secrets / name).write_text(value)

    def env(self, **extra) -> dict:
        return {"ORACLE_RPC": "https://devnet.example", "ORACLE_RACE": RACE, "SEAT_SECRETS": str(self.secrets),
                "SEAT_WORK": str(self.work), **extra}

    def test_the_secrets_from_their_files_and_devnet_seats_settings(self):
        env = self.env()
        seat.configure(env, "run")
        self.assertEqual((env["ORACLE_PRIVATE_KEY"], env["ORACLE_RPC_TOKEN"], env["FORGEJO_TOKEN"]), (KEY, AUTH, TOKEN))
        expected = {"ORACLE_KEYS": "env", "ORACLE_VERSION": "2", "ORACLE_RPC_API_KEY_HEADER": "Basic",
                    "ORACLE_EXCHANGE_TRANSPORT": "http", "ORACLE_EXCHANGE_URL": "https://devnet.example/exchange",
                    "ORACLE_REPO": "example-org/pof-sandbox", "FORGEJO_USER": "pof-validator-bot",
                    "ORACLE_JUDGE": "fake", "ORACLE_ROUND_TIMEOUT": "900", "ORACLE_POLL": "5", "ORACLE_SANDBOX": "api",
                    "ORACLE_SRC_ROOT": str(self.work / "src"), "ORACLE_RECEIPTS": str(self.work / "receipts"),
                    "ORACLE_REPOS": str(self.work / "repos.json")}
        self.assertEqual({k: env[k] for k in expected}, expected)
        self.assertTrue((self.work / "src").is_dir())
        repos = (self.work / "repos.json").read_text()
        self.assertEqual(json.loads(repos), {"repos": {"example-org/pof-sandbox": {
            "host": "forgejo", "api": "https://git.example.com"}}})
        for secret in (KEY, AUTH, TOKEN, "s3cret"):
            self.assertNotIn(secret, repos)

    def test_devnet_seats_sh_and_the_entry_agree(self):
        """The laptop's settings (scripts/devnet-seats.sh's in_node_env) are the host's defaults."""
        script = (ROOT / "scripts" / "devnet-seats.sh").read_text()
        for var, value in (("ORACLE_KEYS", "env"), ("ORACLE_VERSION", "2"), ("ORACLE_RPC_API_KEY_HEADER", "Basic"),
                           ("ORACLE_EXCHANGE_TRANSPORT", "http")):
            self.assertIn(f"{var}={value}", script)
            self.assertEqual(seat.DEFAULTS[var], value)
        self.assertIn("DEVNET_SEATS_ROUND_TIMEOUT:-900", script)
        self.assertIn("DEVNET_SEATS_POLL:-5", script)
        self.assertIn("DEVNET_SEATS_JUDGE:-fake", script)

    def test_the_environment_wins_over_a_file(self):
        env = self.env(FORGEJO_TOKEN="from-env", ORACLE_REPOS="/etc/repos.json", ORACLE_SRC_ROOT=str(self.work / "x"))
        seat.configure(env, "run")
        self.assertEqual((env["FORGEJO_TOKEN"], env["ORACLE_PRIVATE_KEY"]), ("from-env", KEY))
        self.assertEqual(env["ORACLE_REPOS"], "/etc/repos.json")
        self.assertFalse((self.work / "repos.json").exists())

    def test_info_needs_no_working_directory(self):
        env = self.env()
        del env["SEAT_WORK"]
        seat.configure(env, "info")  # seats.sh status: `oracle seat info` in the running container
        self.assertEqual(env["ORACLE_PRIVATE_KEY"], KEY)
        with self.assertRaisesRegex(seat.Refused, "SEAT_WORK"):
            seat.configure(self.env(SEAT_WORK="relative/dir"), "run")

    def test_a_missing_or_bad_secret_is_named_never_shown(self):
        (self.secrets / "repo-token").unlink()
        with self.assertRaisesRegex(seat.Refused, "FORGEJO_TOKEN.*repo-token"):
            seat.configure(self.env(), "run")
        (self.secrets / "repo-token").write_text("\n")
        with self.assertRaisesRegex(seat.Refused, "FORGEJO_TOKEN is empty"):
            seat.configure(self.env(), "run")
        (self.secrets / "repo-token").write_text(TOKEN)
        (self.secrets / "rpc-auth").write_text("s3cret-without-handle")
        with self.assertRaises(seat.Refused) as caught:
            seat.configure(self.env(), "run")
        self.assertIn("<handle>:<key>", str(caught.exception))
        self.assertNotIn("s3cret", str(caught.exception))

    def test_only_the_fake_judge(self):
        with self.assertRaisesRegex(seat.Refused, "#160"):
            seat.configure(self.env(ORACLE_JUDGE="direct:bedrock:x"), "run")

    def test_urls_without_credentials_and_https_only(self):
        for bad in ({"ORACLE_RPC": "https://u:k@devnet.example"},
                    {"ORACLE_EXCHANGE_URL": "https://u:k@devnet.example/exchange"},
                    {"ORACLE_RPC": "http://devnet.example"}, {"ORACLE_RPC": ""}, {"ORACLE_RACE": ""}):
            with self.assertRaises(seat.Refused, msg=str(bad)):
                seat.configure(self.env(**bad), "run")
        env = self.env(ORACLE_RPC="http://127.0.0.1:8545", SEAT_ALLOW_HTTP="1")
        seat.configure(env, "run")  # a local test proxy, as devnet-seats.sh's DEVNET_RPC_ALLOW_HTTP
        self.assertEqual(env["ORACLE_EXCHANGE_URL"], "http://127.0.0.1:8545/exchange")

    def test_main_hands_the_command_to_the_node(self):
        got = []
        with mock.patch.dict(os.environ, self.env(), clear=True):
            rc = seat.main(["seat", "run", "--until-idle", "600"], lambda argv: got.append(argv) or 75)
            self.assertEqual(os.environ["ORACLE_PRIVATE_KEY"], KEY)  # the node's own process environment
        self.assertEqual((rc, got), (75, [["oracle", "run", "--until-idle", "600"]]))  # its exit code, unchanged

    def test_a_refusal_exits_2_without_running_the_node_or_printing_a_secret(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("ORACLE_", "SEAT_", "FORGEJO_"))}
        env.update(self.env(ORACLE_JUDGE="gateway:x"), PYTHONPATH=str(ROOT))
        out = subprocess.run([sys.executable, "-m", "oracle", "seat", "run", "--until-idle", "600"], env=env, cwd=ROOT,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 2)
        self.assertIn("oracle seat: ", out.stderr)
        for secret in (KEY, AUTH, TOKEN):
            self.assertNotIn(secret, out.stdout + out.stderr)


class ImagesTest(unittest.TestCase):
    def test_the_node_image_carries_the_seat_entry_and_pofctl(self):
        dockerfile = (ROOT / "oracle" / "Dockerfile").read_text()
        self.assertRegex(dockerfile, r"(?m)^FROM python@sha256:[0-9a-f]{64}$")
        self.assertIn("COPY oracle/ /app/oracle/", dockerfile)  # oracle/seat.py with it
        self.assertIn("COPY pofctl/ /app/pofctl/", dockerfile)  # the bot service (#210) runs from this image
        self.assertIn('ENTRYPOINT ["python3", "-m", "oracle"]', dockerfile)  # the kit's command is unchanged

    def test_the_build_script(self):
        script = (ROOT / "scripts" / "seats-image.sh").read_text()
        subprocess.run(["bash", "-n", str(ROOT / "scripts" / "seats-image.sh")], check=True)
        self.assertTrue(os.access(ROOT / "scripts" / "seats-image.sh", os.X_OK))
        for needed in ("--platform linux/arm64", "--provenance=false", "--sbom=false", "rewrite-timestamp=true",
                       "SOURCE_DATE_EPOCH", "git archive", "node_image_digest", "watcher_image_digest",
                       "an image must come from a commit", "source scripts/ecr-login.sh", "ecr_login "):
            self.assertIn(needed, script)
        self.assertIn("--password-stdin", (ROOT / "scripts" / "ecr-login.sh").read_text())  # #213
        self.assertNotRegex(script, r"--value\b|set -x")
        out = subprocess.run(["bash", str(ROOT / "scripts" / "seats-image.sh"), "node", "not-a-repository"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 2)
        self.assertIn("seats-image.sh node <repository url>", out.stdout)
        self.assertTrue(re.search(r"tofu output -raw seats_node_repository_url", out.stdout))


if __name__ == "__main__":
    unittest.main()
