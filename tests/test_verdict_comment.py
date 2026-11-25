"""The verdict on the Radicle issue (proof-of-fix#251, v3.1 polish VP18; oracle/verdict_comment.py).

Nodes judge on test_oracle_v3's fake chain; the Radicle node is tests/fake_rad.py (`rad` on PATH, the issues as COB
files under $RAD_HOME), holding the issue whose signed claim names the check's registration. Cases: a counted
registration check gets one comment with the reason; a fix check gets the outcome only, then the reason once its bounty
is paid; a hidden registration never gets the reason; a node that finds the marker doesn't comment; a restart doesn't
repeat a comment and still gives the reason later; a failing Radicle node is retried with backoff and never stops a
seat step; only a node with Radicle issues (ORACLE_FIX_SOURCE=radicle) has the step."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from oracle import crypto, v3  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle import verdict_comment as VC  # noqa: E402
from oracle.rounds import Store as Rounds  # noqa: E402
from test_oracle_v3 import CHAIN, RACE, SEAL_WINDOW, FakeChain, Net  # noqa: E402

RID = "rad:z2ZdzxFSFzBavdeNbUKwEnfVcAq5R"
ME = "did:key:z6Mkr4Av6WRPU25LajzvoTtRFjdp7kPQLxCgpJodG1RCtzNX"
REPORTER_SECRET = 0xC0FFEE
REPORTER = crypto.address(REPORTER_SECRET)
COUNTING_TX = "0x" + "c0" * 32


class CountingChain(FakeChain):
    """The fake chain with Panels' Counted event (the counting transaction)."""

    def counted_tx(self, s, pid, from_block=0):
        p = self.panels_[pid]
        return {"tx": COUNTING_TX, "block": 4242} if p["counted"] and p["id"] == s else None


class RadHome:
    """A stand-in Radicle node: $RAD_HOME and `rad` on PATH (tests/fake_rad.py)."""

    def __init__(self, tmp: Path) -> None:
        self.home = tmp / "radhome"
        (self.home / "cobs" / "xyz.radicle.issue").mkdir(parents=True)
        (self.home / "did").write_text(ME)
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "rad").write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_rad.py'} \"$@\"\n")
        (bin_dir / "rad").chmod(0o755)
        self.env = mock.patch.dict(os.environ, {"RAD_HOME": str(self.home),
                                                "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"})
        self.env.start()

    def issue(self, registration: int, extra_comments=()) -> str:
        """An issue whose description carries the reporter's signed claim of `registration`; its id."""
        iid = hashlib.sha1(f"issue {registration}".encode()).hexdigest()
        lines = RV.signed_claim_lines(lambda d: crypto.sign(REPORTER_SECRET, d), REPORTER, CHAIN, RACE, registration,
                                      v3.ZERO, iid)
        body = "The median is wrong for even lengths.\n\n" + "\n".join(lines)
        comments = {iid: {"author": ME[8:], "body": body, "edits": []}}
        timeline = [iid]
        for i, text in enumerate(extra_comments):
            cid = hashlib.sha1(f"{iid} {i}".encode()).hexdigest()
            comments[cid] = {"author": ME[8:], "body": text, "edits": []}
            timeline.append(cid)
        cob = {"title": "median", "state": {"status": "open"}, "labels": [],
               "thread": {"comments": comments, "timeline": timeline}}
        (self.home / "cobs" / "xyz.radicle.issue" / f"{iid}.json").write_text(json.dumps(cob))
        return iid

    def comments(self) -> list:
        f = self.home / "issue-comments.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines()] if f.exists() else []


class FlakyRadicle:
    """A Radicle whose first `fails` comments fail as an unreachable node's do."""

    def __init__(self, radicle, fails):
        self.radicle, self.fails, self.tries = radicle, fails, 0

    def comment(self, issue, body):
        self.tries += 1
        if self.tries <= self.fails:
            raise R.Unavailable("Radicle: exit 1: the node isn't running")
        return self.radicle.comment(issue, body)


