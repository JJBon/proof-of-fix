"""The integration suite's targets (proof-of-fix#152): which target and scenarios run, the AWS profile's settings and its
refusals, the delta assertions, the books and the secrets' redaction. No Docker, no AWS: the one network exchange is with
a fake RPC on the loopback that answers the wrong chain ID."""

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from targets import (DEVNET_CHAIN_ID, LOCAL_ONLY, Refused, RedactingStream, Secrets, aws_settings,  # noqa: E402
                     check_books, check_chain, check_withdrawal, deltas, expect_deltas, plan, split_target)

AUTH = "sandbox-validator:" + "ab" * 32
TOKEN = "f0" * 20
KEY = "0x" + "cd" * 32
GOOD = {"DEVNET_RPC_URL": "https://devnet.example", "DEVNET_RPC_AUTH": AUTH, "FIRST_BOUNTY_TOKEN": TOKEN,
        "FIRST_BOUNTY_USER": "maintainer"}


class TestTarget(unittest.TestCase):
    def test_the_local_devnet_is_the_default(self):
        self.assertEqual(split_target(["--only", "2"]), ("local", ["--only", "2"]))

    def test_aws_is_picked_either_way(self):
        self.assertEqual(split_target(["--target", "aws", "--preflight"]), ("aws", ["--preflight"]))
        self.assertEqual(split_target(["--preflight", "--target=aws"]), ("aws", ["--preflight"]))

    def test_an_unknown_or_missing_target_is_refused(self):
        with self.assertRaisesRegex(Refused, "unknown target"):
            split_target(["--target", "mainnet"])
        with self.assertRaisesRegex(Refused, "needs a name"):
            split_target(["--target"])


class TestPlan(unittest.TestCase):
    def test_local_runs_every_scenario(self):
        self.assertEqual(plan("local"), (list("12345678"), []))

    def test_aws_runs_what_the_shared_devnet_allows_and_says_why_not_the_rest(self):
        run, skipped = plan("aws")
        self.assertEqual(run, ["2", "3", "1", "5"])  # no merge first, then the merges
        self.assertEqual([s for s, _ in skipped], ["4", "6", "7", "8"])
        for s, why in skipped:
            self.assertEqual(why, LOCAL_ONLY[s])
            self.assertTrue(why)

    def test_only_narrows_both_lists(self):
        self.assertEqual(plan("aws", "2,4"), (["2"], [("4", LOCAL_ONLY["4"])]))
        self.assertEqual(plan("local", "3,2"), (["2", "3"], []))

    def test_an_unknown_scenario_is_refused(self):
        with self.assertRaisesRegex(Refused, "no scenario 9"):
            plan("aws", "1,9")


class TestAwsSettings(unittest.TestCase):
    def refused(self, env, says):
        with self.assertRaises(Refused) as c:
            aws_settings(env)
        self.assertIn(says, str(c.exception))
        for secret in (AUTH, "ab" * 32, TOKEN, KEY):
            self.assertNotIn(secret, str(c.exception))

    def test_the_defaults(self):
        s = aws_settings(GOOD)
        self.assertEqual((s.repo, s.forge, s.record, s.exchange_url),
                         ("example-org/pof-sandbox", "https://git.example.com",
                          "contracts/deployments/devnet-aws-v2.json", "https://devnet.example/exchange"))
        self.assertFalse(s.insecure_local)
        self.assertEqual(s.engineer_key, "")

    def test_no_secret_in_the_settings_repr(self):
        s = aws_settings({**GOOD, "POFCTL_KEY_ENGINEER": KEY, "DEVNET_REPO_TOKEN": "e1" * 20})
        for secret in (AUTH, TOKEN, KEY, "e1" * 20):
            self.assertNotIn(secret, repr(s))
        self.assertEqual(set(s.secrets()), {"the RPC credential", "the repository token", "the read-only token",
                                            "seat 6's key"})

    def test_each_missing_setting_is_named(self):
        self.refused({k: v for k, v in GOOD.items() if k != "DEVNET_RPC_URL"}, "DEVNET_RPC_URL")
        self.refused({k: v for k, v in GOOD.items() if k != "DEVNET_RPC_AUTH"}, "DEVNET_RPC_AUTH")
        self.refused({k: v for k, v in GOOD.items() if k != "FIRST_BOUNTY_TOKEN"}, "FIRST_BOUNTY_TOKEN")
        self.refused({k: v for k, v in GOOD.items() if k != "FIRST_BOUNTY_USER"}, "FIRST_BOUNTY_USER")

    def test_a_credential_in_the_url_is_refused(self):
        self.refused({**GOOD, "DEVNET_RPC_URL": f"https://{AUTH}@devnet.example"}, "without a credential")

    def test_plain_http_only_for_a_local_test_proxy(self):
        self.refused({**GOOD, "DEVNET_RPC_URL": "http://devnet.example"}, "plain HTTP")
        s = aws_settings({**GOOD, "DEVNET_RPC_URL": "http://127.0.0.1:8558", "DEVNET_RPC_ALLOW_HTTP": "1"})
        self.assertEqual(s.rpc_url, "http://127.0.0.1:8558")

    def test_anvils_public_keys_never_on_a_real_endpoint(self):
        self.refused({**GOOD, "DEVNET_KEYS": "insecure-local"}, "public keys")
        self.refused({**GOOD, "DEVNET_KEYS": "env"}, "OpenBao")

    def test_a_malformed_credential_or_key_is_refused_without_printing_it(self):
        self.refused({**GOOD, "DEVNET_RPC_AUTH": "ab" * 32}, "<handle>:<key>")
        self.refused({**GOOD, "POFCTL_KEY_ENGINEER": KEY[:-2]}, "32-byte hex")

    def test_files_instead_of_values(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "auth").write_text(AUTH + "\n", encoding="utf-8")
            (Path(d) / "token").write_text(f" {TOKEN}\r\n", encoding="utf-8")  # a paste brings line endings along
            env = {**GOOD, "DEVNET_RPC_AUTH_FILE": f"{d}/auth", "FIRST_BOUNTY_TOKEN_FILE": f"{d}/token"}
            del env["DEVNET_RPC_AUTH"], env["FIRST_BOUNTY_TOKEN"]
            s = aws_settings(env)
            self.assertEqual((s.auth, s.token), (AUTH, TOKEN))
            self.refused({**env, "DEVNET_RPC_AUTH_FILE": f"{d}/nothing"}, "can't read DEVNET_RPC_AUTH_FILE")


