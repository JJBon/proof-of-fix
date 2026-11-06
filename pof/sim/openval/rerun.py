"""Task group 6 of #132 (proof-of-fix#141): the open-validator simulation re-run with #141's rules.

    python3 -m pof.sim market validators --seeds 40            this report (reports/open-validators-v2.md)
    python3 -m pof.sim market validators --seeds 40 --jobs 2   the same numbers, on two processes
    python3 -m pof.sim market validators --seeds 40 --v1       #134's report (reports/open-validators-v1.md), unchanged

#141's rules are `params.V2` (the defaults); #134's are `params.V1`. What this module adds to the sections of #134
(`report`, `levels`, `pricing`, `scores`, `full`), each run on V2:
- `SWITCHES`: each alternative #141 named, as a `Params` (and, for five TEE types, a world) that changes only the
  fields it names; every switch runs beside its rule on the same seeds;
- the new scenarios of the incentive-simulation delta: "An honest network grows under the hold", "The colluding
  genesis under the hold", "An honest validator's month", "A silent judge without a silence slash", "An early
  coalition", "A rule against its alternative" and "The TEE cap from k = 5";
- the owner's decision of 2026-11-03 (spec PR pending): level C is off at launch (`Params.C_ACCEPTED` False, the
  default) and switched on later by a constitution ADR; the merged design (C from genesis) is the switch "c_on", and
  the level C attackers run "after C is switched on by ADR" on a grown network;
- `acceptance`: every criterion of "Acceptance criteria for open validators", judged as D17 says ("How a criterion is
  judged": over seeds 1..N with two standard errors of the mean; a result that isn't significant fails), with the
  thresholds published in `Params` (SYBIL_SHARE, LONE_CATCH_SHARE, FEE_MARGIN, WAIT_CROWD_MAX, BORDERLINE_COUNTED).

`collect` runs every section once (`jobs` > 1: that many processes, one section each; the numbers don't change) and
`render` prints them, so the criteria read the same numbers as the tables. `quick=True` runs one row per section on
few seeds, for the tests: not a result to read. Simulated only (rule 1): nothing here opens a connection.
"""

from __future__ import annotations

import math
import multiprocessing
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, replace
from statistics import mean, median
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import full as F
from . import levels as L
from . import pricing as PR
from . import report as R
from . import scores as SC
from .net import CONSTITUTION, ISSUE, Net
from .params import DAY, MONTH, V1, V2, WORLD, Params, World, v1_fields
from .registry import RegistrationError

NAN = float("nan")
TEES5 = ("nitro", "tdx", "sev-snp", "cca", "ibm-se")  # five accepted TEE types (placeholders for the switch)
W_TEE5 = replace(WORLD, tees=TEES5)


# ---------- judging a criterion (design D17, "How a criterion is judged") ----------

def mean_se(xs: Sequence[float]) -> Tuple[float, float]:
    xs = [x for x in xs if x == x]
    if not xs:
        return NAN, NAN
    return mean(xs), A._se(xs)


def loses(m: float, se: float) -> bool:
    """"Loses against its honest twin": mean(attacker - twin) + 2 SE < 0. Not significant fails."""
    return m == m and m + 2 * se < 0


def at_most(m: float, se: float, x: float) -> bool:
    """"At most X": mean + 2 SE <= X."""
    return m == m and m + 2 * se <= x + 1e-12


def at_least(m: float, se: float, x: float) -> bool:
    """"At least X": mean - 2 SE >= X."""
    return m == m and m - 2 * se >= x - 1e-12


def pooled(num: Sequence[float], den: Sequence[float]) -> Tuple[float, float]:
    """A share pooled over the runs, sum(num) / sum(den), and its standard error (the ratio estimator, runs as the
    sampling unit)."""
    d = sum(den)
    if d <= 0:
        return NAN, NAN
    r = sum(num) / d
    n = len(den)
    if n < 2:
        return r, 0.0
    var = sum((x - r * y) ** 2 for x, y in zip(num, den)) / (n - 1)
    return r, math.sqrt(var / n) / (d / n)


def verdict(m: float, se: float) -> str:
    if m != m:
        return "–"
    if m + 2 * se < 0:
        return "loses"
    if m - 2 * se > 0:
        return "**wins**"
    return "not significant"


def _pm(m: float, se: float, nd: int = 0, pre: str = "") -> str:
    if m != m:
        return "–"
    return f"{pre}{m:+,.{nd}f} ± {2 * se:,.{nd}f}"


def _ms(xs: Sequence[float], nd: int = 1, scale: float = 1.0, pre: str = "", unit: str = "") -> str:
    m, se = mean_se(xs)
    if m != m:
        return "–"
    return f"{pre}{scale * m:,.{nd}f} ± {2 * scale * se:,.{nd}f}{unit}"


def _pct(x: float, nd: int = 0) -> str:
    return "–" if x != x else f"{100 * x:.{nd}f} %"


# ---------- the switches (task 6.2): each changes only what it names ----------

def window(hours: float, p: Params = V2) -> Params:
    """k = 1's window at level A set to `hours` (the network's level in phase 1's worlds); UNBONDING_DELAY follows:
    the longest window of any (k, level) + 7 days."""
    cw = {lv: dict(x) for lv, x in p.CHALLENGE_WINDOW_H.items()}
    cw["A"][1] = hours
    longest = max(h for lv in cw.values() for h in lv.values())
    return replace(p, CHALLENGE_WINDOW_H=cw, UNBONDING_DELAY_H=longest + 7 * DAY)


@dataclass(frozen=True)
class Switch:
    key: str
    label: str  # what it is, in the tables
    rule: str  # the #141 rule it is the alternative of
    p: Params
    names: Tuple[str, ...]  # the Params fields it names
    world: Optional[World] = None  # the world it names (five TEE types)


def _sw(key: str, label: str, rule: str, names: Tuple[str, ...], world: Optional[World] = None, **kw) -> Switch:
    return Switch(key, label, rule, replace(V2, **kw), names, world)


SWITCHES: Tuple[Switch, ...] = (
    _sw("k1_cap_5", "`K1_PENDING_MAX` 5", "`K1_PENDING_MAX` 10", ("K1_PENDING_MAX",), K1_PENDING_MAX=5),
    _sw("k1_cap_20", "`K1_PENDING_MAX` 20", "`K1_PENDING_MAX` 10", ("K1_PENDING_MAX",), K1_PENDING_MAX=20),
    _sw("k1_batch", "`K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties)", "`K1_PENDING_MAX` 10",
        ("K1_BATCH_BOND", "K1_PENDING_MAX"), K1_BATCH_BOND=True, K1_PENDING_MAX=None),
    Switch("k1_window_14", "k = 1's window 14 days", "k = 1's window 7 days (168 h at A)", window(336.0),
           ("CHALLENGE_WINDOW_H", "UNBONDING_DELAY_H")),
    Switch("k1_window_30", "k = 1's window 30 days", "k = 1's window 7 days (168 h at A)", window(720.0),
           ("CHALLENGE_WINDOW_H", "UNBONDING_DELAY_H")),
    _sw("sealed_050", "`SEALED_NO_REVEAL_SLASH` $0.50", "`SEALED_NO_REVEAL_SLASH` $1", ("SEALED_NO_REVEAL_SLASH",),
        SEALED_NO_REVEAL_SLASH=0.5),
    _sw("sealed_5", "`SEALED_NO_REVEAL_SLASH` $5", "`SEALED_NO_REVEAL_SLASH` $1", ("SEALED_NO_REVEAL_SLASH",),
        SEALED_NO_REVEAL_SLASH=5.0),
    _sw("silence_1", "`SILENCE_SLASH` $1", "no slash for silence", ("SILENCE_SLASH",), SILENCE_SLASH=1.0),
    _sw("const_21", "`CONSTITUTION_MIN_ELIGIBLE` 21", "`CONSTITUTION_MIN_ELIGIBLE` 14", ("CONSTITUTION_MIN_ELIGIBLE",),
        CONSTITUTION_MIN_ELIGIBLE=21),
    _sw("const_28", "`CONSTITUTION_MIN_ELIGIBLE` 28", "`CONSTITUTION_MIN_ELIGIBLE` 14", ("CONSTITUTION_MIN_ELIGIBLE",),
        CONSTITUTION_MIN_ELIGIBLE=28),
    _sw("idle_30", "`IDLE_HIGH` 30 %", "`IDLE_HIGH` 40 %", ("IDLE_HIGH",), IDLE_HIGH=0.30),
    _sw("idle_50", "`IDLE_HIGH` 50 %", "`IDLE_HIGH` 40 %", ("IDLE_HIGH",), IDLE_HIGH=0.50),
    _sw("idle_7d", "idling over 7 days (`IDLE_WINDOW_DAYS` 7)", "idling over one period", ("IDLE_WINDOW_DAYS",),
        IDLE_WINDOW_DAYS=7),
    _sw("wait_any", "waits a newcomer of any bond could end", "waits a floor-bond newcomer could end",
        ("WAIT_SIGNAL",), WAIT_SIGNAL="any"),
    _sw("step_up", "`FEE_STEP_UP` 10 %", "symmetric 5 % steps", ("FEE_STEP_UP",), FEE_STEP_UP=0.10),
    _sw("balanced", "`SCORE_BALANCED`", "agreement with outcomes", ("SCORE_BALANCED",), SCORE_BALANCED=True),
    _sw("median", "the factor's 1 × at the median family score", "the factor normalised to a mean of 1 ×",
        ("SCORE_FACTOR_RULE",), SCORE_FACTOR_RULE="median"),
    _sw("c_half", "`C_LIMIT_X` 0.5 (level C's limits halved)", "level C's limits as the k table", ("C_LIMIT_X",),
        C_LIMIT_X=0.5),
    _sw("tee5_from3", "five TEE types, the TEE cap from k = 3", "three TEE types, the TEE cap from k = 5",
        ("TEE_CAP_FROM_K",), world=W_TEE5, TEE_CAP_FROM_K=3),
    _sw("no_wait_shadows", "`SHADOW_PER_WAITING` 0", "`SHADOW_PER_WAITING` 3", ("SHADOW_PER_WAITING",),
        SHADOW_PER_WAITING=0),
    _sw("false_2000", "`FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity)", "the whole bond (10,000)",
        ("FALSE_VERDICT_SLASH_BPS",), FALSE_VERDICT_SLASH_BPS=2_000),
    _sw("c_on", "level C accepted from genesis (the merged design)",
        "level C off at launch (owner decision 2026-11-03, spec PR pending)", ("C_ACCEPTED",), C_ACCEPTED=True),
)
SW: Dict[str, Switch] = {s.key: s for s in SWITCHES}
TEE_FROM_3 = replace(V2, TEE_CAP_FROM_K=3)  # #134's TEE cap with three types (the "TEE cap from k = 5" scenario)
C_ON = SW["c_on"].p  # level C switched on (by ADR, on a grown network; or from genesis: the merged design)
AFTER_C = "after C is switched on by ADR"


