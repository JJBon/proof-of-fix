"""Market pricing for v3 (#132 design D9, specs/check-pricing; #134 task 1.4): no account or vote sets a price.

- **Unit prices** (the pass-through part): every active validator posts a table of its own unit costs whenever it
  likes, and only its latest counts. At the end of each `PRICE_PERIOD`, each unit's price moves toward the median of
  the counting validators' latest values, by at most `PRICE_STEP_MAX`, never above `PRICE_CAP_X` times its value at
  deployment, and only if at least `MEDIAN_MIN_POSTERS` posted it (`step_price`). The units are v2's price table
  (pof.checkgas: input, cached and output tokens per family, vCPU- and GB-seconds, storage) plus gas per check.
- **The service fee** (a queue controller, like EIP-1559's base fee): at the end of each period it rises `FEE_STEP` if
  more than `WAIT_HIGH` of the period's submissions waited for a panel, otherwise falls `FEE_STEP` if more than
  `IDLE_HIGH` of the active validators weren't drawn, within [`FEE_FLOOR`, `FEE_CEILING`] (`step_fee`).
- **Quotes:** an attempt is charged the unit prices and the fee in effect when it was submitted (`Market.quote`).
- **Entry and exit:** prospective operators arrive at `MarketWorld.prospects_week` and register if their expected
  net a month is positive; honest validators review their own month every `review_days` and leave if it is
  negative (`Market.on_tick`). A month's net counts the service fee and the margin on usage (paid at the unit
  prices, spent at the validator's own costs), less the node's overhead per check, the expected slash for an outage
  (`outage_slash`: D16's flat amounts under #141, v2's `NO_REVEAL_SLASH_BPS` under #134; with round 3's switch, the
  larger of the flat amount and a share of each expected draw's bounty), the node's fixed costs and the bond's
  capital.
- **#141's rules** (each a `Params` field): every validator posts every family's list price and a table missing a unit
  doesn't count (`POST_ALL_FAMILIES`); the lower median for an even count; `IDLE_HIGH` 40 %; the switches
  `IDLE_WINDOW_DAYS` and `FEE_STEP_UP`. The wait signal (`WAIT_SIGNAL`): round 2 counts every wait once ("every": a
  submission in the period it starts waiting, and a stalled counted panel); round 1 counted only waits a newcomer at
  the bond floor could end ("floor"); "any" is a newcomer of any bond.

`Market` is `net.FlatFee`'s interface (`fee`, `end_period`), so `net.py` is unchanged. A paid check's pass-through
part goes through the same hook: `Market.fee` returns the service fee plus the quoted usage less the world's flat
`usage_per_check` (which `Net` adds to the solver's charge), and books the validator's own usage cost less that flat
amount as overhead. The solver is charged the quoted fee plus the quoted usage; the validator nets the fee plus its
usage margin. `MarketMixin` installs a `Market` from an actor's `setup`, so every pricing attacker runs alone against
its honest twin with `actors.against_twin` unchanged.

The attackers (specs/incentive-simulation, "Market pricing in the simulation"):
- `Cartel`: validators that refuse work (stay silent when drawn) to fake a shortage while the fee is below the
  ceiling; replacements come from the same sample, so nothing waits;
- `Spammer`: a solver faking demand, either with fixes to bounties no panel can judge yet (they wait, and count in
  the wait share) or with bad fixes that are judged (they keep validators drawn); with validators of its own;
- `Inflater`: validators posting cost tables at a multiple of their real costs.

    python3 -m pof.sim.openval pricing --seeds N

Simulated only (rule 1): nothing here opens a connection, holds a key or moves money.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_left, bisect_right
from collections import Counter, deque
from dataclasses import dataclass, replace
from statistics import mean, median, median_low
from typing import Callable, Deque, Dict, List, Optional, Sequence, Set, Tuple

from ... import checkgas as G
from . import actors as A
from . import panels as D
from .net import COUNTED, ISSUE, Act, Honest, Net, Sub
from .params import BPS, DAY, MONTH, PARAMS, WEEK, WORLD, YEAR, Params, World
from .registry import ACTIVE, CANDIDATE, GONE, LEAVING, Validator

# randomness tags of this module (panels' tags are 1-16): prospects, costs, initial validators, the attackers
T_PROSPECT, T_COST, T_INITIAL, T_REFUSE, T_SPAM = 101, 102, 103, 104, 105
INITIAL_VID = 400_000  # the market's initial honest validators
PROSPECT_VID = 500_000  # prospective operators: a fixed id each, so an attacker's twin sees the same newcomers

# The world's families priced as v2's table prices them (pof.checkgas.judge_table); open weights at Llama's rates.
FAMILY_TABLE = {"anthropic": "anthropic", "openai": "openai", "google": "google", "open-weight": "llama",
                # the score tables' families (pof.sim.openval.scores), priced as the providers they stand for when
                # task 1.8 runs them on the market fee (pof.sim.openval.full)
                "top": "anthropic", "mid": "openai", "low": "google", "weak": "llama"}
TOKEN_FIELDS = ("input", "cached", "output")
SHARED_UNITS = ("vcpu_second", "gb_second", "storage_mb", "gas")


def family_units(family: str) -> Tuple[str, ...]:
    return tuple(f"{family}.{x}" for x in TOKEN_FIELDS)


@dataclass(frozen=True)
class CheckUsage:
    """One counted judge's usage: a judge-grade medium review (pof.costs: 28,500 input tokens of which 7,000 cached,
    4,000 output), an 8-minute test run on 2 vCPU and 4 GB (the sandbox's profile), 1 MB kept, one check's gas."""
    input: int = 28_500
    cached: int = 7_000
    output: int = 4_000
    vcpu_seconds: float = 2 * 480.0
    gb_seconds: float = 4 * 480.0
    storage_mb: float = 1.0
    gas: float = 1.0


def usage_cost(prices: Dict[str, float], family: str, q: CheckUsage = CheckUsage()) -> float:
    return (((q.input - q.cached) * prices[f"{family}.input"] + q.cached * prices[f"{family}.cached"]
             + q.output * prices[f"{family}.output"]) / G.M
            + q.vcpu_seconds * prices["vcpu_second"] + q.gb_seconds * prices["gb_second"]
            + q.storage_mb * prices["storage_mb"] + q.gas * prices["gas"])


def genesis_prices(families: Sequence[str], gas: float = 0.005) -> Dict[str, float]:
    """The table at deployment: v2's first table (the providers' list prices, 2026-10-30) and gas per check."""
    e = G.judge_table().entries()
    out: Dict[str, float] = {}
    for f in families:
        src = FAMILY_TABLE.get(f, f)
        for x in TOKEN_FIELDS:
            out[f"{f}.{x}"] = e[f"{src}.{x}"]
    for u in SHARED_UNITS[:3]:
        out[u] = e[u]
    out["gas"] = gas
    return out


# ---------- the two rules, as pure functions ----------

def step_price(old: float, genesis: float, values: Sequence[float], p: Params = PARAMS) -> float:
    """A unit's price at the end of a period: toward the median of the counting validators' latest values, by at most
    PRICE_STEP_MAX, never above PRICE_CAP_X x its value at deployment; unchanged if fewer than MEDIAN_MIN_POSTERS
    posted it. An even count's median is the mean of the two middle values, or the lower one (MEDIAN_LOW_EVEN)."""
    if len(values) < p.MEDIAN_MIN_POSTERS:
        return old
    target = median_low(values) if p.MEDIAN_LOW_EVEN else median(values)
    return min(max(target, old * (1 - p.PRICE_STEP_MAX)), old * (1 + p.PRICE_STEP_MAX), p.PRICE_CAP_X * genesis)


