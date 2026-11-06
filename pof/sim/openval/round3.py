"""Task group 8 of #132 (proof-of-fix#141, round 3): round 3's criteria, the silence-slash sweep and the deposit's
honest cost, for reports/open-validators-v3.1.md (an addendum to reports/open-validators-v3.md).

    python3 -m pof.sim market validators --round3 --seeds 40 --jobs 4   this addendum's tables

Round 3 changes no protocol rule (design.md, "Revision 2026-11-03, round 3"). Its parameters (`params.V2R3`, the
defaults) differ from round 2's (`params.V2R2`) only in how D17's criteria are read, so the simulation gives report v3's
numbers, run for run. What this module adds:
- `rejudge` (tasks 8.1 and 8.4): D17's acceptance table from report v3's published numbers (`V3`), judged under
  round 3's criteria (V2R3: "not shown to gain", `LONE_CATCH_SHARE` on the lone validator's own verdicts,
  `WAIT_CROWD_MAX` 20 %) or round 2's (V2R2, the switch). Under V2R2 it gives v3's verdicts (tested), so v3's table is
  re-judged without re-running v3. The judging is `round2`'s (`gain_ok`, `at_least`, `at_most`), which
  `round2.acceptance` also uses for a full run under either set;
- `SWEEP_X` (task 8.2): the silence slash and the slash for a sealed vote not revealed at the larger of $5 and x % of
  the bounty (`SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS`), x of 0, 1, 2 and 5 % (and 10 %, beyond the spec's
  range, for reference): the silent judge and the withholder bribed 5 % and 10 % of the bounty beside their twins, and
  the honest validator's month on the market;
- `HonestAuthor` (task 8.3): the deposit's honest cost.

`collect` runs the sections (`jobs` > 1: one process each; the numbers don't change) and `render` prints them.
`quick=True` runs x of 0 and 5 % on few seeds, for the tests: not a result to read. Simulated only (rule 1): nothing
here opens a connection.
"""

from __future__ import annotations

import multiprocessing
import random
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import panels as D
from . import pricing as PR
from . import rerun as RR
from . import round2 as R2M
from .net import CONSTITUTION, Net
from .params import BPS, WEEK, WORLD, V2R2, V2R3, Params, World

NAN = float("nan")
R3 = V2R3
Criterion = R2M.Criterion
mean_se, at_most, at_least, loses = RR.mean_se, RR.at_most, RR.at_least, RR.loses
_ms, _pct, _pm = RR._ms, RR._pct, R2M._pm


# ---------- report v3's published numbers (reports/open-validators-v3.md), for the re-judged table ----------

def parse_pm(text: str) -> Tuple[float, float]:
    """"-1,976 ± 53" or "+2.7 ± 3.9" (a mean ± 2 SE, as the reports print it) -> (mean, SE)."""
    m = re.fullmatch(r"\s*([-+−]?[\d,]*\.?\d+)\s*(?:%\s*)?±\s*([\d,]*\.?\d+)\s*%?\s*", text)
    if not m:
        raise ValueError(text)
    num = lambda s: float(s.replace(",", "").replace("−", "-"))  # noqa: E731
    return num(m.group(1)), num(m.group(2)) / 2


