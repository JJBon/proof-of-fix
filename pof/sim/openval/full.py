"""Task 1.8 of #134: every open-validator scenario of the incentive-simulation delta, and its acceptance criteria.

    python3 -m pof.sim market validators --seeds 40     the full report (markdown): every section, then the criteria

What this module adds to the sections of phase 1 (`report`), proof levels (`levels`), pricing (`pricing`) and
scores (`scores`):
- "The k table compared": the k table against a fixed k of 3 (`FixedKNet`), on the same seeds;
- "The window's length": k = 1's challenge window varied, with the colluding lone validator against its twin;
- the key score rows re-run on the market fee (`pricing.Market`, wrapped by `scores.ScoredFee`), where a counted draw
  is worth more than phase 1's flat $0.05;
- `acceptance`: each criterion of "Acceptance criteria for open validators", met or not, with the number that
  decides it. Where the spec leaves a threshold unpublished, the row says so and gives the number measured.

`collect` runs everything once and `render` prints it, so the criteria read the same numbers as the tables.
`quick=True` runs one row per section on few seeds (the tests' reproducibility check), not a result to read.
Simulated only (rule 1): nothing here opens a connection, holds a key or moves money.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import levels as L
from . import panels as D
from . import pricing as PR
from . import report as R
from . import scores as SC
from .net import CONSTITUTION, ISSUE, Net
from .params import DAY, MONTH, PARAMS, WORLD, Params, World

# ---------- the k table compared ----------


class FixedKNet(Net):
    """The comparison's rule: every issue panel is exactly `k` (no table): a submission waits until k validators
    eligible for its bounty fit the caps, and bounties above `limit` wait. The window and the challenge panel are
    k's (CHALLENGE_WINDOW[k], CHALLENGE_K[k]). The constitution tier is unchanged."""

    def __init__(self, seed: int, p: Params = PARAMS, w: World = WORLD, k: int = 3, limit: float = 625.0, **kw):
        self.fixed_k, self.fixed_limit = k, limit
        super().__init__(seed, p, w, **kw)

    def plan(self, sub):
        if sub.tier == CONSTITUTION:
            return super().plan(sub)
        pool = self.eligible(sub)
        if len(pool) < self.fixed_k:
            return 0, None, "fewer than k eligible"
        if sub.bounty > self.fixed_limit:
            return 0, None, "above the limit"
        d = D.draw(self._seed(sub), pool, self.fixed_k, self.p, exact=True, epoch=self.reg.epoch)
        if not d.filled:
            return 0, None, "the caps"
        return d.k, d, ""


GROWN = replace(WORLD, initial_active=20, joins_week=0.5)  # levels.MATURE: the genesis and 20 active
SMALL = replace(WORLD, initial_active=4)  # the genesis and 4 active, a newcomer a week
K_NETWORKS: List[Tuple[str, World]] = [
    ("Growth from one validator", WORLD),
    ("Small: the genesis and 4 active", SMALL),
    ("Grown: the genesis and 20 active", GROWN),
]
K_RULES: List[Tuple[str, Optional[int]]] = [("k table (v3)", None), ("fixed k = 3, bounties to $625", 3)]


def _nan_mean(xs: Sequence[float]) -> float:
    xs = [x for x in xs if x == x]
    return mean(xs) if xs else float("nan")


def k_metrics(n: Net) -> Dict[str, float]:
    st = n.stats
    issue = [s for s in n.subs.values() if s.tier == ISSUE]
    paid = st["paid"]
    cost = sum(s.charges for s in issue) + st["audit_pay"] + st["challenge_pay"] + st["shadow_pool_spend"]
    month = [n.validator_net(v) / max(1e-9, (n.t - v.registered_at) / MONTH)
             for v in n.reg.validators.values() if v.active_at is not None]
    return {"bad": st["bad_merged"], "bad_per_100": 100 * st["bad_merged"] / max(1, paid), "paid": paid,
            "days": st["final_days"] / st["final"] if st["final"] else float("nan"),
            "waited": st["waited"] / max(1, st["submitted"]), "withdrawn": st["withdrawn"] / max(1, st["submitted"]),
            "cost": cost / paid if paid else float("nan"), "month": _nan_mean(month),
            "active": n.series[-1]["active"] if n.series else 0.0}


