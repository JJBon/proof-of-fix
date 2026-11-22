# Tasks

## 1. Mechanism

- [x] 1.1 Parameters `attempt_fee` and `duplicate_appeal_jury`, with validation. Verify with tests.
- [x] 1.2 The attempt fee and the late fee in `race_start` and `race_submit` (D1, D2), and the duplicate appeal (D3). Verify with tests for each scenario in the bounty-market delta.

## 2. Simulation

- [x] 2.1 False duplicates at `duplicate_false_bps`, honest solvers appealing them, and the appeal jury's vote (D3). Verify with tests.
- [x] 2.2 The fake attempter and its honest twin (D4), with its criterion. Verify with tests.

## 3. Acceptance run

- [x] 3.1 Run modes v3 (D5) and commit `reports/acceptance-modes-v3.{json,md}`, compared with v2. Verify that it reproduces byte for byte.
- [x] 3.2 If a criterion fails, fix it here in the open, recorded in the design. Verify that the report passes or names each failure.
- [x] 3.3 Post the results on #64, #56 and #15, update `README.md`, and run the check.
