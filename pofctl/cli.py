"""pofctl: play every role of proof-of-fix against a devnet (proof-of-fix#104). See pofctl/README.md.

    pofctl [--json] [--config FILE] [--v1] [--as ROLE] <command> ...

Roles and their default keys (devnet-keys.sh's roles; --as picks another, e.g. --as solver-b, or --as engineer with
POFCTL_KEY_ENGINEER set to an engineer's own key):
    funder -> funder, reporter -> reporter, solver -> solver-a, validator -> oracle-0, bot -> bot, oracle -> bot

The chain's API key (#104's chain on AWS): POFCTL_RPC_TOKEN, sent as POFCTL_RPC_AUTH says: "Authorization" (Bearer,
the default), "Basic" (a "<handle>:<key>" token) or another header name; or put it in the URL
(https://<handle>:<key>@host, sent as HTTP Basic). Never in the config file.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import sys
from pathlib import Path

from oracle import v2
from oracle.crypto import recover, sign

from bot import logic
from bot.forge import load_config as load_repos
from bot.forge import repo_for

from . import keys as keysrc
from . import leaderboard
from .race import C, FAIL, PASS, Race, Signers, commitment, fix_of, fmt, load_record
from .rpc import Reverted, Rpc, RpcError, Wallet, auth_headers

DEVNET_CHAINS = (7193, 31337)  # the private devnet and anvil: the only chains the stub quorum and warp touch
DEFAULT_ROLE = {"funder": "funder", "reporter": "reporter", "solver": "solver-a", "validator": "oracle-0",
                "bot": "bot", "oracle": "bot", "coin": "deployer"}
REGISTERED, AT_MERGE = 120 * C, 100 * C  # the stub quorum's two importance estimates (as the loop's)


class Fail(Exception):
    pass


# ---------- context ----------

class Ctx:
    def __init__(self, args) -> None:
        self.args = args
        self.config = self._config(args.config)
        url = args.rpc or os.environ.get("POFCTL_RPC") or self.config.get("rpc") or "http://127.0.0.1:8546"
        headers = dict(self.config.get("rpc_headers") or {})
        # #104's chain on AWS: a per-engineer key, never in the config
        headers.update(auth_headers(os.environ.get("POFCTL_RPC_TOKEN"),
                                    os.environ.get("POFCTL_RPC_AUTH") or "Authorization"))
        self.rpc = Rpc(url, headers)
        self.version = 1 if args.v1 else 2
        self.record = load_record(self.version, args.record or self.config.get("record"))
        self.race = Race(self.rpc, self.record, self.version)
        self.src = keysrc.source(self.config.get("keys"))
        self.profiles = {**DEFAULT_ROLE, **(self.config.get("profiles") or {})}
        self._wallets: dict = {}

    @staticmethod
    def _config(path):
        p = path or os.environ.get("POFCTL_CONFIG") or "pofctl.json"
        return json.loads(Path(p).read_text(encoding="utf-8")) if Path(p).exists() else {}

    def key_role(self, role: str) -> str:
        return self.args.as_role or self.profiles.get(role, role)

    def wallet(self, role: str) -> Wallet:
        kr = self.key_role(role)
        if kr not in self._wallets:
            self._wallets[kr] = Wallet(self.rpc, keysrc.key(kr, self.src), kr)
        return self._wallets[kr]

    def address(self, key_role: str) -> str:
        if key_role not in self._wallets:
            self._wallets[key_role] = Wallet(self.rpc, keysrc.key(key_role, self.src), key_role)
        return self._wallets[key_role].address

    def devnet_only(self, what: str) -> None:
        cid = self.race.chain_id()
        if cid not in DEVNET_CHAINS:
            raise Fail(f"{what} runs on a devnet only (chain {cid} isn't one of {DEVNET_CHAINS})")

    def held_oracle_keys(self) -> list:
        """The devnet keys this source holds that are active oracle keys: the oracle roles, then the joiners."""
        found = []
        for role in [r for r in keysrc.ROLES if r.startswith(("oracle-", "joiner-"))]:
            try:
                k = keysrc.key(role, self.src)
            except keysrc.KeyError_:
                continue
            if self.race.is_oracle(keysrc.address(k)):
                found.append(k)
        return found

    def stub_quorum(self) -> Signers:
        """The quorum's worth of devnet oracle keys in the deployed set (the stub quorum signs accepts, and v1's
        results). v2's verdicts are signed by the drawn judges among them (stub_judges)."""
        self.devnet_only("the stub quorum")
        need, found = self.race.quorum(), self.held_oracle_keys()
        if len(found) < need:
            raise Fail(f"only {len(found)} of the {need} oracle keys needed are in the deployed set")
        return Signers(found[:need])

    def stub_judges(self) -> Signers:
        """Every devnet oracle key held: whichever of them are drawn for a submission sign its verdict (v2)."""
        self.devnet_only("the stub quorum")
        if self.version == 1:
            return self.stub_quorum()
        return Signers(self.held_oracle_keys())

    def repo(self, full_name: str):
        return repo_for(full_name, self.config if self.config.get("repos") else load_repos())


# ---------- commands (each returns (data, human lines)) ----------

def cmd_status(ctx: Ctx, a) -> tuple:
    r = ctx.race
    data = {"version": ctx.version, "chainId": r.chain_id(), "block": ctx.rpc.block(), "day": r.day(),
            "race": r.address, "coin": r.coin, "quoter": r.quoter, "oracles": r.oracle_keys(), "quorum": r.quorum(),
            "keys": ctx.src, "record": ctx.record.get("commit", "")}
    lines = [f"chain {data['chainId']}, block {data['block']}, contract day {data['day']} (v{ctx.version})",
             f"race {r.address}", f"coin {r.coin} (test coin, devnet only)",
             f"oracle quorum {data['quorum']} of {len(data['oracles'])}", f"keys from {ctx.src}"]
    return data, lines


