"""Builds B1's labelled set of real fixes (proof-of-fix#85 task 2.1) from public data, reading only: no account, no
key, nothing written anywhere but data/judges/. Run it through scripts/judge-set.sh, which runs it in a pinned
container (rule 4: upstream code is untrusted; here it is only read as text, never run).

    select        choose the pairs and write data/judges/manifest.json (done once; the manifest is committed)
    build         rebuild data/judges/cases.jsonl from the manifest, checking every patch's hash and the label counts;
                  --set more|pbw rebuilds #160's sets (cases-more.jsonl, cases-pbw.jsonl) the same way
    select-more   #160: 50 more pairs by v1's rules, seed 160, from the issues v1 didn't use (manifest-more.json)
    select-pbw    #160: the passing-but-wrong arm from Wang, Pradel and Liu's published verdicts (manifest-pbw.json);
                  needs their replication package's PatchDiff/ folder, mounted read-only (POF_PATCHDIFF_DIR)
    coverage      #160: what those verdicts and UTBoost's data say about every hidden-test-labelled case, and which
                  a person should review (ground-truth.json); needs POF_PATCHDIFF_DIR too

Sources, pinned:
- SWE-bench Verified (princeton-nlp/SWE-bench_Verified on Hugging Face, revision below): the issues, base commits,
  gold patches and their tests; the dataset server's rows API serves it as JSON.
- SWE-bench's experiments (github.com/SWE-bench/experiments at the commit below): each submission's per-instance
  outcome under the benchmark's hidden tests. Their patches and reports are in the public bucket
  swe-bench-submissions, read anonymously over HTTPS.
- The base files around each change, from raw.githubusercontent.com at the base commit.
People's data (rule 5): no author is read or stored; issue texts are scrubbed of e-mails, @mentions and profile links,
and hints (comments by people) are dropped.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pof.judges import dataset as D  # noqa: E402
from pof.judges import pbw as PBW  # noqa: E402

DATASET = "princeton-nlp/SWE-bench_Verified"
DATASET_REVISION = "c104f840cc67f8b6eec6f759ebc8b2693d585d4a"  # 2025-02-18
EXPERIMENTS_COMMIT = "40f164d5b8f1d249bf95a6df8b74b577fd8e519d"  # 2026-09-03
BUCKET = "https://swe-bench-submissions.s3.amazonaws.com"
# Four strong agents from four model families, same scaffold (mini-SWE-agent), so their failures are plausible fixes.
RUNS = {
    "20251124_mini-v1.16.0_claude-opus-4-5-20251101": {"family": "anthropic", "model": "Claude Opus 4.5"},
    "20251211_mini-v1.17.2_gpt-5.2-2025-12-11-high": {"family": "openai", "model": "GPT-5.2 (high)"},
    "20251118_mini-v1.15.0_gemini-3-pro-preview-20251118": {"family": "google", "model": "Gemini 3 Pro Preview"},
    "20251201_mini-v1.17.1_deepseek-v3.2-reasoner": {"family": "deepseek", "model": "DeepSeek V3.2 Reasoner"},
}
USER_AGENT = "research-client"  # generic: no project name in outside requests (owner's rule, #160)
COMMIT_MESSAGE = "Fix the issue described above."  # the same for every case; the injections add to it
PAIRS, SEED = 50, 85

DATA = ROOT / "data" / "judges"
CACHE = DATA / "cache"


def fetch(url: str, cache: bool = True) -> bytes:
    """GET a public URL, anonymously, through a local cache so a rebuild doesn't hit the sources twice."""
    key = CACHE / D.sha256(url)
    if cache and key.exists():
        return key.read_bytes()
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            time.sleep(2 ** attempt)
        except urllib.error.URLError:
            time.sleep(2 ** attempt)
    else:
        raise RuntimeError(f"could not fetch {url}")
    CACHE.mkdir(parents=True, exist_ok=True)
    key.write_bytes(body)
    return body


