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
from oracle import rpc as rpc_module  # noqa: E402
from oracle.judge import FakeJudge  # noqa: E402
from oracle.keys import LocalDevKeys  # noqa: E402
from oracle.node_v2 import Exchange, NodeV2  # noqa: E402
from oracle.receipt import Store  # noqa: E402
from oracle.rpc import DEFAULT_RETRIES, RETRY_AFTER_MAX_S, Reverted, Rpc, RpcError, Unavailable, Wallet  # noqa: E402
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
        self.assertEqual(self.sleeps, [7.0, RETRY_AFTER_MAX_S, 4.0])  # Retry-After up to 30 s (VP19)

    def test_exhausted_retries_raise_unavailable_with_no_key_in_the_message(self):
        rpc = Rpc("https://alice:s3cret@devnet.example/", retries=2, sleep=self.sleeps.append)
        with answers(*[http_error(502)] * 3) as urlopen, self.assertRaises(Unavailable) as caught:
            rpc.call("eth_blockNumber")
        self.assertEqual(urlopen.call_count, 3)
        self.assertNotIn("s3cret", str(caught.exception))
        self.assertIsInstance(caught.exception, RpcError)

    def test_three_retries_by_default_honouring_retry_after(self):
        """#251 v3.1 polish VP19 (S5): an Rpc built with no `retries` retries a 429 DEFAULT_RETRIES (3) times, waiting
        what Retry-After says; it never repeats eth_sendTransaction, and never a revert."""
        self.assertEqual(DEFAULT_RETRIES, 3)
        rpc = Rpc(URL, sleep=self.sleeps.append)
        with answers(http_error(429, "5"), http_error(429, "6"), http_error(429, "7"), OK) as urlopen:
            self.assertEqual(rpc.call("eth_blockNumber"), "0x10")
        self.assertEqual((urlopen.call_count, self.sleeps), (4, [5.0, 6.0, 7.0]))
        self.sleeps.clear()
        with answers(*[http_error(429, "2")] * 4) as urlopen, self.assertRaises(Unavailable) as caught:
            rpc.call("eth_getLogs")
        self.assertEqual((urlopen.call_count, self.sleeps), (4, [2.0, 2.0, 4.0]))
        self.assertEqual(caught.exception.retry_after, 2.0)  # the last answer's, for the keeper's pause (VP6)
        self.sleeps.clear()
        with answers(http_error(429, "1"), OK) as urlopen, self.assertRaises(Unavailable):
            rpc.call("eth_sendTransaction")
        self.assertEqual((urlopen.call_count, self.sleeps), (1, []))
        with answers({"id": 1, "error": {"code": 3, "message": "execution reverted", "data": "0x"}}, OK) as urlopen, \
                self.assertRaises(Reverted):
            rpc.call("eth_call")
        self.assertEqual((urlopen.call_count, self.sleeps), (1, []))
        with answers(http_error(429, "1"), {"id": 1, "result": "0x" + "ab" * 32}) as urlopen:
            rpc.call("eth_sendRawTransaction", ["0x00"])  # its bytes carry their own nonce: safe to repeat
        self.assertEqual(urlopen.call_count, 2)

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
        if method == "eth_getTransactionByHash":  # asked only when a refusal leaves it open: not here
            return None
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
        """Bytes that may have gone out (a lost answer), then refused as a taken nonce the chain shows nothing for:
        maybe sent, so waited for; with no receipt, a later call signs afresh (VP27 keeps this for bytes once out)."""
        chain = ChainStub(sends=[Unavailable("502"), RpcError("nonce too low")], receipts=[None, None])
        wallet = self._wallet(chain)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)  # the same bytes: refused, not signed again
        self.assertEqual(chain.raw[0], chain.raw[1])
        wallet.send(self.TO, "f()")
        self.assertNotEqual(chain.raw[1], chain.raw[2])


