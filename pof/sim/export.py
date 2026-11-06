"""The replay's exporter (proof-of-fix#56 design D7): a race run's events, in ledger order, as the contract's calls.

The run is built as `market_sim.run` builds it, with the market's methods wrapped, so every call that moves money (or
changes what the contract tracks, like an attempt that stops) is recorded with the ledger entries it made. Each
becomes one event of `contracts/test/Replay.t.sol`, with what every account touched should hold after it.

What the contract holds and what the simulation keeps apart are compared as the contract sees them: an actor's net
is its wallet plus its credits less its endowment; a bounty's pot is its bounty account plus its escrow, after the
merge; the race's deposits are the issue stakes and the submissions' accounts. Flows the contract doesn't have
(validator stakes, the checkers' bonds, reputation) are left out. Any money movement the exporter can't map raises
ExportError, so a gap shows instead of drifting.

Accounts get addresses in name order, so the funder with the highest address (the contract's lastFunder) is the last
pledger in pof's sorted order, which takes the refund's remainder in both.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field

from ..params import CONTRACT, TOKENS, Params
from . import market_sim as MS

KINDS = {name: i + 1 for i, name in enumerate((
    "register", "accept", "withdrawIssue", "pledge", "attempt", "stop", "submit", "appeal", "tooLate", "duplicate",
    "appealDuplicate", "merged", "instalment", "settle", "sunset"))}
OUTCOME = {"pass": 1, "fail": 2, "duplicate": 3, "split": 4}  # Race.Outcome
EVENT_FIELDS = ("amount", "bounty", "day", "deposits", "expFrom", "expTo", "feeFrom", "feeTo", "fix", "funFrom", "funTo",
                "heldFrom", "heldTo", "issue", "kind", "outcome", "price", "prev", "seq", "sub", "weight", "who")
CONTRACT_TOKENS = CONTRACT.with_(token_emission_per_period=TOKENS.token_emission_per_period)  # #56 D15, task 3.4
REPLAY_TOKEN_PRICE = 0.05  # #58: where tokens start to matter, so bounties of 0 coin get fixed in the replay
QUOTE_FIELDS = ("attempting", "bounty", "cap", "event", "finderFee", "instalment", "lastInstalment", "offerBps", "price",
                "state", "sunsetDay")
QUOTE_STATES = {"open": 1, "won": 2, "paid": 4}  # Race.State; pof's won is the contract's Won or Merged
HELD = ("issue", "entry", "bounty", "escrow")  # accounts the contract keeps
OUT = ("vstake", "ebond", "rbond")  # simulation-only: validator stakes, checkers' bonds
WRAPPED = ("register", "report_issue", "open_bounty", "release_unfunded", "pledge", "race_start", "race_stop",
           "race_submit", "race_appeal", "appeal_duplicate", "deliver_checked", "deliver", "fail", "_split_rejected",
           "merged", "_finish", "_close_unsolved", "flag_junk", "expire", "expire_deliveries", "fund_treasury")


class ExportError(ValueError):
    """A run the exporter can't map to the contract's calls."""


def kind_of(account: str | None) -> str:
    return account.rsplit("-", 1)[0] if account else ""


@dataclass
class Call:
    name: str
    args: dict
    result: object
    start: int  # ledger entries [start, end) made by the call
    end: int
    nested: list[str] = field(default_factory=list)
    kinds: tuple[str, ...] = ()  # the ledger events it recorded
    quote: dict | None = None  # its bounty's quote right after it (#56 task 3.2), if it has one


class Recorder:
    def __init__(self, world) -> None:
        self.world, self.market = world, world.market
        self.ledger = self.market.ledger
        self.calls: list[Call] = []
        self.depth = 0
        self.stack: list[list[str]] = []
        for name in WRAPPED:
            self._wrap(self.market, name)
        self._wrap(self.market.lifecycle, "pay_instalment", "instalment")

    def _wrap(self, obj, name: str, label: str | None = None) -> None:
        orig = getattr(obj, name)
        sig = inspect.signature(orig)

        def wrapped(*a, **k):
            top = self.depth == 0
            start, events = len(self.ledger._entries), len(self.ledger._events)
            self.depth += 1
            self.stack.append([])
            try:
                result = orig(*a, **k)
            except Exception:
                if top and len(self.ledger._entries) != start:
                    raise ExportError(f"{name} failed after moving money")
                raise
            finally:
                self.depth -= 1
                nested = self.stack.pop()
            if self.stack:
                self.stack[-1] += [name] + nested
            if top:
                args = sig.bind(*a, **k).arguments
                kinds = tuple(e.kind for e in self.ledger._events[events:])
                call = Call(label or name, dict(args), result, start, len(self.ledger._entries), nested, kinds)
                b = self._bounty_of(call)
                if b is not None:
                    call.quote = self.market.quote(b, int(args.get("day", 0)))
                self.calls.append(call)
            return result

        setattr(obj, name, wrapped)

    def _bounty_of(self, call: Call):
        """The bounty a call acts on, for its quote."""
        a, m = call.args, self.market
        if call.name == "open_bounty":
            return call.result
        if "b" in a:
            return a["b"]
        if "failed" in a:
            return m.bounties.get(a["failed"].bounty)
        if "e" in a:
            return m.bounties.get(a["e"].bounty)
        if "c" in a:
            return m._by_contribution.get(a["c"].id)
        return None


def record(scenario: str, seed: int, params: Params = CONTRACT, weeks: int = 2, **knobs) -> Recorder:
    world = MS.build(scenario, seed, params.with_(award_mode="race"), **knobs)
    rec = Recorder(world)
    world.run(weeks * 7, drain_days=MS.MARKET_DRAIN)
    return rec


class Exporter:
    def __init__(self, rec: Recorder) -> None:
        self.rec, self.m = rec, rec.market
        self.entries = rec.ledger.entries
        self.bounty_of_account = {b.account: b.id for b in self.m.bounties.values()}
        self.escrow_bounty: dict[str, int] = {}
        self.events: list[dict] = []
        self.covered: set[int] = set()
        self.sub = 0  # the contract's submission ids
        self.appeals = 0  # and its duplicate appeals
        self.sub_of: dict[int, int] = {}  # pof entry id -> contract submission id
        self.fixes: dict[str, int] = {}

    # ---------- entries ----------

    def in_scope(self, x) -> bool:
        if x.source is None:
            return False  # endowments: the replay mints its own
        return not (kind_of(x.source) in OUT or kind_of(x.target) in OUT)

    def contract_side(self, x) -> bool:
        """An entry the contract must reproduce: it touches a held account or the fee recipients."""
        return any(kind_of(a) in HELD + ("infrastructure",) for a in (x.source, x.target))

    def take(self, call: Call) -> list[int]:
        out = []
        for i in range(call.start, call.end):
            x = self.entries[i]
            if not self.in_scope(x):
                continue
            if kind_of(x.source) == "bounty" and kind_of(x.target) == "escrow":
                self.escrow_bounty[x.target] = self.bounty_of_account[x.source]
            out.append(i)
            self.covered.add(i)
        return out

    def fix_id(self, fix: str) -> int:
        return self.fixes.setdefault(fix or f"none:{len(self.fixes)}", len(self.fixes) + 1)

    # ---------- events ----------

    def event(self, kind: str, call: Call, entries: list[int], **fields) -> None:
        ev = {"kind": kind, "day": int(call.args.get("day", 0)), "entries": entries, "quote": call.quote, **fields}
        self.events.append(ev)

    def run(self) -> None:
        calls = self.rec.calls
        i = 0
        while i < len(calls):
            c = calls[i]
            a = c.args
            n = c.name
            if n == "register":
                if c.result:  # the fee; report_issue follows at once (market_world._report)
                    nxt = calls[i + 1] if i + 1 < len(calls) else None
                    if nxt is None or nxt.name != "report_issue" or nxt.args["reporter"] != a["poster"]:
                        raise ExportError("a registration without its issue")
                    r = nxt.result
                    self.event("register", nxt, self.take(c) + self.take(nxt), who=r.reporter, issue=r.id)
                    i += 2
                    continue
                if c.end != c.start:
                    raise ExportError("a registration that moved money without a fee")
            elif n == "report_issue":
                raise ExportError("an issue without the registration check (the contract takes both)")
            elif n == "open_bounty":
                b = c.result
                if b.report is None or b.parts:
                    raise ExportError(f"{b.ref}: a bounty the contract opens only for one registered issue")
                self.event("accept", c, self.take(c), bounty=b.id, issue=b.report, weight=b.weight)
            elif n == "release_unfunded":
                if c.end != c.start:
                    r = a["r"]
                    if r.bounty is not None:
                        raise ExportError(f"issue:{r.id}: its stake returned outside the bounty's close")
                    self.event("withdrawIssue", c, self.take(c), who=r.reporter, issue=r.id)
            elif n == "pledge":
                self.event("pledge", c, self.take(c), who=a["pledger"], bounty=a["b"].id, amount=a["amount"])
            elif n == "race_start":
                self.event("attempt", c, self.take(c), who=a["solver"], bounty=a["b"].id)
            elif n == "race_stop":
                self.event("stop", c, self.take(c), who=a["solver"], bounty=a["b"].id)
            elif n in ("race_submit", "race_appeal"):
                i = self._submission(calls, i)
                continue
            elif n == "appeal_duplicate":
                b = a["b"]
                entries = self.take(c)
                jurors = [x for x in entries if self.entries[x].reason == "payout"]
                self.appeals += 1
                self.event("appealDuplicate", c, entries, who=a["solver"], bounty=b.id, fix=self.fix_id(a["fix"]),
                           prev=self.appeals, outcome=int(bool(c.result)),
                           fees=[(self.entries[x].target, self.entries[x].amount) for x in jurors])
            elif n == "merged":
                b = self.m._by_contribution[a["c"].id]
                self.event("merged", c, self.take(c), bounty=b.id, weight=b.merge_weight or 0)
            elif n == "instalment":
                if c.end != c.start:
                    b = self.m._by_contribution.get(a["c"].id)
                    if b is None:
                        raise ExportError(f"{a['c'].ref}: an instalment that isn't a bounty's")
                    self.event("instalment", c, self.take(c), bounty=b.id)
            elif n == "_finish":
                b = a["b"]
                self.event("settle", c, self.take(c), bounty=b.id, funders=sorted(b.pledges))
            elif n == "_close_unsolved":
                b = a["b"]
                if b.treasury_in:
                    raise ExportError(f"{b.ref}: treasury funds have no contract counterpart")
                self.event("sunset", c, self.take(c), bounty=b.id, funders=sorted(b.pledges))
            elif c.end != c.start and any(self.contract_side(self.entries[x]) for x in range(c.start, c.end)):
                raise ExportError(f"{n} moved money the replay can't map (day {a.get('day')})")
            i += 1
        self._check_coverage()

    def _submission(self, calls: list[Call], i: int) -> int:
        """race_submit or race_appeal, and the delivery that decides it the same day."""
        c = calls[i]
        a = c.args
        b = a["b"] if c.name == "race_submit" else self.m.bounties[a["failed"].bounty]
        solver = a["solver"] if c.name == "race_submit" else a["failed"].solver
        e = c.result
        entries = self.take(c)
        if e is None:  # rejected unchecked for the evaluation fee: late, or a duplicate (#64, #56 D10)
            if c.name != "race_submit":
                raise ExportError("an appeal rejected unchecked")
            if "too_late" in c.kinds:
                self.event("tooLate", c, entries, who=solver, bounty=b.id, fix=self.fix_id(a.get("fix", "")))
            elif "duplicate_rejected" in c.kinds or "paid_elsewhere" in c.kinds:
                self.sub += 1
                self.event("duplicate", c, entries, who=solver, bounty=b.id, fix=self.fix_id(a.get("fix", "")),
                           sub=self.sub, outcome=OUTCOME["duplicate"])
            else:
                raise ExportError(f"{b.ref}: a submission rejected for a reason the contract doesn't have: {c.kinds}")
            return i + 1
        nxt = calls[i + 1] if i + 1 < len(calls) else None
        if nxt is None or nxt.name not in ("deliver_checked", "deliver") or nxt.args["e"] is not e:
            raise ExportError(f"entry {e.id}: a submission not decided the same day")
        entries += self.take(nxt)
        outcome = "pass" if e.state == "delivered" else "split" if "_split_rejected" in nxt.nested else "fail"
        if e.state not in ("delivered", "failed") or self.rec.ledger.balance(e.account):
            raise ExportError(f"entry {e.id}: a submission left {e.state} or holding money")
        fees = [(x.target, x.amount) for x in (self.entries[j] for j in entries)
                if x.source == e.account and x.target != solver]
        self.sub += 1
        self.sub_of[e.id] = self.sub
        fields = dict(who=solver, bounty=b.id, fix=self.fix_id(e.commitment), sub=self.sub, outcome=OUTCOME[outcome],
                      price=b.price, fees=fees)
        if c.name == "race_appeal":
            self.event("appeal", c, entries, prev=self.sub_of[a["failed"].id], **fields)
        else:
            self.event("submit", c, entries, **fields)
        self.events[-1]["quote"] = nxt.quote  # after its result
        return i + 2

    def _check_coverage(self) -> None:
        for i, x in enumerate(self.entries):
            if i in self.covered or not self.in_scope(x):
                continue
            if kind_of(x.source) == "bounty" and kind_of(x.target) == "escrow":  # the merge's escrow move
                self.escrow_bounty[x.target] = self.bounty_of_account[x.source]
                continue
            if self.contract_side(x):
                raise ExportError(f"entry {x.seq} ({x.reason} {x.source} -> {x.target}, day {x.time}) is in no event")

    # ---------- the file ----------

    def document(self, seed: int, params: Params) -> dict:
        """The file Replay.t.sol reads. Every table is a set of columns, one array of numbers per field: forge's
        vm.parseJson doesn't keep an object's fields in a dependable order, so nothing is decoded as a struct. The
        per-event tables (expects, held, fees, funders) start with a placeholder row, so ranges are never empty."""
        book = self.m.tokens
        holders = (set(book.balances) | ({book.owner} if book.owner else set())) if book else set()
        names = sorted({a for x in self.entries if x.source is not None and self.in_scope(x)
                        for a in (x.source, x.target) if kind_of(a) not in HELD}
                       | {self.m.infrastructure, self.m.releases.insurance} | holders)
        index = {n: i for i, n in enumerate(names)}
        net = {n: 0 for n in names}
        bal: dict[str, int] = {}
        tables = {"expects": ("account", "neg", "value"), "held": ("amount", "bounty"), "fees": ("amount", "to"),
                  "funders": ("account",)}
        out = {t: {f: [0] for f in fields} for t, fields in tables.items()}
        out["events"] = {f: [] for f in EVENT_FIELDS}
        out["quotes"] = {f: [] for f in QUOTE_FIELDS}

        def held_of(b: int) -> int:
            acc = self.m.bounties[b].account
            return bal.get(acc, 0) + sum(v for a, v in bal.items() if self.escrow_bounty.get(a) == b)

        def deposits() -> int:
            return sum(v for a, v in bal.items() if kind_of(a) in ("issue", "entry"))

        def push(table: str, rows: list[tuple]) -> tuple[int, int]:
            cols = out[table]
            start = len(cols[tables[table][0]])
            for row in rows:
                for f, v in zip(tables[table], row):
                    cols[f].append(v)
            return start, start + len(rows)

        def signed(n: str) -> tuple:  # forge reads unsigned arrays: the sign apart
            return index[n], int(net[n] < 0), abs(net[n])

        for ev in self.events:
            touched, bounties = set(), set()
            for j in ev["entries"]:
                x = self.entries[j]
                for acc, sign in ((x.source, -1), (x.target, 1)):
                    if kind_of(acc) in HELD:
                        bal[acc] = bal.get(acc, 0) + sign * x.amount
                        b = self.bounty_of_account.get(acc) or self.escrow_bounty.get(acc)
                        if b:
                            bounties.add(b)
                    else:
                        net[acc] += sign * x.amount
                        touched.add(acc)
            if ev.get("bounty"):
                bounties.add(ev["bounty"])
            fees = push("fees", [(amt, index[to]) for to, amt in ev.get("fees", [])])
            exp = push("expects", [signed(n) for n in sorted(touched)])
            held = push("held", [(held_of(b), b) for b in sorted(bounties)])
            fun = push("funders", [(index[f],) for f in ev.get("funders", [])])
            first = ev["entries"][0] if ev["entries"] else -1
            row = {"amount": ev.get("amount", 0), "bounty": ev.get("bounty", 0), "day": ev["day"],
                   "deposits": deposits(), "expFrom": exp[0], "expTo": exp[1], "feeFrom": fees[0], "feeTo": fees[1],
                   "fix": ev.get("fix", 0), "funFrom": fun[0], "funTo": fun[1], "heldFrom": held[0],
                   "heldTo": held[1], "issue": ev.get("issue", 0), "kind": KINDS[ev["kind"]],
                   "outcome": ev.get("outcome", 0), "price": ev.get("price", 0), "prev": ev.get("prev", 0),
                   "seq": self.entries[first].seq if first >= 0 else 0,
                   "sub": ev.get("sub", 0), "weight": ev.get("weight", 0),
                   "who": index[ev["who"]] if "who" in ev else 0}
            for f in EVENT_FIELDS:
                out["events"][f].append(row[f])
            q = ev.get("quote")
            if q is not None and q["state"] in QUOTE_STATES and ev.get("bounty"):
                q = {**q, "event": len(out["events"]["kind"]) - 1, "bounty": ev["bounty"],
                     "state": QUOTE_STATES[q["state"]]}
                for f in QUOTE_FIELDS:
                    out["quotes"][f].append(q[f])
        final = [signed(n) for n in names]
        p = params
        out.update({
            "seed": seed, "accounts": len(names), "names": names,
            "infra": index[self.m.infrastructure], "insurance": index[self.m.releases.insurance],
            "params": {  # Race.Config, as pof sets it (design D9)
                "appealFee": p.rerun_appeal_fee, "attemptFee": p.attempt_fee,
                "checkDeposit": self.m.deposit(), "evaluationFee": p.evaluation_fee,
                "finderFeeBps": p.finder_fee_bps, "idleDays": p.bounty_max_rounds * p.round_days,
                "instalments": p.reward_instalments, "issueStake": p.issue_stake,
                "marketFeeBps": p.market_fee_bps, "registrationFee": p.registration_fee,
                "releaseEveryDays": p.release_every_days, "riseBpsPerDay": p.price_rise_bps_per_day,
                "startPriceBps": p.start_price_bps, "windowDays": p.challenge_window_days},
            "token": self._token(index),
            "final": {f: [r[i] for r in final] for i, f in enumerate(tables["expects"])},
            "finalHeld": {"amount": [held_of(b) for b in sorted(self.m.bounties)], "bounty": sorted(self.m.bounties)},
            "finalDeposits": deposits(),
        })
        return out


    def _token(self, index: dict[str, int]) -> dict:
        """The token as pof's TokenBook minted it (#58; the contract's Token, task 3.4): its parameters, the founder,
        each period's closes and mint, and every holder's balance. With the emission off, an empty book."""
        book, p = self.m.tokens, self.rec.world.params
        periods = sorted({period for period, _, _ in book.history}) if book else []
        holders = sorted(book.balances) if book else []
        return {
            "emission": p.token_emission_per_period, "decayBps": p.token_emission_decay_bps,
            "founderBps": p.founder_share_bps, "founderPeriods": p.founder_periods, "reporterBps": p.token_reporter_bps,
            "inflationPct": p.weight_inflation_pct,
            "hasFounder": int(bool(book and book.owner)), "founder": index[book.owner] if book and book.owner else 0,
            "periods": {"period": [0] + periods,
                        "closes": [0] + [sum(1 for q, _, _ in book.history if q == x) for x in periods],
                        "minted": [0] + [book.minted[x] for x in periods]},
            "holders": {"account": [0] + [index[a] for a in holders], "balance": [0] + [book.balances[a] for a in holders]},
            "supply": book.supply if book else 0,
        }


def export(seed: int, scenario: str = "market", params: Params = CONTRACT, weeks: int = 2, **knobs) -> dict:
    rec = record(scenario, seed, params, weeks, **knobs)
    ex = Exporter(rec)
    ex.run()
    return ex.document(seed, rec.world.params)
