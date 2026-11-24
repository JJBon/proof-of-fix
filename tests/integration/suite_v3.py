"""v3 (open validators) on a throwaway local devnet beside v2 (proof-of-fix#140, tasks 5.0 and 5.1 of #132). Run it with
scripts/devnet-v3-e2e.sh or scripts/integration.sh --version 3, which start the devnet, deploy v2, deploy v3 beside
it (scripts/devnet.sh deploy-v3: one genesis validator of the `simulated` proof type, level A on a devnet, D18) and
remove everything when it ends. Not part of the unit tests: it needs Docker (the chain). No model call, no network
beyond this machine.

The validators are real `NodeV3` objects (oracle/node_v3.py) with the fake judge, as in tests/e2e_node_v3.py: their
keys come from a stand-in for the dstack simulator, the repository host is a fake with the registrations' claims and
the fixes' pull requests, and a fix's tests are a stand-in for the Docker sandbox (exit 0 for a good fix, 1 for a bad
one: no fix's code is run). Everything on-chain is real: Validators, Panels, FeesV3 and RaceV3 check every signature,
window and draw. Who is drawn and what decides is read through tests/integration/panel.py (PanelV3), the interface
the v2 suite reads its draws through too (task 5.0).

Time is the chain's. Panels' windows are the deployment's (#251, L4); the devnet deploys the production ones, in
hours and days (SEAL_WINDOW 2 h, REVEAL_WINDOW 1 h, a k = 1 window of 168 h), as Sepolia will, so this run moves the
chain's clock (evm_increaseTime, a devnet affordance) to the next deadline whenever no node has anything to do. Every duration it
prints is chain time under the real windows. A validator run outside this harness (POF_V3_EXTERNAL, its addresses,
comma-separated: a real SEV-SNP host, #251 L18 item 3) acts in wall time, so the clock doesn't pass a deadline its open
seat still has to meet: it waits, up to POF_V3_EXTERNAL_WAIT seconds a seat (default 900; the host's cold start takes
about 127 s, validator-kit/SEVSNP-PLAN.md), then lets the seat be missed. The devnet's 2-second blocks are switched to mining on demand for the
run (evm_setIntervalMining 0, evm_setAutomine).

The story, in order (each step needs the one before):
1. the genesis validator alone, k = 1: candidates register (scenario 6: registration); a registration check is judged
   by the genesis validator alone and held, with two candidates as shadows; a second registration that nobody claims
   on the host is passed anyway by a lying genesis judge (a wrong k = 1 verdict), and a watcher challenges it: the
   challenge waits, since no panel of 3 exists yet;
2. qualification: registrations until three candidates have qualified by their shadow verdicts (k reaches 3); the
   submissions that waited meanwhile were shadowed; a check judged by a panel of 3 is final after its window;
3. a waiting bounty (task 5.1, second bullet): that registration's bounty opens, is funded above k = 1's limit, and a
   fix is sealed: it waits (only the genesis validator's bond covers that bounty), shadowed by candidates, until two
   validators top up their bonds; then it is drawn with k = 3, judged, won and claimed (a third tops up after the draw,
   so the verdict's random audit, if due, has an auditor outside its panel);
4. a silent judge (scenario 4): a drawn validator never answers on its seat; it is slashed for silence and replaced
   from the same sample, and the panel still decides with k verdicts and k usage reports;
5. k reaches 5: two more candidates qualify, and a check is judged by a counted panel of 5;
6. the k = 1 hold (first bullet): the held verdict was audited twice while held, its window started only once three
   validators who could judge its challenge were active (its auditors sit out, so five beside the genesis one), and
   it became final after its window, not before;
7. the challenge (third bullet): the wrong k = 1 verdict's challenge is drawn (a fresh panel of 3, without its judge
   or its auditors), it reverses the verdict, the challenger's stake returns, and the registration ends forfeited.
   Time to heal, k = 1: the chain time from the wrong pass to its reversal;
8. with --heal, time to heal for a paid fix: once validators v1-v8 have qualified (#251 L25: a challenge that can't be
   drawn by CHALLENGE_DEADLINE lapses, so the network that can judge it is grown first), a bad fix is passed by a panel
   of 3 of the four validators bonded for its bounty, three of whom lie; it wins and is claimed; the others top up and
   an honest validator challenges it; a fresh panel of 5 reverses it, the award is clawed back with nothing earned, and
   the bounty reopens. A challenge that lapses (none here, normally) is filed again once a panel could be drawn.

10. protected tests (#251 L20, task 4.8): a repository of real code on this machine (git over file://) whose
   `.pof/check.json` protects `tests/`. A bad fix that also weakens its protected test fails, and so does the same bad
   fix without that edit: every judge ran the base's test, twice in a fresh container each (L22), on a run tree whose
   hash is the unedited fix's tree. A good fix passes. These fixes' tests run in the real Docker sandbox; without the
   overlay, the weakened fix's own tests pass, as the run shows.

What it doesn't cover is listed at the end of the run (and in reports/devnet-v3-local.md)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from bot import logic  # noqa: E402
from e2e_node_v3 import COIN, ETH_100, Host, Run, check, keys_for, simulator  # noqa: E402
from oracle import abi, checkconfig, crypto, fetch, node_v3, sandbox, v2, v3  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.node_v3 import NodeV3  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from oracle.rpc import Reverted, Rpc, Wallet  # noqa: E402
from oracle.transport import OnchainExchange  # noqa: E402
from panel import PanelV3  # noqa: E402

TEES = ("intel-tdx", "amd-sev-snp", "aws-nitro-enclaves")  # spread, so the TEE-type cap lets k = 5 and 7 fill
FAMILIES = ["fake"] + [f"fake-{i}" for i in range(1, 9)]  # one family per validator: the family cap allows 1 at k = 3
HOUR, DAY, WEEK = 3600, 86400, 7 * 86400
REPORT_WINDOW = 86400
WON, CLAIMED, OPEN = 2, 3, 1  # RaceV3Base.State ("Merged": claimed; the head moves at finality, #251 L9)
PASS, FAIL = 1, 2  # RaceV3Base.Outcome
FORFEITED = 4  # RaceV3Base.IssueState


def hours(seconds: float) -> str:
    return f"{seconds / HOUR:,.1f} h"


def topic(signature: str) -> str:
    return "0x" + crypto.keccak256(signature.encode()).hex()


class Forge(Host):
    """The fake repository host: the registrations' claims (Host) and the fixes' pull requests."""

    def __init__(self) -> None:
        super().__init__()
        self._pulls: list = []

    def pulls(self, state="all"):
        return list(self._pulls)

    def add_pull(self, title: str, body: str, sha: str, base: str = "") -> int:
        self._pulls.append({"number": 500 + len(self._pulls), "title": title, "body": body, "head_sha": sha,
                            "base_sha": base, "state": "open"})
        return self._pulls[-1]["number"]


class Sources:
    """The nodes' fetcher: the protected-tests scenario's repository (step 10) through a real fetcher (oracle/fetch.py,
    git over file://), every other fix as before: a checkout already under the source root, and no repository
    settings at its base (so the sandbox's own command, and nothing protected)."""

    def __init__(self) -> None:
        self.real: fetch.Fetcher | None = None
        self.shas: set = set()

    def use(self, url: str, shas, log) -> None:
        self.real = fetch.Fetcher(url, log=log)
        self.shas |= set(shas)

    def ensure(self, root, sha, fix) -> bool:
        if self.real is not None and sha in self.shas:
            return self.real.ensure(root, sha, fix)
        return (Path(root) / sha).is_dir()

    def file_at(self, root, sha, path, max_bytes):
        if self.real is not None and sha in self.shas:
            return self.real.file_at(root, sha, path, max_bytes)
        return fetch.Blob()


STATS = "def mean(xs):\n    return sum(xs) / len(xs)\n\n\ndef median(xs):\n    return {median}\n"
GOOD_MEDIAN = "(sorted(xs)[(len(xs) - 1) // 2] + sorted(xs)[len(xs) // 2]) / 2"
MEAN_TEST = ("import unittest\n\nfrom stats import mean\n\n\nclass Mean(unittest.TestCase):\n"
             "    def test_mean(self):\n        self.assertEqual(mean([1, 2, 3]), 2)\n")
WEAK_TEST = "import unittest\n\n\nclass Mean(unittest.TestCase):\n    def test_mean(self):\n        pass\n"
ISSUE_TEST = ("import unittest\n\nfrom stats import median\n\n\nclass Issue(unittest.TestCase):\n"
              "    def test_median(self):\n        self.assertEqual(median([4, 1, 3, 2]), 2.5)\n")
SUITE = ["python", "-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-q"]


def git(cwd: Path, *args) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-c", "user.name=pof", "-c", "user.email=pof@example.invalid",
                           "-c", "init.defaultBranch=main", *args], cwd=str(cwd), env=env, capture_output=True,
                          text=True, check=True).stdout.strip()


class ProtectedRepo:
    """Step 10's repository, on this machine: a base whose `.pof/check.json` runs its suite and protects `tests/`
    (its test of `mean`), and fixes for an issue about `median` on branches off it."""

    def __init__(self, root: Path) -> None:
        root = Path(root).resolve()
        self.work, self.bare = root / "work", root / "repo.git"
        self.work.mkdir(parents=True)
        git(root, "init", "-q", "--bare", str(self.bare))
        git(self.work, "init", "-q")
        self.base = self.commit({"stats.py": STATS.format(median="0"), "tests/test_stats.py": MEAN_TEST,
                                 ".pof/check.json": json.dumps({"commands": [SUITE], "protected": ["tests/"]})},
                                "the base: its suite, tests/ protected", parent="")
        self.url = f"file://{self.bare}"

    def commit(self, files: dict, message: str, parent: str | None = None) -> str:
        if parent:
            git(self.work, "checkout", "-q", "--detach", parent)
        for name, data in files.items():
            path = self.work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", message)
        sha = git(self.work, "rev-parse", "HEAD")
        git(self.work, "push", "-q", str(self.bare), f"{sha}:refs/heads/c-{sha[:12]}")
        return sha

    def fix(self, files: dict, message: str) -> str:
        return self.commit(files, message, parent=self.base)

    def tree(self, sha: str) -> str:
        return git(self.work, "rev-parse", f"{sha}^{{tree}}")


FEED_EVERY = 6 * HOUR  # while `drive` is fed (validators qualifying), at least this often in chain time
LAST_CALL = HOUR  # a watcher's last moment to re-file a lapsed challenge before the verdict's window closes
EXTERNAL_WAIT_S = 900.0  # how long (wall time) the clock waits on one seat of a validator run outside the harness


