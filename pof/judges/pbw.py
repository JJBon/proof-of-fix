"""#160's passing-but-wrong arm (H1) and the stronger ground truth for the v1 set, from published per-patch verdicts.

A passing-but-wrong fix is an agent's patch that SWE-bench Verified's hidden tests accept but that is wrong by a
stronger standard. The label comes from Wang, Pradel and Liu, "Are 'Solved Issues' in SWE-bench Really Solved
Correctly?" (ICSE 2026, arXiv:2503.15223), whose replication package (Zenodo 10.5281/zenodo.17074796, CC BY 4.0)
publishes two per-patch verdicts for three agents' plausible patches:
- RQ1 (`results/RQ1_<tool>_runall.json`): the repository's full developer test suite. A patch fails it when a test
  the reference (gold) patch passes fails with the agent's patch. The authors classify each difference as
  "functionality" or "coding_conventions"; only "functionality" counts as wrong, as in the paper (68 patches);
- RQ3/4 (`results/RQ34.csv`): the authors' manual review of 77 patches PatchDiff flagged as behaving differently
  from the reference; "incorrect_*" counts as wrong (22 patches), "correct_*" and "uncertain" don't.

UTBoost (Yu et al., ACL 2025, arXiv:2506.09289; github.com/CUHK-Shenzhen-SE/UTBoost, MIT) publishes no per-patch
verdicts: only the augmented tests it confirmed for 36 instances (`assets/useful_scripts/augTest.json`) and its
re-parsed test lists (`update_SWE_Bench/updated_parser_test_instance_dict_verified.json`). They are used here as
instance-level evidence that an issue's hidden tests are weak, never as a patch's label.

Nothing here reaches the network; scripts/judge_set.py reads the sources and passes them in.
"""

from __future__ import annotations

import random
import re



# The three agents PatchDiff studied, by the name its results use, with their SWE-bench submission (the patches are
# byte-identical in the Zenodo package and in the public bucket swe-bench-submissions/verified/<run>/all_preds.jsonl,
# checked 2026-11-13). All three run on Claude 3.5 Sonnet, so every patch of the arm is from the Anthropic family.
TOOLS = {
    "OpenHands": "20241029_OpenHands-CodeAct-2.1-sonnet-20241022",
    "CodeStory": "20241221_codestory_midwit_claude-3-5-sonnet_swe-search",
    "LearnByInteract": "20250110_learn_by_interact_claude3.5",
}
SOLVER_FAMILY = "anthropic"
SOLVER_MODEL = "Claude 3.5 Sonnet (2024-10-22)"

# The replication package, pinned: the archive and the result files the labels come from (sha256 of each file as
# extracted from PatchDiff_0908.7z).
ZENODO = {"doi": "10.5281/zenodo.17074796", "record": "https://zenodo.org/records/17074796",
          "file": "PatchDiff_0908.7z", "md5": "ec317f442b40122e646e46bb09eb1350",
          "sha256": "26366405ba37cb3f8052ddd49e23f62e11925dc4a5512744cf03037d30e9204a", "licence": "CC-BY-4.0"}
RESULT_FILES = {  # path inside the archive's PatchDiff/ folder -> sha256
    "results/RQ1_CodeStory_runall.json": "30b2e153be517c08731a5ba273ebd0df91c509b7fd17d5cce12d5fb5acee033d",
    "results/RQ1_LearnByInteract_runall.json": "b6471f1b6a4d66cb3dc08c001d2a908e9a9ca179f273edb4083bfa20cd004cf7",
    "results/RQ1_OpenHands_runall.json": "9e6913c0f169d5d62261ba8266400675cdbda3f531cd6d9cc3a92d5b6465421c",
    "results/RQ34.csv": "44ac55898d4a9212ba0d3a980d1cb6401c59c562bfc1aee40aa8dadfcd623289",
    "results/RQ2_CodeStory_difftests.json": "606bfdc0b8338aa60a542698ced2d9ae8d5660172994f0646e17bb14c6763a64",
    "results/RQ2_LearnByInteract_difftests.json": "2a7817091e633b77c8772aa567f59d7ffb0c6c6302e045e23d13acbbf8e18404",
    "results/RQ2_OpenHands_difftests.json": "0386857b2addcef4e65394a69986c4642320bde6409d87341bdac19e602a2685",
}
UTBOOST = {"repo": "github.com/CUHK-Shenzhen-SE/UTBoost", "commit": "4f32782517f23940d3ede8cd1f250667873cc0c6",
           "licence": "MIT", "aug_tests": "assets/useful_scripts/augTest.json",
           "parser_lists": "update_SWE_Bench/updated_parser_test_instance_dict_verified.json"}

WRONG_DIFFERENCE = "functionality"  # RQ1's class that counts as wrong; "coding_conventions" doesn't
SEED = 160


