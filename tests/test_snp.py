"""#253, #251 L21: SEV-SNP attestation reports in the node (oracle/snp.py): the guest driver's request, the report's
fields, the key provider ORACLE_KEYS=snp, and the v3 node taking its quotes as a TEE's. No SEV-SNP hardware here: the
ioctl is faked; validator-kit/SEVSNP-PLAN.md checks it on the real host."""

from __future__ import annotations

import ctypes
import os
import struct
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import snp, v3  # noqa: E402
from oracle.node_v3 import QUOTE_KINDS, _kind  # noqa: E402

KEY = "0x" + "11" * 32


def report(report_data=b"\x07" * 64, measurement=b"\x5a" * 48, tcb=(3, 0, 0, 0, 0, 0, 22, 213), signer=1,
           version=3) -> bytes:
    raw = bytearray(snp.REPORT_SIZE)
    struct.pack_into("<IIQ", raw, 0, version, 0, 0x30000)
    struct.pack_into("<II", raw, 0x30, 0, 1)
    struct.pack_into("<I", raw, 0x48, signer << 2)
    raw[0x50:0x90] = report_data
    raw[0x90:0xC0] = measurement
    raw[0x180:0x188] = bytes(tcb)
    raw[0x1A0:0x1E0] = b"\xc1" * 64
    return bytes(raw)


class Parse(unittest.TestCase):
    def test_fields(self):
        r = snp.parse(report())
        self.assertEqual((r.version, r.vmpl, r.signer, r.policy), (3, 0, "vlek", 0x30000))
        self.assertEqual((r.report_data, r.measurement), (b"\x07" * 64, b"\x5a" * 48))
        self.assertEqual(r.tcb(), {"boot_loader": 3, "tee": 0, "snp": 22, "microcode": 213})
        self.assertEqual(r.firmware(), (3 << 24) | (22 << 8) | 213)
        self.assertEqual(r.summary()["measurement"], "5a" * 48)
        self.assertEqual(snp.parse(report(signer=0)).signer, "vcek")

    def test_refusals(self):
        with self.assertRaises(ValueError):
            snp.parse(b"\x00" * 100)
        with self.assertRaises(ValueError):
            snp.parse(report(version=1))