def step_fee(fee: float, submitted: int, waited: int, active: int, drawn: int, p: Params = PARAMS) -> float:
    """The service fee at the end of a period: up FEE_STEP (FEE_STEP_UP when set) if more than WAIT_HIGH of the period's
    submissions waited for a panel; otherwise down FEE_STEP if more than IDLE_HIGH of the active validators weren't
    drawn; within [FEE_FLOOR, FEE_CEILING]."""
    if submitted > 0 and waited / submitted > p.WAIT_HIGH:
        fee *= 1 + (p.FEE_STEP_UP if p.FEE_STEP_UP is not None else p.FEE_STEP)
    elif active > 0 and (active - drawn) / active > p.IDLE_HIGH:
        fee *= 1 - p.FEE_STEP
    return min(max(fee, p.FEE_FLOOR), p.FEE_CEILING)


def outage_slash(p: Params, w: World, bond: float, draws: Sequence[Tuple[float, float]] = ()) -> float:
    """An honest validator's expected slash per draw for its outages (1 - reliability of its draws): #134's share of
    the bond (NO_REVEAL_SLASH_BPS), or D16's flat amounts: SEALED_NO_REVEAL_SLASH for an outage after the seal
    (`World.outage_sealed`), SILENCE_SLASH for one before it. Under round 3's switch (SILENCE_SLASH_BPS,
    SEALED_NO_REVEAL_SLASH_BPS) an outage's slash follows the bounty (`Params.miss_slash`): its mean over `draws`,
    (weight, bounty) pairs of the draws the validator expects; without draws, or with the switch off, the flat amounts."""
    def miss(sealed: bool) -> float:
        bps = p.SEALED_NO_REVEAL_SLASH_BPS if sealed else p.SILENCE_SLASH_BPS
        total = sum(x for x, _ in draws)
        if not bps or total <= 0:
            return p.miss_slash(0.0, sealed)
        return sum(x * p.miss_slash(b, sealed) for x, b in draws) / total
    flat = w.outage_sealed * miss(True) + (1 - w.outage_sealed) * miss(False)
    return (1 - w.reliability) * (p.NO_REVEAL_SLASH_BPS / BPS * bond + flat)


WAIT_KEYS = {"every": "waited", "floor": "waited_floor", "any": "waited_any"}


# ---------- the market's world ----------

@dataclass(frozen=True)
class MarketWorld:
    """What the market simulation assumes beyond `World` (each named in the report)."""
    fee_start: Optional[float] = None  # None: Params.FEE_START
    initial: int = 20  # honest validators active at the start beside the genesis one; bonds as World.join_bonds
    entry: bool = True  # prospective operators enter, and honest validators leave, by their expected net
    prospects_week: float = 2.0  # prospective operators arriving (Poisson), each with World.join_bonds' bonds
    review_days: float = 30.0  # how often an honest validator reviews its month (at a phase of its own)
    patience: int = 1  # it leaves after this many reviews in a row expecting a loss (leaving forfeits qualification)
    cost_spread: float = 0.10  # a validator's unit costs: the provider's price x U(1 - s, 1 + s), per unit group
    post_all_families: Optional[bool] = None  # honest validators also post the other families' list prices (None:
    # Params.POST_ALL_FAMILIES, #141's rule; #134 posted only its own family's)
    provider_changes: Tuple[Tuple[float, str, float], ...] = ()  # (day, unit prefix, factor): a provider's new price
    gas: float = 0.005  # gas per counted check, at deployment
    usage: CheckUsage = CheckUsage()


MARKET = MarketWorld()


@dataclass
class Ledger:
    """A validator's checks under the market: service fees, the margin on usage, and when it was paid."""
    service: float = 0.0
    margin: float = 0.0
    checks: int = 0
    times: Deque[float] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.times is None:
            self.times = deque()

    def recent(self, t: float, span: float) -> int:
        while self.times and self.times[0] < t - span:
            self.times.popleft()
        return len(self.times)


Poster = Callable[["Market", Validator, float], Dict[str, float]]


