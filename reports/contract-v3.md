# Contracts v3: Panels, proof levels and RaceV3 (proof-of-fix#138, tasks 3.2, 3.4 and 3.5 of #132)

Task 3.2 builds `Panels`, v3's draw and verdict bookkeeping, on `Validators` (3.1) and `FeesV3` (3.3). Task 3.4 adds the proof levels and the constitution's lists (below, "Task 3.4"), and the owner's decision on a reveal missed after the majority revealed. Task 3.2 came in two milestones:
- **Milestone A:** the draw; seals, reveals and receipts on-chain (D18, in place of #122 and #85 5.5/5.6); the replacement of silent judges; finality and the k = 1 hold.
- **Milestone B:** shadows; audits; challenge panels and the frozen window; the family scores; the constitution tier; and a draw that registry changes made after its seed is fixed can't re-roll.

Task 3.5 builds `RaceV3`, the race on Panels and FeesV3, splits `FeesV3.roll` into bounded parts, and replays group 7's market on them (below, "Task 3.5").

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
  - `RaceV3Annex` has 443 bytes of margin and `RaceV3` 1,681. The next race feature needs a second annex, or the Baskets externals moved off the annex.
  - `Validators` has 2,870 bytes of margin, as 3.4 left it.
