"""The labelled set of real fixes (task 2.1): diffs, sizes, scrubbing, the seeded selection and the manifest's checks.

A case is one fix to one real issue, labelled by tests, not by opinion:
- good: the merged fix (the gold patch, with its tests), or an agent's patch the benchmark's hidden tests accepted;
- bad: an agent's patch that applied but that the same hidden tests rejected.
The cases come in pairs, a good and a bad fix to the same issue, so a judge is measured on the same problems both ways.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

LABELS = ("good", "bad")
SIZES = ("small", "medium", "large")
SMALL_MAX, MEDIUM_MAX = 10, 40  # changed lines (added + removed): small up to 10, medium up to 40, large above


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- diffs ----------

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


def changed_lines(diff: str) -> int:
    """Added and removed lines, not counting the file headers."""
    n = 0
    for line in diff.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            n += 1
    return n


def size_class(lines: int) -> str:
    return "small" if lines <= SMALL_MAX else "medium" if lines <= MEDIUM_MAX else "large"


def files(diff: str) -> list[str]:
    """The files a diff changes, as paths in the base tree (new files are left out: they have no base)."""
    out = []
    for line in diff.splitlines():
        if line.startswith("--- a/"):
            path = line[6:].strip()
            if path not in out:
                out.append(path)
    return out


def hunks(diff: str) -> dict[str, list[tuple[int, int]]]:
    """Each changed file's hunks as (first line, line count) in the base file."""
    out: dict[str, list[tuple[int, int]]] = {}
    path = None
    for line in diff.splitlines():
        if line.startswith("--- "):
            path = line[6:].strip() if line.startswith("--- a/") else None
        m = HUNK.match(line)
        if m and path:
            out.setdefault(path, []).append((int(m.group(1)), int(m.group(2) or 1)))
    return out


def windows(spans: list[tuple[int, int]], length: int, around: int = 40) -> list[tuple[int, int]]:
    """1-based inclusive line ranges of the base file around each hunk, merged where they overlap."""
    ranges = sorted((max(1, start - around), min(length, start + count + around)) for start, count in spans)
    merged: list[tuple[int, int]] = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        elif lo <= hi:
            merged.append((lo, hi))
    return merged


def excerpt(text: str, ranges: list[tuple[int, int]]) -> str:
    """The base file's lines in the ranges, each prefixed with its number, ranges separated by an ellipsis."""
    lines = text.splitlines()
    parts = []
    for lo, hi in ranges:
        parts.append("\n".join(f"{i:>5} {lines[i - 1]}" for i in range(lo, min(hi, len(lines)) + 1)))
    return "\n   ...\n".join(parts)


