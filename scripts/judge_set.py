"""Builds B1's labelled set of real fixes (proof-of-fix#85 task 2.1) from public data, reading only: no account, no
key, nothing written anywhere but data/judges/. Run it through scripts/judge-set.sh, which runs it in a pinned
container (rule 4: upstream code is untrusted; here it is only read as text, never run).

    select   choose the pairs and write data/judges/manifest.json (done once; the manifest is committed)
    build    rebuild data/judges/cases.jsonl from the manifest, checking every patch's hash and the label counts

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
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pof.judges import dataset as D  # noqa: E402

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
            req = urllib.request.Request(url, headers={"User-Agent": "proof-of-fix-judge-set"})
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


def select(_args) -> int:
    rows = verified_rows()
    results = {run: outcomes(run) for run in RUNS}
    candidates = []
    for iid, row in rows.items():
        failed = tuple(r for r in RUNS if results[r].get(iid) is False)
        resolved = tuple(r for r in RUNS if results[r].get(iid) is True)
        candidates.append(D.Candidate(iid, row["repo"], D.changed_lines(row["patch"]), resolved, failed))
    excluded: set[str] = set()
    while True:
        plans = D.select([c for c in candidates if c.instance not in excluded], tuple(RUNS), PAIRS, SEED)
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
            break
        excluded.update(bad_plans)
    repos = sorted({c["repo"] for c in cases})
    manifest = {
        "about": "B1's labelled set of real fixes (proof-of-fix#85 task 2.1). Labels come from SWE-bench's hidden "
                 "tests. Rebuild with scripts/judge-set.sh build.",
        "sources": {"dataset": f"huggingface.co/datasets/{DATASET}", "dataset_revision": DATASET_REVISION,
                    "dataset_licence": "no licence stated on the dataset card; SWE-bench's code is MIT, and each "
                                       "issue and patch is its repository's, under that repository's licence",
                    "experiments": "github.com/SWE-bench/experiments", "experiments_commit": EXPERIMENTS_COMMIT,
                    "agent_patches": f"{BUCKET}/bash-only/<run>/logs/<instance>/patch.diff",
                    "agent_patches_licence": "no licence stated: read for measurement, not redistributed (this "
                                             "repository stores only their hashes)"},
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
    return build(_args)


def build(args) -> int:
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    errors = D.check_manifest(manifest)
    rows = verified_rows()
    out = []
    for c in manifest["cases"]:
        row = rows[c["instance"]]
        diff = gold_diff(row) if c["source"] == "gold" else agent_patch(c["source"], c["instance"])[0]
        if D.sha256(diff) != c["patch_sha256"]:
            errors.append(f"{c['id']}: patch hash differs")
        if D.sha256(row["problem_statement"]) != c["issue_sha256"]:
            errors.append(f"{c['id']}: issue hash differs")
        out.append({"id": c["id"], "instance": c["instance"], "repo": c["repo"], "base_commit": c["base_commit"],
                    "label": c["label"], "source": c["source"], "size": c["size"], "issue": D.scrub(row["problem_statement"]),
                    "commit": manifest["commit_message"], "diff": diff,
                    "context": context(c["repo"], c["base_commit"], diff)})
    counts = D.label_counts(out)
    if counts != manifest["counts"]:
        errors.append(f"rebuilt counts {counts} != manifest {manifest['counts']}")
    if errors:
        raise SystemExit("\n".join(errors))
    (DATA / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in out), encoding="utf-8")
    print(f"built {len(out)} cases {counts}; every patch and issue matches its hash")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/judge_set.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select").set_defaults(fn=select)
    sub.add_parser("build").set_defaults(fn=build)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
