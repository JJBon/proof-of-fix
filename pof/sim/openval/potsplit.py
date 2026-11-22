"""A funding variant as a hypothesis (proof-of-fix#236, owner 2026-11-15): no per-issue bounty. Funders pay into the
repository's pot per window; each accepted fix earns its solver one unit of reputation, and at the window's end the pot
is split in proportion to the units earned in the window that still stand (a reversed fix earns nothing).

This is NOT the network simulation: it is an expected-value model on #160's measured pass rates, with a small Monte
Carlo for the spread of an honest solver's income. It differs from the merit pool of #186 (`pof/sim/cyclepool.py`,
docs/paper/results.md 5.5): there the judges split the pool by each fix's merit and overclaims are challenged; here
nobody scores merit, an accepted fix is a unit (or, the alternative, a weight the funders set per issue).

Compared with per-issue bounties at equal total funding and with no solver's deposit (the primary case), for one seated family, a number of honest solvers and a
kind of bad fix. ASSUMED: the rival solvers' find rate, the contenders' (1 in 2, as task 10.1), what an honest fix
costs to write (`EFFORT` of its bounty: the bounty stands for the issue's difficulty), that a bad fix costs nothing to
write, and that only issues the funders list can earn a unit (the farmer's row shows what happens otherwise).

    python3 -m pof.sim.openval.potsplit
"""

from __future__ import annotations

import math
import random
from statistics import mean, pstdev
from typing import Dict, List, Sequence, Tuple

from . import measured as M
from .params import WORLD

ISSUES = 1560  # funded issues a year (30 a week, report v3's world)
GOOD = 0.75  # the share of honest fixes that are good
BAD_PER_YEAR = 260  # an attacker's bad fixes (5 a week, as task 10.1)
CHECKS = 1.14  # a fix's seven checks at the floor fee (report measured-v3, section 8)
EFFORT = 0.5  # ASSUMED: an honest fix costs this share of its issue's bounty to write
FIND, RIVAL_FIND = 0.5, 0.25  # ASSUMED: a contender, and each rival solver, finds a failing test for a bad fix
SEARCH = 0.50  # ASSUMED: what one search costs
SEATS = [s for _, s in M.SEVEN]


def bounties(n: int = ISSUES, seed: int = 1) -> List[float]:
    rng = random.Random(seed)
    mu = math.log(WORLD.bounty_median)
    sigma = math.log(WORLD.bounty_p90 / WORLD.bounty_median) / 1.2815515655446004
    return [min(WORLD.bounty_max, rng.lognormvariate(mu, sigma)) for _ in range(n)]


def judge(seat: str, pool: str) -> Tuple[float, float, float]:
    """(share of good fixes the seat passes, share of bad ones it passes, share of those passes another measured
    model failed: the ones a contender can flag)."""
    t = M.table()
    passed = [c for c in t[pool] if c[seat]]
    flagged = mean(any(not c[s] for s in SEATS if s != seat) for c in passed) if passed else 0.0
    return mean(c[seat] for c in t["good"]), mean(c[seat] for c in t[pool]), flagged


def stands(seat: str, pool: str, solvers: int, rival_find: float = RIVAL_FIND) -> float:
    """The chance a bad fix is passed and never reversed: no contender and no rival solver finds a test."""
    _, pb, flagged = judge(seat, pool)
    return pb * (1 - FIND * flagged) * (1 - rival_find) ** solvers