def switch_fields(s: Switch) -> List[str]:
    """The Params fields a switch actually changes against #141's rules."""
    return v1_fields(s.p, V2)


# ---------- #134's published numbers (reports/open-validators-v1.md), beside each changed row ----------

V1_PUBLISHED: Dict[str, str] = {
    "sybil": "-1,494 ± 486", "sybil_one": "-2,122 ± 329", "colluder": "2,920 ± 456", "colluder_1": "196 ± 51",
    "grinder": "258 ± 79", "grinder_fixed": "1,306 ± 382", "silent": "-3,813 ± 123", "farmer": "-544 ± 3",
    "coalition_5": "5,196 ± 2,178", "coalition_3": "819 ± 450", "liar_genesis": "165 ± 13", "liar_grown": "-899 ± 102",
    "shopper_genesis": "301 ± 28", "shopper_3": "328 ± 69", "shopper_3_nofix": "1,209 ± 144", "shopper_1": "-2 ± 14",
    "breaker_genesis": "-102 ± 40", "breaker_genesis_50": "848 ± 40", "breaker_grown": "-3,220 ± 341",
    "breaker_grown_all": "-5,525 ± 449", "cartel": "-5,460 ± 335", "spam_wait": "-608 ± 19", "spam_judged": "-960 ± 43",
    "inflate": "42 ± 22", "inflate_small": "48 ± 28", "pfarmer": "-435 ± 9", "herd_mid_det": "-12,782 ± 828",
    "herd_mid": "-11 ± 31", "herd_weak_det": "-10,533 ± 1,144", "herd_weak": "-191 ± 53", "herd_mid_25": "-95 ± 30",
    "herd_weak_25": "-81 ± 49", "mherd_mid": "-123 ± 58", "mherd_weak": "-157 ± 57", "mherd_weak_moving": "294 ± 28",
    "waited": "68 % ± 6", "withdrawn": "64 % ± 6", "qualified": "18.2 ± 5.0", "qualify_days": "135.1 ± 20.6",
    "stepped": "39 % ± 9", "k3_week": "week 18 (40 of 40 runs)", "month_growth": "net **$-8.01**",
    "fee": "$0.250 ± 0.000", "break_even": "$0.251 ± 0.006", "collapsed_05": "28 of 40", "crowd": "11.6 ± 5.5 %",
    "bribed_5": "-34.4 ± 46.6", "bribed_10": "-136.9 ± 64.4", "fees_per_sub": "0.499 ± 0.003",
    "fees_flat": "0.358 ± 0.000", "caught_share": "1242 of the 6997", "month_market": "$-2.65 ± 0.51",
}


# ---------- growth from one validator, under the hold (and the TEE cap from k = 5) ----------

def one_tee_majority(n: Net, s) -> bool:
    """A panel of k >= 3 whose majority shares one TEE type: one vendor's flaw could decide it."""
    tees = Counter(n.reg.validators[vid].tee for vid, _, _ in s.judges)
    tees.pop("none", None)
    return bool(tees) and max(tees.values()) >= (s.k + 1) // 2


def growth_metrics(n: Net) -> Dict[str, object]:
    st = n.stats
    issue = [s for s in n.subs.values() if s.tier == ISSUE]
    pay = [(s.final_t - s.verdict_t) / DAY for s in issue if s.k == 1 and s.final]
    big = [s for s in issue if s.draw is not None and s.k >= 3 and s.judges]
    week3 = next((x["week"] for x in n.series if x["k_small"] >= 3), NAN)
    held = [s for s in issue if s.was_held]
    return {"k3": 0.0 if week3 != week3 else 1.0, "k3_week": week3, "pay_days": median(pay) if pay else NAN,
            "pay": pay, "k1": st["k1"] / max(1, st["drawn"]), "held": len(held) / max(1, st["k1"]),
            "held_days": mean(s.held_h / DAY for s in held) if held else NAN,
            "waited": st["waited"] / max(1, st["submitted"]), "withdrawn": st["withdrawn"] / max(1, st["submitted"]),
            "joined": st["joined"], "qualified": st["qualified"],
            "qualify_days": st["qualify_days"] / st["qualified"] if st["qualified"] else NAN,
            "pool": st["shadow_pool_spend"], "pool_wait": st["wait_shadow_spend"],
            "bad": 100 * st["bad_merged"] / max(1, st["paid"]), "active": n.series[-1]["active"] if n.series else 0.0,
            "stepped": st["stepped_down"] / max(1, st["drawn"]),
            "one_tee": sum(1 for s in big if one_tee_majority(n, s)) / max(1, len(big)),
            "one_tee_k3": (sum(1 for s in big if s.k == 3 and one_tee_majority(n, s))
                           / max(1, sum(1 for s in big if s.k == 3))),
            "final_days": st["final_days"] / max(1, st["final"]), "reversed": st["reversed"]}


def _collect_runs(rows: List[Dict[str, object]]) -> Dict[str, list]:
    out: Dict[str, list] = {}
    for r in rows:
        for k, v in r.items():
            if k == "pay":
                out.setdefault("pay_all", []).extend(v)  # type: ignore[arg-type]
            else:
                out.setdefault(k, []).append(v)
    return out


GROWTH_ROWS: List[Tuple[str, str, Params, World]] = [
    ("design", "**#141's rules (the design)**", V2, WORLD),
    ("k1_cap_5", SW["k1_cap_5"].label, SW["k1_cap_5"].p, WORLD),
    ("k1_cap_20", SW["k1_cap_20"].label, SW["k1_cap_20"].p, WORLD),
    ("k1_batch", SW["k1_batch"].label, SW["k1_batch"].p, WORLD),
    ("k1_window_14", SW["k1_window_14"].label, SW["k1_window_14"].p, WORLD),
    ("k1_window_30", SW["k1_window_30"].label, SW["k1_window_30"].p, WORLD),
    ("no_wait_shadows", SW["no_wait_shadows"].label, SW["no_wait_shadows"].p, WORLD),
    ("tee_from_3", "#134's TEE cap from k = 3, three TEE types", TEE_FROM_3, WORLD),
    ("tee5_from3", SW["tee5_from3"].label, SW["tee5_from3"].p, W_TEE5),
    ("v1", "#134's rules (v1)", V1, WORLD),
]


def s_growth(seeds, sweep, quick) -> Dict[str, object]:
    rows = GROWTH_ROWS[:1] if quick else GROWTH_ROWS
    out = []
    for key, label, p, w in rows:
        out.append((key, label, _collect_runs([growth_metrics(Net(s, p, w).run()) for s in seeds])))
    return {"rows": out, "weekly": R.growth_table(seeds, V2, WORLD)}


def _p90(xs: Sequence[float]) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else NAN


