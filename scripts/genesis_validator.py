#!/usr/bin/env python3
"""The Sepolia genesis validator: its plan fields and its signature (proof-of-fix#251 task 7.1; design L3, L11, L17,
L21; the owner's decision of 2026-11-22). Run it as scripts/genesis-validator.sh.

The genesis validator on Sepolia is the owner's SEV-SNP kit host (validator-kit/sevsnp: the measured disk, AWS
us-east-2) with a fresh key in the kit's Secrets Manager secret (`signing_key_secret_arn`). The key's custody isn't
attested on this disk (validator-kit/SEVSNP-PLAN.md, "Open risks"), so the genesis digest is signed here, from the
secret, not on the host. The key is read into this process only: never printed, logged, written to a file or put on
a command line. Only its address is printed.

    scripts/genesis-validator.sh new-key [--replace] [--kit-dir DIR | --secret-arn ARN]
        a fresh secp256k1 key straight into the secret (PutSecretValue, signed here); prints its address. Refused when
        the secret already holds a key, naming that key's address, unless --replace (Secrets Manager keeps the old
        value as AWSPREVIOUS).
    scripts/genesis-validator.sh binding --deployer 0x… [--deployer-nonce 0] [--chain-id 11155111]
        the registry's address (from the deployer's address and nonce, as DeploySepolia.s.sol computes it) and the
        boot nonce that binds an attested boot to this key and that registry: set it as the kit's `attest_nonce`
        (POF_ATTEST_NONCE) for the attest-only boot whose console `fields` reads.
    scripts/genesis-validator.sh fields --plan PLAN --console console.txt --manifest manifest.json
                                        --verify verify.json --deployer 0x… [--operator 0x…] [--unbound]
        the genesis validator's fields from that boot, written into the plan's `genesisValidator` (any old signature
        removed): `key` (the secret's address), `operator` (default the key: the bond goes back to it on withdrawal,
        and the node's own `register` defaults to it too), `teeType` amd-sev-snp, `level` 1 (A: a cloud's
        confidential VM with its attestation, design L10; `--level B` for 2), `attestation` (keccak256 of the boot's
        SEV-SNP report, as the node's `register` hashes its quote), `image` (the manifest's `image_digest`), `host`
        (keccak256 of `--host`, default "aws:us-east-2", the kit's ORACLE_HOST_ID) and `firmware` (the report's
        REPORTED_TCB, oracle/snp.py `Report.firmware`). The plan's `teeTypes` and `images` gain amd-sev-snp and the
        image if missing. Refused unless verify.py's saved output (`--verify`) shows every check run and passed
        (release_candidate.verify_problems) and is this console's (its nonce and measurement), the offline checks
        pass again here on the console, and the boot's nonce is `binding`'s for this key, deployer and registry
        (`--unbound` accepts another nonce: the attestation then shows the measured disk booted, not that it booted
        for this registration). Prints the fields and the boot's Radicle node (`--genesis-rad-node` for the deploy).
    scripts/genesis-validator.sh sign --plan PLAN --deployer 0x… --genesis-rad-node did:key:z6Mk…
                                      [--deployer-nonce 0] [--chain-id 11155111] [--digest 0x…]
        GENESIS_DIGEST computed as DeploySepolia.s.sol computes it (the registration's EIP-712 digest for the registry
        at the address the deployer's nonce gives), checked against `--digest` (what a dry run printed) when given;
        signed with the secret's key, which must be the plan's `genesisValidator.key`; the signature written into the
        plan. Prints the registry, the digest and the signer's address.

Every command that reads the key takes `--secret-arn ARN` (default `tofu -chdir=<--kit-dir> output -raw
signing_key_secret_arn`, local state; `--kit-dir` defaults to validator-kit/sevsnp/terraform, the genesis kit: pass
another validator's state directory, or `--secret-arn`, for another kit) and `--profile` (default pof-sandbox: `aws configure export-credentials`,
the SSO profile's credentials, read into this process; the requests are signed here, oracle/models.py's SigV4).
`binding` and `fields` take `--key-address 0x…` instead to read nothing.

The digest depends on the deployer's address and on its nonce when the script runs: forge first deploys Panels'
linked libraries (PanelsDraw, PanelsVerdict, PanelsJudge) from the deployer through the CREATE2 deployer, three
transactions, and then the script's faucet, pool and registry maker, whose first creation is the registry. So the
registry is the maker's at nonce `--deployer-nonce` + `--libraries` + 2: a fresh deployer (task 7.2) that has sent
nothing has nonce 0 (the faucet's funding doesn't change it), and `--libraries` is 3 unless the libraries already
exist on the chain at their CREATE2 addresses (an earlier broadcast of the same build: then 0, and the dry run's
GENESIS_REGISTRY says so). `sign --digest` checks the result against the dry run. If the deployer sends anything
first, the digest (and the binding) change: sign again, and boot again unless --unbound. Exit 2 on any refusal, with
nothing written."""

