"""scripts/github_issues.py (#178): rendering, the scrub and scan, mentions, the plan and number alignment, against a
fake tracker and a fake GitHub in memory."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = "acme-" + "internal.test"


def load():
    spec = importlib.util.spec_from_file_location("github_issues", ROOT / "scripts" / "github_issues.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gi = load()


def item(n, title, body="", login="boss", state="open", pr=None, labels=(), day="2026-10-01"):
    return {"number": n, "title": title, "body": body, "state": state, "user": {"login": login},
            "created_at": f"{day}T00:00:00Z", "pull_request": pr,
            "labels": [{"name": name, "color": "0e8a16"} for name in labels]}


def comment(cid, n, body, login="boss", day="2026-10-02"):
    return {"id": cid, "issue_url": f"https://forge.example/api/v1/repos/o/r/issues/{n}", "body": body,
            "user": {"login": login}, "created_at": f"{day}T00:00:00Z"}


class FakeForge:
    def __init__(self, items, comments, login="boss"):
        self._items, self._comments, self._login = items, comments, login

    def items(self):
        return self._items

    def comments(self):
        return self._comments

    def login(self):
        return self._login


class FakeGitHub(gi.GitHub):
    """GitHub's numbering (shared, sequential) and its comment ids, in memory."""

    def __init__(self, skip_numbers=0):
        super().__init__("me/proof-of-fix", pause=0)
        self.store, self.notes, self.label_names, self.next_comment = {}, {}, set(), 1000
        self.next_number = 1 + skip_numbers
        self.writes = 0

    def api(self, method, path, body=None):
        parts = path.split("?")[0].split("/")[3:]
        if method != "GET":
            self.writes += 1
        if method == "GET":
            raise AssertionError("reads go through pages()")
        if parts == ["labels"]:
            self.label_names.add(body["name"])
            return {}
        if parts == ["issues"] and method == "POST":
            n, self.next_number = self.next_number, self.next_number + 1
            self.store[n] = {"title": body["title"], "body": body["body"], "state": "open",
                             "labels": sorted(body.get("labels", []))}
            return {"number": n}
        if parts[0] == "issues" and parts[1] == "comments":
            cid = int(parts[2])
            if method == "DELETE":
                del self.notes[cid]
            else:
                self.notes[cid]["body"] = body["body"]
            return {}
        if parts[0] == "issues" and len(parts) == 2:
            self.store[int(parts[1])].update({k: v for k, v in body.items() if k != "state_reason"})
            return {}
        if parts[0] == "issues" and parts[2] == "comments":
            self.next_comment += 1
            self.notes[self.next_comment] = {"n": int(parts[1]), "body": body["body"]}
            return {}
        raise AssertionError(path)

    def issues(self):
        return {n: dict(v) for n, v in self.store.items()}

    def comments(self):
        out = {}
        for gid, c in self.notes.items():
            m = gi.COMMENT_MARK_RE.search(c["body"])
            if m:
                out[int(m.group(1))] = (gid, c["n"], c["body"])
        return out

    def labels(self):
        return set(self.label_names)


class IssuesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.terms = Path(self.tmp.name) / "terms"
        self.terms.write_text(f"{PRIVATE} => example.com\ndeny: forbidden-literal\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, forge, gh, push=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gi.main(["--terms", str(self.terms)] + (["--push"] if push else []), forge=forge, gh=gh)
        return code, out.getvalue()

    def tracker(self):
        items = [item(1, "First", f"see https://{PRIVATE}/x, thanks @boss and @Ana"),
                 item(2, "A fix", "Requested by @boss", pr={"merged": True}, state="closed", labels=["type/bug"]),
                 item(4, "Later", "`@types/node` stays\n```\n@decorator\n```\nbut @ghost loses it", login="ana",
                      day="2026-10-03")]
        comments = [comment(10, 1, "first comment by @ana", login="ana", day="2026-10-02"),
                    comment(11, 4, "second")]
        return items, comments

    def test_numbers_align_with_placeholders(self):
        gh = FakeGitHub()
        code, out = self.run_main(FakeForge(*self.tracker()), gh)
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(gh.store), [1, 2, 3, 4])
        self.assertEqual(gh.store[2]["title"], "PR: A fix")
        self.assertEqual(gh.store[2]["state"], "closed")
        self.assertEqual(gh.store[3]["state"], "closed")
        self.assertIn("isn't on the tracker", gh.store[3]["body"])
        self.assertEqual(gh.store[2]["labels"], ["type/bug"])
        self.assertIn("type/bug", gh.label_names)

    def test_scrubbed_and_nobody_named_or_notified(self):
        gh = FakeGitHub()
        self.run_main(FakeForge(*self.tracker()), gh)
        one = gh.store[1]["body"]
        self.assertNotIn(PRIVATE, one)
        self.assertIn("https://example.com/x", one)
        self.assertIn("thanks owner and contributor-1", one)  # ana first appears in comment 10
        self.assertIn("Requested by owner", gh.store[2]["body"])
        four = gh.store[4]["body"]
        self.assertIn("`@types/node` stays", four)  # code is untouched
        self.assertIn("@decorator", four)
        self.assertIn("but ghost loses it", four)
        self.assertIn("opened by contributor-1", four)
        bodies = [c["body"] for c in gh.notes.values()]
        self.assertTrue(any(b.startswith("**contributor-1**") and "by contributor-1" in b for b in bodies))
        self.assertNotIn("@ana", "".join(bodies + [v["body"] for v in gh.store.values()]))

    def test_a_finding_stops_everything(self):
        items, comments = self.tracker()
        comments.append(comment(12, 1, "oops forbidden-literal here"))
        gh = FakeGitHub()
        code, out = self.run_main(FakeForge(items, comments), gh)
        self.assertEqual(code, 1)
        self.assertIn("FOUND a denied term: #1 comment 12", out)
        self.assertNotIn("oops", out)  # never the value
        self.assertEqual(gh.writes, 0)

    def test_dry_run_writes_nothing(self):
        gh = FakeGitHub()
        code, out = self.run_main(FakeForge(*self.tracker()), gh, push=False)
        self.assertEqual((code, gh.writes), (0, 0))
        self.assertIn("4 create", out)
        self.assertIn("2 comment", out)

    def test_idempotent_then_follows_edits_and_deletions(self):
        items, comments = self.tracker()
        gh = FakeGitHub()
        self.run_main(FakeForge(items, comments), gh)
        writes = gh.writes
        code, out = self.run_main(FakeForge(items, comments), gh)
        self.assertEqual((code, gh.writes), (0, writes))
        self.assertIn("up to date", out)
        items[0]["title"] = "First, renamed"
        items[0]["state"] = "closed"
        comments[0]["body"] = "edited"
        del comments[1]
        gh.notes[5000] = {"n": 1, "body": "a reader's own comment"}
        self.run_main(FakeForge(items + [item(5, "New")], comments), gh)
        self.assertEqual(gh.store[1]["title"], "First, renamed")
        self.assertEqual(gh.store[1]["state"], "closed")
        self.assertIn(5, gh.store)
        bodies = [c["body"] for c in gh.notes.values()]
        self.assertTrue(any("edited" in b for b in bodies))
        self.assertFalse(any(b.startswith("**owner** · 2026-10-02\n\nsecond") for b in bodies))
        self.assertIn("a reader's own comment", bodies)  # left alone

    def test_refuses_a_misaligned_number(self):
        gh = FakeGitHub(skip_numbers=1)  # GitHub's #1 already taken by something else
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            gi.main(["--terms", str(self.terms), "--push"], forge=FakeForge(*self.tracker()), gh=gh)
        self.assertIn("numbered the tracker's #1 as #2", str(e.exception))

    def test_refuses_to_touch_an_issue_it_did_not_write(self):
        gh = FakeGitHub()
        gh.store[1] = {"title": "mine", "body": "someone's own issue", "state": "open", "labels": []}
        with self.assertRaises(SystemExit) as e, contextlib.redirect_stdout(io.StringIO()):
            gi.main(["--terms", str(self.terms), "--push"], forge=FakeForge(*self.tracker()), gh=gh)
        self.assertIn("isn't the tracker's #1", str(e.exception))

    def test_long_bodies_are_cut_with_the_marker_kept(self):
        body = gi.fit("x" * 70_000, gi.ISSUE_MARK.format(7))
        self.assertLessEqual(len(body), 65_536)
        self.assertTrue(body.endswith(gi.ISSUE_MARK.format(7)))

    def test_pull_request_comments_count(self):
        c = comment(20, 2, "on a PR")
        c["issue_url"], c["pull_request_url"] = "", "https://forge.example/api/v1/repos/o/r/pulls/2"
        self.assertEqual(gi.number_of(c), 2)


if __name__ == "__main__":
    unittest.main()
