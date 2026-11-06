"""A verdict's receipt (design D3), shaped after the IETF draft "Attested Inference Receipt"
(draft-tsyrulnikov-rats-attested-inference-receipt-02) where it fits: what checked the fix, on what, with which model,
and what came out. Its hash is sha256 of its canonical JSON; it is stored under that hash, and the hash is what the node
quotes (dstack) and seals."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RECEIPT_VERSION = "pof-receipt-1"


def canonical(receipt: dict) -> bytes:
    return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()


def receipt_hash(receipt: dict) -> str:
    return hashlib.sha256(canonical(receipt)).hexdigest()


def build(*, node: str, checker_image: str, model: str, backend: str, prompt: str, response: str, fix_tree: str,
          tests: dict, submission: int, bounty: int, outcome: int, chain_id: int, race: str, attestation_kind: str,
          issued_at: int, usage: dict | None = None, inference: dict | None = None) -> dict:
    """`usage`: the judge backend's token counts, the provider's own object included (`reported`); `inference`: a
    direct call's provider, endpoint host, request ID and stop reason (#118), what an attested inference receipt
    names. Both are left out when the backend has none (the fake judge), so those receipts are unchanged."""
    rec = {
        "version": RECEIPT_VERSION,
        "node": node,
        "checker_image": checker_image,
        "model": {"id": model, "backend": backend},
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
        "base_commit": fix_tree,
        "tests": tests,
        "verdict": {"submission": submission, "bounty": bounty, "outcome": outcome},
        "chain": {"id": chain_id, "race": race},
        "attestation": {"kind": attestation_kind},
        "issued_at": issued_at,
    }
    if inference:
        rec["model"].update({k: v for k, v in inference.items() if k != "model"})
    if usage:
        rec["usage"] = usage
    return rec


class Store:
    """Content-addressed: <dir>/<sha256>.json. A read checks the content still hashes to its name."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, receipt: dict) -> str:
        h = receipt_hash(receipt)
        (self.root / f"{h}.json").write_bytes(canonical(receipt))
        return h

    def get(self, h: str) -> dict:
        data = (self.root / f"{h}.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != h:
            raise ValueError(f"receipt {h} doesn't match its content")
        return json.loads(data)
