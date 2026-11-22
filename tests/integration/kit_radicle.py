"""The SEV-SNP kit's Radicle node on the internal Docker network (proof-of-fix#251 task 4.9; design L11, L12, L16, L21).
Run it with `scripts/kit-radicle.sh`, which builds the spike's node image (spikes/radicle/Dockerfile: the pinned Radicle
1.10.3 release, checked by SHA-256) and calls this file. `python3 tests/integration/kit_radicle.py clean` removes
anything a stopped run left behind.

Not a new harness: task 4.6's (tests/integration/suite_v3_radicle.py `Story`, under its own names): the launch's rules
on anvil, seven validators configured as `python3 -m oracle run` configures them (ORACLE_FIX_SOURCE=radicle,
ORACLE_MERGE_VIA=radicle, ORACLE_SEAT_NODES=chain), each fix's tests in the real Docker sandbox, the reporter and the
solvers through pofctl. What differs is the Radicle network, configured exactly as the launch runs it:
- **the seed** as seed/ configures it: seed/radicle/seed-setup.sh (its key, seed/radicle/config.json with the "block"
  default, the one seeding policy) and radicle-seed.service's ExecStart, the RID from a publication record
  (seed/publication.py), as tests/integration/seed_radicle.py starts it;
- **every other node** as the measured disk configures a validator's: validator-kit/sevsnp/disk's radicle-setup.sh (the
  key made once in RAD_HOME=/data/state/radicle, radicle-config.json on Radicle's main network: listening on no
  address, announcing none, static peers dialling only the seed) and pof-radicle.service's ExecStart, then the disk's
  radicle-ready.sh at each boot (a sync with the seed and the working copy made again in /data/scratch/radicle/repo,
  ORACLE_RADICLE_REPO). The owner's, the reporter's and the solver's nodes too: no node but the seed listens, so
  everything goes through it.
- **the node container beside it**, as pof-node.sh runs it: each validator's oracle reaches its Radicle node through a
  second container with no network at all (`--network none`), the same user and the Radicle node's /data mounted
  (the control socket, the storage, the key, the working copy), as the disk's node container mounts /data/state/radicle
  and /data/scratch/radicle; so every `rad` and `git` call the oracle makes (patches, issues, `main`, identity reviews)
  goes through the socket and the shared storage, and only radicle-node touches the network.
- **the kit's lifecycle**: a validator's host is stopped ("asleep": its Radicle node stopped, its oracle node not
  running) except while validator-kit/sevsnp/lambda/watcher.py, the kit's real watcher run against this chain, starts
  it (a fake EC2 whose start wakes the node). The keeper's calls (draws, audits, finality) stay on: the genesis key's
  keeper runs while its host sleeps, standing in for an always-on keeper (the kit's node keeps only while up: see the
  report). The chain's clock doesn't move while a host wakes (anvil's interval 0), so the boot's time isn't measured
  here (validator-kit/SEVSNP-PLAN.md has it).

The story, each step needing the one before:
S. task 4.6's setup (seven validators qualified, the identity handed to the seats: 7 delegates, threshold 4), on this
   network;
O. outbound only: no validator's node listens (no socket on 8776, a dial from the seed refused, `rad node status` says
   so), each dialled only the seed, and every session on its side is outbound;
1. task 4.6's registration: Radicle issues registered with pofctl, their checks passed;
A. a patch opened while every validator's host is stopped: the seed holds it; the watcher starts each drawn judge's host
   on its `Seated` event; each node fetches the patch from the seed and judges it, and the fix passes;
L. the canonical `main` while the delegates sleep: after `merge`, with every host stopped, it lags `Heads.head` and
   `verify-head` refuses; three delegates up push their `main` and it still lags (3 of the 4 needed); the fourth makes
   it canonical on the seed, on the solver's node and on a fresh node connected only to the seed;
B. a second fix the same way, with the watcher's Radicle duty on (WAKE_ON_HEAD);
W. the duty: at B's merge the watcher starts all seven hosts once and the canonical `main` follows with no other draw;
   `verify-head` exits 0;
T. the wakes' times: radicle-node's start and the ready step;
7. task 4.6's verify-head and verify-delegates, every host up;
I. isolation (the spike's check; the kit's nodes may hold main's bootstrap entries but never dial them), plus no
   inbound session on any validator's node over the whole run.

No model call, no public chain or network, no AWS. Results and node logs stay in .kit-radicle/ (gitignored)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle", ROOT / "seed"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import publication  # noqa: E402
import suite_v3_radicle as SR  # noqa: E402
import v3_spike as VS  # noqa: E402
from oracle import v3  # noqa: E402
from oracle import radicle as R  # noqa: E402

PREFIX = "pof251k"
OUT = ROOT / ".kit-radicle"
RECORD_DIR = ROOT / "contracts" / "deployments" / "kit-radicle"
DISK = ROOT / "validator-kit" / "sevsnp" / "disk" / "rootfs"
KIT_LIB = DISK / "usr" / "lib" / "pof"
KIT_UNIT = DISK / "etc" / "systemd" / "system" / "pof-radicle.service"
SEED_DIR = ROOT / "seed" / "radicle"
WATCHER = ROOT / "validator-kit" / "sevsnp" / "lambda" / "watcher.py"
KIT_FILES = "/opt/pof-kit"  # radicle-setup.sh and radicle-config.json, as on the disk's /usr/lib/pof
SEED_FILES = "/opt/radicle-seed"
STATE = "/data/state/radicle"  # RAD_HOME on the kit's host: the data volume
LOGS = "/data/logs"  # every session's radicle-node log, kept across the host's stops (this test's, not the disk's)
WORK_COPY = "/data/scratch/radicle/repo"  # ORACLE_RADICLE_REPO on the kit's host: the scratch disk
VALIDATORS = SR.VALIDATORS
NODES = SR.NODES + ["seed", "viewer"]
HOME_C = VS.HOME_C
FOLLOW_S = 180
NODE_SUFFIX = "-node"  # the validator's node container beside its Radicle node (pof-node.sh's mounts)
KIT_NETWORK = "main"  # what pof-radicle.sh passes: Radicle's main network, whose bootstrap nodes the static peers never dial
RUNNING = "rad node status 2>/dev/null | grep -q 'Node is running'"  # `rad node status` exits 0 either way


def _watcher():
    spec = importlib.util.spec_from_file_location("pof_kit_watcher", WATCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _watcher()


def exec_start(unit: Path) -> str:
    m = re.search(r"^ExecStart=(.+)$", unit.read_text(encoding="utf-8"), re.M)
    if not m:
        raise RuntimeError(f"{unit.name} has no ExecStart")
    return m.group(1).strip()


def kit_node_command() -> str:
    """radicle-node's command line from the kit's unit, with the disk's binary path as the image's (on PATH)."""
    return re.sub(r"^/usr/lib/pof/radicle/bin/", "", exec_start(KIT_UNIT))


DOCKER_DNS = "0B00007F"  # 127.0.0.11 in /proc/net/tcp: Docker's embedded resolver, in every container's namespace


def listening(proc_net: str) -> list:
    """The listening TCP sockets in /proc/net/tcp{,6} text, as (address in hex, port), except Docker's own resolver on
    127.0.0.11 (a random port in every container on a user-defined network: the network's, not radicle-node's)."""
    socks = []
    for line in proc_net.splitlines():
        f = line.split()
        if len(f) > 3 and f[3] == "0A" and ":" in f[1]:
            addr, port = f[1].rsplit(":", 1)
            if addr != DOCKER_DNS:
                socks.append((addr, int(port, 16)))
    return sorted(socks)



class Param:
    """The watcher's SSM parameter."""

    class exceptions:
        ParameterNotFound = KeyError

    def __init__(self, value: str) -> None:
        self.value = value

    def get_parameter(self, Name):  # noqa: N803 (boto3's names)
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, Name, Value, Type, Overwrite):  # noqa: N803
        self.value = Value


