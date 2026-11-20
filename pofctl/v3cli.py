"""pofctl on v3 and Radicle (proof-of-fix#251 task 4.4; design L6, L9, L12, L17; ADR 0007): the reporter, the funder
and the solver of a v3 race whose one repository lives on Radicle, as they play on Sepolia.

    pofctl --v3 status [--address 0x…]                  the solver's cap, open claims and the deposit a fix posts
    pofctl --v3 issue register --rad-issue <id>         register a Radicle issue on-chain (fee, stake, its check)
    pofctl --v3 issue open --issue N                    open its bounty once its registration check is final
    pofctl --v3 pledge --bounty B --amount X            fund it: refused below 3 active solvers, before anything is sent
    pofctl --v3 submit --bounty B --patch <commit>      seal a fix; prints how to open its Radicle patch
    pofctl --v3 claim --bounty B --patch <c> --base <c> --salt 0x…   the winner opens its seal
    pofctl --v3 merge --bounty B                        at finality, anyone moves Heads to the fix (L9)
    pofctl --v3 verify-head [--rid … --rad-exec …]      Radicle's canonical main is Heads.head
    pofctl --v3 checkout [--rid … --rad-exec …]         the commit Heads.head names, from any namespace
    pofctl --v3 withdraw --role solver                  the refunded deposits' rest and other credit, to the wallet
    pofctl faucet [--when]                              claim 20 test coins for your key (one claim every 2 hours)

The commands that only v3 has (issue, pledge, submit, claim, merge, checkout, faucet) select v3 by themselves; a v3
record (`"version": 3`) does too. Every amount is the deployment's fee coin, shown in coins with 6 decimals: on Sepolia
the project's own test coin, "proof-of-fix test coin" (POFTEST), with no value (L17 as amended on 2026-11-20). Its
keyless faucet gives 20 coins a claim, one claim per address every 2 hours (`pofctl faucet`); the coin is read from the
chain (RaceV3's contracts) and the faucet from the deployment record or the coin's `faucet()`. The coin needs an allowance before RaceV3 can take it: pofctl checks the balance and the
allowance first, says what it approves and why, and approves only when the allowance is short (as v2's commands do,
an unlimited allowance to the race). The taxi fare (`judgeFee` 0, ADR 0007's amendment): a fix posts FeesV3's
worst-case deposit for 7 judges, its judges are paid by the meter, and the rest is refunded to the solver."""

from __future__ import annotations

import re
import secrets
import shlex
import subprocess

from oracle import v2, v3
from oracle.abi import selector
from oracle.crypto import checksum, keccak256

from bot import logic

from .race import fmt
from .rpc import Reverted

K_MAX = 7  # RaceV3's: a fix's deposit is FeesV3's worst case for K_MAX judges (k is fixed only at the draw)
ACTIVE_SOLVERS_MIN = 3  # SolverBook.ACTIVE_SOLVERS_MIN (launch L6)
MAX = 2**256 - 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RAD_ISSUE_RE = re.compile(r"^[0-9a-f]{7,40}$")  # a Radicle issue's collaborative-object id, or a unique prefix
SEPOLIA = 11155111
FAUCET_HINT = "claim 20 test coins every 2 hours with `pofctl faucet`"

# RaceV3's and SolverBook's errors, by selector, as a reader would want them explained.
_ERRORS = {
    "TooFewActiveSolvers(uint256)": "pledges are refused while fewer than 3 solvers are active",
    "OverCap(address,uint256,uint256)": "the claim doesn't fit the solver's cap (D29)",
    "WrongState(uint256,uint8)": "the bounty isn't in the state this needs",
    "NotYet()": "not yet",
    "Refused()": "refused by the race",
    "AppealClosed()": "the appeal window is closed",
    "BadParams()": "bad parameters",
}
_BY_SELECTOR = {selector(sig).hex(): (sig, why) for sig, why in _ERRORS.items()}
BOOK_EVENTS = {"ClaimOpened": "ClaimOpened(uint256,address,uint256,uint256,uint256)",
               "ClaimClosed": "ClaimClosed(uint256,address,uint256)"}


class Fail(Exception):
    pass


def explain(e: Reverted) -> str:
    """A revert from RaceV3 or SolverBook, named and explained."""
    raw = (e.data or "")[2:] if (e.data or "").startswith("0x") else (e.data or "")
    hit = _BY_SELECTOR.get(raw[:8]) if len(raw) >= 8 else None
    if hit is None:
        return e.reason
    return f"{hit[0].split('(')[0]}: {hit[1]}"


def _topic(sig: str) -> str:
    return "0x" + keccak256(sig.encode()).hex()


