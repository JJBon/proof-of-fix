"""Who acts in the simulation (specs/incentive-simulation, "Actor behaviours"; design D6 and D7).

Behaviour numbers here are simulation assumptions, not mechanism parameters: how often people submit, how often
their work hides a defect, how good hunters are at finding one. They're named so scenarios can vary them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import credits

SEVERITY_MIX = (("cosmetic", 5_000), ("wrong_result", 4_000), ("crash", 1_000))  # bps of defects


@dataclass(frozen=True)
class Behaviour:
    endowment: int = credits(500)
    submissions_per_week: float = 0.0
    max_lines: int | None = None  # spam is small
    split_into: int = 1  # the splitting spammer cuts each change into this many PRs
    defect_bps: int = 1_500  # chance a contribution hides a defect
    checks_catch_bps: int = 3_000  # chance the deterministic gate catches a defect
    false_check_failure_bps: int = 500  # chance the gate fails a sound contribution (flaky CI)
    high_risk_bps: int = 0  # share of contributions that are high-risk
    high_risk_defect_bps: int = 4_000  # their defect chance
    hunt_daily_bps: int = 0  # chance per day of finding a given defect in a beta build (hunters)
    false_challenges_per_day: float = 0.0  # griefers
    validator_stake: int = 0  # > 0: registers as a validator
    vote_error_bps: int = 500  # an honest validator's chance of voting wrong
    no_reveal_bps: int = 200  # chance of forgetting to reveal
    appeals_wrong_decisions: bool = True  # honest parties appeal a decision that contradicts the truth
    decline_others_bps: int = 0  # self-interested owner as maintainer: decline others' contributions
    shift_split_to_validators: bool = False  # self-interested owner: publish a split favouring validators
    pad_factor: int = 1  # proof-of-fix#10 padder: inflates changed lines by this factor
    padding_defect_bps: int = 0  # chance padding is reported as a cosmetic defect (reviewers, hunters)
    # proof-of-fix#15 market solvers: capacity > 0 makes an actor a solver
    capacity: int = 0  # bounties it works on at once (entries in open rounds and its contributions in flight)
    skill: float = 1.0  # its cost multiplier (lower is cheaper)
    bid_factor: float = 1.0  # its price over its cost: 1 is truthful, 1.5 a bluffer, 0.6 a lowballer
    delivers: bool = True  # a no-show wins jobs and never delivers (design D9)
    incomplete_bps: int = 0  # proof-of-fix#43: chance a delivered fix only partly solves its issue, breaking nothing
    floods: float = 0.0  # junk issues per day pushed at the AI treasury (a treasury flood)
    stack_from_day: int = 0  # proof-of-fix#19 pledge stacker: honest until this day, then `turns_to`
    turns_to: "Behaviour | None" = None  # what it does from stack_from_day (default STACKING)
    # proof-of-fix#60: fix quality (of 1, in bps) as the constitution's gates measure it, and the attacks on them
    quality_bps: int = 8_000
    pads_tests: bool = False  # its tests raise coverage without catching anything: only mutation scoring sees it
    variants: bool = False  # a failed submission is resubmitted as a variant from its second account
    inflates: bool = False  # its issues' effort estimates come out at twice the truth
    fake_attempts: int = 0  # proof-of-fix#64: its sock accounts each start a paid attempt they never submit
    # proof-of-fix#58: tokens
    codes_own: bool = False  # registers issues of its own, doesn't fund them, and races only for them
    inflates_importance: bool = False  # its registrations' importance estimates come out at twice the truth


@dataclass
class Actor:
    name: str
    kind: str  # honest | spammer | splitter | hunter | griefer | validator | colluder | owner
    behaviour: Behaviour
    account: str = ""
    group: str | None = None  # collusion group; colluding validators protect their group's contributions
    cohort: str | None = None  # accounting group (a ring, an abuser and its fake accounts), even when acting honestly
    sponsor: "Actor | None" = None  # who posts this actor's stake when it can't (proof-of-fix#10)
    operator: str | None = None  # an AI evaluator's operator and declared model family (proof-of-fix#43)
    family: str | None = None
    true_family: str | None = None  # the model it really runs, if it declared another
    actions: int = 0  # submissions, challenges, revealed votes: the "effort" for return per unit of effort
    staked: int = 0  # total ever put at stake (entry, challenger, validator stakes)
    stats: dict = field(default_factory=dict)

    def bump(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n


# ---------- the population each scenario starts from ----------

HONEST = Behaviour(submissions_per_week=1.0)
SPAMMER = Behaviour(submissions_per_week=5.0, max_lines=100, defect_bps=6_000, appeals_wrong_decisions=False)
SPLITTER = Behaviour(submissions_per_week=0.5, split_into=8, defect_bps=1_500, appeals_wrong_decisions=False)
HUNTER = Behaviour(endowment=credits(300), hunt_daily_bps=1_500)
GRIEFER = Behaviour(endowment=credits(300), false_challenges_per_day=0.5, appeals_wrong_decisions=False)
VALIDATOR = Behaviour(endowment=credits(200), validator_stake=credits(100))
COLLUDER = Behaviour(endowment=credits(200), validator_stake=credits(100), appeals_wrong_decisions=False)
# proof-of-fix#10 actors
PADDER = Behaviour(submissions_per_week=3.0, max_lines=100, pad_factor=5, padding_defect_bps=4_000,
                   appeals_wrong_decisions=False)
NEWCOMER = Behaviour(endowment=credits(5), submissions_per_week=1.0)  # can't afford a stake alone
ABUSER = Behaviour(submissions_per_week=1.0)  # contributes honestly until it can sponsor its fake accounts
SYBIL = Behaviour(endowment=0, submissions_per_week=5.0, max_lines=100, defect_bps=6_000,
                  appeals_wrong_decisions=False)
# proof-of-fix#19: builds accepted work for 3 weeks, then stacks defective contributions on its pledged rewards
STACKER = Behaviour(submissions_per_week=1.0, stack_from_day=21)
STACKING = Behaviour(submissions_per_week=7.0, max_lines=100, defect_bps=6_000, appeals_wrong_decisions=False)
# proof-of-fix#23: floods small sound contributions for 3 weeks to push the stake index down, then stacks defects
INDEX_GAMER = Behaviour(submissions_per_week=10.0, max_lines=20, defect_bps=0, stack_from_day=21, turns_to=STACKING)
# proof-of-fix#15 market actors (design D6)
PLEDGER = Behaviour(endowment=credits(5_000))
SOLVER = Behaviour(capacity=3, incomplete_bps=500)
BLUFFER = Behaviour(capacity=3, bid_factor=1.5)
LOWBALLER = Behaviour(capacity=3, bid_factor=0.6)
# proof-of-fix#34: discoverers, and the attacks on their rewards and on matching
REPORTER = Behaviour(endowment=credits(200))
MATCH_FARMER = Behaviour(capacity=3, appeals_wrong_decisions=False)  # pledges via fake accounts, solves its own
FAKE = Behaviour(endowment=credits(200))  # a match farmer's fake pledging account
SELF_DEALER = Behaviour(capacity=3, endowment=credits(1_000))  # funds and solves its own issues
# proof-of-fix#37: builds solver trust on small jobs for 3 weeks, then wins jobs low and walks away
REP_FARMER_TURNED = Behaviour(capacity=3, bid_factor=0.5, delivers=False, appeals_wrong_decisions=False)
REP_FARMER = Behaviour(capacity=3, max_lines=100, stack_from_day=21, turns_to=REP_FARMER_TURNED)
NO_SHOW = Behaviour(capacity=3, bid_factor=0.5, delivers=False, appeals_wrong_decisions=False)
SPAM_SOLVER = Behaviour(capacity=10, skill=0.2, defect_bps=6_000, appeals_wrong_decisions=False, quality_bps=4_000)
FLOOD = Behaviour(capacity=10, floods=2.0, appeals_wrong_decisions=False)
# proof-of-fix#43: AI evaluators, and the attacks on the checking layer (design D6)
EVALUATOR = Behaviour(endowment=credits(50))
RUNNER = Behaviour(endowment=credits(50))  # an attested CI runner's operator
LAZY_VALIDATOR = VALIDATOR  # its kind makes it report "pass" without running the checks
JUNK_SOLVER = Behaviour(capacity=3, defect_bps=10_000, checks_catch_bps=0, appeals_wrong_decisions=False,
                        quality_bps=3_000)
PLANT_PARTNER = Behaviour(endowment=credits(300))
HALF_FIXER = Behaviour(capacity=3, defect_bps=0, incomplete_bps=10_000, appeals_wrong_decisions=False,
                       quality_bps=6_000)
OWNER_HONEST = Behaviour(submissions_per_week=2.0, validator_stake=credits(100))
OWNER_SELF_INTERESTED = Behaviour(submissions_per_week=2.0, validator_stake=credits(100), decline_others_bps=3_000,
                                  shift_split_to_validators=True)
# proof-of-fix#60: the attacks on the award modes (design D7)
TEST_PADDER = Behaviour(capacity=3, quality_bps=5_000, pads_tests=True, appeals_wrong_decisions=False)
VARIANT_RACER = Behaviour(capacity=3, variants=True)  # races, and resubmits a failed fix from a second account
INFLATER = Behaviour(capacity=3, endowment=credits(1_000), inflates=True)  # posts and solves small issues of its own
FAKE_ATTEMPTER = Behaviour(capacity=3, fake_attempts=2)  # #64: its two socks inflate the published attempts
# proof-of-fix#58: the token scenarios (design D6)
SELF_CODER = Behaviour(capacity=3, codes_own=True)  # registers and solves its own issues for tokens
IMPORTANCE_INFLATER = Behaviour(capacity=3, codes_own=True, inflates_importance=True)
OWNER_CODER = Behaviour(capacity=3, validator_stake=credits(100), codes_own=True)  # the launch: the owner codes too
