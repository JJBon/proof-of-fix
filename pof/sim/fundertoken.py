"""One general token earned by funders, investor pools, and an emission that adapts to use (proof-of-fix#193;
simulation only, rule 1: simulated money, no model calls, no chain).

The owner's design (2026-11-09/10), against #186's spec: solvers are paid in stablecoins and funders earn one protocol
token. Several repositories run weekly cycles; some stay healthy (steady valuable fixes) and some stall a quarter in
(few, low-merit fixes). Each cycle:

1. **Merit.** Each repository's fixes are scored in dollars of value by a panel: the median of `k` judges, each off by a
   log-normal `noise` (#184's 15 %). Fix values follow #184's distribution (median $86, p90 $184).
2. **Pay, the thin-cycle fix.** A fix is paid its bounty, if any, and the pool tops it up to its merit (times the pay
   per merit dollar under (b)), pro rata when the pool is short. Unspent coin stays with its funders by share, and
   each funder decides alone (below) to roll it over, withdraw it or move it.
3. **Emission** = min(`rate` x the network's merit, cap). Each fix gets its merit share, capped at `tpc` (tokens per
   coin) x the coin that paid it; what the cap cuts isn't minted (`redistribute` gives it to uncapped fixes instead,
   as #186 D3 says). A fix's tokens go to whoever's coin paid it: its bounty's funder and its pool's funders by the
   coin each had spent.
4. **Burns.** A margin per check (`margin` dollars; registration, each submission's k checks and the merit panel's k,
   plus `external_checks` a cycle bought outside the bounty market), the stakes of failed submissions, and the payout
   fee: the token value the fix's coin earned, up to `fee_cap` (20 %) of the coin (#182). The fee comes out of the
   solver's pay. Every burn is modelled as dollars that buy tokens and burn them: that is the token's only demand.

**Funders.** Bounty buyers fund about `bounty_share` of fixes, at their own estimate of the fix's value (they need the
fix). Bounty-picking investors (`pickers`) fund unfunded issues at an AI estimate (#58 D3, 30 % error) while their
budget lasts. Single-repository investors (`repo_investors` per repository) add `repo_inflow` a cycle to their
repository's pool. The index pool adds `index_inflow` a cycle, spread **by need**: a repository's recent merit less its
recent bounty coin and the coin already waiting in its pool; the index also pulls its own idle coin out of pools
holding more than two cycles of that need. Curated pools aren't modelled.

**Investors' rule (roll over, withdraw, move).** Each cycle, each single-repository investor reviews with probability
`review` (inertia): it compares its repository with `look` others at random by **tokens per coin held** over the last
`window` cycles (its pool funders' tokens over the coin waiting in the pool) and moves its unspent coin and its future
inflow to the best if that's `better` times its own. If not, and its pool spent under a tenth of what it held, it
withdraws half its unspent coin. Otherwise it rolls over.

**Solvers** follow pay: a repository's fix rate is its base rate times its recent pay per merit dollar (gross, bounty
and pool coin over merit, clipped to 0.25-1.5) to the power `solver_elasticity`. Waiting money raises pay only under
(b), and a short pool lowers it unless (c) pays the shortfall later.

**Adaptations (each a switch).** (a) `adapt_cap`: cap = `base` + last cycle's burned tokens. (b) `adapt_pay`: pay per
merit dollar = clamp(pool / merit, 1, `pay_max`). (c) `carry`: underpaid merit (at 1x) is the first claim on the next
cycle's pool, minted when paid, as merit equal to the coin that paid it.

**The token's price** is not predicted. Funding is a purchase of new tokens: a funder's dollar return is its tokens
per coin spent times the price, so the report gives each funder's break-even price (1 / tokens per coin) and the
**flow-clearing price** p*: the highest price at which the year's burns still absorb every token minted. Below p*
burns exceed minting and supply shrinks; above it, funders who sell every token they earn meet less buying than they
sell, so it holds only if someone accumulates tokens, which this model doesn't know about. The simulation itself
doesn't depend on the price except through (a) (burned tokens = burned dollars / price) and the fee, both at `price`.

**Attacks** (#184's team in repository 0, with #186's defences: challenges before the split, judges' merit records,
the 3x issue stake): `self` and `overclaim` file `fakes` correct trivial fixes a cycle (worth $5) claimed at `claim`,
funding each with `own_coin` from a second wallet that the protocol can't tell from an outside funder; colluding
judges accept the claim, honest judges see through it with probability `detect`. `cent` pledges `cent` (1 cent) on
every fix of `unfunded` repositories that nobody funds, for `pledge_cost` each. The attacker's gain is against its
honest twin: the same fixes claimed at their worth and not self-funded (or no pledges).

**Check domains, v2 (proof-of-fix#195).** The judges also answer other contracts' questions: outside requests in
`domains`, each a `Domain` with its requests a cycle (flat, or growing from a start level up to a ceiling), its
`margin` a request (burned, like a check's margin), its judges' real cost an answer (paid to them in stablecoins at
cost: never burned, so it doesn't change any funder's tokens or p*), and its panel: the issue tier's 3 judges or the
constitution tier's 7, the only two tiers Article 3 allows before v3 (#132). With no domains every number is v1's,
bit for bit. `rebate_max` (0: off) is the rebate ceiling v2 proposes: a cycle's outside burns stop at
`rebate_max` x the coin paid to fixes that cycle, less the payout fee's cap and the cycle's other burns, so the value
funders get back per coin spent stays near `rebate_max` whatever outside use grows to; the rest of the margin isn't
charged."""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field, replace
from statistics import mean, median, pstdev
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Domain:
    """A check domain (#195): outside requests a cycle, each burning `margin` and paying its panel at cost."""
    name: str
    tier: str  # #195's verifiability tiers: "checkable", "partly checkable", "judgment"
    requests: float  # a cycle, at cycle 0
    margin: float  # dollars burned per request
    judge_cost: float  # one judge's real cost of an answer (models, tests, fetches), paid in stablecoins at cost
    panel: int = 3  # 3 (the issue tier) or 7 (the constitution tier): Article 3 allows only these before v3
    growth: float = 0.0  # a cycle, compounded (0: flat)
    ceiling: float = 0.0  # requests a cycle at most (0: none)
    minutes: float = 2.0  # slot-minutes of a judge's node an answer takes
    at_stake: float = 1_000.0  # the largest value one request decides: a judge's bond is at least twice it (Art. 3.7)
    price: float = 0.0  # what a buyer pays a request, if set by `priced` (margin = price - the panel's cost)

    def at(self, t: int) -> float:
        n = self.requests * (1 + self.growth) ** t
        return min(n, self.ceiling) if self.ceiling > 0 else n


def priced(name: str, tier: str, price: float, cost: float, panel: int = 3, **kw) -> Domain:
    """A domain priced the market's way (#196): each verdict sells at `price` and costs its panel `cost` in all, paid
    to the judges at cost; the margin burned is what's left, verdicts x (price - cost)."""
    return Domain(name, tier, kw.pop("requests", 0.0), max(0.0, price - cost), judge_cost=cost / panel, panel=panel,
                  price=price, **kw)


@dataclass(frozen=True)
class Params:
    cycles: int = 52
    healthy: int = 8  # repositories that stay healthy
    stalling: int = 4  # repositories that stall at `stall_at`
    unfunded: int = 0  # repositories with no pool, no bounties and no investors (the 1-cent attack's targets)
    stall_at: int = 13
    fix_rate: float = 10.0  # fixes a cycle in a healthy repository (Poisson), before solvers' response
    stall_rate: float = 2.0
    value_median: float = 86.0  # #184: an honest fix's true merit, in dollars (reports/self-healing-v1)
    value_p90: float = 184.0
    stall_median: float = 30.0  # a stalled repository's fixes: fewer, and worth less
    noise: float = 0.15  # #184: a judge's comparison error (multiplicative)
    k: int = 3
    bounty_share: float = 0.3  # of fixes, funded by a buyer who needs them
    bounty_error: float = 0.3  # a buyer's or picker's estimate of a fix's value (#58 D3)
    pickers: int = 10  # investors who fund unfunded issues as bounties
    picker_inflow: float = 150.0  # each, a cycle
    repo_investors: int = 4  # per funded repository at the start
    repo_inflow: float = 100.0  # each, a cycle
    index_inflow: float = 1_500.0  # the index pool, a cycle
    review: float = 0.25  # an investor reviews its position this cycle (inertia)
    look: int = 3  # other repositories it compares
    better: float = 1.5  # moves when another's tokens per coin held is this many times its own
    window: int = 4  # cycles of history investors, the index and solvers look at
    rate: float = 1.0  # tokens per network merit dollar
    cap: float = 8_000.0  # tokens a cycle (#58 emitted 10,000 a week over a smaller market)
    tpc: float = 1.0  # TOKENS_PER_COIN: a fix's tokens are at most this times the coin that paid it
    redistribute: bool = False  # #186 D3: the cut goes to uncapped fixes; #193: it isn't minted
    fee_cap: float = 0.2  # #182: the payout fee is the token value the coin earned, up to this share of the coin
    fee_burn: bool = True  # False: the fee goes to the repository's next pool (#186 FEE_SINK), not a burn
    margin: float = 0.05  # dollars burned per check
    external_checks: float = 0.0  # checks a cycle bought outside the bounty market (CI use), each with the margin
    fail_mean: float = 0.5  # failed submissions per fix (Poisson)
    fail_stake: float = 5.0  # forfeited and burned per failed submission
    price: float = 0.2  # dollars a token, for (a)'s burned tokens and the attacker's fee (see the docstring)
    adapt_cap: bool = False  # (a)
    base: float = 8_000.0  # (a): the cap is this plus last cycle's burned tokens
    adapt_pay: bool = False  # (b)
    pay_max: float = 1.5
    carry: bool = False  # (c)
    solver_elasticity: float = 1.0
    # the attacker (#184's team in repository 0; see the docstring)
    attack: str = ""  # "", "overclaim" (also self-dealing: claim = true value), "cent"
    fakes: int = 5
    claim: float = 5.0
    true_fake: float = 5.0
    own_coin: float = 0.0
    entry: float = 3.5  # #184: an issue's AI check and gas, plus the fix's checks, at cost
    cent: float = 0.01
    pledge_cost: float = 0.02  # gas for one pledge
    validators: int = 15
    colluders: int = 0
    detect: float = 0.8
    challenge: float = 0.5  # #186's defences, at #184's values
    challenge_detect: float = 0.9
    false_challenge: float = 0.1
    penalty: float = 0.5
    recovery: float = 0.02
    floor: float = 0.05
    newcomer: float = 0.2
    bond: float = 250.0
    stake: float = 50.0
    inflation: float = 3.0
    # v2 (#195): outside requests in check domains, and the proposed rebate ceiling
    domains: Tuple[Domain, ...] = ()
    rebate_max: float = 0.0


@dataclass(eq=False)  # pools key funders by identity
class Funder:
    kind: str  # "buyer", "picker", "repo", "index", "attacker", "forfeit"
    repo: int = -1  # its repository now (single-repository investors)
    start: int = -1  # its repository at the start
    contributed: float = 0.0
    spent: float = 0.0
    tokens: float = 0.0
    withdrawn: float = 0.0
    cash: float = 0.0  # coin not in any pool: a picker's budget, the index's reserve
    moved: int = 0

    def left(self, pools: Sequence[Dict["Funder", float]]) -> float:
        """Coin it gets back: withdrawn, unplaced, or still waiting in a pool at the year's end."""
        return self.withdrawn + self.cash + sum(pool.get(self, 0.0) for pool in pools)


