# Proposal

## Why

Acceptance run v3 (`reports/acceptance-v3.md`, ticket proof-of-fix#23) traced two failures to one mismatch: a **fixed** stake against a reward that **swings with volume**.

- **The capital throttle is a stake-size problem.**
  - The 75-credit stake was tuned on the small scenarios, where a reward is 3–6 times the stake. At GridCraft's volume, a reward is about 0.8 of the stake.
  - Pledges (#19) freed 3 % of the blocked submissions, while a lower stake frees far more (−32 % at 40 credits, −59 % at 25).
  - A flat lower stake isn't the answer: a stake of 10 lets defective work pay in the small scenarios.
- **A reward has no cap.** In a sparse release one contribution takes most of the contributors' pool. One escaped defect earned 2,148 credits, about 30 times its stake, and made defective work pay at hunting elasticity 0.

What keeps defective work from paying is the ratio of reward to stake. That ratio should stay in a band at any volume.

## What Changes

- **Indexed stake.** A contribution's entry stake becomes a published share of its expected reward, then multiplied by the risk class. Its bounds:
  - **floor:** a published minimum per size tier;
  - **ceiling:** today's fixed stake for its size.

  The expected reward is the reward per unit of weight over a window of recent releases, times the contribution's weight. It's published, so anyone can recompute it. Before any release has paid rewards, the fixed stake applies (cold start).
- **Reward cap.** A contribution's escrowed reward is at most a published multiple of its stake. The excess stays in the contributors' pool and rolls over.
- **Simulation:**
  - a new attacker, the **index gamer**, floods a release with small sound contributions to push stakes down, then submits defective work at the lower stake;
  - the **capital criterion** now compares the mechanism with the **fixed-stake rules** of acceptance v2 on the same seeds, rather than pledges with no pledges. Its target, a third fewer unaffordable submissions in the replay, stays;
  - the safety criteria must hold at **hunting elasticity 0** too;
  - pledges stay as they are (on, at most half a stake), and are swept, so the owner can decide on them with v4's data.

**Out of scope:**
- changing the release funding or the split;
- the bounty market (#15);
- re-proving theorems (#5 adds the band after this lands);
- anything on a real chain (rule 1).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `contribution-lifecycle`: a new requirement, "Stake indexed to the expected reward". The entry stake still grows with size and risk, as "Entry stake" requires.
- `release-payouts`: a new requirement, "Reward capped relative to the stake".
- `incentive-simulation`:
  - "Acceptance with pledged stakes" is replaced by "Acceptance with pledges", which keeps only its safety part;
  - a new "Capital criterion" against the fixed-stake rules;
  - new "Actors for the indexed stake" (the index gamer).

**Actors and attacks affected:**
- **Contributors:** lower stakes where rewards are small, and capped rewards in sparse releases.
- **Challengers and hunters:** challenger stakes and the slash shares scale with the contributor's stake, so their pay changes.
- **Covered:** spam, sybils and stacking at lower stakes; gaming the index by flooding; the sparse-release outlier.

## Impact

- **Code:**
  - `pof/params.py`: four parameters (the stake's share of the expected reward, the floor, the index window, the reward cap);
  - `pof/payouts.py`: the reward-per-weight index published at each beta build, and the cap in `ship_beta`;
  - `pof/lifecycle.py`: the stake from the index at submission;
  - `pof/sim/*`: the index gamer, the new capital counterfactual, sweeps and ablation rows;
  - tests for each.
- **Data:** `reports/acceptance-v4.{json,md}` next to v3.
- **No change** to `ledger` (the cap's excess simply stays in the pool) or to `challenges` (its shares are already relative to the contributor's stake).
