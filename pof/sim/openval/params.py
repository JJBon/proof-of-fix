"""v3's parameters (proof-of-fix#132 design.md, "Parameters") and the simulation's own assumptions about the world.

Two dataclasses, both frozen:
- `Params`: the protocol. Every parameter of the design's table, with the design's starting values as revised by #141
  in three rounds (design.md, "Revision 2026-11-03", "..., round 2" and "..., round 3"): each rule is a named field, so
  the ADR (#137) cites it. Round 3 changed no rule, only how D17's criteria are read (`GAIN_TEST`, `LONE_CATCH_COUNT`,
  `WAIT_CROWD_MAX`) and a switch the ADR sizes (`SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS`, 0 by default). The
  named sets, run beside each other on the same seeds:
  - `V2R3` (= `Params()`, the defaults): round 3's criteria on round 2's rules (reports/open-validators-v3.1.md); its
    simulation is `V2R2`'s, number for number;
  - `V2R2`: round 2's rules and criteria (reports/open-validators-v3.md);
  - `V2R1`: round 1's rules (reports/open-validators-v2.md); `V2` is the same set under its old name, as
    `pof.sim.openval.rerun` (round 1's report) reads it;
  - `V1`: #134's rules (reports/open-validators-v1.md).
  `Params.table()` prints them; `v1_fields()` names the fields #141's round 1 changed, `diff_fields(a, b)` any two.
- The environment variable POF_OPENVAL_RULES=v1 (or v2r1, v2r2) makes `PARAMS` (every default) `V1` (or `V2R1`,
  `V2R2`): that is how `python3 -m pof.sim market validators --v1` prints v1's report unchanged.
- `World`: what the protocol doesn't decide (how many fixes arrive, how good judges are, what a node costs, how
  often a volunteer re-runs a check). Every one is a named assumption the report states.

Phase 1 treats every validator as level A: the per-(k, level) tables hold all three columns (the design's values),
but phase 1's level rule (`net.PHASE1_LEVEL`) maps every panel to "A", so only level A's column is read. Task 1.5
switches the levels on without touching these tables. Times are hours; money is US dollars (1 credit = $1, as in
reports/costs-v1.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from typing import Dict, List, Mapping, Optional, Tuple

from ... import checkgas as G

HOUR = 1.0
DAY = 24.0
WEEK = 7 * DAY
YEAR = 365 * DAY
MONTH = YEAR / 12
BPS = 10_000
LEVELS = ("A", "B", "C")


def _per_level(a: Mapping[int, float], b: Mapping[int, float], c: Mapping[int, float]) -> Dict[str, Dict[int, float]]:
    return {"A": dict(a), "B": dict(b), "C": dict(c)}


@dataclass(frozen=True)
class Params:
    """The protocol's parameters for v3, fixed per version (entrenched; a new version by migration, D15).

    From the design's table (starting values):"""
    K_MAX: int = 7  # the largest panel, and the constitution tier's exact size
    # the largest bounty each (k, level) may judge; level B is half of A's, level C its own (design, Parameters)
    BOUNTY_LIMIT: Dict[str, Dict[int, float]] = field(default_factory=lambda: _per_level(
        {1: 50.0, 3: 250.0, 5: 625.0, 7: 625.0}, {1: 25.0, 3: 125.0, 5: 312.5, 7: 312.5},
        {1: 10.0, 3: 50.0, 5: 125.0, 7: 250.0}))
    BOND_FACTOR: float = 2.0  # a validator may judge a bounty only if its bond >= BOND_FACTOR x the bounty
    BOND_FLOOR: float = 100.0  # the smallest bond a registration may post (covers k = 1's largest bounty)
    # hours from the verdict to finality, per (k, level); level B twice A's, level C its own; k = 1 at least 7 days
    # (#141: 168 / 336 / 336 h; #134: 72 / 144 / 168 h)
    CHALLENGE_WINDOW_H: Dict[str, Dict[int, float]] = field(default_factory=lambda: _per_level(
        {1: 168.0, 3: 24.0, 5: 12.0, 7: 6.0}, {1: 336.0, 3: 48.0, 5: 24.0, 7: 12.0},
        {1: 336.0, 3: 72.0, 5: 48.0, 7: 24.0}))
    CHALLENGE_K: Dict[int, int] = field(default_factory=lambda: {1: 3, 3: 5, 5: 7, 7: 7})  # fresh validators
    SEED_DELAY: int = 5  # blocks between the submission's seal and the block whose hash seeds the draw
    SEAL_WINDOW_H: float = 2.0  # as #85
    REVEAL_WINDOW_H: float = 1.0  # as #85
    QUALIFY_VERDICTS: int = 20  # shadow verdicts a candidate completes before it is judged for activation
    QUALIFY_REVEAL: float = 0.95  # ... with at least this reveal rate
    QUALIFY_AGREE: float = 0.80  # ... and at least this agreement with the final outcomes (of its revealed verdicts)
    ACTIVE_REVEAL_MIN: float = 0.90  # an active validator below this reveal rate over its last ACTIVE_REVEAL_WINDOW
    ACTIVE_REVEAL_WINDOW: int = 50  # ... counted draws stops being drawn and must re-qualify
    # the longest CHALLENGE_WINDOW of any (k, level) + 7 days (#141: 504 h; #134: CHALLENGE_WINDOW[1] at A + 7 days,
    # 240 h); slashable throughout, and (UNBOND_AFTER_CHALLENGES) until every verdict it gave is final
    UNBONDING_DELAY_H: float = 336.0 + 7 * DAY
    SHADOW_PER_DRAW: int = 1  # shadow judges drawn with each counted panel...
    SHADOW_PER_DRAW_SMALL: int = 2  # ...or this many while fewer than SHADOW_SMALL_BELOW validators are active
    SHADOW_SMALL_BELOW: int = 7
    DRAW_TRIES: int = 8  # rejection-sampling tries per seat before k steps down by 2 (#141: a constant, a gas bound)
    GENESIS_MAX: int = 1  # genesis validators a deployment may name
    GENESIS_LEVELS: Tuple[str, ...] = ("A", "B")  # #141: a level C genesis is refused (#134: any level)
    CONSTITUTION_QUORUM: int = 5  # of K_MAX, for ADRs and escalated fixes
    AUDIT_RATE: float = 0.10  # the share of submissions drawn for audit by the draw's seed (D13; #141: 10 %, #134: 5 %)
    # D14's model scores (task 1.7; pof.sim.openval.scores applies them): a family's agreement with final outcomes
    # over its last SCORE_WINDOW verdicts; below SCORE_MIN over at least SCORE_MIN_VERDICTS it isn't drawn for
    # counted panels; the service fee's factor is linear from SCORE_FACTOR_MIN at SCORE_MIN to SCORE_FACTOR_MAX at 1
    SCORE_WINDOW: int = 200
    SCORE_MIN: float = 0.70
    SCORE_MIN_VERDICTS: int = 50
    SCORE_FACTOR_MIN: float = 0.5
    SCORE_FACTOR_MAX: float = 2.0

    # Carried over from v2 (#85 S12, S16: the specs' "as v2's bond rules define"):
    # v2's slash of the bond for a counted judge that doesn't reveal, which #134 applied to silence too (500). v3 doesn't
    # use it (#141, D16): 0 here, SEALED_NO_REVEAL_SLASH and SILENCE_SLASH below instead.
    NO_REVEAL_SLASH_BPS: int = 0
    EQUIVOCATION_SLASH_BPS: int = 10_000  # two conflicting signatures, or a reveal that doesn't match its seal
    BAD_RECEIPT_SLASH_BPS: int = 2_000  # an upheld receipt challenge (owner, 2026-11-01)
    CHALLENGE_REWARD_BPS: int = 5_000  # of a slash, to whoever proved the fault (a challenger or an auditor)
    ADR_WINDOW_H: float = 14 * DAY  # an ADR's notice after its constitution verdict (#85, Article 9)
    REMOVAL_WINDOW_H: float = 48.0  # D11: an ADR that only removes takes effect after this (levels.LevelParams too)

    QUALIFY_COOLDOWN_H: float = 7 * DAY  # the published cooling-off period after a failed qualification (#141)
    # D16: a false verdict (an upheld receipt challenge) costs the whole bond (#141: 10,000; #134 assumed 2,000)
    FALSE_VERDICT_SLASH_BPS: int = 10_000
    # A challenge panel's size when fewer than CHALLENGE_K[k] fresh validators are eligible. False (the spec's
    # scenario "a fresh panel of at least 3, or every other eligible validator if fewer"): the largest odd number the
    # eligible ones allow, waiting only when none is. True (design D4, "if too few are eligible, the challenge waits"):
    # wait for the full CHALLENGE_K[k].
    CHALLENGE_WAITS_FOR_FULL: bool = False
    # Eligibility by bond. True (#141, D2): bond >= BOND_FACTOR x the bounty's tier, the smallest bounty limit of the k
    # table at ANY level at or above the bounty ($10, $25, $50, $125, $250, $312.50, $625). False (#134's reading of
    # the spec): bond >= BOND_FACTOR x the bounty.
    BOND_TIERS: bool = True
    # D3's seed. True: from the hash of a block SEED_DELAY after the seal, unknown to the solver when it seals. False:
    # the counterfactual D3 rejects, a seed fixed at the seal from what the solver knows (for the seed grinder).
    SEED_FROM_LATER_BLOCK: bool = True

    # Market pricing (D9, specs/check-pricing; task 1.4, pof.sim.openval.pricing): the design's starting values.
    PRICE_PERIOD_H: float = DAY  # unit prices and the service fee move once per period (a whole number of days)
    PRICE_STEP_MAX: float = 0.25  # a unit price moves toward the median by at most this share of itself a period
    PRICE_CAP_X: float = 2.0  # ... and never above this multiple of its value at deployment
    MEDIAN_MIN_POSTERS: int = 3  # a unit's price moves only if at least this many counting validators posted it
    FEE_STEP: float = 0.05  # the service fee's step per period
    WAIT_HIGH: float = 0.05  # it rises if more than this share of the period's submissions waited for a panel...
    IDLE_HIGH: float = 0.40  # ...otherwise it falls if more than this share of active validators wasn't drawn (#134: 80 %)
    FEE_FLOOR: float = 0.01  # dollars per counted check
    FEE_CEILING: float = 0.25  # v2's cap
    FEE_START: float = 0.25  # the service fee at deployment: FEE_CEILING (#141, a rule)
    # The median of an even number of values: the lower middle one (#141); False: the mean of the two middle ones
    # (#134's reading, statistics.median)
    MEDIAN_LOW_EVEN: bool = True

    # ---- #141's rules (design "Revision 2026-11-03"), each a named field; `V1` sets #134's ----
    # k = 1 (D4): a k = 1 verdict's window runs only while CHALLENGE_K[1] validators are eligible for its challenge panel
    # (active, outside its panel, not a party, bonded for its bounty); until then it is held, unpaid
    K1_HOLD: bool = True
    # at most this many k = 1 verdicts not yet final per validator; at the cap it isn't drawn at k = 1 (None: no cap)
    K1_PENDING_MAX: Optional[int] = 10
    # switch (D4's alternative): no count cap, but a k = 1 judge's bond >= BOND_FACTOR x (its pending k = 1 bounties +
    # the new one)
    K1_BATCH_BOND: bool = False
    AUDIT_K1_ALL: bool = True  # D13: every k = 1 verdict audited, once a validator outside its panel is eligible
    # round 2 (D13): ...by this many different auditors outside its panel, each drawn by the seed once eligible
    # (round 1: 1)
    K1_AUDITS: int = 2
    AUDIT_SPLIT_C: bool = True  # D10, D13: every non-unanimous pass by a level C panel audited
    # D5: a shadow verdict counts only against an outcome no lone validator set; on a held k = 1 verdict, or a waiting
    # or withdrawn submission, against the majority of the verdicts sealed on it, if SHADOW_MAJORITY_MIN were revealed
    SHADOW_LONE_RULE: bool = True
    SHADOW_MAJORITY_MIN: int = 3
    SHADOW_PER_WAITING: int = 3  # D5: candidates drawn as shadows of a submission that waits for a panel (#134: 0)
    # D4: a challenge panel is CHALLENGE_K[k], or the largest odd number the eligible allow if still larger than k
    # (K_MAX for a panel of K_MAX); otherwise the challenge waits, window frozen (#134: any odd number >= 1)
    CHALLENGE_LARGER: bool = True
    # D16: a counted judge's sealed vote not revealed costs a flat amount, and so does silence (a drawn counted judge
    # that never seals), the same for every bond (round 2: $5 each; round 1: $1 and none); #134 slashed both
    # NO_REVEAL_SLASH_BPS of the bond
    SEALED_NO_REVEAL_SLASH: float = 5.0
    SILENCE_SLASH: float = 5.0
    # round 3 (D16; the value is ADR 0004's): each slash is the larger of its flat amount and this share of the bounty the
    # judge was drawn for (on a challenge panel, the challenged fix's; an ADR has none, so the flat amount). 0: flat
    # (round 2); the sweep runs 100, 200 and 500 (1, 2 and 5 %), and 1,000 for reference
    SILENCE_SLASH_BPS: int = 0
    SEALED_NO_REVEAL_SLASH_BPS: int = 0
    # gap 11: a leaver's bond is withdrawable only once every verdict it gave is final and every challenge naming it is
    # closed, and it stays slashable until then
    UNBOND_AFTER_CHALLENGES: bool = True
    # D7: the constitution tier is drawn only when at least this many are eligible: CONSTITUTION_MIN_ELIGIBLE (round 2:
    # 3 x K_MAX = 21) for an ADR that adds or loosens anything and for an escalated fix, REMOVAL_MIN_ELIGIBLE (2 x
    # K_MAX = 14) for an ADR that only removes or raises a firmware minimum (round 1: 14 for every ADR; #134: K_MAX);
    # with EXPIRE an ADR submitted to a smaller network expires unjudged (#134: it waits)
    CONSTITUTION_MIN_ELIGIBLE: int = 21
    REMOVAL_MIN_ELIGIBLE: int = 14
    CONSTITUTION_EXPIRE: bool = True
    # round 2 (D7): an ADR, or an escalated fix, posts this deposit; a rejected one forfeits it to the sponsors' pool
    # (never to the issue's funder or reporter); it is refunded when it takes effect or expires (round 1: none).
    # DEPOSIT_FORFEIT_TO "funder" is the rejected alternative: an escalated fix's forfeit goes to its issue's funder
    ADR_DEPOSIT: float = 15.0
    DEPOSIT_FORFEIT_TO: str = "pool"
    # D9's wait signal: which waits count toward the fee's rise. "every" (round 2, as #134): every wait, once: a
    # submission in the period it starts waiting, and a stalled counted panel; "floor" (round 1): only those one more
    # validator bonded at BOND_FLOOR, of any host, TEE type, family or level, would have let be drawn; "any" (switch):
    # a newcomer of any bond
    WAIT_SIGNAL: str = "every"
    POST_ALL_FAMILIES: bool = True  # D9: every validator posts every family's list price; a table missing a unit doesn't count
    IDLE_WINDOW_DAYS: int = 1  # the idle share over this many periods (switch: 7)
    FEE_STEP_UP: Optional[float] = None  # the rise per period when it differs from FEE_STEP (switch: 10 %)
    # D14: a family's score from counted verdicts only; a barred family recovers by its shadow verdicts alone, then its
    # counted window restarts and it is paid SCORE_FACTOR_MIN until it has SCORE_MIN_VERDICTS new ones (#134: shadow and
    # counted verdicts merged in one window)
    SCORE_COUNTED_ONLY: bool = True
    # the fee factor: "normalised" (#141: the raw factor divided by its mean over the previous period's counted seats),
    # "median" (switch: the factor is 1 at the median family score), "linear" (#134: 1 at 80 %)
    SCORE_FACTOR_RULE: str = "normalised"
    # round 2 (D14): the score is the mean of a family's agreement on passed and on failed outcomes (round 1: plain
    # agreement, the switch)
    SCORE_BALANCED: bool = True
    # round 2 (D14): a barred family recovers on fresh, consecutive blocks of SCORE_RECOVER_VERDICTS shadow verdicts,
    # each judged once when complete, at SCORE_MIN + SCORE_RECOVER_MARGIN ("blocks"); round 1 ("sliding"): its last
    # SCORE_RECOVER_VERDICTS (50) shadow verdicts at each check, at SCORE_MIN (margin 0)
    SCORE_RECOVERY: str = "blocks"
    SCORE_RECOVER_VERDICTS: int = 100
    SCORE_RECOVER_MARGIN: float = 0.10
    MOVE_REREGISTERS: bool = True  # changing model family means registering again, with a new key that qualifies
    # D6: the per-TEE-type cap applies from TEE_CAP_FROM_K (5), or from k = 3 while at least TEE_CAP_K3_TYPES TEE types
    # are accepted (round 2: 5; None: never by count, round 1); #134: from 3. Host and family caps from k = 3.
    TEE_CAP_FROM_K: int = 5
    TEE_CAP_K3_TYPES: Optional[int] = 5
    # Owner decision 2026-11-03 (spec PR pending): level C (zkTLS) is off at launch, only A and B register; a
    # constitution ADR switches it on once #135 (notaries) and #125 (determinism) prove out. True: the merged design,
    # C accepted from genesis (#134; the comparison switch)
    C_ACCEPTED: bool = False
    C_LIMIT_X: float = 1.0  # switch: level C's bounty limits times this (0.5)

    # D17's published acceptance thresholds (#141), read by pof.sim.openval.rerun's acceptance check
    SYBIL_SHARE: float = 0.125  # a sybil at or under this share of the eligible never holds a k >= 3 majority
    LONE_CATCH_SHARE: float = 0.90  # of a colluding lone validator's passed bad fixes, reversed before payment (pooled)
    FEE_MARGIN: float = 0.25  # the fee over the last 13 weeks at most this far above break-even
    # submissions waiting for a panel when everyone chases the top family (round 3: 20 %, the balanced score's cost;
    # round 2: 15 %)
    WAIT_CROWD_MAX: float = 0.20
    BORDERLINE_COUNTED: float = 0.10  # answer shopping is counted at this borderline rate (3 in 10: the trust point)
    # the most an attacker's upper bound (mean + 2 SE, dollars over the run) may reach (round 2)
    GAIN_TOLERANCE: float = 10.0
    # every attacker criterion (D17): "not_shown" (round 3, "not shown to gain"): mean - 2 SE <= 0 and mean + 2 SE <=
    # GAIN_TOLERANCE; "doesnt_gain" (round 2, the switch): mean <= 0 and mean + 2 SE <= GAIN_TOLERANCE
    GAIN_TEST: str = "not_shown"
    # which bad fixes LONE_CATCH_SHARE counts: "own" (round 3): the k = 1 verdicts the colluding lone validator gave
    # itself; "all" (round 2, the switch): every bad fix its accomplice passed, whoever judged it
    LONE_CATCH_COUNT: str = "own"

    # ---- lookups (the level field is consulted here, so task 1.5 only changes the panel's level) ----

    def k_for(self, n: int, cap: Optional[int] = None) -> int:
        """The largest odd number <= min(n, K_MAX, cap); 0 when n is 0."""
        m = min(n, self.K_MAX if cap is None else min(cap, self.K_MAX))
        if m <= 0:
            return 0
        return m if m % 2 else m - 1

    def limit(self, k: int, level: str = "A") -> float:
        x = self.BOUNTY_LIMIT[level][k]
        return x * self.C_LIMIT_X if level == "C" else x

    def window_h(self, k: int, level: str = "A") -> float:
        return self.CHALLENGE_WINDOW_H[level][k]

    def challenge_k(self, k: int) -> int:
        return self.CHALLENGE_K[k]

    def cap(self, k: int) -> int:
        """Validators sharing a host, a TEE type or a model family in a panel of k: (k - 1) / 2, no limit at k = 1."""
        return k if k == 1 else (k - 1) // 2

    def tee_cap(self, k: int) -> int:
        """Validators sharing a TEE type in a panel of k: the cap from TEE_CAP_FROM_K, no limit below it."""
        return self.cap(k) if k >= self.TEE_CAP_FROM_K else k

    def tee_from(self, n_types: int) -> int:
        """D6 (round 2): the k the TEE-type cap starts at while `n_types` TEE types are accepted: 3 from
        TEE_CAP_K3_TYPES on, TEE_CAP_FROM_K below (and always, when TEE_CAP_K3_TYPES is None)."""
        if self.TEE_CAP_K3_TYPES is not None and n_types >= self.TEE_CAP_K3_TYPES:
            return min(3, self.TEE_CAP_FROM_K)
        return self.TEE_CAP_FROM_K

    def for_tees(self, n_types: int) -> "Params":
        """The parameters a draw reads while `n_types` TEE types are accepted: these, with TEE_CAP_FROM_K at its
        effective start (`tee_from`). The same object when it doesn't move, so round 1's draws are unchanged."""
        k = self.tee_from(n_types)
        if k == self.TEE_CAP_FROM_K:
            return self
        cache = _FOR_TEES.get(id(self))
        if cache is None or cache[0] is not self:
            cache = _FOR_TEES[id(self)] = (self, {})
        q = cache[1].get(k)
        if q is None:
            q = cache[1][k] = replace(self, TEE_CAP_FROM_K=k, TEE_CAP_K3_TYPES=None)
        return q

    def constitution_min(self, removal: bool) -> int:
        """D7 (round 2): the eligible validators the constitution tier needs: REMOVAL_MIN_ELIGIBLE for an ADR that only
        removes (or raises a firmware minimum), CONSTITUTION_MIN_ELIGIBLE for anything else and for an escalated fix."""
        return self.REMOVAL_MIN_ELIGIBLE if removal else self.CONSTITUTION_MIN_ELIGIBLE

    @property
    def tier_steps(self) -> Tuple[float, ...]:
        """D2's bond tiers: every bounty limit of the k table, at every level (the table's own values: the C_LIMIT_X
        switch scales what a level C panel may judge, not the tiers)."""
        return tuple(sorted({x for lv in self.BOUNTY_LIMIT.values() for x in lv.values()}))

    def bond_needed(self, bounty: float, level: str = "A") -> float:
        if not self.BOND_TIERS or bounty <= 0:
            return self.BOND_FACTOR * bounty
        tier = next((s for s in self.tier_steps if s >= bounty - 1e-9), bounty)
        return self.BOND_FACTOR * tier

    def shadows_per_draw(self, n_active: int) -> int:
        return self.SHADOW_PER_DRAW_SMALL if n_active < self.SHADOW_SMALL_BELOW else self.SHADOW_PER_DRAW

    @property
    def judge_hours(self) -> float:
        """A judge's seal and reveal windows: what a replacement gets afresh."""
        return self.SEAL_WINDOW_H + self.REVEAL_WINDOW_H

    def miss_slash(self, bounty: float, sealed: bool) -> float:
        """D16: what a counted judge loses for a sealed vote not revealed (`sealed`) or for silence: the flat amount, or
        (round 3's switch) the share of the bounty it was drawn for when that is larger. An ADR's bounty is 0."""
        if sealed:
            flat, bps = self.SEALED_NO_REVEAL_SLASH, self.SEALED_NO_REVEAL_SLASH_BPS
        else:
            flat, bps = self.SILENCE_SLASH, self.SILENCE_SLASH_BPS
        return max(flat, bps * max(0.0, bounty) / BPS) if bps else flat

    def table(self) -> List[Tuple[str, str]]:
        """(name, value) for every parameter, in declaration order: what the report and the ADR cite."""
        return [(f.name, str(getattr(self, f.name))) for f in fields(self)]


