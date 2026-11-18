"""The v3 protocol as a validator's node speaks it (proof-of-fix#139, task 4.1 of #132, on #138's contracts): the
registry's signed registration and statements (a seal, a reveal, a receipt's hash, a usage report), the receipt's
on-chain form, and the chain's v3 views: RaceV3 and the contracts it names (Panels, FeesV3, Validators, the pool).

v3 has no quorum signature: each drawn judge posts its own seal, reveal and receipt to Panels, each signed by its key
as a registry `Statement(subject, content)`, and Panels counts the reveals. Two contents signed for one subject are
equivocation, so a node signs one seal, one reveal, one receipt and one usage report per seat, and keeps what it
signed on disk (oracle/rounds.py).

Every digest here is checked against the contracts' sources by tests/test_oracle_v3.py (the type strings and the
view structs), and against the deployed contracts by the local-chain run (scripts/node-v3-e2e.sh: Panels, Validators
and RaceV3 accept the node's signatures)."""

from __future__ import annotations

from dataclasses import dataclass

from . import abi
from .crypto import checksum, keccak256, word
from .v2 import DOMAIN_TYPEHASH, Usage, b32, commit_word, typed  # noqa: F401 (Usage and b32 are v3's too)

REGISTRATION_TYPE = ("Registration(address key,address operator,bytes32 proofType,bytes32 teeType,uint8 level,"
                     "bytes32 attestation,bytes32 image,bytes32 host,bytes32 family,uint32 firmware)")
STATEMENT_TYPE = "Statement(bytes32 subject,bytes32 content)"
RECEIPT_TYPE = ("Receipt(bytes32 proofType,bytes32 notary,bytes32 model,bytes32 weights,bytes32 image,bytes32 seed,"
                "bytes32 prompt,bytes32 answer,bytes32 tests,bytes32 proof)")
REGISTRATION_TYPEHASH = keccak256(REGISTRATION_TYPE.encode())
STATEMENT_TYPEHASH = keccak256(STATEMENT_TYPE.encode())
RECEIPT_TYPEHASH = keccak256(RECEIPT_TYPE.encode())
SEAL_TAG = keccak256(b"proof-of-fix v3 seal")
REVEAL_TAG = keccak256(b"proof-of-fix v3 reveal")
RECEIPT_TAG = keccak256(b"proof-of-fix v3 receipt")
USAGE_TAG = keccak256(b"proof-of-fix v3 usage")
PROOF_TEE, PROOF_ZKTLS, PROOF_SIMULATED = keccak256(b"tee"), keccak256(b"zktls"), keccak256(b"simulated")
PROOFS = {"tee": PROOF_TEE, "zktls": PROOF_ZKTLS, "simulated": PROOF_SIMULATED}
LEVEL_A, LEVEL_B, LEVEL_C = 1, 2, 3
K_MAX = 7
ZERO = b"\0" * 32

# Panels' enums (PanelsBase.sol) and the registry's (IValidators.sol), in their declared order.
STATUS = ["None", "Sealed", "Waiting", "Judging", "Held", "Window", "Final", "Withdrawn", "Expired"]
SEALED, WAITING, JUDGING, HELD, WINDOW, FINAL = 1, 2, 3, 4, 5, 6
KINDS = ["Counted", "Shadow", "Audit", "Challenge"]
COUNTED, SHADOW, AUDIT, CHALLENGE = 0, 1, 2, 3
STATES = ["None", "Candidate", "Active", "Leaving", "Exited"]
CANDIDATE, ACTIVE, LEAVING, EXITED = 1, 2, 3, 4

# The views' structs as ABI tuples, and their field names (tests/test_oracle_v3.py rebuilds both from the sources).
SNAP = "(uint64,uint32,uint32,uint64)"
PANELS_SUBMISSION = (f"(bytes32,uint128,uint64,uint8,uint8,uint8,uint8,bool,bool,bool,{SNAP},uint64,uint64,uint64,"
                     f"uint64,uint64,uint64,uint8,uint8,uint8,bool,bool,bool,uint64,uint64,uint64,{SNAP},{SNAP},"
                     "address,address)")
