"""The Sepolia genesis validator's plan fields and signature (proof-of-fix#251 task 7.1; scripts/genesis_validator.py),
without AWS, Docker or a network: the fields from the real SEV-SNP host's attested boot of 2026-11-22
(validator-kit/sevsnp/evidence/2026-11-22), the registry's address and GENESIS_DIGEST as DeploySepolia.s.sol computes
them, the signature the deploy's own `--genesis-dev-key` path would make, refusals on malformed input, and the key
never in stdout, stderr or a file. The secret is a fake here (`main(..., source=…)`), and the Secrets Manager calls
are checked against a fake runner and a fake HTTP request. scripts/deploy-sepolia-e2e.sh (scenario 4) signs with this
tool for a dry run on an anvil with chain id 11155111."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "validator-kit" / "sevsnp" / "evidence" / "2026-11-22"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("genesis_validator_under_test", ROOT / "scripts" / "genesis_validator.py")
gv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gv)

from oracle import crypto, node_v3, v3  # noqa: E402
from oracle.keys import Quote  # noqa: E402
from oracle.models import Reply  # noqa: E402
from pofctl.keys import MNEMONIC, derive  # noqa: E402

DEPLOYER = crypto.address(derive(MNEMONIC, 0))  # anvil's public key 0
KEY = derive(MNEMONIC, 1)  # anvil's public key 1 as the genesis validator's (a test key: public)
KEY_ADDR = crypto.address(KEY)
RAD = bytes(range(1, 33))
RAD_DID = gv.did_from_key(RAD)
IMAGE = "0x34cc24150088013c0d0e482998b153dd745168d3cd4877c7ead67e12e198ca6b"  # the 51c96e70 disk's image digest
ATTESTATION = "0x4cf4bce748f779208ae32891cd2b49ce788c3ed137f305cc78c5d05fa1bc2522"  # keccak256(report.bin)
NID_DID = "did:key:z6MkndSSawVcJAPRY96cRcTzG5mBTM46fhgXYb8jMwFdBEG8"  # the host's POF-RADICLE nid
LIBS = 3  # Panels' linked libraries, deployed by forge from the deployer before the script's creations
# What the deploy's dry run printed on a fresh anvil with chain id 11155111 and anvil's key 0 as the deployer
# (scripts/deploy-sepolia-e2e.sh, 2026-11-22): GENESIS_REGISTRY, after the three libraries
FORGE_REGISTRY = "0x61c36a8d610163660E21a8b7359e1Cac0C9133e1"
ARN = "arn:aws:secretsmanager:us-east-2:123456789012:secret:pof-sevsnp/signing-key-AbCdEf"


def key_forms(k: int) -> list:
    h = f"{k:064x}"
    return [h, h.upper(), "0x" + h, str(k)]


class FakeSecret:
    """The secret, in memory: `read()` its value (None when empty), `write(value)`."""

    def __init__(self, value=None):
        self.value, self.writes = value, 0

    def read(self):
        return self.value

    def write(self, value):
        self.value, self.writes = value, self.writes + 1


def run(argv, source=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = gv.main(argv, source=source)
    return code, out.getvalue(), err.getvalue()


class Work(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gv-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for name in ("console.txt", "manifest.json", "verify.json"):
            shutil.copy(EVIDENCE / name, self.tmp / name)
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps({"rid": "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5", "genesisHead": "1" * 40,
                                         "families": ["anthropic.claude"], "teeTypes": ["amd-sev-snp"],
                                         "images": [IMAGE]}), encoding="utf-8")

    def fields_args(self, *extra):
        return ["fields", "--plan", str(self.plan), "--console", str(self.tmp / "console.txt"),
                "--manifest", str(self.tmp / "manifest.json"), "--verify", str(self.tmp / "verify.json"), *extra]

    def assert_no_key(self, k: int, *texts):
        for t in texts:
            for form in key_forms(k)[:3]:
                self.assertNotIn(form.lower(), t.lower())
        for f in self.tmp.rglob("*"):
            if f.is_file():
                data = f.read_bytes().lower()
                for form in key_forms(k)[:3]:
                    self.assertNotIn(form.lower().encode(), data, f"the key is in {f.name}")


class TheAddresses(unittest.TestCase):
    def test_create_addresses_match_known_vectors(self):
        # anvil's deployer's first two creations, as every Foundry user sees them
        self.assertEqual(gv.create_address(DEPLOYER, 0), "0x5FbDB2315678afecb367f032d93F642f64180aa3")
        self.assertEqual(gv.create_address(DEPLOYER, 1), "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512")

    def test_registry_is_the_makers_first_creation_after_two(self):
        maker = gv.create_address(DEPLOYER, 2)
        self.assertEqual(gv.registry_address(DEPLOYER, 0), gv.create_address(maker, 1))
        self.assertNotEqual(gv.registry_address(DEPLOYER, 0), gv.registry_address(DEPLOYER, 1))

    def test_forge_deploys_the_libraries_first(self):
        """Forge deploys Panels' linked libraries from the deployer (through the CREATE2 deployer) before the script
        runs, so the script's nonce is the deployer's plus the libraries: the registry a fresh anvil printed."""
        self.assertEqual(gv.registry_address(DEPLOYER, LIBS), FORGE_REGISTRY)
        found = set()
        for f in sorted((ROOT / "contracts" / "src" / "v3").glob("*.sol")):
            s = f.read_text(encoding="utf-8")
            for m in re.finditer(r"^library\s+(\w+)\s*\{", s, re.M):
                rest = s[m.end():]
                end = re.search(r"^(contract|abstract contract|interface|library)\s", rest, re.M)
                body = rest[:end.start()] if end else rest
                if re.search(r"function\s+\w+\s*\([^)]*\)[^{;]*?\b(external|public)\b", body, re.S):
                    found.add(m.group(1))
        self.assertEqual(found, set(gv.LINKED_LIBRARIES))  # a library with external functions is linked, deployed
        self.assertEqual(len(gv.LINKED_LIBRARIES), LIBS)

    def test_the_libraries_and_nonce_options(self):
        code, out, _ = run(["binding", "--deployer", DEPLOYER, "--key-address", KEY_ADDR, "--libraries", "0"])
        self.assertEqual((code, json.loads(out)["registry"]), (0, gv.registry_address(DEPLOYER, 0)))
        code, out, _ = run(["binding", "--deployer", DEPLOYER, "--key-address", KEY_ADDR, "--deployer-nonce", "2"])
        self.assertEqual((code, json.loads(out)["registry"]), (0, gv.registry_address(DEPLOYER, 2 + LIBS)))
        for bad in (["--libraries", "4"], ["--libraries", "-1"], ["--deployer-nonce", "-1"]):
            code, _, err = run(["binding", "--deployer", DEPLOYER, "--key-address", KEY_ADDR, *bad])
            self.assertEqual(code, 2, bad)
            self.assertIn("--deployer-nonce", err)

    def test_the_script_computes_the_registry_this_way(self):
        sol = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")
        self.assertIn("vm.computeCreateAddress(p.deployer, nonce + 2)", sol)
        self.assertIn("vm.computeCreateAddress(makerAt, 1)", sol)


class TheBinding(unittest.TestCase):
    def test_boot_nonce_is_what_the_nodes_register_quotes(self):
        """The binding is the report data the node's own `register` asks its SEV-SNP guest for."""
        registry = gv.registry_address(DEPLOYER, 0)
        seen = {}

        class Chain:
            def domain(self):
                return v3.registry_domain(gv.ds.SEPOLIA, registry)

        class Keys:
            def address(self):
                return KEY_ADDR

            def quote(self, data):
                seen["data"] = data
                return Quote("amd-sev-snp", "ab" * 10, data.hex())

        r, _ = node_v3.registration(Chain(), Keys(), proof="tee", family="f", host="h", image=b"\1" * 32,
                                    tee_type="amd-sev-snp")
        self.assertEqual(seen["data"].hex(), gv.boot_nonce(gv.ds.SEPOLIA, registry, KEY_ADDR))
        self.assertEqual(gv.REGISTRATION_NOTE, node_v3.REGISTRATION_NOTE)
        self.assertEqual(r.attestation, crypto.keccak256(bytes.fromhex("ab" * 10)))  # the quote's keccak256

    def test_binding_command_prints_registry_and_nonce(self):
        code, out, _ = run(["binding", "--deployer", DEPLOYER, "--key-address", KEY_ADDR])
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["registry"], gv.registry_address(DEPLOYER, LIBS))
        self.assertEqual(doc["attestNonce"], gv.boot_nonce(11_155_111, doc["registry"], KEY_ADDR))
        self.assertRegex(doc["attestNonce"], r"^[0-9a-f]{64}$")  # the kit's attest_nonce: lowercase hex, <= 64 bytes

    def test_binding_reads_the_address_from_the_secret_only(self):
        code, out, err = run(["binding", "--deployer", DEPLOYER], source=FakeSecret(f"{KEY:064x}"))
        self.assertEqual((code, json.loads(out)["key"]), (0, KEY_ADDR))
        for form in key_forms(KEY)[:3]:
            self.assertNotIn(form, out + err)


