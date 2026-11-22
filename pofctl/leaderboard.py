"""The contributor leaderboard (proof-of-fix#151): who earns what, computed only from the contracts' events (RaceV2's,
which carry its annex's and Baskets', and the meter's), so anyone can recompute it from the chain. No off-chain
database, and addresses only: nothing here links an address to a person (#126).

`compute(events, coin, ...)` is pure: the events as pofctl.race decodes them (each with its block, transaction and log
index, and its block's time when a period is asked for), in chain order. It turns them into facts (who, which metric,
how much, when, on which bounty), keeps the facts in the period and the bounties asked for, and ranks each role.

What v2's events give, per role:
- solvers: attempts (Attempted), submissions (Committed), late fixes (TooLate), decided and passed (Decided, matched to
  the submission's solver), fixes merged (Awarded: each signed merge starts an award), awards clawed back (ClawedBack),
  bounties won (closed Paid with them as the last award's winner) and coin earned (the instalments paid to them: Paid
  events, told apart from the check refund at settlement below);
- reporters: issues registered, bounties opened for them, refused as similar, rewarded (IssueClosed Rewarded), junk
  (IssueClosed Forfeited), and finder's fees (Paid to the reporter at settlement, told apart from the registration
  refund);
- funders: coin pledged and bounties funded (Pledged), bounties solved with their money (a bounty they pledged to closed
  Paid), refunds claimed and their amount (Refunded);
- validators: usage reports (Fees.Reported), verdicts counted (a reported judge on a submission the meter charged:
  Charged), and fees withdrawn (Withdrawn by the judge's payee account).

What they don't give (NOT_DERIVABLE, printed with the board): a validator's draws (the seed is stored, not emitted;
Verdicts.drawn is a view), its agreement with final outcomes (a judge's own verdict isn't on-chain: only the agreeing
signatures, in the transaction's input), its reveal rate (seals and reveals go through the exchange until task 5.5),
its fees per check (the meter credits each judge without an event; Charged has only the total), and slashes (no bonds
or slashes in v2: task 5.8).

Telling the payouts apart: a settlement pays, in this order in one transaction and per coin, the instalments still due
(to each award's winner), then the reporter's finder's fee, the registration refund, and the winner's checks refunded
(with a meter). So, within one transaction's Paid events for a bounty and a coin: a payment to a winner before any to
the reporter is an instalment; to the reporter, the finder's fee then the registration refund (alone, it's the refund
when it equals the registration fee Collected at the issue's registration in that coin, else the fee); to a winner
after the reporter's, the check refund. With no reporter payment, a last payment to the winner of a Paid bounty that
equals what the meter charged its passing submission is the check refund. A reporter who is also the bounty's winner
can't be told apart this way: their payments count as instalments."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

ROLES = ("solvers", "reporters", "funders", "validators")
ROLE_ALIASES = {"solver": "solvers", "reporter": "reporters", "funder": "funders", "validator": "validators"}
PERIODS = {"week": 7 * 86_400, "month": 30 * 86_400, "all": None}
PERIOD_NAMES = {"week": "the last 7 days", "month": "the last 30 days", "all": "all time"}

# Each role's metrics, in the table's order; the first ones rank (descending), then the address.
METRICS = {
    "solvers": ["earned", "merged", "won", "passed", "decided", "submissions", "attempts", "late", "clawedBack"],
    "reporters": ["finderFees", "opened", "registered", "rewarded", "refused", "junk"],
    "funders": ["pledged", "bounties", "solved", "refunds", "refunded"],
    "validators": ["counted", "reports", "withdrawn"],
}
RANK_BY = {"solvers": ["earned", "merged", "passed"], "reporters": ["finderFees", "opened", "registered"],
           "funders": ["pledged", "solved", "bounties"], "validators": ["counted", "withdrawn", "reports"]}
AMOUNTS = {"earned", "finderFees", "pledged", "refunded", "withdrawn"}
HEADERS = {"earned": "earned", "merged": "merged", "won": "won", "passed": "passed", "decided": "decided",
           "submissions": "submitted", "attempts": "attempts", "late": "late", "clawedBack": "clawed back",
           "finderFees": "finder's fees", "opened": "opened", "registered": "registered", "rewarded": "rewarded",
           "refused": "refused", "junk": "junk", "pledged": "pledged", "bounties": "bounties", "solved": "solved",
           "refunds": "refunds", "refunded": "refunded", "counted": "counted", "reports": "reports",
           "withdrawn": "withdrawn", "passRate": "pass rate"}

NOT_DERIVABLE = {
    "validators": {
        "draws": "not in v2's events: a submission's draw seed is stored, not emitted, and Verdicts.drawn is a view "
                 "(usage reports are the nearest: a drawn judge that took part)",
        "agreement": "not in v2's events: a judge's own verdict isn't on-chain, only the agreeing judges' signatures, "
                     "in the result transaction's input",
        "revealRate": "not in v2's events: seals and reveals go through the exchange until sealed verdicts on-chain "
                      "(task 5.5)",
        "feesEarned": "not in v2's events per check: the meter credits each judge without an event and Charged has "
                      "only the total; fees withdrawn are shown instead",
        "slashes": "none in v2: bonds and slashes are task 5.8's",
    },
}


@dataclass(frozen=True)
class Fact:
    role: str
    who: str
    metric: str
    value: int
    time: int | None
    bounty: int | None


def role_name(role: str | None) -> str | None:
    if role is None:
        return None
    role = ROLE_ALIASES.get(role, role)
    if role not in ROLES:
        raise ValueError(f"no role {role!r}: {', '.join(ROLES)}")
    return role


def facts(events: list, coin: str) -> list:
    """Every fact the events state, in chain order. Amounts count only in `coin` (the board's)."""
    coin = coin.lower()
    issue_bounty = {e["issue"]: e["bounty"] for e in events if e["event"] == "BountyOpened"}
    paid_groups: dict = defaultdict(list)  # (tx, bounty, coin) -> its Paid events, in order
    for e in events:
        if e["event"] == "Paid":
            paid_groups[(e["tx"], e["bounty"], e["coin"].lower())].append(e)

    reporter: dict = {}  # issue -> reporter
    registration: dict = {}  # issue -> (coin, fee) Collected at its registration
    bounty_issue: dict = {}
    sub_of: dict = {}  # submission -> (bounty, solver)
    passed_subs: dict = defaultdict(set)  # bounty -> its submissions decided Pass
    winners: dict = defaultdict(dict)  # bounty -> epoch -> winner
    paid: set = set()  # bounties closed Paid
    pledges: dict = defaultdict(dict)  # bounty -> funder -> pledged in coin
    refunded: set = set()  # (bounty, coin, funder) that claimed
    reports: dict = defaultdict(list)  # submission -> judges that reported
    charged: dict = {}  # submission -> what the meter charged
    payee_judge: dict = {}  # payee -> judge
    collected: dict = defaultdict(list)  # tx -> Collected events
    kinds: dict = {}  # id(Paid event) -> its kind

    out: list = []

    def fact(role, who, metric, value, e, bounty):
        if value:
            out.append(Fact(role, who, metric, value, e.get("time"), bounty))

    def classify(group, b):
        rep = reporter.get(bounty_issue.get(b), "").lower()
        won_by = {w.lower() for w in winners[b].values()}
        seen_rep, found, rep_payments = False, {}, []
        for p in group:
            to = p["to"].lower()
            if to == rep and to not in won_by:
                seen_rep = True
                rep_payments.append(p)
            elif to in won_by:
                found[id(p)] = "checkRefund" if seen_rep else "instalment"
            else:
                found[id(p)] = "other"
        if len(rep_payments) >= 2:
            found[id(rep_payments[0])] = "finderFee"
            found[id(rep_payments[1])] = "registrationRefund"
            for p in rep_payments[2:]:
                found[id(p)] = "other"
        elif rep_payments:
            p = rep_payments[0]
            reg = registration.get(bounty_issue.get(b))
            refund = reg is not None and reg[0] == p["coin"].lower() and reg[1] == p["amount"]
            found[id(p)] = "registrationRefund" if refund else "finderFee"
        elif group and b in paid and found.get(id(group[-1])) == "instalment":
            last = group[-1]
            mine = [s for s in passed_subs[b] if sub_of[s][1].lower() == last["to"].lower()]
            if any(charged.get(s) == last["amount"] for s in mine):
                found[id(last)] = "checkRefund"
        kinds.update(found)

    for e in events:
        name = e["event"]
        if name == "Collected":
            collected[e["tx"]].append(e)
        elif name == "Registered":
            i = e["issue"]
            reporter[i] = e["reporter"]
            for c in collected.get(e["tx"], []):
                if c["from"].lower() == e["reporter"].lower():
                    registration[i] = (c["coin"].lower(), c["amount"])
                    break
            fact("reporters", e["reporter"], "registered", 1, e, issue_bounty.get(i))
        elif name == "BountyOpened":
            bounty_issue[e["bounty"]] = e["issue"]
            fact("reporters", reporter.get(e["issue"], ""), "opened", 1, e, e["bounty"])
        elif name == "RefusedSimilar":
            fact("reporters", reporter.get(e["issue"], ""), "refused", 1, e, None)
        elif name == "IssueClosed":
            who, b = reporter.get(e["issue"], ""), issue_bounty.get(e["issue"])
            if e["state"] == "Rewarded":
                fact("reporters", who, "rewarded", 1, e, b)
            elif e["state"] == "Forfeited":
                fact("reporters", who, "junk", 1, e, b)
        elif name == "Attempted":
            fact("solvers", e["solver"], "attempts", 1, e, e["bounty"])
        elif name == "Committed":
            sub_of[e["submission"]] = (e["bounty"], e["solver"])
            fact("solvers", e["solver"], "submissions", 1, e, e["bounty"])
        elif name == "TooLate":
            fact("solvers", e["solver"], "late", 1, e, e["bounty"])
        elif name == "Decided":
            if e["submission"] not in sub_of:
                continue
            b, solver = sub_of[e["submission"]]
            fact("solvers", solver, "decided", 1, e, b)
            if e["outcome"] == "Pass":
                passed_subs[b].add(e["submission"])
                fact("solvers", solver, "passed", 1, e, b)
        elif name == "Awarded":
            winners[e["bounty"]][e["epoch"]] = e["winner"]
            fact("solvers", e["winner"], "merged", 1, e, e["bounty"])
        elif name == "ClawedBack":
            who = winners[e["bounty"]].get(e["epoch"])
            if who:
                fact("solvers", who, "clawedBack", 1, e, e["bounty"])
        elif name == "StateChanged" and e["state"] == "Paid":
            b = e["bounty"]
            paid.add(b)
            if winners[b]:
                fact("solvers", winners[b][max(winners[b])], "won", 1, e, b)
            for funder in pledges[b]:
                fact("funders", funder, "solved", 1, e, b)
        elif name == "Pledged":
            b, mine = e["bounty"], e["coin"].lower() == coin
            if e["funder"] not in pledges[b]:
                pledges[b][e["funder"]] = 0
                fact("funders", e["funder"], "bounties", 1, e, b)
            if mine:
                pledges[b][e["funder"]] += e["amount"]
                fact("funders", e["funder"], "pledged", e["amount"], e, b)
        elif name == "Refunded":
            key = (e["bounty"], e["coin"].lower(), e["funder"].lower())
            if key not in refunded:  # the last funder may get a second event: the rounding's remainder
                refunded.add(key)
                fact("funders", e["funder"], "refunds", 1, e, e["bounty"])
            if e["coin"].lower() == coin:
                fact("funders", e["funder"], "refunded", e["amount"], e, e["bounty"])
        elif name == "Paid":
            b = e["bounty"]
            if id(e) not in kinds:
                classify(paid_groups[(e["tx"], b, e["coin"].lower())], b)
            kind = kinds.get(id(e))
            if e["coin"].lower() != coin:
                continue
            if kind == "instalment":
                fact("solvers", e["to"], "earned", e["amount"], e, b)
            elif kind == "finderFee":
                fact("reporters", e["to"], "finderFees", e["amount"], e, b)
        elif name == "Reported":
            reports[e["submission"]].append(e["judge"])
            payee_judge.setdefault(e["payee"].lower(), e["judge"])
            fact("validators", e["judge"], "reports", 1, e, sub_of.get(e["submission"], (None,))[0])
        elif name == "Charged":
            charged[e["submission"]] = e["amount"]
            for judge in reports.get(e["submission"], []):
                fact("validators", judge, "counted", 1, e, sub_of.get(e["submission"], (None,))[0])
        elif name == "Withdrawn":
            judge = payee_judge.get(e["account"].lower())
            if judge and e["coin"].lower() == coin:
                fact("validators", judge, "withdrawn", e["amount"], e, None)
    return out


def compute(events: list, coin: str, period: str = "all", now: int | None = None, bounties=None,
            role: str | None = None) -> dict:
    """The board: each role's rows, ranked. `now`: the chain's time (needed for a week or a month); `bounties`: only
    the facts about these bounties (withdrawals, tied to none, are left out then)."""
    if period not in PERIODS:
        raise ValueError(f"no period {period!r}: week, month or all")
    role = role_name(role)
    since = None
    if PERIODS[period] is not None:
        if now is None:
            raise ValueError("a period needs the chain's time")
        since = now - PERIODS[period]
    wanted = None if bounties is None else set(bounties)
    rows: dict = {r: {} for r in ROLES}
    for f in facts(events, coin):
        if since is not None and (f.time is None or f.time < since):
            continue
        if wanted is not None and f.bounty not in wanted:
            continue
        if not f.who:
            continue
        row = rows[f.role].setdefault(f.who.lower(), {"address": f.who, **{m: 0 for m in METRICS[f.role]}})
        row[f.metric] += f.value
    board = {"period": period, "since": since, "until": now, "coin": coin,
             "bounties": None if wanted is None else sorted(wanted), "notDerivable": NOT_DERIVABLE}
    for r in ROLES:
        if role and r != role:
            continue
        ranked = sorted(rows[r].values(), key=lambda x: ([-x[m] for m in RANK_BY[r]], x["address"].lower()))
        for i, row in enumerate(ranked, 1):
            row["rank"] = i
            if r == "solvers":
                row["passRate"] = round(row["passed"] / row["decided"], 4) if row["decided"] else None
        board[r] = ranked
    return board


def _cell(metric: str, value) -> str:
    if metric in AMOUNTS:
        return f"{value / 10**6:,.6f}"
    if metric == "passRate":
        return "-" if value is None else f"{value * 100:.1f} %"
    return str(value)


def render(board: dict) -> list:
    """The board as text tables, one per role, then what v2's events can't say."""
    scope = PERIOD_NAMES[board["period"]]
    lines = [f"leaderboard: {scope}, from the contracts' events only; amounts in coin {board['coin']}; addresses only"]
    if board["bounties"] is not None:
        ids = ", ".join(map(str, board["bounties"]))
        lines.append(f"only bounties {ids} (withdrawals, tied to no bounty, left out)")
    for r in ROLES:
        if r not in board:
            continue
        cols = METRICS[r] + (["passRate"] if r == "solvers" else [])
        heads = [HEADERS[c] for c in cols]
        cells = [[_cell(c, row[c]) for c in cols] for row in board[r]]
        widths = [max([len(h)] + [len(x[i]) for x in cells]) for i, h in enumerate(heads)]
        lines += ["", f"{r} ({len(board[r])})"]
        lines.append(f"{'#':>3} {'address':<42}  " + "  ".join(h.rjust(w) for h, w in zip(heads, widths)))
        for row, x in zip(board[r], cells):
            lines.append(f"{row['rank']:>3} {row['address']:<42}  " + "  ".join(v.rjust(w) for v, w in zip(x, widths)))
        if not board[r]:
            lines.append("    none in this period")
        for metric, why in NOT_DERIVABLE.get(r, {}).items():
            lines.append(f"    not shown, {metric}: {why}")
    return lines
