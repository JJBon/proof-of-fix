"""Delegates follow the seats (proof-of-fix#251, design L11, model (a); task 4.1): the pure rules, promoted from the
Radicle spike (spikes/radicle/seats.py, which now imports them from here).

Under model (a) the validators seated on-chain (`Validators.isDrawable`) are the Radicle repository's delegates, with
a majority threshold. The chain knows a validator by its Ethereum key; Radicle knows a delegate by its node key (a
`did:key`). What links the two is a **seat-to-node mapping**, `SeatNodes.node_of(validator) -> did | None`, with two
implementations:

- `ChainSeatNodes`, what the spec asks for ("A seat maps to one Radicle node key on-chain"; the owner's choice of
  2026-11-20): each validator signs its node's 32-byte Ed25519 public key into its v3 registration
  (`Registration.radNode`), and the registry holds it, readable by anyone (`Validators.radNodeOf`). A seat registered
  with 0 has no node: it's reported as unmapped and never counted as a delegate. The registry refuses a node key
  another registration still holds, so two seats never name one node;
- `DocumentBindings`, kept only for a deployment whose Validators predates the field: each validator signs a binding
  of its node's DID with its validator key, and the bindings travel inside the identity document (payload
  `xyz.proofoffix.seats` -> `bindings`: {did: {"validator": 0x..., "sig": 0x...}}), as the first spike carried them.

On top of the mapping:

- `verify_delegates` (anyone): the identity document's delegates are exactly the seats' nodes, with a majority
  threshold; a seat with no node is reported as unmapped;
- `review_revision` (each honest seated node, before it signs a proposed identity revision);
- `identity_step`: one pending identity revision at a time (Radicle 1.10.3 blocks a delegate's second proposal while
  an earlier one is pending): review the oldest pending revision, in order; propose only when none is pending;
- `update_args` (the `rad id update` arguments) and `patch_pulls` (a node's patches as the revisions its fix source
  reads, task 4.2).

Standard library and the node's own crypto only."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .crypto import keccak256, recover

PAYLOAD = "xyz.proofoffix.seats"
PROJECT = "xyz.radicle.project"
DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{40,50}$")
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
TAG = b"proof-of-fix radicle seat binding v1"
ED25519_PUB = b"\xed\x01"  # the multicodec prefix of an Ed25519 public key, as did:key spells a Radicle node ID
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

ACCEPT, REJECT, PROPOSE, WAIT, IN_SYNC = "accept", "reject", "propose", "wait", "in-sync"


def nid(did: str) -> str:
    """A DID's Node ID (what Radicle's refs and verdicts are keyed by)."""
    return did[len("did:key:"):] if did.startswith("did:key:") else did


def majority(n: int) -> int:
    """The threshold design L11 gives model (a): a majority of the delegates."""
    if n < 1:
        raise ValueError("no delegates")
    return n // 2 + 1


# ---------- did:key <-> the Ed25519 key a contract would hold ----------

def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    out = ""
    while n:
        n, r = divmod(n, 58)
        out = B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def _b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        i = B58.find(ch)
        if i < 0:
            raise ValueError(f"not base58: {ch!r}")
        n = n * 58 + i
    body = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\0" * (len(text) - len(text.lstrip("1"))) + body


def did_from_key(key: bytes) -> str:
    """A Radicle node's DID from its 32-byte Ed25519 public key (did:key, multibase base58btc)."""
    if len(key) != 32:
        raise ValueError(f"an Ed25519 public key has 32 bytes, not {len(key)}")
    return "did:key:z" + _b58encode(ED25519_PUB + key)


def key_from_did(did: str) -> bytes:
    """The 32-byte Ed25519 public key a node's DID names (the inverse of `did_from_key`)."""
    if not did.startswith("did:key:z"):
        raise ValueError(f"not a did:key: {did!r}")
    raw = _b58decode(did[len("did:key:z"):])
    if len(raw) != 34 or raw[:2] != ED25519_PUB:
        raise ValueError(f"not an Ed25519 did:key: {did!r}")
    return raw[2:]


# ---------- the spike's bindings ----------

