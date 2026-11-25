"""The Radicle repository moves from v3 to v3.1 (proof-of-fix#310, design RB12; task 6.3): the hand-over rehearsed on a
local chain and real Radicle nodes, as the Sepolia hand-over will run. Run it with `scripts/integration.sh --version 3
--radicle --handover`, or `python3 tests/integration/handover_v3_radicle.py run` once the Radicle image is built and
POF_SOLC is set (integration.sh does both). It is suite_v3_radicle.py's harness (the spike's Radicle nodes on an
--internal Docker network, anvil reached through a pipe, real `NodeV3` validators with the fake judge, pofctl as its
own process), with its own names, so it runs beside that suite.

The story, each step needing the one before:
H1. v3 as Sepolia has it today: one validator, the genesis one, whose node is the repository's one delegate
    (threshold 1); canonical `main` is v3's genesis head.
H2. v3.1 deployed beside it with the same RID, the same genesis validator and the same genesis Radicle node; its
    genesis head is canonical `main` (`pofctl --v3 verify-head` against v3.1's record exits 0); no v3 bounty is won
    or claimed and unmerged (RB12's precondition).
H3. The switch: v3's record is marked `supersededBy`; the genesis validator's node starts v3's part with that record
    (the seat's part refuses to start and says why; the keeper runs) and v3.1's with the seat's part. No identity
    revision is needed: `verify-delegates` against v3.1's seats passes at once.
H4. v3.1 grows: six validators join v3.1 and qualify; the identity follows v3.1's seats (seven delegates,
    threshold 4); `verify-delegates` against v3.1 passes.
H5. A v3.1 fix merges (a Radicle patch through pofctl, judged by v3.1's panel): canonical `main` follows v3.1's Heads on
    every delegate's node.
H6. A later v3 head move is never pushed: the same six validators qualify in v3 too (their v3 nodes superseded: no
    seat's part), a v3 fix on v3's head is merged on v3's Heads, and canonical `main` stays v3.1's head on every node,
    the v3 commit outside it; `verify-head` against v3's record fails, against v3.1's passes, and so does
    `verify-delegates` against v3.1's seats.
I.  isolation (the spike's check).

No model call, no public chain, no AWS. Results and node logs stay in .integration-handover-v3/ (gitignored)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import suite_v3 as SV  # noqa: E402
import suite_v3_radicle as RS  # noqa: E402
import v3_spike as VS  # noqa: E402
from e2e_node_v3 import ETH_100, secret  # noqa: E402
from oracle import crypto, fetch, sandbox, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.rpc import Reverted  # noqa: E402

PREFIX = os.environ.get("POF_RADICLE_PREFIX", "pof310h")  # containers and network: pof310h-*, unless set
OUT = ROOT / ".integration-handover-v3"
RECORD_DIR = ROOT / "contracts" / "deployments" / "integration-handover-v3"
VALIDATORS = RS.VALIDATORS
NODES = RS.NODES


class HNet(RS.RadNet):
    """suite_v3_radicle's network for one deployment; `record_file`: the deployment record every node of it is started
    with (ORACLE_DEPLOYMENT_RECORD), as an operator starts `python3 -m oracle run`."""

    record_file: Path | None = None

    def env(self, name: str) -> dict:
        e = super().env(name)
        if self.record_file is not None:
            e["ORACLE_DEPLOYMENT_RECORD"] = str(self.record_file)
        return e


class Idle:
    """A seat adapter that does nothing: the owner's node once it handed the repository over."""

    def tick(self, force: bool = False) -> bool:
        return False