def external_hold(seats: list, external: set, now: int) -> list:
    """The deadlines the moved clock mustn't pass yet (#251 L18 item 3: a validator run outside this harness, such as
    a real SEV-SNP host, acts in wall time; its cold start takes about 2 minutes, validator-kit/SEVSNP-PLAN.md). From
    `seats` ({"pid", "slot", "key", "sealBy", "revealBy", "allSealed", "hasSeal", "revealed", "closed"} per open seat):
    each seat of an `external` key that can still seal (before its sealBy) or reveal (every seat sealed, before
    revealBy) and hasn't. Returns [(pid, slot, phase, deadline)], phase "seal" or "reveal"."""
    out = []
    for x in seats:
        if x["closed"] or x["key"].lower() not in external:
            continue
        if not x["hasSeal"] and now <= x["sealBy"]:
            out.append((x["pid"], x["slot"], "seal", x["sealBy"]))
        elif x["hasSeal"] and x["allSealed"] and not x["revealed"] and now <= x["revealBy"]:
            out.append((x["pid"], x["slot"], "reveal", x["revealBy"]))
    return out


class LiveChain(v3.Chain):
    """v3.Chain whose keeper list is the submissions this run still has open: a node's keeper reads every submission
    since its start block on each pass, which is quadratic over a run of a few hundred checks."""

    live: dict = {}

    def registered(self, from_block: int, to_block=None) -> list:
        return [{"issue": 0, "submission": s, "block": 0} for s in self.live]

    def committed(self, from_block: int, to_block=None) -> list:
        return []