@dataclass(eq=False)
class Judge:
    colluding: bool
    score: float = 1.0


@dataclass(eq=False)
class Fix:
    repo: int
    value: float
    team: bool = False
    merit: float = 0.0
    bounty: float = 0.0
    payer: Optional[Funder] = None
    pool: float = 0.0
    tokens: float = 0.0
    checks: int = 0
    owed: float = 0.0  # (c): merit carried as a claim, minted when it is paid rather than now

    @property
    def coin(self) -> float:
        return self.bounty + self.pool


@dataclass
class Result:
    funders: List[Funder]
    pools: List[Dict[Funder, float]]
    kinds: List[str]  # each repository's kind: "healthy", "stalling", "unfunded"
    items: List[List[Tuple[float, float]]] = field(default_factory=list)  # a cycle: each minted item's (tokens, coin)
    mint: List[float] = field(default_factory=list)  # a cycle
    cut: List[float] = field(default_factory=list)  # tokens the per-fix cap cut, a cycle
    burned: List[float] = field(default_factory=list)  # tokens burned a cycle, at `price`
    checks: List[int] = field(default_factory=list)  # in the bounty market, a cycle
    stakes: List[float] = field(default_factory=list)  # failed submissions' stakes, a cycle
    fee_coin_to_pools: float = 0.0
    stall_waiting: List[float] = field(default_factory=list)  # coin waiting in stalling repositories' pools, a cycle
    all_waiting: List[float] = field(default_factory=list)  # in every pool, a cycle
    stall_investor_share: List[float] = field(default_factory=list)  # of single-repo investors, in stalling ones
    fixes: Dict[str, List[int]] = field(default_factory=dict)  # by kind, a cycle
    merit: Dict[str, float] = field(default_factory=dict)  # honest merit by kind, the year
    paid: Dict[str, float] = field(default_factory=dict)  # coin paid to honest fixes by kind (gross)
    underpaid: float = 0.0  # merit dollars never paid (at 1x), healthy and stalling
    waiting_end: float = 0.0  # coin left in pools at the end
    # the attacker
    a_coin_in: float = 0.0  # coin its fixes were paid (it is their solver)
    a_own: float = 0.0  # coin its second wallets put in
    a_tokens: float = 0.0  # tokens its wallets earned
    a_items: List[Tuple[float, float]] = field(default_factory=list)  # its fixes' (tokens, coin), for their fees
    a_fixed: float = 0.0  # entry, margins on its checks, forfeited stakes, bonds, pledge gas
    a_checks: int = 0
    colluders_draw_share: float = 0.0
    # v2: outside requests (#195), a cycle
    outside: List[float] = field(default_factory=list)  # dollars burned by outside requests' margins
    outside_waived: List[float] = field(default_factory=list)  # margin not charged under the rebate ceiling
    outside_requests: List[float] = field(default_factory=list)
    answers: List[float] = field(default_factory=list)  # judges' answers to outside requests
    judges_paid: List[float] = field(default_factory=list)  # their real cost, passed through in stablecoins
    coin: List[float] = field(default_factory=list)  # coin paid to fixes (and claims under (c))


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    n, q, limit = 0, 1.0, math.exp(-lam)
    while True:
        q *= rng.random()
        if q <= limit:
            return n
        n += 1


def _sigma(p: Params) -> float:
    return (math.log(p.value_p90) - math.log(p.value_median)) / 1.2816


