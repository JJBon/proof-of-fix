"""Rebuild data/gridcraft_baseline.json from GridCraft's public pull-request history (specs/incentive-simulation,
"Replay of real history"; design D8).

Uses the GitHub GraphQL API through `gh` (signed in). Everything is aggregated in memory: author logins are used
only to count distinct authors per week and are then dropped. The output holds distributions and counts only,
with no usernames, PR numbers, titles or URLs.

    python3 scripts/fetch_baseline.py --since 2026-10-07 --until 2026-10-23 > data/gridcraft_baseline.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone

REPO = "storytold/gridcraft"
BOTS = ("bot", "rabbit", "sonar", "dependabot")
QUERY = """
query($q: String!, $after: String) {
  search(query: $q, type: ISSUE, first: 50, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest {
      createdAt mergedAt additions deletions changedFiles
      author { login }
      reviews(first: 50) { nodes { author { login } } }
      closingIssuesReferences { totalCount }
    } }
  }
}"""


def search(q: str) -> list[dict]:
    out, after = [], None
    while True:
        args = ["gh", "api", "graphql", "-f", f"query={QUERY}", "-F", f"q={q}"]
        if after:
            args += ["-F", f"after={after}"]
        page = json.loads(subprocess.run(args, check=True, capture_output=True, text=True).stdout)["data"]["search"]
        out += [n for n in page["nodes"] if n]
        if not page["pageInfo"]["hasNextPage"] or len(out) >= 1000:
            return out
        after = page["pageInfo"]["endCursor"]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def quantiles(values: list[float]) -> dict:
    v = sorted(values)
    if not v:
        return {}
    pick = lambda q: v[min(len(v) - 1, int(q * len(v)))]  # noqa: E731
    return {"p10": pick(0.1), "p25": pick(0.25), "p50": pick(0.5), "p75": pick(0.75), "p90": pick(0.9), "max": v[-1]}


def histogram(values: list[int], bounds=(10, 30, 100, 400, 1500, 5000)) -> dict:
    labels = [f"<={b}" for b in bounds] + [f">{bounds[-1]}"]
    counts = dict.fromkeys(labels, 0)
    for x in values:
        counts[next((f"<={b}" for b in bounds if x <= b), labels[-1])] += 1
    return counts


def human(review: dict) -> bool:
    login = ((review.get("author") or {}).get("login") or "").lower()
    return bool(login) and not any(b in login for b in BOTS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True)
    ap.add_argument("--until", required=True)
    a = ap.parse_args()
    window = f"{a.since}..{a.until}"
    merged = search(f"repo:{REPO} is:pr is:merged merged:{window}")
    still_open = search(f"repo:{REPO} is:pr is:open created:<={a.until}")
    as_of = ts(f"{a.until}T23:59:59Z")

    sizes = [p["additions"] + p["deletions"] for p in merged]
    weeks: dict[str, int] = {}
    authors: dict[str, set] = {}
    for p in merged:
        y, w, _ = ts(p["mergedAt"]).isocalendar()
        key = f"{y}-W{w:02d}"
        weeks[key] = weeks.get(key, 0) + 1
        authors.setdefault(key, set()).add((p.get("author") or {}).get("login"))
    baseline = {
        "source": REPO,
        "window": [a.since, a.until],
        "fetched": date.today().isoformat(),
        "note": "Aggregates of public pull-request metadata only: no usernames, PR numbers, titles or URLs.",
        "merged": {
            "count": len(merged),
            "changed_lines": quantiles(sizes),
            "changed_lines_histogram": histogram(sizes),
            "changed_files": quantiles([p["changedFiles"] for p in merged]),
            "hours_to_merge": quantiles([round((ts(p["mergedAt"]) - ts(p["createdAt"])).total_seconds() / 3600, 1)
                                         for p in merged]),
            "human_review_share": round(sum(any(human(r) for r in p["reviews"]["nodes"]) for p in merged)
                                        / max(1, len(merged)), 3),
            "linked_issue_share": round(sum(p["closingIssuesReferences"]["totalCount"] > 0 for p in merged)
                                        / max(1, len(merged)), 3),
        },
        "weekly": {k: {"merged": weeks[k], "distinct_authors": len(authors[k] - {None})} for k in sorted(weeks)},
        "open": {
            "count": len(still_open),
            "changed_lines": quantiles([p["additions"] + p["deletions"] for p in still_open]),
            "age_days": quantiles([round((as_of - ts(p["createdAt"])).total_seconds() / 86400, 1) for p in still_open]),
            "human_review_share": round(sum(any(human(r) for r in p["reviews"]["nodes"]) for p in still_open)
                                        / max(1, len(still_open)), 3),
        },
    }
    json.dump(baseline, sys.stdout, indent=2, sort_keys=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