def k_table(seeds: Sequence[int], networks=None, p: Optional[Params] = None
            ) -> List[Tuple[str, str, Dict[str, List[float]]]]:
    p = p or PARAMS
    out = []
    for net_name, w in (networks if networks is not None else K_NETWORKS):
        for rule, k in K_RULES:
            ms: Dict[str, List[float]] = {}
            for s in seeds:
                n = (Net(s, p, w) if k is None else FixedKNet(s, p, w, k=k)).run()
                for key, v in k_metrics(n).items():
                    ms.setdefault(key, []).append(v)
            out.append((net_name, rule, ms))
    return out


def _ms(xs: Sequence[float], nd: int = 1, scale: float = 1.0, pre: str = "") -> str:
    xs = [x for x in xs if x == x]
    if not xs:
        return "–"
    return f"{pre}{scale * mean(xs):,.{nd}f} ± {2 * scale * A._se(xs):,.{nd}f}"


def k_table_md(seeds: Sequence[int], data) -> str:
    out = [f"### The k table compared ({len(seeds)} seeds; a year; 30 submissions a week; every validator at level A; "
           "the same seeds for both rules)", "",
           "| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that "
           "waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active "
           "at year's end |", "|---|---|---|---|---|---|---|---|---|---|"]
    for net_name, rule, m in data:
        out.append(f"| {net_name} | {rule} | {_ms(m['bad'])} ({_ms(m['bad_per_100'], 2)}) | {_ms(m['paid'], 0)} | "
                   f"{_ms(m['days'])} | {_ms(m['waited'], 0, 100)} % | {_ms(m['withdrawn'], 0, 100)} % | "
                   f"{_ms(m['cost'], 2, pre='$')} | {_ms(m['month'], 2, pre='$')} | {_ms(m['active'])} |")
    out += ["", "Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' "
            "usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with "
            "three validators, a 24-hour window and a challenge panel of 5. \"–\": nothing to measure (no "
            "verdict became final, or nothing was paid)."]
    return "\n".join(out)


# ---------- the window's length ----------

WINDOWS_H: Tuple[float, ...] = (24.0, 72.0, 168.0, 336.0, 720.0)  # the range tried: 1 to 30 days (unpublished)
COLLUDERS: List[Tuple[str, float]] = [("5 bad fixes a week", 5.0), ("1 bad fix a week", 1.0)]


def window_params(hours: float, p: Params = PARAMS) -> Params:
    """k = 1's window at level A set to `hours`; UNBONDING_DELAY follows it (CHALLENGE_WINDOW[1] + 7 days)."""
    cw = {lv: dict(x) for lv, x in p.CHALLENGE_WINDOW_H.items()}
    cw["A"][1] = hours
    return replace(p, CHALLENGE_WINDOW_H=cw, UNBONDING_DELAY_H=hours + 7 * DAY)


def windows(seeds: Sequence[int], hours: Sequence[float] = WINDOWS_H, colluders=None
            ) -> List[Tuple[str, float, Dict[str, List[float]]]]:
    """Per window and colluder, per run: its return − its twin's, the bad fixes it passed, how many were paid, how
    many reversed, and how many challenges were still frozen at the year's end."""
    out = []
    for label, rate in (colluders if colluders is not None else COLLUDERS):
        for hrs in hours:
            p = window_params(hrs)
            ms: Dict[str, List[float]] = {}
            for s in seeds:
                a, t = A.LoneColluder(False, bad_week=rate), A.LoneColluder(True, bad_week=rate)
                na, nt = A.run(a, s, p), A.run(t, s, p)
                mine = [x for x in na.subs.values() if x.party == a.party]
                passed = [x for x in mine if x.verdict]
                pa = na.parties.get(a.party)
                row = {"diff": na.party_net(a.party) - nt.party_net(t.party),
                       "passed": len(passed), "paid": pa.bad_paid if pa else 0,
                       "reversed": sum(1 for x in passed if x.reversed),
                       "frozen": sum(1 for x in mine if x.challenge is not None and x.challenge.state == "waiting"),
                       "qualified": na.stats["qualified"], "twin_qualified": nt.stats["qualified"]}
                row["loses"] = 1.0 if row["diff"] < 0 else 0.0
                row["none_paid"] = 1.0 if row["paid"] == 0 else 0.0
                row["caught_and_loses"] = row["loses"] * row["none_paid"]
                for k, v in row.items():
                    ms.setdefault(k, []).append(v)
            out.append((label, hrs, ms))
    return out


