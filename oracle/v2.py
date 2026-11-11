"""The v2 protocol as a node and pofctl's stub quorum speak it (proof-of-fix#85 tasks 5.2-5.7, #104): the verdict v2's
EIP-712 struct and its two uses (a submission's `Result`, a winner's `Merged`), the judges' signed `Usage` for the
meter (Fees.report), a seat's `Rotate` (the join flow), and the chain's v2 views: submissions with their draw seed, the
judges `Verdicts.drawn` names for one, the meter's reports and terms.

Every digest here is checked against the contracts by the end-to-end run (scripts/demo-e2e.sh: the contracts accept
the signatures) and against fixed encodings by tests/test_oracle_v2.py."""

from __future__ import annotations

from dataclasses import dataclass

from . import abi
from .crypto import checksum, keccak256, recover, word

VERDICT_TYPE = ("Verdict(bytes32 repo,bytes32 base,bytes32 fix,uint256 bounty,uint256 submission,uint8 tier,"
                "uint8 outcome,bytes32 receiptHash,bytes32 seed,bytes32 nonce)")
FEE_TYPE = "Fee(address to,uint256 amount)"
DOMAIN_TYPEHASH = keccak256(b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
VERDICT_TYPEHASH = keccak256(VERDICT_TYPE.encode())
RESULT_TYPEHASH = keccak256(("Result(Verdict verdict,Fee[] fees)" + FEE_TYPE + VERDICT_TYPE).encode())
MERGED_TYPEHASH = keccak256(("Merged(Verdict verdict,uint256 weight)" + VERDICT_TYPE).encode())
FEE_TYPEHASH = keccak256(FEE_TYPE.encode())
ACCEPT_TYPEHASH = keccak256(b"Accept(uint256 issue,uint256 weight,bytes32 nonce)")
USAGE_TYPEHASH = keccak256(b"Usage(uint256 submission,bytes32 receipt,uint64 input,uint64 cached,uint64 output,"
                           b"uint64 vcpuSeconds,uint64 gbSeconds,uint64 storageMb)")
ROTATE_TYPEHASH = keccak256(b"Rotate(uint256 seat,address key,bytes32 image,bytes32 attestationType,"
                            b"bytes32 attestation,bytes32 nonce)")

TIER_ISSUE = 1
ISSUE_JUDGES, ISSUE_QUORUM = 3, 2
NONE, PASS, FAIL = 0, 1, 2
OUTCOMES = ["None", "Pass", "Fail", "Duplicate", "Split", "TimedOut"]
STATES = ["None", "Open", "Won", "Merged", "Paid", "Refunded", "Unsolved"]
ZERO = b"\0" * 32
# The devnet's checker image and attestation type (contracts/script/DeployV2.s.sol, scripts/devnet.sh join-v2).
DEVNET_IMAGE = keccak256(b"devnet checker image")
NO_ATTESTATION = keccak256(b"none")

# RaceV2's views, as ABI tuples, and their field names.
SUBMISSION = ["(uint256,uint256,address,bytes32,address,uint256,uint8,bytes32,bool,bytes32,bytes32,bytes32)"]
SUBMISSION_FIELDS = ["bounty", "day", "solver", "commitment", "coin", "deposit", "outcome", "fix", "appealed", "base",
                     "receipt", "seed"]
BOUNTY = ["(uint256,uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,bool)"]
BOUNTY_FIELDS = ["issue", "state", "offerFrom", "locked", "lockBps", "idleSince", "attempting", "next", "winner",
                 "mergeBy", "epoch", "weight", "mergeWeight", "inflated"]
ISSUE = ["(bytes32,address,address,uint256,uint256,uint256,uint8)"]
ISSUE_FIELDS = ["repo", "reporter", "coin", "registration", "stake", "bounty", "state"]
USAGE = "(bytes32,uint64,uint64,uint64,uint64,uint64,uint64)"
REPORTS = [f"(address,address,uint256,{USAGE})[]"]
PROFILE = ["(bytes32,uint32,uint32,uint32)"]
HEAD = ["(bytes32,bytes32,uint256,uint256,uint256,bytes32)"]
HEAD_FIELDS = ["commit", "constitution", "movedAt", "bounty", "submission", "verdict"]
CAPS = ["(uint64,uint64,uint64,uint64,uint64,uint64)"]
VERDICT = "(bytes32,bytes32,bytes32,uint256,uint256,uint8,uint8,bytes32,bytes32,bytes32)"
COMMITTED = "Committed(uint256,uint256,address)"
CHARGED = "Charged(uint256,uint256,uint256)"


def b32(value) -> bytes:
    """bytes32 from bytes or a 0x hex string."""
    if isinstance(value, bytes):
        if len(value) != 32:
            raise ValueError("bytes32 needs 32 bytes")
        return value
    raw = bytes.fromhex(value[2:] if value.startswith("0x") else value)
    if len(raw) != 32:
        raise ValueError("bytes32 needs 32 bytes")
    return raw


def commit_word(sha: str) -> bytes:
    """A git commit as bytes32, as Heads keeps them: a SHA-1 left-aligned, a SHA-256 id as is."""
    raw = bytes.fromhex(sha.strip().lower())
    if len(raw) not in (20, 32):
        raise ValueError(f"not a commit id: {sha}")
    return raw.ljust(32, b"\0")


def domain(name: str, version: str, chain_id: int, contract: str) -> bytes:
    return keccak256(DOMAIN_TYPEHASH + keccak256(name.encode()) + keccak256(version.encode()) + word(chain_id)
                     + word(contract))


def race_domain(chain_id: int, race: str) -> bytes:
    return domain("proof-of-fix Race", "2", chain_id, race)


def verdicts_domain(chain_id: int, verdicts: str) -> bytes:
    return domain("proof-of-fix Verdicts", "2", chain_id, verdicts)


def fees_domain(chain_id: int, fees: str) -> bytes:
    return domain("proof-of-fix Fees", "2", chain_id, fees)


def typed(domain_separator: bytes, struct_hash: bytes) -> bytes:
    return keccak256(b"\x19\x01" + domain_separator + struct_hash)


# ---------- the verdict v2 ----------

@dataclass(frozen=True)
class Verdict:
    repo: bytes
    base: bytes
    fix: bytes
    bounty: int
    submission: int
    outcome: int
    receipt_hash: bytes
    seed: bytes
    nonce: bytes
    tier: int = TIER_ISSUE

    def as_tuple(self) -> tuple:
        return (self.repo, self.base, self.fix, self.bounty, self.submission, self.tier, self.outcome,
                self.receipt_hash, self.seed, self.nonce)

    def struct_hash(self) -> bytes:
        return keccak256(VERDICT_TYPEHASH + self.repo + self.base + self.fix + word(self.bounty)
                         + word(self.submission) + word(self.tier) + word(self.outcome) + self.receipt_hash
                         + self.seed + self.nonce)

    def to_json(self) -> dict:
        return {"repo": "0x" + self.repo.hex(), "base": "0x" + self.base.hex(), "fix": "0x" + self.fix.hex(),
                "bounty": self.bounty, "submission": self.submission, "tier": self.tier, "outcome": self.outcome,
                "receiptHash": "0x" + self.receipt_hash.hex(), "seed": "0x" + self.seed.hex(),
                "nonce": "0x" + self.nonce.hex()}

    @classmethod
    def from_json(cls, d: dict) -> "Verdict":
        return cls(b32(d["repo"]), b32(d["base"]), b32(d["fix"]), int(d["bounty"]), int(d["submission"]),
                   int(d["outcome"]), b32(d["receiptHash"]), b32(d["seed"]), b32(d["nonce"]), int(d.get("tier", 1)))


def fees_hash(fees=()) -> bytes:
    return keccak256(b"".join(keccak256(FEE_TYPEHASH + word(to) + word(amount)) for to, amount in fees))


def result_digest(race_domain_separator: bytes, v: Verdict, fees=()) -> bytes:
    """RaceV2.result's digest. With the meter (task 5.7) the judges sign an empty fee list."""
    return typed(race_domain_separator, keccak256(RESULT_TYPEHASH + v.struct_hash() + fees_hash(fees)))


def merged_digest(race_domain_separator: bytes, v: Verdict, weight: int) -> bytes:
    return typed(race_domain_separator, keccak256(MERGED_TYPEHASH + v.struct_hash() + word(weight)))


def verdict_nonce(kind: str, submission: int, bounty: int, outcome: int, receipt_hash: bytes, fix: bytes) -> bytes:
    """Every agreeing judge derives the same nonce for the same verdict, so their signatures combine (design D2)."""
    return keccak256(kind.encode() + word(submission) + word(bounty) + word(outcome) + receipt_hash + fix)


def receipts_hash(by_node: dict) -> bytes:
    """The verdict's receipt hash: keccak256 of the agreeing judges' receipt hashes (sha256), in node address order.
    Each judge's own receipt hash is in its signed usage report, so anyone can match the two."""
    ordered = sorted(by_node.items(), key=lambda kv: int(kv[0], 16))
    return keccak256(b"".join(bytes.fromhex(h[2:] if h.startswith("0x") else h) for _, h in ordered))


def ordered_signatures(digest: bytes, sigs) -> list:
    """Signatures sorted by their signer's address (the contracts want strictly increasing signers), one per signer."""
    by_signer = {}
    for s in sigs:
        raw = s if isinstance(s, bytes) else bytes.fromhex(s[2:] if s.startswith("0x") else s)
        by_signer[recover(digest, raw).lower()] = raw
    return [by_signer[k] for k in sorted(by_signer, key=lambda a: int(a, 16))]


# ---------- the meter's usage report ----------

@dataclass(frozen=True)
class Usage:
    receipt: bytes  # the judge's own receipt hash (sha256), as bytes32
    input: int  # tokens, cached ones included
    cached: int
    output: int
    vcpu_seconds: int
    gb_seconds: int
    storage_mb: int

    def as_tuple(self) -> tuple:
        return (self.receipt, self.input, self.cached, self.output, self.vcpu_seconds, self.gb_seconds,
                self.storage_mb)


def usage_digest(fees_domain_separator: bytes, submission: int, u: Usage) -> bytes:
    return typed(fees_domain_separator, keccak256(USAGE_TYPEHASH + word(submission) + u.receipt + word(u.input)
                                                  + word(u.cached) + word(u.output) + word(u.vcpu_seconds)
                                                  + word(u.gb_seconds) + word(u.storage_mb)))


def measured_usage(receipt_sha256: str, prompt: str, response: str, seconds: float, milli_vcpus: int,
                   memory_mb: int, stored_bytes: int, tokens: dict | None = None) -> Usage:
    """A check's usage as the node measured it: the judge backend's token counts (the provider's, when it reports
    them; else about 4 characters a token, the fake judge's), the sandbox's vCPU-seconds and GB-seconds at the
    repository's CI profile for the time the tests ran (rounded up, at least 1), and the receipt's storage."""
    tokens = tokens or {}
    inp = tokens.get("input_tokens")
    out = tokens.get("output_tokens")
    inp = int(inp) if inp is not None else max(1, (len(prompt) + 3) // 4)
    out = int(out) if out is not None else max(1, (len(response) + 3) // 4)
    cached = int(tokens.get("cached_tokens") or 0)
    secs = max(1, int(-(-seconds // 1)))
    vcpu = max(1, -(-secs * milli_vcpus // 1000))
    gb = max(1, -(-secs * memory_mb // 1024))
    storage = max(1, -(-stored_bytes // (1024 * 1024)))
    receipt = b32(receipt_sha256 if receipt_sha256.startswith("0x") else "0x" + receipt_sha256)
    return Usage(receipt, inp, min(cached, inp), out, vcpu, gb, storage)


# ---------- seats: the join ----------

def rotate_digest(verdicts_domain_separator: bytes, seat: int, key: str, nonce: bytes, image: bytes = DEVNET_IMAGE,
                  attestation_type: bytes = NO_ATTESTATION, attestation: bytes = ZERO) -> bytes:
    return typed(verdicts_domain_separator, keccak256(ROTATE_TYPEHASH + word(seat) + word(key) + image
                                                      + attestation_type + attestation + nonce))


# ---------- the chain's v2 views ----------

class Chain:
    """RaceV2 and the contracts it names (Verdicts, the meter), read over JSON-RPC (oracle.rpc.Rpc)."""

    def __init__(self, rpc, race: str) -> None:
        self.rpc, self.race = rpc, checksum(race)
        self.verdicts = checksum(rpc.view(race, "verdicts()", ["address"])[0])
        self.meter = checksum(rpc.view(race, "meter()", ["address"])[0])
        self._chain_id = None

    def chain_id(self) -> int:
        if self._chain_id is None:
            self._chain_id = self.rpc.chain_id()
        return self._chain_id

    def race_domain(self) -> bytes:
        return b32(self.rpc.view(self.race, "domainSeparator()", ["bytes32"])[0])

    def fees_domain(self) -> bytes:
        return b32(self.rpc.view(self.meter, "domainSeparator()", ["bytes32"])[0])

    def verdicts_domain(self) -> bytes:
        return b32(self.rpc.view(self.verdicts, "domainSeparator()", ["bytes32"])[0])

    def coin(self) -> str:
        return checksum(self.rpc.view(self.meter, "coin()", ["address"])[0])

    def submission(self, s: int) -> dict:
        return dict(zip(SUBMISSION_FIELDS, self.rpc.view(self.race, "submission(uint256)", SUBMISSION, s)[0]))

    def bounty(self, b: int) -> dict:
        return dict(zip(BOUNTY_FIELDS, self.rpc.view(self.race, "bounty(uint256)", BOUNTY, b)[0]))

    def issue(self, i: int) -> dict:
        return dict(zip(ISSUE_FIELDS, self.rpc.view(self.race, "issue(uint256)", ISSUE, i)[0]))

    def drawn(self, seed, bounty: int, submission: int) -> tuple:
        """(the judges drawn for the submission, the keys recused on the way): Verdicts.drawn on RaceV2's subject."""
        judges, recused = self.rpc.view(self.verdicts, "drawn(bytes32,uint256,uint256,address)",
                                        ["address[]", "address[]"], b32(seed), bounty, submission, self.race)
        return [checksum(a) for a in judges], [checksum(a) for a in recused]

    def keys(self) -> list:
        return [checksum(a) for a in self.rpc.view(self.verdicts, "keys()", ["address[]"])[0]]

    def is_oracle(self, key: str) -> bool:
        return self.rpc.view(self.verdicts, "isOracle(address)", ["bool"], key)[0]

    def reports(self, s: int) -> list:
        rows = self.rpc.view(self.meter, "reports(uint256)", REPORTS, s)[0]
        return [{"judge": checksum(j), "payee": checksum(p), "family": f, "usage": u} for j, p, f, u in rows]

    def profile(self, repo) -> dict:
        image, mv, mem, timeout = self.rpc.view(self.meter, "profileOf(bytes32)", PROFILE, b32(repo))[0]
        return {"image": image, "milliVcpus": mv, "memoryMb": mem, "timeoutSeconds": timeout}

    def owed(self, who: str, coin: str | None = None) -> int:
        return self.rpc.view(self.race, "owed(address,address)", ["uint256"], who, coin or self.coin())[0]

    def committed(self, from_block: int, to_block: int | None = None) -> list:
        topic = "0x" + keccak256(COMMITTED.encode()).hex()
        return [{"bounty": int(log["topics"][1], 16), "submission": int(log["topics"][2], 16),
                 "solver": checksum("0x" + log["topics"][3][-40:]), "block": int(log["blockNumber"], 16)}
                for log in self.rpc.logs(self.race, from_block, [topic], to_block)]

    def heads(self) -> str:
        """The head registry RaceV2 deployed (Heads)."""
        if getattr(self, "_heads", None) is None:
            self._heads = checksum(self.rpc.view(self.race, "heads()", ["address"])[0])
        return self._heads

    def head(self, repo) -> dict:
        """Heads.head(repo): the repository's canonical head on-chain (reverts UnknownRepo outside the registry)."""
        row = self.rpc.view(self.heads(), "head(bytes32)", HEAD, b32(repo))[0]
        return {k: (b32(v) if isinstance(v, (bytes, str)) else v) for k, v in zip(HEAD_FIELDS, row)}

    def charged(self, from_block: int = 0) -> dict:
        """submission -> (judges counted, the total charged), from the meter's Charged events."""
        topic = "0x" + keccak256(CHARGED.encode()).hex()
        out = {}
        for log in self.rpc.logs(self.meter, from_block, [topic]):
            judges, total = abi.decode(["uint256", "uint256"], abi.hexdata(log["data"]))
            out[int(log["topics"][1], 16)] = (judges, total)
        return out