class VerdictOnTheIssue(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.rad = RadHome(self.tmp)
        self.addCleanup(self.rad.env.stop)
        with mock.patch("test_oracle_v3.FakeChain", CountingChain):
            self.net = Net(self.tmp)
        self.c = self.net.chain
        self.c.issues[1].update(reporter=REPORTER)
        self.radicle = R.Radicle(RID)
        self.issue = self.rad.issue(1)
        for n in self.net.nodes:
            self.attach(n)

    def attach(self, node, radicle=None, store="node"):
        node.claims = RV.RadicleIssues(self.radicle)
        node.verdicts = VC.VerdictComments(radicle or self.radicle, node.claims, log=node.log,
                                           clock=lambda: self.c.time,
                                           store=node.rounds if store == "node" else store)
        return node.verdicts

    def judge(self, s, idx=(0, 1, 2)):
        pid = self.c.add_panel(s, v3.COUNTED, self.net.addresses(*idx))
        nodes = [self.net.nodes[i] for i in idx]
        self.net.judge_through(nodes)
        self.assertTrue(self.c.panel(pid)["counted"])
        self.c.warp(VC.CHECK_EVERY_S + 1)
        self.net.tick(nodes)
        return pid

    def registration_check(self, s=2):
        self.c.add_submission(s, bounty=0, issue=1)
        return s

    def test_a_registration_check_gets_one_comment_with_the_reason(self):
        s = self.registration_check()
        pid = self.judge(s)
        self.net.tick(times=3)
        (c,) = self.rad.comments()
        self.assertEqual((c["repo"], c["issue"]), (RID, self.issue))
        body = c["body"]
        self.assertIn(f"proof-of-fix verdict: registration check {s} passed, 3 of 3 judges for a pass (k = 3).", body)
        self.assertIn("State: Window: final at ", body)
        self.assertIn(f"Counted in transaction {COUNTING_TX} (block 4242).", body)
        self.assertIn(f"panel {pid}; told by {self.net.keys[0].address()}, its seat 0.", body)
        self.assertIn("Reason (seat 0's judge, which voted pass): an issue validly claims the registration", body)
        self.assertEqual(body.splitlines()[-1], f"pof-verdict: {CHAIN}/{RACE.lower()}/{s}")
        self.assertIn(f"check {s}: its verdict commented on Radicle issue {self.issue[:7]}", self.net.logs)

    def test_a_seat_finished_in_the_pass_it_was_judged_still_gets_its_comment(self):
        """#311's early reveal can seal, reveal and report a seat within one pass, and the node lets the seat go
        before the comment step ran (the Radicle integration set found no comment): the seat is kept at its finish."""
        s = self.registration_check()
        pid = self.c.add_panel(s, v3.COUNTED, self.net.addresses(0, 1, 2))
        nodes = [self.net.nodes[i] for i in (0, 1, 2)]
        for n in nodes:  # no comment step between the judging and the finish: all of it in one pass
            n.verdicts.step = lambda node, now=None: False
        self.net.judge_through(nodes)
        for n in nodes:
            del n.verdicts.step  # the class's step again
            for r in list(n.seats.values()):
                n._finish(r, "done in one pass")
            self.assertEqual(n.seats, {})
        self.c.warp(VC.CHECK_EVERY_S + 1)
        self.net.tick(times=3)
        (c,) = self.rad.comments()
        self.assertEqual(c["body"].splitlines()[-1], f"pof-verdict: {CHAIN}/{RACE.lower()}/{s}")

    def test_a_fix_check_gets_the_outcome_then_the_reason_once_the_bounty_is_paid(self):
        self.judge(1)
        (first,) = self.rad.comments()
        self.assertIn("proof-of-fix verdict: check 1 (a fix on bounty 1) ", first["body"])
        self.assertNotIn("Reason (", first["body"])
        self.assertIn("The reason follows once the bounty is paid or closed", first["body"])
        self.c.warp(VC.SETTLE_EVERY_S + 1)
        self.net.tick()
        self.assertEqual(len(self.rad.comments()), 1)  # the bounty is open: the evidence stays sealed
        self.c.bounties[1] = {"state": v3.PAID}
        self.c.warp(VC.SETTLE_EVERY_S + 1)
        self.net.tick(times=2)
        first_, second = self.rad.comments()
        self.assertEqual(first_, first)
        self.assertIn("bounty 1 is paid, so check 1's evidence is no longer sealed", second["body"])
        self.assertIn("Reason (seat 0's judge, which voted ", second["body"])
        self.assertIn("fake judge", second["body"])
        self.assertEqual(second["body"].splitlines()[-1], f"pof-verdict-reason: {CHAIN}/{RACE.lower()}/1")
        self.c.warp(VC.SETTLE_EVERY_S + 1)
        self.net.tick()
        self.assertEqual(len(self.rad.comments()), 2)

    def test_a_hidden_registration_never_gets_the_reason(self):
        self.c.issues[1]["hidden"] = True
        self.judge(self.registration_check())
        (c,) = self.rad.comments()
        self.assertNotIn("Reason", c["body"])
        self.assertNotIn("reason follows", c["body"])
        self.judge(1, idx=(1, 2, 3))  # a fix on the hidden registration's bounty: no reason, even once paid
        self.c.bounties[1] = {"state": v3.PAID}
        self.c.warp(VC.SETTLE_EVERY_S + 1)
        self.net.tick(times=2)
        self.assertEqual(len(self.rad.comments()), 2)
        self.assertFalse(any("Reason" in x["body"] for x in self.rad.comments()))

    def test_only_the_first_revealed_seats_node_comments_and_a_marker_stops_it(self):
        s = self.registration_check()
        marker = VC.marker_line(CHAIN, RACE, s)
        iid = self.rad.issue(1, extra_comments=[f"Verdict, by another node\n\n{marker}"])
        self.assertEqual(iid, self.issue)
        self.judge(s)
        self.net.tick(times=2)
        self.assertEqual(self.rad.comments(), [])  # the first seat's node found the marker; the others aren't first
        self.assertIn(f"check {s}: its verdict is already on Radicle issue {iid[:7]}; not again", self.net.logs)

    def test_a_restart_doesnt_repeat_it_and_still_gives_the_reason(self):
        self.judge(1)
        self.assertEqual(len(self.rad.comments()), 1)
        node = self.net.nodes[0]
        saved = node.rounds.get(VC.STATE)["watch"]
        self.assertEqual([e["stage"] for e in saved.values()], ["reason"])
        # a restarted node: the same store, a fresh step; and one that lost its store but still holds the seat
        self.attach(node)
        self.net.tick(times=2)
        lost = self.net.node(0)
        lost.seats = {}
        pid = int(next(iter(saved)))
        lost._take(pid)
        lost.seats[pid].judged = True
        self.attach(lost, store=None)
        lost.tick(0)
        self.assertEqual(len(self.rad.comments()), 1)  # nothing repeated: the marker is on the issue
        self.c.bounties[1] = {"state": v3.UNSOLVED}
        self.c.warp(VC.SETTLE_EVERY_S + 1)
        node.tick(0)
        self.assertEqual(len(self.rad.comments()), 2)
        self.assertIn("bounty 1 is unsolved", self.rad.comments()[1]["body"])

    def test_a_failing_radicle_node_is_retried_with_backoff_and_never_stops_a_seat(self):
        s = self.registration_check()
        flaky = FlakyRadicle(self.radicle, fails=2)
        self.attach(self.net.nodes[0], radicle=flaky)
        self.judge(s)  # counted in the pass after the seals (#311's early reveal): two tries since, 30 s apart
        self.assertEqual((flaky.tries, self.rad.comments()), (2, []))
        fails = [x for x in self.net.logs if "the verdict comment on check 2 failed (Radicle: exit 1: the node isn't "
                                             "running); trying again in" in x]
        self.assertEqual([x.rsplit(" ", 1)[-1] for x in fails], ["30s", "60s"])
        self.net.tick()
        self.c.warp(59)
        self.net.tick()
        self.assertEqual(flaky.tries, 2)  # backing off
        self.c.warp(2)
        self.net.tick()
        self.assertEqual((flaky.tries, len(self.rad.comments())), (3, 1))
        # meanwhile the seats went on: every usage report is on-chain
        pid = self.c.verdicts[s]["pid"]
        self.assertTrue(all((pid, i) in self.c.usage for i in range(3)))

    def test_the_reason_of_a_judges_answer(self):
        self.assertEqual(VC.reason_of('{"solves": true, "reason": "  the fix\\n handles it "}'), "the fix handles it")
        self.assertEqual(VC.reason_of("not json"), "")
        self.assertEqual(len(VC.reason_of(json.dumps({"reason": "x" * 1000}))), VC.REASON_CHARS)


class OnlyWithRadicleIssues(unittest.TestCase):
    def test_attach_gives_the_step_only_to_a_radicle_fix_source(self):
        class Chain(FakeChain):
            def repo(self):
                return R.repo_id(RID)

        with tempfile.TemporaryDirectory() as tmp:
            net = Net(Path(tmp))
            node = net.nodes[0]
            RV.attach(node, {"ORACLE_FIX_SOURCE": "host"}, Chain(), node.address)
            self.assertIsNone(node.verdicts)
            RV.attach(node, {"ORACLE_FIX_SOURCE": "radicle", "ORACLE_RADICLE_RID": RID}, Chain(), node.address)
            self.assertIsInstance(node.verdicts, VC.VerdictComments)
            self.assertIs(node.verdicts.issues, node.claims)
            self.assertIs(node.verdicts.store, node.rounds)
            self.assertIsInstance(node.rounds, Rounds)


if __name__ == "__main__":
    unittest.main()
