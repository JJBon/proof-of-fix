# Tasks

## 1. Parameters

- [x] 1.1 Add `pool_buffer_releases` (design D6, 0 = off) with validation (not negative). Verify with a test.

## 2. Mechanism

- [x] 2.1 Funding follows use (design D6): `open_release` scales the whole funding by f, records a `funding_scaled` event when f < 1, and splits the reduced funding by the published shares. Verify with tests for "Pool within the buffer", "Pool over the buffer" (the split still matches the shares, and the ledger conserves) and "Buffer switched off".

## 3. Simulation

- [x] 3.1 Defective work judged with clustered standard errors (design D1, D2):
  - attacking kinds pass only if m + 2·SE < 0;
  - honest-intent kinds fail only if m − 2·SE > 0;
  - attacking kinds under `MIN_DEFECTIVE_SAMPLE` fail as inconclusive with the count.

  Verify with tests:
  - the statistic on hand-made data (known mean and SE);
  - one test for each outcome (passes, fails, inconclusive, honest kind gaining).
- [x] 3.2 Splitting per accepted line (design D3). The report gives the return per accepted line, lines accepted and unaffordable submissions, split and unsplit. Verify with a test that the criterion uses per-line returns and reports both line counts.
- [x] 3.3 Three abusers in the sponsorship scenario (design D5). Verify with a test that each has its own fake accounts and that the abuser group's count roughly triples.
- [x] 3.4 `summary --sweep-seeds` (design D4) and the `pool_buffer_releases` sweep. Verify with a test that the sweeps use the sweep seeds and that their rows say how many.

## 4. Acceptance run

- [x] 4.1 Run `python3 -m pof.sim summary --seeds 100 --sweep-seeds 20 > reports/acceptance-v5.json` and write `reports/acceptance-v5.md`. It must include a section on which v2–v4 verdicts don't hold at 100 seeds. Verify that it reproduces byte for byte.
- [x] 4.2 If a criterion fails, change parameters or rules in this change, in the open: record each change and its reason in the design, and re-run 4.1. Verify that the final report passes every criterion at hunting elasticity 0, 0.5 and 1, or names each remaining failure as significant or inconclusive, with its cause and a proposed next step.
- [x] 4.3 Post the comparison (v4 vs v5) on #27 and it-ops#14, update `README.md`, and verify the documented commands run as written. Then run the check.

## Workflow follow-up

- Review with the owner, then archive the change.
- Then the Lean proofs (#5) against the settled rules.