class Market:
    """The fee hook with D9's rules, the posted tables, the quotes, and entry and exit."""

    def __init__(self, p: Params = PARAMS, w: World = WORLD, mw: MarketWorld = MARKET, seed: int = 1):
        self.p, self.w, self.mw, self.seed = p, w, mw, seed
        self.genesis = genesis_prices(w.families, mw.gas)
        self.prices = dict(self.genesis)
        self.fee_now = p.FEE_START if mw.fee_start is None else mw.fee_start
        self.quotes_t: List[float] = [0.0]
        self.quotes: List[Tuple[float, Dict[str, float]]] = [(self.fee_now, dict(self.prices))]
        self.tables: Dict[int, Dict[str, float]] = {}  # each validator's latest posted table
        self.posters: Dict[int, Poster] = {}  # validators posting by a policy of their own (attackers)
        self.ledger: Dict[int, Ledger] = {}
        self.series: List[dict] = []
        self.stats: Counter = Counter()
        self._factors: Dict[int, Tuple[float, float, float]] = {}
        self._acc: Counter = Counter()
        self._drawn: Set[int] = set()
        self._drawn_hist: Deque[Set[int]] = deque()  # the last IDLE_WINDOW_DAYS periods' drawn validators
        self._ticks = 0
        self._scanned = -1.0
        self._stalled_seen: Set[int] = set()
        self._bounties: Deque[Tuple[float, float]] = deque()  # (t, bounty) of recent submissions
        self._seen_sids = 0
        self._losing: Dict[int, int] = {}
        self._prospects: List[Tuple[float, int, float, str, str, str]] = []
        self.checks_total = 0

    # ----- costs and tables -----

    def factors(self, vid: int) -> Tuple[float, float, float]:
        """A validator's own cost factors (tokens, sandbox and storage, gas), bound to its id."""
        f = self._factors.get(vid)
        if f is None:
            s = self.mw.cost_spread
            f = tuple(1 + s * (2 * D.u(self.seed, T_COST, vid, g) - 1) for g in range(3))  # type: ignore
            self._factors[vid] = f
        return f

    def provider(self, unit: str, t: float) -> float:
        """The provider's price of a unit at time t: the deployment's, times every change made by then."""
        x = self.genesis[unit]
        for day, prefix, factor in self.mw.provider_changes:
            if t >= day * DAY and unit.startswith(prefix):
                x *= factor
        return x

    def costs(self, vid: int, family: str, t: float, all_families: bool = False) -> Dict[str, float]:
        """A validator's real unit costs at time t: its own family's tokens (every family's with `all_families`) and
        the shared units."""
        ft, fs, fg = self.factors(vid)
        fams = self.w.families if all_families else (family,)
        out = {u: self.provider(u, t) * ft for f in fams for u in family_units(f)}
        for u in SHARED_UNITS[:3]:
            out[u] = self.provider(u, t) * fs
        out["gas"] = self.provider("gas", t) * fg
        return out

    def post_all(self) -> bool:
        return self.p.POST_ALL_FAMILIES if self.mw.post_all_families is None else self.mw.post_all_families

    def honest_table(self, v: Validator, t: float) -> Dict[str, float]:
        """What an honest validator posts. #141 (POST_ALL_FAMILIES, D9): every family's public list price for tokens
        (the provider's price: one number for everyone) and its own costs for the shared units. #134: its own costs,
        for its own family's tokens (or, in v1's remedy row `MarketWorld.post_all_families`, every family's tokens at
        its own cost factor)."""
        if self.p.POST_ALL_FAMILIES:
            out = self.costs(v.vid, v.family, t)
            for f in self.w.families:
                for u in family_units(f):
                    out[u] = self.provider(u, t)
            return out
        return self.costs(v.vid, v.family, t, self.post_all())

    def post(self, v: Validator, table: Dict[str, float]) -> None:
        """A validator posts its table (signed by its key; any time; the latest replaces the earlier). Only units of
        the price table: a service fee isn't a unit, and no one posts one."""
        unknown = set(table) - set(self.genesis)
        if unknown:
            raise ValueError(f"not units of the price table: {sorted(unknown)}")
        if any(x < 0 for x in table.values()):
            raise ValueError("a cost can't be negative")
        self.tables[v.vid] = dict(table)
        self.stats["posts"] += 1

    def counting(self, net: Net) -> List[Validator]:
        """Validators whose tables count: active ones (not candidates, suspended or leaving)."""
        return [v for v in net.reg.validators.values() if v.state == ACTIVE]

    # ----- quotes and the fee hook -----

    def quote(self, t: float) -> Tuple[float, Dict[str, float]]:
        """The service fee and unit prices in effect at time t (an attempt started at t is charged these)."""
        return self.quotes[max(0, bisect_right(self.quotes_t, t) - 1)]

    def led(self, vid: int) -> Ledger:
        x = self.ledger.get(vid)
        if x is None:
            x = self.ledger[vid] = Ledger()
        return x

    def service_part(self, sub: Sub) -> float:
        """The service fee alone in what `fee` returns for `sub` (its quote): what D14's score factor scales."""
        return self.quote(sub.t)[0]

    def fee(self, net: Net, sub: Sub, v: Validator) -> float:
        fee, prices = self.quote(sub.t)
        paid = usage_cost(prices, v.family, self.mw.usage)
        real = usage_cost(self.costs(v.vid, v.family, net.t), v.family, self.mw.usage)
        v.acct.overhead += real - self.w.usage_per_check  # the validator's own usage, less what Net passes through
        led = self.led(v.vid)
        led.service += fee
        led.margin += paid - real
        led.checks += 1
        led.times.append(net.t)
        self.checks_total += 1
        self.stats["charged_fee"] += fee
        self.stats["charged_usage"] += paid
        self.stats["real_usage"] += real
        self.stats["paid_checks"] += 1
        return fee + paid - self.w.usage_per_check

    def end_period(self, net: Net, period: Counter) -> None:
        p = self.p
        self._acc["submitted"] += period["submitted"]
        for key in WAIT_KEYS.values():
            self._acc[key] += period[key]
        for panel in net.stalled:  # a counted panel stalled for want of a replacement: its submission waits too
            if panel.role == COUNTED and panel.sub.sid not in self._stalled_seen:
                self._stalled_seen.add(panel.sub.sid)
                self._acc["waited"] += 1
                self._acc["stalled"] += 1
                # #141: a newcomer at the floor could be its replacement only if bonded for its bounty
                self._acc["waited_floor"] += p.bond_needed(panel.sub.bounty) <= p.BOND_FLOOR + 1e-9
                self._acc["waited_any"] += 1
        self._drawn |= net.period_drawn
        for s in net.subs.values():  # everyone seated this day, silent ones and replacements included
            if s.drawn_t is not None and s.drawn_t > self._scanned and s.draw is not None:
                self._drawn |= s.draw.drawn
        self._scanned = net.t
        self._ticks += 1
        if self._ticks < max(1, round(p.PRICE_PERIOD_H / DAY)):
            return
        counting = self.counting(net)
        for v in counting:
            poster = self.posters.get(v.vid)
            self.post(v, poster(self, v, net.t) if poster is not None else self.honest_table(v, net.t))
        ids = [v.vid for v in counting]
        if p.POST_ALL_FAMILIES:  # #141: a table missing a unit doesn't count
            ids = [i for i in ids if len(self.tables.get(i, ())) == len(self.genesis)]
        for unit in self.prices:
            vals = [self.tables[i][unit] for i in ids if unit in self.tables.get(i, ())]
            self.prices[unit] = step_price(self.prices[unit], self.genesis[unit], vals, p)
        active = {v.vid for v in counting}
        self._drawn_hist.append(self._drawn)
        while len(self._drawn_hist) > max(1, p.IDLE_WINDOW_DAYS):
            self._drawn_hist.popleft()
        seen = set().union(*self._drawn_hist) if len(self._drawn_hist) > 1 else self._drawn
        drawn = len(active & seen)
        sub_n, wait_n = self._acc["submitted"], self._acc[WAIT_KEYS[p.WAIT_SIGNAL]]
        self.fee_now = step_fee(self.fee_now, sub_n, wait_n, len(active), drawn, p)
        self.quotes_t.append(net.t)
        self.quotes.append((self.fee_now, dict(self.prices)))
        self.series.append({"t": net.t, "fee": self.fee_now, "active": len(active),
                            "waited": wait_n / sub_n if sub_n else 0.0,
                            "waited_all": self._acc["waited"] / sub_n if sub_n else 0.0,
                            "idle": (len(active) - drawn) / len(active) if active else 0.0,
                            "usage": mean(usage_cost(self.prices, f, self.mw.usage) for f in self.w.families)})
        self.stats["periods"] += 1
        self.stats["rises"] += self.fee_now > self.quotes[-2][0] + 1e-12
        self.stats["falls"] += self.fee_now < self.quotes[-2][0] - 1e-12
        self._acc, self._drawn, self._ticks = Counter(), set(), 0

    # ----- entry and exit -----

    def start(self, net: Net) -> None:
        """The market's initial honest validators (active, bonds as World.join_bonds) and the prospects' arrivals."""
        w, mw = self.w, self.mw
        rng = random.Random(D.h(T_INITIAL, self.seed))
        bonds, weights = zip(*w.join_bonds)
        for i in range(mw.initial):
            v = net.reg.register(0.0, key=f"m{i}", signer=f"m{i}", bond=rng.choices(bonds, weights)[0],
                                 proof=w.tees[i % len(w.tees)], host=w.hosts[i % len(w.hosts)],
                                 family=w.families[i % len(w.families)], operator=f"m-op{i}", vid=INITIAL_VID + i)
            net.reg.seed_active(v, 0.0)
        rng = random.Random(D.h(T_PROSPECT, self.seed))
        t, i = 0.0, 0
        while mw.entry and mw.prospects_week > 0:
            t += rng.expovariate(mw.prospects_week / WEEK)
            if t > w.horizon_h:
                break
            self._prospects.append((t, PROSPECT_VID + i, rng.choices(bonds, weights)[0], rng.choice(w.hosts),
                                    w.pick_tee(rng), rng.choice(w.families)))
            i += 1
        self._prospects.reverse()

    def _honest(self, v: Validator) -> bool:
        return v.behaviour is None and v.party == v.operator and not v.genesis

    def expected_draws(self, net: Net, bond: float, joining: bool) -> List[Tuple[float, float]]:
        """(k / n, bounty) for each issue submission of the last 30 days a validator with `bond` covers, where n counts
        the active validators bonded for it (itself included, `joining` adds it) and k is the largest odd number n
        allows within the k table's limit (the caps aside). The waiting submissions are in the count: a newcomer sees
        the queue."""
        p = self.p
        bonds = sorted(v.bond for v in net.reg.validators.values() if v.state == ACTIVE)
        if joining:
            bonds.append(bond)
            bonds.sort()
        out = []
        for _, b in self._bounties:
            need = p.bond_needed(b)
            if bond < need - 1e-9:
                continue
            n = len(bonds) - bisect_left(bonds, need - 1e-9)
            k = p.k_for(n)
            if k and b <= p.limit(k):
                out.append((k / n, b))
        return out

    def expected_checks(self, net: Net, bond: float, joining: bool,
                        draws: Optional[List[Tuple[float, float]]] = None) -> float:
        """Counted checks a month a validator with `bond` can expect: the sum of `expected_draws`' k / n, a month."""
        total = 0.0
        for x, _ in (self.expected_draws(net, bond, joining) if draws is None else draws):
            total += x
        return total * MONTH / min(MONTH, max(DAY, net.t))

    def slash_draws(self, net: Net, bond: float, joining: bool) -> List[Tuple[float, float]]:
        """The draws an outage's expected slash is weighted by: none while round 3's switch is off (the flat amounts,
        so round 2's numbers are unchanged)."""
        if not (self.p.SILENCE_SLASH_BPS or self.p.SEALED_NO_REVEAL_SLASH_BPS):
            return []
        return self.expected_draws(net, bond, joining)

    def month_net(self, checks: float, bond: float, vid: int, family: str, t: float,
                  draws: Sequence[Tuple[float, float]] = ()) -> float:
        """A validator's expected net a month at the current prices: the service fee and its usage margin less its
        overhead and expected outage slash per check (over `draws`, under round 3's switch), less the fixed costs and
        the bond's capital."""
        w, p = self.w, self.p
        margin = (usage_cost(self.prices, family, self.mw.usage)
                  - usage_cost(self.costs(vid, family, t), family, self.mw.usage))
        slash = outage_slash(p, w, bond, draws)
        return (checks * (self.fee_now + margin - w.enclave.per_check - slash) - w.enclave.fixed_month
                - bond * w.capital_rate / 12)

    def on_tick(self, net: Net) -> None:
        t = net.t
        subs = list(net.subs.values())
        for s in subs[self._seen_sids:]:
            if s.tier == ISSUE:
                self._bounties.append((s.t, s.bounty))
        self._seen_sids = len(subs)
        while self._bounties and self._bounties[0][0] < t - MONTH:
            self._bounties.popleft()
        if not self.mw.entry:
            return
        while self._prospects and self._prospects[-1][0] <= t:
            _, vid, bond, host, tee, family = self._prospects.pop()
            dr = self.expected_draws(net, bond, True)
            if self.month_net(self.expected_checks(net, bond, True, dr), bond, vid, family, t,
                              self.slash_draws(net, bond, True)) > 0:
                net.reg.register(t, key=f"p{vid}", signer=f"p{vid}", bond=bond, proof=tee, host=host, family=family,
                                 operator=f"p-op{vid}", vid=vid)
                self.stats["entered"] += 1
            else:
                self.stats["declined"] += 1
        review = self.mw.review_days * DAY
        for v in list(net.reg.validators.values()):
            if v.state not in (ACTIVE, CANDIDATE) or not self._honest(v):
                continue
            age = t - v.registered_at  # once per review period, at a phase of its own (bound to its id), after
            if age < review or (age - review * D.u(self.seed, T_COST, v.vid, 9)) % review >= DAY:  # its first one
                continue
            joining = v.state != ACTIVE
            checks = self.expected_checks(net, v.bond, joining)
            if self.month_net(checks, v.bond, v.vid, v.family, t, self.slash_draws(net, v.bond, joining)) >= 0:
                self._losing.pop(v.vid, None)
                continue
            self._losing[v.vid] = self._losing.get(v.vid, 0) + 1
            if self._losing[v.vid] >= self.mw.patience:
                net.leave(v)
                self.stats["left"] += 1


