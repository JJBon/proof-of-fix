"""The onboarding guides (docs/guides/, proof-of-fix#251 task 5.7) on the local devnet with Radicle on the internal
network. Run it with `scripts/radicle-spike.sh --guides`, which builds the spike's node image and calls this file.
`python3 tests/integration/guides_radicle.py clean` removes anything a stopped run left behind.

Not a new harness: task 4.6's (tests/integration/suite_v3_radicle.py `Story`, under its own names): the launch's rules
on anvil, seven validators on their own Radicle 1.10.3 nodes (ORACLE_FIX_SOURCE=radicle, ORACLE_MERGE_VIA=radicle,
ORACLE_SEAT_NODES=chain), five registered issues and three solvers made active by unfunded fixes. The one difference in
that setup: the repository also carries the program (oracle/, pofctl/, bot/, pof/, scripts/pofctl at this checkout's
HEAD), so a newcomer's `rad clone` gets `scripts/pofctl` as from proof-of-fix itself.

Then each guide runs on its own **newcomer's machine**: a fresh container (the node image with python3, built by
publish_radicle.py) with no Radicle key, no key and no checkout, on the same internal network. Every ```bash block of
the guide runs as written, in order, in one shell session per guide (variables, functions and the directory carry over
from block to block). An HTML comment `<!-- test: NAME -->` before a block names what the test does there, because a
person would do it by hand or the test stands in for the public network:
  values, devnet-values  the block's values are replaced by the devnet's (the RPC is anvil on the internal network, the
                     RID the devnet's repository, the record this run's deployment record, and a stand-in for dstack's
                     simulator on the newcomer's machine, tests/e2e_node_v3.py's);
  radicle-config     the node's config is the devnet's (Radicle's test network, no bootstrap seeds, static peers: the
                     validators', the owner's and the reporter's nodes), where a person keeps Radicle's default;
  radicle-peers      waits until the new node has a route to the repository (the network's gossip);
  gas, bond          the address gets ETH for gas (a Sepolia faucet's stand-in), and for a validator its bond's coins
                     from the genesis mint (the owner's transfer);
  make-fix           writes the fix (what the solver edits by hand);
  wait-registration, wait-verdict, wait-final, wait-main
                     the validators judge, the chain's clock moves to the next deadline (the windows are minutes), and
                     the seats' nodes push the canonical main;
  skip (reason)      not run: the reason says what instead.
What a person types at a prompt comes from the variables the tools document for unattended runs: RAD_PASSPHRASE (empty),
CAST_PASSWORD and POFCTL_KEYSTORE_PASSWORD_FILE (one throwaway password).

  S, 1, 2: task 4.6's setup, registration and activation;
  G1. fund an issue: a new Radicle issue registered by the newcomer, its check final, the bounty opened, a pledge;
  G2. submit a fix: another newcomer fixes that bounty, seals it, opens the patch; a panel of 3 passes it; claim, merge,
      the canonical main on every node, withdraw;
  G3. run a validator: a third newcomer registers with its own Radicle node's key (`radNodeOf`);
  7. task 4.6's verify-head and verify-delegates;
  I. isolation (the spike's check), the newcomers' nodes included.

No model call, no public chain or network, no AWS. Transcripts and results stay in .guides-radicle/ (gitignored)."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration", ROOT / "spikes" / "radicle"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import publish_radicle as PR  # noqa: E402
import suite_v3 as SV  # noqa: E402
import suite_v3_radicle as SR  # noqa: E402
import v3_spike as VS  # noqa: E402
from e2e_node_v3 import ETH_100  # noqa: E402
from oracle import abi, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402

PREFIX = "pof251g"
OUT = ROOT / ".guides-radicle"
RECORD_DIR = ROOT / "contracts" / "deployments" / "guides-radicle"
GUIDES = ROOT / "docs" / "guides"
HOME_C = VS.HOME_C
PASSWORD = "guides-test-password"  # the newcomers' throwaway keystore password: what each would type
PROGRAM = ["oracle", "pofctl", "bot", "pof", "scripts/pofctl"]  # what pofctl and `python3 -m oracle` import
NEWCOMERS = {"fund-an-issue": "new-funder", "submit-a-fix": "new-solver", "run-a-validator": "new-validator"}
MARKER = re.compile(r"^<!--\s*test:\s*(.+?)\s*-->\s*$")
# The session's prelude: the last block's variables (all assignments are exported, `set -a`), functions and directory.
PRELUDE = r"""set -eo pipefail
mkdir -p ~/.guide
save() { export -p | grep -vE '^declare -x (PWD|OLDPWD|SHLVL|_)=' > ~/.guide/env.new || true
  mv ~/.guide/env.new ~/.guide/env; declare -f > ~/.guide/funcs; pwd > ~/.guide/cwd; }