# Each row: (the attacker, its return − twin's as printed, a text that identifies its line in report v3). D17's
# counted attackers (report v3, "The attackers counted"), in the acceptance table's order.
V3_ROWS: Dict[str, List[Tuple[str, str, str]]] = {
    "open": [
        ("Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families", "-21,535 ± 2,510",
         "| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families |"),
        ("Sybil: 10 of 30 validators, one host, TEE type and family", "-17,969 ± 1,752",
         "| Sybil: 10 of 30 validators, one host, TEE type and family |"),
        ("Seed grinder (v3's seed: a later block)", "-272 ± 48", "| Seed grinder (v3's seed: a later block) |"),
        ("Fee farmer (10 idle nodes at the bond floor; twin: one node)", "-545 ± 3",
         "| Fee farmer (10 idle nodes at the bond floor; twin: one node) |"),
        ("Colluding genesis (two audits of every k = 1 verdict, 5 bad fixes a week)", "-247 ± 41",
         "two audits of every k = 1 verdict**, 5 bad fixes a week |"),
        ("Silent (never seals): `SILENCE_SLASH` $5", "-14 ± 9", "| **Silent (never seals): `SILENCE_SLASH` $5"),
        ("Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5", "-15 ± 9",
         "| **Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5"),
        ("Constitution coalition: 5 early validators, 21 for adding ADRs, a $15 deposit", "-280 ± 147",
         "| 5 early validators: **21 for adding ADRs, a $15 deposit (the design)** |"),
        ("Constitution coalition: 3 early validators, 21 for adding ADRs, a $15 deposit", "-431 ± 145",
         "| 3 early validators: **21 for adding ADRs, a $15 deposit (the design)** |"),
        ("Constitution coalition: 5 early, escalated fixes to issues they fund, 21, a $15 deposit", "-280 ± 147",
         "sending escalated fixes to issues they fund themselves: **21, a $15 deposit to the sponsors' pool"),
        ("Coalition of removals: 5 early, from 14 with a $15 deposit, three types even", "-456 ± 103",
         "| **5 early validators, removals from 14 with a $15 deposit (the design)**; three types, even;"),
        ("Coalition of removals: the same, three types skewed", "-505 ± 97",
         "| the same, three types skewed; they remove TDX (40 % of newcomers) |"),
        ("D13's lazy cheater (audits at 10 %, no volunteers)", "-3,838.7 ± 587.4", "| none | 10 % | 28.4 | 11 % |"),
        ("D13's bribed cheater (audits at 10 %, no volunteers)", "-858.8 ± 319.8", "| none | 10 % | 6.7 | 11 % |"),
    ],
    "pricing": [
        ("Cartel: 6 validators refusing half their draws (design)", "-1,976 ± 53",
         "| Cartel: 6 validators refusing half their draws | design |"),
        ("Spammer: a fix a day to a $625 bounty no panel can judge yet (design)", "-502 ± 71",
         "| Spammer: a fix a day to a $625 bounty no panel can judge yet | design |"),
        ("Spammer: a bad fix a day, judged (design)", "-915 ± 28", "| Spammer: a bad fix a day, judged | design |"),
        ("Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design)", "+2.7 ± 3.9",
         "| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs | design |"),
        ("Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) (design)", "-0.1 ± 2.3",
         "| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) | design |"),
        ("Fee farmer: 10 idle validators at the bond floor (twin: one) (design)", "-402 ± 21",
         "| Fee farmer: 10 idle validators at the bond floor (twin: one) | design |"),
    ],
    "levels": [
        ("Test liar, after C is switched on by ADR: 1 of 15, 2 bad fixes a week", "-4,809 ± 505",
         "| Test liar, after C is switched on by ADR: 1 of 15, every other validator at C but the genesis (A); 2 bad "
         "fixes a week |"),
        ("Answer shopper, after C is switched on by ADR: 1 of 15 at C, 1 in 10", "-13 ± 1",
         "| **Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in "
         "10 (counted; twin: calls once, same fixes)** |"),
        ("Chip breaker at launch: the genesis at B, $1,000 device", "-1,500 ± 57",
         "forging on half its bad-fix draws, $1,000 device |"),
        ("Chip breaker at launch: the genesis at B, $50 device", "-550 ± 57",
         "| Chip breaker at launch: the same, a $50 device |"),
        ("Chip breaker at launch: 1 of a grown network, $50 device", "-14,166 ± 1,492",
         "| Chip breaker at launch: 1 of a grown network (⅓ A, ⅓ B; the ⅓ at C refused), a $50 device |"),
        ("Chip breaker at launch: the same, forging on every bad-fix draw", "-22,003 ± 2,142",
         "| Chip breaker at launch: the same, forging on every bad-fix draw |"),
        ("Chip breaker, after C is switched on by ADR: 1 of 15, $50 device", "-19,830 ± 1,644",
         "| Chip breaker, after C is switched on by ADR: 1 of 15 (⅓ A, ⅓ B, ⅓ C), a $50 device |"),
    ],
    "scores": [
        ("Herders: `mid` (90 %), receipts detectable", "-3,011 ± 1,202", "| `mid` (90 %), receipts detectable |"),
        ("Herders: `mid` (90 %), not detectable (upper bound)", "-23 ± 4",
         "| `mid` (90 %), not detectable (upper bound) |"),
        ("Herders: `weak` (68 %), receipts detectable", "-1,957 ± 547", "| `weak` (68 %), receipts detectable |"),
        ("Herders: `weak` (68 %), not detectable (upper bound)", "+0.2 ± 0.7",
         "| `weak` (68 %), not detectable (upper bound) |"),
        ("Herders: `mid`, not detectable, at a $0.25 fee", "-347 ± 31",
         "| `mid`, not detectable, at a $0.25 fee (`FEE_CEILING`) |"),
        ("Herders: `weak`, not detectable, at a $0.25 fee", "-5.3 ± 3.3",
         "| `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) |"),
        ("Herders on the market: `mid` (90 %), not detectable", "-340 ± 33",
         "| `mid` (90 %), not detectable, the design's market |"),
        ("Herders on the market: `weak` (68 %), not detectable", "-4.7 ± 2.4",
         "| `weak` (68 %), not detectable, the design's market |"),
    ],
}
# The other deciding numbers, as printed, with the text that identifies their line in report v3
V3: Dict[str, Tuple[str, str]] = {
    "col_all": ("93.3 % ± 3.9 %", "two audits of every k = 1 verdict**, 5 bad fixes a week |"),  # 195 of 209
    "col_own": ("98.4 % ± 1.8 %", "two audits of every k = 1 verdict**, 5 bad fixes a week |"),  # 184 of 187
    "col_counts": ("195 of 209", "| The colluding lone validator doesn't gain"),
    "col_own_counts": ("184 of 187", "of its own lone bad verdicts are reversed before payment** (184 of 187)"),
    "crowd": ("11.3 ± 4.9 %", "| **Submissions that waited for a panel** (`WAIT_CROWD_MAX` 15 %) |"),
    "fee": ("1.20 ± 0.04 ×", "| **Round 2's rules (the design): every wait counts, once** | 1.20 ± 0.04 × |"),
    "collapsed": ("0 of 40", "| **Round 2's rules (the design): every wait counts, once** | 1.20 ± 0.04 × |"),
    "shop_1": ("-13 ± 1", "| Answer shopping, the trust point:"),
    "shop_3": ("+174 ± 46", "| Answer shopping, the trust point:"),
    "shop_125": ("-16 ± 1", "| Answer shopping, the trust point:"),
    "sybil": ("a majority on 0.00 % of panels", "| A sybil at or under `SYBIL_SHARE` (12.5 %)"),
    "const": ("adding ADRs and escalated fixes passed below 21, all runs: 0", "| The constitution waits for the network"),
    "removals": ("removals passed below 14: 0", "| The constitution waits for the network"),
    "growth": ("40 of 40 runs, at week 6 ± 1", "| The network still grows"),
}
V3_VERDICTS = ["met", "not met", "met", "not met", "met", "met", "not met", "met", "met", "not met", "met", "met", "met",
               "not met"]  # report v3's acceptance table, in order (tested against it)