# ---------- the market installed by an actor ----------

class MarketMixin:
    """Installs a `Market` as the network's fee from the actor's `setup`, and runs entry and exit on each tick. The
    world: no Poisson joins and no `World.initial_active` (the market brings its own validators and prospects)."""
    market_world: MarketWorld = MARKET
    fee_start: Optional[float] = None

    def world(self) -> World:
        return replace(WORLD, initial_active=0, joins_week=0.0)

    def mworld(self) -> MarketWorld:
        mw = self.market_world
        return mw if self.fee_start is None else replace(mw, fee_start=self.fee_start)

    def setup(self, net: Net) -> None:
        self.market = Market(net.p, net.w, self.mworld(), net.seed)
        net.fee = self.market
        self.market.start(net)
        super().setup(net)  # type: ignore[misc]

    def on_tick(self, net: Net) -> None:
        self.market.on_tick(net)
        super().on_tick(net)  # type: ignore[misc]


def in_market(actor: A.Actor, mw: MarketWorld) -> A.Actor:
    """The actor, run in the market world `mw`."""
    actor.market_world = mw  # type: ignore[attr-defined]
    return actor


class Baseline(MarketMixin, A.Actor):
    """No attacker: the market alone (the fee finding the validators' cost)."""
    name = "market"
    party = "nobody"

    def __init__(self, honest: bool = True, mw: MarketWorld = MARKET, w: Optional[World] = None) -> None:
        super().__init__(honest)
        self.market_world, self._w = mw, w

    def world(self) -> World:
        return self._w if self._w is not None else super().world()