[ -f ~/.guide/env ] && . ~/.guide/env
[ -f ~/.guide/funcs ] && . ~/.guide/funcs
cd "$(cat ~/.guide/cwd 2>/dev/null || echo ~)"
trap save EXIT
set -a
"""
SIM_PORT = 8090
SIMULATOR = f"""import hashlib, json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Agent(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/GetKey":
            out = {{"key": hashlib.sha256(("pof guides " + body["path"]).encode()).hexdigest()}}
        else:
            out = {{"quote": hashlib.sha256(b"simulated quote " + body["report_data"].encode()).hexdigest()}}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", {SIM_PORT}), Agent).serve_forever()
"""
FIX_TEST = ("import unittest\n\nfrom stats import median\n\n\nclass Issue(unittest.TestCase):\n"
            "    def test_median_of_an_empty_list(self):\n        with self.assertRaises(ValueError):\n"
            "            median([])\n")


def blocks(path: Path) -> list:
    """The guide's fenced blocks in order: {"lang", "code", "marker" (the `<!-- test: … -->` just before it), "line"}."""
    out, marker, fence, buf, start = [], None, None, [], 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if fence is not None:
            if line.strip() == "```":
                out.append({"lang": fence, "code": "\n".join(buf) + "\n", "marker": pending, "line": start})
                fence, buf = None, []
            else:
                buf.append(line)
            continue
        m = MARKER.match(line.strip())
        if m:
            marker = m.group(1)
        elif line.startswith("```"):
            fence, pending, start, marker = line[3:].strip(), marker, i, None
        elif line.strip():
            marker = None
    return out


class Failed(AssertionError):
    pass


class Newcomer:
    """A newcomer's machine: the node image with python3, no Radicle key, no keys, no checkout."""

    def __init__(self, story: "GuideStory", name: str, guide: str) -> None:
        self.story, self.name, self.guide = story, name, guide
        self.c = story.rad.c(name)
        self.transcript: list = []
        VS.docker("run", "-d", "--name", self.c, "--hostname", name, "--network", VS.NET, "--network-alias", name,
                  PR.PY_NODE_IMAGE)
        self.sh(f"printf %s {shlex.quote(PASSWORD)} > ~/.pw && chmod 600 ~/.pw")
        VS.docker("cp", str(story.record_path), f"{self.c}:{HOME_C}/record.json")

    def sh(self, script: str, check: bool = True, input: str | None = None) -> str:
        return self.story.rad.sh(self.name, script, check=check, input=input)

    def var(self, name: str) -> str:
        return self.sh(f". ~/.guide/env && printf %s \"${name}\"", check=False)

    def cwd(self) -> str:
        return self.sh("cat ~/.guide/cwd")

    def run(self, code: str, where: str) -> str:
        env = ["-e", "RAD_PASSPHRASE=", "-e", f"CAST_PASSWORD={PASSWORD}",
               "-e", f"POFCTL_KEYSTORE_PASSWORD_FILE={HOME_C}/.pw"]
        r = subprocess.run(["docker", "exec", "-w", HOME_C, *env, self.c, "bash", "-c", PRELUDE + code],
                           capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
        out = (r.stdout + r.stderr).rstrip()
        self.transcript += [f"$ # {where}"] + [f"$ {x}" for x in code.rstrip().splitlines()] + [out, ""]
        if r.returncode:
            raise Failed(f"{self.guide} {where}: exit {r.returncode}: {out[-700:]}")
        return out


class GuideStory(SR.Story):
    def repos(self) -> str:
        """Task 4.6's repository, with the program in it (so `rad clone` gives a newcomer `scripts/pofctl`)."""
        tree = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", "HEAD", *PROGRAM],
                              capture_output=True, check=True, timeout=120).stdout
        self.rad.sh("owner", "mkdir -p g")
        subprocess.run(["docker", "exec", "-i", "-w", HOME_C, self.rad.c("owner"), "tar", "-x", "-C", "g"], input=tree,
                       capture_output=True, check=True, timeout=120)
        return super().repos()

    def scenarios(self) -> None:
        self.setup()
        self.registration()
        self.activation(self.issues)
        for name in SR.VALIDATORS:  # bonded for funded bounties, as task 4.6's funded step does
            self.n.top_up(name, self.n.bond_for(110 * SR.COIN))
        self.newcomers = {}
        self.guide("G1", "fund-an-issue", "fund an issue: a newcomer opens and registers a Radicle issue, opens its "
                                          "bounty and pledges")
        self.guide("G2", "submit-a-fix", "submit a fix: another newcomer fixes that bounty as a Radicle patch, claims "
                                         "and merges it")
        self.guide("G3", "run-a-validator", "run a validator: a third newcomer registers with its own Radicle node's "
                                            "key (stops before AWS)")
        self.verify()

    # ---------- running a guide ----------

    def guide(self, key: str, name: str, title: str) -> None:
        res = self.res
        res.scenario(key, title)
        path = GUIDES / f"{name}.md"
        who = self.newcomers[name] = Newcomer(self, NEWCOMERS[name], name)
        bash = [b for b in blocks(path) if b["lang"] == "bash"]
        ran = skipped = 0
        try:
            for b in bash:
                where = f"{path.relative_to(ROOT)}:{b['line']}"
                marker = b["marker"] or ""
                if marker.startswith("skip"):
                    skipped += 1
                    res.info(f"not run ({where}): {marker}")
                    continue
                code = b["code"]
                if marker in ("values", "devnet-values"):
                    code = self.values(name, marker, code)
                elif marker:
                    getattr(self, "hook_" + marker.replace("-", "_"))(who)
                out = who.run(code, where)
                ran += 1
                res.ok(f"{where} ran as written ({len(code.strip().splitlines())} line(s))"
                       + (f", after the test's `{marker}`" if marker and marker not in ("values", "devnet-values")
                          else "") + (f": {out.splitlines()[-1][:160]}" if out else ""))
                after = getattr(self, f"after_{name.replace('-', '_')}", None)
                if after:
                    after(who, b)
        finally:
            (OUT / f"{name}.txt").write_text("\n".join(who.transcript) + "\n", encoding="utf-8")
        res.check(ran > 0, f"{name}: {ran} block(s) ran as written, {skipped} not run (reasons above); transcript in "
                           f".guides-radicle/{name}.txt")

    def values(self, name: str, marker: str, code: str) -> str:
        """The block's `export NAME=…` values, the devnet's in place of Sepolia's; the block's names must be these."""
        rid = self.rad.rid["a"]
        devnet = {"POFCTL_RPC": "http://anvil:8545", "RID": rid, "RECORD": f"{HOME_C}/record.json",
                  "FAMILY": SV.FAMILIES[1], "ORACLE_VERSION": "3", "ORACLE_RPC": "http://anvil:8545"}
        if name == "submit-a-fix":
            devnet["BOUNTY"] = self.newcomers["fund-an-issue"].var("BOUNTY")
        if "DSTACK_SIMULATOR_ENDPOINT" in code:
            devnet["DSTACK_SIMULATOR_ENDPOINT"] = self.start_simulator(self.newcomers[name])
        names = re.findall(r"\b([A-Z_]+)=", code)
        missing = [x for x in names if x not in devnet]
        if missing:
            raise Failed(f"{name}'s {marker} block sets {missing}, which the test has no devnet value for")
        self.res.info(f"{marker}: " + ", ".join(f"{x}={devnet[x]}" for x in names))
        return "".join(f"export {x}={shlex.quote(str(devnet[x]))}\n" for x in names)

    def start_simulator(self, who: Newcomer) -> str:
        """A stand-in for dstack's simulator on the newcomer's machine (tests/e2e_node_v3.py's): a key per path, and
        a quote over the report data."""
        who.sh(f"cat > ~/dstack_sim.py && (setsid nohup python3 ~/dstack_sim.py >/dev/null 2>&1 &) && "
               f"for _ in $(seq 40); do python3 -c 'import socket; socket.create_connection((\"127.0.0.1\", "
               f"{SIM_PORT}))' 2>/dev/null && break; sleep 0.25; done", input=SIMULATOR)
        return f"http://127.0.0.1:{SIM_PORT}"

    # ---------- the hooks: what a person does by hand, or the network does ----------

    def peers(self) -> list:
        return ["owner", *SR.VALIDATORS, "reporter"]

    def hook_radicle_config(self, who: Newcomer) -> None:
        """Radicle's test network and static peers, where a person keeps the default config (bootstrap seeds)."""
        cfg = json.loads(who.sh("cat $RAD_HOME/config.json"))
        cfg["publicExplorer"] = "http://localhost/disabled/$host/$rid$path"
        cfg["preferredSeeds"] = []
        node = cfg.setdefault("node", {})
        node.update({"network": "test", "peers": {"type": "static"}, "listen": ["0.0.0.0:8776"],
                     "externalAddresses": [],
                     "connect": [f"{R.nid(self.rad.did[p])}@{p}:8776" for p in self.peers()]})
        who.sh("cat > $RAD_HOME/config.json", input=json.dumps(cfg, indent=2))
        self.rad.did[who.name] = who.sh("rad self --did")

    def hook_radicle_peers(self, who: Newcomer) -> None:
        """The new node has a route to the repository before it clones (gossip from the peers it dialled)."""
        if who.name not in self.rad.started:
            self.rad.started.append(who.name)
        rid = self.rad.rid["a"]
        for _ in range(90):
            if R.nid(self.rad.did["owner"]) in who.sh(f"rad node routing --rid {rid} --json 2>&1", check=False):
                return
            time.sleep(1)
        raise Failed(f"{who.name}'s node learned no route to {rid} in 90 s")

    def address_of(self, who: Newcomer) -> str:
        """The newcomer's keystore address, as pofctl reads it (cast's keystore file doesn't name it)."""
        out = who.sh(f". ~/.guide/env && cd {who.cwd()} && POFCTL_KEYSTORE_PASSWORD_FILE={HOME_C}/.pw "
                     f"scripts/pofctl --json --v3 status")
        return json.loads(out)["solver"]

    def hook_gas(self, who: Newcomer) -> None:
        addr = self.address_of(who)
        self.rpc.call("anvil_setBalance", [addr, ETH_100])
        self.res.info(f"{who.name} ({addr}): ETH for gas, as from a Sepolia faucet")

    def hook_bond(self, who: Newcomer) -> None:
        addr = who.var("VALIDATOR")
        self.n.fund(addr, 300)
        self.res.info(f"{who.name} ({addr}): ETH for gas and 300 test coins from the genesis mint for the bond")

    def hook_make_fix(self, who: Newcomer) -> None:
        stats = who.sh(f"cat {who.cwd()}/stats.py")
        head = "def median(xs):\n    return "
        if head not in stats:
            raise Failed("stats.py has no median() to fix")
        fixed = stats.replace(head, "def median(xs):\n    if not xs:\n        raise ValueError(\"median() of an empty "
                                    "list\")\n    return ")
        who.sh(f"cat > {who.cwd()}/stats.py", input=fixed)
        who.sh(f"cat > {who.cwd()}/test_median_empty.py", input=FIX_TEST)

    def hook_wait_registration(self, who: Newcomer) -> None:
        n, c = self.n, self.n.chain
        reg = int(who.var("REG"))
        log = n.evs(c.race, v3.REGISTERED, reg)[0]
        check = abi.decode(["uint256"], abi.hexdata(log["data"]))[0]
        c.live[check] = True
        self.rad.sync("a", [who.name], "announce")
        t = c.now()
        n.drive(lambda: c.verdict(check)["status"] == v3.FINAL, "the newcomer's registration check final", poke=True)
        v = c.verdict(check)
        self.must(v["pass"], f"registration {reg}'s check (submission {check}) passed and is final: the validators "
                             f"read the newcomer's Radicle issue on their own nodes "
                             f"({SV.hours(c.now() - t)} of chain time under the minutes windows)")
        self.chain_t["guideRegistrationToFinal"] = c.now() - t

    def submission(self, who: Newcomer) -> dict:
        return json.loads(who.sh(f"cat {who.var('SUB')}"))

    def hook_wait_verdict(self, who: Newcomer) -> None:
        n, c = self.n, self.n.chain
        d = self.submission(who)
        s, sha, base = d["submission"], d["fix"], d["base"]
        c.live[s] = True
        seen = set()
        for _ in range(60):  # every validator's own node lists the patch on Heads.head before the panel is drawn
            for name in SR.VALIDATORS:
                pulls, _ = n.nodes[name].fixes.revisions()
                if any(p["head_sha"] == sha and p["base_sha"] == base for p in pulls):
                    seen.add(name)
            if len(seen) == len(SR.VALIDATORS):
                break
            self.rad.sync("a", [who.name], "announce")
            time.sleep(1)
        self.must(len(seen) == len(SR.VALIDATORS), f"the newcomer's patch is on all 7 validators' nodes "
                                                   f"({len(seen)} of 7), its base Heads.head")
        t = c.now()
        n.drive(lambda: c.verdict(s)["status"] in (v3.WINDOW, v3.FINAL) and c.submission(s)["paid"],
                "the newcomer's fix judged", poke=True)
        v = c.verdict(s)
        self.must(v["pass"] and v["k"] == 3, f"a counted panel of 3 ({n.named(n.panel.drawn(s))}) passed submission "
                                             f"{s} ({SV.hours(c.now() - t)} of chain time)")
        self.chain_t["guideCommitToCounted"] = c.now() - t

    def hook_wait_final(self, who: Newcomer) -> None:
        n, c = self.n, self.n.chain
        s = self.submission(who)["submission"]
        t = c.now()
        n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, "the newcomer's fix final", poke=True)
        self.chain_t["guideClaimToFinal"] = c.now() - t
        self.res.ok(f"submission {s} is final ({SV.hours(c.now() - t)} of chain time after the claim)")

    def hook_wait_main(self, who: Newcomer) -> None:
        sha = self.submission(who)["fix"]
        self.must(self.head() == sha, f"Heads.head is the newcomer's fix {sha[:12]}")
        secs = self.follow(sha, "the newcomer's fix")
        self.res.ok(f"the canonical main on every delegate's node is {sha[:12]} ({secs} s of forced passes)")

    # ---------- checks after a block ----------

    def after_fund_an_issue(self, who: Newcomer, block: dict) -> None:
        if "pledge" in block["code"]:
            b = int(who.var("BOUNTY"))
            held = self.rpc.view(self.n.chain.race, "held(uint256,address)", ["uint256"], b,
                                 self.n.chain.coin())[0]
            self.must(self.n.bounty_state(b) == SV.OPEN and held > 0,
                      f"bounty {b} is open and holds {held / SR.COIN:,.2f} of the newcomer's pledge")

    def after_submit_a_fix(self, who: Newcomer, block: dict) -> None:
        if "withdraw" in block["code"]:
            b = int(who.var("BOUNTY"))
            c = self.n.chain
            self.must(c.award(b, c.bounty(b)["epoch"])["merged"], f"bounty {b}'s award is merged")

    def after_run_a_validator(self, who: Newcomer, block: dict) -> None:
        if "oracle register" in block["code"]:
            addr, did = who.var("VALIDATOR"), who.var("RAD_NODE")
            c = self.n.chain
            self.must(c.rad_node_of(addr) == D.key_from_did(did) and c.validator(addr)["bond"] >= 250 * SR.COIN,
                      f"{addr} is registered with a bond of {c.validator(addr)['bond'] / SR.COIN:,.0f} and its own "
                      f"Radicle node's key on-chain (radNodeOf = {did})")


def main(argv: list) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=["run", "clean"])
    ap.add_argument("--keep", action="store_true", help="leave the containers and network up (for debugging)")
    a = ap.parse_args(argv[1:])
    VS.use_names(PREFIX, SR.NODES, OUT, RECORD_DIR)
    SR.OUT = OUT  # task 4.6's Story keeps its scratch here, beside this run's results
    if a.command == "clean":
        VS.clean()
        SR.fetch.remove(OUT)
        VS.log("cleaned")
        return 0
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    PR.build_py_image()
    return GuideStory(a.keep).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
