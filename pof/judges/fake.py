"""A deterministic stand-in judge for tests and dry runs: no model, no cost. Each family is right with a fixed
probability, decided by a hash of (family, case), and falls for an injection with another; the answer is the JSON a
real judge would give, so the whole pipeline (prompt, parse, store, analysis) runs without spending anything.
"""

from __future__ import annotations

import json

from .dataset import sha256


def _draw(*parts: str) -> float:
    return int(sha256(":".join(parts))[:8], 16) / 0xFFFFFFFF


class FakeJudge:
    def __init__(self, family: str, accuracy: float = 0.8, gullible: float = 0.1):
        self.family, self.accuracy, self.gullible = family, accuracy, gullible

    def answer(self, case: dict) -> str:
        base = case["id"].split("+", 1)[0]
        right = _draw(self.family, base) < self.accuracy
        solves = (case["label"] == "good") == right
        if case.get("injection") and not solves and _draw(self.family, case["id"], "inj") < self.gullible:
            solves = True
        return json.dumps({"solves": solves, "probability": 0.8 if solves else 0.2,
                           "evidence": [{"file": "fake.py", "line": 1, "note": "fake"}],
                           "constitutional": False, "reason": "fake judge"})
