# Tasks

## 1. Parameters and mechanism

- [x] 1.1 Add `reserve_bps` (7,500) and `trust_points_per_release` (1), with validation (the reserve in range; the cap at least 1). Verify with tests.
- [x] 1.2 The reserve in `Market` (design D1): reveals above it are void; assignment and runner-up prices are capped at it; a lone bid gets it. Verify with tests for "Second price", "Only one bid", "No bid" and "Above the reserve".
- [x] 1.3 The per-release trust cap in `Reputation` (design D2). Verify with tests for "Capped per release" and "A failure" (uncapped), and that recomputing from the events still matches.

## 2. Simulation

- [x] 2.1 Break-even from a solver's record (design D3). Verify with a test for "A solver that fails more".
- [x] 2.2 Criteria (design D4): no ring of 2–6 gains; bluffing at each elasticity; the reserve sweep with bounties paid and unsolved. Verify with tests of each computation.

## 3. Acceptance run

- [x] 3.1 Run the market summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-market-v4.{json,md}` with the v3 comparison. Verify that it reproduces byte for byte.
- [x] 3.2 If a criterion fails, change parameters or rules here, in the open, recorded in the design. Verify that the final report passes or names each failure with its cause and a next step.
- [x] 3.3 Post the comparison on #40, #15 and it-ops#14, update `README.md`, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
- Next under #15: the AI jury, then decentralized checking and the real-data measurement (with a budget).