_FOR_TEES: Dict[int, Tuple["Params", Dict[int, "Params"]]] = {}

V2R3 = Params()  # round 3's criteria on round 2's rules: the design (reports/open-validators-v3.1.md)
# round 2 (reports/open-validators-v3.md): round 3 changed only how the criteria are read, so the same simulation
V2R2 = replace(V2R3, WAIT_CROWD_MAX=0.15, GAIN_TEST="doesnt_gain", LONE_CATCH_COUNT="all")

# #141's round 1 (reports/open-validators-v2.md): every field round 2 changed, back to its round-1 value
V2R1 = replace(
    V2R2, WAIT_SIGNAL="floor", SEALED_NO_REVEAL_SLASH=1.0, SILENCE_SLASH=0.0, CONSTITUTION_MIN_ELIGIBLE=14,
    REMOVAL_MIN_ELIGIBLE=14, ADR_DEPOSIT=0.0, K1_AUDITS=1, SCORE_BALANCED=False, SCORE_RECOVERY="sliding",
    SCORE_RECOVER_VERDICTS=50, SCORE_RECOVER_MARGIN=0.0, TEE_CAP_K3_TYPES=None)
V2 = V2R1  # round 1's rules under their old name (pof.sim.openval.rerun, tests/test_openval_v2.py)

