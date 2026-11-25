"""One bounty end to end on the local devnet with Radicle on the internal network (proof-of-fix#251, task 4.6; design
L9, L12, L19, L20, L22, L23, L24, L25). Run it with `scripts/integration.sh --version 3 --radicle`, which builds the
Radicle node image (spikes/radicle/Dockerfile, the pinned release) and calls this file. `python3
tests/integration/suite_v3_radicle.py clean` removes anything a stopped run left behind.

It is not a third harness. It joins the two that exist:
- the Radicle spike's (spikes/radicle/v3_spike.py): real Radicle 1.10.3 nodes, anvil and a relay on a Docker network
  created with --internal, the chain reached only through a `docker exec` pipe, the deployment from inside the anvil
  container, the isolation check and the results; under its own names here (`v3_spike.use_names`);
- the v3 suite's network (tests/integration/suite_v3.py `Net`): real `NodeV3` validators with the fake judge, the
  chain's clock moved to the next deadline, validators qualifying by their shadow verdicts.
What it adds is the launch's configuration and one bounty's story through the real parts: every validator configured
as `python3 -m oracle run` configures it (`radicle_v3.attach`) with ORACLE_FIX_SOURCE=radicle, ORACLE_MERGE_VIA=radicle
and ORACLE_SEAT_NODES=chain, each reaching its own Radicle node with `docker exec`; each fix's tests in the real
Docker sandbox (twice, protected tests overlaid); the reporter, the funder and the solvers playing through `pofctl
--v3` as separate processes.

The deployment is the launch's rules on a local chain (contracts/script/NodeV3Local.s.sol): panel caps off
(`launch`, L23), panels of 3 and same-size challenges (`kTop` 3, `same`, L24), the windows in minutes (every hour a
minute, L4), the taxi fare (`judgeFee` 0) and the launch's test coin (CoinFaucet's POFTEST, L17: its genesis mint funds
the run's keys, and the funder claims from the faucet with `pofctl faucet`). The repository is real Python code whose
`.pof/check.json` protects `tests/` (L20).

The story, each step needing the one before:
S. setup: seven validators (a genesis one and six who qualify by their shadow verdicts, their registrations' claims
   read from Radicle issues), each registered with its own Radicle node's key (`radNodeOf`); the owner's node, the
   repository's first delegate, hands over to the seats through the same seat adapter, and the identity follows the
   seats as they qualify;
1. a Radicle issue registered with `pofctl --v3 issue register --rad-issue … --comment` (the reporter's signed claim);
   its check passes, each judge reading the issue on its own node;
2. a pledge refused while no solver is active; three solvers' unfunded fixes, each a Radicle patch opened with the
   command `pofctl --v3 submit --patch` prints, judged, claimed, refused at `merge` before finality and merged at it,
   the seats' nodes pushing the canonical `main` to `Heads.head` after each: three active solvers;
3. a pledge (`pofctl --v3 pledge`) and a fix submitted as a Radicle patch with pofctl;
4. a panel of 3 judges it: each judge takes the patch from its own node, runs the tests twice on a run tree with the
   protected tests overlaid, and the fake judge follows them;
5. finality, then `pofctl --v3 merge`: the canonical `main` on every delegate's node equals `Heads.head`;
R. rebase in place (#310, v3.1): two fixes on the same head; the first merges, the second's merge is refused as stale;
   its solver rebases it on its node, `pofctl --v3 rebase` opens the rebase check and the command it prints pushes a
   new revision of the same Radicle patch; the judges take it from their own nodes, and at both verdicts' finality
   `pofctl --v3 merge` moves Heads.head to the rebased commit, which canonical main follows on every delegate's node;
6. a bad fix (it breaks `mean` and weakens the protected test of it) passed by a lying counted panel is claimed,
   challenged by an honest validator, and reversed by a fresh panel of 3: it never reaches `Heads.head` or `main`;
7. `pofctl --v3 verify-head` exits 0 on a delegate's node and on a node that isn't one, and `pofctl --v3
   verify-delegates` passes;
I. isolation (the spike's check): the internal network, no route out, the nodes dialled only each other, no public
   Radicle host in their logs.

pofctl reaches the chain through a JSON-RPC bridge on this machine's loopback (127.0.0.1, an ephemeral port) into the
same pipe: nothing on the internal network is reachable from outside it, and nothing in it reaches out. No model call,
no public chain, no AWS. Results and node logs stay in .integration-radicle-v3/ (gitignored)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import suite_v3 as SV  # noqa: E402
import v3_spike as VS  # noqa: E402
from e2e_node_v3 import ETH_100, keys_for, secret  # noqa: E402
from oracle import crypto, fetch, sandbox, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.node_v3 import NodeV3  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from oracle.rpc import Wallet  # noqa: E402
from oracle.transport import OnchainExchange  # noqa: E402
from pofctl import keys as keysrc  # noqa: E402

PREFIX = os.environ.get("POF_RADICLE_PREFIX", "pof251i")  # containers and network: pof251i-*, unless set
VALIDATORS = ["genesis"] + [f"v{i}" for i in range(1, 7)]  # seven: a panel of 3, an auditor and a fresh 3 (L24)
NODES = ["owner", *VALIDATORS, "reporter", "solver"]
OUT = ROOT / ".integration-radicle-v3"
RECORD_DIR = ROOT / "contracts" / "deployments" / "integration-radicle-v3"
HOME_C = VS.HOME_C
REPO = f"{HOME_C}/repo-a"  # each node's working copy (the spike's repository A)
COIN = 10**6
HOUR = 3600
SEAL_MARGIN = 30  # the windows are minutes: a seal window is 120 s of chain time
FOLLOW_S = 180  # wall seconds for the seats' nodes to bring the canonical main or the identity in line
GENESIS_MINT = 100_000_000 * COIN  # the test coin's genesis mint to the run's minter (L17's 5,000 is Sepolia's)
LAUNCH = {"LOCAL_WINDOWS": "minutes", "LOCAL_PANEL_CAPS": "launch", "LOCAL_K_TOP": "3",
          "LOCAL_CHALLENGE_SIZE": "same", "LOCAL_COIN": "test", "LOCAL_GENESIS_MINT": str(GENESIS_MINT),
          "LOCAL_FAMILIES": ",".join(["anthropic/claude"] + SV.FAMILIES[1:len(VALIDATORS)])}
# the genesis validator's family: the launch's (v3.1 polish VP12, `provider/line`); the others keep the suite's names,
# priced from genesis too (a family the node's `register` accepts: `provider/line`, or already priced)
GENESIS_FAMILY = "anthropic/claude"
SOLVER_C = int.from_bytes(crypto.keccak256(b"pof integration radicle v3 solver-c"), "big") % crypto.N or 1

# The repository: Python code whose tests/ are protected (.pof/check.json), as suite_v3's step 10's, on Radicle.
MEAN = "def mean(xs):\n    return sum(xs) / len(xs)\n"
BROKEN_MEAN = "def mean(xs):\n    return 0\n"
WRONG_MEDIAN = "def median(xs):\n    return 0\n"
FUNCS = {
    "median": "def median(xs):\n    return " + SV.GOOD_MEDIAN + "\n",
    "mode": "def mode(xs):\n    return max(sorted(set(xs)), key=xs.count)\n",
    "spread": "def spread(xs):\n    return max(xs) - min(xs)\n",
    "total": "def total(xs):\n    return sum(xs)\n",
    "middle": "def middle(xs):\n    return sorted(xs)[len(xs) // 2]\n",
    "count": "def count(xs):\n    return len(xs)\n",
    "first": "def first(xs):\n    return xs[0]\n",
}
CHECKS = {"median": ("median([4, 1, 3, 2])", "2.5"), "mode": ("mode([1, 2, 2, 3])", "2"),
          "spread": ("spread([4, 1, 9])", "8"), "total": ("total([1, 2, 3])", "6"),
          "middle": ("middle([3, 1, 2])", "2"), "count": ("count([3, 1, 2])", "3"), "first": ("first([3, 1, 2])", "3")}
ISSUES = {
    "median": ("median() of an even list is wrong", "median([4, 1, 3, 2]) returns 0; expected 2.5."),
    "mode": ("No mode()", "stats has no mode(): mode([1, 2, 2, 3]) should be 2."),
    "spread": ("No spread()", "stats has no spread(): spread([4, 1, 9]) should be 8."),
    "total": ("No total()", "stats has no total(): total([1, 2, 3]) should be 6."),
    "middle": ("No middle()", "stats has no middle(): middle([3, 1, 2]) should be 2."),
    "count": ("No count()", "stats has no count(): count([3, 1, 2]) should be 3."),
    "first": ("No first()", "stats has no first(): first([3, 1, 2]) should be 3."),
}


def acceptance(func: str) -> str:
    call, want = CHECKS[func]
    return (f"import unittest\n\nfrom stats import {func}\n\n\nclass Issue(unittest.TestCase):\n"
            f"    def test_{func}(self):\n        self.assertEqual({call}, {want})\n")


def files_with(funcs: list, broken: bool = False) -> dict:
    """stats.py with `funcs` (FUNCS' names, in order; median is the genesis' wrong one until it's fixed) and each one's
    acceptance test at the root; `broken`: mean() broken too, and its protected test weakened (the bad fix)."""
    median = FUNCS["median"] if "median" in funcs else WRONG_MEDIAN
    body = "\n\n".join([BROKEN_MEAN if broken else MEAN, median] + [FUNCS[f] for f in funcs if f != "median"])
    out = {"stats.py": body}
    out.update({f"test_{f}.py": acceptance(f) for f in funcs})
    if broken:
        out["tests/test_stats.py"] = SV.WEAK_TEST
    return out


GENESIS_FILES = {
    "README.md": "# stats\n\nThe devnet's repository on Radicle (proof-of-fix#251, task 4.6).\n",
    "stats.py": MEAN + "\n\n" + WRONG_MEDIAN,
    "tests/test_stats.py": SV.MEAN_TEST,
    ".pof/check.json": json.dumps({"commands": [SV.SUITE], "protected": ["tests/"]}) + "\n",
}


# ---------------------------------------------------------------------------------------------------------------------
# pofctl's way to the chain: a JSON-RPC bridge on the loopback into the relay's pipe


def bridge(rpc: VS.PipeRpc) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (http.server's name)
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                req = json.loads(body)
                out = ([rpc._exchange(json.dumps(x).encode()) for x in req] if isinstance(req, list)
                       else rpc._exchange(json.dumps(req).encode()))
                data, code = json.dumps(out).encode(), 200
            except Exception as e:  # noqa: BLE001 (the client sees an error, as from any endpoint)
                data, code = json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603,
                                                                                 "message": str(e)[:200]}}).encode(), 200
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------------------------------------------------------------
# The validators and the network


class Node(SV.Node):
    """suite_v3's node, lying (when told to) only on its counted seats: its own re-run for a challenge, an audit and a
    challenge seat stay honest."""

    def _judge(self, s: int, p: dict, late: bool = False, seat: tuple | None = None):
        self.judge.lie = s in self.lies and seat is not None and p["kind"] == v3.COUNTED
        try:
            return NodeV3._judge(self, s, p, late, seat)
        finally:
            self.judge.lie = False


class RadNet(SV.Net):
    """suite_v3's network with the launch's coin (sent from the genesis mint, never minted), a clock that moves only
    when the run moves it (anvil's timestamp interval 0: wall time spent in the sandbox or on Radicle doesn't pass
    on-chain), and validators on Radicle."""

    def __init__(self, rpc, record: dict, work: Path, story: "Story") -> None:
        self.story = story
        super().__init__(rpc, record, work, verbose=False)
        self.rad_nodes = {n: D.key_from_did(story.rad.did[n]) for n in VALIDATORS}

    def fund(self, address: str, coins: int) -> None:
        self.rpc.call("anvil_setBalance", [address, ETH_100])
        if address.lower() != self.minter.address.lower():  # the minter holds the genesis mint
            self.minter.send(self.chain.coin(), "transfer(address,uint256)", address, coins * COIN)

    def warp(self, seconds: int, blocks: int = 6) -> None:
        self.rpc.call("evm_setNextBlockTimestamp", [self.chain.now() + int(seconds)])
        for _ in range(blocks):
            self.rpc.call("evm_mine", [])

    def env(self, name: str) -> dict:
        """The node's Radicle settings, as an operator sets them for `python3 -m oracle run`."""
        return {"ORACLE_FIX_SOURCE": "radicle", "ORACLE_MERGE_VIA": "radicle", "ORACLE_SEAT_NODES": "chain",
                "ORACLE_RADICLE_RID": self.story.rad.rid["a"],
                "ORACLE_RADICLE_EXEC": f"docker exec -i {self.story.rad.c(name)}", "ORACLE_RADICLE_REPO": REPO,
                "ORACLE_RADICLE_EVERY": "15"}

    def make_node(self, name: str, family: str, keeper: bool = False, tag: str = "") -> Node:
        keys = keys_for(self.sim, name)
        wallet = Wallet(self.rpc, keys.account_secret(), name)
        me = keys.address()
        self.names[me.lower()] = name
        node = Node(self.chain, keys, FakeJudge(family=family), self.host, "pof/stats", self.work / "src" / name,
                    OnchainExchange(self.chain, keys, wallet=wallet), Store(self.work / "receipts"),
                    runner=sandbox.docker_runner, log=self.log(name + tag), wallet=wallet,
                    rounds=Rounds(self.work / "rounds", self.chain.chain_id(), self.chain.race, me + tag),
                    keeper=keeper, costs={"vcpu_second": 12_000_000, "gb_second": 1_300_000} if keeper else None,
                    seal_margin=SEAL_MARGIN)
        RV.attach(node, self.env(name), self.chain, me, sign=keys.sign)
        return node

    def register_issue(self, claim: bool = True) -> tuple:
        """The suite's registrations (the validators' qualification traffic): each claimed by a Radicle issue the
        reporter's node opens, with the reporter's signed claim as its comment."""
        issue, s = super().register_issue(claim=False)
        if claim:
            st = self.story
            iid = st.rad_issue("reporter", "a", f"Qualification check {issue}",
                               "median([4, 1, 3, 2]) returns 0; expected 2.5.")
            st.rad_comment("reporter", "a", iid, "\n".join(RV.signed_claim_lines(
                self.reporter.sign, self.reporter.address, self.chain.chain_id(), self.chain.race, issue,
                self.chain.repo(), iid)))
        return issue, s

    def feeder(self, batch: int, rounds: int):
        feed, made = super().feeder(batch, rounds)

        def announced() -> bool:
            more = feed()
            if more:
                self.story.rad.sync("a", ["reporter"], "announce")
            return more
        return announced, made


# ---------------------------------------------------------------------------------------------------------------------
# The story


class Failed(AssertionError):
    pass


class Story(VS.Spike):
    def __init__(self, keep: bool) -> None:
        super().__init__(keep)
        self.server: ThreadingHTTPServer | None = None
        self.owner_seat: RV.SeatAdapter | None = None
        self.funcs: list = []  # what Heads.head's stats.py has (FUNCS' names)
        self.wall: dict = {}

    def must(self, cond, what: str) -> None:
        if not self.res.check(cond, what):
            raise Failed(what)

    # ---------- infrastructure ----------

    def repos(self) -> str:
        """One repository (the race's, L1): the owner's node creates it; every other node clones it."""
        rad = self.rad
        rad.sh("owner", "mkdir -p g/tests g/.pof && cd g && git init -q -b main")
        for path, text in GENESIS_FILES.items():
            rad.sh("owner", f"cat > g/{path}", input=text)
        genesis = rad.sh("owner", "cd g && git add -A && git commit -q -m 'genesis: median() is wrong "
                                  "(proof-of-fix#251)' && git rev-parse HEAD")
        rad.sh("owner", "git clone -q g repo-a && cd repo-a && git remote remove origin && rad init --name pof-stats "
                        "--description 'proof-of-fix#251 task 4.6' --default-branch main --public --no-confirm "
                        ">/dev/null 2>&1")
        rad.rid["a"] = rad.sh("owner", "cd repo-a && rad .")
        if not R.RID_RE.match(rad.rid["a"]):
            raise RuntimeError(f"rad init gave no RID: {rad.rid['a']!r}")
        for n in NODES[1:]:
            for _ in range(15):
                rad.sh(n, f"rad clone {rad.rid['a']} repo-a --no-confirm >/dev/null 2>&1 || rm -rf repo-a", check=False)
                if rad.sh(n, "test -d repo-a/.git && echo yes", check=False) == "yes":
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f"{n} couldn't clone {rad.rid['a']}")
        VS.log(f"repository {rad.rid['a']}; genesis {genesis}")
        return genesis

    def head(self, repo: str = "a") -> str:
        return R.sha_of(self.n.chain.head())

    def ctl(self, *argv, as_: str | None = None, expect_fail: str | None = None) -> dict | None:
        """`pofctl --v3 …` as its own process, with devnet keys (31337 only), against the bridge. Returns its JSON;
        with `expect_fail`, checks that it was refused saying so, with nothing printed on stdout."""
        cmd = [sys.executable, "-m", "pofctl", "--rpc", self.url, "--record", str(self.record_path), "--json",
               *(["--as", as_] if as_ else []), "--v3", *[str(a) for a in argv]]
        env = {**os.environ, "DEVNET_KEYS": "insecure-local", "POFCTL_KEY_SOLVER_C": f"0x{SOLVER_C:064x}",
               "POFCTL_CONFIG": str(OUT / "no-pofctl.json")}
        env.pop("POFCTL_KEYSTORE", None)
        shown = " ".join(([f"--as {as_}"] if as_ else []) + [str(a) for a in argv])
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
                           stdin=subprocess.DEVNULL)
        self.ctl_runs = getattr(self, "ctl_runs", 0) + 1
        if expect_fail is not None:
            err = r.stderr.strip()
            self.must(r.returncode == 1 and expect_fail in err, f"$ pofctl --v3 {shown}: refused ({err[-240:]})")
            return None
        if r.returncode:
            raise Failed(f"pofctl --v3 {shown}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
        self.res.info(f"$ pofctl --v3 {shown}")
        return json.loads(r.stdout)

    def ctl_exit(self, *argv) -> tuple:
        """A pofctl command's exit code and output, as a reader sees them (verify-head, verify-delegates)."""
        cmd = [sys.executable, "-m", "pofctl", "--rpc", self.url, "--record", str(self.record_path), "--v3",
               *[str(a) for a in argv]]
        env = {**os.environ, "DEVNET_KEYS": "insecure-local", "POFCTL_CONFIG": str(OUT / "no-pofctl.json")}
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
                           stdin=subprocess.DEVNULL)
        return r.returncode, (r.stdout + r.stderr).strip()

    def addr(self, role: str) -> str:
        return crypto.address(SOLVER_C if role == "solver-c" else keysrc.key(role, "insecure-local"))

    def tick_seats(self) -> None:
        """One forced pass of every seat adapter: the validators' and the owner's (the first delegate's)."""
        for name, node in self.n.nodes.items():
            try:
                node.radicle_seat.tick(force=True)
            except R.Unavailable as e:
                VS.log(f"  warn {name}: {e}")
        try:
            self.owner_seat.tick(force=True)
        except R.Unavailable as e:
            VS.log(f"  warn owner: {e}")

    def owner_pass(self) -> None:
        try:
            self.owner_seat.tick()
        except R.Unavailable as e:
            VS.log(f"  warn owner: {e}")

    def delegates(self, on: str = "genesis") -> tuple:
        """(the delegates' node names, the threshold) of the identity in force on node `on`."""
        _, doc, _ = self.rad.identity(on, "a")
        names = {R.nid(d): n for n, d in self.rad.did.items()}
        return sorted(names.get(R.nid(d), d) for d in doc["delegates"]), doc["threshold"]

    def in_line(self) -> tuple:
        """(the identity's delegates are the seats' nodes on every validator's node, the problems)."""
        seats = self.n.chain.seats()
        nodes = D.ChainSeatNodes.of(self.n.chain)
        for name in VALIDATORS:
            _, doc, _ = self.rad.identity(name, "a")
            ok, problems = D.verify_delegates(doc, seats, nodes)
            if not ok:
                return False, [f"{name}: " + "; ".join(problems)]
        return True, []

    def settle(self, what: str) -> float:
        """Forced passes of the seat adapters until the identity's delegates are the seats on every validator's node.
        Returns the wall seconds it took."""
        t = time.time()
        while True:
            self.rad.sync("a", VALIDATORS)
            ok, problems = self.in_line()
            if ok:
                return round(time.time() - t, 1)
            if time.time() - t > FOLLOW_S:
                raise Failed(f"{what}: the identity didn't follow the seats in {FOLLOW_S} s: {problems}")
            self.tick_seats()

    def follow(self, sha: str, what: str) -> float:
        """Forced passes of the seat adapters until the canonical main on every delegate's node (and on the solver's,
        which bases the next patch on it) is `sha`. Returns the wall seconds it took."""
        t = time.time()
        while True:
            names, _ = self.delegates()
            at = {x: self.rad.canonical(x, "a") for x in names + ["solver"]}
            if all(v == sha for v in at.values()):
                secs = round(time.time() - t, 1)
                self.wall.setdefault("canonicalFollows", []).append({"what": what, "seconds": secs})
                return secs
            if time.time() - t > FOLLOW_S:
                raise Failed(f"{what}: canonical main isn't {sha[:12]} after {FOLLOW_S} s: "
                             f"{ {k: v[:12] for k, v in at.items()} }")
            self.tick_seats()
            self.rad.sync("a", names + ["solver"])

    # ---------- the run ----------

    def run(self) -> int:
        fetch.remove(OUT)  # the last run's: the nodes' fetched checkouts are read-only (#115)
        try:
            return super().run()
        finally:
            if self.server is not None:
                self.server.shutdown()
                self.server.server_close()

    def scenarios(self) -> None:
        self.setup()
        self.registration()
        iss = self.issues
        self.activation(iss)
        out = self.funded(iss)
        self.rebase_in_place(iss)
        self.reversed(iss, out)
        self.verify()
        self.summary()

    def setup(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("S", "setup: the launch's rules on anvil, seven validators on their own Radicle nodes (node keys "
                          "on-chain, ORACLE_FIX_SOURCE=radicle, ORACLE_SEAT_NODES=chain), the identity following the "
                          "seats; isolation starts here")
        if subprocess.run(["docker", "image", "inspect", sandbox.TEST_IMAGE], capture_output=True).returncode:
            raise Failed(f"the pinned test image isn't here ({sandbox.TEST_IMAGE}); build it: scripts/test-image.sh")
        t0 = time.time()
        self.up()
        genesis_commit = self.repos()
        minter = crypto.address(secret("minter"))
        record = self.deploy_v3(rad.rid["a"], genesis_commit, env={**LAUNCH, "LOCAL_GENESIS_MINT_TO": minter})
        # chain time moves only when the run moves it (RadNet.warp): no wall time spent in the sandbox or on Radicle,
        # and no transaction, passes on-chain (the windows are minutes: a reveal window is 60 s)
        self.rpc.call("anvil_setBlockTimestampInterval", [0])
        record["rid"] = rad.rid["a"]
        self.record_path = OUT / "record.json"
        self.record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.server = bridge(self.rpc)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        rules = record["panelRules"]
        self.must(rules == {"operatorCap": "off", "hostCap": "off", "teeCap": "off", "kTop": 3, "challengeSize": "same"}
                  and record["windowsKind"] == "minutes" and record["judgeFee"] == 0 and record.get("faucet"),
                  f"deployed on the launch's rules: panel caps off, kTop 3, challenges of the same size (Panels reads "
                  f"them back: {rules}), the windows in minutes (seal {record['windows']['seal']} s), the taxi fare "
                  f"(judgeFee 0), and the test coin with its faucet ({record['coin']}, faucet {record['faucet']})")
        n = self.n = RadNet(self.rpc, record, OUT / "work", self)
        c = n.chain
        name = self.rpc.view(c.coin(), "symbol()", ["string"])[0]
        self.must(name == "POFTEST" and crypto.checksum(self.rpc.view(c.coin(), "faucet()", ["address"])[0])
                  == crypto.checksum(record["faucet"]),
                  f"the fee coin is {name}, minted only by its faucet; the run's keys are funded from its genesis mint")
        g = n.make_node("genesis", GENESIS_FAMILY, keeper=True)
        self.rpc.call("anvil_setBalance", [g.address, ETH_100])
        n.nodes["genesis"] = g
        self.owner_seat = RV.SeatAdapter(R.Radicle(rad.rid["a"], ["docker", "exec", "-i", rad.c("owner")], REPO),
                                         c, "0x" + "00" * 20, D.ChainSeatNodes.of(c), log=n.log("owner"), every=15)
        n.watches.append(self.owner_pass)
        for i in range(1, 7):
            n.join(i)
        n.start = max(self.rpc.block() - 20, 0)
        self.must(all(c.rad_node_of(n.nodes[x].address) == D.key_from_did(rad.did[x]) for x in VALIDATORS),
                  "each validator registered its own Radicle node's key: radNodeOf = its node's did:key, for all 7")
        self.must(all(isinstance(n.nodes[x].fixes, RV.RadicleFixes) and isinstance(n.nodes[x].claims, RV.RadicleIssues)
                      and isinstance(n.nodes[x].radicle_seat.nodes, D.ChainSeatNodes) for x in VALIDATORS),
                  "every validator node runs ORACLE_FIX_SOURCE=radicle (patches and issues from its own Radicle "
                  "node), ORACLE_MERGE_VIA=radicle and ORACLE_SEAT_NODES=chain")
        t = time.time()
        made = n.grow(VALIDATORS[1:], 12, "v1 to v6 qualify", rounds=60)
        acts = n.evs(c.registry, "Activated(address)")
        self.chain_t = {"qualified": n.when(acts[-1]) - n.t0}
        self.wall["qualification"] = round(time.time() - t)
        self.must(len(n.active()) == 7 and len(c.seats()) == 7,
                  f"v1 to v6 qualified by their shadow verdicts after {made} registration checks, each claimed by a "
                  f"Radicle issue read on the judges' own nodes ({SV.hours(self.chain_t['qualified'])} of chain time, "
                  f"{self.wall['qualification']} s): 7 seats")
        secs = self.settle("the seats")
        names, threshold = self.delegates()
        self.must(names == sorted(VALIDATORS) and threshold == 4,
                  f"the identity followed the seats (the owner's node handed over through the same seat adapter): "
                  f"delegates {', '.join(names)}, threshold {threshold} ({secs} s of forced passes at the end)")
        rad.sync("a")
        self.must(all(rad.canonical(x, "a") == genesis_commit for x in NODES),
                  f"canonical main = Heads.head (the genesis commit {genesis_commit[:12]}) on all {len(NODES)} nodes")
        for role in ("reporter", "funder", "solver-a", "solver-b", "solver-c"):
            n.fund(self.addr(role), 2_000)
        self.wall["setup"] = round(time.time() - t0)

    def registration(self) -> None:
        """Step 1: a Radicle issue registered with a signed claim (pofctl), the check passing on the judges' nodes."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("1", "a Radicle issue registered with pofctl and the reporter's signed claim; its check passes, "
                          "each judge reading the issue on its own Radicle node")
        self.issues = {}
        for f in ("total", "median", "mode", "spread", "middle"):
            title, body = ISSUES[f]
            if f == "total":  # v3.1 (VP11): pofctl opens the Radicle issue itself, its id from `rad issue open`'s box
                d = self.ctl("issue", "register", "--title", title, "--description", body, "--comment", "--rad-exec",
                             f"docker exec -i {rad.c('reporter')}", as_="reporter")
                iid = d["radIssue"]
                listed = rad.sh("reporter", f"rad cob list --repo {rad.rid['a']} --type xyz.radicle.issue").split()
                self.must(d["opened"] and iid in listed,
                          f"`pofctl --v3 issue register --title {title!r} --description …` opened Radicle issue "
                          f"{iid[:12]} on the reporter's node (real Radicle 1.10.3: its id read from `rad issue "
                          f"open`'s box, checked with `rad issue show`), then registered it (registration "
                          f"{d['issue']})")
            else:
                iid = self.rad_issue("reporter", "a", title, body)
                d = self.ctl("issue", "register", "--rad-issue", iid, "--comment", "--rad-exec",
                             f"docker exec -i {rad.c('reporter')}", as_="reporter")
            self.issues[f] = {"rad": iid, "issue": d["issue"], "check": d["check"], "lines": d["lines"],
                              "at": c.now()}
            c.live[d["check"]] = True
        rad.sync("a", ["reporter"], "announce")
        first = self.issues["total"]
        shown = self.ctl("issue", "show", "--issue", first["issue"])
        self.must(shown["check"] == first["check"] and shown["status"] in ("sealed", "judging", "held", "window",
                                                                         "final"),
                  f"`pofctl --v3 issue show --issue {first['issue']}` reads its check {shown['check']}: "
                  f"{shown['status']}, k = {shown['k']}")
        self.must(all(x["lines"][0] == f"Registration: {x['issue']}" and x["lines"][2].startswith("Claim signature: 0x")
                      for x in self.issues.values()),
                  f"{len(self.issues)} Radicle issues opened on the reporter's node and registered on-chain; pofctl "
                  f"commented each "
                  f"claim with the reporter's signature for that issue (first: Radicle issue {first['rad'][:7]}, "
                  f"registration {first['issue']}, check {first['check']})")
        checks = [x["check"] for x in self.issues.values()]
        n.drive(lambda: all(c.verdict(s)["status"] == v3.FINAL for s in checks), "the registration checks final",
                poke=True)
        s = first["check"]
        shown = self.ctl("issue", "show", "--issue", first["issue"])
        self.must(shown["status"] == "final" and shown["result"] == "pass" and shown["k"] == 3
                  and shown["deposit"]["paid"] > 0,
                  f"`pofctl --v3 issue show` once it is final: {shown['status']}, result {shown['result']} at k = "
                  f"{shown['k']}, {shown['deposit']['paid'] / COIN:,.2f} of its deposit paid to its judges")
        self.verdict_comments(first["rad"], [x["check"] for x in self.issues.values() if x["rad"] == first["rad"]])
        v = c.verdict(s)
        views = {i["id"]: i for i in RV.RadicleIssues(R.Radicle(rad.rid["a"], ["docker", "exec", "-i",
                                                                               rad.c("v1")])).issues()[0]}
        claim = next(x["body"] for x in views[first["rad"]]["comments"] if x["body"].startswith("Registration:"))
        want = {"source": "radicle", "issue": first["rad"], "claims": 1,
                "issue_sha256": hashlib.sha256(RV.issue_text(views[first["rad"]]).encode()).hexdigest(),
                "claim_sha256": hashlib.sha256(claim.encode()).hexdigest()}
        docs = self.receipts(s)
        self.must(v["pass"] and v["k"] == 3 and len(docs) == 3
                  and all({k: d["registration"].get(k) for k in want} == want for _, d in docs),
                  f"registration {first['issue']}'s check passed by a counted panel of 3 ({', '.join(x for x, _ in docs)}): "
                  f"each receipt names Radicle issue {first['rad'][:7]}, one signed claim, the issue's sha256 "
                  f"({want['issue_sha256'][:12]}) and the claim's ({want['claim_sha256'][:12]})")
        final = n.evs(c.panels, "Final(uint256,bool)", s)[0]
        self.chain_t["registrationToFinal"] = n.when(final) - first["at"]
        res.info(f"chain time from the registration to its check's finality: "
                 f"{SV.hours(self.chain_t['registrationToFinal'])} (the window of a panel of 3 at level A, in minutes)")
        for f, x in self.issues.items():
            x["bounty"] = self.ctl("issue", "open", "--issue", x["issue"], as_="reporter")["bounty"]
        res.info("bounties opened: " + ", ".join(f"{x['bounty']} ({f})" for f, x in self.issues.items()))

    def verdict_comments(self, iid: str, checks: list) -> None:
        """VP18: the verdict on the Radicle issue, one comment per verdict (its marker line), with the judge's reason
        for a registration check, made by the counted panel's first revealed seat's node through its own Radicle node
        and read on another node after a sync."""
        rad, c = self.rad, self.n.chain
        marks = {s: f"pof-verdict: {c.chain_id()}/{c.race.lower()}/{s}" for s in checks}

        def bodies() -> list:
            rad.sync("a", VALIDATORS, "announce")
            rad.sync("a", ["reporter"], "fetch")
            views = {i["id"]: i for i in RV.RadicleIssues(R.Radicle(rad.rid["a"], ["docker", "exec", "-i",
                                                                                   rad.c("reporter")])).issues()[0]}
            return [x["body"] for x in views.get(iid, {}).get("comments") or []]

        found: list = []
        end = time.time() + FOLLOW_S
        while time.time() < end:
            # the nodes' passes go on meanwhile (as a running node's would): the comment step reads a panel that
            # wasn't counted at its last look again CHECK_EVERY_S (wall) later, and this wait is the only pass then
            for node in self.n.nodes.values():
                try:
                    node.tick(self.n.start)
                except Exception as err:  # noqa: BLE001 - a pass that fails is tried again next round, as a node does
                    self.res.info(f"a node's pass during the verdict wait: {err}")
            found = bodies()
            if all(any(m in b.splitlines() for b in found) for m in marks.values()):
                break
            time.sleep(3)
        for s, m in marks.items():
            mine = [b for b in found if m in b.splitlines()]
            self.must(len(mine) == 1 and "Reason (" in mine[0] and "registration check" in mine[0],
                      f"the verdict of check {s} on Radicle issue {iid[:7]} (read on the reporter's node): "
                      f"{len(mine)} comment with its marker `{m[:40]}…`; "
                      + (" / ".join(x for x in mine[0].splitlines() if x.startswith(("proof-of-fix verdict", "Reason")))
                         if mine else "none"))
        self.res.info(f"Radicle issue {iid[:7]}: {len(found)} comment(s) in all (the claim and the verdict)")

    def receipts(self, s: int) -> list:
        """[(judge, its stored receipt)] of submission `s`'s counted panel."""
        c, n = self.n.chain, self.n
        pid = c.verdict(s)["pid"]
        out = []
        for i, key in enumerate(c.judges(pid)):
            seat = c.seat(pid, i)
            doc = next(iter(n.nodes.values())).receipts3.get(seat["receipt"]) if seat["receipted"] else None
            out.append((n.name(key), doc))
        return out

    # ---------- a fix through pofctl and Radicle ----------

    def fix(self, role: str, x: dict, funcs: list, label: str, broken: bool = False, merge: bool = True,
            early_merge: bool = False, lie: bool = False, attempt: bool = False) -> dict:
        """`role`'s fix of bounty x["bounty"]: committed on the solver's node on Heads.head, sealed with `pofctl --v3
        submit --patch`, opened as a Radicle patch with the command it prints, judged; then claimed, and (`merge`)
        merged with pofctl at finality and followed by the canonical main. `lie`: every validator lies on its counted
        seat for it. `attempt`: the solver first records its attempt with `pofctl --v3 attempt` (v3.1 polish VP26), as
        the solver's guide does. Returns what happened."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        b = x["bounty"]
        if attempt:
            a = self.ctl("attempt", "--bounty", b, as_=role)
            self.must(a["locked"] and a["attempting"] >= 1 and a["tx"] and "submit" in a["next"],
                      f"{role} recorded its attempt on bounty {b} with `pofctl --v3 attempt`: the share locked at "
                      f"{a['lockBps'] / 100:g} %, {a['attempting']} attempt(s), tx in block {a['block']}")
        base = self.head()
        sha = rad.commit_on("solver", "a", base, files_with(funcs, broken), label)
        d = self.ctl("submit", "--bounty", b, "--patch", sha, "--title", label, as_=role)
        s = d["submission"]
        c.live[s] = True
        if lie:
            for node in n.nodes.values():
                node.lies.add(s)
        out = {"label": label, "solver": role, "bounty": b, "submission": s, "fix": sha, "base": base,
               "claim": d["claim"], "committedAt": c.now()}
        dep = self.rpc.view(c.fees, "maxDeposit(bytes32,uint256)", ["uint256"], c.repo(), 3)[0]
        self.must(d["deposit"] == dep and d["base"] == base,
                  f"{role} sealed submission {s} on bounty {b} with pofctl: commit {sha[:12]} on Heads.head "
                  f"{base[:12]}, a claim of {d['claim'] / COIN:,.2f}, the taxi fare's deposit for kTop = 3 judges "
                  f"({dep / COIN:,.2f}, the rest refunded)")
        opened = rad.sh("solver", f"cd {REPO} && {d['patchCommand']} 2>&1", check=False)
        m = re.search(r"Patch ([0-9a-f]{40}) opened", opened)
        self.must(m is not None, f"the patch opened on the solver's node with pofctl's printed command "
                                 f"(`git push rad {sha[:12]}:refs/patches -o patch.message=…`)"
                                 + ("" if m else f": {opened[-300:]}"))
        out["patch"] = m.group(1)
        rad.sync("a", ["solver"], "announce")
        seen = {}
        for name in VALIDATORS:  # every validator's own node lists it, on Heads.head (what its node will read)
            for _ in range(20):
                pulls, _ = n.nodes[name].fixes.revisions()
                if any(p["head_sha"] == sha and p["base_sha"] == base for p in pulls):
                    seen[name] = True
                    break
                time.sleep(0.5)
        self.must(len(seen) == len(VALIDATORS), f"patch {out['patch'][:7]} is on all 7 validators' Radicle nodes, its "
                                                f"base Heads.head")
        n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s)["paid"],
                f"{label}: judged", poke=True)
        v = c.verdict(s)
        drawn = [n.name(k) for k in n.panel.drawn(s)]
        out.update(k=v["k"], drawn=drawn, passed=bool(v["pass"]), countedAt=n.when(
            n.evs(c.panels, "Counted(uint256,uint256,bool,uint256,uint8)", s)[0]))
        docs = self.receipts(s)
        tests = [d_["receipt"]["tests"] for _, d_ in docs if d_]
        fetched = all((n.work / "src" / x / sha).is_dir() for x in drawn)
        good = not broken
        self.must(v["k"] == 3 and len(tests) == 3 and fetched
                  and all(t["protected"] == ["tests"] and len(t["runs"]) == 2 for t in tests)
                  and all((t["exit_code"] == 0) == good and all((r["exit_code"] == 0) == good for r in t["runs"])
                          for t in tests),
                  f"a counted panel of 3 ({', '.join(drawn)}) judged it: each took the commit from its own Radicle "
                  f"node and ran the tests twice, each run in a fresh container, on a run tree with tests/ protected "
                  f"(the base's copy); both runs {'passed' if good else 'failed'} for every judge"
                  + (f"; {tests[0]['not_run']} changed file under tests/ not run" if broken else ""))
        self.must(v["pass"] == (good or lie) and n.bounty_state(b) == SV.WON and c.bounty(b)["winner"] == s,
                  f"the verdict: {'pass' if v['pass'] else 'fail'}"
                  + (" (the counted judges lied: their receipts say the tests failed)" if lie else
                     " (the fake judge follows the tests)") + f"; bounty {b} is won by submission {s}")
        self.ctl("claim", "--bounty", b, "--patch", sha, "--base", base, "--salt", d["salt"], as_=role)
        out["claimedAt"] = c.now()
        self.must(c.bounty(b)["state"] == SV.CLAIMED and self.head() == base,
                  f"{role} claimed it with pofctl; Heads.head is still the base {base[:12]} (L9: it moves at finality)")
        if early_merge:
            self.ctl("merge", "--bounty", b, as_=role, expect_fail="not yet")
        if not merge:
            return out
        n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"{label}: final", poke=True)
        out["finalAt"] = n.when(n.evs(c.panels, "Final(uint256,bool)", s)[0])
        m = self.ctl("merge", "--bounty", b, as_=role)
        out["mergedAt"] = n.when(n.evs(c.race, "HeadMerged(uint256,uint256,uint256,bytes32)", b)[-1])
        self.must(m["merged"] and not m["already"] and m["head"] == sha and self.head() == sha,
                  f"at finality `pofctl --v3 merge` moved Heads.head {base[:12]} -> {sha[:12]} (chain time: claim to "
                  f"final {SV.hours(out['finalAt'] - out['claimedAt'])}, final to merge "
                  f"{out['mergedAt'] - out['finalAt']} s)")
        secs = self.follow(sha, label)
        names, threshold = self.delegates()
        self.must(True, f"the seats' nodes pushed their main: the canonical main on all {len(names)} delegates' nodes "
                        f"(threshold {threshold}) and the solver's is {sha[:12]} = Heads.head, {secs} s after the merge")
        out["followSeconds"] = secs
        self.funcs = list(funcs)
        return out

    def activation(self, iss: dict) -> None:
        res, n = self.res, self.n
        c = n.chain
        res.scenario("2", "three solvers made active by unfunded fixes merged at finality (L6), each a Radicle patch "
                          "through pofctl")
        self.ctl("pledge", "--bounty", iss["total"]["bounty"], "--amount", 10, as_="funder",
                 expect_fail="active solvers: 0 of the 3 needed")
        self.fixes = []
        plan = [("solver-a", "median", ["median"]), ("solver-b", "mode", ["median", "mode"]),
                ("solver-c", "spread", ["median", "mode", "spread"])]
        for k, (role, f, funcs) in enumerate(plan):
            self.fixes.append(self.fix(role, iss[f], funcs, f"fix {f} (unfunded)", early_merge=k == 0))
        book = crypto.checksum(self.rpc.view(c.race, "solverBook()", ["address"])[0])
        actives = self.rpc.view(book, "activeCount()", ["uint256"])[0]
        self.must(actives == 3 and self.rpc.view(book, "pledgesOpen()", ["bool"])[0],
                  f"three solvers' unfunded fixes were merged: {actives} active solvers, pledges open")

    def funded(self, iss: dict) -> dict:
        res, n = self.res, self.n
        c = n.chain
        res.scenario("3", "a pledge, and a fix submitted as a Radicle patch with pofctl")
        x = iss["total"]
        f = self.ctl("faucet", as_="funder")
        self.must(f["claimed"] == 20 * COIN, f"the funder claimed {f['claimed'] / COIN:g} test coins from the faucet "
                                             f"with pofctl (one claim per address every 2 hours)")
        self.ctl("faucet", as_="funder", expect_fail="may claim from the faucet")
        p = self.ctl("pledge", "--bounty", x["bounty"], "--amount", 105, as_="funder")
        self.must(p["activeSolvers"] == 3 and p["held"] >= 105 * COIN,
                  f"the funder pledged 105 to bounty {x['bounty']} with pofctl (3 active solvers): it holds "
                  f"{p['held'] / COIN:,.2f}")
        for name in VALIDATORS:  # bonded for the claim (a fix's bounty is judged at its price on offer, D29)
            n.top_up(name, n.bond_for(110 * COIN))
        res.scenario("4", "a panel of 3 judges it, with protected tests and two runs, using the fake judge")
        res.scenario("5", "finality, then merge: the canonical main on the delegates' nodes equals Heads.head")
        res.cur = "4"
        out = self.fix("solver-a", x, self.funcs + ["total"], "fix total (funded)", early_merge=True, attempt=True)
        self.funded_fix = out
        res.cur = "5"
        self.must(c.award(x["bounty"], c.bounty(x["bounty"])["epoch"])["merged"],
                  f"bounty {x['bounty']}'s fix is merged; its claim of {out['claim'] / COIN:,.2f} closes into "
                  f"solver-a's reputation")
        return out

    def registered(self, f: str) -> dict:
        """Issue `f` (ISSUES) opened on the reporter's node and registered with pofctl, its check final, its bounty
        open: step 1's way, for one more issue."""
        rad, n = self.rad, self.n
        c = n.chain
        title, body = ISSUES[f]
        iid = self.rad_issue("reporter", "a", title, body)
        d = self.ctl("issue", "register", "--rad-issue", iid, "--comment", "--rad-exec",
                     f"docker exec -i {rad.c('reporter')}", as_="reporter")
        c.live[d["check"]] = True
        rad.sync("a", ["reporter"], "announce")
        n.drive(lambda: c.verdict(d["check"])["status"] == v3.FINAL, f"{f}: its registration check final", poke=True)
        b = self.ctl("issue", "open", "--issue", d["issue"], as_="reporter")["bounty"]
        return {"rad": iid, "issue": d["issue"], "check": d["check"], "bounty": b}

    def rebase_in_place(self, iss: dict) -> None:
        """Step R (#310, task 6.2): two fixes on the same head; the first merges; the second's merge is refused as
        stale; its solver rebases it onto the new head on its own node, `pofctl --v3 rebase` opens the rebase check,
        and the command it prints pushes the rebased commit as a new revision of the same Radicle patch; the judges
        take that revision from their own nodes, and at both verdicts' finality `pofctl --v3 merge` moves Heads.head to
        the rebased commit, which canonical main follows on every delegate's node."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("R", "rebase in place: a stale winner's fix rebased as a new revision of its Radicle patch, judged "
                          "and merged; canonical main fast-forwards to it")
        for f in ("count", "first"):  # registered here: earlier, their checks would move the funded fix's price on
            iss[f] = self.registered(f)
        funcs = list(self.funcs)
        first = self.fix("solver-a", iss["count"], funcs + ["count"], "fix count (merged first)", merge=False)
        second = self.fix("solver-b", iss["first"], funcs + ["first"], "fix first (on the same head)", merge=False)
        n.drive(lambda: all(c.verdict(x["submission"])["status"] == v3.FINAL for x in (first, second)),
                "R: both final", poke=True)
        self.ctl("merge", "--bounty", first["bounty"], as_="solver-a")
        new_head = first["fix"]
        self.follow(new_head, "R: the first fix")
        self.ctl("merge", "--bounty", second["bounty"], as_="solver-b", expect_fail="stale base")
        sha = rad.commit_on("solver", "a", new_head, files_with(funcs + ["count", "first"]),
                            "fix first, rebased onto fix count")
        d = self.ctl("rebase", "--bounty", second["bounty"], "--patch", sha, "--patch-id", second["patch"],
                     as_="solver-b")
        rid = d["check"]
        c.live[rid] = True
        self.must(d["original"] == second["submission"] and d["base"] == new_head and not d["thirdParty"],
                  f"solver-b opened rebase check {rid} of submission {second['submission']} with pofctl: commit "
                  f"{sha[:12]} on Heads.head {new_head[:12]}")
        pushed = rad.sh("solver", f"cd {REPO} && {d['patchCommand']} 2>&1", check=False)
        rad.sync("a", ["solver"], "announce")
        seen = {}
        for name in VALIDATORS:
            for _ in range(20):
                pulls, _ = n.nodes[name].fixes.revisions()
                if any(p["patch"] == second["patch"] and p["head_sha"] == sha and p["base_sha"] == new_head
                       for p in pulls):
                    seen[name] = True
                    break
                time.sleep(0.5)
        self.must(len(seen) == len(VALIDATORS),
                  f"the rebased commit is a new revision of the same patch {second['patch'][:7]} on all 7 validators' "
                  f"nodes, its base the new Heads.head (pofctl's printed push: {pushed.splitlines()[-1][:120] if pushed else ''})")
        n.drive(lambda: c.verdict(rid)["status"] == v3.FINAL, "R: the rebase check final", poke=True)
        self.must(c.verdict(rid)["pass"] and c.verdict(rid)["k"] == 3,
                  f"a fresh panel of 3 ({', '.join(n.name(k) for k in n.panel.drawn(rid))}) passed the rebased tree, "
                  f"with the new head's protected tests")
        m = self.ctl("merge", "--bounty", second["bounty"], as_="solver-b")
        self.must(m["merged"] and m["rebase"] == rid and m["head"] == sha and self.head() == sha,
                  f"at both verdicts' finality `pofctl --v3 merge` moved Heads.head {new_head[:12]} -> {sha[:12]}: the "
                  f"rebased commit, not the original {second['fix'][:12]}")
        secs = self.follow(sha, "R: the rebased fix")
        self.must(True, f"canonical main fast-forwarded to the rebased commit on every delegate's node ({secs} s)")
        self.funcs = funcs + ["count", "first"]
        code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('genesis')}")
        self.must(code == 0, f"pofctl --v3 verify-head exits {code} after the rebase: {out[-160:]}")
        self.rebase = {"first": first, "second": second, "rebase": rid, "fix": sha}

    def reversed(self, iss: dict, good: dict) -> None:
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("6", "a bad fix that passes is reversed by a challenge and never reaches main")
        x = iss["middle"]
        self.ctl("pledge", "--bounty", x["bounty"], "--amount", 60, as_="funder")
        head = self.head()
        out = self.fix("solver-b", x, self.funcs + ["middle"], "a bad fix: middle() added, mean() broken, its "
                       "protected test weakened", broken=True, merge=False, lie=True)
        s = out["submission"]
        inside = set(n.panel.drawn(s))
        watcher = next(n.nodes[x_] for x_ in VALIDATORS if n.nodes[x_].address not in inside)
        n.fund(watcher.address, 1_000)
        v = c.verdict(s)
        if v["challengeOpen"]:
            res.info("its random audit disagreed first and opened the challenge")
        else:
            ev = watcher.challenge(s)
            self.must(ev is not None and c.verdict(s)["challengeOpen"],
                      f"{n.name(watcher.address)}, outside its panel, re-ran the check (the tests fail), disagreed "
                      f"and challenged it inside its window")
        n.watches.append(lambda: n.rechallenge(watcher, s))  # L25: filed again if it lapses with no panel
        n.drive(lambda: not c.verdict(s)["challengeOpen"]
                and n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s) != [],
                "the bad fix's challenge judged and settled", poke=True)
        for node in n.nodes.values():
            node.lies.discard(s)
        h = SV.heal_times(n, s)
        resolved = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s)[-1]
        upheld, now_pass, _ = SV.abi.decode(["bool", "bool", "bool"], SV.abi.hexdata(resolved["data"]))
        cjudges = [k for k in c.judges(h["challengePanel"]) if k]
        self.must(h["challengeK"] == 3 and not (set(cjudges) & inside) and upheld and not now_pass
                  and not c.verdict(s)["pass"],
                  f"a fresh panel of 3 of the same size (L24: {', '.join(n.name(k) for k in cjudges)}; none of its "
                  f"judges) reversed it: pass -> fail")
        b = x["bounty"]
        self.must(n.bounty_state(b) == SV.OPEN and not c.award(b, 1)["merged"] and self.head() == head,
                  f"the award was clawed back and bounty {b} is open again; Heads.head is still {head[:12]}")
        self.ctl("merge", "--bounty", b, as_="solver-b", expect_fail="is Open")
        rad.sync("a")
        names, _ = self.delegates()
        self.must(all(rad.canonical(y, "a") == head for y in NODES) and all(
            not self.rad.sh(y, f"git --git-dir {self.rad.store('a')} merge-base --is-ancestor {out['fix']} "
                               f"refs/heads/main && echo in", check=False) for y in names),
                  f"the bad fix {out['fix'][:12]} never reached main: canonical main is {head[:12]} on all "
                  f"{len(NODES)} nodes, and the fix isn't in it on any delegate's node")
        self.chain_t["badFix"] = {k: h[k] for k in ("wrongPassToReversal_s", "wrongPassToChallenge_s",
                                                    "challengeWaitedForAPanel_s", "panelDrawnToReversal_s",
                                                    "lapsedChallenges")}
        res.info(f"time to heal (chain time, minutes windows): {h['wrongPassToReversal_s']} s from the wrong pass to "
                 f"its reversal = {h['wrongPassToChallenge_s']} s until the watcher challenged + "
                 f"{h['challengeWaitedForAPanel_s']} s until its panel was drawn + {h['panelDrawnToReversal_s']} s from "
                 f"the draw to the verdict (seal and reveal windows)")
        self.bad = out

    def verify(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("7", "pofctl verify-head exits 0 and pofctl verify-delegates passes")
        secs = self.settle("the end")
        res.info(f"the identity is the seats' on every validator's node ({secs} s)")
        for name in ("genesis", "reporter"):
            code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c(name)}")
            self.must(code == 0, f"pofctl --v3 verify-head on {name}'s node exits {code}: {out[-200:]}")
        code, out = self.ctl_exit("verify-delegates", "--rad-exec", f"docker exec -i {rad.c('v3')}")
        self.must(code == 0, f"pofctl --v3 verify-delegates on v3's node exits {code}: {out.splitlines()[0][:200]}")

    def summary(self) -> None:
        res = self.res
        c = self.n.chain
        res.scenario("T", "the scenario's durations (chain time under the minutes windows; wall time)")
        t = self.chain_t
        res.info(f"qualification: 7 validators active {SV.hours(t['qualified'])} after the deployment "
                 f"({self.wall['qualification']} s of wall time)")
        res.info(f"step 1, registration to its check's finality: {t['registrationToFinal']} s")
        for f in self.fixes + [self.funded_fix]:
            res.info(f"{f['label']}: commit to counted {f['countedAt'] - f['committedAt']} s, claim to final "
                     f"{f['finalAt'] - f['claimedAt']} s, final to merge {f['mergedAt'] - f['finalAt']} s; "
                     f"canonical main followed in {f['followSeconds']} s of wall time")
        bad = t["badFix"]
        res.info(f"the bad fix: counted at {self.bad['countedAt'] - self.bad['committedAt']} s after its commit; "
                 f"wrong pass to reversal {bad['wrongPassToReversal_s']} s (challenged after "
                 f"{bad['wrongPassToChallenge_s']} s, panel drawn {bad['challengeWaitedForAPanel_s']} s later, verdict "
                 f"{bad['panelDrawnToReversal_s']} s after the draw)")
        res.meas["chainSeconds"] = self.chain_t
        res.meas["fixes"] = self.fixes + [self.funded_fix]
        res.meas["bad"] = getattr(self, "bad", {})
        res.meas["wallSeconds"] = self.wall
        res.meas["pofctlRuns"] = getattr(self, "ctl_runs", 0)
        res.meas["chainSecondsTotal"] = c.now() - self.n.t0
        res.ok(f"{c.panel_count()} panels drawn, {SV.hours(c.now() - self.n.t0)} of chain time, "
               f"{round(time.time() - self.started)} s of wall time, {getattr(self, 'ctl_runs', 0)} pofctl runs")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    VS.use_names(PREFIX, NODES, OUT, RECORD_DIR)
    if a.command == "clean":
        VS.clean()
        fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return Story(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
