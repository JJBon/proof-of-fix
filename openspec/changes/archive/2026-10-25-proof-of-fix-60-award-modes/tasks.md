# Tasks

## 1. Mechanism

- [x] 1.1 Parameters (D1–D6): `award_mode`, `registration_fee`, `size_floor_lines`, `estimate_error`, `top_up_bps_per_week`, `claim_days`, `gate_bar`, `gate_accuracy`, `mutation_catch_bps`, with validation. Verify with tests.
- [x] 1.2 The registration check and the bundle pool (D2), and prices set by funders, including 0 coin (D3). Verify with tests for each scenario in the bounty-market delta.
- [x] 1.3 The race (D4) and claim then build (D5) in `pof/market.py`, with the auction's paths unchanged. Verify with tests for each scenario, and that checking v6's base run is unchanged in `auction` mode.
- [x] 1.4 The constitution's gates (D6) in `pof/checking.py`. Verify with tests for each scenario in the checking delta.

## 2. Simulation

- [x] 2.1 Fix quality and gate measurement; solvers racing and claiming, with effort and waste counted (D4–D7). Verify with tests.
- [x] 2.2 The spam poster, padder, second identity racing and inflater, and rings in every mode (D7). Verify with tests.
- [x] 2.3 The comparison across modes in the summary (D7, D8). Verify with tests of each computation.

## 3. Acceptance run

- [x] 3.1 Run modes v1 (D8) and commit `reports/acceptance-modes-v1.{json,md}`. Verify that it reproduces byte for byte.
- [x] 3.2 If a criterion fails in a mode, report it, and fix what's a bug here in the open, recorded in the design. Verify that the report passes or names each failure per mode.
- [x] 3.3 Post the results and the recommended default on #60, #15 and #55, update `README.md`, and run the check.