class Host:
    """The validator's instance, as the watcher sees it through EC2: stopped while its validator sleeps; a start wakes
    it."""

    def __init__(self, story: "KitStory", name: str) -> None:
        self.story, self.name, self.starts = story, name, 0

    def describe_instances(self, InstanceIds):  # noqa: N803
        state = "stopped" if self.name in self.story.asleep else "running"
        return {"Reservations": [{"Instances": [{"State": {"Name": state}}]}]}

    def start_instances(self, InstanceIds):  # noqa: N803
        self.starts += 1
        self.story.wake(self.name, "the watcher")


class KitNet(SR.RadNet):
    """Task 4.6's network with the kit's working copy (ORACLE_RADICLE_REPO on the scratch disk) and the kit's
    lifecycle: a validator whose host is stopped doesn't run, except the genesis key's keeper calls (see above)."""

    def env(self, name: str) -> dict:
        """The disk's settings: the node container's own `rad` and `git` on the shared storage (pof-node.sh), the
        working copy on the scratch disk."""
        return {**super().env(name), "ORACLE_RADICLE_EXEC": f"docker exec -i {self.story.rad.c(name)}{NODE_SUFFIX}",
                "ORACLE_RADICLE_REPO": WORK_COPY}

    def make_node(self, name: str, family: str, keeper: bool = False, tag: str = ""):
        node = super().make_node(name, family, keeper=keeper, tag=tag)
        run = node.tick

        def tick(from_block: int, _run=run, _node=node, _name=name) -> bool:
            if _name not in self.story.asleep:
                return _run(from_block)
            return bool(_node.keeper and _node._keep(from_block, self.chain.now()))
        node.tick = tick
        return node


