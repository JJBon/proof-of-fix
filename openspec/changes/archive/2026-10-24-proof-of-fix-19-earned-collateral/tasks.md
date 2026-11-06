# Tasks

## 1. Parameters

- [x] 1.1 Add `pledge_max_stake_bps` and `pledge_max_escrow_bps` (design D2) to `pof/params.py`, with range validation. Verify with tests: each cap must be within 0–10,000, and a cap of 0 must turn pledging off.

## 2. Lifecycle

- [x] 2.1 Pledges at submission (design D1, D8): `submit(..., pledges=)`, a list of (backing contribution, amount). Checks:
  - the backing contribution is the contributor's own, accepted and in clawback;
  - no challenge is open on it;
  - both caps hold;
  - there's no sponsor.

  The pledge moves by transfer from each backing escrow to the new stake account, and the contribution records it. Verify with tests for "Stake partly pledged", "Pledge over a limit", "Backing contribution under challenge", "Sponsored stake" and "Insufficient balance", each checking that nothing is locked on refusal.
- [x] 2.2 Forfeit order and return (design D3, D5). The check fee and slashes come from the balance part first. Every refund path (withdraw, decline, failed checks, last instalment, slash and clawback remainders) returns:
  - each pledge to its backing escrow while that contribution is in clawback, otherwise to the contributor;
  - the balance part to the contributor.

  Verify with tests for "Pledged contribution slashed" (a cosmetic and a wrong-result slash leave the pledge whole within the check-fee residue, and a crash reaches it) and "Pledge returned on settlement" (in clawback, and after the clawback ended). Each test checks conservation.
- [x] 2.3 Deferred clawback reach (design D4): `claw_back` marks the backing contribution's outstanding pledges as forfeited to the clawback's distribution. When they come back, they go to the challenger's escrow share and to the reward's source. Verify with a test for "Defect found while the reward is pledged": the other contribution keeps its full stake until it settles, then the pledge's remainder goes to the challenger and the source, and nothing reaches the contributor.
- [x] 2.4 Chains (design D6): a pledged contribution, once accepted, can pledge its own reward but never its stake. Verify with a three-link test (A backs B, then B backs C), in which clawbacks and slashes at each link conserve value and respect both caps.

## 3. Simulation

- [x] 3.1 Actors (design D7):
  - every contributor with accepted work pledges when short, the smallest amount needed, from its backing contributions with the largest unpaid reward first;
  - a pledge stacker is added to the spam scenario.

  Verify with tests: a contributor that couldn't afford a stake now submits with a pledge, and the stacker's defective contributions are slashed or clawed back with its pledges.
- [x] 3.2 Report and criteria:
  - the report gains pledges made, the amount pledged, pledges lost to slashes and to clawbacks, and the stacker's return;
  - the acceptance check runs with pledges on, and adds the capital criterion: the replay with and without pledges on the same seeds, at least a third fewer unaffordable submissions within two standard errors.

  Verify with tests: the counterfactual differs only in `pledge_max_stake_bps`, and the criterion reports both numbers.
- [x] 3.3 Summary: the pledge-cap sweeps (design D2) and a "no pledges" ablation row. Verify with a test that the summary has the new tables.

## 4. Acceptance run

- [x] 4.1 Run `python3 -m pof.sim summary --seeds 20`, and commit `reports/acceptance-v3.json` and `.md` next to v2, with the capital criterion, the sweeps and the stacker's result. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails, change the parameters or rules in this change, in the open: record each change and its reason in the design, as a "changes the simulation forced" section, and re-run 4.1. Verify that the final report passes every criterion (at hunting elasticity 0 as well) or names each remaining failure, its cause and a proposed next step.
- [x] 4.3 Post the comparison (v2 vs v3) on #19 and it-ops#14, update `README.md`, and verify the documented commands run as written. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- In #5, add the theorems for pledges: conservation, and the cash-first bound.
