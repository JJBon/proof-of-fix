#!/usr/bin/env python3
"""Judges with a failure memory (#241, reports/judges-memory-v1.prereg.md): the plan, a fake run, the paid run and
the one analysis.

    plan                 write reports/judges-memory-v1.plan.json (calls, worst case, hash); no network
    fake                 the whole pipeline with fake judges, then the report (no network)
    run --execute        THE PAID RUN, only with POF_JUDGE_RUN_APPROVED equal to the plan's hash; resumable
    report --final       the analysis, once, after the last call

The baseline arm is the stored v2 verdicts (data/judges/verdicts-v2); the new calls are the memory arm, the
other-issue memory arm on good fixes and a drift check. It reuses judge_run.py's gateway client, limits and resume.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import judge_run as JR  # noqa: E402
from pof.judges import memory as M  # noqa: E402
from pof.judges import plan as PL  # noqa: E402
from pof.judges import prereg as PR  # noqa: E402
from pof.judges import prompt as P  # noqa: E402
from pof.judges.fake import FakeJudge  # noqa: E402

MEMDIR = Path(os.environ.get("POF_JUDGES_MEMORY") or ROOT / "data" / "judges" / "memory-v1")
PLAN = Path(os.environ.get("POF_JUDGES_PLAN_MEMORY") or ROOT / "reports" / "judges-memory-v1.plan.json")
SEATS = ("anthropic", "openai", "google")  # the owner's choice (2026-11-15): the top tier
ARMS = ("mem", "other", "drift")
GUARD = 3  # H2: good fixes passed may drop by at most this many
DRIFT_MAX = 5  # of the drift reruns; more and the seat's stored baseline is not used
ALPHA = 0.05
KINDS = {"same_issue": "this same issue", "same_file": "a different issue, changing a file this fix also changes",
         "other_issue": "a different issue in this repository"}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def inputs() -> tuple[dict, dict]:
    return (json.loads((MEMDIR / "set.json").read_text(encoding="utf-8")),
            json.loads((MEMDIR / "notes.json").read_text(encoding="utf-8")))


def memory_text(picks: list, notes: dict) -> str:
    return "\n\n".join(f"[{n}] An earlier fix for {KINDS[kind]} was rejected.\n{notes[nid]}"
                       for n, (_prior, kind, nid) in enumerate(picks, 1))


def variants(base: dict[str, dict], st: dict, notes: dict) -> dict[str, dict]:
    """The run's cases by id: <case>#mem, <case>#other (good fixes with a note from another issue), <case>#drift."""
    out = {}
    for cid, picks in st["memory"].items():
        out[f"{cid}#mem"] = dict(base[cid], id=f"{cid}#mem", memory=memory_text(picks, notes))
    for cid, picks in st["other"].items():
        if picks:
            out[f"{cid}#other"] = dict(base[cid], id=f"{cid}#other", memory=memory_text(picks, notes))
    for cid in st["drift"]:
        out[f"{cid}#drift"] = dict(base[cid], id=f"{cid}#drift")
    return out


def base_cases() -> dict[str, dict]:
    return {c["id"]: c for cases in JR.load_sets().values() for c in cases}


def calls(cases: dict[str, dict]) -> list[tuple[int, str, str]]:
    """(stage, seat, case id): seats in order, then the arms, then cases by id."""
    return [(1, s, i) for s in SEATS for arm in ARMS for i in sorted(cases) if i.endswith("#" + arm)]


def worst(seat: str, case: dict) -> tuple[int, float]:
    """The call's worst case as the runner counts it: the request's bytes as input tokens, the answer at its limit."""
    s = PR.all_seats(())[seat]
    system, user = M.messages(case)
    cap = PR.limit(seat, case["size"])
    _path, payload = JR.request(s, system, user, cap)
    payload.update(PR.REQUEST_EXTRA.get(seat, {}))
    n = len(json.dumps(payload).encode())
    m = PR.seat_price(seat)
    return n + cap, (n * m.input + cap * m.output) / PL.C.M


def make_plan(base: dict[str, dict]) -> dict:
    st, notes = inputs()
    cases = variants(base, st, notes)
    todo = calls(cases)
    per = {s: {"calls": 0, "tokens": 0, "usd": 0.0} for s in SEATS}
    for _stage, seat, cid in todo:
        t, usd = worst(seat, cases[cid])
        per[seat]["calls"] += 1
        per[seat]["tokens"] += t
        per[seat]["usd"] += usd
    for s in per:
        per[s]["usd"] = round(per[s]["usd"], 2)
    seats = PR.all_seats(())
    core = {
        "prompt": P.prompt_hash(), "memory_text": sha(M.MEMORY), "notes": sha(json.dumps(notes, sort_keys=True)),
        "set": sha(json.dumps(st, sort_keys=True)),
        "seats": {s: {"model": seats[s].model, "extra": PR.REQUEST_EXTRA.get(s, {})} for s in SEATS},
        "cases": {i: sha("\n".join(M.messages(c)) + f"|{c['size']}") for i, c in sorted(cases.items())},
        "rules": {"guard": GUARD, "drift_max": DRIFT_MAX, "alpha": ALPHA},
    }
    total = round(sum(p["usd"] for p in per.values()), 2)
    return {"hash": sha(json.dumps(core, sort_keys=True))[:16], "core": core, "calls": len(todo), "per_seat": per,
            "seats": list(SEATS),
            "worst_usd": total, "worst_tokens": sum(p["tokens"] for p in per.values()),
            "arms": {a: sum(1 for i in cases if i.endswith("#" + a)) for a in ARMS}}


