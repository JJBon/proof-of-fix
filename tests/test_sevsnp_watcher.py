"""The SEV-SNP validator's v3 watcher (validator-kit/sevsnp/lambda/watcher.py; #251 task 4.9, #253): it starts the
stopped instance only for this key's seats on v3's Panels that need the node, with v2's guardrails (the kill switch,
the day's fuse, retries per seat) plus the spend pause and the budget. No network and no AWS: the chain (Panels'
Seated event and views), SSM, EC2 and Budgets are fakes. Also the Terraform's static checks."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import unittest
import unittest.mock
import urllib.error
from pathlib import Path

from oracle import crypto

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "validator-kit" / "sevsnp"
V3 = ROOT / "contracts" / "src" / "v3"


def _load():
    spec = importlib.util.spec_from_file_location("pof_sevsnp_watcher", KIT / "lambda" / "watcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load()

RACE = "0x" + "ab" * 20
PANELS = "0x" + "cd" * 20
KEY = "0x" + "11" * 20
OTHER = "0x" + "22" * 20
T0 = 1_795_000_000  # the chain's time and the Lambda's clock, in seconds
COUNTED, SHADOW, AUDIT, CHALLENGE = 0, 1, 2, 3


def _w(v) -> str:
    if isinstance(v, bool):
        v = int(v)
    return (v[2:] if isinstance(v, str) else format(v, "x")).rjust(64, "0")


class FakeChain:
    """Panels: `seats_given` [(pid, slot, key, block)] as Seated logs; `panels` {pid: Panel fields}; `seats`
    {(pid, slot): Seat fields}; `caps` {key: (checks, next)}. RaceV3.contracts() names Panels."""

    def __init__(self, head=1000, now=T0):
        self.head, self.now, self.calls, self.down = head, now, [], False
        self.seats_given, self.panels, self.seats, self.caps = [], {}, {}, {}

    def draw(self, pid, slot=0, kind=COUNTED, k=3, block=990, seal_in=7200, reveal=3600, key=KEY):
        """`key` seated on panel `pid` at `block`, its windows from now (production's by default)."""
        self.seats_given.append((pid, slot, key, block))
        p = self.panels.setdefault(pid, {"id": pid + 100, "k": k, "seats": k, "nSealed": 0, "counted": False,
                                         "kind": kind, "closed": False})
        p["sealBy"], p["revealBy"] = self.now + seal_in, self.now + seal_in + reveal
        self.seats[(pid, slot)] = {"key": key, "hasSeal": False, "revealed": False, "receipted": False}

    def call(self, method, params):
        self.calls.append((method, params))
        if self.down:
            raise RuntimeError(f"{method}: the chain didn't answer (URLError)")
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getBlockByNumber":
            assert params == ["latest", False]
            return {"timestamp": hex(self.now)}
        if method == "eth_getLogs":
            q = params[0]
            assert q["address"] == PANELS and q["topics"][0] == W.SEATED_TOPIC and q["topics"][1] is None
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            who = "0x" + q["topics"][2][-40:]
            return [{"topics": [W.SEATED_TOPIC, hex(pid), "0x" + _w(key)], "data": "0x" + _w(slot) + _w(0),
                     "blockNumber": hex(b)} for pid, slot, key, b in self.seats_given if lo <= b <= hi and key == who]
        if method == "eth_call":
            to, data = params[0]["to"], params[0]["data"]
            sel, args = data[:10], [data[10 + i:74 + i] for i in range(0, len(data) - 10, 64)]
            if sel == W.CONTRACTS:
                assert to == RACE
                return "0x" + _w(PANELS) + "".join(_w(i + 1) for i in range(6))
            assert to == PANELS
            if sel == W.PANEL:
                p = self.panels.get(int(args[0], 16))
                if p is None:
                    return "0x" + _w(0) * 20
                words = [p["id"], 7, p["sealBy"], p["revealBy"], 0, p["k"], p["seats"], p["nSealed"], 0, 0, 1,
                         p["counted"], p["kind"], p["closed"], False, 0, 0, 0, 0, 0]
                return "0x" + "".join(_w(x) for x in words)
            if sel == W.SEAT:
                s = self.seats.get((int(args[0], 16), int(args[1], 16)))
                if s is None:
                    return "0x" + _w(0) * 9
                words = [s["key"], 1, s["hasSeal"], s["revealed"], s["receipted"], False, 0, 0, 0]
                return "0x" + "".join(_w(x) for x in words)
            if sel == W.CAPACITY:
                checks, nxt = self.caps.get("0x" + args[0][-40:], (5, 5))
                return "0x" + _w(checks) + _w(nxt) + _w(0) + _w(checks > 0)
        raise AssertionError((method, params))


class ParameterNotFound(Exception):
    pass


class FakeSsm:
    class exceptions:
        ParameterNotFound = ParameterNotFound

    def __init__(self, value=None):
        self.value, self.puts = value, 0

    def get_parameter(self, Name):
        if self.value is None:
            raise ParameterNotFound(Name)
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, Name, Value, Type, Overwrite):
        self.value, self.puts = Value, self.puts + 1

    def state(self) -> dict:
        return json.loads(self.value)


class FakeEc2:
    def __init__(self, state="stopped"):
        self.state, self.started = state, 0

    def describe_instances(self, InstanceIds):
        assert InstanceIds == [ENV["INSTANCE_ID"]]
        return {"Reservations": [{"Instances": [{"State": {"Name": self.state}}]}]}

    def start_instances(self, InstanceIds):
        assert InstanceIds == [ENV["INSTANCE_ID"]]
        self.started += 1
        self.state = "pending"


class FakeBudgets:
    def __init__(self, actual="3.10", limit="15.0"):
        self.actual, self.limit, self.calls = actual, limit, 0

    def describe_budget(self, AccountId, BudgetName):
        self.calls += 1
        assert (AccountId, BudgetName) == ("123456789012", "pof-snp-monthly")
        return {"Budget": {"BudgetLimit": {"Amount": self.limit, "Unit": "USD"},
                           "CalculatedSpend": {"ActualSpend": {"Amount": self.actual, "Unit": "USD"}}}}


ENV = {"ENABLED": "true", "STATE_PARAM": "/pof-snp/watcher/state", "RACE_ADDRESS": RACE, "VALIDATOR_ADDRESS": KEY,
       "INSTANCE_ID": "i-0123456789abcdef0", "UNPAUSE_CHECK": "off"}


def run(chain, ssm, ec2, env=None, at=None, budgets=None):
    return W.run(dict(ENV, **(env or {})), chain, ssm, ec2, budgets=budgets,
                 now=lambda: at if at is not None else chain.now)


