"""The node's cryptography (design D1): keccak-256, secp256k1 signatures as Ethereum makes them (RFC 6979 nonces,
low-s, v = 27 or 28), addresses, ABI words, and the EIP-712 digest of Race's `Result`.

The primitives come from vendored, pinned, pure-Python code (oracle/vendor, checked against its SHA256SUMS by
scripts/check.sh; re-created by scripts/oracle-vendor.sh):
- keccak-256: the Keccak team's reference implementation (XKCP CompactFIPS202, by Gilles Van Assche);
- secp256k1 signing, RFC 6979 nonces, low-s encoding and key recovery: python-ecdsa 0.19.2.
What stays here is Ethereum's glue: the address, v, and the EIP-712 struct encoding, which tests cross-check against
fixed vectors and the contract (OpenZeppelin's EIP712 and ECDSA) accepting the signatures (scripts/oracle-run.sh)."""

from __future__ import annotations

import hashlib
import os
import sys

_VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)  # the vendored copies win over anything installed

from ecdsa import SECP256k1, SigningKey, VerifyingKey  # noqa: E402  (python-ecdsa, vendored)
from ecdsa.util import sigdecode_string, sigencode_string_canonize  # noqa: E402
from keccak.CompactFIPS202 import Keccak  # noqa: E402  (XKCP reference, vendored)

N = SECP256k1.order


def keccak256(data: bytes) -> bytes:
    """Keccak-256 as Ethereum uses it: the original padding (delimiter 0x01), not FIPS 202 SHA3-256 (0x06)."""
    return bytes(Keccak(1088, 512, bytearray(data), 0x01, 32))


def checksum(addr: str) -> str:
    """EIP-55 mixed-case address."""
    hexpart = addr.lower()
    hexpart = hexpart[2:] if hexpart.startswith("0x") else hexpart
    h = keccak256(hexpart.encode()).hex()
    return "0x" + "".join(c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c for i, c in enumerate(hexpart))


def _address_of(vk: VerifyingKey) -> str:
    return checksum("0x" + keccak256(vk.to_string())[-20:].hex())  # to_string(): x || y, 64 bytes


def _signing_key(secret: int) -> SigningKey:
    if not 1 <= secret < N:
        raise ValueError("a valid key is required")
    return SigningKey.from_secret_exponent(secret, curve=SECP256k1, hashfunc=hashlib.sha256)


def address(secret: int) -> str:
    return _address_of(_signing_key(secret).get_verifying_key())


def _candidates(rs: bytes, digest: bytes) -> list:
    """The public keys r || s can come from: [the one with an even-y R (v = 27), the one with an odd-y R (v = 28)]."""
    try:
        return VerifyingKey.from_public_key_recovery_with_digest(
            rs, digest, SECP256k1, hashfunc=hashlib.sha256, sigdecode=sigdecode_string)
    except Exception as e:  # python-ecdsa raises its own errors for points off the curve
        raise ValueError("no key recovers: %s" % e) from e


def sign(secret: int, digest: bytes) -> bytes:
    """A 65-byte signature r || s || v over a 32-byte digest, low-s (the contract's ECDSA refuses high-s)."""
    if len(digest) != 32:
        raise ValueError("a 32-byte digest is required")
    sk = _signing_key(secret)
    rs = sk.sign_digest_deterministic(digest, hashfunc=hashlib.sha256, sigencode=sigencode_string_canonize)
    mine = sk.get_verifying_key().to_string()
    for i, vk in enumerate(_candidates(rs, digest)):
        if vk.to_string() == mine:
            return rs + bytes([27 + i])
    raise ValueError("the signature doesn't recover to its own key")


def recover(digest: bytes, sig: bytes) -> str:
    """The signer's address, or ValueError for a malformed or high-s signature."""
    if len(sig) != 65:
        raise ValueError("a signature is 65 bytes")
    r, s, v = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big"), sig[64]
    if not (1 <= r < N and 1 <= s <= N // 2 and v in (27, 28)):
        raise ValueError("malformed or high-s signature")
    return _address_of(_candidates(sig[:64], digest)[v - 27])


# ---------- ABI words and EIP-712 ----------

def word(value) -> bytes:
    """One ABI word: an int, an address string, or 32 bytes."""
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError("bytes32 needs 32 bytes")
        return value
    if isinstance(value, str):
        return int(value, 16).to_bytes(32, "big")
    return int(value).to_bytes(32, "big")


def h32(hexstr: str) -> bytes:
    raw = bytes.fromhex(hexstr[2:] if hexstr.startswith("0x") else hexstr)
    if len(raw) != 32:
        raise ValueError("expected 32 bytes")
    return raw


DOMAIN_TYPEHASH = keccak256(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
NAME_HASH = keccak256(b"proof-of-fix Race")
VERSION_HASH = keccak256(b"1")
FEE_TYPEHASH = keccak256(b"Fee(address to,uint256 amount)")
RESULT_TYPEHASH = keccak256(b"Result(uint256 submission,uint256 bounty,uint8 outcome,bytes32 fix,Fee[] fees,"
                            b"bytes32 nonce)Fee(address to,uint256 amount)")
PASS, FAIL = 1, 2


def domain_separator(chain_id: int, race: str) -> bytes:
    return keccak256(DOMAIN_TYPEHASH + NAME_HASH + VERSION_HASH + word(chain_id) + word(race))


def fees_hash(fees: list) -> bytes:
    return keccak256(b"".join(keccak256(FEE_TYPEHASH + word(to) + word(amount)) for to, amount in fees))


def result_digest(domain: bytes, submission: int, bounty: int, outcome: int, fix: bytes,
                  fees: list, nonce: bytes) -> bytes:
    """The digest Race's `result` checks: \\x19\\x01 || domain || hashStruct(Result)."""
    struct = keccak256(RESULT_TYPEHASH + word(submission) + word(bounty) + word(outcome) + fix + fees_hash(fees)
                       + nonce)
    return keccak256(b"\x19\x01" + domain + struct)


def result_nonce(submission: int, bounty: int, fix: bytes) -> bytes:
    """Design D2: every node derives the same nonce for the same verdict, so their signatures combine."""
    return keccak256(word(submission) + word(bounty) + fix)


def commitment(fix: bytes, salt: bytes, solver: str) -> bytes:
    """A sealed submission, as the contract's tests seal it: keccak256(abi.encode(fix, salt, solver))."""
    return keccak256(fix + salt + word(solver))
