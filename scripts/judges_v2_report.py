#!/usr/bin/env python3
"""Every table of reports/judges-v2.md from the stored verdicts (proof-of-fix#160).

    python3 scripts/judges_v2_report.py            # writes reports/judges-v2.json and prints the tables

The hypotheses' numbers come from pof.judges.prereg.evaluate, unchanged (it is in the plan's hash). Everything else
here is the descriptive reporting section 6 of the pre-registration lists, plus what is marked post hoc. Reads only
data/judges/verdicts-v2 and the manifests; makes no model call.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pof.judges import prereg as PR  # noqa: E402
from pof.judges import stats as S  # noqa: E402

_spec = importlib.util.spec_from_file_location("judge_run", ROOT / "scripts" / "judge_run.py")
JR = importlib.util.module_from_spec(_spec)
sys.modules["judge_run"] = JR
_spec.loader.exec_module(JR)

MAIN = ("anthropic", "openai", "google", "deepseek", "qwen", "mistral", "nvidia")
EXTRA = ("google-gemma", "openai-oss")
NAMES = {"anthropic": "Opus 5.5", "openai": "GPT-6.1", "google": "Gemini 3.1 Pro", "deepseek": "DeepSeek V3.2",
         "qwen": "Qwen3 235B", "mistral": "Mistral Large 3", "nvidia": "Nemotron 3 Super", "google-gemma": "Gemma 3 27B",
         "openai-oss": "gpt-oss-120b"}
# The AI review of the six flagged cases (pre-registration, section 9 item 7): relabel two good fixes as bad, drop one.
REVIEW_RELABEL = {"pydata__xarray-3993:good": "bad", "sphinx-doc__sphinx-10673:good": "bad"}
REVIEW_DROP = ("django__django-16100:bad",)
INVALID_RULE = 0.10


def passed(r: dict) -> bool:
    return PR.passed(r, False)


def rate(k: int, n: int) -> dict:
    lo, hi = S.wilson(k, n) if n else (None, None)
    return {"k": k, "n": n, "rate": k / n if n else None, "low": lo, "high": hi}


def cell(x: dict) -> str:
    if not x["n"]:
        return "n/a"
    return f"{x['k']} of {x['n']} ({x['rate']:.0%}, {x['low']:.0%}–{x['high']:.0%})"


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def group(meta: dict, source: dict) -> dict[str, list[str]]:
    """The clean case ids of each reported group."""
    g = {"bad-v1": [], "bad-more": [], "pbw": [], "good-gold": [], "good-agent": []}
    for i, c in meta.items():
        if c.get("excluded") or c["arm"].endswith("-inj"):
            continue
        if c["arm"] == "pbw":
            g["pbw"].append(i)
        elif c["label"] == "bad":
            g["bad-v1" if c["arm"] == "v1" else "bad-more"].append(i)
        elif c["arm"] == "v1":
            g["good-gold" if source.get(i) == "gold" else "good-agent"].append(i)
    return g


def build(records: list[dict], plan: dict, manifests: dict[str, dict], resamples: int = 10_000) -> dict:
    meta = plan["cases"]
    t: dict[str, dict[str, dict]] = {}
    for r in records:
        t.setdefault(r["case"], {})[r["seat"]] = r
    seats = [s for s in MAIN + EXTRA if any(s in v for v in t.values())]
    source = {c["id"]: c.get("source") for c in manifests["v1"]["cases"]}
    pbw = {c["id"]: c for c in manifests["pbw"]["cases"]}
    g = group(meta, source)
    bad = g["bad-v1"] + g["bad-more"]
    good = g["good-gold"] + g["good-agent"]
    out: dict = {"calls": len(records), "groups": {k: len(v) for k, v in g.items()}}

    # ---- each seat, per arm
    per = {}
    for s in seats:
        mine = [r for r in records if r["seat"] == s]
        cl = [r for r in mine if not r.get("injection")]
        def fp(ids):
            ids = [i for i in ids if s in t.get(i, {})]
            return rate(sum(passed(t[i][s]) for i in ids), len(ids))
        def ff(ids):
            ids = [i for i in ids if s in t.get(i, {})]
            return rate(sum(not passed(t[i][s]) for i in ids), len(ids))
        both = [i for i in bad + good if s in t.get(i, {})]
        right = sum(passed(t[i][s]) == (meta[i]["label"] == "good") for i in both)
        row = {"false_pass": fp(bad), "false_pass_v1": fp(g["bad-v1"]), "false_pass_more": fp(g["bad-more"]),
               "pbw_pass": fp(g["pbw"]), "false_fail": ff(good), "false_fail_gold": ff(g["good-gold"]),
               "false_fail_agent": ff(g["good-agent"]), "accuracy": rate(right, len(both)),
               "invalid_clean": rate(sum("error" in r["verdict"] for r in cl), len(cl)),
               "invalid_all": rate(sum("error" in r["verdict"] for r in mine), len(mine)),
               "errors": sum(str(r.get("answer", "")).startswith("ERROR") for r in mine), "injected": {}}
        for k in PR.KINDS:
            ids = [i for i, c in meta.items() if c["arm"].endswith("-inj") and i.endswith("+" + k) and s in t.get(i, {})]
            base = [i.rsplit("+", 1)[0] for i in ids]
            failed_clean = [(i, b) for i, b in zip(ids, base) if s in t.get(b, {}) and not passed(t[b][s])]
            passed_clean = [(i, b) for i, b in zip(ids, base) if s in t.get(b, {}) and passed(t[b][s])]
            row["injected"][k] = {"false_pass": rate(sum(passed(t[i][s]) for i in ids), len(ids)),
                                  "clean_false_pass": rate(sum(passed(t[b][s]) for b in base if s in t.get(b, {})),
                                                           len(base)),
                                  "flipped_to_pass": rate(sum(passed(t[i][s]) for i, _ in failed_clean),
                                                          len(failed_clean)),
                                  "flipped_to_fail": rate(sum(not passed(t[i][s]) for i, _ in passed_clean),
                                                          len(passed_clean))}
        # tokens and dollars, by stage
        m = PR.seat_price(s)
        stages: dict[int, dict] = {}
        for r in mine:
            u = r.get("usage") or {}
            i_, o_ = u.get("input_tokens"), u.get("output_tokens")
            st = stages.setdefault(r["stage"], {"calls": 0, "input": 0, "output": 0, "usd": 0.0})
            st["calls"] += 1
            if isinstance(i_, int) and isinstance(o_, int):
                st["input"] += i_
                st["output"] += o_
                st["usd"] += (i_ * m.input + o_ * m.output) / 1e6
            else:
                st["usd"] += (r.get("worst") or (0, 0.0))[1]
        row["stages"] = stages
        row["usd"] = sum(x["usd"] for x in stages.values())
        row["calls"] = len(mine)
        per[s] = row
    out["seats"] = per
    out["failed_seats"] = [s for s in seats if per[s]["invalid_clean"]["rate"] > INVALID_RULE]

    # ---- the hypotheses, both rules for invalid verdicts
    primary = PR.evaluate(records, meta, invalid_passes=False, resamples=resamples)
    sens = PR.evaluate(records, meta, invalid_passes=True, resamples=resamples)
    out["primary"], out["invalid_passes"] = primary, sens
    out["decisions_by_code"] = PR.decisions(primary, sens)

    # ---- H1 by evidence, by tool, and on every patch with an issue-level bootstrap
    def panel_of(seats3, quorum, i):
        row = t.get(i, {})
        if not all(s in row for s in seats3):
            return None
        return sum(passed(row[s]) for s in seats3) >= quorum
    prim = [i for i in g["pbw"] if meta[i].get("primary")]
    def caught(ids):
        o = [x for x in (panel_of(PR.PANEL, PR.QUORUM, i) for i in ids) if x is not None]
        return rate(sum(not x for x in o), len(o))
    h1 = {"primary": caught(prim), "all": caught(g["pbw"]),
          "by_evidence": {e: caught([i for i in prim if pbw[i]["evidence"] == e])
                          for e in sorted({pbw[i]["evidence"] for i in prim})},
          "by_evidence_all": {e: caught([i for i in g["pbw"] if pbw[i]["evidence"] == e])
                              for e in sorted({pbw[i]["evidence"] for i in g["pbw"]})},
          "by_tool_all": {tool: caught([i for i in g["pbw"] if pbw[i]["tool"] == tool])
                          for tool in sorted({pbw[i]["tool"] for i in g["pbw"]})}}
    issues = sorted({meta_i.split(":")[0] for meta_i in g["pbw"]})
    by_issue = {iss: [i for i in g["pbw"] if i.split(":")[0] == iss] for iss in issues}
    def stat(idx):
        ids = [i for j in idx for i in by_issue[issues[j]]]
        o = [panel_of(PR.PANEL, PR.QUORUM, i) for i in ids]
        return sum(not x for x in o) / len(o) if o else None
    values = []
    import random
    rng = random.Random(160)
    for _ in range(resamples):
        v = stat([rng.randrange(len(issues)) for _ in issues])
        if v is not None:
            values.append(v)
    values.sort()
    h1["all_bootstrap"] = {"issues": len(issues), "low": values[int(0.025 * (len(values) - 1))],
                           "high": values[-int(0.025 * (len(values) - 1)) - 1]}
    out["H1_detail"] = h1

    # ---- every 2-of-3 panel of the seven seats, and the 5-of-7 panel (descriptive)
    def panel_row(seats3, quorum):
        fpb = [x for x in (panel_of(seats3, quorum, i) for i in bad) if x is not None]
        pb = [x for x in (panel_of(seats3, quorum, i) for i in g["pbw"]) if x is not None]
        gd = [x for x in (panel_of(seats3, quorum, i) for i in good) if x is not None]
        return {"false_pass": rate(sum(fpb), len(fpb)), "pbw_pass": rate(sum(pb), len(pb)),
                "false_fail": rate(sum(not x for x in gd), len(gd))}
    out["panels_2of3"] = {"+".join(c): panel_row(c, 2) for c in combinations(MAIN, 3)}
    out["panel_5of7"] = panel_row(MAIN, 5)
    # post hoc rules on the two strongest seats
    out["post_hoc_rules"] = {"Opus alone": panel_row(("anthropic",), 1), "GPT-6.1 alone": panel_row(("openai",), 1),
                             "Opus and GPT-6.1 both pass": panel_row(("anthropic", "openai"), 2),
                             "Opus, GPT-6.1 and Gemini all pass": panel_row(PR.PANEL, 3),
                             "the panel (2 of 3)": panel_row(PR.PANEL, 2)}

    # ---- injection: the pre-registered panel, per kind
    inj = {}
    for k in PR.KINDS:
        ids = [i for i, c in meta.items() if c["arm"].endswith("-inj") and i.endswith("+" + k)]
        pairs = [(panel_of(PR.PANEL, PR.QUORUM, i), panel_of(PR.PANEL, PR.QUORUM, i.rsplit("+", 1)[0])) for i in ids]
        pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
        inj[k] = {"n": len(pairs), "clean_pass": sum(b for _, b in pairs), "injected_pass": sum(a for a, _ in pairs),
                  "flipped_to_pass": sum(a and not b for a, b in pairs),
                  "flipped_to_fail": sum(b and not a for a, b in pairs)}
    out["injection_panel"] = inj

    # ---- agreement between the seven seats on the clean cases: both wrong
    agree = {}
    ids = [i for i in bad + good + g["pbw"] if all(s in t.get(i, {}) for s in seats)]
    wrong = {s: {i for i in ids if passed(t[i][s]) != (meta[i]["label"] == "good")} for s in seats}
    for a in seats:
        for b in seats:
            agree[f"{a}|{b}"] = {"both_wrong": len(wrong[a] & wrong[b]), "a_wrong": len(wrong[a]),
                                 "same_verdict": sum(passed(t[i][a]) == passed(t[i][b]) for i in ids)}
    out["agreement"] = {"n": len(ids), "pairs": agree}

    # ---- H3 without the failed seat (post hoc)
    if out["failed_seats"]:
        kept = [r for r in records if r["seat"] not in out["failed_seats"]]
        e = PR.evaluate(kept, meta, invalid_passes=False, resamples=resamples)["H3"]
        out["H3_without_failed"] = {k: e[k] for k in ("n", "gap", "low", "high", "p")}

    # ---- the review-list sensitivity analysis
    reviewed = {i: dict(c) for i, c in meta.items()}
    for i, label in REVIEW_RELABEL.items():
        reviewed[i]["label"] = label
    for i in REVIEW_DROP:
        reviewed[i]["excluded"] = "dropped by the review"
        for k in PR.KINDS:
            if f"{i}+{k}" in reviewed:
                reviewed[f"{i}+{k}"]["excluded"] = "dropped by the review"
    rv = PR.evaluate(records, reviewed, invalid_passes=False, resamples=resamples)
    out["review"] = {"relabel": REVIEW_RELABEL, "drop": list(REVIEW_DROP),
                     "verdicts": {i: {s: passed(t[i][s]) for s in seats if s in t.get(i, {})}
                                  for i in list(REVIEW_RELABEL) + list(REVIEW_DROP) +
                                  ["sympy__sympy-21379:good", "sympy__sympy-13615:good", "django__django-16950:bad"]},
                     "evaluate": rv}
    out["total_usd"] = sum(per[s]["usd"] for s in seats)
    out["total_tokens"] = sum(x["input"] + x["output"] for s in seats for x in per[s]["stages"].values())
    return out


def markdown(o: dict, plan: dict) -> str:
    per = o["seats"]
    seats = list(per)
    L = []
    L.append("### Each seat on the clean cases\n")
    L.append(table(["Seat", "Bad fixes passed (false passes)", "Passing-but-wrong passed", "Good fixes failed (false fails)",
                    "Accuracy on bad + good", "Invalid on clean cases", "Cents per call"],
                   [[NAMES[s], cell(per[s]["false_pass"]), cell(per[s]["pbw_pass"]), cell(per[s]["false_fail"]),
                     cell(per[s]["accuracy"]), cell(per[s]["invalid_clean"]),
                     f"{100 * per[s]['usd'] / per[s]['calls']:.2f}"] for s in seats]))
    L.append("\n### False passes and false fails by source\n")
    L.append(table(["Seat", "v1's bad fixes passed", "Extension's bad fixes passed", "Gold good fixes failed",
                    "Agent-written good fixes failed"],
                   [[NAMES[s], cell(per[s]["false_pass_v1"]), cell(per[s]["false_pass_more"]),
                     cell(per[s]["false_fail_gold"]), cell(per[s]["false_fail_agent"])] for s in seats]))
    L.append("\n### Injected bad fixes, per seat (v1's 50 bad fixes per kind)\n")
    rows = []
    for s in seats:
        for k in PR.KINDS:
            x = per[s]["injected"][k]
            if x["false_pass"]["n"]:
                rows.append([NAMES[s], k, cell(x["clean_false_pass"]), cell(x["false_pass"]),
                             cell(x["flipped_to_pass"]), cell(x["flipped_to_fail"])])
    L.append(table(["Seat", "Kind", "Passed clean", "Passed injected", "Failed clean, passed injected (injection's success)",
                    "Passed clean, failed injected"], rows))
    L.append("\n### Injection and the panel\n")
    L.append(table(["Kind", "Cases", "Panel passed clean", "Panel passed injected", "Flipped to pass", "Flipped to fail"],
                   [[k, v["n"], v["clean_pass"], v["injected_pass"], v["flipped_to_pass"], v["flipped_to_fail"]]
                    for k, v in o["injection_panel"].items()]))
    L.append("\n### The hypotheses\n")
    rows = []
    for h in ("H1", "H2", "H3", "H4", "H9"):
        a, b = o["primary"]["holm"][h], o["invalid_passes"]["holm"][h]
        rows.append([h, f"{a['p']:.4f}", f"{a['adjusted']:.4f}", "yes" if a["reject"] else "no", f"{b['p']:.4f}",
                     f"{b['adjusted']:.4f}", "yes" if b["reject"] else "no", o["decisions_by_code"][h]])
    L.append(table(["", "p (invalid = not passed)", "Holm-adjusted", "Rejected", "p (invalid = passed)", "Holm-adjusted",
                    "Rejected", "Status by the code"], rows))
    for name, key in (("invalid = not passed", "primary"), ("invalid = passed", "invalid_passes")):
        p = o[key]
        L.append(f"\n**Numbers, {name}:**")
        L.append(f"- H1: caught {p['H1']['caught']} of {p['H1']['n']} ({p['H1']['rate']:.3f}, "
                 f"{p['H1']['low']:.3f}–{p['H1']['high']:.3f})")
        L.append(f"- H2: best {p['H2']['best']}; false passes {p['H2']['false_passes']}; panel "
                 f"{p['H2']['panel_false_passes']} of {p['H2']['n']}; best-only {p['H2']['best_only']}, panel-only "
                 f"{p['H2']['panel_only']}; panel interval {p['H2']['panel_interval']}, best {p['H2']['best_interval']}")
        L.append(f"- H3: gap {p['H3']['gap']:.3f} ({p['H3']['low']:.3f} to {p['H3']['high']:.3f}), n {p['H3']['n']}")
        L.append("- H4: " + "; ".join(f"{k} {v['difference']:+.3f} ({v['low']:+.3f} to {v['high']:+.3f}), n {v['n']}, "
                                      f"p {v['p']:.4f}" for k, v in p["H4"]["kinds"].items()))
        L.append(f"- H9: risk difference {p['H9']['rd']:+.3f} ({p['H9']['low']:+.3f} to {p['H9']['high']:+.3f}), se "
                 f"{p['H9']['se']:.4f}; TOST p {p['H9']['p']:.4f}; CMH p {p['H9']['difference_p']:.4f}; strata "
                 f"{p['H9']['strata']}")
    L.append("\n### H1 in detail\n")
    h1 = o["H1_detail"]
    rows = [["Primary: one patch per issue", cell(h1["primary"])],
            ["All patches", cell(h1["all"]) + f"; issue-level bootstrap {h1['all_bootstrap']['low']:.0%}–"
             f"{h1['all_bootstrap']['high']:.0%} over {h1['all_bootstrap']['issues']} issues"]]
    rows += [[f"Primary, evidence: {e}", cell(v)] for e, v in h1["by_evidence"].items()]
    rows += [[f"All patches, evidence: {e}", cell(v)] for e, v in h1["by_evidence_all"].items()]
    rows += [[f"All patches, tool: {e}", cell(v)] for e, v in h1["by_tool_all"].items()]
    L.append(table(["Passing-but-wrong fixes", "Failed by the panel"], rows))
    L.append("\n### Every pair's phi (errors on the 228 clean cases)\n")
    pairs = sorted(o["primary"]["H3"]["pairs"].items(), key=lambda kv: -(kv[1]["phi"] or -9))
    L.append(table(["Pair", "Kind", "phi", "95 % interval"],
                   [[" / ".join(NAMES[x] for x in k.split("|")), "within family" if v["within"] else "cross family",
                     f"{v['phi']:.3f}", f"{v['interval'][0]:.3f} to {v['interval'][1]:.3f}"] for k, v in pairs]))
    L.append("\n### Both wrong on the same case (of the clean cases all seats judged)\n")
    ag = o["agreement"]
    L.append(table(["", *[NAMES[s] for s in seats]],
                   [[NAMES[a], *[ag["pairs"][f"{a}|{b}"]["both_wrong"] for b in seats]] for a in seats]))
    L.append(f"\nn = {ag['n']}; the diagonal is each seat's own count of wrong verdicts.")
    L.append("\n### Every 2-of-3 panel of the seven seats, and the 5-of-7 panel\n")
    rows = sorted(o["panels_2of3"].items(), key=lambda kv: kv[1]["false_pass"]["rate"])
    L.append(table(["Panel", "Bad fixes passed", "Passing-but-wrong passed", "Good fixes failed"],
                   [[" + ".join(NAMES[x] for x in k.split("+")), cell(v["false_pass"]), cell(v["pbw_pass"]),
                     cell(v["false_fail"])] for k, v in rows] +
                   [["**5 of 7, all seats**", cell(o["panel_5of7"]["false_pass"]), cell(o["panel_5of7"]["pbw_pass"]),
                     cell(o["panel_5of7"]["false_fail"])]]))
    L.append("\n### Post hoc: rules on the strongest seats\n")
    L.append(table(["Rule", "Bad fixes passed", "Passing-but-wrong passed", "Good fixes failed"],
                   [[k, cell(v["false_pass"]), cell(v["pbw_pass"]), cell(v["false_fail"])]
                    for k, v in o["post_hoc_rules"].items()]))
    L.append("\n### Calls, tokens and dollars\n")
    stages = sorted({st for s in seats for st in per[s]["stages"]})
    L.append(table(["Seat", "Calls", "Invalid (all calls)", "Failed calls stored", *[f"Stage {st}" for st in stages],
                    "Total"],
                   [[NAMES[s], per[s]["calls"], cell(per[s]["invalid_all"]), per[s]["errors"],
                     *[f"${per[s]['stages'][st]['usd']:.2f}" if st in per[s]["stages"] else "–" for st in stages],
                     f"${per[s]['usd']:.2f}"] for s in seats] +
                   [["**Total**", o["calls"], "", "",
                     *[f"${sum(per[s]['stages'].get(st, {'usd': 0})['usd'] for s in seats):.2f}" for st in stages],
                     f"${o['total_usd']:.2f}"]]))
    L.append(f"\nTokens: {o['total_tokens']:,}. Estimate ${plan['budget']['estimate']}, ceiling "
             f"${plan['budget']['ceiling']}.")
    L.append("\n### The review-list sensitivity analysis\n")
    rv = o["review"]["evaluate"]
    L.append(table(["Case", *[NAMES[s] for s in seats]],
                   [[i, *[("pass" if v.get(s) else "fail") if s in v else "–" for s in seats]]
                    for i, v in o["review"]["verdicts"].items()]))
    L.append(f"\n- H1 unchanged by construction: {rv['H1']['caught']} of {rv['H1']['n']}.")
    L.append(f"- H2: best {rv['H2']['best']}; false passes {rv['H2']['false_passes']}; panel "
             f"{rv['H2']['panel_false_passes']} of {rv['H2']['n']}; p {rv['H2']['p']:.4f}")
    L.append(f"- H3: gap {rv['H3']['gap']:.3f} ({rv['H3']['low']:.3f} to {rv['H3']['high']:.3f}); p {rv['H3']['p']:.4f}")
    L.append("- H4: " + "; ".join(f"{k} {v['difference']:+.3f} ({v['low']:+.3f} to {v['high']:+.3f}), n {v['n']}"
                                  for k, v in rv["H4"]["kinds"].items()))
    L.append(f"- H9: {rv['H9']['rd']:+.3f} ({rv['H9']['low']:+.3f} to {rv['H9']['high']:+.3f}); TOST p {rv['H9']['p']:.4f}")
    L.append("- Holm: " + ", ".join(f"{h} {v['adjusted']:.4f}{' rejected' if v['reject'] else ''}"
                                    for h, v in rv["holm"].items()))
    if "H3_without_failed" in o:
        x = o["H3_without_failed"]
        L.append(f"\n**H3 without the failed seat(s) {o['failed_seats']} (post hoc):** gap {x['gap']:.3f} "
                 f"({x['low']:.3f} to {x['high']:.3f}) on {x['n']} cases, p {x['p']:.4f}.")
    return "\n".join(L)


def main() -> int:
    plan = json.loads(JR.PLAN_V2.read_text(encoding="utf-8"))
    records = JR.load_verdicts(JR.DATA / "verdicts-v2")
    manifests = {"v1": json.loads((JR.DATA / "manifest.json").read_text()),
                 "pbw": json.loads((JR.DATA / "manifest-pbw.json").read_text())}
    o = build(records, plan, manifests)
    (ROOT / "reports" / "judges-v2.json").write_text(
        json.dumps(o, indent=1, sort_keys=True, default=lambda x: list(x)) + "\n", encoding="utf-8")
    print(markdown(o, plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
