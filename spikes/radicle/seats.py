"""Seats and delegates for the Radicle spike under v3 (proof-of-fix#251, tasks 2.2 and 2.3; design L11).

The rules were promoted into the node for task 4.1 (oracle/delegates.py: the seat-to-node mapping behind
`SeatNodes`, `verify_delegates`, `review_revision`, one pending identity revision at a time, `patch_pulls`). This file
keeps the spike's own signatures over them, with the spike's signed bindings as the mapping; scripts/radicle-spike.sh
--v3 drives them against a local Radicle network and the v3 contracts on anvil (spikes/radicle/v3_spike.py), and
tests/test_radicle_seats.py tests them alone.

Candidate (a) makes the validators seated on-chain the repository's delegates. The chain knows validators by their
Ethereum key; Radicle knows delegates by their node key (a did:key). When the first spike ran, nothing on-chain linked
the two, so each validator signed a **binding** of its node's DID with its validator key, and the bindings travelled
inside the identity document itself, in a payload of our own (`xyz.proofoffix.seats` -> `bindings`: {did:
{"validator": 0x..., "sig": 0x...}}). Since #251's contract change of 2026-11-20 the node key is a signed field of the
v3 registration (`Validators.radNodeOf`): spikes/radicle/v3_spike.py now reads each seat's node from the chain
(oracle/delegates.py `ChainSeatNodes`), and these binding wrappers stay for the bindings' own tests and for a registry
from before the field. Either way anyone holding the identity document and a view of the chain can check it
(`verify_delegates`), and every honest seated node reviews a proposed revision by the same rule before signing it
(`review_revision`).

"Seated" here is `Validators.isDrawable`: active, bonded at least BOND_FLOOR and in standing. That is the set L5 means
(a validator below the floor isn't counted); today's `activeCount` still counts one (finding 7 of the devnet report).

Candidate (b) needs none of this: `verify_head` (oracle/radicle.py) and a checkout of the commit `Heads.head` names."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from oracle import delegates as D  # noqa: E402
from oracle.delegates import (ADDR_RE, DID_RE, PAYLOAD, PROJECT, TAG, binding_digest, binding_signer,  # noqa: E402,F401
                              bindings_of, majority, make_binding, patch_pulls)


def verify_delegates(doc: dict, seats, chain_id: int, registry: str, rid: str) -> tuple:
    """`verify-delegates` with the bindings the document carries as the seat-to-node mapping (D.verify_delegates)."""
    return D.verify_delegates(doc, seats, D.DocumentBindings(chain_id, registry, rid))


def review_revision(current: dict, proposed: dict, seats, published: dict, head: str, chain_id: int, registry: str,
                    rid: str) -> tuple:
    """An honest seated node's review of a proposed revision (D.review_revision), with the bindings as the mapping."""
    return D.review_revision(current, proposed, seats, D.DocumentBindings(chain_id, registry, rid), published, head)


def update_args(current: dict, seats_to_did: dict, bindings: dict) -> list:
    """The `rad id update` arguments for delegates = `seats_to_did`'s DIDs, carrying those bindings."""
    return D.update_args(current, seats_to_did, bindings)
