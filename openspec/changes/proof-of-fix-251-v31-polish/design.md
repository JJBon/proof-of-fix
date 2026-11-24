# Design

## Context

- **Why:** see proposal.md. The behaviour is in the deltas to `checking`, `challenges` and `bounty-market`. This
  document covers how, the parameters and their values, the sizes, how it ships with #310 and #311, and what reaches
  live v3 before v3.1.
- **Source:** the audit `~/dev/pof-research/v31-polish-audit.md` (2026-11-23), findings F1–F13. Its scratch tests ran in
  throwaway `git archive` copies (`ScratchAudit.t.sol`, `ScratchRoll.t.sol`); they aren't in any tree, so tasks 1.x
  rebuild them as regression tests.
- **Numbering:** the decisions are **VP1–VP22** (v3.1 polish; VP17–VP22 from the live smoke test of 2026-11-23). That avoids a clash with #132's D-numbers, #251's
  L-numbers, #310's RB-numbers, #311's E-numbers, the R1–R4 rows of `reports/glamsterdam-runtime-v1.md` and the audit's
  F-numbers, which this document cites as findings.
- **Base:** everything marked "observed" was read at `origin/main` bafac40 (the live v3's `contracts/src/v3` and
  `oracle/` are unchanged since rc3's 8946b9c). #323 (#310, branch `proof-of-fix-310-rebase`) and #324 (#311, branch
  `proof-of-fix-311-early-reveal`) are open; both merge before this change's implementation (task 0.1).

### What v3 does today (observed)

| Step | Where | What happens |
|---|---|---|
| A check's epoch | `FeesV3.open`, `contracts/src/v3/FeesV3.sol:225-229` | `_epochOf[id] = rolled + 1` at the commit (`RaceV3Base.sol:478`); `settle` (`:254`) and `checkCost` (`:560`) price at that epoch through `_tokensAt` (`:663`), which reverts `Unpriced(family)` (`:184`) for a family priced later |
| The draw's snapshot | `PanelsBase.snap`, `contracts/src/v3/PanelsBase.sol:189-196` | `rolled` read when the snapshot is taken: at the start, and again at every re-target, refill, audit and challenge snapshot |
| The draw's price test | `PanelsDraw.fill`, `contracts/src/v3/PanelsDraw.sol:257-261` | unpriced: skipped and announced; `pricedFrom(family) > snap.rolled`: skipped. So a family priced after the check opened but before the snapshot **is seated** (F1) |
| Shadows | `PanelsDraw.shadows`, `PanelsDraw.sol:315` | only `isPriced`; a later-priced shadow is "paid nothing" by `payShadow`'s catch (F12, by design) |
| The k = 1 hold | `PanelsDraw.challengersReady`, `PanelsDraw.sol:332-357`, from `PanelsVerdict.sol:384-408` | counts eligible, drawable, bonded, non-party validators with room under the caps; **no price test at all** |
| The roll | `FeesV3.roll`, `FeesV3.sol:343-348`; constants `:80-81` | parts while `gasleft() > ROLL_PART_GAS` (1M); `ROLL_WORK` 100 entries a part. Measured parts of 3.1M and 4.0M gas at 3 posters (F2) |
| Announce | `PanelsBase.announce`, `PanelsBase.sol:317-319`; `FeesV3.announce` `:329-337` | `try … {} catch {}`; idempotent; any later draw that meets the validator announces again |
| Top-up | `Validators.topUp`, `contracts/src/v3/Validators.sol:383-392` | `_rebucket` then `++epoch` always. `recheck` (`:504-514`) already bumps only when a bucket moved |
| The repayment | `contracts/script/DeploySepolia.s.sol:374` | `Caps(140_000, 16_000, 20, 1_000_000, 50_000, 1 gwei)`: `gasAllowance` 1M, `gasOverhead` 50,000, `maxGasPrice` 1 gwei |
| The node's keeper | `oracle/node_v3.py:739-903` | `_call` (`:739-753`) counts every `Reverted`; `_settled` (`:755-756`) stops a once-only call at `GIVE_UP` = 50 (`:75`). `startWindow` (`:779`), `result` (`:802`), `finish` (`:804`), `release` (`:811`), `roll()` (`:816`) and `refill` (`:895`) are sent every pass while due-or-not |
| Its pass | `NodeV3.run`/`tick`, `oracle/node_v3.py:265-321` | `ORACLE_POLL` 2 s (`oracle/__main__.py:148`); seats first, then table, then the keeper; an `Unavailable` (HTTP 429 among others, `oracle/rpc.py:58`) aborts the pass; both call `me()`, which refuses an unregistered key (`:247-262`) |
| Gas | `Wallet.send`, `oracle/rpc.py:265-271` | estimate × 1.25 + 10,000; no override. `poll_s` 0.4 s between receipt looks (`:263`) |
| Families | `oracle/node_v3.py:65-67`, `:95-113` | `LIST_NAMES` in the `provider/line` form; the table posts every listed family plus the priced ones. The deployment seats `anthropic.claude` (`contracts/deployments/sepolia-v3.plan.json:24`; `docs/guides/run-a-validator.md:17`, `:133`; `docs/take-part.md:14`) |
| Who draws | `validator-kit/sevsnp/lambda/watcher.py:1-51`, `:214` | the watcher wakes a host for this key's seats (and `WAKE_ON_HEAD`). A check that nobody drew has no seats, so nothing wakes |
| pofctl `status` | `pofctl/v3cli.py:254-293` | the address is `ctx.wallet("solver").address` (`:256`), which decrypts the keystore (`pofctl/cli.py:96-112`); no ETH balance |
| pofctl `issue register` | `pofctl/v3cli.py:296-346` | takes `--rad-issue` (the whole id); the guides scrape it from `rad issue open`'s box (#327, finding 8) |
| The snapshot | `scripts/github_snapshot.py:51`, `:63`, `:146-148` | `IMAGE_INPUTS` copied verbatim with the private terms #318 left in them (term numbers 5, 6, 7, 8, 9, 11, 20) |
| The README's hold | `README.md:305-307` | "fewer than 3 validators could judge a challenge" / "3 validators outside the panel" (F7) |

### The live smoke test on Sepolia v3 (2026-11-23, observed)

