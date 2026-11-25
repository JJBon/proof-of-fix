"""pofctl's v3.1 polish (proof-of-fix#251, openspec change proof-of-fix-251-v31-polish, tasks 4.1-4.6, and pofctl's
share of 2.9 and 2.10): `draw` (VP11), `status` without the password and with the ETH balance (VP11), `issue register`
with the whole id and `--title` (VP11), the approval race (VP17 S1), transaction hashes (S2), the reporter's view
`issue show` (S3), `Rpc`'s default retries (VP19) and no RPC key in pofctl's errors (VP20). On a fake chain: no
network, no Radicle node (tests/fake_rad.py stands in for `rad`)."""

from __future__ import annotations

import inspect
import io
import json
import os
import sys
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from oracle import crypto, v2, v3  # noqa: E402
from oracle.rpc import Reverted, Rpc, Wallet  # noqa: E402
from pofctl import cli, keystore, v3cli  # noqa: E402
from test_pofctl_v3 import (BOOK, C, CAST_KEY, CAST_KEYSTORE, COIN, FAUCET, HEAD, PANELS, RACE,  # noqa: E402
                            FakeRpc, Records, _word, run_main)

FAKE_RAD = Path(__file__).resolve().parent / "fake_rad.py"
REPORTER = crypto.address(CAST_KEY)
BASE = HEAD  # Heads.head, the fixes' base


def _topic(sig: str) -> str:
    return "0x" + crypto.keccak256(sig.encode()).hex()


def _row(fields: list, **kw) -> tuple:
    return tuple(kw.get(f, 0) for f in fields)


class Chain(FakeRpc):
    """FakeRpc with state: Panels' verdicts and panels, RaceV3's issues and submissions, the registry's epoch, an
    allowance that can lag behind its approval, and the transactions (`send`, patched in for Wallet.send), each mined
    with a hash and a block."""

    def __init__(self, chain_id: int = 31337, lag: int = 0, refuse: dict | None = None, **over) -> None:
        super().__init__(chain_id)
        self.verdicts: dict = {}
        self.subs: dict = {}
        self.issues: dict = {}
        self.panels: dict = {}
        self.epoch, self.allowed, self.lag, self.refuse = 5, 0, lag, dict(refuse or {})
        self.sent: list = []
        self.stay_waiting, self.revert = False, {}
        self.locked, self.attempting = False, 0  # the bounty's, as `attempt` leaves them (`bounty` below)
        self.answers.update({
            "submission": self._submission, "issue": self._issue, "panel": self._panel,
            "judges": lambda to, pid: [self.panels.get(pid, {}).get("judges", [])],
            "epoch": lambda to: [self.epoch], "allowance": self._allowance,
            "bounty": lambda to, b: [(1, v3.OPEN, 0, self.locked, 5000 if self.locked else 0, 0, self.attempting, 0,
                                      0, 0, 0, 0)],
            "lockedPrice": lambda to, b: [5 * C], "claimOf": lambda to, s: [(RACE, 0)],
            "held": lambda to, *a: [10 * C], "nextClaim": lambda to, who: [0], "faucet": lambda to: [FAUCET],
            "CLAIM_AMOUNT": lambda to: [20 * C], "CLAIM_INTERVAL": lambda to: [7200],
        })
        self.answers.update(over)

    # ----- views -----

    def _allowance(self, to, owner, spender):
        if self.lag:
            self.lag -= 1
            return [0]
        return [self.allowed]

    def _submission(self, to, s):
        if to.lower() == PANELS:
            return [_row(v3.PANELS_SUBMISSION_FIELDS, **self.verdicts.get(s, {}))]
        return [_row(v3.RACE_SUBMISSION_FIELDS[:-1], **{"solver": RACE, **self.subs.get(s, {})})]

    def _issue(self, to, i):
        return [_row(v3.RACE_ISSUE_FIELDS, **{"reporter": "0x" + "00" * 20, **self.issues.get(i, {})})]

    def _panel(self, to, pid):
        return [_row(v3.PANEL_FIELDS, **{k: v for k, v in self.panels.get(pid, {}).items() if k != "judges"})]

    # ----- transactions -----

    def send(self, to, sig, *args, **kw):
        name = sig.split("(")[0]
        if name in self.revert:
            self.sent.append((to, sig, args))
            raise Reverted(self.revert[name], "0x")
        if self.refuse.get(name):
            self.refuse[name] -= 1
            self.sent.append((to, sig, args))
            raise Reverted("ERC20InsufficientAllowance", "0x" + v3cli.ALLOWANCE_SHORT + "00" * 96)
        self.sent.append((to, sig, args))
        n = len(self.sent)
        logs = []
        if name == "approve":
            self.allowed = 2**256 - 1
        elif name == "register":
            self.issues[1] = {"reporter": REPORTER, "check": 2, "state": 1, "stake": 5 * C}
            self.verdicts[2] = {"status": v3.SEALED, "seedBlock": self.height + 1}
            logs = [{"topics": [_topic(v3.REGISTERED), "0x%064x" % 1, _word(REPORTER)], "data": "0x%064x" % 2}]
        elif name == "commit":
            logs = [{"topics": [_topic(v3.COMMITTED), "0x%064x" % args[0], "0x%064x" % 9], "data": "0x"}]
            self.subs[9] = {"bounty": args[0], "deposit": 1_230_000, "solver": REPORTER}
        elif name == "openBounty":
            logs = [{"topics": [_topic("BountyOpened(uint256,uint256)"), "0x%064x" % 3, "0x%064x" % args[0]],
                     "data": "0x"}]
        elif name == "attempt":
            self.locked, self.attempting = True, self.attempting + 1
        elif name == "draw" and self.stay_waiting:  # too few validators: it waits again
            self.verdicts[args[0]] = {**self.verdicts.get(args[0], {}), "retryAt": 20_000}
        elif name == "draw":
            self.verdicts[args[0]] = {**self.verdicts.get(args[0], {}), "status": v3.JUDGING, "pid": 4, "k": 1}
        return {"transactionHash": "0x%064x" % (0xabc000 + n), "blockNumber": hex(1000 + n), "status": "0x1",
                "logs": logs}


