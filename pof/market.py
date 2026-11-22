"""The bounty market (specs/bounty-market, proof-of-fix#15): issues become bounties funded by pledges or a capped
treasury; solvers bid for the job in sealed second-price rounds before building anything; the assigned solver
delivers within a deadline and is paid on release through the lifecycle (design D9: bid first, build after).

    pledging --target reached--> open (a sealed round) --cheapest bid--> assigned --delivery passes--> won
        \\--deadline missed--> refunded        \\--no bid--> open (a new round)       \\--fails or late--> next bid
    won --last instalment--> paid (leftover refunded);  won --slashed, clawed back or declined--> next bid | open

Only prices are sealed and revealed, so nothing exists to copy before delivery, and only the assigned solver spends
the effort of building. Its stake is a performance bond: forfeited to the bounty if it doesn't deliver.

Award modes (proof-of-fix#60): in "race" and "claim" there are no bids or rounds. A bounty is registered through an
AI check its poster pays for, funders set its price, and the winning contribution is the first through the project's
constitution (in a claim, the claimant's, during its exclusive time).

Issues carry a reporter's stake (proof-of-fix#34): back with a finder's fee when the bounty is paid, lost if the
issue is confirmed junk, back if it's never funded. Half the treasury budget matches pledges quadratically at each
release; a bounty's leftover returns in proportion to what each source put in, the treasury's share to insurance.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

from . import BPS, credits, share
from .ledger import Ledger
from .checking import constitution_passes
from .lifecycle import Contribution, Lifecycle, LifecycleError, NeedsPanel
from .params import FEE_SHARES, Params
from .reputation import Reputation
from .tokens import TokenBook


class MarketError(ValueError):
    """A step the bounty's or bid's state doesn't allow, or one someone can't pay for; nothing changed."""


def seal(price: int, salt: str) -> str:
    """The commitment to a sealed price, revealed after the round's deadline."""
    return hashlib.sha256(f"{price}:{salt}".encode()).hexdigest()


@dataclass
class Entry:
    """A bid for a bounty's job."""

    id: int
    bounty: int
    solver: str
    commitment: str
    risk: str
    account: str  # holds the stake (the bond, once assigned) and the evaluation fee while they're locked
    day: int
    round: int = 0
    stake: int = 0
    fee_held: int = 0
    price: int | None = None
    deliver_by: int | None = None
    appeal: bool = False  # race: its author's one appeal of a failed submission, judged by the second jury (#60)
    state: str = "committed"  # committed | revealed | void | queued | assigned | delivered | failed | skipped


@dataclass
class IssueStake:
    """An issue's reporter and its stake (#34)."""

    id: int
    reporter: str
    account: str
    day: int
    bounty: int | None = None
    state: str = "posted"  # posted | rewarded | returned | forfeited
    registration: int = 0  # race and claim: the registration check its reporter paid, refunded if it's solved (#60)


@dataclass
class Bounty:
    id: int
    target: int
    deadline: int
    account: str
    treasury: bool = False
    pledges: dict[str, int] = field(default_factory=dict)
    state: str = "pledging"  # pledging | open | assigned | won | paid | refunded | unsolved
    rounds: int = 0
    round_deadline: int | None = None
    entries: list[Entry] = field(default_factory=list)
    queue: list[Entry] = field(default_factory=list)  # the last round's revealed bids not yet offered, cheapest first
    assigned: Entry | None = None
    contribution: int | None = None
    price: int = 0
    assignments: int = 0
    report: int | None = None  # the issue stake behind it (#34)
    treasury_in: int = 0  # what the treasury put in: a treasury bounty's funding, or matches
    matched: int = 0
    empty_rounds: int = 0  # rounds in a row that closed without a bid (#34)
    published: list[int] = field(default_factory=list)  # failed attempts made public, by bid id (#43)
    cases: list[str] = field(default_factory=list)  # cases added to the public definition by upheld proofs (#43)
    hidden_set: int = 1  # the hidden tests in use; a failed attempt burns them (#43)
    reserve_limit: int | None = None  # a reopened round's reserve: at most the failed attempt's price (#43)
    opened: int = 0  # the day it was registered (#60: time to fix)
    won_day: int | None = None  # the day its latest winning delivery passed
    idle_since: int = 0  # race and claim: opened, reopened or last had a submission checked on this day
    stopped_on: int = 0  # race: the last attempt stopped on this day (pledgers' top-ups wait a week after it)
    attempting: set[str] = field(default_factory=set)  # race: solvers whose attempts are in progress, published
    gate_bar_bps: int = 0  # the constitution's bar it was registered under (#60: gates are versioned)
    parts: list[int] = field(default_factory=list)  # a bundle's issue stakes: their reporters share the finder's fee
    offer_from: int | None = None  # race and claim: the day its rising price started (#60 D9)
    lock_bps: int | None = None  # the price's share of the cap, locked by the first attempt or claim (#56 D14)
    failed_fixes: set[str] = field(default_factory=set)  # race: fingerprints of failed submissions (#60 D9)
    appealed: set[int] = field(default_factory=set)  # race: failed submissions already appealed
    cleared: set[tuple[str, str]] = field(default_factory=set)  # race: (solver, fix) found independent on appeal (#64)
    key: str = ""  # race and claim: the issue it tracks, as the registration check recognizes it (#56 D12)
    weight: int = 0  # the registration check's estimate of the issue's importance: its token weight (#58 D3)
    merge_weight: int | None = None  # the independent estimate when its fix is merged; the smaller one counts
    inflated: bool = False  # its registered weight was above the tolerance: its reporters forfeited their share

    @property
    def ref(self) -> str:
        return f"bounty:{self.id}"


