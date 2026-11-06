"""Per-family model scores (#132 design D14, specs/judge-scores; #134 task 1.7).

- The score: a model family's agreement with final outcomes over its last `SCORE_WINDOW` verdicts. A counted
  verdict agrees when its vote equals the final outcome: the verdict after its window, or the upheld challenge's
  verdict when one reversed it (`Net.family_outcomes`, recorded at finality). While a family is barred, its active
  validators' shadow verdicts are scored the same way (`Net.family_shadow_outcomes`), so it can recover.
- Eligibility: a family below `SCORE_MIN` over at least `SCORE_MIN_VERDICTS` isn't drawn for counted panels
  (`Net(family_ok=...)`); its validators shadow-judge until the score is back.
- The neutral start: fewer than `SCORE_MIN_VERDICTS` verdicts is the neutral score, drawn normally and paid the
  unscaled fee. The neutral score is the one whose factor is 1 (`NEUTRAL`, 80 % at the starting values).
- Pay: a counted judge's service fee is the market fee (whatever `Net.fee` is: phase 1's flat fee or task 1.4's
  market) times its family's factor, linear from `SCORE_FACTOR_MIN` at `SCORE_MIN` to `SCORE_FACTOR_MAX` at 100 %.
  `ScoredFee` wraps the fee object rather than replacing it. Metered usage is passed through at cost either way.
- Votes stay one per judge. The rejected alternative, votes weighted by score (`Net(vote_weight=...)`), is here only
  to compare against (`install(net, weighted=...)`).
- #141's rules (each a `Params` field; `params.V1` restores #134's above): the score counts counted verdicts only
  (`SCORE_COUNTED_ONLY`); a barred family recovers by its shadow verdicts alone (round 2, `SCORE_RECOVERY` "blocks":
  a fresh block of SCORE_RECOVER_VERDICTS (100), each judged once, at SCORE_MIN + SCORE_RECOVER_MARGIN (80 %); round
  1, "sliding": its last 50 at SCORE_MIN, at each check), its counted window then restarts and it is paid
  SCORE_FACTOR_MIN until it has SCORE_MIN_VERDICTS new counted verdicts; the factor is normalised each pricing period by its mean over the previous period's counted
  seats (`SCORE_FACTOR_RULE` "normalised"; "median" puts the factor's 1 x at the median family score); `SCORE_BALANCED`
  scores the mean of a family's agreement on passed and on failed outcomes; a family change is a new registration
  (`MOVE_REREGISTERS`).

The behaviours task 1.7 adds, each against its honest twin (`actors.against_twin`): `Movers` (validators switching to
the family that pays most per head) and `Herders` (judges voting the expected majority instead of their finding).
`SCORE_WORLD` is the assumption the tables run on: four families of different true accuracies, each with a blind
spot. `python3 -m pof.sim.openval scores --seeds N` prints the tables of reports/open-validators-v1.md, "Model scores".
"""

from __future__ import annotations

import heapq
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from statistics import mean, median
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from . import actors as A
from . import panels as D
from .net import ACTOR_VID, COUNTED, ISSUE, SHADOW, Act, Honest, Net, Sub
from .params import MONTH, PARAMS, WORLD, Params, World
from .registry import Validator

T_MOVE = 0x5C0E  # randomness tag of a mover's monthly reconsideration
MOVER_VID = 3_000_000  # #141: the new keys of honest validators that change family (a separate id range)

# The world the score tables run on (assumptions, named in the report): four model families whose judges' verdicts
# match the truth with different accuracies (independently per judge), plus a blind spot per family: 5 % of bad fixes
# fool every judge of that family at once (a prompt injection that works on that model). A grown network of 16
# validators (four per family) with newcomers at half a validator a week, each family equally likely.
FAMILIES = ("top", "mid", "low", "weak")
SCORE_WORLD = replace(WORLD, families=FAMILIES, initial_active=16, joins_week=0.5,
                      family_accuracy=(("top", 0.95), ("mid", 0.90), ("low", 0.85), ("weak", 0.68)),
                      family_blind=tuple((f, 0.05) for f in FAMILIES))
NO_BLIND = replace(SCORE_WORLD, family_blind=())


# ---------- the rule (what the contract computes) ----------

def neutral(p: Params = PARAMS) -> float:
    """The neutral score: the one whose factor is 1 (80 % at the starting values)."""
    return p.SCORE_MIN + (1.0 - p.SCORE_FACTOR_MIN) / (p.SCORE_FACTOR_MAX - p.SCORE_FACTOR_MIN) * (1.0 - p.SCORE_MIN)