def binding_digest(chain_id: int, registry: str, rid: str, did: str) -> bytes:
    """What a validator signs to bind its Radicle node to its seat: the deployment (chain id, registry), the
    repository (RID) and the node's DID. A binding is valid for that repository on that deployment only."""
    if not ADDR_RE.match(registry):
        raise ValueError(f"not an address: {registry!r}")
    return keccak256(TAG + b"\0" + chain_id.to_bytes(32, "big") + bytes.fromhex(registry[2:]) + b"\0"
                     + rid.encode() + b"\0" + did.encode())


def make_binding(sign, address: str, chain_id: int, registry: str, rid: str, did: str) -> dict:
    """A binding entry: `sign` is the validator's signer (a 32-byte digest -> 65-byte signature)."""
    return {"validator": address, "sig": "0x" + sign(binding_digest(chain_id, registry, rid, did)).hex()}


def binding_signer(entry: dict, chain_id: int, registry: str, rid: str, did: str) -> str | None:
    """The validator address a binding entry was signed by, if its signature recovers to the address it names."""
    try:
        sig = bytes.fromhex(str(entry.get("sig", ""))[2:])
        who = recover(binding_digest(chain_id, registry, rid, did), sig)
    except (ValueError, TypeError, AttributeError):
        return None
    named = str(entry.get("validator", ""))
    return who if ADDR_RE.match(named) and who.lower() == named.lower() else None


def bindings_of(doc: dict | None) -> dict:
    return dict((((doc or {}).get("payload") or {}).get(PAYLOAD) or {}).get("bindings") or {})


# ---------- the seat-to-node mapping ----------

class SeatNodes:
    """Which Radicle node (DID) a seated validator's is. `node_of` returns None for a seat with no node (unmapped);
    the rules never count such a seat as a delegate. `for_document` is the mapping a given identity document shows
    (the chain's doesn't depend on the document; the spike's bindings travel in it, `in_document`)."""

    in_document = False

    def node_of(self, validator: str) -> str | None:
        raise NotImplementedError

    def why_unmapped(self, validator: str) -> str:
        return "no Radicle node ID is recorded for it"

    def why_not(self, did: str) -> str:
        return "isn't the Radicle node of any seat on-chain"

    def binding_for(self, did: str) -> dict | None:
        """The binding entry a revision's payload must carry for `did` (None: the mapping needs none)."""
        return None

    def for_document(self, doc: dict) -> "SeatNodes":
        return self


class DocumentBindings(SeatNodes):
    """The first spike's mapping, the fallback for a deployment whose Validators has no `radNodeOf` (before #251's
    contract change): signed bindings, read from an identity document
    (`doc`) and from bindings this node knows itself (`known`: DID -> entry, e.g. its own, or ones its operator
    collected). A validator bound to two nodes maps to none."""

    in_document = True

    def __init__(self, chain_id: int, registry: str, rid: str, doc: dict | None = None, known: dict | None = None):
        self.chain_id, self.registry, self.rid = chain_id, registry, rid
        self.entries: dict = {}
        self.signer: dict = {}  # did -> the validator its entry recovers to (None: it doesn't)
        self.by_validator: dict = {}  # validator (lower) -> [did]
        for did, entry in {**bindings_of(doc), **dict(known or {})}.items():
            self.know(did, entry)

    def know(self, did: str, entry) -> None:
        """Adds (or replaces) the binding entry for `did`."""
        old = self.signer.pop(did, None)
        if old is not None:
            self.by_validator[old.lower()].remove(did)
        self.entries[did] = entry
        who = binding_signer(entry, self.chain_id, self.registry, self.rid, did) if isinstance(entry, dict) else None
        self.signer[did] = who
        if who is not None:
            self.by_validator.setdefault(who.lower(), []).append(did)

    def node_of(self, validator: str) -> str | None:
        dids = self.by_validator.get(validator.lower(), [])
        return dids[0] if len(dids) == 1 else None

    def why_unmapped(self, validator: str) -> str:
        dids = sorted(self.by_validator.get(validator.lower(), []))
        if len(dids) > 1:
            return f"validator {validator.lower()} is bound to two delegates ({', '.join(dids)})"
        return "no seat binding names it"

    def why_not(self, did: str) -> str:
        entry = self.entries.get(did)
        if entry is None:
            return "has no seat binding"
        who = self.signer.get(did)
        if who is None:
            named = entry.get("validator") if isinstance(entry, dict) else None
            return f"its binding's signature doesn't recover to {named}"
        if len(self.by_validator.get(who.lower(), [])) > 1:
            return self.why_unmapped(who)
        return f"is bound to {who}, which isn't seated on-chain"

    def binding_for(self, did: str) -> dict | None:
        return self.entries.get(did)

    def for_document(self, doc: dict) -> "DocumentBindings":
        return DocumentBindings(self.chain_id, self.registry, self.rid, doc)


