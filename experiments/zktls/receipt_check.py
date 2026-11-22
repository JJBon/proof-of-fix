"""Checks a zkTLS receipt (proof-of-fix#135) without Rust or a network: pure Python and the repository's vendored
keccak-256 and secp256k1 (oracle/vendor, through oracle.crypto).

A receipt is what experiments/zktls/rust/pof_verify.rs exports from a TLSNotary (tlsn v0.1.0-alpha.15) presentation:
the notary's key and signature, the attestation's header and body (BCS-encoded), the hash openings and the revealed
transcript. This module redoes, step by step:

1. the notary's signature: secp256k1 "eth" scheme, ecrecover(keccak256(header)) == the notary key's address -- the
   same check a contract would make;
2. the header: version 0 and the Merkle root of the body's fields;
3. the body: every field hashed as H(domain || BCS(field)), the Merkle tree (rs_merkle's layout) and its root;
4. the connection: TLS version, time and transcript lengths, from the signed body;
5. the transcript: every revealed range opens a signed hash commitment, H(plaintext || blinder), and every byte not
   revealed is zero.

What it does not check: the server's certificate chain and its signature over the TLS key exchange (that the data came
from the named server). That needs X.509 and RSA/ECDSA verification of the server's certificates, which the pinned
Rust verifier does (pof_verify); the receipt's "server_name" is therefore only as good as that verifier's run.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from oracle import crypto  # noqa: E402  (vendored keccak-256 and python-ecdsa)
from ecdsa import SECP256k1, VerifyingKey  # noqa: E402  (vendored, put on sys.path by oracle.crypto)

SIG_SECP256K1ETH = 3
KEY_K256 = 1
HASH_SHA256, HASH_BLAKE3, HASH_KECCAK256 = 1, 2, 3
TLS_VERSIONS = ("V1_2", "V1_3")

# tlsn's domain separators: the first 16 bytes of blake3(the type's name as written in tlsn's source). They are
# protocol constants; the receipt carries them too and must agree.
DOMAINS = {
    "VerifyingKey": "aec37d45b99c4e4b637706b1e978a3eb",
    "ConnectionInfo": "6e317487904af460f6bba793610c9961",
    "ServerEphemKey": "23302af3213e5b0a44d3f7ba9cf33e93",
    "ServerCertCommitment": "d0f7107feb7eec1e5793d2e8a2b696f0",
    "Extension": "67ed567f312ca482b9f365cc271baa42",
    "TranscriptCommitment": "bd0ab9ac6ea93ebda2500e8769e63a9e",
}


class ReceiptError(ValueError):
    pass


def _hash(alg: int, data: bytes) -> bytes:
    if alg == HASH_SHA256:
        return hashlib.sha256(data).digest()
    if alg == HASH_KECCAK256:
        return crypto.keccak256(data)
    raise ReceiptError("hash algorithm %d isn't supported without Rust (BLAKE3 needs a vendored implementation)" % alg)


class _Reader:
    """A BCS reader: little-endian fixed-width integers, ULEB128 lengths and enum tags."""

    def __init__(self, data: bytes):
        self.data, self.at = data, 0

    def take(self, n: int) -> bytes:
        if self.at + n > len(self.data):
            raise ReceiptError("truncated BCS data")
        out = self.data[self.at:self.at + n]
        self.at += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return int.from_bytes(self.take(4), "little")

    def u64(self) -> int:
        return int.from_bytes(self.take(8), "little")

    def uleb(self) -> int:
        shift = value = 0
        while True:
            b = self.u8()
            value |= (b & 0x7F) << shift
            if not b & 0x80:
                return value
            shift += 7

    def vec(self) -> bytes:
        return self.take(self.uleb())

    def typed_hash(self) -> tuple[int, bytes]:
        return self.u8(), self.vec()

    def done(self) -> bool:
        return self.at == len(self.data)


def parse_header(header: bytes) -> dict:
    r = _Reader(header)
    uid, version = r.take(16), r.u32()
    alg, root = r.typed_hash()
    if not r.done():
        raise ReceiptError("trailing bytes in the header")
    return {"id": uid.hex(), "version": version, "root_alg": alg, "root": root}


def parse_body(body: bytes) -> list[dict]:
    """The body's fields in order: {"id", "kind", "bcs" (the field's data, as hashed), plus decoded values}."""
    r = _Reader(body)
    fields = []

    def field(kind: str, decode) -> None:
        fid = r.u32()
        start = r.at
        value = decode()
        fields.append({"id": fid, "kind": kind, "bcs": body[start:r.at], **value})

    field("VerifyingKey", lambda: {"key_alg": r.u8(), "key": r.vec()})

    def conn():
        time, tag = r.u64(), r.uleb()
        if tag >= len(TLS_VERSIONS):
            raise ReceiptError("unknown TLS version tag %d" % tag)
        return {"time": time, "tls_version": TLS_VERSIONS[tag], "sent_len": r.u32(), "recv_len": r.u32()}

    field("ConnectionInfo", conn)
    field("ServerEphemKey", lambda: {"key_type": r.uleb(), "server_key": r.vec()})
    field("ServerCertCommitment", lambda: dict(zip(("cert_alg", "cert_hash"), r.typed_hash())))
    for _ in range(r.uleb()):
        field("Extension", lambda: {"ext_id": r.vec(), "ext_value": r.vec()})

    def commitment():
        if r.uleb() != 0:
            raise ReceiptError("only plaintext-hash transcript commitments are known")
        direction = ("Sent", "Received")[r.uleb()]
        ranges = [(r.u64(), r.u64()) for _ in range(r.uleb())]
        alg, digest = r.typed_hash()
        return {"direction": direction, "ranges": ranges, "alg": alg, "hash": digest}

    for _ in range(r.uleb()):
        field("TranscriptCommitment", commitment)
    if not r.done():
        raise ReceiptError("trailing bytes in the body")
    return fields


def merkle_root(alg: int, leaves: list[bytes]) -> bytes:
    """rs_merkle's root: pairs are hashed as H(left || right); an odd node at the end of a layer moves up as is."""
    if not leaves:
        raise ReceiptError("an empty tree has no root")
    layer = list(leaves)
    while len(layer) > 1:
        layer = [_hash(alg, layer[i] + layer[i + 1]) if i + 1 < len(layer) else layer[i] for i in range(0, len(layer), 2)]
    return layer[0]


