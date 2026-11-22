"""Task group 7 of #132 (proof-of-fix#141, round 2): the open-validator simulation re-run with round 2's rules.

    python3 -m pof.sim market validators --seeds 40 --jobs 4   this report (reports/open-validators-v3.md)
    python3 -m pof.sim market validators --seeds 40 --v2r1     round 1's report (reports/open-validators-v2.md)
    python3 -m pof.sim market validators --seeds 40 --v1       #134's report (reports/open-validators-v1.md)

Round 2's rules are `params.V2R2` (the defaults); round 1's are `params.V2R1`, #134's `params.V1`. What this module
adds to round 1's report (`rerun`), every section run on V2R2:
- `SWITCHES` (task 7.3): each alternative round 2 named, as a `Params` and/or a `World` that changes only what it
  names, run beside its rule on the same seeds; `R1_SWITCHES`: round 1's alternatives (task 6.2) on round 2's rules;
- D6's real TEE types (task 7.2): the launch world (AWS Nitro Enclaves, Intel TDX, AMD SEV-SNP: three types, the cap
  from k = 5) and a five-type world adding Intel SGX and IBM Secure Execution (the cap from k = 3), each spread evenly
  and skewed toward TDX and SEV-SNP (`World.tee_weights`, a named assumption);
- the scenarios "A bribed silent judge and a bribed withholder", "A coalition of removals", "Recovery by chance" and
  "The TEE cap and the number of TEE types", escalated fixes with the deposit, and answer shopping at #125's measured
  room (`Q125`);
- `acceptance` (task 7.4): D17's round-2 criteria. Every attacker criterion is "doesn't gain against its honest twin"
  (`doesnt_gain`: mean <= 0 and mean + 2 SE <= GAIN_TOLERANCE), with round 1's "loses" reported beside it; no adding
  ADR or escalated fix passes below CONSTITUTION_MIN_ELIGIBLE (21) eligible and no removal below REMOVAL_MIN_ELIGIBLE
  (14); LONE_CATCH_SHARE with two audits. Under `params.V2R3` (task 8.1) it judges round 3's: "not shown to gain"
  (`not_shown_to_gain`), and LONE_CATCH_SHARE on the lone validator's own verdicts (`lone_share`);
- `R1_PUBLISHED`: round 1's numbers (reports/open-validators-v2.md) beside each changed row; `derived_md`: the
  design's hand-derived numbers beside what the run measures.

`collect` runs every section once (`jobs` > 1: that many processes, one section each; the numbers don't change) and
`render` prints them. `quick=True` runs one row per section on few seeds, for the tests: not a result to read.
Simulated only (rule 1): nothing here opens a connection.
"""

from __future__ import annotations

import functools
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
from . import rerun as RR
from . import scores as SC
from .net import CONSTITUTION, ISSUE, Net
from .params import DAY, V1, V2R1, V2R2, WORLD, Params, World, diff_fields, r2_fields

NAN = float("nan")
R2 = V2R2
mean_se, at_most, at_least, pooled, loses = RR.mean_se, RR.at_most, RR.at_least, RR.pooled, RR.loses
_ms, _pct, _p90 = RR._ms, RR._pct, RR._p90


def _pm(m: float, se: float, nd: Optional[int] = None, pre: str = "") -> str:
    """mean ± 2 SE, with one decimal when both are under $10 (where "doesn't gain" is decided by the sign)."""
    if nd is None:
        nd = 1 if m == m and abs(m) < 10 and 2 * se < 10 else 0
    return RR._pm(m, se, nd, pre)


# ---------- judging a criterion (D17, round 2) ----------

def doesnt_gain(m: float, se: float, tol: float = R2.GAIN_TOLERANCE) -> bool:
    """"Doesn't gain against its honest twin" (D17, round 2): mean(attacker - twin) <= 0 and mean + 2 SE <=
    GAIN_TOLERANCE. A positive mean fails, and so does a noisy result whose upper bound is above the tolerance."""
    return m == m and m <= 0 and m + 2 * se <= tol + 1e-12


def not_shown_to_gain(m: float, se: float, tol: float = R2.GAIN_TOLERANCE) -> bool:
    """"Not shown to gain against its honest twin" (D17, round 3): mean(attacker - twin) - 2 SE <= 0 and mean + 2 SE
    <= GAIN_TOLERANCE. A gain shown by its lower bound fails, and so does a noisy result whose upper bound is above the
    tolerance; a mean above zero by chance doesn't."""
    return m == m and m - 2 * se <= 1e-12 and m + 2 * se <= tol + 1e-12


GAIN_TESTS: Dict[str, Callable[[float, float, float], bool]] = {"doesnt_gain": doesnt_gain,
                                                                 "not_shown": not_shown_to_gain}


def gain_ok(m: float, se: float, p: Params = R2) -> bool:
    """Every attacker criterion, judged by `p.GAIN_TEST` (round 3: "not shown to gain"; round 2: "doesn't gain")."""
    return GAIN_TESTS[p.GAIN_TEST](m, se, p.GAIN_TOLERANCE)


def gain_cell(m: float, se: float, tol: float = R2.GAIN_TOLERANCE, test: str = "doesnt_gain") -> str:
    """The verdict in a table: "yes" (doesn't gain, or isn't shown to gain under round 3's `test`), or why not."""
    if m != m:
        return "–"
    if GAIN_TESTS[test](m, se, tol):
        return "yes"
    if (m - 2 * se if test == "not_shown" else m) > 0:
        return "**no: it gains**"
    return f"**no: up to {m + 2 * se:+,.0f}**"


def loses_cell(m: float, se: float) -> str:
    """Round 1's verdict beside it: loses, wins, or not significant."""
    return RR.verdict(m, se)


# ---------- the worlds: D6's real TEE types (task 7.2) ----------

TEES3 = WORLD.tees  # the launch list: AWS Nitro Enclaves, Intel TDX, AMD SEV-SNP
TEES5 = TEES3 + ("sgx", "ibm-se")  # ...and Intel SGX and IBM Secure Execution
SKEW3 = (0.2, 0.4, 0.4)  # newcomers: Nitro 20 %, TDX 40 %, SEV-SNP 40 % (an assumption)
SKEW5 = (0.15, 0.35, 0.35, 0.10, 0.05)  # Nitro 15 %, TDX 35 %, SEV-SNP 35 %, SGX 10 %, IBM SE 5 % (an assumption)
W3 = WORLD
W3_SKEW = replace(WORLD, tee_weights=SKEW3)
W5 = replace(WORLD, tees=TEES5)
W5_SKEW = replace(W5, tee_weights=SKEW5)
VENDOR = {"nitro": "AWS", "tdx": "Intel", "sgx": "Intel", "sev-snp": "AMD", "ibm-se": "IBM"}
TEE_NAMES = {"nitro": "Nitro", "tdx": "TDX", "sev-snp": "SEV-SNP", "sgx": "SGX", "ibm-se": "IBM SE"}


# ---------- the switches (task 7.3): each changes only what it names ----------

def _sw(key: str, label: str, rule: str, names: Tuple[str, ...], world: Optional[World] = None, **kw) -> RR.Switch:
    return RR.Switch(key, label, rule, replace(R2, **kw), names, world)


SWITCHES: Tuple[RR.Switch, ...] = (
    RR.Switch("v2r1", "round 1's rules as a whole (`V2R1`)", "round 2's rules", V2R1, tuple(r2_fields())),
    _sw("wait_floor", "waits a floor-bond newcomer could end (round 1's signal)", "every wait counts, once",
        ("WAIT_SIGNAL",), WAIT_SIGNAL="floor"),
    _sw("wait_any", "waits a newcomer of any bond could end", "every wait counts, once", ("WAIT_SIGNAL",),
        WAIT_SIGNAL="any"),
    _sw("slash_1", "both flat slashes at $1", "$5 for silence and for withholding",
        ("SEALED_NO_REVEAL_SLASH", "SILENCE_SLASH"), SEALED_NO_REVEAL_SLASH=1.0, SILENCE_SLASH=1.0),
    _sw("silence_0", "silence unslashed", "$5 for silence", ("SILENCE_SLASH",), SILENCE_SLASH=0.0),
    _sw("const_14", "one threshold for every ADR: 14", "21 for adding ADRs and escalated fixes, 14 for removals",
        ("CONSTITUTION_MIN_ELIGIBLE", "REMOVAL_MIN_ELIGIBLE"), CONSTITUTION_MIN_ELIGIBLE=14, REMOVAL_MIN_ELIGIBLE=14),
    _sw("const_28", "one threshold for every ADR: 28", "21 for adding ADRs and escalated fixes, 14 for removals",
        ("CONSTITUTION_MIN_ELIGIBLE", "REMOVAL_MIN_ELIGIBLE"), CONSTITUTION_MIN_ELIGIBLE=28, REMOVAL_MIN_ELIGIBLE=28),
    _sw("deposit_0", "`ADR_DEPOSIT` $0", "`ADR_DEPOSIT` $15", ("ADR_DEPOSIT",), ADR_DEPOSIT=0.0),
    _sw("deposit_25", "`ADR_DEPOSIT` $25", "`ADR_DEPOSIT` $15", ("ADR_DEPOSIT",), ADR_DEPOSIT=25.0),
    _sw("forfeit_funder", "an escalated fix's forfeit to its issue's funder (rejected by the owner)",
        "forfeits to the sponsors' pool", ("DEPOSIT_FORFEIT_TO",), DEPOSIT_FORFEIT_TO="funder"),
    _sw("k1_audits_1", "`K1_AUDITS` 1 (one audit of every k = 1 verdict)", "`K1_AUDITS` 2", ("K1_AUDITS",),
        K1_AUDITS=1),
    _sw("plain", "plain agreement for the score", "the balanced score (`SCORE_BALANCED`)", ("SCORE_BALANCED",),
        SCORE_BALANCED=False),
    _sw("sliding", "round 1's recovery: the last 50 shadow verdicts at each check, at `SCORE_MIN`",
        "fresh blocks of 100 at `SCORE_MIN` + 10 points",
        ("SCORE_RECOVERY", "SCORE_RECOVER_VERDICTS", "SCORE_RECOVER_MARGIN"), SCORE_RECOVERY="sliding",
        SCORE_RECOVER_VERDICTS=50, SCORE_RECOVER_MARGIN=0.0),
    _sw("block_200", "a fresh block of 200 at `SCORE_MIN` + 5 points", "fresh blocks of 100 at `SCORE_MIN` + 10 points",
        ("SCORE_RECOVER_VERDICTS", "SCORE_RECOVER_MARGIN"), SCORE_RECOVER_VERDICTS=200, SCORE_RECOVER_MARGIN=0.05),
    RR.Switch("tee3_skew", "three TEE types, skewed (TDX 40 %, SEV-SNP 40 %, Nitro 20 %)", "three TEE types, even",
              R2, (), W3_SKEW),
    RR.Switch("tee5", "five TEE types, even (adding SGX and IBM SE; the cap from k = 3)",
              "three TEE types, even (the cap from k = 5)", R2, (), W5),
    RR.Switch("tee5_skew", "five TEE types, skewed (TDX 35 %, SEV-SNP 35 %, Nitro 15 %, SGX 10 %, IBM SE 5 %)",
              "three TEE types, even (the cap from k = 5)", R2, (), W5_SKEW),
)
SW: Dict[str, RR.Switch] = {s.key: s for s in SWITCHES}

# round 1's alternatives (task 6.2) that round 2 didn't replace, on round 2's rules: the same fields, round 2's others
R1_KEYS = ("k1_cap_5", "k1_cap_20", "k1_batch", "k1_window_14", "k1_window_30", "idle_30", "idle_50", "idle_7d",
           "step_up", "median", "c_half", "no_wait_shadows", "false_2000", "c_on")
R1_SWITCHES: Tuple[RR.Switch, ...] = tuple(
    RR.Switch(k, RR.SW[k].label, RR.SW[k].rule, replace(R2, **{f: getattr(RR.SW[k].p, f) for f in RR.SW[k].names}),
              RR.SW[k].names) for k in R1_KEYS)
R1SW: Dict[str, RR.Switch] = {s.key: s for s in R1_SWITCHES}
C_ON2 = R1SW["c_on"].p  # level C switched on (by ADR) on round 2's rules
C_HALF_ON2 = replace(C_ON2, C_LIMIT_X=0.5)
AFTER_C = RR.AFTER_C


def switch_fields(s: RR.Switch) -> List[str]:
    """The Params fields a switch actually changes against round 2's rules."""
    return diff_fields(s.p, R2)