Registration 1 went through the whole path on live v3: registered, drawn (by the seed host's keeper), judged a Pass at
k = 1, now Held (too few validators for the hold, F7). It found:

| # | What | Where |
|---|---|---|
| S1 | `pofctl --v3 issue register` fails right after its own approval with `ERC20InsufficientAllowance`: the provider answered `register`'s estimate from a node that hadn't seen the approval yet | `pofctl/v3cli.py:322-325`, `ensure_allowance` `:222-242` |
| S2 | No transaction hash or block in pofctl's output for `faucet` or `issue register`, in `--json` too | `pofctl/v3cli.py:537-564`, `:296-346` |
| S3 | Nothing shows a reporter its registration's progress: `status` covers the solver only, and there is no `issue show` | `pofctl/v3cli.py:254-293` |
| S4 | The verdict is visible only on-chain: nothing on the Radicle issue says it passed or failed | `oracle/node_v3.py` (no comment step) |
| S5 | `oracle.rpc.Rpc` defaults to `retries=0`, so a 429 fails a pofctl call at once; the node passes 5 (`oracle/__main__.py:172`, `:192`) | `oracle/rpc.py` `Rpc.__init__` |
| S6 | **The RPC key is printed:** `Rpc` strips only the URL's user info (`oracle/rpc.py:106-114`); Infura's key is in the path (`/v3/<key>`), so every "answered HTTP 429" line carries it. The live validator's console shows its key today | `oracle/rpc.py`, the node's log, the watcher |
| S7 | The guides don't say how long a verdict takes: about 2–3 h on v3 (the 2 h seal window, then the reveal), then held until 6–7 validators | `docs/guides/*.md` |

### Sizes, measured (the audit, on #324's copy)

| Contract | Before (B) | After F1 (B) | Margin after (B) | This change also |
|---|---:|---:|---:|---|
| PanelsDraw (library) | 10,656 | 10,827 | 13,749 | `challengersReady`'s price test (VP1), est. +60–120 |
| FeesV3 | 18,026 | 18,072 | 6,504 | F2's constants, ≈0 (VP3) |
| Validators | 22,908 | – | 1,668 | F8, est. +30–60 (VP4) |
| Panels, PanelsJudge, PanelsVerdict | – | unchanged | PanelsVerdict 1,249 | nothing |
| RaceV3, RaceV3Annex, RaceV3Endings | – | unchanged | RaceV3Endings 983 (#323) | nothing |

The rule for every contract this change touches: at least 512 B of runtime margin after it, measured with
`scripts/contracts.sh sizes` once #323 and #324 are merged (task 1.8).

**Measured after the change (task 1.8, 2026-11-24, `scripts/contracts.sh sizes` on main 736808b + this change; runtime
bytes, margin under EIP-170's 24,576):**

| Contract | Before (B) | After (B) | Margin after (B) | Code |
|---|---:|---:|---:|---|
| FeesV3 | 18,026 | 17,961 | 6,615 | changed (`drawEpoch`; `ROLL_PART_GAS` and the part loop gone) |
| Validators | 22,908 | 23,007 | 1,569 | changed (`topUp`'s epoch) |
| PanelsDraw (library) | 10,656 | 11,186 | 13,390 | changed (`fill`'s epoch, the hold's price test) |
| Panels | 19,026 | 19,026 | 5,550 | identical but for the metadata hash |
| PanelsJudge | 16,695 | 16,695 | 7,881 | identical but for the metadata hash |
| PanelsVerdict | 23,327 | 23,327 | 1,249 | identical but for the metadata hash |
| RaceV3 | 22,982 | 22,982 | 1,594 | identical but for the metadata hash |
| RaceV3Annex | 23,406 | 23,406 | 1,170 | identical but for the metadata hash |
| RaceV3Endings | 23,593 | 23,593 | 983 | identical but for the metadata hash |
| PanelScores, PoolV3, SolverBook, CoinFaucet, TestCoin, LaunchChain | – | unchanged | – | identical |

## Goals / Non-Goals

**Goals:**

- No check, payment, stake or bounty can be locked by a family's first price (F1), on v3.1 by the contracts and on
  live v3 by the nodes' tables.
- Every gas-dependent success in v3.1 is monotonic in the gas limit (F2, F3), so `eth_estimateGas` is safe to use.
- A keeper that is cheap on RPC, never gives up a payment that is only late, and never lets a rate limit cost a seat
  its deadline.
- An idle network of on-demand validators still draws its checks, and anyone can keep or draw without a bond.
- One family name, and docs that state the real thresholds.

**Non-goals:**

- **F6's design change** (D29: the claim at commit capped to the solver's room, or the price amount locked per solver
  at `attempt`): a separate owner decision. Docs only here (VP14).
- **F7's design question** (whether the hold should count only HOLD_K at launch scale).
- **F2's fuller fix** (new slots counted as work in a part, `ROLL_PART_GAS` at the 8037 worst case): only if batching
  matters later.
- **F11's per-judge overhead or second gas reading** (RaceV3 bytes), **F12's binding read-back**, **F13** (faucet):
  info findings.
- **F9's guard** (decided against, VP5).
- Applying the seed's Terraform and installing its service unit: operations (`~/dev/pof-research/keeper-runbook.md`).
  This change commits the code and the Terraform they use (VP10, VP22), and applies nothing.

## Decisions

### VP1. F1: a paid seat only for a family priced at the check's epoch

**The rule.** FeesV3 gets `drawEpoch(uint256 id) external view returns (uint256)`: `_epochOf[id] - 1` once the check
is open, else `rolled`. `IPanelsFees` (`contracts/src/v3/IPanels.sol:22-27`) gains the view. `PanelsDraw.fill` reads it
once per call and compares `pricedFrom(family)` with `ep = min(drawEpoch(id), c.snap.rolled)` instead of
`c.snap.rolled` (`PanelsDraw.sol:261`).

- That is the rule `shadowCost` already applies to shadows, extended to the seats whose pay reverts: counted, refill,
  audit and challenge seats all go through `fill` (`PanelsJudge.sol:327`, `PanelsVerdict.sol:104`, `drawPanel`).
- Shadows (`PanelsDraw.shadows`) keep `isPriced` only: new families qualify through shadow verdicts, and a shadow priced
  later is paid nothing by design (F12).
- A rebase check (#310) opens its own FeesV3 epoch through `_newCheck` (`RaceV3Base.sol:478`), so it is priced and drawn
  at its own opening.
- Tried in the audit's scratch copy of #324: 0 of 12 panels seated the fresh family, every `result` succeeded, and
  the whole v3 suite passed (36 suites, 480 tests).

**The hold too.** `challengersReady` counts a challenger only if `isPriced(family)` and
`pricedFrom(family) <= drawEpoch(id)`.

- Without it, a later-priced validator would count toward ending a k = 1 hold although a challenge panel can't seat it
  (today the hold has no price test at all, so an *unpriced* family's validator counts too). The window would then start
  while the challenge would wait (L25 retries it, and it lapses with the stake returned): no lock, but a lone verdict
  becoming final without a real chance of challenge, which is what the hold exists to prevent.
- `ShadowCtx` already carries `fees` and `id`; the cost is in the PanelsDraw library (13.7 kB margin), two static calls
  per scanned validator (up to HOLD_SCAN_MAX). PanelsVerdict's bytecode doesn't change.
- At launch (one family, priced from genesis) it changes nothing.
- **Decided (owner, 2026-11-23):** the price test in `challengersReady`, as recommended.

**Alternative B, rejected:** FeesV3 charges a later-priced family at its first price. No Panels change and more families
drawable, but it breaks "an attempt is charged the prices it was quoted" (#132's check-pricing): a first price can be
2× the dearest family the deposit was sized for, so `result` would truncate the last judges' pay.

**Tests** (tasks 1.1–1.3): the audit's scenario as a regression for each path that reverted (a counted re-target, `refill`,
an audit's `payPanel`, a challenge's `settleChallenge`), each failing on bafac40's code; a shadow of the fresh family
still drawn and paid nothing; a hold not ended by later-priced validators; and an invariant in
`RaceV3Invariant.t.sol`: every seated non-shadow validator's family has `pricedFrom <= drawEpoch(check)`.

### VP2. F1 on live v3: no new family is priced there

Live v3 can't be patched, and its validators run the measured image `0xd95b…87d1`, so a code change in `oracle/` doesn't
reach their tables until v3.1's disk.

- **Now, by configuration** (no code): `ORACLE_LIST_PRICES={}` makes `build_table` (`node_v3.py:95-113`) post only the
  families already priced, at the price in force (`_json_setting("{}")` is `{}`, not the default, `node_v3.py:223`).
  `node_config` accepts it (`validator-kit/sevsnp/terraform/variables.tf:82-83`). The v3 guide's node config gets it
  (task 7.3), and the owner's genesis validator gets it on the owner's go (task 10.0).
- **In code, for any node built from now on:** the node probes `FeesV3.drawEpoch(0)` once at start. If the call
  reverts (live v3's FeesV3 has no such function), `build_table` drops every family that isn't already priced and logs
  it once. On v3.1 it posts every listed family, as today. Probing the chain rather than reading the record's version
  needs no record field and can't be got wrong by an operator.
- **The cost:** no new family on v3. The guides don't offer one, and three counting tables from other families are
  needed anyway (F10, point 3).

### VP3. F2: `ROLL_WORK` 40 and one part per `roll()`

- `ROLL_WORK` 100 → **40**. Scaled from the audit's measurements at 3 posters: the worst parts are ≈4.2M (families: 10
  families, 30 new checkpoints) and ≈6.8M (new families: 5 priced, 55 new slots) under EIP-8037, all well under 2^24
  and under the 8M the spec allows.
- **`roll()` is `rollPart()`** (one part a call), and `ROLL_PART_GAS` is removed. That removes the only gas-dependent
  branch, so the estimate is exact and success is monotonic.
  - The alternative `ROLL_PART_GAS = 2**24` relies on `gasleft()` never exceeding it, which a reservoir transaction
    (tx.gas > 2^24 under 8037) breaks. One part a call has no such assumption.
  - The cost: a period takes a few more transactions (about 5 at launch, each cheap). `roll()` stays for the ABI.
- While a roll is under way `post` and `announce` revert `RollInProgress`; nothing changes there, and the keeper finishes
  a roll within a pass or two (VP8).

**Tests** (task 1.4): the audit's `ScratchRoll` as a regression (3 posters, 40 priced and 20 announced families, every
price moving): every part's gas plus 97,920 × its new slots ≤ 8,000,000; a limit sweep (`roll()` at every limit from its
estimate to the block limit, in steps, succeeds); `test_rollPartsAreBounded` (`FeesV3.t.sol:1054-1081`) rewritten
against the 8M bound instead of `ROLL_PART_GAS`.

### VP4. F8: a top-up bumps `epoch` only when it changed something

- `topUp` records `_place[key].bucket` and `v.state` before `_rebucket`, and runs `++epoch` only if either changed.
  This is `recheck`'s rule (`Validators.sol:504-514`), and `_rebucket`'s `_floor` already moves a below-floor key back
  to Active.
- A candidate's top-up changes neither (its bucket is 0 before and after). If the implementation finds a candidate's
  bond feeding shadow eligibility (`canShadow`), a top-up that crosses that floor bumps too, with a test.
- A minimum top-up, the weaker alternative, still lets a griefer re-arm every wait for that minimum; rejected.
- **Tests** (task 1.5): a top-up below the next tier leaves `epoch` unchanged and a waiting draw still refuses
  `NothingChanged`; a top-up across a tier, and one that restores a below-floor validator, bump it.

### VP5. F9: no guard on `try fees.announce(key) {} catch {}`

Decided: leave it.

- `announce` is idempotent and permissionless, and every later draw that meets the validator announces it again. A
  starved call (only on the refill/advance/mismatch paths, where little follows) skips an announcement, nothing else.
- Success stays monotonic there (no reverting band between the skip and the full branch), so it isn't the #325 shape.
- The guard costs ≈40–60 B in each of PanelsJudge and PanelsVerdict, and PanelsVerdict has 1,249 B after #324, which
  #310's and #311's follow-ups may need.
- **A test pins the claim** (task 1.6): a refill with gas just short of `announce` leaves the family unannounced and
  the refill done, and the next draw meeting the validator announces it.

### VP6. The keeper's retry model (F4, F5, #314)

**Gated calls: sent only when readable state says they're due.**

| Call | Sent when | Else |
|---|---|---|
| `finish` | `now > finalAt + REPORT_WINDOW_S` | nothing |
| `release` (the race's) | the race's `resultDays` (read once) has passed since the sub's day, or `paid` once a panel sat | nothing |
| `result`, `payPanel`, `settleChallenge` | every seated key reported (`usage_of(pid, slot).receipt != 0`) or `now > revealBy + REPORT_WINDOW_S` | nothing |
| `startWindow` | as today, at most `CHALLENGE_TRIES` per (`s`, registry `epoch`, `now // capWindow`), as `drawChallenge` already does (`node_v3.py:841-846`) | – |
| `refill` | at most `CHALLENGE_TRIES` per (`pid`, `epoch`, `now // capWindow`) | – |
| `roll()` | replaced by the `rollPart()` loop (VP8) | – |
| `merge`, `mergeExpired` | pre-gated as today (#314's part already in `_merge`) | – |

**Giving up.** A refusal whose reason is time- or state-gated (`NotYet`, `NotReady`, `TooEarly`, `NothingDue`,
`NothingChanged`, `ShortOfGas`) doesn't count toward giving up. Any other refusal starts a wall-clock budget:
`GIVE_UP_S` = 86,400 s after the first one, the call is left to others. Today's count (`GIVE_UP` = 50 passes, minutes at
2 s) goes.

**Backoff for whatever stays ungated.** Per call key: `(n, next_at)` with `next_at = now + min(BACKOFF_BASE_S ×
2^(n−1), BACKOFF_MAX_S)` (30 s, 3,600 s); `n` resets when the key's state fingerprint changes (registry `epoch`, the
capacity window, the verdict's status, `rolled`). One log line per backoff, with the skipped count (#314's "done when").

**The pass and the RPC.**

- **Cadence:** `ORACLE_POLL` defaults to 12 s (one block) on Sepolia (chain id 11155111) and stays 2 s on a devnet. The
  keeper section runs every `ORACLE_KEEPER_EVERY` s (default 60 on Sepolia, every pass on a devnet). Seats keep running
  every pass. `Wallet.poll_s` becomes `ORACLE_TX_POLL` (default 4 s on Sepolia, 0.4 s on a devnet; the runbook's
  item 3: 0.4 s means about 30 receipt looks per transaction).
- **A scan that forgets finished checks:** a submission that is `done` with its verdict Final or Released and nothing
  owed, and a panel in `_kept`, leave the keeper's scan set (the runbook's item 4: today every pass reads every
  submission ever). A restart rescans once from `ORACLE_FROM_BLOCK`.
- **A per-pass budget:** the keeper section stops after `ORACLE_KEEPER_BUDGET` RPC calls (default 300), and resumes
  next time from where it stopped (a rotating cursor), so a long list is covered over several passes.
- **HTTP 429 in the keeper section** (an `Unavailable` there) no longer aborts the pass: the keeper section pauses for
  the answer's `Retry-After` or a backoff (`RATE_PAUSE_MAX_S` 600 s), logged once; the seat steps of the next pass run
  as usual. The seat steps stay first in the pass.
- **No RPC key in a log line:** VP20.
- **Short rate limits:** absorbed by `Rpc`'s own retries (VP19, seconds); a storm that outlasts them pauses the keeper
  section as above (minutes). The two don't stack beyond `RATE_PAUSE_MAX_S`: the keeper's pause starts only after
  `Rpc` gave up.

**Tests** (task 2.1): a fake chain that counts estimates per call key over simulated hours: at most k estimates per
state for `startWindow`, `finish`, `release` and `refill`; one late report: `payPanel` not sent before the window, sent
after it, never given up; a 429 storm doesn't delay a due reveal; the scan set shrinks as checks finish; no key in a
logged URL.

### VP7. F3: `payShadow` with a gas floor

- `Wallet.send` gains a `gas_floor`: the limit is `max(estimate × 1.25 + 10,000, gas_floor)`. Unused gas isn't
  charged.
- `PAY_SHADOW_GAS_FLOOR` = **600,000**: the paying branch plus EIP-8037's first-write margin, from the audit.
  Task 2.2 measures the paying branch on v3 and v3.1 under 8037 and keeps the floor at least twice it.
- On live v3 this puts the keeper's own call on the paying branch (anyone else can still grief a seat there; #325). On
  v3.1 #323's `ShortOfGas` guard already makes success monotonic, and the floor only saves a failed estimate.
- **Test:** a node test that `payShadow` is sent with at least the floor; #323's
  `test_payShadowNeverClosesASeatUnpaidOnShortGas` stays.

### VP8. F2 on the keeper: a `rollPart()` loop

While `rolled < current_period`, the keeper calls `rollPart()`, at most `ROLL_PARTS_PER_PASS` = 10 a pass. Each part
has no gas branch, so its estimate is exact. This takes F2 off live v3 without a contract change (through the
keeper-only node, VP10), and it is what v3.1's `roll()` does anyway.

### VP9. Who draws: the watcher's draw duty

**Yes, the watcher wakes a validator for undrawn checks**, as it does for the Radicle duty (`WAKE_ON_HEAD`):

- Each run it also scans RaceV3's events that open a check (`Committed`, `Registered`, and #310's `Rebased`) in the
  same block range as `Seated`, and keeps the undrawn ones on its state list (bounded by `STATE_LIMIT`, as the seats).
- **Due:** a listed check is due when its verdict is `SEALED` and the block is past `seedBlock + DRAW_GRACE_BLOCKS`
  (default 25, about 5 minutes), or `WAITING` and `now > retryAt + DRAW_GRACE_BLOCKS × 12 s`, **plus this validator's
  stagger**: `keccak256(validator, id) mod (DRAW_STAGGER_MINUTES × 60)` seconds (default 10 minutes). With n validators
  the first wakes after the grace plus the least of n stagger draws; the others see the check drawn and drop it.
- **Starting:** once per check (`DRAW_MAX_STARTS` = 1), under the fuse, the budget and the kill switch as any start.
  Not held by the spend pause: a draw needs no model call (like a reveal). The node (`oracle run --until-idle`) draws
  it with its keeper (on by default) and powers off once idle, or stays if it was drawn itself.
- **A check drawn, released or refunded** leaves the list (amended by VP23: a drawn check stays listed until final). A seed block older than 256 blocks isn't a problem: the draw
  re-targets (`PanelsVerdict.sol:41-46`) and the next pass draws.
- **Default on** in the kit (`WAKE_ON_DRAW = "true"`): with an always-on keeper (the seed host's) it never fires; without
  one it is the only thing that draws. The cost is about 10 minutes of compute per undrawn check, staggered so that
  usually one host wakes. **Decided (owner, 2026-11-23): on by default**, as recommended.
- **RPC:** the draw duty reads at most `DRAW_READS_MAX` = 20 verdicts a run; a 429 ends the run before it saves
  anything, as today (the runbook's item 6: the watcher's own key is the advice, in the kit's runbook).

**Why not only a keeper:** an always-on keeper is one host someone pays for (today the owner's seed). The watcher makes
drawing a property of the validator set, at the cost of a few staggered boots.

**Tests** (task 3.1): in `tests/test_sevsnp_watcher.py`, an undrawn check past grace and stagger starts the instance
once; one drawn within the grace starts nothing; two watchers with different keys start at different times; a waiting
check past its retry time; the fuse and the kill switch hold it.

### VP10. A keeper-only node mode: the seed host's `oracle/keeper.py`, upstreamed

`python3 -m oracle.keeper run [--once] [--from-block N]` (and `info`). It is the file the seed host runs today
(`~/dev/pof-research/keeper-runbook.md`; branch `keeper-sepolia-local` in the keeper build tree, commit 1ca389d, 217
lines, never pushed), folded in as it is, with VP6–VP8 in the keeper calls it shares with the node:

- **`Keeper(NodeV3)`** sets only the chain, the wallet, the log and its retry state, and leaves out everything else a
  node has (seats, judge, host, receipts, Radicle), so a method that needs them fails loudly instead of acting. `tick`
  runs `_keep` alone; no `me()`, so no registration. It never seals, reveals, judges, posts a table or pushes.
- **The key pays gas only**, so it may be a plain key (`ORACLE_PRIVATE_KEY` or `ORACLE_PRIVATE_KEY_SECRET_ARN`) on any
  chain: it never signs a seal, reveal, receipt, registration or claim, so the attestation rule for validator keys
  doesn't apply. `ORACLE_KEEPER_ADDRESS`, if set, must be the key's address, or it stops at start.
- **`ORACLE_RPC_SECRET_ARN`:** the RPC URL from Secrets Manager (a URL with its key in it), through
  `oracle/awssecret.py`; also for the node (VP20).
- **Redaction:** its `Redactor` (the URL, its path and its last path segment, each of 8 characters or more, replaced in
  every line, tracebacks included) becomes VP20's shared redaction.
- **Transaction logging:** `KeeperWallet` logs each transaction's hash, block, gas used and ETH cost, and a call mined
  but reverted (gas spent: another keeper came first). The node's wallet logs the same (VP17's hashes, on the node's
  side).
- **The hourly cap:** `ORACLE_KEEPER_MAX_TX_HOUR` (default 60) counts each send, an estimate that reverts included
  (loose on purpose); past it, passes wait for room, said once an hour.
- **`Wallet.poll_s` configurable:** `ORACLE_TX_POLL`, for the keeper and the node (VP6's defaults).
- **A cursor over the submissions:** finished submissions leave the scan set and a cursor over the event list resumes
  where the last pass stopped (VP6), so a pass no longer re-reads every submission ever.
- **Its defaults** keep the seed host's: `ORACLE_POLL` 120 s (a free RPC tier's daily credits), `ORACLE_TX_POLL` 3 s.
- `info` prints the address, its ETH balance, the deployment and the scan's start, and says "not registered (keeper
  only)" instead of `None` (the runbook's item 7).
- **Docs:** `oracle/__main__.py`'s help, a "Run a keeper" section in `validator-kit/runbook.md` (the systemd unit as on
  the seed host, with its limits, and its cost from the runbook: about 1.5–2M gas a check, ≈9k RPC calls a day at a
  120 s poll) and a line in `docs/take-part.md`.
- **Tests:** `tests/test_keeper.py`: an unregistered key keeps a fake chain's checks and sends no seal, reveal, post or
  register; a mismatched address stops it; the cap; the redaction of a URL with a path key in a log line and in a
  traceback; the transaction lines.

### VP11. pofctl

- **`pofctl --v3 draw <id>`:** reads Panels' verdict. `SEALED` past its seed block: sends `Panels.draw(id)` then
  `RaceV3.signal(id)`. `WAITING` with the registry changed or past `retryAt`: signal, draw, then signal again if a
  panel was seated (VP24). Anything else: says why
  (before the seed block, with the blocks left; already drawn; waiting until a time) and sends nothing. Any key with gas
  (the `reporter` role by default). `issue register` and `submit` print the hint: "if no validator draws it within
  10 minutes: `pofctl --v3 draw <check>`".
- **`status` without the password:** the address comes from `--address`, then `address` in `pofctl.json` (the guides
  put the address `cast wallet new` prints there), then the keystore's `address` field if it has one. The keystore is
  decrypted only if none gives it. Signing commands are unchanged.
- **ETH in `status`:** the address's ETH balance (`eth_getBalance`), in the text and the JSON, with "about 0.01 Sepolia
  ETH covers every step" when it is lower.
- **The issue's id from `issue register`:** the whole id on a line of its own (`radicle issue <id>`) and `radIssue` in
  `--json` (already in the data). New: `--title T --description D` instead of `--rad-issue` opens the Radicle issue
  itself (`rad issue open` through `--rad-exec`), takes the id from its output, checks it with `rad issue show <id>`
  (its title must match), then registers. That retires the guides' `awk` over `rad issue open`'s box (#327, finding 8).
- **Tests** (task 4.x): each refusal of `draw`; `status` with a keystore and no terminal asks nothing; the ETH line;
  `register --title` against `tests/fake_rad.py` extended with Radicle 1.10.3's box output.

### VP12. One family name: `provider/line`

Decided: **`provider/line`** (`anthropic/claude`), not the dotted form.

- It is what #132's validator-admission spec names ("the provider's model line as its receipts name the model, for
  example `anthropic/claude`"), what `ORACLE_FAMILY`'s help says (`oracle/__main__.py`), and what the node's `LIST_NAMES`
  and every receipt check already use. The dotted name exists only in the v3 plan, record and two guides.
- **v3.1's plan** names `anthropic/claude`. `scripts/deploy_sepolia.py` refuses a family that doesn't match
  `^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9.-]*$`, before anything is sent.
- **The node's `register`** refuses an `ORACLE_FAMILY` not in that form, unless that exact name is already priced on the
  deployment (so live v3's `anthropic.claude` validators can still join v3 until it is superseded).
- **The guides** switch to `anthropic/claude` together with the switch to v3.1 (task 11.3); until then v3's guides keep
  `anthropic.claude`, with a note that v3.1 renames it.
- `tests/test_genesis_validator.py:85` and the plan fixtures follow.

### VP13. The v3.1 deploy plan's repayment values (F11)

| Value | v3 | v3.1 | Rationale |
|---|---:|---:|---|
| `gasOverhead` | 50,000 | **500,000** | the measured k = 1 tail (480,361 of 698,932) rounded up: repays ≈103 % at k = 1, ≈60–100 % at k = 3 |
| `gasAllowance` | 1,000,000 | 1,000,000 | caps `window + overhead`, ≤ ≈0.8M at k = 3 and ≤ ≈0.9M at k = 7; 1.5M would add 1.35 coins to every deposit for nothing |
| `maxGasPrice` | 1 gwei | 1 gwei | the deposit's gas line stays 1M × 1 gwei × 2,700 = 2.70 coins; on Sepolia (≈20 wei/gas) the repayment rounds to 0 either way |

Set in `DeploySepolia.s.sol:374` and read back from the record by `deploy_sepolia.py`'s checks. The deposit doesn't
change.

### VP14. Docs: the hold's real threshold and the newcomer's ceiling

- **F7:** `README.md:305-307`, `docs/take-part.md` and `docs/guides/run-a-validator.md` say: a held k = 1 verdict needs
  `challengeK(1) + auditsDue − auditsDrawn + (auditDecided ? 0 : 1)` validators outside its panel and auditors, bonded,
  not parties and with room now: **six before the audits are drawn (seven in all), three outside the judge and both
  auditors after (six in all)**; below that every lone verdict stays held, and at exactly the threshold one validator
  pausing holds them all (L16). A test (`tests/test_guides.py`) checks the stated numbers against `HOLD_K`, `K1_AUDITS`
  read from the contracts' source, and a Foundry test documents the 6/7 threshold.
- **F6 (docs only):** `docs/guides/submit-a-fix.md` and `docs/take-part.md` state the newcomer's ceiling: with a cap of
  `REP_BASE` 50 coins at the 50 % opening share and the finder's fee of 17.65 %, funds less the registration fee over
  about 117.6 coins can't be claimed; pledges after an attempt still raise the claim (the share is locked, the funds
  aren't); so record the attempt (`attemptFee` 0 on Sepolia) as soon as work starts, and check `pofctl status`' room
  before committing. The design change is the owner's (non-goal).

### VP15. The checker image's files lose the private terms (#318's follow-up)

- In `IMAGE_INPUTS` (`scripts/github_snapshot.py:51`): the comments, defaults and examples that hold the terms #318
  kept (term numbers 5, 6, 7, 8, 9, 11, 20: internal hostnames, the organisation and repository names, platform issue
  numbers) are rewritten in neutral words. A default that was an internal hostname becomes no default (the setting is
  then required, with a clear error) or a public one; the kit and tests set it.
- **The exemption shrinks to v3's refs:** the preset's `verbatim` exemption applies only to refs listed in it (live
  v3's 8946b9c and the `sepolia-v3` branch, whose image `0xd95b…87d1` must stay reproducible while v3 lives). For any
  other ref the image files are still copied verbatim (so the public code builds the listed image), but **a kept term
  fails the run**. Since a clean file scrubs to itself, verbatim and scrubbed are the same there.
- **Test:** `tests/test_github_snapshot.py` scans the working tree's `IMAGE_INPUTS` with the preset's replacement terms
  and requires zero hits (so a term can't come back); a ref outside the list with a kept term fails.
- The image's digest changes: expected for v3.1 (a new disk, task 9.2). When v3 is retired (it sunsets by itself,
  `idleDays` 28), the list empties and **the exemption code is removed (decided, owner, 2026-11-23, Q3)**.

### VP16. Shipping: v3.1 is #310 + #311 + this change, one release candidate (rc4)

- #323 and #324 merge first (task 0.1); this change's code is on top. Contracts are redeployed together, so FeesV3,
  PanelsDraw and Validators change freely.
- **The keeper reaches live v3 first**, without an image: the seed host's keeper-only node (VP10) runs the new keeper
  against v3 once tasks 2–3 are merged (task 10.0, the owner's go). The validators' measured nodes get it with v3.1's
  disk.
- **The seed host's keeper is launch infrastructure (decided, owner, 2026-11-23, Q1).** The v3.1 plan and record name
  it (its account's address and its role: "the seed host's keeper-only node") with its cost line: about $0 (the seed's
  existing instance) plus Sepolia gas (about 1.5–2M gas a check; at ≈20 wei/gas effectively nothing). The watcher's draw
  duty stays on as the fallback. The genesis validator keeps its own keeper on (decided, 2026-11-23).
- **One rc4** for all three changes. #310's tasks 7–8 and this change's tasks 9–11 are the same steps (the gate, the
  release candidate, the plan, the deployment, the hand-over): each is done once, and ticked in both with the same
  evidence. The v3.1 plan carries #310's `mergeDays` 3 (O4), VP12's family and VP13's values.

### VP17. pofctl fixes from the smoke test (S1–S3)

- **S1, the approval race:** after `ensure_allowance` sends an approval, it waits until `allowance()` reads at least
  `need` (every `APPROVAL_POLL_S` = 2 s, up to `APPROVAL_WAIT_S` = 60 s), so the next estimate can't be answered from a
  lagging node. If the send still reverts `ERC20InsufficientAllowance`, it is retried once after another wait. Every
  command that approves (`issue register`, `pledge`, `submit`, a rebase, a dispute) goes through it.
- **S2, transaction hashes:** every command that sends prints each transaction's hash and block (and the approval's),
  and its `--json` carries them as `tx` and `block` (a list `txs` when it sent several). `faucet` and `issue register`
  first.
- **S3, a reporter's view:** `pofctl --v3 issue show --issue N` prints the registration's check: its status (sealed,
  waiting, judging, held, window, final, released), k and panel, the seal, reveal and report deadlines, the counted
  result (pass or fail), the hold's state and `finalAt`, and the deposit: paid to judges so far, the refund due and
  whether it was refunded. `--json` has the same. `status` also lists the address's registrations (from `Registered`
  with that reporter) with one line each and the `issue show` hint.
- **Tests:** a fake chain whose allowance lags one read behind the approval (S1, `register` succeeds and waits once);
  `tx`/`block` in each sending command's JSON; `issue show` in each status, from the fake chain.

### VP18. The verdict on the Radicle issue (S4)

After a verdict is counted, the node of the counted panel's first revealed seat comments a short receipt on the
bounty's (or the registration's) Radicle issue, through its own Radicle node:

- the outcome (pass or fail), k, the verdict's state (held, window, final) with the times that apply, the counting
  transaction's hash, and a marker line `pof-verdict: <chainId>/<race>/<check>` so the comment is made once (a node
  that finds the marker skips it; a restart doesn't repeat it);
- **the reason**, the judge's one-line answer, only where it reveals no sealed evidence: for a registration check whose
  registration isn't `hidden`, at once; for a fix check, only once its bounty is paid or closed unsolved (the
  `checking` rule "Evidence sealed until the bounty settles"), as a second comment then. A `hidden` registration (hidden
  tests) never gets the reason;
