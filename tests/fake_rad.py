"""A stand-in for the `rad` CLI of one Radicle node, for pofctl's v3 end-to-end run (tests/e2e_pofctl_v3.py, #251 task
4.4), its unit tests, and the node's Radicle tests (tests/test_radicle_v3.py, tasks 4.1 and 4.2): the node's storage is
a real bare git repository at $RAD_HOME/storage/<RID without "rad:"> (namespaces, signed branches, the canonical
`refs/heads/main`, the patches' commits), the collaborative objects are JSON files under
$RAD_HOME/cobs/<type>/<id>.json, and only the commands the callers run are answered:

    rad self --did                       the node's DID ($RAD_HOME/did if present, else the one delegate's)
    rad inspect <RID> --identity         the identity document: the identity COB's current revision, or that one
                                         delegate, threshold 1
    rad sync --fetch|--announce <RID>    nothing to fetch: exit 0. The RID is positional, as in Radicle 1.10.3:
                                         `--rid` is refused (exit 2). With $RAD_HOME/sync-fails present, it fails
                                         as an isolated node's does (exit 1, "no candidate seeds")
    rad cob list --repo RID --type T     the ids of $RAD_HOME/cobs/T/*.json, sorted
    rad cob show --repo RID --type T --object ID     that file, on one line
    rad id update --repo RID --title T --description D [--delegate DID]... [--rescind DID]... [--threshold N]
           [--payload ID KEY VALUE] --no-confirm
                                         a new revision of the identity COB, "active" (or "accepted" when the current
                                         threshold is 1 and this node is a delegate), recorded in id-calls.jsonl
    rad id accept|reject REV --repo RID --no-confirm   this node's verdict on REV; accepted at the threshold
    rad issue open [--repo RID] --title T --description D [--no-announce]
                                         a new issue COB in Radicle 1.10.3's shape (its id the description's comment
                                         id; the thread's timeline in order), printed as Radicle 1.10.3 prints it: a
                                         box whose row `│ Issue   <40 hex> │` holds the whole id (v3.1 polish VP11)
    rad issue show <ID> [--repo RID]     the same box for that issue (a unique prefix, as rad takes it); with
                                         $RAD_HOME/show-title present, its contents as the title shown (a test's
                                         mismatch)
    rad issue comment [--repo RID] <ID> --message M    appended to $RAD_HOME/issue-comments.jsonl, and to the
                                         issue COB's thread when this node has that issue

Install it as `rad` on PATH (a two-line wrapper). Everything else exits 2. No network, no Radicle node: what the real
node does is checked by the Radicle spike (scripts/radicle-spike.sh --v3) and task 4.6's run."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

DELEGATE = "z6MkpofctlE2eDelegateStandIn111111111111111111"
ID_TYPE, PATCH_TYPE, ISSUE_TYPE = "xyz.radicle.id", "xyz.radicle.patch", "xyz.radicle.issue"


def _opt(argv: list, name: str, default=None):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else default


def _me(home: Path) -> str:
    f = home / "did"
    return f.read_text(encoding="utf-8").strip() if f.is_file() else f"did:key:{DELEGATE}"


def _record(home: Path, name: str, row: dict) -> None:
    with open(home / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _id_cob(home: Path):
    d = home / "cobs" / ID_TYPE
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    return (files[0], json.loads(files[0].read_text(encoding="utf-8"))) if files else (None, None)


def _identity(home: Path, argv: list) -> int:
    verb = argv[1] if len(argv) > 1 else ""
    path, cob = _id_cob(home)
    me = _me(home)
    if cob is None:
        sys.stderr.write("✗ Error: no identity\n")
        return 1
    _record(home, "id-calls.jsonl", {"argv": argv})
    current = cob["revisions"][cob["current"]]
    doc = json.loads(json.dumps(current["doc"]))
    if verb == "update":
        rest = argv[2:]
        delegates = list(doc["delegates"])
        for i, a in enumerate(rest):
            if a == "--delegate" and rest[i + 1] not in delegates:
                delegates.append(rest[i + 1])
            elif a == "--rescind" and rest[i + 1] in delegates:
                delegates.remove(rest[i + 1])
            elif a == "--payload":
                doc.setdefault("payload", {}).setdefault(rest[i + 1], {})[rest[i + 2]] = json.loads(rest[i + 3])
        doc["delegates"] = delegates
        if "--threshold" in rest:
            doc["threshold"] = int(_opt(rest, "--threshold"))
        rid_ = hashlib.sha1(json.dumps([cob["current"], doc, len(cob["revisions"])]).encode()).hexdigest()
        alone = current["doc"]["threshold"] == 1 and me in current["doc"]["delegates"]
        cob["revisions"][rid_] = {"id": rid_, "title": _opt(rest, "--title", ""), "state": "accepted" if alone else
                                  "active", "doc": doc, "timestamp": len(cob["revisions"]), "parent": cob["current"],
                                  "verdicts": {me[8:]: {"Accept": "sig"}}}
        cob["timeline"].append(rid_)
        if alone:
            cob["current"] = rid_
        print(f"✓ Identity revision {rid_} created")
    elif verb in ("accept", "reject"):
        rev = next((a for a in argv[2:] if len(a) == 40 and all(c in "0123456789abcdef" for c in a)), "")
        r = cob["revisions"].get(rev)
        if r is None:
            sys.stderr.write(f"✗ Error: revspec '{rev}' not found\n")
            return 1
        r["verdicts"][me[8:]] = {"Accept" if verb == "accept" else "Reject": "sig"}
        accepts = sum(1 for v in r["verdicts"].values() if "Accept" in v)
        if verb == "accept" and accepts >= current["doc"]["threshold"]:
            r["state"], cob["current"] = "accepted", rev
        print(f"✓ Revision {rev[:7]} {verb}ed")
    else:
        sys.stderr.write(f"fake rad: unsupported: rad id {verb}\n")
        return 2
    path.write_text(json.dumps(cob), encoding="utf-8")
    return 0


def _comment(author: str, body: str, reply_to: str = "") -> dict:
    c = {"author": author, "reactions": [], "resolved": False, "body": body,
         "edits": [{"author": author, "timestamp": 1795187355000, "body": body, "embeds": []}]}
    if reply_to:
        c["replyTo"] = reply_to
    return c


def _issue_cob(title: str, iid: str, author: str, description: str) -> dict:
    """An issue as `rad cob show --type xyz.radicle.issue` prints it in Radicle 1.10.3: the description is the thread's
    first comment, whose id is the issue's."""
    return {"assignees": [], "title": title, "state": {"status": "open"}, "labels": [],
            "thread": {"comments": {iid: _comment(author, description)}, "timeline": [iid]}}


