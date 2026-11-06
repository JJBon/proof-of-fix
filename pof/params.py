"""The mechanism's published parameters (design D5), in one frozen object the simulation can sweep.

Amounts are micro-credits; shares and fractions are basis points (BPS = 10,000 is the whole).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Mapping

from . import BPS, credits, share


def _frozen(d: dict) -> Mapping:
    return MappingProxyType(dict(d))


SPLIT_SHARES = ("contributors", "validators", "author", "infrastructure", "insurance", "owner")
FEE_SHARES = ("validators", "author", "infrastructure", "insurance", "owner")  # the market fee (proof-of-fix#15)
REWARD_SOURCES = ("pool", "market")
AWARD_MODES = ("auction", "race", "claim")  # how a bounty's job is awarded (proof-of-fix#60)
SEVERITIES = ("crash", "wrong_result", "cosmetic")


class ParamsError(ValueError):
    """Parameters that can't be published."""


@dataclass(frozen=True)
class Params:
    # contribution lifecycle
    size_tiers: tuple[int, ...] = (100, 400, 1500)  # upper bounds in changed lines; above the last is the top tier
    stake_multiplier: tuple[int, ...] = (1, 2, 5, 10)  # per tier, times base_stake
    validators: tuple[int, ...] = (3, 3, 5, 7)  # per tier
    reward_weight: tuple[int, ...] = (1, 2, 4, 6)  # per tier, used only when linear_reward_weight is off
    linear_reward_weight: bool = True  # proof-of-fix#10: weight = changed lines, capped, so splitting earns nothing
    reward_weight_cap_lines: int = 1_500
    reward_instalments: int = 4  # #10: paid one per release; unpaid instalments can be clawed back
    sponsor_min_accepted: int = 1  # #10: accepted contributions needed to sponsor someone else's stake, or to pledge
    pledge_max_stake_bps: int = 5_000  # proof-of-fix#19: of a stake that unpaid rewards may cover; 0 turns pledges off
    pledge_max_escrow_bps: int = 5_000  # #19: of a backing contribution's unpaid reward that may be pledged
    max_declines_bps: int = 1_000  # #10: of others' contributions per release a maintainer may decline unaided
    decline_appeal_stake_bps: int = 200  # #10: of the contribution's stake, to appeal a decline
    risk_multiplier: Mapping[str, int] = field(default_factory=lambda: _frozen({"normal": 1, "high": 2}))
    base_stake: int = credits(75)  # proof-of-fix#10 (task 6.2): 10 let rare escaped defects pay for all caught ones
    stake_per_reward_bps: int = 4_000  # proof-of-fix#23: stake = this share of the expected reward; 0 = fixed stake
    # (task 4.2: 2,500 let the index gamer's defects pay at hunting elasticity 0.5)
    stake_floor: int = credits(10)  # #23: the indexed stake's floor per size tier (times stake_multiplier)
    stake_index_window: int = 4  # #23: beta builds averaged into the reward-per-weight index
    reward_cap_stake_multiple: int = 6  # #23: a reward is at most this many times its stake; 0 = no cap
    # (task 4.2: 8 let defects pay at elasticity 0; 6 passed at every stake share tried)
    check_fee_bps: int = 200
    challenge_window_days: int = 7
    extension_days: int = 3
    # challenges
    severity_slash_bps: Mapping[str, int] = field(
        default_factory=lambda: _frozen({"crash": 10_000, "wrong_result": 5_000, "cosmetic": 2_500})  # #10: padding
    )
    challenger_reward_share_bps: int = 5_000  # of what the contributor forfeits; the rest goes to insurance
    challenger_escrow_share_bps: int = 0  # #10: of the forfeited escrowed reward (5,000 in LEGACY); 0 in the market,
    # where the escrow is pledgers' money and must return to the bounty (#15 design D8)
    review_duty: bool = True  # #10: one reviewer per contribution entering beta
    review_bond: int = credits(5)
    missed_review_penalty_bps: int = 5_000  # of the review bond, when a defect the reviewer passed is proven
    no_review_penalty_bps: int = 2_000  # of the review bond, when no report comes within the window
    challenger_stake_bps: int = 5_000  # of the contributor's stake
    rejected_challenge_loss_bps: int = 5_000  # of the challenger's stake
    filing_fee_bps: int = 200  # of the challenger's stake, kept when a challenge is refused for lack of proof
    validator_bond: int = credits(5)
    no_reveal_penalty_bps: int = 2_000  # of the bond
    overturned_penalty_bps: int = 5_000  # of the bond
    appeal_stake_multiplier: int = 2  # times the challenger's stake
    challenge_appeals: bool = True  # a decided challenge can be appealed to jurors; False: the local contract's phase
    # 1, where a challenge arrives as one final result, so instalments never pause and windows never extend (#56 D9)
    collusion_threshold_bps: int = 3_333  # of total validator stake
    # release payouts
    release_split_bps: Mapping[str, int] = field(
        default_factory=lambda: _frozen(
            {"contributors": 5_000, "validators": 2_000, "author": 1_000, "infrastructure": 1_000,
             "insurance": 500, "owner": 500}
        )
    )
    owner_share_cap_bps: int = 500
    owner_vesting_months: int = 24
    insurance_limit_bps: int = 5_000  # of the pool, per release
    release_funding: int = credits(10_000)
    # the bounty market (proof-of-fix#15): the reward source, and its parameters (design D2)
    reward_source: str = "market"  # "market": bounties (the default, owner's decision 2026-10-24); "pool": LEGACY
    bounty_deadline_days: int = 14  # to reach a bounty's target with pledges, or every pledge is refunded
    round_days: int = 7  # a sealed round's bidding period; reveals at its end
    delivery_days: int = 14  # for the assigned solver to deliver, or its bond goes to the bounty (#15 design D9)
    bounty_stake_bps: int = 4_000  # an entry's stake, of the bounty's price cap (times the risk multiplier)
    evaluation_fee: int = credits(2)  # per entry, for the checks; refunded to the winner
    market_fee_bps: int = 2_000  # on the winner's price, paid from the bounty
    market_fee_split_bps: Mapping[str, int] = field(default_factory=lambda: _frozen(
        {"validators": 4_000, "author": 2_000, "infrastructure": 2_000, "insurance": 1_000, "owner": 1_000}))
    treasury_budget: int = credits(2_000)  # per release, for bounties on unpledged issues; issued only when used
    treasury_bounty_cap: int = credits(500)
    treasury_approval_above: int = credits(300)  # a larger treasury bounty needs a validator panel
    # discoverers and funders (proof-of-fix#34, design D2)
    issue_stake: int = credits(5)  # posted with an issue: back with a finder's fee when its bounty is paid; lost if junk
    finder_fee_bps: int = 1_765  # of the winning price, from the bounty, to the issue's reporter: 15 % of the payout,
    # the solver 85 % (#56 D13, at the owner's request; 500 before). reports/split-v1: on the contract's shape,
    # reporters lose below ~12.5 %, and above 15 % fewer bounties are fixed. Below the market fee (#34)
    matching_share_bps: int = 5_000  # of the treasury budget, matching pledges quadratically
    match_cap_bps: int = 5_000  # of a bounty's target: the most its match can be
    bounty_max_rounds: int = 4  # empty rounds in a row before a funded bounty closes and its funds return (#34 D6)
    reserve_bps: int = 7_500  # of the price cap: the most any price can be; bids above it are void (#40 design D1)
    # non-transferable reputation (proof-of-fix#37, design D4): points per outcome, trust, the bond discount
    points_paid: int = 1  # a solver's contribution fully paid
    points_failed: int = -2  # a failed or late delivery
    points_slashed: int = -3  # a contribution slashed or clawed back
    points_rewarded: int = 1  # a reporter's issue rewarded
    points_forfeited: int = -3  # a reporter's issue forfeited as junk
    reputation_min_pledge: int = credits(10)  # a funder earns a point per paid bounty it pledged at least this to
    trust_floor_bps: int = 2_500  # a newcomer's trust
    trust_step_bps: int = 2_500  # trust gained per point, up to the whole
    bond_discount_bps: int = 5_000  # the most a solver's bond falls at full trust
    trust_points_per_release: int = 1  # the most positive points an account earns per role per release (#40 D2)
    # the checking layer (proof-of-fix#43, design D1-D4)
    rerun_validators: int = 3  # validators re-running a delivery's checks
    rerun_quorum: int = 2  # matching results that count
    rerun_dissent_penalty_bps: int = 2_000  # of the review bond, for a result off the quorum or no reveal
    planted_share_bps: int = 1_000  # of check and jury jobs, planted with a known answer
    planted_penalty_bps: int = 10_000  # of the bond, for a wrong (re-run) or confidently wrong (jury) planted answer
    planted_fail_bps: int = 8_000  # of planted re-runs, whose checks fail: a lazy "pass" is right on the others
    jury_size: int = 3
    jury_pool: int = 10  # the jury is drawn from this many top evaluators by score
    jury_accept: int = 3  # verdicts that accept a delivery: all of them, AI consensus (owner, 2026-10-24); only a
    # unanimous jury rejects it, and anything else goes to the second jury
    second_jury_size: int = 7  # the second, larger AI jury a split goes to (no person decides a delivery)
    second_jury_accept: int = 5  # its verdicts that accept; fewer reject the delivery (5 of 7 beat 6 of 7, #43)
    second_jury_per_family: int = 3  # its seats per model family (one per operator, as for the first); 3 providers'
    # frontier models fill 7 seats (#47, owner: top models only)
    # oracle fees (owner, 2026-10-25): every check run on a delivery is paid by its bounty, which must hold the
    # oracle reserve (one full attempt's checks); the re-runners and AI evaluators are oracles
    run_fee: int = credits(0.3)  # per run that matched the quorum (and, with validators, the system's hidden runner)
    # CI is an oracle too (owner, 2026-10-25): attested runners, MCP test runners in TEEs, run the public and hidden
    # tests; "validators" (re-runs by staked validators, hidden tests on the system's runner) is the comparison
    ci_mode: str = "attested"
    checks_paid_by: str = "solver"  # #49 (owner): the contributor pays its checks from a deposit posted with its bid,
    # the oracle reserve; "bounty" is #43's rule, kept for the comparison
    ci_runners: int = 2  # per delivery, from different operators and hardware vendors; all must agree
    runner_bond: int = credits(20)
    verdict_fee: int = credits(0.5)  # per counted verdict, on either jury (the flat fee, without tiers)
    # oracle quality (proof-of-fix#47, owner 2026-10-25): the fee by the evaluator's own Brier tier, best first;
    # empty: the flat fee above. The check deposit covers the top tier.
    verdict_fee_tiers: tuple = ((800, credits(0.6)), (1_200, credits(0.45)), (2_000, credits(0.35)))
    model_bar_bps: int = 8_500  # a model is listed while its measured accuracy is at least this (the target is 0.9)
    unproven_penalty_bps: int = 2_000  # of the evaluator's bond, per verdict without valid proof of a listed model
    cheat_margin_bps: int = 500  # Brier above the proven model's expected a(1 - a) that suspends an evaluator
    evaluator_bond: int = credits(10)
    score_window: int = 50  # an evaluator's score: its mean Brier over this many latest scored verdicts
    shadow_verdicts: int = 20  # scored verdicts before an evaluator can qualify
    qualify_brier_bps: int = 2_000  # the most an evaluator's Brier score (of 1) can be to qualify
    confident_bps: int = 9_900  # a planted answer is confidently wrong only if near-certain; Brier handles the rest
    split_rejection_keeps_bond: bool = True  # a split the second jury rejects returns the bond: the solver loses its
    # time, tokens and fee, not its bond (owner, 2026-10-24); clear failures still forfeit it
    rerun_appeal_fee: int = credits(2)  # a solver's fee to have failed re-runs re-run by fresh validators
    failed_reopens_round: bool = True  # a delivered attempt that fails is published and a fresh round opens; False:
    # the next queued bid gets the job at its old price (the rule before #43, kept for the comparison)
    reopen_at_last_price: bool = True  # a reopened round's reserve is at most the failed attempt's price (#43)
    not_solved_challenges: bool = True  # a bounty's fix can be challenged with a case of its issue that still fails
    # award modes (proof-of-fix#60, owner 2026-10-25): "auction" is everything above; "race": no bids, funders set
    # the price, and the first submission through the project's constitution wins; "claim": the race with an
    # exclusive claim, so nobody's work is wasted
    award_mode: str = "race"  # the default since modes v2 (owner, 2026-10-25: "the first valid PR wins")
    registration_fee: int = credits(2)  # race and claim: the AI registration check, paid in coin by the poster
    size_floor_lines: int = 20  # race and claim: an issue estimated below it waits to be bundled (#60 D2)
    top_up_bps_per_week: int = 0  # of an unattempted bounty's value, added by its pledgers each week (#60 D3)
    claim_days_percent: int = 150  # a claim's exclusive time, of the estimated build days (#60 D5)
    claim_min_days: int = 3
    gate_bar_bps: int = 7_000  # the constitution's quality bar, of 1 (#60 D6)
    gate_accuracy_bps: int = 500  # the gates' measurement error, a standard deviation of 1 (an assumption, swept)
    mutation_catch_bps: int = 9_000  # padded tests the mutation gate catches
    # the owner's decisions on modes v1 (2026-10-25, #60 D9)
    start_price_bps: int = 5_000  # race and claim: a bounty opens at this share of its funds...
    price_rise_bps_per_day: int = 1_000  # ...rising by this share a day until the first attempt or claim locks it
    duplicate_catch_bps: int = 9_000  # resubmissions of a failed fix the AI similarity check recognizes
    # the owner's answers on the contract pitfalls (#64): nothing is free
    attempt_fee: int = credits(0.5)  # race: starting an attempt, never refunded
    duplicate_appeal_jury: int = 3  # race: evaluators (one per provider first) judging a duplicate rejection
    published_attempts: str = "all"  # race: the attempts count shows "all", or only "trusted" solvers' (earned reputation)
    # the token emission (proof-of-fix#58, design D2): off by default. Amounts are micro-tokens; a period is a release
    token_emission_per_period: int = 0  # minted only to bounties that closed paid in the period; 0 turns tokens off
    token_emission_decay_bps: int = 100  # of the emission, each period: it halves in about 69 weeks
    token_reporter_bps: int = 1_500  # of a bounty's tokens, to its reporter(s): the same 15 % as its coin (#56 D13)
    founder_share_bps: int = 100  # of each period's emission, to the owner if anything closed: within its cap (rule 3); 1 %, owner 2026-10-29
    founder_periods: int = 208  # 4 years of weekly periods (#58 comment 4025); then the whole emission goes to fixes
    weight_inflation_pct: int = 300  # a registered weight above 300 % of the merge estimate: its reporters forfeit their
    # share, coin and tokens (#58, owner 2026-10-29); 3x: under 1 % of honest reporters forfeit by the estimates' own error (tokens-v2)
    founder_genesis: int = 0  # minted to the owner once, at launch (the genesis option, compared in the report)
    # #56 task 3.4: a fix with no coin reward (a bounty of 0 coin) still runs its instalments, its clawback period,
    # before it closes paid and mints its tokens, as on-chain (the default since 2026-10-30, owner: the simulation
    # follows the contract); off, it closes when its window ends (tokens-v1 to v3)
    zero_reward_instalments: bool = True
    pool_buffer_releases: int = 2  # proof-of-fix#27: releases' worth the contributors' pool may hold before funding
    # scales down (funding follows use); 0 = always fund in full
    release_every_days: int = 7
    # simulation noise
    ai_review_accuracy_bps: int = 8_500
    ai_injection_susceptibility_bps: int = 3_000  # unhardened; 0 when comments are removed
    replay_inconclusive_bps: int = 500

    def __post_init__(self) -> None:
        self.validate()

    # ---------- validation ----------

    def validate(self) -> None:
        tiers = len(self.size_tiers) + 1
        if list(self.size_tiers) != sorted(set(self.size_tiers)) or not all(t > 0 for t in self.size_tiers):
            raise ParamsError("size_tiers must be positive and strictly increasing")
        for name in ("stake_multiplier", "validators", "reward_weight"):
            values = getattr(self, name)
            if len(values) != tiers:
                raise ParamsError(f"{name} needs one value per tier ({tiers})")
            if any(b < a for a, b in zip(values, values[1:])) or min(values) < 1:
                raise ParamsError(f"{name} must be at least 1 and never decrease with size")
        if any(v % 2 == 0 for v in self.validators):
            raise ParamsError("validators per tier must be odd, so a panel has a majority")
        if set(self.release_split_bps) != set(SPLIT_SHARES):
            raise ParamsError(f"release_split_bps must have exactly {SPLIT_SHARES}")
        if sum(self.release_split_bps.values()) != BPS:
            raise ParamsError("release_split_bps must sum to the whole (10,000 bps)")
        if self.release_split_bps["owner"] > self.owner_share_cap_bps:
            raise ParamsError("the owner's share is above the published cap")
        if self.owner_share_cap_bps > 500:
            raise ParamsError("the owner's cap can't be raised above 5 % (openspec/config.yaml rule 3)")
        if set(self.severity_slash_bps) != set(SEVERITIES):
            raise ParamsError(f"severity_slash_bps must have exactly {SEVERITIES}")
        slashes = [self.severity_slash_bps[s] for s in ("cosmetic", "wrong_result", "crash")]
        if slashes != sorted(slashes):
            raise ParamsError("a more severe defect can't slash less than a milder one")
        if not self.risk_multiplier or min(self.risk_multiplier.values()) < 1:
            raise ParamsError("risk multipliers must be at least 1")
        for name, value in vars(self).items():
            if name.endswith("_bps") and isinstance(value, int) and not 0 <= value <= BPS:
                raise ParamsError(f"{name} must be between 0 and 10,000 bps")
            if name.endswith("_bps") and isinstance(value, Mapping) and not all(0 <= v <= BPS for v in value.values()):
                raise ParamsError(f"{name} values must be between 0 and 10,000 bps")
        for name in ("challenge_window_days", "release_every_days", "owner_vesting_months", "appeal_stake_multiplier"):
            if getattr(self, name) < 1:
                raise ParamsError(f"{name} must be at least 1")
        if self.reward_instalments < 1 or self.reward_weight_cap_lines < 1 or self.sponsor_min_accepted < 0:
            raise ParamsError("at least one instalment, a positive weight cap, and a non-negative sponsor threshold")
        if not 0 < self.stake_floor <= self.base_stake:
            raise ParamsError("the stake floor must be positive and at most the base stake (#23)")
        if self.reward_source not in REWARD_SOURCES:
            raise ParamsError(f"reward_source must be one of {REWARD_SOURCES}")
        if self.award_mode not in AWARD_MODES:
            raise ParamsError(f"award_mode must be one of {AWARD_MODES}")
        if (self.attempt_fee < 0 or self.duplicate_appeal_jury < 1 or self.duplicate_appeal_jury % 2 == 0
                or self.published_attempts not in ("all", "trusted")):
            raise ParamsError("the attempt fee can't be negative, and the duplicate appeal jury is odd (#64)")
        if (self.registration_fee < 0 or self.size_floor_lines < 0 or self.claim_min_days < 1
                or self.claim_days_percent < 100 or not all(0 <= v <= BPS for v in (
                    self.top_up_bps_per_week, self.gate_bar_bps, self.gate_accuracy_bps, self.mutation_catch_bps))):
            raise ParamsError("award-mode amounts can't be negative, a claim lasts at least its build, and shares "
                              "are in range (#60)")
        if self.reward_source == "market" and self.challenger_escrow_share_bps:
            # pledges pay only for released fixes (bounty-market spec): a slashed winner's escrow goes back to the
            # bounty in full; challengers are paid from the slashed stake (40 % of the cap) (#15 design D8)
            raise ParamsError("in the market mode the challengers' escrow share must be 0")
        if set(self.market_fee_split_bps) != set(FEE_SHARES) or sum(self.market_fee_split_bps.values()) != BPS:
            raise ParamsError(f"market_fee_split_bps must have exactly {FEE_SHARES} and sum to the whole")
        if self.market_fee_bps * self.market_fee_split_bps["owner"] // BPS > self.owner_share_cap_bps:
            raise ParamsError("the owner's part of the market fee is above the owner's cap")
        if min(self.bounty_deadline_days, self.round_days, self.delivery_days) < 1 or min(
                self.evaluation_fee, self.treasury_bounty_cap, self.treasury_approval_above) <= 0 or self.treasury_budget < 0:
            raise ParamsError("market windows and amounts must be positive (#15)")
        if min(self.points_paid, self.points_rewarded) <= 0 or max(
                self.points_failed, self.points_slashed, self.points_forfeited) >= 0:
            raise ParamsError("success points are positive and failure points negative (#37)")
        if self.trust_floor_bps >= BPS or self.trust_step_bps <= 0 or self.reputation_min_pledge <= 0:
            raise ParamsError("the trust floor is below one, and the trust step and minimum pledge are positive")
        if self.bounty_max_rounds < 1:
            raise ParamsError("a bounty gets at least one round")
        if not 1 <= self.second_jury_accept <= self.second_jury_size or self.second_jury_per_family < 1:
            raise ParamsError("the second jury's threshold fits its size, with a seat per family at least (#43)")
        if min(self.verdict_fee, self.run_fee) < 0:
            raise ParamsError("oracle fees can't be negative")
        bounds = [b for b, _ in self.verdict_fee_tiers]
        if bounds != sorted(bounds) or any(f < 0 for _, f in self.verdict_fee_tiers) or not 0 < self.model_bar_bps <= BPS \
                or not 0 <= self.unproven_penalty_bps <= BPS:
            raise ParamsError("fee tiers best first with fees not negative, and the model bar in range (#47)")
        if self.checks_paid_by not in ("solver", "bounty"):
            raise ParamsError("checks are paid by the solver or by the bounty (#49)")
        if self.ci_mode not in ("attested", "validators") or self.ci_runners < 1 or self.runner_bond <= 0:
            raise ParamsError("CI is attested runners (at least one, bonded) or validators (#43)")
        if not 1 <= self.rerun_quorum <= self.rerun_validators or not 1 <= self.jury_accept <= self.jury_size \
                or self.jury_pool < self.jury_size or self.evaluator_bond <= 0 or self.rerun_appeal_fee <= 0 or min(
                    self.score_window, self.shadow_verdicts) < 1 or not 0 <= self.planted_share_bps < BPS or max(
                    self.rerun_dissent_penalty_bps, self.planted_penalty_bps, self.qualify_brier_bps,
                    self.confident_bps, self.planted_fail_bps) > BPS:
            raise ParamsError("the quorum fits the re-runners, the jury fits its pool, and shares are in range (#43)")
        if not 0 < self.reserve_bps <= BPS or self.trust_points_per_release < 1:
            raise ParamsError("the reserve is a share of the cap above zero, and the trust cap at least 1 (#40)")
        if self.issue_stake <= 0 or (self.treasury_budget and self.finder_fee_bps >= self.market_fee_bps):
            # self-dealing must lose against the treasury's matches; with no treasury there's nothing to farm (#56 D9)
            raise ParamsError("the issue stake is positive, and with a treasury the finder's fee is below the market "
                              "fee (#34)")
        if not self.bounty_stake_bps and self.award_mode != "race":
            raise ParamsError("only the race runs without a stake: its unpaid instalments are the bond (#56 D9)")
        if min(self.token_emission_per_period, self.founder_periods, self.founder_genesis) < 0:
            raise ParamsError("the emission, the founder's periods and the genesis can't be negative (#58)")
        if self.weight_inflation_pct < 100:
            raise ParamsError("the inflation tolerance can't be below the merge estimate itself (#58)")
        if self.founder_share_bps > self.owner_share_cap_bps:
            raise ParamsError("the founder's share is above the owner's published cap (#58, rule 3)")
        if self.pool_buffer_releases < 0:
            raise ParamsError("the pool buffer can't be negative (#27)")
        if self.stake_index_window < 1 or self.reward_cap_stake_multiple < 0:
            raise ParamsError("the index window is at least 1 build, and the reward cap can't be negative (#23)")
        if self.pledge_max_stake_bps + self.check_fee_bps > BPS:
            raise ParamsError("the part of a stake posted from the balance must at least cover the check fee (#19)")
        if self.review_bond <= 0:
            raise ParamsError("the review bond must be positive")
        if self.extension_days < 0 or self.base_stake <= 0 or self.validator_bond <= 0 or self.release_funding <= 0:
            raise ParamsError("amounts must be positive and the extension can't be negative")

    @property
    def oracle_reserve(self) -> int:
        """What checking one full attempt costs: a run fee for each re-run and the hidden tests, and a verdict fee
        for every seat on both juries (#43). A bounty must hold more than this, and its price cap leaves room for it."""
        runs = self.ci_runners if self.ci_mode == "attested" else self.rerun_validators + 1
        return self.run_fee * runs + self.top_verdict_fee * (self.jury_size + self.second_jury_size)

    @property
    def top_verdict_fee(self) -> int:
        """The most one counted verdict can earn: the top tier's fee, or the flat fee (#47)."""
        return max([f for _, f in self.verdict_fee_tiers] + [self.verdict_fee])

    def with_(self, **changes) -> "Params":
        """A copy with some values changed, validated like any published set."""
        for key in ("risk_multiplier", "severity_slash_bps", "release_split_bps", "market_fee_split_bps"):
            if key in changes:
                changes[key] = _frozen(changes[key])
        return replace(self, **changes)

    # ---------- derived values ----------

    def tier(self, changed_lines: int) -> int:
        """The size tier (0-based) of a contribution with this many changed lines."""
        for i, bound in enumerate(self.size_tiers):
            if changed_lines <= bound:
                return i
        return len(self.size_tiers)

    def stake_for(self, changed_lines: int, risk: str = "normal", reward_per_weight: int | None = None) -> int:
        """The fixed stake for this size and risk; with a reward-per-weight index (proof-of-fix#23), a share of the
        expected reward instead, between the floor and the fixed stake for the size, times the risk multiplier."""
        if risk not in self.risk_multiplier:
            raise ParamsError(f"unknown risk class {risk!r}")
        tier = self.stake_multiplier[self.tier(changed_lines)]
        stake = self.base_stake * tier
        if reward_per_weight is not None and self.stake_per_reward_bps:
            expected = reward_per_weight * self.reward_weight_for(changed_lines)
            stake = min(stake, max(self.stake_floor * tier, share(expected, self.stake_per_reward_bps)))
        return stake * self.risk_multiplier[risk]

    def reward_weight_for(self, changed_lines: int) -> int:
        """Linear in changed lines up to the cap (#10), so the parts of a split change weigh no more than the whole;
        the per-tier weights only when linear weights are switched off (for the ablation)."""
        if self.linear_reward_weight:
            return max(1, min(changed_lines, self.reward_weight_cap_lines))
        return self.reward_weight[self.tier(changed_lines)]

    def validators_for(self, changed_lines: int) -> int:
        return self.validators[self.tier(changed_lines)]

    def jurors_for(self, changed_lines: int) -> int:
        return 2 * self.validators_for(changed_lines) + 1


DEFAULTS = Params()  # the bounty market (proof-of-fix#15), awarded by the race (the owner's choice, #60)
AUCTION = Params(award_mode="auction")  # the sealed rounds of #30-#55, kept to compare with and to reproduce those runs
# the legacy pool: a fixed fund per release split by lines changed, the placeholder of runs v1-v5; kept only to
# compare with and to reproduce those runs
LEGACY = Params(reward_source="pool", challenger_escrow_share_bps=5_000)
# the local contract's shape (proof-of-fix#56 design D9), for the replay: the race as it runs on-chain, with no treasury
# or matching, no trust discount, no market fee, no stake (the unpaid instalments are the bond), and challenges decided
# by one final result
CONTRACT = Params(treasury_budget=0, bond_discount_bps=0, market_fee_bps=0, bounty_stake_bps=0,
                  challenge_appeals=False)
# the token emission on (proof-of-fix#58 design D2): 10,000 tokens a week, the founder's share at its default
TOKENS = Params(token_emission_per_period=credits(10_000))  # micro-tokens, on the same scale as credits
