"""#253: the node's own model-spending caps (daily and monthly, across runs) and the on-chain pause (oracle/spend.py),
in the model client (oracle/models.py) and the v3 node (oracle/node_v3.py)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import models, spend  # noqa: E402
from oracle.models import Client, ModelError, OpenAI, Reply  # noqa: E402
from oracle.rpc import Reverted  # noqa: E402

DAY = 86400
T0 = 1_795_000_000.0  # 2026-11-17 (UTC), a Tuesday mid-month


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def answer(inp=1000, out=200):
    body = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": inp, "completion_tokens": out}}
    return Reply(200, {}, json.dumps(body).encode())


class Requests:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def __call__(self, method, url, headers, body, timeout):
        self.calls += 1
        r = self.replies.pop(0) if self.replies else answer()
        if isinstance(r, Exception):
            raise r
        return r


PRICES = spend.Prices(4.0, 0.2, 20.0)  # USD per million tokens: a token at $4/M costs 4 micro-USD


def caps(tmp, daily=0.5, monthly=5.0, clock=None, **kw):
    return spend.SpendCaps(daily, monthly, PRICES, Path(tmp) / "spend.json", clock or Clock(), **kw)


def client(request, caps_, max_tokens=1000):
    return Client(OpenAI("m", "k"), max_tokens=max_tokens, request=request, sleep=lambda s: None, spend=caps_,
                  retries=0)


class Caps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_prices(self):
        self.assertEqual(PRICES.cost(1_000_000, 0), 4_000_000)  # $4
        self.assertEqual(PRICES.cost(1000, 200), 4000 + 4000)  # $0.008
        self.assertEqual(PRICES.cost(1000, 0, cached_tokens=500), 500 * 4 + 500 * 0.2)

    def test_a_call_within_the_caps_is_made_and_its_real_cost_recorded(self):
        c = caps(self.tmp)
        req = Requests(answer(1000, 200))
        client(req, c).complete("system", "user")
        self.assertEqual(req.calls, 1)
        self.assertEqual(c.spent(), (8000, 8000))  # the provider's counts, not the worst case

    def test_the_daily_cap_stops_the_call_before_it_is_made(self):
        c = caps(self.tmp, daily=0.01)  # $0.01: the worst case of a 1,000-token answer is $0.02 at $20/M out
        req = Requests()
        with self.assertRaises(spend.SpendCapReached) as e:
            client(req, c).complete("system", "user")
        self.assertEqual((req.calls, e.exception.cap), (0, "day"))
        self.assertIsInstance(e.exception, models.BudgetExceeded)  # a ModelError: the node seals nothing
        self.assertIsInstance(e.exception, ModelError)
        self.assertIn("ORACLE_SPEND_DAILY_USD", str(e.exception))
        self.assertEqual(c.stopped_now(), "day")

    def test_the_monthly_cap_stops_it_across_days(self):
        clock = Clock()
        c = caps(self.tmp, daily=1.0, monthly=0.05, clock=clock)
        req = Requests(answer(1000, 1000), answer(1000, 1000))
        cl = client(req, c)
        cl.complete("s", "u")  # $0.024
        clock.t += DAY
        cl.complete("s", "u")  # $0.048 this month
        clock.t += DAY
        with self.assertRaises(spend.SpendCapReached) as e:
            cl.complete("s", "u")
        self.assertEqual((e.exception.cap, req.calls), ("month", 2))
        self.assertEqual(c.stopped_now(), "month")

    def test_a_call_with_no_reply_counts_its_worst_case(self):
        c = caps(self.tmp)
        with self.assertRaises(ModelError):
            client(Requests(OSError("reset")), c).complete("s" * 35, "u" * 35)
        self.assertEqual(c.spent()[0], PRICES.cost(20, 1000))

    def test_the_ledger_survives_the_on_demand_runs(self):
        clock = Clock()
        client(Requests(answer(1000, 200)), caps(self.tmp, clock=clock)).complete("s", "u")
        again = caps(self.tmp, clock=clock)  # the next boot's node
        self.assertEqual(again.spent(), (8000, 8000))
        clock.t += DAY
        self.assertEqual(caps(self.tmp, clock=clock).spent(), (0, 8000))  # a new UTC day, the same month

    def test_an_unreadable_ledger_refuses_to_spend(self):
        (Path(self.tmp) / "spend.json").write_text("not json")
        with self.assertRaisesRegex(models.ConfigError, "can't be read"):
            caps(self.tmp)

    def test_caps_must_be_positive(self):
        with self.assertRaises(models.ConfigError):
            caps(self.tmp, daily=0)


class Pause(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.clock = Clock()
        self.c = caps(self.tmp, daily=0.01, clock=self.clock)
        self.sent, self.cap = [], {"checks": 5, "next": 5, "from": 0, "room": True}

    def step(self, c=None):
        return (c or self.c).pause_step(lambda: dict(self.cap), self.sent.append, log=lambda m: None)

    def stop(self):
        with self.assertRaises(spend.SpendCapReached):
            client(Requests(), self.c).complete("s", "u")

    def test_nothing_while_no_cap_stopped_a_call(self):
        self.assertFalse(self.step())
        self.assertEqual(self.sent, [])

    def test_paused_on_chain_when_a_cap_stops_a_call_and_restored_the_next_day(self):
        self.stop()
        self.assertTrue(self.step())
        self.assertEqual(self.sent, [0])
        self.assertFalse(self.step())  # once
        self.assertEqual(caps(self.tmp, daily=0.01, clock=self.clock).data["paused"], {"restore": 5, "cap": "day"})
        self.clock.t += DAY
        self.assertTrue(self.step(caps(self.tmp, daily=0.01, clock=self.clock)))  # a later run, the next day
        self.assertEqual(self.sent, [0, 5])

    def test_the_monthly_cap_holds_the_pause_until_the_next_month(self):
        c = caps(self.tmp, daily=1.0, monthly=0.01, clock=self.clock)
        with self.assertRaises(spend.SpendCapReached):
            client(Requests(), c).complete("s", "u")
        self.cap["next"] = 3  # the operator's own setting comes back, not the default
        self.assertTrue(self.step(c))
        self.clock.t += DAY
        self.assertFalse(self.step(c))  # a new day isn't a new month
        self.clock.t += 20 * DAY  # into December
        self.assertTrue(self.step(c))
        self.assertEqual(self.sent, [0, 3])

    def test_an_operator_s_own_pause_is_left_alone(self):
        self.stop()
        self.cap["next"] = 0
        self.assertFalse(self.step())
        self.assertEqual(self.sent, [])

    def test_a_refused_change_is_tried_again(self):
        self.stop()

        def busy(n):
            raise Reverted("Busy()")

        with self.assertRaises(Reverted):
            self.c.pause_step(lambda: dict(self.cap), busy, log=lambda m: None)
        self.assertIsNone(self.c.data["paused"])  # not recorded: the next pass tries again
        self.assertTrue(self.step())
        self.assertEqual(self.sent, [0])

    def test_pause_off(self):
        c = caps(self.tmp, daily=0.01, clock=self.clock, pause=False)
        with self.assertRaises(spend.SpendCapReached):
            client(Requests(), c).complete("s", "u")
        self.assertFalse(self.step(c))

    def test_the_node_pauses_through_panels(self):
        from oracle.node_v3 import NodeV3

        self.stop()
        node = NodeV3.__new__(NodeV3)
        sends, logs = [], []
        node.address, node.spend, node._said, node.log = "0x" + "11" * 20, self.c, set(), logs.append
        node.chain = type("C", (), {"panels": "0x" + "22" * 20, "capacity": lambda s, key: dict(self.cap)})()
        node.wallet = type("W", (), {"send": lambda s, *a: sends.append(a)})()
        self.assertTrue(node._spend_pause())
        self.assertEqual(sends, [("0x" + "22" * 20, "setCapacity(address,uint256)", "0x" + "11" * 20, 0)])

        def busy(*a):
            raise Reverted("Busy()")

        self.clock.t += DAY
        node.wallet = type("W", (), {"send": lambda s, *a: busy()})()
        self.assertFalse(node._spend_pause())  # pending change: logged once, tried again
        self.assertTrue(any("refused the capacity change" in m for m in logs))


class FromEnv(unittest.TestCase):
    def test_defaults_fit_the_owner_s_model_budget(self):
        with tempfile.TemporaryDirectory() as d:
            c = spend.from_env({"ORACLE_ROUNDS": d})
            self.assertEqual((c.daily, c.monthly), (500_000, 5_000_000))
            self.assertEqual(c.path, Path(d) / "spend.json")
            self.assertTrue(c.pause_on)
        self.assertTrue(30 <= 7 * spend.DEFAULT_MONTHLY_USD <= 50)  # #253: $30-50 a month across 7 validators
        self.assertLessEqual(30 * spend.DEFAULT_DAILY_USD, 3 * spend.DEFAULT_MONTHLY_USD)

    def test_configurable_and_off(self):
        env = {"ORACLE_SPEND_DAILY_USD": "1", "ORACLE_SPEND_MONTHLY_USD": "3", "ORACLE_SPEND_LEDGER": "/x/l.json",
               "ORACLE_PRICE_PER_MTOK": "1,0.1,5", "ORACLE_SPEND_PAUSE": "off"}
        c = spend.from_env(env)
        self.assertEqual((c.daily, c.monthly, c.path, c.prices, c.pause_on),
                         (1_000_000, 3_000_000, Path("/x/l.json"), spend.Prices(1, 0.1, 5), False))
        self.assertIsNone(spend.from_env({"ORACLE_SPEND_MONTHLY_USD": "0"}))
        for bad in ({"ORACLE_PRICE_PER_MTOK": "1,2"}, {"ORACLE_SPEND_DAILY_USD": "lots"}):
            with self.assertRaises(models.ConfigError):
                spend.from_env(bad)

    def test_prices_follow_the_family_else_the_dearest(self):
        from pof import costs

        a = costs.JUDGE["anthropic"]
        self.assertEqual(spend.prices_from_env({"ORACLE_FAMILY": "anthropic/claude"}),
                         spend.Prices(a.input, a.cached, a.output))
        dearest = spend.prices_from_env({"ORACLE_FAMILY": "unknown/model"})
        self.assertEqual(dearest.output, max(m.output for m in costs.JUDGE.values()))
        self.assertEqual(dearest.input, max(m.input for m in costs.JUDGE.values()))


if __name__ == "__main__":
    unittest.main()
