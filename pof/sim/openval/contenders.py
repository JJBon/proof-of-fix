"""Contenders' disputes and the attackers, on measured judges (proof-of-fix#236, hypothesis H7).

`measured` showed that a panel of the best family beats any mix, and that a second panel repeats the first. Here:

- **disputes backed by evidence** (`World.evidence_find`): after a passing verdict, anyone running a model that failed
  the fix (a contender: a family without a seat, or a seated one outvoted) looks for a failing test. Found evidence
  reverses the verdict without a second panel. Which fixes a contender flags is measured (#160's verdicts); how often
  a flagged bad fix yields a failing test is assumed and swept;
- **the cover** (`cover`): exact counts from #160's verdicts, no simulation: of the bad fixes a panel passes, how
  many some contender failed, and how many good fixes contenders would search in vain;
- **the attackers** of report v3 against their honest twins with measured judges, and one v3 didn't have: a solver
  that submits bad fixes and colludes with nobody.

    python3 -m pof.sim.openval.contenders [--seeds 40] [--jobs 4] [--quick]

prints reports/open-validators-measured-v2.md's tables. No model call.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import measured as M
from . import panels as D
from . import report as R
from . import scores as SC
from .params import PARAMS, WEEK, WORLD, Params, World

ALL_SEATS = tuple(M.NAMES)
NOCAP = replace(PARAMS, FAMILY_CAP=False)
BAD_SHARE = 1 - WORLD.good_share

# ---------- the cover: exact, from #160's verdicts ----------

PANELS: Tuple[Tuple[str, Callable[[Dict[str, bool]], bool], Tuple[str, ...]], ...] = (
    ("Opus 5.5 alone", lambda c: c["anthropic"], ("anthropic",)),
    ("GPT-6.1 alone", lambda c: c["openai"], ("openai",)),
    ("Opus 5.5 and GPT-6.1, both must pass", lambda c: c["anthropic"] and c["openai"], ("anthropic", "openai")),
    ("Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority",
     lambda c: c["anthropic"] + c["openai"] + c["google"] >= 2, ("anthropic", "openai", "google")),
)
CONTENDERS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("every other seat", ()),  # filled per panel: all nine less the panel's
    ("GPT-6.1 only", ("openai",)),
    ("Opus 5.5 only", ("anthropic",)),
    ("the six open-weight seats", ("deepseek", "qwen", "mistral", "nvidia", "google-gemma", "openai-oss")),
)


def cover(passes: Callable[[Dict[str, bool]], bool], contenders: Sequence[str], pool: str) -> Dict[str, float]:
    """Counts over #160's cases: bad fixes passed, those some contender failed, good fixes passed, those some
    contender failed (searched in vain), and the searches (one per contender that failed a passed fix)."""
    t = M.table()
    bad = [c for c in t[pool] if passes(c)]
    good = [c for c in t["good"] if passes(c)]
    flag = lambda c: sum(1 for s in contenders if not c[s])  # noqa: E731
    return {"bad_n": len(t[pool]), "bad_passed": len(bad), "bad_flagged": sum(1 for c in bad if flag(c)),
            "good_n": len(t["good"]), "good_passed": len(good), "good_flagged": sum(1 for c in good if flag(c)),
            "searches_bad": sum(flag(c) for c in bad), "searches_good": sum(flag(c) for c in good)}


def per_100(c: Dict[str, float], find: float, false: float = 0.0) -> Tuple[float, float, float]:
    """With `BAD_SHARE` of fixes bad: (bad fixes merged per 100 paid, share of good fixes not paid, fixes a contender
    searches per verdict it reverses), if flagged bad fixes yield evidence with `find`."""
    bad = BAD_SHARE * (c["bad_passed"] - find * c["bad_flagged"]) / c["bad_n"]
    good = (1 - BAD_SHARE) * (c["good_passed"] - false * c["good_flagged"]) / c["good_n"]
    tried = BAD_SHARE * c["bad_flagged"] / c["bad_n"] + (1 - BAD_SHARE) * c["good_flagged"] / c["good_n"]
    won = BAD_SHARE * find * c["bad_flagged"] / c["bad_n"]
    return (100 * bad / (bad + good), 100 * (1 - good / (1 - BAD_SHARE)), tried / won if won else float("nan"))


def cover_table() -> str:
    head = ["Bad fixes", "Panel", "Contenders", "Bad fixes passed", "…that a contender failed",
            "Good fixes passed", "…that a contender failed", "Bad merged per 100 paid: no disputes",
            "evidence found 1 time in 4", "1 in 2", "3 in 4", "Fixes searched per reversal (1 in 2)"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for pool, what in (("hidden", "the tests fail them"), ("pbw", "pass the tests, wrong")):
        for pname, passes, seats in PANELS:
            for cname, who in CONTENDERS:
                who = who or tuple(s for s in ALL_SEATS if s not in seats)
                if set(who) <= set(seats):
                    continue
                c = cover(passes, who, pool)
                out.append(
                    f"| {what} | {pname} | {cname} | {c['bad_passed']} of {c['bad_n']} | {c['bad_flagged']} | "
                    f"{c['good_passed']} of {c['good_n']} | {c['good_flagged']} | {per_100(c, 0)[0]:.1f} | "
                    f"{per_100(c, .25)[0]:.1f} | {per_100(c, .5)[0]:.1f} | {per_100(c, .75)[0]:.1f} | "
                    f"{per_100(c, .5)[2]:.1f} |")
    return "\n".join(out)


# ---------- the network with disputes ----------

def with_evidence(w: World, find: float, by: Sequence[str] = ALL_SEATS, false: float = 0.0) -> World:
    return replace(w, evidence_find=find, evidence_false=false, evidence_by=tuple(by))


def metrics(net) -> Dict[str, float]:
    m = M.metrics(net)
    st = net.stats
    m["evidence_reversed"] = st["evidence_reversed"]
    m["evidence_wrong"] = st["evidence_wrong"]
    m["evidence_tried"] = st["evidence_tried"]
    m["tried_per_reversal"] = st["evidence_tried"] / st["evidence_reversed"] if st["evidence_reversed"] else float("nan")
    return m


def dispute_rows() -> List[Tuple[str, object, World, Params]]:
    """(label, mode, World, Params): mode "pay" = v3's scores, ("rank", top, bar) = the rank on known answers."""
    rows: List[Tuple[str, object, World, Params]] = []
    top1 = ("rank", 1, None)
    for pool, what in (("hidden", "the tests fail them"), ("pbw", "pass the tests, wrong")):
        w = M.world(M.SEVEN, pool)
        pre = f"bad = {what}: "
        rows += [(pre + "**v3 as designed**, no disputes", "pay", w, PARAMS)]
        rows += [(pre + f"v3 as designed, evidence found {lab}", "pay", with_evidence(w, q), PARAMS)
                 for q, lab in ((.25, "1 time in 4"), (.5, "1 in 2"), (.75, "3 in 4"))]
        rows += [(pre + "v3's scores, no family cap, evidence found 1 in 2", "pay", with_evidence(w, .5), NOCAP),
                 (pre + "**top family alone**, no disputes", top1, w, NOCAP)]
        rows += [(pre + f"top family alone, evidence found {lab}", top1, with_evidence(w, q), NOCAP)
                 for q, lab in ((.25, "1 time in 4"), (.5, "1 in 2"), (.75, "3 in 4"))]
        other = "openai" if pool == "hidden" else "anthropic"
        rows += [(pre + f"top family alone, evidence 1 in 2, the only contender {M.NAMES[other]}", top1,
                  with_evidence(w, .5, (other,)), NOCAP),
                 (pre + "top family alone, evidence 1 in 2, wrong evidence accepted 1 time in 20", top1,
                  with_evidence(w, .5, false=.05), NOCAP)]
    return rows


