# Tasks

## 1. Parameters

- [x] 1.1 Add the design D2 parameters (`reward_source`, `bounty_deadline_days`, `round_days`, `bounty_stake_bps`, `evaluation_fee`, `market_fee_bps` with its split, `treasury_budget`, `treasury_bounty_cap`, `treasury_approval_above`), with validation:
  - the mode is one of the two;
  - the fee split sums to the whole;
  - the owner's part of the fee stays within the owner's cap;
  - amounts are positive.

  Verify with tests for each.

## 2. Market mechanism (`pof/market.py`)

- [x] 2.1 Bounties and pledges: open a bounty with a target and a deadline; pledges go to its escrow; a missed target refunds every pledge. Verify with tests for "Target reached" and "Target missed".
- [x] 2.2 Treasury bounties: the per-release budget, issued only on funding; the cap per bounty; the panel above the threshold. Verify with tests for "Within the budget", "Over the budget" and "A large proposal".
- [x] 2.3 Sealed rounds for the job (design D9): commit a sealed price at most the cap, with the stake and fee locked; reveal prices after the deadline; a mismatched or missing reveal forfeits the fee. Verify with tests for "Bid accepted", "Nothing to copy" and "Reveal doesn't match".
- [x] 2.4 Assignment and delivery (design D9):
  - the cheapest bid is assigned at the second price or the cap, its stake held as a bond, and the others refunded and queued;
  - delivery through the gate within `delivery_days`;
  - a failure or a late delivery forfeits the bond to the bounty and the fee;
  - the next queued bid is offered the job (it posts its stake again, or is skipped);
  - after a slash, clawback or decline, the same.

  Verify with tests for "Second price", "Only one bid", "No bid", "Delivered in time", "Not delivered", "Runner-up can't post its stake" and "Winner slashed".
- [x] 2.5 Payment and fees:
  - `Lifecycle.submit` takes an explicit stake;
  - the winner's price is escrowed from the bounty;
  - the market fee is split;
  - the leftover is refunded after the last instalment (design D4);
  - `Releases` works in the market mode (no pool funding).

  Verify with tests for "Paid on release", "Fee split" and "Leftover refunded", and that the legacy mode is unchanged (the existing tests pass).

## 3. Simulation

- [x] 3.1 Issues and solvers (design D5): arrival, value, difficulty, private cost and defects; no per-person data. Verify with tests: the arrival rate matches the baseline, and costs are positive and private to each solver.
- [x] 3.2 Actors (design D6). Verify with tests in which each acts as configured, alone.
- [x] 3.3 Market scenarios, report and criteria (design D7), the summary (100-seed verdicts, 20-seed sweeps), and `python3 -m pof.sim market ...`. Verify with tests for "A market run", "Reported per bounty", and each criterion's computation, including the exact pledge accounting.

## 4. Acceptance run

- [x] 4.1 Run the market summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-market-v1.{json,md}`. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails, change parameters or rules in this change, in the open: record each change and its reason in the design, and re-run 4.1. Verify that the final report passes, or names each failure with its cause and a next step. If it passes, propose making `market` the default.
- [x] 4.3 Post the comparison (legacy v5 vs market v1) on #15 and it-ops#14, update `README.md`, and verify the documented commands. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- The next changes under #15: the AI jury and reputation, decentralized checking, bug planters, and the real-data measurement (with a budget).