PANELS_SUBMISSION_FIELDS = ["commitment", "bounty", "seedBlock", "status", "tier", "k", "level", "pass",
                            "heldAtCount", "teeOnly", "snap", "waitEpoch", "finalAt", "pid", "shadowPid",
                            "frozenLeft", "auditBlock", "auditsDue", "auditsDrawn", "auditsDone", "auditDecided",
                            "challengeOpen", "lastUpheld", "challengeBlock", "challengeEpoch", "challengePid",
                            "auditSnap", "challengeSnap", "challenger", "author"]
PANEL = f"(uint256,bytes32,uint64,uint64,uint32,uint8,uint8,uint8,uint8,uint8,uint8,bool,uint8,bool,bool,uint64,{SNAP})"
PANEL_FIELDS = ["id", "seed", "sealBy", "revealBy", "counter", "k", "seats", "nSealed", "done", "passes", "level",
                "counted", "kind", "closed", "scored", "ex", "snap"]
SEAT = "(address,uint8,bool,bool,bool,bool,uint8,bytes32,bytes32)"
SEAT_FIELDS = ["key", "level", "hasSeal", "revealed", "receipted", "vote", "mask", "seal", "receipt"]
VALIDATOR = ("(address,uint8,uint8,bool,uint8,address,uint64,bytes32,bytes32,bytes32,bytes32,bytes32,bytes32,uint128,"
             "uint128,uint32,uint32,uint64,uint32,uint32)")
VALIDATOR_FIELDS = ["key", "level", "state", "genesis", "suspensions", "operator", "leftAt", "proofType", "teeType",
                    "attestation", "image", "host", "family", "bond", "slashed", "openVerdicts", "openChallenges",
                    "registeredAt", "firmware", "reattestations"]
REGISTRATION = "(address,address,bytes32,bytes32,uint8,bytes32,bytes32,bytes32,bytes32,uint32)"
RACE_ISSUE = "(bytes32,address,uint256,uint256,uint256,uint256,uint8,bool)"
RACE_ISSUE_FIELDS = ["repo", "reporter", "registration", "stake", "bounty", "check", "state", "hidden"]
RACE_BOUNTY = "(uint256,uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)"
RACE_BOUNTY_FIELDS = ["issue", "state", "offerFrom", "locked", "lockBps", "idleSince", "attempting", "next", "winner",
                      "mergeBy", "epoch", "pledges"]
RACE_SUBMISSION = ("(uint256,uint256,uint256,address,bytes32,uint256,uint256,uint256,uint256,uint8,bool,bool,bool,"
                   "bytes32)")
RACE_SUBMISSION_FIELDS = ["bounty", "issue", "day", "solver", "commitment", "deposit", "charged", "judged", "pledges",
                          "outcome", "appealed", "paid", "done", "fix"]
RACE_CONFIG = "(address,address," + ",".join(["uint256"] * 14) + ")"
RACE_CONFIG_FIELDS = ["infrastructure", "insurance", "registrationFee", "issueStake", "attemptFee", "evaluationFee",
                      "appealFee", "challengeStake", "startPriceBps", "riseBpsPerDay", "finderFeeBps", "idleDays",
                      "resultDays", "mergeDays", "releaseEveryDays", "instalments"]
USAGE = "(bytes32,uint64,uint64,uint64,uint64,uint64,uint64)"
PROFILE = "(bytes32,uint32,uint32,uint32)"

SEATED = "Seated(uint256,uint256,address,uint256)"
COMMITTED = "Committed(uint256,uint256,address)"
REGISTERED = "Registered(uint256,address,uint256)"


def name_id(name: str) -> bytes:
    """A name as the bytes32 the contracts keep: keccak256 of it (a model family such as "anthropic/claude", D19; a
    TEE type such as "intel-tdx"; a host). A 0x value of 32 bytes is taken as it is."""
    if name.startswith("0x") and len(name) == 66:
        return b32(name)
    return keccak256(name.encode())


def address_word(addr: str) -> bytes:
    """An address as a bytes32 (a zkTLS notary in a receipt)."""
    return word(addr)


# ---------- the registry's domain and statements ----------

def registry_domain(chain_id: int, registry: str) -> bytes:
    return keccak256(DOMAIN_TYPEHASH + keccak256(b"proof-of-fix Validators") + keccak256(b"3") + word(chain_id)
                     + word(registry))