def notary_address(sec1: bytes) -> str:
    vk = VerifyingKey.from_string(sec1, curve=SECP256k1)  # accepts the compressed form
    return crypto.checksum("0x" + crypto.keccak256(vk.to_string())[-20:].hex())


def check(receipt: dict) -> dict:
    """Checks a receipt; returns what it proves, or raises ReceiptError."""
    if receipt.get("format") != "pof-zktls-receipt/1":
        raise ReceiptError("unknown receipt format")
    for kind, value in DOMAINS.items():
        if receipt["domains"].get(kind) != value:
            raise ReceiptError("domain separator for %s differs from tlsn's" % kind)

    header = bytes.fromhex(receipt["header_bcs"])
    sig = receipt["signature"]
    key = receipt["notary_key"]
    if sig["alg"] != SIG_SECP256K1ETH or key["alg"] != KEY_K256:
        raise ReceiptError("only secp256k1eth signatures by k256 keys are checked here")
    signer = notary_address(bytes.fromhex(key["sec1"]))
    try:
        recovered = crypto.recover(crypto.keccak256(header), bytes.fromhex(sig["data"]))
    except ValueError as e:
        raise ReceiptError("bad notary signature: %s" % e) from e
    if recovered != signer:
        raise ReceiptError("the signature recovers %s, not the notary's %s" % (recovered, signer))

    h = parse_header(header)
    if h["version"] != 0:
        raise ReceiptError("unknown attestation version %d" % h["version"])
    fields = parse_body(bytes.fromhex(receipt["body_bcs"]))
    leaves = [_hash(h["root_alg"], bytes.fromhex(DOMAINS[f["kind"]]) + f["bcs"]) for f in sorted(fields, key=lambda f: f["id"])]
    if merkle_root(h["root_alg"], leaves) != h["root"]:
        raise ReceiptError("the body doesn't match the signed header's Merkle root")

    by_kind = {}
    for f in fields:
        by_kind.setdefault(f["kind"], []).append(f)
    if by_kind["VerifyingKey"][0]["key"] != bytes.fromhex(key["sec1"]):
        raise ReceiptError("the body names a different notary key")
    conn = by_kind["ConnectionInfo"][0]

    sent = bytes.fromhex(receipt["sent"]["bytes"])
    recv = bytes.fromhex(receipt["recv"]["bytes"])
    if (len(sent), len(recv)) != (conn["sent_len"], conn["recv_len"]):
        raise ReceiptError("transcript lengths differ from the signed ones")
    data = {"Sent": sent, "Received": recv}
    authed = {"Sent": [0] * len(sent), "Received": [0] * len(recv)}
    commitments = {(c["direction"], tuple(c["ranges"])): c for c in by_kind.get("TranscriptCommitment", [])}
    for o in receipt["openings"]:
        ranges = tuple((a, b) for a, b in o["ranges"])
        c = commitments.get((o["direction"], ranges))
        if c is None or c["alg"] != o["alg"]:
            raise ReceiptError("an opening has no matching signed commitment")
        plaintext = b"".join(data[o["direction"]][a:b] for a, b in ranges)
        if _hash(o["alg"], plaintext + bytes.fromhex(o["blinder"])) != c["hash"]:
            raise ReceiptError("revealed %s bytes don't match their signed commitment" % o["direction"].lower())
        for a, b in ranges:
            for i in range(a, b):
                authed[o["direction"]][i] = 1
    for direction, key_ in (("Sent", "sent"), ("Received", "recv")):
        claimed = {i for a, b in receipt[key_]["authed"] for i in range(a, b)}
        opened = {i for i, v in enumerate(authed[direction]) if v}
        if claimed != opened:
            raise ReceiptError("the %s bytes claimed as revealed aren't exactly the opened ones" % key_)
        if any(data[direction][i] for i in range(len(data[direction])) if i not in opened):
            raise ReceiptError("hidden %s bytes must be zero in a receipt" % key_)

    return {
        "notary": signer,
        "attestation_id": h["id"],
        "root": h["root"].hex(),
        "tls_version": conn["tls_version"],
        "time": conn["time"],
        "sent": sent,
        "recv": recv,
        "sent_revealed": sum(authed["Sent"]),
        "recv_revealed": sum(authed["Received"]),
        "server_name_unchecked": receipt["server_name"],
    }


def main(argv: list[str]) -> int:
    for path in argv:
        with open(path, encoding="utf-8") as f:
            out = check(json.load(f))
        print("%s: signed by %s, %s, %d/%d sent and %d/%d received bytes revealed" % (
            path, out["notary"], out["tls_version"], out["sent_revealed"], len(out["sent"]),
            out["recv_revealed"], len(out["recv"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
