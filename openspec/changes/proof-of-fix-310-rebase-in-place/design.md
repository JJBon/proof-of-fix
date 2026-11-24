# Design

## Context

- **Why:** see proposal.md. The behaviour is in the deltas to `bounty-market`, `checking`, `challenges`,
  `contribution-lifecycle` and `reputation`. This document covers how, the parameters, the sizes and gas, the numbers,
  and the move of the Radicle repository from v3 to v3.1.
- **Numbering:** the decisions are numbered **RB1–RB13**. That avoids a clash with #132's D-numbers, #251's L-numbers
  and the R1–R4 risk rows of `reports/glamsterdam-runtime-v1.md`.
- **Base commit:** everything marked "observed" was read at `origin/main` b61fa63.

### What v3 does today (observed)

| Step | Where | What happens |
|---|---|---|
| Seal | `RaceV3.commit`, `RaceV3.sol:295-307` | Seals keccak256(fix, base, salt, solver) with the deposit, through `_newCheck` (`RaceV3Base.sol:460-481`) and `_submit` (`:483-490`, opens a D29 claim) |
| Judge | `oracle/node_v3.py:507-547` (`_find_patch`) | A judge takes the Radicle patch revision that opens the seal. It **refuses a revision whose base isn't `Heads.head`** (`:539-541`), and the fix is failed as "stale" |
| Count | `RaceV3.result`, `RaceV3.sol:319-345` | Pays the counted judges by the meter. `_decided` → `_decide` → `_win` sets `Won` and `mergeBy = day + mergeDays` (`RaceV3Base.sol:493-519`) |
| Claim | `RaceV3.claim`, `RaceV3.sol:351-375` | Opens the seal and stores `s.fix` and `s.base`. Starts award epoch `e` (`Award{winner, fix, sub, closed, earned, merged}`, `RaceV3Base.sol:127-134`) and sets `Merged`. The head doesn't move (L9) |
| Window | `PanelsVerdict.sol:370-378` (`_startWindow`) | `CHALLENGE_WINDOW[k, level]`. In the deployment record (`contracts/deployments/sepolia-v3.json` `windows.challenge`): level A k = 1/3/5/7: 168/24/12/6 h; level B 336/48/24/12 h; level C 336/72/48/24 h. Seal 2 h, reveal 1 h. `kTop` 3 (L24) |
| Merge | `RaceV3.merge`, `RaceV3.sol:380-394` | Needs the verdict Final and a pass. Calls `heads.move(repo, s.base, a.fix, …)` (`:389`) |
| Stale base | `Heads.move`, `contracts/src/v2/Heads.sol:91-106` | `if (base != current) revert StaleVerdict` (`:98`). The whole merge reverts |
| Expiry | `RaceV3Endings.mergeExpired`, `RaceV3Endings.sol:178-196` | Unclaimed after `mergeBy`, or claimed and unmerged `mergeDays` after its finality: the award closes with nothing earned, and the bounty reopens (`_reopen`, `RaceV3Base.sol:515-519`) |
| `mergeDays` | `contracts/script/DeploySepolia.s.sol:400` | 14 (deployment record `constructorArgs.RaceV3.config.mergeDays`) |
| Instalments | `_earned`, `RaceV3Base.sol:311-320` | Counted from the award's own sub's finality, and only once merged |
| S6 | `_settle`, `RaceV3Base.sol:416-419` | When paid: the winner's `charged` (its metered checks) is refunded from the pot's rest |
| Reversal | `RaceV3Annex._sync`, `RaceV3Annex.sol:296-330` | A pass reversed in its window closes the award and reopens the bounty. A sub that isn't `bt.winner` returns early (`:317`) |
| D21 reward | `RaceV3Annex.settleChallenge`, `RaceV3Annex.sol:172-174` | The reward comes from the pot only when the reversed sub is `bt.winner` |
| Appeal (D24) | `RaceV3Annex.appeal`, `RaceV3Annex.sol:83-97` | A failed sub of an **open** bounty is re-submitted once, with the same commitment. Its claim replaces the old one |

### v2's rebase path (observed)

`RaceV2.merged` (`contracts/src/v2/RaceV2.sol:259-282`):