def _row_vals(key: str) -> List[Tuple[str, float, float]]:
    return [(name, *parse_pm(v)) for name, v, _ in V3_ROWS[key]]


def _share(text: str) -> Tuple[float, float]:
    m, se = parse_pm(text)
    return m / 100, se / 100


def rejudge(p: Params = R3) -> List[Criterion]:
    """D17's acceptance criteria on report v3's published numbers, judged as `p` says (round 3's V2R3, or round 2's
    V2R2, which gives v3's own verdicts). The judging is round2's, the same a full run's `round2.acceptance` uses."""
    words, tol = R2M.gain_words(p)
    out: List[Criterion] = []
    for name, key in ((f"Each open-validator attacker {words} against its honest twin", "open"),
                      (f"Each pricing attacker {words} against its honest twin", "pricing"),
                      (f"Each proof-level attacker {words} against its honest twin (answer shopping at 1 in 10; "
                       "the level C rows after C is switched on by ADR)", "levels"),
                      (f"Each scoring attacker (the herders) {words} against its honest twin", "scores")):
        met, why, note = R2M.rows_dont_gain(_row_vals(key), p.GAIN_TOLERANCE, p.GAIN_TEST)
        out.append(Criterion(name, met, why, tol, note))
    out.append(Criterion(
        f"A sybil at or under `SYBIL_SHARE` ({100 * p.SYBIL_SHARE:g} %) never holds a majority of a panel of k ≥ 3, "
        "in any run", True, "3 validators (12.5 %), spread and on one host: " + V3["sybil"][0] + " (v3)", "0 runs"))
    out.append(Criterion("A sybil above the share: the report gives how often it holds a majority, what it passes, "
                         "and how often it's caught", True, "reported in v3 (22 %, 32 % and 49 %)", "reported"))
    dm, dse = parse_pm(V3_ROWS["open"][4][1])
    own, ose = _share(V3["col_own"][0])
    alls, ase = _share(V3["col_all"][0])
    c, cse = (own, ose) if p.LONE_CATCH_COUNT == "own" else (alls, ase)
    which = ("of the bad fixes it passes itself, as the lone judge," if p.LONE_CATCH_COUNT == "own"
             else "of the bad fixes it passes")
    out.append(Criterion(
        f"The colluding lone validator {words}, and at least `LONE_CATCH_SHARE` ({100 * p.LONE_CATCH_SHARE:g} %) "
        f"{which} are reversed before any payment (pooled), with two audits",
        R2M.gain_ok(dm, dse, p) and at_least(c, cse, p.LONE_CATCH_SHARE),
        f"return − twin's {_pm(dm, dse)} $ ({words}: {R2M.gain_cell(dm, dse, p.GAIN_TOLERANCE, p.GAIN_TEST)}); its own "
        f"verdicts reversed before payment {V3['col_own'][0]} ({V3['col_own_counts'][0]}); every bad fix of its "
        f"accomplice, whoever judged it, {V3['col_all'][0]} ({V3['col_counts'][0]})"
        + ("; counted: its own (round 3), the rest the named trust point" if p.LONE_CATCH_COUNT == "own"
           else "; counted: every one (round 2)"),
        f"{tol}; share − 2 SE ≥ {100 * p.LONE_CATCH_SHARE:g} %", R2M.loses_cell(dm, dse)))
    out.append(Criterion(
        f"The constitution waits for the network: no adding ADR or escalated fix passes while fewer than "
        f"{p.CONSTITUTION_MIN_ELIGIBLE} validators are eligible, and no removal while fewer than "
        f"{p.REMOVAL_MIN_ELIGIBLE}, in any run", True, V3["const"][0] + "; " + V3["removals"][0] + " (v3)", "0 runs"))
    fm, fse = parse_pm(V3["fee"][0].replace(" ×", ""))
    out.append(Criterion(
        f"The fee settles within `FEE_MARGIN` ({100 * p.FEE_MARGIN:g} %) above break-even and at least break-even less "
        "one step, and no run collapses",
        at_most(fm, fse, 1 + p.FEE_MARGIN) and at_least(fm, fse, 1 - p.FEE_STEP) and V3["collapsed"][0] == "0 of 40",
        f"fee / break-even over the last 13 weeks {V3['fee'][0]}; {V3['collapsed'][0]} runs collapsed (v3)",
        f"{1 - p.FEE_STEP:.2f} ≤ ratio ± 2 SE ≤ {1 + p.FEE_MARGIN:.2f}; 0 runs collapse"))
    wm, wse = _share(V3["crowd"][0])
    out.append(Criterion(
        f"Everyone crowds into one model: at most `WAIT_CROWD_MAX` ({100 * p.WAIT_CROWD_MAX:g} %) of submissions wait",
        at_most(wm, wse, p.WAIT_CROWD_MAX), f"{V3['crowd'][0]} waited (upper bound {100 * (wm + 2 * wse):.1f} %)",
        f"mean + 2 SE ≤ {100 * p.WAIT_CROWD_MAX:g} %"))
    out.append(Criterion("The network still grows: a small bounty reaches k ≥ 3 within the year in every run", True,
                         V3["growth"][0] + " (v3)", "every run"))
    sm, sse = parse_pm(V3["shop_1"][0])
    out.append(Criterion(
        f"Answer shopping, the trust point: it {words} at 1 in 10; at 3 in 10 the report gives its gain",
        R2M.gain_ok(sm, sse, p),
        f"at 1 in 10: {V3['shop_1'][0]} $; at 3 in 10 (reported): {V3['shop_3'][0]} $; at #125's measured room "
        f"(reported): {V3['shop_125'][0]} $", f"{tol} at 1 in 10", R2M.loses_cell(sm, sse)))
    out.append(Criterion("Every earlier criterion holds or is named", True,
                         "named, not re-run (D15, gap 20), as in v3", "named"))
    failed = [x.name for x in out if not x.met]
    out.append(Criterion(
        "Adopt the k table, windows, bonds, caps and pricing bounds (all of the above)", not failed,
        f"{len(failed)} of {len(out)} criteria not met" if failed else "every criterion met", "all"))
    return out


