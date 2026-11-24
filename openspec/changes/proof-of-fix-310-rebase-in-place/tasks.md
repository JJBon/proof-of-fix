## 0. Decisions (the owner)

- [x] 0.1 The owner decides the open questions in design.md: O1 (who may rebase, `REBASE_GRACE`, `REBASE_SHARE_BPS`), O2 (no tests-only or shorter windows in v3.1), O3 (no reputation for rebasers), O4 (v3.1's `mergeDays`), O5 (the Radicle hand-over: same RID, shared genesis node, a `v3.1` branch from the owner's node), O6 (#311 in the same release candidate). Verify: a dated comment by the owner on #310; design.md updated where a decision differs from the recommendation.
  Done (2026-11-23): the owner decided all six as recommended: O1 the solver, then anyone after 1 day, with a 10 % share; O2 no shortcut re-checks; O3 no reputation for third-party rebasers; O4 `mergeDays` 3; O5 the hand-over as designed; O6 #311 in the same release candidate. Recorded in design.md ("Decided (owner, 2026-11-23)") and on #310.

## 1. Contracts (`contracts/src/v3`)

- [ ] 1.1 State: `Submission.rebaseOf`, `Award.rebase`, the `Rebased(bounty, original, check, fix, base)` event, the constants `REBASE_GRACE` and `REBASE_SHARE_BPS` (RB1, RB2) in RaceV3Base. Verify: `test_theRaceReadsPanelsRecordsRight` and the existing v3 suites pass unchanged.
- [ ] 1.2 `rebase(b, fix, base, salt)` in RaceV3Endings (RB2, RB10), delegated from RaceV3 through the Annex's fallback: every refusal in RB2, the grace for third parties (`Heads.head(repo).movedAt`), `_newCheck` at the original's `judged`, the claim (RB7: the solver's own original claim closed first). Verify: Foundry tests for each refusal and each accepted case (task 2.1).
- [ ] 1.3 `merge(b)` through a rebase (RB5): both verdicts Final passes, `heads.move` with the rebase's base, fix and verdict hash, `a.fix` and `paidFix` for both commits, `book.paid(orig…)` and `closeClaim(r)`. Unchanged path for awards with no rebase. Verify: tests 2.1–2.3; `HeadAtFinalityV3.t.sol` passes unchanged.
- [ ] 1.4 `mergeExpired(b)` extended (RB5): the solver's own counted fail on a base that is still the head reopens at once; any other ending frees the slot; the deadline from the later finality; `NotYet` while a rebase submitted before the deadline is undecided. Verify: tests 2.2, 2.4.
- [ ] 1.5 `_earned` from the merged rebase's finality; `_settle`: the rebaser's share (third party only) and the rebase's S6 refund; `isParty` includes the original solver for a rebase check; `settleChallenge`'s reward for a rebase (RB5, RB6). Verify: tests 2.3, 2.5.
- [ ] 1.6 Sizes: `scripts/contracts.sh sizes` after 1.1–1.5. Each of RaceV3, RaceV3Annex and RaceV3Endings keeps at least 512 B of runtime margin; otherwise apply RB10's fallbacks in order (drop the share; then a third companion `RaceV3Rebase` behind the Endings' fallback, with its fingerprint check). Verify: the size table in the PR, before and after; Panels, Heads, FeesV3, Validators and SolverBook bytecode unchanged.
- [ ] 1.7 Gas: `forge test --gas-report` for `rebase`, `merge` through a rebase and `mergeExpired`'s reopening, then the same transactions on the Sepolia rehearsal (a throwaway deployment of the branch, as in `reports/glamsterdam-runtime-v1.md`) under EIP-8037. Verify: a short report `reports/rebase-gas-v1.md` with each transaction's gasUsed on Sepolia and under the old rules, against RB11's estimates.

## 2. Foundry tests (`contracts/test/v3/RebaseV3.t.sol`, and the invariants)

- [ ] 2.1 The issue's done-when: two bounties judged on the same head; the first merges; the second's `merge` reverts `StaleVerdict`; its solver rebases onto the new head; the rebase check passes and becomes final; the second merges about one cycle after the first (asserted in chain time with the production `Windows`, k = 3, level A: ≤ 28 h after the first merge with r = 1 h, against ≥ 15 days without). Verify: the test passes; the head is the rebased commit, a fast-forward of the first fix.
- [ ] 2.2 Fail fast: the solver's rebase counted as a fail reopens the bounty at once through `mergeExpired`, and a pass waiting behind wins; a third party's fail and a fail after the head moved again only free the slot; the solver's failed rebase is appealed once under D24 in the reopened bounty. Verify: tests pass.
- [ ] 2.3 Timing: a rebase counted near the end of the original window can't merge before its own window ends; a rebase final before the original waits for it; instalments count from the later finality. Verify: tests pass.
- [ ] 2.4 Refusals and the deadline: rebase onto a non-head base, of a mergeable award, of a paid commit, two at once, a third party inside the grace, over the cap; the deadline counted from the latest passing rebase, held by a rebase in flight. Verify: tests pass.
- [ ] 2.5 D21 and challenges against a rebase: an upheld dispute reverses it, pays the disputer the reward from the pot and charges the rebaser's reputation; the original reversed while its rebase is judged is clawed back as today and the rebase's deposit rest returns; a rejected dispute's stake goes to the rebaser. Verify: tests pass.
- [ ] 2.6 Invariants: `RaceV3Invariant.t.sol` gains rebase actions (the head never names a commit whose own verdict isn't a final pass; the original commit of a rebased award never becomes the head; at most one undecided rebase per award; the pot's conservation holds with the share and refund). Verify: the invariant runs pass at the suite's usual depth.

## 3. Node (`oracle/`)

- [ ] 3.1 The chain reader and ABI for v3.1 (`Submission.rebaseOf`, `Award.rebase`, `Rebased`), chosen by the deployment record's version. Verify: `tests/test_node_v3*.py` pass against v3 and v3.1 records.
- [ ] 3.2 The judge's case for a rebase check (RB3): the original's commit fetched with the verified fetch, the approved and rebased diffs and the range-diff in the case, the rubric's adaptation question; the tests as today (protected paths from the new base, twice). Verify: unit tests with a fake judge: a clean rebase passes, a smuggled change fails, a semantic conflict fails on the new base's protected test.
- [ ] 3.3 The keeper (RB8): `Rebased` checks discovered and kept like any check; `merge` for a final passing rebase; `mergeExpired` after a failed rebase; no `merge` call on a stale base. Verify: unit tests; with #314, one estimate per backoff period.
- [ ] 3.4 The superseded guard (RB12): the seat part (`ORACLE_MERGE_VIA=radicle`) refuses to start for a deployment record with `supersededBy`, and logs why; the keeper still runs. Verify: a unit test; `tests/test_radicle_v3*.py` pass.

## 4. pofctl (`pofctl/v3cli.py`)

- [ ] 4.1 `pofctl --v3 rebase --bounty B --patch <commit> [--salt]` (RB8): the checks before sending (state, stale base, new base is the head, the grace for a non-solver, the cap, the allowance), the transaction, the patch-update command and claim lines printed. Verify: unit tests for each refusal, and a devnet run in task 6.
- [ ] 4.2 `merge`, `submit` and `status` updated: stale-base messages point to `rebase`; `merge` explains a rebase awaiting finality; `status` lists rebases. Verify: unit tests.

## 5. Guides

- [ ] 5.1 `docs/guides/submit-a-fix.md`: a section "If your fix's base went stale: rebase in place" (when it applies, the command, the patch update, what it costs, what happens on a fail, the grace for others), and the README's timing numbers updated. Verify: `tests/integration/guides_radicle.py` runs the new block as written on the devnet; `tests/test_guides.py` passes.

## 6. Integration

- [ ] 6.1 A new scenario in `tests/integration/scenarios_v3.py` (letter `r`), on the minute windows: two fixes on the same head pass; the first merges; the second's merge is refused as stale; its solver rebases with pofctl; the rebase passes and merges about one cycle after the first; and a second bounty where a rebase breaks the first fix's protected test, is failed, and its bounty reopens at once. Verify: `scripts/integration.sh --version 3` passes with `r` included, three runs in a row.
- [ ] 6.2 The Radicle variant (`tests/integration/suite_v3_radicle.py`): the rebase as a new revision of the same Radicle patch; the judges find it; canonical `main` fast-forwards to the rebased commit on every delegate's node; `pofctl verify-head` exits 0. Verify: the Radicle set passes.
- [ ] 6.3 The hand-over rehearsal (RB12) on the devnet: deploy "v3" and "v3.1" with the same genesis Radicle node; v3.1's genesis head is canonical `main`; the node switches its seat part to v3.1 (v3 marked superseded); a v3.1 fix merges and `main` follows v3.1's `Heads`; a later v3 head move is never pushed. Verify: an integration test passes; `verify-delegates` passes against v3.1's seats throughout.
- [ ] 6.4 `bash scripts/check.sh` passes. Verify: its output in the PR.

## 7. Release candidate (gate: the owner's go)

- [ ] 7.0 #311 (early reveal with the shadow guard) is merged to main with its own tests (its own change and PR), so the release candidate's commit holds both (O6). Verify: #311's Foundry tests and integration scenario pass on the candidate commit; the size table of task 1.6 re-measured with both changes (Panels' margin included, since #311 changes PanelsJudge).
- [ ] 7.1 **Gate:** the owner's go for a new release candidate, naming the commit (this change and #311, O6). Verify: a dated comment by the owner on #310.
- [ ] 7.2 The release candidate (L18): `scripts/integration.sh --release-candidate <commit>` passes 3 runs in a row with scenario `r` and #311's early-reveal scenario, the production-windows run, the external SEV-SNP validator and a small real-model run (dry run first; the owner's approval and a cost estimate before any paid call). Verify: `contracts/release-candidates/rcN.json` committed and linked on #310.

## 8. The v3.1 deployment and the Radicle hand-over (gates: the owner's go)

- [ ] 8.1 The v3.1 plan: the same RID, the genesis head at canonical `main` (`deploy_sepolia.py`'s verify-head), the same `genesisRadNode`, v3.1's `mergeDays` = 3 (O4), the contracts of this change and #311 (O6); the precondition of RB12 checked (no v3 bounty `Won` or claimed and unmerged). The v3.1 code pushed from the owner's node as the non-canonical branch `v3.1` (O5). Verify: the dry run against Sepolia passes; the branch is readable from a fresh node.
- [ ] 8.2 **Gate:** the owner's go for deploying v3.1 (this change and #311), naming the plan and the release candidate. Verify: a dated comment by the owner on #310.
- [ ] 8.3 Deploy v3.1 with the script's broadcast flag; record `contracts/deployments/sepolia-v3.1.json`; mark v3's record `supersededBy`. Verify: the script's checks pass; `pofctl --v3 verify-head` against v3.1 and the Radicle node exits 0.
- [ ] 8.4 **Gate:** the owner's go for the hand-over. Then the genesis validator's node switches its seat part to v3.1 (v3 keeps only its keeper). Verify: `verify-delegates` passes against v3.1's seats; canonical `main` unchanged; recorded on #310.
- [ ] 8.5 The guides and README name v3.1 as the live deployment and v3 as superseded. Verify: `tests/test_guides.py` passes; the README's deployment table updated.
