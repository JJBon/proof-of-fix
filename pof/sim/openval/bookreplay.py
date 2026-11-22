"""Report v5's R(minus)+F rows and the launch's pledge gate, exported for the contracts' replay (proof-of-fix#251
contract batch 3; #132 task 12.5, launch tasks 3.3 and 3.6).

`nodeposit.NDNet` runs report v5's reputation cap (`REP_CAP`, `REP_ON_REVERSAL` "minus", REP_BASE $50, REP_MULT 1,
REP_LOSS_X 2) and, with `ACTIVE_GATE`, report active-solvers-v1's count of active solvers. `TraceNet` records what the
contracts' `SolverBook` must see of a run, in the order it happened:
- every claim an attacker's identity makes (OPEN: its submission, identity, bounty in micro-coins, and whether the cap
  let it in), and how it ends: a final pass (PASS: the bounty joins the reputation), a pass reversed (REVERSED: twice
  its bounty off, not below zero), a final fail (FAIL) or a withdrawal (WITHDRAWN), each with the identity's
  reputation after it, in micro-coins;
- with the gate, every event that makes an identity active (ACTIVE: a fix's final pass, by an attacker's identity or
  by the honest solver of the repository who wrote it; DISPUTE: an honest solver's failing test upheld) and, at every
  issue listed, the count of active solvers (GATE).

The contract replay (`contracts/test/v3/ReplaySolversV3.t.sol`) drives a `SolverBook` with those calls at those times
(seconds: the run's hours × 3,600) and checks every acceptance, every reputation and every count.

**Integers and the rules the chain has.** The run's amounts are floats; the export carries micro-coins (rounded to the
nearest) and computes its own integer reputation, cap decisions and counts by the contract's rules. A run whose float
cap decision differs from the integer one is refused (`Unfollowable`), as `contract.py` refuses runs the FeesV3 replay
can't follow. One rule differs on purpose: an upheld test counts toward the active solvers only for an identity that
already has a merged fix (the decided rule, owner 2026-11-19; the simulation counts every honest solver's upheld test,
report active-solvers-v1 section 5: "not simulated"). The export's count follows the contract's rule, and records how
many gate checks the two rules would have decided differently (`gateDiffers`).

    python3 -m pof.sim.openval.bookreplay ROW SEED > contracts/test/data/v3-book-ROW-SEED.json

ROW is `L` (report v5's long con under R(minus)+F: Opus 5.5 seated alone, 3 honest solvers, bad fixes the tests fail;
no gate) or `YS` (the sybil of three with free identities under the gate, 26 weeks, 1 honest solver).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Dict, List, Optional, Tuple

from . import activesolvers as AS
from . import nodeposit as N
from .net import ISSUE, Sub
from .params import WEEK

OPEN, PASS, REVERSED, FAIL, WITHDRAWN, ACTIVE, DISPUTE, GATE = range(1, 9)
NAMES = {OPEN: "open", PASS: "pass", REVERSED: "reversed", FAIL: "fail", WITHDRAWN: "withdrawn", ACTIVE: "active",
         DISPUTE: "dispute", GATE: "gate"}
REP_BASE = 50_000_000  # micro-coins: SolverBook's
REP_LOSS_X = 2
ACTIVE_MIN = 3


class Unfollowable(Exception):
    """A run the contract replay can't follow exactly."""


def micro(dollars: float) -> int:
    return int(round(dollars * 1_000_000))


def seconds(hours: float) -> int:
    return int(round(hours * 3600))