def world_fields(s: RR.Switch) -> List[str]:
    """The World fields a switch changes against the base world."""
    if s.world is None:
        return []
    return [f for f in World.__dataclass_fields__ if getattr(s.world, f) != getattr(WORLD, f)]


def q_for_room(room: float, tries: int = 5) -> float:
    """The borderline rate q at which a shopper calling up to `tries` times gains `room` over one call, in the
    simulation's model of independent calls: 1 - (1 - q)^tries - q = room (bisection)."""
    lo, hi = 0.0, 0.5
    for _ in range(80):
        q = (lo + hi) / 2
        if 1 - (1 - q) ** tries - q < room:
            lo = q
        else:
            hi = q
    return (lo + hi) / 2


Q125 = q_for_room(0.035)  # #125 (reports/determinism-v1.md): +3.5 points on borderline fixes with 5 calls


# ---------- round 1's published numbers (reports/open-validators-v2.md), beside each changed row ----------

R1_PUBLISHED: Dict[str, str] = {
    # attackers
    "att:sybil": "-21,601 ± 2,530", "att:sybil_one": "-17,936 ± 1,753", "att:grinder": "-250 ± 46",
    "att:grinder_fixed": "-240 ± 36", "att:farmer": "-535 ± 1", "att:sybil_2000": "-3,043 ± 532",
    "att:grinder_2000": "-70 ± 14",
    # the colluding genesis (round 1: one audit of every k = 1 verdict)
    "col:design": "-221 ± 38", "col:design_share": "86.6 % ± 5.1 %", "col:k1_cap_5": "-185 ± 38",
    "col:k1_cap_20": "-299 ± 51", "col:k1_batch": "-97 ± 33", "col:k1_window_14": "-243 ± 36",
    "col:k1_window_30": "-247 ± 39", "col:no_wait_shadows": "-130 ± 2", "col:false_2000": "-67 ± 11",
    "col:design_1": "-103 ± 30", "col:v1": "+2,920 ± 456",
    # the silent judge and the withholder
    "sil:silent": "+317 ± 13", "sil:withhold": "+249 ± 12", "sil:silent_1": "+250 ± 12", "sil:withhold_1": "+249 ± 12",
    "sil:silent_0": "+317 ± 13", "sil:silent_v1": "-3,813 ± 123",
    # the early coalition (round 1: 14 for every ADR, no deposit)
    "con:c5": "+622 ± 260", "con:c5_14": "+622 ± 260", "con:c5_28": "+187 ± 138", "con:c5_d0": "+280 ± 152",
    "con:c5_v2r1": "+622 ± 260", "con:c5_v1": "+5,196 ± 2,178", "con:c3": "+148 ± 182", "con:c3_14": "+148 ± 182",
    "con:c3_28": "+65 ± 128", "con:c3_d0": "+82 ± 135", "con:c3_v2r1": "+148 ± 182", "con:c3_v1": "+819 ± 450",
    # proof levels
    "lev:liar_grown": "-4,810 ± 505", "lev:liar_grown_c_half": "-4,310 ± 484", "lev:shopper_1": "-13 ± 1",
    "lev:shopper_3": "+174 ± 46", "lev:shopper_3_nofix": "+531 ± 107", "lev:shopper_1_c_half": "-12 ± 1",
    "lev:shopper_3_c_half": "+157 ± 47", "lev:breaker_genesis": "-1,520 ± 64", "lev:breaker_genesis_50": "-570 ± 64",
    "lev:breaker_grown": "-13,873 ± 1,579", "lev:breaker_grown_all": "-21,352 ± 2,153",
    "lev:breaker_grown_on": "-19,766 ± 1,636",
    # pricing (round 1's design: the floor-bond wait signal; and its any-bond switch)
    "pr:cartel": "-488 ± 17", "pr:spam_wait": "-603 ± 10", "pr:spam_judged": "-548 ± 50", "pr:inflate": "+33 ± 4",
    "pr:inflate_small": "+28 ± 4", "pr:pfarmer": "-548 ± 1", "pr:floor_cartel": "-488 ± 17",
    "pr:floor_spam_wait": "-603 ± 10", "pr:any_cartel": "-503 ± 11", "pr:any_spam_wait": "-463 ± 89",
    # the fee / break-even and the runs collapsed (round 1's FEE_MARGIN table)
    "fee:design": "0.47 ± 0.40 ×", "feec:design": "33 of 40", "fee:every": "1.21 ± 0.04 ×", "feec:every": "0 of 40",
    "fee:any": "1.08 ± 0.07 ×", "feec:any": "1 of 40", "feec:idle_30": "40 of 40", "fee:idle_50": "0.99 ± 0.10 ×",
    "feec:idle_50": "12 of 40", "fee:idle_7d": "1.20 ± 0.03 ×", "feec:idle_7d": "0 of 40",
    "fee:step_up": "0.62 ± 0.36 ×", "feec:step_up": "32 of 40", "fee:w100": "1.28 ± 0.03 ×", "feec:w100": "0 of 40",
    "feec:s005": "40 of 40", "fee:v1": "1.00 ± 0.02 ×", "feec:v1": "0 of 40",
    "month:design": "$-6.81 ± 0.99", "month:sealed_1": "$-7.35 ± 0.97", "month:any_5": "$-2.92 ± 0.80",
    "month:v1": "$-2.65 ± 0.51",
    # scores (round 1's design: plain agreement, the sliding recovery)
    "sc:weak_score": "66.6 ± 6.0 %", "sc:weak_barred": "58 ± 3 %", "sc:weak_bars": "11.3 / 10.8",
    "her:herd_mid_det": "-82,767 ± 5,385", "her:herd_mid": "-10 ± 2", "her:herd_weak_det": "-79,203 ± 5,111",
    "her:herd_weak": "+13 ± 2", "her:herd_mid_25": "-54 ± 11", "her:herd_weak_25": "+80 ± 9",
    "her:mherd_mid": "-5 ± 4", "her:mherd_weak": "+33 ± 16", "her:mherd_weak_any": "+202 ± 19",
    "crowd": "7.9 ± 2.4 %", "fees_pay": "0.354 ± 0.001", "fees_none": "0.363 ± 0.001",
    # growth and the TEE cap
    "gro:pay": "19.0 ± 3.6 (46.1)", "gro:waited": "21 ± 3 % / 16 ± 3 %", "gro:one_tee": "11.1 ± 2.8 % (77 ± 8 %)",
    "gro:stepped": "13 ± 3 %", "gro:tee5": "6 ± 1 %", "gro:k3": "40 of 40",
    "watch:bribed_10": "-795.1 ± 324.2", "watch:lazy_10": "-3,807.5 ± 604.9",
}


def r1(key: str) -> str:
    return R1_PUBLISHED.get(key, "–")


# ---------- growth from one validator, and the TEE types ----------

def _majority_of(n: Net, s, key: Callable) -> bool:
    c = Counter(key(n.reg.validators[vid]) for vid, _, _ in s.judges)
    c.pop(None, None)
    return bool(c) and max(c.values()) >= (s.k + 1) // 2


def growth_metrics(n: Net) -> Dict[str, object]:
    """Round 1's growth metrics, and the share of panels of 3 whose majority one vendor's TEE types hold (Intel: SGX
    and TDX), with the TEE types accepted at the year's end."""
    m = RR.growth_metrics(n)
    k3 = [s for s in n.subs.values() if s.tier == ISSUE and s.draw is not None and s.k == 3 and s.judges]
    m["one_vendor_k3"] = (sum(1 for s in k3 if _majority_of(n, s, lambda v: VENDOR.get(v.tee))) / max(1, len(k3)))
    m["k3_share"] = len(k3) / max(1, n.stats["drawn"])
    m["tee_types"] = n._tee_count()
    return m


GROWTH_ROWS: List[Tuple[str, str, Params, World]] = [
    ("design", "**Round 2's rules (the design)**: three TEE types at launch, even", R2, W3),
    ("v2r1", SW["v2r1"].label, V2R1, W3),
    ("k1_audits_1", SW["k1_audits_1"].label, SW["k1_audits_1"].p, W3),
    ("k1_cap_5", R1SW["k1_cap_5"].label, R1SW["k1_cap_5"].p, W3),
    ("k1_cap_20", R1SW["k1_cap_20"].label, R1SW["k1_cap_20"].p, W3),
    ("k1_batch", R1SW["k1_batch"].label, R1SW["k1_batch"].p, W3),
    ("k1_window_14", R1SW["k1_window_14"].label, R1SW["k1_window_14"].p, W3),
    ("k1_window_30", R1SW["k1_window_30"].label, R1SW["k1_window_30"].p, W3),
    ("no_wait_shadows", R1SW["no_wait_shadows"].label, R1SW["no_wait_shadows"].p, W3),
    ("v1", "#134's rules (v1)", V1, W3),
]
TEE_ROWS: List[Tuple[str, str, Params, World]] = [  # "design" is the first growth row
    ("tee3_skew", "Three types, skewed (TDX 40 %, SEV-SNP 40 %, Nitro 20 %): the cap from k = 5", R2, W3_SKEW),
    ("tee5", "Five types (adding SGX and IBM SE), even: **the cap from k = 3**", R2, W5),
    ("tee5_skew", "Five types, skewed (TDX 35 %, SEV-SNP 35 %, Nitro 15 %, SGX 10 %, IBM SE 5 %): the cap from k = 3",
     R2, W5_SKEW),
    ("tee3_from3", "Three types, even, the cap from k = 3 (#134's rule)", replace(R2, TEE_CAP_FROM_K=3), W3),
    ("tee5_from5", "Five types, even, the cap from k = 5 (round 1's rule)", replace(R2, TEE_CAP_K3_TYPES=None), W5),
]


def s_growth(seeds, sweep, quick):
    rows = GROWTH_ROWS[:1] if quick else GROWTH_ROWS
    out = [(key, label, RR._collect_runs([growth_metrics(Net(s, p, w).run()) for s in seeds]))
           for key, label, p, w in rows]
    return {"rows": out, "weekly": None if quick else R.growth_table(seeds, R2, W3)}


def s_tees(seeds, sweep, quick):
    rows = TEE_ROWS[1:2] if quick else TEE_ROWS
    return [(key, label, RR._collect_runs([growth_metrics(Net(s, p, w).run()) for s in seeds]))
            for key, label, p, w in rows]


GROWTH_R1 = {"design": "gro:pay"}