def _log_of(receipt: dict, sig: str) -> dict:
    t = _topic(sig)
    for log in receipt["logs"]:
        if log["topics"] and log["topics"][0] == t:
            return log
    raise RuntimeError(f"no {sig} in the receipt")


def commit_sha(value: str, what: str) -> str:
    sha = (value or "").strip().lower()
    if not SHA_RE.match(sha):
        raise Fail(f"{what} must be a 40-character git commit id, not {value!r}")
    return sha


def salt_of(value: str | None) -> bytes:
    if not value:
        return secrets.token_bytes(32)
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
        raise Fail("--salt is 0x and 64 hex digits")
    return bytes.fromhex(value[2:])


# ---------- the deployment, read ----------

class RaceV3:
    """RaceV3, the contracts it names (oracle.v3.Chain) and its SolverBook, as pofctl reads them."""

    def __init__(self, rpc, record: dict) -> None:
        self.rpc, self.record = rpc, record
        # NodeV3Local's record names the race at its top; DeploySepolia's under `addresses`
        self.chain = v3.Chain(rpc, record.get("race") or (record.get("addresses") or {}).get("race"))
        self.address = self.chain.race
        self.coin = self.chain.coin()
        self.book = checksum(rpc.view(self.address, "solverBook()", ["address"])[0])
        self._unit = None

    def chain_id(self) -> int:
        return self.chain.chain_id()

    def faucet(self) -> str:
        """The test coin's faucet (L17): the deployment record's (`faucet`, `addresses.faucet` or `testCoin.faucet`),
        checked against the coin's own `faucet()`; else the coin's. A coin without one (a devnet's mock coin) fails."""
        rec = self.record
        named = rec.get("faucet") or (rec.get("addresses") or {}).get("faucet") or (rec.get("testCoin") or {}).get("faucet")
        try:
            on_chain = checksum(self.rpc.view(self.coin, "faucet()", ["address"])[0])
        except Reverted:
            on_chain = None
        if not on_chain or int(on_chain, 16) == 0:
            raise Fail(f"the fee coin {self.coin} has no faucet (a devnet's mock coin: `pofctl coin mint` there)")
        if named and checksum(named) != on_chain:
            raise Fail(f"the record's faucet {named} isn't the coin's ({on_chain})")
        return on_chain

    def unit(self) -> int:
        """10 ** the fee coin's decimals (RaceV3's `unit`): micro-coins to the coin's smallest units."""
        if self._unit is None:
            self._unit = self.rpc.view(self.address, "unit(address)", ["uint256"], self.coin)[0] or 10**6
        return self._unit

    def units(self, micro: int) -> int:
        """What RaceV3 takes for `micro` micro-coins (its `_units`)."""
        return micro * self.unit() // 10**6

    def micro(self, units: int) -> int:
        return units * 10**6 // self.unit()

    def from_block(self) -> int:
        return int(self.record.get("block", 0))

    # ----- the solver's book (D29, L6) -----

    def active(self) -> int:
        return self.rpc.view(self.book, "activeCount()", ["uint256"])[0]

    def active_window(self) -> int:
        return self.rpc.view(self.book, "ACTIVE_WINDOW()", ["uint256"])[0]

    def standing(self, who: str) -> dict:
        r = self.rpc.view
        rep, open_, cap = (r(self.book, f"{f}(address)", ["uint256"], who)[0]
                           for f in ("reputation", "openClaims", "capOf"))
        base = r(self.book, "REP_BASE()", ["uint256"])[0]
        mult = r(self.book, "REP_MULT()", ["uint256"])[0]
        return {"reputation": rep, "openClaims": open_, "cap": cap, "repBase": base, "repMult": mult,
                "room": max(cap - open_, 0), "active": r(self.book, "isActive(address)", ["bool"], who)[0]}

    def claims(self, who: str) -> list:
        """The solver's open claims: the submissions whose ClaimOpened has no ClaimClosed, with their bounty, amount
        and Panels status."""
        topic_who = "0x" + who.lower()[2:].rjust(64, "0")
        opened, closed = {}, set()
        for name, sig in BOOK_EVENTS.items():
            for log in self.rpc.logs(self.book, self.from_block(), [_topic(sig), None, topic_who]):
                sid = int(log["topics"][1], 16)
                if name == "ClaimOpened":
                    opened[sid] = int(log["data"][2:66], 16)
                else:
                    closed.add(sid)
        out = []
        for sid in sorted(set(opened) - closed):
            sub = self.chain.submission(sid)
            ver = self.chain.verdict(sid)
            out.append({"submission": sid, "bounty": sub["bounty"], "amount": opened[sid],
                        "status": v3.STATUS[ver["status"]], "pass": ver["pass"],
                        "outcome": v3.RACE_OUTCOMES[sub["outcome"]]})
        return out

    # ----- the race -----

    def check_deposit(self) -> int:
        """What a fix posts now (micro-coins): the flat judges' fee if the deployment set one, else FeesV3's worst case
        for K_MAX judges at today's prices (the taxi fare)."""
        fee = self.chain.config()["judgeFee"]
        return fee if fee else self.rpc.view(self.chain.fees, "maxDeposit(bytes32,uint256)", ["uint256"],
                                             self.chain.repo(), K_MAX)[0]

    def state(self, b: int) -> str:
        return v3.RACE_STATES[self.chain.bounty(b)["state"]]

    def claim_now(self, b: int) -> int:
        """The claim a submission would open now (micro-coins): the price on offer, as `_submit` judges it."""
        judged = self.rpc.view(self.address, "lockedPrice(uint256)", ["uint256"], b)[0] * 10**6 // self.unit()
        return judged or 1

    def head(self) -> str:
        from oracle import radicle

        return radicle.sha_of(self.chain.head())


