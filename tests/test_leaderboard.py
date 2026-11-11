"""The contributor leaderboard (proof-of-fix#151) on a fixed event history: raw logs, as a v2 devnet's RaceV2 and meter
emit them, decoded by pofctl's race and ranked by pofctl/leaderboard.py. The expected tables are worked out by hand
from the history below; the board must match them exactly. And the bot's step that closes a paid bounty's issue, on the
fake GitHub and against a Forgejo's API."""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from bot import logic
from bot.forge import ForgejoRepo
from bot.github import GitHubRepo
from fake_github import FakeGitHub
from oracle import abi
from oracle.crypto import keccak256
from pofctl import cli, leaderboard
from pofctl.race import Race

sys.path.insert(0, str(Path(__file__).resolve().parent / "integration"))  # targets.py: the suite's check

RACE, METER, COIN, COIN2 = "0x" + "a1" * 20, "0x" + "a2" * 20, "0x" + "c1" * 20, "0x" + "c2" * 20
INFRA = "0x" + "1f" * 20
R, R2 = "0x" + "11" * 20, "0x" + "12" * 20  # reporters
F1, F2 = "0x" + "21" * 20, "0x" + "22" * 20  # funders
S1, S2 = "0x" + "31" * 20, "0x" + "32" * 20  # solvers
J1, J2, J3, P3 = "0x" + "41" * 20, "0x" + "42" * 20, "0x" + "43" * 20, "0x" + "4f" * 20  # judges; P3 is J3's payee
DAY, T0 = 86_400, 1_700_000_000
M = 10**6
OPEN, WON, MERGED, PAID = 1, 2, 3, 4
PASS, FAIL = 1, 2
REWARDED, RETURNED, FORFEITED = 2, 3, 4

# block -> its day after T0 (the chain's clock; the devnet warps it)
DAYS = {**{b: b - 10 for b in range(10, 13)}, **{b: 2 for b in range(13, 22)}, 22: 20,
        **{b: 30 for b in range(23, 27)}, **{b: 35 for b in range(30, 37)}, 37: 38, 38: 39, 39: 39,
        **{b: 39 for b in range(40, 44)}, 50: 40}