def agreement(entries: Sequence[tuple], p: Params = PARAMS) -> float:
    """The share of `entries` (finality time, agreed[, outcome]) that agreed; with SCORE_BALANCED, the mean of the
    shares on passed and on failed outcomes (an always-pass judge scores 50 %)."""
    if p.SCORE_BALANCED:
        parts = [[e[1] for e in entries if bool(e[2]) is side] for side in (True, False)]
        shares = [sum(x) / len(x) for x in parts if x]
        return sum(shares) / len(shares)
    return sum(1 for e in entries if e[1]) / len(entries)


def recompute(counted: Sequence[tuple], shadows: Sequence[tuple] = (),
              p: Params = PARAMS) -> Tuple[Optional[float], int]:
    """(score, verdicts in the window) from a family's recorded verdicts, each (finality time, agreed, outcome),
    counted and shadow merged in time order (counted first on a tie; #141 passes no shadows): the share that agreed
    among the last SCORE_WINDOW. Anyone can run it on the chain's records (specs/judge-scores, "Recomputing a score").
    None with no verdicts."""
    w = p.SCORE_WINDOW
    last = list(heapq.merge(counted[-w:], shadows[-w:], key=lambda e: e[0]))[-w:]
    if not last:
        return None, 0
    return agreement(last, p), len(last)


def factor(score: Optional[float], n: int, p: Params = PARAMS) -> float:
    """The raw factor: 1 below SCORE_MIN_VERDICTS (the neutral start); else linear from SCORE_FACTOR_MIN at SCORE_MIN
    to SCORE_FACTOR_MAX at 100 %, within those bounds (#134's whole rule; #141 normalises it, `Scores.factor`)."""
    if score is None or n < p.SCORE_MIN_VERDICTS:
        return 1.0
    x = p.SCORE_FACTOR_MIN + (score - p.SCORE_MIN) / (1.0 - p.SCORE_MIN) * (p.SCORE_FACTOR_MAX - p.SCORE_FACTOR_MIN)
    return min(p.SCORE_FACTOR_MAX, max(p.SCORE_FACTOR_MIN, x))


def bounded(x: float, p: Params = PARAMS) -> float:
    return min(p.SCORE_FACTOR_MAX, max(p.SCORE_FACTOR_MIN, x))


@dataclass
class FamilyState:
    """#141's per-family state: barred or not, where its counted window starts (an index into its counted records,
    moved at each recovery), where its shadow record starts counting toward recovery, and whether it is recovering
    (paid SCORE_FACTOR_MIN until it has SCORE_MIN_VERDICTS new counted verdicts)."""
    barred: bool = False
    start: int = 0
    shadow_start: int = 0
    recovering: bool = False
    bars: int = 0
    recoveries: int = 0
    blocks: int = 0  # round 2: recovery blocks judged (each once)


def eligible(score: Optional[float], n: int, p: Params = PARAMS) -> bool:
    """Drawn for counted panels: fewer than SCORE_MIN_VERDICTS (neutral), or a score at least SCORE_MIN."""
    return score is None or n < p.SCORE_MIN_VERDICTS or score >= p.SCORE_MIN - 1e-12