# ---------- the fee coin: balance and allowance, said out loud ----------

def ensure_allowance(rc: RaceV3, w, need_micro: int, what: str) -> list:
    """Before `what` takes `need_micro` micro-coins: the wallet must hold them (else nothing is sent), and RaceV3 must
    be allowed to take them. If the allowance is short, it's approved (unlimited, as pofctl's v2 commands approve),
    and the line returned says so."""
    need = rc.units(need_micro)
    if need == 0:
        return []
    have = rc.chain.balance(w.address)
    if have < need:
        hint = f" ({FAUCET_HINT})" if rc.chain_id() == SEPOLIA else \
            " (`pofctl faucet`, or `pofctl coin mint` on a devnet's mock coin)"
        raise Fail(f"{w.address} holds {fmt(rc.micro(have))} of the fee coin {rc.coin}; {what} needs {fmt(need_micro)}"
                   f"{hint}. Nothing was sent.")
    allowed = rc.chain.allowance(w.address, rc.address)
    if allowed >= need:
        return [f"the race may already take {fmt(need_micro)} of the fee coin from {w.address} (allowance "
                f"{'unlimited' if allowed > 2**200 else fmt(rc.micro(allowed))})"]
    w.send(rc.coin, "approve(address,uint256)", rc.address, MAX)
    return [f"approved RaceV3 {rc.address} to take the fee coin {rc.coin} from {w.address}: {what} needs "
            f"{fmt(need_micro)} and the allowance was {fmt(rc.micro(allowed))}. The approval is unlimited, as pofctl's "
            f"v2 commands set it; revoke it with approve({rc.address}, 0) on the coin"]


def _send(w, to: str, sig: str, *args) -> dict:
    try:
        return w.send(to, sig, *args)
    except Reverted as e:
        raise Fail(f"{sig.split('(')[0]} reverted: {explain(e)}") from None


# ---------- commands ----------

