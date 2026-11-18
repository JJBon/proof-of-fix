import json, os, subprocess, sys, collections
from pathlib import Path
WT = Path.home() / "dev/proof-of-fix"
sys.path.insert(0, str(WT)); sys.path.insert(0, str(WT / "scripts"))
import graph_test as GT
HOME = Path.home() / ".cache/pof-graph"; CD = Path.home() / "dev/proof-of-fix-wt-prereg/data/judges"
cases = {c["id"]: c for c in GT.load_cases(CD)}
date = {}
def when(c):
    k = (c["repo"], c["base_commit"])
    if k not in date:
        r = subprocess.run(["git", "-C", str(HOME/"repos"/c["repo"].split("/")[1]), "show", "-s", "--format=%ct", c["base_commit"]], capture_output=True, text=True)
        date[k] = int(r.stdout.strip() or 0)
    return date[k]
files = {i: {f for f in GT.changed_lines(c["diff"]) if not GT.is_test(f)} for i, c in cases.items()}
plan, used = {}, set()
for cid, c in cases.items():
    same = sorted(i for i, x in cases.items() if x["label"] == "bad" and x["instance"] == c["instance"] and i < cid)
    other = sorted((i for i, x in cases.items() if x["label"] == "bad" and x["repo"] == c["repo"] and x["instance"] != c["instance"]
                    and when(x) < when(c) and files[i] & files[cid]), key=lambda i: -when(cases[i]))
    pick = [(i, "same_issue") for i in same[:2]]; pick += [(i, "same_file") for i in other[:3 - len(pick)]]
    if pick: plan[cid] = pick; used |= {i for i, _ in pick}
old = json.loads((HOME / "pilot/notes-plan.json").read_text())["nid"]
lab = collections.Counter(cases[c]["label"] for c in plan)
print("cases with history", len(plan), dict(lab), "| notes needed", len(used), "already written", len(used & set(old)), "missing", len(used - set(old)))
good_other = sum(1 for c in plan if cases[c]["label"] == "good" and any(k == "same_file" for _, k in plan[c]))
print("good fixes with a same-file other-issue note:", good_other)
tot = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0])
for f in sorted(os.listdir(CD / "verdicts-v2")):
    if not f.endswith(".jsonl"): continue
    for l in open(CD / "verdicts-v2" / f):
        r = json.loads(l)
        if r.get("case") in plan and str(r.get("stage")) != "0":
            t = tot[r["seat"]]; t[0] += 1; t[1] += (r.get("worst") or [0, 0])[1]
            u = r.get("usage") or {}; t[2] += u.get("input_tokens") or u.get("prompt_tokens") or 0; t[3] += u.get("output_tokens") or u.get("completion_tokens") or 0
real = {"anthropic": 22.68/378, "openai": 6.71/378, "google": 9.23/378, "deepseek": 3.44/378, "qwen": 4.04/378, "mistral": 1.47/378, "nvidia": 0.46/378, "google-gemma": 0.38/228, "openai-oss": 0.39/228}
print("seat           records  worst$  in_tok  out_tok  expected$(avg/call x n x1.1)")
for s, t in tot.items():
    print(f"{s:14} {t[0]:5} {t[1]:8.2f} {t[2]:8} {t[3]:7}  {real.get(s, 0) * len(plan) * 1.1:6.2f}")
json.dump({"plan": plan}, open(HOME / "pilot/plan-v3.json", "w"))
