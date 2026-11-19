"""The v3 validator node against the real v3 contracts on a local chain (proof-of-fix#139, task 4.1 of #132). Run it
with scripts/node-v3-e2e.sh, which starts anvil, deploys v3 (contracts/script/NodeV3Local.s.sol) and removes both.
Not part of the unit tests: it needs Docker (the chain).

The nodes are real `NodeV3` objects with the fake judge, a fake repository host and a test runner in place of the
Docker sandbox; their keys come from a dstack simulator this script stands in for (the same two calls, GetKey and
GetQuote), so they register with the `simulated` proof type as D18 says. Everything on-chain is real: Validators
checks the registrations, Panels the seals, reveals and receipts, RaceV3 the usage reports and the challenge, FeesV3
the table. Time is moved with anvil's evm_increaseTime, since Panels' windows are hours long.

What it checks:
1. three candidates register (bonded, signed, attested by the simulator's quote);
2. an issue is registered; its check is drawn (the genesis validator's keeper calls `draw`): the genesis validator is
   the counted judge (k = 1), two candidates are its shadows. Each seals; after the seal window each posts its
   receipt's hash and reveals; each reports its usage. The shadows' seals are in earlier blocks than the counted
   reveal. The verdict is held (k = 1), the result pays the counted judge, and the shadows are settled;
3. the genesis validator's table is on FeesV3: its own shared-unit costs and every family's list price;
4. a watcher with a lying judge re-runs the check and files a challenge; RaceV3 holds its stake and Panels opens it;
5. a candidate leaves;
6. the node's command line (`python3 -m oracle register`, `info`, `run`, `leave`) does the same for a key of its own.

With --grow: more issues are registered until candidates qualify (20 scored shadow verdicts each). Meanwhile the
genesis validator's held verdicts reach K1_PENDING_MAX, so submissions wait and are shadowed. Once candidates are
active, a waiting submission is judged by a counted panel of 3, and the held k = 1 verdicts' audits are drawn, so a
validator also sits as an auditor. Not reached even then: a challenge panel (it needs more validators outside the
verdict's judge and auditors than this run grows)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle import abi, crypto, node_v3, v2, v3  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.keys import DstackKeys  # noqa: E402
from oracle.node_v3 import NodeV3  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from oracle.rpc import Reverted, Rpc, Wallet  # noqa: E402
from oracle.transport import OnchainExchange  # noqa: E402

COIN = 10**6
ETH_100 = hex(100 * 10**18)


def secret(name: str) -> int:
    """A throwaway test key from a public string (as oracle.keys.LocalDevKeys): anyone can derive it."""
    return int.from_bytes(crypto.keccak256(f"pof node v3 e2e {name}".encode()), "big") % crypto.N or 1


def simulator() -> str:
    """Stands in for the dstack simulator: a key per path, and a quote over the report data."""

    class Agent(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/GetKey":
                out = {"key": hashlib.sha256(("pof node v3 e2e " + body["path"]).encode()).hexdigest()}
            else:
                out = {"quote": hashlib.sha256(b"simulated quote " + body["report_data"].encode()).hexdigest()}
            data = json.dumps(out).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Agent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}"


def keys_for(endpoint: str, name: str) -> DstackKeys:
    return DstackKeys(f"pof/oracle/e2e/{name}", endpoint=endpoint)


def prepare(rpc: Rpc) -> int:
    """Funds the deployer and prints what the deployment needs: the deployer's and the genesis validator's keys and
    the genesis attestation (its simulated quote, hashed). Read by scripts/node-v3-e2e.sh, never shown."""
    genesis = keys_for(simulator(), "genesis")
    deployer = secret("deployer")
    rpc.call("anvil_setBalance", [crypto.address(deployer), ETH_100])
    quote = genesis.quote(crypto.keccak256(b"genesis"))
    print(f"DEPLOYER=0x{deployer:064x}")
    print(f"GENESIS=0x{genesis.account_secret():064x}")
    print(f"ATTESTATION=0x{crypto.keccak256(bytes.fromhex(quote.quote)).hex()}")
    return 0


class Host:
    """A repository host with the registrations' claims and nothing else."""

    def __init__(self) -> None:
        self._issues: list = []

    def claim(self, issue: int, reporter: str) -> None:
        self._issues.append({"number": 100 + issue, "labels": ["bounty"],
                             "body": f"Registration: {issue}\nReporter wallet: {reporter}"})

    def issues(self, state="open", label=None):
        return list(self._issues)

    def pulls(self, state="all"):
        return []


