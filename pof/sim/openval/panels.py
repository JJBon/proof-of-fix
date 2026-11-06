"""The draw (#132 specs/judge-panels; design D2, D3, D4, D6, D7, D13), as pure functions of a seed and a registry
snapshot, so anyone can recompute a panel (the spec's "Recomputing a panel"):

- the seed: keccak(blockhash(sealBlock + SEED_DELAY), commitment, bounty, submission id), modelled by a 64-bit mix
  (`h`): the block's hash is a function of the run's seed and the block number, unknown to a solver when it seals;
- k: the largest odd number <= min(eligible, K_MAX), within the k table's bounty limit (the caller checks the limit);
- the panel: rejection sampling, index = h(seed, counter) mod n over the snapshot, skipping duplicates and cap
  violations (operator 1 per panel; host, TEE type and model family at most (k - 1) / 2), DRAW_TRIES x k tries
  before k steps down by 2, continuing the same sample;
- replacement of a silent judge: the next validator of the same sample that is still eligible and fits the caps;
- shadows (D5), the auditor (D13), the challenge panel (D4) and the constitution tier (D7) from the same seed with
  their own counters.

The hash is a stand-in for keccak (splitmix64's finalizer): the simulation needs uniform, reproducible, seed-bound
draws, not collision resistance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .params import Params
from .registry import Validator

_M64 = (1 << 64) - 1

# stream tags: each use of randomness has its own, so an actor's choices never shift anyone else's draws
(T_BLOCK, T_SEED, T_PANEL, T_SHADOW, T_AUDIT, T_AUDITOR, T_CHALLENGE, T_VOTE, T_REVEAL, T_DETECT, T_VOLUNTEER,
 T_ARRIVALS, T_JOINS, T_BRIBE, T_CHEAT, T_GRIND) = range(1, 17)
T_WAIT_SHADOW, T_OUTAGE = 17, 18  # #141: shadows of a waiting submission; whether an honest outage struck after the seal

BLOCKS_PER_HOUR = 1800  # a 2-second L2 block (assumption; only the seed's block number reads it)
BLOCKHASH_RANGE = 256  # D3: the draw must happen within 256 blocks of the seed's block, or it re-targets


def _mix(x: int) -> int:
    x = (x + 0x9E3779B97F4A7C15) & _M64
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & _M64
    return x ^ (x >> 31)


def h(*keys: int) -> int:
    """A 64-bit hash of integers: the model of keccak over the draw's inputs."""
    x = 0x243F6A8885A308D3
    for k in keys:
        x = _mix(x ^ (k & _M64))
    return x


def u(*keys: int) -> float:
    """A uniform number in [0, 1) bound to its keys."""
    return (h(*keys) >> 11) / float(1 << 53)


def block_at(t: float) -> int:
    return int(t * BLOCKS_PER_HOUR)


def blockhash(world_seed: int, block: int) -> int:
    return h(T_BLOCK, world_seed, block)


def draw_seed(p: Params, world_seed: int, seal_block: int, commitment: int, bounty: float, sid: int) -> int:
    """D3. With SEED_FROM_LATER_BLOCK (v3), the hash of block sealBlock + SEED_DELAY, which doesn't exist when the
    solver seals; without it (the counterfactual), only what the solver chose."""
    cents = int(round(bounty * 100))
    if p.SEED_FROM_LATER_BLOCK:
        return h(T_SEED, blockhash(world_seed, seal_block + p.SEED_DELAY), commitment, cents, sid)
    return h(T_SEED, commitment, cents, sid)


@dataclass
class Draw:
    """A recorded draw: the seed, the registry epoch and snapshot it used, k, the panel in order, and where the
    sample stopped (replacements continue from there)."""
    seed: int
    epoch: int
    pool: Tuple[int, ...]
    k: int = 0
    panel: List[int] = field(default_factory=list)
    k0: int = 0  # the k it started from (k < k0: the caps, or DRAW_TRIES, stepped it down)
    counter: int = 0
    tag: int = T_PANEL
    drawn: Set[int] = field(default_factory=set)  # everyone ever seated, replaced ones included

    @property
    def filled(self) -> bool:
        return self.k > 0


def fits(members: Sequence[Validator], c: Validator, k: int, p: Params) -> bool:
    """D6: may `c` join `members` in a panel of k? One per declared operator; at most (k - 1) / 2 per host and model
    family, and per TEE type (TEE validators only) from k = TEE_CAP_FROM_K; no limit at k = 1."""
    cap, tcap = p.cap(k), p.tee_cap(k)
    nh = nt = nf = 0
    for m in members:
        if m.operator == c.operator or m.vid == c.vid:
            return False
        nh += m.host == c.host
        nf += m.family == c.family
        nt += c.tee != "none" and m.tee == c.tee
    return nh < cap and nt < tcap and nf < cap


