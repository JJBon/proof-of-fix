# Can challenges be drawn at 7 and 15 validators? v1 (proof-of-fix#251; 2026-11-20)

**What this is:** a reading of `contracts/src/v3` at main `223ff45`, with each case run in a Foundry test that was not committed (the pinned image, `scripts/contracts.sh test`, production windows). No contract was changed. Each line below says whether it was **tested** or comes **from reading**.

**Why:** the devnet report's finding 9 (#281, branch `proof-of-fix-251-devnet-stalls`) shows that a panel of 7 out of 7 validators leaves nobody to audit it. It also suggested, from reading only, that a challenge of such a panel can't be drawn. L16 plans 7 launch validators, with 15 as the target, all run by the owner.

**The family plan isn't written down.** L16, the validator kit and #253 don't say which model families the launch validators run. #253's budget comment says "the seated family" (one family), and report v6 simulated one family. So every table covers 1, 2 and 3 families.

## In brief
- **Bounty size makes no difference up to $125.** A $250 bond is `BOND_FACTOR` (2) × $125, so every validator is eligible for every tier ($10, $25, $50, $125). The limit for k = 7 at level A is $625, so the k table never lowers k for these bounties. k depends only on how many validators there are and on the caps.
- **At n = 7 a challenge (or a test dispute) of a k = 7 verdict can never get a fresh panel.** D4 needs 7 validators outside the panel, and there are none. D27's second draw saves it only while fewer than 3 families are *known and seated*. With 3 families it works only until each family has had one verdict reach finality. After that, every challenge waits forever. **Tested.**
- **Even when D27 applies at n = 7, it is fragile.** The second draw must seat all 7 validators, so one paused, under-bonded or departed validator makes the challenge wait. One silent judge on the panel the second draw seated leaves that challenge panel open forever, because nothing can release it. **Tested.**
- **At n = 15 challenges are usually drawable but not always.** With 3 families the fresh draw failed in 10 of 60 tries, and those challenges waited for the registry to change. With 1 or 2 families it failed in 5 of 60, and the second draw seated a panel. **Tested.**
- **L19's invariant is broken by open challenges.** No release, abandon or time-out applies while a challenge is open (`challengeOpen`). Neither a waiting challenge nor a stuck challenge panel has a deadline.
- **Appeals never hang.** An appeal is a new submission, drawn like any other and covered by L19.
- **There is a precondition before any of this.** A panel of 7 at n = 7 needs the 7 validators spread over at least 3 hosts and 3 TEE types, with distinct operators. If all of them run the AWS SEV-SNP kit, the TEE cap holds k to 3 (**tested**). If they share one host value, k = 1 (**tested**): $125 bounties are never judged, and challenges of k = 1 verdicts never draw.

## The rules that decide it (file:line)
| Rule | Where |
|---|---|
| Eligible for a bounty means bond ≥ 2 × the bounty's tier step; steps $10, $25, $50, $125, … | `Validators.sol:70-74, 101-102, 777-787` |
| k is the largest odd number ≤ min(eligible count, `K_MAX` = 7). It steps down by 2 while the caps can't fill it, and stops below `kMin` | `PanelsDraw.sol:189-210` (k from n `196-198`, the stop `200`, "full: wait" `205`) |
| The largest bounty a panel may judge: level A k=1 $50 · k=3 $250 · k=5/7 $625; level B half of that | `PanelsDraw.sol:154-159` |
| Caps: 1 per operator (every k); ≤ (k−1)/2 per host and, while the family cap is on, per family (from k = 3); ≤ (k−1)/2 per TEE type from `teeFrom` | `PanelsDraw.sol:263-278` |
| `teeFrom` is 3 with ≥ 5 accepted TEE types, otherwise 5 (the launch accepts 3, D6) | `PanelsBase.sol:202-204` |
| The family cap is on while `seatedCount ≥ CAP_MIN_FAMILIES` (3). A family counts only once known (its first final verdict) and seated (not barred, not more than 5 points behind the best) | `PanelScores.sol:26-31, 219-221, 255-291`; `PanelsBase.sol:231` |
| Seats skip: the new panel, the challenged panel (`exPid`, including its auditors and replaced judges marked `GONE`), parties, validators full or paused (L16), unpriced or unseated families | `PanelsDraw.sol:229-256`; `PanelsBase.sol:295`; `PanelsJudge.sol:260` |
| Tries per seat: `DRAW_TRIES` (8) × the roster slack (1 when nobody has left) | `PanelsDraw.sol:168-172` |
| Challenge size `CHALLENGE_K`: 1→3, 3→5, 5→7, 7→7; `kMin` = 7 for k = 7, otherwise k + 2 | `PanelsBase.sol:336-338`; `PanelsVerdict.sol:146-147` |
| D27's second draw: only if `!famCap && k > 1`; original size; `exPid = 0` (original judges allowed); caps still apply | `PanelsVerdict.sol:154-167` |
| No panel: `ChallengeWaits`; `drawChallenge` then reverts `NothingChanged` until the registry's `epoch` changes | `PanelsVerdict.sol:136-140, 168-171` |
| Challenge, test dispute: both are `_file` → `Panels.challenge` → `drawChallenge` | `RaceV3Annex.sol:117, 126-131, 208-217`; `Panels.sol:330-338` |
| Appeal: a new submission (`_submit` → `panels.open`), a normal counted draw | `RaceV3Annex.sol:83-97`; `RaceV3Base.sol:467-468` |