class KitStory(SR.Story):
    def __init__(self, keep: bool) -> None:
        super().__init__(keep)
        self.asleep: set = set()
        self.wakes: list = []  # {"node", "why", "readyS", "at"}
        self.watchers: dict = {}  # name -> {"env", "param", "host"}
        self.watch_log: list = []
        self.seed_addr = ""
        self.awaited: dict = {}  # a patch id the woken nodes should list -> the wall time it was opened
        self.kit: dict = {}

    # ---------- the network: the seed, and every other node as the kit configures a validator's ----------

    def up(self) -> None:
        """The spike's anvil and relay on the internal network, and the owner's node; the rest start in `repos`."""
        rad = self.rad
        solc = os.environ.get("POF_SOLC", "")
        if not solc or not (ROOT / solc).is_file():
            raise RuntimeError("POF_SOLC (the pinned solc, scripts/solc.sh) is missing: run scripts/contracts.sh setup")
        VS.docker("network", "create", "--internal", VS.NET)
        uid = f"{os.getuid()}:{os.getgid()}"
        VS.docker("run", "-d", "--name", f"{VS.P}-anvil", "--network", VS.NET, "--network-alias", "anvil", "--user", uid,
                  "-e", "HOME=/tmp", "-v", f"{ROOT}/contracts:/work", "-v", f"{ROOT}/{solc}:/opt/solc/solc:ro",
                  "-w", "/work", "--entrypoint", "anvil", VS.FOUNDRY_IMAGE, "--host", "0.0.0.0", "--port", "8545",
                  "--chain-id", "31337", "--silent")
        VS.docker("run", "-d", "--name", f"{VS.P}-relay", "--network", VS.NET, "--entrypoint", "python3", VS.PY_IMAGE,
                  "-c", "import time; time.sleep(10**9)")
        self.rpc = VS.PipeRpc(f"{VS.P}-relay")
        for _ in range(120):
            try:
                if self.rpc.chain_id() == 31337:
                    break
            except Exception:  # noqa: BLE001 (anvil isn't listening yet)
                time.sleep(0.5)
        else:
            raise RuntimeError("anvil didn't answer through the relay")
        self.kit_node("owner")
        self.radicle_version = rad.sh("owner", "rad --version")
        VS.log(f"radicle: {self.radicle_version}; the kit's radicle-node: `{kit_node_command()}`")

    def kit_node(self, n: str, rid: str = "", seed: str = "") -> None:
        """Node `n` configured by the disk's radicle-setup.sh in RAD_HOME=/data/state/radicle, then started with
        pof-radicle.service's command."""
        rad = self.rad
        VS.docker("run", "-d", "--name", rad.c(n), "--hostname", n, "--network", VS.NET, "--network-alias", n,
                  "-e", f"RAD_HOME={STATE}", "-v", f"{rad.c(n)}-data:/data", VS.IMAGE)
        VS.docker("exec", "-u", "root", rad.c(n), "bash", "-c",
                  f"mkdir -p {STATE} /data/scratch/radicle {KIT_FILES} && chown -R foundry:foundry /data")
        for f in ("radicle-setup.sh", "radicle-ready.sh", "radicle-config.json"):
            VS.docker("cp", str(KIT_LIB / f), f"{rad.c(n)}:{KIT_FILES}/{f}")
        out = rad.sh(n, f"bash {KIT_FILES}/radicle-setup.sh {n} {KIT_NETWORK} {shlex.quote(rid)} {shlex.quote(seed)} 2>&1")
        rad.did[n] = out.splitlines()[-1].strip()
        if not rad.did[n].startswith("did:key:z6Mk"):
            raise RuntimeError(f"{n}: radicle-setup.sh gave no DID: {out[-300:]}")
        rad.started.append(n)
        self.start_radicle(n)
        if n in VALIDATORS:  # its node container: no network, the same user, the Radicle node's /data
            VS.docker("run", "-d", "--name", rad.c(n) + NODE_SUFFIX, "--network", "none", "-e", f"RAD_HOME={STATE}",
                      "-v", f"{rad.c(n)}-data:/data", VS.IMAGE)

    def start_radicle(self, n: str) -> float:
        t = time.time()
        self.rad.sh(n, f"mkdir -p $RAD_HOME/node && (setsid nohup {kit_node_command()} >>$RAD_HOME/node/node.log 2>&1 &)"
                       f" && for _ in $(seq 300); do {RUNNING} && break; sleep 0.1; done; {RUNNING}")
        return time.time() - t

    def ready(self, n: str) -> tuple:
        """pof-radicle.sh's `ready` step: the disk's radicle-ready.sh (a sync with the seed, then the working copy
        made again from the storage). Returns (seconds, the sync's error or "")."""
        rid = self.rad.rid["a"]
        t = time.time()
        out = self.rad.sh(n, f"cd /data/scratch/radicle && bash {KIT_FILES}/radicle-ready.sh {rid} {WORK_COPY} 2>&1; "
                             f"echo \"@exit $?\"; ln -sfn {WORK_COPY} {HOME_C}/repo-a", check=False)
        m = re.search(r"^ready in \d+ ms \(sync: (.*)\)$", out, re.M)
        if not m or "@exit 0" not in out:
            raise RuntimeError(f"{n}: no working copy after radicle-ready.sh: {out[-300:]}")
        return time.time() - t, "" if m.group(1) == "ok" else m.group(1)

    def start_seed(self, rid: str) -> None:
        """The seed, as tests/integration/seed_radicle.py starts it: seed-setup.sh, then radicle-seed.service's
        ExecStart."""
        rad, n = self.rad, "seed"
        VS.docker("run", "-d", "--name", rad.c(n), "--hostname", n, "--network", VS.NET, "--network-alias", n,
                  VS.IMAGE)
        VS.docker("cp", f"{SEED_DIR}/.", f"{rad.c(n)}:{SEED_FILES}")
        # Radicle's test network: the seed's dynamic peers would dial main's bootstrap nodes, which an internal
        # network can't resolve (seed_radicle.py, task 5.3, runs it the same way); the kit's nodes are on main.
        out = rad.sh(n, f"bash {SEED_FILES}/seed-setup.sh {shlex.quote(rid)} seed seed:8776 test 2>&1")
        rad.did[n] = out.splitlines()[-1].strip()
        start = exec_start(SEED_DIR / "radicle-seed.service").replace("/usr/local/bin/", "")
        rad.sh(n, f"mkdir -p $RAD_HOME/node && (setsid nohup {start} >$RAD_HOME/node/node.log 2>&1 &) && "
                  f"for _ in $(seq 300); do {RUNNING} && break; sleep 0.1; done; {RUNNING}")
        rad.started.append(n)
        self.seed_addr = f"{R.nid(rad.did[n])}@seed:8776"

    def repos(self) -> str:
        """Task 4.6's repository, created on the owner's node; then the seed from its publication record; then every
        other node, configured as the kit's, cloning it through the seed alone."""
        rad = self.rad
        rad.sh("owner", "mkdir -p g/tests g/.pof && cd g && git init -q -b main")
        for path, text in SR.GENESIS_FILES.items():
            rad.sh("owner", f"cat > g/{path}", input=text)
        genesis = rad.sh("owner", "cd g && git add -A && git commit -q -m 'genesis: median() is wrong "
                                  "(proof-of-fix#251)' && git rev-parse HEAD")
        rad.sh("owner", "git clone -q g repo-a && cd repo-a && git remote remove origin && rad init --name pof-stats "
                        "--description 'proof-of-fix#251 task 4.9' --default-branch main --public --no-confirm "
                        ">/dev/null 2>&1")
        rad.rid["a"] = rad.sh("owner", "cd repo-a && rad .")
        if not R.RID_RE.match(rad.rid["a"]):
            raise RuntimeError(f"rad init gave no RID: {rad.rid['a']!r}")
        record = {"format": publication.FORMAT, "rid": rad.rid["a"], "rootCommit": genesis,
                  "nodeId": R.nid(rad.did["owner"]), "radicle": publication.RADICLE}
        (OUT / "record").mkdir(parents=True, exist_ok=True)
        path = OUT / "record" / "publication.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        rid = publication.rid(path)
        self.start_seed(rid)
        rad.sh("owner", f"rad node connect {self.seed_addr} >/dev/null 2>&1 || true", check=False)  # it dials out
        for _ in range(60):
            if rad.canonical("seed", "a") == genesis:
                break
            rad.sync("a", ["owner"], "announce")
            time.sleep(1)
        else:
            raise RuntimeError("the seed didn't replicate the repository from the owner's node")
        for n in SR.NODES[1:]:
            self.kit_node(n, rid, self.seed_addr)
            self.ready(n)
        VS.log(f"repository {rid}; genesis {genesis}; seed {self.seed_addr}; {len(SR.NODES) - 1} kit nodes cloned "
               f"it through the seed")
        return genesis

    # ---------- the kit's lifecycle ----------

    def sleep(self, name: str) -> None:
        """The host powers off: its Radicle node stops (the oracle node already exited, idle)."""
        if name in self.asleep:
            return
        # `rad node stop` deletes node/node.log, so each session's log is kept first: the isolation check reads them all
        self.rad.sh(name, f"mkdir -p {LOGS} && cat $RAD_HOME/node/node.log >>{LOGS}/radicle-node.log 2>/dev/null; "
                          f"rad node stop >/dev/null 2>&1; for _ in $(seq 100); do {RUNNING} || break; sleep 0.1; "
                          f"done", check=False)
        self.asleep.add(name)

    def wake(self, name: str, why: str) -> None:
        """The host boots: pof-radicle.service (the node, then its ready step), then the oracle node runs."""
        if name not in self.asleep:
            return
        t = time.time()
        node_s = self.start_radicle(name)
        ready_s, err = self.ready(name)
        self.asleep.discard(name)
        w = {"node": name, "why": why, "at": t, "radicleNodeS": round(node_s, 2), "readyS": round(ready_s, 2),
             "syncError": err}
        if self.awaited:  # a patch opened while this host was stopped: on its own node now?
            listed = set(self.rad.sh(name, f"rad cob list --repo {self.rad.rid['a']} --type xyz.radicle.patch",
                                     check=False).split())
            w["patchesListed"] = sorted(p[:7] for p in self.awaited if p in listed)
        w["wakeToReadyS"] = round(time.time() - t, 2)
        self.wakes.append(w)
        VS.log(f"  {name} woke ({why}): radicle-node {w['radicleNodeS']} s, ready {w['readyS']} s"
               + (f", patches {w.get('patchesListed')}" if self.awaited else ""))

    def watchers_on(self, wake_on_head: bool) -> None:
        c = self.n.chain
        block = self.rpc.block()
        for name in VALIDATORS:
            w = self.watchers.get(name)
            if w is None:
                w = self.watchers[name] = {"param": Param(json.dumps({"last": block})), "host": Host(self, name)}
            w["env"] = {"ENABLED": "true", "STATE_PARAM": f"/pof-snp/{name}/watcher", "RACE_ADDRESS": c.race,
                        "VALIDATOR_ADDRESS": self.n.nodes[name].address, "INSTANCE_ID": f"i-{name}",
                        "UNPAUSE_CHECK": "off", "MAX_BLOCK_RANGE": "100000", "RETRY_MINUTES": "0",
                        "WAKE_ON_HEAD": "true" if wake_on_head else "false"}

    def watch(self) -> dict:
        """One run of each validator's watcher (validator-kit/sevsnp/lambda/watcher.py) against this chain."""
        out = {}
        for name, w in self.watchers.items():
            out[name] = W.run(w["env"], self.rpc, w["param"], w["host"], now=time.time)
            if out[name].get("action") not in ("idle", "running"):
                self.watch_log.append({"node": name, **out[name]})
        return out

    def patch_on(self, n: str, pid: str) -> bool:
        return pid in self.rad.sh(n, f"rad cob list --repo {self.rad.rid['a']} --type xyz.radicle.patch",
                                  check=False).split()

    def seed_view(self, sha: str) -> tuple:
        """(the seed's canonical main, the delegates whose `main` on the seed contains `sha`, by name)."""
        snap = R.Radicle(self.rad.rid["a"], ["docker", "exec", "-i", self.rad.c("seed")]).snapshot(sync=False)
        names = {R.nid(d): n for n, d in self.rad.did.items()}
        return snap.canonical_ref, sorted(names.get(x, x[:8]) for x in snap.votes(sha))

    def until(self, probe, timeout: float, every: float = 1.0) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if probe():
                return True
            time.sleep(every)
        return bool(probe())

    def push_pass(self, names) -> None:
        """One forced pass of these validators' seat adapters (their node's Radicle part, as `oracle run` does)."""
        for name in names:
            try:
                self.n.nodes[name].radicle_seat.tick(force=True)
            except R.Unavailable as e:
                VS.log(f"  warn {name}: {e}")

    # ---------- the story ----------

    def scenarios(self) -> None:
        self.setup()
        self.outbound()
        self.registration()
        self.watchers_on(wake_on_head=False)
        self.n.watches.append(self.watch)
        first = self.asleep_fix("A", "solver-a", "median", ["median"])
        self.lagging(first)
        self.duty()
        for name in VALIDATORS:
            self.wake(name, "the end: every host up for the checks")
        self.verify()
        self.measure()

    def outbound(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("O", "outbound only: no validator's Radicle node listens or can be dialled; each dialled the seed "
                          "alone and every session on its side is outbound")
        seed_nid = R.nid(rad.did["seed"])
        seed_log = rad.sh("seed", "cat $RAD_HOME/node/node.log", check=False)
        for name in VALIDATORS:
            cfg = json.loads(rad.sh(name, "cat $RAD_HOME/config.json"))["node"]
            net = rad.sh(name, "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null", check=False)
            socks = listening(net)
            # its node container: no interface but lo, and radicle-node reached through the shared control socket
            side = VS.docker("exec", rad.c(name) + NODE_SUFFIX, "bash", "-c",
                             "echo $(ls /sys/class/net); rad node status 2>&1 | head -1", check=False).splitlines()
            dial = rad.sh("seed", f"timeout 3 bash -c '</dev/tcp/{name}/8776' >/dev/null 2>&1 && echo open || "
                                  f"echo refused", check=False)
            status = rad.sh(name, "rad node status 2>&1 | head -1", check=False)
            log = rad.sh(name, "cat $RAD_HOME/node/node.log", check=False)
            dirs = re.findall(r"Connected to (\S+) \(([^)]*)\) \((Inbound|Outbound)\)", log)
            inbound_at_seed = len(re.findall(rf"Connected to {R.nid(rad.did[name])} \([^)]*\) \(Inbound\)", seed_log))
            policies = sorted(set(re.findall(r"rad:z[1-9A-HJ-NP-Za-km-z]+", rad.sh(name, "rad seed", check=False))))
            self.must(cfg["listen"] == [] and cfg["externalAddresses"] == [] and cfg["connect"] == [self.seed_addr]
                      and cfg["peers"] == {"type": "static"} and cfg["network"] == KIT_NETWORK
                      and cfg["seedingPolicy"] == {"default": "block"} and policies == [rad.rid["a"]]
                      and not socks and dial == "refused"
                      and len(side) == 2 and side[0] == "lo" and "Node is running" in side[1]
                      and "not configured to listen" in status
                      and dirs and all(d == "Outbound" and peer == seed_nid for peer, _, d in dirs)
                      and inbound_at_seed >= 1,
                      f"{name}: listen [], no external address, connect [the seed], static peers, {KIT_NETWORK} "
                      f"network, policy block + the RID only; "
                      f"listening sockets {socks or 'none'} besides Docker's resolver on 127.0.0.11, the seed's dial to "
                      f"{name}:8776 {dial}, "
                      f"`rad node status`: \"{status[:80]}\"; its node container's interfaces: "
                      f"{side[0] if side else '?'}, and there `rad node status` (the socket): "
                      f"\"{side[1][:40] if len(side) > 1 else '?'}\"; its sessions {sorted({d for _, _, d in dirs})} to the "
                      f"seed only; the seed logged {inbound_at_seed} inbound session(s) from it")
        self.kit["outbound"] = {"validators": len(VALIDATORS), "seed": self.seed_addr}

    def asleep_fix(self, key: str, role: str, func: str, funcs: list) -> dict:
        """A fix opened while every validator's host is stopped; the watcher starts the drawn judges' hosts."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario(key, "a patch opened while every validator's host is stopped: the seed holds it; the watcher "
                          "starts each drawn judge's host; its node fetches the patch from the seed and judges it")
        for name in VALIDATORS:
            self.sleep(name)
        stopped = [x for x in VALIDATORS if "Node is stopped" in rad.sh(x, "rad node status 2>&1 | head -1",
                                                                         check=False)]
        self.must(len(stopped) == 7, f"every validator's host is stopped: {len(stopped)} of 7 Radicle nodes stopped")
        x = self.issues[func]
        b = x["bounty"]
        base = self.head()
        label = f"fix {func} (unfunded, opened while the validators sleep)"
        sha = rad.commit_on("solver", "a", base, SR.files_with(funcs), label)
        d = self.ctl("submit", "--bounty", b, "--patch", sha, "--title", label, as_=role)
        s = d["submission"]
        c.live[s] = True
        opened = rad.sh("solver", f"cd {SR.REPO} && {d['patchCommand']} 2>&1", check=False)
        m = re.search(r"Patch ([0-9a-f]{40}) opened", opened)
        self.must(m is not None, f"{role} sealed submission {s} with pofctl and opened its patch on the solver's node "
                                 f"(connected to the seed only)" + ("" if m else f": {opened[-300:]}"))
        pid = m.group(1)
        t_open = time.time()
        rad.sync("a", ["solver"], "announce")
        on_seed = self.until(lambda: self.patch_on("seed", pid), 30)
        self.must(on_seed and len(self.asleep) == 7,
                  f"patch {pid[:7]} is on the seed while all 7 validators' hosts are stopped")
        self.awaited = {pid: t_open}
        n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s)["paid"],
                f"{label}: judged", poke=True)
        v = c.verdict(s)
        drawn = [n.name(k) for k in n.panel.drawn(s)]
        woken = [w for w in self.wakes if w["at"] >= t_open]
        by_watcher = {w["node"] for w in woken if w["why"] == "the watcher"}
        listed = {w["node"] for w in woken if pid[:7] in w.get("patchesListed", [])}
        docs = self.receipts(s)
        tests = [d_["receipt"]["tests"] for _, d_ in docs if d_]
        fetched = all((n.work / "src" / name / sha).is_dir() for name in drawn)
        self.must(set(drawn) <= by_watcher and set(drawn) <= listed,
                  f"the watcher started each drawn judge's host on its Seated event ({', '.join(drawn)}; it started "
                  f"{len(by_watcher)} host(s) in all, for any seat), and each one's node had the patch, opened while "
                  f"it was stopped, right after its ready step (wake to ready: "
                  f"{', '.join(str(w['wakeToReadyS']) + ' s' for w in woken if w['node'] in drawn)})")
        self.must(v["k"] == 3 and v["pass"] and len(tests) == 3 and fetched
                  and all(t["exit_code"] == 0 and len(t["runs"]) == 2 for t in tests),
                  f"a counted panel of 3 judged it from their own nodes' storage: each fetched commit {sha[:12]}, ran "
                  f"the tests twice, and the fix passes")
        out = {"label": label, "submission": s, "fix": sha, "base": base, "patch": pid, "drawn": drawn,
               "woken": sorted(by_watcher), "bounty": b, "role": role, "salt": d["salt"]}
        self.awaited = {}
        for name in VALIDATORS:  # idle: each host powers off
            self.sleep(name)
        self.ctl("claim", "--bounty", b, "--patch", sha, "--base", base, "--salt", d["salt"], as_=role)
        n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"{label}: final", poke=True)
        for name in VALIDATORS:
            self.sleep(name)
        mr = self.ctl("merge", "--bounty", b, as_=role)
        self.must(mr["merged"] and self.head() == sha,
                  f"claimed, final (any audit's host started by the watcher too), and merged at finality "
                  f"({'already by the keeper' if mr.get('already') else 'with pofctl'}) while every validator's host "
                  f"is stopped: Heads.head {base[:12]} -> {sha[:12]}")
        return out

    def lagging(self, fix: dict) -> None:
        res, rad = self.res, self.rad
        sha, base = fix["fix"], fix["base"]
        res.scenario("L", "the canonical main while the delegates sleep: it lags Heads.head until 4 of the 7 "
                          "delegates' hosts have been up; then it follows through the seed")
        ran = self.watch()
        self.must(all(r["action"] == "idle" for r in ran.values()) and len(self.asleep) == 7,
                  "without the Radicle duty, the merge starts no host: every watcher idle (no seat is due)")
        canon, votes = self.seed_view(sha)
        code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('solver')}")
        self.must(canon == base and not votes and code != 0,
                  f"the canonical main on the seed is still {base[:12]} (no delegate has pushed {sha[:12]}), and "
                  f"pofctl verify-head on the solver's node refuses (exit {code}: {out.splitlines()[-1][:160]})")
        three = VALIDATORS[:3]
        t = time.time()
        for name in three:
            self.wake(name, "drawn for another check")
        self.push_pass(three)
        got = self.until(lambda: len(self.seed_view(sha)[1]) >= 3, 60)
        canon, votes = self.seed_view(sha)
        self.must(got and canon == base and votes == sorted(three),
                  f"three delegates' hosts up ({', '.join(three)}): each pushed its main to Heads.head and the seed "
                  f"has them ({len(votes)} votes), but the canonical main is still {base[:12]}: 3 of the 4 needed")
        fourth = VALIDATORS[3]
        self.wake(fourth, "drawn for another check")
        self.push_pass([fourth])
        on_seed = self.until(lambda: self.seed_view(sha)[0] == sha, 60)
        seed_s = round(time.time() - t, 1)
        rad.sync("a", ["solver"])
        on_solver = self.until(lambda: rad.canonical("solver", "a") == sha, 60)
        self.kit_node("viewer", rad.rid["a"], self.seed_addr)
        head = rad.sh("viewer", f"rm -rf fresh && rad clone {rad.rid['a']} fresh --scope all --no-confirm "
                                f">/dev/null 2>&1; git -C fresh rev-parse HEAD 2>/dev/null || echo none", check=False)
        code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('solver')}")
        self.must(on_seed and on_solver and head == sha and code == 0,
                  f"the fourth ({fourth}) made it canonical: the seed's canonical main is {sha[:12]} = Heads.head "
                  f"({seed_s} s after the first of the four woke), the solver's node has it, a fresh node connected only "
                  f"to the seed clones it (HEAD {head[:12]}), and verify-head exits 0")
        self.kit["lag"] = {"threshold": 4, "votesBelow": 3, "canonicalAfterFourS": seed_s}
        for name in VALIDATORS:
            self.sleep(name)

    def duty(self) -> None:
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        self.watchers_on(wake_on_head=True)
        ran = self.watch()  # the first run with the duty records Heads.head
        self.must(all(r["action"] == "idle" for r in ran.values()) and len(self.asleep) == 7,
                  "WAKE_ON_HEAD on: each watcher's first run records Heads.head and starts nothing")
        second = self.asleep_fix("B", "solver-b", "mode", ["median", "mode"])
        sha = second["fix"]
        res.scenario("W", "the watcher's Radicle duty: at the merge it starts every delegate's host once and the "
                          "canonical main follows Heads.head with no other draw")
        t = time.time()
        ran = self.watch()
        started = sorted(x for x, r in ran.items() if r["action"] == "started" and r.get("radicle"))
        self.must(started == sorted(VALIDATORS) and not self.asleep,
                  f"the merge moved Heads.head: every watcher started its host once for it ({len(started)} of 7, "
                  f"`radicle: true`, head {ran[VALIDATORS[0]].get('head', '')[:12]})")
        end = time.time() + FOLLOW_S
        while time.time() < end and self.seed_view(sha)[0] != sha:
            self.push_pass(VALIDATORS)
            time.sleep(1)
        canon, votes = self.seed_view(sha)
        secs = round(time.time() - t, 1)
        rad.sync("a", ["solver"])
        ok_solver = self.until(lambda: rad.canonical("solver", "a") == sha, 60)
        code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('solver')}")
        again = self.watch()
        self.must(canon == sha and ok_solver and code == 0 and all(r["action"] == "running" or r["action"] == "idle"
                                                                   for r in again.values()),
                  f"the canonical main on the seed and on the solver's node is {sha[:12]} = Heads.head, {secs} s "
                  f"after the watchers' run ({len(votes)} delegates pushed); verify-head exits 0; the next run starts "
                  f"nothing more")
        self.kit["duty"] = {"started": len(started), "followS": secs, "votes": len(votes)}
        for name in VALIDATORS:
            self.sleep(name)

    def measure(self) -> None:
        res = self.res
        res.scenario("T", "the wakes: radicle-node's start and the ready step (wall time on this machine)")
        ws = [w for w in self.wakes]
        if ws:
            node = sorted(w["radicleNodeS"] for w in ws)
            ready = sorted(w["readyS"] for w in ws)
            mid = len(ws) // 2
            res.ok(f"{len(ws)} wakes: radicle-node running in {node[0]}-{node[-1]} s (median {node[mid]}); the ready "
                   f"step (sync with the seed, working copy) {ready[0]}-{ready[-1]} s (median {ready[mid]})")
        res.meas["wakes"] = self.wakes
        res.meas["watcher"] = self.watch_log
        res.meas["kit"] = self.kit

    def isolation(self, others: tuple = ("anvil", "relay")) -> None:
        """The spike's check (spikes/radicle/v3_spike.py `isolation`), with one difference for the nodes configured as
        the kit's: they run on Radicle's main network, as the disk does, so radicle-node adds main's bootstrap nodes
        to an empty address book ("4 nodes added", on a node with no seed in `connect`); the kit's static peers must
        never dial them. Plus no inbound session on any validator's node over the whole run, every session's log
        included."""
        res, rad = self.res, self.rad
        res.scenario("I", "isolation: internal network, no route out, nodes dialled only each other, no public "
                          "hostname in the logs; the kit's nodes never dial main's bootstrap nodes")
        res.expect(f"network {VS.NET} is internal", VS.docker("network", "inspect", "-f", "{{.Internal}}", VS.NET),
                   "true")
        subnet = VS.docker("network", "inspect", "-f", "{{range .IPAM.Config}}{{.Subnet}}{{end}}", VS.NET)
        prefix = ".".join(subnet.split(".")[:2]) + "."
        for x in others:
            routes = VS.docker("exec", f"{VS.P}-{x}", "awk", '$2 == "00000000"', "/proc/net/route").splitlines()
            res.expect(f"{x}: default routes", len(routes), 0)
        names = set(rad.started)
        bootstrap = 0
        for n in rad.started:
            routes = rad.sh(n, "awk '$2 == \"00000000\"' /proc/net/route | wc -l", check=False)
            text = rad.sh(n, f"cat {LOGS}/radicle-node.log $RAD_HOME/node/node.log 2>/dev/null", check=False)
            (OUT / f"{n}.log").write_text(text, encoding="utf-8")
            sessions = text.count("Starting node..")
            added = set(re.findall(r" (\d+) nodes added to address book", text)) - {"0"}
            kit = n != "seed"
            dialled = set()
            for line in text.splitlines():
                if re.search(r"Connecting to|Attempted connection to|Connected to", line):
                    dialled |= set(re.findall(r"\(([^()]*):\d+\)", line))
            foreign = {h for h in dialled if h not in names and not h.startswith(prefix)}
            ips = {ip for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
                   if not ip.startswith((prefix, "127.")) and ip != "0.0.0.0"}
            public = len(re.findall(r"radicle\.(xyz|garden|dev|network)|seed\.radicle|iris\.|rosa\.", text, re.I))
            bootstrap += bool(added)
            res.check(routes == "0" and (kit or not added) and not foreign and not ips and public == 0,
                      f"{n}: {sessions} radicle-node session(s), {routes} default routes, "
                      f"{'main' if kit else 'test'} network, bootstrap nodes in its "
                      f"address book {sorted(added) or 0} (dialled: none), dialled {sorted(dialled)}, IPs outside "
                      f"{subnet}: {sorted(ips) or 'none'}, public Radicle hostnames: {public}")
        # radicle-node adds main's bootstrap nodes only to an empty address book: a node with the seed in `connect`
        # (every validator's) never has them; the owner's (no `connect`, like an attest-only boot) does, and its
        # static peers must still dial none
        res.check(bootstrap >= 1, f"main's bootstrap nodes were in the address book of {bootstrap} kit node(s) with "
                                  f"no seed configured, and static peers dialled none of them; with the seed in "
                                  f"`connect` (every validator) radicle-node adds none")
        for name in VALIDATORS:
            if name not in rad.started:
                continue
            log = rad.sh(name, f"cat {LOGS}/radicle-node.log $RAD_HOME/node/node.log 2>/dev/null", check=False)
            peers = {peer for peer, _, _ in re.findall(r"Connected to (\S+) \(([^)]*)\) \((Inbound|Outbound)\)", log)}
            res.check("(Inbound)" not in log and log.count("Starting node..") > 1 and peers == {R.nid(rad.did["seed"])},
                      f"{name}: no inbound session over the whole run ({log.count('Starting node..')} radicle-node "
                      f"sessions, {log.count('(Outbound)')} outbound connections, all to the seed)")


_spike_clean = VS.clean


def clean() -> None:
    """The spike's clean-up (containers by prefix, the network, the record), plus this run's named volumes: each
    validator's /data, shared by its Radicle node and its node container."""
    _spike_clean()
    vols = VS.docker("volume", "ls", "-q", "--filter", f"name=^{PREFIX}-", check=False).split()
    if vols:
        VS.docker("volume", "rm", "-f", *vols, check=False)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    VS.use_names(PREFIX, NODES, OUT, RECORD_DIR)
    VS.clean = clean  # v3_spike's run() calls it before and after
    SR.OUT = OUT  # task 4.6's Story keeps its scratch here, beside this run's results
    SR.RadNet = KitNet
    if a.command == "clean":
        clean()
        SR.fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return KitStory(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
