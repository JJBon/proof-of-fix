#!/usr/bin/env python3
"""proof-of-fix#241: does a code graph separate good fixes from bad ones? A free test, no model call.

For each of #160's labelled fixes, the code graph of its repository at its base commit is built by parsing only
(graphify, tree-sitter, code-only), the patch's changed functions are placed on it, and a few features fixed in
advance are computed. The report measures how well each feature separates good fixes from bad ones, alone and
among the fixes Opus passed.

    scripts/graph_test.py build    --cases DIR --repos DIR --graphs DIR --graphify BIN   # one graph per commit
    scripts/graph_test.py features --cases DIR --graphs DIR --out data/judges/graph-features.json
    scripts/graph_test.py report   [--features data/judges/graph-features.json]          # prints the tables

The repositories are untrusted (rule 4): `build` only reads them with `git archive` and parses them; nothing in
them is run. graphify runs with an empty environment, so no API key can reach it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data" / "judges" / "verdicts-v2.matrix.json"
CASE_FILES = ("cases.jsonl", "cases-more.jsonl", "cases-pbw.jsonl")
CALLS = ("calls", "indirect_call")
STRUCT = ("calls", "indirect_call", "method", "contains", "inherits", "mixes_in", "imports", "imports_from", "uses",
          "references", "re_exports")
FAR = 9  # a distance when no path exists, or the issue names nothing in the graph
FEATURES = (  # fixed before any result was looked at (#241); the direction is "higher = more likely bad"
    ("n_funcs", "Functions the patch changes"),
    ("n_files", "Files the patch changes (tests aside)"),
    ("lines", "Lines added and removed (no graph: the baseline)"),
    ("touches_tests", "The patch changes a test file"),
    ("callers", "Other functions that call the changed ones (tests aside)"),
    ("callees", "Functions the changed ones call"),
    ("tests_calling", "Test functions that call the changed ones"),
    ("issue_distance", "Steps from the changed code to code the issue names"),
    ("issue_misses", "The issue names code and the patch changes none of it"),
    ("spread", "Largest distance between two changed functions"),
    # added after the first results (post hoc): the baseline above counts test files, which every fix written by
    # the project itself includes and almost no other fix does
    ("lines_code", "Lines added and removed, tests aside (no graph; post hoc)"),
)


def load_cases(cases_dir: Path) -> List[dict]:
    keep = set(json.loads(MATRIX.read_text(encoding="utf-8"))["cases"])
    out = []
    for name in CASE_FILES:
        with open(cases_dir / name, encoding="utf-8") as f:
            out += [c for c in map(json.loads, f) if c["id"] in keep]
    return out


def graph_name(repo: str, commit: str) -> str:
    return f"{repo.replace('/', '__')}-{commit}.json"


# ---------- build ----------

def build_one(repo_dir: Path, commit: str, out: Path, graphify: str, work: Path) -> Tuple[int, int]:
    tree = work / commit
    shutil.rmtree(tree, ignore_errors=True)
    tree.mkdir(parents=True)
    try:
        ar = subprocess.Popen(["git", "-C", str(repo_dir), "archive", commit], stdout=subprocess.PIPE)
        subprocess.run(["tar", "-x", "-C", str(tree)], stdin=ar.stdout, check=True)
        if ar.wait() != 0:
            raise RuntimeError(f"git archive {commit} failed")
        home = work / "home"
        home.mkdir(exist_ok=True)
        subprocess.run([graphify, "extract", str(tree), "--code-only", "--no-cluster"], check=True,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(home)}, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=1800)
        src = tree / "graphify-out" / "graph.json"
        g = json.loads(src.read_text(encoding="utf-8"))
        shutil.copyfile(src, out)
        return len(g["nodes"]), len(g.get("links") or g.get("edges") or [])
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def canon(path: Path) -> str:
    """A hash of the graph's nodes and links, in a fixed order (two builds of one commit should agree)."""
    g = json.loads(path.read_text(encoding="utf-8"))
    nodes = sorted(json.dumps({k: v for k, v in n.items() if k != "community"}, sort_keys=True) for n in g["nodes"])
    links = sorted(json.dumps(e, sort_keys=True) for e in (g.get("links") or g.get("edges") or []))
    return hashlib.sha256("\n".join(nodes + links).encode()).hexdigest()