# The history: (block, tx, contract, event signature, indexed values, data types, data values).
HISTORY = [
    # bounty 1 (issue 1, reporter R): two funders, S1 attempts and wins, S2's pass comes second, paid in two parts
    (10, 1, RACE, "Collected(address,address,address,uint256)", [COIN, R, INFRA], ["uint256"], [M]),
    (10, 1, RACE, "Registered(uint256,address)", [1, R], [], []),
    (11, 2, RACE, "BountyOpened(uint256,uint256)", [1, 1], [], []),
    (11, 2, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [OPEN]),
    (12, 3, RACE, "Pledged(uint256,address,address,uint256)", [1, COIN, F1], ["uint256"], [100 * M]),
    (13, 4, RACE, "Pledged(uint256,address,address,uint256)", [1, COIN, F2], ["uint256"], [50 * M]),
    (14, 5, RACE, "Collected(address,address,address,uint256)", [COIN, S1, INFRA], ["uint256"], [M // 2]),
    (14, 5, RACE, "Locked(uint256,uint256)", [1], ["uint256"], [5000]),
    (14, 5, RACE, "Attempted(uint256,address)", [1, S1], [], []),
    (15, 6, RACE, "Committed(uint256,uint256,address)", [1, 1, S1], [], []),
    (16, 7, RACE, "Committed(uint256,uint256,address)", [1, 2, S2], [], []),
    (17, 8, METER, "Reported(uint256,address,address,bytes32)", [1, J1], ["address", "bytes32"], [J1, b"\1" * 32]),
    (17, 9, METER, "Reported(uint256,address,address,bytes32)", [1, J2], ["address", "bytes32"], [J2, b"\2" * 32]),
    (17, 10, METER, "Reported(uint256,address,address,bytes32)", [1, J3], ["address", "bytes32"], [P3, b"\3" * 32]),
    (18, 11, METER, "Charged(uint256,uint256,uint256)", [1], ["uint256", "uint256"], [3, 300_000]),
    (18, 11, RACE, "Decided(uint256,uint8)", [1], ["uint8"], [PASS]),
    (18, 11, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [WON]),
    (19, 12, METER, "Reported(uint256,address,address,bytes32)", [2, J1], ["address", "bytes32"], [J1, b"\4" * 32]),
    (19, 13, METER, "Reported(uint256,address,address,bytes32)", [2, J2], ["address", "bytes32"], [J2, b"\5" * 32]),
    (20, 14, METER, "Charged(uint256,uint256,uint256)", [2], ["uint256", "uint256"], [2, 200_000]),
    (20, 14, RACE, "Decided(uint256,uint8)", [2], ["uint8"], [PASS]),
    (21, 15, RACE, "Awarded(uint256,uint256,address)", [1, 1], ["address"], [S1]),
    (21, 15, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [MERGED]),
    (21, 16, RACE, "TooLate(uint256,address)", [1, S2], [], []),
    (22, 17, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [30 * M]),  # claimInstalments
    (23, 18, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [PAID]),  # settle: in the contract's order
    (23, 18, RACE, "IssueClosed(uint256,uint8)", [1], ["uint8"], [REWARDED]),
    (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [60 * M]),  # instalments due
    (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, R], ["uint256"], [15 * M]),  # finder's fee
    (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, R], ["uint256"], [M]),  # registration refund
    (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [300_000]),  # checks refunded
    (24, 19, RACE, "Refunded(uint256,address,address,uint256)", [1, COIN, F1], ["uint256"], [29 * M]),
    (25, 20, RACE, "Refunded(uint256,address,address,uint256)", [1, COIN, F2], ["uint256"], [14 * M]),
    (25, 20, RACE, "Refunded(uint256,address,address,uint256)", [1, COIN, F2], ["uint256"], [1]),  # the remainder
    (26, 21, RACE, "Withdrawn(address,address,address,uint256)", [J1, COIN], ["address", "uint256"], [J1, 250_000]),
    (26, 22, RACE, "Withdrawn(address,address,address,uint256)", [P3, COIN], ["address", "uint256"], [P3, 100_000]),
    (26, 23, RACE, "Withdrawn(address,address,address,uint256)", [R, COIN], ["address", "uint256"], [R, 16 * M]),
    # bounty 2 (issue 2, reporter R): F1 pledges in two coins, S2's merge is clawed back, S1's fix fails (no meter)
    (30, 24, RACE, "Collected(address,address,address,uint256)", [COIN, R, INFRA], ["uint256"], [M]),
    (30, 24, RACE, "Registered(uint256,address)", [2, R], [], []),
    (31, 25, RACE, "BountyOpened(uint256,uint256)", [2, 2], [], []),
    (32, 26, RACE, "Pledged(uint256,address,address,uint256)", [2, COIN2, F1], ["uint256"], [5 * M]),
    (32, 27, RACE, "Pledged(uint256,address,address,uint256)", [2, COIN, F1], ["uint256"], [20 * M]),
    (33, 28, RACE, "Committed(uint256,uint256,address)", [2, 3, S2], [], []),
    (34, 29, METER, "Reported(uint256,address,address,bytes32)", [3, J2], ["address", "bytes32"], [J2, b"\6" * 32]),
    (34, 30, METER, "Reported(uint256,address,address,bytes32)", [3, J3], ["address", "bytes32"], [P3, b"\7" * 32]),
    (35, 31, METER, "Charged(uint256,uint256,uint256)", [3], ["uint256", "uint256"], [2, 210_000]),
    (35, 31, RACE, "Decided(uint256,uint8)", [3], ["uint8"], [PASS]),
    (36, 32, RACE, "Awarded(uint256,uint256,address)", [2, 1], ["address"], [S2]),
    (37, 33, RACE, "ClawedBack(uint256,uint256,uint256)", [2, 1], ["uint256"], [0]),
    (37, 33, RACE, "StateChanged(uint256,uint8)", [2], ["uint8"], [OPEN]),
    (38, 34, RACE, "Committed(uint256,uint256,address)", [2, 4, S1], [], []),
    (39, 35, RACE, "Decided(uint256,uint8)", [4], ["uint8"], [FAIL]),
    # issue 3 (R2) refused as similar to bounty 2; issue 4 (R2) junk
    (40, 36, RACE, "Collected(address,address,address,uint256)", [COIN, R2, INFRA], ["uint256"], [M]),
    (40, 36, RACE, "Registered(uint256,address)", [3, R2], [], []),
    (41, 37, RACE, "IssueClosed(uint256,uint8)", [3], ["uint8"], [RETURNED]),
    (41, 37, RACE, "RefusedSimilar(uint256,uint256)", [3, 2], [], []),
    (42, 38, RACE, "Registered(uint256,address)", [4, R2], [], []),
    (43, 39, RACE, "IssueClosed(uint256,uint8)", [4], ["uint8"], [FORFEITED]),
]


