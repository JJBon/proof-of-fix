# Tasks

## 1. Parameters and the checking module

- [x] 1.1 Add the checking parameters (design D1–D4) with validation (quorum at most the re-runners, accept at most the jury size, shares in range). Verify with tests.
- [x] 1.2 `pof/checking.py`: signed re-runs with commit-reveal, quorum, dissent penalty and a fresh draw on no quorum (D1). Verify with tests for "All agree", "One disagrees", "No quorum" and "Results can't be copied".
- [x] 1.3 Planted cases: drawn at the published share, scored, penalized, and revealed on the ledger once settled (D2). Verify with tests for "A lazy validator" and "Revealed after settling".
- [x] 1.4 Evaluators: registration with a bond, operator and family; the seeded draw from the top with one seat per operator and family; shadow mode (D3, D4). Verify with tests for "One seat per family", "Selection reproducible" and "Shadow mode".
- [x] 1.5 Jury verdicts: commit-reveal with probability and evidence, the thresholds, escalation to a panel, and Brier scoring on planted answers and revealed fates (D3, D4). Verify with tests for "Accepted", "Rejected unanimously", "Split" and "Scored on the outcome".

## 2. Market and payouts

- [x] 2.1 `Market.deliver` through the re-runs and the jury; a rejection fails the delivery. Verify with tests for "Delivered in time" and "Rejected by the jury".
- [x] 2.2 Units of work for matching re-runs and jury verdicts that held up. Verify with a test for "Re-runs and jury verdicts are paid work", and that conservation holds.

## 3. Simulation

- [x] 3.1 The error model, honest validators and evaluators, and their effort (D5). Verify with a test for "Correlated errors".
- [x] 3.2 The attackers: lazy validator, herding evaluator, copy operator, crafting solver, bug planter; and the agreement-scoring comparison (D6). Verify with a test per attacker that it behaves as specified.
- [x] 3.3 Criteria and sweeps (D7). Verify with tests of each computation.

## 4. Acceptance run

- [x] 4.1 Run the checking summary on 100 seeds (sweeps on 20), and commit the report, compared with market v4. Verify that it reproduces byte for byte. Done as `reports/acceptance-checking-v4.{json,md}`; v1–v3 are the intermediate runs.
- [x] 4.2 If a criterion fails, change parameters or rules here, in the open, recorded in the design. Verify that the final report passes or names each failure with its cause and a next step. Design notes 1–26 record the changes; the one remaining failure (honest solvers' earnings under consensus) is named, with model accuracy as its cause and #47 as the next step.
- [x] 4.3 Post the results on #43, #15 and it-ops#14, update `README.md`, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
- Next: the oracle and architecture desk study (#44), using what the oracle has to report from this change; the real-data measurement once the budget is approved.
