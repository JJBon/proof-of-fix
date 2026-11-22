"""The aggregator (design D5, D6): collects the nodes' seals, then their reveals, keeps only honest reveals by keys in the
contract's oracle set, and asks the agreeing nodes to sign once at least the quorum agree. Anyone can run one: it holds
no key that matters, and the contract checks everything it relays.

A reveal is refused when:
- it arrives before the seal phase closed, or its node didn't seal (no copying others' verdicts);
- it doesn't match its seal (a changed verdict);
- its receipt doesn't hash to the hash revealed, or names another node (a tampered receipt);
- its signature over the receipt hash doesn't recover to the node;
- its node isn't in the contract's oracle set."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import crypto, receipt as receipts
from .node import Reveal, seal_of


@dataclass
class Decision:
    outcome: int
    signers: list[str]  # the agreeing nodes, ordered by address as the contract requires
    dissent: list[Reveal]


@dataclass
class Round:
    submission: int
    oracle_set: list[str]
    quorum: int
    seals: dict[str, str] = field(default_factory=dict)
    reveals: dict[str, Reveal] = field(default_factory=dict)
    refused: list[tuple[str, str]] = field(default_factory=list)  # (node, why)
    sealing: bool = True

    def __post_init__(self):
        self._set = {a.lower() for a in self.oracle_set}

    def seal(self, node: str, seal: str) -> None:
        if not self.sealing:
            self.refused.append((node, "sealed after the seal phase closed"))
            return
        self.seals[node.lower()] = seal.lower()

    def close_seals(self) -> None:
        self.sealing = False

    def reveal(self, r: Reveal) -> bool:
        who = r.node.lower()
        why = self._check(r)
        if why:
            self.refused.append((r.node, why))
            return False
        self.reveals[who] = r
        return True

    def _check(self, r: Reveal) -> str | None:
        who = r.node.lower()
        if self.sealing:
            return "revealed before the seal phase closed"
        if who not in self.seals:
            return "no seal"
        salt = bytes.fromhex(r.salt.removeprefix("0x"))
        if "0x" + seal_of(r.receipt_hash, r.outcome, salt, r.node).hex() != self.seals[who]:
            return "the reveal doesn't match its seal"
        if receipts.receipt_hash(r.receipt) != r.receipt_hash:
            return "the receipt doesn't match its hash"
        if r.receipt.get("node", "").lower() != who or r.receipt.get("verdict", {}).get("outcome") != r.outcome \
                or r.receipt.get("verdict", {}).get("submission") != self.submission:
            return "the receipt doesn't match the reveal"
        try:
            signer = crypto.recover(crypto.keccak256(bytes.fromhex(r.receipt_hash)),
                                    bytes.fromhex(r.signature.removeprefix("0x")))
        except ValueError as e:
            return f"bad signature: {e}"
        if signer.lower() != who:
            return "the signature isn't the node's"
        if who not in self._set:
            return "not in the contract's oracle set"
        return None

    def decide(self) -> Decision | None:
        """The outcome at least the quorum agree on, or None (nothing is relayed; the contract's timeOut applies)."""
        by_outcome: dict[int, list[Reveal]] = defaultdict(list)
        for r in self.reveals.values():
            by_outcome[r.outcome].append(r)
        winners = [(o, rs) for o, rs in by_outcome.items() if len(rs) >= self.quorum]
        if not winners:
            return None
        outcome, agreeing = max(winners, key=lambda x: len(x[1]))
        dissent = [r for o, rs in by_outcome.items() if o != outcome for r in rs]
        return Decision(outcome, sorted((r.node for r in agreeing), key=lambda a: int(a, 16)), dissent)


def assemble(decision: Decision, signatures: dict[str, str], digest: bytes, quorum: int) -> list[str]:
    """The signatures for the relay, checked against the digest and ordered by signer address."""
    ordered = []
    for signer in decision.signers:
        sig = signatures.get(signer) or signatures.get(signer.lower())
        if sig is None:
            continue
        if crypto.recover(digest, bytes.fromhex(sig.removeprefix("0x"))).lower() != signer.lower():
            raise ValueError(f"{signer}'s signature doesn't recover to it")
        ordered.append(sig)
    if len(ordered) < quorum:
        raise ValueError(f"only {len(ordered)} valid signatures, quorum {quorum}")
    return ordered


class Scoreboard:
    """Canaries (design D5): fixes with a known outcome, sent like real submissions. Each node's record on them."""

    def __init__(self):
        self.record: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # node -> [right, wrong]

    def score(self, reveals: list[Reveal], expected: int) -> None:
        for r in reveals:
            self.record[r.node.lower()][0 if r.outcome == expected else 1] += 1

    def accuracy(self, node: str) -> float | None:
        right, wrong = self.record[node.lower()]
        return right / (right + wrong) if right + wrong else None
