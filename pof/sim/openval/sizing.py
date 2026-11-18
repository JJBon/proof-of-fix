"""Sizing D20-D23 on measured judges and the market fee (proof-of-fix#236, task 10.1 of #132's change).

`measured` and `contenders` showed what #160's verdicts do to v3. The owner then agreed four rules (design D20-D23,
2026-11-14) whose values this module sweeps, each beside its alternative on the same seeds, so a new parameters ADR
can fix them:

- **seats by rank** (`SEAT_RULE` "rank"): `SEAT_MARGIN` and `CAP_MIN_FAMILIES`, with the scores read from known
  answers (an upper bound) and live, from final outcomes (`seats`);
- **the solver's deposit** (`SOLVER_DEPOSIT_BPS`) and where a rejected fix's deposit goes (`SOLVER_DEPOSIT_TO`);
- **the appeal** (`APPEAL`): its panel drawn from the families that did not judge the fix, contenders included (the
  owner's decision), or from the seated ones, and the pass rule on it;
- **a new family's start** (`NEW_FAMILY_START`): as a contender, or D14's neutral start.

Every network runs on the market's fee and unit prices (`pricing.Market`), with the measured world's validators: the
market's entry and exit are off (`MW`), since its entry rule knows nothing of what a contender earns by disputing.

The actors, each against its honest twin (`actors.against_twin`):
- `Solver`: bad fixes, 5 a week, colluding with nobody (`contenders.BadFixSolver`'s submissions); it may appeal every
  rejection (10.1's first new actor) and may try the same issue again after a rejection (`retry`);
- `Disputer`: posts tests against passes with no evidence (10.1's second new actor): tests that pass on the fixed
  code, or tests that fail on it and state the wrong requirement. Its twin posts nothing. Beside it, an honest
  contender: it runs a model, searches the passes its model failed and posts the tests it finds;
- report v3's judged spammer (`pricing.Spammer`), on measured judges.

    python3 -m pof.sim.openval.sizing [--seeds 40] [--jobs 8] [--quick] [--only seats,live,...]

prints reports/open-validators-measured-v3.md's tables, in about 15 minutes on 15 cores. No model call: verdicts are
replayed from data/judges/verdicts-v2.matrix.json. Assumed, not measured: how often a flagged bad fix yields a failing
test (`World.evidence_find`), how often a test stating the wrong requirement is accepted (`World.evidence_false`),
which rejections honest solvers appeal (`World.appeal_good`, `appeal_bad`), and what a contender's search costs.
Rows labelled "post hoc" were added after the first full run's results were seen.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import contenders as C
from . import measured as M
from . import panels as D
from . import pricing as PR
from . import report as R
from . import scores as SC
from .net import ISSUE, Net
from .params import BPS, D236, PARAMS, WEEK, WORLD, Params, World

MW = replace(PR.MARKET, initial=0, entry=False)  # the market's fee and prices; the measured world's validators
T_WRONG = 0x236E57  # randomness tag: whether a test that states the wrong requirement is accepted
POOLS = (("hidden", "the tests fail them"), ("pbw", "pass the tests, wrong"))
FIND, FALSE = 0.5, 0.05  # the assumed base: evidence found 1 time in 2; a wrong test accepted 1 time in 20
BASE = replace(D236, APPEAL="off")  # the proposal less the appeal: each table moves one rule from here
SEARCH_COST = 0.50  # assumed: what one search for a failing test costs a contender (about four judge-grade calls)


def world(pool: str, find: float = FIND, false: float = FALSE, scores: str = "known", seats=M.SEVEN,
          second_opinions: bool = False, **kw) -> World:
    """`measured.world`'s grown network judging as #160's seats did, with the world's contenders disputing passes
    (every one of the nine models measured) and the seat rule's scores read from `scores`.

    Without `second_opinions`, nobody challenges a verdict only because another model disagrees (D21: "the existing
    challenge stays for fabricated receipts"; honest judges fabricate none): reports measured-v1 and -v2 let a
    volunteer running a model drawn by the seed do so, and with one family seated most of those challenges wait for
    a fresh panel that never comes (the seats table has the row)."""
    w = replace(C.with_evidence(M.world(seats, pool), find, false=false), seat_scores=scores, **kw)
    return w if second_opinions else replace(w, volunteer_per_day=0.0)


def market_on(net: Net, actor: A.Actor) -> None:
    # every family with a seat in the judges' table is priced, so one that registers later is too
    fams = tuple(dict.fromkeys(tuple(net.w.families) + tuple(f for f, _ in net.w.measured_seats)))
    actor.market = PR.Market(net.p, replace(net.w, families=fams), MW, net.seed)  # type: ignore[attr-defined]
    net.fee = actor.market  # type: ignore[attr-defined]
    actor.market.start(net)  # type: ignore[attr-defined]


class OnMarket(A.Actor):
    """No attacker: the world `w` on the market fee (`scores`: v3's D14 scores installed, for the reference row)."""
    name = "market"
    party = "nobody"

    def __init__(self, honest: bool = True, w: World = WORLD, scores: bool = False):
        super().__init__(honest)
        self.w, self.scores = w, scores

    def world(self) -> World:
        return self.w

    def setup(self, net: Net) -> None:
        market_on(net, self)
        if self.scores:
            SC.install(net)

    def on_tick(self, net: Net) -> None:
        self.market.on_tick(net)  # type: ignore[attr-defined]


# ---------- the actors ----------

class Solver(OnMarket):
    """A solver of bad fixes, `per_week` a week, that colludes with nobody. `appeal`: it appeals every rejection.
    `retry`: after a rejection is final it submits another bad fix to the same issue, up to `retry` more times; it
    is the only solver of its issues, so a rejected fix's deposit, added to the issue's bounty, comes back to it when
    one of its fixes is paid (the best case for it). Its twin (`twin`): "none" submits nothing; "no_appeal" submits
    the same fixes and never appeals; "no_retry" submits them once."""
    name = "bad-fix solver"
    party = "bad-fix solver"

    def __init__(self, honest: bool = False, w: World = WORLD, per_week: float = 5.0, appeal: bool = False,
                 retry: int = 0, twin: str = "none"):
        super().__init__(honest, w)
        if twin not in ("none", "no_appeal", "no_retry"):
            raise ValueError(twin)
        self.per_week = per_week
        self.does_appeal = appeal and not (honest and twin == "no_appeal")
        self.retries = 0 if honest and twin == "no_retry" else retry
        self.submits = not honest or twin != "none"
        self.subs: List = []
        self.tries: Dict[int, int] = {}

    def setup(self, net: Net) -> None:
        super().setup(net)
        if not self.submits:
            return
        rng = random.Random(D.h(net.seed, D.T_GRIND, 7))  # `contenders.BadFixSolver`'s submissions, fix for fix
        t, times = 0.0, []
        while True:
            t += rng.expovariate(self.per_week / WEEK)
            if t > net.w.horizon_h:
                break
            times.append(t)
        for i, (t, b) in enumerate(zip(times, A._bounties(net, rng, len(times), net.w.bounty_max))):
            self.subs.append(net.submit(t, b, False, "bad-fix-solver", self.party, issue=i))
            self.tries[i] = 1

    def on_tick(self, net: Net) -> None:
        super().on_tick(net)
        if not self.retries:
            return
        open_subs = []
        for s in self.subs:
            if s.final is None and s.state != "withdrawn":
                open_subs.append(s)
            elif s.final is False and self.tries[s.issue] <= self.retries:
                self.tries[s.issue] += 1
                open_subs.append(net.submit(net.t, s.bounty, False, "bad-fix-solver", self.party, issue=s.issue))
        self.subs = open_subs

    def appeals(self, net: Net, sub) -> bool:
        return self.does_appeal


class Disputer(OnMarket):
    """A party that posts tests against passes. Its twin posts nothing.
    - `kind` "passing": no evidence and no model; its tests pass on the fixed code, so each falls with no panel and
      its stake goes to the solver.
    - `kind` "wrong": no evidence and no model; its tests fail on the fixed code and state a requirement the issue
      didn't ask for; the challenge panel accepts one with `World.evidence_false` (assumed). `select`: it posts only
      where it expects to gain, knowing that rate, the stake and the reward.
    - `kind` "contender": an honest contender running `seat`'s model. It searches every pass its model failed
      (`search_cost` each, assumed) and posts a test when the search finds one (`measured.evidence`'s draw, shared by
      every contender: a bug that is hard to test is hard for all of them). It files before the world's others."""
    name = "disputer"
    party = "disputer"

    def __init__(self, honest: bool = False, w: World = WORLD, kind: str = "wrong", select: bool = False,
                 seat: str = "openai", search_cost: float = SEARCH_COST):
        super().__init__(honest, w)
        if kind not in ("passing", "wrong", "contender"):
            raise ValueError(kind)
        self.kind, self.select, self.seat, self.search_cost = kind, select, seat, search_cost

    def tests(self, net: Net, sub):
        p, w = net.p, net.w
        if self.honest:
            return None
        if self.kind == "contender":
            if M.case_of(net, sub)[self.seat]:
                return None  # its model passed the fix too: nothing to search
            net.parties[self.party].costs += self.search_cost
            net.stats["disputer_searches"] += 1
            found = D.u(net.seed, M.T_EVIDENCE, sub.sid) < (w.evidence_false if sub.good else w.evidence_find)
            return (True, True) if found else None
        if self.kind == "passing":
            return (False, False)
        if self.select:
            q = w.evidence_false
            win = (sub.sdeposit + p.EVIDENCE_REWARD_BPS * sub.bounty / BPS)
            if q * win <= (1 - q) * p.evidence_stake(sub.bounty):
                return None
        return (D.u(net.seed, T_WRONG, sub.sid) < w.evidence_false, True)


class NewFamily(OnMarket):
    """`n` honest validators of a model family the network has not seen register in week `week` (already qualified:
    what is tested is the family's seat, not D5). The family must have a seat in `World.measured_seats` and be left
    out of `World.families`."""
    name = "new family"
    party = "new-family"

    def __init__(self, honest: bool = True, w: World = WORLD, family: str = "mistral", n: int = 4, week: float = 8.0):
        super().__init__(honest, w)
        self.family, self.n, self.week = family, n, week

    def setup(self, net: Net) -> None:
        super().setup(net)
        net._at(self.week * WEEK, self._join, net)

    def _join(self, net: Net) -> None:
        w = net.w
        for i in range(self.n):
            net.register_actor(i, self.party, w.initial_bond, w.hosts[i % len(w.hosts)], w.tees[i % len(w.tees)],
                               self.family, f"new-family-op-{i}", None, active=True)


def late(pool: str, family: str, **kw) -> World:
    """The seven-family world without `family`'s validators (its seat stays in the judges' table for `NewFamily`)."""
    w = world(pool, scores="live", **kw)
    fams = tuple(f for f in w.families if f != family)
    return replace(w, families=fams, initial_active=4 * len(fams))


# ---------- what the tables read ----------

def metrics(net: Net) -> Dict[str, float]:
    m = C.metrics(net)
    st, w = net.stats, net.w
    subs = [s for s in net.subs.values() if s.tier == ISSUE and s.final is not None and s.party is None]
    good = [s for s in subs if s.good]
    # a verdict never final: a challenge (D4: it waits, window frozen) still without a panel four weeks on. Such a
    # good fix is unpaid and its deposit locked: both are counted as lost
    old = [s for s in net.subs.values() if s.tier == ISSUE and s.party is None and s.verdict is not None
           and s.verdict_t < net.t - 4 * WEEK]
    stuck = [s for s in old if s.state == "challenged"]
    m["stuck_pct"] = 100 * len(stuck) / max(1, len(old))
    good += [s for s in stuck if s.good]

    def lost(s) -> float:  # its deposit, when it went elsewhere or is locked behind a verdict never final
        return s.sdeposit if s.sdeposit_to != "returned" and (s.sdeposit_to or s.final is None) else 0.0

    m["good_failed_pct"] = 100 * sum(1 for s in good if not s.final) / max(1, len(good))
    m["cost_good"] = mean(w.attempt_fee + s.charges + lost(s) - s.stakes_won for s in good) if good else float("nan")
    m["checks_good"] = mean(s.charges for s in good) if good else float("nan")
    m["dep_good"] = mean(lost(s) for s in good) if good else float("nan")
    rej_bad = [s for s in subs if not s.good and not s.verdict]
    rej_good = [s for s in good if not s.verdict]
    app_bad = [s for s in rej_bad if s.appeal in ("upheld", "failed")]
    m["appeals"] = st["appeals"]
    m["appeals_no_panel"] = st["appeals_no_panel"]
    m["overturned_pct"] = (100 * sum(1 for s in app_bad if s.appeal == "upheld") / len(app_bad)
                           if app_bad else float("nan"))
    m["overturned_n"] = sum(1 for s in rej_bad if s.appeal == "upheld")
    m["appeal_paid_bad"] = sum(1 for s in rej_bad if s.appeal == "upheld" and s.final)
    m["restored_pct"] = 100 * sum(1 for s in rej_good if s.final) / len(rej_good) if rej_good else float("nan")
    m["rej_days"] = (mean((s.final_t - s.verdict_t) / 24 for s in subs if not s.verdict and not s.final)
                     if any(not s.verdict and not s.final for s in subs) else float("nan"))
    m["sdep_bounty"] = st["sdep_bounty"] + st["sdep_pool"]
    m["sdep_disputer"] = st["sdep_disputer"]
    m["reward"] = st["evidence_reward"]
    market = getattr(net.fee, "series", None) or getattr(getattr(net.fee, "inner", None), "series", [])
    tail = [r["fee"] for r in market if r["t"] > net.t - 13 * WEEK]
    m["fee"] = mean(tail) if tail else float("nan")
    seats = net.seats
    days = max(1.0, net.t / 24.0)
    if seats is not None:
        for f in {v.family for v in net.reg.validators.values()}:
            m[f"seated_{f}"] = 100 * seats.seated_days[f] / days
        m["n_seated"] = sum(seats.seated_days.values()) / days
        m["fallback_pct"] = 100 * seats.fallbacks / days if seats.source == "live" else 0.0
    m["k"] = mean(s.k for s in subs) if subs else float("nan")
    return m


def _new_family_metrics(net: Net) -> Dict[str, float]:
    m = metrics(net)
    a = net.actors[-1]
    fam = a.family
    first = net.seats.first_seated.get(fam) if hasattr(net.seats, "first_seated") else None
    m["new_seated"] = m.get(f"seated_{fam}", 0.0) * 52 / max(1e-9, 52 - a.week)  # of the weeks it was there
    m["new_first_week"] = first / WEEK if first is not None else float("nan")
    m["new_ever"] = 100.0 * (first is not None)
    m["new_counted"] = sum(1 for s in net.subs.values() for vid, _, _ in s.judges
                           if net.reg.validators[vid].family == fam)
    return m


Row = Tuple[str, World, Params, Optional[Callable[[World], A.Actor]]]


def _pre(what: str) -> str:
    return f"bad = {what}: "


def seat_rows() -> List[Row]:
    """D20 on known answers: `SEAT_MARGIN` (with `SCORE_MIN` 70 % and, to show what the margin alone seats, 50 %),
    then `CAP_MIN_FAMILIES` where one, two and three families are seated."""
    rows: List[Row] = []
    for pool, what in POOLS:
        w, pre = world(pool), _pre(what)
        rows.append((pre + "v3 as designed (seats at `SCORE_MIN`, scores on agreement, the family cap, second-opinion "
                     "challenges); test disputes on", world(pool, second_opinions=True), PARAMS,
                     lambda w: OnMarket(w=w, scores=True)))
        for mg in (0.0, 0.01, 0.02, 0.05, 0.10, 0.25):
            mark = "**" if mg == 0.05 else ""
            rows.append((pre + f"{mark}`SEAT_MARGIN` {100 * mg:.0f} points{mark}", w, replace(BASE, SEAT_MARGIN=mg),
                         None))
        for mg in (0.10, 0.25, 0.40):
            rows.append((pre + f"`SEAT_MARGIN` {100 * mg:.0f} points, `SCORE_MIN` 50 %", w,
                         replace(BASE, SEAT_MARGIN=mg, SCORE_MIN=0.50), None))
        for mg, n in ((0.05, 1), (0.05, 2), (0.05, 4), (0.01, 2), (0.01, 3)):
            rows.append((pre + f"`CAP_MIN_FAMILIES` {n}, `SEAT_MARGIN` {100 * mg:.0f} points", w,
                         replace(BASE, SEAT_MARGIN=mg, CAP_MIN_FAMILIES=n), None))
        rows.append((pre + "`SEAT_MARGIN` 5 points, with volunteers' second-opinion challenges (D4; as reports "
                     "measured-v1 and -v2 ran)", world(pool, second_opinions=True), BASE, None))
    return rows


WIDE = replace(BASE, SCORE_WINDOW=1400, SCORE_MIN_VERDICTS=350)  # a window of about 200 fixes at k = 7 (post hoc)


def live_rows() -> List[Row]:
    """D20 with D23's live scores: the margin, with and without the appeal feeding the scores, without disputes, the
    contenders' shadow rate, and a wider score window."""
    rows: List[Row] = []
    for pool, what in POOLS:
        w, pre = world(pool, scores="live"), _pre(what)
        rows.append((pre + "known answers, `SEAT_MARGIN` 5 (the upper bound)", world(pool), BASE, None))
        for mg in (0.02, 0.05, 0.10):
            rows.append((pre + f"live, `SEAT_MARGIN` {100 * mg:.0f}, no appeal", w, replace(BASE, SEAT_MARGIN=mg),
                         None))
        rows += [(pre + "live, `SEAT_MARGIN` 5, appeal to other families (majority)", w, D236, None),
                 (pre + "live, `SEAT_MARGIN` 5, appeal to the seated families", w, replace(D236, APPEAL="seated"),
                  None),
                 (pre + "live, `SEAT_MARGIN` 5, no disputes and no appeal", world(pool, 0.0, 0.0, "live"), BASE,
                  None),
                 (pre + "live, `SEAT_MARGIN` 5, no appeal, six contender shadows a draw", w,
                  replace(BASE, CONTENDER_SHADOWS=6), None),
                 (pre + "live, `SEAT_MARGIN` 5, no appeal, score window 1,400 verdicts (post hoc)", w, WIDE, None),
                 (pre + "live, `SEAT_MARGIN` 5, appeal to other families, score window 1,400 (post hoc)", w,
                  replace(WIDE, APPEAL="others"), None)]
    return rows


DEPOSITS = (0, 500, 1_000, 1_500, 2_500, 4_000, 5_000, 7_500)


def deposit_rows() -> List[Row]:
    rows: List[Row] = []
    for pool, what in POOLS:
        w, pre = world(pool), _pre(what)
        for bps in DEPOSITS:
            mark = "**" if bps == 2_500 else ""
            rows.append((pre + f"{mark}`SOLVER_DEPOSIT_BPS` {bps:,}{mark}", w, replace(BASE, SOLVER_DEPOSIT_BPS=bps),
                         None))
        rows += [(pre + "`SOLVER_DEPOSIT_BPS` 2,500, no disputes", world(pool, 0.0, 0.0), BASE, None),
                 (pre + "`SOLVER_DEPOSIT_BPS` 2,500, a wrong test accepted 1 time in 5", world(pool, FIND, 0.20), BASE,
                  None),
                 (pre + "`SOLVER_DEPOSIT_BPS` 2,500, the idle signal counts seated validators only", w,
                  replace(BASE, IDLE_COUNTS="seated"), None)]
    return rows


APPEALS: Tuple[Tuple[str, Dict[str, str]], ...] = (
    ("no appeal", dict(APPEAL="off")),
    ("**other families, contenders included; majority** (the owner's decision)", dict(APPEAL="others")),
    ("other families, contenders included; every judge must pass",
     dict(APPEAL="others", APPEAL_PASS_RULE="unanimous")),
    ("other families, seated only", dict(APPEAL="others_seated")),
    ("the seated families' next draw", dict(APPEAL="seated")),
)


def appeal_rows() -> List[Row]:
    rows: List[Row] = []
    for pool, what in POOLS:
        for who, bad in (("honest solvers appeal good fixes only", 0.0),
                         ("honest solvers appeal every rejection", 1.0)):
            for name, kw in APPEALS:
                if bad and kw["APPEAL"] == "off":
                    continue
                rows.append((_pre(what) + f"{name}; {who}", world(pool, appeal_bad=bad), replace(D236, **kw), None))
        rows.append((_pre(what) + "other families, contenders included; majority; honest solvers appeal every "
                     "rejection; no disputes", world(pool, 0.0, 0.0, appeal_bad=1.0), D236, None))
    return rows


def new_family_rows() -> List[Row]:
    """A new family's start, on live scores: a weak newcomer (Mistral Large 3: 92 % of bad fixes passed) and a strong
    one (Opus 5.5, into a network whose genesis family is GPT-6.1)."""
    rows: List[Row] = []
    for pool, what in POOLS:
        for fam, kind in (("mistral", "weak"), ("anthropic", "strong")):
            w = late(pool, fam)
            for start, p in (("**a contender**", BASE),
                             ("neutral (v3, D14)", replace(BASE, NEW_FAMILY_START="neutral")),
                             ("a contender, six contender shadows a draw", replace(BASE, CONTENDER_SHADOWS=6)),
                             ("a contender, with the appeal to other families (majority)", D236),
                             ("a contender, with the appeal and six contender shadows a draw",
                              replace(D236, CONTENDER_SHADOWS=6))):
                rows.append((_pre(what) + f"a {kind} family ({M.NAMES[fam]}) joins in week 8, starting as {start}",
                             w, p, lambda w, fam=fam: NewFamily(w=w, family=fam)))
    return rows


def final_rows() -> List[Row]:
    """v3 as designed beside the proposal, whole."""
    rows: List[Row] = []
    for pool, what in POOLS:
        w, pre = world(pool), _pre(what)
        rows += [(pre + "v3 as designed (second-opinion challenges, no test disputes)",
                  world(pool, 0.0, 0.0, second_opinions=True), PARAMS, lambda w: OnMarket(w=w, scores=True)),
                 (pre + "seats by rank alone (no disputes, no deposit, no appeal)", world(pool, 0.0, 0.0),
                  replace(PARAMS, SEAT_RULE="rank", NEW_FAMILY_START="contender"), None),
                 (pre + "…and disputes, the deposit, no appeal", w, BASE, None),
                 (pre + "**the proposal (D236)**: …and the appeal to other families, majority", w, D236, None),
                 (pre + "the proposal, appeal to the seated families", w, replace(D236, APPEAL="seated"), None),
                 (pre + "the proposal, appeal to other families, every judge must pass", w,
                  replace(D236, APPEAL_PASS_RULE="unanimous"), None),
                 (pre + "the proposal, on live scores", world(pool, scores="live"), D236, None)]
    return rows


TABLES: Dict[str, Callable[[], List[Row]]] = {"seats": seat_rows, "live": live_rows, "deposit": deposit_rows,
                                              "appeal": appeal_rows, "new": new_family_rows, "final": final_rows}


def run_row(row: Row, seed: int) -> Net:
    _, w, p, extra = row
    return Net(seed, p, w, [extra(w) if extra is not None else OnMarket(w=w)]).run()


def _run(job) -> Dict[str, float]:
    table, i, seed = job
    net = run_row(TABLES[table]()[i], seed)
    return _new_family_metrics(net) if table == "new" else metrics(net)


def run_table(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = TABLES[table]()
    res = C._map(_run, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    out = []
    for i, row in enumerate(rows):
        chunk = res[i * len(seeds):(i + 1) * len(seeds)]
        keys = sorted({k for r in chunk for k in r})
        out.append((row[0], row[1], {k: [r.get(k, float("nan")) for r in chunk] for k in keys}))
    return out


_ms = M._ms


def _table(head: Sequence[str], lines: Sequence[Sequence[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(x) + " |" for x in lines])


def _seated(m, fams=("anthropic", "openai", "google")) -> List[str]:
    others = [k for k in m if k.startswith("seated_") and k[7:] not in fams]
    rest = [sum(x for x in xs if x == x) for xs in zip(*(m[k] for k in others))] if others else []
    return [_ms(m.get(f"seated_{f}", []), 0, " %") for f in fams] + [_ms(rest, 0, " %")]


def honest_table(data, seats: bool = False, appeal: bool = False) -> str:
    head = ["Network", "Bad fixes merged per 100 paid", "Good fixes wrongly unpaid",
            "An honest solver's cost per good fix", "…of which deposits lost", "Fixes paid a year",
            "Submissions that waited", "Verdicts never final", "Service fee, last 13 weeks"]
    if seats:
        head += ["Opus 5.5 seated, share of the year", "GPT-6.1", "Gemini 3.1 Pro", "the four others, their shares added",
                 "No family met the rule, share of the year"]
    if appeal:
        head += ["Appeals a year", "Correct rejections overturned, of those appealed", "Bad fixes paid after an "
                 "appeal, a year", "Wrongly rejected good fixes paid in the end", "Appeals with no panel"]
    lines = []
    for label, _, m in data:
        line = [label, _ms(m["bad_per_100"], 1), _ms(m["good_failed_pct"], 1, " %"), "$" + _ms(m["cost_good"], 2),
                "$" + _ms(m["dep_good"], 2), _ms(m["paid_n"], 0), _ms(m["waited_pct"], 1, " %"),
                _ms(m["stuck_pct"], 1, " %"), "$" + _ms(m["fee"], 3)]
        if seats:
            line += _seated(m) + [_ms(m.get("fallback_pct", []), 0, " %")]
        if appeal:
            line += [_ms(m["appeals"], 0), _ms(m["overturned_pct"], 0, " %"), _ms(m["appeal_paid_bad"], 1),
                     _ms(m["restored_pct"], 0, " %"), _ms(m["appeals_no_panel"], 0)]
        lines.append(line)
    return _table(head, lines)


def new_family_table(data) -> str:
    head = ["Network", "Bad fixes merged per 100 paid", "Good fixes wrongly unpaid", "Runs in which the new family "
            "was ever seated", "Week it was first seated", "Seated, share of its weeks", "Counted verdicts it gave",
            "No family met the rule, share of the year"]
    return _table(head, [[label, _ms(m["bad_per_100"], 1), _ms(m["good_failed_pct"], 1, " %"),
                          _ms(m["new_ever"], 0, " %"), _ms(m["new_first_week"], 0), _ms(m["new_seated"], 0, " %"),
                          _ms(m["new_counted"], 0), _ms(m.get("fallback_pct", []), 0, " %")] for label, _, m in data])


# ---------- the attackers ----------

def _on_measured(make: Callable[[bool], A.Actor], pool: str) -> Callable[[bool], A.Actor]:
    """`contenders.on_measured`, with the base's disputes and the seat rule on known answers."""
    def made(h: bool) -> A.Actor:
        a = make(h)
        base = a.world()
        a.world = lambda: replace(base, family_accuracy=(), family_blind=(), measured=pool, measured_seats=M.FOUR,
                                  evidence_find=FIND, evidence_false=FALSE, evidence_by=C.ALL_SEATS,
                                  seat_scores="known")
        return a
    return made


AttRow = Tuple[str, Callable[[bool], A.Actor], Params, str]


def deposit_attack_rows() -> List[AttRow]:
    rows: List[AttRow] = []
    for pool, what in POOLS:
        w, pre = world(pool), _pre(what)
        for bps in DEPOSITS:
            rows.append((pre + f"bad-fix solver, `SOLVER_DEPOSIT_BPS` {bps:,}", lambda h, w=w: Solver(h, w),
                         replace(BASE, SOLVER_DEPOSIT_BPS=bps), "solver"))
        w0 = world(pool, 0.0, 0.0)
        for bps, note in ((0, ""), (2_500, ""), (4_000, ""), (5_000, " (post hoc)"), (7_500, " (post hoc)")):
            rows.append((pre + f"bad-fix solver, `SOLVER_DEPOSIT_BPS` {bps:,}, no disputes{note}",
                         lambda h, w=w0: Solver(h, w), replace(BASE, SOLVER_DEPOSIT_BPS=bps), "solver"))
        for n, times in ((5, "six"), (20, "21")):
            for to, name in (("bounty", "the issue's bounty (the owner's decision)"), ("pool", "the sponsors' pool")):
                rows.append((pre + f"bad-fix solver that tries each issue up to {times} times, deposit 2,500 to {name}",
                             lambda h, w=w, n=n: Solver(h, w, retry=n), replace(BASE, SOLVER_DEPOSIT_TO=to),
                             "solver"))
        for to, name in (("bounty", "the issue's bounty"), ("pool", "the sponsors' pool")):  # added after the first run
            rows.append((pre + f"bad-fix solver that tries each issue up to 21 times, deposit 4,000 to {name} "
                         "(post hoc)", lambda h, w=w: Solver(h, w, retry=20),
                         replace(BASE, SOLVER_DEPOSIT_BPS=4_000, SOLVER_DEPOSIT_TO=to), "solver"))
        for bps, note in ((0, ""), (2_500, ""), (4_000, " (post hoc)")):
            rows.append((pre + f"report v3's judged spammer (a bad fix a day, three validators of its own, four "
                         f"families, the market with entry), `SOLVER_DEPOSIT_BPS` {bps:,}{note}",
                         _on_measured(lambda h: PR.Spammer(h, kind="judged"), pool),
                         replace(BASE, SOLVER_DEPOSIT_BPS=bps), "spam"))
    return rows


def appeal_attack_rows() -> List[AttRow]:
    """The solver that appeals every rejection, against the same solver that never appeals."""
    rows: List[AttRow] = []
    for pool, what in POOLS:
        pre = _pre(what)
        for find, lab in ((FIND, ""), (0.0, ", no disputes")):
            w = world(pool, find, FALSE if find else 0.0)
            for name, kw in APPEALS[1:]:
                if not find and kw["APPEAL"] != "others":
                    continue
                rows.append((pre + f"appeals everything; panel: {name}{lab}",
                             lambda h, w=w: Solver(h, w, appeal=True, twin="no_appeal"), replace(D236, **kw),
                             "appeal"))
        w = world(pool)
        rows.append((pre + "appeals everything; panel: other families, contenders included; majority; no deposit",
                     lambda h, w=w: Solver(h, w, appeal=True, twin="no_appeal"),
                     replace(D236, SOLVER_DEPOSIT_BPS=0), "appeal"))
    return rows


STAKE5 = replace(BASE, EVIDENCE_STAKE_BPS=500)


def disputer_rows() -> List[AttRow]:
    rows: List[AttRow] = []
    s10 = replace(BASE, EVIDENCE_STAKE_BPS=1_000)
    for pool, what in POOLS:
        pre = _pre(what)
        w, w20 = world(pool), world(pool, FIND, 0.20)
        wrong = lambda w, sel: (lambda h: Disputer(h, w, "wrong", sel))  # noqa: E731
        rows += [
            (pre + "tests that pass on the fixed code, on every pass; stake $5",
             lambda h, w=w: Disputer(h, w, "passing"), BASE, "dispute"),
            (pre + "wrong tests on every pass; stake $5", wrong(w, False), BASE, "dispute"),
            (pre + "wrong tests where it expects to gain; stake $5", wrong(w, True), BASE, "dispute"),
            (pre + "wrong tests where it expects to gain; stake $5; a wrong test accepted 1 time in 5",
             wrong(w20, True), BASE, "dispute"),
            (pre + "wrong tests where it expects to gain; stake the larger of $5 and 5 % of the bounty",
             wrong(w, True), STAKE5, "dispute"),
            (pre + "wrong tests where it expects to gain; stake the larger of $5 and 5 %; accepted 1 time in 5",
             wrong(w20, True), STAKE5, "dispute"),
            (pre + "wrong tests where it expects to gain; stake the larger of $5 and 10 %; accepted 1 time in 5",
             wrong(w20, True), s10, "dispute"),
            (pre + "wrong tests on every pass; stake the larger of $5 and 10 %; accepted 1 time in 5",
             wrong(w20, False), s10, "dispute"),
        ]
        for seat in ("openai", "anthropic", "deepseek"):
            rows.append((pre + f"an honest contender running {M.NAMES[seat]}, ${SEARCH_COST:.2f} a search; stake $5",
                         lambda h, w=w, seat=seat: Disputer(h, w, "contender", seat=seat), BASE, "contend"))
        for bps in (0, 2_500):  # added after the first run: what the reward's share changes for a contender
            rows.append((pre + f"an honest contender running GPT-6.1, `EVIDENCE_REWARD_BPS` {bps:,} (post hoc)",
                         lambda h, w=w: Disputer(h, w, "contender", seat="openai"),
                         replace(BASE, EVIDENCE_REWARD_BPS=bps), "contend"))
    return rows


ATTACKS: Dict[str, Callable[[], List[AttRow]]] = {"deposit_attack": deposit_attack_rows,
                                                  "appeal_attack": appeal_attack_rows, "disputer": disputer_rows}


def _party_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    pa = net.parties.get(a.party)
    get = lambda k: getattr(pa, k) if pa else 0  # noqa: E731
    mine = [s for s in net.subs.values() if s.party == a.party and s.tier == ISSUE]
    return {"submitted": get("submitted"), "bad_paid": get("bad_paid"), "appeals": get("appeals"),
            "upheld": sum(1 for s in mine if s.appeal == "upheld"),
            "appeal_paid": sum(1 for s in mine if s.appeal == "upheld" and s.final),
            "lost": get("sdeposits_lost"), "tests": get("tests"), "tests_upheld": get("tests_upheld"),
            "searches": net.stats["disputer_searches"], "wrong": net.stats["evidence_wrong"],
            "spam": net.stats["spam"], "waited": 100 * net.stats["waited"] / max(1, net.stats["submitted"])}


def _run_attack(job) -> Dict[str, object]:
    table, i, seed = job
    _, make, p, _ = ATTACKS[table]()[i]
    return A.against_twin(make, [seed], p=p, metrics=_party_metrics)


def run_attacks(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = ATTACKS[table]()
    res = C._map(_run_attack, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    return [(rows[i][0], C._twin(res[i * len(seeds):(i + 1) * len(seeds)]), rows[i][3]) for i in range(len(rows))]


def _got(kind: str, r: Dict[str, object]) -> str:
    n = max(1.0, r["submitted"])
    if kind == "solver":
        return (f"{r['bad_paid']:.0f} bad fixes paid of {r['submitted']:.0f} submitted "
                f"({100 * r['bad_paid'] / n:.0f} %); ${r['attacker'] / n:+,.2f} a fix submitted; "
                f"${r['lost']:,.0f} of deposits lost")
    if kind == "appeal":
        return (f"{r['appeals']:.0f} appeals, {r['upheld']:.0f} upheld, {r['appeal_paid']:.0f} of them paid; "
                f"{r['bad_paid']:.0f} bad fixes paid of {r['submitted']:.0f} (twin: {r['twin_bad_paid']:.0f}); "
                f"${r['diff'] / max(1.0, r['appeals']):+,.2f} an appeal")
    if kind == "spam":
        return (f"{r['spam']:.0f} bad fixes submitted, {r['bad_paid']:.0f} paid; ${r['lost']:,.0f} of deposits lost; "
                f"{r['waited']:.0f} % of all submissions waited")
    if kind == "contend":
        return (f"{r['searches']:.0f} fixes searched, {r['tests_upheld']:.0f} tests upheld; "
                f"${r['attacker'] / max(1.0, r['tests_upheld']):,.0f} a reversal")
    return (f"{r['tests']:.0f} tests posted, {r['tests_upheld']:.0f} upheld; good fixes reversed by a wrong test, "
            f"whoever posted it: {r['wrong']:.0f} (twin's run: {r['twin_wrong']:.0f})")


def attack_table(data) -> str:
    head = ["Attacker", "Return − twin's ($ a year, ± 2 SE)", "Against its twin", "Attacker's return", "Twin's return",
            "What it got"]
    return _table(head, [[name, f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}", R._verdict(r["diff"], r["se"]),
                          f"{r['attacker']:,.0f}", f"{r['twin']:,.0f}", _got(kind, r)] for name, r, kind in data])


# ---------- exact counts: an appeal panel on #160's verdicts ----------

def appeal_exact(pool: str, seated: Sequence[str], others: Sequence[str], k: int = 5, cap: int = 2,
                 unanimous: bool = False) -> Dict[str, float]:
    """No simulation: of the fixes a panel of `seated` (majority, one vote a family) rejects, the share an appeal
    panel of `k` passes, averaged over every panel that takes at most `cap` judges of a family from `others`."""
    from itertools import combinations_with_replacement
    t = M.table()
    panels = [c for c in combinations_with_replacement(sorted(others), k) if max(c.count(f) for f in c) <= cap]
    need = k if unanimous else (k + 1) // 2
    first = lambda c: 2 * sum(c[s] for s in seated) > len(seated)  # noqa: E731

    def share(cases) -> Tuple[int, float]:
        rej = [c for c in cases if not first(c)]
        if not rej or not panels:
            return len(rej), float("nan")
        return len(rej), mean(mean(sum(c[s] for s in pn) >= need for pn in panels) for c in rej)
    nb, ob = share(t[pool])
    ng, og = share(t["good"])
    return {"bad_rejected": nb, "bad_overturned": ob, "good_rejected": ng, "good_restored": og}


def appeal_exact_table() -> str:
    seven = [s for _, s in M.SEVEN]
    head = ["Bad fixes", "Seated panel", "Appeal panel of 5 drawn from", "Rule", "Bad fixes rejected",
            "…of which the appeal passes", "Good fixes rejected", "…of which the appeal passes"]
    lines = []
    for pool, what in POOLS:
        sets = ((("anthropic",), "Opus 5.5"), (("openai",), "GPT-6.1")) if pool == "hidden" else (
            (("anthropic", "openai", "google"), "Opus, GPT-6.1, Gemini (majority)"), (("anthropic",), "Opus 5.5"))
        for seated, sname in sets:
            rest = [s for s in seven if s not in seated]
            for others, oname in ((rest, "the other families of the seven"),
                                  ([s for s in rest if s in ("anthropic", "openai", "google")],
                                   "the other frontier families only")):
                if not others:
                    continue
                cap = 2 if len(others) >= 3 else 5
                for una in (False, True):
                    x = appeal_exact(pool, seated, others, cap=cap, unanimous=una)
                    lines.append([what, sname, oname, "every judge must pass" if una else "majority",
                                  f"{x['bad_rejected']}", f"{100 * x['bad_overturned']:.0f} %",
                                  f"{x['good_rejected']}", f"{100 * x['good_restored']:.0f} %"])
    return _table(head, lines)


TITLES = {
    "seats": "Seats by rank, on known answers: `SEAT_MARGIN` and `CAP_MIN_FAMILIES`",
    "live": "Seats by rank, on live scores (D23)",
    "deposit": "The solver's deposit: what it costs honest solvers",
    "deposit_attack": "The solver's deposit: what a solver of bad fixes earns",
    "appeal": "The appeal: its panel",
    "appeal_attack": "The solver that appeals every rejection, against the same solver that never appeals",
    "disputer": "The disputer without evidence (its twin posts nothing), and an honest contender",
    "new": "A new family's start (live scores)",
    "final": "v3 as designed beside the proposal",
}
ORDER = ("seats", "live", "deposit", "deposit_attack", "appeal", "exact", "appeal_attack", "disputer", "new", "final")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.sizing")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--quick", action="store_true", help="4 seeds")
    ap.add_argument("--only", default="", help="comma-separated tables: " + ", ".join(ORDER))
    a = ap.parse_args(argv)
    seeds = list(range(1, (4 if a.quick else a.seeds) + 1))
    only = [x for x in a.only.split(",") if x] or list(ORDER)
    print(f"Seeds 1-{seeds[-1]}; every ± is two standard errors of the mean.\n")
    for name in only:
        if name == "exact":
            print("### An appeal panel on #160's verdicts (exact, no simulation)\n")
            print(appeal_exact_table() + "\n")
            continue
        print(f"### {TITLES[name]}\n")
        if name in ATTACKS:
            print(attack_table(run_attacks(name, seeds, a.jobs)) + "\n")
        elif name == "new":
            print(new_family_table(run_table(name, seeds, a.jobs)) + "\n")
        else:
            print(honest_table(run_table(name, seeds, a.jobs), seats=name in ("seats", "live", "final"),
                               appeal=name in ("appeal", "final")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
