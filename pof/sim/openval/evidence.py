"""The appeal on evidence, sponsorship, known-answer issues and the one-family second panel, on measured judges
(proof-of-fix#236, the revision of 2026-11-15: design D24-D28 of #132's change).

Task 10.1 (`sizing`, reports/open-validators-measured-v3.md) found that D23's appeal panel, drawn from the families
that did not judge, overturns four in five correct rejections. The owner dropped it (2026-11-15) and asked for a way
to challenge wrong rejections that the seated judges decide. This module plays the proposed replacement out, each rule
behind a named switch of `Params`, beside its alternative on the same seeds:

- **the appeal on evidence** (`APPEAL` "evidence", D24): one appeal per rejected fix, with a test that fails on the
  base code and passes with the fix, and a stake (`APPEAL_STAKE`, `APPEAL_STAKE_BPS`); a fresh draw of the seated
  families decides. #160's verdicts cannot say how a judge reacts to a passing test, so the panel's answer is one
  draw per fix at an ASSUMED rate, swept: `World.appeal_accept_good` (a wrongly rejected good fix) and
  `World.appeal_accept_bad` (a correctly rejected bad fix whose test passes anyway);
- **sponsorship** (`SPONSOR`, D25): a contender whose model passed a rejected fix posts the stake and the test in the
  solver's place, and is paid `SPONSOR_REWARD_BPS` of the bounty when the fix is paid;
- **known-answer issues** (`KNOWN_RATE`, D26): every family, seated or not, judges them, and its seat score is read
  from them;
- **the second panel** (`SECOND_PANEL`, D27): a challenge that cannot draw D4's larger fresh panel while few families
  can judge is decided by a second draw from those families.

The attackers, each against its twin: `sizing.Solver` appealing every rejection with a test it wrote itself; the same
solver trying one issue again and again while its deposit is held (`Retrier`); and `Sponsor`, a contender that
sponsors every rejection.

    python3 -m pof.sim.openval.evidence [--seeds 40] [--jobs 8] [--quick] [--only appeal,...]

prints reports/open-validators-measured-v4.md's tables. No model call: verdicts are replayed from
data/judges/verdicts-v2.matrix.json.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import contenders as C
from . import measured as M
from . import pricing as PR
from . import report as R
from . import sizing as Z
from .net import ISSUE, Net
from .params import D236R2, PARAMS, WEEK, WORLD, Params, World

POOLS = Z.POOLS
BASE = Z.BASE  # task 10.1's base: seats by rank, deposit 2,500, test disputes, no appeal
STAKE = dict(APPEAL_STAKE=5.0, APPEAL_STAKE_BPS=1_000)  # the proposal: the larger of $5 and 10 % of the bounty
EV = replace(BASE, APPEAL="evidence", **STAKE)  # ...and the appeal on evidence, decided by the seated families
P0 = replace(BASE, SOLVER_DEPOSIT_BPS=0)  # no solver's deposit: the primary case since the owner put D22 on hold
A0, B0 = 0.5, 0.05  # the assumed base: a good fix's evidence accepted 1 time in 2, a bad fix's 1 time in 20
SEVEN = tuple(s for _, s in M.SEVEN)
_pre = Z._pre
_ms = Z._ms
_table = Z._table


def world(pool: str, a: float = A0, b: float = B0, **kw) -> World:
    """`sizing.world` with the two assumed rates of the appeal on evidence."""
    return Z.world(pool, appeal_accept_good=a, appeal_accept_bad=b, **kw)


# ---------- the actors ----------

class Retrier(Z.Solver):
    """`sizing.Solver` that tries the same issue again. `eager`: it submits the next fix as soon as a panel rejects
    one, while that fix's deposit is still held for its appeal period (it does not appeal: one bounty is paid once)."""

    def __init__(self, honest: bool = False, w: World = WORLD, eager: bool = False, **kw):
        super().__init__(honest, w, **kw)
        self.eager = eager
        self.done: set = set()

    def on_tick(self, net: Net) -> None:
        if not self.eager:
            return super().on_tick(net)
        Z.OnMarket.on_tick(self, net)
        if not self.retries:
            return
        paid = {s.issue for s in self.subs if s.final}
        for s in list(self.subs):
            if s.sid in self.done or s.verdict is not False or s.issue in paid:
                continue
            self.done.add(s.sid)
            if self.tries[s.issue] <= self.retries:
                self.tries[s.issue] += 1
                self.subs.append(net.submit(net.t, s.bounty, False, "bad-fix-solver", self.party, issue=s.issue))


class Sponsor(Z.OnMarket):
    """A contender that sponsors appeals (D25). Its twin sponsors nothing.
    - `kind` "model": honest. It runs `seat`'s model, and sponsors a rejected fix its solver did not appeal when its
      model passed the fix and its family is not seated; each costs it `search_cost` (assumed) to write the test.
    - `kind` "every": the attacker. It sponsors every rejection its solver did not appeal, with a test that passes."""
    name = "sponsor"
    party = "sponsor"

    def __init__(self, honest: bool = False, w: World = WORLD, kind: str = "model", seat: str = "openai",
                 search_cost: float = Z.SEARCH_COST):
        super().__init__(honest, w)
        if kind not in ("model", "every"):
            raise ValueError(kind)
        self.kind, self.seat, self.search_cost = kind, seat, search_cost

    def sponsors(self, net: Net, sub) -> bool:
        if self.honest or sub.party == self.party:
            return False
        if self.kind == "model" and (net.family_ok(self.seat) or not M.case_of(net, sub)[self.seat]):
            return False
        net.parties[self.party].costs += self.search_cost
        net.stats["sponsor_searches"] += 1
        return True


# ---------- what the tables read ----------

