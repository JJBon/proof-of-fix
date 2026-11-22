"""A transient failure doesn't end a node's run (proof-of-fix#166): the RPC client's bounded retries, what it never
retries, transactions that can't go twice, and what a node does when the chain stays away. urllib is mocked and every
sleep injected: no network, and nothing depends on timing."""

from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # test_oracle_v2's fakes, as tests.test_*

from oracle import crypto, v2  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.keys import LocalDevKeys  # noqa: E402
from oracle.node_v2 import Exchange, NodeV2  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rpc import Reverted, Rpc, RpcError, Unavailable, Wallet  # noqa: E402
from test_oracle_v2 import CHAIN, RACE, FakeChain, FakeHost, FakeWallet  # noqa: E402

URL = "https://devnet.example/"
OK = {"jsonrpc": "2.0", "id": 1, "result": "0x10"}


def http_error(code: int, retry_after: str = "") -> urllib.error.HTTPError:
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(URL, code, "error", headers, io.BytesIO(b""))


class Answer(io.BytesIO):
    """What urlopen returns, as a context manager."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def answers(*items):
    """urlopen's side effect: each item raised if it's an exception, else answered as JSON (bytes as they are)."""
    out = []
    for item in items:
        if isinstance(item, BaseException):
            out.append(item)
        else:
            out.append(Answer(item if isinstance(item, bytes) else json.dumps(item).encode()))
    return mock.patch("urllib.request.urlopen", side_effect=out)


class Retries(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.rpc = Rpc(URL, retries=3, sleep=self.sleeps.append)

    def test_each_transient_failure_is_tried_again(self):
        for failure in (http_error(502), http_error(503), http_error(504), http_error(429),
                        urllib.error.URLError(ConnectionRefusedError("refused")), socket.timeout("timed out"),
                        ConnectionResetError("reset"), b"<html>Bad Gateway</html>"):
            with answers(failure, OK) as urlopen:
                self.assertEqual(self.rpc.call("eth_blockNumber"), "0x10", failure)
            self.assertEqual(urlopen.call_count, 2)

    def test_backoff_is_bounded_and_honours_retry_after_up_to_the_cap(self):
        rpc = Rpc(URL, retries=6, sleep=self.sleeps.append)
        with answers(*[http_error(502)] * 6, OK):
            rpc.call("eth_blockNumber")
        self.assertEqual(self.sleeps, [1.0, 2.0, 4.0, 8.0, 15.0, 15.0])
        self.sleeps.clear()
        with answers(http_error(429, "7"), http_error(429, "900"), http_error(429, "soon"), OK):
            rpc.call("eth_blockNumber")
        self.assertEqual(self.sleeps, [7.0, 15.0, 4.0])

    def test_exhausted_retries_raise_unavailable_with_no_key_in_the_message(self):
        rpc = Rpc("https://alice:s3cret@devnet.example/", retries=2, sleep=self.sleeps.append)
        with answers(*[http_error(502)] * 3) as urlopen, self.assertRaises(Unavailable) as caught:
            rpc.call("eth_blockNumber")
        self.assertEqual(urlopen.call_count, 3)
        self.assertNotIn("s3cret", str(caught.exception))
        self.assertIsInstance(caught.exception, RpcError)

    def test_no_retries_by_default(self):
        with answers(http_error(502)) as urlopen, self.assertRaises(Unavailable):
            Rpc(URL, sleep=self.sleeps.append).call("eth_blockNumber")
        self.assertEqual((urlopen.call_count, self.sleeps), (1, []))

    def test_non_transient_answers_arent_retried(self):
        for failure, kind in ((http_error(401), RpcError), (http_error(403), RpcError), (http_error(404), RpcError),
                              (http_error(500), RpcError),
                              ({"id": 1, "error": {"code": 3, "message": "execution reverted", "data": "0x"}}, Reverted),
                              ({"id": 1, "error": {"code": -32000, "message": "invalid opcode"}}, RpcError)):
            with answers(failure, OK) as urlopen, self.assertRaises(kind) as caught:
                self.rpc.call("eth_call")
            self.assertNotIsInstance(caught.exception, Unavailable)
            self.assertEqual(urlopen.call_count, 1, failure)
        self.assertEqual(self.sleeps, [])

    def test_a_call_the_server_would_pick_a_nonce_for_gets_one_try(self):
        for method in ("eth_sendTransaction", "evm_mine", "anvil_setBalance"):
            with answers(http_error(502), OK) as urlopen, self.assertRaises(Unavailable):
                self.rpc.call(method)
            self.assertEqual(urlopen.call_count, 1, method)


class ChainStub:
    """The JSON-RPC calls a wallet makes. `sends`: what each eth_sendRawTransaction does."""

    def __init__(self, sends=(), receipts=None, nonce=7):
        self.sends, self.receipts, self.nonce = list(sends), list(receipts or []), nonce
        self.raw, self.asked, self.prepared = [], [], 0

    def chain_id(self):
        return CHAIN

    def call(self, method, params=None):
        if method == "eth_estimateGas":
            self.prepared += 1
            return "0x5208"
        if method == "eth_getTransactionCount":
            self.nonce += 1
            return hex(self.nonce - 1)
        if method == "eth_gasPrice":
            return "0x1"
        if method == "eth_sendRawTransaction":
            self.raw.append(params[0])
            effect = self.sends.pop(0) if self.sends else "0xabc"
            if isinstance(effect, Exception):
                raise effect
            return effect
        if method == "eth_getTransactionReceipt":
            self.asked.append(params[0])
            effect = self.receipts.pop(0) if self.receipts else {"status": "0x1", "blockNumber": "0x1"}
            if isinstance(effect, Exception):
                raise effect
            return effect
        raise AssertionError(method)


class Transactions(unittest.TestCase):
    TO = crypto.checksum("0x" + "ab" * 20)

    def _wallet(self, chain):
        return Wallet(chain, 0x11)

    def test_a_lost_answer_doesnt_lose_or_repeat_the_transaction(self):
        chain = ChainStub(sends=[Unavailable("502")])
        receipt = self._wallet(chain).send(self.TO, "f()")
        self.assertEqual(receipt["status"], "0x1")
        self.assertEqual(len(chain.raw), 1)
        self.assertEqual(chain.asked[0], "0x" + crypto.keccak256(bytes.fromhex(chain.raw[0][2:])).hex())

    def test_a_copy_the_chain_already_has_counts_as_sent(self):
        for message in ("already known", "Transaction already imported", "nonce too low"):
            chain = ChainStub(sends=[RpcError(f"eth_sendRawTransaction: {message}")])
            self.assertEqual(self._wallet(chain).send(self.TO, "f()")["status"], "0x1")

    def test_any_other_refusal_stands(self):
        chain = ChainStub(sends=[RpcError("eth_sendRawTransaction: intrinsic gas too low")])
        with self.assertRaises(RpcError):
            self._wallet(chain).send(self.TO, "f()")
        self.assertEqual(chain.asked, [])

    def test_a_retry_of_the_same_call_sends_the_same_bytes(self):
        """The run's next pass, after no receipt: same nonce and hash, so it can't happen twice."""
        chain = ChainStub(receipts=[None])
        wallet = self._wallet(chain)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)  # no time to see a receipt
        self.assertEqual(wallet.send(self.TO, "f()")["status"], "0x1")
        self.assertEqual(len(chain.raw), 2)
        self.assertEqual(chain.raw[0], chain.raw[1])
        self.assertEqual(chain.prepared, 1)

    def test_a_confirmed_transaction_doesnt_stop_the_same_call_being_sent_again(self):
        chain = ChainStub()
        wallet = self._wallet(chain)
        wallet.send(self.TO, "f()")
        wallet.send(self.TO, "f()")  # e.g. minting twice: two transactions, two nonces
        self.assertNotEqual(chain.raw[0], chain.raw[1])

    def test_a_reverted_receipt_is_not_transient(self):
        chain = ChainStub(receipts=[{"status": "0x0", "blockNumber": "0x1"}])
        with self.assertRaises(Reverted):
            self._wallet(chain).send(self.TO, "f()")

    def test_a_spent_nonce_lets_a_later_call_sign_afresh(self):
        chain = ChainStub(sends=[RpcError("nonce too low")])
        wallet = self._wallet(chain)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)
        wallet.send(self.TO, "f()")
        self.assertNotEqual(chain.raw[0], chain.raw[1])


class FlakyChain(FakeChain):
    """A fake chain whose `committed` goes through a real Rpc, so a 502 comes through the real client; or `away`."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.away = 0  # passes left that raise Unavailable
        self.flaky_rpc = None

    def committed(self, from_block, to_block=None):
        if self.away:
            self.away -= 1
            raise Unavailable("the chain at https://devnet.example/ answered HTTP 502")
        if self.flaky_rpc:
            self.flaky_rpc.call("eth_blockNumber")
        return super().committed(from_block, to_block)