def verified_rows() -> dict[str, dict]:
    info = json.loads(fetch(f"https://huggingface.co/api/datasets/{DATASET}", cache=False))
    if info["sha"] != DATASET_REVISION:
        raise SystemExit(f"{DATASET} moved to {info['sha']}; pinned {DATASET_REVISION}")
    rows = {}
    for offset in range(0, 500, 100):
        url = (f"https://datasets-server.huggingface.co/rows?dataset={DATASET}&config=default&split=test"
               f"&offset={offset}&length=100")
        for r in json.loads(fetch(url))["rows"]:
            rows[r["row"]["instance_id"]] = r["row"]
    return rows


def outcomes(run: str) -> dict[str, bool]:
    url = (f"https://raw.githubusercontent.com/SWE-bench/experiments/{EXPERIMENTS_COMMIT}/evaluation/verified/"
           f"{run}/per_instance_details.json")
    return {iid: bool(v.get("resolved")) for iid, v in json.loads(fetch(url)).items()}


def agent_patch(run: str, iid: str) -> tuple[str, dict]:
    """A run's patch and its hidden-test report for one issue; ("", {}) when the run left none."""
    base = f"{BUCKET}/bash-only/{run}/logs/{iid}"
    try:
        patch = fetch(f"{base}/patch.diff").decode("utf-8", "replace")
        report = json.loads(fetch(f"{base}/report.json"))
        report = report.get(iid, report)  # some submissions key the report by instance, others don't
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):  # the bucket answers 403 for a missing key
            return "", {}
        raise
    return patch, report


def licence(repo: str) -> str:
    try:
        return json.loads(fetch(f"https://api.github.com/repos/{repo}/license"))["license"]["spdx_id"]
    except (urllib.error.HTTPError, KeyError):
        return "NOASSERTION"


def gold_diff(row: dict) -> str:
    return row["patch"].rstrip("\n") + "\n" + row["test_patch"]


def context(repo: str, commit: str, diff: str) -> list[dict]:
    """The base version of each changed file, 40 lines around each hunk."""
    out = []
    for path, spans in D.hunks(diff).items():
        try:
            text = fetch(f"https://raw.githubusercontent.com/{repo}/{commit}/{path}").decode("utf-8", "replace")
        except urllib.error.HTTPError:
            continue
        out.append({"path": path, "text": D.excerpt(text, D.windows(spans, len(text.splitlines())))})
    return out


def choose_pairs(rows: dict, results: dict, candidates: list, pairs: int, seed: int,
                 already: dict[str, int] | None = None, per_repo: int = 12) -> tuple[list[dict], set[str]]:
    """The seeded pairs and their cases; an issue whose chosen failing patch is empty, didn't apply or wasn't a
    failure is excluded and the selection redrawn without it, until every pair holds."""
    excluded: set[str] = set()
    while True:
        plans = D.select([c for c in candidates if c.instance not in excluded], tuple(RUNS), pairs, seed,
                         per_repo=per_repo, already=already)
        cases, bad_plans = [], []
        for p in plans:
            row = rows[p["instance"]]
            patch, report = agent_patch(p["bad_run"], p["instance"])
            if not patch.strip() or not report.get("patch_successfully_applied") or report.get("resolved"):
                bad_plans.append(p["instance"])
                continue
            good_source, good = p["good"], None
            if good_source != "gold":
                gpatch, greport = agent_patch(good_source, p["instance"])
                if gpatch.strip() and greport.get("resolved"):
                    good = gpatch
                else:
                    good_source = "gold"
            if good is None:
                good = gold_diff(row)
            for label, source, diff in (("good", good_source, good), ("bad", p["bad_run"], patch)):
                n = D.changed_lines(diff)
                cases.append({"id": f"{p['instance']}:{label}", "instance": p["instance"], "repo": row["repo"],
                              "base_commit": row["base_commit"], "label": label, "source": source,
                              "solver_family": "human" if source == "gold" else RUNS[source]["family"],
                              "patch_sha256": D.sha256(diff), "changed_lines": n, "size": D.size_class(n),
                              "difficulty": row.get("difficulty"), "issue_sha256": D.sha256(row["problem_statement"])})
        if not bad_plans:
            return cases, excluded
        excluded.update(bad_plans)


