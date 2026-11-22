"""Proof levels (#132 design D10, D11; specs validator-admission, judge-panels, incentive-simulation; #134 task 1.5).

- **A validator's level** is read from its proof at registration (`registry.Registry.register`): a TEE with the cloud
  platform's own attestation is A, a TEE whose location isn't proven (a home or rented server) B, zkTLS C.
- **A panel's level** is the lowest level held by a majority of its judges (`majority_weakest`): sort the judges'
  levels strongest first and take the ((k + 1) / 2)-th. Any mix is allowed, all level C included.
- **Limits and windows** are looked up per (k, level) (`Params.BOUNTY_LIMIT`, `Params.CHALLENGE_WINDOW_H`). A drawn
  panel whose level can't judge the bounty doesn't judge it: the draw is void, the submission waits and is drawn again
  with a fresh seed when the registry changes (#141, gap 12).
- **#141:** the genesis must be at a level of `Params.GENESIS_LEVELS` (A or B; a level C genesis is refused at
  deployment), and every non-unanimous pass by a level C panel is audited (`AUDIT_SPLIT_C`).
- **Hidden tests and private repositories** go only to panels whose every judge is at level A or B: level C
  validators aren't eligible for them as counted judges, shadows, auditors or challenge judges. Volunteers can't re-run
  hidden tests, so only audits and challenge panels re-check those verdicts.
- **The constitution's lists** (`Constitution`): accepted TEE types, listed zkTLS notaries and each TEE type's minimum
  firmware (TCB) level, with platforms their makers revoked refused at registration. A removal or a raised minimum
  takes effect `REMOVAL_WINDOW` after its ADR; an addition after the full window (D11). Validators of a removed type,
  or below the minimum, stop being drawn and keep their bonds; a zkTLS verdict proven by an unlisted notary doesn't
  count (the judge is treated as not having revealed, and replaced).

`LevelNet` is `net.Net` with those rules and a world of mixed levels (`LevelWorld`). The attackers, each against its
honest twin (`against_twin`, the phase-1 helper's equivalent for a `LevelNet`):
- `TestLiar`: a level C validator reporting test results it didn't get, for its own solver's bad fixes;
- `AnswerShopper`: a level C validator calling the model until it gets a pass on its own solver's borderline fixes,
  with a valid zkTLS proof of the call it keeps (not provable per call);
- `ChipBreaker`: a level B validator that broke its own chip and signs verdicts outside the official code on a
  share of its draws, for a bribe paid when the fix is paid.

`python3 -m pof.sim.openval levels --seeds N` prints the tables of reports/open-validators-v1.md, "Proof levels". Simulated
only (rule 1): nothing here opens a connection.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from . import actors as A
from . import panels as D
from .actors import Colluder, _se
from .net import ACTOR_VID, AUDIT, CHALLENGE, COUNTED, HONEST, ISSUE, PHASE1_LEVEL, VOLUNTEER_ID, Act, Honest, Net, Sub
from .params import DAY, LEVELS, PARAMS, WORLD, Params, World
from .registry import TEE_TYPES, ZKTLS, RegistrationError, Validator

LEVEL_RANK = {"A": 0, "B": 1, "C": 2}
THIRDS = (1 / 3, 1 / 3, 1 / 3)
CLOUD_TEES = ("nitro",)  # a TEE that exists only in a cloud (AWS Nitro): level A by construction
HOME_TEES = ("tdx", "sev-snp")  # server-class chips a home or bare-metal validator can own (D12): level B
# randomness tags of this module (panels' tags are 1-16; these can't collide with a sibling's next ones)
T_LEVEL, T_HIDDEN, T_SHOP, T_BREAK, T_LIAR = 0x1E7E1_01, 0x1E7E1_02, 0x1E7E1_03, 0x1E7E1_04, 0x1E7E1_05


def majority_weakest(levels: Sequence[str]) -> str:
    """D10: the lowest level held by a majority of the judges. With the levels sorted strongest first, a majority
    ((k + 1) / 2 judges) holds at least the ((k + 1) / 2)-th one, and no majority holds a stronger one."""
    if not levels:
        return "A"
    s = sorted(levels, key=LEVEL_RANK.__getitem__)
    return s[(len(s) + 1) // 2 - 1]


# ---------- the constitution's lists (D10, D11) ----------

@dataclass(frozen=True)
class LevelParams:
    """The proof-level parameters the design names that `Params` doesn't carry (kept here so phase 2's tasks don't
    edit one shared table)."""
    REMOVAL_WINDOW_H: float = 48.0  # an ADR removing a type, notary or image, or raising a TCB minimum (design)
    ADD_WINDOW_H: float = 14 * DAY  # an ADR adding one: "the full challenge window (14 days, #85)"
    # "the vendors' current patched levels at deployment": modelled as level 1 of each TEE type's firmware
    TCB_MIN: Tuple[Tuple[str, int], ...] = (("nitro", 1), ("tdx", 1), ("sev-snp", 1))
    # several notaries listed, none required (task 1.9 measures which to list; these are placeholders)
    NOTARIES: Tuple[str, ...] = ("notary-1", "notary-2", "notary-3")


LEVEL_PARAMS = LevelParams()


class Constitution:
    """The constitution's proof lists over time. `adr(t, kind, key, value)` records an ADR that passed the
    constitution tier at t; it takes effect after REMOVAL_WINDOW_H (removals, raised minimums) or ADD_WINDOW_H
    (additions). Kinds: remove_tee, add_tee, raise_tcb (value: the new minimum), remove_notary, add_notary.
    `revoked`: platforms their makers revoked, refused at registration."""

    SLOW = ("add_tee", "add_notary")
    FAST = ("remove_tee", "raise_tcb", "remove_notary")

    def __init__(self, lp: LevelParams = LEVEL_PARAMS, tees: Sequence[str] = tuple(sorted(TEE_TYPES))):
        tees = tuple(tees)
        self.lp = lp
        self._tees0 = frozenset(tees)
        self._tcb0 = dict(lp.TCB_MIN)
        self._notaries0 = frozenset(lp.NOTARIES)
        self.changes: List[Tuple[float, int, str, str, object]] = []
        self.revoked: Set[str] = set()

    def adr(self, t: float, kind: str, key: str, value: object = None) -> float:
        if kind not in self.SLOW + self.FAST:
            raise ValueError(kind)
        eff = t + (self.lp.ADD_WINDOW_H if kind in self.SLOW else self.lp.REMOVAL_WINDOW_H)
        self.changes.append((eff, len(self.changes), kind, key, value))
        return eff

    def state(self, t: float) -> Tuple[Set[str], Dict[str, int], Set[str]]:
        tees, tcb, notaries = set(self._tees0), dict(self._tcb0), set(self._notaries0)
        for eff, _, kind, key, value in sorted(self.changes):
            if eff > t:
                break
            if kind == "remove_tee":
                tees.discard(key)
            elif kind == "add_tee":
                tees.add(key)
                tcb.setdefault(key, int(value or 1))
            elif kind == "raise_tcb":
                tcb[key] = max(tcb.get(key, 0), int(value))
            elif kind == "remove_notary":
                notaries.discard(key)
            else:
                notaries.add(key)
        return tees, tcb, notaries

    def tee_ok(self, tee: str, t: float) -> bool:
        return tee in self.state(t)[0]

    def tcb_min(self, tee: str, t: float) -> int:
        return self.state(t)[1].get(tee, 0)

    def notary_ok(self, notary: str, t: float) -> bool:
        return notary in self.state(t)[2]


@dataclass
class Attest:
    """What a validator's attestation (or zkTLS set-up) shows beyond the registry's record: the platform's id (for
    makers' revocations), its firmware (TCB) level, and the notary its zkTLS proofs come from."""
    platform: str
    tcb: int
    notary: str