class Scores:
    """The contract's per-family scores in a running `Net`, read from its records (cached until a record changes).
    #134 (`SCORE_COUNTED_ONLY` off): one window of counted and barred-shadow verdicts, eligible at SCORE_MIN, the raw
    factor. #141: counted verdicts only, barring and recovery as a state per family (`FamilyState`), the normalised
    (or median-neutral) factor."""

    def __init__(self, net: Net):
        self.net, self.p = net, net.p
        self._cache: Dict[str, Tuple[Tuple[int, int, int, int], Tuple[Optional[float], int]]] = {}
        self.barred_days: Counter = Counter()  # days each family spent barred (sampled at each tick)
        self.fam: Dict[str, FamilyState] = defaultdict(FamilyState)
        self.norm = 1.0  # the mean raw factor over the previous period's counted seats
        self.seats: List[float] = []  # this period's counted seats' raw factors (scored families)

    def state(self, family: str) -> Tuple[Optional[float], int]:
        c = self.net.family_outcomes.get(family, ())
        s = self.net.family_shadow_outcomes.get(family, ())
        key = (id(c), len(c), id(s), len(s))  # records only grow; a replaced list is a new one
        hit = self._cache.get(family)
        if hit is None or hit[0] != key:
            hit = (key, recompute(c, s, self.p) if not self.p.SCORE_COUNTED_ONLY else self._update(family, c, s))
            self._cache[family] = hit
        return hit[1]

    def _update(self, family: str, c: Sequence[tuple], s: Sequence[tuple]) -> Tuple[Optional[float], int]:
        """#141: the counted score since the window's last restart, and the state's moves: barred below SCORE_MIN over
        SCORE_MIN_VERDICTS counted verdicts; recovered when its last SCORE_MIN_VERDICTS shadow verdicts since then
        agree at SCORE_MIN or above (the counted window restarts); recovering until SCORE_MIN_VERDICTS new ones."""
        p, st = self.p, self.fam[family]
        score, n = recompute(c[st.start:], (), p)
        if st.barred:
            if self._recovers(st, s):
                st.barred, st.recovering, st.start = False, True, len(c)
                st.recoveries += 1
                score, n = None, 0
        elif score is not None and n >= p.SCORE_MIN_VERDICTS and score < p.SCORE_MIN - 1e-12:
            st.barred, st.shadow_start, st.recovering = True, len(s), False
            st.bars += 1
        if st.recovering and n >= p.SCORE_MIN_VERDICTS:
            st.recovering = False
        return score, n

    def _recovers(self, st: FamilyState, s: Sequence[tuple]) -> bool:
        """D14's recovery test on a barred family's shadow verdicts since its barring. Round 2 ("blocks"): consecutive
        fresh blocks of SCORE_RECOVER_VERDICTS, each judged once when complete, at SCORE_MIN + SCORE_RECOVER_MARGIN.
        Round 1 ("sliding"): its last SCORE_RECOVER_VERDICTS at each check, at SCORE_MIN + the margin (0)."""
        p = self.p
        n, bar = p.SCORE_RECOVER_VERDICTS, p.SCORE_MIN + p.SCORE_RECOVER_MARGIN - 1e-12
        if p.SCORE_RECOVERY == "sliding":
            sh = s[st.shadow_start:]
            return len(sh) >= n and agreement(sh[-n:], p) >= bar
        while len(s) - st.shadow_start >= n:
            block = s[st.shadow_start:st.shadow_start + n]
            st.shadow_start += n
            st.blocks += 1
            if agreement(block, p) >= bar:
                return True
        return False

    def score(self, family: str) -> float:
        """The score, or the neutral one while the family has fewer than SCORE_MIN_VERDICTS."""
        s, n = self.state(family)
        return neutral(self.p) if s is None or n < self.p.SCORE_MIN_VERDICTS else s

    def ok(self, family: str) -> bool:
        if not self.p.SCORE_COUNTED_ONLY:
            return eligible(*self.state(family), self.p)
        self.state(family)
        return not self.fam[family].barred

    def scored(self, family: str) -> bool:
        """It has SCORE_MIN_VERDICTS counted verdicts in its window and isn't recovering: its factor follows its score."""
        s, n = self.state(family)
        return s is not None and n >= self.p.SCORE_MIN_VERDICTS and not self.fam[family].recovering

    def raw(self, family: str) -> float:
        return factor(*self.state(family), self.p)

    def factor(self, family: str) -> float:
        p = self.p
        if p.SCORE_FACTOR_RULE == "linear":
            return factor(*self.state(family), p)
        if self.p.SCORE_COUNTED_ONLY and (self.state(family) and self.fam[family].recovering):
            return p.SCORE_FACTOR_MIN
        if not self.scored(family):
            return 1.0  # a new family: the neutral factor
        if p.SCORE_FACTOR_RULE == "median":
            fams = {v.family for v in self.net.reg.validators.values()}
            mid = median(self.state(f)[0] for f in fams if self.scored(f))
            slope = (p.SCORE_FACTOR_MAX - p.SCORE_FACTOR_MIN) / (1.0 - p.SCORE_MIN)
            return bounded(1.0 + (self.state(family)[0] - mid) * slope, p)
        return bounded(self.raw(family) / self.norm, p)

    def seat(self, family: str) -> None:
        """A counted seat of `family` paid this period (what the next period's normalisation reads)."""
        if self.scored(family):
            self.seats.append(self.raw(family))

    def end_period(self) -> None:
        if self.seats:
            self.norm = mean(self.seats)
        self.seats = []

    def weight_factor(self, v: Validator) -> float:
        return self.factor(v.family)

    def weight_score(self, v: Validator) -> float:
        return self.score(v.family)


class ScoredFee:
    """The market fee (any fee object with `fee` and `end_period`) times the counted judge's family factor. Audits
    and challenge panels are paid the market fee unscaled (the spec scales "a counted judge's service fee")."""

    def __init__(self, inner: object, scores: Scores):
        self.inner, self.scores = inner, scores

    def fee(self, net: Net, sub: Sub, v: Validator) -> float:
        base = self.inner.fee(net, sub, v)
        if sub.draw is not None and v.vid in sub.draw.drawn:  # seated on the counted panel (replacements included)
            seat = getattr(self.scores, "seat", None)
            if seat is not None:
                seat(v.family)
            # only the service fee is scaled: a market fee (pricing.Market) also returns the usage margin, which
            # `service_part` leaves out; the flat fee is all service fee
            part = getattr(self.inner, "service_part", None)
            if part is None:
                return base * self.scores.factor(v.family)
            return base + (self.scores.factor(v.family) - 1.0) * part(sub)
        return base

    def end_period(self, net: Net, period: Counter) -> None:
        self.inner.end_period(net, period)
        self.scores.end_period()
        for f in {v.family for v in net.reg.validators.values()}:
            self.scores.barred_days[f] += not self.scores.ok(f)

    def __getattr__(self, name: str):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)


