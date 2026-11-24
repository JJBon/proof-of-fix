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
                     "bytes32 attestation,bytes32 image,bytes32 host,bytes32 family,uint32 firmware,bytes32 radNode)")
STATEMENT_TYPE = "Statement(bytes32 subject,bytes32 content)"
RECEIPT_TYPE = ("Receipt(bytes32 proofType,bytes32 notary,bytes32 model,bytes32 weights,bytes32 image,bytes32 seed,"
                "bytes32 prompt,bytes32 answer,bytes32 tests,bytes32 proof,address panels,uint256 pid,uint256 slot,"
                "address key)")
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
STATUS = ["None", "Sealed", "Waiting", "Judging", "Held", "Window", "Final", "Withdrawn", "Expired", "Released"]
SEALED, WAITING, JUDGING, HELD, WINDOW, FINAL, WITHDRAWN, EXPIRED, RELEASED = 1, 2, 3, 4, 5, 6, 7, 8, 9
KINDS = ["Counted", "Shadow", "Audit", "Challenge"]
COUNTED, SHADOW, AUDIT, CHALLENGE = 0, 1, 2, 3
STATES = ["None", "Candidate", "Active", "Leaving", "Exited", "BelowFloor"]
CANDIDATE, ACTIVE, LEAVING, EXITED, BELOW_FLOOR = 1, 2, 3, 4, 5

# The views' structs as ABI tuples, and their field names (tests/test_oracle_v3.py rebuilds both from the sources).
SNAP = "(uint64,uint32,uint32,uint64)"
PANELS_SUBMISSION = (f"(bytes32,uint128,uint64,uint8,uint8,uint8,uint8,bool,bool,bool,{SNAP},uint64,uint64,uint64,"
                     f"uint64,uint64,uint64,uint8,uint8,uint8,bool,bool,bool,uint64,uint64,uint64,{SNAP},{SNAP},"
                     "address,address,uint64,bool,uint8,uint64,uint64,uint64,uint64,uint8,bool,bool)")
PANELS_SUBMISSION_FIELDS = ["commitment", "bounty", "seedBlock", "status", "tier", "k", "level", "pass",
                            "heldAtCount", "teeOnly", "snap", "waitEpoch", "finalAt", "pid", "shadowPid",
                            "frozenLeft", "auditBlock", "auditsDue", "auditsDrawn", "auditsDone", "auditDecided",
                            "challengeOpen", "lastUpheld", "challengeBlock", "challengeEpoch", "challengePid",
                            "auditSnap", "challengeSnap", "challenger", "author", "auditEpoch", "auditWaits",
                            "redraws", "retryAt", "auditStuckAt", "challengeBy", "challengeRetryAt", "lapses",
                            "chalFiled", "filedLapsed"]
PANEL = f"(uint256,bytes32,uint64,uint64,uint32,uint8,uint8,uint8,uint8,uint8,uint8,bool,uint8,bool,bool,uint64,{SNAP})"
PANEL_FIELDS = ["id", "seed", "sealBy", "revealBy", "counter", "k", "seats", "nSealed", "done", "passes", "level",
                "counted", "kind", "closed", "scored", "ex", "snap"]
# Panels' rules (#251 contract batch 4, L23 and L24): each cap Strict (0) or Off (1), kTop, and the challenge's size,
# Larger (0) or Same (1).
PANEL_RULES = "(uint8,uint8,uint8,uint256,uint8)"
PANEL_RULES_FIELDS = ["operatorCap", "hostCap", "teeCap", "kTop", "challengeSize"]
CAPS = ["strict", "off"]
CHALLENGE_SIZES = ["larger", "same"]
SEAT = "(address,uint8,bool,bool,bool,bool,uint8,bytes32,bytes32)"
SEAT_FIELDS = ["key", "level", "hasSeal", "revealed", "receipted", "vote", "mask", "seal", "receipt"]
VALIDATOR = ("(address,uint8,uint8,bool,uint8,address,uint64,bytes32,bytes32,bytes32,bytes32,bytes32,bytes32,uint128,"
             "uint128,uint32,uint32,uint64,uint32,uint32,bytes32)")
VALIDATOR_FIELDS = ["key", "level", "state", "genesis", "suspensions", "operator", "leftAt", "proofType", "teeType",
                    "attestation", "image", "host", "family", "bond", "slashed", "openVerdicts", "openChallenges",
                    "registeredAt", "firmware", "reattestations", "radNode"]
