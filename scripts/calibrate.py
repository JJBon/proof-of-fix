#!/usr/bin/env python3
"""The calibration driver (proof-of-fix#334): runs calibration/'s items through a v3 deployment, so the launch's
candidates qualify by their shadow verdicts (calibration/README.md has the counts, calibration/RUNBOOK.md the order of
operations on Sepolia).

    scripts/calibrate.py plan   [--deployment R] [--max-usd X]       the items, the checks and shadow verdicts they
                                                                     make, the estimated model spend, the coins
    scripts/calibrate.py run    --target local|sepolia --deployment R --ledger L [--max-usd X] [--pace-seconds S]
                                [--yes-spend] [--once]               register, open, attempt, submit; resumable
    scripts/calibrate.py status --deployment R --ledger L            the items' progress and each candidate's counters

For each item, in order: its issue is opened on Radicle and registered (`pofctl --v3 issue register --title …
--description … --comment`), which posts its registration check. Once that check is final and passed, the bounty is
opened (`issue open`), pledged to if `--pledge` asks for it (refused below 3 active solvers, as the launch's rule says;
the fix is then unfunded, which the race allows), the attempt recorded (`attempt`), and the item's prepared fix
(calibration/fixes/<id>.py) committed on Heads.head in the solver's working copy, sealed (`submit`) and opened as a
Radicle patch with the command pofctl prints. Up to `--merge` passing fixes are claimed and merged at finality.

The ledger (JSONL, one event a line, appended and flushed) is the driver's only state: `run` reads it back and goes on
from where it stopped, so it can be stopped at any time. Each event names the item, what was done and the ids
(registration, check, bounty, submission, commit), and the checks' outcomes as read from Panels: status, k, the
counted seats, and each scored shadow (`ShadowScored`). Which prepared fix is good or bad is in
scripts/calibrate_items.json only.

The budget: before each check it starts (a registration, a fix), the driver adds that check's estimated model spend:
its model calls (a registration check: 1 counted and SHADOW_PER_DRAW_SMALL shadow seats; a fix: kTop counted and
the same shadows) times one call's cost at FeesV3's token prices (the dearest priced family) and FeesV3's token caps
(or `--tokens IN:OUT`, a typical call). It stops before a check that would take the total over `--max-usd`.

Secrets: the RPC URL (POFCTL_RPC, the pofctl config's `rpc`, or --rpc) and any key are loaded into oracle/redact.py's
Redactor and never printed; pofctl's own output passes through it too. Keys stay in pofctl (keystores on Sepolia,
devnet keys locally). `run --target sepolia` refuses to start without `--yes-spend` and an explicit `--max-usd`."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle import redact  # noqa: E402

ITEMS_JSON = ROOT / "scripts" / "calibrate_items.json"
CAL = ROOT / "calibration"
SHADOW_PER_DRAW_SMALL = 2  # Panels: shadows per draw while fewer than K_MAX validators are active
QUALIFY_VERDICTS = 20  # Validators.QUALIFY_VERDICTS
STATES = ["None", "Candidate", "Active", "Leaving", "Exited", "BelowFloor"]  # IValidators.State
STATUS = ["None", "Sealed", "Waiting", "Judging", "Held", "Window", "Final", "Withdrawn", "Expired", "Released"]
SEALED, WAITING, JUDGING, HELD, WINDOW, FINAL = 1, 2, 3, 4, 5, 6
ENDED = {7, 8, 9}  # withdrawn, expired, released
PROGRESS = "(uint16,uint16,uint16,uint16,uint64,uint64,uint8)"
SHADOW_SCORED = "ShadowScored(uint256,address,bool)"
SEATED = "Seated(uint256,uint256,address,uint256)"


class Stop(Exception):
    """The run stops here (the budget, or a refusal); the ledger keeps what was done."""


# ---------------------------------------------------------------------------------------------------------------------
# The items


@dataclass(frozen=True)
class Item:
    id: str
    function: str
    prepared: str  # "good" or "bad": the driver's data only
    title: str
    body: str
    fix: str  # the prepared fix's module text

    @property
    def path(self) -> str:
        return f"calibration/{self.id}.py"


def load_items(root: Path = ROOT) -> list:
    data = json.loads((root / "scripts" / "calibrate_items.json").read_text(encoding="utf-8"))
    out = []
    for x in data["items"]:
        text = (root / "calibration" / "issues" / f"{x['id']}.md").read_text(encoding="utf-8")
        first, _, body = text.partition("\n")
        out.append(Item(x["id"], x["function"], x["prepared"], first.lstrip("# ").strip(), body.strip(),
                        (root / "calibration" / "fixes" / f"{x['id']}.py").read_text(encoding="utf-8")))
    return out


# ---------------------------------------------------------------------------------------------------------------------
# The ledger


class Ledger:
    """Append-only JSONL. `items()` folds the events into each item's state; a torn last line (a crash mid-write) is
    ignored."""

    def __init__(self, path: Path, clock=time.time) -> None:
        self.path, self.clock = Path(path), clock

    def events(self) -> list:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def add(self, item: str | None, step: str, **data) -> dict:
        ev = {"t": round(self.clock(), 3), "item": item, "step": step, **data}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return ev

    def items(self) -> dict:
        state: dict = {}
        for ev in self.events():
            if ev.get("item"):
                s = state.setdefault(ev["item"], {"errors": 0})
                if ev["step"] == "error":
                    s["errors"] += 1
                else:
                    s.update({k: v for k, v in ev.items() if k not in ("t", "item", "step")})
                    s[ev["step"]] = True
        return state

    def spent(self) -> float:
        return round(sum(ev.get("estUsd", 0.0) for ev in self.events()), 6)


# ---------------------------------------------------------------------------------------------------------------------
# The chain, read (never written: every transaction goes through pofctl)


class ChainReader:
    def __init__(self, rpc_url: str, record: dict, headers: dict | None = None) -> None:
        from oracle import v3
        from oracle.rpc import Rpc

        race = record.get("race") or (record.get("addresses") or {}).get("race")
        self.rpc = Rpc(rpc_url, headers=headers)
        self.chain = v3.Chain(self.rpc, race, first_block=int(record.get("block", 0)))

    def check(self, s: int) -> dict:
        v = self.chain.verdict(s)
        return {"status": v["status"], "pass": bool(v["pass"]), "k": v["k"], "pid": v["pid"],
                "shadowPid": v["shadowPid"], "held": bool(v["heldAtCount"])}

    def head(self) -> str:
        from oracle import radicle

        return radicle.sha_of(self.chain.head())

    def _logs(self, sig: str, pid: int) -> list:
        from oracle.crypto import keccak256

        return self.chain._logs(self.chain.panels, 0, ["0x" + keccak256(sig.encode()).hex(), "0x%064x" % pid])

    def seats(self, pid: int) -> list:
        return ["0x" + log["topics"][2][-40:] for log in self._logs(SEATED, pid)] if pid else []

    def shadow_scores(self, spid: int) -> list:
        return [{"key": "0x" + log["topics"][2][-40:], "agreed": int(log["data"], 16) != 0}
                for log in self._logs(SHADOW_SCORED, spid)] if spid else []

    def validators(self) -> list:
        reg, out = self.chain.registry, []
        n = self.rpc.view(reg, "validatorCount()", ["uint256"])[0]
        for i in range(n):
            key = self.rpc.view(reg, "validatorAt(uint256)", ["address"], i)[0]
            v = self.chain.validator(key)
            draws, reveals, scored, agreed, cooldown, _, _ = self.rpc.view(reg, "progress(address)", [PROGRESS], key)[0]
            out.append({"key": v["key"], "state": STATES[v["state"]], "family": v["family"].hex(),
                        "shadowDraws": draws, "shadowReveals": reveals, "scored": scored, "agreed": agreed,
                        "cooldownUntil": cooldown})
        return out

    def k_top(self) -> int:
        return int(self.chain.panel_rules().get("kTop") or 7)

    def usd_per_call(self, tokens: tuple | None = None) -> float:
        """One model call's cost in USD (FeesV3's units: micro-coins per million tokens, a coin priced as a dollar):
        the dearest priced family's input (or cached, the dearer) and output prices, times FeesV3's token caps or
        `tokens` (input, output)."""
        fees = self.chain.fees
        caps = self.rpc.view(fees, "caps()", ["(uint64,uint64,uint64,uint64,uint64,uint64)"])[0]
        tin, tout = tokens or (caps[0], caps[1])
        worst = 0
        for f in self.rpc.view(fees, "pricedFamilies()", ["bytes32[]"])[0]:
            p = self.rpc.view(fees, "tokenPrices(bytes32)", ["uint256[3]"], f)[0]
            worst = max(worst, tin * max(p[0], p[1]) + tout * p[2])
        return worst / 1e12

    def coins(self) -> dict:
        """What a registration and a fix post, in coins (micro-coins / 1e6)."""
        cfg = self.chain.config()
        dep = self.rpc.view(self.chain.fees, "maxDeposit(bytes32,uint256)", ["uint256"], self.chain.repo(),
                            self.k_top())[0]
        return {"registration": (cfg["registrationFee"] + cfg["issueStake"] + dep) / 1e6, "fixDeposit": dep / 1e6,
                "issueStake": cfg["issueStake"] / 1e6}


# ---------------------------------------------------------------------------------------------------------------------
# Side effects: pofctl and the working copies


class PofctlFailed(RuntimeError):
    pass


class Ops:
    """pofctl as its own process, and shell commands in a role's working copy (through `exec` prefixes such as
    `docker exec -i <container>`, or on this machine). `target` local: devnet keys by role (`--as`, LOCAL_ROLES) and
    `--rpc`; sepolia: each role's pofctl config (keystore, record, rpc) in POFCTL_CONFIG."""

    LOCAL_ROLES = {"reporter": "reporter", "solver": "solver-a", "funder": "funder"}  # pofctl/keys.py's devnet roles

    def __init__(self, target: str, record: Path | None, rpc_url: str | None, repo: str, execs: dict,
                 configs: dict, rid: str | None, redactor: redact.Redactor, timeout: float = 900) -> None:
        self.target, self.record, self.rpc_url, self.repo = target, record, rpc_url, repo
        self.execs, self.configs, self.rid, self.red, self.timeout = execs, configs, rid, redactor, timeout

    def rad_exec(self, role: str) -> str | None:
        return self.execs.get(role) or None

    def pofctl(self, role: str, *argv) -> dict:
        cmd = [sys.executable, "-m", "pofctl", "--json"]
        env = dict(os.environ)
        if self.record:
            cmd += ["--record", str(self.record)]
        if self.target == "local":
            cmd += ["--rpc", self.rpc_url, "--as", self.LOCAL_ROLES[role]]
            env.update(DEVNET_KEYS="insecure-local", POFCTL_CONFIG=str(ROOT / ".calibration" / "no-pofctl.json"))
            env.pop("POFCTL_KEYSTORE", None)
        elif self.configs.get(role):
            env["POFCTL_CONFIG"] = self.configs[role]
        cmd += ["--v3", *[str(a) for a in argv]]
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=self.timeout,
                           stdin=subprocess.DEVNULL)
        if r.returncode:
            raise PofctlFailed(self.red(f"pofctl --v3 {argv[0]}: exit {r.returncode}: "
                                        f"{(r.stderr or r.stdout).strip()[-400:]}"))
        return json.loads(r.stdout)

    def sh(self, role: str, script: str, input: str | None = None, check: bool = True) -> str:
        prefix = shlex.split(self.execs.get(role) or "")
        r = subprocess.run(prefix + ["bash", "-c", script], capture_output=True, text=True, input=input,
                           timeout=self.timeout, stdin=None if input is not None else subprocess.DEVNULL)
        if check and r.returncode:
            raise PofctlFailed(self.red(f"{role}'s working copy: exit {r.returncode}: "
                                        f"{(r.stderr or r.stdout).strip()[-300:]}"))
        return r.stdout.strip()

    def commit_fix(self, item: Item, base: str) -> str:
        """The item's prepared fix as one commit on `base` in the solver's working copy: its sha."""
        repo = shlex.quote(self.repo)
        self.sh("solver", f"cd {repo} && {{ git cat-file -e {base}^{{commit}} 2>/dev/null || "
                          f"{{ rad sync --fetch >/dev/null 2>&1; git fetch -q --all 2>/dev/null; }}; }} && "
                          f"git checkout -q -B calibration-{item.id} {base}")
        self.sh("solver", f"cat > {repo}/{item.path}", input=item.fix)
        msg = shlex.quote(f"calibration {item.id}: fix {item.function}()")
        return self.sh("solver", f"cd {repo} && git add {item.path} && git commit -q -m {msg} && git rev-parse HEAD")

    def open_patch(self, command: str) -> str:
        out = self.sh("solver", f"cd {shlex.quote(self.repo)} && {command} 2>&1")
        m = re.search(r"Patch ([0-9a-f]{40}) opened", out)
        return m.group(1) if m else ""

    def announce(self, role: str) -> None:
        self.sh(role, f"cd {shlex.quote(self.repo)} && rad sync --announce >/dev/null 2>&1", check=False)


