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

Time is the chain's. Panels' windows are constants in hours and days (SEAL_WINDOW 2 h, REVEAL_WINDOW 1 h, a k = 1
window of 168 h): there are no short test windows in the contracts, so this run moves the chain's clock
(evm_increaseTime, a devnet affordance) to the next deadline whenever no node has anything to do. Every duration it
prints is chain time under the real windows. The devnet's 2-second blocks are switched to mining on demand for the
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
   validators top up their bonds; then it is drawn with k = 3, judged, won and claimed;
4. a silent judge (scenario 4): a drawn validator never answers on its seat; it is slashed for silence and replaced
   from the same sample, and the panel still decides with k verdicts and k usage reports;
5. k reaches 5: two more candidates qualify, and a check is judged by a counted panel of 5;
6. the k = 1 hold (first bullet): the held verdict was audited twice while held, its window started only once three
   validators who could judge its challenge were active (its auditors sit out, so five beside the genesis one), and
   it became final after its window, not before;
7. the challenge (third bullet): the wrong k = 1 verdict's challenge is drawn (a fresh panel of 3, without its judge
   or its auditors), it reverses the verdict, the challenger's stake returns, and the registration ends forfeited.
   Time to heal, k = 1: the chain time from the wrong pass to its reversal;
8. with --heal, time to heal for a paid fix: a bad fix is passed 2 to 1 by a panel of 3 with two lying judges, wins and
   is claimed; the outvoted judge challenges it; more validators qualify until a fresh panel of 5 can be drawn; the
   panel reverses it, the award is clawed back with nothing earned, and the bounty reopens.

What it doesn't cover is listed at the end of the run (and in reports/devnet-v3-local.md)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from bot import logic  # noqa: E402
from e2e_node_v3 import COIN, ETH_100, Host, Run, check, keys_for, simulator  # noqa: E402
from oracle import abi, crypto, node_v3, v2, v3  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.node_v3 import NodeV3  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from oracle.rpc import Reverted, Rpc, Wallet  # noqa: E402
from oracle.transport import OnchainExchange  # noqa: E402
from panel import PanelV3  # noqa: E402