class Node(NodeV3):
    """A validator's node the run can make lie on chosen submissions, or keep silent on chosen panels."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.lies: set = set()
        self.mute: set = set()  # panels this node never answers on, as if it were down for them
        self.silent_on = None  # or a test of a panel id: True keeps it silent there (scenarios_v3's stuck panel)
        self.no_report: set = set()  # (pid, its address): seals and reveals there, never reports its usage (p)

    def _report(self, r, now: int, p: dict, slot: int, seat: dict) -> bool:
        if (r.pid, self.address.lower()) in self.no_report:
            return False
        return super()._report(r, now, p, slot, seat)

    def _take(self, pid: int) -> bool:
        if pid in self.mute or (self.silent_on is not None and self.silent_on(pid)):
            self.finished.add(pid)
            return False
        return super()._take(pid)

    def _judge(self, s: int, p: dict, late: bool = False, seat: tuple | None = None):
        self.judge.lie = s in self.lies
        try:
            return super()._judge(s, p, late, seat)
        finally:
            self.judge.lie = False


class Net(Run):
    """The local v3 network: the chain, the fake host, the nodes, and a clock that jumps to the next deadline."""

    def __init__(self, rpc: Rpc, record: dict, work: Path, verbose: bool) -> None:
        rpc.call("evm_setIntervalMining", [0])  # the devnet mines every 2 s: on demand for this run
        rpc.call("evm_setAutomine", [True])
        Wallet.poll_s = 0.002
        self.verbose = verbose
        work.mkdir(parents=True, exist_ok=True)
        self.node_log = open(work / "nodes.log", "a", encoding="utf-8")
        super().__init__(rpc, record, work)
        self.chain = LiveChain(rpc, record["race"])
        self.chain.live = {}
        self.host = Forge()
        self.panel = PanelV3(self.chain)
        self.bad: set = set()  # the fixes whose tests fail
        self.sources = Sources()  # step 10's fixes are real code, fetched; the rest are stand-ins
        self.funder = self.account("funder")
        self.solver = self.account("solver")
        self.anyone = self.account("anyone")
        self.fund(self.reporter.address, 1_000_000)
        self.minter.send(self.chain.coin(), "approve(address,uint256)", self.chain.registry, 2**255)
        self.fund(self.minter.address, 1_000)  # its pokes' top-ups (`fund`: the mock minted, or another coin sent)
        self.t0 = self.chain.now()
        self.open_panels: set = set()
        self.seen_panels = 0
        self.jumps = 0
        self.pokes = 0
        self.live_values: dict | None = None  # Panels' L19 values, read once (jump)
        self.names: dict = {}
        self.next_index = 1
        self.rad_nodes: dict = {}  # name -> its Radicle node key (32 bytes); the spike sets its nodes' real keys
        self.watches: list = []  # called at each step of `drive`: a watcher re-filing a lapsed challenge (#251 L25)
        self.last_calls: set = set()  # submissions whose watcher gets a turn LAST_CALL before their window closes
        # validators run outside the harness (#251 L18 item 3): the clock waits for their seats (`held_by_external`)
        self.external = {a.strip().lower() for a in os.environ.get("POF_V3_EXTERNAL", "").split(",") if a.strip()}
        self.external_wait_s = float(os.environ.get("POF_V3_EXTERNAL_WAIT", EXTERNAL_WAIT_S))
        self.external_waits: dict = {}

    def account(self, name: str) -> Wallet:
        w = Wallet(self.rpc, int.from_bytes(crypto.keccak256(f"pof devnet v3 e2e {name}".encode()), "big") % crypto.N or 1,
                   name)
        self.fund(w.address, 100_000)
        w.send(self.chain.coin(), "approve(address,uint256)", self.chain.race, 2**255)
        return w

    def log(self, who: str):
        def write(m):
            self.node_log.write(f"[{who}] {m}\n")
            if self.verbose:
                print(f"  [{who}] {m}", flush=True)
        return write

    # ---------- the validators ----------

    def make_node(self, name: str, family: str, keeper: bool = False, tag: str = "") -> Node:
        keys = keys_for(self.sim, name)
        wallet = Wallet(self.rpc, keys.account_secret(), name)
        me = keys.address()
        self.names[me.lower()] = name
        node = Node(self.chain, keys, FakeJudge(family=family), self.host, "demo/median", self.work / "src",
                    OnchainExchange(self.chain, keys, wallet=wallet), Store(self.work / "receipts"),
                    runner=self.tests, log=self.log(name + tag), wallet=wallet,
                    rounds=Rounds(self.work / "rounds", self.chain.chain_id(), self.chain.race, me + tag),
                    keeper=keeper, costs={"vcpu_second": 12_000_000, "gb_second": 1_300_000} if keeper else None,
                    seal_margin=3 * HOUR)  # a check that can't be run is sealed at once as not passed
        node.fetcher = self.sources
        return node

    def tests(self, argv: list) -> tuple:
        """Stands in for the Docker sandbox: a bad fix's tests fail. No fix's code exists, so none is run. Step 10's
        fixes are real code: their run trees and checkouts run in the real sandbox (oracle/sandbox.py's CLI runner)."""
        mount = next((a[:-len(":/src:ro")] for a in argv if str(a).endswith(":/src:ro")), "")
        if "/.run-" in mount or Path(mount).name in self.sources.shas:
            return sandbox.docker_runner(argv)
        text = " ".join(str(a) for a in argv)
        return (1, "", "1 failed") if any(sha in text for sha in self.bad) else (0, "ok", "")

    def rad_node(self, name: str) -> bytes:
        """The Radicle node key `name` registers with (#251, L11): its node's, when the run has real nodes; otherwise a
        stand-in key of its own (no Radicle node runs in this suite; the registry only needs 32 distinct bytes)."""
        return self.rad_nodes.get(name) or crypto.keccak256(f"pof devnet v3 radicle node {name}".encode())

    def join(self, i: int, bond: int = 100) -> Node:
        """Validator v<i> registers as a candidate: its own family, host, operator and Radicle node key, bonded, signed
        by its key."""
        name = f"v{i}"
        keys = keys_for(self.sim, name)
        self.fund(keys.address(), 5_000)
        node_v3.register(self.chain, keys, Wallet(self.rpc, keys.account_secret(), name), bond * COIN,
                         self.work / "receipts", log=self.log(name), proof="simulated", family=FAMILIES[i],
                         host=f"host-{i}", image=v2.DEVNET_IMAGE, tee_type=TEES[i % 3],
                         rad_node=self.rad_node(name))
        self.nodes[name] = self.make_node(name, FAMILIES[i])
        return self.nodes[name]

    def join_next(self, bond: int = 100) -> str:
        self.join(self.next_index, bond)
        self.next_index += 1
        return f"v{self.next_index - 1}"

    def outside(self, s: int) -> list:
        """The active validators that could judge a challenge of `s`: not on its counted panel, not its auditors."""
        inside = {k.lower() for k in self.panel.drawn(s)}
        for pid, _, _ in panels_of(self, s, v3.AUDIT):  # every auditor ever seated, a replaced one too: all sit out
            inside |= {"0x" + log["topics"][2][-40:].lower() for log in self.evs(self.chain.panels, v3.SEATED, pid)}
        return [name for name, node in self.nodes.items()
                if self.drawable(node.address) and node.address.lower() not in inside]

    def watch(self, watcher, s: int) -> None:
        """`watcher` re-files `s`'s challenge after a lapse (`rechallenge`), and the clock stops LAST_CALL before
        `s`'s window closes so it can."""
        self.last_calls.add(s)
        self.watches.append(lambda: self.rechallenge(watcher, s))

    def rechallenge(self, watcher, s: int) -> bool:
        """#251 L25: a challenge with no panel by CHALLENGE_DEADLINE lapses (the verdict stands; the keeper settles
        the lapse and the stake and cover come back). The watcher files it again once a fresh challenge panel could
        be drawn (enough validators outside the panel and its auditors), while the verdict still passes, is open to a
        challenge and has had fewer than MAX_REDRAWS lapses; and, at the latest, LAST_CALL before its window closes,
        so the challenge holds the window while the network grows to judge it (else the wrong pass would be final).
        Before this last call, a random audit that sat a third validator out of a k = 1 verdict's challenge left
        too few to judge it until after its window: the wrong pass became final (one run in ten, #256)."""
        c = self.chain
        v = c.verdict(s)
        if v["challengeOpen"] or not v["lapses"] or not v["pass"] or v["status"] not in (v3.HELD, v3.WINDOW):
            return False
        if self.live_values is None:
            self.live_values = c.liveness()
        if v["lapses"] >= self.live_values["maxRedraws"] or (v["status"] == v3.WINDOW and c.now() >= v["finalAt"]):
            return False
        need = self.rpc.view(c.panels, "challengeRange(uint256)", ["uint256", "uint256"], v["k"])[1]
        # its audits still to be drawn take validators from outside the panel too (a k = 1 verdict gets K1_AUDITS)
        due = v["auditsDue"] if v["auditDecided"] else (2 if v["k"] == 1 else 0)
        ready = len(self.outside(s)) >= need + max(0, due - v["auditsDrawn"])
        last_call = v["status"] == v3.WINDOW and v["finalAt"] - c.now() <= LAST_CALL
        if not (ready or last_call):
            return False
        if v["filedLapsed"]:
            try:
                self.anyone.send(c.race, "settleLapse(uint256)", s)  # its stake and cover first (a keeper's call)
            except Reverted:
                pass
        watcher.challenge(s, force=True)
        when = (f"once a fresh panel of {need} could be drawn" if ready else
                f"before its window closed, so it holds while the network grows: no fresh panel of {need} could be "
                f"drawn yet ({len(self.outside(s))} outside its panel and auditors)")
        print(f"    (its challenge lapsed at CHALLENGE_DEADLINE {v['lapses']} time(s), with no panel; the stake came "
              f"back; {self.name(watcher.address)} filed it again {when})", flush=True)
        return True

    def drawable(self, key: str) -> bool:
        return self.rpc.view(self.chain.registry, "isDrawable(address)", ["bool"], key)[0]

    def name(self, key: str) -> str:
        return self.names.get(key.lower(), key[:10])

    def named(self, keys) -> str:
        return ", ".join(self.name(k) for k in keys)

    def active(self) -> list:
        return [n for n, node in self.nodes.items() if self.chain.is_active(node.address)]

    def top_up(self, name: str, to: int) -> None:
        node = self.nodes[name]
        have = self.chain.validator(node.address)["bond"]
        if have >= to:
            return
        node.wallet.send(self.chain.coin(), "approve(address,uint256)", self.chain.registry, to - have)
        node.wallet.send(self.chain.registry, "topUp(address,uint256)", node.address, to - have)

    def eligible(self, bounty: int) -> int:
        return self.rpc.view(self.chain.registry, "eligibleCount(uint256)", ["uint256"], bounty)[0]

    def bond_for(self, bounty: int) -> int:
        """The bond that makes a validator eligible for `bounty`: BOND_FACTOR × its tier's step."""
        reg = self.chain.registry
        tier = self.rpc.view(reg, "tierOf(uint256)", ["uint256"], bounty)[0]
        return (self.rpc.view(reg, "BOND_FACTOR()", ["uint256"])[0]
                * self.rpc.view(reg, "tierStep(uint256)", ["uint256"], tier)[0])

    # ---------- issues, bounties and fixes ----------

    def register_issue(self, claim: bool = True) -> tuple:
        receipt = self.reporter.send(self.chain.race, "register(bytes32,bool)", self.chain.repo(), False)
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic(v3.REGISTERED))
        issue, s = int(log["topics"][1], 16), abi.decode(["uint256"], abi.hexdata(log["data"]))[0]
        if claim:
            self.host.claim(issue, self.reporter.address)
        self.chain.live[s] = True
        return issue, s

    def open_bounty(self, issue: int) -> int:
        receipt = self.anyone.send(self.chain.race, "openBounty(uint256)", issue)
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic("BountyOpened(uint256,uint256)"))
        return int(log["topics"][1], 16)

    @staticmethod
    def fix_sha(label: str) -> str:
        return hashlib.sha1(f"pof devnet v3 fix {label}".encode()).hexdigest()

    def submit_fix(self, bounty: int, issue: int, label: str, good: bool, base: bytes | None = None,
                   solver: Wallet | None = None) -> tuple:
        """The solver (`solver`, default the run's) seals a fix on `base` (default: the repository's head now; the race
        serves one repository and its merge at finality moves its head only from the base, #251 L1 and L9) and opens
        its pull request. Returns (the submission, the commitment's opening)."""
        w = self.solver if solver is None else solver
        base = self.chain.head() if base is None else base
        sha = self.fix_sha(label)
        (self.work / "src" / sha).mkdir(parents=True, exist_ok=True)
        if not good:
            self.bad.add(sha)
        fix, salt = v2.commit_word(sha), crypto.keccak256(f"salt {label}".encode())
        w.send(self.chain.race, "attempt(uint256)", bounty)
        receipt = w.send(self.chain.race, "commit(uint256,bytes32)", bounty, v3.fix_commitment(fix, base, salt, w.address))
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic(v3.COMMITTED))
        s = int(log["topics"][2], 16)
        self.host.add_pull(f"Fix the median ({label})",
                           logic.pr_body(100 + issue, bounty, s, "0x" + salt.hex(), w.address), sha,
                           base[:20].hex())
        self.chain.live[s] = True
        return s, (fix, base, salt)

    def submit_real(self, bounty: int, issue: int, label: str, sha: str, base: str) -> int:
        """Step 10: a solver of its own seals a real commit `sha` and opens its pull request against the git commit
        `base`, whose `.pof/check.json` the judges read. The seal's base is 0 (a repository outside the head
        registry's history: this repository isn't Heads' genesis), which the node accepts as before."""
        w = self.account(f"protected {label}")
        fix, salt = v2.commit_word(sha), crypto.keccak256(f"salt {label}".encode())
        w.send(self.chain.race, "attempt(uint256)", bounty)
        receipt = w.send(self.chain.race, "commit(uint256,bytes32)", bounty,
                         v3.fix_commitment(fix, v3.ZERO, salt, w.address))
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic(v3.COMMITTED))
        s = int(log["topics"][2], 16)
        self.host.add_pull(f"Fix the median ({label})", logic.pr_body(100 + issue, bounty, s, "0x" + salt.hex(),
                                                                      w.address), sha, base)
        self.chain.live[s] = True
        return s

    def merged_fix(self, solver: Wallet, bounty: int, issue: int, label: str) -> int:
        """`solver`'s good fix to `bounty`, judged, claimed, final and merged by a keeper (the head moves to it).
        Returns its submission."""
        s, opening = self.submit_fix(bounty, issue, label, good=True, solver=solver)
        self.drive(lambda: self.bounty_state(bounty) == WON and self.chain.bounty(bounty)["winner"] == s,
                   f"{label}: won")
        solver.send(self.chain.race, "claim(uint256,bytes32,bytes32,bytes32)", bounty, *opening)
        self.drive(lambda: self.chain.award(bounty, self.chain.bounty(bounty)["epoch"])["merged"], f"{label}: merged",
                   poke=True)
        return s

    def bounty_state(self, b: int) -> int:
        return self.chain.bounty(b)["state"]

    # ---------- events and time ----------

    def evs(self, contract: str, signature: str, *topics) -> list:
        ts = [topic(signature)] + ["0x" + crypto.word(t).hex() if t is not None else None for t in topics]
        return self.rpc.logs(contract, self.start, ts)

    def when(self, log: dict) -> int:
        """A log's block time."""
        return int(self.rpc.call("eth_getBlockByNumber", [log["blockNumber"], False])["timestamp"], 16)

    def warp(self, seconds: int, blocks: int = 6) -> None:
        self.rpc.call("evm_increaseTime", [int(seconds)])
        for _ in range(blocks):
            self.rpc.call("evm_mine", [])

    def jump(self) -> bool:
        """Nothing to do now: move the chain's clock to the next deadline (a panel's seal or reveal deadline, a
        window's end, a deposit's return; since #251's batch 2 also a waiting submission's scheduled redraw, and the
        release of a stuck panel or of audits nobody can take, L19), or only mine the blocks a draw's seed waits for.
        False, with nothing moved, when there is no deadline ahead."""
        c, now, targets = self.chain, self.chain.now(), []
        if self.live_values is None:
            self.live_values = c.liveness()
        grace = self.live_values["stuckGrace"]
        block, blocks_only = c.block(), False  # a draw waits for its seed block: only blocks are needed, not time
        count = c.panel_count()
        self.open_panels |= set(range(self.seen_panels + 1, count + 1))
        self.seen_panels = count
        for pid in sorted(self.open_panels):
            p = c.panel(pid)
            if p["counted"] or p["closed"] or now > p["revealBy"] + grace + DAY:
                self.open_panels.discard(pid)
                continue
            targets += [p["sealBy"] + 1, p["revealBy"] + 1]
            if p["seats"] < p["k"] and p["kind"] in (v3.COUNTED, v3.AUDIT, v3.CHALLENGE):
                targets.append(p["revealBy"] + grace + 1)  # replacements exhausted: released then (L19, L25)
        for s in list(c.live):
            v = c.verdict(s)
            st = v["status"]
            blocks_only |= st == v3.SEALED and block <= v["seedBlock"] + 1
            if st in (v3.HELD, v3.WINDOW):
                blocks_only |= v["auditBlock"] + 1 >= block and not (v["auditDecided"] and v["auditsDrawn"] == v["auditsDue"])
                blocks_only |= (v["challengeOpen"] and v["challengePid"] == 0 and v["challengeEpoch"] == 0
                                and v["challengeBlock"] + 1 >= block)
            if st in (v3.HELD, v3.WINDOW) and v["challengeOpen"] and v["challengePid"] == 0:
                targets.append(v["challengeBy"] + 1)  # no panel by its deadline: it lapses then (L25)
                if v["challengeEpoch"]:
                    targets.append(v["challengeRetryAt"])  # a waiting challenge's scheduled redraw (L25)
            if st == v3.WAITING and v["retryAt"]:
                targets.append(v["retryAt"])  # its scheduled redraw (L19's RETRY_DELAY, L16's capacity hour)
            if st == v3.WINDOW and v["auditStuckAt"] and v["auditsDrawn"] < v["auditsDue"]:
                targets.append(v["auditStuckAt"] + grace + 1)  # audits nobody can take: released then (L19)
            if v["status"] == v3.WINDOW and not v["challengeOpen"]:
                targets.append(v["finalAt"])
                if s in self.last_calls:
                    targets.append(v["finalAt"] - LAST_CALL)  # its watcher's last call (`rechallenge`)
            elif v["status"] == v3.FINAL:
                if c.submission(s)["done"]:
                    del c.live[s]
                else:
                    targets.append(v["finalAt"] + REPORT_WINDOW + 1)
            elif v["status"] == v3.RELEASED and not c.submission(s)["done"]:
                targets.append(now + 1)  # the race's refund is due now
            elif v["status"] not in (v3.SEALED, v3.WAITING, v3.JUDGING, v3.HELD, v3.WINDOW):
                del c.live[s]
        ahead = [t for t in targets if t > now]
        if blocks_only:
            self.warp(12)  # six blocks, 2 s apart as on the devnet
            return True
        if not ahead:
            return False
        hold = self.held_by_external(now)
        if hold is not None and min(ahead) > hold:
            time.sleep(2)  # an outside validator's seat is open: wall time, not the moved clock, until it acts
            return True
        if min(ahead) - now > 6 * HOUR and os.environ.get("POF_V3_SHOW_JUMPS"):  # a long jump, said (diagnostics)
            vs = {s_: c.verdict(s_) for s_ in c.live}
            shown = sorted(vs, key=lambda s_: vs[s_]["status"] == v3.FINAL)[:12]  # the ones not final first

            def said(s_: int) -> str:
                seed = f" (seed block {vs[s_]['seedBlock']})" if vs[s_]["status"] == v3.SEALED else ""
                return f"{s_}:{v3.STATUS[vs[s_]['status']]}{seed}"
            print(f"  jump {hours(min(ahead) - now)} at block {block}: live " + ", ".join(map(said, shown)), flush=True)
        self.warp(min(ahead) - now)
        self.jumps += 1
        return True

    def held_by_external(self, now: int):
        """The earliest deadline an outside validator (POF_V3_EXTERNAL, comma-separated addresses) still has to act
        by, or None: each of its open seats holds the clock for at most EXTERNAL_WAIT_S of wall time (then it is
        missed, as a silent seat is)."""
        if not self.external:
            return None
        c, seats = self.chain, []
        for pid in sorted(self.open_panels):
            p = c.panel(pid)
            keys = c.judges(pid)
            if not any(k and k.lower() in self.external for k in keys):
                continue
            rows = [c.seat(pid, i) for i in range(len(keys))]
            for i, (k, s) in enumerate(zip(keys, rows)):
                if k:
                    seats.append({"pid": pid, "slot": i, "key": k, "sealBy": p["sealBy"], "revealBy": p["revealBy"],
                                  "allSealed": p["nSealed"] >= p["seats"], "hasSeal": s["hasSeal"],
                                  "revealed": s["revealed"], "closed": p["closed"] or p["counted"]})
        wall, due = time.time(), []
        for pid, slot, phase, deadline in external_hold(seats, self.external, now):
            first = self.external_waits.setdefault((pid, slot, phase), wall)
            if wall - first < self.external_wait_s:
                due.append(deadline)
        return min(due) if due else None

    def poke(self) -> None:
        """Changes the registry's epoch (a 1 micro-coin top-up of the genesis bond, by anyone): a waiting draw is
        retried only after the registry changes."""
        self.minter.send(self.chain.registry, "topUp(address,uint256)", self.nodes["genesis"].address, 1)

    def history(self, s: int) -> str:
        """Submission `s`'s life on-chain, for a run that stopped: its verdict now, then its panels, audits,
        challenges and lapses in chain-time order (hours since the deployment)."""
        c = self.chain
        v = c.verdict(s)
        keys = ("status", "k", "pass", "lapses", "challengeOpen", "challengePid", "challengeBy", "filedLapsed",
                "auditDecided", "auditsDue", "auditsDrawn", "auditsDone", "finalAt")
        now = {k: (v3.STATUS[v[k]] if k == "status" else v.get(k)) for k in keys}
        rows = []
        for contract, sig in ((c.panels, "Drawn(uint256,uint256,uint8,uint256,bytes32)"),
                              (c.panels, "Audited(uint256,uint256,address,bool)"),
                              (c.panels, "ChallengeOpened(uint256,address,bytes32)"),
                              (c.panels, "ChallengeWaits(uint256)"), (c.panels, "SecondDraw(uint256,uint256)"),
                              (c.panels, "ChallengeLapsed(uint256,uint256)"),
                              (c.panels, "Released(uint256,uint256,uint256)"),
                              (c.panels, "ChallengeReleased(uint256,uint256,bool)"),
                              (c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)"),
                              (c.panels, "WindowStarted(uint256,uint256)"), (c.panels, "Final(uint256,bool)"),
                              (c.race, "ChallengeFiled(uint256,address)"),
                              (c.race, "ChallengeSettled(uint256,uint256,bool)"),
                              (c.race, "ChallengeLapsed(uint256,address,uint256)")):
            for log in self.evs(contract, sig, s):
                extra = ""
                if sig.startswith("Drawn"):
                    kind, k, _ = abi.decode(["uint8", "uint256", "bytes32"], abi.hexdata(log["data"]))
                    extra = f" panel {int(log['topics'][2], 16)} {v3.KINDS[kind]} k={k}"
                elif sig.startswith("Audited"):
                    extra = (f" by {self.name('0x' + log['topics'][3][-40:])} agrees="
                             f"{abi.decode(['bool'], abi.hexdata(log['data']))[0]}")
                rows.append((int(log["blockNumber"], 16), self.when(log), sig.split("(")[0] + extra))
        rows.sort()
        lines = [f"submission {s} now: {now}; chain time now {hours(c.now() - self.t0)}"]
        lines += [f"  {hours(t - self.t0):>10} block {b}: {what}" for b, t, what in rows]
        return "\n".join(lines)

    def drive(self, until, what: str, steps: int = 20000, idle_max: int = 40, poke: bool = False,
              strict: bool = True, only=None, feed=None, explain=()) -> bool:
        """Ticks every node; when none makes progress, jumps to the next deadline. With no deadline ahead the network
        is idle: `feed`, if given, is called for more work (new registrations; it returns False when it has no more),
        and at least every FEED_EVERY of chain time anyway;
        otherwise the clock moves on a little (half an hour; with `poke`, six blocks and a change of the registry's
        epoch, so a draw that waits for a registry change is retried). After `idle_max` idle moments in a row with
        no deadline reached in between it gives up: an error when `strict`, else False. `only`: the nodes that run
        meanwhile (default: all)."""
        stalls = 0
        fed = self.chain.now()
        for _ in range(steps):
            if until():
                return True
            for watch in self.watches:
                watch()
            if any([n.tick(self.start) for name, n in self.nodes.items() if only is None or name in only]):
                continue
            before = self.jumps
            if only is not None:  # the others aren't running: no deadline of theirs may pass meanwhile, only blocks
                stalls += 1
                if stalls > idle_max:
                    break
                self.warp(12)
                continue
            if feed is not None and self.chain.now() - fed >= FEED_EVERY and feed():
                # work keeps coming while the clock moves: a challenge waiting for validators to qualify (#251
                # L25) has a retry deadline every RETRY_DELAY, so the network is never idle and is otherwise never fed
                fed = self.chain.now()
                continue
            if self.jump():
                stalls = 0 if self.jumps > before else stalls
                continue
            stalls += 1
            if stalls > idle_max:
                break
            if feed is not None and feed():
                fed = self.chain.now()
                continue
            if poke:
                self.poke()
                self.pokes += 1
            self.warp(12 if poke else 1800)
        if strict:
            for s in explain:  # what the run was waiting on, for a stop that is hard to reproduce
                print(self.history(s), flush=True)
            raise AssertionError(f"not reached: {what}")
        return False

    def quiet(self, s: int, final: bool = False) -> bool:
        """Submission `s` needs nothing more for now: held, waiting or final (not counted and in its window), its
        shadows' deadlines recorded. `final`: only final counts."""
        v = self.chain.verdict(s)
        ok = (v3.FINAL,) if final else (v3.HELD, v3.WAITING, v3.FINAL)
        sp = v["shadowPid"]
        return v["status"] in ok and (sp == 0 or self.chain.panel(sp)["closed"])

    def feeder(self, batch: int, rounds: int):
        """More work for an idle network: `batch` new registrations at a time, at most `rounds` times."""
        made = [0]

        def feed() -> bool:
            if made[0] >= batch * rounds:
                return False
            for _ in range(batch):
                self.register_issue()
            made[0] += batch
            return True
        return feed, made

    def grow(self, want: list, batch: int, what: str, rounds: int = 40) -> int:
        """Registers issues, `batch` at a time whenever the network is idle, until every validator in `want` has
        qualified by its shadow verdicts. Returns how many checks it took."""
        feed, made = self.feeder(batch, rounds)
        self.drive(lambda: all(self.chain.is_active(self.nodes[n].address) for n in want), what, feed=feed, poke=True)
        return made[0]

    def seats_reported(self, pid: int) -> int:
        p = self.chain.panel(pid)
        return sum(1 for i in range(p["k"]) if self.chain.usage_of(pid, i).receipt != v3.ZERO)


