"""The bot as a service (proof-of-fix#210, bot/service.py), with a fake chain and a fake forge: no Docker, no network.

Each step happens once over many passes; a crash after any write, then a new service on the same fakes, repeats
nothing; the only transactions are settle, timeOut, mergeExpired and sunset; the deadlines go out on their due day and
not the day before, a revert because someone else did it first counts as done, and a timeout that frees a sunset lands
in the same pass; ended bounties' issues get one comment and are closed; the hint is posted once, ever; the limits,
the backoff, the idle and away exits, the gas floor, --min-bounty and the pending transaction; the refusals at start;
and no secret in anything it prints. The local suite's scenario 10 runs it against a devnet."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from bot import logic
from bot.service import (ALLOWED, EXIT_AWAY, EXIT_FUSE, EXIT_IDLE, BotService, Refused, RpcChain, Settings, build,
                         main)
from oracle.crypto import checksum
from oracle.rpc import Reverted, Unavailable

RACE = checksum("0x" + "ab" * 20)
COIN = checksum("0x" + "c0" * 20)
OTHER = checksum("0x" + "c1" * 20)
BOT = checksum("0x" + "b0" * 20)
REPORTER = checksum("0x" + "11" * 20)
CFG = {"resultDays": 7, "mergeDays": 14, "idleDays": 28, "instalments": 4, "releaseEveryDays": 7}


class Crash(Exception):
    """The process dies right after a write took effect (before its answer is read)."""


class World:
    """What the chain and the forge hold, shared by every service started on them (a restart is a new service)."""

    def __init__(self):
        self.writes = 0
        self.crash_at = None  # crash right after this many writes (chain and forge alike)

    def wrote(self):
        self.writes += 1
        if self.crash_at is not None and self.writes == self.crash_at:
            raise Crash()


class FakeChain:
    def __init__(self, world: World):
        self.world, self.race, self.coin, self.address, self.from_block = world, RACE, COIN, BOT, 0
        self.today, self.blocks = 100, 10
        self.bounties: dict = {}
        self.subs: dict = {}
        self.issues: dict = {}
        self.settled_: set = set()
        self.held_: dict = {}
        self.logs: list = []  # (block, kind, fields, tx)
        self.sent: list = []
        self.oracles: set = set()
        self.gas = 10**18
        self.nonce = [0, 0]
        self.down = 0  # the next reads that fail
        self.coins = [COIN]
        self.fail_sends: dict = {}  # fn -> reason, every time
        self._tx = 0

    # ---------- seeding ----------

    def _log(self, kind, **fields):
        self.blocks += 1
        self._tx += 1
        tx = "0x" + f"{self._tx:064x}"
        self.logs.append((self.blocks, kind, fields, tx))
        return tx

    def register(self, n, reporter=REPORTER, repo="0x0"):
        self.issues[n] = {"reporter": reporter, "repo": repo, "state": "Posted", "bounty": 0}

    def open_bounty(self, b, issue, idle_since=None):
        self.bounties[b] = {"issue": issue, "state": "Open", "epoch": 0, "idleSince": self.today if idle_since is None
                            else idle_since, "next": 0, "mergeBy": 0, "winner": 0, "earned": 0, "list": []}
        if issue in self.issues:
            self.issues[issue]["bounty"] = b
        self._log("opened", bounty=b, issue=issue)

    def submit(self, s, b, day=None):
        self.subs[s] = {"bounty": b, "day": self.today if day is None else day, "outcome": "None"}
        self.bounties[b]["list"].append(s)
        self._log("committed", bounty=b, submission=s)

    def set_state(self, b, state):
        self.bounties[b]["state"] = state
        return self._log("changed", bounty=b, state=state)

    def decide(self, s, outcome):
        self.subs[s]["outcome"] = outcome
        self._decide(self.subs[s]["bounty"])

    def _decide(self, b):
        bt = self.bounties[b]
        while bt["state"] == "Open" and bt["next"] < len(bt["list"]):
            sub = self.subs[bt["list"][bt["next"]]]
            if sub["outcome"] == "None":
                return
            if sub["outcome"] == "Pass":
                bt["winner"], bt["mergeBy"] = bt["list"][bt["next"]], self.today + CFG["mergeDays"]
                bt["next"] += 1
                self.set_state(b, "Won")
                return
            bt["next"] += 1

    # ---------- the port ----------

    def _read(self):
        if self.down:
            self.down -= 1
            raise Unavailable("the chain at http://rpc is down")

    def chain_id(self):
        return 7193

    def head(self):
        self._read()
        return self.blocks

    def day(self):
        self._read()
        return self.today

    def config(self):
        return dict(CFG)

    def fee_coins(self):
        return list(self.coins)

    def scan(self, a, b):
        self._read()
        return [(k, {x: y for x, y in f.items()}) for blk, k, f, _ in self.logs if a <= blk <= b]

    def bounty(self, b):
        self._read()
        bt = self.bounties.get(b)
        if bt is None:
            return {"state": "None", "issue": 0, "epoch": 0, "idleSince": 0, "next": 0, "mergeBy": 0, "winner": 0}
        return {k: v for k, v in bt.items() if k not in ("list", "earned")}

    def submission(self, s):
        self._read()
        return dict(self.subs[s])

    def submissions_of(self, b):
        return list(self.bounties[b]["list"])

    def issue(self, n):
        self._read()
        if n not in self.issues:
            raise Reverted("reverted (0x4e487b71)")
        return dict(self.issues[n])

    def earned(self, b, epoch):
        return self.bounties[b]["earned"]

    def settled(self, b, coin):
        return (b, coin) in self.settled_

    def held(self, b, coin):
        return self.held_.get((b, coin), 0)

    def state_tx(self, b, state):
        found = None
        for blk, k, f, tx in self.logs:
            if k == "changed" and f["bounty"] == b and f["state"] == state:
                found = {"tx": tx, "block": blk}
        return found

    def is_oracle(self, who):
        return who.lower() in self.oracles

    def balance(self, who):
        return self.gas

    def nonces(self):
        self._read()
        return tuple(self.nonce)

    def send(self, fn, *args):
        assert fn in ALLOWED, fn
        self.sent.append((fn, args))
        if fn in self.fail_sends:
            raise Reverted(self.fail_sends[fn])
        getattr(self, "_" + fn)(*args)
        self.world.wrote()
        self._tx += 1
        return {"transactionHash": "0x" + f"{self._tx:064x}", "status": "0x1"}

    def _settle(self, b, coin):
        bt = self.bounties[b]
        if bt["state"] == "Merged" and bt["earned"] >= CFG["instalments"]:
            self.set_state(b, "Paid")
        if bt["state"] in ("Paid", "Unsolved", "Refunded"):
            self.settled_.add((b, coin))

    def _timeOut(self, s):
        sub = self.subs[s]
        if sub["outcome"] != "None":
            raise Reverted("Refused()")
        if self.today < sub["day"] + CFG["resultDays"]:
            raise Reverted("NotYet()")
        self.decide(s, "TimedOut")

    def _mergeExpired(self, b):
        bt = self.bounties[b]
        if bt["state"] != "Won" or self.today <= bt["mergeBy"]:
            raise Reverted("NotYet()")
        bt["idleSince"] = self.today
        self.set_state(b, "Open")
        self._decide(b)

    def _sunset(self, b):
        bt = self.bounties[b]
        if bt["state"] != "Open" or bt["next"] < len(bt["list"]) or self.today < bt["idleSince"] + CFG["idleDays"]:
            raise Reverted("NotYet()")
        self.set_state(b, "Unsolved")


class HTTPError(urllib.error.HTTPError):
    def __init__(self, code, headers=None, text=""):
        super().__init__("https://forge.example/api", code, text or f"HTTP {code}", headers or {}, None)


class FakeForge:
    def __init__(self, world: World):
        self.world = world
        self.items: dict = {}
        self.notes: dict = {}
        self.down = 0
        self.down_error = None
        self.refuse_comments = 0
        self.writes: list = []

    def add(self, n, body, labels=("bounty",), state="open", created="2026-11-01T00:00:00Z"):
        self.items[n] = {"number": n, "title": f"issue {n}", "body": body, "state": state, "labels": list(labels),
                         "user": "reporter", "created_at": created}
        return n

    def _read(self):
        if self.down:
            self.down -= 1
            raise self.down_error or urllib.error.URLError("the forge is down")

    def issues(self, state="open", label=None):
        self._read()
        return [dict(i) for i in self.items.values() if state in (i["state"], "all")
                and (label is None or label in i["labels"])]

    def issue(self, n):
        self._read()
        return dict(self.items[n])

    def comments(self, n):
        self._read()
        return [dict(c) for c in self.notes.get(n, [])]

    def comment(self, n, body):
        if self.refuse_comments:
            self.refuse_comments -= 1
            raise HTTPError(403)
        c = {"id": len(self.writes) + 1, "body": body, "user": "pof-bounty-bot"}
        self.notes.setdefault(n, []).append(c)
        self.writes.append(("comment", n))
        self.world.wrote()
        return c

    def close(self, n):
        self.items[n]["state"] = "closed"
        self.writes.append(("close", n))
        self.world.wrote()
        return dict(self.items[n])

    def markers(self, n, kind):
        reader = {"link": lambda c: logic.linked([c]), "paid": lambda c: logic.paid([c]),
                  "ended": lambda c: logic.ended([c]), "hint": lambda c: logic.hinted([c])}[kind]
        return sum(1 for c in self.notes.get(n, []) if reader(c))


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t, self.waits = t, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.waits.append(s)
        self.t += s


def claimed(n, reporter=REPORTER):
    return f"Something's wrong.\n\nRegistration: {n}\nReporter wallet: {reporter}\n"


class Rig:
    def __init__(self, **settings):
        self.world = World()
        self.chain, self.forge, self.clock = FakeChain(self.world), FakeForge(self.world), Clock()
        self.lines: list = []
        self.settings = {"repo": "o/r", "poll": 30, "hint_grace": 300, **settings}

    def service(self, **overrides):
        s = Settings(**{**self.settings, **overrides})
        return BotService(self.chain, self.forge, s, clock=self.clock, sleep=self.clock.sleep, out=self.lines.append,
                          chain_id=7193)

    def passes(self, n=20, svc=None):
        svc = svc or self.service()
        for _ in range(n):
            svc.run_pass()
            self.clock.t += 30
        return svc

    def sent(self, fn=None):
        return [x for x in self.chain.sent if fn is None or x[0] == fn]


def full_world(rig: Rig):
    """A linked bounty to pay, a claimed bounty to link, one ended unsolved, a timeout and a hint."""
    c, f = rig.chain, rig.forge
    c.register(1)
    c.open_bounty(1, 1)
    f.add(1, claimed(1))  # to link
    c.register(2)
    c.open_bounty(2, 2)
    f.add(2, claimed(2))
    f.notes[2] = [{"id": 90, "body": logic.bounty_comment(RACE, 2, 2)}]
    c.bounties[2].update(state="Merged", epoch=1, earned=4)  # due to settle, then paid and closed
    c.register(3)
    c.open_bounty(3, 3, idle_since=c.today - 30)  # due to sunset, then settled and closed
    f.add(3, claimed(3))
    f.notes[3] = [{"id": 91, "body": logic.bounty_comment(RACE, 3, 3)}]
    c.submit(1, 1, day=c.today - 7)  # due to time out
    f.add(4, "No lines here.", created="2020-01-01T00:00:00Z")  # the hint
    return c, f


class EachStepOnce(unittest.TestCase):
    def check_world(self, rig):
        c, f = rig.chain, rig.forge
        self.assertEqual(f.markers(1, "link"), 1)
        self.assertEqual((f.markers(2, "paid"), f.items[2]["state"]), (1, "closed"))
        self.assertEqual((f.markers(3, "ended"), f.items[3]["state"]), (1, "closed"))
        self.assertEqual(f.markers(4, "hint"), 1)
        self.assertEqual(c.bounties[2]["state"], "Paid")
        self.assertEqual(c.bounties[3]["state"], "Unsolved")
        self.assertEqual(c.subs[1]["outcome"], "TimedOut")
        self.assertIn((2, COIN), c.settled_)
        self.assertIn((3, COIN), c.settled_)
        self.assertEqual(f.items[1]["state"], "open")
        self.assertEqual(f.items[4]["state"], "open")

    def test_each_step_happens_once_over_20_passes(self):
        rig = Rig()
        full_world(rig)
        rig.passes(20)
        self.check_world(rig)
        self.assertEqual(sorted(fn for fn, _ in rig.sent()), ["settle", "settle", "sunset", "timeOut"])
        self.assertEqual(len(rig.forge.writes), 6)  # link, paid + close, ended + close, hint
        rig.passes(20)  # and nothing more after
        self.assertEqual(len(rig.forge.writes), 6)
        self.assertEqual(len(rig.sent()), 4)

    def test_a_crash_after_any_write_then_a_new_service_repeats_nothing(self):
        total = 10  # 4 transactions and 6 forge writes
        for k in range(1, total + 1):
            with self.subTest(crash_after=k):
                rig = Rig()
                full_world(rig)
                rig.world.crash_at = k
                svc = rig.service()
                with self.assertRaises(Crash):
                    for _ in range(20):
                        svc.run_pass()
                rig.world.crash_at = None
                rig.passes(20)  # a new service on the same chain and forge
                self.check_world(rig)
                self.assertEqual(len(rig.forge.writes), 6)
                self.assertEqual(sorted(fn for fn, _ in rig.sent()), ["settle", "settle", "sunset", "timeOut"])

    def test_the_only_transactions_are_the_four(self):
        rig = Rig()
        full_world(rig)
        rig.passes(20)
        self.assertLessEqual({fn for fn, _ in rig.sent()}, {"settle", "timeOut", "mergeExpired", "sunset"})
        self.assertEqual(set(ALLOWED), {"settle", "timeOut", "mergeExpired", "sunset"})
        chain = RpcChain.__new__(RpcChain)
        chain.wallet, chain.race = mock.Mock(), RACE
        for fn in ("register", "accept", "pledge", "attempt", "commit", "result", "merged", "claimRefund", "withdraw"):
            with self.assertRaises(ValueError):
                chain.send(fn, 1)
        chain.wallet.send.assert_not_called()
        chain.send("sunset", 4)
        chain.wallet.send.assert_called_once_with(RACE, "sunset(uint256)", 4)


class Settling(unittest.TestCase):
    def test_not_due_with_three_of_four_instalments(self):
        rig = Rig()
        rig.chain.open_bounty(1, 1)
        rig.chain.bounties[1].update(state="Merged", epoch=1, earned=3)
        rig.passes(5)
        self.assertEqual(rig.sent(), [])
        rig.chain.bounties[1]["earned"] = 4  # the release that earns the 4th
        rig.passes(1)
        self.assertEqual(rig.sent(), [("settle", (1, COIN))])
        self.assertEqual(rig.chain.bounties[1]["state"], "Paid")

    def test_another_fee_coin_only_when_its_pot_holds_something(self):
        rig = Rig()
        rig.chain.coins = [COIN, OTHER]
        rig.chain.open_bounty(1, 1)
        rig.chain.set_state(1, "Unsolved")
        rig.passes(3)
        self.assertEqual(rig.sent(), [("settle", (1, COIN))])
        rig.chain.open_bounty(2, 2)
        rig.chain.set_state(2, "Refunded")
        rig.chain.held_[(2, OTHER)] = 5
        rig.passes(3)
        self.assertEqual(rig.sent()[1:], [("settle", (2, COIN)), ("settle", (2, OTHER))])

    def test_settled_by_someone_else_still_closes_with_the_payout(self):
        rig = Rig()
        rig.chain.register(1)
        rig.chain.open_bounty(1, 1)
        rig.forge.add(12, claimed(1))
        rig.forge.notes[12] = [{"id": 1, "body": logic.bounty_comment(RACE, 1, 1)}]
        rig.chain.bounties[1]["state"] = "Merged"
        tx = rig.chain.set_state(1, "Paid")  # a person settled it with pofctl
        rig.chain.settled_.add((1, COIN))
        rig.passes(3)
        self.assertEqual(rig.sent(), [])
        self.assertEqual(logic.paid(rig.forge.notes[12])[2], tx)
        self.assertEqual(rig.forge.items[12]["state"], "closed")


class Deadlines(unittest.TestCase):
    def test_each_deadline_on_its_due_day_and_not_the_day_before(self):
        rig = Rig()
        c = rig.chain
        c.open_bounty(1, 1)
        c.submit(1, 1)  # times out on day + 7
        svc = rig.service()
        c.today += 6
        rig.passes(3, svc)
        self.assertEqual(rig.sent(), [])
        c.today += 1
        rig.passes(3, svc)
        self.assertEqual(rig.sent(), [("timeOut", (1,))])
        c.open_bounty(2, 2)
        c.submit(2, 2)
        c.decide(2, "Pass")  # Won: mergeBy = today + 14; expires the day after
        c.today += 14
        rig.passes(3, svc)
        self.assertEqual(rig.sent("mergeExpired"), [])
        c.today += 1
        rig.passes(3, svc)
        self.assertEqual(rig.sent("mergeExpired"), [("mergeExpired", (2,))])
        self.assertEqual(c.bounties[2]["state"], "Open")
        c.today += 27  # idle since the expiry; sunsets on idleSince + 28
        rig.passes(3, svc)
        self.assertEqual(rig.sent("sunset"), [("sunset", (1,))] if c.bounties[1]["idleSince"] + 28 <= c.today else [])
        sunset_before = [x for x in rig.sent("sunset") if x[1] == (2,)]
        self.assertEqual(sunset_before, [])
        c.today += 1
        rig.passes(3, svc)
        self.assertEqual([x for x in rig.sent("sunset") if x[1] == (2,)], [("sunset", (2,))])
        self.assertEqual(c.bounties[2]["state"], "Unsolved")

    def test_another_accounts_call_first_counts_as_done(self):
        rig = Rig()
        c = rig.chain
        c.open_bounty(1, 1)
        c.submit(1, 1, day=c.today - 7)
        svc = rig.service()
        real = c.submission

        def raced(s):  # someone times it out between the bot's read and its transaction
            view = real(s)
            c.subs[s]["outcome"] = "TimedOut"
            return view

        c.submission = raced
        rig.passes(1, svc)
        c.submission = real
        self.assertEqual(rig.sent(), [("timeOut", (1,))])
        self.assertTrue(any('"done": "already"' in line and "Refused()" in line for line in rig.lines))
        self.assertEqual(svc.failures, {})
        rig.passes(5, svc)
        self.assertEqual(len(rig.sent()), 1)

    def test_a_timeout_frees_a_sunset_in_the_same_pass(self):
        rig = Rig()
        c = rig.chain
        c.open_bounty(1, 1, idle_since=c.today - 40)
        c.submit(1, 1, day=c.today - 10)  # waiting for its result: holds the sunset
        rig.passes(1)
        self.assertEqual([fn for fn, _ in rig.sent()], ["timeOut", "sunset"])
        self.assertEqual(c.bounties[1]["state"], "Unsolved")


class Closing(unittest.TestCase):
    def test_unsolved_is_settled_commented_once_and_closed(self):
        rig = Rig()
        c, f = rig.chain, rig.forge
        c.register(5)
        c.open_bounty(5, 5)
        f.add(13, claimed(5))
        f.notes[13] = [{"id": 1, "body": logic.bounty_comment(RACE, 5, 5)}]
        tx = c.set_state(5, "Unsolved")
        rig.passes(10)
        self.assertEqual(rig.sent(), [("settle", (5, COIN))])
        said = logic.ended(f.notes[13])
        self.assertEqual(said[1:], (5, "Unsolved", tx))
        self.assertIn("reporter's stake has returned", f.notes[13][-1]["body"])
        self.assertEqual((f.markers(13, "ended"), f.items[13]["state"]), (1, "closed"))

    def test_not_ended_is_left_alone(self):
        rig = Rig()
        rig.chain.register(4)
        rig.chain.open_bounty(4, 4)
        rig.chain.set_state(4, "Won")
        rig.chain.bounties[4]["mergeBy"] = rig.chain.today + 5
        rig.forge.add(12, claimed(4))
        rig.forge.notes[12] = [{"id": 1, "body": logic.bounty_comment(RACE, 4, 4)}]
        rig.passes(5)
        self.assertEqual((rig.forge.writes, rig.forge.items[12]["state"]), ([], "open"))

    def test_a_reopened_unlabelled_issue_stays_open(self):
        rig = Rig()
        rig.chain.register(4)
        rig.chain.open_bounty(4, 4)
        rig.forge.add(12, claimed(4))
        rig.forge.notes[12] = [{"id": 1, "body": logic.bounty_comment(RACE, 4, 4)}]
        rig.chain.bounties[4]["state"] = "Merged"
        rig.chain.set_state(4, "Paid")
        rig.chain.settled_.add((4, COIN))
        rig.passes(3)
        self.assertEqual(rig.forge.items[12]["state"], "closed")
        rig.forge.items[12].update(state="open", labels=[])  # a person reopens it and removes the label
        rig.passes(5)
        self.assertEqual(rig.forge.items[12]["state"], "open")
        self.assertEqual(rig.forge.markers(12, "paid"), 1)


class Linking(unittest.TestCase):
    def test_only_the_first_valid_claimant_is_linked(self):
        rig = Rig()
        rig.chain.register(7)
        rig.forge.add(12, claimed(7))
        rig.forge.add(15, claimed(7))
        rig.passes(2)
        self.assertEqual(rig.forge.writes, [("comment", 15)])  # no bounty yet: no link, and no hint for #12
        rig.chain.open_bounty(4, 7)
        rig.passes(2)
        self.assertEqual(rig.forge.markers(12, "link"), 1)
        self.assertEqual(logic.linked(rig.forge.notes[12]), (RACE, 4, 7))
        self.assertEqual(rig.forge.markers(15, "link"), 0)
        self.assertEqual(rig.forge.markers(15, "hint"), 1)
        self.assertIn("first claim wins", rig.forge.notes[15][0]["body"])

    def test_a_wrong_wallet_or_repository_isnt_linked(self):
        rig = Rig()
        rig.chain.register(7)
        rig.chain.register(8, repo="0x" + "22" * 32)
        rig.chain.open_bounty(4, 7)
        rig.chain.open_bounty(5, 8)
        rig.forge.add(12, claimed(7, reporter=checksum("0x" + "99" * 20)))
        rig.forge.add(13, claimed(8))
        rig.clock.t += 400
        rig.passes(3)
        self.assertEqual((rig.forge.markers(12, "link"), rig.forge.markers(13, "link")), (0, 0))
        self.assertIn("isn't the wallet that registered", rig.forge.notes[12][0]["body"])
        self.assertIn("another repository", rig.forge.notes[13][0]["body"])
        self.assertEqual(rig.chain.sent, [])  # it registers and opens nothing


class Hints(unittest.TestCase):
    def test_once_after_the_grace_and_never_again(self):
        rig = Rig()
        now = rig.clock.t
        rig.forge.add(9, "No lines.", created="")  # the host doesn't say: the bot's first sight counts
        svc = rig.passes(5)  # 150 s: younger than the grace
        self.assertEqual(rig.forge.markers(9, "hint"), 0)
        rig.passes(10, svc)
        self.assertEqual(rig.forge.markers(9, "hint"), 1)
        self.assertGreaterEqual(rig.clock.t - now, 300)
        self.assertIn("Registration:", rig.forge.notes[9][0]["body"])
        self.assertIn("never registers", rig.forge.notes[9][0]["body"])
        rig.forge.items[9]["body"] = "Registration: 99\nReporter wallet: " + REPORTER  # still invalid: no such issue
        rig.passes(5, rig.service())  # a restart
        rig.forge.items[9]["labels"] = []
        rig.passes(2)
        rig.forge.items[9]["labels"] = ["bounty"]  # relabelled
        rig.passes(5, rig.service())
        self.assertEqual(rig.forge.markers(9, "hint"), 1)

    def test_a_valid_claim_in_time_gets_no_hint_and_its_link_follows(self):
        rig = Rig()
        rig.forge.add(9, "Opened first.", created="")
        svc = rig.passes(3)
        rig.chain.register(7)
        rig.forge.items[9]["body"] = claimed(7)
        rig.passes(20, svc)
        self.assertEqual(rig.forge.markers(9, "hint"), 0)
        rig.chain.open_bounty(4, 7)
        rig.passes(2)
        self.assertEqual(rig.forge.markers(9, "link"), 1)

    def test_none_on_a_linked_issue(self):
        rig = Rig()
        rig.forge.add(9, "Linked by hand.")
        rig.forge.notes[9] = [{"id": 1, "body": logic.bounty_comment(RACE, 4, 7)}]
        rig.passes(5)
        self.assertEqual(rig.forge.writes, [])

    def test_each_reason_has_its_own_text(self):
        texts = {r: logic.hint_comment(RACE, r) for r in logic.REASONS}
        self.assertEqual(len(set(texts.values())), len(logic.REASONS))
        for r, t in texts.items():
            self.assertTrue(logic.hinted([{"body": t}], RACE), r)
            self.assertIn(logic.REASONS[r], t)


class Limits(unittest.TestCase):
    def eight_due(self, rig):
        c = rig.chain
        for b in range(1, 5):  # 4 to settle
            c.open_bounty(b, b)
            c.set_state(b, "Unsolved")
        for b in range(5, 7):  # 2 time-outs
            c.open_bounty(b, b, idle_since=c.today)
            c.submit(b, b, day=c.today - 7)
        for b in range(7, 9):  # 2 sunsets
            c.open_bounty(b, b, idle_since=c.today - 28)

    def test_eight_due_take_two_passes_in_order(self):
        rig = Rig()
        self.eight_due(rig)
        svc = rig.service()
        svc.run_pass()
        self.assertEqual([fn for fn, _ in rig.sent()], ["settle"] * 4 + ["timeOut"])
        svc.run_pass()
        self.assertEqual([fn for fn, _ in rig.sent()][5:], ["timeOut", "sunset", "sunset"])

    def test_the_51st_write_exits_4(self):
        rig = Rig(max_pass=100)
        c = rig.chain
        for b in range(1, 52):
            c.open_bounty(b, b)
            c.set_state(b, "Unsolved")
        code = rig.service().run()
        self.assertEqual(code, EXIT_FUSE)
        self.assertEqual(len(rig.sent()), 50)

    def test_an_item_refused_three_times_is_left_for_the_next_run(self):
        rig = Rig()
        rig.chain.open_bounty(1, 1)
        rig.chain.set_state(1, "Unsolved")
        rig.chain.fail_sends["settle"] = "settle reverted in block 12"
        svc = rig.passes(10)
        self.assertEqual(len(rig.sent()), 3)
        self.assertIn(("settle", 1, COIN), svc.skipped)
        rig.chain.fail_sends.clear()
        rig.passes(1)  # the next run tries again
        self.assertEqual(len(rig.sent()), 4)

    def test_the_forge_down_backs_off_60_120_240_with_no_write(self):
        rig = Rig(until_idle=1000)
        rig.forge.down = 3
        rig.chain.open_bounty(1, 1)
        rig.chain.set_state(1, "Unsolved")
        rig.forge.add(9, "No lines.", created="2020-01-01T00:00:00Z")
        svc = rig.service()
        writes = []
        real = svc.run_pass

        def counted():
            writes.append(len(rig.forge.writes))
            return real()

        svc.run_pass = counted
        self.assertEqual(svc.run(), EXIT_IDLE)
        self.assertEqual(rig.clock.waits[:3], [60, 120, 240])
        self.assertEqual(writes[:4], [0, 0, 0, 0])
        self.assertEqual(rig.forge.markers(9, "hint"), 1)

    def test_retry_after_is_honoured_up_to_300(self):
        rig = Rig(until_idle=100)
        rig.forge.down, rig.forge.down_error = 2, HTTPError(429, {"Retry-After": "200"})
        rig.service().run()
        self.assertEqual(rig.clock.waits[:2], [200, 200])
        rig = Rig(until_idle=100)
        rig.forge.down, rig.forge.down_error = 1, HTTPError(503, {"Retry-After": "9999"})
        rig.service().run()
        self.assertEqual(rig.clock.waits[0], 300)

    def test_the_chain_away_for_30_minutes_exits_75(self):
        rig = Rig(until_idle=600)
        rig.chain.down = 10**6
        self.assertEqual(rig.service().run(), EXIT_AWAY)
        self.assertGreaterEqual(sum(rig.clock.waits), 1800 - 300)

    def test_idle_with_only_a_future_instalment(self):
        rig = Rig(until_idle=600)
        rig.chain.open_bounty(1, 1)
        rig.chain.bounties[1].update(state="Merged", epoch=1, earned=3)
        self.assertEqual(rig.service().run(), EXIT_IDLE)
        self.assertEqual(rig.sent(), [])
        self.assertLessEqual(sum(rig.clock.waits), 700)

    def test_a_claim_waiting_for_its_check_holds_idle_for_900_s(self):
        rig = Rig(until_idle=60)
        rig.chain.register(7)
        rig.forge.add(9, claimed(7))
        self.assertEqual(rig.service().run(), EXIT_IDLE)
        self.assertGreaterEqual(sum(rig.clock.waits), 900)

    def test_below_the_gas_floor_no_transaction_but_the_forge_steps_go_on(self):
        rig = Rig()
        rig.chain.gas = 10**15
        rig.chain.open_bounty(1, 1)
        rig.chain.set_state(1, "Unsolved")
        rig.forge.add(9, "No lines.", created="2020-01-01T00:00:00Z")
        rig.passes(5)
        self.assertEqual(rig.sent(), [])
        self.assertEqual(rig.forge.markers(9, "hint"), 1)
        self.assertEqual(sum("under 0.01 ETH" in line for line in rig.lines), 1)

    def test_min_bounty_leaves_older_bounties_alone(self):
        rig = Rig(min_bounty=3)
        c = rig.chain
        for b in (1, 2, 3):
            c.open_bounty(b, b)
            c.set_state(b, "Unsolved")
        c.open_bounty(4, 4, idle_since=c.today)
        c.submit(1, 2, day=c.today - 7)
        rig.passes(5)
        self.assertEqual(rig.sent(), [("settle", (3, COIN))])

    def test_a_pending_transaction_holds_new_ones_for_up_to_10_minutes(self):
        rig = Rig()
        rig.chain.open_bounty(1, 1)
        rig.chain.set_state(1, "Unsolved")
        rig.chain.nonce = [3, 4]
        svc = rig.service()
        rig.passes(15, svc)  # 450 s
        self.assertEqual(rig.sent(), [])
        rig.chain.nonce = [4, 4]  # it was mined
        rig.passes(1, svc)
        self.assertEqual(len(rig.sent()), 1)
        rig.chain.open_bounty(2, 2)
        rig.chain.set_state(2, "Unsolved")
        rig.chain.nonce = [4, 5]
        rig.passes(25, svc)  # 750 s: past the 10 minutes, it goes on
        self.assertEqual(len(rig.sent()), 2)


class Start(unittest.TestCase):
    def test_refusals_at_start(self):
        rig = Rig()
        svc = rig.service()
        rig.chain.chain_id = lambda: 1
        with self.assertRaisesRegex(Refused, "rule 1"):
            svc.check_start()
        rig.chain.chain_id = lambda: 31337
        rig.chain.oracles.add(BOT.lower())
        with self.assertRaisesRegex(Refused, "oracle key"):
            svc.check_start()
        rig.chain.oracles.clear()
        with self.assertRaisesRegex(Refused, "deployer"):
            svc.check_start(BOT)
        svc.check_start(REPORTER)

    def env(self, d: Path, **extra):
        (d / "key").write_text("0x" + "5a" * 32 + "\n", encoding="utf-8")
        (d / "auth").write_text("pof-bot:" + "6b" * 24, encoding="utf-8")
        (d / "token").write_text("t0ken" + "7c" * 18, encoding="utf-8")
        return {"POF_BOT_RPC": "http://127.0.0.1:9", "POF_BOT_KEY_FILE": str(d / "key"),
                "POF_BOT_RPC_AUTH_FILE": str(d / "auth"), "POF_BOT_FORGE_TOKEN_FILE": str(d / "token"),
                "POF_BOT_RACE": RACE, "POF_BOT_REPO": "o/r", "POF_BOT_FORGE_URL": "http://127.0.0.1:9", **extra}

    def refused(self, env, says):
        out = []
        self.assertEqual(main(env, out=out.append), 2)
        self.assertIn(says, out[-1])
        for secret in ("5a" * 32, "6b" * 24, "7c" * 18):
            self.assertNotIn(secret, "\n".join(out))

    def test_missing_files_and_a_credential_in_the_url(self):
        with tempfile.TemporaryDirectory() as d:
            env = self.env(Path(d))
            self.refused({**env, "POF_BOT_RPC": "https://pof-bot:" + "6b" * 24 + "@devnet.example"}, "credential")
            self.refused({k: v for k, v in env.items() if k != "POF_BOT_KEY_FILE"}, "POF_BOT_KEY_FILE")
            self.refused({**env, "POF_BOT_FORGE_TOKEN_FILE": d + "/nothing"}, "POF_BOT_FORGE_TOKEN_FILE")
            (Path(d) / "empty").write_text("\n", encoding="utf-8")
            self.refused({**env, "POF_BOT_RPC_AUTH_FILE": d + "/empty"}, "empty")
            self.refused({**env, "POF_BOT_REPO": ""}, "POF_BOT_REPO")

    def test_the_environment_holds_paths_not_values(self):
        with tempfile.TemporaryDirectory() as d:
            env = self.env(Path(d))
            for k, v in env.items():
                if k.endswith("_FILE"):
                    self.assertTrue(Path(v).is_file(), k)
            for secret in ("5a" * 32, "6b" * 24, "7c" * 18):
                self.assertNotIn(secret, json.dumps(env))


class NoSecretInTheOutput(unittest.TestCase):
    def test_a_forge_error_carrying_the_token_is_redacted(self):
        from bot.service import Redactor

        token, key, auth = "t0ken" + "7c" * 18, "0x" + "5a" * 32, "pof-bot:" + "6b" * 24
        red = Redactor()
        for v in (token, key, auth):
            red.add(v)
        rig = Rig(until_idle=60)
        rig.forge.down, rig.forge.down_error = 1, HTTPError(500, text=f"bad token {token} for key {key[2:]} {auth}")
        svc = BotService(rig.chain, rig.forge, Settings(repo="o/r", until_idle=60), clock=rig.clock,
                         sleep=rig.clock.sleep, out=rig.lines.append, redactor=red, chain_id=7193)
        rig.forge.down_error = urllib.error.URLError(f"refused {token} {auth.split(':')[1]}")
        svc.run()
        text = "\n".join(rig.lines)
        self.assertIn("***", text)
        for secret in (token, key[2:], "6b" * 24):
            self.assertNotIn(secret, text)

    def test_build_reads_each_secret_once_and_redacts_them(self):
        with tempfile.TemporaryDirectory() as d:
            env = Start().env(Path(d))
            out = io.StringIO()
            fake_rpc = mock.Mock()
            fake_rpc.view.side_effect = lambda to, sig, ret, *a: ([COIN] if sig.startswith("feeCoins") else
                                                                  [RACE])
            with mock.patch("bot.service.Rpc", return_value=fake_rpc), \
                    mock.patch("bot.service.Wallet") as wallet:
                wallet.return_value.address = BOT
                svc, deployer = build(env, out=lambda line: out.write(line + "\n"))
            svc.emit(error="the forge said t0ken" + "7c" * 18 + " and " + "5a" * 32 + " and pof-bot:" + "6b" * 24)
            text = out.getvalue()
            for secret in ("7c" * 18, "5a" * 32, "6b" * 24):
                self.assertNotIn(secret, text)
            self.assertEqual(svc.s.repo, "o/r")
            self.assertEqual(svc.s.poll, 30)


if __name__ == "__main__":
    unittest.main()
