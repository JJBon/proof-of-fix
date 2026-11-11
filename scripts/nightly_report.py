#!/usr/bin/env python3
"""The nightly integration run's report (proof-of-fix#152's third box): .forgejo/workflows/nightly.yml runs
scripts/integration.sh against the throwaway local devnet on the test runner and hands this script the suite's log and
the step's outcome.

It prints a short summary (the scenarios passed and failed, the books' totals, what wasn't run and why) to the job log,
and also to $GITHUB_STEP_SUMMARY when the runner sets it. With --issue it keeps one tracking issue on the forge, titled
TITLE below:

- a failed run opens it, or comments on it if it's open, or reopens the latest closed one and comments;
- a passing run comments that it passed and closes it, if one is open; otherwise it does nothing.

    scripts/nightly_report.py --log nightly-integration.log --outcome failure                # the summary only
    TOKEN=… scripts/nightly_report.py --log … --outcome failure --issue --run-url URL     # and the tracking issue

The forge, the repository and the token come from the environment: GITHUB_SERVER_URL, GITHUB_REPOSITORY and TOKEN (the
workflow's own github.token, which can write this repository's issues). The token is only ever sent in a header; it's
never printed and never on a command line. Standard library only."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TITLE = "Nightly integration run failing"
LABEL = "type/bug"  # an organization label (Something is broken)
SCENARIOS = ("1", "2", "3", "4", "5", "6", "7")  # tests/integration/suite.py's, without --radicle
MAX_FAILURES = 20  # FAILED lines quoted in the summary
MAX_PAGES = 10  # of 50 issues each, when looking for the tracking issue


class Result:
    def __init__(self):
        self.passed: list = []  # scenarios, as the suite's "scenarios passed:" line has them
        self.failures: list = []  # the suite's FAILED lines, without "FAILED: "
        self.books = ""  # "charged by the meter: …"
        self.verdict = ""  # the suite's "result: …" line
        self.errors: list = []  # the wrapper's own "integration: …" refusals

    @property
    def failed(self) -> list:
        """The scenarios (and "books") named in FAILED lines, in order, once each."""
        seen = []
        for f in self.failures:
            m = re.match(r"scenario (\S+?):", f)
            if m and m.group(1) not in seen:
                seen.append(m.group(1))
        return seen


def parse(text: str) -> Result:
    r = Result()
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith("scenarios passed: "):
            rest = line[len("scenarios passed: "):]
            r.passed = [] if rest == "none" else [s.strip() for s in rest.split(",") if s.strip()]
        elif line.startswith("FAILED: "):
            r.failures.append(line[len("FAILED: "):])
        elif line.startswith("charged by the meter: "):
            r.books = line
        elif line.startswith("result: "):
            r.verdict = line[len("result: "):]
        elif line.startswith("integration: "):
            r.errors.append(line)
    return r


def summary(r: Result, ok: bool, outcome: str, scenarios=SCENARIOS, notes=(), run_url: str = "") -> str:
    failed = r.failed
    missing = [s for s in scenarios if s not in r.passed and s not in failed]
    lines = [f"## Nightly integration run: {'passed' if ok else 'FAILED'}", "",
             "Target: the throwaway local devnet on the test runner (anvil's public test keys), the fake judge.", "",
             f"- scenarios passed: {', '.join(r.passed) or 'none'}",
             f"- scenarios failed: {', '.join(failed) or 'none'}"]
    if missing and not ok:
        lines.append(f"- scenarios with no result: {', '.join(missing)} (the suite stopped before reporting them)")
    lines.append(f"- the books: {r.books[len('charged by the meter: '):] if r.books else 'not reached'}")
    lines.append(f"- the suite's verdict: {r.verdict or 'none (it did not finish)'}; the step's outcome: {outcome}")
    lines += [f"- {n}" for n in notes]
    if run_url:
        lines.append(f"- run: {run_url}")
    if r.errors:
        lines += ["", "The wrapper refused:", ""] + [f"    {e}" for e in r.errors]
    if r.failures:
        lines += ["", "Failures:", ""] + [f"    {f}" for f in r.failures[:MAX_FAILURES]]
        if len(r.failures) > MAX_FAILURES:
            lines.append(f"    … and {len(r.failures) - MAX_FAILURES} more (see the run's log)")
    return "\n".join(lines) + "\n"


class ApiError(Exception):
    """A forge API call that failed. The message carries the status and the forge's message, never the token."""