def install(net: Net, weighted: Optional[str] = None) -> Scores:
    """Switch D14 on in a network built but not yet run (or from an actor's `setup`): eligibility by SCORE_MIN and
    pay by score; `weighted` = "factor" or "score" also weights each vote by its family's factor or score (the
    rejected alternative)."""
    sc = Scores(net)
    net.scores = sc
    net.family_ok = sc.ok
    net.fee = ScoredFee(net.fee, sc)
    if weighted == "factor":
        net.vote_weight = sc.weight_factor
    elif weighted == "score":
        net.vote_weight = sc.weight_score
    elif weighted is not None:
        raise ValueError(weighted)
    return sc


# ---------- behaviours and actors ----------

def expected_majority(net: Net) -> bool:
    """What a herder expects a panel to decide without judging: the public base rate (the share of final verdicts
    that passed so far; the world's share of good fixes before any)."""
    st = net.stats
    rate = st["paid"] / st["final"] if st["final"] else net.w.good_share
    return rate >= 0.5


class Herder(Honest):
    """A counted judge that votes the expected majority instead of its finding. It runs the check (it must reveal a
    receipt), so when its vote differs from its finding it signs a verdict its check didn't produce: `detectable`
    (a re-run shows the receipt doesn't reproduce, as any false verdict), or not (an upper bound: a herder that can
    steer its own model call). It judges honestly as a shadow, an auditor and a challenge judge."""

    def __init__(self, detectable: bool = True):
        self.detectable = detectable

    def counted(self, net: Net, sub: Sub, v: Validator) -> Act:
        if not net.online(sub, v, COUNTED):
            return Act(False, False)
        found = net.honest_vote(sub, v, COUNTED)
        guess = expected_majority(net) if sub.tier == ISSUE else found
        net.stats["herded"] += guess != found
        return Act(True, True, guess, faked=self.detectable and guess != found)

    def shadow(self, net: Net, sub: Sub, v: Validator) -> Act:
        """Herds as a shadow too (a shadow verdict is never re-run): to qualify, or to lift a barred family."""
        if not net.online(sub, v, SHADOW):
            return Act(False, False)
        return Act(True, True, expected_majority(net))


class ScoreActor(A.Actor):
    """An actor in SCORE_WORLD with D14 switched on (`weighted`: the alternative), `honest_nodes` honest validators."""

    def __init__(self, honest: bool = False, honest_nodes: int = 16, weighted: Optional[str] = None,
                 w: World = SCORE_WORLD):
        super().__init__(honest)
        self.honest_nodes, self.weighted, self.w = honest_nodes, weighted, w

    def world(self) -> World:
        return replace(self.w, initial_active=self.honest_nodes)

    def setup(self, net: Net) -> None:
        install(net, self.weighted)


class Herders(ScoreActor):
    """`nodes` validators of one `family` (already qualified, bonded at `bond`, on distinct hosts and TEE types)
    that herd on every counted draw. Its twin: the same validators judging honestly."""
    name = "herders"
    party = "herders"

    def __init__(self, honest: bool = False, nodes: int = 4, family: str = "mid", detectable: bool = True,
                 bond: float = 1250.0, **kw):
        super().__init__(honest, **kw)
        self.n, self.family, self.detectable, self.bond = nodes, family, detectable, bond

    def setup(self, net: Net) -> None:
        super().setup(net)
        w = net.w
        for i in range(self.n):
            net.register_actor(i, self.party, self.bond, w.hosts[(i + 2) % len(w.hosts)], w.tees[i % len(w.tees)],
                               self.family, f"herder-op-{i}", self.behaviour(Herder(self.detectable)), active=True)


