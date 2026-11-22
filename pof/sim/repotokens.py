"""Per-repository tokens and the self-farmer (proof-of-fix#177; simulation only, rule 1).

The owner (2026-11-07): can each repository have its own token, minted by #58's rule scoped to it? The risk is a
farmer who registers a repository, files real trivial issues, funds them itself, fixes them properly and mints its
own token: every judge rightly passes the fixes, and the bounty coin only goes round in a circle. This model asks
what the farmer's tokens must sell for before farming pays (its break-even price), under each candidate minting rule,
and what each rule costs honest projects.

What it is: a year of weekly paid bounties on `honest` repositories, funded by a population of honest funders with
earned reputation (#37), beside one farmer's repository. The farmer picks, per rule, the strategy that minimises its
cost per token (fixes a week, coin per bounty, sock funders and whether it buys their reputation), so the break-even
price is the attack's best case. Its costs are the race's own fees (pof.params: the AI registration check, the
attempt fee, the market fee on the winner's price) and the checks (k judges at the market's service fee plus usage,
pof.sim.openval). Its development cost is taken as zero: a trivial fix written by a model.

What it isn't: a prediction of any token's price (an input here), or of whether anyone would buy a farmed token.
The full market simulation (#58's scenarios) is the next step if a rule holds up.

The rules (`Rule.kind`):
- R0 "fixed": each repository mints a fixed weekly emission, split among its paid bounties by AI weight (#58 D3).
- R1 "coin": a bounty mints KAPPA tokens per dollar of the smaller of its AI weight and the coin pledged by
  accounts other than its solver.
- R2 "reputation": R1 with each funder's coin weighted by its reputation in [0, 1], earned only by funding paid
  bounties on repositories it doesn't control (REP_FULL dollars for full reputation).
- R3 "burn": minting a token burns BURN_FLOOR dollars of coin (paid by the bounty's funders), on top of R1.
- R4 "maturity": R2, switched on only once the repository has had ACTIVATE distinct funders with reputation >= 0.5.
- R5 "cap": any rule, with a repository's mint each week capped at CAP tokens (a share of the protocol token's).
Rules combine: `Rule(kind, burn=..., activate=..., cap=...)`.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

WEEKS = 52
EMISSION = 10_000.0  # #58: the protocol token's weekly emission (pof.params.TOKENS)
DECAY = 0.01  # #58: less 1 % a week


@dataclass(frozen=True)
class Costs:
    """What one fix costs whoever posts and solves it, in dollars (pof.params defaults; the openval market's fee)."""
    registration: float = 2.0  # the AI registration check, paid by the poster (pof.params.registration_fee)
    attempt: float = 0.5  # pof.params.attempt_fee
    judges: int = 3  # k at a grown network
    service: float = 0.21  # the market's service fee per check (reports/open-validators-v3.1.md)
    usage: float = 0.13  # one judge's metered usage (pof.sim.openval World.usage_per_check)
    market_fee: float = 0.20  # of the winner's price, from the bounty (pof.params.market_fee_bps); 0 in the contract

    def per_fix(self, coin: float) -> float:
        return self.registration + self.attempt + self.judges * (self.service + self.usage) + self.market_fee * coin


CONTRACT_COSTS = replace(Costs(), market_fee=0.0)  # pof.params.CONTRACT: no market fee


@dataclass(frozen=True)
class Rule:
    kind: str  # "fixed", "coin", "reputation"
    label: str = ""
    burn: float = 0.0  # R3: dollars burned per token minted
    activate: int = 0  # R4: distinct funders with reputation >= 0.5 before the token turns on
    cap: Optional[float] = None  # R5: tokens a repository may mint a week
    repo_emission: float = 1_000.0  # R0's weekly emission per repository
    kappa: float = 10.0  # R1-R4: tokens per dollar of counted weight


@dataclass(frozen=True)
class World:
    honest: int = 20  # honest repositories
    bounties_week: float = 1.0  # paid bounties a week per honest repository (Poisson, its own rate around this)
    bounty_median: float = 86.0  # the market's paid bounties (reports/self-healing-v1.md)
    bounty_p90: float = 184.0
    weight_error: float = 0.3  # #58 D3: each AI estimate is value x exp(N(0, 0.3)); the smaller of two counts
    funders: int = 300  # the honest funders' population
    funders_per_bounty: float = 2.0  # 1 + Poisson(1) by default
    rep_full: float = 500.0  # dollars funded on others' paid bounties for full reputation (#37)
    trivial_value: float = 5.0  # what a farmer's trivial issue is worth: its AI weight's centre
    # a manufactured serious-looking bug: the merit judges value it at `manufactured` unless they see through it
    # (with probability `detect`: they recognise it has no reach), when it's judged at `trivial_value`; 0: off
    manufactured: float = 0.0
    detect: float = 0.0
    report_cost: float = 2.0  # a bug report's AI registration check, paid by the reporter (pof.params)


@dataclass
class Strategy:
    fixes: int  # trivial fixes a week
    coin: float  # coin pledged per bounty (it comes back to the farmer as the solver, less the market fee)
    socks: int  # sock funder accounts (0: it funds as itself, the solver)
    rep: bool  # whether it buys the socks' reputation by funding other repositories' paid bounties


@dataclass
class Result:
    rule: str
    farmer_tokens: float  # a year
    farmer_cost: float  # a year
    break_even: float  # dollars a token the farmer must sell at to profit (inf: it can't mint)
    strategy: Optional[Strategy]
    honest_tokens_per_dollar: float  # tokens per dollar of outside funding, honest repositories
    honest_active_share: float  # honest repositories whose token is on by the year's end
    honest_weeks_to_activate: float  # mean weeks before an honest repository's token turns on (R4)
    honest_burn_share: float  # of honest funding, the share burned (R3)


def _lognormal(rng: random.Random, w: World) -> float:
    mu = math.log(w.bounty_median)
    sigma = (math.log(w.bounty_p90) - mu) / 1.2816
    return rng.lognormvariate(mu, sigma)


def _weight(rng: random.Random, value: float, w: World) -> float:
    """#58 D3: the smaller of two independent AI estimates."""
    return min(value * math.exp(rng.gauss(0, w.weight_error)), value * math.exp(rng.gauss(0, w.weight_error)))


def _farmer_weight(rng: random.Random, w: World) -> float:
    """The judged value of one of the farmer's fixes: manufactured importance unless the judges see through it."""
    seen_through = not w.manufactured or rng.random() < w.detect
    return _weight(rng, w.trivial_value if seen_through else w.manufactured, w)


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    n, p, limit = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= limit:
            return n
        n += 1


class Sim:
    """One seed: the honest repositories' year, then the farmer's best response under `rule`."""

    def __init__(self, seed: int, rule: Rule, w: World = World(), costs: Costs = Costs()):
        self.seed, self.rule, self.w, self.costs = seed, rule, w, costs
        self.rng = random.Random(seed * 1_000_003 + 177)
        self.rep_dollars = [self.rng.uniform(0.0, 2.0) * w.rep_full for _ in range(w.funders)]  # history so far

    def rep(self, f: int) -> float:
        return min(1.0, self.rep_dollars[f] / self.w.rep_full)

    # ----- honest repositories -----

    def honest_year(self) -> Tuple[float, float, float, float, float]:
        """Tokens per dollar of outside funding, active share, weeks to activate, burn share, and the honest weekly
        weight on the protocol pool (for the single-token comparison)."""
        w, r, rng = self.w, self.rule, self.rng
        rates = [w.bounties_week * rng.lognormvariate(-0.5 * 0.5 ** 2, 0.5) for _ in range(w.honest)]
        tokens = funding = burned = 0.0
        activated_at: List[Optional[int]] = [None] * w.honest
        seen: List[set] = [set() for _ in range(w.honest)]
        pool_weight = 0.0
        for week in range(WEEKS):
            for i, lam in enumerate(rates):
                rows = []
                for _ in range(_poisson(rng, lam)):
                    value = _lognormal(rng, w)
                    n = 1 + _poisson(rng, w.funders_per_bounty - 1)
                    fs = rng.sample(range(w.funders), n)
                    coin = [value / n] * n
                    weight = _weight(rng, value, w)
                    rows.append((value, weight, fs, coin))
                    pool_weight += weight
                for value, weight, fs, coin in rows:
                    funding += value
                    for f in fs:
                        if self.rep(f) >= 0.5:
                            seen[i].add(f)
                if activated_at[i] is None and len(seen[i]) >= r.activate:
                    activated_at[i] = week
                mint = self._mint(rows, week, active=activated_at[i] is not None)
                tokens += mint
                burned += mint * r.burn
                for value, weight, fs, coin in rows:  # funding paid bounties builds reputation
                    for f, c in zip(fs, coin):
                        self.rep_dollars[f] += c
        weeks = [a for a in activated_at if a is not None]
        return (tokens / funding if funding else 0.0, len(weeks) / w.honest,
                mean(weeks) if weeks else float("nan"), burned / funding if funding else 0.0, pool_weight / WEEKS)

    def _counted(self, weight: float, fs: Sequence[int], coin: Sequence[float], solver: Optional[int]) -> float:
        """R1/R2's counted dollars of one bounty: the smaller of its weight and its outside coin (by reputation)."""
        outside = 0.0
        for f, c in zip(fs, coin):
            if f == solver:
                continue
            outside += c * (self.rep(f) if self.rule.kind == "reputation" else 1.0)
        return min(weight, outside)

    def _mint(self, rows, week: int, active: bool, solver: Optional[int] = None,
              rep_of=None) -> float:
        r = self.rule
        if not active or not rows:
            return 0.0
        if r.kind == "fixed":
            total = r.repo_emission * (1 - DECAY) ** week
        else:
            total = 0.0
            for value, weight, fs, coin in rows:
                if rep_of is not None:
                    outside = sum(c * (rep_of(f) if r.kind == "reputation" else 1.0)
                                  for f, c in zip(fs, coin) if f != solver)
                    total += r.kappa * min(weight, outside)
                else:
                    total += r.kappa * self._counted(weight, fs, coin, solver)
        if r.cap is not None:
            total = min(total, r.cap * (1 - DECAY) ** week)
        return total

    # ----- the farmer -----

    def farmer(self, s: Strategy) -> Tuple[float, float]:
        """Its tokens and its cost over the year with strategy `s` (its own repository; its sock accounts fund)."""
        w, r, rng, c = self.w, self.rule, random.Random(self.seed * 7 + 1), self.costs
        tokens = cost = 0.0
        sock_rep = [0.0] * max(1, s.socks)
        if s.rep and s.socks:
            # it funds other repositories' paid bounties to give each sock full reputation: real money to real
            # solvers, lost to the farmer (it gets none of it back)
            cost += s.socks * w.rep_full
            sock_rep = [1.0] * s.socks
        funders = list(range(-s.socks, 0)) if s.socks else [-1]  # negative ids: the farmer's own accounts
        solver = -1 if not s.socks else None  # with no socks it funds as the solver itself
        rep_of = (lambda f: sock_rep[-f - 1]) if s.socks else (lambda f: 0.0)
        reputable = sum(1 for x in sock_rep if x >= 0.5) if s.socks else 0
        active = reputable >= r.activate
        for week in range(WEEKS):
            rows = []
            for _ in range(s.fixes):
                weight = _farmer_weight(rng, w)
                coin = [s.coin / len(funders)] * len(funders)
                rows.append((s.coin, weight, funders, coin))
                cost += c.per_fix(s.coin)
            mint = self._mint(rows, week, active, solver=solver if solver is not None else 0, rep_of=rep_of)
            tokens += mint
            cost += mint * r.burn
        return tokens, cost


STRATEGIES = [Strategy(f, coin, socks, rep)
              for f in (1, 2, 5, 10, 20, 50)
              for coin in (5.0, 50.0, 500.0)
              for socks, rep in ((0, False), (3, False), (3, True), (10, False), (10, True))]


def run(seed: int, rule: Rule, w: World = World(), costs: Costs = Costs()) -> Result:
    sim = Sim(seed, rule, w, costs)
    tpd, active, weeks, burn, _ = sim.honest_year()
    best: Tuple[float, Optional[Strategy], float, float] = (float("inf"), None, 0.0, 0.0)
    for s in STRATEGIES:
        tokens, cost = Sim(seed, rule, w, costs).farmer(s)
        if tokens > 0 and cost / tokens < best[0]:
            best = (cost / tokens, s, tokens, cost)
    return Result(rule.label or rule.kind, best[2], best[3], best[0], best[1], tpd, active, weeks, burn)


def single_token(seed: int, w: World = World(), costs: Costs = Costs()) -> Tuple[float, float]:
    """The comparison: the protocol's one token (#58), where a farmer's trivial fixes share the week's emission with
    every honest paid bounty by weight. Its best break-even price over fixes a week, and its tokens a year then."""
    sim = Sim(seed, Rule("fixed"), w, costs)
    *_, pool = sim.honest_year()  # honest weight a week on the protocol's pool (the honest repositories')
    honest_tpd = EMISSION * sum((1 - DECAY) ** k for k in range(WEEKS)) / (pool * WEEKS)  # tokens per weight-dollar
    rng = random.Random(seed * 11 + 3)
    best = (float("inf"), 0.0)
    for f in (1, 2, 5, 10, 20, 50, 100):
        tokens = cost = 0.0
        for week in range(WEEKS):
            mine = sum(_farmer_weight(rng, w) for _ in range(f))
            tokens += EMISSION * (1 - DECAY) ** week * mine / (pool + mine)
            cost += f * costs.per_fix(w.trivial_value)
        if cost / tokens < best[0]:
            best = (cost / tokens, tokens)
    return best[0], best[1], honest_tpd


RULES: List[Rule] = [
    Rule("fixed", "R0: a fixed 1,000 tokens a week per repository"),
    Rule("coin", "R1: 10 tokens per counted dollar (outside coin, up to the AI weight)"),
    Rule("reputation", "R2: R1, outside coin weighted by reputation"),
    Rule("coin", "R3: R1, burning $0.05 per token", burn=0.05),
    Rule("reputation", "R4: R2, on after 5 reputable funders", activate=5),
    Rule("fixed", "R5: R0, capped at 100 tokens a week", cap=100.0),
    Rule("reputation", "R2 + R3 + R4 + R5", burn=0.05, activate=5, cap=100.0),
]


# ---------- per cycle: one protocol-wide pool, split by judges comparing the cycle's fixes (owner, 2026-11-07) ----------

@dataclass(frozen=True)
class Cycle:
    """Each week the protocol's emission (#58) is split across every repository's paid fixes of that week, in
    proportion to the value the judges give each fix when comparing them, times the evidence its repository is used.
    Judges are paid flat for the work (their competition is on quality, pof.sim.openval), never a share of the pool.
    - `need`: distinct funders with reputation >= 0.5 (earned on others' paid bounties, #37) a repository needs in the
      last `window` cycles for full usage evidence; fewer scale it down linearly.
    - `noise`: the judges' comparison error (multiplicative, log-normal): smaller than pricing one fix alone."""
    need: int = 5
    window: int = 4
    noise: float = 0.15
    # reputation counts as evidence only if earned in the last `renew_weeks` (0: once earned, forever), so a farmer
    # pays for its socks' reputation again every period instead of once
    renew_weeks: int = 0
    # merit vests over `vest_weeks` (0: paid at once): each week releases its part times the repository's reach that
    # week (its usage evidence), and what isn't released is never minted. The farmer keeps its reach up by having each
    # sock file a valid bug report every `window` weeks (report_cost each: reports are AI-checked like any issue)
    vest_weeks: int = 0
    # the hybrid (owner, 2026-11-07): a fix's merit in the split is capped by the bounty coin pledged by accounts other
    # than its solver, so manufactured importance needs real coin behind it, and the market fee on that coin is lost
    cap_coin: bool = False
    # a payout fee indexed to the pot (owner, 2026-11-08, #182): each cycle's fee per dollar of bounty coin is `pot_fee`
    # times the token value one dollar of bounty coin earns that cycle (the cycle's emission over the coin paid out in
    # it, at the token's price). It scales with the price, so the break-even is where tokens net of the fee pay the
    # farmer's other costs; with pot_fee > 0, pass costs with no flat market fee
    pot_fee: float = 0.0
    # with pot_cap > 0, the pot fee never exceeds pot_cap of the coin: it follows the token's value while tokens are worth
    # little, and is a flat fee from the price where β times their value reaches the cap
    pot_cap: float = 0.0
    label: str = ""


def cycle_run(seed: int, c: Cycle, w: World = World(), costs: Costs = Costs()) -> tuple:
    """The farmer's best break-even price, honest tokens per dollar funded, the share of the pool honest work keeps
    against the farmer's best strategy, that strategy, the honest repositories' mean usage evidence, and the pot fee
    honest funders pay per dollar, in tokens (0 without `c.pot_fee`). The farmer's own repository's evidence is its
    sock funders: with bought reputation each costs `w.rep_full` once (real fixes elsewhere), without it they count
    for nothing."""
    sim = Sim(seed, Rule("reputation"), w, costs)
    rng = sim.rng
    rates = [w.bounties_week * rng.lognormvariate(-0.5 * 0.5 ** 2, 0.5) for _ in range(w.honest)]
    recent: List[List[Tuple[int, int]]] = [[] for _ in range(w.honest)]  # (week, reputable funder)
    honest_v: List[float] = []
    paid = [0.0] * WEEKS  # honest bounty coin paid out each week: the pot fee's denominator
    funding = 0.0
    # with renewal, a funder's reputation counts only what it funded in the last `renew_weeks` (its history before
    # the year counts as funded at week 0)
    history: List[List[Tuple[int, float]]] = [[(0, sim.rep_dollars[f])] for f in range(w.funders)]

    def reputable(f: int, week: int) -> bool:
        if not c.renew_weeks:
            return sim.rep(f) >= 0.5
        history[f] = [(k, x) for k, x in history[f] if k > week - c.renew_weeks]
        return sum(x for _, x in history[f]) >= 0.5 * w.rep_full

    usage_seen: List[float] = []
    reach = [[0.0] * WEEKS for _ in range(w.honest)]  # each honest repository's usage evidence, week by week
    owed: List[List[Tuple[int, int, float]]] = [[] for _ in range(WEEKS)]  # per week: (repo, week found, value)
    for week in range(WEEKS):
        rows = []
        for i, lam in enumerate(rates):
            for _ in range(_poisson(rng, lam)):
                value = _lognormal(rng, w)
                n = 1 + _poisson(rng, w.funders_per_bounty - 1)
                fs = rng.sample(range(w.funders), n)
                funding += value
                paid[week] += value
                recent[i] += [(week, f) for f in fs if reputable(f, week)]
                weight = _weight(rng, value, w)
                rows.append((i, min(weight, value) if c.cap_coin else weight, fs, value / n))
        total = 0.0
        for i in range(w.honest):
            recent[i] = [(wk, f) for wk, f in recent[i] if wk > week - c.window]
            reach[i][week] = min(1.0, len({f for _, f in recent[i]}) / c.need)
        for i, weight, fs, part in rows:
            usage = reach[i][week]
            usage_seen.append(usage)
            v = weight * usage * math.exp(rng.gauss(0, c.noise))
            total += v
            owed[week].append((i, week, v))
            for f in fs:
                sim.rep_dollars[f] += part
                history[f].append((week, part))
        honest_v.append(total)
    pool = [EMISSION * (1 - DECAY) ** k for k in range(WEEKS)]

    def released(series: Sequence[float], week: int) -> float:
        """The share of an allocation made in `week` that vests: the mean reach over the next vest_weeks (a series
        that ends with the year repeats its last value)."""
        if not c.vest_weeks:
            return 1.0
        return mean(series[min(k, WEEKS - 1)] for k in range(week + 1, week + 1 + c.vest_weeks))

    honest_tokens = 0.0
    for k in range(WEEKS):
        if honest_v[k] <= 0:
            continue
        for i, _, v in owed[k]:
            honest_tokens += pool[k] * v / honest_v[k] * released(reach[i], k)
    honest_tpd = honest_tokens / funding
    honest_fee = c.pot_fee * sum(pool[k] for k in range(WEEKS) if paid[k] > 0) / funding  # tokens per honest dollar
    best = (float("inf"), None, 1.0)
    frng = random.Random(seed * 13 + 5)
    coins = HYBRID_COINS if c.cap_coin else (5.0,)
    for fixes, socks, coin in [(f, s, x) for f in (1, 2, 5, 10, 20, 50, 100)
                               for s in sorted({0, max(1, c.need // 2), c.need, 2 * c.need}) for x in coins]:
        usage = min(1.0, socks / c.need)
        if usage == 0:
            continue
        tokens, cost, kept, fee = 0.0, 0.0, 0.0, 0.0
        weekly = []  # (the pot fee in tokens, its cap in dollars), week by week
        mine_reach = [usage] * WEEKS
        for k in range(WEEKS):
            if k == 0 or (c.renew_weeks and k % c.renew_weeks == 0):
                cost += socks * 0.5 * w.rep_full  # what a sock needs to count as reputable
            if c.vest_weeks and k % c.window == 0:
                cost += socks * w.report_cost  # each sock's valid bug report keeps its reach up
            # its socks pledge `coin` (outside coin: they aren't the solver); it comes back less the market fee
            mine = sum((min(_farmer_weight(frng, w), coin) if c.cap_coin else _farmer_weight(frng, w))
                       * usage * math.exp(frng.gauss(0, c.noise)) for _ in range(fixes))
            tokens += pool[k] * mine / (honest_v[k] + mine) * released(mine_reach, k)
            kept += honest_v[k] / (honest_v[k] + mine) if honest_v[k] + mine else 1.0
            cost += fixes * costs.per_fix(coin)
            if c.pot_fee:  # in tokens: the price multiplies both sides
                f = c.pot_fee * pool[k] * fixes * coin / (paid[k] + fixes * coin)
                fee += f
                weekly.append((f, c.pot_cap * fixes * coin))
        net = tokens - fee
        if c.pot_cap:
            be = _capped_break_even(tokens, cost, weekly)
        else:
            be = cost / net if net > 0 else float("inf")  # inf: no price makes it pay
        if be < best[0] or best[1] is None:
            best = (be, Strategy(fixes, coin, socks, True), kept / WEEKS)
    return best[0], honest_tpd, best[2], best[1], mean(usage_seen) if usage_seen else 0.0, honest_fee


HYBRID_COINS = (5.0, 20.0, 50.0, 100.0, 200.0, 500.0)  # the farmer's choice of coin per bounty under the hybrid

def _capped_break_even(tokens: float, cost: float, weekly: Sequence[Tuple[float, float]]) -> float:
    """The lowest token price at which farming pays when each week's fee is the smaller of its pot fee (tokens, times
    the price) and its cap (dollars). Profit rises with the price whenever any price can make it pay, so bisect."""
    def profit(p: float) -> float:
        return p * tokens - cost - sum(min(cap, p * f) for f, cap in weekly)

    hi = 1.0
    while profit(hi) <= 0:
        hi *= 2
        if hi > 1e9:
            return float("inf")
    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if profit(mid) <= 0 else (lo, mid)
    return hi


CYCLES: List[Cycle] = [
    Cycle(need=1, label="usage needs 1 reputable outside funder"),
    Cycle(need=5, label="usage needs 5 distinct reputable funders"),
    Cycle(need=20, label="usage needs 20 distinct reputable funders"),
    Cycle(need=5, renew_weeks=13, label="5 funders, reputation earned in the last quarter"),
    Cycle(need=5, vest_weeks=13, label="5 funders; merit vests over 13 weeks on realised reach"),
    Cycle(need=5, vest_weeks=26, label="5 funders; merit vests over 26 weeks on realised reach"),
]


def cycle_report(seeds: Sequence[int], costs: Costs = Costs(), w: World = World()) -> str:
    out = ["| Per cycle, one shared pool | Farming pays once honest funders get back, in tokens | Farmer's break-even "
           "price ($ a token) | Honest: tokens per $ funded | Honest work's share of the pool against the farmer | "
           "Honest repositories' usage evidence | The farmer's best strategy |", "|---|---|---|---|---|---|---|"]
    for c in CYCLES:
        rs = [cycle_run(s, c, w, costs) for s in seeds]
        be = [r[0] for r in rs]
        ratio = [r[0] * r[1] for r in rs]
        s0 = rs[0][3]
        out.append(f"| {c.label} | **{mean(ratio):.0%}** | {mean(be):.4f} ± {2 * _se(be):.4f} | "
                   f"{mean(r[1] for r in rs):.2f} | {mean(r[2] for r in rs):.0%} | {mean(r[4] for r in rs):.0%} | "
                   f"{s0.fixes} fixes a week, {s0.socks} socks with bought reputation |")
    return "\n".join(out)


def hybrid_sweep(seeds: Sequence[int], fees: Sequence[float] = (0.0, 0.05, 0.10, 0.20),
                 detects: Sequence[float] = (0.0, 0.5, 0.8, 0.9), manufactured: float = 200.0,
                 c: Cycle = Cycle(need=5, cap_coin=True)) -> str:
    """The hybrid against the plain per-cycle split, by the market fee on bounty coin and the judges' detection rate
    of manufactured importance. Each cell: the share of their funding honest funders get back in tokens when farming
    starts to pay (higher is safer)."""
    plain = replace(c, cap_coin=False)
    head = "| Market fee on bounty coin | Split | " + " | ".join(f"{d:.0%} seen through" for d in detects) + \
        " | Trivial fixes only | Honest funders' cost (fee on what they fund) |"
    out = [head, "|" + "---|" * (len(detects) + 4)]
    for fee in fees:
        costs = replace(Costs(), market_fee=fee)
        for name, cyc in (("plain per cycle", plain), ("hybrid: capped by outside coin", c)):
            cells = []
            for w in [World(manufactured=manufactured, detect=d) for d in detects] + [World()]:
                rs = [cycle_run(s, cyc, w, costs) for s in seeds]
                cells.append(f"{mean(r[0] * r[1] for r in rs):.0%}")
            out.append(f"| {fee:.0%} | {name} | " + " | ".join(cells) + f" | {fee:.0%} |")
    return "\n".join(out)


def pot_sweep(seeds: Sequence[int], betas: Sequence[float] = (0.1, 0.2, 0.3, 0.5, 1.0),
              detects: Sequence[float] = (0.0, 0.5, 0.8, 0.9), manufactured: float = 200.0) -> str:
    """#182: the hybrid with a fee indexed to the pot (β times the token value a dollar of bounty coin earns that
    cycle) against flat fees. Each cell: the share of their funding honest funders get back in tokens when farming
    starts to pay, before the fee ("never": no token price makes farming pay)."""
    c = Cycle(need=5, cap_coin=True)
    no_fee = replace(Costs(), market_fee=0.0)
    head = "| Fee | " + " | ".join(f"{d:.0%} caught" for d in detects) + \
        " | Trivial fixes only | Honest funders pay, as a share of their token value |"
    out = [head, "|" + "---|" * (len(detects) + 3)]
    worlds = [World(manufactured=manufactured, detect=d) for d in detects] + [World()]

    def cell(rs):
        fin = [r for r in rs if math.isfinite(r[0])]
        if not fin:
            return "**never**"
        share = mean(r[0] * r[1] for r in fin)
        return f"{share:.0%}" + (f" ({len(rs) - len(fin)} of {len(rs)} never)" if len(fin) < len(rs) else "")

    for fee in (0.10, 0.20):
        rows = [[cycle_run(s, c, w, replace(Costs(), market_fee=fee)) for s in seeds] for w in worlds]
        out.append(f"| flat {fee:.0%} | " + " | ".join(cell(rs) for rs in rows) + f" | {fee:.0%} of the coin |")
    for beta in betas:
        cb = replace(c, pot_fee=beta)
        rows = [[cycle_run(s, cb, w, no_fee) for s in seeds] for w in worlds]
        kept = mean(r[5] / r[1] for r in rows[-1])
        out.append(f"| pot-indexed, β = {beta:g} | " + " | ".join(cell(rs) for rs in rows) + f" | {kept:.0%} |")
    for beta, cap in ((1.0, 0.20), (0.5, 0.20), (1.0, 0.10), (0.5, 0.10)):
        cb = replace(c, pot_fee=beta, pot_cap=cap)
        rows = [[cycle_run(s, cb, w, no_fee) for s in seeds] for w in worlds]
        out.append(f"| pot-indexed, β = {beta:g}, capped at {cap:.0%} of the coin | " + " | ".join(cell(rs) for rs in rows)
                   + f" | {beta:.0%} of their token value, up to {cap:.0%} of the coin |")
    return "\n".join(out)


def _se(xs: Sequence[float]) -> float:
    xs = [x for x in xs if math.isfinite(x)]
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 / len(xs) ** 0.5


def report(seeds: Sequence[int], costs: Costs = Costs(), w: World = World()) -> str:
    out = ["| Rule | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | "
           "Honest: tokens per $ funded | Farmer's tokens a year | Its cost a year ($) | Its best strategy | "
           "Honest repos with the token on | Weeks to turn on | Honest funding burned |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for rule in RULES:
        rs = [run(s, rule, w, costs) for s in seeds]
        be = [r.break_even for r in rs]
        fin = [x for x in be if math.isfinite(x)]
        top = max(((r.strategy.fixes, r.strategy.coin, r.strategy.socks, r.strategy.rep) for r in rs if r.strategy),
                  key=lambda k: sum(1 for r in rs if r.strategy and (r.strategy.fixes, r.strategy.coin,
                                                                       r.strategy.socks, r.strategy.rep) == k),
                  default=None)
        strat = (f"{top[0]} fixes a week, ${top[1]:g} each, " + (f"{top[2]} socks" + (" with bought reputation"
                 if top[3] else "") if top[2] else "funding itself")) if top else "can't mint"
        weeks = [r.honest_weeks_to_activate for r in rs if math.isfinite(r.honest_weeks_to_activate)]
        ratio = [r.break_even * r.honest_tokens_per_dollar for r in rs if math.isfinite(r.break_even)]
        out.append(
            f"| {rule.label} | " + (f"**{mean(ratio):.0%}**" if ratio else "never") + " | "
            + (f"{mean(fin):.4f} ± {2 * _se(fin):.4f}" if fin else "can't mint")
            + f" | {mean(r.honest_tokens_per_dollar for r in rs):.2f}"
            f" | {mean(r.farmer_tokens for r in rs):,.0f} | {mean(r.farmer_cost for r in rs):,.0f} | {strat} | "
            f"{mean(r.honest_active_share for r in rs):.0%} | "
            + (f"{mean(weeks):.1f}" if weeks else "–") + f" | {mean(r.honest_burn_share for r in rs):.1%} |")
    st = [single_token(s, w, costs) for s in seeds]
    out.append(f"| For comparison: #58's one protocol token (a shared pool) | **{mean(x[0] * x[2] for x in st):.0%}** | "
               f"{mean(x[0] for x in st):.4f} ± {2 * _se([x[0] for x in st]):.4f} | {mean(x[2] for x in st):.2f} | "
               f"{mean(x[1] for x in st):,.0f} | – | its fixes in the shared pool | – | – | – |")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.repotokens")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--contract", action="store_true", help="the contract's fees: no market fee")
    ap.add_argument("--weight", type=float, default=World().trivial_value,
                    help="the AI weight the farmer's issues get, in dollars (a manufactured serious-looking bug: more)")
    ap.add_argument("--rep-full", type=float, default=World().rep_full,
                    help="dollars funded on others' paid bounties for full reputation")
    ap.add_argument("--cycle", action="store_true", help="the per-cycle shared pool instead of per-fix rules")
    ap.add_argument("--manufactured", type=float, default=0.0,
                    help="the value judges give a manufactured serious-looking bug they don't see through")
    ap.add_argument("--detect", type=float, default=0.0, help="the share of manufactured bugs the judges see through")
    ap.add_argument("--hybrid", action="store_true",
                    help="sweep the hybrid (per-cycle split capped by outside coin) by market fee and detection")
    ap.add_argument("--pot", action="store_true",
                    help="sweep a fee indexed to the pot's value (#182) against flat fees, by detection")
    a = ap.parse_args(argv)
    if a.pot:
        print(pot_sweep(range(1, a.seeds + 1), manufactured=a.manufactured or 200.0))
        return 0
    if a.hybrid:
        print(hybrid_sweep(range(1, a.seeds + 1), manufactured=a.manufactured or 200.0))
        return 0
    costs = CONTRACT_COSTS if a.contract else Costs()
    w = World(trivial_value=a.weight, rep_full=a.rep_full, manufactured=a.manufactured, detect=a.detect)
    print((cycle_report if a.cycle else report)(range(1, a.seeds + 1), costs, w))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