def rejudged_md() -> str:
    """The acceptance table under round 3's criteria beside round 2's, both on report v3's numbers."""
    r2, r3 = rejudge(V2R2), rejudge(R3)
    out = ["### Acceptance criteria for open validators: report v3's numbers under round 2's and round 3's criteria (40 "
           "seeds; ± 2 standard errors)", "",
           "| Criterion (round 3's words) | v3 (round 2's criteria) | v3.1 (round 3's criteria) | Threshold (round 3) "
           "| What decides it (round 3) | Loses (#141's criterion) |", "|---|---|---|---|---|---|"]
    for a, b in zip(r2, r3):
        out.append(f"| {b.name} | {a.verdict} | **{b.verdict}** | {b.threshold} | {b.decides} | {b.loses or '–'} |")
    n2 = sum(1 for c in r2[:-1] if c.met)
    n3 = sum(1 for c in r3[:-1] if c.met)
    out += ["", f"Met: {n2} of {len(r2) - 1} under round 2's criteria (v3), {n3} of {len(r3) - 1} under round 3's. The "
            "numbers are report v3's, as printed there; round 3's rules and seeds are round 2's, so nothing is re-run."]
    return "\n".join(out)


def rejudged_rows_md() -> str:
    """Every counted attacker under both criteria: the rows whose verdict changes, and why."""
    out = ["### The counted attackers under both criteria (report v3's numbers)", "",
           "| Attacker | Return − twin's ($, ± 2 SE) | Lower / upper bound | Doesn't gain (round 2) | Not shown to gain "
           "(round 3) | Loses |", "|---|---|---|---|---|---|"]
    for key in ("open", "pricing", "levels", "scores"):
        for name, m, se in _row_vals(key):
            out.append(f"| {name} | {_pm(m, se)} | {m - 2 * se:+,.1f} / {m + 2 * se:+,.1f} | "
                       f"{R2M.gain_cell(m, se, R3.GAIN_TOLERANCE, 'doesnt_gain')} | "
                       f"{R2M.gain_cell(m, se, R3.GAIN_TOLERANCE, 'not_shown')} | {R2M.loses_cell(m, se)} |")
    return "\n".join(out)


