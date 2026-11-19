"""Three deposit-free mechanisms, alone and combined, on measured judges (proof-of-fix#236; the owner approved
simulating them on 2026-11-15 after report measured-v4 found that, with no solver's deposit, a solver of bad fixes
profits unless about ten rival solvers search, and that a retrying solver and free identities stay open).

Each mechanism is a named switch of `Params`, off by default and read only by `NDNet` (a `Net` that refuses them):

- **reputation before large claims** (`REP_CAP`, `REP_BASE`, `REP_MULT`, `REP_ON_REVERSAL`): an identity's open
  claims may add up to at most REP_BASE + REP_MULT x its reputation, the bounties of its fixes paid and never
  reversed; a pass reversed by a test resets it. The rule and its values were fixed before any run (see the report);
- **the shared pot weighted by impact** (`POT` "impact", `POT_WINDOW_WEEKS`): no per-issue bounty is paid; each
  window's funding is split over the fixes paid in it by a weight, the issue's impact signal. #247's impact graph is
  not built: the signal is ASSUMED to correlate with the issue's true impact (its bounty) at `World.impact_corr` in
  log space, and an inflater may raise its own signal by `World.inflate_sd` at `World.inflate_cost` a fix. `POT`
  "equal" is report v4's equal units, now in the network rather than in expected values (`potsplit`);
- **a fee that only covers the judges' cost** (`JUDGE_FEE`): every submission pays it, never refunded, in place of its
  panels' per-check charges. `judge_cost` measures it: every check the network pays for, at the market's break-even
  fee plus the model's usage, over the submissions.

#251 task 3.2 adds a fourth switch, **the pledge gate** (`ACTIVE_GATE`, launch design L6; its rows and the sybil of
three are in `activesolvers`): an identity is active while it has, within `ACTIVE_WINDOW_WEEKS`, a fix whose passing
verdict became final or an upheld failing-test dispute; while fewer than `ACTIVE_SOLVERS_MIN` are, an issue listed is
left unfunded and actors start no new claim. The world's fixes are written by the `World.rival_solvers` honest
solvers (one of them, by a draw bound to the fix), so the chain's count can see them.

The base is report v4's primary case: task 10.1's network with no solver's deposit and no appeal (`evidence.P0`),
the world's contenders disputing (1 in 2, assumed), and `n` active honest solvers that each search every pass for a
failing test (`World.rival_solvers`, found 1 time in 4 on a bad fix: ASSUMED). One family is registered and seated:
Opus 5.5 or GPT-6.1 (28 validators, as v4's GPT-alone rows).

The attackers, each against its honest twin on the same seeds (`against_twin`):
- `BadFix`: bad fixes, 5 a week, on one identity (v4's solver of bad fixes; twin: submits nothing), or each from a
  fresh identity (`fresh`: free identities attempting at once; it takes the largest issue it may claim);
- `Retrier`: tries each issue up to 21 times (v4's retrier; twin: submits nothing), on one identity or fresh ones;
- `LongCon`: farms honest fixes on one identity until it may claim any issue, then submits bad fixes on the largest
  issues it may claim until a reversal resets it, then farms again (twin: farms all year);
- `RepSale`: a reputation seller and its buyer together: the buyer cashes in a bought identity of `rep0`, the seller
  farms on a fresh one (twin: the seller keeps the identity and farms all year);
- `Farmer`: good fixes to the cheapest fifth of listed issues, or to issues it files itself (`self_filed`, no
  funding); twin: good fixes to typical issues at the same expected effort;
- `Inflater`: good fixes to typical issues, its signal raised (twin: not raised);
- `Newcomer`: an honest solver's first year on a fresh identity (twin: the same solver, established).

    python3 -m pof.sim.openval.nodeposit [--seeds 40] [--jobs 15] [--only grid,rep,pot,...]

prints reports/open-validators-measured-v5.md's tables. No model call: verdicts are replayed from
data/judges/verdicts-v2.matrix.json (#160).
"""

from __future__ import annotations

import argparse
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from dataclasses import replace
from statistics import NormalDist, mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import contenders as C
from . import measured as M
from . import panels as D
from . import pricing as PR
from . import report as R
from . import sizing as Z
from .evidence import P0
from .net import ISSUE, T_RIVAL, Net, Sub
from .params import BPS, WEEK, WORLD, Params, World

T_IMPACT = 0x1A9AC7  # randomness tag: an issue's impact signal (its noise)
T_ND = 0x0DE905  # ...an actor's own draws (its times, the issues it sees, whether an honest fix is good)
T_AUTHOR = 0xA07403  # ...which of the repository's honest solvers wrote a world fix (the pledge gate, #251)
T_CONTENDER = 0xC0D7E5  # ...which contender seat posted an upheld test (ACTIVE_COUNTS "anyone")
INF = float("inf")
LOOK = 30  # the issues an actor sees when it picks one: a week's listings (`World.subs_week`)
TRIGGER = 625.0  # the long con cashes in once it may claim the largest bounty (`World.bounty_max`); fixed in advance
REP0 = 5_000.0  # the reputation a seller sells (about a year of an established honest solver's paid bounties)
FIND = 0.25  # ASSUMED: each active honest solver finds a failing test for a bad pass
N01 = NormalDist()


def _mu_sigma(w: World) -> Tuple[float, float]:
    return math.log(w.bounty_median), math.log(w.bounty_p90 / w.bounty_median) / 1.2815515655446004


def _normal(*keys: int) -> float:
    """A standard normal number bound to its keys (Box-Muller on two of `panels.u`'s uniforms)."""
    a = max(D.u(*keys, 0), 1e-12)
    return math.sqrt(-2 * math.log(a)) * math.cos(2 * math.pi * D.u(*keys, 1))


def cheap_limit(w: World = WORLD, share: float = 0.2) -> float:
    """The bounty below which the cheapest `share` of listed issues lie."""
    mu, sig = _mu_sigma(w)
    return math.exp(mu + sig * N01.inv_cdf(share))


def mean_bounty(w: World = WORLD, hi: float = INF) -> float:
    """The mean listed bounty (clipped at `bounty_max`), below `hi`: numerically, on 4,000 quantiles."""
    mu, sig = _mu_sigma(w)
    xs = [min(w.bounty_max, math.exp(mu + sig * N01.inv_cdf((i + 0.5) / 4000))) for i in range(4000)]
    xs = [x for x in xs if x <= hi]
    return mean(xs)


# ---------- the network with the three switches ----------

