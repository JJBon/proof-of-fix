# Tasks

## 1. Simulation

- [ ] 1.1 Solver streams (D1): each solver's own decisions draw from its own stream. Verify with a test that a solver outside a ring draws the same numbers for the same decisions in the ring run and its honest twin, and that a run is still reproducible.
- [ ] 1.2 Measure the rings' and the hidden bidder's standard errors on seeds 1–100, before and after 1.1, and record them in the design.
- [ ] 1.3 Attack seeds and `--jobs` (D2): rings and the hidden bidder on `attack_seeds`, run in parallel and merged in seed order. Verify with a test that results don't depend on the number of jobs.
- [ ] 1.4 The ring tolerance (D3): `ring_tolerance_bps` and the bounded criterion for rings and the hidden bidder, with the report giving each gain, its standard error and its upper bound. Verify with tests of the criterion on given values.

## 2. Acceptance run

- [ ] 2.1 Run checking v7 (100 verdict seeds, 400 attack seeds, sweeps on 20), and commit `reports/acceptance-checking-v7.{json,md}` compared with v6. Verify that it reproduces byte for byte with a different `--jobs`.
- [ ] 2.2 If a criterion fails, fix it here in the open and record it in the design. Verify that the report passes or names each failure.
- [ ] 2.3 Post the results on #55, #15 and it-ops#14, update `README.md`, and run the check.