# ---------- the pricing attackers ----------

class Refuser(Honest):
    """A cartel member: it refuses (never seals) `rate` of its counted draws, to make the network look short of
    validators."""

    def __init__(self, rate: float):
        self.rate = rate

    def counted(self, net: Net, sub: Sub, v: Validator) -> Act:
        if sub.tier == ISSUE and D.u(net.seed, T_REFUSE, sub.sid, v.vid) < self.rate:
            net.stats["refusals"] += 1
            return Act(False, False)
        return super().counted(net, sub, v)


def _spread(net: Net, i: int) -> Tuple[str, str, str]:
    w = net.w
    return w.hosts[(i + 2) % len(w.hosts)], w.tees[i % len(w.tees)], w.families[(i + 1) % len(w.families)]


class Cartel(MarketMixin, A.Actor):
    """`nodes` validators (diversified, bonded at `bond`, active) refusing `rate` of their counted draws, so that
    submissions would wait and the fee rise. Its twin: the same validators working."""
    name = "cartel"
    party = "cartel"

    def __init__(self, honest: bool = False, nodes: int = 6, rate: float = 0.5, bond: float = 500.0):
        super().__init__(honest)
        self.n, self.rate, self.bond = nodes, rate, bond

    def setup(self, net: Net) -> None:
        super().setup(net)
        for i in range(self.n):
            host, tee, fam = _spread(net, i)
            net.register_actor(i, self.party, self.bond, host, tee, fam, f"cartel-op-{i}",
                               self.behaviour(Refuser(self.rate)), active=True)