class Unproven(Honest):
    """A level C judge whose zkTLS proof comes from a notary not on the list: it seals and reveals, but its verdict
    doesn't count (judge-panels: treated as not having revealed; the next validator in the shuffle replaces it)."""

    def __init__(self, inner: object):
        self.inner = inner
        self.tops_up = getattr(inner, "tops_up", True)

    def counted(self, net, sub, v):
        return Act(False, self.inner.counted(net, sub, v).sealed)

    def shadow(self, net, sub, v):
        return Act(False, self.inner.shadow(net, sub, v).sealed)

    def audit(self, net, sub, v):
        return Act(False, self.inner.audit(net, sub, v).sealed)

    def challenge(self, net, ch, v):
        return Act(False, self.inner.challenge(net, ch, v).sealed)


# ---------- the network with levels ----------

@dataclass(frozen=True)
class LevelWorld:
    """The world's levels (assumptions the report names): the honest validators' levels, the genesis validator's,
    the share of honest bounties with hidden tests or on private repositories, and how often an honest judge passes a
    borderline bad fix (the answer shopper's target; ordinary bad fixes use `World.accuracy`)."""
    mix: Tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)  # A, B, C: newcomers and validators active at the start
    genesis_level: str = "A"
    hidden_share: float = 0.0
    borderline_pass: float = 0.3
    # level C accepted? None: `Params.C_ACCEPTED` (owner decision 2026-11-03: off at launch). When it isn't,
    # validators who would register at C are refused (they don't join; none is active at the start)
    c_accepted: Optional[bool] = None


LEVEL_WORLD = LevelWorld()