- the oracle quorum signs a merge verdict naming the winning submission;
- its `v.fix` may be the rebased commit, checked on `v.base`;
- `heads.move` either succeeds or the whole call reverts, and the winner "keeps its place and its locked share";
- `paidFix` covers both commits (`:278-279`).

What carries over to v3:

- the winner keeps its place;
- a second check on the rebased commit;
- `paidFix` on both commits;
- the rule that only the winning submission's award can merge.

What doesn't carry over: v3 has no quorum-signed merge. The second check has to be a Panels check, with its own
finality (L9).

### Sizes, measured

Measured with `scripts/contracts.sh sizes` (pinned Foundry 1.8.5, solc 0.8.37) at b61fa63. The EIP-170 limit is
24,576 B; the EIP-3860 limit is 49,152 B.

| Contract | Runtime (B) | Runtime margin (B) | Initcode margin (B) |
|---|---:|---:|---:|
| RaceV3 | 22,612 | **1,964** | 16,718 |
| RaceV3Annex | 22,362 | **2,214** | 23,633 |
| RaceV3Endings | 21,845 | **2,731** | 24,356 |
| Panels | 19,026 | 5,550 | 26,452 |
| Validators | 22,908 | 1,668 | 17,992 |
| FeesV3 | 18,026 | 6,550 | 28,889 |
| SolverBook | 3,707 | 20,869 | 45,188 |
| Heads (v2) | 1,091 | 23,485 | 47,246 |

## Goals / Non-Goals

**Goals:**

- A conflicting fix reaches the head about one cycle after the first, with no new trust: the rebased tree is judged
  in full.
- Port v2's "winner keeps its place" to v3's Panels, L9 and D21.
- Stay within EIP-170 without touching Panels, Heads, FeesV3 or Validators.

**Non-goals:**

- **#311 (early reveal):** its own change. It composes with this change (RB9) and ships in the same v3.1 release
  candidate (O6, decided by the owner on 2026-11-23).
- **#306's `next` branch, and stacked fixes.** Observed: today a fix based on a claimed, unmerged fix is refused by
  the judges as stale (`oracle/node_v3.py:539-541`). So #306's section 3.2a premise ("v3 already accepts a fix whose
  base is a claimed but unmerged fix") holds for the contracts but not for the node. That is for #306's follow-up.