class Case(Records):
    def setUp(self):
        super().setUp()
        os.environ["DEVNET_KEYS"] = "insecure-local"

    def run_cmd(self, chain: Chain, *argv, record=None):
        """(data, lines) of one command on the fake chain, its sends through `chain.send`."""
        a = cli.parser().parse_args(["--record", str(record or self.v3), *argv])
        with mock.patch.object(cli, "Rpc", return_value=chain):
            ctx = cli.Ctx(a)
        with mock.patch.object(Wallet, "send", side_effect=chain.send):
            return a.fn3(ctx, a)

    def refused(self, chain: Chain, *argv) -> str:
        with self.assertRaises(cli.Fail) as e:
            self.run_cmd(chain, *argv)
        return str(e.exception)

    def sigs(self, chain: Chain) -> list:
        return [s[1].split("(")[0] for s in chain.sent]


# ---------- 4.1: draw ----------

class TestDraw(Case):
    def test_sealed_before_its_seed_block_sends_nothing(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.SEALED, "seedBlock": 102}
        msg = self.refused(chain, "draw", "7")
        self.assertIn("check 7 is sealed until its seed block 102 (now block 100): it may be drawn in 3 block(s)", msg)
        self.assertIn("Nothing was sent", msg)
        self.assertEqual(chain.sent, [])

    def test_sealed_past_its_seed_block_draws_then_signals(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.SEALED, "seedBlock": 99}
        data, lines = self.run_cmd(chain, "draw", "7")
        self.assertEqual([(s[0].lower(), s[1], s[2]) for s in chain.sent],
                         [(PANELS, "draw(uint256)", (7,)), (RACE, "signal(uint256)", (7,))])
        self.assertEqual((data["before"], data["status"], data["panel"], data["k"]), ("Sealed", "Judging", 4, 1))
        self.assertEqual([t["what"] for t in data["txs"]], ["draw", "signal"])
        self.assertEqual((data["tx"], data["block"]), ("0x%064x" % 0xabc002, 1002))
        text = "\n".join(lines)
        self.assertIn("drew check 7 (sealed, past its seed block 99)", text)
        self.assertIn(f"tx {'0x%064x' % 0xabc001} in block 1001 (draw)", text)
        self.assertIn("check 7 is judging: panel 4, k = 1", text)

    def test_waiting_with_nothing_changed_says_when(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 6, "retryAt": 10_000 + 3600}
        msg = self.refused(chain, "draw", "7")
        self.assertIn("check 7 is waiting for validators who can judge it: it is drawn again once the registry "
                      "changes, or at 1970-01-01 03:46:40 UTC (in 1 h 00 min). Nothing was sent.", msg)
        self.assertEqual(chain.sent, [])

    def test_waiting_with_the_registry_changed_draws(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 5, "retryAt": 10_000 + 3600}  # epoch 5 + 1 != 5
        data, lines = self.run_cmd(chain, "draw", "7")
        self.assertEqual(self.sigs(chain), ["signal", "draw", "signal"])  # VP24: the wait, the draw, the panel
        text = "\n".join(lines)
        self.assertIn("signalled check 7 to FeesV3's queue (its wait)", lines[0])
        self.assertIn("drew check 7 (waiting, and the registry changed)", text)
        self.assertIn("signalled check 7 to FeesV3's queue (its panel)", text)
        self.assertEqual([t["what"] for t in data["txs"]], ["signal", "draw", "signal"])

    def test_waiting_past_its_retry_time_draws(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 6, "retryAt": 9_000}
        _, lines = self.run_cmd(chain, "draw", "7")
        self.assertEqual(self.sigs(chain), ["signal", "draw", "signal"])
        self.assertIn("waiting, past its retry time", "\n".join(lines))

    def test_waiting_and_still_waiting_after_the_draw_signals_once(self):
        """VP24: a draw that finds too few validators leaves the check waiting; its wait was signalled already."""
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 6, "retryAt": 9_000}
        chain.stay_waiting = True
        data, lines = self.run_cmd(chain, "draw", "7")
        self.assertEqual(self.sigs(chain), ["signal", "draw"])
        self.assertEqual(data["status"], "Waiting")
        self.assertIn("check 7 is waiting: too few validators could judge it now", "\n".join(lines))

    def test_a_refused_draw_after_the_wait_signal_says_what_was_sent(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 6, "retryAt": 9_000}
        chain.revert = {"draw": "NotReady()"}
        msg = self.refused(chain, "draw", "7")
        self.assertIn("draw reverted", msg)
        self.assertIn(f"Only the wait's signal was sent ({'0x%064x' % 0xabc001}, block 1001)", msg)
        self.assertEqual(self.sigs(chain), ["signal", "draw"])

    def test_a_failed_signal_doesn_t_stop_the_draw(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.WAITING, "waitEpoch": 6, "retryAt": 9_000}
        chain.revert = {"signal": "Refused()"}
        data, lines = self.run_cmd(chain, "draw", "7")
        self.assertEqual(self.sigs(chain), ["signal", "draw", "signal"])
        self.assertNotIn("txs", data)  # one transaction mined: the draw's
        self.assertIn("drew check 7", lines[1])
        self.assertIn("the signal of its wait wasn't sent", lines[0])

    def test_drawn_already_or_no_check(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.JUDGING, "pid": 4, "k": 3}
        msg = self.refused(chain, "draw", "7")
        self.assertIn("check 7 is judging (panel 4, k = 3): it was drawn already", msg)
        self.assertIn("there is no check 8 on Panels", self.refused(chain, "draw", "8"))
        self.assertEqual(chain.sent, [])

    def test_draw_selects_v3_and_the_reporter_key_by_default(self):
        a = cli.parser().parse_args(["draw", "7"])
        self.assertEqual((a.check, a.role, a.fn3), (7, "reporter", v3cli.cmd_draw))
        self.assertIn("draw", v3cli.V3_ONLY)