# ---------------------------------------------------------------------------------------------------------------------
# The driver


class Driver:
    def __init__(self, items: list, ledger: Ledger, ops, reader, max_usd: float, pace: float = 0.0,
                 tokens: tuple | None = None, batch: int = 5, fixes: bool = True, merge: int = 1,
                 pledge: float = 0.0, say=print, sleep=time.sleep) -> None:
        self.items, self.ledger, self.ops, self.reader = items, ledger, ops, reader
        self.max_usd, self.pace, self.tokens, self.batch = max_usd, pace, tokens, batch
        self.fixes, self.merge, self.pledge, self.say, self.sleep = fixes, merge, pledge, say, sleep
        self._call = None
        self._k = None

    # -- estimates --
    def per_call(self) -> float:
        if self._call is None:
            self._call = self.reader.usd_per_call(self.tokens)
        return self._call

    def k_top(self) -> int:
        if self._k is None:
            self._k = self.reader.k_top()
        return self._k

    def est_registration(self) -> float:
        return round((1 + SHADOW_PER_DRAW_SMALL) * self.per_call(), 6)

    def est_fix(self) -> float:
        return round((self.k_top() + SHADOW_PER_DRAW_SMALL) * self.per_call(), 6)

    def afford(self, est: float, what: str) -> None:
        spent = self.ledger.spent()
        if spent + est > self.max_usd + 1e-9:
            self.ledger.add(None, "stopped", reason="budget", spentUsd=spent, nextUsd=est, maxUsd=self.max_usd)
            raise Stop(f"budget: {what} would take the estimated model spend from ${spent:.2f} to "
                       f"${spent + est:.2f}, over --max-usd ${self.max_usd:.2f}")

    def paced(self) -> None:
        if self.pace:
            self.sleep(self.pace)

    # -- one pass --
    def step(self) -> dict:
        """One pass over the items: at most `batch` new registrations, and every other step that is due. Returns
        {"actions": n, "open": the items not finished}."""
        actions = new = 0
        for item in self.items:
            s = self.ledger.items().get(item.id, {"errors": 0})
            try:
                if not s.get("registered"):
                    if new < self.batch:
                        self.register(item)
                        new += 1
                        actions += 1
                    continue
                if self.follow_check(item, s):
                    actions += 1
                    s = self.ledger.items()[item.id]
                if not self.fixes or s.get("rejected"):
                    continue
                if s.get("checkFinal") and not s.get("opened"):  # a failed check: `issue open` closes it (no bounty)
                    self.open(item, s)
                    actions += 1
                    s = self.ledger.items()[item.id]
                    if s.get("rejected"):
                        continue
                if s.get("opened") and not s.get("submitted"):
                    self.submit(item, s)
                    actions += 1
                    continue
                if s.get("submitted"):
                    actions += self.follow_fix(item, s)
                    s = self.ledger.items()[item.id]
                    claimed = sum(1 for x in self.ledger.items().values() if x.get("claimed"))
                    wants = s.get("claimed") or (claimed < self.merge and s.get("verdictPass")
                                                 and item.prepared == "good")
                    if wants and not s.get("merged") and self.claim_merge(item, s):
                        actions += 1
            except PofctlFailed as e:
                self.ledger.add(item.id, "error", message=str(e)[-400:])
                self.say(f"{item.id}: {e}")
        state = self.ledger.items()
        return {"actions": actions, "open": [i.id for i in self.items if not self.done(state.get(i.id, {}))]}

    def done(self, s: dict) -> bool:
        if not s.get("registered"):
            return False
        if s.get("rejected"):
            return True
        if not self.fixes:
            return bool(s.get("checkFinal"))
        return s.get("verdictStatus") == FINAL and (not s.get("claimed") or bool(s.get("merged")))

    # -- the steps --
    def register(self, item: Item) -> None:
        est = self.est_registration()
        self.afford(est, f"{item.id}'s registration check")
        argv = ["issue", "register", "--title", item.title, "--description", item.body, "--comment"]
        if self.ops.rad_exec("reporter"):
            argv += ["--rad-exec", self.ops.rad_exec("reporter")]
        d = self.ops.pofctl("reporter", *argv)
        self.ledger.add(item.id, "registered", issue=d["issue"], check=d["check"], radIssue=d.get("radIssue", ""),
                        estUsd=est)
        self.say(f"{item.id}: registered as issue {d['issue']}, its check is submission {d['check']} "
                 f"(estimated ${est:.2f})")
        self.ops.announce("reporter")
        self.paced()

    def follow_check(self, item: Item, s: dict) -> int:
        """The registration check's status, recorded when it changes: k, the counted seats, the scored shadows."""
        if s.get("checkFinal"):
            return 0
        c = self.reader.check(s["check"])
        shadows = self.reader.shadow_scores(c["shadowPid"])
        if c["status"] == s.get("checkStatus") and len(shadows) == len(s.get("checkShadows", [])):
            return 0
        final = c["status"] == FINAL
        self.ledger.add(item.id, "checked", checkStatus=c["status"], checkPass=c["pass"], checkK=c["k"],
                        checkHeld=c["held"], checkSeats=self.reader.seats(c["pid"]), checkShadows=shadows,
                        checkFinal=final)
        self.say(f"{item.id}: registration check {s['check']} {STATUS[c['status']].lower()}"
                 + (f", k = {c['k']}, {'pass' if c['pass'] else 'fail'}" if c["status"] >= HELD else "")
                 + (f", {len(shadows)} shadow(s) scored" if shadows else ""))
        if c["status"] in ENDED:
            self.ledger.add(item.id, "rejected", why=STATUS[c["status"]])
        return 1

    def open(self, item: Item, s: dict) -> None:
        d = self.ops.pofctl("reporter", "issue", "open", "--issue", s["issue"])
        if not d.get("bounty"):
            self.ledger.add(item.id, "rejected", why="the registration check failed")
            return
        self.ledger.add(item.id, "opened", bounty=d["bounty"])
        self.say(f"{item.id}: bounty {d['bounty']} open")
        self.paced()
        if self.pledge:
            try:
                self.ops.pofctl("funder", "pledge", "--bounty", d["bounty"], "--amount", self.pledge)
                self.ledger.add(item.id, "pledged", amount=self.pledge)
            except PofctlFailed as e:  # below 3 active solvers the race refuses it before anything is sent (L6)
                self.ledger.add(item.id, "pledgeRefused", why=str(e)[-200:])
            self.paced()

    def submit(self, item: Item, s: dict) -> None:
        est = self.est_fix()
        self.afford(est, f"{item.id}'s fix")
        b = s["bounty"]
        if not s.get("attempted"):
            self.ops.pofctl("solver", "attempt", "--bounty", b)
            self.ledger.add(item.id, "attempted")
            self.paced()
        base = self.reader.head()
        sha = self.ops.commit_fix(item, base)
        d = self.ops.pofctl("solver", "submit", "--bounty", b, "--patch", sha, "--title",
                            f"calibration {item.id}: fix {item.function}()")
        patch = self.ops.open_patch(d["patchCommand"])
        self.ops.announce("solver")
        self.ledger.add(item.id, "submitted", submission=d["submission"], fix=sha, base=base, salt=d["salt"],
                        patch=patch, estUsd=est)
        self.say(f"{item.id}: fix {sha[:12]} sealed as submission {d['submission']} on bounty {b}"
                 + (f", Radicle patch {patch[:7]}" if patch else "") + f" (estimated ${est:.2f})")
        self.paced()

    def follow_fix(self, item: Item, s: dict) -> int:
        if s.get("verdict") and s.get("verdictStatus") == FINAL:
            return 0
        c = self.reader.check(s["submission"])
        if c["status"] < HELD or c["status"] == s.get("verdictStatus"):
            return 0
        shadows = self.reader.shadow_scores(c["shadowPid"])
        expect = item.prepared == "good"
        self.ledger.add(item.id, "verdict", verdictStatus=c["status"], verdictPass=c["pass"], verdictK=c["k"],
                        verdictSeats=self.reader.seats(c["pid"]), verdictShadows=shadows,
                        asPrepared=c["pass"] == expect)
        self.say(f"{item.id}: fix {STATUS[c['status']].lower()}: {'pass' if c['pass'] else 'fail'} at k = {c['k']} "
                 f"({'as expected' if c['pass'] == expect else 'NOT as expected'})")
        return 1

    def claim_merge(self, item: Item, s: dict) -> bool:
        if not s.get("claimed"):
            self.ops.pofctl("solver", "claim", "--bounty", s["bounty"], "--patch", s["fix"], "--base", s["base"],
                            "--salt", s["salt"])
            self.ledger.add(item.id, "claimed")
            self.paced()
            return True
        if s.get("verdictStatus") != FINAL:
            return False
        d = self.ops.pofctl("solver", "merge", "--bounty", s["bounty"])
        self.ledger.add(item.id, "merged", head=d.get("head"))
        self.say(f"{item.id}: merged; Heads.head is {str(d.get('head'))[:12]}")
        return True

    def run(self, once: bool = False, max_passes: int = 0) -> dict:
        passes = 0
        while True:
            r = self.step()
            passes += 1
            if once or not r["open"] or (max_passes and passes >= max_passes):
                return r
            self.sleep(max(self.pace, 30.0))


