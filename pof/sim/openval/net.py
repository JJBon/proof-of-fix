"""The open-validator network over time (#134 phase 1): submissions arrive, panels are drawn and judge, candidates
shadow-judge and qualify, verdicts wait out their challenge windows, audits and volunteers re-run some of them,
challenges are judged by fresh panels (or wait, with the window frozen), and the outcome becomes final.

An event loop in hours (`Net.run`). Judging is computed when a panel is drawn: each judge seals, reveals or stays
silent; a silent judge is replaced by the next validator of the same sample with a fresh window, and k never
shrinks (specs/judge-panels). The verdict takes effect when the last seated judge reveals.

Randomness is bound to what it decides (`panels.u(seed, tag, submission, validator, role)`), not drawn from a
shared stream, so an actor's choices never move anyone else's dice: an attacker and its honest twin (`actors`) see
the same submissions, joins and honest votes.

Hooks for phase 2, each a constructor argument with phase 1's behaviour as the default:
- `fee`: the service fee per counted check (`FlatFee`; task 1.4's market pricing replaces it). The network calls
  `fee.fee(net, sub, v)` for each paid check and `fee.end_period(net, period)` once a day (D9's PRICE_PERIOD) with
  the period's counts: submitted, waited, drawn validators, active validators.
- `level_rule`: a panel's proof level from its judges' levels (`PHASE1_LEVEL`: always "A"; task 1.5's rule is the
  majority's weakest). The k table's bounty limit and the challenge window are looked up per (k, level).
- `family_ok`: whether a model family may be drawn for counted panels (`EVERY_FAMILY`; task 1.7's SCORE_MIN), and
  `family_outcomes`, every counted verdict's agreement with the final outcome per family (what the scores read).
  The active validators of a family it bars shadow-judge instead (specs/judge-scores, "A weak model"), and their
  shadow verdicts' agreement is recorded in `family_shadow_outcomes` (how a barred family's score recovers).
- `vote_weight`: None (v3: one judge, one vote), or a validator's vote weight (task 1.7's rejected alternative,
  votes weighted by score): a verdict, and a challenge's outcome, then pass on a strict majority of the weight.

#141's rules (proof-of-fix#141, design "Revision 2026-11-03"), each switched by its `Params` field, so `params.V1`
runs #134's network unchanged:
- the k = 1 hold (`K1_HOLD`): a k = 1 verdict is held, unpaid, its window not running, while fewer than CHALLENGE_K[1]
  validators are eligible for its challenge panel; at most `K1_PENDING_MAX` k = 1 verdicts not yet final per
  validator (or `K1_BATCH_BOND`); every k = 1 verdict audited once a validator outside its panel is eligible
  (`AUDIT_K1_ALL`, deferred until then);
- shadows (`SHADOW_LONE_RULE`, `SHADOW_PER_WAITING`): scored only against outcomes no lone validator set; a held k = 1
  verdict's shadows, and a waiting submission's, against the majority of the verdicts sealed on it;
- larger challenge panels (`panels.challenge_draw`), D16's flat slashes, unbonding after every open verdict, the
  constitution drawn from 2 x K_MAX eligible with expiry, and the wait signal a newcomer could end (`period`'s
  "waited_floor" and "waited_any", read by `pricing.Market`).

Round 2's rules (design "Revision 2026-11-03, round 2"), each switched by its `Params` field, so `params.V2R1` runs
round 1's network unchanged:
- every k = 1 verdict audited by `K1_AUDITS` (2) different auditors outside its panel, each drawn by the seed once
  eligible (`_more_audits`);
- the constitution: an ADR that only removes a TEE type (`Sub.removal`) is drawn from `REMOVAL_MIN_ELIGIBLE` (14)
  eligible, anything else (adding ADRs, escalated fixes) from `CONSTITUTION_MIN_ELIGIBLE` (21); both expire on a
  smaller network; every ADR and escalated fix posts `ADR_DEPOSIT`, forfeited to the sponsors' pool when rejected
  (`DEPOSIT_FORFEIT_TO` "funder": the rejected alternative) and refunded when it passes or expires;
- the constitution's list of TEE types (`tee_list`): a removal ADR that passes takes effect `REMOVAL_WINDOW_H` after
  its verdict; validators of a removed type stop being drawn (counted, shadow, audit, challenge) and newcomers of it
  are refused; the last accepted type is never removed; the TEE-type cap starts at `Params.tee_from(len(tee_list))`
  (`dp`, the parameters every draw reads);
- the flat slashes ($5), the every-wait fee signal, the balanced score and recovery by blocks are read where round 1's
  were (`_run_panel`, `pricing.Market`, `scores.Scores`).
"""

from __future__ import annotations

import heapq
import math
import random
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

from . import panels as D
from .params import BPS, DAY, LEVELS, MONTH, PARAMS, WEEK, WORLD, YEAR, Params, World
from .registry import ACTIVE, CANDIDATE, TEE_TYPES, ZKTLS, Registry, Validator

ISSUE, CONSTITUTION = "issue", "constitution"
COUNTED, SHADOW, AUDIT, CHALLENGE, VOLUNTEER = 1, 2, 3, 4, 5  # roles: part of each judge's randomness key
ACTOR_SID = 2_000_000  # actors' submissions are numbered from here; honest ones from 1
ACTOR_VID = 1_000_000  # actors' validators likewise
VOLUNTEER_ID = 0
HONEST_SOLVERS, HONEST_FUNDERS = 50, 30
T_BLIND = 0xB11D  # randomness tag of a family's blind spot and of barred families' shadow draws (task 1.7)
R_CONST_FEW = "constitution: fewer than CONSTITUTION_MIN_ELIGIBLE eligible"
R_K1_CAP = "k = 1: every eligible validator at its pending k = 1 cap"
OPEN = ("judging", "window", "held", "challenged")  # a drawn submission not yet final


# ---------- phase 2's hooks, with phase 1's defaults ----------

class FlatFee:
    """Phase 1's service fee: v2's flat fee per counted check, the same for every judge."""

    def __init__(self, service_fee: float):
        self.service_fee = service_fee

    def fee(self, net: "Net", sub: "Sub", v: Validator) -> float:
        return self.service_fee

    def end_period(self, net: "Net", period: Counter) -> None:
        pass


def PHASE1_LEVEL(levels: Sequence[str]) -> str:
    return "A"


def EVERY_FAMILY(family: str) -> bool:
    return True


# ---------- records ----------

@dataclass(frozen=True)
class Act:
    """What a judge did: whether it sealed and revealed, its vote, whether its receipt is fabricated (a re-run can
    show it), and the receipts it found fabricated (re-runs) or confirms (challenge judges)."""
    revealed: bool
    sealed: bool = True
    vote: bool = False
    faked: bool = False
    found: Tuple[int, ...] = ()


@dataclass
class PartyAccount:
    """An actor's solver side: what its submissions earned and cost."""
    gains: float = 0.0  # bounties paid on its fixes, and what a passed ADR is worth to it
    costs: float = 0.0  # attempt fees and the check charges of its counted judges
    submitted: int = 0
    paid: int = 0
    bad_paid: int = 0
    adrs_passed: int = 0
    deposits: float = 0.0  # ADR_DEPOSIT posted (round 2)
    forfeited: float = 0.0  # ...and forfeited by rejected ADRs and escalated fixes


