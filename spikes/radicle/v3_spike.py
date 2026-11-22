"""The Radicle spike under v3 (proof-of-fix#251, tasks 2.1-2.5; design L9, L11, L12). Run it with
`scripts/radicle-spike.sh --v3`, which builds the node image (the pinned Radicle release, #190's Dockerfile) and calls
this file. `python3 spikes/radicle/v3_spike.py clean` removes anything a stopped run left behind.

The question: who signs Radicle's canonical `main` when v3's judges change with every draw. Two candidates run here,
side by side on one local network and one chain, each on its own Radicle repository:

  (a) repository A: the delegates are the validators seated on-chain (`Validators.isDrawable`), threshold a majority.
      Each seated node's gate (spikes/radicle/gate.sh) pushes `Heads.head` when it moves and refuses anything else;
      each node signs only an identity revision whose delegates equal the seats (oracle/delegates.py,
      `review_revision`); `verify_delegates` compares the identity document with the seats for anyone. A seat's node
      is the one its validator signed into its v3 registration (`Registration.radNode`, #251's contract change of
      2026-11-20), read from the chain (`Validators.radNodeOf`, `delegates.ChainSeatNodes`): no binding travels in the
      identity document. The repository starts with one delegate, the owner's node (`rad init`), which hands over to
      the seats.
  (b) repository B: the chain is the only truth. The owner's node stays the one delegate of convenience; anyone may
      push anything; readers take the commit `Heads.head` names from any namespace (`checkout`) and `verify_head`
      (oracle/radicle.py, what `pofctl verify-head` runs) reports the canonical `main` as a mismatch when it differs.
  (c) one merge key in approved enclaves: a desk study only (reports/radicle-spike-v2.md); oracle/keys.py has only
      the dstack (TDX) provider and no enclave key sharing exists to run.

The chain is anvil with the real v3 contracts (contracts/script/NodeV3Local.s.sol: Validators, Panels, PanelScores,
FeesV3, PoolV3, RaceV3) and real v3 node objects with the fake judge (tests/integration/suite_v3.py's network, no model
call): a genesis validator, candidates that qualify by their shadow verdicts and become seated, panels drawn for
registration checks and fixes, a validator that leaves, one slashed below the floor and topped up again. Panels'
windows are the production ones in hours (#251 L4 makes them constructor parameters; the spike keeps production's), so
the clock is moved with evm_increaseTime.

L9 (#251 task 3.5, contract batch 2): RaceV3 moves its own `Heads` only by `merge(bounty)`, once the claimed fix's
verdict is final; the claim doesn't move it. Since #251's L1 RaceV3 serves exactly one repository, fixed at its
construction: here A (its RID and the genesis commit), so A's head is the race's own `Heads`, moved by the real
`merge` (the run shows the contract refusing it before finality, and a keeper node merging at finality). B's fixes are
judged by the same race but not claimed there (B isn't the race's repository), so B's head lives in a separate v2
`Heads`, moved by one account standing in for `merge` only once B's winning verdict is final (`merge_at_finality`).
Every registration names A, the race's repository.

L6 (#251 contract batch 3): RaceV3 refuses every pledge (`TooFewActiveSolvers`) until three solvers are active, each
for 26 weeks after a fix of it was merged (the SolverBook). So the setup does what the devnet suite does (#270): three
solvers' fixes to A, raced unfunded and merged at finality, then a funded fix of about $44 (under D29's $50 for a new
identity) for the run's solver, whose $200 bounties' claims need that reputation. A's head has moved four times
before a1; the owner's node, A's one delegate until then, pushes it through its gate. The fixes pay the taxi fare
(`judgeFee` 0: FeesV3's worst-case deposit, the rest back after finality; no attempt, evaluation or appeal fee).

L12's fix source: a fix is a Radicle patch whose description carries the claim (bounty, submission, salt, solver: the
bot's pull request format). Each validator lists the patches on its own Radicle node, refuses a revision whose base
isn't `Heads.head`, takes the commit from its own node's storage, and runs the repository's tests (`test.sh`) inside
its own node's container; the fake judge labels the fix by those tests. The node objects read those patches as their
"pull requests" (`NodeHost`).

L12's registration check (#251 task 4.3, scenario r1): a reporter's node opens a Radicle issue on A, the reporter
registers it on-chain, and its node comments the claim lines on the issue (`pofctl --v3 issue register --rad-issue …
--comment`'s command, `rad issue comment`). Each validator reads the issues on its own Radicle node
(`radicle_v3.RadicleIssues` through `docker exec`), checks the claim against the on-chain registration and reporter,
and its judge (the fake: no model call) passes the issue; each receipt names the issue and the sha256 of the issue's
text and of the claim. The claim carries the reporter's signature for that issue (the owner's decision of 2026-11-20).
A second registration whose issue names it only with another wallet is sealed as failing, saying there's no signed
claim, at the seal margin: no silence. Scenario r2: a third registration's claim copied onto a junk issue with a lower
id is ignored, and the real one passes. Everywhere else the registrations' claims stay on the shared fake host, as
before.

Isolation (#190's rules): everything on a Docker network created with --internal (no route out); Radicle's `test`
network (no bootstrap nodes), no seeds, static peers connected by name; anvil on the same network. This process never
has a network path to anvil: its JSON-RPC goes through a `docker exec -i` pipe into a relay container (the pinned
python image the oracle node uses) on the internal network (`PipeRpc`). No model call, no public chain, no AWS. The
isolation evidence is checked at the end (scenario I). Results and node logs stay in .radicle-spike/v3/ (gitignored).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import seats as S  # noqa: E402
import suite_v3 as SV  # noqa: E402
from bot import logic  # noqa: E402
from e2e_node_v3 import ETH_100, keys_for, secret, simulator  # noqa: E402
from oracle import crypto, node_v3, v2, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from oracle.rpc import Reverted, Rpc, Unavailable, Wallet  # noqa: E402
from oracle.transport import OnchainExchange  # noqa: E402

P = "pof251"
NET = f"{P}-net"
IMAGE = "pof190-radicle:spike"  # spikes/radicle/Dockerfile: heartwood 1.10.3, its release checked by sha256
PY_IMAGE = "python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8"  # oracle/Dockerfile's
FOUNDRY_IMAGE = "ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
HOME_C = "/home/foundry"
VALIDATORS = ["genesis", "v1", "v2", "v3", "v4"]
NODES = ["owner", *VALIDATORS, "solver"]
RECORD_DIR = ROOT / "contracts" / "deployments" / "radicle-spike-v3"
OUT = ROOT / ".radicle-spike" / "v3"
COIN = 10**6
PLEDGE = 200
REP_PLEDGE = 105  # the solver's reputation fix: judged at about $44, under the $50 a new identity may claim (D29)
K_MAX = 7  # RaceV3's: a fix's deposit is FeesV3's worst case for K_MAX judges under the taxi fare
HOUR = 3600
REGISTERED_V = v3.VALIDATOR_REGISTERED  # its third topic is the validator's Radicle node key (#251, L11)
HEAD_T = ["(bytes32,bytes32,uint256,uint256,uint256,bytes32)"]
CONVERGE_S = 45  # how long a passive convergence is watched before a sync is forced

GENESIS_CALC = "# The spike's target (proof-of-fix#251): shell arithmetic.\nadd() { echo $(( $1 - $2 )); }\n"
FIXED_CALC = "# The spike's target (proof-of-fix#251): shell arithmetic.\nadd() { echo $(( $1 + $2 )); }\n"
# A's fixes after add()'s each add one function and its check to what A's head has (`Spike.a_files`); B only fixes
# add().
FUNCS = {
    "neg": ("neg() { echo $(( 0 - $1 )); }", 'check "neg 4" "$(neg 4)" -4'),
    "sq": ("sq() { echo $(( $1 * $1 )); }", 'check "sq 3" "$(sq 3)" 9'),
    "mul": ("mul() { echo $(( $1 * $2 )); }", 'check "mul 2 3" "$(mul 2 3)" 6'),
    "max": ("max() { if [ $1 -gt $2 ]; then echo $1; else echo $2; fi; }", 'check "max 2 5" "$(max 2 5)" 5'),
    "sub": ("sub() { echo $(( $1 - $2 )); }", 'check "sub 5 3" "$(sub 5 3)" 2'),
}
TEST = """#!/usr/bin/env bash
# The repository's tests (proof-of-fix#251's spike target): exit 0 when every check passes.
set -u
. ./calc.sh
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got $2, want $3"; fail=1; fi; }
check "add 2 3" "$(add 2 3)" 5
%s
exit $fail
"""
GENESIS_TEST = TEST % ""


def files_with(funcs: list) -> dict:
    """calc.sh and test.sh with add() fixed and `funcs` (FUNCS' names) added, each with its check."""
    return {"calc.sh": FIXED_CALC + "".join(FUNCS[f][0] + "\n" for f in funcs),
            "test.sh": TEST % "\n".join(FUNCS[f][1] for f in funcs)}


RELAY = r"""
import json, sys, urllib.request
for line in sys.stdin:
    try:
        req = urllib.request.Request("http://anvil:8545", data=line.encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            out = json.loads(r.read())
    except Exception as e:
        out = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "relay: %s: %s" % (type(e).__name__, str(e)[:200])}}
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()
"""


def use_names(prefix: str, nodes: list, out: Path, record_dir: Path) -> None:
    """Another run of this harness beside the spike (tests/integration/suite_v3_radicle.py, #251 task 4.6): its own
    container and network names, Radicle nodes, results folder and deployment record, so neither run's clean-up
    touches the other's."""
    global P, NET, NODES, OUT, RECORD_DIR
    P, NET, NODES, OUT, RECORD_DIR = prefix, f"{prefix}-net", list(nodes), out, record_dir


def log(msg: str) -> None:
    print(msg, flush=True)


def docker(*args, check: bool = True, input: str | None = None, timeout: float = 600) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, input=input, timeout=timeout,
                       stdin=None if input is not None else subprocess.DEVNULL)
    if check and r.returncode:
        raise RuntimeError(f"docker {' '.join(args[:4])}...: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-600:]}")
    return r.stdout.strip()


def clean() -> None:
    ids = docker("ps", "-aq", "--filter", f"name=^{P}-", check=False).split()
    if ids:
        docker("rm", "-f", *ids, check=False)
    docker("network", "rm", NET, check=False)
    shutil.rmtree(RECORD_DIR, ignore_errors=True)


def leftovers() -> str:
    return " ".join(docker("ps", "-aq", "--filter", f"name=^{P}-", check=False).split()
                    + docker("network", "ls", "-q", "--filter", f"name=^{NET}$", check=False).split())


