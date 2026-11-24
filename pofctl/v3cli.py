"""pofctl on v3 and Radicle (proof-of-fix#251 task 4.4; design L6, L9, L12, L17; ADR 0007): the reporter, the funder
and the solver of a v3 race whose one repository lives on Radicle, as they play on Sepolia.

    pofctl --v3 status [--address 0x…]                  the solver's cap, open claims, the deposit a fix posts, the
                                                        reporter's registrations and the ETH for gas (no password)
    pofctl --v3 issue register --rad-issue <id>         register a Radicle issue on-chain (fee, stake, its check)
    pofctl --v3 issue register --title T --description D   v3.1: open the Radicle issue too, then register it
    pofctl --v3 issue show --issue N                    v3.1: a registration's check: status, panel, deadlines, deposit
    pofctl --v3 draw <check>                            v3.1: draw a check's panel that no validator drew (any key)
    pofctl --v3 issue open --issue N                    open its bounty once its registration check is final
    pofctl --v3 pledge --bounty B --amount X            fund it: refused below 3 active solvers, before anything is sent
    pofctl --v3 attempt --bounty B                      v3.1: record an attempt (the first locks the share of the price)
    pofctl --v3 submit --bounty B --patch <commit>      seal a fix; prints how to open its Radicle patch
    pofctl --v3 claim --bounty B --patch <c> --base <c> --salt 0x…   the winner opens its seal
    pofctl --v3 merge --bounty B                        at finality, anyone moves Heads to the fix (L9)
    pofctl --v3 rebase --bounty B --patch <commit>      v3.1: a won fix whose base went stale, rebased in place (#310)
    pofctl --v3 verify-head [--rid … --rad-exec …]      Radicle's canonical main is Heads.head
    pofctl --v3 verify-delegates [--rid … --rad-exec …] the identity's delegates are the seats' nodes on-chain
    pofctl --v3 checkout [--rid … --rad-exec …]         the commit Heads.head names, from any namespace
    pofctl --v3 withdraw --role solver                  the refunded deposits' rest and other credit, to the wallet
    pofctl faucet [--when]                              claim 20 test coins for your key (one claim every 2 hours)

The commands that only v3 has (issue, draw, attempt, pledge, submit, claim, merge, checkout, faucet) select v3 by themselves; a v3
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
import time

from oracle import v2, v3
from oracle.abi import selector
from oracle.crypto import checksum, keccak256

from bot import logic

from .race import fmt
from .rpc import Reverted

# RaceV3's: a fix's deposit is FeesV3's worst case for Panels' `kTop` judges (k is fixed only at the draw; #251 batch 4,
# L24: 3 on Sepolia, 7 by default), read from the deployment (`Chain.panel_rules`).
ACTIVE_SOLVERS_MIN = 3  # SolverBook.ACTIVE_SOLVERS_MIN (launch L6)
MAX = 2**256 - 1
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RAD_ISSUE_RE = re.compile(r"^[0-9a-f]{7,40}$")  # a Radicle issue's collaborative-object id, or a unique prefix
SEPOLIA = 11155111
FAUCET_HINT = "claim 20 test coins every 2 hours with `pofctl faucet`"
# v3.1 polish VP17 (S1): after an approval, the allowance is read back until a provider's node shows it, so the next
# estimate isn't answered by a node that hasn't seen the approval yet
APPROVAL_POLL_S, APPROVAL_WAIT_S = 2, 60
REPORT_WINDOW_S = 86_400  # RaceV3Base.REPORT_WINDOW: a panel's reports are due this long after its reveal deadline
ETH_HINT_WEI = 10**16  # VP11: about 0.01 Sepolia ETH covers every step
DRAW_HINT_MINUTES = 10  # VP11: the hint `issue register` and `submit` print
ISSUE_STATES = ["None", "Posted", "Rewarded", "Returned", "Forfeited"]  # RaceV3Base.IssueState
_sleep, _clock = time.sleep, time.monotonic  # the approval wait's (tests replace them)

# RaceV3's and SolverBook's errors, by selector, as a reader would want them explained.
_ERRORS = {
    "TooFewActiveSolvers(uint256)": "pledges are refused while fewer than 3 solvers are active",
    "OverCap(address,uint256,uint256)": "the claim doesn't fit the solver's cap (D29)",
    "WrongState(uint256,uint8)": "the bounty isn't in the state this needs",
    "NotYet()": "not yet",
    "Refused()": "refused by the race",
    "AppealClosed()": "the appeal window is closed",
    "BadParams()": "bad parameters",
    "ERC20InsufficientAllowance(address,uint256,uint256)": "the race's allowance on the fee coin is short (a provider's "
                                                           "node may not have seen the approval yet)",
    "ERC20InsufficientBalance(address,uint256,uint256)": "the wallet holds too little of the fee coin",
    "NothingChanged()": "nothing changed since the check began waiting (the registry, or its retry time)",
    "WrongStatus()": "the check isn't in the status this needs",
}
COUNTED = ("Held", "Window", "Final")  # a counted verdict: its pass or fail is known
ALLOWANCE_SHORT = selector("ERC20InsufficientAllowance(address,uint256,uint256)").hex()
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
        self.chain = v3.Chain(rpc, record.get("race") or (record.get("addresses") or {}).get("race"),
                              first_block=int(record.get("block", 0)))  # scans start at the deployment's block (#312)
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
                        "outcome": v3.RACE_OUTCOMES[sub["outcome"]], "rebaseOf": sub.get("rebaseOf", 0)})
        return out

    # ----- the race -----

    def check_deposit(self) -> int:
        """What a fix posts now (micro-coins): the flat judges' fee if the deployment set one, else FeesV3's worst case
        for Panels' `kTop` judges at today's prices (the taxi fare)."""
        fee = self.chain.config()["judgeFee"]
        return fee if fee else self.rpc.view(self.chain.fees, "maxDeposit(bytes32,uint256)", ["uint256"],
                                             self.chain.repo(), self.k_top())[0]

    def k_top(self) -> int:
        """Panels' largest issue-tier panel (#251 batch 4, L24): a check's deposit is priced for this many judges."""
        return self.chain.panel_rules()["kTop"]

    def state(self, b: int) -> str:
        return v3.RACE_STATES[self.chain.bounty(b)["state"]]

    def claim_now(self, b: int) -> int:
        """The claim a submission would open now (micro-coins): the price on offer, as `_submit` judges it."""
        judged = self.rpc.view(self.address, "lockedPrice(uint256)", ["uint256"], b)[0] * 10**6 // self.unit()
        return judged or 1

    def head(self) -> str:
        from oracle import radicle

        return radicle.sha_of(self.chain.head())

    def rebases_of(self, who: str) -> list:
        """v3.1 (#310): the rebase checks `who` submitted, or that rebase a fix `who` won (`by`: its own)."""
        out = []
        for e in self.chain.rebased(self.from_block()):
            mine = self.chain.submission(e["submission"])["solver"].lower() == who.lower()
            if mine or self.chain.submission(e["original"])["solver"].lower() == who.lower():
                out.append({**e, "fix": "0x" + e["fix"].hex(), "base": "0x" + e["base"].hex(), "by": mine})
        return out

    def registrations(self, who: str) -> list:
        """VP17 (S3): the issues `who` registered (RaceV3's Registered with that reporter), each with its check's
        status."""
        topics = [_topic(v3.REGISTERED), None, "0x" + who.lower()[2:].rjust(64, "0")]
        out = []
        for log in self.rpc.logs(self.address, self.from_block(), topics):
            issue, check = int(log["topics"][1], 16), int(log["data"][2:66], 16)
            ver = self.chain.verdict(check)
            out.append({"issue": issue, "check": check, "status": v3.STATUS[ver["status"]], "pass": ver["pass"],
                        "state": ISSUE_STATES[self.chain.issue(issue)["state"]]})
        return out

    def head_moved_at(self) -> int:
        """When Heads.head last moved (its record's `movedAt`): a third party may rebase REBASE_GRACE after it."""
        return self.rpc.view(self.chain.heads, "head(bytes32)", [v3.HEAD], self.chain.repo())[0][2]


# ---------- the fee coin: balance and allowance, said out loud ----------

def _check_balance(rc: RaceV3, w, need_micro: int, what: str) -> None:
    """The wallet must hold `need_micro` micro-coins before `what` (else nothing is sent)."""
    have = rc.chain.balance(w.address)
    if have < rc.units(need_micro):
        hint = f" ({FAUCET_HINT})" if rc.chain_id() == SEPOLIA else \
            " (`pofctl faucet`, or `pofctl coin mint` on a devnet's mock coin)"
        raise Fail(f"{w.address} holds {fmt(rc.micro(have))} of the fee coin {rc.coin}; {what} needs {fmt(need_micro)}"
                   f"{hint}. Nothing was sent.")


def _await_allowance(rc: RaceV3, w, need: int) -> tuple:
    """VP17 (S1): reads the allowance every APPROVAL_POLL_S until it's at least `need` units, up to APPROVAL_WAIT_S:
    (seen, seconds waited)."""
    start = _clock()
    while True:
        if rc.chain.allowance(w.address, rc.address) >= need:
            return True, _clock() - start
        if _clock() - start >= APPROVAL_WAIT_S:
            return False, _clock() - start
        _sleep(APPROVAL_POLL_S)


def ensure_allowance(rc: RaceV3, w, need_micro: int, what: str, txs: list | None = None) -> list:
    """Before `what` takes `need_micro` micro-coins: the wallet must hold them (else nothing is sent), and RaceV3 must
    be allowed to take them. If the allowance is short, it's approved (unlimited, as pofctl's v2 commands approve),
    and the lines returned say so, with the approval's transaction. Then it waits until the chain shows the allowance
    (VP17, S1: a provider may answer the next estimate from a node that hasn't seen the approval yet)."""
    need = rc.units(need_micro)
    if need == 0:
        return []
    _check_balance(rc, w, need_micro, what)
    allowed = rc.chain.allowance(w.address, rc.address)
    if allowed >= need:
        return [f"the race may already take {fmt(need_micro)} of the fee coin from {w.address} (allowance "
                f"{'unlimited' if allowed > 2**200 else fmt(rc.micro(allowed))})"]
    t = _tx(w.send(rc.coin, "approve(address,uint256)", rc.address, MAX), "approve")
    if txs is not None:
        txs.append(t)
    lines = [f"approved RaceV3 {rc.address} to take the fee coin {rc.coin} from {w.address}: {what} needs "
             f"{fmt(need_micro)} and the allowance was {fmt(rc.micro(allowed))}. The approval is unlimited, as pofctl's "
             f"v2 commands set it; revoke it with approve({rc.address}, 0) on the coin", tx_line(t)]
    seen, waited = _await_allowance(rc, w, need)
    if not seen:
        lines.append(f"  the chain doesn't show the allowance after {waited:.0f} s; sending anyway (once more if it is "
                     f"refused for the allowance)")
    elif waited:
        lines.append(f"  waited {waited:.0f} s until the chain showed the allowance")
    return lines


def _tx(receipt: dict | None, what: str) -> dict:
    """A sent transaction as pofctl reports it (VP17, S2): what it was, its hash and its block."""
    receipt = receipt or {}
    n = receipt.get("blockNumber")
    return {"what": what, "tx": receipt.get("transactionHash"),
            "block": int(n, 16) if isinstance(n, str) else n}


def tx_line(t: dict) -> str:
    return f"  tx {t['tx']} in block {t['block']} ({t['what']})"


def with_txs(data: dict, txs: list) -> dict:
    """`tx` and `block` in a command's JSON: its one transaction's, or with several, the last one's (the command's
    own) and every one in `txs`, in the order sent."""
    if txs:
        data.update(tx=txs[-1]["tx"], block=txs[-1]["block"])
    if len(txs) > 1:
        data["txs"] = list(txs)
    return data


def _allowance_short(e: Reverted) -> bool:
    raw = (e.data or "").removeprefix("0x")
    return raw[:8] == ALLOWANCE_SHORT or "ERC20InsufficientAllowance" in (e.reason or "")


def _send(w, to: str, sig: str, *args, txs: list | None = None, paid: tuple | None = None) -> dict:
    """Sends, names a revert, and records the transaction in `txs`. `paid` = (the race, micro-coins): the send takes
    the fee coin, so a refusal for the allowance (a provider's node behind the approval, VP17 S1) is retried once after
    another wait for the allowance; refused again, it fails and nothing more is sent."""
    name = sig.split("(")[0]
    try:
        receipt = w.send(to, sig, *args)
    except Reverted as e:
        if paid is None or not _allowance_short(e):
            raise Fail(f"{name} reverted: {explain(e)}") from None
        rc, need_micro = paid
        _await_allowance(rc, w, rc.units(need_micro))
        try:
            receipt = w.send(to, sig, *args)
        except Reverted as e2:
            raise Fail(f"{name} reverted twice: {explain(e2)}. The approval went through, but the chain's provider still "
                       f"answered from a node that doesn't show it; run the command again in a minute (the allowance "
                       f"stays). Nothing more was sent.") from None
    t = _tx(receipt, name)
    if txs is not None:
        txs.append(t)
    return receipt


# ---------- commands ----------

def cmd_status(ctx, a) -> tuple:
    rc: RaceV3 = ctx.v3
    c = rc.chain
    who = ctx.view_address(a.address)  # VP11: --address, pofctl.json's, the keystore's; decrypted only without one
    st = rc.standing(who)
    claims = rc.claims(who)
    deposit, cfg = rc.check_deposit(), c.config()
    k_top = rc.k_top()
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
        what = f"rebase check {cl['submission']} of submission {cl['rebaseOf']}" if cl["rebaseOf"] else \
            f"submission {cl['submission']}"
        lines.append(f"    {what} on bounty {cl['bounty']}: {fmt(cl['amount'])}, "
                     f"{cl['status']}{', passed' if cl['pass'] else ''}, outcome {cl['outcome']}")
    rebases = rc.rebases_of(who)
    data["rebases"] = rebases
    for r in rebases:
        ver = c.verdict(r["submission"])
        lines.append(f"  rebase         check {r['submission']} of bounty {r['bounty']}'s fix (submission "
                     f"{r['original']}) onto {rebase_v3_sha(r['base'])[:12]}: {v3.STATUS[ver['status']]}"
                     f"{', passed' if ver['pass'] else ''}" + (" (by you)" if r["by"] else " (of your fix)"))
    if cfg["judgeFee"] == 0:
        lines.append(f"  a fix posts    {fmt(deposit)}: FeesV3's maxDeposit, the meter's worst case for {k_top} judges at "
                     f"today's prices. Its judges are paid by the meter and the rest is refunded to you after the "
                     f"verdict, pass or fail (the taxi fare: no attempt, evaluation or appeal fee)")
    else:
        lines.append(f"  a fix pays     a flat judges' fee of {fmt(deposit)}, not refunded (its rest goes to the "
                     f"sponsors' pool)")
    lines.append(f"  wallet         {fmt(rc.micro(data['wallet']))}, credit in the race {fmt(rc.micro(data['credit']))}, "
                 f"allowance to the race "
                 f"{'unlimited' if data['allowance'] > 2**200 else fmt(rc.micro(data['allowance']))}")
    eth = int(rc.rpc.call("eth_getBalance", [who, "latest"]), 16)
    data["eth"] = eth
    low = ""
    if eth < ETH_HINT_WEI:
        low = (" (about 0.01 Sepolia ETH covers every step)" if data["chainId"] == SEPOLIA else
               " (about 0.01 ETH covers every step)")
    lines.append(f"  ETH            {eth / 10**18:.6f} for gas{low}")
    regs = rc.registrations(who)
    data["registrations"] = regs
    if regs:
        lines.append(f"reporter {who}: {len(regs)} registration(s)")
        for r in regs:
            lines.append(f"  issue {r['issue']}  check {r['check']}: {r['status'].lower()}"
                         f"{', passed' if r['pass'] and r['status'] in COUNTED else ''}"
                         f"{', failed' if not r['pass'] and r['status'] in COUNTED else ''}, issue {r['state'].lower()}")
        lines.append("  each one's progress: pofctl --v3 issue show --issue <N>")
    return data, lines


RAD_ROW = re.compile(r"^\s*│\s*(\w+)\s+(.*?)\s*│\s*$")  # a row of Radicle 1.10.3's box: `│ Issue   <id>   │`


def rad_box(out: str) -> dict:
    """The rows of the box `rad issue open` and `rad issue show` print (Radicle 1.10.3): {"Title": …, "Issue": …}, the
    first of each name (the description's lines below them aren't `Name  value` rows the callers ask for)."""
    rows: dict = {}
    for line in out.splitlines():
        m = RAD_ROW.match(line)
        if m and m.group(1) not in rows:
            rows[m.group(1)] = m.group(2)
    return rows


def rad_issue_id(out: str) -> str:
    """The new issue's whole id from `rad issue open`'s output (its box's `│ Issue   <40 hex> │` row), or ""."""
    from oracle import radicle_v3 as RV

    iid = rad_box(out).get("Issue", "").split(" ")[0].strip().lower()
    return iid if RV.ISSUE_ID_RE.match(iid) else ""


def _open_rad_issue(a, rid: str) -> str:
    """VP11: `rad issue open` through --rad-exec, its id from the box, then checked with `rad issue show <id>`: the
    title must match. A mismatch is refused before any transaction."""
    out = _rad(a.rad_exec, ["rad", "issue", "open", "--repo", rid, "--title", a.title, "--description",
                            a.description or ""], "open the Radicle issue")
    iid = rad_issue_id(out)
    if not iid:
        raise Fail(f"`rad issue open` printed no issue id (its box's `Issue` row): {out.strip()[-300:]!r}. Find it "
                   f"with `rad issue list` and register it with --rad-issue <its whole id>. Nothing was sent.")
    shown = rad_box(_rad(a.rad_exec, ["rad", "issue", "show", iid, "--repo", rid], "read the Radicle issue back"))
    title = shown.get("Title", "")
    if " ".join(title.split()) != " ".join(a.title.split()):
        raise Fail(f"the Radicle issue {iid} that `rad issue open` named has the title {title!r}, not {a.title!r}: "
                   f"check `rad issue list` and register the right one with --rad-issue <its whole id>. Nothing was "
                   f"sent.")
    return iid


def draw_hint(check: int) -> str:
    return f"if no validator draws it within {DRAW_HINT_MINUTES} minutes: pofctl --v3 draw {check}"


def cmd_register(ctx, a) -> tuple:
    """A Radicle issue registered on-chain: the registration fee, the issue stake and its registration check's
    deposit. The check reads the Radicle issue's claim (`Registration: N`, `Reporter wallet: 0x…`, bot/logic's
    format, and `Claim signature: 0x…`), so those lines go on the issue, as a comment. The signature is the reporter's,
    by the key that registered (a keystore's or a devnet key, by the same rules), over radicle_v3.claim_digest: this
    chain, the race, the registration, the repository and the issue's whole id, so it holds on that issue only (#251
    L12, the owner's decision of 2026-11-20). v3.1 (VP11): `--title T --description D` opens the Radicle issue first
    (`rad issue open` through --rad-exec) and checks it with `rad issue show`, instead of `--rad-issue`."""
    from oracle import radicle as rad
    from oracle import radicle_v3 as RV

    rc: RaceV3 = ctx.v3
    opening = getattr(a, "title", None) is not None
    if opening == bool(a.rad_issue):
        raise Fail("name the Radicle issue with --rad-issue <its whole id>, or open it with --title T --description D "
                   "(one of the two)")
    rad_issue = ""
    if not opening:
        rad_issue = (a.rad_issue or "").strip().lower()
        if not RAD_ISSUE_RE.match(rad_issue):
            raise Fail(f"--rad-issue is the Radicle issue's id (hex, as `rad issue list` shows it), not {a.rad_issue!r}")
        if not RV.ISSUE_ID_RE.match(rad_issue):
            raise Fail(f"--rad-issue needs the issue's whole id (40 hex digits, as `rad issue list` or `rad cob list "
                       f"--type xyz.radicle.issue` shows it): the claim's signature names it, so a prefix ({rad_issue}) "
                       f"won't do")
    elif not a.title.strip():
        raise Fail("--title is the Radicle issue's title: not empty")
    rid = a.rid or rc.record.get("rid", "")
    if (a.comment or opening) and not rid:
        raise Fail(f"{'--title' if opening else '--comment'} needs the repository's RID (--rid, or `rid` in the record)")
    repo = rc.chain.repo()
    if rid and rad.repo_id(rid) != repo:
        raise Fail(f"{rid} isn't the race's repository (its keccak256 isn't the race's repo())")
    w = ctx.wallet("reporter")
    cfg = rc.chain.config()
    deposit = rc.rpc.view(rc.chain.fees, "maxDeposit(bytes32,uint256)", ["uint256"], rc.chain.repo(), rc.k_top())[0]
    need = cfg["registrationFee"] + cfg["issueStake"] + deposit
    lines = []
    if opening:
        _check_balance(rc, w, need, "the registration")  # before the Radicle issue is opened
        rad_issue = _open_rad_issue(a, rid)
        lines.append(f"opened the Radicle issue {rad_issue} ({a.title!r}) and read it back")
    txs: list = []
    lines += ensure_allowance(rc, w, need, "the registration", txs)
    receipt = _send(w, rc.address, "register(bytes32,bool)", rc.chain.repo(), bool(a.hidden), txs=txs,
                    paid=(rc, need))
    log = _log_of(receipt, v3.REGISTERED)
    issue = int(log["topics"][1], 16)
    check = int(log["data"][2:66], 16)
    paste = RV.signed_claim_lines(w.sign, w.address, rc.chain.chain_id(), rc.address, issue, repo, rad_issue)
    message = "\n".join(paste)
    cmd = ["rad", "issue", "comment", "--repo", rid or "<RID>", rad_issue, "--message", message]
    data = {"issue": issue, "check": check, "reporter": w.address, "radIssue": rad_issue, "rid": rid, "lines": paste,
            "paid": {"registrationFee": cfg["registrationFee"], "issueStake": cfg["issueStake"], "deposit": deposit},
            "opened": opening, "commented": False}
    lines += [f"{w.role} registered on-chain issue {issue} for the Radicle issue {rad_issue[:12]}: paid the registration "
              f"fee {fmt(cfg['registrationFee'])}, staked {fmt(cfg['issueStake'])}, and posted its registration check "
              f"(submission {check})'s deposit {fmt(deposit)}; the check's unused deposit is refunded",
              tx_line(txs[-1]), f"radicle issue {rad_issue}"]
    if a.comment:
        _rad(a.rad_exec, cmd, "comment on the Radicle issue")
        data["commented"] = True
        lines.append(f"commented the claim on the Radicle issue {rad_issue[:12]} ({rid}):")
        lines += ["", *paste, ""]
    else:
        lines += ["the registration check reads the claim on the Radicle issue: comment these three lines on it, each "
                  "on its own line (the signature holds for this issue only):", "", *paste, "", "  " + shlex.join(cmd)]
    lines += [draw_hint(check), f"its progress: pofctl --v3 issue show --issue {issue}",
              f"once the check is final, anyone opens the bounty: pofctl --v3 issue open --issue {issue}"]
    return with_txs(data, txs), lines


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
    txs: list = []
    receipt = _send(w, rc.address, "openBounty(uint256)", a.issue, txs=txs)
    b = int(_log_of(receipt, "BountyOpened(uint256,uint256)")["topics"][1], 16)
    return with_txs({"issue": a.issue, "bounty": b}, txs), [
        f"issue {a.issue}'s registration check passed: bounty {b} is open", tx_line(txs[-1])]


def cmd_draw(ctx, a) -> tuple:
    """v3.1 (VP11): anyone draws a check's panel that no validator drew. Panels' verdict says whether it may be drawn:
    sealed and past its seed block, or waiting with the registry changed or past its `retryAt`. Then the keeper's
    draw-and-signal rule (VP24, oracle.v3.draw_and_signal): waiting, `RaceV3.signal` (FeesV3 counts the wait), then
    `Panels.draw`, then the signal again if the draw seated a panel; sealed, the draw, then the signal. Anything else
    is said, with nothing sent. A signal that fails doesn't stop the draw (a validator's keeper signals it later)."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    s = a.check
    v = c.verdict(s)
    st = v["status"]
    name = v3.STATUS[st] if st < len(v3.STATUS) else str(st)
    if st == v3.SEALED:
        block = c.block()
        if block <= v["seedBlock"]:
            left = v["seedBlock"] - block + 1
            raise Fail(f"check {s} is sealed until its seed block {v['seedBlock']} (now block {block}): it may be "
                       f"drawn in {left} block(s), about {left * 12} s on Sepolia. Nothing was sent.")
        why = f"sealed, past its seed block {v['seedBlock']}"
    elif st == v3.WAITING:
        now, epoch = c.now(), c.epoch()
        changed = epoch + 1 != v["waitEpoch"]
        if not changed and now < v["retryAt"]:
            raise Fail(f"check {s} is waiting for validators who can judge it: it is drawn again once the registry "
                       f"changes, or at {_utc(v['retryAt'])} (in {_wait(v['retryAt'] - now)}). Nothing was sent.")
        why = "waiting, and the registry changed" if changed else f"waiting, past its retry time {_utc(v['retryAt'])}"
    elif st == 0:
        raise Fail(f"there is no check {s} on Panels. Nothing was sent.")
    else:
        drawn = f" (panel {v['pid']}, k = {v['k']})" if v["pid"] else ""
        raise Fail(f"check {s} is {name.lower()}{drawn}: it was drawn already, or is past drawing. Nothing was sent.")
    w = ctx.wallet(a.role)
    txs: list = []
    lines: list = []
    read: dict = {}

    def draw() -> bool:
        try:
            _send(w, c.panels, "draw(uint256)", s, txs=txs)
        except Fail as e:
            if txs:  # the wait's signal went out before the draw was refused
                raise Fail(f"{e}. Only the wait's signal was sent ({txs[-1]['tx']}, block {txs[-1]['block']}); "
                           f"nothing more was sent.") from None
            raise
        lines.extend([f"{w.role} drew check {s} ({why})", tx_line(txs[-1])])
        return True

    def signal(kind: str) -> bool:
        what = "its wait" if kind == "wait" else "its panel"
        try:
            _send(w, c.race, "signal(uint256)", s, txs=txs)
        except Fail as e:  # the draw stands (or still goes out); a validator's keeper signals it later
            lines.append(f"the signal of {what} wasn't sent ({e}); a validator's keeper signals it later")
            return False
        lines.extend([f"signalled check {s} to FeesV3's queue ({what})", tx_line(txs[-1])])
        return True

    def seated() -> bool:
        read.update(c.verdict(s))
        return read["status"] != v3.WAITING and bool(read["pid"])

    v3.draw_and_signal(st, draw, signal, seated)
    after = read or c.verdict(s)
    now_st = v3.STATUS[after["status"]]
    data = {"check": s, "before": name, "status": now_st, "k": after["k"], "panel": after["pid"],
            "drawer": w.address}
    if after["status"] == v3.WAITING:
        lines.append(f"check {s} is waiting: too few validators could judge it now; it is drawn again once the "
                     f"registry changes, or at {_utc(after['retryAt'])}")
    else:
        lines.append(f"check {s} is {now_st.lower()}: panel {after['pid']}, k = {after['k']}")
    return with_txs(data, txs), lines


def _when(ts: int, now: int) -> str:
    if not ts:
        return "-"
    return f"{_utc(ts)} ({'in ' + _wait(ts - now) if ts > now else _wait(now - ts) + ' ago'})"


def cmd_issue_show(ctx, a) -> tuple:
    """v3.1 (VP17, S3): a reporter's view of a registration: its check's status (sealed, waiting, judging, held,
    window, final, released), k and panel, the seal, reveal and report deadlines, the counted result, the hold or the
    window and `finalAt`, and the deposit: paid to its judges so far, the refund due and whether it was refunded. Reads
    only."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    i = c.issue(a.issue)
    if int(i["reporter"], 16) == 0:
        raise Fail(f"there is no on-chain issue {a.issue}")
    s = i["check"]
    sub, v = c.submission(s), c.verdict(s)
    now = c.now()
    st = v["status"]
    status = v3.STATUS[st].lower()
    counted = st in (v3.HELD, v3.WINDOW, v3.FINAL)
    data = {"issue": a.issue, "reporter": i["reporter"], "check": s, "state": ISSUE_STATES[i["state"]],
            "bounty": i["bounty"], "hidden": i["hidden"], "stake": i["stake"], "status": status, "k": v["k"],
            "panel": v["pid"], "judges": [], "sealBy": 0, "revealBy": 0, "reportBy": 0,
            "result": ("pass" if v["pass"] else "fail") if counted else None, "held": st == v3.HELD,
            "challengeOpen": v["challengeOpen"], "finalAt": v["finalAt"], "outcome": v3.RACE_OUTCOMES[sub["outcome"]],
            "deposit": {"paid": sub["charged"], "left": sub["deposit"], "refundDue": 0 if sub["done"] else
                        sub["deposit"], "refunded": bool(sub["done"]),
                        "refundFrom": v["finalAt"] + REPORT_WINDOW_S if v["finalAt"] else 0}}
    lines = [f"issue {a.issue} (reporter {i['reporter']}): {data['state'].lower()}"
             + (f", bounty {i['bounty']}" if i["bounty"] else "") + (", hidden tests" if i["hidden"] else ""),
             f"  check          {s}: {status}"]
    if st == v3.SEALED:
        lines.append(f"  draw           at seed block {v['seedBlock']} (now block {c.block()}); "
                     f"{draw_hint(s)}")
    elif st == v3.WAITING:
        lines.append(f"  waiting        too few validators could judge it; drawn again once the registry changes, or "
                     f"at {_when(v['retryAt'], now)}; pofctl --v3 draw {s} then")
    if v["pid"]:
        p = c.panel(v["pid"])
        judges = [j for j in c.judges(v["pid"]) if j]
        data.update(judges=judges, sealBy=p["sealBy"], revealBy=p["revealBy"],
                    reportBy=p["revealBy"] + REPORT_WINDOW_S)
        lines += [f"  panel          {v['pid']}, k = {v['k']}: {', '.join(judges) or 'no seat filled yet'}",
                  f"  seal by        {_when(p['sealBy'], now)}",
                  f"  reveal by      {_when(p['revealBy'], now)}",
                  f"  reports by     {_when(data['reportBy'], now)}"]
    if counted:
        lines.append(f"  result         {data['result']} (counted at k = {v['k']})")
    if st == v3.HELD:
        lines.append("  held           a pass at k = 1 waits until enough validators outside its panel could judge a "
                     "challenge (design L16); its challenge window starts then"
                     + ("; a challenge is open" if v["challengeOpen"] else ""))
    elif st == v3.WINDOW:
        lines.append(f"  window         open to challenges; final at {_when(v['finalAt'], now)}"
                     + ("; a challenge is open" if v["challengeOpen"] else ""))
    elif st == v3.FINAL:
        lines.append(f"  final          since {_when(v['finalAt'], now)}")
    elif st == v3.RELEASED:
        lines.append("  released       never judged: its rounds were released (no panel could be seated); the deposit "
                     "comes back")
    dep = data["deposit"]
    if dep["refunded"]:
        refund = "refunded"
    elif dep["refundFrom"]:
        refund = f"refund due {fmt(rc.micro(dep['refundDue']))}, from {_when(dep['refundFrom'], now)}"
    else:
        refund = f"refund due {fmt(rc.micro(dep['refundDue']))} after the verdict"
    lines.append(f"  deposit        paid to judges {fmt(rc.micro(dep['paid']))}; {refund}")
    if i["bounty"] == 0 and st == v3.FINAL and v["pass"]:
        lines.append(f"  next           anyone opens its bounty: pofctl --v3 issue open --issue {a.issue}")
    return data, lines


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
    txs: list = []
    lines += ensure_allowance(rc, w, amount, "the pledge", txs)
    _send(w, rc.address, "pledge(uint256,uint256)", a.bounty, rc.units(amount), txs=txs, paid=(rc, amount))
    held = rc.micro(rc.rpc.view(rc.address, "held(uint256,address)", ["uint256"], a.bounty, rc.coin)[0])
    lines += [f"{w.role} pledged {fmt(amount)} to bounty {a.bounty}; it holds {fmt(held)}", tx_line(txs[-1])]
    return with_txs({"bounty": a.bounty, "pledged": amount, "held": held, "activeSolvers": active,
                     "funder": w.address}, txs), lines


def cmd_attempt(ctx, a) -> tuple:
    """v3.1 polish (VP26, the owner's Q4 of 2026-11-24): a solver records an attempt on an open bounty, in place of
    the guides' `cast send <race> "attempt(uint256)"`. The first attempt locks the bounty's share of its rising price
    (pledges made after it still raise the claim). Checked first, with nothing sent on a refusal: the bounty is open,
    a fix's claim at the price on offer fits the solver's room (over it, the commit would be refused, D29), and the
    wallet holds the attempt fee. Then the fee coin is approved if the fee needs it, with VP17's wait for the allowance
    and its one retry, and `RaceV3.attempt` is sent."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    bt = c.bounty(a.bounty)
    state = v3.RACE_STATES[bt["state"]] if bt["state"] < len(v3.RACE_STATES) else str(bt["state"])
    if state != "Open":
        raise Fail(f"bounty {a.bounty} is {state}: an attempt is recorded on an open bounty. Nothing was sent.")
    w = ctx.wallet("solver")
    st = rc.standing(w.address)
    claim = rc.claim_now(a.bounty)
    fee = c.config()["attemptFee"]
    if st["openClaims"] + claim > st["cap"]:
        raise Fail(f"a fix of bounty {a.bounty} would claim {fmt(claim)} (its price on offer), and {w.address}'s open "
                   f"claims are {fmt(st['openClaims'])} of its cap {fmt(st['cap'])}: its commit would be refused "
                   f"(D29), so the attempt would only spend gas"
                   f"{f' and the attempt fee {fmt(fee)}' if fee else ''}. Wait for a claim to close, or build "
                   f"reputation on smaller bounties. Nothing was sent.")
    share = (f"its share locked at {bt['lockBps'] / 100:g} %" if bt["locked"]
             else "its share rising until the first attempt locks it")
    lines = [f"bounty {a.bounty} is open: a fix would claim {fmt(claim)} now ({share}); {w.address}'s room is "
             f"{fmt(st['room'])}, the attempt fee {fmt(fee)}{' (never refunded)' if fee else ''}"]
    txs: list = []
    if fee:
        lines += ensure_allowance(rc, w, fee, "the attempt fee", txs)
    _send(w, rc.address, "attempt(uint256)", a.bounty, txs=txs, paid=(rc, fee) if fee else None)
    after = c.bounty(a.bounty)
    nxt = (f"fix it on top of Heads.head (`pofctl --v3 status` shows it), then: pofctl --v3 submit --bounty "
           f"{a.bounty} --patch <your fix's commit>")
    lines += [f"{w.role} attempted bounty {a.bounty}: its share is locked at {after['lockBps'] / 100:g} %; "
              f"{after['attempting']} attempt(s) in progress", tx_line(txs[-1]), f"next: {nxt}"]
    data = {"bounty": a.bounty, "solver": w.address, "attemptFee": fee, "claim": claim, "room": st["room"],
            "locked": bool(after["locked"]), "lockBps": after["lockBps"], "attempting": after["attempting"],
            "next": nxt}
    return with_txs(data, txs), lines


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
    if state == "Merged" and rc.chain.rebases():
        raise Fail(f"bounty {a.bounty} is claimed: a fix is sealed on an open bounty. If you won it and its base went "
                   f"stale, rebase it in place: pofctl --v3 rebase --bounty {a.bounty} --patch <the rebased commit>. "
                   f"Nothing was sent.")
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
    txs: list = []
    lines = ensure_allowance(rc, w, deposit, "the fix's deposit", txs)
    salt = salt_of(a.salt)
    fix, base = v2.commit_word(fix_sha), v2.commit_word(base_sha)
    sealed = v3.fix_commitment(fix, base, salt, w.address)
    receipt = _send(w, rc.address, "commit(uint256,bytes32)", a.bounty, sealed, txs=txs, paid=(rc, deposit))
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
              f"worst case; the rest is refunded after the verdict)", tx_line(txs[-1]),
              "open the Radicle patch from your working copy of the repository, with the claim in its description "
              "(the salt lets the drawn validators open the seal; their nodes read the patch from their own Radicle "
              "node and take only a revision whose head is the commit and whose base is Heads.head):",
              "", "  " + shlex.join(push), "",
              "its description must carry these lines, each on its own line:", "", *body.splitlines(), "",
              f"if your fix wins, claim it (anyone holding these values can): {claim_cmd}", draw_hint(s)]
    return with_txs(data, txs), lines


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
    txs: list = []
    _send(w, rc.address, "claim(uint256,bytes32,bytes32,bytes32)", a.bounty, fix, base, salt, txs=txs)
    ver = c.verdict(s)
    data = {"bounty": a.bounty, "submission": s, "fix": fix_sha, "base": base_sha, "status": v3.STATUS[ver["status"]],
            "finalAt": ver["finalAt"], "state": rc.state(a.bounty)}
    when = (f"at chain time {ver['finalAt']} (in {max(ver['finalAt'] - c.now(), 0) / 3600:,.1f} h)"
            if ver["finalAt"] else "once its verdict is final")
    return with_txs(data, txs), [f"{w.role} claimed bounty {a.bounty} with submission {s}: its award started",
                  tx_line(txs[-1]), f"the head moves to {fix_sha[:12]} only at finality (L9): pofctl --v3 merge --bounty {a.bounty} "
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
    from oracle import rebase_v3

    target, _ = rebase_v3.merge_target(c, a.bounty)
    if target != aw["sub"]:  # through its rebase (#310 RB5): that verdict must be final too
        rv = c.verdict(target)
        if rv["status"] != v3.FINAL:
            left = max(rv["finalAt"] - c.now(), 0) if rv["finalAt"] else None
            when = f"; final at chain time {rv['finalAt']} (in {left / 3600:,.1f} h)" if left is not None else ""
            raise Fail(f"not yet: bounty {a.bounty} merges through its rebase, check {target}, whose verdict is "
                       f"{v3.STATUS[rv['status']]}, not Final{when}: the head moves to the rebased commit once both "
                       f"verdicts are final. Nothing was sent.")
    before = rc.head()
    sub = c.submission(target)
    base = rebase_v3.sha_of(sub["base"])
    if base != before:
        hint = (f"Its solver rebases it in place now (anyone else a day after the head moved): pofctl --v3 rebase "
                f"--bounty {a.bounty} --patch <the fix rebased onto {before[:12]}>" if c.rebases() else
                "The winner keeps its place until the merge deadline")
        raise Fail(f"the fix's base {base[:12]} isn't Heads.head {before[:12]} any more (a stale base): merge would "
                   f"revert. {hint}. Nothing was sent.")
    w = ctx.wallet("solver")
    txs: list = []
    _send(w, rc.address, "merge(uint256)", a.bounty, txs=txs)
    after = rc.head()
    data = {"bounty": a.bounty, "submission": aw["sub"], "merged": True, "already": False, "from": before, "head": after,
            "solver": aw["winner"], "rebase": target if target != aw["sub"] else 0}
    rid = rc.record.get("rid", "<RID>")
    return with_txs(data, txs), [f"merged bounty {a.bounty}: Heads.head {before[:12]} -> {after[:12]} (submission "
                                 f"{aw['sub']}, winner {aw['winner']}); the winner's claim closed into its reputation",
                  tx_line(txs[-1]),
                  f"the seated validators push Radicle's canonical main to it; check: pofctl --v3 verify-head --rid "
                  f"{rid} --rad-exec '<your node>'"]


def cmd_rebase(ctx, a) -> tuple:
    """v3.1 (#310, RB1, RB2, RB8): a claimed, unmerged fix whose base is no longer Heads.head, rebased in place onto the
    head. The rebased commit is opened in the clear (the approved fix is public since its claim) as a new check with
    the same deposit as a fix, judged by a fresh panel; the award keeps its place, its epoch and its price, and merges
    once both verdicts are final. The winner may rebase at once, anyone else a day (REBASE_GRACE) after the head last
    moved; a third party's rebase that merges is paid 10 % of the price (REBASE_SHARE_BPS) at the bounty's payment, and
    its checks. Every refusal the race would make is checked first, sending nothing. Then it prints how to push the
    rebased commit as a new revision of the fix's Radicle patch, with the claim lines its judges read."""
    rc: RaceV3 = ctx.v3
    c = rc.chain
    if not c.rebases():
        raise Fail("this deployment is v3, which has no rebase in place (v3.1 has it, #310): a stale winner waits for "
                   "the merge deadline there. Nothing was sent.")
    fix_sha = commit_sha(a.patch, "--patch (the rebased commit)")
    head = rc.head()
    base_sha = commit_sha(a.base, "--base") if a.base else head
    if base_sha != head:
        raise Fail(f"the rebase's base {base_sha[:12]} isn't Heads.head {head[:12]}: a rebase goes onto the head. "
                   f"Nothing was sent.")
    bt = c.bounty(a.bounty)
    state = v3.RACE_STATES[bt["state"]]
    if state != "Merged":
        raise Fail(f"bounty {a.bounty} is {state}: a rebase takes a claimed fix not merged yet. Nothing was sent.")
    aw = c.award(a.bounty, bt["epoch"])
    original = c.submission(aw["sub"])
    if aw["merged"]:
        raise Fail(f"bounty {a.bounty}'s fix is merged already. Nothing was sent.")
    if not c.verdict(aw["sub"])["pass"]:
        raise Fail(f"submission {aw['sub']}'s verdict isn't a pass any more: nothing to rebase. Nothing was sent.")
    from oracle import rebase_v3

    if rebase_v3.sha_of(original["base"]) == head:
        raise Fail(f"bounty {a.bounty}'s fix is based on Heads.head already: it merges as it is (pofctl --v3 merge "
                   f"--bounty {a.bounty} at finality). Nothing was sent.")
    if fix_sha in (rebase_v3.sha_of(original["fix"]), head) or rc.rpc.view(rc.address, "paid(bytes32)", ["bool"],
                                                                          v2.commit_word(fix_sha))[0]:
        raise Fail(f"{fix_sha[:12]} is the approved commit, the head or a commit already paid: a rebase is a new "
                   f"commit on the head. Nothing was sent.")
    r = aw.get("rebase", 0)
    if r:
        rs = c.submission(r)
        if rs["outcome"] == 0:
            raise Fail(f"bounty {a.bounty}'s rebase check {r} is still being judged: one rebase at a time. Nothing was "
                       f"sent.")
        if rs["outcome"] == 1 and rebase_v3.sha_of(rs["base"]) == head:
            raise Fail(f"bounty {a.bounty}'s rebase check {r} passed on the head: it merges at its finality (pofctl "
                       f"--v3 merge). Nothing was sent.")
    w = ctx.wallet("solver")
    third = w.address.lower() != aw["winner"].lower()
    if third:
        ready = rc.head_moved_at() + v3.REBASE_GRACE_S
        if c.now() < ready:
            raise Fail(f"{w.address} isn't the winner ({aw['winner']}): anyone else may rebase a day after the head "
                       f"last moved, at chain time {ready} (in {_wait(ready - c.now())}). Nothing was sent.")
    elif r and c.submission(r)["outcome"] == 2 and c.submission(r)["solver"].lower() == w.address.lower() \
            and rebase_v3.sha_of(c.submission(r)["base"]) == head:
        raise Fail(f"your rebase check {r} failed on the head: the award closes and the bounty reopens at once (the "
                   f"validators' keepers call mergeExpired({a.bounty}); anyone may), and you may appeal that check "
                   f"once in the reopened bounty. Nothing was sent.")
    st = rc.standing(w.address)
    claim = original["judged"]
    own = 0 if third else _open_claim(rc, aw["sub"])  # the winner's rebase replaces its earlier claims (RB7)
    if r and c.submission(r)["solver"].lower() == w.address.lower():
        own += _open_claim(rc, r)
    if st["openClaims"] - own + claim > st["cap"]:
        raise Fail(f"the rebase would claim {fmt(claim)} (the bounty its original was judged at), and {w.address}'s "
                   f"open claims are {fmt(st['openClaims'])} of its cap {fmt(st['cap'])}: refused (D29). Nothing was "
                   f"sent.")
    deposit = rc.check_deposit()
    txs: list = []
    lines = ensure_allowance(rc, w, deposit, "the rebase check's deposit", txs)
    salt = salt_of(a.salt)
    receipt = _send(w, rc.address, "rebase(uint256,bytes32,bytes32,bytes32)", a.bounty, v2.commit_word(fix_sha),
                    v2.commit_word(base_sha), salt, txs=txs, paid=(rc, deposit))
    check = int(_log_of(receipt, v3.REBASED)["topics"][3], 16)
    sub = c.submission(check)
    issue = bt["issue"]
    body = logic.pr_body(issue, a.bounty, check, "0x" + salt.hex(), w.address)
    msgs = patch_messages(a.title or f"Fix for bounty {a.bounty}, rebased onto {head[:12]}", body)
    # a new revision of an open patch: Radicle's remote helper takes a push to refs/heads/patches/<id> as its update
    # (refs/patches opens a new patch); forced, since a rebased commit doesn't descend from the patch's last revision
    ref = f"refs/heads/patches/{a.patch_id}" if a.patch_id else "refs/heads/patches/<the fix's patch id>"
    push = (["git", "push", "--force", "rad", f"{fix_sha}:{ref}"]
            + [x for m in msgs for x in ("-o", f"patch.message={m}")])
    data = {"bounty": a.bounty, "original": aw["sub"], "check": check, "fix": fix_sha, "base": base_sha,
            "salt": "0x" + salt.hex(), "rebaser": w.address, "winner": aw["winner"], "thirdParty": third,
            "deposit": sub["deposit"], "claim": claim, "patchBody": body, "patchMessages": msgs,
            "patchCommand": shlex.join(push)}
    lines += [f"{w.role} rebased bounty {a.bounty}'s fix (submission {aw['sub']}) onto Heads.head {head[:12]} as "
              f"commit {fix_sha[:12]}: rebase check {check}, a claim of {fmt(claim)}, deposit "
              f"{fmt(rc.micro(sub['deposit']))} (the meter's worst case; the rest is refunded after the verdict)",
              tx_line(txs[-1]), "push the rebased commit as a new revision of the fix's Radicle patch, with these claim lines (the "
              "judges read the revision whose head and base open the check):", "", "  " + shlex.join(push), "",
              *body.splitlines(), "",
              "a fresh panel judges the rebased tree with the new head's protected tests and compares it with the "
              "approved fix; the head moves to it once both verdicts are final (pofctl --v3 merge --bounty "
              f"{a.bounty}). If the winner's own rebase fails on the head, the bounty reopens at once"
              + ("; as a third party you get 10 % of the price and your checks back when the bounty is paid"
                 if third else ""), draw_hint(check)]
    return with_txs(data, txs), lines


def rebase_v3_sha(word: str) -> str:
    from oracle import rebase_v3

    return rebase_v3.sha_of(word)


def _open_claim(rc: RaceV3, s: int) -> int:
    """The claim submission `s` still holds against its solver's cap (0 once closed)."""
    return rc.rpc.view(rc.book, "claimOf(uint256)", ["(address,uint256)"], s)[0][1]


def cmd_withdraw(ctx, a) -> tuple:
    """The credit the race holds for this key (refunded deposits' rest, instalments, a stake back) to its wallet."""
    rc: RaceV3 = ctx.v3
    w = ctx.wallet(a.role)
    owed = rc.chain.owed(w.address)
    txs: list = []
    if owed:
        _send(w, rc.address, "withdraw(address,address)", rc.coin, w.address, txs=txs)
    return (with_txs({"account": w.address, "withdrawn": owed}, txs),
            [f"{w.role} withdrew {fmt(rc.micro(owed))} of credit (refunds, instalments, stakes back) to its wallet",
             *map(tx_line, txs)])


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
    txs: list = []
    _send(w, faucet, "claim()", txs=txs)
    nxt = r(faucet, "nextClaim(address)", ["uint256"], w.address)[0]
    data.update(claimed=amount, nextClaim=nxt, balance=rc.chain.balance(w.address))
    with_txs(data, txs)
    return data, [f"{w.role} {w.address} claimed {fmt(rc.micro(amount))} test coins from the faucet {faucet}",
                  tx_line(txs[-1]),
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
    synced = snap.sync_error if rid else ""
    if d.action != radicle.SIGN:
        raise Fail(f"verify-head refused: {d.reason}" + (f" (and {synced}: the node's copy may be behind)"
                                                         if synced else ""))
    return ({"repo": "0x" + repo.hex(), "rid": rid, "head": head, "canonical": canonical, "match": True},
            [f"repository 0x{repo.hex()[:12]}{' (' + rid + ')' if rid else ''}: {d.reason}"]
            + ([f"  note: {synced}; this is the node's own copy"] if synced else []))


def cmd_verify_delegates(ctx, a) -> tuple:
    """`verify-delegates` (specs/radicle-hosting, "Delegates follow the seats"; #251, L11): the Radicle identity's
    delegates are exactly the nodes of the validators seated on-chain (`isDrawable`), with a majority threshold. Each
    seat's node is read from the chain, the key its registration signed (`Validators.radNodeOf`); a seat registered
    without one is reported as unmapped. Nothing is signed or sent."""
    from oracle import delegates, radicle

    rc: RaceV3 = ctx.v3
    rid = _rid(rc, a.rid)
    try:
        cob, _, synced = radicle.Radicle(rid, shlex.split(a.rad_exec or "")).identity()
    except radicle.Unavailable as e:
        raise Fail(str(e)) from None
    doc = ((cob.get("revisions") or {}).get(cob.get("current")) or {}).get("doc") or {}
    seats = rc.chain.seats()
    nodes = delegates.ChainSeatNodes.of(rc.chain)
    ok, problems = delegates.verify_delegates(doc, seats, nodes)
    mapped = {s: nodes.node_of(s) for s in seats}
    if not ok:
        raise Fail("verify-delegates refused: " + "; ".join(problems)
                   + (f" (and {synced}: the node's copy may be behind)" if synced else ""))
    return ({"rid": rid, "seats": mapped, "delegates": doc.get("delegates", []), "threshold": doc.get("threshold"),
             "match": True},
            [f"{rid}: the {len(seats)} seats on-chain are the {len(doc.get('delegates', []))} delegates, threshold "
             f"{doc.get('threshold')} (each seat's node from its registration, Validators.radNodeOf)"]
            + [f"  {s} {d}" for s, d in mapped.items()]
            + ([f"  note: {synced}; this is the node's own copy"] if synced else []))


CHECKOUT = r"""set -u
S="${RAD_HOME:-$HOME/.radicle}/storage/%(store)s"
have() { git --git-dir "$S" cat-file -e "%(head)s^{commit}" 2>/dev/null; }
if ! have; then
%(sync_lines)s
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
    from oracle import radicle

    rc: RaceV3 = ctx.v3
    rid = _rid(rc, a.rid)
    head = rc.head()
    target = a.dir or f"pof-checkout-{head[:12]}"
    script = CHECKOUT % {"store": rid[4:], "head": head, "dir": shlex.quote(target),
                         "sync_lines": radicle.sync_lines(rid, "fetch", 60)}
    try:
        r = subprocess.run(shlex.split(a.rad_exec or "") + ["bash", "-c", script], capture_output=True, text=True,
                           timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Fail(f"checkout: {e}") from None
    got = dict(re.findall(r"^@(\w+) ?(.*)$", r.stdout, re.M))
    synced = radicle.sync_error(r.stdout)
    if r.returncode == 4:
        raise Fail(f"checkout: Heads.head {head} isn't on the node's copy of {rid}, even after a sync"
                   + (f" ({synced})" if synced else ""))
    if r.returncode == 5:
        raise Fail(f"checkout: {target} exists and isn't empty; give a new --dir")
    if r.returncode or got.get("head") != head:
        raise Fail(f"checkout failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-300:]}")
    ns = got.get("ns", "").split()
    return ({"rid": rid, "head": head, "dir": got.get("dir", target), "namespaces": ns},
            [f"checked out Heads.head {head} of {rid} into {got.get('dir', target)} (detached), from the namespaces "
             f"{', '.join(n[:16] + '…' for n in ns) or 'none'}",
             "this is the judged code whatever Radicle's main says; pofctl --v3 verify-head checks main against it"])


V3_ONLY = {"issue", "draw", "attempt", "pledge", "submit", "claim", "merge", "rebase", "checkout", "faucet", "verify-delegates"}