class Clock:
    def __init__(self, step: float = 1.0):
        self.now, self.step = 1000.0, step

    def __call__(self):
        self.now += self.step
        return self.now


class TheRun(unittest.TestCase):
    def setUp(self):
        from bot import logic

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        tmp = Path(self.tmp.name)
        self.keys = [LocalDevKeys(i, extra_chain_ids={CHAIN}) for i in range(3)]
        judges = [k.address() for k in self.keys]
        solver, salt, sha = crypto.checksum("0x" + "99" * 20), b"\x02" * 32, "ab" * 20
        self.chain = FlakyChain(judges, crypto.commitment(v2.commit_word(sha), salt, solver), solver)
        (tmp / "src" / sha).mkdir(parents=True)
        host = FakeHost([{"number": 3, "title": "Fix", "body": logic.pr_body(1, 1, 1, "0x" + salt.hex(), solver),
                          "state": "open", "head_sha": sha, "base_sha": "11" * 20, "merged": False}])
        self.logs, self.clock = [], Clock()
        self.nodes = [NodeV2(self.chain, k, FakeJudge(), host, "demo/median", tmp / "src",
                             Exchange(tmp / "exchange", RACE), Store(tmp / f"receipts-{i}"), 100 * 10**6,
                             runner=lambda argv: (0, "ok", ""), clock=self.clock, log=self.logs.append,
                             wallet=FakeWallet(self.chain, k.address())) for i, k in enumerate(self.keys)]
        self.node = self.nodes[0]

    def test_a_502_then_success_keeps_the_draw(self):
        rpc = Rpc(URL, retries=2, sleep=lambda s: None)
        self.chain.flaky_rpc = rpc
        with answers(http_error(502), OK, *[OK] * 200):
            for _ in range(20):
                for n in self.nodes:
                    n.tick(0)
        self.assertEqual(len(self.chain.results), 1)

    def test_exhausted_retries_end_the_pass_and_lose_nothing(self):
        self.node.tick(0)
        self.node.tick(0)
        c = self.node.checks[1]
        self.chain.away = 1
        with self.assertRaises(Unavailable):
            self.node.tick(0)
        self.assertIs(self.node.checks[1], c)  # the same round, with its salt
        self.assertNotIn(1, self.node.skipped)
        self.assertEqual(c.outcome, 0)
        self.node.tick(0)
        self.assertEqual(c.outcome, v2.PASS)

    def test_a_failure_of_a_read_before_the_check_doesnt_half_record_it(self):
        self.node.tick(0)
        self.node.tick(0)
        c, called = self.node.checks[1], []
        self.node.runner = lambda argv: (called.append(1) or (0, "ok", ""))
        real, self.chain.profile = self.chain.profile, mock.Mock(side_effect=Unavailable("502"))
        with self.assertRaises(Unavailable):
            self.node.tick(0)
        self.assertEqual((c.outcome, c.usage, called), (0, None, []))  # the tests didn't run: nothing was spent
        self.chain.profile = real
        self.node.tick(0)
        self.assertEqual((c.outcome, len(called)), (v2.PASS, 2))  # one check: its two runs (#251 L22)
        self.assertIsNotNone(c.usage)

    def test_a_report_that_didnt_go_through_is_sent_again_on_the_next_pass(self):
        self.node.tick(0)
        self.node.tick(0)
        self.node.tick(0)
        c, real = self.node.checks[1], self.node.wallet.send
        self.node.wallet.send = mock.Mock(side_effect=Unavailable("no receipt"))
        with self.assertRaises(Unavailable):
            self.node.tick(0)
        self.assertFalse(c.reported)
        self.node.wallet.send = real
        self.node.tick(0)
        self.assertTrue(c.reported)
        self.assertEqual(len(self.chain.reports_), 1)

    def test_the_run_outlasts_an_outage_and_it_doesnt_count_as_idle(self):
        self.chain.away = 500  # far longer than the idle limit, in clock steps
        passes, real = [], self.node.tick

        def counted(block):
            passes.append(1)
            return real(block)

        self.node.tick = counted
        with mock.patch("oracle.node_v2.time.sleep"):
            self.node.run(0, until_idle=50.0, poll=0, outage_limit=100_000.0)
        self.assertGreater(len(passes), 500)  # it went on through the outage, then idled out from the chain's return
        self.assertTrue(any("idle for 50s" in m for m in self.logs))
        self.assertTrue(any("isn't answering" in m for m in self.logs))

    def test_the_outage_limit_ends_the_run_as_unfinished(self):
        self.chain.away = 10_000
        with mock.patch("oracle.node_v2.time.sleep"), self.assertRaises(Unavailable):
            self.node.run(0, until_idle=5.0, poll=0, outage_limit=30.0)
        self.assertFalse(any("idle" in m for m in self.logs))

    def test_a_node_with_no_idle_limit_keeps_trying(self):
        self.chain.away = 300
        passes = []
        real = self.node.tick

        def stop_after(block):
            passes.append(1)
            if not self.chain.away:
                raise KeyboardInterrupt
            return real(block)

        self.node.tick = stop_after
        with mock.patch("oracle.node_v2.time.sleep"), self.assertRaises(KeyboardInterrupt):
            self.node.run(0, poll=0)  # devnet-seats.sh's: no limit, it stays up with its round in memory
        self.assertGreater(len(passes), 300)

    def test_a_non_transient_error_still_ends_the_run(self):
        self.chain.submission = mock.Mock(side_effect=RpcError("the chain answered HTTP 401 (check the RPC key)"))
        with mock.patch("oracle.node_v2.time.sleep"), self.assertRaises(RpcError):
            self.node.run(0, until_idle=5.0, poll=0, outage_limit=30.0)

    def test_a_host_that_doesnt_answer_isnt_the_end_of_the_run(self):
        self.node.tick(0)
        self.node.host.pulls = mock.Mock(side_effect=urllib.error.HTTPError(URL, 502, "bad", Message(), io.BytesIO(b"")))
        self.assertFalse(self.node.tick(0))
        self.assertEqual(self.node.checks[1].pull, None)

    def test_a_restarted_node_that_already_reported_doesnt_judge_again(self):
        """A node has no state on disk: its salt is gone, the relay keeps its first seal, and a real model would be paid
        for an answer the round can't take."""
        node = self.node
        node.tick(0)
        node.tick(0)
        node.tick(0)
        node.tick(0)
        self.assertEqual(len(self.chain.reports_), 1)
        restarted = NodeV2(self.chain, self.keys[0], mock.Mock(side_effect=AssertionError("judged again")), node.host,
                           "demo/median", node.src_root, node.exchange, node.store, node.merge_weight,
                           runner=lambda argv: (0, "ok", ""), clock=self.clock, log=self.logs.append,
                           wallet=node.wallet)
        self.assertTrue(restarted.tick(0))
        self.assertIn(1, restarted.skipped)
        self.assertTrue(any("sitting the round out" in m for m in self.logs))