TEES = ("intel-tdx", "amd-sev-snp", "aws-nitro-enclaves")  # spread, so the TEE-type cap lets k = 5 and 7 fill
FAMILIES = ["fake"] + [f"fake-{i}" for i in range(1, 9)]  # one family per validator: the family cap allows 1 at k = 3
HOUR, DAY = 3600, 86400
REPORT_WINDOW = 86400
WON, MERGED, OPEN = 2, 3, 1  # RaceV3Base.State
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

    def add_pull(self, title: str, body: str, sha: str) -> int:
        self._pulls.append({"number": 500 + len(self._pulls), "title": title, "body": body, "head_sha": sha,
                            "state": "open"})
        return self._pulls[-1]["number"]


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

    def _take(self, pid: int) -> bool:
        if pid in self.mute:
            self.finished.add(pid)
            return False
        return super()._take(pid)

    def _judge(self, s: int, p: dict, late: bool = False):
        self.judge.lie = s in self.lies
        try:
            return super()._judge(s, p, late)
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
        self.funder = self.account("funder")
        self.solver = self.account("solver")
        self.anyone = self.account("anyone")
        self.fund(self.reporter.address, 1_000_000)
        self.minter.send(self.chain.coin(), "approve(address,uint256)", self.chain.registry, 2**255)
        self.minter.send(self.chain.coin(), "mint(address,uint256)", self.minter.address, 1_000 * COIN)
        self.t0 = self.chain.now()
        self.open_panels: set = set()
        self.seen_panels = 0
        self.jumps = 0
        self.pokes = 0
        self.names: dict = {}
        self.next_index = 1

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
        return Node(self.chain, keys, FakeJudge(family=family), self.host, "demo/median", self.work / "src",
                    OnchainExchange(self.chain, keys, wallet=wallet), Store(self.work / "receipts"),
                    runner=self.tests, log=self.log(name + tag), wallet=wallet,
                    rounds=Rounds(self.work / "rounds", self.chain.chain_id(), self.chain.race, me + tag),
                    keeper=keeper, costs={"vcpu_second": 12_000_000, "gb_second": 1_300_000} if keeper else None,
                    seal_margin=3 * HOUR)  # a check that can't be run is sealed at once as not passed

    def tests(self, argv: list) -> tuple:
        """Stands in for the Docker sandbox: a bad fix's tests fail. No fix's code exists, so none is run."""
        text = " ".join(str(a) for a in argv)
        return (1, "", "1 failed") if any(sha in text for sha in self.bad) else (0, "ok", "")

    def join(self, i: int, bond: int = 100) -> Node:
        """Validator v<i> registers as a candidate: its own family, host and operator, bonded, signed by its key."""
        name = f"v{i}"
        keys = keys_for(self.sim, name)
        self.fund(keys.address(), 5_000)
        node_v3.register(self.chain, keys, Wallet(self.rpc, keys.account_secret(), name), bond * COIN,
                         self.work / "receipts", log=self.log(name), proof="simulated", family=FAMILIES[i],
                         host=f"host-{i}", image=v2.DEVNET_IMAGE, tee_type=TEES[i % 3])
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
        receipt = self.reporter.send(self.chain.race, "register(bytes32,bool)", v3.ZERO, False)
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

    def submit_fix(self, bounty: int, issue: int, label: str, good: bool) -> tuple:
        """The solver seals a fix and opens its pull request. Returns (the submission, the commitment's opening)."""
        sha = hashlib.sha1(f"pof devnet v3 fix {label}".encode()).hexdigest()
        (self.work / "src" / sha).mkdir(parents=True, exist_ok=True)
        if not good:
            self.bad.add(sha)
        fix, salt = v2.commit_word(sha), crypto.keccak256(f"salt {label}".encode())
        self.solver.send(self.chain.race, "attempt(uint256)", bounty)
        receipt = self.solver.send(self.chain.race, "commit(uint256,bytes32)", bounty,
                                   v3.fix_commitment(fix, v3.ZERO, salt, self.solver.address))
        log = next(x for x in receipt["logs"] if x["topics"][0] == topic(v3.COMMITTED))
        s = int(log["topics"][2], 16)
        self.host.add_pull(f"Fix the median ({label})",
                           logic.pr_body(100 + issue, bounty, s, "0x" + salt.hex(), self.solver.address), sha)
        self.chain.live[s] = True
        return s, (fix, v3.ZERO, salt)

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
        window's end, a deposit's return), or only mine the blocks a draw's seed waits for. False, with nothing moved,
        when there is no deadline ahead."""
        c, now, targets = self.chain, self.chain.now(), []
        block, blocks_only = c.block(), False  # a draw waits for its seed block: only blocks are needed, not time
        count = c.panel_count()
        self.open_panels |= set(range(self.seen_panels + 1, count + 1))
        self.seen_panels = count
        for pid in sorted(self.open_panels):
            p = c.panel(pid)
            if p["counted"] or (p["kind"] == v3.SHADOW and p["closed"]) or now > p["revealBy"] + DAY:
                self.open_panels.discard(pid)
                continue
            targets += [p["sealBy"] + 1, p["revealBy"] + 1]
        for s in list(c.live):
            v = c.verdict(s)
            st = v["status"]
            blocks_only |= st == v3.SEALED and block <= v["seedBlock"] + 1
            if st in (v3.HELD, v3.WINDOW):
                blocks_only |= v["auditBlock"] + 1 >= block and not (v["auditDecided"] and v["auditsDrawn"] == v["auditsDue"])
                blocks_only |= (v["challengeOpen"] and v["challengePid"] == 0 and v["challengeEpoch"] == 0
                                and v["challengeBlock"] + 1 >= block)
            if v["status"] == v3.WINDOW and not v["challengeOpen"]:
                targets.append(v["finalAt"])
            elif v["status"] == v3.FINAL:
                if c.submission(s)["done"]:
                    del c.live[s]
                else:
                    targets.append(v["finalAt"] + REPORT_WINDOW + 1)
            elif v["status"] not in (v3.SEALED, v3.WAITING, v3.JUDGING, v3.HELD, v3.WINDOW):
                del c.live[s]
        ahead = [t for t in targets if t > now]
        if blocks_only:
            self.warp(12)  # six blocks, 2 s apart as on the devnet
            return True
        if not ahead:
            return False
        self.warp(min(ahead) - now)
        self.jumps += 1
        return True

    def poke(self) -> None:
        """Changes the registry's epoch (a 1 micro-coin top-up of the genesis bond, by anyone): a waiting draw is
        retried only after the registry changes."""
        self.minter.send(self.chain.registry, "topUp(address,uint256)", self.nodes["genesis"].address, 1)

    def drive(self, until, what: str, steps: int = 20000, idle_max: int = 40, poke: bool = False,
              strict: bool = True, only=None, feed=None) -> bool:
        """Ticks every node; when none makes progress, jumps to the next deadline. With no deadline ahead the network
        is idle: `feed`, if given, is called for more work (new registrations; it returns False when it has no more);
        otherwise the clock moves on a little (half an hour; with `poke`, six blocks and a change of the registry's
        epoch, so a draw that waits for a registry change is retried). After `idle_max` idle moments in a row with
        no deadline reached in between it gives up: an error when `strict`, else False. `only`: the nodes that run
        meanwhile (default: all)."""
        stalls = 0
        for _ in range(steps):
            if until():
                return True
            if any([n.tick(self.start) for name, n in self.nodes.items() if only is None or name in only]):
                continue
            before = self.jumps
            if only is not None:  # the others aren't running: no deadline of theirs may pass meanwhile, only blocks
                stalls += 1
                if stalls > idle_max:
                    break
                self.warp(12)
                continue
            if self.jump():
                stalls = 0 if self.jumps > before else stalls
                continue
            stalls += 1
            if stalls > idle_max:
                break
            if feed is not None and feed():
                continue
            if poke:
                self.poke()
                self.pokes += 1
            self.warp(12 if poke else 1800)
        if strict:
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
    filed = n.evs(c.race, "ChallengeFiled(uint256,address)", s)[0]
    cpid, kc, drawn = panels_of(n, s, v3.CHALLENGE)[-1]
    resolved = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s)[-1]
    settled = n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s)
    t = {"counted": n.when(counted), "filed": n.when(filed), "drawn": n.when(drawn), "resolved": n.when(resolved)}
    return {"submission": s, "challengePanel": cpid, "challengeK": kc,
            "wrongPassToReversal_s": t["resolved"] - t["counted"],
            "wrongPassToChallenge_s": t["filed"] - t["counted"],
            "challengeWaitedForAPanel_s": t["drawn"] - t["filed"],
            "panelDrawnToReversal_s": t["resolved"] - t["drawn"],
            "reversalToSettlement_s": (n.when(settled[-1]) - t["resolved"]) if settled else None}


def say_heal(what: str, h: dict) -> None:
    print(f"time to heal ({what}): {hours(h['wrongPassToReversal_s'])} of chain time from the wrong pass to its "
          f"reversal\n  = {hours(h['wrongPassToChallenge_s'])} until a watcher challenged it"
          f"\n  + {hours(h['challengeWaitedForAPanel_s'])} the challenge waited for a panel of {h['challengeK']} "
          f"to exist (validators qualifying)"
          f"\n  + {hours(h['panelDrawnToReversal_s'])} from the panel's draw to its verdict (the seal window, then the "
          f"reveals)", flush=True)


def run(rpc: Rpc, record: dict, work: Path, heal: bool, verbose: bool, report: str | None) -> int:
    started = time.time()
    n = Net(rpc, record, work, verbose)
    c, P = n.chain, n.panel
    out: dict = {"chainId": c.chain_id(), "race": c.race, "besideV2": record.get("besideV2")}
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
    s_h = 0
    if heal:
        n.funder.send(c.race, "pledge(uint256,uint256)", b2, 200 * COIN)
        s_h, opening_h = n.submit_fix(b2, issue3h, "a bad fix", good=False)
        for name in ("v1", "v2"):
            n.nodes[name].lies.add(s_h)  # the two validators that will sit with the genesis validator lie on it
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
    n.drive(lambda: c.verdict(s_b)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s_b)["paid"]
            and (not heal or (c.verdict(s_h)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s_h)["paid"])),
            "the waiting fix drawn and judged")
    pid, k, drawn_log = panels_of(n, s_b, v3.COUNTED)[0]
    check(k == 3 and set(P.drawn(s_b)) == {genesis.address, n.nodes["v1"].address, n.nodes["v2"].address}
          and c.verdict(s_b)["pass"],
          f"it was drawn with k = 3 ({n.named(P.drawn(s_b))}) {(n.when(drawn_log) - topped_at) / 60:,.0f} minutes "
          f"after the top-ups (it had waited {hours(topped_at - waited_at)} for them), and passed")
    check(n.bounty_state(b1) == WON and c.bounty(b1)["winner"] == s_b, f"bounty {b1} is won by submission {s_b}")
    n.solver.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b1, *opening)
    check(n.bounty_state(b1) == MERGED, "the solver claimed it (the commitment opened): its award started")
    out["waitingBounty"] = {"submission": s_b, "judgedAt": judged, "k1Limit": limit1, "k": k,
                            "waitedForTopUpsSeconds": topped_at - waited_at,
                            "topUpsToDrawSeconds": n.when(drawn_log) - topped_at}
    if heal:
        check(c.verdict(s_h)["pass"] and c.verdict(s_h)["k"] == 3 and n.bounty_state(b2) == WON,
              f"a second wrong verdict passed: a bad fix (its tests fail) was passed 2 to 1 by a panel of 3 with two "
              f"lying judges (submission {s_h}), and won bounty {b2}")
        n.solver.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b2, *opening_h)
        n.fund(genesis.address, 1_000)
        check(genesis.challenge(s_h) is not None and c.verdict(s_h)["challengeOpen"] and n.bounty_state(b2) == MERGED,
              "its solver claimed it; the outvoted judge (genesis) re-ran the check and challenged it inside its window")

    # ---------- 4. a silent judge is replaced ----------
    print("\n== 4. a silent validator is replaced (scenario 4) ==", flush=True)
    _, s4 = n.register_issue()
    n.drive(lambda: c.verdict(s4)["status"] == v3.JUDGING, "a check drawn", only=("genesis",))  # nobody else seals yet
    first = P.drawn(s4)
    floor = c.bond_floor()
    others = [k for k in first if k != genesis.address]
    silent_key = next((k for k in others if c.validator(k)["bond"] == floor), others[0])  # a floor bond, if one is drawn
    slashed = c.validator(silent_key)["slashed"]
    n.nodes[n.name(silent_key)].mute.add(P.pid(s4))
    n.drive(lambda: c.verdict(s4)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s4)["paid"],
            "the check decided without the silent validator")
    missed = n.evs(c.panels, "Missed(uint256,address,bool)", c.verdict(s4)["pid"], silent_key)
    after = P.drawn(s4)
    check(len(missed) == 1 and silent_key not in after and len(after) == P.size(s4) == 3,
          f"{n.name(silent_key)} stayed silent on its seat: at the seal deadline it was replaced from the same sample "
          f"({n.named(first)} -> {n.named(after)}); k stayed 3")
    check(c.validator(silent_key)["slashed"] - slashed >= rpc.view(c.registry, "SILENCE_SLASH()", ["uint256"])[0],
          f"its silence cost it {(c.validator(silent_key)['slashed'] - slashed) / COIN:,.2f} of its bond")
    check(P.replaces_silent() and n.seats_reported(c.verdict(s4)["pid"]) == P.reports(s4, silent=1) == 3,
          "the panel still decided with 3 verdicts and 3 usage reports")
    out["silent"] = {"validator": n.name(silent_key), "slashed": c.validator(silent_key)["slashed"] - slashed,
                     "belowFloor": c.validator(silent_key)["bond"] < floor}
    if c.validator(silent_key)["bond"] < floor:
        check(c.is_active(silent_key) and not n.drawable(silent_key),
              f"its bond is now under the floor ({c.validator(silent_key)['bond'] / COIN:,.2f} of {floor / COIN:,.2f}): "
              f"still active, but drawn for nothing until it tops up")
        n.top_up(n.name(silent_key), floor)
        check(n.drawable(silent_key), "it topped its bond back up to the floor and is drawn again")

    # ---------- 5. k reaches 5 ----------
    print("\n== 5. two more candidates qualify until k reaches 5 ==", flush=True)
    made = n.grow(["v4", "v5"], 12, "v4 and v5 qualify")
    check(len(n.active()) == 6, f"v4 and v5 qualified after {made} more checks: six validators are active")
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
        while len(n.outside(x)) < 3 and (c.verdict(x)["status"] == v3.HELD or c.verdict(x)["challengeOpen"]):
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
    n.drive(lambda: not c.verdict(s_w)["challengeOpen"]
            and n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_w) != [],
            "the k = 1 verdict's challenge judged and settled", poke=True)
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
    settled = n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_w)[-1]
    check(abi.decode(["bool"], abi.hexdata(settled["data"]))[0] and c.owed(watcher.address) >= held_stake,
          f"the challenge was upheld: the watcher's stake and cover ({held_stake / COIN:,.2f}) are credited back to it")
    n.drive(lambda: c.verdict(s_w)["status"] == v3.FINAL, "the reversed verdict final", poke=True)
    n.anyone.send(c.race, "openBounty(uint256)", issue_w)
    check(c.issue(issue_w)["state"] == FORFEITED and c.issue(issue_w)["bounty"] == 0,
          f"registration {issue_w} ended forfeited: no bounty was ever opened on the wrong verdict")
    say_heal("a wrong k = 1 verdict of the lone genesis validator", h)
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
        need_h = n.bond_for(c.verdict(s_h)["bounty"])
        for name in list(n.nodes):
            if name != "genesis":
                n.top_up(name, need_h)
        check(c.verdict(s_h)["challengePid"] == 0,
              f"its challenge waited meanwhile: a panel of 5 outside its three judges needs 5 more validators bonded "
              f"for the bounty ({need_h / COIN:,.2f} each)")
        while len(n.nodes) - 1 - 2 < 5 + c.verdict(s_h)["auditsDue"] and n.next_index <= 8:
            n.join_next(bond=need_h // COIN)
        feed, made = n.feeder(12, 20)
        n.drive(lambda: not c.verdict(s_h)["challengeOpen"]
                and n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s_h) != [],
                "more candidates qualified and the fix's challenge was judged and settled", feed=feed, poke=True)
        check(True, f"more candidates qualified ({len(n.active())} validators active, after {made[0]} more checks) "
                    f"and the challenge was judged")
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
        say_heal("a bad fix passed 2 to 1 by a panel of 3", hh)
        hh["falseReceiptFound"] = false_receipt
        print(f"  no receipt was found false ({'yes' if false_receipt else 'no'}): the two lying judges keep their bonds, "
              f"and the solver's only loss is the award it never received", flush=True)
        out["healFix"] = hh

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
          "ADRs and escalated fixes (RaceV3 can't open them); the test-backed dispute and the appeal of D21-D23 "
          "(task 10.4, not built); short test windows (the contracts' windows are constants)")
    print("devnet-v3: all checks passed", flush=True)
    return 0


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
