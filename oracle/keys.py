"""Where a node's signing key lives (design D4). One interface, two providers:

- DstackKeys: inside a Phala dstack confidential VM, the guest agent derives the key (GetKey) and quotes the TDX report
  (GetQuote); the key never leaves the VM. Spoken over HTTP (the simulator's endpoint) or the agent's Unix socket, with
  the standard library. The Ethereum key is sha256 of the derived key material, as the SDK's `to_account_secure`.
- LocalDevKeys: INSECURE, for the local chain only. The key is forge's makeAddrAndKey("oracle<i>"), so it matches the
  loop's deployment (contracts/script/Loop.s.sol); anyone can derive it. Refused on any other chain.
- DevnetKeys: the private devnet's oracle keys (#93), handed to the node by scripts/oracle-run.sh --devnet from OpenBao
  (or anvil's public mnemonic with DEVNET_KEYS=insecure-local). Refused on any chain but the devnet's.
- EnvKeys: a validator's own key, from ORACLE_PRIVATE_KEY (ORACLE_KEYS=env; the validator kit, #104). Devnet only."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import socket
from dataclasses import dataclass

from . import crypto

LOCAL_CHAIN_IDS = {31337}  # anvil
DEVNET_CHAIN_ID = 7193  # the private devnet (scripts/devnet.sh, #93)
DSTACK_SOCKET = "/var/run/dstack.sock"


@dataclass(frozen=True)
class Quote:
    kind: str  # "dstack-tdx", "dstack-simulator" or "none-insecure-local"
    quote: str  # hex; empty when there is none
    report_data: str  # hex of the 64 bytes quoted (the receipt hash, zero-padded)


class KeyProvider:
    def address(self) -> str:
        raise NotImplementedError

    def sign(self, digest: bytes) -> bytes:
        raise NotImplementedError

    def quote(self, report_data: bytes) -> Quote:
        raise NotImplementedError

    def check_chain(self, chain_id: int) -> None:
        """Raise if this provider must not be used on `chain_id`."""

    def account_secret(self) -> int:
        """The key, for the node's own transactions (its usage reports, and the results it relays): in memory only,
        in this process (inside the CVM or enclave, for an attested node)."""
        return self._secret


class LocalDevKeys(KeyProvider):
    """INSECURE: a public test key. For anvil and the devnet only."""

    def __init__(self, index: int | None = None, secret: int | None = None, extra_chain_ids: set[int] | None = None):
        if (index is None) == (secret is None):
            raise ValueError("give an oracle index or a secret")
        self._secret = secret if secret is not None else int.from_bytes(crypto.keccak256(f"oracle{index}".encode()), "big")
        self._chains = LOCAL_CHAIN_IDS | (extra_chain_ids or set())

    def address(self) -> str:
        return crypto.address(self._secret)

    def sign(self, digest: bytes) -> bytes:
        return crypto.sign(self._secret, digest)

    def quote(self, report_data: bytes) -> Quote:
        return Quote("none-insecure-local", "", _pad64(report_data).hex())

    def check_chain(self, chain_id: int) -> None:
        if chain_id not in self._chains:
            raise RuntimeError(f"local test keys refused on chain {chain_id}: they are public; use dstack keys")


class DevnetKeys(KeyProvider):
    """A devnet oracle key, held in memory only for the run. For the private devnet (#93) alone: no attestation."""

    def __init__(self, secret: int):
        if not 1 <= secret < crypto.N:
            raise ValueError("not a valid key")
        self._secret = secret

    def address(self) -> str:
        return crypto.address(self._secret)

    def sign(self, digest: bytes) -> bytes:
        return crypto.sign(self._secret, digest)

    def quote(self, report_data: bytes) -> Quote:
        return Quote("none-devnet", "", _pad64(report_data).hex())

    def check_chain(self, chain_id: int) -> None:
        if chain_id != DEVNET_CHAIN_ID:
            raise RuntimeError(f"devnet keys refused on chain {chain_id}: they exist for the devnet ({DEVNET_CHAIN_ID})")


class EnvKeys(KeyProvider):
    """A validator's own key from the environment (ORACLE_KEYS=env, ORACLE_PRIVATE_KEY: the validator kit reads it
    from the operator's Secrets Manager into the run's process only). No attestation, so devnet chains only (rule 1)."""

    VAR = "ORACLE_PRIVATE_KEY"

    def __init__(self, env: dict | None = None):
        raw = (os.environ if env is None else env).get(self.VAR, "").strip()
        if not raw:
            raise RuntimeError(f"ORACLE_KEYS=env needs {self.VAR}")
        try:
            secret = int(raw[2:] if raw.startswith("0x") else raw, 16)
        except ValueError:
            raise RuntimeError(f"{self.VAR} isn't a hex private key") from None
        if not 1 <= secret < crypto.N:
            raise RuntimeError(f"{self.VAR} isn't a valid key")
        self._secret = secret

    def address(self) -> str:
        return crypto.address(self._secret)

    def sign(self, digest: bytes) -> bytes:
        return crypto.sign(self._secret, digest)

    def quote(self, report_data: bytes) -> Quote:
        return Quote("none-env", "", _pad64(report_data).hex())

    def check_chain(self, chain_id: int) -> None:
        if chain_id not in LOCAL_CHAIN_IDS | {DEVNET_CHAIN_ID}:
            raise RuntimeError(f"environment keys refused on chain {chain_id}: unattested, for the devnet only")


class DstackKeys(KeyProvider):
    """The dstack guest agent: `endpoint` is an http:// URL (the simulator, DSTACK_SIMULATOR_ENDPOINT) or a Unix socket
    path (the agent inside a CVM). `path` names the key; the same path in the same app gives the same key."""

    def __init__(self, path: str, endpoint: str | None = None, simulator: bool | None = None):
        self.endpoint = endpoint or os.environ.get("DSTACK_SIMULATOR_ENDPOINT") or DSTACK_SOCKET
        self.simulated = simulator if simulator is not None else self.endpoint != DSTACK_SOCKET
        derived = bytes.fromhex(self._rpc("/GetKey", {"path": path, "purpose": "pof-oracle-signing"})["key"]
                                .removeprefix("0x"))
        self._secret = int.from_bytes(hashlib.sha256(derived).digest(), "big") % crypto.N or 1

    def _rpc(self, method: str, body: dict) -> dict:
        payload = json.dumps(body).encode()
        if self.endpoint.startswith("http://"):
            host = self.endpoint.removeprefix("http://").rstrip("/")
            conn = http.client.HTTPConnection(host, timeout=30)
        else:
            conn = _UnixHTTPConnection(self.endpoint)
        try:
            conn.request("POST", method, payload, {"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = resp.read()
            if resp.status != 200:
                raise RuntimeError(f"dstack {method}: HTTP {resp.status}: {data[:200]!r}")
            return json.loads(data)
        finally:
            conn.close()

    def address(self) -> str:
        return crypto.address(self._secret)

    def sign(self, digest: bytes) -> bytes:
        return crypto.sign(self._secret, digest)

    def quote(self, report_data: bytes) -> Quote:
        rd = _pad64(report_data)
        out = self._rpc("/GetQuote", {"report_data": rd.hex()})
        return Quote("dstack-simulator" if self.simulated else "dstack-tdx", out.get("quote", ""), rd.hex())


def _pad64(data: bytes) -> bytes:
    if len(data) > 64:
        data = hashlib.sha256(data).digest()
    return data.ljust(64, b"\x00")


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("localhost", timeout=30)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self._path)