def candidates(rq1: dict[str, dict], rq34: list[dict], resolved: dict[str, set]) -> list[dict]:
    """Every patch the authors found wrong, with its evidence. rq1 maps a tool to its RQ1 file ({instance:
    {"oracle_pass_model_fail": [tests], "difference": class}}); rq34 is RQ34.csv's rows ({tool, instance_id,
    diff_pattern, correctness}); resolved maps a tool to the instances the hidden tests accepted. A patch the hidden
    tests didn't accept isn't passing-but-wrong, so it's refused."""
    out: dict[tuple[str, str], dict] = {}
    for tool, rows in rq1.items():
        for iid, v in rows.items():
            if v.get("difference") == WRONG_DIFFERENCE:
                out[(tool, iid)] = {"tool": tool, "instance": iid, "full_tests": "fail",
                                    "failing_tests": len(v.get("oracle_pass_model_fail") or []), "manual": None,
                                    "diff_pattern": None}
    for r in rq34:
        if not r["correctness"].startswith("incorrect"):
            continue
        key = (r["tool"], r["instance_id"])
        row = out.setdefault(key, {"tool": r["tool"], "instance": r["instance_id"], "full_tests": "not failed",
                                   "failing_tests": 0, "manual": None, "diff_pattern": None})
        row["manual"], row["diff_pattern"] = r["correctness"], r["diff_pattern"]
    for (tool, iid) in out:
        if iid not in resolved.get(tool, set()):
            raise ValueError(f"{tool} {iid}: not accepted by the hidden tests, so not passing-but-wrong")
    return [out[k] for k in sorted(out)]


def evidence(row: dict) -> str:
    """Which published verdict makes the patch wrong: both, the full developer tests, or the manual review."""
    if row["full_tests"] == "fail" and row["manual"]:
        return "both"
    return "full-tests" if row["full_tests"] == "fail" else "manual"


STRENGTH = {"both": 0, "full-tests": 1, "manual": 2}


def primary(rows: list[dict], seed: int = SEED) -> set[tuple[str, str]]:
    """One patch per issue for H1's primary analysis, so its binomial counts independent problems: the patch with
    the strongest evidence (both verdicts, then the full tests, then the manual review), ties broken by a seeded
    draw. Returns the chosen (tool, instance) pairs."""
    rng = random.Random(seed)
    by_issue: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: (r["instance"], r["tool"])):
        by_issue.setdefault(r["instance"], []).append(r)
    chosen = set()
    for iid in sorted(by_issue):
        group = by_issue[iid]
        best = min(STRENGTH[evidence(r)] for r in group)
        top = [r for r in group if STRENGTH[evidence(r)] == best]
        pick = top[rng.randrange(len(top))]
        chosen.add((pick["tool"], iid))
    return chosen


PBW_FIELDS = ("id", "instance", "repo", "base_commit", "label", "arm", "source", "solver_family", "patch_sha256",
              "changed_lines", "size", "issue_sha256", "evidence", "primary")


def check_pbw_manifest(manifest: dict) -> list[str]:
    """The arm's manifest: every case complete, labelled bad (the judges should fail it) with published evidence,
    one primary case per issue, and the stated counts matching."""
    from .dataset import size_class
    import re
    errors = []
    cases = manifest.get("cases", [])
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        errors.append("duplicate case ids")
    for c in cases:
        missing = [f for f in PBW_FIELDS if f not in c]
        if missing:
            errors.append(f"{c.get('id')}: missing {missing}")
            continue
        if c["label"] != "bad" or c["arm"] != "pbw":
            errors.append(f"{c['id']}: label {c['label']!r}, arm {c['arm']!r}")
        if c["evidence"] not in STRENGTH:
            errors.append(f"{c['id']}: evidence {c['evidence']!r}")
        if not re.fullmatch(r"[0-9a-f]{64}", c["patch_sha256"]) or not re.fullmatch(r"[0-9a-f]{40}", c["base_commit"]):
            errors.append(f"{c['id']}: hash or commit")
        if size_class(c["changed_lines"]) != c["size"]:
            errors.append(f"{c['id']}: size {c['size']} for {c['changed_lines']} lines")
        if c["source"] not in TOOLS.values():
            errors.append(f"{c['id']}: unknown source {c['source']}")
        if c["repo"] not in manifest.get("licences", {}):
            errors.append(f"{c['id']}: no licence for {c['repo']}")
    per_issue: dict[str, int] = {}
    for c in cases:
        per_issue[c.get("instance")] = per_issue.get(c.get("instance"), 0) + bool(c.get("primary"))
    for iid, n in per_issue.items():
        if n != 1:
            errors.append(f"{iid}: {n} primary cases, expected 1")
    counts = {"cases": len(cases), "issues": len(per_issue),
              "by_evidence": {e: sum(1 for c in cases if c.get("evidence") == e) for e in STRENGTH}}
    if manifest.get("counts") != counts:
        errors.append(f"counts {manifest.get('counts')} != {counts}")
    return errors