class Handover(RS.Story):
    def scenarios(self) -> None:
        self.h1_v3()
        self.h2_v31()
        self.h3_switch()
        self.h4_grow()
        self.h5_v31_fix()
        self.h6_v3_unpushed()

    # ---------- helpers ----------

    def use(self, which: str) -> None:
        """pofctl and the story's helpers on deployment `which` ("v3" or "v3.1")."""
        self.n = self.nets[which]
        self.record_path = self.records[which]

    def delegates_ok(self, what: str) -> None:
        self.rad.sync("a", VALIDATORS)
        record = self.record_path
        self.record_path = self.records["v3.1"]
        code, out = self.ctl_exit("verify-delegates", "--rad-exec", f"docker exec -i {self.rad.c('genesis')}")
        self.record_path = record
        self.must(code == 0, f"{what}: pofctl --v3 verify-delegates against v3.1's seats exits {code} "
                             f"({out.splitlines()[0][:160] if out else ''})")

    def one_issue(self, f: str) -> dict:
        """A Radicle issue registered on the current deployment with pofctl, its check final, its bounty open."""
        rad, n = self.rad, self.n
        c = n.chain
        title, body = RS.ISSUES[f]
        iid = self.rad_issue("reporter", "a", title, body)
        d = self.ctl("issue", "register", "--rad-issue", iid, "--comment", "--rad-exec",
                     f"docker exec -i {rad.c('reporter')}", as_="reporter")
        c.live[d["check"]] = True
        rad.sync("a", ["reporter"], "announce")
        n.drive(lambda: c.verdict(d["check"])["status"] == v3.FINAL, f"{f}: its registration check final", poke=True)
        b = self.ctl("issue", "open", "--issue", d["issue"], as_="reporter")["bounty"]
        return {"rad": iid, "issue": d["issue"], "check": d["check"], "bounty": b}

    def net(self, record: dict, which: str, record_file: Path | None) -> HNet:
        n = HNet(self.rpc, record, OUT / f"work-{which}", self)
        n.record_file = record_file
        g = n.make_node("genesis", RS.GENESIS_FAMILY, keeper=True)
        self.rpc.call("anvil_setBalance", [g.address, ETH_100])
        n.nodes["genesis"] = g
        for role in ("reporter", "funder", "solver-a", "solver-b", "solver-c"):
            n.fund(self.addr(role), 2_000)
        return n

    # ---------- the story ----------

    def h1_v3(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("H1", "v3 as on Sepolia: the genesis validator alone, its node the repository's one delegate")
        if subprocess.run(["docker", "image", "inspect", sandbox.TEST_IMAGE], capture_output=True).returncode:
            raise RS.Failed(f"the pinned test image isn't here ({sandbox.TEST_IMAGE}); build it: scripts/test-image.sh")
        self.up()
        self.genesis_commit = self.repos()
        self.minter = crypto.address(secret("minter"))
        record = self.deploy_v3(rad.rid["a"], self.genesis_commit,
                                env={**RS.LAUNCH, "LOCAL_GENESIS_MINT_TO": self.minter})
        self.rpc.call("anvil_setBlockTimestampInterval", [0])
        record["rid"] = rad.rid["a"]
        self.records = {"v3": OUT / "v3.json", "v3.1": OUT / "v3.1.json"}
        self.records["v3"].write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.server = RS.bridge(self.rpc)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.nets = {"v3": self.net(record, "v3", None)}
        self.use("v3")
        n = self.n
        self.owner_seat = RV.SeatAdapter(R.Radicle(rad.rid["a"], ["docker", "exec", "-i", rad.c("owner")], RS.REPO),
                                         n.chain, "0x" + "00" * 20, D.ChainSeatNodes.of(n.chain), log=n.log("owner"),
                                         every=15)
        n.start = max(self.rpc.block() - 20, 0)
        secs = self.settle("v3's one seat")
        names, threshold = self.delegates()
        self.must(names == ["genesis"] and threshold == 1 and len(n.chain.seats()) == 1,
                  f"v3 has one seat, the genesis validator's; the identity followed it: delegates {names}, threshold "
                  f"{threshold} ({secs} s)")
        rad.sync("a")
        self.must(all(rad.canonical(x, "a") == self.genesis_commit for x in NODES),
                  f"canonical main = v3's genesis head {self.genesis_commit[:12]} on all {len(NODES)} nodes")

    def h2_v31(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("H2", "v3.1 deployed with the same RID, genesis validator and genesis node; its genesis head is "
                           "canonical main")
        c3 = self.nets["v3"].chain
        open_awards = []
        for b in range(1, 1000):
            try:
                bt = c3.bounty(b)
            except Reverted:  # past the last bounty
                break
            if bt["state"] == SV.WON or (bt["state"] == SV.CLAIMED and not c3.award(b, bt["epoch"])["merged"]):
                open_awards.append(b)
        self.must(not open_awards, "RB12's precondition: no v3 bounty is won, or claimed and unmerged")
        main = rad.canonical("genesis", "a")
        record = self.deploy_v3(rad.rid["a"], main, env={**RS.LAUNCH, "LOCAL_GENESIS_MINT_TO": self.minter})
        record["rid"] = rad.rid["a"]
        self.records["v3.1"].write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.record_path = self.records["v3.1"]
        code, out = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('reporter')}")
        self.record_path = self.records["v3"]
        self.must(code == 0 and record["race"].lower() != c3.race.lower(),
                  f"v3.1's RaceV3 {record['race'][:10]}… is a new deployment; its genesis head is canonical main "
                  f"{main[:12]} (pofctl --v3 verify-head against v3.1's record exits {code})")
        self.v31_record = record

    def h3_switch(self) -> None:
        res = self.res
        res.scenario("H3", "the switch: v3 marked superseded; the genesis node runs v3.1's seat part and only v3's "
                           "keeper; no identity revision needed")
        doc = json.loads(self.records["v3"].read_text(encoding="utf-8"))
        doc["supersededBy"] = self.records["v3.1"].name
        self.records["v3"].write_text(json.dumps(doc, indent=2), encoding="utf-8")
        n3 = self.nets["v3"]
        n3.record_file = self.records["v3"]
        n3.nodes["genesis"] = n3.make_node("genesis", RS.GENESIS_FAMILY, keeper=True, tag=" (v3)")
        n3.node_log.flush()
        said = Path(n3.node_log.name).read_text(encoding="utf-8")
        self.must(n3.nodes["genesis"].radicle_seat is None and "superseded by v3.1.json" in said
                  and n3.nodes["genesis"].keeper and isinstance(n3.nodes["genesis"].fixes, RV.RadicleFixes),
                  "the genesis node started v3's part with its record: the seat's part refused to start (\"superseded "
                  "by v3.1.json\"), the keeper and the fix source run")
        n31 = self.nets["v3.1"] = self.net(self.v31_record, "v3.1", self.records["v3.1"])
        self.owner_seat = Idle()
        self.use("v3.1")
        n31.start = max(self.rpc.block() - 20, 0)
        self.must(isinstance(n31.nodes["genesis"].radicle_seat, RV.SeatAdapter)
                  and n31.chain.rad_node_of(n31.nodes["genesis"].address)
                  == n3.chain.rad_node_of(n3.nodes["genesis"].address),
                  "v3.1's part runs the seat's part; its genesis seat maps to the same Radicle node as v3's")
        self.delegates_ok("at once, with no identity revision")

    def h4_grow(self) -> None:
        res, n = self.res, self.n
        c = n.chain
        res.scenario("H4", "v3.1 grows: six validators join and qualify; the identity follows v3.1's seats")
        for i in range(1, 7):
            n.join(i)
        made = n.grow(VALIDATORS[1:], 12, "v1 to v6 qualify on v3.1", rounds=60)
        self.must(len(n.active()) == 7 and len(c.seats()) == 7,
                  f"v1 to v6 qualified on v3.1 after {made} registration checks: 7 seats")
        secs = self.settle("v3.1's seats")
        names, threshold = self.delegates()
        self.must(names == sorted(VALIDATORS) and threshold == 4,
                  f"the identity followed v3.1's seats: delegates {', '.join(names)}, threshold {threshold} ({secs} s)")
        self.delegates_ok("after v3.1 grew")

    def h5_v31_fix(self) -> None:
        res = self.res
        res.scenario("H5", "a v3.1 fix merges: canonical main follows v3.1's Heads")
        x = self.one_issue("median")
        out = self.fix("solver-a", x, ["median"], "fix median (v3.1)")
        self.v31_head = out["fix"]
        self.must(R.sha_of(self.nets["v3.1"].chain.head()) == out["fix"],
                  f"v3.1's Heads.head is {out['fix'][:12]}, and canonical main followed it on every delegate's node")
        self.delegates_ok("after the v3.1 merge")

    def h6_v3_unpushed(self) -> None:
        res, rad = self.res, self.rad
        res.scenario("H6", "a later v3 head move is never pushed")
        self.use("v3")
        n3 = self.n
        c3 = n3.chain
        for i in range(1, 7):
            n3.join(i)
        made = n3.grow(VALIDATORS[1:], 12, "v1 to v6 qualify on v3", rounds=60)
        self.must(len(n3.active()) == 7 and all(n3.nodes[x].radicle_seat is None for x in VALIDATORS),
                  f"the same six validators qualified on v3 too ({made} checks), every v3 node with its record: no "
                  f"seat's part")
        base = R.sha_of(c3.head())
        x = self.one_issue("mode")
        out = self.fix("solver-b", x, ["mode"], "fix mode (v3, superseded)", merge=False)
        n3.drive(lambda: c3.verdict(out["submission"])["status"] == v3.FINAL, "the v3 fix final", poke=True)
        m = self.ctl("merge", "--bounty", x["bounty"], as_="solver-b")
        self.must(m["merged"] and R.sha_of(c3.head()) == out["fix"] and out["base"] == base,
                  f"v3's Heads moved {base[:12]} -> {out['fix'][:12]} (merged on v3)")
        self.use("v3.1")
        for _ in range(4):  # the seat adapters' passes: v3.1's push v3.1's head; nothing runs v3's
            self.tick_seats()
            rad.sync("a")
            time.sleep(2)
        at = {x_: rad.canonical(x_, "a") for x_ in NODES}
        names, _ = self.delegates()
        inside = [y for y in names if rad.sh(y, f"git --git-dir {rad.store('a')} merge-base --is-ancestor "
                                                f"{out['fix']} refs/heads/main && echo in", check=False)]
        self.must(all(v == self.v31_head for v in at.values()) and not inside,
                  f"canonical main is still v3.1's head {self.v31_head[:12]} on all {len(NODES)} nodes; the v3 commit "
                  f"{out['fix'][:12]} is in no delegate's main")
        self.record_path = self.records["v3"]
        code3, _ = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('reporter')}")
        self.record_path = self.records["v3.1"]
        code31, _ = self.ctl_exit("verify-head", "--rad-exec", f"docker exec -i {rad.c('reporter')}")
        self.must(code3 != 0 and code31 == 0,
                  f"pofctl --v3 verify-head: against v3's record exits {code3} (its head isn't canonical main), "
                  f"against v3.1's exits {code31}")
        self.delegates_ok("after the v3 head move")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    RS.OUT, RS.RECORD_DIR = OUT, RECORD_DIR  # this run's own folders: suite_v3_radicle's stay untouched
    VS.use_names(PREFIX, NODES, OUT, RECORD_DIR)
    if a.command == "clean":
        VS.clean()
        fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return Handover(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