class Market:
    def __init__(self, ledger: Ledger, params: Params, lifecycle: Lifecycle, releases, infrastructure: str) -> None:
        self.ledger, self.params, self.lifecycle, self.releases = ledger, params, lifecycle, releases
        self.infrastructure = infrastructure
        releases.market = self
        self.bounties: dict[int, Bounty] = {}
        self.entries: dict[int, Entry] = {}
        self._by_contribution: dict[int, Bounty] = {}
        self._credited: set[int] = set()  # contributions whose acceptance earned their points (#37 design D6)
        self._treasury_spent: dict[int, int] = {}  # release -> treasury spend on bounties it proposed
        self._match_spent: dict[int, int] = {}  # release -> treasury spend on matching (#34)
        self.reports: dict[int, IssueStake] = {}
        self.reputation = Reputation(ledger, params, lambda: lifecycle.release)  # scores from outcomes, and trust (#37)
        self.checking = None  # the checking layer (#43), when deliveries go through re-runs and a jury
        self.check_gas = None  # #85 S15: a pof.checkgas.PriceTable charges checks as usage plus the service fee
        self._entry_of: dict[int, Entry] = {}  # contribution id -> the bid that delivered it
        self.paid_fixes: dict[str, int] = {}  # race: fingerprints of merged fixes -> the bounty paying them (#56 D10)
        # the token emission (#58): minted by solved issues only, kept apart from the coin ledger (D1)
        self.tokens = TokenBook(params, releases.owner) if params.token_emission_per_period else None
        self.weigh_at_merge = None  # the AI's second importance estimate, made when a fix is merged (D3)

    # ---------- issues (#34) ----------

    def report_issue(self, reporter: str, day: int, registration: int = 0) -> IssueStake:
        """Submit an issue, posting the issue stake (and noting the registration check paid for it, #60). Refused,
        with nothing locked, without the balance."""
        if self.ledger.balance(reporter) < self.params.issue_stake:
            raise MarketError(f"{reporter} can't cover the issue stake")
        r = IssueStake(len(self.reports) + 1, reporter, self.ledger.open("issue"), day, registration=registration)
        self.ledger.transfer(reporter, r.account, self.params.issue_stake, "stake", f"issue:{r.id}", day)
        self.reports[r.id] = r
        return r

    def flag_junk(self, r: IssueStake, day: int, panel_majority: bool) -> bool:
        """The treasury flagged the issue as junk (or its fix was slashed as junk) and a validator panel voted. If
        the panel confirms, the stake goes to insurance, and a bounty still gathering pledges or in a round closes,
        its funds returned by input. Returns whether junk was confirmed."""
        if r.state != "posted" or not panel_majority:
            return False
        self.ledger.transfer(r.account, self.releases.insurance, self.ledger.balance(r.account), "slash",
                             f"issue:{r.id}", day)
        r.state = "forfeited"
        self.ledger.record(day, "issue_junk", f"issue:{r.id}", "confirmed by a validator panel")
        self.reputation.record(r.reporter, "reporter", self.params.points_forfeited, f"issue:{r.id}", day, "forfeited")
        b = self.bounties.get(r.bounty) if r.bounty else None
        if b is not None and b.state in ("pledging", "open"):
            self._refund_inputs(b, day)
            b.state = "refunded"
        return True

    def release_unfunded(self, r: IssueStake, day: int) -> None:
        """An issue never funded, or whose bounty closed unsolved: its stake returns, with no fee."""
        if r.state == "posted" and (r.bounty is None or self.bounties[r.bounty].state in ("refunded", "unsolved")):
            self.ledger.transfer(r.account, r.reporter, self.ledger.balance(r.account), "refund",
                                 f"issue:{r.id}", day)
            r.state = "returned"

    def _link(self, b: "Bounty", report: IssueStake | None) -> None:
        if report is not None:
            if report.state != "posted" or report.bounty is not None:
                raise MarketError(f"issue:{report.id} can't back another bounty")
            b.report, report.bounty = report.id, b.id

    # ---------- bounties ----------

    def open_bounty(self, target: int, day: int, report: IssueStake | None = None, parts=(), key: str = "",
                    weight: int = 0) -> Bounty:
        """An issue becomes a bounty. In the auction it has a target, and pledges are taken until the deadline. In
        race and claim it has none (#56 D12): whoever opens it doesn't fund it; it opens at once and anyone funds it
        while it's open, so the market sets its value. The registration check refuses an issue similar to one whose
        bounty is still open or being paid (`key`: the issue as the check recognizes it). `weight`: its estimate of
        the issue's importance, the bounty's token weight (#58 D3)."""
        market = self.params.award_mode != "auction"
        if market and target:
            raise MarketError("in race and claim a bounty has no target: anyone funds it while it's open (#56 D12)")
        if market and key and self.similar_open(key) is not None:
            raise MarketError(f"a similar issue's bounty is open: {self.similar_open(key).ref} (#56 D12)")
        if not market and (target <= 0 or (self._bounty_pays() and target <= self.params.oracle_reserve)):
            raise MarketError("a bounty's target is above the oracle reserve (#43)")
        b = Bounty(len(self.bounties) + 1, target, day + self.params.bounty_deadline_days, self.ledger.open("bounty"),
                   opened=day, gate_bar_bps=self.params.gate_bar_bps, parts=[r.id for r in parts], key=key,
                   weight=weight)
        self._link(b, report)
        self.bounties[b.id] = b
        if market:
            self._open_round(b, day)
        return b

    def similar_open(self, key: str) -> Bounty | None:
        """Race and claim: the bounty still open or being paid for this issue, if any (#56 D12: one open per issue).
        Once it's paid, refunded or closed unsolved, a new bounty may open; a fix it paid still can't win (D10)."""
        return next((b for b in self.bounties.values() if b.key == key and b.state in ("open", "assigned", "won")),
                    None)

    def register(self, poster: str, day: int) -> int:
        """Race and claim (#60): the AI registration check, paid in coin by whoever opens the bounty. It writes the
        acceptance criteria the author approves, checks the size floor and estimates the effort (the simulation
        models those). It's refunded with the finder's fee if the bounty is paid (#60 D9). Refused, with nothing paid,
        without the balance. Returns the fee paid."""
        fee = self.params.registration_fee
        if self.params.award_mode == "auction" or not fee:
            return 0
        if self.ledger.balance(poster) < fee:
            raise MarketError(f"{poster} can't pay the registration check")
        self.ledger.transfer(poster, self.infrastructure, fee, "fee", f"registration:{poster}", day)
        return fee

    def pledge(self, b: Bounty, pledger: str, amount: int, day: int) -> None:
        """A pledge goes to the bounty's escrow. In the auction, before the deadline, and reaching the target opens its
        first round; in race and claim, any time it's open (#56 D12)."""
        if self.params.award_mode == "auction":
            if b.state != "pledging" or day >= b.deadline:
                raise MarketError(f"{b.ref} isn't taking pledges")
        elif b.state != "open":
            raise MarketError(f"{b.ref} isn't open to funding")
        if amount <= 0 or self.ledger.balance(pledger) < amount:
            raise MarketError(f"{pledger} can't pledge {amount}")
        self.ledger.transfer(pledger, b.account, amount, "escrow", b.ref, day)
        b.pledges[pledger] = b.pledges.get(pledger, 0) + amount
        if b.state == "pledging" and self.ledger.balance(b.account) >= b.target:
            self._open_round(b, day)

    def expire(self, day: int) -> list[Bounty]:
        """Bounties whose deadline passed below their target refund every pledge in full."""
        out = []
        for b in self.bounties.values():
            if b.state == "pledging" and day >= b.deadline:
                self._refund_inputs(b, day)  # every pledge in full, and any match back to insurance
                b.state = "refunded"
                if b.report:
                    self.release_unfunded(self.reports[b.report], day)
                out.append(b)
        return out

    def fund_treasury(self, target: int, day: int, panel_majority: bool | None = None,
                      report: IssueStake | None = None, parts=()) -> Bounty:
        """A treasury bounty for an issue nobody pledges for: within the release's budget and the cap per bounty,
        and above the approval threshold only with a validator panel's majority. The budget is issued only when
        used, so unspent budget never accumulates."""
        p = self.params
        release = self.lifecycle.release
        spent = self._treasury_spent.get(release, 0)
        if target <= 0 or target > p.treasury_bounty_cap:
            raise MarketError(f"a treasury bounty is at most {p.treasury_bounty_cap}")
        if self._bounty_pays() and target <= p.oracle_reserve:
            raise MarketError("a bounty's target is above the oracle reserve (#43)")
        if spent + target > p.treasury_budget - share(p.treasury_budget, p.matching_share_bps):
            self.ledger.record(day, "treasury_refused", f"release:{release}", f"{target} over the budget")
            raise MarketError("over the release's treasury budget")
        if target > p.treasury_approval_above:
            if panel_majority is None:
                raise NeedsPanel("a large treasury bounty needs a validator panel")
            if not panel_majority:
                self.ledger.record(day, "treasury_refused", f"release:{release}", f"{target}: panel refused")
                raise MarketError("the panel didn't approve the treasury bounty")
        b = Bounty(len(self.bounties) + 1, target, day, self.ledger.open("bounty"), treasury=True, opened=day,
                   gate_bar_bps=p.gate_bar_bps, parts=[r.id for r in parts])
        self._link(b, report)
        self.bounties[b.id] = b
        self.ledger.issue(b.account, target, "release_funding", b.ref, day)
        b.treasury_in = target
        self._treasury_spent[release] = spent + target
        self.ledger.record(day, "treasury_bounty", b.ref, f"{target} in release {release}")
        self._open_round(b, day)
        return b

    def top_up_treasury(self, b: Bounty, amount: int, day: int, panel_majority: bool | None = None) -> None:
        """With the emission on (#58 D4): the treasury funds an open bounty by topping it up, instead of opening one of
        its own, so there's still one open bounty per issue. The same budget, cap per bounty and panel as a treasury
        bounty; issued only when used."""
        p, release = self.params, self.lifecycle.release
        spent = self._treasury_spent.get(release, 0)
        if b.state != "open" or amount <= 0 or b.treasury_in + amount > p.treasury_bounty_cap:
            raise MarketError(f"a treasury top-up goes to an open bounty, at most {p.treasury_bounty_cap} in all")
        if spent + amount > p.treasury_budget - share(p.treasury_budget, p.matching_share_bps):
            self.ledger.record(day, "treasury_refused", f"release:{release}", f"{amount} over the budget")
            raise MarketError("over the release's treasury budget")
        if amount > p.treasury_approval_above:
            if panel_majority is None:
                raise NeedsPanel("a large treasury top-up needs a validator panel")
            if not panel_majority:
                self.ledger.record(day, "treasury_refused", f"release:{release}", f"{amount}: panel refused")
                raise MarketError("the panel didn't approve the treasury top-up")
        self.ledger.issue(b.account, amount, "release_funding", b.ref, day)
        b.treasury, b.treasury_in = True, b.treasury_in + amount
        self._treasury_spent[release] = spent + amount
        self.ledger.record(day, "treasury_top_up", b.ref, f"{amount} in release {release}")

    def token_weight(self, b: Bounty) -> int:
        """A bounty's token weight: the smaller of the AI's two importance estimates (#58 D3)."""
        return b.weight if b.merge_weight is None else min(b.weight, b.merge_weight)

    def _inflated(self, b: Bounty) -> bool:
        """Its registered weight is above the published multiple of the merge estimate (#58)."""
        return (self.tokens is not None and b.merge_weight is not None
                and b.weight * 100 > b.merge_weight * self.params.weight_inflation_pct)

    def token_rate(self, day: int) -> float:
        """Tokens per unit of weight, as published: pooled over the last minting periods (#58 D5); before the first
        mint, the emission over a period's worth of the weight registered so far."""
        if self.tokens is None:
            return 0.0
        if self.tokens.rate is not None:
            return self.tokens.rate
        registered = sum(b.weight for b in self.bounties.values())
        per_period = registered * self.params.release_every_days / max(1, day + 1)
        return self.tokens.emission(self.tokens.period) / per_period if per_period else 0.0

    def expected_tokens(self, b: Bounty, day: int) -> int:
        """What a solver expects the bounty to mint it: the published rate times its registered weight, less the
        reporter's share (#58 D5)."""
        if self.tokens is None:
            return 0
        reporters = self.params.token_reporter_bps if self._finders(b) else 0
        return int(self.token_rate(day) * b.weight * (BPS - reporters) / BPS)

    def price_cap(self, b: Bounty) -> int:
        """The most a price can be: what the bounty holds, leaving room for the market fee and, for a reported
        issue, the finder's fee."""
        fees = self.params.market_fee_bps + (self.params.finder_fee_bps if b.report or b.parts else 0)
        held = self.ledger.balance(b.account) - (self.params.oracle_reserve if self._bounty_pays() else 0)
        held -= sum(self.reports[r].registration for r in self._finders(b))  # refunded if it's solved (#60 D9)
        return max(0, held) * BPS // (BPS + fees)  # #49: the solver pays its checks, so no room is kept for them

    def _finders(self, b: Bounty) -> list[int]:
        """The issue stakes whose reporters share the finder's fee: the bounty's own, or a bundle's parts."""
        return ([b.report] if b.report else []) + list(b.parts)

    def offer(self, b: Bounty, day: int) -> int:
        """Race and claim: the price on offer, a share of the price cap. The share opens at start_price_bps and rises
        daily until the first attempt or claim locks it (#60 D9). The share is locked, not the amount (#56 D14): later
        pledges raise the price, so every funder pays the same fraction. The rest of the funds is refunded when the
        bounty is paid."""
        return share(self.price_cap(b), self.offer_bps(b, day))

    def quote(self, b: Bounty, day: int) -> dict:
        """Race: what a solver pays to try this bounty and could earn, as `Quoter.quote` reads it on-chain (#56 task
        3.2). Open: the price a win would pay now (the rising share until the first attempt locks it), and the day it
        sunsets with no checked submission. Won or paid: the award's price. Instalments are price // n, the last one
        what's left; the finder's fee is the reporter's share of the price."""
        p, n = self.params, self.params.reward_instalments
        price = self.offer(b, day) if b.state == "open" else b.price if b.state in ("won", "paid") else 0
        return {
            "state": b.state, "offerBps": self.offer_bps(b, day), "cap": self.price_cap(b), "price": price,
            "instalment": price // n, "lastInstalment": price - price // n * (n - 1),
            "finderFee": share(price, p.finder_fee_bps) if self._finders(b) else 0,
            "attempting": len(b.attempting),
            "sunsetDay": b.idle_since + p.bounty_max_rounds * p.round_days if b.state == "open" else 0,
            "attemptFee": p.attempt_fee, "checkDeposit": self.deposit(), "evaluationFee": p.evaluation_fee,
            "appealFee": p.rerun_appeal_fee,
        }

    def offer_bps(self, b: Bounty, day: int) -> int:
        if b.lock_bps is not None:
            return b.lock_bps
        p, start = self.params, b.offer_from if b.offer_from is not None else day
        return min(BPS, p.start_price_bps + p.price_rise_bps_per_day * max(0, day - start))

    def reserve(self, b: Bounty) -> int:
        """The most any price can be: a published share of the cap, so a lone bid or a ring can't take the whole
        cap (#40 design D1)."""
        reserve = share(self.price_cap(b), self.params.reserve_bps)
        return reserve if b.reserve_limit is None else min(reserve, b.reserve_limit)

    # ---------- quadratic matching (#34) ----------

    def match(self, day: int) -> dict[int, int]:
        """At a release's opening, the matching share of the treasury budget matches bounties still gathering
        pledges by weight, (sum of the square roots of each pledger's pledges)^2 less the pledges, scaled to fit,
        capped at match_cap_bps of the target and at what's missing. In race and claim, where there's no target
        (#56 D12), bounties gather pledges while open with their price's share not yet locked, and a match is capped at
        match_cap_bps of their pledges. Returns each match."""
        p, release = self.params, self.lifecycle.release
        budget = share(p.treasury_budget, p.matching_share_bps) - self._match_spent.get(release, 0)
        auction = p.award_mode == "auction"
        pledging = [b for b in sorted(self.bounties.values(), key=lambda b: b.id)
                    if b.state == "pledging" or (not auction and b.state == "open" and b.lock_bps is None and b.pledges)]
        def trust(pledger: str) -> float:  # each pledger weighted by its funder trust (#37)
            return self.reputation.trust_bps(pledger, "funder") / BPS

        weights = {b.id: max(0.0, sum(trust(k) * math.sqrt(v) for k, v in b.pledges.items()) ** 2
                             - sum(trust(k) ** 2 * v for k, v in b.pledges.items()))
                   for b in pledging}
        total = sum(weights.values())
        if budget <= 0 or total <= 0:
            return {}
        scale = min(1.0, budget / total)
        out = {}
        for b in pledging:
            if auction:
                room = min(share(b.target, p.match_cap_bps) - b.matched, b.target - self.ledger.balance(b.account))
            else:
                room = share(sum(b.pledges.values()), p.match_cap_bps) - b.matched
            amount = max(0, min(int(weights[b.id] * scale), room, budget))
            if not amount:
                continue
            self.ledger.issue(b.account, amount, "release_funding", b.ref, day)
            b.matched += amount
            b.treasury_in += amount
            budget -= amount
            self._match_spent[release] = self._match_spent.get(release, 0) + amount
            out[b.id] = amount
            self.ledger.record(day, "matched", b.ref, f"{amount} in release {release}")
            if b.state == "pledging" and self.ledger.balance(b.account) >= b.target:
                self._open_round(b, day)
        return out

    def stake_for(self, b: Bounty, risk: str = "normal", solver: str | None = None) -> int:
        """A share of the cap, times risk, lowered by the solver's trust down to bond_discount_bps off (#37)."""
        p = self.params
        if risk not in p.risk_multiplier:
            raise MarketError(f"unknown risk class {risk!r}")
        stake = share(self.price_cap(b), p.bounty_stake_bps) * p.risk_multiplier[risk]
        if solver is not None and p.bond_discount_bps:
            earned = self.reputation.trust_bps(solver, "solver") - p.trust_floor_bps
            stake -= share(stake, p.bond_discount_bps * earned // (BPS - p.trust_floor_bps))
        return stake

    def priority(self, value: int, reporter: str | None) -> int:
        """How the treasury ranks an unpledged issue: its value times the reporter's trust (#37)."""
        if reporter is None:
            return share(value, self.params.trust_floor_bps)
        return share(value, self.reputation.trust_bps(reporter, "reporter"))

    # ---------- sealed rounds for the job ----------

    def commit(self, b: Bounty, solver: str, commitment: str, day: int, risk: str = "normal") -> Entry:
        """Bid for the job with a sealed price, locking the stake and the evaluation fee. Refused, with nothing
        locked, after the deadline or without the balance."""
        if b.state != "open" or b.round_deadline is None or day >= b.round_deadline:
            raise MarketError(f"{b.ref} has no round open for bids")
        stake = self.stake_for(b, risk, solver)
        if stake < 1 or self.ledger.balance(solver) < stake + self.deposit():
            raise MarketError(f"{solver} can't cover the stake and check deposit")
        e = Entry(len(self.entries) + 1, b.id, solver, commitment, risk, self.ledger.open("entry"), day,
                  round=b.rounds, stake=stake, fee_held=self.deposit())
        self.ledger.transfer(solver, e.account, stake + e.fee_held, "stake", b.ref, day)
        self.entries[e.id] = e
        b.entries.append(e)
        return e

    def reveal(self, e: Entry, price: int, salt: str, day: int) -> bool:
        """After the deadline, a bidder reveals its price; a reveal that doesn't match the commitment, or a price
        above the reserve, voids the bid. Returns whether it counts."""
        b = self.bounties[e.bounty]
        if e.state != "committed" or b.round_deadline is None or day < b.round_deadline:
            raise MarketError("reveals open after the round's deadline")
        if seal(price, salt) != e.commitment or not 0 < price <= self.reserve(b):
            e.state = "void"
            return False
        e.price, e.state = price, "revealed"
        return True

    def close_round(self, b: Bounty, day: int) -> Entry | None:
        """Settle the round: void or unrevealed bids lose their fee; the cheapest revealed bid is assigned the job
        at the second price (or the reserve); every other bid gets its stake and fee back and is queued as a
        runner-up. Without a bid, a new round opens. Returns the assigned bid."""
        if b.state != "open" or b.round_deadline is None or day < b.round_deadline:
            raise MarketError(f"{b.ref} has no round to close")
        current = [e for e in b.entries if e.round == b.rounds]
        for e in current:
            if e.state != "revealed":
                e.state = "void"
                self._forfeit_fee(e, b, day)
                self._release_stake(e, b, day)
        b.queue = sorted((e for e in current if e.state == "revealed"), key=lambda e: (e.price, e.id))
        if not b.queue:
            b.empty_rounds += 1
            if b.empty_rounds >= self.params.bounty_max_rounds:
                self._close_unsolved(b, day)  # no one can do it: funds back by input, the stake back (#34)
            else:
                self._open_round(b, day)
            return None
        b.empty_rounds = 0
        first = b.queue.pop(0)
        for e in b.queue:  # runners-up keep their price and place, not their money
            self._refund_fee(e, b, day)
            self._release_stake(e, b, day)
            e.state = "queued"
        return self._assign(b, first, day)

    # ---------- the race and the claim (#60) ----------

    def _mode(self, b: Bounty, mode: str) -> None:
        if self.params.award_mode != mode or b.state != "open":
            raise MarketError(f"{b.ref} isn't open to {mode}")

    def race_start(self, b: Bounty, solver: str, day: int = 0) -> None:
        """A solver starts an attempt, paying the attempt fee, never refunded (#64); the number of attempts in
        progress is published. The first attempt locks the rising price's share (#60 D9; #56 D14 measured locking on
        the first submission instead: funders paid 30 % more and fake attempts paid). Refused, with nothing paid,
        without the balance."""
        self._mode(b, "race")
        fee = self.params.attempt_fee
        if self.ledger.balance(solver) < fee:
            raise MarketError(f"{solver} can't pay the attempt fee")
        if fee:
            self.ledger.transfer(solver, self.infrastructure, fee, "fee", b.ref, day)
        if b.lock_bps is None:
            b.lock_bps = self.offer_bps(b, day)
        b.attempting.add(solver)

    def published_attempts(self, b: Bounty) -> int:
        """The attempts in progress, as published: all of them, or only those by solvers with earned reputation, so
        accounts with no record can't make a bounty look crowded (#64)."""
        if self.params.published_attempts == "all":
            return len(b.attempting)
        return sum(1 for s in b.attempting if self.reputation.score(s, "solver") > 0)

    def race_stop(self, b: Bounty, solver: str, day: int) -> None:
        """An attempt ends without a submission (the bounty was won or closed, or the solver gave up). It doesn't
        restart the idle clock (owner, 2026-10-29): attempts can't keep a dead bounty alive."""
        b.attempting.discard(solver)
        if not b.attempting and b.state == "open":
            b.stopped_on = day

    def race_submit(self, b: Bounty, solver: str, day: int, risk: str = "normal", fix: str = "") -> Entry | None:
        """A sealed submission with the contribution's stake and the check deposit. It's checked now, in arrival
        order; once the bounty is won, a later submission isn't checked and pays the evaluation fee (#64; returns
        None). A fix the AI similarity check recognizes as a failed submission's (`fix`, its fingerprint) is rejected
        unchecked, from any account, for the evaluation fee (#60 D9), unless an appeal found it independent; so is a
        fix already paid on another bounty, a twin tracking the same issue (#56 D10: one fix, one payout). Refused,
        with nothing locked, without the balance: a late submission needs the whole evaluation fee, and one rejected
        unchecked the whole check deposit, as on-chain (owner, 2026-10-29: the contract can't take what's there)."""
        if self.params.award_mode != "race":
            raise MarketError("submissions race only in the race mode")
        unchecked = b.state == "open" and bool(fix) and (
            (fix in b.failed_fixes or self.fix_paid_elsewhere(b, fix)) and (solver, fix) not in b.cleared)
        need = self.params.evaluation_fee if b.state != "open" else self.deposit() if unchecked else 0
        if need and self.ledger.balance(solver) < max(need, self.params.evaluation_fee):
            raise MarketError(f"{solver} can't cover the {'evaluation fee' if b.state != 'open' else 'check deposit'}")
        b.attempting.discard(solver)
        if b.state in ("unsolved", "refunded"):  # it closed without a winner: on-chain the commit is refused
            raise MarketError(f"bounty {b.id} closed unsolved")
        if b.state != "open":
            self._evaluation_fee(b, solver, day)
            self.ledger.record(day, "too_late", b.ref, f"{solver}: already won")
            return None
        if fix and fix in b.failed_fixes and (solver, fix) not in b.cleared:
            self._evaluation_fee(b, solver, day)
            self.ledger.record(day, "duplicate_rejected", b.ref, f"{solver}: a failed submission's fix")
            return None
        if self.fix_paid_elsewhere(b, fix) and (solver, fix) not in b.cleared:
            self._evaluation_fee(b, solver, day)
            self.ledger.record(day, "paid_elsewhere", b.ref, f"{solver}: bounty:{self.paid_fixes[fix]} pays this fix")
            return None
        if b.lock_bps is None:
            b.lock_bps = self.offer_bps(b, day)  # a submission without an attempt locks it too
        e = self._take(b, solver, day, day, risk)
        e.commitment = fix
        return e

    def fix_paid_elsewhere(self, b: Bounty, fix: str) -> bool:
        """Race: whether the similarity check recognizes this fix as one another bounty already pays (#56 D10). Twin
        bounties may track the same issue, but each needs its own fix; paying one never closes another."""
        return bool(fix) and self.paid_fixes.get(fix, b.id) != b.id

    def merged(self, c: Contribution, day: int) -> None:
        """A race's winning fix is merged and its payment starts: it's paid, so it can't win a twin bounty (#56 D10).
        A clawback doesn't unregister it."""
        b = self._by_contribution.get(c.id)
        if self.tokens is not None and b is not None and self.weigh_at_merge is not None:
            b.merge_weight = self.weigh_at_merge(b)  # the second, independent estimate (#58 D3)
        e = self._entry_of.get(c.id)
        if self.params.award_mode == "race" and e is not None and e.commitment:
            self.paid_fixes.setdefault(e.commitment, e.bounty)
            self.ledger.record(day, "fix_paid", f"bounty:{e.bounty}", f"contribution:{c.id}")

    def _evaluation_fee(self, b: Bounty, solver: str, day: int) -> None:
        fee = min(self.params.evaluation_fee, self.ledger.balance(solver))
        if fee:
            self.ledger.transfer(solver, self.infrastructure, fee, "fee", b.ref, day)

    def appeal_duplicate(self, b: Bounty, solver: str, fix: str, day: int, votes: list[tuple[str, int, bool]]) -> bool:
        """Race (#64): a submitter whose fix was rejected as a failed fix's duplicate (or as paid elsewhere, #56 D10)
        appeals, paying the appeal fee and each juror's verdict fee. `votes`: (evaluator, its fee, whether it found
        the fix independent), from a jury of duplicate_appeal_jury drawn one per provider first. A majority for
        independent clears the fix: its next submission is checked like any. Returns whether it was cleared. Refused,
        with nothing paid, without the balance."""
        self._mode(b, "race")
        if len(votes) != self.params.duplicate_appeal_jury:
            raise MarketError("the appeal jury has the published size")
        cost = self.params.rerun_appeal_fee + sum(fee for _, fee, _ in votes)
        if self.ledger.balance(solver) < cost:
            raise MarketError(f"{solver} can't cover the duplicate appeal")
        self.ledger.transfer(solver, self.infrastructure, self.params.rerun_appeal_fee, "fee", b.ref, day)
        for evaluator, fee, _ in votes:
            if fee:
                self.ledger.transfer(solver, evaluator, fee, "payout", b.ref, day)
        cleared = sum(1 for _, _, independent in votes if independent) * 2 > len(votes)
        if cleared:
            b.cleared.add((solver, fix))
        self.ledger.record(day, "duplicate_appeal", b.ref, f"{solver}: {'independent' if cleared else 'duplicate'}")
        return cleared

    def race_appeal(self, failed: Entry, day: int) -> Entry:
        """Race: a failed submission's author appeals once, at its own cost (the appeal fee besides a new deposit):
        the same fix is checked again, judged by the second jury (#60 D9)."""
        b = self.bounties[failed.bounty]
        if failed.state != "failed" or failed.appeal or failed.id in b.appealed:
            raise MarketError("only a failed submission is appealed, once")
        self._mode(b, "race")
        fee = self.params.rerun_appeal_fee
        if self.ledger.balance(failed.solver) < fee + self.stake_for(b, failed.risk, failed.solver) + self.deposit():
            raise MarketError(f"{failed.solver} can't cover the appeal")
        self.ledger.transfer(failed.solver, self.infrastructure, fee, "fee", b.ref, day)
        b.appealed.add(failed.id)
        e = self._take(b, failed.solver, day, day, failed.risk)
        e.commitment, e.appeal = failed.commitment, True
        return e

    def claim(self, b: Bounty, solver: str, day: int, days: int, risk: str = "normal") -> Entry:
        """A solver claims the bounty with its bond and the check deposit, for `days` of exclusive time; the first
        claim locks the rising price's share."""
        self._mode(b, "claim")
        if b.lock_bps is None:
            b.lock_bps = self.offer_bps(b, day)
        return self._take(b, solver, day, day + days, risk)

    def _take(self, b: Bounty, solver: str, day: int, deliver_by: int, risk: str) -> Entry:
        stake = self.stake_for(b, risk, solver)  # 0 in a race without stakes (#56 D9), or a bounty of 0 coin (#58)
        zero_coin = self.tokens is not None and self.price_cap(b) == 0
        if ((stake < 1 and self.params.bounty_stake_bps and not zero_coin)
                or self.ledger.balance(solver) < stake + self.deposit()):
            raise MarketError(f"{solver} can't cover the stake and check deposit")
        e = Entry(len(self.entries) + 1, b.id, solver, "", risk, self.ledger.open("entry"), day, round=b.rounds,
                  stake=stake, fee_held=self.deposit())
        self.ledger.transfer(solver, e.account, stake + e.fee_held, "stake", b.ref, day)
        self.entries[e.id] = e
        b.entries.append(e)
        price = self.offer(b, day) if b.lock_bps is not None else self.price_cap(b)  # funders and time set it: no bid
        b.assigned, b.price, b.state = e, min(price, self.price_cap(b)), "assigned"
        b.assignments += 1
        e.state, e.deliver_by = "assigned", deliver_by
        self.ledger.record(day, "claimed" if deliver_by > day else "submitted", b.ref, f"entry {e.id} at {b.price}")
        return e

    def top_up(self, b: Bounty, pledger: str, amount: int, day: int) -> None:
        """Race and claim: a funder raises an open bounty's price (#60). Refused without the balance."""
        if self.params.award_mode == "auction":
            raise MarketError("in the auction, funders pledge before the rounds")
        self.pledge(b, pledger, amount, day)

    def close_idle(self, day: int) -> list[Bounty]:
        """Race and claim: an open bounty closes unsolved, its funds returned by input, as long as an auction's empty
        rounds would take after it opened, reopened or had a submission checked. Attempts in progress don't hold it
        open (owner, 2026-10-29): they end with it, their effort lost."""
        out = []
        if self.params.award_mode == "auction":
            return out
        limit = self.params.bounty_max_rounds * self.params.round_days
        for b in self.bounties.values():
            if b.state == "open" and day - b.idle_since >= limit:
                self._close_unsolved(b, day)
                out.append(b)
        return out

    # ---------- assignment and delivery ----------

    def _assign(self, b: Bounty, e: Entry, day: int) -> Entry:
        price = b.queue[0].price if b.queue else self.reserve(b)
        b.assigned, b.price, b.state = e, min(price, self.reserve(b)), "assigned"
        b.assignments += 1
        e.state, e.deliver_by = "assigned", day + self.params.delivery_days
        self.ledger.record(day, "assigned", b.ref, f"bid {e.id} at {b.price}, deliver by day {e.deliver_by}")
        return e

    def deliver(self, e: Entry, lines: int, day: int, passes: bool) -> Contribution | None:
        """The assigned solver delivers; `passes` is the deterministic gate's verdict. A passing delivery in time
        becomes the winning contribution, with the bond as its stake and the fee refunded; otherwise the delivery
        fails (see `fail`). Returns the contribution, or None."""
        b = self.bounties[e.bounty]
        if e.state != "assigned" or b.assigned is not e:
            raise MarketError("only the assigned bid delivers")
        if day > e.deliver_by or lines < 1:
            self.fail(e, day)
            return None
        if not passes:
            self.fail(e, day, attempted=True)
            return None
        self._refund_fee(e, b, day)
        self._release_stake(e, b, day)
        try:
            c = self.lifecycle.submit(e.solver, lines, day, e.risk, stake=e.stake)
        except LifecycleError:
            e.state = "failed"
            self._next(b, day)
            return None
        self.lifecycle.run_checks(c, True, day)  # it passed the gate
        e.state = "delivered"
        self._entry_of[c.id] = e
        if getattr(self.releases, "challenges", None) is not None:
            self.releases.challenges.issue_of[c.id] = b.ref  # its issue's cases can now prove it unsolved (#43)
        b.contribution, b.state, b.won_day = c.id, "won", day
        self._by_contribution[c.id] = b
        self.ledger.record(day, "delivered", b.ref, f"bid {e.id} as contribution:{c.id} at {b.price}")
        return c

    def parties(self, b: Bounty) -> set[str]:
        """Everyone who bid for this bounty's job, or is racing for it: none of them checks its deliveries (#43)."""
        return {x.solver for x in b.entries} | b.attempting

    def deliver_checked(self, e: Entry, lines: int, day: int, reruns, jury=None, second=None,
                        hidden_passes: bool = True, gates_pass: bool = True) -> Contribution | None:
        """A delivery through the checking layer (#43): it passes if its re-runs of the public checks passed, the
        system's runner passed the hidden tests, and its jury accepted it by consensus, or, for a split, the second
        jury did, and (race and claim, #60) it passed the project's constitution. No person decides it. The jobs
        must be closed and name this bid; no bidder may sit on them."""
        ref = f"entry:{e.id}"
        jobs = [j for j in (jury, second) if j is not None]
        if reruns.ref != ref or reruns.state == "open" or any(j.ref != ref or j.state == "open" for j in jobs):
            raise MarketError("the delivery's checks aren't closed, or aren't this bid's")
        b = self.bounties[e.bounty]
        bidders = self.parties(b)
        if bidders & set(reruns.members) or any(bidders & set(j.members) for j in jobs):
            raise MarketError("a bidder on this bounty sat on its checks")
        if self.checking is not None:
            self._pay_checks(e, b, reruns, jobs, day, lines)
        passes = gates_pass and reruns.outcome is True and hidden_passes and jury is not None and (
            jury.outcome == "accept" or (jury.outcome == "escalate" and second is not None and second.outcome == "accept"))
        if jury is not None and not passes and self.checking is not None:
            self.checking.unscored(ref, day)  # rejected: its truth is never revealed, so its verdicts are only work
        if (not passes and self.params.split_rejection_keeps_bond and reruns.outcome is True and hidden_passes
                and gates_pass and jury is not None and jury.outcome == "escalate"):
            return self._split_rejected(e, day)
        if reruns.outcome is None and self.params.split_rejection_keeps_bond:  # the runners never agreed:
            return self._split_rejected(e, day, "CI inconclusive")  # flaky tests aren't the solver's failure
        return self.deliver(e, lines, day, passes)

    def deposit(self) -> int:
        """What a bid posts besides its stake: the check deposit, one full attempt's oracle fees, when the solver
        pays its checks (#49); otherwise the evaluation fee."""
        if self.checking is not None and self.params.checks_paid_by == "solver":
            return max(self.gas_reserve() if self.check_gas is not None else self.params.oracle_reserve,
                       self.params.evaluation_fee)
        return self.params.evaluation_fee

    def gas_reserve(self) -> int:
        """#85 S15: the deposit's ceiling under check gas: both juries' seats at the per-verdict caps at the dearest
        family, plus the service fee each, and every runner's run at the CI profile's limits, plus the relayer's gas
        allowance."""
        from . import checkgas as G
        p, t = self.params, self.check_gas
        seats = p.jury_size + p.second_jury_size
        runs = p.ci_runners if p.ci_mode == "attested" else p.rerun_validators + 1
        return credits(G.deposit_max(t, seats, list(G.SIM_FAMILIES.values()), ci_runs=runs))

    def _bounty_pays(self) -> bool:
        return self.checking is not None and self.params.checks_paid_by == "bounty"

    def _pay_checks(self, e: Entry, b: Bounty, reruns, jobs, day: int, lines: int | None = None) -> int:
        """Each check run on the delivery is paid its oracle fee: from the solver's deposit (#49), or, in #43's rule,
        from the bounty. Under check gas (#85 S15) a run is paid its sandbox usage and a counted verdict its family's
        usage at the table's unit prices plus the service fee. Returns what was paid."""
        p = self.params
        if self.check_gas is not None and lines is not None:
            from . import checkgas as G
            run_fee = credits(G.sim_run(self.check_gas, lines))
            fam = self.checking.evaluators
            due = [(m, run_fee) for m in self.checking.runs_due(reruns)]
            if p.ci_mode == "validators":
                due.append((self.infrastructure, run_fee))
            due += [(m, credits(G.sim_verdict(self.check_gas, fam[m].family if m in fam else "", lines)))
                    for j in jobs for m in self.checking.verdicts_due(j)]
        else:
            due = [(m, p.run_fee) for m in self.checking.runs_due(reruns)]
            if p.ci_mode == "validators":  # the system's runner, for the hidden tests
                due.append((self.infrastructure, p.run_fee))
            due += [(m, self.checking.verdict_fee(m)) for j in jobs for m in self.checking.verdicts_due(j)]
        payer, paid = (b.account, 0) if self._bounty_pays() else (e.account, 0)
        for to, fee in due:
            amount = min(fee, self.ledger.balance(payer) if self._bounty_pays() else e.fee_held)
            if amount > 0:
                self.ledger.transfer(payer, to, amount, "payout", b.ref, day)
                paid += amount
                if not self._bounty_pays():
                    e.fee_held -= amount
        return paid

    def _settle_deposit(self, e: Entry, b: Bounty, day: int, checked: bool) -> None:
        """After a delivery: if its checks were paid from the deposit, the rest returns; otherwise (no checks ran,
        or the bounty paid them) the evaluation fee is forfeited and the rest returns."""
        if checked and self.checking is not None and not self._bounty_pays():
            self._refund_fee(e, b, day)
        else:
            self._forfeit_fee(e, b, day)

    def _split_rejected(self, e: Entry, day: int, why: str = "rejected on a split") -> None:
        """No clear failure (the first jury split and the second rejected, or the CI runners never agreed): the bond
        returns; the fee pays for the checks, the attempt is published and the bounty reopens, as for any failed
        attempt."""
        b = self.bounties[e.bounty]
        if e.state != "assigned" or b.assigned is not e:
            raise MarketError("only the assigned bid delivers")
        self._settle_deposit(e, b, day, checked=True)
        self._release_stake(e, b, day)
        e.state = "failed"
        self.ledger.record(day, "rejected_on_split", b.ref, f"bid {e.id}: {why}, bond returned")
        self.reputation.record(e.solver, "solver", 0, b.ref, day, why)
        return self._reopen(b, e, day)

    def fail(self, e: Entry, day: int, attempted: bool = False) -> Entry | None:
        """A failed or late delivery: the bond goes to the bounty, the fee to the checking costs. A delivered attempt
        that failed is published, its hidden tests are burned, and a fresh round opens (#43); a late one offers the
        job to the next queued bid. Returns the newly assigned bid, if any."""
        b = self.bounties[e.bounty]
        bond = self.ledger.balance(e.account) - e.fee_held
        if self.params.award_mode == "race":  # no bond in the race (#60): the stake returns
            self._release_stake(e, b, day)
        elif bond > 0:
            self.ledger.transfer(e.account, b.account, bond, "slash", b.ref, day)
        self._settle_deposit(e, b, day, checked=attempted)
        e.state = "failed"
        self.ledger.record(day, "delivery_failed", b.ref, f"bid {e.id}, bond {bond} to the bounty")
        self.reputation.record(e.solver, "solver", self.params.points_failed, b.ref, day, "delivery failed")
        if attempted:
            return self._reopen(b, e, day)
        return self._next(b, day)

    def _reopen(self, b: Bounty, e: Entry, day: int) -> Entry | None:
        """A failed attempt is public now: everyone bids again on what's left, and the hidden tests it faced are
        burned (#43). With failed_reopens_round off, the queue as before."""
        b.hidden_set += 1
        self.ledger.record(day, "hidden_tests_burned", b.ref, f"set {b.hidden_set - 1} retired after bid {e.id}")
        if self.params.award_mode == "race" and e.commitment:
            b.failed_fixes.add(e.commitment)  # recognized if resubmitted (#60 D9)
        if not self.params.failed_reopens_round:
            return self._next(b, day)
        b.published.append(e.id)
        if self.params.reopen_at_last_price and b.price:  # less is left to do than the market priced it at
            b.reserve_limit = b.price if b.reserve_limit is None else min(b.reserve_limit, b.price)
        self.ledger.record(day, "attempt_published", b.ref, f"bid {e.id}, reserve now {self.reserve(b)}")
        for q in b.queue:
            q.state = "released"
        b.queue, b.contribution = [], None
        self._open_round(b, day)
        return None

    def expire_deliveries(self, day: int) -> list[Entry]:
        """Assigned bids past their delivery deadline fail. Returns the bids assigned in their place."""
        out = []
        for b in list(self.bounties.values()):
            e = b.assigned
            if b.state == "assigned" and e is not None and e.deliver_by is not None and day > e.deliver_by:
                nxt = self.fail(e, day)
                if nxt is not None:
                    out.append(nxt)
        return out

    def _next(self, b: Bounty, day: int) -> Entry | None:
        """Offer the job to the next queued bid that can post its stake again (at the next queued price or the
        reserve); with none left, a new round opens."""
        while b.queue:
            e = b.queue.pop(0)
            stake = self.stake_for(b, e.risk, e.solver)
            if self.ledger.balance(e.solver) < stake + self.deposit() or stake < 1:
                e.state = "skipped"
                continue
            e.stake, e.fee_held = stake, self.deposit()
            self.ledger.transfer(e.solver, e.account, stake + e.fee_held, "stake", b.ref, day)
            return self._assign(b, e, day)
        b.assigned, b.contribution = None, None
        self._open_round(b, day)
        return None

    # ---------- payment ----------

    def payment_for(self, c: Contribution) -> tuple[int, str]:
        """The winner's price and the bounty it's escrowed from (release payouts ship it)."""
        b = self._by_contribution[c.id]
        return min(b.price, self.price_cap(b)), b.account

    def pay_fee(self, c: Contribution, day: int) -> int:
        """The market fee on the escrowed price, from the bounty, in the published proportions; the owner's part
        vests like its release share. Returns the fee."""
        b = self._by_contribution[c.id]
        fee = min(share(c.reward, self.params.market_fee_bps), self.ledger.balance(b.account))
        targets, left = self.releases.fee_targets(), fee
        for i, name in enumerate(FEE_SHARES):
            amount = left if i == len(FEE_SHARES) - 1 else share(fee, self.params.market_fee_split_bps[name])
            if amount:
                self.ledger.transfer(b.account, targets[name], amount, "payout", b.ref, day)
                if name == "owner":
                    self.releases.owner_tranche(amount, day)
            left -= amount
        return fee

    def settle(self, day: int) -> list[Entry]:
        """Follow each won bounty's contribution: fully paid means the bounty is paid and its leftover refunded; a
        slash, clawback or decline offers the job to the next queued bid (or opens a new round). Returns the bids
        newly assigned."""
        out = []
        for b in list(self.bounties.values()):
            if b.state != "won":
                continue
            c = self.lifecycle.contributions[b.contribution]
            if c.state == "accepted" and c.id not in self._credited:
                self._credit(b, c, day)
            if c.state in ("slashed", "declined", "withdrawn", "failed_checks") or c.clawed_back:
                self.ledger.record(day, "bounty_reopened", b.ref, f"contribution:{c.id} {c.state}")
                if c.state == "slashed" or c.clawed_back:
                    self.reputation.record(c.contributor, "solver", self.params.points_slashed, b.ref, day,
                                           "clawed back" if c.clawed_back else "slashed")
                    self._resolve(c, False, day)
                    self._add_cases(b, c, day)
                nxt = self._reopen(b, self._entry_of[c.id], day) if c.id in self._entry_of else self._next(b, day)
                if nxt is not None:
                    out.append(nxt)
            elif c.state == "accepted" and c.instalments_left == 0 and not c.open_challenges:
                self._resolve(c, True, day)
                self._finish(b, day)
        return out

    def _credit(self, b: Bounty, c: Contribution, day: int) -> None:
        """The fix was accepted (its window closed without an upheld challenge): its solver, its reporter and its
        funders (at least the minimum pledge) earn their points now; a later clawback still costs the solver."""
        rep, p = self.reputation, self.params
        self._credited.add(c.id)
        rep.record(c.contributor, "solver", p.points_paid, b.ref, day, "accepted")
        r = self.reports.get(b.report) if b.report else None
        if r is not None and r.state == "posted":
            rep.record(r.reporter, "reporter", p.points_rewarded, b.ref, day, "fix accepted")
        for pledger, amount in sorted(b.pledges.items()):
            if amount >= p.reputation_min_pledge:
                rep.record(pledger, "funder", p.points_paid, b.ref, day, "funded an accepted fix")

    def _finish(self, b: Bounty, day: int) -> None:
        """The bounty is paid: the reporter gets its stake back with the finder's fee, then the leftover returns in
        proportion to what each source put in (#34). If its registered weight was inflated, its reporters forfeit the
        finder's fee, which returns to its funders with the leftover, and their tokens (#58)."""
        b.inflated = self._inflated(b)
        if b.inflated:
            self.ledger.record(day, "weight_inflated", b.ref, f"registered {b.weight}, merged {b.merge_weight}")
            for rid in self._finders(b):
                self.reputation.record(self.reports[rid].reporter, "reporter", self.params.points_forfeited, b.ref,
                                       day, "inflated importance")
        r = self.reports.get(b.report) if b.report else None
        if r is not None and r.state == "posted":
            fee = 0 if b.inflated else min(share(b.price, self.params.finder_fee_bps), self.ledger.balance(b.account))
            if fee:
                self.ledger.transfer(b.account, r.reporter, fee, "reward", b.ref, day)
            self.ledger.transfer(r.account, r.reporter, self.ledger.balance(r.account), "refund", f"issue:{r.id}", day)
            r.state = "rewarded"
            self._refund_registration(b, r, day)
        if b.parts:  # a bundle: its parts' reporters share the finder's fee, each with its registration back (#60)
            fee = 0 if b.inflated else min(share(b.price, self.params.finder_fee_bps), self.ledger.balance(b.account))
            for i, rid in enumerate(b.parts):
                part = self.reports[rid]
                amount = fee // len(b.parts) + (fee % len(b.parts) if i == len(b.parts) - 1 else 0)
                if amount:
                    self.ledger.transfer(b.account, part.reporter, amount, "reward", b.ref, day)
                self._refund_registration(b, part, day)
        self._refund_inputs(b, day)
        b.state = "paid"
        if self.tokens is not None:  # it closed paid: it shares the period's emission by its weight (#58)
            reporters = [] if b.inflated else [self.reports[r].reporter for r in self._finders(b)
                                               if self.reports[r].state != "forfeited"]
            solver = self.lifecycle.contributions[b.contribution].contributor
            self.tokens.record(b.ref, self.token_weight(b), solver, reporters)
        self._publish_evidence(b, day)

    def _refund_registration(self, b: Bounty, r: IssueStake, day: int) -> None:
        amount = min(r.registration, self.ledger.balance(b.account))
        if amount:
            self.ledger.transfer(b.account, r.reporter, amount, "refund", b.ref, day)

    def _add_cases(self, b: Bounty, c: Contribution, day: int) -> None:
        """An upheld "not solved" proof's case joins the bounty's public definition of solved (#43)."""
        ch = getattr(self.releases, "challenges", None)
        if ch is None:
            return
        for x in ch.challenges.values():
            if x.contribution is c and x.proof.kind == "not_solved" and x.outcome:
                b.cases.append(x.proof.description)
                self.ledger.record(day, "case_added", b.ref, x.proof.description)

    def _resolve(self, c: Contribution, good: bool, day: int) -> None:
        """The delivery's fate is known: its jury is scored on it (#43)."""
        e = self._entry_of.get(c.id)
        if self.checking is not None and e is not None:
            self.checking.resolve(f"entry:{e.id}", good, day)

    def _publish_evidence(self, b: Bounty, day: int) -> None:
        """The bounty is settled: its juries' cited evidence can be published now (#43). Earlier, it would teach the
        next solver how to fool the judges."""
        if self.checking is not None:
            for x in b.entries:
                self.checking.publish_evidence(f"entry:{x.id}", day)

    def _close_unsolved(self, b: Bounty, day: int) -> None:
        self._refund_inputs(b, day)
        b.state = "unsolved"
        self._publish_evidence(b, day)
        self.ledger.record(day, "bounty_unsolved", b.ref, f"{b.empty_rounds} rounds without a bid")
        if b.report:
            self.release_unfunded(self.reports[b.report], day)

    def _refund_inputs(self, b: Bounty, day: int) -> None:
        """What's left returns in proportion to what each source put in: pledgers their share, the treasury's (a
        treasury bounty's funding or matches) to insurance, rounded down, the remainder to the last."""
        left = self.ledger.balance(b.account)
        if not left:
            return
        inputs = sorted(b.pledges.items()) + ([(self.releases.insurance, b.treasury_in)] if b.treasury_in else [])
        total = sum(v for _, v in inputs)
        if not total:
            self.ledger.transfer(b.account, self.releases.insurance, left, "refund", b.ref, day)
            return
        rest = left
        for i, (who, put_in) in enumerate(inputs):
            amount = rest if i == len(inputs) - 1 else left * put_in // total
            if amount:
                self.ledger.transfer(b.account, who, amount, "refund", b.ref, day)
            rest -= amount

    # ---------- internals ----------

    def _open_round(self, b: Bounty, day: int) -> None:
        if self.params.award_mode != "auction":  # open to attempts or claims (#60): no rounds
            b.state, b.round_deadline, b.assigned, b.idle_since = "open", None, None, day
            if b.offer_from is None:
                b.offer_from = day
            b.rounds += 1
            self.ledger.record(day, "open", b.ref, f"price {self.price_cap(b)}")
            return
        b.state, b.round_deadline, b.assigned = "open", day + self.params.round_days, None
        b.rounds += 1
        self.ledger.record(day, "round_opened", b.ref, f"round {b.rounds}, cap {self.price_cap(b)}")

    def _release_stake(self, e: Entry, b: Bounty, day: int) -> None:
        """The stake goes back; a fee still held stays in the bid's account."""
        amount = self.ledger.balance(e.account) - e.fee_held
        if amount > 0:
            self.ledger.transfer(e.account, e.solver, amount, "refund", b.ref, day)

    def _forfeit_fee(self, e: Entry, b: Bounty, day: int) -> None:
        """The evaluation fee goes to the checking costs; anything else still held (the rest of a check deposit,
        #49) returns."""
        fee = min(e.fee_held, self.params.evaluation_fee)
        if fee:
            self.ledger.transfer(e.account, self.infrastructure, fee, "fee", b.ref, day)
            e.fee_held -= fee
        self._refund_fee(e, b, day)

    def _refund_fee(self, e: Entry, b: Bounty, day: int) -> None:
        if e.fee_held:
            self.ledger.transfer(e.account, e.solver, e.fee_held, "refund", b.ref, day)
            e.fee_held = 0
