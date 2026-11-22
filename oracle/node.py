"""The judge node (proof-of-fix#94): check a sealed submission, run its tests in the sandbox, judge it, write a receipt,
seal the verdict, reveal it, and sign the result the contract verifies.

Three rounds with the aggregator (design D5, D6):
1. seal: keccak256(abi.encode(receipt hash, outcome, salt, node)), so no node can copy another's verdict;
2. reveal: the outcome, the receipt and the salt, signed over the receipt hash (the node vouches for its record);
3. sign: once the aggregator names the agreeing signers, the EIP-712 `Result` with one fee to each of them."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import crypto, receipt as receipts
from .judge import case_for
from .keys import KeyProvider
from .sandbox import TestRun, run_tests

ORACLE_FEE = 300_000  # 0.3 coin to each signer, as the loop deploys it (contracts/script/Loop.s.sol)
CHECKER_IMAGE = os.environ.get("POF_ORACLE_IMAGE", "local-unpinned")  # the node's own image digest, set by its container


@dataclass(frozen=True)
class Claim:
    """What a solver reveals to the oracles off-chain: the fix (its tree and files) and the salt it was sealed with."""
    submission: int
    bounty: int
    solver: str
    salt: str  # hex
    tree: str  # git tree hash of the fix, hex without 0x
    src: Path  # the fix's files, with the issue's acceptance test
    issue: str = ""
    diff: str = ""
    repo: str = ""
    commit: str = ""  # the fix's commit message

    @property
    def fix(self) -> bytes:
        return crypto.keccak256(self.tree.encode())  # the fix is its tree, as the loop hashes it with `cast keccak`


@dataclass
class Reveal:
    node: str
    outcome: int
    receipt: dict
    receipt_hash: str
    salt: str
    signature: str  # over keccak256(receipt hash), recovers to `node`


@dataclass
class Verdict:
    claim: Claim
    outcome: int
    receipt: dict
    receipt_hash: str
    salt: bytes = field(default_factory=lambda: secrets.token_bytes(32))

    def seal(self, node: str) -> str:
        return "0x" + seal_of(self.receipt_hash, self.outcome, self.salt, node).hex()


def seal_of(receipt_hash: str, outcome: int, salt: bytes, node: str) -> bytes:
    return crypto.keccak256(bytes.fromhex(receipt_hash) + crypto.word(outcome) + salt + crypto.word(node))


class RefusedClaim(Exception):
    pass


class Node:
    def __init__(self, keys: KeyProvider, judge, store: receipts.Store, chain_id: int, race: str,
                 runner=None, clock=time.time):
        keys.check_chain(chain_id)  # local test keys refuse any other chain (design D4)
        self.keys, self.judge, self.store = keys, judge, store
        self.chain_id, self.race = chain_id, race
        self.runner = runner
        self.clock = clock
        self.address = keys.address()
        self.verdicts: dict[int, Verdict] = {}

    # ---------- round 0: check and judge ----------

    def check(self, claim: Claim, sealed_commitment: str) -> Verdict:
        if crypto.commitment(claim.fix, bytes.fromhex(claim.salt.removeprefix("0x")), claim.solver) \
                != crypto.h32(sealed_commitment):
            raise RefusedClaim(f"submission {claim.submission}: the claim doesn't match its sealed commitment")
        tests: TestRun = run_tests(claim.src, runner=self.runner) if self.runner else run_tests(claim.src)
        case = case_for(claim.repo, claim.issue, claim.commit, claim.diff)
        answer = self.judge.judge(case, tests)
        outcome = crypto.PASS if answer.solves else crypto.FAIL
        quote_kind = self.keys.quote(b"").kind
        rec = receipts.build(node=self.address, checker_image=CHECKER_IMAGE, model=answer.model,
                             backend=answer.backend, prompt=answer.prompt, response=answer.response,
                             fix_tree=claim.tree, tests=tests.record(), submission=claim.submission,
                             bounty=claim.bounty, outcome=outcome, chain_id=self.chain_id, race=self.race,
                             attestation_kind=quote_kind, issued_at=int(self.clock()),
                             usage=getattr(answer, "usage", None),
                             inference=getattr(answer, "inference", None))
        h = self.store.put(rec)
        quote = self.keys.quote(bytes.fromhex(h))  # in a CVM the TDX quote binds the receipt hash
        if quote.quote:
            (self.store.root / f"{h}.quote").write_text(quote.quote)
        v = Verdict(claim, outcome, rec, h)
        self.verdicts[claim.submission] = v
        return v

    # ---------- round 1: seal ----------

    def seal(self, submission: int) -> str:
        return self.verdicts[submission].seal(self.address)

    # ---------- round 2: reveal ----------

    def reveal(self, submission: int) -> Reveal:
        v = self.verdicts[submission]
        sig = self.keys.sign(crypto.keccak256(bytes.fromhex(v.receipt_hash)))
        return Reveal(self.address, v.outcome, v.receipt, v.receipt_hash, "0x" + v.salt.hex(), "0x" + sig.hex())

    # ---------- round 3: sign the result ----------

    def sign_result(self, submission: int, outcome: int, signers: list[str], domain: bytes) -> str:
        """Sign the EIP-712 Result only for the outcome this node reached, and only if it is one of the signers."""
        v = self.verdicts[submission]
        if outcome != v.outcome:
            raise RefusedClaim(f"submission {submission}: asked to sign {outcome}, judged {v.outcome}")
        if self.address.lower() not in (s.lower() for s in signers):
            raise RefusedClaim(f"submission {submission}: not among the signers")
        digest = result_digest(domain, v.claim, outcome, signers)
        return "0x" + self.keys.sign(digest).hex()


def fees_for(signers: list[str]) -> list[tuple[str, int]]:
    return [(s, ORACLE_FEE) for s in sorted(signers, key=lambda a: int(a, 16))]


def result_digest(domain: bytes, claim: Claim, outcome: int, signers: list[str]) -> bytes:
    nonce = crypto.result_nonce(claim.submission, claim.bounty, claim.fix)
    return crypto.result_digest(domain, claim.submission, claim.bounty, outcome, claim.fix, fees_for(signers), nonce)