class Spammer(MarketMixin, A.Actor):
    """A party with `nodes` validators of its own (judging honestly) and a solver faking demand at `per_day`
    submissions a day:
    - "waiting": fixes to bounties of `World.bounty_max` funded by itself, submitted only when the draw would wait
      (no panel can judge that bounty yet), so they count in the wait share; each costs the attempt fee and the
      capital its escrowed bounty locks until the solver withdraws;
    - "judged": bad fixes to ordinary bounties, judged and failed, so more validators are drawn; each costs the
      attempt fee and the checks.
    Its twin: the same validators, no spam."""
    name = "spammer"
    party = "spammer"

    def __init__(self, honest: bool = False, kind: str = "waiting", per_day: int = 1, nodes: int = 3,
                 bond: float = 500.0):
        super().__init__(honest)
        if kind not in ("waiting", "judged"):
            raise ValueError(kind)
        self.kind, self.per_day, self.n, self.bond = kind, per_day, nodes, bond

    def setup(self, net: Net) -> None:
        super().setup(net)
        for i in range(self.n):
            host, tee, fam = _spread(net, i + 3)
            net.register_actor(i, self.party, self.bond, host, tee, fam, f"spam-op-{i}", None, active=True)
        self.rng = random.Random(D.h(net.seed, T_SPAM))

    def on_tick(self, net: Net) -> None:
        super().on_tick(net)
        if self.honest:
            return
        w = net.w
        for j in range(self.per_day):
            if self.kind == "waiting":
                probe = Sub(net._sid, net.t, w.bounty_max, False, "spam-solver", frozenset(("spam-solver",)),
                            party=self.party, commitment=D.h(net.seed, T_SPAM, net._sid))
                if net.plan(probe)[1] is not None:
                    return  # a panel could judge it now: it wouldn't wait, and the checks would cost
                net.submit(net.t, w.bounty_max, False, "spam-solver", self.party, commitment=probe.commitment)
                net.parties[self.party].costs += w.bounty_max * w.capital_rate * w.withdraw_after_days * DAY / YEAR
            else:
                net.submit(net.t, A._bounties(net, self.rng, 1, self.bond / net.p.BOND_FACTOR)[0], False,
                           "spam-solver", self.party)
            net.stats["spam"] += 1


class Inflater(MarketMixin, A.Actor):
    """`nodes` validators of one `family` posting every unit at `factor` x their real costs. Its twin: the same
    validators posting their real costs. `small=True`: a small network (the genesis and 4 honest validators, one of
    them of the inflaters' family) where they are most of their family's posters."""
    name = "inflater"
    party = "inflater"

    def __init__(self, honest: bool = False, nodes: int = 3, factor: float = 100.0, family: str = "anthropic",
                 small: bool = False, bond: float = 500.0):
        super().__init__(honest)
        self.n, self.factor, self.family, self.small, self.bond = nodes, factor, family, small, bond

    def mworld(self) -> MarketWorld:
        mw = super().mworld()
        return replace(mw, initial=4) if self.small else mw

    def setup(self, net: Net) -> None:
        super().setup(net)
        w = net.w
        for i in range(self.n):
            v = net.register_actor(i, self.party, self.bond, w.hosts[(i + 3) % len(w.hosts)],
                                   w.tees[(i + 1) % len(w.tees)], self.family, f"inflate-op-{i}", None, active=True)
            if not self.honest:
                self.market.posters[v.vid] = self._post

    def _post(self, m: Market, v: Validator, t: float) -> Dict[str, float]:
        return {u: x * self.factor for u, x in m.honest_table(v, t).items()}


class PricedFeeFarmer(MarketMixin, A.FeeFarmer):
    """Phase 1's fee farmer (10 idle validators at the bond floor; its twin runs one) under market pricing."""
    name = "fee farmer (priced)"


# ---------- what the report reads ----------

def market_of(net: Net) -> Market:
    return net.fee  # type: ignore[return-value]


def honest_month(net: Net) -> List[float]:
    """Every honest validator's net a month over the time it was registered (fees, margin, slashes, costs)."""
    out = []
    for v in net.reg.validators.values():
        if v.party != v.operator or v.behaviour is not None or v.active_at is None:
            continue
        m = (min(net.t, v.leave_at) if v.leave_at is not None else net.t) - v.registered_at
        if m >= MONTH:
            out.append(net.validator_net(v) / (m / MONTH))
    return out


def settle(net: Net, weeks: int = 13) -> Dict[str, float]:
    """The fee's last `weeks` and the validators' costs then: what "how far it settles from cost" reads.
    - marginal: what one more check costs a validator: its node's overhead per check and the expected slash for an
      outage at the counting validators' mean bond (usage is passed through, its margin aside);
    - break_even: the fee at which the mean active validator's month nets zero at its own checks (its fixed costs
      and the bond's capital spread over them)."""
    m, w, p = market_of(net), net.w, net.p
    tail = [r for r in m.series if r["t"] > net.t - weeks * WEEK]
    act = [v for v in net.reg.validators.values()
           if v.state == ACTIVE and v.active_at is not None and net.t - v.active_at >= MONTH]
    bond = mean(v.bond for v in act) if act else 0.0
    slash = outage_slash(p, w, bond, m.slash_draws(net, bond, False))
    marginal = w.enclave.per_check + slash
    checks = [m.led(v.vid).recent(net.t, MONTH) for v in act]
    c = mean(checks) if checks else 0.0
    fixed = w.enclave.fixed_month + bond * w.capital_rate / 12
    be = marginal + fixed / c if c > 0 else float("inf")
    return {"fee": mean(r["fee"] for r in tail), "active": mean(r["active"] for r in tail),
            "waited": mean(r["waited"] for r in tail), "idle": mean(r["idle"] for r in tail),
            "marginal": marginal, "break_even": be, "checks": c, "bond": bond}


def fee_at(net: Net, week: float) -> float:
    m = market_of(net)
    return m.quote(week * WEEK)[0]




def run_market(seed: int, p: Params = PARAMS, w: Optional[World] = None, mw: MarketWorld = MARKET) -> Net:
    b = Baseline(mw=mw, w=w)
    return Net(seed, p, b.world(), [b]).run()


# ---------- the report's tables (reports/open-validators-v1.md, "Market pricing") ----------