REGISTRATION = "(address,address,bytes32,bytes32,uint8,bytes32,bytes32,bytes32,bytes32,uint32,bytes32)"
RACE_ISSUE = "(bytes32,address,uint256,uint256,uint256,uint256,uint8,bool)"
RACE_ISSUE_FIELDS = ["repo", "reporter", "registration", "stake", "bounty", "check", "state", "hidden"]
RACE_BOUNTY = "(uint256,uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256)"
RACE_BOUNTY_FIELDS = ["issue", "state", "offerFrom", "locked", "lockBps", "idleSince", "attempting", "next", "winner",
                      "mergeBy", "epoch", "pledges"]
# v3.1 (#310, rebase in place) adds `rebaseOf` to the submission and `rebase`, `lastPass` to the award; a v3
# deployment's views return the shorter v3 tuples (`Chain.rebases` tells them apart, `_V3` below).
RACE_SUBMISSION = ("(uint256,uint256,uint256,address,bytes32,uint256,uint256,uint256,uint256,uint8,bool,bool,bool,"
                   "bytes32,bytes32,uint256)")
RACE_SUBMISSION_FIELDS = ["bounty", "issue", "day", "solver", "commitment", "deposit", "charged", "judged", "pledges",
                          "outcome", "appealed", "paid", "done", "fix", "base", "rebaseOf"]
RACE_AWARD = "(address,bytes32,uint256,bool,uint256,bool,uint256,uint256)"
RACE_AWARD_FIELDS = ["winner", "fix", "sub", "closed", "earned", "merged", "rebase", "lastPass"]
RACE_SUBMISSION_V3 = RACE_SUBMISSION[:-len(",uint256)")] + ")"
RACE_AWARD_V3 = RACE_AWARD[:-len(",uint256,uint256)")] + ")"
REBASE_GRACE_S = 86_400  # RaceV3Base.REBASE_GRACE (O1): a third party may rebase this long after the head moved
REBASE_SHARE_BPS = 1_000  # RaceV3Base.REBASE_SHARE_BPS: a third party's share of the price when its rebase merges
# RaceV3's enums (RaceV3Base.sol), in their declared order. "Merged" is the claimed state: since #251's L9 the head
# moves at the verdict's finality (`merge`), recorded on the award (`merged`).
RACE_STATES = ["None", "Open", "Won", "Merged", "Paid", "Refunded", "Unsolved"]
OPEN, WON, CLAIMED, PAID, REFUNDED, UNSOLVED = 1, 2, 3, 4, 5, 6
RACE_OUTCOMES = ["None", "Pass", "Fail", "Duplicate", "Withdrawn", "TimedOut", "Released"]
RACE_CONFIG = "(address,address," + ",".join(["uint256"] * 15) + ")"
RACE_CONFIG_FIELDS = ["infrastructure", "insurance", "registrationFee", "issueStake", "attemptFee", "evaluationFee",
                      "appealFee", "challengeStake", "startPriceBps", "riseBpsPerDay", "finderFeeBps", "idleDays",
                      "resultDays", "mergeDays", "releaseEveryDays", "instalments", "judgeFee"]
USAGE = "(bytes32,uint64,uint64,uint64,uint64,uint64,uint64)"
PROFILE = "(bytes32,uint32,uint32,uint32)"
HEAD = "(bytes32,bytes32,uint256,uint256,uint256,bytes32)"  # v2's Heads.Head

SEATED = "Seated(uint256,uint256,address,uint256)"
COMMITTED = "Committed(uint256,uint256,address)"
REGISTERED = "Registered(uint256,address,uint256)"
REBASED = "Rebased(uint256,uint256,uint256,bytes32,bytes32)"  # v3.1 (#310): bounty, original, check; fix, base
COUNTED_EVENT = "Counted(uint256,uint256,bool,uint256,uint8)"  # Panels: id, pid (indexed); pass, passes, level
# Validators' own; its third topic is the Radicle node key (#251, L11)
VALIDATOR_REGISTERED = f"Registered(address,address,bool,uint8,uint256,{REGISTRATION},bytes32)"


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
    """What a validator's key signs to register (IValidators.Registration). `rad_node` (#251, design L11) is its
    Radicle node's 32-byte Ed25519 public key, the one its `did:key` names; ZERO registers no node (the seat is never
    counted as a Radicle delegate)."""
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
    rad_node: bytes = ZERO

    def as_tuple(self) -> tuple:
        return (self.key, self.operator, self.proof_type, self.tee_type, self.level, self.attestation, self.image,
                self.host, self.family, self.firmware, self.rad_node)

    def digest(self, domain: bytes) -> bytes:
        return typed(domain, keccak256(REGISTRATION_TYPEHASH + word(self.key) + word(self.operator) + self.proof_type
                                       + self.tee_type + word(self.level) + self.attestation + self.image + self.host
                                       + self.family + word(self.firmware) + self.rad_node))


