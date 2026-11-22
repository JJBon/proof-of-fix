"""The Sepolia deploy's wrapper (proof-of-fix#251, task 3.9; design L2, L3, L17, L18; specs/deployment-binding).
Run it as scripts/deploy-sepolia.sh. It is a dry run unless given `--broadcast-sepolia`, the flag naming the step.

    scripts/deploy-sepolia.sh deploy --rpc-url URL --plan PLAN.json --release-candidate RC.json
                                     --genesis-rad-node did:key:z6Mk… [signer] [options]
    scripts/deploy-sepolia.sh hashes          each contract's creation-code hash, for a release-candidate record

Before anything is signed, in this order, and stopping at the first refusal (exit 2) with nothing sent:
1. the plan (the RID, the genesis head, the genesis validator, the families, TEE types and images) is well formed,
   the genesis validator's Radicle node (`--genesis-rad-node`, a did:key or 0x and 64 hex digits, never zero) is
   well formed, and a test key (`--dev-key`, `--genesis-dev-key`) is given only for a local endpoint;
2. the endpoint's chain id (`eth_chainId`, the only call made before the checks pass): 11155111 goes on; 31337 and
   7193, the local test ids the constructors also accept (L2 option 1), only for a local endpoint (http on 127.0.0.1,
   localhost or [::1], nothing else); anything else is refused, naming the chain id. A local anvil started with
   `--chain-id 11155111` takes the Sepolia path: a rehearsal, not a shortcut;
3. the release-candidate record (L18) is well formed, says passed, and names a commit this checkout contains;
4. `pofctl verify-head --rid RID --commit HEAD`: the Radicle repository exists and its canonical `main` is the
   genesis head (`--verify-head-cmd` replaces the command, e.g. in tests; `--rad-exec` reaches the Radicle node);
5. forge simulates the deployment against the endpoint (DeploySepolia.s.sol): the chain again, every contract's
   creation-code hash against the record (it names the contract that differs), the genesis mint, the genesis
   validator's signature for the registry's address, and every constructor's own checks.
Only then, and only with `--broadcast-sepolia`, forge broadcasts; the wrapper checks that every address in the record
has code, that the race reports the chain id, and that Panels reads back the panel rules asked for. The record (chain id, addresses, every constructor argument, the
deployer, the bytecode hashes, the limit of the binding; plus Panels' linked libraries, which forge deploys through the
CREATE2 deployer at addresses that follow from their code, the release candidate, the commit and the genesis-head
check) is written under contracts/deployments: `sepolia-v3.json` on Sepolia, `sepolia-local/chain-<id>.json` on a
local endpoint, `.dry-run.json` for a dry run.

The fee coin (design L17, amended by the owner on 2026-11-20): the deployment brings its own, on Sepolia and on the
local ids alike. CoinFaucet is deployed first and creates TestCoin ("proof-of-fix test coin", POFTEST, 6 decimals, no
value), whose only minter it is: 20 coins a claim, one claim per address every 2 hours, anyone for itself, no key. The
genesis mint, fixed at deploy, is `--genesis-mint AMOUNT` coins in total (default 5,000: 15 bonds of $250 and 1,250 to
seed bounties): the genesis validator's 250-coin bond goes to the registry maker, which bonds it into Validators, and
the rest to `--genesis-mint-to ADDRESS` (default the deployer). The record's `testCoin` names the coin, the faucet, the
genesis mint and the faucet's rule.

The panel rules (#251 contract batch 4, design L23 and L24): `--panel-caps strict|launch` (default `strict`: the
operator, host and TEE-type caps each `Strict`; `launch`: each `Off`), `--k-top N` (the largest issue-tier panel, odd
from 1 to 7; default 7) and `--challenge-size larger|same` (default `larger`, D4). The Sepolia deployment runs with
`--panel-caps launch --k-top 3 --challenge-size same` (owner, 2026-11-20). They are Panels' constructor argument, not its
creation code, so the bytecode hashes don't cover them: the release-candidate record names them (`panelRules`) and
the wrapper refuses one that ran with other rules; the deployment record names them as Panels reads them back
(`panelRules`), and a record whose rules differ from the ones asked for (or, after a broadcast, from the chain's) is
refused.

The genesis validator's Radicle node (#251, design L11 condition 1, owner 2026-11-20): `--genesis-rad-node` names it
(required). Its 32-byte Ed25519 key is a field of the genesis registration, inside the digest the genesis validator
signs, and Validators stores it (`radNodeOf`), so the genesis seat maps to its node on-chain. The record names it twice:
in the Validators constructor arguments (`validators.radNode`) and as `genesisRadNode` (the key and its did:key); the
wrapper refuses a record whose key isn't the one asked for.

Signers. A dry run signs nothing: it needs only the deploying address (`--deployer`, or the keystore's). A broadcast
needs `--keystore FILE` (forge asks for its password; the key is never read here), or, on a local endpoint only,
`--dev-key N` (anvil's public test key N, passed to forge on stdin, never on a command line). The genesis validator's
signature is the plan's `genesisValidator.signature`, over the GENESIS_DIGEST a dry run prints; `--genesis-dev-key N`
signs with anvil's key N on a local endpoint. The RPC URL goes to forge in the environment, and is never printed.

Forge runs in the pinned Foundry image (scripts/contracts.sh's), with the host's network so it reaches the endpoint.
DEPLOY_FORGE_CONTAINER=<name> runs it in an existing container instead (the test rig's anvil container, which mounts
contracts/ at /work and the pinned solc).

The release-candidate record (L18), `pof-release-candidate/1`, one JSON file (committed under
contracts/release-candidates/ once the run of task 7.0 passes):

    {"format": "pof-release-candidate/1",
     "tag": "v3-rc1", "commit": "<the tagged commit's 40-hex SHA-1>",
     "result": "passed",                                   # or "failed"; "incomplete" while items are pending
     "checks": {"integration": {"command": "scripts/integration.sh --release-candidate <commit>",
                                "runs": ["passed", "passed", "passed"]},   # the last 3 must have passed, in a row
                "productionWindows": "passed",             # L18 item 2: a bounty with production windows, clock moved
                "sevSnpValidator": "passed",               # item 3: one real SEV-SNP validator registered and judged
                "realModelRun": "passed",                  # item 4: one small real-model run
                "attestedImages": "passed"},               # item 6 (L21): item 3's host booted the measured checker
                                                           # disk, its measurement equals the reproducible build's and
                                                           # the genesis's image digest, and it refused an unlisted image
     "panelRules": {"operatorCap": "off", "hostCap": "off", "teeCap": "off",   # the rules the run deployed with (#251
                    "kTop": 3, "challengeSize": "same"},                       # batch 4): the deploy's must equal them
     "bytecode": {"TestCoin": "0x<keccak256 of the creation code>", "CoinFaucet": "0x…", "PoolV3": "0x…",
                  "RegistryMaker": "0x…", "Validators": "0x…",
                  "PanelScores": "0x…", "FeesV3": "0x…", "Panels": "0x…", "RaceV3Endings": "0x…", "RaceV3Annex": "0x…",
                  "RaceV3": "0x…"}}

`scripts/integration.sh --release-candidate <commit>` (scripts/release_candidate.py) writes the record: the commit, the
hashes, the integration runs and `productionWindows`; the items it can't check stay "pending" until recorded.
`hashes` prints the `bytecode` object for the checkout as it is. The record is refused if any field is missing or not
"passed", if it names other contracts, or if its commit isn't this checkout's HEAD or an ancestor of it; forge then
refuses any contract whose hash differs, so a change after the run means a new release candidate.

The plan (task 7.1 prepares it):

    {"rid": "rad:z…", "genesisHead": "<40-hex SHA-1: Radicle main now>",
     "families": ["<the genesis validator's family>", …], "teeTypes": ["amd-sev-snp", …], "images": ["0x<digest>", …],
     "genesisValidator": {"key": "0x…", "operator": "0x…", "teeType": "amd-sev-snp", "level": 1,
                          "attestation": "0x<hash>", "image": "0x<digest>", "host": "0x<hash>", "firmware": 0,
                          "signature": "0x<65 bytes, over GENESIS_DIGEST>"}}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle.crypto import address as address_of  # noqa: E402
from oracle.crypto import keccak256  # noqa: E402
from oracle.delegates import did_from_key, parse_node  # noqa: E402
from pofctl.keys import MNEMONIC, derive  # noqa: E402

SEPOLIA = 11_155_111
LOCAL_IDS = (31_337, 7_193)
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
FOUNDRY_IMAGE = "ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
SCRIPT = "script/DeploySepolia.s.sol:DeploySepoliaScript"
RC_FORMAT = "pof-release-candidate/1"
CONTRACTS = ("TestCoin", "CoinFaucet", "PoolV3", "RegistryMaker", "Validators", "PanelScores", "FeesV3", "Panels",
             "RaceV3Endings", "RaceV3Annex", "RaceV3")
COIN_DECIMALS = 6
GENESIS_BOND_COINS = 250  # the genesis validator's bond (L17), paid from the genesis mint
GENESIS_MINT_COINS = 5_000  # L17, 2026-11-20: 15 bonds of $250 (3,750) and 1,250 to seed bounties
RC_CHECKS = ("productionWindows", "sevSnpValidator", "realModelRun", "attestedImages")
# The panel rules (#251 batch 4, L23, L24), as the records name them; the defaults are #132's, the Sepolia launch's
# `launch`, 3 and `same`.
RULE_FIELDS = ("operatorCap", "hostCap", "teeCap", "kTop", "challengeSize")
PANEL_CAPS = ("strict", "launch")
CHALLENGE_SIZES = ("larger", "same")
RID_RE = re.compile(r"^rad:z[1-9A-HJ-NP-Za-km-z]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
B32_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
REFUSED = 2


class Refused(Exception):
    """A check failed: nothing was signed or sent."""


def say(msg: str) -> None:
    print(f"deploy-sepolia: {msg}", file=sys.stderr)


# ---------- the endpoint ----------

def is_local(url: str) -> bool:
    """A local endpoint: plain http on 127.0.0.1, localhost or [::1] exactly, with no user part. Anything else (another
    loopback address, a name that merely starts with localhost, https) counts as remote."""
    try:
        u = urlsplit(url)
        host = u.hostname
        u.port  # noqa: B018  (raises on a malformed port)
    except ValueError:
        return False
    return u.scheme == "http" and "@" not in u.netloc and host in LOCAL_HOSTS


def check_url(url: str) -> None:
    try:
        u = urlsplit(url)
        u.port  # noqa: B018
    except ValueError:
        raise Refused("the RPC URL is malformed") from None
    if u.scheme not in ("http", "https") or not u.hostname:
        raise Refused("the RPC URL must be http(s)://host…")
    if "@" in u.netloc:
        raise Refused("the RPC URL carries a user part; give the endpoint without credentials in its authority")
    if not is_local(url) and u.scheme != "https":
        raise Refused("a remote endpoint must be https (only a local endpoint, 127.0.0.1, localhost or [::1], is http)")


def rpc(url: str, method: str, params: list, timeout: float = 15.0):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310  (http(s) only, checked)
            reply = json.loads(r.read().decode())
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Refused(f"the endpoint didn't answer {method} ({type(e).__name__})") from None
    if "error" in reply:
        raise Refused(f"the endpoint refused {method}: {reply['error']}")
    return reply.get("result")


def chain_id(url: str) -> int:
    v = rpc(url, "eth_chainId", [])
    try:
        return int(v, 16)
    except (TypeError, ValueError):
        raise Refused(f"the endpoint's chain id isn't a number: {v!r}") from None


def check_chain(cid: int, local: bool) -> None:
    """L2: Sepolia only; the local test ids only for a local endpoint (a public chain could reuse them)."""
    if cid == SEPOLIA:
        return
    if cid in LOCAL_IDS:
        if local:
            return
        raise Refused(f"chain {cid} is a local test id, refused for a non-local endpoint: Sepolia (11155111) only")
    raise Refused(f"chain {cid} refused: Sepolia (11155111) only")


# ---------- the release candidate (L18) ----------

def git_head(root: Path = ROOT) -> str:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if r.returncode:
        raise Refused("this checkout's commit can't be read (git rev-parse HEAD)")
    return r.stdout.strip()


def contains(commit: str, root: Path = ROOT) -> bool:
    r = subprocess.run(["git", "-C", str(root), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True)
    return r.returncode == 0


def panel_rules(caps: str = "strict", k_top: int = 7, size: str = "larger") -> dict:
    """The panel rules from the flags, named as the records name them (#251 batch 4): refused unless the caps are
    `strict` or `launch`, kTop odd from 1 to 7 and the challenge size `larger` or `same`."""
    if caps not in PANEL_CAPS:
        raise Refused(f"--panel-caps is strict or launch, not {caps!r}")
    if not isinstance(k_top, int) or isinstance(k_top, bool) or not 1 <= k_top <= 7 or k_top % 2 == 0:
        raise Refused(f"--k-top is an odd number from 1 to 7, not {k_top!r}")
    if size not in CHALLENGE_SIZES:
        raise Refused(f"--challenge-size is larger or same, not {size!r}")
    cap = "strict" if caps == "strict" else "off"
    return {"operatorCap": cap, "hostCap": cap, "teeCap": cap, "kTop": k_top, "challengeSize": size}


def _rules_text(r: dict) -> str:
    return ", ".join(f"{k} {r.get(k)}" for k in RULE_FIELDS)


def load_release_candidate(path: str, root: Path = ROOT, rules: dict | None = None) -> dict:
    """The record, refused unless it's `pof-release-candidate/1`, passed in every L18 item (the integration suite's
    last 3 runs in a row), names exactly this script's contracts with a 32-byte hash each, names a commit this
    checkout contains, and names every panel rule (`panelRules`), which must be `rules` when given (the deployment's:
    the run tested those rules, #251 batch 4). The bytecode itself is compared by forge, which compiles it."""
    p = Path(path)
    if not p.is_file():
        raise Refused(f"no release-candidate record at {path}")
    try:
        rc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refused(f"the release-candidate record isn't JSON ({e})") from None
    if not isinstance(rc, dict) or rc.get("format") != RC_FORMAT:
        raise Refused(f"the release-candidate record isn't {RC_FORMAT}")
    if rc.get("result") != "passed":
        raise Refused(f"the release-candidate record's run didn't pass (result {rc.get('result')!r})")
    checks = rc.get("checks") or {}
    runs = (checks.get("integration") or {}).get("runs") if isinstance(checks.get("integration"), dict) else None
    if not isinstance(runs, list) or len(runs) < 3 or any(r != "passed" for r in runs[-3:]):
        raise Refused("the release-candidate record doesn't show the integration suite passing 3 runs in a row")
    for c in RC_CHECKS:
        if checks.get(c) != "passed":
            raise Refused(f"the release-candidate record's {c} check didn't pass ({checks.get(c)!r})")
    commit = str(rc.get("commit", "")).lower()
    if not SHA_RE.match(commit):
        raise Refused("the release-candidate record names no commit (a 40-hex SHA-1)")
    if not contains(commit, root):
        raise Refused(f"the release-candidate record's commit {commit[:12]} isn't this checkout's HEAD or an ancestor")
    code = rc.get("bytecode")
    if not isinstance(code, dict) or set(code) != set(CONTRACTS):
        raise Refused(f"the release-candidate record must name exactly these contracts' bytecode: {', '.join(CONTRACTS)}")
    for name, h in code.items():
        if not isinstance(h, str) or not B32_RE.match(h):
            raise Refused(f"the release-candidate record's hash for {name} isn't 32 bytes")
    pr = rc.get("panelRules")
    if not isinstance(pr, dict) or set(pr) != set(RULE_FIELDS):
        raise Refused(f"the release-candidate record must name every panel rule: {', '.join(RULE_FIELDS)}")
    if rules is not None and pr != rules:
        raise Refused(f"the release-candidate record ran with other panel rules ({_rules_text(pr)}), not the ones asked "
                      f"for ({_rules_text(rules)})")
    return rc


# ---------- the plan ----------

def _b32(v, what: str, nonzero: bool = True) -> str:
    if not isinstance(v, str) or not B32_RE.match(v) or (nonzero and int(v, 16) == 0):
        raise Refused(f"the plan's {what} must be a nonzero 0x bytes32")
    return v.lower()


def _addr(v, what: str) -> str:
    if not isinstance(v, str) or not ADDR_RE.match(v) or int(v, 16) == 0:
        raise Refused(f"the plan's {what} must be a nonzero address")
    return v


def _names(v, what: str) -> list:
    if not isinstance(v, list) or not v or not all(isinstance(n, str) and NAME_RE.match(n) for n in v):
        raise Refused(f"the plan's {what} must be a nonempty list of names (letters, digits, '.', '_', '-')")
    if len(set(v)) != len(v):
        raise Refused(f"the plan's {what} repeat a name")
    return v


def load_plan(path: str, genesis_key: int | None) -> dict:
    p = Path(path)
    if not p.is_file():
        raise Refused(f"no plan at {path}")
    try:
        plan = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise Refused(f"the plan isn't JSON ({e})") from None
    if not isinstance(plan, dict):
        raise Refused("the plan must be a JSON object")
    if not isinstance(plan.get("rid"), str) or not RID_RE.match(plan["rid"]):
        raise Refused("the plan's rid must be a Radicle RID (rad:z…)")
    head = str(plan.get("genesisHead", "")).lower()
    if not SHA_RE.match(head):
        raise Refused("the plan's genesisHead must be a 40-hex SHA-1 (Radicle main)")
    plan["genesisHead"] = head
    _names(plan.get("families"), "families")
    _names(plan.get("teeTypes"), "teeTypes")
    images = plan.get("images")
    if not isinstance(images, list) or not images:
        raise Refused("the plan's images must be a nonempty list")
    plan["images"] = [_b32(i, "images") for i in images]
    g = plan.get("genesisValidator")
    if not isinstance(g, dict):
        raise Refused("the plan has no genesisValidator")
    if genesis_key is not None:
        derived = address_of(genesis_key)
        if g.get("key") and str(g["key"]).lower() != derived.lower():
            raise Refused("the plan's genesis key isn't --genesis-dev-key's address")
        g["key"] = derived
    _addr(g.get("key"), "genesisValidator.key")
    _addr(g.get("operator"), "genesisValidator.operator")
    if g.get("teeType") not in plan["teeTypes"]:
        raise Refused("the plan's genesisValidator.teeType must be one of its teeTypes")
    if g.get("level") not in (1, 2):
        raise Refused("the plan's genesisValidator.level must be 1 (A) or 2 (B)")
    g["attestation"] = _b32(g.get("attestation"), "genesisValidator.attestation")
    g["image"] = _b32(g.get("image"), "genesisValidator.image")
    if g["image"] not in plan["images"]:
        raise Refused("the plan's genesisValidator.image must be one of its images")
    g["host"] = _b32(g.get("host"), "genesisValidator.host")
    fw = g.get("firmware", 0)
    if not isinstance(fw, int) or not 0 <= fw < 2**32:
        raise Refused("the plan's genesisValidator.firmware must be a 32-bit number")
    sig = g.get("signature")
    if sig is not None and (not isinstance(sig, str) or not re.match(r"^0x[0-9a-fA-F]{130}$", sig)):
        raise Refused("the plan's genesisValidator.signature must be 65 bytes of hex")
    return plan


# ---------- the test coin's genesis mint (L17) ----------

def genesis_mint(amount: str | None, to: str | None, deployer: str) -> tuple:
    """(micro-coins in total, the recipient): `--genesis-mint` in whole or decimal coins (default 5,000), at least the
    genesis bond and at most 6 decimals; `--genesis-mint-to` a nonzero address (default the deployer)."""
    text = str(GENESIS_MINT_COINS) if amount is None else str(amount).strip()
    if not re.match(r"^[0-9]+(\.[0-9]{1,6})?$", text):
        raise Refused("--genesis-mint is an amount of coins (up to 6 decimals), e.g. 5000")
    whole, _, frac = text.partition(".")
    micro = int(whole) * 10**COIN_DECIMALS + int((frac or "0").ljust(COIN_DECIMALS, "0"))
    if micro < GENESIS_BOND_COINS * 10**COIN_DECIMALS:
        raise Refused(f"--genesis-mint must cover the genesis bond ({GENESIS_BOND_COINS} coins)")
    if micro >= 2**128:
        raise Refused("--genesis-mint is implausibly large")
    recipient = deployer if to is None else to
    if not isinstance(recipient, str) or not ADDR_RE.match(recipient) or int(recipient, 16) == 0:
        raise Refused("--genesis-mint-to must be a nonzero address")
    return micro, recipient


# ---------- the genesis validator's Radicle node (#251, L11) ----------

def genesis_rad_node(value: str | None) -> tuple:
    """(the bytes32 hex, the did:key) of `--genesis-rad-node`: the genesis validator's Radicle node, a did:key:z6Mk…,
    its Node ID z6Mk… or 0x and 64 hex digits. It is signed into the genesis registration and stored on-chain, so it is
    required, and never zero (the genesis seat is the first delegate after the owner's node hands over)."""
    if not value:
        raise Refused("--genesis-rad-node: the genesis validator's Radicle node (did:key:z6Mk… from its `rad self "
                      "--did`, or 0x and 64 hex digits); it is signed into the genesis registration")
    try:
        key = parse_node(value)
    except ValueError as e:
        raise Refused(f"--genesis-rad-node: {e}") from None
    if not any(key):
        raise Refused("--genesis-rad-node: zero names no node; the genesis validator's seat needs one")
    return "0x" + key.hex(), did_from_key(key)


# ---------- the genesis head ----------

def verify_head(cmd: list, rid: str, head: str) -> str:
    """`pofctl verify-head --rid RID --commit HEAD` (or the command given): exit 0 or a refusal with its message."""
    try:
        r = subprocess.run(cmd + ["--rid", rid, "--commit", head], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Refused(f"verify-head couldn't run ({type(e).__name__})") from None
    out = (r.stdout + r.stderr).strip()
    if r.returncode:
        raise Refused(f"the genesis head isn't the repository's canonical main: {out[-400:] or 'exit %d' % r.returncode}")
    return out


# ---------- forge ----------

def forge(script: str, env: dict, stdin: str = "", network: str = "host", mounts=(), tty: bool = False) -> tuple:
    """Runs `script` (a shell command line using $DEPLOY_* from `env`) with forge: in the pinned image, or in the
    container DEPLOY_FORGE_CONTAINER names. Values go in the environment (names only on the command line)."""
    names = sorted(env)
    full = {**os.environ, **env}
    container = os.environ.get("DEPLOY_FORGE_CONTAINER")
    flags = ["-it"] if tty else ["-i"]
    if container:
        cmd = ["docker", "exec", *flags, "-w", "/work"]
        for n in names:
            cmd += ["-e", n]
        cmd += [container, "sh", "-c", script]
    else:
        solc = _solc()
        cmd = ["docker", "run", "--rm", *flags, "--network", network, "--user", f"{os.getuid()}:{os.getgid()}",
               "-e", "HOME=/tmp"]
        for n in names:
            cmd += ["-e", n]
        cmd += ["-v", f"{ROOT / 'contracts'}:/work", "-v", f"{solc}:/opt/solc/solc:ro"]
        for src, dst in mounts:
            cmd += ["-v", f"{src}:{dst}:ro"]
        cmd += ["-w", "/work", "--entrypoint", "sh", FOUNDRY_IMAGE, "-c", script]
    if tty:
        r = subprocess.run(cmd, env=full)
        return r.returncode, ""
    r = subprocess.run(cmd, env=full, input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def _solc() -> Path:
    r = subprocess.run(["bash", "-c", "source scripts/solc.sh && echo \"$SOLC\""], cwd=ROOT, capture_output=True,
                       text=True)
    p = ROOT / r.stdout.strip()
    if r.returncode or not p.is_file():
        raise Refused("the pinned solc is missing: run scripts/contracts.sh setup")
    return p


def revert_reason(out: str) -> str:
    for pat in (r"(?:revert|reverted)[:,]?\s*(.+)", r"Error:\s*(.+)"):
        found = re.findall(pat, out)
        if found:
            return found[-1].strip()
    return out.strip().splitlines()[-1] if out.strip() else "forge failed"


def hashes() -> dict:
    code, out = forge(f"forge script {SCRIPT} --sig 'hashes()'", {}, network="none")
    if code:
        raise Refused(f"forge couldn't compute the hashes: {revert_reason(out)}")
    found = dict(re.findall(r"BYTECODE (\w+) (0x[0-9a-f]{64})", out))
    if set(found) != set(CONTRACTS):
        raise Refused("forge's output doesn't list every contract's hash")
    return {n: found[n] for n in CONTRACTS}


# ---------- deploy ----------

def record_name(cid: int, local: bool, broadcast: bool) -> str:
    base = f"sepolia-local/chain-{cid}" if local else "sepolia-v3"
    return base + ("" if broadcast else ".dry-run") + ".json"


def deploy(a) -> int:
    url = a.rpc_url or os.environ.get("DEPLOY_RPC_URL", "")
    if not url:
        raise Refused("no endpoint: --rpc-url or DEPLOY_RPC_URL")
    check_url(url)
    local = is_local(url)
    if not local and (a.dev_key is not None or a.genesis_dev_key is not None):
        raise Refused("anvil's public test keys (--dev-key, --genesis-dev-key) are for a local endpoint only")
    if a.dev_key is not None and a.keystore:
        raise Refused("one signer: --keystore or --dev-key")
    if a.broadcast_sepolia and a.dev_key is None and not a.keystore:
        raise Refused("--broadcast-sepolia needs a signer: --keystore FILE (or --dev-key N on a local endpoint)")
    if a.record and (".." in Path(a.record).parts or Path(a.record).is_absolute() or not a.record.endswith(".json")):
        raise Refused("--record is a .json path under contracts/deployments")
    gkey = derive(MNEMONIC, a.genesis_dev_key) if a.genesis_dev_key is not None else None
    plan = load_plan(a.plan, gkey)
    deployer = _deployer(a)
    mint, mint_to = genesis_mint(a.genesis_mint, a.genesis_mint_to, deployer)
    rad_key, rad_did = genesis_rad_node(a.genesis_rad_node)
    rules = panel_rules(a.panel_caps, a.k_top, a.challenge_size)

    cid = chain_id(url)  # before anything is signed
    check_chain(cid, local)
    say(f"chain {cid}, {'a local endpoint' if local else 'a remote endpoint'}; deployer {deployer}")

    rc = load_release_candidate(a.release_candidate, rules=rules)
    say(f"release candidate {rc.get('tag', '?')} at {rc['commit'][:12]}: passed")

    cmd = shlex.split(a.verify_head_cmd) if a.verify_head_cmd else [sys.executable, "-m", "pofctl", "verify-head"]
    if not a.verify_head_cmd and a.rad_exec:
        cmd += ["--rad-exec", a.rad_exec]
    if not a.verify_head_cmd and a.repo_dir:
        cmd += ["--repo-dir", a.repo_dir]
    checked = verify_head(cmd, plan["rid"], plan["genesisHead"])
    say(f"genesis head {plan['genesisHead'][:12]} is {plan['rid']}'s canonical main")

    name = a.record or record_name(cid, local, a.broadcast_sepolia)
    out = ROOT / "contracts" / "deployments" / name
    out.parent.mkdir(parents=True, exist_ok=True)
    env = _env(plan, rc, deployer, url, name, gkey)
    env["DEPLOY_GENESIS_MINT"] = str(mint)
    env["DEPLOY_GENESIS_MINT_TO"] = mint_to
    env["DEPLOY_GENESIS_RAD_NODE"] = rad_key
    env["DEPLOY_PANEL_CAPS"] = a.panel_caps
    env["DEPLOY_K_TOP"] = str(a.k_top)
    env["DEPLOY_CHALLENGE_SIZE"] = a.challenge_size
    script = f'forge script {SCRIPT} --rpc-url "$DEPLOY_RPC_URL" --sender "$DEPLOY_DEPLOYER"'
    stdin, mounts, tty = "", (), False
    if a.broadcast_sepolia:
        script += " --broadcast --slow"
        if a.dev_key is not None:
            script = 'read -r PK; ' + script + ' --private-key "$PK"'
            stdin = hex(derive(MNEMONIC, a.dev_key)) + "\n"
        else:
            ks = Path(a.keystore).resolve()
            mounts = ((ks, "/keystore/key.json"),)
            script += " --keystore /keystore/key.json"
            tty = True  # forge asks for the password
    if out.exists():
        out.unlink()  # never report a stale record
    run_file = ROOT / "contracts" / "broadcast" / "DeploySepolia.s.sol" / str(cid) / (
        "run-latest.json" if a.broadcast_sepolia else "dry-run/run-latest.json")
    if run_file.exists():
        run_file.unlink()
    code, log = forge(script, env, stdin=stdin, mounts=mounts, tty=tty)
    if code:
        if log:
            sys.stderr.write("\n".join(log.strip().splitlines()[-25:]) + "\n")
        if a.broadcast_sepolia:  # forge simulates first and sends nothing if that fails; a later failure can't be undone
            raise Refused(f"forge stopped: {revert_reason(log)} (check the deployer's nonce and contracts/broadcast "
                          "for anything already sent)")
        raise Refused(f"forge refused the deployment: {revert_reason(log)}")
    if not out.is_file():
        raise Refused(f"forge wrote no record at {out}")

    record = json.loads(out.read_text(encoding="utf-8"))
    if int(record["chainId"]) != cid or record["deployer"].lower() != deployer.lower():
        raise Refused("the record's chain or deployer isn't the one checked")
    gm = (record.get("testCoin") or {}).get("genesisMint") or {}
    if int(gm.get("total", -1)) != mint or str(gm.get("restTo", "")).lower() != mint_to.lower():
        raise Refused("the record's genesis mint isn't the one asked for")
    if str(_genesis_args(record).get("radNode", "")).lower() != rad_key:
        raise Refused("the record's genesis Radicle node key isn't the one asked for")
    if isinstance(record.get("panelRules"), str):  # forge writes a nested JSON object, or its text
        try:
            record["panelRules"] = json.loads(record["panelRules"])
        except ValueError:
            pass
    if record.get("panelRules") != rules:
        raise Refused(f"the record's panel rules ({_rules_text(record.get('panelRules') or {})}) aren't the ones asked "
                      f"for ({_rules_text(rules)})")
    record["libraries"] = libraries(run_file)
    if a.broadcast_sepolia:
        _check_deployed(url, record, cid)
        _check_rules(url, record, rules)
    record.update({
        "dryRun": not a.broadcast_sepolia,
        "endpoint": "local" if local else "remote",
        "commit": git_head(),
        "releaseCandidate": {"path": _rel(a.release_candidate), "tag": rc.get("tag"), "commit": rc["commit"]},
        "genesisHeadCheck": {"rid": plan["rid"], "commit": plan["genesisHead"], "result": checked[-300:]},
        "genesisRadNode": {"key": rad_key, "did": rad_did, "registry": "Validators.radNodeOf(genesis key)"},
    })
    out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verb = "deployed" if a.broadcast_sepolia else "dry run passed (nothing sent)"
    say(f"{verb}: RaceV3 {record['addresses']['race']}; record {out.relative_to(ROOT)}")
    return 0


def _genesis_args(record: dict) -> dict:
    """The genesis validator's registration as the record's constructor arguments give it."""
    found = ((record.get("constructorArgs") or {}).get("Validators") or {}).get("validators") or {}
    if isinstance(found, str):
        try:
            found = json.loads(found)
        except ValueError:
            return {}
    return found if isinstance(found, dict) else {}


def _deployer(a) -> str:
    if a.dev_key is not None:
        derived = address_of(derive(MNEMONIC, a.dev_key))
        if a.deployer and a.deployer.lower() != derived.lower():
            raise Refused("--deployer isn't --dev-key's address")
        return derived
    found = a.deployer
    if a.keystore:
        try:
            ks = json.loads(Path(a.keystore).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Refused("the keystore file can't be read as JSON") from None
        addr = ks.get("address") if isinstance(ks, dict) else None
        if addr:
            addr = addr if addr.startswith("0x") else "0x" + addr
            if found and found.lower() != addr.lower():
                raise Refused("--deployer isn't the keystore's address")
            found = addr
    if not found or not ADDR_RE.match(found):
        raise Refused("the deploying address: --deployer 0x… (or a signer that names it)")
    return found


def _env(plan: dict, rc: dict, deployer: str, url: str, name: str, gkey: int | None) -> dict:
    g = plan["genesisValidator"]
    env = {
        "DEPLOY_RPC_URL": url,
        "DEPLOY_DEPLOYER": deployer,
        "DEPLOY_RECORD": name,
        "DEPLOY_RC_NAMES": ",".join(rc["bytecode"]),
        "DEPLOY_RC_HASHES": ",".join(rc["bytecode"].values()),
        "DEPLOY_RID": plan["rid"],
        "DEPLOY_GENESIS_HEAD": "0x" + plan["genesisHead"] + "0" * 24,
        "DEPLOY_CONSTITUTION": "0x" + keccak256((ROOT / "CONSTITUTION.md").read_bytes()).hex(),
        "DEPLOY_FAMILIES": ",".join(plan["families"]),
        "DEPLOY_TEE_TYPES": ",".join(plan["teeTypes"]),
        "DEPLOY_IMAGES": ",".join(plan["images"]),
        "DEPLOY_GENESIS_KEY": g["key"],
        "DEPLOY_GENESIS_OPERATOR": g["operator"],
        "DEPLOY_GENESIS_TEE_TYPE": g["teeType"],
        "DEPLOY_GENESIS_LEVEL": str(g["level"]),
        "DEPLOY_GENESIS_ATTESTATION": g["attestation"],
        "DEPLOY_GENESIS_IMAGE": g["image"],
        "DEPLOY_GENESIS_HOST": g["host"],
        "DEPLOY_GENESIS_FIRMWARE": str(g.get("firmware", 0)),
    }
    if gkey is not None:
        env["DEPLOY_GENESIS_PK"] = hex(gkey)
    elif g.get("signature"):
        env["DEPLOY_GENESIS_SIG"] = g["signature"]
    return env


def libraries(run_file: Path) -> dict:
    """Panels' linked libraries, which forge deploys itself through the CREATE2 deployer (so their addresses, and
    Panels' linked creation code with them, follow from their code): from forge's run file."""
    try:
        found = json.loads(run_file.read_text(encoding="utf-8")).get("libraries") or []
    except (OSError, ValueError):
        raise Refused(f"forge left no run file ({run_file.relative_to(ROOT)}) to read the linked libraries from") from None
    out = {}
    for entry in found:  # "src/v3/PanelsDraw.sol:PanelsDraw:0x…"
        _, name, addr = entry.rsplit(":", 2)
        out[name] = addr
    return out


def _check_deployed(url: str, record: dict, cid: int) -> None:
    """After a broadcast: every address (the linked libraries' too) has code, and the race reports this chain."""
    for what, addr in [*record["addresses"].items(), *record["libraries"].items()]:
        if rpc(url, "eth_getCode", [addr, "latest"]) in (None, "0x", "0x0"):
            raise Refused(f"no code at the record's {what} ({addr}) after the broadcast")
    got = rpc(url, "eth_call", [{"to": record["addresses"]["race"],
                                 "data": "0x" + keccak256(b"chainId()")[:4].hex()}, "latest"])
    if int(got or "0x0", 16) != cid:
        raise Refused(f"the race reports chain {int(got or '0x0', 16)}, not {cid}")


def read_rules(url: str, panels: str) -> dict:
    """Panels' `panelRules()` on the chain, named as the records name them."""
    out = rpc(url, "eth_call", [{"to": panels, "data": "0x" + keccak256(b"panelRules()")[:4].hex()}, "latest"])
    raw = bytes.fromhex((out or "0x")[2:])
    if len(raw) < 5 * 32:
        raise Refused(f"Panels at {panels} doesn't answer panelRules()")
    w = [int.from_bytes(raw[32 * i:32 * i + 32], "big") for i in range(5)]
    if any(x > 1 for x in (w[0], w[1], w[2], w[4])):
        raise Refused("Panels' panelRules() isn't a rules tuple")
    caps = ("strict", "off")
    return {"operatorCap": caps[w[0]], "hostCap": caps[w[1]], "teeCap": caps[w[2]], "kTop": w[3],
            "challengeSize": CHALLENGE_SIZES[w[4]]}


def _check_rules(url: str, record: dict, rules: dict) -> None:
    """After a broadcast: the deployed Panels reads back the rules asked for (#251 batch 4)."""
    got = read_rules(url, record["addresses"]["panels"])
    if got != rules:
        raise Refused(f"the deployed Panels has other panel rules ({_rules_text(got)}), not the ones asked for "
                      f"({_rules_text(rules)})")


def _rel(path: str) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(path)


# ---------- the command line ----------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="deploy-sepolia.sh", description="v3 on Sepolia (#251 task 3.9): a dry run "
                                "unless --broadcast-sepolia.")
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("deploy", help="check everything, simulate, and broadcast only with --broadcast-sepolia")
    d.add_argument("--rpc-url", help="the endpoint (default DEPLOY_RPC_URL); never printed")
    d.add_argument("--plan", required=True, help="the deployment plan (JSON; see this file's docstring)")
    d.add_argument("--release-candidate", required=True, help="the passing release-candidate record (L18)")
    d.add_argument("--broadcast-sepolia", action="store_true", help="sign and send; without it nothing is sent")
    d.add_argument("--deployer", help="the deploying address (for a dry run, when no signer names it)")
    d.add_argument("--keystore", help="the deployer's keystore file (forge asks for its password)")
    d.add_argument("--dev-key", type=int, help="local endpoint only: anvil's public test key N as the deployer")
    d.add_argument("--genesis-dev-key", type=int, help="local endpoint only: anvil's key N signs as the genesis validator")
    d.add_argument("--verify-head-cmd", help="replaces `python3 -m pofctl verify-head` (gets --rid and --commit)")
    d.add_argument("--rad-exec", help="pofctl verify-head's --rad-exec: the command prefix reaching the Radicle node")
    d.add_argument("--repo-dir", help="pofctl verify-head's --repo-dir")
    d.add_argument("--record", help="the record's path under contracts/deployments (default by chain and mode)")
    d.add_argument("--genesis-mint", metavar="AMOUNT", help=f"the test coin's genesis mint in coins, in total (default "
                   f"{GENESIS_MINT_COINS:,}); the genesis bond ({GENESIS_BOND_COINS}) goes to the registry")
    d.add_argument("--genesis-mint-to", metavar="ADDRESS", help="the genesis mint's recipient (default the deployer)")
    d.add_argument("--genesis-rad-node", metavar="DID", help="required: the genesis validator's Radicle node, "
                   "did:key:z6Mk… (its `rad self --did`) or 0x and 64 hex digits; signed into its registration and "
                   "stored on-chain (#251, L11)")
    d.add_argument("--panel-caps", default="strict", help="the operator, host and TEE-type caps (#251 L23): strict "
                   "(default, #132's) or launch (all off, the Sepolia record's)")
    d.add_argument("--k-top", type=int, default=7, help="the largest issue-tier panel (L24): odd, 1 to 7 (default 7; "
                   "Sepolia 3)")
    d.add_argument("--challenge-size", default="larger", help="a challenge panel's size (L24): larger (default, D4) "
                   "or same (the Sepolia record's)")
    d.set_defaults(fn=deploy)
    h = sub.add_parser("hashes", help="print each contract's creation-code hash (a release-candidate record's)")
    h.set_defaults(fn=lambda a: print(json.dumps({"bytecode": hashes()}, indent=2)) or 0)
    return p


def main(argv: list | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.fn(a)
    except Refused as e:
        say(f"refused: {e}")
        return REFUSED


if __name__ == "__main__":
    sys.exit(main())
