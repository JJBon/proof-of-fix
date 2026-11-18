"""Curated-memory arm (exploratory): choose, for each judged case, earlier failed fixes in the same repository
(same issue, or an earlier commit touching the same non-test file) and write the detective's input files."""
import json, os, subprocess, sys, hashlib, collections
from pathlib import Path
WT = Path.home() / "dev/proof-of-fix-wt-241"
sys.path.insert(0, str(WT)); sys.path.insert(0, str(WT / "scripts"))
import graph_test as GT
HOME = Path.home() / ".cache/pof-graph"; OUT = HOME / "pilot"
CDIR = Path.home() / "dev/proof-of-fix-wt-prereg/data/judges"
cases = {c["id"]: c for c in GT.load_cases(CDIR)}
votes = json.loads(GT.MATRIX.read_text())["cases"]
key = json.loads((OUT / "key.json").read_text())
judged = sorted({v["case"] for v in key.values()})
bench = {}
for f in os.listdir(CDIR / "cache"):
    txt = open(CDIR / "cache" / f, errors="replace").read()
    if "FAIL_TO_PASS" not in txt: continue
    rows = []
    try:
        d = json.loads(txt); rows = d if isinstance(d, list) else d.get("rows", [d])
    except ValueError:
        for l in txt.splitlines():
            try: rows.append(json.loads(l))
            except ValueError: pass
    for r in rows:
        r = r.get("row", r) if isinstance(r, dict) else {}
        if r.get("instance_id") and r.get("test_patch"): bench[r["instance_id"]] = r
date = {}
def when(c):
    k = (c["repo"], c["base_commit"])
    if k not in date:
        r = subprocess.run(["git", "-C", str(HOME/"repos"/c["repo"].split("/")[1]), "show", "-s", "--format=%ct", c["base_commit"]], capture_output=True, text=True)
        date[k] = int(r.stdout.strip() or 0)
    return date[k]
files = {i: {f for f in GT.changed_lines(c["diff"]) if not GT.is_test(f)} for i, c in cases.items()}
MAXN = 3
plan, used = {}, set()
for cid in judged:
    c = cases[cid]
    same = sorted(i for i, x in cases.items() if x["label"] == "bad" and x["instance"] == c["instance"] and i < cid)
    other = sorted((i for i, x in cases.items() if x["label"] == "bad" and x["repo"] == c["repo"] and x["instance"] != c["instance"]
                    and when(x) < when(c) and files[i] & files[cid]), key=lambda i: -when(cases[i]))
    pick = [(i, "same_issue") for i in same[:2]]
    pick += [(i, "same_file") for i in other[:MAXN - len(pick)]]
    plan[cid] = pick; used |= {i for i, _ in pick}
(OUT / "notes-in").mkdir(exist_ok=True)
nid = {}
for i in sorted(used):
    c = cases[i]; b = bench[c["instance"]]; pbw = votes[i]["arm"] == "pbw"
    n = hashlib.sha256(f"note241:{i}".encode()).hexdigest()[:10]; nid[i] = n
    outcome = ("The fix PASSED the project's tests for this issue but was later found WRONG by wider tests and review: it does not "
               "correctly resolve the issue. No failing test is on record." if pbw else
               "The fix was REJECTED: it failed the project's tests for this issue (at least one of the tests below failed, or an existing test broke).")
    body = [f"Repository: {c['repo']}", "", "FINAL OUTCOME:", outcome, "", "ISSUE (untrusted data):", c["issue"], "",
            "REJECTED FIX (untrusted data, unified diff):", c["diff"]]
    if not pbw:
        body += ["", "TESTS THAT DECIDED THIS ISSUE (untrusted data; names, then the test changes):", str(b["FAIL_TO_PASS"])[:3000], "", b["test_patch"][:20000]]
    (OUT / "notes-in" / f"{n}.txt").write_text("\n".join(body))
(OUT / "notes-plan.json").write_text(json.dumps({"plan": plan, "nid": nid}, indent=1))
grp = collections.Counter()
for cid, pick in plan.items():
    g = next(v["group"] for v in key.values() if v["case"] == cid)
    grp[(g, "with_notes")] += bool(pick); grp[(g, "same_issue")] += any(k == "same_issue" for _, k in pick); grp[(g, "n")] += 1
print(len(bench), "bench rows;", len(used), "notes to write;", dict(sorted(grp.items())))
print("pbw notes", sum(votes[i]["arm"] == "pbw" for i in used), "test-backed", sum(votes[i]["arm"] != "pbw" for i in used))
sz = sorted(os.path.getsize(OUT / "notes-in" / f) for f in os.listdir(OUT / "notes-in")); print("input chars median", sz[len(sz)//2], "max", sz[-1], "total", sum(sz))