def candidates_from(rows: dict, results: dict) -> list:
    out = []
    for iid, row in rows.items():
        failed = tuple(r for r in RUNS if results[r].get(iid) is False)
        resolved = tuple(r for r in RUNS if results[r].get(iid) is True)
        out.append(D.Candidate(iid, row["repo"], D.changed_lines(row["patch"]), resolved, failed))
    return out


def sources() -> dict:
    return {"dataset": f"huggingface.co/datasets/{DATASET}", "dataset_revision": DATASET_REVISION,
            "dataset_licence": "no licence stated on the dataset card; SWE-bench's code is MIT, and each "
                               "issue and patch is its repository's, under that repository's licence",
            "experiments": "github.com/SWE-bench/experiments", "experiments_commit": EXPERIMENTS_COMMIT,
            "agent_patches": f"{BUCKET}/bash-only/<run>/logs/<instance>/patch.diff",
            "agent_patches_licence": "no licence stated: read for measurement, not redistributed (this "
                                     "repository stores only their hashes)"}


def select(_args) -> int:
    rows = verified_rows()
    results = {run: outcomes(run) for run in RUNS}
    cases, excluded = choose_pairs(rows, results, candidates_from(rows, results), PAIRS, SEED)
    repos = sorted({c["repo"] for c in cases})
    manifest = {
        "about": "B1's labelled set of real fixes (proof-of-fix#85 task 2.1). Labels come from SWE-bench's hidden "
                 "tests. Rebuild with scripts/judge-set.sh build.",
        "sources": sources(),
        "runs": RUNS, "licences": {r: licence(r) for r in repos}, "seed": SEED, "pairs": PAIRS,
        "size_classes": {"small": f"<= {D.SMALL_MAX} changed lines", "medium": f"<= {D.MEDIUM_MAX}",
                         "large": f"> {D.MEDIUM_MAX}"},
        "commit_message": COMMIT_MESSAGE, "counts": D.label_counts(cases), "cases": cases,
    }
    errors = D.check_manifest(manifest)
    if errors:
        raise SystemExit("\n".join(errors))
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"selected {len(cases)} cases from {len(repos)} repositories; excluded {len(excluded)} issues "
          f"whose failed patch was empty, didn't apply or wasn't a failure")
    return build(argparse.Namespace(set="v1"))


# ---------- #160: 50 more pairs, the passing-but-wrong arm, and the v1 set's stronger ground truth ----------

MORE_PAIRS, MORE_SEED = 50, 160  # a fresh seed: the v1 draw (seed 85) stays exactly as committed
PER_REPO_UNION = 24  # v1's cap was 12 of 50 issues per repository; the same share of the union of 100


def select_more(_args) -> int:
    """50 more pairs by v1's rules (same four agents, sizes 40/40/20 %, round-robin over the agents, gold for every
    other good fix), from the issues v1 didn't use, with seed 160; the per-repository cap holds for the union."""
    v1 = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    used = {c["instance"] for c in v1["cases"]}
    already: dict[str, int] = {}
    for iid in used:
        repo = next(c["repo"] for c in v1["cases"] if c["instance"] == iid)
        already[repo] = already.get(repo, 0) + 1
    rows = verified_rows()
    results = {run: outcomes(run) for run in RUNS}
    cands = [c for c in candidates_from(rows, results) if c.instance not in used]
    cases, excluded = choose_pairs(rows, results, cands, MORE_PAIRS, MORE_SEED, already=already,
                                   per_repo=PER_REPO_UNION)
    repos = sorted({c["repo"] for c in cases})
    manifest = {
        "about": "#160's extension of B1's set: 50 more pairs by v1's rules from the issues v1 didn't use. Labels "
                 "come from SWE-bench's hidden tests. Rebuild with scripts/judge-set.sh build --set more.",
        "extends": {"manifest": "data/judges/manifest.json",
                    "sha256": D.sha256((DATA / "manifest.json").read_text(encoding="utf-8"))},
        "sources": sources(), "runs": RUNS, "licences": {r: licence(r) for r in repos}, "seed": MORE_SEED,
        "pairs": MORE_PAIRS, "per_repo_union": PER_REPO_UNION,
        "size_classes": {"small": f"<= {D.SMALL_MAX} changed lines", "medium": f"<= {D.MEDIUM_MAX}",
                         "large": f"> {D.MEDIUM_MAX}"},
        "commit_message": COMMIT_MESSAGE, "excluded_redraws": len(excluded), "counts": D.label_counts(cases),
        "cases": cases,
    }
    errors = D.check_manifest(manifest)
    if errors:
        raise SystemExit("\n".join(errors))
    (DATA / "manifest-more.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"selected {len(cases)} more cases from {len(repos)} repositories; excluded {len(excluded)} issues "
          f"whose failed patch was empty, didn't apply or wasn't a failure")
    return build(argparse.Namespace(set="more"))


