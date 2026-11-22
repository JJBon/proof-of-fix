"""Pilot analysis (exploratory): baseline vs failure-memory verdicts, paired per case. Usage: analyze.py <journal>"""
import json, sys, re, collections
from pathlib import Path
from math import comb
OUT = Path.home() / ".cache/pof-graph/pilot"
key = json.loads((OUT / "key2.json").read_text()); res = {}
def walk(o):
    if isinstance(o, dict):
        if isinstance(o.get("id"), str) and isinstance(o.get("solves"), bool) and o["id"] in key: res[o["id"]] = o
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
    elif isinstance(o, str) and o.startswith("{") and '"solves"' in o:
        try: walk(json.loads(o))
        except ValueError: pass
for l in open(sys.argv[1], errors="replace"):
    try: walk(json.loads(l))
    except ValueError: pass
(OUT / "verdicts-pilot.json").write_text(json.dumps(res, indent=1))
print("verdicts", len(res), "of", len(key))
by = collections.defaultdict(dict)
for pid, k in key.items():
    if pid in res: by[k["case"]][k["arm"]] = res[pid]
meta = {k["case"]: k for k in key.values()}
def sign(b, c):  # exact two-sided sign test on the discordant pairs
    n = b + c
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(0, min(b, c) + 1)) / 2 ** n)
def row(name, cs):
    cs = [c for c in cs if len(by[c]) == 2]
    if not cs: return
    b0 = sum(by[c]["base"]["solves"] for c in cs); m0 = sum(by[c]["memory"]["solves"] for c in cs)
    p2f = sum(by[c]["base"]["solves"] and not by[c]["memory"]["solves"] for c in cs)
    f2p = sum(not by[c]["base"]["solves"] and by[c]["memory"]["solves"] for c in cs)
    pb = sum(by[c]["base"]["probability"] for c in cs) / len(cs); pm = sum(by[c]["memory"]["probability"] for c in cs) / len(cs)
    print(f"{name:44} n={len(cs):3}  passes base {b0:3}  memory {m0:3}  pass->fail {p2f:2}  fail->pass {f2p:2}  sign p={sign(p2f, f2p):.3f}  mean prob {pb:.2f} -> {pm:.2f}")
cases = sorted(by)
for g in ("false_pass", "true_reject", "good"):
    G = [c for c in cases if meta[c]["group"] == g]
    row(g, G)
    row(f"  {g}: note on the same issue", [c for c in G if "same_issue" in meta[c]["kinds"]])
    row(f"  {g}: same-file notes only", [c for c in G if "same_issue" not in meta[c]["kinds"]])
    row(f"  {g}: a test-backed note", [c for c in G if "tests" in meta[c]["evidence"]])
    row(f"  {g}: no test-backed note", [c for c in G if "tests" not in meta[c]["evidence"]])
    for pool in ("v1", "more", "pbw"):
        row(f"  {g}: pool {pool}", [c for c in G if meta[c]["pool"] == pool])
bad = [c for c in cases if meta[c]["label"] == "bad"]; row("all bad fixes", bad)