class TheFields(Work):
    def test_fields_from_the_real_attested_boot(self):
        code, out, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 0, err)
        g = json.loads(self.plan.read_text())["genesisValidator"]
        self.assertEqual(g, {"key": KEY_ADDR, "operator": KEY_ADDR, "teeType": "amd-sev-snp", "level": 1,
                             "attestation": ATTESTATION, "image": IMAGE,
                             "host": "0x" + crypto.keccak256(b"aws:us-east-2").hex(), "firmware": 67117025})
        self.assertEqual(ATTESTATION[2:], crypto.keccak256((EVIDENCE / "report.bin").read_bytes()).hex())
        self.assertEqual(json.loads(out)["genesisRadNode"], NID_DID)
        self.assertIn(f"--genesis-rad-node {NID_DID}", err)
        plan = json.loads(self.plan.read_text())
        self.assertEqual((plan["teeTypes"], plan["images"]), (["amd-sev-snp"], [IMAGE]))  # already there: unchanged

    def test_firmware_is_the_reports_tcb(self):
        from oracle import snp

        rep = snp.parse((EVIDENCE / "report.bin").read_bytes())
        self.assertEqual(rep.firmware(), 67117025)
        self.assertIn('"firmware": 67117025', (EVIDENCE / "console.txt").read_text(errors="replace"))

    def test_operator_level_host_and_a_new_plan(self):
        self.plan.unlink()
        op = "0x" + "55" * 20
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound", "--operator", op, "--level", "B",
                                            "--host", "aws:us-east-2b"))
        self.assertEqual(code, 0, err)
        plan = json.loads(self.plan.read_text())
        g = plan["genesisValidator"]
        self.assertEqual((g["operator"], g["level"], g["host"]),
                         (crypto.checksum(op), 2, "0x" + crypto.keccak256(b"aws:us-east-2b").hex()))
        self.assertEqual((plan["teeTypes"], plan["images"]), (["amd-sev-snp"], [IMAGE]))

    def test_key_address_from_the_secret_never_the_key(self):
        code, out, err = run(self.fields_args("--unbound"), source=FakeSecret(f"0x{KEY:064x}"))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(self.plan.read_text())["genesisValidator"]["key"], KEY_ADDR)
        self.assert_no_key(KEY, out, err)

    def test_an_unbound_boot_is_refused_by_default(self):
        before = self.plan.read_text()
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--deployer", DEPLOYER))
        self.assertEqual(code, 2)
        want = gv.boot_nonce(11_155_111, gv.registry_address(DEPLOYER, LIBS), KEY_ADDR)
        self.assertIn(f"attest_nonce {want}", err)
        self.assertEqual(self.plan.read_text(), before)
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR))
        self.assertEqual(code, 2)
        self.assertIn("--deployer", err)

    def test_a_bound_boot_passes(self):
        registry = gv.registry_address(DEPLOYER, LIBS)
        real = gv.boot_fields

        def bound(console, manifest, verify_doc):
            return dict(real(console, manifest, verify_doc), nonce=gv.boot_nonce(11_155_111, registry, KEY_ADDR))

        with mock.patch.object(gv, "boot_fields", bound):
            code, out, err = run(self.fields_args("--key-address", KEY_ADDR, "--deployer", DEPLOYER))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["boot"]["bound"]["registry"], registry)
        with mock.patch.object(gv, "boot_fields", bound):  # another deployer nonce is another registry
            code, _, _ = run(self.fields_args("--key-address", KEY_ADDR, "--deployer", DEPLOYER,
                                              "--deployer-nonce", "1"))
        self.assertEqual(code, 2)

    def test_verify_output_with_a_skipped_check_is_refused(self):
        doc = json.loads((self.tmp / "verify.json").read_text())
        del doc["checks"]["snpSignature"]
        (self.tmp / "verify.json").write_text(json.dumps(doc))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)
        self.assertIn("snpSignature didn't run", err)

    def test_verify_output_of_another_boot_is_refused(self):
        doc = json.loads((self.tmp / "verify.json").read_text())
        doc["checks"]["nonce"]["detail"] = "the boot used '00ff'"
        (self.tmp / "verify.json").write_text(json.dumps(doc))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)
        self.assertIn("another boot", err)
        doc["checks"]["nonce"]["detail"] = "the boot used '6c620e28ba75f2a262cdf89266266168'"
        doc["checks"]["snpMeasurement"]["detail"] = "00" * 48
        (self.tmp / "verify.json").write_text(json.dumps(doc))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)
        self.assertIn("measurement", err)

    def test_a_tampered_console_is_refused(self):
        text = (self.tmp / "console.txt").read_text(errors="replace")
        (self.tmp / "console.txt").write_text(text.replace("POF-ATTEST roothash 51c96e70", "POF-ATTEST roothash 61c96e70"))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)
        self.assertIn("roothash", err)
        (self.tmp / "console.txt").write_text("no attestation here\n")
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)

    def test_another_manifest_is_refused(self):
        m = json.loads((self.tmp / "manifest.json").read_text())
        m["image_digest"] = "0x" + "12" * 32
        (self.tmp / "manifest.json").write_text(json.dumps(m))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 2)
        self.assertIn("image digest", err)

    def test_malformed_options_are_refused(self):
        for extra, why in ((["--key-address", "0x12"], "--key-address"), (["--level", "C"], "--level"),
                           (["--operator", "0x" + "00" * 20], "--operator")):
            args = extra if extra[0] == "--key-address" else ["--key-address", KEY_ADDR, *extra]
            code, _, err = run(self.fields_args(*args, "--unbound"))
            self.assertEqual(code, 2, extra)
            self.assertIn(why, err)

    def test_changed_fields_drop_an_old_signature(self):
        p = json.loads(self.plan.read_text())
        p["genesisValidator"] = {"key": KEY_ADDR, "signature": "0x" + "11" * 65}
        self.plan.write_text(json.dumps(p))
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 0)
        self.assertNotIn("signature", json.loads(self.plan.read_text())["genesisValidator"])
        self.assertIn("sign again", err)


