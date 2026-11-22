# Proposal

## Why

With the #10 rules, the mechanism passes every acceptance criterion, but it throttles contributors at GridCraft's real pace. In the replay, about 1,146 submissions per run are unaffordable: only 629 are made against about 1,780 attempted (`reports/acceptance-v2.md`, ticket proof-of-fix#19).

The capital is held by the mechanism itself. Here is one replay run at day 35, per honest contributor:
- 573 credits of stake are locked, and 428 of those are on work already accepted, waiting for its instalments;
- 334 credits of rewards are unpaid in escrow;
- only 38 credits are free.

The obvious fixes break the #10 results:
- a smaller stake lets defective work pay again;
- releasing the stake at acceptance reopens the instalment leak that design D9 closed.

## What Changes

- **Pledged stake (earned collateral).** A contributor with accepted work can cover part of a new contribution's entry stake with the unpaid rewards of their own accepted contributions still in clawback (the *backing* contributions). Limits:
  - Part of every stake is always posted from the balance. The pledged share of a stake is capped by a published parameter.
  - Only part of each backing contribution's unpaid reward can be pledged. The rest stays in its escrow to cover that contribution's own clawback.
  - Nothing can be pledged from a contribution with an open challenge.
- **The pledge is at risk like any stake:**
  - When the new contribution is slashed, the forfeit comes from the cash part of the stake first, then from the pledge.
  - When the new contribution settles, the pledge goes back to the backing contribution's escrow, or to the contributor if that contribution's clawback has ended.
  - **A clawback reaches the pledge:** if a backing contribution is clawed back while its reward is pledged, the pledge, when it comes back, goes where the clawback sends the escrow (to the challenger and the reward's source), not to the contributor.
- **Instalments shrink while pledged.** A backing contribution's instalments are paid from what remains in its escrow; the pledged part comes back later. Nothing is paid twice.
- **Simulation:**
  - contributors pledge when their balance falls short;
  - an attacker that pledges to stack defective contributions;
  - the acceptance run is repeated with pledging open to every actor;
  - a new capital criterion: unaffordable submissions in the replay must fall by at least a third against acceptance v2, with every other criterion still passing.

**Out of scope:**
- reputation-based stake discounts;
- releasing a stake before its last instalment;
- the bounty market (#15);
- re-proving theorems (#5 adds a pledge theorem after this lands);
- anything on a real chain (rule 1).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `contribution-lifecycle`:
  - the entry stake can be partly pledged from unpaid rewards (two new requirements: "Pledged stake" for the limits, and "Pledges in settlement" for the forfeit order and return);
  - "Entry stake" names the pledge as a source;
  - "Clawback" reaches pledged rewards.
- `incentive-simulation`: two new requirements.
  - "Acceptance with pledged stakes": the criteria hold with pledging open in every attack scenario, plus the capital criterion.
  - "Actors for pledges": the pledging contributor and the stacking attacker.

**Actors and attacks affected:** contributors (honest and attacking), challengers (a clawback's reach now includes pledges), sponsors (unchanged, but a sponsored stake can't also be pledged). Covered:
- spam and sybils using pledges;
- stacking several defective contributions on the same unpaid reward;
- chained pledges;
- a defect proven in a backing contribution while its reward is pledged.

## Impact

- **Code:**
  - `pof/params.py`: two new parameters, the pledge caps;
  - `pof/lifecycle.py`: pledges at submission, forfeit order, return on settlement, deferred clawback;
  - `pof/sim/*`: actors pledge, the stacking attacker, the capital criterion, sweeps of the two caps and an ablation row;
  - tests for each.
- **Data:** `reports/acceptance-v3.{json,md}` next to v2.
- **No change** to `ledger` (pledges are ordinary transfers, so conservation holds), `challenges` (the forfeit distribution is unchanged) or `release-payouts`.
