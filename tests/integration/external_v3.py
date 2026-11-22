"""One validator run outside the harness, on a production-windows chain with Radicle (proof-of-fix#251 task 7.0; design
L18 items 3 and 6, L4, L12, L21). Run it with `scripts/integration.sh --version 3 --external`, or as the release
candidate's external set: `scripts/integration.sh --release-candidate <commit> --external` (scripts/release_candidate.py),
which scripts/rc-aws.sh runs on the test-chain host beside the SEV-SNP host, and in its dress rehearsal on this machine.

Not a new harness: task 4.9's (tests/integration/kit_radicle.py `KitStory`, itself task 4.6's), under its own names:
anvil, the seed as seed/ configures it, every other Radicle node as the measured disk configures a validator's, the
v3 suite's network (real `NodeV3` validators with the fake judge, the clock moved to the next deadline). What differs:
- **the windows are production's** (L4: seal 2 h, reveal 1 h, as Sepolia), on a chain whose clock only the run moves;
  the launch's other rules as in task 4.6 (panel caps off, kTop 3, same-size challenges, the taxi fare, POFTEST);
- **six validators in the harness** (genesis and v1-v5) and **one outside it** (POF_V3_EXTERNAL): a validator this
  file doesn't start, sign for or configure. It registers itself, with its own key, attestation, image and Radicle
  node; it reads the registrations' Radicle issues and the fix's patch through its own Radicle node, which dials only
  the seed; it seals and reveals in wall time while the moved clock waits at each deadline its open seat still has to
  meet (tests/integration/suite_v3.py `external_hold`, POF_V3_EXTERNAL_WAIT);
- **the chain and the seed are reachable from outside the run's internal network** only where the mode says:
  POF_EXT_MODE=aws (the test-chain host, validator-kit/sevsnp/testchain): anvil and the seed also join a second Docker
  network whose ports are published on POF_EXT_BIND (the host's private address; its security group admits only the
  SEV-SNP host's), so the SEV-SNP host reaches the RPC on 8545 and the seed on 8776; POF_EXT_MODE=local (the dress
  rehearsal): that second network is internal too, the outside validator's Radicle node joins it, and its node process
  reaches the chain through the JSON-RPC bridge on this machine's loopback, as pofctl does.

The run, each step needing the one before:
S. setup: v3 on production windows with the outside validator's checker image accepted (POF_EXT_IMAGE, the measured
   disk's `image_digest`: NodeV3Local's LOCAL_EXTRA_IMAGE), the seed, the six harness validators qualified, the outside
   key funded (gas and coins for its bond); then `ready.json` in POF_EXT_DIR: the chain URL, the race, the RID, the
   seed's address and the settings the outside validator needs (scripts/rc_aws.py turns it into the SEV-SNP host's
   user data, or the rehearsal's stand-in host);
X. the outside validator registers itself (within POF_EXT_REGISTER_WAIT seconds): its proof type, TEE type, image,
   family and Radicle node as expected (POF_EXT_PROOF, POF_EXT_TEE, POF_EXT_IMAGE, POF_EXT_RAD_NODE);
Q. it qualifies by its shadow verdicts on registration checks claimed by Radicle issues;
F. a fix: a Radicle issue registered with pofctl and its check final, its bounty opened, then a patch submitted with
   pofctl. For the draw, four of the six harness validators pause (capacity 0, as an operator may), so the counted
   panel of 3 is the genesis validator, v1 and the outside validator; they resume once it is drawn. The outside
   validator seals and reveals its verdict on its counted seat, and the verdict is counted.
R. the result, `pof-external-run/1`, to POF_EXT_DIR/external.json (or --result): what release_candidate.py's external
   items read.
I. isolation: the run's internal network has no route out, and every harness validator's Radicle node dialled only the
   seed, outbound.

No model call, no public chain. Results and node logs: .external-v3/ (gitignored)."""

from __future__ import annotations

import argparse
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