def panels_of(n: Net, s: int, kind: int) -> list:
    """Submission `s`'s panels of a kind, by their Drawn events: [(pid, k, the log)]."""
    out = []
    for log in n.evs(n.chain.panels, "Drawn(uint256,uint256,uint8,uint256,bytes32)", s):
        k_kind, k, _ = abi.decode(["uint8", "uint256", "bytes32"], abi.hexdata(log["data"]))
        if k_kind == kind:
            out.append((int(log["topics"][2], 16), k, log))
    return out


def heal_times(n: Net, s: int) -> dict:
    """The chain times of a wrong verdict's life: counted, challenged, its challenge panel drawn, reversed, settled."""
    c = n.chain
    counted = n.evs(c.panels, "Counted(uint256,uint256,bool,uint256,uint8)", s)[0]
    filings = n.evs(c.race, "ChallengeFiled(uint256,address)", s)
    first, filed = filings[0], filings[-1]  # a challenge that lapsed (L25) was filed again
    cpid, kc, drawn = panels_of(n, s, v3.CHALLENGE)[-1]
    # the challenge that panel judged: the last opened before its draw, filed at the race or opened by an auditor's
    # mismatch (#251 L25 lapses either; a watcher re-files)
    opened = [o for o in n.evs(c.panels, "ChallengeOpened(uint256,address,bytes32)", s)
              if int(o["blockNumber"], 16) <= int(drawn["blockNumber"], 16)]
    resolved = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s)[-1]
    settled = n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s)
    if opened:
        filed = opened[-1]
    by = "filed" if any(int(x["topics"][2], 16) == cpid for x in settled) else "auditor"
    t = {"counted": n.when(counted), "first": n.when(first), "filed": n.when(filed), "drawn": n.when(drawn),
         "resolved": n.when(resolved)}
    return {"submission": s, "challengePanel": cpid, "challengeK": kc, "reversedBy": by,
            "wrongPassToReversal_s": t["resolved"] - t["counted"],
            "wrongPassToChallenge_s": t["first"] - t["counted"],
            "lapsedChallenges": len(n.evs(c.panels, "ChallengeLapsed(uint256,uint256)", s)),
            "lapsedUntilRefiled_s": t["filed"] - t["first"],
            "challengeWaitedForAPanel_s": t["drawn"] - t["filed"],
            "panelDrawnToReversal_s": t["resolved"] - t["drawn"],
            "reversalToSettlement_s": (n.when(settled[-1]) - t["resolved"]) if settled else None}


