# Tasks

## 1. Mechanism

- [x] 1.1 Parameters: `model_bar`, the fee schedule by Brier tier, `cheat_margin`, and seats from the leaderboard (amended from the weighted draw). Verify with tests.
- [x] 1.2 Models proven per verdict (amended from declared models), the reputable list, suspension, tiered fees from the deposit, the deposit at the top tier, and seats from the leaderboard, top to bottom (D2–D5, amended). Verify with tests for every scenario in the checking delta.

## 2. Simulation

- [x] 2.1 The model catalogue, operators' choice, and the cheat (D1, D5, D6). Verify with tests that operators pick the model D3 predicts, and that the cheat is suspended.
- [x] 2.2 The criteria and the flat-fee comparison (D6). Verify with tests of each computation.

## 3. Acceptance run

- [x] 3.1 Run the checking summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-checking-v6.{json,md}`, compared with checking v5. Verify that it reproduces byte for byte.
- [x] 3.2 If a criterion fails, change parameters or rules here, in the open, recorded in the design. Verify that the report passes or names each failure.
- [x] 3.3 Post the results on #47, #15 and it-ops#14, update `README.md`, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
- The real-data measurement replaces D1's assumed accuracies and sets D2's bar.