import kit_radicle as K  # noqa: E402
import suite_v3 as SV  # noqa: E402
import suite_v3_radicle as SR  # noqa: E402
import v3_spike as VS  # noqa: E402
from e2e_node_v3 import ETH_100, secret  # noqa: E402
from oracle import crypto, sandbox, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.keys import DstackKeys  # noqa: E402

FORMAT = "pof-external-run/1"
READY_FORMAT = "pof-external-ready/1"
PREFIX = "pof251x"
OUT = ROOT / ".external-v3"
RECORD_DIR = ROOT / "contracts" / "deployments" / "external-v3"
HARNESS = ["genesis"] + [f"v{i}" for i in range(1, 6)]  # the other six (the owner's decision, 2026-11-21)
NODES = ["owner", *HARNESS, "reporter", "solver"]
EXTERNAL_FAMILY = SV.FAMILIES[len(HARNESS)]  # "fake-6": priced from the deployment, as the seventh validator's
EXTERNAL_BOND = 250  # coins: the SEV-SNP plan's `register --bond 250`
EXTERNAL_FUNDS = 5_000  # coins sent to the outside key: its bond, stakes and its share of a challenge's cover
REHEARSAL_IMAGE = "0x" + crypto.keccak256(b"pof external rehearsal checker image").hex()
RPC_PORT, SEED_PORT = 8545, 8776
HOUR = 3600
SEAL_MARGIN = 3 * HOUR  # production windows: suite_v3's margin (a check that can't be run is sealed at once)
PAUSED = HARNESS[2:]  # v2-v5 pause for the fix's draw: genesis, v1 and the outside validator are the panel of 3
GENESIS_MINT = SR.GENESIS_MINT


def settings(env=None) -> dict:
    """The run's settings from the environment (the module's docstring), checked."""
    env = os.environ if env is None else env
    mode = env.get("POF_EXT_MODE", "local")
    if mode not in ("local", "aws"):
        raise SystemExit(f"external_v3: POF_EXT_MODE is local or aws, not {mode!r}")
    bind = env.get("POF_EXT_BIND", "")
    if mode == "aws" and not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", bind):
        raise SystemExit("external_v3: POF_EXT_MODE=aws needs POF_EXT_BIND, the host's private IPv4 address")
    external = env.get("POF_V3_EXTERNAL", "").strip()
    if mode == "aws" and not re.fullmatch(r"0x[0-9a-fA-F]{40}", external):
        raise SystemExit("external_v3: POF_EXT_MODE=aws needs POF_V3_EXTERNAL, the SEV-SNP host's validator address")
    if "," in external:
        raise SystemExit("external_v3: one outside validator (POF_V3_EXTERNAL holds one address here)")
    image = env.get("POF_EXT_IMAGE", "") or REHEARSAL_IMAGE
    if not re.fullmatch(r"0x[0-9a-f]{64}", image):
        raise SystemExit("external_v3: POF_EXT_IMAGE is 0x and 64 lower-case hex digits (manifest.json's image_digest)")
    proof = env.get("POF_EXT_PROOF", "tee" if mode == "aws" else "simulated")
    if proof not in v3.PROOFS:
        raise SystemExit(f"external_v3: POF_EXT_PROOF is one of {sorted(v3.PROOFS)}")
    return {"mode": mode, "bind": bind, "external": external, "image": image, "proof": proof,
            "tee": env.get("POF_EXT_TEE", "amd-sev-snp"), "radNode": env.get("POF_EXT_RAD_NODE", ""),
            "registerWait": float(env.get("POF_EXT_REGISTER_WAIT", "1800")),
            "dir": Path(env.get("POF_EXT_DIR", "") or OUT)}


def external_local_key(sim: str, chain_id: int, race: str) -> str:
    """The rehearsal's outside key: what `python3 -m oracle` derives with ORACLE_KEYS=dstack (its default) from the
    simulator, for this chain and race (oracle/__main__.py `keys_from_env`)."""
    return DstackKeys(f"pof/oracle/{chain_id}/{race.lower()}", endpoint=sim).address()