def raw_logs(history):
    out, index = [], {}
    for block, tx, contract, sig, indexed, types, values in history:
        i = index.get(block, 0)
        index[block] = i + 1
        topics = ["0x" + keccak256(sig.encode()).hex()]
        topics += ["0x%064x" % (int(v, 16) if isinstance(v, str) else v) for v in indexed]
        out.append({"address": contract, "topics": topics, "data": "0x" + abi.encode(types, values).hex(),
                    "blockNumber": hex(block), "transactionHash": "0x%064x" % tx, "logIndex": hex(i)})
    return out


class FakeRpc:
    """eth_getLogs over the fixed history, and each block's time."""

    def __init__(self, history=HISTORY, latest=50):
        self.logs_ = raw_logs(history)
        self.latest = latest
        self.block_reads = 0

    def logs(self, address, from_block=0, topics=None, to_block=None):
        out = [x for x in self.logs_ if x["address"] == address and int(x["blockNumber"], 16) >= from_block]
        for i, t in enumerate(topics or []):
            out = [x for x in out if len(x["topics"]) > i and x["topics"][i] == t]
        return out

    def call(self, method, params):
        assert method == "eth_getBlockByNumber", method
        block = self.latest if params[0] == "latest" else int(params[0], 16)
        self.block_reads += params[0] != "latest"
        return {"number": hex(block), "timestamp": hex(T0 + DAYS[block] * DAY)}

    def chain_id(self):
        return 7193


def board(period="all", bounties=None, role=None, history=HISTORY):
    race = Race(FakeRpc(history), {"race": RACE, "coin": COIN, "quoter": "0x" + "00" * 20, "meter": METER,
                                   "block": 0})
    block, now = race.now()
    events = race.board_events(with_time=period != "all")
    return leaderboard.compute(events, COIN, period, now, bounties, role)


def rows(b, role):
    return [{k: v for k, v in r.items() if k != "address"} | {"address": r["address"].lower()} for r in b[role]]


def row(address, rank, **metrics):
    return {"address": address, "rank": rank, **metrics}


def solver(address, rank, earned=0, merged=0, won=0, passed=0, decided=0, submissions=0, attempts=0, late=0,
           clawedBack=0):
    rate = round(passed / decided, 4) if decided else None
    return row(address, rank, earned=earned, merged=merged, won=won, passed=passed, decided=decided,
               submissions=submissions, attempts=attempts, late=late, clawedBack=clawedBack, passRate=rate)


def reporter(address, rank, finderFees=0, opened=0, registered=0, rewarded=0, refused=0, junk=0):
    return row(address, rank, finderFees=finderFees, opened=opened, registered=registered, rewarded=rewarded,
               refused=refused, junk=junk)