class TestChain(unittest.TestCase):
    RECORD = {"chainId": DEVNET_CHAIN_ID, "version": "2"}

    def test_the_devnet_passes(self):
        check_chain(7193, self.RECORD)

    def test_any_other_chain_is_refused(self):
        for cid in (1, 11155111, 31337, 8453):
            with self.assertRaisesRegex(Refused, "rule 1"):
                check_chain(cid, self.RECORD)

    def test_a_record_of_another_chain_is_refused(self):
        with self.assertRaisesRegex(Refused, "record is for chain 31337"):
            check_chain(7193, {**self.RECORD, "chainId": 31337})
        with self.assertRaisesRegex(Refused, "v2"):
            check_chain(7193, {**self.RECORD, "version": "1"})


class TestDeltas(unittest.TestCase):
    def test_deltas(self):
        self.assertEqual(deltas({"a": 5, "b": 1}, {"a": 3, "c": 2}), {"a": -2, "b": -1, "c": 2})

    def test_only_the_expected_names_are_held_to_it(self):
        before, after = {"funder": 1_000, "solver": 50}, {"funder": 900, "solver": 75}
        self.assertEqual(expect_deltas("fund", before, after, {"funder": -100}), [])
        self.assertEqual(expect_deltas("fund", before, after, {"funder": -99}),
                         ["fund: funder moved -100, expected -99"])

    def test_absolute_values_dont_matter(self):  # a shared chain: earlier runs left balances behind
        self.assertEqual(expect_deltas("x", {"a": 10**12}, {"a": 10**12 - 5}, {"a": -5}), [])

    def test_a_withdrawal_pays_the_whole_credit(self):
        self.assertEqual(check_withdrawal("oracle-0", 142_861, 10, 0, 142_871), [])
        self.assertEqual(len(check_withdrawal("oracle-0", 142_861, 10, 1, 142_870)), 2)


class TestBooks(unittest.TestCase):
    SEATS = ["s0", "s1", "s2"]

    def owed(self, changes):
        return lambda block, who: changes.get((block, who), 0)

    def test_balanced_books(self):
        subs = {7: {"solver": "A", "deposit": 1_000}, 8: {"solver": "B", "deposit": 1_000}}
        decided = {100: [7, 8], 105: [9]}  # 9: someone else's, in a block of its own
        charged = {7: (3, 300), 8: (2, 200), 9: (3, 999)}
        changes = {(100, "A"): 700, (100, "B"): 800, (100, "s0"): 250, (100, "s1"): 250}
        self.assertEqual(check_books(subs, decided, charged, self.owed(changes), self.SEATS), [])

    def test_a_deposit_that_doesnt_add_up(self):
        subs = {7: {"solver": "A", "deposit": 1_000}}
        changes = {(100, "A"): 650, (100, "s0"): 300}
        problems = check_books(subs, {100: [7]}, {7: (3, 300)}, self.owed(changes), self.SEATS)
        self.assertEqual(problems, ["block 100: submission(s) [7]: deposits 1000 != charged 300 + returned 650"])

    def test_seats_credited_other_than_charged(self):
        subs = {7: {"solver": "A", "deposit": 1_000}}
        changes = {(100, "A"): 700, (100, "s0"): 299}
        problems = check_books(subs, {100: [7]}, {7: (3, 300)}, self.owed(changes), self.SEATS)
        self.assertEqual(problems, ["block 100: the meter charged 300, the seats were credited 299"])

    def test_another_runs_result_in_the_same_block_counts_for_the_seats(self):
        subs = {7: {"solver": "A", "deposit": 1_000}}
        changes = {(100, "A"): 700, (100, "s0"): 500}
        self.assertEqual(check_books(subs, {100: [7, 9]}, {7: (3, 300), 9: (2, 200)}, self.owed(changes), self.SEATS),
                         [])


