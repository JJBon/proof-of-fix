"""The open registry (#132 specs/validator-admission; design D1's `Validators`, D5): registration with a bond and a
proof type, candidates qualifying as shadow judges, activation by the thresholds alone, the reveal-rate floor,
leaving with the unbonding delay (slashable throughout), and at most `GENESIS_MAX` genesis validators.

No function here activates, removes or suspends a validator except by those rules: there is no `activate` or
`admit` to call (the spec's "The owner tries to admit a friend"). Every change bumps `epoch`, so a draw can record
the registry state it used (D2) and a waiting submission is retried only when something changed.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, FrozenSet, Iterable, List, Optional, Sequence

from .params import BPS, PARAMS, Params

CANDIDATE, ACTIVE, LEAVING, GONE = "candidate", "active", "leaving", "gone"
OFFICIAL_IMAGE = "sha256:official-checker"  # the constitution's allowed checker image (one, built reproducibly)
TEE_TYPES = frozenset({"nitro", "tdx", "sev-snp"})  # the constitution's accepted TEE types (#85 S14)
ZKTLS = "zktls"  # the proof type for validators without a TEE (D10)


class RegistrationError(ValueError):
    pass


@dataclass
class Account:
    """What a validator earned and spent, in dollars. Metered usage is passed through at cost, so it nets to zero
    and isn't recorded; `overhead` is the node's own cost per check on top of it."""
    fees: float = 0.0  # service fees: counted checks, audits, challenge panels
    overhead: float = 0.0  # the enclave's cost per check run (counted, shadow, audit, challenge)
    slashed: float = 0.0
    rewards: float = 0.0  # shares of slashes it proved (as an auditor)
    gains: float = 0.0  # what it was paid outside the protocol (bribes): actors only
    checks: int = 0  # counted checks revealed
    shadows: int = 0
    audits: int = 0
    tokens: float = 0.0  # #142: its share of the validators' slice, in tokens (valued at World.token_price)


@dataclass(eq=False)
class Validator:
    """A registered key and what the caps need (specs: "A registration records what the caps need")."""
    vid: int
    key: str
    operator: str  # the declared operator account: a disclosure, not a proof
    party: str  # who really controls it (hidden from the protocol; the simulation's accounting only)
    bond: float
    proof: str  # a TEE type, or "zktls"
    level: str  # "A", "B" or "C" (D10); phase 1 treats every level alike
    host: str
    family: str
    attestation: Optional[str]
    behaviour: object = None  # a pof.sim.openval.actors behaviour; None is honest
    genesis: bool = False
    state: str = CANDIDATE
    registered_at: float = 0.0
    active_at: Optional[float] = None
    leave_at: Optional[float] = None
    unbond_at: Optional[float] = None
    withdrawn: Optional[float] = None  # what it took back after the delay
    gone_at: Optional[float] = None  # when it took it back
    target: float = 0.0  # the bond it means to keep (it tops up to this after a slash)
    posted: float = 0.0  # every dollar it ever posted (the capital a bond locks)
    # qualification (D5): the current attempt's shadow verdicts
    shadow_n: int = 0
    shadow_revealed: int = 0
    shadow_agree: int = 0
    cooldown_until: float = 0.0
    qualify_tries: int = 0
    activations: int = 0
    suspensions: int = 0
    # the reveal-rate floor: the last ACTIVE_REVEAL_WINDOW counted draws (True: revealed)
    recent: Deque[bool] = field(default_factory=deque)
    acct: Account = field(default_factory=Account)

    @property
    def tee(self) -> str:
        """Its TEE type (a TEE type added by ADR is its own type, gap 14), or "none" at level C."""
        return self.proof if self.proof != ZKTLS else "none"

    def public(self) -> dict:
        """What anyone reads (specs: "Reading a validator's host")."""
        return {"key": self.key, "proof": self.proof, "level": self.level, "tee": self.tee, "host": self.host,
                "family": self.family, "operator": self.operator, "attestation": self.attestation,
                "bond": self.bond, "state": self.state, "genesis": self.genesis}


class Registry:
    """The validator set. `images` and `proofs` are the constitution's lists (changed only by ADR, not modelled in
    phase 1)."""

    def __init__(self, p: Params = PARAMS, images: Iterable[str] = (OFFICIAL_IMAGE,),
                 proofs: Iterable[str] = tuple(TEE_TYPES) + (ZKTLS,)):
        self.p = p
        self.images: FrozenSet[str] = frozenset(images)
        self.proofs: FrozenSet[str] = frozenset(proofs)
        self.validators: Dict[int, Validator] = {}
        self.epoch = 0
        self._next = 1
        self._genesis_done = False

    # ---------- registration ----------

    def register(self, t: float, key: str, signer: str, bond: float, proof: str, host: str, family: str,
                 operator: str, image: str = OFFICIAL_IMAGE, attestation: Optional[str] = "att",
                 cloud_attested: bool = True, party: Optional[str] = None, behaviour: object = None,
                 vid: Optional[int] = None) -> Validator:
        """Anyone registers, without a co-signature. Refused: a key that didn't sign its own registration, a bond
        below the floor, an unaccepted proof type, a TEE attestation of an image not on the list. The level is read
        from the proof: a TEE with the cloud platform's own attestation is A, a TEE alone B, zkTLS C."""
        if signer != key:
            raise RegistrationError("the new key must sign its own registration")
        if bond < self.p.BOND_FLOOR:
            raise RegistrationError(f"a bond of {bond} is below the floor {self.p.BOND_FLOOR}")
        if proof not in self.proofs:
            raise RegistrationError(f"proof type {proof!r} isn't accepted")
        if proof != ZKTLS and (attestation is None or image not in self.images):
            raise RegistrationError("the attestation must show a checker image on the allowed list")
        if any(v.key == key for v in self.validators.values()):
            raise RegistrationError("key already registered")
        level = "C" if proof == ZKTLS else ("A" if cloud_attested else "B")
        if vid is None:  # honest ids count up from 1; actors pass their own (a separate range), so an actor's
            vid = self._next  # presence never renumbers anyone else (its honest twin sees the same ids)
            self._next += 1
        if vid in self.validators:
            raise RegistrationError(f"validator id {vid} taken")
        v = Validator(vid=vid, key=key, operator=operator, party=party or operator, bond=bond, proof=proof,
                      level=level, host=host, family=family, attestation=None if proof == ZKTLS else attestation,
                      behaviour=behaviour, registered_at=t, target=bond, posted=bond)
        self.validators[vid] = v
        self.epoch += 1
        return v

    def genesis(self, specs: Sequence[dict]) -> List[Validator]:
        """A deployment names at most GENESIS_MAX genesis validators, active from the start, bonded and attested like
        any other, at a level of GENESIS_LEVELS (#141: A or B); a deployment breaking either is refused whole."""
        if self._genesis_done:
            raise RegistrationError("genesis happens once, at deployment")
        if len(specs) > self.p.GENESIS_MAX:
            raise RegistrationError(f"{len(specs)} genesis validators; at most {self.p.GENESIS_MAX}")
        for s in specs:
            level = "C" if s.get("proof") == ZKTLS else ("A" if s.get("cloud_attested", True) else "B")
            if level not in self.p.GENESIS_LEVELS:
                raise RegistrationError(f"a level {level} genesis validator; the genesis must be at level "
                                        f"{' or '.join(self.p.GENESIS_LEVELS)}")
        self._genesis_done = True
        out = []
        for s in specs:
            v = self.register(**{"t": 0.0, **s})
            v.genesis = True
            self._activate(v, 0.0)
            out.append(v)
        return out

    def seed_active(self, v: Validator, t: float) -> None:
        """The simulation's shortcut for a mature network: a validator that qualified before the run started."""
        self._activate(v, t)

    # ---------- qualification and the reveal-rate floor ----------

    def record_shadow(self, v: Validator, revealed: bool, agreed: bool, t: float) -> Optional[str]:
        """One shadow verdict, at its submission's finality. At exactly QUALIFY_VERDICTS the candidate becomes active
        if its reveal rate and agreement meet the thresholds, or starts the cooling-off period and tries again.
        Returns "active", "failed" or None. A missed shadow verdict is never slashed (it doesn't count)."""
        if v.state != CANDIDATE or t < v.cooldown_until:
            return None
        v.shadow_n += 1
        v.shadow_revealed += revealed
        v.shadow_agree += revealed and agreed
        v.acct.shadows += 1
        if v.shadow_n < self.p.QUALIFY_VERDICTS:
            return None
        v.qualify_tries += 1
        ok = (v.shadow_revealed >= self.p.QUALIFY_REVEAL * v.shadow_n
              and v.shadow_revealed > 0 and v.shadow_agree >= self.p.QUALIFY_AGREE * v.shadow_revealed)
        v.shadow_n = v.shadow_revealed = v.shadow_agree = 0
        if ok:
            self._activate(v, t)
            return "active"
        v.cooldown_until = t + self.p.QUALIFY_COOLDOWN_H
        return "failed"

    def record_counted(self, v: Validator, revealed: bool, t: float) -> bool:
        """One counted draw's reveal (a missing seal counts as not revealed). An active validator whose misses in its
        last ACTIVE_REVEAL_WINDOW draws exceed what ACTIVE_REVEAL_MIN allows stops being drawn and must re-qualify
        (it becomes a candidate again). Returns True when that happens. Draws before its first window fills count as
        revealed, so a newly active validator isn't suspended by its first miss."""
        v.recent.append(revealed)
        if len(v.recent) > self.p.ACTIVE_REVEAL_WINDOW:
            v.recent.popleft()
        misses = sum(1 for r in v.recent if not r)
        if v.state == ACTIVE and misses > (1 - self.p.ACTIVE_REVEAL_MIN) * self.p.ACTIVE_REVEAL_WINDOW + 1e-9:
            v.state = CANDIDATE
            v.suspensions += 1
            v.recent.clear()
            v.shadow_n = v.shadow_revealed = v.shadow_agree = 0
            self.epoch += 1
            return True
        return False

    def _activate(self, v: Validator, t: float) -> None:
        v.state = ACTIVE
        v.active_at = t
        v.activations += 1
        v.recent.clear()
        self.epoch += 1

    # ---------- leaving, slashing, bonds ----------

    def leave(self, v: Validator, t: float) -> None:
        """Leave at any time: never drawn again; the bond is withdrawable after UNBONDING_DELAY_H, slashable until
        then."""
        if v.state in (LEAVING, GONE):
            return
        v.state = LEAVING
        v.leave_at = t
        v.unbond_at = t + self.p.UNBONDING_DELAY_H
        self.epoch += 1

    def withdraw(self, v: Validator, t: float) -> float:
        """After the delay, what's left of the bond goes back; nothing before."""
        if v.state != LEAVING or t < (v.unbond_at or 0.0):
            return 0.0
        v.state = GONE
        v.gone_at = t
        v.withdrawn = v.bond
        v.bond = 0.0
        self.epoch += 1
        return v.withdrawn

    def slashable(self, v: Validator, t: float) -> bool:
        """Until its bond is withdrawn. #134: and not after the delay; #141 (UNBOND_AFTER_CHALLENGES): the bond is
        withdrawn only once every verdict it gave is final and every challenge naming it closed, so until then."""
        if self.p.UNBOND_AFTER_CHALLENGES:
            return v.state != GONE
        return v.state != GONE and not (v.state == LEAVING and t >= (v.unbond_at or 0.0))

    def slash(self, v: Validator, bps: int, t: float) -> float:
        """Slash `bps` of the bond for a provable fault; a leaving validator is slashed as if active until its delay
        ends, and nothing after. Returns the amount taken."""
        if not self.slashable(v, t):
            return 0.0
        amount = v.bond * bps / BPS
        v.bond -= amount
        v.acct.slashed += amount
        self.epoch += 1
        return amount

    def slash_flat(self, v: Validator, amount: float, t: float) -> float:
        """A flat slash (D16: a sealed vote not revealed, or the SILENCE_SLASH switch), at most the bond left."""
        if amount <= 0 or not self.slashable(v, t):
            return 0.0
        amount = min(amount, v.bond)
        v.bond -= amount
        v.acct.slashed += amount
        self.epoch += 1
        return amount

    def top_up(self, v: Validator, to: float) -> float:
        """Post more bond (capital, not a loss). Returns what was added."""
        if v.state == GONE or v.bond >= to:
            return 0.0
        add = to - v.bond
        v.bond = to
        v.posted += add
        self.epoch += 1
        return add

    # ---------- who may be drawn ----------

    def active(self) -> List[Validator]:
        return [v for v in self.validators.values() if v.state == ACTIVE]

    def drawable(self, v: Validator) -> bool:
        """Active, not leaving, and bonded at least at the floor (a slashed validator below it waits to top up)."""
        return v.state == ACTIVE and v.bond >= self.p.BOND_FLOOR

    def eligible(self, bounty: float, parties: FrozenSet[str] = frozenset(), exclude: FrozenSet[int] = frozenset(),
                 family_ok=None) -> List[Validator]:
        """The validators a draw may sample, in registry order (D2's snapshot): drawable, bonded for the bounty, not
        a party (by declared operator), not excluded, and of a family the scores allow (task 1.7's hook; phase 1
        allows every family). The caps are applied by the draw itself."""
        need = self.p.bond_needed(bounty)
        out = []
        for v in self.validators.values():
            if (v.state == ACTIVE and v.bond >= self.p.BOND_FLOOR and v.bond >= need - 1e-9
                    and v.operator not in parties and v.vid not in exclude
                    and (family_ok is None or family_ok(v.family))):
                out.append(v)
        return out

    def candidates(self, t: float, parties: FrozenSet[str] = frozenset(),
                   exclude: FrozenSet[int] = frozenset()) -> List[Validator]:
        """Candidates a shadow draw may sample: not cooling off, not a party."""
        return [v for v in self.validators.values()
                if v.state == CANDIDATE and t >= v.cooldown_until and v.operator not in parties
                and v.vid not in exclude]