def funder(address, rank, pledged=0, bounties=0, solved=0, refunds=0, refunded=0):
    return row(address, rank, pledged=pledged, bounties=bounties, solved=solved, refunds=refunds, refunded=refunded)


def validator(address, rank, counted=0, reports=0, withdrawn=0):
    return row(address, rank, counted=counted, reports=reports, withdrawn=withdrawn)


class TestLeaderboard(unittest.TestCase):
    def test_all_time(self):
        b = board()
        self.assertEqual(rows(b, "solvers"), [
            solver(S1, 1, earned=90 * M, merged=1, won=1, passed=1, decided=2, submissions=2, attempts=1),
            solver(S2, 2, merged=1, passed=2, decided=2, submissions=2, late=1, clawedBack=1)])
        self.assertEqual(rows(b, "reporters"), [
            reporter(R, 1, finderFees=15 * M, opened=2, registered=2, rewarded=1),
            reporter(R2, 2, registered=2, refused=1, junk=1)])
        self.assertEqual(rows(b, "funders"), [
            funder(F1, 1, pledged=120 * M, bounties=2, solved=1, refunds=1, refunded=29 * M),  # COIN2's 5 not counted
            funder(F2, 2, pledged=50 * M, bounties=1, solved=1, refunds=1, refunded=14 * M + 1)])
        self.assertEqual(rows(b, "validators"), [
            validator(J2, 1, counted=3, reports=3),
            validator(J1, 2, counted=2, reports=2, withdrawn=250_000),
            validator(J3, 3, counted=2, reports=2, withdrawn=100_000)])  # withdrawn by its payee, P3
        self.assertEqual(set(b["notDerivable"]["validators"]),
                         {"draws", "agreement", "revealRate", "feesEarned", "slashes"})

    def test_the_table_exactly(self):
        self.maxDiff = None
        self.assertEqual("\n".join(leaderboard.render(board())), TABLE.strip("\n"))

    def test_last_week(self):
        """Back 7 days from the latest block's time (day 40): from day 33 on, bounty 2 and issues 3 and 4 only."""
        b = board("week")
        self.assertEqual(b["since"], T0 + 33 * DAY)
        self.assertEqual(rows(b, "solvers"), [
            solver(S2, 1, merged=1, passed=1, decided=1, submissions=1, clawedBack=1),
            solver(S1, 2, decided=1, submissions=1)])
        self.assertEqual(rows(b, "reporters"), [
            reporter(R, 1, opened=1, registered=1), reporter(R2, 2, registered=2, refused=1, junk=1)])
        self.assertEqual(rows(b, "funders"), [funder(F1, 1, pledged=20 * M, bounties=1)])
        self.assertEqual(rows(b, "validators"), [validator(J2, 1, counted=1, reports=1),
                                                 validator(J3, 2, counted=1, reports=1)])

    def test_last_month_and_one_role(self):
        b = board("month", role="validator")
        self.assertEqual(b["since"], T0 + 10 * DAY)
        self.assertNotIn("solvers", b)
        # from day 10: bounty 2's reports, and the withdrawals on day 30; J3 ties J2 on counted, and has withdrawn more
        self.assertEqual(rows(b, "validators"), [validator(J3, 1, counted=1, reports=1, withdrawn=100_000),
                                                 validator(J2, 2, counted=1, reports=1),
                                                 validator(J1, 3, withdrawn=250_000)])

    def test_only_some_bounties(self):
        """A run's own bounties on a shared devnet: the facts about them only; withdrawals, tied to none, left out."""
        b = board(bounties=[1])
        self.assertEqual(rows(b, "solvers"), [
            solver(S1, 1, earned=90 * M, merged=1, won=1, passed=1, decided=1, submissions=1, attempts=1),
            solver(S2, 2, passed=1, decided=1, submissions=1, late=1)])
        self.assertEqual(rows(b, "reporters"), [reporter(R, 1, finderFees=15 * M, opened=1, registered=1, rewarded=1)])
        self.assertEqual(rows(b, "funders"), [
            funder(F1, 1, pledged=100 * M, bounties=1, solved=1, refunds=1, refunded=29 * M),
            funder(F2, 2, pledged=50 * M, bounties=1, solved=1, refunds=1, refunded=14 * M + 1)])
        self.assertEqual(rows(b, "validators"), [validator(J1, 1, counted=2, reports=2),
                                                 validator(J2, 2, counted=2, reports=2),
                                                 validator(J3, 3, counted=1, reports=1)])

    def test_the_settlement_alone_tells_the_check_refund_by_the_meter(self):
        """No finder's fee (inflated) and no registration refund: the winner's last payment at settlement, equal to
        what the meter charged its passing fix, is the check refund, not an instalment."""
        settle = [h for h in HISTORY if h[0] < 22] + [
            (23, 18, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [PAID]),
            (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [90 * M]),
            (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [300_000])]
        b = board(history=settle)
        self.assertEqual(b["solvers"][0]["earned"], 90 * M)
        self.assertEqual(b["reporters"][0]["finderFees"], 0)

    def test_a_lone_reporter_payment_is_the_refund_when_it_equals_the_registration(self):
        settle = [h for h in HISTORY if h[0] < 23] + [
            (23, 18, RACE, "StateChanged(uint256,uint8)", [1], ["uint8"], [PAID]),
            (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, S1], ["uint256"], [60 * M]),
            (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, R], ["uint256"], [M])]
        self.assertEqual(board(history=settle)["reporters"][0]["finderFees"], 0)
        settle[-1] = (23, 18, RACE, "Paid(uint256,address,address,uint256)", [1, COIN, R], ["uint256"], [15 * M])
        self.assertEqual(board(history=settle)["reporters"][0]["finderFees"], 15 * M)

    def test_addresses_only(self):
        """Nothing in the board names a person: every row holds an address and numbers."""
        text = json.dumps(board(), default=str)
        for r in leaderboard.ROLES:
            for x in board()[r]:
                self.assertEqual(set(x) - {"address", "rank", "passRate"}, set(leaderboard.METRICS[r]))
        self.assertNotIn("name", text)

    def test_block_times_are_read_once_and_only_for_a_period(self):
        rpc = FakeRpc()
        race = Race(rpc, {"race": RACE, "coin": COIN, "quoter": "0x" + "00" * 20, "meter": METER, "block": 0})
        race.board_events()
        self.assertEqual(rpc.block_reads, 0)
        race.board_events(with_time=True)
        self.assertEqual(rpc.block_reads, len({h[0] for h in HISTORY}))

    def test_bad_options(self):
        with self.assertRaises(ValueError):
            leaderboard.compute([], COIN, "year", 0)
        with self.assertRaises(ValueError):
            leaderboard.compute([], COIN, "week")  # a period needs the chain's time
        with self.assertRaises(ValueError):
            leaderboard.role_name("judges")

    def test_the_cli(self):
        p = cli.parser()
        a = p.parse_args(["leaderboard", "--period", "month", "--role", "funders", "--bounties", "3,4"])
        self.assertIs(a.fn, cli.cmd_leaderboard)
        self.assertEqual((a.period, a.role, a.bounties), ("month", "funders", "3,4"))
        ctx = mock.Mock(version=2)
        ctx.race = Race(FakeRpc(), {"race": RACE, "coin": COIN, "quoter": "0x" + "00" * 20, "meter": METER,
                                    "block": 0})
        data, lines = cli.cmd_leaderboard(ctx, p.parse_args(["leaderboard", "--bounties", "1"]))
        self.assertEqual(data["block"], 50)
        self.assertEqual(data["bounties"], [1])
        self.assertIn("only bounties 1", lines[1])
        ctx.version = 1
        with self.assertRaises(cli.Fail):
            cli.cmd_leaderboard(ctx, p.parse_args(["leaderboard"]))