def parse_node(text: str) -> bytes:
    """A Radicle node key as a registration signs it (32 bytes, Ed25519) from a `did:key:z6Mk…` (`rad self --did`), a
    Node ID `z6Mk…` (`rad self --nid`) or 0x and 64 hex digits. Raises ValueError on anything else; zero is returned
    as it is (the caller decides whether "no node" is allowed)."""
    t = (text or "").strip()
    if t.startswith("0x"):
        if not re.fullmatch(r"0x[0-9a-fA-F]{64}", t):
            raise ValueError(f"a node key in hex is 0x and 64 hex digits, not {t!r}")
        return bytes.fromhex(t[2:])
    did = t if t.startswith("did:key:") else "did:key:" + t
    if not DID_RE.match(did):
        raise ValueError(f"not a Radicle node ID (did:key:z6Mk…, z6Mk… or 0x and 64 hex digits): {t!r}")
    return key_from_did(did)


class ChainSeatNodes(SeatNodes):
    """The mapping the spec asks for: each seat's Radicle node key read from the chain (`Validators.radNodeOf`, signed
    into the validator's v3 registration). `read(validator)` returns the 32-byte key the registry holds for it (zero
    or empty: none, the seat is unmapped). A registration can't change, so a key read once is kept."""

    def __init__(self, read) -> None:
        if read is None:
            raise ValueError("ChainSeatNodes needs a reader of Validators.radNodeOf")
        self.read = read
        self._known: dict = {}

    @classmethod
    def of(cls, chain) -> "ChainSeatNodes":
        """The mapping of a v3 chain view (oracle/v3.py's `Chain.rad_node_of`)."""
        return cls(chain.rad_node_of)

    def key_of(self, validator: str) -> bytes:
        v = validator.lower()
        if v not in self._known:
            key = bytes(self.read(validator) or b"")
            if not any(key):
                return b""
            self._known[v] = key
        return self._known[v]

    def node_of(self, validator: str) -> str | None:
        key = self.key_of(validator)
        return did_from_key(key) if key else None

    def why_unmapped(self, validator: str) -> str:
        return f"validator {validator.lower()} registered no Radicle node key on-chain (Validators.radNodeOf is 0)"

    def why_not(self, did: str) -> str:
        return "isn't the Radicle node any seat registered on-chain"


# ---------- verify-delegates and the review of a revision ----------

@dataclass
class Comparison:
    """An identity document against the seats on-chain."""
    problems: list = field(default_factory=list)  # every difference, by name
    unmapped: list = field(default_factory=list)  # seats with no node (reported; never counted as delegates)
    mapped: dict = field(default_factory=dict)  # seat (lower) -> its node's DID


def compare(doc: dict, seats, nodes: SeatNodes) -> Comparison:
    """`doc`'s delegates against the nodes of `seats`, as `nodes` (the mapping this document shows) gives them."""
    c = Comparison()
    seated = sorted({s.lower() for s in seats})
    owner: dict = {}  # did -> seat
    for s in seated:
        did = nodes.node_of(s)
        if did is None:
            c.unmapped.append(s)
            c.problems.append(f"seat {s} has no delegate: {nodes.why_unmapped(s)} (unmapped)")
            continue
        if did in owner:
            c.problems.append(f"seats {owner[did]} and {s} name the same node {did}")
            continue
        owner[did] = s
        c.mapped[s] = did
    delegates = list(doc.get("delegates") or [])
    for did in delegates:
        if did not in owner:
            c.problems.append(f"delegate {did} {nodes.why_not(did)}")
    for s, did in c.mapped.items():
        if did not in delegates:
            c.problems.append(f"seat {s}'s node {did} isn't a delegate")
    if delegates and int(doc.get("threshold", 0)) != majority(len(delegates)):
        c.problems.append(f"threshold {doc.get('threshold')} isn't a majority of {len(delegates)} delegates "
                          f"({majority(len(delegates))})")
    if not delegates:
        c.problems.append("no delegates")
    return c