# #134's rules (reports/open-validators-v1.md): every field #141 changed, back to its v1 value
V1 = replace(
    V2R1,
    CHALLENGE_WINDOW_H=_per_level({1: 72.0, 3: 24.0, 5: 12.0, 7: 6.0}, {1: 144.0, 3: 48.0, 5: 24.0, 7: 12.0},
                                  {1: 168.0, 3: 72.0, 5: 48.0, 7: 24.0}),
    UNBONDING_DELAY_H=72.0 + 7 * DAY, GENESIS_LEVELS=("A", "B", "C"), AUDIT_RATE=0.05, NO_REVEAL_SLASH_BPS=500,
    FALSE_VERDICT_SLASH_BPS=2_000, BOND_TIERS=False, IDLE_HIGH=0.80, MEDIAN_LOW_EVEN=False, K1_HOLD=False,
    K1_PENDING_MAX=None, AUDIT_K1_ALL=False, AUDIT_SPLIT_C=False, SHADOW_LONE_RULE=False, SHADOW_PER_WAITING=0,
    CHALLENGE_LARGER=False, SEALED_NO_REVEAL_SLASH=0.0, SILENCE_SLASH=0.0, UNBOND_AFTER_CHALLENGES=False,
    CONSTITUTION_MIN_ELIGIBLE=7, REMOVAL_MIN_ELIGIBLE=7, CONSTITUTION_EXPIRE=False, WAIT_SIGNAL="every",
    POST_ALL_FAMILIES=False, SCORE_COUNTED_ONLY=False, SCORE_FACTOR_RULE="linear", MOVE_REREGISTERS=False,
    TEE_CAP_FROM_K=3, C_ACCEPTED=True)


