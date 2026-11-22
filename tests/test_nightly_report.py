"""scripts/nightly_report.py (#152's third box): the nightly run's summary from the suite's log, and the one tracking
issue, against a fake forge API on the loopback (no network beyond it). The token only ever travels in a header."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "nightly-" + "5e" * 20
REPO = "acme/pof"


def load():
    spec = importlib.util.spec_from_file_location("nightly_report", ROOT / "scripts" / "nightly_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nr = load()

PASSING = """== 6. joining: a new engineer's own key joins seat 6 ==
  7 active seats; whether the engineer is drawn is checked at the end
charged by the meter: 0.270000 for 9 checks; withdrawn: 0.270000; the engineer was drawn for 2 submission(s)

not covered here: the leaderboard (#151 isn't built)
scenarios passed: 1, 2, 3, 4, 5, 6, 7
result: the integration suite passed
"""

FAILING = """charged by the meter: 0.240000 for 8 checks; withdrawn: 0.210000; the engineer was drawn for 1 submission(s)
FAILED: scenario 3: crashed: Reverted: TooLate
FAILED: scenario books: withdrawn 210000 != charged 240000
FAILED: scenario 3: the late fix was checked
scenarios passed: 1, 2, 4, 6
result: 3 failed
"""


class FakeForge:
    """Just enough of Forgejo's issues API: list (q, state, type, paging), create, comment, edit state, add labels."""

    def __init__(self, issues=()):
        self.issues = {i["number"]: dict(i) for i in issues}
        self.comments: list = []  # (number, body)
        self.labels: dict = {}  # number -> [names]
        self.requests: list = []  # (method, path, query, the Authorization header)
        self.deny = False  # answer 403 to writes, as a read-only token would get

    def __enter__(self):
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def reply(self, code, body=None):
                raw = json.dumps(body).encode() if body is not None else b""
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def handle_any(self):
                url = urllib.parse.urlsplit(self.path)
                query = dict(urllib.parse.parse_qsl(url.query))
                auth = self.headers.get("Authorization", "")
                fake.requests.append((self.command, url.path, query, auth))
                if auth != f"token {TOKEN}":
                    return self.reply(401, {"message": "token is required"})
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                if fake.deny and self.command != "GET":
                    return self.reply(403, {"message": "user should have a permission to write to a repo"})
                prefix = f"/api/v1/repos/{REPO}/issues"
                if not url.path.startswith(prefix):
                    return self.reply(404, {"message": "not found"})
                rest = url.path[len(prefix):].strip("/").split("/") if url.path != prefix else []
                return fake.route(self, rest, query, body)

            do_GET = do_POST = do_PATCH = handle_any

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def route(self, h, rest, query, body):
        if not rest and h.command == "GET":
            found = [i for i in sorted(self.issues.values(), key=lambda i: -i["number"])
                     if (query.get("state", "open") == "all" or i["state"] == query.get("state", "open"))
                     and (query.get("type") != "issues" or not i.get("pull_request"))
                     and query.get("q", "").lower() in i["title"].lower()]
            limit, page = int(query.get("limit", 30)), int(query.get("page", 1))
            return h.reply(200, found[(page - 1) * limit:page * limit])
        if not rest and h.command == "POST":
            n = max(self.issues, default=0) + 1
            self.issues[n] = {"number": n, "title": body["title"], "body": body["body"], "state": "open"}
            return h.reply(201, self.issues[n])
        n = int(rest[0])
        if n not in self.issues:
            return h.reply(404, {"message": "issue not found"})
        if len(rest) == 1 and h.command == "PATCH":
            self.issues[n]["state"] = body["state"]
            return h.reply(201, self.issues[n])
        if rest[1:] == ["comments"] and h.command == "POST":
            self.comments.append((n, body["body"]))
            return h.reply(201, {"id": len(self.comments), "body": body["body"]})
        if rest[1:] == ["labels"] and h.command == "POST":
            self.labels.setdefault(n, []).extend(body["labels"])
            return h.reply(200, [{"name": x} for x in self.labels[n]])
        return h.reply(405, {"message": "not here"})

    def forge(self):
        return nr.Forge(self.url, REPO, TOKEN)


def issue(n, title=None, state="open", pr=False):
    return {"number": n, "title": title or nr.TITLE, "state": state, "pull_request": {"merged": False} if pr else None}


class TestParse(unittest.TestCase):
    def test_a_passing_log(self):
        r = nr.parse(PASSING)
        self.assertEqual(r.passed, list("1234567"))
        self.assertEqual(r.failed, [])
        self.assertIn("0.270000 for 9 checks", r.books)
        self.assertEqual(r.verdict, "the integration suite passed")

    def test_a_failing_log_names_each_failed_scenario_once(self):
        r = nr.parse(FAILING)
        self.assertEqual(r.passed, ["1", "2", "4", "6"])
        self.assertEqual(r.failed, ["3", "books"])
        self.assertEqual(len(r.failures), 3)
        self.assertEqual(r.verdict, "3 failed")

    def test_the_wrappers_refusal_and_an_empty_log(self):
        r = nr.parse("integration: Docker isn't reachable\n")
        self.assertEqual(r.errors, ["integration: Docker isn't reachable"])
        self.assertEqual((r.passed, r.failures, r.books, r.verdict), ([], [], "", ""))
        self.assertEqual(nr.parse("scenarios passed: none\n").passed, [])


class TestSummary(unittest.TestCase):
    def test_passed(self):
        text = nr.summary(nr.parse(PASSING), True, "success", notes=["scenario 8: not run"], run_url="https://f/r/1")
        self.assertIn("Nightly integration run: passed", text)
        self.assertIn("scenarios passed: 1, 2, 3, 4, 5, 6, 7", text)
        self.assertIn("scenarios failed: none", text)
        self.assertIn("the books: 0.270000 for 9 checks; withdrawn: 0.270000", text)
        self.assertIn("- scenario 8: not run", text)
        self.assertIn("- run: https://f/r/1", text)
        self.assertNotIn("no result", text)

    def test_failed_lists_failures_and_scenarios_with_no_result(self):
        text = nr.summary(nr.parse(FAILING), False, "failure")
        self.assertIn("Nightly integration run: FAILED", text)
        self.assertIn("scenarios failed: 3, books", text)
        self.assertIn("scenarios with no result: 5, 7", text)
        self.assertIn("scenario books: withdrawn 210000 != charged 240000", text)

    def test_only_narrows_what_is_expected(self):
        text = nr.summary(nr.parse("scenarios passed: 2, 6\nresult: 1 failed\nFAILED: scenario 2: x\n"), False,
                          "failure", scenarios=("2", "6"))
        self.assertNotIn("no result", text)

    def test_a_long_list_of_failures_is_cut(self):
        log = "".join(f"FAILED: scenario 1: problem {k}\n" for k in range(nr.MAX_FAILURES + 5))
        text = nr.summary(nr.parse(log), False, "failure")
        self.assertIn("and 5 more", text)
        self.assertNotIn(f"problem {nr.MAX_FAILURES}\n", text)


class TestTrack(unittest.TestCase):
    def test_a_first_failure_opens_the_issue_and_labels_it(self):
        with FakeForge([issue(1, "Nightly integration run failing in a fork", state="open")]) as f:
            did = nr.track(f.forge(), False, "the summary")
        self.assertEqual(did, "failed: opened #2")
        self.assertEqual(f.issues[2]["title"], nr.TITLE)
        self.assertIn("the summary", f.issues[2]["body"])
        self.assertEqual(f.labels, {2: [nr.LABEL]})
        self.assertEqual(f.comments, [])

    def test_a_later_failure_comments_instead_of_opening_another(self):
        with FakeForge([issue(4), issue(5, pr=True)]) as f:
            did = nr.track(f.forge(), False, "second")
        self.assertEqual(did, "failed: commented on #4")
        self.assertEqual(len(f.issues), 2)
        self.assertEqual(f.comments, [(4, "The nightly integration run failed again.\n\nsecond")])

    def test_a_failure_after_a_close_reopens_the_latest(self):
        with FakeForge([issue(3, state="closed"), issue(7, state="closed")]) as f:
            did = nr.track(f.forge(), False, "back")
        self.assertEqual(did, "failed: reopened #7 and commented")
        self.assertEqual((f.issues[3]["state"], f.issues[7]["state"]), ("closed", "open"))
        self.assertEqual(f.comments[0][0], 7)

    def test_a_pass_comments_and_closes(self):
        with FakeForge([issue(4)]) as f:
            did = nr.track(f.forge(), True, "all good")
        self.assertEqual(did, "passed: commented on #4 and closed it")
        self.assertEqual(f.issues[4]["state"], "closed")
        self.assertEqual(f.comments, [(4, "The nightly integration run passed.\n\nall good")])

    def test_a_pass_with_nothing_open_writes_nothing(self):
        with FakeForge([issue(3, state="closed")]) as f:
            self.assertEqual(nr.track(f.forge(), True, "fine"), "passed; no tracking issue is open")
        self.assertEqual([m for m, *_ in f.requests], ["GET"])

    def test_the_search_pages_through(self):
        others = [issue(n, f"{nr.TITLE} (old copy {n})", state="closed") for n in range(1, 61)]
        with FakeForge(others + [issue(0)]) as f:
            self.assertEqual(nr.track(f.forge(), False, "x"), "failed: commented on #0")
        self.assertEqual([q.get("page") for m, _, q, _ in f.requests if m == "GET"], ["1", "2"])

    def test_a_label_that_cant_be_added_doesnt_lose_the_issue(self):
        with FakeForge() as f:
            forge = f.forge()
            with mock.patch.object(forge, "add_label", side_effect=nr.ApiError("HTTP 422")), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(nr.track(forge, False, "x"), "failed: opened #1")
        self.assertIn("couldn't label it", err.getvalue())


class TestToken(unittest.TestCase):
    def test_the_token_travels_in_the_header_only(self):
        with FakeForge([issue(4)]) as f:
            nr.track(f.forge(), False, "x")
        for method, path, query, auth in f.requests:
            self.assertEqual(auth, f"token {TOKEN}")
            self.assertNotIn(TOKEN, path + json.dumps(query))
        self.assertNotIn(TOKEN, repr(f.forge()))

    def test_a_token_that_cant_write_says_so_without_printing_it(self):
        with tempfile.TemporaryDirectory() as tmp, FakeForge() as f:
            log = Path(tmp) / "log"
            log.write_text(FAILING, encoding="utf-8")
            f.deny = True
            env = {"GITHUB_SERVER_URL": f.url, "GITHUB_REPOSITORY": REPO, "TOKEN": TOKEN}
            with mock.patch.dict(os.environ, env, clear=False), contextlib.redirect_stdout(io.StringIO()) as out, \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                os.environ.pop("GITHUB_STEP_SUMMARY", None)
                code = nr.main(["--log", str(log), "--outcome", "failure", "--issue"])
        self.assertEqual(code, 1)
        self.assertIn("HTTP 403", err.getvalue())
        self.assertIn("write:issue", err.getvalue())
        self.assertNotIn(TOKEN, out.getvalue() + err.getvalue())

    def test_a_wrong_repository_name_is_refused(self):
        with self.assertRaises(nr.ApiError):
            nr.Forge("https://forge.example", "acme/pof/../../admin", TOKEN)


class TestMain(unittest.TestCase):
    def run_main(self, argv, env):
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(io.StringIO()) as out, \
                contextlib.redirect_stderr(io.StringIO()) as err:
            code = nr.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_the_summary_goes_to_the_log_and_the_job_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, step = Path(tmp) / "log", Path(tmp) / "summary.md"
            log.write_text(PASSING, encoding="utf-8")
            code, out, _ = self.run_main(["--log", str(log), "--outcome", "success", "--note", "radicle: not run"],
                                         {"GITHUB_STEP_SUMMARY": str(step)})
            self.assertEqual(code, 0)
            self.assertIn("Nightly integration run: passed", out)
            self.assertEqual(step.read_text(encoding="utf-8").strip(), out.strip())

    def test_a_missing_log_is_a_failure_said_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_main(["--log", str(Path(tmp) / "none"), "--outcome", "skipped"], {})
        self.assertEqual(code, 0)
        self.assertIn("FAILED", out)
        self.assertIn("an earlier step (checkout, toolchain) failed", out)

    def test_the_issue_needs_its_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, err = self.run_main(["--log", str(Path(tmp) / "none"), "--outcome", "failure", "--issue"], {})
        self.assertEqual(code, 2)
        self.assertIn("TOKEN", err)

    def test_end_to_end_against_the_fake(self):
        with tempfile.TemporaryDirectory() as tmp, FakeForge() as f:
            log = Path(tmp) / "log"
            log.write_text(FAILING, encoding="utf-8")
            env = {"GITHUB_SERVER_URL": f.url, "GITHUB_REPOSITORY": REPO, "TOKEN": TOKEN}
            code, out, _ = self.run_main(["--log", str(log), "--outcome", "failure", "--issue",
                                          "--run-url", "https://forge.example/acme/pof/actions/runs/9"], env)
            self.assertEqual(code, 0)
            self.assertIn("nightly: failed: opened #1", out)
            self.assertIn("actions/runs/9", f.issues[1]["body"])
            log.write_text(PASSING, encoding="utf-8")
            code, out, _ = self.run_main(["--log", str(log), "--outcome", "success", "--issue"], env)
            self.assertIn("nightly: passed: commented on #1 and closed it", out)
            self.assertEqual(f.issues[1]["state"], "closed")
        self.assertNotIn(TOKEN, out)


if __name__ == "__main__":
    unittest.main()