# ---------- 4.2: status without the password, with ETH ----------

class TestStatusAddress(Case):
    def setUp(self):
        super().setUp()
        del os.environ["DEVNET_KEYS"]
        self.ks = self.dir / "key.json"
        self.ks.write_text(json.dumps(CAST_KEYSTORE))

    def status(self, chain, *argv, config=None):
        cfg = self.dir / "pofctl.json"
        cfg.write_text(json.dumps(config or {}))
        return self.run_cmd(chain, "--config", str(cfg), "--keystore", str(self.ks), "status", *argv)

    def run_cmd(self, chain, *argv, record=None):
        argv = list(argv)
        a = cli.parser().parse_args(["--record", str(record or self.v3), *argv])
        with mock.patch.object(cli, "Rpc", return_value=chain):
            ctx = cli.Ctx(a)
        with mock.patch.object(Wallet, "send", side_effect=chain.send):
            return a.fn3(ctx, a)

    def test_the_configs_address_asks_nothing_and_shows_both_balances(self):
        chain = Chain(11155111)
        chain.eth = 4 * 10**15
        with mock.patch.object(keystore, "load", side_effect=AssertionError("the password was asked")):
            data, lines = self.status(chain, config={"address": REPORTER.lower()})
        text = "\n".join(lines)
        self.assertEqual((data["solver"], data["eth"], data["wallet"]), (REPORTER, 4 * 10**15, 500 * C))
        self.assertIn("  ETH            0.004000 for gas (about 0.01 Sepolia ETH covers every step)", text)
        self.assertIn("  wallet         500.000000, credit in the race", text)

    def test_the_keystores_address_field_asks_nothing(self):
        self.ks.write_text(json.dumps({**CAST_KEYSTORE, "address": REPORTER[2:].lower()}))
        chain = Chain(11155111)
        with mock.patch.object(keystore, "load", side_effect=AssertionError("the password was asked")):
            data, lines = self.status(chain)
        self.assertEqual(data["solver"], REPORTER)
        self.assertIn("  ETH            0.020000 for gas", lines)  # enough: no hint

    def test_without_an_address_the_keystore_is_decrypted_once(self):
        chain = Chain(11155111)
        with mock.patch.object(keystore, "load", return_value=CAST_KEY) as load:
            data, _ = self.status(chain)
        self.assertEqual((data["solver"], load.call_count), (REPORTER, 1))

    def test_a_signing_command_still_asks_once(self):
        chain = Chain(11155111)
        cfg = self.dir / "pofctl.json"
        cfg.write_text(json.dumps({"address": REPORTER}))
        with mock.patch.object(keystore, "load", return_value=CAST_KEY) as load:
            data, _ = self.run_cmd(chain, "--config", str(cfg), "--keystore", str(self.ks), "faucet")
        self.assertEqual((load.call_count, data["account"], [s[1] for s in chain.sent]), (1, REPORTER, ["claim()"]))

    def test_status_lists_the_reporters_registrations(self):
        chain = Chain(11155111)
        chain.issues[1] = {"reporter": REPORTER, "check": 2, "state": 1}
        chain.issues[3] = {"reporter": REPORTER, "check": 6, "state": 1}
        chain.verdicts[2] = {"status": v3.HELD, "pass": True, "k": 1, "pid": 4}
        chain.verdicts[6] = {"status": v3.SEALED, "seedBlock": 101}
        topic = _topic(v3.REGISTERED)
        chain.log_rows = [
            {"address": RACE, "topics": [topic, "0x%064x" % 1, _word(REPORTER)], "data": "0x%064x" % 2},
            {"address": RACE, "topics": [topic, "0x%064x" % 2, _word(BOOK)], "data": "0x%064x" % 5},  # not its
            {"address": RACE, "topics": [topic, "0x%064x" % 3, _word(REPORTER)], "data": "0x%064x" % 6},
        ]
        data, lines = self.status(chain, config={"address": REPORTER})
        self.assertEqual([(r["issue"], r["check"], r["status"]) for r in data["registrations"]],
                         [(1, 2, "Held"), (3, 6, "Sealed")])
        text = "\n".join(lines)
        self.assertIn(f"reporter {REPORTER}: 2 registration(s)", text)
        self.assertIn("  issue 1  check 2: held, passed, issue posted", text)
        self.assertIn("  issue 3  check 6: sealed, issue posted", text)
        self.assertIn("  each one's progress: pofctl --v3 issue show --issue <N>", text)