def compare(seat: str, pool: str, solvers: int, deposit: float = 0.0, weights: str = "equal",
            rival_find: float = RIVAL_FIND) -> Dict[str, float]:
    b = bounties()
    fund, bbar = sum(b), mean(b)
    pg, pb0, _ = judge(seat, pool)
    s_bad = stands(seat, pool, solvers, rival_find)
    # no deposit (the primary case; owner, 2026-11-15), so nothing of the solver's pays a disputer. With the pot, a
    # reversed fix's unit goes to whoever reversed it, so every passed fix yields one unit to somebody
    honest_units = ISSUES * (GOOD * pg + (1 - GOOD) * pb0)
    out: Dict[str, float] = {}
    # per-issue bounties with a deposit: a bad fix wins the bounty when it stands, and loses the deposit otherwise
    out["bounty_bad"] = BAD_PER_YEAR * (s_bad * bbar - (1 - s_bad) * deposit * bbar - CHECKS)
    out["bounty_honest"] = BAD_PER_YEAR * ((GOOD * pg + (1 - GOOD) * s_bad) * bbar
                                           - (1 - GOOD * pg - (1 - GOOD) * s_bad) * deposit * bbar
                                           - EFFORT * bbar - CHECKS)
    # the pot: a unit is worth the pot over every standing unit, the attacker's included
    unit = fund / (honest_units + BAD_PER_YEAR * pb0)
    out["unit"] = unit
    out["pot_bad"] = BAD_PER_YEAR * (s_bad * unit - CHECKS)
    out["pot_bad_taken"] = BAD_PER_YEAR * s_bad * unit  # every dollar of it from the other solvers' shares
    out["pot_honest"] = BAD_PER_YEAR * ((GOOD * pg + (1 - GOOD) * s_bad) * unit - EFFORT * bbar - CHECKS)
    # the farmer of trivial fixes: good fixes to the cheapest fifth of the listed issues only
    cheap = sorted(b)[:len(b) // 5]
    out["bounty_farmer"] = len(cheap) * (pg * mean(cheap) - (1 - pg) * deposit * mean(cheap) - EFFORT * mean(cheap)
                                         - CHECKS)
    out["pot_farmer"] = len(cheap) * (pg * unit - EFFORT * mean(cheap) - CHECKS)
    # ...and the same farmer filing its own trivial issues, if anyone may file one (as #186's farmer did)
    out["pot_self_filed"] = BAD_PER_YEAR * (fund / (honest_units + BAD_PER_YEAR * pg)) * pg - BAD_PER_YEAR * CHECKS
    # a Sybil solver: the split is linear in units, so n names earn what one does
    out["sybil"] = 0.0
    # hard issues: with equal units an honest fix pays pg x unit - effort; issues dearer than that are not worth it
    limit = pg * unit / EFFORT
    out["neglected_pct"] = 100 * mean(x > limit for x in b) if weights == "equal" else 0.0
    out["neglected_funding_pct"] = 100 * sum(x for x in b if x > limit) / fund if weights == "equal" else 0.0
    # what a rival earns per search of a passed fix (a bad one with chance `share_bad`)
    _, pb, _ = judge(seat, pool)
    share_bad = (1 - GOOD) * pb / (GOOD * pg + (1 - GOOD) * pb)
    out["search_bounty"] = share_bad * rival_find * (deposit + 0.10) * bbar - SEARCH  # 1,000 of the bounty, and D22
    out["search_pot"] = share_bad * rival_find * unit - SEARCH  # the reversed fix's unit
    # code health per 100 funded issues (the E2 measure; equal weights leave the neglected issues unfixed)
    take = 1 - out["neglected_pct"] / 100
    for name, t in (("bounty", 1.0), ("pot", take)):
        out[f"{name}_fixed"] = 100 * t * GOOD * pg
        out[f"{name}_wrong"] = 100 * t * (1 - GOOD) * s_bad
        out[f"{name}_unfixed"] = 100 - out[f"{name}_fixed"] - out[f"{name}_wrong"]
    return out


def spread(seat: str, pool: str, solvers: int, windows: int = 400, per_window: int = 390) -> Tuple[float, float]:
    """The spread (standard deviation over the mean) of one honest solver's income in a 13-week window, with
    per-issue bounties and with the pot: Monte Carlo over which issues it takes and which of its fixes stand."""
    if solvers < 1:
        return float("nan"), float("nan")
    pg, _, _ = judge(seat, pool)
    p = GOOD * pg + (1 - GOOD) * stands(seat, pool, solvers)
    rng = random.Random(7)
    by_bounty, by_pot = [], []
    for w in range(windows):
        b = bounties(per_window, seed=1000 + w)
        mine, units, total = 0.0, 0, 0
        for x in b:
            ok = rng.random() < p
            total += ok
            if rng.randrange(solvers) == 0:
                mine += x * ok
                units += ok
        by_bounty.append(mine)
        by_pot.append(sum(b) * units / max(1, total))
    cv = lambda xs: pstdev(xs) / mean(xs) if mean(xs) else float("nan")  # noqa: E731
    return cv(by_bounty), cv(by_pot)


def threshold(seat: str, pool: str, q: float, key: str, below: str = "") -> str:
    """The fewest rival solvers (0-40) at which the bad-fix solver's return `key` is at most zero, or at most a tenth
    of its honest twin's `below`."""
    for n in range(0, 41):
        r = compare(seat, pool, n, rival_find=q)
        if r[key] <= (0.1 * r[below] if below else 0.0):
            return str(n)
    return "more than 40"


def threshold_table() -> str:
    names = {"hidden": "the tests fail them", "pbw": "pass the tests, wrong"}
    head = ["Bad fixes", "Seated", "Each rival finds a test", "Bounties, no deposit: rivals needed for the bad-fix "
            "solver to earn nothing", "The pot: rivals needed for it to earn nothing", "The pot: rivals needed for "
            "it to earn under a tenth of an honest solver"]
    lines = [[names[pool], M.NAMES[seat], f"{100 * q:.0f} %", threshold(seat, pool, q, "bounty_bad"),
              threshold(seat, pool, q, "pot_bad"), threshold(seat, pool, q, "pot_bad", "pot_honest")]
             for pool in ("hidden", "pbw") for seat in ("anthropic", "openai") for q in (0.10, 0.25, 0.50)]
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(x) + " |" for x in lines])