# ---------------------------------------------------------------------------------------------------------------------
# plan and status


def plan_lines(items: list, est_reg: float | None = None, est_fix: float | None = None, coins: dict | None = None,
               max_usd: float | None = None) -> list:
    good = sum(1 for i in items if i.prepared == "good")
    n = len(items)
    out = [f"{n} calibration items: {good} prepared fixes good, {n - good} bad ({100 * good / n:.0f} % / "
           f"{100 * (n - good) / n:.0f} %)",
           f"checks: {2 * n} ({n} registration checks, then {n} fixes once each registration check is final)",
           f"shadow verdicts while only the genesis validator is active: {SHADOW_PER_DRAW_SMALL} a registration check "
           f"(k = 1, scored against the majority of 3), so {SHADOW_PER_DRAW_SMALL * n} from the registrations alone; "
           f"{QUALIFY_VERDICTS} per candidate qualifies {SHADOW_PER_DRAW_SMALL * n // QUALIFY_VERDICTS} candidates"]
    if est_reg is not None:
        total = n * (est_reg + est_fix)
        out.append(f"estimated model spend: ${est_reg:.2f} a registration check, ${est_fix:.2f} a fix; "
                   f"${n * est_reg:.2f} for the registrations, ${total:.2f} with every fix"
                   + (f" (--max-usd ${max_usd:.2f} stops the run before it would pass)" if max_usd else ""))
    if coins:
        out.append(f"coins: {coins['registration']:.2f} a registration (fee, stake and its check's deposit; the "
                   f"stake and the deposit's unused part come back), {coins['fixDeposit']:.2f} a fix's deposit; "
                   f"{n * coins['registration']:.2f} for every registration")
    return out