TABLE = f"""
leaderboard: all time, from the contracts' events only; amounts in coin {COIN}; addresses only

solvers (2)
  # address                                        earned  merged  won  passed  decided  submitted  attempts  late  clawed back  pass rate
  1 {S1}  90.000000       1    1       1        2          2         1     0            0     50.0 %
  2 {S2}   0.000000       1    0       2        2          2         0     1            1    100.0 %

reporters (2)
  # address                                     finder's fees  opened  registered  rewarded  refused  junk
  1 {R}      15.000000       2           2         1        0     0
  2 {R2}       0.000000       0           2         0        1     1

funders (2)
  # address                                        pledged  bounties  solved  refunds   refunded
  1 {F1}  120.000000         2       1        1  29.000000
  2 {F2}   50.000000         1       1        1  14.000001

validators (3)
  # address                                     counted  reports  withdrawn
  1 {J2}        3        3   0.000000
  2 {J1}        2        2   0.250000
  3 {J3}        2        2   0.100000
    not shown, draws: {leaderboard.NOT_DERIVABLE['validators']['draws']}
    not shown, agreement: {leaderboard.NOT_DERIVABLE['validators']['agreement']}
    not shown, revealRate: {leaderboard.NOT_DERIVABLE['validators']['revealRate']}
    not shown, feesEarned: {leaderboard.NOT_DERIVABLE['validators']['feesEarned']}
    not shown, slashes: {leaderboard.NOT_DERIVABLE['validators']['slashes']}
"""