# ---------- the silence-slash sweep (task 8.2) ----------

SWEEP_X: Tuple[float, ...] = (0.0, 1.0, 2.0, 5.0)  # % of the bounty: the spec's range (task 8.2)
SWEEP_EXTRA: Tuple[float, ...] = (10.0,)  # beyond it, for reference: the 10 % bribe's own share


def sweep_params(x: float, base: Params = R3) -> Params:
    """Both slashes at the larger of their flat $5 and x % of the bounty (each attacker and outage meets only one)."""
    bps = int(round(x * BPS / 100))
    return replace(base, SILENCE_SLASH_BPS=bps, SEALED_NO_REVEAL_SLASH_BPS=bps)


def x_label(x: float) -> str:
    if not x:
        return "a flat $5 (round 2; x = 0)"
    return f"max($5, {x:g} % of the bounty)" + (" (beyond the spec's range)" if x in SWEEP_EXTRA else "")


def sweep_xs(quick: bool) -> Tuple[float, ...]:
    return (SWEEP_X[0], SWEEP_X[-1]) if quick else SWEEP_X + SWEEP_EXTRA


BRIBED: List[Tuple[str, str, bool, float]] = [  # (key, label, sealed, bribe as a share of the bounty)
    ("silent_5", "Silent, bribed 5 % of the bounty", False, 0.05),
    ("silent_10", "Silent, bribed 10 % of the bounty", False, 0.10),
    ("withhold_5", "Seals, then withholds, bribed 5 %", True, 0.05),
    ("withhold_10", "Seals, then withholds, bribed 10 %", True, 0.10),
]