class Forge:
    def __init__(self, server: str, repo: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
            raise ApiError(f"unexpected repository name {repo!r}")
        self.base = f"{server.rstrip('/')}/api/v1/repos/{repo}"
        self._token = token

    def __repr__(self) -> str:  # never the token
        return f"Forge({self.base!r})"

    def call(self, method: str, path: str, body: dict = None, query: dict = None):
        url = self.base + path + ("?" + urllib.parse.urlencode(query) if query else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"token {self._token}", "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {})})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read() or b"{}").get("message", "")
            except ValueError:
                message = ""
            hint = (" (the token can't write this repository's issues: give the workflow a token with write:issue, "
                    "see .forgejo/workflows/nightly.yml)") if e.code in (401, 403) else ""
            raise ApiError(f"{method} {path}: HTTP {e.code} {message}".rstrip() + hint) from None
        except urllib.error.URLError as e:
            raise ApiError(f"{method} {path}: {e.reason}") from None
        return json.loads(raw) if raw else None

    def tracking_issues(self) -> list:
        """Every issue (not pull request) titled exactly TITLE, open or closed."""
        found = []
        for page in range(1, MAX_PAGES + 1):
            batch = self.call("GET", "/issues", query={"state": "all", "type": "issues", "q": TITLE, "limit": 50,
                                                       "page": page}) or []
            found += [i for i in batch if i.get("title") == TITLE and not i.get("pull_request")]
            if len(batch) < 50:
                break
        return found

    def comment(self, number: int, body: str) -> None:
        self.call("POST", f"/issues/{number}/comments", {"body": body})

    def set_state(self, number: int, state: str) -> None:
        self.call("PATCH", f"/issues/{number}", {"state": state})

    def create(self, body: str) -> int:
        return self.call("POST", "/issues", {"title": TITLE, "body": body})["number"]

    def add_label(self, number: int, name: str) -> None:
        self.call("POST", f"/issues/{number}/labels", {"labels": [name]})  # by name: the organization's labels too


def track(forge: Forge, ok: bool, text: str, label: str = LABEL) -> str:
    """Opens, updates, reopens or closes the one tracking issue. Returns what it did, for the log."""
    issues = forge.tracking_issues()
    open_ = sorted((i for i in issues if i.get("state") == "open"), key=lambda i: i["number"])
    closed = sorted((i for i in issues if i.get("state") != "open"), key=lambda i: i["number"])
    if ok:
        if not open_:
            return "passed; no tracking issue is open"
        n = open_[0]["number"]
        forge.comment(n, "The nightly integration run passed.\n\n" + text)
        forge.set_state(n, "closed")
        return f"passed: commented on #{n} and closed it"
    if open_:
        n = open_[0]["number"]
        forge.comment(n, "The nightly integration run failed again.\n\n" + text)
        return f"failed: commented on #{n}"
    if closed:
        n = closed[-1]["number"]
        forge.set_state(n, "open")
        forge.comment(n, "The nightly integration run is failing again.\n\n" + text)
        return f"failed: reopened #{n} and commented"
    n = forge.create("The nightly integration run (.forgejo/workflows/nightly.yml, proof-of-fix#152) failed. Each later "
                     "failure adds a comment here; the next passing run comments and closes this issue.\n\n" + text)
    try:
        forge.add_label(n, label)
    except ApiError as e:
        print(f"nightly: opened #{n} but couldn't label it {label}: {e}", file=sys.stderr)
    return f"failed: opened #{n}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--log", required=True, help="the suite's output (missing: the suite didn't run)")
    ap.add_argument("--outcome", required=True, help="the integration step's outcome: success, failure, cancelled, skipped")
    ap.add_argument("--only", default="", help="the scenarios that were asked for, comma-separated; empty for all")
    ap.add_argument("--note", action="append", default=[], help="a line added to the summary (repeatable)")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--issue", action="store_true", help="open, update or close the tracking issue")
    ap.add_argument("--label", default=LABEL)
    args = ap.parse_args(argv)

    log = Path(args.log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.is_file() else ""
    r = parse(text)
    if not text:
        r.errors.append("nightly: no log from the suite: an earlier step (checkout, toolchain) failed; see the job log")
    ok = args.outcome == "success"
    scenarios = tuple(s for s in args.only.split(",") if s) or SCENARIOS
    report = summary(r, ok, args.outcome, scenarios, args.note, args.run_url)
    print(report)
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        try:
            with Path(step_summary).open("a", encoding="utf-8") as f:
                f.write(report)
        except OSError as e:
            print(f"nightly: couldn't write the job summary: {e}", file=sys.stderr)
    if not args.issue:
        return 0
    server, repo, token = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "TOKEN"))
    if not (server and repo and token):
        print("nightly: --issue needs GITHUB_SERVER_URL, GITHUB_REPOSITORY and TOKEN in the environment", file=sys.stderr)
        return 2
    try:
        print("nightly: " + track(Forge(server, repo, token), ok, report, args.label))
    except ApiError as e:
        print(f"nightly: the tracking issue wasn't updated: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