def rows(solvers: Sequence[int] = (1, 3, 10)) -> List[Tuple[str, str, int, Dict[str, float]]]:
    out = []
    for pool in ("hidden", "pbw"):
        for seat in ("anthropic", "openai"):
            for n in solvers:
                r = compare(seat, pool, n)
                r["cv_bounty"], r["cv_pot"] = spread(seat, pool, n)
                out.append((pool, seat, n, r))
    return out


def table() -> str:
    names = {"hidden": "the tests fail them", "pbw": "pass the tests, wrong"}
    head = ["Bad fixes", "Seated", "Honest solvers", "A bad fix stands", "Bad-fix solver, bounties, no deposit "
            "($ a year)", "…the pot, no deposit", "…bounties, deposit 2,500", "…bounties, deposit 4,000",
            "Honest twin, bounties, no deposit", "…the pot", "Farmer of trivial fixes − its bounty return",
            "Farmer filing its own issues, the pot", "Issues not worth an honest fix (equal units)",
            "…their share of funding", "A rival's return per search: bounties", "…the pot",
            "Fixed / wrong / unfixed per 100: bounties", "…the pot", "Income spread: bounties", "…the pot"]
    lines = []
    for pool, seat, n, r in rows():
        lines.append([names[pool], M.NAMES[seat], str(n), f"{100 * stands(seat, pool, n):.1f} %",
                      f"{r['bounty_bad']:+,.0f}", f"{r['pot_bad']:+,.0f}",
                      f"{compare(seat, pool, n, 0.25)['bounty_bad']:+,.0f}",
                      f"{compare(seat, pool, n, 0.40)['bounty_bad']:+,.0f}", f"{r['bounty_honest']:+,.0f}",
                      f"{r['pot_honest']:+,.0f}", f"{r['pot_farmer'] - r['bounty_farmer']:+,.0f}",
                      f"{r['pot_self_filed']:+,.0f}", f"{r['neglected_pct']:.0f} %",
                      f"{r['neglected_funding_pct']:.0f} %", f"${r['search_bounty']:+.2f}", f"${r['search_pot']:+.2f}",
                      f"{r['bounty_fixed']:.0f} / {r['bounty_wrong']:.1f} / {r['bounty_unfixed']:.0f}",
                      f"{r['pot_fixed']:.0f} / {r['pot_wrong']:.1f} / {r['pot_unfixed']:.0f}",
                      f"{r['cv_bounty']:.2f}", f"{r['cv_pot']:.2f}"])
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(x) + " |" for x in lines])


def main() -> int:
    print("### The pot split by standing fixes, beside per-issue bounties (expected values, no simulation)\n")
    print(table() + "\n")
    print("### How many rival solvers it takes, with no deposit (expected values, no simulation)\n")
    print(threshold_table() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