def shortest_window(data, label: str, share: float) -> Optional[float]:
    """The shortest window at which the colluder is caught (none of its bad fixes paid) and loses money in at least
    `share` of the runs; None if no window tried gets there."""
    rows = sorted((h, m) for lab, h, m in data if lab == label)
    return next((h for h, m in rows if mean(m["caught_and_loses"]) >= share - 1e-12), None)


def windows_md(seeds: Sequence[int], data) -> str:
    out = [f"### The window's length ({len(seeds)} seeds; a year; growth from one validator; the colluding genesis, "
           "bonded $100, against its honest twin; k = 1's window varied, `UNBONDING_DELAY` following it)", "",
           "| Colluder | k = 1's window | Return − twin's ($, ± 2 SE) | Runs it loses money | Runs none of its bad "
           "fixes is paid | Runs both (caught and loses) | Bad fixes passed / paid / reversed | Challenges still "
           "frozen at year's end | Newcomers qualified (twin's) |", "|---|---|---|---|---|---|---|---|---|"]
    for label, hrs, m in data:
        n = len(m["diff"])
        out.append(f"| {label} | {hrs:g} h | {mean(m['diff']):,.0f} ± {2 * A._se(m['diff']):,.0f} | "
                   f"{sum(m['loses']):.0f} of {n} | {sum(m['none_paid']):.0f} of {n} | "
                   f"{sum(m['caught_and_loses']):.0f} of {n} | {mean(m['passed']):.1f} / {mean(m['paid']):.1f} / "
                   f"{mean(m['reversed']):.1f} | {mean(m['frozen']):.1f} | {mean(m['qualified']):.1f} "
                   f"({mean(m['twin_qualified']):.1f}) |")
    out.append("")
    for label, _ in COLLUDERS:
        if not any(lab == label for lab, _, _ in data):
            continue
        any_run, all_runs = shortest_window(data, label, 1 / len(seeds)), shortest_window(data, label, 1.0)
        out.append(f"- **{label}:** the shortest window at which it is caught and loses money in at least one run: "
                   f"{f'{any_run:g} h' if any_run else 'none of those tried'}; in every run: "
                   f"{f'{all_runs:g} h' if all_runs else 'none of those tried'}. The spec's \"published share\" of "
                   "runs isn't published.")
    return "\n".join(out)


# ---------- the key score rows on the market fee ----------

SCORE_MARKET = replace(SC.SCORE_WORLD, initial_active=0, joins_week=0.0)  # the market brings its own validators
SCORE_MARKETS: List[Tuple[str, Params]] = [("design", PARAMS), ("moving", PR.MOVING)]


class ScoreMarket(PR.MarketMixin, A.Actor):
    """No attacker: the score families' network under market pricing, with D14 on (`mode` "pay") or off (None)."""
    name = "score market"
    party = "nobody"

    def __init__(self, honest: bool = True, mode: Optional[str] = "pay", p: Params = PARAMS):
        super().__init__(honest)
        self.mode, self.p = mode, p

    def world(self) -> World:
        return SCORE_MARKET

    def params(self) -> Params:
        return self.p

    def setup(self, net: Net) -> None:
        super().setup(net)  # the market first, so the score factor wraps the market's fee
        if self.mode is not None:
            SC.install(net, None if self.mode == "pay" else self.mode)


class MarketHerders(PR.MarketMixin, SC.Herders):
    """`scores.Herders` under market pricing: the market's 20 initial validators (five per family) and its
    prospects, the herders beside them."""
    name = "herders (priced)"

    def __init__(self, honest: bool = False, p: Params = PARAMS, **kw):
        super().__init__(honest, **kw)
        self.p = p

    def world(self) -> World:
        return SCORE_MARKET

    def params(self) -> Params:
        return self.p


def _market_fee(net: Net) -> float:
    return mean(r["fee"] for r in PR.market_of(net).series)


def market_compare(seeds: Sequence[int], markets=None) -> List[Tuple[str, str, Dict[str, List[float]]]]:
    out = []
    for market, p in (markets if markets is not None else SCORE_MARKETS):
        for rule, mode in (("One vote, no scores", None), ("**One vote, pay by score (v3's design)**", "pay")):
            rows = []
            for s in seeds:
                b = ScoreMarket(mode=mode, p=p)
                net = A.run(b, s)
                m = SC.market_metrics(net)
                m["fee"] = _market_fee(net)
                m["active"] = PR.settle(net)["active"]
                rows.append(m)
            out.append((market, rule, SC._avg(rows)))
    return out