- **Seating the original panel's members** (RB3 option A).
- **Shorter windows** (#306 stage v3.2).

## Decisions

### RB1. Who may rebase: the solver first, then anyone (question 1)

The options:

- **A. The solver only.**
  - Simplest and smallest.
  - But a solver who has gone silent holds the bounty until the deadline. The issue asks for "by the solver or
    anyone".
- **B. Anyone, at any time.**
  - The fastest.
  - But a stranger can submit a broken rebase first. If a failed rebase reopened the bounty, that would be a cheap
    griefing attack on a winner (the cost is one metered check). If it didn't, one stranger could still occupy the
    single rebase slot (RB4) with slow failing checks.
- **C (decided, O1). The solver at any time; anyone else once `REBASE_GRACE` has passed since the head last moved.**
  - "Since the head last moved" is `Heads.head(repo).movedAt`, already stored (`Heads.sol:101`).
  - A third party's failed rebase ends only that check (RB5).

**Who is paid under C:**

- The award stays the winner's: its fix was approved, and the conflict isn't its fault.
- A third party whose rebase merges gets `REBASE_SHARE_BPS` of the award's price. It comes from the pot's rest at the
  bounty's payment, after the award and the finder's fee and before the S6 refunds, capped by what the pot holds.
  That puts it beside S6 in `_settle`.
- The pot's rest is the funders' unsold share (the locked price is below 100 % until the rise reaches it,
  `startPriceBps` 5,000 and `riseBpsPerDay` 1,000 on Sepolia). So the funders pay the rebaser, and in exchange they get
  their fix weeks sooner.
- **Decided values (owner, 2026-11-23, O1):** `REBASE_GRACE` = 1 day, `REBASE_SHARE_BPS` = 1,000 (10 %, the same as D21's
  `EVIDENCE_REWARD_BPS`). Both are constants (no new `Config` field, so the deploy scripts keep their struct).
- **Fallback if RaceV3 can't fit the share (RB10):** a third party gets only the S6-style refund of its metered check
  (it rebases at no net cost, but with no reward).

**Decided (owner, 2026-11-23, O1): C**, with `REBASE_GRACE` = 1 day and `REBASE_SHARE_BPS` = 10 %.

### RB2. The rebase is opened, not sealed

- The race's sealing stops solvers copying each other's fixes while the bounty is open. A rebase has no race: the
  winner is fixed, and the approved fix is public on Radicle since its claim.
- So `rebase(b, fix, base, salt)` takes the commit and its base in the clear. The race computes the commitment
  keccak256(abi.encode(fix, base, salt, msg.sender)) itself and opens the Panels check with it.
- The node's `_find_patch` then works unchanged: it reads claim lines with a salt.
- It saves the separate claim transaction a sealed rebase would need.

**On-chain checks:**

- `bt.state == Merged`;
- the award is neither merged nor closed, and its original verdict is still a pass (Held, Window or Final);
- the original's `s.base` isn't the head;
- `base` is the head;
- `fix` is nonzero, differs from `a.fix` and isn't in `paidFix`;
- no rebase of this award is undecided;
- the caller is allowed by RB1;
- the claim fits the cap (RB7).

The check is opened at the original's `judged`, so Panels sizes the panel and the stakes as it did for the original.
That bounty is also the most the award can pay (`_priceNow`, `RaceV3Base.sol:303-307`).

**New state:**

- `Submission.rebaseOf` (the original's id);
- `Award.rebase` (the latest rebase check);
- a `Rebased(bounty, original, check, fix, base)` event.

**Option rejected:** a sealed rebase with a later opening. It needs a second transaction and gives no protection,
since the tree is public.

### RB3. What is re-checked, and by whom (question 2)

The options:

- **A. The original panel's members, where possible.**
  - It needs a "preferred seats" path in `PanelsDraw` (Panels has 5,550 B left).
  - It reuses judges whose identity and votes are public since their reveal, so a bribe is easier to aim.
  - The original seats may be offline or at capacity (L16), and then the fallback is a fresh draw anyway.
  - With `kTop` 3 and about 7 validators, a fresh draw overlaps the original panel often anyway.
  - **Not for v3.1.**
- **B (chosen; O2 decided). One fresh counted panel, by Panels' ordinary rules,** with shadows, random audits, challenges and
  D21, at the original's `judged`.
  - **The tests:** the checker runs as for any fix: protected paths from the base (L20; `oracle/node_v3.py:475-505`
    via `_test_config` and `_run_check`), twice (L22).
  - Because the base is the new head, `tests/` already holds the first fix's protected tests. That is what catches a
    semantic conflict that applied without a textual one.
  - **The model:** the judge's case (`case_for`/`_case`) for a sub with `rebaseOf != 0` carries the approved diff
    (from the original's `s.fix`/`s.base`, revealed at the claim), the rebased diff and `git range-diff`.
  - The rubric adds one question: is the rebased diff the approved fix adapted to the new base, with no unrelated
    change? A "no" fails it (`checking`, "The judges compare a rebase with the approved fix").
  - **Why it's cheap:** the case is short (the range-diff and the base's changes to the same files), so the meter
    charges fewer input tokens. The chain gas is that of any check (RB11).
- **C. Tests only, no model, when `git patch-id --stable` is equal ("clean").**
  - The cheapest option.
  - But passing tests don't catch a semantic conflict the tests don't cover, which is exactly the risk a rebase adds.
    Off-chain "cleanness" is also each judge's own claim.
  - **Decided (owner, 2026-11-23, O2): not in v3.1.** No shortcut re-check for clean rebases; a later deployment may
    revisit it once there is data on how often clean rebases are reversed.

**Semantic conflicts are caught three ways:**

1. the new base's protected tests (B);
2. the range-diff question (B);
3. after the count, a D21 failing-test dispute against the rebased tree (RB6).

### RB4. Timing: a full window of its own, run beside the original's (question 3)

The options:

- **A. Inherit the original's remaining window.** A rebase counted one hour before the original's finality would be
  final an hour later.
  - **The attack:** an approved fix is rebased into something else, the rebased tree slips past review, and its
    window is all but gone.
  - Rejected.
- **B (chosen; O2 decided). The rebase check has its own full `CHALLENGE_WINDOW[k, level]`**, as any Panels check does, so
  Panels needs no change.
  - It may be submitted while the original is still in its window.
  - `merge` needs both verdicts to be Final passes.
  - So the windows run side by side, and the second fix merges at max(original final, rebase final).
- **C. A shorter, rebase-only window** for clean rebases.
  - It needs a per-kind window in Panels, and it rests on the same unverifiable "clean" as RB3 C.
  - Not in v3.1 (O2, decided by the owner on 2026-11-23).

**Further rules:**

- **One rebase in flight.** At most one rebase check of an award is undecided at a time. A passed rebase that went
  stale again (the head moved once more) may be replaced.
- **Approved and then swapped.** The original's approval never transfers:
  - `merge` moves the head to the rebase's commit, using the rebase's verdict;
  - the original commit never becomes the head;
  - a rebased commit that differs from the approved fix beyond adaptation fails RB3's rubric.

### RB5. The award, the claim and the payout (question 4)

**The first fix to merge** (bounty A) is untouched. Its tests become protected tests that B's rebase must pass.

**The stale winner** (bounty B) keeps `bt.winner`, its award epoch and its price snapshot (`_priceOf`/`_touch`,
`RaceV3Base.sol:291-307, 434-443`). Its D29 claim follows RB7.

**`merge(b)` with a rebase** (`RaceV3.sol:380-394` extended):

- needs the original's verdict and the rebase's to be Final passes;
- calls `heads.move(repo, rs.base, rs.fix, b, orig, keccak256(abi.encode(address(panels), r)))`, so the head records
  the check that judged the tree now on it;
- sets `a.fix = rs.fix` and `paidFix` for both commits (v2's `RaceV2.sol:278-279`);
- calls `book.paid(orig, solver, judged)` and `book.closeClaim(r)`;
- emits `HeadMerged(b, epoch, r, rs.fix)`.

**Instalments:**

- `_earned` (`RaceV3Base.sol:311-320`) counts from `a.rebase`'s finality when the award was merged through a rebase.
  Invariant: `a.merged && a.rebase != 0` means it merged through `a.rebase`.
- So the tree on the head gets the full schedule. The alternative, counting from the original's finality, would pay
  some instalments for code that sat outside the head.

**Failure, reopening and the deadline.** All of this is in `mergeExpired` (`RaceV3Endings.sol:181-196`, extended; the
name is kept, so there is no new selector):

- **The solver's own rebase was counted as a fail and its base is still the head:** the award closes with nothing
  earned, the original claim closes, and `_reopen`. The rebase's base must still be the head. Otherwise a head that
  moved during the check (so the judges refused it as stale, `node_v3.py:539-541`) would count against the solver
  through no fault of its own. That fail only frees the slot.
- **A third party's fail, a withdrawal, a time-out or a release (L19):** frees the slot, and the award stays.
- **The deadline:** `mergeDays` from the later of the original's finality and the latest passing rebase's finality. A
  rebase submitted before the deadline and still undecided returns `NotYet`.

**Interplay:**

- Once the bounty reopens, the solver's failed rebase may be appealed under D24 (`RaceV3Annex.sol:83-97`): it has
  `bounty != 0`, `outcome == Fail`, and the bounty is open. The appealed copy joins the queue on the head it was
  judged on.
- `_reopen` lets a pass waiting behind the old winner win at once (`RaceV3Base.sol:518`), as today.
- **No reputation loss for a failed rebase** (a fail isn't a reversal). A passed rebase that is reversed costs its
  submitter (RB7).

### RB6. D21 disputes, challenges and #311 (question 6)

**A rebase check is an ordinary Panels check:** challenges, audits and D21 disputes apply in its own window.

| Case | Existing code | What happens |
|---|---|---|
| A rebase pass reversed (receipt challenge or D21) | `_sync` (`RaceV3Annex.sol:296-330`): `_penalize(r)` charges the rebaser's reputation (D29); outcome Pass→Fail; returns at `:317` because `bt.winner != r` | The award stays claimed; `mergeExpired` then treats it as a fail (RB5) |
| A D21 dispute upheld against the rebase | `settleChallenge`'s `won` (`RaceV3Annex.sol:172`) | Extended to `bt.winner == id \|\| awards[b][bt.epoch].rebase == id`, so the disputer is paid `EVIDENCE_REWARD_BPS` from the pot, as against a winning fix: catching a bad rebase protects the head just as much |
| A D21 dispute rejected | `settleChallenge` | Its stake goes to `s.solver`, which is the rebaser: the party whose delay it was |
| The original reversed in its window while a rebase is in flight | `_sync(orig)` | Closes the award and reopens the bounty as today. The rebase's result still pays its judges, and `finish` returns its rest. A passed rebase never merges, because `merge` needs `Merged` |
| `isParty` for a rebase check (`RaceV3.sol:226-235`) | — | Extended so the original solver is a party too (recused) when it isn't the rebaser |

**#311 (early reveal)** changes `_inRevealWindow` (`PanelsJudge.sol:388-392`). Rebase checks benefit automatically,
because they are ordinary panels. The shadow guard covers them the same way. Nothing here depends on #311.

**#314 (keeper backoff):** the keeper stops calling `merge` on a stale base. RB8 adds a pre-check, and #314's backoff
covers the rest.

### RB7. Claims and reputation (D29)

- Every rebase check opens a claim of the original's `judged` for its submitter (`book.openClaim`), refused over the
  cap.
- Third parties must fit the cap, because a rebase puts a tree on the head just as a fix does. That is D29's reason
  for the cap.
- The winning solver's rebase first closes its original claim, as `appeal` does (`RaceV3Annex.sol:93-94`), so the
  bounty counts once.
- At the merge, the bounty joins the **winner's** reputation (`book.paid(orig…)`). The rebaser's claim closes with no
  reputation gained.
- **Decided (owner, 2026-11-23, O3):** a third-party rebaser gains no reputation and doesn't count as an active solver
  (L6). L6's "active" is for fixes, and a rebase is a smaller contribution.

### RB8. Node, pofctl and Radicle patches

**The patch.** A rebase is a new revision of the same Radicle patch: `git push --force rad
<fix>:refs/heads/patches/<patch-id>` (forced: the rebased commit doesn't descend from the last revision; `refs/patches`
would open a new patch) with `patch.message` lines. Its description carries bot/logic's claim lines (`pr_body`: bounty, submission = the
rebase check's id, salt, solver = the rebaser).

- `_find_patch` (`node_v3.py:507-547`) already matches per revision on the claim lines and the commitment, and
  refuses a stale base. Unchanged.
- `RadicleFixes.revisions` lists every revision (`radicle_v3.py:95-105`).

**The judge** (`node_v3._fix`/`_case`): for a sub with `rebaseOf`, it fetches the original's commit (the same verified
fetch) and builds the range-diff case (RB3).

**The keeper** (`node_v3._keep`, `:758-817`):

- It discovers checks from `Committed` and `Registered` events (`:760`). It adds `Rebased`.
- Rebase checks get the same draw, signal, result, finish and release calls.
- `_merge` (`:906-919`) also handles a final passing `a.rebase`.
- It calls `mergeExpired(b)` when a rebase failed (RB5).
- Before `merge`, it compares the base with `Heads.head` and skips stale ones, which saves the reverting estimates
  #314 is about.

**The seat adapter** (`radicle_v3.py`, `radicle.decide_head`, `oracle/radicle.py:190-216`) doesn't change. The rebased
commit's base is the head, so the new head fast-forwards every delegate's `main`.

**pofctl** (`pofctl/v3cli.py`):

- `pofctl --v3 rebase --bounty B --patch <rebased commit> [--salt]` checks:
  - the state, the stale base and the new base == head;
  - the grace period for a non-solver;
  - the cap and the deposit's allowance.

  Then it sends `rebase`, and prints the patch update command and the claim lines.
- `merge`'s stale-base message (`:500-502`) and `submit`'s (`:408-409`) point to `rebase`.
- `status` lists rebases.

### RB9. Expected merge time (question 8)

**Model:**

- one cycle C = seal 2 h + reveal 1 h + the window W, as #306's spike section 1 counts it (draw and transaction
  latency left out);
- r = the solver's time to rebase.

**Without a rebase (today):**

- the second fix is final at about C;
- `mergeExpired` frees it `mergeDays` = 14 d (336 h) later;
- a fresh submission then needs another C.

**With a rebase:** the first merges at C, and the second at C + r + C.

| Panel (production windows, `sepolia-v3.json` `windows`) | C | Today: second fix on the head | With rebase | With rebase + #311 (count about 1.5 h, spike section 4) |
|---|---:|---:|---:|---:|
| k = 3, level A (the launch) | 27 h | ≥ 390 h (16.3 d) | 54 h + r (2.25 d) | 51 h + r |
| k = 3, level B | 51 h | ≥ 438 h (18.3 d) | 102 h + r (4.25 d) | 99 h + r |
| k = 1, level A (plus any hold) | 171 h | ≥ 678 h (28.3 d) | 342 h + r (14.3 d) | 339 h + r |
| k = 1, level B (plus any hold) | 339 h | ≥ 1,014 h (42.3 d) | 678 h + r (28.3 d) | 675 h + r |

- At the launch (k = 3, level A) a conflicting fix goes from at least 16 days to about 2.3 days: 7.2 times faster
  with r = 0, saving 336 h.
- When the solver is silent, a third party adds `REBASE_GRACE` (24 h).
- When the second fix was submitted Δ after the first, it merges at max(C + Δ, C + r + C).
- k = 1 panels stay slow (168 h windows). That is #306's lever, not this one.
- **Not affected:** today's Sepolia, where with one validator every verdict is k = 1 and held (`PanelsVerdict.sol:219,
  300`), so nothing merges at all until more validators join (RB12).

### RB10. Where the code goes, and the size budget (question 7)

| Piece | Contract | Estimated bytes (to be measured in task 1.6) |
|---|---|---:|
| `rebase(b, fix, base, salt)` (RB2; reuses `_newCheck`, already compiled into the Endings for `register`) | RaceV3Endings | +700 to 1,100 |
| `mergeExpired` extended (RB5) | RaceV3Endings | +200 to 350 |
| The `rebase` stub (`_delegate`) | RaceV3 | +40 |
| `merge`'s rebase branch (RB5) | RaceV3 | +300 to 450 |
| `isParty` (RB6) | RaceV3 | +60 to 100 |
| `_earned` (in RaceV3Base, compiled into all three through `_settle` and `claimRefund`) | all three | +60 to 100 each |
| `_settle`: the rebaser's share and the rebase's S6 refund (RB1, RB4) | all three (`Baskets.claimRefund` → `_settleForRefund`) | +200 to 350 each |
| `settleChallenge`'s `won` (RB6) | RaceV3Annex | +40 to 80 |

**Expected margins after the change:**

| Contract | Expected margin |
|---|---|
| RaceV3 | about 1,000 to 1,300 B |
| RaceV3Annex | about 1,700 to 1,900 B |
| RaceV3Endings | about 900 to 1,500 B |

None of the other contracts changes.

**The rule:** each of the three keeps at least 512 B of margin. If RaceV3 or the Endings would fall below it, in this
order:

1. drop `REBASE_SHARE_BPS` (RB1's fallback);
2. move `rebase` and the reopening into a third companion, `RaceV3Rebase`. It is reached from the Endings' fallback, as
   the Endings are from the Annex (`RaceV3Annex.sol:51-62`), and its fingerprint is checked. That costs one more
   DELEGATECALL hop, about 2.6k gas plus calldata copying, on the rare calls only.

`merge` stays in RaceV3, because it is the hot path and Heads' mover is RaceV3.

### RB11. Gas under EIP-8037

**Not measured yet; estimated from `reports/glamsterdam-runtime-v1.md`.** In that report a new slot is 110,028 gas as
`gasleft()` sees it, and `register` (row 3), which opens a check in FeesV3 and Panels as `rebase` does, used
**2,416,879** gas on Sepolia (639,079 under the old rules).

- **`rebase` ≈ 2.2–2.6M:**
  - it has no `Issue` push (about 6 fewer new slots);
  - it adds `Submission.rebaseOf`/`fix`/`base`, `Award.rebase` and a SolverBook claim (about 5 new slots, ≈ 0.55M).
- **`merge` through a rebase:** today's `merge` plus 2–3 cold SLOADs and one SSTORE that overwrites a value (`a.fix`).
- **`mergeExpired`'s reopening:** today's.
- **The re-check panel's chain gas** is that of any check, per the report's table (per seat for seal, receipt, reveal
  and report):

  | Step | Gas on Sepolia |
  |---|---:|
  | draw | 1.43M |
  | seal | 171k |
  | receipt | 160k |
  | reveal | 468k |
  | report | 499k |
  | result | 699k |

  At about 22 wei/gas this rounds to zero coins. The relayer's repayment has the undercount the report names (R1),
  unchanged.
- **The limits:** every transaction stays far below 2^24, and none of the new code reads `gasleft()`. So the
  reservoir caveats (report rows R1 and R2) don't apply.
- **Task 1.7** measures each new path with `forge test --gas-report` and on the Sepolia rehearsal under Glamsterdam
  before the release candidate.

### RB12. The Radicle repository moves from v3 to v3.1 (added at the coordinator's request, 2026-11-23)

**The facts:**

- The repository `rad:zyZXC9NqVuse8nXdpv7iYRScDHsN` has one delegate, the v3 genesis validator's node
  `did:key:z6MkwbkgYBtcn47Cu3rRjEvGRLjEvWaoDMovaMaH5VLEVYRt`, with threshold 1 (`sepolia-v3.json` `genesisRadNode`). So
  canonical `main` moves only through v3's `Heads`.
- With one validator every verdict is k = 1 and held. So `main` is frozen at `81505595` (= `sepolia-v3.json`
  `genesisHead`).
- `scripts/deploy_sepolia.py` refuses a plan whose genesis head isn't the RID's canonical `main` (`:330-333`, `:408-416`,
  `:513-519`, via `pofctl verify-head`).
- A node signs only identity revisions whose delegates equal **its own deployment's** seats' nodes:
  - `review_revision` (`oracle/delegates.py:312-344`);
  - `identity_step` proposes them (`:385-425`);
  - the seats' nodes are read from that deployment's `Validators.radNodeOf` (`ChainSeatNodes`, `:233-265`).

**1. Same RID (decided, O5).** v3.1 keeps `rad:zyZX…`, with its genesis head at the canonical `main` at deployment.
That is `81505595` if v3 still hasn't merged anything, and `deploy_sepolia.py`'s verify-head enforces it.

- **The alternative, a new RID:** it loses the repository's issues, the patches (bounty registrations claim Radicle
  issues, L12) and its followers, and it needs a new seed setup.
- **Precondition:** no v3 bounty is `Won`, or `Merged` with an unmerged award. Otherwise v3's `Heads` could still
  move after v3.1's genesis. Check it with
  `pofctl --v3 status` over the bounties at the hand-over.

**2. The delegate set: one node in both seat sets, then v3 wound down.**

- v3.1's genesis plan names the same `genesisRadNode` (the same node key), so v3.1's genesis seat maps to the same
  node.
- Then v3's seats' nodes and v3.1's are both {`z6Mkwbkg…`}, threshold 1 = `majority(1)`. The identity document
  already satisfies both deployments' `verify_delegates`, and **no identity revision is needed at the hand-over**.
- The genesis validator then switches its node's seat part from v3's record to v3.1's.
- From there v3.1 grows the delegates by the ordinary rule as validators join v3.1 (`identity_step` proposes; a new
  delegate first publishes `main` at the head).
- **If the operator wants a different node for v3.1:** v3's node (the only v3 delegate) must accept a revision that
  `review_revision` would refuse, because the delegates aren't v3's seats. So that path needs a one-time, deliberate
  manual `rad id update` by the operator, recorded in the deployment record. Not recommended.

**3. What a v3 node does once v3.1 takes over.** A node runs the seat part (`ORACLE_MERGE_VIA=radicle`: pushes and
identity votes) for **exactly one** deployment, the newest record it is given. For a superseded record it runs only
the keeper (results, finish, release, refunds), so v3's money can still settle.

- A guard is added in `radicle_v3.SeatAdapter`: if the deployment record carries `supersededBy`, the seat part refuses
  to start and logs why.
- **Which `Heads` wins:** the one whose seats are the delegates, which after the hand-over is v3.1's. Radicle's
  threshold makes it so.
- **Safety net, already there:** if v3's `Heads` ever moves to a commit that doesn't fast-forward `main`,
  `decide_head` refuses to push (`oracle/radicle.py:212-214`).
- **v3's bounties after the hand-over:**
  - they can still merge on v3's `Heads`, but never on Radicle;
  - the guide and the record say v3 is superseded, as `sepolia-v3.superseded-12192376.json` was (#316);
  - keyless contracts can't be closed, but they sunset by themselves (`idleDays` 28);
  - pledges are refused below 3 active solvers anyway (L6).

**4. The v3.1 code is public before the hand-over.**

- The owner's Radicle node pushes the release candidate's commit as a **non-canonical branch** in the owner's
  namespace (`git push rad <rc commit>:refs/heads/v3.1`). It is readable by anyone with `rad` under the owner's NID and
  never becomes canonical `main`, because the owner's node isn't a delegate.
- The deployment record names that commit (L18).
- Getting the v3.1 code and its record into canonical `main` afterwards goes through v3.1's own race (L15).
- **Decided (owner, 2026-11-23, O5):** the hand-over as designed here: the same RID, the genesis node shared by both
  deployments, and the `v3.1` branch from the owner's node first.

### RB13. Shipping: one v3.1 with a new release candidate

- `mergeDays` is a constructor parameter (`Config`). With a rebase path, it only bounds a winner that nobody rebases
  or merges, and RB5 already gives every passing rebase `mergeDays` after its own finality.
- So v3.1 uses a shorter `mergeDays`. **Decided (owner, 2026-11-23, O4): 3 days** (one grace day plus a working
  margin), in the v3.1 plan's `Config` (task 8.1).
- **Decided (owner, 2026-11-23, O6): v3.1 = this change plus #311's early reveal** (one release candidate, L18), on the owner's go for each of: the
  release candidate, the deployment, and the hand-over (RB12).

## Risks / Trade-offs

- **The size budget is tighter than estimated** → RB10's order: drop the share, then a third companion. Measured
  before anything else (task 1.6).
- **A semantic conflict that no test covers and the model misses** → the same residual risk as any fix. A D21 dispute
  catches it in the window, and its reward is extended to rebases (RB6). The window isn't shortened (RB4).
- **A stranger blocks the rebase slot after the grace period** with a stream of failing rebases → each one costs its
  metered check, and once the solver's own rebase is counted, the next slot is free. A grief costs about one check per
  slot cycle (about 3 h). Watch for it on Sepolia. If it appears, a later deployment can give the solver's rebase
  priority (it ends a stranger's undecided check before a panel is seated).
- **A head that keeps moving** (many merges) → a rebase can go stale again before its count, and is then failed as
  stale, which frees the slot without reopening (RB5). The deadline keeps counting from the last passing rebase, so a
  winner in a busy repository isn't expired while it keeps up.
- **ABI break** (`Submission` and `Award` gain fields) → pofctl's and the node's decoders take the version from the
  deployment record (`version` 3 → 3.1). Covered in tasks 3 and 4.
- **The funders pay the third-party share** → bounded (10 % of the price, only from the pot's rest), and only when a
  stranger did the work. Accepted by the owner (O1).

## Migration Plan

1. The contracts and tests (tasks 1–2), the node and pofctl (tasks 3–4), the guide (task 5), all on the devnet
   first.
2. The integration scenario on the local devnet, then its Radicle variant (task 6).
3. A new release candidate (task 7, L18), after the owner's go.
4. The v3.1 Sepolia deployment with the same RID (task 8, after the owner's go). v3 is marked superseded.
5. The Radicle hand-over (RB12): the genesis validator's node switches its seat part to v3.1.

**Rollback:** before step 5, v3 keeps the repository and v3.1 is simply abandoned. After it, the seat part can be
switched back to v3 as long as v3.1's `Heads` hasn't moved past v3's. Keyless contracts are never "rolled back".

## Open Questions

None left. The owner decided all six on 2026-11-23, each as recommended (comment on #310):

- **O1** (RB1): **decided:** the solver at any time; anyone else after `REBASE_GRACE` = 1 day; a third party whose
  rebase merges gets `REBASE_SHARE_BPS` = 10 % of the price from the pot's rest.
- **O2** (RB3, RB4): **decided:** no tests-only re-check and no shorter window for "clean" rebases in v3.1.
- **O3** (RB7): **decided:** no reputation and no activity for third-party rebasers.
- **O4** (RB13): **decided:** v3.1's `mergeDays` = 3.
- **O5** (RB12): **decided:** the same RID, the genesis node shared by v3 and v3.1, and the v3.1 code public first as a
  non-canonical `v3.1` branch from the owner's node.
- **O6** (RB13): **decided:** #311 (early reveal with the shadow guard) ships in the same v3.1 release candidate.