# ---------- the receipt's on-chain form ----------

RECEIPT_FIELDS = ("proofType", "notary", "model", "weights", "image", "seed", "prompt", "answer", "tests", "proof",
                  "panels", "pid", "slot", "key")


@dataclass(frozen=True)
class Receipt:
    """What a receipt names on-chain (IValidators.Receipt, D11): a counted verdict posts `hash()` of it. Its last four
    fields are the seat it was given on (#251 task 3.10): the Panels' address, the panel, the slot and the validator's
    key, each as one ABI word; a receipt whose seat isn't the one it was posted on is false (`receipt_faults`)."""
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
    panels: bytes = ZERO  # the seat: the Panels it was posted to (an address word),
    pid: bytes = ZERO  # the panel (a uint256 word),
    slot: bytes = ZERO  # the seat's slot on it (a uint256 word),
    key: bytes = ZERO  # and the validator seated there (an address word)

    def words(self) -> tuple:
        return (self.proof_type, self.notary, self.model, self.weights, self.image, self.seed, self.prompt,
                self.answer, self.tests, self.proof, self.panels, self.pid, self.slot, self.key)

    def seat(self) -> tuple:
        """(panels address, pid, slot, key address) as this receipt names them."""
        return (checksum("0x" + self.panels[-20:].hex()), int.from_bytes(self.pid, "big"),
                int.from_bytes(self.slot, "big"), checksum("0x" + self.key[-20:].hex()))

    def hash(self) -> bytes:
        """`Validators.receiptHash`: keccak256(abi.encode(RECEIPT_TYPEHASH, receipt))."""
        return keccak256(RECEIPT_TYPEHASH + b"".join(self.words()))

    def to_json(self) -> dict:
        return {name: "0x" + w.hex() for name, w in zip(RECEIPT_FIELDS, self.words())}

    @classmethod
    def from_json(cls, d: dict) -> "Receipt":
        return cls(*(b32(d[name]) for name in RECEIPT_FIELDS if name in d))


# ---------- drawing a check ----------

def draw_and_signal(status: int, draw, signal, seated) -> list:
    """The one draw-and-signal rule for anyone who draws a check: the keeper (oracle/node_v3.py, and so the keeper-only
    node) and `pofctl --v3 draw` (v3.1 polish VP24, the owner's Q2 of 2026-11-24). RaceV3Endings.signal counts a wait
    while the check waits, and otherwise counts the seated validators as drawn; FeesV3 counts each event at most once
    a period, so a signal more than needed is harmless, and one fewer loses a count.

    - Waiting: signal (the wait), then draw, then signal again if the draw seated a panel.
    - Sealed: draw, then signal (the panel; or the wait, if the draw found too few validators).
    - Anything else: nothing.

    `draw()` sends Panels.draw and says whether it was sent (it may raise, as the caller's sends do); `signal(kind)`
    sends RaceV3.signal for `kind` "wait" (before the draw) or "drawn" (after it) and says whether it was sent;
    `seated()` reads whether the check now has a panel. Returns the steps sent, in order ("signal:wait", "draw",
    "signal:drawn")."""
    sent = []
    if status == WAITING:
        if signal("wait"):
            sent.append("signal:wait")
        if not draw():
            return sent
        sent.append("draw")
        if seated() and signal("drawn"):
            sent.append("signal:drawn")
    elif status == SEALED:
        if not draw():
            return sent
        sent.append("draw")
        if signal("drawn"):
            sent.append("signal:drawn")
    return sent


# ---------- the chain's v3 views ----------

def _named(fields: list, row) -> dict:
    return dict(zip(fields, row))