class Request(unittest.TestCase):
    def test_the_ioctl_and_its_response(self):
        seen = {}

        def ioctl(fd, request, arg, mutate):
            seen["request"], seen["mutate"] = request, mutate
            version, req, resp = struct.unpack_from("<B7xQQ", arg, 0)
            seen["version"] = version
            seen["req"] = ctypes.string_at(req, 96)
            body = struct.pack("<II", 0, snp.REPORT_SIZE) + bytes(24) + report(seen["req"][:64])
            ctypes.memmove(resp, body, len(body))
            return 0

        with tempfile.NamedTemporaryFile() as dev:
            raw = snp.request_report(b"\x42" * 64, dev.name, ioctl=ioctl)
        self.assertEqual(seen["request"], 0xC0205300)  # _IOWR('S', 0, 32 bytes): linux/sev-guest.h's SNP_GET_REPORT
        self.assertEqual((seen["version"], seen["mutate"]), (1, True))
        self.assertEqual(seen["req"], b"\x42" * 64 + bytes(32))  # the data, VMPL 0, reserved
        self.assertEqual(snp.parse(raw).report_data, b"\x42" * 64)

    def test_the_extended_report_and_the_host_s_certificates(self):
        import uuid

        vlek, ask = b"\x30\x82vlek-der", b"\x30\x82ask-der"
        seen = {"calls": 0}

        def ioctl(fd, request, arg, mutate):
            seen["calls"] += 1
            self.assertEqual(request, 0xC0205302)  # SNP_GET_EXT_REPORT
            _, req, resp = struct.unpack_from("<B7xQQ", arg, 0)
            raw_req = ctypes.string_at(req, 112)
            certs_addr, certs_len = struct.unpack_from("<QI", raw_req, 96)
            self.assertEqual(certs_addr % 4096, 0)  # page-aligned, as the driver requires
            if certs_len < 5 * 4096:  # the host asks for more: the length comes back in the request
                ctypes.memmove(req + 104, struct.pack("<I", 5 * 4096), 4)
                struct.pack_into("<II", arg, 24, 0, snp.VMM_ERR_INVALID_LEN)
                raise OSError(22, "Invalid argument")
            # The GUIDs' bytes in the order their strings are written (the host's table; this test held them as
            # bytes_le until disk c7b72b70, the node's old reading)
            table = (uuid.UUID("a8074bc2-a25a-483e-aae6-39c045a0b8a1").bytes + struct.pack("<II", 200, len(vlek))
                     + uuid.UUID("4ab7b379-bbac-4fe4-a02f-05aef327c782").bytes + struct.pack("<II", 300, len(ask))
                     + bytes(24))
            blob = bytearray(certs_len)
            blob[:len(table)] = table
            blob[200:200 + len(vlek)] = vlek
            blob[300:300 + len(ask)] = ask
            ctypes.memmove(certs_addr, bytes(blob), len(blob))
            body = struct.pack("<II", 0, snp.REPORT_SIZE) + bytes(24) + report(raw_req[:64])
            ctypes.memmove(resp, body, len(body))
            return 0

        with tempfile.NamedTemporaryFile() as dev:
            raw, certs = snp.request_ext_report(b"\x42" * 64, dev.name, ioctl=ioctl)
        self.assertEqual(seen["calls"], 2)
        self.assertEqual(certs, {"vlek": vlek, "ask": ask})
        self.assertEqual(snp.parse(raw).report_data, b"\x42" * 64)

    def test_the_first_test_host_s_vlek_is_named_vlek(self):
        """The real host's table (2026-11-20, i-01ede2166387706db): its VLEK entry's 16 bytes are the ones the old node
        printed, read as bytes_le, as `c24b07a8-5aa2-3e48-aae6-39c045a0b8a1` (evidence/2026-11-20/console.txt). Read in
        the table's own order they are AWS's VLEK GUID, so the node now names the certificate `vlek`; an unknown entry
        keeps its GUID, in the same order."""
        import uuid

        host_bytes = uuid.UUID("c24b07a8-5aa2-3e48-aae6-39c045a0b8a1").bytes_le
        self.assertEqual(str(uuid.UUID(bytes=host_bytes)), "a8074bc2-a25a-483e-aae6-39c045a0b8a1")
        unknown = bytes(range(1, 17))
        vlek, other = b"\x30\x82vlek-der", b"\x30\x82other"
        table = (host_bytes + struct.pack("<II", 200, len(vlek)) + unknown + struct.pack("<II", 300, len(other))
                 + bytes(24))

        def ioctl(fd, request, arg, mutate):
            _, req, resp = struct.unpack_from("<B7xQQ", arg, 0)
            raw_req = ctypes.string_at(req, 112)
            certs_addr, certs_len = struct.unpack_from("<QI", raw_req, 96)
            blob = bytearray(certs_len)
            blob[:len(table)] = table
            blob[200:200 + len(vlek)] = vlek
            blob[300:300 + len(other)] = other
            ctypes.memmove(certs_addr, bytes(blob), len(blob))
            body = struct.pack("<II", 0, snp.REPORT_SIZE) + bytes(24) + report(raw_req[:64])
            ctypes.memmove(resp, body, len(body))
            return 0

        with tempfile.NamedTemporaryFile() as dev:
            _, certs = snp.request_ext_report(b"\x42" * 64, dev.name, ioctl=ioctl)
        self.assertEqual(certs, {"vlek": vlek, str(uuid.UUID(bytes=unknown)): other})
        self.assertNotIn("c24b07a8-5aa2-3e48-aae6-39c045a0b8a1", certs)

    def test_failures(self):
        def failing(fd, request, arg, mutate):
            struct.pack_into("<II", arg, 24, 0x16, 0)
            raise OSError(5, "Input/output error")

        with tempfile.NamedTemporaryFile() as dev:
            with self.assertRaisesRegex(RuntimeError, "firmware error 0x16"):
                snp.request_report(b"\x00" * 64, dev.name, ioctl=failing)
        with self.assertRaisesRegex(RuntimeError, "isn't an SEV-SNP guest"):
            snp.request_report(b"\x00" * 64, "/nonexistent/sev-guest")
        with self.assertRaises(ValueError):
            snp.request_report(b"\x00" * 10, "/dev/null")