def s_bribed(seeds, quick, sealed: bool):
    xs = sweep_xs(quick)
    out = []
    for x in xs:
        p = sweep_params(x)
        for key, label, s, bribe in BRIBED:
            if s != sealed:
                continue
            r = A.against_twin(lambda h, s=s, b=bribe: A.SilentJudge(h, stall_value=b, sealed=s), seeds, p=p,
                               metrics=R2M.silent_metrics)
            out.append((x, key, label, r))
    return out


def month_run(seeds, p: Params, w: World) -> Dict[str, list]:
    """The honest validator's month on the market (`rerun.honest_breakdown`), and the fee against break-even."""
    r: Dict[str, list] = {}
    for s in seeds:
        net = PR.run_market(s, p, w)
        st = PR.settle(net)
        dead = st["active"] < 3
        r.setdefault("collapsed", []).append(1.0 if dead else 0.0)
        r.setdefault("fee", []).append(st["fee"])
        if not dead:
            r.setdefault("ratio", []).append(st["fee"] / st["break_even"])
            r.setdefault("break_even", []).append(st["break_even"])
        b = RR.honest_breakdown(net)
        for k, v in b.items():
            r.setdefault(k, []).append(v)
    return r


OUTAGES: List[Tuple[str, str, World]] = [
    ("before", "every outage before the seal (silence)", RR.MARKET_W),
    ("after", "every outage after the seal (withheld)", replace(RR.MARKET_W, outage_sealed=1.0)),
]


def s_month(seeds, quick, when: str):
    xs = sweep_xs(quick)
    w = next(w for k, _, w in OUTAGES if k == when)
    return [(x, month_run(seeds, sweep_params(x), w)) for x in xs]


def _cell(r: Dict[str, object]) -> str:
    return f"{_pm(r['diff'], r['se'])} ({R2M.gain_cell(r['diff'], r['se'], R3.GAIN_TOLERANCE, R3.GAIN_TEST)})"


def sweep_md(d: Dict[str, object], seeds) -> str:
    rows: Dict[Tuple[float, str], Dict[str, object]] = {}
    for x, key, _, r in list(d["silent"]) + list(d["withhold"]):
        rows[(x, key)] = r
    xs = sorted({x for x, _ in rows})
    out = [f"### A bribed silent judge and a bribed withholder, by the slash ({len(seeds)} seeds; a year; a grown "
           "network of 12 honest validators; bribed on 10 % of its draws; return − twin's in $, ± 2 SE, and whether "
           "it is not shown to gain)", "",
           "| Slash for silence and for a sealed vote not revealed | " + " | ".join(lab for _, lab, _, _ in BRIBED)
           + " | Slashed per bribed miss: silent 5 % / 10 % | Bribe a miss: 5 % / 10 % | Suspended a year (silent 5 %) |",
           "|---|" + "---|" * (len(BRIBED) + 3)]
    for x in xs:
        cells = [_cell(rows[(x, k)]) if (x, k) in rows else "–" for k, _, _, _ in BRIBED]
        s5, s10 = rows.get((x, "silent_5")), rows.get((x, "silent_10"))

        def per(r, k):
            return f"${r[k] / r['silences']:.2f}" if r and r.get("silences") else "–"
        susp = f"{s5['suspensions']:.1f}" if s5 else "–"
        out.append(f"| {x_label(x)} | " + " | ".join(cells) + f" | {per(s5, 'slashed')} / {per(s10, 'slashed')} | "
                   f"{per(s5, 'bribes')} / {per(s10, 'bribes')} | {susp} |")
    out += ["", "A bribed miss is a draw on which it was bribed and stayed silent (or withheld its sealed vote). "
            "Slashed per bribed miss: everything it was slashed in the year over its bribed misses, so its own honest "
            "outages (1 in 200 draws) add a little. Its twin is the same validator never bribed. x = 0 is round 2's "
            "design (report v3: silent −14 ± 9 and +311 ± 21, withholder −15 ± 9 and +310 ± 21)."]
    m_rows = []
    for when, label, _ in OUTAGES:
        for x, r in d[f"month_{when}"]:
            m_rows.append((when, label, x, r))
    out += ["", f"### An honest validator's month on the market, by the slash ({len(seeds)} seeds; 1 outage in 200 "
            "draws; honest validators active a month or more; $ a month; the fee over the last 13 weeks)", "",
            "| Outages | Slash | Slashes | Service fees | Net | Fee | Fee / break-even | Runs collapsed |",
            "|---|---|---|---|---|---|---|---|"]
    for when, label, x, r in m_rows:
        out.append(f"| {label} | {x_label(x)} | {_ms(r.get('slashed', []), 2, pre='$')} | "
                   f"{_ms(r.get('service', []), 2, pre='$')} | {_ms(r.get('net', []), 2, pre='$')} | "
                   f"{_ms(r['fee'], 3, pre='$')} | {_ms(r.get('ratio', []), 2, unit=' ×')} | "
                   f"{sum(r['collapsed']):.0f} of {len(r['collapsed'])} |")
    out += ["", "x = 0 is round 2's design (report v3: slashes $0.98 ± 0.05 a month and a net of $-1.43 ± 0.22 before "
            "the seal; $0.98 ± 0.05 and $-1.45 ± 0.22 after it). The market's validators expect the slash at their own "
            "draws' bounties when they decide to enter or stay (`pricing.outage_slash`)."]
    return "\n".join(out)