def md_growth(d, seeds) -> str:
    out = [d["weekly"].replace("### Growth from one validator", "### Growth from one validator under #141's rules", 1),
           "", f"#### An honest network grows under the hold ({len(seeds)} seeds; a year; growth from one validator, "
           "one newcomer a week, 30 submissions a week; each rule beside its alternatives, same seeds)", "",
           "| Rule | Runs where a small bounty reaches k ≥ 3 | First 4-week snapshot at k ≥ 3 | Days from a k = 1 "
           "verdict to payment: median a run (p90, all runs) | k = 1 verdicts held / days held | Submissions that "
           "waited / withdrawn | Newcomers qualified (of joined) / days to qualify | Sponsors' pool on shadows (on "
           "waiting submissions) | Bad fixes merged per 100 paid | Draws the caps lowered | Panels of k ≥ 3 (of 3) "
           "with one TEE type holding the majority | Active at year's end |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, m in d["rows"]:
        n = len(m["k3"])
        out.append(
            f"| {label} | {sum(m['k3']):.0f} of {n} | week {_ms(m['k3_week'], 0)} | {_ms(m['pay_days'], 1)} "
            f"({_p90(m.get('pay_all', [])):.1f}) | {_ms(m['held'], 0, 100, unit=' %')} / {_ms(m['held_days'], 1)} | "
            f"{_ms(m['waited'], 0, 100, unit=' %')} / {_ms(m['withdrawn'], 0, 100, unit=' %')} | "
            f"{_ms(m['qualified'], 1)} ({mean(m['joined']):.1f}) / {_ms(m['qualify_days'], 0)} | "
            f"${mean(m['pool']):,.0f} (${mean(m['pool_wait']):,.0f}) | {_ms(m['bad'], 2)} | "
            f"{_ms(m['stepped'], 0, 100, unit=' %')} | {_ms(m['one_tee'], 1, 100, unit=' %')} "
            f"({_ms(m['one_tee_k3'], 0, 100, unit=' %')}) | {_ms(m['active'], 1)} |")
    out += ["", "\"Days from a k = 1 verdict to payment\": over the k = 1 fixes paid in each run, the median a run "
            "(mean over runs ± 2 SE) and the 90th percentile over every run's paid k = 1 fixes. \"Held\": k = 1 "
            "verdicts whose window waited for CHALLENGE_K[1] eligible challengers, and the mean days they waited. "
            "#134's numbers: waited " + V1_PUBLISHED["waited"] + ", withdrawn " + V1_PUBLISHED["withdrawn"]
            + ", qualified " + V1_PUBLISHED["qualified"] + " after " + V1_PUBLISHED["qualify_days"]
            + " days, the caps lowered " + V1_PUBLISHED["stepped"] + " of draws; the last row reruns them."]
    return "\n".join(out)


# ---------- the attackers against their twins ----------

def attack_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = R._attack_metrics(net, a)
    m["k_shrank"] = float(any(k != c for k, c in net.k_seen))
    m["withheld"] = net.stats["withheld"]
    return m


ATTACK_ROWS: List[Tuple[str, str, Callable[[bool], A.Actor], Params, str, bool]] = [
    ("sybil", "Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families", lambda h: A.Sybil(h), V2,
     "sybil", True),
    ("sybil_one", "Sybil: 10 of 30 validators, one host, TEE type and family",
     lambda h: A.Sybil(h, hosts=1, tees=1, families=1), V2, "sybil", True),
    ("grinder", "Seed grinder (v3's seed: a later block)", lambda h: A.SeedGrinder(h), V2, "grinder", True),
    ("grinder_fixed", "Seed grinder (counterfactual: the seed fixed at the seal)", lambda h: A.SeedGrinder(h),
     replace(V2, SEED_FROM_LATER_BLOCK=False), "grinder", False),
    ("farmer", "Fee farmer (10 idle nodes at the bond floor; twin: one node)", lambda h: A.FeeFarmer(h), V2, "farmer",
     True),
    ("sybil_2000", "Sybil, spread, " + SW["false_2000"].label, lambda h: A.Sybil(h), SW["false_2000"].p, "sybil",
     False),
    ("grinder_2000", "Seed grinder, " + SW["false_2000"].label, lambda h: A.SeedGrinder(h), SW["false_2000"].p,
     "grinder", False),
]


def s_attackers(seeds, sweep, quick):
    rows = ATTACK_ROWS[2:3] if quick else ATTACK_ROWS
    return [(key, label, A.against_twin(make, seeds, p=p, metrics=attack_metrics), kind, counted)
            for key, label, make, p, kind, counted in rows]


def _row(label: str, r: Dict[str, object], v1key: Optional[str], got: str) -> str:
    v1 = V1_PUBLISHED.get(v1key or "", "–")
    return (f"| {label} | {_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | {r['attacker']:,.0f} | "
            f"{r['twin']:,.0f} | {v1} | {got} |")


ATTACK_HEAD = ["| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | "
               "#134's return − twin's (v1) | What it got |", "|---|---|---|---|---|---|---|"]


def md_attackers(d, seeds) -> str:
    out = [f"### Each attacker against its honest twin ({len(seeds)} seeds; a year; returns in $, with bonds' "
           "capital, running costs, fees, slashes, attempt fees and checks counted)", ""] + ATTACK_HEAD
    for key, label, r, kind, counted in d:
        out.append(_row(label, r, key if key in V1_PUBLISHED else None, R._got(kind, r)))
    out += ["", "The colluding genesis, the silent judge and the constitution coalition have their own tables below."]
    return "\n".join(out)


# ---------- the colluding genesis under the hold ----------

COLLUDER_ROWS: List[Tuple[str, str, Params, float]] = [
    ("design", "**#141's rules (the design)**, 5 bad fixes a week", V2, 5.0),
    ("k1_cap_5", SW["k1_cap_5"].label, SW["k1_cap_5"].p, 5.0),
    ("k1_cap_20", SW["k1_cap_20"].label, SW["k1_cap_20"].p, 5.0),
    ("k1_batch", SW["k1_batch"].label, SW["k1_batch"].p, 5.0),
    ("k1_window_14", SW["k1_window_14"].label, SW["k1_window_14"].p, 5.0),
    ("k1_window_30", SW["k1_window_30"].label, SW["k1_window_30"].p, 5.0),
    ("no_wait_shadows", SW["no_wait_shadows"].label, SW["no_wait_shadows"].p, 5.0),
    ("false_2000", SW["false_2000"].label, SW["false_2000"].p, 5.0),
    ("design_1", "#141's rules, 1 bad fix a week", V2, 1.0),
    ("v1", "#134's rules (v1), 5 bad fixes a week", V1, 5.0),
]


def colluder_run(s: int, p: Params, bad_week: float) -> Dict[str, object]:
    a, t = A.LoneColluder(False, bad_week=bad_week), A.LoneColluder(True, bad_week=bad_week)
    na, nt = A.run(a, s, p), A.run(t, s, p)
    mine = [x for x in na.subs.values() if x.party == a.party]
    passed = [x for x in mine if x.verdict]
    rev = sum(1 for x in passed if x.reversed)
    paid = sum(1 for x in passed if x.final)
    honest_pay = [(x.final_t - x.verdict_t) / DAY for x in na.subs.values()
                  if x.party is None and x.tier == ISSUE and x.k == 1 and x.final]
    return {"diff": na.party_net(a.party) - nt.party_net(t.party), "attacker": na.party_net(a.party),
            "twin": nt.party_net(t.party), "passed": len(passed), "reversed": rev, "paid": paid,
            "resolved": rev + paid, "pending": len(passed) - rev - paid,
            "held": sum(1 for x in mine if x.was_held), "submitted": len(mine),
            "frozen": sum(1 for x in mine if x.challenge is not None and x.challenge.state == "waiting"),
            "qualified": na.stats["qualified"], "twin_qualified": nt.stats["qualified"],
            "slashed": sum(v.acct.slashed for v in na.party_validators(a.party)),
            "honest_pay_days": median(honest_pay) if honest_pay else NAN}


def s_colluder(seeds, sweep, quick):
    rows = COLLUDER_ROWS[:1] if quick else COLLUDER_ROWS
    return [(key, label, _collect_runs([colluder_run(s, p, bw) for s in seeds])) for key, label, p, bw in rows]


def caught(m: Dict[str, list]) -> Tuple[float, float]:
    """LONE_CATCH_SHARE's number: of the bad fixes the colluder passed that reached an outcome (paid or reversed),
    the share reversed before any payment, pooled over the runs."""
    return pooled(m["reversed"], m["resolved"])


def md_colluder(d, seeds) -> str:
    out = [f"### The colluding genesis under the hold ({len(seeds)} seeds; a year; growth from one validator; the "
           "genesis, bonded $100, passes its accomplice's bad fixes at k = 1; against its honest twin)", "",
           "| Rule | Return − twin's ($, ± 2 SE) | Against its twin | Bad fixes passed / reversed / paid / still "
           "pending | Reversed before payment, pooled (± 2 SE) | Its verdicts held | Challenges still frozen | "
           "Newcomers qualified (twin's) | Slashed |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label, m in d:
        dm, dse = mean_se(m["diff"])
        c, cse = caught(m)
        out.append(f"| {label} | {_pm(dm, dse)} | {verdict(dm, dse)} | {mean(m['passed']):.1f} / "
                   f"{mean(m['reversed']):.1f} / {mean(m['paid']):.1f} / {mean(m['pending']):.1f} | "
                   f"{_pct(c, 1)} ± {_pct(2 * cse, 1) if cse == cse else '–'} | {mean(m['held']):.1f} | "
                   f"{mean(m['frozen']):.1f} | {mean(m['qualified']):.1f} ({mean(m['twin_qualified']):.1f}) | "
                   f"${mean(m['slashed']):,.0f} |")
    out += ["", "#134 (k = 1's 72-hour window, 20 % slash, no hold): " + V1_PUBLISHED["colluder"]
            + " $, " + V1_PUBLISHED["caught_share"] + " bad fixes it passed reversed (18 %); the last row reruns "
            "it. \"Reversed before payment\" counts the passed bad fixes that reached an outcome by the year's end; "
            "\"still pending\" ones (held or in their window at the year's end) are neither."]
    return "\n".join(out)


# ---------- the sybil's share and the watcher's dilemma ----------

SYBIL_SIZES = (3, 6, 10, 20)


def s_sybil(seeds, sweep, quick):
    return R.sybil_shares(sweep, (3,) if quick else SYBIL_SIZES, p=V2)


def md_sybil(d, sweep) -> str:
    text = R.sybil_table(sweep, d)
    return text.replace("| Sybil validators (share at the start) |", "| Sybil validators (share of the eligible) |")


def s_watch(seeds, sweep, quick):
    rates = (V2.AUDIT_RATE,) if quick else R.AUDIT_RATES
    return {"lazy": R.watchers(sweep, rates, "lazy", base=V2), "bribed": R.watchers(sweep, rates, "bribed", base=V2)}


# ---------- an early coalition ----------

def const_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    p = net.p
    mine = [s for s in net.subs.values() if s.party == a.party and s.tier == CONSTITUTION]
    passed = [s for s in mine if s.final]
    return {"submitted": len(mine), "passed": len(passed), "judged": sum(1 for s in mine if s.draw is not None),
            "expired": sum(1 for s in mine if s.state == "expired"),
            "below_min": sum(1 for s in passed if len(s.draw.pool) < p.CONSTITUTION_MIN_ELIGIBLE),
            "below_14": sum(1 for s in passed if len(s.draw.pool) < 2 * p.K_MAX),
            "first_judged": min([s.drawn_t / DAY for s in mine if s.drawn_t is not None], default=365.0)}


CONST_ROWS: List[Tuple[str, str, int, Params]] = [
    (f"c{n}_{thr}", f"{n} early validators, `CONSTITUTION_MIN_ELIGIBLE` {thr}" + (" (the design)" if thr == 14 else ""),
     n, replace(V2, CONSTITUTION_MIN_ELIGIBLE=thr)) for n in (5, 3) for thr in (14, 21, 28)
] + [(f"c{n}_v1", f"{n} early validators, #134's rule (`K_MAX` eligible, ADRs wait)", n, V1) for n in (5, 3)]


def s_constitution(seeds, sweep, quick):
    rows = CONST_ROWS[:1] if quick else CONST_ROWS
    return [(key, label, A.against_twin(lambda h, n=n: A.ConstitutionCoalition(h, nodes=n), seeds, p=p,
                                        metrics=const_metrics)) for key, label, n, p in rows]


def md_constitution(d, seeds) -> str:
    out = [f"### An early coalition ({len(seeds)} seeds; a year; growth from one validator; the coalition registers "
           "its validators at the start and submits an ADR worth $1,000 to it each week; its validators pass them)",
           "", "| Coalition and rule | Return − twin's ($, ± 2 SE) | Against its twin | ADRs submitted / expired / "
           "judged / passed | Passed while fewer than the threshold were eligible (all runs) | Passed while fewer "
           "than 2 × `K_MAX` (14) were eligible (all runs) | First ADR judged (day; 365: none) | #134 (v1) |",
           "|---|---|---|---|---|---|---|---|"]
    for key, label, r in d:
        n = len(r["diffs"])
        v1 = V1_PUBLISHED.get("coalition_" + key[1], "–") if key.endswith("v1") else "–"
        out.append(f"| {label} | {_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | {r['submitted']:.0f} / "
                   f"{r['expired']:.1f} / {r['judged']:.1f} / {r['passed']:.2f} | {r['below_min'] * n:.0f} | "
                   f"{r['below_14'] * n:.0f} | {r['first_judged']:.0f} | {v1} |")
    return "\n".join(out)


# ---------- a silent judge without a silence slash; the sealed-vote slash ----------

SILENT_ROWS: List[Tuple[str, str, Callable[[bool], A.Actor], Params, bool]] = [
    ("silent", "**Silent (never seals), the design: no slash for silence**", lambda h: A.SilentJudge(h), V2, True),
    ("silence_1", "Silent, " + SW["silence_1"].label, lambda h: A.SilentJudge(h), SW["silence_1"].p, False),
    ("withhold_1", "**Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $1 (the design)**",
     lambda h: A.SilentJudge(h, sealed=True), V2, True),
    ("withhold_050", "Seals, then withholds: " + SW["sealed_050"].label, lambda h: A.SilentJudge(h, sealed=True),
     SW["sealed_050"].p, False),
    ("withhold_5", "Seals, then withholds: " + SW["sealed_5"].label, lambda h: A.SilentJudge(h, sealed=True),
     SW["sealed_5"].p, False),
    ("silent_v1", "Silent, #134's rules (5 % of the bond a miss)", lambda h: A.SilentJudge(h), V1, False),
]


def s_silent(seeds, sweep, quick):
    rows = SILENT_ROWS[:1] if quick else SILENT_ROWS
    return [(key, label, A.against_twin(make, seeds, p=p, metrics=attack_metrics), counted)
            for key, label, make, p, counted in rows]


def md_silent(d, seeds) -> str:
    out = [f"### A silent judge without a silence slash ({len(seeds)} seeds; a year; a grown network of 12 honest "
           "validators; bribed 5 % of the bounty on 10 % of its draws)", "",
           "| Judge and rule | Return − twin's ($, ± 2 SE) | Against its twin | Bribed misses / suspended | Slashed | "
           "k ever shrank | #134 (v1) |", "|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d:
        out.append(f"| {label} | {_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | {r['silences']:.1f} / "
                   f"{r['suspensions']:.1f} | ${r['slashed']:,.2f} | {'yes' if r['k_shrank'] else 'never'} | "
                   f"{V1_PUBLISHED['silent'] if key == 'silent_v1' else '–'} |")
    return "\n".join(out)


# ---------- the k table compared ----------

def s_ktable(seeds, sweep, quick):
    return F.k_table(seeds, F.K_NETWORKS[2:] if quick else None, p=V2)


# ---------- proof levels, and the owner's option: level C not accepted at launch ----------

LW = L.LEVEL_WORLD
LEVEL_NETWORKS: List[Tuple[str, Params, World, L.LevelWorld]] = [
    ("Growth, all level A", V2, WORLD, replace(LW, mix=(1.0, 0.0, 0.0))),
    ("Growth at launch: genesis A, newcomers ⅓ A, ⅓ B, ⅓ C, **the C third refused (level C off)**", V2, WORLD, LW),
    ("Growth at launch, the same with 10 % hidden-test bounties", V2, WORLD, replace(LW, hidden_share=0.1)),
    (f"Grown, {AFTER_C}: 21 active, ⅓ A, ⅓ B, ⅓ C", C_ON, L.MATURE, LW),
    (f"Grown, {AFTER_C}: the same with 10 % hidden-test bounties", C_ON, L.MATURE, replace(LW, hidden_share=0.1)),
    (f"Grown, {AFTER_C}: the genesis at A, 20 active at C", C_ON, L.MATURE,
     replace(LW, mix=(0.0, 0.0, 1.0), genesis_level="A")),
]


def refused(p: Params, w: World, lw: L.LevelWorld) -> str:
    try:
        L.LevelNet(1, p, replace(w, weeks=0), (), lw=lw)
    except RegistrationError as e:
        return str(e)
    return ""


def s_level_networks(seeds, sweep, quick):
    rows = LEVEL_NETWORKS[1:2] if quick else LEVEL_NETWORKS
    return {"rows": [L.networks(seeds, [(name, w, lw)], p=p)[0] for name, p, w, lw in rows],
            "c_genesis": refused(C_ON, WORLD, replace(LW, mix=(0.0, 0.0, 1.0), genesis_level="C"))}


def md_level_networks(d, seeds) -> str:
    out = [f"### Panels by proof level ({len(seeds)} seeds; a year; 30 submissions a week)", "",
           "| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C "
           "| Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | "
           "Active at year's end |", "|---|---|---|---|---|---|---|---|---|---|"]
    hidden = []
    for name, ms in d["rows"]:
        lv = " / ".join(f"{100 * mean(ms[f'lv{x}']):.0f} %" for x in "ABC") if ms.get("lvA") else "–"
        days = " / ".join(f"{mean(ms[f'days{x}']):.1f}" if ms.get(f"days{x}") else "–" for x in "ABC")
        out.append(f"| {name} | {L._pct(ms['waited'])} | {L._pct(ms['withdrawn'])} | {L._pct(ms['level_wait'])} | "
                   f"{L._ms(ms['drawn'], 0)} | {lv} | {days} | {L._ms(ms['bad'], 2)} | ${mean(ms['max_bounty']):,.0f} "
                   f"| {L._ms(ms['active'])} |")
        if ms.get("hidden_waited"):
            hidden.append(f"| {name} | {L._pct(ms['hidden_waited'])} | {L._pct(ms['hidden_withdrawn'])} | "
                          f"{sum(ms['hidden_c_seen']):g} |")
    if d["c_genesis"]:
        out.append(f"| Growth, ordinary PCs only (genesis at C, even with C accepted) | refused at deployment: "
                   f"{d['c_genesis']} | | | | | | | | |")
    out += ["", "| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, "
            "replacement or shadow; all runs) |", "|---|---|---|---|"] + hidden
    return "\n".join(out)


C_HALF_ON = replace(C_ON, C_LIMIT_X=0.5)
LEVEL_ATTACKERS: List[Tuple[str, str, Callable[[bool], L.LevelActor], Params, str, bool]] = [
    ("liar_genesis", "Test liar: the genesis at C, 5 bad fixes a week (even with C accepted)",
     lambda h: L.TestLiar(h), C_ON, "liar", True),
    ("liar_grown", f"Test liar, {AFTER_C}: 1 of 15, every other validator at C but the genesis (A); 2 bad fixes "
     "a week", lambda h: L.TestLiar(h, "grown"), C_ON, "liar", True),
    ("liar_grown_c_half", "Test liar: the same, " + SW["c_half"].label, lambda h: L.TestLiar(h, "grown"), C_HALF_ON,
     "liar", False),
    ("shopper_genesis", "Answer shopper: the genesis at C (even with C accepted)",
     lambda h: L.AnswerShopper(h, twin_submits=True), C_ON, "shopper", True),
    ("shopper_1", f"**Answer shopper, {AFTER_C}: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 "
     "(counted; twin: calls once, same fixes)**",
     lambda h: L.AnswerShopper(h, "grown", borderline_pass=0.1, twin_submits=True), C_ON, "shopper", True),
    ("shopper_3", "Answer shopper: the same at 3 in 10 (the trust point; twin: calls once, same fixes)",
     lambda h: L.AnswerShopper(h, "grown", twin_submits=True), C_ON, "shopper", False),
    ("shopper_3_nofix", "Answer shopper: 3 in 10 (twin: no fixes)", lambda h: L.AnswerShopper(h, "grown"), C_ON,
     "shopper", False),
    ("shopper_1_c_half", "Answer shopper: 1 in 10, " + SW["c_half"].label,
     lambda h: L.AnswerShopper(h, "grown", borderline_pass=0.1, twin_submits=True), C_HALF_ON, "shopper", False),
    ("shopper_3_c_half", "Answer shopper: 3 in 10, " + SW["c_half"].label,
     lambda h: L.AnswerShopper(h, "grown", twin_submits=True), C_HALF_ON, "shopper", False),
    ("breaker_genesis", "Chip breaker at launch: the genesis at B ($25 at k = 1, 336 h), forging on half its bad-fix "
     "draws, $1,000 device", lambda h: L.ChipBreaker(h), V2, "breaker", True),
    ("breaker_genesis_50", "Chip breaker at launch: the same, a $50 device", lambda h: L.ChipBreaker(h, break_cost=50.0),
     V2, "breaker", True),
    ("breaker_grown", "Chip breaker at launch: 1 of a grown network (⅓ A, ⅓ B; the ⅓ at C refused), a $50 device",
     lambda h: L.ChipBreaker(h, "grown", break_cost=50.0), V2, "breaker", True),
    ("breaker_grown_all", "Chip breaker at launch: the same, forging on every bad-fix draw",
     lambda h: L.ChipBreaker(h, "grown", rate=1.0, break_cost=50.0), V2, "breaker", True),
    ("breaker_grown_on", f"Chip breaker, {AFTER_C}: 1 of 15 (⅓ A, ⅓ B, ⅓ C), a $50 device",
     lambda h: L.ChipBreaker(h, "grown", break_cost=50.0), C_ON, "breaker", True),
]


def level_twin(make, seeds, p: Params, lw: Optional[L.LevelWorld] = None) -> Dict[str, object]:
    """`levels.against_twin`, or {"refused": why} when the deployment or the registration is refused."""
    try:
        return L.against_twin(make, seeds, p=p, lw=lw, metrics=L.attack_metrics)
    except RegistrationError as e:
        return {"refused": str(e)}


def s_level_attackers(seeds, sweep, quick):
    rows = [LEVEL_ATTACKERS[0], LEVEL_ATTACKERS[4]] if quick else LEVEL_ATTACKERS
    return [(key, label, level_twin(make, seeds, p), kind, counted) for key, label, make, p, kind, counted in rows]


def md_level_attackers(d, seeds) -> str:
    out = [f"### Each proof-level attacker against its honest twin ({len(seeds)} seeds; a year; returns in $)", ""]
    out += ATTACK_HEAD
    for key, label, r, kind, counted in d:
        if "refused" in r:
            out.append(f"| {label} | refused at deployment | – | – | – | {V1_PUBLISHED.get(key, '–')} | "
                       f"{r['refused']} |")
        else:
            out.append(_row(label, r, key, L._got(kind, r)))
    return "\n".join(out)


COFF_NETWORKS: List[Tuple[str, Params, World, L.LevelWorld]] = [
    ("Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C: **level C off at launch (the default)**, the C third refused",
     V2, WORLD, LW),
    ("Growth, the same: **level C accepted from genesis (the merged design)**", C_ON, WORLD, LW),
    ("Grown: 21 validators ⅓ A, ⅓ B, ⅓ C: **level C off** (the 7 at C never registered)", V2, L.MATURE, LW),
    ("Grown: the same: **level C accepted**", C_ON, L.MATURE, LW),
]
COFF_ATTACKERS: List[Tuple[str, str, Callable[[bool], A.Actor], Optional[L.LevelWorld], str]] = [
    ("colluder", "Colluding genesis (A, $100), newcomers ⅓ each", lambda h: A.LoneColluder(h), LW, ""),
    ("breaker_genesis_50", "Chip breaker: the genesis at B, $50 device, newcomers ⅓ each",
     lambda h: L.ChipBreaker(h, break_cost=50.0), None, "breaker"),
    ("liar_grown", "Test liar: 1 of 15 at C", lambda h: L.TestLiar(h, "grown"), None, "liar"),
    ("shopper_1", "Answer shopper: 1 of 15 at C, 1 in 10",
     lambda h: L.AnswerShopper(h, "grown", borderline_pass=0.1, twin_submits=True), None, "shopper"),
    ("shopper_3", "Answer shopper: 1 of 15 at C, 3 in 10",
     lambda h: L.AnswerShopper(h, "grown", twin_submits=True), None, "shopper"),
]


def level_growth(seeds: Sequence[int], p: Params, w: World, lw: L.LevelWorld) -> Dict[str, list]:
    rows = []
    for s in seeds:
        n = L.LevelNet(s, p, w, (), lw=lw).run()
        m = growth_metrics(n)
        m["refused_c"] = n.stats["refused_c"]
        m["max_bounty"] = n.largest_bounty()
        rows.append(m)
    return _collect_runs(rows)


def s_c_off(seeds, sweep, quick):
    """Level C off at launch (the default) against the merged design (C from genesis). The level C attackers' C-on
    side is the proof-level table's rows (not run twice); off, their registration is refused (checked on one seed)."""
    nets = COFF_NETWORKS[:2] if quick else COFF_NETWORKS
    atts = COFF_ATTACKERS[:1] if quick else COFF_ATTACKERS
    out_n = [(label, level_growth(seeds, p, w, lw)) for label, p, w, lw in nets]
    out_a = []
    for key, label, make, lw, kind in atts:
        if kind in ("liar", "shopper"):
            out_a.append((key, label, None, level_twin(make, seeds[:1], V2, lw), kind))
        else:
            out_a.append((key, label, level_twin(make, seeds, C_ON, lw), level_twin(make, seeds, V2, lw), kind))
    return {"networks": out_n, "attackers": out_a}


def md_c_off(d, seeds, level_attackers=None) -> str:
    by_key = {k: r for k, _, r, _, _ in (level_attackers or [])}
    out = [f"### Level C at launch: off (owner decision 2026-11-03, spec PR pending; the default) against the merged "
           f"design, C accepted from genesis ({len(seeds)} seeds; a year)", "",
           "| Network | Newcomers joined (refused at C) | Qualified / days | Runs reaching k ≥ 3 / first week | "
           "Submissions that waited / withdrawn | Days from a k = 1 verdict to payment (median a run) | Bad fixes "
           "merged per 100 paid | Largest bounty judged at year's end | Active at year's end |",
           "|---|---|---|---|---|---|---|---|---|"]
    for label, m in d["networks"]:
        n = len(m["k3"])
        out.append(f"| {label} | {mean(m['joined']):.1f} ({mean(m['refused_c']):.1f}) | {_ms(m['qualified'], 1)} / "
                   f"{_ms(m['qualify_days'], 0)} | {sum(m['k3']):.0f} of {n} / week {_ms(m['k3_week'], 0)} | "
                   f"{_ms(m['waited'], 0, 100, unit=' %')} / {_ms(m['withdrawn'], 0, 100, unit=' %')} | "
                   f"{_ms(m['pay_days'], 1)} | {_ms(m['bad'], 2)} | ${mean(m['max_bounty']):,.0f} | "
                   f"{_ms(m['active'], 1)} |")
    out += ["", "| Attacker | Level C off at launch (the default): return − twin's ($) | | Level C accepted (from "
            "genesis, or after the ADR for the grown network's rows): return − twin's ($) | |", "|---|---|---|---|---|"]
    for key, label, on, off, kind in d["attackers"]:
        def cell(r):
            if r is None:
                return "–", "–"
            if "refused" in r:
                return "refused: it can't register", "–"
            return _pm(r["diff"], r["se"]), verdict(r["diff"], r["se"])
        a, b = cell(off)
        c, e = cell(on if on is not None else by_key.get(key))
        out.append(f"| {label} | {a} | {b} | {c} | {e} |")
    return "\n".join(out)


# ---------- market pricing ----------

MARKET_W = replace(WORLD, initial_active=0, joins_week=0.0)
SETTLE_ROWS: List[Tuple[str, Params, PR.MarketWorld, Optional[World]]] = [
    ("**#141's rules (the design)**", V2, PR.MARKET, None),
    (SW["idle_30"].label, SW["idle_30"].p, PR.MARKET, None),
    (SW["idle_50"].label, SW["idle_50"].p, PR.MARKET, None),
    (SW["idle_7d"].label, SW["idle_7d"].p, PR.MARKET, None),
    (SW["wait_any"].label, SW["wait_any"].p, PR.MARKET, None),
    ("every wait counts (#134's signal)", replace(V2, WAIT_SIGNAL="every"), PR.MARKET, None),
    (SW["step_up"].label, SW["step_up"].p, PR.MARKET, None),
    ("the design, 100 submissions a week", V2, PR.MARKET, PR.MARKET_100),
    ("the design, starting at v2's $0.05", V2, replace(PR.MARKET, fee_start=0.05), None),
    ("#134's rules (v1)", V1, PR.MARKET, None),
]


def honest_breakdown(net: Net) -> Dict[str, float]:
    """The honest validators' month (validators active for a month or more): service fees, the usage margin, node
    overhead, slashes, fixed costs and the bond's capital, and the net."""
    m, w = PR.market_of(net), net.w
    rows = []
    for v in net.reg.validators.values():
        if v.party != v.operator or v.behaviour is not None or v.active_at is None:
            continue
        months = ((min(net.t, v.leave_at) if v.leave_at is not None else net.t) - v.registered_at) / MONTH
        if months < 1:
            continue
        cap_end = min(net.t, v.gone_at) if v.gone_at is not None else net.t
        led = m.led(v.vid)
        fixed = months * w.enclave.fixed_month
        capital = v.posted * w.capital_rate * max(0.0, cap_end - v.registered_at) / (12 * MONTH)
        net_ = net.validator_net(v)
        over = led.service + led.margin + v.acct.rewards - v.acct.slashed - fixed - capital - net_
        rows.append({"service": led.service / months, "margin": led.margin / months, "overhead": over / months,
                     "slashed": v.acct.slashed / months, "fixed": fixed / months, "capital": capital / months,
                     "net": net_ / months})
    return {k: mean(r[k] for r in rows) for k in rows[0]} if rows else {}


MONTH_ROWS: List[Tuple[str, Params, World]] = [
    ("the design: outages before the seal (silence, not slashed)", V2, MARKET_W),
    ("the design: every outage after the seal ($1)", V2, replace(MARKET_W, outage_sealed=1.0)),
    (SW["wait_any"].label + ": outages before the seal", SW["wait_any"].p, MARKET_W),
    (SW["wait_any"].label + ": after the seal, $0.50", replace(SW["wait_any"].p, SEALED_NO_REVEAL_SLASH=0.5),
     replace(MARKET_W, outage_sealed=1.0)),
    (SW["wait_any"].label + ": after the seal, $1", SW["wait_any"].p, replace(MARKET_W, outage_sealed=1.0)),
    (SW["wait_any"].label + ": after the seal, $5", replace(SW["wait_any"].p, SEALED_NO_REVEAL_SLASH=5.0),
     replace(MARKET_W, outage_sealed=1.0)),
    ("#134's rules (v1)", V1, MARKET_W),
]


def s_pricing(seeds, sweep, quick):
    rows = SETTLE_ROWS[:1] if quick else SETTLE_ROWS
    settle = PR.settle_rows(seeds, rows)
    months = []
    for label, p, w in (MONTH_ROWS[:1] if quick else MONTH_ROWS):
        rs = [honest_breakdown(PR.run_market(s, p, w)) for s in seeds]
        rs = [r for r in rs if r]
        months.append((label, {k: [r[k] for r in rs] for k in (rs[0] if rs else {})}, len(rs)))
    series = [] if quick else [PR.series_table(seeds, "the design's values (#141)", V2),
                               PR.series_table(seeds, SW["wait_any"].label, SW["wait_any"].p),
                               PR.provider_table(seeds, p=V2)]
    return {"settle": settle, "months": months, "series": series}


def md_pricing(d, seeds) -> str:
    out = [PR.settle_table(seeds, d["settle"]).replace(
        "| Runs collapsed (< 3 active) | Honest validator's month |",
        "| Runs collapsed (< 3 active) | Honest validator's month |"), "",
        f"#### The fee against break-even, D17's `FEE_MARGIN` ({len(seeds)} seeds; the runs that didn't collapse)",
        "", "| Variant | Fee / break-even over the last 13 weeks (± 2 SE) | Within [1 − `FEE_STEP`, 1 + `FEE_MARGIN`] "
        "| Runs collapsed |", "|---|---|---|---|"]
    for label, r in d["settle"]:
        m, se = mean_se(r.get("ratio", []))
        ok = at_most(m, se, 1 + V2.FEE_MARGIN) and at_least(m, se, 1 - V2.FEE_STEP) and sum(r["collapsed"]) == 0
        out.append(f"| {label} | {_ms(r.get('ratio', []), 2, unit=' ×')} | {'yes' if ok else 'no'} | "
                   f"{sum(r['collapsed']):.0f} of {len(seeds)} |")
    out += ["", f"#### An honest validator's month on the market ({len(seeds)} seeds; honest validators active a "
            "month or more; $ a month)", "",
            "| Market and outages | Service fees | Usage margin | Node overhead | Slashes | Fixed costs | The bond's "
            "capital | Net | Runs with such validators |", "|---|---|---|---|---|---|---|---|---|"]
    for label, m, n in d["months"]:
        if not m:
            out.append(f"| {label} | – | – | – | – | – | – | – | 0 |")
            continue
        out.append(f"| {label} | " + " | ".join(_ms(m[k], 2, pre="$") for k in
                                                ("service", "margin", "overhead", "slashed", "fixed", "capital", "net"))
                   + f" | {n} |")
    out += ["", "#134: the honest validator's month on the market " + V1_PUBLISHED["month_market"] + " $ (the fee "
            "at its ceiling), and −$8.01 on the growing network, $2.05 of it outage slashes."]
    return "\n\n".join([out[0], "\n".join(out[2:])] + list(d["series"]))


PRICE_ATTACKS: List[Tuple[str, str, str, Callable[[bool], A.Actor], Params, str, bool]] = []
for _world, _p, _counted in (("design", V2, True), ("any-bond wait signal", SW["wait_any"].p, False)):
    PRICE_ATTACKS += [
        ("cartel", "Cartel: 6 validators refusing half their draws", _world, lambda h: PR.Cartel(h), _p, "cartel",
         _counted),
        ("spam_wait", "Spammer: a fix a day to a $625 bounty no panel can judge yet", _world, lambda h: PR.Spammer(h),
         _p, "spam", _counted),
        ("spam_judged", "Spammer: a bad fix a day, judged", _world, lambda h: PR.Spammer(h, kind="judged"), _p, "spam",
         _counted),
        ("inflate", "Inflaters: 3 Anthropic validators of 24 posting 100 × their costs", _world,
         lambda h: PR.Inflater(h), _p, "inflate", _counted),
        ("inflate_small", "Inflaters on a small network (the genesis, 4 honest, the 3 inflaters)", _world,
         lambda h: PR.Inflater(h, small=True), _p, "inflate", _counted),
        ("pfarmer", "Fee farmer: 10 idle validators at the bond floor (twin: one)", _world,
         lambda h: PR.PricedFeeFarmer(h), _p, "farmer", _counted),
    ]


def s_price_attacks(seeds, sweep, quick):
    rows = PRICE_ATTACKS[:1] if quick else PRICE_ATTACKS
    return [(key, label, world, A.against_twin(make, seeds, p=p, metrics=PR._attack_metrics), kind, counted)
            for key, label, world, make, p, kind, counted in rows]


def md_price_attacks(d, seeds) -> str:
    out = [f"### The pricing attackers against their honest twins ({len(seeds)} seeds; a year; returns in $)", "",
           "| Attacker | Market | Return − twin's ($, ± 2 SE) | Against its twin | Mean fee: attacker's run / twin's | "
           "Its family's token price (× deployment): attacker's / twin's | Active validators (last 13 weeks) | "
           "#134 (v1, design) | What it did |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label, world, r, kind, counted in d:
        v1 = V1_PUBLISHED.get(key, "–") if counted else ""
        out.append(f"| {label} | {world} | {_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | "
                   f"${r['fee']:.3f} / ${r['twin_fee']:.3f} | {r['price']:.2f} / {r['twin_price']:.2f} | "
                   f"{r['active']:.1f} | {v1} | {PR._did(kind, r)} |")
    return "\n".join(out)


# ---------- model scores ----------

def herd_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = SC._herd_metrics(net, a)
    mine = [(vote, s.final) for s in net.subs.values() if s.tier == ISSUE and s.final is not None
            for vid, vote, _ in s.judges if net.reg.validators[vid].party == a.party]
    sides = [[v == f for v, f in mine if f is side] for side in (True, False)]
    shares = [sum(x) / len(x) for x in sides if x]
    m["agree_balanced"] = sum(shares) / len(shares) if shares else NAN
    return m


HERD_ROWS: List[Tuple[str, str, str, bool, Optional[float], Params, bool]] = [
    ("herd_mid_det", "`mid` (90 %), receipts detectable", "mid", True, None, V2, True),
    ("herd_mid", "`mid` (90 %), not detectable (upper bound)", "mid", False, None, V2, True),
    ("herd_weak_det", "`weak` (68 %), receipts detectable", "weak", True, None, V2, True),
    ("herd_weak", "`weak` (68 %), not detectable (upper bound)", "weak", False, None, V2, True),
    ("herd_mid_25", "`mid`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "mid", False, 0.25, V2, True),
    ("herd_weak_25", "`weak`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "weak", False, 0.25, V2, True),
    ("herd_mid_bal", "`mid`, not detectable, " + SW["balanced"].label, "mid", False, None, SW["balanced"].p, False),
    ("herd_weak_bal", "`weak`, not detectable, " + SW["balanced"].label, "weak", False, None, SW["balanced"].p, False),
    ("herd_weak_25_bal", "`weak`, not detectable, $0.25, " + SW["balanced"].label, "weak", False, 0.25,
     SW["balanced"].p, False),
]
MODES: List[Tuple[str, Optional[str], Params]] = [
    ("One vote, no scores", None, V2),
    ("**One vote, pay by score (#141: counted-only scores, the normalised factor)**", "pay", V2),
    ("One vote, pay by score, " + SW["median"].label, "pay", SW["median"].p),
    ("One vote, pay by score, " + SW["balanced"].label, "pay", SW["balanced"].p),
    ("Votes weighted by the score factor", "factor", V2),
    ("One vote, pay by score, #134's scores (shadows merged, neutral at 80 %)", "pay", V1),
]


def s_scores(seeds, sweep, quick):
    fams: Dict[str, Dict[str, list]] = {}
    for s in seeds:
        n = SC.run_mode(s, "pay", SC.SCORE_WORLD, V2)
        for f in SC.FAMILIES:
            sc, k = n.scores.state(f)
            st = n.scores.fam[f]
            row = fams.setdefault(f, {})
            for key, val in (("score", sc if sc is not None else NAN), ("factor", n.scores.factor(f)),
                             ("barred", n.scores.barred_days[f] / max(1.0, n.t / 24.0)), ("bars", st.bars),
                             ("recoveries", st.recoveries)):
                row.setdefault(key, []).append(val)
    modes = []
    for world_name, w in ((("blind spots", SC.SCORE_WORLD),) if quick else
                          (("blind spots", SC.SCORE_WORLD), ("no blind spots", SC.NO_BLIND))):
        for label, mode, p in (MODES[1:2] if quick else MODES):
            modes.append((world_name, label, SC._avg([SC.market_metrics(SC.run_mode(s, mode, w, p)) for s in seeds])))
    herds = []
    for key, label, f, det, fee, p, counted in (HERD_ROWS[3:4] if quick else HERD_ROWS):
        w = SC.SCORE_WORLD if fee is None else replace(SC.SCORE_WORLD, service_fee=fee)
        herds.append((key, label, SC.twins(lambda h, f=f, d=det, w=w: SC.Herders(h, family=f, detectable=d, w=w),
                                           seeds, herd_metrics, p), counted))
    movers = {} if quick else {"design": SC.movers(seeds, p=V2),
                               "instant": SC.movers(seeds, p=replace(V2, MOVE_REREGISTERS=False)),
                               "party": SC.movers_party(seeds, p=V2)}
    return {"families": fams, "modes": modes, "herds": herds, "movers": movers}


def md_scores(d, seeds) -> str:
    out = [f"### The families' scores under #141's rules ({len(seeds)} seeds; at the year's end)", "",
           "| Family | True accuracy (assumed) | Score (counted verdicts) | Fee factor (normalised) | Share of the year "
           "barred | Times barred / recovered |", "|---|---|---|---|---|---|"]
    for f in SC.FAMILIES:
        m = d["families"].get(f)
        if not m:
            continue
        out.append(f"| `{f}` | {100 * SC.SCORE_WORLD.accuracy_of(f):.0f} % | {_ms(m['score'], 1, 100, unit=' %')} | "
                   f"{_ms(m['factor'], 2, unit=' ×')} | {_ms(m['barred'], 0, 100, unit=' %')} | "
                   f"{mean(m['bars']):.1f} / {mean(m['recoveries']):.1f} |")
    fams = SC.FAMILIES
    out += ["", f"### One vote, pay by score, weighted votes ({len(seeds)} seeds; a year)", "",
            "| Families | Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family "
            "(%) | Service fees per submission ($) | " + " | ".join(f"`{f}` net a month ($)" for f in fams) + " |",
            "|---" * (6 + len(fams)) + "|"]
    for world, label, m in d["modes"]:
        out.append(f"| {world} | {label} | {_ms(m['bad_per_100'], 2)} | {_ms(m['good_failed_pct'], 2)} | "
                   f"{_ms(m['one_family'], 2, 100)} | {_ms(m['fee_per_check'], 3)} | "
                   + " | ".join(_ms(m[f'net_{f}'], 2) for f in fams) + " |")
    out += ["", "#134: service fees per submission " + V1_PUBLISHED["fees_per_sub"] + " with pay by score against "
            + V1_PUBLISHED["fees_flat"] + " without (+39 %)."]
    if d["movers"]:
        r, t, i = d["movers"]["design"], None, d["movers"]["instant"]
        tw = {k[5:]: v for k, v in r.items() if k.startswith("twin_")}

        def row(label, key, nd=1, scale=1.0, unit=""):
            return (f"| {label} | {_ms(tw[key], nd, scale, unit=unit)} | {_ms(r[key], nd, scale, unit=unit)} | "
                    f"{_ms(i[key], nd, scale, unit=unit)} |")
        out += ["", f"### Everyone moves to the top model ({len(seeds)} seeds; a year; every validator reconsiders "
                "monthly and changes to the family paying most per head when it pays 10 % more)", "",
                "| | Nobody moves | Everyone moves, registering again (#141) | Everyone moves at once (#134's reading) "
                "|", "|---|---|---|---|"]
        out += [row(f"Share of drawable validators in `{f}` at the year's end", f"share_{f}", 0, 100, " %")
                for f in fams]
        out += [row("Families with at least 10 % of the validators", "families_10", 1),
                row("Share of counted seats held by `top`", "top_seats", 1, 100, " %"),
                row("Panels with more of one family than the cap allows", "over_cap", 0),
                row("Draws whose k the caps lowered", "stepped_down", 1, 100, " %"),
                row("**Submissions that waited for a panel** (`WAIT_CROWD_MAX` 15 %)", "waited", 1, 100, " %"),
                row("Bad fixes merged per 100 paid", "bad_per_100", 2),
                row("Family changes in the year", "moves", 0),
                row("An activated validator's net per month ($)", "net_all", 2)]
        pm = d["movers"]["party"]
        out += ["", f"Four validators starting in `low` that move (registering again) against the same four staying: "
                f"return − twin's **{_pm(pm['diff'], pm['se'])}** $ a year ({verdict(pm['diff'], pm['se'])}). "
                "#134 (moving at once): crowding " + V1_PUBLISHED["crowd"] + " of submissions waited."]
    out += ["", f"### Herding ({len(seeds)} seeds; a year; 4 herders of one family among 16 honest validators; each "
            "votes pass, the public base rate's majority)", "",
            "| Herders | Their agreement with outcomes (twin's) | ...balanced over passed and failed outcomes | Their "
            "family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Return − "
            "twin's ($, ± 2 SE) | Herding | #134 (v1) |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d["herds"]:
        two = lambda k, nd, scale=1.0, unit="": (f"{_ms(r[k], nd, scale, unit=unit)} "
                                                 f"({_ms(r['twin_' + k], nd, scale, unit=unit)})")
        out.append(f"| {label} | {two('agree', 1, 100, ' %')} | {two('agree_balanced', 1, 100, ' %')} | "
                   f"{two('family_score', 1, 100, ' %')} | {two('barred', 0, 100, ' %')} | {two('bad_per_100', 2)} | "
                   f"{_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | {V1_PUBLISHED.get(key, '–')} |")
    return "\n".join(out)


ANY = SW["wait_any"].p  # the market that doesn't collapse: the switches of the score factor run on it
SCORE_MARKETS: List[Tuple[str, Params]] = [
    ("design", V2), ("any-bond wait signal", ANY),
    ("any-bond wait signal, the factor's 1 × at the median score", replace(ANY, SCORE_FACTOR_RULE="median"))]
MARKET_HERDS: List[Tuple[str, str, str, bool, Params, bool]] = [
    ("mherd_mid", "`mid` (90 %), not detectable, market at the design's values", "mid", False, V2, True),
    ("mherd_weak", "`weak` (68 %), not detectable, market at the design's values", "weak", False, V2, True),
    ("mherd_mid_any", "`mid`, not detectable, " + SW["wait_any"].label, "mid", False, ANY, False),
    ("mherd_weak_any", "`weak`, not detectable, " + SW["wait_any"].label, "weak", False, ANY, False),
    ("mherd_weak_any_bal", "`weak`, not detectable, " + SW["wait_any"].label + ", " + SW["balanced"].label, "weak",
     False, replace(ANY, SCORE_BALANCED=True), False),
]


def s_scores_market(seeds, sweep, quick):
    compare = F.market_compare(seeds, SCORE_MARKETS[:1] if quick else SCORE_MARKETS)
    herds = []
    for key, label, fam, det, p, counted in (MARKET_HERDS[1:2] if quick else MARKET_HERDS):
        def make(h, fam=fam, det=det, p=p):
            return F.MarketHerders(h, p=p, family=fam, detectable=det)

        def metrics(net, a):
            return {**herd_metrics(net, a), "fee": F._market_fee(net), "active": PR.settle(net)["active"]}
        herds.append((key, label, SC.twins(make, seeds, metrics), counted))
    return {"compare": compare, "herds": herds}


def md_scores_market(d, seeds) -> str:
    table = F.market_compare_md(seeds, d["compare"]).split("\n\nMarket \"design\"")[0]
    out = [table, "", "Market \"design\": #141's rules, the fee starting at the ceiling (it collapses in most runs, "
           "see the pricing section). \"any-bond wait signal\": the switch under which it doesn't. The families are "
           "priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight "
           "model). Prospects decide to enter on the unscaled fee.", "",
           f"### Herding on the market fee ({len(seeds)} seeds; a year; 4 undetectable herders of one family beside "
           "the market's validators)", "",
           "| Herders | Their agreement (twin's) | Their family's score (twin's) | Family barred (twin's) | Bad fixes "
           "merged per 100 paid (twin's) | Mean fee | Return − twin's ($, ± 2 SE) | Herding | #134 (v1) |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d["herds"]:
        two = lambda k, nd, scale=1.0, unit="": (f"{_ms(r[k], nd, scale, unit=unit)} "
                                                 f"({_ms(r['twin_' + k], nd, scale, unit=unit)})")
        out.append(f"| {label} | {two('agree', 1, 100, ' %')} | {two('family_score', 1, 100, ' %')} | "
                   f"{two('barred', 0, 100, ' %')} | {two('bad_per_100', 2)} | ${mean(r['fee']):.3f} | "
                   f"{_pm(r['diff'], r['se'])} | {verdict(r['diff'], r['se'])} | {V1_PUBLISHED.get(key, '–')} |")
    out += ["", "#134's weak-family herders on its moving market (no outage slash, `IDLE_HIGH` 50 %): "
            + V1_PUBLISHED["mherd_weak_moving"] + " $."]
    return "\n".join(out)


# ---------- everything once ----------

SECTIONS: Dict[str, Callable] = {
    "growth": s_growth, "attackers": s_attackers, "colluder": s_colluder, "sybil": s_sybil, "watch": s_watch,
    "constitution": s_constitution, "silent": s_silent, "ktable": s_ktable, "level_networks": s_level_networks,
    "level_attackers": s_level_attackers, "c_off": s_c_off, "pricing": s_pricing, "price_attacks": s_price_attacks,
    "scores": s_scores, "scores_market": s_scores_market,
}
# the heaviest first, so two processes share the load
ORDER = ("price_attacks", "level_attackers", "scores", "colluder", "watch", "c_off", "scores_market", "constitution",
         "pricing", "level_networks", "growth", "silent", "attackers", "sybil", "ktable")


def _section(name: str, seeds: Tuple[int, ...], sweep: Tuple[int, ...], quick: bool):
    return SECTIONS[name](seeds, sweep, quick)


def collect(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None, quick: bool = False,
            jobs: int = 1) -> Dict[str, object]:
    seeds, sweep = tuple(seeds), tuple(sweep or seeds)
    d: Dict[str, object] = {"seeds": list(seeds), "sweep": list(sweep), "quick": quick}
    if jobs > 1:  # forked workers (no program is run, rule 1); where fork doesn't exist, one process
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:
            jobs = 1
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as ex:
            futs = {name: ex.submit(_section, name, seeds, sweep, quick) for name in ORDER}
            for name, fut in futs.items():
                d[name] = fut.result()
    else:
        for name in ORDER:
            d[name] = _section(name, seeds, sweep, quick)
    return d


# ---------- the acceptance criteria (D17) ----------

@dataclass(frozen=True)
class Criterion:
    name: str
    met: bool
    decides: str
    threshold: str = ""

    @property
    def verdict(self) -> str:
        return "met" if self.met else "not met"


def _rows_against_twin(rows: List[Tuple[str, float, float]]) -> Tuple[bool, str]:
    """Every row loses (mean + 2 SE < 0); the reason names the ones that don't, or the closest that does."""
    bad = [(n, m, se) for n, m, se in rows if not loses(m, se)]
    if not rows:
        return False, "no rows"
    if not bad:
        n, m, se = max(rows, key=lambda x: x[1] + 2 * x[2])
        return True, f"all {len(rows)} lose; the closest: {n} ({_pm(m, se)} $)"
    return False, f"{len(bad)} of {len(rows)} don't lose: " + "; ".join(f"{n} ({_pm(m, se)} $)" for n, m, se in bad)


def counted_rows(d: Dict[str, object]) -> Dict[str, List[Tuple[str, float, float]]]:
    """The attackers counted (D17): on the design's values, the new rules included, every herder row; not the
    counterfactuals, the "without levels" rows, the switches or #134's rules."""
    ov = [(label, r["diff"], r["se"]) for key, label, r, kind, counted in d["attackers"] if counted]
    for key, label, m in d["colluder"]:
        if key == "design":  # 1 bad fix a week is a sensitivity row, as in #134
            ov.append((f"Colluding genesis ({label.replace('**', '')})", *mean_se(m["diff"])))
    ov += [(label.replace("**", ""), r["diff"], r["se"]) for key, label, r, counted in d["silent"] if counted]
    ov += [(f"Constitution coalition: {label}", r["diff"], r["se"]) for key, label, r in d["constitution"]
           if key.endswith("_14")]
    for kind in ("lazy", "bribed"):
        for vol, rate, r in d["watch"][kind]:
            if not vol and abs(rate - V2.AUDIT_RATE) < 1e-12:
                ov.append((f"D13's {kind} cheater (audits at {100 * rate:g} %, no volunteers)", r["diff"], r["se"]))
    lv = [(label.replace("**", ""), r["diff"], r["se"]) for key, label, r, kind, counted in d["level_attackers"]
          if counted and "refused" not in r]
    pr = [(f"{label} ({world})", r["diff"], r["se"]) for key, label, world, r, kind, counted in d["price_attacks"]
          if counted]
    sc = [(f"Herders: {label}", r["diff"], r["se"]) for key, label, r, counted in d["scores"]["herds"] if counted]
    sc += [(f"Herders on the market: {label}", r["diff"], r["se"]) for key, label, r, counted
           in d["scores_market"]["herds"] if counted]
    return {"open": ov, "pricing": pr, "levels": lv, "scores": sc}


def acceptance(d: Dict[str, object], p: Params = V2) -> List[Criterion]:
    """Each criterion of "Acceptance criteria for open validators", judged as D17 says."""
    out: List[Criterion] = []
    rows = counted_rows(d)
    for name, key in (("Each open-validator attacker loses against its honest twin", "open"),
                      ("Each pricing attacker loses against its honest twin", "pricing"),
                      ("Each proof-level attacker loses against its honest twin (answer shopping at 1 in 10; the "
                       "level C rows after C is switched on by ADR)", "levels"),
                      ("Each scoring attacker (the herders) loses against its honest twin", "scores")):
        met, why = _rows_against_twin(rows[key])
        out.append(Criterion(name, met, why, "mean + 2 SE < 0"))

    sy = {(n, s): m for n, s, m in d["sybil"]}
    at = [(n, s, m) for (n, s), m in sy.items() if n / (n + 21) <= p.SYBIL_SHARE + 1e-9]
    worst = max((m["any_majority"] for _, _, m in at), default=NAN)
    out.append(Criterion(
        f"A sybil at or under `SYBIL_SHARE` ({100 * p.SYBIL_SHARE:g} %) never holds a majority of a panel of k ≥ 3, "
        "in any run", bool(at) and worst == 0,
        ("no sybil size at the share was run" if not at else
         "; ".join(f"{n} validators ({100 * n / (n + 21):.1f} %), {s}: a majority on {100 * m['any_majority']:.2f} % "
                   "of panels" for n, s, m in at)), "0 runs"))
    above = sorted(((n, s, m) for (n, s), m in sy.items() if n / (n + 21) > p.SYBIL_SHARE + 1e-9))
    out.append(Criterion(
        "A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's "
        "caught", True, "reported: " + ("; ".join(
            f"{n} ({100 * n / (n + 21):.0f} %), {s}: a majority on {100 * m['majority']:.1f} % of its own panels, "
            f"{m['bad_paid']:.1f} bad fixes paid, {m['caught']:.1f} false verdicts proven" for n, s, m in above)
            if above else "no size above the share was run"), "reported"))

    col = {k: m for k, _, m in d["colluder"]}["design"]
    c, cse = caught(col)
    dm, dse = mean_se(col["diff"])
    met = loses(dm, dse) and at_least(c, cse, p.LONE_CATCH_SHARE)
    out.append(Criterion(
        f"The colluding lone validator loses, and at least `LONE_CATCH_SHARE` ({100 * p.LONE_CATCH_SHARE:g} %) of the "
        "bad fixes it passes are reversed before any payment (pooled)", met,
        f"return − twin's {_pm(dm, dse)} $ ({verdict(dm, dse)}); reversed before payment {_pct(c, 1)} ± "
        f"{_pct(2 * cse, 1)} ({sum(col['reversed']):.0f} of {sum(col['resolved']):.0f} that reached an outcome; "
        f"{sum(col['pending']):.0f} still pending at the year's end)",
        f"mean + 2 SE < 0 and share − 2 SE ≥ {100 * p.LONE_CATCH_SHARE:g} %"))

    const = [(label, r) for key, label, r in d["constitution"] if key.endswith("_14")]
    small = sum(r["below_14"] * len(r["diffs"]) for _, r in const)
    out.append(Criterion(
        "The constitution waits for the network: no ADR passes while fewer than 2 × `K_MAX` validators are eligible, "
        "in any run", bool(const) and small == 0,
        f"ADRs passed while fewer than {2 * p.K_MAX} were eligible, all runs: {small:g} (over "
        f"{' and '.join(l for l, _ in const)})", "0 runs"))

    st = d["pricing"]["settle"][0][1]
    m, se = mean_se(st.get("ratio", []))
    dead = sum(st["collapsed"])
    met = at_most(m, se, 1 + p.FEE_MARGIN) and at_least(m, se, 1 - p.FEE_STEP) and dead == 0
    out.append(Criterion(
        f"The fee settles within `FEE_MARGIN` ({100 * p.FEE_MARGIN:g} %) above break-even and at least break-even less "
        "one step, and no run collapses", met,
        f"from the ceiling, fee / break-even over the last 13 weeks {_ms(st.get('ratio', []), 2, unit=' ×')} (the runs "
        f"that didn't collapse); {dead:.0f} of {len(st['collapsed'])} runs collapsed below 3 active validators",
        f"{1 - p.FEE_STEP:.2f} ≤ ratio ± 2 SE ≤ {1 + p.FEE_MARGIN:.2f}; 0 runs collapse"))

    mv = d["scores"]["movers"]
    if mv:
        wm, wse = mean_se(mv["design"]["waited"])
        out.append(Criterion(
            f"Everyone crowds into one model: at most `WAIT_CROWD_MAX` ({100 * p.WAIT_CROWD_MAX:g} %) of submissions "
            "wait", at_most(wm, wse, p.WAIT_CROWD_MAX),
            f"{_ms(mv['design']['waited'], 1, 100, unit=' %')} waited, every validator moving (registering again)",
            f"mean + 2 SE ≤ {100 * p.WAIT_CROWD_MAX:g} %"))
    else:
        out.append(Criterion("Everyone crowds into one model: at most `WAIT_CROWD_MAX` of submissions wait", False,
                             "not run (quick)", ""))

    g = {k: m for k, _, m in d["growth"]["rows"]}["design"]
    runs = len(g["k3"])
    out.append(Criterion(
        "The network still grows: a small bounty reaches k ≥ 3 within the year in every run", sum(g["k3"]) == runs,
        f"{sum(g['k3']):.0f} of {runs} runs, at week {_ms(g['k3_week'], 0)}; the median days from a k = 1 verdict to "
        f"its payment, a run: {_ms(g['pay_days'], 1)} (p90 over every run: {_p90(g.get('pay_all', [])):.1f})",
        "every run"))

    sh = {k: r for k, _, r, _, _ in d["level_attackers"]}
    s1 = sh.get("shopper_1")
    s3 = sh.get("shopper_3")
    if s1 is not None and "refused" not in s1:
        out.append(Criterion(
            "Answer shopping, the trust point: it loses at 1 in 10; at 3 in 10 the report gives its gain",
            loses(s1["diff"], s1["se"]),
            f"at 1 in 10: {_pm(s1['diff'], s1['se'])} $ ({verdict(s1['diff'], s1['se'])}); at 3 in 10 (reported): "
            + (f"{_pm(s3['diff'], s3['se'])} $" if s3 is not None and "refused" not in s3 else "not run"),
            "mean + 2 SE < 0 at 1 in 10"))
    out.append(Criterion(
        "Every earlier criterion holds or is named", True,
        "named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so "
        "reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and "
        "split-v1.md stand", "named"))
    failed = [c.name for c in out if not c.met]
    out.append(Criterion(
        "Adopt the k table, windows, bonds, caps and pricing bounds (all of the above)", not failed,
        f"{len(failed)} of {len(out)} criteria not met" if failed else "every criterion met", "all"))
    return out


def acceptance_md(d: Dict[str, object]) -> str:
    seeds = d["seeds"]
    out = [f"### Acceptance criteria for open validators under D17 ({len(seeds)} seeds; sweeps on {len(d['sweep'])}; "
           "± 2 standard errors)", "", "| Criterion | Verdict | Threshold | What decides it |", "|---|---|---|---|"]
    for c in acceptance(d):
        out.append(f"| {c.name} | **{c.verdict}** | {c.threshold} | {c.decides} |")
    return "\n".join(out)


# ---------- a rule against its alternative ----------

def rule_vs_alternative(d: Dict[str, object]) -> str:
    """One row per #141 rule: the number that measures it, under the rule and under each alternative (same seeds)."""
    col = {k: m for k, _, m in d["colluder"]}
    gro = {k: m for k, _, m in d["growth"]["rows"]}
    sil = {k: r for k, _, r, _ in d["silent"]}
    con = {k: r for k, _, r in d["constitution"]}
    att = {k: r for k, _, r, _, _ in d["attackers"]}
    lev = {k: r for k, _, r, _, _ in d["level_attackers"]}
    settle = {label: r for label, r in d["pricing"]["settle"]}
    herd = {k: r for k, _, r, _ in d["scores"]["herds"]}

    def col_cell(k):
        if k not in col:
            return "–"
        m = col[k]
        c, cse = caught(m)
        dm, dse = mean_se(m["diff"])
        g = gro.get(k)
        pay = f"; honest k = 1 pay {_ms(g['pay_days'], 1)} days" if g else ""
        return f"colluder {_pm(dm, dse)} $, {_pct(c, 0)} reversed{pay}"

    def twin_cell(r, what=""):
        if r is None or "refused" in r:
            return "–"
        return f"{what}{_pm(r['diff'], r['se'])} $ ({verdict(r['diff'], r['se'])})"

    def fee_cell(label):
        r = settle.get(label)
        if r is None:
            return "–"
        return f"fee / break-even {_ms(r.get('ratio', []), 2, unit=' ×')}; {sum(r['collapsed']):.0f} collapsed"

    def growth_cell(k):
        g = gro.get(k)
        if g is None:
            return "–"
        return (f"k ≥ 3 in {sum(g['k3']):.0f} runs, week {_ms(g['k3_week'], 0)}; caps lowered "
                f"{_ms(g['stepped'], 0, 100, unit=' %')}; one TEE type holds a k = 3 majority on "
                f"{_ms(g['one_tee_k3'], 0, 100, unit=' %')}")

    rows = [
        ("k = 1: hold, `K1_PENDING_MAX` 10, every k = 1 audited", col_cell("design"),
         "; ".join(f"{SW[k].label}: {col_cell(k)}" for k in ("k1_cap_5", "k1_cap_20", "k1_batch"))),
        ("k = 1's window 7 days", col_cell("design"),
         "; ".join(f"{SW[k].label}: {col_cell(k)}" for k in ("k1_window_14", "k1_window_30"))),
        ("False verdict: the whole bond", "; ".join(x for x in (twin_cell(att.get("grinder"), "grinder "),
                                                                twin_cell(att.get("sybil"), "sybil ")) if x != "–"),
         "2,000: " + "; ".join(x for x in (twin_cell(att.get("grinder_2000"), "grinder "),
                                           twin_cell(att.get("sybil_2000"), "sybil "), col_cell("false_2000"))
                               if x != "–")),
        ("Constitution from 14 eligible, with expiry",
         "; ".join(twin_cell(con.get(f"c{n}_14"), f"{n} early: ") for n in (5, 3)),
         "; ".join(f"{thr}: " + ", ".join(twin_cell(con.get(f"c{n}_{thr}"), f"{n} early ") for n in (5, 3))
                   for thr in (21, 28))),
        ("Sealed vote not revealed: $1; silence not slashed",
         twin_cell(sil.get("silent"), "silent ") + "; " + twin_cell(sil.get("withhold_1"), "withholder "),
         "; ".join(x for x in (twin_cell(sil.get("silence_1"), "`SILENCE_SLASH` $1: silent "),
                               twin_cell(sil.get("withhold_050"), "$0.50: withholder "),
                               twin_cell(sil.get("withhold_5"), "$5: withholder ")) if x != "–")),
        ("Pricing: `IDLE_HIGH` 40 %, floor-bond wait signal", fee_cell(SETTLE_ROWS[0][0]),
         "; ".join(f"{label}: {fee_cell(label)}" for label, *_ in SETTLE_ROWS[1:7])),
        ("Scores: counted only, normalised factor", twin_cell(herd.get("herd_weak"), "weak herders "),
         "; ".join(x for x in (twin_cell(herd.get("herd_weak_bal"), f"{SW['balanced'].label}: weak herders "),
                               twin_cell(herd.get("herd_mid_bal"), "mid herders ")) if x != "–")),
        ("Level C's limits as the k table", twin_cell(lev.get("shopper_3"), "shopper at 3 in 10 ") + "; "
         + twin_cell(lev.get("shopper_1"), "at 1 in 10 "),
         twin_cell(lev.get("shopper_3_c_half"), f"{SW['c_half'].label}: at 3 in 10 ") + "; "
         + twin_cell(lev.get("shopper_1_c_half"), "at 1 in 10 ")),
        ("TEE cap from k = 5", growth_cell("design"),
         f"#134's from k = 3: {growth_cell('tee_from_3')}; {SW['tee5_from3'].label}: {growth_cell('tee5_from3')}"),
        ("`SHADOW_PER_WAITING` 3", growth_cell("design") + "; " + col_cell("design"),
         f"{SW['no_wait_shadows'].label}: {growth_cell('no_wait_shadows')}; {col_cell('no_wait_shadows')}"),
    ]
    out = [f"### A rule against its alternative ({len(d['seeds'])} seeds; the same seeds for each pair)", "",
           "| #141's rule | Under the rule | Under each alternative |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    return "\n".join(out)


# ---------- the report ----------

def render(d: Dict[str, object]) -> str:
    seeds, sweep = d["seeds"], d["sweep"]
    head = (f"# Open validators, v2: #141's rules ({len(seeds)} seeds; the sybil and audit sweeps on {len(sweep)})"
            + (" — QUICK: one row per section, for the tests" if d["quick"] else ""))
    parts = [head,
             "## Growth from one validator under the hold, and the TEE cap", md_growth(d["growth"], seeds),
             "## The attackers", md_attackers(d["attackers"], seeds), md_colluder(d["colluder"], seeds),
             md_silent(d["silent"], seeds), md_constitution(d["constitution"], seeds), md_sybil(d["sybil"], sweep),
             R.watchers_table(sweep, "lazy", data=d["watch"]["lazy"]),
             R.watchers_table(sweep, "bribed", data=d["watch"]["bribed"]),
             "## The k table compared", F.k_table_md(seeds, d["ktable"]),
             "## Proof levels", md_level_networks(d["level_networks"], seeds),
             md_level_attackers(d["level_attackers"], seeds), md_c_off(d["c_off"], seeds, d["level_attackers"]),
             "## Market pricing", md_pricing(d["pricing"], seeds), md_price_attacks(d["price_attacks"], seeds),
             "## Model scores", md_scores(d["scores"], seeds), md_scores_market(d["scores_market"], seeds),
             "## A rule against its alternative", rule_vs_alternative(d),
             "## Acceptance criteria", acceptance_md(d)]
    return "\n\n".join(parts)


def full_report(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None, quick: bool = False,
                jobs: int = 1) -> str:
    return render(collect(seeds, sweep, quick, jobs))