class Movers(ScoreActor):
    """Validators that switch to the model family paying its validators the most per head (service fees over the
    last month), whenever it beats their own by `margin`; each reconsiders once a month with probability `pace`. A
    switch takes effect at once, without re-qualifying (the worst case for concentration), and the validator then
    judges with the new family's accuracy; a validator seated on a panel still waiting for a replacement switches
    after it (the panel's caps were checked on the families it was drawn with). `everyone=True`: every validator moves (the market scenario), and the twin
    is the same network where nobody does; else `nodes` validators of the party, starting in `family`, and the twin
    is the same validators staying put."""
    name = "movers"
    party = "movers"

    def __init__(self, honest: bool = False, everyone: bool = False, nodes: int = 4, family: str = "low",
                 margin: float = 0.10, pace: float = 0.5, bond: float = 1250.0, **kw):
        super().__init__(honest, **kw)
        self.everyone, self.n, self.family, self.margin, self.pace = everyone, nodes, family, margin, pace
        self.bond = bond
        self.shares: List[Dict[str, float]] = []  # each month: the families' shares of drawable validators

    def setup(self, net: Net) -> None:
        super().setup(net)
        w = net.w
        if not self.everyone:
            for i in range(self.n):
                net.register_actor(i, self.party, self.bond, w.hosts[(i + 3) % len(w.hosts)],
                                   w.tees[(i + 1) % len(w.tees)], self.family, f"mover-op-{i}", None, active=True)
        self._fees: Dict[int, float] = {}
        self._month = 0
        self.families_at_draw: Dict[int, Tuple[str, ...]] = {}  # each panel's judges' families when judged

    def pay(self, net: Net) -> Dict[str, float]:
        """Each family's service fees per drawable validator over the last month (and remember this month's)."""
        tot: Dict[str, float] = defaultdict(float)
        cnt: Counter = Counter()
        for v in net.reg.validators.values():
            if net.reg.drawable(v):
                tot[v.family] += v.acct.fees - self._fees.get(v.vid, 0.0)
                cnt[v.family] += 1
            self._fees[v.vid] = v.acct.fees
        return {f: tot[f] / cnt[f] for f in cnt}

    def on_tick(self, net: Net) -> None:
        rec = self.families_at_draw  # before anyone switches: switches happen only here, at a tick
        for s in net.subs.values():
            if s.judges and s.sid not in rec:
                rec[s.sid] = tuple(net.reg.validators[vid].family for vid, _, _ in s.judges)
        if net.t < (self._month + 1) * MONTH:
            return
        self._month += 1
        pay = self.pay(net)
        drawable = [v for v in net.reg.validators.values() if net.reg.drawable(v)]
        n = max(1, len(drawable))
        self.shares.append({f: sum(1 for v in drawable if v.family == f) / n for f in net.w.families})
        if self.honest or not pay:
            return
        best = max(sorted(pay), key=lambda f: pay[f])
        busy = {v.vid for panel in net.stalled for v in panel.seated}  # mid-check: it switches after the panel
        movers = [v for v in (drawable if self.everyone else [v for v in drawable if v.party == self.party])
                  if v.vid not in busy]
        for v in movers:
            if (v.family != best and pay[best] > (1 + self.margin) * pay.get(v.family, 0.0)
                    and D.u(net.seed, T_MOVE, v.vid, self._month) < self.pace):
                if net.p.MOVE_REREGISTERS:
                    self.reregister(net, v, best)
                else:
                    v.family = best
                    net.reg.epoch += 1
                net.stats["moves"] += 1

    def reregister(self, net: Net, v: Validator, family: str) -> Validator:
        """#141 (gap 17): a family change is a new registration. The old key leaves (its bond unbonds after the
        delay); a new key, same operator, host, TEE type and bond, registers with the new family as a candidate and
        must qualify as a shadow judge before it is drawn for counted panels."""
        self._renew = getattr(self, "_renew", 0) + 1
        vid = (ACTOR_VID + 500 + self._renew) if v.party == self.party else (MOVER_VID + self._renew)
        net.leave(v)
        net.stats["reregistered"] += 1
        return net.reg.register(net.t, key=f"{v.key}>{family}-{self._renew}", signer=f"{v.key}>{family}-{self._renew}",
                                bond=max(v.target, net.p.BOND_FLOOR), proof=v.proof, host=v.host, family=family,
                                operator=v.operator, cloud_attested=v.level == "A", party=v.party,
                                behaviour=v.behaviour, vid=vid)


# ---------- what the tables read ----------

def panel_families(net: Net, sub: Sub, at_draw: Optional[Dict[int, Tuple[str, ...]]] = None) -> Tuple[str, ...]:
    """The families of a panel's judges (as recorded when judged, when validators may switch families)."""
    if at_draw is not None and sub.sid in at_draw:
        return at_draw[sub.sid]
    return tuple(net.reg.validators[vid].family for vid, _, _ in sub.judges)