# ---------- the deposit's honest cost (task 8.3) ----------

class HonestAuthor(A.Actor):
    """Task 8.3: an honest author submitting good ADRs that add something (drawn from CONSTITUTION_MIN_ELIGIBLE) at
    `adrs_week`, each with ADR_DEPOSIT, to a grown network (`network` honest validators active beside the genesis, a
    newcomer a week). It runs no validator, and an ADR is worth nothing to it here: its return is what the ADRs cost
    it. Its twin: the same ADRs under `ADR_DEPOSIT` $0 (`deposit_cost`), so the difference is the deposits it forfeits."""
    name = "honest ADR author"
    party = "author"

    def __init__(self, honest: bool = False, adrs_week: float = 1.0, network: int = 24):
        super().__init__(honest)
        self.adrs_week, self.network = adrs_week, network

    def world(self) -> World:
        return replace(WORLD, initial_active=self.network)

    def setup(self, net: Net) -> None:
        rng = random.Random(D.h(net.seed, D.T_GRIND, 7))
        t = 0.0
        while True:
            t += rng.expovariate(self.adrs_week / WEEK)
            if t > net.w.horizon_h:
                break
            net.submit(t, 0.0, True, "author-solver", self.party, tier=CONSTITUTION)


def author_metrics(net: Net, party: str) -> Dict[str, float]:
    mine = [s for s in net.subs.values() if s.party == party and s.tier == CONSTITUTION]
    pa = net.parties.get(party)
    return {"submitted": len(mine), "expired": sum(1 for s in mine if s.state == "expired"),
            "judged": sum(1 for s in mine if s.draw is not None), "passed": sum(1 for s in mine if s.final),
            "rejected": sum(1 for s in mine if s.final is False),
            "pending": sum(1 for s in mine if s.final is None and s.state != "expired"),
            "forfeited": pa.forfeited if pa else 0.0, "net": net.party_net(party)}


DEPOSITS: Tuple[float, ...] = (15.0, 25.0)


def deposit_cost(seeds, quick=False) -> List[Tuple[float, Dict[str, list]]]:
    """For each deposit: the author's metrics, and its return − its twin's under ADR_DEPOSIT $0 (same seeds)."""
    out = []
    for dep in (DEPOSITS[:1] if quick else DEPOSITS):
        r: Dict[str, list] = {}
        for s in seeds:
            a = HonestAuthor()
            na = A.run(a, s, replace(R3, ADR_DEPOSIT=dep))
            nt = A.run(HonestAuthor(), s, replace(R3, ADR_DEPOSIT=0.0))
            ma, mt = author_metrics(na, a.party), author_metrics(nt, a.party)
            for k, v in ma.items():
                r.setdefault(k, []).append(v)
            # deposits still held at the year's end (ADRs in their notice) come back: counted as returned
            r.setdefault("diff", []).append(ma["net"] - mt["net"] + ma["pending"] * dep)
        out.append((dep, r))
    return out


