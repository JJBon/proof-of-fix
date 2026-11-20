"""Radicle merges in the integration suite (proof-of-fix#201): scenario 8, run by scripts/integration.sh --radicle.

#190's spike showed that judges can merge on Radicle as the repository's delegates. Here it's wired end to end with the
seats' real node processes (python3 -m oracle run, the fake judge, no model call) and RaceV2.merged(): the merge the
chain records is the commit that became Radicle's canonical main by the delegates' votes, and it must be Heads' head.

The network is local and isolated, as the spike's: heartwood 1.10.3 (spikes/radicle/Dockerfile, the release pinned by
sha256; the image is built only if it isn't there yet, and that build is the only download), one node per seat (the 7
delegates, threshold 2 = the issue quorum) plus an outsider node, on a Docker network created with --internal (no route
out), Radicle's test network (no bootstrap nodes), no seeds, static peers connected by name. Nothing touches Radicle's
public network. Keys are throwaway, made in the containers and never printed.

    python3 tests/integration/radicle.py up --work .integration   the network and the repository, before the deploy:
                                                                  prints "<RID> <genesis commit>" for Heads' genesis
    python3 tests/integration/radicle.py down                     remove its containers and network

Scenario 8 (suite.py runs it with --radicle; each part on its own bounty, registered in the head registry):
  8a. the happy path merged on Radicle: judged, the drawn judges push, canonical main moves at the threshold, the
      merge is signed from it and relayed (Heads moves to the same commit), settled and paid; verify-head agrees;
  8b. an outsider's push (not a delegate) to its own main, and its patch: canonical main doesn't move on any node, the
      node's own count ignores it, and the chain records nothing;
  8c. fewer delegates than the threshold push (two of the drawn judges' nodes are offline at the merge; the outsider
      pushes too, and doesn't count): canonical main doesn't move, nothing is signed, and once the merge deadline
      passes (mergeDays) RaceV2.mergeExpired reopens the bounty with nothing paid;
  8d. Heads and canonical main disagree (two delegates skip the check and push an unjudged commit): verify-head refuses,
      and the drawn judges' nodes neither vote nor sign; the bounty stays Won and Heads doesn't move;
  8e. isolation: the network is internal, no node has a default route, and every node's log dialled only the suite's
      nodes (the spike's checks)."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from oracle import radicle as rad  # noqa: E402
from oracle import v2  # noqa: E402
from oracle.crypto import address, keccak256  # noqa: E402
from oracle.rpc import Reverted, Wallet  # noqa: E402
from pofctl import keys  # noqa: E402

IMAGE = "pof190-radicle:spike"  # spikes/radicle/Dockerfile: heartwood 1.10.3, its release checked by sha256
SEATS = ("oracle-0", "oracle-1", "oracle-2", "oracle-3", "oracle-4", "joiner-0", "engineer")  # the delegates
OUTSIDER = "outsider"
NODES = SEATS + (OUTSIDER,)
HOME_C = "/home/foundry"
THRESHOLD = v2.ISSUE_QUORUM
HEAD_MOVED = "0x" + keccak256(b"HeadMoved(bytes32,bytes32,bytes32,uint256,uint256,bytes32)").hex()
AWARDED = "0x" + keccak256(b"Awarded(uint256,uint256,address)").hex()
GIT_ENV = {"GIT_AUTHOR_NAME": "suite", "GIT_AUTHOR_EMAIL": "suite@localhost", "GIT_COMMITTER_NAME": "suite",
           "GIT_COMMITTER_EMAIL": "suite@localhost"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def prefix() -> str:
    return (os.environ.get("DEVNET_NAME") or "pof-devnet-integration") + "-rad"


def git(cwd, *args) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


class Net:
    """The suite's Radicle network: one container per node, on an internal Docker network."""

    def __init__(self, work, p: str | None = None) -> None:
        self.dir = Path(work).resolve() / "radicle"
        self.p = p or prefix()
        self.net = f"{self.p}-net"
        f = self.dir / "state.json"
        self.state = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    @property
    def rid(self) -> str:
        return self.state["rid"]

    def did(self, n: str) -> str:
        return self.state["dids"][n]

    def c(self, n: str) -> str:
        return f"{self.p}-{n}"

    def exec_prefix(self, n: str) -> str:
        return f"docker exec -i {self.c(n)}"

    @staticmethod
    def docker(*args, check: bool = True, stdin=None) -> str:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, stdin=stdin)
        if check and r.returncode:
            raise RuntimeError(f"docker {' '.join(args[:3])}: {r.stderr.strip()[-400:]}")
        return r.stdout.strip()

    def sh(self, n: str, script: str, check: bool = True) -> str:
        return self.docker("exec", "-w", HOME_C, self.c(n), "bash", "-c", script, check=check)

    def storage(self) -> str:
        return f"$RAD_HOME/storage/{self.rid[4:]}"

    # ---------- up and down ----------

    def clean(self) -> None:
        ids = self.docker("ps", "-aq", "--filter", f"name=^{self.p}-", check=False).split()
        if ids:
            self.docker("rm", "-f", *ids, check=False)
        self.docker("network", "rm", self.net, check=False)

    def up(self) -> dict:
        self.clean()
        if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode:
            log(f"radicle: building {IMAGE} (spikes/radicle: the pinned release, sha256-checked) ...")
            subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(ROOT / "spikes" / "radicle")], check=True,
                           stdout=subprocess.DEVNULL)
        self.docker("network", "create", "--internal", self.net)
        dids = {}
        for n in NODES:
            self.docker("run", "-d", "--name", self.c(n), "--hostname", n, "--network", self.net, "--network-alias", n,
                        IMAGE)
            dids[n] = self.sh(n, f"node-init.sh {n} 2>/dev/null")
        for i, a in enumerate(NODES):  # a full mesh among the suite's nodes, and nothing else
            for b in NODES[i + 1:]:
                self.sh(a, f"rad node connect {rad.nid(dids[b])}@{b}:8776 >/dev/null")
        # The repository: the sample code (bot/sample) as its first commit, made here and carried in as a bundle.
        self.dir.mkdir(parents=True, exist_ok=True)
        gdir = self.dir / "genesis"
        shutil.rmtree(gdir, ignore_errors=True)
        gdir.mkdir()
        git(gdir, "init", "-q", "-b", "main")
        for f in (ROOT / "bot" / "sample").iterdir():
            if f.is_file():
                shutil.copy(f, gdir / f.name)
        git(gdir, "add", "-A")
        git(gdir, "commit", "-q", "-m", "the sample code (proof-of-fix#201's Radicle target)")
        genesis = git(gdir, "rev-parse", "HEAD")
        git(gdir, "bundle", "create", str(self.dir / "genesis.bundle"), "main")
        first = SEATS[0]
        with open(self.dir / "genesis.bundle", "rb") as fh:
            self.docker("exec", "-i", self.c(first), "bash", "-c", "cat > /tmp/genesis.bundle", stdin=fh)
        self.sh(first, "git clone -q -b main /tmp/genesis.bundle repo && cd repo && git remote remove origin && "
                       "rad init --name pof-target --description 'proof-of-fix#201 suite target' --default-branch main "
                       "--public --no-confirm >/dev/null 2>&1")
        rid = self.sh(first, "cd repo && rad .")
        if not rad.RID_RE.match(rid):
            raise RuntimeError(f"rad init gave no RID: {rid!r}")
        self.state = {"rid": rid, "genesis": genesis, "prefix": self.p, "dids": dids}
        for n in NODES[1:]:
            for _ in range(10):
                self.sh(n, f"rad clone {rid} repo --no-confirm >/dev/null 2>&1 || rm -rf repo", check=False)
                if subprocess.run(["docker", "exec", self.c(n), "test", "-d", f"{HOME_C}/repo/.git"]).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(f"{n} couldn't clone {rid}")
        # A delegate must have published the default branch before it can be added (#190).
        for n in SEATS[1:]:
            self.sh(n, "cd repo && git push -q rad main 2>/dev/null")
        delegates = " ".join(f"--delegate {dids[n]}" for n in SEATS[1:])
        self.sync_on(first)
        self.sh(first, f"cd repo && rad id update --title 'The seats are the delegates' "
                       f"--description 'Seven seats, threshold {THRESHOLD} = the issue quorum (proof-of-fix#201)' "
                       f"{delegates} --threshold {THRESHOLD} --no-confirm >/dev/null")
        self.sync_on(first, "announce")
        self.sync()
        for n in NODES:
            s = self.snapshot(n)
            if len(s.delegates) != len(SEATS) or s.threshold != THRESHOLD or s.canonical_ref != genesis:
                raise RuntimeError(f"{n}: {len(s.delegates)} delegates, threshold {s.threshold}, canonical main "
                                   f"{s.canonical_ref}")
        (self.dir / "state.json").write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        log(f"radicle: {self.sh(first, 'rad --version')}; {rid}, {len(SEATS)} delegates (the seats), threshold "
            f"{THRESHOLD}, genesis {genesis[:12]}; network {self.net} (internal)")
        return self.state

    # ---------- reading and pushing ----------

    def sync_on(self, n: str, mode: str = "fetch") -> str:
        """`rad sync --<mode> <RID>` on node `n` (the RID positional: Radicle 1.10.3 refuses `--rid`); a failure is
        logged, not hidden, and returned ("" when it worked)."""
        err = rad.sync_error(self.sh(n, rad.sync_lines(self.rid, mode), check=False))
        if err:
            log(f"radicle: {n}: {err}")
        return err

    def sync(self, nodes=NODES) -> None:
        for n in nodes:
            self.sync_on(n)

    def snapshot(self, n: str, sync: bool = False) -> rad.Snapshot:
        return rad.Radicle(self.rid, ["docker", "exec", "-i", self.c(n)]).snapshot(sync=sync)

    def canonical_on(self, n: str) -> str:
        return self.sh(n, f"git --git-dir {self.storage()} rev-parse refs/heads/main")

    def main_of(self, n: str, of: str) -> str:
        """`of`'s signed main, as node `n` has it."""
        return self.sh(n, f"git --git-dir {self.storage()} rev-parse --verify -q "
                          f"refs/namespaces/{rad.nid(self.did(of))}/refs/heads/main || echo none", check=False)

    def publish(self, bundle: Path, ref: str, sha: str) -> None:
        """The outsider (the solver's node: not a delegate) opens a patch with the fix, as proposals arrive."""
        with open(bundle, "rb") as fh:
            self.docker("exec", "-i", self.c(OUTSIDER), "bash", "-c", "cat > /tmp/fix.bundle", stdin=fh)
        self.sh(OUTSIDER, f"cd repo && git fetch -q /tmp/fix.bundle {ref}:refs/heads/p-{sha[:12]} && "
                          f"git checkout -q p-{sha[:12]} && git push -q rad HEAD:refs/patches 2>/dev/null; "
                          f"git checkout -q --detach")

    def commit_on(self, n: str, base: str, what: str) -> str:
        """An unjudged commit on top of `base`, made on node `n`."""
        self.sync_on(n)
        return self.sh(n, f"cd repo && git fetch -q {self.storage()} {base} && "
                          f"git checkout -q -B work {base} && printf '\\n# {what}\\n' >> stats.py && "
                          f"git commit -q -a -m '{what} (proof-of-fix#201)' && git rev-parse HEAD")

    def push_main(self, n: str, sha: str) -> None:
        """Node `n` pushes its own signed main to `sha` with no check at all (an outsider, or a delegate who skips the
        node's): what Radicle alone allows."""
        self.sync_on(n)
        self.sh(n, f"cd repo && {{ git cat-file -e {sha}^{{commit}} 2>/dev/null || "
                   f"git fetch -q {self.storage()} {sha}; }} && git push -q -f rad {sha}:refs/heads/main 2>/dev/null")

    # ---------- isolation (#190's checks) ----------

    def isolation(self, fail) -> int:
        if self.docker("network", "inspect", "-f", "{{.Internal}}", self.net) != "true":
            fail(f"network {self.net} isn't internal")
        subnet = self.docker("network", "inspect", "-f", "{{range .IPAM.Config}}{{.Subnet}}{{end}}", self.net)
        net_prefix = ".".join(subnet.split(".")[:2]) + "."
        checked = 0
        for n in NODES:
            routes = self.sh(n, "awk '$2 == \"00000000\"' /proc/net/route | wc -l")
            if routes != "0":
                fail(f"{n}: {routes} default route(s)")
            text = self.sh(n, "cat $RAD_HOME/node/node.log.* $RAD_HOME/node/node.log 2>/dev/null", check=False)
            (self.dir / f"{n}.log").write_text(text, encoding="utf-8")
            added = set(re.findall(r" (\d+) nodes added to address book", text))
            if added - {"0"}:
                fail(f"{n}: bootstrap nodes added to its address book: {sorted(added)}")
            dialled = set()
            for line in text.splitlines():
                if re.search(r"Connecting to|Attempted connection to|Connected to", line):
                    for host in re.findall(r"\(([^()]*):\d+\)", line):
                        dialled.add(host)
            foreign = {h for h in dialled if h not in NODES and not h.startswith(net_prefix)}
            if foreign:
                fail(f"{n}: dialled peers outside the suite's network: {sorted(foreign)}")
            ips = {ip for ip in re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
                   if not ip.startswith((net_prefix, "127.")) and ip != "0.0.0.0"}
            if ips:
                fail(f"{n}: IP addresses outside {subnet} in its log: {sorted(ips)}")
            if re.search(r"radicle\.(xyz|garden|dev|network)|seed\.radicle|iris\.|rosa\.", text, re.I):
                fail(f"{n}: a public Radicle hostname in its log")
            checked += 1
        return checked


