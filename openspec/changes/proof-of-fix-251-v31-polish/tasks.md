## 0. Preconditions

- [x] 0.1 #324 (#311, early reveal) and #323 (#310, rebase in place) are merged to main, and this change's branch starts from that main. Verify: `git merge-base --is-ancestor` of both PRs' merge commits; `scripts/contracts.sh sizes` on that base recorded as the "before" column of task 1.6 (RaceV3Endings ≈983 B, PanelsVerdict ≈1,249 B of margin).

## 1. Contracts (`contracts/src/v3`) and their Foundry tests

- [x] 1.1 F1 (VP1): `FeesV3.drawEpoch(id)` (the check's epoch once open, else `rolled`), `IPanelsFees.drawEpoch`, and `PanelsDraw.fill` comparing `pricedFrom(family)` with `min(drawEpoch(id), c.snap.rolled)`. Verify: a new suite `contracts/test/v3/PolishV31.t.sol` with the audit's scenario (genesis plus 3 validators of priced families pricing a fresh family, a fresh-family validator announced, 12 registrations opened in epoch 0, `roll()` pricing the fresh family at epoch 1, the seed blocks aged out) as one regression per path: a counted re-target (`result`), `refill`, an audit (`payPanel`) and a challenge (`settleChallenge`); each fails on the base commit with `Unpriced(fresh)` and passes after (0 of 12 panels seat the fresh family); a fresh-family shadow is still drawn and paid nothing; a check opened after the fresh family's first price seats it.
- [x] 1.2 F1's hold (VP1): `PanelsDraw.challengersReady` counts a challenger only if `isPriced(family)` and `pricedFrom(family) <= drawEpoch(id)`. Verify: in `PolishV31.t.sol`, a held k = 1 verdict with later-priced and unpriced validators outside its panel stays held until enough payable challengers exist; `HeldWindowV3` and the launch-rule suites pass unchanged.
- [x] 1.3 F1's invariant: `RaceV3Invariant.t.sol` (or the Panels invariant suite) gains a pricing action (a new family priced by three tables at a roll) and the invariant "every seated non-shadow validator's family has `pricedFrom <= drawEpoch(its check)`", plus "no `result`, `payPanel` or `settleChallenge` reverts `Unpriced`". Verify: the invariant runs pass at the suite's usual depth.
- [x] 1.4 F2 (VP3): `ROLL_WORK` 40; `roll()` runs one `rollPart()`; `ROLL_PART_GAS` removed and the natspec of `roll`/`rollPart` updated. Verify: the audit's `ScratchRoll` as a regression (3 posters, 40 priced and 20 announced families, every price moving): each part's gas + 97,920 × its new slots ≤ 8,000,000; a limit sweep from `roll()`'s estimate up to 30M in steps of 50k all succeed; `test_rollPartsAreBounded` (`FeesV3.t.sol:1054-1081`) rewritten against the 8M bound; the FeesV3 suites pass.
- [x] 1.5 F8 (VP4): `Validators.topUp` bumps `epoch` only if the key's bucket or state changed (as `recheck`). Verify: tests in `PolishV31.t.sol`: a one-micro-coin top-up leaves `epoch` and a waiting draw's `NothingChanged` refusal as they were; a top-up across a tier and one restoring a below-floor validator bump it; a candidate's top-up doesn't (or, if a candidate's bond feeds `canShadow`, bumps only when it crosses that floor); the Validators suites pass.
- [x] 1.6 F9 (VP5, no code change): a test that a refill sent with gas just short of `fees.announce` completes with the family unannounced, and the next draw meeting that validator announces it. Verify: the test passes; PanelsJudge and PanelsVerdict bytecode unchanged.
- [x] 1.7 F7's threshold documented in a test: a held k = 1 verdict needs six eligible validators with room outside its panel before its audits are drawn and three outside the judge and both auditors after; one pause at the threshold keeps it held. Verify: the test passes on the launch rules (caps `launch`, kTop 3, `same`).
- [x] 1.8 Sizes and gas: `scripts/contracts.sh sizes` and the libraries' sizes from `out/*.json` after 1.1–1.5, against task 0.1's column; `forge test --gas-report` for `draw`, `refill`, `drawAudits`, `drawChallenge`, `startWindow` (the hold's scan), `roll`, `rollPart` and `topUp`. Verify: the table in design.md ("Sizes") filled in with measured values; FeesV3, Validators and PanelsDraw each keep at least 512 B of runtime margin; RaceV3, RaceV3Annex, RaceV3Endings, Panels, PanelsJudge and PanelsVerdict bytecode unchanged; `scripts/contracts.sh test` passes in full, with `POF_TEST_WINDOWS=minutes` too.
  - **Done (2026-11-24):** sizes in design.md ("Measured after the change"): FeesV3 18,026 → 17,961 B (6,615 left),
    Validators 22,908 → 23,007 B (1,569 left), PanelsDraw 10,656 → 11,186 B (13,390 left); the six untouched contracts
    identical but for the metadata hash. Gas (median / max): `draw` 766,997 / 2,722,372; `refill` 534,389 / 979,522;
    `drawAudits` 45,707 / 1,209,291; `drawChallenge` 521,700 / 2,444,844; `startWindow` 378,852 / 943,405; `roll` and
    `rollPart` max 1,473,083 (one part; before, `roll` reached 8,424,051); `topUp` 80,192 / 472,907; `drawEpoch` ≈3.9k.
    `payShadow`'s paying branch: 241,395 used, least paying limit 222,000 pre-8037, 2 new slots (≈418k with 8037's state
    gas). Full suites: 63 suites, 815 tests passed, 0 failed, in both window modes.
  - Deviations: 1.3's invariant is in `LivenessInvariantV3.t.sol` (RaceV3Invariant's panels are replayed, not drawn);
    1.6 uses `advance`'s refill (`refill()` reverts `NotReady` when it seats nobody) and emulates the starved branch
    with `vm.mockCallRevert`, since forge's gas isn't EIP-8037's; 1.4's sweep is split into ten tests (forge's per-test
    gas cap); `PanelsLevelsV3.test_aHiddenLoneVerdictWaitsForTeeChallengers` now uses challengers of priced families
    (VP1's hold rule).

## 2. Keeper (`oracle/node_v3.py`, `oracle/rpc.py`, `oracle/__main__.py`) and its Python tests

- [x] 2.1 F4/F5 (VP6): the gates for `finish`, `release`, `result`, `payPanel` and `settleChallenge`; state-keyed tries for `startWindow` and `refill`; gated refusals (`NotYet`, `NotReady`, `TooEarly`, `NothingDue`, `NothingChanged`, `ShortOfGas`) not counted; `GIVE_UP_S` replacing `GIVE_UP`; the generic backoff with a state fingerprint and one log line per backoff. Verify: `tests/test_oracle_v3.py` gains a fake chain that counts estimates per call key over simulated hours: at most `CHALLENGE_TRIES` estimates per state for `startWindow` and `refill`, none for `finish` before `finalAt + REPORT_WINDOW`, none for `release` before `resultDays`; one late report: `payPanel` not sent before the window, sent and kept after it, never given up (#314's "done when": one estimate per backoff period).
- [x] 2.2 F3 (VP7): `Wallet.send(..., gas_floor=)` and `payShadow` sent with `PAY_SHADOW_GAS_FLOOR`; the paying branch measured on v3's and v3.1's `payShadow` under EIP-8037 (the gas report of task 1.8 and #323's test) and the floor kept at least twice it. Verify: a node test that `payShadow`'s transaction carries at least the floor; a `rpc` test that the limit is `max(estimate × 1.25 + 10,000, floor)`.
- [x] 2.3 F2 (VP8): `rollPart()` in a loop, at most `ROLL_PARTS_PER_PASS` a pass, instead of `roll()`. Verify: a node test on the fake chain that a period of several parts closes in one or two passes with one estimate per part; against a devnet with FeesV3 v3.1 and v3, the period closes.
- [x] 2.4 RPC (VP6): `ORACLE_POLL`, `ORACLE_KEEPER_EVERY` and `ORACLE_TX_POLL` with chain-dependent defaults; the scan set dropping finished submissions and kept panels, with a cursor over the event list; `ORACLE_KEEPER_BUDGET` with a rotating cursor; a 429 (`Unavailable`) in the keeper section pausing it (Retry-After, else backoff up to `RATE_PAUSE_MAX_S`) without aborting the pass. Verify: tests that a 429 storm in the keeper section doesn't delay a due reveal (sent in the same or next pass); the scan set shrinks as checks finish and a restart rescans once; a budgeted pass resumes where it stopped; `oracle/__main__.py`'s help documents each setting.
- [x] 2.5 F1 on live v3 (VP2): probe `FeesV3.drawEpoch(0)` once; where it reverts, `build_table` posts only families already priced and logs it once. Verify: tests that on a fake v3 chain a table with `openai/gpt`'s list price posts no `openai/gpt` entry while `anthropic.claude` (priced) is posted at the price in force, and on a v3.1 chain every listed family is posted; `ORACLE_LIST_PRICES={}` gives the same table as the v3 rule (the configuration route for the measured image).
- [x] 2.6 F10 in the node (VP12): `register` refuses an `ORACLE_FAMILY` not in the `provider/line` form unless that exact name is already priced on the deployment. Verify: tests for `anthropic/claude` (accepted), `anthropic.claude` on a deployment that prices it (accepted, with a note that v3.1 renames it) and on one that doesn't (refused, naming the form).
- [x] 2.7 The keeper-only mode (VP10): fold in the seed host's `oracle/keeper.py` as built (branch `keeper-sepolia-local`, commit 1ca389d, cherry-picked or copied into this branch with its history noted): `python3 -m oracle.keeper run [--once] [--from-block]|info`, `Keeper(NodeV3)` with no `me()`, `ORACLE_RPC_SECRET_ARN`, the `Redactor` (moved to a shared module for 2.9), `KeeperWallet`'s transaction lines (hash, block, gas, ETH; mined-but-reverted), the `ORACLE_KEEPER_ADDRESS` check, `ORACLE_KEEPER_MAX_TX_HOUR`, defaults `ORACLE_POLL` 120 s and `ORACLE_TX_POLL` 3 s; on top, `Wallet.poll_s` configurable for the node too (`ORACLE_TX_POLL`), the submissions cursor of 2.4, and `info` saying "not registered (keeper only)". Verify: a new `tests/test_keeper.py`: an unregistered key keeps a fake chain's checks and sends no `seal`, `reveal`, `post` or `register`; a mismatched address stops it; the hourly cap holds; transaction lines carry hash and block; the seed host's runbook commands (`run`, `info`) work unchanged; `validator-kit/runbook.md` gains "Run a keeper" (the systemd unit as on the seed host, its limits, gas and RPC cost from the runbook's measurements).
- [x] 2.8 #310's rebase checks: `Rebased` checks are in the keeper's scan set and get the same gates and backoff (#310's task 3.3 "with #314, one estimate per backoff period"). Verify: a test with a rebase check on the fake chain.
- [x] 2.9 No RPC key in any log line (VP20): `Rpc`'s shown URL is scheme, host and `/…` when the path has a segment of 8 characters or more; the node's, the keeper's, the watcher's and pofctl's log functions pass every line, tracebacks included, through the shared redactor loaded with the RPC URL; `ORACLE_RPC_SECRET_ARN` for the node. Verify: for each of the four, a 429 from `https://<provider>/v3/<key>` retried and then failed logs no part of the key; a traceback through `Rpc` is redacted.
- [x] 2.10 `Rpc`'s default retries (VP19): `DEFAULT_RETRIES` 3 for safe calls, Retry-After honoured up to `RETRY_AFTER_MAX_S` 30 s; pofctl uses the default; the node keeps `ORACLE_RPC_RETRIES` (5). Verify: tests that an `Rpc` built with no `retries` retries a 429 three times honouring Retry-After, and never retries `eth_sendTransaction` or a revert; a pofctl read survives one 429.
- [x] 2.11 The verdict on the Radicle issue (VP18): after a verdict is counted, the node of the counted panel's first revealed seat comments the receipt (outcome, k, state and times, the counting transaction, the marker `pof-verdict: <chainId>/<race>/<check>`) on the bounty's or registration's Radicle issue; the reason at once for a non-hidden registration check, and for a fix check only once its bounty is paid or closed; retried with the keeper's backoff, never blocking a seat step. Verify: unit tests on the Radicle fakes for each case (registration with reason, fix without then with, hidden without, a second node skipping on the marker, a restart not repeating).

  - **Done (2026-11-24), deviations:** the keeper's backoff, gates and `GIVE_UP_S` run on chain time (block
    timestamps), so tests drive them with a warp; `result`, `finish` and the race's `release` became once-only so
    `GIVE_UP_S` applies to them; the budget counts chain-method calls (a mined send ≈6). `PAY_SHADOW_GAS_FLOOR` is
    **850,000**, not 600,000: task 1.8 measured the paying branch at ≈418k with EIP-8037's state gas (222k + 2 new
    slots), and the rule here keeps the floor at least twice it. The keeper-only node's hourly cap counts mined sends
    (reverted or not), not estimates that revert, which spend no gas (the seed host's code; VP10's text says they count:
    counting them could stall the live keeper on gated estimates). The verdict comment: the reason of a fix check goes
    out as a second comment with its own marker `pof-verdict-reason: …`; a fix check on a hidden registration's bounty
    never gets it either; the reason quoted is the commenting node's own judge's (labelled with its seat and vote);
    "first revealed seat" is the lowest revealed slot. The devnet parts of 2.3 and 2.7 are in task 8.

## 3. The watcher (`validator-kit/sevsnp/lambda/watcher.py`)

- [x] 3.1 The draw duty (VP9): scan `Committed`, `Registered` and `Rebased` in the run's block range; keep the undrawn checks on the state list; due past `seedBlock + DRAW_GRACE_BLOCKS` (or `retryAt` + grace for a waiting check) plus the validator's stagger; one start a check under the fuse, the budget and the kill switch, not held by the spend pause; `DRAW_READS_MAX`; `WAKE_ON_DRAW` (default `"true"` in the kit's Terraform, `validator-kit/sevsnp/terraform/watcher.tf`); the module docstring's new section. Verify: `tests/test_sevsnp_watcher.py` gains: an undrawn check past grace and stagger starts the instance once; drawn within the grace, nothing starts; two keys start at different times for the same check; a waiting check past its retry time starts it; the fuse, the budget and `ENABLED` hold it; the ABI check covers the new events; #311's reveal-phase tests pass unchanged.

  - **Done (2026-11-24), deviations:** the start limit is one per seed block or `retryAt` (a re-targeted or redrawn
    check may wake one more host; else such a check could never be drawn by the watcher again); a sealed check's stagger
    counts from when this watcher first saw it past its grace; a 429 still ends the watcher's run (no retries), with no
    key in the log; `WAKE_ON_DRAW` defaults to `"false"` in the code and `"true"` in the kit (`watcher.tf`), and the
    kit's new variables `watcher_wake_on_draw` and `watcher_max_block_range` (`MAX_BLOCK_RANGE`) are declared in
    `watcher.tf`. Open: a check drawn then released back to WAITING has left the list, so the watcher doesn't wake for
    it again. **Closed by task 12.1 (VP23).**

## 4. pofctl (`pofctl/v3cli.py`, `pofctl/cli.py`)

- [x] 4.1 `pofctl --v3 draw <id>` (VP11): the checks before sending (sealed past its seed block, or waiting with the registry changed or past `retryAt`), `Panels.draw` then `RaceV3.signal`, each refusal explained with nothing sent; the hint printed by `issue register` and `submit`. Verify: unit tests for each refusal and the two sends; a devnet run in task 8.1.
- [x] 4.2 `status` without the password and with the ETH balance (VP11): the address from `--address`, `pofctl.json`'s `address`, or the keystore's `address` field, decrypting only if none gives it; `eth` in the JSON and a line in the text with the 0.01 ETH hint. Verify: unit tests that `status` with a keystore, an `address` in the config and no terminal asks nothing and prints both balances; a signing command still asks once.
- [x] 4.3 `issue register` (VP11): the whole id on its own line and in `--json`; `--title/--description` opening the Radicle issue, taking the id from Radicle 1.10.3's output and checking it with `rad issue show`. Verify: `tests/fake_rad.py` prints Radicle 1.10.3's box for `rad issue open`; unit tests for the id line, `--title` end to end on the fake, and a title mismatch refused before any transaction.
- [x] 4.4 The approval race (VP17, S1): `ensure_allowance` waits after an approval until `allowance()` reads at least `need` (`APPROVAL_POLL_S` 2 s, up to `APPROVAL_WAIT_S` 60 s), and a send that still reverts `ERC20InsufficientAllowance` is retried once after another wait; every approving command uses it. Verify: a fake chain whose allowance lags behind the approval: `issue register`, `pledge` and `submit` succeed and wait; a send refused twice fails with the explanation and nothing more sent.
- [x] 4.5 Transaction hashes (VP17, S2): every sending command prints each transaction's hash and block, approvals included, and its `--json` carries `tx` and `block` (or `txs`). Verify: unit tests for `faucet`, `issue register`, `issue open`, `pledge`, `submit`, `claim`, `merge`, `draw` and `withdraw`.
- [x] 4.6 A reporter's view (VP17, S3): `pofctl --v3 issue show --issue N` (status, k, panel, the seal, reveal and report deadlines, the counted result, the hold or window and `finalAt`, the deposit's spending, the refund due and whether refunded; `--json` too), and `status` listing the address's registrations with the hint. Verify: unit tests for a sealed, a held-after-pass, a final-and-refunded and a released registration on the fake chain; the guides' fund-an-issue block uses `issue show`.

  - **Done (2026-11-24), deviations:** with several transactions the JSON keeps `tx`/`block` (the command's own, the
    last) beside `txs`; `issue register --title` needs a RID and passes `--repo` to `rad issue open` and `rad issue
    show`; after `APPROVAL_WAIT_S` without the allowance the send goes out anyway (said), and the one retry on
    `ERC20InsufficientAllowance` covers it; any unexpected exception prints a redacted traceback (exit 2). pofctl v3 has
    no dispute command, so the approval wait covers register, pledge, submit and rebase.

## 5. The checker image's files (#318's follow-up)

- [x] 5.1 Remove the private terms #318 kept from `IMAGE_INPUTS` (term numbers 5, 6, 7, 8, 9, 11, 20): neutral comments, no internal default (a required setting with a clear error, or a public value), the kit and the tests setting what they need (VP15). Verify: a new test in `tests/test_github_snapshot.py` scans the working tree's `IMAGE_INPUTS` with the preset's replacement terms and finds none (term numbers only in its output); `bash scripts/check.sh` passes.
- [x] 5.2 The exemption limited to v3's refs (VP15): the preset's `verbatim` exemption applies only to the listed refs (8946b9c and `sepolia-v3`); for any other ref a kept term in an image file fails the run. Verify: tests that a listed ref still copies its image files verbatim with the terms counted, and an unlisted ref with a kept term fails; a Radicle-target dry run of this branch reports 0 kept terms and image inputs byte-identical to the source.

  - **Done (2026-11-24):** `ImageInputsClean` finds no term in `IMAGE_INPUTS` (the image's files: oracle/seat.py,
    oracle/rpc.py, oracle/__main__.py, oracle/Dockerfile, oracle/README.md, pofctl/keys.py, scripts/judge_run.py
    cleaned; the seat has no built-in repository or forge: `ORACLE_REPO` and `SEAT_FORGE_URL`, or `ORACLE_REPOS`, are
    required, which the AWS seats host and devnet-seats.sh set; pofctl's `openbao` key source needs `BAO_ADDR`). The
    preset's `verbatim_refs` are 8946b9c and `sepolia-v3`. The Radicle-target dry run of this branch (841afd4): one
    root commit, 0 kept terms, the image inputs byte-identical to the source (`diff -r`). Open: `scripts/judge_run.py`
    keeps a default gateway URL on an internal AWS hostname that isn't in the terms file.

## 6. The v3.1 deploy plan and the hosts' Terraform

- [x] 6.1 F11 (VP13): `DeploySepolia.s.sol:374` with `gasOverhead` 500,000 (`gasAllowance` 1,000,000 and `maxGasPrice` 1 gwei unchanged), and `deploy_sepolia.py`'s checks reading the three back from the record. Verify: `tests/test_deploy_sepolia*.py` (or the deploy script's tests) assert the values; a local deploy's record shows them; FeesV3's `maxDeposit` for kTop 3 unchanged from v3's at the same prices.
- [x] 6.2 F10 (VP12): `deploy_sepolia.py` refuses a plan family not matching `provider/line`, before anything is sent; the plan template, `tests/test_genesis_validator.py:85` and the fixtures use `anthropic/claude`. Verify: tests that `anthropic.claude` is refused with the expected form named and `anthropic/claude` accepted.
- [ ] 6.3 The seed's Terraform (VP22): the `keeper_secret_arns` variable (ARNs only, default empty) and its `GetSecretValue` policy on exactly those ARNs, ported from the kit build tree's uncommitted change (no ARN values in the repository); a committed `seed/terraform/seed.tfvars.example` with `create_instance = true`; `seed/README.md` saying in bold that a plan without it destroys the running seed, with every `tofu plan`/`apply` line carrying it; the same note for the SEV-SNP kit in `validator-kit/runbook.md` and its tfvars example. Verify: `tofu validate` on both modules (no plan, no apply); a test that the examples set `create_instance = true` and that `keeper_secret_arns` refuses a non-ARN.
- [x] 6.4 The keeper as launch infrastructure (VP16, Q1): the v3.1 plan and the record's template name the seed host's keeper (its account's address, role "the seed host's keeper-only node") with its cost line (about $0 on the seed's existing instance, plus Sepolia gas of about 1.5–2M gas a check). Verify: `deploy_sepolia.py` copies it into the record; its test.

  - **Done (2026-11-24), except 6.3:** 6.3 (the seed's and the kit's Terraform, VP22) is left to the change being
    made to `seed/terraform` and the kit's `main.tf`/`variables.tf` the same night; nothing here touches them. 6.1:
    `REPAYMENT` read back from the record (FeesV3's `maxDeposit` uses only `gasAllowance × maxGasPrice`, so it is
    unchanged). 6.2: the family rule applies to every plan but v3's committed one (matched by its RID and genesis head,
    since plans carry no version). `mergeDays` 3 was already in the forge script (#310); `MERGE_DAYS` checks the record.
    6.4: the plan template is `deploy_sepolia.py`'s docstring; `keeper` is required on a remote endpoint (not for v3's
    plan) and optional on a local rehearsal.

## 7. Docs and guides

- [x] 7.1 F7 (VP14): `README.md:305-307`, `docs/take-part.md` and `docs/guides/run-a-validator.md` give the hold's real count (six before the audits are drawn, seven in all; six in all after) and what happens below and at the threshold. Verify: `tests/test_guides.py` gains a check of the stated numbers against `HOLD_K` and `K1_AUDITS` read from the contracts' source; `grep` finds no remaining "3 validators outside the panel".
- [x] 7.2 F6 (VP14, docs only): `docs/guides/submit-a-fix.md` and `docs/take-part.md` state the newcomer's ceiling (about 117.6 coins of funds less the registration fee at the record's opening share and finder's fee), that later pledges still raise the claim, and "record the attempt first; check `pofctl status`' room". Verify: `tests/test_guides.py` passes; the numbers derived from `contracts/deployments/sepolia-v3.json` in a test.
- [x] 7.3 The v3 guide's node config gets `ORACLE_LIST_PRICES = "{}"` with one line on why (VP2), and the guides use `pofctl --v3 draw`, `status` without a password and `issue register --title` in place of the `awk` over `rad issue open`. Verify: `scripts/radicle-spike.sh --guides` runs every guide's blocks as written on the devnet; `tests/test_guides.py` passes.
- [x] 7.4 The keeper-only mode and the watcher's draw duty in `docs/take-part.md` ("anyone can keep"), `validator-kit/runbook.md` and `validator-kit/SEVSNP-PLAN.md` (the draw duty's starts and cost). Verify: `tests/test_guides.py` passes; the runbook's commands run against a devnet in task 8.1.
- [x] 7.5 The guides' timing (VP21): about 2–3 h to a verdict on v3 (the seal window, the reveal, the count), then held until 6–7 validators with room; with #311 on v3.1, minutes once every seat sealed, then the same hold. Verify: `tests/test_guides.py` checks the stated windows against the deployment record's `windows`.

  - **Done (2026-11-24), 7.3's guides run in task 8.3's results.** The guides keep `anthropic.claude` for v3 with a
    note that v3.1 renames it; the draw blocks are marked `skip` (the devnet's keepers draw at once). pofctl v3 had no
    `attempt` command: the solver guide's "record the attempt first" block used `cast send … attempt(uint256)`
    (marked `skip`). **Replaced by `pofctl --v3 attempt` in task 12.4 (VP26).**

## 8. Integration

- [x] 8.1 The launch set (`tests/integration/scenarios_v3.py`, production windows): a new scenario `p` where (a) with every validator node stopped, a registration check is drawn by one validator's node started through the watcher's draw duty (the harness's watcher function on the devnet), and on a second check by `pofctl --v3 draw`, and on a third by a keeper-only node; (b) a new family is priced while 12 checks are in flight and every one of them settles (`result`, audits paid, a challenge settled); (c) one auditor never reports and its panel is paid after the report window by the keeper. Run with the harness's own keeper calls off, so the node's keeper does the work. Verify: `scripts/integration.sh --version 3 --sets launch` passes with `p`.
- [ ] 8.2 #310's rebase scenario `r` and #311's early-reveal scenario `e` pass with this change's contracts and keeper. Verify: `scripts/integration.sh --version 3` passes three runs in a row (the story, `launch` with `e`, `p` and `r`, `few-larger`, `few-same`).
- [x] 8.3 The Radicle set (`tests/integration/suite_v3_radicle.py`) with the family renamed `anthropic/claude`, `issue register --title`, `issue show`, and the verdict comment on the Radicle issue (one comment per verdict, with the reason for the registration check). Verify: `scripts/integration.sh --version 3 --radicle` passes.
- [x] 8.4 The external set (`tests/integration/external_v3.py`): the outside validator registers as `anthropic/claude`, qualifies and judges; its watcher's draw duty is exercised once (the harness's keeper off for one draw). Verify: `scripts/integration.sh --version 3 --external` passes (local Docker; the AWS run is task 9.4).
- [x] 8.5 Run the check: `bash scripts/check.sh` passes. Verify: its output in the PR.

  - **Results (2026-11-24, local Docker, `POF_INTEGRATION_PORT=8596`, `POF_INTEGRATION_NAME=pofv31`, Radicle,
    guides and external prefixes `pofv31*`; nothing left running):**
    - 8.1/8.2: `scripts/integration.sh --version 3` at 0fe665a: story passed 619 s, launch (u w v x e p) 949 s, rebase
      (r) 266 s, few-larger 223 s, few-same 228 s. Earlier, `--sets rebase,launch` passed (356 s, 1074 s) and
      `--sets launch` passed (830 s). **Not done:** three full runs in a row (one full pass, after the fixes below).
    - 8.3: `--version 3 --radicle` passed (597 s wall): `anthropic/claude` genesis family, `issue register --title`,
      `issue show`, one verdict comment with the reason. 7.3: `scripts/radicle-spike.sh --guides` passed (450 s).
    - 8.4: `scripts/rc-aws.sh rehearse b1c7d80` (local Docker, no AWS) passed: the outside validator as
      `anthropic/claude`, its watcher's draw duty started its stopped instance once and its own keeper drew the check
      (verify.py stays pending on a local run, as before).
    - 8.5: `bash scripts/check.sh`: 2,364 tests OK (1 skipped).
    - Code bugs the runs found, each fixed with a unit test: the keeper dropped a won fix from its scan set before its
      claim (no merge); `shown_url` refused a URL whose port is a label (every Radicle and external set aborted); a
      seat let go in the pass it was judged lost its verdict comment; a verdict comment was part of what a later judge
      reads (an audit or challenge would see the counted verdict, and the issue's hash in receipts changed).
    - Harness fixes: `r`'s stale-base wait; `p` announces the new family at once and asks at least one of its 12 checks
      in flight at the first price (a run found some done by then; all 12 must settle); `p` (c) accepts whichever
      keeper paid after REPORT_WINDOW; the external set's D mines past the check's own seed block and asks no second
      draw start (a start for the drawn seat is the seat duty's); the Radicle set's comment wait runs the nodes'
      passes; the fake `rad` box matches Radicle 1.10.3's real output (pofctl's parser needed no change).
    - Scenario `p` (b)'s newcomer stays a candidate, so "no seat of the 12 went to `anthropic/claude`" holds trivially
      there; the Foundry suite (`PolishV31.t.sol`, the invariant) is F1's regression.

## 9. The v3.1 release candidate, rc4 (gates: the owner's go)

- [ ] 9.1 **Gate:** the owner's go for rc4, naming the commit (#310, #311 and this change on main). Verify: a dated comment by the owner on #251 (and #310's task 7.1 ticked with the same link).
- [ ] 9.2 **Gate:** the owner's go for the new disk; then the checker image and disk rebuilt at the rc4 commit (`scripts/checker-disk.sh`), its root hash and image digest recorded, and the public snapshot's dry run of that commit building the same digest with 0 kept terms (VP15). Verify: the digest in the rc record and the plan; the snapshot dry run's output linked on #251.
- [ ] 9.3 rc4 locally: `scripts/integration.sh --release-candidate <commit>` passes 3 runs in a row with `e`, `p` and `r`. Verify: `contracts/release-candidates/rc4.json` with `integration` passed.
- [ ] 9.4 **Gate:** the owner's go for the AWS run (`scripts/rc-aws.sh plan` first, its cost stated); then the external SEV-SNP validator on the AWS test chain with the new disk (`sevSnpValidator`, `attestedImages`). Verify: `evidence/rc-rc4/` and the record's items `passed`; both machines stopped afterwards.
- [ ] 9.5 **Gate:** the owner's approval and a cost estimate, after a passed dry run with the fake judge; then the small real-model run. Verify: `evidence/rc-rc4-model/` and `realModelRun` `passed`; the record's `result` `passed`, committed and linked on #251 and #310.

## 10. The v3.1 deployment (gates: the owner's go)

- [ ] 10.0 **Gate:** the owner's go for the live-v3 steps that need no deployment: the seed host's keeper-only node updated to this change's keeper (the runbook's update steps); `ORACLE_LIST_PRICES={}` in the owner's genesis validator's `node_config`, its own keeper staying on (VP2, VP16; decided 2026-11-23); the validator's Infura key, printed in its console, rotated (VP20); the seed's Terraform applied with `keeper_secret_arns` from the committed module and `create_instance = true` (VP22). Verify: the keeper's log shows gated calls and backoff lines and no key; the genesis node's next table posts only `anthropic.claude`; the old key refused by the provider; the seed's plan shows no destroy; recorded on #251.
- [x] 10.1 The v3.1 plan `contracts/deployments/sepolia-v3.1.plan.json`: families `["anthropic/claude"]`, the rc4 image, the keeper as launch infrastructure with its cost line (task 6.4), `mergeDays` 3 (#310's O4), `gasOverhead` 500,000, the same RID and `genesisRadNode` (#310's RB12), and #310's precondition checked. Verify: `deploy_sepolia.py`'s dry run against Sepolia passes and refuses any other commit's bytecode.
  - **Done (2026-11-25), with a new RID instead of the same one.** The plan: families `["anthropic/claude"]`, rc5's
    image `0xd0960af2…c50a` (rc4 at a36c7cd failed at run 3, #339; rc5 at 6f23f52 passed every item,
    `contracts/release-candidates/rc5.json`), the keeper `0xd793…E1aC` with its cost line; `mergeDays` 3 and
    `gasOverhead` 500,000 are in the record's constructor arguments. **Deviation from RB12:** v3's repository
    `rad:zyZXC9NqVuse8nXdpv7iYRScDHsN` is frozen at `81505595`: its only delegate key (`z6MkwbkgYB…`) was lost when the
    SEV-SNP host was replaced (its data volume was deleted with the instance), so no node can move its `main` again.
    The plan names a new repository, `rad:z2whCPbrSKbtyvwYjHXPZhN9ZkK5z` (genesis head `bc68e00`, a scrubbed snapshot
    of 6f23f52), and a new `genesisRadNode`, the genesis validator's node `did:key:z6MkvmUF…NqCw` (its delegate,
    threshold 1). RB12's precondition no longer guards anything: v3's `Heads` can't move the frozen repository. The
    dry run against Sepolia passed (verify-head on the new RID included).
- [ ] 10.2 **Gate:** the owner's go for deploying v3.1, naming the plan and rc4. Verify: a dated comment by the owner on #251 (#310's task 8.2 ticked with the same link).
  - Owner's go 2026-11-25 (in session), for the plan and rc5; broadcast by the owner. The dated comment on #251 is still
    to be posted.
- [x] 10.3 The owner broadcasts; the record `contracts/deployments/sepolia-v3.1.json` committed, v3's record marked `supersededBy`; the genesis validator registered as `anthropic/claude` on v3.1 with the watcher's draw duty on; the keeper-only node pointed at v3.1 as well as v3 (one process each). Verify: the script's checks pass; `pofctl --v3 verify-head` against v3.1 exits 0; a registration on v3.1 is drawn with no manual call.
  - **Done (2026-11-25) but for one check:** owner's go 2026-11-25 (in session); broadcast by the owner. Block
    12211341: RaceV3 `0xC02F191a82f9459FB4C003B68245c872a256a790`, registry `0xbF7138DAA5DC0b0796e56C79DA2Ed0F480b06B94`.
    The record and the plan committed, with rc5's AWS evidence (`evidence/rc-rc5`, `evidence/rc-rc5-model`) and the
    genesis binding boot on the v3.1 disk (`validator-kit/sevsnp/evidence/2026-11-25-genesis-v31/`, verify.py passed);
    v3's record carries `supersededBy` (and `supersededAt`: block, RaceV3, date). The genesis seat is `anthropic/claude`
    in the record. The seed seeds both RIDs, and its host runs two keeper-only units, one for v3 and one for v3.1. The
    script's checks passed, verify-head included (the record's `genesisHeadCheck`). **Open:** a registration on v3.1
    drawn with no manual call isn't observed yet (nor, so far, the genesis validator's watcher drawing on v3.1).