# ---------- the integration suite's check: the same bounties read from the views ----------

class FakeViews:
    """RaceV2's and the meter's views as they stand at the end of HISTORY, for bounties 1 and 2."""

    BOUNTIES = {1: {"state": "Paid", "issue": 1, "epoch": 1, "inflated": False},
                2: {"state": "Open", "issue": 2, "epoch": 1, "inflated": False}}
    ISSUES = {1: {"reporter": R, "state": "Rewarded"}, 2: {"reporter": R, "state": "Posted"}}
    AWARDS = {(1, 1): {"winner": S1, "closed": False}, (2, 1): {"winner": S2, "closed": True}}
    SUBS = {1: [(1, S1, "Pass"), (2, S2, "Pass")], 2: [(3, S2, "Pass"), (4, S1, "Fail")]}
    REPORTS = {1: [J1, J2, J3], 2: [J1, J2], 3: [J2, J3], 4: []}
    PLEDGED = {(1, F1): 100 * M, (1, F2): 50 * M, (2, F1): 20 * M}

    def config(self):
        return {"finderFeeBps": 1765}

    def bounty(self, b):
        return self.BOUNTIES[b]

    def issue(self, i):
        return self.ISSUES[i]

    def award(self, b, e):
        return self.AWARDS[(b, e)]

    def instalments_paid(self, b, e):
        return {(1, 1): 90 * M}.get((b, e), 0)

    def price_of(self, b, e):
        return 84_985_836  # its finder's fee, 17.65 % rounded down, is the 15 paid at settlement

    def submissions_of(self, b):
        return [s for s, _, _ in self.SUBS[b]]

    def submission(self, s):
        solver, outcome = next((x[1], x[2]) for subs in self.SUBS.values() for x in subs if x[0] == s)
        return {"solver": solver, "outcome": outcome}

    def reports(self, s):
        return [{"judge": j} for j in self.REPORTS[s]]

    def pledged(self, b, who):
        return self.PLEDGED.get((b, who), 0)

    def refunded_to(self, b, who):
        return b == 1