# ---------- 4.3: issue register's id, --title ----------

class TestRegister(Case):
    RID = "rad:z4PofctrTest"  # the record's: keccak256 of it is the fake chain's repo()

    def setUp(self):
        super().setUp()
        self.home = self.dir / "rad"
        self.home.mkdir()
        os.environ["RAD_HOME"] = str(self.home)
        self.rad = self.dir / "rad-exec"  # the --rad-exec prefix: drops the `rad` and runs the stand-in
        self.rad.write_text(f'#!/bin/sh\nshift\nexec {sys.executable} {FAKE_RAD} "$@"\n')
        self.rad.chmod(0o755)

    def test_the_whole_id_on_its_own_line_and_in_the_json(self):
        chain = Chain()
        iid = "ab" * 20
        data, lines = self.run_cmd(chain, "issue", "register", "--rad-issue", iid)
        self.assertIn(f"radicle issue {iid}", lines)
        self.assertEqual((data["radIssue"], data["issue"], data["check"]), (iid, 1, 2))
        self.assertIn("if no validator draws it within 10 minutes: pofctl --v3 draw 2", lines)
        self.assertIn("its progress: pofctl --v3 issue show --issue 1", lines)

    def test_title_opens_the_radicle_issue_checks_it_and_registers(self):
        chain = Chain()
        data, lines = self.run_cmd(chain, "issue", "register", "--title", "median() of an empty list raises",
                                   "--description", "median([]) raises IndexError.", "--rad-exec", str(self.rad),
                                   "--comment")
        cobs = list((self.home / "cobs" / "xyz.radicle.issue").glob("*.json"))
        self.assertEqual(len(cobs), 1)
        iid = cobs[0].stem
        self.assertEqual((data["radIssue"], data["opened"], data["commented"]), (iid, True, True))
        self.assertEqual(self.sigs(chain), ["approve", "register"])
        self.assertEqual(lines[0], f"opened the Radicle issue {iid} ('median() of an empty list raises') and read it "
                                   f"back")
        self.assertIn(f"radicle issue {iid}", lines)
        comment = json.loads((self.home / "issue-comments.jsonl").read_text())
        self.assertEqual((comment["issue"], comment["repo"]), (iid, self.RID))
        self.assertIn("Registration: 1", comment["body"])

    def test_a_title_mismatch_is_refused_before_any_transaction(self):
        (self.home / "show-title").write_text("another issue")
        chain = Chain()
        msg = self.refused(chain, "issue", "register", "--title", "median() of an empty list raises",
                           "--description", "d", "--rad-exec", str(self.rad))
        self.assertIn("has the title 'another issue', not 'median() of an empty list raises'", msg)
        self.assertIn("Nothing was sent", msg)
        self.assertEqual(chain.sent, [])

    def test_a_short_balance_opens_no_radicle_issue(self):
        chain = Chain(balanceOf=lambda to, *a: [C])
        msg = self.refused(chain, "issue", "register", "--title", "t", "--description", "d", "--rad-exec",
                           str(self.rad))
        self.assertIn("Nothing was sent", msg)
        self.assertFalse((self.home / "cobs").exists())

    def test_one_of_rad_issue_or_title(self):
        chain = Chain()
        self.assertIn("one of the two", self.refused(chain, "issue", "register"))
        self.assertIn("one of the two", self.refused(chain, "issue", "register", "--rad-issue", "ab" * 20,
                                                     "--title", "t"))

    def test_the_box_parser_takes_the_issue_row_only(self):
        import subprocess

        out = subprocess.run([sys.executable, str(FAKE_RAD), "issue", "open", "--title", "x", "--description",
                              "a description that names " + "cd" * 20], capture_output=True, text=True,
                             env={**os.environ}, check=True).stdout
        self.assertTrue(out.startswith("╭"))
        iid = v3cli.rad_issue_id(out)
        self.assertEqual(len(iid), 40)
        self.assertNotEqual(iid, "cd" * 20)
        self.assertEqual(v3cli.rad_issue_id("✓ done"), "")

    # Radicle 1.10.3's own output with no terminal (`docker exec -i`), captured from the real binary (task 8.3): no
    # divider before the description, an empty row instead; `show` adds each comment after a divider.
    REAL_OPEN = ("╭──────────────────────────────────────────────────────╮\n"
                 "│ Title   No mode()                                    │\n"
                 "│ Issue   c627325f440e51543c4607c94a877038a6f1a63e     │\n"
                 "│ Author  probe (you)                                  │\n"
                 "│ Status  open                                         │\n"
                 "│                                                      │\n"
                 "│ stats has no mode(): mode([1, 2, 2, 3]) should be 2. │\n"
                 "│ second line                                          │\n"
                 "╰──────────────────────────────────────────────────────╯\n")
    REAL_SHOW = ("╭──────────────────────────────────────────────────╮\n"
                 "│ Title   Third                                    │\n"
                 "│ Issue   a5dac6205af2d57896d639c30271dac5916a25c6 │\n"
                 "│ Author  probe (you)                              │\n"
                 "│ Status  open                                     │\n"
                 "│                                                  │\n"
                 "│ body three                                       │\n"
                 "├──────────────────────────────────────────────────┤\n"
                 "│ probe (you) now 05c154b                          │\n"
                 "│                                                  │\n"
                 "│ Title   a comment that looks like a row          │\n"
                 "╰──────────────────────────────────────────────────╯\n")

    def test_the_parser_reads_radicle_1_10_3s_real_boxes(self):
        self.assertEqual(v3cli.rad_issue_id(self.REAL_OPEN), "c627325f440e51543c4607c94a877038a6f1a63e")
        shown = v3cli.rad_box(self.REAL_SHOW)
        self.assertEqual((shown["Title"], shown["Issue"], shown["Status"]),
                         ("Third", "a5dac6205af2d57896d639c30271dac5916a25c6", "open"))

    def test_the_fake_prints_the_real_shape(self):
        import subprocess

        env = {**os.environ, "RAD_HOME": str(self.home)}
        out = subprocess.run([sys.executable, str(FAKE_RAD), "issue", "open", "--title", "No mode()", "--description",
                              "stats has no mode(): mode([1, 2, 2, 3]) should be 2.\nsecond line"],
                             capture_output=True, text=True, env=env, check=True).stdout
        iid = v3cli.rad_issue_id(out)
        self.assertEqual([x[0] for x in out.splitlines()], [x[0] for x in self.REAL_OPEN.splitlines()])
        self.assertEqual(out.splitlines()[5].strip("│ "), "")
        subprocess.run([sys.executable, str(FAKE_RAD), "issue", "comment", iid, "--message", "a comment"],
                       capture_output=True, text=True, env=env, check=True)
        shown = subprocess.run([sys.executable, str(FAKE_RAD), "issue", "show", iid[:7]], capture_output=True,
                               text=True, env=env, check=True).stdout
        self.assertEqual(sum(x.startswith("├") for x in shown.splitlines()), 1)
        self.assertEqual(v3cli.rad_box(shown)["Title"], "No mode()")


