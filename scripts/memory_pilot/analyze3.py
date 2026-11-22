"""Three-way comparison: baseline, curated notes, judge-written notes. Usage: analyze3.py <journal of arm 3>"""
import json, sys, collections
from pathlib import Path
from math import comb
OUT = Path.home() / ".cache/pof-graph/pilot"
key2 = json.loads((OUT / "key2.json").read_text()); key3 = json.loads((OUT / "key3.json").read_text())
v2 = json.loads((OUT / "verdicts-pilot.json").read_text()); v3 = {}
def walk(o):
    if isinstance(o, dict):
        if isinstance(o.get("id"), str) and isinstance(o.get("solves"), bool) and o["id"] in key3: v3[o["id"]] = o
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
    elif isinstance(o, str) and o.startswith("{") and '"solves"' in o:
        try: walk(json.loads(o))
        except ValueError: pass
for l in open(sys.argv[1], errors="replace"):
    try: walk(json.loads(l))
    except ValueError: pass
(OUT / "verdicts-pilot3.json").write_text(json.dumps(v3, indent=1)); print("verdicts", len(v3), "of", len(key3))
by = collections.defaultdict(dict); meta = {}
for p, k in key2.items():
    if p in v2: by[k["case"]][k["arm"]] = v2[p]; meta[k["case"]] = k
for p, k in key3.items():
    if p in v3: by[k["case"]]["opus"] = v3[p]
def sign(b, c):
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n)
def row(name, cs):
    cs = [c for c in cs if len(by[c]) == 3]
    if not cs: return
    P = lambda a: sum(by[c][a]["solves"] for c in cs)
    d = lambda a, b: (sum(by[c][a]["solves"] and not by[c][b]["solves"] for c in cs), sum(not by[c][a]["solves"] and by[c][b]["solves"] for c in cs))
    bo, cm = d("base", "opus"), d("memory", "opus")
    pr = lambda a: sum(by[c][a]["probability"] for c in cs) / len(cs)
    print(f"{name:36} n={len(cs):3} passes: base {P('base'):3} curated {P('memory'):3} judge-notes {P('opus'):3} | base->judge-notes: to fail {bo[0]}, to pass {bo[1]}, p={sign(*bo):.3f} | curated->judge-notes: to fail {cm[0]}, to pass {cm[1]}, p={sign(*cm):.3f} | prob {pr('base'):.2f}/{pr('memory'):.2f}/{pr('opus'):.2f}")
cases = sorted(by)
for g in ("false_pass", "true_reject", "good"):
    G = [c for c in cases if meta[c]["group"] == g]; row(g, G)
    row(f"  {g}: same-issue note", [c for c in G if "same_issue" in meta[c]["kinds"]])
    row(f"  {g}: same-file only", [c for c in G if "same_issue" not in meta[c]["kinds"]])
    row(f"  {g}: pool pbw", [c for c in G if meta[c]["pool"] == "pbw"])
row("all bad fixes", [c for c in cases if meta[c]["label"] == "bad"])
both = [c for c in cases if meta[c]["group"] == "false_pass" and len(by[c]) == 3]
print("false passes caught by curated only:", sum(not by[c]["memory"]["solves"] and by[c]["opus"]["solves"] for c in both),
      "by judge-notes only:", sum(by[c]["memory"]["solves"] and not by[c]["opus"]["solves"] for c in both),
      "by both:", sum(not by[c]["memory"]["solves"] and not by[c]["opus"]["solves"] for c in both))
