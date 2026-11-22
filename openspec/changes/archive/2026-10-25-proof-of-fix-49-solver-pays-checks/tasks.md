# Tasks

## 1. Mechanism

- [x] 1.1 Parameters: the deposit as `oracle_reserve`, the evaluation fee as its forfeitable part, and `checks_paid_by` ("solver" or "bounty"). Verify with tests.
- [x] 1.2 The market (design D1, D2):
  - commit locks the stake and the deposit; void and unrevealed bids forfeit the evaluation fee; losing bids get the deposit back;
  - the assigned bid's checks are paid from its deposit and the rest returns;
  - a late delivery forfeits the evaluation fee;
  - the price cap and minimum target without the reserve.

  Verify with tests for every scenario in the bounty-market delta, and that conservation and pledge accounting hold.

## 2. Simulation

- [x] 2.1 Expected checks in an honest solver's break-even (D3). Verify with a test that it rises by the expected checks over the chance of being paid.
- [x] 2.2 The split farmer and the comparison, with their criteria (D4, D5). Verify with tests that the farmer delivers borderline junk and that the comparison is reported.

## 3. Acceptance run

- [x] 3.1 Run the checking summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-checking-v5.{json,md}`, compared with checking v4. Verify that it reproduces byte for byte.
- [x] 3.2 If a criterion fails, change parameters or rules here, in the open, recorded in the design. Verify that the report passes or names each failure with its cause and a next step.
- [x] 3.3 Post the results on #49, #15 and it-ops#14, update `README.md`, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