# ---------- 4.4: the approval race ----------

class TestApprovalRace(Case):
    """VP17 (S1): the allowance lags behind the approval (the provider's node answering hasn't seen it)."""

    def submit_args(self):
        return ["submit", "--bounty", "1", "--patch", "c" * 40]

    def test_register_pledge_and_submit_wait_for_the_allowance(self):
        for argv, what in ((["issue", "register", "--rad-issue", "ab" * 20], "register"),
                           (["pledge", "--bounty", "1", "--amount", "10"], "pledge"),
                           (self.submit_args(), "commit")):
            self.slept.clear()
            chain = Chain(lag=2, activeCount=lambda to: [3])  # the first read, then one more before it shows
            _, lines = self.run_cmd(chain, *argv)
            self.assertEqual(self.sigs(chain), ["approve", what], argv)
            self.assertEqual(self.slept, [v3cli.APPROVAL_POLL_S], argv)
            self.assertIn("  waited 2 s until the chain showed the allowance", lines, argv)

    def test_a_refusal_for_the_allowance_is_sent_once_more(self):
        chain = Chain(lag=1, refuse={"register": 1})
        data, _ = self.run_cmd(chain, "issue", "register", "--rad-issue", "ab" * 20)
        self.assertEqual(self.sigs(chain), ["approve", "register", "register"])
        self.assertEqual(data["issue"], 1)

    def test_refused_twice_fails_and_sends_nothing_more(self):
        chain = Chain(refuse={"register": 2})
        msg = self.refused(chain, "issue", "register", "--rad-issue", "ab" * 20)
        self.assertEqual(self.sigs(chain), ["approve", "register", "register"])
        self.assertIn("register reverted twice: ERC20InsufficientAllowance", msg)
        self.assertIn("run the command again in a minute", msg)
        self.assertIn("Nothing more was sent", msg)

    def test_an_allowance_never_shown_waits_60_s_then_sends(self):
        chain = Chain(lag=10**6)
        _, lines = self.run_cmd(chain, "issue", "register", "--rad-issue", "ab" * 20)
        self.assertEqual(sum(self.slept), v3cli.APPROVAL_WAIT_S)
        self.assertIn("  the chain doesn't show the allowance after 60 s; sending anyway (once more if it is refused "
                      "for the allowance)", lines)

    def test_another_revert_isnt_retried(self):
        chain = Chain(allowance=lambda to, *a: [2**255])

        def refuse(to, sig, *args, **kw):
            chain.sent.append((to, sig, args))
            raise Reverted("TooFewActiveSolvers", "0x")
        a = cli.parser().parse_args(["--record", str(self.v3), "issue", "register", "--rad-issue", "ab" * 20])
        with mock.patch.object(cli, "Rpc", return_value=chain):
            ctx = cli.Ctx(a)
        with mock.patch.object(Wallet, "send", side_effect=refuse), self.assertRaises(cli.Fail):
            v3cli.cmd_register(ctx, a)
        self.assertEqual(self.sigs(chain), ["register"])


# ---------- 4.5: transaction hashes ----------