def _run_dispute(job) -> Dict[str, float]:
    i, seed = job
    _, mode, w, p = dispute_rows()[i]
    if isinstance(mode, tuple):
        return metrics(M.run_variant(seed, w, p, mode[1], mode[2]))
    return metrics(SC.run_mode(seed, mode, w, p))


def dispute_table(data) -> str:
    head = ["Network", "Bad fixes merged per 100 paid", "Good fixes rejected", "Fixes paid a year",
            "Verdicts reversed by evidence a year", "Fixes searched per reversal", "Submissions that waited"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for label, _, m in data:
        out.append(f"| {label} | {M._ms(m['bad_per_100'], 1)} | {M._ms(m['good_failed_pct'], 1, ' %')} | "
                   f"{M._ms(m['paid_n'], 0)} | {M._ms(m['evidence_reversed'], 0)} | "
                   f"{M._ms(m['tried_per_reversal'], 1)} | {M._ms(m['waited_pct'], 1, ' %')} |")
    return "\n".join(out)


# ---------- the attackers ----------

class BadFixSolver(A.Actor):
    """A solver that submits `bad_week` bad fixes a week and colludes with nobody: it is paid when the honest judges
    pass one. It pays the attempt fee and its checks; what a bad fix costs to produce is not counted (the table
    gives the return per attempt to set against it). Its twin submits nothing."""
    name = "bad-fix solver"
    party = "bad-fix solver"

    def __init__(self, honest: bool = False, w: World = WORLD, scores: bool = False, top: Optional[int] = None,
                 bad_week: float = 5.0):
        super().__init__(honest)
        self.w, self.scores, self.top, self.bad_week = w, scores, top, bad_week

    def world(self) -> World:
        return self.w

    def setup(self, net) -> None:
        if self.scores:
            SC.install(net)
        if self.top:
            net.family_ok = M.known_answer_rank(net.w, self.top, None)
        if self.honest:
            return
        rng = random.Random(D.h(net.seed, D.T_GRIND, 7))
        t, times = 0.0, []
        while True:
            t += rng.expovariate(self.bad_week / WEEK)
            if t > net.w.horizon_h:
                break
            times.append(t)
        for t, b in zip(times, A._bounties(net, rng, len(times), net.w.bounty_max)):
            net.submit(t, b, False, "bad-fix-solver", self.party)


def on_measured(make: Callable[[bool], A.Actor], pool: str, seats=M.FOUR) -> Callable[[bool], A.Actor]:
    """The same actor, its world's judges replaced by #160's (its families must be `seats`' families)."""
    def made(h: bool) -> A.Actor:
        a = make(h)
        base = a.world()
        assert set(base.families) == {f for f, _ in seats}, base.families
        a.world = lambda: replace(base, family_accuracy=(), family_blind=(), measured=pool, measured_seats=seats)
        return a
    return made


def _solver_metrics(net, a) -> Dict[str, float]:
    pa = net.parties.get(a.party)
    return {"submitted": pa.submitted if pa else 0, "bad_paid": pa.bad_paid if pa else 0,
            "evidence_reversed": net.stats["evidence_reversed"]}


def _herd_metrics(net, a) -> Dict[str, float]:
    return {**SC._herd_metrics(net, a), "herded": net.stats["herded"]}


def attacker_rows() -> List[Tuple[str, Callable[[bool], A.Actor], Optional[Params], str]]:
    """(label, make, Params, kind). The first block is report v3's design rows, each on its assumed judges and on
    #160's; then the herders; then the bad-fix solver."""
    rows: List[Tuple[str, Callable[[bool], A.Actor], Optional[Params], str]] = []
    for name, make, p, kind in R.ATTACKERS:
        if p is not None:
            continue  # the counterfactuals
        rows.append((f"{name}; assumed judges", make, None, kind))
        rows.append((f"{name}; **measured**, bad = the tests fail them", on_measured(make, "hidden"), None, kind))
    for pool in ("hidden",):
        w = M.world(M.FOUR, pool)
        for fam in ("openai", "open-weight"):
            seat = dict(M.FOUR)[fam]
            rows.append((f"Herders: four validators of `{fam}` ({M.NAMES[seat]}), receipts not detectable; "
                         "**measured**, v3's scores",
                         lambda h, fam=fam, w=w: SC.Herders(h, family=fam, detectable=False, w=w), None, "herd"))
    four_h, four_p = M.world(M.FOUR, "hidden"), M.world(M.FOUR, "pbw")
    seven_h, seven_p = M.world(M.SEVEN, "hidden"), M.world(M.SEVEN, "pbw")
    solver = [("assumed judges (report v3's score world), v3's scores", SC.SCORE_WORLD, True, None, None),
              ("**measured**, four families, v3 as designed, bad = the tests fail them", four_h, True, None, None),
              ("**measured**, four families, v3 as designed, bad = pass the tests, wrong", four_p, True, None, None),
              ("**measured**, top family alone, bad = the tests fail them", seven_h, False, 1, NOCAP),
              ("**measured**, top family alone, bad = pass the tests, wrong", seven_p, False, 1, NOCAP),
              ("**measured**, top family alone, evidence found 1 in 2, bad = the tests fail them",
               with_evidence(seven_h, .5), False, 1, NOCAP),
              ("**measured**, top family alone, evidence found 1 in 2, bad = pass the tests, wrong",
               with_evidence(seven_p, .5), False, 1, NOCAP)]
    for label, w, scores, top, p in solver:
        rows.append((f"Bad-fix solver (5 a week, no collusion); {label}",
                     lambda h, w=w, scores=scores, top=top: BadFixSolver(h, w, scores, top), p, "solver"))
    return rows


def _run_attacker(job) -> Dict[str, object]:
    i, seed = job
    _, make, p, kind = attacker_rows()[i]
    if kind == "solver":
        mt = _solver_metrics
    elif kind == "herd":
        mt = _herd_metrics
    else:
        mt = R._attack_metrics
    return A.against_twin(make, [seed], p=p, metrics=mt)


def _twin(chunk: List[Dict[str, object]]) -> Dict[str, object]:
    diffs = [r["diffs"][0] for r in chunk]
    out = {k: mean(r[k] for r in chunk) for k in chunk[0] if k not in ("diffs", "diff", "se", "loses")}
    out.update(diff=mean(diffs), se=A._se(diffs), diffs=diffs)
    return out


def _got(kind: str, r: Dict[str, object]) -> str:
    if kind == "solver":
        n = max(1.0, r["submitted"])
        return (f"{r['bad_paid']:.0f} bad fixes paid of {r['submitted']:.0f} ({100 * r['bad_paid'] / n:.0f} %); "
                f"${r['attacker'] / n:,.2f} a bad fix submitted")
    if kind == "herd":
        return (f"{r['herded']:.0f} votes herded of {r['counted']:.0f} counted; its family barred "
                f"{100 * r['barred']:.0f} % of the year (twin: {100 * r['twin_barred']:.0f} %)")
    return R._got(kind, r)


def attacker_table(data) -> str:
    out = ["| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | "
           "What it got |", "|---|---|---|---|---|---|"]
    for name, r, kind in data:
        out.append(f"| {name} | {r['diff']:+,.0f} ± {2 * r['se']:,.0f} | {R._verdict(r['diff'], r['se'])} | "
                   f"{r['attacker']:,.0f} | {r['twin']:,.0f} | {_got(kind, r)} |")
    return "\n".join(out)


def deposit_table() -> str:
    """The deposit a solver would have to lose on a rejected fix for a bad one not to pay, at the median bounty, and
    what the same deposit costs a solver of good fixes (exact, from #160's verdicts; attempt fee and checks aside)."""
    b = WORLD.bounty_median
    out = ["| Bad fixes | Panel | Disputes | A bad fix is paid | Deposit at which a bad fix stops paying | "
           "What that deposit costs a good fix, on average |", "|---|---|---|---|---|---|"]
    for pool, what in (("hidden", "the tests fail them"), ("pbw", "pass the tests, wrong")):
        for pname, passes, seats in PANELS:
            who = tuple(s for s in ALL_SEATS if s not in seats)
            c = cover(passes, who, pool)
            for find, lab in ((0.0, "none"), (0.5, "evidence found 1 in 2")):
                paid = (c["bad_passed"] - find * c["bad_flagged"]) / c["bad_n"]
                dep = paid * b / (1 - paid) if paid < 1 else float("inf")
                lost = 1 - c["good_passed"] / c["good_n"]
                out.append(f"| {what} | {pname} | {lab} | {100 * paid:.0f} % | ${dep:,.0f} | ${dep * lost:,.2f} |")
    return "\n".join(out)


# ---------- everything once ----------

def _map(fn, work, jobs: int):
    if jobs > 1:
        from multiprocessing import Pool
        with Pool(jobs) as pool:
            return pool.map(fn, work, chunksize=1)
    return [fn(j) for j in work]


def run_disputes(seeds: Sequence[int], jobs: int = 1, rows=None):
    rows = dispute_rows() if rows is None else rows
    idx = [i for i, r in enumerate(dispute_rows()) if r in rows]
    res = _map(_run_dispute, [(i, s) for i in idx for s in seeds], jobs)
    out = []
    for n, i in enumerate(idx):
        chunk = res[n * len(seeds):(n + 1) * len(seeds)]
        label, _, w, _ = dispute_rows()[i]
        out.append((label, w, {k: [r.get(k, float("nan")) for r in chunk] for k in chunk[0]}))
    return out


def run_attackers(seeds: Sequence[int], jobs: int = 1, pick: Optional[Sequence[int]] = None):
    rows = attacker_rows()
    idx = list(range(len(rows))) if pick is None else list(pick)
    res = _map(_run_attacker, [(i, s) for i in idx for s in seeds], jobs)
    return [(rows[i][0], _twin(res[n * len(seeds):(n + 1) * len(seeds)]), rows[i][3]) for n, i in enumerate(idx)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.contenders")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="4 seeds")
    a = ap.parse_args(argv)
    seeds = list(range(1, (4 if a.quick else a.seeds) + 1))
    print(f"Seeds 1-{seeds[-1]}; every ± is two standard errors of the mean.\n")
    print("### The cover (exact, from #160's verdicts; a quarter of fixes bad)\n")
    print(cover_table())
    print("\n### The network with disputes backed by evidence (seven families)\n")
    data = run_disputes(seeds, a.jobs)
    print(dispute_table(data))
    print("\n### Scores by v3's rule, with disputes\n")
    print(M.score_table([d for d in data if "v3 as designed" in d[0]]))
    print("\n### Each attacker against its honest twin\n")
    print(attacker_table(run_attackers(seeds, a.jobs)))
    print("\n### The deposit that stops a bad fix paying (median bounty $%.0f)\n" % WORLD.bounty_median)
    print(deposit_table())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