def say_heal(what: str, h: dict) -> None:
    print(f"time to heal ({what}): {hours(h['wrongPassToReversal_s'])} of chain time from the wrong pass to its "
          f"reversal\n  = {hours(h['wrongPassToChallenge_s'])} until a watcher challenged it"
          + (f"\n  + {hours(h['lapsedUntilRefiled_s'])} until it filed again after {h['lapsedChallenges']} lapse(s) at "
             f"CHALLENGE_DEADLINE (no panel could be drawn yet, #251 L25)" if h["lapsedChallenges"] else "")
          + f"\n  + {hours(h['challengeWaitedForAPanel_s'])} the challenge waited for a panel of {h['challengeK']} "
          f"to exist (validators qualifying)"
          f"\n  + {hours(h['panelDrawnToReversal_s'])} from the panel's draw to its verdict (the seal window, then the "
          f"reveals)", flush=True)


def run(rpc: Rpc, record: dict, work: Path, heal: bool, verbose: bool, report: str | None) -> int:
    started = time.time()
    n = Net(rpc, record, work, verbose)
    c, P = n.chain, n.panel
    out: dict = {"chainId": c.chain_id(), "race": c.race, "besideV2": record.get("besideV2"),
                 "windowsKind": record.get("windowsKind"), "panelRules": record.get("panelRules")}
    v2_code = rpc.call("eth_getCode", [record["besideV2"], "latest"]) if int(record.get("besideV2", "0x0"), 16) else "0x"
    check(len(v2_code) > 2 and record.get("testOnly") is True and "simulated" in record.get("proofTypes", []),
          f"v3 is deployed beside v2 (RaceV2 at {record.get('besideV2')}) on chain {c.chain_id()}; its record is "
          f"marked for testing only, with the simulated proof type")

    # ---------- 1. the genesis validator alone ----------
    print("\n== 1. one genesis validator, k = 1 ==", flush=True)
    genesis = n.make_node("genesis", FAMILIES[0], keeper=True)
    rpc.call("anvil_setBalance", [genesis.address, ETH_100])
    n.nodes["genesis"] = genesis
    g = c.validator(genesis.address)
    check(genesis.address == crypto.checksum(record["genesis"]) and c.is_active(genesis.address) and g["genesis"]
          and g["level"] == v3.LEVEL_A and rpc.view(c.registry, "activeCount()", ["uint256"])[0] == 1,
          "one genesis validator, active from the start, at level A (the simulated proof type on a devnet)")
    for _ in range(3):
        n.join_next()
    check(all(c.validator(n.nodes[f"v{i}"].address)["state"] == v3.CANDIDATE for i in (1, 2, 3)),
          "v1, v2 and v3 registered as candidates (bonded 100 each, signed by their keys, their own families and hosts)")
    check(all(c.rad_node_of(n.nodes[f"v{i}"].address) == n.rad_node(f"v{i}") for i in (1, 2, 3)),
          "each registration signed its validator's Radicle node key, and the registry holds it (radNodeOf, #251 L11)")
    n.start = max(rpc.block() - 20, 0)

    issue1, s1 = n.register_issue()
    issue2, s2 = n.register_issue()
    issue_w, s_w = n.register_issue(claim=False)  # nobody claims it on the host: an honest check fails it
    genesis.lies.add(s_w)
    n.drive(lambda: all(c.verdict(x)["status"] == v3.HELD and c.submission(x)["paid"] and n.quiet(x)
                        for x in (s1, s2, s_w)), "the first three checks counted, held, their shadows settled")
    v = c.verdict(s1)
    check(v["k"] == 1 and v["pass"] and v["heldAtCount"] and P.drawn(s1) == [genesis.address],
          f"registration {issue1}'s check (submission {s1}) was judged by the genesis validator alone, k = 1, and its "
          f"verdict is held")
    shadows = P.shadows(s1)
    check(len(shadows) == 2 and all(c.validator(k)["state"] == v3.CANDIDATE for k in shadows),
          f"two candidates were its shadows ({n.named(shadows)})")
    try:
        n.anyone.send(c.panels, "startWindow(uint256)", s1)
        raise AssertionError("a k = 1 verdict's window started with no validator to challenge it")
    except Reverted as e:
        check(True, f"its window can't start yet: nobody could judge its challenge (startWindow: {e.reason})")
    w = c.verdict(s_w)
    sp = w["shadowPid"]
    votes = [c.seat(sp, i)["vote"] for i in range(c.panel(sp)["k"])]
    check(w["pass"] and w["k"] == 1 and votes == [False, False],
          f"a wrong verdict passed: registration {issue_w} is claimed by nobody, the lying genesis judge passed it "
          f"alone (submission {s_w}), and both honest shadows sealed a fail")
    watcher = n.nodes["v3"]
    before = c.balance(watcher.address)
    evidence = watcher.challenge(s_w)
    held_stake = before - c.balance(watcher.address)
    check(evidence is not None and c.verdict(s_w)["challengeOpen"],
          f"a watcher (v3, still a candidate) re-ran the check, disagreed and challenged it, staking "
          f"{held_stake / COIN:,.2f}")
    n.watch(watcher, s_w)  # L25: re-filed if it lapses before a panel exists
    n.drive(lambda: c.verdict(s_w)["challengeEpoch"] != 0, "the challenge's draw tried")
    check(c.verdict(s_w)["challengePid"] == 0,
          "its challenge waits: no fresh panel of 3 exists while the genesis validator is the only one active")

    # ---------- 2. qualification: k reaches 3 ----------
    print("\n== 2. candidates qualify by their shadow verdicts until k reaches 3 (scenario 6) ==", flush=True)
    made = n.grow(["v1", "v2", "v3"], 12, "v1, v2 and v3 qualify")
    acts = n.evs(c.registry, "Activated(address)")
    check(len(n.active()) == 4 and len(acts) == 3,
          f"v1, v2 and v3 qualified with no vote and no co-signature, after {made} more registration checks "
          f"({hours(n.when(acts[-1]) - n.t0)} of chain time after the deployment)")
    waited = {int(x["topics"][1], 16) for x in n.evs(c.panels, "Waited(uint256,uint256,uint8)")}
    check(len(waited) > 0, f"{len(waited)} submissions waited for a panel meanwhile (a validator holds at most "
                           f"{rpc.view(c.panels, 'K1_PENDING_MAX()', ['uint256'])[0]} k = 1 verdicts) and were "
                           f"shadowed by the candidates")
    out["qualification"] = {"checks": made + 3, "chainSecondsToThreeActive": n.when(acts[-1]) - n.t0}
    n.drive(lambda: c.verdict(s1)["auditsDrawn"] > 0 or c.verdict(s1)["status"] != v3.HELD, "an audit drawn", strict=False,
            idle_max=6, poke=True)
    if c.verdict(s1)["status"] == v3.HELD and len(n.outside(s1)) < 3:
        try:
            n.anyone.send(c.panels, "startWindow(uint256)", s1)
            raise AssertionError("a k = 1 verdict's window started without three validators to judge its challenge")
        except Reverted as e:
            check(True, f"with three more validators active, the first k = 1 verdict is still held (startWindow: "
                        f"{e.reason}): its auditors are drawn from them and sit out of its challenge, so only "
                        f"{len(n.outside(s1))} could judge one")
        out["holdNeedsMoreThanThree"] = True
    issue3, s3 = n.register_issue()
    issue3h, s3h = n.register_issue() if heal else (0, 0)
    mine = [s3] + ([s3h] if heal else [])
    n.drive(lambda: all(c.verdict(x)["status"] in (v3.WINDOW, v3.FINAL) for x in mine), "a check counted by a panel of 3")
    check(c.verdict(s3)["k"] == 3 and len(P.drawn(s3)) == 3 and P.decides(s3) == 2,
          f"k = 3: a new registration check (submission {s3}) was judged by a counted panel of 3 "
          f"({n.named(P.drawn(s3))}); 2 agreeing decide")
    n.drive(lambda: all(c.verdict(x)["status"] == v3.FINAL for x in mine), "the panel of 3's verdict final")
    window3 = rpc.view(c.panels, "windowOf(uint256,uint8)", ["uint256"], 3, c.verdict(s3)["level"])[0]
    check(c.verdict(s3)["pass"], f"it became final after its window of {hours(window3)}, with no hold: a k = 1 verdict "
                                 f"is held, a k = 3 verdict isn't")

    # ---------- 2b. the minimum of active solvers (#251 task 3.3, contract batch 3) ----------
    print("\n== 2b. three solvers made active by unfunded fixes, then pledges open; reputation before large claims "
          "==", flush=True)
    book = crypto.checksum(rpc.view(c.race, "solverBook()", ["address"])[0])
    healer = n.account("healer")  # the heal step's solver (step 8): its own reputation
    third = n.account("third solver")
    regs = [n.register_issue() for _ in range(5)]
    n.drive(lambda: all(c.verdict(x)["status"] == v3.FINAL for _, x in regs), "five registrations final")
    unfunded = [(w, n.open_bounty(i), i) for w, (i, _) in zip((n.solver, healer, third), regs[:3])]
    try:
        n.funder.send(c.race, "pledge(uint256,uint256)", unfunded[0][1], 10 * COIN)
        raise AssertionError("a pledge landed before three solvers were active")
    except Reverted as e:
        check(True, f"no active solver yet: a pledge is refused ({e.reason}), and the issues are raced unfunded")
    for k, (w, b, i) in enumerate(unfunded):
        n.merged_fix(w, b, i, f"an unfunded fix {k + 1}")
    actives = rpc.view(book, "activeCount()", ["uint256"])[0]
    check(actives == 3, f"three solvers' unfunded fixes were merged: {actives} active solvers, pledges open "
                        f"(ACTIVE_SOLVERS_MIN 3, ACTIVE_WINDOW {rpc.view(book, 'ACTIVE_WINDOW()', ['uint256'])[0] / WEEK:g} "
                        f"weeks)")
    for w, (i, _) in zip((n.solver, healer), regs[3:]):  # reputation: a funded fix each, about $44 (D29's cap is $50)
        b = n.open_bounty(i)
        n.funder.send(c.race, "pledge(uint256,uint256)", b, 105 * COIN)
        n.merged_fix(w, b, i, f"a funded fix by {w.role}")
    reps = [rpc.view(book, "reputation(address)", ["uint256"], w.address)[0] for w in (n.solver, healer)]
    check(all(r > 30 * COIN for r in reps),
          f"each of the two solvers has a merged funded fix: reputation {', '.join(f'{r / COIN:,.2f}' for r in reps)}, "
          f"so its cap is above the $50 a new identity may claim")
    out["activeSolvers"] = {"active": actives, "reputations": reps}

    # ---------- 3. a bounty above k = 1's limit ----------
    print("\n== 3. a bounty above k = 1's limit waits, is shadowed, and is drawn when k = 3 is reached ==", flush=True)
    b1 = n.open_bounty(issue3)
    b2 = n.open_bounty(issue3h) if heal else 0
    for _ in range(2):
        n.join_next()
    n.funder.send(c.race, "pledge(uint256,uint256)", b1, 200 * COIN)
    s_b, opening = n.submit_fix(b1, issue3, "a good fix", good=True)
    judged = c.verdict(s_b)["bounty"]
    limit1 = rpc.view(c.panels, "limitOf(uint256,uint8)", ["uint256"], 1, v3.LEVEL_A)[0]
    need = n.bond_for(judged)
    check(judged > limit1 and n.eligible(judged) == 1,
          f"bounty {b1} opened from the final registration, was funded, and a fix was sealed at {judged / COIN:,.2f}: "
          f"above k = 1's limit ({limit1 / COIN:,.2f}), and only the genesis validator's bond covers it (a bond of "
          f"{need / COIN:,.2f} is needed)")
    s_h = 0  # the heal step's bad fix (step 8): submitted once the network can judge its challenge (#251 L25)
    if heal:  # funded now, while pledges are open (L6's active solvers lapse with time): about $85 at step 8's price
        n.funder.send(c.race, "pledge(uint256,uint256)", b2, 100 * COIN)
    n.drive(lambda: c.verdict(s_b)["status"] == v3.WAITING and n.quiet(s_b), "the fix waits, its shadows settled")
    shadows = P.shadows(s_b)
    sp = c.verdict(s_b)["shadowPid"]
    check(P.waiting(s_b) and P.drawn(s_b) == [] and len(shadows) == 2
          and all(c.validator(k)["state"] == v3.CANDIDATE for k in shadows)
          and all(c.seat(sp, i)["revealed"] for i in range(2)),
          f"it waits with no panel, and candidates shadowed it meanwhile ({n.named(shadows)} sealed and revealed)")
    waited_at = n.when(n.evs(c.panels, "Waited(uint256,uint256,uint8)", s_b)[0])
    for name in ("v1", "v2"):
        n.top_up(name, need)
    topped_at = c.now()
    check(n.eligible(judged) == 3, f"v1 and v2 topped their bonds up to {need / COIN:,.2f}: three validators are now "
                                   f"eligible for it, so k = 3 is reached")
    n.drive(lambda: c.verdict(s_b)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s_b)["paid"],
            "the waiting fix drawn and judged")
    pid, k, drawn_log = panels_of(n, s_b, v3.COUNTED)[0]
    check(k == 3 and set(P.drawn(s_b)) == {genesis.address, n.nodes["v1"].address, n.nodes["v2"].address}
          and c.verdict(s_b)["pass"],
          f"it was drawn with k = 3 ({n.named(P.drawn(s_b))}) {(n.when(drawn_log) - topped_at) / 60:,.0f} minutes "
          f"after the top-ups (it had waited {hours(topped_at - waited_at)} for them), and passed")
    check(n.bounty_state(b1) == WON and c.bounty(b1)["winner"] == s_b, f"bounty {b1} is won by submission {s_b}")
    # A counted verdict is audited at random (AUDIT_RATE_BPS: one k = 3 verdict in ten) by a validator outside its
    # panel and bonded for its bounty. With only its three judges bonded nobody could take that audit, and L19 released
    # the good fix's verdict (refunded, never merged) after MAX_REDRAWS rounds of STUCK_GRACE: step 9 failed whenever
    # its audit fell due. A fourth validator bonded after the draw is the auditor it may need.
    n.top_up("v3", need)
    v_b = c.verdict(s_b)
    check(n.eligible(judged) == 4,
          f"v3 topped its bond up too, after the draw: an auditor outside the panel is eligible for it if its random "
          f"audit falls due (audits due: {v_b['auditsDue'] if v_b['auditDecided'] else 'not decided yet'})")
    genesis_head = c.head()
    n.solver.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b1, *opening)
    claimed_at = c.now()
    check(n.bounty_state(b1) == CLAIMED and c.head() == genesis_head,
          "the solver claimed it (the commitment opened): its award started, and the head didn't move (#251 L9: it "
          "moves at the verdict's finality)")
    out["waitingBounty"] = {"submission": s_b, "judgedAt": judged, "k1Limit": limit1, "k": k,
                            "waitedForTopUpsSeconds": topped_at - waited_at,
                            "topUpsToDrawSeconds": n.when(drawn_log) - topped_at}

    # ---------- 4. a silent judge is replaced ----------
    print("\n== 4. a silent validator is replaced (scenario 4) ==", flush=True)
    _, s4 = n.register_issue()
    n.drive(lambda: c.verdict(s4)["status"] == v3.JUDGING, "a check drawn", only=("genesis",))  # nobody else seals yet
    first = P.drawn(s4)
    floor = c.bond_floor()
    others = [k for k in first if k != genesis.address]
    silent_key = next((k for k in others if c.validator(k)["bond"] == floor), others[0])  # a floor bond, if one is drawn
    slashed = c.validator(silent_key)["slashed"]
    first_pid = P.pid(s4)
    n.nodes[n.name(silent_key)].mute.add(first_pid)
    n.drive(lambda: c.verdict(s4)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s4)["paid"],
            "the check decided without the silent validator", explain=(s4,))
    missed = n.evs(c.panels, "Missed(uint256,address,bool)", first_pid, silent_key)
    after = P.drawn(s4)
    if P.pid(s4) == first_pid:
        check(len(missed) == 1 and silent_key not in after and len(after) == P.size(s4) == 3,
              f"{n.name(silent_key)} stayed silent on its seat: at the seal deadline it was replaced from the same "
              f"sample ({n.named(first)} -> {n.named(after)}); k stayed 3")
    else:
        # The seat's replacement comes from the same sample (PanelsDraw.tries per seat); when none of its tries finds
        # a validator free to sit (all drawn already, full or ineligible), the panel stays short and, STUCK_GRACE
        # after its reveal deadline, the round is released and redrawn from a fresh seed (#251 L19). The silence
        # still cost the seat; the redrawn panel, where it isn't muted, decides. Rare (one release-candidate run in
        # thirteen, rc1 run 3): the check accepts either path and says which it saw.
        released = n.evs(c.panels, "Released(uint256,uint256,uint256)", s4, first_pid)
        print(n.history(s4), flush=True)
        check(len(missed) == 1 and len(released) == 1 and len(after) == P.size(s4) == 3,
              f"{n.name(silent_key)} stayed silent on its seat: at the seal deadline its seat was emptied, no "
              f"validator in its sample could take it, and the round was released and redrawn (L19, panel "
              f"{first_pid} -> {P.pid(s4)}: {n.named(first)} -> {n.named(after)}); k stayed 3")
    check(c.validator(silent_key)["slashed"] - slashed >= rpc.view(c.registry, "SILENCE_SLASH()", ["uint256"])[0],
          f"its silence cost it {(c.validator(silent_key)['slashed'] - slashed) / COIN:,.2f} of its bond")
    check(P.replaces_silent() and n.seats_reported(c.verdict(s4)["pid"]) == P.reports(s4, silent=1) == 3,
          "the panel still decided with 3 verdicts and 3 usage reports")
    below = c.validator(silent_key)["bond"] < floor
    out["silent"] = {"validator": n.name(silent_key), "slashed": c.validator(silent_key)["slashed"] - slashed,
                     "belowFloor": below, "redrawn": P.pid(s4) != first_pid}
    if below:
        # #251, L5: visibly inactive, not counted, and nothing waits for it; it isn't topped up here (its operator
        # may top up or leave; section 8 tops every validator up for its bounty)
        went = n.evs(c.registry, "WentBelowFloor(address,uint256)", silent_key)
        active_now = rpc.view(c.registry, "activeCount()", ["uint256"])[0]
        check(c.validator(silent_key)["state"] == v3.BELOW_FLOOR and not c.is_active(silent_key)
              and not n.drawable(silent_key) and len(went) == 1 and active_now == len(n.active()),
              f"its bond is now under the floor ({c.validator(silent_key)['bond'] / COIN:,.2f} of {floor / COIN:,.2f}): "
              f"it is BelowFloor, said so by an event, not counted active ({active_now} are) and drawn for nothing; "
              f"no manual top-up")

    # ---------- 5. k reaches 5 ----------
    print("\n== 5. two more candidates qualify until k reaches 5 ==", flush=True)
    growing = ["v4", "v5"] + ([n.join_next()] if below else [])  # one more in place of the validator below the floor
    made = n.grow(growing, 12, f"{', '.join(growing)} qualify")
    check(len(n.active()) == 6, f"{', '.join(growing)} qualified after {made} more checks: six validators are active")
    _, s5 = n.register_issue()
    n.drive(lambda: c.verdict(s5)["status"] in (v3.WINDOW, v3.FINAL), "a check counted by a panel of 5")
    judges = P.drawn(s5)
    tees = [c.validator(k)["teeType"] for k in judges]
    check(c.verdict(s5)["k"] == 5 and len(set(judges)) == 5 and P.decides(s5) == 3
          and max(tees.count(t) for t in tees) <= 2,
          f"k = 5: a new check was judged by a counted panel of 5 ({n.named(judges)}), at most 2 of one TEE type; "
          f"3 agreeing decide")
    out["k5"] = {"submission": s5, "active": 6}

    # ---------- 6. the k = 1 hold ----------
    print("\n== 6. the k = 1 verdict: held, audited twice, final after its window ==", flush=True)
    for x in (s1, s_w):  # every auditor seated sits out of the verdict's challenge: it may take more validators
        n.drive(lambda: c.verdict(x)["auditDecided"] and c.verdict(x)["auditsDrawn"] == c.verdict(x)["auditsDue"],
                "the k = 1 verdict's audits drawn", poke=True)
        # held, challenged, or (the wrong pass) still passing in its window: its challenge needs three outside
        while len(n.outside(x)) < 3 and (c.verdict(x)["status"] == v3.HELD or c.verdict(x)["challengeOpen"] or (
                x == s_w and c.verdict(x)["pass"] and c.verdict(x)["status"] == v3.WINDOW)):
            extra = n.join_next()
            made = n.grow([extra], 12, f"{extra} qualifies")
            print(f"    ({extra} registered and qualified after {made} more checks: submission {x} had only "
                  f"{len(n.outside(x)) - 1} validators left who could judge its challenge)", flush=True)
    n.drive(lambda: c.verdict(s1)["status"] in (v3.WINDOW, v3.FINAL), "the held verdict's window started")
    v = c.verdict(s1)
    started_log = n.evs(c.panels, "WindowStarted(uint256,uint256)", s1)[0]
    held_log = n.evs(c.panels, "Held(uint256)", s1)[0]
    audits = n.evs(c.panels, "Audited(uint256,uint256,address,bool)", s1)
    auditors = [crypto.checksum("0x" + a["topics"][3][-40:]) for a in audits]
    agrees = [abi.decode(["bool"], abi.hexdata(a["data"]))[0] for a in audits]
    check(len(audits) == v["auditsDue"] >= 2 and len(set(auditors)) == len(audits) and genesis.address not in auditors
          and all(agrees),
          f"it was audited {'twice' if len(audits) == 2 else f'{len(audits)} times (2, and a random one)'}, by "
          f"validators outside its panel ({n.named(auditors)}); {'both' if len(audits) == 2 else 'all'} agree")
    start_block = int(started_log["blockNumber"], 16)
    in_window = sum(1 for a in audits if int(a["blockNumber"], 16) >= start_block)
    print(f"    ({len(audits) - in_window} of its audits were judged while it was held, {in_window} after its window "
          f"started: each is drawn as soon as an auditor is eligible, whichever comes first)")
    active_then = [crypto.checksum("0x" + a["topics"][1][-40:]) for a in n.evs(c.registry, "Activated(address)")
                   if int(a["blockNumber"], 16) <= start_block]
    sat_out = {k for pid, _, log in panels_of(n, s1, v3.AUDIT) if int(log["blockNumber"], 16) <= start_block
               for k in c.judges(pid) if k}
    free = [k for k in active_then if k not in sat_out]
    why = (f"the auditors drawn before that ({n.named(sat_out)}) sit out of its challenge, so three more validators "
           f"weren't enough" if sat_out else "none of its auditors had been drawn yet, so three more were enough")
    check(len(free) >= 3,
          f"its window started only once three validators who could judge its challenge were active "
          f"({len(active_then)} beside the genesis one: {why}). Held for "
          f"{hours(n.when(started_log) - n.when(held_log))} of chain time")
    window = rpc.view(c.panels, "windowOf(uint256,uint8)", ["uint256"], 1, v["level"])[0]
    check(v["finalAt"] - n.when(started_log) == window, f"its window is CHALLENGE_WINDOW[1, level A]: {hours(window)}")
    if c.now() < v["finalAt"]:
        try:
            n.anyone.send(c.panels, "finalize(uint256)", s1)
            raise AssertionError("a verdict became final before its window passed")
        except Reverted as e:
            check(True, f"it can't be final before its window has passed (finalize: {e.reason})")
    n.drive(lambda: c.verdict(s1)["status"] == v3.FINAL, "the k = 1 verdict final", poke=True)
    final_log = n.evs(c.panels, "Final(uint256,bool)", s1)[0]
    check(n.when(final_log) >= v["finalAt"] and all(n.when(a) <= n.when(final_log) for a in audits),
          f"then it became final, after its audits and its window: {hours(n.when(final_log) - n.when(held_log))} "
          f"after it was counted")
    out["k1Hold"] = {"submission": s1, "heldSeconds": n.when(started_log) - n.when(held_log), "audits": len(audits),
                     "validatorsBesideGenesisAtRelease": len(active_then), "auditorsDrawnBeforeRelease": len(sat_out),
                     "auditsJudgedWhileHeld": len(audits) - in_window, "windowSeconds": window,
                     "countedToFinalSeconds": n.when(final_log) - n.when(held_log)}

    # ---------- 7. the challenged k = 1 verdict is reversed ----------
    print("\n== 7. the challenged k = 1 verdict is reversed by a fresh panel of 3 ==", flush=True)
    def judged_w() -> bool:  # the watcher's challenge settled, or an auditor's challenge reversed it (no race filing)
        v = c.verdict(s_w)
        if v["challengeOpen"]:
            return False
        settled_w = n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_w)
        if v["pass"]:
            return settled_w != []
        # filed at the race (its ChallengeFiled in the same block), or opened by an auditor's mismatch; the watcher
        # may be that auditor, so the opener's address doesn't tell
        opened = int(n.evs(c.panels, "ChallengeOpened(uint256,address,bytes32)", s_w)[-1]["blockNumber"], 16)
        filed = any(int(x["blockNumber"], 16) == opened for x in n.evs(c.race, "ChallengeFiled(uint256,address)", s_w))
        return not filed or settled_w != []  # a filed one: its settlement at the race too
    n.drive(judged_w, "the k = 1 verdict's challenge judged and settled", poke=True, explain=(s_w,))
    h = heal_times(n, s_w)
    cpid = h["challengePanel"]
    resolved = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s_w)[-1]
    upheld, now_pass, false_receipt = abi.decode(["bool", "bool", "bool"], abi.hexdata(resolved["data"]))
    cjudges = c.judges(cpid)
    audited = [crypto.checksum("0x" + a["topics"][3][-40:])
               for a in n.evs(c.panels, "Audited(uint256,uint256,address,bool)", s_w)]
    check(h["challengeK"] == 3 and len(set(cjudges)) == 3 and not ({genesis.address, *audited} & set(cjudges)),
          f"its challenge was drawn once a fresh panel of 3 existed ({n.named(cjudges)}): without its judge (genesis) "
          f"or its auditors ({n.named(audited)})")
    check(upheld and not now_pass and not c.verdict(s_w)["pass"],
          f"the panel reversed the verdict: pass -> fail (a false receipt found: {'yes' if false_receipt else 'no'}; "
          f"the judges disagreed on the outcome)")
    settled = n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_w)
    if h["reversedBy"] == "filed":
        check(abi.decode(["bool"], abi.hexdata(settled[-1]["data"]))[0] and c.owed(watcher.address) >= held_stake,
              f"the challenge was upheld: the watcher's stake and cover ({held_stake / COIN:,.2f}) are credited back to "
              f"it")
    else:
        check(not settled and c.owed(watcher.address) >= held_stake,
              f"the reversing challenge was an auditor's (its mismatch opened it; the race holds no stake for it): the "
              f"watcher's own challenge had lapsed, and its stake and cover ({held_stake / COIN:,.2f}) came back")
    n.drive(lambda: c.verdict(s_w)["status"] == v3.FINAL, "the reversed verdict final", poke=True)
    n.anyone.send(c.race, "openBounty(uint256)", issue_w)
    check(c.issue(issue_w)["state"] == FORFEITED and c.issue(issue_w)["bounty"] == 0,
          f"registration {issue_w} ended forfeited: no bounty was ever opened on the wrong verdict")
    say_heal("a wrong k = 1 verdict of the lone genesis validator", h)
    vw = c.verdict(s_w)
    print(f"  ({vw['auditsDone']} audits of it (K1_AUDITS 2, and a random one if due), each auditor sitting out of its "
          f"challenge; {vw['lapses']} lapse(s); reversed by {'the watcher' if h['reversedBy'] == 'filed' else 'an auditor'}"
          f"'s challenge)", flush=True)
    h.update(audits=vw["auditsDone"], lapses=vw["lapses"])
    scores = rpc.view(c.panels, "scores()", ["address"])[0]
    barred = rpc.view(scores, "isBarred(bytes32)", ["bool"], v3.name_id(FAMILIES[0]))[0]
    lost = c.validator(genesis.address)["slashed"]
    print(f"  the lying judge lost {lost / COIN:,.2f} of its bond (no receipt was false: a disagreement isn't a fault); "
          f"its family is {'now barred from counted panels by its score' if barred else 'not barred by its score'}",
          flush=True)
    h.update(liarSlashed=lost, liarFamilyBarred=barred)
    out["healK1"] = h

    # ---------- 8. time to heal for a paid fix ----------
    if heal:
        print("\n== 8. time to heal: a wrongly passed fix, reversed by a fresh panel of 5 ==", flush=True)
        # #251 L25: a challenge is judged by CHALLENGE_DEADLINE or lapses, the wrong pass standing; before batch 4 this
        # fix's challenge waited, its window frozen, while validators qualified for a fresh panel of 5. So the network
        # that can draw that panel is grown first: every validator qualified, only four bonded for the bounty (a panel
        # of 3 from them, of which three lie); the others top up once it's claimed and challenged.
        while n.next_index <= 8:
            extra = n.join_next()
            made = n.grow([extra], 12, f"{extra} qualifies")
            print(f"    ({extra} registered and qualified after {made} more checks)", flush=True)
        for name in ("v1", "v2", "v3"):  # bonded for the bounty, as in step 3 (a silence may have cost one 5.00)
            n.top_up(name, n.bond_for(85 * COIN))
        # on the good fix, as a solver building on a pending fix would: the good fix's merge at its finality moves the
        # one head there (#251 L9); this one is reversed before its own finality and never merged
        s_h, opening_h = n.submit_fix(b2, issue3h, "a bad fix", good=False, base=v2.commit_word(n.fix_sha("a good fix")),
                                      solver=healer)
        need_h = n.bond_for(c.verdict(s_h)["bounty"])
        bonded = [name for name in n.nodes if c.validator(n.nodes[name].address)["bond"] >= need_h]
        for name in bonded:
            if name != "genesis":
                n.nodes[name].lies.add(s_h)  # every bonded validator but the genesis one lies on it
        check(n.eligible(c.verdict(s_h)["bounty"]) == len(bonded) == 4,
              f"{len(n.active())} validators are active, four of them ({', '.join(bonded)}) bonded for the bounty "
              f"({need_h / COIN:,.2f}): a panel of 3, at least two of them lying")
        n.drive(lambda: c.verdict(s_h)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s_h)["paid"],
                "the bad fix drawn and judged", poke=True)
        check(c.verdict(s_h)["pass"] and c.verdict(s_h)["k"] == 3 and n.bounty_state(b2) == WON,
              f"a wrong verdict passed: a bad fix (its tests fail) was passed by a panel of 3 ({n.named(P.drawn(s_h))}) "
              f"with lying judges (submission {s_h}), and won bounty {b2}")
        n.solver.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b2, *opening_h)
        for name in list(n.nodes):
            n.top_up(name, need_h)
        n.fund(genesis.address, 1_000)
        n.watch(genesis, s_h)  # L25: re-filed if it lapses before a panel exists
        check(genesis.challenge(s_h) is not None and c.verdict(s_h)["challengeOpen"] and n.bounty_state(b2) == CLAIMED,
              "its solver claimed it; the others topped up for the bounty, and an honest validator (genesis) re-ran "
              "the check and challenged it inside its window")
        n.drive(lambda: not c.verdict(s_h)["challengeOpen"]
                and n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_h) != [],
                "the fix's challenge judged and settled", poke=True)
        hh = heal_times(n, s_h)
        resolved = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s_h)[-1]
        upheld, now_pass, false_receipt = abi.decode(["bool", "bool", "bool"], abi.hexdata(resolved["data"]))
        cjudges = c.judges(hh["challengePanel"])
        check(hh["challengeK"] == 5 and not (set(P.drawn(s_h)) & set(cjudges)) and upheld and not now_pass,
              f"a fresh panel of 5 ({n.named(cjudges)}), none of the three original judges, reversed it: pass -> fail")
        clawed = n.evs(c.race, "ClawedBack(uint256,uint256,uint256)", b2)
        earned = abi.decode(["uint256"], abi.hexdata(clawed[-1]["data"]))[0] if clawed else None
        check(earned == 0 and n.bounty_state(b2) == OPEN and c.submission(s_h)["outcome"] == FAIL,
              f"the award was clawed back with nothing earned (no instalment starts before finality), and bounty {b2} "
              f"is open again")
        say_heal("a bad fix passed by a panel of 3 with lying judges", hh)
        hh["falseReceiptFound"] = false_receipt
        print(f"  no receipt was found false ({'yes' if false_receipt else 'no'}): the lying judges keep their bonds, "
              f"and the solver's only loss is the award it never received", flush=True)
        out["healFix"] = hh

    # ---------- 9. the head moves at finality (#251 L9) ----------
    print("\n== 9. the head moves at the winning verdict's finality (merge), never to a reversed fix ==", flush=True)
    n.drive(lambda: c.verdict(s_b)["status"] == v3.FINAL and c.award(b1, c.bounty(b1)["epoch"])["merged"],
            "the good fix's verdict final and merged by a keeper", poke=True)
    head = rpc.view(c.heads, "head(bytes32)", [v3.HEAD], c.repo())[0]
    merged_log = n.evs(c.race, "HeadMerged(uint256,uint256,uint256,bytes32)", b1)[0]
    final_b = n.evs(c.panels, "Final(uint256,bool)", s_b)[0]
    check(v3.b32(head[0]) == v2.commit_word(n.fix_sha("a good fix")) and head[4] == s_b and head[3] == b1,
          f"a keeper merged it once its verdict was final: the head is the good fix (bounty {b1}, submission {s_b}); "
          f"the merge came {hours(n.when(merged_log) - n.when(final_b))} after the finality, and "
          f"{hours(n.when(merged_log) - claimed_at)} after the claim (the wait L9 adds before the head moves)")
    out["headAtFinality"] = {"submission": s_b, "claimToMergeSeconds": n.when(merged_log) - claimed_at,
                             "finalToMergeSeconds": n.when(merged_log) - n.when(final_b)}
    if heal:
        check(head[4] != s_h and not c.award(b2, 1)["merged"],
              f"the reversed fix (submission {s_h}) never reached the head: its award was closed unmerged")
        out["headAtFinality"]["reversedNeverMerged"] = True

    # ---------- 10. protected tests (#251 L20, task 4.8) ----------
    print("\n== 10. protected tests: a bad fix that weakens a protected test fails, and so does the same fix without "
          "that edit ==", flush=True)
    out["protectedTests"] = protected_tests(n)

    out["validators"] = {name: {"state": v3.STATES[c.validator(node.address)["state"]],
                                "bond": c.validator(node.address)["bond"], "slashed": c.validator(node.address)["slashed"]}
                         for name, node in n.nodes.items()}
    out["panels"] = c.panel_count()
    out["chainSeconds"] = c.now() - n.t0
    out["wallSeconds"] = round(time.time() - started)
    if report:
        Path(report).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\n{c.panel_count()} panels drawn, {len(n.active())} validators active, {hours(c.now() - n.t0)} of chain "
          f"time in {time.time() - started:,.0f} s; the clock was moved to a deadline {n.jumps} times, and the "
          f"registry's epoch was bumped {n.pokes} times to retry a waiting draw")
    print("not covered here: validators as separate processes over a relay (the relay doesn't speak v3 messages); real "
          "attestation and the zkTLS prover (the simulated proof type only); a model judge (the fake judge only); "
          "ADRs and escalated fixes (RaceV3 can't open them); the test-backed dispute and the appeal (D21, D24: in the "
          "contracts since #251's contract batch 3, not yet in the node, #132 tasks 10.5 and 11.5); short test windows "
          "(the devnet deploys the production ones; minutes are task 3.12's)")
    print("devnet-v3: all checks passed", flush=True)
    return 0