class Scenarios:
    """Scenario 8, on the suite's devnet, repository host and seats (tests/integration/suite.py's Suite)."""

    def __init__(self, suite) -> None:
        self.s = suite
        self.net = Net(suite.work)
        self.chain = suite.chain
        self.repo = rad.repo_id(self.net.rid)
        self.heads = self.chain.heads()
        self.bot = Wallet(suite.rpc, keys.derive(keys.MNEMONIC, keys.ROLES.index("bot")), "bot")
        self.problems = 0

    def fail(self, part: str, what: str) -> None:
        self.problems += 1
        self.s.fail("8", f"{part}: {what}")

    def check(self, part: str, what: str, got, want) -> bool:
        if got == want:
            print(f"  ok   {what}: {got}")
            return True
        self.fail(part, f"{what}: got {got!r}, want {want!r}")
        return False

    # ---------- helpers ----------

    def head(self) -> str:
        return rad.sha_of(self.chain.head(self.repo)["commit"])

    def moved_since(self, block: int) -> list:
        return self.s.rpc.logs(self.heads, block, [HEAD_MOVED])

    def setup(self) -> None:
        if v2.b32(self.s.record["repo"]) != self.repo:
            raise RuntimeError("v2 wasn't deployed with the Radicle repository in Heads: run scripts/integration.sh "
                               "--radicle")
        git(self.s.clone, "fetch", "-q", str(self.net.dir / "genesis"), "main")
        git(self.s.clone, "push", "-q", str(self.s.bare), f"{self.net.state['genesis']}:refs/heads/radicle-genesis")
        print(f"  Radicle {self.net.rid}: 7 delegates (the seats), threshold {THRESHOLD}; Heads' genesis "
              f"{self.head()[:12]}")

    def new_bounty(self, label: str) -> tuple:
        s = self.s
        rep = s.ctl("reporter", "register", "--repo", "registry", show=False)
        gh_issue = s.gh.add_issue("demo/median", f"median() is wrong for an even count ({label})",
                                  f"`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\n"
                                  f"Reporter wallet: {rep['reporter']}\n", labels=["bounty"])
        bounty = s.ctl("oracle", "accept", "--issue", str(rep["issue"]), show=False)["bounty"]
        s.ctl("bot", "link", "--repo", "demo/median", "--issue", str(gh_issue), "--bounty", str(bounty), show=False)
        s.ctl("funder", "fund", "--bounty", str(bounty), "--amount", "100", show=False)
        print(f"  bounty {bounty} (in the head registry): registered, accepted, linked to issue #{gh_issue}, funded 100")
        return bounty, gh_issue

    def submit(self, bounty: int, gh_issue: int, solver: str) -> tuple:
        """A passing fix on top of Heads' head: committed, sealed, its pull request opened (the claim the nodes read),
        and published on Radicle as the outsider's patch. Returns (submission, the fix's commit, the drawn seats)."""
        s, base = self.s, self.head()
        clone = str(s.clone)
        git(clone, "checkout", "-q", "--detach", base)
        shutil.copy(ROOT / "bot" / "fixes" / "good_stats.py", s.clone / "stats.py")
        shutil.copy(ROOT / "bot" / "acceptance" / "test_issue_median_even.py", s.clone)
        with open(s.clone / "stats.py", "a", encoding="utf-8") as fh:
            fh.write(f"\n# {solver}'s fix for bounty {bounty} ({secrets.token_hex(4)})\n")
        git(clone, "add", "-A")
        git(clone, "commit", "-q", "-m", f"fix the median (bounty {bounty}, {solver})")
        sha = git(clone, "rev-parse", "HEAD")
        ref = f"refs/heads/fix-{sha[:12]}"
        git(clone, "push", "-q", str(s.bare), f"HEAD:{ref}")
        r = s.ctl("solver", "submit", "--bounty", str(bounty), "--commit", sha, "--issue", str(gh_issue),
                  as_role=solver, show=False)
        sub = r["submission"]
        pr = s.gh.add_pull("demo/median", "Fix the median (on Radicle)", r["prBody"], sha, user=solver, base_sha=base)
        s.submissions[sub] = {"solver": address(keys.derive(keys.MNEMONIC, keys.ROLES.index(solver))),
                              "deposit": r["deposit"], "judges": r["judges"], "bounty": bounty}
        bundle = self.net.dir / f"fix-{sha[:12]}.bundle"
        git(str(s.bare), "bundle", "create", str(bundle), ref)
        self.net.publish(bundle, ref, sha)
        drawn = [s.names[j.lower()] for j in r["judges"]]
        print(f"  {solver} sealed {sha[:12]} on {base[:12]}: submission {sub}, drawn {', '.join(drawn)}; pull request "
              f"#{pr} (the claim) and the outsider's patch on Radicle")
        return sub, sha, drawn

    def run_nodes(self, label: str, skip=(), radicle: bool = True, idle: int = 25) -> dict:
        """The seats' nodes until each is idle, each reaching its own Radicle node (or the forge path, radicle=False).
        Returns each node's log written during this run."""
        s = self.s
        env = s.node_env()
        if radicle:
            env.update({"ORACLE_MERGE_VIA": "radicle", "ORACLE_RADICLE_RID": self.net.rid})
        sizes = {n: (s.work / f"node-{n}.log").stat().st_size if (s.work / f"node-{n}.log").exists() else 0
                 for n in s.seat_keys}
        procs = [s.start(n, {**env, "ORACLE_RADICLE_EXEC": self.net.exec_prefix(n)} if radicle else env, idle)
                 for n in s.seat_keys if n not in skip]
        for name, fh, p in procs:
            code = p.wait(timeout=900)
            fh.close()
            if code:
                self.fail("8", f"{label}: {name}'s node exited {code} (see {s.work}/node-{name}.log)")
        out = {}
        for n in s.seat_keys:
            f = s.work / f"node-{n}.log"
            if f.exists():
                with open(f, encoding="utf-8") as fh:
                    fh.seek(sizes[n])
                    out[n] = fh.read()
        return out

    def settle(self, bounty: int) -> bool:
        for _ in range(80):
            self.s.ctl("devnet", "warp", "--days", "1", show=False)
            if self.s.ctl("bot", "settle", "--bounty", str(bounty), show=False)["settled"]:
                return True
        return False

    def verify_head(self) -> tuple:
        """pofctl verify-head on a seat's node: (True, its line) or (False, the refusal)."""
        try:
            data = self.s.ctl("verify-head", "--rid", self.net.rid, "--rad-exec", self.net.exec_prefix(SEATS[0]),
                              show=False)
            return bool(data.get("match")), data.get("canonical")
        except Exception as e:  # noqa: BLE001 (pofctl's refusal is the point)
            return False, str(e)

    def canonical_everywhere(self, part: str, want: str, what: str) -> None:
        self.net.sync()
        got = {n: self.net.canonical_on(n) for n in NODES}
        bad = {n: c[:12] for n, c in got.items() if c != want}
        if bad:
            self.fail(part, f"{what}: canonical main isn't {want[:12]} on {bad}")
        else:
            print(f"  ok   {what}: canonical main = {want[:12]} on all {len(NODES)} nodes")

    # ---------- the scenarios ----------

    def s8a_happy(self) -> None:
        print("\n== 8a. the happy path merged on Radicle ==", flush=True)
        start, base = self.s.rpc.block(), self.head()
        bounty, issue = self.new_bounty("Radicle happy path")
        self.s.ctl("solver", "quote", "--bounty", str(bounty), as_role="solver-a", show=False)
        sub, fix, drawn = self.submit(bounty, issue, "solver-a")
        logs = self.run_nodes(f"bounty {bounty}'s check and merge on Radicle")
        if not self.check("8a", f"bounty {bounty} after the nodes", self.s.state(bounty), "Merged"):
            return
        pushed = [n for n in drawn if "Radicle: pushed main" in logs.get(n, "")]
        print(f"  the drawn judges who pushed: {', '.join(pushed)}")
        if len(pushed) < THRESHOLD:
            self.fail("8a", f"only {pushed} pushed, fewer than the threshold")
        self.check("8a", "Heads.head(repo)", self.head(), fix)
        moved = self.moved_since(start)
        self.check("8a", "HeadMoved events", len(moved), 1)
        if moved:
            e = moved[0]
            self.check("8a", "HeadMoved (base, commit)", (e["topics"][2], e["topics"][3]),
                       ("0x" + v2.commit_word(base).hex(), "0x" + v2.commit_word(fix).hex()))
            bounty_ev, sub_ev = (int(e["data"][2 + 64 * i:2 + 64 * (i + 1)], 16) for i in range(2))
            self.check("8a", "HeadMoved (bounty, submission)", (bounty_ev, sub_ev), (bounty, sub))
        self.canonical_everywhere("8a", fix, "after the merge")
        snap = self.net.snapshot(SEATS[0])
        voters = {n for n in SEATS if rad.nid(self.net.did(n)) in snap.votes(fix)}
        self.check("8a", "the delegates whose main has the fix are drawn judges", voters <= set(drawn), True)
        self.check("8a", "pofctl verify-head", self.verify_head(), (True, fix))
        if not self.settle(bounty):
            return self.fail("8a", f"bounty {bounty} never settled")
        self.check("8a", f"bounty {bounty} after settling", self.s.state(bounty), "Paid")
        claimed = self.s.ctl("funder", "claim", "--bounty", str(bounty), show=False)
        print(f"  the funder claimed bounty {bounty}'s leftover: {json.dumps(claimed)[:100]}")

    def s8b_outsider(self) -> None:
        print("\n== 8b. an outsider pushes its own main, and opens a patch ==", flush=True)
        start, head = self.s.rpc.block(), self.head()
        unjudged = self.net.commit_on(OUTSIDER, head, "an outsider change, never judged")
        self.net.push_main(OUTSIDER, unjudged)
        self.net.sh(OUTSIDER, "cd repo && git push -q rad HEAD:refs/patches 2>/dev/null || true", check=False)
        self.net.sync()
        self.check("8b", "the outsider's own main, on oracle-0's copy", self.net.main_of(SEATS[0], OUTSIDER), unjudged)
        self.canonical_everywhere("8b", head, "after the outsider's push")
        snap = self.net.snapshot(SEATS[0])
        self.check("8b", "the node's own count (the outsider's main seen, not counted)",
                   (unjudged in snap.tips.values(), rad.canonical(snap)), (True, head))
        self.check("8b", "pofctl verify-head", self.verify_head(), (True, head))
        self.check("8b", "Heads.head(repo)", self.head(), head)
        self.check("8b", "HeadMoved events since", len(self.moved_since(start)), 0)

    def s8c_threshold(self) -> None:
        print("\n== 8c. fewer delegates than the threshold push ==", flush=True)
        start, head = self.s.rpc.block(), self.head()
        bounty, issue = self.new_bounty("Radicle below the threshold")
        sub, fix, drawn = self.submit(bounty, issue, "solver-b")
        self.run_nodes(f"bounty {bounty}'s check", radicle=False)  # the verdict; the forge never merges it
        if not self.check("8c", f"bounty {bounty} after the check", self.s.state(bounty), "Won"):
            return
        voter, offline = drawn[0], drawn[1:]
        self.net.push_main(OUTSIDER, fix)  # a non-delegate's vote for the won fix: counts for nothing
        print(f"  the outsider pushed its main to the fix; {', '.join(offline)}'s nodes are offline at the merge")
        logs = self.run_nodes(f"bounty {bounty}'s merge with {voter} alone", skip=offline)
        self.check("8c", f"{voter}'s node pushed", "Radicle: pushed main" in logs.get(voter, ""), True)
        self.check("8c", f"{voter}'s own main, on oracle-0's copy", self.net.main_of(SEATS[0], voter), fix)
        self.canonical_everywhere("8c", head, "one delegate (and the outsider) pushed")
        self.check("8c", f"bounty {bounty} with one vote", self.s.state(bounty), "Won")
        self.check("8c", "HeadMoved events since", len(self.moved_since(start)), 0)
        epoch = self.chain.bounty(bounty)["epoch"]
        for _ in range(20):  # the round's deadline: mergeDays after the win, then anyone reopens it
            self.s.ctl("devnet", "warp", "--days", "1", show=False)
            try:
                self.bot.send(self.chain.race, "mergeExpired(uint256)", bounty)
                break
            except Reverted:
                continue
        else:
            return self.fail("8c", f"mergeExpired({bounty}) was refused for 20 days")
        print(f"  the merge deadline passed: mergeExpired({bounty}) by the bot")
        self.check("8c", f"bounty {bounty} after mergeExpired", self.s.state(bounty), "Open")
        self.check("8c", "awards (epoch)", self.chain.bounty(bounty)["epoch"], epoch)
        awarded = self.s.rpc.logs(self.chain.race, start, [AWARDED, "0x" + bounty.to_bytes(32, "big").hex()])
        self.check("8c", f"Awarded events for bounty {bounty}", len(awarded), 0)
        self.check("8c", "Heads.head(repo)", self.head(), head)

    def s8d_mismatch(self) -> None:
        print("\n== 8d. Heads and canonical main disagree ==", flush=True)
        start, head = self.s.rpc.block(), self.head()
        bounty, issue = self.new_bounty("Radicle mismatch")
        sub, fix, drawn = self.submit(bounty, issue, "solver-a")
        rogue = [n for n in SEATS if n not in drawn][:2]
        unjudged = self.net.commit_on(rogue[0], head, "a rogue change, never judged")
        for n in rogue:
            self.net.push_main(n, unjudged)
        print(f"  {' and '.join(rogue)} (delegates, not drawn) skipped the check and pushed {unjudged[:12]}")
        self.canonical_everywhere("8d", unjudged, "two delegates pushed an unjudged commit")
        ok, why = self.verify_head()
        self.check("8d", "pofctl verify-head refuses", (ok, "refused" in why), (False, True))
        print(f"  ({why.strip()[:160]})")
        logs = self.run_nodes(f"bounty {bounty}'s check and merge on Radicle")
        self.check("8d", f"bounty {bounty}", self.s.state(bounty), "Won")
        refused = [n for n in drawn if "Radicle: refused" in logs.get(n, "")]
        self.check("8d", "the drawn judges' nodes that refused", sorted(refused), sorted(drawn))
        self.check("8d", "a drawn judge's main pushed to the fix",
                   any(self.net.main_of(SEATS[0], n) == fix for n in drawn), False)
        self.check("8d", "Heads.head(repo)", self.head(), head)
        self.check("8d", "HeadMoved events since", len(self.moved_since(start)), 0)

    def s8e_isolation(self) -> None:
        print("\n== 8e. isolation: internal network, no route out, nodes dialled only each other ==", flush=True)
        n = self.net.isolation(lambda what: self.fail("8e", what))
        print(f"  checked {n} nodes' routes and logs (kept in {self.net.dir})")

    def run(self) -> None:
        print("\n== 8. Radicle merges (#201) ==", flush=True)
        self.setup()
        for part in (self.s8a_happy, self.s8b_outsider, self.s8c_threshold, self.s8d_mismatch, self.s8e_isolation):
            try:
                part()
            except Exception as e:  # noqa: BLE001 (one part's crash shouldn't hide the others)
                self.fail(part.__name__[1:3], f"crashed: {type(e).__name__}: {e}")
        if not self.problems:
            self.s.passed.append("8")


def run(suite) -> None:
    Scenarios(suite).run()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("action", choices=("up", "down"))
    ap.add_argument("--work", default=".integration")
    a = ap.parse_args()
    net = Net(a.work)
    if a.action == "down":
        net.clean()
        return 0
    try:
        st = net.up()
    except Exception:
        net.clean()
        raise
    print(st["rid"], st["genesis"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