def nonce_of(raw: bytes) -> int:
    """A legacy transaction's nonce: the first item of its RLP list."""
    i = 1 + (raw[0] - 0xf7 if raw[0] > 0xf7 else 0)
    if raw[i] < 0x80:
        return raw[i]
    return int.from_bytes(raw[i + 1:i + 1 + raw[i] - 0x80], "big")


class LoadBalancedChain:
    """A chain behind a load-balanced public RPC (#251 v3.1 polish VP27): it mines each accepted transaction at once,
    but `stale` pending counts are answered first, one per ask, by a backend that hasn't seen the last ones.
    `refuse`: a refusal message for every send, whatever its nonce (a chain that never takes it); `drop`: the next
    accepted transaction is lost by the pool (gone until sent again); `hold`: receipt asks a pooled transaction waits
    before it mines (0: mined as it's accepted); `lose`: the next send's answer is lost after it arrives."""

    url = "https://sepolia.infura.io/v3/4f1e9c0a7b3d42e8a5c6d7e8f9a0b1c2"  # a key in the path

    def __init__(self, next_nonce=0, stale=(), refuse=None, drop=False, hold=0, lose=False):
        self.next, self.stale, self.refuse, self.drop = next_nonce, list(stale), refuse, drop
        self.hold, self.lose = hold, lose
        self.mined, self.pool, self.nonces, self.counts = {}, {}, [], []

    def chain_id(self):
        return CHAIN

    def call(self, method, params=None):
        if method == "eth_estimateGas":
            return "0x5208"
        if method == "eth_gasPrice":
            return "0x1"
        if method == "eth_getTransactionCount":
            count = self.stale.pop(0) if self.stale else self.next
            self.counts.append(count)
            return hex(count)
        if method == "eth_sendRawTransaction":
            raw = bytes.fromhex(params[0][2:])
            h, nonce = "0x" + crypto.keccak256(raw).hex(), nonce_of(raw)
            self.nonces.append(nonce)
            if self.refuse:
                raise RpcError(f"eth_sendRawTransaction: {self.refuse}")
            if h in self.pool:
                raise RpcError("eth_sendRawTransaction: already known")
            if nonce < self.next:  # a mined copy too: it has left the pool
                raise RpcError("eth_sendRawTransaction: nonce too low")
            if self.drop:
                self.drop = False
            elif self.hold:
                self.pool[h] = [nonce, self.hold]
            else:
                self._mine(h, nonce)
            if self.lose:
                self.lose = False
                raise Unavailable("502")
            return h
        if method == "eth_getTransactionReceipt":
            if params[0] in self.pool:
                self.pool[params[0]][1] -= 1
                if self.pool[params[0]][1] < 0:
                    self._mine(params[0], self.pool.pop(params[0])[0])
            return self.mined.get(params[0])
        if method == "eth_getTransactionByHash":
            return self.mined.get(params[0]) or ({"hash": params[0]} if params[0] in self.pool else None)
        raise AssertionError(method)

    def _mine(self, h, nonce):
        self.mined[h] = {"status": "0x1", "blockNumber": hex(len(self.mined) + 1), "transactionHash": h}
        self.next = nonce + 1