def cmd_status(ctx, a) -> tuple:
    rc: RaceV3 = ctx.v3
    c = rc.chain
    who = checksum(a.address) if a.address else ctx.wallet("solver").address
    st = rc.standing(who)
    claims = rc.claims(who)
    deposit, cfg = rc.check_deposit(), c.config()
    active = rc.active()
    data = {"version": 3, "chainId": rc.chain_id(), "block": rc.rpc.block(), "race": rc.address, "coin": rc.coin,
            "repo": "0x" + c.repo().hex(), "head": rc.head(), "rid": rc.record.get("rid", ""),
            "solver": who, **st, "claims": claims, "checkDeposit": deposit, "judgeFee": cfg["judgeFee"],
            "refunded": cfg["judgeFee"] == 0, "activeSolvers": active, "pledgesOpen": active >= ACTIVE_SOLVERS_MIN,
            "wallet": c.balance(who), "allowance": c.allowance(who, rc.address), "credit": c.owed(who)}
    lines = [f"chain {data['chainId']}, block {data['block']}: RaceV3 {rc.address} (v3)",
             f"  repository     0x{c.repo().hex()[:12]}… {data['rid']}, Heads.head {data['head']}",
             f"  fee coin       {rc.coin}" + (" (the test coin POFTEST, no value; `pofctl faucet`)"
                                               if data["chainId"] == SEPOLIA else ""),
             f"  active solvers {active}: pledges {'open' if data['pledgesOpen'] else 'refused'} "
             f"(at least {ACTIVE_SOLVERS_MIN}, each active for {rc.active_window() / 604800:g} weeks after a fix of it "
             f"is merged)",
             f"solver {who}{' (active)' if st['active'] else ''}",
             f"  cap            {fmt(st['cap'])} = REP_BASE {fmt(st['repBase'])} + {st['repMult']} x reputation "
             f"{fmt(st['reputation'])}",
             f"  open claims    {fmt(st['openClaims'])} in {len(claims)} submission(s); room for {fmt(st['room'])} "
             f"more (a commit over the cap is refused and costs nothing)"]
    for cl in claims:
        lines.append(f"    submission {cl['submission']} on bounty {cl['bounty']}: {fmt(cl['amount'])}, "
                     f"{cl['status']}{', passed' if cl['pass'] else ''}, outcome {cl['outcome']}")
    if cfg["judgeFee"] == 0:
        lines.append(f"  a fix posts    {fmt(deposit)}: FeesV3's maxDeposit, the meter's worst case for {K_MAX} judges at "
                     f"today's prices. Its judges are paid by the meter and the rest is refunded to you after the "
                     f"verdict, pass or fail (the taxi fare: no attempt, evaluation or appeal fee)")
    else:
        lines.append(f"  a fix pays     a flat judges' fee of {fmt(deposit)}, not refunded (its rest goes to the "
                     f"sponsors' pool)")
    lines.append(f"  wallet         {fmt(rc.micro(data['wallet']))}, credit in the race {fmt(rc.micro(data['credit']))}, "
                 f"allowance to the race "
                 f"{'unlimited' if data['allowance'] > 2**200 else fmt(rc.micro(data['allowance']))}")
    return data, lines


def cmd_register(ctx, a) -> tuple:
    """A Radicle issue registered on-chain: the registration fee, the issue stake and its registration check's
    deposit. The check reads the Radicle issue's claim (`Registration: N`, `Reporter wallet: 0x…`, bot/logic's
    format), so those two lines go on the issue, as a comment."""
    rc: RaceV3 = ctx.v3
    rad_issue = (a.rad_issue or "").strip().lower()
    if not RAD_ISSUE_RE.match(rad_issue):
        raise Fail(f"--rad-issue is the Radicle issue's id (hex, as `rad issue list` shows it), not {a.rad_issue!r}")
    rid = a.rid or rc.record.get("rid", "")
    if a.comment and not rid:
        raise Fail("--comment needs the repository's RID (--rid, or `rid` in the record)")
    w = ctx.wallet("reporter")
    cfg = rc.chain.config()
    deposit = rc.rpc.view(rc.chain.fees, "maxDeposit(bytes32,uint256)", ["uint256"], rc.chain.repo(), K_MAX)[0]
    need = cfg["registrationFee"] + cfg["issueStake"] + deposit
    lines = ensure_allowance(rc, w, need, "the registration")
    receipt = _send(w, rc.address, "register(bytes32,bool)", rc.chain.repo(), bool(a.hidden))
    log = _log_of(receipt, v3.REGISTERED)
    issue = int(log["topics"][1], 16)
    check = int(log["data"][2:66], 16)
    paste = logic.claim_lines(issue, w.address)
    message = "\n".join(paste)
    cmd = ["rad", "issue", "comment", "--repo", rid or "<RID>", rad_issue, "--message", message]
    data = {"issue": issue, "check": check, "reporter": w.address, "radIssue": rad_issue, "rid": rid, "lines": paste,
            "paid": {"registrationFee": cfg["registrationFee"], "issueStake": cfg["issueStake"], "deposit": deposit},
            "commented": False}
    lines += [f"{w.role} registered on-chain issue {issue} for the Radicle issue {rad_issue[:12]}: paid the registration "
              f"fee {fmt(cfg['registrationFee'])}, staked {fmt(cfg['issueStake'])}, and posted its registration check "
              f"(submission {check})'s deposit {fmt(deposit)}; the check's unused deposit is refunded"]
    if a.comment:
        _rad(a.rad_exec, cmd, "comment on the Radicle issue")
        data["commented"] = True
        lines.append(f"commented the claim on the Radicle issue {rad_issue[:12]} ({rid}):")
        lines += ["", *paste, ""]
    else:
        lines += ["the registration check reads the claim on the Radicle issue: comment these two lines on it, each on "
                  "its own line:", "", *paste, "", "  " + shlex.join(cmd)]
    lines.append(f"once the check is final, anyone opens the bounty: pofctl --v3 issue open --issue {issue}")
    return data, lines


