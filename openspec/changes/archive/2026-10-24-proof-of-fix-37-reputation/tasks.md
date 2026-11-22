# Tasks

## 1. Parameters and reputation

- [x] 1.1 Add the design D4 parameters, with validation (failure points negative and success points positive; the floor and step between 0 and 1; the discount in range). Verify with tests.
- [x] 1.2 `pof/reputation.py` (design D1, D2): scores per account and role, a `reputation` ledger event per change, trust, and a recompute from the events. Verify with tests for "A paid job", "A failure", "A small pledge", "Recomputed from the records", "No transfer", "A newcomer" and "Proven".

## 2. Market

- [x] 2.1 The market records outcomes in reputation (design D1): paid bounties for the solver and the funders, failed deliveries, slashes and clawbacks, rewarded and forfeited issues. Verify with tests that each outcome changes the right score.
- [x] 2.2 The uses (design D3): the bond discount at commit and when a runner-up re-posts; trust-weighted matching; `rank_candidates` for the treasury. Verify with tests for "A proven solver's bond", "New accounts draw little", "Ranked by trust", and the unchanged scenarios when everyone has the same trust.

## 3. Simulation

- [x] 3.1 The world's treasury ranks by `rank_candidates`, and the reputation farmer (design D5). Verify with tests: it builds trust, then turns.
- [x] 3.2 The report (scores, trust and bonds per kind) and the reputation criteria: crowd-out at 50 % detection, farming significant, the reputation farmer, bonds against no discount. Verify with tests of each criterion's computation.
- [x] 3.3 Summary sweeps (the trust floor, the bond discount). Verify with a test.

## 4. Acceptance run

- [x] 4.1 Run the market summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-market-v3.{json,md}` with the v2 comparison. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails, change parameters or rules in the open, recorded in the design. Verify that the final report passes or names each failure with its cause and a next step.
- [x] 4.3 Post the comparison on #37, #15 and it-ops#14, update `README.md`, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
- Next under #15: a reserve price (the ring of 4), then the AI jury.
