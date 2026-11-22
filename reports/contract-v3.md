# Contracts v3: Panels, proof levels and RaceV3 (proof-of-fix#138, tasks 3.2, 3.4 and 3.5 of #132)

Task 3.2 builds `Panels`, v3's draw and verdict bookkeeping, on `Validators` (3.1) and `FeesV3` (3.3). Task 3.4 adds the proof levels and the constitution's lists (below, "Task 3.4"), and the owner's decision on a reveal missed after the majority revealed. Task 3.2 came in two milestones:
- **Milestone A:** the draw; seals, reveals and receipts on-chain (D18, in place of #122 and #85 5.5/5.6); the replacement of silent judges; finality and the k = 1 hold.
- **Milestone B:** shadows; audits; challenge panels and the frozen window; the family scores; the constitution tier; and a draw that registry changes made after its seed is fixed can't re-roll.

Task 3.5 builds `RaceV3`, the race on Panels and FeesV3, splits `FeesV3.roll` into bounded parts, and replays group 7's market on them (below, "Task 3.5").

## #251, contract batch 5: `startWindow` and the k = 1 hold's audits (#290; launch design L25's note of 2026-11-21; task 3.28)
Two gaps around the k = 1 hold, found by #256's integration flake (task 3.27) and fixed before the Sepolia deploy (the contracts are keyless: the bytecode is fixed at deploy).
- **`Panels.startWindow` (PanelsVerdict.startWindow) refuses while a challenge is open** (`NotReady`). It started a held verdict's window with its challenge open; `frozenLeft` is set only when a challenge opens in the window, so the challenge's lapse or resolution resumed the window with 0 left and the verdict could be final at once. Anyone may call it. Refusing is one condition and leaves no window running beside an open challenge without a frozen rest; the window starts whole once the challenge closes. The other paths that set `finalAt` or `frozenLeft` (the count, `openChallenge`, a resolution, `lapseChallenge`, a challenge panel's `release` past the deadline; disputes and appeals go through them) have no such gap.
- **The k = 1 hold counts the audits still due** (`PanelsVerdict._challengersReady` → `PanelsDraw.challengersReady`): `count` = CHALLENGE_K[1] + `auditsDue` − `auditsDrawn` (+ 1 while the random audit is undecided): 6 at the count, 3 once every audit is drawn (the drawn auditors are `GONE` on the panel, outside the count as before). Its audits are drawn from the same validators and each sits out of the challenge, so before this honest audits that caught a wrong lone pass could leave nobody to judge it. `challengersReady` now applies the caps of a panel of `HOLD_K` (3) whatever `count` is: under `Strict` it counts validators that pairwise fit, so any 3 left once the auditors are drawn could sit together (with `count` 3, exactly as in batch 4).
- No signature, event, storage or ABI change. The node's keeper keeps its guard (no `startWindow` while a challenge is open); it now only saves the reverting call.

**Sizes** (runtime; EIP-170 24,576):

| Contract | Runtime | Margin | Before batch 5 |
|---|---|---|---|
| `PanelsVerdict` | 23,163 | **1,413** | 23,060 (1,516) |
| `Validators` | 22,908 | 1,668 | unchanged |
| `RaceV3` | 22,612 | 1,964 | unchanged |
| `RaceV3Annex` | 22,362 | 2,214 | unchanged |
| `RaceV3Endings` | 21,845 | 2,731 | unchanged |
| `Panels` | 19,026 | 5,550 | unchanged |
| `FeesV3` | 18,026 | 6,550 | unchanged |
| `PanelsJudge` | 16,515 | 8,061 | unchanged |
| `PanelsDraw` | 10,656 | 13,920 | 10,279 (14,297) |
| `PanelScores` | 5,869 | 18,707 | unchanged |
| `SolverBook` | 3,707 | 20,869 | unchanged |
| `PoolV3` | 1,927 | 22,649 | unchanged |
| `TestCoin` | 1,914 | 22,662 | unchanged |
| `CoinFaucet` | 649 | 23,927 | unchanged |

`PanelsVerdict` stays the tightest; the next change to the draws should still move `drawAudits` or `drawChallenge` out of it.

**Tests.** `test/v3/HeldWindowV3.t.sol` (`HeldWindowV3Test`, 4, each failing before the fix: `startWindow` waits for an open challenge and the window starts whole after its lapse; a lone wrong pass caught by its audit, held at 3 ready, its challenge waiting and then reversing it, the window whole after; the hold's count 5 held, 6 at once; under `Strict` caps, pairwise-fitting challengers with room for the audits). `DrawabilityCasesV3Test.test_n{7,15}_launch_loneWrongPassAudited` (one `LONE` line a case, 132 cases): an outage leaves the genesis validator alone, `m` others back by its count. Before the fix the wrong pass was paid in 24 of 60 cases at 7 validators and 21 of 72 at 15 (m = 3 and 4, and m = 5 with a random audit); after it, in none: held and unpaid while the network stays short, reversed once 3 are left after its audits (the table in design L25's note). Scenario **x** of the integration suite's `launch` set (`tests/integration/scenarios_v3.py`). `scripts/contracts.sh test`: **750 passed with production windows and 750 with `POF_TEST_WINDOWS=minutes`** (744 before: 6 new, 0 removed).

**Existing tests changed (the hold's count, not weaker; every assertion kept):** the k = 1 verdicts whose window started with 3 to 5 validators ready now get 6, or draw their audits first: `PanelsV3Test.test_theGenesisValidatorsFirstVerdicts` (and it now asserts the hold at 3 ready), `PanelsV3Test.test_theNetworkAlreadyHasChallengers` (3 → 6), `PanelsV3BTest.test_aColludingGenesisValidator` (3 → 6), `test_aLoneValidatorPassesABadFix` (3 more before `startWindow`), `test_challengersAlreadyEligible` (4 → 6), `test_oneAuditorMissesABadFix` (5 → 6), `PanelRulesV3Test.test_oneHostLayout` (2 → 5 on hosts of their own, and it asserts the hold at 2), `PanelsLevelsV3Test.test_aHiddenLoneVerdictWaitsForTeeChallengers` (3 → 6 TEE validators), `PanelLivenessV3Test.test_anAuditThatCantBeDrawnIsReleased` (also run as `PanelLivenessV3TaxiTest`; 3 → 6, all paused after the window starts), `CapacityV3Test.test_pausedValidatorsArentChallengers` (3 → 6), `RaceV3Test.test_aHeldVerdictPaysNothingUntilFinal` and `test_auditsPaidFromTheDeposit` (3 → 6), `TaxiV3Test.test_judgesBeyondTheDepositArePaidByThePool` (3 → 6). `tests/test_integration_v3.py` `test_the_launch_set_is_the_sepolia_record`: the launch set's scenarios are `u w v x`.

## #251, contract batch 4: panel rules, panels of 3, challenges end (launch design L23, L24, L25; tasks 3.22–3.27)
The owner's decisions of 2026-11-20 on [`reports/challenge-drawability-v1.md`](challenge-drawability-v1.md), built as the spec gives them.

**L23, the caps as deployment settings.** `PanelRules` (`src/v3/PanelRules.sol`): `operatorCap`, `hostCap`, `teeCap`, each `Cap.Strict` or `Cap.Off`; `kTop`; `challengeSize`. Panels' constructor takes it as a sixth argument, checks it (`PanelRulesLib.check`: `kTop` odd, 1 to 7; the enums by the ABI decoder) and keeps it in immutables; `panelRules()` reads it back; it rides in `Env` to the libraries and into `PanelsDraw.Ctx` (`opCap`, `hostCap`; a TEE cap `Off` sets `teeFrom` beyond every k). `PanelsDraw.fits` applies the operator cap (one per account, every k), the host cap ((k − 1) / 2 from k = 3) and the TEE-type cap ((k − 1) / 2 from `teeFrom`) only when `Strict`; the family cap is D20's, unchanged. Under `Strict`, `challengersReady` (the k = 1 hold) now counts only challengers that could sit together under those caps (a `fits` check on the three it finds, in scan order; the family cap is not counted, as before), so a lone verdict on one host or one operator account stays held instead of starting a window whose challenge can't be drawn. Under `Off` the count is what it was. Defaults: `PanelRulesLib.strict()` = all `Strict`, 7, `Larger` (what every deployment had); the Sepolia launch: `PanelRulesLib.launch()` = all `Off`, 3, `Same`.

**L24, panels of 3 and same-size challenges.** Issue-tier draws go up to `kTop` (`PanelsBase.drawCounted`); the constitution tier keeps exactly `K_MAX` = 7 (ADRs, escalated fixes, `CONSTITUTION_QUORUM` 5, `CONSTITUTION_MIN_ELIGIBLE` 21). `PanelsBase.challengeRange(e, k)`: with `Same` and k ≥ 3, `kTop = kMin = k` (a fresh panel of the verdict's size, no step-down); otherwise D4's `CHALLENGE_K[k]` down to k + 2 (7 for 7), which also keeps a lone verdict's 3. The fresh panel excludes the challenged panel, its auditors and its replaced judges (`exPid`, as before) and parties. D27's second draw is unchanged as the fallback. The race prices for the rules (`RaceV3Base`'s immutables `topJudges`, `coverJudges`, read from `panels.panelRules()` at construction): a check's deposit is `FeesV3.maxDeposit(repo, kTop)` and a challenge's cover `depositFor(id, repo, PanelRulesLib.challengeTop(rules))`, the largest challenge panel the rules draw: `kTop` with `Same` (3 when `kTop` is 1), `CHALLENGE_K[kTop]` with `Larger`. With the defaults both are 7, as before; on Sepolia both are 3. (The spec says "priced for `kTop` judges"; the two agree on both recorded settings, and with `Larger` and a `kTop` below 7 the cover follows the larger challenge panel so it still covers it.)

**L25, challenges always end.** `Windows.challengeDeadline` (CHALLENGE_DEADLINE, **120 h, decided (owner, 2026-11-20)**; the last field of `Windows`; 120 minutes in `inMinutes()`), nonzero, below 2^32 s, and at least `maxRedraws × retryDelay + seal + reveal + stuckGrace` (99 h in production), or both constructors refuse (`BadWindows`). Each challenge (filed, disputed, or an auditor's) gets `challengeBy` = opening + CHALLENGE_DEADLINE.
- *A retry clock:* a challenge that finds no panel waits with `challengeRetryAt` = now + RETRY_DELAY beside its registry epoch; `drawChallenge` re-targets (fresh seed block and snapshot) once the registry changes **or** the retry time has come (a capacity change, e.g. an un-pause, isn't a registry change and needn't be).
- *A lapse:* past `challengeBy`, `drawChallenge` refuses (`TooLate`) and `lapseChallenge(id)` (anyone) lapses a challenge with no panel. A drawn panel that completes is counted as before, even after the deadline.
- *A stuck challenge panel:* `release(pid)` now takes `Kind.Challenge` panels on L19's terms (replacements exhausted, after the reveal deadline + STUCK_GRACE; silent seats slashed by `_vacate`, sealed ones closed unslashed). It isn't one of the submission's L19 rounds. Before the deadline the challenge waits again (`challengeEpoch`, `challengeRetryAt`); after it, it lapses.
- *What a lapse does* (`PanelsJudge._lapse`): `challengeOpen` false, the verdict as it was, the window resumed from `frozenLeft`, `challengeClosed` for each original judge, no slash; `lapses` + 1; a race-filed challenge sets `filedLapsed`. `RaceV3.settleLapse(id)` (anyone) then returns the filed challenge's stake and cover whole, a D21 dispute's stake too, with no reward and nothing to the accused. `settleChallenge` refuses a lapsed filing (a later panel isn't its own). A released challenge panel's seats that revealed with receipts are paid by `payPanel` from the check's deposit and the pool, never from the cover.
- *Against free delay (decided (owner, 2026-11-20)):* a verdict takes at most MAX_REDRAWS (3) lapsed challenges: `Panels.challenge` then refuses (`TooManyLapses`), an auditor's mismatch opens none, and the verdict finalizes at its window.

**Signature and ABI changes.**
- `Panels` constructor: `(IPanelsRegistry, IPanelsFees, IPanelScores, bytes32[], Windows, PanelRules)` (was five arguments).
- `Windows` gains `uint256 challengeDeadline` (last): `Panels.windows()`, the Validators genesis (`Validators.Genesis.windows`) and `windowsHash` change with it.
- New on `Panels`: `panelRules() → PanelRules`, `challengeRange(uint256 k) → (top, min)`, `lapseChallenge(uint256 id)`, `CHALLENGE_DEADLINE()`; events `ChallengeReleased(uint256 indexed id, uint256 indexed pid, bool lapsed)`, `ChallengeLapsed(uint256 indexed id, uint256 lapses)`; error `TooManyLapses()`. `release(uint256)` now also releases challenge panels; `drawChallenge` can revert `TooLate()`.
- `Submission` (Panels' view) gains, last: `uint64 challengeBy, uint64 challengeRetryAt, uint8 lapses, bool chalFiled, bool filedLapsed` (the race reads word 48, `S_FILED_LAPSED`; `oracle/v3.py`'s `PANELS_SUBMISSION` follows).
- `Env` (library ABI) gains `challengeDeadline, opCap, hostCap, teeCap, kTop, sameSize`; `PanelsDraw.Ctx` gains `opCap, hostCap`; `ShadowCtx` gains `opCap, hostCap, teeFrom`.
- New on `RaceV3`: `settleLapse(uint256)` (to the annex) and event `ChallengeLapsed(uint256 indexed submission, address indexed challenger, uint256 returned)`; `payPanel` accepts a released challenge panel. RaceV3's constructor reads `panels_.panelRules()`.
- Scripts: `DeploySepolia.s.sol` reads `DEPLOY_PANEL_CAPS` (strict|launch), `DEPLOY_K_TOP`, `DEPLOY_CHALLENGE_SIZE` (larger|same) and records `panelRules`, `constructorArgs.Panels.rules` and `windows.challengeDeadline`; `scripts/deploy_sepolia.py` takes `--panel-caps`, `--k-top`, `--challenge-size` (defaults strict, 7, larger), requires `panelRules` in the release-candidate record equal to them, refuses a record whose rules differ, and after a broadcast reads `panelRules()` back from Panels. `NodeV3Local.s.sol` takes `LOCAL_PANEL_CAPS`, `LOCAL_K_TOP`, `LOCAL_CHALLENGE_SIZE` (`scripts/devnet.sh`: `DEVNET_V3_PANEL_CAPS`, `DEVNET_V3_K_TOP`, `DEVNET_V3_CHALLENGE_SIZE`). No new contract is deployed (`PanelRules.sol` is a struct, enums and an internal library), so the release candidate's bytecode set is unchanged.

**Sizes** (runtime; EIP-170 24,576; initcode under EIP-3860 49,152):

| Contract | Runtime | Margin | Before batch 4 | Initcode |
|---|---|---|---|---|
| `PanelsVerdict` | 23,060 | **1,516** | 22,355 (2,221) | 23,092 |
| `Validators` | 22,908 | 1,668 | unchanged (the order check runs in its constructor) | 31,160 |
| `RaceV3` | 22,612 | 1,964 | 22,570 (2,006) | 32,434 |
| `RaceV3Annex` | 22,362 | 2,214 | 21,731 (2,845) | 25,519 |
| `RaceV3Endings` | 21,845 | 2,731 | 21,814 (2,762) | 24,796 |
| `Panels` | 19,026 | 5,550 | 17,254 (7,322) | 22,700 |
| `PanelsJudge` | 16,515 | 8,061 | 15,266 (9,310) | 16,547 |
| `PanelsDraw` | 10,279 | 14,297 | 9,789 (14,787) | 10,309 |

The lapse and the challenge panel's release went into `PanelsJudge` (the most room), so `PanelsVerdict` kept 1,516 bytes; nothing had to move to a new library. `PanelsVerdict` is now the tightest of the deployed set; the next change to the draws should move `drawAudits` or `drawChallenge` to `PanelsJudge` or a fourth library.

**Gas** (call frame, `PanelRulesV3Test.test_gasChallengesEnd`, `ChallengesEndV3Test`): `drawChallenge` with no panel (strict, k = 7 at 7 of 7, three families: it waits, its retry time set) **531,700**; `drawChallenge` at the retry time (re-targets) **75,100**; `lapseChallenge` (seven original judges' challenges closed, the window resumed) **153,200**; `drawChallenge` drawing a fresh panel of 3 of the 4 outside (launch rules) **741,300**; `release` of a challenge panel of 3 (one silent seat slashed, two closed; it waits again) **90,900**; `RaceV3.settleLapse` (stake and cover back) **129,000**. The race's steps and Panels' draws with the default rules are as before (`test_gasPerStep`: `commit` 536,700, `result` (k = 3) 579,300, `challenge` 580,100).

**Tests.** `test/v3/DrawabilityV3.t.sol` (`PanelRulesV3Test`, 21: deployment-binding's "The panel caps are set at construction" scenarios ("The owner's validators fill panels on Sepolia", "No change after deployment") and "The k = 1 hold counts challengers under the caps" ("The owner's validators on a strict deployment"); the report's one-host and one-TEE-type layouts; judge-panels' "The Sepolia launch at 7 validators", "A challenge of a panel of 3 at 7 validators" (challenge and test dispute), "A lone verdict's challenge keeps 3 judges", "An audited verdict's challenge", "ADRs keep their size", level B's 48 h, 15 validators, `Larger`'s D4 panel; panel-liveness' "No panel by the deadline", "A panel completes after the deadline", "A silent judge on a challenge panel with no replacement", "A validator un-pauses", the MAX_REDRAWS lapses, the deadline; gas), `test/v3/DrawabilityCasesV3.t.sol` (16: every row of the report's tables at 7 and 15 validators, $10–$125, 1–3 families before and after all are known, strict and launch, 64 cases, `CASE` lines), `test/v3/ChallengesEndV3.t.sol` (5: a lapsed challenge's and a lapsed test dispute's stake and cover returned whole with no reward, `settleLapse` only for a lapse and the MAX_REDRAWS refusal at the race, deposits and covers priced for `kTop`, a released challenge panel's revealed seats paid from the deposit), `LaunchBindingV3Test.test_theChallengeDeadlineIsCheckedForOrder`, and `LivenessInvariantV3`'s four `ChallengeLiveness{Strict,Launch}{7,15}Test` (L19's invariant as L25 restates it, with challenges, test disputes, silences, pauses, joins and leaves; afterwards every submission final or refunded and no challenge outliving its deadline without a panel). `scripts/contracts.sh test`: **744 passed with production windows and 744 with `POF_TEST_WINDOWS=minutes`** (693 before: 51 new, 0 removed).

**Existing tests changed (the decided behaviour, not weaker):**
- `PanelsV3Test.test_theNetworkAlreadyHasChallengers`, `PanelsV3BTest.test_oneAuditorMissesABadFix`, `PanelsV3BTest.test_challengersAlreadyEligible`: they put the other validators on the genesis validator's host to step k down to 1 while "challengers exist". Under `Strict` caps (L23) three validators on one host can't sit together on a challenge panel of 3, so that verdict is now held, which is the report's layout bug fixed. The lone verdict is now drawn while the genesis validator is alone, and the validators join on hosts of their own before its count; every assertion after that is unchanged.
- `PanelsV3BTest.test_aChallengeWithTooFewValidators`: it waited 30 days to show a challenge with no panel never ends; under L25 it lapses at CHALLENGE_DEADLINE. The registry change now comes within the deadline (past the window's end), and `NothingChanged` is asserted before the retry time; the draw of 5, the verdict and the resumed window are asserted as before.
- `LaunchBindingV3Test.testFuzz_windowsInOrderDeploy`: it builds `Windows` field by field and now also sets `challengeDeadline` at or above its lower bound (else every case would be refused).
- `RaceV3Test.test_noPrivilegedCall` and `PanelsV3Test.test_noFunctionChangesAParameter`: the new functions added to their lists (`settleLapse`; `lapseChallenge`, `panelRules`, `challengeRange`, `CHALLENGE_DEADLINE`), and the count 34 → 35.
- `RaceV3Test.test_theRaceReadsPanelsRecordsRight`: three more words checked (41, 44, 48 of `Submission`; 13 of `Panel`).
- `LivenessInvariantV3Test`: its handler takes the network's size and rules (`new LivenessHandler(3, false)`, the old run), the keeper also draws, redraws and lapses challenges, and the invariant checks challenges too (stricter, never looser).
- `test/v3/helpers/ReplayStubs.sol`: the replay's scripted Panels answers `panelRules()` with the strict defaults (RaceV3 reads it at construction).
- `tests/integration/suite_v3.py` (the devnet story, `scripts/devnet-v3-e2e.sh` and `scripts/time-to-heal.sh`): under L25 a challenge filed before the network can draw its panel lapses at CHALLENGE_DEADLINE. Step 1's watcher now files again once a fresh panel could be drawn (`Net.rechallenge`, after the keeper settled the lapse; at most MAX_REDRAWS lapses), and the time to heal reports the lapses. Step 8 (`--heal`) grew the network while the bad fix's challenge stayed open, its window frozen, which L25 ends; now v6–v8 qualify first, the bad fix is judged by a panel of 3 of the four validators bonded for its bounty (three of them lying), the others top up, and an honest validator's challenge is drawn at once (a fresh panel of 5) and reverses it. The clock also jumps to a challenge's deadline and retry time, and to a stuck challenge panel's release.
- `tests/sandbox_env.py`: `EXPECTED` 13 → 18 (five new `outside_sandbox` uses in `tests/test_deploy_sepolia.py`).
- `tests/test_deploy_sepolia.py`, `tests/e2e_deploy_sepolia.py`: the release-candidate fixtures name `panelRules` (a required field now); the e2e deploys the Sepolia rehearsal with the launch's rules.
- `tests/test_pofctl_v3.py`, `tests/e2e_pofctl_v3.py`: the fake chain answers `panelRules()`; the deposit is read for `kTop` judges.

## #251: the Radicle node key in the registration (launch design L11 condition 1, owner 2026-11-20; tasks 3.21 and 4.1)
The owner chose a signed field of the v3 registration (not a separate setter, not an off-chain binding) for the link between a seat and its Radicle node (`specs/radicle-hosting`, "A seat maps to one Radicle node key on-chain").
- **The field.** `IValidators.Registration.radNode` (`bytes32`, last field): the 32-byte Ed25519 public key behind the node's `did:key:z6Mk…`. It is in `REGISTRATION_TYPEHASH` (`…,uint32 firmware,bytes32 radNode)`) and so in the digest the key signs, at genesis and at `register`. `IValidators.Validator.radNode` (last field) stores it; `radNodeOf(address)` reads it (in `IValidators`), whatever the validator's state, 0 for a key never registered.
- **Zero is allowed:** it registers no node. The validator is drawn and judges as before; off-chain, its seat is reported as unmapped by `verify-delegates` and never counted as a delegate (no honest node signs a revision giving it a key).
- **One seat per node:** a nonzero key that another registration still holds (Candidate, Active or BelowFloor) is refused, `NodeTaken()`. A Leaving or Exited validator holds none, so its node can be registered again by a new key. There is no setter: a validator changes its node by registering again (a new key, after leaving with the old one). `KeyTaken` still refuses a second registration of the same key.
- **The event:** `Registered(address indexed key, address indexed operator, bool genesis, uint8 level, uint256 bond, Registration r, bytes32 indexed radNode)`: the node key is in `r` and is the event's third topic, so a node's seat can be found by a log filter. The event's signature changed (`Registered(address,address,bool,uint8,uint256,(…,uint32,bytes32),bytes32)`).
- **Signature changes:** `Registration` and `Validator` gain their last field (so `register(Registration,uint256,bytes)`, `registrationDigest(Registration)`, `validator(address)`, `Validators.Genesis.validators` and the `Registered` event change their ABI); `radNodeOf(address)` and `NodeTaken()` are new. The deploy script takes `DEPLOY_GENESIS_RAD_NODE` (never 0 for the genesis validator) and `NodeV3Local` `LOCAL_GENESIS_RAD_NODE` (default 0); both records name the key.
- **Tests:** `test/v3/RadNodeV3.t.sol` (10: the genesis's node, a registration's node with its event and getter, the key covered by the signature, 0 allowed and read back as no node for a drawable seat, a node held by a candidate, an active, the genesis or a below-floor validator refused, a node freed when its validator leaves, registering again (the same key refused as `KeyTaken`; a new key on a new node, the old node then free), a fuzz of two keys, gas); `scripts/contracts.sh test`: 693 passed with production windows and 693 with `POF_TEST_WINDOWS=minutes` (683 before); the test helpers register every validator with a node key of its own (`radNodeFor`), so every suite runs with the field set; `radNodeOf` in the ABI's list.

| Contract | Runtime | Margin under 24,576 | Initcode | Margin under 49,152 | Before |
|---|---|---|---|---|---|
| `Validators` | 22,908 | **1,668** | 31,040 | 18,112 | 22,435 (2,141) |
| `Panels` (reads the longer `Validator`) | 17,254 | 7,322 | 20,357 | 28,795 | 17,242 |

The other contracts are unchanged. `Validators` has the smallest margin of the deployed set now (RaceV3 2,006, RaceV3Annex 2,845). If it needs more, `applyAdr` and `_change` can still move to a linked library (as noted under 3.4).

Gas (call frame, `RadNodeV3Test.test_gasRegister`, after a first registration warms the shared slots): `Validators.register` **428,600** with a node key, 383,500 without (+45,200: the record's word and the holder's word, two new slots, and the topic). The race's steps (`test_gasPerStep`) don't call the registry's registration: `RaceV3.register` 770,600, `commit` 536,400, `result` (k = 3) 576,300, `claim` 247,200, `merge` 310,100.

## #251: the test coin and its faucet (launch design L17 as amended on 2026-11-20, tasks 3.17 and 3.18)
The owner replaced Circle's Sepolia USDC with the project's own valueless test coin on 2026-11-20.
- **`TestCoin`** ("proof-of-fix test coin", `POFTEST`, 6 decimals): an OpenZeppelin ERC-20 whose genesis mint is in its constructor (`genesisMint()` reads its total) and whose `mint` only its `faucet()`, the contract that created it, may call (`NotFaucet`).
- **`CoinFaucet`**: deploys the token in its own constructor (so neither needs the other's address in advance, and the faucet's creation code holds the token's); `claim()` mints `CLAIM_AMOUNT` (20 coins) to the caller, at most once per address every `CLAIM_INTERVAL` (2 hours) from its last claim (`TooSoon(next)`; `nextClaim(address)` readable). No owner, admin, pause, setter or upgrade on either; both call `LaunchChain`.
- **The deploy (DeploySepolia.s.sol):** CoinFaucet first, on Sepolia and the local ids alike, then the rest as before with the token as the coin. The genesis mint is 5,000 coins by default: the genesis validator's 250 to the registry maker's precomputed address (it bonds them into Validators), the rest to the recipient named at deploy. The release-candidate set is 11 contracts (TestCoin and CoinFaucet added).
- **Tests:** `test/v3/TestCoinV3.t.sol`, 17 tests (each scenario of `deployment-binding`'s two coin requirements by name, repeat claims, a fuzz of the wait and of other minters, the ABI's only writers, chain 1 and other public chains refused for both).

| Contract | Runtime | Margin under 24,576 | Initcode | Margin under 49,152 |
|---|---|---|---|---|
| `TestCoin` (created by CoinFaucet) | 1,914 | 22,662 | 3,409 | 45,743 |
| `CoinFaucet` (initcode holds TestCoin's) | 649 | 23,927 | 4,693 | 44,459 |

## #251, contract batch 3: seats by rank, test disputes, the appeal, reputation, the judges' fee, active solvers (tasks 3.3, 3.6; #132 10.4, 11.4, 12.5)
Batch 3 of the testnet launch builds the solver-side rules the owner decided on 2026-11-19, with [ADR 0007](../docs/adr/0007-solver-side-parameters.md)'s values (launch design L6, L7, L8; #132 D20, D21, D24, D27, D29, D30). No solver's deposit exists anywhere.
- **Seats by rank (D20, `PanelScores`, `PanelsDraw`).** A Scored family more than `SEAT_MARGIN` (5 points) below the best Scored family is a contender: not drawn for counted, audit, challenge or replacement seats, drawn as a shadow (with barred families: `unseatedCount`). Neutral and Recovering families stay seated (D23's contender start for a new family isn't built). The family cap applies only while at least `CAP_MIN_FAMILIES` (3) families are seated (`capApplies`). PanelScores knows a family from its first scored counted verdict (`families()`), and re-ranks at every counted verdict and recovery (`_reseat`: one read a family, a write only where a seat or a count changes). Against grinding, as `isBarredSince`: a family seated by rank after a draw's snapshot isn't drawn by it (`isSeatedSince`), and a draw whose snapshot predates a switch of the cap applies it.
- **The second draw among few families (D27).** While fewer than 3 families are seated at a challenge's snapshot, a challenge of a panel of 3 or more that can't draw its larger fresh panel is judged by a second draw of the original size, the original judges not excluded (`SecondDraw`); with three families seated it waits as before. **Judgement call:** not for k = 1 (a second draw of one could seat the lone judge on its own verdict; its hold already waits for CHALLENGE_K[1] challengers).
- **The test dispute (D21, `RaceV3.dispute(id, test)`).** Against a pass in its window (or held): the stake is the larger of $5 and 10 % of the bounty, beside the panel's worst-case cover (as a challenge). The challenge panel decides whether the fix fails (the test's hash is its evidence; the checker image's run is the judges'). Upheld (reversed): stake and cover back, the panel paid from the fix's fee and the pool, `EVIDENCE_REWARD_BPS` 1,000 of the bounty to the disputer from the pot when the reversed fix had won the bounty (otherwise no pot pays: a later pass would never have been paid), and the disputer counts as active if it has a merged fix. Rejected: the panel paid from the cover, the stake to the solver. A receipt challenge (`challenge`) is unchanged.
- **The appeal (D24, `RaceV3.appeal(id, test)`).** Once, by the rejected fix's solver, while its bounty is open, within `APPEAL_WINDOW` (72 h, a new field of `Windows`; minutes in `inMinutes()`) of its counted panel's reveal deadline, with the test's hash and **no stake** (owner, 2026-11-19: the stake first built, the larger of $5 and 10 % lost to the pool, was dropped): a new submission with its own deposit (the appeal fee, 0 on Sepolia) drawn fresh from the seated families. `close(id)` only closes a decided check's claim.
- **Reputation and claims (D29, `SolverBook`).** RaceV3 deploys a `SolverBook` (its only writer; readable by anyone, `RaceV3.solverBook()`): each commitment registers its claim (the bounty it's judged at) against `REP_BASE` $50 + `REP_MULT` 1 × reputation, or the commit reverts with `OverCap` and costs nothing; the merge adds the bounty to the reputation; a reversed pass takes 2 × its bounty off, not below zero, once (at the race's `sync` or the dispute's settlement, and at `close`/`finish` if nobody had); claims close at finality (`finish`, `close`, the merge, `mergeExpired`) or when a check ends unjudged.
- **The judges' fee (D30, `Config.judgeFee`), two modes.** **0, the pure taxi fare (Sepolia's, owner 2026-11-19):** a fix posts FeesV3's worst-case deposit for K_MAX judges, its counted judges, audits and challenge panels are paid by the meter (the pool beyond the deposit), and whatever is left returns to the solver at `finish`, a withdrawal, a time-out or a release, pass or fail; the pool keeps no fee. **Above 0, the flat fee (for a mainnet decision):** every fix's submission pays it in place of the deposit, its judges are paid from it at market prices (the pool beyond it), and its rest goes to the sponsors' pool at `finish` or a withdrawal, never back except when the network never judged it (timed out, released, L19). Registration checks keep FeesV3's deposit in both. A constructor argument, so the deployment record lists it (`mode: taxi`, `judgeFee` 0). The Sepolia deploy script also sets the attempt, evaluation and appeal fees to 0 (a solver pays only the metered validation); a late commit with an evaluation fee of 0 now charges nothing instead of reverting on a zero transfer.
- **Active solvers and the pledge gate (L6, task 3.3).** An identity is active for `ACTIVE_WINDOW` (26 weeks, a new field of `Windows`) after its fix is merged, or after its failing-test dispute is upheld if it already has a merged fix. `pledge` reverts with `TooFewActiveSolvers(count)` while fewer than 3 are active; unfunded bounties are raced, and funded ones continue, whatever the count. The book keeps identities in order of their last activity, so the gate reads at most three and the count stops at the first one past the window. **Judgement call:** activity is recorded at the merge (the fix is in the repository) and at the dispute's settlement, not at the verdict's finality time.
- **The split.** RaceV3 had 916 bytes left. `report` moved to the endings (the race keeps a delegating entry), and so did `register`, `openBounty`, `payShadow`, `signal` and `finish` from the annex. The endings are now deployed first, on their own, and passed to the annex's constructor, which checks their fingerprint: with them inside, the annex's initcode reached 48,277 of EIP-3860's 49,152. **Constructor changes:** `RaceV3Annex(config, bountyCap, totalCap, panels, pool, start, endings)`; `RaceV3Endings(config, bountyCap, totalCap, panels, pool, start)` deployed by the deployer; `RaceV3Base.Config` gains `judgeFee` (last field), so RaceV3's, the annex's and the endings' `config` tuples change; `Windows` gains `appeal` and `active` (last fields), so Validators' genesis and Panels' constructor tuples change. `SolverBook(activeWindow)` is created by RaceV3's constructor (no new argument).

Sizes (runtime bytes, `scripts/contracts.sh sizes` and the artifacts for the linked libraries):

| Contract | Runtime | Margin under 24,576 | Batch 2 |
|---|---|---|---|
| `Panels` | 17,242 | 7,334 | 16,785 |
| `PanelsVerdict` (linked library) | 22,355 | 2,221 | 21,789 |
| `PanelsJudge` (linked library) | 15,253 | 9,323 | 15,080 |
| `PanelsDraw` (linked library) | 9,777 | 14,799 | 9,716 |
| `PanelScores` | 5,869 | 18,707 | 3,797 |
| `Validators` | 22,435 | **2,141** | 22,435 |
| `FeesV3` | 18,026 | 6,550 | 18,026 |
| `RaceV3` (initcode 32,047, with Heads' and SolverBook's) | 22,570 | **2,006** | 23,660 |
| `RaceV3Annex` (initcode 24,528: no longer holds the endings) | 21,731 | **2,845** | 22,730 |
| `RaceV3Endings` (deployed on its own) | 21,814 | 2,762 | 12,831 |
| `SolverBook` (new; created by RaceV3) | 3,707 | 20,869 | – |
| `PoolV3` | 1,927 | 22,649 | 1,927 |

Gas (call frame; `test_gasPerStep`, `PanelsV3Test.test_gas`, `test_gasLiveness`, `SolversV3Test.test_gasSolvers`, `SeatsV3Test.test_gasSeats`):

| Call | Batch 2 | Batch 3 |
|---|---|---|
| `RaceV3.register` | 767,000 | 770,600 |
| `openBounty` | 194,800 | 198,400 |
| `pledge` (the gate read: three active solvers) | – | 225,600 (211,500 with the gate's view mocked) |
| `commit` (the judges' fee, the claim against the cap) | 648,100 | **539,000** (no worst-case quote to compute) |
| `report` (now in the endings: two DELEGATECALLs) | – | 160,400 |
| `signal` (3 drawn) | 143,200 | 146,800 |
| `result` (k = 3) | 569,100 | 569,700 |
| `claim` | 247,100 | 247,300 |
| `merge` (the head, the reputation, the activity list) | 209,400 | **266,800–310,100** |
| `claimInstalments` / `settle` (paid) | 232,500 / 235,400 | 232,600 / 235,500 |
| `finish` (the fee's rest to the pool, the claim closed) | – | 242,700 |
| `challenge` | 533,000 | 535,400 |
| `settleChallenge` (a receipt challenge upheld, k = 5) | 696,500 | **759,600** (the reversal charged to the reputation) |
| `dispute` (stake and cover held) | – | 618,900 |
| `settleChallenge` (a test dispute upheld: reward, reputation, activity) | – | 877,900 |
| `appeal` (no stake: fees, a new submission and claim) | – | 591,500 |
| `close` (a failed appeal's claim closed at finality) | – | 117,900 |
| `RaceV3.release` | 184,900 | 208,500 |
| `Panels.draw` k = 1 / 3 / 5 / 7 | 428,200 / 735,000 / 1,049,100 / 1,351,000 | 438,300 / 749,800 / 1,068,600 / 1,373,200 |
| `drawChallenge` (k = 7, fresh) | 1,429,300 | 1,447,400 |
| `advance` (one silent seat replaced, k = 7) | 657,600 | 663,300 |
| `finalize` (k = 7, the first verdict of seven families) | 466,700 | **857,500** (each family registered once, about 45,000, and re-ranked) |
| `finalize` (k = 7, three Scored families already known) | – | 316,600 |
| `PanelScores.recordCounted` (a Scored family, three known) | – | 79,700 |

What moved and why: a draw reads one more view a member (its family's seat, in place of the barred check) and the cap's switch once (+0.5 to +2 %); `finalize` re-ranks the known families at each counted verdict, and the first verdict of a family registers it; `commit` no longer computes FeesV3's worst-case deposit; `merge` writes the reputation and moves the identity to the head of the activity list; a settled challenge checks whether it reversed a pass to charge the reputation.

Tests: `test/v3/SeatsV3.t.sol` (12: the judge-scores and judge-panels seat and second-draw scenarios by name, the snapshot, the lone verdict, gas), `test/v3/SolversV3.t.sol` (26 + 2: the launch's bounty-market and reputation scenarios, #132's dispute and appeal scenarios, no deposit path, a challenge among one family closed by its second draw, gas; and `SolversGateInvariantTest`: no pledge lands while fewer than three solvers are active, and the book's count equals the identities active within the window), `test/v3/ReplaySolversV3.t.sol` (2: the replay below). The suites written before the gate see three active solvers through a mocked view of the book (`RaceV3Setup._openGate`), and solvers that claim more than $50 at once get reputation first (`_reputation`). `scripts/contracts.sh test`: 666 passed with production windows and 666 with `POF_TEST_WINDOWS=minutes` (604 before batch 3; 646 before the taxi fare added `TaxiV3.t.sol` and the taxi runs of the race invariant and the liveness suite).

**The devnet.** `tests/integration/suite_v3.py` gains step 2b: a pledge refused with no active solver, three solvers' unfunded fixes merged (three active), then a funded fix each for the two solvers whose fixes claim more than $50 (reputation $43.77 each). The devnet deploys Sepolia's fees (`NodeV3Local`: the taxi fare, no attempt, evaluation or appeal fee). `DEVNET_V3_WINDOWS=minutes scripts/time-to-heal.sh` passed: 198 panels, 105.3 h of chain time in 260 s; the wrong k = 1 verdict was reversed after 53.9 h and the bad fix after 100.8 h of chain time (batch 2: 53.1 h and 102.6 h), and the good fix merged 0.4 h after its claim. With the flat $40 the same story ran 305 panels and 199.6 h (reversals after 78.0 h and 195.5 h).

**The replay against the simulation.** `pof/sim/openval/bookreplay.py` runs report v5's R(minus)+F rows in `nodeposit.NDNet` and records what the book must see, in order (every claim and whether the cap let it in, every final pass, reversal, fail and withdrawal with the reputation after it, every activity and the count of active solvers at every issue listed), in micro-coins and seconds, mirrored in integers by the contract's rules (a run whose float cap decision differs is refused). `ReplaySolversV3.t.sol` drives a `SolverBook` with those calls at those times and checks every acceptance, reputation and count: the long con (Opus 5.5 alone, 3 honest solvers, seed 1: 229 claims, 93 passes, 17 reversals) and the sybil of three with free identities under the gate (26 weeks, 1 honest solver, seed 1: 262 claims, 1,566 gate checks, locked then unlocked). On those runs the contract's narrower count (an upheld test counts only for an identity with a merged fix) decided every gate as the simulation did. Seats and disputes aren't replayed: the existing harness scripts Panels' draws, and the simulation ranks families on known answers the chain doesn't have.

**Where the spec was open or the code chose:**
- *The checker image's run* of a dispute's or an appeal's test is off-chain: the panel decides. "A test that passes: the dispute falls with no panel" is, on-chain, a panel rejecting the dispute (the stake to the solver); an appeal with a test that passes on the base code is a panel rejecting the appeal (it costs the appellant that panel's metered checks; there is no appeal stake). A test of no hash is refused before anything moves.
- *The dispute's reward* comes from the pot only when the reversed fix had won the bounty; a later pass that never won is reversed with no reward (no pot owes it, and paying it could take from an award in progress).
- *The fee modes:* the contract tests of batch 3 run the flat $40 (`RaceV3Setup._judgeFee`), and `test/v3/TaxiV3.t.sol`, `RaceV3InvariantTaxiTest` and `PanelLivenessV3TaxiTest` run the taxi fare (Sepolia's): each refund, the judges beyond the deposit paid by the pool, and the attempt, evaluation and appeal fees at 0. Accepted risk (owner, 2026-11-19): spam can block validation on the testnet, bounded by the nodes' spending caps; `reports/faucet-spam-v1.md` simulated a flat fee, not the taxi fare.
- *The appeal window* runs from the counted panel's reveal deadline, the latest the count can come; a fail produced later by a reversal can't be appealed then.
- *Families* are known from their first scored verdict: until three are, the cap is off and challenges get second draws, even if more families have validators; a family whose validators all left counts as seated until its score changes (open problems 7.5).
- *The fee on a time-out and a release* returns to the solver (the network never judged it: L19's "reputation and stake unchanged"); on a withdrawal it doesn't (the spec's scenario).
- *The winner's checks* (S6: refunded from what the pot holds once the award is paid) are kept: the funders' surplus pays them, not the fee.
- *Not built:* sponsorship (D25) and known answers (D26), deferred; D23's re-scoring of judges by final outcomes (an upheld appeal or dispute doesn't change the original judges' scores on-chain); the period's re-measurement of the fee (#132 12.6, later networks).

## #251, contract batch 2: the head at finality, stuck rounds released, capacity (tasks 3.5, 3.13, 3.14)
Batch 2 of the testnet launch (`openspec/changes/proof-of-fix-251-testnet-launch`, design L9, L16, L19; #253's on-chain pause):
- **The head moves at finality (L9, 3.5).** `claim` opens the commitment and starts the award; it no longer moves `Heads` (it records `fix` and `base` on the submission). `RaceV3.merge(b)`, anyone, once, moves the head when the claimed fix's verdict is `Final` and still a pass, from its committed `base`: a stale base reverts whole (`Heads.StaleVerdict`) and the winner keeps its place until `mergeDays` after the finality, when `mergeExpired` closes the award with nothing earned and reopens the bounty. `Award.merged` records the move; instalments still count from finality, but are paid only once merged (Solved = merged); `paid(fix)` is set at the merge. Final verdicts can't be challenged, so the head never names a reversed fix (`invariant_headNeverNamesAReversedFix`). **Batch 1's note, now:** two fixes from one base are both claimed; the first merged moves the head, and the second is refused at its merge, keeping its place until its merge deadline, after which its solver commits the fix rebased on the new head (`test_twoFixesFinalInTheSameWindow`).
- **Stuck rounds are released (L19, 3.13).** `Panels.release(pid)`: a counted or audit panel with a seat its replacements couldn't fill, after its reveal deadline + `STUCK_GRACE`; seats that never sealed are slashed as silence, seats that sealed (they couldn't reveal: the reveal window opens only on a full panel) or revealed are closed unslashed. A counted round sends the submission back to `Waiting` with `retryAt` = now + `RETRY_DELAY`; an audit round makes its audit due again from a fresh audit block. `Panels.releaseAudits(id)`: audits no validator could take for `STUCK_GRACE` (`auditStuckAt`, set when a draw first finds no auditor), counted only in the verdict's window: while a k = 1 verdict is held, its hold keeps it from finality and ends only when the network can judge its challenge, so its audits aren't released then, and the clock restarts when the window starts (otherwise the genesis validator's first verdicts were refunded during the network's first days: the devnet run found it). Any waiting submission is now redrawn (a fresh seed block and snapshot) on a registry change **or** at `retryAt`. The `MAX_REDRAWS`-th released round makes it `Status.Released` (appended to the enum); `Panels.abandon(id)` (race only) does the same at the race's deadline for a parked one (waiting, sealed, or audits undrawn) with a released round. `RaceV3.release(id)` then refunds: outcome `Released` (appended), the deposit's rest back to the solver (no slash, no failed verdict; a counted verdict's judges are paid first by `result`), the bounty (open, or won by this check) `Refunded` to its funders by input, the award closed unmerged, the issue stake back; a registration check's issue is returned. `timeOut` refuses a check with a released round (it ends by `release`). The values are construction parameters in `Windows` (`stuckGrace` 24 h, `retryDelay` 24 h, `maxRedraws` 3, `capWindow` 1 h; minutes in `inMinutes()`, `maxRedraws` unchanged), checked (times nonzero and below 2^32 s, `maxRedraws` 1–255) and readable (`STUCK_GRACE`, `RETRY_DELAY`, `MAX_REDRAWS`, `CAP_WINDOW`).
- **Capacity and the pause (L16, 3.14; #253).** Each validator's `Load` in Panels: its capacity (`CHECKS_DEFAULT` 5 until it sets one, at most `CHECKS_CEILING` 16; 0 pauses it) and the times of its last 16 seats. Every seat (counted, replacement, audit, challenge, shadow) counts; every draw, and the k = 1 hold's count of challengers, skips a validator with its capacity's worth of seats in the trailing `capWindow`, or paused: skipped like a seat it can't take, never slashed. A paused validator is as if absent (a panel steps down without it). A full one is only busy for at most `capWindow`, so **a panel that busy validators leave short waits for them rather than stepping down to a smaller k** (a counted draw waits with `retryAt` = `capWindow` away; an audit or a challenge is retried from the same seed): the minutes devnet run showed a k = 3 check shrinking to k = 1 when two validators were busy, which would trade a short wait for a weaker panel and a week-long k = 1 window. `Panels.setCapacity(key, n)` is the validator's own setting (its key or operator; not an admin power): it takes effect `CAP_DELAY` = 262 blocks later (a seed block's hash lives 256 blocks after `SEED_DELAY`), and no second change is accepted while one is pending, so a validator that sees from a seed block that it's about to be drawn can't pause in time to dodge that draw, nor cancel a pending unpause to do so; a seat already given is judged or slashed as usual. `REPO_CHECKS_PER_HOUR` is a public constant 0 (off) while one repository is served.
- **The split.** RaceV3Annex had 443 bytes left. RaceV3 now has the least (916 bytes): the next race change should move another action out (to the endings, which has 11,745). The endings (`withdrawIssue`, `withdraw`, `timeOut`, `mergeExpired` and the new `release`) moved to **`RaceV3Endings`**, which the annex deploys from its own constructor with the same parameters and reaches through its `fallback` (one more DELEGATECALL, in the race's storage). Deployers and RaceV3 still name one companion: no deployment call site changed. The new Panels code went to `PanelsJudge` (the release paths) and `Panels` (capacity), which had room.

Sizes (runtime bytes, `scripts/contracts.sh sizes` and the artifacts for the linked libraries):

| Contract | Runtime | Margin under 24,576 | Batch 1 |
|---|---|---|---|
| `Panels` | 16,785 | 7,791 | 14,109 |
| `PanelsVerdict` (linked library) | 21,789 | 2,787 | 20,824 |
| `PanelsJudge` (linked library) | 15,080 | 9,496 | 12,291 |
| `PanelsDraw` (linked library) | 9,716 | 14,860 | 9,095 |
| `PanelScores` | 3,797 | 20,779 | 3,797 |
| `Validators` | 22,435 | **2,141** | 22,436 |
| `FeesV3` | 18,026 | 6,550 | 18,026 |
| `RaceV3` | 23,660 | **916** | 23,003 |
| `RaceV3Annex` (initcode 40,832, deploys the endings; EIP-3860 limit 49,152) | 22,730 | 1,846 | 24,133 |
| `RaceV3Endings` (new) | 12,831 | 11,745 | – |
| `PoolV3` | 1,927 | 22,649 | 1,927 |

Gas (call frame; `test_gasPerStep`, `PanelsV3Test.test_gas`, `test_gasLiveness`, `test_gasCapacity`):

| Call | Batch 1 | Batch 2 |
|---|---|---|
| `RaceV3.register` | 766,700 | 767,000 |
| `openBounty` | 192,400 | 194,800 |
| `commit` | 647,600 | 648,100 |
| `signal` (3 drawn) | 140,400 | 143,200 |
| `result` (k = 3) | 565,900 | 569,100 |
| `claim` | 325,300 (moved the head) | **247,100** (opens the commitment only) |
| `merge` (the head moves at finality) | – | **209,400** |
| `claimInstalments` | 228,100 | 232,500 |
| `settle` (paid) | 230,500 | 235,400 |
| `challenge` | 530,000 | 533,000 |
| `settleChallenge` (upheld, k = 5) | 693,200 | 696,500 |
| `Panels.draw` k = 1 (1 eligible) | 381,700 | **428,200** |
| `draw` k = 3 (4 eligible) | 598,000 | **735,000** |
| `draw` k = 5 (6 eligible) | 821,500 | **1,049,100** |
| `draw` k = 7 (40 eligible) | 1,032,900 | **1,351,000** |
| `drawChallenge` (k = 7, fresh) | 1,111,500 | **1,429,300** |
| `advance` (one silent seat replaced, k = 7) | 642,500 | 657,600 |
| `seal` / `reveal` / `receipt` (not the last) | 72,500 / 50,500 / 84,500 | 73,200 / 51,000 / 85,100 |
| `receipt` that counts a panel (k = 1 / k = 7) | 201,600 / 215,500 | 203,300 / 216,300 |
| `finalize` (k = 7) | 466,300 | 466,700 |
| `drawAudits` (the decision) | 44,100 | 44,800 |
| `Panels.release` (k = 3, two sealed seats closed; back to waiting) | – | 103,200–137,400 |
| `Panels.release` (the MAX_REDRAWS-th: `Released`) | – | 93,700 |
| `draw` of a waiting submission at its `retryAt` (re-target) | – | 70,500 |
| `RaceV3.release` (deposit back, bounty refunded, issue returned) | – | 184,900 |
| `Panels.setCapacity` (first change / later change) | – | 47,200 / 34,600 |

What moved and why: **`claim` is 78,100 cheaper** (no `Heads.move`) and **`merge` costs 209,400** (the move, now at finality). **Draws cost more: about +46,500 at k = 1 to +318,000 at k = 7** (`drawChallenge` k = 7: +318,000), because every seat now writes its validator's capacity record (the seat count and one ring slot) and every try that passes the cheap filters reads it. These test draws seat fresh validators, so each first write is a zero-to-nonzero store (about 44,000 a seat, the worst case); once a validator's 16 ring slots are written, a seat costs about 10,000 more than before. `advance` +15,000; seals, reveals, receipts, `result`, `settle` and the rest +0.2 to +1.5 % (a larger `Env` and `Submission`).

Tests: `test/v3/HeadAtFinalityV3.t.sol` (8: the canonical-head contract scenarios by name), `test/v3/LivenessV3.t.sol` (19: the panel-liveness scenarios by name, the deadline, a registration check, a stuck audit, capacity, busy validators and the pause, and the gas), `test/v3/LivenessInvariantV3.t.sol` (L19's invariant over draws, silences, joins, leaves, pauses and time on the real Panels, with a liveness check after every run: once honest validators of every family have room, every submission ends final or refunded), the race invariant's `invariant_headNeverNamesAReversedFix`, and the existing tests moved to `merge`. `scripts/contracts.sh test`: 604 passed with production windows and 604 with `POF_TEST_WINDOWS=minutes` (575 before; the v3 suite is 320 of them).

**Where the spec was open or the code chose:**
- *"The bounty's deadline"* has no v3 field: it is read as the submission's `resultDays` after its commitment, the race's existing time-out for a check never judged.
- *A refund with other fixes queued:* the spec refunds the bounty; the code does so when the bounty is open or this check won it, whatever else is queued (their deposits return by `withdraw`, `result`/`finish`).
- *Judges of a released round* who sealed or revealed aren't paid (the round never counted, so there's no result to pay from), and a revealed vote of a released round is public when the round is redrawn.
- *"Keeps its place until the merge deadline"* (stale base): kept as written, though in v3 the place buys nothing (a rebased fix is a new commitment); the solver waits `mergeDays` after finality to resubmit.
- *Challenge panels that can't complete* aren't covered by L19 (counted panels and audits only): a challenge that never finds a panel still freezes its window.
- *Audits of a held k = 1 verdict:* L19 releases audits that block finality; during the hold they don't, so the release counts only in the window (above).
- *Busy versus paused:* the spec says a full validator is skipped and that with no capacity anywhere the submission waits; it doesn't say what happens when some capacity remains but not enough for the panel the network allows. The code waits (busy) or steps down (paused), as above.
- *Capacity's hour* is `capWindow`, a construction value (a minute in the devnet profile), so the minutes devnet isn't throttled by wall-clock hours.

## #251, contract batch 1: the launch's bindings (tasks 3.1, 3.4, 3.7, 3.8, 3.10)
The testnet launch (`openspec/changes/proof-of-fix-251-testnet-launch`) binds one deployment at construction:
- **One repository (L1):** `RaceV3` takes `repo` (keccak256 of the Radicle RID) and `genesisHead`; its `Heads` holds that one entry; `register` refuses any other id and zero; `FeesV3` keeps one CI profile (`repo`, `profileOf` refuses another). Every claim now moves the head, so a second fix on a stale base can't be claimed.
- **Windows at construction (L4):** a `Windows` struct (`src/v3/Windows.sol`) goes to `Validators` (its genesis) and `Panels`, is checked for order (every window nonzero and below 2^32 s; k = 1 ≥ 3 ≥ 5 ≥ 7 at each level; level C ≥ B ≥ A; k = 1 ≥ `K1_WINDOW_MIN`), and is stored as immutables (Panels packs the twelve challenge windows in two words). `Validators.UNBONDING_DELAY` = the longest challenge window + `UNBONDING_MARGIN` (7 days): 504 h with the production values, which give exactly the old constants. Panels refuses windows other than the registry's (`windowsHash`). The suite runs with production windows and, with `POF_TEST_WINDOWS=minutes`, with every hour a minute.
- **Below the floor (L5):** `State.BelowFloor`, entered and left in `_rebucket` with `WentBelowFloor` / `BackAboveFloor`; it isn't in `activeCount` or the draws; `topUp` brings it back without qualifying; `leave` works from it; its misses still count toward the reveal-rate floor.
- **Sepolia only, TEE only (L2 option 1, L10):** every v3 constructor (Validators, Panels, PanelScores, FeesV3, PoolV3, RaceV3, RaceV3Annex) reverts unless the chain id is 11155111, 31337 or 7193 (`LaunchChain`); `teeOnly` makes `applyAdr` refuse an ADR adding zkTLS; `simulated` stays refused on Sepolia.
- **Known findings (open problems 7.5):** `drawAudits` refuses repeat calls (a draw with no auditor in a snapshot of the registry as it is waits, `auditWaits`, until the registry changes; `recheck` bumps the epoch only when it moves a validator); the on-chain `Receipt` names its seat (Panels, pid, slot, key), and the node finds a receipt naming another seat false.

| Contract | Runtime (bytes) | Margin under 24,576 | Before #251 |
|---|---|---|---|
| `Panels` | 14,109 | 10,467 | 12,662 |
| `PanelsVerdict` (linked library) | 20,824 | 3,752 | 20,156 |
| `PanelsJudge` (linked library) | 12,291 | 12,285 | 12,061 |
| `PanelsDraw` (linked library) | 9,095 | 15,481 | 9,095 |
| `PanelScores` | 3,797 | 20,779 | 3,797 |
| `Validators` | 22,436 | **2,140** | 21,706 |
| `FeesV3` | 18,026 | 6,550 | 17,943 |
| `RaceV3` | 23,003 | 1,573 | 22,895 |
| `RaceV3Annex` | 24,133 | **443** | 24,133 |
| `PoolV3` | 1,927 | 22,649 | 1,927 |

Gas that moved (call frame, the tests below): the `receipt` that counts a panel 174,000 → 201,600 (k = 1) and 187,900 → 215,500 (k = 7), mostly the audit snapshot's registry epoch in a fresh slot; `seal`, `reveal`, a non-final `receipt` and `draw` about +0.2 to +0.7 % (the windows ride in the libraries' `Env`); `claim` 223,000 → 325,300, because every claim now moves the head (it moved nothing in the test race before, which had no repository); `register` 743,100 → 766,700; `result` 552,800 → 565,900.

Tests: `test/v3/LaunchV3.t.sol` (27: the deployment-binding scenarios, Sepolia and the other chains, production and minute windows, windows out of order, a fuzz of ordered windows, `drawAudits`' repeat calls, the validator-admission delta's scenarios and the TEE-only ADR); the receipt's seat in `ValidatorsLevelsV3`; and the recount invariant now also checks that `activeCount` never counts a BelowFloor validator.

**A test-suite pitfall found on the way:** in the large test contracts, `new Panels`, `new RaceV3` and `new RaceV3Annex` are cheatcode deployments (`deployCode`), and a `vm.expectRevert` before one of them ends the test there, passing, without running the rest. The expected reverts now wrap an external call (`this.deployRace`, …), including two older tests in `RaceV3.t.sol` (`test_annexRunsOnlyThroughTheRace`, `test_paramsChecked`) that were silently cut short.

## Sizes
Runtime bytecode, from the build artifacts (`scripts/contracts.sh sizes` doesn't list the linked libraries `PanelsJudge` and `PanelsVerdict`, so `test_everyPanelsContractFitsEip170` checks every one):

| Contract | Runtime (bytes) | Margin under 24,576 | Initcode (bytes) | Before 3.4 (runtime) |
|---|---|---|---|---|
| `Panels` | 12,662 | 11,914 | 13,913 | 12,517 |
| `PanelsVerdict` (linked library) | **20,156** | 4,420 | 20,188 | 19,889 |
| `PanelsJudge` (linked library) | 12,061 | 12,515 | 12,093 | 10,862 |
| `PanelsDraw` (linked library) | 9,095 | 15,481 | 9,125 | 8,724 |
| `PanelScores` | 3,797 | 20,779 | 3,823 | 3,797 |
| `Validators` (3.1, with 3.4's lists, standing, re-attestation and ADRs) | **21,706** | **2,870** | 28,015 | 16,031 |
| `FeesV3` (3.3; 3.5's roll parts and `checkCost`) | 17,943 | 6,633 | 20,455 | 16,058 |
| `RaceV3` (3.5; deploys `Heads`) | **22,895** | 1,681 | **28,097** (EIP-3860: 49,152) | – |
| `RaceV3Annex` (3.5; deployed first) | **24,133** | **443** | 26,747 | – |
| `PoolV3` (3.5) | 1,927 | 22,649 | 2,402 | – |

`Validators` has the smallest margin now (2,870 bytes). If 3.5 needs more of it, the ADR application (`applyAdr` and `_change`) can move to a linked library on the registry's storage, as Panels' rules did.

**The split.** With milestone B, one `Panels` would have been about 31.7 KB. It's split four ways:
- **`Panels`** keeps all the state in one `Store` struct (`PanelsBase.sol`), with the immutables, the race's entry points and the views.
- **Three linked libraries** run the rules on that `Store`. Each gets the storage pointer, so they keep no state of their own and need no wiring:
  - `PanelsJudge`: seals, reveals, receipts and replacement;
  - `PanelsVerdict`: the draws, counting, audits, challenges, shadows and finality;
  - `PanelsDraw`: the sampling and the caps.
- **`PanelScores`** is its own contract. It's deployed first, so FeesV3 can take its address as `IFeesV3Scores`; `Panels` binds it once from its constructor, as it binds the registry. That also breaks the deployment cycle between FeesV3 (which needs the scores) and Panels (which needs FeesV3).

Deployment order: PoolV3 → Validators → PanelScores → FeesV3 → Panels (which binds the registry and the scores) → RaceV3Annex → RaceV3 (which deploys Heads, checks the annex's fingerprint, and binds Panels, FeesV3 and the pool).

## Gas
These are call-frame gas measurements from `test_gas`. They don't include the transaction's 21,000 base or its calldata (about 3,000 to 4,000 more for a signed statement).

| Call | Gas (after 3.4) |
|---|---|
| `seal` | **72,000** |
| `reveal` | **49,900** |
| `receipt` (not the last) | **83,800** |
| `receipt` that completes a panel (counts it, fixes its audit block and snapshot, hold check or window) | 174,000 (k = 1) · 174,300 (k = 3) · 181,600 (k = 5) · 187,900 (k = 7) |
| `draw` | 380,500 (k = 1, 1 eligible) · 596,100 (k = 3, 4) · 819,000 (k = 5, 6) · 1,029,800 (k = 7, 40) |
| `draw`, hidden tests (`openHidden`; k = 7, 40 eligible, another seed) | 1,200,400 |
| `advance`, one silent seat replaced (k = 7) | 640,500 |
| `advance`, a reveal missed after the majority revealed (k = 7, 3 seats emptied, counted) | 649,000 |
| `drawAudits` (the decision, no auditor due) | 41,300 |
| `challenge` (opened by the race: snapshot, frozen window, 7 × `challengeOpened`) | 198,200 |
| `drawChallenge` (a fresh panel of 7) | 1,108,500 |
| `finalize` (k = 7: `verdictFinal` and the family score for each judge) | 465,100 |
| `finalize`, an ADR (with `adrPassed` and the deposit's refund) | 552,900 |
| `Validators.applyAdr` (one operation: a raised minimum) | 53,400 |
| `Validators.applyAdr` (a TEE type removed: its group leaves the counters) | 110,400 |
| `Validators.recheck` (per validator moved out of the counters) | 40,700 |
| `Validators.reattest` | 180,800 |

What 3.4 costs the existing calls: the draw reads a validator's standing (its proof type, TEE type and image listings, one slot each) only for a roster entry that passed the cheap filters, about +1 % on a draw; a challenge draw rose 4.5 % (1,060,800 to 1,108,500), mostly from the larger `Validator` record each new key decodes.

- **One judge's on-chain part of a check** (its seal, reveal and receipt) costs about **205,500 gas**, plus about 3 × 24,000 for the transactions and calldata.
- **A k = 7 verdict costs about 2.8M gas from draw to finality.**
- **The draw is bounded.** Each k it tries gets DRAW_TRIES × k tries, times the roster's slack (at most ×4). Each try is one `rosterEntry` read, plus a `validator` read for each new key.
- **What milestone B added to the draw** (about 50,000 to 120,000 gas over milestone A, depending on k):
  - the snapshot;
  - the shadow draw;
  - the linked-library calls.

## The draw's snapshot: changes after the seed can't re-roll it
**The problem (milestone A, choice 8).** A draw read the registry live:
- k came from `eligibleCount`;
- index i mapped to a validator through `eligibleAt`, whose order changes with every swap-and-pop.

Whoever called `draw` could see the seed block's hash first. They could then leave, top up across a tier, qualify a candidate, finalize a k = 1 verdict, or roll FeesV3's prices, all in the same block, to re-roll the panel.

**The fix.** The draw reads only what was fixed before the seed was known:
- **Validators keeps an append-only roster per bond tier:** every key that ever became drawable for the tier, in order, never removed. It also keeps the block each key last rose to a higher bucket (`rosterEntry(t, i)` returns the key, that block and its bucket now).
- **When a seed block is set, Panels records a `Snap`.** That happens at `open`, at each re-target, at a verdict's count (for its audits) and at a challenge. The `Snap` holds:
  - the block;
  - the bounty tier's live count, which gives k;
  - the roster's length;
  - FeesV3's epoch.
- **The draw reads the snapshot, not the live registry.** It samples roster indices below the snapshot's length. An entry counts only if all of these hold:
  - it was drawable for the tier at the snapshot's block and still is: it rose at or before that block, and its bucket now covers the tier;
  - its family was priced by the snapshot's epoch;
  - its family isn't barred, and didn't recover after the snapshot;
  - (a counted k = 1 seat) it wasn't freed from K1_PENDING_MAX after the snapshot.
- **So a change after the snapshot can only remove a validator from a draw, as its silence would.** It can't add one or move the others.
- **The tries scale with the roster's slack** (its length over the live count at the snapshot, at most ×4), so keys that left don't eat the tries.

**The tests:**
- `test_aDrawIgnoresRegistryChangesAfterItsSnapshot`: after the seed's hash is known, the attacker leaves with one validator, tops another up across a tier ($700 to $1,300), tops a $100 validator up into the bounty's tier, and qualifies a newcomer. The live set changed, and the drawn panel is exactly the panel `sample` gave before the moves.
- `test_aLeaverOnlyRemovesItself`: a drawn validator that leaves in the draw's block only loses its own seat.
- `test_anAuditDrawIgnoresChangesAfterItsSnapshot`: the same for an audit draw.
- `test_theRostersCoverTheDrawableValidators`: the rosters agree with the tier counters.

**What it costs:**
- one 32-byte `Snap` per submission, audit round and challenge (about 22,000 gas);
- in Validators, one roster push per (key, tier) the first time a key reaches a tier, and one stamp per bucket raise.

**What remains** (residuals, none of which adds a chosen validator):
- **Free self-removal.** A validator that tops up removes itself from in-flight draws for free. That's the same as silence without the $5, and it doesn't choose who replaces it.
- **Rosters don't shrink.** They keep departed keys. The slack multiplier (at most ×4) absorbs up to 75 % departed keys; beyond that, draws step k down more often. A later version could rebuild a roster as a new generation.
- **A stalled panel's `refill` re-snapshots at the call,** since the registry must have grown for it to succeed. So the caller times which newcomers exist, but only after the whole sample was exhausted.
- **Shadow draws read the candidate list live.** Who shadows is low stakes: no counted vote, no pay beyond usage.
- **The k = 1 hold's challenger check** (`startWindow`) reads live. It's exact up to 32 eligible validators, so it can only start a window when three challengers really exist.
- **Parties are read at the draw.** RaceV3 (3.5) must keep a submission's parties fixed from its opening (a pledge made after the seal mustn't recuse anyone in that draw).
- **The block proposer's influence on its own block hash** stays as D3 records.

## Reveal-phase replacement: decided (owner, 2026-11-13, option 2)
**Built:** on a counted panel, when the verdicts revealed with receipts already decide ((k + 1) / 2 on one side; at the constitution tier 5 passes or 3 fails), a seat that sealed but missed its reveal is slashed ($5) and counts a miss, but isn't replaced: the verdict counts with the revealed votes, and the seat stays empty. With no majority yet, it's replaced as before. Two refinements, both the smallest reading:
- **the level still has to cover the bounty:** if the revealed judges' level (the majority's weakest, of k) can't judge the bounty, the seat is replaced (or waits), so a verdict never counts at a level its draw would have voided;
- **only counted panels:** challenge and audit panels always replace. A challenge panel's majority also decides each original receipt (its mask), which a missing vote could still change.

A level C pass counted with an empty seat is treated as split (its passes are fewer than k), so it's always audited. `judges(pid)` returns 0 for an empty seat; RaceV3 (3.5) must skip it when it pays the counted judges. Tests: `PanelsLevelsV3.t.sol`, from `test_aMissedRevealAfterAMajorityRevealed` on.

The options as they were put to the owner (#227):
- **A seat that misses its seal** is replaced, and the whole round's windows restart. Nobody has revealed yet, because reveals open only once every seat has sealed.
- **A seat that sealed but misses its reveal or receipt** is slashed ($5) and replaced, with fresh windows. The replacement seals after the others' reveals are public, so it can copy them.

| Option | What happens at a missed reveal | For | Against |
|---|---|---|---|
| **1. As built:** replace, fresh windows | a new judge seals and reveals after the others' reveals are public | simple; k and the majority never change; liveness | the replacement can copy (or herd toward) the revealed votes; its vote is less independent, and its score agreement comes cheap |
| **2. Stop at a majority** | if the revealed votes already hold (k + 1) / 2 on one side, the missing seat is slashed and not replaced; the verdict counts with fewer reveals. Otherwise replace as in 1 | removes the copying where it can't change the outcome; saves a check | the verdict carries fewer independent votes (audits and scores see k − 1); a withholder's bribe-ability is unchanged; with no majority yet, the copy problem remains |
| **3. Restart the round** | the missing seat is replaced and every seat re-seals and re-reveals; the reveals already posted are void | every vote sealed before any is revealed, as far as the chain can enforce | a published reveal can't be unseen, and fresh checks with new receipts double the cost; one withholder can force repeated restarts at $5 each |
| **4. A missing reveal counts against** | nothing is replaced; the seat is slashed and counted as a fail (or an abstention) | no copying, no restarts, no delay | changes what k means; a bribed withholder can now tilt a verdict, which D16 assumes silence can't |

The spec read as 1 until the owner chose 2; judge-panels now has it as its own requirement, "A reveal missed after the majority revealed isn't replaced", and design D16 records why.

## Task 3.4: proof levels and the constitution's lists
**The lists (D10, D11).** `Validators` keeps four: proof types, TEE types (each with its firmware minimum), checker image digests and zkTLS notaries. The genesis lists them (no zkTLS, no notary). After that, only an ADR changes them:
- Panels reports an ADR passed and final (`adrPassed`, from `finalize`, with its commitment and whether it was opened as a removal). Finality already waits ADR_WINDOW (14 days) for an `Adr` and REMOVAL_WINDOW (48 hours) for a `Removal`, so an addition can't take effect before the full window.
- Anyone then applies it, once (`applyAdr(id, text, changes)`). The operations must hash to its commitment (`adrCommitment`: the ADR's text hash and its operations), and a removal's must all be removals (`isRemoval`: remove a TEE type, image, notary or proof type, or raise a minimum). All or nothing.
- **Never:** the last TEE type or image (it can be applied later, once a replacement is added); PROOF_TEE (every TEE type at once); zkTLS listed with no notary; a proof type without a verifier path in this code (only zkTLS, and `simulated` on chain 31337 or 7193).

**Standing.** A validator is in standing while its proof type, TEE type and image are listed and its attested firmware is at least its type's minimum. One out of standing isn't drawn (counted, shadow, auditor, challenger, or counted toward a k = 1 hold) and keeps its bond and state.
- A removed TEE type (or zkTLS) leaves the tier counters at once, by its bucket group (O(tiers)); listed again, it comes back.
- A raised minimum, a removed image or a removed `simulated` touch some validators of a group. The draw skips them at once (`rosterEntry` returns bucket 0 out of standing). They leave the counters when anyone calls `recheck` (k is computed from the counters, so until then the draw may step k down).
- **Coming back:** after a raised minimum or a new image, the key re-attests (`reattest`: a new attestation hash, image and firmware, signed by the key over a nonce). It returns without qualifying again: state, bond, family, level and qualification progress are unchanged. After a removed TEE or proof type, it registers a new key and qualifies.
- **Snapshots:** a validator brought back (re-attested, or its type, image or proof type listed again, or its minimum lowered) counts as risen at that block, so a draw whose snapshot is older still can't add it.

**Registrations** record the attested firmware level (`Registration.firmware`, now in the signed registration) and are refused below the type's minimum.

**Notaries.** `notaryCounts(notary, revealedAt)`: a zkTLS proof counts if its notary was listed when the verdict was revealed, so verdicts revealed before a removal took effect still count (only the latest listing interval is kept).

**Receipts** name their proof (`Validators.receiptHash`): the proof type, notary, model, weights, image, seed, prompt, answer, tests and proof hashes, so a proof type switched on later needs no new receipt format.

**All-TEE panels.** `Panels.openHidden` opens a submission with hidden tests or to a private repository. Every seat drawn for it is at level A or B: counted, replacement, shadow, auditor, challenger, and the k = 1 hold's challengers. On a network of level C validators only, it waits.

**The (k, level) table** is ADR 0004's (`limitOf`, `windowOf`), tested value by value, with a level B panel of 5 judged at its own limit and window.

**`simulated` (D18)** still counts as level A on a devnet; a deployment on any other chain id refuses it, and so does an ADR (both fuzzed over chain ids).

**Interface changes:**
- `IValidators`: `Registration.firmware` (in the signed typehash), `Validator.firmware` and `Validator.reattestations`; `Op`, `Change` and `Receipt`; the hook `adrPassed`. `isDrawable` and `canShadow` now also require standing.
- `Validators`: `reattest`, `recheck`, `applyAdr`; views `inStanding`, `acceptedNotary`, `minFirmware`, `notaryCounts`, `adr`, `adrCommitment`, `isRemoval`, `receiptHash`, `reattestationDigest`, `teeTypeCount`, `imageCount`, `notaryCount`. `acceptedProofType`, `acceptedTeeType` and `allowedImage` are functions now (same ABI). `Genesis.firmware` (empty: every minimum 0).
- `IPanelsRegistry`: `teeTypeCount`. `Panels`: `openHidden`; `Submission.teeOnly`; its constructor's `teeTypes_` must be exactly the registry's list. `teeCapFrom` reads the registry's count, so it follows additions as well as removals.

**What 3.4 leaves to 3.5 (RaceV3):** checking `isRemoval` before opening a `Removal` ADR (the registry refuses to apply a removal that adds anything, but the panel would already have judged it), and opening hidden-test bounties with `openHidden`.

## What milestone B builds
- **Shadows (D5):**
  - Every draw also seats SHADOW_PER_DRAW shadows (2 while fewer than K_MAX are active), and a waiting submission gets SHADOW_PER_WAITING. They're candidates not cooling off, or validators of a barred family, and their family must be priced.
  - They seal in the counted panel's seal window and reveal after it. They're never replaced or slashed for silence.
  - `settleShadows` records each reveal or miss (`recordShadow`), then scores each revealed shadow once:
    - against the final outcome, when no lone validator set it;
    - against the majority of the sealed verdicts (counted and shadow, at least 3 revealed), for a k = 1 verdict held at its count and for a waiting or withdrawn submission.
  - Scoring feeds `scoreShadow` (qualification) and, for barred families, `PanelScores.recordShadow` (recovery). Finality settles the shadows of its panel.
- **Audits (D13):**
  - At a count, an audit block and snapshot are fixed. From that block (so the judges can't know when they vote), `drawAudits` decides the random AUDIT_RATE share.
  - Every k = 1 verdict gets K1_AUDITS (2), and every split level C pass one.
  - Each auditor is a one-seat panel outside the original panel and its earlier auditors, drawn as soon as one is eligible (otherwise the audit block re-targets).
  - An audit that disagrees opens a challenge with no stake. Finality waits for the decision and every audit.
- **Challenges (D4):**
  - The race files them, since it holds the stakes. Each gets its own seed block and snapshot.
  - The challenge panel is CHALLENGE_K[k], or the largest odd number above k the network allows (K_MAX for K_MAX). It's drawn without the original judges, auditors or parties. Until one can be drawn, it waits (re-targeting after a registry change), and the window is frozen.
  - Each challenge judge's reveal carries a mask of false receipts. A receipt its majority finds false is `slashFault(FalseVerdict, challenger)`.
  - The panel's majority decides the fix (quorum 5 at the constitution tier). The window resumes where it froze. One challenge is open at a time.
- **Scores (D14, `PanelScores`):**
  - The last 200 counted verdicts per family, kept as a 2-bit ring and balanced over passed and failed outcomes.
  - States: Neutral, Scored, Barred (below 70 % over 50 or more), and Recovering (a fresh block of 100 shadow verdicts at 80 %; the window restarts; the minimum factor until 50 new counted verdicts).
  - Fed at finality against the final outcome (after any reversal). FeesV3 reads `familyScore`, and the draw skips barred families.
- **The constitution tier (D7):**
  - `openConstitution` takes Adr, Removal or Escalated, with ADR_DEPOSIT pulled from the race.
  - Exactly K_MAX are drawn under the caps, passing with 5. It needs 21 eligible (14 for Removal) at the opening and in its snapshot, or it expires unjudged and refunded.
  - The window is 14 days for an ADR, 48 hours for a removal, whatever the level; an escalated fix gets its (7, level) window.
  - At finality the deposit is refunded on a pass and goes to the sponsors' pool on a rejection.

## Tests: 495 contract tests, all passing
- `test/v3/ValidatorsLevelsV3.t.sol` (3.4, 23 tests): the firmware minimums at the genesis and at registration; "A flaw is patched" (and re-attestation without qualifying again, for an active validator and a candidate); a re-attestation's signature and nonce; "An exploit is published for a TEE type"; a type listed again; "Removing the last accepted type" (and the last image, and PROOF_TEE); "A new TEE type proposed"; an ADR that removes and adds; a removed image and the next release; only a passed ADR applies, once, as bound; "Switching zkTLS on"; "A verifier that isn't in the code" by ADR; "A notary that isn't listed" and "A notary removed while verdicts are in flight"; zkTLS switched off and on again; `simulated` refused off a devnet by deployment and by ADR (fuzzed over chain ids) and listed on one; the receipt format; and a fuzz test that the tier counters follow the lists.
- `test/v3/PanelsLevelsV3.t.sol` (3.4 through Panels, 19 tests): an adding ADR takes effect only after the full window; a removal after REMOVAL_WINDOW; "A type is removed" by ADR; a removal carrying an addition, a rejected ADR and an escalated fix never change a list; "A flaw is patched" in the draw, with an in-flight snapshot; hidden tests go only to level A or B judges, wait on a network of PCs, and hold a lone verdict for TEE challengers; the (k, level) table and a level B panel of 5; option 2 (a missed reveal after a majority, with no majority yet, at the constitution tier, one that would weaken the panel, on a challenge panel, and a level C pass with a missed reveal); and the gas above.
- Two milestone A tests, "A verdict with no receipt" and "A sealed vote not revealed", now split their revealed votes, so they still test replacement.
- `test/v3/PanelsV3.t.sol` (milestone A, 39 tests):
  - the draw scenarios, seals, reveals and replacement, finality and the hold, the caps;
  - the fuzz test that k is odd, at most K_MAX, and fixed through replacements;
  - the view matching the recorded draw;
  - early, mismatched and replayed reveals, and missed deadlines;
  - gas, and the ABI's lack of a setter.
- `test/v3/PanelsV3B.t.sol` (milestone B, 44 tests):
  - **judge-panels:** a zkTLS validator lies about the tests; a verdict through a gateway; a model of another family; a lone validator passes a bad fix; a challenge with too few validators; a lone judge's false receipt on a bad fix; a false receipt on a fix the panel passes; nobody is watching; an audit agrees; validators qualify after the genesis; one auditor misses a bad fix; a split level C pass.
  - **The constitution scenarios:** an ADR on a grown network; an adding ADR on a small network, and an ADR that expires; a removal on a small network; an ADR that removes and adds; the network reaches the threshold; a rejected ADR; a rejected escalated fix; an ADR that takes effect; an ADR passed by a mostly level C panel.
  - **judge-scores:** a judge that always votes pass; only one kind of outcome; a reversal counts as the truth; recomputing a score; shadow verdicts don't lift a score; a weak model; a model that gets better; a weak model's lucky streak; a newly released open model; a better model earns more (with the real scores; "Scores don't raise the price of a check" is FeesV3's, `test_scoresDontRaiseThePriceOfACheck`); a high-score family in the minority.
  - **validator-admission shadows:** a candidate copies the counted judges; a submission waits for a panel; a colluding genesis validator, and a held verdict becomes final; challengers already eligible; a waiting submission; a silent shadow.
  - **The snapshot, and the EIP-170 guard:** the tests in the section above, and `test_everyPanelsContractFitsEip170`.
- The Validators suites (3.1) still pass, with `familyOf`, `rosterLength` and `rosterEntry` added to their ABI list.

## Task 3.5: RaceV3
`RaceV3` is v2's race (bounties, attempts, sealed commitments, the rising price locked by the first attempt, the earliest passing commitment wins, the claim, instalments, the clawback, Heads), judged by `Panels` in place of v2's `Verdicts` and charged by `FeesV3`. Like v2's race it has no owner and no setter: Panels, FeesV3 and the sponsors' pool are bound once, from its constructor.

**Every check is a Panels submission under the same id:**
- that's a fix's submission, or an issue's registration check (judged at 1 micro-coin, the lowest tier);
- each posts `FeesV3.maxDeposit(repo, K_MAX)` as its deposit, since k is fixed only at the draw;
- `FeesV3.open` fixes its prices;
- Panels opens it, with `openHidden` for an issue registered as hidden (hidden tests or a private repository: level A or B judges only).

**The bounty a panel judges is the price on offer at the commitment.** An award never pays more than that. A pledge made after the commitment can't raise what's at stake above what the panel was sized for; the rest returns to the funders by refund.

**Parties are fixed when a check opens** (`isParty`):
- the issue's reporter, the solver, and the funders who had pledged by then;
- each funder's place is its first pledge's order, `pledgeOrder`;
- a later pledge recuses nobody in that check, and a refund frees nobody.

**Pay:**
- **Reports:** each judge of any panel signs its usage as a registry statement on its seat, bound to its on-chain receipt (`report`).
- **Counted judges:** `result`, posted by anyone once Panels has counted the verdict and every seat has reported (or a day after the reveal deadline), pays each counted judge through `FeesV3.settle` from the deposit. That's the median of the reports (k = 1 is its own median), plus the service fee scaled by the family's score. It also repays the relayer's gas and tells FeesV3 who was seated. Empty seats (3.4's option 2) are skipped.
- **Audits and an auditor's challenge panel:** `payPanel` pays `FeesV3.checkCost` (the unscaled fee) from the deposit's rest, and from the pool beyond it.
- **Shadows:** `payShadow` pays `FeesV3.shadowCost` from the pool, one capped report per seat. So a draw's shadows cost at most their seats' quoted usage, and a family priced after the check opened is paid nothing.
- **The deposit's rest** returns a day after finality (`finish`).

**The verdict and finality:**
- The counted verdict decides the queue at once.
- The winner's `claim` opens the commitment, `keccak256(abi.encode(fix, base, salt, solver))`. In a repository of the head registry, the head moves only if `base` is still the head. A fix already paid is a duplicate: it costs the evaluation fee and reopens the bounty.
- Instalments count from the verdict's `finalAt` in Panels, and only once Panels' status is Final with a pass. A held k = 1 verdict or a frozen window pays nothing.
- A pass reversed before finality claws back the award and reopens the bounty (`sync`, also run by `settleChallenge` and `payPanel`).
- A fail reversed to a pass wins if the bounty is still open, in its commitment's turn.

**Challenges** (`challenge`, `settleChallenge`):
- The challenger posts `challengeStake` plus the panel's worst-case cost (`FeesV3.depositFor(id, repo, K_MAX)`), and the race holds both.
- **Upheld:** both return, and the panel is paid from the solver's deposit (and the pool).
- **Rejected:** the panel is paid from the cover, the rest of it returns, and the stake goes to the challenged panel's judges in equal shares.
- The outcome is recomputed from the challenge panel's own seats, so a later auditor's challenge can't change it: its majority against the verdict at the filing, or a receipt flagged by more than half its seats.

**FeesV3's queue signals** come from Panels' status, through `signal(id)` (anyone):
- a waiting submission counts once as waited;
- a counted panel with an empty seat counts once as stalled;
- the seated validators count as drawn.

`result` also reports the counted judges as drawn.

**Size:**
- RaceV3 runs its rarely called actions in `RaceV3Annex` by DELEGATECALL, as v2 did.
- The annex is deployed first, and RaceV3 checks its fingerprint (the same Panels, pool, start and caps). Deploying it from RaceV3's constructor would make RaceV3's initcode about 61 KB, over EIP-3860.
- Both read only the few words they need of Panels' and the registry's records. `test_theRaceReadsPanelsRecordsRight` checks each offset against the typed views; it caught 3.4's `teeOnly`.
- `PoolV3` is v2's `Pool` plus one bound spender (the race), which pays only what the race computes from FeesV3.

### FeesV3.roll in bounded parts
`rollPart` closes the oldest ended period in parts:
1. counting the tables;
2. the shared units;
3. the priced families;
4. the new families;
5. the close.

Each part reads at most about `ROLL_WORK` (100) posted entries. `roll()` keeps its meaning, one period a call, by running parts while more than `ROLL_PART_GAS` (1M) gas is left. Every FeesV3 test passes unchanged. While a roll is under way, `post` and `announce` revert (`RollInProgress`), so every part reads the same tables. Quotes don't move until the close.

At #222's size (36 posters × 16 families, two periods), `test_rollPartsAreBounded` measures:

| Part | Gas |
|---|---|
| counting, 8 posters (12 priced families) | 568,000 to 592,000 |
| counting, 6 posters (16 priced families) | 396,000 to 411,000 |
| the shared units | 316,000 to 514,000 |
| two families | 643,000 to **857,000** |
| one new family priced | 750,000 to 797,000 |
| the close | 75,000 to 124,000 |

- **The largest part is 857,000 gas, under the stated bound of 1M.** The one-call roll took 5.3M.
- A period takes about 17 parts at this size.
- The parts give exactly the prices of a one-call roll on a twin meter.
- The bound holds while a family's tables fit one part: a part always takes at least one family, so with far more than 100 posting validators a part grows by about 4,200 gas per poster.

### Gas per step
Call-frame gas from `test_gasPerStep` (a network of 4, k = 3, the real Panels, FeesV3 and pool), plus `payPanel` and `payShadow` from their tests. It excludes the transaction's 21,000 and its calldata.

| Call | Gas |
|---|---|
| `register` (fee, stake, the check's deposit, `FeesV3.open`, `Panels.open`) | 743,100 |
| `openBounty` | 192,100 |
| `pledge` (a first funder) | 206,300 |
| `attempt` | 175,200 |
| `commit` (the deposit, `FeesV3.open`, `Panels.open`) | 652,100 |
| `signal` (3 drawn) | 140,000 |
| `report` (one judge's signed usage) | 152,700 |
| `result` (k = 3: `FeesV3.settle`, 3 judges and the relayer paid, the queue) | 552,800 |
| `claim` (the merge) | 223,000 |
| `payPanel` (an audit) | 251,300 |
| `payShadow` | 239,100 |
| `claimInstalments` | 227,800 |
| `settle` (paid: instalments, finder's fee, registration and checks refunded) | 230,100 |
| `finish` (the deposit's rest) | 92,100 |
| `claimRefund` | 154,700 |
| `challenge` (stake and cover held, `Panels.challenge`) | 533,500 |
| `settleChallenge` (upheld: a panel of 5 paid, the award clawed back) | 696,900 |

- Most of `register` and `commit` is FeesV3's deposit quote over every priced family, and Panels' snapshot.
- A k = 3 check's race-side cost from commitment to its judges' pay is about 1.66M gas: commit, 3 reports and the result.

### The replay: group 7's market to the micro-credit
**The exporter.** `pof.sim.openval.contract` runs group 7's market (round 2's rules, `params.V2R2`; `pricing.Baseline`) in FeesV3's integers:
- posted tables are rounded to integers;
- prices step by FeesV3's `stepPrice` and the fee by its `stepFee`, with their floor rounding;
- each judge's pay is `FeesV3.settle`'s, for identical reports.

The sim's own entry and exit decisions read those integers, so the run is the simulation in the contracts' units, not a recomputation beside it. `pricing.Market.end_period` now calls `step_prices` and `step_fee`, so the contract market overrides only those. Every existing pricing test is unchanged.

**The replay.** `contracts/test/v3/ReplayV3.t.sol` replays the exported calls on the real RaceV3, FeesV3 and pool:
- commits;
- first waits and stalls, through `signal`;
- every paid panel: counted, through `report` and `result`; audits and auditors' challenge panels, through `payPanel`;
- each period's seated validators, through `signal`;
- each close: the active validators post their tables, then the roll.

It checks, exactly:
- every judge's pay;
- every counted charge from a deposit;
- after every roll, the service fee and all 15 unit prices;
- the books.

| Seed | Weeks | Submissions | Counted panels | Audits | Auditors' challenge panels | Waits, stalls | Judge pays | Closes | Fee (min, max, last) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 4 | 127 | 124 | 14 | 0 | 2, 1 | 882 | 28 | $0.1347, $0.25, $0.1486 |
| 2 | 8 | 199 | 188 | 16 | 2 | 11, 0 | 1,346 | 56 | $0.1397, $0.25, $0.1397 |
| 3 | 8 | 254 | 250 | 19 | 2 | 4, 0 | 1,783 | 56 | $0.1418, $0.25, $0.1642 |
| 4 | 8 | 242 | 238 | 30 | 2 | 10, 0 | 1,566 | 56 | $0.1824, $0.25, $0.1996 |

All four match to the micro-credit: 822 submissions, 5,577 judge pays and 196 rolls. The fee rises and falls in every 8-week run. A pay or a fee changed by one micro-credit in a copy of the file fails the replay (checked by hand). `tests/test_openval_contract.py` checks that the files are what the exporter writes on their seeds, that the integer rules are FeesV3's, and that the refused runs below are refused.

**Where an exact match isn't possible, and why** (the exporter refuses these runs by name rather than loosening the replay):
1. **Panels' draws are scripted.** The simulation draws its panels from its own seeds, and the contract draws from block hashes the simulation can't know. So the replay's `ReplayPanels` seats exactly the judges the simulation paid. RaceV3 and FeesV3 run as deployed. The real draw is covered by Panels' own tests.
2. **A counted judge that leaves before its period closes.** FeesV3 counts every validator seated in a period as drawn (capped at the active count). The simulation counts only those still active at the close. The two idle shares then differ, so the exporter refuses such a run ("not active at its close"); seeds 1 and 5 at 8 weeks hit it. It's a difference between FeesV3's rule and the simulation's, not a rounding. Making `drawn` count only validators still active at the roll would need a pass over the period's seated validators at the close, or a decrement when one leaves (a registry hook into FeesV3).
3. **Waits in the first period.** Each replayed submission gets its own bounty, so no pass ends a queue. Their registration checks open in the first period, adding to its submissions, which could only change a wait share. The exporter refuses a run with a wait in the first period (seed 5).
4. **Not replayed:** the bounties' money. The group 7 simulation doesn't model the race's pots, prices and instalments; v2's race replay (`ReplayV2`) does, on v2. The award path is covered by RaceV3's tests and invariants.
5. **Gas:** the simulation's gas unit is a judge's cost there. On-chain it's the relayer's, at the transaction's gas price (0 in the replay), so the contract market keeps it out of the judges' pay.

Audits differ in who pays, not in how much. The simulation books an audit's pay as a network cost; RaceV3 takes it from the solver's deposit, and from the pool beyond it. The replay compares what each auditor receives.

### Tests
- `test/v3/RaceV3.t.sol` (45 tests). v2's race suite (RaceV2.t.sol) is ported where v3 keeps the rule:
  - registration and the check;
  - the price, its lock and top-ups;
  - commitment order;
  - the deposit paying the checks and returning;
  - late submissions;
  - the claim, duplicates and paid fixes;
  - expired merges;
  - instalments then refunds;
  - the sunset and the idle clock;
  - appeals;
  - Heads;
  - no privileged call;
  - the annex only through the race;
  - the parameters.

  The tests new in v3:
  - parties fixed at the opening, and a funder recused (k stepping down to 1);
  - the held verdict paying nothing until final;
  - the award capped at the judged bounty;
  - reports signed and bound to receipts;
  - results waiting for reports;
  - the clawback, a fail reversed to a win, and a rejected challenge paying the accused;
  - challenge rules;
  - audits from the deposit;
  - shadows from the pool;
  - FeesV3's signals;
  - withdrawals and time-outs;
  - a hidden issue's checks;
  - the record offsets, sizes and gas.

  Not ported, since nothing is signed by a quorum any more:
  - v2's signature, replay and malleability tests;
  - the signed fee list;
  - the signed weights and inflation rule;
  - `appealDuplicate`.
- `test/v3/RaceV3Invariant.t.sol`, in RaceV2Invariant's style:
  - random races over 17 actions, with scripted Panels verdicts at any k, reversals, audits, finality and periods rolling, at a depth of 200;
  - the invariants: exact books; payouts never stuck; deposits accounted, and none overcharged; pots cover awards, and no award above its judged bounty; settled pots drain; winners passed;
  - a scripted run that reaches each guarded path.
- `test/v3/ReplayV3.t.sol` (4 seeds), above.
- `test/v3/FeesV3.t.sol`: `test_rollPartsAreBounded`.
- The whole suite: 547 contract tests and 1,420 Python tests pass (`scripts/contracts.sh test`, `scripts/check.sh`).

### Choices made where the spec was open
1. **One coin.** Pledges are in the version's fee coin only. Panels' bounty limits are in it, and nothing converts another coin. Because the pot can't exceed `BOUNTY_MAX`, the race refuses a `bountyCap` above $625.
2. **The registration check is a Panels judgment.** A final pass opens the bounty and a final fail forfeits the stake (v2's `junk`). v2's quorum-signed `refuseSimilar` and its importance weights (and so the inflation rule on the finder's fee) have no keyless counterpart and are gone. `appealDuplicate` is gone too: a duplicate is now an on-chain fact found at the claim.
3. **The commitment covers the base:** `keccak256(abi.encode(fix, base, salt, solver))`, so the claim proves which base the panel judged. A stale base reverts the claim, and the winner has until `mergeDays` (no rebase verdict yet).
4. **Decisions at the count, payment from finality.** The queue moves at the counted verdict. A reversal before finality claws back. Panels allows no challenge after finality, so a clawback always finds nothing earned.
5. **Who pays audits and challenge panels:** the check's deposit (`K_MAX` judges' worst case), then the pool. A rejected race-filed challenge's panel is paid from its own cover.
6. **Its stake goes to the challenged panel's judges** (judge-panels: "a failed one SHALL pay the stake to the accused").
7. **`timeOut`** (no panel seated within `resultDays`) refunds the whole deposit and charges no evaluation fee: the wait is the network's.
8. **Reports and results:** a result waits for every seat's report, or a day after the reveal deadline (`REPORT_WINDOW`). A judge that doesn't report isn't paid, as in v2.
9. **`signal` is a keeper's call.** A silent judge replaced before anyone signals isn't counted as drawn.
10. **Not opened by RaceV3 yet:** escalated fixes and ADRs (Panels' constitution tier).

## Left for groups 4 and 5
- **The node (4.1):**
  - report each seat's usage to RaceV3 (`report`, the `USAGE_TAG` statement) beside its receipt;
  - call `signal` after each draw and replacement, and `result`, `payPanel`, `payShadow`, `finish` and `rollPart` as a keeper;
  - commit fixes as `keccak256(abi.encode(fix, base, salt, solver))` and claim them;
  - post to RaceV3's `challenge` with evidence.
- **The race, still open:**
  - a rebased winner (a fresh check of the rebased fix keeping its place);
  - escalated fixes and ADRs through RaceV3, with ADR_DEPOSIT, and `Validators.isRemoval` before a `Removal`;
  - the sponsors' pool's system bounties (5.11's rules).
- **FeesV3 against the simulation:** whether `drawn` should count only validators still active at the roll (item 2 above), for the ADR or a later version.
- **Deployment (group 5):**
  - the deployment script deploys PoolV3, then the registry with it as the pool, …, RaceV3Annex, then RaceV3 with the same nonzero `start`;
  - `scripts/integration.sh --version 3` drives the race through the panel interface (5.0).
- **Sizes:**
  - `RaceV3Annex` has 443 bytes of margin and `RaceV3` 1,573 (after #251's batch 1). The next race feature needs a second annex, or the Baskets externals moved off the annex.
  - `Validators` has 2,140 bytes of margin after #251's batch 1 (BelowFloor, the windows' derived delay, `teeOnly`).