class Sim:
    def __init__(self, seed: int, p: Params):
        self.p, self.rng = p, random.Random(seed * 7_919 + 193)
        kinds = ["healthy"] * p.healthy + ["stalling"] * p.stalling + ["unfunded"] * p.unfunded
        self.kinds = kinds
        n = len(kinds)
        self.funded = [r for r in range(n) if kinds[r] != "unfunded"]
        self.pools: List[Dict[Funder, float]] = [{} for _ in range(n)]
        self.funders: List[Funder] = []
        self.investors = []
        for r in self.funded:
            for _ in range(p.repo_investors):
                f = Funder("repo", repo=r, start=r)
                self.investors.append(f)
        self.pickers = [Funder("picker") for _ in range(p.pickers)]
        self.index = Funder("index")
        self.buyers = {r: Funder("buyer", repo=r, start=r) for r in range(n)}
        self.forfeit = Funder("forfeit")  # stakes and fees added to a pool: no one's share
        self.attacker = Funder("attacker", repo=0, start=0)
        self.funders = self.investors + self.pickers + [self.index] + list(self.buyers.values()) + [self.attacker]
        exp_merit = p.fix_rate * p.value_median * math.exp(_sigma(p) ** 2 / 2)
        # trailing history per repository: (merit, bounty coin, coin paid, pool held, pool tokens)
        self.hist: List[List[Tuple[float, float, float, float, float]]] = [
            [(exp_merit, p.bounty_share * exp_merit, exp_merit, 0.0, 0.0)] for _ in range(n)]
        self.claims = [0.0] * n  # (c): merit owed from earlier cycles
        self.cap = p.cap
        self.judges = [Judge(colluding=i < p.colluders) for i in range(p.validators)]
        self.drawn = [0, 0]
        self.r = Result(self.funders, self.pools, kinds, fixes={k: [] for k in ("healthy", "stalling", "unfunded")},
                        merit={"healthy": 0.0, "stalling": 0.0}, paid={"healthy": 0.0, "stalling": 0.0})

    # ----- helpers -----

    def recent(self, r: int, col: int) -> float:
        return mean(h[col] for h in self.hist[r][-self.p.window:])

    def kind(self, r: int, t: int) -> str:
        k = self.kinds[r]
        return "stalling" if k == "stalling" and t >= self.p.stall_at else ("healthy" if k != "unfunded" else k)

    def pay_per_merit(self, r: int) -> float:
        hs = self.hist[r][-self.p.window:]
        m = sum(h[0] for h in hs)
        return min(1.5, max(0.25, sum(h[2] for h in hs) / m)) if m else 1.0

    def signal(self, r: int) -> float:
        """Tokens per coin held: the pool funders' tokens over the coin that waited in the pool, recent cycles."""
        hs = self.hist[r][-self.p.window:]
        held = sum(h[3] for h in hs)
        return sum(h[4] for h in hs) / held if held > 0 else 0.0

    def panel(self) -> List[Judge]:
        p = self.p
        for i, j in enumerate(self.judges):
            if j.score < p.floor:
                self.judges[i] = Judge(colluding=j.colluding, score=p.newcomer)
                if j.colluding:
                    self.r.a_fixed += p.bond
        chosen: List[Judge] = []
        for _ in range(min(p.k, len(self.judges))):
            rest = [j for j in self.judges if j not in chosen]
            chosen.append(self.rng.choices(rest, weights=[j.score for j in rest])[0])
        for j in chosen:
            self.drawn[0] += j.colluding
            self.drawn[1] += 1
        return chosen

    # ----- a cycle -----

    def inflows(self, t: int) -> None:
        p = self.p
        for f in self.investors:
            f.contributed += p.repo_inflow
            self.pools[f.repo][f] = self.pools[f.repo].get(f, 0.0) + p.repo_inflow
        for f in self.pickers:
            f.contributed += p.picker_inflow
            f.cash += p.picker_inflow
        # the index: pull its idle coin from pools holding over two cycles of need, then place by need
        ix = self.index
        ix.contributed += p.index_inflow
        ix.cash += p.index_inflow
        need, gaps = {}, {}
        for r in self.funded:
            gap = max(0.0, self.recent(r, 0) - self.recent(r, 1))
            held = sum(self.pools[r].values())
            mine = self.pools[r].get(ix, 0.0)
            pull = min(mine, max(0.0, held - 2 * gap))
            if pull > 0:
                self.pools[r][ix] = mine - pull
                ix.cash += pull
                held -= pull
            need[r], gaps[r] = max(0.0, gap - held), gap
        # everything it holds is placed: by need first, up to the need, and the rest by recent merit not paid by
        # bounties
        for weights in (need, gaps):
            total = sum(weights.values())
            if total <= 0 or ix.cash <= 0:
                continue
            give = min(ix.cash, total) if weights is need else ix.cash
            for r, w in weights.items():
                if w > 0:
                    self.pools[r][ix] = self.pools[r].get(ix, 0.0) + give * w / total
            ix.cash -= give

    def make_fixes(self, t: int) -> List[Fix]:
        p, rng = self.p, self.rng
        fixes: List[Fix] = []
        for r, k in enumerate(self.kinds):
            kind = self.kind(r, t)
            base, med = (p.stall_rate, p.stall_median) if kind == "stalling" else (p.fix_rate, p.value_median)
            lam = base * self.pay_per_merit(r) ** p.solver_elasticity if k != "unfunded" else base
            n = _poisson(rng, lam)
            self.r.fixes[kind].append(n)
            for _ in range(n):
                f = Fix(r, rng.lognormvariate(math.log(med), _sigma(p)))
                if k != "unfunded" and rng.random() < p.bounty_share:
                    f.bounty = f.value * math.exp(rng.gauss(0, p.bounty_error))
                    f.payer = self.buyers[r]
                fixes.append(f)
        # bounty-picking investors fund unfunded issues in funded repositories at an AI estimate
        open_ = [f for f in fixes if f.payer is None and self.kinds[f.repo] != "unfunded"]
        rng.shuffle(open_)
        for f in open_:
            est = f.value * min(math.exp(rng.gauss(0, p.bounty_error)), math.exp(rng.gauss(0, p.bounty_error)))
            able = [x for x in self.pickers if x.cash >= est]
            if not able:
                continue
            x = rng.choice(able)
            x.cash -= est
            f.bounty, f.payer = est, x
        if p.attack == "overclaim":
            for _ in range(p.fakes):
                f = Fix(0, p.true_fake, team=True)
                if p.own_coin > 0:
                    f.bounty, f.payer = p.own_coin, self.attacker
                    self.r.a_own += p.own_coin
                fixes.append(f)
        if p.attack == "cent":
            for f in fixes:
                if self.kinds[f.repo] == "unfunded":
                    f.bounty, f.payer = p.cent, self.attacker
                    self.r.a_own += p.cent
                    self.r.a_fixed += p.pledge_cost
        return fixes

    def judge(self, fixes: List[Fix]) -> None:
        p, rng = self.p, self.rng
        panels = []
        for f in fixes:
            if self.kinds[f.repo] == "unfunded" and f.payer is None:
                continue  # nobody funds it: not judged, not minted
            f.checks = 1 + (1 + _poisson(rng, p.fail_mean if not f.team else 0.0)) * p.k + p.k
            if p.attack == "overclaim" and f.repo == 0:
                js = self.panel()
                if f.team:
                    scores = [(p.true_fake if not j.colluding and rng.random() < p.detect else p.claim)
                              * math.exp(rng.gauss(0, p.noise)) for j in js]
                else:
                    scores = [f.value * math.exp(rng.gauss(0, p.noise)) for _ in js]
                f.merit = median(scores)
                panels.append((f, js, scores))
            else:
                f.merit = f.value * math.exp(median(rng.gauss(0, p.noise) for _ in range(p.k)))
        if p.attack != "overclaim":
            return
        # #186's defences on the team's repository: challenges before the split, stakes, the judges' records
        for f, js, scores in panels:
            if f.team and f.merit > 2 * p.true_fake and rng.random() < p.challenge:
                if rng.random() < p.challenge_detect:
                    f.merit = p.true_fake
            elif not f.team and rng.random() < p.challenge * p.false_challenge:
                if rng.random() < (1 - p.challenge_detect) / 2:
                    f.merit *= 0.5
            if f.team and p.stake and p.claim > p.inflation * f.merit:
                self.r.a_fixed += p.stake
                self.pools[0][self.forfeit] = self.pools[0].get(self.forfeit, 0.0) + p.stake  # the next pool
            if p.penalty:
                for j, sc in zip(js, scores):
                    if sc > p.inflation * f.merit or sc * p.inflation < f.merit:
                        j.score *= 1 - p.penalty
                    else:
                        j.score = min(1.0, j.score + p.recovery)

    def split(self, t: int, fixes: List[Fix]) -> List[Tuple[Fix, float]]:
        """Pay each repository's fixes from its pool. Returns the claims paid under (c) as (pseudo-fix, coin)."""
        p = self.p
        claims_paid: List[Tuple[Fix, float]] = []
        self.spent_share: Dict[int, Dict[Funder, float]] = {}
        self.held: Dict[int, float] = {}
        by_repo: Dict[int, List[Fix]] = {}
        for f in fixes:
            by_repo.setdefault(f.repo, []).append(f)
        for r in self.funded:
            pool = self.pools[r]
            held = sum(pool.values())
            self.held[r] = held
            avail = held
            out = 0.0
            if p.carry and self.claims[r] > 0 and avail > 0:
                pay = min(avail, self.claims[r])
                self.claims[r] -= pay
                avail -= pay
                out += pay
                claims_paid.append((Fix(r, 0.0, merit=pay, pool=pay), pay))
            fs = [f for f in by_repo.get(r, []) if f.merit > 0]
            need1 = sum(max(0.0, f.merit - f.bounty) for f in fs)
            ppm = min(p.pay_max, max(1.0, avail / need1)) if p.adapt_pay and need1 > 0 else 1.0
            targets = [max(0.0, f.merit * ppm - f.bounty) for f in fs]
            want = sum(targets)
            scale = min(1.0, avail / want) if want > 0 else 0.0
            for f, x in zip(fs, targets):
                f.pool = x * scale
                out += f.pool
                if p.carry and not f.team:
                    f.owed = max(0.0, f.merit - f.bounty - f.pool)
                    self.claims[r] += f.owed
                elif not f.team and self.kind(r, t) != "unfunded":
                    self.r.underpaid += max(0.0, f.merit - f.bounty - f.pool)
            # spend the pool by shares
            share: Dict[Funder, float] = {}
            if out > 0 and held > 0:
                frac = out / held
                for g in list(pool):
                    s = pool[g] * frac
                    pool[g] -= s
                    g.spent += s
                    share[g] = s / out
            self.spent_share[r] = share
        return claims_paid

    def emit(self, t: int, fixes: List[Fix], claims_paid: List[Tuple[Fix, float]]) -> None:
        p, r = self.p, self.r
        items = [f for f in fixes if f.merit > 0] + [c for c, _ in claims_paid]
        w = [f.merit - f.owed for f in items]  # each merit dollar counts once: carried merit when it is paid
        M = sum(w)
        E = min(p.rate * M, self.cap)
        caps = [p.tpc * f.coin for f in items]
        if p.redistribute:
            alloc = [0.0] * len(items)
            free = [i for i in range(len(items))]
            left = E
            while free and left > 1e-12:
                m = sum(w[i] for i in free)
                if m <= 0:
                    break
                over = [i for i in free if left * w[i] / m > caps[i]]
                if not over:
                    for i in free:
                        alloc[i] = left * w[i] / m
                    left = 0.0
                    break
                for i in over:
                    alloc[i] = caps[i]
                    left -= caps[i]
                free = [i for i in free if i not in over]
        else:
            alloc = [min(E * x / M, c) if M else 0.0 for x, c in zip(w, caps)]
        minted = sum(alloc)
        r.mint.append(minted)
        r.cut.append(E - minted)
        pool_tokens: Dict[int, float] = {}
        cycle_items = []
        for f in fixes:  # bounty coin is spent whether or not it earns tokens
            if f.payer is not None and f.bounty > 0:
                f.payer.spent += f.bounty
                if f.payer.kind == "buyer":
                    f.payer.contributed += f.bounty
        for f, tk in zip(items, alloc):
            f.tokens = tk
            if tk <= 0 or f.coin <= 0:
                continue
            cycle_items.append((tk, f.coin))
            if f.payer is not None and f.bounty > 0:
                part = tk * f.bounty / f.coin
                f.payer.tokens += part
                if f.payer is self.attacker:
                    r.a_tokens += part
            pool_tokens[f.repo] = pool_tokens.get(f.repo, 0.0) + tk * f.pool / f.coin
        r.items.append(cycle_items)
        for rep, tk in pool_tokens.items():
            for g, s in self.spent_share.get(rep, {}).items():
                g.tokens += tk * s
        self.pool_tokens = pool_tokens

    def burn(self, t: int, fixes: List[Fix], claims_paid) -> None:
        p, r = self.p, self.r
        checks = sum(f.checks for f in fixes)
        fails = sum(max(0, (f.checks - 1 - 2 * p.k) // p.k) for f in fixes if f.checks)
        stakes = fails * p.fail_stake
        r.checks.append(checks)
        r.stakes.append(stakes)
        dollars = p.margin * (checks + p.external_checks) + stakes
        fee_tokens = 0.0
        for f in list(fixes) + [c for c, _ in claims_paid]:
            if f.tokens > 0:
                fee = min(f.tokens * p.price, p.fee_cap * f.coin)
                if p.fee_burn:
                    fee_tokens += fee / p.price
                else:
                    self.pools[f.repo][self.forfeit] = self.pools[f.repo].get(self.forfeit, 0.0) + fee
                    r.fee_coin_to_pools += fee
                if f.team or (p.attack == "cent" and f.payer is self.attacker):
                    r.a_items.append((f.tokens, f.coin))
        coin = sum(f.coin for f in fixes) + sum(c for _, c in claims_paid)
        outside, waived = self.outside(t, coin, dollars)
        dollars = dollars + outside
        r.coin.append(coin)
        r.outside.append(outside)
        r.outside_waived.append(waived)
        burned = fee_tokens + dollars / p.price
        r.burned.append(burned)
        if p.adapt_cap:
            self.cap = p.base + burned

    def outside(self, t: int, coin: float, dollars: float) -> Tuple[float, float]:
        """The outside requests' margins burned this cycle, and what the rebate ceiling waives; records the
        validators' work and pay (v2, #195)."""
        p, r = self.p, self.r
        n = [d.at(t) for d in p.domains]
        r.outside_requests.append(sum(n))
        r.answers.append(sum(x * d.panel for x, d in zip(n, p.domains)))
        r.judges_paid.append(sum(x * d.panel * d.judge_cost for x, d in zip(n, p.domains)))
        want = sum(x * d.margin for x, d in zip(n, p.domains))
        if p.rebate_max <= 0:
            return want, 0.0
        room = max(0.0, (p.rebate_max - (p.fee_cap if p.fee_burn else 0.0)) * coin - dollars)
        return min(want, room), max(0.0, want - room)

    def account(self, t: int, fixes: List[Fix], claims_paid) -> None:
        p, r = self.p, self.r
        for rep in range(len(self.kinds)):
            fs = [f for f in fixes if f.repo == rep and not f.team]
            m = sum(f.merit for f in fs)
            b = sum(f.bounty for f in fs)
            paid = sum(f.coin for f in fs) + sum(c for x, c in claims_paid if x.repo == rep)
            kind = self.kind(rep, t)
            if kind in r.merit:
                r.merit[kind] += m
                r.paid[kind] += paid
            self.hist[rep].append((m, b, paid, self.held.get(rep, 0.0), self.pool_tokens.get(rep, 0.0)))
            self.hist[rep] = self.hist[rep][-p.window:]
        for f in fixes:
            if f.team or (p.attack == "cent" and f.payer is self.attacker):
                r.a_coin_in += f.coin if f.team else 0.0
                r.a_checks += f.checks if f.team else 0
                if f.team:
                    r.a_fixed += p.entry + p.margin * f.checks

    def review(self, t: int) -> None:
        p, rng = self.p, self.rng
        if t + 1 < p.window:
            return
        sig = {rep: self.signal(rep) for rep in self.funded}
        for f in self.investors:
            if rng.random() >= p.review:
                continue
            others = [x for x in self.funded if x != f.repo]
            look = rng.sample(others, min(p.look, len(others)))
            best = max(look, key=lambda x: sig[x])
            mine = self.pools[f.repo].get(f, 0.0)
            if sig[best] > p.better * sig[f.repo] and sig[best] > 0:
                self.pools[f.repo][f] = 0.0
                self.pools[best][f] = self.pools[best].get(f, 0.0) + mine
                f.repo = best
                f.moved += 1
            else:
                hs = self.hist[f.repo][-p.window:]
                held = sum(h[3] for h in hs)
                spent = sum(h[2] - h[1] for h in hs)  # coin paid less bounties: what the pool paid
                if held > 0 and spent < 0.1 * held and mine > 0:
                    self.pools[f.repo][f] = mine / 2
                    f.withdrawn += mine / 2

    def record(self, t: int) -> None:
        r = self.r
        stall = [x for x in self.funded if self.kinds[x] == "stalling"]
        total = sum(sum(v for g, v in self.pools[x].items() if g is not self.forfeit) for x in self.funded)
        ins = sum(sum(v for g, v in self.pools[x].items() if g is not self.forfeit) for x in stall)
        r.stall_waiting.append(max(0.0, ins))
        r.all_waiting.append(total)
        r.stall_investor_share.append(sum(1 for f in self.investors if f.repo in stall) / max(1, len(self.investors)))

    def run(self) -> Result:
        for t in range(self.p.cycles):
            self.inflows(t)
            fixes = self.make_fixes(t)
            self.judge(fixes)
            claims_paid = self.split(t, fixes)
            self.emit(t, fixes, claims_paid)
            self.burn(t, fixes, claims_paid)
            self.account(t, fixes, claims_paid)
            self.review(t)
            self.record(t)
        self.r.waiting_end = sum(sum(v for g, v in pool.items() if g is not self.forfeit) for pool in self.pools)
        if self.p.carry:  # what is still owed at the year's end
            self.r.underpaid = sum(self.claims[x] for x in self.funded)
        self.r.colluders_draw_share = self.drawn[0] / self.drawn[1] if self.drawn[1] else 0.0
        return self.r


def run(seed: int, p: Params = Params()) -> Result:
    return Sim(seed, p).run()


# ---------- reading a run ----------

def burned_at(r: Result, p: Params, price: float, margin: Optional[float] = None,
              external: Optional[float] = None, cycles: Optional[Sequence[int]] = None,
              outside: Optional[Sequence[float]] = None) -> float:
    """Tokens burned at a token price over `cycles` (default: the year), from the run's minted items, checks and
    stakes. The margin and the outside checks may be changed after the fact: without (a) the run doesn't depend on
    them or on the price. `outside` (v2) replaces the run's outside requests' burned dollars, a cycle."""
    m = p.margin if margin is None else margin
    out = r.outside if outside is None else outside
    ext = p.external_checks if external is None else external
    idx = range(len(r.mint)) if cycles is None else cycles
    total = 0.0
    for i in idx:
        if p.fee_burn:
            total += sum(min(tk, p.fee_cap * c / price) for tk, c in r.items[i])
        total += (m * (r.checks[i] + ext) + r.stakes[i] + out[i]) / price
    return total


def flow_price(r: Result, p: Params, margin: Optional[float] = None, external: Optional[float] = None,
               cycles: Optional[Sequence[int]] = None, outside: Optional[Sequence[float]] = None) -> float:
    """p*: the highest token price at which the year's burns absorb every token minted (no (a): mint doesn't depend
    on the price). Burns fall as the price rises, so bisect on a log scale. `cycles` (v2): over those cycles only."""
    mint = sum(r.mint) if cycles is None else sum(r.mint[i] for i in cycles)
    if mint <= 0:
        return float("inf")
    lo, hi = 1e-6, 1e6
    if burned_at(r, p, hi, margin, external, cycles, outside) >= mint:
        return hi
    if burned_at(r, p, lo, margin, external, cycles, outside) < mint * (1 - 1e-9):
        return 0.0
    for _ in range(60):
        mid = math.sqrt(lo * hi)
        if burned_at(r, p, mid, margin, external, cycles, outside) >= mint * (1 - 1e-9):
            lo = mid
        else:
            hi = mid
    return lo


def outside_needed(r: Result, p: Params, margin: float, price: float) -> float:
    """Outside checks a cycle, at `margin` each, for the year's burns to absorb every token minted at `price` (0: the
    bounty market's own burns already do)."""
    fee = sum(min(tk, p.fee_cap * c / price) for cyc in r.items for tk, c in cyc) if p.fee_burn else 0.0
    dollars = price * (sum(r.mint) - fee) - sum(r.stakes) - margin * sum(r.checks)
    return max(0.0, dollars / (margin * len(r.mint)))


def flow_price_rerun(seed: int, p: Params, steps: int = 24) -> Tuple[float, Result]:
    """p* under (a), where the cap follows burned tokens: the run is repeated at each price tried."""
    lo, hi = 1e-3, 1e3
    for _ in range(steps):
        mid = math.sqrt(lo * hi)
        r = run(seed, replace(p, price=mid))
        lo, hi = (mid, hi) if sum(r.burned) >= sum(r.mint) else (lo, mid)
    return lo, run(seed, replace(p, price=lo))


def tpc_spent(fs: Sequence[Funder]) -> float:
    spent = sum(f.spent for f in fs)
    return sum(f.tokens for f in fs) / spent if spent else 0.0


def attack_profit(r: Result, p: Params, price: float) -> float:
    fee = sum(min(tk * price, p.fee_cap * c) for tk, c in r.a_items)
    return r.a_coin_in - r.a_own - fee + r.a_tokens * price - r.a_fixed


def pays_from(base: Result, att: Result, p: Params, pt: Params) -> float:
    """The lowest price at which the attack gains over its honest twin (inf: none up to $100 a token)."""
    grid = [10 ** (x / 40) for x in range(-160, 81)]  # $0.0001 to $100
    prev = None
    for x in grid:
        gain = attack_profit(att, p, x) - attack_profit(base, pt, x)
        if gain > 0:
            if prev is None:
                return x
            lo, hi = prev, x
            for _ in range(40):
                mid = (lo + hi) / 2
                g = attack_profit(att, p, mid) - attack_profit(base, pt, mid)
                lo, hi = (lo, mid) if g > 0 else (mid, hi)
            return hi
        prev = x
    return float("inf")


# ---------- the report ----------

PRICES = (0.05, 0.2, 0.5, 1.0)

CONFIGS = [
    ("none", {}),
    ("(a) cap = base + last burns", {"adapt_cap": True}),
    ("(a) with a base of 2,000", {"adapt_cap": True, "base": 2_000.0}),
    ("(b) pay up to 1.5x when money waits", {"adapt_pay": True}),
    ("(c) shortfall carried", {"carry": True}),
    ("(b) + (c)", {"adapt_pay": True, "carry": True}),
    ("(a) + (b) + (c)", {"adapt_cap": True, "adapt_pay": True, "carry": True}),
]


def _ms(xs: Sequence[float], fmt: str = "{:.2f}") -> str:
    xs = [x for x in xs if math.isfinite(x)]
    if not xs:
        return "–"
    return (fmt + " ± " + fmt).format(mean(xs), pstdev(xs) if len(xs) > 1 else 0.0)


def _pct(xs: Sequence[float], q: float) -> float:
    s = sorted(xs)
    if not s:
        return float("nan")
    i = q * (len(s) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


def groups(r: Result, p: Params) -> Dict[str, List[Funder]]:
    stall = {x for x, k in enumerate(r.kinds) if k == "stalling"}
    inv = [f for f in r.funders if f.kind == "repo"]
    return {
        "bounty buyers (need the fix)": [f for f in r.funders if f.kind == "buyer" and r.kinds[f.repo] != "unfunded"],
        "investors picking bounties": [f for f in r.funders if f.kind == "picker"],
        "one repository's pool, started healthy": [f for f in inv if f.start not in stall],
        "one repository's pool, started in one that stalls": [f for f in inv if f.start in stall],
        "  of those, still in a stalling one at the end": [f for f in inv if f.start in stall and f.repo in stall],
        "the index pool (by need)": [f for f in r.funders if f.kind == "index"],
    }


def investors(seeds: Sequence[int], base: Params, data: dict, key: str) -> List[str]:
    rows: Dict[str, Dict[str, list]] = {}
    pstars, fees = [], []
    for s in seeds:
        r = run(s, base)
        ps = flow_price(r, base)
        pstars.append(ps)
        coin = sum(c for cyc in r.items for _, c in cyc)
        fees.append(sum(min(tk * ps, base.fee_cap * c) for cyc in r.items for tk, c in cyc) / coin)
        for name, fs in groups(r, base).items():
            d = rows.setdefault(name, {"tpc": [], "each": [], "left": [], "ret": [], "val": []})
            if any(f.spent > 0 for f in fs):
                d["tpc"].append(tpc_spent(fs))
            for f in fs:
                if f.spent > 0:
                    d["each"].append(f.tokens / f.spent)
                if f.contributed > 0:
                    left = f.left(r.pools)
                    d["left"].append(left / f.contributed)
                    d["ret"].append((f.tokens * ps + left) / f.contributed - 1)
                    d["val"].append(f.tokens / f.spent * ps if f.spent else 0.0)
    out = [f"The flow-clearing price p* = **${mean(pstars):.3f} ± {pstev(pstars):.3f}** a token "
           f"(margin ${base.margin:g} a check, no outside checks). At p* the payout fee takes {mean(fees):.1%} of the "
           "coin paid to solvers.\n",
           "| Funder | Tokens per coin spent (mean ± sd over seeds) | p10 – p90 over funders | Break-even price "
           "($ a token) | Coin left over (of what it put in) | Value back per coin spent at p* | Return on what it put "
           "in at p* (p10 – p90) |", "|---|---|---|---|---|---|---|"]
    data[key] = {"p_star": pstars, "fee_share_at_p_star": fees, "groups": {}}
    for name, d in rows.items():
        t = [x for x in d["tpc"] if x > 0]
        be = 1 / mean(t) if t and mean(t) > 0 else float("inf")
        left = f"{mean(d['left']):.0%}" if d["left"] else "–"
        ret = (f"{mean(d['ret']):+.0%} ({_pct(d['ret'], .1):+.0%} – {_pct(d['ret'], .9):+.0%})" if d["ret"] else "–")
        out.append(f"| {name} | {_ms(d['tpc'])} | {_pct(d['each'], .1):.2f} – {_pct(d['each'], .9):.2f} | "
                   f"${be:.2f} | {left} | {mean(d['val']):.0%} | {ret} |")
        data[key]["groups"][name.strip()] = {k: (mean(v) if v else None) for k, v in d.items()}
        data[key]["groups"][name.strip()].update(p10_each=_pct(d["each"], .1), p90_each=_pct(d["each"], .9),
                                                 p10_ret=_pct(d["ret"], .1), p90_ret=_pct(d["ret"], .9))
    return out


def pstev(xs: Sequence[float]) -> float:
    return pstdev(xs) if len(xs) > 1 else 0.0


def adaptation(seeds: Sequence[int], base: Params, data: dict) -> List[str]:
    out = ["| Adaptation | Coin waiting in stalling repositories ($): cycle 12 → 16 → 26 → 52 | "
           "Single-repo investors still in stalling ones: 12 → 16 → 26 → 52 | Fixes a cycle, healthy repo (last "
           "quarter) | Fixes a cycle, stalling repo (last quarter) | Solvers' pay per merit dollar, healthy (gross) | "
           "Merit left unpaid | Pool investors' tokens per coin spent | Coin waiting at the year's end (of all "
           "pool coin put in) | p* ($) | Pool investors' value back per coin at p* |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    data["adaptation"] = {}
    supply = ["| Adaptation | Mint ÷ burn over the year at $0.05 | at $0.20 | at $1.00 | Net tokens added a cycle, last "
              "quarter, at $1.00 | Tokens the per-fix cap cut (of what the formula allowed) |",
              "|---|---|---|---|---|---|"]
    for name, kw in CONFIGS:
        p = replace(base, **kw)
        rs = [run(s, p) for s in seeds]
        sh = lambda r, i: r.stall_waiting[i]  # noqa: E731
        si = lambda r, i: r.stall_investor_share[i]  # noqa: E731
        idx = tuple(min(i, p.cycles - 1) for i in (11, 15, 25, p.cycles - 1))
        bal = " → ".join(f"{mean(sh(r, i) for r in rs):,.0f}" for i in idx)
        inv = " → ".join(f"{mean(si(r, i) for r in rs):.0%}" for i in idx)
        nh = mean(mean(r.fixes["healthy"][-13 * p.healthy:]) for r in rs)
        ns = mean(mean(r.fixes["stalling"][-13 * p.stalling:]) for r in rs) if p.stalling else 0.0
        ppm = [r.paid["healthy"] / r.merit["healthy"] for r in rs]
        unpaid = [r.underpaid / (r.merit["healthy"] + r.merit["stalling"]) for r in rs]
        put = [sum(f.contributed for f in r.funders if f.kind in ("repo", "index")) for r in rs]
        waiting = [r.waiting_end / x for r, x in zip(rs, put)]
        tpcs = [tpc_spent([f for f in r.funders if f.kind in ("repo", "index")]) for r in rs]
        if not p.adapt_cap:
            ps = [flow_price(r, p) for r in rs]
        else:
            ps = [flow_price_rerun(s, p)[0] for s in seeds]
        pst = _ms(ps, "{:.3f}")
        vals = [x * t for x, t in zip(ps, tpcs)]
        out.append(f"| {name} | {bal} | {inv} | {nh:.1f} | {ns:.1f} | {_ms(ppm)} | {mean(unpaid):.1%} | "
                   f"{_ms(tpcs)} | {mean(waiting):.1%} | {pst} | {mean(vals):.0%} |")
        ratios, added = [], []
        last = range(p.cycles - 13, p.cycles)
        for price in (0.05, 0.2, 1.0):
            if p.adapt_cap:  # the cap follows burned tokens, so the run depends on the price
                rq = [run(s, replace(p, price=price)) for s in seeds]
                ratios.append([sum(r.mint) / sum(r.burned) for r in rq])
                if price == 1.0:
                    added = [mean(r.mint[-13:]) - mean(r.burned[-13:]) for r in rq]
            else:
                ratios.append([sum(r.mint) / burned_at(r, p, price) for r in rs])
                if price == 1.0:
                    added = [mean(r.mint[-13:]) - burned_at(r, p, price, cycles=last) / 13 for r in rs]
        cut = [max(0.0, sum(r.cut)) / (sum(r.cut) + sum(r.mint)) for r in rs]
        supply.append(f"| {name} | " + " | ".join(_ms(x) for x in ratios) + f" | {_ms(added, '{:,.0f}')} | "
                      f"{mean(cut):.1%} |")
        data["adaptation"][name] = {
            "stall_waiting": [mean(sh(r, i) for r in rs) for i in range(p.cycles)],
            "all_waiting": [mean(r.all_waiting[i] for r in rs) for i in range(p.cycles)],
            "stall_investor_share": [mean(si(r, i) for r in rs) for i in range(p.cycles)],
            "fixes_healthy_last_quarter": nh, "fixes_stalling_last_quarter": ns, "pay_per_merit_healthy": ppm,
            "unpaid_share": unpaid, "pool_tokens_per_coin": tpcs, "waiting_end_share": waiting, "p_star": ps,
            "mint_over_burn": dict(zip(("0.05", "0.2", "1.0"), ratios)), "added_per_cycle_at_1.0": added,
            "value_per_coin_at_p_star": vals,
            "cut_share": cut}
    return out + ["", "**Supply.** Mint over burn above 1 means the supply grows. With (a) the run is repeated at "
                  "each price, since the cap follows burned tokens.", ""] + supply


ATTACKS = [  # (label, attack, plays as (claim, own coin), changes to the defences)
    ("self-dealing: a $5 fix claimed at its worth, funded from a second wallet", "overclaim",
     [(5.0, x) for x in (1.0, 5.0, 50.0)], {}),
    ("overclaimed merit, no own funding (#184's team)", "overclaim", [(c, 0.0) for c in (15.0, 50.0, 200.0)], {}),
    ("overclaimed merit, funded from a second wallet", "overclaim",
     [(c, x) for c in (15.0, 50.0, 200.0) for x in (5.0, 50.0, 200.0)], {}),
    ("the same, without the issue stake (what the stake does)", "overclaim",
     [(c, x) for c in (15.0, 50.0, 200.0) for x in (0.0, 5.0, 50.0, 200.0)], {"stake": 0.0}),
]


def farming(seeds: Sequence[int], base: Params, data: dict, colluders: Sequence[int] = (0, 3, 5)) -> List[str]:
    out = ["| Attack | Colluding judges (of 15) | Its best play | Gain a year over its honest twin at $0.05 | at $0.20 | "
           "at $0.50 | at $1.00 | Pays from a token price of (any play, mean over seeds) | …where honest pool investors get back, per coin spent |",
           "|---|---|---|---|---|---|---|---|---|"]
    data["farming"] = []
    for name, kind, plays, kw in ATTACKS:
        for c in colluders:
            twin_p = replace(base, attack=kind, colluders=c, claim=base.true_fake, own_coin=0.0, **kw)
            twins = {s: run(s, twin_p) for s in seeds}
            best = None
            pays = [float("inf")] * len(seeds)  # per seed: the lowest price at which any play gains
            val = [float("nan")] * len(seeds)
            for claim, own in plays:
                q = replace(twin_p, claim=claim, own_coin=own)
                rs = {s: run(s, q) for s in seeds}
                gains = {x: [attack_profit(rs[s], q, x) - attack_profit(twins[s], twin_p, x) for s in seeds]
                         for x in PRICES}
                for i, s in enumerate(seeds):
                    x = pays_from(twins[s], rs[s], q, twin_p)
                    if x < pays[i]:
                        pays[i] = x
                        val[i] = x * tpc_spent([f for f in rs[s].funders if f.kind in ("repo", "index")])
                score = max(mean(v) for v in gains.values())
                if best is None or score > best[0]:
                    best = (score, claim, own, gains)
            _, claim, own, gains = best
            val = [v for v in val if math.isfinite(v)]
            fin = [x for x in pays if math.isfinite(x)]
            if fin and max(fin) < 0.001:
                where = "any price: it pays in coin alone"
            else:
                where = (f"${mean(fin):.2f}" + (f" ({len(pays) - len(fin)} of {len(pays)} seeds never)"
                                                 if len(fin) < len(pays) else "")) if fin else "**never** (to $100)"
            out.append(f"| {name} | {c} | claims ${claim:g}, own coin ${own:g} | "
                       + " | ".join(_ms(gains[x], "{:,.0f}") for x in PRICES)
                       + f" | {where} | " + (f"{mean(val):.0%}" if val and where[0] == "$" else "–") + " |")
            data["farming"].append({"attack": name, "colluders": c, "claim": claim, "own_coin": own,
                                    "gain": {str(x): gains[x] for x in PRICES}, "pays_from": pays,
                                    "value_per_coin_then": val})
    # the 1-cent pledge on valuable fixes nobody funds
    cent = replace(base, unfunded=2, attack="cent")
    for label, kw in (("per-fix cap on (the design)", {}),
                      ("per-fix cap on, the cut given to uncapped fixes (#186 D3)", {"redistribute": True}),
                      ("no per-fix cap", {"tpc": 1e12})):
        q = replace(cent, **kw)
        twin = replace(q, attack="")
        rs = {s: run(s, q) for s in seeds}
        ts = {s: run(s, twin) for s in seeds}
        gains = {x: [attack_profit(rs[s], q, x) - attack_profit(ts[s], twin, x) for s in seeds] for x in PRICES}
        pays = [pays_from(ts[s], rs[s], q, twin) for s in seeds]
        fin = [x for x in pays if math.isfinite(x)]
        hon = [tpc_spent([f for f in rs[s].funders if f.kind in ("repo", "index")]) /
               tpc_spent([f for f in ts[s].funders if f.kind in ("repo", "index")]) - 1 for s in seeds]
        where = f"${mean(fin):.4f}" if fin else "**never** (to $100)"
        out.append(f"| 1-cent pledges on every fix of 2 unfunded repositories, {label} | – | 1 cent a fix, "
                   f"${base.pledge_cost:g} gas | " + " | ".join(_ms(gains[x], "{:,.0f}") for x in PRICES)
                   + f" | {where} | honest pool investors' tokens per coin {mean(hon):+.1%} |")
        data["farming"].append({"attack": "cent", "variant": label, "gain": {str(x): gains[x] for x in PRICES},
                                "pays_from": pays, "honest_tokens_per_coin_change": hon})
    return out


SUSTAIN_MARGINS = (0.01, 0.05, 0.10, 0.25)
SUSTAIN_EXTERNAL = (0.0, 10_000.0, 100_000.0, 1_000_000.0)


def sustainability(seeds: Sequence[int], base: Params, data: dict) -> List[str]:
    rs = [run(s, base) for s in seeds]
    nofee = replace(base, fee_burn=False)
    rn = [run(s, nofee) for s in seeds]
    inv = lambda r: tpc_spent([f for f in r.funders if f.kind in ("repo", "index")])  # noqa: E731
    put = mean(sum(f.spent for f in r.funders if f.kind in ("repo", "index", "picker", "buyer")) / base.cycles
               for r in rs)
    checks = mean(sum(r.checks) / base.cycles for r in rs)
    out = [f"The bounty market itself runs about {checks:,.0f} checks a cycle; funders spend about ${put:,.0f} a cycle "
           "on fixes. Each cell: pool investors' value back per coin spent at the flow-clearing price p* (their tokens "
           "per coin × p*), with p* in brackets.\n",
           "| Payout fee | Margin a check | " + " | ".join(f"{x:,.0f} outside checks a cycle" for x in SUSTAIN_EXTERNAL)
           + " | Outside checks a cycle for pool investors to get back 50 % | …100 % (break even) |",
           "|---|---|" + "---|" * (len(SUSTAIN_EXTERNAL) + 2)]
    data["sustainability"] = {"checks_per_cycle": checks, "funded_per_cycle": put, "cells": []}
    for label, p, runs in (("burned (≤ 20 %)", base, rs), ("to the next pool", nofee, rn)):
        for m in SUSTAIN_MARGINS:
            cells = []
            for ext in SUSTAIN_EXTERNAL:
                ps = [flow_price(r, p, m, ext) for r in runs]
                v = [inv(r) * x for r, x in zip(runs, ps)]
                cells.append(f"{mean(v):.0%} (${mean(ps):.3f})")
                data["sustainability"]["cells"].append({"fee": label, "margin": m, "external": ext,
                                                        "p_star": ps, "value_per_coin": v})
            need = {}
            for target in (0.5, 1.0):
                need[target] = [outside_needed(r, p, m, target / inv(r)) for r in runs]
                cells.append(f"{mean(need[target]):,.0f}")
            data["sustainability"]["cells"].append({"fee": label, "margin": m, "outside_for_half": need[0.5],
                                                    "outside_for_break_even": need[1.0]})
            out.append(f"| {label} | ${m:g} | " + " | ".join(cells) + " |")
    return out


def _params_v1(p: Params) -> dict:
    """v1's parameters as v1's JSON has them: v2's fields only when they're set."""
    d = p.__dict__.copy()
    for k in ("domains", "rebate_max"):
        if not d[k]:
            del d[k]
    if "domains" in d:
        d["domains"] = [x.__dict__.copy() for x in p.domains]
    return d


def report(seeds: Sequence[int], base: Params = Params(), colluders: Sequence[int] = (0, 3, 5)) -> Tuple[str, dict]:
    data: dict = {"seeds": list(seeds), "params": _params_v1(base)}
    out = ["### 1. Investors' returns, no adaptation\n"]
    out += investors(seeds, base, data, "investors_none")
    out += ["", "### 1b. Investors' returns with (b) + (c)\n"]
    out += investors(seeds, replace(base, adapt_pay=True, carry=True), data, "investors_bc")
    out += ["", "### 2. Farming, with the funder rewards (#186's defences on; honest judges see through an overclaim "
            f"{base.detect:.0%} of the time)\n"]
    out += farming(seeds, base, data, colluders)
    out += ["", "### 3. Adaptation\n"]
    out += adaptation(seeds, base, data)
    out += ["", "### 4. Sustainability: what burns must cover\n"]
    out += sustainability(seeds, base, data)
    return "\n".join(out), data


# ---------- v2: outside revenue from check domains (#195) ----------

# #195's three verifiability tiers as four domains, with v2's assumptions (reports/fundertoken-v2.md lists their
# sources). Each run sets the requests.
DOMAINS: Dict[str, Domain] = {
    # #196's best fit: bug-bounty and audit-contest reports, each with a proof-of-concept run; contest judging pays
    # about $8-10 an issue (Sherlock). Our cost isn't measured: a medium code check is $0.37 (costs v1), a PoC on a
    # forked chain more, so $1 here and $0.37-3 in the scenarios.
    "triage": priced("security triage (bounty and contest reports with a PoC)", "checkable", 9.0, 1.0, minutes=20.0,
                     at_stake=10_000.0),
    # AI pull-request review sells for about $1 (Greptile, #196); a medium check costs $0.37 at judge grade
    "code": priced("code checks for outside repositories", "checkable", 1.0, 0.37, minutes=6.0),
    # routine resolution and fact checks with fetched sources: UMA's AI drafts one for $0.005, proposers get $2-5;
    # we'd sell at $0.50 against a cost of 3 x $0.15 (a model reading sources, and a zkTLS fetch, #139)
    "resolution": priced("routine resolution and fact checks with fetched sources", "partly checkable", 0.50, 0.45,
                         minutes=3.0),
    # prediction-market disputes: about 50 a week escalate, each behind a $750 bond (#196); all 7 judges, $30 a
    # verdict assumed, cost 7 x $0.21 (an escalated medium review, costs v1) plus fetches
    "disputes": priced("prediction-market disputes", "judgment", 30.0, 1.50, panel=7, minutes=5.0,
                       at_stake=50_000.0),
    # Lean proofs: nobody pays per check today (#196), so sold at cost, for credibility
    "maths": priced("maths: does a Lean statement say what the question means", "checkable", 0.09, 0.09,
                    minutes=10.0),
}
MIXES: List[Tuple[str, Dict[str, float]]] = [  # shares of requests
    ("mostly checkable", {"triage": 0.1, "code": 0.7, "resolution": 0.1, "maths": 0.1}),
    ("balanced", {"triage": 0.05, "code": 0.35, "resolution": 0.4, "disputes": 0.1, "maths": 0.1}),
    ("mostly judgment and facts", {"triage": 0.02, "code": 0.08, "resolution": 0.6, "disputes": 0.3}),
    ("security triage only", {"triage": 1.0}),
    ("code checks only", {"code": 1.0}),
    ("routine resolution only", {"resolution": 1.0}),
    ("disputes only", {"disputes": 1.0}),
]
# #196's market: the whole paid on-chain verdict market is about 5,000-30,000 requests a week; what we could serve at a
# margin, about 1,000-4,000; a realistic first-year share, a few hundred to a few thousand.
MARKET_SCENARIOS: List[Tuple[str, Dict[str, float]]] = [  # requests a cycle by domain
    ("#196's first year, low", {"triage": 300, "code": 500, "maths": 50}),
    ("#196's first year, realistic", {"triage": 900, "code": 2_000, "disputes": 10, "maths": 200}),
    ("all we could serve (#196's upper end)", {"triage": 3_000, "code": 5_000, "disputes": 50, "resolution": 2_000,
                                               "maths": 500}),
]
TRIAGE_VOLUMES = (300.0, 900.0, 3_000.0)
TRIAGE_PRICES = (8.0, 10.0)
TRIAGE_COSTS = (0.37, 1.0, 3.0)
V2_MARGINS = (0.01, 0.02, 0.05, 0.10, 0.25, 0.50, 1.00, 2.00)
V2_GRID_MARGINS = (0.05, 0.10, 0.25, 1.00)
V2_VOLUMES = (10_000.0, 25_000.0, 50_000.0, 100_000.0, 250_000.0, 1_000_000.0)
V2_CONFIGS = [("none", {}), ("(b) + (c)", {"adapt_pay": True, "carry": True})]
V2_A_CONFIGS = [("(a) with a base of 2,000", {"adapt_cap": True, "base": 2_000.0}),
                ("(a) base 2,000 + (b) + (c)", {"adapt_cap": True, "base": 2_000.0, "adapt_pay": True,
                                                "carry": True})]
# validators (v2's assumptions)
SEATS = 7  # Article 3: seven judges, a different operator each
SLOTS = 8  # answers one judge node works on at once
UTILISATION = 0.6  # of a week, so peaks fit
WEEK_MINUTES = 7 * 24 * 60
NODE_WEEK = 65.0  # dollars a week for one TEE node: AWS m6i.2xlarge with Nitro Enclaves, on demand, $0.384 an hour
BOND_RATE = 0.05  # a year: what the bonded money would earn elsewhere
MARKET_LARGEST_BOUNTY = 1_000.0  # the largest bounty a version accepts (Article 3.7 sets the bond at twice it)
ATTACK_PRICES = (1.12, 2.84)  # v1: self-dealing pays from about $1.12; overclaim + self-funding from $2.84 (5 of 15)


def capacity() -> float:
    """Slot-minutes one judge node gives a cycle (a week)."""
    return SLOTS * UTILISATION * WEEK_MINUTES


def generic(requests: float, margin: float, **kw) -> Domain:
    """One 3-judge domain priced like a code check, for the volume x margin sweep."""
    return Domain("outside checks", "checkable", requests, margin, judge_cost=0.37 / 3, **kw)


def mix(shares: Dict[str, float], requests: float, growth: float = 0.0) -> Tuple[Domain, ...]:
    """A mix's domains at `requests` a cycle in all, split by its shares."""
    return tuple(replace(DOMAINS[k], requests=requests * sh, growth=growth) for k, sh in shares.items())


def mix_margin(shares: Dict[str, float]) -> float:
    return sum(sh * DOMAINS[k].margin for k, sh in shares.items())


def pool_tpc(r: Result) -> float:
    return tpc_spent([f for f in r.funders if f.kind in ("repo", "index")])


def outside_dollars_needed(r: Result, p: Params, price: float, cycles: Optional[Sequence[int]] = None) -> float:
    """Outside margin dollars a cycle, flat over `cycles` (default: the year) and on top of the run's own burns and
    outside requests, for the burns to absorb every token minted there at `price` (0: they already do). No (a)."""
    idx = list(range(len(r.mint))) if cycles is None else list(cycles)
    mint = sum(r.mint[i] for i in idx)
    fee = sum(min(tk, p.fee_cap * c / price) for i in idx for tk, c in r.items[i]) if p.fee_burn else 0.0
    have = sum(p.margin * (r.checks[i] + p.external_checks) + r.stakes[i] + r.outside[i] for i in idx)
    return max(0.0, (price * (mint - fee) - have) / len(idx))


def flat(dollars: float, p: Params) -> List[float]:
    return [dollars] * p.cycles


def _qs(xs: Sequence[float], fmt: str = "{:,.0f}") -> str:
    """mean (p10 – p90) over seeds."""
    return (fmt + " (" + fmt + " – " + fmt + ")").format(mean(xs), _pct(xs, .1), _pct(xs, .9))


def v2_needs(seeds: Sequence[int], base: Params, data: dict) -> Tuple[List[str], Dict[str, Dict[float, List[float]]]]:
    """Outside dollars a cycle each funder needs, for each configuration (no (a))."""
    out = ["| Adaptation | Funder | Tokens per coin spent | p* with no outside use | Value back per coin at p* | "
           "Outside margin dollars a cycle to break even | …to get +20 % | Break even, as a share of what all funders "
           "spend |", "|---|---|---|---|---|---|---|---|"]
    need: Dict[str, Dict[float, List[float]]] = {}
    data["needs"] = {}
    for cname, kw in V2_CONFIGS:
        p = replace(base, **kw)
        rs = [run(s, p) for s in seeds]
        spent = [sum(f.spent for f in r.funders if f.kind in ("repo", "index", "picker", "buyer")) / p.cycles
                 for r in rs]
        ps = [flow_price(r, p) for r in rs]
        for gname, kinds in (("pool investors (one repository's pool and the index)", ("repo", "index")),
                             ("investors picking bounties", ("picker",)), ("bounty buyers", ("buyer",))):
            g = [tpc_spent([f for f in r.funders if f.kind in kinds]) for r in rs]
            d1 = [outside_dollars_needed(r, p, 1.0 / x) for r, x in zip(rs, g)]
            d12 = [outside_dollars_needed(r, p, 1.2 / x) for r, x in zip(rs, g)]
            if kinds == ("repo", "index"):
                need[cname] = {1.0: d1, 1.2: d12}
            out.append(f"| {cname} | {gname} | {_ms(g)} | {_ms(ps, '{:.3f}')} | "
                       f"{mean(x * y for x, y in zip(g, ps)):.0%} | ${_qs(d1)} | ${_qs(d12)} | "
                       f"{mean(x / y for x, y in zip(d1, spent)):.0%} |")
            data["needs"].setdefault(cname, {})[gname] = {"tokens_per_coin": g, "p_star": ps, "break_even": d1,
                                                         "plus_20": d12, "spent_per_cycle": spent}
    return out, need


def v2_volumes(seeds: Sequence[int], base: Params, data: dict, need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    out = ["| Margin a request | " + " | ".join(f"Break even, {c}: requests a cycle (p10 – p90)" for c, _ in V2_CONFIGS)
           + " | " + " | ".join(f"+20 %, {c}" for c, _ in V2_CONFIGS) + " | p* at break even / +20 % (none) |",
           "|---|" + "---|" * (2 * len(V2_CONFIGS) + 1)]
    data["volumes"] = []
    rs = [run(s, base) for s in seeds]
    g = [pool_tpc(r) for r in rs]
    for m in V2_MARGINS:
        cells = [_qs([d / m for d in need[c][1.0]]) for c, _ in V2_CONFIGS]
        cells += [_qs([d / m for d in need[c][1.2]]) for c, _ in V2_CONFIGS]
        cells.append(f"${mean(1 / x for x in g):.2f} / ${mean(1.2 / x for x in g):.2f}")
        out.append(f"| ${m:g} | " + " | ".join(cells) + " |")
        data["volumes"].append({"margin": m, **{f"break_even_{c}": [d / m for d in need[c][1.0]] for c, _ in V2_CONFIGS},
                                **{f"plus_20_{c}": [d / m for d in need[c][1.2]] for c, _ in V2_CONFIGS}})
    grid = ["| Margin a request | " + " | ".join(f"{v:,.0f} requests a cycle" for v in V2_VOLUMES) + " |",
            "|---|" + "---|" * len(V2_VOLUMES)]
    data["grid"] = []
    for m in V2_GRID_MARGINS:
        cells = []
        for v in V2_VOLUMES:
            ps = [flow_price(r, base, outside=flat(v * m, base)) for r in rs]
            val = [x * y for x, y in zip(g, ps)]
            cells.append(f"{mean(val):.0%} (${mean(ps):.2f})")
            data["grid"].append({"margin": m, "requests": v, "p_star": ps, "value_per_coin": val})
        grid.append(f"| ${m:g} | " + " | ".join(cells) + " |")
    return out + ["", "**Value back per coin spent at p\\* (p\\* in brackets), pool investors, no adaptation:**", ""] + grid


GROWTH_PATHS = [  # (label, start as a share of break even, growth a cycle, ceiling as a share of break even)
    ("flat at break even", 1.0, 0.0, 0.0),
    ("starts at a quarter, +3 % a cycle", 0.25, 0.03, 0.0),
    ("starts at a tenth, +5 % a cycle", 0.10, 0.05, 0.0),
    ("starts at a tenth, +5 % a cycle, levels off at break even", 0.10, 0.05, 1.0),
    ("starts at 1 %, +10 % a cycle", 0.01, 0.10, 0.0),
]


def v2_growth(seeds: Sequence[int], base: Params, data: dict, need: Dict[str, Dict[float, List[float]]],
              margin: float = DOMAINS["triage"].margin) -> List[str]:
    rs = [run(s, base) for s in seeds]
    g = [pool_tpc(r) for r in rs]
    be = mean(need["none"][1.0]) / margin  # requests a cycle at break even, mean over seeds
    out = [f"Security triage at an ${margin:.2f} margin (a $9 price, $1 cost) breaks pool investors even at about "
           f"{be:,.0f} verdicts a cycle. "
           "Each path is in those terms. Each quarter's p\\* clears that quarter's minting with its own burns.\n",
           "| Path | Verdicts a cycle: cycle 1 → 52 | Value back per coin over the year (p\\*) | Q1 | Q2 | Q3 | Q4 | "
           "First quarter at break even |", "|---|---|---|---|---|---|---|---|"]
    data["growth"] = []
    quarters = [range(i * 13, min((i + 1) * 13, base.cycles)) for i in range(4)]
    for label, start, gr, ceil in GROWTH_PATHS:
        d = generic(start * be, margin, growth=gr, ceiling=ceil * be)
        dollars = [d.at(t) * margin for t in range(base.cycles)]
        ps = [flow_price(r, base, outside=dollars) for r in rs]
        year = [x * y for x, y in zip(g, ps)]
        qv = [[x * flow_price(r, base, cycles=q, outside=dollars) for r, x in zip(rs, g)] for q in quarters]
        first = next((f"Q{i + 1}" for i, v in enumerate(qv) if mean(v) >= 1.0), "never this year")
        out.append(f"| {label} | {d.at(0):,.0f} → {d.at(base.cycles - 1):,.0f} | {mean(year):.0%} "
                   f"(${mean(ps):.2f}) | " + " | ".join(f"{mean(v):.0%}" for v in qv) + f" | {first} |")
        data["growth"].append({"path": label, "requests": [d.at(t) for t in range(base.cycles)], "p_star": ps,
                               "value_per_coin": year, "quarters": qv})
    return out


def v2_mixes(seeds: Sequence[int], base: Params, data: dict, need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    dom = ["| Domain | Tier | Panel | Judges' real cost a request (paid at cost) | Margin a request (burned) | "
           "What a user pays a request | Slot-minutes a judge's answer | Largest value one request decides |",
           "|---|---|---|---|---|---|---|---|"]
    for d in DOMAINS.values():
        dom.append(f"| {d.name} | {d.tier} | {d.panel} | ${d.panel * d.judge_cost:.2f} | ${d.margin:.2f} | "
                   f"${d.price:.2f} | {d.minutes:g} | ${d.at_stake:,.0f} |")
    out = dom + ["", "| Mix (shares of requests) | Margin a request, mean | Requests a cycle to break even (none) | "
                 "…with (b) + (c) | Requests a cycle for +20 % (none) | Value back per coin at that volume, in the "
                 "simulation (break even / +20 %) | Burns by domain (" + " / ".join(DOMAINS) + ") | What users pay "
                 "a cycle at break even | …of which judges' cost |", "|---|---|---|---|---|---|---|---|---|"]
    data["mixes"] = []
    for name, shares in MIXES:
        mm = mix_margin(shares)
        reqs = {t: [d / mm for d in need["none"][t]] for t in (1.0, 1.2)}
        reqs_bc = [d / mm for d in need["(b) + (c)"][1.0]]
        check = {}
        for t in (1.0, 1.2):
            vals = []
            for s, n in zip(seeds, reqs[t]):
                p = replace(base, domains=mix(shares, n))
                r = run(s, p)
                vals.append(pool_tpc(r) * flow_price(r, p))
            check[t] = vals
        burns = " / ".join(f"{shares.get(k, 0.0) * DOMAINS[k].margin / mm:.0%}" for k in DOMAINS)
        n1 = mean(reqs[1.0])
        cost = sum(sh * DOMAINS[k].panel * DOMAINS[k].judge_cost for k, sh in shares.items())
        out.append(f"| {name} ({', '.join(f'{k} {v:.0%}' for k, v in shares.items())}) | ${mm:.3f} | "
                   f"{_qs(reqs[1.0])} | {mean(reqs_bc):,.0f} | {mean(reqs[1.2]):,.0f} | "
                   f"{mean(check[1.0]):.0%} / {mean(check[1.2]):.0%} | {burns} | ${n1 * (cost + mm):,.0f} | "
                   f"${n1 * cost:,.0f} |")
        data["mixes"].append({"mix": name, "shares": shares, "margin": mm, "break_even": reqs[1.0],
                              "break_even_bc": reqs_bc, "plus_20": reqs[1.2], "check_value": check})
    return out


def validators(domains: Sequence[Domain]) -> dict:
    """What a cycle of these domains' requests asks of the judges (v2's assumptions above)."""
    answers = sum(d.requests * d.panel for d in domains)
    minutes = sum(d.requests * d.panel * d.minutes for d in domains)
    paid = sum(d.requests * d.panel * d.judge_cost for d in domains)
    seat_answers, seat_minutes = answers / SEATS, minutes / SEATS
    nodes = max(1, math.ceil(seat_minutes / capacity()))
    bond = 2 * max([MARKET_LARGEST_BOUNTY] + [d.at_stake for d in domains if d.requests > 0])
    unpaid = nodes * NODE_WEEK + bond * BOND_RATE / 52
    return {"requests": sum(d.requests for d in domains), "answers": answers, "seat_answers": seat_answers,
            "per_minute": seat_answers / WEEK_MINUTES, "seat_minutes": seat_minutes, "nodes_per_seat": nodes,
            "seat_paid": paid / SEATS, "bond": bond, "seat_uncovered": unpaid,
            "markup_per_answer": unpaid / seat_answers if seat_answers else float("inf"),
            "markup_share": unpaid / (paid / SEATS) if paid else float("inf"),
            "v3_validators": max(SEATS, math.ceil(minutes / capacity()))}


def v2_validators(data: dict, need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    out = [f"Seven judges (Article 3), each answering every request it's drawn for. One judge node works on {SLOTS} "
           f"answers at once, {UTILISATION:.0%} of the week: {capacity():,.0f} slot-minutes a cycle. A node costs "
           f"${NODE_WEEK:.0f} a week; a bond earns {BOND_RATE:.0%} a year elsewhere.\n",
           "| Outside use | Requests a cycle | Answers a cycle, per judge (a minute) | Nodes each judge runs | "
           "Each judge's pay a cycle (its real cost, passed through) | Each judge's bond | Each judge's cost not "
           "covered a cycle (nodes + the bond's opportunity cost) | …per answer (share of its real cost) | Validators "
           "needed with v3's open registry (one node each) |", "|---|---|---|---|---|---|---|---|---|"]
    data["validators"] = []
    rows: List[Tuple[str, Tuple[Domain, ...]]] = [
        (name, tuple(replace(DOMAINS[k], requests=n) for k, n in vol.items()))
        for name, vol in MARKET_SCENARIOS]
    for name, shares in (MIXES[0], MIXES[2]):
        mm = mix_margin(shares)
        for label, t, times in (("break even", 1.0, 1.0), ("+20 %", 1.2, 1.0), ("10x break even", 1.0, 10.0)):
            rows.append((f"{name}, {label}", mix(shares, mean(need["none"][t]) / mm * times)))
    for name, doms in rows:
        v = validators(doms)
        out.append(f"| {name} | {v['requests']:,.0f} | {v['seat_answers']:,.0f} ({v['per_minute']:.2f}) | "
                   f"{v['nodes_per_seat']} | ${v['seat_paid']:,.0f} | ${v['bond']:,.0f} | ${v['seat_uncovered']:,.0f} | "
                   f"${v['markup_per_answer']:.3f} ({v['markup_share']:.0%}) | {v['v3_validators']} |")
        data["validators"].append({"use": name, **v})
    return out


def _scenario(seeds: Sequence[int], base: Params, domains: Tuple[Domain, ...]) -> dict:
    """Pool investors' value back per coin and p* with these outside domains, no adaptation and (b) + (c)."""
    res = {}
    for cname, kw in V2_CONFIGS:
        p = replace(base, domains=domains, **kw)
        ps, val = [], []
        for s in seeds:
            r = run(s, p)
            x = flow_price(r, p)
            ps.append(x)
            val.append(pool_tpc(r) * x)
        res[cname] = {"p_star": ps, "value_per_coin": val}
    return res


def _verdict(v: float) -> str:
    return "**yes**" if v >= 1.0 else "no"


def _crosses(x: float) -> str:
    hit = [f"${a:.2f}" for a in ATTACK_PRICES if x >= a]
    return "above " + " and ".join(hit) if hit else "below both"


def v2_market(seeds: Sequence[int], base: Params, data: dict) -> List[str]:
    """#196's scenarios: security triage at its volumes, prices and costs; then whole-market scenarios."""
    out = ["| Triage verdicts a cycle | Price | Our cost a verdict | Margin burned a cycle | Value back per coin, "
           "pool investors (none / (b) + (c)) | Break even? | p\\* (none) | v1's attack prices ($1.12 self-dealing, "
           "$2.84 overclaim + self-funding) |", "|---|---|---|---|---|---|---|---|"]
    data["market"] = {"triage": [], "scenarios": []}
    for n in TRIAGE_VOLUMES:
        for price in TRIAGE_PRICES:
            for cost in TRIAGE_COSTS:
                d = priced(DOMAINS["triage"].name, "checkable", price, cost, requests=n, minutes=20.0,
                           at_stake=10_000.0)
                res = _scenario(seeds, base, (d,))
                v0, vb = mean(res["none"]["value_per_coin"]), mean(res["(b) + (c)"]["value_per_coin"])
                x = mean(res["none"]["p_star"])
                out.append(f"| {n:,.0f} | ${price:.0f} | ${cost:.2f} | ${n * d.margin:,.0f} | {v0:.0%} / {vb:.0%} | "
                           f"{_verdict(v0)} / {_verdict(vb)} | ${x:.2f} | {_crosses(x)} |")
                data["market"]["triage"].append({"verdicts": n, "price": price, "cost": cost,
                                                 "margin_per_cycle": n * d.margin, **res})
    out += ["", "| Scenario (requests a cycle) | Margin burned a cycle | Of it, from triage | What buyers pay a cycle | "
            "Value back per coin, pool investors (none / (b) + (c)) | Break even? | p\\* (none) | v1's attack prices |",
            "|---|---|---|---|---|---|---|---|"]
    for name, vol in MARKET_SCENARIOS:
        doms = tuple(replace(DOMAINS[k], requests=n) for k, n in vol.items())
        res = _scenario(seeds, base, doms)
        burn = sum(d.requests * d.margin for d in doms)
        tri = sum(d.requests * d.margin for d in doms if d.name == DOMAINS["triage"].name)
        pay = sum(d.requests * d.price for d in doms)
        v0, vb = mean(res["none"]["value_per_coin"]), mean(res["(b) + (c)"]["value_per_coin"])
        x = mean(res["none"]["p_star"])
        out.append(f"| {name}: " + ", ".join(f"{k} {n:,.0f}" for k, n in vol.items()) + f" | ${burn:,.0f} | "
                   f"{tri / burn:.0%} | ${pay:,.0f} | {v0:.0%} / {vb:.0%} | {_verdict(v0)} / {_verdict(vb)} | "
                   f"${x:.2f} | {_crosses(x)} |")
        data["market"]["scenarios"].append({"scenario": name, "requests": vol, "margin_per_cycle": burn,
                                            "buyers_pay": pay, **res})
    return out


def invested_gain(base_r: Result, att: Result, p: Params, pt: Params, price: float) -> float:
    """The attack's gain over the better of v1's twin (which funds nothing) and a twin that also puts the attack's
    own coin in honest pools, at their tokens per coin spent. Once funding pays, v1's twin makes any play that funds
    look like a gain; this one asks whether cheating beats the honest use of the same coin."""
    naive = attack_profit(att, p, price) - attack_profit(base_r, pt, price)
    return naive - max(0.0, att.a_own * (pool_tpc(att) * price - 1))


V2_PRICE_GRID = [10 ** (k / 40) for k in range(-160, 81)]  # $0.0001 to $100, as v1's pays_from


def pays_over_investing(base_r: Result, att: Result, p: Params, pt: Params) -> float:
    """The lowest price, up to $100, at which the attack beats honest investing (inf: never; 0: at every price)."""
    for k, x in enumerate(V2_PRICE_GRID):
        if invested_gain(base_r, att, p, pt, x) > 0:
            return 0.0 if k == 0 else x
    return float("inf")


V2_ATTACKS = [  # (label, attack, plays as (claim, own coin), colluders, other changes): v1's plays
    ("self-dealing: a $5 fix claimed at its worth, funded from a second wallet", "overclaim",
     [(5.0, x) for x in (1.0, 5.0, 50.0)], (0, 5), {}),
    ("overclaimed merit, funded from a second wallet", "overclaim",
     [(c, x) for c in (15.0, 50.0, 200.0) for x in (5.0, 50.0, 200.0)], (0, 3, 5), {}),
    ("1-cent pledges on every fix of 2 unfunded repositories, per-fix cap on, the cut to uncapped fixes (#186 D3)",
     "cent", [(0.0, 0.0)], (0,), {"unfunded": 2, "redistribute": True}),
]
V2_GAIN_PRICES = (1.41, 2.84, 10.0)


def v2_farming(seeds: Sequence[int], base: Params, data: dict, need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    """Each attack's best play per seed: the lowest price at which it beats v1's twin, and the most it gains over a
    twin that invests the same coin honestly."""
    out = ["| Attack | Colluding judges (of 15) | Pays over v1's twin from (any play) | Pool investors' value back per "
           "coin there | Security triage verdicts a cycle that push p\\* there (an $8 margin) | Gain a "
           "year over the honest use of the same coin (best play), at $1.41 (+20 %) | at $2.84 | at $10 | "
           "Beats the honest use of its coin from |", "|---|---|---|---|---|---|---|---|---|"]
    data["farming"] = []
    for label, kind, plays, colluders, kw in V2_ATTACKS:
        for c in colluders:
            twin_p = replace(base, attack=kind if kind != "cent" else "", colluders=c, claim=base.true_fake,
                             own_coin=0.0, **kw)
            twins = {s: run(s, twin_p) for s in seeds}
            pays = [float("inf")] * len(seeds)
            over = [float("inf")] * len(seeds)
            vals = [float("nan")] * len(seeds)
            vols = [float("nan")] * len(seeds)
            gains = {y: [-float("inf")] * len(seeds) for y in V2_GAIN_PRICES}
            for claim, own in plays:
                q = replace(twin_p, attack=kind, claim=claim, own_coin=own) if kind != "cent" else \
                    replace(twin_p, attack="cent")
                for i, s in enumerate(seeds):
                    a, b = run(s, q), twins[s]
                    x = pays_from(b, a, q, twin_p)
                    if x < pays[i]:
                        pays[i] = x
                        vals[i] = pool_tpc(a) * x
                        vols[i] = outside_dollars_needed(a, q, x)
                    over[i] = min(over[i], pays_over_investing(b, a, q, twin_p))
                    for y in V2_GAIN_PRICES:
                        gains[y][i] = max(gains[y][i], invested_gain(b, a, q, twin_p, y))
            fin = [x for x in pays if math.isfinite(x)]
            where = (f"${mean(fin):.2f}" + (f" ({len(pays) - len(fin)} of {len(pays)} seeds never)"
                                             if len(fin) < len(pays) else "")) if fin else "**never** (to $100)"
            v = [x for x in vals if math.isfinite(x)]
            d = [x for x in vols if math.isfinite(x)]
            vol = f"{mean(d) / DOMAINS['triage'].margin:,.0f}" if d else "–"
            ofin = [x for x in over if math.isfinite(x)]
            if ofin and max(ofin) == 0.0 and len(ofin) == len(over):
                ow = "every price (see the gains)"
            elif ofin:
                ow = f"${mean(ofin):.2f}" + (f" ({len(over) - len(ofin)} of {len(over)} seeds never)"
                                             if len(ofin) < len(over) else "")
            else:
                ow = "**never** (to $100)"
            out.append(f"| {label} | {c if kind != 'cent' else '–'} | {where} | "
                       f"{(f'{mean(v):.0%}' if v else '–')} | {vol} | "
                       + " | ".join(_ms(gains[y], "{:,.0f}") for y in V2_GAIN_PRICES) + f" | {ow} |")
            data["farming"].append({"attack": label, "colluders": c, "pays_from": pays, "value_then": vals,
                                    "outside_dollars_then": vols,
                                    "gain_over_invested": {str(y): g for y, g in gains.items()},
                                    "beats_investing_from": over})
    return out


def v2_sensitivity(seeds: Sequence[int], base: Params, data: dict,
                   need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    rs0 = {s: run(s, base) for s in seeds}
    danger = [outside_dollars_needed(rs0[s], base, ATTACK_PRICES[1]) for s in seeds]
    levels = [("none", [0.0] * len(seeds)), ("break even", need["none"][1.0]), ("+20 %", need["none"][1.2]),
              ("p* at $2.84", danger)]
    out = ["Outside margin dollars a cycle are set from the no-adaptation run of each seed: 0, its break even, its +20 % "
           "and where its p\\* reaches $2.84 (v1's price at which overclaim plus self-funding starts to beat its "
           f"honest twin with 5 of 15 judges colluding); on average ${mean(need['none'][1.0]):,.0f}, "
           f"${mean(need['none'][1.2]):,.0f} and ${mean(danger):,.0f}.\n",
           "| Adaptation | Outside use | p\\* ($) | Pool investors' tokens per coin | Value back per coin at p\\* | "
           "Merit left unpaid | Coin waiting at the year's end | Fixes a cycle, healthy repo (last quarter) | "
           "Mint ÷ burn at $1.00 | Tokens the per-fix cap cut |", "|---|---|---|---|---|---|---|---|---|---|"]
    data["sensitivity"] = []
    for cname, kw in V2_CONFIGS + V2_A_CONFIGS:
        p0 = replace(base, **kw)
        for lname, ds in levels:
            ps, tp, unpaid, waiting, nh, ratio, cut = [], [], [], [], [], [], []
            for s, d in zip(seeds, ds):
                p = replace(p0, domains=(generic(d, 1.0),)) if d > 0 else p0
                if p.adapt_cap:
                    x, r = flow_price_rerun(s, p, steps=20)
                    r1 = run(s, replace(p, price=1.0))
                    ratio.append(sum(r1.mint) / sum(r1.burned))
                else:
                    r = run(s, p)
                    x = flow_price(r, p)
                    ratio.append(sum(r.mint) / burned_at(r, p, 1.0))
                ps.append(x)
                tp.append(pool_tpc(r))
                unpaid.append(r.underpaid / (r.merit["healthy"] + r.merit["stalling"]))
                put = sum(f.contributed for f in r.funders if f.kind in ("repo", "index"))
                waiting.append(r.waiting_end / put)
                nh.append(mean(r.fixes["healthy"][-13 * p.healthy:]))
                cut.append(max(0.0, sum(r.cut)) / (sum(r.cut) + sum(r.mint)))
            val = [x * y for x, y in zip(ps, tp)]
            out.append(f"| {cname} | {lname} | {_ms(ps, '{:.3f}')} | {_ms(tp)} | {mean(val):.0%} | "
                       f"{mean(unpaid):.1%} | {mean(waiting):.1%} | {mean(nh):.1f} | {_ms(ratio)} | {mean(cut):.1%} |")
            data["sensitivity"].append({"adaptation": cname, "outside": lname, "dollars": list(ds), "p_star": ps,
                                        "tokens_per_coin": tp, "value_per_coin": val, "unpaid": unpaid,
                                        "waiting_end": waiting, "fixes_healthy": nh, "mint_over_burn_at_1": ratio,
                                        "cut_share": cut})
    return out


REBATES = (1.2, 1.5)
REBATE_LEVELS = (0.5, 1.0, 2.0, 5.0, 10.0)  # outside margin dollars, as multiples of break even


def v2_rebate(seeds: Sequence[int], base: Params, data: dict, need: Dict[str, Dict[float, List[float]]]) -> List[str]:
    be = need["none"][1.0]
    out = ["| Rebate ceiling | Adaptation | " + " | ".join(f"Outside margins at {x:g}x break even" for x in REBATE_LEVELS)
           + " |", "|---|---|" + "---|" * len(REBATE_LEVELS)]
    data["rebate"] = []
    for rmax in (0.0,) + REBATES:
        for cname, kw in V2_CONFIGS:
            cells = []
            for lv in REBATE_LEVELS:
                ps, val, waived = [], [], []
                for s, d in zip(seeds, be):
                    p = replace(base, rebate_max=rmax, domains=(generic(lv * d, 1.0),), **kw)
                    r = run(s, p)
                    x = flow_price(r, p)
                    ps.append(x)
                    val.append(pool_tpc(r) * x)
                    waived.append(sum(r.outside_waived) / (sum(r.outside_waived) + sum(r.outside)))
                cells.append(f"{mean(val):.0%} (${mean(ps):.2f}" + (f"; {mean(waived):.0%} waived)" if rmax else ")"))
                data["rebate"].append({"rebate_max": rmax, "adaptation": cname, "level": lv, "p_star": ps,
                                       "value_per_coin": val, "waived": waived})
            out.append(f"| {('off' if not rmax else f'{rmax:g}x the coin')} | {cname} | " + " | ".join(cells) + " |")
    return out


def report_v2(seeds: Sequence[int], base: Params = Params()) -> Tuple[str, dict]:
    data: dict = {"seeds": list(seeds), "params": _params_v1(base),
                  "domains": {k: d.__dict__.copy() for k, d in DOMAINS.items()},
                  "validator_assumptions": {
                      "seats": SEATS, "slots": SLOTS, "utilisation": UTILISATION, "node_week": NODE_WEEK,
                      "bond_rate": BOND_RATE, "market_largest_bounty": MARKET_LARGEST_BOUNTY}}
    data["mix_shares"] = dict(MIXES)
    rs = [run(s, base) for s in seeds]
    v1_ps = [flow_price(r, base) for r in rs]
    out = ["### 0. With no outside use, v1's numbers\n",
           f"p\\* = ${mean(v1_ps):.3f} ± {pstev(v1_ps):.3f} and pool investors get back "
           f"{mean(pool_tpc(r) * x for r, x in zip(rs, v1_ps)):.0%} per coin spent (v1: $0.273 ± 0.003, 23 %).", ""]
    data["v1_p_star"] = v1_ps
    lines, need = v2_needs(seeds, base, data)
    out += ["### 1. What outside use must burn\n"] + lines
    out += ["", "### 2. Outside volume x margin (one 3-judge domain; the bounty market's own checks stay at "
            f"${base.margin:g})\n"] + v2_volumes(seeds, base, data, need)
    out += ["", "### 3. The market study's scenarios (#196): verdicts x (price - cost)\n"] + v2_market(seeds, base, data)
    out += ["", "### 3b. Growth paths\n"] + v2_growth(seeds, base, data, need)
    out += ["", "### 4. Domain mixes\n"] + v2_mixes(seeds, base, data, need)
    out += ["", "### 5. Validators\n"] + v2_validators(data, need)
    out += ["", "### 6. v1's conclusions with outside use\n"] + v2_sensitivity(seeds, base, data, need)
    out += ["", "### 7. Farming when funding pays\n"] + v2_farming(seeds, base, data, need)
    out += ["", "### 8. The rebate ceiling (proposed): value back per coin at p\\* (p\\*; share of outside margins "
            "not charged)\n"] + v2_rebate(seeds, base, data, need)
    return "\n".join(out), data


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.fundertoken")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--json", action="store_true",
                    help="print every number as JSON (the markdown tables under \"markdown\") instead of the tables")
    ap.add_argument("--v2", action="store_true", help="v2 (#195): outside revenue from check domains")
    a = ap.parse_args(argv)
    md, data = (report_v2 if a.v2 else report)(range(1, a.seeds + 1))
    if a.json:
        data["markdown"] = md
        print(json.dumps(data, indent=1, default=float))
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