def metrics(net: Net) -> Dict[str, float]:
    m = Z.metrics(net)
    st, w = net.stats, net.w
    subs = [s for s in net.subs.values() if s.tier == ISSUE and s.final is not None and s.party is None]
    good = [s for s in subs if s.good]
    old = [s for s in net.subs.values() if s.tier == ISSUE and s.party is None and s.verdict is not None
           and s.verdict_t < net.t - 4 * WEEK and s.state == "challenged" and s.good]
    good += old  # as `sizing.metrics`: a good fix behind a verdict never final is unpaid, its deposit locked

    def lost(s) -> float:
        return s.sdeposit if s.sdeposit_to != "returned" and (s.sdeposit_to or s.final is None) else 0.0

    # an honest solver's cost per good fix: its attempt fee, its own checks (a sponsor pays the appeal panel's), the
    # deposit and the appeal stake it lost, and the sponsor's share of its bounty; less the stakes rejected tests paid
    m["cost_good"] = (mean(w.attempt_fee + s.charges - s.sponsor_charges + lost(s) + s.astake_lost + s.sponsor_fee
                           - s.stakes_won for s in good) if good else float("nan"))
    m["stake_good"] = mean(s.astake_lost for s in good) if good else float("nan")
    m["sponsored"] = st["appeals_sponsored"]
    m["astake_lost"] = st["astake_lost"]
    m["second_panels"] = st["second_panels"]
    m["challenges"] = st["challenges"]
    m["rival_tests"] = st["rival_tests"]
    m["reopened"] = st["evidence_reversed"] - st["evidence_wrong"]  # a bad fix reversed: its issue is open again
    m["known_issues"] = st["known_issues"]
    m["known_pay"] = st["known_pay"]
    m["known_per_sub"] = st["known_pay"] / max(1, st["submitted"])
    first = getattr(net.seats, "first_seated", None)
    if first is not None:
        for f in ("anthropic", "openai"):
            m[f"first_{f}"] = first[f] / WEEK if f in first else float("nan")
            m[f"ever_{f}"] = 100.0 * (f in first)
    return m


def _new_family_metrics(net: Net) -> Dict[str, float]:
    m = metrics(net)
    m.update({k: v for k, v in Z._new_family_metrics(net).items() if k.startswith("new_")})
    return m


Row = Z.Row
AB = ((0.25, 0.05), (0.5, 0.0), (0.5, 0.05), (0.5, 0.10), (0.5, 0.20), (0.5, 0.50), (0.75, 0.05), (0.75, 0.20),
      (1.0, 0.05), (1.0, 0.20))


def _ab(a: float, b: float) -> str:
    return f"good-fix evidence accepted {100 * a:.0f} %, bad-fix evidence accepted {100 * b:.0f} %"


def appeal_rows() -> List[Row]:
    """D24 on known seats: the two assumed rates swept, with honest solvers appealing every rejection (the worst
    case: the solver of a bad fix believes it good and writes a test that passes) or good fixes only."""
    rows: List[Row] = []
    for pool, what in POOLS:
        pre = _pre(what)
        rows.append((pre + "no appeal (task 10.1's base)", world(pool), BASE, None))
        rows.append((pre + "D23's appeal, the seated families' next draw, no evidence (10.1)",
                     world(pool, appeal_bad=1.0), replace(BASE, APPEAL="seated"), None))
        for a, b in AB:
            mark = "**" if (a, b) == (A0, B0) else ""
            rows.append((pre + f"{mark}appeal on evidence; {_ab(a, b)}{mark}; every rejection appealed",
                         world(pool, a, b, appeal_bad=1.0), EV, None))
        rows.append((pre + f"appeal on evidence; {_ab(A0, B0)}; good fixes only appealed", world(pool), EV, None))
        rows.append((pre + f"appeal on evidence; {_ab(A0, B0)}; every rejection appealed; deposit 4,000",
                     world(pool, appeal_bad=1.0), replace(EV, SOLVER_DEPOSIT_BPS=4_000), None))
        rows.append((pre + f"appeal on evidence; {_ab(A0, B0)}; every rejection appealed; lost stakes to the "
                     "issue's bounty", world(pool, appeal_bad=1.0), replace(EV, APPEAL_STAKE_TO="bounty"), None))
        rows.append((pre + f"appeal on evidence; {_ab(A0, 0.20)}; every rejection appealed; no test disputes",
                     world(pool, A0, 0.20, find=0.0, false=0.0, appeal_bad=1.0), EV, None))
    return rows


def genesis(w: World, family: str) -> World:
    """The same world with `family` as the genesis validator's."""
    return replace(w, families=(family,) + tuple(f for f in w.families if f != family))


KNOWN_RATES = (0.02, 0.05, 0.10, 0.20)


def known_rows() -> List[Row]:
    """D26 on live seats, no appeal: the rate swept, with the genesis family the best one (Opus 5.5) and a strict one
    (GPT-6.1), beside the live score alone and the score on every known answer (the upper bound)."""
    rows: List[Row] = []
    for pool, what in POOLS:
        pre = _pre(what)
        live = world(pool, scores="live")
        rows.append((pre + "scores on every known answer (10.1's upper bound)", world(pool), BASE, None))
        for gen, name in (("anthropic", "Opus 5.5"), ("openai", "GPT-6.1")):
            w = genesis(live, gen)
            rows.append((pre + f"genesis {name}; live scores, no known-answer issues", w, BASE, None))
            for r in KNOWN_RATES:
                mark = "**" if r == 0.05 else ""
                rows.append((pre + f"genesis {name}; {mark}known-answer issues at {100 * r:.0f} %{mark}", w,
                             replace(BASE, KNOWN_RATE=r), None))
        w = genesis(live, "openai")
        rows.append((pre + "genesis GPT-6.1; known-answer issues at 10 %, window 400, at least 100", w,
                     replace(BASE, KNOWN_RATE=0.10, KNOWN_WINDOW=400, KNOWN_MIN=100), None))
        rows.append((pre + "genesis GPT-6.1; known-answer issues at 5 %, with the appeal on evidence", w,
                     replace(EV, KNOWN_RATE=0.05), None))
    return rows