@dataclass(eq=False)
class Sub:
    """A sealed submission (a fix to a bounty, or an ADR at the constitution tier)."""
    sid: int
    t: float
    bounty: float
    good: bool  # the truth a correct check finds: a good fix passes, a bad one fails
    solver: str
    parties: FrozenSet[str]  # declared accounts recused from its panels (solver, funder, ...)
    tier: str = ISSUE
    party: Optional[str] = None  # the actor behind it (accounting); None for honest solvers
    commitment: int = 0
    value: float = 0.0  # what passing it is worth to its party beyond the bounty (an ADR)
    state: str = "new"  # new, waiting, judging, window, challenged, final, withdrawn
    seed: int = 0
    k: int = 0
    level: str = "A"
    draw: Optional[D.Draw] = None
    judges: List[Tuple[int, bool, bool]] = field(default_factory=list)  # (vid, vote, faked), the counted panel
    shadows: List[Tuple[int, bool, bool]] = field(default_factory=list)  # (vid, revealed, vote)
    family_shadows: List[Tuple[int, bool, bool]] = field(default_factory=list)  # barred families' (vid, revealed, vote)
    verdict: Optional[bool] = None
    drawn_t: Optional[float] = None
    verdict_t: Optional[float] = None
    window_end: Optional[float] = None
    final: Optional[bool] = None
    final_t: Optional[float] = None
    waited_since: Optional[float] = None
    wait_reason: str = ""
    tried_epoch: int = -1
    challenge: Optional["Challenge"] = None
    reversed: bool = False
    replaced: int = 0
    charges: float = 0.0
    token: int = 0  # invalidates a scheduled finality when a challenge freezes the window
    audit: str = ""  # "", "agreed", "mismatch", "no auditor"
    # #141
    remaining: float = 0.0  # hours of its window left (frozen by a challenge, or not yet started while held)
    held_since: Optional[float] = None  # the k = 1 hold: since when its window is held
    held_h: float = 0.0  # hours held in all
    was_held: bool = False
    volunteered: bool = False  # the volunteer's re-run was drawn (once, when its window first runs)
    shadows_scored: bool = False  # its shadows were scored by the sealed majority (D5), not at finality
    wait_shadows: List[Tuple[int, bool, bool]] = field(default_factory=list)  # shadows drawn while it waited
    wait_floor: bool = False  # its wait counts toward the fee's rise: a floor-bond newcomer could have ended it
    wait_any: bool = False  # ...a newcomer of any bond could have
    k1_judge: Optional[int] = None  # the k = 1 judge whose pending count it holds
    # round 2
    auditors: List[int] = field(default_factory=list)  # the validators that audited it (K1_AUDITS: two at k = 1)
    removal: Optional[str] = None  # an ADR that only removes this TEE type (drawn from REMOVAL_MIN_ELIGIBLE)
    escalated: bool = False  # an escalated fix at the constitution tier (from CONSTITUTION_MIN_ELIGIBLE, with a deposit)
    funder_party: Optional[str] = None  # the actor that funded its issue (an escalated fix), if any
    deposit: float = 0.0  # ADR_DEPOSIT it posted
    queued: List["Challenge"] = field(default_factory=list)  # an auditor's dispute filed while another was judged

    @property
    def waited(self) -> bool:
        return self.waited_since is not None


@dataclass(eq=False)
class Challenge:
    sub: Sub
    filed_t: float
    by: str  # "audit" or "volunteer"
    challenger: Optional[int]  # the auditor's id; volunteers aren't validators
    outcome: bool  # disputes the verdict's outcome
    accused: Tuple[int, ...]  # judges whose receipts it disputes
    state: str = "filed"
    waited: bool = False
    tried_epoch: int = -1
    k: int = 0
    upheld: bool = False
    receipts: Tuple[int, ...] = ()
    resolved_t: Optional[float] = None


@dataclass(eq=False)
class Panel:
    """A panel being judged (counted or challenge): k fixed at the draw; the queue grows by one replacement per
    silent judge."""
    role: int
    sub: Sub
    draw: D.Draw
    queue: List[Tuple[Validator, float]]
    seated: List[Validator]
    exclude: Set[int]
    qi: int = 0
    votes: List[Tuple[int, bool, bool, Tuple[int, ...]]] = field(default_factory=list)
    finish: float = 0.0
    stall_t: float = 0.0
    challenge: Optional[Challenge] = None


# ---------- behaviours ----------

class Honest:
    """An honest validator: drawn, it runs the official check (its verdict matches the truth with its family's
    accuracy, independently of the others), misses a seal at 1 - reliability (an outage: before the seal, or after it
    with `World.outage_sealed`), re-runs honestly as an auditor or a challenge judge, and tops its bond back up after
    a slash."""
    tops_up = True

    def counted(self, net: "Net", sub: Sub, v: Validator) -> Act:
        if not net.online(sub, v, COUNTED):
            return Act(False, net.outage_sealed(sub, v, COUNTED))
        return Act(True, True, net.honest_vote(sub, v, COUNTED))

    def shadow(self, net: "Net", sub: Sub, v: Validator) -> Act:
        if not net.online(sub, v, SHADOW):
            return Act(False, False)
        return Act(True, True, net.honest_vote(sub, v, SHADOW))

    def audit(self, net: "Net", sub: Sub, v: Validator) -> Act:
        if not net.online(sub, v, AUDIT):
            return Act(False, False)
        return Act(True, True, net.honest_vote(sub, v, AUDIT), found=net.rerun_found(sub, v.vid))

    def challenge(self, net: "Net", ch: Challenge, v: Validator) -> Act:
        if not net.online(ch.sub, v, CHALLENGE):
            return Act(False, net.outage_sealed(ch.sub, v, CHALLENGE))
        return Act(True, True, net.honest_vote(ch.sub, v, CHALLENGE), found=net.confirms(ch, v))


HONEST = Honest()


# ---------- the network ----------

