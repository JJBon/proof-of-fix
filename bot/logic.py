"""The bounty bot's pure logic (proof-of-fix#56 task 3.3): what it reads from issues, comments and pull requests, and
the payouts the loop must end with. No I/O here, so it's tested without Docker (tests/test_bot.py).

The bot is a convenience: anyone can call the contract directly. It links an issue to its bounty and a pull request to
its sealed submission, nothing more; the contract decides who is paid what."""

from __future__ import annotations

import re
from dataclasses import dataclass

LABEL = "bounty"  # the maintainer labels an issue to opt it in
MARKER = re.compile(r"<!-- pof-bounty race=(0x[0-9a-fA-F]{40}) bounty=(\d+) issue=(\d+) -->")
WALLET = re.compile(r"^(Reporter|Solver) wallet:\s*(0x[0-9a-fA-F]{40})\s*$", re.M)
CLAIM = re.compile(r"^(Bounty|Submission|Salt):\s*(\S+)\s*$", re.M)
FIXES = re.compile(r"^Fixes #(\d+)\s*$", re.M)
BPS = 10_000


def wallet(body: str, role: str) -> str | None:
    """The address an issue's reporter or a pull request's solver names in its body."""
    for who, address in WALLET.findall(body or ""):
        if who == role:
            return address
    return None


def needs_bounty(issue: dict, comments: list[dict]) -> bool:
    """An open issue the maintainer labelled, with no bounty linked yet."""
    labelled = any(label.get("name") == LABEL for label in issue.get("labels") or [])
    return issue.get("state") == "open" and labelled and linked(comments) is None


def linked(comments: list[dict]) -> tuple[str, int, int] | None:
    """The (race, bounty, on-chain issue) the bot linked in a comment, if any."""
    for c in comments:
        m = MARKER.search(c.get("body") or "")
        if m:
            return m.group(1), int(m.group(2)), int(m.group(3))
    return None


def bounty_comment(race: str, bounty: int, onchain_issue: int, quote: str = "") -> str:
    body = (f"Bounty #{bounty} is open on the Race at `{race}` (on-chain issue {onchain_issue}). Anyone can fund it, "
            f"and the first fix that passes the checks and is merged wins it. The bot only links the two: anyone can "
            f"call the contract directly.\n\n<!-- pof-bounty race={race} bounty={bounty} issue={onchain_issue} -->")
    return body + (f"\n\n```\n{quote.strip()}\n```" if quote else "")


PAID_MARKER = re.compile(r"<!-- pof-paid race=(0x[0-9a-fA-F]{40}) bounty=(\d+) tx=(0x[0-9a-fA-F]{64}) -->")


def paid(comments: list[dict]) -> tuple[str, int, str] | None:
    """The (race, bounty, payout transaction) the bot reported paid in a comment, if any (#151's closing step)."""
    for c in comments:
        m = PAID_MARKER.search(c.get("body") or "")
        if m:
            return m.group(1), int(m.group(2)), m.group(3)
    return None


def tx_link(tx: str, explorer: str = "") -> str:
    """A transaction as Markdown: a link when an explorer's URL template (with {tx}) is configured, else its hash."""
    return f"[`{tx}`]({explorer.format(tx=tx)})" if explorer and "{tx}" in explorer else f"`{tx}`"


def paid_comment(race: str, bounty: int, tx: str, block: int, chain_id: int, explorer: str = "") -> str:
    """The comment the bot closes a paid bounty's issue with: the payout transaction, and the marker it reads back."""
    where = f"chain {chain_id}, block {block}"
    if not (explorer and "{tx}" in explorer):
        where += "; no explorer is configured for this chain, so read it with eth_getTransactionReceipt"
    return (f"Bounty #{bounty} on the Race at `{race}` was paid: its award settled on-chain in transaction "
            f"{tx_link(tx, explorer)} ({where}). The fix is merged and paid, so this issue is closed. The bot only "
            f"reports what the contract did: anyone can check the transaction.\n\n"
            f"<!-- pof-paid race={race} bounty={bounty} tx={tx} -->")


def pr_body(issue: int, bounty: int, submission: int, salt: str, solver: str) -> str:
    """A fix's pull request names its bounty and its sealed submission, and reveals the salt to the oracles."""
    return (f"Fixes #{issue}\n\nBounty: {bounty}\nSubmission: {submission}\nSalt: {salt}\nSolver wallet: {solver}\n")


def fixes(body: str) -> int | None:
    """The issue a pull request's body says it fixes (as pr_body writes it); None if it names none. The solver wrote
    it: a judge checks the issue is the bounty's before reading it (oracle/evidence.py)."""
    m = FIXES.search(body or "")
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


@dataclass(frozen=True)
class Claim:
    bounty: int
    submission: int
    salt: str
    solver: str