def status_lines(items: list, ledger: Ledger, validators: list | None) -> list:
    st = ledger.items()
    count = {k: sum(1 for i in items if st.get(i.id, {}).get(k)) for k in
             ("registered", "checkFinal", "opened", "submitted", "verdict", "merged", "rejected")}
    shadows = sum(len(st.get(i.id, {}).get("checkShadows", [])) for i in items)
    agree = sum(1 for i in items if st.get(i.id, {}).get("asPrepared"))
    out = [f"items: {len(items)}; registered {count['registered']}, registration checks final {count['checkFinal']}, "
           f"bounties open {count['opened']}, fixes submitted {count['submitted']}, judged {count['verdict']} "
           f"({agree} as prepared), merged {count['merged']}, rejected {count['rejected']}",
           f"shadow verdicts scored on the registration checks: {shadows}; estimated model spend so far "
           f"${ledger.spent():.2f}"]
    for v in validators or []:
        rate = f"{100 * v['shadowReveals'] / v['shadowDraws']:.0f} %" if v["shadowDraws"] else "-"
        agreed = f"{100 * v['agreed'] / v['scored']:.0f} %" if v["scored"] else "-"
        out.append(f"  {v['key']}  {v['state']:<10} scored {v['scored']:>3}/{QUALIFY_VERDICTS}  agreed {agreed:>5}  "
                   f"revealed {v['shadowReveals']}/{v['shadowDraws']} ({rate})")
    return out


