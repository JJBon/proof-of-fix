# Tasks

## 1. Setup

- [x] 1.1 The pinned Foundry image (by digest), `contracts/` layout, vendored libraries at pinned commits, and `scripts/contracts.sh` (build and test in the container). Verify that `forge test` runs with no network access other than localhost.

## 2. Phase 1: money

- [x] 2.1 Baskets (D5, D6): per-coin escrow, received-amount checks, pull payouts, the invariants, withdraw-only mode, caps. Verify with unit tests for each scenario, and the invariant suite.
- [x] 2.2 The race (D4, D9–D11): registration, the rising price, attempts, commitments, results through a mock oracle, late fees, appeals, the paid-fix registry, merge, instalments, clawback, the issue stake and finder's fee, idle sunset; no market fee. Verify with unit tests for each scenario in the deltas, and a test listing every external function (no privileged call).
- [x] 2.3 The simulation (bounty-market delta): twin bounties and the paid-fix check (`fix_paid_elsewhere`), and the contract-shaped configuration (D9: no treasury, matching or trust discount, no market fee, race stake 0, challenges resolved at once). Verify with tests for the delta's scenarios; the default runs are unchanged (the modes v3 reproduction).
- [x] 2.4 No target, one open bounty per issue, and the reporter's split (D12, D13; owner, 2026-10-26): in the contract (`accept`, `refuseSimilar`, pledges while open) and in the simulation's race and claim. Verify with tests for the delta's scenarios, the contract's invariant suites, the race's acceptance check, the split sweep (`market split`) and a new modes run (v4).
- [x] 2.5 Fixes from the contract review (D14; owner, 2026-10-27): a result deadline (`timeOut`), and the price's share locked, not its amount; locking on the first submission was measured and dropped. Verify with the contract's tests and invariant suites, a new modes run (v5) and the split sweep again (v2).
- [x] 2.6 The exporter and the replay (D7). Verify that a 2-week race run on several seeds, in the contract-shaped configuration (`pof.params.CONTRACT`), replays to identical balances.

## 3. Phases 2-5

- [x] 3.1 Signed results with the quorum (D3). Verify with tests: too few signatures, wrong bounty, replayed signature.
- [x] 3.2 `quote()` and its CLI. Verify with tests against the simulation's numbers.
- [x] 3.3 Phase 4: the local Forgejo test repository, the bounty bot, one fix through the whole loop. Verify end to end.
- [x] 3.4 The token (D15): the fixed schedule and decay, the founder's share, and its Race as the only minter. Verify with unit and invariant tests that supply never exceeds the schedule, and with the test listing every external function that there's no privileged call.
- [x] 3.5 Migration (D15): the 1:1 swap with burn, and the emission continued less the previous version's mint in each period. Verify with a test that runs two versions side by side.

## 4. Report

- [x] 4.1 A report: what works, gas per step, the replay results, the migration, and what's left before any audit. Post it on #56 and #15, update `README.md`, and run the check (Python tests and the contract tests).