def use_seats(seats) -> None:
    """The run's seats: `plan --seats` chooses them (part of the hash); every other command reads the plan's."""
    global SEATS
    unknown = [s for s in seats if s not in PR.all_seats(())]
    if unknown:
        raise SystemExit(f"unknown seats: {unknown}")
    SEATS = tuple(seats)


def cmd_plan(a) -> int:
    use_seats(a.seats.split(",") if a.seats else SEATS)
    plan = make_plan(base_cases())
    PLAN.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for s, p in plan["per_seat"].items():
        print(f"{s:10} calls={p['calls']:4}  worst case ${p['usd']:.2f}  ({p['tokens']:,} tokens)")
    print(f"total: {plan['calls']} calls, worst case ${plan['worst_usd']:.2f}; arms {plan['arms']}")
    print(f"plan {plan['hash']} written to {PLAN}")
    return 0


# ---------- the analysis ----------

def sign_less(to_fail: int, to_pass: int) -> float:
    """One-sided exact sign test: the chance of at least `to_fail` of the changed verdicts going to fail."""
    n = to_fail + to_pass
    return 1.0 if n == 0 else sum(comb(n, k) for k in range(to_fail, n + 1)) / 2 ** n


def holm(ps: dict[str, float]) -> dict[str, float]:
    out, worst_p = {}, 0.0
    for rank, (k, p) in enumerate(sorted(ps.items(), key=lambda kv: kv[1])):
        worst_p = max(worst_p, min(1.0, (len(ps) - rank) * p))
        out[k] = worst_p
    return out


def solves(records: list[dict]) -> dict[str, bool | None]:
    """{case id: solves}, None for an invalid verdict; stage 0 (smoke) left out."""
    return {r["case"]: r["verdict"].get("solves") for r in records if str(r.get("stage")) != "0"}


def analyse(st: dict, baseline: dict[str, dict], new: dict[str, dict], seen: set[str] = frozenset()) -> str:
    """baseline[seat] and new[seat] are {case id: solves or None}. `seen` are bad cases Opus judged with notes in
    the pilot."""
    label = st["label"]
    bad = [c for c in sorted(label) if label[c] == "bad"]
    good = [c for c in sorted(label) if label[c] == "good"]
    rows, ps, notes = {}, {}, []
    for seat in SEATS:
        b, n = baseline.get(seat, {}), new.get(seat, {})
        pair = lambda cs, arm: [(b[c], n[f"{c}#{arm}"]) for c in cs  # noqa: E731
                                if isinstance(b.get(c), bool) and isinstance(n.get(f"{c}#{arm}"), bool)]
        pb = pair(bad, "mem")
        to_fail, to_pass = sum(x and not y for x, y in pb), sum(y and not x for x, y in pb)
        ps[seat] = sign_less(to_fail, to_pass)
        pg, po, pd = pair(good, "mem"), pair(good, "other"), pair(st["drift"], "drift")
        drift = sum(x != y for x, y in pd)
        rows[seat] = {
            "bad": (len(pb), sum(x for x, _ in pb), sum(y for _, y in pb), to_fail, to_pass),
            "good": (len(pg), sum(x for x, _ in pg), sum(y for _, y in pg)),
            "other": (len(po), sum(x for x, _ in po), sum(y for _, y in po)),
            "drift": (len(pd), drift), "dropped": len(bad) - len(pb), "good_pairs": pg,
        }
        if seat == "anthropic" and seen:
            fresh = pair([c for c in bad if c not in seen], "mem")
            notes.append(f"- Opus on the {len(fresh)} bad fixes it had not judged with notes in the pilot: "
                         f"{sum(x for x, _ in fresh)} passed at baseline, {sum(y for _, y in fresh)} with memory.")
    adj = holm(ps)
    out = ["| Seat | Bad fixes (pairs) | Passed, baseline | Passed, memory | To reject | To pass | p (one-sided) | Holm |"
           " Good passed: baseline / memory / other-issue | Drift | Result |", "|" + "---|" * 11]
    for seat in SEATS:
        r = rows[seat]
        n, b0, m0, tf, tp = r["bad"]
        gn, g0, g1 = r["good"]
        on, o0, o1 = r["other"]
        dn, dd = r["drift"]
        pg = [(b0_, m_) for b0_, m_ in rows[seat]["good_pairs"]]
        h3 = sign_less(sum(y and not x for x, y in pg), sum(x and not y for x, y in pg))
        notes.append(f"- {seat}, good fixes (H3, secondary): {sum(y and not x for x, y in pg)} to pass, "
                     f"{sum(x and not y for x, y in pg)} to reject, one-sided p = {h3:.4f}.")
        h1 = adj[seat] < ALPHA
        h2 = g1 >= g0 - GUARD and o1 >= o0 - GUARD
        usable = dd <= DRIFT_MAX
        result = ("inconclusive: the stored baseline drifted" if not usable else
                  "supported" if h1 and h2 else "stricter, not better informed" if h1 else "not supported")
        out.append(f"| {seat} | {n} | {b0} | {m0} | {tf} | {tp} | {ps[seat]:.4f} | {adj[seat]:.4f} | "
                   f"{g0} / {g1} of {gn}; {o0} / {o1} of {on} | {dd} of {dn} | {result} |")
        if r["dropped"]:
            notes.append(f"- {seat}: {r['dropped']} bad-fix pairs dropped for an invalid verdict.")
    return "\n".join(out + [""] + notes)


