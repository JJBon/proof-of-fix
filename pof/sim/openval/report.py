"""The phase-1 tables of reports/open-validators-v1.md (#134 tasks 1.1-1.3, 1.6):

    python3 -m pof.sim.openval growth    --seeds N   growth from one validator: k, the largest bounty, the waiting
    python3 -m pof.sim.openval attackers --seeds N   each phase-1 attacker against its honest twin
    python3 -m pof.sim.openval sybil     --seeds N   the sybil's majorities by its share and its spread
    python3 -m pof.sim.openval audits    --seeds N   the watcher's dilemma by audit rate, with and without volunteers
    python3 -m pof.sim.openval levels    --seeds N   proof levels: panels by level, and their attackers (task 1.5)
    python3 -m pof.sim.openval pricing   --seeds N   market pricing: the fee finding cost, unit prices, the attackers
    python3 -m pof.sim.openval scores    --seeds N   model scores (task 1.7, pof.sim.openval.scores): one vote, pay by
                                                     score and weighted votes; everyone moving to the top model; herders
    python3 -m pof.sim.openval all       --seeds N   the full v3 report of #141's round 2 (pof.sim.openval.round2; =
                                                     python3 -m pof.sim market validators)

Each section runs on the current defaults: #141's round 2 (`params.V2R2`); with POF_OPENVAL_RULES=v2r1, round 1's
(`V2R1`); with POF_OPENVAL_RULES=v1, #134's (`V1`), which is how reports/open-validators-v1.md is reproduced
(python3 -m pof.sim market validators --v1). Every number is a mean
over seeds 1..N; "± 2 SE" is two standard errors of that mean. Nothing here opens a connection (rule 1).
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from .net import Net
from .params import MONTH, PARAMS, WORLD, Params, World


def _ms(xs: Sequence[float], nd: int = 1) -> str:
    return f"{mean(xs):,.{nd}f} ± {2 * A._se(xs):,.{nd}f}"


def _pct(xs: Sequence[float]) -> str:
    return f"{100 * mean(xs):.0f} % ± {200 * A._se(xs):.0f}"


def _verdict(m: float, se: float) -> str:
    if m + 2 * se < 0:
        return "loses"
    if m - 2 * se > 0:
        return "**wins**"
    return "not significant"


# ---------- growth from one validator ----------

def growth(seeds: Sequence[int], p: Params = PARAMS, w: World = WORLD) -> Dict[str, object]:
    nets = [Net(s, p, w).run() for s in seeds]
    rows = []
    for i in range(min(len(n.series) for n in nets)):
        snap = [n.series[i] for n in nets]
        rows.append({"week": round(snap[0]["week"]),
                     **{k: [s[k] for s in snap] for k in ("active", "candidates", "k_small", "max_bounty", "waiting")},
                     "k3": mean(1.0 if s["k_small"] >= 3 else 0.0 for s in snap),
                     "withdrawn": [s["withdrawn"] / max(1, s["submitted"]) for s in snap]})
    st = [n.stats for n in nets]

    def first_week(n: Net, k: int) -> float:
        return next((s["week"] for s in n.series if s["k_small"] >= k), float("nan"))

    month: Dict[str, List[float]] = {k: [] for k in ("net", "fees", "overhead", "slashed", "fixed", "capital")}
    for n in nets:  # every validator that was active at some point, per month registered
        for v in n.reg.validators.values():
            if v.active_at is None:
                continue
            m = max(1e-9, (n.t - v.registered_at) / MONTH)
            month["net"].append(n.validator_net(v) / m)
            month["fees"].append(v.acct.fees / m)
            month["overhead"].append(v.acct.overhead / m)
            month["slashed"].append(v.acct.slashed / m)
            month["fixed"].append(w.enclave.fixed_month)
            month["capital"].append(v.posted * w.capital_rate / 12)
    return {"rows": rows, "nets": nets,
            "waited": [s["waited"] / s["submitted"] for s in st],
            "withdrawn": [s["withdrawn"] / s["submitted"] for s in st],
            "days_to_final": [s["final_days"] / max(1, s["final"]) for s in st],
            "bad_per_100_paid": [100 * s["bad_merged"] / max(1, s["paid"]) for s in st],
            "qualified": [s["qualified"] for s in st], "joined": [s["joined"] for s in st],
            "qualify_days": [s["qualify_days"] / s["qualified"] for s in st if s["qualified"]],
            "qualify_failed": [s["qualify_failed"] for s in st],
            "k_shares": {k: [s[f"k{k}"] / max(1, s["drawn"]) for s in st] for k in (1, 3, 5, 7)},
            "reversed": [s["reversed"] for s in st], "challenges": [s["challenges"] for s in st],
            "frozen_at_end": [len(n.ch_waiting) for n in nets],
            "week_k3": [first_week(n, 3) for n in nets], "week_k7": [first_week(n, 7) for n in nets],
            "stepped_down": [s["stepped_down"] / max(1, s["drawn"]) for s in st],
            "shadow_spend": [s["shadow_pool_spend"] for s in st], "month": month}


def growth_table(seeds: Sequence[int], p: Params = PARAMS, w: World = WORLD) -> str:
    g = growth(seeds, p, w)
    out = [f"### Growth from one validator ({len(seeds)} seeds; one newcomer a week, {w.subs_week:g} submissions a "
           "week)", "",
           "| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | "
           "Waiting submissions | Withdrawn so far |", "|---|---|---|---|---|---|---|---|"]
    for r in g["rows"]:
        out.append(f"| {r['week']} | {_ms(r['active'])} | {_ms(r['candidates'])} | {mean(r['k_small']):.1f} | "
                   f"{100 * r['k3']:.0f} % | ${mean(r['max_bounty']):,.0f} | {_ms(r['waiting'])} | "
                   f"{100 * mean(r['withdrawn']):.0f} % |")
    k3 = [x for x in g["week_k3"] if x == x]
    k7 = [x for x in g["week_k7"] if x == x]
    ks, mo = g["k_shares"], g["month"]
    shares = " / ".join(f"{100 * mean(ks[k]):.0f} %" for k in (1, 3, 5, 7))
    out += ["", "| Over the year | |", "|---|---|",
            f"| Submissions that waited for a panel | {_pct(g['waited'])} |",
            f"| ...withdrawn after {w.withdraw_after_days:g} days of waiting | {_pct(g['withdrawn'])} |",
            f"| Days from submission to final verdict | {_ms(g['days_to_final'])} |",
            f"| Bad fixes merged per 100 paid | {_ms(g['bad_per_100_paid'], 2)} |",
            f"| Panels drawn at k = 1 / 3 / 5 / 7 | {shares} |",
            f"| Draws whose k the caps lowered (from the largest odd number of eligible validators) | "
            f"{_pct(g['stepped_down'])} |",
            f"| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week {mean(k3):.0f} ({len(k3)} of "
            f"{len(seeds)} runs) / week {mean(k7):.0f} ({len(k7)} of {len(seeds)} runs) |" if k3 and k7 else
            f"| First snapshot with k ≥ 3 / k = 7 | {len(k3)} / {len(k7)} of {len(seeds)} runs reach it |",
            f"| Newcomers / qualified in the year | {_ms(g['joined'])} / {_ms(g['qualified'])} |",
            f"| Days from registration to activation | {_ms(g['qualify_days'])} |",
            f"| Failed qualification attempts | {_ms(g['qualify_failed'])} |",
            f"| Challenges / verdicts reversed / challenges still frozen at year's end | {_ms(g['challenges'])} / "
            f"{_ms(g['reversed'])} / {_ms(g['frozen_at_end'])} |",
            f"| Shadows' usage repaid from the sponsors' pool | ${mean(g['shadow_spend']):,.0f} |",
            f"| An activated validator's month: fees ${mean(mo['fees']):.2f}, less overhead "
            f"${mean(mo['overhead']):.2f}, "
            f"slashes for outages ${mean(mo['slashed']):.2f}, fixed costs ${mean(mo['fixed']):.2f}, the bond's capital "
            f"${mean(mo['capital']):.2f} | net **${mean(mo['net']):,.2f}** |"]
    return "\n".join(out)


# ---------- the attackers ----------

def _attack_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    pa = net.parties.get(a.party)
    nodes = net.party_validators(a.party)
    mine = [s for s in net.subs.values() if s.party == a.party]
    drawn = [s for s in mine if s.draw is not None]
    maj = sum(1 for s in drawn
              if sum(1 for vid, _, _ in s.judges if net.reg.validators[vid].party == a.party) >= (s.k + 1) // 2)
    return {"submitted": pa.submitted if pa else 0, "bad_paid": pa.bad_paid if pa else 0,
            "adrs": pa.adrs_passed if pa else 0, "slashed": sum(v.acct.slashed for v in nodes),
            "checks": sum(v.acct.checks for v in nodes) / max(1, len(nodes)),
            "caught": net.stats["receipts_upheld"], "silences": net.stats["silences"],
            "suspensions": sum(v.suspensions for v in nodes), "majority": maj / len(drawn) if drawn else 0.0,
            "own_drawn": len(drawn),
            "adrs_small": sum(1 for s in mine if s.tier == "constitution" and s.final
                              and len(s.draw.pool) < net.p.K_MAX),
            "frozen": sum(1 for s in mine if s.challenge is not None and s.challenge.state == "waiting"),
            "qualified": net.stats["qualified"]}


FULL_BOND = replace(PARAMS, FALSE_VERDICT_SLASH_BPS=10_000)
D4_READING = replace(PARAMS, CHALLENGE_WAITS_FOR_FULL=True)
FIXED_SEED = replace(PARAMS, SEED_FROM_LATER_BLOCK=False)

ATTACKERS: List[Tuple[str, Callable[[bool], A.Actor], Optional[Params], str]] = [
    ("Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families", lambda h: A.Sybil(h), None, "sybil"),
    ("Sybil: 10 of 30 validators, one host, TEE type and family",
     lambda h: A.Sybil(h, hosts=1, tees=1, families=1), None, "sybil"),
    ("Colluding lone validator (the genesis, bonded $100)", lambda h: A.LoneColluder(h), None, "colluder"),
    ("Seed grinder (v3's seed: a later block)", lambda h: A.SeedGrinder(h), None, "grinder"),
    ("Seed grinder (counterfactual: the seed fixed at the seal)", lambda h: A.SeedGrinder(h), FIXED_SEED, "grinder"),
    ("Silent judge (bribed on 10 % of its draws)", lambda h: A.SilentJudge(h), None, "silent"),
    ("Fee farmer (10 idle nodes at the bond floor; twin: one node)", lambda h: A.FeeFarmer(h), None, "farmer"),
    ("Constitution coalition (5 early validators)", lambda h: A.ConstitutionCoalition(h), None, "coalition"),
    ("Constitution coalition (3 early validators)", lambda h: A.ConstitutionCoalition(h, nodes=3), None, "coalition"),
]
SENSITIVITY: List[Tuple[str, Callable[[bool], A.Actor], Optional[Params], str]] = [
    ("Sybil, spread (whole bond slashed per false verdict)", lambda h: A.Sybil(h), FULL_BOND, "sybil"),
    ("Colluding lone validator (whole bond)", lambda h: A.LoneColluder(h), FULL_BOND, "colluder"),
    ("Colluding lone validator (D4's reading: challenges wait for CHALLENGE_K)", lambda h: A.LoneColluder(h),
     D4_READING, "colluder"),
    ("Colluding lone validator (1 bad fix a week, not 5)", lambda h: A.LoneColluder(h, bad_week=1.0), None,
     "colluder"),
    ("Seed grinder (whole bond)", lambda h: A.SeedGrinder(h), FULL_BOND, "grinder"),
]


def _got(kind: str, r: Dict[str, object]) -> str:
    if kind == "sybil":
        return (f"{r['bad_paid']:.1f} bad fixes paid of {r['submitted']:.0f}; a majority on "
                f"{100 * r['majority']:.0f} % of its own panels; {r['caught']:.1f} false verdicts proven")
    if kind in ("colluder", "grinder"):
        return (f"{r['bad_paid']:.1f} bad fixes paid of {r['submitted']:.0f} attempts; {r['caught']:.1f} false "
                f"verdicts proven, {r['frozen']:.1f} challenges still frozen; {r['qualified']:.1f} newcomers "
                f"qualified (twin: {r['twin_qualified']:.1f})")
    if kind == "silent":
        return f"{r['silences']:.1f} silences, suspended {r['suspensions']:.1f} times (k never shrank)"
    if kind == "farmer":
        return f"{r['checks']:.1f} counted checks a node"
    if kind == "coalition":
        return (f"{r['adrs']:.1f} ADRs passed of {r['submitted']:.0f}; passed while fewer than K_MAX were eligible: "
                f"{r['adrs_small']:g}")
    return ""


def attackers(seeds: Sequence[int], rows=None) -> List[Tuple[str, Dict[str, object], str]]:
    return [(name, A.against_twin(make, seeds, p=p, metrics=_attack_metrics), kind)
            for name, make, p, kind in (rows if rows is not None else ATTACKERS)]


def attackers_table(seeds: Sequence[int], data=None, sensitivity=None) -> str:
    """`data`: `attackers(seeds)` already computed; `sensitivity`: the same for SENSITIVITY (an empty list omits it)."""
    head = ["| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | "
            "What it got |", "|---|---|---|---|---|---|"]
    out = [f"### Each attacker against its honest twin ({len(seeds)} seeds; a year; returns in $, with bonds' capital, "
           "running costs, fees, slashes, attempt fees and checks counted)", ""] + head
    for name, r, kind in (data if data is not None else attackers(seeds)):
        out.append(f"| {name} | {r['diff']:,.0f} ± {2 * r['se']:,.0f} | {_verdict(r['diff'], r['se'])} | "
                   f"{r['attacker']:,.0f} | {r['twin']:,.0f} | {_got(kind, r)} |")
    sens = sensitivity if sensitivity is not None else attackers(seeds, SENSITIVITY)
    if not sens:
        return "\n".join(out)
    out += ["", f"### Sensitivity ({len(seeds)} seeds)", ""] + head
    for name, r, kind in sens:
        out.append(f"| {name} | {r['diff']:,.0f} ± {2 * r['se']:,.0f} | {_verdict(r['diff'], r['se'])} | "
                   f"{r['attacker']:,.0f} | {r['twin']:,.0f} | {_got(kind, r)} |")
    return "\n".join(out)


# ---------- the sybil's share ----------

def sybil_shares(seeds: Sequence[int], sizes: Sequence[int] = (3, 6, 10, 20), p: Optional[Params] = None
                 ) -> List[Tuple[int, str, Dict[str, float]]]:
    out = []
    for n in sizes:
        for spread, kw in (("spread", {}), ("one host", dict(hosts=1, tees=1, families=1))):
            ms: Dict[str, List[float]] = {}
            for s in seeds:
                a = A.Sybil(nodes=n, **kw)
                net = A.run(a, s, p)
                m = _attack_metrics(net, a)
                allp = [x for x in net.subs.values() if x.draw is not None and x.k >= 3 and x.tier == "issue"]
                m["any_majority"] = sum(1 for x in allp if sum(1 for vid, _, _ in x.judges
                                                               if net.reg.validators[vid].party == a.party)
                                        >= (x.k + 1) // 2) / max(1, len(allp))
                for k, v in m.items():
                    ms.setdefault(k, []).append(v)
            out.append((n, spread, {k: mean(v) for k, v in ms.items()}))
    return out


def sybil_table(seeds: Sequence[int], data=None) -> str:
    out = [f"### The sybil's majorities by its share ({len(seeds)} seeds; 20 honest validators, newcomers at half a "
           "validator a week; its bad fixes at 2 a week)", "",
           "| Sybil validators (share at the start) | Spread | Majority of its own panels | Majority of any panel "
           "with k ≥ 3 | Bad fixes paid | False verdicts proven |", "|---|---|---|---|---|---|"]
    for n, spread, m in (data if data is not None else sybil_shares(seeds)):
        out.append(f"| {n} ({100 * n / (n + 21):.0f} %) | {spread} | {100 * m['majority']:.1f} % | "
                   f"{100 * m['any_majority']:.2f} % | {m['bad_paid']:.1f} | {m['caught']:.1f} |")
    return "\n".join(out)


# ---------- the watcher's dilemma ----------

AUDIT_RATES = (0.0, 0.01, 0.02, 0.05, 0.10, 0.20)


def watchers(seeds: Sequence[int], rates: Sequence[float] = AUDIT_RATES, kind: str = "lazy", weeks: int = 26,
             base: Optional[Params] = None):
    out = []
    for volunteers in (False, True):
        for rate in rates:
            p = replace(base or PARAMS, AUDIT_RATE=rate)

            def metrics(net: Net, a: A.Actor) -> Dict[str, float]:
                st = net.stats
                return {"cheats": st["cheats"], "caught": st["receipts_upheld"],
                        "audit_cost": st["audit_pay"] / max(1, st["drawn"]), "audits": st["audits"]}

            w = replace(A.WatchedCheater(volunteers=volunteers).world(), weeks=weeks)
            r = A.against_twin(lambda h: A.WatchedCheater(h, kind=kind, volunteers=volunteers), seeds, p=p, w=w,
                               metrics=metrics)
            out.append((volunteers, rate, r))
    return out


def watchers_table(seeds: Sequence[int], kind: str = "lazy", weeks: int = 26, data=None) -> str:
    out = [f"### The watcher's dilemma ({len(seeds)} seeds; {weeks} weeks; one {kind} cheater among 16 validators, "
           "cheating on 10 % of its draws)", "",
           "| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | "
           "Cheating | Audit cost per check |", "|---|---|---|---|---|---|---|"]
    for volunteers, rate, r in (data if data is not None else watchers(seeds, kind=kind, weeks=weeks)):
        caught = r["caught"] / r["cheats"] if r["cheats"] else 0.0
        pays = "pays" if r["diff"] - 2 * r["se"] > 0 else _verdict(r["diff"], r["se"])
        out.append(f"| {'yes' if volunteers else 'none'} | {100 * rate:g} % | {r['cheats']:.1f} | "
                   f"{100 * caught:.0f} % | {r['diff']:,.1f} ± {2 * r['se']:,.1f} | {pays} | ${r['audit_cost']:.4f} |")
    return "\n".join(out)


def phase1(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None) -> str:
    sweep = sweep or seeds
    return "\n\n".join([growth_table(seeds), attackers_table(seeds), sybil_table(sweep), watchers_table(sweep),
                        watchers_table(sweep, kind="bribed")])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval")
    ap.add_argument("what", choices=("growth", "attackers", "sybil", "audits", "levels", "pricing", "scores", "all", "params"))
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--sweep-seeds", type=int, help="seeds for the sybil and audit sweeps (default: --seeds)")
    a = ap.parse_args(argv)
    seeds = range(1, a.seeds + 1)
    sweep = range(1, a.sweep_seeds + 1) if a.sweep_seeds else seeds
    if a.what == "growth":
        print(growth_table(seeds))
    elif a.what == "attackers":
        print(attackers_table(seeds))
    elif a.what == "sybil":
        print(sybil_table(sweep))
    elif a.what == "audits":
        print(watchers_table(sweep) + "\n\n" + watchers_table(sweep, kind="bribed"))
    elif a.what == "levels":
        from .levels import levels_report
        print(levels_report(seeds))
    elif a.what == "pricing":  # task 1.4: market pricing (pof.sim.openval.pricing)
        from .pricing import pricing_tables
        print(pricing_tables(seeds))
    elif a.what == "scores":
        from .scores import tables
        print(tables(seeds))
    elif a.what == "params":
        print("\n".join(f"| `{k}` | {v} |" for k, v in PARAMS.table()))
    else:
        from .params import RULES
        if RULES == "v1":
            from .full import full_report
            print(full_report(seeds, sweep if a.sweep_seeds else None))
        elif RULES == "v2r1":
            from .rerun import full_report as v2_report
            print(v2_report(seeds, sweep if a.sweep_seeds else None))
        else:
            from .round2 import full_report as v3_report
            print(v3_report(seeds, sweep if a.sweep_seeds else None))
    return 0