class TheAbi(unittest.TestCase):
    def test_the_event_and_selectors_are_panels(self):
        self.assertEqual(W.SEATED_TOPIC,
                         "0x" + crypto.keccak256(b"Seated(uint256,uint256,address,uint256)").hex())
        for sel, sig in ((W.CONTRACTS, "contracts()"), (W.PANEL, "panel(uint256)"),
                         (W.SEAT, "seat(uint256,uint256)"), (W.CAPACITY, "capacity(address)")):
            self.assertEqual(sel, "0x" + crypto.keccak256(sig.encode()).hex()[:8], sig)
        panels = (V3 / "Panels.sol").read_text()
        self.assertIn("event Seated(uint256 indexed pid, uint256 slot, address indexed key, uint256 sealBy);", panels)
        for view in ("function panel(uint256 pid) external view returns (Panel memory)",
                     "function seat(uint256 pid, uint256 slot) external view returns (Seat memory)",
                     "function capacity(address key) external view returns (uint256 checks, uint256 next, uint256 "
                     "from, bool room)"):
            self.assertIn(view, panels)
        race = (V3 / "RaceV3.sol").read_text()
        self.assertIn("returns (Panels, IFeesV3, PoolV3, IValidators, Heads, address coin_, uint256 start_)", race,
                      "RaceV3.contracts() names Panels first")

    def test_the_words_it_reads_are_where_the_structs_put_them(self):
        """Panel's and Seat's fields in PanelsBase.sol, in order: the watcher's word indices follow them."""
        base = (V3 / "PanelsBase.sol").read_text()

        def fields(struct):
            body = re.search(r"struct %s \{(.*?)\n\}" % struct, base, re.S).group(1)
            return [m.group(1) for m in re.finditer(r"^\s+[\w.]+ (\w+);", body, re.M)]

        panel = fields("Panel")
        self.assertEqual([panel.index(f) for f in ("id", "sealBy", "revealBy", "k", "seats", "nSealed", "counted",
                                                   "kind", "closed", "snap")], [0, 2, 3, 5, 6, 7, 11, 12, 13, 16])
        self.assertEqual(len(panel), 17)  # snap, a 4-field static struct, last: 20 words in all
        snap = re.search(r"struct Snap \{(.*?)\}", (V3 / "PanelsDraw.sol").read_text(), re.S).group(1)
        self.assertEqual(len(re.findall(r";", snap)), 4)
        seat = fields("Seat")
        self.assertEqual([seat.index(f) for f in ("key", "hasSeal", "revealed", "receipted")], [0, 2, 3, 4])
        kinds = re.search(r"enum Kind \{(.*?)\}", base, re.S).group(1)
        self.assertEqual([k.strip() for k in kinds.split(",")], ["Counted", "Shadow", "Audit", "Challenge"])


