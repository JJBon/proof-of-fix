"""The calibration set's local proof (proof-of-fix#334): candidates qualify on calibration checks alone, then a good
calibration fix passes and merges and a bad one fails, all driven by scripts/calibrate.py on the Radicle devnet of
tests/integration/suite_v3_radicle.py (real Radicle 1.10.3 nodes and anvil on an --internal Docker network, real
`NodeV3` validators with the fake judge, each fix's tests in the real Docker sandbox with tests/ protected).

    POF_RADICLE_PREFIX=pofcal python3 tests/integration/calibration_radicle.py run   (scripts/integration.sh
        --version 3 --radicle --calibration builds the images and calls it)
    python3 tests/integration/calibration_radicle.py clean

The repository is the calibration set itself: calibration/ with its 60 buggy modules and visible tests,
tests/test_calibration.py, and proof-of-fix's own `.pof/check.json` (`python -m unittest discover -s tests -t
tests`, tests/ protected), so the sandbox runs what Sepolia's validators run on proof-of-fix. Main's suite passes on it
with every bug present (each item's tests skip until its fix sets FIXED).

S. setup: the launch's rules on anvil, the genesis validator and six candidates (v1-v6) on their own Radicle nodes;
Q. qualification: `calibrate.py`'s Driver registers calibration issues (each a Radicle issue opened by pofctl on the
   reporter's node, with the signed claim) a batch at a time whenever the network is idle, and nothing else is
   registered: each candidate goes from Candidate to Active on the shadow verdicts of calibration checks;
F. fixes: the same driver opens the bounties of a good item and a bad item, records the attempts, commits each
   prepared fix on Heads.head in the solver's working copy, seals it with `pofctl --v3 submit` and opens the Radicle
   patch; a panel of 3 passes the good fix and fails the bad one (its protected test fails in the sandbox); the good
   fix is claimed and merged at finality, and the canonical main follows;
I. isolation, as in the Radicle suite.

No model call, no public chain, no AWS. Results and node logs stay in .integration-calibration/ (gitignored)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "scripts", ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import calibrate as CAL  # noqa: E402
import suite_v3 as SV  # noqa: E402
import suite_v3_radicle as SR  # noqa: E402
import v3_spike as VS  # noqa: E402
from e2e_node_v3 import ETH_100, secret  # noqa: E402
from oracle import crypto, fetch, redact, sandbox, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402

PREFIX = os.environ.get("POF_RADICLE_PREFIX", "pofcal")
OUT = ROOT / ".integration-calibration"
RECORD_DIR = ROOT / "contracts" / "deployments" / "integration-calibration"
CANDIDATES = SR.VALIDATORS[1:]


def genesis_files() -> dict:
    """The race's repository: the calibration set, its protected tests and proof-of-fix's check.json."""
    files = {"README.md": "# calibration\n\nThe calibration set's devnet repository (proof-of-fix#334).\n",
             ".pof/check.json": (ROOT / ".pof" / "check.json").read_text(encoding="utf-8"),
             "tests/test_calibration.py": (ROOT / "tests" / "test_calibration.py").read_text(encoding="utf-8")}
    for p in sorted((ROOT / "calibration").glob("*.py")):
        files[f"calibration/{p.name}"] = p.read_text(encoding="utf-8")
    return files


class Calibration(SR.Story):
    def scenarios(self) -> None:
        self.setup()
        self.qualify()
        self.fixes()
        self.summary()

    def repos(self) -> str:
        self.rad.sh("owner", "mkdir -p g/calibration")  # the suite's repos() makes tests/ and .pof/ only
        return super().repos()

    def setup(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("S", "setup: the launch's rules on anvil, the genesis validator and six candidates on their own "
                          "Radicle nodes; the repository is the calibration set (isolation starts here)")
        if subprocess_missing(sandbox.TEST_IMAGE):
            raise SR.Failed(f"the pinned test image isn't here ({sandbox.TEST_IMAGE}); build it: scripts/test-image.sh")
        t0 = time.time()
        self.up()
        genesis_commit = self.repos()
        minter = crypto.address(secret("minter"))
        record = self.deploy_v3(rad.rid["a"], genesis_commit, env={**SR.LAUNCH, "LOCAL_GENESIS_MINT_TO": minter})
        self.rpc.call("anvil_setBlockTimestampInterval", [0])
        record["rid"] = rad.rid["a"]
        self.record_path = OUT / "record.json"
        self.record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.server = SR.bridge(self.rpc)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        n = self.n = SR.RadNet(self.rpc, record, OUT / "work", self)
        c = n.chain
        g = n.make_node("genesis", SR.GENESIS_FAMILY, keeper=True)
        self.rpc.call("anvil_setBalance", [g.address, ETH_100])
        n.nodes["genesis"] = g
        self.owner_seat = RV.SeatAdapter(R.Radicle(rad.rid["a"], ["docker", "exec", "-i", rad.c("owner")], SR.REPO),
                                         c, "0x" + "00" * 20, D.ChainSeatNodes.of(c), log=n.log("owner"), every=15)
        n.watches.append(self.owner_pass)
        for i in range(1, 7):
            n.join(i)
        n.start = max(self.rpc.block() - 20, 0)
        for role in CAL.Ops.LOCAL_ROLES.values():
            n.fund(self.addr(role), 5_000)
        self.must(len(n.active()) == 1 and all(c.validator(n.nodes[x].address)["state"] == 1 for x in CANDIDATES),
                  f"one validator active from the deployment (genesis); v1-v6 registered as candidates; the "
                  f"repository's genesis {genesis_commit[:12]} holds the {len(CAL.load_items())} calibration items, "
                  f"with proof-of-fix's .pof/check.json (tests/ protected)")
        red = redact.Redactor()
        red.add(self.url)
        self.ledger = CAL.Ledger(OUT / "ledger.jsonl")
        self.ops = CAL.Ops("local", self.record_path, self.url, SR.REPO,
                           {"reporter": f"docker exec -i {rad.c('reporter')}",
                            "solver": f"docker exec -i {rad.c('solver')}"}, {}, rad.rid["a"], red)
        self.reader = CAL.ChainReader(self.url, record)
        self.lines: list = []
        self.seen: set = set()
        self.wall["setup"] = round(time.time() - t0)

    def driver(self, items: list, **kw) -> CAL.Driver:
        return CAL.Driver(items, self.ledger, self.ops, self.reader, max_usd=1_000.0, say=self.lines.append,
                          sleep=lambda s: None, **kw)

    def live(self) -> None:
        """The checks and fixes the driver started, in the nodes' keeper list (suite_v3's LiveChain)."""
        for s in self.ledger.items().values():
            for key in ("check", "submission"):
                if s.get(key) and s[key] not in self.seen:
                    self.n.chain.live[s[key]] = True
                    self.seen.add(s[key])

    def qualify(self) -> None:
        res, n = self.res, self.n
        c = n.chain
        res.scenario("Q", "qualification on calibration checks alone: scripts/calibrate.py registers calibration "
                          "issues through pofctl and Radicle until v1-v6 are active")
        items = CAL.load_items()
        d = self.driver(items, batch=12, fixes=False)
        t = time.time()

        def feed() -> bool:
            st = self.ledger.items()
            if len(st) == len(items) and all(s.get("registered") for s in st.values()):
                return False
            d.step()
            errors = [e for e in self.ledger.events() if e["step"] == "error"]
            if errors and not any(s.get("registered") for s in self.ledger.items().values()):
                raise SR.Failed(f"the driver registers nothing: {errors[0]['message']}")
            self.live()
            self.rad.sync("a", ["reporter"], "announce")
            return True

        n.drive(lambda: all(c.is_active(n.nodes[x].address) for x in CANDIDATES), "v1-v6 qualify on calibration "
                "checks", feed=feed, poke=True)
        d.step()  # the checks' outcomes into the ledger
        st = self.ledger.items()
        made = sum(1 for s in st.values() if s.get("registered"))
        acts = n.evs(c.registry, "Activated(address)")
        checks = {s["check"] for s in st.values() if s.get("registered")}
        scored = n.evs(c.panels, "ShadowScored(uint256,address,bool)")
        on_cal = [x for x in scored if c.panel(int(x["topics"][1], 16))["id"] in checks]
        self.qual = {"registrations": made, "activated": len(acts), "shadowScored": len(scored),
                     "shadowScoredOnCalibration": len(on_cal), "wallSeconds": round(time.time() - t),
                     "chainSeconds": n.when(acts[-1]) - n.t0}
        self.must(len(n.active()) == 7 and len(acts) == 6 and len(on_cal) == len(scored) and made <= len(items),
                  f"v1-v6 went from Candidate to Active on the shadow verdicts of {made} calibration registration "
                  f"checks (every check registered in this run is a calibration item's): {len(scored)} shadow "
                  f"verdicts scored, all on calibration checks; {SV.hours(self.qual['chainSeconds'])} of chain time, "
                  f"{self.qual['wallSeconds']} s of wall time")
        self.must(all(st[i]["radIssue"] for i in st),
                  f"each registration opened its Radicle issue on the reporter's node through pofctl (first "
                  f"{st['c01']['radIssue'][:12]}) and the ledger recorded its registration, check and outcome")
        secs = self.settle("the seats")
        res.info(f"the identity followed the seats ({secs} s)")

    def fixes(self) -> None:
        res, n, rad = self.res, self.n, self.rad
        c = n.chain
        res.scenario("F", "a good calibration fix passes and merges, a bad one fails: opened, attempted, committed, "
                          "sealed and opened as Radicle patches by scripts/calibrate.py")
        st = self.ledger.items()
        items = CAL.load_items()
        good = next(i for i in items if i.prepared == "good" and i.id in st)
        bad = next(i for i in items if i.prepared == "bad" and i.id in st)
        pair = [good, bad]
        n.drive(lambda: all(c.verdict(st[i.id]["check"])["status"] == v3.FINAL for i in pair),
                f"{good.id} and {bad.id}: their registration checks final", poke=True)
        d = self.driver(pair, merge=1)
        d.step()  # the checks final: bounties opened, attempts, fixes sealed and patches opened
        self.live()
        st = self.ledger.items()
        self.must(all(st[i.id].get("submitted") and st[i.id].get("patch") for i in pair),
                  f"{good.id} and {bad.id}: bounties {st[good.id]['bounty']} and {st[bad.id]['bounty']} opened, "
                  f"attempts recorded, each prepared fix committed on Heads.head in the solver's working copy, sealed "
                  f"(submissions {st[good.id]['submission']} and {st[bad.id]['submission']}) and opened as Radicle "
                  f"patches {st[good.id]['patch'][:7]} and {st[bad.id]['patch'][:7]}")
        rad.sync("a", ["solver"], "announce")
        rad.sync("a", SR.VALIDATORS)
        subs = [st[i.id]["submission"] for i in pair]
        n.drive(lambda: all(c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s)["paid"] for s in subs),
                "the two fixes judged", poke=True)
        d.step()  # the verdicts, and the good fix claimed
        st = self.ledger.items()
        docs = {i.id: self.receipts(st[i.id]["submission"]) for i in pair}
        tests = {k: [x["receipt"]["tests"] for _, x in v if x] for k, v in docs.items()}
        self.must(st[good.id]["verdictPass"] and not st[bad.id]["verdictPass"] and st[good.id]["verdictK"] == 3
                  and st[bad.id]["verdictK"] == 3 and all(t["exit_code"] == 0 for t in tests[good.id])
                  and all(t["exit_code"] != 0 and t["protected"] == ["tests"] for t in tests[bad.id])
                  and st[good.id]["asPrepared"] and st[bad.id]["asPrepared"],
                  f"panels of 3 judged them in the sandbox with tests/ protected: {good.id}'s good fix passed "
                  f"(exit 0 for its {len(tests[good.id])} judges), {bad.id}'s bad fix failed (its protected test "
                  f"fails: exit codes {[t['exit_code'] for t in tests[bad.id]]})")
        self.must(st[good.id].get("claimed") and not st[bad.id].get("claimed"),
                  f"the driver claimed the good fix with pofctl (bounty {st[good.id]['bounty']}), not the bad one")
        s = st[good.id]["submission"]
        n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"{good.id}: final", poke=True)
        d.step()
        st = self.ledger.items()
        self.must(st[good.id].get("merged") and self.head() == st[good.id]["fix"],
                  f"at finality the driver merged it with `pofctl --v3 merge`: Heads.head is the fix "
                  f"{st[good.id]['fix'][:12]}")
        secs = self.follow(st[good.id]["fix"], f"{good.id}'s fix")
        res.info(f"the canonical main on the delegates' nodes followed in {secs} s")

    def summary(self) -> None:
        res = self.res
        res.scenario("T", "the driver's ledger and the run's numbers")
        st = self.ledger.items()
        res.info(f"qualification: {self.qual}")
        res.info(f"ledger: {len(self.ledger.events())} events, {sum(1 for s in st.values() if s.get('registered'))} "
                 f"items registered; driver lines: {len(self.lines)}")
        res.meas["qualification"] = self.qual
        res.meas["wallSeconds"] = self.wall
        res.ok(f"{round(time.time() - self.started)} s of wall time")


def subprocess_missing(image: str) -> bool:
    import subprocess

    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    SR.OUT, SR.RECORD_DIR, SR.GENESIS_FILES = OUT, RECORD_DIR, genesis_files()
    VS.use_names(PREFIX, SR.NODES, OUT, RECORD_DIR)
    if a.command == "clean":
        VS.clean()
        fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return Calibration(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
