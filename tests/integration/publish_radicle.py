"""The Radicle target of scripts/github_snapshot.py on the internal Docker network (proof-of-fix#251, task 5.1; design
L13). Run it with `scripts/radicle-spike.sh --publish`, which builds the spike's node image (spikes/radicle/Dockerfile:
the pinned Radicle 1.10.3 release, checked by SHA-256) and calls this file. `python3
tests/integration/publish_radicle.py clean` removes anything a stopped run left behind.

Not a new harness: the Radicle spike's (spikes/radicle/v3_spike.py) containers, `Rad` helpers, results and isolation
check, under their own names (`use_names`). The publisher's container is the spike's node image with python3 added
(PY_NODE_IMAGE, built here from it; the one download is Ubuntu's python3 package, at build time), so the script runs
where its node is, as on the owner's machine. The script and seed/publication.py are this checkout's; the source is a
small repository with a private term and two commits, and the terms are a test file.

  D. dry run: the script, without --publish, makes one root commit in a new repository, scrubbed, and no Radicle
     command runs: the node has no repository;
  R. refused scan: a source with a secret's shape creates nothing (no folder, no repository on the node);
  P. publish: --publish with the node named (--rad-home) and --expect-root naming the dry run's commit: `rad init` on
     the publisher's node, the record written and accepted by seed/publication.py, its RID the node's only repository;
  F. a fresh node, connected only to the publisher, clones the RID: HEAD the root commit, one commit, the term gone;
  I. isolation (the spike's check): the internal network, no route out, the nodes dialled only each other, no public
     Radicle host in their logs.

Radicle's `test` network (no bootstrap nodes); throwaway keys made in the containers. No public network, nothing
published. Results and node logs stay in .publish-radicle/ (gitignored)."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
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

PREFIX = "pof251pub"
NODES = ["publisher", "fresh"]
OUT = ROOT / ".publish-radicle"
RECORD_DIR = OUT / "record"
PY_NODE_IMAGE = "pof251-radicle-py:test"
PROGRAM = "/opt/pof"  # the script and seed/publication.py, as in a checkout
HOME_C = VS.HOME_C
PRIVATE = "acme-" + "internal.test"  # the test terms' private term (never a real one)
TERMS = f"# kind: company domain\n{PRIVATE} => example.com\ndeny: forbidden-literal\n"


def build_py_image() -> None:
    """The spike's node image with python3, for the containers that run Python beside their Radicle node."""
    dockerfile = (f"FROM {VS.IMAGE}\nUSER root\nRUN apt-get update -qq && apt-get install -y -qq "
                  "--no-install-recommends python3 >/dev/null && rm -rf /var/lib/apt/lists/*\nUSER foundry\n")
    r = subprocess.run(["docker", "build", "-q", "-t", PY_NODE_IMAGE, "-"], input=dockerfile, text=True,
                       capture_output=True, timeout=900)
    if r.returncode:
        raise RuntimeError(f"building {PY_NODE_IMAGE}: {r.stderr.strip()[-400:]}")


def start_py_node(rad: VS.Rad, n: str) -> None:
    """Like Rad.start, from PY_NODE_IMAGE."""
    VS.docker("run", "-d", "--name", rad.c(n), "--hostname", n, "--network", VS.NET, "--network-alias", n,
              PY_NODE_IMAGE)
    rad.did[n] = rad.sh(n, f"node-init.sh {n} 2>/dev/null")
    rad.started.append(n)


def copy_in(rad: VS.Rad, n: str, src: Path, dest: str) -> None:
    VS.docker("cp", f"{src}/.", f"{rad.c(n)}:{dest}")
    VS.docker("exec", "-u", "root", rad.c(n), "chown", "-R", "foundry:foundry", dest)


