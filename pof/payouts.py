"""Releases and their money (specs/release-payouts).

Each release is funded with `release_funding`, which is split by the published shares into:
- the contributors' pool: divided by reward weight among the contributions entering that release's beta build,
  and escrowed (design D10, option A). A slashed contribution's share returns to the pool and rolls over.
- the validators' pool: paid at the release's close to members whose verdicts matched final outcomes.
- the author's escrow: accrues until someone proves control of the upstream project; never paid to a guessed
  address.
- infrastructure: spent on CI and agents; unspent funds roll over.
- insurance: pays covered claims up to a limit per release; it also receives rounding remainders.
- the owner: vests over owner_vesting_months; unvested amounts go to insurance if the owner leaves. Holding it
  gives no vote, no validator weight and no say over payouts.

Parameter changes take effect only from the next release, and the ledger records when they were made.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import BPS, share
from .challenges import Challenge
from .ledger import Ledger
from .lifecycle import Contribution, Lifecycle
from .params import SPLIT_SHARES, Params

DAYS_PER_MONTH = 30


class PayoutError(ValueError):
    """A step the release's state doesn't allow, or an unverified claim; nothing changed."""


class PanelNeeded(PayoutError):
    """The owner proposed a split change that raises a share whose role the owner holds: a validator panel
    without the owner decides (proof-of-fix#10)."""


@dataclass
class Release:
    number: int
    params: Params
    opened_day: int
    split: dict[str, int] = field(default_factory=dict)
    insurance_limit: int = 0
    insurance_paid: int = 0
    shipped: list[int] = field(default_factory=list)
    closed: bool = False

    @property
    def ref(self) -> str:
        return f"release:{self.number}"


class Releases:
    def __init__(self, ledger: Ledger, params: Params, lifecycle: Lifecycle, insurance: str, infrastructure: str,
                 owner: str, upstream_keys: set[str] | None = None, challenges=None) -> None:
        self.ledger, self.lifecycle, self.challenges = ledger, lifecycle, challenges
        self.checking = None  # the checking layer (#43): its re-runs and jury verdicts that held up are work
        self.insurance, self.infrastructure, self.owner = insurance, infrastructure, owner
        self.params = params  # published: applies to the next release opened
        self.treasury = ledger.open("treasury")
        self.contributors_pool = ledger.open("pool")
        self.validators_pool = ledger.open("pool")
        self.author_escrow = ledger.open("author_escrow")
        self.owner_vesting = ledger.open("owner_vesting")
        self.costs = ledger.open("costs")
        self.upstream_keys = set(upstream_keys or ())  # simulated: keys published in the upstream repository
        self.author_key: str | None = None
        self.market = None  # the bounty market, in the market mode (proof-of-fix#15): it prices each contribution
        self._offers: list[tuple[int, int]] = []  # (pool, weight) of the last beta builds, for the stake index (#23)
        self.author_account: str | None = None
        self.owner_active = True
        self._tranches: list[tuple[int, int]] = []  # (amount, day it starts vesting)
        self._owner_withdrawn = 0
        self.releases: list[Release] = []

    # ---------- parameters ----------

    def owner_roles(self) -> set[str]:
        """The split shares whose role the owner holds: the owner share always; validators when the owner has a
        validator stake; contributors when the owner has contributed."""
        roles = {"owner"}
        if self.challenges is not None and self.owner in self.challenges.validators.stake_account:
            roles.add("validators")
        if any(c.contributor == self.owner for c in self.lifecycle.contributions.values()):
            roles.add("contributors")
        return roles

    def publish(self, params: Params, day: int, by: str | None = None, panel_majority: bool | None = None) -> bool:
        """Publish new parameters (validated on construction). They apply from the next release; an open release
        keeps the set it was opened with. Proposed by the owner and raising a share whose role the owner holds:
        a validator panel without the owner must approve (pass its majority). Returns whether it was published."""
        if by is not None and by == self.owner:
            raised = [k for k in self.owner_roles()
                      if params.release_split_bps[k] > self.params.release_split_bps[k]]
            if raised:
                if panel_majority is None:
                    raise PanelNeeded(f"raises {', '.join(sorted(raised))}, a share the owner holds")
                self.ledger.record(day, "params_panel", f"release:{len(self.releases) + 1}",
                                   f"owner's split change raising {', '.join(sorted(raised))}: "
                                   f"{'approved' if panel_majority else 'rejected'} by a panel without the owner")
                if not panel_majority:
                    return False
        self.params = params
        applies_from = len(self.releases) + 1
        self.ledger.record(day, "params", f"release:{applies_from}", f"published on day {day}, applies from release {applies_from}")
        return True

    @property
    def current(self) -> Release | None:
        return self.releases[-1] if self.releases and not self.releases[-1].closed else None

    # ---------- a release ----------

    def open_release(self, day: int) -> Release:
        if self.current is not None:
            raise PayoutError(f"{self.current.ref} is still open")
        if self.releases and self.market is not None and self.market.tokens is not None:
            self.market.tokens.release()  # the period that ends mints its emission (#58)
        r = Release(len(self.releases) + 1, self.params, day)
        p = r.params
        funding = self._funding(r, day)
        if funding:
            self.ledger.issue(self.treasury, funding, "release_funding", r.ref, day)
        targets = {"contributors": self.contributors_pool, "validators": self.validators_pool,
                   "author": self.author_escrow, "infrastructure": self.infrastructure, "insurance": self.insurance,
                   "owner": self.owner_vesting if self.owner_active else self.insurance}
        for name in SPLIT_SHARES:
            amount = share(funding, p.release_split_bps[name])
            r.split[name] = amount
            if amount:
                self.ledger.transfer(self.treasury, targets[name], amount, "payout", r.ref, day)
        remainder = self.ledger.balance(self.treasury)
        if remainder:
            self.ledger.transfer(self.treasury, self.insurance, remainder, "payout", r.ref, day)
            r.split["insurance"] += remainder
        if self.owner_active and r.split["owner"]:
            self._tranches.append((r.split["owner"], day))
        r.insurance_limit = share(self.ledger.balance(self.insurance), p.insurance_limit_bps)
        self.releases.append(r)
        self.lifecycle.release = r.number
        if self.market is not None and p.reward_source == "market":
            self.market.match(day)  # quadratic matching of pledges at each release's opening (#34)
        for c in sorted(self.lifecycle.contributions.values(), key=lambda c: c.id):
            if c.in_clawback and c.settled_day is not None and c.settled_day < day:
                self.lifecycle.pay_instalment(c, day)
        if self.challenges is not None:
            self.challenges.settle_due_reviews(day)
        return r

    def _funding(self, r: Release, day: int) -> int:
        """In the market mode, nothing: bounties pay contributors, and their fee pays the other shares (#15).
        Funding follows use (proof-of-fix#27): when the contributors' pool already holds more than
        pool_buffer_releases of the contributors' share, the whole funding scales down by the surplus over the buffer
        (f = 1 - surplus / share, at least 0), the same for every share; the factor is recorded."""
        p = r.params
        if p.reward_source == "market":
            return 0
        funding = p.release_funding
        full = share(funding, p.release_split_bps["contributors"])
        if not p.pool_buffer_releases or not full:
            return funding
        surplus = self.ledger.balance(self.contributors_pool) - p.pool_buffer_releases * full
        if surplus <= 0:
            return funding
        scaled = max(0, funding - funding * surplus // full)
        self.ledger.record(day, "funding_scaled", r.ref, f"factor_bps={scaled * BPS // funding} surplus={surplus}")
        return scaled

    def ship_beta(self, r: Release, contributions: list[Contribution], day: int) -> dict[int, int]:
        """The release's beta build takes these contributions: the contributors' pool (this release's share plus
        anything rolled over) is divided among them by reward weight and escrowed. Rounding remainders stay in
        the pool. Returns each contribution's reward."""
        self._open(r)
        if r.shipped:
            raise PayoutError(f"{r.ref} already shipped its beta build")
        if r.params.reward_source == "market":
            return self._ship_market(r, contributions, day)
        weights = {c.id: r.params.reward_weight_for(c.changed_lines) for c in contributions}
        if r.params.linear_reward_weight:  # D9: an author's weight per release is capped too, so splitting a change
            by_author: dict[str, int] = {}  # above the cap into parts earns no more than one capped contribution
            for c in contributions:
                by_author[c.contributor] = by_author.get(c.contributor, 0) + weights[c.id]
            cap = r.params.reward_weight_cap_lines
            for c in contributions:
                total = by_author[c.contributor]
                if total > cap:
                    weights[c.id] = max(1, weights[c.id] * cap // total)
        total, pool = sum(weights.values()), self.ledger.balance(self.contributors_pool)
        rewards = {c.id: (pool * weights[c.id] // total if total else 0) for c in contributions}
        cap = r.params.reward_cap_stake_multiple
        if cap:  # proof-of-fix#23: at most cap x the stake; the excess stays in the pool and rolls over
            rewards = {c.id: min(rewards[c.id], cap * c.stake) for c in contributions}
        if total:
            self._index_offer(r, pool, total, day)
        for c in contributions:
            self.lifecycle.enter_beta(c, day, rewards[c.id], self.contributors_pool)
            if self.challenges is not None:
                self.challenges.assign_reviewer(c, day, beacon=f"{r.ref}:{c.id}")
        r.shipped = [c.id for c in contributions] or [0]
        return rewards

    def _ship_market(self, r: Release, contributions: list[Contribution], day: int) -> dict[int, int]:
        """The market mode (#15): each contribution's reward is its winning price, escrowed from its bounty, and the
        market fee on it is paid from the bounty at the same time."""
        if self.market is None:
            raise PayoutError("the market mode needs a market")
        rewards = {}
        for c in contributions:
            price, source = self.market.payment_for(c)
            self.lifecycle.enter_beta(c, day, price, source)
            self.market.merged(c, day)
            self.market.pay_fee(c, day)
            if self.challenges is not None:
                self.challenges.assign_reviewer(c, day, beacon=f"{r.ref}:{c.id}")
            rewards[c.id] = price
        r.shipped = [c.id for c in contributions] or [0]
        return rewards

    def fee_targets(self) -> dict[str, str]:
        """Where each part of the market fee goes (#15): the same accounts as the release split's shares."""
        return {"validators": self.validators_pool, "author": self.author_escrow, "infrastructure": self.infrastructure,
                "insurance": self.insurance, "owner": self.owner_vesting if self.owner_active else self.insurance}

    def owner_tranche(self, amount: int, day: int) -> None:
        """The owner's part of a market fee vests like its release share does."""
        if self.owner_active and amount:
            self._tranches.append((amount, day))

    def _index_offer(self, r: Release, pool: int, weight: int, day: int) -> None:
        """Publish this build's offer (the pool and the weight it was divided by, before any cap) and set the
        lifecycle's stake index: the offered pool per unit of weight over the last stake_index_window builds that
        shipped something (proof-of-fix#23, design D1)."""
        self._offers = (self._offers + [(pool, weight)])[-r.params.stake_index_window:]
        index = sum(p for p, _ in self._offers) // sum(w for _, w in self._offers)
        self.ledger.record(day, "stake_index", r.ref, f"pool={pool} weight={weight} index={index}")
        self.lifecycle.reward_per_weight = index

    def close_release(self, r: Release, challenges: list[Challenge], day: int) -> dict[str, int]:
        """Pay the validators' pool by units of work (proof-of-fix#10): one per counted verdict that matched a final
        outcome in the given (finalized) challenges, one per completed review settled since the last close, and one
        per re-run that matched the quorum and jury verdict that held up (#43). No work: the pool rolls over."""
        self._open(r)
        matched: dict[str, int] = {}
        if self.challenges is not None:
            self.challenges.settle_due_reviews(day)
            for review in self.challenges.take_settled_reviews():
                if review.outcome == "completed":
                    matched[review.reviewer] = matched.get(review.reviewer, 0) + 1
        if self.checking is not None:
            for member, units in self.checking.take_work().items():
                matched[member] = matched.get(member, 0) + units
        for ch in challenges:
            if not ch.applied:
                raise PayoutError(f"{ch.ref} isn't finalized")
            for panel in ch.panels:
                for member, verdict in panel.verdicts.items():
                    if verdict == ch.outcome:
                        matched[member] = matched.get(member, 0) + 1
        pool, total = self.ledger.balance(self.validators_pool), sum(matched.values())
        paid = {}
        for member in sorted(matched):
            amount = pool * matched[member] // total
            if amount:
                self.ledger.transfer(self.validators_pool, member, amount, "payout", r.ref, day)
                paid[member] = amount
        r.closed = True
        return paid

    # ---------- the author ----------

    def claim_author(self, key: str, signed_statement_key: str, upstream_commit_key: str | None, day: int) -> str:
        """A claim to the author's escrow: a statement signed with `key`, and a commit in the upstream repository
        naming the same key. Verified: the escrow becomes withdrawable to an account for that key, and the
        evidence is recorded. Otherwise refused, escrow unchanged."""
        if self.author_key is not None:
            raise PayoutError("the author's escrow is already claimed")
        if signed_statement_key != key or upstream_commit_key != key or key not in self.upstream_keys:
            raise PayoutError("claim not verified: the signed statement and an upstream commit must name the same key")
        self.author_key, self.author_account = key, self.ledger.open("author")
        self.ledger.record(day, "author_claim", "author", f"verified: statement and upstream commit name key {key}")
        return self.author_account

    def withdraw_author(self, day: int) -> int:
        if self.author_account is None:
            raise PayoutError("no verified claim: the author's share stays in escrow")
        amount = self.ledger.balance(self.author_escrow)
        if amount:
            self.ledger.transfer(self.author_escrow, self.author_account, amount, "claim", "author", day)
        return amount

    # ---------- the owner ----------

    def owner_vested(self, day: int) -> int:
        span = self.params.owner_vesting_months * DAYS_PER_MONTH
        return sum(amount * min(max(day - start, 0), span) // span for amount, start in self._tranches)

    def withdraw_owner(self, day: int) -> int:
        amount = self.owner_vested(day) - self._owner_withdrawn
        if amount > 0:
            self.ledger.transfer(self.owner_vesting, self.owner, amount, "payout", "owner", day)
            self._owner_withdrawn += amount
        return max(amount, 0)

    def owner_leaves(self, day: int) -> int:
        """The owner leaves: the vested part is paid, the unvested part goes to insurance, and later releases'
        owner share goes to insurance."""
        self.withdraw_owner(day)
        unvested = self.ledger.balance(self.owner_vesting)
        if unvested:
            self.ledger.transfer(self.owner_vesting, self.insurance, unvested, "slash", "owner", day)
        self.owner_active = False
        self._tranches = []
        return unvested

    # ---------- infrastructure and insurance ----------

    def spend_infrastructure(self, amount: int, day: int, what: str) -> None:
        if amount > self.ledger.balance(self.infrastructure):
            raise PayoutError("not enough infrastructure funds")
        self.ledger.transfer(self.infrastructure, self.costs, amount, "payout", f"infrastructure:{what}", day)

    def pay_insurance(self, r: Release, claimant: str, amount: int, challenge: Challenge, day: int) -> int:
        """A harmed party's covered claim: only after an upheld challenge of severity 'crash' (crash or data loss),
        and up to what's left of the release's insurance limit. Returns what was paid."""
        self._open(r)
        if not (challenge.applied and challenge.outcome and challenge.severity == "crash"):
            raise PayoutError("insurance covers upheld crash or data-loss regressions only")
        paid = min(amount, r.insurance_limit - r.insurance_paid, self.ledger.balance(self.insurance))
        if paid > 0:
            self.ledger.transfer(self.insurance, claimant, paid, "payout", f"insurance:{challenge.ref}", day)
            r.insurance_paid += paid
        return max(paid, 0)

    def _open(self, r: Release) -> None:
        if r.closed or r is not self.current:
            raise PayoutError(f"{r.ref} isn't the open release")