def market_compare_md(seeds: Sequence[int], data) -> str:
    fams = SC.FAMILIES
    out = [f"### Scores on the market fee ({len(seeds)} seeds; a year; the score families' accuracies and blind "
           "spots; the market's 20 initial validators, five per family, and 2 prospects a week)", "",
           "| Market | Rule | Mean service fee | Active validators (last 13 weeks) | Bad fixes merged per 100 paid | "
           + " | ".join(f"`{f}` validator's net per month" for f in fams) + " |", "|---" * (5 + len(fams)) + "|"]
    for market, rule, m in data:
        out.append(f"| {market} | {rule} | {_ms(m['fee'], 3, pre='$')} | {_ms(m['active'])} | "
                   f"{_ms(m['bad_per_100'], 2)} | " + " | ".join(_ms(m[f'net_{f}'], 2, pre='$') for f in fams) + " |")
    out += ["", "Market \"design\": the design's values, the fee starting at the ceiling. \"moving\": no slash for an "
            "honest outage and `IDLE_HIGH` 50 % (the pricing section's world where the fee moves). The families are "
            "priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight "
            "model). Prospects decide to enter on the unscaled fee: they don't know their family's factor."]
    return "\n".join(out)


MARKET_HERDS: List[Tuple[str, str, str, bool, Params]] = [
    ("`mid` (90 %), not detectable, market at design values", "design", "mid", False, PARAMS),
    ("`weak` (68 %), not detectable, market at design values", "design", "weak", False, PARAMS),
    ("`mid` (90 %), not detectable, moving market", "moving", "mid", False, PR.MOVING),
    ("`weak` (68 %), not detectable, moving market", "moving", "weak", False, PR.MOVING),
]


def market_herders(seeds: Sequence[int], rows=None) -> List[Tuple[str, Dict[str, object]]]:
    out = []
    for name, _, fam, det, p in (rows if rows is not None else MARKET_HERDS):
        def make(h, fam=fam, det=det, p=p):
            return MarketHerders(h, p=p, family=fam, detectable=det)

        def metrics(net, a):
            return {**SC._herd_metrics(net, a), "fee": _market_fee(net)}
        out.append((name, SC.twins(make, seeds, metrics)))
    return out


def market_herders_md(seeds: Sequence[int], data) -> str:
    title = (f"### Herding on the market fee ({len(seeds)} seeds; a year; 4 herders of one family beside the market's "
             "validators; herding that a re-run can't detect, the upper bound)")
    out = [SC.herders_table(seeds, data=data, title=title), "",
           "Mean service fee in the herders' runs: " + "; ".join(
               f"{name.split(',')[0]} ({name.split(', ')[-1]}): ${mean(r['fee']):.3f}" for name, r in data) + "."]
    return "\n".join(out)


# ---------- everything once ----------

@dataclass(frozen=True)
class Plan:
    """Which rows each section runs: `FULL` (the report) or `QUICK` (one row per section, for the tests)."""
    attackers: list
    sensitivity: list
    sybil_sizes: Tuple[int, ...]
    audit_rates: Tuple[float, ...]
    k_networks: list
    windows: Tuple[float, ...]
    colluders: list
    level_networks: Optional[list]
    level_attackers: list
    settle: list
    series: bool
    pricing_attacks: list
    scores_extra: bool  # the families' scores, one vote against weighted votes, the movers
    herds: tuple
    score_markets: Optional[list]
    market_herds: list


FULL = Plan(R.ATTACKERS, R.SENSITIVITY, (3, 6, 10, 20), R.AUDIT_RATES, K_NETWORKS, WINDOWS_H, COLLUDERS, L.NETWORKS,
            L.ATTACKERS, PR.SETTLE_ROWS, True, PR.ATTACKS, True, SC.HERDS, SCORE_MARKETS, MARKET_HERDS)
QUICK = Plan([r for r in R.ATTACKERS if r[3] in ("colluder", "coalition")][:2], [], (10,), (PARAMS.AUDIT_RATE,),
             K_NETWORKS[2:], (72.0,), COLLUDERS[:1], None, L.ATTACKERS[:1], PR.SETTLE_ROWS[:1], False,
             PR.ATTACKS[:1], False, SC.HERDS[:1], None, MARKET_HERDS[:1])