class TestTheSuitesCheck(unittest.TestCase):
    def test_events_and_views_agree(self):
        from targets import board_expected, check_board

        want = board_expected(FakeViews(), [1, 2], [F1, F2], late={S2: 1}, attempts={S1: 1})
        self.assertEqual(check_board("fixed history", board(bounties=[1, 2]), want), [])

    def test_a_difference_is_named(self):
        from targets import board_expected, check_board

        want = board_expected(FakeViews(), [1, 2], [F1, F2], late={S2: 1})  # no attempt expected
        got = board(bounties=[1, 2])
        self.assertEqual(check_board("x", got, want), [f"x: solvers {S1}: attempts 1, expected 0"])
        got["validators"].append({"address": "0x" + "77" * 20, "counted": 1, "reports": 1, "withdrawn": 0})
        self.assertIn("unexpected", check_board("x", got, want)[-1])
        del got["funders"][0]
        self.assertTrue(any("missing" in p for p in check_board("x", got, want)))


class TestTheAwsTarget(unittest.TestCase):
    """--target aws's two #151 steps (tests/integration/aws.py), without AWS: the owner runs the real thing."""

    def run_(self):
        import aws

        r = aws.AwsRun.__new__(aws.AwsRun)
        r.problems, r.late = [], {S2: 1}
        r.addr = {"funder": F1}
        return r

    def test_the_leaderboard_over_the_runs_bounties(self):
        r = self.run_()
        r.bounties = [("1", 1, 5), ("5", 2, 6)]
        r.race = FakeViews()
        asked = []
        r.ctl = lambda *argv, **kw: asked.append(argv) or board(bounties=[1, 2])
        with mock.patch("aws.say"):
            r.leaderboard()
        self.assertEqual(asked, [("leaderboard", "--bounties", "1,2")])
        # the fixed history has an attempt and a second funder the run wouldn't have: both are named
        f2 = {"pledged": 50 * M, "bounties": 1, "solved": 1, "refunds": 1, "refunded": 14 * M + 1}
        self.assertEqual(r.problems, [f"leaderboard: solvers {S1}: attempts 1, expected 0",
                                      f"leaderboard: funders {F2} unexpected ({f2})"])

    def test_the_issue_closed_on_payout(self):
        tx = "0x" + "ee" * 32
        r = self.run_()
        r.race = mock.Mock()
        r.race.payout.return_value = {"tx": tx, "block": 9}
        replies = {"/issues/5": {"state": "closed"},
                   "/issues/5/comments": [{"body": logic.bounty_comment(RACE, 1, 1)},
                                          {"body": logic.paid_comment(RACE, 1, tx, 9, 7193)}]}
        r.forge = mock.Mock()
        r.forge.api.side_effect = lambda method, path, body=None: replies[path]
        with mock.patch("aws.say"):
            self.assertTrue(r.closed_on_payout(1, 5))
            replies["/issues/5"] = {"state": "open"}
            self.assertFalse(r.closed_on_payout(1, 5))
        pay = {"tx": tx, "block": 9}
        self.assertEqual(r.problems, [f"scenario 1: issue #5 is open after bounty 1 was paid ({pay})"])


# ---------- closing a paid bounty's issue (the bot's step) ----------

class FakeRace:
    def __init__(self, paid=True):
        self.address, self._paid = RACE, paid

    def payout(self, b):
        return {"tx": "0x" + "ee" * 32, "block": 23} if self._paid else None

    def chain_id(self):
        return 7193


