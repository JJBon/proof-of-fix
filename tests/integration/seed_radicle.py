"""The proof-of-fix seed on the internal Docker network (proof-of-fix#251, task 5.3; design L14). Run it with
`scripts/radicle-spike.sh --seed`, which builds the spike's node image (spikes/radicle/Dockerfile: the pinned Radicle
1.10.3 release, checked by SHA-256) and calls this file. `python3 tests/integration/seed_radicle.py clean` removes
anything a stopped run left behind.

Not a new harness: the Radicle spike's (spikes/radicle/v3_spike.py) containers, `Rad` helpers, results and isolation
check, under their own names (`use_names`). What is new is the seed, configured exactly as the AWS host configures it:
seed/radicle/seed-setup.sh (the key, seed/radicle/config.json with the "block" default, the one seeding policy) run in
the seed's container, and radicle-node started with seed/radicle/radicle-seed.service's ExecStart line. The RID it
seeds is read from a publication record (seed/publication.py) written after the publish, as task 6.2 will write it.

  P. publish: a publisher node `rad init`s proof-of-fix (one root commit) and a second repository; the record is
     written; only then is the seed configured from it and started;
  R. replicate: the seed replicates proof-of-fix from the publisher, its canonical `main` the root commit;
  X. refuse: the publisher announces the second repository straight to the seed, and the seed doesn't fetch, store or
     serve it; its only seeding policy is proof-of-fix's;
  F. fetch through the seed: with the publisher's node stopped, a fresh node connected only to the seed clones
     proof-of-fix from it (HEAD = the root commit), and its clone of the second repository from the seed fails;
  M. the seed's radicle-node memory (peak and current RSS), for the instance's size (seed/README.md);
  I. isolation (the spike's check): the internal network, no route out, the nodes dialled only each other, no public
     Radicle host in their logs.

Radicle's `test` network (no bootstrap nodes) is the only difference from the host's config (`main`). No AWS, no
public network, nothing published. Results and node logs stay in .seed-radicle/ (gitignored)."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle", ROOT / "seed"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import publication  # noqa: E402
import v3_spike as VS  # noqa: E402
from oracle import radicle as R  # noqa: E402

PREFIX = "pof251seed"
NODES = ["publisher", "seed", "fresh"]
OUT = ROOT / ".seed-radicle"
RECORD_DIR = OUT / "record"
SEED_DIR = ROOT / "seed" / "radicle"
SEED_FILES = "/opt/radicle-seed"  # where the seed's files go in its container (the host's /usr/local/lib/radicle-seed)
WAIT_S = 45  # how long a passive replication is watched before a sync is asked for


def exec_start() -> str:
    """radicle-node's command line, from the systemd unit the host runs."""
    unit = (SEED_DIR / "radicle-seed.service").read_text(encoding="utf-8")
    m = re.search(r"^ExecStart=(.+)$", unit, re.M)
    if not m:
        raise RuntimeError("radicle-seed.service has no ExecStart")
    return m.group(1).strip()