from __future__ import annotations

import argparse
import base64
import datetime
import importlib.util
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "scripts"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import deploy_sepolia as ds  # noqa: E402
import release_candidate as rcmod  # noqa: E402
from oracle import crypto, snp, v3  # noqa: E402
from oracle.awssecret import SecretError, get_secret  # noqa: E402
from oracle.delegates import did_from_key, parse_node  # noqa: E402
from oracle.models import AwsCredentials, http_request, sigv4  # noqa: E402
from oracle.tx import rlp  # noqa: E402
from rc_aws import console_facts  # noqa: E402

REFUSED = 2
TEE_TYPE = "amd-sev-snp"
DEFAULT_HOST = "aws:us-east-2"  # the kit's ORACLE_HOST_ID (validator-kit/SEVSNP-PLAN.md step 8)
DEFAULT_PROFILE = "pof-sandbox"
KIT_TERRAFORM = "validator-kit/sevsnp/terraform"
LEVELS = {"A": v3.LEVEL_A, "B": v3.LEVEL_B}
# Panels' linked libraries, which forge deploys from the deployer (CREATE2 deployer) before the script's own creations
# (tests/test_genesis_validator.py checks the list against contracts/src/v3).
LINKED_LIBRARIES = ("PanelsDraw", "PanelsJudge", "PanelsVerdict")
CHAINS = (ds.SEPOLIA, *ds.LOCAL_IDS)  # a local id only for a rehearsal (the deploy refuses it off a local endpoint)
# What the node's `register` puts in its quote's report data (oracle/node_v3.py `registration`): the same preimage is
# the boot's nonce here, so the boot's report names this key and registry.
REGISTRATION_NOTE = b"proof-of-fix v3 registration"
ARN_RE = re.compile(r"^arn:aws:secretsmanager:[a-z0-9-]+:\d{12}:secret:[A-Za-z0-9/_+=.@-]+$")


class Refused(Exception):
    """A check failed: nothing was written."""


def say(msg: str) -> None:
    print(f"genesis-validator: {msg}", file=sys.stderr)


# ---------- the registry's address, the binding and the digest ----------

def create_address(sender: str, nonce: int) -> str:
    """The address `sender`'s creation number `nonce` gets (CREATE: keccak256(rlp([sender, nonce]))[12:])."""
    return crypto.checksum("0x" + crypto.keccak256(rlp([bytes.fromhex(sender[2:]), nonce]))[12:].hex())


def registry_address(deployer: str, nonce: int = 0) -> str:
    """Where Validators will be, as DeploySepolia.s.sol computes it before anything is sent: `nonce` is the deployer's
    nonce when the script runs (after forge's library deployments); its creations from there are the faucet, the pool
    and the registry maker, whose first creation is Validators."""
    return create_address(create_address(deployer, nonce + 2), 1)


def script_nonce(a) -> int:
    """The deployer's nonce when the script runs: its transaction count, plus the linked libraries forge deploys."""
    n, libs = a.deployer_nonce, a.libraries
    if n < 0 or n >= 2**63 or libs < 0 or libs > len(LINKED_LIBRARIES):
        raise Refused(f"--deployer-nonce is the deployer's transaction count, from 0; --libraries from 0 to "
                      f"{len(LINKED_LIBRARIES)}")
    return n + libs