def cmd_build(a) -> int:
    cases = load_cases(Path(a.cases))
    commits = sorted({(c["repo"], c["base_commit"]) for c in cases})
    graphs, work = Path(a.graphs), Path(a.graphs).parent / "work"
    graphs.mkdir(parents=True, exist_ok=True)
    failed = []
    for i, (repo, commit) in enumerate(commits, 1):
        out = graphs / graph_name(repo, commit)
        if out.exists():
            continue
        try:
            n, e = build_one(Path(a.repos) / repo.split("/")[1], commit, out, a.graphify, work)
            print(f"{i}/{len(commits)} {repo} {commit[:10]}: {n} nodes, {e} links", flush=True)
        except Exception as ex:  # noqa: BLE001 - reported, the run goes on
            failed.append((repo, commit))
            print(f"{i}/{len(commits)} {repo} {commit[:10]}: FAILED {ex}", flush=True)
    rng = random.Random(241)
    again = rng.sample(commits, min(a.repeat, len(commits)))
    same = 0
    for repo, commit in again:
        first = graphs / graph_name(repo, commit)
        if not first.exists():
            continue
        second = work / ("again-" + graph_name(repo, commit))
        build_one(Path(a.repos) / repo.split("/")[1], commit, second, a.graphify, work)
        same += canon(first) == canon(second)
        second.unlink()
    print(f"built {len(commits) - len(failed)} of {len(commits)}; failed: {failed}")
    print(f"rebuilt {len(again)}: {same} identical (nodes and links, community ids aside)")
    return 0


# ---------- the patch on the graph ----------

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def is_test(path: str) -> bool:
    p = path.lower()
    return bool(re.search(r"(^|/)(tests?|testing)(/|$)", p) or re.search(r"(^|/)(test_[^/]*|[^/]*_tests?|conftest)\.py$", p))


def changed_lines(diff: str) -> Dict[str, Set[int]]:
    """{file: lines of the old file the patch touches}: a removed line is its own number; an added line counts at
    the old line it is inserted before. A new file has no old lines and maps to an empty set."""
    out: Dict[str, Set[int]] = {}
    cur: Optional[str] = None
    old = 0
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            cur = None
        elif line.startswith("--- "):
            path = line[4:].strip()
            cur = None if path == "/dev/null" else re.sub(r"^a/", "", path)
            if cur is not None:
                out.setdefault(cur, set())
        elif line.startswith("+++ "):
            path = line[4:].strip()
            if cur is None and path != "/dev/null":
                out.setdefault(re.sub(r"^b/", "", path), set())
        elif cur is not None:
            m = HUNK.match(line)
            if m:
                old = int(m.group(1))
            elif line.startswith("-"):
                out[cur].add(old)
                old += 1
            elif line.startswith("+"):
                out[cur].add(old)
            elif line.startswith(" "):
                old += 1
    return out


def diff_size(diff: str, tests: bool = True) -> int:
    n, cur = 0, ""
    for ln in diff.splitlines():
        if ln.startswith("diff --git "):
            cur = ln.split(" b/")[-1]
        elif (ln.startswith("+") or ln.startswith("-")) and not ln.startswith(("+++", "---")):
            n += tests or not is_test(cur)
    return n


class Graph:
    def __init__(self, path: Path):
        g = json.loads(path.read_text(encoding="utf-8"))
        self.nodes = {n["id"]: n for n in g["nodes"]}
        self.links = g.get("links") or g.get("edges") or []
        self.by_file: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
        for n in g["nodes"]:
            loc = n.get("source_location") or ""
            if n.get("_callable") and n.get("source_file") and loc.startswith("L") and loc[1:].isdigit():
                self.by_file[n["source_file"]].append((int(loc[1:]), n["id"]))
        for v in self.by_file.values():
            v.sort()
        self.callers: Dict[str, Set[str]] = defaultdict(set)
        self.callees: Dict[str, Set[str]] = defaultdict(set)
        self.adj: Dict[str, Set[str]] = defaultdict(set)
        self.guessed = 0
        for e in self.links:
            s, t, rel = e.get("source"), e.get("target"), e.get("relation")
            if s not in self.nodes or t not in self.nodes or rel not in STRUCT:
                continue
            self.adj[s].add(t)
            self.adj[t].add(s)
            if rel in CALLS:
                self.callers[t].add(s)
                self.callees[s].add(t)
                self.guessed += e.get("confidence") != "EXTRACTED"
        self.names: Dict[str, Set[str]] = defaultdict(set)
        for n in g["nodes"]:
            if n.get("file_type") == "code" and n.get("source_file") and not is_test(n["source_file"]):
                name = re.sub(r"[^A-Za-z0-9_]", "", n.get("label") or "")
                if len(name) >= 4:
                    self.names[name].add(n["id"])

    def owner(self, path: str, line: int) -> Optional[str]:
        """The function or class that starts last at or before `line` (graphify gives no end line)."""
        best = None
        for start, nid in self.by_file.get(path, ()):
            if start > line:
                break
            best = nid
        return best

    def test_node(self, nid: str) -> bool:
        return is_test(self.nodes[nid].get("source_file") or "")

    def distance(self, sources: Iterable[str], targets: Set[str], limit: int = FAR) -> int:
        seen = set(sources)
        if seen & targets:
            return 0
        q = deque((s, 0) for s in seen)
        while q:
            n, d = q.popleft()
            if d + 1 >= limit:
                continue
            for m in self.adj.get(n, ()):
                if m in targets:
                    return d + 1
                if m not in seen:
                    seen.add(m)
                    q.append((m, d + 1))
        return limit


