"""Seats and delegates for the Radicle spike under v3 (proof-of-fix#251, tasks 2.2 and 2.3; design L11).

Pure functions, standard library and the node's own crypto only; scripts/radicle-spike.sh --v3 drives them against a
local Radicle network and the v3 contracts on anvil (spikes/radicle/v3_spike.py), and tests/test_radicle_seats.py
tests them alone.

Candidate (a) makes the validators seated on-chain the repository's delegates. The chain knows validators by their
Ethereum key; Radicle knows delegates by their node key (a did:key). Nothing on-chain links the two (v3's
`Registration` has no field for it), so here each validator signs a **binding** of its node's DID with its validator
key, and the bindings travel inside the identity document itself, in a payload of our own
(`xyz.proofoffix.seats` -> `bindings`: {did: {"validator": 0x..., "sig": 0x...}}). Then anyone holding the identity
document and a view of the chain can check it (`verify_delegates`), and every honest seated node reviews a proposed
revision by the same rule before signing it (`review_revision`).

"Seated" here is `Validators.isDrawable`: active, bonded at least BOND_FLOOR and in standing. That is the set L5 means
(a validator below the floor isn't counted); today's `activeCount` still counts one (finding 7 of the devnet report).

Candidate (b) needs none of this: `verify_head` (oracle/radicle.py) and a checkout of the commit `Heads.head` names."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle.crypto import keccak256, recover  # noqa: E402

PAYLOAD = "xyz.proofoffix.seats"
PROJECT = "xyz.radicle.project"
DID_RE = re.compile(r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{40,50}$")
ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
TAG = b"proof-of-fix radicle seat binding v1"


def majority(n: int) -> int:
    """The threshold design L11 gives candidate (a): a majority of the delegates."""
    if n < 1:
        raise ValueError("no delegates")
    return n // 2 + 1


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
    except (ValueError, TypeError):
        return None
    named = str(entry.get("validator", ""))
    return who if ADDR_RE.match(named) and who.lower() == named.lower() else None


def bindings_of(doc: dict) -> dict:
    return dict(((doc.get("payload") or {}).get(PAYLOAD) or {}).get("bindings") or {})


def verify_delegates(doc: dict, seats, chain_id: int, registry: str, rid: str) -> tuple:
    """`verify-delegates`: the identity document's delegates are exactly the seats on-chain, each bound by its seat's
    signature, with a majority threshold. Returns (ok, problems); every problem names what differs."""
    seated = {s.lower() for s in seats}
    delegates = list(doc.get("delegates") or [])
    bindings = bindings_of(doc)
    problems = []
    bound: dict = {}  # validator -> did
    for did in delegates:
        entry = bindings.get(did)
        if entry is None:
            problems.append(f"delegate {did} has no seat binding")
            continue
        who = binding_signer(entry, chain_id, registry, rid, did)
        if who is None:
            problems.append(f"delegate {did}: its binding's signature doesn't recover to {entry.get('validator')}")
            continue
        if who.lower() not in seated:
            problems.append(f"delegate {did} is bound to {who}, which isn't seated on-chain")
            continue
        if who.lower() in bound:
            problems.append(f"validator {who} is bound to two delegates ({bound[who.lower()]}, {did})")
            continue
        bound[who.lower()] = did
    for s in sorted(seated - set(bound)):
        problems.append(f"seat {s} has no delegate")
    if delegates and int(doc.get("threshold", 0)) != majority(len(delegates)):
        problems.append(f"threshold {doc.get('threshold')} isn't a majority of {len(delegates)} delegates "
                        f"({majority(len(delegates))})")
    if not delegates:
        problems.append("no delegates")
    return not problems, problems


def review_revision(current: dict, proposed: dict, seats, published: dict, head: str, chain_id: int, registry: str,
                    rid: str) -> tuple:
    """An honest seated node's rule for signing a proposed identity revision (specs/radicle-hosting, "Delegates follow
    the seats"). Accept only when: the proposed delegates are the seats on-chain (`verify_delegates`); every delegate
    it adds has published `main` at `Heads.head` (`published`: Node ID -> that namespace's `main`, as this node has
    it); and nothing but the delegates, the threshold and the bindings changes. Returns (accept, reason)."""
    ok, problems = verify_delegates(proposed, seats, chain_id, registry, rid)
    if not ok:
        return False, "; ".join(problems)
    added = [d for d in proposed.get("delegates", []) if d not in set(current.get("delegates", []))]
    for did in added:
        tip = published.get(did.removeprefix("did:key:"))
        if tip != head:
            return False, f"new delegate {did} hasn't published main at the head {head[:12]} (has {tip or 'none'})"
    before = {k: v for k, v in (current.get("payload") or {}).items() if k != PAYLOAD}
    after = {k: v for k, v in (proposed.get("payload") or {}).items() if k != PAYLOAD}
    if before != after:
        return False, "the revision changes more than the delegates, the threshold and the bindings"
    return True, f"delegates = the {len(proposed['delegates'])} seats on-chain, threshold {proposed['threshold']}"


def update_args(current: dict, seats_to_did: dict, bindings: dict) -> list:
    """The `rad id update` arguments that turn `current` into the document whose delegates are `seats_to_did`'s DIDs,
    with a majority threshold and those bindings (validator address -> DID; bindings: DID -> entry)."""
    want = sorted(seats_to_did.values())
    have = list(current.get("delegates", []))
    args = []
    for d in want:
        if d not in have:
            args += ["--delegate", d]
    for d in have:
        if d not in want:
            args += ["--rescind", d]
    args += ["--threshold", str(majority(len(want)))]
    args += ["--payload", PAYLOAD, "bindings", json.dumps({d: bindings[d] for d in want}, sort_keys=True,
                                                          separators=(",", ":"))]
    return args


def patch_pulls(cobs: list) -> list:
    """A node's Radicle patches (`rad cob show --type xyz.radicle.patch` objects, with their ids under "_id") as the
    pull requests the v3 node's fix source reads: one per revision, its description as the body (the claim), its head
    commit and its base."""
    pulls = []
    for cob in cobs:
        pid = cob.get("_id", "")
        for rid_, rev in (cob.get("revisions") or {}).items():
            if not rev:  # a redacted revision
                continue
            body = "\n".join(d.get("body", "") for d in rev.get("description") or [])
            pulls.append({"number": int(pid[:7] or "0", 16), "patch": pid, "revision": rid_, "title": cob.get("title", ""),
                          "body": body, "head_sha": rev.get("oid", ""), "base_sha": rev.get("base", ""),
                          "state": (cob.get("state") or {}).get("status", "open")})
    return pulls