def draw(seed: int, pool: Sequence[Validator], k0: int, p: Params, tag: int = T_PANEL, exact: bool = False,
         epoch: int = 0) -> Draw:
    """D2's rejection sampling under the caps, from k0 down by 2 (unless `exact`: then k0 or nothing). Each k gets
    DRAW_TRIES x k tries; stepping down keeps the panel's members that still fit the tighter caps, in order, and
    continues the same sample."""
    d = Draw(seed, epoch, tuple(v.vid for v in pool), tag=tag, k0=k0)
    n = len(pool)
    if n == 0 or k0 <= 0:
        return d
    panel: List[Validator] = []
    k = k0
    counter = 0
    while k >= 1:
        tries = 0
        budget = p.DRAW_TRIES * k
        while len(panel) < k and tries < budget:
            c = pool[h(seed, tag, counter) % n]
            counter += 1
            tries += 1
            if fits(panel, c, k, p):
                panel.append(c)
        if len(panel) == k:
            d.k, d.panel, d.counter = k, [v.vid for v in panel], counter
            d.drawn = set(d.panel)
            return d
        if exact:
            break
        k -= 2
        kept: List[Validator] = []
        for m in panel:
            if len(kept) < k and fits(kept, m, k, p):
                kept.append(m)
        panel = kept
    d.counter = counter
    return d


def replacement(d: Draw, members: Sequence[Validator], eligible_now: Dict[int, Validator], p: Params,
                pool: Optional[Sequence[int]] = None) -> Optional[Validator]:
    """The next validator of the same sample that is still eligible, wasn't seated before for this check, and fits
    the caps beside `members`; None once DRAW_TRIES x k tries find nobody (the shuffle is exhausted: the check
    waits). `pool` samples a newer snapshot instead (a stalled check retried when the registry changed)."""
    ids = tuple(pool) if pool is not None else d.pool
    n = len(ids)
    if n == 0:
        return None
    for _ in range(p.DRAW_TRIES * max(d.k, 1)):
        vid = ids[h(d.seed, d.tag, d.counter) % n]
        d.counter += 1
        if vid in d.drawn:
            continue
        v = eligible_now.get(vid)
        if v is not None and fits(members, v, d.k, p):
            d.drawn.add(vid)
            return v
    return None


def shadows(seed: int, candidates: Sequence[Validator], s: int, p: Params) -> List[Validator]:
    """D5: up to `s` distinct candidates as shadow judges, from the same seed with their own counter (no caps:
    shadows don't count)."""
    out: List[Validator] = []
    n = len(candidates)
    if n == 0 or s <= 0:
        return out
    seen: Set[int] = set()
    for counter in range(p.DRAW_TRIES * s):
        c = candidates[h(seed, T_SHADOW, counter) % n]
        if c.vid not in seen:
            seen.add(c.vid)
            out.append(c)
            if len(out) == s:
                break
    return out


def audited(seed: int, p: Params) -> bool:
    """D13: the draw's seed decides whether a submission is audited, at AUDIT_RATE."""
    return u(seed, T_AUDIT) < p.AUDIT_RATE


def auditor(seed: int, pool: Sequence[Validator]) -> Optional[Validator]:
    """One eligible validator outside the panel and not a party (the caller excludes them)."""
    return pool[h(seed, T_AUDITOR) % len(pool)] if pool else None


def challenge_seed(world_seed: int, sub_seed: int, filed_block: int, p: Params) -> int:
    """A seed nobody can choose after the challenge is filed: a block after the filing."""
    return h(T_CHALLENGE, sub_seed, blockhash(world_seed, filed_block + p.SEED_DELAY))


def challenge_draw(seed: int, pool: Sequence[Validator], k: int, p: Params, epoch: int = 0) -> Draw:
    """D4: a fresh panel of CHALLENGE_K[k] from validators outside the original panel and not parties. With fewer
    eligible: the largest odd number they allow, if still larger than k (K_MAX for a panel of K_MAX; #141,
    CHALLENGE_LARGER), or any odd number (#134's reading of the spec's scenario), or nothing until CHALLENGE_K[k] are
    eligible (CHALLENGE_WAITS_FOR_FULL). An unfilled draw (k = 0) means the challenge waits, window frozen."""
    target = p.challenge_k(k)
    empty = Draw(seed, epoch, tuple(v.vid for v in pool), tag=T_CHALLENGE)
    if p.CHALLENGE_WAITS_FOR_FULL:
        if len(pool) < target:
            return empty
        return draw(seed, pool, target, p, tag=T_CHALLENGE, exact=True, epoch=epoch)
    d = draw(seed, pool, p.k_for(len(pool), cap=target), p, tag=T_CHALLENGE, epoch=epoch)
    if p.CHALLENGE_LARGER and d.filled and d.k <= k and not (k == p.K_MAX and d.k == p.K_MAX):
        return empty  # too small to judge it: the challenge waits for a larger fresh panel
    return d


def constitution_draw(seed: int, pool: Sequence[Validator], p: Params, epoch: int = 0) -> Draw:
    """D7: exactly K_MAX under the caps, or nothing (the ADR waits)."""
    if len(pool) < p.K_MAX:
        return Draw(seed, epoch, tuple(v.vid for v in pool))
    return draw(seed, pool, p.K_MAX, p, exact=True, epoch=epoch)