# A world where the fee can move: no slash for an honest outage (phase 1's finding 6 questions it) and IDLE_HIGH at
# 50 %, so the idle signal can fire before free entry has spread the fee over idle validators.
MOVING = replace(PARAMS, NO_REVEAL_SLASH_BPS=0, IDLE_HIGH=0.5)
MARKET_100 = replace(WORLD, initial_active=0, joins_week=0.0, subs_week=100.0)
SETTLE_ROWS: List[Tuple[str, Params, MarketWorld, Optional[World]]] = [
    ("Design values", PARAMS, MARKET, None),
    ("Design values, starting at v2's $0.05", PARAMS, replace(MARKET, fee_start=0.05), None),
    ("Design values, 100 submissions a week", PARAMS, MARKET, MARKET_100),
    ("`IDLE_HIGH` 30 %", replace(PARAMS, IDLE_HIGH=0.3), MARKET, None),
    ("No outage slash (`NO_REVEAL_SLASH_BPS` 0)", replace(PARAMS, NO_REVEAL_SLASH_BPS=0), MARKET, None),
    ("No outage slash, `IDLE_HIGH` 50 %", MOVING, MARKET, None),
    ("No outage slash, `IDLE_HIGH` 50 %, starting at $0.05", MOVING, replace(MARKET, fee_start=0.05), None),
    ("No outage slash, `IDLE_HIGH` 30 %", replace(MOVING, IDLE_HIGH=0.3), MARKET, None),
]
WEEKS_SHOWN = (4, 13, 26, 52)


def _se(xs: Sequence[float]) -> float:
    return A._se(list(xs))


def _ms(xs: Sequence[float], nd: int = 3) -> str:
    xs = [x for x in xs if math.isfinite(x)]
    return f"{mean(xs):,.{nd}f} ± {2 * _se(xs):,.{nd}f}" if xs else "–"


def _pct(xs: Sequence[float]) -> str:
    return f"{100 * mean(xs):.0f} % ± {200 * _se(xs):.0f}" if xs else "–"


def _verdict(m: float, se: float) -> str:
    if m + 2 * se < 0:
        return "loses"
    if m - 2 * se > 0:
        return "**wins**"
    return "not significant"


def settle_rows(seeds: Sequence[int], rows=None) -> List[Tuple[str, Dict[str, list]]]:
    out = []
    for label, p, mw, w in (rows if rows is not None else SETTLE_ROWS):
        r: Dict[str, list] = {}
        for s in seeds:
            net = run_market(s, p, w, mw)
            m, st = market_of(net), settle(net)
            dead = st["active"] < 3
            r.setdefault("collapsed", []).append(1.0 if dead else 0.0)
            for wk in WEEKS_SHOWN:
                r.setdefault(f"w{wk}", []).append(fee_at(net, wk))
            for k in ("fee", "active", "waited", "idle"):
                r.setdefault(k, []).append(st[k])
            if not dead:
                for k in ("marginal", "break_even"):
                    r.setdefault(k, []).append(st[k])
                r.setdefault("gap", []).append(st["fee"] - st["break_even"])
                r.setdefault("ratio", []).append(st["fee"] / st["break_even"])  # D17's FEE_MARGIN reads it
            hm = honest_month(net)
            r.setdefault("month", []).append(mean(hm) if hm else float("nan"))
            r.setdefault("charge", []).append((m.stats["charged_fee"] + m.stats["charged_usage"])
                                              / max(1, m.stats["paid_checks"]))
            r.setdefault("entered", []).append(m.stats["entered"])
            r.setdefault("left", []).append(m.stats["left"])
            waits = [x for x in net.subs.values() if x.waited]
            r.setdefault("caps_waits", []).append(sum(1 for x in waits if x.wait_reason.startswith("above"))
                                                  / max(1, len(waits)))
        out.append((label, r))
    return out


def settle_table(seeds: Sequence[int], data=None) -> str:
    out = [f"### The fee finds the validators' cost ({len(seeds)} seeds; a year; 20 honest validators and the genesis "
           "at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the "
           "ceiling unless stated)", "",
           "| Variant | Fee at week " + " / ".join(str(w) for w in WEEKS_SHOWN) + " | Fee over the last 13 weeks | "
           "Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | "
           "Runs collapsed (< 3 active) | Honest validator's month |", "|---|---|---|---|---|---|---|---|---|---|"]
    for label, r in (data if data is not None else settle_rows(seeds)):
        fees = " / ".join(f"${mean(r[f'w{w}']):.3f}" for w in WEEKS_SHOWN)
        out.append(f"| {label} | {fees} | ${_ms(r['fee'])} | ${_ms(r.get('marginal', []))} | "
                   f"${_ms(r.get('break_even', []))} | {_ms(r['active'], 1)} | {_pct(r['waited'])} | "
                   f"{_pct(r['idle'])} | {sum(r['collapsed']):.0f} of {len(seeds)} | ${_ms(r['month'], 2)} |")
    out += ["", "Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the "
            "active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or "
            "more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over "
            "them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every "
            "row, so the fee is the validator's whole margin."]
    return "\n".join(out)


def series_table(seeds: Sequence[int], label: str, p: Params, mw: MarketWorld = MARKET, every: int = 4,
                 nets=None) -> str:
    nets = nets if nets is not None else [run_market(s, p, None, mw) for s in seeds]
    out = [f"### The fee over the year: {label} ({len(seeds)} seeds; means over each {every}-week span)", "",
           "| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |", "|---|---|---|---|---|"]
    for k in range(0, 52, every):
        lo, hi = k * WEEK, (k + every) * WEEK
        rows = [[r for r in market_of(n).series if lo < r["t"] <= hi] for n in nets]
        f = [mean(r["fee"] for r in rs) for rs in rows if rs]
        a = [mean(r["active"] for r in rs) for rs in rows if rs]
        wt = [mean(r["waited"] for r in rs) for rs in rows if rs]
        idl = [mean(r["idle"] for r in rs) for rs in rows if rs]
        out.append(f"| {k + 1}–{k + every} | ${_ms(f)} | {_ms(a, 1)} | {_pct(wt)} | {_pct(idl)} |")
    return "\n".join(out)


def provider_cut(seeds: Sequence[int], day: int = 30, unit: str = "anthropic.input", p: Optional[Params] = None
                 ) -> Dict[int, list]:
    """The provider halves its price on `day`, and its validators post their new costs at that day's end: the unit
    price at the end of each day around it, as a multiple of its value at deployment."""
    mw = replace(MARKET, provider_changes=((float(day), unit.split(".")[0] + ".", 0.5),))
    out: Dict[int, list] = {}
    for s in seeds:
        net = run_market(s, p or PARAMS, replace(WORLD, initial_active=0, joins_week=0.0, weeks=6), mw)
        m = market_of(net)
        for d in range(day - 1, day + 6):
            out.setdefault(d, []).append(m.quote(d * DAY + 1e-6)[1][unit] / m.genesis[unit])
    return out