class NDNet(Net):
    """`Net` with reputation caps, the shared pot and the judges' fee (`Params.REP_CAP`, `POT`, `JUDGE_FEE`)."""
    NO_DEPOSIT_RULES = True

    def __init__(self, seed: int, p: Params, w: World, actors: Sequence[object] = (), **kw):
        self.rep: Dict[Tuple[str, str], float] = defaultdict(float)  # an identity's reputation
        self.open: Dict[Tuple[str, str], float] = defaultdict(float)  # ...and its open claims
        self.claims: Dict[int, Tuple[Tuple[str, str], float]] = {}
        self.meta: Dict[int, dict] = {}  # an actor's submission: identity, issue key, inflated, effort
        self.resets: Counter = Counter()  # reversals that reset an identity's reputation
        self.pot_fund: Dict[int, float] = defaultdict(float)  # each window's funding
        self.pot_units: Dict[int, Dict[Tuple[str, Optional[str]], float]] = defaultdict(lambda: defaultdict(float))
        self.pot_paid: Dict[str, float] = defaultdict(float)
        self.unit_values: List[float] = []
        self.carry = 0.0  # a window's undistributed funding (no units, or shares over a cap), to the next
        self.funding = 0.0
        self.cohort_fund = 0.0  # funding of the issues already settled (final or neglected): the unit's estimate
        self.units_cum = 0.0
        self.world_final = self.world_paid = 0
        self.neglected: List[Sub] = []
        self.effort_paid: Dict[str, float] = defaultdict(float)
        # #251 task 3.2, the pledge gate: each identity's last event that makes it active (and every such event)
        self.last_active: Dict[Tuple[str, str], float] = {}
        self.active_log: List[Tuple[float, Tuple[str, str]]] = []
        self.unfunded: Dict[int, float] = {}  # a world issue listed while the gate was shut: the pledge refused
        self.dispute_by: Dict[int, Tuple[str, str]] = {}  # whose test is pending against a pass
        super().__init__(seed, p, w, actors, **kw)
        if p.POT != "off":
            for i in range(self.n_windows()):
                self._at(min(w.horizon_h, (i + 1) * p.POT_WINDOW_WEEKS * WEEK), self._pot_close, i)

    # ----- identities and the cap -----

    def n_windows(self) -> int:
        return max(1, math.ceil(self.w.horizon_h / (self.p.POT_WINDOW_WEEKS * WEEK) - 1e-9))

    def window(self, t: float) -> int:
        return min(self.n_windows() - 1, int(t // (self.p.POT_WINDOW_WEEKS * WEEK)))

    def ident(self, sub: Sub) -> Optional[Tuple[str, str]]:
        m = self.meta.get(sub.sid)
        return (sub.party, m["ident"]) if sub.party and m and m.get("ident") is not None else None

    def cap(self, ident: Tuple[str, str]) -> float:
        if not self.p.REP_CAP:
            return INF
        return self.p.REP_BASE + self.p.REP_MULT * self.rep[ident]

    def room(self, ident: Tuple[str, str]) -> float:
        return self.cap(ident) - self.open[ident]

    def submit(self, t: float, bounty: float, good: bool, solver: str, party: Optional[str], tier: str = ISSUE,
               value: float = 0.0, parties=None, commitment=None, issue: Optional[int] = None,
               ident: Optional[str] = None, key: Optional[int] = None, inflate: bool = False,
               effort: float = 0.0) -> Sub:
        sub = super().submit(t, bounty, good, solver, party, tier, value, parties, commitment, issue)
        self.meta[sub.sid] = dict(ident=ident, key=key, inflate=inflate, effort=effort)
        return sub

    def fund(self, t: float, bounty: float) -> None:
        """An issue an actor works on is a listed issue: its funding enters the pot of the window it is listed in."""
        self.pot_fund[self.window(t)] += bounty
        self.funding += bounty
        self.cohort_fund += bounty

    # ----- the pledge gate (#251 task 3.2, launch design L6) -----

    def author(self, sub: Sub) -> Tuple[str, str]:
        """The honest solver of the repository who wrote a world fix: one of `World.rival_solvers` (at least one)."""
        return ("honest", f"h{int(D.u(self.seed, T_AUTHOR, sub.sid) * max(1, self.w.rival_solvers))}")

    def active_count(self, t: Optional[float] = None) -> int:
        t = self.t if t is None else t
        win = self.p.ACTIVE_WINDOW_WEEKS * WEEK + 1e-9
        return sum(1 for x in self.last_active.values() if t - x <= win)

    def locked(self) -> bool:
        """Pledges are refused now: the gate is on and fewer than ACTIVE_SOLVERS_MIN identities are active."""
        return self.p.ACTIVE_GATE and self.active_count() < self.p.ACTIVE_SOLVERS_MIN

    def _activate(self, idt: Optional[Tuple[str, str]]) -> None:
        if idt is not None:
            self.last_active[idt] = self.t
            self.active_log.append((self.t, idt))

    def open_spans(self) -> List[Tuple[float, float]]:
        """The spans of the year in which pledges were taken (at least ACTIVE_SOLVERS_MIN identities active), from every
        event that made an identity active."""
        win, hz = self.p.ACTIVE_WINDOW_WEEKS * WEEK, self.w.horizon_h
        edges: List[Tuple[float, int]] = []
        last: Dict[Tuple[str, str], Tuple[float, float]] = {}
        for t, idt in sorted(self.active_log):
            a, b = last.get(idt, (None, None))  # type: ignore[assignment]
            if a is not None and t <= b:
                last[idt] = (a, max(b, t + win))
                continue
            if a is not None:
                edges += [(a, 1), (b, -1)]
            last[idt] = (t, t + win)
        for a, b in last.values():
            edges += [(a, 1), (b, -1)]
        spans, n, start = [], 0, 0.0
        for t, d in sorted(edges, key=lambda e: (e[0], -e[1])):
            before, n = n, n + d
            if before < self.p.ACTIVE_SOLVERS_MIN <= n:
                start = t
            elif n < self.p.ACTIVE_SOLVERS_MIN <= before:
                if min(t, hz) > start:
                    spans.append((start, min(t, hz)))
        if n >= self.p.ACTIVE_SOLVERS_MIN and hz > start:
            spans.append((start, hz))
        return [(a, b) for a, b in spans if a < hz]

    def _disputes(self, sub: Sub, window: float) -> None:
        if not self.p.ACTIVE_GATE:
            super()._disputes(sub, window)
            return
        rt, n0 = self.stats["rival_tests"], self._n
        super()._disputes(sub, window)
        if self.stats["rival_tests"] > rt:  # the first of the honest solvers whose draw found the test
            i = next(i for i in range(self.w.rival_solvers) if D.u(self.seed, T_RIVAL, sub.sid, i) < self.w.rival_find)
            self.dispute_by[sub.sid] = ("honest", f"h{i}")
        elif self._n > n0 and self.p.ACTIVE_COUNTS == "anyone":  # a contender's test: one of the seats that failed it
            case = M.case_of(self, sub)
            flags = [x for x in self.w.evidence_by if not case[x]]
            if flags:
                self.dispute_by[sub.sid] = ("contender", flags[int(D.u(self.seed, T_CONTENDER, sub.sid) * len(flags))])

    # ----- the impact weight (#247 not built: a noisy signal of the issue's true impact, its bounty) -----

    def weight(self, sub: Sub) -> float:
        if self.p.POT != "impact":
            return 1.0
        m = self.meta.get(sub.sid) or {}
        key = m.get("key")
        key = sub.sid if key is None else key
        mu, sig = _mu_sigma(self.w)
        z = (math.log(max(sub.bounty, 0.01)) - mu) / sig
        rho = self.w.impact_corr
        x = rho * z + math.sqrt(max(0.0, 1 - rho * rho)) * _normal(self.seed, T_IMPACT, key)
        if m.get("inflate"):
            x += self.w.inflate_sd
        return math.exp(sig * x)

    def unit_estimate(self) -> float:
        """What a unit of weight is worth, as a solver reads it: the funding of the issues already settled over the
        weight they earned."""
        return self.cohort_fund / self.units_cum if self.units_cum > 0 else INF

    def _neglects(self, sub: Sub) -> bool:
        """An honest solver leaves an issue whose expected share is below its effort (`World.effort` of its bounty).
        From week 4, on the network's own pass rate and unit value so far."""
        if self.w.effort <= 0 or self.t < 4 * WEEK or self.world_final < 50 or self.units_cum <= 0:
            return False
        pg = self.world_paid / self.world_final
        return pg * self.unit_estimate() * self.weight(sub) < self.w.effort * sub.bounty

    # ----- events -----

    def _arrive(self, sub: Sub) -> None:
        if sub.tier == ISSUE:
            p = self.p
            if sub.party is None and p.ACTIVE_GATE and self.locked():  # the pledge is refused: its fix is unpaid
                self.unfunded[sub.sid] = sub.bounty
                self.stats["pledges_refused"] += 1
                sub.bounty = 0.0
            if sub.party is None:
                self.pot_fund[self.window(sub.t)] += sub.bounty
                self.funding += sub.bounty
                if p.POT != "off" and self._neglects(sub):
                    sub.state = "neglected"
                    self.neglected.append(sub)
                    self.cohort_fund += sub.bounty
                    self.stats["neglected"] += 1
                    return
            else:
                idt = self.ident(sub)
                if idt is not None and p.REP_CAP:
                    if self.open[idt] + sub.bounty > self.cap(idt) + 1e-6:
                        sub.state = "refused"
                        self.stats["rep_refused"] += 1
                        return
                    self.open[idt] += sub.bounty
                    self.claims[sub.sid] = (idt, sub.bounty)
                m = self.meta.get(sub.sid) or {}
                pa = self.parties[sub.party]
                if m.get("effort"):
                    pa.costs += m["effort"]
                    self.effort_paid[sub.party] += m["effort"]
                if m.get("inflate") and p.POT == "impact":
                    pa.costs += self.w.inflate_cost
                if p.JUDGE_FEE:
                    pa.costs += p.JUDGE_FEE
        super()._arrive(sub)

    def _bill(self, sub: Sub) -> None:
        if self.p.JUDGE_FEE and sub.tier == ISSUE:
            sub.billed = sub.charges  # the flat fee paid for its panels: no per-check charge
            return
        super()._bill(sub)

    def _finalize(self, sub: Sub, outcome: bool) -> None:
        pa = self.parties[sub.party] if sub.party else None
        before = pa.gains if pa is not None else 0.0
        super()._finalize(sub, outcome)
        if sub.tier != ISSUE:
            return
        c = self.claims.pop(sub.sid, None)
        if c is not None:
            self.open[c[0]] -= c[1]
        idt = self.ident(sub)
        if sub.party is None:
            self.world_final += 1
            self.world_paid += bool(outcome)
            self.cohort_fund += sub.bounty
        if self.p.ACTIVE_GATE:
            if outcome:
                self._activate(self.author(sub) if sub.party is None else idt)
            elif sub.by_evidence:
                self._activate((sub.disputer, "tests") if sub.disputer else self.dispute_by.get(sub.sid))
        pot = self.p.POT != "off"
        if outcome:
            if idt is not None:
                self.rep[idt] += sub.bounty
            if pot:
                if pa is not None:
                    pa.gains = before  # no bounty: a share of the window's pot instead
                x = self.weight(sub)
                self.pot_units[self.window(self.t)][(sub.party or "world", idt[1] if idt else None)] += x
                self.units_cum += x
        elif sub.reversed:
            if idt is not None:
                self.resets[idt] += 1
                if self.p.REP_ON_REVERSAL == "minus":
                    self.rep[idt] = max(0.0, self.rep[idt] - self.p.REP_LOSS_X * sub.bounty)
                else:
                    self.rep[idt] = 0.0
            if pot and sub.by_evidence:
                if sub.disputer:  # the reward of the bounty world, taken back: the fix's weight instead
                    self.parties[sub.disputer].gains -= self.p.EVIDENCE_REWARD_BPS * sub.bounty / BPS
                x = self.weight(sub)
                self.pot_units[self.window(self.t)][(sub.disputer or "disputers", None)] += x
                self.units_cum += x

    def _pot_close(self, i: int) -> None:
        fund = self.pot_fund[i] + self.carry
        self.carry = 0.0
        units = self.pot_units[i]
        tot = sum(units.values())
        if tot <= 0:
            self.carry = fund
            return
        u = fund / tot
        self.unit_values.append(u)
        for (owner, name), x in units.items():
            pay = u * x
            if self.p.REP_CAP and name is not None:  # a share of the pot is capped as a claim is
                cap = self.cap((owner, name))
                if pay > cap:
                    self.carry += pay - cap
                    self.stats["pot_capped"] += pay - cap
                    pay = cap
            self.pot_paid[owner] += pay
            if owner not in ("world", "disputers"):
                self.parties[owner].gains += pay

    def _tick(self) -> None:
        super()._tick()
        for sid, (idt, v) in list(self.claims.items()):
            s = self.subs.get(sid)
            if s is not None and s.state == "withdrawn":
                del self.claims[sid]
                self.open[idt] -= v


# ---------- the actors ----------

class NDActor(Z.OnMarket):
    """An actor of `per_week` slots a week, each at its own time (the same in its twin's run). At each slot it sees
    `LOOK` listed issues (the same in both runs) and picks one it may claim."""
    TAG = 0
    name = "nd-actor"
    party = "nd-actor"

    def __init__(self, honest: bool = False, w: World = WORLD, per_week: float = 5.0):
        super().__init__(honest, w)
        self.per_week = per_week
        self.subs: List[Sub] = []
        self.count: Counter = Counter()

    def setup(self, net: NDNet) -> None:  # type: ignore[override]
        super().setup(net)
        self.start(net)
        for i, t in enumerate(self.times(net, self.TAG, self.per_week)):
            net._at(t, self._slot, net, i)

    def _slot(self, net: NDNet, i: int) -> None:
        """A slot, unless the pledge gate is shut (#251): no issue may be funded, so no new claim starts."""
        if net.p.ACTIVE_GATE and net.locked():
            self.count["locked_slots"] += 1
            return
        self.slot(net, i)

    def start(self, net: NDNet) -> None:
        pass

    @staticmethod
    def times(net: NDNet, tag: int, per_week: float) -> List[float]:
        rng = random.Random(D.h(net.seed, T_ND, tag))
        t, out = 0.0, []
        while per_week > 0:
            t += rng.expovariate(per_week / WEEK)
            if t > net.w.horizon_h:
                break
            out.append(t)
        return out

    def seen(self, net: NDNet, tag: int, i: int, hi: float = INF) -> List[float]:
        """The `LOOK` issues listed around slot `i`, below `hi` (all of them drawn from the world's bounties)."""
        rng = random.Random(D.h(net.seed, T_ND, tag, i, 1))
        mu, sig = _mu_sigma(net.w)
        xs = [round(min(net.w.bounty_max, rng.lognormvariate(mu, sig)), 2) for _ in range(LOOK)]
        return [x for x in xs if x <= hi] if hi < INF else xs

    @staticmethod
    def pick(xs: Sequence[float], room: float, how: str, rng: random.Random) -> Optional[float]:
        ok = [x for x in xs if x <= room + 1e-9]
        if not ok:
            return None
        return max(ok) if how == "largest" else rng.choice(ok)

    def go(self, net: NDNet, bounty: float, good: bool, ident: Optional[str], key: int, issue: Optional[int] = None,
           inflate: bool = False, effort: bool = False) -> Sub:
        s = net.submit(net.t, bounty, good, self.name, self.party, issue=issue, ident=ident, key=key,
                       inflate=inflate, effort=net.w.effort * bounty if effort else 0.0)
        self.subs.append(s)
        self.count["submitted"] += 1
        return s

    def slot(self, net: NDNet, i: int) -> None:
        raise NotImplementedError


class BadFix(NDActor):
    """Bad fixes, 5 a week. `fresh`: each from a new identity (free identities: it takes the largest issue a new
    identity may claim); otherwise on one identity, a random issue it may claim (v4's solver). Twin: nothing."""
    TAG = 1
    name = party = "bad-fix solver"

    def __init__(self, honest: bool = False, w: World = WORLD, fresh: bool = False, how: str = ""):
        super().__init__(honest, w)
        self.fresh = fresh
        self.how = how or ("largest" if fresh else "random")

    def slot(self, net: NDNet, i: int) -> None:
        xs = self.seen(net, self.TAG, i)
        net.fund(net.t, xs[0])
        if self.honest:
            return
        ident = f"id{i}" if self.fresh else "id"
        b = self.pick(xs, net.room((self.party, ident)), self.how, random.Random(D.h(net.seed, T_ND, self.TAG, i, 2)))
        if b is None:
            self.count["skipped"] += 1
            return
        self.go(net, b, False, ident, 10_000_000 + i)


class Retrier(NDActor):
    """v4's retrier: bad fixes, 5 new issues a week, each tried up to `retry` + 1 times until one is paid (it is the
    only solver of its issues). One identity, or a fresh one each try (`fresh`). Twin: nothing."""
    TAG = 2
    name = party = "retrying solver"

    def __init__(self, honest: bool = False, w: World = WORLD, retry: int = 20, fresh: bool = False):
        super().__init__(honest, w)
        self.retry, self.fresh = retry, fresh
        self.live: List[Tuple[Sub, int, int]] = []  # (latest try, issue, tries)
        self.n = 0

    def ident(self) -> str:
        self.n += 1
        return f"id{self.n}" if self.fresh else "id"

    def slot(self, net: NDNet, i: int) -> None:
        xs = self.seen(net, self.TAG, i)
        net.fund(net.t, xs[0])
        if self.honest:
            return
        ident = self.ident()
        b = self.pick(xs, net.room((self.party, ident)), "random", random.Random(D.h(net.seed, T_ND, self.TAG, i, 2)))
        if b is None:
            self.count["skipped"] += 1
            return
        self.live.append((self.go(net, b, False, ident, 10_000_000 + i, issue=i), i, 1))

    def on_tick(self, net: NDNet) -> None:  # type: ignore[override]
        super().on_tick(net)
        keep = []
        used: Counter = Counter()  # claims made this tick, not yet arrived
        for s, i, n in self.live:
            if s.final is None and s.state not in ("withdrawn", "refused"):
                keep.append((s, i, n))
            elif not s.final and n <= self.retry:
                ident = self.ident()
                idt = (self.party, ident)
                if net.room(idt) - used[idt] >= s.bounty:
                    used[idt] += s.bounty
                    nxt = n + (s.state != "refused")  # a refused claim was never judged: not a try
                    keep.append((self.go(net, s.bounty, False, ident, 10_000_000 + i, issue=i), i, nxt))
                else:
                    keep.append((s, i, n))  # it waits until its identity may claim the issue again
                    self.count["waits"] += 1
        self.live = keep


class LongCon(NDActor):
    """Farms good fixes (each costs `World.effort` of its bounty to write) on one identity until it may claim
    `TRIGGER`, then submits bad fixes on the largest issues it may claim until a reversal resets its reputation, and
    farms again. Twin: farms all year."""
    TAG = 3
    name = party = "long con"

    def __init__(self, honest: bool = False, w: World = WORLD, trigger: float = TRIGGER):
        super().__init__(honest, w)
        self.trigger = trigger
        self.cashing = False

    def slot(self, net: NDNet, i: int) -> None:
        xs = self.seen(net, self.TAG, i)
        net.fund(net.t, xs[0])
        idt = (self.party, "id")
        rng = random.Random(D.h(net.seed, T_ND, self.TAG, i, 2))
        if self.cashing and net.resets[idt] > self.count["resets_seen"]:
            self.cashing = False
            self.count["resets_seen"] = net.resets[idt]
        if not self.honest and not self.cashing and net.cap(idt) >= self.trigger:
            self.cashing = True
            self.count["cash_ins"] += 1
            self.count["resets_seen"] = net.resets[idt]
        b = self.pick(xs, net.room(idt), "largest" if self.cashing else "random", rng)
        if b is None:
            self.count["skipped"] += 1
            return
        if self.cashing:
            self.go(net, b, False, "id", 10_000_000 + i)
            self.count["bad"] += 1
        else:
            self.go(net, b, True, "id", 10_000_000 + i, effort=True)


class RepSale(NDActor):
    """A reputation seller and its buyer, together. The buyer holds a bought identity of `rep0` and submits bad
    fixes on the largest issues it may claim until a reversal resets it; the seller farms on a fresh identity. Twin:
    the seller keeps the identity and farms on it all year; nobody buys."""
    TAG = 4
    name = party = "reputation sale"

    def __init__(self, honest: bool = False, w: World = WORLD, rep0: float = REP0):
        super().__init__(honest, w)
        self.rep0 = rep0
        self.done = False

    def start(self, net: NDNet) -> None:
        net.rep[(self.party, "bought")] = self.rep0
        for i, t in enumerate(self.times(net, self.TAG + 100, self.per_week)):
            net._at(t, self._buyer, net, i)

    def _buyer(self, net: NDNet, i: int) -> None:
        if net.p.ACTIVE_GATE and net.locked():
            self.count["locked_slots"] += 1
            return
        self.buyer(net, i)

    def slot(self, net: NDNet, i: int) -> None:  # the seller
        xs = self.seen(net, self.TAG, i)
        net.fund(net.t, xs[0])
        ident = "bought" if self.honest else "new"
        b = self.pick(xs, net.room((self.party, ident)), "random", random.Random(D.h(net.seed, T_ND, self.TAG, i, 2)))
        if b is None:
            self.count["skipped"] += 1
            return
        self.go(net, b, True, ident, 10_000_000 + i, effort=True)

    def buyer(self, net: NDNet, i: int) -> None:
        idt = (self.party, "bought")
        xs = self.seen(net, self.TAG + 100, i)
        net.fund(net.t, xs[0])  # the issues listed at its times are funded in both runs
        if self.honest or self.done or net.resets[idt]:
            self.done = not self.honest and bool(self.done or net.resets[idt])
            return
        b = self.pick(xs, net.room(idt), "largest", random.Random(D.h(net.seed, T_ND, self.TAG + 100, i, 2)))
        if b is None:
            self.count["skipped"] += 1
            return
        self.go(net, b, False, "bought", 20_000_000 + i)
        self.count["bad"] += 1


class Farmer(NDActor):
    """Good fixes to the cheapest fifth of listed issues (each costs `World.effort` of its bounty), 6 a week (v4:
    the cheapest fifth of 1,560 issues a year), outside the reputation cap (what is tested is the pot). `self_filed`: to issues it files itself,
    which nobody funds. Twin: good fixes to typical issues at the same expected effort."""
    TAG = 5
    name = party = "farmer"

    def __init__(self, honest: bool = False, w: World = WORLD, self_filed: bool = False, per_week: float = 6.0):
        rate = per_week * mean_bounty(w, cheap_limit(w)) / mean_bounty(w) if honest else per_week
        super().__init__(honest, w, rate)
        self.self_filed = self_filed

    def slot(self, net: NDNet, i: int) -> None:
        hi = INF if self.honest else cheap_limit(net.w)
        xs = self.seen(net, self.TAG + 10 * self.honest, i, hi)
        if not xs:
            return
        b = xs[0]
        if not (self.self_filed and not self.honest):
            net.fund(net.t, b)
        self.go(net, b, True, None, 30_000_000 + i + 1_000_000 * self.honest, effort=True)


class Inflater(NDActor):
    """Good fixes to typical issues, 5 a week, outside the reputation cap, its impact signal raised by
    `World.inflate_sd` at `World.inflate_cost` a fix. Twin: the same fixes, not raised."""
    TAG = 6
    name = party = "inflater"

    def slot(self, net: NDNet, i: int) -> None:
        b = self.seen(net, self.TAG, i)[0]
        net.fund(net.t, b)
        self.go(net, b, True, None, 40_000_000 + i, inflate=not self.honest, effort=True)


class Newcomer(NDActor):
    """An honest solver's year on a fresh identity (`rep0` 0) or an established one (`rep0` 5,000), 5 fixes a week
    (good with `World.good_share`, as the world's: its mistakes can be reversed and reset it), each costing
    `World.effort` of its bounty to write. It takes the issue it would have taken when it may claim it; otherwise
    that issue is turned away and it takes a random one it may claim. Twin: the same solver with no cap."""
    TAG = 7
    name = party = "newcomer"

    def __init__(self, honest: bool = False, w: World = WORLD, rep0: float = 0.0):
        super().__init__(honest, w)
        self.rep0 = rep0
        self.first: Dict[float, float] = {}

    def start(self, net: NDNet) -> None:
        net.rep[(self.party, "id")] = self.rep0

    def slot(self, net: NDNet, i: int) -> None:
        idt = (self.party, "id")
        if self.honest:  # the twin: no cap binds it (its claims carry no identity)
            idt = ("", "")
            net.rep[idt] = 1e15
        for x in (net.w.bounty_median, net.w.bounty_p90):
            if x not in self.first and net.cap(idt) >= x:
                self.first[x] = net.t / WEEK
        xs = self.seen(net, self.TAG, i)
        net.fund(net.t, xs[0])
        rng = random.Random(D.h(net.seed, T_ND, self.TAG, i, 2))
        good = rng.random() < net.w.good_share
        room = net.room(idt)
        self.count["wanted"] += 1
        self.count["wanted_value"] += xs[0]
        if xs[0] <= room:
            b: Optional[float] = xs[0]
        else:
            self.count["turned"] += 1
            self.count["turned_value"] += xs[0]
            b = self.pick(xs[1:], room, "random", rng)
        if b is None:
            self.count["skipped"] += 1
            return
        self.go(net, b, good, None if self.honest else "id", 50_000_000 + i, effort=True)


# ---------- running an actor against its twin ----------

def _health(net: NDNet, party: str) -> Dict[str, float]:
    """E2, per funded issue: the world's issues (the neglected ones included) and the actor's distinct issues."""
    world = [s for s in net.subs.values() if s.tier == ISSUE and s.party is None]
    mine = [s for s in net.subs.values() if s.tier == ISSUE and s.party == party]
    keys = {net.meta[s.sid]["key"] for s in mine}
    wrong = {net.meta[s.sid]["key"] for s in mine if s.final and not s.good}
    fixed = {net.meta[s.sid]["key"] for s in mine if s.final and s.good}
    return dict(h_n=len(world) + len(net.neglected), h_fixed=sum(1 for s in world if s.good and s.final),
                h_wrong=sum(1 for s in world if not s.good and s.final), a_n=len(keys), a_wrong=len(wrong),
                a_fixed=len(fixed), neglected=len(net.neglected),
                neglected_funding=100 * sum(s.bounty for s in net.neglected) / max(1.0, net.funding))


def party_metrics(net: NDNet, a: NDActor) -> Dict[str, float]:
    pa = net.parties[a.party]
    mine = [s for s in net.subs.values() if s.tier == ISSUE and s.party == a.party]
    m = dict(submitted=pa.submitted, paid=pa.paid, bad_paid=pa.bad_paid,
             good_paid=sum(1 for s in mine if s.final and s.good), refused=net.stats["rep_refused"],
             resets=sum(v for (p, _), v in net.resets.items() if p == a.party), effort=net.effort_paid[a.party],
             pot_paid=net.pot_paid.get(a.party, 0.0), unit=mean(net.unit_values) if net.unit_values else 0.0,
             world_pot=net.pot_paid.get("world", 0.0), funding=net.funding, rival_tests=net.stats["rival_tests"],
             passes=sum(1 for s in net.subs.values() if s.tier == ISSUE and s.verdict),
             disputers_pot=net.pot_paid.get("disputers", 0.0), ev_reversed=net.stats["evidence_reversed"],
             world_reward=sum(net.p.EVIDENCE_REWARD_BPS * s.bounty / BPS for s in net.subs.values()
                              if s.tier == ISSUE and s.by_evidence and s.disputer is None),
             **_health(net, a.party))
    m.update({k: float(v) for k, v in a.count.items()})
    if net.p.ACTIVE_GATE:
        m.update(gate_metrics(net))
    if isinstance(a, Newcomer):
        m["week_median"] = a.first.get(net.w.bounty_median, float("nan"))
        m["week_p90"] = a.first.get(net.w.bounty_p90, float("nan"))
        m["reached_median"] = 100.0 * (net.w.bounty_median in a.first)
    return m


def gate_metrics(net: NDNet) -> Dict[str, float]:
    """The pledge gate's year (#251): when pledges were first taken, the share of the year they were, how often the
    gate shut again, the pledges refused (and their funding), and the honest fixes left unpaid by it."""
    spans = net.open_spans()
    hz = net.w.horizon_h
    world = [s for s in net.subs.values() if s.tier == ISSUE and s.party is None]
    listed = sum(net.unfunded.get(s.sid, s.bounty) for s in world)
    lost = [s for s in world if s.sid in net.unfunded and s.final and s.good]
    first = spans[0][0] if spans else float("nan")
    return dict(gate_open_week=first / WEEK, gate_never=100.0 * (not spans),
                gate_open_share=100.0 * sum(b - a for a, b in spans) / hz,
                gate_shut_again=float(sum(1 for _, b in spans if b < hz - 1e-6)),
                pledges_refused=float(len(net.unfunded)),
                pledges_refused_after=float(sum(1 for sid in net.unfunded if spans and net.subs[sid].t > first)),
                funding_refused=100.0 * sum(net.unfunded.values()) / max(1.0, listed),
                honest_unpaid=float(len(lost)), honest_unpaid_value=sum(net.unfunded[s.sid] for s in lost),
                active_end=float(net.active_count(hz)), identities_active=float(len(net.last_active)))


def run(actor: NDActor, seed: int, p: Params) -> NDNet:
    return NDNet(seed, p, actor.world(), [actor]).run()  # type: ignore[return-value]


def against_twin(make: Callable[[bool], NDActor], seeds: Sequence[int], p: Params) -> Dict[str, object]:
    """`actors.against_twin` on `NDNet`."""
    diffs, att, twin, extra = [], [], [], {}
    for s in seeds:
        a, t = make(False), make(True)
        na, nt = run(a, s, p), run(t, s, p)
        ra, rt = na.party_net(a.party), nt.party_net(t.party)
        diffs.append(ra - rt)
        att.append(ra)
        twin.append(rt)
        for k, v in party_metrics(na, a).items():
            extra.setdefault(k, []).append(v)
        for k, v in party_metrics(nt, t).items():
            extra.setdefault(f"twin_{k}", []).append(v)
    m, se = mean(diffs), A._se(diffs)

    def avg(xs):
        xs = [x for x in xs if x == x]
        return mean(xs) if xs else float("nan")
    return {"diff": m, "se": se, "loses": m + 2 * se < 0, "attacker": mean(att), "twin": mean(twin),
            "diffs": diffs, **{k: avg(v) for k, v in extra.items()}}


# ---------- the judges' cost: what JUDGE_FEE is set to ----------

def world(pool: str, seat: str, n: int, find: float = FIND, **kw) -> World:
    """v4's primary world with one family registered and seated (28 validators, as v4's GPT-alone rows) and `n`
    active honest solvers searching every pass (each finds a failing test for a bad one with `find`: ASSUMED)."""
    return replace(Z.world(pool, seats=((seat, seat),), rival_solvers=n, rival_find=find if n else 0.0, **kw),
                   initial_active=28)


def panel_cost(net: NDNet) -> Dict[str, float]:
    """Every check the network paid for in the year (counted panels, audits, challenge and test panels), priced at
    the market's break-even service fee (`pricing.settle`: the fee at which the mean active validator nets zero) plus
    one judge's usage, per issue submission."""
    st = PR.settle(net)
    usage = net.w.usage_per_check
    checks = sum(v.acct.checks for v in net.reg.validators.values())
    checks += net.stats["test_panel_pay"] / (st["fee"] + usage) if net.stats["test_panel_pay"] else 0.0
    subs = net.stats["submitted"]
    return dict(break_even=st["break_even"], fee=st["fee"], checks_per_sub=checks / max(1, subs),
                cost=checks * (st["break_even"] + usage) / max(1, subs),
                charged=mean(s.charges for s in net.subs.values() if s.tier == ISSUE and s.party is None))


def _cost_job(job) -> Dict[str, float]:
    pool, seat, seed = job
    w = world(pool, seat, 3)
    return panel_cost(NDNet(seed, P0, w, [Z.OnMarket(w=w)]).run())  # type: ignore[arg-type]


COST_SEEDS = tuple(range(1, 11))


def judge_cost(seeds: Sequence[int] = COST_SEEDS, jobs: int = 1) -> Tuple[float, List[Tuple[str, str, Dict]]]:
    """JUDGE_FEE: the mean over both seats and both kinds of bad fix of `panel_cost`, rounded to the cent. Fixed
    before the grid is run, on seeds 1-10 of the base network with 3 active honest solvers."""
    jobs_ = [(pool, seat, s) for pool in ("hidden", "pbw") for seat in ("anthropic", "openai") for s in seeds]
    res = C._map(_cost_job, jobs_, jobs)
    rows = []
    for k, (pool, seat) in enumerate((pool, seat) for pool in ("hidden", "pbw") for seat in ("anthropic", "openai")):
        chunk = res[k * len(seeds):(k + 1) * len(seeds)]
        rows.append((pool, seat, {key: mean(r[key] for r in chunk) for key in chunk[0]}))
    return round(mean(r["cost"] for _, _, r in rows), 2), rows


JUDGE_FEE = 5.03  # `judge_cost()` on seeds 1-10 (2026-11-15): $0.53 break-even fee + $0.13 usage, 7.6 checks a submission


# ---------- the rows ----------

REP = dict(REP_CAP=True)
POT = dict(POT="impact")
FEE = dict(JUDGE_FEE=JUDGE_FEE)
COMBOS: Tuple[Tuple[str, dict], ...] = (
    ("none", {}), ("R", REP), ("P", POT), ("F", FEE), ("R+P", {**REP, **POT}), ("R+F", {**REP, **FEE}),
    ("P+F", {**POT, **FEE}), ("R+P+F", {**REP, **POT, **FEE}))
COMBO_NAMES = {"none": "no mechanism (v4's base, no deposit)", "R": "reputation cap", "P": "pot by impact",
               "F": "judges' fee"}
SEATS = (("anthropic", "Opus 5.5"), ("openai", "GPT-6.1"))
SOLVERS = (1, 3, 10)
POOLS = Z.POOLS
GRID_INFLATE_COST = 20.0  # ASSUMED in the grid: what raising one fix's signal by a standard deviation costs
ATTACKERS = {
    "B": "solver of bad fixes, one identity (twin: nothing)",
    "S": "free identities: a new identity for each bad fix, the largest issue it may claim (twin: nothing)",
    "T": "retrying solver, one identity, up to 21 tries an issue (twin: nothing)",
    "Tf": "retrying solver, a new identity each try (twin: nothing)",
    "L": "long con: farms, then cashes in until reset (twin: farms all year)",
    "RS": "reputation sale of 5,000, seller and buyer together (twin: the seller keeps it and farms)",
    "F": "farmer of the cheapest fifth (twin: typical issues, same effort)",
    "SF": "farmer filing its own issues, unfunded (twin: typical issues, same effort)",
    "I": "inflater, +1 SD of signal at $20 a fix (twin: does not inflate)",
}
GridRow = Tuple[str, str, str, int, str, str, World, Params]  # combo, seat, pool, n, attacker, label, world, params


def make(kind: str, w: World) -> Callable[[bool], NDActor]:
    return {"B": lambda h: BadFix(h, w), "S": lambda h: BadFix(h, w, fresh=True),
            "T": lambda h: Retrier(h, w), "Tf": lambda h: Retrier(h, w, fresh=True),
            "L": lambda h: LongCon(h, w), "RS": lambda h: RepSale(h, w), "F": lambda h: Farmer(h, w),
            "SF": lambda h: Farmer(h, w, self_filed=True), "I": lambda h: Inflater(h, w),
            "N": lambda h: Newcomer(h, w), "E": lambda h: Newcomer(h, w, rep0=REP0)}[kind]


def kinds(combo: str, pool: str) -> List[str]:
    rep, pot = "R" in combo.split("+"), "P" in combo.split("+")
    out = ["B", "S", "T"] + (["Tf", "L", "RS"] if rep else [])
    if pool == "hidden":  # the farmer and the inflater submit good fixes: the kind of bad fix doesn't matter
        out += ["F"] + (["SF", "I"] if pot else [])
    return out


def grid_rows() -> List[GridRow]:
    rows: List[GridRow] = []
    for combo, kw in COMBOS:
        p = replace(P0, **kw)
        for pool, _ in POOLS:
            for seat, _ in SEATS:
                for n in SOLVERS:
                    w = world(pool, seat, n, inflate_cost=GRID_INFLATE_COST)
                    for k in kinds(combo, pool):
                        rows.append((combo, seat, pool, n, k, "", w, p))
    return rows


def newcomer_rows() -> List[GridRow]:
    """An honest solver's year with no cap (the twin) beside the same solver on a fresh identity ("N") and on one of
    5,000 ("E", where the cap is on), in every combination."""
    rows: List[GridRow] = []
    for combo, kw in COMBOS:
        for seat, _ in SEATS:
            for n in SOLVERS:
                for k in ("N", "E") if "R" in combo.split("+") else ("N",):
                    rows.append((combo, seat, "hidden", n, k, "", world("hidden", seat, n), replace(P0, **kw)))
    return rows


REP_SWEEP: Tuple[Tuple[str, dict], ...] = tuple(
    [(f"base ${b:,.0f}, x{m:g}", dict(REP_BASE=float(b), REP_MULT=m)) for b in (25, 50, 100, 200)
     for m in (0.5, 1.0, 2.0)] + [("base $50, x1; a reversal takes 2 x its bounty off", dict(REP_ON_REVERSAL="minus"))])


def rep_rows() -> List[GridRow]:
    """The reputation rule's two numbers swept (alone, no fee, no pot), 3 active honest solvers, fixes the tests
    fail. The proposal, fixed before any run: base $50, x1, a reversal resets."""
    rows: List[GridRow] = []
    for label, kw in REP_SWEEP:
        p = replace(P0, REP_CAP=True, **kw)
        for seat, _ in SEATS:
            w = world("hidden", seat, 3)
            for k in ("B", "S", "T", "L", "RS", "N", "E"):
                rows.append(("R", seat, "hidden", 3, k, label, w, p))
    return rows


POT_SWEEP: Tuple[Tuple[str, str, float], ...] = (("equal units", "equal", 0.0),) + tuple(
    (f"impact, correlation {r:g}", "impact", r) for r in (0.3, 0.6, 0.9))
INFLATE_COSTS = (0.0, 5.0, 20.0, 50.0, 100.0)


def pot_rows() -> List[GridRow]:
    """The pot alone (no cap, no fee), 3 active honest solvers, fixes the tests fail: equal units and the impact
    weight at three assumed correlations; the inflater at five assumed costs."""
    rows: List[GridRow] = []
    for label, pot, rho in POT_SWEEP:
        p = replace(P0, POT=pot)
        for seat, _ in SEATS:
            w = world("hidden", seat, 3, impact_corr=rho)
            for k in ("B", "F", "SF", "N"):
                rows.append(("P", seat, "hidden", 3, k, label, w, p))
            if pot == "impact":
                for c in INFLATE_COSTS:
                    rows.append(("P", seat, "hidden", 3, "I", f"{label}; inflating costs ${c:g} a fix",
                                 replace(w, inflate_cost=c), p))
    return rows


SENS_FIND = (0.10, 0.50)


def sens_rows() -> List[GridRow]:
    """Sensitivity, fixed before the grid ran: the active honest solvers' find rate (ASSUMED 25 % in the grid) at 10 %
    and 50 %, with no mechanism and in the two combinations that hold the cap and the fee."""
    rows: List[GridRow] = []
    for combo, kw in COMBOS:
        if combo not in ("R+F", "R+P+F", "none"):
            continue
        p = replace(P0, **kw)
        for q in SENS_FIND:
            for pool, _ in POOLS:
                for seat, _ in SEATS:
                    for n in SOLVERS:
                        w = world(pool, seat, n, find=q, inflate_cost=GRID_INFLATE_COST)
                        for k in ("B", "S", "T") + (("Tf", "L", "RS") if "R" in combo else ()):
                            rows.append((combo, seat, pool, n, k, f"find {100 * q:.0f} %", w, p))
    return rows


MINUS = dict(REP_ON_REVERSAL="minus")


def minus_rows() -> List[GridRow]:
    """POST HOC (chosen after the reputation sweep was seen): the cap and the fee with a reversal taking 2 x its
    bounty off the reputation instead of resetting it, at every condition of the grid, with the honest solver."""
    rows: List[GridRow] = []
    p = replace(P0, **REP, **FEE, **MINUS)
    for pool, _ in POOLS:
        for seat, _ in SEATS:
            for n in SOLVERS:
                w = world(pool, seat, n)
                for k in ("B", "S", "T", "Tf", "L", "RS") + (("N", "E") if pool == "hidden" else ()):
                    rows.append(("R+F", seat, pool, n, k, "minus", w, p))
    return rows


HOLE_DEPOSITS = (500, 1_000, 2_500)


def deposit_rows() -> List[GridRow]:
    """POST HOC (added after the grid was seen): the holes the recommended combination (the cap with a reversal taking
    2 x its bounty off, and the judges' fee) leaves with one active honest solver, and the solver's deposit (D22, on
    hold) that would close each."""
    rows: List[GridRow] = []
    for dep in HOLE_DEPOSITS:
        p = replace(P0, SOLVER_DEPOSIT_BPS=dep, **REP, **FEE, **MINUS)
        for pool, _ in POOLS:
            for seat, _ in SEATS:
                w = world(pool, seat, 1)
                for k in ("B", "S", "T", "Tf", "L", "RS"):
                    rows.append(("R+F", seat, pool, 1, k, f"deposit {dep:,}", w, p))
    return rows


TABLES: Dict[str, Callable[[], List[GridRow]]] = {"grid": grid_rows, "newcomer": newcomer_rows, "rep": rep_rows,
                                                  "pot": pot_rows, "sens": sens_rows, "minus": minus_rows,
                                                  "deposit": deposit_rows}


def _job(job) -> Dict[str, object]:
    table, i, seed = job
    combo, seat, pool, n, k, label, w, p = TABLES[table]()[i]
    return against_twin(make(k, w), [seed], p)


def run_rows(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = TABLES[table]()
    res = C._map(_job, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    return [(rows[i], _gather(res[i * len(seeds):(i + 1) * len(seeds)])) for i in range(len(rows))]


def _gather(chunk: List[Dict[str, object]]) -> Dict[str, object]:
    """One row's seeds: the difference's mean and standard error, and every metric's values seed by seed."""
    diffs = [r["diffs"][0] for r in chunk]  # type: ignore[index]
    out: Dict[str, object] = {k: [r.get(k, float("nan")) for r in chunk] for k in chunk[0]
                              if k not in ("diffs", "diff", "se", "loses")}
    out.update(diff=mean(diffs), se=A._se(diffs), diffs=diffs)
    return out


def key_of(row: GridRow) -> str:
    combo, seat, pool, n, k, label, _, _ = row
    return "|".join((combo, seat, pool, str(n), k, label))


def main(argv=None) -> int:
    import json
    import time
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.nodeposit")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated: cost, " + ", ".join(TABLES))
    ap.add_argument("--out", default="", help="write each table's raw results to OUT/<table>.json")
    ap.add_argument("--render", default="", help="print the report's tables from the raw results in this folder")
    a = ap.parse_args(argv)
    if a.render:
        from .nodeposit_tables import render
        print(render(a.render))
        return 0
    seeds = list(range(1, a.seeds + 1))
    for name in [x for x in a.only.split(",") if x] or ["cost"] + list(TABLES):
        t0 = time.time()
        if name == "cost":
            fee, rows = judge_cost(jobs=a.jobs)
            data: object = {"fee": fee, "rows": rows}
        else:
            data = [(key_of(row), res) for row, res in run_rows(name, seeds, a.jobs)]
        if a.out:
            Path(a.out, f"{name}.json").write_text(json.dumps(data))
        print(f"{name}: done in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