class TestTxHashes(Case):
    """VP17 (S2): every sending command prints each transaction's hash and block, and its JSON carries `tx` and
    `block` (and `txs` when it sent several)."""

    def check(self, data, lines, whats):
        self.assertEqual((data["tx"], data["block"]), ("0x%064x" % (0xabc000 + len(whats)), 1000 + len(whats)))
        if len(whats) > 1:
            self.assertEqual([t["what"] for t in data["txs"]], whats)
        else:
            self.assertNotIn("txs", data)
        for n, what in enumerate(whats, 1):
            self.assertIn(f"  tx {'0x%064x' % (0xabc000 + n)} in block {1000 + n} ({what})", lines)

    def test_faucet(self):
        self.check(*self.run_cmd(Chain(), "faucet"), ["claim"])

    def test_issue_register_with_its_approval(self):
        self.check(*self.run_cmd(Chain(), "issue", "register", "--rad-issue", "ab" * 20), ["approve", "register"])

    def test_issue_open(self):
        self.check(*self.run_cmd(Chain(), "issue", "open", "--issue", "1"), ["openBounty"])

    def test_pledge(self):
        chain = Chain(activeCount=lambda to: [3], allowance=lambda to, *a: [2**255])
        self.check(*self.run_cmd(chain, "pledge", "--bounty", "1", "--amount", "5"), ["pledge"])

    def test_submit(self):
        data, lines = self.run_cmd(Chain(), "submit", "--bounty", "1", "--patch", "c" * 40)
        self.check(data, lines, ["approve", "commit"])
        self.assertIn("if no validator draws it within 10 minutes: pofctl --v3 draw 9", lines)

    def test_claim(self):
        salt = b"\x11" * 32
        sealed = v3.fix_commitment(v2.commit_word("c" * 40), v2.commit_word(BASE), salt, REPORTER)
        chain = Chain(bounty=lambda to, b: [(1, v3.WON, 0, False, 0, 0, 0, 0, 9, 0, 1, 0)])
        chain.subs[9] = {"solver": REPORTER, "commitment": sealed}
        self.check(*self.run_cmd(chain, "claim", "--bounty", "1", "--patch", "c" * 40, "--base", BASE, "--salt",
                                 "0x" + salt.hex()), ["claim"])

    def test_merge(self):
        chain = Chain(bounty=lambda to, b: [(1, v3.CLAIMED, 0, False, 0, 0, 0, 0, 9, 0, 1, 0)],
                      award=lambda to, b, e: [(REPORTER, b"\0" * 32, 9, False, 0, False)])
        chain.subs[9] = {"solver": REPORTER, "base": v2.commit_word(BASE)}
        chain.verdicts[9] = {"status": v3.FINAL, "pass": True}
        self.check(*self.run_cmd(chain, "merge", "--bounty", "1"), ["merge"])

    def test_draw(self):
        chain = Chain()
        chain.verdicts[7] = {"status": v3.SEALED, "seedBlock": 1}
        self.check(*self.run_cmd(chain, "draw", "7"), ["draw", "signal"])

    def test_withdraw(self):
        self.check(*self.run_cmd(Chain(owed=lambda to, *a: [3 * C]), "withdraw", "--role", "solver"), ["withdraw"])


# ---------- VP26 (Q4): attempt ----------

def config_with(attempt_fee: int):
    """RaceV3's getConfig with this attempt fee (micro-coins), the rest as test_pofctl_v3's FakeRpc has it."""
    cfg = (RACE, RACE, 2 * C, 5 * C, attempt_fee, 0, 0, 10 * C, 5000, 1000, 1765, 28, 7, 14, 7, 4, 0)
    return {"getConfig": lambda to, *a: [cfg]}