class Run:
    def __init__(self, rpc: Rpc, record: dict, work: Path) -> None:
        self.rpc, self.work = rpc, work
        self.chain = v3.Chain(rpc, record["race"])
        assert (self.chain.registry, self.chain.panels) == (crypto.checksum(record["registry"]),
                                                            crypto.checksum(record["panels"]))
        self.sim = simulator()
        self.host = Host()
        self.start = 0
        self.logs: list = []
        self.reporter = Wallet(rpc, secret("reporter"), "reporter")
        self.minter = Wallet(rpc, secret("minter"), "minter")  # anyone mints the test coin
        rpc.call("anvil_setBalance", [self.minter.address, ETH_100])
        self.fund(self.reporter.address, 10_000)
        self.reporter.send(self.chain.coin(), "approve(address,uint256)", self.chain.race, 2**255)
        self.nodes: dict = {}

    def log(self, who: str):
        def write(m):
            self.logs.append(f"[{who}] {m}")
            print(f"  [{who}] {m}", flush=True)
        return write

    def fund(self, address: str, coins: int) -> None:
        self.rpc.call("anvil_setBalance", [address, ETH_100])
        self.minter.send(self.chain.coin(), "mint(address,uint256)", address, coins * COIN)

    def node(self, name: str, keeper: bool = False, lie: bool = False, tag: str = "") -> NodeV3:
        keys = keys_for(self.sim, name)
        wallet = Wallet(self.rpc, keys.account_secret(), name)
        me = keys.address()
        family = "fake" if name == "genesis" else "fake-" + name[-1]
        return NodeV3(self.chain, keys, FakeJudge(lie=lie, family=family), self.host, "demo/median", self.work / "src",
                      OnchainExchange(self.chain, keys, wallet=wallet), Store(self.work / "receipts"),
                      runner=lambda argv: (0, "ok", ""), log=self.log(name + tag), wallet=wallet,
                      rounds=Rounds(self.work / "rounds", self.chain.chain_id(), self.chain.race, me + tag),
                      keeper=keeper, costs={"vcpu_second": 12_000_000, "gb_second": 1_300_000} if keeper else None)

    def warp(self, seconds: int, blocks: int = 6) -> None:
        self.rpc.call("evm_increaseTime", [seconds])
        for _ in range(blocks):
            self.rpc.call("evm_mine", [])

    def drive(self, until, what: str, steps: int = 400) -> None:
        """Ticks every node; when none makes progress, moves the chain on (blocks, and half an hour)."""
        for _ in range(steps):
            if until():
                return
            if not any([n.tick(self.start) for n in self.nodes.values()]):
                self.warp(1800)
        raise AssertionError(f"not reached: {what}")

    def register_issue(self) -> tuple:
        receipt = self.reporter.send(self.chain.race, "register(bytes32,bool)", self.chain.repo(), False)
        topic = "0x" + crypto.keccak256(v3.REGISTERED.encode()).hex()
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic)
        issue, check = int(log["topics"][1], 16), abi.decode(["uint256"], abi.hexdata(log["data"]))[0]
        self.host.claim(issue, self.reporter.address)
        return issue, check

    def events(self, name: str, pid: int) -> list:
        """The blocks of Panels' `name` events on panel `pid`."""
        topics = ["0x" + crypto.keccak256(name.encode()).hex(), "0x" + crypto.word(pid).hex()]
        return [int(x["blockNumber"], 16) for x in self.rpc.logs(self.chain.panels, 0, topics)]

    def seats_done(self, pid: int) -> bool:
        p = self.chain.panel(pid)
        return all((s["revealed"] and s["receipted"] and self.chain.usage_of(pid, i).receipt != v3.ZERO)
                   for i, s in ((i, self.chain.seat(pid, i)) for i in range(p["k"])) if int(s["key"], 16))


def check(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)
    print(f"ok: {what}", flush=True)