class Keys(unittest.TestCase):
    def keys(self, **kw):
        return snp.SnpKeys({"ORACLE_PRIVATE_KEY": KEY}, request=lambda rd, dev: report(rd), **kw)

    def test_quotes_are_reports_over_the_padded_data(self):
        k = self.keys()
        q = k.quote(b"\x01\x02")
        self.assertEqual(q.kind, "amd-sev-snp")
        self.assertEqual(q.report_data, ("0102" + "00" * 62))
        self.assertEqual(snp.parse(bytes.fromhex(q.quote)).report_data.hex(), q.report_data)

    def test_chains(self):
        k = self.keys()
        for ok in (31337, 7193, 11_155_111):
            k.check_chain(ok)
        with self.assertRaisesRegex(RuntimeError, "refused on chain 1"):
            k.check_chain(1)

    def test_the_device_is_configurable(self):
        k = snp.SnpKeys({"ORACLE_PRIVATE_KEY": KEY, "ORACLE_SNP_DEVICE": "/dev/x"})
        self.assertEqual(k.device, "/dev/x")

    def test_the_v3_node_takes_them_as_a_tee_s(self):
        k = self.keys()
        self.assertIn(_kind(k), QUOTE_KINDS[v3.PROOF_TEE])
        self.assertIn("dstack-tdx", QUOTE_KINDS[v3.PROOF_TEE])  # unchanged
        self.assertNotIn("amd-sev-snp", QUOTE_KINDS[v3.PROOF_SIMULATED])

    def test_chosen_by_oracle_keys(self):
        from oracle import __main__ as cli

        with unittest.mock.patch.dict(os.environ, {"ORACLE_KEYS": "snp", "ORACLE_PRIVATE_KEY": KEY}):
            self.assertIsInstance(cli.keys_from_env(7193, "0x" + "00" * 20), snp.SnpKeys)


class Secrets(unittest.TestCase):
    """The kit's node reads its own secrets (no AWS CLI on the measured disk): oracle/awssecret.py."""

    ARN = "arn:aws:secretsmanager:us-east-2:123456789012:secret:pof-snp/signing-key-AbCdEf"

    def test_get_secret_value_signed_in_the_secret_s_region(self):
        import json

        from oracle import awssecret
        from oracle.models import AwsCredentials, Reply

        seen = {}

        def request(method, url, headers, body, timeout):
            seen.update(method=method, url=url, headers=headers, body=json.loads(body))
            return Reply(200, {}, json.dumps({"SecretString": KEY + "\n"}).encode())

        env = {"ORACLE_PRIVATE_KEY_SECRET_ARN": self.ARN, "RPC_API_KEY": "already"}
        done = awssecret.resolve(env, request, lambda: AwsCredentials("AKIA", "s", "tok"))
        self.assertEqual((done, env["ORACLE_PRIVATE_KEY"], env["RPC_API_KEY"]), (["ORACLE_PRIVATE_KEY"], KEY, "already"))
        self.assertEqual(seen["url"], "https://secretsmanager.us-east-2.amazonaws.com/")
        self.assertEqual(seen["headers"]["X-Amz-Target"], "secretsmanager.GetSecretValue")
        self.assertIn("/us-east-2/secretsmanager/aws4_request", seen["headers"]["Authorization"])
        self.assertEqual(seen["body"], {"SecretId": self.ARN})

    def test_refusals_never_hold_the_value(self):
        from oracle import awssecret
        from oracle.models import AwsCredentials, Reply

        def denied(*a):
            return Reply(400, {}, b'{"__type":"com.amazonaws#AccessDeniedException"}')

        with self.assertRaisesRegex(awssecret.SecretError, "HTTP 400 AccessDeniedException"):
            awssecret.get_secret(self.ARN, denied, lambda: AwsCredentials("a", "b"))
        with self.assertRaisesRegex(awssecret.SecretError, "not a Secrets Manager ARN"):
            awssecret.get_secret("arn:aws:s3:::bucket", denied, lambda: AwsCredentials("a", "b"))


if __name__ == "__main__":
    unittest.main()