def collect(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None, quick: bool = False) -> Dict[str, object]:
    """Every section's numbers, each computed once (seeds 1..N; the sybil and audit sweeps on `sweep`)."""
    pl = QUICK if quick else FULL
    sweep = sweep or seeds
    d: Dict[str, object] = {"seeds": list(seeds), "sweep": list(sweep), "plan": pl, "quick": quick}
    d["growth"] = R.growth_table(seeds)
    d["attackers"] = R.attackers(seeds, pl.attackers)
    d["sensitivity"] = R.attackers(seeds, pl.sensitivity) if pl.sensitivity else []
    d["sybil"] = R.sybil_shares(sweep, pl.sybil_sizes)
    d["watch_lazy"] = R.watchers(sweep, pl.audit_rates, "lazy")
    d["watch_bribed"] = R.watchers(sweep, pl.audit_rates, "bribed")
    d["k_table"] = k_table(seeds, pl.k_networks)
    d["windows"] = windows(seeds, pl.windows, pl.colluders)
    d["level_networks"] = L.networks_table(seeds) if pl.level_networks is not None else ""
    d["level_attackers"] = L.attackers(seeds, pl.level_attackers)
    d["settle"] = PR.settle_rows(seeds, pl.settle)
    d["series"] = ([PR.series_table(seeds, "the design's values", PARAMS),
                    PR.series_table(seeds, "no outage slash, `IDLE_HIGH` 50 %", PR.MOVING), PR.provider_table(seeds)]
                   if pl.series else [])
    d["pricing_attacks"] = PR.attacks(seeds, pl.pricing_attacks)
    d["scores_extra"] = ([SC.scores_table(seeds), SC.compare_table(seeds, SC.SCORE_WORLD, "; families with blind spots"),
                          SC.compare_table(seeds, SC.NO_BLIND, "; no blind spots: independent errors only"),
                          SC.movers_table(seeds)] if pl.scores_extra else [])
    d["herders"] = _herders(seeds, pl.herds)
    d["market_compare"] = market_compare(seeds, pl.score_markets) if pl.score_markets is not None else []
    d["market_herders"] = market_herders(seeds, pl.market_herds)
    return d


def _herders(seeds: Sequence[int], herds) -> List[Tuple[str, Dict[str, object]]]:
    """`scores.herders` over the rows `herds` (scores.HERDS or a part of it)."""
    out = []
    for name, f, det, fee in herds:
        w = SC.SCORE_WORLD if fee is None else replace(SC.SCORE_WORLD, service_fee=fee)
        out.append((name, SC.twins(lambda h, f=f, d=det, w=w: SC.Herders(h, family=f, detectable=d, w=w), seeds,
                                   SC._herd_metrics)))
    return out


# ---------- the acceptance criteria ----------

@dataclass(frozen=True)
class Criterion:
    name: str
    met: bool
    decides: str  # the number that decides it, and what's unpublished
    condition: str = ""  # "met only if ...": where the spec leaves the threshold unpublished

    @property
    def verdict(self) -> str:
        return ("met" if self.met else "not met") + (f" ({self.condition})" if self.condition else "")


def _loses(r: Dict[str, object]) -> bool:
    return r["diff"] + 2 * r["se"] < 0


def _pm(r: Dict[str, object]) -> str:
    return f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}"


def _against_twin(rows: List[Tuple[str, Dict[str, object]]]) -> Tuple[bool, str]:
    bad = [(n, r) for n, r in rows if not _loses(r)]
    if not bad:
        worst = max(rows, key=lambda x: x[1]["diff"] + 2 * x[1]["se"])
        return True, f"all {len(rows)} lose; the closest: {worst[0]} ({_pm(worst[1])} $)"
    return False, (f"{len(bad)} of {len(rows)} don't lose: "
                   + "; ".join(f"{n} ({_pm(r)} $)" for n, r in bad))