class Net:
    def __init__(self, seed: int, p: Params = PARAMS, w: World = WORLD, actors: Sequence[object] = (),
                 fee: Optional[FlatFee] = None, level_rule: Callable[[Sequence[str]], str] = PHASE1_LEVEL,
                 family_ok: Callable[[str], bool] = EVERY_FAMILY,
                 vote_weight: Optional[Callable[[Validator], float]] = None):
        self.seed, self.p, self.w = seed, p, w
        self.fee = fee if fee is not None else FlatFee(w.service_fee)
        self.level_rule, self.family_ok, self.vote_weight = level_rule, family_ok, vote_weight
        self.actors = list(actors)
        self.reg = Registry(p, proofs=tuple(dict.fromkeys(tuple(w.tees) + tuple(sorted(TEE_TYPES)))) + (ZKTLS,))
        self.t = 0.0
        self._q: list = []
        self._n = 0
        self.subs: Dict[int, Sub] = {}
        self.waiting: Dict[int, Sub] = {}
        self.ch_waiting: List[Challenge] = []
        self.stalled: List[Panel] = []
        self.family_outcomes: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        self.family_shadow_outcomes: Dict[str, List[Tuple[float, bool]]] = defaultdict(list)
        self.stats: Counter = Counter()
        self.period: Counter = Counter()
        self.period_drawn: Set[int] = set()
        self.series: List[dict] = []
        self.parties: Dict[str, PartyAccount] = defaultdict(PartyAccount)
        self.k_seen: List[Tuple[int, int]] = []  # (k drawn, judges counted) per panel: k never shrinks
        # #141's bookkeeping
        self.k1_pending: Counter = Counter()  # per validator: its k = 1 verdicts not yet final
        self.k1_bounty: Dict[int, float] = defaultdict(float)  # ...and their bounties (K1_BATCH_BOND)
        self.k1_live: Dict[int, Sub] = {}  # k = 1 verdicts not yet final (held, in window or challenged)
        self.audit_due: Dict[int, Sub] = {}  # always-audited verdicts waiting for an auditor
        self.open_by: Dict[int, Set[int]] = defaultdict(set)  # per validator: drawn submissions it judged, not final
        # round 2: the constitution's list of TEE types (a removal ADR shortens it) and the parameters draws read
        self.tee_list: List[str] = list(dict.fromkeys(w.tees))
        self.tees_removed = False
        self.dp = p.for_tees(self._tee_count())
        self._sid = ACTOR_SID
        self._joined = 0
        self._next_snapshot = 0.0
        self._start()

    # ----- set-up -----

    def genesis_spec(self) -> dict:
        """The deployment's genesis validator when no actor brings its own."""
        w = self.w
        return dict(key="genesis", signer="genesis", bond=w.genesis_bond, proof=w.tees[0], host=w.hosts[0],
                    family=w.families[0], operator="genesis")

    def _start(self) -> None:
        w = self.w
        gen = None
        for a in self.actors:
            gen = gen or a.genesis(self)
        self.reg.genesis([gen or self.genesis_spec()])
        for i in range(w.initial_active):
            v = self.reg.register(0.0, key=f"init-{i}", signer=f"init-{i}", bond=w.initial_bond,
                                  proof=w.tees[(i + 1) % len(w.tees)], host=w.hosts[(i + 1) % len(w.hosts)],
                                  family=w.families[(i + 1) % len(w.families)], operator=f"init-{i}")
            self.reg.seed_active(v, 0.0)
        horizon = w.horizon_h
        rng = random.Random(D.h(D.T_ARRIVALS, self.seed))
        rate = w.subs_week / WEEK
        mu = math.log(w.bounty_median)
        sigma = math.log(w.bounty_p90 / w.bounty_median) / 1.2815515655446004
        t, sid = 0.0, 0
        while rate > 0:
            t += rng.expovariate(rate)
            if t > horizon:
                break
            sid += 1
            bounty = round(min(w.bounty_max, rng.lognormvariate(mu, sigma)), 2)
            good = rng.random() < w.good_share
            solver, funder = f"solver-{rng.randrange(HONEST_SOLVERS)}", f"funder-{rng.randrange(HONEST_FUNDERS)}"
            self._at(t, self._arrive, Sub(sid, t, bounty, good, solver, frozenset((solver, funder)),
                                          commitment=rng.getrandbits(64)))
        rng = random.Random(D.h(D.T_JOINS, self.seed))
        rate = w.joins_week / WEEK
        bonds, weights = zip(*w.join_bonds)
        t = 0.0
        while rate > 0:
            t += rng.expovariate(rate)
            if t > horizon:
                break
            self._at(t, self._join, rng.choices(bonds, weights)[0], rng.choice(w.hosts), w.pick_tee(rng),
                     rng.choice(w.families))
        for a in self.actors:
            a.setup(self)
        self._at(DAY, self._tick)

    def _at(self, t: float, fn, *args) -> None:
        heapq.heappush(self._q, (t, self._n, fn, args))
        self._n += 1

    def run(self) -> "Net":
        horizon = self.w.horizon_h
        while self._q and self._q[0][0] <= horizon:
            t, _, fn, args = heapq.heappop(self._q)
            self.t = t
            fn(*args)
        self.t = horizon
        return self

    # ----- randomness bound to what it decides -----

    def online(self, sub: Sub, v: Validator, role: int) -> bool:
        return D.u(self.seed, D.T_REVEAL, sub.sid, v.vid, role) < self.w.reliability

    def outage_sealed(self, sub: Sub, v: Validator, role: int) -> bool:
        """Whether an honest outage struck after the seal (a sealed vote not revealed) rather than before it."""
        return self.w.outage_sealed > 0 and D.u(self.seed, D.T_OUTAGE, sub.sid, v.vid, role) < self.w.outage_sealed

    def honest_vote(self, sub: Sub, v: Optional[Validator], role: int) -> bool:
        if (v is not None and not sub.good and self.w.family_blind
                and D.u(self.seed, T_BLIND, sub.sid, zlib.crc32(v.family.encode())) < self.w.blind_of(v.family)):
            return True  # the family's blind spot: every judge of the family is fooled by this bad fix
        acc = self.w.accuracy_of(v.family) if v is not None else self.w.accuracy
        right = D.u(self.seed, D.T_VOTE, sub.sid, v.vid if v is not None else VOLUNTEER_ID, role) < acc
        return sub.good if right else not sub.good

    def rerun_found(self, sub: Sub, rerunner: int) -> Tuple[int, ...]:
        """The counted judges whose fabricated receipts a re-run shows (each with `rerun_detect`)."""
        return tuple(vid for vid, _, faked in sub.judges
                     if faked and D.u(self.seed, D.T_DETECT, sub.sid, rerunner, vid) < self.w.rerun_detect)

    def confirms(self, ch: Challenge, v: Validator) -> Tuple[int, ...]:
        faked = {vid for vid, _, f in ch.sub.judges if f}
        return tuple(a for a in ch.accused if a in faked
                     and D.u(self.seed, D.T_DETECT, ch.sub.sid, v.vid, a, CHALLENGE) < self.w.rerun_detect)

    @staticmethod
    def _beh(v: Validator):
        return v.behaviour or HONEST

    # ----- actors' entry points -----

    def submit(self, t: float, bounty: float, good: bool, solver: str, party: Optional[str], tier: str = ISSUE,
               value: float = 0.0, parties: Optional[Sequence[str]] = None, commitment: Optional[int] = None) -> Sub:
        sid = self._sid
        self._sid += 1
        sub = Sub(sid, t, bounty, good, solver, frozenset(parties or (solver,)), tier, party,
                  D.h(self.seed, sid) if commitment is None else commitment, value)
        self._at(t, self._arrive, sub)
        return sub

    def register_actor(self, i: int, party: str, bond: float, host: str, tee: str, family: str,
                       operator: str, behaviour: object, active: bool = False) -> Validator:
        vid = ACTOR_VID + i
        v = self.reg.register(self.t, key=f"{party}-{vid}", signer=f"{party}-{vid}", bond=bond, proof=tee,
                              host=host, family=family, operator=operator, party=party, behaviour=behaviour,
                              vid=vid)
        if active:
            self.reg.seed_active(v, self.t)
        return v

    # ----- events -----

    def _join(self, bond: float, host: str, tee: str, family: str) -> None:
        self._joined += 1
        n = self._joined
        if self.tees_removed and tee not in self.tee_list:  # round 2: a removed TEE type can't register
            self.stats["refused_tee"] += 1
            return
        self.reg.register(self.t, key=f"k{n}", signer=f"k{n}", bond=bond, proof=tee, host=host, family=family,
                          operator=f"op-{n}")
        self.stats["joined"] += 1

    def _arrive(self, sub: Sub) -> None:
        self.subs[sub.sid] = sub
        self.stats["submitted"] += 1
        self.period["submitted"] += 1
        if sub.party:
            pa = self.parties[sub.party]
            pa.costs += self.w.attempt_fee
            pa.submitted += 1
        if sub.tier == CONSTITUTION and self.p.ADR_DEPOSIT > 0:  # round 2 (D7): an ADR's or escalated fix's deposit
            sub.deposit = self.p.ADR_DEPOSIT
            self.stats["deposits"] += sub.deposit
            if sub.party:
                self.parties[sub.party].costs += sub.deposit
                self.parties[sub.party].deposits += sub.deposit
        self._try_draw(sub)

    def _refund(self, sub: Sub) -> None:
        """D7: the deposit back, when the ADR takes effect or expires."""
        if sub.deposit and sub.party:
            self.parties[sub.party].costs -= sub.deposit
        self.stats["deposits_refunded"] += sub.deposit

    def _forfeit(self, sub: Sub) -> None:
        """D7: a rejected ADR or escalated fix forfeits its deposit to the sponsors' pool, never to the issue's funder
        or reporter (`DEPOSIT_FORFEIT_TO` "funder", the rejected alternative: to an escalated fix's funder)."""
        if not sub.deposit:
            return
        if sub.party:
            self.parties[sub.party].forfeited += sub.deposit
        if self.p.DEPOSIT_FORFEIT_TO == "funder" and sub.escalated and sub.funder_party:
            self.parties[sub.funder_party].gains += sub.deposit
            self.stats["deposits_to_funder"] += sub.deposit
        else:
            self.stats["deposits_forfeited"] += sub.deposit  # the sponsors' pool

    def _seed(self, sub: Sub) -> int:
        seal = D.block_at(sub.t)
        now = D.block_at(self.t)
        if now - (seal + self.p.SEED_DELAY) > D.BLOCKHASH_RANGE:
            seal = now  # D3: past 256 blocks the draw re-targets to the latest block plus SEED_DELAY
        return D.draw_seed(self.p, self.seed, seal, sub.commitment, sub.bounty, sub.sid)

    def eligible(self, sub: Sub, exclude: Set[int] = frozenset()) -> List[Validator]:
        bounty = 0.0 if sub.tier == CONSTITUTION else sub.bounty
        out = self.reg.eligible(bounty, sub.parties, frozenset(exclude), self.family_ok)
        if self.tees_removed:  # round 2: a removed TEE type's validators stop being drawn
            out = [v for v in out if self.tee_ok(v)]
        return out

    def shadow_candidates(self, sub: Sub) -> List[Validator]:
        """The candidates a submission's shadow draw may sample (task 1.5 keeps level C off hidden tests)."""
        out = self.reg.candidates(self.t, sub.parties)
        if self.tees_removed:
            out = [v for v in out if self.tee_ok(v)]
        return out

    # ----- round 2: the constitution's TEE types -----

    def tee_ok(self, v: Validator) -> bool:
        """Its TEE type is on the constitution's list (level C has none)."""
        return v.tee == "none" or v.tee in self.tee_list

    def _tee_count(self) -> int:
        """The accepted TEE types the cap counts (D6). `levels.LevelNet` reads its constitution's list instead."""
        return len(self.tee_list)

    def _refresh_dp(self) -> None:
        self.dp = self.p.for_tees(self._tee_count())

    def remove_tee(self, tee: str) -> bool:
        """A removal ADR takes effect: the type leaves the list (never the last one: owner, 2026-11-03), its validators
        stop being drawn, and the TEE cap's start follows the new count from the next draw."""
        if tee not in self.tee_list:
            return False
        if len(self.tee_list) <= 1:
            self.stats["removals_refused_last"] += 1
            return False
        stopped = [v for v in self.reg.validators.values() if self.reg.drawable(v) and v.tee == tee]
        self.tee_list.remove(tee)
        self.tees_removed = True
        self.stats["removals_applied"] += 1
        self.stats["stopped_drawn"] += len(stopped)
        self._refresh_dp()
        self.reg.epoch += 1
        return True

    def plan(self, sub: Sub) -> Tuple[int, Optional[D.Draw], str]:
        """The draw a submission would get now: (k, draw, reason it waits). A pure function of the seed and the
        registry, so anyone (a solver, the seed grinder) can compute it once the seed is known."""
        p = self.dp
        pool = self.eligible(sub)
        seed = self._seed(sub)
        if sub.tier == CONSTITUTION:
            if len(pool) < p.constitution_min(sub.removal is not None):
                return 0, None, R_CONST_FEW
            d = D.constitution_draw(seed, pool, p, self.reg.epoch)
            return (d.k, d, "") if d.filled else (0, None, "constitution: the caps")
        k0 = p.k_for(len(pool))
        if k0 == 0:
            return 0, None, "no eligible validator"
        if sub.bounty > max(p.limit(k0, lv) for lv in LEVELS):
            return 0, None, "above the limit"
        d = D.draw(seed, pool, k0, p, epoch=self.reg.epoch)
        if not d.filled:
            return 0, None, "the caps"
        if d.k == 1 and not self.k1_ok(self.reg.validators[d.panel[0]], sub):
            ok = [v for v in pool if self.k1_ok(v, sub)]  # D4: a validator at its pending cap isn't drawn at k = 1
            d = D.draw(seed, ok, 1, p, exact=True, epoch=self.reg.epoch) if ok else None
            if d is None or not d.filled:
                return 0, None, R_K1_CAP
        level = self.level_rule([self.reg.validators[v].level for v in d.panel])
        if sub.bounty > p.limit(d.k, level):
            return 0, None, "above the limit after the caps"
        return d.k, d, ""

    def k1_ok(self, v: Validator, sub: Sub) -> bool:
        """D4: may `v` judge `sub` alone? Under its K1_PENDING_MAX, or (K1_BATCH_BOND) bonded for all its pending k = 1
        bounties and this one."""
        p = self.p
        if p.K1_BATCH_BOND:
            return v.bond >= p.BOND_FACTOR * (self.k1_bounty[v.vid] + sub.bounty) - 1e-9
        return p.K1_PENDING_MAX is None or self.k1_pending[v.vid] < p.K1_PENDING_MAX

    def fixable(self, sub: Sub) -> Tuple[bool, bool]:
        """D9's wait signal (#141): would one more validator bonded at BOND_FLOOR, of any host, TEE type, family or
        level, have let `sub` be drawn? And one of any bond (the switch)? The newcomer joins the eligible count, and
        may pick whatever host, TEE type, family and level the caps and the level limit need."""
        p = self.p
        k = p.k_for(len(self.eligible(sub)) + 1)
        fits = k > 0 and sub.bounty <= max(p.limit(k, lv) for lv in LEVELS)
        return fits and p.bond_needed(sub.bounty) <= p.BOND_FLOOR + 1e-9, fits

    def _try_draw(self, sub: Sub) -> None:
        sub.tried_epoch = self.reg.epoch
        k, d, reason = self.plan(sub)
        if d is None:
            if sub.tier == CONSTITUTION and reason == R_CONST_FEW and self.p.CONSTITUTION_EXPIRE:
                self.waiting.pop(sub.sid, None)  # D7: an ADR submitted to a small network expires unjudged
                sub.state, sub.wait_reason = "expired", reason
                self.stats["adrs_expired"] += 1
                self._refund(sub)
                return
            if sub.sid not in self.waiting:
                self.waiting[sub.sid] = sub
                sub.waited_since = self.t
                self.stats["waited"] += 1
                self.period["waited"] += 1
                if sub.tier == ISSUE and self.p.WAIT_SIGNAL != "every":
                    sub.wait_floor, sub.wait_any = self.fixable(sub)
                    self.stats["waited_floor"] += sub.wait_floor
                    self.period["waited_floor"] += sub.wait_floor
                    self.period["waited_any"] += sub.wait_any
                if sub.tier == ISSUE and self.p.SHADOW_PER_WAITING > 0:
                    self._wait_shadows(sub)
            sub.state, sub.wait_reason = "waiting", reason
            return
        if self.waiting.pop(sub.sid, None) is not None:
            self.stats["drawn_after_wait"] += 1
        sub.seed, sub.draw, sub.k, sub.drawn_t, sub.state = d.seed, d, k, self.t, "judging"
        sub.level = self.level_rule([self.reg.validators[v].level for v in d.panel])
        self.stats["drawn"] += 1
        self.stats[f"k{k}"] += 1
        self.stats["stepped_down"] += k < d.k0  # the caps (or DRAW_TRIES) lowered k
        if sub.tier == ISSUE:
            self._draw_shadows(sub)
        seated = [self.reg.validators[v] for v in d.panel]
        self._run_panel(Panel(COUNTED, sub, d, [(v, self.t) for v in seated], list(seated), set(), finish=self.t))

    def _draw_shadows(self, sub: Sub) -> None:
        p, w = self.p, self.w
        s = p.shadows_per_draw(sum(1 for v in self.reg.validators.values() if v.state == ACTIVE))
        for v in D.shadows(sub.draw.seed, self.shadow_candidates(sub), s, p):
            act = self._beh(v).shadow(self, sub, v)
            if act.sealed:
                v.acct.overhead += w.enclave.per_check
            self.stats["shadow_pool_spend"] += w.usage_per_check  # usage repaid from the sponsors' pool, no fee
            sub.shadows.append((v.vid, act.revealed, act.vote))
        barred = [v for v in self.reg.validators.values()  # specs/judge-scores: drawn only as shadows
                  if self.reg.drawable(v) and v.operator not in sub.parties and not self.family_ok(v.family)]
        for v in D.shadows(D.h(sub.draw.seed, T_BLIND), barred, s, p):
            act = self._beh(v).shadow(self, sub, v)
            if act.sealed:
                v.acct.overhead += w.enclave.per_check
            self.stats["shadow_pool_spend"] += w.usage_per_check
            self.stats["barred_shadows"] += 1
            sub.family_shadows.append((v.vid, act.revealed, act.vote))

    def _wait_shadows(self, sub: Sub) -> None:
        """D5 (#141): SHADOW_PER_WAITING candidates drawn by the waiting submission's seed as its shadows; they judge it
        while it waits, and are scored against the majority of their sealed verdicts once revealed."""
        p, w = self.p, self.w
        for v in D.shadows(D.h(self._seed(sub), D.T_WAIT_SHADOW), self.shadow_candidates(sub), p.SHADOW_PER_WAITING,
                           p):
            act = self._beh(v).shadow(self, sub, v)
            if act.sealed:
                v.acct.overhead += w.enclave.per_check
            self.stats["shadow_pool_spend"] += w.usage_per_check
            self.stats["wait_shadow_spend"] += w.usage_per_check
            self.stats["wait_shadows"] += 1
            sub.wait_shadows.append((v.vid, act.revealed, act.vote))
        if sub.wait_shadows:
            self._at(self.t + p.judge_hours, self._score_majority, list(sub.wait_shadows), [])

    def _score_majority(self, shadows: Sequence[Tuple[int, bool, bool]], counted: Sequence[bool]) -> None:
        """D5 (#141): shadow verdicts scored against the majority of the verdicts sealed on their submission (the
        counted judge's `counted` votes and the shadows'), when at least SHADOW_MAJORITY_MIN were revealed and they
        don't tie; otherwise none of them counts toward qualification."""
        votes = list(counted) + [vote for _, revealed, vote in shadows if revealed]
        yes = sum(votes)
        if len(votes) < self.p.SHADOW_MAJORITY_MIN or 2 * yes == len(votes):
            self.stats["shadows_unscored"] += len(shadows)
            return
        majority = 2 * yes > len(votes)
        for vid, revealed, vote in shadows:
            self._record_shadow(self.reg.validators[vid], revealed, vote == majority)

    def _record_shadow(self, v: Validator, revealed: bool, agreed: bool) -> None:
        r = self.reg.record_shadow(v, revealed, agreed, self.t)
        if r == "active":
            self.stats["qualified"] += 1
            self.stats["qualify_days"] += (self.t - v.registered_at) / DAY
        elif r == "failed":
            self.stats["qualify_failed"] += 1

    def _pay_check(self, v: Validator, sub: Sub, solver_pays: bool) -> None:
        fee = self.fee.fee(self, sub, v)
        v.acct.fees += fee
        v.acct.overhead += self.w.enclave.per_check
        v.acct.checks += 1
        self.period_drawn.add(v.vid)
        if solver_pays:
            sub.charges += fee + self.w.usage_per_check
        else:
            self.stats["challenge_pay"] += fee + self.w.usage_per_check

    def _slash(self, v: Validator, bps: int, t: float) -> float:
        amount = self.reg.slash(v, bps, t)
        self.stats["slashed"] += amount
        return amount

    def _run_panel(self, panel: Panel) -> bool:
        """Seat, seal and reveal; replace each silent judge from the same sample (a missing seal counts as not
        revealed, and costs NO_REVEAL_SLASH_BPS). Returns False when the sample is exhausted (the check waits)."""
        p, reg = self.p, self.reg
        while panel.qi < len(panel.queue):
            v, ts = panel.queue[panel.qi]
            panel.qi += 1
            beh = self._beh(v)
            if panel.role == CHALLENGE:
                act = beh.challenge(self, panel.challenge, v)
            else:
                act = beh.counted(self, panel.sub, v)
            if act.revealed:
                panel.votes.append((v.vid, act.vote, act.faked, act.found))
                panel.finish = max(panel.finish, ts + p.judge_hours)
                reg.record_counted(v, True, ts)
                self._pay_check(v, panel.sub, panel.role == COUNTED)
                continue
            if reg.record_counted(v, False, ts):
                self.stats["suspended"] += 1
            if p.NO_REVEAL_SLASH_BPS:  # #134: v2's share of the bond, sealed or silent
                self._slash(v, p.NO_REVEAL_SLASH_BPS, ts)
            # D16 (#141): flat, or (round 3's switch) the larger of that and a share of the bounty
            flat = p.miss_slash(panel.sub.bounty, act.sealed)
            if flat > 0:
                self.stats["slashed"] += reg.slash_flat(v, flat, ts)
            self.stats["withheld" if act.sealed else "silent"] += 1
            self.stats["missed_reveals"] += 1
            if act.sealed:
                v.acct.overhead += self.w.enclave.per_check
            panel.seated.remove(v)
            t_fail = ts + (p.judge_hours if act.sealed else p.SEAL_WINDOW_H)
            if not self._replace(panel, t_fail):
                panel.stall_t = t_fail
                self.stalled.append(panel)
                self.stats["stalled"] += 1
                return False
        self._panel_done(panel)
        return True

    def _replace(self, panel: Panel, t: float, fresh: bool = False) -> bool:
        excl = panel.exclude | panel.draw.drawn
        pool = self.eligible(panel.sub, excl)
        rep = D.replacement(panel.draw, panel.seated, {v.vid: v for v in pool}, self.dp,
                            pool=[v.vid for v in pool] if fresh else None)
        if rep is None:
            return False
        panel.seated.append(rep)
        panel.queue.append((rep, t))
        panel.sub.replaced += 1
        self.stats["replaced"] += 1
        return True

    def _panel_done(self, panel: Panel) -> None:
        self.k_seen.append((panel.draw.k, len(panel.votes)))
        if panel.role == CHALLENGE:
            self._at(panel.finish, self._resolve, panel.challenge, panel)
            return
        sub = panel.sub
        sub.judges = [(vid, vote, faked) for vid, vote, faked, _ in panel.votes]
        for vid, _, _ in sub.judges:
            self.open_by[vid].add(sub.sid)
        if sub.tier == ISSUE and sub.k == 1 and sub.judges:
            sub.k1_judge = vid = sub.judges[0][0]
            self.k1_pending[vid] += 1
            self.k1_bounty[vid] += sub.bounty
            self.k1_live[sub.sid] = sub
        need = self.p.CONSTITUTION_QUORUM if sub.tier == CONSTITUTION else (sub.k + 1) // 2
        if self.vote_weight is not None and sub.tier == ISSUE:
            sub.verdict = self.weighted([(vid, vote) for vid, vote, _ in sub.judges])
        else:
            sub.verdict = sum(1 for _, vote, _ in sub.judges if vote) >= need
        sub.verdict_t = panel.finish
        self._at(panel.finish, self._after_verdict, sub)

    def _after_verdict(self, sub: Sub) -> None:
        p, w, t = self.p, self.w, self.t
        if sub.party:
            self.parties[sub.party].costs += sub.charges
        if sub.tier == CONSTITUTION:  # a removal takes effect after REMOVAL_WINDOW (D11), anything else ADR_WINDOW
            sub.window_end = t + (p.REMOVAL_WINDOW_H if sub.removal is not None else p.ADR_WINDOW_H)
            sub.state = "window"
            self._at(sub.window_end, self._final, sub, sub.token)
            return
        window = p.window_h(sub.k, sub.level)
        sub.window_end, sub.state, sub.remaining = t + window, "window", window
        first = None  # the earliest re-run that disputes the verdict: (time, by, challenger, outcome, accused)
        always = self.always_audit(sub)
        if D.audited(sub.seed, p) or always:
            a = D.auditor(sub.seed, self.eligible(sub, sub.draw.drawn))
            if a is None:
                if always:  # #141: audited once a validator outside its panel is eligible (each tick tries)
                    self.audit_due[sub.sid] = sub
                    self.stats["audits_deferred"] += 1
                else:
                    sub.audit = "no auditor"
                    self.stats["audits_no_auditor"] += 1
            else:
                first = self._audit(sub, a)
                if always:
                    self._more_audits(sub)  # round 2: K1_AUDITS different auditors
        if sub.tier == ISSUE and sub.k == 1 and p.SHADOW_LONE_RULE and (not p.K1_HOLD or not self.hold_ok(sub)):
            # D5: a lone validator's verdict, held (or never held back), doesn't score its shadows: the majority of
            # the verdicts sealed on it does
            sub.shadows_scored = True
            self._score_majority(sub.shadows, [vote for _, vote, _ in sub.judges])
        if p.K1_HOLD and sub.tier == ISSUE and sub.k == 1 and not self.hold_ok(sub):
            self._hold(sub)  # D4: no window, no payment, until CHALLENGE_K[1] could judge its challenge
            if first is not None:
                self._at(first[0], self._file, Challenge(sub, first[0], first[1], first[2], first[3], first[4]))
            return
        sub.volunteered = True
        first = self._volunteer(sub, window, first)
        if first is not None:
            self._at(first[0], self._file, Challenge(sub, first[0], first[1], first[2], first[3], first[4]))
        self._at(sub.window_end, self._final, sub, sub.token)

    def always_audit(self, sub: Sub) -> bool:
        """#141 (D13): audited whatever the random draw: every k = 1 verdict (AUDIT_K1_ALL). `levels.LevelNet` adds
        every split level C pass."""
        return self.p.AUDIT_K1_ALL and sub.tier == ISSUE and sub.k == 1

    def audits_needed(self, sub: Sub) -> int:
        """Round 2 (D13): K1_AUDITS different auditors for a k = 1 verdict; one for any other audited verdict."""
        if self.p.AUDIT_K1_ALL and sub.tier == ISSUE and sub.k == 1:
            return max(1, self.p.K1_AUDITS)
        return 1

    def _more_audits(self, sub: Sub) -> None:
        """Round 2: after the first audit, each further one by a different validator outside the panel, drawn by the
        seed (its own counter) as soon as one is eligible; until then the verdict waits in `audit_due`. A mismatch from
        any auditor files a challenge."""
        while len(sub.auditors) < self.audits_needed(sub):
            pool = self.eligible(sub, set(sub.draw.drawn) | set(sub.auditors))
            a = D.auditor(D.h(sub.seed, D.T_AUDITOR, len(sub.auditors)), pool)
            if a is None:
                self.audit_due[sub.sid] = sub
                return
            d = self._audit(sub, a)
            if d is not None:
                self._at(d[0], self._file, Challenge(sub, d[0], d[1], d[2], d[3], d[4]))

    def _audit(self, sub: Sub, a: Validator):
        """One auditor re-runs the check and seals its result; returns the dispute it files, or None."""
        w, p = self.w, self.p
        sub.auditors.append(a.vid)
        act = self._beh(a).audit(self, sub, a)
        fee = self.fee.fee(self, sub, a)
        a.acct.fees += fee
        a.acct.overhead += w.enclave.per_check
        a.acct.audits += 1
        self.stats["audits"] += 1
        self.stats["audit_pay"] += fee + w.usage_per_check
        if act.revealed:
            mismatch = act.vote != sub.verdict
            sub.audit = "mismatch" if mismatch or act.found else "agreed"
            if mismatch or act.found:
                return (self.t + p.judge_hours, "audit", a.vid, mismatch, act.found)
        return None

    def _volunteer(self, sub: Sub, window: float, first):
        """A volunteer re-runs the verdict at `volunteer_per_day` from when its window runs: the earlier dispute."""
        w, t = self.w, self.t
        lam = w.volunteer_per_day / DAY
        if lam > 0:
            dt = -math.log(1.0 - D.u(self.seed, D.T_VOLUNTEER, sub.sid)) / lam
            if dt < window and (first is None or t + dt < first[0]):
                vote = self.honest_vote(sub, None, VOLUNTEER)
                found = self.rerun_found(sub, VOLUNTEER_ID)
                if vote != sub.verdict or found:
                    first = (t + dt, "volunteer", None, vote != sub.verdict, found)
        return first

    # ----- #141's k = 1 hold -----

    def hold_ok(self, sub: Sub) -> bool:
        """D4: may a k = 1 verdict's window run? At least CHALLENGE_K[1] validators eligible for its challenge panel:
        active, outside its panel, not a party, bonded for its bounty."""
        return len(self.eligible(sub, sub.draw.drawn)) >= self.p.challenge_k(1)

    def _hold(self, sub: Sub) -> None:
        sub.state = "held"
        sub.token += 1
        if sub.held_since is None:
            sub.held_since = self.t
        if not sub.was_held:
            sub.was_held = True
            self.stats["held"] += 1

    def _open(self, sub: Sub) -> None:
        """The window runs (again) for its remaining hours: at once, or when the hold lifts. A volunteer's re-run is
        drawn the first time it runs."""
        t = self.t
        if sub.held_since is not None:
            sub.held_h += t - sub.held_since
            sub.held_since = None
        sub.state, sub.window_end = "window", t + sub.remaining
        sub.token += 1
        if not sub.volunteered:
            sub.volunteered = True
            first = self._volunteer(sub, sub.remaining, None)
            if first is not None:
                self._at(first[0], self._file, Challenge(sub, first[0], first[1], first[2], first[3], first[4]))
        self._at(sub.window_end, self._final, sub, sub.token)

    def _reopen(self, sub: Sub) -> None:
        """After a challenge that didn't reverse it: the window resumes, unless the hold applies (k = 1)."""
        if self.p.K1_HOLD and sub.tier == ISSUE and sub.k == 1 and not self.hold_ok(sub):
            self._hold(sub)
        else:
            self._open(sub)

    def _recheck_holds(self) -> None:
        """Each tick: a held k = 1 verdict whose challengers are now eligible starts its window; one whose challengers
        are no longer eligible is held again ("its window runs only while...")."""
        for sub in list(self.k1_live.values()):
            if sub.state == "held" and self.hold_ok(sub):
                self._open(sub)
            elif sub.state == "window" and not self.hold_ok(sub):
                sub.remaining = max(0.0, sub.window_end - self.t)
                self._hold(sub)

    def _retry_audits(self) -> None:
        """Each tick: an always-audited verdict still without an auditor gets one if one is now eligible."""
        for sub in list(self.audit_due.values()):
            if sub.state not in ("held", "window"):
                if sub.state == "final":
                    del self.audit_due[sub.sid]
                continue
            if not sub.auditors:
                a = D.auditor(sub.seed, self.eligible(sub, sub.draw.drawn))
                if a is None:
                    continue
                del self.audit_due[sub.sid]
                d = self._audit(sub, a)
                if d is not None:
                    self._at(d[0], self._file, Challenge(sub, d[0], d[1], d[2], d[3], d[4]))
            else:
                del self.audit_due[sub.sid]
            self._more_audits(sub)

    def _file(self, ch: Challenge) -> None:
        sub = ch.sub
        if sub.state not in ("window", "held"):
            if sub.state == "challenged" and self.queues(ch):
                sub.queued.append(ch)  # judged after the pending challenge, unless that one reverses the verdict
                self.stats["challenges_queued"] += 1
            return
        if sub.state == "window":
            sub.remaining = max(0.0, sub.window_end - self.t)
        elif sub.held_since is not None:
            sub.held_h += self.t - sub.held_since
            sub.held_since = None
        sub.state, sub.challenge = "challenged", ch
        sub.token += 1  # the window is frozen until the challenge is resolved
        self.stats["challenges"] += 1
        self.stats[f"challenges_{ch.by}"] += 1
        self._try_challenge(ch)

    def _try_challenge(self, ch: Challenge) -> None:
        sub, p = ch.sub, self.dp
        ch.tried_epoch = self.reg.epoch
        excl = set(sub.draw.drawn) | ({ch.challenger} if ch.challenger is not None else set())
        pool = self.eligible(sub, excl)
        seed = D.challenge_seed(self.seed, sub.seed, D.block_at(self.t), p)
        d = D.challenge_draw(seed, pool, sub.k, p, self.reg.epoch)
        if not d.filled:
            if not ch.waited:
                ch.waited = True
                self.stats["challenges_waited"] += 1
                self.ch_waiting.append(ch)
            ch.state = "waiting"
            return
        if ch.waited and ch in self.ch_waiting:
            self.ch_waiting.remove(ch)
        ch.state, ch.k = "judging", d.k
        seated = [self.reg.validators[v] for v in d.panel]
        self._run_panel(Panel(CHALLENGE, sub, d, [(v, self.t) for v in seated], list(seated), excl,
                              finish=self.t, challenge=ch))

    def _resolve(self, ch: Challenge, panel: Panel) -> None:
        sub, p, t = ch.sub, self.p, self.t
        need = (ch.k + 1) // 2
        if self.vote_weight is not None:
            upheld = ch.outcome and self.weighted([(vid, vote != sub.verdict) for vid, vote, _, _ in panel.votes])
        else:
            upheld = ch.outcome and sum(1 for _, vote, _, _ in panel.votes if vote != sub.verdict) >= need
        receipts = tuple(a for a in ch.accused if sum(1 for *_, found in panel.votes if a in found) >= need)
        ch.upheld, ch.receipts, ch.resolved_t, ch.state = upheld, receipts, t, "resolved"
        for a in receipts:
            amount = self._slash(self.reg.validators[a], p.FALSE_VERDICT_SLASH_BPS, t)
            reward = amount * p.CHALLENGE_REWARD_BPS / BPS
            if ch.challenger is not None:
                self.reg.validators[ch.challenger].acct.rewards += reward
            self.stats["receipts_upheld"] += 1
            self.stats["slashed_false"] += amount
        if upheld:
            sub.reversed = True
            self.stats["reversed"] += 1
            self._finalize(sub, not sub.verdict)
            return
        if not receipts:
            self.stats["challenges_rejected"] += 1
        self._reopen(sub)  # the window resumes (or, at k = 1, waits for its challengers)
        if sub.queued and sub.state in ("window", "held"):
            nxt = sub.queued.pop(0)
            nxt.filed_t = t
            self._file(nxt)

    def queues(self, ch: Challenge) -> bool:
        """Round 2 (D13, "Every lone verdict is audited twice"): a mismatch from either auditor of a k = 1 verdict opens
        a challenge, so an auditor's dispute filed while another challenge on the verdict is judged waits its turn
        instead of being dropped (round 1, one audit: a later dispute on a challenged verdict was dropped)."""
        sub = ch.sub
        return ch.by == "audit" and sub.tier == ISSUE and sub.k == 1 and self.p.K1_AUDITS > 1

    def _final(self, sub: Sub, token: int) -> None:
        if token == sub.token and sub.state == "window":
            self._finalize(sub, sub.verdict)

    def _finalize(self, sub: Sub, outcome: bool) -> None:
        t = self.t
        sub.final, sub.final_t, sub.state = outcome, t, "final"
        for vid, _, _ in sub.judges:
            self.open_by[vid].discard(sub.sid)
        if sub.k1_judge is not None:
            self.k1_pending[sub.k1_judge] -= 1
            self.k1_bounty[sub.k1_judge] -= sub.bounty
            self.k1_live.pop(sub.sid, None)
        self.audit_due.pop(sub.sid, None)
        pa = self.parties[sub.party] if sub.party else None
        if sub.tier == ISSUE:
            self.stats["final"] += 1
            self.stats["final_days"] += (t - sub.t) / DAY
            if outcome:
                self.stats["paid"] += 1
                self.stats["bad_merged"] += not sub.good
                if pa is not None:
                    pa.gains += sub.bounty
                    pa.paid += 1
                    pa.bad_paid += not sub.good
        else:
            if outcome:
                self.stats["adrs_passed"] += 1
                if pa is not None:
                    pa.gains += sub.value
                    pa.adrs_passed += 1
                self._refund(sub)
                if sub.removal is not None:  # D11: it takes effect now, REMOVAL_WINDOW after its verdict
                    self.remove_tee(sub.removal)
            else:
                self.stats["adrs_rejected"] += 1
                self._forfeit(sub)
        for vid, vote, _ in sub.judges:
            self.family_outcomes[self.reg.validators[vid].family].append((t, vote == outcome, outcome))
        if not sub.shadows_scored:  # D5: an outcome no lone validator set (#134: every final outcome)
            for vid, revealed, vote in sub.shadows:
                self._record_shadow(self.reg.validators[vid], revealed, vote == outcome)
        for vid, revealed, vote in sub.family_shadows:
            if revealed:
                self.family_shadow_outcomes[self.reg.validators[vid].family].append((t, vote == outcome, outcome))

    def weighted(self, votes: Sequence[Tuple[int, bool]]) -> bool:
        """The rejected alternative's tally: True on a strict majority of the votes' weight."""
        weights = [(self.vote_weight(self.reg.validators[vid]), vote) for vid, vote in votes]
        return 2 * sum(x for x, vote in weights if vote) > sum(x for x, _ in weights)

    def _withdraw_bond(self, v: Validator) -> None:
        """After the delay; #141 (UNBOND_AFTER_CHALLENGES): and once every verdict it gave is final (so every
        challenge naming it is closed), checked daily until then."""
        if self.p.UNBOND_AFTER_CHALLENGES and self.open_by.get(v.vid):
            self.stats["unbond_waits"] += 1
            self._at(self.t + DAY, self._withdraw_bond, v)
            return
        self.reg.withdraw(v, self.t)

    def leave(self, v: Validator) -> None:
        self.reg.leave(v, self.t)
        self._at(v.unbond_at, self._withdraw_bond, v)

    def _tick(self) -> None:
        t, w, reg = self.t, self.w, self.reg
        self.period["active"] = sum(1 for v in reg.validators.values() if v.state == ACTIVE)
        self.period["drawn_validators"] = len(self.period_drawn)
        self.fee.end_period(self, self.period)
        self.period, self.period_drawn = Counter(), set()
        for v in reg.validators.values():
            if v.state in (ACTIVE, CANDIDATE) and v.bond < v.target and self._beh(v).tops_up:
                reg.top_up(v, v.target)
        for panel in list(self.stalled):
            if self._replace(panel, max(t, panel.stall_t), fresh=True):
                self.stalled.remove(panel)
                self._run_panel(panel)
        for ch in list(self.ch_waiting):
            if ch.tried_epoch != reg.epoch:
                self._try_challenge(ch)
        for sub in list(self.waiting.values()):
            if (sub.tier == ISSUE and t - sub.waited_since >= w.withdraw_after_days * DAY
                    and all(a.withdraws(self, sub) for a in self.actors)):
                del self.waiting[sub.sid]
                sub.state = "withdrawn"  # the deposit comes back; nothing was metered
                self.stats["withdrawn"] += 1
            elif sub.tried_epoch != reg.epoch:
                self._try_draw(sub)
        if self.k1_live and self.p.K1_HOLD:
            self._recheck_holds()
        if self.audit_due:
            self._retry_audits()
        if t >= self._next_snapshot:
            self.series.append(self.snapshot())
            self._next_snapshot = t + w.snapshot_weeks * WEEK - 1e-9
        for a in self.actors:
            a.on_tick(self)
        self._at(t + DAY, self._tick)

    # ----- what the report reads -----

    def largest_bounty(self) -> float:
        """The largest bounty a panel could judge now, from the bonds alone (before the caps)."""
        p = self.p
        bonds = [v.bond for v in self.reg.validators.values() if self.reg.drawable(v)]
        best = 0.0
        for b in sorted(set(p.BOUNTY_LIMIT["A"].values()) | {x / p.BOND_FACTOR for x in bonds}):
            k = p.k_for(sum(1 for x in bonds if x >= p.bond_needed(b) - 1e-9))
            if k and b <= p.limit(k):
                best = b
        return best

    def snapshot(self) -> dict:
        reg = self.reg
        return {"week": round(self.t / WEEK, 1),
                "active": sum(1 for v in reg.validators.values() if reg.drawable(v)),
                "candidates": sum(1 for v in reg.validators.values() if v.state == CANDIDATE),
                "k_small": self.p.k_for(len(reg.eligible(self.p.limit(1)))),
                "max_bounty": self.largest_bounty(), "waiting": len(self.waiting),
                "submitted": self.stats["submitted"], "withdrawn": self.stats["withdrawn"],
                "final": self.stats["final"], "waited": self.stats["waited"]}

    def validator_net(self, v: Validator) -> float:
        """Fees and rewards (and bribes) less the node's costs, slashes and the bond's capital cost, to now."""
        a, w = v.acct, self.w
        run_end = min(self.t, v.leave_at) if v.leave_at is not None else self.t
        if v.gone_at is not None:
            cap_end = min(self.t, v.gone_at)
        elif v.unbond_at is not None and not self.p.UNBOND_AFTER_CHALLENGES:
            cap_end = min(self.t, v.unbond_at)
        else:
            cap_end = self.t  # still locked: its bond is withdrawn only once nothing it judged is open
        months = max(0.0, run_end - v.registered_at) / MONTH
        years = max(0.0, cap_end - v.registered_at) / YEAR
        return (a.fees + a.rewards + a.gains - a.overhead - a.slashed - months * w.enclave.fixed_month
                - v.posted * w.capital_rate * years)

    def party_net(self, party: str) -> float:
        nodes = sum(self.validator_net(v) for v in self.reg.validators.values() if v.party == party)
        pa = self.parties.get(party)
        return nodes + ((pa.gains - pa.costs) if pa is not None else 0.0)

    def party_validators(self, party: str) -> List[Validator]:
        return [v for v in self.reg.validators.values() if v.party == party]
