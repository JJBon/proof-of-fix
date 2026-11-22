# Tasks

## 1. Parameters

- [x] 1.1 Add `issue_stake`, `finder_fee_bps`, `matching_share_bps` and `match_cap_bps` (design D2), with validation:
  - the finder's fee is smaller than the market fee;
  - shares are in range;
  - the stake is positive.

  Verify with tests for each validation.

## 2. Mechanism (`pof/market.py`)

- [x] 2.1 Issue stakes (design D1): stake at submission; returned with the finder's fee when the bounty is paid; forfeited to insurance when junk is confirmed; returned when never funded. Verify with tests for "Real issue fixed", "Junk confirmed", "Flag not confirmed", "Never funded" and "Funding your own issue doesn't pay".
- [x] 2.2 Quadratic matching (design D3): at each release's opening, the matching share of the budget is spent on bounties gathering pledges. Verify with tests for "Many small pledgers attract more", "Within the matching budget", "Capped" and "A match completes the target".
- [x] 2.4 Unsolved bounties close (design D6): after `bounty_max_rounds` empty rounds in a row, funds return by input and the reporter's stake returns. Verify with tests for "No one can do it" and "A bid in time".
- [x] 2.3 The price cap with room for both fees, the finder's fee at payment, and refunds in proportion to inputs (design D4); the treasury budget less its matching share. Verify with tests for "Fee split", "Leftover refunded" and "Matched leftover", and the treasury scenarios against the reduced budget, each checking conservation and exact pledge accounting.

## 3. Simulation

- [x] 3.1 Reporters, the staking flood, the match farmer and the self-dealer (design D5). Verify with tests in which each acts as configured.
- [x] 3.2 The report (issues reported, stakes returned or forfeited, finder's fees, pledged credits per paid bounty) and the new criteria, including the counterfactuals: no flood, no matching, and the farmer from one account. Verify with tests of each criterion's computation.
- [x] 3.3 Summary sweeps (issue stake, finder's fee, matching share). Verify with a test that the summary has them.

## 4. Acceptance run

- [x] 4.1 Run the market summary on 100 seeds (sweeps on 20), and commit `reports/acceptance-market-v2.{json,md}` with the v1 comparison. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails, change parameters or rules here, in the open, recorded in the design. Verify that the final report passes or names each failure with its cause and a next step.
- [x] 4.3 Post the comparison on #34, #15 and it-ops#14, update `README.md`, verify the documented commands, and run the check.

## Workflow follow-up

- Review with the owner, then archive.
- Next: reputation (solvers, reporters, funders), which also weights matching by trust.
