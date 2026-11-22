"""The SEV-SNP validator's v3 watcher (validator-kit/sevsnp/lambda/watcher.py; #251 task 4.9, #253): it starts the
stopped instance only for this key's seats on v3's Panels that need the node, with v2's guardrails (the kill switch,
the day's fuse, retries per seat) plus the spend pause and the budget. No network and no AWS: the chain (Panels'
Seated event and views), SSM, EC2 and Budgets are fakes. Also the Terraform's static checks."""

from __future__ import annotations

import importlib.util
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

    def test_a_sealed_seat_starts_the_node_for_its_reveal(self):
        chain, ssm, ec2 = FakeChain(), FakeSsm("950"), FakeEc2()
        chain.draw(5, seal_in=1000)
        chain.seats[(5, 0)]["hasSeal"] = True
        chain.panels[5]["nSealed"] = 3
        result = run(chain, ssm, ec2)  # the reveal window opens in 1000 s: more than the lead (180 s)
        self.assertEqual((result["action"], ec2.started), ("idle", 0))
        self.assertIn("5", ssm.state()["seats"])  # still listed, waiting
        chain.now += 850  # 150 s before it opens
        result = run(chain, ssm, ec2, at=T0 + 850)
        self.assertEqual((result["action"], result["reveal"]), ("started", [5]))

    def test_a_reveal_waits_while_the_panel_isnt_fully_sealed(self):
        """A judging panel's reveal window opens only once every seat sealed (a refill then restarts the windows); a
        shadow's opens on its own."""
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