def boot_nonce(chain_id: int, registry: str, key: str) -> str:
    """The attest-only boot's nonce (hex) that binds its report to this key and registry: keccak256 of what the
    node's `register` quotes (REGISTRATION_NOTE, the registry's EIP-712 domain, the key)."""
    return crypto.keccak256(REGISTRATION_NOTE + v3.registry_domain(chain_id, registry) + v3.address_word(key)).hex()


def registration(plan: dict, rad_node: bytes) -> v3.Registration:
    """The genesis registration as DeploySepolia.s.sol `_registration` builds it from the plan."""
    g = plan["genesisValidator"]
    return v3.Registration(g["key"], g["operator"], v3.PROOF_TEE, crypto.keccak256(g["teeType"].encode()),
                           int(g["level"]), crypto.h32(g["attestation"]), crypto.h32(g["image"]),
                           crypto.h32(g["host"]), crypto.keccak256(plan["families"][0].encode()),
                           int(g.get("firmware", 0)), rad_node)


def genesis_digest(plan: dict, deployer: str, nonce: int, chain_id: int, rad_node: bytes) -> tuple:
    """(the registry's address, GENESIS_DIGEST) as the deploy's dry run prints them; `nonce` as `registry_address`'s."""
    registry = registry_address(deployer, nonce)
    return registry, registration(plan, rad_node).digest(v3.registry_domain(chain_id, registry))


# ---------- the attested boot ----------

