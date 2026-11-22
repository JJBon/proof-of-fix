"""Signing a transaction as Ethereum expects it: RLP, and a legacy transaction with EIP-155 replay protection (the
chain id is in the signature, so a devnet transaction can't be replayed on another chain). Keys sign through the
oracle node's vendored, pinned secp256k1 code (oracle/crypto.py)."""

from __future__ import annotations

from .crypto import keccak256, sign


def _int(value: int) -> bytes:
    return b"" if value == 0 else value.to_bytes((value.bit_length() + 7) // 8, "big")


def rlp(item) -> bytes:
    """RLP of bytes, an int (big-endian, no leading zeros) or a list of those."""
    if isinstance(item, int):
        item = _int(item)
    if isinstance(item, (bytes, bytearray)):
        item = bytes(item)
        if len(item) == 1 and item[0] < 0x80:
            return item
        return _length(len(item), 0x80) + item
    if isinstance(item, list):
        body = b"".join(rlp(x) for x in item)
        return _length(len(body), 0xC0) + body
    raise TypeError(f"can't RLP {type(item).__name__}")


def _length(n: int, offset: int) -> bytes:
    if n < 56:
        return bytes([offset + n])
    raw = _int(n)
    return bytes([offset + 55 + len(raw)]) + raw


def _address(to: str | None) -> bytes:
    if not to:
        return b""
    raw = bytes.fromhex(to[2:] if to.startswith("0x") else to)
    if len(raw) != 20:
        raise ValueError(f"not an address: {to}")
    return raw


def signed_legacy(secret: int, chain_id: int, nonce: int, gas_price: int, gas: int, to: str | None, value: int,
                  data: bytes) -> bytes:
    """The raw signed transaction (EIP-155): sign keccak(rlp([nonce, gasPrice, gas, to, value, data, chainId, 0, 0]))
    and send rlp([..., v, r, s]) with v = recovery id + 35 + 2 * chainId."""
    fields = [nonce, gas_price, gas, _address(to), value, data]
    digest = keccak256(rlp(fields + [chain_id, 0, 0]))
    sig = sign(secret, digest)
    r, s, recovery = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big"), sig[64] - 27
    return rlp(fields + [recovery + 35 + 2 * chain_id, r, s])
