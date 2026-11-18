"""The watcher's bot work (proof-of-fix#210, design D8: validator-kit/lambda/watcher.py's bot_work()), against a fake
chain: each kind starts a stopped host and is named; the due kinds again every DUE_POLL_MINUTES while they stay due,
and not once they aren't; PENDING_MAX_STARTS bounds a registration nobody claims; an overflowing state keeps the oldest
and says state-full; BOT_ENABLED=false leaves the seats' work; the selectors and topics are keccak256 of their
signatures. tests/test_validator_kit.py covers the hook's wiring and the kit's results without BOT_WORK."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "validator-kit" / "lambda"))

import watcher  # noqa: E402
from oracle.crypto import keccak256  # noqa: E402

RACE = "0x" + "ab" * 20
REPO = "0x" + "21" * 32
SEAT = "0x" + "5e" * 20
ENV = {"ENABLED": "true", "STATE_PARAM": "/pof-seats/watcher/state", "RACE_ADDRESS": RACE, "SEAT_ADDRESSES": SEAT,
       "INSTANCE_ID": "i-0123", "BOT_WORK": "true", "BOT_REPO_IDS": REPO, "PENDING_POLL_MINUTES": "30",
       "PENDING_MAX_STARTS": "2", "DUE_POLL_MINUTES": "30"}
STATE_INDEX = {s: i for i, s in enumerate(watcher.STATES)}


def _w(x) -> str:
    return format(int(x, 16) if isinstance(x, str) else int(x), "064x")


class Chain:
    """RaceV2 as bot_work() reads it: its logs and the issue, bounty, submission, submissionsOf, earned, day and
    getConfig views."""

    def __init__(self):
        self.head, self.logs, self.day = 100, [], 50
        self.issues: dict = {}  # n -> (repo, bounty, state)
        self.bounties: dict = {}  # b -> dict(state, idleSince, next, mergeBy, epoch, queue, earned)
        self.subs: dict = {}  # s -> (day, outcome)
        self.calls: list = []

    def log(self, block, topic, a, b=None, data=0):
        self.logs.append({"blockNumber": hex(block), "topics": [topic, "0x" + _w(a)] + (["0x" + _w(b)] if b is not None
                                                                                       else []),
                          "data": "0x" + _w(data)})

    def call(self, method, params):
        self.calls.append(method)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getLogs":
            q = params[0]
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            topics = q["topics"][0] if isinstance(q["topics"][0], list) else q["topics"]
            return [x for x in self.logs if lo <= int(x["blockNumber"], 16) <= hi and x["topics"][0] in topics]
        data = params[0]["data"]
        sel, args = data[:10], [int(data[10 + i:74 + i], 16) for i in range(0, len(data) - 10, 64)]
        if sel == watcher.ISSUE:
            repo, bounty, state = self.issues.get(args[0], ("0" * 64, 0, 0))
            return "0x" + _w(repo) + _w(1) + _w(2) + _w(3) + _w(4) + _w(bounty) + _w(state)
        if sel == watcher.BOUNTY:
            b = self.bounties.get(args[0], {"state": "None"})
            words = [0] * 14
            words[1], words[5], words[7] = STATE_INDEX[b["state"]], b.get("idleSince", 0), b.get("next", 0)
            words[9], words[10] = b.get("mergeBy", 0), b.get("epoch", 0)
            return "0x" + "".join(_w(x) for x in words)
        if sel == watcher.SUBMISSION:
            day, outcome = self.subs[args[0]]
            words = [0] * 12
            words[1], words[6] = day, outcome
            return "0x" + "".join(_w(x) for x in words)
        if sel == watcher.SUBMISSIONS_OF:
            n = self.bounties[args[0]].get("queue", 0)
            return "0x" + _w(32) + _w(n) + "".join(_w(i + 1) for i in range(n))
        if sel == watcher.EARNED:
            return "0x" + _w(self.bounties[args[0]].get("earned", 0))
        if sel == watcher.DAY:
            return "0x" + _w(self.day)
        if sel == watcher.CONFIG:
            words = [0] * 18
            words[12], words[13], words[14], words[17] = 28, 7, 14, 4
            return "0x" + "".join(_w(x) for x in words)
        raise AssertionError(sel)


def work(chain, state=None, start=0, end=None, now=10_000.0, env=None):
    return watcher.bot_work(env or ENV, chain, RACE, start, chain.head if end is None else end, state or {}, now)


class Kinds(unittest.TestCase):
    def test_a_registration_waiting_for_its_check(self):
        c = Chain()
        c.issues = {7: (REPO[2:], 0, 1), 8: ("00" * 32, 0, 1), 9: (REPO[2:], 4, 1)}
        for n in (7, 8, 9):
            c.log(10, watcher.REGISTERED_TOPIC, n, 0x11)
        due, state = work(c)
        self.assertEqual(due, {"registrations": [7]})  # 8: another repository; 9: already open
        due, state = work(c, state, start=101, end=100, now=10_000 + 29 * 60)
        self.assertEqual(due, {})
        due, state = work(c, state, start=101, end=100, now=10_000 + 30 * 60)
        self.assertEqual(due, {"registrations": [7]})
        due, state = work(c, state, start=101, end=100, now=10_000 + 60 * 60)
        self.assertEqual(due, {})  # PENDING_MAX_STARTS (2) asked: given up
        self.assertNotIn("regs", state)

    def test_opened_and_ended_once(self):
        c = Chain()
        c.log(10, watcher.OPENED_TOPIC, 4, 7)
        c.log(11, watcher.STATE_CHANGED_TOPIC, 3, data=STATE_INDEX["Unsolved"])
        c.bounties = {4: {"state": "Open", "idleSince": 50}}
        due, state = work(c)
        self.assertEqual(due, {"opened": [4], "ended": [3]})
        due, state = work(c, state, start=101, end=100, now=20_000)
        self.assertEqual(due, {})
        self.assertEqual(state["bounties"], [4])

    def test_each_due_kind_on_its_day_and_again_every_due_poll(self):
        c = Chain()
        c.bounties = {1: {"state": "Merged", "epoch": 1, "earned": 3}, 2: {"state": "Won", "mergeBy": 50},
                      3: {"state": "Open", "idleSince": 23, "queue": 1, "next": 1},
                      4: {"state": "Open", "idleSince": 23, "queue": 1, "next": 0}}
        c.subs = {9: (44, 0)}
        for b in (1, 2, 3, 4):
            c.log(10, watcher.STATE_CHANGED_TOPIC, b, data=STATE_INDEX[c.bounties[b]["state"]])
        c.log(10, watcher.COMMITTED_TOPIC, 4, 9)
        c.day = 50
        due, state = work(c)
        self.assertEqual(due, {})  # 3 of 4 earned; mergeBy is today; idle until 51; result due on 51
        c.day = 51
        c.bounties[1]["earned"] = 4
        due, state = work(c, state, start=101, end=100, now=20_000)
        self.assertEqual(due, {"settle": [1], "merge-expired": [2], "sunset": [3], "timeout": [9]})
        due, state = work(c, state, start=101, end=100, now=20_000 + 29 * 60)
        self.assertEqual(due, {})
        c.bounties[2]["state"] = "Open"  # someone expired it first: dropped, not started for
        c.bounties[2]["idleSince"] = 51
        due, state = work(c, state, start=101, end=100, now=20_000 + 30 * 60)
        self.assertEqual(due, {"settle": [1], "sunset": [3], "timeout": [9]})
        self.assertNotIn("merge-expired:2", state["due"])
        c.subs[9] = (44, 5)  # timed out
        c.bounties[1]["state"] = "Paid"
        due, state = work(c, state, start=101, end=100, now=20_000 + 60 * 60)
        self.assertEqual(due, {"sunset": [3]})
        self.assertNotIn(1, state["bounties"])
        self.assertNotIn("subs", state)

    def test_an_overflowing_state_keeps_the_oldest_and_says_so(self):
        c = Chain()
        for b in range(1, 900):
            c.log(10, watcher.OPENED_TOPIC, b, b)
            c.bounties[b] = {"state": "Open", "idleSince": 50}
        due, state = work(c)
        self.assertTrue(state["full"])
        self.assertEqual(state["bounties"][:3], [1, 2, 3])
        self.assertLessEqual(len(watcher.json.dumps(state, separators=(",", ":"))), watcher.BOT_STATE_LIMIT + 20)


class Wiring(unittest.TestCase):
    def test_the_selectors_and_topics(self):
        for value, sig in ((watcher.ISSUE, "issue(uint256)"), (watcher.CONFIG, "getConfig()"), (watcher.DAY, "day()"),
                           (watcher.EARNED, "earned(uint256,uint256)"),
                           (watcher.SUBMISSIONS_OF, "submissionsOf(uint256)")):
            self.assertEqual(value, "0x" + keccak256(sig.encode()).hex()[:8], sig)
        self.assertEqual(watcher.REGISTERED_TOPIC, "0x" + keccak256(b"Registered(uint256,address)").hex())
        self.assertEqual(watcher.OPENED_TOPIC, "0x" + keccak256(b"BountyOpened(uint256,uint256)").hex())

    def test_the_run_starts_a_stopped_host_and_names_the_work(self):
        from test_validator_kit import FakeEc2, FakeSsm

        c = Chain()
        c.issues = {7: (REPO[2:], 0, 1)}
        c.log(100, watcher.REGISTERED_TOPIC, 7, 0x11)
        ssm, ec2 = FakeSsm("99"), FakeEc2()
        result = watcher.run(ENV, c, ssm, ec2, now=lambda: 10_000.0)
        self.assertEqual((result["action"], result["registrations"]), ("started", [7]))

    def test_the_bots_switch_off_leaves_the_seats_registrations(self):
        from test_validator_kit import FakeEc2, FakeSsm

        c = Chain()
        c.bounties = {4: {"state": "Open", "idleSince": 50}}
        c.log(100, watcher.OPENED_TOPIC, 4, 7)
        result = watcher.run({**ENV, "BOT_ENABLED": "false"}, c, FakeSsm("99"), FakeEc2(), now=lambda: 10_000.0)
        self.assertEqual(result["action"], "idle")
        self.assertNotIn("opened", result)

    def test_state_full_is_in_the_result_line(self):
        from test_validator_kit import FakeEc2, FakeSsm

        c = Chain()
        for b in range(1, 900):
            c.log(100, watcher.OPENED_TOPIC, b, b)
            c.bounties[b] = {"state": "Open", "idleSince": 50}
        result = watcher.run(ENV, c, FakeSsm("99"), FakeEc2(), now=lambda: 10_000.0)
        self.assertTrue(result.get("state-full"))


if __name__ == "__main__":
    unittest.main()