def issue_names(g: Graph, issue: str) -> Set[str]:
    """Nodes whose name the issue's text uses as a word (four characters or more, an identifier)."""
    out: Set[str] = set()
    for word in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", issue)):
        if word in g.names and (("_" in word) or (word != word.lower() and word != word.capitalize())
                                or f"{word}(" in issue or f"`{word}`" in issue or f".{word}" in issue):
            out |= g.names[word]
    return out


def features(case: dict, g: Graph) -> Dict[str, float]:
    lines = changed_lines(case["diff"])
    code = {f: ls for f, ls in lines.items() if not is_test(f)}
    changed: Set[str] = set()
    for f, ls in code.items():
        for ln in ls:
            o = g.owner(f, ln)
            if o:
                changed.add(o)
    callers = {c for n in changed for c in g.callers.get(n, ()) if c not in changed}
    callees = {c for n in changed for c in g.callees.get(n, ()) if c not in changed}
    named = issue_names(g, case["issue"])
    dist = g.distance(changed, named) if changed and named else FAR
    spread = 0
    ch = sorted(changed)
    for i, x in enumerate(ch[:6]):
        for y in ch[i + 1:6]:
            spread = max(spread, g.distance([x], {y}))
    return {
        "n_funcs": len(changed), "n_files": len(code), "lines": diff_size(case["diff"]),
        "lines_code": diff_size(case["diff"], tests=False),
        "touches_tests": int(any(is_test(f) for f in lines)),
        "callers": sum(1 for c in callers if not g.test_node(c)),
        "callees": len(callees),
        "tests_calling": sum(1 for c in callers if g.test_node(c)),
        "issue_distance": dist, "issue_misses": int(bool(named) and dist > 0), "spread": spread,
        "_placed": int(bool(changed)), "_named": len(named), "_new_files": sum(1 for ls in code.values() if not ls),
    }


