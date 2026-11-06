"""Task 1.9 (proof-of-fix#135): a recorded zkTLS proof of a model call, checked offline.

The proofs in experiments/zktls/proofs come from real runs (experiments/zktls/run_spike.py): one small call to a
model on AWS Bedrock, proven with TLSNotary (tlsn v0.1.0-alpha.15) and attested by our own notary on 127.0.0.1.
These tests need no network, no Rust and no credentials: they redo the receipt's checks in pure Python with the
repository's vendored keccak-256 and secp256k1 (experiments/zktls/receipt_check.py): the notary's signature as a
contract would check it (ecrecover), the Merkle root of the signed body, the TLS version, and every revealed byte
against its signed hash commitment. They also check that the credentials were hidden.

What only the Rust verifier checks is the server's certificate chain (that the bytes came from Bedrock's server).
test_rust_verifier_agrees runs it when the pinned build is present and skips otherwise (as on the CI host)."""

import copy
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPIKE = ROOT / "experiments" / "zktls"
PROOFS = SPIKE / "proofs"
sys.path.insert(0, str(SPIKE))

import receipt_check  # noqa: E402

RECORDED = "call-self-a-mpc-claude-haiku-4.5-2"  # the first attempt failed its signature (see the report)
NOTARY_A = "0xCA5064d5dA7A391f1FEd7dAbE591d502B59d7944"  # notary A's address, from its public key
HOST = "bedrock-runtime.us-east-1.amazonaws.com"
# Access key ids, a signed Authorization value, an STS session token ("IQoJb3JpZ2lu..." or "FwoGZXIvYXdz...") or a token
# quoted after its header name (Bedrock's signature error quotes it).
CREDENTIAL = re.compile(rb"(AKIA|ASIA)[A-Z0-9]{12,}|AWS4-HMAC-SHA256 Credential|Signature=[0-9a-f]{16}|aws_secret"
                        rb"|IQoJb3JpZ2lu|FwoGZXIvYXdz|x-amz-security-token\s*[:=]\s*[A-Za-z0-9+/=]{16}", re.IGNORECASE)
RUST_VERIFIER = Path(os.environ.get("POF_ZKTLS_VERIFY", "~/pof-135-build/target/release/examples/pof_verify")).expanduser()


def load(name=RECORDED):
    return json.loads((PROOFS / f"{name}.receipt.json").read_text())


class TestRecordedReceipt(unittest.TestCase):
    def setUp(self):
        self.receipt = load()
        self.out = receipt_check.check(self.receipt)

    def test_signed_by_notary_a_over_tls_1_2(self):
        self.assertEqual(self.out["notary"], NOTARY_A)
        self.assertEqual(self.out["tls_version"], "V1_2")
        self.assertEqual(self.receipt["server_name"], HOST)

    def test_reveals_the_request_and_the_answer(self):
        sent, recv = self.out["sent"], self.out["recv"]
        self.assertTrue(sent.startswith(b"POST /model/us.anthropic.claude-haiku-4-5-20251001-v1%3A0/converse HTTP/1.1"))
        self.assertIn(b"Host: " + HOST.encode(), sent)
        body = json.loads(sent.split(b"\r\n\r\n", 1)[1])
        self.assertEqual(body["inferenceConfig"]["maxTokens"], 20)
        self.assertEqual(self.out["recv_revealed"], len(recv))  # the whole answer
        self.assertTrue(recv.startswith(b"HTTP/1.1 200 OK"))
        answer = json.loads(recv.split(b"\r\n\r\n", 1)[1])
        self.assertGreater(answer["usage"]["outputTokens"], 0)
        self.assertLessEqual(answer["usage"]["outputTokens"], 20)
        self.assertTrue(answer["output"]["message"]["content"][0]["text"])

    def test_the_credentials_are_hidden(self):
        sent = self.out["sent"]
        authed = {i for a, b in self.receipt["sent"]["authed"] for i in range(a, b)}
        for name in (b"Authorization: ", b"X-Amz-Security-Token: "):
            at = sent.index(name) + len(name)
            end = sent.index(b"\r\n", at)
            self.assertGreater(end - at, 20)
            self.assertFalse(authed & set(range(at, end)), name)  # not one byte of the value is revealed
            self.assertEqual(sent[at:end], b"\0" * (end - at))
        self.assertEqual(self.out["sent_revealed"], len(sent) - sum(
            sent.index(b"\r\n", sent.index(n) + len(n)) - sent.index(n) - len(n)
            for n in (b"Authorization: ", b"X-Amz-Security-Token: ")))


