"""The Sepolia deploy's wrapper (proof-of-fix#251, task 3.9): what it refuses before anything is signed, and what it
passes to forge, without Docker or a chain. A fake JSON-RPC endpoint on 127.0.0.1 answers and records every call; a
fake `docker` on the PATH stands in for forge (DEPLOY_FORGE_CONTAINER), recording its command line and stdin and
writing the record forge would. The genesis head goes through the real `pofctl verify-head` with a fake Radicle node
(tests/fake_radicle.py). scripts/deploy-sepolia-e2e.sh runs the real thing against local anvils."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from fake_radicle import snapshot  # noqa: E402
from sandbox_env import outside_sandbox  # noqa: E402

# Why some of these skip in the validator's sandbox (tests/sandbox_env.py): its run tree has no .git and is read-only.
NEEDS_HEAD = ("needs this repository's git checkout (the release candidate is checked against HEAD); the run tree "
              "has no .git")
NEEDS_CHECKOUT = ("needs this repository's git checkout (HEAD) and a writable contracts/deployments/ for the record; "
                  "the run tree has no .git and is read-only")

spec = importlib.util.spec_from_file_location("deploy_sepolia", ROOT / "scripts" / "deploy_sepolia.py")
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

RID = "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5"
HEAD = "1" * 40
OTHER = "2" * 40
DEV_KEY_0 = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"  # anvil's public key 0
IMAGE = "0x" + "ab" * 32
GENESIS = ds.address_of(ds.derive(ds.MNEMONIC, 1))  # anvil's public key 1, the genesis validator's in these tests
RAD_KEY = bytes(range(1, 33))  # the genesis validator's Radicle node key (#251, L11), as 32 bytes
RAD_DID = ds.did_from_key(RAD_KEY)


def head_commit() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def good_rc(**changes) -> dict:
    rc = {"format": ds.RC_FORMAT, "tag": "test", "commit": head_commit(), "result": "passed",
          "checks": {"integration": {"command": "scripts/integration.sh --release-candidate x",
                                     "runs": ["passed", "passed", "passed"]},
                     "productionWindows": "passed", "sevSnpValidator": "passed", "realModelRun": "passed",
                     "attestedImages": "passed"},
          "panelRules": ds.panel_rules(),  # the defaults, as a deploy without the rules' flags asks (#251 batch 4)
          "bytecode": {n: "0x" + "cd" * 32 for n in ds.CONTRACTS}}
    rc.update(changes)
    return rc


def good_plan() -> dict:
    return {"rid": RID, "genesisHead": HEAD, "families": ["anthropic/claude"], "teeTypes": ["amd-sev-snp"],
            "images": [IMAGE],
            "genesisValidator": {"key": GENESIS, "operator": "0x" + "55" * 20, "teeType": "amd-sev-snp",
                                 "level": 1, "attestation": "0x" + "66" * 32, "image": IMAGE, "host": "0x" + "77" * 32}}


PANEL_RULES_SEL = "0x" + ds.keccak256(b"panelRules()")[:4].hex()


class Chain(BaseHTTPRequestHandler):
    """A JSON-RPC endpoint answering eth_chainId, eth_getCode and eth_call (the race's chainId(), and Panels'
    panelRules() as `rules`, five words); it records methods."""
    chain = 1
    calls: list = []
    rules = (0, 0, 0, 7, 0)

    def do_POST(self):  # noqa: N802
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append(req["method"])
        call = "0x" + f"{self.chain:064x}"
        if req["method"] == "eth_call" and req["params"][0].get("data") == PANEL_RULES_SEL:
            call = "0x" + "".join(f"{w:064x}" for w in self.rules)
        result = {"eth_chainId": hex(self.chain), "eth_getCode": "0x6080", "eth_call": call}.get(req["method"])
        body = json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
script = sys.argv[-1]
Path(os.environ["FAKE_DOCKER_LOG"]).write_text(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read(),
    "mint": os.environ.get("DEPLOY_GENESIS_MINT"), "mintTo": os.environ.get("DEPLOY_GENESIS_MINT_TO"),
    "radNode": os.environ.get("DEPLOY_GENESIS_RAD_NODE"), "caps": os.environ.get("DEPLOY_PANEL_CAPS"),
    "kTop": os.environ.get("DEPLOY_K_TOP"), "size": os.environ.get("DEPLOY_CHALLENGE_SIZE")}))
if os.environ.get("FAKE_DOCKER_FAIL"):
    print("Error: script failed: " + os.environ["FAKE_DOCKER_FAIL"])
    sys.exit(1)
root, cid = Path(os.environ["FAKE_ROOT"]), os.environ["FAKE_CHAIN"]
broadcast = "--broadcast" in script
rec = root / "contracts" / "deployments" / os.environ["DEPLOY_RECORD"]
rec.parent.mkdir(parents=True, exist_ok=True)
cap = "strict" if os.environ["DEPLOY_PANEL_CAPS"] == "strict" else "off"
rules = {"operatorCap": cap, "hostCap": cap, "teeCap": cap, "kTop": int(os.environ["DEPLOY_K_TOP"]),
         "challengeSize": os.environ["DEPLOY_CHALLENGE_SIZE"]}
if os.environ.get("FAKE_RULES_OFF"):
    rules["kTop"] = 5
rec.write_text(json.dumps({"chainId": int(cid), "deployer": os.environ["DEPLOY_DEPLOYER"], "panelRules": rules,
                           "limit": "a fork can remove both checks", "rid": os.environ["DEPLOY_RID"],
                           "addresses": {"race": "0x" + "11" * 20, "pool": "0x" + "22" * 20,
                                         "panels": "0x" + "44" * 20},
                           "constructorArgs": {"Validators": {"validators": {
                               "radNode": os.environ.get("FAKE_RAD_NODE") or os.environ["DEPLOY_GENESIS_RAD_NODE"]}},
                               "FeesV3": {"caps": {"inputTokens": 140000, "outputTokens": 16000, "storageMb": 20,
                                                   "gasAllowance": 1000000, "maxGasPrice": 1000000000,
                                                   "gasOverhead": int(os.environ.get("FAKE_OVERHEAD") or 500000)}},
                               "RaceV3": {"config": json.dumps({"mergeDays": int(os.environ.get("FAKE_MERGE_DAYS")
                                                                                 or 3)})}},
                           "testCoin": {"genesisMint": {"total": int(os.environ["DEPLOY_GENESIS_MINT"])
                                                        + int(os.environ.get("FAKE_MINT_OFF", "0")),
                                                        "restTo": os.environ["DEPLOY_GENESIS_MINT_TO"]}}}))
run = root / "contracts" / "broadcast" / "DeploySepolia.s.sol" / cid / ("run-latest.json" if broadcast else
                                                                        "dry-run/run-latest.json")
run.parent.mkdir(parents=True, exist_ok=True)
run.write_text(json.dumps({"libraries": ["src/v3/PanelsDraw.sol:PanelsDraw:0x" + "33" * 20],
                           "receipts": [{"blockNumber": "0x2a"}, {"blockNumber": "0x29"}]}))
print("== Logs ==")
'''


class TestFees(unittest.TestCase):
    """The Sepolia deployment's fees (owner, 2026-11-19): the pure taxi fare and no solver's fee beyond validation. The
    values are DeploySepolia.s.sol's; scripts/deploy-sepolia-e2e.sh checks them in the record and on the chain."""

    def setUp(self):
        self.src = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")

    def test_the_taxi_fare(self):
        self.assertIn("uint256 internal constant JUDGES_FEE = 0;", self.src)
        self.assertIn("c.judgeFee = JUDGES_FEE;", self.src)
        self.assertIn('vm.serializeString(o, "mode", "taxi");', self.src)

    def test_a_solver_pays_only_validation(self):
        for name in ("attemptFee", "evaluationFee", "appealFee"):
            self.assertIn(f"c.{name} = 0;", self.src)
        self.assertIn("c.registrationFee = 2e6;", self.src)  # the reporter's fees stay
        self.assertIn("c.issueStake = 5e6;", self.src)