def git(cwd: Path, *args) -> str:
    ident = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main"]
    return subprocess.run(["git", *ident, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class PublishTest:
    def __init__(self, keep: bool) -> None:
        self.keep = keep
        self.spike = VS.Spike(keep)
        self.res, self.rad = self.spike.res, self.spike.rad

    def snapshot(self, *extra, source: str = f"{HOME_C}/src") -> tuple:
        cmd = ["python3", f"{PROGRAM}/scripts/github_snapshot.py", "proof-of-fix", "--target", "radicle",
               "--source", source, "--ref", "HEAD", "--terms", f"{HOME_C}/terms", *extra]
        out = self.rad.sh("publisher", " ".join(shlex.quote(c) for c in cmd) + " 2>&1; echo \"@exit $?\"",
                          check=False)
        m = re.search(r"@exit (\d+)\s*$", out)
        return (int(m.group(1)) if m else -1), out[:m.start()] if m else out

    def repos_on(self, n: str) -> list:
        return sorted(set(re.findall(r"rad:z[1-9A-HJ-NP-Za-km-z]+", self.rad.sh(n, "rad ls --all 2>&1",
                                                                                 check=False))))

    def setup(self) -> None:
        rad = self.rad
        start_py_node(rad, "publisher")
        with tempfile.TemporaryDirectory() as tmp:
            prog, src, bad = Path(tmp) / "prog", Path(tmp) / "src", Path(tmp) / "bad"
            for rel in ("scripts/github_snapshot.py", "seed/publication.py"):
                (prog / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, prog / rel)
            for d, leak in ((src, ""), (bad, "AKIA" + "D" * 16)):
                d.mkdir()
                git(d, "init", "-q")
                (d / "README.md").write_text(f"# proof-of-fix\n\nDeveloped at {PRIVATE}.\n")
                (d / "code.py").write_text(f"x = '{leak}'\n" if leak else "x = 1\n")
                git(d, "add", "-A")
                git(d, "commit", "-q", "-m", "first")
                git(d, "commit", "-q", "--allow-empty", "-m", "second, which must not go across")
            (Path(tmp) / "t").mkdir()
            (Path(tmp) / "t" / "terms").write_text(TERMS)
            rad.sh("publisher", f"mkdir -p {HOME_C}/src {HOME_C}/bad")
            VS.docker("exec", "-u", "root", rad.c("publisher"), "mkdir", "-p", PROGRAM)
            copy_in(rad, "publisher", prog, PROGRAM)
            copy_in(rad, "publisher", src, f"{HOME_C}/src")
            copy_in(rad, "publisher", bad, f"{HOME_C}/bad")
            copy_in(rad, "publisher", Path(tmp) / "t", HOME_C)

    def dry_run(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("D", "dry run: one root commit in a new repository, scrubbed; no Radicle command, nothing on "
                          "the node")
        rc, out = self.snapshot("--out", f"{HOME_C}/dry")
        res.expect("the dry run's exit", rc, 0)
        res.check("a dry run: no Radicle command ran, nothing published" in out, "it says it's a dry run")
        res.check("term 1 (company domain): replaced 1 time(s) in 1 file(s)" in out and PRIVATE not in out,
                  "it counts the replaced term by its number and kind, never its value")
        self.root = rad.sh("publisher", f"git -C {HOME_C}/dry rev-parse HEAD")
        res.expect("commits in the new repository", rad.sh("publisher", f"git -C {HOME_C}/dry rev-list --count HEAD"),
                   "1")
        res.check(self.root in out, f"the root commit {self.root[:12]} is printed")
        res.expect("the private term in the snapshot",
                   rad.sh("publisher", f"git -C {HOME_C}/dry grep -c {shlex.quote(PRIVATE)} HEAD || true",
                          check=False), "")
        res.expect("repositories on the publisher's node after the dry run", self.repos_on("publisher"), [])
        res.expect("Radicle remotes in the new repository", rad.sh("publisher", f"git -C {HOME_C}/dry remote"), "")

    def refused(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("R", "a refused scan creates nothing")
        home = rad.sh("publisher", "echo $RAD_HOME")
        rc, out = self.snapshot("--out", f"{HOME_C}/refused", "--publish", "--rad-home", home, "--record",
                                f"{HOME_C}/refused.json", source=f"{HOME_C}/bad")
        res.expect("the refused run's exit", rc, 1)
        res.check("FOUND aws access key: code.py" in out and "AKIA" not in out,
                  "the finding names the file and the kind, not the value")
        res.expect("the folder and record it would have written",
                   rad.sh("publisher", f"ls -d {HOME_C}/refused {HOME_C}/refused.json 2>/dev/null || true",
                          check=False), "")
        res.expect("repositories on the publisher's node", self.repos_on("publisher"), [])

    def publish(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("P", "publish: rad init on the named node, the record written and accepted")
        home = rad.sh("publisher", "echo $RAD_HOME")
        rc, out = self.snapshot("--out", f"{HOME_C}/public", "--expect-root", self.root, "--publish", "--rad-home",
                                home, "--record", f"{HOME_C}/record/publication.json")
        res.expect("the publish's exit", rc, 0)
        if rc:
            res.info(out[-600:])
            raise RuntimeError("the publish failed")
        raw = rad.sh("publisher", f"cat {HOME_C}/record/publication.json")
        RECORD_DIR.mkdir(parents=True, exist_ok=True)
        path = RECORD_DIR / "publication.json"
        path.write_text(raw + "\n", encoding="utf-8")
        record = json.loads(raw)
        rid = publication.rid(path)  # seed/publication.py's rules, as the seed reads it
        self.rad.rid["pof"] = rid
        res.expect("the record's root commit (the dry run's)", record["rootCommit"], self.root)
        res.expect("the record's node id (the publisher's)", record["nodeId"], R.nid(rad.did["publisher"]))
        res.expect("the record's Radicle release", record["radicle"], publication.RADICLE)
        res.expect("the publisher's repositories", self.repos_on("publisher"), [rid])
        res.expect("its canonical main on the publisher's node", rad.canonical("publisher", "pof"), self.root)
        res.check(rid in out, f"the script printed the RID {rid}")

    def fresh(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("F", "a fresh node clones the RID from the publisher")
        rad.start("fresh")
        rad.connect("fresh", "publisher")
        rid, pub_nid = rad.rid["pof"], R.nid(rad.did["publisher"])
        head = rad.sh("fresh", f"for _ in 1 2 3 4 5; do rad clone {rid} pof --seed {pub_nid} --no-confirm "
                               f">/dev/null 2>&1 && break; rm -rf pof; sleep 2; done; "
                               f"git -C pof rev-parse HEAD 2>/dev/null || echo none", check=False)
        res.expect("the fresh clone's HEAD", head, self.root)
        res.expect("its commits", rad.sh("fresh", "git -C pof rev-list --count HEAD", check=False), "1")
        res.check(PRIVATE not in rad.sh("fresh", "cat pof/README.md", check=False)
                  and "A scrubbed snapshot" in rad.sh("fresh", "cat pof/README.md", check=False),
                  "its README has the snapshot's note and not the private term")

    def run(self) -> int:
        res, rad = self.res, self.rad
        VS.clean()
        shutil.rmtree(OUT, ignore_errors=True)
        OUT.mkdir(parents=True)
        started = time.time()
        try:
            build_py_image()
            VS.docker("network", "create", "--internal", VS.NET)
            self.setup()
            for step in (self.dry_run, self.refused, self.publish, self.fresh):
                step()
        except Exception as e:  # noqa: BLE001 (recorded as the current scenario's failure, then cleaned up)
            if not res.cur:
                res.scenario("D", "setup")
            res.bad(f"aborted: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            try:
                if rad.started:
                    self.spike.isolation(others=())
            except Exception as e:  # noqa: BLE001
                res.scenario("I", "isolation")
                res.bad(f"aborted: {type(e).__name__}: {e}")
            self.spike.radicle_version = rad.sh("publisher", "rad --version", check=False) if rad.started else ""
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
    return PublishTest(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