class TestCloseOnPayout(unittest.TestCase):
    def ctx(self, gh, paid=True, explorer=""):
        ctx = mock.Mock(version=2, config={"explorer": explorer} if explorer else {})
        ctx.race = FakeRace(paid)
        ctx.repo = lambda name: GitHubRepo(name, token=gh.token, api=gh.url, sleep=lambda s: None)
        return ctx

    def linked_issue(self, gh, race=RACE, label=True):
        n = gh.add_issue("o/r", "bug", "Reporter wallet: " + R, labels=["bounty"] if label else [])
        gh.repos["o/r"]["comments"][n] = [{"id": 1, "body": logic.bounty_comment(race, 1, 1), "user": {"login": "b"}}]
        return n

    def test_closes_with_the_payout_once(self):
        with FakeGitHub() as gh:
            n = self.linked_issue(gh)
            ctx = self.ctx(gh, explorer="https://explorer.example.invalid/tx/{tx}")
            out = cli.close_paid(ctx, "o/r", n)
            self.assertTrue(out["closed"] and out["commented"] and out["paid"])
            item = gh.repos["o/r"]["items"][n]
            self.assertEqual((item["state"], item["state_reason"]), ("closed", "completed"))
            body = gh.repos["o/r"]["comments"][n][-1]["body"]
            self.assertIn("[`0x" + "ee" * 32 + "`](https://explorer.example.invalid/tx/0x" + "ee" * 32 + ")", body)
            self.assertEqual(logic.paid([{"body": body}]), (RACE, 1, "0x" + "ee" * 32))
            again = cli.close_paid(ctx, "o/r", n)  # idempotent: no second comment
            self.assertFalse(again["commented"])
            self.assertEqual(len(gh.repos["o/r"]["comments"][n]), 2)

    def test_without_an_explorer_the_hash_and_where_to_read_it(self):
        body = logic.paid_comment(RACE, 3, "0x" + "ab" * 32, 9, 7193)
        self.assertIn("`0x" + "ab" * 32 + "`", body)
        self.assertIn("chain 7193, block 9", body)
        self.assertIn("eth_getTransactionReceipt", body)

    def test_not_paid_or_not_this_race_stays_open(self):
        with FakeGitHub() as gh:
            n = self.linked_issue(gh)
            out = cli.close_paid(self.ctx(gh, paid=False), "o/r", n)
            self.assertFalse(out["closed"] or out["commented"])
            other = self.linked_issue(gh, race="0x" + "99" * 20)
            self.assertFalse(cli.close_paid(self.ctx(gh), "o/r", other)["closed"])
            self.assertEqual(gh.repos["o/r"]["items"][n]["state"], "open")

    def test_the_watcher_pass_closes_every_paid_bounty_issue(self):
        with FakeGitHub() as gh:
            a, b = self.linked_issue(gh), self.linked_issue(gh)
            unlabelled = self.linked_issue(gh, label=False)
            results, lines = cli.cmd_close(self.ctx(gh), cli.parser().parse_args(["bot", "close", "--repo", "o/r"]))
            self.assertEqual(sorted(r["issue"] for r in results if r["closed"]), [a, b])
            self.assertEqual(gh.repos["o/r"]["items"][unlabelled]["state"], "open")

    def test_settle_closes_once_paid_and_wants_both_options(self):
        p = cli.parser()
        ctx = mock.Mock(version=2)
        with self.assertRaises(cli.Fail):
            cli.cmd_settle(ctx, p.parse_args(["bot", "settle", "--bounty", "1", "--repo", "o/r"]))
        with FakeGitHub() as gh:
            n = self.linked_issue(gh)
            ctx = self.ctx(gh)
            ctx.race.bounty = mock.Mock(side_effect=[{"state": "Merged"}, {"state": "Paid"}])
            ctx.race.settle = mock.Mock()
            data, lines = cli.cmd_settle(ctx, p.parse_args(["bot", "settle", "--bounty", "1", "--repo", "o/r",
                                                            "--issue", str(n)]))
            self.assertTrue(data["settled"] and data["issue"]["closed"])
            self.assertIn(f"o/r#{n} closed", lines[-1])

    def test_forgejo_closes_by_patch(self):
        client = mock.Mock()
        client.api.return_value = {"number": 7, "state": "closed", "labels": [], "user": {"login": "x"}}
        out = ForgejoRepo(client, "example-org/pof-sandbox").close(7)
        client.api.assert_called_once_with("PATCH", "/repos/example-org/pof-sandbox/issues/7",
                                           {"state": "closed"})
        self.assertEqual(out["state"], "closed")


if __name__ == "__main__":
    unittest.main()
