"""The tables of reports/open-validators-measured-v5.md, from `nodeposit`'s raw results (one JSON file a table):

    python3 -m pof.sim.openval.nodeposit --render <folder>
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Dict, List, Sequence, Tuple

from . import actors as A
from . import nodeposit as N

Res = Dict[str, object]


def _load(folder: str, name: str):
    path = Path(folder, f"{name}.json")
    return json.loads(path.read_text()) if path.exists() else None


def _rows(data) -> Dict[Tuple[str, ...], Res]:
    return {tuple(k.split("|")): r for k, r in data}


def _m(r: Res, k: str) -> float:
    xs = [x for x in r.get(k, []) if x == x]  # type: ignore[union-attr]
    return mean(xs) if xs else float("nan")


def _pm(r: Res, k: str, nd: int = 0, scale: float = 1.0) -> str:
    xs = [scale * x for x in r.get(k, []) if x == x]  # type: ignore[union-attr]
    if not xs:
        return "–"
    return f"{mean(xs):,.{nd}f} ± {2 * A._se(xs):,.{nd}f}"


def wins(r: Res) -> bool:
    return r["diff"] - 2 * r["se"] > 0  # type: ignore[operator]


def cell(r: Res) -> str:
    s = f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}"  # type: ignore[str-format]
    return f"**{s}**" if wins(r) else s


def _table(head: Sequence[str], lines: Sequence[Sequence[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(x) + " |" for x in lines])


SEAT = dict(N.SEATS)
POOL = dict(N.POOLS)
CONDS = [(s, n) for s, _ in N.SEATS for n in N.SOLVERS]
COND_HEAD = [f"{SEAT[s]}, {n} solver{'s' if n > 1 else ''}" for s, n in CONDS]


def cost_table(data) -> str:
    head = ["Seated", "Bad fixes", "Checks paid a submission", "Break-even service fee a check", "Market fee (floor)",
            "Judges' cost a submission (fee + usage $0.13)", "Charged a submission now"]
    lines = [[SEAT[seat], POOL[pool], f"{r['checks_per_sub']:.2f}", f"${r['break_even']:.3f}", f"${r['fee']:.3f}",
              f"${r['cost']:.2f}", f"${r['charged']:.2f}"] for pool, seat, r in data["rows"]]
    return _table(head, lines) + f"\n\n`JUDGE_FEE` = **${data['fee']:.2f}** a submission (the mean of the four), plus " \
                                 "the attempt fee of $0.50 as before."


def summary_table(grid) -> str:
    """Per combination and condition: does every attacker (both kinds of bad fix) earn at or below its twin?"""
    rows = _rows(grid)
    head = ["Combination"] + COND_HEAD
    lines = []
    for combo, _ in N.COMBOS:
        out = [combo]
        for seat, n in CONDS:
            bad = []
            for (c, s, pool, nn, k, label), r in rows.items():
                if c == combo and s == seat and int(nn) == n and not label and wins(r):
                    bad.append((r["diff"], k, pool))
            if not bad:
                out.append("holds")
            else:
                ks = sorted({k for _, k, _ in bad}, key=list(N.ATTACKERS).index)
                out.append(f"no: {', '.join(ks)} (up to {max(d for d, _, _ in bad):+,.0f})")
        lines.append(out)
    return _table(head, lines)


def combo_table(grid, combo: str, label: str = "") -> str:
    rows = _rows(grid)
    head = ["Attacker", "Bad fixes"] + COND_HEAD
    lines = []
    for k in N.ATTACKERS:
        for pool, what in N.POOLS:
            cells = []
            for seat, n in CONDS:
                r = rows.get((combo, seat, pool, str(n), k, label))
                cells.append(cell(r) if r else "")
            if any(cells):
                lines.append([N.ATTACKERS[k], what if k not in ("F", "SF", "I") else "(good fixes)"] + cells)
    return _table(head, lines)


def _health(r: Res) -> Tuple[float, float, float, bool]:
    stays = r["diff"] > 0  # type: ignore[operator]
    pre = "" if stays else "twin_"
    n = _m(r, pre + "h_n") + _m(r, "a_n")
    fixed = _m(r, pre + "h_fixed") + (_m(r, "a_fixed") if stays else 0.0)
    wrong = _m(r, pre + "h_wrong") + (_m(r, "a_wrong") if stays else 0.0)
    return 100 * fixed / n, 100 * wrong / n, 100 * (n - fixed - wrong) / n, stays


def health_table(grid, label: str = "") -> str:
    """E2 (report v4, section 9): per 100 funded issues, the solver of bad fixes (one identity) present while it
    profits; when it does not, its issues are funded and left unfixed."""
    rows = _rows(grid)
    head = ["Combination", "Seated"] + [f"{n} solver{'s' if n > 1 else ''}: {POOL[p]}" for p, _ in N.POOLS
                                         for n in N.SOLVERS]
    lines = []
    for combo, _ in N.COMBOS:
        for seat, _ in N.SEATS:
            out = [combo, SEAT[seat]]
            for pool, _ in N.POOLS:
                for n in N.SOLVERS:
                    r = rows.get((combo, seat, pool, str(n), "B", label))
                    if r is None:
                        out.append("")
                        continue
                    f, w, u, stays = _health(r)
                    out.append(f"{f:.1f} / {w:.1f} / {u:.1f}" + ("" if stays else " (left)"))
            lines.append(out)
    return _table(head, lines)


def search_table(grid) -> str:
    """What an active honest solver's search of a pass earns (gross of its cost), from the solver-of-bad-fixes rows:
    its share of the disputers' rewards (bounties: 1,000 of the bounty; the pot: the reversed fix's weight), by its
    share of the reversals, over every pass it searched."""
    rows = _rows(grid)
    head = ["Combination", "Bad fixes"] + COND_HEAD
    lines = []
    for combo, _ in N.COMBOS:
        if combo not in ("none", "P"):
            continue
        for pool, what in N.POOLS:
            out = [combo, what]
            for seat, n in CONDS:
                r = rows.get((combo, seat, pool, str(n), "B", ""))
                if r is None:
                    out.append("")
                    continue
                vals = []
                for i in range(len(r["diffs"])):  # type: ignore[arg-type]
                    rev, rt = r["ev_reversed"][i], r["rival_tests"][i]  # type: ignore[index]
                    pot = r["disputers_pot"][i] if combo == "P" else r["world_reward"][i]  # type: ignore[index]
                    vals.append((pot * rt / rev if rev else 0.0) / max(1.0, r["passes"][i] * n))  # type: ignore
                out.append(f"${mean(vals):.2f}")
            lines.append(out)
    return _table(head, lines)


def fee_table(grid) -> str:
    """The fee a submission would need for the solver of bad fixes and the retrier to earn nothing (no cap, no pot):
    with the judges' fee its return falls by the fee's rise on every submission, so the zero is linear."""
    rows = _rows(grid)
    head = ["Attacker", "Bad fixes"] + COND_HEAD
    lines = []
    for k in ("B", "S", "T"):
        for pool, what in N.POOLS:
            out = [N.ATTACKERS[k], what]
            for seat, n in CONDS:
                r = rows.get(("F", seat, pool, str(n), k, ""))
                r0 = rows.get(("none", seat, pool, str(n), k, ""))
                if r is None or r0 is None:
                    out.append("")
                    continue
                sub = _m(r, "submitted")
                out.append(f"{cell(r0)} → {cell(r)}; zero at ${N.JUDGE_FEE + r['diff'] / max(1.0, sub):,.2f}")
            lines.append(out)
    return _table(head, lines)


def newcomer_table(data, ns: Sequence[int] = N.SOLVERS) -> str:
    rows = _rows(data)
    head = ["Combination", "Seated", "Solvers", "An honest solver's year with no cap ($)",
            "Newcomer: cost of the cap ($ a year)", "…runs in which it may claim a median bounty ($86)",
            "…week it first may", "…week it first may claim $184 (p90)", "Issues it wanted, turned away",
            "…their share of the value", "Its resets a year", "Established (5,000): cost of the cap ($ a year)",
            "…its resets a year"]
    lines = []
    for combo, _ in N.COMBOS:
        for seat, _ in N.SEATS:
            for n in ns:
                r = rows.get((combo, seat, "hidden", str(n), "N", ""))
                if r is None:
                    continue
                e = rows.get((combo, seat, "hidden", str(n), "E", ""))
                rep = "R" in combo.split("+")
                lines.append([combo, SEAT[seat], str(n), _pm(r, "twin"), cell(r) if rep else "n/a",
                              _pm(r, "reached_median", 0) + " %" if rep else "n/a",
                              _pm(r, "week_median", 1) if rep else "n/a", _pm(r, "week_p90", 1) if rep else "n/a",
                              f"{100 * _m(r, 'turned') / max(1.0, _m(r, 'wanted')):.1f} %" if rep else "n/a",
                              f"{100 * _m(r, 'turned_value') / max(1.0, _m(r, 'wanted_value')):.1f} %" if rep
                              else "n/a", _pm(r, "resets", 1) if rep else "n/a",
                              cell(e) if e else "n/a", _pm(e, "resets", 1) if e else "n/a"])
    return _table(head, lines)


def newcomer_table_minus(data) -> str:
    rows = _rows(data)
    head = ["Seated", "Solvers", "Newcomer: cost of the cap ($ a year)", "…week it first may claim $86",
            "…issues it wanted, turned away", "…their share of the value", "Established (5,000): cost"]
    lines = []
    for seat, name in N.SEATS:
        for n in N.SOLVERS:
            r, e = rows[("R+F", seat, "hidden", str(n), "N", "minus")], rows[("R+F", seat, "hidden", str(n), "E", "minus")]
            lines.append([name, str(n), cell(r), _pm(r, "week_median", 1),
                          f"{100 * _m(r, 'turned') / max(1.0, _m(r, 'wanted')):.1f} %",
                          f"{100 * _m(r, 'turned_value') / max(1.0, _m(r, 'wanted_value')):.1f} %", cell(e)])
    return _table(head, lines)


def rep_table(data) -> str:
    rows = _rows(data)
    head = ["Rule", "Seated", "Bad fixes, one identity", "Free identities", "Retrier", "Long con",
            "Reputation sale", "Newcomer: cost ($ a year)", "…week it may claim $86", "…issues turned away",
            "Established: cost"]
    lines = []
    for label, _ in N.REP_SWEEP:
        for seat, _ in N.SEATS:
            g = lambda k: rows.get(("R", seat, "hidden", "3", k, label))  # noqa: E731
            nc = g("N")
            lines.append([label, SEAT[seat]] + [cell(g(k)) for k in ("B", "S", "T", "L", "RS")]
                         + [cell(nc), _pm(nc, "week_median", 1),
                            f"{100 * _m(nc, 'turned') / max(1.0, _m(nc, 'wanted')):.1f} %", cell(g("E"))])
    return _table(head, lines)


def pot_table(data) -> str:
    rows = _rows(data)
    head = ["Split", "Seated", "Bad fixes, one identity ($ a year)", "Farmer of the cheapest fifth − its twin",
            "Farmer filing its own issues − its twin", "An honest solver's year", "Issues not worth an honest fix",
            "…their share of the funding", "Fixed / wrong / unfixed per 100 (solver of bad fixes present while it "
            "profits)", "A unit of weight ($)"]
    lines = []
    for label, pot, _ in N.POT_SWEEP:
        for seat, _ in N.SEATS:
            g = lambda k: rows.get(("P", seat, "hidden", "3", k, label))  # noqa: E731
            b = g("B")
            f, w, u, stays = _health(b)
            n = _m(b, "h_n")
            lines.append([label, SEAT[seat], cell(b), cell(g("F")), cell(g("SF")), _pm(g("N"), "twin"),
                          f"{100 * _m(b, 'neglected') / n:.1f} %", f"{_m(b, 'neglected_funding'):.1f} %",
                          f"{f:.1f} / {w:.1f} / {u:.1f}" + ("" if stays else " (left)"), _pm(b, "unit", 1)])
    return _table(head, lines)


def inflate_table(data) -> str:
    rows = _rows(data)
    head = ["Correlation (assumed)", "Seated"] + [f"Inflating costs ${c:g} a fix" for c in N.INFLATE_COSTS]
    lines = []
    for label, pot, _ in N.POT_SWEEP:
        if pot != "impact":
            continue
        for seat, _ in N.SEATS:
            lines.append([label, SEAT[seat]] + [cell(rows[("P", seat, "hidden", "3", "I",
                                                             f"{label}; inflating costs ${c:g} a fix")])
                                                for c in N.INFLATE_COSTS])
    return _table(head, lines)


def sens_table(data) -> str:
    rows = _rows(data)
    head = ["Combination", "Find rate (assumed)", "Attacker", "Bad fixes"] + COND_HEAD
    lines = []
    for combo in ("none", "R+F", "R+P+F"):
        for q in N.SENS_FIND:
            label = f"find {100 * q:.0f} %"
            for k in N.ATTACKERS:
                for pool, what in N.POOLS:
                    cells = [rows.get((combo, seat, pool, str(n), k, label)) for seat, n in CONDS]
                    if any(cells):
                        lines.append([combo, f"{100 * q:.0f} %", N.ATTACKERS[k], what]
                                     + [cell(c) if c else "" for c in cells])
    return _table(head, lines)


def deposit_table(data, grid) -> str:
    rows, g = _rows(data), _rows(grid)  # `grid`: the "minus" rows
    head = ["Attacker", "Bad fixes", "Seated", "No deposit (grid)"] + [f"Deposit {d:,}" for d in N.HOLE_DEPOSITS]
    lines = []
    for k in ("B", "S", "T", "Tf", "L", "RS"):
        for pool, what in N.POOLS:
            for seat, name in N.SEATS:
                lines.append([N.ATTACKERS[k], what, name, cell(g[("R+F", seat, pool, "1", k, "minus")])]
                             + [cell(rows[("R+F", seat, pool, "1", k, f"deposit {d:,}")]) for d in N.HOLE_DEPOSITS])
    return _table(head, lines)


def render(folder: str) -> str:
    out: List[str] = []
    cost = _load(folder, "cost")
    if cost:
        out += ["### The judges' cost, and `JUDGE_FEE`", "", cost_table(cost), ""]
    grid = _load(folder, "grid")
    if grid:
        out += ["### Does every attacker earn at or below its twin? (both kinds of bad fix; 25 % find rate)", "",
                summary_table(grid), ""]
        for combo, _ in N.COMBOS:
            out += [f"### Combination {combo}: each attacker's return minus its twin's ($ a year, ± 2 SE; bold: wins)",
                    "", combo_table(grid, combo), ""]
        out += ["### Code health (E2): correctly fixed / wrongly marked fixed / left unfixed, per 100 funded issues",
                "", health_table(grid), ""]
        out += ["### The judges' fee against the solver of bad fixes and the retrier (no cap, no pot)", "",
                fee_table(grid), ""]
        out += ["### What an active honest solver earns a search of a pass, gross (it costs $0.50, assumed)", "",
                search_table(grid), ""]
    nc = _load(folder, "newcomer")
    if nc:
        out += ["### The honest solver: its year, and what the cap costs a newcomer and an established solver", "",
                newcomer_table(nc), ""]
    rep = _load(folder, "rep")
    if rep:
        out += ["### The reputation rule's numbers swept (alone; Opus 5.5 or GPT-6.1; 3 solvers; the tests fail them)",
                "", rep_table(rep), ""]
    pot = _load(folder, "pot")
    if pot:
        out += ["### The pot alone: equal units and impact weights (3 solvers; the tests fail them)", "",
                pot_table(pot), "", "### The inflater against its twin, by the assumed correlation and cost", "",
                inflate_table(pot), ""]
    sens = _load(folder, "sens")
    if sens:
        out += ["### The find rate: 10 % and 50 % in place of 25 %", "", sens_table(sens), ""]
    mn = _load(folder, "minus")
    if mn:
        out += ["### Post hoc: the cap with a reversal taking 2 x its bounty off, and the judges' fee", "",
                combo_table(mn, "R+F", "minus"), "", newcomer_table_minus(mn), ""]
    dep = _load(folder, "deposit")
    if dep and mn:
        out += ["### Post hoc: the deposit that would close the holes of the cap and the fee, one active solver", "",
                deposit_table(dep, mn), ""]
    return "\n".join(out)