class SeedTest:
    def __init__(self, keep: bool) -> None:
        self.keep = keep
        self.spike = VS.Spike(keep)  # its Results, Rad, isolation check and results file
        self.res, self.rad = self.spike.res, self.spike.rad
        self.root = ""

    # ---------- the seed, as the host runs it ----------

    def start_seed(self, rid: str) -> None:
        rad, n = self.rad, "seed"
        VS.docker("run", "-d", "--name", rad.c(n), "--hostname", n, "--network", VS.NET, "--network-alias", n,
                  VS.IMAGE)
        VS.docker("cp", f"{SEED_DIR}/.", f"{rad.c(n)}:{SEED_FILES}")
        self.setup_out = rad.sh(n, f"bash {SEED_FILES}/seed-setup.sh {shlex.quote(rid)} seed seed:8776 test 2>&1")
        rad.did[n] = self.setup_out.splitlines()[-1].strip()
        rad.sh(n, f"mkdir -p $RAD_HOME/node && (setsid nohup {exec_start()} >$RAD_HOME/node/node.log 2>&1 &) && "
                  "for _ in $(seq 60); do rad node status >/dev/null 2>&1 && break; sleep 0.5; done && rad node status")
        rad.started.append(n)

    def has(self, n: str, repo: str) -> bool:
        return self.rad.sh(n, f"test -d {self.rad.store(repo)} && echo yes || echo no", check=False) == "yes"

    def watch(self, probe, timeout: float = WAIT_S) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            if probe():
                return True
            time.sleep(1)
        return bool(probe())

    def memory(self) -> dict:
        out = self.rad.sh("seed", "for p in /proc/[0-9]*; do [ \"$(cat $p/comm 2>/dev/null)\" = radicle-node ] && "
                                  "grep -E '^(VmHWM|VmRSS):' $p/status; done", check=False)
        return {k: int(v) for k, v in re.findall(r"^(VmHWM|VmRSS):\s+(\d+) kB", out, re.M)}

    # ---------- the story ----------

    def publish(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("P", "publish: proof-of-fix and a second repository; the record; then the seed, from the record")
        rad.start("publisher")
        # proof-of-fix: this repository's tracked files at HEAD, as one root commit (what task 5.1's snapshot is);
        # the other: one file.
        rad.sh("publisher", f"mkdir {rad.wd('pof')} {rad.wd('other')} && "
                            f"echo 'another repository the seed must refuse' > {rad.wd('other')}/README.md")
        tree = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD"], capture_output=True,
                              check=True, timeout=120).stdout
        subprocess.run(["docker", "exec", "-i", rad.c("publisher"), "tar", "-x", "-C", rad.wd("pof")], input=tree,
                       capture_output=True, check=True, timeout=120)
        res.info(f"proof-of-fix's snapshot: {len(tree) // 10**6} MB of tracked files at this repository's HEAD")
        for repo, name in (("pof", "proof-of-fix"), ("other", "not-proof-of-fix")):
            rad.sh("publisher", f"cd {rad.wd(repo)} && git init -q -b main && git add -A && "
                                f"git commit -q -m {shlex.quote('root: ' + name)} && "
                                f"rad init --name {name} --description {shlex.quote(name)} --default-branch main "
                                f"--public --no-confirm >/dev/null 2>&1")
            rad.rid[repo] = rad.sh("publisher", f"cd {rad.wd(repo)} && rad .")
        roots = rad.sh("publisher", f"cd {rad.wd('pof')} && git rev-list --max-parents=0 HEAD").split()
        res.expect("proof-of-fix's root commits", len(roots), 1)
        self.root = roots[0]
        record = {"format": publication.FORMAT, "rid": rad.rid["pof"], "rootCommit": self.root,
                  "nodeId": R.nid(rad.did["publisher"]), "radicle": publication.RADICLE}
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        path = RECORD_DIR / "publication.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        rid = publication.rid(path)
        res.expect("the RID the seed is given comes from the record", rid, rad.rid["pof"])
        res.info(f"proof-of-fix {rad.rid['pof']} (root {self.root[:12]}); the other {rad.rid['other']}")
        self.start_seed(rid)
        res.ok(f"seed {rad.did['seed']} configured by seed-setup.sh and started with `{exec_start()}`")
        cfg = json.loads(rad.sh("seed", "cat $RAD_HOME/config.json"))
        res.expect("the seed's default seeding policy", cfg["node"]["seedingPolicy"], {"default": "block"})
        res.expect("the seed's external address", cfg["node"]["externalAddresses"], ["seed:8776"])
        res.expect("the seed's seeding policies (`rad seed`)", self.policies(), [rad.rid["pof"]])
        res.expect("radicle on the seed", rad.sh("seed", "rad --version"),
                   "rad 1.10.3 (7e1cb406bb935c3de008d2171e8961f57b4336ea)")
        self.idle = self.memory()
        rad.connect("publisher", "seed")  # the publisher dials the seed's external address

    def policies(self) -> list:
        return sorted(set(re.findall(r"rad:z[1-9A-HJ-NP-Za-km-z]+", self.rad.sh("seed", "rad seed", check=False))))

    def replicate(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("R", "replicate: the seed fetches proof-of-fix from the publisher")
        start = time.time()
        got = self.watch(lambda: rad.canonical("seed", "pof") == self.root)
        how = f"passively in {round(time.time() - start)} s"
        if not got:
            rad.sync("pof", ["publisher"], "announce")
            got = self.watch(lambda: rad.canonical("seed", "pof") == self.root, 30)
            how = "after the publisher's `rad sync --announce`"
        res.check(got, f"the seed's canonical main of proof-of-fix is the root commit {self.root[:12]} ({how})")
        tips = rad.tips("seed", "pof")
        res.expect("the publisher's main on the seed", tips.get(R.nid(rad.did["publisher"])), self.root)

    def refuse(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("X", "refuse: the second repository, announced straight to the seed, is never fetched")
        seed_nid = R.nid(rad.did["seed"])
        out = rad.sh("publisher", f"rad sync --announce {rad.rid['other']} --seed {seed_nid} --timeout 30s 2>&1 || true",
                     check=False)
        res.info("publisher's announce to the seed: " + (out.strip().splitlines() or ["(no output)"])[-1][:200])
        time.sleep(10)  # time for a fetch the seed should not make
        # The seed heard of it (the publisher's inventory is in its routing table) and still didn't fetch it.
        routing = rad.sh("seed", f"rad node routing --rid {rad.rid['other']} --json 2>&1", check=False)
        res.check(R.nid(rad.did["publisher"]) in routing,
                  f"the seed's routing table has {rad.rid['other']} at the publisher (it was offered)")
        res.check(not self.has("seed", "other"), f"no {rad.rid['other']} in the seed's storage")
        res.expect("the seed's seeding policies after the announce", self.policies(), [rad.rid["pof"]])
        res.expect("the seed's repositories (`rad ls --all`)",
                   sorted(set(re.findall(r"rad:z[1-9A-HJ-NP-Za-km-z]+", rad.sh("seed", "rad ls --all 2>&1",
                                                                               check=False)))),
                   [rad.rid["pof"]])

    def fetch_through_seed(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("F", "a fresh node fetches proof-of-fix through the seed, the publisher stopped")
        rad.stop_node("publisher")
        rad.start("fresh")
        rad.connect("fresh", "seed")  # only the seed
        seed_nid = R.nid(rad.did["seed"])
        head = rad.sh("fresh", f"for _ in 1 2 3 4 5; do rad clone {rad.rid['pof']} pof --seed {seed_nid} "
                               f"--no-confirm >/dev/null 2>&1 && break; rm -rf pof; sleep 2; done; "
                               f"git -C pof rev-parse HEAD 2>/dev/null || echo none", check=False)
        res.expect("the fresh node's clone of proof-of-fix from the seed: HEAD", head, self.root)
        res.expect("its root commits", rad.sh("fresh", "git -C pof rev-list --max-parents=0 HEAD | wc -l",
                                              check=False), "1")
        out = rad.sh("fresh", f"rad clone {rad.rid['other']} other --seed {seed_nid} --no-confirm --timeout 15s 2>&1;"
                              f" echo \"@exit $?\"", check=False)
        code = re.search(r"@exit (\d+)", out)
        res.check(code is not None and code.group(1) != "0" and not self.has("fresh", "other"),
                  f"the fresh node's clone of the second repository from the seed fails (exit "
                  f"{code.group(1) if code else '?'}: "
                  f"{[x for x in out.splitlines() if x.strip() and not x.startswith('@exit')][-1:]})")

    def measure(self) -> None:
        res = self.res
        res.scenario("M", "the seed's radicle-node memory")
        now = self.memory()
        res.meas["seedMemoryKiB"] = {"idle": self.idle, "after": now}
        res.check(bool(now), f"radicle-node RSS idle {self.idle.get('VmRSS', '?')} KiB; after replicating and serving "
                             f"{now.get('VmRSS', '?')} KiB, peak {now.get('VmHWM', '?')} KiB")

    def run(self) -> int:
        res, rad = self.res, self.rad
        VS.clean()
        shutil.rmtree(OUT, ignore_errors=True)
        OUT.mkdir(parents=True)
        started = time.time()
        try:
            VS.docker("network", "create", "--internal", VS.NET)
            for step in (self.publish, self.replicate, self.refuse, self.fetch_through_seed, self.measure):
                step()
        except Exception as e:  # noqa: BLE001 (recorded as the current scenario's failure, then cleaned up)
            res.bad(f"aborted: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            try:
                if rad.started:
                    self.spike.isolation(others=())
            except Exception as e:  # noqa: BLE001
                res.scenario("I", "isolation")
                res.bad(f"aborted: {type(e).__name__}: {e}")
            self.spike.radicle_version = rad.sh("seed", "rad --version", check=False) if "seed" in rad.started else ""
            self.spike.started = started
            self.spike.write()
            if not self.keep:
                VS.clean()
                left = VS.leftovers()
                VS.log(f"cleaned up: {'nothing left' if not left else 'LEFT ' + left}")
        return 0 if res.result and all(v == "PASS" for v in res.result.values()) else 1


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    VS.use_names(PREFIX, NODES, OUT, RECORD_DIR)
    if a.command == "clean":
        VS.clean()
        shutil.rmtree(OUT, ignore_errors=True)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return SeedTest(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