# ---------- people's data (rule 5) ----------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
MENTION = re.compile(r"(?<![\w/@])@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
PROFILE = re.compile(r"https?://github\.com/(?!(?:[\w.-]+/[\w.-]+/(?:issues|pull|blob|tree|commit)))[A-Za-z0-9-]+/?(?=[\s)\]>.,]|$)")
# Django's Trac prefixes an edited description with "(last modified by <name>)" (#160: 28 of the sets' issue texts).
TRAC_EDITOR = re.compile(r"\(last modified by [^)\n]*\)")


def scrub(text: str) -> str:
    """Drops what identifies a person in an issue's text: e-mail addresses, @mentions, profile links and Trac's
    "(last modified by <name>)"."""
    text = TRAC_EDITOR.sub("(last modified by <user>)", text)
    text = EMAIL.sub("<email>", text)
    text = PROFILE.sub("<profile>", text)
    return MENTION.sub("@<user>", text)


# ---------- selection ----------

@dataclass(frozen=True)
class Candidate:
    """An issue of the benchmark with the agents' outcomes on it: which runs resolved it and which failed it."""
    instance: str
    repo: str
    gold_lines: int
    resolved_by: tuple[str, ...]
    failed_by: tuple[str, ...]


def select(candidates: list[Candidate], runs: tuple[str, ...], pairs: int = 50, seed: int = 85,
           size_targets: dict[str, float] | None = None, per_repo: int = 12,
           already: dict[str, int] | None = None) -> list[dict]:
    """Picks `pairs` issues and, for each, a bad fix (a run that failed it) and a good one (the gold patch for half
    the pairs, an agent's accepted patch for the other half when one exists), seeded and stratified:
    - by the gold patch's size, toward `size_targets` (default 40 % small, 40 % medium, 20 % large);
    - at most `per_repo` issues from one repository;
    - the bad fixes spread round-robin over the runs, so no agent dominates.
    `already` counts issues per repository picked by an earlier selection that this one extends (#160's extension of
    the v1 set): they count toward `per_repo`, so the cap holds for the union.
    Returns one plan per pair: {instance, repo, bad_run, good: "gold" or a run}."""
    targets = size_targets or {"small": 0.4, "medium": 0.4, "large": 0.2}
    rng = random.Random(seed)
    pool = sorted((c for c in candidates if c.failed_by), key=lambda c: c.instance)
    rng.shuffle(pool)
    quota = {s: round(pairs * w) for s, w in targets.items()}
    quota[SIZES[0]] += pairs - sum(quota.values())
    by_repo: dict[str, int] = dict(already or {})
    chosen: list[Candidate] = []
    for strict in (True, False):  # first fill each size's quota, then top up from any size
        for c in pool:
            if len(chosen) == pairs:
                break
            size = size_class(c.gold_lines)
            if c in chosen or by_repo.get(c.repo, 0) >= per_repo or (strict and quota[size] <= 0):
                continue
            chosen.append(c)
            by_repo[c.repo] = by_repo.get(c.repo, 0) + 1
            quota[size] -= 1
    plans = []
    used = {r: 0 for r in runs}
    for i, c in enumerate(chosen):
        preferred = runs[i % len(runs)]
        bad_run = preferred if preferred in c.failed_by else min(sorted(c.failed_by), key=lambda r: used.get(r, 0))
        used[bad_run] = used.get(bad_run, 0) + 1
        agents = [r for r in runs if r in c.resolved_by and r != bad_run]
        good = "gold" if i % 2 == 0 or not agents else agents[(i // 2) % len(agents)]
        plans.append({"instance": c.instance, "repo": c.repo, "bad_run": bad_run, "good": good})
    return plans


# ---------- the manifest ----------

CASE_FIELDS = ("id", "instance", "repo", "base_commit", "label", "source", "patch_sha256", "changed_lines", "size")


def label_counts(cases: list[dict]) -> dict[str, int]:
    return {label: sum(1 for c in cases if c["label"] == label) for label in LABELS}


def check_manifest(manifest: dict) -> list[str]:
    """The manifest's own consistency: every case complete and labelled, its size matching its changed lines, pairs
    of one good and one bad fix to the same issue, and the stated label counts matching the cases."""
    errors = []
    cases = manifest.get("cases", [])
    ids = [c.get("id") for c in cases]
    if len(set(ids)) != len(ids):
        errors.append("duplicate case ids")
    for c in cases:
        missing = [f for f in CASE_FIELDS if f not in c]
        if missing:
            errors.append(f"{c.get('id')}: missing {missing}")
            continue
        if c["label"] not in LABELS:
            errors.append(f"{c['id']}: label {c['label']!r}")
        if not re.fullmatch(r"[0-9a-f]{64}", c["patch_sha256"]):
            errors.append(f"{c['id']}: patch_sha256")
        if not re.fullmatch(r"[0-9a-f]{40}", c["base_commit"]):
            errors.append(f"{c['id']}: base_commit")
        if size_class(c["changed_lines"]) != c["size"]:
            errors.append(f"{c['id']}: size {c['size']} for {c['changed_lines']} lines")
        if c["source"] != "gold" and c["source"] not in manifest.get("runs", {}):
            errors.append(f"{c['id']}: unknown source {c['source']}")
        if c["repo"] not in manifest.get("licences", {}):
            errors.append(f"{c['id']}: no licence for {c['repo']}")
    per_issue: dict[str, list[str]] = {}
    for c in cases:
        per_issue.setdefault(c.get("instance"), []).append(c.get("label"))
    for instance, labels in per_issue.items():
        if sorted(labels) != ["bad", "good"]:
            errors.append(f"{instance}: labels {labels}, expected one good and one bad")
    if manifest.get("counts") != label_counts(cases):
        errors.append(f"counts {manifest.get('counts')} != {label_counts(cases)}")
    return errors