PATCHDIFF = Path("/ext/patchdiff")  # the replication package's PatchDiff/ folder, mounted read-only by judge-set.sh


def patchdiff_file(rel: str) -> bytes:
    """A result file of the replication package, checked against its pinned hash."""
    path = PATCHDIFF / rel
    if not path.exists():
        raise SystemExit(f"{path} missing: extract the replication package and set POF_PATCHDIFF_DIR (see "
                         f"reports/judges-v2.prereg.md, 'The data')")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != PBW.RESULT_FILES[rel]:
        raise SystemExit(f"{rel}: sha256 differs from the pinned replication package")
    return body


def patchdiff_results() -> tuple[dict, list[dict], dict]:
    rq1 = {t: json.loads(patchdiff_file(f"results/RQ1_{t}_runall.json")) for t in PBW.TOOLS}
    rq34 = list(csv.DictReader(io.StringIO(patchdiff_file("results/RQ34.csv").decode("utf-8"))))
    suspicious = {}
    for t in PBW.TOOLS:
        d = json.loads(patchdiff_file(f"results/RQ2_{t}_difftests.json"))
        suspicious[t] = {i for i, v in d.items() if any(x.get("differential_tests") for x in v)}
    return rq1, rq34, suspicious


def tool_patches(run: str) -> dict[str, str]:
    """A submission's patches from the public bucket (byte-identical to the replication package's copies)."""
    url = f"{BUCKET}/verified/{run}/all_preds.jsonl"
    out = {}
    for line in fetch(url).decode("utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[r["instance_id"]] = r.get("model_patch") or ""
    return out


def tool_resolved(run: str) -> set:
    url = (f"https://raw.githubusercontent.com/SWE-bench/experiments/{EXPERIMENTS_COMMIT}/evaluation/verified/"
           f"{run}/results/results.json")
    return set(json.loads(fetch(url))["resolved"])


def select_pbw(_args) -> int:
    """H1's arm: every patch the replication package labels wrong (full developer tests, or the authors' manual
    review) among those the hidden tests accepted, one per issue marked primary (seed 160)."""
    rows = verified_rows()
    rq1, rq34, _ = patchdiff_results()
    resolved = {t: tool_resolved(run) for t, run in PBW.TOOLS.items()}
    found = PBW.candidates(rq1, rq34, resolved)
    chosen = PBW.primary(found)
    patches = {t: tool_patches(run) for t, run in PBW.TOOLS.items()}
    cases = []
    for r in found:
        row, diff = rows[r["instance"]], patches[r["tool"]][r["instance"]]
        n = D.changed_lines(diff)
        cases.append({"id": f"{r['instance']}:pbw:{r['tool']}", "instance": r["instance"], "repo": row["repo"],
                      "base_commit": row["base_commit"], "label": "bad", "arm": "pbw",
                      "source": PBW.TOOLS[r["tool"]], "tool": r["tool"], "solver_family": PBW.SOLVER_FAMILY,
                      "patch_sha256": D.sha256(diff), "changed_lines": n, "size": D.size_class(n),
                      "difficulty": row.get("difficulty"), "issue_sha256": D.sha256(row["problem_statement"]),
                      "hidden_tests": "pass", "full_tests": r["full_tests"], "failing_tests": r["failing_tests"],
                      "manual": r["manual"], "diff_pattern": r["diff_pattern"], "evidence": PBW.evidence(r),
                      "primary": (r["tool"], r["instance"]) in chosen})
    repos = sorted({c["repo"] for c in cases})
    manifest = {
        "about": "#160's passing-but-wrong arm (H1): agents' patches SWE-bench Verified's hidden tests accept but "
                 "that fail the repository's full developer tests or the authors' manual review against the "
                 "reference, per Wang, Pradel and Liu (ICSE 2026, arXiv:2503.15223). Rebuild with "
                 "scripts/judge-set.sh build --set pbw.",
        "label_source": {"paper": "Wang, Y., Pradel, M., Liu, Z. Are 'Solved Issues' in SWE-bench Really Solved "
                                  "Correctly? An Empirical Study. ICSE 2026. doi:10.1145/3744916.3764576",
                         "package": PBW.ZENODO, "files": PBW.RESULT_FILES,
                         "rule": "wrong = RQ1 difference 'functionality' (a test the reference passes fails), or "
                                 "RQ34 correctness 'incorrect_*'; 'coding_conventions', 'correct_*' and "
                                 "'uncertain' are not used"},
        "sources": dict(sources(), agent_patches=f"{BUCKET}/verified/<run>/all_preds.jsonl",
                        hidden_test_outcomes="github.com/SWE-bench/experiments evaluation/verified/<run>/results/"
                                             "results.json at experiments_commit"),
        "tools": {t: {"run": run, "family": PBW.SOLVER_FAMILY, "model": PBW.SOLVER_MODEL}
                  for t, run in PBW.TOOLS.items()},
        "licences": {r: licence(r) for r in repos}, "seed": PBW.SEED, "commit_message": COMMIT_MESSAGE,
        "counts": {"cases": len(cases), "issues": len({c["instance"] for c in cases}),
                   "by_evidence": {e: sum(1 for c in cases if c["evidence"] == e) for e in PBW.STRENGTH}},
        "cases": cases,
    }
    errors = PBW.check_pbw_manifest(manifest)
    if errors:
        raise SystemExit("\n".join(errors))
    (DATA / "manifest-pbw.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"selected {len(cases)} passing-but-wrong patches on {manifest['counts']['issues']} issues "
          f"{manifest['counts']['by_evidence']}")
    return build(argparse.Namespace(set="pbw"))


def utboost_file(rel: str) -> bytes:
    return fetch(f"https://raw.githubusercontent.com/CUHK-Shenzhen-SE/UTBoost/{PBW.UTBOOST['commit']}/{rel}")


def cmd_coverage(_args) -> int:
    """What the published artifacts say about each hidden-test-labelled case (v1 and the extension), and which
    cases a person should review: data/judges/ground-truth.json."""
    rq1, rq34, suspicious = patchdiff_results()
    patches = {t: tool_patches(run) for t, run in PBW.TOOLS.items()}
    hashes = {f"{t}:{iid}": D.sha256(p) for t, ps in patches.items() for iid, p in ps.items() if p.strip()}
    resolved = {t: tool_resolved(run) for t, run in PBW.TOOLS.items()}
    aug = set(json.loads(utboost_file(PBW.UTBOOST["aug_tests"])))
    reparsed = json.loads(utboost_file(PBW.UTBOOST["parser_lists"]))
    out = {"about": "#160's stronger ground truth: for every hidden-test-labelled case, the published full-test and "
                    "manual verdicts on the same patch (by sha256), the issue-level evidence of weak hidden tests, "
                    "and why a person should review it. Rebuild with scripts/judge-set.sh coverage.",
           "sources": {"patchdiff": PBW.ZENODO, "patchdiff_files": PBW.RESULT_FILES, "utboost": PBW.UTBOOST},
           "utboost_reparsed_instances": len(reparsed)}
    for name in ("manifest.json", "manifest-more.json"):
        path = DATA / name
        if not path.exists():
            continue
        cases = json.loads(path.read_text(encoding="utf-8"))["cases"]
        failing = {}
        for c in cases:
            if c["label"] == "bad":
                status = agent_patch(c["source"], c["instance"])[1].get("tests_status") or {}
                failing[c["id"]] = [t for k in ("FAIL_TO_PASS", "PASS_TO_PASS")
                                    for t in (status.get(k) or {}).get("failure") or []]
        rows_ = PBW.coverage(cases, hashes, resolved, rq1, suspicious, rq34, aug, reparsed, failing)
        out[name] = {"cases": rows_,
                     "summary": {"cases": len(rows_),
                                 "patch_level_verdict": sum(1 for r in rows_ if r["patch_level"]),
                                 "issue_level_evidence": sum(1 for r in rows_ if any(r["issue_level"].values())),
                                 "for_review": sum(1 for r in rows_ if r["review"])}}
    (DATA / "ground-truth.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for name in ("manifest.json", "manifest-more.json"):
        if name in out:
            print(name, out[name]["summary"])
    return 0


SETS = {"v1": ("manifest.json", "cases.jsonl"), "more": ("manifest-more.json", "cases-more.jsonl"),
        "pbw": ("manifest-pbw.json", "cases-pbw.jsonl")}


def build(args) -> int:
    """Rebuild a set's cases from its committed manifest, checking every patch's and issue's hash and the counts."""
    which = getattr(args, "set", "v1")
    manifest_name, out_name = SETS[which]
    manifest = json.loads((DATA / manifest_name).read_text(encoding="utf-8"))
    errors = PBW.check_pbw_manifest(manifest) if which == "pbw" else D.check_manifest(manifest)
    rows = verified_rows()
    patches = {run: tool_patches(run) for run in PBW.TOOLS.values()} if which == "pbw" else {}
    out = []
    for c in manifest["cases"]:
        row = rows[c["instance"]]
        if which == "pbw":
            diff = patches[c["source"]][c["instance"]]
        else:
            diff = gold_diff(row) if c["source"] == "gold" else agent_patch(c["source"], c["instance"])[0]
        if D.sha256(diff) != c["patch_sha256"]:
            errors.append(f"{c['id']}: patch hash differs")
        if D.sha256(row["problem_statement"]) != c["issue_sha256"]:
            errors.append(f"{c['id']}: issue hash differs")
        case = {"id": c["id"], "instance": c["instance"], "repo": c["repo"], "base_commit": c["base_commit"],
                "label": c["label"], "source": c["source"], "size": c["size"],
                "issue": D.scrub(row["problem_statement"]), "commit": manifest["commit_message"], "diff": diff,
                "context": context(c["repo"], c["base_commit"], diff)}
        if which == "pbw":
            case.update(arm="pbw", primary=c["primary"], solver_family=c["solver_family"])
        out.append(case)
    if which == "pbw":
        if len(out) != manifest["counts"]["cases"]:
            errors.append(f"rebuilt {len(out)} cases != manifest {manifest['counts']['cases']}")
        counts = manifest["counts"]
    else:
        counts = D.label_counts(out)
        if counts != manifest["counts"]:
            errors.append(f"rebuilt counts {counts} != manifest {manifest['counts']}")
    if errors:
        raise SystemExit("\n".join(errors))
    (DATA / out_name).write_text("".join(json.dumps(c) + "\n" for c in out), encoding="utf-8")
    print(f"built {len(out)} cases of {which} {counts}; every patch and issue matches its hash")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/judge_set.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select").set_defaults(fn=select)
    sub.add_parser("select-more").set_defaults(fn=select_more)
    sub.add_parser("select-pbw").set_defaults(fn=select_pbw)
    sub.add_parser("coverage").set_defaults(fn=cmd_coverage)
    b = sub.add_parser("build")
    b.add_argument("--set", choices=sorted(SETS), default="v1")
    b.set_defaults(fn=build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
