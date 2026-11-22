"""The node's view of the chain over JSON-RPC (standard library): the chain ID, the contract's oracle set and quorum, its
EIP-712 domain, a submission's sealed commitment, and the `Committed` events a node watches. Reads only: relaying is the
aggregator's job (any account can relay; the contract checks the signatures)."""

from __future__ import annotations

from . import crypto
from .rpc import Rpc as _Rpc

SUBMISSION = "submission(uint256)"  # (bounty, day, solver, commitment, coin, deposit, outcome, fix, appealed)
COMMITTED = "Committed(uint256,uint256,address)"


def selector(sig: str) -> bytes:
    return crypto.keccak256(sig.encode())[:4]


class Rpc(_Rpc):
    """The shared JSON-RPC client (oracle/rpc.py: API-key headers, URL user info as HTTP Basic), with v1's names."""

    def call_raw(self, method: str, params: list):
        return self.call(method, params)


def _words(data: bytes) -> list[bytes]:
    return [data[i:i + 32] for i in range(0, len(data), 32)]


class Race:
    def __init__(self, rpc: Rpc, address: str):
        self.rpc, self.address = rpc, address

    def _call(self, sig: str, *args) -> bytes:
        return self.rpc.eth_call(self.address, selector(sig) + b"".join(crypto.word(a) for a in args))

    def domain_separator(self) -> bytes:
        return self._call("domainSeparator()")

    def quorum(self) -> int:
        return int.from_bytes(self._call("quorum()"), "big")

    def oracle_keys(self) -> list[str]:
        w = _words(self._call("oracleKeys()"))
        n = int.from_bytes(w[1], "big")  # w[0] is the offset of the dynamic array
        return [crypto.checksum("0x" + w[2 + i][12:].hex()) for i in range(n)]

    def submission(self, sid: int) -> dict:
        w = _words(self._call(SUBMISSION, sid))
        return {"bounty": int.from_bytes(w[0], "big"), "solver": crypto.checksum("0x" + w[2][12:].hex()),
                "commitment": "0x" + w[3].hex(), "outcome": int.from_bytes(w[6], "big"), "fix": "0x" + w[7].hex()}

    def committed_since(self, from_block: int) -> list[dict]:
        """The submissions sealed since `from_block`: what a node watches for."""
        topic = "0x" + crypto.keccak256(COMMITTED.encode()).hex()
        logs = self.rpc.call_raw("eth_getLogs", [{"address": self.address, "topics": [topic],
                                                  "fromBlock": hex(from_block), "toBlock": "latest"}])
        return [{"bounty": int(log["topics"][1], 16), "submission": int(log["topics"][2], 16),
                 "solver": crypto.checksum("0x" + log["topics"][3][-40:]), "block": int(log["blockNumber"], 16)}
                for log in logs]