class TestTestCoin(unittest.TestCase):
    """The fee coin (design L17, amended 2026-11-20): the project's own test coin and its faucet, in the deploy script,
    the release-candidate set and the genesis mint's flags."""

    def setUp(self):
        self.src = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")

    def test_the_release_candidate_names_both_contracts(self):
        self.assertEqual(len(ds.CONTRACTS), 11)
        self.assertEqual(ds.CONTRACTS[:2], ("TestCoin", "CoinFaucet"))
        for name in ds.CONTRACTS:
            self.assertIn(f'"{name}"', self.src)
            self.assertIn(f"type({name}).creationCode", self.src)

    def test_no_circle_usdc_and_no_mock_coin(self):
        self.assertNotIn("0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238", self.src)
        self.assertNotIn("MockCoin", self.src)
        self.assertIn("d.faucet = new CoinFaucet(to, amounts);", self.src)
        self.assertIn("d.coin = address(d.faucet.coin());", self.src)

    def test_the_genesis_rad_node_parses_a_did_a_node_id_and_hex(self):
        want = ("0x" + RAD_KEY.hex(), RAD_DID)
        self.assertEqual(ds.genesis_rad_node(RAD_DID), want)
        self.assertEqual(ds.genesis_rad_node(RAD_DID[len("did:key:"):]), want)  # `rad self --nid`
        self.assertEqual(ds.genesis_rad_node("0x" + RAD_KEY.hex()), want)
        for bad in (None, "", "0x" + "00" * 32, "0x" + "zz" * 32, "did:key:zQ3s", "did:web:example"):
            with self.assertRaises(ds.Refused):
                ds.genesis_rad_node(bad)

    def test_the_genesis_mints_defaults(self):
        deployer = "0x" + "88" * 20
        self.assertEqual(ds.genesis_mint(None, None, deployer), (5_000 * 10**6, deployer))
        self.assertIn("uint256 internal constant GENESIS_MINT = 5_000e6;", self.src)

    def test_the_genesis_mints_flags(self):
        to = "0x" + "99" * 20
        self.assertEqual(ds.genesis_mint("6000", to, "0x" + "88" * 20), (6_000 * 10**6, to))
        self.assertEqual(ds.genesis_mint("250.5", to, to), (250_500_000, to))
        self.assertEqual(ds.genesis_mint("250", to, to), (250 * 10**6, to))  # the bond alone: the rest is 0

    def test_the_genesis_mints_refusals(self):
        to = "0x" + "99" * 20
        for amount, says in (("249.999999", "cover the genesis bond"), ("0", "cover the genesis bond"),
                             ("-5", "amount of coins"), ("1e6", "amount of coins"), ("1.0000001", "amount of coins"),
                             ("abc", "amount of coins"), ("9" * 40, "implausibly large")):
            with self.assertRaises(ds.Refused) as e:
                ds.genesis_mint(amount, to, to)
            self.assertIn(says, str(e.exception), amount)
        for bad in ("0x" + "00" * 20, "0x1234", "me"):
            with self.assertRaises(ds.Refused) as e:
                ds.genesis_mint("5000", bad, to)
            self.assertIn("nonzero address", str(e.exception))


