"""Non-transferable reputation (specs/reputation, proof-of-fix#37): a score per account and role (solver, reporter,
funder), changed only by recorded outcomes, each change a `reputation` event on the ledger so anyone can recompute
every score; and trust, a published function of the score that the market uses to weight matching, rank treasury
proposals and size bonds. There is no operation to move a score: it belongs to the account that earned it.
"""

from __future__ import annotations

import re
from typing import Callable

from . import BPS
from .ledger import Ledger
from .params import Params

ROLES = ("solver", "reporter", "funder")
_EVENT = re.compile(r"^(\S+) (solver|reporter|funder) ([+-]\d+) ")


class Reputation:
    def __init__(self, ledger: Ledger, params: Params, release: Callable[[], int] | None = None) -> None:
        self.ledger, self.params, self.release = ledger, params, release
        self._scores: dict[tuple[str, str], int] = {}
        self._earned: dict[tuple[str, str, int], int] = {}  # positive points per account, role and release
        self.outcomes: dict[tuple[str, str], dict[str, int]] = {}  # every outcome counted, capped or not

    def record(self, account: str, role: str, points: int, ref: str, day: int, outcome: str) -> None:
        """An outcome changes a score; the change is recorded with its reference. Positive points stop at the
        published cap per role per release (#40 design D2): the outcome is still recorded, with the points it
        earned; failures always count in full."""
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}")
        key = (account, role)
        counts = self.outcomes.setdefault(key, {})
        counts[outcome] = counts.get(outcome, 0) + 1
        if points > 0 and self.release is not None:
            slot = (account, role, self.release())
            earned = self._earned.get(slot, 0)
            points = max(0, min(points, self.params.trust_points_per_release - earned))
            self._earned[slot] = earned + points
        self._scores[key] = self._scores.get(key, 0) + points
        self.ledger.record(day, "reputation", ref, f"{account} {role} {points:+d} {outcome}")

    def score(self, account: str, role: str) -> int:
        return self._scores.get((account, role), 0)

    def trust_bps(self, account: str, role: str) -> int:
        """The floor at zero, a step per point up to the whole, and a step per point down to nothing below zero:
        a proven offender ranks below a newcomer (#37 design D6)."""
        p = self.params
        return max(0, min(BPS, p.trust_floor_bps + self.score(account, role) * p.trust_step_bps))

    def scores(self) -> dict[tuple[str, str], int]:
        return dict(self._scores)

    @staticmethod
    def recompute(ledger: Ledger) -> dict[tuple[str, str], int]:
        """Every score, from the recorded `reputation` events alone."""
        out: dict[tuple[str, str], int] = {}
        for e in ledger.events:
            if e.kind == "reputation":
                m = _EVENT.match(e.detail)
                if m:
                    key = (m.group(1), m.group(2))
                    out[key] = out.get(key, 0) + int(m.group(3))
        return out