def ready_doc(s: dict, record: dict, rid: str, seed_nid: str, external: str, rpc_url: str, sim: str = "",
              network: str = "") -> dict:
    """What the outside validator needs, for scripts/rc_aws.py: the chain URL and seed address it reaches, the race,
    the RID, its family and image; in local mode the rehearsal's stand-ins (the simulator, the Docker network)."""
    if s["mode"] == "aws":
        rpc, seed = f"http://{s['bind']}:{RPC_PORT}", f"{seed_nid}@{s['bind']}:{SEED_PORT}"
    else:
        rpc, seed = rpc_url, f"{seed_nid}@seed:{SEED_PORT}"
    doc = {"format": READY_FORMAT, "mode": s["mode"], "external": external, "chainId": record["chainId"],
           "rpc": rpc, "race": record["race"], "registry": record["registry"], "rid": rid, "seed": seed,
           "family": EXTERNAL_FAMILY, "image": s["image"], "bond": EXTERNAL_BOND, "proof": s["proof"],
           "teeType": s["tee"], "windowsKind": record["windowsKind"], "acceptedImages": record.get("images", [])}
    if s["mode"] == "local":
        doc["local"] = {"simulator": sim, "network": network, "radicleImage": VS.IMAGE, "prefix": PREFIX,
                        "root": str(ROOT)}
    return doc


def name_of(table: dict, value: str) -> str:
    """The name in `table` ({name: id bytes}) whose id is `value` (0x hex), else the value itself."""
    for k, v in table.items():
        if "0x" + bytes(v).hex() == str(value).lower():
            return k
    return value


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # a reader never sees half a file