class LevelNet(Net):
    """`net.Net` with D10's levels: a level per validator, the panel's level by `majority_weakest`, all-TEE panels for
    hidden tests, the constitution's lists (TEE types, notaries, TCB minimums), borderline fixes."""

    def __init__(self, seed: int, p: Params = PARAMS, w: World = WORLD, actors: Sequence[object] = (),
                 lw: LevelWorld = LEVEL_WORLD, lp: LevelParams = LEVEL_PARAMS,
                 level_rule: Callable[[Sequence[str]], str] = majority_weakest, **kw):
        self.lw, self.lp = lw, lp
        self.const = Constitution(lp, tuple(sorted(set(TEE_TYPES) | set(w.tees))))
        self.att: Dict[int, Attest] = {}
        self.hidden: Set[int] = set()
        self.borderline: Set[int] = set()
        self.reasons: Dict[int, Set[str]] = defaultdict(set)  # every reason each submission waited
        super().__init__(seed, p, w, actors, level_rule=level_rule, **kw)

    # ----- levels at registration -----

    def pick_level(self, n: int) -> str:
        """An honest validator's level from the world's mix, bound to its join number (twins see the same)."""
        x, acc = D.u(T_LEVEL, self.seed, n), 0.0
        for lv, share in zip(LEVELS, self.lw.mix):
            acc += share
            if x < acc:
                return lv
        return LEVELS[-1]

    @staticmethod
    def proof_for(level: str, tee: str, n: int) -> str:
        if level == "C":
            return ZKTLS
        if level == "B" and tee in CLOUD_TEES:
            return HOME_TEES[n % len(HOME_TEES)]
        return tee

    def _relevel(self, v: Validator, level: str) -> None:
        """A validator set up by `Net._start` (the genesis, validators active at the start) as if it had registered
        with the proof of `level`."""
        v.level, v.proof = level, self.proof_for(level, v.proof if v.proof != ZKTLS else "tdx", v.vid)
        v.attestation = None if level == "C" else (v.attestation or "att")

    def genesis_spec(self) -> dict:
        """The genesis validator registered at the world's genesis level (a level the deployment may refuse)."""
        lv = self.lw.genesis_level
        return {**super().genesis_spec(), "proof": self.proof_for(lv, self.w.tees[0], 1), "cloud_attested": lv == "A",
                "attestation": None if lv == "C" else "att"}

    @property
    def c_ok(self) -> bool:
        """Level C accepted: the world's override, else `Params.C_ACCEPTED`."""
        return self.p.C_ACCEPTED if self.lw.c_accepted is None else self.lw.c_accepted

    def _start(self) -> None:
        super()._start()
        for v in list(self.reg.validators.values()):
            if v.key.startswith("init-"):
                self._relevel(v, self.pick_level(-1 - int(v.key[5:])))
                if v.level == "C" and not self.c_ok:  # level C off: it never registered
                    del self.reg.validators[v.vid]
                    self.reg.epoch += 1
                    self.stats["refused_c"] += 1

    def _join(self, bond: float, host: str, tee: str, family: str) -> None:
        self._joined += 1
        n = self._joined
        level = self.pick_level(n)
        if level == "C" and not self.c_ok:  # level C isn't accepted (off at launch)
            self.stats["refused_c"] += 1
            return
        self.reg.register(self.t, key=f"k{n}", signer=f"k{n}", bond=bond, proof=self.proof_for(level, tee, n),
                          host=host, family=family, operator=f"op-{n}", cloud_attested=level == "A",
                          attestation=None if level == "C" else "att")
        self.stats["joined"] += 1

    def attest(self, v: Validator) -> Attest:
        a = self.att.get(v.vid)
        if a is None:  # registered at the minimum then in force, with the first listed notary
            a = self.att[v.vid] = Attest(f"chip-{v.vid}", self.const.tcb_min(v.proof, v.registered_at),
                                         self.lp.NOTARIES[0])
        return a

    def register_level(self, key: str, bond: float, level: str, host: str, family: str, operator: str,
                       tee: Optional[str] = None, tcb: Optional[int] = None, platform: Optional[str] = None,
                       notary: Optional[str] = None, party: Optional[str] = None, behaviour: object = None,
                       vid: Optional[int] = None, active: bool = False) -> Validator:
        """Register at a level, checked against the constitution's lists now: an accepted TEE type at or above its
        minimum firmware on a platform its maker hasn't revoked (A, B), or a listed notary (C)."""
        t = self.t
        tee = tee or ("nitro" if level == "A" else HOME_TEES[0])
        if level == "C" and not self.c_ok:
            raise RegistrationError("level C isn't accepted: it is off at launch until a constitution ADR switches it on")
        if level != "C":
            if not self.const.tee_ok(tee, t):
                raise RegistrationError(f"TEE type {tee!r} isn't accepted")
            if tcb is not None and tcb < self.const.tcb_min(tee, t):
                raise RegistrationError(f"firmware level {tcb} is below {tee}'s minimum")
            if platform is not None and platform in self.const.revoked:
                raise RegistrationError(f"platform {platform!r} was revoked by its maker")
        elif notary is not None and not self.const.notary_ok(notary, t):
            raise RegistrationError(f"notary {notary!r} isn't listed")
        self.reg.proofs = frozenset(self.const.state(t)[0]) | {ZKTLS}  # the registry follows the constitution
        v = self.reg.register(t, key=key, signer=key, bond=bond, proof=ZKTLS if level == "C" else tee, host=host,
                              family=family, operator=operator, cloud_attested=level == "A",
                              attestation=None if level == "C" else "att", party=party, behaviour=behaviour, vid=vid)
        self.att[v.vid] = Attest(platform or f"chip-{v.vid}",
                                 tcb if tcb is not None else self.const.tcb_min(v.proof, t),
                                 notary or self.lp.NOTARIES[0])
        if active:
            self.reg.seed_active(v, t)
        return v

    def register_level_actor(self, i: int, party: str, bond: float, level: str, host: str, family: str,
                             operator: str, behaviour: object, active: bool = False, tee: Optional[str] = None
                             ) -> Validator:
        vid = ACTOR_VID + i
        return self.register_level(f"{party}-{vid}", bond, level, host, family, operator, tee=tee, party=party,
                                   behaviour=behaviour, vid=vid, active=active)

    # ----- the constitution's changes -----

    def adr(self, kind: str, key: str, value: object = None) -> float:
        """An ADR on the proof lists passed now; returns when it takes effect (and the registry's epoch moves then,
        so waiting submissions are retried)."""
        eff = self.const.adr(self.t, kind, key, value)
        self._at(eff, self._bump)
        return eff

    def _bump(self) -> None:
        self.reg.epoch += 1
        self._refresh_dp()  # round 2: the TEE cap's start follows the number of accepted types

    def _tee_count(self) -> int:
        """The constitution's accepted TEE types now (D6: the TEE cap's start reads it)."""
        return len(self.const.state(self.t)[0])

    def reattest(self, v: Validator, tcb: int) -> None:
        """A validator updated its firmware and attests again."""
        self.attest(v).tcb = tcb
        self.reg.epoch += 1

    def attests(self, v: Validator) -> bool:
        """Its TEE type is still accepted and its firmware at the current minimum (level C: always; its proofs are
        checked per verdict)."""
        if v.level == "C":
            return True
        return self.const.tee_ok(v.proof, self.t) and self.attest(v).tcb >= self.const.tcb_min(v.proof, self.t)

    # ----- who may be drawn -----

    def always_audit(self, sub: Sub) -> bool:
        """#141: also every pass by a level C panel whose judges weren't unanimous (D10, D13)."""
        if super().always_audit(sub):
            return True
        return (self.p.AUDIT_SPLIT_C and sub.tier == ISSUE and sub.level == "C" and bool(sub.verdict)
                and not all(vote for _, vote, _ in sub.judges))

    def _allowed(self, sub: Sub, v: Validator) -> bool:
        return self.attests(v) and not (v.level == "C" and sub.sid in self.hidden)

    def eligible(self, sub: Sub, exclude=frozenset()) -> List[Validator]:
        return [v for v in super().eligible(sub, exclude) if self._allowed(sub, v)]

    def shadow_candidates(self, sub: Sub) -> List[Validator]:
        return [v for v in super().shadow_candidates(sub) if self._allowed(sub, v)]

    def _beh(self, v: Validator):
        b = v.behaviour or HONEST
        if v.level == "C" and not self.const.notary_ok(self.attest(v).notary, self.t):
            return Unproven(b)
        return b

    def plan(self, sub: Sub):
        k, d, reason = super().plan(sub)
        if reason == "above the limit after the caps":
            pool = self.eligible(sub)
            dd = D.draw(self._seed(sub), pool, self.p.k_for(len(pool)), self.p, epoch=self.reg.epoch)
            if dd.filled and sub.bounty <= self.p.limit(dd.k, "A"):
                reason = "the panel's proof level"
        elif reason == "no eligible validator" and sub.sid in self.hidden:
            reason = "hidden tests: no TEE validator"
        return k, d, reason

    def _try_draw(self, sub: Sub) -> None:
        super()._try_draw(sub)
        if sub.state == "waiting":
            self.reasons[sub.sid].add(sub.wait_reason)

    # ----- submissions -----

    def submit(self, *a, hidden: bool = False, borderline: bool = False, **kw) -> Sub:
        sub = super().submit(*a, **kw)
        if hidden:
            self.hidden.add(sub.sid)
        if borderline:
            self.borderline.add(sub.sid)
        return sub

    def _arrive(self, sub: Sub) -> None:
        if sub.party is None and self.lw.hidden_share > 0 and D.u(T_HIDDEN, self.seed, sub.sid) < self.lw.hidden_share:
            self.hidden.add(sub.sid)
        super()._arrive(sub)

    def pass_prob(self, sub: Sub, v: Optional[Validator]) -> float:
        """One honest model call's chance to pass the fix."""
        if sub.sid in self.borderline and not sub.good:
            return self.lw.borderline_pass
        acc = self.w.accuracy_of(v.family) if v is not None else self.w.accuracy
        return acc if sub.good else 1.0 - acc

    def honest_vote(self, sub: Sub, v: Optional[Validator], role: int) -> bool:
        if v is None and sub.sid in self.hidden:
            return bool(sub.verdict)  # a volunteer can't run hidden tests, so it has nothing to dispute
        if sub.sid in self.borderline and not sub.good:
            return D.u(self.seed, D.T_VOTE, sub.sid, v.vid if v is not None else VOLUNTEER_ID, role) \
                < self.lw.borderline_pass
        return super().honest_vote(sub, v, role)

    def rerun_found(self, sub: Sub, rerunner: int) -> Tuple[int, ...]:
        if rerunner == VOLUNTEER_ID and sub.sid in self.hidden:
            return ()
        return super().rerun_found(sub, rerunner)

    # ----- what the report reads -----

    def largest_bounty(self) -> float:
        """The largest bounty a panel could judge now, from the bonds and levels alone (before the caps): for each
        bounty, k from the validators bonded for it, and the level of a majority of the strongest k of them."""
        p = self.p
        vs = [v for v in self.reg.validators.values() if self.reg.drawable(v) and self.attests(v)]
        steps = {x for lv in LEVELS for x in p.BOUNTY_LIMIT[lv].values()} | {v.bond / p.BOND_FACTOR for v in vs}
        best = 0.0
        for b in sorted(steps):
            el = sorted((v.level for v in vs if v.bond >= p.bond_needed(b) - 1e-9), key=LEVEL_RANK.__getitem__)
            k = p.k_for(len(el))
            if k and b <= p.limit(k, majority_weakest(el[:k])):
                best = b
        return best


