"""The integration suite against the AWS devnet (proof-of-fix#152's second box): `scripts/integration.sh --target aws`.

It plays the roles against the live devnet, the `pof-sandbox` repository and the live validator nodes, with the fake
judge, and asserts what changed. It starts no node: the 6 role seats are scripts/devnet-seats.sh's (on the fake judge,
its default) and seat 6 is the owner's kit. Run the preflight first; it only reads:

    scripts/integration.sh --target aws --preflight     reachability, chain ID, record, seats, repository, balances
    scripts/integration.sh --target aws                 scenarios 2, 3, 1 and 5, then the fees withdrawn, the books and
                                                        the leaderboard over the run's own bounties (#151)
    scripts/integration.sh --target aws --only 2        some of them (4, 6, 7 and 8 are local-only: listed as skipped)
    scripts/integration.sh --target aws --withdraw-only every seat's fees withdrawn, seat 6's too with its key (#150)
    scripts/integration.sh --target aws --cleanup       close and delete what an interrupted run left in pof-sandbox

The environment (the same names as scripts/devnet-seats.sh and scripts/first-bounty.sh):
    DEVNET_RPC_URL                  the devnet (https, no credential in it)
    DEVNET_RPC_AUTH or _FILE        "<handle>:<key>"
    FIRST_BOUNTY_TOKEN or _FILE     a token with write:repository and write:issue on pof-sandbox (issues, fix branches,
                                    pull requests, merges, and the cleanup). Not pof-validator-bot's: that one only reads
    FIRST_BOUNTY_USER               that token's user
  optional:
    DEVNET_REPO_TOKEN or _FILE      the seats' read-only token: the preflight checks it reads and can't write
    POFCTL_KEY_ENGINEER or _FILE    seat 6's own key (the kit's secret): then seat 6's fees are withdrawn too (#150)
    DEVNET_EXCHANGE_URL, DEVNET_REPO, DEVNET_FORGE_URL, DEVNET_RECORD_V2, DEVNET_REPO_USER, DEVNET_SEATS_WORK
The role keys come from OpenBao (bao login -no-print -method=oidc role=admin), read once at the start.

What it changes on the shared devnet, and what it leaves: every issue it opens is closed and every branch it pushes is
deleted at the end, pass or fail. Its bounties stay on the chain (Open, Merged or Paid), as on-chain records do. Scenario
1 settles by warping the shared chain's clock (--no-warp stops at Merged), and scenarios 1, 3 and 5 merge a fix: main
moves to it, and the head on-chain with it, as with any merged bounty. Scenario 1's issue is closed by the bot when it
settles the bounty (`pofctl bot settle --repo --issue`, #151), with a comment linking the payout transaction; the
leaderboard (`pofctl leaderboard --bounties`, from the events) is checked over the run's own bounties against the same
bounties read from the views: on a shared devnet, those are the run's deltas. Each fix writes the same two root files
(integration_probe.py and its test), so main keeps no file per run."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for p in (ROOT, ROOT / "scripts", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from bot.forgejo import Forgejo  # noqa: E402
from first_bounty import Forge  # noqa: E402  (scripts/first_bounty.py: the forge's writes, git with the token in a header)
from oracle import abi, v2  # noqa: E402
from oracle.crypto import address, keccak256  # noqa: E402
from pofctl import keys  # noqa: E402
from pofctl.cli import run as pofctl_run  # noqa: E402
from pofctl.race import C, Race, load_record  # noqa: E402
from pofctl.rpc import Reverted, Rpc, RpcError, auth_headers  # noqa: E402
from targets import (NOT_COVERED, SECRET_VARS, Refused, RedactingStream, Secrets, aws_settings,  # noqa: E402
                     board_expected, check_board, check_books, check_chain, check_withdrawal, expect_deltas, plan)

SEAT_ROLES = [f"oracle-{i}" for i in range(5)] + ["joiner-0"]
PARTIES = ["reporter", "funder", "solver-a", "solver-b"]
ROLES = ["deployer", "bot"] + PARTIES + SEAT_ROLES  # the role keys this run reads from OpenBao
OWNER_SEAT = 6
MARK = "[integration "  # in every issue title this suite opens
BRANCH = "integration-"  # every branch it pushes starts so
MIN_GAS = 10**17  # 0.1 ETH: what first-bounty.sh asks of each sender
MIN_COINS = 1000 * C
CODE = ("race", "verdicts", "meter", "pool", "quoter", "heads", "annex")
PROBE = '''"""Integration run {tag}'s probe (proof-of-fix#152): the value its issue asks for."""

VALUE = "{value}"


def probe():
    return VALUE
'''
PROBE_TEST = '''"""The acceptance test of integration run {tag}'s issue (proof-of-fix#152): probe() returns {want!r}."""

import unittest

from integration_probe import probe


class TestIntegrationProbe(unittest.TestCase):
    def test_probe(self):
        self.assertEqual(probe(), {want!r})


if __name__ == "__main__":
    unittest.main()