## 11. The Radicle hand-over (gate: the owner's go)

- [ ] 11.1 **Gate:** the owner's go for the hand-over (#310's RB12, task 8.4). Verify: a dated comment by the owner on #251 and #310.
- [ ] 11.2 The genesis validator's node switches its seat part to v3.1; v3 keeps only its keeper. Verify: `pofctl --v3 verify-delegates` passes against v3.1's seats; canonical `main` unchanged.
- [ ] 11.3 The guides and README name v3.1 as live, v3 as superseded, and the family `anthropic/claude` throughout (VP12); the v3 note on `ORACLE_LIST_PRICES` moves to the superseded section. Verify: `tests/test_guides.py` passes; `grep` finds `anthropic.claude` only in v3's superseded records and notes; `scripts/radicle-spike.sh --guides` passes.

## 12. The owner's follow-ups (decided 2026-11-24; before task 9.2's disk rebuild)

- [x] 12.1 Q1 (VP23): the watcher keeps a drawn check (JUDGING, HELD, WINDOW) on its list until it is final, read every `RETRY_MINUTES`; starts are counted per round (`redraws`, seed block or `retryAt`), so a released round wakes a host once more and the same round never starts twice; a given-up check stays listed; drawn checks go first when the state is full; another slot on a listed panel is a new seat. Verify: `tests/test_sevsnp_watcher.py` gains redraw after a release, no duplicate wake over hours of polling, removal once final, the state's drop order and the new seat; the ABI check reads `redraws` at word 41.
- [x] 12.2 Q2 (VP24): `oracle.v3.draw_and_signal` (waiting: signal, draw, signal again if seated; sealed: draw, signal), used by the keeper (`NodeV3._draw_and_signal`, which the keeper-only node shares) and by `pofctl --v3 draw`; the keeper signals a wait once per wait round. Verify: `tests/test_oracle_v3.py`'s `KeeperDrawAndSignal`, whose waiting test failed first (`['signal', 'draw']`); `tests/test_pofctl_v31.py`'s `TestDraw`.
- [x] 12.3 Q3 (VP25): `scripts/judge_run.py` without the internal `GATEWAY` default: `MODEL_GATEWAY_URL` required by `run`, `run-v2` and `judge_memory_run.py run` (first, one line, nothing sent), and by `GatewayJudge`, which `judge_from_env` passes it; the report, the oracle README and `oracle/__main__.py`'s help updated. No workflow used the default. Verify: `tests/test_judge_gateway.py`, `tests/test_judge_memory.py` and `tests/test_oracle.py`; the snapshot's dry run (`scripts/github_snapshot.py proof-of-fix --target radicle`) scans clean.
- [x] 12.4 Q4 (VP26): `pofctl --v3 attempt --bounty B`: the checks first (open, claim within the room, the fee in the wallet), the fee coin's approval with VP17's wait and retry when the fee is above 0, the transactions and the next step in text and `--json`; the solver guide's attempt block uses it; the Radicle set's funded fix runs it before `submit`. Verify: `tests/test_pofctl_v31.py`'s `TestAttempt`; `tests/test_guides.py`.
- [x] 12.5 The integration sets with 12.1–12.4: `scripts/integration.sh --version 3` (launch and rebase sets), `--version 3 --radicle` and `scripts/radicle-spike.sh --guides`. Verify: their results in the PR.
  - Done 2026-11-24 on e2c94b2 (local Docker, port 8596, `pofv31*`): launch passed 1,018 s, rebase 377 s; `--radicle` passed (its funded fix records the attempt with `pofctl --v3 attempt --bounty 1`); `radicle-spike.sh --guides` passed. No containers or networks left.