# ---------- the stronger ground truth for the v1 cases ----------

DJANGO_NAME = re.compile(r"^(\S+) \((.+)\)$")


def test_name(name: str) -> str:
    """A test's name with the formatting that differs between parsers removed: Django's "test_x (mod.Class.test_x)"
    and "test_x (mod.Class)" are the same test."""
    name = name.strip()
    m = DJANGO_NAME.match(name)
    if m:
        test, path = m.groups()
        if path.endswith("." + test):
            path = path[: -len(test) - 1]
        return f"{test} ({path})"
    return name


def reparse_drops(failing: list[str], lists: dict | None) -> bool | None:
    """Whether every test a bad patch failed is missing from UTBoost's re-parsed lists for its issue (so its "bad"
    label may come from SWE-bench's parser, not the patch). None when UTBoost didn't re-parse the issue or the patch
    failed no listed test."""
    if not lists or not failing:
        return None
    listed = {test_name(t) for k in ("FAIL_TO_PASS", "PASS_TO_PASS") for t in lists.get(k) or []}
    return not any(test_name(t) in listed for t in failing)


def coverage(cases: list[dict], patch_hashes: dict[str, str], resolved: dict[str, set], rq1: dict[str, dict],
             suspicious: dict[str, set], rq34: list[dict], aug: set, reparsed: dict[str, dict],
             failing: dict[str, list[str]]) -> list[dict]:
    """For every case of a set labelled by hidden tests: what the published artifacts say about it.
    - patch level: a full-test or manual verdict exists only if the very same patch (by sha256) is one PatchDiff
      judged, which it did only for patches the hidden tests accepted; patch_hashes maps "<tool>:<instance>" to the
      sha256 of that tool's patch, resolved maps a tool to its accepted instances;
    - issue level: how many of PatchDiff's agents had a plausible patch on the issue that failed the full developer
      tests (rq1, "functionality") or that PatchDiff flagged as diverging from the reference (suspicious, per tool);
      whether UTBoost confirmed the issue's hidden tests insufficient (aug) or re-parsed its test lists (reparsed:
      instance -> its lists);
    - failing maps a bad case's id to the hidden tests its patch failed (its SWE-bench report).
    `review` says why a person should look at the case, or is empty: a patch-level verdict that disagrees with the
    hidden tests, a good case written by an agent on an issue with weak-test evidence (its label may be a false
    pass), or a bad case whose failing tests UTBoost's re-parse doesn't list (its label may be the parser's)."""
    manual = {(r["tool"], r["instance_id"]): r["correctness"] for r in rq34}
    by_hash: dict[str, list[str]] = {}
    for k, h in patch_hashes.items():
        by_hash.setdefault(h, []).append(k)
    out = []
    for c in cases:
        iid = c["instance"]
        judged = [k.split(":", 1)[0] for k in by_hash.get(c["patch_sha256"], [])
                  if k.split(":", 1)[1] == iid and iid in resolved.get(k.split(":", 1)[0], set())]
        patch_level = None
        if judged:
            tool = sorted(judged)[0]
            v = rq1.get(tool, {}).get(iid)
            patch_level = {"tool": tool, "full_tests": "fail" if v and v.get("difference") == WRONG_DIFFERENCE
                           else "pass", "manual": manual.get((tool, iid))}
        n_fail = sum(1 for t in rq1 if (rq1[t].get(iid) or {}).get("difference") == WRONG_DIFFERENCE)
        n_susp = sum(1 for t in suspicious if iid in suspicious[t])
        drops = reparse_drops(failing.get(c["id"], []), reparsed.get(iid)) if c["label"] == "bad" else None
        row = {"id": c["id"], "hidden_tests": "pass" if c["label"] == "good" else "fail", "patch_level": patch_level,
               "issue_level": {"patchdiff_full_test_failures": n_fail, "patchdiff_suspicious": n_susp,
                               "utboost_insufficient_tests": iid in aug, "utboost_reparsed": iid in reparsed},
               "reparse_drops_failing_tests": drops}
        reasons = []
        if patch_level:
            wrong = patch_level["full_tests"] == "fail" or (patch_level["manual"] or "").startswith("incorrect")
            if (c["label"] == "good") == wrong:
                reasons.append("the published full-test or manual verdict disagrees with the hidden tests")
        if c["label"] == "good" and c.get("source") != "gold" and (n_fail or n_susp or iid in aug):
            reasons.append("agent-written good fix on an issue whose hidden tests are known to pass wrong fixes")
        if drops:
            reasons.append("bad fix whose failing hidden tests UTBoost's re-parse doesn't list")
        row["review"] = reasons
        out.append(row)
    return out