def cmd_features(a) -> int:
    cases = load_cases(Path(a.cases))
    votes = json.loads(MATRIX.read_text(encoding="utf-8"))["cases"]
    out, cache = {}, {}
    missing = 0
    for c in cases:
        path = Path(a.graphs) / graph_name(c["repo"], c["base_commit"])
        if not path.exists():
            missing += 1
            continue
        if path not in cache:
            cache.clear()  # one graph in memory at a time (cases are grouped by commit only loosely)
            cache[path] = Graph(path)
        g = cache[path]
        v = votes[c["id"]]
        out[c["id"]] = {"label": c["label"], "arm": v["arm"], "repo": c["repo"],
                        "gold": c.get("source") == "gold", "opus": v["votes"].get("anthropic"),
                        "calls_guessed": round(g.guessed / max(1, sum(len(x) for x in g.callers.values())), 3),
                        **features(c, g)}
    Path(a.out).write_text(json.dumps({"about": "proof-of-fix#241: features of each of #160's fixes on its code "
                                                "graph (scripts/graph_test.py); no issue or patch text",
                                       "cases": out}, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(out)} cases written, {missing} without a graph")
    return 0


# ---------- the report ----------

def auc(bad: Sequence[float], good: Sequence[float]) -> float:
    """The chance a bad fix scores higher than a good one (ties count half): 0.5 is chance."""
    if not bad or not good:
        return float("nan")
    wins = sum((b > x) + 0.5 * (b == x) for b in bad for x in good)
    return wins / (len(bad) * len(good))


def auc_ci(bad: Sequence[float], good: Sequence[float], n: int = 2000, seed: int = 241) -> Tuple[float, float]:
    rng = random.Random(seed)
    xs = sorted(auc([rng.choice(bad) for _ in bad], [rng.choice(good) for _ in good]) for _ in range(n))
    return xs[int(0.025 * n)], xs[int(0.975 * n) - 1]


def flag_rule(bad: Sequence[float], good: Sequence[float], budget: float = 0.10) -> Tuple[float, int, int, int]:
    """The best one-sided rule on one feature that flags at most `budget` of the good fixes: (threshold, side,
    bad flagged, good flagged); side +1 flags values at or above the threshold, -1 at or below. Chosen on the same
    cases it is scored on, so it is optimistic."""
    best = (float("nan"), 1, 0, 0)
    for side in (1, -1):
        for t in sorted(set(bad) | set(good)):
            fb = sum(1 for x in bad if (x >= t if side > 0 else x <= t))
            fg = sum(1 for x in good if (x >= t if side > 0 else x <= t))
            if fg <= budget * len(good) and (fb, -fg) > (best[2], -best[3]):
                best = (t, side, fb, fg)
    return best


def _fmt(bad, good) -> str:
    a = auc(bad, good)
    lo, hi = auc_ci(bad, good)
    star = " *" if (lo > 0.5 or hi < 0.5) else ""
    return f"{a:.2f} ({lo:.2f}–{hi:.2f}){star}"


def cmd_report(a) -> int:
    cases = json.loads(Path(a.features).read_text(encoding="utf-8"))["cases"]
    rows = list(cases.values())
    good = [r for r in rows if r["label"] == "good"]
    hidden = [r for r in rows if r["label"] != "good" and r["arm"] != "pbw"]
    pbw = [r for r in rows if r["arm"] == "pbw"]
    placed = sum(r["_placed"] for r in rows)
    print(f"Cases: {len(good)} good ({sum(r['gold'] for r in good)} the project's own, "
          f"{sum(not r['gold'] for r in good)} written by a model), {len(hidden)} bad that fail the tests, "
          f"{len(pbw)} bad that pass them. The patch was placed on the graph in {placed} of {len(rows)}; "
          f"the issue names code in {sum(1 for r in rows if r['_named'])}. "
          f"Call links guessed, not read: {100 * sum(r['calls_guessed'] for r in rows) / len(rows):.0f} % on average.\n")
    print("### How well each feature separates (0.50 is chance; above it, higher values mean bad; "
          "95 % interval by bootstrap; * excludes chance)\n")
    print("| Feature | Bad (fail the tests) vs good | Bad (pass the tests) vs good | "
          "Good by a model vs good by the project (authorship) |")
    print("|---|---|---|---|")
    for key, name in FEATURES:
        g = [r[key] for r in good]
        print(f"| {name} | {_fmt([r[key] for r in hidden], g)} | {_fmt([r[key] for r in pbw], g)} | "
              f"{_fmt([r[key] for r in good if not r['gold']], [r[key] for r in good if r['gold']])} |")
    print("\n### Medians\n")
    print("| Feature | Good | Bad (fail the tests) | Bad (pass the tests) |")
    print("|---|---|---|---|")
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else float("nan")  # noqa: E731
    for key, name in FEATURES:
        print(f"| {name} | {med([r[key] for r in good])} | {med([r[key] for r in hidden])} | "
              f"{med([r[key] for r in pbw])} |")
    og = [r for r in good if r["opus"] == 1]
    print(f"\n### Among the fixes Opus passed ({len(og)} good; the best rule on one feature that flags at most "
          "10 % of those good fixes; chosen on these cases, so optimistic)\n")
    print("| Feature | Bad that fail the tests, passed by Opus: flagged | Bad that pass the tests, passed by Opus: "
          "flagged | Rule (first / second) | Good flagged (first / second) |")
    print("|---|---|---|---|---|")
    for key, name in FEATURES:
        cells, rules, gf = [], [], []
        for pool in (hidden, pbw):
            ob = [r for r in pool if r["opus"] == 1]
            t, side, fb, fg = flag_rule([r[key] for r in ob], [r[key] for r in og])
            cells.append(f"{fb} of {len(ob)}")
            rules.append("none" if fb == 0 else f"{'≥' if side > 0 else '≤'} {t:g}")
            gf.append(f"{fg} of {len(og)}")
        print(f"| {name} | {cells[0]} | {cells[1]} | {' / '.join(rules)} | {' / '.join(gf)} |")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/graph_test.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--cases", required=True)
    b.add_argument("--repos", required=True)
    b.add_argument("--graphs", required=True)
    b.add_argument("--graphify", required=True)
    b.add_argument("--repeat", type=int, default=10)
    f = sub.add_parser("features")
    f.add_argument("--cases", required=True)
    f.add_argument("--graphs", required=True)
    f.add_argument("--out", default=str(ROOT / "data" / "judges" / "graph-features.json"))
    r = sub.add_parser("report")
    r.add_argument("--features", default=str(ROOT / "data" / "judges" / "graph-features.json"))
    a = ap.parse_args(argv)
    return {"build": cmd_build, "features": cmd_features, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