## 1. What each case needs (bond $250 each; any bounty from $10 to $125)
Assumed layout: distinct operators, each validator on its own host, and 3 TEE types with at most 3 per type on a panel (the "spread" layout). Families are split as evenly as possible: 3/2/2 at n = 7 and 5/5/5 at n = 15. "Known" means the family has had a final verdict.

| n | Families | Verdict k | Challenge / test dispute needs | Appeal needs |
|---|---|---|---|---|
| 7 | 1 | 7 (all 7) | 7 fresh: outside the panel and its auditors, not parties, with room. No family cap. Second draw allowed (7 of all 7, original judges included) | a counted draw of 7 from all 7, original judges allowed |
| 7 | 2 | 7 | same as 1 family | same |
| 7 | 3, fewer than 3 known | 7 | same as 1 family (the cap is off, so the second draw is allowed) | same |
| 7 | 3, all known and seated | 7 at 3/2/2 (5 at 4/2/1, 3 at 5/1/1) | 7 fresh with ≤ 3 per family; **no second draw** | a draw of 7 with ≤ 3 per family |
| 15 | 1 | 7 | 7 fresh of the 8 left (7 of 7 if the verdict was audited). Second draw allowed | a draw of 7 from 15 |
| 15 | 2 | 7 | same as 1 family | same |
| 15 | 3, all known | 7 | 7 fresh of the 8 left, ≤ 3 per family; no second draw | a draw of 7 with ≤ 3 per family |

The size of a challenge panel never depends on the bounty here. A smaller verdict panel (k = 5 or 3) still needs a challenge panel of 7 or 5 (`kMin = k + 2`), so the 3/1/1-style splits are worse, not better.

## 2. Can it be drawn, and what happens if not
| n | Families | Challenge / test dispute | What the code does | Evidence |
|---|---|---|---|---|
| 7 | 1 or 2 | the fresh panel never; the second draw yes, when all 7 are drawable and have room | fresh fails (`PanelsDraw.sol:200`), then the second draw seats the original 7 (`PanelsVerdict.sol:160-166`, `SecondDraw`) | tested (1 and 2 families) |
| 7 | 1 or 2, one validator paused, under the floor or gone | no | the second draw fails → `ChallengeWaits` (`:168-171`). It is retried only after a registry change, and a capacity change isn't one: un-pausing still reverts `NothingChanged` (`:137`) | tested (pause, then un-pause) |
| 7 | 1 or 2, one validator full (L16) | not now | returns without a state change; retried from the same seed (`:153`, `:164`) | from reading |
| 7 | 3, fewer than 3 known | yes, by the second draw | as for 1 family | tested (2 of 3 known) |
| 7 | 3, all known | **never** | `ChallengeWaits`. Each registry change re-targets (`:136-140`) and fails the same way, until at least 14 validators can be drawn | tested (5 re-targets; `finalize` reverts `NotReady` a year later) |
| 15 | 1 or 2 | yes | fresh panel 55 of 60; the second draw for the other 5 (failures from sampling and the TEE cap) | tested (60 verdicts each) |
| 15 | 3, all known | usually | fresh panel 50 of 60; the other 10 → `ChallengeWaits` until a registry change gives a new seed | tested (60 verdicts) |
| 15 | any, verdict audited (1 in 10 at k ≥ 3) | less often | the auditor is excluded, so all 7 remaining fresh validators must be hit in 56 tries: that fails about 14 % of the time on sampling alone; then it goes to the second draw (1–2 families) or waits (3 families) | from reading, plus a Python estimate |
| any | — | appeal | a normal counted draw. If it can't fill, the submission waits with `retryAt` and is released after `MAX_REDRAWS` (L19) | from reading |