class TestSecrets(unittest.TestCase):
    def secrets(self):
        s = Secrets()
        s.add("the RPC credential", AUTH)
        s.add("the repository token", TOKEN, user="maintainer")
        s.add("seat 6's key", KEY)
        s.add("short", "abc")  # too short to look for
        return s

    def test_every_form_is_found_and_only_its_label_is_said(self):
        import base64
        s = self.secrets()
        for text, label in ((f"x {AUTH} y", "the RPC credential"), ("ab" * 32, "the RPC credential"),
                            (base64.b64encode(AUTH.encode()).decode(), "the RPC credential"),
                            (base64.b64encode(f"maintainer:{TOKEN}".encode()).decode(), "the repository token"),
                            (KEY[2:].upper(), "seat 6's key"), (KEY, "seat 6's key")):
            self.assertEqual(s.leaks(text), [label], text)
        self.assertEqual(s.leaks("nothing here, abc"), [])

    def test_redact(self):
        s = self.secrets()
        self.assertEqual(s.redact(f"auth {AUTH} key {KEY}"), "auth *** key ***")

    def test_the_stream_redacts_and_remembers(self):
        out = io.StringIO()
        stream = RedactingStream(out, self.secrets())
        stream.write("one line\n")
        stream.write(f"half {TOKEN[:10]}")
        stream.write(f"{TOKEN[10:]} end\n")  # split across writes
        stream.flush()
        self.assertEqual(out.getvalue(), "one line\nhalf *** end\n")
        self.assertEqual(stream.caught, {"the repository token"})


class FakeChain(BaseHTTPRequestHandler):
    """An RPC on the loopback that answers chain 1 (mainnet's ID) and records the methods it was asked."""
    calls: list = []

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeChain.calls.append((body["method"], self.headers.get("Authorization", "")))
        answer = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": "0x1"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, *a):
        pass


class TestScript(unittest.TestCase):
    """scripts/integration.sh --target aws: refusals before anything is sent, without Docker (a `docker` and a `bao` that
    fail the test stand first on the PATH)."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.bin = Path(self.dir.name)
        for tool in ("docker", "bao"):
            shim = self.bin / tool
            shim.write_text(f'#!/bin/sh\ntouch "{self.bin}/ran-{tool}"\nexit 99\n', encoding="utf-8")
            shim.chmod(shim.stat().st_mode | stat.S_IXUSR)

    def run_script(self, *args, script="scripts/integration.sh", **env):
        base = {k: v for k, v in os.environ.items()
                if not k.startswith(("DEVNET_", "FIRST_BOUNTY_", "POFCTL_", "FORGEJO_"))}
        cmd = ["bash", str(ROOT / script)] if script.endswith(".sh") else [sys.executable, str(ROOT / script)]
        return subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=60, cwd=ROOT,
                              env={**base, "PATH": f"{self.bin}:{base['PATH']}", **env})

    def assert_refused(self, r, says):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn(says, r.stderr)
        for secret in (AUTH, "ab" * 32, TOKEN):
            self.assertNotIn(secret, r.stdout + r.stderr)
        self.assertFalse((self.bin / "ran-docker").exists(), "it reached docker")
        self.assertFalse((self.bin / "ran-bao").exists(), "it read a key before refusing")

    def test_no_settings(self):
        self.assert_refused(self.run_script("--target", "aws", "--preflight"), "set DEVNET_RPC_URL")

    def test_a_credential_in_the_url(self):
        self.assert_refused(self.run_script("--target", "aws", **{**GOOD, "DEVNET_RPC_URL": f"https://{AUTH}@x.example"}),
                            "without a credential")

    def test_suite_py_hands_the_aws_target_over(self):
        self.assert_refused(self.run_script("--target", "aws", script="tests/integration/suite.py"), "DEVNET_RPC_URL")

    def test_a_wrong_chain_id_is_refused_before_any_key_is_read(self):
        FakeChain.calls = []
        server = HTTPServer(("127.0.0.1", 0), FakeChain)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        record = self.bin / "record.json"
        record.write_text(json.dumps({"chainId": 7193, "version": "2", "race": "0x" + "11" * 20}), encoding="utf-8")
        url = f"http://127.0.0.1:{server.server_port}"
        r = self.run_script("--target", "aws", "--preflight", **{**GOOD, "DEVNET_RPC_URL": url,
                                                                 "DEVNET_RPC_ALLOW_HTTP": "1",
                                                                 "DEVNET_RECORD_V2": str(record)})
        self.assert_refused(r, "answers chain 1, not the devnet's 7193 (rule 1")
        self.assertEqual([m for m, _ in FakeChain.calls], ["eth_chainId"])  # nothing else asked, nothing sent
        self.assertTrue(FakeChain.calls[0][1].startswith("Basic "), "the credential goes in a header")


if __name__ == "__main__":
    unittest.main()
