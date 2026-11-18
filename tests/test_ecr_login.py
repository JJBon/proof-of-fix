"""scripts/ecr-login.sh (proof-of-fix#213): the image scripts log in to ECR with a throwaway Docker config, because
Docker Desktop's Windows credential store refuses ECR tokens. Stubs stand in for aws and docker: nothing leaves the
machine."""

import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "ecr-token-" + "x" * 3000  # longer than the Windows store takes

AWS = f"""#!/bin/sh
printf '%s' '{TOKEN}'
"""
DOCKER = """#!/bin/sh
# Records where it was asked to store the login, what that config said, and its own arguments.
cat > "$LOG_DIR/stdin"
printf '%s\\n' "$DOCKER_CONFIG" > "$LOG_DIR/config_dir"
cp "$DOCKER_CONFIG/config.json" "$LOG_DIR/config_before"
printf '%s\\n' "$@" > "$LOG_DIR/argv"
echo "WARNING! Your credentials are stored unencrypted" >&2
[ -n "$FAIL" ] && { echo "denied" >&2; exit 1; }
exit 0
"""


class TestEcrLogin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.bin, self.log, self.home, self.work = t / "bin", t / "log", t / "home", t / "work"
        for d in (self.bin, self.log, self.home / ".docker" / "buildx", self.home / ".docker" / "contexts", self.work):
            d.mkdir(parents=True)
        (self.home / ".docker" / "config.json").write_text('{"credsStore": "desktop.exe"}')
        for name, body in (("aws", AWS), ("docker", DOCKER)):
            p = self.bin / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, fail=False):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.home), "LOG_DIR": str(self.log)}
        if fail:
            env["FAIL"] = "1"
        script = f'source "{ROOT}/scripts/ecr-login.sh"; ecr_login us-east-1 1.dkr.ecr.us-east-1.amazonaws.com "{self.work}"'
        return subprocess.run(["bash", "-c", "set -euo pipefail; " + script], env=env, capture_output=True, text=True)

    def test_a_throwaway_config_without_the_windows_store(self):
        r = self.login()
        self.assertEqual(r.returncode, 0, r.stderr)
        config_dir = Path((self.log / "config_dir").read_text().strip())
        self.assertEqual(config_dir, self.work / "docker-config")
        self.assertEqual(json.loads((self.log / "config_before").read_text()), {})
        self.assertEqual(oct(config_dir.stat().st_mode & 0o777), "0o700")
        # The builder and contexts still come from the usual config.
        self.assertTrue((config_dir / "buildx").is_symlink())
        self.assertTrue((config_dir / "contexts").is_symlink())
        # The usual config is untouched.
        self.assertEqual((self.home / ".docker" / "config.json").read_text(), '{"credsStore": "desktop.exe"}')

    def test_the_token_goes_through_stdin_only(self):
        self.login()
        self.assertEqual((self.log / "stdin").read_text(), TOKEN)
        self.assertNotIn(TOKEN, (self.log / "argv").read_text())
        self.assertIn("--password-stdin", (self.log / "argv").read_text())

    def test_the_unencrypted_warning_is_hidden_on_success(self):
        r = self.login()
        self.assertNotIn("WARNING", r.stderr)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)

    def test_a_failed_login_says_so(self):
        r = self.login(fail=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("denied", r.stderr)
        self.assertIn("docker login", r.stderr)
        self.assertNotIn(TOKEN, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