class ExternalStory(K.KitStory):
    def __init__(self, keep: bool, s: dict, result: Path) -> None:
        super().__init__(keep)
        self.s = s
        self.result_path = result
        self.edge = f"{PREFIX}-edge"
        self.ext = ""
        self.out: dict = {"format": FORMAT, "mode": s["mode"], "result": "failed"}

    # ---------- the network: the kit's, with anvil and the seed reachable from outside where the mode says ----------

    def up(self) -> None:
        rad = self.rad
        solc = os.environ.get("POF_SOLC", "")
        if not solc or not (ROOT / solc).is_file():
            raise RuntimeError("POF_SOLC (the pinned solc, scripts/solc.sh) is missing: run scripts/contracts.sh setup")
        VS.docker("network", "create", "--internal", VS.NET)
        # aws: a plain bridge whose ports are published on the host's private address only; local: internal as well
        VS.docker("network", "create", *(["--internal"] if self.s["mode"] == "local" else []), self.edge)
        uid = f"{os.getuid()}:{os.getgid()}"
        publish = ["-p", f"{self.s['bind']}:{RPC_PORT}:8545"] if self.s["mode"] == "aws" else []
        VS.docker("run", "-d", "--name", f"{VS.P}-anvil", "--network", self.edge, "--network-alias", "anvil", *publish,
                  "--user", uid, "-e", "HOME=/tmp", "-v", f"{ROOT}/contracts:/work",
                  "-v", f"{ROOT}/{solc}:/opt/solc/solc:ro", "-w", "/work", "--entrypoint", "anvil", VS.FOUNDRY_IMAGE,
                  "--host", "0.0.0.0", "--port", "8545", "--chain-id", "31337", "--silent")
        VS.docker("network", "connect", "--alias", "anvil", VS.NET, f"{VS.P}-anvil")
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
        VS.log(f"radicle: {self.radicle_version}; mode {self.s['mode']}"
               + (f", anvil and the seed published on {self.s['bind']}" if self.s["mode"] == "aws" else ""))

    def start_seed(self, rid: str) -> None:
        """The seed as kit_radicle starts it (seed-setup.sh, radicle-seed.service's ExecStart), on the outside
        network too: published on POF_EXT_BIND:8776 in aws mode."""
        rad, n = self.rad, "seed"
        publish = ["-p", f"{self.s['bind']}:{SEED_PORT}:8776"] if self.s["mode"] == "aws" else []
        VS.docker("run", "-d", "--name", rad.c(n), "--hostname", n, "--network", self.edge, "--network-alias", n,
                  *publish, VS.IMAGE)
        VS.docker("network", "connect", "--alias", n, VS.NET, rad.c(n))
        VS.docker("cp", f"{K.SEED_DIR}/.", f"{rad.c(n)}:{K.SEED_FILES}")
        out = rad.sh(n, f"bash {K.SEED_FILES}/seed-setup.sh {shlex.quote(rid)} seed seed:8776 test 2>&1")
        rad.did[n] = out.splitlines()[-1].strip()
        start = K.exec_start(K.SEED_DIR / "radicle-seed.service").replace("/usr/local/bin/", "")
        rad.sh(n, f"mkdir -p $RAD_HOME/node && (setsid nohup {start} >$RAD_HOME/node/node.log 2>&1 &) && "
                  f"for _ in $(seq 300); do {K.RUNNING} && break; sleep 0.1; done; {K.RUNNING}")
        rad.started.append(n)
        self.seed_addr = f"{R.nid(rad.did[n])}@seed:8776"

    def repos(self) -> str:
        """kit_radicle's: the repository on the owner's node, the seed from its publication record, then this run's
        other nodes configured as the kit's, cloning it through the seed."""
        rad = self.rad
        rad.sh("owner", "mkdir -p g/tests g/.pof && cd g && git init -q -b main")
        for path, text in SR.GENESIS_FILES.items():
            rad.sh("owner", f"cat > g/{path}", input=text)
        genesis = rad.sh("owner", "cd g && git add -A && git commit -q -m 'genesis: median() is wrong "
                                  "(proof-of-fix#251)' && git rev-parse HEAD")
        rad.sh("owner", "git clone -q g repo-a && cd repo-a && git remote remove origin && rad init --name pof-stats "
                        "--description 'proof-of-fix#251 task 7.0' --default-branch main --public --no-confirm "
                        ">/dev/null 2>&1")
        rad.rid["a"] = rad.sh("owner", "cd repo-a && rad .")
        if not R.RID_RE.match(rad.rid["a"]):
            raise RuntimeError(f"rad init gave no RID: {rad.rid['a']!r}")
        record = {"format": K.publication.FORMAT, "rid": rad.rid["a"], "rootCommit": genesis,
                  "nodeId": R.nid(rad.did["owner"]), "radicle": K.publication.RADICLE}
        (OUT / "record").mkdir(parents=True, exist_ok=True)
        path = OUT / "record" / "publication.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        rid = K.publication.rid(path)
        self.start_seed(rid)
        rad.sh("owner", f"rad node connect {self.seed_addr} >/dev/null 2>&1 || true", check=False)
        for _ in range(60):
            if rad.canonical("seed", "a") == genesis:
                break
            rad.sync("a", ["owner"], "announce")
            time.sleep(1)
        else:
            raise RuntimeError("the seed didn't replicate the repository from the owner's node")
        for n in NODES[1:]:
            self.kit_node(n, rid, self.seed_addr)
            self.ready(n)
        VS.log(f"repository {rid}; genesis {genesis}; seed {self.seed_addr}")
        return genesis

    # ---------- the run ----------

    def run(self) -> int:
        try:
            return super().run()
        finally:
            write_json(self.result_path, self.out)
            VS.log(f"result: {self.result_path} ({self.out['result']})")

    def scenarios(self) -> None:
        self.setup()
        self.registered()
        self.qualified()
        self.judged()
        self.out["result"] = "passed" if all(v == "PASS" for v in self.res.result.values()) else "failed"
        self.res.scenario("R", "the result for the release candidate's external items")
        self.res.ok(f"{FORMAT}: {self.result_path}")

    def setup(self) -> None:
        res, rad, s = self.res, self.rad, self.s
        res.scenario("S", "setup: the launch's rules on production windows, the outside validator's image accepted, "
                          "the seed, six harness validators on their own Radicle nodes, the outside key funded")
        if subprocess.run(["docker", "image", "inspect", sandbox.TEST_IMAGE], capture_output=True).returncode:
            raise SR.Failed(f"the pinned test image isn't here ({sandbox.TEST_IMAGE}); build it: scripts/test-image.sh")
        t0 = time.time()
        self.up()
        genesis_commit = self.repos()
        minter = crypto.address(secret("minter"))
        launch = {**SR.LAUNCH, "LOCAL_WINDOWS": "production", "LOCAL_GENESIS_MINT_TO": minter,
                  "LOCAL_FAMILIES": ",".join(SV.FAMILIES[:len(HARNESS) + 1]), "LOCAL_EXTRA_IMAGE": s["image"]}
        record = self.deploy_v3(rad.rid["a"], genesis_commit, env=launch)
        self.rpc.call("anvil_setBlockTimestampInterval", [0])  # chain time moves only when the run moves it
        record["rid"] = rad.rid["a"]
        self.record_path = OUT / "record.json"
        self.record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        self.server = SR.bridge(self.rpc)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        rules = record["panelRules"]
        w = record["windows"]
        self.must(rules == {"operatorCap": "off", "hostCap": "off", "teeCap": "off", "kTop": 3, "challengeSize": "same"}
                  and record["windowsKind"] == "production" and w["seal"] == 2 * HOUR and w["reveal"] == HOUR
                  and record["judgeFee"] == 0 and record.get("faucet"),
                  f"deployed on the launch's rules (caps off, kTop 3, same-size challenges: {rules}) on production "
                  f"windows (seal {w['seal']} s, reveal {w['reveal']} s), the taxi fare, POFTEST and its faucet")
        self.must(s["image"] in [x.lower() for x in record.get("images", [])]
                  and self.rpc.view(record["registry"], "allowedImage(bytes32)", ["bool"], s["image"])[0],
                  f"the outside validator's checker image {s['image'][:18]}… is on the registry's list "
                  f"(allowedImage; the record lists {len(record.get('images', []))} images)")
        n = self.n = SR.RadNet(self.rpc, record, OUT / "work", self)
        c = n.chain
        self.ext = s["external"] or external_local_key(n.sim, c.chain_id(), c.race)
        n.external = {self.ext.lower()}  # the moved clock waits for its seats (suite_v3 `held_by_external`)
        n.names[self.ext.lower()] = "outside"
        g = n.make_node("genesis", SV.FAMILIES[0], keeper=True)
        self.rpc.call("anvil_setBalance", [g.address, ETH_100])
        n.nodes["genesis"] = g
        self.owner_seat = RV.SeatAdapter(R.Radicle(rad.rid["a"], ["docker", "exec", "-i", rad.c("owner")], SR.REPO),
                                         c, "0x" + "00" * 20, D.ChainSeatNodes.of(c), log=n.log("owner"), every=15)
        n.watches.append(self.owner_pass)
        for i in range(1, len(HARNESS)):
            n.join(i)
        n.start = max(self.rpc.block() - 20, 0)
        t = time.time()
        made = n.grow(HARNESS[1:], 12, "v1 to v5 qualify", rounds=60)
        self.wall["qualification"] = round(time.time() - t)
        self.must(len(n.active()) == len(HARNESS),
                  f"v1 to v5 qualified by their shadow verdicts after {made} registration checks claimed by Radicle "
                  f"issues ({self.wall['qualification']} s): {len(HARNESS)} harness validators active")
        for role in ("reporter", "funder", "solver-a"):
            n.fund(self.addr(role), 2_000)
        n.fund(self.ext, EXTERNAL_FUNDS)
        self.must(c.balance(self.ext) >= EXTERNAL_FUNDS * SR.COIN,
                  f"the outside key {self.ext} funded: {EXTERNAL_FUNDS:,} POFTEST and gas")
        seed_nid = R.nid(rad.did["seed"])
        self.ready_path = s["dir"] / "ready.json"
        doc = ready_doc(s, record, rad.rid["a"], seed_nid, self.ext, self.url, sim=n.sim, network=self.edge)
        write_json(self.ready_path, doc)
        self.out.update({"chainId": record["chainId"], "race": record["race"], "registry": record["registry"],
                         "windowsKind": record["windowsKind"], "acceptedImages": record.get("images", []),
                         "rid": rad.rid["a"], "seed": doc["seed"], "rpc": doc["rpc"]})
        self.wall["setup"] = round(time.time() - t0)
        res.info(f"ready for the outside validator: {self.ready_path} (rpc {doc['rpc']}, race {record['race']}, "
                 f"seed {doc['seed']})")

    def registered(self) -> None:
        """X: the outside validator registers itself; nothing here signs for it."""
        res, n, s = self.res, self.n, self.s
        c = n.chain
        res.scenario("X", "the outside validator registers itself: its own key, attestation, image and Radicle node")
        t = time.time()
        while c.validator(self.ext)["bond"] == 0:
            if time.time() - t > s["registerWait"]:
                raise SR.Failed(f"the outside validator {self.ext} didn't register within {s['registerWait']:.0f} s")
            for name, node in n.nodes.items():
                node.tick(n.start)
            time.sleep(2)
        v = c.validator(self.ext)
        rad_node = c.rad_node_of(self.ext)
        reg = {"key": self.ext, "proofType": name_of(v3.PROOFS, v["proofType"]),
               "teeType": name_of({s["tee"]: v3.name_id(s["tee"])}, v["teeType"]),
               "image": str(v["image"]).lower(), "family": name_of({EXTERNAL_FAMILY: v3.name_id(EXTERNAL_FAMILY)},
                                                                   v["family"]),
               "level": v["level"], "attestation": str(v["attestation"]), "bond": v["bond"],
               "radNode": R.nid(D.did_from_key(rad_node)) if any(rad_node) else "",
               "waitedSeconds": round(time.time() - t)}
        self.out["registration"] = reg
        want_nid = R.nid(s["radNode"]) if s["radNode"].startswith("did:") else s["radNode"]
        self.must(reg["proofType"] == s["proof"] and reg["teeType"] == s["tee"] and reg["image"] == s["image"]
                  and reg["family"] == EXTERNAL_FAMILY and reg["bond"] >= EXTERNAL_BOND * SR.COIN and reg["radNode"]
                  and (not want_nid or reg["radNode"] == want_nid) and int(reg["attestation"], 16) != 0,
                  f"{self.ext} registered after {reg['waitedSeconds']} s: proof {reg['proofType']}, TEE "
                  f"{reg['teeType']}, image {reg['image'][:18]}…, family {reg['family']}, bond "
                  f"{reg['bond'] / SR.COIN:,.0f}, attestation {reg['attestation'][:18]}…, Radicle node "
                  f"{reg['radNode'][:16]}…" + (" (the expected one)" if want_nid else ""))

    def seats_of(self, key: str) -> list:
        """[(pid, slot, panel kind)] of every seat `key` was given."""
        c, out = self.n.chain, []
        for log in self.n.evs(c.panels, v3.SEATED):
            if "0x" + log["topics"][2][-40:].lower() == key.lower():
                pid = int(log["topics"][1], 16)
                keys = [k.lower() for k in c.judges(pid)]
                if key.lower() in keys:
                    out.append((pid, keys.index(key.lower()), c.panel(pid)["kind"]))
        return out

    def qualified(self) -> None:
        """Q: it qualifies by its shadow verdicts, read from Radicle issues on its own node."""
        res, n = self.res, self.n
        c = n.chain
        res.scenario("Q", "the outside validator qualifies by its shadow verdicts on Radicle-claimed registrations")
        t = time.time()
        feed, made = n.feeder(3, 40)
        n.drive(lambda: c.is_active(self.ext), "the outside validator qualified", feed=feed, poke=True)
        seats = self.seats_of(self.ext)
        revealed = sum(1 for pid, slot, _ in seats if c.seat(pid, slot)["revealed"])
        self.out["qualification"] = {"checks": made[0], "seats": len(seats), "revealed": revealed,
                                     "wallSeconds": round(time.time() - t),
                                     "holds": len(n.external_waits)}
        self.must(c.is_active(self.ext) and revealed >= 1,
                  f"active after {made[0]} more registration checks: {len(seats)} seats, {revealed} revealed in wall "
                  f"time while the clock waited ({len(n.external_waits)} seat deadlines held), "
                  f"{round(time.time() - t)} s")

    def capacity(self, name: str, checks: int) -> None:
        """scenarios_v3's `capacity_now`: `name` sets its capacity (0 pauses it), in force CAP_DELAY blocks later."""
        n = self.n
        c, node = n.chain, n.nodes[name]
        frm = c.capacity(node.address)["from"]
        if c.block() < frm:
            self.rpc.call("anvil_mine", [hex(frm - c.block() + 1)])
        node.wallet.send(c.panels, "setCapacity(address,uint256)", node.address, checks)
        frm = c.capacity(node.address)["from"]
        if c.block() < frm:
            self.rpc.call("anvil_mine", [hex(frm - c.block() + 1)])

    def judged(self) -> None:
        """F: a fix judged by a counted panel with the outside validator on it."""
        res, rad, n = self.res, self.rad, self.n
        c = n.chain
        res.scenario("F", "a fix as a Radicle patch, judged by a counted panel of 3 with the outside validator on it")
        title, body = SR.ISSUES["median"]
        iid = self.rad_issue("reporter", "a", title, body)
        d = self.ctl("issue", "register", "--rad-issue", iid, "--comment", "--rad-exec",
                     f"docker exec -i {rad.c('reporter')}", as_="reporter")
        c.live[d["check"]] = True
        rad.sync("a", ["reporter"], "announce")
        n.drive(lambda: c.verdict(d["check"])["status"] == v3.FINAL, "the issue's registration check final", poke=True)
        bounty = self.ctl("issue", "open", "--issue", d["issue"], as_="reporter")["bounty"]
        res.ok(f"Radicle issue {iid[:7]} registered ({d['issue']}), its check final, bounty {bounty} opened")
        before = {name: c.capacity(n.nodes[name].address)["checks"] for name in PAUSED}
        for name in PAUSED:
            self.capacity(name, 0)
        res.ok(f"{', '.join(PAUSED)} paused (capacity 0) for the draw: genesis, v1 and the outside validator can sit")
        base = self.head()
        sha = rad.commit_on("solver", "a", base, SR.files_with(["median"]), "median() of an even list")
        sub = self.ctl("submit", "--bounty", bounty, "--patch", sha, "--title", "median", as_="solver-a")
        s = sub["submission"]
        c.live[s] = True
        opened = rad.sh("solver", f"cd {SR.REPO} && {sub['patchCommand']} 2>&1", check=False)
        m = re.search(r"Patch ([0-9a-f]{40}) opened", opened)
        self.must(m is not None, f"solver-a sealed submission {s} (commit {sha[:12]}) and opened its patch with "
                                 f"pofctl's printed command" + ("" if m else f": {opened[-300:]}"))
        rad.sync("a", ["solver"], "announce")
        n.drive(lambda: c.verdict(s)["pid"] != 0, f"submission {s}'s counted panel drawn", poke=True)
        pid = c.verdict(s)["pid"]
        keys = [k.lower() for k in c.judges(pid)]
        for name in PAUSED:
            self.capacity(name, before[name])  # back to what each had
        self.must(self.ext.lower() in keys, f"counted panel {pid} drawn: {n.named(c.judges(pid))}; the four resumed")
        slot = keys.index(self.ext.lower())
        t = time.time()
        n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) or c.panel(pid)["counted"],
                f"submission {s} judged", poke=True)
        seat, p, v = c.seat(pid, slot), c.panel(pid), c.verdict(s)
        self.out["judged"] = {"submission": s, "bounty": bounty, "fix": sha, "patch": m.group(1), "pid": pid,
                              "slot": slot, "kind": v3.KINDS[p["kind"]], "sealed": bool(seat["hasSeal"]),
                              "revealed": bool(seat["revealed"]), "counted": bool(p["counted"]),
                              "receipted": bool(seat.get("receipted")), "pass": bool(v["pass"]),
                              "status": v3.STATUS[v["status"]], "wallSeconds": round(time.time() - t),
                              "holds": len(n.external_waits)}
        self.must(p["kind"] == v3.COUNTED and seat["hasSeal"] and seat["revealed"] and p["counted"],
                  f"panel {pid} counted with the outside validator's verdict: seat {slot} sealed and revealed "
                  f"({'receipted, ' if seat.get('receipted') else ''}verdict {'pass' if v['pass'] else 'fail'}, "
                  f"status {v3.STATUS[v['status']]}), {round(time.time() - t)} s of wall time")

    def isolation(self, others: tuple = ("relay",)) -> None:
        """The run's internal network has no route out; every harness validator's Radicle node dialled only the seed,
        outbound. (The outside network is internal in local mode; in aws mode it is the published one, and the host's
        security group is the boundary: validator-kit/sevsnp/testchain.)"""
        res, rad = self.res, self.rad
        res.scenario("I", "isolation: the run's internal network, no route out, harness validators outbound to the "
                          "seed only")
        res.expect(f"network {VS.NET} is internal", VS.docker("network", "inspect", "-f", "{{.Internal}}", VS.NET),
                   "true")
        res.expect(f"network {self.edge} is internal", VS.docker("network", "inspect", "-f", "{{.Internal}}",
                                                                 self.edge),
                   "true" if self.s["mode"] == "local" else "false")
        for x in others:
            routes = VS.docker("exec", f"{VS.P}-{x}", "awk", '$2 == "00000000"', "/proc/net/route").splitlines()
            res.expect(f"{x}: default routes", len(routes), 0)
        seed = R.nid(rad.did.get("seed", "")) if rad.did.get("seed") else ""
        for name in HARNESS:
            if name not in rad.started:
                continue
            log = rad.sh(name, "cat $RAD_HOME/node/node.log 2>/dev/null", check=False)
            (OUT / f"{name}.log").write_text(log, encoding="utf-8")
            routes = rad.sh(name, "awk '$2 == \"00000000\"' /proc/net/route | wc -l", check=False)
            peers = {peer for peer, _, _ in re.findall(r"Connected to (\S+) \(([^)]*)\) \((Inbound|Outbound)\)", log)}
            res.check(routes == "0" and "(Inbound)" not in log and peers <= {seed},
                      f"{name}: {routes} default routes, no inbound session, connected to {sorted(peers) or 'none'} "
                      f"(the seed only)")

    def write(self) -> None:
        super().write()
        self.out["results"] = {k: self.res.result[k] for k in self.res.order}
        self.out["wallSeconds"] = round(time.time() - self.started)
        self.out["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                            text=True).stdout.strip()
        if self.out["result"] == "passed" and not all(v == "PASS" for v in self.out["results"].values()):
            self.out["result"] = "failed"  # isolation runs after the story


def clean() -> None:
    K.clean()


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and networks up (for debugging)")
    ap.add_argument("--result", help="where the result goes (default POF_EXT_DIR/external.json)")
    a = ap.parse_args(argv[1:])
    VS.use_names(PREFIX, NODES + ["seed"], OUT, RECORD_DIR)
    K.PREFIX = PREFIX
    K.OUT = SR.OUT = OUT
    K.VALIDATORS = SR.VALIDATORS = HARNESS  # node containers beside these Radicle nodes; RadNet's registrations
    SR.NODES = NODES
    SR.SEAL_MARGIN = SEAL_MARGIN
    SR.RadNet = K.KitNet
    edge = f"{PREFIX}-edge"

    def clean_all() -> None:
        K.clean()
        VS.docker("network", "rm", edge, check=False)
    VS.clean = clean_all
    if a.command == "clean":
        clean_all()
        SR.fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    s = settings()
    result = Path(a.result) if a.result else s["dir"] / "external.json"
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return ExternalStory(a.keep, s, result).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