def _rad(prefix: str | None, argv: list, what: str) -> str:
    """Runs a `rad` command on the Radicle node `prefix` reaches (e.g. `docker exec -i <name>`; none: this machine)."""
    try:
        r = subprocess.run(shlex.split(prefix or "") + argv, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail(f"{what}: {e}") from None
    if r.returncode:
        raise Fail(f"{what}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout


def cmd_open(ctx, a) -> tuple:
    rc: RaceV3 = ctx.v3
    w = ctx.wallet("reporter")
    receipt = _send(w, rc.address, "openBounty(uint256)", a.issue)
    b = int(_log_of(receipt, "BountyOpened(uint256,uint256)")["topics"][1], 16)
    return {"issue": a.issue, "bounty": b}, [f"issue {a.issue}'s registration check passed: bounty {b} is open"]


def cmd_pledge(ctx, a) -> tuple:
    """L6: below 3 active solvers the pledge is refused with the count, before anything is sent (no approval, no
    transaction). Unfunded bounties are still raced."""
    rc: RaceV3 = ctx.v3
    active = rc.active()
    if active < ACTIVE_SOLVERS_MIN:
        raise Fail(f"active solvers: {active} of the {ACTIVE_SOLVERS_MIN} needed. Pledges are refused while fewer "
                   f"than {ACTIVE_SOLVERS_MIN} solvers are active (an identity is active for "
                   f"{rc.active_window() / 604800:g} weeks after a fix of it is merged); bounties are still raced "
                   f"unfunded meanwhile. Nothing was sent.")
    state = rc.state(a.bounty)
    if state != "Open":
        raise Fail(f"bounty {a.bounty} is {state}: pledges go to an open bounty. Nothing was sent.")
    amount = int(round(a.amount * 10**6))
    if amount <= 0:
        raise Fail("--amount must be above 0")
    w = ctx.wallet("funder")
    lines = [f"active solvers: {active} (pledges open at {ACTIVE_SOLVERS_MIN})"]
    lines += ensure_allowance(rc, w, amount, "the pledge")
    _send(w, rc.address, "pledge(uint256,uint256)", a.bounty, rc.units(amount))
    held = rc.micro(rc.rpc.view(rc.address, "held(uint256,address)", ["uint256"], a.bounty, rc.coin)[0])
    lines.append(f"{w.role} pledged {fmt(amount)} to bounty {a.bounty}; it holds {fmt(held)}")
    return {"bounty": a.bounty, "pledged": amount, "held": held, "activeSolvers": active, "funder": w.address}, lines


def patch_messages(title: str, body: str) -> list:
    """The patch's title, then each line of the claim as its own `patch.message` (a push option can't hold a newline;
    Radicle joins them into the description, one paragraph each, and the claim is read line by line)."""
    return [title] + [x for x in body.splitlines() if x.strip()]


def cmd_submit(ctx, a) -> tuple:
    """A fix sealed on-chain: keccak256(abi.encode(fix, base, salt, solver)), with its deposit (the taxi fare). The fix
    is then opened as a Radicle patch whose description carries the claim (bounty, submission, salt, solver: the bot's
    pull request format, which the validators' nodes read from their own Radicle node)."""
    rc: RaceV3 = ctx.v3
    fix_sha = commit_sha(a.patch, "--patch (the patch revision's head commit)")
    head = rc.head()
    base_sha = commit_sha(a.base, "--base") if a.base else head
    if base_sha != head:
        raise Fail(f"the fix's base {base_sha[:12]} isn't Heads.head {head[:12]}: validators refuse a patch on another "
                   f"base, and the merge would revert (stale base). Rebase it onto {head}. Nothing was sent.")
    state = rc.state(a.bounty)
    if state != "Open":
        raise Fail(f"bounty {a.bounty} is {state}: a fix is sealed on an open bounty. Nothing was sent.")
    w = ctx.wallet("solver")
    st = rc.standing(w.address)
    claim = rc.claim_now(a.bounty)
    if st["openClaims"] + claim > st["cap"]:
        raise Fail(f"the fix would claim {fmt(claim)} (bounty {a.bounty}'s price on offer), and {w.address}'s open "
                   f"claims are {fmt(st['openClaims'])} of its cap {fmt(st['cap'])}: the commit would be refused "
                   f"(D29). Wait for a claim to close, or build reputation on smaller bounties. Nothing was sent.")
    deposit = rc.check_deposit()
    lines = ensure_allowance(rc, w, deposit, "the fix's deposit")
    salt = salt_of(a.salt)
    fix, base = v2.commit_word(fix_sha), v2.commit_word(base_sha)
    sealed = v3.fix_commitment(fix, base, salt, w.address)
    receipt = _send(w, rc.address, "commit(uint256,bytes32)", a.bounty, sealed)
    s = int(_log_of(receipt, v3.COMMITTED)["topics"][2], 16)
    sub = rc.chain.submission(s)
    issue = a.issue if a.issue is not None else rc.chain.bounty(a.bounty)["issue"]
    body = logic.pr_body(issue, a.bounty, s, "0x" + salt.hex(), w.address)
    title = a.title or f"Fix for bounty {a.bounty}"
    msgs = patch_messages(title, body)
    push = ["git", "push", "rad", f"{fix_sha}:refs/patches"] + [x for m in msgs for x in ("-o", f"patch.message={m}")]
    claim_cmd = (f"pofctl --v3 claim --bounty {a.bounty} --patch {fix_sha} --base {base_sha} --salt 0x{salt.hex()}")
    data = {"bounty": a.bounty, "submission": s, "fix": fix_sha, "base": base_sha, "salt": "0x" + salt.hex(),
            "commitment": "0x" + sealed.hex(), "solver": w.address, "deposit": sub["deposit"],
            "claim": rc.chain.verdict(s)["bounty"], "patchBody": body, "patchMessages": msgs,
            "patchCommand": shlex.join(push), "claimCommand": claim_cmd}
    lines += [f"{w.role} sealed submission {s} on bounty {a.bounty}: commit {fix_sha[:12]} on Heads.head "
              f"{base_sha[:12]}, a claim of {fmt(data['claim'])}, deposit {fmt(rc.micro(sub['deposit']))} (the meter's "
              f"worst case; the rest is refunded after the verdict)",
              "open the Radicle patch from your working copy of the repository, with the claim in its description "
              "(the salt lets the drawn validators open the seal; their nodes read the patch from their own Radicle "
              "node and take only a revision whose head is the commit and whose base is Heads.head):",
              "", "  " + shlex.join(push), "",
              "its description must carry these lines, each on its own line:", "", *body.splitlines(), "",
              f"if your fix wins, claim it (anyone holding these values can): {claim_cmd}"]
    return data, lines


def cmd_claim(ctx, a) -> tuple:
    """The winner's seal opened: its award starts (the head moves only at finality, `merge`)."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    fix_sha, base_sha = commit_sha(a.patch, "--patch"), commit_sha(a.base, "--base")
    salt = salt_of(a.salt)
    bt = c.bounty(a.bounty)
    state = v3.RACE_STATES[bt["state"]]
    if state != "Won":
        raise Fail(f"bounty {a.bounty} is {state}: a claim opens a won bounty's winning seal. Nothing was sent.")
    s = bt["winner"]
    sub = c.submission(s)
    fix, base = v2.commit_word(fix_sha), v2.commit_word(base_sha)
    if v3.fix_commitment(fix, base, salt, sub["solver"]) != v3.b32(sub["commitment"]):
        raise Fail(f"the winning submission {s}'s seal doesn't open to commit {fix_sha[:12]} on base {base_sha[:12]} "
                   f"with that salt and its solver {sub['solver']}. Nothing was sent.")
    w = ctx.wallet("solver")
    _send(w, rc.address, "claim(uint256,bytes32,bytes32,bytes32)", a.bounty, fix, base, salt)
    ver = c.verdict(s)
    data = {"bounty": a.bounty, "submission": s, "fix": fix_sha, "base": base_sha, "status": v3.STATUS[ver["status"]],
            "finalAt": ver["finalAt"], "state": rc.state(a.bounty)}
    when = (f"at chain time {ver['finalAt']} (in {max(ver['finalAt'] - c.now(), 0) / 3600:,.1f} h)"
            if ver["finalAt"] else "once its verdict is final")
    return data, [f"{w.role} claimed bounty {a.bounty} with submission {s}: its award started",
                  f"the head moves to {fix_sha[:12]} only at finality (L9): pofctl --v3 merge --bounty {a.bounty} "
                  f"{when}; its instalments are paid from the merge"]


def cmd_merge(ctx, a) -> tuple:
    """L9: once the claimed fix's verdict is final and still a pass, anyone moves Heads to it."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    bt = c.bounty(a.bounty)
    state = v3.RACE_STATES[bt["state"]]
    if state != "Merged":
        raise Fail(f"bounty {a.bounty} is {state}: merge takes a claimed fix (a won bounty's winner claims it first). "
                   "Nothing was sent.")
    aw = c.award(a.bounty, bt["epoch"])
    if aw["merged"]:
        return ({"bounty": a.bounty, "merged": True, "already": True, "head": rc.head()},
                [f"bounty {a.bounty}'s fix is already merged: Heads.head is {rc.head()}"])
    ver = c.verdict(aw["sub"])
    if ver["status"] != v3.FINAL:
        left = max(ver["finalAt"] - c.now(), 0) if ver["finalAt"] else None
        when = f"; final at chain time {ver['finalAt']} (in {left / 3600:,.1f} h)" if left is not None else ""
        raise Fail(f"not yet: submission {aw['sub']}'s verdict is {v3.STATUS[ver['status']]}, not Final{when}. The "
                   f"head moves only at finality (L9). Nothing was sent.")
    before = rc.head()
    sub = c.submission(aw["sub"])
    base = v3.b32(sub["base"])[:20].hex()
    if base != before:
        raise Fail(f"the fix's base {base[:12]} isn't Heads.head {before[:12]} any more (a stale base): merge would "
                   f"revert. The winner keeps its place until the merge deadline. Nothing was sent.")
    w = ctx.wallet("solver")
    _send(w, rc.address, "merge(uint256)", a.bounty)
    after = rc.head()
    data = {"bounty": a.bounty, "submission": aw["sub"], "merged": True, "already": False, "from": before, "head": after,
            "solver": aw["winner"]}
    rid = rc.record.get("rid", "<RID>")
    return data, [f"merged bounty {a.bounty}: Heads.head {before[:12]} -> {after[:12]} (submission {aw['sub']}, "
                  f"winner {aw['winner']}); the winner's claim closed into its reputation",
                  f"the seated validators push Radicle's canonical main to it; check: pofctl --v3 verify-head --rid "
                  f"{rid} --rad-exec '<your node>'"]


def cmd_withdraw(ctx, a) -> tuple:
    """The credit the race holds for this key (refunded deposits' rest, instalments, a stake back) to its wallet."""
    rc: RaceV3 = ctx.v3
    w = ctx.wallet(a.role)
    owed = rc.chain.owed(w.address)
    if owed:
        _send(w, rc.address, "withdraw(address,address)", rc.coin, w.address)
    return ({"account": w.address, "withdrawn": owed},
            [f"{w.role} withdrew {fmt(rc.micro(owed))} of credit (refunds, instalments, stakes back) to its wallet"])


def _utc(ts: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _wait(seconds: int) -> str:
    h, m = divmod(max(seconds, 0) // 60, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def cmd_faucet(ctx, a) -> tuple:
    """The test coin's faucet (L17): claims CLAIM_AMOUNT for the caller's key and prints the next claim time; a claim
    before it is refused here, sending nothing. `--when` only shows the time."""
    rc: RaceV3 = ctx.v3
    faucet = rc.faucet()
    w = ctx.wallet(a.role)
    r = rc.rpc.view
    amount, interval = (r(faucet, f"{f}()", ["uint256"])[0] for f in ("CLAIM_AMOUNT", "CLAIM_INTERVAL"))
    now = int(rc.rpc.call("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)
    nxt = r(faucet, "nextClaim(address)", ["uint256"], w.address)[0]
    data = {"faucet": faucet, "coin": rc.coin, "account": w.address, "claimAmount": amount,
            "claimInterval": interval, "now": now}
    rule = f"{fmt(amount)} coins a claim, one claim per address every {interval / 3600:g} h"
    if a.when or now < nxt:
        data.update(claimed=0, nextClaim=max(nxt, now), balance=rc.chain.balance(w.address))
        when = "now" if now >= nxt else f"at {_utc(nxt)} (in {_wait(nxt - now)})"
        if not a.when:
            raise Fail(f"{w.address} may claim from the faucet {faucet} again {when} ({rule}). Nothing was sent.")
        return data, [f"{w.address} may claim from the faucet {faucet} {when} ({rule})",
                      f"  balance        {fmt(rc.micro(data['balance']))} of the test coin {rc.coin}"]
    receipt = _send(w, faucet, "claim()")
    nxt = r(faucet, "nextClaim(address)", ["uint256"], w.address)[0]
    data.update(claimed=amount, nextClaim=nxt, balance=rc.chain.balance(w.address), tx=receipt.get("transactionHash"))
    return data, [f"{w.role} {w.address} claimed {fmt(rc.micro(amount))} test coins from the faucet {faucet}",
                  f"  balance        {fmt(rc.micro(data['balance']))} of the test coin {rc.coin} (no value)",
                  f"  next claim     at {_utc(nxt)} (in {_wait(nxt - now)}; {rule})"]


# ---------- Radicle: verify-head and checkout ----------

def _rid(rc: RaceV3, rid: str | None) -> str:
    from oracle import radicle

    rid = rid or rc.record.get("rid", "")
    if not rid:
        raise Fail("--rid: the repository's Radicle id (or `rid` in the deployment record)")
    if not radicle.RID_RE.match(rid):
        raise Fail(f"not a Radicle RID: {rid!r}")
    if radicle.repo_id(rid) != rc.chain.repo():
        raise Fail(f"{rid} isn't this deployment's repository (keccak256 of it isn't RaceV3.repo "
                   f"0x{rc.chain.repo().hex()})")
    return rid


def cmd_verify_head(ctx, a) -> tuple:
    """Radicle's canonical main (or a mirror's main given by --commit) is Heads.head of the race's one repository."""
    from oracle import radicle

    rc: RaceV3 = ctx.v3
    head = rc.head()
    repo = rc.chain.repo()
    if a.commit and not a.rid:
        canonical = commit_sha(a.commit, "--commit")
        d = (radicle.Decision(radicle.SIGN, f"{canonical} is Heads' head") if canonical == head else
             radicle.Decision(radicle.REFUSE, f"{canonical} isn't Heads' head {head}"))
        rid = ""
    else:
        rid = _rid(rc, a.rid)
        try:
            snap = radicle.Radicle(rid, shlex.split(a.rad_exec or ""), a.repo_dir or "").snapshot()
        except radicle.Unavailable as e:
            raise Fail(str(e)) from None
        d = radicle.verify_head(head, snap)
        canonical = radicle.canonical(snap)
    if d.action != radicle.SIGN:
        raise Fail(f"verify-head refused: {d.reason}")
    return ({"repo": "0x" + repo.hex(), "rid": rid, "head": head, "canonical": canonical, "match": True},
            [f"repository 0x{repo.hex()[:12]}{' (' + rid + ')' if rid else ''}: {d.reason}"])


CHECKOUT = r"""set -u
S="${RAD_HOME:-$HOME/.radicle}/storage/%(store)s"
have() { git --git-dir "$S" cat-file -e "%(head)s^{commit}" 2>/dev/null; }
if ! have; then
  if command -v timeout >/dev/null; then timeout 60 rad sync --fetch %(rid)s >/dev/null 2>&1 || true
  else rad sync --fetch %(rid)s >/dev/null 2>&1 || true; fi
fi
have || { echo "@missing %(head)s"; exit 4; }
d=%(dir)s
if [ -e "$d" ] && [ -n "$(ls -A "$d" 2>/dev/null)" ]; then echo "@exists $d"; exit 5; fi
git init -q "$d" && git -C "$d" fetch -q "$S" %(head)s && git -C "$d" checkout -q --detach FETCH_HEAD || exit 6
echo "@dir $(cd "$d" && pwd)"
echo "@head $(git -C "$d" rev-parse HEAD)"
echo "@ns $(git --git-dir "$S" for-each-ref --contains %(head)s --format='%%(refname)' refs/namespaces | sed -n 's#^refs/namespaces/\([^/]*\)/.*#\1#p' | sort -u | tr '\n' ' ')"
"""


def cmd_checkout(ctx, a) -> tuple:
    """The commit Heads.head names, from whichever namespace of the node's copy has it (synced first if none does),
    checked out by its hash into a new directory on that node: (b)'s reader, which trusts the chain, not `main`."""
    rc: RaceV3 = ctx.v3
    rid = _rid(rc, a.rid)
    head = rc.head()
    target = a.dir or f"pof-checkout-{head[:12]}"
    script = CHECKOUT % {"store": rid[4:], "rid": shlex.quote(rid), "head": head, "dir": shlex.quote(target)}
    try:
        r = subprocess.run(shlex.split(a.rad_exec or "") + ["bash", "-c", script], capture_output=True, text=True,
                           timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail(f"checkout: {e}") from None
    got = dict(re.findall(r"^@(\w+) ?(.*)$", r.stdout, re.M))
    if r.returncode == 4:
        raise Fail(f"checkout: Heads.head {head} isn't on the node's copy of {rid}, even after a sync")
    if r.returncode == 5:
        raise Fail(f"checkout: {target} exists and isn't empty; give a new --dir")
    if r.returncode or got.get("head") != head:
        raise Fail(f"checkout failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}")
    ns = got.get("ns", "").split()
    return ({"rid": rid, "head": head, "dir": got.get("dir", target), "namespaces": ns},
            [f"checked out Heads.head {head} of {rid} into {got.get('dir', target)} (detached), from the namespaces "
             f"{', '.join(n[:16] + '…' for n in ns) or 'none'}",
             "this is the judged code whatever Radicle's main says; pofctl --v3 verify-head checks main against it"])


V3_ONLY = {"issue", "pledge", "submit", "claim", "merge", "checkout", "faucet"}
