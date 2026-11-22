"""The market simulation (specs/incentive-simulation "Market scenarios", proof-of-fix#15 design D5-D7, D9).

Issues arrive; users pledge for some, and the AI treasury funds others from its budget; solvers with private costs
bid for the job in sealed rounds; the assigned solver builds and delivers (a no-show never does); the delivered
contribution goes through the same enforcement layer as the legacy world (review duty, hunters, panels, clawback),
which this class inherits unchanged. A solver's cost of development isn't a ledger flow: it's counted as `effort`
when it builds, and returns are reported net of it.

Award modes (proof-of-fix#60): in "race", solvers attempt any open bounty whose price, shared with the published
attempts in progress, beats their cost, and the first submission through the gates wins; the others' effort so far
is wasted. In "claim", the first solver to whom a bounty pays claims it and builds alone. Every fix has a quality the
constitution's gates measure; its draws come from their own stream, so the auction's path doesn't change.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .. import BPS, credits, share
from ..challenges import Proof
from ..checking import constitution_passes
from ..lifecycle import NeedsPanel
from ..market import Bounty, Entry, MarketError, Market, seal
from .actors import SEVERITY_MIX, SOLVER, Actor
from .checks import EVALUATOR_KINDS, RUNNER_KINDS, CheckSim, tally_fixed_odds
from .world import World


DISGUISED = ("crafter", "copy_partner", "planter", "half_fixer", "spam_solver", "split_farmer")  # deliver junk, bid as honest
# solvers to win jobs (#43)
HIDDEN_CATCH_INCOMPLETE_BPS = 6_000  # the hidden tests (other cases of the bug) catch a partial fix (#43 D9)
ESCALATION_RATE = 0.44  # the share of deliveries whose first jury splits, as the market publishes it (#49)
DELIVERY_CATCH_WITH_CHECKS = 0.9  # the share of bad deliveries the checking layer catches, as solvers price it
# (checking v1 measured 0.93; the market publishes its record)
HEAD_START = {"good": 0.3, "defective": 0.7}  # the work left after a public failed attempt, by what it was (#43 D8)


@dataclass
class Issue:
    id: int
    day: int
    value: int  # what a fix is worth to users (micro-credits); a junk issue's is what it claims
    lines: int  # the size of a fix
    junk: bool = False
    route: str = "unfunded"  # pledged | treasury | unfunded
    reporter: Actor | None = None  # who submitted it and staked on it (#34)
    report: object = None  # its IssueStake
    owner: Actor | None = None  # a match farmer's or self-dealer's own issue: it funds it and bids on it
    remaining: float = 1.0  # the share of the work left, once a failed attempt is public (#43)
    estimate: int = 0  # race and claim: the registration check's effort estimate, in lines (#60 D2)
    parts: list = field(default_factory=list)  # a bundle's parts' issue stakes: their reporters share the finder's fee
    bounty: Bounty | None = None  # with the emission on, the 0-coin bounty it opened as (#58 D4)
    bias: float = 1.0  # #58 D3: how its registrant's importance estimates are biased (2 for an inflater)


@dataclass
class Bid:
    actor: Actor
    issue: Issue
    price: int
    salt: str
    deliver_on: int | None = None  # the day it delivers, once assigned (None: never)
    defect: str | None = None  # what its delivery hid
    partial: bool = False
    quality: float = 0.0  # its fix's true quality (#60)
    fix: str = ""  # its fix's fingerprint (#60 D9: a failed fix resubmitted is recognized)


@dataclass
class Attempt:
    """A race attempt in progress (#60 D4): its effort accrues daily until it's submitted, or stopped."""
    actor: Actor
    issue: Issue
    bounty: Bounty
    start: int
    finish: int
    cost: int


class MarketWorld(World):
    def __init__(self, params, seed: int, actors: list[Actor], size_sampler, maintainer: Actor | None = None,
                 hunt_elasticity: float = 0.5, review_detect_bps: int = 6_000, issues_per_week: float = 15.0,
                 value_median: int = credits(100), value_spread: float = 0.8, pledged_share_bps: int = 4_000,
                 cost_per_line: int = credits(1), treasury_detect_bps: int = 8_500, bid_daily_bps: int = 3_000,
                 build_days: tuple[int, int] = (2, 10), single_account: bool = False, record_prior: float = 5.0,
                 checking: bool = True, rho_within: float = 0.5, rho_across: float = 0.2,
                 score_on_agreement: bool = False, evaluator_cost: int = credits(0.3), accuracy_shift: float = 0.0,
                 tee_compromise_bps: int = 50, estimate_error: float = 0.3, duplicate_false_bps: int = 500,
                 token_price: float = 0.0, weight_error: float | None = None, weight_check_catch_bps: int = 9_000):
        super().__init__(params, seed, actors, size_sampler, maintainer=maintainer, hunt_elasticity=hunt_elasticity,
                         review_detect_bps=review_detect_bps)
        self.market = Market(self.ledger, params, self.life, self.releases, self.infra)
        self.owner_rng = random.Random(seed * 15_485_863 + 11)  # its own stream, so a defecting owner's failed
        # attempts don't shift the market's path: the comparison with an honest owner measures the defection (#47)
        self.issues_per_week, self.value_median, self.value_spread = issues_per_week, value_median, value_spread
        self.pledged_share_bps, self.cost_per_line = pledged_share_bps, cost_per_line
        self.treasury_detect_bps, self.bid_daily_bps, self.build_days = treasury_detect_bps, bid_daily_bps, build_days
        self.single_account = single_account  # the match farmer's counterfactual: pledging from one account
        self.record_prior = record_prior  # pseudo-trials of the default assumption in a solver's rates (#40 D3)
        self.issues: list[Issue] = []
        self.issue_of: dict[int, Issue] = {}  # bounty id -> issue
        self.candidates: list[Issue] = []  # unpledged issues the AI treasury may fund
        self.bids: dict[int, Bid] = {}  # entry id -> bid
        self._open: dict[str, set[int]] = {}  # solver account -> its bids that may still be in an open round
        self.pledgers = [a for a in actors if a.kind == "pledger"]
        self.reporters = [a for a in actors if a.kind == "reporter"]
        self.fakes = [a for a in actors if a.kind == "fake"]
        self.solvers = [a for a in actors if a.behaviour.capacity]
        self.treasury_junk = 0  # treasury money spent on junk issues
        self._days = 0
        self.check_stats: dict[str, int] = {}  # deliveries by how they were checked (#43)
        self._seen_published: dict[int, int] = {}  # bounty id -> its published attempts already reused
        self.checks = None  # the checking layer; None: fixed odds, the comparison
        self.mode = params.award_mode  # how jobs are awarded (#60)
        self.mode_rng = random.Random(seed * 2_750_159 + 17)  # fix quality, gates and estimates: their own stream
        self.estimate_error = estimate_error
        self.duplicate_false_bps = duplicate_false_bps  # #64: honest fixes the similarity check flags as a duplicate
        self.fake_attempts: dict[int, list[str]] = {}  # bounty id -> sock accounts attempting it, never submitting
        self.bundle: list[Issue] = []  # race and claim: issues below the size floor, waiting to be bundled
        self.attempts: dict[tuple[int, str], Attempt] = {}  # race: (bounty id, solver) -> its attempt
        self.fix_quality: dict[int, float] = {}  # contribution id -> its true quality
        # #58: tokens. Their price is an assumption (D5, credits per token); the AI's importance estimates (D3) draw
        # from their own stream, so a run with the emission off doesn't change
        self.token_price = token_price
        self.weight_error = estimate_error if weight_error is None else weight_error
        self.weight_check_catch_bps = weight_check_catch_bps
        self.weight_rng = random.Random(seed * 3_141_593 + 29)
        self.tokens_on = self.market.tokens is not None
        if self.tokens_on:
            self.market.weigh_at_merge = self._merge_weight
        if checking:
            self.checks = CheckSim(self, rho_within, rho_across, score_on_agreement=score_on_agreement,
                                   evaluator_cost=evaluator_cost, accuracy_shift=accuracy_shift,
                                   tee_compromise_bps=tee_compromise_bps,
                                   exam_good_bps=9_000 if score_on_agreement else 5_000)
            for a in actors:
                if a.kind in EVALUATOR_KINDS:
                    self.checks.register(a, a.operator, a.family, a.true_family)
                elif a.kind in RUNNER_KINDS and params.ci_mode == "attested":
                    self.checks.register_runner(a)

    def run(self, days: int, drain_days: int = 40) -> "World":
        self._days = days
        if self.checks is not None:
            self.checks.exam()
        super().run(days, drain_days)
        if self.tokens_on:
            self.market.tokens.release()  # the last period's closes, minted as the next release would (#58)
        return self

    def _quiet(self) -> bool:
        return super()._quiet() and not self.attempts and not any(
            b.state in ("won", "assigned") for b in self.market.bounties.values())

    def _submit(self, a: Actor, lines: int, day: int, beh) -> None:
        """No legacy submissions in the market: work enters through bounties."""

    # ---------- a day of the market ----------

    def _act(self, a: Actor, day: int) -> None:
        super()._act(a, day)  # hunters and griefers act on the delivered contributions as before
        if a.kind == "plant_partner":  # challenges its partner's planted bug as soon as it's in beta (#43)
            for c in list(self.in_beta):
                author = self.author.get(c.id)
                if (author is not None and author.kind == "planter" and self.defect.get(c.id)
                        and not any(ch.contribution is c for ch in self.open_challenges)):
                    self._challenge(a, c, Proof("planted regression", c.id), self.defect[c.id], day)
        if a.behaviour.floods:
            self._flood(a, day)
        if a.behaviour.capacity:
            {"auction": self._bid_for_jobs, "race": self._race_for_jobs, "claim": self._claim_jobs}[self.mode](a, day)

    def _settle(self, day: int) -> None:
        super()._settle(day)
        if day < self._days:
            self._arrivals(day)
        self._treasury(day)
        self.market.expire(day)
        for b in sorted(self.market.bounties.values(), key=lambda b: b.id):
            if b.state == "open" and b.round_deadline == day:
                self._reveal(b, day)
                e = self.market.close_round(b, day)
                if e is not None:
                    self._assigned(e, day)
        if self.mode == "race":
            self._attempts(day)
        if self.mode != "auction":
            self._top_ups(day)
            for b in self.market.close_idle(day):
                if b.report:
                    self.market.release_unfunded(self.market.reports[b.report], day)
        self._deliveries(day)
        for e in self.market.expire_deliveries(day):
            self._assigned(e, day)
        for e in self.market.settle(day):
            self._assigned(e, day)
        self._head_starts()
        self._junk_slashed(day)

    def _head_starts(self) -> None:
        """A failed attempt is public: whoever bids next starts from it, so less work is left. Junk delivered to
        fool the checks leaves nothing to reuse (#43 design D8)."""
        for b in self.market.bounties.values():
            for eid in b.published[self._seen_published.get(b.id, 0):]:
                bid = self.bids.get(eid)
                if bid is None or bid.actor.kind in DISGUISED or bid.issue.junk:
                    continue
                cid = next((c for c, x in self.market._entry_of.items() if x.id == eid), None)
                bad = self.defect.get(cid) is not None if cid is not None else bid.defect is not None
                bid.issue.remaining = min(bid.issue.remaining, HEAD_START["defective" if bad else "good"])
            self._seen_published[b.id] = len(b.published)

    def _junk_slashed(self, day: int) -> None:
        """A junk issue whose delivered fix was slashed goes to a validator panel, which can forfeit its stake."""
        for cid, b in self.market._by_contribution.items():
            issue = self.issue_of.get(b.id)
            if (issue is not None and issue.junk and issue.report is not None and issue.report.state == "posted"
                    and self.life.contributions[cid].state == "slashed"):
                self.market.flag_junk(issue.report, day, self._panel(True, set()))

    # ---------- issues, pledges and the treasury ----------

    def _poisson(self, mean: float) -> int:
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= self.rng.random()
            if p <= limit:
                return k
            k += 1

    def _value(self) -> int:
        return max(credits(1), int(self.value_median * math.exp(self.rng.gauss(0, self.value_spread))))

    def _report(self, issue: Issue, reporter: Actor, day: int) -> bool:
        """The reporter stakes on its issue (#34); an issue whose reporter can't stake isn't submitted. In race and
        claim it also pays the registration check, which estimates the issue's effort (#60 D2)."""
        try:
            if self.mode != "auction":
                if self.ledger.balance(reporter.account) < self.params.registration_fee + self.params.issue_stake:
                    raise MarketError("can't pay the check and the stake")
                fee = self.market.register(reporter.account, day)
                bias = 2.0 if reporter.behaviour.inflates else 1.0
                issue.estimate = max(1, int(issue.lines * bias * math.exp(self.mode_rng.gauss(0, self.estimate_error))))
                issue.report = self.market.report_issue(reporter.account, day, registration=fee)
            else:
                issue.report = self.market.report_issue(reporter.account, day)
        except MarketError:
            reporter.bump("unaffordable_reports")
            return False
        issue.reporter = reporter
        reporter.bump("reported")
        return True

    def _arrivals(self, day: int) -> None:
        for _ in range(self._poisson(self.issues_per_week / 7)):
            issue = Issue(len(self.issues) + 1, day, self._value(), self.sample_size(self.rng))
            if self.reporters and not self._report(issue, self.rng.choice(self.reporters), day):
                continue
            self.issues.append(issue)
            if self._below_floor(issue, day):
                continue
            if self.pledgers and self.rng.randrange(BPS) < self.pledged_share_bps:
                self._pledge(issue, day)
            else:
                self._unpledged(issue, day)
        for a in self.actors:  # match farmers and self-dealers submit, fund and bid on their own issues
            own = a.kind in ("match_farmer", "self_dealer", "inflater") or a.behaviour.codes_own
            if own and self.rng.random() < 1 / 7:
                self._own_issue(a, day)

    def _unpledged(self, issue: Issue, day: int) -> None:
        """An issue nobody pledges for waits for the treasury. With the emission on (#58 D4), it opens at once as a
        bounty of 0 coin, which anyone can solve for its tokens and the treasury may top up. With no treasury (the
        contract's shape, owner 2026-10-29), it opens at once as the registration check opens it on-chain, and sunsets
        if nobody funds or attempts it; a bundle, which the contract doesn't have, still waits, with the emission on too
        (task 3.4: the token's replay)."""
        no_treasury = not self.params.treasury_budget
        opens = (self.tokens_on or no_treasury) and not (no_treasury and issue.parts)
        if opens and not self._too_small(issue, day):
            issue.bounty = self._open_bounty(issue, day)
            issue.route = "zero_coin" if self.tokens_on else "unpledged"
            self.issue_of[issue.bounty.id] = issue
        self.candidates.append(issue)

    def _below_floor(self, issue: Issue, day: int) -> bool:
        """Race and claim: an issue estimated below the size floor doesn't open alone; it waits in the bundle pool,
        its reporter's stake back. Once the pool's estimates reach the floor, they open as one bounty for the
        treasury (#60 D2)."""
        if self.mode == "auction" or issue.estimate >= self.params.size_floor_lines:
            return False
        issue.route = "bundled"
        if issue.report is not None:
            self.market.release_unfunded(issue.report, day)
        self.bundle.append(issue)
        if sum(i.estimate for i in self.bundle) >= self.params.size_floor_lines:
            parts, self.bundle = self.bundle, []
            merged = Issue(len(self.issues) + 1, day, sum(i.value for i in parts), sum(i.lines for i in parts),
                           estimate=sum(i.estimate for i in parts), parts=[i.report for i in parts if i.report])
            self.issues.append(merged)
            self._unpledged(merged, day)
            self.check_stats["bundles"] = self.check_stats.get("bundles", 0) + 1
        return True

    def _own_issue(self, a: Actor, day: int) -> None:
        small = a.kind == "match_farmer"
        value = self._value()
        if a.kind == "inflater":  # small issues of its own, which an honest estimate would bundle (#60)
            lines = self.mode_rng.randint(8, 14)
        else:
            lines = self.rng.randint(10, 40) if small else self.sample_size(self.rng)
        issue = Issue(len(self.issues) + 1, day, value, lines, owner=a)
        if not self._report(issue, a, day):
            return
        self.issues.append(issue)
        if self._too_small(issue, day) or self._below_floor(issue, day):
            return
        if a.behaviour.codes_own:  # #58: it doesn't fund its issue; it's open to anyone, like any unpledged issue
            self._unpledged(issue, day)
            return
        b = self._open_bounty(issue, day)
        issue.route, self.issue_of[b.id] = "pledged", issue
        if small and not self.single_account:  # 60 % of the value, split across its fake accounts: the match does the rest
            part = share(issue.value, 6_000) // max(1, len(self.fakes))
            backers = [(f, part) for f in self.fakes]
        elif small:  # the counterfactual, without a match: in the auction, what it needs from one account to reach
            # the target; with no target (#56 D12), the same 60 % from one account, so only the match differs
            whole = issue.value if self.mode == "auction" else share(issue.value, 6_000) // max(1, len(self.fakes)) * max(
                1, len(self.fakes))
            backers = [(a, whole)]
        else:
            backers = [(a, issue.value)]  # the self-dealer funds its own issue in full
        for who, amount in backers:
            amount = min(amount, self.ledger.balance(who.account))
            if amount > 0 and self._funding(b):
                self.market.pledge(b, who.account, amount, day)
                who.bump("pledged", amount)

    def _too_small(self, issue: Issue, day: int) -> bool:
        """An issue worth no more than one attempt's oracle fees isn't worth a bounty (#43): it stays unfunded, and
        its reporter's stake comes back."""
        if self.checks is None or self.params.checks_paid_by != "bounty" or issue.value > self.params.oracle_reserve:
            return False  # #49: when the solver pays its checks, small bounties are the solvers' call
        issue.route = "too_small"
        if issue.report is not None:
            self.market.release_unfunded(issue.report, day)
        self.check_stats["too_small"] = self.check_stats.get("too_small", 0) + 1
        return True

    def _pledge(self, issue: Issue, day: int) -> None:
        """1-6 backers pledge 50-110 % of the issue's value between them (#34 design D6): some bounties reach their
        target at once, others wait for more pledges or a match."""
        if self._too_small(issue, day):
            return
        b = self._open_bounty(issue, day)
        issue.route, self.issue_of[b.id] = "pledged", issue
        backers = self.rng.sample(self.pledgers, min(len(self.pledgers), self.rng.randint(1, 6)))
        total = int(issue.value * self.rng.uniform(0.5, 1.1))
        for p in backers:
            amount = min(total // len(backers), self.ledger.balance(p.account))
            if amount > 0 and self._funding(b):
                self.market.pledge(b, p.account, amount, day)
                p.bump("pledged", amount)

    def _open_bounty(self, issue: Issue, day: int) -> Bounty:
        """In the auction, a bounty with the issue's value as its target; in race and claim, none: its funders set
        its value (#56 D12)."""
        target = issue.value if self.mode == "auction" else 0
        if issue.reporter is not None and issue.reporter.behaviour.inflates_importance:
            issue.bias = 2.0
        return self.market.open_bounty(target, day, report=issue.report, parts=issue.parts, key=f"issue:{issue.id}",
                                       weight=self._importance(issue, issue.bias) if self.tokens_on else 0)

    def _importance(self, issue: Issue, bias: float) -> int:
        """The AI's estimate of an issue's importance: its true value, biased, with a lognormal error (#58 D3)."""
        return max(1, int(issue.value * bias * math.exp(self.weight_rng.gauss(0, self.weight_error))))

    def _merge_weight(self, b: Bounty) -> int:
        """The second estimate, when the fix is merged: independent and unbiased with weight_check_catch_bps, otherwise
        it repeats the registration's bias (#58 D3)."""
        issue = self.issue_of.get(b.id)
        if issue is None:
            return b.weight
        caught = self.weight_rng.randrange(BPS) < self.weight_check_catch_bps
        return self._importance(issue, 1.0 if caught else issue.bias)

    def _funding(self, b: Bounty) -> bool:
        """Whether a pledge can still go in: before the target in the auction, while it's open otherwise."""
        return b.state == ("pledging" if self.mode == "auction" else "open")

    def _flood(self, a: Actor, day: int) -> None:
        """Junk issues pushed at the AI treasury, each claiming a value just under the panel threshold."""
        n = int(a.behaviour.floods) + (1 if self.rng.random() < a.behaviour.floods % 1 else 0)
        for _ in range(n):
            claim = self.params.treasury_approval_above - credits(1)
            issue = Issue(len(self.issues) + 1, day, claim, 10, junk=True)
            if not self._report(issue, a, day):  # it stakes on every junk issue (#34)
                return
            self.issues.append(issue)
            self._unpledged(issue, day)

    def _treasury(self, day: int) -> None:
        """The AI treasury funds the most valuable unpledged issues it believes real, within its budget; a larger
        bounty goes to a validator panel. It spots junk with treasury_detect_bps."""
        keep = []
        def rank(i: Issue):  # value times the reporter's trust (#37)
            return -self.market.priority(i.value, i.reporter.account if i.reporter else None), i.id

        for issue in sorted(self.candidates, key=rank):
            if day - issue.day > self.params.bounty_deadline_days:
                if issue.report is not None:
                    self.market.release_unfunded(issue.report, day)  # stale: never funded, its stake back
                continue
            if issue.junk and self.rng.randrange(BPS) < self.treasury_detect_bps:
                # flagged as junk: a validator panel decides, and a confirmed flag forfeits the stake (#34)
                if issue.report is None or self.market.flag_junk(issue.report, day, self._panel(True, set())):
                    continue
            if self._too_small(issue, day):
                continue
            target = min(issue.value, self.params.treasury_bounty_cap)
            if issue.bounty is not None and not self.tokens_on:  # open already, with no treasury to fund it
                keep.append(issue)
                continue
            if self.tokens_on:  # #58 D4: it tops up the issue's open bounty instead of opening its own
                if issue.bounty is None or issue.bounty.state != "open":
                    continue
                try:
                    self._top_up(issue.bounty, target, day, issue.junk)
                except MarketError:
                    keep.append(issue)
                    continue
                if issue.junk:
                    self.treasury_junk += target
                continue
            try:
                b = self.market.fund_treasury(target, day, report=issue.report, parts=issue.parts)
            except NeedsPanel:
                try:
                    b = self.market.fund_treasury(target, day, panel_majority=self._panel(not issue.junk, set()),
                                                  report=issue.report, parts=issue.parts)
                except MarketError:
                    continue
            except MarketError:
                keep.append(issue)  # over this release's budget: try again later
                continue
            issue.route, self.issue_of[b.id] = "treasury", issue
            if issue.junk:
                self.treasury_junk += target
        self.candidates = keep

    def _top_up(self, b: Bounty, amount: int, day: int, junk: bool) -> None:
        try:
            self.market.top_up_treasury(b, amount, day)
        except NeedsPanel:
            self.market.top_up_treasury(b, amount, day, panel_majority=self._panel(not junk, set()))

    # ---------- solvers ----------

    def cost(self, a: Actor, issue: Issue) -> int:
        """A solver's private cost of development for an issue (design D5)."""
        return int(issue.lines * self.cost_per_line * a.behaviour.skill * issue.remaining)

    def rates(self, a: Actor) -> tuple[float, float]:
        """A solver's chance that a delivery fails, and that a delivered fix is slashed or clawed back later:
        its recorded outcomes, with the default assumption counted as record_prior trials (#40 design D3). An attacker
        delivering junk prices like an honest solver, to win jobs (#43 design D6)."""
        beh = SOLVER if a.kind in DISGUISED else a.behaviour
        d, catch, flaky = beh.defect_bps / BPS, beh.checks_catch_bps / BPS, beh.false_check_failure_bps / BPS
        q, catch_q = beh.incomplete_bps / BPS, 0.0  # its partial fixes (#43): the old gate never caught them
        if self.checks is not None:  # the checking layer's published detection rate (#43 design D9)
            catch = catch_q = DELIVERY_CATCH_WITH_CHECKS
        later_q = q * (1 - catch_q) if self.params.not_solved_challenges else 0.0
        k = self.record_prior
        seen = self.market.reputation.outcomes.get((a.account, "solver"), {})
        failed, delivered = seen.get("delivery failed", 0), a.stats.get("delivered", 0)
        caught = seen.get("slashed", 0) + seen.get("clawed back", 0)
        judged = seen.get("accepted", 0) + seen.get("slashed", 0)  # a clawback follows an acceptance
        fail_delivery = (failed + k * (d * catch + q * catch_q + (1 - d - q) * flaky)) / (failed + delivered + k)
        caught_later = (caught + k * (d * (1 - catch) + later_q) * self.review_detect_bps / BPS) / (judged + k)
        return fail_delivery, min(caught_later, 1.0)

    def break_even(self, a: Actor, b: Bounty, issue: Issue) -> int:
        """The price at which the job pays nothing over its full expected cost: the build cost plus the expected
        penalties (a failed delivery forfeits the bond; a defect caught later slashes the stake and pays nothing),
        over the chance of being paid, at the solver's own rates. An honest solver bids this, its true cost
        (design D5, D10; #40 D3)."""
        p = self.params
        stake = self.market.stake_for(b, solver=a.account)  # its own bond, discounted by its trust (#37)
        fail_delivery, caught_later = self.rates(a)
        avg_slash = sum(share_bps / BPS * p.severity_slash_bps[sev] / BPS for sev, share_bps in SEVERITY_MIX)
        penalty = fail_delivery * stake + caught_later * avg_slash * stake + share(stake, p.check_fee_bps)
        paid = (1 - fail_delivery) * (1 - caught_later)
        return int((self.cost(a, issue) + penalty + self.expected_checks()) / max(paid, 1e-6))

    def expected_checks(self) -> int:
        """What one attempt's checks cost the solver when it pays them (#49): the runs, the first jury, and the
        second on a split at the published escalation rate. Paid on every attempt, so priced like its other costs."""
        p = self.params
        if self.checks is None or p.checks_paid_by != "solver":
            return 0
        runs = p.ci_runners if p.ci_mode == "attested" else p.rerun_validators
        table = getattr(self.market, "check_gas", None)
        if table is not None:  # #85 S15: a medium fix's usage at the table, one judge per family on average
            from .. import checkgas as G
            verdict = sum(G.sim_verdict(table, f, 200) for f in G.SIM_FAMILIES) / len(G.SIM_FAMILIES)
            return credits(runs * G.sim_run(table, 200) + verdict * (p.jury_size + ESCALATION_RATE * p.second_jury_size))
        return int(runs * p.run_fee + p.verdict_fee * (p.jury_size + ESCALATION_RATE * p.second_jury_size))

    def _active(self, a: Actor) -> int:
        """Bids still in open rounds, jobs assigned to it, and its contributions waiting for or in a beta build."""
        open_ = self._open.get(a.account, set())
        open_ -= {eid for eid in open_ if self.market.entries[eid].state != "committed"}
        assigned = sum(1 for b in self.market.bounties.values()
                       if b.state == "assigned" and b.assigned is not None and b.assigned.solver == a.account)
        working = sum(1 for c in self.pending + self.in_beta if c.contributor == a.account)
        racing = sum(1 for _, who in self.attempts if who == a.account)
        return len(open_) + assigned + working + racing

    def _bid_for_jobs(self, a: Actor, day: int) -> None:
        active = self._active(a)
        for b in sorted(self.market.bounties.values(), key=lambda b: b.id):
            if active >= self._behaviour(a, day).capacity:
                return
            if b.state != "open" or b.round_deadline is None or day >= b.round_deadline:
                continue
            if any(e.solver == a.account for e in b.entries if e.round == b.rounds):
                continue  # already bid in this round
            issue = self.issue_of.get(b.id)
            if issue is None or self.rng.randrange(BPS) >= self.bid_daily_bps:
                continue
            price = self._price(a, b, issue, day)
            if price is None:
                continue
            salt = f"{a.name}:{b.id}:{b.rounds}"
            try:
                e = self.market.commit(b, a.account, seal(price, salt), day)
            except MarketError:
                a.bump("unaffordable")
                continue
            self.bids[e.id] = Bid(a, issue, price, salt)
            self._open.setdefault(a.account, set()).add(e.id)
            a.actions += 1
            a.staked += e.stake
            a.bump("bids")
            active += 1

    def _price(self, a: Actor, b: Bounty, issue: Issue, day: int = 0) -> int | None:
        """What this solver bids for the job, or None if it stays out. No bid is above the reserve (#40)."""
        beh, cap = self._behaviour(a, day), self.market.reserve(b)
        if beh.max_lines and issue.lines > beh.max_lines:
            return None  # a reputation farmer builds trust on small jobs only
        if beh.floods:  # the flood bids only on junk bounties, at the reserve: there's nothing to build or catch
            return cap if issue.junk else None
        if issue.junk:
            return None  # a real solver can't fix a junk issue
        if a.kind == "match_farmer":  # it bids only on its own issues, at the reserve
            return cap if issue.owner is a and self.cost(a, issue) < cap else None
        if not beh.delivers:  # a no-show bids low to win, with no intention of building
            return max(1, min(cap, int(self.cost(a, issue) * beh.bid_factor)))
        true_cost = self.break_even(a, b, issue)
        if true_cost >= cap:
            return None  # not worth it
        if a.group is not None:  # a ring: only its cheapest member with room bids, once per round; the rest stay out
            members = {m.account for m in self.solvers if m.group == a.group}
            if any(e.solver in members for e in b.entries if e.round == b.rounds):
                return None
            ring = [m for m in self.solvers if m.group == a.group and self._active(m) < m.behaviour.capacity]
            if min(ring, key=lambda m: (self.break_even(m, b, issue), m.name)) is not a:
                return None
        return max(1, min(cap, int(true_cost * beh.bid_factor)))

    # ---------- the race and the claim (#60) ----------

    def _min_price(self, a: Actor, b: Bounty, issue: Issue, bond: bool) -> int:
        """The price at which a job pays nothing over its expected cost, as `break_even`, with no bond to forfeit in
        the race (its stake only backs the accepted contribution)."""
        if bond:
            return self.break_even(a, b, issue)
        p = self.params
        stake = self.market.stake_for(b, solver=a.account)
        fail_delivery, caught_later = self.rates(a)
        avg_slash = sum(share_bps / BPS * p.severity_slash_bps[sev] / BPS for sev, share_bps in SEVERITY_MIX)
        paid = (1 - fail_delivery) * (1 - caught_later)
        return int((self.cost(a, issue) + caught_later * avg_slash * stake + self.expected_checks()) / max(paid, 1e-6))

    def _eligible(self, a: Actor, b: Bounty, issue: Issue | None, day: int) -> bool:
        """Whether this solver would work on this bounty at all, as in the auction's `_price`."""
        beh = self._behaviour(a, day)
        if issue is None or not beh.delivers or (beh.max_lines and issue.lines > beh.max_lines):
            return False
        if beh.floods:
            return issue.junk  # the flood goes for its own junk issues only
        if issue.junk:
            return False
        if a.kind == "match_farmer" or beh.codes_own:
            return issue.owner is a
        return True

    def _race_for_jobs(self, a: Actor, day: int) -> None:
        """Attempt open bounties whose price, shared with the attempts in progress, beats this solver's cost
        (#60 D4). A ring's members don't race each other."""
        active = self._active(a)
        for b in sorted(self.market.bounties.values(), key=lambda b: b.id):
            if active >= self._behaviour(a, day).capacity:
                return
            issue = self.issue_of.get(b.id)
            if b.state != "open" or (b.id, a.account) in self.attempts or not self._eligible(a, b, issue, day):
                continue
            if self.rng.randrange(BPS) >= self.bid_daily_bps:
                continue
            if a.group is not None and any(m.account in b.attempting for m in self.solvers if m.group == a.group):
                continue
            price = self.market.offer(b, day) + self.token_value(b, day)  # coin, and tokens at their price (#58 D5)
            share_of_price = price // (self.market.published_attempts(b) + 1)  # naive odds
            if not a.behaviour.floods and share_of_price <= self._min_price(a, b, issue, False):
                continue
            try:
                self.market.race_start(b, a.account, day)  # pays the attempt fee (#64)
            except MarketError:
                a.bump("unaffordable")
                continue
            self._fake_attempts(a, b, day)
            start = day
            self.attempts[(b.id, a.account)] = Attempt(a, issue, b, start, start + self.rng.randint(*self.build_days),
                                                       0 if a.behaviour.floods else self.cost(a, issue))
            a.bump("attempts")
            active += 1

    def token_value(self, b: Bounty, day: int) -> int:
        """What a solver expects the bounty's tokens to be worth, at the run's token price (#58 D5): 0 with the emission
        off or a price of 0."""
        if not self.tokens_on or not self.token_price:
            return 0
        return int(self.market.expected_tokens(b, day) * self.token_price)

    def _fake_attempts(self, a: Actor, b: Bounty, day: int) -> None:
        """#64: a fake attempter's socks start paid attempts on the same bounty and never submit, so the published
        count looks crowded. They stop when the bounty closes."""
        if not a.behaviour.fake_attempts:
            return
        socks = [m for m in self.actors if m.cohort == a.cohort and m is not a and a.cohort][:a.behaviour.fake_attempts]
        for sock in socks:
            try:
                self.market.race_start(b, sock.account, day)
            except MarketError:
                continue
            sock.bump("fake_attempts")
            self.fake_attempts.setdefault(b.id, []).append(sock.account)

    def _attempts(self, day: int) -> None:
        """Attempts due today are submitted and checked in arrival order; an attempt on a bounty that was won
        stops, its effort so far wasted, unless it finished today: then it's submitted late, and pays for that (#64)."""
        for bid_, socks in list(self.fake_attempts.items()):
            b = self.market.bounties[bid_]
            if b.state not in ("open", "assigned"):
                for sock in socks:
                    self.market.race_stop(b, sock, day)
                del self.fake_attempts[bid_]
        for key in sorted(self.attempts, key=lambda k: (self.attempts[k].finish, k)):
            t = self.attempts[key]
            b, a = t.bounty, t.actor
            if b.state not in ("open", "assigned") and t.finish != day:
                spent = t.cost * (day - t.start) // max(1, t.finish - t.start)
                a.bump("effort", spent)
                a.bump("wasted", spent)
                a.bump("stopped")
                self.market.race_stop(b, a.account, day)
                del self.attempts[key]
                continue
            if t.finish != day:
                continue
            del self.attempts[key]
            a.bump("effort", t.cost)
            fix = f"{a.name}:{b.id}:{t.start}"
            late = b.state not in ("open", "assigned")
            flagged = (not late and b.failed_fixes and not a.behaviour.floods
                       and self.mode_rng.randrange(BPS) < self.duplicate_false_bps)
            seen = sorted(b.failed_fixes)[0] if flagged else fix  # #64: an honest fix flagged as a failed one's
            refused = False
            try:
                e = self.market.race_submit(b, a.account, day, fix=seen)
            except MarketError:  # can't cover it: nothing was submitted, so there's no rejection to appeal
                e, refused = None, True
            if e is None and flagged and not refused:
                a.bump("false_duplicates")
                e = self._appeal_duplicate(a, b, seen, day)
            if e is None:
                a.bump("late" if late else "wasted_submissions")
                a.bump("wasted", t.cost)
                continue
            bid = self.bids[e.id] = Bid(a, t.issue, b.price, "", fix=seen)
            if self._deliver_one(b, e, day, built=True):
                continue
            if self._appeal(a, b, e, bid, day) or not a.behaviour.variants:
                continue
            self._variant(a, b, bid, day)

    def _appeal_duplicate(self, a: Actor, b: Bounty, fix: str, day: int) -> Entry | None:
        """#64: an honest solver whose own fix was flagged as someone's failed one appeals to a jury of
        duplicate_appeal_jury evaluators, one per provider first; each is right with its model's accuracy. Cleared,
        its fix is submitted again and checked like any. Returns the new submission, or None."""
        if not a.behaviour.appeals_wrong_decisions or self.checks is None:
            return None
        votes = self._appeal_votes(b, independent=True)
        if votes is None:
            return None
        try:
            cleared = self.market.appeal_duplicate(b, a.account, fix, day, votes)
        except MarketError:
            return None
        a.bump("duplicate_appeals")
        if not cleared:
            return None
        a.bump("duplicate_appeals_won")
        try:
            return self.market.race_submit(b, a.account, day, fix=fix)
        except MarketError:
            return None

    def _appeal_votes(self, b: Bounty, independent: bool) -> list[tuple[str, int, bool]] | None:
        """The duplicate appeal's jury: the best evaluator of each provider by model accuracy, then the next best,
        none of them racing for the bounty; each votes the truth with its model's accuracy."""
        ch, n = self.checks.checking, self.params.duplicate_appeal_jury
        parties = self.market.parties(b)
        pool = sorted((x for x in ch.evaluators if ch.qualified(x) and x not in parties),
                      key=lambda x: (-self.checks.model_acc[self.checks.running[x]], x))
        picked, families = [], {}
        for rank in range(n):
            for x in pool:
                fam = ch.evaluators[x].family
                if len(picked) < n and x not in picked and families.get(fam, 0) == rank:
                    picked.append(x)
                    families[fam] = rank + 1
        if len(picked) < n:
            return None
        return [(x, ch.verdict_fee(x), independent if self.mode_rng.random() < self.checks.model_acc[self.checks.running[x]]
                 else not independent) for x in picked]

    def _appeal(self, a: Actor, b: Bounty, failed: Entry, bid: Bid, day: int) -> bool:
        """An honest solver whose fix it knows is good appeals its failed submission once, at its own cost, to the
        second jury (#60 D9). The same fix: only the checks run again. Returns whether it won."""
        good = bid.defect is None and bid.quality >= b.gate_bar_bps / BPS
        if not (a.behaviour.appeals_wrong_decisions and good and b.state == "open"):
            return False
        try:
            e = self.market.race_appeal(failed, day)
        except MarketError:
            return False
        a.bump("appeals")
        self.bids[e.id] = Bid(a, bid.issue, b.price, "", fix=bid.fix)
        return self._deliver_one(b, e, day, built=True, same=bid)

    def _variant(self, a: Actor, b: Bounty, bid: Bid, day: int) -> None:
        """The same failed fix resubmitted from the solver's second account: no new build, new checks. The AI
        similarity check recognizes it with duplicate_catch_bps (#60 D9)."""
        partner = next((m for m in self.actors if m.cohort == a.cohort and m is not a and a.cohort), None)
        if partner is None or b.state != "open":
            return
        recognized = self.mode_rng.randrange(BPS) < self.params.duplicate_catch_bps
        fix = bid.fix if recognized else f"{bid.fix}:variant"
        partner.bump("variants")
        try:
            e = self.market.race_submit(b, partner.account, day, fix=fix)
        except MarketError:
            return
        if e is not None:
            self.bids[e.id] = Bid(partner, bid.issue, b.price, "", fix=fix)
            self._deliver_one(b, e, day, built=True, same=bid)

    def _claim_jobs(self, a: Actor, day: int) -> None:
        """Claim an open bounty that pays this solver's cost, bond risk included (#60 D5)."""
        active = self._active(a)
        for b in sorted(self.market.bounties.values(), key=lambda b: b.id):
            if active >= self._behaviour(a, day).capacity:
                return
            issue = self.issue_of.get(b.id)
            beh = self._behaviour(a, day)
            if b.state != "open" or self.rng.randrange(BPS) >= self.bid_daily_bps:
                continue
            no_show = not beh.delivers and issue is not None and not issue.junk
            if not no_show and not self._eligible(a, b, issue, day):
                continue
            if not beh.floods and not no_show and self.market.offer(b, day) + self.token_value(b, day) <= self._min_price(
                    a, b, issue, True):
                continue
            mid = sum(self.build_days) / 2
            days = max(self.params.claim_min_days,
                       math.ceil(mid * issue.estimate / max(1, issue.lines) * self.params.claim_days_percent / 100))
            try:
                e = self.market.claim(b, a.account, day, days)
            except MarketError:
                a.bump("unaffordable")
                continue
            self.bids[e.id] = Bid(a, issue, b.price, "")
            a.staked += e.stake
            a.bump("claims")
            self._assigned(e, day)
            active += 1

    def _top_ups(self, day: int) -> None:
        """Each week, an open bounty nobody has attempted or claimed for a week gets top_up_bps_per_week of its
        issue's value from its pledgers, up to that value (#60 D3)."""
        bps = self.params.top_up_bps_per_week
        if not bps or day % 7:
            return
        for b in self.market.bounties.values():
            issue = self.issue_of.get(b.id)
            quiet = day - max(b.idle_since, b.stopped_on)
            if b.state != "open" or b.attempting or quiet < 7 or issue is None or not b.pledges:
                continue
            room = issue.value - self.ledger.balance(b.account)
            for pledger in sorted(b.pledges):
                amount = min(share(issue.value, bps) // len(b.pledges), room, self.ledger.balance(pledger))
                if amount > 0:
                    self.market.top_up(b, pledger, amount, day)
                    room -= amount

    def _reveal(self, b: Bounty, day: int) -> None:
        for e in b.entries:
            if e.round != b.rounds or e.state != "committed":
                continue
            bid = self.bids[e.id]
            if self.rng.randrange(BPS) < bid.actor.behaviour.no_reveal_bps:
                continue  # forgot to reveal: the fee is lost
            self.market.reveal(e, bid.price, bid.salt, day)

    def _assigned(self, e: Entry, day: int) -> None:
        """An assigned solver schedules its delivery (a no-show never delivers)."""
        bid = self.bids[e.id]
        a = bid.actor
        a.bump("assigned")
        a.bump("bond_total", e.stake)
        if self._behaviour(a, day).delivers:
            bid.deliver_on = min(e.deliver_by, day + self.rng.randint(*self.build_days))

    def _deliveries(self, day: int) -> None:
        for b in sorted(self.market.bounties.values(), key=lambda b: b.id):
            e = b.assigned
            if b.state != "assigned" or e is None or self.bids[e.id].deliver_on != day:
                continue
            self._deliver_one(b, e, day)

    def _gates(self, a: Actor, b: Bounty, quality: float | None = None) -> tuple[float, bool]:
        """A fix's true quality (drawn, unless it's a fix already delivered), and whether it passes the
        constitution's gates (race and claim only; the auction has none, #60 D6). Drawn from the mode's own stream in
        every mode, so the auction's path doesn't change."""
        p, beh = self.params, a.behaviour
        if quality is None:
            quality = beh.quality_bps / BPS + self.mode_rng.gauss(0, 0.08)
        measured = (0.9 if beh.pads_tests else quality) + self.mode_rng.gauss(0, p.gate_accuracy_bps / BPS)
        padding = beh.pads_tests and self.mode_rng.randrange(BPS) < p.mutation_catch_bps
        if self.mode == "auction":
            return quality, True
        return quality, constitution_passes(b.gate_bar_bps, int(measured * BPS), padding)

    def _deliver_one(self, b: Bounty, e: Entry, day: int, built: bool = False, same: Bid | None = None) -> bool:
        """The assigned (or submitted) bid delivers. `same`: a fix already delivered once (an appeal or a variant),
        whose defect and quality don't change; only its checks run again (#60 D9). Returns whether it won."""
        bid = self.bids[e.id]
        a, issue = bid.actor, bid.issue
        if not a.behaviour.floods and not built:
            a.bump("effort", self.cost(a, issue))  # it builds: the only effort spent on this job
        defect = "wrong_result" if issue.junk else None  # a fix for an issue that isn't real: review can see it
        if same is None and not issue.junk and self.rng.randrange(BPS) < a.behaviour.defect_bps:
            pick = self.rng.randrange(BPS)
            for severity, share_bps in SEVERITY_MIX:
                if pick < share_bps:
                    defect = severity
                    break
                pick -= share_bps
        partial = (same is None and self.rng.randrange(BPS) < a.behaviour.incomplete_bps and defect is None
                   and not issue.junk)
        if same is not None:
            defect, partial = same.defect, same.partial
        elif partial:  # solves the reported case, not the whole issue: a wrong result elsewhere, nothing broken
            defect = "wrong_result"
        bid.defect, bid.partial = defect, partial
        caught = defect is not None and not issue.junk and self.rng.randrange(BPS) < a.behaviour.checks_catch_bps
        hidden_draw = self.rng.randrange(BPS)
        if partial:  # the public checks pass it; only the hidden tests can catch it
            caught = self.checks is not None and hidden_draw < HIDDEN_CATCH_INCOMPLETE_BPS
        flaky = defect is None and self.rng.randrange(BPS) < a.behaviour.false_check_failure_bps
        quality, gates = self._gates(a, b, None if same is None else same.quality)
        bid.quality = quality
        if self.checks is not None:  # re-runs and the jury (#43)
            c = self.checks.deliver(e, a, issue, defect, caught, day, partial=partial, gates=gates)
        else:
            tally_fixed_odds(self.check_stats, defect is None and not issue.junk,
                             defect is not None and not issue.junk, not (caught or flaky))
            c = self.market.deliver(e, issue.lines, day, passes=not (caught or flaky) and gates)
        if not gates:
            self.check_stats["gates_failed"] = self.check_stats.get("gates_failed", 0) + 1
        if c is None:
            a.bump("delivery_failed")
            if not a.behaviour.floods:
                a.bump("wasted", self.cost(a, issue))  # its effort on this job wasn't paid
            nxt = b.assigned if b.state == "assigned" else None
            if nxt is not None and nxt is not e:
                self._assigned(nxt, day)
            return False
        if partial:
            self.incomplete.add(c.id)
        self.fix_quality[c.id] = quality
        self._won(b, c, a, defect, day)
        return True

    def _won(self, b: Bounty, c, a: Actor, defect: str | None, day: int) -> None:
        """A delivered contribution joins the enforcement layer: authored, with its hidden defect, checked by the
        maintainer like any contribution, then queued for the next beta build."""
        self.author[c.id], self.defect[c.id] = a, defect
        a.bump("delivered")
        m = self.maintainer
        if m is not None and m is not a and self.rng.randrange(BPS) < m.behaviour.decline_others_bps:
            self._decline(m, a, c, day, justified=defect is not None)
        if c.state == "checked":
            self.pending.append(c)

    # ---------- results ----------

    def wealth(self, a: Actor) -> int:
        """As in the legacy world, plus its issue stakes still posted: its money, held (#34 design D6)."""
        held = sum(self.ledger.balance(r.account) for r in self.market.reports.values()
                   if r.reporter == a.account and r.state == "posted")
        if self.checks is not None and a.account in self.checks.checking.evaluators:
            held += self.ledger.balance(self.checks.checking.evaluators[a.account].bond_account)
        if self.checks is not None and a.account in self.checks.checking.runners:
            held += self.ledger.balance(self.checks.checking.runners[a.account].bond_account)
        return super().wealth(a) + held

    def effort(self, a: Actor) -> int:
        return a.stats.get("effort", 0)

    def tokens(self, a: Actor) -> int:
        """The micro-tokens an actor holds (#58)."""
        return self.market.tokens.balance(a.account) if self.tokens_on else 0

    def net(self, a: Actor) -> int:
        """Its coin gained, plus its tokens at the run's token price (#58 D5: earnings are coin and tokens)."""
        coin = super().net(a)
        return coin + int(self.tokens(a) * self.token_price) if self.tokens_on else coin

    def net_of_effort(self, a: Actor) -> int:
        """What an actor gained, its cost of development counted (pledgers' pledges are spending, not effort)."""
        return self.net(a) - self.effort(a)