def verify_delegates(doc: dict, seats, nodes: SeatNodes) -> tuple:
    """`verify-delegates`: the identity document's delegates are exactly the seats' nodes, with a majority threshold,
    and every seat has a node. Returns (ok, problems); every problem names what differs, an unmapped seat included."""
    c = compare(doc, seats, nodes.for_document(doc))
    return not c.problems, c.problems


def review_revision(current: dict, proposed: dict, seats, nodes: SeatNodes, published: dict, head: str) -> tuple:
    """An honest seated node's rule for signing a proposed identity revision (specs/radicle-hosting, "Delegates follow
    the seats"). Accept only when: the proposed delegates are the nodes of the seats on-chain, with a majority
    threshold (a seat with no node is left out, never given a key); the revision doesn't drop or change a seat's node
    that the current document or this node knows; every delegate it adds has published `main` at `Heads.head`
    (`published`: Node ID -> that namespace's `main`, as this node has it); and nothing but the delegates, the
    threshold and the bindings changes. Returns (accept, reason)."""
    view = nodes.for_document(proposed)
    c = compare(proposed, seats, view)
    wrong = [p for p in c.problems if "(unmapped)" not in p]
    if wrong:
        return False, "; ".join(wrong)
    if not proposed.get("delegates"):
        return False, "no delegates"
    before = nodes.for_document(current)
    for s in c.unmapped:
        known = nodes.node_of(s) or before.node_of(s)
        if known is not None:
            return False, f"the revision drops seat {s}'s node {known}"
    for s, did in c.mapped.items():
        known = nodes.node_of(s) or before.node_of(s)
        if known is not None and known != did:
            return False, f"the revision changes seat {s}'s node from {known} to {did}"
    added = [d for d in proposed.get("delegates", []) if d not in set(current.get("delegates", []))]
    for did in added:
        tip = published.get(nid(did))
        if tip != head:
            return False, f"new delegate {did} hasn't published main at the head {head[:12]} (has {tip or 'none'})"
    keep_before = {k: v for k, v in (current.get("payload") or {}).items() if k != PAYLOAD}
    keep_after = {k: v for k, v in (proposed.get("payload") or {}).items() if k != PAYLOAD}
    if keep_before != keep_after:
        return False, "the revision changes more than the delegates, the threshold and the bindings"
    left = f"; {len(c.unmapped)} seat(s) unmapped, left out" if c.unmapped else ""
    return True, (f"delegates = the nodes of the {len(c.mapped)} seats on-chain, threshold "
                  f"{proposed['threshold']}{left}")


def update_args(current: dict, seats_to_did: dict, bindings: dict | None = None) -> list:
    """The `rad id update` arguments that turn `current` into the document whose delegates are `seats_to_did`'s DIDs,
    with a majority threshold, and, when the mapping travels in the document, those bindings (DID -> entry)."""
    want = sorted(set(seats_to_did.values()))
    have = list(current.get("delegates", []))
    args = []
    for d in want:
        if d not in have:
            args += ["--delegate", d]
    for d in have:
        if d not in want:
            args += ["--rescind", d]
    args += ["--threshold", str(majority(len(want)))]
    if bindings is not None:
        args += ["--payload", PAYLOAD, "bindings", json.dumps({d: bindings[d] for d in want}, sort_keys=True,
                                                              separators=(",", ":"))]
    return args


# ---------- one pending identity revision at a time ----------

@dataclass(frozen=True)
class Step:
    action: str  # ACCEPT, REJECT, PROPOSE, WAIT or IN_SYNC
    reason: str
    revision: str = ""  # the revision to accept or reject
    args: tuple = ()  # PROPOSE: the `rad id update` arguments


def pending_revisions(cob: dict) -> list:
    """The identity's pending revisions (state "active", not the current one), oldest first (the COB's timeline)."""
    revs = cob.get("revisions") or {}
    order = list(cob.get("timeline") or []) or sorted(revs, key=lambda r: (revs[r] or {}).get("timestamp", 0))
    return [revs[r] for r in order if revs.get(r) and revs[r].get("state") == "active" and r != cob.get("current")]


