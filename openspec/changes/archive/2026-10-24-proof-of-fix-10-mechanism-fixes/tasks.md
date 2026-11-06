# Tasks

## 1. Parameters

- [x] 1.1 Add the design D2 parameters to `pof/params.py` with validation: shares in range, at least 1 instalment, a positive weight cap, and linear weights replacing the per-tier `reward_weight` behind a switch, so the ablation can restore the old weights. Verify with tests for each new validation and for "One change split into eight" (the weights add up to no more).

## 2. Lifecycle

- [x] 2.1 Sponsored stakes: `submit(..., sponsor=)`, sponsor eligibility, and refunds and forfeits to and from the sponsor. Verify with tests for "A newcomer is sponsored", "A sponsored contribution is slashed" and "Only proven contributors sponsor".
- [x] 2.2 Instalments and clawback (design D4): acceptance pays the first instalment and the stake; `pay_instalment` and `claw_back` work as the spec says. Verify with tests for "Paid in instalments", "Accepted", "Defect found after acceptance" and "After the last instalment", each checking the ledger.
- [x] 2.3 Maintainer guardrails (design D5): another approver for a maintainer's own contribution, the decline limit, decline appeals and records. Verify with tests for "Approved by another maintainer", "Only maintainer", "Maintainer declines" (recorded with a reason), "Over the limit" and "Decline overturned on appeal".

## 3. Challenges

- [x] 3.1 An upheld challenge pays `challenger_escrow_share_bps` of the escrowed reward, in the window and during clawback. Verify with the updated "Upheld challenge pays the challenger" test, including the rest returning to the contributors' pool.
- [x] 3.2 Review duty (design D3): drawing the reviewer with exclusions, the bond, the report, and the missed-defect and no-report penalties. Verify with tests for "Reviewer drawn", "Review completed", "Missed defect" and "No report".

## 4. Payouts

- [x] 4.1 The validators' pool paid by units of work (matching verdicts plus completed reviews), and instalments paid at each `open_release`. Verify with tests for "Overturned verdict earns nothing", "Reviews are paid work" and a release paying instalments of earlier contributions.
- [x] 4.2 A split change that raises a share whose role the owner holds goes to a panel without the owner. Verify with a test for "A change that would benefit the owner".

## 5. Simulation

- [x] 5.1 Actors (design D1, D3, D5, D6): hunting that responds to pay with `hunt_elasticity`, reviewer duty, the declining maintainer with appeals, the sponsored newcomer, the sponsorship abuser, and a padder. Verify with tests in which each runs alone and acts as configured.
- [x] 5.2 Scenarios and criteria:
  - a `sponsorship` scenario;
  - the counterfactual collusion criterion (design D7);
  - the updated acceptance check (reviewers must earn; splitters, padders and abusers must lose).

  Verify that the existing simulation tests still pass, plus a test that the counterfactual run differs only in the ring's behaviour.
- [x] 5.3 Summary additions: the elasticity sweep (0, 0.5, 1), the review-detection sweep, and the ablation table (design D8). Verify with a test that the summary has every table.

## 6. Acceptance run

- [x] 6.1 Run `python3 -m pof.sim summary --seeds 20` with the new defaults. Commit `reports/acceptance-v2.json` and `.md` next to the first run, with every criterion's result, the ablation table and the elasticity sweep. Verify that it reproduces byte for byte.
- [x] 6.2 If a criterion fails, tune the parameters in this change (not silently): record each changed value and its reason in design D2, and re-run 6.1. Verify that the final report passes every criterion, including at elasticity 0, or that it names each remaining failure, its cause and a proposed next step.
- [x] 6.3 Post the comparison (first run vs this one) on it-ops#14 and #10, and update `README.md` for the new scenario and options. Verify the documented commands run as written. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- Then #5 (the Lean proofs) against the fixed rules.
