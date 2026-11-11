#!/usr/bin/env python3
"""The issue tracker, scrubbed, as issues in the private GitHub repository (proof-of-fix#178, #175).

GitHub is where invited readers get temporary read access; the code there (scripts/github_snapshot.py) cites the
tracker's issues (`#142`), so this copies them across, one way. Every issue and pull request becomes a GitHub issue with
the same number, so those links work: a pull request is titled `PR: …`, and a number the tracker no longer has gets a
closed placeholder. It stops if GitHub hands out a different number.

The same safeguards as the snapshot: the same terms file (--terms) scrubs every title, body, comment and label, and the
same scan stops everything on a leftover private term or a secret, naming the issue and the kind of finding, never the
value. No one is named or notified: authors become `owner` (whoever's token reads the tracker) or `contributor-N`, and an
`@login` outside code becomes that role, or loses its `@`. Dry run by default; --push writes. It refuses a target that
isn't private.

It's idempotent: titles, bodies, state and labels are updated in place, and each comment carries a hidden marker, so it
is edited, or deleted once it's gone from the tracker. Comments written on GitHub are left alone. GitHub allows about
500 new comments or issues an hour, so the first run takes a while; a rerun picks up where one stopped.

    FORGEJO_TOKEN=… scripts/github_issues.py                 # a dry run: what would change
    FORGEJO_TOKEN=… scripts/github_issues.py --push          # mirror it

FORGEJO_TOKEN needs only read:issue (and read:user); it's read from the environment, never from git's credentials.
Standard library; gh for GitHub."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIMIT = 65_000  # GitHub refuses a body over 65,536 characters
ISSUE_MARK = "<!-- forgejo:{} -->"
COMMENT_MARK = "<!-- forgejo-comment:{} -->"
ISSUE_MARK_RE = re.compile(r"<!-- forgejo:(\d+) -->")
COMMENT_MARK_RE = re.compile(r"<!-- forgejo-comment:(\d+) -->")
CODE_RE = re.compile(r"(```.*?```|~~~.*?~~~|`[^`\n]*`)", re.S)
MENTION_RE = re.compile(r"(?<![\w`/@.])@([A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?)")


def _snapshot():
    spec = importlib.util.spec_from_file_location("github_snapshot", HERE / "github_snapshot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


snap = _snapshot()


def fail(message: str) -> None:
    raise SystemExit(f"github-issues: {message}")


# ---------- the tracker ----------

class Forgejo:
    """Reads issues, pull requests and comments; the token goes in a header and is never printed."""

    def __init__(self, base: str, repo: str, token: str):
        self.base, self.repo, self.token = base.rstrip("/"), repo, token

    def get(self, path: str, params: dict = None):
        url = f"{self.base}/api/v1/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        req = urllib.request.Request(url, headers={"Authorization": f"token {self.token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            fail(f"the tracker answered HTTP {e.code} for {path}: check FORGEJO_TOKEN's scopes (read:issue, read:user)")

    def pages(self, path: str, params: dict) -> list:
        out, page = [], 1
        while True:
            batch = self.get(path, {**params, "limit": 50, "page": page})
            out += batch
            if len(batch) < 50:
                return out
            page += 1

    def login(self) -> str:
        return self.get("user")["login"]

    def items(self) -> list:
        return self.pages(f"repos/{self.repo}/issues", {"state": "all"})  # issues and pull requests

    def comments(self) -> list:
        return self.pages(f"repos/{self.repo}/issues/comments", {})


def forge_from_origin() -> tuple:
    """(base URL, owner/name) from this repository's origin, without any credentials in it."""
    url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout.decode().strip()
    m = re.match(r"https?://(?:[^@/]*@)?([^/]+)/([^/]+)/([^/]+?)(?:\.git)?$", url)
    if not m:
        fail("can't tell the tracker from origin: pass --forge-url and --repo")
    return f"https://{m.group(1)}", f"{m.group(2)}/{m.group(3)}"


# ---------- rendering ----------

