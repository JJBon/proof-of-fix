# Proposal

## Why

The first acceptance run (`reports/acceptance-defaults.md`, 20 seeds) shows the mechanism as specified fails four of its five criteria (ticket: proof-of-fix#10):
- **Spam pays:** spammer +3,027 and splitter +6,533 credits, against +2,453 for an honest contributor.
- **Validators earn nothing** in 11 of 20 honest runs.
- **The collusion criterion is mis-specified:** it measures spam income, not collusion.
- **A self-interested owner gains** on 12 of 20 seeds, by declining others' work.

A bigger stake alone can't fix spam: from 600 credits nobody can afford to contribute. The weak factor is **detection**: hunters earn 8–30 credits, so too few defects are caught. The fixes must make catching defects pay, make being caught cost, stop splitting from paying, and take away the owner's (and every maintainer's) unchecked power over what gets in.

## What Changes

- **A challenger is paid from the escrowed reward.** An upheld challenge pays the challenger a published share of the contribution's escrowed reward, as well as the share of the forfeited stake. Today the reward goes back to the pool and the challenger earns almost nothing.
- **Review duty:**
  - every contribution entering beta gets one reviewer, drawn at random from validators (stake-weighted, excluding the author and linked accounts), who posts a review bond;
  - a completed review is paid from the validators' pool;
  - a reviewer who passed a contribution that is later slashed loses part of the bond.
- **The reward is paid in instalments with clawback.** An accepted contribution's reward is paid in instalments over the following releases. Until the last one, a defect found later can still be challenged and forfeits the unpaid instalments. **BREAKING** for the lifecycle: "accepted" no longer pays the whole reward at once.
- **Splitting doesn't pay.** The weights of a change's parts never add up to more than the weight of the same change as one contribution. Each part still pays its own stake and check fee.
- **Maintainer guardrails** (they apply to the owner too):
  - a maintainer's own contribution needs another maintainer's approval, or a validator panel where there's no other maintainer;
  - declines of others' contributions are recorded with a reason, limited per release, and appealable by the contributor to a validator panel;
  - a change to the published split that raises a share whose role the owner holds needs a validator panel without the owner.
- **Sponsored stakes for newcomers:** an existing contributor can post a newcomer's stake and shares its slash. This replaces the "stake advance" idea in #10, which new accounts could abuse for free.
- **Simulation:**
  - the collusion criterion compares the ring with the same actors acting honestly on the same seed;
  - new actors: reviewer duty for validators, a maintainer who declines others, a sponsored newcomer, and a spammer abusing sponsorship;
  - the acceptance run is repeated.

Out of scope:
- identity or proof of personhood;
- reputation scores;
- anything on a real chain;
- re-proving theorems (#5 follows this change).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `contribution-lifecycle`:
  - the entry stake can be sponsored;
  - payment moves to instalments with clawback;
  - the settlement outcomes change;
  - maintainers' declines and own contributions get guardrails.
- `challenges`:
  - an upheld challenge pays from the escrowed reward;
  - new review duty.
- `release-payouts`:
  - the validators' pool pays completed reviews as well as matching verdicts;
  - the reward weight can't reward splitting;
  - split changes that benefit the owner need a panel.
- `incentive-simulation`:
  - new actors;
  - a counterfactual collusion criterion;
  - a sponsorship-abuse scenario.

Actors and attacks affected: contributors, validators (now also reviewers), maintainers and the owner, newcomers and their sponsors. Covered: spam, splitting, owner and maintainer self-dealing, collusion, and sybil abuse of sponsorship.

## Impact

- **Code:** `pof/params.py` (new parameters), `pof/lifecycle.py`, `pof/challenges.py`, `pof/payouts.py`, `pof/sim/*`, with tests for each changed scenario.
- **Data:** `reports/` gains a second acceptance run with the new defaults, next to the first, which stays as the baseline.
- **No change to `ledger`** (conservation and append-only still hold) or to anything outside this repository.
