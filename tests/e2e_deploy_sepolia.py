"""The Sepolia deploy script against local anvils (proof-of-fix#251, task 3.9; run by scripts/deploy-sepolia-e2e.sh).

Each scenario starts a fresh anvil in the pinned Foundry image, published on 127.0.0.1 only, and runs
scripts/deploy-sepolia.sh against it with anvil's public test keys (key 0 deploys, key 1 is the genesis validator)
and forge inside the same container (DEPLOY_FORGE_CONTAINER). The genesis head is checked by the real
`pofctl verify-head`, reaching a fake Radicle node (tests/fake_radicle.py) whose canonical `main` the scenario sets.
No other network: nothing here names a public endpoint.

1. chain id 1, with --broadcast-sepolia: refused, naming the chain; the deployer's nonce is 0 and no block was mined;
2. chain id 11155111, a genesis head that isn't the repository's canonical main: refused, nothing sent;
3. chain id 11155111, a release-candidate record whose Panels hash differs: refused, naming Panels, nothing sent;
4. chain id 11155111, the right head: with no genesis signature the dry run refuses and prints the digest to sign;
   signed outside the script it passes, and so does a plan signed by scripts/genesis-validator.sh `sign` from a secret
   (task 7.1: its GENESIS_DIGEST is forge's); the dry run sends nothing and writes its record; then --broadcast-sepolia
   deploys the test coin's faucet (and with it the coin, the genesis mint to the deployer by default) and the rest,
   and the record and the chain agree; a claim from the deployed faucet pays 20 coins and a second is refused;
5. chain id 31337 on the local endpoint: the same test coin (no mock coin), the genesis mint of 6,000 coins to
   another address (--genesis-mint-to, --genesis-mint).

No coin is planted: the deployment brings its own (design L17, 2026-11-20)."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from fake_radicle import snapshot  # noqa: E402
from oracle.crypto import address, keccak256, sign  # noqa: E402
from oracle.delegates import did_from_key  # noqa: E402
from pofctl.keys import MNEMONIC, derive  # noqa: E402

_spec = importlib.util.spec_from_file_location("genesis_validator", ROOT / "scripts" / "genesis_validator.py")
GV = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(GV)

IMAGE = "ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
NAME = os.environ.get("POF_DEPLOY_E2E_NAME", "pof-deploy-sepolia-e2e")
PORT = int(os.environ.get("POF_DEPLOY_E2E_PORT", "8561"))
URL = f"http://127.0.0.1:{PORT}"
RID = "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5"  # a well-formed RID for the test; nothing is published or fetched
HEAD = "1111111111111111111111111111111111111111"
OTHER = "2222222222222222222222222222222222222222"
DEPLOYER = address(derive(MNEMONIC, 0))
CLAIMANT = address(derive(MNEMONIC, 9))  # claims from the faucet (anvil's accounts are unlocked)
RECIPIENT = address(derive(MNEMONIC, 5))  # scenario 5's genesis mint recipient
RECORDS = ROOT / "contracts" / "deployments" / "sepolia-local"
RAD_KEY = keccak256(b"the genesis validator's Radicle node (test)")  # #251, L11: an Ed25519 key's 32 bytes
RAD_DID = did_from_key(RAD_KEY)


def sh(*cmd, **kw):
    return subprocess.run(list(cmd), capture_output=True, text=True, **kw)


def rpc(method, params=()):
    req = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                                       "params": list(params)}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        reply = json.loads(r.read().decode())
    if "error" in reply:
        raise RuntimeError(f"{method}: {reply['error']}")
    return reply["result"]


def solc() -> str:
    return sh("bash", "-c", "source scripts/solc.sh && echo \"$SOLC\"", cwd=ROOT).stdout.strip()


def start(chain: int) -> None:
    stop()
    r = sh("docker", "run", "-d", "--name", NAME, "-p", f"127.0.0.1:{PORT}:{PORT}", "--user",
           f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp", "-v", f"{ROOT / 'contracts'}:/work", "-v",
           f"{ROOT / solc()}:/opt/solc/solc:ro", "-w", "/work", "--entrypoint", "anvil", IMAGE, "--host", "0.0.0.0",
           "--port", str(PORT), "--chain-id", str(chain), "--silent")
    if r.returncode:
        raise SystemExit(f"anvil didn't start: {r.stderr}")
    for _ in range(120):
        try:
            if int(rpc("eth_chainId"), 16) == chain:
                return
        except Exception:  # noqa: BLE001  (not up yet)
            pass
        time.sleep(0.5)
    raise SystemExit("anvil didn't answer")


def stop() -> None:
    sh("docker", "rm", "-f", NAME)


def nonce(who: str) -> int:
    return int(rpc("eth_getTransactionCount", [who, "latest"]), 16)


def blocks() -> int:
    return int(rpc("eth_blockNumber"), 16)


class KeySecret:
    """The genesis validator's secret for scripts/genesis_validator.py, in memory (anvil's public key 1)."""

    def __init__(self, key: int) -> None:
        self.key = key

    def read(self) -> str:
        return f"{self.key:064x}"

    def write(self, value: str) -> None:
        raise AssertionError("signing never writes the secret")


class Rig:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.snap = work / "snapshot"
        self.plan = work / "plan.json"
        image = "0x" + keccak256(b"the checker image").hex()
        self.plan.write_text(json.dumps({
            "rid": RID, "genesisHead": HEAD, "families": ["fake", "fake-1"],
            "teeTypes": ["amd-sev-snp", "intel-tdx"], "images": [image],
            "genesisValidator": {"operator": address(derive(MNEMONIC, 2)), "teeType": "amd-sev-snp", "level": 1,
                                 "attestation": "0x" + keccak256(b"a test attestation").hex(), "image": image,
                                 "host": "0x" + keccak256(b"a test host").hex(), "firmware": 0},
        }), encoding="utf-8")

    def deploy(self, *extra, rc: Path, head: str = HEAD, plan: Path | None = None, genesis_key: bool = True):
        self.snap.write_text(snapshot(head), encoding="utf-8")
        rad = f"{sys.executable} {ROOT / 'tests' / 'fake_radicle.py'} {self.snap}"
        signer = ["--genesis-dev-key", "1"] if genesis_key else []
        r = sh(str(ROOT / "scripts" / "deploy-sepolia.sh"), "deploy", "--rpc-url", URL, "--plan", str(plan or self.plan),
               "--release-candidate", str(rc), "--dev-key", "0", *signer, "--rad-exec", rad,
               "--genesis-rad-node", RAD_DID, *extra,
               env={**os.environ, "DEPLOY_FORGE_CONTAINER": NAME}, timeout=1800)
        print(r.stderr.strip()[-1500:])
        return r

    def signed_plan(self, digest: str) -> Path:
        """The plan with the genesis validator's signature over the digest a dry run printed, made outside the
        script, as an enclave-held key would sign it on Sepolia."""
        plan = json.loads(self.plan.read_text(encoding="utf-8"))
        g = plan["genesisValidator"]
        g["key"] = address(derive(MNEMONIC, 1))
        g["signature"] = "0x" + sign(derive(MNEMONIC, 1), bytes.fromhex(digest[2:])).hex()
        p = self.work / "plan-signed.json"
        p.write_text(json.dumps(plan), encoding="utf-8")
        return p

    def release_candidate(self, tamper: str = "", rules: dict | None = None) -> Path:
        r = sh(str(ROOT / "scripts" / "deploy-sepolia.sh"), "hashes", env={**os.environ, "DEPLOY_FORGE_CONTAINER": NAME},
               timeout=1800)
        assert r.returncode == 0, r.stderr
        code = json.loads(r.stdout)["bytecode"]
        if tamper:
            code[tamper] = "0x" + keccak256(b"another build").hex()
        commit = sh("git", "-C", str(ROOT), "rev-parse", "HEAD").stdout.strip()
        rc = {"format": "pof-release-candidate/1", "tag": "e2e", "commit": commit, "result": "passed",
              "checks": {"integration": {"command": f"scripts/integration.sh --release-candidate {commit}",
                                         "runs": ["passed"] * 3},
                         "productionWindows": "passed", "sevSnpValidator": "passed", "realModelRun": "passed",
                         "attestedImages": "passed"},
              "panelRules": rules or STRICT, "bytecode": code}
        p = self.work / f"rc-{tamper or 'good'}-{(rules or STRICT)['kTop']}.json"
        p.write_text(json.dumps(rc), encoding="utf-8")
        return p


def check(cond: bool, what: str) -> None:
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    print(f"ok: {what}")


def receipt(tx: str) -> dict:
    for _ in range(60):
        got = rpc("eth_getTransactionReceipt", [tx])
        if got:
            if int(got["status"], 16) != 1:
                raise SystemExit(f"the transaction {tx} failed")
            return got
        time.sleep(0.25)
    raise SystemExit(f"no receipt for {tx}")


def call(to: str, sig: str, arg: str = "", sender: str = "") -> str:
    tx = {"to": to, "data": "0x" + keccak256(sig.encode())[:4].hex() + (arg[2:].lower().rjust(64, "0") if arg else "")}
    if sender:
        tx["from"] = sender
    return rpc("eth_call", [tx, "latest"])


def uint(v: str) -> int:
    return int(v, 16)


def coin_checks(rec: dict, recipient: str, total: int) -> None:
    """L17: the record and the chain agree on the test coin, its faucet, its genesis mint and the faucet's rule; a
    claim pays 20 coins and a second one at once is refused."""
    tc, adr = rec["testCoin"], rec["addresses"]
    coin, faucet = adr["coin"], adr["faucet"]
    check(tc["address"].lower() == coin.lower() == rec["coin"].lower() and tc["faucet"].lower() == faucet.lower(),
          "the record names the test coin and its faucet")
    check((tc["name"], tc["symbol"], tc["decimals"]) == ("proof-of-fix test coin", "POFTEST", 6),
          "the test coin: 'proof-of-fix test coin', POFTEST, 6 decimals")
    check(uint(call(coin, "faucet()")) == uint(faucet) and uint(call(faucet, "coin()")) == uint(coin),
          "the coin's only minter is the faucet that created it")
    g = tc["genesisMint"]
    check(g["total"] == total and g["genesisBond"] == 250 * 10**6 and g["rest"] == total - 250 * 10**6
          and g["restTo"].lower() == recipient.lower() and g["genesisBondTo"].lower() == adr["registryMaker"].lower(),
          "the record names the genesis mint: the bond to the registry maker, the rest to the recipient")
    check(uint(call(coin, "totalSupply()")) == total and uint(call(coin, "genesisMint()")) == total,
          "the supply is the genesis mint")
    check(uint(call(coin, "balanceOf(address)", adr["registry"])) == 250 * 10**6
          and uint(call(coin, "balanceOf(address)", adr["registryMaker"])) == 0, "the genesis bond is in the registry")
    check(uint(call(coin, "balanceOf(address)", recipient)) == total - 250 * 10**6, "the recipient holds the rest")
    rule = tc["faucetRule"]
    check(rule["claimAmount"] == 20 * 10**6 and rule["claimIntervalSeconds"] == 7200 and rule["per"] == "address"
          and rule["onlyMinter"] is True, "the record names the faucet's rule: 20 coins, 2 h, per address")
    claim = "0x" + keccak256(b"claim()")[:4].hex()
    got = receipt(rpc("eth_sendTransaction", [{"from": CLAIMANT, "to": faucet, "data": claim, "gas": hex(200_000)}]))
    ts = uint(rpc("eth_getBlockByNumber", [got["blockNumber"], False])["timestamp"])
    check(uint(call(coin, "balanceOf(address)", CLAIMANT)) == 20 * 10**6
          and uint(call(faucet, "nextClaim(address)", CLAIMANT)) == ts + 7200, "a claim pays 20 coins, next in 2 h")
    try:
        call(faucet, "claim()", sender=CLAIMANT)
        refused = False
    except RuntimeError:
        refused = True
    check(refused and uint(call(coin, "totalSupply()")) == total + 20 * 10**6, "a second claim at once is refused")


def pofctl_faucet(record: Path) -> None:
    """`pofctl faucet` against the deployed faucet, reading the deployment's own record (local chain: devnet keys)."""
    env = {**os.environ, "DEVNET_KEYS": "insecure-local"}
    env.pop("POFCTL_KEYSTORE", None)
    base = [sys.executable, "-m", "pofctl", "--rpc", URL, "--record", str(record), "--json"]
    r = sh(*base, "faucet", "--role", "funder", env=env, cwd=ROOT)
    got = json.loads(r.stdout) if r.returncode == 0 else {}
    print(r.stdout.strip()[-600:], r.stderr.strip()[-600:])
    check(got.get("claimed") == 20 * 10**6 and got.get("balance") == 20 * 10**6
          and 7200 <= got.get("nextClaim", 0) - got.get("now", 0) <= 7260,
          "pofctl faucet claims 20 coins for its key and prints the next claim time (2 h later)")
    r = sh(*base, "faucet", "--role", "funder", env=env, cwd=ROOT)
    check(r.returncode == 1 and "again at" in r.stderr and "Nothing was sent" in r.stderr,
          "pofctl faucet before the next claim time is refused, saying when, and sends nothing")


