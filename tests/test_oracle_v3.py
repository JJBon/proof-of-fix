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
from oracle.rpc import Reverted
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
    node must respect: a seal within its window and signed; a reveal only after the seal window, once every seat of a
    judging panel has sealed, signed, and opening the seal; a receipt in the reveal window; a usage report bound to the
    on-chain receipt; a table only from an active validator. Every transaction is recorded in `txs`, in order."""

    version = 3
    race, panels, fees, registry = RACE, PANELS, FEES, REGISTRY
    rpc = None

    def __init__(self) -> None:
        self.time, self.height = 1_000_000, 100
        self.validators: dict = {}
        self.panels_: dict = {}
        self.subs: dict = {}  # id -> the race's submission
        self.verdicts: dict = {}  # id -> Panels' record
        self.issues: dict = {1: {"repo": "0x" + "00" * 32, "reporter": crypto.checksum("0x" + "77" * 20), "check": 0,
                                 "bounty": 1, "state": 1, "hidden": False, "registration": 0, "stake": 0}}
        self.usage: dict = {}
        self.txs: list = []
        self.allowances: dict = {}
        self.challenges: list = []
        self.posted: dict = {}
        self.period, self.rolled_ = 0, 0
        self.priced = [FAMILY]
        self.bounties: dict = {}  # b -> the race's bounty, beyond {"issue": 1}
        self.awards: dict = {}  # (b, epoch) -> award
        self.live = {"stuckGrace": 86400, "retryDelay": 86400, "maxRedraws": 3, "capWindow": 3600,
                     "challengeDeadline": 120 * 3600}
        self.settled_lapses: list = []

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
                            "waitEpoch": 0, "redraws": 0, "retryAt": 0, "auditStuckAt": 0}

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

    def issue(self, i):
        return dict(self.issues[i])

    def issue_of(self, sub):
        return sub["issue"] if sub["issue"] else self.bounty(sub["bounty"])["issue"]

    def config(self):
        return {"challengeStake": 10 * 10**6}

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

    def _reveal_window(self, p):
        if self.time <= p["sealBy"] or (p["kind"] != v3.SHADOW and p["nSealed"] < p["k"]):
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
        self._reveal_window(p)
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
        self._reveal_window(p)
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
        p["paid"] = True

    def releaseAudits(self, sender, s):  # noqa: N802 (the contract's name)
        v = self.verdicts[s]
        if not v["auditStuckAt"] or self.time <= v["auditStuckAt"] + self.live["stuckGrace"]:
            _fail("NothingDue()")
        v["redraws"] += 1
        v["auditStuckAt"] = self.time

    def refund(self, sender, s):
        """RaceV3.release, as the node calls it on the race (FakeWallet routes it here)."""
        if self.verdicts[s]["status"] != v3.RELEASED or self.subs[s]["done"]:
            _fail("NotYet()")
        self.subs[s].update(done=True, outcome=6)

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
        counted = c.add_panel(1, v3.COUNTED, net.addresses(0))
        net.tick([net.nodes[0]])  # sealed as the counted judge
        c.warp(SEAL_WINDOW + 1)  # its reveal window is open ...
        shadow = c.add_panel(2, v3.SHADOW, net.addresses(0))  # ... and the same node is drawn as a shadow elsewhere
        net.tick([net.nodes[0]])
        mine = [(n, a[0]) for _, n, a in c.txs]
        self.assertLess(mine.index(("seal", shadow)), mine.index(("reveal", counted)))

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