def issue_box(iid: str, title: str, author: str, description: str, status: str = "open", comments=()) -> str:
    """`rad issue open` and `rad issue show` as Radicle 1.10.3 prints them with no terminal (checked against the real
    binary for the v3.1 polish, task 8.3): the issue's attributes in a rounded box (`Title`, `Issue`, `Author`,
    `Status`, each `│ Name   value │`), an empty row, then the description; `show` adds each later comment after a
    divider: `<author> (you) now <its short id>`, an empty row, its lines. The box is as wide as its widest line."""
    rows = [f"Title   {title}", f"Issue   {iid}", f"Author  {author} (you)", f"Status  {status}", "",
            *(description.splitlines() or [""])]
    parts = [[f"{a} (you) now {cid[:7]}", "", *(body.splitlines() or [""])] for cid, a, body in comments]
    width = max(len(x) for x in rows + [y for part in parts for y in part]) + 2
    line = "─" * width

    def row(text: str) -> str:
        return f"│ {text.ljust(width - 2)} │"

    out = [f"╭{line}╮", *map(row, rows)]
    for part in parts:
        out += [f"├{line}┤", *map(row, part)]
    return "\n".join(out + [f"╰{line}╯"])


def main(argv: list) -> int:
    home = Path(os.environ.get("RAD_HOME") or Path.home() / ".radicle")
    if argv[:2] == ["self", "--did"]:
        print(_me(home))
        return 0
    if argv[:1] == ["inspect"] and "--identity" in argv:
        rid = next((a for a in argv[1:] if a.startswith("rad:")), "")
        if not (home / "storage" / rid[4:]).is_dir():
            sys.stderr.write("rad inspect: repository not found\n")
            return 3
        _, cob = _id_cob(home)
        doc = cob["revisions"][cob["current"]]["doc"] if cob else {"delegates": [f"did:key:{DELEGATE}"], "threshold": 1}
        print(json.dumps(doc))
        return 0
    if argv[:1] == ["sync"]:
        if "--rid" in argv:
            sys.stderr.write("error: unexpected argument '--rid' found\n\nUsage: rad sync --fetch [RID]\n")
            return 2
        if (home / "sync-fails").exists():
            print("No seeds found.", flush=True)
            sys.stderr.write("✗ Error: no candidate seeds were found to fetch from\n")
            return 1
        return 0
    if argv[:2] == ["cob", "list"]:
        d = home / "cobs" / str(_opt(argv, "--type", ""))
        for f in sorted(d.glob("*.json")) if d.is_dir() else []:
            print(f.stem)
        return 0
    if argv[:2] == ["cob", "show"]:
        f = home / "cobs" / str(_opt(argv, "--type", "")) / f"{_opt(argv, '--object', '')}.json"
        if not f.is_file():
            sys.stderr.write("✗ Error: object not found\n")
            return 1
        print(json.dumps(json.loads(f.read_text(encoding="utf-8")), separators=(",", ":")))
        return 0
    if argv[:1] == ["id"]:
        return _identity(home, argv)
    if argv[:2] == ["issue", "open"]:
        title, desc = _opt(argv, "--title"), _opt(argv, "--description", "")
        if title is None:
            sys.stderr.write("rad issue open: --title is required\n")
            return 2
        iid = hashlib.sha1(json.dumps([title, desc, _me(home)]).encode()).hexdigest()
        d = home / "cobs" / ISSUE_TYPE
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{iid}.json").write_text(json.dumps(_issue_cob(title, iid, _me(home)[8:], desc)), encoding="utf-8")
        print(issue_box(iid, title, _me(home)[8:], desc))
        return 0
    if argv[:2] == ["issue", "show"]:
        rest = [x for i, x in enumerate(argv[2:]) if x != "--repo" and (i == 0 or argv[2:][i - 1] != "--repo")]
        issue = rest[0] if rest else ""
        d = home / "cobs" / ISSUE_TYPE
        found = sorted(d.glob(f"{issue}*.json")) if d.is_dir() and issue else []
        if len(found) != 1:
            sys.stderr.write(f"✗ Error: revspec '{issue}' not found; class=Reference (4); code=NotFound (-3)\n")
            return 1
        cob = json.loads(found[0].read_text(encoding="utf-8"))
        iid = found[0].stem
        first = cob["thread"]["comments"][cob["thread"]["timeline"][0]]
        override = home / "show-title"
        title = override.read_text(encoding="utf-8").strip() if override.is_file() else cob["title"]
        later = [(cid, cob["thread"]["comments"][cid]["author"], cob["thread"]["comments"][cid]["body"])
                 for cid in cob["thread"]["timeline"][1:]]
        print(issue_box(iid, title, first["author"], first["body"], cob["state"]["status"], later))
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
        d = home / "cobs" / ISSUE_TYPE
        found = sorted(d.glob(f"{issue}*.json")) if d.is_dir() else []
        if len(found) == 1:  # this node has the issue (a unique prefix, as rad takes it): the comment joins its thread
            cob = json.loads(found[0].read_text(encoding="utf-8"))
            thread = cob["thread"]
            cid = hashlib.sha1(json.dumps([found[0].stem, msg, len(thread["timeline"])]).encode()).hexdigest()
            thread["comments"][cid] = _comment(_me(home)[8:], msg, found[0].stem)
            thread["timeline"].append(cid)
            found[0].write_text(json.dumps(cob), encoding="utf-8")
        print(f"✓ commented on {issue[:7]}")
        return 0
    sys.stderr.write(f"fake rad: unsupported: {' '.join(argv)}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
