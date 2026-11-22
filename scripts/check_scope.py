#!/usr/bin/env python3
"""How much of "pof / check" a pull request needs (proof-of-fix#208).

    scripts/check_scope.py <base>     prints "docs" or "full" on the last line, and why on the lines before

"docs": every file the change touches (merge base of <base> and HEAD, to HEAD) is documentation that no test reads,
so the Python tests can't be affected and scripts/check.sh skips them. Anything else, including a file it can't
classify or a merge base it can't find, is "full". Main's own run (push) and local runs pass no base: always full.

If a test starts reading a documentation file, add the file's path to TESTS_READ below (and to the test's list).
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys

DOCS = (
    "openspec/*",    # specs, changes, archive: their structure is still checked by scripts/check_openspec.py
    "docs/*",        # ADRs and guides
    ".claude/*",     # Claude Code's project settings and skills
    "README.md",
    "CONSTITUTION.md",
    "*.md",          # any other Markdown, except under the directories below
)
TESTS_READ = (       # documentation a test reads: a change here runs everything
    "openspec/config.yaml",  # tests/test_no_network.py
    "reports/*",             # the simulations' reports, reproduced by tests (test_judges, test_openval*, test_fundertoken)
    "validator-kit/*",       # tests/test_devnet_remote.py reads the runbook
    "seed/*",                # tests/test_seed.py scans every file there, its README too (no RID, no account value)
    "tests/*",
    "experiments/*",         # tests/test_zktls_receipt.py
    "docs/research/hypotheses.md",  # tests/test_judges_v2.py checks the pre-registration's thresholds against it
    "docs/guides/*",         # tests/test_guides.py parses the onboarding guides' command blocks (#251 task 5.7)
)


def classify(paths: list) -> tuple:
    """("docs" or "full", [reasons]). An empty change is "full": nothing to compare means nothing proven."""
    if not paths:
        return "full", ["no changed files found"]
    code = [p for p in paths
            if any(fnmatch.fnmatch(p, g) for g in TESTS_READ) or not any(fnmatch.fnmatch(p, g) for g in DOCS)]
    if code:
        shown = ", ".join(code[:5]) + (f" and {len(code) - 5} more" if len(code) > 5 else "")
        return "full", [f"changes outside documentation: {shown}"]
    return "docs", [f"{len(paths)} documentation file(s) only"]


def changed(base: str) -> list:
    """Files changed from the merge base of `base` and HEAD to HEAD. Raises on any git error."""
    merge_base = subprocess.run(["git", "merge-base", base, "HEAD"], check=True, capture_output=True,
                                text=True).stdout.strip()
    out = subprocess.run(["git", "diff", "--name-only", "--no-renames", merge_base, "HEAD"], check=True,
                         capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def main(argv: list) -> int:
    if len(argv) != 1:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    try:
        paths = changed(argv[0])
    except (subprocess.CalledProcessError, OSError) as e:
        print(f"check scope: can't compare with {argv[0]} ({type(e).__name__}); running everything")
        print("full")
        return 0
    scope, reasons = classify(paths)
    for r in reasons:
        print(f"check scope: {r}")
    print(scope)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
