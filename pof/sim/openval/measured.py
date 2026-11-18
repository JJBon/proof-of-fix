"""The open-validator network with measured judges (proof-of-fix#236, hypothesis H7).

The simulation's judges were assumed: right 90 % of the time (68-95 % by family), each call independent, plus a blind
spot per family. proof-of-fix#160 measured nine models on 228 real fixes. Here an honest judge's verdict is its
seat's recorded verdict on a real case:

- every submission is bound to one of #160's cases, drawn by the seed: a good fix from the 50 good ones, a bad fix
  from `World.measured`'s pool: "hidden" (the 100 fixes the hidden tests fail) or "pbw" (the 78 that pass the hidden
  tests and are wrong, the ones a test run before the judges would not stop);
- a judge of family f votes as `World.measured_seats`[f]'s seat did on that case (an invalid verdict is "not
  passed", the pre-registration's primary rule), so every seat's error rates and every pair's correlation are the
  measured ones, with no model of them;
- every judge of a family votes the same on a case, and so does the same judge asked again (an audit, a challenge
  panel), unless `World.measured_same` < 1: then each call returns the opposite with that chance. #160 took one
  verdict per case, so run-to-run variation is an assumption here, swept in the report;
- a volunteer re-runs with a family drawn by the seed;
- only fixes are judged this way: an ADR at the constitution tier keeps the assumed judges (#160 measured none).

    python3 -m pof.sim.openval.measured [--seeds 40] [--jobs 4] [--quick]

prints reports/open-validators-measured-v1.md's tables. No model call.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from . import panels as D
from . import scores as SC
from .params import PARAMS, Params, World
from .registry import Validator

MATRIX = Path(__file__).resolve().parents[3] / "data" / "judges" / "verdicts-v2.matrix.json"
T_CASE = 0x160CA5E  # randomness tag: the #160 case a submission is bound to
T_VOLUNTEER_FAMILY = 0x160F4A1
T_EVIDENCE = 0x160E71D
POOLS = {"hidden": ("v1", "more"), "pbw": ("pbw",)}
NAMES = {"anthropic": "Opus 5.5", "openai": "GPT-6.1", "google": "Gemini 3.1 Pro", "deepseek": "DeepSeek V3.2",
         "qwen": "Qwen3 235B", "mistral": "Mistral Large 3", "nvidia": "Nemotron 3 Super",
         "google-gemma": "Gemma 3 27B", "openai-oss": "gpt-oss-120b"}


@lru_cache(maxsize=None)
def table() -> Dict[str, object]:
    """{"good": [votes per case], "hidden": [...], "pbw": [...]}, each votes a {seat: bool} (invalid = False)."""
    m = json.loads(MATRIX.read_text(encoding="utf-8"))
    out: Dict[str, list] = {"good": [], "hidden": [], "pbw": []}
    for cid in sorted(m["cases"]):
        c = m["cases"][cid]
        votes = {s: v == 1 for s, v in c["votes"].items()}
        if c["label"] == "good":
            out["good"].append(votes)
        else:
            out["pbw" if c["arm"] == "pbw" else "hidden"].append(votes)
    return out


def rates(seat: str, pool: str) -> Tuple[float, float]:
    """(share of the pool's bad fixes the seat passed, share of good fixes it failed)."""
    t = table()
    return (mean(v[seat] for v in t[pool]), mean(not v[seat] for v in t["good"]))


def case_of(net, sub) -> Dict[str, bool]:
    cases = table()["good" if sub.good else net.w.measured]
    return cases[int(D.u(net.seed, T_CASE, sub.sid) * len(cases))]


def evidence(net, sub) -> bool:
    """Disputes backed by evidence (`World.evidence_find`): is a passing verdict reversed? A contender whose seat
    failed the case looks for evidence (counted in `stats`: what contenders spend); one draw per submission decides
    whether the evidence exists to be found (a bad fix) or wrong evidence is accepted (a good one)."""
    w = net.w
    case = case_of(net, sub)
    flags = sum(1 for s in w.evidence_by if not case[s])
    if not flags:
        return False
    net.stats["evidence_tried"] += 1
    net.stats["evidence_tried_good"] += sub.good
    net.stats["evidence_searches"] += flags
    return D.u(net.seed, T_EVIDENCE, sub.sid) < (w.evidence_false if sub.good else w.evidence_find)


def vote(net, sub, v: Optional[Validator], role: int) -> bool:
    w = net.w
    case = case_of(net, sub)
    seats = dict(w.measured_seats)
    if v is not None:
        seat = seats[v.family]
    else:
        fams = sorted(seats)
        seat = seats[fams[int(D.u(net.seed, T_VOLUNTEER_FAMILY, sub.sid) * len(fams))]]
    base = case[seat]
    if w.measured_same < 1.0:
        from .net import VOLUNTEER_ID
        if D.u(net.seed, D.T_VOTE, sub.sid, v.vid if v is not None else VOLUNTEER_ID, role) >= w.measured_same:
            return not base
    return base


# ---------- the worlds ----------

def world(seats: Sequence[Tuple[str, str]], pool: str, same: float = 1.0, per_family: int = 4) -> World:
    """`scores.SCORE_WORLD`'s grown network (newcomers at half a validator a week, each family equally likely) with
    `per_family` validators of each family at the start, judging as #160's seats did."""
    fams = tuple(f for f, _ in seats)
    return replace(SC.SCORE_WORLD, families=fams, initial_active=per_family * len(fams), family_accuracy=(),
                   family_blind=(), measured=pool, measured_seats=tuple(seats), measured_same=same)


PANEL3 = (("anthropic", "anthropic"), ("openai", "openai"), ("google", "google"))
FOUR = PANEL3 + (("open-weight", "deepseek"),)  # v3's four launch families; DeepSeek stands for the open-weight one
SEVEN = tuple((s, s) for s in ("anthropic", "openai", "google", "deepseek", "qwen", "mistral", "nvidia"))
TOP2 = (("anthropic", "anthropic"), ("openai", "openai"))
OPUS = (("anthropic", "anthropic"),)

MODES = (("no scores", None), ("v3's scores", "pay"))


def balanced(seat: str, pool: str) -> float:
    """D14's balanced score if outcomes were the truth: the mean of the seat's accuracy on good and on bad fixes."""
    fp, ff = rates(seat, pool)
    return ((1 - fp) + (1 - ff)) / 2


def known_answer_rank(w: World, top: Optional[int] = None, bar: Optional[float] = None):
    """`family_ok` for a rank kept on known answers (an upper bound: every family scored on the truth): the `top`
    families by balanced score, or every family at `bar` or above."""
    ranked = sorted(w.measured_seats, key=lambda fs: -balanced(fs[1], w.measured))
    ok = {f for f, _ in ranked[:top]} if top else {f for f, s in ranked if balanced(s, w.measured) >= bar}
    return lambda family: family in ok


def run_variant(seed: int, w: World, p: Params, top: Optional[int], bar: Optional[float]):
    from .net import Net
    net = Net(seed, p, w)
    net.family_ok = known_answer_rank(w, top, bar)
    return net.run()


def metrics(net) -> Dict[str, float]:
    m = SC.market_metrics(net)
    subs = [s for s in net.subs.values() if s.tier == "issue" and s.final is not None]
    bad = [s for s in subs if not s.good]
    good = [s for s in subs if s.good]
    m["bad_paid_pct"] = 100 * sum(1 for s in bad if s.final) / max(1, len(bad))
    m["good_paid_pct"] = 100 * sum(1 for s in good if s.final) / max(1, len(good))
    m["first_bad_pass_pct"] = 100 * sum(1 for s in bad if s.verdict) / max(1, len(bad))
    m["reversed_n"] = net.stats["reversed"]
    m["paid_n"] = net.stats["paid"]
    m["challenges"] = net.stats["challenges"]
    m["waited_pct"] = 100 * m["waited"]
    m["decided"] = len(subs)
    return m


def _one(job) -> Dict[str, float]:
    seed, mode, w, p = job
    if isinstance(mode, tuple):  # ("rank", top, bar): the known-answer rank
        return metrics(run_variant(seed, w, p, mode[1], mode[2]))
    return metrics(SC.run_mode(seed, mode, w, p))


def run_rows(rows, seeds: Sequence[int], jobs: int = 1):
    """rows: (label, mode, World, Params). Returns [(label, {metric: [per seed]})]."""
    work = [(s, mode, w, p) for _, mode, w, p in rows for s in seeds]
    if jobs > 1:
        from multiprocessing import Pool
        with Pool(jobs) as pool:
            res = pool.map(_one, work, chunksize=1)
    else:
        res = [_one(j) for j in work]
    out = []
    for i, (label, _, w, _) in enumerate(rows):
        chunk = res[i * len(seeds):(i + 1) * len(seeds)]
        out.append((label, w, {k: [r.get(k, float("nan")) for r in chunk] for k in chunk[0]}))
    return out


def _ms(xs: List[float], nd: int = 1, unit: str = "") -> str:
    xs = [x for x in xs if x == x]
    if not xs:
        return "n/a"
    m = mean(xs)
    se = (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 / len(xs) ** 0.5 if len(xs) > 1 else 0.0
    return f"{m:.{nd}f}{unit} ± {2 * se:.{nd}f}"


def outcome_table(data) -> str:
    head = ["World", "Bad fixes paid, of bad fixes decided", "Bad fixes merged per 100 paid", "Good fixes rejected",
            "Fixes paid a year", "Verdicts reversed a year", "Submissions that waited"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for label, _, m in data:
        out.append(f"| {label} | {_ms(m['bad_paid_pct'], 1, ' %')} | {_ms(m['bad_per_100'], 1)} | "
                   f"{_ms(m['good_failed_pct'], 1, ' %')} | {_ms(m['paid_n'], 0)} | {_ms(m['reversed_n'], 1)} | "
                   f"{_ms(m['waited_pct'], 1, ' %')} |")
    return "\n".join(out)


def score_table(data) -> str:
    out = ["| World | Family (seat) | Measured: bad passed / good failed | Score on known answers | "
           "Score by v3's rule | Barred, share of the year |", "|---|---|---|---|---|---|"]
    for label, w, m in data:
        for f, seat in w.measured_seats:
            fp, ff = rates(seat, w.measured)
            out.append(f"| {label} | `{f}` ({NAMES[seat]}) | {100 * fp:.0f} % / {100 * ff:.0f} % | "
                       f"{100 * balanced(seat, w.measured):.0f} % | "
                       f"{_ms([100 * x for x in m.get(f'score_{f}', [])], 1, ' %')} | "
                       f"{_ms([100 * x for x in m.get(f'barred_{f}', [])], 0, ' %')} |")
    return "\n".join(out)


def plan(p: Params = PARAMS):
    rows = [("Assumed (report v3's score world: 95 / 90 / 85 / 68 %, independent calls), no scores", None,
             SC.SCORE_WORLD, p),
            ("**Assumed, v3's scores**", "pay", SC.SCORE_WORLD, p)]
    for pool, what in (("hidden", "fixes the tests fail"), ("pbw", "fixes that pass the tests and are wrong")):
        for name, seats in (("four families", FOUR), ("seven families", SEVEN), ("Opus and GPT-6.1 only", TOP2),
                            ("Opus only", OPUS)):
            for mlabel, mode in MODES:
                for same in (1.0, 0.9):
                    if same < 1.0 and (mode is None or name not in ("four families",)):
                        continue
                    again = "" if same == 1.0 else ", a repeated call differs 1 time in 10"
                    rows.append((f"Measured, bad = {what}; {name}; {mlabel}{again}", mode,
                                 world(seats, pool, same), p))
    return rows


def variants(p: Params = PARAMS):
    """What would change the result, on the measured judges (exploratory)."""
    nocap = replace(p, FAMILY_CAP=False)
    strict = replace(nocap, PASS_RULE="unanimous")
    rows = []
    for pool, what in (("hidden", "fixes the tests fail"), ("pbw", "fixes that pass the tests and are wrong")):
        for name, seats in (("four families", FOUR), ("seven families", SEVEN)):
            w = world(seats, pool)
            pre = f"bad = {what}; {name}: "
            rows += [(pre + "**v3 as designed** (scores on agreement, family cap, majority)", "pay", w, p),
                     (pre + "v3's scores, no family cap", "pay", w, nocap),
                     (pre + "known-answer rank at 70 %, family cap", ("rank", None, p.SCORE_MIN), w, p),
                     (pre + "known-answer rank at 70 %, no family cap", ("rank", None, p.SCORE_MIN), w, nocap),
                     (pre + "top family only, no family cap", ("rank", 1, None), w, nocap),
                     (pre + "top two families, no family cap, majority", ("rank", 2, None), w, nocap),
                     (pre + "top two families, no family cap, every judge must pass", ("rank", 2, None), w, strict),
                     (pre + "top three families, family cap, majority", ("rank", 3, None), w, p)]
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.measured")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="4 seeds")
    a = ap.parse_args(argv)
    seeds = list(range(1, (4 if a.quick else a.seeds) + 1))
    data = run_rows(plan(), seeds, a.jobs)
    print(f"Seeds 1-{seeds[-1]}; every ± is two standard errors of the mean.\n")
    print("### Outcomes\n")
    print(outcome_table(data))
    print("\n### Scores, with v3's rule\n")
    print(score_table([d for d in data if d[1].measured and "v3's scores" in d[0]]))
    print("\n### What would change it (exploratory)\n")
    print(outcome_table(run_rows(variants(), seeds, a.jobs)))
    print("\n### The rank on known answers\n")
    print("| Bad fixes | " + " | ".join(NAMES[s] for _, s in SEVEN) + " |")
    print("|---|" + "---|" * len(SEVEN))
    for pool, what in (("hidden", "the tests fail them"), ("pbw", "pass the tests, wrong")):
        print(f"| {what} | " + " | ".join(f"{100 * balanced(s, pool):.0f} %" for _, s in SEVEN) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
