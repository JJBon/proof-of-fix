# Tasks

## 1. Parameters

- [x] 1.1 Add `stake_per_reward_bps`, `stake_floor`, `stake_index_window` and `reward_cap_stake_multiple` (design D2) with validation:
  - the floor is positive and at most `base_stake`;
  - the window is at least 1;
  - the cap is at least 0;
  - 0 switches the index or the cap off.

  Verify with tests for each validation.

## 2. Mechanism

- [x] 2.1 The index (design D1, D3):
  - `ship_beta` records the offered rate as a `stake_index` event and keeps the window;
  - the lifecycle computes the stake from the index, clamped between the floor and the fixed stake, times risk;
  - the fixed stake applies before any build.

  Verify with tests for "No history yet", "The stake follows the reward", "Never above the fixed stake", "Larger contributions still need larger stakes" and "Anyone can recompute the stake" (recomputed from the recorded events alone).
- [x] 2.2 The reward cap in `ship_beta` (design D4). Verify with tests for "Lone contribution in a sparse release", "Under the cap" and "Nothing lost", each checking conservation.

## 3. Simulation

- [x] 3.1 The world and the index gamer (design D6):
  - submissions use the lifecycle's stake;
  - the index gamer joins the spam scenario;
  - the report gives its mean stake before and after its turn, and the contributors' pool balance at the end.

  Verify with tests: the gamer floods, then turns, and the index falls during its flood.
- [x] 3.2 The capital criterion against the fixed-stake rules. Verify with tests: the counterfactual differs only in `stake_per_reward_bps` and `reward_cap_stake_multiple`, and the criterion reports both numbers.
- [x] 3.3 Summary: the index and cap sweeps, and the "no index" and "no reward cap" ablation rows, with the pledge sweep kept. Verify with a test that the summary has the new tables.

## 4. Acceptance run

- [x] 4.1 Run `python3 -m pof.sim summary --seeds 20`, and commit `reports/acceptance-v4.json` and `.md` next to v3. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails (including at hunting elasticity 0), change the parameters or rules in this change, in the open: record each change and its reason in the design, and re-run 4.1. Verify that the final report passes every criterion, or names each remaining failure, its cause and a proposed next step. Include a recommendation on pledges (design D5).
- [x] 4.3 Post the comparison (v3 vs v4) on #23 and it-ops#14, update `README.md`, and verify the documented commands run as written. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- In #5, add the theorem that reward ÷ stake stays within the band, next to the pledge theorems from #19.
