"""Freeze the memory run's inputs (#241): the notes and, per case, which notes it reads.
Needs the local case files, the clones and the pilot's note journals; writes data/judges/memory-v1/."""
import json, random, re, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import graph_test as GT  # noqa: E402
HOME = Path.home() / ".cache/pof-graph"; PILOT = HOME / "pilot"
OUT = ROOT / "data" / "judges" / "memory-v1"


def main(journal: str) -> None:
    cases = {c["id"]: c for c in GT.load_cases(Path.home() / "dev/proof-of-fix-wt-prereg/data/judges")}
    p = json.loads((PILOT / "plan-v3.json").read_text()); plan, nid = p["plan"], p["nid"]
    notes = json.loads((ROOT / "data/judges/memory-pilot/notes-opus.json").read_text())
    for line in open(journal, errors="replace"):
        for m in re.finditer(r'\{[^{}]*"note"[^{}]*\}', line):
            try:
                o = json.loads(m.group(0))
            except ValueError:
                try:
                    o = json.loads(json.loads('"' + m.group(0) + '"'))
                except ValueError:
                    continue
            if re.fullmatch(r"[0-9a-f]{10}", str(o.get("id", ""))) and isinstance(o.get("note"), str):
                notes.setdefault(o["id"], o["note"].strip())
    need = {nid[i] for pick in plan.values() for i, _ in pick}
    missing = sorted(need - set(notes))
    if missing:
        raise SystemExit(f"notes missing: {missing}")
    when = {}
    for c in cases.values():
        k = (c["repo"], c["base_commit"])
        if k not in when:
            r = subprocess.run(["git", "-C", str(HOME / "repos" / c["repo"].split("/")[1]), "show", "-s", "--format=%ct",
                                c["base_commit"]], capture_output=True, text=True)
            when[k] = int(r.stdout.strip() or 0)
    t = lambda i: when[(cases[i]["repo"], cases[i]["base_commit"])]  # noqa: E731
    used = sorted({i for pick in plan.values() for i, _ in pick})
    other = {}
    for cid in sorted(plan):
        c = cases[cid]
        if c["label"] != "good":
            continue
        pick = [i for i, k in plan[cid] if k == "same_file"]
        rest = sorted((i for i in used if cases[i]["repo"] == c["repo"] and cases[i]["instance"] != c["instance"]
                       and i not in pick), key=lambda i: (t(i) >= t(cid), abs(t(i) - t(cid)), i))
        other[cid] = [[i, "other_issue", nid[i]] for i in (pick + rest)[:2]]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "notes.json").write_text(json.dumps({k: notes[k] for k in sorted(need)}, indent=1, sort_keys=True) + "\n")
    drift = sorted(random.Random(243).sample(sorted(plan), 30))
    (OUT / "set.json").write_text(json.dumps({
        "memory": {c: [[i, k, nid[i]] for i, k in plan[c]] for c in sorted(plan)}, "other": other, "drift": drift,
        "label": {c: cases[c]["label"] for c in sorted(plan)},
    }, indent=1, sort_keys=True) + "\n")
    print(len(plan), "cases;", len(need), "notes;", len(other), "other-issue;", sum(1 for v in other.values() if not v), "empty")


if __name__ == "__main__":
    main(sys.argv[1])