- [x] 12.6 VP27: `oracle/rpc.py`'s `Wallet` keeps its nonce monotonic within a process (max of the remembered next nonce and the pending count); a refusal naming a taken nonce, for fresh bytes whose hash the chain doesn't know, is signed again past it at most 3 times, then fails naming the nonce and the redacted RPC host; bytes once out keep the maybe-sent wait; a transaction no node shows after 20 s is sent once more with the same bytes. **Image file:** `oracle/rpc.py` is in the node image, so this lands before task 9.2's disk rebuild. Verify: `tests/test_rpc_retry.py`'s `StaleNonces` (five tests failed first, the dropped one with the live "no receipt … after 60s"); the duplicate tests and `Transactions` pass; `scripts/check.sh`; the launch set.
  - Done 2026-11-24 on 1b2e2c1 (the node branch merged): `StaleNonces` 7 tests, `scripts/check.sh` 2,395 tests OK; `scripts/integration.sh --version 3 --sets launch` (local Docker, port 8596, `pofv31`) passed 955 s on its second run. The first run stopped at scenario x ("its audits drawn and their challenge tried", 730 s) with no nonce refusal or missing receipt in its log; the same commit then passed every scenario. No containers or networks left.

## Workflow follow-up

- #310's tasks 7.1–8.5 and this change's tasks 9–11 are the same release steps (VP16): each is done once and ticked in
  both changes with the same evidence.
- Archive this change after task 11.3, with #310's and #311's.