def deposit_md(d, seeds) -> str:
    out = [f"### The deposit's honest cost ({len(seeds)} seeds; a year; an honest author submitting a good adding ADR "
           "a week, with the deposit, to the genesis and 24 honest validators, a newcomer a week; its twin: the same "
           "ADRs with no deposit)", "",
           "| Deposit | ADRs submitted / expired / judged / passed / rejected (a run) | Rejected of those decided, pooled "
           "(± 2 SE) | "
           "Forfeited a run | Forfeited per ADR submitted | Return − twin's ($ a year, ± 2 SE; deposits still held at the "
           "year's end counted as returned) |",
           "|---|---|---|---|---|---|"]
    for dep, r in d:
        rej, rse = RR.pooled(r["rejected"], [a + b for a, b in zip(r["passed"], r["rejected"])])
        sub = sum(r["submitted"])
        dm, dse = mean_se(r["diff"])
        out.append(f"| ${dep:g} | {mean(r['submitted']):.1f} / {mean(r['expired']):.1f} / {mean(r['judged']):.1f} / "
                   f"{mean(r['passed']):.1f} / {mean(r['rejected']):.2f} | {_pct(rej, 1)} ± {_pct(2 * rse, 1)} "
                   f"({sum(r['rejected']):.0f} of {sum(r['passed']) + sum(r['rejected']):.0f} decided) | "
                   f"${mean(r['forfeited']):.2f} | "
                   f"${sum(r['forfeited']) / max(1, sub):.3f} | {_pm(dm, dse)} |")
    out += ["", "D7's hand estimate: a good ADR is rejected when 3 or more of its 7 honest judges err, about 2.6 % of "
            "the time at 90 % accuracy, so about $0.39 an ADR at $15."]
    return "\n".join(out)


# ---------- collecting and printing ----------

SECTIONS: Dict[str, Callable] = {
    "silent": lambda seeds, quick: s_bribed(seeds, quick, False),
    "withhold": lambda seeds, quick: s_bribed(seeds, quick, True),
    "month_before": lambda seeds, quick: s_month(seeds, quick, "before"),
    "month_after": lambda seeds, quick: s_month(seeds, quick, "after"),
    "author": lambda seeds, quick: deposit_cost(seeds, quick),
}
ORDER = ("month_before", "month_after", "silent", "withhold", "author")


def _section(name: str, seeds: Tuple[int, ...], quick: bool):
    return SECTIONS[name](seeds, quick)


def collect(seeds: Sequence[int], quick: bool = False, jobs: int = 1) -> Dict[str, object]:
    seeds = tuple(seeds)
    d: Dict[str, object] = {"seeds": list(seeds), "quick": quick}
    if jobs > 1:  # forked workers (no program is run, rule 1); where fork doesn't exist, one process
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:
            jobs = 1
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs, mp_context=ctx) as ex:
            futs = {name: ex.submit(_section, name, seeds, quick) for name in ORDER}
            for name, fut in futs.items():
                d[name] = fut.result()
    else:
        for name in ORDER:
            d[name] = _section(name, seeds, quick)
    return d


def render(d: Dict[str, object]) -> str:
    seeds = d["seeds"]
    head = (f"# Open validators, v3.1: round 3's criteria and sweeps ({len(seeds)} seeds)"
            + (" — QUICK: x of 0 and 5 % on few seeds, for the tests" if d["quick"] else ""))
    return "\n\n".join([head, "## Report v3 re-judged", rejudged_md(), rejudged_rows_md(),
                        "## The silence-slash sweep", sweep_md(d, seeds),
                        "## The deposit's honest cost", deposit_md(d["author"], seeds)])


def full_report(seeds: Sequence[int], quick: bool = False, jobs: int = 1) -> str:
    return render(collect(seeds, quick, jobs))
