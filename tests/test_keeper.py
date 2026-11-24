"""The keeper-only node (proof-of-fix#251, v3.1 polish VP10; oracle/keeper.py, the seed host's build folded in), and no
RPC key in the node's or the keeper's log (VP20).

On test_oracle_v3's fake chain: an unregistered key keeps the checks (draws, signals, the result) and never seals,
reveals, posts a table or registers; the hourly cap holds; each transaction is a log line with its hash and block,
and a call mined but reverted says so. Through `main` with urllib mocked (no network): `run --once` and `info` as the
seed host's runbook runs them, a mismatched ORACLE_KEEPER_ADDRESS stops it, ORACLE_RPC_SECRET_ARN (a fake Secrets
Manager), and a 429 storm or a traceback from a provider whose key is in the URL's path logs no part of the key."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))  # test_oracle_v3's fakes

from oracle import __main__ as cli  # noqa: E402
from oracle import crypto, keeper, v3  # noqa: E402
from oracle.redact import REDACT, shown_url  # noqa: E402
from oracle.rpc import Reverted, Wallet  # noqa: E402
from test_oracle_v3 import RACE, FakeChain, Net  # noqa: E402

KEEPER_SECRET = 0xBEEF
KEEPER = crypto.address(KEEPER_SECRET)
KEY = "4f1e9c0a7b3d42e8a5c6d7e8f9a0b1c2"  # a provider key, as Infura's sits in the path
URL = f"https://sepolia.infura.io/v3/{KEY}"
SEAT_CALLS = {"seal", "reveal", "receipt", "report", "post", "register", "approve", "setCapacity", "challenge"}


class ChainWallet(Wallet):
    """Wallet.send against the fake chain: the call applied (a refusal raised as an estimate's revert), and a receipt
    as a node gives it. `mined_reverts`: call names mined but reverted (their gas spent)."""

    def __init__(self, chain, secret, mined_reverts=(), **kw):
        super().__init__(None, secret, "keeper", **kw)
        self.chain, self.mined_reverts, self.n = chain, set(mined_reverts), 0

    def send(self, to, signature, *args, **kw):
        name = signature.split("(")[0]
        if to == RACE and name == "release":
            name = "refund"
        self.n += 1
        receipt = {"transactionHash": "0x" + f"{self.n:064x}", "blockNumber": hex(self.chain.height),
                   "gasUsed": hex(100_000), "effectiveGasPrice": hex(2 * 10**9), "status": "0x1"}
        if name in self.mined_reverts:
            raise Reverted(f"{name} reverted in block {self.chain.height}", receipt={**receipt, "status": "0x0"})
        fn = getattr(self.chain, name, None)
        if fn is None:
            raise Reverted(f"{name}: not due")
        fn(self.address, *args)
        self.chain.txs.append((self.address, name, args))
        return receipt


class FakeKeeperWallet(keeper.KeeperWallet, ChainWallet):
    pass


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def keeper_on(chain, logs, **kw) -> keeper.Keeper:
    wallet = FakeKeeperWallet(chain, KEEPER_SECRET, log=logs.append, **kw)
    return keeper.Keeper(chain, wallet, log=logs.append)


class KeeperOnTheFakeChain(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_an_unregistered_key_keeps_the_checks_and_never_acts_as_a_seat(self):
        net = Net(self.tmp)
        c, logs = net.chain, []
        k = keeper_on(c, logs)
        self.assertEqual(c.validator(KEEPER)["state"], 0)  # no registration
        k.tick(0)
        self.assertEqual(c.names(KEEPER), [])  # the seed block hasn't passed
        c.height += 6
        k.tick(0)
        self.assertEqual(c.names(KEEPER), ["draw"])
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        k.tick(0)
        self.assertEqual(c.names(KEEPER), ["draw", "drawAudits", "result"])
        self.assertTrue(c.subs[1]["paid"] and c.panel(counted)["counted"])
        self.assertFalse(set(c.names(KEEPER)) & SEAT_CALLS)
        self.assertFalse(any(n in SEAT_CALLS for who, n, _ in c.txs if who == KEEPER))
        self.assertEqual(k.seats, {})
        with self.assertRaises(keeper.SetupError):
            k.me()  # no registration to act with: a seat step would fail loudly, never act
        self.assertFalse(hasattr(k, "verdicts") and k.verdicts)  # it never comments

    def test_transaction_lines_carry_the_hash_and_block_and_a_mined_revert_says_so(self):
        net = Net(self.tmp)
        c, logs = net.chain, []
        c.height += 6
        k = keeper_on(c, logs)
        k.tick(0)
        line = next(x for x in logs if x.startswith("tx "))
        self.assertRegex(line, r"^tx 0x0{63}1 draw\(1\): block \d+, gas 100000, 0\.000200000 ETH$")
        logs.clear()
        k2 = keeper_on(c, logs, mined_reverts={"drawAudits"})
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        k2.tick(0)
        self.assertTrue(any(x.startswith("tx 0x") and "drawAudits(1) mined but reverted in block" in x
                            and "0.000200000 ETH spent" in x for x in logs), logs)
        self.assertEqual(len(k2.wallet.sent), 2)  # the mined revert counts (gas spent); result too

    def test_the_hourly_cap_holds(self):
        net = Net(self.tmp)
        c, logs, clock = net.chain, [], Clock()
        for s in (2, 3, 4):
            c.add_submission(s)
        c.height += 6
        k = keeper_on(c, logs, max_per_hour=2, clock=clock)
        k.tick(0)
        k.tick(0)
        self.assertEqual(len([n for who, n, _ in c.txs if who == KEEPER]), 2)  # never past the cap within a pass
        self.assertEqual(sum("hourly transaction cap (2) is reached" in x for x in logs), 1)  # said once an hour
        clock.t += 3601
        k.tick(0)
        self.assertEqual(len([n for who, n, _ in c.txs if who == KEEPER]), 4)

    def test_an_estimate_that_reverts_isnt_counted(self):
        c, logs = FakeChain(), []
        k = keeper_on(c, logs, max_per_hour=1)
        with self.assertRaises(Reverted):
            k.wallet.send(c.panels, "nothing(uint256)", 1)
        self.assertTrue(k.wallet.room())


class Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code, retry_after=""):
    headers = Message()
    if retry_after:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(URL, code, "Too Many Requests", headers, io.BytesIO(b""))


class FakeNode:
    """urlopen against a JSON-RPC node: the calls a keeper's wallet and `info` make. `fail(method)` → an exception
    to raise for that call, or None."""

    def __init__(self, fail=None):
        self.methods, self.fail, self.height = [], fail or (lambda m: None), 120

    def __call__(self, req, timeout=None):
        body = json.loads(req.data)
        m, params = body["method"], body["params"]
        self.methods.append(m)
        err = self.fail(m)
        if err is not None:
            raise err
        result = {"eth_chainId": hex(11155111), "eth_blockNumber": hex(self.height), "eth_getBalance": hex(5 * 10**16),
                  "eth_estimateGas": hex(80_000), "eth_getTransactionCount": "0x3", "eth_gasPrice": hex(10**9)}.get(m)
        if m == "eth_sendRawTransaction":
            result = "0x" + "00" * 32
        if m == "eth_getTransactionReceipt":
            result = {"transactionHash": params[0], "blockNumber": hex(self.height), "gasUsed": hex(70_000),
                      "effectiveGasPrice": hex(10**9), "status": "0x1"}
        return Answer(json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode())


def run_main(argv, env, node, make_chain=None, entry=False):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch("urllib.request.urlopen", side_effect=node), mock.patch("oracle.rpc.time.sleep"), \
            mock.patch.dict("os.environ", env, clear=True), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        if entry:
            code = keeper.entry(argv)
        else:
            code = keeper.main(argv, make_chain=make_chain, sleep=lambda s: None)
    return code, out.getvalue(), err.getvalue()


def env_for(**kw):
    return {"ORACLE_RPC": URL, "ORACLE_RACE": RACE, "ORACLE_PRIVATE_KEY": hex(KEEPER_SECRET),
            "ORACLE_FROM_BLOCK": "100", "ORACLE_KEEPER_ADDRESS": KEEPER, "PATH": "/usr/bin:/bin", **kw}


def no_key(test, text):
    test.assertNotIn(KEY, text)
    for i in range(0, len(KEY) - 7):
        test.assertNotIn(KEY[i:i + 8], text)  # no 8-character piece of it either


class TheRunbookCommands(unittest.TestCase):
    """`python3 -m oracle.keeper run --once` and `info`, as the seed host runs them."""

    def setUp(self):
        self.chain = FakeChain()

    def make_chain(self, rpc, race):
        self.assertEqual(race, RACE)
        self.chain.rpc = rpc
        return self.chain

    def test_info_says_not_registered_keeper_only(self):
        code, out, _ = run_main(["keeper", "info"], env_for(), FakeNode(), self.make_chain)
        self.assertEqual(code, 0)
        self.assertIn(f"keeper {KEEPER} on chain 31337, RaceV3 {RACE}, block 120", out)
        self.assertIn("balance 0.050000 ETH", out)
        self.assertIn("scans from block 100", out)
        self.assertIn("not registered (keeper only)", out)
        self.assertNotIn("None", out)
        no_key(self, out)

    def test_run_once_draws_and_logs_the_transaction(self):
        self.chain.add_submission(1)
        self.chain.height += 6
        node = FakeNode()
        code, out, _ = run_main(["keeper", "run", "--once"], env_for(ORACLE_TX_POLL="0"), node, self.make_chain)
        self.assertEqual(code, 0)
        self.assertIn(f"keeping RaceV3 {RACE} on chain 31337 from block 100 as {KEEPER}, a pass every 120s", out)
        self.assertRegex(out, r"\[keeper\] tx 0x[0-9a-f]{64} draw\(1\): block 120, gas 70000, 0\.000070000 ETH")
        self.assertIn("eth_sendRawTransaction", node.methods)
        self.assertNotIn("eth_sendTransaction", node.methods)

    def test_the_defaults_are_the_seed_hosts(self):
        self.assertEqual((keeper.DEFAULT_POLL_S, keeper.DEFAULT_TX_POLL_S, keeper.DEFAULT_MAX_TX_HOUR), (120.0, 3.0, 60))
        seen = {}
        real = keeper.Keeper.loop

        def loop(k, start, poll, once=False, sleep=None):
            seen.update(poll=poll, tx_poll=k.wallet.poll_s, cap=k.wallet.max_per_hour, start=start)
            return real(k, start, poll, once=True, sleep=lambda s: None)

        with mock.patch.object(keeper.Keeper, "loop", loop):
            run_main(["keeper", "run", "--from-block", "150"], env_for(), FakeNode(), self.make_chain)
        self.assertEqual(seen, {"poll": 120.0, "tx_poll": 3.0, "cap": 60, "start": 150})

    def test_a_mismatched_address_stops_it(self):
        node = FakeNode()
        code, out, _ = run_main(["keeper", "run", "--once"], env_for(ORACLE_KEEPER_ADDRESS="0x" + "12" * 20), node,
                                self.make_chain)
        self.assertEqual(code, 1)
        self.assertIn(f"the key's address is {KEEPER}, not ORACLE_KEEPER_ADDRESS 0x{'12' * 20}: stopping", out)
        self.assertEqual(node.methods, [])  # nothing asked of the chain, nothing sent

    def test_the_rpc_url_from_a_secret(self):
        env = env_for(ORACLE_RPC_SECRET_ARN="arn:aws:secretsmanager:us-east-1:123456789012:secret:rpc-AbCdEf")
        del env["ORACLE_RPC"]
        with mock.patch("oracle.awssecret.get_secret", return_value=URL) as got:
            code, out, _ = run_main(["keeper", "info"], env, FakeNode(), self.make_chain)
        self.assertEqual(code, 0)
        self.assertEqual(got.call_args[0][0], env["ORACLE_RPC_SECRET_ARN"])
        self.assertEqual(self.chain.rpc.url, URL)
        no_key(self, out)


class NoKeyInTheLog(unittest.TestCase):
    """VP20: a provider whose key is in the URL's path (Infura's /v3/<key>) answers 429 until the retries give up, or
    an error message carries the whole URL: the keeper's and the node's lines, tracebacks included, show no part of
    the key."""

    def test_the_shown_url(self):
        self.assertEqual(shown_url(URL), "https://sepolia.infura.io/…")
        self.assertEqual(shown_url("https://alice:pw@devnet.example/"), "https://devnet.example/")
        self.assertEqual(shown_url("http://127.0.0.1:8545"), "http://127.0.0.1:8545")
        # a label in place of the port (the integration harness's piped chain) is shown, not refused
        self.assertEqual(shown_url("http://u:pw@127.0.0.1:8545 (through a docker exec pipe)"),
                         "http://127.0.0.1:8545 (through a docker exec pipe)")
        self.assertEqual(shown_url("https://eth-sepolia.g.alchemy.com/v2/abcdefgh1234"), "https://eth-sepolia.g.alchemy.com/…")

    def test_the_keeper_429_retried_then_failed(self):
        chain = FakeChain()
        chain.add_submission(1)
        chain.height += 6
        node = FakeNode(fail=lambda m: http_error(429, "1") if m == "eth_estimateGas" else None)
        code, out, err = run_main(["keeper", "run", "--once"], env_for(ORACLE_RPC_RETRIES=""), node,
                                  lambda rpc, race: chain)
        self.assertEqual(code, 0)
        self.assertEqual(node.methods.count("eth_estimateGas"), 6)  # the node's ORACLE_RPC_RETRIES default, 5
        self.assertIn("eth_estimateGas: the chain at https://sepolia.infura.io/… answered HTTP 429; retry 1 of 5", out)
        self.assertIn("the chain isn't answering the keeper's calls (the chain at https://sepolia.infura.io/… answered HTTP 429)", out)
        no_key(self, out + err)

    def test_the_keeper_traceback_is_redacted(self):
        node = FakeNode(fail=lambda m: RuntimeError(f"proxy said no to {URL} (POST {URL}/)"))
        code, out, err = run_main(["keeper", "info"], env_for(), node, entry=True)
        self.assertEqual(code, 1)
        self.assertIn("Traceback", err)
        self.assertIn("RuntimeError: proxy said no to https://sepolia.infura.io/…", err)
        no_key(self, out + err)

    def test_the_node_429_retried_then_failed(self):
        out = io.StringIO()
        env = {"ORACLE_RPC": URL, "ORACLE_RACE": RACE, "ORACLE_RPC_RETRIES": "3", "PATH": "/usr/bin:/bin"}
        node = FakeNode(fail=lambda m: http_error(429, "2"))
        with mock.patch("urllib.request.urlopen", side_effect=node), mock.patch("oracle.rpc.time.sleep"), \
                mock.patch.dict("os.environ", env, clear=True), contextlib.redirect_stdout(out):
            cli.load_env(env)
            rpc = cli.rpc_from_env()
            rpc.log = log = cli.node_log(KEEPER)
            try:
                rpc.block()
            except cli.Unavailable as e:
                log(f"node {KEEPER}: the chain isn't answering ({e}); trying again, nothing is lost")  # NodeV3.run's
            code = cli.main(["oracle", "info"])  # the command line's own line when the chain stays away
        text = out.getvalue()
        self.assertEqual(code, cli.EXIT_UNFINISHED)
        self.assertIn("eth_blockNumber: the chain at https://sepolia.infura.io/… answered HTTP 429; retry 3 of 3", text)
        self.assertIn("the chain isn't answering (the chain at https://sepolia.infura.io/… answered HTTP 429)", text)
        self.assertIn("oracle: the chain at https://sepolia.infura.io/… answered HTTP 429; the run didn't finish", text)
        no_key(self, text)

    def test_the_node_traceback_is_redacted(self):
        out, err = io.StringIO(), io.StringIO()
        env = {"ORACLE_RPC": URL, "ORACLE_RACE": RACE, "PATH": "/usr/bin:/bin"}
        node = FakeNode(fail=lambda m: urllib.error.URLError(f"no route to {URL}"))
        boom = FakeNode(fail=lambda m: ValueError(f"bad answer from {URL}"))
        with mock.patch("urllib.request.urlopen", side_effect=node), mock.patch("oracle.rpc.time.sleep"), \
                mock.patch.dict("os.environ", env, clear=True), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            self.assertEqual(cli.entry(["oracle", "info"]), cli.EXIT_UNFINISHED)  # a URL in the reason, caught
            with mock.patch("urllib.request.urlopen", side_effect=boom):
                self.assertEqual(cli.entry(["oracle", "info"]), 1)  # through Rpc, uncaught: the traceback
        self.assertIn("can't reach the chain at https://sepolia.infura.io/…: no route to https://sepolia.infura.io/…",
                      out.getvalue())
        self.assertIn("Traceback", err.getvalue())
        self.assertIn("oracle/rpc.py", err.getvalue())
        self.assertIn("ValueError: bad answer from https://sepolia.infura.io/…", err.getvalue())
        no_key(self, out.getvalue() + err.getvalue())

    def test_the_node_reads_the_rpc_url_from_a_secret(self):
        env = {"ORACLE_RPC_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:rpc-AbCdEf",
               "ORACLE_RACE": RACE, "PATH": "/usr/bin:/bin"}
        out = io.StringIO()
        with mock.patch("oracle.awssecret.get_secret", return_value=URL), \
                mock.patch("urllib.request.urlopen", side_effect=FakeNode(fail=lambda m: http_error(503))), \
                mock.patch("oracle.rpc.time.sleep"), mock.patch.dict("os.environ", env, clear=True), \
                contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["oracle", "info"]), cli.EXIT_UNFINISHED)
            import os

            self.assertEqual(os.environ["ORACLE_RPC"], URL)
        self.assertIn("https://sepolia.infura.io/…", out.getvalue())
        no_key(self, out.getvalue())
        self.assertIn((KEY, "…"), REDACT.secrets)


if __name__ == "__main__":
    unittest.main()