class TheWatcher(unittest.TestCase):
    def test_no_seat_keeps_the_instance_stopped(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1, key=OTHER)  # another validator's seat
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], result["to"]), ("idle", 1000))
        self.assertEqual(ec2.started, 0)
        self.assertEqual(ssm.state(), {"last": 1000})
        self.assertNotIn("eth_getBlockByNumber", [m for m, _ in chain.calls])  # no seat: no view read

    def test_every_kind_of_seat_starts_the_stopped_instance(self):
        for kind, name in ((COUNTED, "counted"), (SHADOW, "shadow"), (AUDIT, "audit"), (CHALLENGE, "challenge")):
            with self.subTest(name):
                chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
                chain.draw(4, slot=1, kind=kind, k=1 if kind == AUDIT else 3)
                result = run(chain, ssm, ec2)
                self.assertEqual(result["action"], "started")
                self.assertEqual((result["seal"], result["kinds"]), ([4], {"4": name}))
                self.assertEqual(result["seal_left_s"], 7200)
                self.assertNotIn("late", result)
                self.assertEqual(ec2.started, 1)
                self.assertEqual(ssm.state()["seats"], {"4": {"slot": 1, "seal": [T0, 1]}})

    def test_a_replacement_seat_is_work_with_its_fresh_window(self):
        """A missed deadline's `advance` seats this key in an emptied slot of a running panel, with a fresh window
        for every seat (resetTimeline): the watcher reads sealBy from the panel, not from the event."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(9, slot=0, key=OTHER, seal_in=-10)  # someone else's seat, its seal window over
        self.assertEqual(run(chain, ssm, ec2)["action"], "idle")
        chain.head = 1100
        chain.draw(9, slot=0, block=1050)  # this key takes the slot; the panel's windows restart from now
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], result["seal"], result["seal_left_s"]), ("started", [9], 7200))

    def test_a_running_node_is_left_alone_and_spends_no_start(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2("running")
        chain.draw(2)
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], ec2.started), ("running", 0))
        self.assertEqual(ssm.state()["seats"]["2"]["seal"], [T0, 0])

    def test_a_seat_still_due_restarts_the_node_every_retry_and_then_gives_up(self):
        """The node stopped without sealing (a crash, its outage limit): started again every RETRY_MINUTES while the
        seal window lasts, at most SEAT_MAX_STARTS times."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(3, seal_in=7200)
        self.assertEqual(run(chain, ssm, ec2)["action"], "started")
        ec2.state = "stopped"
        self.assertEqual(run(chain, ssm, ec2, at=T0 + 300)["action"], "idle")  # 5 minutes: not yet
        self.assertEqual(run(chain, ssm, ec2, at=T0 + 600)["action"], "started")
        ec2.state = "stopped"
        self.assertEqual(run(chain, ssm, ec2, at=T0 + 1200)["action"], "started")
        ec2.state = "stopped"
        result = run(chain, ssm, ec2, at=T0 + 1800)
        self.assertEqual((result["action"], result["gave_up"], ec2.started), ("idle", [3], 3))

    def test_a_full_panel_starts_the_node_for_its_reveal_long_before_sealby(self):
        """#311: a judging panel's reveal opens once every seat has sealed, so a full panel's sealed seat is due at
        once, with its seal window still 1000 s from closing."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(5, seal_in=1000)
        chain.seats[(5, 0)]["hasSeal"] = True
        chain.panels[5]["nSealed"] = 3
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], result["reveal"]), ("started", [5]))

    def test_a_shadow_starts_the_node_near_its_own_seal_deadline(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(5, kind=SHADOW, seal_in=1000)
        chain.seats[(5, 0)]["hasSeal"] = True
        result = run(chain, ssm, ec2)  # a shadow's reveal opens after its `sealBy`: in 1000 s, more than the lead
        self.assertEqual((result["action"], ec2.started), ("idle", 0))
        self.assertIn("5", ssm.state()["seats"])  # still listed, waiting
        chain.now += 850  # 150 s before it opens
        result = run(chain, ssm, ec2, at=T0 + 850)
        self.assertEqual((result["action"], result["reveal"]), ("started", [5]))

    def test_a_reveal_waits_while_the_panel_isnt_fully_sealed(self):
        """A judging panel's reveal opens only once every seat sealed (a refill then restarts the windows); a shadow's
        opens on its own, after its `sealBy`."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(6, seal_in=-5)
        chain.draw(7, kind=SHADOW, seal_in=-5)
        for pid in (6, 7):
            chain.seats[(pid, 0)]["hasSeal"] = True
            chain.panels[pid]["nSealed"] = 2  # one of 3 seats never sealed
        result = run(chain, ssm, ec2)
        self.assertEqual((result["reveal"], result["kinds"]), ([7], {"7": "shadow"}))
        self.assertIn("6", ssm.state()["seats"])

    def test_seats_that_need_nothing_more_are_dropped(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        for pid in (1, 2, 3, 4, 5):
            chain.draw(pid)
        chain.seats[(1, 0)].update(hasSeal=True, revealed=True, receipted=True)  # done
        chain.panels[2]["counted"] = True
        chain.panels[3]["closed"] = True  # released
        chain.seats[(4, 0)]["key"] = OTHER  # vacated and refilled with another key
        chain.panels[5]["sealBy"] = T0 - 1  # its seal window passed unsealed
        result = run(chain, ssm, ec2)
        self.assertEqual(result["dropped"], {"1": "done", "2": "closed", "3": "closed", "4": "vacated", "5": "missed"})
        self.assertEqual((result["action"], ec2.started), ("idle", 0))
        self.assertNotIn("seats", ssm.state())

    def test_the_day_s_fuse(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1)
        chain.draw(2, block=995)
        env = {"MAX_STARTS_PER_DAY": "1", "RETRY_MINUTES": "0"}
        self.assertEqual(run(chain, ssm, ec2, env)["action"], "started")
        ec2.state = "stopped"
        result = run(chain, ssm, ec2, env, at=T0 + 60)
        self.assertEqual((result["action"], result["fuse"]["max"], ec2.started), ("fuse", 1, 1))
        result = run(chain, ssm, ec2, env, at=T0 + 86400)  # the next UTC day
        self.assertEqual((result["action"], ec2.started), ("started", 2))

    def test_the_kill_switch(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1)
        self.assertEqual(run(chain, ssm, ec2, {"ENABLED": "false"}), {"action": "disabled"})
        self.assertEqual((chain.calls, ec2.started, ssm.value), ([], 0, "950"))

    def test_the_spend_pause_holds_seal_work_but_not_a_reveal(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.caps[KEY] = (0, 0)
        chain.draw(1)
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], result["paused"], ec2.started), ("paused", [1], 0))
        self.assertEqual(ssm.state()["seats"]["1"], {"slot": 0})  # no start spent: it starts once the pause ends
        chain.head = 1010
        chain.draw(2, seal_in=-10, block=1005)
        chain.seats[(2, 0)]["hasSeal"] = True
        chain.panels[2]["nSealed"] = 3
        result = run(chain, ssm, ec2, at=T0 + 60)  # a sealed vote to open: no model call, and a miss is slashed
        self.assertEqual((result["action"], result["reveal"], result["paused"], ec2.started), ("started", [2], [1], 1))
        chain.caps[KEY] = (5, 5)  # the node set its capacity back
        ec2.state = "stopped"
        result = run(chain, ssm, ec2, at=T0 + 120)
        self.assertEqual((result["action"], result["seal"], ec2.started), ("started", [1], 2))

    def test_the_daily_unpause_check(self):
        """While the capacity reads 0 with nothing pending, the instance starts once a UTC day so the node can set its
        capacity back at a new period; not while it isn't paused, not twice a day, and never with "off"."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        daily = {"UNPAUSE_CHECK": "daily"}
        self.assertEqual(run(chain, ssm, ec2, daily)["action"], "idle")  # not paused: checked, nothing to do
        self.assertEqual(ssm.state()["unpause"], "2026-11-18")
        chain.caps[KEY] = (0, 0)
        self.assertEqual(run(chain, ssm, ec2, daily, at=T0 + 60)["action"], "idle")  # already checked today
        result = run(chain, ssm, ec2, daily, at=T0 + 86400)
        self.assertEqual((result["action"], result["unpause-check"], ec2.started), ("started", True, 1))
        ec2.state = "stopped"
        self.assertEqual(run(chain, ssm, ec2, daily, at=T0 + 86400 + 900)["action"], "idle")
        chain.caps[KEY] = (0, 5)  # a restore already pending: no start needed
        self.assertEqual(run(chain, ssm, ec2, daily, at=T0 + 2 * 86400)["action"], "idle")
        chain.caps[KEY] = (0, 0)
        self.assertEqual(run(chain, ssm, ec2, {"UNPAUSE_CHECK": "off"}, at=T0 + 3 * 86400)["action"], "idle")
        self.assertEqual(ec2.started, 1)

    def test_the_budget_s_stop_holds(self):
        env = {"BUDGET_NAME": "pof-snp-monthly", "ACCOUNT_ID": "123456789012"}
        for actual, expected in (("15.00", "budget"), ("14.99", "started")):
            with self.subTest(actual):
                chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
                chain.draw(1)
                budgets = FakeBudgets(actual=actual)
                result = run(chain, ssm, ec2, env, budgets=lambda: budgets)
                self.assertEqual(result["action"], expected)
                self.assertEqual(budgets.calls, 1)
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()  # no work: the budget isn't read
        budgets = FakeBudgets()
        run(chain, ssm, ec2, env, budgets=lambda: budgets)
        self.assertEqual(budgets.calls, 0)

    def test_an_instance_on_its_way_down_loses_nothing(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2("stopping")
        chain.draw(1)
        self.assertEqual(run(chain, ssm, ec2)["action"], "stopping")
        self.assertEqual((ssm.value, ec2.started), ("950", 0))
        ec2.state = "stopped"
        self.assertEqual(run(chain, ssm, ec2, at=T0 + 60)["action"], "started")

    def test_a_chain_outage_spends_nothing_and_loses_nothing(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1)
        chain.down = True
        with self.assertRaises(RuntimeError):
            run(chain, ssm, ec2)
        self.assertEqual((ssm.puts, ec2.started), (0, 0))
        chain.down = False
        self.assertEqual(run(chain, ssm, ec2)["action"], "started")

    def test_a_failed_start_saves_nothing(self):
        class Refused(FakeEc2):
            def start_instances(self, InstanceIds):
                raise RuntimeError("InsufficientInstanceCapacity")

        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), Refused()
        chain.draw(1)
        with self.assertRaises(RuntimeError):
            run(chain, ssm, ec2)
        self.assertEqual(ssm.value, "950")

    def test_the_first_run_looks_back_and_the_scan_resumes(self):
        chain, ssm, ec2 = FakeChain(head=5000), FakeSsm(None), FakeEc2()
        chain.draw(1, block=3700)  # before the look back (5000 - 1200 = 3800): its windows would be long over
        chain.draw(2, block=4900)
        result = run(chain, ssm, ec2, {"MAX_BLOCK_RANGE": "1000"})
        self.assertEqual((result["to"], result.get("seal")), (4799, None))
        self.assertEqual(run(chain, ssm, ec2, {"MAX_BLOCK_RANGE": "1000"}, at=T0 + 60)["seal"], [2])
        self.assertEqual(ssm.state()["last"], 5000)

    def test_a_seal_with_less_time_than_a_cold_start_is_flagged_late(self):
        """Minute windows (a devnet's 120 s seal): by the time the watcher sees the seat the node can't boot in time."""
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1, seal_in=90, reveal=60)
        result = run(chain, ssm, ec2)
        self.assertEqual((result["action"], result["seal_left_s"], result["late"]), ("started", 90, True))

    def test_the_state_stays_within_its_parameter(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2("running")
        for pid in range(1, 121):
            chain.draw(pid, slot=2)
        result = run(chain, ssm, ec2)
        self.assertTrue(result["state-full"])
        self.assertLessEqual(len(ssm.value), W.STATE_LIMIT)
        kept = sorted(map(int, ssm.state()["seats"]))
        self.assertEqual(kept[-1], 120)  # the newest are kept

    def test_a_malformed_validator_address_fails_the_run(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        with self.assertRaises(ValueError):
            run(chain, ssm, ec2, {"VALIDATOR_ADDRESS": "0x1234"})
        self.assertEqual(ssm.puts, 0)

    def test_panels_may_be_named_directly(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(1)
        result = run(chain, ssm, ec2, {"PANELS_ADDRESS": PANELS, "RACE_ADDRESS": ""})
        self.assertEqual(result["action"], "started")
        self.assertNotIn(W.CONTRACTS, json.dumps(chain.calls))


HEADS = "0x" + "ef" * 20
REPO_ID = "77" * 32


class HeadChain(FakeChain):
    """FakeChain plus RaceV3.repo(), Heads.head(repo) and contracts() naming Heads fifth (the Radicle duty)."""

    def __init__(self, commit="aa" * 20, **kw):
        super().__init__(**kw)
        self.commit, self.head_reads = commit, 0

    def call(self, method, params):
        if method == "eth_call":
            to, data = params[0]["to"], params[0]["data"]
            if data[:10] == W.CONTRACTS:
                return "0x" + _w(PANELS) + "".join(_w(HEADS if i == 3 else i + 1) for i in range(6))
            if data[:10] == W.REPO:
                assert to == RACE
                return "0x" + REPO_ID
            if data[:10] == W.HEAD:
                assert to == HEADS and data[10:] == REPO_ID
                self.head_reads += 1
                return "0x" + _w("0x" + self.commit + "00" * 12) + "".join(_w(x) for x in (9, T0, 1, 2, 3))
        return super().call(method, params)


class TheRadicleDuty(unittest.TestCase):
    """WAKE_ON_HEAD: the stopped instance is started once when Heads.head moves, so this validator's Radicle node, a
    delegate, pushes the canonical main to it (tests/integration/kit_radicle.py, scenario L, shows the lag without)."""

    ON = {"WAKE_ON_HEAD": "true"}

    def test_off_by_default_nothing_is_read(self):
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2()
        self.assertEqual(run(chain, ssm, ec2)["action"], "idle")
        self.assertEqual((chain.head_reads, ec2.started), (0, 0))
        self.assertNotIn("head", ssm.state())

    def test_the_first_run_records_the_head_and_starts_nothing(self):
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2()
        result = run(chain, ssm, ec2, env=self.ON)
        self.assertEqual((result["action"], ec2.started), ("idle", 0))
        self.assertEqual(ssm.state()["head"], "aa" * 20 + "00" * 12)

    def test_a_moved_head_starts_the_stopped_instance_once(self):
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2()
        run(chain, ssm, ec2, env=self.ON)
        chain.commit = "bb" * 20
        result = run(chain, ssm, ec2, env=self.ON)
        self.assertEqual((result["action"], result["radicle"], result["head"]), ("started", True, "bb" * 20))
        self.assertEqual(ec2.started, 1)
        self.assertEqual(ssm.state()["head"], "bb" * 20 + "00" * 12)
        ec2.state = "stopped"  # the node pushed and powered off: the same head starts nothing again
        self.assertEqual(run(chain, ssm, ec2, env=self.ON)["action"], "idle")
        self.assertEqual(ec2.started, 1)

    def test_a_running_node_takes_the_move(self):
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2("running")
        run(chain, ssm, ec2, env=self.ON)
        chain.commit = "cc" * 20
        result = run(chain, ssm, ec2, env=self.ON)
        self.assertEqual((result["action"], ec2.started), ("running", 0))
        self.assertEqual(ssm.state()["head"], "cc" * 20 + "00" * 12)

    def test_the_spend_pause_doesn_t_hold_it(self):
        """Pushing main makes no model call: like a reveal, it starts a paused validator."""
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2()
        chain.caps[KEY] = (0, 0)
        run(chain, ssm, ec2, env=self.ON)
        chain.commit, chain.head = "dd" * 20, 1010
        chain.draw(3, block=1005)  # a seal seat too: held by the pause
        result = run(chain, ssm, ec2, env=self.ON)
        self.assertEqual((result["action"], result["paused"], ec2.started), ("started", [3], 1))
        self.assertTrue(result["radicle"])

    def test_the_fuse_holds_it_and_it_is_tried_again(self):
        chain, ssm, ec2 = HeadChain(), FakeSsm("950"), FakeEc2()
        env = dict(self.ON, MAX_STARTS_PER_DAY="1", RETRY_MINUTES="0")
        run(chain, ssm, ec2, env=env)
        chain.head = 1010
        chain.draw(5, block=1005)
        self.assertEqual(run(chain, ssm, ec2, env=env)["action"], "started")  # the day's one start: a seat
        ec2.state = "stopped"
        chain.commit = "ee" * 20
        result = run(chain, ssm, ec2, env=env, at=T0 + 60)
        self.assertEqual((result["action"], ec2.started), ("fuse", 1))
        self.assertEqual(ssm.state()["head"], "aa" * 20 + "00" * 12)  # not seen yet: tried again
        result = run(chain, ssm, ec2, env=env, at=T0 + 86_400)  # the next UTC day
        self.assertEqual((result["action"], ec2.started), ("started", 2))
        self.assertEqual(ssm.state()["head"], "ee" * 20 + "00" * 12)

    def test_the_abi_is_race_v3_s_and_heads(self):
        self.assertEqual(W.REPO, "0x" + crypto.keccak256(b"repo()").hex()[:8])
        self.assertEqual(W.HEAD, "0x" + crypto.keccak256(b"head(bytes32)").hex()[:8])
        self.assertIn("bytes32 public immutable repo;", (V3 / "RaceV3.sol").read_text())
        heads = (ROOT / "contracts" / "src" / "v2" / "Heads.sol").read_text()
        self.assertIn("function head(bytes32 repo) external view returns (Head memory h)", heads)
        self.assertRegex(heads, r"struct Head \{\s+bytes32 commit;")  # the commit is the struct's first word
        self.assertIn('WAKE_ON_HEAD           = lookup(var.node_config, "ORACLE_MERGE_VIA", "") == "radicle" ? "true" '
                      ': "false"', (KIT / "terraform" / "watcher.tf").read_text())


class DrawChain(FakeChain):
    """FakeChain plus RaceV3's check-opening events and Panels.submission(id): `checks` {id: {"how", "block",
    "status", "seedBlock", "retryAt", "redraws"}}, `verdict_reads` the submission reads made."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.checks, self.verdict_reads = {}, []

    def open(self, cid, block=990, how="committed", status=1, seed_in=5, retry_at=0):
        self.checks[cid] = {"how": how, "block": block, "status": status, "seedBlock": block + seed_in,
                            "retryAt": retry_at, "redraws": 0}

    def call(self, method, params):
        if method == "eth_getLogs" and params[0]["address"] == RACE:
            q = params[0]
            assert q["topics"] == [[W.COMMITTED_TOPIC, W.REGISTERED_TOPIC, W.REBASED_TOPIC]]
            self.calls.append((method, params))
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            logs = []
            for cid, c in self.checks.items():
                if not lo <= c["block"] <= hi:
                    continue
                if c["how"] == "committed":  # Committed(bounty, submission, solver), all indexed
                    logs.append({"topics": [W.COMMITTED_TOPIC, hex(7), hex(cid), "0x" + _w(OTHER)], "data": "0x"})
                elif c["how"] == "registered":  # Registered(issue, reporter, check): the check in the data
                    logs.append({"topics": [W.REGISTERED_TOPIC, hex(3), "0x" + _w(OTHER)], "data": "0x" + _w(cid)})
                else:  # Rebased(bounty, original, check, fix, base)
                    logs.append({"topics": [W.REBASED_TOPIC, hex(7), hex(cid - 1), hex(cid)],
                                 "data": "0x" + _w("ab" * 32) + _w("cd" * 32)})
            return logs
        if method == "eth_call" and params[0]["data"][:10] == W.SUBMISSION:
            self.calls.append((method, params))
            assert params[0]["to"] == PANELS
            cid = int(params[0]["data"][10:], 16)
            self.verdict_reads.append(cid)
            c = self.checks.get(cid, {"status": 0, "seedBlock": 0, "retryAt": 0})
            words = [0] * 49
            words[0], words[1], words[2], words[3], words[42] = 0xC0, 1000, c["seedBlock"], c["status"], c["retryAt"]
            words[41] = c.get("redraws", 0)
            return "0x" + "".join(_w(x) for x in words)
        return super().call(method, params)