def decided_by_one_family(net: Net, sub: Sub, at_draw: Optional[Dict[int, Tuple[str, ...]]] = None) -> bool:
    """A panel of k >= 3 whose verdict went against a strict majority of the judges outside one family: that family
    overrode the rest."""
    fam = list(zip(panel_families(net, sub, at_draw), (vote for _, vote, _ in sub.judges)))
    for f in {x for x, _ in fam}:
        others = [vote for x, vote in fam if x != f]
        yes = sum(others)
        if others and 2 * yes != len(others) and (2 * yes > len(others)) != sub.verdict:
            return True
    return False


def one_vote(sub: Sub) -> bool:
    return 2 * sum(1 for _, vote, _ in sub.judges if vote) > len(sub.judges)


def market_metrics(net: Net, at_draw: Optional[Dict[int, Tuple[str, ...]]] = None) -> Dict[str, float]:
    st = net.stats
    panels = [s for s in net.subs.values() if s.tier == ISSUE and s.judges and s.k >= 3 and s.verdict is not None]
    good = [s for s in net.subs.values() if s.tier == ISSUE and s.final is not None and s.good]
    fees = sum(v.acct.fees for v in net.reg.validators.values())
    out = {"bad_per_100": 100 * st["bad_merged"] / max(1, st["paid"]), "bad": st["bad_merged"],
           "good_failed_pct": 100 * sum(1 for s in good if not s.final) / max(1, len(good)),
           "one_family": sum(1 for s in panels if decided_by_one_family(net, s, at_draw)) / max(1, len(panels)),
           "flipped": sum(1 for s in panels if s.verdict != one_vote(s)) / max(1, len(panels)),
           "fee_per_check": fees / max(1, st["drawn"]), "reversed": st["reversed"],
           "stepped_down": st["stepped_down"] / max(1, st["drawn"]), "waited": st["waited"] / max(1, st["submitted"])}
    for f in net.w.families:
        vals = [net.validator_net(v) / max(1e-9, (net.t - v.registered_at) / MONTH)
                for v in net.reg.validators.values() if v.family == f and v.active_at is not None and not v.party
                .startswith(("herders", "movers"))]
        out[f"net_{f}"] = mean(vals) if vals else float("nan")
        sc = getattr(net, "scores", None)
        if sc is not None:
            s, n = sc.state(f)
            out[f"score_{f}"] = s if s is not None else float("nan")
            out[f"barred_{f}"] = sc.barred_days[f] / max(1.0, net.t / 24.0)
    return out


def run_mode(seed: int, mode: Optional[str], w: World = SCORE_WORLD, p: Params = PARAMS) -> Net:
    """One network: mode None (one vote, flat pay: phase 1), "pay" (v3's design: eligibility and pay by score), or
    "factor" / "score" (the alternative: votes weighted by the family's factor or score)."""
    net = Net(seed, p, w)
    if mode is not None:
        install(net, None if mode == "pay" else mode)
    return net.run()


MODES: Tuple[Tuple[str, Optional[str]], ...] = (
    ("One vote, flat pay (phase 1, no scores)", None),
    ("**One vote, pay by score (v3's design)**", "pay"),
    ("Votes weighted by the score factor (0.5–2×)", "factor"),
    ("Votes weighted by the raw score", "score"),
)