class TestAttempt(Case):
    """`pofctl --v3 attempt --bounty B` (v3.1 polish VP26, the owner's Q4 of 2026-11-24), in place of the guide's
    `cast send <race> "attempt(uint256)"`."""

    def test_a_free_attempt_sends_it_and_prints_its_tx_and_the_next_step(self):
        chain = Chain()
        data, lines = self.run_cmd(chain, "attempt", "--bounty", "1")
        self.assertEqual([(s[0].lower(), s[1], s[2]) for s in chain.sent], [(RACE, "attempt(uint256)", (1,))])
        self.assertEqual((data["tx"], data["block"]), ("0x%064x" % 0xabc001, 1001))
        self.assertNotIn("txs", data)
        self.assertEqual((data["bounty"], data["attemptFee"], data["claim"], data["room"]), (1, 0, 5 * C, 50 * C))
        self.assertRegex(data["solver"], r"^0x[0-9a-fA-F]{40}$")  # the devnet's solver key
        self.assertEqual((data["locked"], data["lockBps"], data["attempting"]), (True, 5000, 1))
        self.assertIn("pofctl --v3 submit --bounty 1 --patch <your fix's commit>", data["next"])
        text = "\n".join(lines)
        self.assertIn("bounty 1 is open: a fix would claim 5.000000 now (its share rising until the first attempt "
                      "locks it)", text)
        self.assertIn("attempted bounty 1: its share is locked at 50 %; 1 attempt(s) in progress", text)
        self.assertIn(f"  tx {'0x%064x' % 0xabc001} in block 1001 (attempt)", lines)
        self.assertTrue(lines[-1].startswith("next: fix it on top of Heads.head"))

    def test_a_fee_is_approved_with_the_wait_for_the_allowance(self):
        chain = Chain(lag=2, **config_with(1 * C))
        data, lines = self.run_cmd(chain, "attempt", "--bounty", "1")
        self.assertEqual(self.sigs(chain), ["approve", "attempt"])
        self.assertEqual(self.slept, [v3cli.APPROVAL_POLL_S])
        self.assertIn("  waited 2 s until the chain showed the allowance", lines)
        self.assertEqual([t["what"] for t in data["txs"]], ["approve", "attempt"])
        self.assertEqual(data["attemptFee"], 1 * C)

    def test_a_refusal_for_the_allowance_is_sent_once_more(self):
        chain = Chain(lag=1, refuse={"attempt": 1}, **config_with(1 * C))
        data, _ = self.run_cmd(chain, "attempt", "--bounty", "1")
        self.assertEqual(self.sigs(chain), ["approve", "attempt", "attempt"])
        self.assertEqual(data["attempting"], 1)

    def test_an_allowance_already_there_approves_nothing(self):
        chain = Chain(**config_with(1 * C))
        chain.allowed = 2**255
        self.run_cmd(chain, "attempt", "--bounty", "1")
        self.assertEqual(self.sigs(chain), ["attempt"])

    def test_a_bounty_that_isn_t_open_is_refused_with_nothing_sent(self):
        chain = Chain(bounty=lambda to, b: [(1, v3.WON, 0, True, 5000, 0, 1, 1, 9, 0, 1, 0)])
        msg = self.refused(chain, "attempt", "--bounty", "1")
        self.assertIn("bounty 1 is Won: an attempt is recorded on an open bounty. Nothing was sent.", msg)
        self.assertEqual(chain.sent, [])

    def test_a_claim_over_the_room_is_refused_with_nothing_sent(self):
        chain = Chain(openClaims=lambda to, *a: [48 * C], **config_with(1 * C))
        msg = self.refused(chain, "attempt", "--bounty", "1")
        self.assertIn("a fix of bounty 1 would claim 5.000000 (its price on offer)", msg)
        self.assertIn("its commit would be refused (D29), so the attempt would only spend gas and the attempt fee "
                      "1.000000", msg)
        self.assertIn("Nothing was sent.", msg)
        self.assertEqual(chain.sent, [])

    def test_a_fee_the_wallet_can_t_pay_is_refused_with_nothing_sent(self):
        chain = Chain(balanceOf=lambda to, *a: [0], **config_with(1 * C))
        msg = self.refused(chain, "attempt", "--bounty", "1")
        self.assertIn("the attempt fee needs 1.000000", msg)
        self.assertIn("Nothing was sent.", msg)
        self.assertEqual(chain.sent, [])

    def test_attempt_selects_v3_and_its_json(self):
        a = cli.parser().parse_args(["attempt", "--bounty", "4"])
        self.assertEqual((a.bounty, a.fn3), (4, v3cli.cmd_attempt))
        self.assertIn("attempt", v3cli.V3_ONLY)
        chain = Chain()
        with mock.patch.object(Wallet, "send", side_effect=chain.send):
            code, out, err = run_main(["--record", str(self.v3), "--json", "attempt", "--bounty", "1"], chain)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual((data["tx"], data["block"], data["lockBps"]), ("0x%064x" % 0xabc001, 1001, 5000))
        self.assertIn("next", data)


# ---------- 4.6: the reporter's view ----------