def roles_for(owner: str, items: list, comments: list) -> dict:
    """login (lower case) -> `owner` or `contributor-N`, numbered by first appearance."""
    seen = sorted([(i["created_at"], i["user"]["login"]) for i in items] +
                  [(c["created_at"], c["user"]["login"]) for c in comments])
    roles = {owner.lower(): "owner"}
    for _, login in seen:
        if login.lower() not in roles:
            roles[login.lower()] = f"contributor-{sum(1 for r in roles.values() if r != 'owner') + 1}"
    return roles


def unmention(text: str, roles: dict) -> str:
    """No @login stays outside code: a known one becomes its role, any other loses its @ (GitHub would notify it)."""
    parts = CODE_RE.split(text)
    for k in range(0, len(parts), 2):
        parts[k] = MENTION_RE.sub(lambda m: roles.get(m.group(1).lower(), m.group(1)), parts[k])
    return "".join(parts)


def clean(text: str, roles: dict, replace: list) -> str:
    out = unmention((text or "").replace("\r\n", "\n"), roles)
    for old, new in replace:
        out = out.replace(old, new)
    return out


def fit(text: str, mark: str) -> str:
    if len(text) + len(mark) + 2 > LIMIT:
        text = text[:LIMIT - len(mark) - 200] + "\n\n_(Cut here: the rest is on the tracker.)_"
    return f"{text}\n\n{mark}"


def number_of(comment: dict) -> int:
    url = comment.get("issue_url") or comment.get("pull_request_url") or ""
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def render(items: list, comments: list, owner: str, replace: list) -> dict:
    """number -> {title, body, state, reason, labels, colors, comments: {comment id: body}}, every number up to the
    highest, with placeholders for gaps."""
    roles = roles_for(owner, items, comments)
    by_number = {i["number"]: i for i in items}
    out = {}
    for n in range(1, max(by_number, default=0) + 1):
        item = by_number.get(n)
        if item is None:
            out[n] = {"title": f"(no #{n} on the tracker)", "state": "closed", "reason": "not_planned", "labels": [],
                      "colors": {}, "comments": {},
                      "body": fit(f"_Number {n} isn't on the tracker any more; this keeps GitHub's numbers aligned._",
                                  ISSUE_MARK.format(n))}
            continue
        pr = item.get("pull_request")
        merged = bool(pr and (pr.get("merged") or pr.get("merged_at")))
        status = "merged" if merged else item["state"]
        author = roles.get(item["user"]["login"].lower(), "contributor")
        head = (f"_From the private tracker: {'pull request' if pr else 'issue'} #{n}, opened by {author} on "
                f"{item['created_at'][:10]}, {status}. A read-only copy: the discussion is on the tracker._")
        body = clean(head + "\n\n" + (item.get("body") or "_No description._"), roles, replace)
        labels = [lab for lab in (item.get("labels") or [])]
        out[n] = {
            "title": clean(("PR: " if pr else "") + item["title"], roles, replace),
            "body": fit(body, ISSUE_MARK.format(n)),
            "state": "closed" if item["state"] == "closed" else "open",
            "reason": "not_planned" if pr and not merged else "completed",
            "labels": sorted(clean(lab["name"], roles, replace) for lab in labels),
            "colors": {clean(lab["name"], roles, replace): (lab.get("color") or "ededed").lstrip("#") for lab in labels},
            "comments": {},
        }
    for c in sorted(comments, key=lambda c: c["id"]):
        n = number_of(c)
        if n not in out:
            continue
        who = roles.get(c["user"]["login"].lower(), "contributor")
        text = clean(f"**{who}** · {c['created_at'][:10]}\n\n{c.get('body') or ''}", roles, replace)
        out[n]["comments"][c["id"]] = fit(text, COMMENT_MARK.format(c["id"]))
    return out


def scan(desired: dict, replace: list, deny: list) -> list:
    """Findings as (where, kind): never the value."""
    literals = [("a private term", old) for old, _ in replace] + [("a denied term", d) for d in deny]
    found = []
    for n, d in desired.items():
        texts = [(f"#{n} title", d["title"]), (f"#{n} body", d["body"]), (f"#{n} labels", "\n".join(d["labels"]))]
        texts += [(f"#{n} comment {cid}", body) for cid, body in d["comments"].items()]
        for where, text in texts:
            for kind, literal in literals:
                if literal in text:
                    found.append((where, kind))
                    break
            for kind, pattern in snap.SECRET_PATTERNS.items():
                if re.search(pattern, text):
                    found.append((where, kind))
    return found