# The panel rules (#251 batch 4): the defaults, and the Sepolia launch's (`--panel-caps launch --k-top 3
# --challenge-size same`), as the records name them.
STRICT = {"operatorCap": "strict", "hostCap": "strict", "teeCap": "strict", "kTop": 7, "challengeSize": "larger"}
LAUNCH = {"operatorCap": "off", "hostCap": "off", "teeCap": "off", "kTop": 3, "challengeSize": "same"}
LAUNCH_FLAGS = ("--panel-caps", "launch", "--k-top", "3", "--challenge-size", "same")


def rules_on_chain(panels: str) -> dict:
    """Panels' panelRules() read back from the chain, named as the records name them."""
    raw = bytes.fromhex(call(panels, "panelRules()")[2:])
    w = [int.from_bytes(raw[32 * i:32 * i + 32], "big") for i in range(5)]
    caps = ("strict", "off")
    return {"operatorCap": caps[w[0]], "hostCap": caps[w[1]], "teeCap": caps[w[2]], "kTop": w[3],
            "challengeSize": ("larger", "same")[w[4]]}


def deployed(rig: Rig, rc: Path, chain: int, *mint: str, recipient: str = DEPLOYER, total: int = 5_000 * 10**6,
             rules: dict = STRICT) -> None:
    r = rig.deploy(*mint, rc=rc)
    dry = RECORDS / f"chain-{chain}.dry-run.json"
    check(r.returncode == 0 and dry.is_file(), f"chain {chain}: the dry run passes and writes its record")
    check(nonce(DEPLOYER) == 0, f"chain {chain}: the dry run sent nothing (deployer nonce 0)")
    check(json.loads(dry.read_text())["dryRun"] is True, f"chain {chain}: the dry run's record says so")

    r = rig.deploy("--broadcast-sepolia", *mint, rc=rc)
    out = RECORDS / f"chain-{chain}.json"
    check(r.returncode == 0 and out.is_file(), f"chain {chain}: --broadcast-sepolia deploys and writes the record")
    rec = json.loads(out.read_text())
    check(rec["chainId"] == chain and rec["dryRun"] is False, f"chain {chain}: the record names the chain")
    check(rec["deployer"].lower() == DEPLOYER.lower() and nonce(DEPLOYER) > 0, "the record names the deployer")
    check("a fork can remove both checks" in rec["limit"], "the record states the limit of the binding")
    check(rec["rid"] == RID and rec["repo"] == "0x" + keccak256(RID.encode()).hex(), "the record names RID and id")
    check(rec["genesisHead"] == "0x" + HEAD + "0" * 24, "the record names the genesis head")
    check(rec["genesisBond"] == 250 * 10**6, "the bond")
    fee, cfg = rec["judgesFee"], rec["constructorArgs"]["RaceV3"]["config"]
    check(fee["mode"] == "taxi" and fee["judgeFee"] == 0 and fee["inBytecode"] is True and cfg["judgeFee"] == 0,
          "the taxi fare: Config.judgeFee 0 (a fix's deposit's rest returns to its solver)")
    check(cfg["attemptFee"] == 0 and cfg["evaluationFee"] == 0 and cfg["appealFee"] == 0
          and fee["attemptFee"] == fee["evaluationFee"] == fee["appealFee"] == 0
          and cfg["registrationFee"] == 2 * 10**6 and cfg["issueStake"] == 5 * 10**6,
          "a solver pays only the metered validation: no attempt, evaluation or appeal fee; the reporter's fees stay")
    check(rec["windows"]["appeal"] == 72 * 3600 and rec["windows"]["active"] == 26 * 7 * 24 * 3600,
          "APPEAL_WINDOW 72 h and ACTIVE_WINDOW 26 weeks")
    check(rec["windows"]["challenge"][0][0] == 168 * 3600 and rec["windowsKind"] == "production",
          "the production windows")
    check(rec["windows"]["challengeDeadline"] == 120 * 3600, "CHALLENGE_DEADLINE 120 h (L25)")
    panels = rec["addresses"]["panels"]
    check(rec["panelRules"] == rules and rules_on_chain(panels) == rules,
          f"the panel rules ({rules['operatorCap']} caps, kTop {rules['kTop']}, {rules['challengeSize']} challenges) "
          "are in the record and read back from the deployed Panels")
    check(int(call(panels, "CHALLENGE_DEADLINE()"), 16) == 120 * 3600, "Panels' CHALLENGE_DEADLINE")
    check(rec["teeOnly"] is True, "TEE only")
    names = {"TestCoin", "CoinFaucet", "PoolV3", "RegistryMaker", "Validators", "PanelScores", "FeesV3", "Panels", "RaceV3Endings", "RaceV3Annex",
             "RaceV3"}
    check(names <= set(rec["constructorArgs"]) and all("encoded" in v for v in rec["constructorArgs"].values()),
          "every contract's constructor arguments")
    check(set(rec["bytecode"]) == names, "the bytecode hashes")
    check(set(rec["libraries"]) == {"PanelsDraw", "PanelsJudge", "PanelsVerdict"}, "Panels' linked libraries")
    for what, addr in [*rec["addresses"].items(), *rec["libraries"].items()]:
        check(rpc("eth_getCode", [addr, "latest"]) not in ("0x", "0x0"), f"code at {what}")
    race = rec["addresses"]["race"]
    check(int(call(race, "chainId()"), 16) == chain, "the race reports the chain")
    check(call(race, "repo()") == rec["repo"], "the race serves the one repository")
    check(int(call(race, "solverBook()"), 16) == int(rec["addresses"]["solverBook"], 16), "the race's SolverBook")
    check(int(call(rec["addresses"]["registry"], "teeOnly()"), 16) == 1, "the registry is TEE only")
    check(int(call(rec["addresses"]["registry"], "activeCount()"), 16) == 1, "the genesis validator is active")
    genesis = call(rec["addresses"]["registry"], "genesisKey()")
    on_chain = call(rec["addresses"]["registry"], "radNodeOf(address)", "0x" + genesis[-40:])
    check(on_chain == "0x" + RAD_KEY.hex() and rec["genesisRadNode"] == {"key": "0x" + RAD_KEY.hex(), "did": RAD_DID,
                                                                         "registry": "Validators.radNodeOf(genesis key)"}
          and rec["constructorArgs"]["Validators"]["validators"]["radNode"] == "0x" + RAD_KEY.hex(),
          f"the genesis validator's Radicle node ({RAD_DID[:20]}…) is signed into its registration and on-chain "
          "(radNodeOf), and the record names it")
    check(rec["network"] == ("sepolia" if chain == 11_155_111 else "local"), "the record names the network")
    coin_checks(rec, recipient, total)
    if chain != 11_155_111:
        pofctl_faucet(out)