def provider_table(seeds: Sequence[int], p: Optional[Params] = None) -> str:
    r = provider_cut(seeds, p=p)
    days = sorted(r)
    return "\n".join([
        f"### A provider halves its price ({len(seeds)} seeds; Anthropic's input-token price at the end of each day, as "
        "a multiple of its value at deployment; its validators post their new costs on day 30)", "",
        "| End of day | " + " | ".join(str(d) for d in days) + " |", "|---|" + "---|" * len(days),
        "| Unit price | " + " | ".join(f"{mean(r[d]):.3f}" for d in days) + " |", "",
        "One `PRICE_STEP_MAX` step (−25 %) a day until it reaches the median of the new tables (half the old "
        "median), with no proposal or vote."])


def _attack_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = market_of(net)
    fam = getattr(a, "family", "anthropic")
    unit = f"{fam}.input"
    nodes = net.party_validators(a.party)
    pa = net.parties.get(a.party)
    return {"fee": mean(r["fee"] for r in m.series),
            "price": mean(q[1][unit] for q in m.quotes) / m.genesis[unit],
            "refusals": net.stats["refusals"], "suspensions": sum(v.suspensions for v in nodes),
            "spam": net.stats["spam"], "spam_cost": pa.costs if pa else 0.0,
            "margin": sum(m.led(v.vid).margin for v in nodes), "service": sum(m.led(v.vid).service for v in nodes),
            "slashed": sum(v.acct.slashed for v in nodes), "active": settle(net)["active"]}


ATTACKS: List[Tuple[str, str, Callable[[bool], A.Actor], Params, str]] = [
    ("Cartel: 6 validators refusing half their draws", "design", lambda h: Cartel(h), PARAMS, "cartel"),
    ("Spammer: a fix a day to a $625 bounty no panel can judge yet", "design", lambda h: Spammer(h), PARAMS, "spam"),
    ("Spammer: a bad fix a day, judged", "design", lambda h: Spammer(h, kind="judged"), PARAMS, "spam"),
    ("Inflaters: 3 Anthropic validators of 24 posting 100 × their costs", "design", lambda h: Inflater(h), PARAMS,
     "inflate"),
    ("... with an even count's median the lower middle value", "design", lambda h: Inflater(h),
     replace(PARAMS, MEDIAN_LOW_EVEN=True), "inflate"),
    ("Inflaters on a small network (the genesis, 4 honest, the 3 inflaters)", "design",
     lambda h: Inflater(h, small=True), PARAMS, "inflate"),
    ("... with every validator posting every family's list price", "design",
     lambda h: in_market(Inflater(h, small=True), replace(MARKET, post_all_families=True)), PARAMS, "inflate"),
    ("Fee farmer: 10 idle validators at the bond floor (twin: one)", "design", lambda h: PricedFeeFarmer(h), PARAMS,
     "farmer"),
    ("Cartel: 6 validators refusing half their draws", "moving", lambda h: Cartel(h), MOVING, "cartel"),
    ("Spammer: a fix a day to a $625 bounty no panel can judge yet", "moving", lambda h: Spammer(h), MOVING, "spam"),
    ("Spammer: a bad fix a day, judged", "moving", lambda h: Spammer(h, kind="judged"), MOVING, "spam"),
    ("Fee farmer: 10 idle validators at the bond floor (twin: one)", "moving", lambda h: PricedFeeFarmer(h), MOVING,
     "farmer"),
]


def _did(kind: str, r: Dict[str, object]) -> str:
    if kind == "cartel":
        return (f"{r['refusals']:.0f} refusals, suspended {r['suspensions']:.0f} times, slashed "
                f"${r['slashed']:,.0f}")
    if kind == "spam":
        return f"{r['spam']:.0f} spam submissions costing its solver ${r['spam_cost']:,.0f}"
    if kind == "inflate":
        return f"usage margin ${r['margin']:,.0f} (twin: ${r['twin_margin']:,.0f})"
    if kind == "farmer":
        return f"service fees ${r['service']:,.0f} (twin: ${r['twin_service']:,.0f})"
    return ""


def attacks(seeds: Sequence[int], rows=None) -> List[Tuple[str, str, Dict[str, object], str]]:
    return [(name, world, A.against_twin(make, seeds, p=p, metrics=_attack_metrics), kind)
            for name, world, make, p, kind in (rows if rows is not None else ATTACKS)]


def attacks_table(seeds: Sequence[int], data=None) -> str:
    out = [f"### The pricing attackers against their honest twins ({len(seeds)} seeds; a year; returns in $, with "
           "bonds' capital, running costs, fees, the usage margin, slashes, attempt fees and checks counted)", "",
           "| Attacker | Pricing | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return "
           "| Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's run / twin's | "
           "What it did |", "|---|---|---|---|---|---|---|---|---|"]
    for name, world, r, kind in (data if data is not None else attacks(seeds)):
        out.append(f"| {name} | {world} | {r['diff']:,.0f} ± {2 * r['se']:,.0f} | {_verdict(r['diff'], r['se'])} | "
                   f"{r['attacker']:,.0f} | {r['twin']:,.0f} | ${r['fee']:.3f} / ${r['twin_fee']:.3f} | "
                   f"{r['price']:.2f} / {r['twin_price']:.2f} | {_did(kind, r)} |")
    out += ["", "Pricing \"design\": the design's values, the fee starting at the ceiling. \"moving\": no slash for "
            "an honest outage and `IDLE_HIGH` 50 %, where the fee moves below the ceiling (the settling table)."]
    return "\n".join(out)


def pricing_tables(seeds: Sequence[int]) -> str:
    return "\n\n".join([settle_table(seeds), series_table(seeds, "the design's values", PARAMS),
                        series_table(seeds, "no outage slash, `IDLE_HIGH` 50 %", MOVING),
                        provider_table(seeds), attacks_table(seeds)])