def statement_digest(domain: bytes, subject: bytes, content: bytes) -> bytes:
    """What a key signs for a statement on a subject (`Validators.statementDigest`)."""
    return typed(domain, keccak256(STATEMENT_TYPEHASH + subject + content))


def subject_of(tag: bytes, contract: str, pid: int, key: str) -> bytes:
    """A seat's subject: keccak256(abi.encode(tag, the contract that defines it, the panel, the key)). Panels defines
    the seal's, the reveal's and the receipt's; RaceV3 the usage report's."""
    return keccak256(tag + word(contract) + word(pid) + word(key))


def commitment_of(panels: str, pid: int, key: str, vote: bool, mask: int, salt: bytes) -> bytes:
    """What a judge seals (`Panels.commitmentOf`): its vote, its mask and a secret salt, bound to the panel and key."""
    return keccak256(word(panels) + word(pid) + word(key) + word(1 if vote else 0) + word(mask) + salt)


def reveal_content(vote: bool, mask: int, salt: bytes) -> bytes:
    return keccak256(word(1 if vote else 0) + word(mask) + salt)


def usage_content(u: Usage) -> bytes:
    return keccak256(u.receipt + word(u.input) + word(u.cached) + word(u.output) + word(u.vcpu_seconds)
                     + word(u.gb_seconds) + word(u.storage_mb))


def fix_commitment(fix: bytes, base: bytes, salt: bytes, solver: str) -> bytes:
    """A sealed fix in v3: keccak256(abi.encode(fix, base, salt, solver)), so the claim proves the base judged."""
    return keccak256(fix + base + salt + word(solver))


# ---------- the registration ----------

@dataclass(frozen=True)
class Registration:
    key: str
    operator: str
    proof_type: bytes
    tee_type: bytes
    level: int
    attestation: bytes
    image: bytes
    host: bytes
    family: bytes
    firmware: int

    def as_tuple(self) -> tuple:
        return (self.key, self.operator, self.proof_type, self.tee_type, self.level, self.attestation, self.image,
                self.host, self.family, self.firmware)

    def digest(self, domain: bytes) -> bytes:
        return typed(domain, keccak256(REGISTRATION_TYPEHASH + word(self.key) + word(self.operator) + self.proof_type
                                       + self.tee_type + word(self.level) + self.attestation + self.image + self.host
                                       + self.family + word(self.firmware)))


# ---------- the receipt's on-chain form ----------

RECEIPT_FIELDS = ("proofType", "notary", "model", "weights", "image", "seed", "prompt", "answer", "tests", "proof")


@dataclass(frozen=True)
class Receipt:
    """What a receipt names on-chain (IValidators.Receipt, D11): a counted verdict posts `hash()` of it."""
    proof_type: bytes
    notary: bytes  # zkTLS: the notary that signed the proof; 0 for a TEE
    model: bytes
    weights: bytes  # 0 where not public
    image: bytes
    seed: bytes
    prompt: bytes
    answer: bytes
    tests: bytes
    proof: bytes  # the proof bytes (a TEE quote or a zkTLS proof), hashed

    def words(self) -> tuple:
        return (self.proof_type, self.notary, self.model, self.weights, self.image, self.seed, self.prompt,
                self.answer, self.tests, self.proof)

    def hash(self) -> bytes:
        """`Validators.receiptHash`: keccak256(abi.encode(RECEIPT_TYPEHASH, receipt))."""
        return keccak256(RECEIPT_TYPEHASH + b"".join(self.words()))

    def to_json(self) -> dict:
        return {name: "0x" + w.hex() for name, w in zip(RECEIPT_FIELDS, self.words())}

    @classmethod
    def from_json(cls, d: dict) -> "Receipt":
        return cls(*(b32(d[name]) for name in RECEIPT_FIELDS))


# ---------- the chain's v3 views ----------

def _named(fields: list, row) -> dict:
    return dict(zip(fields, row))