# ---------- GitHub ----------

class GitHub:
    """Through gh, so its sign-in is used and no token passes through here."""

    def __init__(self, repo: str, pause: float = 7.5, wait: float = 120.0):
        self.repo, self.pause, self.wait = repo, pause, wait

    def api(self, method: str, path: str, body: dict = None):
        args = ["gh", "api", "-X", method, path, "-H", "Accept: application/vnd.github+json"]
        if body is not None:
            args += ["--input", "-"]
        for attempt in range(10):
            r = subprocess.run(args, input=json.dumps(body).encode() if body is not None else None,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if not r.returncode:
                if method != "GET":
                    time.sleep(self.pause)
                return json.loads(r.stdout.decode()) if r.stdout.strip() else None
            err = (r.stderr + r.stdout).decode(errors="replace")
            if "rate limit" in err.lower() and attempt < 9:
                print(f"  GitHub's rate limit: waiting {self.wait:.0f} s")
                time.sleep(self.wait)
                continue
            fail(f"gh api {method} {path} failed: {err[-300:]}")

    def pages(self, path: str) -> list:
        out, page = [], 1
        while True:
            batch = self.api("GET", f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def issues(self) -> dict:
        return {i["number"]: {"title": i["title"], "body": (i.get("body") or "").replace("\r\n", "\n"),
                              "state": i["state"], "labels": sorted(lab["name"] for lab in i["labels"])}
                for i in self.pages(f"repos/{self.repo}/issues?state=all")}

    def comments(self) -> dict:
        """tracker comment id -> (GitHub comment id, issue number, body), for the comments this script wrote."""
        out = {}
        for c in self.pages(f"repos/{self.repo}/issues/comments"):
            m = COMMENT_MARK_RE.search(c.get("body") or "")
            if m:
                out[int(m.group(1))] = (c["id"], int(c["issue_url"].rsplit("/", 1)[-1]),
                                        (c.get("body") or "").replace("\r\n", "\n"))
        return out

    def labels(self) -> set:
        return {lab["name"] for lab in self.pages(f"repos/{self.repo}/labels")}


def github_repo(name: str) -> str:
    login = json.loads(snap.run(["gh", "api", "user"]))["login"]
    view = json.loads(snap.run(["gh", "repo", "view", f"{login}/{name}", "--json", "visibility"]))
    if view["visibility"] != "PRIVATE":
        fail(f"{login}/{name} isn't private: refusing. Going public is the owner's own step.")
    return f"{login}/{name}"


# ---------- the plan ----------

def plan(desired: dict, issues: dict, comments: dict) -> list:
    """Actions in the order they must run: issues in number order, each followed by its comments."""
    actions = []
    for n in sorted(desired):
        d, cur = desired[n], issues.get(n)
        if cur is None:
            actions.append(("create", n, None))
        else:
            m = ISSUE_MARK_RE.search(cur["body"])
            if not m or int(m.group(1)) != n:
                fail(f"GitHub's #{n} isn't the tracker's #{n}: refusing to touch it")
            fields = [f for f in ("title", "body", "state", "labels") if cur[f] != d[f]]
            if fields:
                actions.append(("update", n, fields))
        for cid, body in d["comments"].items():
            have = comments.get(cid)
            if have is None:
                actions.append(("comment", n, cid))
            elif have[2] != body:
                actions.append(("edit-comment", n, cid))
    wanted = {cid for d in desired.values() for cid in d["comments"]}
    actions += [("delete-comment", have[1], cid) for cid, have in sorted(comments.items()) if cid not in wanted]
    return actions


def apply(gh: GitHub, desired: dict, actions: list, comments: dict) -> None:
    have = gh.labels()
    for name, color in sorted({(k, v) for d in desired.values() for k, v in d["colors"].items()}):
        if name not in have:
            gh.api("POST", f"repos/{gh.repo}/labels", {"name": name, "color": color})
            have.add(name)
    r = gh.repo
    for k, (kind, n, extra) in enumerate(actions, 1):
        d = desired.get(n)
        if kind == "create":
            made = gh.api("POST", f"repos/{r}/issues", {"title": d["title"], "body": d["body"], "labels": d["labels"]})
            if made["number"] != n:
                fail(f"GitHub numbered the tracker's #{n} as #{made['number']}: stopping (numbers must match)")
            if d["state"] == "closed":
                gh.api("PATCH", f"repos/{r}/issues/{n}", {"state": "closed", "state_reason": d["reason"]})
        elif kind == "update":
            patch = {f: d[f] for f in extra}
            if "state" in extra and d["state"] == "closed":
                patch["state_reason"] = d["reason"]
            gh.api("PATCH", f"repos/{r}/issues/{n}", patch)
        elif kind == "comment":
            gh.api("POST", f"repos/{r}/issues/{n}/comments", {"body": d["comments"][extra]})
        elif kind == "edit-comment":
            gh.api("PATCH", f"repos/{r}/issues/comments/{comments[extra][0]}", {"body": d["comments"][extra]})
        elif kind == "delete-comment":
            gh.api("DELETE", f"repos/{r}/issues/comments/{comments[extra][0]}")
        if k % 25 == 0:
            print(f"  {k}/{len(actions)} done")


def main(argv=None, forge: Forgejo = None, gh: GitHub = None) -> int:
    ap = argparse.ArgumentParser(description="The tracker's issues, scrubbed, in the private GitHub repository "
                                             "(dry run by default).")
    ap.add_argument("--target", default="proof-of-fix", help="the GitHub repository under the signed-in account")
    ap.add_argument("--forge-url", help="the tracker's base URL (default: from origin)")
    ap.add_argument("--repo", help="the tracker's owner/name (default: from origin)")
    ap.add_argument("--terms", default=os.environ.get("POF_SNAPSHOT_TERMS", snap.DEFAULT_TERMS))
    ap.add_argument("--pause", type=float, default=7.5, help="seconds after each write (GitHub: ~500 an hour)")
    ap.add_argument("--push", action="store_true", help="write to GitHub when the scan is clean")
    a = ap.parse_args(argv)

    replace, deny = snap.read_terms(Path(a.terms).expanduser())
    if forge is None:
        token = os.environ.get("FORGEJO_TOKEN")
        if not token:
            fail("set FORGEJO_TOKEN (read:issue, read:user) in the environment")
        base, repo = forge_from_origin()
        forge = Forgejo(a.forge_url or base, a.repo or repo, token)
    if gh is None:
        gh = GitHub(github_repo(a.target), pause=a.pause)

    items, comments = forge.items(), forge.comments()
    desired = render(items, comments, forge.login(), replace)
    print(f"tracker: {len(items)} issues and pull requests, {len(comments)} comments, numbers 1-{len(desired)}")
    found = scan(desired, replace, deny)
    if found:
        for where, kind in found:
            print(f"  FOUND {kind}: {where}")
        print(f"{len(found)} finding(s): nothing written")
        return 1
    print("the scan is clean")

    have_comments = gh.comments()
    actions = plan(desired, gh.issues(), have_comments)
    counts = {}
    for kind, *_ in actions:
        counts[kind] = counts.get(kind, 0) + 1
    if not actions:
        print(f"{gh.repo}: up to date")
        return 0
    writes = len(actions) + sum(1 for k, n, _ in actions if k == "create" and desired[n]["state"] == "closed")
    print(f"{gh.repo}: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
          + f" ({writes} writes, about {writes * a.pause / 60:.0f} min)")
    for kind, n, extra in actions[:20]:
        print(f"  {kind} #{n}" + (f": {', '.join(extra)}" if kind == "update" else ""))
    if not a.push:
        print("a dry run: nothing written (--push to write)")
        return 0
    apply(gh, desired, actions, have_comments)
    print(f"{gh.repo}: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