class TestTampering(unittest.TestCase):
    def setUp(self):
        self.receipt = load()

    def assertRejected(self, receipt):
        with self.assertRaises(receipt_check.ReceiptError):
            receipt_check.check(receipt)

    def flip(self, hexstr, at):
        b = bytearray(bytes.fromhex(hexstr))
        b[at] ^= 1
        return b.hex()

    def test_a_changed_answer_fails_its_commitment(self):
        r = copy.deepcopy(self.receipt)
        recv = bytes.fromhex(r["recv"]["bytes"])
        r["recv"]["bytes"] = self.flip(r["recv"]["bytes"], recv.index(b'"text"') + 9)
        self.assertRejected(r)

    def test_a_changed_header_fails_the_signature(self):
        r = copy.deepcopy(self.receipt)
        r["header_bcs"] = self.flip(r["header_bcs"], 3)
        self.assertRejected(r)

    def test_a_changed_body_fails_the_root(self):
        r = copy.deepcopy(self.receipt)
        r["body_bcs"] = self.flip(r["body_bcs"], 43)  # the connection info's time (its first byte)
        self.assertRejected(r)

    def test_another_notary_key_fails(self):
        r = copy.deepcopy(self.receipt)
        r["notary_key"]["sec1"] = load("call-self-b-mpc-claude-haiku-4.5")["notary_key"]["sec1"]
        self.assertRejected(r)

    def test_a_hidden_byte_claimed_as_revealed_fails(self):
        r = copy.deepcopy(self.receipt)
        a, b = r["sent"]["authed"][0]
        r["sent"]["authed"][0] = [a, b + 1]
        self.assertRejected(r)

    def test_a_hidden_byte_filled_in_fails(self):
        r = copy.deepcopy(self.receipt)
        sent = bytearray(bytes.fromhex(r["sent"]["bytes"]))
        sent[r["sent"]["authed"][0][1]] = ord("A")
        r["sent"]["bytes"] = sent.hex()
        self.assertRejected(r)


class TestEveryRecordedProof(unittest.TestCase):
    def test_every_receipt_checks_and_hides_the_credentials(self):
        receipts = sorted(PROOFS.glob("*.receipt.json"))
        self.assertGreaterEqual(len(receipts), 4)
        notaries = set()
        for path in receipts:
            with self.subTest(path.name):
                out = receipt_check.check(json.loads(path.read_text()))
                notaries.add(out["notary"])
                self.assertEqual(out["tls_version"], "V1_2")
                self.assertNotIn(b"AWS4-HMAC-SHA256", out["sent"])
        self.assertEqual(len(notaries), 2)  # notary A and notary B, two keys

    def test_nothing_recorded_looks_like_a_credential(self):
        recorded = sorted(PROOFS.glob("*")) + sorted((SPIKE / "results").glob("*"))
        self.assertTrue(recorded)
        for path in recorded:
            if path.is_file():
                with self.subTest(str(path.relative_to(ROOT))):
                    self.assertIsNone(CREDENTIAL.search(path.read_bytes()))


class TestRustVerifier(unittest.TestCase):
    @unittest.skipUnless(RUST_VERIFIER.exists(), "needs the pinned Rust verifier (tlsn v0.1.0-alpha.15, "
                         "experiments/zktls/build.sh); the CI host has no Rust, so the pure-Python checks stand alone")
    def test_rust_verifier_agrees(self):
        for path in sorted(PROOFS.glob("*.presentation.tlsn")):
            with self.subTest(path.name):
                p = subprocess.run([str(RUST_VERIFIER), str(path), "--expect-server", HOST],
                                   capture_output=True, text=True, timeout=60)
                self.assertEqual(p.returncode, 0, p.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
