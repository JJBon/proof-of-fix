"""A stand-in for the `rad` CLI of one Radicle node, for pofctl's v3 end-to-end run (tests/e2e_pofctl_v3.py, #251 task
4.4) and its unit tests: the node's storage is a real bare git repository at $RAD_HOME/storage/<RID without "rad:">
(namespaces, signed branches, the canonical `refs/heads/main`), and only the commands pofctl's Radicle paths call are
answered:

    rad self --did                       the node's DID (the one delegate of the repository)
    rad inspect <RID> --identity         the identity document: that one delegate, threshold 1
    rad sync [--fetch] <RID>             nothing to fetch: exit 0
    rad issue comment [--repo RID] <ID> --message M    appended to $RAD_HOME/issue-comments.jsonl

Install it as `rad` on PATH (a two-line wrapper). Everything else exits 2. No network, no Radicle node: what the real
node does is checked by the Radicle spike (scripts/radicle-spike.sh --v3) and task 4.6's run."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DELEGATE = "z6MkpofctlE2eDelegateStandIn111111111111111111"


def main(argv: list) -> int:
    home = Path(os.environ.get("RAD_HOME") or Path.home() / ".radicle")
    if argv[:2] == ["self", "--did"]:
        print(f"did:key:{DELEGATE}")
        return 0
    if argv[:1] == ["inspect"] and "--identity" in argv:
        rid = next((a for a in argv[1:] if a.startswith("rad:")), "")
        if not (home / "storage" / rid[4:]).is_dir():
            sys.stderr.write("rad inspect: repository not found\n")
            return 3
        print(json.dumps({"delegates": [f"did:key:{DELEGATE}"], "threshold": 1}))
        return 0
    if argv[:1] == ["sync"]:
        return 0
    if argv[:2] == ["issue", "comment"]:
        rest, repo, msg, issue = argv[2:], "", None, ""
        i = 0
        while i < len(rest):
            if rest[i] in ("--repo", "-r"):
                repo, i = rest[i + 1], i + 2
            elif rest[i] in ("--message", "-m"):
                msg, i = rest[i + 1], i + 2
            else:
                issue, i = rest[i], i + 1
        if msg is None or not issue:
            sys.stderr.write("rad issue comment: an issue id and --message are required\n")
            return 2
        with open(home / "issue-comments.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"repo": repo, "issue": issue, "body": msg}) + "\n")
        print(f"✓ commented on {issue[:7]}")
        return 0
    sys.stderr.write(f"fake rad: unsupported: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