**The layout precondition**, which applies before any of the rows above:
| Layout of the 7 | Verdict k | Effect | Evidence |
|---|---|---|---|
| all but one on SEV-SNP (one TEE type) | 3 | the TEE cap from k = 5 allows ≤ 2 per type; challenge needs 5 fresh of 4 → second draw (1–2 families) or wait forever (3 families) | tested |
| all but one on one host value | 1 | the $125 bounty waits (k = 1's limit is $50) until L19 refunds it. A $50 verdict's hold ends anyway, because `challengersReady` doesn't check the caps (`PanelsDraw.sol:320-339`); its challenge of 3 needs one per host → waits forever, and k = 1 gets no second draw (`:154`) | tested |
| one operator account for all | 1 | as for one host: the operator cap applies at every k (`PanelsDraw.sol:270`) | from reading |

The spec counts the host per cloud ("One technology in two clouds … the host cap counts them apart", `validator-admission` spec). Read that way, the owner's AWS-only validators share one host.

## 3. Does D27 rescue n = 7?
- **With 1 or 2 families: yes, but only as a re-vote.** The second draw seats the same 7 judges who gave the verdict. As D27 says, it ends the wait but corrects nothing. It needs every one of the 7 to be drawable with room at once.
- **With 3 families: only at the start.** `famCap` reads `seatedCount`, which counts only families that have had a final verdict (`PanelScores.sol:26-28, 219-221`). Once all three have one, D27 is off for good, and every challenge or dispute of a 7-of-7 panel waits forever. It switches back on only if a family becomes a contender or is barred, and then that family's validators can't sit either.
- **D27 doesn't apply to k = 1** (`PanelsVerdict.sol:154`), which is the case the one-host and one-operator layouts produce.

## 4. Paths that never end (L19's invariant)
L19 says every submission is drawn with a live deadline, waiting with a scheduled redraw, final, or refunded (`Panels.sol:98-105` repeats it). A verdict with an open challenge is none of these:
1. **A challenge waiting for a panel** has no deadline and no scheduled retry. It moves only when the registry changes (`PanelsVerdict.sol:136-140`), unlike a waiting submission's `retryAt` (`:55`). At n = 7 with 3 known families, a retry never succeeds. Elsewhere anyone can force a registry change with a 1 micro-coin `topUp` (devnet finding 4).
2. **A challenge panel that is drawn but has an empty seat.** `release` handles only counted and audit panels (`PanelsJudge.sol:155`). `advance` and `refill` find nobody new (`:270-299`), and the reveal window never opens on a panel that isn't full (`:348`). At n = 7 a single silence on a second-draw panel causes this; at n = 15, a second silence (or the first, if the verdict was audited). **Tested at n = 7.**
3. **Nothing else ends it either.** `finalize` refuses while a challenge is open (`PanelsVerdict.sol:213`), as do `releaseAudits` (`PanelsJudge.sol:199`) and `abandon` (`:214`). `RaceV3.timeOut` applies only before a verdict (`RaceV3Endings.sol:173`).
4. **What stays locked:** the bounty (neither paid nor refunded), the challenger's stake and cover (`RaceV3Annex.sol:211-214`), and every original judge's bond, since `withdraw` refuses while `openChallenges` isn't 0 (`Validators.sol:420`).

Appeals have no such path.

## 5. The smallest changes that would make challenges drawable at n = 7 (options, not chosen)
| Option | Change | Gains | Costs |
|---|---|---|---|
| A. `SECOND_PANEL` "always" | drop `!c.famCap` at `PanelsVerdict.sol:154` | 3 families at n = 7 drawable whenever all 7 are up; report v4's last 0.3 % close | reverses the owner's 2026-11-19 choice; the second draw is still a re-vote by the same 7 (the family cap still applies to it) |
| B. Launch with 1 or 2 families | no code; record it in L16 | D27 applies throughout | one-family panels (D20's prompt-injection trust point); challenges only re-vote; the all-7 fragility stays |
| C. A smaller verdict panel and a same-size challenge | cap k so that at least k validators stay outside (at n = 7: k = 3, 4 left over), and let the challenge's `kMin` be k instead of k + 2 | a fresh panel that can correct; audits drawable too (finding 9) | k = 3's windows are longer (24 h against 6 h at level A); a challenge is no longer "larger"; touches D2 and D4 |
| D. A deadline for challenges | after `STUCK_GRACE` × `MAX_REDRAWS` without a panel, or with a panel stuck, the challenge lapses (stake back, verdict stands) or the submission is released (refunded) | restores L19's invariant in every case | doesn't make anything drawable; "lapse" leaves 7-of-7 verdicts unchallengeable, including D21 disputes; "release" lets anyone with a stake force a refund |
| E. `release` for challenge panels | allow `Kind.Challenge` at `PanelsJudge.sol:155`, back to a waiting challenge | ends the stuck-panel hang (4.2) | a waiting challenge still needs D or a retry clock |
| F. A retry clock for waiting challenges | a `retryAt` like waiting submissions | ends waits caused by pauses and bad sampling luck (n = 15) | no help where no panel can ever be drawn |
| G. More validators | at least 16–17 spread validators, so 7 fresh remain after an audit | no code | model budget (#253's $30–50 a month total) |

Whatever is chosen, the layout precondition stands. A panel of 7 needs ≥ 3 hosts, ≥ 3 TEE types (≤ 3 each) and one operator account per validator. Otherwise the launch runs at k = 3 or k = 1, and the k = 1 hold's readiness check, which ignores the caps, lets windows start whose challenges can't be drawn.

## Decided (owner, 2026-11-20)
The owner decided on all three questions the same day. The rules are in `openspec/changes/proof-of-fix-251-testnet-launch/design.md` L23–L25, in the specs (`deployment-binding`, `judge-panels`, `panel-liveness`), and in tasks 3.22–3.27. No contract had changed then; contract batch 4 built them (the last section).
- **L23, caps as deployment settings, loose on Sepolia.**
  - The operator, host and TEE-type caps become `PanelRules` constructor settings, each `Strict` or `Off`. They are fixed at deploy, keyless and in the record. Mainnet defaults to `Strict`; Sepolia sets them `Off`.
  - The family cap is unchanged.
  - New trust point: one operator runs every launch validator.
  - This settles this report's layout precondition.
- **L24, launch panels of 3.**
  - `kTop` is a deployment parameter: 3 on Sepolia, 7 by default. The constitution tier keeps 7.
  - Challenges and test disputes draw a fresh panel of the challenged size (`challengeSize` `Same`). A k = 1 verdict's challenge keeps 3 judges, and D27 stays as the fallback.
  - The k table is unchanged: k = 3 judges up to $250 at level A and $125 at level B. The windows become 24 h (A) and 48 h (B).
  - At 7 validators, 4 stay outside every panel, which is option C of section 5. That makes the stuck-audit refund (finding 9) practically moot at the launch.
- **L25, challenges always end.** This combines options D, E and F of section 5.
  - Each challenge has `CHALLENGE_DEADLINE` (proposed 120 h, a `Windows` field).
  - Past the deadline, a challenge with no panel lapses: the verdict stands, and the stake and cover come back whole.
  - A stuck challenge panel is released as L19 releases counted panels.
  - A waiting challenge is retried at `RETRY_DELAY`.
  - L19's invariant is restated to include challenges.

## After contract batch 4: the cases again, tested (2026-11-20)
Contract batch 4 (tasks 3.22–3.27) built L23–L25. Every case above is now a Foundry test, at 7 and 15 validators bonded $250 (spread: each its own operator account and host, three TEE types), bounties of $10, $25, $50 and $125, and 1, 2 and 3 families (3 before and after all are known), under the strict settings (#132's: every cap `Strict`, `kTop` 7, `Larger`) and the launch's (every cap `Off`, `kTop` 3, `Same`): `contracts/test/v3/DrawabilityCasesV3.t.sol`, one `CASE` line a case in the log (`scripts/contracts.sh test --match-contract DrawabilityCasesV3Test -vv`). The table below is regenerated from those lines; the 64 lines are identical with production windows and with `POF_TEST_WINDOWS=minutes`. The bounty made no difference in any case, so each row stands for its four bounties.

| n | Families (known) | Rules | k | Challenge | Test dispute | Appeal k |
|---|---|---|---|---|---|---|
| 7 | 1 (1) | strict | 7 | D27's second draw, counted | second draw, counted | 7 |
| 7 | 2 (2) | strict | 7 | second draw, counted | second draw, counted | 7 |
| 7 | 3 (2 known) | strict | 7 | second draw, counted | second draw, counted | 7 |
| 7 | 3 (3 known) | strict | 7 | no panel: **lapses at CHALLENGE_DEADLINE** (before: waited forever) | lapses | 7 |
| 7 | 1, 2, 3 (any) | launch | 3 | a fresh panel of 3 from the 4 outside, counted | fresh 3, counted | 3 |
| 15 | 1, 2, 3 (any) | strict | 7 | fresh 7, counted | fresh 7, counted | 7 |
| 15 | 1, 2, 3 (any) | launch | 3 | fresh 3 from the 12 outside, counted | fresh 3, counted | 3 |

Every challenge and dispute ended (counted or lapsed); none stayed open. No random audit fell due on these 64 verdicts (their seeds); audits are tested on their own below.

**The "tested" marks of sections 2 and 4, checked against the decisions:**
- *7 validators, 1–2 families, the second draw* (tested): unchanged under the strict rules (D27, the fallback); under the launch's rules the challenge gets a fresh panel of 3 instead.
- *7 validators, one paused, the challenge waits; un-pausing didn't redraw it* (tested): now redrawn at its retry time (`PanelRulesV3Test.test_aValidatorUnpauses`, scenario "A validator un-pauses").
- *7 validators, 3 families all known, waits forever* (tested): lapses at CHALLENGE_DEADLINE, the verdict standing and its window resumed (`test_noPanelByTheDeadline`, and the table above).
- *15 validators* (tested): every case drew a fresh panel; where a sample fails, the retry clock redraws it with a fresh seed (`_endChallenge`), and a challenge with no panel lapses at its deadline.
- *A silent judge on a second-draw panel at 7, never released* (tested): released at its reveal deadline plus STUCK_GRACE, the silent seat slashed; before the deadline the challenge waits again, after it it lapses (`test_aSilentJudgeOnAChallengePanelWithNoReplacement`).
- *The layout precondition* (tested): with every cap `Off`, one operator account, one host value and one TEE type give a panel of `kTop` (`test_theOwnersValidatorsFillPanelsOnSepolia`); with every cap `Strict`, one host or one operator account still gives k = 1 and one TEE type k = 3, but the k = 1 hold now counts challengers under the caps, so the verdict stays held instead of starting a window its challenge can't be drawn for (`test_theOwnersValidatorsOnAStrictDeployment`, `test_oneHostLayout`, `test_oneTeeTypeLayout`).
- *Audits at n = 7* (finding 9): with panels of 3, an audit that falls due is drawn from the 4 outside (`test_theSepoliaLaunchAt7Validators`), and an audited verdict's challenge falls to D27's second draw when one of the 3 left can't sit (`test_anAuditedVerdictsChallenge`).
- *L19's invariant with challenges*: `LivenessInvariantV3`'s `ChallengeLiveness{Strict,Launch}{7,15}Test` apply challenges, test disputes, silences, pauses, joins and leaves in any order and check the restated invariant at every step, and that every submission ends final or refunded with no challenge outliving its deadline without a panel.