class Chain:
    """RaceV3 and the contracts it names, read over JSON-RPC (oracle.rpc.Rpc). The node's writes go through its
    wallet (oracle/node_v3.py) and the `onchain` transport (oracle/transport.py).

    Event scans (#312) never start before `first_block`, the deployment's first block (the node's ORACLE_FROM_BLOCK,
    pofctl's record `block`, or `find_first_block`). A scan up to the latest block keeps what it read up to
    `reorg_depth` blocks back, so the next one asks only for the blocks after that: a node polling every 2 s asks for a
    few dozen blocks a pass, not for everything since its start."""

    version = 3
    reorg_depth = 32  # blocks a scan reads again each time: past any Sepolia reorg, or a provider node that lags
    first_block_margin_s = 3600  # find_first_block looks this far before RaceV3's start (clock skew; ~300 blocks)

    def __init__(self, rpc, race: str, first_block: int = 0) -> None:
        self.rpc, self.race = rpc, checksum(race)
        panels, fees, pool, registry, heads, coin, start = rpc.view(
            race, "contracts()", ["address", "address", "address", "address", "address", "address", "uint256"])
        self.panels, self.fees, self.pool = checksum(panels), checksum(fees), checksum(pool)
        self.registry, self.heads, self._coin, self.start = checksum(registry), checksum(heads), checksum(coin), start
        self._chain_id = self._domain = self._repo = self._rebases = None
        self.first_block = max(int(first_block), 0)
        self._scans: dict = {}  # (address, topics, first block) -> (the logs up to `done`, done)

    def find_first_block(self) -> int:
        """The first block from an hour before RaceV3's start, by bisection on the blocks' timestamps: where the
        deployment's events can begin, for a node that isn't told (ORACLE_FROM_BLOCK). RaceV3's start is the deploying
        script's block time, read before any of its transactions is mined (DeploySepolia.s.sol, NodeV3Local.s.sol), and
        the registry, its genesis registration and Panels are deployed in that same broadcast. About 25 block reads."""
        target, lo, hi = self.start - self.first_block_margin_s, 0, self.block()
        while lo < hi:
            mid = (lo + hi) // 2
            if int(self.rpc.call("eth_getBlockByNumber", [hex(mid), False])["timestamp"], 16) < target:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def _logs(self, address: str, from_block: int, topics: list, to_block: int | None = None) -> list:
        """`address`'s events with `topics`, from `from_block` (never before `first_block`) to `to_block` or the latest
        block. Up to the latest, the blocks older than `reorg_depth` are read once and kept (see the class)."""
        start = max(from_block, self.first_block)
        if to_block is not None:
            return self.rpc.logs(address, start, topics, to_block) if to_block >= start else []
        key = (address, tuple(topics), start)
        kept, done = self._scans.get(key, ([], start - 1))
        head = self.rpc.block()
        fresh = self.rpc.logs(address, done + 1, topics, head) if head > done else []
        safe = head - self.reorg_depth
        if safe > done:
            kept = kept + [log for log in fresh if int(log["blockNumber"], 16) <= safe]
            fresh = [log for log in fresh if int(log["blockNumber"], 16) > safe]
            self._scans[key] = (kept, safe)
        return kept + fresh

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
        for log in self._logs(self.panels, from_block, topics, to_block):
            slot, seal_by = abi.decode(["uint256", "uint256"], abi.hexdata(log["data"]))
            out.append({"pid": int(log["topics"][1], 16), "slot": slot, "sealBy": seal_by,
                        "block": int(log["blockNumber"], 16)})
        return out

    def liveness(self) -> dict:
        """Panels' liveness values (#251, L19, L16 and L25): STUCK_GRACE, RETRY_DELAY, MAX_REDRAWS, the capacity's
        window and CHALLENGE_DEADLINE, in seconds (MAX_REDRAWS a count)."""
        names = {"stuckGrace": "STUCK_GRACE()", "retryDelay": "RETRY_DELAY()", "maxRedraws": "MAX_REDRAWS()",
                 "capWindow": "CAP_WINDOW()", "challengeDeadline": "CHALLENGE_DEADLINE()"}
        return {k: self.rpc.view(self.panels, sig, ["uint256"])[0] for k, sig in names.items()}

    def panel_rules(self) -> dict:
        """Panels' rules (#251 contract batch 4, L23 and L24), named as the deployment record names them: each cap
        "strict" or "off", "kTop", and "challengeSize" "larger" or "same"."""
        r = _named(PANEL_RULES_FIELDS, self.rpc.view(self.panels, "panelRules()", [PANEL_RULES])[0])
        return {"operatorCap": CAPS[r["operatorCap"]], "hostCap": CAPS[r["hostCap"]], "teeCap": CAPS[r["teeCap"]],
                "kTop": r["kTop"], "challengeSize": CHALLENGE_SIZES[r["challengeSize"]]}

    def cover_judges(self) -> int:
        """How many judges a challenge's cover is priced for (RaceV3: the largest challenge panel the rules draw,
        PanelRulesLib.challengeTop): kTop with `same` (3 for kTop 1), CHALLENGE_K[kTop] with `larger`."""
        r = self.panel_rules()
        k = r["kTop"]
        if k == 1:
            return 3
        return k if r["challengeSize"] == "same" else min(k + 2, K_MAX)

    def capacity(self, key: str) -> dict:
        """A validator's capacity (#251 L16, #253): checks a window in force now, the next one and from which block,
        and whether it has room for a seat now (0 checks: paused)."""
        checks, nxt, frm, room = self.rpc.view(self.panels, "capacity(address)", ["uint256", "uint256", "uint256",
                                                                                  "bool"], key)
        return {"checks": checks, "next": nxt, "from": frm, "room": room}

    # ----- the registry -----

    def validator(self, key: str) -> dict:
        v = _named(VALIDATOR_FIELDS, self.rpc.view(self.registry, "validator(address)", [VALIDATOR], key)[0])
        v["key"], v["operator"] = checksum(v["key"]), checksum(v["operator"])
        return v

    def rad_node_of(self, key: str) -> bytes:
        """The Radicle node key (32 bytes, Ed25519) `key` registered with; ZERO for none (#251, L11)."""
        return b32(self.rpc.view(self.registry, "radNodeOf(address)", ["bytes32"], key)[0])

    def epoch(self) -> int:
        """Bumped on every change to the registry."""
        return self.rpc.view(self.registry, "epoch()", ["uint256"])[0]

    def is_active(self, key: str) -> bool:
        return self.rpc.view(self.registry, "isActive(address)", ["bool"], key)[0]

    def is_drawable(self, key: str) -> bool:
        """Active, bonded at least BOND_FLOOR and in standing: the set #251's L5 counts as seated."""
        return self.rpc.view(self.registry, "isDrawable(address)", ["bool"], key)[0]

    def seats(self, from_block: int | None = None) -> list:
        """The validators seated on-chain (#251 L11, model (a): the Radicle repository's delegates): every key the
        registry's Registered events name that `isDrawable` now, checksummed and sorted. The events are read from the
        deployment's first block (a validator registered long ago is still a delegate), each block once (#312);
        `isDrawable` is asked every time, since it changes."""
        topic = "0x" + keccak256(VALIDATOR_REGISTERED.encode()).hex()
        start = self.first_block if from_block is None else from_block
        keys = {checksum("0x" + log["topics"][1][-40:]) for log in self._logs(self.registry, start, [topic])}
        return sorted(k for k in keys if self.is_drawable(k))

    def repo(self) -> bytes:
        """The deployment's one repository (RaceV3.repo, #251 L1): keccak256 of its Radicle RID."""
        if self._repo is None:
            self._repo = b32(self.rpc.view(self.race, "repo()", ["bytes32"])[0])
        return self._repo

    def head(self) -> bytes:
        """The repository's canonical head in the race's Heads (a fix's base must be it at its merge, #251 L9)."""
        return b32(self.rpc.view(self.heads, "head(bytes32)", [HEAD], self.repo())[0][0])

    def registration_digest(self, r: Registration) -> bytes:
        return b32(self.rpc.view(self.registry, f"registrationDigest({REGISTRATION})", ["bytes32"], r.as_tuple())[0])

    def bond_floor(self) -> int:
        return self.rpc.view(self.registry, "BOND_FLOOR()", ["uint256"])[0]

    # ----- RaceV3 -----

    def rebases(self) -> bool:
        """Whether this deployment is v3.1 (#310: rebase in place), read once from the race itself: v3.1's `award`
        view returns eight words, v3's six. The ABI follows the contract, so a v3 record and a v3.1 record both read
        right whatever their `version` says."""
        if self._rebases is None:
            data = self.rpc.eth_call(self.race, abi.call_data("award(uint256,uint256)", 0, 0))
            self._rebases = len(data) >= 8 * 32
        return self._rebases

    def submission(self, s: int) -> dict:
        """A check's record. `rebaseOf` (v3.1): the original winning submission a rebase check rebases, else 0."""
        if self.rebases():
            row = self.rpc.view(self.race, "submission(uint256)", [RACE_SUBMISSION], s)[0]
        else:
            row = (*self.rpc.view(self.race, "submission(uint256)", [RACE_SUBMISSION_V3], s)[0], 0)
        sub = _named(RACE_SUBMISSION_FIELDS, row)
        sub["solver"] = checksum(sub["solver"])
        return sub

    def bounty(self, b: int) -> dict:
        return _named(RACE_BOUNTY_FIELDS, self.rpc.view(self.race, "bounty(uint256)", [RACE_BOUNTY], b)[0])

    def award(self, b: int, epoch: int) -> dict:
        """An award (`merged`: the head moved to its fix at its verdict's finality, #251 L9)."""
        if self.rebases():
            row = self.rpc.view(self.race, "award(uint256,uint256)", [RACE_AWARD], b, epoch)[0]
        else:
            row = (*self.rpc.view(self.race, "award(uint256,uint256)", [RACE_AWARD_V3], b, epoch)[0], 0, 0)
        row = _named(RACE_AWARD_FIELDS, row)
        row["winner"] = checksum(row["winner"])
        return row

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
                 "block": int(log["blockNumber"], 16)} for log in self._logs(self.race, from_block, [topic], to_block)]

    def registered(self, from_block: int, to_block: int | None = None) -> list:
        """RaceV3's Registered(issue, reporter, check): each registration and its check's submission id."""
        topic = "0x" + keccak256(REGISTERED.encode()).hex()
        return [{"issue": int(log["topics"][1], 16), "submission": abi.decode(["uint256"], abi.hexdata(log["data"]))[0],
                 "block": int(log["blockNumber"], 16)} for log in self._logs(self.race, from_block, [topic], to_block)]

    def rebased(self, from_block: int, to_block: int | None = None) -> list:
        """RaceV3's Rebased(bounty, original, check, fix, base) (v3.1, #310): each rebase check opened. None on v3."""
        if not self.rebases():
            return []
        topic = "0x" + keccak256(REBASED.encode()).hex()
        out = []
        for log in self._logs(self.race, from_block, [topic], to_block):
            fix, base = abi.decode(["bytes32", "bytes32"], abi.hexdata(log["data"]))
            out.append({"bounty": int(log["topics"][1], 16), "original": int(log["topics"][2], 16),
                        "submission": int(log["topics"][3], 16), "fix": b32(fix), "base": b32(base),
                        "block": int(log["blockNumber"], 16)})
        return out

    def counted_tx(self, s: int, pid: int, from_block: int = 0) -> dict | None:
        """The transaction that counted check `s`'s panel `pid` (Panels' Counted event), from `from_block` to the
        latest block: {"tx": its hash, "block"}, or None when there's none (yet). Read once, not kept."""
        topics = ["0x" + keccak256(COUNTED_EVENT.encode()).hex(), "0x" + word(s).hex(), "0x" + word(pid).hex()]
        for log in self._logs(self.panels, from_block, topics, self.block()):
            return {"tx": log["transactionHash"], "block": int(log["blockNumber"], 16)}
        return None

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

    def deposit_for(self, s: int, repo, judges: int | None = None) -> int:
        """FeesV3's deposit for check `s` and `judges` judges (default: what a challenge's cover is priced for)."""
        if judges is None:
            judges = self.cover_judges()
        return self.rpc.view(self.fees, "depositFor(uint256,bytes32,uint256)", ["uint256"], s, b32(repo), judges)[0]

    # ----- the fee coin -----

    def balance(self, who: str) -> int:
        return self.rpc.view(self._coin, "balanceOf(address)", ["uint256"], who)[0]

    def allowance(self, owner: str, spender: str) -> int:
        return self.rpc.view(self._coin, "allowance(address,address)", ["uint256"], owner, spender)[0]