def run(rpc: Rpc, record: dict, work: Path, grow: bool) -> int:
    r = Run(rpc, record, work)
    c = r.chain
    genesis = r.node("genesis", keeper=True)
    rpc.call("anvil_setBalance", [genesis.address, ETH_100])
    check(genesis.address == crypto.checksum(record["genesis"]) and c.is_active(genesis.address),
          "the genesis validator is this run's node, and active")
    r.nodes["genesis"] = genesis

    # 1. candidates register
    names = ["candidate-1", "candidate-2", "candidate-3"]
    for name in names:
        keys = keys_for(r.sim, name)
        r.fund(keys.address(), 1_000)
        family = "fake-" + name[-1]  # each its own family and host: the caps allow one of each from k = 3
        reg = node_v3.register(c, keys, Wallet(rpc, keys.account_secret(), name), 100 * COIN, work / "receipts",
                               log=r.log(name), proof="simulated", family=family, host=f"host-{name}",
                               image=v2.DEVNET_IMAGE, tee_type="intel-tdx")
        val = c.validator(keys.address())
        check((val["state"], val["bond"], val["level"]) == (v3.CANDIDATE, 100 * COIN, v3.LEVEL_A)
              and val["attestation"] == "0x" + reg.attestation.hex(),
              f"{name} is a candidate with its bond and its simulated attestation (level A on a devnet)")
        r.nodes[name] = r.node(name)

    # 2. a registration's check: a counted judge and its shadows
    issue, s = r.register_issue()
    r.start = max(rpc.block() - 20, 0)
    r.drive(lambda: c.verdict(s)["status"] == v3.HELD and c.submission(s)["paid"]
            and c.panel(c.verdict(s)["shadowPid"])["scored"], "the check counted, paid and its shadows settled")
    v = c.verdict(s)
    counted, shadow = v["pid"], v["shadowPid"]
    check(v["pass"] and v["k"] == 1 and c.judges(counted) == [genesis.address],
          "the genesis validator judged the check alone (k = 1) and passed it; the verdict is held")
    shadows = c.judges(shadow)
    check(len(shadows) == 2 and all(c.validator(k)["state"] == v3.CANDIDATE for k in shadows),
          "two candidates were drawn as its shadows")
    check(r.seats_done(counted) and r.seats_done(shadow),
          "every seat sealed, posted its receipt, revealed and reported its usage on-chain")
    sealed, revealed = r.events("Sealed(uint256,address,bytes32)", shadow), \
        r.events("Revealed(uint256,address,bool,uint8)", counted)
    check(len(sealed) == 2 and len(revealed) == 1 and max(sealed) < min(revealed),
          "the shadows' seals are on-chain before the counted reveal")
    doc = genesis.receipts3.get(c.seat(counted, 0)["receipt"])
    check(doc is not None and doc["proof"]["kind"] == "dstack-simulator"
          and v3.Receipt.from_json(doc["onchain"]).proof_type == v3.PROOF_SIMULATED,
          "the receipt posted on-chain is the hash of the node's document, proven by the simulator's quote")
    check(c.owed(genesis.address) > 0, "the result paid the counted judge")
    p = c.rpc.view(c.registry, "progress(address)", ["(uint16,uint16,uint16,uint16,uint64,uint64,uint8)"],
                   shadows[0])[0]
    check(p[0] == 1 and p[1] == 1 and p[2] == 1 and p[3] == 1,
          "a shadow's reveal was recorded and scored as agreeing (the sealed majority of 3)")

    # 3. the table
    values, current = c.rpc.view(c.fees, "postedShared(address)", ["uint256[4]", "bool"], genesis.address)
    check(current and values[:2] == [12_000_000, 1_300_000] and values[2:] == c.shared_prices()[2:],
          "the genesis validator's table is on FeesV3: its own costs, and the prices in force for the rest")
    listed, cur = c.rpc.view(c.fees, "postedTokens(address,bytes32)", ["uint256[3]", "bool"], genesis.address,
                             v3.name_id("anthropic/claude"))
    check(cur and listed == node_v3.default_list_prices()["anthropic/claude"], "with every family's list price")
    check(not c.rpc.view(c.fees, "postedShared(address)", ["uint256[4]", "bool"], shadows[0])[1],
          "a candidate posts no table (it wouldn't count)")

    if grow:
        grow_network(r, names)

    # 4. a challenge, with evidence
    watcher = r.node(names[0], lie=True, tag="-watcher")
    target = s
    before = c.balance(watcher.address)
    ev = watcher.challenge(target)
    check(ev is not None and c.verdict(target)["challengeOpen"]
          and c.verdict(target)["challenger"].lower() == watcher.address.lower(),
          "a watcher whose check disagrees filed a challenge: Panels has it open")
    need = c.config()["challengeStake"] + c.deposit_for(target, c.repo())
    check(before - c.balance(watcher.address) == need, "RaceV3 holds its stake and its panel's worst-case cost")
    try:
        watcher.challenge(target)
        raise AssertionError("a second challenge was filed")
    except node_v3.SetupError:
        check(True, "one challenge at a time")
    agreeing = r.nodes[names[1]]
    if not grow:
        s2 = r.register_issue()[1]
        r.drive(lambda: c.verdict(s2)["status"] == v3.HELD, "a second check counted")
        check(agreeing.challenge(s2) is None and not c.verdict(s2)["challengeOpen"],
              "a watcher whose check agrees files nothing")

    # 5. leaving
    leaver = keys_for(r.sim, names[2])
    node_v3.leave(c, leaver, Wallet(rpc, leaver.account_secret()), log=r.log(names[2]))
    check(c.validator(leaver.address())["state"] == v3.LEAVING, f"{names[2]} is leaving")
    try:
        node_v3.withdraw_bond(c, leaver, Wallet(rpc, leaver.account_secret()), log=r.log(names[2]))
        raise AssertionError("the bond left before the unbonding delay")
    except Reverted:
        check(True, "its bond stays until the unbonding delay has passed")
    command_line(r)
    print("node-v3-e2e: all checks passed", flush=True)
    return 0


