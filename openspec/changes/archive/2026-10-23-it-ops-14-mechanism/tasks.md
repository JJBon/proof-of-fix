# Tasks

## 1. Package and CI

- [x] 1.1 Create the `pof/` package and `pof/sim/` layout (design D3), with `tests/` holding one import test; verify `bash scripts/check.sh` runs the Python tests locally.
- [x] 1.2 Confirm the CI host has `python3` (3.10 or later) and `npx` for `scripts/check.sh`: the first PR's `pof / check` log shows the Python tests and the OpenSpec validation running. If either is missing, adjust `check.sh` (or the runner image, through a platform PR) before going on.

## 2. Ledger and parameters

- [x] 2.1 Implement `pof/ledger.py`: pseudonymous accounts, append-only entries with reason and reference, refusal of negative balances, reversing entries for corrections, and a conservation check. Verify with tests for each scenario in `specs/ledger/spec.md`, including a randomized sequence that keeps the sum of balances equal to the issued total.
- [x] 2.2 Implement `pof/params.py` with the defaults from design D5 as one frozen dataclass. Validation: shares sum to 1, owner share ≤ cap, tiers ordered. Verify with tests that refuse an owner share above the cap and shares that don't sum to 1.
- [x] 2.3 Verify that nothing in `pof/` opens a network connection or reads keys: a test walks the package's imports and fails on `socket`, `http`, `urllib`, `ssl` or `subprocess`.

## 3. Contribution lifecycle

- [x] 3.1 Implement submission with an entry stake by tier, the deterministic gate (check fee), maintainer decline and withdrawal (`pof/lifecycle.py`). Verify with tests for the scenarios "Stake locked on submission", "Insufficient balance", "Larger contributions need larger stakes", "Checks pass/fail", "Maintainer declines" and "Withdrawn before beta".
- [x] 3.2 Implement escrow on entry to beta, the challenge window with one extension, and settlement as accepted or slashed. Verify with tests for "No early payout", the two window scenarios, "Accepted" and "Slashed", each checking the ledger entries.

## 4. Challenges

- [x] 4.1 Implement filing with a challenger stake, proof admission (passes before, fails after), the filing fee and bisection attribution (`pof/challenges.py`). Verify with tests for "Valid regression proof", "No proof", "Bug from an earlier contribution" and the formula-reference scenario, using a simulated proof object.
- [x] 4.2 Implement validator selection (stake-weighted, seeded, parties and linked accounts excluded) and commit-reveal with penalties. Verify with tests for "Parties excluded", "Selection reproducible", "Reveal matches" and "No reveal".
- [x] 4.3 Implement the layered judgement: replay, then two AI reviewers (advisory; disagreement goes to validators; comments removed), then an appeal to jurors. Add severity slashing with the cap. Verify with tests for "Replay settles it", "AI review alone can't slash", "Instructions hidden in a comment", "Appeal overturns", "Severity sets the slash" and "Cap".

## 5. Release payouts

- [x] 5.1 Implement the release split with rounding remainders to insurance (design D2): contributors by reward weight, and validators by verdicts that matched the outcome (`pof/payouts.py`). Verify with tests for "Split adds up", "Shares can't change mid-release", "Only accepted contributions are paid" and "Overturned verdict earns nothing".
- [x] 5.2 Implement the author's escrow and claim verification: a signed statement plus a matching commit in the upstream repository, both simulated. Verify with tests for "Unclaimed share accrues", "Verified claim" and "Unverified claim"; no code path assigns an author address.
- [x] 5.3 Implement the owner's share (cap, vesting, forfeit to insurance, no validator weight), the infrastructure roll-over and insurance claims up to the limit. Verify with tests for "Cap enforced", "Owner can't validate on the share", "Insurance pays out" and "Unspent infrastructure funds roll over".

## 6. Baseline data

- [x] 6.1 Write `scripts/fetch_baseline.py` (via `gh`, aggregated in memory) and commit `data/gridcraft_baseline.json` with the size, time-to-merge, review and weekly-volume distributions. Verify with a test that the file has no usernames, PR numbers or titles, and that its changed-lines median matches it-ops#14 comment 3323 within 10 %. For the other figures, the full window supersedes that 40-PR sample (time to merge and review share differ; recorded on it-ops#14).

## 7. Simulation

- [x] 7.1 Implement the actors (honest contributor, spammer including a splitting variant, griefer, colluding validators, self-interested owner with every move in design D7) in `pof/sim/actors.py`. Verify with tests in which each actor runs alone in a tiny scenario and acts as configured.
- [x] 7.2 Implement the scenarios (`honest`, `spam`, `griefing`, `collusion` with a stake-share sweep, `owner` honest vs self-interested, `replay` from the baseline, and a `risk` sweep: a share of high-risk contributions with risk multipliers 1×, 2× and 3×, design D5) and the CLI `python3 -m pof.sim run`. Verify with a test that the same seed gives identical ledgers and reports, and that the replay with the mechanism off matches the baseline sizes and weekly volume within tolerance.
- [x] 7.3 Implement `pof/sim/report.py` with every metric in `specs/incentive-simulation/spec.md` and the acceptance check, which names the criterion, scenario and seed on failure. Verify with a test on a deliberately unsound parameter set (owner share above cap by bypassing validation, or no challenger stake) that the report flags it.

## 8. Acceptance run

- [x] 8.1 Run every scenario over at least 20 seeds with the default parameters. Commit the summary report under `reports/` and post it on it-ops#14: returns per actor type, the measured collusion threshold, and the owner's honest vs self-interested payout. Verify that each acceptance criterion passes, or that every failure is listed with the parameter change proposed for it (a follow-up change, not a silent edit here).
- [x] 8.2 Document how to run the simulation and read the report in `README.md`, and verify the documented commands run as written. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- Next changes: real GridCraft builds and proofs in containers; parameter tuning; then, after the PoC review, decentralized hosting and the chain choice.