class StaleNonces(unittest.TestCase):
    """The wallet's nonce on a load-balanced public RPC (VP27; seen live on Sepolia through PublicNode, 2026-11-24: a
    register signed with the approve's nonce, refused, then waited for as maybe sent until 60s ran out)."""

    TO = crypto.checksum("0x" + "ab" * 20)

    def setUp(self):
        patcher = mock.patch.object(Wallet, "poll_s", 0.001)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_stale_pending_nonce_is_refused_then_signed_again_past_it(self):
        chain = LoadBalancedChain(next_nonce=1, stale=[0, 0])  # the approve mined at 0; two backends behind
        receipt = Wallet(chain, 0x11).send(self.TO, "register()", wait=1)
        self.assertEqual(receipt["status"], "0x1")
        self.assertEqual(chain.nonces, [0, 1])  # the second signing is past the refused nonce, stale count or not
        self.assertEqual(chain.counts, [0, 0])

    def test_the_nonce_never_goes_backwards_within_a_process(self):
        chain = LoadBalancedChain()
        wallet = Wallet(chain, 0x11)
        wallet.send(self.TO, "approve()", wait=1)
        chain.stale = [0]  # the backend that answers next hasn't seen the approve
        wallet.send(self.TO, "register()", wait=1)
        self.assertEqual(chain.nonces, [0, 1])  # no refusal: the remembered nonce wins
        self.assertEqual(len(chain.mined), 2)

    def test_a_nonce_still_refused_after_the_retries_fails_clearly(self):
        chain = LoadBalancedChain(refuse="nonce too low: next nonce 9, tx nonce 0")
        with self.assertRaises(RpcError) as ctx:
            Wallet(chain, 0x11).send(self.TO, "register()", wait=1)
        self.assertNotIsInstance(ctx.exception, Unavailable)  # not "maybe sent": nothing waited for
        message = str(ctx.exception)
        self.assertIn("nonce 3", message)
        self.assertIn("https://sepolia.infura.io/…", message)
        self.assertNotIn("4f1e9c0a7b3d42e8a5c6d7e8f9a0b1c2", message)
        self.assertEqual(chain.nonces, [0, 1, 2, 3])  # 1 + NONCE_RETRIES signings, each past the last

    def test_other_providers_refusals_of_a_taken_nonce(self):
        for message in ("replacement transaction underpriced", "Nonce too low. Expected nonce to be 1 but got 0",
                        "NONCE_TOO_LOW", "OldNonce", "nonce has already been used",
                        "already known: 0x" + "cd" * 32):  # another transaction's hash: not these bytes
            chain = LoadBalancedChain(next_nonce=1, stale=[0])
            sends = iter([RpcError(f"eth_sendRawTransaction: {message}")])
            real = chain.call

            def call(method, params=None, real=real):
                if method == "eth_sendRawTransaction":
                    for effect in sends:
                        chain.nonces.append(nonce_of(bytes.fromhex(params[0][2:])))
                        raise effect
                return real(method, params)

            chain.call = call
            self.assertEqual(Wallet(chain, 0x11).send(self.TO, "register()", wait=1)["status"], "0x1", message)
            self.assertEqual(chain.nonces, [0, 1], message)

    def test_a_true_duplicate_is_still_waited_for(self):
        """The same bytes sent twice (the first answer lost, the copy pending): "already known", then its receipt, and
        no second signing."""
        chain = LoadBalancedChain(hold=2, lose=True)
        wallet = Wallet(chain, 0x11)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)  # no time to see a receipt: its bytes are kept
        self.assertEqual(wallet.send(self.TO, "f()", wait=1)["status"], "0x1")
        self.assertEqual(chain.nonces, [0, 0])
        self.assertEqual(len(chain.mined), 1)

    def test_its_own_mined_copy_refused_as_nonce_too_low_is_waited_for(self):
        """The same bytes again after the first copy mined: "nonce too low", but the chain knows the hash, so its
        receipt is the answer and nothing is signed again."""
        chain = LoadBalancedChain(lose=True)
        wallet = Wallet(chain, 0x11)
        with self.assertRaises(Unavailable):
            wallet.send(self.TO, "f()", wait=0)
        self.assertEqual(wallet.send(self.TO, "f()", wait=1)["status"], "0x1")
        self.assertEqual(chain.nonces, [0, 0])
        self.assertEqual(len(chain.mined), 1)

    def test_a_dropped_transaction_is_sent_once_more_with_the_same_bytes(self):
        chain = LoadBalancedChain(drop=True)
        now = [1000.0]
        clock = mock.Mock(time=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + 1.0))
        with mock.patch.object(rpc_module, "time", clock):
            receipt = Wallet(chain, 0x11).send(self.TO, "f()", wait=60)
        self.assertEqual(receipt["status"], "0x1")
        self.assertEqual(chain.nonces, [0, 0])  # the same nonce, the same bytes
        self.assertGreaterEqual(now[0] - 1000.0, rpc_module.DROPPED_AFTER_S)


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