def claim(body: str) -> Claim | None:
    """What a pull request claims: its bounty, submission, salt and solver; None if any is missing."""
    found = dict(CLAIM.findall(body or ""))
    solver = wallet(body, "Solver")
    if not {"Bounty", "Submission", "Salt"} <= found.keys() or solver is None:
        return None
    if not (found["Bounty"].isdigit() and found["Submission"].isdigit() and re.fullmatch(r"0x[0-9a-f]{64}", found["Salt"])):
        return None
    return Claim(int(found["Bounty"]), int(found["Submission"]), found["Salt"], solver)


def tuple_fields(value) -> list[str]:
    """A struct cast returns, as a list of its fields: cast --json gives a list already, or the tuple as text."""
    if isinstance(value, list):
        return [str(v) for v in value]
    text = str(value).strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    return [f.strip().split(" ")[0] for f in text.split(",")]


def script_values(output: str) -> dict[str, str]:
    """The `NAME=value` lines a forge script logs."""
    return dict(re.findall(r"^\s*([A-Z][A-Z0-9_]*)=(\S+)\s*$", output, re.M))


# ---------- settling on time ----------

MERGED, PAID = 3, 4  # Race.State


def last_release_day(window_end: int, release_every_days: int, instalments: int) -> int:
    """The day a merged bounty's last instalment is released (Race.earned): the start of the release `instalments`
    after the one its challenge window ended in. From that day it can be settled paid."""
    return (window_end // release_every_days + instalments) * release_every_days


def due_to_settle(state: int, today: int, window_end: int, release_every_days: int, instalments: int) -> bool:
    """The bot settles a bounty the day its last instalment is released, so its close is recorded in that period and
    nobody loses tokens to a missed grace window (owner, 2026-10-30)."""
    return state == MERGED and today >= last_release_day(window_end, release_every_days, instalments)


# ---------- the payouts (the contract's arithmetic, restated to check it) ----------

@dataclass(frozen=True)
class Config:
    registration_fee: int
    issue_stake: int
    attempt_fee: int
    check_deposit: int
    start_bps: int
    rise_bps_per_day: int
    finder_fee_bps: int


def lock_bps(cfg: Config, days_open: int) -> int:
    """The share of the cap on offer when the first attempt locks it."""
    return min(cfg.start_bps + cfg.rise_bps_per_day * days_open, BPS)


def price(cfg: Config, pledged: int, locked_bps: int) -> int:
    """The award's price: the locked share of the cap, the cap leaving room for the registration refund and the
    finder's fee (Race.capOf, pof's price_cap)."""
    cap = max(pledged - cfg.registration_fee, 0) * BPS // (BPS + cfg.finder_fee_bps)
    return cap * locked_bps // BPS


def loop_payouts(cfg: Config, start: int, pledged: int, locked_bps: int, oracle_fee: int, signers: int,
                 failed: int) -> dict[str, int]:
    """What each account holds at the end of the loop (its wallet plus its credit in the contract): one reporter, one
    funder, `failed` solvers whose fixes failed, and the winner; every submission checked by `signers` oracles."""
    p = price(cfg, pledged, locked_bps)
    finder = p * cfg.finder_fee_bps // BPS
    checks = oracle_fee * signers
    out = {
        "reporter": start - cfg.registration_fee + cfg.registration_fee + finder,  # stake back, fee refunded
        "funder": start - p - finder - cfg.registration_fee,  # the pot's leftover returns
        "winner": start - cfg.attempt_fee - checks + p,
        "infrastructure": cfg.registration_fee + cfg.attempt_fee * (failed + 1),
        "oracle": oracle_fee * (failed + 1),  # each signing oracle, for every checked submission
    }
    for i in range(failed):
        out[f"failed{i}"] = start - cfg.attempt_fee - checks
    return out


# ---------- the tokens (Token.sol, pof's TokenBook: #58) ----------

@dataclass(frozen=True)
class TokenRules:
    first_emission: int
    decay_bps: int
    founder_bps: int
    founder_periods: int
    reporter_bps: int
    inflation_pct: int


def emission(rules: TokenRules, period: int) -> int:
    """A period's emission: the first, less decay_bps of the previous one each period, rounded down."""
    e = rules.first_emission
    for _ in range(period):
        e -= e * rules.decay_bps // BPS
    return e


def lone_close_tokens(rules: TokenRules, period: int, registered: int, at_merge: int) -> dict[str, int]:
    """What a period with a single close mints: the founder's share off the top, the rest to that close (the largest
    weight takes the remainder), split between its reporter and its solver; the reporter's part goes to the solver if
    the registered weight was above inflation_pct of the merge estimate."""
    e = emission(rules, period)
    founder = e * rules.founder_bps // BPS if period < rules.founder_periods else 0
    pool = e - founder
    inflated = registered * 100 > at_merge * rules.inflation_pct
    reporter = 0 if inflated else pool * rules.reporter_bps // BPS
    return {"founder": founder, "reporter": reporter, "solver": pool - reporter, "supply": e}