class TestProfile(unittest.TestCase):
    """Sepolia's CI profile (#251 L22, task 4.10): its time limit is the whole check's, and each of the two test runs
    gets half, so it is set for two runs of proof-of-fix's own suite with a margin."""

    SUITE_S = 513  # one run of proof-of-fix's suite in the sandbox (1 vCPU, the pinned image), measured 2026-11-19

    def test_the_timeout_fits_two_runs_of_the_suite_with_a_margin(self):
        sys.path.insert(0, str(ROOT))
        from oracle import sandbox

        src = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")
        timeout = int(re.search(r"uint32 internal constant SEPOLIA_TIMEOUT_S = ([0-9_]+);", src).group(1).replace("_", ""))
        self.assertIn('g.profile = IFeesV3.Profile(keccak256("image"), 2_000, 4_096, SEPOLIA_TIMEOUT_S);', src)
        self.assertEqual(sandbox.RUNS, 2)
        self.assertGreaterEqual(timeout // sandbox.RUNS, 2 * self.SUITE_S)  # each run: twice the suite's time


class TestEndpoint(unittest.TestCase):
    def test_only_exact_local_hosts_are_local(self):
        for url in ("http://127.0.0.1:8545", "http://localhost:8545", "http://[::1]:8545"):
            self.assertTrue(ds.is_local(url), url)
        for url in ("http://127.0.0.2:8545", "http://localhost.example:8545", "http://127.0.0.1.example:8545",
                    "http://127.0.0.1@rpc.example:8545", "https://127.0.0.1:8545", "http://10.0.0.1:8545",
                    "http://[::1]:x"):
            self.assertFalse(ds.is_local(url), url)

    def test_sepolia_only_and_the_local_ids_only_locally(self):
        ds.check_chain(11_155_111, False)
        ds.check_chain(11_155_111, True)  # a local anvil with Sepolia's id takes the Sepolia path
        ds.check_chain(31_337, True)
        ds.check_chain(7_193, True)
        for cid, local in ((31_337, False), (7_193, False), (1, True), (1, False), (10, True), (8453, False)):
            with self.assertRaises(ds.Refused) as e:
                ds.check_chain(cid, local)
            self.assertIn(f"chain {cid}", str(e.exception))

    def test_a_remote_endpoint_must_be_https_without_credentials(self):
        with self.assertRaises(ds.Refused):
            ds.check_url("http://rpc.example/v3")
        with self.assertRaises(ds.Refused):
            ds.check_url("https://user:pw@rpc.example/v3")
        ds.check_url("https://rpc.example/v3")
        ds.check_url("http://127.0.0.1:8545")


class TestReleaseCandidate(unittest.TestCase):
    def load(self, rc) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rc.json"
            p.write_text(json.dumps(rc) if isinstance(rc, dict) else rc, encoding="utf-8")
            return ds.load_release_candidate(str(p))

    def refused(self, rc, says: str) -> None:
        with self.assertRaises(ds.Refused) as e:
            self.load(rc)
        self.assertIn(says, str(e.exception))

    @outside_sandbox(NEEDS_HEAD)
    def test_a_passing_record_for_this_commit(self):
        self.assertEqual(self.load(good_rc())["result"], "passed")

    def test_no_record(self):
        with self.assertRaises(ds.Refused):
            ds.load_release_candidate("/nonexistent/rc.json")

    def test_attested_images_is_a_check(self):
        # L21 (task 3.16): the record must show the measured checker disk's check passed, or the deploy is refused,
        # naming it. The checks come before the commit's, so this needs no checkout.
        self.assertIn("attestedImages", ds.RC_CHECKS)
        checks = good_rc(commit="ab" * 20)["checks"]
        without = {k: v for k, v in checks.items() if k != "attestedImages"}
        self.refused(good_rc(checks=without), "attestedImages check didn't pass (None)")
        self.refused(good_rc(checks={**checks, "attestedImages": "failed"}), "attestedImages check didn't pass")
        self.assertIn('"attestedImages": "passed"', (ROOT / "scripts/deploy_sepolia.py").read_text())

    @outside_sandbox(NEEDS_HEAD)
    def test_refusals(self):
        self.refused("not json", "isn't JSON")
        self.refused(good_rc(format="something else"), "pof-release-candidate/1")
        self.refused(good_rc(result="failed"), "didn't pass")
        checks = good_rc()["checks"]
        self.refused(good_rc(checks={**checks, "integration": {"runs": ["passed", "passed"]}}), "3 runs in a row")
        self.refused(good_rc(checks={**checks, "integration": {"runs": ["passed", "failed", "passed"]}}),
                     "3 runs in a row")
        for c in ds.RC_CHECKS:
            self.refused(good_rc(checks={**checks, c: "failed"}), c)
        self.refused(good_rc(commit="ab" * 20), "isn't this checkout's HEAD or an ancestor")
        self.refused(good_rc(commit="main"), "names no commit")
        code = good_rc()["bytecode"]
        self.refused(good_rc(bytecode={**code, "Other": "0x" + "00" * 32}), "exactly these contracts")
        self.refused(good_rc(bytecode={k: v for k, v in code.items() if k != "Panels"}), "exactly these contracts")
        self.refused(good_rc(bytecode={**code, "Panels": "0x1234"}), "Panels isn't 32 bytes")
        rules = good_rc()["panelRules"]
        self.refused(good_rc(panelRules=None), "every panel rule")
        self.refused(good_rc(panelRules={k: v for k, v in rules.items() if k != "kTop"}), "every panel rule")

    @outside_sandbox(NEEDS_HEAD)
    def test_a_record_that_ran_with_other_rules_is_refused(self):
        """#251 batch 4: the release candidate must have run with the rules being deployed (they aren't in the
        bytecode the hashes cover)."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "rc.json"
            p.write_text(json.dumps(good_rc(panelRules=ds.panel_rules("launch", 3, "same"))), encoding="utf-8")
            self.assertEqual(ds.load_release_candidate(str(p), rules=ds.panel_rules("launch", 3, "same"))["result"],
                             "passed")
            with self.assertRaises(ds.Refused) as e:
                ds.load_release_candidate(str(p), rules=ds.panel_rules())
            self.assertIn("ran with other panel rules", str(e.exception))


class TestPanelRules(unittest.TestCase):
    """The panel rules' flags (#251 contract batch 4, task 3.25; design L23, L24)."""

    def test_the_defaults_are_strict_7_and_larger(self):
        self.assertEqual(ds.panel_rules(), {"operatorCap": "strict", "hostCap": "strict", "teeCap": "strict",
                                            "kTop": 7, "challengeSize": "larger"})
        a = ds.parser().parse_args(["deploy", "--plan", "p", "--release-candidate", "r"])
        self.assertEqual((a.panel_caps, a.k_top, a.challenge_size), ("strict", 7, "larger"))

    def test_the_sepolia_launchs(self):
        self.assertEqual(ds.panel_rules("launch", 3, "same"), {"operatorCap": "off", "hostCap": "off",
                                                               "teeCap": "off", "kTop": 3, "challengeSize": "same"})

    def test_refusals(self):
        for args in (("loose", 7, "larger"), ("strict", 0, "larger"), ("strict", 4, "larger"),
                     ("strict", 9, "larger"), ("strict", 7, "smaller")):
            with self.assertRaises(ds.Refused):
                ds.panel_rules(*args)


class TestPlan(unittest.TestCase):
    def load(self, plan, key=None) -> dict:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            p.write_text(json.dumps(plan), encoding="utf-8")
            return ds.load_plan(str(p), key)

    def test_a_good_plan(self):
        self.assertEqual(self.load(good_plan())["genesisHead"], HEAD)

    def test_refusals(self):
        for change, says in (({"rid": "proof-of-fix"}, "rid"), ({"genesisHead": "abc"}, "genesisHead"),
                             ({"families": []}, "families"), ({"families": ["a,b"]}, "family 'a,b'"),
                             ({"images": ["0x12"]}, "images")):
            with self.assertRaises(ds.Refused) as e:
                self.load({**good_plan(), **change})
            self.assertIn(says, str(e.exception))
        for change, says in (({"level": 3}, "level"), ({"image": "0x" + "99" * 32}, "one of its images"),
                             ({"teeType": "intel-tdx"}, "one of its teeTypes"), ({"signature": "0x12"}, "65 bytes")):
            plan = good_plan()
            plan["genesisValidator"].update(change)
            with self.assertRaises(ds.Refused) as e:
                self.load(plan)
            self.assertIn(says, str(e.exception))

    def test_the_genesis_dev_key_must_be_the_plans_key(self):
        with self.assertRaises(ds.Refused):
            self.load(good_plan(), key=2)

    def test_a_family_must_be_provider_slash_line(self):
        """VP12: `anthropic/claude` is accepted; the dotted `anthropic.claude` is refused, naming the form."""
        self.assertEqual(self.load({**good_plan(), "families": ["anthropic/claude", "openai/gpt-5.1"]})["families"],
                         ["anthropic/claude", "openai/gpt-5.1"])
        for bad in ("anthropic.claude", "fake", "Anthropic/claude", "anthropic/", "/claude", "a/b/c", "-a/b"):
            with self.assertRaises(ds.Refused) as e:
                self.load({**good_plan(), "families": [bad]})
            self.assertIn(f"family {bad!r} isn't in the form provider/line, e.g. anthropic/claude", str(e.exception))
        with self.assertRaises(ds.Refused) as e:
            self.load({**good_plan(), "families": ["anthropic/claude", "anthropic/claude"]})
        self.assertIn("repeat", str(e.exception))

    def test_live_v3s_committed_plan_keeps_its_dotted_family(self):
        """v3's plan (and record) are history: that plan, named by its RID and genesis head, still loads as it is,
        with no keeper even for Sepolia; the same family in any other plan is refused."""
        v3 = json.loads(ds.V3_PLAN.read_text(encoding="utf-8"))
        self.assertEqual(v3["families"], ["anthropic.claude"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            p.write_text(json.dumps(v3), encoding="utf-8")
            self.assertEqual(ds.load_plan(str(p), None, sepolia=True)["families"], ["anthropic.claude"])
        with self.assertRaises(ds.Refused):
            self.load({**good_plan(), "families": ["anthropic.claude"], "genesisHead": v3["genesisHead"]})

    def test_the_keeper(self):
        """VP16 (Q1): a Sepolia plan names the seed host's keeper; it is checked and kept as given."""
        keeper = {"address": "0x" + "99" * 20, "role": ds.KEEPER_ROLE, "cost": ds.KEEPER_COST}
        self.assertEqual(self.load({**good_plan(), "keeper": keeper})["keeper"], keeper)
        self.assertNotIn("keeper", self.load(good_plan()))  # a local rehearsal may leave it out
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "plan.json"
            p.write_text(json.dumps(good_plan()), encoding="utf-8")
            with self.assertRaises(ds.Refused) as e:
                ds.load_plan(str(p), None, sepolia=True)
            self.assertIn("names no keeper", str(e.exception))
        for change, says in (({"address": "0x12"}, "keeper.address"), ({"role": ""}, "keeper.role"),
                             ({"cost": None}, "keeper.cost")):
            with self.assertRaises(ds.Refused) as e:
                self.load({**good_plan(), "keeper": {**keeper, **change}})
            self.assertIn(says, str(e.exception))

    def test_the_template_names_the_family_form_and_the_keeper(self):
        doc = ds.__doc__
        self.assertIn('"families": ["anthropic/claude", …]', doc)
        self.assertNotIn("anthropic.claude\"", doc)
        self.assertIn('"keeper": {"address": "0x<the seed host\'s keeper account>"', doc)
        self.assertIn(f'"role": "{ds.KEEPER_ROLE}"', doc)
        self.assertIn("about $0", ds.KEEPER_COST)
        self.assertIn("1.5-2M gas a check", ds.KEEPER_COST)
        self.assertEqual(ds.KEEPER_ROLE, "the seed host's keeper-only node")


class TestRepayment(unittest.TestCase):
    """VP13 (F11): the v3.1 deploy's FeesV3 caps, set by DeploySepolia.s.sol and read back from the record by the
    wrapper; and #310's mergeDays 3 (O4)."""

    def test_the_script_sets_the_values_the_wrapper_checks(self):
        src = (ROOT / "contracts" / "script" / "DeploySepolia.s.sol").read_text(encoding="utf-8")
        self.assertIn("g.caps = IFeesV3.Caps(140_000, 16_000, 20, 1_000_000, 500_000, 1 gwei);", src)
        self.assertEqual(ds.REPAYMENT, {"gasAllowance": 1_000_000, "gasOverhead": 500_000,
                                        "maxGasPrice": 1_000_000_000})
        self.assertIn("c.mergeDays = 3;", src)
        self.assertEqual(ds.MERGE_DAYS, 3)
        # the struct's order: inputTokens, outputTokens, storageMb, gasAllowance, gasOverhead, maxGasPrice
        iface = (ROOT / "contracts" / "src" / "v3" / "IFeesV3.sol").read_text(encoding="utf-8")
        order = re.findall(r"uint64 (\w+);", iface[iface.index("struct Caps"):iface.index("}", iface.index("struct Caps"))])
        self.assertEqual(order, ["inputTokens", "outputTokens", "storageMb", "gasAllowance", "gasOverhead",
                                 "maxGasPrice"])


class TestDeploy(unittest.TestCase):
    """The command line, end to end with the fakes."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = Path(self.dir.name)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        shim = self.bin / "docker"
        shim.write_text(FAKE_DOCKER, encoding="utf-8")
        shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
        self.docker_log = self.tmp / "docker.json"
        self.snap = self.tmp / "snapshot"
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps(good_plan()), encoding="utf-8")
        self.rc = self.tmp / "rc.json"
        self.rc.write_text(json.dumps(good_rc()), encoding="utf-8")
        self.record = f"sepolia-local/unit-{os.getpid()}.json"
        self.addCleanup(lambda: (ROOT / "contracts" / "deployments" / self.record).unlink(missing_ok=True))
        Chain.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Chain)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def run_deploy(self, *extra, chain=11_155_111, head=HEAD, url=None, fail="", mint_off=0, rad_node=RAD_DID,
                   record_node="", rules_off=False, chain_rules=(0, 0, 0, 7, 0), overhead="", merge_days=""):
        Chain.chain = chain
        Chain.rules = chain_rules
        if head:
            self.snap.write_text(snapshot(head), encoding="utf-8")
        rad = f"{sys.executable} {ROOT / 'tests' / 'fake_radicle.py'} {self.snap}"
        env = {k: v for k, v in os.environ.items() if not k.startswith("DEPLOY_")}
        env.update({"PATH": f"{self.bin}:{env['PATH']}", "DEPLOY_FORGE_CONTAINER": "fake-anvil",
                    "FAKE_DOCKER_LOG": str(self.docker_log), "FAKE_ROOT": str(ROOT), "FAKE_CHAIN": str(chain),
                    "FAKE_DOCKER_FAIL": fail, "FAKE_MINT_OFF": str(mint_off), "FAKE_RAD_NODE": record_node,
                    "FAKE_RULES_OFF": "1" if rules_off else "", "FAKE_OVERHEAD": str(overhead),
                    "FAKE_MERGE_DAYS": str(merge_days)})
        node = ["--genesis-rad-node", rad_node] if rad_node is not None else []
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "deploy_sepolia.py"), "deploy", "--rpc-url",
                               url or self.url, "--plan", str(self.plan), "--release-candidate", str(self.rc),
                               "--rad-exec", rad, "--record", self.record, *node, *extra],
                              capture_output=True, text=True, timeout=120, env=env, cwd=ROOT)

    def assert_refused(self, r, says: str, rpc=("eth_chainId",)):
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(says, r.stderr)
        self.assertFalse(self.docker_log.exists(), "it reached forge before refusing")
        self.assertEqual(Chain.calls, list(rpc), "it called more than the chain id")

    def test_mainnet_is_refused_naming_the_chain_and_nothing_is_sent(self):
        self.assert_refused(self.run_deploy("--dev-key", "0", "--broadcast-sepolia", chain=1), "chain 1 refused")

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_wrong_genesis_head_is_refused(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, head=OTHER),
                            f"canonical main {OTHER} isn't the genesis head {HEAD}")

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_repository_that_doesnt_exist_is_refused(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, head=""), "can't be read")

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_an_injected_verify_head_refusal_is_refused(self):
        cmd = f"{sys.executable} -c \"import sys; print('no such repository'); sys.exit(1)\""
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--verify-head-cmd", cmd),
                            "no such repository")

    def test_a_failed_release_candidate_is_refused(self):
        self.rc.write_text(json.dumps(good_rc(result="failed")), encoding="utf-8")
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20), "didn't pass")

    def test_test_keys_are_refused_for_a_remote_endpoint_before_any_call(self):
        # 127.0.0.2 isn't one of the local hosts: refused before the chain id is read (port 1: nothing listens)
        self.assert_refused(self.run_deploy("--dev-key", "0", url="https://127.0.0.2:1/"), "local endpoint only",
                            rpc=())

    def test_a_broadcast_needs_a_signer(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--broadcast-sepolia"), "needs a signer",
                            rpc=())

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_dry_run_sends_nothing_and_writes_the_record(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        script = ran["argv"][-1]
        self.assertNotIn("--broadcast", script)
        self.assertNotIn("--private-key", script)
        self.assertEqual(ran["stdin"], "")
        self.assertNotIn(self.url, " ".join(ran["argv"]))  # the endpoint goes in the environment
        self.assertEqual(Chain.calls, ["eth_chainId"])
        rec = json.loads((ROOT / "contracts" / "deployments" / self.record).read_text())
        self.assertTrue(rec["dryRun"])
        self.assertEqual(rec["endpoint"], "local")
        self.assertEqual(rec["releaseCandidate"]["commit"], head_commit())
        self.assertEqual(rec["libraries"], {"PanelsDraw": "0x" + "33" * 20})
        self.assertEqual(rec["genesisHeadCheck"]["commit"], HEAD)

    def test_the_record_names_the_deployment_block(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d) / "run-latest.json"
            run.write_text(json.dumps({"receipts": [{"blockNumber": "0xba0a2c"}, {"blockNumber": "0xba0a2b"},
                                                    {"blockNumber": 12192301}]}), encoding="utf-8")
            self.assertEqual(ds.deploy_block(run), 0xba0a2b)
            run.write_text(json.dumps({"receipts": []}), encoding="utf-8")
            with self.assertRaises(ds.Refused):
                ds.deploy_block(run)

    def test_a_remote_broadcast_takes_its_gas_from_the_node(self):
        # 2026-11-22: forge's local estimates predate Sepolia's EIP-8037 gas, and the first broadcast ran out of gas
        self.assertEqual(ds.broadcast_flags(False), " --broadcast --slow --skip-simulation")
        self.assertEqual(ds.broadcast_flags(True), " --broadcast --slow")

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_broadcast_flag_broadcasts_with_the_key_on_stdin(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", "--broadcast-sepolia")
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        self.assertIn("--broadcast", ran["argv"][-1])
        self.assertNotIn(DEV_KEY_0[2:], " ".join(ran["argv"]))
        self.assertEqual(ran["stdin"].strip(), DEV_KEY_0)
        self.assertIn("eth_getCode", Chain.calls)
        self.assertIn("eth_call", Chain.calls)
        rec = json.loads((ROOT / "contracts" / "deployments" / self.record).read_text())
        self.assertFalse(rec["dryRun"])
        self.assertEqual(rec["block"], 0x29)  # the deployment's first block, for pofctl's from_block

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_panel_rules_go_to_forge_and_into_the_record(self):
        """#251 batch 4: --panel-caps, --k-top and --challenge-size reach forge, and the record names the rules; the
        defaults are strict, 7 and larger."""
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        self.assertEqual((ran["caps"], ran["kTop"], ran["size"]), ("strict", "7", "larger"))
        launch = ds.panel_rules("launch", 3, "same")
        self.rc.write_text(json.dumps(good_rc(panelRules=launch)), encoding="utf-8")
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", "--panel-caps", "launch", "--k-top", "3",
                            "--challenge-size", "same", "--broadcast-sepolia", chain_rules=(1, 1, 1, 3, 1))
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        self.assertEqual((ran["caps"], ran["kTop"], ran["size"]), ("launch", "3", "same"))
        rec = json.loads((ROOT / "contracts" / "deployments" / self.record).read_text())
        self.assertEqual(rec["panelRules"], launch)

    @outside_sandbox(NEEDS_HEAD)
    def test_a_release_candidate_with_other_rules_is_refused(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--panel-caps", "launch", "--k-top", "3",
                                            "--challenge-size", "same"), "ran with other panel rules")

    def test_bad_rules_are_refused_before_any_call(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--k-top", "4"), "odd number", rpc=())

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_record_whose_rules_differ_is_refused(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", rules_off=True)
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("the record's panel rules", r.stderr)

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_chain_whose_rules_differ_is_refused(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", "--broadcast-sepolia",
                            chain_rules=(1, 1, 1, 3, 1))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("the deployed Panels has other panel rules", r.stderr)

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_genesis_mint_goes_to_forge_with_its_defaults(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        self.assertEqual(ran["mint"], str(5_000 * 10**6))
        self.assertEqual(ran["mintTo"].lower(), ds.address_of(ds.derive(ds.MNEMONIC, 0)).lower())  # the deployer

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_genesis_mint_flags_go_to_forge(self):
        to = "0x" + "99" * 20
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", "--genesis-mint", "6000",
                            "--genesis-mint-to", to)
        self.assertEqual(r.returncode, 0, r.stderr)
        ran = json.loads(self.docker_log.read_text())
        self.assertEqual((ran["mint"], ran["mintTo"]), (str(6_000 * 10**6), to))

    def test_a_bad_genesis_mint_is_refused_before_any_call(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--genesis-mint", "100"),
                            "cover the genesis bond", rpc=())
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, "--genesis-mint-to", "0x12"),
                            "nonzero address", rpc=())

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_record_with_another_genesis_mint_is_refused(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", mint_off=1)
        self.assertEqual(r.returncode, 2)
        self.assertIn("genesis mint isn't the one asked for", r.stderr)

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_genesis_rad_node_goes_to_forge_and_into_the_record(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(self.docker_log.read_text())["radNode"], "0x" + RAD_KEY.hex())
        rec = json.loads((ROOT / "contracts" / "deployments" / self.record).read_text())
        self.assertEqual(rec["genesisRadNode"]["key"], "0x" + RAD_KEY.hex())
        self.assertEqual(rec["genesisRadNode"]["did"], RAD_DID)
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", rad_node="0x" + RAD_KEY.hex())
        self.assertEqual(r.returncode, 0, r.stderr)  # the same key in hex

    def test_a_missing_or_bad_genesis_rad_node_is_refused_before_any_call(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, rad_node=None), "--genesis-rad-node",
                            rpc=())
        for bad in ("did:key:z6MkNotBase58l0O", "0x1234", "0x" + "00" * 32, "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5"):
            self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, rad_node=bad), "--genesis-rad-node",
                                rpc=())

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_record_with_another_genesis_rad_node_is_refused(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", record_node="0x" + "ee" * 32)
        self.assertEqual(r.returncode, 2)
        self.assertIn("genesis Radicle node key isn't the one asked for", r.stderr)

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_the_record_carries_the_repayment_and_the_keeper(self):
        keeper = {"address": "0x" + "99" * 20, "role": ds.KEEPER_ROLE, "cost": ds.KEEPER_COST}
        self.plan.write_text(json.dumps({**good_plan(), "keeper": keeper}), encoding="utf-8")
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1")
        self.assertEqual(r.returncode, 0, r.stderr)
        rec = json.loads((ROOT / "contracts" / "deployments" / self.record).read_text())
        self.assertEqual(rec["keeper"], keeper)
        caps = rec["constructorArgs"]["FeesV3"]["caps"]
        self.assertEqual((caps["gasOverhead"], caps["gasAllowance"], caps["maxGasPrice"]), (500_000, 1_000_000, 10**9))

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_a_record_with_other_repayment_caps_or_merge_days_is_refused(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", overhead=50_000)
        self.assertEqual(r.returncode, 2)
        self.assertIn("repayment caps (gasAllowance 1000000, gasOverhead 50000, maxGasPrice 1000000000) aren't",
                      r.stderr)
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", merge_days=14)
        self.assertEqual(r.returncode, 2)
        self.assertIn("mergeDays (14) isn't 3", r.stderr)

    def test_a_dotted_family_is_refused_before_any_call(self):
        self.plan.write_text(json.dumps({**good_plan(), "families": ["anthropic.claude"]}), encoding="utf-8")
        self.assert_refused(self.run_deploy("--dev-key", "0"), "isn't in the form provider/line", rpc=())

    def test_a_sepolia_plan_without_the_keeper_is_refused_before_any_call(self):
        self.assert_refused(self.run_deploy("--deployer", "0x" + "88" * 20, url="https://127.0.0.2:1/"),
                            "names no keeper", rpc=())

    @outside_sandbox(NEEDS_CHECKOUT)
    def test_forges_refusal_is_a_refusal(self):
        r = self.run_deploy("--dev-key", "0", "--genesis-dev-key", "1", fail="the bytecode of Panels differs")
        self.assertEqual(r.returncode, 2)
        self.assertIn("the bytecode of Panels differs", r.stderr)


class TestVerifyGenesisHead(unittest.TestCase):
    """`pofctl verify-head --rid --commit`: before a deployment, no chain and no record."""

    def run_pofctl(self, commit: str, head: str | None):
        with tempfile.TemporaryDirectory() as d:
            snap = Path(d) / "snapshot"
            if head:
                snap.write_text(snapshot(head), encoding="utf-8")
            rad = f"{sys.executable} {ROOT / 'tests' / 'fake_radicle.py'} {snap}"
            return subprocess.run([sys.executable, "-m", "pofctl", "--json", "--record", "/nonexistent.json",
                                   "verify-head", "--rid", RID, "--commit", commit, "--rad-exec", rad],
                                  capture_output=True, text=True, cwd=ROOT, timeout=60)

    def test_the_genesis_head_is_canonical_main(self):
        r = self.run_pofctl(HEAD, HEAD)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertTrue(out["match"] and out["genesis"])
        self.assertEqual(out["head"], HEAD)

    def test_another_commit_is_refused(self):
        r = self.run_pofctl(HEAD, OTHER)
        self.assertEqual(r.returncode, 1)
        self.assertIn("isn't the genesis head", r.stderr)

    def test_no_repository_is_refused(self):
        r = self.run_pofctl(HEAD, None)
        self.assertEqual(r.returncode, 1)
        self.assertIn("can't be read", r.stderr)

    def test_a_commit_that_isnt_a_sha_is_refused(self):
        self.assertEqual(self.run_pofctl("main", HEAD).returncode, 1)


if __name__ == "__main__":
    unittest.main()