def cmd_mint(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("coin")
    to = ctx.address(a.to)
    ctx.race.mint(w, to, int(a.amount * C))
    return {"to": a.to, "address": to, "amount": int(a.amount * C)}, [f"minted {a.amount:,.2f} to {a.to} ({to})"]


def _repo_id(ctx: Ctx, repo: str | None) -> bytes:
    """--repo: "registry" (this repository in the head registry, from the record), a 0x bytes32, or none (0: a
    project outside the registry, such as the demo's GitHub repository)."""
    if not repo:
        return v2.ZERO
    if repo == "registry":
        return v2.b32(ctx.record["repo"])
    return v2.b32(repo)


def cmd_register(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("reporter")
    issue = ctx.race.register(w, _repo_id(ctx, a.repo)) if ctx.version == 2 else ctx.race.register(w)
    cfg = ctx.race.config()
    paste = logic.claim_lines(issue, w.address)
    lines = [f"{w.role} registered on-chain issue {issue}: paid the registration fee "
             f"{fmt(cfg['registrationFee'])} and staked {fmt(cfg['issueStake'])}",
             "add these two lines to the forge issue's body, each on its own line (the issue needs the bounty label):",
             "", *paste, "",
             "then the judges' registration check opens its bounty and the bot links it (#210); on a devnet without "
             f"them, the stub quorum: pofctl oracle accept --issue {issue}"]
    return {"issue": issue, "reporter": w.address, "lines": paste}, lines


def cmd_fund(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("funder")
    amount = int(a.amount * C)
    ctx.race.pledge(w, a.bounty, amount)
    q = ctx.race.quote(a.bounty)
    return ({"bounty": a.bounty, "pledged": amount, "price": q["price"]},
            [f"{w.role} pledged {fmt(amount)} to bounty {a.bounty}", f"price now {fmt(q['price'])} "
             f"(the share on offer: {q['offerBps'] / 100:.0f} %{', locked' if q['locked'] else ', rising daily'})"])


def cmd_quote(ctx: Ctx, a) -> tuple:
    q = ctx.race.quote(a.bounty)
    lines = [f"bounty {a.bounty}: {q['state']}, day {q['day']}",
             f"  price            {fmt(q['price'])} ({q['offerBps'] / 100:.2f} % of the cap {fmt(q['cap'])}"
             f"{', locked' if q['locked'] else ', rising until the first attempt'})",
             f"  paid in          {q['instalments']} instalments of {fmt(q['instalment'])}, the last "
             f"{fmt(q['lastInstalment'])}",
             f"  finder's fee     {fmt(q['finderFee'])} (to the reporter)",
             f"  attempts         {q['attempting']} in progress",
             f"  to try it        attempt fee {fmt(q['attemptFee'])} (never refunded)",
             f"  other fees       evaluation {fmt(q['evaluationFee'])}, appeal {fmt(q['appealFee'])}"]
    if q.get("metered"):
        repo = ctx.race.issue(ctx.race.bounty(a.bounty)["issue"])["repo"]
        p = ctx.race.profile(repo)
        q["profile"] = p
        lines += [f"  check deposit    at most {fmt(q['checkDeposit'])}: the meter's worst case for {q['judges']} "
                  f"judges at the caps; each check is charged its measured usage, the rest returns",
                  f"  service fee      {fmt(q['serviceFee'])} per counted judge, on top of its usage",
                  f"  CI profile       {p['milliVcpus'] / 1000:g} vCPU, {p['memoryMb']} MB, {p['timeoutSeconds']} s "
                  f"timeout (image {p['image'][:18]}…)"]
    else:
        lines += [f"  check deposit    {fmt(q['checkDeposit'])} (a fixed fee per signing oracle from it; the rest "
                  f"returns)"]
    if q["state"] == "Open":
        lines.insert(5, f"  sunsets on day   {q['sunsetDay']} without a checked submission")
    return q, lines


def cmd_attempt(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("solver")
    ctx.race.attempt(w, a.bounty)
    b = ctx.race.bounty(a.bounty)
    return ({"bounty": a.bounty, "solver": w.address, "lockBps": b["lockBps"]},
            [f"{w.role} attempted bounty {a.bounty}: the share is locked at {b['lockBps'] / 100:.0f} %"])


def cmd_submit(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("solver")
    fix = fix_of(a.commit, ctx.version)
    salt = bytes.fromhex(a.salt[2:]) if a.salt else secrets.token_bytes(32)
    sealed = commitment(fix, salt, w.address)
    s = ctx.race.commit(w, a.bounty, sealed)
    body = logic.pr_body(a.issue or 0, a.bounty, s, "0x" + salt.hex(), w.address)
    sub = ctx.race.submission(s)
    data = {"bounty": a.bounty, "submission": s, "fix": "0x" + fix.hex(), "salt": "0x" + salt.hex(),
            "commitment": "0x" + sealed.hex(), "solver": w.address, "prBody": body, "deposit": sub["deposit"]}
    if ctx.version == 2:
        data["seed"] = sub["seed"]
        data["judges"] = ctx.race.drawn(s)[0]
    lines = [f"{w.role} sealed submission {s} on bounty {a.bounty} (commit {a.commit[:12]}, fix 0x{fix.hex()[:12]}…), "
             f"deposit {fmt(sub['deposit'])}"]
    if ctx.version == 2:
        lines.append(f"drawn judges: {', '.join(data['judges'])}")
    lines += ["open the pull request with this body (the salt reveals the fix to the oracles):", ""] + body.splitlines()
    return data, lines


def _claim_check(ctx: Ctx, s: int, repo: str | None, pr: int | None, commit: str | None, salt: str | None) -> tuple:
    """What the oracles check before they sign: the pull request (or the given commit and salt) opens the sealed
    submission. Returns (the fix's hash, the commit it was checked on: the pull request's base, or 0)."""
    sub = ctx.race.submission(s)
    base = v2.ZERO
    if pr is not None:
        p = ctx.repo(repo).pull(pr)
        c = logic.claim(p["body"])
        if c is None or c.submission != s or c.bounty != sub["bounty"]:
            raise Fail(f"pull request #{pr} doesn't claim submission {s} of bounty {sub['bounty']}")
        commit, salt, solver = p["head_sha"], c.salt, c.solver
        if p.get("base_sha"):
            base = v2.commit_word(p["base_sha"])
    else:
        if not (commit and salt):
            raise Fail("give --repo and --pr, or --commit and --salt, to open the sealed submission")
        solver = sub["solver"]
    fix = fix_of(commit, ctx.version)
    if solver.lower() != sub["solver"].lower():
        raise Fail(f"the claim names {solver}, the submission's solver is {sub['solver']}")
    if "0x" + commitment(fix, bytes.fromhex(salt[2:]), solver).hex() != sub["commitment"].lower():
        raise Fail(f"submission {s}'s seal doesn't open to commit {commit[:12]} with that salt")
    return fix, base


def cmd_accept(ctx: Ctx, a) -> tuple:
    signers = ctx.stub_quorum()
    b = ctx.race.accept(ctx.wallet("oracle"), signers, a.issue, int(a.weight * C))
    return ({"issue": a.issue, "bounty": b, "signers": ctx.race.signer_addresses(signers)},
            [f"stub quorum ({len(signers.secrets)} oracles) accepted issue {a.issue}: bounty {b} is open"])


def _charged(ctx: Ctx, receipt: dict) -> int:
    """The meter's Charged total in a result's receipt (0 without a meter)."""
    topic = "0x" + v2.keccak256(v2.CHARGED.encode()).hex()
    for log in receipt["logs"]:
        if log["topics"] and log["topics"][0] == topic:
            return int(log["data"][-64:], 16)
    return 0


def cmd_result(ctx: Ctx, a) -> tuple:
    signers = ctx.stub_judges()
    base = v2.ZERO
    if a.outcome == "pass" or a.pr is not None or a.commit:
        fix, base = _claim_check(ctx, a.submission, a.repo, a.pr, a.commit, a.salt)
    else:
        fix = b"\0" * 32
    outcome = PASS if a.outcome == "pass" else FAIL
    fee = int(a.fee * C)
    deposit = ctx.race.submission(a.submission)["deposit"]
    receipt = ctx.race.result(ctx.wallet("oracle"), signers, a.submission, outcome, fix, fee, base=base)
    sub = ctx.race.submission(a.submission)
    b = ctx.race.bounty(sub["bounty"])
    data = {"submission": a.submission, "outcome": sub["outcome"], "bounty": sub["bounty"], "state": b["state"]}
    if ctx.version == 1:
        data.update(feeEach=fee, signers=ctx.race.signer_addresses(signers))
        return data, [f"stub quorum signed submission {a.submission}: {sub['outcome']}; each of "
                      f"{len(signers.secrets)} oracles earns {fmt(fee)} from the check deposit",
                      f"bounty {sub['bounty']} is {b['state']}"]
    judges = [j for j, _ in ctx.race.drawn_signers(signers, a.submission)]
    charged = _charged(ctx, receipt)
    data.update(signers=judges, deposit=deposit, charged=charged, refunded=deposit - charged)
    return data, [f"the drawn judges {', '.join(j[:10] for j in judges)} reported their usage and signed submission "
                  f"{a.submission}: {sub['outcome']}",
                  f"the meter charged {fmt(charged)} of the {fmt(deposit)} deposit (usage plus the service fee per "
                  f"judge, and the relay's gas); {fmt(deposit - charged)} returns to the solver",
                  f"bounty {sub['bounty']} is {b['state']}"]


def cmd_merged(ctx: Ctx, a) -> tuple:
    if a.pr is not None and not ctx.repo(a.repo).merged(a.pr):
        raise Fail(f"pull request #{a.pr} isn't merged: solved = merged")
    signers = ctx.stub_judges()
    ctx.race.merged(ctx.wallet("oracle"), signers, a.bounty, int(a.weight * C))
    b = ctx.race.bounty(a.bounty)
    aw = ctx.race.award(a.bounty, b["epoch"])
    return ({"bounty": a.bounty, "state": b["state"], "winner": aw["winner"], "windowEnd": aw["windowEnd"]},
            [f"stub quorum signed the merge of bounty {a.bounty}: {b['state']}, award to {aw['winner']}",
             f"the challenge window ends on day {aw['windowEnd']}; instalments follow at each release"])


def cmd_uphold(ctx: Ctx, a) -> tuple:
    ctx.devnet_only("an upheld challenge signed by the stub quorum")
    if ctx.version < 2:
        raise Fail("upheld challenges are v2's (RaceV2.challengeUpheld)")
    epoch = ctx.race.bounty(a.bounty)["epoch"]
    ctx.race.uphold_challenge(ctx.wallet("oracle"), ctx.stub_quorum(), a.bounty, epoch)
    b = ctx.race.bounty(a.bounty)
    aw = ctx.race.award(a.bounty, epoch)
    return ({"bounty": a.bounty, "epoch": epoch, "state": b["state"], "award": aw},
            [f"stub quorum upheld a challenge against bounty {a.bounty}'s award {epoch}: the bounty is {b['state']}, "
             f"the award keeps {aw.get('earned', 0)} instalment(s) earned"])


def cmd_link(ctx: Ctx, a) -> tuple:
    repo = ctx.repo(a.repo)
    issue = repo.issue(a.issue)
    if logic.linked(repo.comments(a.issue)):
        return {"linked": True, "issue": a.issue}, [f"{a.repo}#{a.issue} is already linked"]
    reporter = logic.wallet(issue["body"], "Reporter")
    if reporter is None:
        raise Fail(f"{a.repo}#{a.issue} names no 'Reporter wallet:'")
    on_chain = ctx.race.bounty(a.bounty)
    if ctx.race.issue(on_chain["issue"])["reporter"].lower() != reporter.lower():
        raise Fail(f"bounty {a.bounty}'s issue wasn't registered by {reporter}")
    repo.comment(a.issue, logic.bounty_comment(ctx.race.address, a.bounty, on_chain["issue"]))
    return ({"linked": True, "issue": a.issue, "bounty": a.bounty},
            [f"commented on {a.repo}#{a.issue}: bounty {a.bounty} (on-chain issue {on_chain['issue']})"])


def cmd_settle(ctx: Ctx, a) -> tuple:
    if (a.repo is None) != (a.issue is None):
        raise Fail("give both --repo and --issue (the bounty's issue, closed once it's paid), or neither")
    before = ctx.race.bounty(a.bounty)["state"]
    ctx.race.settle(ctx.wallet("bot"), a.bounty)
    b = ctx.race.bounty(a.bounty)
    done = b["state"] == "Paid"
    lines = [f"bounty {a.bounty}: {before} -> {b['state']}" + ("" if done else " (not due yet: the instalments are "
                                                                               "released over the coming releases)")]
    data = {"bounty": a.bounty, "state": b["state"], "settled": done}
    if done and a.repo:
        data["issue"] = close_paid(ctx, a.repo, a.issue)
        lines.append(data["issue"]["line"])
    return data, lines


# ---------- the bot closes a paid bounty's issue (#151's second part) ----------
# The bot links an issue to its bounty (bot link) and settles it (bot settle): it's the one that sees the payout, so it
# closes the issue then, with a comment linking the payout transaction. `bot close` is the same step as a watcher's
# pass, for a bounty someone else settled (anyone can). The validator node never writes to a repository host: it stays
# host-agnostic. Both hosts work through bot/forge.py's RepoHost (GitHub, and Forgejo for pof-sandbox).

def _explorer(ctx: Ctx) -> str:
    """An explorer's transaction URL template (with {tx}): the config's "explorer", or $POFCTL_EXPLORER."""
    return os.environ.get("POFCTL_EXPLORER") or ctx.config.get("explorer") or ""


def close_paid(ctx: Ctx, repo_name: str, number: int) -> dict:
    """Closes `repo_name`#`number` if the bounty it's linked to on this race was paid, with a comment linking the
    payout transaction. Idempotent: the comment is written once (its marker), and a closed issue stays as it is."""
    repo = ctx.repo(repo_name)
    issue = repo.issue(number)
    comments = repo.comments(number)
    link = logic.linked(comments)
    out = {"repo": repo_name, "issue": number, "closed": issue["state"] == "closed", "commented": False}
    if link is None or link[0].lower() != ctx.race.address.lower():
        return {**out, "paid": False, "line": f"{repo_name}#{number} isn't linked to a bounty on this race"}
    bounty = link[1]
    pay = ctx.race.payout(bounty)
    out.update(bounty=bounty, paid=pay is not None)
    if pay is None:
        return {**out, "line": f"{repo_name}#{number}: bounty {bounty} isn't paid yet; the issue stays open"}
    out.update(tx=pay["tx"], block=pay["block"])
    if logic.paid(comments) is None:
        repo.comment(number, logic.paid_comment(ctx.race.address, bounty, pay["tx"], pay["block"],
                                                ctx.race.chain_id(), _explorer(ctx)))
        out["commented"] = True
    was_closed = out["closed"]
    if not was_closed:
        repo.close(number)
        out["closed"] = True
    what = "closed" if not was_closed else "already closed"
    note = ", commented the payout" if out["commented"] else ""
    return {**out, "line": f"{repo_name}#{number} {what}{note}: bounty {bounty} paid in {pay['tx']} (block "
                           f"{pay['block']})"}


def cmd_close(ctx: Ctx, a) -> tuple:
    """One pass of the watcher: the issue given, or every open issue labelled for a bounty on the repository."""
    if ctx.version < 2:
        raise Fail("closing on payout is v2's (pofctl bot close)")
    numbers = [a.issue] if a.issue is not None else [i["number"] for i in ctx.repo(a.repo).issues("open", logic.LABEL)]
    results = [close_paid(ctx, a.repo, n) for n in numbers]
    lines = [r["line"] for r in results] or [f"no open issue labelled {logic.LABEL!r} on {a.repo}"]
    return results, lines


# ---------- the contributor leaderboard (#151) ----------

def cmd_leaderboard(ctx: Ctx, a) -> tuple:
    """Rankings from the contracts' events only (pofctl/leaderboard.py). Reading the chain costs nothing: no fee."""
    if ctx.version < 2:
        raise Fail("the leaderboard reads v2's events")
    period = a.period
    bounties = None
    if a.bounties:
        try:
            bounties = [int(x) for x in a.bounties.split(",") if x.strip()]
        except ValueError:
            raise Fail("--bounties takes bounty numbers, comma-separated") from None
    block, now = ctx.race.now()
    events = ctx.race.board_events(a.from_block, with_time=period != "all")
    board = leaderboard.compute(events, a.coin or ctx.race.coin, period, now, bounties, a.role)
    board["block"] = block
    return board, leaderboard.render(board)


def cmd_claim(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("funder")
    ctx.race.claim_refund(w, a.bounty)
    return {"bounty": a.bounty, "funder": w.address}, [f"{w.role} claimed its refund from bounty {a.bounty}"]


def cmd_withdraw(ctx: Ctx, a) -> tuple:
    w = Wallet(ctx.rpc, keysrc.key(a.role, ctx.src), a.role)
    owed = ctx.race.owed(w.address)
    if owed:
        ctx.race.withdraw(w)
    return {"role": a.role, "withdrawn": owed}, [f"{a.role} withdrew {fmt(owed)} of credit to its wallet"]


def cmd_balances(ctx: Ctx, a) -> tuple:
    rows = []
    for role in a.roles.split(","):
        role = role.strip()
        if role:
            rows.append((role, ctx.address(role)))
    cfg = ctx.race.config()
    rows += [("infrastructure", cfg["infrastructure"]), ("insurance", cfg["insurance"])]
    rows += [(f"oracle {k[:10]}…", k) for k in ctx.race.oracle_keys()]
    if ctx.version == 2:
        rows.append(("bot (relayer)", ctx.address(ctx.key_role("oracle"))))
    data, lines = [], [f"{'account':<22} {'wallet':>18} {'credit':>16}"]
    for name, addr in rows:
        wallet, credit = ctx.race.coin_balance(addr), ctx.race.owed(addr)
        data.append({"account": name, "address": addr, "wallet": wallet, "credit": credit})
        lines.append(f"{name:<22} {fmt(wallet):>18} {fmt(credit):>16}")
    return data, lines


def cmd_history(ctx: Ctx, a) -> tuple:
    events = ctx.race.history(a.from_block)
    lines = []
    for e in events:
        detail = ", ".join(f"{k} {fmt(v) if k == 'amount' else v}" for k, v in e.items()
                           if k not in ("block", "event", "tx", "logIndex", "time"))
        lines.append(f"block {e['block']:>6}  {e['event']:<14} {detail}")
    return events, lines or ["no events yet"]


def cmd_validator(ctx: Ctx, a) -> tuple:
    me = ctx.address(ctx.key_role("validator"))
    r = ctx.race
    if ctx.version == 1:
        data = {"address": me, "inSet": r.is_oracle(me), "quorum": r.quorum(), "keys": len(r.oracle_keys()),
                "wallet": r.coin_balance(me), "credit": r.owed(me)}
        return data, [f"validator {ctx.key_role('validator')} {me}: {'in' if data['inSet'] else 'NOT in'} the oracle "
                      f"set (quorum {data['quorum']} of {data['keys']})",
                      f"  fees earned      wallet {fmt(data['wallet'])}, credit {fmt(data['credit'])}"]
    seat = r.seat_of_key(me)
    st = r.seat(seat) if seat is not None else None
    drawn, decided, reported = [], [], []
    for e in r.history():
        if e["event"] != "Committed":
            continue
        s = e["submission"]
        judges, recused = r.drawn(s)
        if any(j.lower() == me.lower() for j in judges):
            drawn.append(s)
            sub = r.submission(s)
            if sub["outcome"] != "None":
                decided.append({"submission": s, "outcome": sub["outcome"]})
            if any(x["judge"].lower() == me.lower() for x in r.reports(s)):
                reported.append(s)
    withdrawn = sum(e["amount"] for e in r.history()
                    if e["event"] == "Withdrawn" and e["account"].lower() == me.lower())
    credit = r.owed(me)
    data = {"address": me, "seat": seat, "active": bool(st and st["active"]), "pending": st and st["pending"],
            "quorum": r.quorum(), "activeSeats": len(r.oracle_keys()), "seats": r.seat_count(), "drawn": drawn,
            "verdicts": decided, "usageReports": reported, "credit": credit, "withdrawn": withdrawn,
            "feesEarned": credit + withdrawn, "wallet": r.coin_balance(me), "serviceFee": r.service_fee()}
    if seat is None:
        where = "not a seat's key (join a vacant seat: pofctl validator join --seat <n>)"
    elif st["active"] and st["key"].lower() == me.lower():
        where = f"seat {seat}, active"
    else:
        where = f"seat {seat}, pending until {st['pending']['effectiveAt']} (then: pofctl validator activate)"
    lines = [f"validator {ctx.key_role('validator')} {me}: {where}",
             f"  seats            {data['activeSeats']} active of {data['seats']} (quorum {data['quorum']}; 3 judges "
             f"drawn per check, 2 must agree)",
             f"  drawn            {len(drawn)} submission(s){': ' + ', '.join(map(str, drawn)) if drawn else ''}",
             f"  verdicts         {len(decided)} decided: "
             + (", ".join(f"{d['submission']} {d['outcome']}" for d in decided) or "none yet"),
             f"  usage reports    {len(reported)} to the meter",
             f"  fees earned      {fmt(data['feesEarned'])} (credit {fmt(credit)}, withdrawn {fmt(withdrawn)}; "
             f"usage plus {fmt(data['serviceFee'])} per counted check)"]
    return data, lines


def cmd_join(ctx: Ctx, a) -> tuple:
    """The engineer's half of a join: the digest a vacant seat's new key signs, signed with that key."""
    w = ctx.wallet("validator")
    r = ctx.race
    if a.seat >= r.seat_count():
        raise Fail(f"there is no seat {a.seat} (the deployment has {r.seat_count()})")
    st = r.seat(a.seat)
    if st["pending"]:
        raise Fail(f"seat {a.seat} already has a key pending ({st['pending']['key']})")
    nonce = v2.b32(a.nonce) if a.nonce else secrets.token_bytes(32)
    digest = r.rotate_digest(a.seat, w.address, nonce)
    req = {"seat": a.seat, "key": w.address, "nonce": "0x" + nonce.hex(), "digest": "0x" + digest.hex(),
           "sig": "0x" + w.sign(digest).hex()}
    vacant = int(st["key"], 16) == 0
    return req, [f"{w.role} {w.address} signed the join of seat {a.seat} ({'vacant' if vacant else 'a rotation'})",
                 "send this request to the deployment's owner, who publishes it with the seats' co-signatures:",
                 f"  pofctl validator publish --seat {a.seat} --key {w.address} --nonce {req['nonce']} "
                 f"--sig {req['sig']}",
                 f"  (or: scripts/devnet.sh join-v2 {a.seat} --key {w.address} --sig {req['sig']} "
                 f"--nonce {req['nonce']})",
                 "the key takes the seat 7 days later: pofctl validator activate --seat " + str(a.seat)]


def cmd_publish(ctx: Ctx, a) -> tuple:
    """The owner's half (devnet): the quorum of the other seats' keys co-signs the engineer's join, and it's sent."""
    ctx.devnet_only("publishing a join with the devnet's seat keys")
    r = ctx.race
    nonce = v2.b32(a.nonce)
    digest = r.rotate_digest(a.seat, a.key, nonce)
    new_sig = bytes.fromhex(a.sig[2:] if a.sig.startswith("0x") else a.sig)
    if recover(digest, new_sig).lower() != a.key.lower():
        raise Fail(f"the signature isn't {a.key}'s over seat {a.seat}'s join digest (check the nonce)")
    current = r.seat(a.seat)["key"]
    others = [k for k in ctx.held_oracle_keys() if keysrc.address(k).lower() != current.lower()][:r.quorum()]
    if len(others) < r.quorum():
        raise Fail(f"only {len(others)} of the {r.quorum()} co-signing seats' keys are held")
    sigs = v2.ordered_signatures(digest, [new_sig] + [sign(k, digest) for k in others])
    r.rotate(ctx.wallet("oracle"), a.seat, a.key, nonce, sigs)
    at = r.seat(a.seat)["pending"]["effectiveAt"]
    return ({"seat": a.seat, "key": a.key, "effectiveAt": at, "cosigners": len(others)},
            [f"published {a.key} for seat {a.seat}, co-signed by {len(others)} seats; it takes the seat at {at} "
             f"(7 days): pofctl validator activate --seat {a.seat}"])


def cmd_activate(ctx: Ctx, a) -> tuple:
    r = ctx.race
    r.activate(ctx.wallet("oracle"), a.seat)
    st = r.seat(a.seat)
    return ({"seat": a.seat, "key": st["key"], "active": st["active"]},
            [f"seat {a.seat}: {st['key']} {'active' if st['active'] else 'NOT active'}; {len(r.oracle_keys())} "
             f"active seats"])


def cmd_validator_withdraw(ctx: Ctx, a) -> tuple:
    w = ctx.wallet("validator")
    owed = ctx.race.owed(w.address)
    if owed:
        ctx.race.withdraw(w, a.to)
    return ({"validator": w.address, "withdrawn": owed, "to": a.to or w.address},
            [f"{w.role} withdrew {fmt(owed)} in check fees to {a.to or w.address}"])


def cmd_verify_head(ctx: Ctx, a) -> tuple:
    """#201: a repository's canonical main (on Radicle, through its node; or a commit given) is Heads.head(repo).
    A mismatch is refused (exit 1), with both commits."""
    from oracle import radicle

    if ctx.version < 2:
        raise Fail("Heads is v2's")
    if not a.rid and not a.commit:
        raise Fail("verify-head: --rid (read canonical main from Radicle) or --commit")
    repo = _repo_id(ctx, a.repo) if a.repo else radicle.repo_id(a.rid) if a.rid else v2.b32(ctx.record["repo"])
    chain = v2.Chain(ctx.rpc, ctx.race.address)
    head = radicle.sha_of(chain.head(repo)["commit"])
    if a.rid:
        try:
            snap = radicle.Radicle(a.rid, shlex.split(a.rad_exec or ""), a.repo_dir or "").snapshot()
        except radicle.Unavailable as e:
            raise Fail(str(e)) from None
        d = radicle.verify_head(head, snap)
        canonical = radicle.canonical(snap)
    else:
        canonical = a.commit.strip().lower()
        d = (radicle.Decision(radicle.SIGN, f"{canonical} is Heads' head") if canonical == head else
             radicle.Decision(radicle.REFUSE, f"{canonical} isn't Heads' head {head}"))
    if d.action != radicle.SIGN:
        raise Fail(f"verify-head refused: {d.reason}")
    return ({"repo": "0x" + repo.hex(), "head": head, "canonical": canonical, "match": True},
            [f"repository 0x{repo.hex()[:12]}: {d.reason}"])


def cmd_warp(ctx: Ctx, a) -> tuple:
    ctx.devnet_only("warping time")
    ctx.rpc.call("evm_increaseTime", [a.days * 86_400])
    ctx.rpc.call("evm_mine", [])
    return {"days": a.days, "day": ctx.race.day()}, [f"{a.days} day(s) later: contract day {ctx.race.day()}"]


# ---------- parser ----------

def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pofctl", description="Play proof-of-fix's roles against a devnet (#104).")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--config", help="pofctl.json (rpc, record, keys, profiles, repos)")
    p.add_argument("--rpc", help="the chain's RPC URL (default http://127.0.0.1:8546, the devnet)")
    p.add_argument("--record", help="the deployment record (default contracts/deployments/devnet-v2.json)")
    p.add_argument("--v1", action="store_true", help="drive v1 (Race) instead of v2 (RaceV2)")
    p.add_argument("--as", dest="as_role", help="use this role's key (e.g. solver-b) instead of the default")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="the chain, the deployment and the oracle set").set_defaults(fn=cmd_status)

    coin = sub.add_parser("coin", help="the devnet's test coin").add_subparsers(dest="action", required=True)
    m = coin.add_parser("mint", help="mint test coins to a role (devnet only)")
    m.add_argument("--to", required=True, help="the role to mint to (e.g. funder, solver-a)")
    m.add_argument("--amount", type=float, default=1000)
    m.set_defaults(fn=cmd_mint)

    rep = sub.add_parser("reporter").add_subparsers(dest="action", required=True)
    r = rep.add_parser("register", help="register an issue on-chain (fee + stake)")
    r.add_argument("--repo", help="v2: 'registry' (this repository's head registry entry) or a 0x bytes32; default 0, "
                                  "a project outside the registry (the demo's GitHub repository)")
    r.set_defaults(fn=cmd_register)

    fun = sub.add_parser("funder").add_subparsers(dest="action", required=True)
    f = fun.add_parser("fund", help="pledge to a bounty")
    f.add_argument("--bounty", type=int, required=True)
    f.add_argument("--amount", type=float, required=True, help="coins (6 decimals)")
    f.set_defaults(fn=cmd_fund)
    f = fun.add_parser("claim", help="claim the refund of a closed bounty's leftover")
    f.add_argument("--bounty", type=int, required=True)
    f.set_defaults(fn=cmd_claim)

    sol = sub.add_parser("solver").add_subparsers(dest="action", required=True)
    s = sol.add_parser("quote", help="the price, the fees and the rates before trying")
    s.add_argument("--bounty", type=int, required=True)
    s.set_defaults(fn=cmd_quote)
    s = sol.add_parser("attempt", help="start an attempt (locks the price's share)")
    s.add_argument("--bounty", type=int, required=True)
    s.set_defaults(fn=cmd_attempt)
    s = sol.add_parser("submit", help="seal a fix on-chain with the check deposit; prints the PR body")
    s.add_argument("--bounty", type=int, required=True)
    s.add_argument("--commit", required=True, help="the fix's git commit (the pull request's head)")
    s.add_argument("--issue", type=int, help="the repository's issue number, for the PR body")
    s.add_argument("--salt", help="0x + 64 hex (default: random)")
    s.set_defaults(fn=cmd_submit)

    orc = sub.add_parser("oracle", help="the stub quorum (devnet only; a real validator runs oracle/)").add_subparsers(
        dest="action", required=True)
    o = orc.add_parser("accept", help="the registration check: open the issue's bounty")
    o.add_argument("--issue", type=int, required=True, help="the on-chain issue")
    o.add_argument("--weight", type=float, default=REGISTERED / C, help="the importance estimate")
    o.set_defaults(fn=cmd_accept)
    o = orc.add_parser("result", help="sign a submission's result (pass checks the seal against the PR)")
    o.add_argument("--submission", type=int, required=True)
    o.add_argument("--outcome", choices=["pass", "fail"], required=True)
    o.add_argument("--repo", help="owner/name of the pull request's repository")
    o.add_argument("--pr", type=int)
    o.add_argument("--commit", help="without --pr: the fix's commit")
    o.add_argument("--salt", help="without --pr: the submission's salt")
    o.add_argument("--fee", type=float, default=0.3, help="v1: each signing oracle's fee from the deposit (v2 is "
                                                          "metered)")
    o.set_defaults(fn=cmd_result)
    o = orc.add_parser("merged", help="sign the winning fix's merge (solved = merged)")
    o.add_argument("--bounty", type=int, required=True)
    o.add_argument("--weight", type=float, default=AT_MERGE / C, help="the merge's importance estimate")
    o.add_argument("--repo")
    o.add_argument("--pr", type=int, help="checked merged on the host first")
    o.set_defaults(fn=cmd_merged)
    o = orc.add_parser("uphold-challenge", help="v2, devnet: a challenge upheld against a merged bounty's award "
                                                "(reopens the bounty; the award keeps what it has earned)")
    o.add_argument("--bounty", type=int, required=True)
    o.set_defaults(fn=cmd_uphold)

    val = sub.add_parser("validator").add_subparsers(dest="action", required=True)
    val.add_parser("status", help="seat, draws, verdicts, usage reports and fees earned").set_defaults(fn=cmd_validator)
    v = val.add_parser("join", help="sign a vacant seat's join with this validator's own key (prints the request)")
    v.add_argument("--seat", type=int, required=True)
    v.add_argument("--nonce", help="0x + 64 hex (default: random)")
    v.set_defaults(fn=cmd_join)
    v = val.add_parser("publish", help="owner, devnet: co-sign a join request with the seats' keys and send it")
    v.add_argument("--seat", type=int, required=True)
    v.add_argument("--key", required=True, help="the new key's address")
    v.add_argument("--nonce", required=True)
    v.add_argument("--sig", required=True, help="the new key's signature over the join digest")
    v.set_defaults(fn=cmd_publish)
    v = val.add_parser("activate", help="the published key takes its seat (7 days after publishing)")
    v.add_argument("--seat", type=int, required=True)
    v.set_defaults(fn=cmd_activate)
    v = val.add_parser("withdraw", help="pull this validator's check fees to its wallet")
    v.add_argument("--to", help="pay another address")
    v.set_defaults(fn=cmd_validator_withdraw)

    bot = sub.add_parser("bot").add_subparsers(dest="action", required=True)
    b = bot.add_parser("link", help="comment the bounty on the repository's issue")
    b.add_argument("--repo", required=True)
    b.add_argument("--issue", type=int, required=True, help="the repository's issue number")
    b.add_argument("--bounty", type=int, required=True)
    b.set_defaults(fn=cmd_link)
    b = bot.add_parser("settle", help="settle a merged bounty once its instalments are released; with --repo and "
                                      "--issue, close its issue once paid")
    b.add_argument("--bounty", type=int, required=True)
    b.add_argument("--repo", help="the bounty's repository (owner/name): its issue is closed once the bounty is paid")
    b.add_argument("--issue", type=int, help="the repository's issue number linked to the bounty")
    b.set_defaults(fn=cmd_settle)
    b = bot.add_parser("close", help="close a paid bounty's issue with a comment linking the payout transaction; "
                                     "without --issue, every open bounty issue of the repository (a watcher's pass)")
    b.add_argument("--repo", required=True)
    b.add_argument("--issue", type=int, help="the repository's issue number (default: every open one labelled bounty)")
    b.set_defaults(fn=cmd_close)

    b = bot.add_parser("watch", help="the bot as a service (#210): link, hint, settle, the due housekeeping and the "
                                     "closes, unattended; settings and secret files from POF_BOT_* (see bot/service.py)",
                       description="The bounty bot as a service (#210). It sends only settle, timeOut, mergeExpired and "
                                   "sunset, and comments and closes the repository's labelled issues. No option takes "
                                   "a secret. Exit codes: 0 idle, 2 refused at start, 4 the run's write fuse, 75 the "
                                   "chain or the forge away too long.",
                       epilog=None)
    b.add_argument("--until-idle", type=float, help="exit 0 after this many seconds with no write and nothing waiting")
    b.add_argument("--min-bounty", type=int, help="leave out bounties numbered below this, and their submissions "
                                                  "(default POF_BOT_MIN_BOUNTY, else 0)")
    b.set_defaults(fn=cmd_watch, service=True)

    w = sub.add_parser("withdraw", help="pay a role's credit in the contract to its wallet")
    w.add_argument("--role", required=True)
    w.set_defaults(fn=cmd_withdraw)

    bal = sub.add_parser("balances", help="wallet and credit of the roles, infrastructure and the oracles")
    bal.add_argument("--roles", default="reporter,funder,solver-a,solver-b")
    bal.set_defaults(fn=cmd_balances)

    lb = sub.add_parser("leaderboard", help="v2: rankings of solvers, reporters, funders and validators from the "
                                            "contracts' events only (read-only, free; addresses only)")
    lb.add_argument("--period", choices=sorted(leaderboard.PERIODS), default="all",
                    help="week (7 days) or month (30 days) back from the latest block's time, or all (default)")
    lb.add_argument("--role", choices=sorted([*leaderboard.ROLES, *leaderboard.ROLE_ALIASES]),
                    help="one role's table (default: all four)")
    lb.add_argument("--bounties", help="only these bounties' events, comma-separated (a run's own on a shared devnet)")
    lb.add_argument("--coin", help="the coin amounts are counted in (default: the deployment's)")
    lb.add_argument("--from-block", type=int, help="default: the deployment's block")
    lb.set_defaults(fn=cmd_leaderboard)

    h = sub.add_parser("history", help="the race's events")
    h.add_argument("--from-block", type=int)
    h.set_defaults(fn=cmd_history)

    vh = sub.add_parser("verify-head", help="v2: a repository's canonical main (Radicle, or --commit) is Heads' head; "
                                            "a mismatch is refused (#201)")
    vh.add_argument("--rid", help="the Radicle repository (its id in Heads: keccak256 of the RID)")
    vh.add_argument("--rad-exec", help="a command prefix that reaches its Radicle node (e.g. 'docker exec -i <name>')")
    vh.add_argument("--repo-dir", help="the working copy on that node (default ~/repo)")
    vh.add_argument("--commit", help="instead of --rid: a mirror's main to compare")
    vh.add_argument("--repo", help="the repository's id: 'registry' or a 0x bytes32 (default: from --rid, else the "
                                   "record's)")
    vh.set_defaults(fn=cmd_verify_head)

    dev = sub.add_parser("devnet").add_subparsers(dest="action", required=True)
    d = dev.add_parser("warp", help="move the devnet's clock (devnet only)")
    d.add_argument("--days", type=int, required=True)
    d.set_defaults(fn=cmd_warp)
    return p


def cmd_watch(a) -> int:
    """`pofctl bot watch`: the long-running service (bot/service.py); returns its exit code, not (data, lines)."""
    from bot import service

    return service.main(until_idle=a.until_idle, min_bounty=a.min_bounty, rpc_url=a.rpc, record_path=a.record)


def run(argv: list) -> tuple:
    """Parses and runs one command; returns (data, lines). Raises on failure (main() prints it)."""
    a = parser().parse_args(argv)
    return a.fn(Ctx(a), a)


def main(argv: list | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = "--json" in argv
    a = parser().parse_args(argv)
    if getattr(a, "service", False):
        return a.fn(a)
    try:
        data, lines = run(argv)
    except (Fail, RpcError, keysrc.KeyError_, FileNotFoundError, ValueError) as e:
        msg = e.reason if isinstance(e, Reverted) else str(e)
        print(json.dumps({"error": msg}) if as_json else f"pofctl: {msg}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2, default=str) if as_json else "\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