# ---------------------------------------------------------------------------------------------------------------------
# The command line


def rpc_url(a, redactor: redact.Redactor) -> str | None:
    """The RPC URL, from --rpc, POFCTL_RPC, or the reporter's pofctl config; loaded into the redactor."""
    url = a.rpc or os.environ.get("POFCTL_RPC")
    if not url:
        cfg = a.config_reporter or os.environ.get("POFCTL_CONFIG") or "pofctl.json"
        try:
            url = json.loads(Path(cfg).read_text(encoding="utf-8")).get("rpc")
        except (OSError, ValueError):
            url = None
    if a.target == "local" and not url:
        url = "http://127.0.0.1:8546"
    redactor.add(url)
    for name in ("POFCTL_RPC_TOKEN", *redact.RPC_SECRETS):
        redactor.add(os.environ.get(name))
    return url


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="calibrate.py", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["plan", "run", "status"])
    p.add_argument("--target", choices=["local", "sepolia"], default="local")
    p.add_argument("--deployment", type=Path, help="the deployment record (JSON)")
    p.add_argument("--ledger", type=Path, default=ROOT / ".calibration" / "ledger.jsonl")
    p.add_argument("--max-usd", type=float, help="stop before the estimated model spend would pass this (required on "
                                                 "Sepolia; default 60 locally)")
    p.add_argument("--pace-seconds", type=float, default=0.0, help="wait this long after each transaction")
    p.add_argument("--tokens", help="IN:OUT tokens of a typical model call, for the estimate (default FeesV3's caps)")
    p.add_argument("--yes-spend", action="store_true", help="Sepolia only: this run spends the nodes' model budget")
    p.add_argument("--once", action="store_true", help="one pass, then stop")
    p.add_argument("--batch", type=int, default=5, help="new registrations a pass (default 5)")
    p.add_argument("--items", help="only these ids (comma-separated)")
    p.add_argument("--no-fixes", action="store_true", help="registrations only (qualification needs no more)")
    p.add_argument("--merge", type=int, default=1, help="claim and merge up to this many passing good fixes")
    p.add_argument("--pledge", type=float, default=0.0, help="pledge this many coins to each bounty as `funder`")
    p.add_argument("--rpc", help="the RPC URL (local; on Sepolia POFCTL_RPC or the pofctl config's rpc). Never printed")
    p.add_argument("--rid", help="the repository's RID (default: the record's)")
    p.add_argument("--repo", default=".", help="the solver's working copy of the race's repository")
    for role in ("reporter", "solver"):
        p.add_argument(f"--{role}-exec", help=f"a prefix for {role}'s rad and git (e.g. `docker exec -i <name>`)")
    for role in ("reporter", "solver", "funder"):
        p.add_argument(f"--config-{role}", help=f"Sepolia: {role}'s pofctl config (POFCTL_CONFIG)")
    return p


