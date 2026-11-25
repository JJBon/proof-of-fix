"""The wallet's gas limit and receipt polling (v3.1 polish VP6, VP7): the limit is max(estimate × 1.25 + 10,000,
gas_floor), and `poll_s` (the node's ORACLE_TX_POLL) is a constructor setting. A stub chain, no network."""

from __future__ import annotations

import unittest
from unittest import mock

from oracle import crypto, rpc
from oracle.rpc import Wallet, gas_limit

TO = crypto.checksum("0x" + "ab" * 20)


class Stub:
    """Answers a wallet's calls: an estimate, a nonce, a price, the send and a mined receipt."""

    def __init__(self, estimate: int) -> None:
        self.estimate = estimate

    def chain_id(self):
        return 31337

    def call(self, method, params=None):
        return {"eth_estimateGas": hex(self.estimate), "eth_getTransactionCount": "0x0", "eth_gasPrice": "0x1",
                "eth_sendRawTransaction": "0xabc",
                "eth_getTransactionReceipt": {"status": "0x1", "blockNumber": "0x1"}}[method]


class GasLimit(unittest.TestCase):
    def test_the_formula(self):
        self.assertEqual(gas_limit(21_000), 36_250)
        self.assertEqual(gas_limit(21_000, 600_000), 600_000)
        self.assertEqual(gas_limit(800_000, 600_000), 1_010_000)
        self.assertEqual(gas_limit(21_000, None), 36_250)

    def test_the_sent_transaction_carries_it(self):
        for floor, want in ((None, 36_250), (600_000, 600_000), (1_000, 36_250)):
            with mock.patch.object(rpc, "signed_legacy", wraps=rpc.signed_legacy) as signed:
                kw = {} if floor is None else {"gas_floor": floor}
                Wallet(Stub(21_000), 0x11).send(TO, "f()", **kw)
            self.assertEqual(signed.call_args.args[4], want)  # (secret, chain, nonce, price, gas, to, value, data)


class PollSetting(unittest.TestCase):
    def test_poll_s_is_a_constructor_setting(self):
        self.assertEqual(Wallet(Stub(1), 0x11, poll_s=4).poll_s, 4.0)
        self.assertEqual(Wallet(Stub(1), 0x11).poll_s, Wallet.poll_s)  # the class's default, which tests may set
        self.assertEqual(Wallet.poll_s, 0.4)


if __name__ == "__main__":
    unittest.main()