def diff_fields(a: Params, b: Params) -> List[str]:
    """The fields where `a` and `b` differ."""
    return [f.name for f in fields(Params) if getattr(a, f.name) != getattr(b, f.name)]


def v1_fields(a: Params = V2R1, b: Params = V1) -> List[str]:
    """The fields where `a` and `b` differ (by default: what #141's round 1 changed)."""
    return diff_fields(a, b)


def r2_fields(a: Params = V2R2, b: Params = V2R1) -> List[str]:
    """The fields where `a` and `b` differ (by default: what round 2 changed)."""
    return diff_fields(a, b)


def r3_fields(a: Params = V2R3, b: Params = V2R2) -> List[str]:
    """The fields where `a` and `b` differ (by default: what round 3 changed: the criteria only)."""
    return diff_fields(a, b)


RULES = (os.environ.get("POF_OPENVAL_RULES") or "v2r3").strip().lower()
if RULES not in ("v1", "v2r1", "v2", "v2r2", "v2r3"):
    raise ValueError(f"POF_OPENVAL_RULES={RULES!r}: v1, v2r1, v2r2 or v2r3 (v2: round 3, the design)")
PARAMS = {"v1": V1, "v2r1": V2R1, "v2r2": V2R2}.get(RULES, V2R3)


@dataclass(frozen=True)
class World:
    """What the protocol doesn't decide. Every field is an assumption the report names; the defaults are the
    report's base case."""
    weeks: int = 52
    # submissions: an issue tier of `subs_week` checked fixes a week (above today's simulated market's ~7, below
    # the 55 a week at which a v2 seat breaks even, reports/self-healing-v1.md)
    subs_week: float = 30.0
    good_share: float = 0.75  # the share of honest solvers' fixes that are good (the rest fail a correct check)
    # bounties: lognormal with the simulated market's paid prices (median $86, p90 $184; reports/self-healing-v1.md),
    # never above the largest bounty any panel may judge (v2's BOUNTY_MAX, the k table's top)
    bounty_median: float = 86.0
    bounty_p90: float = 184.0
    bounty_max: float = 625.0
    withdraw_after_days: float = 14.0  # a solver whose submission waits this long withdraws it (its deposit back)
    # validators: honest newcomers register at `joins_week` (Poisson), with these bonds (and weights), spread over
    # these hosts, TEE types and model families uniformly; one declared operator each
    joins_week: float = 1.0
    join_bonds: Tuple[Tuple[float, float], ...] = ((100.0, 0.4), (250.0, 0.3), (500.0, 0.15), (1250.0, 0.15))
    hosts: Tuple[str, ...] = ("aws", "gcp", "azure", "hetzner", "ovh", "home")
    # D6's TEE types: the three realistic at launch (AWS Nitro Enclaves, Intel TDX, AMD SEV-SNP; the TEE cap from k = 5);
    # round 2's five-type world adds Intel SGX ("sgx") and IBM Secure Execution ("ibm-se"). Newcomers pick a type
    # evenly, or by `tee_weights` (the skewed spread, in the order of `tees`)
    tees: Tuple[str, ...] = ("nitro", "tdx", "sev-snp")
    tee_weights: Tuple[float, ...] = ()
    families: Tuple[str, ...] = ("anthropic", "openai", "google", "open-weight")
    genesis_bond: float = 1250.0  # the genesis validator's bond (2 x the largest bounty)
    initial_active: int = 0  # honest validators already active at the start, beside the genesis one (mature networks)
    initial_bond: float = 1250.0  # their bonds
    # judges: an honest judge's verdict matches the truth with `accuracy` (its model's variance), independently; a
    # family may differ (the hook task 1.7's scores read). An honest node misses a seal at 1 - `reliability`.
    accuracy: float = 0.9
    family_accuracy: Tuple[Tuple[str, float], ...] = ()
    # a family's blind spot (task 1.7): the share of bad fixes that fool every judge of that family at once (a prompt
    # injection that works on that model), on top of its independent errors; none by default
    family_blind: Tuple[Tuple[str, float], ...] = ()
    reliability: float = 0.995
    # the share of honest outages that strike between the seal and the reveal (a sealed vote not revealed, slashed
    # SEALED_NO_REVEAL_SLASH) rather than before the seal (silence, SILENCE_SLASH); 0 as #134 (every outage before the
    # seal: the spec's "An honest outage"); the honest month's worst case sets 1 (#141)
    outage_sealed: float = 0.0
    # re-runs: a re-run (an audit, a volunteer, a challenge panel's judge) shows a fabricated receipt with
    # `rerun_detect` (the receipt's tests and model call don't reproduce); volunteers re-run a verdict at
    # `volunteer_per_day` (Poisson), so the share of verdicts re-run before the window ends grows with the window
    rerun_detect: float = 0.95
    volunteer_per_day: float = 0.25
    # money: phase 1's flat service fee per counted check (v2's SERVICE_FEE; task 1.4 replaces it with the market),
    # one judge's metered usage (passed through at cost; a judge-grade medium review, reports/self-healing-v1.md),
    # the race's attempt fee (pof.params), a node's on-demand enclave (pof.checkgas.Enclave: overhead per check and
    # fixed cost a month), and the yearly cost of the capital a bond locks
    service_fee: float = 0.05
    usage_per_check: float = 0.13
    attempt_fee: float = 0.50
    enclave: G.Enclave = G.Enclave()
    capital_rate: float = 0.05
    snapshot_weeks: int = 4  # the growth table's period

    def accuracy_of(self, family: str) -> float:
        return dict(self.family_accuracy).get(family, self.accuracy)

    def blind_of(self, family: str) -> float:
        return dict(self.family_blind).get(family, 0.0)

    def pick_tee(self, rng) -> str:
        """A newcomer's TEE type: even (`rng.choice`, as #134 and round 1), or by `tee_weights`."""
        return rng.choices(self.tees, self.tee_weights)[0] if self.tee_weights else rng.choice(self.tees)

    @property
    def horizon_h(self) -> float:
        return self.weeks * WEEK


WORLD = World()