def _design_rows(d: Dict[str, object]):
    """The attacker rows run on the design's values (the counterfactuals and sensitivities aside)."""
    pl: Plan = d["plan"]  # type: ignore[assignment]
    p1 = [(row[0], r) for row, (_, r, _) in zip(pl.attackers, d["attackers"]) if row[2] is None]
    rate = PARAMS.AUDIT_RATE
    for kind in ("lazy", "bribed"):
        for vol, rt, r in d[f"watch_{kind}"]:
            if not vol and abs(rt - rate) < 1e-12:
                p1.append((f"D13's {kind} cheater (audits at {100 * rate:g} %, no volunteers)", r))
    lv = [(row[0], r) for row, (_, r, _) in zip(pl.level_attackers, d["level_attackers"])
          if row[2] is None and row[3] is L.majority_weakest]
    pr = [(row[0], r) for row, (_, _, r, _) in zip(pl.pricing_attacks, d["pricing_attacks"])
          if row[1] == "design" and not row[0].startswith("...")]
    sc = [(f"Herders: {n}", r) for n, r in d["herders"]] + [(f"Herders: {n}", r) for n, r in d["market_herders"]]
    return p1, lv, pr, sc


def acceptance(d: Dict[str, object]) -> List[Criterion]:
    """Each criterion of the incentive-simulation delta's "Acceptance criteria for open validators", from the run's
    numbers. "Loses" means the mean return − twin's plus two standard errors is below zero."""
    out: List[Criterion] = []
    p1, lv, pr, sc = _design_rows(d)
    for name, rows in (("Each open-validator attacker loses against its honest twin", p1),
                       ("Each pricing attacker loses against its honest twin", pr),
                       ("Each proof-level attacker loses against its honest twin", lv),
                       ("Each scoring attacker (the herders) loses against its honest twin", sc)):
        met, why = _against_twin(rows)
        out.append(Criterion(name, met, why))

    st = d["settle"][0][1]  # the design's values, the fee starting at the ceiling
    ceiling = PARAMS.FEE_CEILING
    near = ceiling * (1 - PARAMS.FEE_STEP)  # within one FEE_STEP of the ceiling, over the last 13 weeks
    at_ceiling = sum(1 for f in st["fee"] if f >= near - 1e-9)
    n = len(st["fee"])
    fee, marginal, be = mean(st["fee"]), _nan_mean(st.get("marginal", [])), _nan_mean(st.get("break_even", []))
    moved = at_ceiling < n
    out.append(Criterion(
        "The service fee settles within the published margin of validators' real cost", False,
        f"the margin isn't published. Measured (design values, from the ceiling): the fee over the last 13 weeks "
        f"${fee:.3f}, within one `FEE_STEP` of the ${ceiling:.2f} ceiling in {at_ceiling} of {n} runs; validators' "
        f"marginal cost "
        f"${marginal:.3f} a check ({fee / marginal:.1f} ×), break-even fee ${be:.3f}",
        "the fee " + ("moves, but no margin is published to judge it by" if moved else
                      "never leaves its ceiling, so it doesn't find the cost; validators' entry and exit make the cost "
                      "find the fee")))

    spread = sorted((100 * k / (k + 21), m) for k, s, m in d["sybil"] if s == "spread")
    one = sorted((100 * k / (k + 21), m) for k, s, m in d["sybil"] if s == "one host")
    clean = [sh for sh, m in spread if m["any_majority"] == 0]
    first_bad = next(((sh, m) for sh, m in spread if m["any_majority"] > 0), None)
    one_clean = all(m["any_majority"] == 0 for _, m in one)
    out.append(Criterion(
        "A sybil just under the published share never holds a majority of a panel of k ≥ 3, under the caps",
        bool(clean),
        "the share isn't published. Measured: a sybil spread over 3 hosts, TEE types and families "
        + (f"never holds one up to {max(clean):.0f} % of the validators" if clean else "holds one at every share tried")
        + (f", but does on {100 * first_bad[1]['any_majority']:.2f} % of panels at {first_bad[0]:.0f} %"
           if first_bad else "")
        + ("; one on a single host, TEE type and family never does, at any share tried (to "
           f"{max(sh for sh, _ in one):.0f} %)" if one and one_clean else ""),
        f"only if the published share is at most {max(clean):.0f} %" if clean else "at any share tried"))

    if first_bad:
        sh, m = first_bad
        out.append(Criterion(
            "A sybil at the published share: the report gives how often it holds a majority, what it passes, and how "
            "often it's caught", True,
            f"reported (the sybil tables). At {sh:.0f} %, spread: a majority on {100 * m['majority']:.1f} % of its own "
            f"panels and {100 * m['any_majority']:.2f} % of all panels of k ≥ 3, {m['bad_paid']:.1f} bad fixes paid, "
            f"{m['caught']:.1f} false verdicts proven in a year"))
    else:
        out.append(Criterion("A sybil at the published share: the report gives how often it holds a majority, what "
                             "it passes, and how often it's caught", True,
                             "reported (the sybil tables): no majority at any share tried"))

    w72 = [(lab, m) for lab, h, m in d["windows"] if abs(h - PARAMS.window_h(1)) < 1e-9]
    if w72:
        lab, m = w72[0]
        runs = len(m["none_paid"])
        caught = sum(m["none_paid"])
        passed, reversed_ = sum(m["passed"]), sum(m["reversed"])
        out.append(Criterion(
            "The colluding lone validator: each bad fix it passes is challenged and reversed before payment, in at "
            "least the published share of runs", caught == runs,
            f"the share isn't published. Measured (the genesis, {lab}, k = 1's 72-hour window): every bad fix "
            f"reversed before payment in {caught:.0f} of {runs} runs. Over the {runs} runs, {reversed_:.0f} of the "
            f"{passed:.0f} bad fixes it passed were reversed ({100 * reversed_ / max(1, passed):.0f} %); "
            f"{mean(m['paid']):.1f} were paid a run",
            "for any published share above 0" if caught == 0 else
            ("" if caught == runs else f"only if the published share is at most {100 * caught / runs:.0f} %")))

    coal = [(row[0], r) for row, (_, r, _) in zip(d["plan"].attackers, d["attackers"]) if row[3] == "coalition"]
    if coal:
        small = sum(r["adrs_small"] for _, r in coal)
        out.append(Criterion(
            "The constitution waits for the network: no ADR passes while fewer than K_MAX validators are eligible",
            small == 0,
            f"ADRs passed while fewer than K_MAX were eligible: {small:g} (mean a run, over "
            f"{' and '.join(n for n, _ in coal)})"))

    out.append(Criterion(
        "Every earlier criterion holds or is named", True,
        "named, not re-run: v3's simulation doesn't re-run v2's market, checking, token or split criteria. Their "
        "latest results are reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, "
        "tokens-v4.md and split-v1.md"))
    others = [c for c in out]
    failed = [c.name for c in others if not c.met]
    out.append(Criterion(
        "Adopt the k table, windows, bonds, caps and pricing bounds (all of the above)", not failed,
        f"{len(failed)} of {len(others)} criteria not met" if failed else "every criterion met"))
    return out


