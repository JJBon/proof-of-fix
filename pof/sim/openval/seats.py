"""Seats by rank (#236; design D20 and D23, specs/judge-scores "Seats go to the best-scoring families" and "A new
family starts as a contender").

With `Params.SEAT_RULE` "rank", counted panels are drawn only from the **seated** families: those whose score is at
least `SCORE_MIN` and within `SEAT_MARGIN` of the best-scoring family (`rule`). Every other family is a contender: its
validators shadow-judge (`Net._draw_shadows`, the barred families' draw), dispute and may sit on appeal panels. The
family cap applies only while `CAP_MIN_FAMILIES` are seated (`Net.draw_p`).

Where a score comes from is the world's (`World.seat_scores`):

- `LiveSeats` ("live", D23's rule): a seated family's score is D14's, its balanced agreement with final outcomes over
  its last `SCORE_WINDOW` counted verdicts since it was seated; a contender's is its last complete block of
  `SCORE_RECOVER_VERDICTS` live shadow verdicts, each block judged once. A contender is seated when a block meets
  the seat rule; a seated family that falls outside the rule becomes a contender, and its next block starts then.
  The genesis validator's family is seated from the start. A family with no verdicts starts as a contender
  (`NEW_FAMILY_START` "contender") or, as in v3, seated at once until it has `SCORE_MIN_VERDICTS` counted verdicts
  ("neutral"). Final outcomes are the network's: a panel's verdict unless a challenge, a test (D21) or an appeal
  (D23) changed it.
- `KnownSeats` ("known"): the rule applied to each family's balanced score on known answers
  (`measured.balanced`; for assumed judges, its accuracy and blind spot). It is what a perfect source of final
  outcomes would give, an upper bound, and what reports measured-v1 and -v2 called "the rank on known answers".

Two readings the specs leave open, both stated in reports/open-validators-measured-v3.md:
- **someone must judge:** when no family meets the rule (every score is below `SCORE_MIN`), the best-scoring family
  keeps its seat, as the genesis family has it at the start (`fallbacks` counts the days). Without it the network
  would halt, and contenders, which shadow only drawn submissions, could never earn a seat;
- **a seated family not yet scored** (the genesis family, or a neutral start, before `SCORE_MIN_VERDICTS` counted
  verdicts) keeps its seat and doesn't set the best score.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

from .params import Params

EPS = 1e-12


def rule(scores: Dict[str, Optional[float]], p: Params) -> FrozenSet[str]:
    """D20: the families at SCORE_MIN or above and within SEAT_MARGIN of the best score (families with no score yet
    are left out)."""
    known = {f: s for f, s in scores.items() if s is not None}
    if not known:
        return frozenset()
    best = max(known.values())
    return frozenset(f for f, s in known.items() if s >= p.SCORE_MIN - EPS and s >= best - p.SEAT_MARGIN - EPS)


def meets(score: float, best: float, p: Params) -> bool:
    return score >= p.SCORE_MIN - EPS and score >= best - p.SEAT_MARGIN - EPS


class KnownSeats:
    """The seat rule on known answers: fixed for the run."""
    source = "known"

    def __init__(self, net):
        w = net.w
        self.net, self.p = net, net.p
        if w.measured:
            from . import measured as M
            self.scores: Dict[str, Optional[float]] = {f: M.balanced(s, w.measured) for f, s in w.measured_seats}
        else:  # assumed judges: right with its accuracy on good fixes; on bad ones, less its blind spot
            self.scores = {f: (w.accuracy_of(f) + w.accuracy_of(f) * (1 - w.blind_of(f))) / 2 for f in w.families}
        self._seated = rule(self.scores, self.p)
        self.fallbacks = 0
        if not self._seated:
            self._seated = frozenset([max(sorted(self.scores), key=lambda f: self.scores[f])])
            self.fallbacks = 1
        self.seated_days: Counter = Counter()

    def seated(self) -> FrozenSet[str]:
        return self._seated

    def ok(self, family: str) -> bool:
        return family in self._seated

    def score(self, family: str) -> Optional[float]:
        return self.scores.get(family)

    def on_day(self) -> None:
        for f in self._seated:
            self.seated_days[f] += 1


@dataclass
class Fam:
    seated: bool = False
    score: Optional[float] = None  # its standing score (None: no verdicts to score it on yet)
    start: int = 0  # where its counted window starts (restarts at each seating)
    shadow_start: int = 0  # where its next shadow block starts
    blocks: int = 0  # shadow blocks judged
    seatings: int = 0
    unseatings: int = 0
    seated_t: Optional[float] = None  # when it was last seated
    by_known: bool = False  # its score is read from known-answer issues (D26)


class LiveSeats:
    """D23's seats in a running `Net`, read from its records (`family_outcomes`, `family_shadow_outcomes`), updated
    whenever a verdict becomes final or a validator registers."""
    source = "live"

    def __init__(self, net):
        self.net, self.p = net, net.p
        self.fam: Dict[str, Fam] = {}
        self._key = None
        self._seated: FrozenSet[str] = frozenset()
        self.fallback = False  # no family meets the rule now: the best one judges
        self.fallbacks = 0  # days that was so
        self.seated_days: Counter = Counter()
        self.first_seated: Dict[str, float] = {}

    def _families(self):
        net = self.net
        gen = [v.family for v in net.reg.validators.values() if v.genesis]
        for v in net.reg.validators.values():
            if v.family not in self.fam:
                st = self.fam[v.family] = Fam()
                # at genesis the genesis validator's family is seated; a later family starts as the rule says
                if v.family in gen or self.p.NEW_FAMILY_START == "neutral":
                    self._seat(v.family, st, None)
        return self.fam

    def _seat(self, f: str, st: Fam, score: Optional[float]) -> None:
        st.seated, st.score, st.start = True, score, len(self.net.family_outcomes.get(f, ()))
        st.seatings += 1
        st.seated_t = self.net.t
        self.first_seated.setdefault(f, self.net.t)

    def _unseat(self, f: str, st: Fam) -> None:
        st.seated, st.shadow_start = False, len(self.net.family_shadow_outcomes.get(f, ()))
        st.unseatings += 1

    def _update(self) -> None:
        from .scores import agreement, recompute
        net, p = self.net, self.p
        fams = self._families()
        block = p.SCORE_RECOVER_VERDICTS
        fresh = []  # contenders whose block completed in this update: (family, the block's score)
        for f in sorted(fams):
            st = fams[f]
            ko = net.known_outcomes.get(f, ()) if p.KNOWN_RATE > 0 else ()  # a network without D26 keeps none
            if len(ko) >= p.KNOWN_MIN:
                # D26: once it holds KNOWN_MIN verdicts on known-answer issues, its score is its balanced agreement
                # with the known answers, seated or not; a contender may be seated at any update
                st.score = agreement(ko[-p.KNOWN_WINDOW:], p)
                st.by_known = True
                if not st.seated:
                    fresh.append(f)
                continue
            if st.seated:
                sc, n = recompute(net.family_outcomes.get(f, ())[st.start:], (), p)
                if sc is not None and n >= p.SCORE_MIN_VERDICTS:
                    st.score = sc
                continue
            s = net.family_shadow_outcomes.get(f, ())
            done = None
            while len(s) - st.shadow_start >= block:
                done = agreement(s[st.shadow_start:st.shadow_start + block], p)
                st.shadow_start += block
                st.blocks += 1
            if done is not None:
                st.score = done
                fresh.append(f)
        known = [st.score for st in fams.values() if st.score is not None]
        best = max(known) if known else None
        stay = {f for f, st in fams.items() if st.seated and (st.score is None or meets(st.score, best, p))}
        join = {f for f in fresh if not fams[f].seated and meets(fams[f].score, best, p)}
        if not stay and not join:
            # someone must judge: the best-scoring seated family keeps its seat (or, with none seated, the best one)
            seated = [f for f in fams if fams[f].seated] or [f for f in fams if fams[f].score is not None]
            keep = sorted(seated, key=lambda f: (-(fams[f].score if fams[f].score is not None else 1.0), f))[:1]
            self.fallback = True
            if keep and fams[keep[0]].seated:
                stay = set(keep)
            else:
                join = set(keep)
        else:
            self.fallback = False
        for f in sorted(fams):
            st = fams[f]
            if st.seated and f not in stay:
                self._unseat(f, st)  # a seated family that falls outside the rule becomes a contender
            elif not st.seated and f in join:
                self._seat(f, st, st.score)  # a contender is seated when a block meets the seat rule
        self._seated = frozenset(f for f, st in fams.items() if st.seated)

    def seated(self) -> FrozenSet[str]:
        net = self.net
        key = (net.n_final, len(net.reg.validators), getattr(net, "n_known", 0))
        if key != self._key:
            self._key = key
            self._update()
        return self._seated

    def ok(self, family: str) -> bool:
        return family in self.seated()

    def score(self, family: str) -> Optional[float]:
        self.seated()
        st = self.fam.get(family)
        return st.score if st is not None else None

    def on_day(self) -> None:
        for f in self.seated():
            self.seated_days[f] += 1
        self.fallbacks += self.fallback


def install(net):
    """Switch D20's seat rule on in a network (called by `Net` when `Params.SEAT_RULE` is "rank")."""
    src = net.w.seat_scores
    if src not in ("live", "known"):
        raise ValueError(src)
    net.seats = KnownSeats(net) if src == "known" else LiveSeats(net)
    net.family_ok = net.seats.ok
    return net.seats