- only from a node with a Radicle node (`ORACLE_FIX_SOURCE=radicle`); the keeper-only node doesn't comment. A failed
  comment is retried with the keeper's backoff and never blocks a seat step.
- **Tests:** on the Radicle fakes, a counted registration check gets one comment with the reason; a fix check gets the
  outcome only, and the reason after the bounty is paid; a second node finding the marker doesn't comment; a hidden
  registration gets no reason.

### VP19. `Rpc`'s retries by default (S5)

- `oracle.rpc.Rpc`'s default `retries` becomes `DEFAULT_RETRIES` = 3 (from 0) for the calls that are safe to repeat (a
  read, `eth_sendRawTransaction`), with its bounded backoff and Retry-After honoured up to `RETRY_AFTER_MAX_S` = 30 s.
  pofctl gets the default; the node keeps `ORACLE_RPC_RETRIES` (default 5).
- This is the seconds scale. Longer storms are the keeper's (VP6: its section pauses up to `RATE_PAUSE_MAX_S`), and a
  seat step tries again next pass. So a 429 never fails a pofctl command at its first answer, and never stalls a node
  for more than a pass.
- **Tests:** an `Rpc` with no `retries` argument retries a 429 three times with Retry-After, and doesn't retry
  `eth_sendTransaction` or a revert.