def receipts_of(n: Net, s: int) -> list:
    """The `tests` of every receipt on submission `s`'s counted panel."""
    c = n.chain
    pid = c.verdict(s)["pid"]
    any_node = next(iter(n.nodes.values()))
    return [any_node.receipts3.get(c.seat(pid, i)["receipt"])["receipt"]["tests"] for i in range(c.panel(pid)["k"])]


def protected_tests(n: Net) -> dict:
    """Step 10 (#251 L20): real fixes, real tests in the Docker sandbox, judged by the network's panels."""
    c = n.chain
    if subprocess.run(["docker", "image", "inspect", sandbox.TEST_IMAGE], capture_output=True).returncode:
        raise AssertionError(f"the pinned test image isn't here ({sandbox.TEST_IMAGE}); build it: scripts/test-image.sh")
    repo = ProtectedRepo(n.work / "protected-repo")
    broken = STATS.format(median=GOOD_MEDIAN).replace("sum(xs) / len(xs)", "0")  # median fixed, mean broken
    weakened = repo.fix({"stats.py": broken, "test_issue.py": ISSUE_TEST, "tests/test_stats.py": WEAK_TEST},
                        "a bad fix that also weakens the protected test of mean")
    unedited = repo.fix({"stats.py": broken, "test_issue.py": ISSUE_TEST}, "the same bad fix, the test untouched")
    good = repo.fix({"stats.py": STATS.format(median=GOOD_MEDIAN), "test_issue.py": ISSUE_TEST}, "a good fix")
    n.sources.use(repo.url, [repo.base, weakened, unedited, good], n.log("fetch"))
    # Three registrations, so one that L19 releases (its audit undrawable in this run's draws) doesn't stop the step.
    regs = [n.register_issue() for _ in range(3)]
    final = lambda: [i for i, x in regs if c.verdict(x)["status"] == v3.FINAL]  # noqa: E731
    n.drive(lambda: final() or all(c.verdict(x)["status"] in (v3.FINAL, v3.RELEASED, v3.EXPIRED) for _, x in regs),
            "the scenario's registrations decided", poke=True)
    if not final():
        raise AssertionError(f"none of the scenario's registrations became final: "
                             f"{[v3.STATUS[c.verdict(x)['status']] for _, x in regs]}")
    issue = final()[0]
    bounty = n.open_bounty(issue)
    s_weak = n.submit_real(bounty, issue, "weakened", weakened, repo.base)
    s_plain = n.submit_real(bounty, issue, "unedited", unedited, repo.base)
    def judged(x: int) -> bool:  # counted: in its window, final, or released after counting (L19's audits)
        v = c.verdict(x)
        return v["status"] in (v3.WINDOW, v3.FINAL) or (v["status"] == v3.RELEASED and v["pid"] != 0
                                                         and c.panel(v["pid"])["counted"])
    n.drive(lambda: judged(s_weak) and judged(s_plain), "the two bad fixes judged", poke=True)
    weak, plain = receipts_of(n, s_weak), receipts_of(n, s_plain)
    same_tree = repo.tree(unedited)
    check(not c.verdict(s_weak)["pass"] and all(t["exit_code"] != 0 for t in weak)
          and all(t["protected"] == ["tests"] and t["not_run"] == 1 and t["run_tree"] == same_tree for t in weak)
          and all(len(t["runs"]) == 2 and all(r["exit_code"] != 0 for r in t["runs"]) for t in weak),
          f"the bad fix that weakens the protected test failed (submission {s_weak}, a panel of {len(weak)}): each "
          f"judge ran the base's test twice on a run tree whose hash is the unedited fix's tree ({same_tree[:12]}), "
          f"and its receipt says 1 changed file was protected and not run")
    check(not c.verdict(s_plain)["pass"] and all(t["exit_code"] != 0 and t["not_run"] == 0
                                                 and t["run_tree"] == same_tree for t in plain),
          f"the same bad fix without that edit failed too (submission {s_plain}), on the same run tree")
    alone = sandbox.run_tests(n.work / "src" / weakened, command=checkconfig.command((tuple(SUITE),)),
                              runner=sandbox.docker_runner, timeout_s=240)
    check(alone.passed, "without the overlay, the weakened fix's own tests pass in the same sandbox (both runs exit "
                        "0): the protected path is what failed it")
    s_good = n.submit_real(bounty, issue, "good", good, repo.base)
    n.drive(lambda: judged(s_good), "the good fix judged", poke=True)
    good_tests = receipts_of(n, s_good)
    check(c.verdict(s_good)["pass"] and all(t["exit_code"] == 0 and not t.get("flaky") for t in good_tests),
          f"a good fix passed (submission {s_good}): its acceptance test at the root and the base's protected test "
          f"both ran, twice each")
    return {"weakened": s_weak, "unedited": s_plain, "good": s_good, "runTree": same_tree,
            "judges": len(weak)}