class TraceNet(N.NDNet):
    """`NDNet` recording the book's events (see the module's docstring) and mirroring them in integers."""

    def __init__(self, *a, **kw) -> None:
        self.events: List[Dict[str, int]] = []
        self.who: Dict[Tuple[str, str], int] = {}
        self.irep: Dict[int, int] = {}
        self.iopen: Dict[int, int] = {}
        self.iclaims: Dict[int, Tuple[int, int]] = {}
        self.last: Dict[int, int] = {}
        self.has_fix: Dict[int, bool] = {}
        self.gate_differs = 0
        self._disputing = False
        super().__init__(*a, **kw)

    # ----- identities -----

    def _id(self, idt: Tuple[str, str]) -> int:
        if idt not in self.who:
            self.who[idt] = len(self.who) + 1
        return self.who[idt]

    def _ev(self, kind: int, **kw: int) -> None:
        e = {"kind": kind, "t": seconds(self.t), "sid": 0, "who": 0, "micro": 0, "ok": 0, "rep": 0, "count": 0}
        e.update(kw)
        self.events.append(e)

    # ----- the integer mirror of SolverBook -----

    def count(self) -> int:
        win = seconds(self.p.ACTIVE_WINDOW_WEEKS * WEEK)
        now = seconds(self.t)
        return sum(1 for x in self.last.values() if now <= x + win)

    def _activate(self, idt: Optional[Tuple[str, str]]) -> None:
        super()._activate(idt)
        if idt is None or not self.p.ACTIVE_GATE:
            return
        w = self._id(idt)
        if self._disputing:
            # the contract's rule: an upheld test counts only for an identity with a merged fix
            if self.has_fix.get(w):
                self.last[w] = seconds(self.t)
            self._ev(DISPUTE, who=w)
            return
        self.last[w] = seconds(self.t)
        self.has_fix[w] = True
        self._ev(ACTIVE, who=w)

    # ----- events -----

    def _arrive(self, sub: Sub) -> None:
        if sub.tier == ISSUE and sub.party is None and self.p.ACTIVE_GATE:
            sim_locked = self.locked()
            n = self.count()
            if sim_locked != (n < ACTIVE_MIN):
                self.gate_differs += 1
            self._ev(GATE, count=n)
        idt = self.ident(sub) if sub.tier == ISSUE and sub.party is not None and self.p.REP_CAP else None
        super()._arrive(sub)
        if idt is None:
            return
        w = self._id(idt)
        m = micro(sub.bounty)
        ok = sub.sid in self.claims
        int_ok = self.iopen.get(w, 0) + m <= REP_BASE + self.irep.get(w, 0)
        if ok != int_ok:
            raise Unfollowable(f"submission {sub.sid}: the cap decides {ok} in floats, {int_ok} in micro-coins")
        if ok:
            self.iopen[w] = self.iopen.get(w, 0) + m
            self.iclaims[sub.sid] = (w, m)
        self._ev(OPEN, sid=sub.sid, who=w, micro=m, ok=int(ok))

    def _finalize(self, sub: Sub, outcome: bool) -> None:
        claim = self.iclaims.pop(sub.sid, None)
        self._disputing = sub.tier == ISSUE and not outcome and sub.by_evidence
        if claim is None:
            super()._finalize(sub, outcome)
            self._disputing = False
            return
        # the claim's events go first: `_activate` (inside the run's finalize) records ACTIVE after the reputation
        w, m = claim
        self.iopen[w] -= m
        idx = len(self.events)
        super()._finalize(sub, outcome)
        self._disputing = False
        if outcome:
            kind = PASS
            self.irep[w] = self.irep.get(w, 0) + m
        elif sub.reversed:
            kind = REVERSED
            self.irep[w] = max(0, self.irep.get(w, 0) - REP_LOSS_X * m)
        else:
            kind = FAIL
        e = {"kind": kind, "t": seconds(self.t), "sid": sub.sid, "who": w, "micro": m, "ok": 1,
             "rep": self.irep.get(w, 0), "count": 0}
        self.events.insert(idx, e)
        sim = micro(self.rep[next(k for k, v in self.who.items() if v == w)])
        if abs(sim - self.irep.get(w, 0)) > 1 + len(self.events) // 1000:
            raise Unfollowable(f"identity {w}: reputation {self.irep.get(w, 0)} in micro-coins, {sim} in the run")

    def _tick(self) -> None:
        before = set(self.claims)
        super()._tick()
        for sid in sorted(before - set(self.claims)):
            claim = self.iclaims.pop(sid, None)
            if claim is None:
                continue
            w, m = claim
            self.iopen[w] -= m
            self._ev(WITHDRAWN, sid=sid, who=w, micro=m, ok=1, rep=self.irep.get(w, 0))


def row(name: str):
    """The run's actor, world and parameters."""
    if name == "L":
        w = N.world("hidden", "anthropic", 3)
        return N.make("L", w)(False), w, AS.BASE
    if name == "YS":
        w = N.world("hidden", "anthropic", 1)
        return AS.make("YS", w, dict(keep=AS.KEEP))(False), w, AS.gated(26.0)
    raise ValueError(f"unknown row {name}")


def export(name: str, seed: int) -> Dict[str, object]:
    actor, w, p = row(name)
    net = TraceNet(seed, p, actor.world(), [actor]).run()
    ev = net.events  # type: ignore[attr-defined]
    cols = ("kind", "t", "sid", "who", "micro", "ok", "rep", "count")
    out: Dict[str, object] = {
        "row": name, "seed": seed, "gate": bool(p.ACTIVE_GATE),
        "activeWindow": seconds(p.ACTIVE_WINDOW_WEEKS * WEEK), "identities": len(net.who),  # type: ignore[attr-defined]
        "gateDiffers": net.gate_differs,  # type: ignore[attr-defined]
        "byKind": {NAMES[k]: sum(1 for e in ev if e["kind"] == k) for k in NAMES},
        "n": len(ev),
    }
    for c in cols:
        out[c + "s"] = [e[c] for e in ev]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("row", choices=("L", "YS"))
    ap.add_argument("seed", type=int)
    a = ap.parse_args(argv)
    json.dump(export(a.row, a.seed), sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