class TheSignature(Work):
    def fill(self):
        code, _, err = run(self.fields_args("--key-address", KEY_ADDR, "--unbound"))
        self.assertEqual(code, 0, err)

    def sign_args(self, *extra):
        return ["sign", "--plan", str(self.plan), "--deployer", DEPLOYER, "--genesis-rad-node", RAD_DID, *extra]

    def independent_digest(self, plan: dict, registry: str, chain_id: int = 11_155_111) -> bytes:
        """DeploySepolia.s.sol `_digest`, rebuilt from the script's own type string, not oracle/v3.py's."""
        sol = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")
        body = sol[sol.index("function _digest("):]
        typestr = re.search(r'"(Registration\([^"]+\))"', body).group(1)
        name = re.search(r'keccak256\("(proof-of-fix Validators)"\)', body).group(1)
        version = re.search(r'keccak256\("(\d+)"\),\s*block\.chainid', body).group(1)
        k, w = crypto.keccak256, crypto.word
        domain = k(k(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
                   + k(name.encode()) + k(version.encode()) + w(chain_id) + w(registry))
        g = plan["genesisValidator"]
        struct = k(k(typestr.encode()) + w(g["key"]) + w(g["operator"]) + k(b"tee") + k(g["teeType"].encode())
                   + w(g["level"]) + crypto.h32(g["attestation"]) + crypto.h32(g["image"]) + crypto.h32(g["host"])
                   + k(plan["families"][0].encode()) + w(g["firmware"]) + RAD)
        return k(b"\x19\x01" + domain + struct)

    def test_sign_matches_the_deploys_dev_key_path(self):
        self.fill()
        secret = FakeSecret(f"{KEY:064x}")
        code, out, err = run(self.sign_args(), source=secret)
        self.assertEqual(code, 0, err)
        plan = json.loads(self.plan.read_text())
        registry = gv.registry_address(DEPLOYER, LIBS)
        digest = self.independent_digest(plan, registry)
        doc = json.loads(out)
        self.assertEqual((doc["genesisDigest"], doc["registry"], doc["signer"]),
                         ("0x" + digest.hex(), registry, KEY_ADDR))
        sig = bytes.fromhex(plan["genesisValidator"]["signature"][2:])
        self.assertEqual(crypto.recover(digest, sig), KEY_ADDR)
        # `--genesis-dev-key 1` signs the same digest with the same key, deterministically (RFC 6979, low s)
        self.assertEqual(sig, crypto.sign(derive(MNEMONIC, 1), digest))
        # and the deploy wrapper takes the plan as it is, passing the signature to forge
        loaded = gv.ds.load_plan(str(self.plan), None)
        env = gv.ds._env(loaded, {"bytecode": {}}, DEPLOYER, "http://127.0.0.1:8545", "x.json", None)
        self.assertEqual(env["DEPLOY_GENESIS_SIG"], plan["genesisValidator"]["signature"])
        self.assertNotIn("DEPLOY_GENESIS_PK", env)
        self.assertEqual(secret.writes, 0)
        self.assert_no_key(KEY, out, err)

    def test_digest_checked_against_the_dry_runs(self):
        self.fill()
        plan = json.loads(self.plan.read_text())
        right = "0x" + self.independent_digest(plan, gv.registry_address(DEPLOYER, LIBS)).hex()
        code, _, err = run(self.sign_args("--digest", right.upper().replace("0X", "0x")), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 0, err)
        before = self.plan.read_text()
        wrong = "0x" + self.independent_digest(plan, gv.registry_address(DEPLOYER, LIBS + 1)).hex()  # the nonce moved
        code, _, err = run(self.sign_args("--digest", wrong), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 2)
        self.assertIn("isn't this plan's", err)
        self.assertEqual(self.plan.read_text(), before)
        code, _, err = run(self.sign_args("--digest", wrong, "--deployer-nonce", "1"), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 0, err)
        code, _, err = run(self.sign_args("--digest", "0x1234"), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 2)

    def test_local_chain_ids_for_a_rehearsal_only(self):
        self.fill()
        code, out, _ = run(self.sign_args("--chain-id", "31337"), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 0)
        plan = json.loads(self.plan.read_text())
        self.assertEqual(json.loads(out)["genesisDigest"],
                         "0x" + self.independent_digest(plan, gv.registry_address(DEPLOYER, LIBS), 31_337).hex())
        code, _, err = run(self.sign_args("--chain-id", "1"), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 2)
        self.assertIn("Sepolia", err)

    def test_a_key_that_isnt_the_plans_is_refused(self):
        self.fill()
        before = self.plan.read_text()
        other = derive(MNEMONIC, 2)
        code, out, err = run(self.sign_args(), source=FakeSecret(f"{other:064x}"))
        self.assertEqual(code, 2)
        self.assertIn("isn't the plan's genesis key", err)
        self.assertEqual(self.plan.read_text(), before)
        self.assert_no_key(other, out, err)

    def test_an_empty_or_malformed_secret_is_refused_without_showing_it(self):
        self.fill()
        code, _, err = run(self.sign_args(), source=FakeSecret(None))
        self.assertEqual(code, 2)
        self.assertIn("new-key", err)
        for bad in ("not-a-key-but-secret-text", "0x" + "f" * 64, "00"):
            code, out, err = run(self.sign_args(), source=FakeSecret(bad))
            self.assertEqual(code, 2, bad)
            self.assertNotIn(bad, out + err)

    def test_malformed_plans_and_options_are_refused(self):
        code, _, err = run(self.sign_args(), source=FakeSecret(hex(KEY)))  # no genesisValidator yet
        self.assertEqual(code, 2)
        self.assertIn("genesisValidator", err)
        self.fill()
        for args, why in ((["sign", "--plan", str(self.plan), "--deployer", "0xnope", "--genesis-rad-node", RAD_DID],
                           "--deployer"),
                          (["sign", "--plan", str(self.plan), "--deployer", DEPLOYER, "--genesis-rad-node", "z6Mk"],
                           "--genesis-rad-node"),
                          (["sign", "--plan", str(self.plan), "--deployer", DEPLOYER, "--genesis-rad-node",
                            "0x" + "00" * 32], "zero"),
                          (self.sign_args("--deployer-nonce", "-1"), "--deployer-nonce"),
                          (self.sign_args("--libraries", "9"), "--libraries"),
                          (["sign", "--plan", str(self.tmp / "none.json"), "--deployer", DEPLOYER,
                            "--genesis-rad-node", RAD_DID], "no plan")):
            code, _, err = run(args, source=FakeSecret(hex(KEY)))
            self.assertEqual(code, 2, args)
            self.assertIn(why, err)
        p = json.loads(self.plan.read_text())
        p["genesisValidator"]["level"] = 3
        self.plan.write_text(json.dumps(p))
        code, _, err = run(self.sign_args(), source=FakeSecret(hex(KEY)))
        self.assertEqual(code, 2)
        self.assertIn("level", err)


class TheNewKey(Work):
    def test_a_fresh_key_into_an_empty_secret_prints_only_its_address(self):
        secret = FakeSecret(None)
        code, out, err = run(["new-key"], source=secret)
        self.assertEqual(code, 0, err)
        self.assertRegex(secret.value, r"^[0-9a-f]{64}$")  # what the node's ORACLE_PRIVATE_KEY reads
        k = int(secret.value, 16)
        self.assertEqual(out.strip(), crypto.address(k))
        self.assertEqual(secret.writes, 1)
        self.assert_no_key(k, out, err)

    def test_a_secret_with_a_key_is_kept_unless_replace(self):
        old = derive(MNEMONIC, 3)
        secret = FakeSecret(f"{old:064x}")
        code, out, err = run(["new-key"], source=secret)
        self.assertEqual(code, 2)
        self.assertIn(crypto.address(old), err)
        self.assertEqual((secret.value, secret.writes), (f"{old:064x}", 0))
        code, out, err = run(["new-key", "--replace"], source=secret)
        self.assertEqual(code, 0)
        self.assertNotEqual(secret.value, f"{old:064x}")
        self.assert_no_key(old, out, err)
        self.assert_no_key(int(secret.value, 16), out, err)

    def test_a_write_that_doesnt_read_back_is_refused(self):
        class Lossy(FakeSecret):
            def write(self, value):
                self.writes += 1
                self.value = f"{derive(MNEMONIC, 4):064x}"

        code, _, err = run(["new-key"], source=Lossy(None))
        self.assertEqual(code, 2)
        self.assertIn("read back", err)


class TheAwsSecret(unittest.TestCase):
    CREDS = {"Version": 1, "AccessKeyId": "AKIATEST", "SecretAccessKey": "secret-access", "SessionToken": "tok"}

    def make(self, replies):
        calls, requests = [], []

        def runner(cmd, **kw):
            calls.append(cmd)
            return mock.Mock(returncode=0, stdout=json.dumps(self.CREDS), stderr="")

        def request(method, url, headers, body, timeout):
            requests.append((method, url, headers, body))
            return replies.pop(0)

        return gv.AwsSecret(ARN, "pof-sandbox", runner=runner, request=request), calls, requests

    def test_read_signs_get_secret_value_with_the_profiles_credentials(self):
        value = f"{KEY:064x}"
        s, calls, reqs = self.make([Reply(200, {}, json.dumps({"SecretString": value + "\n"}).encode())])
        self.assertEqual(s.read(), value)
        self.assertEqual(calls, [["aws", "configure", "export-credentials", "--format", "process", "--profile",
                                  "pof-sandbox"]])
        method, url, headers, body = reqs[0]
        self.assertEqual((method, url), ("POST", "https://secretsmanager.us-east-2.amazonaws.com/"))
        self.assertEqual(headers["X-Amz-Target"], "secretsmanager.GetSecretValue")
        self.assertIn("Credential=AKIATEST/", headers["Authorization"])
        self.assertEqual(json.loads(body), {"SecretId": ARN})

    def test_an_empty_secret_reads_as_none_and_other_errors_refuse(self):
        s, _, _ = self.make([Reply(400, {}, b'{"__type":"ResourceNotFoundException","Message":"no value"}')])
        self.assertIsNone(s.read())
        s, _, _ = self.make([Reply(400, {}, b'{"__type":"AccessDeniedException"}')])
        with self.assertRaises(gv.Refused) as e:
            s.read()
        self.assertIn("AccessDeniedException", str(e.exception))

    def test_write_puts_the_value_in_the_request_body_only(self):
        value = f"{KEY:064x}"
        s, calls, reqs = self.make([Reply(200, {}, b"{}")])
        s.write(value)
        method, url, headers, body = reqs[0]
        self.assertEqual(headers["X-Amz-Target"], "secretsmanager.PutSecretValue")
        doc = json.loads(body)
        self.assertEqual((doc["SecretId"], doc["SecretString"]), (ARN, value))
        self.assertRegex(doc["ClientRequestToken"], r"^[0-9a-f-]{36}$")  # a raw request must carry one
        self.assertFalse(any(value in " ".join(c) for c in calls))  # never on a command line
        self.assertFalse(any(value in str(v) for v in headers.values()))
        s, _, _ = self.make([Reply(400, {}, b'{"__type":"ResourceNotFoundException"}')])
        with self.assertRaises(gv.Refused) as e:
            s.write(value)
        self.assertNotIn(value, str(e.exception))

    def test_no_credentials_and_bad_arns_refuse(self):
        def runner(cmd, **kw):
            return mock.Mock(returncode=255, stdout="", stderr="expired")

        s = gv.AwsSecret(ARN, runner=runner, request=lambda *a: None)
        with self.assertRaises(gv.Refused) as e:
            s.read()
        self.assertIn("aws sso login", str(e.exception))
        for bad in ("", "arn:aws:s3:::bucket", "pof-sevsnp/signing-key"):
            with self.assertRaises(gv.Refused):
                gv.AwsSecret(bad)

    def test_the_arn_defaults_to_the_kits_output(self):
        seen = []

        def runner(cmd, **kw):
            seen.append(cmd)
            return mock.Mock(returncode=0, stdout=ARN + "\n", stderr="")

        a = gv.parser().parse_args(["new-key"])
        self.assertEqual(gv.secret_arn(a, runner), ARN)
        self.assertEqual(seen, [["tofu", "-chdir=validator-kit/sevsnp/terraform", "output", "-raw",
                                 "signing_key_secret_arn"]])
        a = gv.parser().parse_args(["new-key", "--secret-arn", "x"])
        self.assertEqual(gv.secret_arn(a, runner), "x")

        def failing(cmd, **kw):
            return mock.Mock(returncode=1, stdout="", stderr="no state")

        with self.assertRaises(gv.Refused):
            gv.secret_arn(gv.parser().parse_args(["new-key"]), failing)


class TheKeyText(unittest.TestCase):
    def test_parse_key_takes_the_nodes_forms_and_hides_the_rest(self):
        self.assertEqual(gv.parse_key(f"{KEY:064x}\n"), KEY)
        self.assertEqual(gv.parse_key(f"0x{KEY:064x}"), KEY)
        for bad in ("", "zz", "0x" + "f" * 64, "0", "1" * 65):
            with self.assertRaises(gv.Refused) as e:
                gv.parse_key(bad)
            if bad:
                self.assertNotIn(bad, str(e.exception))


if __name__ == "__main__":
    unittest.main()