def acceptance_md(d: Dict[str, object]) -> str:
    seeds = d["seeds"]
    out = [f"### Acceptance criteria for open validators ({len(seeds)} seeds; sweeps on {len(d['sweep'])}; ± 2 "
           "standard errors)", "", "| Criterion | Verdict | What decides it |", "|---|---|---|"]
    for c in acceptance(d):
        out.append(f"| {c.name} | **{c.verdict}** | {c.decides} |")
    return "\n".join(out)


# ---------- the report ----------

def render(d: Dict[str, object]) -> str:
    seeds, sweep = d["seeds"], d["sweep"]
    head = (f"# Open validators: the full run ({len(seeds)} seeds; the sybil and audit sweeps on {len(sweep)})"
            + (" — QUICK: one row per section, for the tests" if d["quick"] else ""))
    parts = [head,
             "## Phase 1: growth, the attackers, the sybil's share, the watcher's dilemma", d["growth"],
             R.attackers_table(seeds, d["attackers"], d["sensitivity"]),
             R.sybil_table(sweep, d["sybil"]),
             R.watchers_table(sweep, "lazy", data=d["watch_lazy"]),
             R.watchers_table(sweep, "bribed", data=d["watch_bribed"]),
             "## The k table compared, and the window's length", k_table_md(seeds, d["k_table"]),
             windows_md(seeds, d["windows"]),
             "## Proof levels"] + ([d["level_networks"]] if d["level_networks"] else []) + [
             L.attackers_table(seeds, d["level_attackers"]),
             "## Market pricing", PR.settle_table(seeds, d["settle"])] + list(d["series"]) + [
             PR.attacks_table(seeds, d["pricing_attacks"]),
             "## Model scores"] + list(d["scores_extra"]) + [
             SC.herders_table(seeds, data=d["herders"]),
             "## Model scores on the market fee"] + (
             [market_compare_md(seeds, d["market_compare"])] if d["market_compare"] else []) + [
             market_herders_md(seeds, d["market_herders"]),
             "## Acceptance criteria", acceptance_md(d)]
    return "\n\n".join(parts)


def full_report(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None, quick: bool = False) -> str:
    return render(collect(seeds, sweep, quick))