def _avg(rows: List[Dict[str, float]]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        for k, v in r.items():
            if v == v:  # skip NaN (a family with no validator in a run)
                out[k].append(v)
    return out


def _ms(xs: Sequence[float], nd: int = 1, scale: float = 1.0) -> str:
    xs = [x for x in xs if x == x]  # NaN: nothing to measure in that run
    if not xs:
        return "–"
    return f"{scale * mean(xs):,.{nd}f} ± {2 * scale * A._se(xs):,.{nd}f}"


def compare(seeds: Sequence[int], w: World = SCORE_WORLD) -> List[Tuple[str, Dict[str, List[float]]]]:
    return [(name, _avg([market_metrics(run_mode(s, mode, w)) for s in seeds])) for name, mode in MODES]


def compare_table(seeds: Sequence[int], w: World = SCORE_WORLD, title: str = "") -> str:
    fams = w.families
    out = [f"### One vote, pay by score, weighted votes ({len(seeds)} seeds; a year{title})", "",
           "| Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | "
           "Verdicts the weights flipped (%) | Service fees per submission ($) | "
           + " | ".join(f"`{f}` validator's net per month ($)" for f in fams) + " |",
           "|---" * (6 + len(fams)) + "|"]
    for name, m in compare(seeds, w):
        out.append(f"| {name} | {_ms(m['bad_per_100'], 2)} | {_ms(m['good_failed_pct'], 2)} | "
                   f"{_ms(m['one_family'], 2, 100)} | {_ms(m['flipped'], 2, 100)} | {_ms(m['fee_per_check'], 3)} | "
                   + " | ".join(_ms(m[f'net_{f}'], 2) for f in fams) + " |")
    return "\n".join(out)


def scores_table(seeds: Sequence[int], w: World = SCORE_WORLD) -> str:
    """The families' scores and factors at the year's end, and how long each was barred, under v3's design."""
    rows = _avg([market_metrics(run_mode(s, "pay", w)) for s in seeds])
    out = [f"### The families' scores under v3's design ({len(seeds)} seeds; at the year's end)", "",
           "| Family | True accuracy (assumed) | Blind spot (assumed) | Score | Fee factor (at the mean score) | "
           "Share of the year barred |",
           "|---|---|---|---|---|---|"]
    for f in w.families:
        sc = rows[f"score_{f}"]
        out.append(f"| `{f}` | {100 * w.accuracy_of(f):.0f} % | {100 * w.blind_of(f):.0f} % of bad fixes | "
                   f"{_ms(sc, 1, 100)} % | {factor(mean(sc), PARAMS.SCORE_MIN_VERDICTS):.2f}× | "
                   f"{_ms(rows[f'barred_{f}'], 0, 100)} % |")
    return "\n".join(out)


# ---------- everyone moves to the top model ----------

def _mover_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    rec = a.families_at_draw
    m = market_metrics(net, rec)
    drawable = [v for v in net.reg.validators.values() if net.reg.drawable(v)]
    shares = {f: sum(1 for v in drawable if v.family == f) / max(1, len(drawable)) for f in net.w.families}
    panels = [s for s in net.subs.values() if s.tier == ISSUE and s.judges and s.k >= 3 and s.sid in rec]
    seats = Counter(f for s in panels for f in rec[s.sid])
    over_cap = sum(1 for s in panels if max(Counter(rec[s.sid]).values()) > net.p.cap(s.k))
    return {**m, "top_share": shares["top"], "largest_share": max(shares.values()),
            "families_10": sum(1 for x in shares.values() if x >= 0.10),
            "top_seats": seats["top"] / max(1, sum(seats.values())),
            "distinct": mean(len(set(rec[s.sid])) for s in panels)
            if panels else 0.0,
            "k7": net.stats["k7"] / max(1, net.stats["drawn"]), "moves": net.stats["moves"], "over_cap": over_cap,
            "net_all": mean(net.validator_net(v) / max(1e-9, (net.t - v.registered_at) / MONTH)
                            for v in net.reg.validators.values() if v.active_at is not None),
            **{f"share_{f}": x for f, x in shares.items()}}


def twins(make: Callable[[bool], A.Actor], seeds: Sequence[int],
          metrics: Callable[[Net, A.Actor], Dict[str, float]], p: Optional[Params] = None) -> Dict[str, object]:
    """`actors.against_twin`, keeping every seed's metrics (key, and twin_key for the twin's), for ± 2 SE."""
    out: Dict[str, List[float]] = defaultdict(list)
    for s in seeds:
        a, t = make(False), make(True)
        na, nt = A.run(a, s, p), A.run(t, s, p)
        out["diffs"].append(na.party_net(a.party) - nt.party_net(t.party))
        for k, v in metrics(na, a).items():
            out[k].append(v)
        for k, v in metrics(nt, t).items():
            out[f"twin_{k}"].append(v)
    return {**out, "diff": mean(out["diffs"]), "se": A._se(out["diffs"])}


def movers(seeds: Sequence[int], weighted: Optional[str] = None, p: Optional[Params] = None) -> Dict[str, object]:
    return twins(lambda h: Movers(h, everyone=True, weighted=weighted), seeds, _mover_metrics, p)


def movers_party(seeds: Sequence[int], p: Optional[Params] = None) -> Dict[str, object]:
    return A.against_twin(lambda h: Movers(h), seeds, p=p, metrics=_mover_metrics)


def movers_table(seeds: Sequence[int]) -> str:
    fams = FAMILIES
    out = [f"### Everyone moves to the top model ({len(seeds)} seeds; a year; every validator reconsiders monthly and "
           "switches to the family paying most per head when it pays 10 % more)", "",
           "| | Nobody moves | Everyone moves |", "|---|---|---|"]
    r = movers(seeds)
    t = {k[5:]: v for k, v in r.items() if k.startswith("twin_")}

    def row(label: str, key: str, nd: int = 1, scale: float = 1.0, unit: str = "") -> str:
        return f"| {label} | {_ms(t[key], nd, scale)}{unit} | {_ms(r[key], nd, scale)}{unit} |"

    out += [row(f"Share of drawable validators in `{f}` at the year's end", f"share_{f}", 0, 100, " %") for f in fams]
    out += [row("Families with at least 10 % of the validators", "families_10", 1),
            row("Share of counted seats held by `top`", "top_seats", 1, 100, " %"),
            row("Distinct families per panel (k ≥ 3)", "distinct", 2),
            row("Panels with more of one family than the cap allows", "over_cap", 0),
            row("Panels drawn at k = 7", "k7", 0, 100, " %"),
            row("Draws whose k the caps lowered", "stepped_down", 1, 100, " %"),
            row("Submissions that waited for a panel", "waited", 1, 100, " %"),
            row("Bad fixes merged per 100 paid", "bad_per_100", 2),
            row("Panels decided by one family", "one_family", 2, 100, " %"),
            row("Family switches in the year", "moves", 0),
            row("An activated validator's net per month ($)", "net_all", 2)]
    p = movers_party(seeds)
    out += ["", f"Four validators starting in `low` that move (in a network where nobody else does) against the same "
            f"four staying in `low`: return − twin's **{p['diff']:,.0f} ± {2 * p['se']:,.0f}** $ a year "
            f"({_verdict(p['diff'], p['se'])}); they made {p['moves']:.1f} switches."]
    return "\n".join(out)


def _verdict(m: float, se: float) -> str:
    if m + 2 * se < 0:
        return "loses"
    if m - 2 * se > 0:
        return "gains"
    return "not significant"


# ---------- herding ----------

def _herd_metrics(net: Net, a: A.Actor) -> Dict[str, float]:
    m = market_metrics(net)
    mine = [(vote, s.final) for s in net.subs.values() if s.tier == ISSUE and s.final is not None
            for vid, vote, _ in s.judges if net.reg.validators[vid].party == a.party]
    sc = net.scores.state(a.family)
    nodes = net.party_validators(a.party)
    return {**m, "agree": sum(1 for v, f in mine if v == f) / max(1, len(mine)), "counted": len(mine),
            "family_score": sc[0] if sc[0] is not None else float("nan"),
            "barred": net.scores.barred_days[a.family] / max(1.0, net.t / 24.0),
            "slashed": sum(v.acct.slashed for v in nodes), "caught": net.stats["receipts_upheld"]}


HERDS: Tuple[Tuple[str, str, bool, Optional[float]], ...] = (
    ("`mid` (90 %), receipts detectable", "mid", True, None),
    ("`mid` (90 %), not detectable (upper bound)", "mid", False, None),
    ("`weak` (68 %), receipts detectable", "weak", True, None),
    ("`weak` (68 %), not detectable (upper bound)", "weak", False, None),
    ("`mid`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "mid", False, 0.25),
    ("`weak`, not detectable, at a $0.25 fee (`FEE_CEILING`)", "weak", False, 0.25),
)


def herders(seeds: Sequence[int], nodes: int = 4) -> List[Tuple[str, Dict[str, object]]]:
    out = []
    for name, f, d, fee in HERDS:
        w = SCORE_WORLD if fee is None else replace(SCORE_WORLD, service_fee=fee)
        out.append((name, twins(lambda h, f=f, d=d, w=w: Herders(h, nodes=nodes, family=f, detectable=d, w=w),
                                seeds, _herd_metrics)))
    return out


def herders_table(seeds: Sequence[int], nodes: int = 4, data=None, title: str = "") -> str:
    out = [title or (f"### Herding ({len(seeds)} seeds; a year; {nodes} herders of one family among 16 honest "
                     "validators; each votes the public base rate's majority, pass, instead of its finding)"), "",
           "| Herders | Their agreement with outcomes (twin's) | Their family's score (twin's) | Family barred, share of "
           "the year (twin's) | Bad fixes merged per 100 paid (twin's) | False verdicts proven | Return − twin's "
           "($, ± 2 SE) | Herding |", "|---|---|---|---|---|---|---|---|"]
    for name, r in (data if data is not None else herders(seeds, nodes)):
        two = lambda k, nd, scale=1.0, unit="": (f"{_ms(r[k], nd, scale)}{unit} "
                                                 f"({_ms(r['twin_' + k], nd, scale)}{unit})")
        out.append(f"| {name} | {two('agree', 1, 100, ' %')} | {two('family_score', 1, 100, ' %')} | "
                   f"{two('barred', 0, 100, ' %')} | {two('bad_per_100', 2)} | {_ms(r['caught'], 1)} | "
                   f"{r['diff']:,.0f} ± {2 * r['se']:,.0f} | {_verdict(r['diff'], r['se'])} |")
    return "\n".join(out)


def tables(seeds: Sequence[int]) -> str:
    return "\n\n".join([scores_table(seeds), compare_table(seeds, SCORE_WORLD, "; families with blind spots"),
                        compare_table(seeds, NO_BLIND, "; no blind spots: independent errors only"),
                        movers_table(seeds), herders_table(seeds)])
