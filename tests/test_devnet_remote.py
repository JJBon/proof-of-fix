"""scripts/devnet.sh's remote mode (#150, #112): what it refuses before it starts anything, so these run without Docker
(a `docker` that fails the test stands first on the PATH). scripts/devnet-remote-e2e.sh runs the mode end to end."""

import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEVNET = ROOT / "scripts" / "devnet.sh"
SECRET = "sandbox-validator:" + "ab" * 32
URL = "https://devnet.example"


class TestRefusals(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.bin = Path(self.dir.name)
        self.ran_docker = self.bin / "ran-docker"
        shim = self.bin / "docker"
        shim.write_text(f'#!/bin/sh\ntouch "{self.ran_docker}"\nexit 99\n', encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)

    def run_devnet(self, *args, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith("DEVNET_")}
        return subprocess.run(["bash", str(DEVNET), *args], capture_output=True, text=True, timeout=30,
                              env={**base, "PATH": f"{self.bin}:{base['PATH']}", **env})

    def assert_refused(self, result, says):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(says, result.stderr)
        self.assertNotIn("ab" * 32, result.stdout + result.stderr)  # never the credential
        self.assertFalse(self.ran_docker.exists(), "it reached docker before refusing")

    def test_a_credential_in_the_url_is_refused(self):
        self.assert_refused(self.run_devnet("status", DEVNET_RPC_URL=f"https://{SECRET}@devnet.example"),
                            "without a credential in it")

    def test_plain_http_is_refused_unless_the_test_rig_says_so(self):
        self.assert_refused(self.run_devnet("status", DEVNET_RPC_URL="http://devnet.example", DEVNET_RPC_AUTH=SECRET),
                            "plain HTTP")

    def test_anvils_public_keys_are_refused_on_a_real_endpoint(self):
        self.assert_refused(self.run_devnet("deploy-v2", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET,
                                            DEVNET_KEYS="insecure-local"), "public keys")

    def test_no_credential_is_refused(self):
        self.assert_refused(self.run_devnet("status", DEVNET_RPC_URL=URL), "no credential")

    def test_a_malformed_credential_is_refused_without_printing_it(self):
        self.assert_refused(self.run_devnet("status", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH="ab" * 32), "<handle>:<key>")

    def test_an_unreadable_credential_file_is_refused(self):
        self.assert_refused(self.run_devnet("status", DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH_FILE="/nonexistent/auth"),
                            "DEVNET_RPC_AUTH_FILE")

    def test_the_local_devnets_commands_are_refused(self):
        for command in ("up", "down", "reset", "deploy", "scenarios"):
            self.assert_refused(self.run_devnet(command, DEVNET_RPC_URL=URL, DEVNET_RPC_AUTH=SECRET), command)


class TestShape(unittest.TestCase):
    """What the end-to-end run can't see from a throwaway rig: the real defaults."""

    def setUp(self):
        self.script = DEVNET.read_text(encoding="utf-8")
        self.remote = self.script[self.script.index("# ---------- Remote mode"):]

    def test_the_aws_devnets_record_is_its_own(self):
        self.assertIn("RECORD_V2=${DEVNET_RECORD_V2:-contracts/deployments/devnet-aws-v2.json}", self.remote)
        self.assertRegex(self.script, r"(?m)^RECORD_V2=\$\{DEVNET_RECORD_V2:-contracts/deployments/devnet-v2\.json\}$")
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertNotRegex(ignored, r"(?m)^/?contracts/deployments/(devnet-aws|\*|$)")  # committed, like devnet.json

    def test_the_chain_is_checked_before_any_command_runs(self):
        self.assertRegex(self.script, r"(?m)^CHAIN_ID=7193$")
        start = self.remote.index('  remote_validate\n  remote_start\n')
        self.assertLess(self.remote.index('[[ "$out" != "$CHAIN_ID" ]]'), start)  # remote_start holds the check
        self.assertGreater(self.remote.index('case "${1:-}" in\n  up) up ;;'), start)  # and comes before the commands

    def test_the_credential_stays_off_the_container_and_its_url(self):
        run = re.search(r"docker run -d --rm --name.*?>/dev/null", self.remote, re.S).group(0)
        self.assertNotIn("HOST_RPC_AUTH", run)
        self.assertNotIn("basic", run)
        self.assertNotIn("HEADERS", run)
        self.assertIn("unset DEVNET_RPC_AUTH", self.remote)
        self.assertIn("/dev/shm/rpc-auth", self.remote)  # on stdin into memory

    def test_keys_stay_off_the_remote_modes_command_lines(self):
        code = "\n".join(line for line in self.remote.splitlines() if not line.lstrip().startswith("#"))
        self.assertNotIn("--private-key", code)
        self.assertIn("forge script script/DeployV2.s.sol:DeployV2Script --rpc-url '\"$RPC\"' --broadcast --slow", self.script)
        self.assertIn("address_of() { python3 -c", self.remote)  # not `cast wallet address --private-key`

    def test_no_account_ids_or_credentials_in_what_the_owner_reads(self):
        runbook = (ROOT / "validator-kit" / "runbook.md").read_text(encoding="utf-8")
        section = runbook[runbook.index("## The AWS devnet"):runbook.index("## A Forgejo target")]
        self.assertIn("DEVNET_V2_REPO=example-org/pof-sandbox", section)
        self.assertNotRegex(section, r"\b\d{12}\b")  # #126's checklist


if __name__ == "__main__":
    unittest.main()