class TestIssueShow(Case):
    def chain(self, status: int, **verdict) -> Chain:
        chain = Chain()
        chain.issues[1] = {"reporter": REPORTER, "check": 2, "state": 1, "stake": 5 * C}
        chain.verdicts[2] = {"status": status, **verdict}
        chain.subs[2] = {"issue": 1, "solver": REPORTER, "deposit": 7 * C, "charged": 0}
        return chain

    def show(self, chain):
        data, lines = self.run_cmd(chain, "issue", "show", "--issue", "1")
        self.assertEqual(chain.sent, [])  # reads only
        return data, "\n".join(lines)

    def test_sealed(self):
        data, text = self.show(self.chain(v3.SEALED, seedBlock=101))
        self.assertEqual((data["status"], data["panel"], data["result"]), ("sealed", 0, None))
        self.assertIn("issue 1 (reporter", text)
        self.assertIn("  check          2: sealed", text)
        self.assertIn("  draw           at seed block 101 (now block 100); if no validator draws it within 10 minutes: "
                      "pofctl --v3 draw 2", text)
        self.assertIn("  deposit        paid to judges 0.000000; refund due 7.000000 after the verdict", text)

    def test_held_after_a_pass(self):
        chain = self.chain(v3.HELD, k=1, pid=4, **{"pass": True})
        chain.panels[4] = {"sealBy": 10_000 - 7200, "revealBy": 10_000 - 3600, "k": 1, "judges": [BOOK]}
        chain.subs[2].update(deposit=5 * C, charged=2 * C)
        data, text = self.show(chain)
        self.assertEqual((data["status"], data["result"], data["held"], data["k"], data["panel"]),
                         ("held", "pass", True, 1, 4))
        self.assertEqual((data["sealBy"], data["revealBy"], data["reportBy"]), (2800, 6400, 6400 + 86400))
        self.assertEqual(data["deposit"], {"paid": 2 * C, "left": 5 * C, "refundDue": 5 * C, "refunded": False,
                                           "refundFrom": 0})
        self.assertIn(f"  panel          4, k = 1: {crypto.checksum(BOOK)}", text)
        self.assertIn("  seal by        1970-01-01 00:46:40 UTC (2 h 00 min ago)", text)
        self.assertIn("  reveal by      1970-01-01 01:46:40 UTC (1 h 00 min ago)", text)
        self.assertIn("  reports by     1970-01-02 01:46:40 UTC (in 23 h 00 min)", text)
        self.assertIn("  result         pass (counted at k = 1)", text)
        self.assertIn("  held           a pass at k = 1 waits until enough validators outside its panel", text)
        self.assertIn("  deposit        paid to judges 2.000000; refund due 5.000000 after the verdict", text)

    def test_final_and_refunded(self):
        chain = self.chain(v3.FINAL, k=3, pid=4, finalAt=5_000, **{"pass": True})
        chain.panels[4] = {"sealBy": 1_000, "revealBy": 2_000, "k": 3, "judges": [BOOK, RACE, PANELS]}
        chain.subs[2].update(deposit=0, charged=3 * C, done=True, outcome=1)
        data, text = self.show(chain)
        self.assertEqual((data["status"], data["result"], data["finalAt"], data["outcome"]), ("final", "pass", 5_000,
                                                                                              "Pass"))
        self.assertEqual(data["deposit"], {"paid": 3 * C, "left": 0, "refundDue": 0, "refunded": True,
                                           "refundFrom": 5_000 + 86_400})
        self.assertIn("  final          since 1970-01-01 01:23:20 UTC (1 h 23 min ago)", text)
        self.assertIn("  deposit        paid to judges 3.000000; refunded", text)
        self.assertIn("  next           anyone opens its bounty: pofctl --v3 issue open --issue 1", text)

    def test_released(self):
        data, text = self.show(self.chain(v3.RELEASED))
        self.assertEqual((data["status"], data["result"]), ("released", None))
        self.assertIn("  released       never judged", text)

    def test_the_window_and_json(self):
        chain = self.chain(v3.WINDOW, k=1, pid=4, finalAt=10_000 + 86_400, **{"pass": False})
        chain.panels[4] = {"sealBy": 1_000, "revealBy": 2_000, "k": 1, "judges": [BOOK]}
        code, out, err = run_main(["--json", "--record", str(self.v3), "issue", "show", "--issue", "1"], chain)
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual((data["status"], data["result"], data["finalAt"]), ("window", "fail", 96_400))
        self.assertIn("refundFrom", data["deposit"])

    def test_no_such_issue(self):
        with self.assertRaises(cli.Fail) as e:
            self.run_cmd(Chain(), "issue", "show", "--issue", "9")
        self.assertIn("there is no on-chain issue 9", str(e.exception))


# ---------- 2.9 and 2.10: the RPC key never printed; a 429 retried by default ----------

KEY = "0123456789abcdef0123456789abcdef"
URL = f"https://sepolia.provider.example/v3/{KEY}"


def _http_429(*a, **kw):
    raise urllib.error.HTTPError(URL, 429, "Too Many Requests", {"Retry-After": "0"}, None)


class _Answer:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self.body


class TestRpcKey(Records):
    def assert_no_key(self, text: str) -> None:
        for part in (KEY, KEY[:8], KEY[8:16], KEY[-8:]):
            self.assertNotIn(part, text)

    def test_a_429_printed_by_pofctl_shows_no_part_of_the_key(self):
        err = io.StringIO()
        with mock.patch("urllib.request.urlopen", side_effect=_http_429), mock.patch("time.sleep"), \
                mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", err):
            code = cli.main(["--rpc", URL, "--record", str(self.v3), "--v3", "status", "--address", RACE])
        text = err.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("HTTP 429", text)
        self.assertIn("https://sepolia.provider.example/…", text)  # the shown URL
        self.assert_no_key(text)

    def test_a_traceback_through_rpc_is_redacted(self):
        def boom(*a, **kw):
            raise RuntimeError(f"a library's message naming {URL}")
        err = io.StringIO()
        with mock.patch("urllib.request.urlopen", side_effect=boom), mock.patch("sys.stdout", io.StringIO()), \
                mock.patch("sys.stderr", err):
            code = cli.main(["--rpc", URL, "--record", str(self.v3), "--v3", "status", "--address", RACE])
        self.assertEqual(code, 2)
        self.assertIn("Traceback", err.getvalue())
        self.assertIn("RuntimeError: a library's message naming https://sepolia.provider.example/…", err.getvalue())
        self.assert_no_key(err.getvalue())

    def test_pofctl_passes_no_retries(self):
        with mock.patch.object(cli, "Rpc") as made:
            cli.make_rpc(URL, {})
        self.assertNotIn("retries", made.call_args.kwargs)

    @mock.patch("time.sleep")
    def test_a_pofctl_read_survives_one_429(self, _sleep):
        if inspect.signature(Rpc).parameters["retries"].default == 0:
            self.skipTest("needs VP19 Rpc default (task 2.10: Rpc's DEFAULT_RETRIES 3)")
        answers = iter([_http_429, lambda *a, **kw: _Answer(b'{"jsonrpc": "2.0", "id": 1, "result": "0xaa36a7"}')])
        err = io.StringIO()
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **kw: next(answers)(*a, **kw)), \
                mock.patch("sys.stderr", err):
            self.assertEqual(cli.make_rpc(URL, {}).chain_id(), 11155111)
        self.assert_no_key(err.getvalue())  # the retry's log line too