# ---------- the attackers ----------

class LevelActor(A.Actor):
    """A phase-2 attacker in a `LevelNet`. `where`: "genesis" (it is the genesis validator of a network growing from
    one, so it judges alone at k = 1 while the network is small) or "grown" (one node among `honest_nodes` validators
    already active, newcomers at half a validator a week)."""
    level = "A"

    def __init__(self, honest: bool = False, where: str = "genesis", honest_nodes: int = 14):
        super().__init__(honest)
        if where not in ("genesis", "grown"):
            raise ValueError(where)
        self.where, self.honest_nodes = where, honest_nodes

    def world(self) -> World:
        return WORLD if self.where == "genesis" else replace(WORLD, initial_active=self.honest_nodes, joins_week=0.5)

    def level_world(self, p: Optional[Params] = None) -> LevelWorld:
        return LEVEL_WORLD

    def node_spec(self, net: LevelNet) -> dict:
        tee = "nitro" if self.level == "A" else HOME_TEES[0]
        return dict(level=self.level, host="home" if self.level != "A" else net.w.hosts[0],
                    family=net.w.families[3], tee=tee)

    def genesis(self, net: Net) -> Optional[dict]:
        if self.where != "genesis":
            return None
        s = self.node_spec(net)
        lv = s["level"]
        return dict(key=self.party, signer=self.party, bond=self.bond, proof=ZKTLS if lv == "C" else s["tee"],
                    host=s["host"], family=s["family"], operator=f"{self.party}-op", party=self.party,
                    behaviour=self.behaviour(self.make_behaviour()), cloud_attested=lv == "A",
                    attestation=None if lv == "C" else "att")

    def setup(self, net: Net) -> None:
        if self.where == "grown":
            s = self.node_spec(net)
            net.register_level_actor(0, self.party, self.bond, s["level"], s["host"], s["family"], f"{self.party}-op",
                                     self.behaviour(self.make_behaviour()), active=True, tee=s["tee"])

    def make_behaviour(self) -> object:
        return None

    def me(self, net: Net) -> Validator:
        return self.nodes(net)[0]