def second_rows() -> List[Row]:
    """D27, with volunteers' second-opinion challenges on (as reports measured-v1 and -v2 ran): D4's larger fresh
    panel, the second draw while few families can judge, and the second draw always."""
    rows: List[Row] = []
    for pool, what in POOLS:
        pre = _pre(what)
        w = world(pool, second_opinions=True)
        v3 = lambda w: Z.OnMarket(w=w, scores=True)  # noqa: E731
        for sp, name in (("larger", "D4: a larger fresh panel, or the challenge waits"),
                         ("few", "**a second draw while fewer than three families can judge**"),
                         ("always", "a second draw whenever the larger panel cannot be drawn")):
            rows.append((pre + f"v3 as designed; {name}", w, replace(PARAMS, SECOND_PANEL=sp), v3))
        for sp, name in (("larger", "D4"), ("few", "**a second draw while fewer than three families can judge**"),
                         ("always", "a second draw whenever the larger panel cannot be drawn")):
            rows.append((pre + f"seats by rank, `SEAT_MARGIN` 5; {name}", w, replace(BASE, SECOND_PANEL=sp), None))
        for sp, name in (("larger", "D4"), ("few", "a second draw while fewer than three families can judge")):
            rows.append((pre + f"seats by rank, `SEAT_MARGIN` 1; {name}", w,
                         replace(BASE, SEAT_MARGIN=0.01, SECOND_PANEL=sp), None))
    return rows


def sponsor_rows() -> List[Row]:
    """D25 and seating, on live scores: a strong family (Opus 5.5) joins a network whose genesis family is GPT-6.1 in
    week 8, and a weak one (Mistral Large 3) joins Opus 5.5's."""
    rows: List[Row] = []
    six = dict(CONTENDER_SHADOWS=6)
    for pool, what in POOLS:
        pre = _pre(what) + "Opus 5.5 joins GPT-6.1's network: "
        new = lambda w: Z.NewFamily(w=w, family="anthropic")  # noqa: E731
        late = lambda **kw: Z.late(pool, "anthropic", **kw)  # noqa: E731
        ab = dict(appeal_accept_good=A0, appeal_accept_bad=B0)
        spon = dict(appeal_good=0.0, sponsor_by=("anthropic",), **ab)
        sp = replace(EV, SPONSOR=True, SPONSOR_REWARD_BPS=1_000)
        rows += [
            (pre + "no appeal (10.1)", late(), BASE, new),
            (pre + "no appeal, six contender shadows a draw (10.1)", late(), replace(BASE, **six), new),
            (pre + "appeal on evidence, solvers appeal their good fixes, no sponsor", late(**ab), EV, new),
            (pre + "appeal on evidence, solvers appeal their good fixes, no sponsor; six shadows", late(**ab),
             replace(EV, **six), new),
            (pre + "solvers never appeal; **the newcomer sponsors the fixes its model passed**", late(**spon), sp, new),
            (pre + "solvers never appeal; **the newcomer sponsors; six shadows**", late(**spon), replace(sp, **six),
             new),
            (pre + "the newcomer sponsors; six shadows; good-fix evidence accepted 25 %",
             late(**{**spon, "appeal_accept_good": 0.25}), replace(sp, **six), new),
            (pre + "the newcomer sponsors; six shadows; good-fix evidence accepted 100 %",
             late(**{**spon, "appeal_accept_good": 1.0}), replace(sp, **six), new),
            (pre + "every contender sponsors the fixes its model passed; six shadows",
             late(**{**spon, "sponsor_by": SEVEN}), replace(sp, **six), new),
            (pre + "every contender sponsors; six shadows; bad-fix evidence accepted 20 %",
             late(**{**spon, "sponsor_by": SEVEN, "appeal_accept_bad": 0.20}), replace(sp, **six), new),
            (pre + "known-answer issues at 5 %, no appeal", late(), replace(BASE, KNOWN_RATE=0.05), new),
            (pre + "known-answer issues at 10 %, no appeal", late(), replace(BASE, KNOWN_RATE=0.10), new),
            (pre + "known-answer issues at 20 %, no appeal", late(), replace(BASE, KNOWN_RATE=0.20), new),
            (pre + "**known-answer issues at 5 %, the newcomer sponsors, six shadows**", late(**spon),
             replace(sp, KNOWN_RATE=0.05, **six), new),
        ]
        pre = _pre(what) + "Mistral Large 3 joins Opus 5.5's network: "
        weak = lambda w: Z.NewFamily(w=w, family="mistral")  # noqa: E731
        lw = lambda **kw: Z.late(pool, "mistral", **kw)  # noqa: E731
        for b in (B0, 0.20, 0.50):
            rows.append((pre + f"it sponsors every fix its model passed; six shadows; bad-fix evidence accepted "
                         f"{100 * b:.0f} %", lw(**{**spon, "sponsor_by": ("mistral",), "appeal_accept_bad": b}),
                         replace(sp, **six), weak))
        rows.append((pre + "known-answer issues at 5 %; it sponsors; six shadows; bad-fix evidence accepted 50 %",
                     lw(**{**spon, "sponsor_by": ("mistral",), "appeal_accept_bad": 0.50}),
                     replace(sp, KNOWN_RATE=0.05, **six), weak))
    return rows


R2W = dict(sponsor_by=SEVEN)


