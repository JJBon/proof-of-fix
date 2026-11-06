"""The open-validator attackers (#132 specs/incentive-simulation, "Open-validator attackers"; #134 task 1.3) and
D13's cheater (task 1.6), each run alone against its honest twin on the same seeds, like v2's `against_twin`
(pof/sim/oraclenet.py).

An `Actor` sets itself up in a `Net` (validators it controls, submissions it makes) and acts on each daily tick.
`honest=True` builds its twin: the same actor behaving honestly, on the same seeds, so the same honest submissions,
joins and votes. Its return is `Net.party_net(party)`: the fees and rewards of its validators, plus what its
submissions were paid, less every running cost, slash, attempt fee and check charge, and the bonds' capital cost.

Phase 1 treats every validator as level A and pays a flat service fee, so a false verdict here is the generic one:
a counted verdict its node's check didn't produce, with a fabricated receipt that a re-run (an audit, a volunteer, a
challenge panel's judge) shows with `World.rerun_detect`. Phase 2 adds the level-specific attackers (the level C
test liar and answer shopper, the level B chip breaker) and the pricing attackers.
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from statistics import mean
from typing import Callable, Dict, List, Optional, Sequence

from . import panels as D
from .net import COUNTED, CONSTITUTION, ISSUE, Act, Honest, Net, Sub
from .params import PARAMS, WEEK, WORLD, Params, World
from .registry import Validator


def _se(xs: Sequence[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5 / len(xs) ** 0.5


# ---------- behaviours ----------

class Colluder(Honest):
    """Passes its own party's fixes and ADRs whatever its check finds (with a fabricated receipt when the check
    disagrees). As an auditor or a challenge judge on its party's submission it defends the verdict; everywhere else
    it judges honestly (it must keep qualifying and keep its reveal rate)."""

    def __init__(self, party: str):
        self.party = party

    def counted(self, net: Net, sub: Sub, v: Validator) -> Act:
        if sub.party != self.party:
            return super().counted(net, sub, v)
        return Act(True, True, True, faked=not net.honest_vote(sub, v, COUNTED))

    def audit(self, net: Net, sub: Sub, v: Validator) -> Act:
        if sub.party != self.party:
            return super().audit(net, sub, v)
        return Act(True, True, bool(sub.verdict))

    def challenge(self, net: Net, ch, v: Validator) -> Act:
        if ch.sub.party != self.party:
            return super().challenge(net, ch, v)
        return Act(True, True, bool(ch.sub.verdict))


class Silent(Honest):
    """Bribed on `rate` of its counted draws to stay silent (it never seals), for `stall_value` of the bounty: v2's
    non-revealer, now hoping the panel shrinks. It doesn't: the next validator of the sample replaces it. `sealed`
    (#141, D16): it seals, sees the others' reveals, then withholds its own (a sealed vote not revealed, slashed
    SEALED_NO_REVEAL_SLASH), instead of never sealing (silence, SILENCE_SLASH)."""

    def __init__(self, rate: float, stall_value: float, sealed: bool = False):
        self.rate, self.stall_value, self.sealed = rate, stall_value, sealed

    def counted(self, net: Net, sub: Sub, v: Validator) -> Act:
        if sub.tier == ISSUE and D.u(net.seed, D.T_BRIBE, sub.sid, v.vid) < self.rate:
            v.acct.gains += self.stall_value * sub.bounty
            net.stats["silences"] += 1
            return Act(False, self.sealed)
        return super().counted(net, sub, v)


class Cheater(Honest):
    """D13's rare cheater: on `rate` of its counted draws it signs a verdict its check didn't produce.
    - "lazy": skips the check, votes pass, and keeps what the check would have cost it (the metered usage, repaid
      anyway, and its node's overhead);
    - "bribed": on a bad fix, votes pass for a bribe of `bribe` dollars, paid whatever the outcome."""

    def __init__(self, kind: str = "lazy", rate: float = 0.1, bribe: float = 5.0):
        if kind not in ("lazy", "bribed"):
            raise ValueError(kind)
        self.kind, self.rate, self.bribe = kind, rate, bribe

    def counted(self, net: Net, sub: Sub, v: Validator) -> Act:
        if sub.tier != ISSUE or D.u(net.seed, D.T_CHEAT, sub.sid, v.vid) >= self.rate:
            return super().counted(net, sub, v)
        if self.kind == "lazy":
            v.acct.gains += net.w.usage_per_check + net.w.enclave.per_check
            net.stats["cheats"] += 1
            return Act(True, True, True, faked=True)
        if sub.good:
            return super().counted(net, sub, v)
        honest = net.honest_vote(sub, v, COUNTED)
        v.acct.gains += self.bribe
        net.stats["cheats"] += not honest
        return Act(True, True, True, faked=not honest)


# ---------- actors ----------

class Actor:
    """One attacker (or, with honest=True, its twin) in a network."""
    name = "actor"
    party = "attacker"

    def __init__(self, honest: bool = False):
        self.honest = honest

    def world(self) -> World:
        return WORLD

    def params(self) -> Params:
        return PARAMS

    def genesis(self, net: Net) -> Optional[dict]:
        return None

    def setup(self, net: Net) -> None:
        pass

    def on_tick(self, net: Net) -> None:
        pass

    def withdraws(self, net: Net, sub: Sub) -> bool:
        return True

    def behaviour(self, b: object) -> object:
        return None if self.honest else b

    def nodes(self, net: Net) -> List[Validator]:
        return net.party_validators(self.party)


def _bounties(net: Net, rng: random.Random, n: int, cap: float) -> List[float]:
    """Bounties an attacker targets: the world's distribution, below `cap` (resampled, then clipped)."""
    w = net.w
    mu, sigma = math.log(w.bounty_median), math.log(w.bounty_p90 / w.bounty_median) / 1.2815515655446004
    out = []
    for _ in range(n):
        b = rng.lognormvariate(mu, sigma)
        for _ in range(20):
            if b <= cap:
                break
            b = rng.lognormvariate(mu, sigma)
        out.append(round(min(b, cap), 2))
    return out


class Sybil(Actor):
    """One party running many validators under different declared operators (the operator cap is a disclosure),
    spread over `hosts` hosts, `tees` TEE types and `families` model families. Its solver submits bad fixes at
    `bad_week` from `start_week`; its validators pass them when drawn, and defend them on audits and challenge
    panels. Its twin: the same validators judging honestly, and no bad fixes. Base world: a grown network of
    `honest_nodes` honest validators (already qualified, like the sybil's), joins at half a validator a week."""
    name = "sybil"
    party = "sybil"

    def __init__(self, honest: bool = False, nodes: int = 10, hosts: int = 3, tees: int = 3, families: int = 3,
                 honest_nodes: int = 20, bad_week: float = 2.0, start_week: int = 4, bond: float = 1250.0):
        super().__init__(honest)
        self.n, self.hosts, self.tees, self.families = nodes, hosts, tees, families
        self.honest_nodes, self.bad_week, self.start_week, self.bond = honest_nodes, bad_week, start_week, bond

    def world(self) -> World:
        return replace(WORLD, initial_active=self.honest_nodes, joins_week=0.5)

    def setup(self, net: Net) -> None:
        w = net.w
        for i in range(self.n):
            net.register_actor(i, self.party, self.bond, w.hosts[i % self.hosts], w.tees[i % self.tees],
                               w.families[i % self.families], f"sybil-op-{i}", self.behaviour(Colluder(self.party)),
                               active=True)
        if self.honest:
            return
        rng = random.Random(D.h(net.seed, D.T_GRIND, 1))
        t = self.start_week * WEEK
        times = []
        while True:
            t += rng.expovariate(self.bad_week / WEEK)
            if t > w.horizon_h:
                break
            times.append(t)
        for t, b in zip(times, _bounties(net, rng, len(times), self.bond / net.p.BOND_FACTOR)):
            net.submit(t, b, False, "sybil-solver", self.party)


class LoneColluder(Actor):
    """The genesis validator, bonded at `bond` (the floor covers k = 1's largest bounty), colluding with a solver:
    while the network allows only k = 1 for small bounties, the solver submits bad fixes to bounties up to k = 1's
    limit at `bad_week`, and the validator passes them. Its twin: the same genesis judging honestly, and no bad
    fixes. Base world: growth from one validator."""
    name = "lone colluder"
    party = "colluder"

    def __init__(self, honest: bool = False, bad_week: float = 5.0, bond: float = 100.0):
        super().__init__(honest)
        self.bad_week, self.bond = bad_week, bond

    def genesis(self, net: Net) -> Optional[dict]:
        w = net.w
        return dict(key="colluder", signer="colluder", bond=self.bond, proof=w.tees[0], host=w.hosts[0],
                    family=w.families[0], operator="colluder-op", party=self.party,
                    behaviour=self.behaviour(Colluder(self.party)))

    def setup(self, net: Net) -> None:
        self.rng = random.Random(D.h(net.seed, D.T_GRIND, 2))

    def on_tick(self, net: Net) -> None:
        if self.honest:
            return
        n = self.rng.random() < self.bad_week / 7  # at most one a day
        lim = net.p.limit(1)
        if n and net.p.k_for(len(net.reg.eligible(lim))) == 1 and net.reg.drawable(self.nodes(net)[0]):
            net.submit(net.t, round(lim * (0.4 + 0.6 * self.rng.random()), 2), False, "colluder-solver", self.party)


class SeedGrinder(Actor):
    """A solver with one hidden, already qualified validator (declared under another operator, so it isn't
    recused). While small
    bounties are judged by k = 1, it submits a bad fix to a bounty up to k = 1's limit once a day, hoping its own
    validator is the one drawn; every attempt pays the attempt fee and the checks. With the counterfactual seed fixed
    at the seal (Params.SEED_FROM_LATER_BLOCK = False), it first tries `grind` commitments offline and submits only
    one that draws its own validator. `declared=True` discloses the validator as the solver's (it is then recused).
    Its twin: the same validator judging honestly, and no bad fixes. Base world: growth from one validator."""
    name = "seed grinder"
    party = "grinder"

    def __init__(self, honest: bool = False, bond: float = 100.0, grind: int = 64, declared: bool = False):
        super().__init__(honest)
        self.bond, self.grind, self.declared = bond, grind, declared

    def setup(self, net: Net) -> None:
        w = net.w
        op = "grinder-solver" if self.declared else "grinder-op"
        net.register_actor(0, self.party, self.bond, w.hosts[1], w.tees[1], w.families[1], op,
                           self.behaviour(Colluder(self.party)), active=True)
        self.rng = random.Random(D.h(net.seed, D.T_GRIND, 3))
        self.day = 0

    def on_tick(self, net: Net) -> None:
        self.day += 1
        if self.honest:
            return
        me = self.nodes(net)[0]
        lim = net.p.limit(1)
        if not net.reg.drawable(me) or net.p.k_for(len(net.reg.eligible(lim))) != 1:
            return
        bounty = round(lim * (0.4 + 0.6 * self.rng.random()), 2)
        commitment = D.h(net.seed, D.T_GRIND, 4, self.day)
        if not net.p.SEED_FROM_LATER_BLOCK:  # the seed is known at the seal: grind it offline, for free
            for j in range(self.grind):
                c = D.h(net.seed, D.T_GRIND, 4, self.day, j)
                probe = Sub(net._sid, net.t, bounty, False, "grinder-solver", frozenset(("grinder-solver",)),
                            party=self.party, commitment=c)
                k, d, _ = net.plan(probe)
                if d is not None and d.panel == [me.vid]:
                    commitment = c
                    break
            else:
                return
        net.submit(net.t, bounty, False, "grinder-solver", self.party, commitment=commitment)


class SilentJudge(Actor):
    """A validator bribed on `rate` of its counted draws to stay silent, for `stall_value` of the bounty (v2's
    assumption). `sealed`: it seals and withholds instead (D16's sealed vote not revealed). Its twin: the same
    validator never bribed. Base world: a grown network of `honest_nodes` validators, no joins."""
    name = "silent judge"
    party = "silent"

    def __init__(self, honest: bool = False, rate: float = 0.1, stall_value: float = 0.05, honest_nodes: int = 12,
                 bond: float = 1250.0, sealed: bool = False):
        super().__init__(honest)
        self.rate, self.stall_value, self.honest_nodes, self.bond = rate, stall_value, honest_nodes, bond
        self.sealed = sealed

    def world(self) -> World:
        return replace(WORLD, initial_active=self.honest_nodes, joins_week=0.0)

    def setup(self, net: Net) -> None:
        w = net.w
        net.register_actor(0, self.party, self.bond, w.hosts[2], w.tees[2], w.families[2], "silent-op",
                           self.behaviour(Silent(self.rate, self.stall_value, self.sealed)), active=True)


class FeeFarmer(Actor):
    """A party registering `nodes` idle validators at `bond` (the floor by default: the cheapest per node), under
    different declared operators, to take a larger share of the checks. They judge honestly (phase 1's fee is flat;
    task 1.4 re-runs it with the queue-driven fee, which idle validators push down). Its twin: the same party running
    one node. Base world: `honest_nodes` qualified validators and newcomers at a validator a week."""
    name = "fee farmer"
    party = "farmer"

    def __init__(self, honest: bool = False, nodes: int = 10, bond: float = 100.0, honest_nodes: int = 8):
        super().__init__(honest)
        self.n, self.bond, self.honest_nodes = nodes, bond, honest_nodes

    def world(self) -> World:
        return replace(WORLD, initial_active=self.honest_nodes)

    def setup(self, net: Net) -> None:
        w = net.w
        for i in range(1 if self.honest else self.n):
            net.register_actor(i, self.party, self.bond, w.hosts[i % len(w.hosts)], w.tees[i % len(w.tees)],
                               w.families[i % len(w.families)], f"farmer-op-{i}", None)


class ConstitutionCoalition(Actor):
    """A coalition registering `nodes` validators early (diversified, so the caps don't bind) and submitting ADRs
    worth `value` to it at `adrs_week` from the start, while the network is small. Its validators pass its ADRs.
    Its twin: the same validators judging honestly, and no ADRs. Base world: growth from one validator.
    `kind` "escalated" (round 2): it sends the same rule changes as escalated fixes to issues it funds itself (the
    constitution tier from CONSTITUTION_MIN_ELIGIBLE, with ADR_DEPOSIT; a rejected one's deposit goes to the sponsors'
    pool, or, under the rejected alternative DEPOSIT_FORFEIT_TO "funder", back to it as the issue's funder)."""
    name = "constitution coalition"
    party = "coalition"

    def __init__(self, honest: bool = False, nodes: int = 5, adrs_week: float = 1.0, value: float = 1000.0,
                 bond: float = 250.0, kind: str = "adr"):
        super().__init__(honest)
        if kind not in ("adr", "escalated"):
            raise ValueError(kind)
        self.n, self.adrs_week, self.value, self.bond, self.kind = nodes, adrs_week, value, bond, kind

    def setup(self, net: Net) -> None:
        w = net.w
        for i in range(self.n):
            net.register_actor(i, self.party, self.bond, w.hosts[(i + 1) % len(w.hosts)],
                               w.tees[(i + 1) % len(w.tees)], w.families[(i + 1) % len(w.families)],
                               f"coalition-op-{i}", self.behaviour(Colluder(self.party)))
        if self.honest:
            return
        rng = random.Random(D.h(net.seed, D.T_GRIND, 5))
        t = 0.0
        while True:
            t += rng.expovariate(self.adrs_week / WEEK)
            if t > w.horizon_h:
                break
            sub = net.submit(t, 0.0, False, "coalition-solver", self.party, tier=CONSTITUTION, value=self.value)
            if self.kind == "escalated":
                sub.escalated, sub.funder_party = True, self.party


class RemovalCoalition(Actor):
    """Round 2's coalition of removals (incentive-simulation, "A coalition of removals"): `nodes` validators
    registered at the start on every accepted TEE type but its target (spread over hosts and families, so the caps
    don't bind), submitting each week an ADR that only removes the target: the TEE type most other validators use
    (`target`, or the world's commonest by its spread, `World.tee_weights`; the first type when even). A removal is
    drawn from REMOVAL_MIN_ELIGIBLE and takes effect REMOVAL_WINDOW_H after it passes; then the target's validators
    stop being drawn, and the coalition's draw more. Its validators pass its removals. `value`: what a passed removal
    is worth to it beyond those fees (0: the fees alone; the sensitivity row sets $1,000, as an adding ADR). It stops
    once the target is removed. Its twin: the same validators judging honestly, and no ADRs. Base world: growth from
    one validator."""
    name = "coalition of removals"
    party = "removers"

    def __init__(self, honest: bool = False, nodes: int = 5, adrs_week: float = 1.0, value: float = 0.0,
                 bond: float = 250.0, target: Optional[str] = None):
        super().__init__(honest)
        self.n, self.adrs_week, self.value, self.bond, self.target = nodes, adrs_week, value, bond, target

    def pick_target(self, w: World) -> str:
        if self.target is not None:
            return self.target
        if w.tee_weights:
            return max(zip(w.tees, w.tee_weights), key=lambda x: x[1])[0]
        return w.tees[0]

    def setup(self, net: Net) -> None:
        w = net.w
        self.tgt = self.pick_target(w)
        own = [x for x in w.tees if x != self.tgt]
        for i in range(self.n):
            net.register_actor(i, self.party, self.bond, w.hosts[(i + 1) % len(w.hosts)], own[i % len(own)],
                               w.families[(i + 1) % len(w.families)], f"remover-op-{i}",
                               self.behaviour(Colluder(self.party)))
        if self.honest:
            return
        rng = random.Random(D.h(net.seed, D.T_GRIND, 6))
        t = 0.0
        while True:
            t += rng.expovariate(self.adrs_week / WEEK)
            if t > w.horizon_h:
                break
            net._at(t, self._submit, net)

    def _submit(self, net: Net) -> None:
        if self.tgt in net.tee_list:  # once it is removed, there is nothing left to take
            sub = net.submit(net.t, 0.0, False, "remover-solver", self.party, tier=CONSTITUTION, value=self.value)
            sub.removal = self.tgt


class WatchedCheater(Actor):
    """D13's watcher's dilemma: one already-qualified validator cheating on `rate` of its draws (`Cheater`), in a
    grown network of `honest_nodes` with no joins. Its twin: the same validator never cheating."""
    name = "cheater"
    party = "cheater"

    def __init__(self, honest: bool = False, kind: str = "lazy", rate: float = 0.1, bribe: float = 5.0,
                 honest_nodes: int = 15, volunteers: bool = True, bond: float = 1250.0):
        super().__init__(honest)
        self.kind, self.rate, self.bribe, self.honest_nodes = kind, rate, bribe, honest_nodes
        self.volunteers, self.bond = volunteers, bond

    def world(self) -> World:
        w = replace(WORLD, initial_active=self.honest_nodes, joins_week=0.0)
        return w if self.volunteers else replace(w, volunteer_per_day=0.0)

    def setup(self, net: Net) -> None:
        w = net.w
        net.register_actor(0, self.party, self.bond, w.hosts[3], w.tees[0], w.families[3], "cheater-op",
                           self.behaviour(Cheater(self.kind, self.rate, self.bribe)), active=True)


# ---------- against the twin ----------

def run(actor: Actor, seed: int, p: Optional[Params] = None, w: Optional[World] = None) -> Net:
    return Net(seed, p or actor.params(), w or actor.world(), [actor]).run()


def against_twin(make: Callable[[bool], Actor], seeds: Sequence[int], p: Optional[Params] = None,
                 w: Optional[World] = None, metrics: Optional[Callable[[Net, Actor], Dict[str, float]]] = None
                 ) -> Dict[str, object]:
    """The attacker's return minus its honest twin's on the same seeds: the mean, its standard error, whether it
    loses significantly (mean + 2 SE below zero), both returns, and any `metrics` of the attacker's runs (and, as
    twin_*, of its twin's), averaged."""
    diffs, att, twin, extra = [], [], [], {}
    for s in seeds:
        a, t = make(False), make(True)
        na, nt = run(a, s, p, w), run(t, s, p, w)
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