class _SolverActor(LevelActor):
    """An attacker whose own solver submits bad fixes at `bad_week` (one a day at most), to bounties its node may
    judge: while the network judges small bounties at k = 1 (where="genesis"), up to k = 1's limit at its level; in a
    grown network, up to the limit of the current k at its level and half its bond. `twin_submits`: the twin keeps
    submitting the same fixes (and judges them honestly) instead of submitting none."""
    borderline = False
    grown_mix: Tuple[float, float, float] = (0.0, 0.0, 1.0)  # where="grown": the honest validators' levels

    def __init__(self, honest: bool = False, where: str = "genesis", bad_week: Optional[float] = None,
                 bond: Optional[float] = None, honest_nodes: int = 14, twin_submits: bool = False):
        super().__init__(honest, where, honest_nodes)
        self.bad_week = bad_week if bad_week is not None else (5.0 if where == "genesis" else 2.0)
        self.bond = bond if bond is not None else (100.0 if where == "genesis" else 500.0)
        self.twin_submits = twin_submits

    def level_world(self, p: Optional[Params] = None) -> LevelWorld:
        """Grown: the honest validators at `grown_mix`; an all-C network's genesis at C where the deployment allows it
        (#134), else at A (#141 refuses a level C genesis)."""
        if self.where == "genesis":
            return LEVEL_WORLD
        all_c = self.grown_mix == (0.0, 0.0, 1.0) and "C" in (p or PARAMS).GENESIS_LEVELS
        return replace(LEVEL_WORLD, mix=self.grown_mix, genesis_level="C" if all_c else "A")

    def setup(self, net: Net) -> None:
        super().setup(net)
        self.rng = random.Random(D.h(net.seed, T_LIAR, LEVEL_RANK[self.level], self.where == "grown"))

    def on_tick(self, net: Net) -> None:
        go, x, y = self.rng.random() < self.bad_week / 7, self.rng.random(), self.rng.random()
        if (self.honest and not self.twin_submits) or not go:
            return
        me, p = self.me(net), net.p
        lv = net.level_rule([self.level])  # its own level, or "A" in the counterfactual without levels
        if not net.reg.drawable(me):
            return
        if self.where == "genesis":
            lim = p.limit(1, lv)
            if p.k_for(len(net.reg.eligible(lim))) != 1:
                return
            bounty = lim * (0.4 + 0.6 * x)
        else:
            k = p.k_for(len(net.reg.eligible(p.limit(1, lv))))
            cap = min(me.bond / p.BOND_FACTOR, p.limit(k, lv)) if k else 0.0
            if cap <= 0:
                return
            w = net.w
            mu, sigma = math.log(w.bounty_median), math.log(w.bounty_p90 / w.bounty_median) / 1.2815515655446004
            bounty = min(cap, math.exp(mu + sigma * _probit(x)))
        net.submit(net.t, round(bounty, 2), False, f"{self.party}-solver", self.party, borderline=self.borderline)