def final_rows() -> List[Row]:
    """Task 10.1's network beside the revision, whole (`D236R2`), on live scores. The primary rows have no solver's
    deposit (on hold, owner 2026-11-15); 2,500 and 4,000 are for comparison."""
    rows: List[Row] = []
    r0 = replace(D236R2, SOLVER_DEPOSIT_BPS=0)
    for pool, what in POOLS:
        pre = _pre(what)
        live = lambda a=A0, b=B0, **kw: world(pool, a, b, scores="live", **R2W, **kw)  # noqa: E731
        rows += [
            (pre + "10.1: seats by rank, disputes, no appeal, deposit 2,500; scores on every known answer",
             world(pool), BASE, None),
            (pre + "10.1: the same on live scores", world(pool, scores="live"), BASE, None),
            (pre + "10.1 on live scores, no deposit", world(pool, scores="live"), P0, None),
            (pre + "**the revision, no deposit**: appeal on evidence, sponsors, known-answer issues at 5 %, the "
             f"second draw; {_ab(A0, B0)}", live(), r0, None),
            (pre + f"the revision, no deposit; {_ab(A0, 0.20)}", live(A0, 0.20), r0, None),
            (pre + f"the revision, no deposit; {_ab(0.25, B0)}", live(0.25, B0), r0, None),
            (pre + f"the revision, no deposit; {_ab(A0, B0)}; honest solvers appeal every rejection",
             live(appeal_bad=1.0), r0, None),
            (pre + f"the revision, no deposit; {_ab(A0, B0)}; 10 rival solvers, each finding a test 25 % of the time",
             live(rival_solvers=10, rival_find=0.25), r0, None),
            (pre + f"the revision, no deposit; {_ab(A0, B0)}; with second-opinion challenges",
             live(second_opinions=True), r0, None),
            (pre + f"the revision; {_ab(A0, B0)}; deposit 2,500 (`D236R2`)", live(), D236R2, None),
            (pre + f"the revision; {_ab(A0, B0)}; deposit 4,000", live(), replace(D236R2, SOLVER_DEPOSIT_BPS=4_000),
             None),
        ]
    return rows


RIVAL_FIND = (0.10, 0.25, 0.50)
RIVALS = (1, 3, 10)


def rival_rows() -> List[Row]:
    """D21, "anyone may dispute": honest solvers of the same repository search the passed fixes of others, beside the
    contenders (which find a test 1 time in 2, assumed) and without them. No solver's deposit: the disputer's reward
    is `EVIDENCE_REWARD_BPS` (1,000) of the reversed fix's bounty, which is then not paid to its solver."""
    rows: List[Row] = []
    for pool, what in POOLS:
        pre = _pre(what)
        rows.append((pre + "no test disputes at all", world(pool, find=0.0, false=0.0), P0, None))
        rows.append((pre + "contenders only", world(pool), P0, None))
        for q in RIVAL_FIND:
            for n in RIVALS:
                rows.append((pre + f"contenders and {n} rival solver{'s' if n > 1 else ''}, each finding a test "
                             f"{100 * q:.0f} % of the time", world(pool, rival_solvers=n, rival_find=q), P0, None))
        for n in RIVALS:
            rows.append((pre + f"no contenders; {n} rival solver{'s' if n > 1 else ''}, each finding a test 25 % of "
                         "the time", world(pool, find=0.0, false=0.0, rival_solvers=n, rival_find=0.25), P0, None))
    return rows


def rival_table(data) -> str:
    head = HEAD + ["Bad fixes paid a year", "Passes reversed by a test, a year", "…of which a rival solver's test",
                   "Issues reopened by a test, a year"]
    return _table(head, [[label] + _base(m) + [_ms(m["bad"], 0), _ms(m["evidence_reversed"], 0),
                                               _ms(m["rival_tests"], 0), _ms(m["reopened"], 0)]
                         for label, _, m in data])


TABLES: Dict[str, Callable[[], List[Row]]] = {"rivals": rival_rows, "appeal": appeal_rows, "known": known_rows, "second": second_rows,
                                              "sponsor": sponsor_rows, "final": final_rows}


def run_row(row: Row, seed: int) -> Net:
    _, w, p, extra = row
    return Net(seed, p, w, [extra(w) if extra is not None else Z.OnMarket(w=w)]).run()


def _run(job) -> Dict[str, float]:
    table, i, seed = job
    net = run_row(TABLES[table]()[i], seed)
    return _new_family_metrics(net) if table == "sponsor" else metrics(net)