'''


def say(line: str = "") -> None:
    print(line, flush=True)


def bogota_hour() -> int:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Bogota")).hour
    except Exception:  # noqa: BLE001 (no tz database: Bogota is UTC-5 all year)
        return datetime.now(timezone(timedelta(hours=-5))).hour


class AwsRun:
    def __init__(self, a, s) -> None:
        self.a, self.s = a, s
        self.secrets = Secrets()
        for label, value in s.secrets().items():
            self.secrets.add(label, value, user=s.user if label == "the repository token" else
                             (s.read_user if label == "the read-only token" else ""))
        self.problems: list = []
        self.passed: list = []
        self.subs: dict = {}  # id -> {"solver", "deposit", "judges", "bounty", "label", "pr", "sha", "scenario"}
        self.bounties: list = []  # (scenario, bounty, forge issue)
        self.late: dict = {}  # solver's address -> fixes sealed after the win (TooLate), for the leaderboard
        self.created = {"issues": [], "pulls": [], "branches": []}
        self.tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M") + "-" + secrets.token_hex(2)
        self.work = Path(tempfile.mkdtemp(prefix="pof-integration-aws-"))
        self.sampler_stop = threading.Event()
        self.sampler_hits: set = set()

    # ---------- the secrets: out of the environment, into this process's memory ----------

    def take_secrets(self) -> None:
        for name in SECRET_VARS:
            os.environ.pop(name, None)
        for k in list(os.environ):
            if k.startswith("POFCTL_KEY_"):
                os.environ.pop(k)
        self.rpc = Rpc(self.s.rpc_url, auth_headers(self.s.auth, "Basic"), retries=3)

    def check_chain(self) -> None:
        """Rule 1, before any key is read or anything is sent."""
        self.record = load_record(2, self.s.record)
        try:
            cid = self.rpc.chain_id()
        except RpcError as e:
            raise Refused(f"no answer from the devnet: {e}. Is the host up (it stops 01:00-09:00 Bogota)?") from None
        check_chain(cid, self.record)
        self.race = Race(self.rpc, self.record)
        self.chain = v2.Chain(self.rpc, self.record["race"])

    def read_keys(self) -> list:
        """Each role's key, once: from OpenBao (or anvil's public keys on a throwaway rig). Returns what's missing."""
        src = "insecure-local" if self.s.insecure_local else "openbao"
        self.keys: dict = {}
        missing = []
        for role in ROLES:
            try:
                self.keys[role] = keys.key(role, src)
            except keys.KeyError_ as e:
                missing.append(f"{role}: {e}")
                continue
            self.secrets.add_key(f"{role}'s key", self.keys[role])
        if self.s.engineer_key:
            self.keys["engineer"] = int(self.s.engineer_key, 16)
            self.secrets.add_key("seat 6's key", self.keys["engineer"])
        # pofctl reads each key by name from this process's environment (keys.py's "env" source): nothing else is
        # started with it. Git gets an environment of its own (Forge.git); no other child process is started.
        for role, k in self.keys.items():
            os.environ[keys.env_name(role)] = f"0x{k:064x}"
        os.environ.update({"DEVNET_KEYS": "env", "POFCTL_RPC": self.s.rpc_url, "POFCTL_RPC_TOKEN": self.s.auth,
                           "POFCTL_RPC_AUTH": "Basic", "FORGEJO_TOKEN": self.s.token, "FORGEJO_USER": self.s.user,
                           "PYTHONDONTWRITEBYTECODE": "1"})
        self.addr = {role: address(k) for role, k in self.keys.items()}
        self.names = {a.lower(): r for r, a in self.addr.items()}
        return missing

    def setup_forge(self) -> None:
        self.forge = Forge(self.s.repo, self.s.forge, self.s.user, self.s.token)
        self.cfg = self.work / "pofctl.json"
        self.cfg.write_text(json.dumps({"repos": {self.s.repo: {"host": "forgejo", "api": self.s.forge}}}),
                            encoding="utf-8")

    def ctl(self, *argv, role=None) -> dict:
        return pofctl_run(["--record", self.s.record, "--config", str(self.cfg)] + (["--as", role] if role else [])
                          + list(argv))[0]

    # ---------- reads ----------

    def seats(self) -> list:
        out = self.race.seats()
        for i, st in enumerate(out):
            role = self.names.get(st["key"].lower())
            st["name"] = role if role in SEAT_ROLES else f"seat {i}" + (" (the owner's)" if i == OWNER_SEAT else "")
            if i == OWNER_SEAT:
                self.names.setdefault(st["key"].lower(), st["name"])
        return out

    def wallets(self, who: dict) -> dict:
        return {n: self.race.coin_balance(a) for n, a in who.items()}

    def credits(self, who: dict) -> dict:
        return {n: self.race.owed(a) for n, a in who.items()}

    def owed_at(self, block: int, who: str) -> int:
        raw = self.rpc.call("eth_call", [{"to": self.chain.race, "data": "0x" + abi.call_data(
            "owed(address,address)", who, self.chain.coin()).hex()}, hex(block)])
        return abi.decode(["uint256"], abi.hexdata(raw))[0]

    def head_on_chain(self) -> bytes:
        return v2.b32(self.rpc.view(self.record["heads"], "head(bytes32)",
                                    ["(bytes32,bytes32,uint256,uint256,uint256,bytes32)"], v2.b32(self.record["repo"]))[0][0])

    def relay_race(self) -> str:
        req = urllib.request.Request(self.s.exchange_url.rstrip("/") + "/healthz", headers=auth_headers(self.s.auth, "Basic"))
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (the configured relay)
            return json.loads(r.read())["race"]

    # ---------- the preflight: reads only ----------

    def preflight(self, key_problems: list) -> list:
        rows: list = []
        ok = lambda t: rows.append(("ok", t))  # noqa: E731
        missing = lambda t: rows.append(("missing", t))  # noqa: E731
        note = lambda t: rows.append(("note", t))  # noqa: E731
        ok(f"{self.s.rpc_url} answers chain {self.race.chain_id()}, block {self.rpc.block()}; the credential works")

        bad = []
        for name in CODE:
            code = abi.hexdata(self.rpc.call("eth_getCode", [self.record[name], "latest"]))
            want = self.record.get(name + "Codehash")
            if not code or (want and "0x" + keccak256(code).hex() != want.lower()):
                bad.append(name)
        coin = abi.hexdata(self.rpc.call("eth_getCode", [self.record["coin"], "latest"]))
        if bad or not coin:
            missing(f"the record {self.s.record} doesn't match this chain ({', '.join(bad or ['coin'])}): is it the "
                    f"devnet it was deployed on?")
        else:
            ok(f"the record {self.s.record}: every contract is on the chain with its recorded code hash")

        try:
            served = self.relay_race()
            if served.lower() == self.record["race"].lower():
                ok(f"the relay at {self.s.exchange_url} serves this race")
            else:
                missing(f"the relay at {self.s.exchange_url} serves race {served}, not {self.record['race']}")
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            missing(f"no answer from the relay at {self.s.exchange_url}: {type(e).__name__}")

        if key_problems:
            for p in key_problems:
                missing(f"a role key: {p}")
        else:
            ok(f"{len(ROLES)} role keys read from {'anvil' if self.s.insecure_local else 'OpenBao'} (addresses only "
               f"below)" + (", and seat 6's key" if self.s.engineer_key else ""))

        seats = self.seats()
        inactive = [st["name"] for st in seats if not st["active"]]
        if len(seats) != 7 or inactive:
            missing(f"{len(seats)} seats, inactive: {', '.join(inactive) or 'none'} (expected 7, all active)")
        else:
            ok("7 seats, all active (scenario 6's joined seat included)")
        for i, st in enumerate(seats):
            role = self.names.get(st["key"].lower())
            if i < OWNER_SEAT and role not in SEAT_ROLES:
                missing(f"seat {i}'s key {st['key']} isn't one of the role seats' keys from OpenBao")
            if st.get("pending"):
                note(f"seat {i} has a key rotation pending to {st['pending']['key']}")
        owner = seats[OWNER_SEAT]["key"] if len(seats) > OWNER_SEAT else ""
        if owner and self.names.get(owner.lower()) in SEAT_ROLES:
            missing(f"seat {OWNER_SEAT} is the role {self.names[owner.lower()]}, not the owner's validator")
        if self.s.engineer_key:
            if owner.lower() == self.addr["engineer"].lower():
                ok(f"POFCTL_KEY_ENGINEER is seat {OWNER_SEAT}'s key ({owner})")
            else:
                missing(f"POFCTL_KEY_ENGINEER's address {self.addr['engineer']} isn't seat {OWNER_SEAT}'s key {owner}")
        if owner:
            credit = self.race.owed(owner)
            if self.s.engineer_key:
                note(f"seat {OWNER_SEAT} has {credit / C:,.6f} to withdraw: the run withdraws it at the end (#150)")
            elif credit:
                note(f"seat {OWNER_SEAT} has {credit / C:,.6f} to withdraw (#150): set POFCTL_KEY_ENGINEER (the runbook's "
                     f"\"The AWS devnet\") and the run withdraws it, or run --withdraw-only with it")

        work = Path(self.a.seats_work)
        pid = None
        try:
            pid = int((work / "up.pid").read_text().strip())
            os.kill(pid, 0)
        except (OSError, ValueError):
            pid = None
        if pid:
            stale = [r for r in SEAT_ROLES if not (work / r / "node.log").exists()]
            ok(f"the role seats' nodes are up on this machine (scripts/devnet-seats.sh, pid {pid})"
               + (f"; no log yet for {', '.join(stale)}" if stale else ""))
        elif self.a.seats_elsewhere:
            note("the role seats' nodes aren't up on this machine: you said they run elsewhere (--seats-elsewhere)")
        else:
            missing("the role seats' nodes aren't up on this machine: run scripts/devnet-seats.sh up in another terminal "
                    "(or --seats-elsewhere if they run on another machine)")
        if (os.environ.get("DEVNET_SEATS_JUDGE") or "fake") != "fake":
            missing("DEVNET_SEATS_JUDGE isn't fake: this suite is for the fake judge (no model calls)")
        note("the judge: the role seats run the fake judge (devnet-seats.sh's default). For no model call at all, seat 6's "
             "kit needs model_id = \"\" (the fake judge) or enabled = false (then a round that draws it waits the seal "
             "window, 15 minutes, and the two others decide)")

        low = []
        for role, a in self.addr.items():
            if int(self.rpc.call("eth_getBalance", [a, "latest"]), 16) < MIN_GAS:
                low.append(f"{role} ({a})")
        if low:
            missing(f"under 0.1 ETH for gas: {', '.join(low)}. scripts/devnet.sh fund (remote mode) funds the roles, "
                    f"fund-address <address> the others")
        else:
            ok(f"every sender has at least 0.1 ETH for gas ({len(self.addr)} accounts)")
        coins = {r: self.race.coin_balance(self.addr[r]) for r in PARTIES if r in self.addr}
        short = [r for r, b in coins.items() if b < MIN_COINS]
        note("test coins: " + ", ".join(f"{r} {b / C:,.2f}" for r, b in coins.items())
             + (f"; the run mints 100,000 to {', '.join(short)} (free, devnet only)" if short else ""))

        try:
            info = self.forge.api("GET", "")
            perms = info.get("permissions") or {}
            if perms.get("push"):
                ok(f"{self.s.repo}: the write token's user {self.s.user} can push"
                   + (" (private repository)" if info.get("private") else " (NOT private: rule 1 wants it private)"))
            else:
                missing(f"{self.s.repo}: {self.s.user} can't push with this token (needs Write on the repository, and "
                        f"the scopes write:repository and write:issue)")
            branch = self.forge.api("GET", "/branches/main")
            if branch.get("protected") and not branch.get("user_can_merge"):
                missing(f"{self.s.repo}'s main is protected and {self.s.user} can't merge to it")
            main = branch["commit"]["id"]
            if self.head_on_chain() == v2.commit_word(main):
                ok(f"{self.s.repo}'s main is at {main[:12]}, the head on-chain")
            else:
                missing(f"{self.s.repo}'s main is at {main[:12]}, not the head on-chain: a merge would be refused as stale. "
                        f"Bring main back to the head on-chain")
            left = self.leftovers()
            if any(left.values()):
                note(f"an earlier run left {len(left['issues'])} open issue(s), {len(left['pulls'])} open pull request(s) "
                     f"and {len(left['branches'])} branch(es): --cleanup closes and deletes them")
        except urllib.error.HTTPError as e:
            missing(f"{self.s.repo}: the forge answered HTTP {e.code} to the write token (its user, scopes and access)")
        except (urllib.error.URLError, OSError) as e:
            missing(f"{self.s.forge}: no answer ({type(e).__name__})")
        if self.s.read_token:
            try:
                reader = Forgejo(self.s.forge, self.s.read_user, "", self.s.read_token)
                perms = reader.api("GET", f"/repos/{self.s.repo}").get("permissions") or {}
                if perms.get("push"):
                    missing(f"the seats' token can write to {self.s.repo}: it should be read-only")
                else:
                    ok(f"the seats' token reads {self.s.repo} and can't write")
            except urllib.error.HTTPError as e:
                missing(f"the seats' token: HTTP {e.code} reading {self.s.repo}")
        else:
            note("DEVNET_REPO_TOKEN not set: the seats' read-only token isn't checked here (devnet-seats.sh checks it)")

        hour = bogota_hour()
        if 9 <= hour < 23:
            ok(f"{hour}h in Bogota: inside the devnet's day (it stops 01:00-09:00)")
        elif self.a.anytime:
            note(f"{hour}h in Bogota: near or in the night stop (--anytime)")
        else:
            missing(f"it's {hour}h in Bogota: the devnet stops 01:00-09:00. Run between 09:00 and 23:00 (--anytime "
                    f"overrides)")
        for role, a in sorted(self.addr.items()):
            note(f"  {role:<9} {a}")
        return rows

    # ---------- the repository: what this run creates, and its cleanup ----------

    def leftovers(self) -> dict:
        issues = [i["number"] for i in self.forge.api("GET", "/issues?state=open&type=issues&limit=50") or []
                  if i.get("title", "").startswith(MARK)]
        pulls = [p["number"] for p in self.forge.api("GET", "/pulls?state=open&limit=50") or []
                 if ((p.get("head") or {}).get("ref") or "").startswith(BRANCH)]
        branches, page = [], 1
        while True:
            got = self.forge.api("GET", f"/branches?limit=50&page={page}") or []
            branches += [b["name"] for b in got if b["name"].startswith(BRANCH)]
            if len(got) < 50:
                break
            page += 1
        return {"issues": issues, "pulls": pulls, "branches": branches}

    def clean(self, what: dict) -> list:
        """Close the issues and pull requests, delete the branches. Returns what couldn't be done."""
        failed = []
        for kind, path, body in (("pulls", "/pulls/{}", {"state": "closed"}), ("issues", "/issues/{}", {"state": "closed"})):
            for n in what.get(kind, []):
                try:
                    if self.forge.api("GET", path.format(n)).get("state") != "closed":
                        self.forge.api("PATCH", path.format(n), body)
                except (urllib.error.URLError, OSError) as e:
                    failed.append(f"{kind[:-1]} #{n}: {type(e).__name__}")
        for b in what.get("branches", []):
            try:
                self.forge.api("DELETE", f"/branches/{b}")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    failed.append(f"branch {b}: HTTP {e.code}")
            except (urllib.error.URLError, OSError) as e:
                failed.append(f"branch {b}: {type(e).__name__}")
        return failed

    def clone(self) -> str:
        """main as it is now, in the work clone: its sha."""
        g, d = self.forge.git, self.work / "clone"
        if not d.exists():
            d.mkdir()
            g(d, "init", "-q")
        g(d, "fetch", "-q", "--depth", "1", "--", f"{self.s.forge.rstrip('/')}/{self.s.repo}.git", "main")
        g(d, "checkout", "-q", "--detach", "FETCH_HEAD")
        self.base = g(d, "rev-parse", "HEAD")
        return self.base

    def fix(self, label: str, passing: bool) -> tuple:
        """A commit on main that sets probe() and adds its test, on its own branch: (sha, branch)."""
        self.clone()
        d, want = self.work / "clone", f"{self.tag}/{label}"
        (d / "integration_probe.py").write_text(PROBE.format(tag=self.tag, value=want if passing else want + "-wrong"),
                                                encoding="utf-8")
        (d / "test_integration_probe.py").write_text(PROBE_TEST.format(tag=self.tag, want=want), encoding="utf-8")
        g = self.forge.git
        g(d, "add", "-A")
        g(d, "commit", "-q", "-m", f"integration probe {want} ({'passing' if passing else 'failing'} fix)")
        sha, branch = g(d, "rev-parse", "HEAD"), f"{BRANCH}{self.tag}-{label}"
        self.created["branches"].append(branch)
        g(d, "push", "-q", f"{self.s.forge.rstrip('/')}/{self.s.repo}.git", f"HEAD:refs/heads/{branch}")
        return sha, branch

    # ---------- the steps, each with its deltas ----------

    def mint(self) -> None:
        who = {r: self.addr[r] for r in PARTIES}
        for role, bal in self.wallets(who).items():
            if bal < MIN_COINS:
                before = self.wallets({role: who[role]})
                self.ctl("coin", "mint", "--to", role, "--amount", "100000")
                self.problems += expect_deltas(f"minting to {role}", before, self.wallets({role: who[role]}),
                                               {role: 100000 * C})
                say(f"  minted 100,000 test coins to {role}")

    def new_bounty(self, scenario: str, label: str, amount: int = 100) -> tuple:
        want = f"{self.tag}/{label}"
        cfg = self.race.config()
        rep_before = self.wallets({"reporter": self.addr["reporter"]})
        rep = self.ctl("reporter", "register", "--repo", "registry")
        self.problems += expect_deltas(f"scenario {scenario}: registering", rep_before,
                                       self.wallets({"reporter": self.addr["reporter"]}),
                                       {"reporter": -(cfg["registrationFee"] + cfg["issueStake"])})
        body = (f"Integration run `{self.tag}`, scenario {scenario} (proof-of-fix#152). `integration_probe.probe()` should "
                f"return `{want!r}`; the acceptance test is `test_integration_probe.py` at the root.\n\n"
                f"This issue is closed when the run ends.\n\nReporter wallet: {rep['reporter']}\n")
        issue = self.forge.api("POST", "/issues", {"title": f"{MARK}{self.tag}] scenario {scenario}: probe() should return "
                                                            f"{want!r}", "labels": [self.forge.bounty_label()],
                                                   "body": body})["number"]
        self.created["issues"].append(issue)
        bounty = self.ctl("oracle", "accept", "--issue", str(rep["issue"]))["bounty"]
        self.ctl("bot", "link", "--repo", self.s.repo, "--issue", str(issue), "--bounty", str(bounty))
        before = self.wallets({"funder": self.addr["funder"]})
        self.ctl("funder", "fund", "--bounty", str(bounty), "--amount", str(amount))
        self.problems += expect_deltas(f"scenario {scenario}: funding bounty {bounty}", before,
                                       self.wallets({"funder": self.addr["funder"]}), {"funder": -amount * C})
        self.bounties.append((scenario, bounty, issue))
        say(f"  issue #{issue} on {self.s.repo}, on-chain issue {rep['issue']}: bounty {bounty} registered, accepted, "
            f"linked and funded with {amount}")
        return bounty, issue

    def submit(self, scenario: str, bounty: int, issue: int, solver: str, label: str, passing: bool) -> int:
        sha, branch = self.fix(label, passing)
        before = self.wallets({solver: self.addr[solver]})
        r = self.ctl("solver", "submit", "--bounty", str(bounty), "--commit", sha, "--issue", str(issue), role=solver)
        self.problems += expect_deltas(f"scenario {scenario}: {solver}'s check deposit", before,
                                       self.wallets({solver: self.addr[solver]}), {solver: -r["deposit"]})
        pr = self.forge.api("POST", "/pulls", {"head": branch, "base": "main", "body": r["prBody"],
                                               "title": f"{MARK}{self.tag}] {label}: "
                                                        f"{'set' if passing else 'a wrong'} probe()"})["number"]
        self.created["pulls"].append(pr)
        s = r["submission"]
        self.subs[s] = {"solver": self.addr[solver], "deposit": r["deposit"], "judges": r["judges"], "bounty": bounty,
                        "label": label, "pr": pr, "sha": sha, "scenario": scenario}
        names = ", ".join(self.names.get(j.lower(), j[:10]) for j in r["judges"])
        say(f"  {solver} sealed a {'passing' if passing else 'failing'} fix ({sha[:12]}): submission {s}, deposit "
            f"{r['deposit'] / C:,.6f}, drawn {names}; pull request #{pr}")
        return s

    def wait(self, what: str, done) -> bool:
        started = time.monotonic()
        while time.monotonic() - started < self.a.check_timeout:
            try:
                finished = done()
            except RpcError as e:  # the chain didn't answer this once: ask again
                say(f"  ({type(e).__name__} while waiting: {e})")
                finished = False
            if finished:
                say(f"  {what}: after {time.monotonic() - started:.0f} s")
                return True
            time.sleep(3)
        return False

    def decided(self, scenario: str, s: int) -> str:
        if not self.wait(f"submission {s} decided by the live nodes",
                         lambda: self.race.submission(s)["outcome"] != "None"):
            self.problems.append(f"scenario {scenario}: submission {s} had no result after {self.a.check_timeout:.0f} s: "
                                 f"are the seats up (scripts/devnet-seats.sh status)?")
            return "None"
        return self.race.submission(s)["outcome"]

    def merge(self, scenario: str, bounty: int, s: int) -> bool:
        sub = self.subs[s]
        style = self.forge.merge(sub["pr"])
        say(f"  pull request #{sub['pr']} merged ({style}); waiting for the drawn judges' signed merge")
        if not self.wait(f"bounty {bounty}'s merge signed on-chain", lambda: self.race.bounty(bounty)["state"] != "Won"):
            self.problems.append(f"scenario {scenario}: bounty {bounty}'s merge wasn't relayed in "
                                 f"{self.a.check_timeout:.0f} s")
            return False
        state = self.race.bounty(bounty)["state"]
        if state != "Merged":
            self.problems.append(f"scenario {scenario}: bounty {bounty} is {state} after its merge, not Merged")
            return False
        if self.forge.main_sha() != sub["sha"]:
            self.problems.append(f"scenario {scenario}: main isn't the fix's commit after the merge")
        if self.head_on_chain() != v2.commit_word(sub["sha"]):
            self.problems.append(f"scenario {scenario}: the head on-chain didn't move to the fix")
        else:
            say(f"  the head on-chain moved to {sub['sha'][:12]}, and main is there too")
        return True

    def close_pr(self, s: int) -> None:
        self.forge.api("PATCH", f"/pulls/{self.subs[s]['pr']}", {"state": "closed"})

    # ---------- the scenarios ----------

    def s2_failing(self) -> None:
        say("\n== 2. a failing fix ==")
        bounty, issue = self.new_bounty("2", "failing")
        s = self.submit("2", bounty, issue, "solver-a", "s2-wrong", passing=False)
        outcome = self.decided("2", s)
        self.close_pr(s)
        if outcome != "Fail":
            return self.problems.append(f"scenario 2: submission {s} is {outcome}, not Fail")
        if self.race.bounty(bounty)["state"] != "Open":
            return self.problems.append(f"scenario 2: bounty {bounty} is {self.race.bounty(bounty)['state']}, not Open")
        say(f"  submission {s}: Fail; bounty {bounty} stays Open (its deposit is checked in the books)")
        self.passed.append("2")

    def s3_race(self) -> None:
        say("\n== 3. a race: two passing fixes ==")
        bounty, issue = self.new_bounty("3", "race")
        first = self.submit("3", bounty, issue, "solver-a", "s3-first", passing=True)
        second = self.submit("3", bounty, issue, "solver-b", "s3-second", passing=True)
        for s in (first, second):
            self.decided("3", s)
        b = self.race.bounty(bounty)
        if b["state"] != "Won" or b["winner"] != first:
            return self.problems.append(f"scenario 3: bounty {bounty} is {b['state']}, winner {b['winner']}, not Won by the "
                                        f"earliest commitment {first}")
        self.close_pr(second)
        say(f"  the earliest commitment ({first}) won; submission {second}: {self.race.submission(second)['outcome']} "
            f"(its deposit is checked in the books)")
        before_block = self.rpc.block()
        fee = self.race.config()["evaluationFee"]
        sha, branch = self.fix("s3-late", passing=True)
        before = self.wallets({"solver-b": self.addr["solver-b"]})
        try:  # a commit after the win isn't a submission: pofctl may fail reading one back, which is the point
            self.ctl("solver", "submit", "--bounty", str(bounty), "--commit", sha, "--issue", str(issue), role="solver-b")
        except Exception as e:  # noqa: BLE001
            say(f"  (pofctl on the late fix: {type(e).__name__})")
        self.problems += expect_deltas("scenario 3: the late fix's evaluation fee", before,
                                       self.wallets({"solver-b": self.addr["solver-b"]}), {"solver-b": -fee})
        late = self.rpc.logs(self.chain.race, before_block + 1, ["0x" + v2.keccak256(b"TooLate(uint256,address)").hex(),
                                                                 "0x" + bounty.to_bytes(32, "big").hex()])
        if len(late) != 1:
            return self.problems.append(f"scenario 3: a fix sealed after the win: {len(late)} TooLate events, not 1")
        self.late[self.addr["solver-b"]] = self.late.get(self.addr["solver-b"], 0) + 1
        say(f"  a fix sealed after the win isn't checked: TooLate, and it paid the evaluation fee {fee / C:,.6f}")
        if self.merge("3", bounty, first):
            self.passed.append("3")

    def s1_happy(self) -> None:
        say("\n== 1. the happy path ==")
        bounty, issue = self.new_bounty("1", "happy")
        self.ctl("solver", "quote", "--bounty", str(bounty), role="solver-a")
        s = self.submit("1", bounty, issue, "solver-a", "s1-right", passing=True)
        outcome = self.decided("1", s)
        if outcome != "Pass" or self.race.bounty(bounty)["state"] != "Won":
            return self.problems.append(f"scenario 1: submission {s} is {outcome}, bounty {bounty} "
                                        f"{self.race.bounty(bounty)['state']}, not Pass and Won")
        if not self.merge("1", bounty, s):
            return
        if self.a.no_warp:
            say("  --no-warp: stopping at Merged (settling needs the shared clock warped)")
        else:
            solver = {"solver-a": self.addr["solver-a"]}
            paid_before = self.credits(solver)
            days = 0
            for days in range(1, self.a.max_warp_days + 1):
                self.ctl("devnet", "warp", "--days", "1")
                try:  # the bot settles, and closes the issue once the bounty is paid (#151)
                    if self.ctl("bot", "settle", "--bounty", str(bounty), "--repo", self.s.repo, "--issue",
                                str(issue))["settled"]:
                        break
                except Reverted as e:
                    if e.reason != "NotYet()":
                        raise
            else:
                return self.problems.append(f"scenario 1: bounty {bounty} didn't settle in {self.a.max_warp_days} days")
            gained = self.credits(solver)["solver-a"] - paid_before["solver-a"]
            say(f"  bounty {bounty}: {self.race.bounty(bounty)['state']} after warping the shared clock {days} day(s); the "
                f"winner was credited {gained / C:,.6f}")
            if self.race.bounty(bounty)["state"] != "Paid" or gained <= 0:
                return self.problems.append(f"scenario 1: bounty {bounty} is {self.race.bounty(bounty)['state']}, the "
                                            f"winner credited {gained}")
            funder = {"funder": self.addr["funder"]}
            before = self.credits(funder)
            self.ctl("funder", "claim", "--bounty", str(bounty))
            got = self.credits(funder)["funder"] - before["funder"]
            if not 0 < got <= 100 * C:
                return self.problems.append(f"scenario 1: the funder's leftover credited {got}, not within (0, 100]")
            say(f"  the funder claimed the leftover: {got / C:,.6f} credited")
            if not self.closed_on_payout(bounty, issue):
                return
        self.passed.append("1")

    def closed_on_payout(self, bounty: int, issue: int) -> bool:
        """The bot's settle closed the issue on the forge, with one comment naming the payout transaction (#151)."""
        from bot import logic

        pay = self.race.payout(bounty)
        state = self.forge.api("GET", f"/issues/{issue}")["state"]
        said = [logic.paid([c]) for c in self.forge.api("GET", f"/issues/{issue}/comments") or [] if logic.paid([c])]
        if state != "closed" or pay is None:
            self.problems.append(f"scenario 1: issue #{issue} is {state} after bounty {bounty} was paid ({pay})")
            return False
        if [x[1:] for x in said] != [(bounty, pay["tx"])]:
            self.problems.append(f"scenario 1: issue #{issue}'s payout comments {said}, expected one naming {pay['tx']}")
            return False
        say(f"  issue #{issue} closed by the bot on payout, its comment linking transaction {pay['tx'][:18]}…")
        return True

    def s5_challenge(self) -> None:
        say("\n== 5. a challenge upheld after the merge ==")
        bounty, issue = self.new_bounty("5", "challenge")
        s = self.submit("5", bounty, issue, "solver-b", "s5-right", passing=True)
        outcome = self.decided("5", s)
        if outcome != "Pass" or self.race.bounty(bounty)["state"] != "Won":
            return self.problems.append(f"scenario 5: submission {s} is {outcome}, not Pass and Won")
        if not self.merge("5", bounty, s):
            return
        epoch = self.race.bounty(bounty)["epoch"]
        r = self.ctl("oracle", "uphold-challenge", "--bounty", str(bounty))
        if self.race.bounty(bounty)["state"] != "Open":
            return self.problems.append(f"scenario 5: bounty {bounty} is {self.race.bounty(bounty)['state']} after an "
                                        f"upheld challenge, not Open")
        if not r["award"]["closed"] or r["award"]["earned"] != 0:
            return self.problems.append(f"scenario 5: award {epoch}: closed {r['award']['closed']}, earned "
                                        f"{r['award']['earned']}")
        say(f"  award {epoch} closed with nothing earned; bounty {bounty} reopened")
        self.passed.append("5")

    # ---------- the end: withdrawals and the books ----------

    def withdraw(self, seats: list, with_parties: bool = True) -> None:
        say("\n== the fees withdrawn (scenario 1's end; seat 6's is #150's) ==")
        rows = [(st["name"], st["key"], self.names.get(st["key"].lower())) for st in seats]
        if with_parties:
            rows += [(r, self.addr[r], r) for r in PARTIES]
        for name, who, role in rows:
            owed = self.race.owed(who)
            if not owed:
                continue
            if role not in self.keys:
                if who.lower() == seats[OWNER_SEAT]["key"].lower():
                    say(f"  {name} has {owed / C:,.6f} to withdraw (#150): set POFCTL_KEY_ENGINEER (seat 6's key, the "
                        f"runbook's \"The AWS devnet\") and run --withdraw-only")
                else:
                    say(f"  {name} has {owed / C:,.6f} to withdraw; this run holds no key for it")
                continue
            wallet = self.race.coin_balance(who)
            if role == "engineer":
                self.ctl("validator", "withdraw", role="engineer")
            else:
                self.ctl("withdraw", "--role", role)
            self.problems += [f"withdrawing: {p}" for p in check_withdrawal(name, owed, wallet, self.race.owed(who),
                                                                             self.race.coin_balance(who))]
            say(f"  {name} withdrew {owed / C:,.6f}")

    def books(self, seats: list, start_credit: dict) -> None:
        say("\n== the books (deltas at each result's block) ==")
        decided: dict = {}
        for e in self.rpc.logs(self.chain.race, self.start_block,
                               ["0x" + v2.keccak256(b"Decided(uint256,uint8)").hex()]):
            decided.setdefault(int(e["blockNumber"], 16), []).append(int(e["topics"][1], 16))
        charged = self.chain.charged(self.start_block)
        seat_keys = [st["key"] for st in seats]
        try:
            self.problems += [f"books: {p}" for p in check_books(
                self.subs, decided, charged, lambda b, who: self.owed_at(b, who) - self.owed_at(b - 1, who), seat_keys)]
        except RpcError as e:
            self.problems.append(f"books: the chain didn't answer for a past block ({e}): was it restarted mid-run?")
        for s, sub in self.subs.items():
            n, total = charged.get(s, (0, 0))
            reports = self.race.reports(s)
            if s not in {x for ids in decided.values() for x in ids}:
                continue
            if len(reports) != n or n not in (2, 3):
                self.problems.append(f"books: submission {s}: {len(reports)} usage reports, {n} judges charged")
            silent = [self.names.get(j.lower(), j) for j in sub["judges"]
                      if j.lower() not in {r["judge"].lower() for r in reports}]
            say(f"  submission {s} ({sub['label']}): {self.race.submission(s)['outcome']}, charged {total / C:,.6f} for "
                f"{n} judges" + (f"; no report from {', '.join(silent)}" if silent else ""))
        gained = sum(self.race.owed(k) - start_credit[k] for k in seat_keys)
        total = sum(t for _, t in charged.values())
        if gained != total:
            self.problems.append(f"books: the seats' credits grew {gained} during the run, the meter charged {total} "
                                 f"(a withdrawal by a seat during the run, elsewhere, would explain it)")
        owner = seats[OWNER_SEAT]["key"].lower()
        drawn = sum(any(j.lower() == owner for j in sub["judges"]) for sub in self.subs.values())
        say(f"charged by the meter during the run: {total / C:,.6f} for {len(charged)} check(s); the seats' credits grew "
            f"{gained / C:,.6f}; seat 6 (the owner's) was drawn for {drawn} of {len(self.subs)} submission(s)")

    def leaderboard(self) -> None:
        """#151: pofctl leaderboard over the run's own bounties (from the events; on a shared devnet, the run's deltas)
        against the same bounties read from the views. Withdrawals are tied to no bounty: left out of both."""
        say("\n== the leaderboard over this run's bounties (#151) ==")
        ids = [b for _, b, _ in self.bounties]
        if not ids:
            return say("  no bounty opened: nothing to rank")
        board = self.ctl("leaderboard", "--bounties", ",".join(map(str, ids)))
        from pofctl.leaderboard import render

        for line in render(board):
            say("  " + line)
        found = check_board("leaderboard", board, board_expected(self.race, ids, [self.addr["funder"]], self.late))
        self.problems += found
        if not found:
            say(f"  the board matches the views for bounties {', '.join(map(str, ids))}")

    # ---------- the leak check (as scripts/devnet-remote-e2e.sh's) ----------

    def sample(self) -> None:
        """Every process's command line, every 2 seconds while the run lasts: no secret may be in one."""
        while not self.sampler_stop.wait(2):
            try:
                out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=10,
                                     env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            self.sampler_hits.update(self.secrets.leaks(out))

    def written(self) -> list:
        """The files this run wrote: its config, the clone's git metadata and the probe files. Not the clone's tree, which
        is the repository's own content (a throwaway rig's repository has anvil's public keys in its tests)."""
        clone = self.work / "clone"
        out = [p for p in self.work.rglob("*") if p.is_file() and clone not in p.parents]
        git = clone / ".git"
        out += [p for p in git.rglob("*") if p.is_file() and "objects" not in p.relative_to(git).parts] if git.is_dir() else []
        return out + [clone / f for f in ("integration_probe.py", "test_integration_probe.py") if (clone / f).is_file()]

    def leak_check(self, streams: list) -> None:
        self.sampler_stop.set()
        where: list = []
        for stream in streams:
            stream.flush()
            if stream.caught:
                where.append(f"the output ({', '.join(sorted(stream.caught))}; redacted there)")
        if self.sampler_hits:
            where.append(f"a process's command line ({', '.join(sorted(self.sampler_hits))})")
        for path in self.written():
            try:
                found = self.secrets.leaks(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if found:
                where.append(f"{path.relative_to(self.work)} in the run's work folder ({', '.join(found)})")
        logs = Path(self.a.seats_work)
        for path in sorted(logs.glob("*/node.log")) if logs.is_dir() else []:
            found = self.secrets.leaks(path.read_text(encoding="utf-8", errors="replace"))
            if found:
                where.append(f"{path} ({', '.join(found)})")
        texts = []
        try:
            for n in self.created["issues"]:
                texts.append(self.forge.api("GET", f"/issues/{n}").get("body") or "")
                texts += [c.get("body") or "" for c in self.forge.api("GET", f"/issues/{n}/comments") or []]
            for n in self.created["pulls"]:
                texts.append(self.forge.api("GET", f"/pulls/{n}").get("body") or "")
        except (urllib.error.URLError, OSError) as e:
            self.problems.append(f"the leak check couldn't read the forge back: {type(e).__name__}")
        found = self.secrets.leaks("\n".join(texts))
        if found:
            where.append(f"an issue, comment or pull request on {self.s.repo} ({', '.join(found)})")
        if where:
            self.problems += [f"leak: a secret in {w}" for w in where]
        else:
            say("leak check: no key, credential or token in the output, any process's command line, the files this run "
                "wrote, the seats' node logs, or the issues, comments and pull requests it wrote")

    # ---------- the run ----------

    def main(self, streams: list) -> int:
        self.take_secrets()
        self.check_chain()
        key_problems = self.read_keys()
        self.setup_forge()
        if self.a.cleanup:
            left = self.leftovers()
            failed = self.clean(left)
            say(f"cleaned up: {len(left['issues'])} issue(s) and {len(left['pulls'])} pull request(s) closed, "
                f"{len(left['branches'])} branch(es) deleted" + (f"; failed: {', '.join(failed)}" if failed else ""))
            return 1 if failed else 0
        rows = self.preflight(key_problems)
        missing = [t for status, t in rows if status == "missing"]
        if self.a.preflight or missing:
            say("== preflight: the AWS devnet, pof-sandbox and the seats (reads only) ==")
            for status, text in rows:
                say(f"{status + ':':<8} {text}")
            if missing:
                say(f"\npreflight: {len(missing)} missing" + ("" if self.a.preflight else "; nothing was sent"))
                return 1
            say("\npreflight: ready")
            return 0
        sampler = threading.Thread(target=self.sample, daemon=True)
        sampler.start()
        seats = self.seats()
        if self.a.withdraw_only:
            self.withdraw(seats, with_parties=False)
            self.leak_check(streams)
            return self.finish([], [])
        run, skipped = plan("aws", self.a.only)
        say(f"integration run {self.tag} on the AWS devnet (chain {self.race.chain_id()}, race {self.record['race']}), "
            f"{self.s.repo}; scenarios {', '.join(run) or 'none'}; the fake judge")
        for s, why in skipped:
            say(f"  skipped on AWS: scenario {s}: {why}")
        self.start_block = self.rpc.block()
        start_credit = {st["key"]: self.race.owed(st["key"]) for st in seats}
        try:
            self.mint()
            for key in run:
                fn = {"1": self.s1_happy, "2": self.s2_failing, "3": self.s3_race, "5": self.s5_challenge}[key]
                try:
                    fn()
                except Exception as e:  # noqa: BLE001 (one scenario's crash shouldn't hide the others)
                    self.problems.append(f"scenario {key}: crashed: {type(e).__name__}: {e}")
            self.books(seats, start_credit)
            self.withdraw(seats)
            try:
                self.leaderboard()
            except Exception as e:  # noqa: BLE001
                self.problems.append(f"leaderboard: crashed: {type(e).__name__}: {e}")
        finally:
            failed = self.clean(self.created)
            say(f"\ncleaned up: {len(self.created['issues'])} issue(s) closed, {len(self.created['pulls'])} pull "
                f"request(s) closed, {len(self.created['branches'])} branch(es) deleted")
            if failed:
                self.problems.append(f"cleanup: {', '.join(failed)} (--cleanup tries again)")
            if self.bounties:
                say("left on the chain, as on-chain records are: " + ", ".join(
                    f"bounty {b} ({self.race.bounty(b)['state']}, scenario {sc})" for sc, b, _ in self.bounties))
        self.leak_check(streams)
        return self.finish(run, skipped)

    def finish(self, run: list, skipped: list) -> int:
        for s, why in skipped:
            say(f"skipped on AWS: scenario {s} (local-only): {why}")
        say("not covered here: " + "; ".join(NOT_COVERED))
        for p in self.problems:
            say(f"FAILED: {p}")
        if run:
            say(f"scenarios passed on AWS: {', '.join(s for s in run if s in self.passed) or 'none'}")
        say("result: the integration suite passed on the AWS devnet" if not self.problems else
            f"result: {len(self.problems)} failed")
        return 1 if self.problems else 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="scripts/integration.sh --target aws",
                                 description="The integration suite against the AWS devnet (#152). See this file's top.")
    ap.add_argument("--preflight", action="store_true", help="the read-only checks, and what's missing")
    ap.add_argument("--only", help="comma-separated scenarios; 4, 6, 7 and 8 are local-only and listed as skipped")
    ap.add_argument("--withdraw-only", action="store_true", help="only every seat's fees withdrawn (seat 6's with its key)")
    ap.add_argument("--cleanup", action="store_true", help="close and delete what an interrupted run left in the repository")
    ap.add_argument("--no-warp", action="store_true", help="scenario 1 stops at Merged: the shared clock stays put")
    ap.add_argument("--max-warp-days", type=int, default=90)
    ap.add_argument("--check-timeout", type=float, default=1500, help="seconds one check or merge may take (default 1500: "
                    "the 900-second seal window, plus the reveals)")
    ap.add_argument("--seats-elsewhere", action="store_true", help="the role seats' nodes run on another machine")
    ap.add_argument("--seats-work", default=os.environ.get("DEVNET_SEATS_WORK") or ".devnet-seats",
                    help="scripts/devnet-seats.sh's working directory (its pid file and node logs)")
    ap.add_argument("--anytime", action="store_true", help="run outside 09:00-23:00 Bogota")
    ap.add_argument("--with-first-run", action="store_true", help=argparse.SUPPRESS)  # the local target's
    return ap


def main(argv: list | None = None) -> int:
    a = parser().parse_args(sys.argv[1:] if argv is None else argv)
    if a.with_first_run:
        print("integration (aws): --with-first-run is the local target's (scripts/first-run-e2e.sh)", file=sys.stderr)
        return 2
    try:
        s = aws_settings(dict(os.environ))
    except Refused as e:
        print(f"integration (aws): {e}", file=sys.stderr)
        return 2
    os.chdir(ROOT)
    r = AwsRun(a, s)
    streams = [RedactingStream(sys.stdout, r.secrets), RedactingStream(sys.stderr, r.secrets)]
    sys.stdout, sys.stderr = streams
    try:
        return r.main(streams)
    except Refused as e:
        print(f"integration (aws): {e}", file=sys.stderr)
        return 2
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            print(f"integration (aws): the forge refused the token (HTTP {e.code} at {e.filename}): check it's complete, "
                  f"its scopes are write:repository and write:issue, and FIRST_BOUNTY_USER is its user", file=sys.stderr)
            return 2
        raise
    finally:
        r.sampler_stop.set()
        for st in streams:
            st.flush()
        sys.stdout, sys.stderr = streams[0].inner, streams[1].inner
        shutil.rmtree(r.work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