### VP20. No RPC key in any log line (S6)

- **At the source:** `Rpc` keeps the URL it shows as scheme, host and `/…` whenever the path has a segment of 8
  characters or more (Infura's `/v3/<key>`, Alchemy's `/v2/<key>`), as it already drops the user info. Every error and
  retry line uses the shown form.
- **At the sink:** the node's, the keeper's and the watcher's log functions pass every line through one shared
  redactor (VP10's `Redactor`) loaded with the RPC URL (and `ORACLE_RPC_SECRET_ARN`'s value), tracebacks included, so a
  library's message that prints the URL is caught too.
- **The live key:** the validator's console has shown its key; the owner rotates that Infura key once the redaction is
  deployed (task 10.0, the owner's go).
- **Tests:** for each of the node, the keeper, pofctl and the watcher, a 429 from a URL with a path key logs no part of
  the key; a traceback through `Rpc` is redacted.

### VP21. The guides' timing (S7)

The guides say how long a verdict takes: **on v3, about 2–3 hours to a verdict** (the 2 h seal window, the reveal, the
count), **then held until 6–7 validators** with room (F7, VP14); **on v3.1 with #311, minutes** once every seat has
sealed, then the same hold. A test checks the stated windows against the deployment record's `windows`.

### VP22. The seed's and the kit's Terraform (operations, made safe)

- **The seed:** the `keeper_secret_arns` variable (Secrets Manager ARNs only; default empty) and its policy
  (`secretsmanager:GetSecretValue` on exactly those ARNs, attached to the seed's role only when the list isn't empty)
  are committed to `seed/terraform/`. They exist today only as uncommitted changes in the kit build tree, with the
  values in its untracked `seed.tfvars`; the values (ARNs) stay out of the repository.
- **`create_instance` pinned:** a plan without `create_instance = true` destroys a running seed (its default is
  `false`). `seed/README.md` and a committed `seed.tfvars.example` set it explicitly and say so in bold, and the README's
  every `tofu plan`/`apply` line carries it. The same note for the SEV-SNP kit (`validator-kit/sevsnp/terraform`,
  `create_instance`, `validator-kit/runbook.md`).
- **Tests:** `tests/test_seed*.py` (or the kit's Terraform tests) check that the example tfvars set
  `create_instance = true` and that `keeper_secret_arns` accepts only ARNs.

### VP23. The watcher keeps a drawn check until it is final (decided, owner, 2026-11-24, Q1)

**Decision:** a check stays on the watcher's draw list until it is final, not until its first wake; wakes are
remembered per round.

- **What VP9 missed:** a check left the list once drawn (JUDGING or later), or once given up after its one start. A
  panel released back to waiting (L19: missed deadlines; `Panels.release` sets `Waiting`, `redraws` + 1 and a new
  `retryAt`) emits none of the events that open a check, so the watcher never saw it again. Without an always-on keeper,
  the redraw waited for some node to happen to run (task 3.1's open note).
- **Kept:** a drawn check (JUDGING, HELD, WINDOW) stays listed as `{d, g, c}` and is read again every `RETRY_MINUTES`,
  within `DRAW_READS_MAX`. A check given up for its round stays too (`x`). Final, released (refunded), withdrawn or
  expired: dropped (`draw_dropped`).
- **Per round:** a round is (check, `redraws`, seed block or `retryAt`), and `DRAW_MAX_STARTS` counts per round. A
  released round or a re-targeted seed block is a new round that wakes a host once more for the redraw. Polling the
  same round never starts the instance twice. The redraw's seats are new panels, so their `Seated` events wake their
  validators as any seat does. A `Seated` event for a listed panel with another slot (a refill's replacement seat) is a
  new seat with its own starts.
- **State:** past `STATE_LIMIT`, drawn checks go first (oldest id), then undrawn ones, then seats.
- **Why:** VP9 makes drawing a property of the validator set. That should hold for every round, not only the first,
  or a released round of a keeper-less deployment waits forever. The cost is one verdict read per drawn check every 10
  minutes. A woken host is still held by the fuse, the budget and the kill switch.
- **Tests** (task 12.1): a check released back to waiting and redrawn wakes once for the redraw and its new seat wakes
  the host; hours of polling never start twice for the same round; a drawn check leaves the list once final; drawn
  checks are dropped before undrawn ones when the state is full; another slot on a listed panel is a new seat.

### VP24. One draw-and-signal rule (decided, owner, 2026-11-24, Q2)

**Decision:** the keeper and `pofctl --v3 draw` follow one rule, in one helper (`oracle.v3.draw_and_signal`):

- **Waiting:** signal, then draw, then signal again if the draw seated a panel.
- **Sealed:** draw, then signal.

`RaceV3Endings.signal` counts a wait while the check waits, and otherwise counts the seated validators as drawn (and a
stalled panel). FeesV3 counts each event at most once a period, so an extra signal is harmless; a missing one loses a
count.

- **What was wrong:** the keeper's waiting branch signalled the wait, then redrew, but never signalled the new panel.
  A test showed it before the fix (`['signal', 'draw']`). It also signalled a wait only once per process, so a released
  round's second wait wasn't signalled. `pofctl --v3 draw` drew, then signalled, and missed the wait.
- **The keeper** (`NodeV3._draw_and_signal`; the keeper-only node shares `_keep`, so it has no path of its own) signals
  a wait once per wait round (`redraws`, `waitEpoch`, `retryAt`): the count is once a period anyway, and each signal
  costs gas. The signal after a draw carries its own backoff state, so a refused wait signal doesn't hold it.
- **pofctl:** a failed signal doesn't stop the draw (a keeper signals later). A draw refused after the wait signal
  says that signal's transaction was sent.
- **Why:** with one rule, FeesV3's waits and drawn counts are complete whichever path drew the check, and the keeper,
  pofctl and the code's reader agree.
- **Tests** (task 12.2): the keeper's waiting branch (fails before the fix), the wait signalled once a round, the
  sealed branch, the rule itself; pofctl's three-step order, a draw that leaves the check waiting, a refused draw after
  the wait signal, a failed signal.

### VP25. No default model gateway in `scripts/judge_run.py` (decided, owner, 2026-11-24, Q3)

**Decision:** the hard-coded `GATEWAY` (an internal AgentCore host name) is removed, and `MODEL_GATEWAY_URL` is
required.

- `run`, `run-v2` and `judge_memory_run.py run` call `gateway_url()` first. Unset or blank, they stop before reading
  the plan, with one line naming the variable and "Nothing was sent". Nothing else is printed, sent or written.
- `GatewayJudge` requires a URL, and `judge_from_env` passes `MODEL_GATEWAY_URL` (`ORACLE_JUDGE=gateway:<family>`).
- **Callers:** no workflow, script or guide relied on the default. The tests already set the variable to their stub,
  and no CI workflow calls the gateway. `reports/judges-v1.md` said "by default the prod model gateway"; it now says
  the variable is required. `oracle/README.md` and `oracle/__main__.py`'s help say so too.
- **An image file:** `scripts/judge_run.py` is in `IMAGE_INPUTS` (copied verbatim, in the node image), so this
  changes the checker image's bytes. It lands before the v3.1 disk rebuild (task 9.2), not after. The snapshot's term
  scan passes on the result.
- **Why:** VP15's direction for the image files: no internal host names in files that go out verbatim. A missing
  variable fails loudly instead of calling a host that a reader can't reach.
- **Tests** (task 12.3): `run` and `run-v2` with the variable unset or blank (one stderr line, empty stdout, nothing
  sent or written); no host name in the script; the memory run; `GatewayJudge` and `judge_from_env`.

### VP26. `pofctl --v3 attempt` (decided, owner, 2026-11-24, Q4)

**Decision:** `pofctl --v3 attempt --bounty B` replaces the solver guide's `cast send <race> "attempt(uint256)"`.

- **Arguments:** RaceV3's `attempt(uint256 bounty)` takes only the bounty, so the command takes `--bounty`, as
  `pledge` and `submit` do (v2's `solver attempt --bounty` stays). It names no issue or commit.
- **Checks first,** each refusal with its reason and "Nothing was sent", as `draw` does:
  - the bounty is open;
  - a fix's claim at the price on offer fits the solver's room (over it, the commit would be refused, D29, so the
    attempt would only spend gas and the fee);
  - the wallet holds the attempt fee.
- **Sends:** if `attemptFee` is above 0, the fee coin is approved with VP17's wait for the allowance and one retry on
  an allowance refusal. Then `RaceV3.attempt`. On Sepolia the fee is 0, so nothing is approved.
- **Prints:** the claim, the share (rising or locked), the room and the fee; each transaction's hash and block; and the
  next step (`pofctl --v3 submit`). `--json` has `tx`, `block`, `txs`, `lockBps`, `locked`, `attempting` and `next`.
- **Docs:** the guide's attempt block uses the command. The guides keep no cast fallback elsewhere (`draw` replaced its
  cast form outright), so none is kept here.
- **Integration:** the Radicle set's funded fix runs `pofctl --v3 attempt` before `submit` (one more process and
  transaction).
- **Why:** the guides drive every other step with pofctl, which checks before sending, explains refusals and prints
  transactions (VP17). The attempt was the last raw `cast send` in a solver's path.
- **Tests** (task 12.4): a free attempt (its transaction, JSON and next step); a fee with the allowance wait; the
  allowance retry; an allowance already there; the three refusals; the parser and `--json`.

### VP27. The wallet's nonce never goes backwards (2026-11-24, from a live Sepolia validator)

**Evidence:** on 2026-11-24 v2's node (the live v3 image, `oracle/rpc.py`'s `Wallet.send`) registered through
PublicNode, a load-balanced public RPC. Its `approve` mined at nonce 0; `register` was then signed with
`eth_getTransactionCount(addr, "pending")`, answered by a backend that hadn't seen the approval, so with nonce 0 again.
`eth_sendRawTransaction` was refused; the message matched `ALREADY_SENT`, so the send counted as maybe sent and waited
60 s for a receipt no node had ("no receipt for 0x… after 60s"; Infura didn't know the hash either). A reboot minutes
later registered.

**Decision:**

- **Monotonic nonce:** `Wallet` remembers the next nonce after each send a node accepted, called already known, or
  mined, and signs with max(that, the pending count). Within a process a stale backend can't hand back a used nonce.
- **A taken nonce isn't "maybe sent":** `NONCE_TAKEN` matches "nonce too low" (and Infura's, Alchemy's and Hardhat's
  forms), Besu's `NONCE_TOO_LOW`, Nethermind's `OldNonce`, "replacement transaction underpriced" and "nonce has already
  been used"; `SAME_TX` matches "already known", "already imported" and "known transaction" (`ALREADY_SENT` is both).
  - `SAME_TX` with no other hash in the message: the node has these bytes, so the send waits for them, as before.
  - Otherwise, if the chain knows this hash (a receipt or `eth_getTransactionByHash`), it waits for it.
  - Otherwise, for bytes signed in this send that never went out, the nonce went to another transaction: the cached
    bytes are dropped, the remembered nonce moves past the refused one, and the call is signed again (a fresh
    estimate, price and count), at most `NONCE_RETRIES` (3) times; then an `RpcError` (not `Unavailable`) names the
    nonce, the account and the RPC host in `oracle.redact.shown_url`'s form, and says nothing was sent.
  - Bytes that may have gone out before (an accepted send, or a lost answer) keep the old rule: maybe sent, waited for,
    and signed afresh by a later call if no receipt comes. A stale lookup can't make them run twice.
- **A dropped transaction:** while waiting, after `DROPPED_AFTER_S` (20 s) with no receipt and no transaction by that
  hash, the same bytes (same nonce, same hash) are sent once more. A copy that is pending elsewhere is the same
  transaction, so this can't run it twice.
- **Trade-off:** a remembered nonce whose transaction every pool dropped leaves a gap until the dropped send's re-send
  or the process restarts (the count starts from the chain again). Its call's bytes stay cached and the next pass of
  the same call sends them again.
- **Image file:** `oracle/rpc.py` is in the node image, so this lands before task 9.2's disk rebuild.
- **Tests** (task 12.6, `tests/test_rpc_retry.py`'s `StaleNonces`, a fake load-balanced chain): a stale pending count
  refused, then signed again past it; the nonce monotonic across two sends with a stale count between; a clear failure
  after the cap, with no key in it; other providers' refusals and "already known" with another hash; a true duplicate
  (same bytes twice, pending) waited for; its own mined copy refused as nonce too low waited for; a dropped transaction
  sent once more with the same bytes. Each of the five new behaviours failed before the fix (the dropped one with the
  live message, "no receipt … after 60s"); the two duplicate tests guard the kept behaviour. `Transactions`'s
  spent-nonce test now loses the first answer, the case the old rule still covers.

### Parameters

| Name | Value | Where | Why |
|---|---:|---|---|
| `ROLL_WORK` | 40 | FeesV3 | worst part ≈6.8M under 8037 at 3 posters (VP3) |
| `PAY_SHADOW_GAS_FLOOR` | 600,000 | node | ≥ 2× the paying branch (VP7) |
| `GIVE_UP_S` | 86,400 s | node | a day of non-gated refusals, not 50 passes (VP6) |
| `BACKOFF_BASE_S` / `BACKOFF_MAX_S` | 30 s / 3,600 s | node | one estimate per state, not per pass (#314) |
| `ORACLE_POLL` | 12 s Sepolia, 2 s devnet | node | one block (VP6) |
| `ORACLE_KEEPER_EVERY` | 60 s Sepolia, every pass devnet | node | keeper calls aren't deadline-bound |
| `ORACLE_TX_POLL` | 4 s Sepolia, 0.4 s devnet | node | ≈3 looks per 12 s block |
| `ORACLE_KEEPER_BUDGET` | 300 calls a pass | node | bounds a pass under spam (F13) |
| `RATE_PAUSE_MAX_S` | 600 s | node | the longest keeper pause on a 429 without Retry-After |
| `ROLL_PARTS_PER_PASS` | 10 | node | a period closes in a pass or two (VP8) |
| `ORACLE_KEEPER_MAX_TX_HOUR` | 60 | keeper-only | the gas guard (VP10) |
| `ORACLE_POLL` / `ORACLE_TX_POLL` (keeper-only) | 120 s / 3 s | keeper-only | the seed host's values: a free RPC tier's credits (VP10) |
| `DEFAULT_RETRIES` / `RETRY_AFTER_MAX_S` | 3 / 30 s | `Rpc` | a 429 doesn't fail a command at once (VP19) |
| `NONCE_RETRIES` / `DROPPED_AFTER_S` | 3 / 20 s | `Wallet` | a stale pending count recovers; a dropped transaction is sent once more (VP27) |
| `APPROVAL_POLL_S` / `APPROVAL_WAIT_S` | 2 s / 60 s | pofctl | the approval seen before the next send (VP17) |
| `DRAW_GRACE_BLOCKS` | 25 (≈5 min) | watcher | a running keeper draws first (VP9) |
| `DRAW_STAGGER_MINUTES` | 10 | watcher | usually one host wakes |
| `DRAW_MAX_STARTS` / `DRAW_READS_MAX` | 1 / 20 | watcher | bounded starts and reads |
| `gasOverhead` / `gasAllowance` / `maxGasPrice` | 500,000 / 1,000,000 / 1 gwei | v3.1 plan | VP13 |

**The simulation:** none of these is a market or incentive parameter, and the incentive simulation has no gas, RPC or
keeper model. They are tested by Foundry (F1, F2, F8, the hold), the node's and the watcher's unit tests, and the
integration sets (task 8). F1 and F8 remove a lock and a griefing lever; they change no payoff the simulation measures.

## Risks / Trade-offs

- **[F1's rule makes fewer validators drawable for older checks]** → only for checks opened before a new family's first
  price, and only for that family. At launch (one family) nothing changes. Liveness after a new family's first price:
  older checks draw from the families priced at their opening, as their deposits were sized for.
- **[The hold's price test (VP1) keeps more lone verdicts held]** → only where a later-priced family would have
  counted; those verdicts would otherwise become final with a challenge that can't be seated. The gas of
  `challengersReady` grows by two static calls per scanned validator; measured in task 1.8.
- **[More roll transactions]** → about 5 a period at launch, each bounded; the keeper loops (VP8).
- **[The watcher wakes hosts for nothing]** → only past the grace and the stagger, once a check, under the fuse; with a
  keeper running it never fires. Watch the kit's starts after v3.1.
- **[Gating reads the wrong field and never sends a due call]** → each gate is unit-tested against the contract's rule,
  and the integration sets run with the new keeper only (no harness keeper doing the work).
- **[Removing the private terms breaks a default]** → each default either becomes required with a clear error or a
  public value; `bash scripts/check.sh` and the integration sets run on the cleaned tree; the snapshot's dry run
  reproduces the new image.
- **[The keeper-only key on any chain is misused]** → it can only make calls anyone may make; the address check and
  the hourly guard bound a wrong or leaked key to gas.
- **[A verdict comment leaks sealed evidence]** → only the outcome before the bounty settles; the reason only for a
  non-hidden registration check, or after the bounty is paid or closed (VP18).
- **[A key already printed]** → redaction stops new leaks; the printed key is rotated (VP20, task 10.0).
- **[Size margins]** → none of RaceV3, its Annex and Endings, Panels, PanelsJudge or PanelsVerdict changes; FeesV3,
  Validators and the library keep ≥ 512 B (task 1.8).

## Migration Plan

1. #323 and #324 merge (task 0.1).
2. Contracts and Foundry tests (task 1); keeper (2); watcher (3); pofctl (4); the image files (5); the deploy plan (6);
   docs and guides (7); integration (8).
3. On the owner's go, the seed host's keeper-only node moves to the merged keeper code on live v3, the owner's genesis
   validator gets `ORACLE_LIST_PRICES={}` (its own keeper stays on, decided 2026-11-23), and the printed Infura key is
   rotated (task 10.0).
4. rc4 with #310 and #311: the new disk, the local and AWS runs, the real-model run (task 9, each on the owner's go).
5. The v3.1 deployment (task 10) and the Radicle hand-over (task 11, #310's RB12), each on the owner's go.

**Rollback:** before step 5, v3 stays live and nothing on-chain changed; the keeper-only node can go back to its
previous directory (the runbook keeps it). Keyless contracts are never rolled back; v3.1 is simply not handed over.

## Decided (owner, 2026-11-23)

The open questions of the first draft, all decided as recommended:

- **Q1** (VP16): the seed host's keeper is launch infrastructure, named in the v3.1 plan and record with its cost
  line: about $0 (the existing seed) plus small Sepolia gas.
- **Q2:** F7's HOLD_K design question and F6's D29 change stay separate decisions, outside this change.
- **Q3** (VP15): the snapshot's verbatim exemption code is removed when v3 sunsets.
- **Confirmed:** the price test in `challengersReady` (VP1), and the watcher's draw duty on by default (VP9). The genesis
  node keeps its own keeper on.

## Decided (owner, 2026-11-24)

Four follow-ups to the polish, each decided as recommended:

- **Q1** (VP23): the watcher keeps a drawn check until it is final, and remembers wakes per round.
- **Q2** (VP24): one draw-and-signal rule for the keeper and `pofctl --v3 draw`.
- **Q3** (VP25): `MODEL_GATEWAY_URL` is required by `scripts/judge_run.py`, with no internal default.
- **Q4** (VP26): `pofctl --v3 attempt` in place of the guide's `cast send`.

From the live Sepolia registration the same day (not a question to the owner): VP27, the wallet's nonce never
goes backwards, and a taken nonce is signed again.

## Open Questions

None.