def run_table(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = TABLES[table]()
    res = C._map(_run, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    out = []
    for i, row in enumerate(rows):
        chunk = res[i * len(seeds):(i + 1) * len(seeds)]
        keys = sorted({k for r in chunk for k in r})
        out.append((row[0], row[1], {k: [r.get(k, float("nan")) for r in chunk] for k in keys}))
    return out


def _base(m) -> List[str]:
    return [_ms(m["bad_per_100"], 1), _ms(m["good_failed_pct"], 1, " %"), "$" + _ms(m["cost_good"], 2)]


HEAD = ["Network", "Bad fixes merged per 100 paid", "Good fixes wrongly unpaid", "An honest solver's cost per good fix"]


def appeal_table(data) -> str:
    head = HEAD + ["…of which deposits lost", "…of which appeal stakes lost", "Appeals a year",
                   "Correct rejections overturned, of those appealed", "Bad fixes paid after an appeal, a year",
                   "Wrongly rejected good fixes paid in the end", "Appeals with no panel", "Verdicts never final"]
    return _table(head, [[label] + _base(m) + ["$" + _ms(m["dep_good"], 2), "$" + _ms(m["stake_good"], 2),
                                               _ms(m["appeals"], 0), _ms(m["overturned_pct"], 0, " %"),
                                               _ms(m["appeal_paid_bad"], 1), _ms(m["restored_pct"], 0, " %"),
                                               _ms(m["appeals_no_panel"], 0), _ms(m["stuck_pct"], 1, " %")]
                         for label, _, m in data])


def known_table(data) -> str:
    head = HEAD[:3] + ["Opus 5.5 seated, share of the year", "GPT-6.1", "Gemini 3.1 Pro",
                       "the four others, their shares added", "No family met the rule, share of the year",
                       "Runs in which Opus 5.5 was ever seated", "Week it was first seated",
                       "Known-answer issues a year", "Their checks, $ a year", "…per submission"]
    return _table(head, [[label] + _base(m)[:2] + Z._seated(m) + [
        _ms(m.get("fallback_pct", []), 0, " %"), _ms(m.get("ever_anthropic", []), 0, " %"),
        _ms(m.get("first_anthropic", []), 0), _ms(m["known_issues"], 0), "$" + _ms(m["known_pay"], 0),
        "$" + _ms(m["known_per_sub"], 3)] for label, _, m in data])


def second_table(data) -> str:
    head = HEAD + ["Submissions that waited", "Challenges a year", "…judged by a second draw",
                   "Verdicts never final"]
    return _table(head, [[label] + _base(m) + [_ms(m["waited_pct"], 1, " %"), _ms(m["challenges"], 0),
                                               _ms(m["second_panels"], 0), _ms(m["stuck_pct"], 1, " %")]
                         for label, _, m in data])


def sponsor_table(data) -> str:
    head = HEAD[:3] + ["Runs in which the new family was ever seated", "Week it was first seated",
                       "Seated, share of its weeks", "GPT-6.1 seated, share of the year",
                       "Opus 5.5 seated, share of the year", "Appeals a year", "…sponsored",
                       "Bad fixes paid after an appeal, a year", "No family met the rule, share of the year"]
    return _table(head, [[label] + _base(m)[:2] + [
        _ms(m["new_ever"], 0, " %"), _ms(m["new_first_week"], 0), _ms(m["new_seated"], 0, " %"),
        _ms(m.get("seated_openai", []), 0, " %"), _ms(m.get("seated_anthropic", []), 0, " %"), _ms(m["appeals"], 0),
        _ms(m["sponsored"], 0), _ms(m["appeal_paid_bad"], 1), _ms(m.get("fallback_pct", []), 0, " %")]
        for label, _, m in data])


def final_table(data) -> str:
    head = HEAD + ["…of which deposits lost", "…of which appeal stakes lost", "Fixes paid a year",
                   "Verdicts never final", "Opus 5.5 seated, share of the year", "GPT-6.1", "Gemini 3.1 Pro",
                   "the four others, their shares added", "Appeals a year", "…sponsored",
                   "Bad fixes paid after an appeal, a year", "Wrongly rejected good fixes paid in the end",
                   "Known-answer checks, $ a year", "Service fee, last 13 weeks"]
    return _table(head, [[label] + _base(m) + ["$" + _ms(m["dep_good"], 2), "$" + _ms(m["stake_good"], 2),
                                               _ms(m["paid_n"], 0), _ms(m["stuck_pct"], 1, " %")] + Z._seated(m) + [
        _ms(m["appeals"], 0), _ms(m["sponsored"], 0), _ms(m["appeal_paid_bad"], 1), _ms(m["restored_pct"], 0, " %"),
        "$" + _ms(m["known_pay"], 0), "$" + _ms(m["fee"], 3)] for label, _, m in data])


# ---------- the attackers ----------

AttRow = Z.AttRow
STAKES = (("$5 flat", dict(APPEAL_STAKE=5.0, APPEAL_STAKE_BPS=0)),
          ("the larger of $5 and 10 % of the bounty", STAKE),
          ("the larger of $5 and 25 %", dict(APPEAL_STAKE=5.0, APPEAL_STAKE_BPS=2_500)))


def appeal_attack_rows() -> List[AttRow]:
    """The solver of bad fixes that appeals every rejection with a test it wrote (it passes: the machine's part
    stops nothing), against the same solver that never appeals."""
    rows: List[AttRow] = []
    for pool, what in POOLS:
        pre = _pre(what)
        for dep in (2_500, 4_000):
            for b in (0.05, 0.10, 0.15, 0.20, 0.50):
                for sname, skw in STAKES:
                    if (dep == 4_000 or b == 0.15) and skw is not STAKE:
                        continue
                    w = world(pool, A0, b)
                    rows.append((pre + f"bad-fix evidence accepted {100 * b:.0f} %; stake {sname}; deposit {dep:,}",
                                 lambda h, w=w: Z.Solver(h, w, appeal=True, twin="no_appeal"),
                                 replace(EV, SOLVER_DEPOSIT_BPS=dep, **skw), "appeal"))
        for b in (0.10, 0.20):
            w = world(pool, A0, b, find=0.0, false=0.0)
            rows.append((pre + f"bad-fix evidence accepted {100 * b:.0f} %; stake the larger of $5 and 10 %; deposit "
                         "2,500; no test disputes", lambda h, w=w: Z.Solver(h, w, appeal=True, twin="no_appeal"),
                         EV, "appeal"))
    return rows


def appeal_attack0_rows() -> List[AttRow]:
    """The same solver with no deposit (the primary case since the owner put D22 on hold; added for that reason, before
    these rows were run), and with rival solvers disputing."""
    rows: List[AttRow] = []
    p = replace(EV, SOLVER_DEPOSIT_BPS=0)
    for pool, what in POOLS:
        for b in (0.05, 0.10, 0.15, 0.20, 0.50):
            for n, q in ((0, 0.0), (10, 0.25)):
                w = world(pool, A0, b, rival_solvers=n, rival_find=q)
                rows.append((_pre(what) + f"no deposit; bad-fix evidence accepted {100 * b:.0f} %; stake the larger of "
                             f"$5 and 10 %; {n} rival solvers" + (f" at {100 * q:.0f} %" if n else ""),
                             lambda h, w=w: Z.Solver(h, w, appeal=True, twin="no_appeal"), p, "appeal"))
    return rows


def retry_rows() -> List[AttRow]:
    """D28: does holding a rejected fix's deposit for the appeal period open a gain to a solver that tries the same
    issue again? It is the only solver of its issues (its best case); its twin submits nothing."""
    rows: List[AttRow] = []
    for pool, what in POOLS:
        pre = _pre(what) + "tries each issue up to 21 times; "
        w = world(pool)
        for dep in (2_500, 4_000):
            p0, pe = replace(BASE, SOLVER_DEPOSIT_BPS=dep), replace(EV, SOLVER_DEPOSIT_BPS=dep)
            rows += [
                (pre + f"deposit {dep:,}; no appeal: the deposit moves at once (10.1)",
                 lambda h, w=w: Retrier(h, w, retry=20), p0, "solver"),
                (pre + f"deposit {dep:,}; **the deposit held for the appeal period**; it waits, and does not appeal",
                 lambda h, w=w: Retrier(h, w, retry=20), pe, "solver"),
                (pre + f"deposit {dep:,}; the deposit held; it submits again while it is held",
                 lambda h, w=w: Retrier(h, w, retry=20, eager=True), pe, "solver"),
                (pre + f"deposit {dep:,}; the deposit held; it appeals every rejection, then tries again",
                 lambda h, w=w: Retrier(h, w, retry=20, appeal=True), pe, "solver"),
            ]
    return rows


def sponsor_attack_rows() -> List[AttRow]:
    rows: List[AttRow] = []
    for pool, what in POOLS:
        pre = _pre(what)
        for reward in (1_000, 2_500):
            p = replace(EV, SPONSOR=True, SPONSOR_REWARD_BPS=reward)
            for b in (0.05, 0.20, 0.50):
                w = world(pool, A0, b)
                rows.append((pre + f"sponsors every rejection the solver did not appeal; bad-fix evidence accepted "
                             f"{100 * b:.0f} %; reward {reward:,}", lambda h, w=w: Sponsor(h, w, "every", "mistral"),
                             p, "sponsor"))
            w = world(pool, A0, B0, appeal_good=0.0)
            rows.append((pre + f"sponsors every rejection, and solvers never appeal; reward {reward:,}",
                         lambda h, w=w: Sponsor(h, w, "every", "mistral"), p, "sponsor"))
            for seat in ("openai", "deepseek"):
                for a in (A0, 0.75):
                    w = world(pool, a, B0, appeal_good=0.0)
                    rows.append((pre + f"an honest contender running {M.NAMES[seat]} sponsors the fixes its model "
                                 f"passed; solvers never appeal; good-fix evidence accepted {100 * a:.0f} %; reward "
                                 f"{reward:,}", lambda h, w=w, seat=seat: Sponsor(h, w, "model", seat), p, "sponsor"))
        # the honest sponsor's best case: Opus 5.5 a contender in a network GPT-6.1 seats (live scores)
        for reward in (1_000, 2_500):
            for a in (A0, 0.75):
                w = genesis(world(pool, a, B0, scores="live", appeal_good=0.0), "openai")
                rows.append((pre + f"an honest contender running Opus 5.5 in a network GPT-6.1 seats (live scores) "
                             f"sponsors the fixes its model passed; solvers never appeal; good-fix evidence accepted "
                             f"{100 * a:.0f} %; reward {reward:,}",
                             lambda h, w=w: Sponsor(h, w, "model", "anthropic"),
                             replace(EV, SPONSOR=True, SPONSOR_REWARD_BPS=reward), "sponsor"))
        # what a sponsor of everything does to the seats, on live scores with six contender shadows a draw
        live = replace(EV, SPONSOR=True, SPONSOR_REWARD_BPS=1_000, CONTENDER_SHADOWS=6)
        for b in (0.20, 0.50):
            w = world(pool, A0, b, scores="live")
            rows.append((pre + f"sponsors every rejection; live scores, six shadows; bad-fix evidence accepted "
                         f"{100 * b:.0f} %; reward 1,000", lambda h, w=w: Sponsor(h, w, "every", "mistral"), live,
                         "sponsor"))
            rows.append((pre + f"sponsors every rejection; live scores, six shadows, known-answer issues at 5 %; "
                         f"bad-fix evidence accepted {100 * b:.0f} %; reward 1,000",
                         lambda h, w=w: Sponsor(h, w, "every", "mistral"), replace(live, KNOWN_RATE=0.05), "sponsor"))
    return rows


HEALTH_DEPOSITS = (0, 1_000, 2_500, 4_000)
STAY_AWAY = (0.0, 0.25, 0.5, 1.0)  # ASSUMED: the share of honest solvers that stay away, per unit of deposit share


def health_rows() -> List[AttRow]:
    """Code health across the deposit: the bad-fix solver (5 a week; its twin submits nothing) on 10.1's base and
    with the appeal on evidence. `health_table` turns each row's counts into issues per 100 funded."""
    rows: List[AttRow] = []
    for pool, what in POOLS:
        for name, p0, w in (("no appeal", BASE, world(pool)),
                            (f"appeal on evidence, {_ab(A0, B0)}", EV, world(pool, appeal_bad=1.0))):
            for dep in HEALTH_DEPOSITS:
                rows.append((_pre(what) + f"{name}; `SOLVER_DEPOSIT_BPS` {dep:,}", lambda h, w=w: Z.Solver(h, w),
                             replace(p0, SOLVER_DEPOSIT_BPS=dep), "health"))
        # post hoc (added after the no-deposit table was seen): no deposit, with rival solvers disputing
        for n, q in ((3, 0.25), (10, 0.25)):
            w = world(pool, rival_solvers=n, rival_find=q)
            rows.append((_pre(what) + f"no appeal, {n} rival solvers at {100 * q:.0f} % (post hoc); "
                         "`SOLVER_DEPOSIT_BPS` 0", lambda h, w=w: Z.Solver(h, w), P0, "health"))
    return rows


def health(net: Net, honest_only: bool) -> Tuple[float, float, float, float]:
    """(funded issues, correctly fixed and paid, wrongly marked fixed, median days a wrong fix stood before its
    reversal). One submission is one funded issue; an issue neither is left unfixed."""
    subs = [s for s in net.subs.values() if s.tier == ISSUE and (s.party is None or not honest_only)]
    stood = sorted((s.final_t - s.verdict_t) / 24 for s in subs
                   if not s.good and s.reversed and s.final is False and s.verdict_t is not None)
    return (len(subs), sum(1 for s in subs if s.good and s.final), sum(1 for s in subs if not s.good and s.final),
            stood[len(stood) // 2] if stood else float("nan"))


def health_table(data) -> str:
    """Per 100 funded issues, the bad-fix solver's issues included. The bad-fix solver is present while its return is
    above zero; when it is not, it has left (its twin's run is used) and its issues count as left unfixed. `STAY_AWAY` x the deposit's share of honest solvers submit nothing (assumed)."""
    head = ["Network", "The bad-fix solver's return ($ a year)", "It stays?", "Honest solvers that stay away "
            "(assumed)", "Correctly fixed and paid, per 100 funded issues", "Wrongly marked fixed",
            "Left unfixed", "Median days a wrong fix stands before reversal"]
    lines = []
    for name, r, _ in data:
        dep = int(name.rsplit("`SOLVER_DEPOSIT_BPS` ", 1)[1].replace(",", "")) / 10_000
        stays = r["diff"] > 0
        pre = "" if stays else "twin_"
        n, fixed, wrong, a_wrong = (r[pre + k] for k in ("h_n", "h_fixed", "h_wrong", "a_wrong"))
        a_n = r["a_n"]  # the attacker's issues stay funded when it leaves: unfixed, as nobody else took them
        for slope in STAY_AWAY:
            away = min(1.0, slope * dep)
            total = n + a_n
            f, wr = (1 - away) * fixed, (1 - away) * wrong + a_wrong
            if slope and not dep:
                continue  # no deposit: nobody stays away for it
            lines.append([name, f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}", "yes" if stays else "no (it has left)",
                          f"{100 * away:.0f} %", f"{100 * f / total:.1f}", f"{100 * wr / total:.1f}",
                          f"{100 * (total - f - wr) / total:.1f}", f"{r[pre + 'h_stood']:.1f}"])
    return _table(head, lines)


def nodeposit_rows() -> List[AttRow]:
    """With no solver's deposit: what a solver of bad fixes earns (5 a week; its twin submits nothing) as rival
    solvers dispute, with the seats 10.1 gives (Opus 5.5 alone, or Opus, GPT-6.1 and Gemini) and with GPT-6.1 alone; the same solver trying each issue again; and
    the deposit for comparison. The disputer is paid `EVIDENCE_REWARD_BPS` (1,000) of the reversed fix's bounty."""
    rows: List[AttRow] = []
    for pool, what in POOLS:
        pre = _pre(what)
        grid = ((0, 0.0), (1, 0.25), (3, 0.10), (3, 0.25), (3, 0.50), (10, 0.10), (10, 0.25), (10, 0.50))
        for n, q in grid:
            w = world(pool, rival_solvers=n, rival_find=q)
            who = f"{n} rival solver{'s' if n != 1 else ''}" + (f" at {100 * q:.0f} %" if n else "")
            rows.append((pre + f"no deposit; contenders and {who}", lambda h, w=w: Z.Solver(h, w), P0, "solver"))
        w = world(pool, find=0.0, false=0.0)
        rows.append((pre + "no deposit; no test disputes at all", lambda h, w=w: Z.Solver(h, w), P0, "solver"))
        for n, q in ((0, 0.0), (3, 0.25), (10, 0.25), (10, 0.50)):  # GPT-6.1 the only family registered (28 of it)
            w = replace(world(pool, seats=(("openai", "openai"),), rival_solvers=n, rival_find=q), initial_active=28)
            rows.append((pre + f"no deposit; GPT-6.1 alone seated; contenders and {n} rival solvers"
                         + (f" at {100 * q:.0f} %" if n else ""), lambda h, w=w: Z.Solver(h, w), P0, "solver"))
        for n, q in ((0, 0.0), (10, 0.25), (10, 0.50)):
            w = world(pool, rival_solvers=n, rival_find=q)
            rows.append((pre + f"no deposit; it tries each issue up to 21 times; contenders and {n} rival solvers"
                         + (f" at {100 * q:.0f} %" if n else ""), lambda h, w=w: Retrier(h, w, retry=20), P0,
                         "solver"))
        for dep in (2_500, 4_000):
            w = world(pool)
            rows.append((pre + f"for comparison: deposit {dep:,}; contenders and 0 rival solvers",
                         lambda h, w=w: Z.Solver(h, w), replace(BASE, SOLVER_DEPOSIT_BPS=dep), "solver"))
    return rows


ATTACKS: Dict[str, Callable[[], List[AttRow]]] = {"appeal_attack0": appeal_attack0_rows, "nodeposit": nodeposit_rows, "health": health_rows, "appeal_attack": appeal_attack_rows, "retry": retry_rows,
                                                  "sponsor_attack": sponsor_attack_rows}


def _party_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = Z._party_metrics(net, a)
    st = net.stats
    days = max(1.0, net.t / 24.0)
    mine = [s for s in net.subs.values() if s.sponsor == a.party]
    m.update(sponsored=len(mine), sponsored_upheld=sum(1 for s in mine if s.appeal == "upheld"),
             sponsored_paid=sum(1 for s in mine if s.final), sponsored_bad_paid=sum(1 for s in mine
                                                                                   if s.final and not s.good),
             bad_merged=st["bad_merged"], **_health(net),
             weak_seated=(100 * sum(net.seats.seated_days[f] for f in ("deepseek", "qwen", "mistral", "nvidia")) / days
                          if net.seats is not None else 0.0))
    return m


def _health(net: Net) -> Dict[str, float]:
    n, fixed, wrong, stood = health(net, True)
    an, _, awrong, _ = health(net, False)
    return dict(h_n=n, h_fixed=fixed, h_wrong=wrong, h_stood=stood, a_n=an - n, a_wrong=awrong - wrong)


def _run_attack(job) -> Dict[str, object]:
    table, i, seed = job
    _, make, p, _ = ATTACKS[table]()[i]
    return A.against_twin(make, [seed], p=p, metrics=_party_metrics)


def run_attacks(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = ATTACKS[table]()
    res = C._map(_run_attack, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    return [(rows[i][0], C._twin(res[i * len(seeds):(i + 1) * len(seeds)]), rows[i][3]) for i in range(len(rows))]


def _got(kind: str, r: Dict[str, object]) -> str:
    if kind == "sponsor":
        return (f"{r['sponsored']:.0f} appeals sponsored, {r['sponsored_upheld']:.0f} upheld, "
                f"{r['sponsored_paid']:.0f} paid, {r['sponsored_bad_paid']:.0f} of them bad fixes; bad fixes paid in "
                f"the network {r['bad_merged']:.0f} (twin's run: {r['twin_bad_merged']:.0f}); the four weak families "
                f"seated {r['weak_seated']:.0f} % of the year, added (twin's run: {r['twin_weak_seated']:.0f} %)")
    return Z._got(kind, r)


def attack_table(data) -> str:
    head = ["Attacker", "Return − twin's ($ a year, ± 2 SE)", "Against its twin", "Attacker's return", "Twin's return",
            "What it got"]
    return _table(head, [[name, f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}", R._verdict(r["diff"], r["se"]),
                          f"{r['attacker']:,.0f}", f"{r['twin']:,.0f}", _got(kind, r)] for name, r, kind in data])


# ---------- exact: the stake that closes the appeal ----------

def break_even(stake: float, deposit: float, reversed_after: float = 0.0) -> float:
    """No simulation. The acceptance rate above which appealing a fix pays, for a solver: it stakes `stake` of the
    bounty to win the bounty and its deposit (`deposit` of the bounty) back, and a test dispute then reverses the
    pass with chance `reversed_after`. Gain when q (1 - r)(1 + d) > (1 - q) s."""
    win = (1 - reversed_after) * (1 + deposit)
    return stake / (stake + win)


def break_even_table() -> str:
    head = ["Stake, share of the bounty", "Deposit 2,500: an appeal pays above", "…if half the bad fixes it wins are "
            "then reversed by a test", "Deposit 4,000: an appeal pays above", "…if half are then reversed",
            "A sponsor paid 1,000 of the bounty gains above", "A sponsor paid 2,500 gains above"]
    lines = []
    for s in (0.05, 0.10, 0.25, 0.50):
        lines.append([f"{100 * s:.0f} %"] + [f"{100 * break_even(s, d, r):.1f} %" for d in (0.25, 0.40)
                                              for r in (0.0, 0.5)]
                     + [f"{100 * s / (s + x):.0f} %" for x in (0.10, 0.25)])
    return _table(head, lines)


TITLES = {
    "appeal": "The appeal on evidence, decided by the seated families (D24): the two assumed rates",
    "appeal_attack": "The solver that appeals every rejection with a test it wrote, against the same solver that "
                     "never appeals",
    "retry": "The deposit held during the appeal period (D28): a solver that tries the same issue again",
    "sponsor": "Sponsorship and seating (D25, D26), on live scores",
    "sponsor_attack": "A contender that sponsors (its twin sponsors nothing)",
    "known": "Known-answer issues (D26), on live scores",
    "second": "The second panel (D27), with second-opinion challenges",
    "final": "Task 10.1's network beside the revision",
    "rivals": "Rival solvers as disputers (D21: anyone may dispute a pass)",
    "health": "Code health across the solver's deposit, per 100 funded issues",
    "appeal_attack0": "The solver that appeals every rejection, with no deposit",
    "nodeposit": "No solver's deposit: the solver of bad fixes against rival solvers' disputes",
}
ORDER = ("exact", "appeal", "appeal_attack", "appeal_attack0", "retry", "sponsor", "sponsor_attack", "known", "second", "final",
         "rivals", "nodeposit", "health")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.evidence")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="4 seeds")
    ap.add_argument("--only", default="", help="comma-separated tables: " + ", ".join(ORDER))
    a = ap.parse_args(argv)
    seeds = list(range(1, (4 if a.quick else a.seeds) + 1))
    only = [x for x in a.only.split(",") if x] or list(ORDER)
    print(f"Seeds 1-{seeds[-1]}; every ± is two standard errors of the mean.\n")
    show = {"rivals": rival_table, "appeal": appeal_table, "known": known_table, "second": second_table, "sponsor": sponsor_table,
            "final": final_table}
    for name in only:
        if name == "exact":
            print("### The acceptance rate above which an appeal pays (exact, no simulation)\n")
            print(break_even_table() + "\n")
            continue
        print(f"### {TITLES[name]}\n", flush=True)
        if name == "health":
            print(health_table(run_attacks(name, seeds, a.jobs)) + "\n", flush=True)
        elif name in ATTACKS:
            print(attack_table(run_attacks(name, seeds, a.jobs)) + "\n", flush=True)
        else:
            print(show[name](run_table(name, seeds, a.jobs)) + "\n", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