def md_growth(d, seeds) -> str:
    out = []
    if d["weekly"]:
        out += [d["weekly"].replace("### Growth from one validator", "### Growth from one validator under round 2's "
                                    "rules", 1), ""]
    out += [f"#### An honest network grows under the hold ({len(seeds)} seeds; a year; growth from one validator, one "
            "newcomer a week, 30 submissions a week; each rule beside its alternatives, same seeds)", "",
            "| Rule | Runs where a small bounty reaches k ≥ 3 | First 4-week snapshot at k ≥ 3 | Days from a k = 1 "
            "verdict to payment: median a run (p90, all runs) | k = 1 verdicts held / days held | Submissions that "
            "waited / withdrawn | Newcomers qualified (of joined) / days to qualify | Sponsors' pool on shadows (on "
            "waiting submissions) | Bad fixes merged per 100 paid | Draws the caps lowered | Panels of k ≥ 3 (of 3) "
            "with one TEE type holding the majority | Active at year's end |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, m in d["rows"]:
        out.append(_growth_row(label, m))
    out += ["", "Round 1's design (reports/open-validators-v2.md): k ≥ 3 in " + r1("gro:k3") + " runs, days to payment "
            + r1("gro:pay") + ", waited / withdrawn " + r1("gro:waited") + ", the caps lowered " + r1("gro:stepped")
            + " of draws, one TEE type holding the majority " + r1("gro:one_tee") + ". The second row re-runs round 1's "
            "rules on the same seeds; the last, #134's."]
    return "\n".join(out)


def _growth_row(label: str, m: Dict[str, list]) -> str:
    n = len(m["k3"])
    return (f"| {label} | {sum(m['k3']):.0f} of {n} | week {_ms(m['k3_week'], 0)} | {_ms(m['pay_days'], 1)} "
            f"({_p90(m.get('pay_all', [])):.1f}) | {_ms(m['held'], 0, 100, unit=' %')} / {_ms(m['held_days'], 1)} | "
            f"{_ms(m['waited'], 0, 100, unit=' %')} / {_ms(m['withdrawn'], 0, 100, unit=' %')} | "
            f"{_ms(m['qualified'], 1)} ({mean(m['joined']):.1f}) / {_ms(m['qualify_days'], 0)} | "
            f"${mean(m['pool']):,.0f} (${mean(m['pool_wait']):,.0f}) | {_ms(m['bad'], 2)} | "
            f"{_ms(m['stepped'], 0, 100, unit=' %')} | {_ms(m['one_tee'], 1, 100, unit=' %')} "
            f"({_ms(m['one_tee_k3'], 0, 100, unit=' %')}) | {_ms(m['active'], 1)} |")


def md_tees(growth, tees, seeds) -> str:
    rows = [("design", "**Three types (TDX, SEV-SNP, Nitro), even: the cap from k = 5 (the design at launch)**",
             {k: m for k, _, m in growth["rows"]}.get("design"))] + list(tees)
    out = [f"### The TEE cap and the number of TEE types ({len(seeds)} seeds; a year; growth from one validator; "
           "newcomers spread over the accepted types as stated; round 2's rules)", "",
           "| TEE types and spread | Panels of 3 with one TEE type holding the majority | ...with one vendor (Intel: SGX "
           "and TDX) holding it | Panels of k ≥ 3 with one type's majority | Panels drawn at k = 3 | Draws the caps "
           "lowered | Submissions that waited / withdrawn | Runs reaching k ≥ 3 / first week | Bad fixes merged per "
           "100 paid | Round 1 (v2) |", "|---|---|---|---|---|---|---|---|---|---|"]
    r1s = {"design": r1("gro:one_tee") + "; lowered " + r1("gro:stepped"),
           "tee5": "five placeholder types from k = 3: lowered " + r1("gro:tee5")}
    for key, label, m in rows:
        if m is None:
            continue
        out.append(f"| {label} | {_ms(m['one_tee_k3'], 0, 100, unit=' %')} | "
                   f"{_ms(m['one_vendor_k3'], 0, 100, unit=' %')} | {_ms(m['one_tee'], 1, 100, unit=' %')} | "
                   f"{_ms(m['k3_share'], 0, 100, unit=' %')} | {_ms(m['stepped'], 0, 100, unit=' %')} | "
                   f"{_ms(m['waited'], 0, 100, unit=' %')} / {_ms(m['withdrawn'], 0, 100, unit=' %')} | "
                   f"{sum(m['k3']):.0f} of {len(m['k3'])} / week {_ms(m['k3_week'], 0)} | {_ms(m['bad'], 2)} | "
                   f"{r1s.get(key, '–')} |")
    out += ["", "The cap's start follows the number of accepted types (`TEE_CAP_K3_TYPES` 5): from k = 3 with five, from "
            "k = 5 with three. One vendor: Intel makes both SGX and TDX, which count as two types (owner, 2026-11-03), "
            "so with five types two Intel validators may hold a panel of 3. The skewed spreads are assumptions."]
    return "\n".join(out)


# ---------- the attackers against their twins ----------

ATTACK_ROWS: List[Tuple[str, str, Callable[[bool], A.Actor], Params, str, bool]] = [
    ("sybil", "Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families", lambda h: A.Sybil(h), R2,
     "sybil", True),
    ("sybil_one", "Sybil: 10 of 30 validators, one host, TEE type and family",
     lambda h: A.Sybil(h, hosts=1, tees=1, families=1), R2, "sybil", True),
    ("grinder", "Seed grinder (v3's seed: a later block)", lambda h: A.SeedGrinder(h), R2, "grinder", True),
    ("grinder_fixed", "Seed grinder (counterfactual: the seed fixed at the seal)", lambda h: A.SeedGrinder(h),
     replace(R2, SEED_FROM_LATER_BLOCK=False), "grinder", False),
    ("farmer", "Fee farmer (10 idle nodes at the bond floor; twin: one node)", lambda h: A.FeeFarmer(h), R2, "farmer",
     True),
    ("sybil_2000", "Sybil, spread, " + R1SW["false_2000"].label, lambda h: A.Sybil(h), R1SW["false_2000"].p, "sybil",
     False),
    ("grinder_2000", "Seed grinder, " + R1SW["false_2000"].label, lambda h: A.SeedGrinder(h), R1SW["false_2000"].p,
     "grinder", False),
]

ATTACK_HEAD = ["| Attacker | Return − twin's ($, ± 2 SE) | Doesn't gain (D17, round 2) | Loses (round 1's criterion) "
               "| Attacker's return | Twin's return | Round 1 (v2) | What it got |",
               "|---|---|---|---|---|---|---|---|"]


def s_attackers(seeds, sweep, quick):
    rows = ATTACK_ROWS[2:3] if quick else ATTACK_ROWS
    return [(key, label, A.against_twin(make, seeds, p=p, metrics=RR.attack_metrics), kind, counted)
            for key, label, make, p, kind, counted in rows]


def _att_row(label: str, r: Dict[str, object], r1key: str, got: str) -> str:
    return (f"| {label} | {_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | "
            f"{loses_cell(r['diff'], r['se'])} | {r['attacker']:,.0f} | {r['twin']:,.0f} | {r1(r1key)} | {got} |")


def md_attackers(d, seeds) -> str:
    out = [f"### Each attacker against its honest twin ({len(seeds)} seeds; a year; returns in $, with bonds' "
           "capital, running costs, fees, slashes, attempt fees and checks counted)", ""] + ATTACK_HEAD
    for key, label, r, kind, counted in d:
        out.append(_att_row(label, r, "att:" + key, R._got(kind, r)))
    return "\n".join(out)


# ---------- the colluding genesis under the hold, with two audits ----------

COLLUDER_ROWS: List[Tuple[str, str, Params, float]] = [
    ("design", "**Round 2's rules (the design): two audits of every k = 1 verdict**, 5 bad fixes a week", R2, 5.0),
    ("k1_audits_1", SW["k1_audits_1"].label, SW["k1_audits_1"].p, 5.0),
    ("v2r1", SW["v2r1"].label, V2R1, 5.0),
    ("k1_cap_5", R1SW["k1_cap_5"].label, R1SW["k1_cap_5"].p, 5.0),
    ("k1_cap_20", R1SW["k1_cap_20"].label, R1SW["k1_cap_20"].p, 5.0),
    ("k1_batch", R1SW["k1_batch"].label, R1SW["k1_batch"].p, 5.0),
    ("k1_window_14", R1SW["k1_window_14"].label, R1SW["k1_window_14"].p, 5.0),
    ("k1_window_30", R1SW["k1_window_30"].label, R1SW["k1_window_30"].p, 5.0),
    ("no_wait_shadows", R1SW["no_wait_shadows"].label, R1SW["no_wait_shadows"].p, 5.0),
    ("false_2000", R1SW["false_2000"].label, R1SW["false_2000"].p, 5.0),
    ("design_1", "Round 2's rules, 1 bad fix a week", R2, 1.0),
    ("v1", "#134's rules (v1), 5 bad fixes a week", V1, 5.0),
]


def colluder_run(s: int, p: Params, bad_week: float) -> Dict[str, object]:
    """Round 1's colluder metrics (`rerun.colluder_run`), and the audits each passed bad fix got."""
    a, t = A.LoneColluder(False, bad_week=bad_week), A.LoneColluder(True, bad_week=bad_week)
    na, nt = A.run(a, s, p), A.run(t, s, p)
    mine = [x for x in na.subs.values() if x.party == a.party]
    passed = [x for x in mine if x.verdict]
    rev = sum(1 for x in passed if x.reversed)
    paid = sum(1 for x in passed if x.final)
    me = {v.vid for v in na.party_validators(a.party)}
    own = [x for x in passed if x.k == 1 and x.judges and x.judges[0][0] in me]  # its own lone verdicts
    honest_pay = [(x.final_t - x.verdict_t) / DAY for x in na.subs.values()
                  if x.party is None and x.tier == ISSUE and x.k == 1 and x.final]
    return {"diff": na.party_net(a.party) - nt.party_net(t.party), "attacker": na.party_net(a.party),
            "twin": nt.party_net(t.party), "passed": len(passed), "reversed": rev, "paid": paid,
            "resolved": rev + paid, "pending": len(passed) - rev - paid,
            "held": sum(1 for x in mine if x.was_held), "submitted": len(mine),
            "frozen": sum(1 for x in mine if x.challenge is not None and x.challenge.state == "waiting"),
            "qualified": na.stats["qualified"], "twin_qualified": nt.stats["qualified"],
            "slashed": sum(v.acct.slashed for v in na.party_validators(a.party)),
            "audits": sum(len(x.auditors) for x in passed),
            "own_reversed": sum(1 for x in own if x.reversed), "own_resolved": sum(1 for x in own if x.reversed or x.final),
            "honest_pay_days": median(honest_pay) if honest_pay else NAN}


def s_colluder(seeds, sweep, quick):
    rows = COLLUDER_ROWS[:1] if quick else COLLUDER_ROWS
    return [(key, label, RR._collect_runs([colluder_run(s, p, bw) for s in seeds])) for key, label, p, bw in rows]


def md_colluder(d, seeds) -> str:
    out = [f"### The colluding genesis under the hold, with two audits ({len(seeds)} seeds; a year; growth from one "
           "validator; the genesis, bonded $100, passes its accomplice's bad fixes at k = 1; against its honest twin)",
           "", "| Rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Bad fixes passed / reversed / paid / "
           "still pending | Reversed before payment, pooled (± 2 SE) | ...of those it judged alone | Audits per passed "
           "bad fix | Its verdicts held | Challenges still frozen | Newcomers qualified (twin's) | Slashed | Round 1 "
           "(v2) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, m in d:
        dm, dse = mean_se(m["diff"])
        c, cse = RR.caught(m)
        ap = sum(m["audits"]) / max(1, sum(m["passed"]))
        o, ose = pooled(m["own_reversed"], m["own_resolved"])
        out.append(f"| {label} | {_pm(dm, dse)} | {gain_cell(dm, dse)} | {loses_cell(dm, dse)} | "
                   f"{mean(m['passed']):.1f} / {mean(m['reversed']):.1f} / {mean(m['paid']):.1f} / "
                   f"{mean(m['pending']):.1f} | {_pct(c, 1)} ± {_pct(2 * cse, 1) if cse == cse else '–'} | "
                   f"{_pct(o, 1)} ± {_pct(2 * ose, 1) if ose == ose else '–'} | {ap:.2f} | "
                   f"{mean(m['held']):.1f} | {mean(m['frozen']):.1f} | {mean(m['qualified']):.1f} "
                   f"({mean(m['twin_qualified']):.1f}) | ${mean(m['slashed']):,.0f} | {r1('col:' + key)} |")
    out += ["", "Round 1's design (one audit of every k = 1 verdict): " + r1("col:design") + " $, "
            + r1("col:design_share") + " reversed before payment. D13 and D17 estimate about 96 % with two audits. "
            "\"Reversed before payment\" counts the passed bad fixes that reached an outcome by the year's end, as "
            "round 1 did: those its accomplice submitted while k was 1, whoever judged them (an honest lone judge's "
            "mistake, or a panel of 3 drawn later). \"...of those it judged alone\" counts only its own k = 1 verdicts. "
            "\"Still pending\" ones (held or in their window at the year's end) are neither."]
    return "\n".join(out)


# ---------- a bribed silent judge and a bribed withholder ----------

SILENT_ROWS: List[Tuple[str, str, Callable[[bool], A.Actor], Params, bool]] = [
    ("silent", "**Silent (never seals): `SILENCE_SLASH` $5 (the design)**", lambda h: A.SilentJudge(h), R2, True),
    ("withhold", "**Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5 (the design)**",
     lambda h: A.SilentJudge(h, sealed=True), R2, True),
    ("silent_1", "Silent: " + SW["slash_1"].label, lambda h: A.SilentJudge(h), SW["slash_1"].p, False),
    ("withhold_1", "Seals, then withholds: " + SW["slash_1"].label, lambda h: A.SilentJudge(h, sealed=True),
     SW["slash_1"].p, False),
    ("silent_0", "Silent: " + SW["silence_0"].label, lambda h: A.SilentJudge(h), SW["silence_0"].p, False),
    ("silent_10", "Silent, the design, bribed 10 % of the bounty (about $9 a silence; sensitivity)",
     lambda h: A.SilentJudge(h, stall_value=0.10), R2, False),
    ("withhold_10", "Seals, then withholds, the design, bribed 10 % of the bounty (sensitivity)",
     lambda h: A.SilentJudge(h, stall_value=0.10, sealed=True), R2, False),
    ("silent_v1", "Silent, #134's rules (5 % of the bond a miss)", lambda h: A.SilentJudge(h), V1, False),
]


def silent_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = RR.attack_metrics(net, a)
    m["bribes"] = sum(v.acct.gains for v in net.party_validators(a.party))
    return m


def s_silent(seeds, sweep, quick):
    rows = SILENT_ROWS[:1] if quick else SILENT_ROWS
    return [(key, label, A.against_twin(make, seeds, p=p, metrics=silent_metrics), counted)
            for key, label, make, p, counted in rows]


def md_silent(d, seeds) -> str:
    out = [f"### A bribed silent judge and a bribed withholder ({len(seeds)} seeds; a year; a grown network of 12 "
           "honest validators; bribed 5 % of the bounty on 10 % of its draws unless stated)", "",
           "| Judge and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Bribed misses / suspended | Bribe "
           "a miss | Slashed | k ever shrank | Round 1 (v2) |", "|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d:
        bribe = r["bribes"] / r["silences"] if r.get("silences") else NAN
        out.append(f"| {label} | {_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | "
                   f"{loses_cell(r['diff'], r['se'])} | {r['silences']:.1f} / {r['suspensions']:.1f} | "
                   f"${bribe:.2f} | ${r['slashed']:,.2f} | {'yes' if r['k_shrank'] else 'never'} | "
                   f"{r1('sil:' + key)} |")
    out += ["", "Round 1's design: the silent judge unslashed (" + r1("sil:silent") + " $) and the withholder at $1 ("
            + r1("sil:withhold") + " $). Round 1's switch set both at $1 (silent " + r1("sil:silent_1") + " $)."]
    return "\n".join(out)


# ---------- an early coalition, escalated fixes, and a coalition of removals ----------

def const_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    p = net.p
    mine = [s for s in net.subs.values() if s.party == a.party and s.tier == CONSTITUTION]
    passed = [s for s in mine if s.final]
    pa = net.parties.get(a.party)
    return {"submitted": len(mine), "passed": len(passed), "judged": sum(1 for s in mine if s.draw is not None),
            "expired": sum(1 for s in mine if s.state == "expired"),
            "below_need": sum(1 for s in passed if len(s.draw.pool) < p.constitution_min(s.removal is not None)),
            "below_21": sum(1 for s in passed if len(s.draw.pool) < 3 * p.K_MAX),
            "below_14": sum(1 for s in passed if len(s.draw.pool) < 2 * p.K_MAX),
            "forfeited": pa.forfeited if pa is not None else 0.0,
            "to_funder": net.stats["deposits_to_funder"],
            "first_judged": min([s.drawn_t / DAY for s in mine if s.drawn_t is not None], default=365.0),
            "stopped": net.stats["stopped_drawn"], "removed": net.stats["removals_applied"],
            "waited": net.stats["waited"] / max(1, net.stats["submitted"]),
            "tees_end": net._tee_count()}


CONST_ROWS: List[Tuple[str, str, int, Params, str, bool]] = []
for _n in (5, 3):
    CONST_ROWS += [
        (f"c{_n}", f"{_n} early validators: **21 for adding ADRs, a $15 deposit (the design)**", _n, R2, "adr", True),
        (f"c{_n}_14", f"{_n} early: {SW['const_14'].label}, $15", _n, SW["const_14"].p, "adr", False),
        (f"c{_n}_28", f"{_n} early: {SW['const_28'].label}, $15", _n, SW["const_28"].p, "adr", False),
        (f"c{_n}_d0", f"{_n} early: 21, {SW['deposit_0'].label}", _n, SW["deposit_0"].p, "adr", False),
        (f"c{_n}_d25", f"{_n} early: 21, {SW['deposit_25'].label}", _n, SW["deposit_25"].p, "adr", False),
        (f"c{_n}_v2r1", f"{_n} early: round 1's rules (14 for every ADR, no deposit)", _n, V2R1, "adr", False),
        (f"c{_n}_v1", f"{_n} early: #134's rule (`K_MAX` eligible, ADRs wait)", _n, V1, "adr", False),
    ]
CONST_ROWS += [
    ("e5", "5 early, sending escalated fixes to issues they fund themselves: **21, a $15 deposit to the sponsors' pool "
     "(the rule)**", 5, R2, "escalated", True),
    ("e5_funder", "5 early, the same escalated fixes: " + SW["forfeit_funder"].label, 5, SW["forfeit_funder"].p,
     "escalated", False),
]
CONST_DERIVED = {"c5": "about −$255 ± 152", "c5_14": "about −$8 ± 260", "c5_28": "about −$258 ± 138",
                 "c3": "about −$429 ± 135"}  # D7's table and sizing, derived from round 1's numbers


def s_constitution(seeds, sweep, quick):
    rows = CONST_ROWS[:1] if quick else CONST_ROWS
    return [(key, label, A.against_twin(lambda h, n=n, k=kind: A.ConstitutionCoalition(h, nodes=n, kind=k), seeds,
                                        p=p, metrics=const_metrics), counted)
            for key, label, n, p, kind, counted in rows]


def md_constitution(d, seeds) -> str:
    out = [f"### An early coalition ({len(seeds)} seeds; a year; growth from one validator; the coalition registers "
           "its validators at the start and submits an adding ADR worth $1,000 to it each week, with its deposit; its "
           "validators pass them)", "",
           "| Coalition and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | ADRs submitted / expired / "
           "judged / passed | Deposits forfeited ($ a run) | Passed below its rule's threshold (all runs) | Passed "
           "while fewer than 21 were eligible (all runs) | First ADR judged (day; 365: none) | Derived (D7) | Round 1 "
           "(v2) |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d:
        n = len(r["diffs"])
        out.append(f"| {label} | {_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | "
                   f"{loses_cell(r['diff'], r['se'])} | {r['submitted']:.0f} / {r['expired']:.1f} / "
                   f"{r['judged']:.1f} / {r['passed']:.2f} | ${r['forfeited']:,.0f} | {r['below_need'] * n:.0f} | "
                   f"{r['below_21'] * n:.0f} | {r['first_judged']:.0f} | {CONST_DERIVED.get(key, '–')} | "
                   f"{r1('con:' + key)} |")
    out += ["", "Round 1's numbers: the same coalition under round 1's design (14 for every ADR, no deposit) for the "
            "design row, and round 1's measured switch for the others (\"21, $0\" is round 1's 21). \"Derived\": D7's "
            "hand estimate from round 1's table, assuming the coalition keeps submitting. An escalated fix's issue is "
            "funded by the coalition itself, so a forfeit sent to the funder comes back to it."]
    return "\n".join(out)


REMOVAL_ROWS: List[Tuple[str, str, Params, World, float, bool]] = [
    ("r5", "**5 early validators, removals from 14 with a $15 deposit (the design)**; three types, even; they remove "
     "Nitro, the genesis's type", R2, W3, 0.0, True),
    ("r5_skew", "the same, three types skewed; they remove TDX (40 % of newcomers)", R2, W3_SKEW, 0.0, True),
    ("r5_d0", "the same as the first, " + SW["deposit_0"].label, SW["deposit_0"].p, W3, 0.0, False),
    ("r5_value", "the same as the first, a passed removal worth $1,000 to it (sensitivity)", R2, W3, 1000.0, False),
]


def s_removal(seeds, sweep, quick):
    rows = REMOVAL_ROWS[:1] if quick else REMOVAL_ROWS
    return [(key, label, A.against_twin(lambda h, v=value: A.RemovalCoalition(h, value=v), seeds, p=p, w=w,
                                        metrics=const_metrics), counted)
            for key, label, p, w, value, counted in rows]


def md_removal(d, seeds) -> str:
    out = [f"### A coalition of removals ({len(seeds)} seeds; a year; growth from one validator; 5 validators "
           "registered at the start on the other types submit each week an ADR removing the TEE type most other "
           "validators use, with its deposit, until it is removed; their validators pass them)", "",
           "| Coalition and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Removals submitted / expired / "
           "judged / passed | Deposits forfeited ($ a run) | Removals taking effect (runs) | Validators that stopped "
           "being drawn (a run) | Passed while fewer than 14 were eligible (all runs) | First removal judged (day) | "
           "Submissions that waited |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in d:
        n = len(r["diffs"])
        out.append(f"| {label} | {_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | "
                   f"{loses_cell(r['diff'], r['se'])} | {r['submitted']:.0f} / {r['expired']:.1f} / "
                   f"{r['judged']:.1f} / {r['passed']:.2f} | ${r['forfeited']:,.0f} | {r['removed'] * n:.0f} of {n} | "
                   f"{r['stopped']:.1f} | {r['below_14'] * n:.0f} | {r['first_judged']:.0f} | "
                   f"{100 * r['waited']:.0f} % (twin {100 * r['twin_waited']:.0f} %) |")
    out += ["", "A removal takes effect `REMOVAL_WINDOW` (48 h) after it passes: the type's validators stop being "
            "drawn and keep their bonds, and newcomers of that type are refused. Assumption: none of them registers "
            "again with another type within the year. The last accepted type can never be removed. The first row "
            "counts only the fees the coalition's validators win from the removed ones; the last values a removal "
            "at $1,000, as the adding coalition values an ADR."]
    return "\n".join(out)


# ---------- the sybil's share and the watcher's dilemma ----------

def s_sybil(seeds, sweep, quick):
    return R.sybil_shares(sweep, (3,) if quick else RR.SYBIL_SIZES, p=R2)


def s_watch(seeds, sweep, quick):
    rates = (R2.AUDIT_RATE,) if quick else R.AUDIT_RATES
    return {"lazy": R.watchers(sweep, rates, "lazy", base=R2), "bribed": R.watchers(sweep, rates, "bribed", base=R2)}


def s_ktable(seeds, sweep, quick):
    return F.k_table(seeds, F.K_NETWORKS[2:] if quick else None, p=R2)


# ---------- proof levels ----------

_REBASE = {id(RR.V2): R2, id(RR.C_ON): C_ON2, id(RR.C_HALF_ON): C_HALF_ON2}
LEVEL_NETWORKS = [(name, _REBASE[id(p)], w, lw) for name, p, w, lw in RR.LEVEL_NETWORKS]
LEVEL_ATTACKERS = [(key, label, make, _REBASE[id(p)], kind, counted)
                   for key, label, make, p, kind, counted in RR.LEVEL_ATTACKERS]
LEVEL_ATTACKERS.insert(6, (
    "shopper_125", f"Answer shopper, {AFTER_C}: the same at #125's measured room, +3.5 points with 5 calls (a "
    f"borderline rate of {100 * Q125:.1f} % in this model; one 7B open model on one setup, reports/determinism-v1.md)",
    lambda h: L.AnswerShopper(h, "grown", borderline_pass=Q125, twin_submits=True), C_ON2, "shopper", False))
COFF_NETWORKS = [(name, _REBASE[id(p)], w, lw) for name, p, w, lw in RR.COFF_NETWORKS]


def s_level_networks(seeds, sweep, quick):
    rows = LEVEL_NETWORKS[1:2] if quick else LEVEL_NETWORKS
    return {"rows": [L.networks(seeds, [(name, w, lw)], p=p)[0] for name, p, w, lw in rows],
            "c_genesis": RR.refused(C_ON2, WORLD, replace(RR.LW, mix=(0.0, 0.0, 1.0), genesis_level="C"))}


def s_level_attackers(seeds, sweep, quick):
    rows = [LEVEL_ATTACKERS[0], LEVEL_ATTACKERS[4]] if quick else LEVEL_ATTACKERS
    return [(key, label, RR.level_twin(make, seeds, p), kind, counted) for key, label, make, p, kind, counted in rows]


def md_level_attackers(d, seeds) -> str:
    out = [f"### Each proof-level attacker against its honest twin ({len(seeds)} seeds; a year; returns in $)", ""]
    out += ATTACK_HEAD
    for key, label, r, kind, counted in d:
        if "refused" in r:
            out.append(f"| {label} | refused at deployment | – | – | – | – | {r1('lev:' + key)} | {r['refused']} |")
        else:
            out.append(_att_row(label, r, "lev:" + key, L._got(kind, r)))
    return "\n".join(out)


def s_c_off(seeds, sweep, quick):
    nets = COFF_NETWORKS[:2] if quick else COFF_NETWORKS
    atts = RR.COFF_ATTACKERS[:1] if quick else RR.COFF_ATTACKERS
    out_n = [(label, RR.level_growth(seeds, p, w, lw)) for label, p, w, lw in nets]
    out_a = []
    for key, label, make, lw, kind in atts:
        if kind in ("liar", "shopper"):
            out_a.append((key, label, None, RR.level_twin(make, seeds[:1], R2, lw), kind))
        else:
            out_a.append((key, label, RR.level_twin(make, seeds, C_ON2, lw), RR.level_twin(make, seeds, R2, lw), kind))
    return {"networks": out_n, "attackers": out_a}


# ---------- market pricing ----------

MARKET_W = RR.MARKET_W
SETTLE_ROWS: List[Tuple[str, Params, PR.MarketWorld, Optional[World]]] = [
    ("**Round 2's rules (the design): every wait counts, once**", R2, PR.MARKET, None),
    (SW["wait_floor"].label, SW["wait_floor"].p, PR.MARKET, None),
    (SW["wait_any"].label, SW["wait_any"].p, PR.MARKET, None),
    (R1SW["idle_30"].label, R1SW["idle_30"].p, PR.MARKET, None),
    (R1SW["idle_50"].label, R1SW["idle_50"].p, PR.MARKET, None),
    (R1SW["idle_7d"].label, R1SW["idle_7d"].p, PR.MARKET, None),
    (R1SW["step_up"].label, R1SW["step_up"].p, PR.MARKET, None),
    ("the design, 100 submissions a week", R2, PR.MARKET, PR.MARKET_100),
    ("the design, starting at v2's $0.05", R2, replace(PR.MARKET, fee_start=0.05), None),
    ("round 1's rules (`V2R1`)", V2R1, PR.MARKET, None),
    ("#134's rules (v1)", V1, PR.MARKET, None),
]
SETTLE_R1 = ("design", "design", "any", "idle_30", "idle_50", "idle_7d", "step_up", "w100", "s005", "design", "v1")
MONTH_ROWS: List[Tuple[str, Params, World]] = [
    ("**the design: every outage before the seal (silence, $5)**", R2, MARKET_W),
    ("**the design: every outage after the seal (withheld, $5)**", R2, replace(MARKET_W, outage_sealed=1.0)),
    (SW["slash_1"].label + ": before the seal", SW["slash_1"].p, MARKET_W),
    (SW["slash_1"].label + ": after the seal", SW["slash_1"].p, replace(MARKET_W, outage_sealed=1.0)),
    (SW["silence_0"].label + ": before the seal", SW["silence_0"].p, MARKET_W),
    ("round 1's rules (`V2R1`): before the seal (unslashed)", V2R1, MARKET_W),
    ("#134's rules (v1)", V1, MARKET_W),
]
MONTH_R1 = {0: "month:design", 1: "month:sealed_1", 5: "month:design", 6: "month:v1"}


def s_pricing(seeds, sweep, quick):
    rows = SETTLE_ROWS[:1] if quick else SETTLE_ROWS
    settle = PR.settle_rows(seeds, rows)
    months = []
    for label, p, w in (MONTH_ROWS[:1] if quick else MONTH_ROWS):
        rs = [RR.honest_breakdown(PR.run_market(s, p, w)) for s in seeds]
        rs = [r for r in rs if r]
        months.append((label, {k: [r[k] for r in rs] for k in (rs[0] if rs else {})}, len(rs)))
    series = [] if quick else [PR.series_table(seeds, "round 2's rules (the design)", R2),
                               PR.series_table(seeds, SW["wait_floor"].label, SW["wait_floor"].p),
                               PR.provider_table(seeds, p=R2)]
    return {"settle": settle, "months": months, "series": series}


def fee_ok(r: Dict[str, list], p: Params = R2) -> bool:
    m, se = mean_se(r.get("ratio", []))
    return at_most(m, se, 1 + p.FEE_MARGIN) and at_least(m, se, 1 - p.FEE_STEP) and sum(r["collapsed"]) == 0


def md_pricing(d, seeds) -> str:
    out = [PR.settle_table(seeds, d["settle"]), "",
           f"#### The fee against break-even, D17's `FEE_MARGIN` ({len(seeds)} seeds; the runs that didn't collapse)",
           "", "| Variant | Fee / break-even over the last 13 weeks (± 2 SE) | Within [1 − `FEE_STEP`, 1 + `FEE_MARGIN`] "
           "| Runs collapsed | Round 1 (v2): fee / break-even; runs collapsed |", "|---|---|---|---|---|"]
    for i, (label, r) in enumerate(d["settle"]):
        k = SETTLE_R1[i] if i < len(SETTLE_R1) else ""
        out.append(f"| {label} | {_ms(r.get('ratio', []), 2, unit=' ×')} | {'yes' if fee_ok(r) else 'no'} | "
                   f"{sum(r['collapsed']):.0f} of {len(seeds)} | {r1('fee:' + k)}; {r1('feec:' + k)} collapsed |")
    out += ["", "Round 1 (v2): the same variant under round 1's rules; for the design and the floor-bond row, round 1's "
            "design (the floor-bond signal, 33 of 40 collapsed); round 1 measured every wait counted at "
            + r1("fee:every") + " (0 of 40 collapsed).", "",
            f"#### An honest validator's month on the market ({len(seeds)} seeds; honest validators active a "
            "month or more; $ a month)", "",
            "| Market and outages | Service fees | Usage margin | Node overhead | Slashes | Fixed costs | The bond's "
            "capital | Net | Runs with such validators | Round 1 (v2): net |", "|---|---|---|---|---|---|---|---|---|---|"]
    for i, (label, m, n) in enumerate(d["months"]):
        if not m:
            out.append(f"| {label} | – | – | – | – | – | – | – | 0 | {r1(MONTH_R1.get(i, ''))} |")
            continue
        out.append(f"| {label} | " + " | ".join(_ms(m[k], 2, pre="$") for k in
                                                ("service", "margin", "overhead", "slashed", "fixed", "capital", "net"))
                   + f" | {n} | {r1(MONTH_R1.get(i, ''))} |")
    out += ["", "Round 1 (v2): its design's market (the floor-bond signal, collapsing) with outages before the seal "
            "(unslashed) and after it ($1); D16 cites $1.11 ± 0.09 of slashes a month at $5 from round 1's any-bond "
            "market."]
    return "\n\n".join([out[0], "\n".join(out[2:])] + list(d["series"]))


PRICE_ATTACKS: List[Tuple[str, str, str, Callable[[bool], A.Actor], Params, str, bool]] = [
    ("cartel", "Cartel: 6 validators refusing half their draws", "design", lambda h: PR.Cartel(h), R2, "cartel", True),
    ("spam_wait", "Spammer: a fix a day to a $625 bounty no panel can judge yet", "design", lambda h: PR.Spammer(h), R2,
     "spam", True),
    ("spam_judged", "Spammer: a bad fix a day, judged", "design", lambda h: PR.Spammer(h, kind="judged"), R2, "spam",
     True),
    ("inflate", "Inflaters: 3 Anthropic validators of 24 posting 100 × their costs", "design",
     lambda h: PR.Inflater(h), R2, "inflate", True),
    ("inflate_small", "Inflaters on a small network (the genesis, 4 honest, the 3 inflaters)", "design",
     lambda h: PR.Inflater(h, small=True), R2, "inflate", True),
    ("pfarmer", "Fee farmer: 10 idle validators at the bond floor (twin: one)", "design",
     lambda h: PR.PricedFeeFarmer(h), R2, "farmer", True),
]
PRICE_ALT: List[Tuple[str, str, str, Callable[[bool], A.Actor], Params, str, bool]] = []
for _k, _w in (("floor", "wait_floor"), ("any", "wait_any")):
    PRICE_ALT += [
        (f"{_k}_cartel", "Cartel: 6 validators refusing half their draws", SW[_w].label, lambda h: PR.Cartel(h),
         SW[_w].p, "cartel", False),
        (f"{_k}_spam_wait", "Spammer: a fix a day to a $625 bounty no panel can judge yet", SW[_w].label,
         lambda h: PR.Spammer(h), SW[_w].p, "spam", False),
    ]


def s_price_attacks(seeds, sweep, quick):
    rows = PRICE_ATTACKS[:1] if quick else PRICE_ATTACKS
    return [(key, label, world, A.against_twin(make, seeds, p=p, metrics=PR._attack_metrics), kind, counted)
            for key, label, world, make, p, kind, counted in rows]


def s_price_alt(seeds, sweep, quick):
    rows = PRICE_ALT[:1] if quick else PRICE_ALT
    return [(key, label, world, A.against_twin(make, seeds, p=p, metrics=PR._attack_metrics), kind, counted)
            for key, label, world, make, p, kind, counted in rows]


def md_price_attacks(d, seeds) -> str:
    out = [f"### The pricing attackers against their honest twins ({len(seeds)} seeds; a year; returns in $)", "",
           "| Attacker | Market | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Mean fee: attacker's run / "
           "twin's | Its family's token price (× deployment): attacker's / twin's | Active validators (last 13 "
           "weeks) | Round 1 (v2) | What it did |", "|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, world, r, kind, counted in d:
        out.append(f"| {label} | {world} | {_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | "
                   f"{loses_cell(r['diff'], r['se'])} | ${r['fee']:.3f} / ${r['twin_fee']:.3f} | {r['price']:.2f} / "
                   f"{r['twin_price']:.2f} | {r['active']:.1f} | {r1('pr:' + key)} | {PR._did(kind, r)} |")
    out += ["", "Round 1 (v2): the same attacker on round 1's design market (the floor-bond signal, which collapsed in "
            "33 of 40 runs); for the any-bond rows, round 1's any-bond switch."]
    return "\n".join(out)


# ---------- model scores ----------

RECOVERY_ROWS: List[Tuple[str, str, Params]] = [  # "design" is the families' run
    ("sliding", SW["sliding"].label, SW["sliding"].p),
    ("block_200", SW["block_200"].label, SW["block_200"].p),
    ("plain", "fresh blocks of 100 at 80 %, " + SW["plain"].label, SW["plain"].p),
    ("v2r1", "round 1's rules (`V2R1`): plain agreement, the sliding recovery", V2R1),
]
MODES: List[Tuple[str, Optional[str], Params]] = [
    ("One vote, no scores", None, R2),
    ("**One vote, pay by score (round 2: the balanced score, recovery by blocks, the normalised factor)**", "pay", R2),
    ("One vote, pay by score, " + R1SW["median"].label, "pay", R1SW["median"].p),
    ("One vote, pay by score, " + SW["plain"].label, "pay", SW["plain"].p),
    ("Votes weighted by the score factor", "factor", R2),
    ("One vote, pay by score, round 1's scores (`V2R1`)", "pay", V2R1),
    ("One vote, pay by score, #134's scores (shadows merged, neutral at 80 %)", "pay", V1),
]
NO_BLIND_MODES = (0, 1, 4)


def family_runs(seeds, p: Params) -> Dict[str, Dict[str, list]]:
    fams: Dict[str, Dict[str, list]] = {}
    for s in seeds:
        n = SC.run_mode(s, "pay", SC.SCORE_WORLD, p)
        for f in SC.FAMILIES:
            sc, k = n.scores.state(f)
            st = n.scores.fam[f]
            row = fams.setdefault(f, {})
            for key, val in (("score", sc if sc is not None else NAN), ("factor", n.scores.factor(f)),
                             ("barred", n.scores.barred_days[f] / max(1.0, n.t / 24.0)), ("bars", st.bars),
                             ("recoveries", st.recoveries), ("blocks", st.blocks)):
                row.setdefault(key, []).append(val)
    return fams


def s_scores(seeds, sweep, quick):
    fams = family_runs(seeds, R2)
    recovery = [] if quick else [(key, label, family_runs(seeds, p)["weak"]) for key, label, p in RECOVERY_ROWS]
    modes = []
    for wi, (world_name, w) in enumerate((("blind spots", SC.SCORE_WORLD),) if quick else
                                         (("blind spots", SC.SCORE_WORLD), ("no blind spots", SC.NO_BLIND))):
        for i, (label, mode, p) in enumerate(MODES[1:2] if quick else MODES):
            if wi == 1 and i not in NO_BLIND_MODES:
                continue
            modes.append((world_name, label, SC._avg([SC.market_metrics(SC.run_mode(s, mode, w, p)) for s in seeds])))
    return {"families": fams, "recovery": recovery, "modes": modes}


HERD_ROWS: List[Tuple[str, str, str, bool, Optional[float], Params, bool]] = [
    ("herd_mid_det", "`mid` (90 %), receipts detectable", "mid", True, None, R2, True),
    ("herd_mid", "`mid` (90 %), not detectable (upper bound)", "mid", False, None, R2, True),
    ("herd_weak_det", "`weak` (68 %), receipts detectable", "weak", True, None, R2, True),
    ("herd_weak", "`weak` (68 %), not detectable (upper bound)", "weak", False, None, R2, True),
    ("herd_mid_25", "`mid`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "mid", False, 0.25, R2, True),
    ("herd_weak_25", "`weak`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "weak", False, 0.25, R2, True),
    ("herd_mid_plain", "`mid`, not detectable, " + SW["plain"].label, "mid", False, None, SW["plain"].p, False),
    ("herd_weak_plain", "`weak`, not detectable, " + SW["plain"].label, "weak", False, None, SW["plain"].p, False),
    ("herd_weak_25_plain", "`weak`, not detectable, $0.25, " + SW["plain"].label, "weak", False, 0.25,
     SW["plain"].p, False),
]
HERD_R1 = {"herd_mid_plain": "her:herd_mid", "herd_weak_plain": "her:herd_weak",
           "herd_weak_25_plain": "her:herd_weak_25"}


def s_herds(seeds, sweep, quick):
    herds = []
    for key, label, f, det, fee, p, counted in (HERD_ROWS[3:4] if quick else HERD_ROWS):
        w = SC.SCORE_WORLD if fee is None else replace(SC.SCORE_WORLD, service_fee=fee)
        herds.append((key, label, SC.twins(lambda h, f=f, d=det, w=w: SC.Herders(h, family=f, detectable=d, w=w),
                                           seeds, RR.herd_metrics, p), counted))
    movers = {} if quick else {"design": SC.movers(seeds, p=R2),
                               "instant": SC.movers(seeds, p=replace(R2, MOVE_REREGISTERS=False)),
                               "party": SC.movers_party(seeds, p=R2)}
    return {"herds": herds, "movers": movers}


CROWD_ROWS: List[Tuple[str, str, Params]] = [  # "design" is the herding section's movers run
    ("plain", SW["plain"].label, SW["plain"].p),
    ("sliding", SW["sliding"].label, SW["sliding"].p),
    ("silence_0", SW["silence_0"].label, SW["silence_0"].p),
    ("v2r1", "round 1's rules (`V2R1`)", V2R1),
]


def s_crowd(seeds, sweep, quick):
    """Everyone moves to the top model under each round-2 alternative that could decide the crowding."""
    return [] if quick else [(key, label, SC.movers(seeds, p=p)) for key, label, p in CROWD_ROWS]


def crowd_md(design, rows, seeds) -> str:
    out = [f"### Crowding into the top model, rule by rule ({len(seeds)} seeds; a year; every validator moves, "
           "registering again; `WAIT_CROWD_MAX` 15 %)", "",
           "| Rule | Submissions that waited for a panel | Draws the caps lowered | Families with at least 10 % of "
           "the validators | Share of drawable validators in `weak` / `low` at the year's end | Family changes in the "
           "year |", "|---|---|---|---|---|---|"]
    for label, r in [("**Round 2's rules (the design)**", design)] + [(label, r) for _, label, r in rows]:
        out.append(f"| {label} | {_ms(r['waited'], 1, 100, unit=' %')} | {_ms(r['stepped_down'], 1, 100, unit=' %')} | "
                   f"{_ms(r['families_10'], 1)} | {_ms(r['share_weak'], 0, 100, unit=' %')} / "
                   f"{_ms(r['share_low'], 0, 100, unit=' %')} | {_ms(r['moves'], 0)} |")
    out += ["", "Round 1 (v2): " + r1("crowd") + " of submissions waited."]
    return "\n".join(out)


def md_scores(sc, hd, seeds, crowd=()) -> str:
    out = [f"### The families' scores under round 2's rules ({len(seeds)} seeds; at the year's end; the balanced "
           "score)", "",
           "| Family | True accuracy (assumed) | Score (counted verdicts) | Fee factor (normalised) | Share of the year "
           "barred | Times barred / recovered | Recovery blocks judged |", "|---|---|---|---|---|---|---|"]
    for f in SC.FAMILIES:
        m = sc["families"].get(f)
        if not m:
            continue
        out.append(f"| `{f}` | {100 * SC.SCORE_WORLD.accuracy_of(f):.0f} % | {_ms(m['score'], 1, 100, unit=' %')} | "
                   f"{_ms(m['factor'], 2, unit=' ×')} | {_ms(m['barred'], 0, 100, unit=' %')} | "
                   f"{mean(m['bars']):.1f} / {mean(m['recoveries']):.1f} | {mean(m['blocks']):.1f} |")
    out += ["", "Round 1 (v2), `weak`: score " + r1("sc:weak_score") + ", barred " + r1("sc:weak_barred")
            + " of the year, barred / recovered " + r1("sc:weak_bars") + " times."]
    if sc["recovery"]:
        out += ["", recovery_md(sc, seeds)]
    fams = SC.FAMILIES
    out += ["", f"### One vote, pay by score, weighted votes ({len(seeds)} seeds; a year)", "",
            "| Families | Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family "
            "(%) | Service fees per submission ($) | " + " | ".join(f"`{f}` net a month ($)" for f in fams) + " |",
            "|---" * (6 + len(fams)) + "|"]
    for world, label, m in sc["modes"]:
        out.append(f"| {world} | {label} | {_ms(m['bad_per_100'], 2)} | {_ms(m['good_failed_pct'], 2)} | "
                   f"{_ms(m['one_family'], 2, 100)} | {_ms(m['fee_per_check'], 3)} | "
                   + " | ".join(_ms(m[f'net_{f}'], 2) for f in fams) + " |")
    out += ["", "Round 1 (v2), blind spots: service fees per submission " + r1("fees_pay") + " with pay by score, "
            + r1("fees_none") + " without."]
    if hd["movers"]:
        r, i = hd["movers"]["design"], hd["movers"]["instant"]
        tw = {k[5:]: v for k, v in r.items() if k.startswith("twin_")}

        def row(label, key, nd=1, scale=1.0, unit=""):
            return (f"| {label} | {_ms(tw[key], nd, scale, unit=unit)} | {_ms(r[key], nd, scale, unit=unit)} | "
                    f"{_ms(i[key], nd, scale, unit=unit)} |")
        out += ["", f"### Everyone moves to the top model ({len(seeds)} seeds; a year; every validator reconsiders "
                "monthly and changes to the family paying most per head when it pays 10 % more)", "",
                "| | Nobody moves | Everyone moves, registering again (the design) | Everyone moves at once (#134's "
                "reading) |", "|---|---|---|---|"]
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
        pm = hd["movers"]["party"]
        out += ["", f"Four validators starting in `low` that move (registering again) against the same four staying: "
                f"return − twin's **{_pm(pm['diff'], pm['se'])}** $ a year (doesn't gain: "
                f"{gain_cell(pm['diff'], pm['se'])}). Round 1 (v2): crowding " + r1("crowd") + " of submissions "
                "waited."]
        if crowd:
            out += ["", crowd_md(r, crowd, seeds)]
    out += ["", f"### Herding ({len(seeds)} seeds; a year; 4 herders of one family among 16 honest validators; each "
            "votes pass, the public base rate's majority)", "",
            "| Herders | Their agreement with outcomes (twin's) | ...balanced over passed and failed outcomes | Their "
            "family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Return − "
            "twin's ($, ± 2 SE) | Doesn't gain | Loses | Round 1 (v2): the same herders, plain agreement |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for key, label, r, counted in hd["herds"]:
        def two(k, nd, scale=1.0, unit=""):
            return f"{_ms(r[k], nd, scale, unit=unit)} ({_ms(r['twin_' + k], nd, scale, unit=unit)})"
        out.append(f"| {label} | {two('agree', 1, 100, ' %')} | {two('agree_balanced', 1, 100, ' %')} | "
                   f"{two('family_score', 1, 100, ' %')} | {two('barred', 0, 100, ' %')} | {two('bad_per_100', 2)} | "
                   f"{_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | {loses_cell(r['diff'], r['se'])} | "
                   f"{r1(HERD_R1.get(key, 'her:' + key))} |")
    return "\n".join(out)


def recovery_md(sc, seeds) -> str:
    rows = [("design", "**Fresh blocks of 100 at `SCORE_MIN` + 10 points (80 %), the balanced score (the design)**",
             sc["families"]["weak"])] + list(sc["recovery"])
    out = [f"### Recovery by chance ({len(seeds)} seeds; a year; the score world; the `weak` family, right 68 % of the "
           "time, as it is barred and recovers)", "",
           "| Recovery rule | Recoveries a year | Times barred | Share of the year barred | Blocks judged a year | "
           "Recoveries per block judged (pooled) | Score at the year's end |", "|---|---|---|---|---|---|---|"]
    for key, label, m in rows:
        blocks = sum(m["blocks"])
        per = f"{100 * sum(m['recoveries']) / blocks:.1f} %" if blocks else "– (no blocks: a sliding test)"
        out.append(f"| {label} | {_ms(m['recoveries'], 2)} | {_ms(m['bars'], 2)} | "
                   f"{_ms(m['barred'], 0, 100, unit=' %')} | {_ms(m['blocks'], 1)} | {per} | "
                   f"{_ms(m['score'], 1, 100, unit=' %')} |")
    out += ["", "D14's estimates (hand, normal approximation): a 68 % family passes a block of 100 at 80 % about 1.9 % of "
            "the time; barred all year, it fills 10 to 15 blocks, so 0.2 to 0.3 chance recoveries a year. Round 1 "
            "(v2): " + r1("sc:weak_bars") + " barred / recovered a year."]
    return "\n".join(out)


SCORE_MARKETS: List[Tuple[str, Params]] = [("design", R2), ("plain agreement", SW["plain"].p),
                                           ("round 1's rules (`V2R1`)", V2R1)]
MARKET_HERDS: List[Tuple[str, str, str, bool, Params, bool]] = [
    ("mherd_mid", "`mid` (90 %), not detectable, the design's market", "mid", False, R2, True),
    ("mherd_weak", "`weak` (68 %), not detectable, the design's market", "weak", False, R2, True),
    ("mherd_weak_plain", "`weak`, not detectable, the design's market, " + SW["plain"].label, "weak", False,
     SW["plain"].p, False),
]


def s_scores_market(seeds, sweep, quick):
    compare = F.market_compare(seeds, SCORE_MARKETS[:1] if quick else SCORE_MARKETS)
    herds = []
    for key, label, fam, det, p, counted in (MARKET_HERDS[1:2] if quick else MARKET_HERDS):
        def make(h, fam=fam, det=det, p=p):
            return F.MarketHerders(h, p=p, family=fam, detectable=det)

        def metrics(net, a):
            return {**RR.herd_metrics(net, a), "fee": F._market_fee(net), "active": PR.settle(net)["active"]}
        herds.append((key, label, SC.twins(make, seeds, metrics), counted))
    return {"compare": compare, "herds": herds}


def md_scores_market(d, seeds) -> str:
    table = F.market_compare_md(seeds, d["compare"]).split("\n\nMarket \"design\"")[0]
    out = [table, "", "Market \"design\": round 2's rules, the fee starting at the ceiling. The families are priced as "
           "the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight model). "
           "Prospects decide to enter on the unscaled fee.", "",
           f"### Herding on the market fee ({len(seeds)} seeds; a year; 4 undetectable herders of one family beside "
           "the market's validators)", "",
           "| Herders | Their agreement (twin's) | Their family's score (twin's) | Family barred (twin's) | Bad fixes "
           "merged per 100 paid (twin's) | Mean fee | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Round 1 "
           "(v2) |", "|---|---|---|---|---|---|---|---|---|---|"]
    r1m = {"mherd_mid": "her:mherd_mid", "mherd_weak": "her:mherd_weak", "mherd_weak_plain": "her:mherd_weak"}
    for key, label, r, counted in d["herds"]:
        def two(k, nd, scale=1.0, unit=""):
            return f"{_ms(r[k], nd, scale, unit=unit)} ({_ms(r['twin_' + k], nd, scale, unit=unit)})"
        out.append(f"| {label} | {two('agree', 1, 100, ' %')} | {two('family_score', 1, 100, ' %')} | "
                   f"{two('barred', 0, 100, ' %')} | {two('bad_per_100', 2)} | ${mean(r['fee']):.3f} | "
                   f"{_pm(r['diff'], r['se'])} | {gain_cell(r['diff'], r['se'])} | {loses_cell(r['diff'], r['se'])} | "
                   f"{r1(r1m.get(key, ''))} |")
    out += ["", "Round 1 (v2): the same herders on round 1's design market (collapsing); its weak herders gained "
            + r1("her:mherd_weak_any") + " $ on its working (any-bond) market."]
    return "\n".join(out)


# ---------- everything once ----------

SECTIONS: Dict[str, Callable] = {
    "growth": s_growth, "tees": s_tees, "attackers": s_attackers, "colluder": s_colluder, "silent": s_silent,
    "constitution": s_constitution, "removal": s_removal, "sybil": s_sybil, "watch": s_watch, "ktable": s_ktable,
    "level_networks": s_level_networks, "level_attackers": s_level_attackers, "c_off": s_c_off,
    "pricing": s_pricing, "price_attacks": s_price_attacks, "price_alt": s_price_alt, "scores": s_scores,
    "herds": s_herds, "scores_market": s_scores_market, "crowd": s_crowd,
}
# the heaviest first, so the processes share the load
ORDER = ("price_attacks", "constitution", "herds", "scores", "scores_market", "pricing", "level_attackers", "colluder",
         "price_alt", "c_off", "watch", "crowd", "removal", "tees", "growth", "level_networks", "silent", "attackers",
         "sybil", "ktable")


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


@functools.lru_cache(maxsize=1)
def quick_collect() -> Dict[str, object]:
    """`collect((1,), (1,), quick=True)`, once a process: the tests of round 2 and round 3 share it (they copy it before
    changing anything)."""
    return collect((1,), (1,), quick=True)


# ---------- the acceptance criteria (D17, round 2; round 3 by `Params.GAIN_TEST` and `LONE_CATCH_COUNT`) ----------

@dataclass(frozen=True)
class Criterion:
    name: str
    met: bool
    decides: str
    threshold: str = ""
    loses: str = ""  # round 1's "loses", reported beside the attacker criteria

    @property
    def verdict(self) -> str:
        return "met" if self.met else "not met"


def rows_dont_gain(rows: List[Tuple[str, float, float]], tol: float = R2.GAIN_TOLERANCE,
                   test: str = "doesnt_gain") -> Tuple[bool, str, str]:
    """Every row doesn't gain (D17, round 2), or (`test` "not_shown", round 3) isn't shown to gain: (met, what decides
    it, how many also lose)."""
    rows = [(n, m, se) for n, m, se in rows if m == m]
    if not rows:
        return False, "no rows", ""
    bad = [(n, m, se) for n, m, se in rows if not GAIN_TESTS[test](m, se, tol)]
    lose = sum(1 for _, m, se in rows if loses(m, se))
    note = f"{lose} of {len(rows)} lose"
    shown = test == "not_shown"
    if not bad:
        n, m, se = max(rows, key=lambda x: x[1] + 2 * x[2])
        return True, (f"none of {len(rows)} {'is shown to gain' if shown else 'gains'}; the closest: {n} "
                      f"({_pm(m, se)} $)"), note
    return False, (f"{len(bad)} of {len(rows)} "
                   + ("shown to gain, or not bounded by the tolerance: " if shown else "gain or aren't shown not to: ")
                   + "; ".join(f"{n} ({_pm(m, se)} $)" for n, m, se in bad)), note


def gain_words(p: Params) -> Tuple[str, str]:
    """The criterion's words and its threshold, as the acceptance table prints them (round 2 or round 3)."""
    if p.GAIN_TEST == "not_shown":
        return "isn't shown to gain", f"mean − 2 SE ≤ 0 and mean + 2 SE ≤ ${p.GAIN_TOLERANCE:g}"
    return "doesn't gain", f"mean ≤ 0 and mean + 2 SE ≤ ${p.GAIN_TOLERANCE:g}"


def lone_share(col: Dict[str, list], p: Params = R2) -> Tuple[float, float]:
    """LONE_CATCH_SHARE's number, pooled over the runs (± SE): round 3 (`LONE_CATCH_COUNT` "own") the share of the
    colluding lone validator's own k = 1 verdicts reversed before payment; round 2 ("all") of every bad fix its
    accomplice passed, whoever judged it (`rerun.caught`)."""
    if p.LONE_CATCH_COUNT == "own":
        return pooled(col["own_reversed"], col["own_resolved"])
    return RR.caught(col)


def counted_rows(d: Dict[str, object]) -> Dict[str, List[Tuple[str, float, float]]]:
    """The attackers counted (D17): on the design's values, the new rules included, every herder row; not the
    counterfactuals, the switches, round 1's rules or #134's."""
    ov = [(label, r["diff"], r["se"]) for key, label, r, kind, counted in d["attackers"] if counted]
    for key, label, m in d["colluder"]:
        if key == "design":
            ov.append((f"Colluding genesis ({label.replace('**', '')})", *mean_se(m["diff"])))
    ov += [(label.replace("**", ""), r["diff"], r["se"]) for key, label, r, counted in d["silent"] if counted]
    ov += [(f"Constitution coalition: {label.replace('**', '')}", r["diff"], r["se"])
           for key, label, r, counted in d["constitution"] if counted]
    ov += [(f"Coalition of removals: {label.replace('**', '')}", r["diff"], r["se"])
           for key, label, r, counted in d["removal"] if counted]
    for kind in ("lazy", "bribed"):
        for vol, rate, r in d["watch"][kind]:
            if not vol and abs(rate - R2.AUDIT_RATE) < 1e-12:
                ov.append((f"D13's {kind} cheater (audits at {100 * rate:g} %, no volunteers)", r["diff"], r["se"]))
    lv = [(label.replace("**", ""), r["diff"], r["se"]) for key, label, r, kind, counted in d["level_attackers"]
          if counted and "refused" not in r]
    pr = [(f"{label} ({world})", r["diff"], r["se"]) for key, label, world, r, kind, counted in d["price_attacks"]
          if counted]
    sc = [(f"Herders: {label}", r["diff"], r["se"]) for key, label, r, counted in d["herds"]["herds"] if counted]
    sc += [(f"Herders on the market: {label}", r["diff"], r["se"]) for key, label, r, counted
           in d["scores_market"]["herds"] if counted]
    return {"open": ov, "pricing": pr, "levels": lv, "scores": sc}


def acceptance(d: Dict[str, object], p: Params = R2) -> List[Criterion]:
    """Each criterion of "Acceptance criteria for open validators", judged as D17 says after round 2."""
    out: List[Criterion] = []
    rows = counted_rows(d)
    words, tol = gain_words(p)
    for name, key in ((f"Each open-validator attacker {words} against its honest twin", "open"),
                      (f"Each pricing attacker {words} against its honest twin", "pricing"),
                      (f"Each proof-level attacker {words} against its honest twin (answer shopping at 1 in 10; "
                       "the level C rows after C is switched on by ADR)", "levels"),
                      (f"Each scoring attacker (the herders) {words} against its honest twin", "scores")):
        met, why, note = rows_dont_gain(rows[key], p.GAIN_TOLERANCE, p.GAIN_TEST)
        out.append(Criterion(name, met, why, tol, note))

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
    c, cse = lone_share(col, p)
    dm, dse = mean_se(col["diff"])
    met = gain_ok(dm, dse, p) and at_least(c, cse, p.LONE_CATCH_SHARE)
    if p.LONE_CATCH_COUNT == "own":
        a, ase = RR.caught(col)
        out.append(Criterion(
            f"The colluding lone validator {words}, and at least `LONE_CATCH_SHARE` ({100 * p.LONE_CATCH_SHARE:g} %) "
            "of the bad fixes it passes itself, as the lone judge, are reversed before any payment (pooled), with two "
            "audits", met,
            f"return − twin's {_pm(dm, dse)} $ ({words}: {gain_cell(dm, dse, p.GAIN_TOLERANCE, p.GAIN_TEST)}); its own "
            f"verdicts reversed before payment {_pct(c, 1)} ± {_pct(2 * cse, 1)} ({sum(col['own_reversed']):.0f} of "
            f"{sum(col['own_resolved']):.0f}); the trust point, every bad fix of its accomplice, whoever judged it: "
            f"{_pct(a, 1)} ± {_pct(2 * ase, 1)} ({sum(col['reversed']):.0f} of {sum(col['resolved']):.0f} that "
            f"reached an outcome; {sum(col['pending']):.0f} still pending at the year's end)",
            f"{tol}; share − 2 SE ≥ {100 * p.LONE_CATCH_SHARE:g} %", loses_cell(dm, dse)))
    else:
        out.append(Criterion(
            f"The colluding lone validator {words}, and at least `LONE_CATCH_SHARE` ({100 * p.LONE_CATCH_SHARE:g} %) "
            "of the bad fixes it passes are reversed before any payment (pooled), with two audits", met,
            f"return − twin's {_pm(dm, dse)} $ ({words}: {gain_cell(dm, dse, p.GAIN_TOLERANCE, p.GAIN_TEST)}); "
            f"reversed before payment {_pct(c, 1)} ± {_pct(2 * cse, 1)} ({sum(col['reversed']):.0f} of "
            f"{sum(col['resolved']):.0f} that reached an outcome; {sum(col['pending']):.0f} still pending at the "
            "year's end)", f"{tol}; share − 2 SE ≥ {100 * p.LONE_CATCH_SHARE:g} %", loses_cell(dm, dse)))

    adds = [(label, r) for key, label, r, counted in d["constitution"] if counted]
    rems = [(label, r) for key, label, r, counted in d["removal"] if counted]
    small_add = sum(r["below_need"] * len(r["diffs"]) for _, r in adds)
    small_rem = sum(r["below_need"] * len(r["diffs"]) for _, r in rems)
    out.append(Criterion(
        f"The constitution waits for the network: no adding ADR or escalated fix passes while fewer than "
        f"{p.CONSTITUTION_MIN_ELIGIBLE} validators are eligible, and no removal while fewer than "
        f"{p.REMOVAL_MIN_ELIGIBLE}, in any run", bool(adds) and bool(rems) and small_add == 0 and small_rem == 0,
        f"adding ADRs and escalated fixes passed below {p.CONSTITUTION_MIN_ELIGIBLE}, all runs: {small_add:g} (over "
        f"{len(adds)} coalitions); removals passed below {p.REMOVAL_MIN_ELIGIBLE}: {small_rem:g} (over {len(rems)}); "
        f"ADRs passed: " + ", ".join(f"{r['passed']:.2f}" for _, r in adds + rems) + " a run", "0 runs"))

    st = d["pricing"]["settle"][0][1]
    m, se = mean_se(st.get("ratio", []))
    dead = sum(st["collapsed"])
    out.append(Criterion(
        f"The fee settles within `FEE_MARGIN` ({100 * p.FEE_MARGIN:g} %) above break-even and at least break-even less "
        "one step, and no run collapses", fee_ok(st, p),
        f"from the ceiling, every wait counted: fee / break-even over the last 13 weeks "
        f"{_ms(st.get('ratio', []), 2, unit=' ×')} (the runs that didn't collapse); {dead:.0f} of "
        f"{len(st['collapsed'])} runs collapsed below 3 active validators",
        f"{1 - p.FEE_STEP:.2f} ≤ ratio ± 2 SE ≤ {1 + p.FEE_MARGIN:.2f}; 0 runs collapse"))

    mv = d["herds"]["movers"]
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
    s1, s3, s125 = sh.get("shopper_1"), sh.get("shopper_3"), sh.get("shopper_125")

    def ok(r):
        return r is not None and "refused" not in r
    if ok(s1):
        out.append(Criterion(
            f"Answer shopping, the trust point: it {words} at 1 in 10; at 3 in 10 the report gives its gain",
            gain_ok(s1["diff"], s1["se"], p),
            f"at 1 in 10: {_pm(s1['diff'], s1['se'])} $; at 3 in 10 (reported): "
            + (f"{_pm(s3['diff'], s3['se'])} $" if ok(s3) else "not run")
            + ("; at #125's measured room (reported): " + f"{_pm(s125['diff'], s125['se'])} $" if ok(s125) else ""),
            f"{tol} at 1 in 10", loses_cell(s1["diff"], s1["se"])))
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
    out = [f"### Acceptance criteria for open validators under D17, round 2 ({len(seeds)} seeds; sweeps on "
           f"{len(d['sweep'])}; ± 2 standard errors)", "",
           "| Criterion | Verdict | Threshold | What decides it | Loses (round 1's criterion) |", "|---|---|---|---|---|"]
    for c in acceptance(d):
        out.append(f"| {c.name} | **{c.verdict}** | {c.threshold} | {c.decides} | {c.loses or '–'} |")
    return "\n".join(out)


# ---------- the design's derived numbers against the run ----------

def derived_md(d: Dict[str, object]) -> str:
    con = {k: r for k, _, r, _ in d["constitution"]}
    col = {k: m for k, _, m in d["colluder"]}
    sil = {k: r for k, _, r, _ in d["silent"]}
    gro = {k: m for k, _, m in d["growth"]["rows"]}
    tee = {k: m for k, _, m in d["tees"]}
    weak = d["scores"]["families"].get("weak")
    herds = {k: r for k, _, r, _ in d["herds"]["herds"]}
    months = d["pricing"]["months"]
    settle = d["pricing"]["settle"]

    def twin(r):
        return f"{_pm(r['diff'], r['se'])} $" if r is not None else "not run"
    rows = []
    if "c5" in con:
        rows.append(("The early coalition of 5, from 21 with a $15 deposit (D7)", "about −$255 ± 152", twin(con["c5"])))
    if "c3" in con:
        rows.append(("The early coalition of 3, from 21 with $15 (D7)", "about −$429 ± 135", twin(con["c3"])))
    if "c5_14" in con:
        rows.append(("The coalition of 5 from 14 with $15 (D7)", "about −$8 ± 260 (not significant)",
                     twin(con["c5_14"])))
    if "design" in col:
        c, cse = RR.caught(col["design"])
        rows.append(("The colluding genesis's bad fixes reversed before payment, two audits (D13, D17)", "about 96 %",
                     f"{_pct(c, 1)} ± {_pct(2 * cse, 1)}"))
    if weak:
        blocks = sum(weak["blocks"])
        rows.append(("The weak family's chance recoveries a year, blocks of 100 at 80 % (D14)", "0.2 to 0.3",
                     _ms(weak["recoveries"], 2)))
        rows.append(("A 68 % family passing a block of 100 at 80 % (D14)", "about 1.9 %",
                     f"{100 * sum(weak['recoveries']) / blocks:.1f} % ({sum(weak['recoveries']):.0f} of "
                     f"{blocks:.0f} blocks)" if blocks else "no block judged"))
    if "silent" in sil:
        rows.append(("The bribed silent judge at $5 (D16)", "near the withholder's −$20", twin(sil["silent"])))
    if "withhold" in sil:
        rows.append(("The bribed withholder at $5 (round 1's switch)", "−$20 ± 9 (measured, round 1)",
                     twin(sil["withhold"])))
    if len(months) > 1 and months[1][1]:
        rows.append(("An honest validator's slashes a month, every outage after the seal at $5 (D16)",
                     "$1.11 ± 0.09 (measured on round 1's any-bond market)",
                     _ms(months[1][1]["slashed"], 2, pre="$")))
    if settle:
        r = settle[0][1]
        rows.append(("The fee over the last 13 weeks, every wait counted (D9)",
                     "1.21 ± 0.04 × break-even, 0 of 40 collapse (round 1's switch)",
                     f"{_ms(r.get('ratio', []), 2, unit=' ×')}, {sum(r['collapsed']):.0f} of {len(r['collapsed'])} "
                     "collapse"))
    if "design" in gro:
        rows.append(("Three TEE types, the cap from k = 5: panels of 3 with one type's majority (D6)",
                     "77 % ± 8 (measured, round 1)", _ms(gro["design"]["one_tee_k3"], 0, 100, unit=" %")))
    if "tee5" in tee:
        m = tee["tee5"]
        rows.append(("Five TEE types, even, the cap from k = 3: one-type majorities of 3 / draws lowered / waited "
                     "(D6)", "none / 6 % ± 1 / 22 % ± 3 (measured, round 1, placeholder types)",
                     f"{_ms(m['one_tee_k3'], 0, 100, unit=' %')} / {_ms(m['stepped'], 0, 100, unit=' %')} / "
                     f"{_ms(m['waited'], 0, 100, unit=' %')}"))
    if "herd_weak" in herds:
        r = herds["herd_weak"]
        rows.append(("An always-pass herder's balanced agreement (D14)", "50.1 % ± 0.1 (measured, round 1)",
                     _ms(r["agree_balanced"], 1, 100, unit=" %")))
    out = ["### The design's derived numbers against the run", "",
           "| What | The design says | This run measures |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    return "\n".join(out)


# ---------- a rule against its alternative ----------

def rule_vs_alternative(d: Dict[str, object]) -> str:
    """One row per round-2 rule: the number that measures it, under the rule and under each alternative."""
    col = {k: m for k, _, m in d["colluder"]}
    gro = {k: m for k, _, m in d["growth"]["rows"]}
    tee = {k: m for k, _, m in d["tees"]}
    sil = {k: r for k, _, r, _ in d["silent"]}
    con = {k: r for k, _, r, _ in d["constitution"]}
    rem = {k: r for k, _, r, _ in d["removal"]}
    settle = {label: r for label, r in d["pricing"]["settle"]}
    herd = {k: r for k, _, r, _ in d["herds"]["herds"]}
    rec = {k: m for k, _, m in d["scores"]["recovery"]}
    weak = d["scores"]["families"].get("weak")
    pa = {k: r for k, _, _, r, _, _ in d["price_attacks"] + d["price_alt"]}

    def tw(r, what=""):
        if r is None or "refused" in r:
            return "–"
        return f"{what}{_pm(r['diff'], r['se'])} $ (doesn't gain: {gain_cell(r['diff'], r['se'])})"

    def col_cell(k):
        if k not in col:
            return "–"
        m = col[k]
        c, cse = RR.caught(m)
        dm, dse = mean_se(m["diff"])
        g = gro.get(k)
        pay = f"; honest k = 1 pay {_ms(g['pay_days'], 1)} days" if g else ""
        return f"colluder {_pm(dm, dse)} $, {_pct(c, 1)} ± {_pct(2 * cse, 1)} reversed{pay}"

    def fee_cell(label):
        r = settle.get(label)
        if r is None:
            return "–"
        return f"fee / break-even {_ms(r.get('ratio', []), 2, unit=' ×')}; {sum(r['collapsed']):.0f} collapsed"

    def tee_cell(m):
        if m is None:
            return "–"
        return (f"one type holds a k = 3 majority on {_ms(m['one_tee_k3'], 0, 100, unit=' %')} (one vendor "
                f"{_ms(m['one_vendor_k3'], 0, 100, unit=' %')}); caps lowered {_ms(m['stepped'], 0, 100, unit=' %')}; "
                f"waited {_ms(m['waited'], 0, 100, unit=' %')}")

    def rec_cell(m):
        if m is None:
            return "–"
        return f"weak family: {_ms(m['recoveries'], 2)} recoveries a year, barred {_ms(m['barred'], 0, 100, unit=' %')}"

    rows = [
        ("Every wait counts, once (`WAIT_SIGNAL` \"every\")",
         fee_cell(SETTLE_ROWS[0][0]) + "; " + tw(pa.get("spam_wait"), "spammer ") + "; " + tw(pa.get("cartel"), "cartel "),
         "; ".join(f"{SW[k].label}: {fee_cell(SW[k].label)}; " + tw(pa.get(f"{s}_spam_wait"), "spammer ")
                   for k, s in (("wait_floor", "floor"), ("wait_any", "any")))),
        ("$5 for silence and for withholding",
         tw(sil.get("silent"), "silent ") + "; " + tw(sil.get("withhold"), "withholder "),
         f"{SW['slash_1'].label}: " + tw(sil.get("silent_1"), "silent ") + ", " + tw(sil.get("withhold_1"), "withholder ")
         + f"; {SW['silence_0'].label}: " + tw(sil.get("silent_0"), "silent ")),
        ("21 for adding ADRs and escalated fixes, 14 for removals, a $15 deposit",
         "; ".join(tw(con.get(k), lab) for k, lab in (("c5", "5 early: "), ("c3", "3 early: "), ("e5", "escalated: ")))
         + "; " + tw(rem.get("r5"), "removals: "),
         "; ".join(f"{lab}: " + ", ".join(tw(con.get(f"c{n}{suf}"), f"{n} early ") for n in (5, 3))
                   for suf, lab in (("_14", "14 for every ADR"), ("_28", "28 for every ADR"), ("_d0", "$0"),
                                    ("_d25", "$25")))
         + "; " + tw(con.get("e5_funder"), "escalated, forfeits to the funder: ")
         + "; " + tw(rem.get("r5_d0"), "removals at $0: ")),
        ("Two audits of every k = 1 verdict (`K1_AUDITS` 2)", col_cell("design"),
         f"{SW['k1_audits_1'].label}: {col_cell('k1_audits_1')}"),
        ("The balanced score", tw(herd.get("herd_weak"), "weak herders ") + "; " + tw(herd.get("herd_mid"), "mid herders "),
         f"{SW['plain'].label}: " + tw(herd.get("herd_weak_plain"), "weak herders ") + "; "
         + tw(herd.get("herd_mid_plain"), "mid herders ")),
        ("Recovery on fresh blocks of 100 at + 10 points", rec_cell(weak),
         "; ".join(f"{SW[k].label}: {rec_cell(rec.get(k))}" for k in ("sliding", "block_200"))),
        ("The TEE cap from k = 3 while 5 types are accepted, else from k = 5",
         "three types, even: " + tee_cell(gro.get("design")) + "; five, even: " + tee_cell(tee.get("tee5")),
         "; ".join(f"{lab}: {tee_cell(tee.get(k))}" for k, lab in
                   (("tee3_skew", "three, skewed"), ("tee5_skew", "five, skewed"),
                    ("tee3_from3", "three, the cap from k = 3"), ("tee5_from5", "five, the cap from k = 5")))),
        ("Round 2's rules as a whole", col_cell("design") + "; " + fee_cell(SETTLE_ROWS[0][0]),
         f"{SW['v2r1'].label}: {col_cell('v2r1')}; {fee_cell(SETTLE_ROWS[9][0])}; "
         + tw(con.get("c5_v2r1"), "coalition of 5 ")),
    ]
    out = [f"### A rule against its alternative: round 2's rules ({len(d['seeds'])} seeds; the same seeds for each "
           "pair)", "", "| Round 2's rule | Under the rule | Under each alternative |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    r1rows = [
        ("k = 1: the hold, `K1_PENDING_MAX` 10", col_cell("design"),
         "; ".join(f"{R1SW[k].label}: {col_cell(k)}" for k in ("k1_cap_5", "k1_cap_20", "k1_batch"))),
        ("k = 1's window 7 days", col_cell("design"),
         "; ".join(f"{R1SW[k].label}: {col_cell(k)}" for k in ("k1_window_14", "k1_window_30"))),
        ("`SHADOW_PER_WAITING` 3", col_cell("design"), f"{R1SW['no_wait_shadows'].label}: {col_cell('no_wait_shadows')}"),
        ("False verdict: the whole bond", "; ".join(tw(r, lab) for r, lab in
                                                    ((({k: r for k, _, r, _, _ in d["attackers"]}).get("grinder"),
                                                      "grinder "),)),
         "2,000: " + "; ".join(tw(r, lab) for r, lab in
                               ((({k: r for k, _, r, _, _ in d["attackers"]}).get("grinder_2000"), "grinder "),))
         + "; " + col_cell("false_2000")),
        ("`IDLE_HIGH` 40 %, idling over one period, symmetric steps", fee_cell(SETTLE_ROWS[0][0]),
         "; ".join(f"{R1SW[k].label}: {fee_cell(R1SW[k].label)}" for k in ("idle_30", "idle_50", "idle_7d", "step_up"))),
    ]
    out += ["", f"### Round 1's rules against their alternatives, on round 2's rules ({len(d['seeds'])} seeds)", "",
            "| Round 1's rule | Under the rule | Under each alternative |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in r1rows]
    return "\n".join(out)


# ---------- the report ----------

def render(d: Dict[str, object]) -> str:
    seeds, sweep = d["seeds"], d["sweep"]
    head = (f"# Open validators, v3: #141's round 2 ({len(seeds)} seeds; the sybil and audit sweeps on {len(sweep)})"
            + (" — QUICK: one row per section, for the tests" if d["quick"] else ""))
    parts = [head,
             "## Growth from one validator under the hold, and the TEE types", md_growth(d["growth"], seeds),
             md_tees(d["growth"], d["tees"], seeds),
             "## The attackers", md_attackers(d["attackers"], seeds), md_colluder(d["colluder"], seeds),
             md_silent(d["silent"], seeds), md_constitution(d["constitution"], seeds),
             md_removal(d["removal"], seeds), RR.md_sybil(d["sybil"], sweep),
             R.watchers_table(sweep, "lazy", data=d["watch"]["lazy"]),
             R.watchers_table(sweep, "bribed", data=d["watch"]["bribed"]),
             "## The k table compared", F.k_table_md(seeds, d["ktable"]),
             "## Proof levels", RR.md_level_networks(d["level_networks"], seeds),
             md_level_attackers(d["level_attackers"], seeds),
             RR.md_c_off(d["c_off"], seeds, d["level_attackers"]).replace(", spec PR pending", ""),
             "## Market pricing", md_pricing(d["pricing"], seeds),
             md_price_attacks(d["price_attacks"] + d["price_alt"], seeds),
             "## Model scores", md_scores(d["scores"], d["herds"], seeds, d.get("crowd", ())),
             md_scores_market(d["scores_market"], seeds)]
    if not d["quick"]:
        parts += ["## Derived against measured", derived_md(d),
                  "## A rule against its alternative", rule_vs_alternative(d)]
    parts += ["## Acceptance criteria", acceptance_md(d)]
    return "\n\n".join(parts)


def full_report(seeds: Sequence[int], sweep: Optional[Sequence[int]] = None, quick: bool = False,
                jobs: int = 1) -> str:
    return render(collect(seeds, sweep, quick, jobs))
