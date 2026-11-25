"""The v3 validator node (proof-of-fix#139, task 4.1 of #132, on #138's contracts): the registration, statement and
receipt encodings and the views' structs against the contracts' sources; and nodes acting as counted judges, shadows,
auditors and challenge judges against a fake chain that keeps Panels' rules (the windows, the signed statements, the
seal that a reveal must open). No Docker, no chain and no model.

The same node against the real contracts on a local chain (anvil), where Validators, Panels, FeesV3 and RaceV3 check
its signatures and its ABI, is scripts/node-v3-e2e.sh (tests/e2e_node_v3.py)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from oracle import abi, crypto, node_v3, v2, v3, zktls
from oracle.judge import Answer, FakeJudge
from oracle.keys import DstackKeys, LocalDevKeys, Quote
from oracle.models import Reply
from oracle.node_v3 import NodeV3, SetupError
from oracle.receipt import Store
from oracle.rounds import Store as Rounds
from oracle.rpc import Reverted, Unavailable
from oracle.transport import OnchainExchange, exchange_from_env

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "src" / "v3"
CHAIN = 31337
RACE, PANELS, FEES, REGISTRY, COIN = (crypto.checksum("0x" + x * 20) for x in ("a1", "b2", "c3", "d4", "e5"))
SEAL_WINDOW, REVEAL_WINDOW = 7200, 3600
FAMILY = v3.name_id("fake")
IMAGE = v2.DEVNET_IMAGE
RECORDED = ROOT / "experiments" / "zktls" / "proofs" / "call-self-a-mpc-claude-haiku-4.5-2.receipt.json"


# ---------- the sources ----------

def _text(name: str) -> str:
    return (SRC / name).read_text(encoding="utf-8")


def _string_constant(text: str, constant: str) -> str:
    m = re.search(constant + r"\s*=\s*keccak256\(\s*((?:\"[^\"]*\"\s*)+)\)", text)
    if m is None:
        raise AssertionError(f"{constant} not found")
    return "".join(re.findall(r"\"([^\"]*)\"", m.group(1)))


def _struct(text: str, name: str) -> list:
    """[(type, field)] of a Solidity struct."""
    m = re.search(r"struct " + name + r"\s*\{(.*?)\n\s*\}", text, re.S)
    if m is None:
        raise AssertionError(f"struct {name} not found")
    body = re.sub(r"//[^\n]*", "", m.group(1))
    return [tuple(part.split()) for part in (x.strip() for x in body.split(";")) if part]


def _enum(text: str, name: str) -> list:
    m = re.search(r"enum " + name + r"\s*\{(.*?)\}", text, re.S)
    return [x.strip() for x in re.sub(r"//[^\n]*", "", m.group(1)).split(",") if x.strip()]


def _tuple(fields: list, nested: dict) -> str:
    """The ABI tuple of a struct: enums are uint8, contracts are addresses, nested structs their own tuples."""
    out = []
    for t, _ in fields:
        if t in nested:
            out.append(nested[t])
        elif re.fullmatch(r"(uint\d+|bytes32|address|bool)", t):
            out.append(t)
        else:
            out.append("uint8")  # an enum
    return "(" + ",".join(out) + ")"


class Encodings(unittest.TestCase):
    def test_type_strings_and_tags_match_the_contracts(self):
        reg, base, race = _text("Validators.sol"), _text("PanelsBase.sol"), _text("RaceV3Base.sol")
        for name, mine in (("REGISTRATION_TYPEHASH", v3.REGISTRATION_TYPE), ("STATEMENT_TYPEHASH", v3.STATEMENT_TYPE),
                           ("RECEIPT_TYPEHASH", v3.RECEIPT_TYPE)):
            self.assertEqual(_string_constant(reg, name), mine, name)
        self.assertEqual(_string_constant(base, "STATEMENT_TYPEHASH"), v3.STATEMENT_TYPE)
        for name, mine in (("SEAL_TAG", v3.SEAL_TAG), ("REVEAL_TAG", v3.REVEAL_TAG), ("RECEIPT_TAG", v3.RECEIPT_TAG)):
            self.assertEqual(crypto.keccak256(_string_constant(base, name).encode()), mine, name)
        self.assertEqual(crypto.keccak256(_string_constant(race, "USAGE_TAG").encode()), v3.USAGE_TAG)
        for name, mine in (("PROOF_TEE", v3.PROOF_TEE), ("PROOF_ZKTLS", v3.PROOF_ZKTLS),
                           ("PROOF_SIMULATED", v3.PROOF_SIMULATED)):
            self.assertEqual(crypto.keccak256(_string_constant(reg, name).encode()), mine, name)
        self.assertIn('keccak256("proof-of-fix Validators"), keccak256("3")', reg)  # the domain's name and version

    def test_the_views_structs_match_the_contracts(self):
        base, iv, race, fees = _text("PanelsBase.sol"), _text("IValidators.sol"), _text("RaceV3Base.sol"), \
            _text("IFeesV3.sol")
        snap = _tuple(_struct(_text("PanelsDraw.sol"), "Snap"), {})
        self.assertEqual(snap, v3.SNAP)
        nested = {"PanelsDraw.Snap": snap}
        for text, name, tup, names in (
                (base, "Submission", v3.PANELS_SUBMISSION, v3.PANELS_SUBMISSION_FIELDS),
                (base, "Panel", v3.PANEL, v3.PANEL_FIELDS), (base, "Seat", v3.SEAT, v3.SEAT_FIELDS),
                (iv, "Validator", v3.VALIDATOR, v3.VALIDATOR_FIELDS),
                (race, "Issue", v3.RACE_ISSUE, v3.RACE_ISSUE_FIELDS),
                (race, "Bounty", v3.RACE_BOUNTY, v3.RACE_BOUNTY_FIELDS),
                (race, "Submission", v3.RACE_SUBMISSION, v3.RACE_SUBMISSION_FIELDS),
                (race, "Award", v3.RACE_AWARD, v3.RACE_AWARD_FIELDS),
                (race, "Config", v3.RACE_CONFIG, v3.RACE_CONFIG_FIELDS)):
            fields = _struct(text, name)
            self.assertEqual(_tuple(fields, nested), tup, name)
            self.assertEqual([f for _, f in fields], names, name)
        self.assertEqual(_tuple(_struct(iv, "Registration"), {}), v3.REGISTRATION)
        self.assertEqual(_tuple(_struct(fees, "Usage"), {}), v3.USAGE)
        self.assertEqual(_tuple(_struct(fees, "Profile"), {}), v3.PROFILE)
        self.assertEqual([f for _, f in _struct(iv, "Receipt")], list(v3.RECEIPT_FIELDS))
        self.assertEqual(_enum(base, "Status"), v3.STATUS)
        self.assertEqual(_enum(base, "Kind"), v3.KINDS)
        self.assertEqual(_enum(iv, "State"), v3.STATES)
        self.assertEqual(_enum(race, "State"), v3.RACE_STATES)
        self.assertEqual(_enum(race, "Outcome"), v3.RACE_OUTCOMES)

    def test_events_and_calls_exist_as_the_node_spells_them(self):
        base, panels, race = _text("PanelsBase.sol"), _text("Panels.sol"), _text("RaceV3Base.sol")
        self.assertIn("event Seated(uint256 indexed pid, uint256 slot, address indexed key, uint256 sealBy)", base)
        self.assertIn("event Registered(uint256 indexed issue, address indexed reporter, uint256 check)", race)
        self.assertIn("event Rebased(uint256 indexed bounty, uint256 indexed original, uint256 indexed check, bytes32 "
                      "fix, bytes32 base)", race)  # v3.1 (#310)
        self.assertEqual(v3.REBASED, "Rebased(uint256,uint256,uint256,bytes32,bytes32)")
        self.assertIn(f"REBASE_GRACE = {v3.REBASE_GRACE_S // 86400} days", race)
        self.assertIn(f"REBASE_SHARE_BPS = {v3.REBASE_SHARE_BPS:_}", race)
        self.assertIn("event Committed(uint256 indexed bounty, uint256 indexed submission, address indexed solver)",
                      race)
        for sig in ("function seal(uint256 pid, address key, bytes32 sealHash, bytes calldata sig)",
                    "function reveal(uint256 pid, address key, bool vote, uint8 mask, bytes32 salt, bytes calldata sig)",
                    "function receipt(uint256 pid, address key, bytes32 receiptHash, bytes calldata sig)"):
            self.assertIn(sig, panels)
        # the race's `report` runs in its endings since #251's contract batch 3 (the race's own entry delegates)
        self.assertIn("function report(uint256, address, IFeesV3.Usage calldata, bytes calldata)", _text("RaceV3.sol"))
        self.assertIn("function report(uint256 pid, address key, IFeesV3.Usage calldata u, bytes calldata sig)",
                      _text("RaceV3Endings.sol"))
        self.assertIn("function post(uint256[4] calldata shared, bytes32[] calldata families, uint256[3][] calldata "
                      "tokens)", _text("FeesV3.sol"))

    def test_statements_bind_the_contract_the_panel_and_the_key(self):
        key = LocalDevKeys(0)
        dom = v3.registry_domain(CHAIN, REGISTRY)
        seal = v3.commitment_of(PANELS, 7, key.address(), True, 0, b"\x01" * 32)
        self.assertNotEqual(seal, v3.commitment_of(PANELS, 8, key.address(), True, 0, b"\x01" * 32))
        self.assertNotEqual(seal, v3.commitment_of(PANELS, 7, key.address(), False, 0, b"\x01" * 32))
        subjects = {v3.subject_of(t, PANELS, 7, key.address()) for t in (v3.SEAL_TAG, v3.REVEAL_TAG, v3.RECEIPT_TAG)}
        subjects.add(v3.subject_of(v3.USAGE_TAG, RACE, 7, key.address()))
        self.assertEqual(len(subjects), 4)
        d = v3.statement_digest(dom, v3.subject_of(v3.SEAL_TAG, PANELS, 7, key.address()), seal)
        self.assertEqual(crypto.recover(d, key.sign(d)), key.address())
        self.assertNotEqual(d, v3.statement_digest(v3.registry_domain(1, REGISTRY),
                                                   v3.subject_of(v3.SEAL_TAG, PANELS, 7, key.address()), seal))

    def test_fixed_size_arrays_in_the_abi(self):
        types = ["uint256[4]", "bytes32[]", "uint256[3][]"]
        values = [[1, 2, 3, 4], [b"\x01" * 32], [[5, 6, 7], [8, 9, 10]]]
        data = abi.encode(types, values)
        self.assertEqual(len(data), 32 * (4 + 2 + 2 + 1 + 6))
        self.assertEqual(abi.decode(types, data), [[1, 2, 3, 4], ["0x" + "01" * 32], [[5, 6, 7], [8, 9, 10]]])
        with self.assertRaises(ValueError):
            abi.encode(["uint256[4]"], [[1, 2, 3]])

    def test_a_receipt_round_trips_and_its_hash_covers_every_field(self):
        r = v3.Receipt(*(bytes([i]) * 32 for i in range(1, 15)))
        self.assertEqual(v3.Receipt.from_json(r.to_json()), r)
        self.assertEqual(r.hash(), crypto.keccak256(v3.RECEIPT_TYPEHASH + b"".join(bytes([i]) * 32
                                                                                   for i in range(1, 15))))
        for i in range(14):
            words = list(r.words())
            words[i] = b"\xff" * 32
            self.assertNotEqual(v3.Receipt(*words).hash(), r.hash())


# ---------- a fake chain that keeps Panels' rules ----------

class SimKeys(LocalDevKeys):
    """A test key whose quotes are labelled as the dstack simulator's (the real provider is DstackKeys; see
    Registering.test_the_simulated_attestation_is_the_dstack_simulators_quote)."""

    def quote(self, report_data: bytes) -> Quote:
        rd = report_data.ljust(64, b"\0")
        return Quote("dstack-simulator", hashlib.sha256(b"simulated quote" + rd).hexdigest(), rd.hex())


def _fail(reason: str):
    raise Reverted(reason)


class FakeChain:
    """Validators, Panels, FeesV3 and RaceV3 as far as the node reads and writes them. The rules kept are the ones the
    node must respect: a seal within its window and signed; a reveal once every seat of a judging panel has sealed
    (and, for a counted panel before its seal window ends, every shadow drawn with it: #311), a shadow's after its
    seal window (every panel's after it with `early = False`, v3's rule), signed, and opening the seal; a receipt in
    the reveal window; a usage report bound to the on-chain receipt; a table only from an active validator. Every
    transaction is recorded in `txs`, in order."""

    version = 3
    race, panels, fees, registry = RACE, PANELS, FEES, REGISTRY
    rpc = None

    def __init__(self) -> None:
        self.time, self.height = 1_000_000, 100
        self.start = self.time  # RaceV3's start: its day 0
        self.validators: dict = {}
        self.panels_: dict = {}
        self.subs: dict = {}  # id -> the race's submission
        self.verdicts: dict = {}  # id -> Panels' record
        self.issues: dict = {1: {"repo": "0x" + "00" * 32, "reporter": crypto.checksum("0x" + "77" * 20), "check": 0,
                                 "bounty": 1, "state": 1, "hidden": False, "registration": 0, "stake": 0}}
        self.usage: dict = {}
        self.txs: list = []
        self.allowances: dict = {}
        self.early = True  # #311's early reveal (v3.1); False: v3's, every reveal after the seal window
        self.challenges: list = []
        self.posted: dict = {}
        self.period, self.rolled_ = 0, 0
        self.priced = [FAMILY]
        self.bounties: dict = {}  # b -> the race's bounty, beyond {"issue": 1}
        self.awards: dict = {}  # (b, epoch) -> award
        self.live = {"stuckGrace": 86400, "retryDelay": 86400, "maxRedraws": 3, "capWindow": 3600,
                     "challengeDeadline": 120 * 3600}
        self.settled_lapses: list = []
        self.head_ = b"\x11" * 20 + b"\0" * 12  # Heads.head: the fixes' base in Net
        self.rebases_: list = []  # Rebased events (v3.1)
        self.v31_fees = True  # FeesV3 has drawEpoch (v3.1); False: live v3's, where the probe reverts
        self.roll_parts, self.parts_left = 1, 1  # FeesV3.rollPart: parts a period takes, and those left of this one
        self.estimates: dict = {}  # (name, args) -> the wallet's sends of that call, refused ones included
        self.floors: dict = {}  # (name, args) -> the gas floor it was last sent with

    # ----- test helpers -----

    def add_validator(self, keys, state=v3.ACTIVE, proof=v3.PROOF_SIMULATED) -> None:
        self.validators[keys.address().lower()] = {
            "key": keys.address(), "level": 1, "state": state, "genesis": False, "suspensions": 0,
            "operator": keys.address(), "leftAt": 0, "proofType": "0x" + proof.hex(), "teeType": "0x" + "00" * 32,
            "attestation": "0x" + "11" * 32, "image": "0x" + IMAGE.hex(), "host": "0x" + "22" * 32,
            "family": "0x" + FAMILY.hex(), "bond": 100 * 10**6, "slashed": 0, "openVerdicts": 0, "openChallenges": 0,
            "registeredAt": 0, "firmware": 0, "reattestations": 0}

    def add_submission(self, s: int, commitment: bytes = b"\0" * 32, solver: str = "0x" + "99" * 20, bounty: int = 1,
                       issue: int = 0) -> None:
        self.subs[s] = {"bounty": bounty, "issue": issue, "day": 0, "solver": crypto.checksum(solver),
                        "commitment": "0x" + commitment.hex(), "deposit": 0, "charged": 0, "judged": 1, "pledges": 0,
                        "outcome": 0, "appealed": False, "paid": False, "done": False, "fix": "0x" + "00" * 32}
        self.verdicts[s] = {"status": v3.SEALED, "seedBlock": self.height + 5, "pid": 0, "pass": False,
                            "challengeOpen": False, "auditBlock": 0, "auditDecided": False, "auditsDrawn": 0,
                            "auditsDue": 0, "auditsDone": 0, "challengePid": 0, "challengeBlock": 0, "finalAt": 0,
                            "waitEpoch": 0, "redraws": 0, "retryAt": 0, "auditStuckAt": 0, "shadowPid": 0}

    def add_panel(self, s: int, kind: int, keys: list, ex: int = 0, seal_by: int | None = None) -> int:
        pid = len(self.panels_) + 1
        seal_by = self.time + SEAL_WINDOW if seal_by is None else seal_by
        self.panels_[pid] = {
            "id": s, "seed": "0x" + crypto.keccak256(b"seed%d" % pid).hex(), "sealBy": seal_by,
            "revealBy": seal_by + REVEAL_WINDOW, "counter": 0, "k": len(keys), "seats": len(keys), "nSealed": 0,
            "done": 0, "passes": 0, "level": 1, "counted": False, "kind": kind, "closed": False, "scored": False,
            "ex": ex, "snap": [0, 0, 0, 0], "born": self.height,
            "slots": [{"key": k, "level": 1, "hasSeal": False, "revealed": False, "receipted": False, "vote": False,
                       "mask": 0, "seal": "0x" + "00" * 32, "receipt": "0x" + "00" * 32} for k in keys]}
        if kind == v3.COUNTED:
            self.verdicts[s].update(status=v3.JUDGING, pid=pid)
        if kind == v3.SHADOW:
            self.verdicts[s].update(shadowPid=pid)
        self.height += 1
        return pid

    def warp(self, seconds: int) -> None:
        self.time += seconds
        self.height += 1

    def names(self, sender: str | None = None) -> list:
        return [n for who, n, _ in self.txs if sender is None or who == sender]

    # ----- the views -----

    def chain_id(self):
        return CHAIN

    def repo(self):
        return v3.ZERO  # the issues' repository here

    def coin(self):
        return COIN

    def domain(self):
        return v3.registry_domain(CHAIN, REGISTRY)

    def now(self):
        return self.time

    def block(self):
        return self.height

    def panel_count(self):
        return len(self.panels_)

    def panel(self, pid):
        return {k: v for k, v in self.panels_[pid].items() if k not in ("slots", "born")}

    def seat(self, pid, slot):
        return dict(self.panels_[pid]["slots"][slot])

    def judges(self, pid):
        return [x["key"] for x in self.panels_[pid]["slots"]]

    def verdict(self, s):
        return dict(self.verdicts[s])

    def seated(self, key, from_block, to_block=None):
        return [{"pid": pid, "slot": i, "sealBy": p["sealBy"], "block": p["born"]}
                for pid, p in self.panels_.items() for i, x in enumerate(p["slots"])
                if x["key"].lower() == key.lower() and p["born"] >= from_block]

    def validator(self, key):
        blank = {**{f: 0 for f in v3.VALIDATOR_FIELDS}, "proofType": "0x" + "00" * 32, "image": "0x" + "00" * 32}
        return dict(self.validators.get(key.lower(), blank))

    def is_active(self, key):
        return self.validator(key)["state"] == v3.ACTIVE

    def epoch(self):
        return len(self.validators)

    def registration_digest(self, r):
        return r.digest(self.domain())

    def bond_floor(self):
        return 100 * 10**6

    def submission(self, s):
        return dict(self.subs[s])

    def bounty(self, b):
        return {"issue": 1, "state": v3.OPEN, "winner": 0, "epoch": 0, **self.bounties.get(b, {})}

    def award(self, b, epoch):
        return dict(self.awards[(b, epoch)])

    def liveness(self):
        return dict(self.live)

    def head(self):
        return self.head_

    def rebased(self, from_block, to_block=None):
        return list(self.rebases_)

    def mergeExpired(self, sender, b):  # noqa: N802 (the contract's name)
        bt = self.bounties[b]
        a = self.awards[(b, bt["epoch"])]
        r = self.subs.get(a.get("rebase", 0))
        if r is None or r["outcome"] != 2 or r["solver"] != a["winner"] or v3.b32(r["base"]) != self.head_:
            _fail("NotYet()")
        a["closed"] = True
        bt["state"] = v3.OPEN

    def issue(self, i):
        return dict(self.issues[i])

    def issue_of(self, sub):
        return sub["issue"] if sub["issue"] else self.bounty(sub["bounty"])["issue"]

    def config(self):
        return {"challengeStake": 10 * 10**6, "resultDays": 7}

    def draw_epoch(self, s):
        if not self.v31_fees:
            _fail("reverted")
        return self.rolled_ + 1

    def usage_of(self, pid, slot):
        return self.usage.get((pid, slot), v2.Usage(v3.ZERO, 0, 0, 0, 0, 0, 0))

    def committed(self, from_block, to_block=None):
        return [{"bounty": x["bounty"], "submission": s, "block": 1} for s, x in self.subs.items() if x["bounty"]]

    def registered(self, from_block, to_block=None):
        return [{"issue": x["issue"], "submission": s, "block": 1} for s, x in self.subs.items() if not x["bounty"]]

    def profile(self, repo):
        return {"milliVcpus": 2000, "memoryMb": 4096}

    def current_period(self):
        return self.period

    def rolled(self):
        return self.rolled_

    def priced_families(self):
        return list(self.priced)

    def pending_families(self):
        return []

    def shared_prices(self):
        return [11_244_444, 1_234_722, 269_531_250, 2_700_000_000]

    def token_prices(self, family):
        return [4_000_000, 200_000, 20_000_000]

    def deposit_for(self, s, repo, judges=7):
        return 3 * 10**6

    def allowance(self, owner, spender):
        return self.allowances.get((owner.lower(), spender.lower()), 0)

    # ----- the transactions (FakeWallet.send) -----

    def _signed(self, key, tag, contract, pid, content, sig):
        d = v3.statement_digest(self.domain(), v3.subject_of(tag, contract, pid, key), content)
        if crypto.recover(d, sig).lower() != key.lower():
            _fail("BadSignature()")

    def _seat(self, pid, key):
        p = self.panels_[pid]
        if p["counted"] or p["closed"]:
            _fail("NotOpen()")
        for i, x in enumerate(p["slots"]):
            if x["key"] and x["key"].lower() == key.lower():
                return p, i, x
        _fail("NotSeated()")

    def _reveal_window(self, pid, p):
        if p["kind"] == v3.SHADOW or not self.early:
            if self.time <= p["sealBy"]:
                _fail("TooEarly()")
        if p["kind"] != v3.SHADOW and p["nSealed"] < p["k"]:
            _fail("TooEarly()")
        if p["kind"] == v3.COUNTED and self.time <= p["sealBy"]:
            sp = self.verdicts[p["id"]].get("shadowPid", 0)
            q = self.panels_.get(sp)
            if q and q["ex"] == pid and q["nSealed"] < q["k"] and self.time <= q["sealBy"]:
                _fail("TooEarly()")
        if self.time > p["revealBy"]:
            _fail("TooLate()")

    def _complete(self, pid, p, x):
        if not (x["revealed"] and x["receipted"]):
            return
        p["done"] += 1
        p["passes"] += x["vote"]
        if p["kind"] != v3.SHADOW and p["done"] == p["k"]:
            p["counted"] = True
            if p["kind"] == v3.COUNTED:
                self.verdicts[p["id"]].update(status=v3.HELD if p["k"] == 1 else v3.WINDOW, pid=pid,
                                              **{"pass": 2 * p["passes"] > p["k"]}, finalAt=self.time + 86400)

    def seal(self, sender, pid, key, seal, sig):
        p, _, x = self._seat(pid, key)
        if x["hasSeal"]:
            _fail("AlreadySealed()")
        if self.time > p["sealBy"]:
            _fail("TooLate()")
        self._signed(key, v3.SEAL_TAG, PANELS, pid, v3.b32(seal), sig)
        x.update(hasSeal=True, seal="0x" + v3.b32(seal).hex())
        p["nSealed"] += 1

    def reveal(self, sender, pid, key, vote, mask, salt, sig):
        p, _, x = self._seat(pid, key)
        if not x["hasSeal"]:
            _fail("NotSealed()")
        if x["revealed"]:
            _fail("AlreadyRevealed()")
        self._reveal_window(pid, p)
        self._signed(key, v3.REVEAL_TAG, PANELS, pid, v3.reveal_content(vote, mask, v3.b32(salt)), sig)
        if v3.commitment_of(PANELS, pid, key, vote, mask, v3.b32(salt)) != v3.b32(x["seal"]):
            raise AssertionError("a reveal that doesn't open its seal: the whole bond")
        x.update(revealed=True, vote=vote, mask=mask)
        self._complete(pid, p, x)

    def receipt(self, sender, pid, key, receipt, sig):
        p, _, x = self._seat(pid, key)
        if not x["hasSeal"]:
            _fail("NotSealed()")
        if x["receipted"]:
            _fail("AlreadyReceipted()")
        self._reveal_window(pid, p)
        self._signed(key, v3.RECEIPT_TAG, PANELS, pid, v3.b32(receipt), sig)
        x.update(receipted=True, receipt="0x" + v3.b32(receipt).hex())
        self._complete(pid, p, x)

    def report(self, sender, pid, key, usage, sig):
        u = v2.Usage(v3.b32(usage[0]), *usage[1:])
        slot = next(i for i, x in enumerate(self.panels_[pid]["slots"]) if x["key"].lower() == key.lower())
        x = self.panels_[pid]["slots"][slot]
        if (pid, slot) in self.usage or not x["receipted"] or v3.b32(x["receipt"]) != u.receipt:
            _fail("Refused()")
        self._signed(key, v3.USAGE_TAG, RACE, pid, v3.usage_content(u), sig)
        self.usage[(pid, slot)] = u

    def register(self, sender, r, amount, sig):
        reg = v3.Registration(r[0], r[1], *(v3.b32(x) if isinstance(x, (bytes, str)) else x for x in r[2:]))
        if crypto.recover(reg.digest(self.domain()), sig).lower() != reg.key.lower():
            _fail("BadSignature()")
        if self.allowance(sender, REGISTRY) < amount or amount < self.bond_floor():
            _fail("BondTooSmall()")
        if reg.key.lower() in self.validators:
            _fail("KeyTaken()")
        self.validators[reg.key.lower()] = {**self.validator(reg.key), "key": reg.key, "state": v3.CANDIDATE,
                                            "operator": reg.operator, "proofType": "0x" + reg.proof_type.hex(),
                                            "attestation": "0x" + reg.attestation.hex(), "bond": amount,
                                            "image": "0x" + reg.image.hex(), "family": "0x" + reg.family.hex()}

    def leave(self, sender, key):
        val = self.validators.get(key.lower())
        if val is None or sender.lower() not in (key.lower(), val["operator"].lower()):
            _fail("NotAllowed()")
        if val["state"] not in (v3.CANDIDATE, v3.ACTIVE):
            _fail("WrongState()")
        val["state"] = v3.LEAVING

    def approve(self, sender, spender, amount):
        self.allowances[(sender.lower(), spender.lower())] = amount

    def post(self, sender, shared, families, tokens):
        if not self.is_active(sender):
            _fail("NotActive()")
        self.posted[sender.lower()] = (list(shared), [v3.b32(f) for f in families], [list(t) for t in tokens])

    def challenge(self, sender, s, evidence):
        v = self.verdicts[s]
        need = self.config()["challengeStake"] + self.deposit_for(s, None)
        if v["challengeOpen"] or v["status"] not in (v3.HELD, v3.WINDOW) or self.allowance(sender, RACE) < need:
            _fail("Refused()")
        v["challengeOpen"] = True
        self.challenges.append((sender, s, v3.b32(evidence)))

    def draw(self, sender, s):
        if self.verdicts[s]["status"] != v3.SEALED or self.height <= self.verdicts[s]["seedBlock"]:
            _fail("TooEarly()")
        self.verdicts[s]["status"] = v3.WAITING  # nobody to seat here: it waits

    def drawAudits(self, sender, s):  # noqa: N802 (the contract's name)
        self.verdicts[s]["auditBlock"] = self.height + 5  # nobody to draw here: it only re-targets, and never refuses

    def drawChallenge(self, sender, s):  # noqa: N802 (the contract's name)
        v = self.verdicts[s]
        if not v["challengeOpen"] or v["challengePid"]:
            _fail("WrongStatus()")
        # busy validators leave the fresh panel short (L16): it neither draws nor refuses, as the contract's `c.full`

    def merge(self, sender, b):
        bt = self.bounty(b)
        a = self.awards[(b, bt["epoch"])]
        if bt["state"] != v3.CLAIMED or a["merged"] or self.verdicts[a["sub"]]["status"] != v3.FINAL:
            _fail("NotYet()")
        a["merged"] = True

    def release(self, sender, pid):
        """Panels.release (the race's `release` is `refund` here)."""
        if not self._release_panel(pid):
            _fail("NothingDue()")

    def _release_panel(self, pid):
        p = self.panels_[pid]
        if p["closed"] or p["counted"] or p["seats"] == p["k"] or self.time <= p["revealBy"] + self.live["stuckGrace"]:
            return False
        p["closed"] = True
        v = self.verdicts[p["id"]]
        if p["kind"] == v3.CHALLENGE:  # L25: back to waiting before the deadline, a lapse after it
            v["challengePid"] = 0
            if self.time > v["challengeBy"]:
                self._lapse(v)
            else:
                v.update(challengeEpoch=self.epoch() + 1, challengeRetryAt=self.time + self.live["retryDelay"])
            return True
        v["redraws"] += 1
        v.update(status=v3.RELEASED if v["redraws"] >= self.live["maxRedraws"] else v3.WAITING, pid=0,
                 retryAt=self.time + self.live["retryDelay"])
        return True

    def lapseChallenge(self, sender, s):  # noqa: N802 (the contract's name)
        v = self.verdicts[s]
        if not v["challengeOpen"] or v["challengePid"]:
            _fail("WrongStatus()")
        if self.time <= v["challengeBy"]:
            _fail("TooEarly()")
        self._lapse(v)

    def _lapse(self, v):
        v.update(challengeOpen=False, challengePid=0, challengeEpoch=0, lapses=v.get("lapses", 0) + 1,
                 filedLapsed=True)

    def settleLapse(self, sender, s):  # noqa: N802 (the contract's name)
        """RaceV3.settleLapse: once per lapse of a filed challenge."""
        if not self.verdicts[s].get("filedLapsed") or (s, self.verdicts[s]["lapses"]) in self.settled_lapses:
            _fail("Refused()")
        self.settled_lapses.append((s, self.verdicts[s]["lapses"]))

    def payPanel(self, sender, pid):  # noqa: N802 (the contract's name)
        p = self.panels_[pid]
        if p.get("paid") or not (p["counted"] or (p["closed"] and p["kind"] == v3.CHALLENGE)):
            _fail("Refused()")
        self._reports_due(pid)
        p["paid"] = True

    def _reports_due(self, pid):
        """RaceV3's `_reportsDue`: every seated key reported, or REPORT_WINDOW after the reveal deadline."""
        p = self.panels_[pid]
        if self.time <= p["revealBy"] + 86400 and any(
                x["key"] and (pid, i) not in self.usage for i, x in enumerate(p["slots"])):
            _fail("NotYet()")

    def rollPart(self, sender):  # noqa: N802 (the contract's name)
        """FeesV3.rollPart: `roll_parts` parts close the oldest open period."""
        if self.rolled_ >= self.period:
            _fail("TooEarly()")
        self.parts_left -= 1
        if self.parts_left <= 0:
            self.rolled_ += 1
            self.parts_left = self.roll_parts

    def releaseAudits(self, sender, s):  # noqa: N802 (the contract's name)
        v = self.verdicts[s]
        if not v["auditStuckAt"] or self.time <= v["auditStuckAt"] + self.live["stuckGrace"]:
            _fail("NothingDue()")
        v["redraws"] += 1
        v["auditStuckAt"] = self.time

    def refund(self, sender, s):
        """RaceV3.release, as the node calls it on the race (FakeWallet routes it here): a check Panels released for
        good, or one with a released round once resultDays have passed since its day; a counted verdict's judges
        paid first."""
        v, x = self.verdicts[s], self.subs[s]
        if x["done"] or (v["pid"] and not x["paid"]):
            _fail("NotYet()")
        if v["status"] != v3.RELEASED and (
                not v["redraws"] or (self.time - self.start) // 86400 < x["day"] + self.config()["resultDays"]):
            _fail("NotYet()")
        x.update(done=True, outcome=6)

    def finish(self, sender, s):
        """RaceV3.finish: REPORT_WINDOW after a paid check's verdict is final."""
        v, x = self.verdicts[s], self.subs[s]
        if x["done"] or not x["paid"] or v["status"] != v3.FINAL or self.time <= v["finalAt"] + 86400:
            _fail("NotYet()")
        x["done"] = True

    def payShadow(self, sender, pid, slot):  # noqa: N802 (the contract's name)
        p = self.panels_[pid]
        if (pid, slot) in p.setdefault("shadowsPaid", set()):
            _fail("Refused()")
        p["shadowsPaid"].add((pid, slot))

    def result(self, sender, s):
        if self.subs[s]["paid"] or self.verdicts[s]["status"] not in (v3.HELD, v3.WINDOW, v3.FINAL):
            _fail("NotYet()")
        p = self.panels_[self.verdicts[s]["pid"]]
        if any((self.verdicts[s]["pid"], i) not in self.usage for i in range(p["k"])):
            _fail("NotYet()")
        self.subs[s]["paid"] = True


class FakeWallet:
    def __init__(self, chain: FakeChain, me: str):
        self.chain, self.address = chain, me

    def send(self, to, signature, *args, **kw):
        name = signature.split("(")[0]
        if to == RACE and name == "release":
            name = "refund"  # the race's release refunds a check; Panels' releases a stuck panel
        try:
            key = (name, args)
            hash(key)
        except TypeError:  # a table's lists
            key = (name, repr(args))
        self.chain.estimates[key] = self.chain.estimates.get(key, 0) + 1
        if kw.get("gas_floor"):
            self.chain.floors[key] = kw["gas_floor"]
        fn = getattr(self.chain, name, None)
        if fn is None:
            raise Reverted(f"{name}: not due")
        fn(self.address, *args)
        self.chain.txs.append((self.address, name, args))
        return {"logs": []}


class FakeHost:
    def __init__(self, pulls=(), issues=()):
        self._pulls, self._issues = list(pulls), list(issues)

    def pulls(self, state="all"):
        return list(self._pulls)

    def issues(self, state="open", label=None):
        return list(self._issues)


class Net:
    """A fake chain, one submitted fix on a fake host, and nodes for it."""

    def __init__(self, tmp: Path, n: int = 4, exit_code: int = 0):
        from bot import logic

        self.tmp, self.chain, self.exit_code = tmp, FakeChain(), exit_code
        self.keys = [SimKeys(i) for i in range(n)]
        solver, self.salt, self.sha = crypto.checksum("0x" + "99" * 20), b"\x02" * 32, "ab" * 20
        commitment = v3.fix_commitment(v2.commit_word(self.sha), v2.commit_word("11" * 20), self.salt, solver)
        self.chain.add_submission(1, commitment, solver)
        (tmp / "src" / self.sha).mkdir(parents=True)
        self.host = FakeHost([{"number": 3, "title": "Fix", "body": logic.pr_body(1, 1, 1, "0x" + self.salt.hex(),
                                                                                  solver),
                               "state": "open", "head_sha": self.sha, "base_sha": "11" * 20, "merged": False}])
        self.logs: list = []
        self.nodes = [self.node(i) for i in range(n)]
        for k in self.keys:
            self.chain.add_validator(k)

    def node(self, i: int, judge=None, rounds: bool = True, exit_code: int | None = None, **kw) -> NodeV3:
        k = self.keys[i]
        wallet = FakeWallet(self.chain, k.address())
        code = self.exit_code if exit_code is None else exit_code
        table = kw.pop("table", False)
        node = NodeV3(self.chain, k, judge or FakeJudge(), self.host, "demo/median", self.tmp / "src",
                      OnchainExchange(self.chain, k, wallet=wallet), Store(self.tmp / "receipts"),
                      runner=lambda argv: (code, "ok", ""), log=self.logs.append, wallet=wallet,
                      rounds=Rounds(self.tmp / "rounds", CHAIN, RACE, k.address()) if rounds else None,
                      keeper=kw.pop("keeper", False), **kw)
        if not table:
            node.posted_period = self.chain.period  # this period's table is posted: the tests of the rest stay quiet
        return node

    def addresses(self, *idx) -> list:
        return [self.keys[i].address() for i in idx]

    def tick(self, nodes=None, times: int = 1) -> None:
        for _ in range(times):
            for n in (self.nodes if nodes is None else nodes):
                n.tick(0)

    def judge_through(self, nodes=None) -> None:
        """Seals, then the seal window passes, then the reveals, receipts and usage reports."""
        self.tick(nodes, 2)
        self.chain.warp(SEAL_WINDOW + 1)
        self.tick(nodes, 3)


class Judging(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_a_counted_judge_and_two_shadows(self):
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        shadow = c.add_panel(1, v3.SHADOW, net.addresses(1, 2), ex=counted, seal_by=c.panels_[counted]["sealBy"])
        net.judge_through()
        # every seat sealed, revealed with its receipt, and reported its usage
        for pid, k in ((counted, 1), (shadow, 2)):
            for slot in range(k):
                seat = c.seat(pid, slot)
                self.assertTrue(seat["hasSeal"] and seat["revealed"] and seat["receipted"] and seat["vote"])
                self.assertEqual(c.usage[(pid, slot)].receipt, v3.b32(seat["receipt"]))
        self.assertEqual(c.verdict(1)["status"], v3.HELD)  # a k = 1 verdict is held
        self.assertTrue(c.verdict(1)["pass"])
        # the receipt on-chain is the hash of the document the node keeps, which names its proof
        doc = net.nodes[0].receipts3.get(c.seat(counted, 0)["receipt"])
        on = v3.Receipt.from_json(doc["onchain"])
        self.assertEqual((on.proof_type, on.image, on.seed), (v3.PROOF_SIMULATED, IMAGE, v3.b32(c.panel(counted)["seed"])))
        self.assertEqual(on.proof, crypto.keccak256(bytes.fromhex(doc["proof"]["quote"])))
        self.assertEqual(doc["proof"]["kind"], "dstack-simulator")
        self.assertEqual(on.model, crypto.keccak256(doc["receipt"]["model"]["id"].encode()))
        # and the seat it was given on (#251 task 3.10)
        self.assertEqual(on.seat(), (crypto.checksum(PANELS), counted, 0, net.keys[0].address()))
        seat = c.seat(counted, 0)
        self.assertEqual(node_v3.receipt_faults(doc, seat, c.validator(seat["key"]), c.panel(counted), None,
                                                (PANELS, counted, 0)), [])
        why = node_v3.receipt_faults(doc, seat, c.validator(seat["key"]), c.panel(counted), None, (PANELS, shadow, 0))
        self.assertIn("it names another seat than the one it was posted on", why)
        self.assertEqual(net.nodes[3].seats, {})  # not drawn: it did nothing
        self.assertEqual(c.names(net.keys[3].address()), [])
        self.assertEqual(c.names(net.keys[0].address()), ["seal", "receipt", "reveal", "report"])

    def test_a_shadows_seal_is_sent_before_the_counted_reveals(self):
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0, 1, 2))
        shadow = c.add_panel(1, v3.SHADOW, net.addresses(3), ex=counted, seal_by=c.panels_[counted]["sealBy"])
        net.judge_through()
        order = [(n, a[0]) for _, n, a in c.txs if n in ("seal", "reveal")]
        first_counted_reveal = order.index(("reveal", counted))
        self.assertLess(order.index(("seal", shadow)), first_counted_reveal)
        self.assertEqual([n for n, _ in order[:4]], ["seal"] * 4)  # every seal before any reveal
        self.assertTrue(c.seat(shadow, 0)["revealed"])
        # and a shadow seated late, after the counted reveals are public, can't seal: its window is the counted one's
        late = c.add_panel(1, v3.SHADOW, net.addresses(3), ex=counted, seal_by=c.panels_[counted]["sealBy"])
        net.tick(times=2)
        self.assertFalse(c.seat(late, 0)["hasSeal"])
        self.assertIn(late, net.nodes[3].finished)

    def test_one_node_seals_as_a_shadow_before_it_reveals_as_a_judge(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_submission(2, bounty=0, issue=1)  # a registration check, to shadow
        net.host._issues = [{"number": 9, "labels": ["bounty"],
                             "body": f"Registration: 1\nReporter wallet: {c.issues[1]['reporter']}"}]
        c.early = False  # v3's rule: the counted reveal waits for the seal window (#311 would reveal at once)
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]])  # sealed as the counted judge
        c.warp(SEAL_WINDOW + 1)  # its reveal window is open ...
        shadow = c.add_panel(2, v3.SHADOW, net.addresses(0))  # ... and the same node is drawn as a shadow elsewhere
        net.tick([net.nodes[0]])
        mine = [(n, a[0]) for _, n, a in c.txs]
        self.assertLess(mine.index(("seal", shadow)), mine.index(("reveal", counted)))

    def test_a_full_panel_reveals_before_its_seal_window_ends(self):
        """#311: once every seat has sealed (and every shadow drawn with it), the judges reveal at once."""
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0, 1, 2))
        shadow = c.add_panel(1, v3.SHADOW, net.addresses(3), ex=counted, seal_by=c.panels_[counted]["sealBy"])
        net.tick(net.nodes[:2])  # two of three sealed: nobody reveals while a seat could still seal
        self.assertEqual([n for _, n, _ in c.txs], ["seal", "seal"])
        net.tick(net.nodes[:3])  # the panel is full, but its shadow hasn't sealed: still no counted reveal
        self.assertNotIn("reveal", c.names())
        net.tick(net.nodes[3:])  # the shadow seals
        net.tick(net.nodes[:3], 2)
        self.assertLess(c.time, c.panels_[counted]["sealBy"])
        self.assertTrue(c.panel(counted)["counted"], "counted before the seal window ends")
        self.assertFalse(any("refused" in m for m in net.logs), "nothing sent that the chain refused")
        c.warp(SEAL_WINDOW + 1)
        net.tick(net.nodes[3:], 2)
        self.assertTrue(c.seat(shadow, 0)["revealed"])

    def test_an_audit_reveals_at_once(self):
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]], 2)
        self.assertTrue(c.panel(counted)["counted"])
        audit = c.add_panel(1, v3.AUDIT, net.addresses(1), ex=counted)
        net.tick([net.nodes[1]], 2)
        self.assertTrue(c.panel(audit)["counted"])
        self.assertLess(c.time, c.panels_[audit]["sealBy"])

    def test_on_v3_a_node_waits_for_the_seal_window(self):
        """A deployment without #311 (v3): one early attempt is refused at the estimate, then the node waits."""
        net = Net(self.tmp)
        c = net.chain
        c.early = False
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]], 3)
        self.assertEqual(c.names(), ["seal"])
        self.assertEqual(sum("only after the seal window" in m for m in net.logs), 1)
        c.warp(SEAL_WINDOW + 1)
        net.tick([net.nodes[0]], 2)
        self.assertTrue(c.panel(counted)["counted"])

    def test_a_shadow_on_a_waiting_submission(self):
        net = Net(self.tmp)
        c = net.chain
        c.verdicts[1]["status"] = v3.WAITING
        shadow = c.add_panel(1, v3.SHADOW, net.addresses(1, 2, 3), ex=0)
        net.judge_through()
        self.assertTrue(all(c.seat(shadow, i)["revealed"] and c.seat(shadow, i)["receipted"] for i in range(3)))
        self.assertTrue(any("waits for a panel" in m for m in net.logs))

    def test_an_auditor_judges_alone(self):
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        audit = c.add_panel(1, v3.AUDIT, net.addresses(1), ex=counted)
        net.judge_through([net.nodes[1]])
        self.assertTrue(c.panel(audit)["counted"])
        self.assertEqual((c.seat(audit, 0)["vote"], c.seat(audit, 0)["mask"]), (True, 0))
        self.assertIn((audit, 0), c.usage)

    def test_a_challenge_judge_names_a_false_receipt(self):
        net = Net(self.tmp, exit_code=1)  # the fix's tests fail
        c = net.chain
        cheat = net.node(0, exit_code=0)  # this judge's receipt says they passed
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0, 1, 2))
        net.judge_through([cheat, net.nodes[1], net.nodes[2]])
        self.assertEqual([c.seat(counted, i)["vote"] for i in range(3)], [True, False, False])
        challenge = c.add_panel(1, v3.CHALLENGE, net.addresses(3), ex=counted)
        net.judge_through([net.nodes[3]])
        self.assertEqual((c.seat(challenge, 0)["vote"], c.seat(challenge, 0)["mask"]), (False, 0b001))
        self.assertTrue(any("seat 0's receipt is false" in m for m in net.logs))

    def test_a_restarted_node_reveals_what_it_sealed(self):
        net = Net(self.tmp)
        c = net.chain
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]])
        sealed = c.seat(counted, 0)["seal"]
        c.warp(SEAL_WINDOW + 1)
        again = net.node(0)  # a new process, the same disk
        net.tick([again], 3)
        self.assertTrue(c.seat(counted, 0)["revealed"])
        self.assertEqual(c.seat(counted, 0)["seal"], sealed)
        self.assertEqual(c.names().count("seal"), 1)  # one seal for the seat, ever

    def test_a_node_that_lost_its_round_doesnt_reveal(self):
        net = Net(self.tmp)
        c = net.chain
        c.early = False  # v3's rule, so the seal and the reveal are in different runs
        first = net.node(0, rounds=False)
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([first])
        c.warp(SEAL_WINDOW + 1)
        again = net.node(0, rounds=False)
        net.tick([again], 3)
        self.assertFalse(c.seat(counted, 0)["revealed"])  # a second, different reveal would be equivocation
        self.assertIn(counted, again.finished)

    def test_a_fix_nobody_published_is_sealed_as_not_passed_at_the_deadline(self):
        net = Net(self.tmp)
        c = net.chain
        net.host._pulls = []
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]], 2)
        self.assertFalse(c.seat(counted, 0)["hasSeal"])  # not yet: the pull request may still come
        c.warp(SEAL_WINDOW - 300)
        net.tick([net.nodes[0]])
        c.warp(301)
        net.tick([net.nodes[0]], 2)
        self.assertEqual((c.seat(counted, 0)["revealed"], c.seat(counted, 0)["vote"]), (True, False))

    def test_a_pull_request_that_doesnt_open_the_seal_is_refused(self):
        net = Net(self.tmp)
        c = net.chain
        c.subs[1]["commitment"] = "0x" + "00" * 32
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]], 3)
        self.assertFalse(c.seat(counted, 0)["hasSeal"])
        self.assertTrue(any("doesn't open its seal" in m for m in net.logs))

    def test_a_registration_check_follows_the_claim(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_submission(2, bounty=0, issue=1)
        net.host._issues = [{"number": 9, "labels": ["bounty"],
                             "body": f"Registration: 1\nReporter wallet: {c.issues[1]['reporter']}"}]
        pid = c.add_panel(2, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        self.assertTrue(c.seat(pid, 0)["vote"])
        self.assertEqual(c.verdict(2)["status"], v3.HELD)

    def test_the_node_needs_the_proof_its_registration_promises(self):
        net = Net(self.tmp)
        plain = LocalDevKeys(9)  # no simulator behind it
        net.chain.add_validator(plain)
        net.keys.append(plain)
        with self.assertRaises(SetupError) as e:
            net.node(4).tick(0)
        self.assertIn("DSTACK_SIMULATOR_ENDPOINT", str(e.exception))
        stranger = LocalDevKeys(10)
        net.keys.append(stranger)
        with self.assertRaises(SetupError):
            net.node(5).tick(0)  # not registered


class TwoRunsInTheNode(unittest.TestCase):
    """#251 L22 in the v3 node: two runs per check within the profile's one time limit, the receipt's `runs` and
    `flaky`, and the metered vCPU- and GB-seconds the two runs' sum."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def judged(self, *codes, seconds=(1.0, 1.0)):
        from unittest import mock

        from oracle import sandbox

        net = Net(self.tmp / "-".join(map(str, codes)))
        c = net.chain
        c.profile = lambda repo: {"milliVcpus": 2000, "memoryMb": 4096, "timeoutSeconds": 1200}
        node = net.nodes[0]
        seen = []

        def runner(argv):
            seen.append(argv[argv.index("timeout") + 1])
            return codes[len(seen) - 1], "ok", ""
        node.runner = runner
        ticks = iter(t for s in seconds for t in (0.0, s))  # each run: started at 0, ended after its seconds
        fake_time = mock.Mock(monotonic=lambda: next(ticks))
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        with mock.patch.object(sandbox, "time", fake_time):
            net.judge_through([node])
        doc = node.receipts3.get(c.seat(counted, 0)["receipt"])
        return c.seat(counted, 0)["vote"], doc["receipt"]["tests"], c.usage[(counted, 0)], seen

    def test_two_passes_pass(self):
        vote, tests, _, seen = self.judged(0, 0)
        self.assertTrue(vote)
        self.assertEqual(([r["exit_code"] for r in tests["runs"]], tests["exit_code"]), ([0, 0], 0))
        self.assertNotIn("flaky", tests)
        self.assertEqual(seen, ["600", "600"])  # half the profile's 1,200 s each

    def test_a_pass_and_a_fail_fail_and_set_flaky(self):
        vote, tests, _, seen = self.judged(0, 1)
        self.assertFalse(vote)
        self.assertEqual(len(seen), 2)
        self.assertIs(tests["flaky"], True)
        self.assertEqual([r["exit_code"] for r in tests["runs"]], [0, 1])

    def test_two_fails_fail(self):
        vote, tests, _, _ = self.judged(1, 1)
        self.assertFalse(vote)
        self.assertNotIn("flaky", tests)

    def test_the_usage_is_the_two_runs_sum(self):
        _, _, usage, _ = self.judged(0, 0, seconds=(10.0, 12.0))
        # 22 s at the profile's 2 vCPUs and 4 GB
        self.assertEqual((usage.vcpu_seconds, usage.gb_seconds), (44, 88))


class KeeperTableChallenge(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_the_table_is_posted_once_a_period_by_an_active_validator(self):
        net = Net(self.tmp)
        c = net.chain
        me = net.keys[0].address()
        node = net.node(0, costs={"vcpu_second": 9_000_000, "eth": 3_000_000_000}, table=True)
        node.tick(0)
        node.tick(0)
        self.assertEqual(c.names(me), ["post"])  # once
        shared, families, tokens = c.posted[me.lower()]
        self.assertEqual(shared, [9_000_000, 1_234_722, 269_531_250, 3_000_000_000])  # its own, else the one in force
        table = dict(zip(families, tokens))
        self.assertEqual(table[v3.name_id("anthropic/claude")], [4_000_000, 200_000, 20_000_000])  # the list price
        self.assertEqual(len(table), len(node_v3.default_list_prices()) + 1)  # every family listed, and the priced one
        self.assertEqual(table[FAMILY], c.token_prices(FAMILY))  # no list price here: the price in force
        c.period = 1
        node.tick(0)
        self.assertEqual(c.names(me), ["post", "post"])
        c.validators[net.keys[1].address().lower()]["state"] = v3.CANDIDATE
        net.node(1, table=True).tick(0)
        self.assertEqual(c.names(net.keys[1].address()), [])  # a candidate's table wouldn't count: not sent

    def test_the_keeper_draws_and_posts_the_result(self):
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertEqual(c.names(), [])  # the seed block hasn't passed
        c.height += 6
        keeper.tick(0)
        self.assertEqual(c.names(), ["draw"])
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        keeper.tick(0)
        self.assertEqual(c.names(net.keys[3].address()), ["draw", "drawAudits", "result"])
        self.assertTrue(c.subs[1]["paid"] and c.panel(counted)["counted"])

    def test_the_keeper_merges_a_claimed_fix_once_its_verdict_is_final(self):
        """#251 L9: the head moves at finality, by `merge` (anyone, once), not at the claim."""
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.subs[1]["paid"] = True
        c.bounties[1] = {"state": v3.CLAIMED, "winner": 1, "epoch": 1}
        c.awards[(1, 1)] = {"winner": c.subs[1]["solver"], "fix": "0x" + "00" * 32, "sub": 1, "closed": False,
                            "earned": 0, "merged": False}
        keeper.tick(0)
        self.assertNotIn("merge", c.names())  # its window is running
        c.verdicts[1]["status"] = v3.FINAL
        keeper.tick(0)
        keeper.tick(0)
        self.assertEqual(c.names().count("merge"), 1)
        self.assertTrue(c.awards[(1, 1)]["merged"])

    def test_the_keeper_releases_a_stuck_panel_and_refunds_it(self):
        """#251 L19: a panel whose replacements are exhausted is released STUCK_GRACE after its reveal deadline; the
        submission waits for its redraw; after MAX_REDRAWS rounds the race refunds it."""
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        for r in range(1, 4):
            pid = c.add_panel(1, v3.COUNTED, net.addresses(0, 1, 2))
            p = c.panels_[pid]
            p["seats"] = 2  # a silent seat nobody could take
            c.time = p["revealBy"] + c.live["stuckGrace"]
            keeper.tick(0)
            self.assertNotIn(("release", pid), [(n, a[0]) for _, n, a in c.txs])  # not before the grace
            c.warp(1)
            keeper.tick(0)
            self.assertTrue(c.panels_[pid]["closed"])
            self.assertEqual(c.verdicts[1]["redraws"], r)
        self.assertEqual(c.verdict(1)["status"], v3.RELEASED)
        keeper.tick(0)
        self.assertEqual(c.names().count("refund"), 1)  # RaceV3.release: the bounty refunded
        self.assertTrue(c.subs[1]["done"])

    def test_the_keeper_releases_audits_nobody_can_take(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.verdicts[1].update(status=v3.WINDOW, auditDecided=True, auditsDue=2, auditsDrawn=0, auditStuckAt=c.time)
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertNotIn("releaseAudits", c.names())
        c.warp(c.live["stuckGrace"] + 1)
        keeper.tick(0)
        self.assertEqual(c.names().count("releaseAudits"), 1)
        self.assertEqual(c.verdicts[1]["redraws"], 1)

    def test_the_keeper_doesnt_redraw_audits_forever(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        keeper = net.node(3, keeper=True)
        for _ in range(8):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawAudits"), node_v3.AUDIT_TRIES)  # then it waits for the registry
        c.add_validator(SimKeys(7))  # a newcomer: an auditor may be eligible now
        for _ in range(8):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawAudits"), 2 * node_v3.AUDIT_TRIES)

    def test_the_keeper_draws_audits_again_once_busy_auditors_have_room(self):
        """#311: every auditor busy (L16: the contract keeps the audit block and draws nobody) when the verdict counts
        minutes after its draw. The keeper's tries for that state of the registry are spent, but a capacity window later
        it tries again, and again after `releaseAudits` re-targets the audits; it used to wait for a registry change
        that never came, and the audits were released until the check was refunded."""
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        keeper = net.node(3, keeper=True)
        for _ in range(6):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawAudits"), node_v3.AUDIT_TRIES)
        c.warp(c.live["capWindow"])  # the busy auditors' hour is over: room again, the registry unchanged
        for _ in range(6):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawAudits"), 2 * node_v3.AUDIT_TRIES)
        c.verdicts[1]["redraws"] += 1  # a released round re-targets the audits (`releaseAudits`)
        for _ in range(6):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawAudits"), 3 * node_v3.AUDIT_TRIES)

    def test_the_keeper_doesnt_redraw_a_challenge_forever(self):
        """drawChallenge succeeds without drawing while busy validators leave its fresh panel short (L16), so the keeper
        tries it a few times per state, not on every pass: on the devnet a keeper that called it every pass made
        progress forever, and the run's clock never moved on to free the capacity it waited for."""
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.verdicts[1].update(challengeOpen=True, challengeBlock=c.height, challengeEpoch=0)
        keeper = net.node(3, keeper=True)
        for _ in range(8):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawChallenge"), node_v3.CHALLENGE_TRIES)
        self.assertFalse(keeper.tick(0))  # nothing left to do: the network is idle, and time can pass
        c.add_validator(SimKeys(7))  # the registry changed: a fresh panel may be drawable now
        for _ in range(8):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawChallenge"), 2 * node_v3.CHALLENGE_TRIES)
        c.warp(c.live["capWindow"])  # a capacity window later the busy validators may have room again
        for _ in range(8):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(c.names().count("drawChallenge"), 3 * node_v3.CHALLENGE_TRIES)

    def _waiting_challenge(self, net):
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.verdicts[1].update(challengeOpen=True, challengeBlock=c.height, challengeEpoch=c.epoch() + 1,
                             challengeRetryAt=c.time + c.live["retryDelay"], filedLapsed=False, lapses=0,
                             challengeBy=c.time + c.live["challengeDeadline"])
        return c

    def test_the_keeper_starts_a_held_window_only_once_its_challenge_closed(self):
        """#256's flake: Panels' startWindow on a held k = 1 verdict whose challenge is open leaves the window's frozen
        rest at 0, so the challenge's lapse resumed the window with nothing left and the verdict was final at once.
        The keeper starts the window only once the challenge is closed: held, the verdict can't be final anyway."""
        net = Net(self.tmp)
        c = self._waiting_challenge(net)
        self.assertEqual(c.verdicts[1]["status"], v3.HELD)
        started = []

        def start(sender, s):
            if c.verdicts[s]["status"] != v3.HELD:
                raise Reverted("WrongStatus()")
            started.append(s)
            c.verdicts[s]["status"] = v3.WINDOW
        c.startWindow = start
        keeper = net.node(3, keeper=True)
        for _ in range(3):
            c.height += 6
            keeper.tick(0)
        self.assertEqual(started, [])  # its challenge is open: the hold goes on
        c.verdicts[1]["challengeOpen"] = False
        keeper.tick(0)
        self.assertEqual(started, [1])

    def test_the_keeper_redraws_a_waiting_challenge_at_its_retry_time(self):
        """#251 L25: a waiting challenge is drawn again at its retry time even with no registry change (an un-pause
        isn't one); before it, the keeper doesn't call."""
        net = Net(self.tmp)
        c = self._waiting_challenge(net)
        keeper = net.node(3, keeper=True)
        for _ in range(4):
            c.height += 6
            keeper.tick(0)
        self.assertNotIn("drawChallenge", c.names())  # it waits: same registry, before its retry time
        c.time = c.verdicts[1]["challengeRetryAt"]
        c.height += 6
        keeper.tick(0)
        self.assertEqual(c.names().count("drawChallenge"), 1)

    def test_the_keeper_lapses_a_challenge_past_its_deadline(self):
        """#251 L25: past CHALLENGE_DEADLINE with no panel the challenge lapses (once), and the race returns a filed
        challenge's stake and cover (settleLapse, once per lapse)."""
        net = Net(self.tmp)
        c = self._waiting_challenge(net)
        keeper = net.node(3, keeper=True)
        c.time = c.verdicts[1]["challengeBy"]
        keeper.tick(0)
        self.assertNotIn("lapseChallenge", c.names())  # at the deadline, not past it
        c.warp(1)
        for _ in range(4):
            keeper.tick(0)
        self.assertEqual(c.names().count("lapseChallenge"), 1)
        self.assertFalse(c.verdicts[1]["challengeOpen"])
        self.assertEqual(c.names().count("settleLapse"), 1)
        self.assertEqual(c.settled_lapses, [(1, 1)])

    def test_the_keeper_releases_a_stuck_challenge_panel(self):
        """#251 L25: a challenge panel whose replacements are exhausted is released STUCK_GRACE after its reveal
        deadline (the challenge waits again, before its deadline), and its revealed seats are paid."""
        net = Net(self.tmp)
        c = self._waiting_challenge(net)
        c.verdicts[1].update(challengeEpoch=0)
        cpid = c.add_panel(1, v3.CHALLENGE, net.addresses(1, 2, 3), ex=1)
        c.verdicts[1]["challengePid"] = cpid
        c.panels_[cpid]["seats"] = 2
        keeper = net.node(3, keeper=True)
        c.time = c.panels_[cpid]["revealBy"] + c.live["stuckGrace"] + 1
        keeper.tick(0)
        self.assertTrue(c.panels_[cpid]["closed"])
        self.assertEqual(c.verdicts[1]["challengePid"], 0)
        self.assertTrue(c.verdicts[1]["challengeOpen"])  # before its deadline: waiting again
        self.assertEqual(c.verdicts[1]["challengeRetryAt"], c.time + c.live["retryDelay"])
        keeper.tick(0)
        self.assertEqual(c.names().count("payPanel"), 1)
        self.assertTrue(c.panels_[cpid]["paid"])

    def test_a_challenge_is_filed_only_on_a_disagreement(self):
        net = Net(self.tmp, exit_code=1)
        c = net.chain
        liar = net.node(0, judge=FakeJudge(lie=True))  # passes a fix whose tests fail
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([liar])
        self.assertTrue(c.verdict(1)["pass"])
        watcher = net.nodes[1]
        ev = watcher.challenge(1)
        sender, s, evidence = c.challenges[0]
        self.assertEqual((sender, s, evidence), (net.keys[1].address(), 1, ev))
        self.assertEqual(c.names(sender), ["approve", "challenge"])
        doc = json.loads((self.tmp / "receipts" / "v3" / f"evidence-{ev.hex()}.json").read_text())
        self.assertEqual((doc["vote"], doc["verdict"], doc["panel"], doc["false_receipts"]), (False, True, counted, 0))
        self.assertEqual(crypto.keccak256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()), ev)
        with self.assertRaises(SetupError):
            watcher.challenge(1)  # one at a time

    def test_no_challenge_when_the_check_agrees(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        self.assertIsNone(net.nodes[1].challenge(1))
        self.assertEqual(c.challenges, [])


class Rebases(unittest.TestCase):
    """v3.1's rebase in place (#310) as the node keeps and judges it: rebase checks found from `Rebased`, `merge`
    through a final passing rebase (never on a stale base), the fail-fast reopening after the solver's own failed
    rebase, and the judge's case with the approved diff, the range-diff and the rubric's question."""

    BASE, ORIG, NEW = "11" * 20, "ab" * 20, "cd" * 20

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _claimed_and_stale(self, net, rebase_solver=None):
        """Submission 1 won bounty 1 and is claimed on base 11…; the head moved to ee…; rebase check 2 of it is on the
        head. Returns the chain."""
        c = net.chain
        c.subs[1].update(fix="0x" + self.ORIG + "00" * 12, base="0x" + self.BASE + "00" * 12, paid=True, outcome=1)
        c.verdicts[1].update(status=v3.FINAL, **{"pass": True})
        c.head_ = bytes.fromhex("ee" * 20) + b"\0" * 12
        c.add_submission(2, solver=rebase_solver or c.subs[1]["solver"])
        c.subs[2].update(rebaseOf=1, fix="0x" + self.NEW + "00" * 12, base="0x" + c.head_.hex(), paid=True)
        c.rebases_ = [{"bounty": 1, "original": 1, "submission": 2, "block": 1}]
        c.bounties[1] = {"state": v3.CLAIMED, "winner": 1, "epoch": 1}
        c.awards[(1, 1)] = {"winner": c.subs[1]["solver"], "fix": "0x" + self.ORIG + "00" * 12, "sub": 1,
                            "closed": False, "earned": 0, "merged": False, "rebase": 2, "lastPass": 0}
        return c

    def test_the_keeper_merges_through_a_final_passing_rebase(self):
        net = Net(self.tmp)
        c = self._claimed_and_stale(net)
        keeper = net.node(3, keeper=True)
        c.verdicts[2].update(status=v3.WINDOW, **{"pass": True})
        keeper.tick(0)
        self.assertNotIn("merge", c.names())  # the original is final, its rebase isn't: no reverting call
        c.verdicts[2]["status"] = v3.FINAL
        c.merge = lambda sender, b: c.awards[(b, 1)].update(merged=True)
        keeper.tick(0)
        self.assertEqual(c.names().count("merge"), 1)

    def test_no_merge_call_on_a_stale_base(self):
        net = Net(self.tmp)
        c = self._claimed_and_stale(net)
        c.verdicts[2].update(status=v3.FINAL, **{"pass": True})
        c.head_ = bytes.fromhex("99" * 20) + b"\0" * 12  # the head moved again
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertNotIn("merge", c.names())
        self.assertTrue(any("isn't Heads.head any more" in line and "pofctl --v3 rebase" in line for line in net.logs))

    def test_the_solvers_failed_rebase_reopens_at_once(self):
        net = Net(self.tmp)
        c = self._claimed_and_stale(net)
        c.verdicts[2].update(status=v3.WINDOW, **{"pass": False})
        c.subs[2]["outcome"] = 2  # counted as a fail, on the head
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        keeper.tick(0)
        self.assertEqual(c.names().count("mergeExpired"), 1)
        self.assertTrue(c.awards[(1, 1)]["closed"])

    def test_a_strangers_failed_rebase_only_frees_its_slot(self):
        net = Net(self.tmp)
        c = self._claimed_and_stale(net, rebase_solver="0x" + "42" * 20)
        c.verdicts[2].update(status=v3.WINDOW, **{"pass": False})
        c.subs[2]["outcome"] = 2
        net.node(3, keeper=True).tick(0)
        self.assertNotIn("mergeExpired", c.names())

    def test_a_fail_after_the_head_moved_again_only_frees_its_slot(self):
        net = Net(self.tmp)
        c = self._claimed_and_stale(net)
        c.verdicts[2].update(status=v3.WINDOW, **{"pass": False})
        c.subs[2]["outcome"] = 2
        c.head_ = bytes.fromhex("99" * 20) + b"\0" * 12
        net.node(3, keeper=True).tick(0)
        self.assertNotIn("mergeExpired", c.names())

    def test_the_judges_case_carries_the_approved_diff_and_the_range_diff(self):
        from types import SimpleNamespace

        from oracle import fetch, rebase_v3

        calls = []

        class Fetcher:
            def diff(self, root, sha, fix, base, max_bytes):
                calls.append(("diff", sha, base))
                return fetch.Diff("mb", "+approved line\n", "the fix")

            def range_diff(self, root, old_base, old_fix, new_base, new_fix, max_bytes):
                calls.append(("range", old_base, old_fix, new_base, new_fix))
                return fetch.Diff("mb2", "1:  abc = 1:  def the fix\n")

        chain = SimpleNamespace(submission=lambda s: {"fix": "0x" + self.ORIG + "00" * 12,
                                                      "base": "0x" + self.BASE + "00" * 12})
        node = SimpleNamespace(judge=SimpleNamespace(reads_evidence=True), chain=chain, fetcher=Fetcher(),
                               src_root=self.tmp)
        base_case = {"id": "c", "repo": "r", "issue": "i", "commit": "x", "diff": "+rebased line\n", "context": [],
                     "notes": ("a note",)}
        sub = {"rebaseOf": 1}
        pull = {"head_sha": self.NEW, "base_sha": "ee" * 20}
        case, refusal = rebase_v3.judge_case(node, sub, pull, base_case, "")
        self.assertEqual(refusal, "")
        self.assertEqual(calls, [("diff", self.ORIG, self.BASE), ("range", self.BASE, self.ORIG, "ee" * 20, self.NEW)])
        self.assertTrue(case["diff"].startswith("+rebased line"))
        self.assertIn(rebase_v3.APPROVED_HEADING + "\n+approved line", case["diff"])
        self.assertIn(rebase_v3.RANGE_HEADING + "\n1:  abc = 1:  def", case["diff"])
        self.assertEqual(case["notes"][0], "a note")
        self.assertIn(f"rebase of submission 1's approved fix (commit {self.ORIG} on base {self.BASE})", case["notes"][1])
        self.assertEqual(case["notes"][2], rebase_v3.RUBRIC)
        self.assertIn("solves = false", rebase_v3.RUBRIC)
        # a judge that reads only the test run (the fake) gets the case as it was; a refusal stays one
        node.judge = SimpleNamespace(reads_evidence=False)
        self.assertEqual(rebase_v3.judge_case(node, sub, pull, base_case, ""), (base_case, ""))
        node.judge = SimpleNamespace(reads_evidence=True)
        self.assertEqual(rebase_v3.judge_case(node, sub, pull, base_case, "no"), (base_case, "no"))
        # not fetched yet: NotReady, so the node tries again before its seal deadline
        node.fetcher = SimpleNamespace(diff=lambda *a: None, range_diff=lambda *a: None)
        with self.assertRaises(node_v3.evidence.NotReady):
            rebase_v3.judge_case(node, sub, pull, base_case, "")

    def test_a_clean_rebase_passes_and_a_smuggled_change_fails(self):
        """With a stand-in judge that answers the rubric's question from the range-diff (a model's job), the node's
        case is what decides it: a range-diff with only context changes passes, one that adds a line fails."""
        from oracle import rebase_v3

        def verdict(range_diff: str, tests_passed: bool) -> bool:
            case = rebase_v3.case({"diff": "+x\n", "notes": ()}, 1, "+x\n", range_diff, (self.BASE, self.ORIG),
                                  ("ee" * 20, self.NEW))
            ranged = case["diff"].split(rebase_v3.RANGE_HEADING, 1)[1]
            unrelated = any(line.lstrip().startswith("++") for line in ranged.splitlines())
            return tests_passed and rebase_v3.RUBRIC in case["notes"] and not unrelated

        self.assertTrue(verdict("1:  abc = 1:  def the fix\n", True))
        self.assertFalse(verdict("1:  abc ! 1:  def the fix\n    @@ x\n    ++unrelated()\n", True))
        self.assertFalse(verdict("1:  abc = 1:  def the fix\n", False))  # a semantic conflict: the tests fail

    def test_a_semantic_conflict_fails_on_the_new_bases_protected_test(self):
        """The rebase check's runs are any fix's: on its tree (with the base's protected paths when the repository
        has them); the first fix's protected test failing there fails the rebase."""
        net = Net(self.tmp, exit_code=1)
        c = net.chain
        c.subs[1]["rebaseOf"] = 7  # a rebase check, judged as any fix (its runs failed)
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        self.assertFalse(c.verdicts[1]["pass"])

    def test_the_chain_reads_v3_and_v3_1_records(self):
        word = lambda i: (i).to_bytes(32, "big")  # noqa: E731

        class Rpc:
            def __init__(self, words):
                self.words = words

            def view(self, to, sig, returns, *args):
                if sig.startswith("contracts"):
                    return [RACE, PANELS, FEES, RACE, RACE, COIN, 1]
                n = self.words(sig)
                return abi.decode(returns, b"".join(word(0) for _ in range(n - 1)) + word(9))

            def eth_call(self, to, data):
                return b"\0" * 32 * self.words("award(")

        v31 = v3.Chain(Rpc(lambda sig: 8 if sig.startswith("award") else 16), RACE)
        self.assertTrue(v31.rebases())
        self.assertEqual(v31.submission(1)["rebaseOf"], 9)
        self.assertEqual(v31.award(1, 1)["lastPass"], 9)
        old = v3.Chain(Rpc(lambda sig: 6 if sig.startswith("award") else 15), RACE)
        self.assertFalse(old.rebases())
        self.assertEqual(old.submission(1)["rebaseOf"], 0)
        self.assertEqual((old.award(1, 1)["rebase"], old.award(1, 1)["lastPass"]), (0, 0))
        self.assertEqual(old.rebased(0), [])


class KeeperRetries(unittest.TestCase):
    """The keeper's retry model (v3.1 polish VP6–VP8; #314, audit F3–F5) on the fake chain over simulated hours: the
    chain's clock moves (`warp`), nothing sleeps. `estimates` counts the wallet's sends per call, refused ones too:
    each is an eth_estimateGas on a real chain."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    @staticmethod
    def hours(net, keeper, hours: float, step: int = 60, each=None) -> None:
        for _ in range(int(hours * 3600 // step)):
            net.chain.warp(step)
            keeper.tick(0)
            if each:
                each()

    def _held(self, net):
        """Submission 1 judged by a k = 1 panel: held, its counted judges paid."""
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.subs[1]["paid"] = True
        return c

    def test_startwindow_and_refill_are_tried_a_few_times_per_state(self):
        net = Net(self.tmp)
        c = self._held(net)
        tries: dict = {}

        def refuse(name):
            def call(sender, x):
                state = (name, c.epoch(), c.time // c.live["capWindow"])
                tries[state] = tries.get(state, 0) + 1
                _fail("NotReady()")
            return call
        c.startWindow, c.refill = refuse("startWindow"), refuse("refill")
        c.add_submission(2)
        short = c.add_panel(2, v3.COUNTED, net.addresses(1, 2, 3))
        c.panels_[short]["seats"] = 2  # a seat nobody can take yet
        keeper = net.node(3, keeper=True)
        self.hours(net, keeper, 3)
        self.assertTrue(tries)
        self.assertLessEqual(max(tries.values()), node_v3.CHALLENGE_TRIES)
        self.assertEqual({k[0] for k in tries}, {"startWindow", "refill"})
        before = sum(tries.values())
        c.add_validator(SimKeys(7))  # the registry changed: a few tries again, at once
        keeper.tick(0)
        self.assertEqual(sum(tries.values()), before + 2)
        self.assertFalse(any("left to others" in line for line in net.logs))  # NotReady is a gate: never given up

    def test_finish_waits_for_the_report_window_after_finality(self):
        net = Net(self.tmp)
        c = self._held(net)
        c.verdicts[1].update(status=v3.FINAL, finalAt=c.time)
        keeper = net.node(3, keeper=True)
        due = c.time + node_v3.REPORT_WINDOW_S
        seen = []
        self.hours(net, keeper, 26, step=600, each=lambda: seen.append((c.time, c.estimates.get(("finish", (1,)), 0))))
        self.assertTrue(all(n == 0 for at, n in seen if at <= due))
        self.assertEqual(c.estimates[("finish", (1,))], 1)
        self.assertTrue(c.subs[1]["done"])
        self.assertNotIn(1, keeper._scan)  # done, final, nothing owed: not read again

    def test_release_waits_for_the_races_result_days(self):
        net = Net(self.tmp)
        c = net.chain
        c.verdicts[1].update(status=v3.WAITING, redraws=1, waitEpoch=c.epoch() + 1, retryAt=c.time + 30 * 86400)
        keeper = net.node(3, keeper=True)
        seen = []
        self.hours(net, keeper, 24 * 9, step=3600,
                   each=lambda: seen.append(((c.time - c.start) // 86400, c.estimates.get(("refund", (1,)), 0))))
        self.assertTrue(all(n == 0 for day, n in seen if day < c.config()["resultDays"]))
        self.assertEqual(c.estimates[("refund", (1,))], 1)  # RaceV3.release, sent once it was due
        self.assertTrue(c.subs[1]["done"])

    def test_a_late_report_pays_the_panel_after_the_window_and_never_gives_up(self):
        """Audit F4: one auditor never reports. `payPanel` isn't sent before REPORT_WINDOW after the reveal deadline,
        is sent once after it, and the auditor who did report is paid."""
        net = Net(self.tmp)
        c = self._held(net)
        audit = c.add_panel(1, v3.AUDIT, net.addresses(1, 2))
        c.panels_[audit].update(counted=True, revealBy=c.time)
        c.usage[(audit, 0)] = v2.Usage(b"\x01" * 32, 1, 0, 1, 1, 1, 1)  # the first reported, the second never will
        keeper = net.node(3, keeper=True)
        due = c.panels_[audit]["revealBy"] + node_v3.REPORT_WINDOW_S
        seen = []
        self.hours(net, keeper, 30, step=300,
                   each=lambda: seen.append((c.time, c.estimates.get(("payPanel", (audit,)), 0))))
        self.assertTrue(all(n == 0 for at, n in seen if at <= due))
        self.assertEqual(c.estimates[("payPanel", (audit,))], 1)
        self.assertTrue(c.panels_[audit]["paid"])
        self.assertIn(("panel", audit), keeper._kept)
        self.assertFalse(any("left to others" in line for line in net.logs))

    def test_an_ungated_refusal_backs_off_and_is_given_up_after_a_day(self):
        """#314's "done when": one estimate per backoff period, one log line each; F1's `Unpriced` (not a gate) is
        left to others GIVE_UP_S after the first refusal."""
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.result = lambda sender, s: _fail("Unpriced(bytes32)")
        c.live["capWindow"] = 10**9  # one capacity window all along: the backoff alone spaces the tries
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.hours(net, keeper, 1, step=12)
        # tries at 0, 30, 90, 210, 450, 930 and 1890 s: seven in the first hour, not 300
        self.assertEqual(c.estimates[("result", (1,))], 7)
        refused = [line for line in net.logs if line.startswith("keeper: result(1) refused")]
        self.assertEqual(len(refused), 7)
        self.assertIn("next try in 60 s (", refused[1])  # with the passes skipped in the backoff before
        self.hours(net, keeper, 25, step=600)
        n = c.estimates[("result", (1,))]
        self.assertLessEqual(n, 7 + 25)  # an hour apart after the first hour
        self.assertTrue(any(line.startswith("keeper: result(1) refused for") and "left to others" in line
                            for line in net.logs))
        self.hours(net, keeper, 5, step=600)
        self.assertEqual(c.estimates[("result", (1,))], n)  # given up

    def test_a_state_change_restarts_the_backoff(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.judge_through([net.nodes[0]])
        c.result = lambda sender, s: _fail("Unpriced(bytes32)")
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        keeper.tick(0)
        self.assertEqual(c.estimates[("result", (1,))], 1)  # backing off
        c.add_validator(SimKeys(7))  # the registry's epoch moved
        keeper.tick(0)
        self.assertEqual(c.estimates[("result", (1,))], 2)

    def test_payshadow_is_sent_with_the_gas_floor(self):
        net = Net(self.tmp)
        c = net.chain
        shadow = c.add_panel(1, v3.SHADOW, net.addresses(1))
        c.panels_[shadow].update(closed=True, scored=True)
        c.panels_[shadow]["slots"][0].update(revealed=True, receipted=True)
        c.usage[(shadow, 0)] = v2.Usage(b"\x01" * 32, 1, 0, 1, 1, 1, 1)
        c.time = c.panels_[shadow]["revealBy"] + 1
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertIn("payShadow", c.names())
        self.assertGreaterEqual(c.floors[("payShadow", (shadow, 0))], node_v3.PAY_SHADOW_GAS_FLOOR)
        self.assertEqual(node_v3.PAY_SHADOW_GAS_FLOOR, 850_000)

    def test_a_period_of_several_parts_closes_in_one_or_two_passes(self):
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        c.period, c.roll_parts, c.parts_left = 1, 4, 4
        keeper.tick(0)
        self.assertEqual(c.rolled_, 1)
        self.assertEqual(c.estimates[("rollPart", ())], 4)  # one estimate a part, none once it closed
        self.assertNotIn("roll", c.names())
        c.period, c.roll_parts, c.parts_left = 2, 15, 15
        keeper.tick(0)
        self.assertEqual(c.rolled_, 1)  # ROLL_PARTS_PER_PASS in this pass
        self.assertEqual(c.estimates[("rollPart", ())], 4 + node_v3.ROLL_PARTS_PER_PASS)
        keeper.tick(0)
        self.assertEqual(c.rolled_, 2)
        self.assertEqual(c.estimates[("rollPart", ())], 4 + 15)

    def test_a_429_storm_in_the_keeper_doesnt_delay_a_due_reveal(self):
        net = Net(self.tmp)
        c = net.chain
        c.add_panel(1, v3.COUNTED, net.addresses(0))
        node = net.node(0, keeper=True)
        storm, asked = [True], []
        rolled = c.rolled

        def limited():
            asked.append(c.time)
            if storm[0]:
                raise Unavailable("HTTP 429", retry_after=None)
            return rolled()
        c.rolled = limited  # read by the keeper alone, first in its section
        node.tick(0)  # the seal; the keeper's section hits the rate limit and pauses
        self.assertIn("seal", c.names())
        node.tick(0)  # the next pass: the reveal (its panel has sealed), and no keeper call
        self.assertIn("reveal", c.names())
        self.assertEqual(len(asked), 1)
        self.assertEqual(sum("isn't answering the keeper's calls" in line for line in net.logs), 1)
        c.warp(node_v3.BACKOFF_BASE_S)
        node.tick(0)  # paused again, longer: still one log line
        self.assertEqual(len(asked), 2)
        self.assertEqual(sum("isn't answering the keeper's calls" in line for line in net.logs), 1)
        c.warp(2 * node_v3.BACKOFF_BASE_S)
        storm[0] = False
        node.tick(0)
        self.assertEqual(len(asked), 3)
        self.assertTrue(any("answers again" in line for line in net.logs))

    def test_a_429_pause_follows_retry_after_up_to_the_cap(self):
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        after = [120.0]

        def limited():
            raise Unavailable("HTTP 429", retry_after=after[0])
        c.rolled = limited
        keeper.tick(0)
        self.assertEqual(keeper._paused_until, c.time + 120)
        after[0] = 10**6
        c.time = keeper._paused_until
        keeper.tick(0)
        self.assertEqual(keeper._paused_until, c.time + node_v3.RATE_PAUSE_MAX_S)

    def test_the_keeper_section_runs_every_keeper_every_seconds(self):
        net = Net(self.tmp)
        c = net.chain
        keeper = net.node(3, keeper=True)
        keeper.keeper_every = 60
        asked = []
        rolled = c.rolled
        c.rolled = lambda: asked.append(c.time) or rolled()
        self.hours(net, keeper, 0.5, step=12)  # a pass a block, a keeper section a minute
        self.assertEqual(len(asked), 30)

    def test_the_scan_set_shrinks_as_checks_finish_and_a_restart_rescans_once(self):
        net = Net(self.tmp)
        c = net.chain
        for s in range(2, 7):
            c.add_submission(s)
            c.subs[s].update(paid=True, done=s % 2 == 0)
            c.verdicts[s].update(status=v3.FINAL, finalAt=c.time + 10**6)
        reads = []
        verdict = c.verdict
        c.verdict = lambda s: reads.append(s) or verdict(s)
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertEqual(sorted(reads), [1, 2, 3, 4, 5, 6])
        self.assertEqual(keeper._scan, {1, 3, 5})  # 2, 4 and 6 are done: final, nothing owed
        reads.clear()
        keeper.tick(0)
        self.assertEqual(sorted(reads), [1, 3, 5])
        c.subs[3]["done"] = True
        keeper.tick(0)
        reads.clear()
        keeper.tick(0)
        self.assertEqual(sorted(reads), [1, 5])
        restarted = net.node(3, keeper=True)  # a new process: every check read once again, then only the open ones
        reads.clear()
        restarted.tick(0)
        self.assertEqual(sorted(reads), [1, 2, 3, 4, 5, 6])
        reads.clear()
        restarted.tick(0)
        self.assertEqual(sorted(reads), [1, 5])

    def test_a_claimed_fix_stays_in_the_scan_until_merged(self):
        net = Net(self.tmp)
        c = net.chain
        c.subs[1].update(paid=True, done=True)
        c.verdicts[1].update(status=v3.FINAL)
        c.bounties[1] = {"state": v3.CLAIMED, "winner": 1, "epoch": 1}
        c.awards[(1, 1)] = {"winner": c.subs[1]["solver"], "fix": "0x" + "00" * 32, "sub": 1, "closed": False,
                            "earned": 0, "merged": False}
        c.merge = lambda sender, b: _fail("NotYet()")
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertIn(1, keeper._scan)  # its merge is owed
        c.awards[(1, 1)]["merged"] = True
        keeper.tick(0)
        self.assertNotIn(1, keeper._scan)

    def test_a_won_fix_stays_in_the_scan_until_claimed_and_merged(self):
        """A final, done fix whose solver hasn't claimed yet isn't dropped: its claim makes the merge due (scenario r
        of the integration set found it dropped before the claim, and never merged)."""
        net = Net(self.tmp)
        c = net.chain
        c.subs[1].update(paid=True, done=True)
        c.verdicts[1].update(status=v3.FINAL)
        c.bounties[1] = {"state": v3.WON, "winner": 1, "epoch": 0}
        merged = []
        c.merge = lambda sender, b: merged.append(b)
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertIn(1, keeper._scan)  # won, not claimed yet: kept
        c.bounties[1] = {"state": v3.CLAIMED, "winner": 1, "epoch": 1}
        c.awards[(1, 1)] = {"winner": c.subs[1]["solver"], "fix": "0x" + "00" * 32, "sub": 1, "closed": False,
                            "earned": 0, "merged": False}
        keeper.tick(0)
        self.assertEqual(merged, [1])

    def test_a_budgeted_section_resumes_where_it_stopped(self):
        net = Net(self.tmp)
        c = net.chain
        for s in range(2, 41):
            c.add_submission(s)
            c.verdicts[s]["seedBlock"] = 10**9  # nothing to call yet: one read each
        reads = []
        verdict = c.verdict
        c.verdict = lambda s: reads.append(s) or verdict(s)
        keeper = net.node(3, keeper=True)
        keeper.keeper_budget = 20
        passes = []
        for _ in range(6):
            reads.clear()
            keeper.tick(0)
            passes.append(list(reads))
        self.assertTrue(all(0 < len(p) < 20 for p in passes))
        covered = [s for p in passes[:4] for s in p]
        self.assertEqual(sorted(set(covered)), list(range(1, 41)))  # every check within a few passes
        self.assertEqual(passes[1][0], passes[0][-1] + 1)  # each pass goes on from where the last stopped
        self.assertTrue(any("budget" in line for line in net.logs))

    def test_a_rebase_check_is_kept_with_the_same_gates(self):
        """#310's rebase checks come from `Rebased` alone (task 2.8): the keeper reads them, gates their `finish`, and
        drops them once done."""
        net = Net(self.tmp)
        c = net.chain
        c.subs[1].update(paid=True, done=True, outcome=1)
        c.verdicts[1].update(status=v3.FINAL)
        c.add_submission(2)
        c.subs[2].update(rebaseOf=1, paid=True)
        c.verdicts[2].update(status=v3.FINAL, finalAt=c.time)
        c.rebases_ = [{"bounty": 1, "original": 1, "submission": 2, "block": 1}]
        committed = c.committed
        c.committed = lambda fb, tb=None: [e for e in committed(fb, tb) if e["submission"] != 2]
        keeper = net.node(3, keeper=True)
        keeper.tick(0)
        self.assertIn(2, keeper._scan)
        due = c.time + node_v3.REPORT_WINDOW_S
        seen = []
        self.hours(net, keeper, 26, step=600, each=lambda: seen.append((c.time, c.estimates.get(("finish", (2,)), 0))))
        self.assertTrue(all(n == 0 for at, n in seen if at <= due))
        self.assertEqual(c.estimates[("finish", (2,))], 1)
        self.assertNotIn(2, keeper._scan)


class KeeperDrawAndSignal(unittest.TestCase):
    """v3.1 polish VP24 (the owner's Q2, 2026-11-24): one draw-and-signal rule. Waiting: signal (the wait), draw, then
    signal again if the draw seated a panel. Sealed: draw, then signal. `signals` records the verdict's status at
    each RaceV3.signal: waiting counts a wait, a panel counts its seated validators as drawn."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.net = Net(Path(self._tmp.name))
        self.c, self.signals, self.sent = self.net.chain, [], []
        c = self.c

        def signal(sender, s):
            self.sent.append("signal")
            self.signals.append(c.verdicts[s]["status"])

        def draw(sender, s):  # a panel seated, from a sealed check past its seed block or a waiting one
            v = c.verdicts[s]
            if v["status"] == v3.SEALED and c.height <= v["seedBlock"]:
                _fail("TooEarly()")
            self.sent.append("draw")
            c.add_panel(s, v3.COUNTED, self.net.addresses(0, 1, 2))
        c.signal, c.draw = signal, draw

    def test_waiting_signals_the_wait_draws_then_signals_the_panel(self):
        c = self.c
        c.verdicts[1].update(status=v3.WAITING, redraws=1, waitEpoch=c.epoch() + 1, retryAt=c.time - 1)
        keeper = self.net.node(3, keeper=True)
        keeper.tick(0)
        self.assertEqual(self.sent[:3], ["signal", "draw", "signal"])
        self.assertEqual(self.signals[:2], [v3.WAITING, v3.JUDGING])

    def test_waiting_not_yet_due_signals_the_wait_once(self):
        c = self.c
        c.verdicts[1].update(status=v3.WAITING, waitEpoch=c.epoch() + 1, retryAt=c.time + 86_400)
        keeper = self.net.node(3, keeper=True)
        for _ in range(5):
            c.warp(60)
            keeper.tick(0)
        self.assertEqual(self.sent, ["signal"])  # the wait, once a wait round; no draw before its retry time
        c.verdicts[1].update(redraws=1, retryAt=c.time + 86_400)  # a released round waits again: its own signal
        keeper.tick(0)
        self.assertEqual(self.sent, ["signal", "signal"])

    def test_sealed_draws_then_signals(self):
        self.c.height = self.c.verdicts[1]["seedBlock"] + 1
        keeper = self.net.node(3, keeper=True)
        keeper.tick(0)
        self.assertEqual((self.sent[:2], self.signals[:1]), (["draw", "signal"], [v3.JUDGING]))

    def test_the_rule_itself(self):
        def steps(status, drew=True, seats=True):
            out = []

            def draw():
                out.append("draw")
                return drew

            def signal(kind):
                out.append("signal:" + kind)
                return True
            v3.draw_and_signal(status, draw, signal, lambda: seats)
            return out
        self.assertEqual(steps(v3.WAITING), ["signal:wait", "draw", "signal:drawn"])
        self.assertEqual(steps(v3.WAITING, seats=False), ["signal:wait", "draw"])  # still waiting: counted already
        self.assertEqual(steps(v3.WAITING, drew=False), ["signal:wait", "draw"])
        self.assertEqual(steps(v3.SEALED), ["draw", "signal:drawn"])
        self.assertEqual(steps(v3.SEALED, drew=False), ["draw"])
        self.assertEqual(steps(v3.JUDGING), [])


class KeeperSettings(unittest.TestCase):
    """ORACLE_POLL, ORACLE_KEEPER_EVERY, ORACLE_TX_POLL and ORACLE_KEEPER_BUDGET (v3.1 polish VP6)."""

    def test_defaults_follow_the_chain(self):
        from oracle import __main__ as cli

        self.assertEqual(cli.node_cadence({}, 11_155_111),
                         {"poll": 12.0, "keeper_every": 60.0, "tx_poll": 4.0, "keeper_budget": 300})
        self.assertEqual(cli.node_cadence({}, CHAIN),
                         {"poll": 2.0, "keeper_every": 0.0, "tx_poll": 0.4, "keeper_budget": 300})
        env = {"ORACLE_POLL": "5", "ORACLE_KEEPER_EVERY": "0", "ORACLE_TX_POLL": "1.5", "ORACLE_KEEPER_BUDGET": "50"}
        self.assertEqual(cli.node_cadence(env, 11_155_111),
                         {"poll": 5.0, "keeper_every": 0.0, "tx_poll": 1.5, "keeper_budget": 50})
        for bad in ({"ORACLE_POLL": "soon"}, {"ORACLE_TX_POLL": "-1"}, {"ORACLE_KEEPER_BUDGET": "0"}):
            with self.assertRaises(SystemExit):
                cli.node_cadence(bad, CHAIN)

    def test_the_help_documents_each_setting(self):
        from oracle import __main__ as cli

        for name in ("ORACLE_POLL", "ORACLE_KEEPER_EVERY", "ORACLE_TX_POLL", "ORACLE_KEEPER_BUDGET"):
            self.assertIn(f"    {name} ", cli.__doc__)


class TableOnV3(unittest.TestCase):
    """VP2 (audit F1 on live v3): where FeesV3 has no `drawEpoch`, the table posts no family that isn't priced yet."""

    CLAUDE = v3.name_id("anthropic.claude")  # the deployment's name for the family it prices

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def table(self, v31: bool, list_prices=None):
        net = Net(Path(tempfile.mkdtemp(dir=self.tmp)))
        c = net.chain
        c.v31_fees = v31
        c.priced = [FAMILY, self.CLAUDE]
        probes = []
        draw_epoch = c.draw_epoch
        c.draw_epoch = lambda s: probes.append(s) or draw_epoch(s)
        kw = {} if list_prices is None else {"list_prices": list_prices}
        node = net.node(0, table=True, **kw)
        _, families, tokens = node.post_table()
        node.post_table()
        self.assertEqual(probes, [0])  # probed once
        return dict(zip(families, tokens)), net.logs

    def test_on_v3_only_priced_families_are_posted(self):
        table, logs = self.table(v31=False)
        self.assertNotIn(v3.name_id("openai/gpt"), table)
        self.assertNotIn(v3.name_id("anthropic/claude"), table)
        self.assertEqual(set(table), {FAMILY, self.CLAUDE})
        self.assertEqual(table[self.CLAUDE], [4_000_000, 200_000, 20_000_000])  # the price in force
        self.assertEqual(sum("no drawEpoch" in line for line in logs), 1)

    def test_on_v31_every_listed_family_is_posted(self):
        table, logs = self.table(v31=True)
        self.assertIn(v3.name_id("openai/gpt"), table)
        self.assertEqual(len(table), len(node_v3.default_list_prices()) + 2)
        self.assertFalse(any("no drawEpoch" in line for line in logs))

    def test_a_v31_function_refusing_check_0_still_counts_as_v31(self):
        net = Net(self.tmp)
        node = net.node(0, table=True)

        def refuse(s):
            raise Reverted("Unknown()", "0x" + abi.selector("Unknown()").hex())
        net.chain.draw_epoch = refuse
        self.assertTrue(node.fees_draw_epoch())

    def test_an_empty_list_gives_the_v3_rules_table(self):
        """ORACLE_LIST_PRICES={} (the measured image's route on live v3): the same table as the v3 rule."""
        from oracle import __main__ as cli

        empty = cli._json_setting("{}")
        self.assertEqual(empty, {})
        on_v31, _ = self.table(v31=True, list_prices=empty)
        on_v3, _ = self.table(v31=False)
        self.assertEqual(on_v31, on_v3)


class Registering(unittest.TestCase):
    def _agent(self):
        calls = []

        class Agent(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append((self.path, body))
                out = ({"key": "11" * 32, "signature_chain": []} if self.path == "/GetKey" else
                       {"quote": hashlib.sha256(body["report_data"].encode()).hexdigest(), "event_log": "[]"})
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        srv = HTTPServer(("127.0.0.1", 0), Agent)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}", calls

    def test_the_simulated_attestation_is_the_dstack_simulators_quote(self):
        endpoint, calls = self._agent()
        keys = DstackKeys("pof/oracle/31337/race", endpoint=endpoint)  # ORACLE_KEYS=dstack, the simulator's endpoint
        chain = FakeChain()
        wallet = FakeWallet(chain, keys.address())
        with tempfile.TemporaryDirectory() as tmp:
            r = node_v3.register(chain, keys, wallet, 100 * 10**6, Path(tmp), log=lambda m: None, proof="simulated",
                                 family="fake", host="home", image=IMAGE, tee_type="intel-tdx")
            report = crypto.keccak256(node_v3.REGISTRATION_NOTE + chain.domain() + v3.address_word(keys.address()))
            self.assertEqual(calls[-1], ("/GetQuote", {"report_data": report.hex() + "00" * 32}))
            quote = hashlib.sha256((report.hex() + "00" * 32).encode()).digest()
            self.assertEqual(r.attestation, crypto.keccak256(quote))
            kept = json.loads((Path(tmp) / "v3" / f"attestation-{r.attestation.hex()}.json").read_text())
            self.assertEqual(kept["kind"], "dstack-simulator")
        val = chain.validator(keys.address())
        self.assertEqual((val["state"], val["bond"], val["proofType"]),
                         (v3.CANDIDATE, 100 * 10**6, "0x" + v3.PROOF_SIMULATED.hex()))
        self.assertEqual(chain.names(), ["approve", "register"])
        self.assertEqual((r.family, r.host, r.tee_type), (v3.name_id("fake"), v3.name_id("home"),
                                                          v3.name_id("intel-tdx")))
        node_v3.leave(chain, keys, wallet, log=lambda m: None)
        self.assertEqual(chain.validator(keys.address())["state"], v3.LEAVING)
        with self.assertRaises(Reverted):
            node_v3.leave(chain, keys, wallet, log=lambda m: None)  # already leaving

    def test_keys_without_a_simulator_cant_register_as_simulated(self):
        chain, keys = FakeChain(), LocalDevKeys(0)
        with self.assertRaises(SetupError):
            node_v3.register(chain, keys, FakeWallet(chain, keys.address()), 100 * 10**6, log=lambda m: None,
                             proof="simulated", family="fake", host="home", image=IMAGE)
        with self.assertRaises(SetupError):  # below the floor: refused before anything is sent
            node_v3.register(chain, SimKeys(0), FakeWallet(chain, keys.address()), 10**6, log=lambda m: None,
                             proof="simulated", family="fake", host="home", image=IMAGE)
        self.assertEqual(chain.txs, [])

    def test_a_zktls_registration_has_no_tee_fields(self):
        r, doc = node_v3.registration(FakeChain(), LocalDevKeys(0), proof="zktls", family="openai/gpt", host="pc",
                                      image=IMAGE)
        self.assertEqual((r.proof_type, r.tee_type, r.attestation, r.level, r.firmware, doc),
                         (v3.PROOF_ZKTLS, v3.ZERO, v3.ZERO, 0, 0, {}))

    def test_the_radicle_node_key_is_signed_with_the_registration(self):
        """#251, L11: the node key is the registration's last field, in the typehash, the digest and the tuple."""
        node = bytes(range(32))
        plain, _ = node_v3.registration(FakeChain(), LocalDevKeys(0), proof="zktls", family="f", host="h", image=IMAGE)
        r, _ = node_v3.registration(FakeChain(), LocalDevKeys(0), proof="zktls", family="f", host="h", image=IMAGE,
                                    rad_node=node)
        self.assertEqual((plain.rad_node, r.rad_node, r.as_tuple()[-1]), (v3.ZERO, node, node))
        self.assertTrue(v3.REGISTRATION_TYPE.endswith(",uint32 firmware,bytes32 radNode)"))
        self.assertNotEqual(r.digest(b"d" * 32), plain.digest(b"d" * 32))
        with self.assertRaises(SetupError):
            node_v3.registration(FakeChain(), LocalDevKeys(0), proof="zktls", family="f", host="h", image=IMAGE,
                                 rad_node=b"short")

    def test_the_command_lines_radicle_node(self):
        """`oracle register --rad-node`: a did:key, a Node ID, hex, `none`, or the node's own `rad self --did`; never a
        silent default."""
        from types import SimpleNamespace

        from oracle import delegates

        did = "did:key:z6MkopH5QMoynapxG9Yis4TCpWgyaxQNEBeiL39wqJ2GZCR1"
        key = delegates.key_from_did(did)
        self.assertEqual(node_v3.rad_node_arg(did, {}), key)
        self.assertEqual(node_v3.rad_node_arg(did[len("did:key:"):], {}), key)
        self.assertEqual(node_v3.rad_node_arg("0x" + key.hex(), {}), key)
        self.assertEqual(node_v3.rad_node_arg("none", {}), v3.ZERO)
        seen = []

        def rad(cmd, **kw):
            seen.append(cmd)
            return SimpleNamespace(returncode=0, stdout=did + "\n")
        self.assertEqual(node_v3.rad_node_arg("", {"ORACLE_RADICLE_EXEC": "docker exec -i node"}, run=rad), key)
        self.assertEqual(seen, [["docker", "exec", "-i", "node", "rad", "self", "--did"]])
        with self.assertRaises(SetupError) as e:
            node_v3.rad_node_arg("", {}, run=lambda cmd, **kw: SimpleNamespace(returncode=127, stdout=""))
        self.assertIn("--rad-node none", str(e.exception))
        with self.assertRaises(SetupError):
            node_v3.rad_node_arg("did:key:zNotAnEd25519Key", {})


class Transport(unittest.TestCase):
    def test_onchain_is_v3s_default_and_the_relay_stays_optional(self):
        chain = FakeChain()
        ex = exchange_from_env({}, RACE, chain=chain, keys=LocalDevKeys(0), wallet=FakeWallet(chain, "0x" + "01" * 20))
        self.assertIsInstance(ex, OnchainExchange)
        both = exchange_from_env({"ORACLE_EXCHANGE_TRANSPORT": "onchain,http",
                                  "ORACLE_EXCHANGE_URL": "https://devnet.example/exchange"}, RACE, chain=chain,
                                 keys=LocalDevKeys(0), wallet=FakeWallet(chain, "0x" + "01" * 20))
        self.assertEqual(both.name, "onchain,http")
        v2_default = exchange_from_env({"ORACLE_EXCHANGE": "/tmp/x"}, RACE)
        self.assertEqual(v2_default.name, "folder")  # v2 is unchanged

    def test_it_reads_the_seats_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            net = Net(Path(tmp))
            c = net.chain
            pid = c.add_panel(1, v3.COUNTED, net.addresses(0, 1))
            ex = net.nodes[0].exchange
            net.tick([net.nodes[0]])
            me = net.keys[0].address().lower()
            self.assertEqual(list(ex.all(pid, "seal")), [me])
            self.assertEqual(ex.all(pid, "reveal"), {})
            with self.assertRaises(ValueError):
                ex.all(pid, "merged")  # a v2 message: not carried on-chain
            with self.assertRaises(Reverted):  # the contract refuses a reveal in the seal window
                ex.put(pid, net.keys[0].address(), "reveal", {"vote": True, "mask": 0, "salt": "0x" + "00" * 32,
                                                               "sig": "0x" + "00" * 65})


# ---------- zkTLS: the interface, checked with task 1.9's recorded proof ----------

class RecordedProver(zktls.Prover):
    """Stands in for the pinned tlsn build: it "proves" the one call task 1.9 recorded."""

    def __init__(self):
        self.receipt = json.loads(RECORDED.read_text())
        recv = bytes.fromhex(self.receipt["recv"]["bytes"])
        self.body = recv.split(b"\r\n\r\n", 1)[1]
        self.calls = 0

    def call(self, method, url, headers, body, timeout):
        self.calls += 1
        proven = zktls.check(self.receipt)
        return Reply(200, {}, self.body), zktls.Proof(self.receipt, proven["notary"])


class ProvenJudge:
    """A judge whose model call goes through a prover, as the direct judge's client does with ProvingRequest."""

    reads_evidence = False

    def __init__(self, request):
        self.request = request

    def judge(self, case, tests):
        reply = self.request("POST", "https://bedrock-runtime.us-east-1.amazonaws.com/model/x/converse", {}, b"{}", 5)
        text = json.loads(reply.body)["output"]["message"]["content"][0]["text"]
        return Answer("PASS" in text, "us.anthropic.claude-haiku-4-5", "direct:bedrock", "prompt", text,
                      {"input_tokens": 37, "output_tokens": 5})


class ZkTls(unittest.TestCase):
    def test_the_recorded_proof_checks_offline(self):
        receipt = json.loads(RECORDED.read_text())
        out = zktls.check(receipt, server="bedrock-runtime.us-east-1.amazonaws.com",
                          notaries=["0xCA5064d5dA7A391f1FEd7dAbE591d502B59d7944"])
        self.assertEqual(out["tls_version"], "V1_2")
        with self.assertRaises(zktls.ProofError):
            zktls.check(receipt, server="api.example.com")
        with self.assertRaises(zktls.ProofError):
            zktls.check(receipt, notaries=["0x" + "11" * 20])  # a notary that isn't listed
        with self.assertRaises(zktls.ProofError):
            zktls.check(receipt, body=b"another answer")
        bad = copy.deepcopy(receipt)
        bad["header_bcs"] = bad["header_bcs"][:6] + ("0" if bad["header_bcs"][6] != "0" else "1") + bad["header_bcs"][7:]
        with self.assertRaises(zktls.ProofError):
            zktls.check(bad)
        other = copy.deepcopy(receipt)
        other["implementation"] = "tlsn v0.1.0-alpha.16"
        with self.assertRaises(zktls.ProofError):
            zktls.check(other)

    def test_the_real_prover_is_a_stub_that_says_so(self):
        with self.assertRaises(zktls.Unavailable):
            zktls.TlsnProver.from_env({}).call("POST", "https://api.example.com/v1", {}, b"{}", 5)
        self.assertIn("STUB", zktls.TlsnProver.__doc__)

    def test_a_level_c_validators_receipt_names_its_notary_and_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            net = Net(Path(tmp))
            c = net.chain
            c.validators[net.keys[0].address().lower()]["proofType"] = "0x" + v3.PROOF_ZKTLS.hex()
            with self.assertRaises(SetupError):
                net.node(0).tick(0)  # a level C validator without a prover
            proving = zktls.ProvingRequest(RecordedProver())
            node = net.node(0, judge=ProvenJudge(proving), prover=proving)
            pid = c.add_panel(1, v3.COUNTED, net.addresses(0))
            net.judge_through([node])
            doc = node.receipts3.get(c.seat(pid, 0)["receipt"])
            on = v3.Receipt.from_json(doc["onchain"])
            self.assertEqual(on.proof_type, v3.PROOF_ZKTLS)
            self.assertEqual(on.notary, v3.address_word("0xCA5064d5dA7A391f1FEd7dAbE591d502B59d7944"))
            self.assertEqual(on.proof, zktls.Proof(doc["proof"]["zktls"], "").hash())
            zktls.check(doc["proof"]["zktls"])  # anyone can check it offline from the stored document
            self.assertIsNone(proving.take())  # one proof, one receipt


if __name__ == "__main__":
    unittest.main()