def command_line(r: Run) -> None:
    """6. The same through the node's command line, as an operator runs it: register, info, run, leave."""
    c = r.chain
    keys = DstackKeys(f"pof/oracle/{c.chain_id()}/{c.race.lower()}", endpoint=r.sim)  # the command line's own key
    r.fund(keys.address(), 1_000)
    env = {**os.environ, "ORACLE_VERSION": "3", "ORACLE_RPC": r.rpc.url, "ORACLE_RACE": c.race, "ORACLE_KEYS": "dstack",
           "DSTACK_SIMULATOR_ENDPOINT": r.sim, "ORACLE_RECEIPTS": str(r.work / "cli" / "receipts"),
           "ORACLE_ROUNDS": str(r.work / "cli" / "rounds"), "ORACLE_SRC_ROOT": str(r.work / "cli" / "src"),
           "ORACLE_REPO": "demo/median", "ORACLE_KEEPER": "off", "ORACLE_POLL": "0.2", "ORACLE_FAMILY": "fake-1",
           "ORACLE_HOST_ID": "host-cli"}

    def oracle(*args) -> str:
        p = subprocess.run([sys.executable, "-m", "oracle", *args], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=120)
        if p.returncode != 0:
            raise AssertionError(f"oracle {' '.join(args)} exited {p.returncode}: {p.stdout[-400:]} {p.stderr[-400:]}")
        return p.stdout

    oracle("register", "--bond", "100")
    check("registry state Candidate, bond 100.00" in oracle("info"),
          "`oracle register` on the command line registered its key (the simulator's): `oracle info` shows a candidate")
    check("0 seat(s) finished" in oracle("run", "--until-idle", "1"), "`oracle run` starts as that validator and idles")
    oracle("leave")
    check("registry state Leaving" in oracle("info"), "`oracle leave` announced its exit")


def grow_network(r: Run, names: list) -> None:
    """Registers issues until candidates have qualified and a counted panel of 3 has judged a check. The genesis
    validator judges alone until K1_PENDING_MAX of its verdicts are held; from then on submissions wait, shadowed by
    the candidates, whose verdicts are scored against each other's; once they qualify, the waiting submissions are
    drawn again with k = 3, and the held verdicts' audits are drawn."""
    c = r.chain
    checks: list = []

    def active() -> list:
        return [n for n in names if c.is_active(r.nodes[n].address)]

    def judged_by_three() -> list:
        return [x for x in checks if c.verdict(x)["k"] == 3 and c.verdict(x)["status"] in (v3.WINDOW, v3.FINAL)
                and c.submission(x)["paid"]]

    def settled(x: int) -> bool:
        v = c.verdict(x)
        return (v["status"] in (v3.HELD, v3.WINDOW, v3.WAITING, v3.FINAL) and not any(n.seats for n in r.nodes.values())
                and (v["shadowPid"] == 0 or c.panel(v["shadowPid"])["closed"]))

    for round_ in range(45):
        if len(active()) >= 2 and judged_by_three():
            break
        checks.append(r.register_issue()[1])
        r.drive(lambda: settled(checks[-1]), f"check {checks[-1]} judged or waiting, its shadows' deadlines recorded")
    check(len(active()) >= 2, f"candidates qualified by their shadow verdicts ({len(active())} of {len(names)}, after "
                              f"{len(checks)} more checks)")
    waited = [x for x in checks if any(c.panel(p)["kind"] == v3.SHADOW and c.panel(p)["ex"] == 0 and c.panel(p)["id"] == x
                                       for p in range(1, c.panel_count() + 1))]
    check(bool(waited), f"{len(waited)} submissions waited for a panel and were shadowed meanwhile")
    three = judged_by_three()
    check(bool(three) and r.seats_done(c.verdict(three[0])["pid"]),
          "a counted panel of 3 judged a check (every seat sealed, revealed, reported), and the result paid it")

    def audited() -> list:
        return [p for p in range(1, c.panel_count() + 1) if c.panel(p)["kind"] == v3.AUDIT and c.panel(p)["counted"]]

    r.drive(lambda: bool(audited()), "an audit drawn and judged")
    check(r.seats_done(audited()[0]), "a validator sat as an auditor: sealed, revealed, posted its receipt, reported")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "run"])
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--record")
    ap.add_argument("--work")
    ap.add_argument("--grow", action="store_true")
    a = ap.parse_args(argv[1:])
    rpc = Rpc(a.rpc, retries=2)
    if a.command == "prepare":
        return prepare(rpc)
    return run(rpc, json.loads(Path(a.record).read_text()), Path(a.work), a.grow)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