SEALED_, WAITING_, JUDGING_, WINDOW_, FINAL_, RELEASED_ = 1, 2, 3, 5, 6, 9
DRAW = {"WAKE_ON_DRAW": "true"}


def stagger(cid, key=KEY):
    return W.stagger(key, cid, 10)


class TheDrawDuty(unittest.TestCase):
    """WAKE_ON_DRAW (VP9): a check nobody drew starts the stopped instance once, past its grace (DRAW_GRACE_BLOCKS)
    and this validator's stagger, so the node's keeper draws it."""

    def at(self, chain, ssm, ec2, when, env=None, **kw):
        chain.now = when
        return run(chain, ssm, ec2, dict(DRAW, **(env or {})), at=when, **kw)

    def past_grace(self, cid=40, env=None, **kw):
        """A sealed check opened at block 990 (seed block 995), the head now 1021: past 995 + 25. Returns the chain,
        the SSM and EC2 fakes, and the first run's result (which records when it saw the check past its grace)."""
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(cid, **kw)
        first = self.at(chain, ssm, ec2, T0, env)  # the check listed; its grace not over (head 1000)
        self.assertEqual((first["action"], ssm.state()["draws"]), ("idle", {str(cid): {"b": 995}}))
        chain.head = 1021
        return chain, ssm, ec2, self.at(chain, ssm, ec2, T0 + 60, env)

    def test_off_by_default_no_race_event_is_read(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(40, block=900)
        self.assertEqual(run(chain, ssm, ec2)["action"], "idle")
        self.assertNotIn(RACE, json.dumps([p for m, p in chain.calls if m == "eth_getLogs"]))
        self.assertNotIn("draws", ssm.state())

    def test_an_undrawn_check_past_grace_and_stagger_starts_the_instance_once(self):
        cid = 40
        lag = stagger(cid)
        self.assertGreater(lag, 60)  # a key and id whose stagger spans more than one run
        chain, ssm, ec2, result = self.past_grace(cid)
        self.assertEqual((result["action"], ec2.started), ("idle", 0))  # past its grace: the stagger counts from now
        self.assertEqual(ssm.state()["draws"][str(cid)], {"b": 995, "at": T0 + 60})
        result = self.at(chain, ssm, ec2, T0 + 60 + lag - 1)
        self.assertEqual((result["action"], ec2.started), ("idle", 0))
        reads = len(chain.verdict_reads)
        result = self.at(chain, ssm, ec2, T0 + 60 + lag)
        self.assertEqual((result["action"], result["draw"], ec2.started), ("started", [cid], 1))
        self.assertEqual(ssm.state()["draws"][str(cid)]["n"], 1)
        ec2.state = "stopped"  # the node powered off without drawing it (say, it crashed)
        result = self.at(chain, ssm, ec2, T0 + 60 + lag + 300)  # within RETRY_MINUTES: not even read
        self.assertEqual((result["action"], ec2.started, len(chain.verdict_reads)), ("idle", 1, reads + 1))
        result = self.at(chain, ssm, ec2, T0 + 60 + lag + 600)  # still undrawn: given up, never a second start
        self.assertEqual((result["action"], result["draw_gave_up"], ec2.started), ("idle", [cid], 1))
        self.assertEqual(ssm.state()["draws"][str(cid)],  # listed still (VP23), given up for this round
                         {"b": 995, "at": T0 + 60, "n": 1, "s": T0 + 60 + lag, "x": 1, "c": T0 + 60 + lag + 600})
        result = self.at(chain, ssm, ec2, T0 + 60 + lag + 1200)  # read again, said once, never started again
        self.assertEqual((result["action"], "draw_gave_up" in result, ec2.started), ("idle", False, 1))

    def test_drawn_within_the_grace_nothing_starts(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(41)
        self.at(chain, ssm, ec2, T0)
        reads = len(chain.verdict_reads)
        chain.head = 1015
        self.at(chain, ssm, ec2, T0 + 60)
        self.assertEqual(len(chain.verdict_reads), reads)  # within its grace: no verdict read
        chain.checks[41]["status"] = JUDGING_  # a running keeper drew it
        chain.head = 1100
        result = self.at(chain, ssm, ec2, T0 + 3600)
        self.assertEqual((result["action"], result["draw_drawn"], ec2.started), ("idle", [41], 0))
        self.assertEqual(ssm.state()["draws"], {"41": {"d": 1, "c": T0 + 3600}})  # watched until final (VP23)

    def test_two_keys_start_at_different_times_for_the_same_check(self):
        cid = next(c for c in range(40, 200) if abs(stagger(c) - stagger(c, OTHER)) > 120)
        starts = {}
        for key in (KEY, OTHER):
            chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
            env = dict(DRAW, VALIDATOR_ADDRESS=key)
            chain.open(cid)
            self.at(chain, ssm, ec2, T0, env)
            chain.head = 1021
            for minute in range(1, 13):  # every minute for 12 minutes, as the schedule runs it
                if self.at(chain, ssm, ec2, T0 + 60 * minute, env)["action"] == "started":
                    starts[key] = minute
                    break
            self.assertEqual(ec2.started, 1, key)
            # the first run at or after the minute it saw the check past its grace plus its stagger
            self.assertEqual(starts[key], 1 + -(-stagger(cid, key) // 60), key)
        self.assertNotEqual(starts[KEY], starts[OTHER])

    def test_the_other_key_sees_it_drawn_and_drops_it(self):
        cid = next(c for c in range(40, 200) if stagger(c, OTHER) - stagger(c) > 120)
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        env = dict(DRAW, VALIDATOR_ADDRESS=OTHER)
        chain.open(cid)
        self.at(chain, ssm, ec2, T0, env)
        chain.head = 1021
        self.at(chain, ssm, ec2, T0 + 60, env)
        chain.checks[cid]["status"] = JUDGING_  # KEY's node drew it first
        result = self.at(chain, ssm, ec2, T0 + 60 + stagger(cid, OTHER), env)
        self.assertEqual((result["action"], result["draw_drawn"], ec2.started), ("idle", [cid], 0))

    def test_a_waiting_check_past_its_retry_time_starts_it(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        retry_at = T0 + 3600
        chain.open(42, status=WAITING_, retry_at=retry_at)
        due_at = retry_at + 25 * 12 + stagger(42)
        self.assertEqual(self.at(chain, ssm, ec2, T0)["action"], "idle")
        self.assertEqual(ssm.state()["draws"], {"42": {"r": retry_at}})
        reads = len(chain.verdict_reads)
        self.assertEqual(self.at(chain, ssm, ec2, due_at)["action"], "idle")  # not past it yet
        self.assertEqual(len(chain.verdict_reads), reads)  # and not read
        result = self.at(chain, ssm, ec2, due_at + 1)
        self.assertEqual((result["action"], result["draw"], ec2.started), ("started", [42], 1))

    def test_a_new_seed_block_or_retry_time_is_due_again(self):
        """A check re-targeted (its seed block over 256 blocks old) or drawn and still waiting (a new retryAt) gets
        its own start: DRAW_MAX_STARTS counts per seed block or retry time."""
        cid = 43
        chain, ssm, ec2, _ = self.past_grace(cid, env={"DRAW_STAGGER_MINUTES": "0"})
        self.assertEqual(ec2.started, 1)
        ec2.state = "stopped"
        chain.checks[cid].update(status=WAITING_, retryAt=T0 + 86_400)  # drawn: too few eligible, waits a day
        result = self.at(chain, ssm, ec2, T0 + 900, {"DRAW_STAGGER_MINUTES": "0"})
        self.assertEqual((result["action"], ssm.state()["draws"][str(cid)]), ("idle", {"r": T0 + 86_400}))
        result = self.at(chain, ssm, ec2, T0 + 86_400 + 301, {"DRAW_STAGGER_MINUTES": "0"})
        self.assertEqual((result["action"], ec2.started), ("started", 2))

    def test_a_drawn_check_released_back_to_waiting_and_redrawn_wakes_again(self):
        """VP23: a drawn check stays listed until final. Its panel released (L19), it waits again in a new round,
        which wakes this validator once for the redraw; the redraw's seat on this key wakes it as any seat."""
        cid, env = 70, {"DRAW_STAGGER_MINUTES": "0"}
        chain, ssm, ec2, result = self.past_grace(cid, env=env)
        self.assertEqual((result["action"], ec2.started), ("started", 1))  # the first draw's wake
        ec2.state = "stopped"
        chain.checks[cid]["status"] = JUDGING_  # this node's keeper drew it
        result = self.at(chain, ssm, ec2, T0 + 660, env)
        self.assertEqual((result["draw_drawn"], ssm.state()["draws"][str(cid)]), ([cid], {"d": 1, "c": T0 + 660}))
        reads = len(chain.verdict_reads)
        self.at(chain, ssm, ec2, T0 + 720, env)  # drawn: read again only every RETRY_MINUTES
        self.assertEqual(len(chain.verdict_reads), reads)
        retry_at = T0 + 3600  # the panel missed its deadlines: released back to waiting, a new round
        chain.checks[cid].update(status=WAITING_, redraws=1, retryAt=retry_at)
        result = self.at(chain, ssm, ec2, T0 + 1260, env)
        self.assertEqual((result["action"], ec2.started), ("idle", 1))
        self.assertEqual(ssm.state()["draws"][str(cid)], {"g": 1, "r": retry_at})
        result = self.at(chain, ssm, ec2, retry_at + 25 * 12 + 1, env)
        self.assertEqual((result["action"], result["draw"], ec2.started), ("started", [cid], 2))  # the redraw's wake
        ec2.state = "stopped"
        chain.checks[cid]["status"] = JUDGING_  # redrawn: this validator is seated on the new panel
        chain.draw(9, block=1030)
        chain.head = 1040
        result = self.at(chain, ssm, ec2, retry_at + 25 * 12 + 61, env)
        self.assertEqual((result["action"], result["seal"], ec2.started), ("started", [9], 3))  # its new seat wakes it

    def test_polling_never_starts_twice_for_the_same_round(self):
        """VP23: neither a drawn check nor an undrawn one already started for its round starts the instance again,
        however long it is polled; a round's starts survive its being drawn and read again."""
        cid, env = 71, {"DRAW_STAGGER_MINUTES": "0"}
        chain, ssm, ec2, result = self.past_grace(cid, env=env)
        self.assertEqual(ec2.started, 1)
        ec2.state = "stopped"
        for minute in range(2, 240):  # four hours of runs, still undrawn: given up for this round
            self.at(chain, ssm, ec2, T0 + 60 * minute, env)
        self.assertEqual(ec2.started, 1)
        chain.checks[cid]["status"] = JUDGING_
        for minute in range(240, 480):  # drawn, then four hours more
            self.assertNotEqual(self.at(chain, ssm, ec2, T0 + 60 * minute, env)["action"], "started")
        self.assertEqual(ec2.started, 1)
        self.assertIn(str(cid), ssm.state()["draws"])

    def test_a_drawn_check_leaves_the_list_once_final(self):
        cid, env = 72, {"DRAW_STAGGER_MINUTES": "0"}
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(cid, status=JUDGING_)
        self.assertEqual(self.at(chain, ssm, ec2, T0, env)["draw_drawn"], [cid])
        chain.checks[cid]["status"] = WINDOW_
        self.at(chain, ssm, ec2, T0 + 600, env)
        self.assertEqual(ssm.state()["draws"], {str(cid): {"d": 1, "c": T0 + 600}})  # in its window: kept
        chain.checks[cid]["status"] = FINAL_
        result = self.at(chain, ssm, ec2, T0 + 1200, env)
        self.assertEqual((result["draw_dropped"], ec2.started), ({str(cid): "final"}, 0))
        self.assertNotIn("draws", ssm.state())

    def test_another_slot_on_a_listed_panel_is_a_new_seat(self):
        """A replacement seat on a panel this key already sits on (another slot) gets its own starts."""
        chain, ssm, ec2 = DrawChain(), FakeSsm(json.dumps({"last": 950, "seats": {"5": {"slot": 0,
                                                                                         "seal": [T0, 3]}}})), FakeEc2()
        chain.draw(5, slot=2, block=995)
        result = self.at(chain, ssm, ec2, T0 + 60)
        self.assertEqual((result["action"], result["seal"], ec2.started), ("started", [5], 1))
        self.assertEqual(ssm.state()["seats"]["5"], {"slot": 2, "seal": [T0 + 60, 1]})

    def test_the_fuse_holds_it(self):
        env = {"MAX_STARTS_PER_DAY": "1", "DRAW_STAGGER_MINUTES": "0"}
        chain, ssm, ec2 = DrawChain(), FakeSsm(json.dumps({"last": 950, "fuse": {"day": "2026-11-18", "starts": 1}})), \
            FakeEc2()
        chain.open(44)
        self.at(chain, ssm, ec2, T0, env)
        chain.head = 1021
        result = self.at(chain, ssm, ec2, T0 + 60, env)
        self.assertEqual((result["action"], result["draw"], ec2.started), ("fuse", [44], 0))
        self.assertNotIn("n", ssm.state()["draws"]["44"])  # no start spent: tried again
        result = self.at(chain, ssm, ec2, T0 + 86_400, env)  # the next UTC day
        self.assertEqual((result["action"], ec2.started), ("started", 1))

    def test_the_budget_holds_it(self):
        env = {"BUDGET_NAME": "pof-snp-monthly", "ACCOUNT_ID": "123456789012", "DRAW_STAGGER_MINUTES": "0"}
        budgets = FakeBudgets(actual="15.00")
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(45)
        self.at(chain, ssm, ec2, T0, env, budgets=lambda: budgets)
        chain.head = 1021
        result = self.at(chain, ssm, ec2, T0 + 60, env, budgets=lambda: budgets)
        self.assertEqual((result["action"], ec2.started, budgets.calls), ("budget", 0, 1))
        self.assertNotIn("n", ssm.state()["draws"]["45"])

    def test_the_kill_switch_holds_it(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(46, block=900)
        self.assertEqual(self.at(chain, ssm, ec2, T0 + 3600, {"ENABLED": "false"}), {"action": "disabled"})
        self.assertEqual((chain.calls, ec2.started, ssm.value), ([], 0, "950"))

    def test_the_spend_pause_doesn_t_hold_it(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.caps[KEY] = (0, 0)
        chain.draw(3, block=995)  # a seal seat: held by the pause
        chain.open(47)
        env = {"DRAW_STAGGER_MINUTES": "0"}
        self.assertEqual(self.at(chain, ssm, ec2, T0, env)["action"], "paused")
        chain.head = 1021
        result = self.at(chain, ssm, ec2, T0 + 60, env)
        self.assertEqual((result["action"], result["draw"], result["paused"], ec2.started), ("started", [47], [3], 1))

    def test_a_running_instance_spends_no_start(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2("running")
        chain.open(48)
        env = {"DRAW_STAGGER_MINUTES": "0"}
        self.at(chain, ssm, ec2, T0, env)
        chain.head = 1021
        result = self.at(chain, ssm, ec2, T0 + 60, env)
        self.assertEqual((result["action"], result["draw"], ec2.started), ("running", [48], 0))
        self.assertNotIn("n", ssm.state()["draws"]["48"])  # its node's keeper draws it

    def test_final_refunded_withdrawn_and_expired_checks_leave_the_list(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        for cid, status in ((50, RELEASED_), (51, 7), (52, 8), (53, FINAL_), (54, 0)):
            chain.open(cid, status=status)
        result = self.at(chain, ssm, ec2, T0)
        self.assertEqual(result["draw_dropped"], {"50": "released", "51": "withdrawn", "52": "expired",
                                                  "53": "final", "54": "none"})
        self.assertNotIn("draws", ssm.state())

    def test_each_event_opens_a_check(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2()
        chain.open(60, how="committed")
        chain.open(61, how="registered", block=995)
        chain.open(62, how="rebased", block=999)
        chain.open(63, block=1001)  # after the head: the next run's
        self.at(chain, ssm, ec2, T0)
        self.assertEqual(sorted(ssm.state()["draws"]), ["60", "61", "62"])
        race_scans = [p[0] for m, p in chain.calls if m == "eth_getLogs" and p[0]["address"] == RACE]
        self.assertEqual([(q["fromBlock"], q["toBlock"]) for q in race_scans], [(hex(951), hex(1000))])

    def test_at_most_draw_reads_max_verdicts_a_run_in_turn(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2("running")
        for cid in range(100, 125):
            chain.open(cid)
        env = {"DRAW_READS_MAX": "20", "DRAW_STAGGER_MINUTES": "0"}
        result = self.at(chain, ssm, ec2, T0, env)
        self.assertEqual((len(chain.verdict_reads), result["draw_reads_max"]), (20, True))
        self.assertEqual(chain.verdict_reads, list(range(100, 120)))
        chain.verdict_reads.clear()
        result = self.at(chain, ssm, ec2, T0 + 60, env)
        self.assertEqual(chain.verdict_reads, list(range(120, 125)))  # the rest, from the cursor
        self.assertNotIn("draw_reads_max", result)
        chain.head = 1021
        chain.verdict_reads.clear()
        result = self.at(chain, ssm, ec2, T0 + 120, env)
        self.assertEqual(chain.verdict_reads, list(range(100, 120)))  # all 25 due: 20 this run
        self.assertEqual(len(result["draw"]), 20)

    def test_checks_are_dropped_before_seats_when_the_state_is_full(self):
        chain, ssm, ec2 = DrawChain(), FakeSsm("950"), FakeEc2("running")
        chain.draw(1)
        for cid in range(1000, 1400):
            chain.open(cid)
        result = self.at(chain, ssm, ec2, T0, {"DRAW_READS_MAX": "0"})
        self.assertTrue(result["state-full"])
        self.assertLessEqual(len(ssm.value), W.STATE_LIMIT)
        self.assertIn("1", ssm.state()["seats"])
        self.assertEqual(max(map(int, ssm.state()["draws"])), 1399)  # the newest kept

    def test_drawn_checks_are_dropped_before_undrawn_ones_when_the_state_is_full(self):
        state = {"last": 1, "draws": {str(c): {"d": 1, "c": T0} for c in range(2000, 2100)}}
        state["draws"].update({"1": {"b": 995}, "2": {"r": T0}})
        self.assertTrue(W._fit(state, limit=600))
        self.assertEqual({"1", "2"} & set(state["draws"]), {"1", "2"})  # the older undrawn checks stay
        self.assertEqual(max(map(int, state["draws"])), 2099)

    def test_the_abi_is_race_v3_s_events_and_panels_submission(self):
        for topic, sig in ((W.COMMITTED_TOPIC, "Committed(uint256,uint256,address)"),
                           (W.REGISTERED_TOPIC, "Registered(uint256,address,uint256)"),
                           (W.REBASED_TOPIC, "Rebased(uint256,uint256,uint256,bytes32,bytes32)")):
            self.assertEqual(topic, "0x" + crypto.keccak256(sig.encode()).hex(), sig)
        self.assertEqual(W.SUBMISSION, "0x" + crypto.keccak256(b"submission(uint256)").hex()[:8])
        race = (V3 / "RaceV3Base.sol").read_text()
        for event in ("event Committed(uint256 indexed bounty, uint256 indexed submission, address indexed solver);",
                      "event Registered(uint256 indexed issue, address indexed reporter, uint256 check);",
                      "event Rebased(uint256 indexed bounty, uint256 indexed original, uint256 indexed check, "
                      "bytes32 fix, bytes32 base);"):
            self.assertIn(event, race)
        self.assertIn("else panels.open(id, commitment, judged);", race)  # a check's id is its Panels id
        self.assertIn("function submission(uint256 id) external view returns (Submission memory)",
                      (V3 / "Panels.sol").read_text())
        base = (V3 / "PanelsBase.sol").read_text()
        body = re.search(r"struct Submission \{(.*?)\n\}", base, re.S).group(1)
        at, words = {}, 0
        for m in re.finditer(r"^\s+([\w.]+) (\w+);", body, re.M):
            at[m.group(2)] = words
            words += 4 if m.group(1) == "PanelsDraw.Snap" else 1  # a Snap is 4 static words (checked above)
        self.assertEqual((at["seedBlock"], at["status"], at["redraws"], at["retryAt"], words), (2, 3, 41, 42, 49))
        statuses = re.search(r"enum Status \{(.*?)\}", base, re.S).group(1)
        names = [re.sub(r"//.*", "", line).strip().strip(",").lower() for line in statuses.splitlines()]
        self.assertEqual(tuple(n for n in names if n), W.STATUSES)
        self.assertEqual((W.STATUSES[W.SEALED], W.STATUSES[W.WAITING]), ("sealed", "waiting"))

    def test_its_keccak256_is_ethereum_s(self):
        for data in (b"", b"abc", b"x" * 135, b"x" * 136, b"y" * 300, bytes(range(64))):
            self.assertEqual(W.keccak256(data), crypto.keccak256(data))
        self.assertEqual(W.stagger(KEY, 40, 10), int.from_bytes(crypto.keccak256(bytes.fromhex(
            _w(KEY) + _w(40))), "big") % 600)
        self.assertEqual(W.stagger(KEY, 40, 0), 0)

    def test_the_kit_turns_it_on(self):
        tf = (KIT / "terraform" / "watcher.tf").read_text()
        self.assertIn('WAKE_ON_DRAW           = var.watcher_wake_on_draw ? "true" : "false"', tf)
        self.assertRegex(tf, r'variable "watcher_wake_on_draw" \{[^}]*default     = true')


class TheBlockRange(unittest.TestCase):
    def test_max_block_range_from_the_env_and_the_kit(self):
        chain, ssm, ec2 = DrawChain(head=5000), FakeSsm("950"), FakeEc2()
        result = run(chain, ssm, ec2, dict(DRAW, MAX_BLOCK_RANGE="50"))
        self.assertEqual(result["to"], 1000)
        scans = [(p[0]["address"], p[0]["fromBlock"], p[0]["toBlock"]) for m, p in chain.calls if m == "eth_getLogs"]
        self.assertEqual(scans, [(PANELS, hex(951), hex(1000)), (RACE, hex(951), hex(1000))])
        self.assertEqual(run(FakeChain(head=5000), FakeSsm("950"), FakeEc2())["to"], 950 + W.MAX_BLOCK_RANGE)
        tf = (KIT / "terraform" / "watcher.tf").read_text()
        self.assertIn("MAX_BLOCK_RANGE        = tostring(var.watcher_max_block_range)", tf)
        self.assertRegex(tf, r'variable "watcher_max_block_range" \{[^}]*default     = %d' % W.MAX_BLOCK_RANGE)


KEY_IN_PATH = "0123456789abcdef0123456789abcdef"
KEYED_URL = f"https://sepolia.provider.example/v3/{KEY_IN_PATH}"


class NoKeyInTheLogs(unittest.TestCase):
    """VP20: the shown URL is scheme, host and `/…`; every line main() prints, tracebacks included, is redacted."""

    def setUp(self):
        self.saved = list(W.REDACT.secrets)

    def tearDown(self):
        W.REDACT.secrets = self.saved

    def assert_no_key(self, text):
        for i in range(len(KEY_IN_PATH) - 7):  # no 8 characters of it
            self.assertNotIn(KEY_IN_PATH[i:i + 8], text)

    def secrets(self, url=KEYED_URL):
        class Secrets:
            def get_secret_value(self, SecretId):
                return {"SecretString": url}

        return Secrets()

    def main(self, clients, env=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                W.main(dict(ENV, **dict({"RPC_URL_SECRET_ARN": "arn:rpc"}, **(env or {}))), lambda name: clients[name])
                error = None
            except RuntimeError as e:
                error = e
        return out.getvalue(), error

    def test_the_shown_url(self):
        self.assertEqual(W.shown_url(KEYED_URL), "https://sepolia.provider.example/…")
        self.assertEqual(W.shown_url("https://eth.example/v2/abcdefgh"), "https://eth.example/…")
        self.assertEqual(W.shown_url("http://127.0.0.1:8545"), "http://127.0.0.1:8545")
        self.assertEqual(W.shown_url("https://rpc.example/v3/rpc"), "https://rpc.example/v3/rpc")
        self.assertEqual(W.shown_url("https://u:pw@rpc.example/"), "https://rpc.example/")
        self.assertEqual(W.Rpc(KEYED_URL).shown, "https://sepolia.provider.example/…")

    def test_a_429_from_a_keyed_url_logs_no_part_of_the_key(self):
        err = urllib.error.HTTPError(KEYED_URL, 429, "Too Many Requests", {"Retry-After": "1"}, None)
        clients = {"secretsmanager": self.secrets(), "ssm": FakeSsm("950"), "ec2": FakeEc2()}
        with unittest.mock.patch("urllib.request.urlopen", side_effect=err):
            out, error = self.main(clients, DRAW)
        self.assertIsNotNone(error)
        self.assertIn("429", out)
        self.assertIn("https://sepolia.provider.example/…", out)
        self.assert_no_key(out)
        self.assert_no_key(str(error))
        self.assertIsNone(error.__cause__)
        self.assertEqual(clients["ssm"].puts, 0)  # nothing saved

    def test_a_traceback_that_prints_the_url_is_redacted(self):
        class Leaky(FakeSsm):
            def get_parameter(self, Name):
                raise ValueError(f"cannot reach {KEYED_URL} (key {KEY_IN_PATH})")

        clients = {"secretsmanager": self.secrets(), "ssm": Leaky("950"), "ec2": FakeEc2()}
        out, error = self.main(clients)
        self.assertIn("Traceback", out)
        self.assertIn("ValueError", out)
        self.assert_no_key(out)
        self.assert_no_key(str(error))

    def test_a_header_key_is_redacted_too(self):
        class Secrets:
            def get_secret_value(self, SecretId):
                return {"SecretString": "handle:" + KEY_IN_PATH} if SecretId == "arn:k" else {"SecretString": ""}

        class Leaky(FakeSsm):
            def get_parameter(self, Name):
                raise ValueError(f"header was Basic handle:{KEY_IN_PATH}")

        clients = {"secretsmanager": Secrets(), "ssm": Leaky("950"), "ec2": FakeEc2()}
        out, error = self.main(clients, {"RPC_URL_SECRET_ARN": "", "RPC_URL": "https://chain.example",
                                         "RPC_API_KEY_SECRET_ARN": "arn:k"})
        self.assert_no_key(out)
        self.assert_no_key(str(error))

    def test_a_disabled_run_logs_one_line(self):
        out, error = self.main({}, {"ENABLED": "false"})
        self.assertEqual((out.strip(), error), ('{"action": "disabled"}', None))


class TheRpc(unittest.TestCase):
    def test_the_url_from_its_secret_and_never_in_an_error(self):
        url = "https://eth-sepolia.example/v2/SECRETKEY123"

        class Secrets:
            def get_secret_value(self, SecretId):
                assert SecretId == "arn:aws:secretsmanager:us-east-2:1:secret:rpc"
                return {"SecretString": url + "\n"}

        rpc = W.rpc_from_env({"RPC_URL_SECRET_ARN": "arn:aws:secretsmanager:us-east-2:1:secret:rpc"}, Secrets)
        self.assertEqual((rpc.url, rpc.api_key), (url, None))
        with unittest.mock.patch("urllib.request.urlopen",
                                 side_effect=urllib.error.URLError(f"cannot reach {url}")):
            with self.assertRaises(RuntimeError) as e:
                rpc.call("eth_blockNumber", [])
        self.assertNotIn("SECRETKEY123", str(e.exception))
        self.assertIsNone(e.exception.__cause__)

    def test_a_header_key_and_no_url(self):
        class Secrets:
            def get_secret_value(self, SecretId):
                return {"SecretString": "dev:k3y"}

        rpc = W.rpc_from_env({"RPC_URL": "https://chain.example", "RPC_API_KEY_SECRET_ARN": "arn:k"}, Secrets)
        self.assertEqual(rpc.headers()["Authorization"], "Basic ZGV2OmszeQ==")
        with self.assertRaises(RuntimeError):
            W.rpc_from_env({}, Secrets)


class TheTerraform(unittest.TestCase):
    text = (KIT / "terraform" / "watcher.tf").read_text()

    def test_it_starts_this_instance_only_and_is_off_by_default(self):
        start = self.text[self.text.index('sid       = "StartThisInstanceOnly"'):]
        start = start[:start.index("}")]
        self.assertIn('actions   = ["ec2:StartInstances"]', start)
        self.assertIn("resources = local.watcher_instance_arns", start)
        self.assertIn('"arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${i.id}"',
                      self.text)
        for never in ('"ec2:*"', '"ec2:StopInstances"', '"ec2:RunInstances"', '"*:*"', "secretsmanager:*",
                      "ssm:*"):
            self.assertNotIn(never, self.text)
        variables = (KIT / "terraform" / "variables.tf").read_text()
        self.assertRegex(variables, r'variable "watcher_enabled" \{[^}]*default     = false')
        self.assertIn('ENABLED                = var.watcher_enabled ? "true" : "false"', self.text)
        self.assertIn('state               = var.watcher_enabled ? "ENABLED" : "DISABLED"', self.text)
        self.assertIn('schedule_expression = "rate(1 minute)"', self.text)
        self.assertIn("watcher = var.create_instance ? 1 : 0", self.text)
        self.assertIn('source_file = "${path.module}/../lambda/watcher.py"', self.text)

    def test_the_guardrails_reach_the_function(self):
        for env in ("MAX_STARTS_PER_DAY     = tostring(var.max_starts_per_day)", "UNPAUSE_CHECK          = var.unpause_check",
                    "BUDGET_NAME            = local.watcher_budget", "RPC_URL_SECRET_ARN     = var.rpc_url_secret_arn",
                    "VALIDATOR_ADDRESS      = var.validator_address"):
            self.assertIn(env, self.text)
        self.assertIn('actions   = ["budgets:ViewBudget"]', self.text)
        self.assertIn("retention_in_days = var.log_retention_days", self.text)

    def test_python_3_9(self):
        self.assertIn("from __future__ import annotations", (KIT / "lambda" / "watcher.py").read_text())

    @unittest.skipUnless(shutil.which("tofu"), "OpenTofu not installed (the CI runner has none)")
    def test_tofu_fmt(self):
        subprocess.run(["tofu", "fmt", "-check", "-recursive"], cwd=KIT / "terraform", check=True)


if __name__ == "__main__":
    unittest.main()