def _verify_module():
    spec = importlib.util.spec_from_file_location("sevsnp_verify", ROOT / "validator-kit" / "sevsnp" / "verify.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


OFFLINE_CHECKS = ("roothash", "imageDigest", "nonce", "snpReportData", "snpPolicy", "nitroPcrs", "nitroBinding",
                  "attestedImages")


def boot_fields(console: str, manifest: dict, verify_doc: dict) -> dict:
    """What the attested boot gives the registration, after its checks (module docstring, `fields`)."""
    problems = rcmod.verify_problems(verify_doc, manifest)
    if problems:
        raise Refused("verify.py's output doesn't attest the boot: " + "; ".join(problems))
    V = _verify_module()
    text = V.console_text(console)
    lines = V.console_lines(text)
    nonce = lines.get("nonce", "")
    if not re.fullmatch(r"[0-9a-f]{2,128}", nonce) or "snp-report" not in lines:
        raise Refused("the console has no attested boot (POF-ATTEST nonce and snp-report lines)")
    if f"the boot used {nonce!r}" != verify_doc["checks"]["nonce"].get("detail"):
        raise Refused("verify.py's output is of another boot (its nonce isn't this console's)")
    again = V.verify(console, manifest, nonce)["checks"]
    failed = [c for c in OFFLINE_CHECKS if again.get(c, {}).get("ok") is not True]
    if failed:
        raise Refused(f"the console fails verify.py's checks here: {', '.join(failed)}")
    try:
        raw = base64.b64decode(lines["snp-report"])
        report = snp.parse(raw)
    except ValueError as e:
        raise Refused(f"the console's SEV-SNP report doesn't parse: {e}") from None
    raw = raw[:snp.REPORT_SIZE]
    if verify_doc["checks"]["snpMeasurement"].get("detail") != report.measurement.hex():
        raise Refused("verify.py's measurement isn't this console's report's")
    nid = console_facts(text)["nid"]
    return {"nonce": nonce, "attestation": "0x" + crypto.keccak256(raw).hex(), "firmware": report.firmware(),
            "image": manifest["image_digest"].lower(), "roothash": manifest["roothash"],
            "measurement": report.measurement.hex(), "radNode": "did:key:" + nid if nid else ""}


# ---------- the secret ----------

def parse_key(text: str) -> int:
    """The secret's value as a key (hex, with or without 0x, as the node's ORACLE_PRIVATE_KEY). The message of a
    refusal never holds the value."""
    raw = (text or "").strip()
    raw = raw[2:] if raw.startswith("0x") else raw
    if not re.fullmatch(r"[0-9a-fA-F]{1,64}", raw):
        raise Refused("the secret's value isn't a hex private key")
    k = int(raw, 16)
    if not 1 <= k < crypto.N:
        raise Refused("the secret's value isn't a valid secp256k1 key")
    return k


class AwsSecret:
    """The kit's signing-key secret through Secrets Manager's API, signed here with the profile's credentials
    (`aws configure export-credentials`, read into this process). `runner` and `request` are fakes in the tests."""

    def __init__(self, arn: str, profile: str = DEFAULT_PROFILE, runner=subprocess.run, request=http_request):
        if not ARN_RE.match(arn or ""):
            raise Refused(f"not a Secrets Manager ARN: {arn!r}")
        self.arn, self.profile, self.runner, self.request = arn, profile, runner, request
        self.region = arn.split(":")[3]
        self._creds = None

    def credentials(self) -> AwsCredentials:
        if self._creds is None:
            cmd = ["aws", "configure", "export-credentials", "--format", "process"]
            cmd += ["--profile", self.profile] if self.profile else []
            r = self.runner(cmd, capture_output=True, text=True, timeout=60)
            try:
                c = json.loads(r.stdout) if r.returncode == 0 else {}
                self._creds = AwsCredentials(c["AccessKeyId"], c["SecretAccessKey"], c.get("SessionToken", ""))
            except (ValueError, KeyError, TypeError):
                raise Refused(f"no credentials from the profile {self.profile!r} (sign in: aws sso login "
                              f"--profile {self.profile})") from None
        return self._creds

    def read(self):
        """The secret's current value, or None when it holds none yet."""
        try:
            return get_secret(self.arn, self.request, self.credentials)
        except SecretError as e:
            if "ResourceNotFoundException" in str(e):
                return None
            raise Refused(str(e)) from None

    def write(self, value: str) -> None:
        url = f"https://secretsmanager.{self.region}.amazonaws.com/"
        body = json.dumps({"SecretId": self.arn, "SecretString": value,
                           "ClientRequestToken": str(uuid.uuid4())}).encode()
        headers = {"Content-Type": "application/x-amz-json-1.1", "X-Amz-Target": "secretsmanager.PutSecretValue"}
        signed = sigv4("POST", url, headers, body, self.credentials(), self.region, "secretsmanager",
                       datetime.datetime.now(datetime.timezone.utc))
        try:
            reply = self.request("POST", url, signed, body, 15.0)
        except OSError as e:
            raise Refused(f"Secrets Manager unreachable: {type(e).__name__}") from None
        del body
        if reply.status != 200:
            try:
                kind = str(json.loads(reply.body.decode() or "{}").get("__type", "")).split("#")[-1]
            except ValueError:
                kind = ""
            raise Refused(f"Secrets Manager refused the new value: HTTP {reply.status} {kind}".rstrip())


def secret_arn(a, runner=subprocess.run) -> str:
    if a.secret_arn:
        return a.secret_arn
    kit = getattr(a, "kit_dir", None) or KIT_TERRAFORM
    try:
        r = runner(["tofu", f"-chdir={kit}", "output", "-raw", "signing_key_secret_arn"], cwd=ROOT,
                   capture_output=True, text=True, timeout=120)
    except OSError:
        raise Refused("no --secret-arn, and tofu can't run to read the kit's output") from None
    if r.returncode or not r.stdout.strip():
        raise Refused(f"no --secret-arn, and the kit's output signing_key_secret_arn can't be read ({kit})")
    return r.stdout.strip()


def _source(a, source):
    return source if source is not None else AwsSecret(secret_arn(a), a.profile)


def _key(source) -> int:
    value = source.read()
    if value is None:
        raise Refused("the secret holds no key yet: run new-key first")
    return parse_key(value)


def _key_address(a, source) -> str:
    if getattr(a, "key_address", None):
        return _address(a.key_address, "--key-address")
    return crypto.address(_key(_source(a, source)))


# ---------- checks and the plan file ----------

def _address(v, what: str) -> str:
    if not isinstance(v, str) or not ds.ADDR_RE.match(v) or int(v, 16) == 0:
        raise Refused(f"{what} must be a nonzero address (0x and 40 hex digits)")
    return crypto.checksum(v)


def _chain(cid: int) -> int:
    if cid not in CHAINS:
        raise Refused(f"--chain-id {cid}: Sepolia (11155111), or a local test id for a rehearsal")
    return cid


def _rad_node(value: str) -> bytes:
    try:
        key = parse_node(value or "")
    except ValueError as e:
        raise Refused(f"--genesis-rad-node: {e}") from None
    if not any(key):
        raise Refused("--genesis-rad-node: zero names no node")
    return key


def _read_json(path: str, what: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError:
        raise Refused(f"no {what} at {path}") from None
    except ValueError as e:
        raise Refused(f"the {what} isn't JSON ({e})") from None


def _write_plan(path: Path, plan: dict) -> None:
    """Atomically, beside the old file (the plan holds no secret: the signature and the key's address are public)."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".plan-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(plan, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------- the commands ----------

def cmd_new_key(a, source=None) -> int:
    src = _source(a, source)
    old = src.read()
    if old is not None:
        try:
            held = crypto.address(parse_key(old))
        except Refused:
            held = "a value that isn't a key"
        if not a.replace:
            raise Refused(f"the secret already holds a key ({held}); --replace to put a fresh one in its place "
                          f"(Secrets Manager keeps the old one as AWSPREVIOUS)")
        say(f"replacing the secret's key {held}")
    del old
    key = secrets.randbelow(crypto.N - 1) + 1
    src.write(f"{key:064x}")
    want = crypto.address(key)
    del key
    got = crypto.address(_key(src))
    if got != want:
        raise Refused("the secret doesn't read back as the new key")
    say("a fresh key is in the secret; only its address is shown")
    print(want)
    return 0


def cmd_binding(a, source=None) -> int:
    deployer, nonce, cid = _address(a.deployer, "--deployer"), script_nonce(a), _chain(a.chain_id)
    key = _key_address(a, source)
    registry = registry_address(deployer, nonce)
    print(json.dumps({"key": key, "deployer": deployer, "deployerNonce": a.deployer_nonce, "libraries": a.libraries,
                      "chainId": cid, "registry": registry, "attestNonce": boot_nonce(cid, registry, key)}, indent=2))
    say("set attestNonce as the kit's attest_nonce for an attest-only boot, then save its console for `fields`")
    return 0


def cmd_fields(a, source=None) -> int:
    if a.level not in LEVELS:
        raise Refused("--level is A or B")
    if not a.host:
        raise Refused("--host names the infrastructure host (default aws:us-east-2)")
    console = Path(a.console).read_text(encoding="utf-8", errors="replace") if Path(a.console).is_file() else None
    if console is None:
        raise Refused(f"no console at {a.console}")
    manifest = _read_json(a.manifest, "manifest")
    verify_doc = _read_json(a.verify, "verify.py output")
    if not isinstance(manifest, dict) or not ds.B32_RE.match(str(manifest.get("image_digest", ""))):
        raise Refused("the manifest has no image_digest")
    boot = boot_fields(console, manifest, verify_doc)
    key = _key_address(a, source)
    operator = _address(a.operator, "--operator") if a.operator else key
    bound = None
    if not a.unbound:
        if not a.deployer:
            raise Refused("--deployer (with --deployer-nonce, default 0) to check the boot's binding, or --unbound")
        deployer, nonce, cid = _address(a.deployer, "--deployer"), script_nonce(a), _chain(a.chain_id)
        registry = registry_address(deployer, nonce)
        want = boot_nonce(cid, registry, key)
        if boot["nonce"] != want:
            raise Refused(f"the boot's nonce isn't the binding for this key and registry ({registry}): boot with "
                          f"attest_nonce {want} (`binding`), or --unbound")
        bound = {"registry": registry, "deployer": deployer, "deployerNonce": a.deployer_nonce,
                 "libraries": a.libraries, "chainId": cid}
    path = Path(a.plan)
    plan = _read_json(a.plan, "plan") if path.exists() else {}
    if not isinstance(plan, dict):
        raise Refused("the plan must be a JSON object")
    g = {"key": key, "operator": operator, "teeType": TEE_TYPE, "level": LEVELS[a.level],
         "attestation": boot["attestation"], "image": boot["image"], "host": "0x" + v3.name_id(a.host).hex(),
         "firmware": boot["firmware"]}
    old = plan.get("genesisValidator") if isinstance(plan.get("genesisValidator"), dict) else {}
    if old.get("signature") and any(old.get(k) != v for k, v in g.items()):
        say("the plan's old genesis signature is removed (the fields changed): sign again")
    elif old.get("signature"):
        g["signature"] = old["signature"]
    plan["genesisValidator"] = g
    tees = plan.get("teeTypes") if isinstance(plan.get("teeTypes"), list) else []
    plan["teeTypes"] = tees + ([TEE_TYPE] if TEE_TYPE not in tees else [])
    images = [str(i).lower() for i in plan.get("images", [])] if isinstance(plan.get("images"), list) else []
    plan["images"] = images + ([boot["image"]] if boot["image"] not in images else [])
    _write_plan(path, plan)
    print(json.dumps({"genesisValidator": g, "hostName": a.host, "boot": {
        "nonce": boot["nonce"], "roothash": boot["roothash"], "measurement": boot["measurement"],
        "bound": bound or "no (--unbound): the attestation shows the measured disk booted, not for this registration"},
        "genesisRadNode": boot["radNode"]}, indent=2))
    hint = f" --genesis-rad-node {boot['radNode']}" if boot["radNode"] else ""
    say(f"written to {path}; next: the deploy's dry run prints GENESIS_DIGEST, then `sign`{hint}")
    return 0


def cmd_sign(a, source=None) -> int:
    deployer, nonce, cid = _address(a.deployer, "--deployer"), script_nonce(a), _chain(a.chain_id)
    rad = _rad_node(a.genesis_rad_node)
    try:
        plan = ds.load_plan(a.plan, None)
    except ds.Refused as e:
        raise Refused(str(e)) from None
    if plan["genesisValidator"]["teeType"] != TEE_TYPE:
        raise Refused(f"the plan's genesis validator isn't {TEE_TYPE} (run `fields`)")
    registry, digest = genesis_digest(plan, deployer, nonce, cid, rad)
    if a.digest is not None:
        if not ds.B32_RE.match(a.digest):
            raise Refused("--digest is the dry run's GENESIS_DIGEST, 0x and 64 hex digits")
        if a.digest.lower() != "0x" + digest.hex():
            raise Refused(f"the dry run's digest {a.digest.lower()} isn't this plan's for the deployer {deployer} at "
                          f"nonce {a.deployer_nonce} with {a.libraries} libraries first (the registry at {registry}) "
                          f"on chain {cid} with this Radicle node (0x{digest.hex()}): check them against the dry "
                          f"run's GENESIS_REGISTRY")
    key = _key(_source(a, source))
    signer = crypto.address(key)
    if signer.lower() != plan["genesisValidator"]["key"].lower():
        raise Refused(f"the secret's key ({signer}) isn't the plan's genesis key ({plan['genesisValidator']['key']})")
    sig = crypto.sign(key, digest)
    del key
    if crypto.recover(digest, sig).lower() != signer.lower():
        raise Refused("the signature doesn't recover to the key")
    raw = _read_json(a.plan, "plan")  # the file as it is (load_plan normalises), with the signature added
    raw["genesisValidator"]["signature"] = "0x" + sig.hex()
    _write_plan(Path(a.plan), raw)
    print(json.dumps({"registry": registry, "genesisDigest": "0x" + digest.hex(), "signer": signer,
                      "deployer": deployer, "deployerNonce": a.deployer_nonce, "libraries": a.libraries, "chainId": cid,
                      "genesisRadNode": did_from_key(rad)}, indent=2))
    say(f"the genesis signature is in {a.plan}; run the dry run again (it passes only for the registry at {registry}: "
        f"this deployer at nonce {a.deployer_nonce}, {a.libraries} libraries deployed first)")
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genesis-validator.sh", description="the Sepolia genesis validator's plan fields "
                                "and signature (#251 task 7.1); the key is never printed")
    sub = p.add_subparsers(dest="command", required=True)

    def secret(sp, key_address=False):
        sp.add_argument("--secret-arn", help="the signing key's secret (default: the kit's tofu output "
                        "signing_key_secret_arn, from --kit-dir)")
        sp.add_argument("--kit-dir", default=KIT_TERRAFORM, help="the kit's state directory whose output names the "
                        f"secret when --secret-arn isn't given (default {KIT_TERRAFORM}: the genesis kit's)")
        sp.add_argument("--profile", default=DEFAULT_PROFILE, help="the AWS profile (default pof-sandbox)")
        if key_address:
            sp.add_argument("--key-address", help="the key's address, instead of reading the secret")

    def deployer(sp, required=True):
        sp.add_argument("--deployer", required=required, help="the deploying address (task 7.2's fresh wallet)")
        sp.add_argument("--deployer-nonce", type=int, default=0, help="its transaction count at the broadcast "
                        "(default 0: a fresh wallet that has sent nothing)")
        sp.add_argument("--libraries", type=int, default=len(LINKED_LIBRARIES), help="Panels' linked libraries forge "
                        f"deploys from the deployer first (default {len(LINKED_LIBRARIES)}; 0 if they already exist "
                        "at their CREATE2 addresses on the chain)")
        sp.add_argument("--chain-id", type=int, default=ds.SEPOLIA, help="default 11155111")

    n = sub.add_parser("new-key", help="a fresh key straight into the secret; prints its address")
    secret(n)
    n.add_argument("--replace", action="store_true", help="replace a key the secret already holds")
    n.set_defaults(fn=cmd_new_key)

    b = sub.add_parser("binding", help="the boot nonce binding an attested boot to this key and registry")
    secret(b, key_address=True)
    deployer(b)
    b.set_defaults(fn=cmd_binding)

    f = sub.add_parser("fields", help="the genesis validator's fields from an attested boot, into the plan")
    secret(f, key_address=True)
    deployer(f, required=False)
    f.add_argument("--plan", required=True, help="the deployment plan (created if missing)")
    f.add_argument("--console", required=True, help="the attested boot's console (get-console-output --latest)")
    f.add_argument("--manifest", required=True, help="the measured disk's manifest.json")
    f.add_argument("--verify", required=True, help="verify.py's output for that console, every check run")
    f.add_argument("--operator", help="the operator account (default the key's address)")
    f.add_argument("--level", default="A", help="A (default: a cloud's confidential VM) or B")
    f.add_argument("--host", default=DEFAULT_HOST, help=f"the declared host (default {DEFAULT_HOST})")
    f.add_argument("--unbound", action="store_true", help="accept a boot whose nonce isn't the binding")
    f.set_defaults(fn=cmd_fields)

    s = sub.add_parser("sign", help="sign GENESIS_DIGEST with the secret's key, into the plan")
    secret(s)
    deployer(s)
    s.add_argument("--plan", required=True, help="the deployment plan, its genesisValidator filled by `fields`")
    s.add_argument("--genesis-rad-node", required=True, help="the deploy's --genesis-rad-node (the host's node)")
    s.add_argument("--digest", help="the dry run's GENESIS_DIGEST, checked against the one computed here")
    s.set_defaults(fn=cmd_sign)
    return p


def main(argv: list | None = None, source=None) -> int:
    """`source` replaces the AWS secret (the tests' fake: `read()` and `write(value)`)."""
    a = parser().parse_args(argv)
    try:
        return a.fn(a, source)
    except Refused as e:
        say(f"refused: {e}")
        return REFUSED


if __name__ == "__main__":
    sys.exit(main())