def identity_step(cob: dict, seats, nodes: SeatNodes, published: dict, head: str, me: str) -> Step:
    """What this seated node does next with the identity (`cob`: `rad cob show --type xyz.radicle.id`). While a
    revision is pending it reviews the oldest one it hasn't voted on yet, by `review_revision`, and proposes nothing;
    with none pending, it proposes the revision whose delegates are the seats' nodes when the document differs and
    the proposal would pass its own review. `me`: this node's DID."""
    current = (cob.get("revisions") or {}).get(cob.get("current"), {}).get("doc") or {}
    mine = nid(me)
    delegate = mine in {nid(d) for d in current.get("delegates", [])}
    pending = pending_revisions(cob)
    if pending:
        oldest = pending[0]
        rid_ = oldest.get("id", "")
        votes = oldest.get("verdicts") or {}
        accepts = sum(1 for v in votes.values() if isinstance(v, dict) and "Accept" in v)
        tally = f"{accepts} of the {current.get('threshold', '?')} accepts needed"
        if not delegate:
            return Step(WAIT, f"revision {rid_[:7]} is pending ({tally}); this node isn't a delegate, so it can't vote")
        if mine in votes:
            return Step(WAIT, f"revision {rid_[:7]} is pending ({tally}); this node voted; nothing is proposed while "
                              f"it's pending")
        ok, why = review_revision(current, oldest.get("doc") or {}, seats, nodes, published, head)
        return Step(ACCEPT if ok else REJECT, f"revision {rid_[:7]}: {why}", revision=rid_)
    ok, problems = verify_delegates(current, seats, nodes)
    if ok:
        return Step(IN_SYNC, f"the delegates are the nodes of the {len(current.get('delegates', []))} seats on-chain")
    if not delegate:
        return Step(WAIT, "the delegates differ from the seats (" + "; ".join(problems) + "); this node isn't a "
                          "delegate, so it can't propose")
    view = nodes.for_document(current)
    mapped, bindings = {}, {}
    for s in sorted({x.lower() for x in seats}):
        did = nodes.node_of(s) or view.node_of(s)
        if did is not None:
            mapped[s] = did
            entry = nodes.binding_for(did) or view.binding_for(did)
            if entry is not None:
                bindings[did] = entry
    if not mapped:
        return Step(WAIT, "no seat on-chain has a known Radicle node: nothing to propose")
    travels = nodes.in_document
    if travels and set(bindings) != set(mapped.values()):
        missing = sorted(set(mapped.values()) - set(bindings))
        return Step(WAIT, f"no binding to carry for {', '.join(missing)}: nothing proposed")
    want = sorted(set(mapped.values()))
    payload = dict(current.get("payload") or {})
    if travels:
        payload[PAYLOAD] = {**(payload.get(PAYLOAD) or {}), "bindings": {d: bindings[d] for d in want}}
    proposed = {**current, "delegates": want, "threshold": majority(len(want)), "payload": payload}
    if (sorted(current.get("delegates", [])) == want and current.get("threshold") == proposed["threshold"]
            and current.get("payload") == payload):
        return Step(WAIT, "the delegates are the nodes of every mapped seat; " + "; ".join(problems))
    ok, why = review_revision(current, proposed, seats, nodes, published, head)
    if not ok:
        return Step(WAIT, f"the revision the seats call for wouldn't pass review yet: {why}")
    return Step(PROPOSE, f"proposing delegates = the nodes of the {len(want)} mapped seats, threshold "
                         f"{proposed['threshold']} (" + "; ".join(problems) + ")",
                args=tuple(update_args(current, mapped, bindings if travels else None)))


# ---------- patches (task 4.2) ----------

def patch_pulls(cobs: list) -> list:
    """A node's Radicle patches (`rad cob show --type xyz.radicle.patch` objects, with their ids under "_id") as the
    revisions the v3 node's fix source reads: one per revision, its description as the body (the claim pofctl writes),
    its head commit and its base."""
    pulls = []
    for cob in cobs:
        pid = str(cob.get("_id", ""))
        for rid_, rev in (cob.get("revisions") or {}).items():
            if not rev:  # a redacted revision
                continue
            body = "\n".join(str(d.get("body", "")) for d in rev.get("description") or [] if isinstance(d, dict))
            pulls.append({"number": int(pid[:7] or "0", 16) if re.fullmatch(r"[0-9a-f]+", pid[:7] or "") else 0,
                          "patch": pid, "revision": rid_, "title": cob.get("title", ""), "body": body,
                          "head_sha": str(rev.get("oid", "")), "base_sha": str(rev.get("base", "")),
                          "state": (cob.get("state") or {}).get("status", "open")})
    return pulls