class PipeRpc(Rpc):
    """JSON-RPC to anvil through `docker exec -i <relay> python3`: one line out, one line back. This process has no
    network path to the internal network; only this pipe."""

    def __init__(self, container: str) -> None:
        super().__init__("http://anvil:8545 (through a docker exec pipe)", timeout=120)
        self.p = subprocess.Popen(["docker", "exec", "-i", container, "python3", "-I", "-u", "-c", RELAY],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                  bufsize=1)
        self.lock = threading.Lock()
        self.calls = 0

    def _exchange(self, body: bytes) -> dict:
        with self.lock:
            self.p.stdin.write(body.decode() + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
            self.calls += 1
        if not line:
            raise Unavailable("the relay to anvil closed")
        return json.loads(line)

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:  # noqa: BLE001 (the container is about to go anyway)
            self.p.kill()


# ---------------------------------------------------------------------------------------------------------------------
# Results


class Results:
    def __init__(self) -> None:
        self.order: list = []
        self.title: dict = {}
        self.result: dict = {}
        self.lines: dict = {}
        self.cur = ""
        self.meas: dict = {}
        self.notes: dict = {}

    def scenario(self, key: str, title: str) -> None:
        self.cur = key
        if key not in self.result:
            self.order.append(key)
            self.title[key] = title
            self.result[key] = "PASS"
            self.lines[key] = []
        log(f"\n=== {key}. {title}")

    def ok(self, what: str) -> None:
        self.lines[self.cur].append("ok   " + what)
        log("  ok   " + what)

    def bad(self, what: str) -> None:
        self.lines[self.cur].append("FAIL " + what)
        self.result[self.cur] = "FAIL"
        log("  FAIL " + what)

    def info(self, what: str) -> None:
        self.lines[self.cur].append("     " + what)
        log("       " + what)

    def expect(self, what: str, got, want) -> bool:
        if got == want:
            self.ok(f"{what}: {got}")
            return True
        self.bad(f"{what}: got {got!r}, want {want!r}")
        return False

    def check(self, cond: bool, what: str) -> bool:
        (self.ok if cond else self.bad)(what)
        return bool(cond)


# ---------------------------------------------------------------------------------------------------------------------
# Radicle


class Rad:
    """The local Radicle network: one container per node on the internal network, two repositories (a, b)."""

    def __init__(self) -> None:
        self.did: dict = {}
        self.rid: dict = {}
        self.started: list = []
        self.offline: set = set()

    @staticmethod
    def c(n: str) -> str:
        return f"{P}-{n}"

    def sh(self, n: str, script: str, check: bool = True, timeout: float = 240, input: str | None = None) -> str:
        args = ["exec"] + (["-i"] if input is not None else []) + ["-w", HOME_C, self.c(n), "bash", "-c", script]
        return docker(*args, check=check, input=input, timeout=timeout)

    def start(self, n: str) -> None:
        docker("run", "-d", "--name", self.c(n), "--hostname", n, "--network", NET, "--network-alias", n, IMAGE)
        self.did[n] = self.sh(n, f"node-init.sh {n} 2>/dev/null")
        self.started.append(n)

    def connect(self, a: str, b: str) -> None:
        self.sh(a, f"rad node connect {R.nid(self.did[b])}@{b}:8776 >/dev/null 2>&1 || true", check=False)

    def online(self, nodes=None) -> list:
        return [n for n in (nodes or self.started) if n not in self.offline]

    def store(self, repo: str) -> str:
        return f"$RAD_HOME/storage/{self.rid[repo][4:]}"

    @staticmethod
    def wd(repo: str) -> str:
        return f"{HOME_C}/repo-{repo}"

    def canonical(self, n: str, repo: str) -> str:
        return self.sh(n, f"git --git-dir {self.store(repo)} rev-parse --verify -q refs/heads/main || echo none",
                       check=False)

    def tips(self, n: str, repo: str) -> dict:
        """Node ID -> that namespace's signed `main`, as node `n` has it."""
        out = self.sh(n, f"git --git-dir {self.store(repo)} for-each-ref --format='%(refname) %(objectname)' "
                         f"'refs/namespaces/*/refs/heads/main'", check=False)
        tips = {}
        for line in out.splitlines():
            m = re.match(r"^refs/namespaces/([^/]+)/refs/heads/main ([0-9a-f]{40})$", line.strip())
            if m:
                tips[m.group(1)] = m.group(2)
        return tips

    def sync(self, repo: str, nodes=None, mode: str = "fetch") -> None:
        """`rad sync --<mode> <RID>` on each online node (oracle/radicle.py's lines: the RID positional, a failure
        reported, not hidden)."""
        for n in self.online(nodes):
            err = R.sync_error(self.sh(n, R.sync_lines(self.rid[repo], mode, 60), check=False))
            if err:
                log(f"  warn {n}: {err}")

    def id_cob(self, n: str, repo: str) -> dict:
        rid = self.rid[repo]
        out = self.sh(n, f"rad cob show --repo {rid} --type xyz.radicle.id --object "
                         f"\"$(rad cob list --repo {rid} --type xyz.radicle.id | head -1)\"")
        return json.loads(out.splitlines()[0])

    def identity(self, n: str, repo: str) -> tuple:
        cob = self.id_cob(n, repo)
        return cob["current"], cob["revisions"][cob["current"]]["doc"], cob

    def patches(self, n: str, repo: str) -> list:
        rid = self.rid[repo]
        cobs = []
        for pid in self.sh(n, f"rad cob list --repo {rid} --type xyz.radicle.patch").split():
            cob = json.loads(self.sh(n, f"rad cob show --repo {rid} --type xyz.radicle.patch --object {pid}")
                             .splitlines()[0])
            cob["_id"] = pid
            cobs.append(cob)
        return cobs

    def gate(self, n: str, repo: str, fix: str, heads: str, repo_id: bytes) -> tuple:
        """The seated node's chain gate (spikes/radicle/gate.sh): (exit code, its output)."""
        r = subprocess.run(["docker", "exec", "-w", HOME_C, "-e", "RPC=http://anvil:8545", "-e", f"HEADS={heads}",
                            "-e", f"REPO_ID=0x{repo_id.hex()}", "-e", f"RID={self.rid[repo]}",
                            "-e", f"REPO_DIR={self.wd(repo)}", self.c(n), "gate.sh", fix],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=240)
        return r.returncode, (r.stderr + r.stdout).strip().replace("\n", " | ")

    def push_main(self, n: str, repo: str, sha: str) -> None:
        """Node `n` pushes its own signed main to `sha` with no check at all: what Radicle alone allows."""
        self.sh(n, f"cd {self.wd(repo)} && {{ git cat-file -e {sha}^{{commit}} 2>/dev/null || "
                   f"git fetch -q {self.store(repo)} {sha}; }} && git push -q -f rad {sha}:refs/heads/main 2>/dev/null")

    def commit_on(self, n: str, repo: str, base: str, files: dict, what: str) -> str:
        wd = self.wd(repo)
        self.sync(repo, [n])
        self.sh(n, f"cd {wd} && {{ git cat-file -e {base}^{{commit}} 2>/dev/null || "
                   f"git fetch -q {self.store(repo)} {base}; }} && git checkout -q -B work {base}")
        for path, text in files.items():
            self.sh(n, f"cat > {wd}/{path}", input=text)
        return self.sh(n, f"cd {wd} && git add -A && git commit -q -m {shlex.quote(what + ' (proof-of-fix#251)')} && "
                          f"git rev-parse HEAD")

    def open_patch(self, n: str, repo: str, sha: str, messages: list) -> str:
        opts = " ".join(f"-o patch.message={shlex.quote(m)}" for m in messages)
        out = self.sh(n, f"cd {self.wd(repo)} && git checkout -q -B p-{sha[:12]} {sha} && "
                         f"git push rad HEAD:refs/patches {opts} 2>&1")
        m = re.search(r"Patch ([0-9a-f]{40}) opened", out)
        if not m:
            raise RuntimeError(f"{n}: no patch opened: {out[-300:]}")
        return m.group(1)

    def export(self, n: str, repo: str, sha: str, dest: Path) -> bool:
        """The commit's tree, from node `n`'s own storage, into `dest` (the node object's checkout)."""
        r = subprocess.run(["docker", "exec", self.c(n), "bash", "-c",
                            f"git --git-dir {self.store(repo)} archive --format=tar {sha}"],
                           capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
        if r.returncode:
            return False
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as t:
            t.extractall(dest, filter="data")
        return True

    def run_tests(self, n: str, repo: str, sha: str) -> tuple:
        """The repository's tests on the commit as node `n`'s own storage has it, inside node `n`'s container."""
        r = subprocess.run(["docker", "exec", "-w", HOME_C, self.c(n), "bash", "-c",
                            f"set -e; d=$(mktemp -d); git --git-dir {self.store(repo)} archive {sha} | tar -x -C $d; "
                            f"cd $d && bash test.sh"], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=120)
        return r.returncode, r.stdout, r.stderr

    def snapshot(self, n: str, repo: str, sync: bool = True) -> R.Snapshot:
        return R.Radicle(self.rid[repo], ["docker", "exec", "-i", self.c(n)], self.wd(repo)).snapshot(sync=sync)

    def checkout(self, n: str, repo: str, head: str) -> tuple:
        """(b)'s reader: the commit Heads.head names, from whichever namespace on node `n` has it (fetched from the
        network first if it isn't there), checked out by its hash. What `pofctl checkout` should do (task 4.4).
        Returns (HEAD of the checkout, the namespaces holding it, the tests' exit code)."""
        s = self.store(repo)
        out = self.sh(n, f"""set -e
if ! git --git-dir {s} cat-file -e {head}^{{commit}} 2>/dev/null; then
{R.sync_lines(self.rid[repo], 'fetch', 60)}
fi
git --git-dir {s} cat-file -e {head}^{{commit}}
d=$HOME/checkout-{repo}; rm -rf $d; git init -q $d; git -C $d fetch -q {s} {head}; git -C $d checkout -q --detach FETCH_HEAD
echo "@head $(git -C $d rev-parse HEAD)"
echo "@ns $(git --git-dir {s} for-each-ref --contains {head} --format='%(refname)' refs/namespaces | sed -n 's#^refs/namespaces/\\([^/]*\\)/.*#\\1#p' | sort -u | tr '\\n' ' ')"
cd $d; bash test.sh >/dev/null 2>&1 && echo "@tests 0" || echo "@tests $?"
""", check=False)
        got = dict(re.findall(r"^@(\w+) ?(.*)$", out, re.M))
        if R.sync_error(out):
            log(f"  warn {n}: {R.sync_error(out)}")
        return got.get("head", ""), got.get("ns", "").split(), got.get("tests", "")

    def stop_node(self, n: str) -> None:
        self.sh(n, "rad node stop >/dev/null 2>&1 || true", check=False)
        self.offline.add(n)

    def start_node(self, n: str) -> None:
        self.sh(n, "rad node start -- --log-level debug >/dev/null 2>&1; "
                   "for _ in $(seq 60); do rad node status >/dev/null 2>&1 && break; sleep 0.5; done")
        self.offline.discard(n)
        for peer in self.online():
            if peer != n:
                self.connect(n, peer)

    def fresh_clone(self, viewer: str, repo: str) -> tuple:
        """A brand-new node clones the repository from the network: (its HEAD, the command output to record)."""
        self.start(viewer)
        for peer in self.online():
            if peer != viewer:
                self.connect(viewer, peer)
        rid = self.rid[repo]
        out = self.sh(viewer, f"for _ in 1 2 3 4 5; do rad clone {rid} fresh --no-confirm >/dev/null 2>&1 && break; "
                              f"rm -rf fresh; sleep 1; done; cd fresh && echo \"\\$ git rev-parse HEAD\" && "
                              f"git rev-parse HEAD && echo '$ git log --oneline -1' && git log --oneline -1 && "
                              f"echo '$ rad patch list --all' && rad patch list --all 2>&1", check=False)
        head = next((x for x in out.splitlines() if re.fullmatch(r"[0-9a-f]{40}", x.strip())), "")
        return head, out


# ---------------------------------------------------------------------------------------------------------------------
# The chain's side: v3's network (suite_v3's Net) with validators that read fixes from their own Radicle node


class NodeHost:
    """A validator's repository host: the registrations' claims (the shared fake host) and, as its pull requests, the
    patches its own Radicle node has (set by `Spike.prefetch`)."""

    def __init__(self, shared) -> None:
        self.shared = shared
        self.found: list = []

    def pulls(self, state="all"):
        return list(self.found)

    def __getattr__(self, name):
        return getattr(self.shared, name)


class Validator(SV.Node):
    mute_all = False  # down for every panel (to be slashed for silence)

    def _take(self, pid: int) -> bool:
        if self.mute_all:
            self.finished.add(pid)
            return False
        return super()._take(pid)


class SpikeNet(SV.Net):
    def __init__(self, rpc, record, work, spike) -> None:
        self.spike = spike
        super().__init__(rpc, record, work, verbose=False)
        # each validator registers its own Radicle node's key (#251, L11): the seat-to-node link is on-chain
        self.rad_nodes = {n: D.key_from_did(spike.rad.did[n]) for n in VALIDATORS}

    def make_node(self, name: str, family: str, keeper: bool = False, tag: str = "") -> Validator:
        keys = keys_for(self.sim, name)
        wallet = Wallet(self.rpc, keys.account_secret(), name)
        me = keys.address()
        self.names[me.lower()] = name
        return Validator(self.chain, keys, FakeJudge(family=family), NodeHost(self.host), "pof-v3-spike",
                         self.work / "src" / name, OnchainExchange(self.chain, keys, wallet=wallet),
                         Store(self.work / "receipts"), runner=lambda argv, name=name: self.spike.tests(name, argv),
                         log=self.log(name + tag), wallet=wallet,
                         rounds=Rounds(self.work / "rounds", self.chain.chain_id(), self.chain.race, me + tag),
                         keeper=keeper, costs={"vcpu_second": 12_000_000, "gb_second": 1_300_000} if keeper else None,
                         seal_margin=3 * HOUR)


def topic(sig: str) -> str:
    return "0x" + crypto.keccak256(sig.encode()).hex()


class Spike:
    def __init__(self, keep: bool) -> None:
        self.keep = keep
        self.res = Results()
        self.rad = Rad()
        self.rpc: PipeRpc | None = None
        self.n: SpikeNet | None = None
        self.sha_repo: dict = {}
        self.test_runs: list = []  # (validator, repo, sha, exit code)
        self.fetches: list = []  # (validator, repo, sha, patch, base ok)
        self.a_funcs: list = []  # the functions A's head has beyond add() (FUNCS' names)
        self.started = time.time()

    # ---------- infrastructure ----------

    def up(self) -> None:
        res, rad = self.res, self.rad
        solc = os.environ.get("POF_SOLC", "")
        if not solc or not (ROOT / solc).is_file():
            raise RuntimeError("POF_SOLC (the pinned solc, scripts/solc.sh) is missing: run scripts/contracts.sh setup")
        docker("network", "create", "--internal", NET)
        uid = f"{os.getuid()}:{os.getgid()}"
        docker("run", "-d", "--name", f"{P}-anvil", "--network", NET, "--network-alias", "anvil", "--user", uid,
               "-e", "HOME=/tmp", "-v", f"{ROOT}/contracts:/work", "-v", f"{ROOT}/{solc}:/opt/solc/solc:ro",
               "-w", "/work", "--entrypoint", "anvil", FOUNDRY_IMAGE, "--host", "0.0.0.0", "--port", "8545",
               "--chain-id", "31337", "--silent")
        docker("run", "-d", "--name", f"{P}-relay", "--network", NET, "--entrypoint", "python3", PY_IMAGE, "-c",
               "import time; time.sleep(10**9)")
        self.rpc = PipeRpc(f"{P}-relay")
        for _ in range(120):
            try:
                if self.rpc.chain_id() == 31337:
                    break
            except Exception:  # noqa: BLE001 (anvil isn't listening yet)
                time.sleep(0.5)
        else:
            raise RuntimeError("anvil didn't answer through the relay")
        for n in NODES:
            rad.start(n)
        for i, a in enumerate(NODES):  # a full mesh among the spike's nodes, and nothing else
            for b in NODES[i + 1:]:
                rad.connect(a, b)
        self.radicle_version = rad.sh("owner", "rad --version")
        log(f"radicle: {self.radicle_version}; nodes: " + ", ".join(f"{n} {rad.did[n]}" for n in NODES))

    def deploy_v3(self, rid: str, genesis_commit: str, env: dict | None = None) -> dict:
        """v3 for one repository (#251, L1): `rid` and its genesis commit; the windows are production's. `env`: more
        of NodeV3Local's settings (LOCAL_*), or other values for these."""
        rpc = self.rpc
        sim = simulator()
        genesis = keys_for(sim, "genesis")
        deployer = secret("deployer")
        rpc.call("anvil_setBalance", [crypto.address(deployer), ETH_100])
        quote = genesis.quote(crypto.keccak256(b"genesis"))
        attestation = "0x" + crypto.keccak256(bytes.fromhex(quote.quote)).hex()
        shutil.rmtree(RECORD_DIR, ignore_errors=True)
        RECORD_DIR.mkdir(parents=True)
        keys_in = f"0x{deployer:064x}\n0x{genesis.account_secret():064x}\n"  # on stdin, never on a command line
        started = time.time()
        settings = {"LOCAL_ATTESTATION": attestation, "LOCAL_RID": rid,
                    "LOCAL_GENESIS_HEAD": f"0x{genesis_commit}{'0' * 24}",
                    "LOCAL_GENESIS_RAD_NODE": f"0x{D.key_from_did(self.rad.did['genesis']).hex()}",
                    "LOCAL_FAMILIES": ",".join(SV.FAMILIES[:6]), "LOCAL_RECORD": f"{RECORD_DIR.name}/local.json",
                    **(env or {})}
        try:
            docker("exec", "-i", "-w", "/work", *(x for k, v in settings.items() for x in ("-e", f"{k}={v}")),
                   f"{P}-anvil", "sh", "-c",
                   'read -r PK; read -r LOCAL_GENESIS_PK; export LOCAL_GENESIS_PK; forge script '
                   'script/NodeV3Local.s.sol:NodeV3LocalScript --rpc-url http://127.0.0.1:8545 --broadcast '
                   '--private-key "$PK" --slow >/tmp/deploy.log 2>&1 || { tail -30 /tmp/deploy.log >&2; exit 1; }',
                   input=keys_in, timeout=3600)
            record = json.loads((RECORD_DIR / "local.json").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(RECORD_DIR, ignore_errors=True)
        log(f"v3 deployed in {time.time() - started:.0f} s: RaceV3 {record['race']}, Validators {record['registry']}, "
            f"Panels {record['panels']}")
        return record

    def deploy_heads(self, commits: dict) -> None:
        """B's head: a v2 Heads moved only by `merger` (merge_at_finality), standing in for a race of B's own. It is
        created with A's entry too, unused: A's head is the race's (`heads_for`)."""
        self.merger = Wallet(self.rpc, secret("merger"), "merger")
        self.rpc.call("anvil_setBalance", [self.merger.address, ETH_100])
        self.repo_id = {r: R.repo_id(self.rad.rid[r]) for r in ("a", "b")}
        repos = ",".join("0x" + self.repo_id[r].hex() for r in ("a", "b"))
        heads = ",".join(f"0x{commits[r]}{'0' * 24}" for r in ("a", "b"))
        script = r"""set -e
R=http://127.0.0.1:8545
a=$(cast rpc --rpc-url $R eth_accounts | tr -d '[]" ' | cut -d, -f1)
stub=$(cast send --rpc-url $R --unlocked --from $a --create 0x6001600c60003960016000f300 --json |
  grep -o '"contractAddress":"0x[0-9a-fA-F]*"' | cut -d'"' -f4)
forge create --rpc-url $R --unlocked --from $a --broadcast src/v2/Heads.sol:Heads \
  --constructor-args "$stub" "[$1]" "[$2]" "$3" "$4" 2>/dev/null | sed -n 's/^Deployed to: //p'"""
        self.heads = docker("exec", "-w", "/work", f"{P}-anvil", "bash", "-c", script, "x", repos, heads,
                            "0x" + crypto.keccak256(b"proof-of-fix#251 spike constitution").hex(), self.merger.address,
                            timeout=1200)
        if not re.fullmatch(r"0x[0-9a-fA-F]{40}", self.heads):
            raise RuntimeError(f"Heads wasn't deployed: {self.heads!r}")
        log(f"Heads (B's stand-in) {self.heads}: mover {self.merger.address}")

    def heads_for(self, repo: str) -> str:
        """Where `repo`'s head lives: A's in the race's own Heads (moved by `merge`, L9), B's in the stand-in."""
        return self.n.chain.heads if repo == "a" else self.heads

    def head(self, repo: str) -> str:
        word = self.rpc.view(self.heads_for(repo), "head(bytes32)", HEAD_T, self.repo_id[repo])[0][0]
        return R.sha_of(v3.b32(word))

    # ---------- the repositories ----------

    def repos(self) -> str:
        rad = self.rad
        rad.sh("owner", "mkdir -p g && cd g && git init -q -b main")
        rad.sh("owner", "cat > g/calc.sh", input=GENESIS_CALC)
        rad.sh("owner", "cat > g/test.sh", input=GENESIS_TEST)
        genesis = rad.sh("owner", "cd g && git add -A && git commit -q -m 'genesis: add() is wrong (proof-of-fix#251)' "
                                  "&& git rev-parse HEAD")
        for r, what in (("a", "candidate (a): the seated validators are the delegates"),
                        ("b", "candidate (b): the chain is the only truth")):
            rad.sh("owner", f"git clone -q g repo-{r} && cd repo-{r} && git remote remove origin && "
                            f"rad init --name pof-v3-{r} --description {shlex.quote(what + ' (proof-of-fix#251)')} "
                            f"--default-branch main --public --no-confirm >/dev/null 2>&1")
            rad.rid[r] = rad.sh("owner", f"cd repo-{r} && rad .")
            if not R.RID_RE.match(rad.rid[r]):
                raise RuntimeError(f"rad init gave no RID: {rad.rid[r]!r}")
        for n in NODES[1:]:
            for r in ("a", "b"):
                for _ in range(15):
                    rad.sh(n, f"rad clone {rad.rid[r]} repo-{r} --no-confirm >/dev/null 2>&1 || rm -rf repo-{r}",
                           check=False)
                    if rad.sh(n, f"test -d repo-{r}/.git && echo yes", check=False) == "yes":
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError(f"{n} couldn't clone {rad.rid[r]}")
        log(f"repositories: A {rad.rid['a']}, B {rad.rid['b']}; genesis {genesis}")
        return genesis

    # ---------- the validators' fix source (L12) and their tests ----------

    def tests(self, name: str, argv: list) -> tuple:
        text = " ".join(str(a) for a in argv)
        m = re.search(r"/src/[^/ ]+/([0-9a-f]{40})", text)
        sha = m.group(1) if m else ""
        repo = self.sha_repo.get(sha)
        if repo is None:
            return 1, "", f"unknown commit {sha!r}"
        code, out, err = self.rad.run_tests(name, repo, sha)
        self.test_runs.append((name, repo, sha, code))
        return code, out, err

    def prefetch(self, repo: str, want_sha: str, names) -> dict:
        """Each validator lists the patches on its own Radicle node, refuses a revision whose base isn't Heads.head,
        and takes the commit's tree from its own node's storage. Returns name -> what it found."""
        head = self.head(repo)
        got = {}
        for name in names:
            node = self.n.nodes[name]
            for _ in range(10):
                self.rad.sync(repo, [name])
                pulls = S.patch_pulls(self.rad.patches(name, repo))
                if any(p["head_sha"] == want_sha for p in pulls):
                    break
                time.sleep(1)
            usable = []
            for p in pulls:
                if p["base_sha"] != head:
                    self.fetches.append((name, repo, p["head_sha"], p["patch"], False))
                    continue
                dest = node.src_root / p["head_sha"]
                if dest.is_dir() or self.rad.export(name, repo, p["head_sha"], dest):
                    self.sha_repo[p["head_sha"]] = repo
                    usable.append(p)
                    self.fetches.append((name, repo, p["head_sha"], p["patch"], True))
            node.host.found = usable
            got[name] = [p["head_sha"] for p in usable]
        return got

    # ---------- seats and their nodes (on-chain) ----------

    def seats(self) -> list:
        """The validators seated on-chain: every registered key that `isDrawable` (read from the chain only)."""
        c = self.n.chain
        keys = {"0x" + x["topics"][1][-40:] for x in self.rpc.logs(c.registry, 0, [topic(REGISTERED_V)])}
        return sorted(crypto.checksum(k) for k in keys
                      if self.rpc.view(c.registry, "isDrawable(address)", ["bool"], k)[0])

    def name_of(self, addr: str) -> str:
        return self.n.names.get(addr.lower(), addr[:10])

    def nodes(self) -> D.ChainSeatNodes:
        """The seat-to-node mapping from the chain: each seat's node key as its registration signed it."""
        return D.ChainSeatNodes.of(self.n.chain)

    def verify_delegates(self, n: str, repo: str) -> tuple:
        _, doc, _ = self.rad.identity(n, repo)
        return D.verify_delegates(doc, self.seats(), self.nodes())

    def verify_head(self, n: str, repo: str) -> tuple:
        """What `pofctl verify-head --rid` decides (oracle/radicle.py verify_head), with the head read from L9's
        stand-in: (exit code, reason naming both commits)."""
        snap = self.rad.snapshot(n, repo, sync=True)  # oracle/radicle.py's own sync: `rad sync --fetch <RID>`
        if snap.sync_error:
            log(f"  warn {n}: {snap.sync_error}")
        d = R.verify_head(self.head(repo), snap)
        return (0 if d.action == R.SIGN else 1), d.reason

    def propose(self, by: str, repo: str, title: str, seats_to_did: dict | None = None, extra: list | None = None) -> str:
        """`by` proposes the identity revision whose delegates are the seats' nodes as the chain records them (or
        `seats_to_did` as given), with a majority threshold. Returns the revision id."""
        rad = self.rad
        rad.sync(repo, [by])
        _, cur, _ = rad.identity(by, repo)
        if seats_to_did is None:
            nodes = self.nodes()
            seats_to_did = {a: nodes.node_of(a) for a in self.seats()}
        args = D.update_args(cur, seats_to_did) + (extra or [])
        self._signed_at = time.time()
        out = rad.sh(by, f"cd {rad.wd(repo)} && rad id update --title {shlex.quote(title)} --description "
                         f"{shlex.quote(title + ' (proof-of-fix#251)')} {' '.join(shlex.quote(a) for a in args)} "
                         f"--no-confirm 2>&1", check=False)
        rad.sync(repo, [by], "announce")
        cob = rad.id_cob(by, repo)
        mine = [r for r in cob["revisions"].values() if r and r.get("title") == title]
        if not mine:
            raise RuntimeError(f"{by}: no revision {title!r}: {out[-400:]}")
        return max(mine, key=lambda r: r["timestamp"])["id"]

    def review(self, n: str, repo: str, rev: str) -> tuple:
        """Node `n` reviews revision `rev` by seats.review_revision and signs its verdict (accept or reject)."""
        rad = self.rad
        rad.sync(repo, [n])
        cob = rad.id_cob(n, repo)
        cur = cob["revisions"][cob["current"]]["doc"]
        prop = cob["revisions"].get(rev)
        if not prop:
            return None, "the revision isn't on this node"
        ok, why = D.review_revision(cur, prop["doc"], self.seats(), self.nodes(), rad.tips(n, repo), self.head(repo))
        verb = "accept" if ok else "reject"
        self._signed_at = time.time()
        out = rad.sh(n, f"cd {rad.wd(repo)} && rad id {verb} {rev} --no-confirm 2>&1", check=False)
        rad.sync(repo, [n], "announce")
        if "rror" in out:
            why += f" ({verb} said: {out.strip()[-200:]})"
        return ok, why

    def watch(self, nodes, probe, want, timeout: float = CONVERGE_S, start: float | None = None) -> dict:
        """Each node in its own thread: seconds from `start` (default now) until probe(node) == want, with no sync
        forced (None: not by then)."""
        start = start or time.time()
        got: dict = {}

        def one(n):
            while time.time() - start < timeout:
                try:
                    if probe(n) == want:
                        got[n] = round(time.time() - start, 2)
                        return
                except Exception:  # noqa: BLE001 (a node mid-update)
                    pass
                time.sleep(0.2)
            got[n] = None

        ts = [threading.Thread(target=one, args=(n,)) for n in nodes]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return got

    def converge(self, key: str, repo: str, probe, want, what: str, start: float | None = None) -> None:
        """Measures convergence on every online node from `start` (the moment the deciding signature or push began:
        it includes that command, whose announcement waits for peers to fetch), with no sync forced; forces a sync on
        any node still behind after CONVERGE_S; records both."""
        res = self.res
        nodes = self.rad.online([n for n in NODES if n in self.rad.started])
        got = self.watch(nodes, probe, want, start=start)
        late = [n for n, s in got.items() if s is None]
        if late:
            self.rad.sync(repo, late)
            forced = {n: probe(n) == want for n in late}
        else:
            forced = {}
        times = [s for s in got.values() if s is not None]
        self.res.meas.setdefault("convergence", []).append(
            {"what": what, "scenario": key, "nodes": len(nodes), "passive": len(times),
             "maxSeconds": max(times) if times else None, "perNode": got, "forcedSyncOk": forced})
        res.info(f"convergence ({what}): {len(times)} of {len(nodes)} nodes without a forced sync, the last after "
                 f"{max(times) if times else '-'} s" + (f"; after a forced sync: {forced}" if late else ""))
        res.check(all(forced.values()), f"every online node has it ({what})")

    def change(self, key: str, by: str, reviewers: list, title: str) -> dict:
        """One seat change on A: `by` proposes delegates = seats; the reviewers sign by the rule until it's accepted.
        Records the identity operations and the convergence."""
        res, rad = self.res, self.rad
        _, before, _ = rad.identity(by, "a")
        rev = self.propose(by, "a", title)
        start = self._signed_at
        verdicts = 1  # the author's own acceptance comes with the proposal
        if rad.id_cob(by, "a")["current"] != rev:
            for r in reviewers:
                ok, why = self.review(r, "a", rev)
                res.info(f"{r} reviews {rev[:7]}: {'accept' if ok else 'reject'} ({why})")
                verdicts += 1
                start = self._signed_at
                if rad.id_cob(r, "a")["current"] == rev:  # the quorum, as the last signer's own node sees it
                    break
        accepted_at = start
        self.converge(key, "a", lambda n: rad.id_cob(n, "a")["current"], rev, f"identity revision {rev[:7]}",
                      start=start)
        cur, after, cob = rad.identity(by, "a")
        res.expect(f"identity on {by}: current revision", cur[:7], rev[:7])
        op = {"scenario": key, "title": title, "delegatesBefore": len(before["delegates"]),
              "thresholdBefore": before["threshold"], "delegatesAfter": len(after["delegates"]),
              "thresholdAfter": after["threshold"], "revisions": 1,
              "signatures": sum(1 for v in cob["revisions"][rev]["verdicts"].values() if "Accept" in v),
              "verdictsAsked": verdicts, "acceptedIn": round(accepted_at - self._t, 2)}
        res.meas.setdefault("seatChanges", []).append(op)
        res.info(f"identity operations: 1 revision, {op['signatures']} signatures (the threshold in force was "
                 f"{op['thresholdBefore']} of {op['delegatesBefore']}); now {op['delegatesAfter']} delegates, "
                 f"threshold {op['thresholdAfter']}")
        return op

    def mark(self) -> None:
        self._t = time.time()

    # ---------- bounties: the race, the panel, finality and the stand-in merge ----------

    def wait_registration(self, s: int) -> None:
        c = self.n.chain
        self.n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL, v3.HELD), f"registration check {s} judged",
                     poke=True)
        self.n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"registration check {s} final", poke=True)

    def a_files(self, func: str) -> dict:
        """A fix of A that adds `func` (FUNCS) to what A's head has."""
        return files_with(self.a_funcs + [func])

    def solver_line(self, w: Wallet) -> str:
        """`w`'s standing in the SolverBook (D29): reputation, open claims and cap, in dollars."""
        rep, open_, cap = (self.rpc.view(self.book, f"{f}(address)", ["uint256"], w.address)[0] / COIN
                           for f in ("reputation", "openClaims", "capOf"))
        return f"{w.role}: reputation {rep:,.2f}, open claims {open_:,.2f}, cap {cap:,.2f}"

    def bounty(self, repo: str, label: str, files: dict, judges: list, pledge: int = PLEDGE,
               solver: Wallet | None = None, issue: int | None = None, b: int | None = None,
               kind: str = "bounties") -> dict:
        """A fix of `repo` through v3: a registration made final (unless `issue` is), a bounty opened (unless `b` is)
        and funded with `pledge` (0: raced unfunded, as before three solvers are active, L6), `solver`'s (default the
        run's) sealed fix opened as a Radicle patch, drawn and judged by validators reading it from their own nodes,
        claimed, final, then merged (L9: A's by the race's `merge`, B's by the stand-in). Returns what happened."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        w = solver or n.solver
        if issue is None:
            issue, s_reg = n.register_issue()
            self.wait_registration(s_reg)
        if b is None:
            b = n.open_bounty(issue)
        if pledge:
            n.funder.send(c.race, "pledge(uint256,uint256)", b, pledge * COIN)
        base = self.head(repo)
        fix = rad.commit_on("solver", repo, base, files, label)
        salt = crypto.keccak256(f"pof251 salt {label}".encode())
        fix_w, base_w = v2.commit_word(fix), v2.commit_word(base)
        w.send(c.race, "attempt(uint256)", b)
        deposit = self.rpc.view(c.fees, "maxDeposit(bytes32,uint256)", ["uint256"], c.repo(), K_MAX)[0]
        receipt = w.send(c.race, "commit(uint256,bytes32)", b, v3.fix_commitment(fix_w, base_w, salt, w.address))
        log_ = next(x for x in receipt["logs"] if x["topics"][0] == topic(v3.COMMITTED))
        s = int(log_["topics"][2], 16)
        sub = c.submission(s)
        res.check(sub["deposit"] + sub["charged"] == deposit and deposit > 0,
                  f"the taxi fare: {w.role}'s submission {s} posted FeesV3's deposit for K_MAX judges "
                  f"({deposit / COIN:,.2f}), no flat fee, no attempt fee; its claim of "
                  f"{c.verdict(s)['bounty'] / COIN:,.2f} fits its cap ({self.solver_line(w)})")
        body = logic.pr_body(100 + issue, b, s, "0x" + salt.hex(), w.address)
        patch = rad.open_patch("solver", repo, fix, [label] + [x for x in body.splitlines() if x.strip()])
        c.live[s] = True
        judged = c.verdict(s)["bounty"]
        # Four eligible, not three: a counted panel of 3 and an auditor outside it. With exactly three, an audit that
        # falls due (AUDIT_RATE_BPS) can never be drawn, the verdict never becomes final, and the keeper's
        # drawAudits retries after every registry change (a development run of this spike stalled so).
        need = n.bond_for(judged)
        for name in judges:
            n.top_up(name, need)
        res.info(f"bounty {b} on {repo.upper()}: fix {fix[:12]} on base {base[:12]} (= Heads.head), sealed as "
                 f"submission {s}, opened as patch {patch[:7]} by the solver's node; judged at "
                 f"{judged / COIN:,.2f}, bonds topped up to {need / COIN:,.2f} for {', '.join(judges)}")
        found = self.prefetch(repo, fix, list(n.nodes))
        res.check(all(fix in v for v in found.values()),
                  f"every validator's node found the patch on its own Radicle node, its base = Heads.head, and took "
                  f"the commit from its own storage ({', '.join(sorted(found))})")
        runs_before = len(self.test_runs)
        n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s)["paid"],
                f"fix {label} judged", poke=True)
        drawn = [self.name_of(k) for k in n.panel.drawn(s)]
        runs = [r for r in self.test_runs[runs_before:] if r[2] == fix]
        res.check(c.verdict(s)["pass"] and n.bounty_state(b) == SV.WON and c.bounty(b)["winner"] == s,
                  f"a counted panel of {len(drawn)} ({', '.join(drawn)}) passed it; bounty {b} is won by submission {s}")
        res.check(bool(runs) and {r[0] for r in runs} >= set(drawn) and all(r[3] == 0 for r in runs),
                  "2.5: each drawn validator ran the tests on the commit from its own node, in its own node's "
                  f"container ({', '.join(f'{r[0]}: exit {r[3]}' for r in runs)}), and the fake judge followed them")
        if repo == "a":  # the race's one repository (L1): claimed there; B's fix isn't (its base isn't the race's head)
            w.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b, fix_w, base_w, salt)
        claimed_at = c.now()
        moved, why = self.merge_at_finality(repo, b, s, fix, base)
        res.check(not moved, f"L9: Heads doesn't move at the claim, before finality ({why})")
        res.expect(f"Heads.head({repo.upper()}) still the base", self.head(repo)[:12], base[:12])
        n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"fix {label} final", poke=True)
        final_at = c.verdict(s)["finalAt"]
        moved, why = self.merge_at_finality(repo, b, s, fix, base)
        res.check(moved, f"at finality Heads.head({repo.upper()}) moved to the fix ({why})")
        res.expect(f"Heads.head({repo.upper()})", self.head(repo)[:12], fix[:12])
        out = {"repo": repo, "bounty": b, "submission": s, "fix": fix, "base": base, "patch": patch, "drawn": drawn,
               "k": len(drawn), "claimToFinalChainSeconds": final_at - claimed_at, "solver": w.role,
               "pledge": pledge}
        res.meas.setdefault(kind, []).append(out)
        res.info(f"chain time from claim to finality (the wait L9 adds before the head moves): "
                 f"{(final_at - claimed_at) / HOUR:,.1f} h")
        return out

    def merge_at_finality(self, repo: str, b: int, s: int, fix: str, base: str) -> tuple:
        """L9's merge: A's by the race's real `merge(bounty)` (anyone; the contract refuses it before finality, and a
        keeper node may have made it already); B's by the stand-in, only once the winning verdict is final."""
        n = self.n
        c = n.chain
        if repo == "a":
            if c.award(b, c.bounty(b)["epoch"])["merged"]:
                return True, "merged by a keeper node at finality (RaceV3.merge)"
            try:
                n.anyone.send(c.race, "merge(uint256)", b)
            except Reverted as e:
                return False, f"RaceV3.merge refused: {e.reason}"
            return True, f"RaceV3.merge({b}): {base[:12]} -> {fix[:12]}"
        v = c.verdict(s)
        if v["status"] != v3.FINAL:
            return False, f"the verdict is {v3.STATUS[v['status']]}, not Final"
        if not v["pass"] or n.bounty_state(b) != SV.WON:
            return False, "not a passed fix"
        try:
            self.merger.send(self.heads, "move(bytes32,bytes32,bytes32,uint256,uint256,bytes32)", self.repo_id[repo],
                             v2.commit_word(base), v2.commit_word(fix), b, s,
                             crypto.keccak256(f"v3 verdict {s}".encode()))
        except Reverted as e:
            return False, e.reason
        return True, f"Heads.move({repo.upper()}, {base[:12]} -> {fix[:12]})"

    def gates(self, repo: str, fix: str, nodes: list, threshold: int, key: str) -> None:
        """Seated nodes' gates push the new head one by one; canonical main moves exactly at the threshold."""
        res, rad = self.res, self.rad
        old = rad.canonical("owner", repo)
        for i, name in enumerate(nodes, 1):
            start = time.time()
            code, out = rad.gate(name, repo, fix, self.heads_for(repo), self.repo_id[repo])
            res.expect(f"{name}'s gate pushes Heads.head (exit)", code, 0)
            if i == threshold:
                self.converge(key, repo, lambda n: rad.canonical(n, repo), fix,
                              f"canonical main of {repo.upper()} after gated push {i} of {len(nodes)}", start=start)
            elif i < threshold:
                rad.sync(repo)
                res.expect(f"canonical main on owner after {i} of {threshold} pushes", rad.canonical("owner", repo)[:12],
                           old[:12])

    # ---------- the run ----------

    def run(self) -> int:
        res, rad = self.res, self.rad
        clean()
        shutil.rmtree(OUT, ignore_errors=True)
        (OUT / "work").mkdir(parents=True)
        try:
            self.scenarios()
        except Exception as e:  # noqa: BLE001 (recorded as the current scenario's failure, then cleaned up)
            res.bad(f"aborted: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            try:
                if rad.started:
                    self.isolation()
            except Exception as e:  # noqa: BLE001
                res.scenario("I", "isolation")
                res.bad(f"aborted: {type(e).__name__}: {e}")
            self.write()
            if self.rpc:
                self.rpc.close()
            if not self.keep:
                clean()
                left = leftovers()
                log(f"cleaned up: {'nothing left' if not left else 'LEFT ' + left}")
        return 0 if all(v == "PASS" for v in res.result.values()) else 1

    def scenarios(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("S", "setup (2.1): v3 on anvil, validators qualify and are seated, panels drawn, Heads at "
                          "genesis for A and B, three solvers made active (L6); isolation starts here")
        self.up()
        genesis_commit = self.repos()
        record = self.deploy_v3(self.rad.rid["a"], genesis_commit)
        self.deploy_heads({"a": genesis_commit, "b": genesis_commit})
        n = self.n = SpikeNet(self.rpc, record, OUT / "work", self)
        c = n.chain
        self.chain_id = c.chain_id()
        g = n.make_node("genesis", SV.FAMILIES[0], keeper=True)
        self.rpc.call("anvil_setBalance", [g.address, ETH_100])
        n.nodes["genesis"] = g
        res.check(c.is_active(g.address), "the genesis validator is active from the deployment")
        for i in (1, 2, 3):
            n.join(i)
        n.start = max(self.rpc.block() - 20, 0)
        t = time.time()
        made = n.grow(["v1", "v2", "v3"], 12, "v1, v2 and v3 qualify")
        acts = n.evs(c.registry, "Activated(address)")
        res.meas["qualification"] = {"checks": made, "wallSeconds": round(time.time() - t),
                                     "chainSeconds": n.when(acts[-1]) - n.t0}
        res.check(len(acts) == 3, f"v1, v2 and v3 registered, were drawn as shadows and qualified after {made} "
                                  f"registration checks ({(n.when(acts[-1]) - n.t0) / HOUR:,.0f} h of chain time)")
        res.expect("seated on-chain (isDrawable)", sorted(self.name_of(a) for a in self.seats()),
                   ["genesis", "v1", "v2", "v3"])
        self.nodes_on_chain()
        kinds = [v3.KINDS[c.panel(p)["kind"]] for p in range(1, c.panel_count() + 1)]
        res.check(kinds.count("Counted") > 0 and kinds.count("Shadow") > 0,
                  f"panels drawn: {len(kinds)} ({kinds.count('Counted')} counted, {kinds.count('Shadow')} shadow, "
                  f"{kinds.count('Audit')} audit)")
        for r in ("a", "b"):
            res.expect(f"Heads.head({r.upper()}) at genesis", self.head(r), genesis_commit)
            rad.sync(r)
            res.check(all(rad.canonical(x, r) == genesis_commit for x in NODES),
                      f"canonical main of {r.upper()} = genesis on all {len(NODES)} nodes")
        race_heads = self.rpc.view(c.race, "contracts()", ["address"] * 6 + ["uint256"])[4]
        res.expect("RaceV3's own Heads holds A only (#251 L1: one repository; B's head is the stand-in's)",
                   ["0x" + v3.b32(x).hex() for x in self.rpc.view(race_heads, "repos()", ["bytes32[]"])[0]],
                   ["0x" + self.repo_id["a"].hex()])
        self.activate()

        self.candidate_a_start()
        self.both_bounties()
        self.registration_from_radicle()
        self.outsider()
        self.seat_added()
        self.seat_removed()
        self.below_floor()
        self.offline()
        self.rogue_one()
        self.rogue_majority()
        self.limits()

    def nodes_on_chain(self) -> None:
        """#251's contract change (L11 condition 1): each seat's Radicle node key is a signed field of its v3
        registration, read from the chain by anyone; another registration naming a seat's node is refused."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        nodes = self.nodes()
        got = {self.name_of(a): nodes.node_of(a) for a in self.seats()}
        res.check(all(did == rad.did[name] for name, did in got.items()),
                  "each seat's Radicle node is on-chain as its registration signed it (Validators.radNodeOf = its "
                  "node's did:key): " + ", ".join(f"{name} {did[8:20]}…" for name, did in sorted(got.items())))
        copy = keys_for(n.sim, "copycat")
        n.fund(copy.address(), 1_000)
        try:
            node_v3.register(c, copy, Wallet(self.rpc, copy.account_secret(), "copycat"), 100 * COIN, None,
                             log=lambda m: None, proof="simulated", family=SV.FAMILIES[0], host="host-copycat",
                             image=v2.DEVNET_IMAGE, tee_type="intel-tdx", rad_node=n.rad_nodes["v1"])
            res.bad("a registration naming v1's Radicle node key landed")
        except Reverted as e:
            res.check("NodeTaken" in e.reason, f"a new key registering with v1's node key is refused ({e.reason}): "
                                               f"two seats never share a node")

    # ---------- (a) and (b), in order ----------

    def activate(self) -> None:
        """L6 (#251 contract batch 3): RaceV3 refuses pledges until ACTIVE_SOLVERS_MIN (3) solvers are active, each for
        ACTIVE_WINDOW (26 weeks) after a fix of it was merged. As the devnet suite does (#270): three solvers' fixes
        to A, raced unfunded and merged at finality, then a funded fix of about $44 (under D29's $50 for a new
        identity) gives the run's solver the reputation its $200 bounties' claims need. A's head moves four times;
        each time the owner's node, A's one delegate until a1, pushes it through its gate (`owner_follows`): a patch's
        base is where it leaves the canonical main, and a validator takes only a patch based on Heads.head."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        self.book = crypto.checksum(self.rpc.view(c.race, "solverBook()", ["address"])[0])
        cfg = c.config()
        res.check(cfg["judgeFee"] == 0 and cfg["attemptFee"] == cfg["evaluationFee"] == cfg["appealFee"] == 0,
                  f"the taxi fare (#251 contract batch 3): judgeFee {cfg['judgeFee']}, attempt, evaluation and appeal "
                  f"fees {cfg['attemptFee']}, {cfg['evaluationFee']}, {cfg['appealFee']}")
        solvers = [n.solver, n.account("second solver"), n.account("third solver")]
        regs = [n.register_issue() for _ in range(4)]
        for _, s in regs:
            self.wait_registration(s)
        b0 = n.open_bounty(regs[0][0])
        too_few = crypto.keccak256(b"TooFewActiveSolvers(uint256)")[:4].hex()
        try:
            n.funder.send(c.race, "pledge(uint256,uint256)", b0, 10 * COIN)
            res.bad("a pledge landed before three solvers were active")
        except Reverted as e:
            res.check(too_few in (e.data or "").lower() or "TooFewActiveSolvers" in e.reason,
                      f"no active solver yet: a pledge is refused (TooFewActiveSolvers, {e.reason}); the issues are "
                      f"raced unfunded")
        fixes = [(solvers[0], "fix add() on A, unfunded", files_with([]), None),
                 (solvers[1], "add neg() on A, unfunded", files_with(["neg"]), "neg"),
                 (solvers[2], "add sq() on A, unfunded", files_with(["neg", "sq"]), "sq")]
        for k, (w, label, files, func) in enumerate(fixes):
            self.bounty("a", label, files, ["v1", "v2", "v3"], pledge=0, solver=w, issue=regs[k][0],
                        b=b0 if k == 0 else None, kind="activation")
            if func:
                self.a_funcs.append(func)
            self.owner_follows()
        actives = self.rpc.view(self.book, "activeCount()", ["uint256"])[0]
        window = self.rpc.view(self.book, "ACTIVE_WINDOW()", ["uint256"])[0]
        res.check(actives == 3 and self.rpc.view(self.book, "pledgesOpen()", ["bool"])[0],
                  f"three solvers' unfunded fixes were merged: {actives} active solvers, pledges open "
                  f"(ACTIVE_SOLVERS_MIN 3, ACTIVE_WINDOW {window / (7 * 24 * HOUR):g} weeks)")
        self.bounty("a", "add mul() on A, the solver's reputation", self.a_files("mul"), ["v1", "v2", "v3"],
                    pledge=REP_PLEDGE, issue=regs[3][0], kind="activation")
        self.a_funcs.append("mul")
        rep = self.rpc.view(self.book, "reputation(address)", ["uint256"], n.solver.address)[0]
        res.check(rep > 30 * COIN, f"the solver's funded fix was merged: {self.solver_line(n.solver)}, so its "
                                   f"${PLEDGE} bounties' claims fit")
        head = self.owner_follows(converge=True)
        res.meas["activeSolvers"] = {"active": actives, "reputation": rep, "headA": head}

    def owner_follows(self, converge: bool = False) -> str:
        """Before a1 the owner's node is A's one delegate: it pushes Heads.head(A) through its gate, so the canonical
        main follows the head and the next patch is based on it. Returns the head."""
        res, rad = self.res, self.rad
        head = self.head("a")
        start = time.time()
        code, out = rad.gate("owner", "a", head, self.heads_for("a"), self.repo_id["a"])
        res.expect(f"the owner's node (A's one delegate) pushes Heads.head(A) = {head[:12]} through its gate (exit)",
                   code, 0)
        if converge:
            self.converge("S", "a", lambda x: rad.canonical(x, "a"), head, "canonical main of A after the activation",
                          start=start)
        else:
            rad.sync("a")
            res.expect("the solver's node: canonical main of A", rad.canonical("solver", "a")[:12], head[:12])
        return head

    def candidate_a_start(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("a1", "(a) the genesis delegate (the owner's node) hands over to the seats")
        ok, problems = self.verify_delegates("owner", "a")
        res.check(not ok, f"before: verify-delegates fails ({'; '.join(problems)})")
        seated = [self.name_of(a) for a in self.seats()]
        head = self.head("a")
        for name in seated:  # a new delegate must have published main first (#190): through its gate, at the head
            code, out = rad.gate(name, "a", head, self.heads_for("a"), self.repo_id["a"])
            res.expect(f"{name} publishes main at Heads.head through its gate (exit)", code, 0)
        rad.sync("a", ["owner"])
        self.mark()
        op = self.change("a1", "owner", [], "Hand over to the seats on-chain")
        _, doc, _ = rad.identity("owner", "a")
        res.check(rad.did["owner"] not in doc["delegates"], "the owner's node is no longer a delegate")
        ok, problems = self.verify_delegates("owner", "a")
        res.check(ok, f"after: verify-delegates passes ({len(doc['delegates'])} delegates = the seats, threshold "
                      f"{doc['threshold']}){'' if ok else ': ' + '; '.join(problems)}")
        res.check(op["signatures"] == 1, "one revision, one signature: the owner was the only delegate")
        res.scenario("b1", "(b) setup: the owner's node is the one delegate of convenience; nothing follows the seats")
        _, doc, cob = rad.identity("owner", "b")
        res.check(doc["delegates"] == [rad.did["owner"]] and doc["threshold"] == 1,
                  f"B: 1 delegate (the owner's node), threshold 1, {len(cob['revisions'])} revision")

    def both_bounties(self) -> None:
        res, rad, n = self.res, self.rad, self.n
        res.scenario("a2", "(a) a fix judged by a v3 panel reading it from Radicle (2.5), final, Heads moves, the "
                           "seated nodes' gates move canonical main at the threshold")
        out = self.bounty("a", "add max() on A", self.a_files("max"), ["v1", "v2", "v3"])
        self.a_funcs.append("max")
        self.fix_a1 = out["fix"]
        seated = [self.name_of(a) for a in self.seats()]
        _, doc, _ = rad.identity("owner", "a")
        self.gates("a", out["fix"], seated, doc["threshold"], "a2")
        code, why = self.verify_head("genesis", "a")
        res.expect(f"verify-head on A ({why})", code, 0)
        head, text = rad.fresh_clone("viewer-a2", "a")
        res.expect("a fresh `rad clone` of A (new node viewer-a2): HEAD", head[:12], out["fix"][:12])
        res.notes["freshCloneA"] = text
        res.notes.setdefault("patchStatusA", rad.sh("owner", f"cd {rad.wd('a')} && rad patch list --all 2>&1",
                                                    check=False))

        res.scenario("b2", "(b) a fix judged by a v3 panel reading it from Radicle (2.5), final, Heads moves; nobody "
                           "pushes: checkout follows the head, verify-head reports the stale main")
        out = self.bounty("b", "fix add() on B", {"calc.sh": FIXED_CALC}, ["v1", "v2", "v3"])
        self.fix_b1 = out["fix"]
        for name in ("solver", "v3"):
            head, ns, tests = rad.checkout(name, "b", out["fix"])
            res.expect(f"checkout on {name}'s node: HEAD = Heads.head (from namespaces "
                       f"{[self._who(x) for x in ns]}), tests exit {tests}", head[:12], out["fix"][:12])
        code, why = self.verify_head("genesis", "b")
        res.expect(f"verify-head on B: exit ({why})", code, 1)
        res.check(out["fix"] in why and rad.canonical("genesis", "b") in why, "it names both commits")
        head, text = rad.fresh_clone("viewer-b2", "b")
        res.expect("a fresh `rad clone` of B (new node viewer-b2): HEAD is still genesis, not the judged fix",
                   head[:12], out["base"][:12])
        res.notes["freshCloneBStale"] = text
        res.scenario("b3", "(b) the delegate of convenience pushes the head: verify-head passes, a fresh clone agrees")
        start = time.time()
        code, outp = rad.gate("owner", "b", out["fix"], self.heads_for("b"), self.repo_id["b"])
        res.expect("the owner's node pushes Heads.head through the same gate (exit)", code, 0)
        self.converge("b3", "b", lambda x: rad.canonical(x, "b"), out["fix"], "canonical main of B after 1 push",
                      start=start)
        code, why = self.verify_head("v3", "b")
        res.expect(f"verify-head on B ({why})", code, 0)
        head, text = rad.fresh_clone("viewer-b3", "b")
        res.expect("a fresh `rad clone` of B (new node viewer-b3): HEAD", head[:12], out["fix"][:12])
        res.notes["freshCloneBUpdated"] = text

    def rad_issue(self, n: str, repo: str, title: str, body: str) -> str:
        """Node `n` opens an issue on `repo`, announced: its id (the issue COB's)."""
        rid = self.rad.rid[repo]
        listed = f"rad cob list --repo {rid} --type xyz.radicle.issue"
        before = set(self.rad.sh(n, listed, check=False).split())
        self.rad.sh(n, f"rad issue open --repo {rid} --title {shlex.quote(title)} --description {shlex.quote(body)} "
                       f"--no-announce >/dev/null 2>&1")
        (iid,) = set(self.rad.sh(n, listed).split()) - before
        return iid

    def rad_comment(self, n: str, repo: str, iid: str, text: str) -> None:
        """What `pofctl --v3 issue register --rad-issue <id> --comment` runs on the reporter's node."""
        self.rad.sh(n, f"rad issue comment --repo {self.rad.rid[repo]} {iid} --message {shlex.quote(text)} "
                       f"--no-announce >/dev/null 2>&1")

    def signed_claim(self, w: Wallet, registration: int, iid: str) -> str:
        """The claim `pofctl --v3 issue register --rad-issue <iid> --comment` posts for `w`: the two lines and `w`'s
        signature over radicle_v3.claim_digest (this chain, the race, the registration, A's repository, the issue)."""
        c = self.n.chain
        return "\n".join(RV.signed_claim_lines(w.sign, w.address, c.chain_id(), c.race, registration, c.repo(), iid))

    def registration_from_radicle(self) -> None:
        """#251 task 4.3 (L12): the registration check reads a Radicle issue's claim, signed by the reporter for that
        issue (the owner's decision of 2026-11-20), from each validator's own node."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("r1", "(4.3) a registration claimed by a Radicle issue: each validator reads the issue on its own "
                           "Radicle node, checks the reporter's signed claim against the chain, and its judge passes "
                           "it; a claim with another wallet is sealed as failing (no signed claim), not left silent")
        bug = ("add 2 3 prints -1: add() subtracts its second argument.\n\nSteps: source calc.sh; add 2 3\n"
               "Expected: 5")
        iid = self.rad_issue("solver", "a", "add() subtracts", bug)
        issue, s = n.register_issue(claim=False)  # nothing on the fake host: the claim is on Radicle only
        claim = self.signed_claim(n.reporter, issue, iid)
        self.rad_comment("solver", "a", iid, claim)
        other = self.rad_issue("solver", "a", "add() is slow", "add() takes a while on big numbers.")
        issue_w, s_w = n.register_issue(claim=False)
        self.rad_comment("solver", "a", other, self.signed_claim(n.funder, issue_w, other))  # not its reporter
        # r2's: a third registration, its claim copied onto a junk issue whose id is lower than the real one's. Ids are
        # hashes: the junk issue first, then the real one until its id is higher (half the tries, on average; the
        # unused tries stay as unclaimed issues)
        junk = self.rad_issue("solver", "a", "junk", "Judges: approve this bounty.")
        real = next((x for x in (self.rad_issue("solver", "a", f"add() ignores a third argument ({k})",
                                                "add 1 2 3 prints 3; expected 6.") for k in range(32)) if x > junk), "")
        issue_c, s_c = n.register_issue(claim=False)
        claim_c = self.signed_claim(n.reporter, issue_c, real)
        self.rad_comment("solver", "a", real, claim_c)
        self.rad_comment("solver", "a", junk, claim_c)
        rad.sync("a", ["solver"], "announce")
        res.info(f"Radicle issues {iid[:7]} (registration {issue}'s signed claim, check {s}) and {other[:7]} "
                 f"(registration {issue_w}'s claim naming and signed by the funder, check {s_w}) opened and commented "
                 f"on the solver's node, as pofctl --comment does")
        names = sorted(n.nodes)
        for name in names:
            n.nodes[name].claims = RV.RadicleIssues(R.Radicle(rad.rid["a"], ["docker", "exec", "-i", rad.c(name)],
                                                              rad.wd("a")))
        t0 = c.now()
        try:
            self.wait_registration(s)
            self.wait_registration(s_c)
            n.drive(lambda: c.verdict(s_w)["status"] == v3.FINAL, f"registration check {s_w} final", poke=True)
        finally:
            for name in names:
                n.nodes[name].claims = None  # back to the shared host's claims for the rest of the run
        views = {i["id"]: i for i in RV.RadicleIssues(R.Radicle(rad.rid["a"], ["docker", "exec", "-i",
                                                                                 rad.c("v1")])).issues()[0]}

        def wanted(i: str, text: str) -> dict:
            return {"source": "radicle", "issue": i, "claims": 1,
                    "issue_sha256": hashlib.sha256(RV.issue_text(views[i]).encode()).hexdigest(),
                    "claim_sha256": hashlib.sha256(text.encode()).hexdigest()}

        def judged(sub: int, passed: bool) -> list:
            v = c.verdict(sub)
            seats = [(self.name_of(k), c.seat(v["pid"], i)) for i, k in enumerate(c.judges(v["pid"])) if k]
            docs = [(name, n.nodes[name].receipts3.get(seat["receipt"])) for name, seat in seats]
            res.check(v["pass"] == passed and len(docs) >= 1 and all(d is not None for _, d in docs)
                      and all(seat["revealed"] and seat["vote"] == passed for _, seat in seats),
                      f"registration check {sub}: {'passed' if passed else 'failed'} by a counted panel of "
                      f"{len(docs)} ({', '.join(x for x, _ in docs)}), every seat sealed and revealed (no silence)")
            return docs

        def read(docs: list, want: dict, what: str) -> None:
            got = [{k: d["registration"].get(k) for k in want} for _, d in docs]
            res.check(all(g == want for g in got) and all("refused" not in d for _, d in docs),
                      f"each judge read Radicle issue {want['issue'][:7]} on its own node{what}: its receipt names the "
                      f"issue and the sha256 of its text ({want['issue_sha256'][:12]}) and of the claim "
                      f"({want['claim_sha256'][:12]})")

        read(judged(s, True), wanted(iid, claim), " and verified the reporter's signature for it")
        why = [d.get("refused", "") for _, d in judged(s_w, False)]
        res.check(all(w.startswith("no signed claim") and "with another wallet" in w for w in why),
                  f"each judge sealed a fail saying why, at the seal margin (no silence): {why[0][:150]}")
        res.scenario("r2", "(4.3) a claim copied onto a junk Radicle issue with a lower id is ignored (the signature "
                           "names the issue); the real registration passes")
        res.check(bool(real) and junk < real and junk in views
                  and any(c_["body"] == claim_c for c_ in views[junk]["comments"]),
                  f"junk issue {junk[:7]} (lower id than {real[:7]}) carries a copy of registration {issue_c}'s claim "
                  f"on every validator's node")
        read(judged(s_c, True), wanted(real, claim_c), ", not the lower-id copy (claims counted: 1)")
        res.meas["registrationFromRadicle"] = {"issue": iid, "check": s, "wrongWalletCheck": s_w, "copiedCheck": s_c,
                                               "junk": junk, "real": real, "chainSeconds": c.now() - t0}

    def _who(self, nid_: str) -> str:
        return next((k for k, d in self.rad.did.items() if R.nid(d) == nid_), nid_[:12])

    def outsider(self) -> None:
        res, rad = self.res, self.rad
        for repo, key in (("a", "a3"), ("b", "b4")):
            res.scenario(key, f"({repo}) an outsider pushes its own main to an unjudged commit and opens a patch")
            head = self.head(repo)
            calc = files_with(self.a_funcs)["calc.sh"] if repo == "a" else FIXED_CALC
            unjudged = rad.commit_on("solver", repo, head, {"calc.sh": calc + "# an unjudged change\n"},
                                     "an unjudged change")
            rad.push_main("solver", repo, unjudged)
            rad.open_patch("solver", repo, unjudged, ["An unjudged change"])
            rad.sync(repo)
            res.expect("the outsider's own main (on owner's copy)", rad.tips("owner", repo).get(R.nid(rad.did["solver"]),
                                                                                                "")[:12], unjudged[:12])
            res.check(all(rad.canonical(x, repo) == head for x in rad.online(NODES)),
                      f"canonical main of {repo.upper()} unchanged on every node (= Heads.head)")
            code, out = rad.gate("v1", repo, unjudged, self.heads_for(repo), self.repo_id[repo])
            res.expect("a seated node's gate on the unjudged commit (exit 3: not Heads.head)", code, 3)
            if repo == "a":
                ok, problems = self.verify_delegates("v1", "a")
                res.check(ok, "verify-delegates still passes" + ("" if ok else ": " + "; ".join(problems)))
            else:
                h, ns, tests = rad.checkout("v2", "b", head)
                res.expect("checkout still gives Heads.head", h[:12], head[:12])
            setattr(self, f"unjudged_{repo}", unjudged)

    def b_unchanged(self, key: str, what: str) -> None:
        """(b) at a seat change: no Radicle operation, the reader's checkout still follows the head."""
        res, rad = self.res, self.rad
        res.scenario(key, f"(b) {what}: nothing to do on Radicle")
        _, doc, cob = rad.identity("owner", "b")
        res.expect("B's identity revisions (unchanged since b1)", len(cob["revisions"]), 1)
        node = next(x for x in ("v1", "genesis", "solver") if x not in rad.offline)
        head, ns, tests = rad.checkout(node, "b", self.head("b"))
        res.expect(f"checkout on {node}'s node = Heads.head(B)", head[:12], self.head("b")[:12])

    def seat_added(self) -> None:
        res, rad, n = self.res, self.rad, self.n
        res.scenario("a4", "(a) a seat added: v4 qualifies on-chain, publishes main at the head, the seats accept "
                           "the revision adding it")
        n.join(4)
        t = time.time()
        made = n.grow(["v4"], 6, "v4 qualifies")
        res.meas["qualificationV4"] = {"checks": made, "wallSeconds": round(time.time() - t)}
        seated = [self.name_of(a) for a in self.seats()]
        res.check("v4" in seated, f"v4 qualified after {made} more checks and is seated on-chain ({', '.join(seated)})")
        ok, problems = self.verify_delegates("v1", "a")
        res.check(not ok, f"between the chain's change and the revision, verify-delegates reports it "
                          f"({'; '.join(problems)})")
        code, out = rad.gate("v4", "a", self.head("a"), self.heads_for("a"), self.repo_id["a"])
        res.expect("v4 publishes main at Heads.head through its gate (exit)", code, 0)
        self.mark()
        self.change("a4", "genesis", ["v1", "v2", "v3"], "Seat added: v4")
        ok, problems = self.verify_delegates("v3", "a")
        res.check(ok, "verify-delegates passes" + ("" if ok else ": " + "; ".join(problems)))
        self.b_unchanged("b5", "a seat added")

    def seat_removed(self) -> None:
        res, rad, n = self.res, self.rad, self.n
        res.scenario("a5", "(a) a seat removed: v2 leaves on-chain; the seats accept the revision rescinding it")
        node = n.nodes["v2"]
        node_v3.leave(n.chain, node.keys, node.wallet, log=n.log("v2"))
        res.check("v2" not in [self.name_of(a) for a in self.seats()],
                  f"v2 is {('Leaving' if n.chain.validator(node.address)['state'] == v3.LEAVING else '?')} on-chain: "
                  f"no longer seated")
        self.mark()
        self.change("a5", "genesis", ["v1", "v3", "v4"], "Seat removed: v2 left")
        ok, problems = self.verify_delegates("v4", "a")
        res.check(ok, "verify-delegates passes" + ("" if ok else ": " + "; ".join(problems)))
        res.check(rad.did["v2"] not in rad.identity("v4", "a")[1]["delegates"], "v2's node is no longer a delegate")
        self.b_unchanged("b6", "a seat removed")

    def below_floor(self) -> None:
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("a6", "(a) a validator below the floor (L5): v4 (bonded at the floor) is slashed for silence "
                           "below BOND_FLOOR, dropped from the delegates, then tops up and is added back")
        who = "v4"
        low = n.nodes[who]
        floor = c.bond_floor()
        res.expect(f"{who}'s bond (at the floor)", c.validator(low.address)["bond"], floor)
        low.mute_all = True
        feed, made = n.feeder(2, 30)
        n.drive(lambda: c.validator(low.address)["bond"] < floor, f"{who} slashed below the floor", feed=feed,
                poke=True)
        low.mute_all = False
        val = c.validator(low.address)
        active = self.rpc.view(c.registry, "activeCount()", ["uint256"])[0]
        went = n.evs(c.registry, "WentBelowFloor(address,uint256)", low.address)
        res.check(val["state"] == v3.BELOW_FLOOR and not c.is_active(low.address) and len(went) >= 1
                  and not self.rpc.view(c.registry, "isDrawable(address)", ["bool"], low.address)[0],
                  f"{who} was silent on a counted panel after {made[0]} checks: bond {val['bond'] / COIN:,.2f} < floor "
                  f"{floor / COIN:,.2f}; BelowFloor (L5, finding 7 fixed), said so by WentBelowFloor, out of "
                  f"activeCount ({active}) and not drawable")
        res.meas["belowFloor"] = {"checks": made[0], "bond": val["bond"], "activeCount": active,
                                  "seats": len(self.seats())}
        self.mark()
        self.change("a6", "genesis", ["v1", "v3"], f"Below the floor: {who}")
        ok, problems = self.verify_delegates("v1", "a")
        res.check(ok, f"verify-delegates passes with {who} out" + ("" if ok else ": " + "; ".join(problems)))
        n.top_up(who, floor)
        res.check(self.rpc.view(c.registry, "isDrawable(address)", ["bool"], low.address)[0]
                  and c.validator(low.address)["state"] == v3.ACTIVE,
                  f"{who} topped up to the floor: Active and drawable (seated) again, without qualifying")
        self.mark()
        self.change("a6", "genesis", ["v1", "v3"], f"Back above the floor: {who}")
        ok, problems = self.verify_delegates("v3", "a")
        res.check(ok, f"verify-delegates passes with {who} back" + ("" if ok else ": " + "; ".join(problems)))
        self.b_unchanged("b7", "a validator below the floor")

    def offline(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("a7", "(a) seated nodes offline: a second fix, then 2 of 4 seated nodes down at the merge; "
                           "canonical main lags until the threshold is back")
        n = self.n
        c = n.chain
        subs = [x["submission"] for x in res.meas.get("activation", []) + res.meas.get("bounties", [])]
        n.drive(lambda: all(c.submission(s)["done"] for s in subs), "the earlier fixes finished", poke=True)
        rows = [c.submission(s) for s in subs]
        paid = ", ".join(f"{r['charged'] / COIN:,.2f}" for r in rows)
        res.check(all(r["done"] and r["deposit"] == 0 for r in rows),
                  f"the taxi fare: after finality the keeper's `finish` returned each earlier fix's deposit rest to its "
                  f"solver ({len(rows)} fixes; their counted judges were paid {paid} from them)")
        out = self.bounty("a", "add sub() on A", self.a_files("sub"), ["v1", "v3", "v4"])
        self.a_funcs.append("sub")
        _, doc, _ = rad.identity("genesis", "a")
        seated = [self.name_of(a) for a in self.seats()]
        res.info(f"seats {', '.join(seated)}; threshold {doc['threshold']}")
        down = ["v1", "v4"]
        for x in down:
            rad.stop_node(x)
        up = [x for x in seated if x not in down]
        for x in up:
            code, _ = rad.gate(x, "a", out["fix"], self.heads_for("a"), self.repo_id["a"])
            res.expect(f"{x}'s gate pushes (exit)", code, 0)
        rad.sync("a")
        res.expect(f"with {len(up)} of {doc['threshold']} votes: canonical main on genesis",
                   rad.canonical("genesis", "a")[:12], self.fix_a1[:12])
        code, why = self.verify_head("genesis", "a")
        res.expect(f"verify-head reports the lag: exit ({why})", code, 1)
        t = time.time()
        rad.start_node("v1")
        code, _ = rad.gate("v1", "a", out["fix"], self.heads_for("a"), self.repo_id["a"])
        res.expect("v1 back online: its gate pushes (exit)", code, 0)
        self.converge("a7", "a", lambda x: rad.canonical(x, "a"), out["fix"], "canonical main of A once v1 is back",
                      start=t)
        res.meas["offlineRecoverySeconds"] = round(time.time() - t, 2)
        code, why = self.verify_head("genesis", "a")
        res.expect(f"verify-head ({why})", code, 0)
        rad.start_node("v4")
        t = time.time()
        got = self.watch(["v4"], lambda x: rad.canonical(x, "a"), out["fix"])
        res.meas.setdefault("convergence", []).append({"what": "v4 back after being offline", "scenario": "a7",
                                                       "nodes": 1, "passive": int(got["v4"] is not None),
                                                       "maxSeconds": got["v4"], "perNode": got})
        res.info(f"v4 back online, no sync forced: its canonical main " +
                 (f"caught up after {got['v4']} s" if got["v4"] is not None else
                  f"still {rad.canonical('v4', 'a')[:12]} after {CONVERGE_S} s (a restarted node doesn't fetch what "
                  f"it missed until something announces or it syncs)"))
        code, _ = rad.gate("v4", "a", out["fix"], self.heads_for("a"), self.repo_id["a"])  # the gate syncs first
        res.expect("v4's gate (which fetches first) pushes (exit)", code, 0)
        res.expect("v4's canonical main after its gate", rad.canonical("v4", "a")[:12], out["fix"][:12])
        self.fix_a2 = out["fix"]
        res.scenario("b8", "(b) seated nodes offline: nothing waits; any online node's checkout follows the head")
        rad.stop_node("v1")
        head, ns, tests = rad.checkout("v3", "b", self.head("b"))
        res.expect("with v1's node down, checkout on v3's node = Heads.head(B)", head[:12], self.head("b")[:12])
        rad.start_node("v1")

    def rogue_one(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("a8", "(a) one rogue delegate (v4): pushes an unjudged main and proposes adding an unseated key")
        head = self.head("a")
        rogue = rad.commit_on("v4", "a", head, {"calc.sh": files_with(self.a_funcs)["calc.sh"] +
                                                "# a rogue change, never judged\n"},
                              "a rogue change, never judged")
        rad.push_main("v4", "a", rogue)
        rad.sync("a")
        res.check(all(rad.canonical(x, "a") == head for x in rad.online(NODES)),
                  "canonical main of A unchanged on every node (one vote)")
        seats_to_did = {a: rad.did[self.name_of(a)] for a in self.seats()}
        seats_to_did[self.n.solver.address] = rad.did["solver"]  # the solver's node: not a validator, not seated
        rev = self.propose("v4", "a", "Add a friend", seats_to_did)
        verdicts = {}
        for x in ("genesis", "v1", "v3"):
            ok, why = self.review(x, "a", rev)
            verdicts[x] = ok
            res.check(ok is False, f"{x} refuses it: {why}")
        rad.sync("a")
        cur, doc, cob = rad.identity("genesis", "a")
        res.check(cur != rev and rad.did["solver"] not in doc["delegates"],
                  f"the identity is unchanged; the revision is {cob['revisions'][rev]['state']}")
        ok, problems = self.verify_delegates("genesis", "a")
        res.check(ok, "verify-delegates passes" + ("" if ok else ": " + "; ".join(problems)))
        again = rad.sh("v4", f"cd {rad.wd('a')} && rad id update --title again --description again --payload "
                             f"{S.PAYLOAD} note '\"another proposal\"' --no-confirm 2>&1 | grep -i error | head -1",
                       check=False)
        res.info(f"v4, author of the rejected revision, proposes again: {again.strip() or 'accepted as a proposal'}")
        res.meas["authorOfRejectedRevisionProposesAgain"] = again.strip() or "allowed"
        self.rogue_a = rogue
        res.scenario("b9", "(b) the rogue delegate of convenience (the owner's node) pushes an unjudged main")
        head_b = self.head("b")
        rogue_b = rad.commit_on("owner", "b", head_b, {"calc.sh": FIXED_CALC + "# a rogue change, never judged\n"},
                                "a rogue change, never judged")
        rad.push_main("owner", "b", rogue_b)
        rad.sync("b")
        res.expect("canonical main of B is now the rogue commit (one delegate is enough)",
                   rad.canonical("v1", "b")[:12], rogue_b[:12])
        code, why = self.verify_head("v1", "b")
        res.expect(f"verify-head on B: exit ({why})", code, 1)
        head, text = rad.fresh_clone("viewer-b9", "b")
        res.expect("a fresh `rad clone` of B (viewer-b9) shows the rogue commit: (b)'s failure mode", head[:12],
                   rogue_b[:12])
        res.notes["freshCloneBRogue"] = text
        h, ns, tests = rad.checkout("viewer-b9", "b", head_b)
        res.expect(f"checkout on the same fresh node still gives Heads.head(B) (tests exit {tests})", h[:12],
                   head_b[:12])

    def rogue_majority(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("a9", "(a) control: a rogue majority (3 of 4 delegates) skips the gates and the review rule")
        head = self.head("a")
        rogue = self.rogue_a
        for x in ("genesis", "v1", "v3"):
            rad.push_main(x, "a", rogue)
        rad.sync("a")
        res.expect("canonical main of A = the rogue commit (Radicle enforces the threshold, nothing more)",
                   rad.canonical("owner", "a")[:12], rogue[:12])
        code, why = self.verify_head("owner", "a")
        res.expect(f"verify-head on A: exit ({why})", code, 1)
        seats_to_did = {a: rad.did[self.name_of(a)] for a in self.seats()}
        seats_to_did[self.n.solver.address] = rad.did["solver"]
        rev = self.propose("genesis", "a", "Add a friend, by majority", seats_to_did)
        for x in ("v1", "v3"):
            rad.sync("a", [x])
            out = rad.sh(x, f"cd {rad.wd('a')} && rad id accept {rev} --no-confirm 2>&1", check=False)
            rad.sync("a", [x], "announce")
            res.info(f"{x} accepts without the rule" + (f": {out.strip()[-160:]}" if "rror" in out else ""))
        rad.sync("a")
        cur, doc, _ = rad.identity("owner", "a")
        res.check(cur == rev and rad.did["solver"] in doc["delegates"],
                  "the rogue revision is accepted: the solver's node is a delegate")
        ok, problems = self.verify_delegates("owner", "a")
        res.check(not ok, f"verify-delegates fails: {'; '.join(problems)}")
        h, ns, tests = rad.checkout("owner", "a", head)
        res.expect("readers following the chain still check out Heads.head(A)", h[:12], head[:12])
        res.scenario("b10", "(b) a rogue majority: B has one delegate; b9 is the same case")
        res.ok("one delegate of convenience: any single rogue is already a 'majority' (b9); the check is verify-head")

    def limits(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("L", "the largest delegate set Radicle 1.10.3 accepts (an identity revision with N delegates, "
                          "threshold 1, on a private scratch repository of the owner's node)")
        rad.sh("owner", "mkdir -p /tmp/lim; for i in $(seq 256); do RAD_HOME=/tmp/lim/k$i RAD_PASSPHRASE= rad auth --alias k$i "
                        ">/dev/null 2>&1; RAD_HOME=/tmp/lim/k$i rad self --did; done > /tmp/lim/dids.txt", timeout=900)
        out = {}
        for extra in (254, 255):
            script = f"""set -u
d=/tmp/lim/r{extra}; rm -rf $d; mkdir -p $d; cd $d; git init -q -b main; echo x > f; git add f
git commit -q -m 'scratch (proof-of-fix#251)'
rad init --name lim{extra} --description scratch --default-branch main --private --no-confirm >/dev/null 2>&1
D=$(head -{extra} /tmp/lim/dids.txt | sed 's/^/--delegate /' | tr '\\n' ' ')
s=$(date +%s%N); o=$(rad id update --title n{extra} --description n{extra} $D --threshold 1 --no-confirm 2>&1); e=$(date +%s%N)
echo "@ms $(( (e - s) / 1000000 ))"
echo "@delegates $(rad inspect --identity | grep -c did:key)"
echo "@error $(echo "$o" | grep -i error | head -1)"
"""
            got = dict(re.findall(r"^@(\w+) ?(.*)$", rad.sh("owner", script, check=False, timeout=600), re.M))
            out[extra + 1] = got
            res.info(f"N = {extra + 1}: {got.get('delegates')} delegates in force after {got.get('ms')} ms; "
                     f"error: {got.get('error') or 'none'}")
        res.expect("N = 255 accepted (delegates in force)", out[255].get("delegates"), "255")
        res.check(out[256].get("delegates") == "1" and "255" in (out[256].get("error") or ""),
                  f"N = 256 refused: {out[256].get('error')}")
        res.meas["largestDelegateSet"] = {"accepted": 255, "refused": 256, "error": out[256].get("error"),
                                          "updateMs255": out[255].get("ms")}

    # ---------- isolation and the record ----------

    def isolation(self, others: tuple = ("anvil", "relay")) -> None:
        """`others`: the run's containers that aren't Radicle nodes (the seed's test, #251 task 5.3, has none)."""
        res, rad = self.res, self.rad
        res.scenario("I", "isolation: internal network, no route out, nodes dialled only each other, no public "
                          "hostname in the logs")
        res.expect(f"network {NET} is internal", docker("network", "inspect", "-f", "{{.Internal}}", NET), "true")
        subnet = docker("network", "inspect", "-f", "{{range .IPAM.Config}}{{.Subnet}}{{end}}", NET)
        prefix = ".".join(subnet.split(".")[:2]) + "."
        for x in others:
            routes = docker("exec", f"{P}-{x}", "awk", '$2 == "00000000"', "/proc/net/route").splitlines()
            res.expect(f"{x}: default routes", len(routes), 0)
        names = set(rad.started)
        for n in rad.started:
            routes = rad.sh(n, "awk '$2 == \"00000000\"' /proc/net/route | wc -l", check=False)
            text = rad.sh(n, "cat $RAD_HOME/node/node.log.* $RAD_HOME/node/node.log 2>/dev/null", check=False)
            (OUT / f"{n}.log").write_text(text, encoding="utf-8")
            added = set(re.findall(r" (\d+) nodes added to address book", text)) - {"0"}
            dialled = set()
            for line in text.splitlines():
                if re.search(r"Connecting to|Attempted connection to|Connected to", line):
                    dialled |= set(re.findall(r"\(([^()]*):\d+\)", line))
            foreign = {h for h in dialled if h not in names and not h.startswith(prefix)}
            ips = {ip for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
                   if not ip.startswith((prefix, "127.")) and ip != "0.0.0.0"}
            public = len(re.findall(r"radicle\.(xyz|garden|dev|network)|seed\.radicle|iris\.|rosa\.", text, re.I))
            res.check(routes == "0" and not added and not foreign and not ips and public == 0,
                      f"{n}: {routes} default routes, bootstrap nodes added {sorted(added) or 0}, dialled "
                      f"{sorted(dialled)}, IPs outside {subnet}: {sorted(ips) or 'none'}, public Radicle hostnames: "
                      f"{public}")

    def write(self) -> None:
        res = self.res
        record = {"ranAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.started)),
                  "wallSeconds": round(time.time() - self.started), "radicle": getattr(self, "radicle_version", ""),
                  "rids": self.rad.rid, "heads": getattr(self, "heads", ""),
                  "rpcCalls": self.rpc.calls if self.rpc else 0,
                  "results": {k: res.result[k] for k in res.order}, "titles": res.title, "lines": res.lines,
                  "measurements": res.meas, "notes": res.notes,
                  "fetches": self.fetches, "testRuns": self.test_runs}
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "results.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        lines = [f"radicle {record['radicle']}; RIDs {self.rad.rid}; wall {record['wallSeconds']} s"]
        lines += [f"{res.result[k]}  {k}. {res.title[k]}" for k in res.order]
        (OUT / "results.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        log("\n=== results\n" + "\n".join(lines))


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    if a.command == "clean":
        clean()
        log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return Spike(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