def main(argv: list | None = None, reader_factory=None, ops_factory=None, out=print) -> int:
    a = parser().parse_args(argv)
    red = redact.Redactor()

    def say(line: str) -> None:
        out(red(line))

    if a.command == "run" and a.target == "sepolia":
        if not a.yes_spend:
            say("refused: `run --target sepolia` spends the validators' model budget and the deployment's test coin; "
                "pass --yes-spend once the caps are raised (calibration/RUNBOOK.md)")
            return 2
        if a.max_usd is None:
            say("refused: `run --target sepolia` needs an explicit --max-usd")
            return 2
    items = load_items()
    if a.items:
        want = set(a.items.split(","))
        items = [i for i in items if i.id in want]
    max_usd = 60.0 if a.max_usd is None else a.max_usd
    tokens = tuple(int(x) for x in a.tokens.split(":")) if a.tokens else None
    record = json.loads(a.deployment.read_text(encoding="utf-8")) if a.deployment else None
    url = rpc_url(a, red)
    reader = None
    if record is not None:
        reader = (reader_factory or (lambda: ChainReader(url, record)))()
    ledger = Ledger(a.ledger)
    if a.command == "plan":
        if reader is None:
            for line in plan_lines(items):
                say(line)
            return 0
        k = reader.k_top()
        call = reader.usd_per_call(tokens)
        est_reg, est_fix = (1 + SHADOW_PER_DRAW_SMALL) * call, (k + SHADOW_PER_DRAW_SMALL) * call
        for line in plan_lines(items, est_reg, est_fix, reader.coins(), max_usd):
            say(line)
        return 0
    if a.command == "status":
        for line in status_lines(items, ledger, reader.validators() if reader else None):
            say(line)
        return 0
    if reader is None:
        say("run needs --deployment")
        return 2
    ops = (ops_factory or (lambda: Ops(a.target, a.deployment, url, a.repo,
                                       {"reporter": a.reporter_exec, "solver": a.solver_exec},
                                       {"reporter": a.config_reporter, "solver": a.config_solver,
                                        "funder": a.config_funder}, a.rid, red)))()
    d = Driver(items, ledger, ops, reader, max_usd, pace=a.pace_seconds, tokens=tokens, batch=a.batch,
               fixes=not a.no_fixes, merge=a.merge, pledge=a.pledge, say=say)
    try:
        r = d.run(once=a.once)
    except Stop as e:
        say(f"stopped: {e}")
        return 3
    say(f"{len(items) - len(r['open'])} of {len(items)} items finished; ledger {a.ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