def main() -> int:
    passed = 0
    with tempfile.TemporaryDirectory() as tmp:
        rig = Rig(Path(tmp))
        try:
            # 1. chain id 1: refused before anything else, even with the broadcast flag
            start(1)
            rc = rig.release_candidate()
            r = rig.deploy("--broadcast-sepolia", rc=rc)
            check(r.returncode == 2 and "chain 1 refused" in r.stderr, "chain 1: refused, naming the chain")
            check(nonce(DEPLOYER) == 0 and blocks() == 0, "chain 1: nothing sent (nonce 0, no block)")
            passed += 1

            # 2. 11155111, a wrong genesis head
            start(11_155_111)
            r = rig.deploy("--broadcast-sepolia", rc=rc, head=OTHER)
            check(r.returncode == 2 and "canonical main" in r.stderr, "a wrong genesis head: refused")
            check(nonce(DEPLOYER) == 0 and blocks() == 0, "a wrong genesis head: nothing sent")
            passed += 1

            # 3. a contract that differs from the release candidate's
            r = rig.deploy("--broadcast-sepolia", rc=rig.release_candidate(tamper="Panels"))
            check(r.returncode == 2 and "the bytecode of Panels differs" in r.stderr, "a changed contract: refused")
            check(nonce(DEPLOYER) == 0 and blocks() == 0, "a changed contract: nothing sent")
            passed += 1

            # 4. 11155111, the right head. Unsigned, the dry run stops and prints the digest the genesis validator
            # signs; signed outside the script, as on Sepolia, the dry run passes; then the deployment
            plan = json.loads(rig.plan.read_text(encoding="utf-8"))
            plan["genesisValidator"]["key"] = address(derive(MNEMONIC, 1))
            unsigned = rig.work / "plan-unsigned.json"
            unsigned.write_text(json.dumps(plan), encoding="utf-8")
            r = rig.deploy(rc=rc, plan=unsigned, genesis_key=False)
            digest = re.findall(r"GENESIS_DIGEST (0x[0-9a-f]{64})", r.stderr)
            check(r.returncode == 2 and bool(digest), "no genesis signature: refused, printing the digest to sign")
            r = rig.deploy(rc=rc, plan=rig.signed_plan(digest[-1]), genesis_key=False)
            check(r.returncode == 0 and nonce(DEPLOYER) == 0, "signed outside the script: the dry run passes, nothing sent")
            # the genesis-validator tool (task 7.1): its digest is forge's, and its signature from a secret passes
            tool_plan = rig.work / "plan-tool.json"
            tool_plan.write_text(unsigned.read_text(encoding="utf-8"), encoding="utf-8")
            code = GV.main(["sign", "--plan", str(tool_plan), "--deployer", DEPLOYER, "--genesis-rad-node", RAD_DID,
                            "--digest", digest[-1]], source=KeySecret(derive(MNEMONIC, 1)))
            check(code == 0, "genesis-validator sign: forge's GENESIS_DIGEST computed here, signed from the secret")
            r = rig.deploy(rc=rc, plan=tool_plan, genesis_key=False)
            check(r.returncode == 0 and nonce(DEPLOYER) == 0, "signed by genesis-validator: the dry run passes, nothing sent")
            # the Sepolia record's rules (#251 batch 4): a release candidate that ran with the defaults is refused
            r = rig.deploy(*LAUNCH_FLAGS, rc=rc)
            check(r.returncode == 2 and "ran with other panel rules" in r.stderr and nonce(DEPLOYER) == 0,
                  "the launch's rules with a release candidate that ran with others: refused, nothing sent")
            deployed(rig, rig.release_candidate(rules=LAUNCH), 11_155_111, *LAUNCH_FLAGS, rules=LAUNCH)
            passed += 1

            # 5. the local test id on a local endpoint: the same test coin, the genesis mint to another address
            start(31_337)
            deployed(rig, rc, 31_337, "--genesis-mint-to", RECIPIENT, "--genesis-mint", "6000",
                     recipient=RECIPIENT, total=6_000 * 10**6)
            passed += 1
        finally:
            if os.environ.get("POF_DEPLOY_E2E_KEEP") != "1":
                stop()
                for f in RECORDS.glob("chain-*.json"):
                    f.unlink()
    print(f"deploy-sepolia e2e: {passed} of 5 scenarios passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