def _probit(x: float) -> float:
    """The standard normal quantile (Acklam's rational approximation, enough for drawing bounties)."""
    x = min(max(x, 1e-9), 1 - 1e-9)
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00)
    if x < 0.02425:
        q = math.sqrt(-2 * math.log(x))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if x > 1 - 0.02425:
        return -_probit(1 - x)
    q = x - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
        (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


class TestLiar(_SolverActor):
    """The level C test liar (incentive-simulation, "A level C validator lies about the tests"): a zkTLS validator
    whose model call is proven but whose tests are only checked by re-runs. On its own solver's bad fixes it reports
    passing tests it didn't get (a receipt a re-run doesn't reproduce: `Colluder`, faked when its check fails), and
    defends them as an auditor or a challenge judge. Its twin: the same validator judging honestly, and no bad
    fixes."""
    name = "level C test liar"
    party = "liar"
    level = "C"

    def make_behaviour(self) -> object:
        return Colluder(self.party)


class Shopper(Honest):
    """Calls the model up to `tries` times on its party's fixes until a call passes, and keeps that call's zkTLS
    proof: a valid receipt (nothing for a re-run to disprove), its extra calls paid by itself. On a challenge panel or
    an audit of its party's fix it shops for the verdict that upholds the pass. Elsewhere it judges honestly."""

    def __init__(self, party: str, tries: int):
        self.party, self.tries = party, tries
        self.flipped: Set[int] = set()
        self.extra_calls = 0
        self.shopped = 0

    def _shop(self, net: LevelNet, sub: Sub, v: Validator, role: int) -> bool:
        vote = net.honest_vote(sub, v, role)
        first, calls = vote, 1
        q = net.pass_prob(sub, v)
        while not vote and calls < self.tries:
            vote = D.u(net.seed, T_SHOP, sub.sid, v.vid, role, calls) < q
            calls += 1
        v.acct.overhead += (calls - 1) * net.w.usage_per_check
        self.extra_calls += calls - 1
        if role == COUNTED:
            self.shopped += 1
            if vote and not first:
                self.flipped.add(sub.sid)
        return vote

    def counted(self, net, sub, v):
        if sub.party != self.party:
            return super().counted(net, sub, v)
        if not net.online(sub, v, COUNTED):
            return Act(False, False)
        return Act(True, True, self._shop(net, sub, v, COUNTED))

    def audit(self, net, sub, v):
        if sub.party != self.party:
            return super().audit(net, sub, v)
        return Act(True, True, self._shop(net, sub, v, AUDIT))

    def challenge(self, net, ch, v):
        if ch.sub.party != self.party:
            return super().challenge(net, ch, v)
        return Act(True, True, self._shop(net, ch.sub, v, CHALLENGE), found=net.confirms(ch, v))


class AnswerShopper(_SolverActor):
    """The level C answer shopper (incentive-simulation, "Answer shopping"): its solver submits borderline bad fixes
    (an honest model call passes one with `LevelWorld.borderline_pass`), and its zkTLS validator, when drawn on them,
    calls the model up to `tries` times until one passes. Its twin: the same validator calling once; with
    `twin_submits` the twin's solver submits the same borderline fixes (so the difference is the shopping alone),
    without it no fixes (phase 1's convention)."""
    name = "level C answer shopper"
    party = "shopper"
    level = "C"
    borderline = True

    def __init__(self, honest: bool = False, where: str = "genesis", tries: int = 5,
                 borderline_pass: float = LEVEL_WORLD.borderline_pass, **kw):
        super().__init__(honest, where, **kw)
        self.tries, self.borderline_pass = tries, borderline_pass
        self.shopper = Shopper(self.party, tries)

    def level_world(self, p: Optional[Params] = None) -> LevelWorld:
        return replace(super().level_world(p), borderline_pass=self.borderline_pass)

    def make_behaviour(self) -> object:
        return self.shopper


class Breaker(Colluder):
    """A level B node whose chip is broken. It signs a pass outside the official code (a forged receipt whose tests a
    re-run doesn't reproduce) on every draw on its own party's bad fixes, and on `rate` of its counted draws on other
    bad fixes, for a bribe of `bribe_share` of the bounty paid by that fix's solver if the fix is paid. As an auditor or
    a challenge judge it defends its party's fixes (`Colluder`)."""

    def __init__(self, party: str, rate: float, bribe_share: float):
        super().__init__(party)
        self.rate, self.bribe_share = rate, bribe_share
        self.pending: List[Tuple[Sub, Validator]] = []
        self.forged = 0
        self.draws = 0
        self.bribes = 0.0
        self.paid_bounties: List[float] = []

    def counted(self, net, sub, v):
        self.draws += 1
        own = sub.party == self.party
        if not own and (sub.tier != ISSUE or sub.good or D.u(net.seed, T_BREAK, sub.sid, v.vid) >= self.rate):
            return Honest.counted(self, net, sub, v)
        if net.honest_vote(sub, v, COUNTED):
            return Act(True, True, True)  # its official check passes it anyway (an honest error)
        self.forged += 1
        net.stats["forged"] += 1
        if not own:
            self.pending.append((sub, v))
        return Act(True, True, True, faked=True)

    def settle(self) -> None:
        keep = []
        for sub, v in self.pending:
            if sub.final is None:
                keep.append((sub, v))
            elif sub.final:
                b = self.bribe_share * sub.bounty
                v.acct.gains += b
                self.bribes += b
                self.paid_bounties.append(sub.bounty)
        self.pending = keep


class ChipBreaker(_SolverActor):
    """The level B chip breaker (incentive-simulation, "A validator breaks its own chip"): a home TDX server whose
    owner spent `break_cost` on a memory-bus device (2025's attacks on TDX and SEV-SNP). Its attestation still reads
    level B, so it is drawn like any level B validator. It signs verdicts outside the official code (`Breaker`) on its
    own solver's bad fixes (at `bad_week`, within level B's limits) and on `rate` of its draws on other bad fixes, for
    `bribe_share` of the bounty when the fix is paid. Its twin: the same validator, chip intact, judging honestly, and
    no bad fixes."""
    name = "level B chip breaker"
    party = "breaker"
    level = "B"
    grown_mix = THIRDS

    def __init__(self, honest: bool = False, where: str = "genesis", rate: float = 0.5, bribe_share: float = 0.5,
                 break_cost: float = 1000.0, **kw):
        kw.setdefault("bond", 100.0 if where == "genesis" else 1250.0)
        super().__init__(honest, where, **kw)
        self.rate, self.bribe_share, self.break_cost = rate, bribe_share, break_cost
        self.breaker = Breaker(self.party, rate, bribe_share)

    def make_behaviour(self) -> object:
        return self.breaker

    def setup(self, net: Net) -> None:
        super().setup(net)
        if not self.honest:
            self.me(net).acct.overhead += self.break_cost

    def on_tick(self, net: Net) -> None:
        super().on_tick(net)
        self.breaker.settle()


# ---------- against the twin ----------

def run(actor: LevelActor, seed: int, p: Optional[Params] = None, w: Optional[World] = None,
        lw: Optional[LevelWorld] = None, rule: Callable[[Sequence[str]], str] = majority_weakest) -> LevelNet:
    p = p or actor.params()
    return LevelNet(seed, p, w or actor.world(), [actor], lw=lw or actor.level_world(p), level_rule=rule).run()


def against_twin(make: Callable[[bool], LevelActor], seeds: Sequence[int], p: Optional[Params] = None,
                 w: Optional[World] = None, lw: Optional[LevelWorld] = None,
                 rule: Callable[[Sequence[str]], str] = majority_weakest,
                 metrics: Optional[Callable[[LevelNet, LevelActor], Dict[str, float]]] = None) -> Dict[str, object]:
    """`actors.against_twin` for a `LevelNet`: the attacker's return minus its twin's on the same seeds (mean, its
    standard error, whether it loses significantly), both returns, and any `metrics` (the twin's as twin_*)."""
    diffs, att, twin, extra = [], [], [], {}
    for s in seeds:
        a, t = make(False), make(True)
        na, nt = run(a, s, p, w, lw, rule), run(t, s, p, w, lw, rule)
        ra, rt = na.party_net(a.party), nt.party_net(t.party)
        diffs.append(ra - rt)
        att.append(ra)
        twin.append(rt)
        if metrics:
            for k, v in metrics(na, a).items():
                extra.setdefault(k, []).append(v)
            for k, v in metrics(nt, t).items():
                extra.setdefault(f"twin_{k}", []).append(v)
    m, se = mean(diffs), _se(diffs)
    return {"diff": m, "se": se, "loses": m + 2 * se < 0, "attacker": mean(att), "twin": mean(twin),
            "diffs": diffs, **{k: mean(v) for k, v in extra.items()}}


def attack_metrics(net: LevelNet, a: LevelActor) -> Dict[str, float]:
    """What each proof-level attacker got, and how often it was caught."""
    pa = net.parties.get(a.party)
    nodes = net.party_validators(a.party)
    me = nodes[0] if nodes else None
    mine = [s for s in net.subs.values() if s.party == a.party]
    judged = [s for s in mine if s.judges]
    by_me = [s for s in net.subs.values() if me is not None and any(vid == me.vid for vid, _, _ in s.judges)]
    agree = [s for s in by_me if s.final is not None]
    m = {"submitted": pa.submitted if pa else 0, "bad_paid": pa.bad_paid if pa else 0,
         "judged": len(judged), "slashed": sum(v.acct.slashed for v in nodes),
         "caught": net.stats["receipts_upheld"], "faked": sum(1 for s in mine for vid, _, f in s.judges
                                                              if f and me is not None and vid == me.vid),
         "reversed": sum(1 for s in mine if s.reversed),
         "challenged": sum(1 for s in mine if s.challenge is not None),
         "frozen": sum(1 for s in mine if s.challenge is not None and s.challenge.state == "waiting"),
         "max_paid": max([s.bounty for s in mine if s.final], default=0.0),
         "agreement": (sum(1 for s in agree if dict((vid, vote) for vid, vote, _ in s.judges)[me.vid] == s.final)
                       / len(agree)) if agree else 1.0,
         "levels_c": sum(1 for s in judged if s.level == "C"), "qualified": net.stats["qualified"],
         "checks": me.acct.checks if me else 0}
    if isinstance(a, ChipBreaker):
        b = a.breaker
        m.update(forged=b.forged, draws=b.draws, bribes=b.bribes, caught_forged=net.stats["receipts_upheld"],
                 max_paid=max([m["max_paid"]] + b.paid_bounties), paid_forged=len(b.paid_bounties))
    if isinstance(a, AnswerShopper):
        sh = a.shopper
        flipped = [net.subs[sid] for sid in sh.flipped]
        m.update(shopped=sh.shopped, flips=len(flipped),
                 outweighed=sum(1 for s in flipped if s.verdict is False),
                 flip_reversed=sum(1 for s in flipped if s.reversed),
                 flip_paid=sum(1 for s in flipped if s.final), extra_calls=sh.extra_calls)
    return m


# ---------- the report's tables ----------

def _ms(xs: Sequence[float], nd: int = 1) -> str:
    return f"{mean(xs):,.{nd}f} ± {2 * _se(xs):,.{nd}f}"


def _pct(xs: Sequence[float]) -> str:
    return f"{100 * mean(xs):.0f} % ± {200 * _se(xs):.0f}"


def _verdict(m: float, se: float) -> str:
    if m + 2 * se < 0:
        return "loses"
    if m - 2 * se > 0:
        return "**wins**"
    return "not significant"


MATURE = replace(WORLD, initial_active=20, joins_week=0.5)
NETWORKS: List[Tuple[str, World, LevelWorld]] = [
    ("Growth, all level A (phase 1's assumption)", WORLD, replace(LEVEL_WORLD, mix=(1.0, 0.0, 0.0))),
    ("Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C", WORLD, LEVEL_WORLD),
    ("Growth, the same with 10 % hidden-test bounties", WORLD, replace(LEVEL_WORLD, hidden_share=0.1)),
    ("Growth, ordinary PCs only (genesis and newcomers at C)", WORLD,
     replace(LEVEL_WORLD, mix=(0.0, 0.0, 1.0), genesis_level="C")),
    ("Grown: 21 active, ⅓ A, ⅓ B, ⅓ C", MATURE, LEVEL_WORLD),
    ("Grown, the same with 10 % hidden-test bounties", MATURE, replace(LEVEL_WORLD, hidden_share=0.1)),
    ("Grown: 21 active, all at C", MATURE, replace(LEVEL_WORLD, mix=(0.0, 0.0, 1.0), genesis_level="C")),
]


def networks(seeds: Sequence[int], rows=None, p: Optional[Params] = None) -> List[Tuple[str, Dict[str, list]]]:
    out = []
    for name, w, lw in (rows if rows is not None else NETWORKS):
        ms: Dict[str, list] = defaultdict(list)
        for s in seeds:
            n = LevelNet(s, p or PARAMS, w, (), lw=lw).run()
            st = n.stats
            issue = [x for x in n.subs.values() if x.tier == ISSUE]
            drawn = [x for x in issue if x.draw is not None]
            ms["waited"].append(st["waited"] / max(1, st["submitted"]))
            ms["withdrawn"].append(st["withdrawn"] / max(1, st["submitted"]))
            ms["days"].append(st["final_days"] / max(1, st["final"]))
            ms["bad"].append(100 * st["bad_merged"] / max(1, st["paid"]))
            ms["level_wait"].append(sum(1 for x in issue if "the panel's proof level" in n.reasons[x.sid])
                                    / max(1, len(issue)))
            ms["drawn"].append(len(drawn))
            for lv in LEVELS:
                if drawn:  # shares among the runs that drew any panel
                    ms[f"lv{lv}"].append(sum(1 for x in drawn if x.level == lv) / len(drawn))
                fin = [x for x in drawn if x.level == lv and x.final is not None]
                if fin:
                    ms[f"days{lv}"].append(mean((x.final_t - x.t) / DAY for x in fin))
            ms["max_bounty"].append(n.series[-1]["max_bounty"] if n.series else 0.0)
            ms["active"].append(n.series[-1]["active"] if n.series else 0.0)
            hid = [x for x in issue if x.sid in n.hidden]
            if hid:
                ms["hidden_waited"].append(sum(1 for x in hid if x.waited) / len(hid))
                ms["hidden_withdrawn"].append(sum(1 for x in hid if x.state == "withdrawn") / len(hid))
                ms["hidden_c_seen"].append(sum(
                    1 for x in hid if (x.draw is not None and any(n.reg.validators[v].level == "C"
                                                                  for v in x.draw.drawn))
                    or any(n.reg.validators[v].level == "C" for v, _, _ in x.shadows)))
        out.append((name, ms))
    return out


def networks_table(seeds: Sequence[int]) -> str:
    out = [f"### Panels by proof level ({len(seeds)} seeds; a year; 30 submissions a week)", "",
           "| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C | "
           "Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | "
           "Active at year's end |", "|---|---|---|---|---|---|---|---|---|---|"]
    hidden_rows = []
    for name, ms in networks(seeds):
        lv = " / ".join(f"{100 * mean(ms[f'lv{x}']):.0f} %" for x in LEVELS) if ms.get("lvA") else "–"
        days = " / ".join(f"{mean(ms[f'days{x}']):.1f}" if ms.get(f"days{x}") else "–" for x in LEVELS)
        out.append(f"| {name} | {_pct(ms['waited'])} | {_pct(ms['withdrawn'])} | {_pct(ms['level_wait'])} | {_ms(ms['drawn'], 0)} | {lv} | "
                   f"{days} | {_ms(ms['bad'], 2)} | ${mean(ms['max_bounty']):,.0f} | {_ms(ms['active'])} |")
        if ms.get("hidden_waited"):
            hidden_rows.append(f"| {name} | {_pct(ms['hidden_waited'])} | {_pct(ms['hidden_withdrawn'])} | "
                               f"{sum(ms['hidden_c_seen']):g} |")
    out += ["", "| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, "
            "replacement or shadow; all runs) |", "|---|---|---|---|"] + hidden_rows
    return "\n".join(out)


FULL_BOND = replace(PARAMS, FALSE_VERDICT_SLASH_BPS=10_000)
ALL_A = PHASE1_LEVEL  # the counterfactual without levels: every panel judged with level A's limits and windows

ATTACKERS: List[Tuple[str, Callable[[bool], LevelActor], Optional[Params], Callable, str]] = [
    ("Test liar: the genesis at C ($10 at k = 1, 7-day window), 5 bad fixes a week", lambda h: TestLiar(h),
     None, majority_weakest, "liar"),
    ("Test liar: the same without levels (A's $50 and 72 h)", lambda h: TestLiar(h), None, ALL_A, "liar"),
    ("Test liar: 1 of 15 validators, all at C; 2 bad fixes a week", lambda h: TestLiar(h, "grown"), None,
     majority_weakest, "liar"),
    ("Test liar: the same, whole bond slashed per false verdict", lambda h: TestLiar(h, "grown"), FULL_BOND,
     majority_weakest, "liar"),
    ("Answer shopper: the genesis at C, 5 borderline fixes a week (twin: calls once, same fixes)",
     lambda h: AnswerShopper(h, twin_submits=True), None, majority_weakest, "shopper"),
    ("Answer shopper: the same (twin: no fixes)", lambda h: AnswerShopper(h), None, majority_weakest, "shopper"),
    ("Answer shopper: the same without levels (A's $50 and 72 h; twin: no fixes)", lambda h: AnswerShopper(h),
     None, ALL_A, "shopper"),
    ("Answer shopper: 1 of 15 validators, all at C (twin: calls once, same fixes)",
     lambda h: AnswerShopper(h, "grown", twin_submits=True), None, majority_weakest, "shopper"),
    ("Answer shopper: the same (twin: no fixes)", lambda h: AnswerShopper(h, "grown"), None, majority_weakest,
     "shopper"),
    ("Answer shopper: the same, fixes an honest call passes 1 time in 10, not 3 (twin: calls once, same fixes)",
     lambda h: AnswerShopper(h, "grown", borderline_pass=0.1, twin_submits=True), None, majority_weakest,
     "shopper"),
    ("Chip breaker: the genesis at B ($25 at k = 1, 144 h), forging on half its bad-fix draws, $1,000 device",
     lambda h: ChipBreaker(h), None, majority_weakest, "breaker"),
    ("Chip breaker: the same, a $50 device", lambda h: ChipBreaker(h, break_cost=50.0), None, majority_weakest,
     "breaker"),
    ("Chip breaker: the same ($50) without levels (A's $50 and 72 h)", lambda h: ChipBreaker(h, break_cost=50.0),
     None, ALL_A, "breaker"),
    ("Chip breaker: 1 of 15 validators (⅓ A, ⅓ B, ⅓ C), a $50 device", lambda h: ChipBreaker(h, "grown",
                                                                                            break_cost=50.0),
     None, majority_weakest, "breaker"),
    ("Chip breaker: the same, forging on every bad-fix draw", lambda h: ChipBreaker(h, "grown", rate=1.0,
                                                                                   break_cost=50.0),
     None, majority_weakest, "breaker"),
]


def _got(kind: str, r: Dict[str, object]) -> str:
    if kind == "liar":
        caught = r["caught"] / r["faked"] if r["faked"] else 0.0
        return (f"{r['bad_paid']:.1f} bad fixes paid of {r['submitted']:.0f} (largest ${r['max_paid']:.0f}); "
                f"{r['faked']:.1f} lies: {r['challenged']:.1f} challenged, {r['caught']:.1f} proven by re-runs "
                f"({100 * caught:.0f} %), {r['reversed']:.1f} reversed, {r['frozen']:.1f} still frozen at year's end; "
                f"slashed ${r['slashed']:.0f}")
    if kind == "shopper":
        return (f"{r['flips']:.1f} verdicts flipped of {r['shopped']:.1f} shopped ({r['extra_calls']:.0f} extra "
                f"calls); outweighed by the other judges {r['outweighed']:.1f}, reversed {r['flip_reversed']:.1f}, "
                f"paid {r['flip_paid']:.1f}; bad fixes paid {r['bad_paid']:.1f} of {r['submitted']:.0f} (twin "
                f"{r['twin_bad_paid']:.1f}); agreement with final outcomes {100 * r['agreement']:.1f} % (twin "
                f"{100 * r['twin_agreement']:.1f} %)")
    if kind == "breaker":
        caught = r["caught_forged"] / r["forged"] if r["forged"] else 0.0
        return (f"{r['forged']:.1f} forged of {r['draws']:.0f} draws ({100 * r['forged'] / max(1, r['draws']):.0f} "
                f"%); own bad fixes paid {r['bad_paid']:.1f} of {r['submitted']:.0f}, bribed ones {r['paid_forged']:.1f} "
                f"(bribes ${r['bribes']:.0f}); largest bounty paid ${r['max_paid']:.0f}; {r['challenged']:.1f} "
                f"challenged, {100 * caught:.0f} % of forgeries proven by re-runs, {r['frozen']:.1f} still frozen; "
                f"slashed ${r['slashed']:.0f}")
    return ""


def attackers(seeds: Sequence[int], rows=None):
    return [(name, against_twin(make, seeds, p=p, rule=rule, metrics=attack_metrics), kind)
            for name, make, p, rule, kind in (rows if rows is not None else ATTACKERS)]


def attackers_table(seeds: Sequence[int], data=None) -> str:
    out = [f"### Each proof-level attacker against its honest twin ({len(seeds)} seeds; a year; returns in $, with "
           "bonds' capital, running costs, fees, slashes, extra model calls, attempt fees and checks counted)", "",
           "| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | "
           "What it got |", "|---|---|---|---|---|---|"]
    for name, r, kind in (data if data is not None else attackers(seeds)):
        out.append(f"| {name} | {r['diff']:,.0f} ± {2 * r['se']:,.0f} | {_verdict(r['diff'], r['se'])} | "
                   f"{r['attacker']:,.0f} | {r['twin']:,.0f} | {_got(kind, r)} |")
    return "\n".join(out)


def levels_report(seeds: Sequence[int]) -> str:
    return "\n\n".join([networks_table(seeds), attackers_table(seeds)])