class TheRoundOnDisk(unittest.TestCase):
    """#216: a node sealed, its other judges silent, must neither stop on --until-idle inside the round's window nor,
    restarted, lose the salt that opens its seal."""

    def setUp(self):
        TheRun.setUp(self)
        from oracle import rounds

        self.rounds_dir = Path(self.tmp.name) / "rounds"
        self.node.rounds = rounds.Store(self.rounds_dir, CHAIN, RACE, self.node.address)

    def seal_alone(self):
        for _ in range(8):
            self.node.tick(0)
            if self.node.checks.get(1) and self.node.checks[1].sealed_at:
                return self.node.checks[1]
        self.fail("node 0 never sealed")

    def restarted(self, with_store=True):
        from oracle import rounds

        n = self.node
        r = NodeV2(self.chain, self.keys[0], mock.Mock(side_effect=AssertionError("judged again")), n.host,
                   "demo/median", n.src_root, n.exchange, n.store, n.merge_weight,
                   runner=lambda argv: (_ for _ in ()).throw(AssertionError("tests run again")), clock=self.clock,
                   log=self.logs.append, wallet=n.wallet)
        if with_store:
            r.rounds = rounds.Store(self.rounds_dir, CHAIN, RACE, r.address)
        return r

    def test_the_round_is_on_disk_private_before_the_seal_leaves(self):
        c = self.seal_alone()
        files = list(self.rounds_dir.rglob("1.json"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual(files[0].parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(json.loads(files[0].read_text())["salt"], {"hex": c.salt.hex()})

    def test_a_sealed_round_isnt_idleness_until_its_window_closes(self):
        c = self.seal_alone()
        with mock.patch("oracle.node_v2.time.sleep"):
            self.node.run(0, until_idle=5.0, poll=0)
        self.assertTrue(c.revealed_at, "stopped before revealing")
        self.assertGreaterEqual(c.revealed_at - c.sealed_at, self.node.round_timeout)

    def test_a_restarted_node_reveals_with_its_first_salt_and_judges_nothing_again(self):
        first = self.seal_alone()
        again = self.restarted()
        self.assertTrue(again.tick(0))
        self.assertTrue(any("resuming this seat's round from disk (sealed" in m for m in self.logs))
        self.assertNotIn(1, again.skipped)
        self.clock.now += again.round_timeout  # the silent judges' window closes
        for _ in range(3):
            again.tick(0)
        reveals = {k.lower(): m for k, m in again.exchange.all(1, "reveal").items()}
        self.assertIn(again.address.lower(), reveals, self.logs[-5:])
        reveal = reveals[again.address.lower()]
        self.assertEqual(reveal["salt"], "0x" + first.salt.hex())
        self.assertEqual(reveal["receipt"], first.receipt_hash)
        self.assertEqual(len(self.chain.reports_), 1)  # reported once, by the first run

    def test_without_a_store_a_restarted_node_still_sits_out(self):
        self.seal_alone()
        again = self.restarted(with_store=False)
        self.assertTrue(again.tick(0))
        self.assertIn(1, again.skipped)

    def test_a_finished_round_leaves_no_file(self):
        for _ in range(40):
            for n in self.nodes:
                n.tick(0)
        self.assertEqual(len(self.chain.results), 1)
        for _ in range(5):
            self.node.tick(0)
        if self.node.checks[1].done:
            self.assertEqual(list(self.rounds_dir.rglob("1.json")), [])

class TheCommandLine(unittest.TestCase):
    def test_a_chain_thats_away_exits_75(self):
        from oracle import __main__ as cli

        env = {"ORACLE_RPC": URL, "ORACLE_RACE": RACE, "ORACLE_RPC_RETRIES": "0", "ORACLE_KEYS": "local:0"}
        with mock.patch.dict("os.environ", env), answers(http_error(502)), mock.patch("builtins.print"):
            self.assertEqual(cli.main(["oracle", "run", "--until-idle", "5"]), 75)

    def test_retries_come_from_the_environment(self):
        from oracle import __main__ as cli

        with mock.patch.dict("os.environ", {"ORACLE_RPC": URL}):
            self.assertEqual(cli.rpc_from_env().retries, cli.DEFAULT_RPC_RETRIES)
        with mock.patch.dict("os.environ", {"ORACLE_RPC": URL, "ORACLE_RPC_RETRIES": "0"}):
            self.assertEqual(cli.rpc_from_env().retries, 0)


if __name__ == "__main__":
    unittest.main()