def stored_new(directory: Path) -> dict[str, dict]:
    return {s: solves(JR.stored(directory / f"{s}.jsonl")) for s in SEATS}


def pilot_seen() -> set[str]:
    path = ROOT / "data" / "judges" / "memory-pilot" / "key2.json"
    if not path.exists():
        return set()
    return {v["case"] for v in json.loads(path.read_text(encoding="utf-8")).values() if v["label"] == "bad"}


def cmd_fake(_a) -> int:
    base = base_cases()
    st, notes = inputs()
    cases = variants(base, st, notes)
    judges = {s: FakeJudge(s, 0.8) for s in SEATS}
    out = JR.DATA / "fake-memory-v1"
    for old in out.glob("*.jsonl"):
        old.unlink()
    JR.judge_v2(out, calls(cases), cases, lambda s, c: (judges[s].answer(c), {}, "fake"))
    baseline = {s: {c: P.parse(judges[s].answer(base[c])).get("solves") for c in st["label"]} for s in SEATS}
    print(analyse(st, baseline, stored_new(out)))
    return 0


def cmd_run(a) -> int:
    if not a.execute:
        raise SystemExit("the paid run needs --execute and the owner's approval of the plan's hash")
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    base = base_cases()
    refusal = JR.approval(plan["hash"], make_plan(base)["hash"], os.environ.get("POF_JUDGE_RUN_APPROVED"))
    if refusal:
        raise SystemExit(refusal.replace("reports/judges-v1.md", "reports/judges-memory-v1.prereg.md"))
    st, notes = inputs()
    cases = variants(base, st, notes)
    out = JR.DATA / "verdicts-memory-v1"
    seats = {s: PR.all_seats(())[s] for s in SEATS}
    limits = JR.Limits(a.max_tokens, a.max_usd, *JR.prior_spend_v2(out, list(seats)))
    gateway = JR.Gateway(os.environ.get("MODEL_GATEWAY_URL", JR.GATEWAY), JR.gateway_token(JR.TOKEN_HELPER))
    answer = JR.answerer_v2(gateway, limits, seats, messages=M.messages)
    try:
        smoke = out / "smoke"
        JR.judge_v2(smoke, [(0, s, PR.SMOKE["id"]) for s in seats], {PR.SMOKE["id"]: PR.SMOKE}, answer)
        bad = [r["seat"] for r in JR.load_verdicts(smoke) if "error" in r["verdict"]]
        if bad:
            raise JR.Stop(f"stage 0: no valid verdict from {bad}; nothing judged")
        JR.judge_v2(out, calls(cases), cases, answer)
    except JR.Stop as e:
        print(f"{e}\n{limits.tokens:,} tokens and ${limits.usd:.2f} used so far; rerun to resume.", file=sys.stderr)
        return 3
    print(f"done: {limits.tokens:,} tokens, ${limits.usd:.2f}", file=sys.stderr)
    return 0


def cmd_report(a) -> int:
    if not a.final:
        raise SystemExit("report runs once, after every call: pass --final (no interim looks)")
    st, notes = inputs()
    out = JR.DATA / "verdicts-memory-v1"
    new = stored_new(out)
    want = {i for _s, _seat, i in calls(variants(base_cases(), st, notes))}
    for s in SEATS:
        if want - set(new[s]):
            raise SystemExit(f"{s}: {len(want - set(new[s]))} calls still to make; the report waits for the last one")
    baseline = {s: solves(JR.stored(JR.DATA / "verdicts-v2" / f"{s}.jsonl")) for s in SEATS}
    print(analyse(st, baseline, new, pilot_seen()))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan")
    pl.add_argument("--seats", help="comma-separated seats (default: anthropic,openai,google)")
    pl.set_defaults(fn=cmd_plan)
    sub.add_parser("fake").set_defaults(fn=cmd_fake)
    r = sub.add_parser("run")
    r.add_argument("--execute", action="store_true")
    r.add_argument("--max-usd", type=float, required=True)
    r.add_argument("--max-tokens", type=int, default=40_000_000)
    r.set_defaults(fn=cmd_run)
    rp = sub.add_parser("report")
    rp.add_argument("--final", action="store_true")
    rp.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    if a.cmd != "plan" and PLAN.exists():
        use_seats(json.loads(PLAN.read_text(encoding="utf-8")).get("seats", SEATS))
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