class Chain:
    """RaceV3 and the contracts it names, read over JSON-RPC (oracle.rpc.Rpc). The node's writes go through its
    wallet (oracle/node_v3.py) and the `onchain` transport (oracle/transport.py)."""

    version = 3

    def __init__(self, rpc, race: str) -> None:
        self.rpc, self.race = rpc, checksum(race)
        panels, fees, pool, registry, heads, coin, start = rpc.view(
            race, "contracts()", ["address", "address", "address", "address", "address", "address", "uint256"])
        self.panels, self.fees, self.pool = checksum(panels), checksum(fees), checksum(pool)
        self.registry, self.heads, self._coin, self.start = checksum(registry), checksum(heads), checksum(coin), start
        self._chain_id = self._domain = None

    def chain_id(self) -> int:
        if self._chain_id is None:
            self._chain_id = self.rpc.chain_id()
        return self._chain_id

    def coin(self) -> str:
        return self._coin

    def domain(self) -> bytes:
        """The registry's EIP-712 domain, read from it and checked, so a node can't sign for the wrong registry."""
        if self._domain is None:
            d = b32(self.rpc.view(self.registry, "domainSeparator()", ["bytes32"])[0])
            if d != registry_domain(self.chain_id(), self.registry):
                raise RuntimeError("the registry's EIP-712 domain isn't v3's: refusing to sign")
            self._domain = d
        return self._domain

    def now(self) -> int:
        """The chain's time: the latest block's timestamp. Panels' windows are in it, not in this machine's clock."""
        return int(self.rpc.call("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)

    def block(self) -> int:
        return self.rpc.block()

    # ----- Panels -----

    def panel_count(self) -> int:
        return self.rpc.view(self.panels, "panelCount()", ["uint256"])[0]

    def panel(self, pid: int) -> dict:
        return _named(PANEL_FIELDS, self.rpc.view(self.panels, "panel(uint256)", [PANEL], pid)[0])

    def seat(self, pid: int, slot: int) -> dict:
        s = _named(SEAT_FIELDS, self.rpc.view(self.panels, "seat(uint256,uint256)", [SEAT], pid, slot)[0])
        s["key"] = checksum(s["key"])
        return s

    def judges(self, pid: int) -> list:
        """The panel's seated validators in seat order ("" for an empty seat)."""
        keys = self.rpc.view(self.panels, "judges(uint256)", ["address[]"], pid)[0]
        return ["" if int(k, 16) == 0 else checksum(k) for k in keys]

    def verdict(self, s: int) -> dict:
        """Panels' record of submission `s`: its status, k, level, outcome, panels, audits and challenge."""
        return _named(PANELS_SUBMISSION_FIELDS,
                      self.rpc.view(self.panels, "submission(uint256)", [PANELS_SUBMISSION], s)[0])

    def seated(self, key: str, from_block: int, to_block: int | None = None) -> list:
        """The seats `key` was given: Panels' Seated(pid, slot, key, sealBy) events naming it."""
        topics = ["0x" + keccak256(SEATED.encode()).hex(), None, "0x" + word(key).hex()]
        out = []
        for log in self.rpc.logs(self.panels, from_block, topics, to_block):
            slot, seal_by = abi.decode(["uint256", "uint256"], abi.hexdata(log["data"]))
            out.append({"pid": int(log["topics"][1], 16), "slot": slot, "sealBy": seal_by,
                        "block": int(log["blockNumber"], 16)})
        return out

    # ----- the registry -----

    def validator(self, key: str) -> dict:
        v = _named(VALIDATOR_FIELDS, self.rpc.view(self.registry, "validator(address)", [VALIDATOR], key)[0])
        v["key"], v["operator"] = checksum(v["key"]), checksum(v["operator"])
        return v

    def epoch(self) -> int:
        """Bumped on every change to the registry."""
        return self.rpc.view(self.registry, "epoch()", ["uint256"])[0]

    def is_active(self, key: str) -> bool:
        return self.rpc.view(self.registry, "isActive(address)", ["bool"], key)[0]

    def registration_digest(self, r: Registration) -> bytes:
        return b32(self.rpc.view(self.registry, f"registrationDigest({REGISTRATION})", ["bytes32"], r.as_tuple())[0])

    def bond_floor(self) -> int:
        return self.rpc.view(self.registry, "BOND_FLOOR()", ["uint256"])[0]

    # ----- RaceV3 -----

    def submission(self, s: int) -> dict:
        sub = _named(RACE_SUBMISSION_FIELDS,
                     self.rpc.view(self.race, "submission(uint256)", [RACE_SUBMISSION], s)[0])
        sub["solver"] = checksum(sub["solver"])
        return sub

    def bounty(self, b: int) -> dict:
        return _named(RACE_BOUNTY_FIELDS, self.rpc.view(self.race, "bounty(uint256)", [RACE_BOUNTY], b)[0])

    def issue(self, i: int) -> dict:
        row = _named(RACE_ISSUE_FIELDS, self.rpc.view(self.race, "issue(uint256)", [RACE_ISSUE], i)[0])
        row["reporter"] = checksum(row["reporter"])
        return row

    def issue_of(self, sub: dict) -> int:
        """The issue a check belongs to: its own (a registration check) or its bounty's (RaceV3's `_repoOf`)."""
        return sub["issue"] if sub["issue"] else self.bounty(sub["bounty"])["issue"]

    def config(self) -> dict:
        return _named(RACE_CONFIG_FIELDS, self.rpc.view(self.race, "getConfig()", [RACE_CONFIG])[0])

    def usage_of(self, pid: int, slot: int) -> Usage:
        r, i, c, o, v, g, m = self.rpc.view(self.race, "usageOf(uint256,uint256)", [USAGE], pid, slot)[0]
        return Usage(b32(r), i, c, o, v, g, m)

    def owed(self, who: str, coin: str | None = None) -> int:
        return self.rpc.view(self.race, "owed(address,address)", ["uint256"], who, coin or self._coin)[0]

    def committed(self, from_block: int, to_block: int | None = None) -> list:
        topic = "0x" + keccak256(COMMITTED.encode()).hex()
        return [{"bounty": int(log["topics"][1], 16), "submission": int(log["topics"][2], 16),
                 "block": int(log["blockNumber"], 16)} for log in self.rpc.logs(self.race, from_block, [topic], to_block)]

    def registered(self, from_block: int, to_block: int | None = None) -> list:
        """RaceV3's Registered(issue, reporter, check): each registration and its check's submission id."""
        topic = "0x" + keccak256(REGISTERED.encode()).hex()
        return [{"issue": int(log["topics"][1], 16), "submission": abi.decode(["uint256"], abi.hexdata(log["data"]))[0],
                 "block": int(log["blockNumber"], 16)} for log in self.rpc.logs(self.race, from_block, [topic], to_block)]

    # ----- FeesV3 -----

    def profile(self, repo) -> dict:
        image, mv, mem, timeout = self.rpc.view(self.fees, "profileOf(bytes32)", [PROFILE], b32(repo))[0]
        return {"image": image, "milliVcpus": mv, "memoryMb": mem, "timeoutSeconds": timeout}

    def current_period(self) -> int:
        return self.rpc.view(self.fees, "currentPeriod()", ["uint256"])[0]

    def rolled(self) -> int:
        return self.rpc.view(self.fees, "rolled()", ["uint256"])[0]

    def priced_families(self) -> list:
        return [b32(f) for f in self.rpc.view(self.fees, "pricedFamilies()", ["bytes32[]"])[0]]

    def pending_families(self) -> list:
        return [b32(f) for f in self.rpc.view(self.fees, "pendingFamilies()", ["bytes32[]"])[0]]

    def shared_prices(self) -> list:
        """The shared units in force: vCPU-s, GB-s, storage MB (micro-coins per million), ETH (micro-coins each)."""
        return self.rpc.view(self.fees, "sharedPrices()", ["uint256[4]"])[0]

    def token_prices(self, family: bytes) -> list:
        return self.rpc.view(self.fees, "tokenPrices(bytes32)", ["uint256[3]"], family)[0]

    def deposit_for(self, s: int, repo, judges: int = K_MAX) -> int:
        return self.rpc.view(self.fees, "depositFor(uint256,bytes32,uint256)", ["uint256"], s, b32(repo), judges)[0]

    # ----- the fee coin -----

    def balance(self, who: str) -> int:
        return self.rpc.view(self._coin, "balanceOf(address)", ["uint256"], who)[0]

    def allowance(self, owner: str, spender: str) -> int:
        return self.rpc.view(self._coin, "allowance(address,address)", ["uint256"], owner, spender)[0]