def prepare() -> int:
    """Prints what scripts/devnet.sh deploy-v3 needs of the genesis validator: its key (a throwaway test key from the
    simulator's stand-in) and its attestation hash. Read by the calling script, never shown."""
    genesis = keys_for(simulator(), "genesis")
    quote = genesis.quote(crypto.keccak256(b"genesis"))
    print(f"GENESIS=0x{genesis.account_secret():064x}")
    print(f"ATTESTATION=0x{crypto.keccak256(bytes.fromhex(quote.quote)).hex()}")
    print(f"FAMILIES={','.join(FAMILIES)}")
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "run"])
    ap.add_argument("--rpc")
    ap.add_argument("--record")
    ap.add_argument("--work")
    ap.add_argument("--heal", action="store_true", help="also step 8: time to heal for a wrongly passed fix")
    ap.add_argument("--verbose", action="store_true", help="print every node's log (it's in <work>/nodes.log anyway)")
    ap.add_argument("--report", help="write the run's numbers here, as JSON")
    ap.add_argument("--profile", help="write a cProfile of the run here (for working on this script)")
    a = ap.parse_args(argv[1:])
    if a.command == "prepare":
        return prepare()
    args = (Rpc(a.rpc, retries=2), json.loads(Path(a.record).read_text()), Path(a.work), a.heal, a.verbose, a.report)
    if a.profile:
        import cProfile

        prof = cProfile.Profile()
        try:
            return prof.runcall(run, *args)
        finally:
            prof.dump_stats(a.profile)
    return run(*args)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
