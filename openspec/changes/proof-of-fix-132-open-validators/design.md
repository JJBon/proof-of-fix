# Design

## Context
- **v2 (built, on the devnet).** `Verdicts` holds 7 seats fixed at deployment. Vacant seats are reserved for named operators, a join is co-signed by 5 other seats, and the issue tier always draws 3 by a Fisher-Yates shuffle over the active keys (ADR 0002). `Fees` meters each check and pays each drawn judge the median usage plus the service fee (#111). Seals, reveals and receipts on-chain (#85 tasks 5.5, 5.6, #122), bonds and challenges (5.8) and attestation (#94) are specified but not built in v2; v3 builds them itself (D18).
- **The node (built).** It fetches the claimed commit (#115), runs the sandbox from inside its container (#116), exchanges seals over a pluggable transport (#117), and calls its model directly with spending guards (#118). One real Bedrock call has been checked.
- **Why this change:** see proposal.md. The behaviour is in `specs/validator-admission`, `specs/judge-panels`, `specs/judge-scores`, `specs/check-pricing` and the `incentive-simulation` delta. This document covers how, the parameters, and the order of work.
- **Revised 2026-11-03 (#141)** after #134's simulation ([`reports/open-validators-v1.md`](../../../reports/open-validators-v1.md)) met only 4 of its 10 acceptance criteria. See the revision note below.
- **Revised again 2026-11-03, round 2 (#141),** after the re-run with round 1's rules ([`reports/open-validators-v2.md`](../../../reports/open-validators-v2.md), PR #147) met 8 of its 13 criteria. See "Revision 2026-11-03, round 2 (#141)".
- **Revised a third time 2026-11-03, round 3 (#141),** after round 2's run ([`reports/open-validators-v3.md`](../../../reports/open-validators-v3.md), PR #153) met 9 of its 13 criteria. No protocol rule changes. See "Revision 2026-11-03, round 3 (#141)".

## Revision 2026-11-03 (#141)
**Why.** #134 simulated this design on 40 seeds and found attacks that pay and money that doesn't work:
- the colluding genesis validator gains +$2,920 ± 456 a year, and no k = 1 window from 1 to 30 days makes it lose;
- the seed grinder gains +$258 ± 79, and the constitution coalition +$5,196 ± 2,178;
- the fee never leaves its ceiling, and an honest validator loses money, mostly to v2's outage slash;
- 23 gaps and contradictions in the specs, and none of the "published" thresholds of the acceptance criteria sized.

Nothing on-chain implements v3 yet, so the change is revised in place. v2 is untouched (D15).

**How.** Each finding gets **one rule** below, chosen on the report's evidence. Each alternative becomes a **simulation switch** that the re-run (tasks 6.x, `reports/open-validators-v2.md`) runs beside the rule on the same seeds. The parameters ADR (#137, task 2.1) decides from that re-run. The validators' token slice (#142) is related and not designed here.

**Round 2** (the next section) changes the rules of rows 1, 3, 4, 5, 7 and 9 below, and of gaps 10 and 16.

| # | What failed (report) | Rule chosen (where) | Switches in the re-run |
|---|---|---|---|
| 1 | **k = 1:** the colluding genesis gains +$2,920 ± 456 at 72 h; +$723 at 7 days, +$312 ± 62 at 30. It's caught in no run, and it stalls qualification (3.1 newcomers qualify in its year, 13.3 in its twin's). | A k = 1 verdict is **held**, unpaid, until `CHALLENGE_K[1]` validators could judge its challenge. At most `K1_PENDING_MAX` k = 1 verdicts pending per validator. **Every** k = 1 verdict audited once a validator outside its panel is eligible. Shadows scored only against outcomes no lone validator set. k = 1's window at least 7 days. (D4, D5, D13) | `K1_PENDING_MAX` 5 / 10 / 20; a batch-sized k = 1 bond (`K1_BATCH_BOND`) in place of the count cap; k = 1's window 7 / 14 / 30 days |
| 2 | **False verdict at 20 % of the bond:** the seed grinder gains +$258 ± 79. | The whole bond, `FALSE_VERDICT_SLASH_BPS` 10,000: the grinder loses (−$378 ± 103), the spread sybil ten times more (−$14,082 ± 2,398). (D16) | 20 % as a sensitivity row |
| 3 | **Constitution:** a coalition can be most of the first `K_MAX`: +$5,196 ± 2,178 with 5 early validators, +$819 ± 450 with 3. | The constitution tier is drawn only when at least `CONSTITUTION_MIN_ELIGIBLE` = 2 × `K_MAX` (14) validators are eligible. ADRs submitted to a smaller network expire unjudged. (D7) | `CONSTITUTION_MIN_ELIGIBLE` 14 / 21 / 28 |
| 4 | **Outage slash:** 5 % of the bond per missed seal costs an honest validator about 3 × its fees ($2.05 against $0.74 a month). It makes large bonds unprofitable and freezes the fee at its ceiling. | A sealed vote not revealed costs a flat `SEALED_NO_REVEAL_SLASH` ($1). A judge that never seals isn't slashed: it's replaced, and the reveal-rate floor (`ACTIVE_REVEAL_MIN`) suspends it. (D16) | `SEALED_NO_REVEAL_SLASH` $0.50 / $1 / $5; `SILENCE_SLASH` $1, if the silent judge doesn't lose without it |
| 5 | **Pricing:** the fee sits at its $0.25 ceiling all year. From $0.05, 28 of 40 runs collapse. `IDLE_HIGH` (80 %) never fires. Inflaters gain +$42 ± 22. | `FEE_START` = the ceiling. `IDLE_HIGH` 40 %. A wait counts only if a newcomer at the bond floor could have ended it. Every validator posts every family's public list price. The lower median for an even count. The target is the validators' **average (break-even)** cost, within the published `FEE_MARGIN`. (D9) | `IDLE_HIGH` 30 / 40 / 50 %; idling measured over 7 days (`IDLE_WINDOW_DAYS`); a wait signal counting waits a newcomer of any bond could end; `FEE_STEP_UP` 10 % (faster rise than fall) |
| 6 | **Audits:** a bribed cheater isn't deterred at 5 % (−$34 ± 47, not significant). | `AUDIT_RATE` 10 % (−$137 ± 64, at $0.018 a check). (D13) | the audit range 0–20 % |
| 7 | **Scores:** a weak family's herders gain +$294 ± 28 on a moving market. Pay by score raises service fees per submission by 39 %. | A barred family's shadow verdicts only decide its recovery; they never enter its counted score. The fee factor is normalised so its mean over the network's counted seats is 1 ×. (D14) | an agreement score balanced over passed and failed outcomes (`SCORE_BALANCED`); the neutral point at the median family score |
| 8 | **Proof levels:** a level C genesis can't grow a network (96 % withdrawn). The answer shopper gains +$328 ± 69 on a grown all-C network at 3 in 10. | The genesis must be at level A or B. Every non-unanimous pass by a level C panel is audited. Answer shopping is named as the remaining trust point. (D10, D13) | level C's bounty limits halved (`C_LIMIT_X` 0.5); the borderline rate at 1 and 3 in 10 |
| 9 | **Caps:** the per-TEE-type cap lowers k on 39 % ± 9 of a growing network's draws. | The TEE-type cap applies only from k = 5 (`TEE_CAP_FROM_K`). Host and family caps from k = 3, as before. (D6) | 5 accepted TEE types with the TEE cap from k = 3 |
| 10 | **Qualification:** 18 of 54 newcomers qualify in a year, after 135 days. | Candidates also shadow-judge waiting submissions (`SHADOW_PER_WAITING` 3 a submission). (D5) | `SHADOW_PER_WAITING` 0 / 3 |
| 11 | **Do-nothing parameters:** `DRAW_TRIES` 8 and 1,000 give the same draws (36.6 % against 36.5 % lowered). `SCORE_FACTOR_MAX` (best 1.70 ×) and `PRICE_CAP_X` (best 1.68 ×) never bind. | `DRAW_TRIES` is fixed at 8 per seat: a gas bound, not a tuning parameter. `SCORE_FACTOR_MAX` and `PRICE_CAP_X` stay as **safety bounds**: they cost one comparison and bound cases the simulation's worlds don't reach (a family far ahead on a small network; a few posters on a tiny one). The ADR doesn't tune them. | none |
| 12 | **23 gaps and contradictions** | each resolved below | as named |
| 13 | **Undecidable criteria:** shares and margins never published | every threshold published (D17); new scenarios in the `incentive-simulation` delta | the published ranges |

### The report's spec gaps, resolved
Numbered as in the report's "Spec gaps and contradictions".
1. **The challenge panel's size.** It's `CHALLENGE_K[k]` fresh validators. If fewer are eligible, it's the largest odd number they allow, but only if that is still larger than k (or `K_MAX` for a panel of `K_MAX`). Otherwise the challenge waits, window frozen (D4). The spec's "or every other eligible validator if fewer" is dropped: that could be 1 or 2. With k = 1 verdicts held (D4), D4's waiting no longer helps a colluder.
2. **Eligibility by bond.** Tiers (D2), with the steps level-independent: every bounty limit in the k table at any level ($10, $25, $50, $125, $250, $312.50, $625). A validator is eligible if its bond is at least `BOND_FACTOR` × the bounty's tier, the smallest step at or above the bounty. For the simulated bonds ($100, $250, $500, $1,250), this is the same eligibility as 2 × the bounty. The contract keeps one counter per step, so k is exact.
3. **The slash for a false verdict:** the whole bond (D16).
4. **The fee's target:** validators' average (break-even) cost, within `FEE_MARGIN`. Under free entry it can't settle at marginal cost (D9).
5. **The absurd-price scenario.** One outlier among 15 moves the median by at most one rank, so the price stays within the honest posters' middle values. The spec now says that.
6. **Re-attestation after a raised firmware minimum:** the spec's reading. The validator re-attests and returns without qualifying again: same key, bond, model and code. A removed TEE or proof type means registering again and qualifying (D11).
7. **"Canary scores"** in the answer-shopping scenario: the family scores of D14. Canaries stay with #136.
8. **Counted verdicts against shadow verdicts in a score:** the counted score uses counted verdicts only; a barred family's shadow verdicts decide only its recovery (D14).
9. **The neutral score:** the factor 1 ×, which after normalisation is the network's mean (D14).
10. **A counted judge that never seals** isn't slashed. It counts as a miss toward the reveal-rate floor and is replaced. A sealed vote not revealed costs `SEALED_NO_REVEAL_SLASH` (D16). **Round 2:** silence costs a flat `SILENCE_SLASH` ($5), and a sealed vote not revealed $5.
11. **Unbonding against a frozen window.** The bond is withdrawable only after `UNBONDING_DELAY`, and only once every verdict it gave is final and every challenge naming it is closed. `UNBONDING_DELAY` is the longest window of any (k, level) plus 7 days: 336 + 168 = 504 h.
12. **A drawn panel too weak for its bounty** (its level's limit is below the bounty): the draw is void and the submission waits. It's drawn again with a fresh seed (D3's re-targeting) when the registry changes. That's the simulated reading; 7 % of a mixed growing network's submissions waited for it.
13. **The constitution tier's level** isn't used. An ADR's notice is `ADR_WINDOW` (14 days) or `REMOVAL_WINDOW`, whatever its judges' levels. ADRs move no bounty, and the 14 days exceed every level's window (D7).
14. **A TEE type added by ADR** is its own type under the TEE-type cap. **A notary delisted by ADR:** verdicts revealed before the removal takes effect still count, and nobody is slashed for them (D11).
15. **The median of an even count** is the lower middle value. **Every validator posts every unit:** its own costs for the shared units, and each family's public list price for tokens (D9).
16. **"Waited for a panel"**, for the fee: a submission, or a stalled panel, that one more validator bonded at `BOND_FLOOR`, of any host, TEE type, family or level, would have let be drawn (D9). **Round 2:** every wait counts, once.
17. **Changing model family means registering again**, with a new key that qualifies. The simulation's movers switched at once (the worst case), and the caps still held, so this is the safer reading.
18. **`SCORE_MIN_VERDICTS`** counts the counted verdicts in the window (at most `SCORE_WINDOW`).
19. **"A fixed k of 3"** is the simulated one: every bounty up to $625, k = 3's 24-hour window, and a challenge panel of 5. The `incentive-simulation` delta now says so.
20. **Earlier criteria:** named, not re-run. v3 leaves v2's market, checking, token and split rules unchanged (D15), so their latest reports stand.
21. **Published values:** all set in D17 and the Parameters (`SYBIL_SHARE`, `LONE_CATCH_SHARE`, `FEE_MARGIN`, `WAIT_CROWD_MAX`, the window and audit ranges).
22. **Unsized values,** now sized:
    - the cooling-off period, `QUALIFY_COOLDOWN` 7 days;
    - the reveal-rate floor before a validator's first 50 draws: more than 5 misses among its draws so far suspends it;
    - the shadows' pool spend per draw: at most the seated shadows' quoted usage;
    - `FEE_START`, the ceiling;
    - the idle share, per period (`IDLE_WINDOW_DAYS` is a switch);
    - the TCB minimums and the notaries (D10).
23. **World assumptions, not parameters.** The movers' pace, the blind spot, the families' accuracies and the borderline rate stay named assumptions. The re-run reports the borderline rate at both 1 and 3 in 10 (D10).

## Revision 2026-11-03, round 2 (#141)
**Why.** Round 1's re-run (task group 6, [`reports/open-validators-v2.md`](../../../reports/open-validators-v2.md), PR #147; 40 seeds, every ± two standard errors) met 8 of its 13 criteria (v1: 4 of 10). Round 1's rules made the lone validator and the seed grinder lose, and fixed the proof-level attackers, growth and the cost of scores. Five criteria still failed:
- the market collapsed below 3 active validators in 33 of 40 runs;
- the bribed silent judge gained +$317 ± 13 and the withholder +$249 ± 12, and an early coalition of 5 gained at every constitution threshold tried;
- 86.6 % ± 5.1 of the colluding genesis's bad fixes were reversed before payment, under the published 90 %;
- a weak family's herders gained (+$13 ± 2; +$202 ± 19 on a working market);
- the inflaters gained on the collapsing market (+$33 ± 4), and on a working one gained nothing (−$1 ± 7), which "loses" couldn't pass.

The owner agreed to the report's recommendations on 2026-11-03.

**How.** As in round 1: one rule per finding, chosen on the report's evidence. Round 1's rules stay reachable as one switch set (`V2R1`), as #134's are (`V1`), and both run beside round 2's on the same seeds (task group 7, `reports/open-validators-v3.md`). The parameters ADR (#137) decides from that run. Unchanged: v2 (D15); ADR 0003's principles (keyless, no vote sets a price, a DAO only funds, the owner runs at most one validator); level C off at launch (#145, D10); and #142, which stays related.

| # | What round 1 found (report v2) | Rule (owner, 2026-11-03; where) | Evidence | Switches in round 2's run |
|---|---|---|---|---|
| 1 | **The fee's wait signal only lets the fee fall.** With bond tiers, a newcomer at the $100 floor can judge bounties only up to $50, so waits for larger ones never raise the fee. `IDLE_HIGH` lowers it, validators leave, and 33 of 40 runs collapse. | **Every wait counts** (`WAIT_SIGNAL` "every"): a submission once, in the period it starts waiting, and a counted panel stalled for a replacement once. `IDLE_HIGH` stays 40 %. (D9) | every wait: 0 of 40 runs collapse, and the fee is 1.21 ± 0.04 × break-even over the last 13 weeks ($0.186 against $0.154), within `FEE_MARGIN` | the floor-bond and the any-bond signals |
| 2 | **Silence and withholding earn a bribe.** Silent judge +$317 ± 13 unslashed, +$250 ± 12 at a $1 silence slash; withholder +$249 ± 12 at $1. | **A flat $5**, the same for every bond, for a counted judge that never seals (`SILENCE_SLASH`) and for one that seals and doesn't reveal (`SEALED_NO_REVEAL_SLASH`). (D16) | withholder at $5: −$20 ± 9. Honest cost at 1 outage in 200 draws: about $0.025 a draw, $1.11 ± 0.09 a month with every outage slashed (v2's share of the bond: $4.34) | both at $1; silence unslashed |
| 3 | **The constitution coalition.** 5 early validators gain at every threshold: +$622 ± 260 from 14 eligible, +$280 ± 152 from 21, +$187 ± 138 from 28. | ADRs that add or loosen anything, and escalated fixes, are drawn from **21** eligible (`CONSTITUTION_MIN_ELIGIBLE`); ADRs that only remove, or raise a firmware minimum, from **14** (`REMOVAL_MIN_ELIGIBLE`). A rejected ADR forfeits **`ADR_DEPOSIT`, $15**. (D7) | derived from the report's table: from 21 with $15, the coalition of 5 nets about −$255 ± 152. Neither the threshold nor the deposit alone makes it lose (D7). | one threshold for all ADRs, 14 or 28; the deposit at $0 and $25 |
| 4 | **The lone validator's catch share:** 86.6 % ± 5.1 of its bad fixes reversed, under `LONE_CATCH_SHARE` (90 %), as D17's own estimate (87 %) predicted. | **Every k = 1 verdict audited twice,** by two validators outside its panel (`K1_AUDITS` 2). `LONE_CATCH_SHARE` stays 90 %. (D13) | estimate: about 96 % reversed. k = 1 is 2 % of panels, so the second audit is one more check on 2 % of panels. | one audit |
| 5 | **Scores.** An always-pass herder agrees 78.5 % ± 0.5, above `SCORE_MIN`, and the weak family's herders gain. Recovery, tested on the last 50 shadow verdicts at each new one, re-admits a 68 % family 10.8 times a year. | **The balanced score** (`SCORE_BALANCED`). **Recovery on fresh blocks** of 100 shadow verdicts, each judged once, at `SCORE_MIN` + 10 points (`SCORE_RECOVER_VERDICTS`, `SCORE_RECOVER_MARGIN`). (D14) | balanced: the herder scores 50.1 % ± 0.1 and every herder row loses (−$8 ± 1; −$54 ± 6 at $0.25; −$69 ± 10 on a working market), at no measured cost (1.30 against 1.33 bad fixes per 100 paid; $0.353 a submission). Blocks: about 1.9 % false recovery a block (estimate). | plain agreement; round 1's sliding test; a fresh block of 200 at + 5 points |
| 6 | **The k = 1 hold's cost:** an honest k = 1 fix is paid a median 19.0 ± 3.6 days after its verdict (p90 46.1). | **Accepted as is.** (D4) | k = 1 is 2 % of panels, and only the bounty waits | as round 1 |
| 7 | **The TEE cap from k = 5:** with three types, one TEE type holds the majority of 77 % ± 8 of the panels of 3. | **From k = 3 while at least 5 TEE types are accepted** (`TEE_CAP_K3_TYPES`), from k = 5 otherwise. Each attestation scheme is its own type, and the real types are named (D6). | five types, the cap from k = 3: no one-type majority, 6 % ± 1 of draws lowered (13 % ± 3 now), 22 % ± 3 waited (21 % ± 3) | three types (the launch list) and five, each spread evenly and skewed |
| 8 | **Level C off at launch** (#145) | kept (D10) | | as round 1 |

### Round 1's spec findings, resolved
Numbered as in the report's "Spec findings".
1. **The floor-bond wait signal** is superseded by rule 1.
2. **`LONE_CATCH_SHARE` above D17's own estimate:** rule 4 raises the estimate to about 96 % (D17), so the threshold now sits below it. It stays 90 %.
3. **"Loses" can't be met by an attack that gains nothing** (the inflaters on a working market, −$1 ± 7): every attacker criterion is now **"doesn't gain against its honest twin"**: the mean difference is at most zero, and the mean plus two standard errors is at most `GAIN_TOLERANCE` ($10 over the run). A positive mean, or a noisy result whose upper bound is above the tolerance, still fails (D17).
4. **Shadows on a held k = 1 verdict** are scored once, against the sealed majority at the reveal (not at all with fewer than 3 revealed), and never again when the verdict becomes final. A k = 1 verdict whose window starts at its reveal scores its shadows at finality. That is how round 1 ran; the spec now says it (D5; validator-admission).
5. **The hold binds almost every k = 1 verdict** (65 % ± 8 held): k is 1 only when one or two validators are eligible, so a k = 1 window starts at once only when the caps or the pending cap stepped k down. D4 says so; no rule changes.
6. **Shadows on waiting submissions are required,** not a speed-up: at `SHADOW_PER_WAITING` 0 the hold deadlocks and no run reaches k ≥ 3. D5 says so.
7. **Recovery on a sliding window** is replaced by rule 5's fresh blocks.
8. **The honest outage** ("silence isn't slashed" against D16's $1, sized as if every outage paid it): superseded by rule 2. Every counted outage costs $5, before or after the seal, and D16 sizes it that way.
9. **"Silence gains nothing"** held for the protocol (k never shrank), but a bribe for silence is income. Rule 2 makes each silence cost more than the report's bribe (about $4).

**The report's other findings** don't change the design. They confirm round 1's values (`IDLE_HIGH` 40 % with a working wait signal, `SHADOW_PER_WAITING` 3, `K1_PENDING_MAX` 10, k = 1's 7-day window, the whole bond for a false verdict, the normalised factor) or recommend dropping switches (`FEE_STEP_UP`, `K1_BATCH_BOND`, `C_LIMIT_X`). The ADR (#137) records them.

## Revision 2026-11-03, round 3 (#141)
**Why.** Round 2's run (task group 7, [`reports/open-validators-v3.md`](../../../reports/open-validators-v3.md), PR #153; 40 seeds, every ± two standard errors) met 9 of its 13 criteria. Round 2's rules did what they were chosen for: the market works, silence and withholding lose at $5, both early coalitions lose, and 7 of 8 herder rows lose. Four criteria failed, and in none of them does an attack pay:
- the inflaters (+$2.7 ± 3.9) and the weak family's herders (+$0.2 ± 0.7) failed only on the sign of a mean too small to measure;
- 93.3 % ± 3.9 of the colluding genesis's bad fixes were reversed before payment (lower bound 89.4 %, under 90 %), counting fixes it didn't judge; of its own lone verdicts, 98.4 % ± 1.8 were;
- crowding into the top model: 11.3 % ± 4.9 of submissions waited (upper bound 16.2 %, over 15 %), the balanced score's cost.

The report also found that a silent judge bribed 10 % of the bounty still gains +$311 ± 21 at the flat $5.

The owner agreed to four decisions on 2026-11-03. None changes a protocol rule: three change how a criterion is read or sized, and the fourth adds a switch for the ADR to size.

**How.** The rules and the seeds are round 2's, so the simulation's outputs are report v3's: the new criteria only re-judge its numbers, and nothing is re-run for them. Task group 8 implements the criteria (round 2's kept as a switch), re-judges v3's numbers, runs the silence-slash sweep and the deposit's honest cost, and writes [`reports/open-validators-v3.1.md`](../../../reports/open-validators-v3.1.md), an addendum to v3. The parameters ADR (#137) decides from v3 and v3.1.

| # | What report v3 found | Decision (owner, 2026-11-03; where) | Evidence (report v3) | Switch or sweep (group 8) |
|---|---|---|---|---|
| 1 | **"Doesn't gain" fails a zero-effect attack half the time.** Its first test is the sign of a sample mean. The inflaters (+$2.7 ± 3.9) and the weak herders (+$0.2 ± 0.7) failed only on it. | **"Not shown to gain"** replaces "doesn't gain" for every attacker criterion: the mean − 2 SE ≤ 0 and the mean + 2 SE ≤ `GAIN_TOLERANCE` ($10 over the run). "Loses" (the mean + 2 SE < 0) stays reported beside it. (D17) | inflaters −$1.2 to +$6.6, weak herders −$0.5 to +$0.9: both met. Every other row the two rounds flagged still fails: its lower bound is above zero (the 10 % bribe +$311 ± 21; plain-agreement herders +$97 ± 31) or its upper bound above $10 (the coalition of 5 from 14, −$58 ± 259). | round 2's "doesn't gain" (`GAIN_TEST`) |
| 2 | **`LONE_CATCH_SHARE` counted every bad fix the accomplice passed, whoever judged it:** 93.3 % ± 3.9. | **It counts only the verdicts the colluding lone validator gave itself,** as the spec's words intend ("the bad fixes it passes"). The rest is a named trust point (finding 3 below). (D17) | its own verdicts: 98.4 % ± 1.8 reversed (184 of 187). The accomplice's other fixes: 11 of 22 paid. The colluder still loses (−$247 ± 41). | round 2's count (`LONE_CATCH_COUNT` "all"), reported beside |
| 3 | **Crowding** into the top model: 11.3 % ± 4.9 waited, upper bound 16.2 %, over `WAIT_CROWD_MAX` (15 %). | **`WAIT_CROWD_MAX` = 20 %,** the cost of keeping `SCORE_BALANCED`. (D17) | plain agreement waits 7.7 % ± 2.5, but brings the weak herders' gain back (+$97 ± 31 on the market, +$20 ± 7 at $0.25) | 15 %, as a switch |
| 4 | **A bribe above $5 still buys silence.** At 10 % of the bounty (about $10 a silence) the silent judge gains +$311 ± 21 and the withholder +$310 ± 21. | **A sweep; the value is the ADR's.** `SILENCE_SLASH_BPS` makes the silence slash max($5, x % of the bounty), and `SEALED_NO_REVEAL_SLASH_BPS` the same for a sealed vote not revealed, for x of 0, 1, 2 and 5 %. ADR 0004 recommends an x from the evidence, or keeps $5 flat and names the trust point. (D16) | to be measured: for each x, the silent judge and the withholder bribed 5 % and 10 % of the bounty, and the honest validator's month at 1 outage in 200 draws | x = 0 (a flat $5) stays the default until the ADR |

### Report v3's spec findings, resolved
Numbered as in report v3's "Spec findings".
1. **The sign test** → decision 1.
2. **Which bad fixes `LONE_CATCH_SHARE` counts** → decision 2: the k = 1 verdicts the colluding validator gave itself, pooled over the runs. The report gives round 2's count beside it.
3. **A colluder sits on its accomplice's challenge panels: a named trust point.** The colluder isn't a declared party to its accomplice's fixes, so nothing keeps it off their challenge panels. In v3, over the 40 runs, 22 of the accomplice's bad fixes that reached an outcome were judged by others (an honest lone judge's mistake, or a panel of 3 drawn later), and 11 of them were paid: the colluder can sit on their challenge panels and defend them. It still loses (−$247 ± 41): its own verdicts are caught (98.4 %), and each costs its whole bond.
   - **Proposed, not decided:** a challenge panel could also exclude every validator that gave a counted verdict on another fix by the same solver that isn't yet final.
   - **What it would do:** keep the colluder off the challenge panels of an accomplice that reuses its address.
   - **What it wouldn't:** stop an accomplice that submits each fix from a fresh address, which costs it nothing. It also shrinks the challenge pool on a small network, where challenges already wait, and keeps honest validators off the challenges of a busy honest solver's fixes.
   - The owner decides. The simulation can measure it as a switch on the colluder's rows if wanted; group 8 doesn't.
4. **An upheld receipt challenge doesn't void the verdict: the code's reading (since #134), now the spec's too.** The disproven judge loses its whole bond (D16). The challenge panel's own majority decides the fix: the verdict is reversed if the panel votes against it, and stands otherwise. Why this reading, not the spec's "the verdict doesn't count":
   - the challenge panel is fresh, larger than the original (D4), and has just re-run the check, so its majority is the best evidence there is. Voiding the verdict would judge the same fix again, by a panel no larger, with no new evidence and another window;
   - "doesn't count" is undefined at k = 1, where no vote is left, and at k = 3, where the two left can split;
   - a second auditor's dispute on a k = 1 verdict queues (round 2), so a bad fix that a challenge panel passes by mistake can still be challenged again.

   A verdict posted with no receipt still doesn't count at the reveal ("A verdict with no receipt"): its judge is replaced in the same panel. The judge-panels spec now says how an upheld receipt challenge ends ("An upheld receipt challenge"), and "A verdict through a gateway" follows it. The code doesn't change, so no task.
5. **Two disputes on one verdict:** resolved in round 2's code. The second auditor's dispute queues (report v3, "How the model changed"), as the spec says ("One auditor misses a bad fix").
6. **The deposit's honest cost isn't simulated:** group 8 adds an honest ADR author on a grown network (task 8.3). It measures the share of its good ADRs rejected and the deposits it forfeits, beside D7's hand estimate (2.6 %, about $0.39 an ADR).

**Report v3's other findings** don't change the design. They confirm round 2's rules, name the trust points the ADR records (one TEE type holding the majority of about 77 % of panels of 3 until five types are accepted; answer shopping at 3 in 10 once level C is on; a silence bribe above the slash, decision 4), and list the switches to drop (report v3, "What's left to change").

## Revision 2026-11-14 (#236): measured judges
**Status: the direction is decided (owner, 2026-11-14); the values are not.** The owner agreed that one family may hold every seat while it is ahead by more than the margin (D20), that a rejected fix's deposit goes to the issue's bounty (D22), that an appeal panel is drawn from the families that didn't judge the fix, contenders included (D23), and that ADR 0004 is replaced, not amended, once group 10's runs are in. Every value (`SEAT_MARGIN`, `CAP_MIN_FAMILIES`, `SOLVER_DEPOSIT_BPS`, `EVIDENCE_REWARD_BPS`, `EVIDENCE_STAKE`, `APPEAL_WINDOW`) stays proposed until task 10.1, and no contract changes before the new ADR.

**Why.** v3's judges were assumed: right 85–95 % of the time, each call independent. #160 measured nine models on 228 real fixes ([`reports/judges-v2.md`](../../../reports/judges-v2.md)), and the simulation was re-run on those verdicts ([`open-validators-measured-v1.md`](../../../reports/open-validators-measured-v1.md), [`-v2.md`](../../../reports/open-validators-measured-v2.md); 40 seeds, exploratory). Five findings change the design:

| # | Finding (measured) | Evidence | What it breaks |
|---|---|---|---|
| 1 | One family is far ahead on fixes the tests fail: Opus 5.5 scores 88 % on known answers, the next 65 %, the five others 50–60 % | judges-v2, measured-v1 §4 | D6's family cap forces weaker families onto every panel of k ≥ 3 |
| 2 | v3 as designed merges 10–18 bad fixes per 100 paid, against the 1.1 assumed, and 43–77 % of submissions wait | measured-v1 §2 | ADR 0004's bonds and windows were sized on 1.1 |
| 3 | The score ranks the judges wrongly: the best family scores 71 % and is barred 69 % of the year, while families right half the time score 75–77 % | measured-v1 §3 | D14 scores agreement with the panel's own outcome |
| 4 | A second panel repeats the first: 1–2 reversals a year, because a model asked again gives the same verdict | measured-v1 §3 | D4's and D13's challenges and audits were the source of truth for the score |
| 5 | A solver that only submits bad fixes gains $10–28 a fix on a flat fee, with no collusion | measured-v2 §5 | a rejected fix costs its solver only the attempt fee and its checks |

**What the proposal does (D20–D23).** Seats go to the best-scoring families, and every other model earns by disputing their passes with a failing test. A solver posts a deposit it loses on rejection. The score rule stays D14's; what changes is where final outcomes come from.

**What the simulation supports, and what it doesn't yet.**

| Decision | Supported by a run | Not yet simulated or measured |
|---|---|---|
| D20: seats by rank, the family cap only among near-equals | the best family alone: 6.0 bad fixes per 100 paid, 0.1 % waiting (measured-v1 §4) | `SEAT_MARGIN`'s value; a prompt injection that fools the one seated family |
| D21: a failing test reverses a pass | 6.0 → 4.4 per 100 paid if a flagged bad fix yields a test 1 time in 2; 3.5 at 3 in 4 (measured-v2 §3) | how often a test can be found, and how often a wrong test is accepted: both assumed. The next paid run measures them |
| D22: the solver's deposit | exact counts: about $19 on an $86 bounty with Opus alone, $1.13 a good fix (measured-v2 §5) | not played out in the network; where the forfeit goes |
| D23: outcomes from evidence and appeals | evidence puts the families in the right order on fixes the tests fail (Opus 70.8 % → 87.5 %) | appeals are not simulated; without them a judge that rejects good fixes rises (measured-v2 §4) |

**How.** Task group 10: the simulation first (appeals, the deposit, `SEAT_MARGIN`, all on measured verdicts), then one paid measurement of the two assumed rates, then the contracts. The confirmatory run (group 9) waits for these rules to be frozen.

## Revision 2026-11-15 (#236): the appeal on evidence
**Status: one decision, the rest proposed.** Task 10.1 ([`open-validators-measured-v3.md`](../../../reports/open-validators-measured-v3.md)) showed that D23's appeal panel, drawn from the families that did not judge, overturns 81 % of the correct rejections appealed to it, and that a panel of the seated families alone overturns nothing.

**Decided by the owner, 2026-11-15:**
- **the appeal as D23 designed it is dropped.** Wrong rejections get a challenge that does not hand the decision to weaker judges: **the seated judges decide the appeal** (D24);
- **the solver's deposit (D22) is on hold.** The owner is against it and wants the market's own incentives to stop bad fixes. It is no longer "decided"; its share is not to be read as 2,500 or as 4,000 until he rules (D28).

**Proposed, not decided, each part for the owner to accept, change or reject** (D24–D28; simulated in [`open-validators-measured-v4.md`](../../../reports/open-validators-measured-v4.md), 40 seeds, exploratory):

| # | Proposed rule | What the simulation says | Recommendation |
|---|---|---|---|
| D24 | An appeal needs a test (fails on the base code, passes with the fix) and a stake; a fresh draw of the seated families decides | It restores as many wrongly rejected good fixes as the panel accepts (assumed 25–100 %). With no deposit, a solver of bad fixes loses by appealing while the panel passes under about 1 in 5 of its tests (assumed); with a deposit of 2,500, under about 1 in 7. Above that it gains | adopt, with the stake at the larger of $5 and 10 % of the bounty, **on the condition that task 11.3 measures the two rates** |
| D25 | A contender may sponsor an appeal | A sponsor of every rejection loses in every row, and so does an honest sponsor unless its model is clearly better than the seated one and its share is 2,500. It seats a better newcomer in 2–5 % of runs on fixes the tests fail (50–62 % with six shadows a draw), and in 0–12 % on fixes that pass them | adopt only as a permission; do not count on it for seating |
| D26 | Known-answer issues score every family | At 5 % a better newcomer is seated in 95 % and 68 % of runs by week 41–44; at 10 %, in 100 % and 92 % by week 25–28, for $81 and $163 of checks a year. At 2 % nothing changes within a year | adopt at 10 %, **if a source of known answers with no privileged author exists** (#136: not designed) |
| D27 | While fewer than three families can judge, a second draw from them decides a challenge | Verdicts never final fall from 23.6 % and 23.0 % to 0.1 % and 0.0 % under v3's seats, and from 2.7 % to 0.0 % under seats by rank | adopt |
| D28 | The deposit is held until the appeal period closes; the appeal stake is separate | Holding it opens no gain to a solver that tries an issue again. With no deposit at all, a solver of bad fixes gains unless about ten rival solvers each find a test 1 time in 4 | on hold with D22 |

**What the stored verdicts cannot say:** how a judge reacts to a passing test. Both rates of D24 are assumed and swept, and every number that depends on them is conditional.

## Revision 2026-11-19 (#251): the values decided
**Status: decided by the owner, every part as recommended** ([ADR 0007](../../../docs/adr/0007-solver-side-parameters.md), which replaces ADR 0004's solver-side values; tasks 10.2, 11.2 and 12.2). D20, D21, D24, D27, D29 and D30 are accepted with the values of reports measured-v3 to -v5. **There is no solver's deposit** (D22 and D28 are void), not even while a repository has fewer than three active solvers. D25 and D26 are left out of the testnet launch. The paid runs (tasks 10.3 and 11.3) are not decided, so D21's and D24's safety rests on assumed rates. The bonds and windows are not re-derived yet. The list is in "Open Questions", at the top; the D-sections carry a "Decided" line, and their earlier text is kept as history.

## Goals / Non-Goals
**Goals:**
- A registry that anyone can join under rules alone.
- A draw whose size follows the network and the bounty.
- A finality rule that makes small panels safe by waiting longer, and a lone verdict safe by waiting for its challengers.
- Parameters chosen by simulation before any contract code, with every acceptance threshold published before the run that judges it.

**Non-goals:**
- On-chain verification of TEE quotes: the drawn panel checks them off-chain and the hash is published, as in #85, because a TDX or Nitro quote costs millions of gas to verify.
- Identity or proof-of-personhood for operators: the declared operator account is a disclosure, not a proof. The defences against one party running many nodes are economic (bonds) and technical (attestation, host and TEE caps).
- Token rewards, including the validators' token slice (#142).
- Any governance key, vote or DAO power over the contracts.

## Decisions

### D1. Two new contracts; v2 left alone
- **`Validators`:** the registry, bonds, candidate/active/leaving state, qualification counters, unbonding and slashing hooks.
- **`Panels`:** k, the seed, the draw, seal and reveal bookkeeping, replacement, windows, holds and finality.
- **The race:** `RaceV3`, the successor of `RaceV2`, calls `Panels` the way `RaceV2` calls `Verdicts`. `Heads`, `Pool` and `QuoterV2` are reused where their interfaces fit.
- **Fees:** `FeesV3` keeps v2's formula (median usage at unit prices, plus one service fee per counted judge) and replaces its signed price updates with D9.
- **Why not modify `Verdicts`:** v2 is keyless and deployed. Changing it means a new version anyway (D15), and splitting the registry from the draw keeps each contract under EIP-170. `RaceV2`'s initcode is already 47,886 of 49,152 bytes.
- **Alternative rejected:** an upgradeable proxy. It brings an upgrade key, against D15.

### D2. k from bond-tiered counters, with sampling under the caps
k must follow "eligible validators", and eligibility depends on:
- the bounty, through the bond factor;
- the parties;
- the caps.

A full pass over a large registry is too expensive on-chain.

**On registration and bond changes,** `Validators` keeps one counter of active validators per **bond tier**. The tier steps are every bounty limit in the k table, at every level ($10, $25, $50, $125, $250, $312.50, $625; #141). A validator is eligible for a bounty if its bond is at least `BOND_FACTOR` × the bounty's tier, the smallest step at or above the bounty. The steps don't depend on the panel's level, which is known only after the draw.

**At the draw:**
1. Read the counter for the bounty's tier, giving n.
2. Start from k₀ = the largest odd number ≤ min(n, `K_MAX`), within the k-table's bounty limit.
3. Fill the panel by **rejection sampling:**
   - index = keccak(seed, counter) mod (tier size);
   - skip parties, duplicates and cap violations;
   - stop after `DRAW_TRIES` × k₀ tries.
4. If the panel can't be filled, step k down by 2 and continue the same sample.
5. If the panel's proof level (D10) can't judge the bounty, the draw is void and the submission waits. It's drawn again, with a fresh seed, when the registry changes (#141, gap 12).

k is fixed when the draw transaction completes, before anyone has judged.

- **The draw is a view function,** so anyone can recompute it from the seed and the registry snapshot. Snapshot: the registry's state is versioned by an epoch counter bumped on every change, and the draw records the epoch it used.
- **`DRAW_TRIES` is a fixed gas bound,** not a tuning parameter. #134 found 8 and 1,000 tries give the same share of lowered draws (36.6 % against 36.5 %): the caps bind, not the tries.
- **Alternative rejected:** a Fisher-Yates shuffle over all active keys, as v2 does. It's O(N) storage reads, fine for 7 seats, not for hundreds of validators.
- **Alternative rejected:** an off-chain draw with an on-chain proof. More moving parts, for no gain at these sizes.

### D3. The seed comes from a later block
- **seed = keccak(blockhash(sealBlock + `SEED_DELAY`), submission commitment, bounty, submission id).**
- The draw can be called by anyone from block sealBlock + `SEED_DELAY` + 1. It must happen within 256 blocks; after that it re-targets to the latest block plus `SEED_DELAY`.
- **Why a fixed later block and not `prevrandao` at call time:** with `prevrandao`, whoever calls the draw picks the block, and can wait for a good one. A block hash fixed in advance removes that choice. #134: with the seed fixed at the seal, the grinder gains five times as much (+$1,306 against +$258).
- **Remaining influence:** the block's proposer, or an L2's sequencer, can influence its own block hash at the cost of the block. That's tracked as a risk, with a randomness beacon (drand, or a VRF) as a later option behind the same interface.

### D4. Finality waits longer for small panels, and a lone verdict waits for its challengers
- **A verdict becomes final when its panel's `CHALLENGE_WINDOW[k, level]` passes** with no challenge upheld. The race's first instalment starts at finality. Judges' fees are paid when the verdict is posted (`Fees.settle`, as in v2); only the bounty's payment waits.
- **A k = 1 verdict is held (#141).** Its window runs only while at least `CHALLENGE_K[1]` validators are eligible for its challenge panel: active, outside its panel, not a party, bonded for its bounty. Until then it isn't final and nothing is paid.
  - **Why:** in #134, about half the colluding genesis's bad fixes were never re-run in 72 hours. The other half waited, frozen, for validators that never qualified. Holding the payment until a challenge could be judged leaves the colluder only the fixes its audit (D13) and challengers miss.
- **Each validator has at most `K1_PENDING_MAX` (10) k = 1 verdicts not yet final.** At the cap it isn't drawn at k = 1.
  - **Why:** faults pending together share one bond, so a batch costs at most the bond. That's why the whole-bond row hardly differed in #134 (+$2,707 ± 512).
  - **Sizing:** with the whole bond as the slash (D16) and every k = 1 verdict audited once (D13), a bad fix survives its audit and challenge about 1 time in 8 (re-runs are right 90 % of the time in the report's world; round 1's re-run reversed 86.6 %). A batch of N bad fixes at the $50 limit then gains about N × $6, against the $100 floor bond: 10 leaves a factor of about 1.6. With two audits (round 2) a bad fix survives about 1 time in 25, N × $2, and 10 leaves a factor of 5.
  - **Alternative (switch `K1_BATCH_BOND`):** no count cap, but a bond of at least `BOND_FACTOR` × the sum of the validator's pending k = 1 bounties.
- **k = 1's window is at least 7 days:** 168 h at level A, 336 h at B and C. In #134 the colluder gained +$723 at 7 days against +$2,920 at 72 hours, and from 7 days qualification recovered and no challenge stayed frozen. The other windows are unchanged.
- **A challenge is judged by a fresh panel larger than the original.** It's `CHALLENGE_K[k]` validators drawn outside the original panel and not parties, with D2's sampling. If fewer are eligible, it's the largest odd number they allow, as long as that is larger than k (`K_MAX` for a panel of `K_MAX`). Otherwise the challenge waits, and the window is frozen, so a verdict can't become final while a challenge is pending.
- **Stakes and payouts follow the existing `challenges` spec:**
  - a rejected challenge costs the challenger its published share;
  - an upheld one pays the challenger from the forfeited stake and the escrowed reward.
- **The cost** is liveness while the network is small. An honest k = 1 fix is paid only once three more validators qualify, and a validator at the cap judges no new small bounty until its verdicts are final. The re-run measures the days from verdict to payment (task 6.3).
- **Measured, and accepted (owner, round 2):** an honest k = 1 fix was paid a median 19.0 ± 3.6 days after its verdict (90th percentile 46.1 days, against 3 days without the hold); 65 % ± 8 of k = 1 verdicts were held, for 19.3 days on average. k = 1 was 2 % of the panels drawn in the year, and only the bounty waits. Since k is 1 only when one or two validators are eligible, a k = 1 window starts at its reveal only when the caps or the pending cap stepped k down while three challengers existed.

### D5. Qualification by shadow judging
- **When a submission is drawn,** `Panels` also draws up to `SHADOW_PER_DRAW` candidates (same seed, separate counter) as shadow judges.
- **When a submission waits** for a panel, `Panels` draws `SHADOW_PER_WAITING` (3) candidates as its shadows (#141).
  - **Why:** in #134 shadows came only with drawn panels, so on a small network few candidates had anything to judge: 18 of 54 newcomers qualified in a year, after 135 days, while 68 % of submissions waited.
  - **Required, not only faster (round 1's re-run):** under the hold, without them the genesis reaches its 10 pending k = 1 verdicts after 20 shadow seats, no candidate reaches 20 scored verdicts, and no run reached k ≥ 3 (`SHADOW_PER_WAITING` 0).
- **Shadows** seal within the same seal window and reveal after it, like counted judges. `Panels` records their reveal and their agreement with the outcome they're scored against.
- **What a shadow verdict is scored against (#141).**
  - **The rule:** only an outcome no lone validator set. That's the final outcome of a panel of k ≥ 3, or of a k = 1 verdict whose window started at its reveal because three challengers were already eligible (D4).
  - **A k = 1 verdict held at its reveal, or a waiting or withdrawn submission:** scored **once**, against the majority of the verdicts sealed on that submission (the counted judge's, if any, and the shadows'), when at least 3 were revealed. Otherwise it doesn't count toward `QUALIFY_VERDICTS`. It isn't scored again when a held verdict later becomes final (round 2: the reading round 1's re-run ran, now in the spec).
  - **Why:** in #134 the colluding genesis set the outcomes candidates were scored against, so honest shadows failed `QUALIFY_AGREE`. Under the hold, no k = 1 verdict is final until three more validators are active, so without the majority rule the first three could never qualify.
  - **Why it can't be copied:** every verdict in the majority is sealed before any is revealed.
  - **Who passes:** an honest candidate (90 % accurate) agrees with a majority of 3 that includes it about 97 % of the time, or 91 % when the third verdict is a colluder's. One guessing at random agrees about 59 % of the time, below `QUALIFY_AGREE`.
- **A candidate becomes active** when it reaches `QUALIFY_VERDICTS` scored shadow verdicts with reveal rate ≥ `QUALIFY_REVEAL` and agreement ≥ `QUALIFY_AGREE`. If it fails, it may try again after `QUALIFY_COOLDOWN` (7 days).
- **Paid:** shadows get their metered usage, but no service fee. The solver's deposit already covers counted judges; shadows are paid from the sponsors' pool, at most the seated shadows' quoted usage per draw.
- **Bootstrapping:** the genesis validator's panels and the waiting submissions give the first candidates something to shadow.
- **Alternative rejected:** a fixed canary set committed at deployment. Its answers become public after the first use, and someone would have to write and keep it fresh, which is a privileged role.

### D6. Caps per panel, read from attestation and receipts
- **Operator:** at most 1 validator per declared operator account per panel.
- **Infrastructure host and model family:** at most `(k − 1) / 2` per panel (no limit at k = 1), so none of them can hold a majority by itself.
- **TEE type:** at most `(k − 1) / 2` per panel, **from k = 3 while at least `TEE_CAP_K3_TYPES` (5) TEE types are accepted, and from k = 5 while fewer are** (round 2). `TEE_CAP_FROM_K` follows the constitution's list from the next draw.
  - **Why from k = 5 with fewer types (#141):** with 3 accepted TEE types, a panel of 3 needs exactly one of each. #134 found the caps lowered k on 39 % ± 9 of a growing network's draws, and 72 % of the draws that could have been k = 3 ended at k = 1.
  - **The cost with fewer than 5 types:** two validators of one TEE type can hold a k = 3 majority. In round 1's re-run, with three types and the cap from k = 5, one TEE type held the majority of **77 % ± 8 of the panels of 3** on a growing network (11.1 % ± 2.8 of all panels of k ≥ 3). A flaw in one vendor's chip could decide those panels, within k = 3's limits ($250 at level A, $125 at B) and windows (24 h, 48 h).
  - **Why from k = 3 with five types (round 2):** five types spread evenly, with the cap from k = 3, gave no one-type majority; the caps lowered 6 % ± 1 of draws (13 % ± 3 with three types from k = 5); 22 % ± 3 of submissions waited (21 % ± 3); and bad fixes merged fell from 0.22 to 0.12 per 100 paid. An even spread is the kind case: round 2's run adds a skewed one.
  - **Who counts:** a level C validator has no TEE type, and a TEE type added by ADR is its own type.
- **What a TEE type is (round 2):** each attestation scheme, meaning a TEE technology with its own attestation format and signing root, is its own type, even when one vendor makes several: Intel SGX and Intel TDX are two. One technology is one type in every cloud and on bare metal, since one flaw breaks it everywhere; the host cap keeps the clouds apart. A confidential GPU's attestation isn't a type: the node's code runs in the CPU's TEE, so it counts under that type.
- **The TEE types that exist,** from the author's knowledge, not checked against current vendor documentation; the ADR (#137) confirms each, by region:

  | TEE type | Attestation signed by | Level A: in a cloud | Level B: elsewhere | At launch |
  |---|---|---|---|---|
  | **Intel TDX** | Intel (TDX quote) | confidential VMs on Azure and Google Cloud, among others | Xeon servers with TDX (D12) | **yes** |
  | **AMD SEV-SNP** | AMD (a report signed by the chip's own key) | confidential VMs on AWS, Azure and Google Cloud | EPYC servers from Milan on (D12) | **yes** |
  | **AWS Nitro Enclaves** | AWS (the Nitro attestation document) | EC2, including the Graviton instances the kit plans (#94) | none: AWS only | **yes** |
  | **Intel SGX** | Intel (SGX quote, DCAP) | some cloud machine types, such as Azure's DCsv3 | Xeon servers; Intel removed it from consumer chips | possible, not at launch: the node needs a library-OS port (such as Gramine), and SGX has the longest record of side-channel breaks |
  | **IBM Secure Execution** | IBM | IBM Cloud's Hyper Protect servers | IBM Z and LinuxONE machines | unlikely: the node and every sandbox image need s390x builds |
  | **Arm CCA** (realms) | the chip vendor's key, per Arm's architecture | none known (to verify) | early Armv9 hardware, if any (to verify) | no |
  | NVIDIA confidential GPUs (H100 and later) | NVIDIA | GPU confidential VMs, always beside a CPU TEE | the same | not a type: counts under its CPU's TEE |

  Not accepted: AMD SEV and SEV-ES without SNP (no memory integrity), and a virtual TPM alone, such as a cloud's trusted launch (it measures the boot but doesn't isolate the VM from the host).
- **At launch, three types are realistic:** Intel TDX, AMD SEV-SNP and AWS Nitro Enclaves. **So the TEE-type cap starts at k = 5,** and the one-type majority of about 77 % of panels of 3 is a named trust point until adding ADRs (from 21 eligible, D7) bring the list to five. SGX is the likeliest fourth type; a fifth needs IBM Secure Execution, Arm CCA, or a scheme not yet offered.
- **One vendor's types can share a flaw:** SGX and TDX run on the same Intel cores, so a CPU side channel can hit both, and Nitro Enclaves run on Intel, AMD or Graviton hosts. Each scheme counts as its own type, as the owner decided; whether two types of one vendor may hold a k = 3 majority is an open question.
- **Where the values come from:**
  - the host and TEE type come from the attestation recorded at registration;
  - the model family is declared, and the receipt must match it (judge-panels, "A counted verdict carries proof"). Changing family means registering again (gap 17).
- **Effect on k:** the caps are checked during D2's sampling, so they can lower k (spec scenario "Too few distinct hosts").

### D7. The constitution tier is always `K_MAX`, drawn from a network three times its size (twice for removals)
- ADRs and escalated fixes draw exactly `K_MAX` under the caps, and pass with `CONSTITUTION_QUORUM`.
- **Drawn only when enough validators are eligible (round 2; #141 drew every ADR from 14):**
  - **an ADR that adds or loosens anything, and any escalated fix:** at least `CONSTITUTION_MIN_ELIGIBLE` = 3 × `K_MAX` (**21**);
  - **an ADR that only removes** (a TEE type, proof type, notary or image digest) **or raises a firmware minimum:** at least `REMOVAL_MIN_ELIGIBLE` = 2 × `K_MAX` (**14**). It can't admit anything or move money, and a broken chip can't wait for the network to reach 21 (D11).
  - **Which is which** is read from the ADR's operations. If every one is a removal or a raised minimum, it's a removal; anything else, including an ADR that removes one thing and adds another, needs 21.
  - **Expiry (#141):** an ADR or escalated fix submitted while fewer are eligible expires unjudged. It's never drawn, its fees and deposit are refunded less what was metered, and it may be submitted again.
  - **Why expiry:** in #134 no ADR passed before `K_MAX` were eligible, but the queue was drawn the moment the seventh qualified, when the panel was the whole network and five early validators were most of it (+$5,196 ± 2,178). Expiry leaves no backlog to draw at the moment a coalition's share is highest.
- **A rejected ADR forfeits `ADR_DEPOSIT` ($15, round 2)** to the sponsors' pool, at its first judging or after a challenge. It's refunded when the ADR takes effect or expires. **An escalated fix posts the same deposit (owner, 2026-11-03)**, beside its attempt fee and check deposit. It forfeits it to the sponsors' pool when the constitution tier rejects the fix, and gets it back when the fix is accepted or expires. Without it, a coalition would simply send rule changes as escalated fixes instead of ADRs. **Forfeits never go to the issue's funder or reporter:** an attacker could fund or open the issue itself and get its own deposits back. The sponsors' pool belongs to no account.
- **Why both: neither alone makes a coalition of 5 lose.** Round 1's re-run (5 early validators, an ADR worth $1,000 to them each week), and the same rows with a $15 deposit taken from each rejected ADR:

  | Threshold | Return − twin's (report v2) | ADRs judged / passed | With a $15 deposit (derived) |
  |---|---|---|---|
  | #134's: from `K_MAX`, ADRs wait | +$5,196 ± 2,178 | 45.4 / 5.28 | about +$4,594: it would need $184 an ADR |
  | from 14 | +$622 ± 260 | 42.7 / 0.70 | about −$8 ± 260: not significant, so it fails |
  | **from 21** | +$280 ± 152 | 36.0 / 0.35 | **about −$255 ± 152: it loses** |
  | from 28 | +$187 ± 138 | 29.9 / 0.25 | about −$258 ± 138, and every ADR waits longer |

  - **The threshold alone** only slows the coalition: from 21 its 5 are a smaller share, but it still passes 0.35 ADRs a year, worth $350. The first ADR is judged on day 122 instead of day 75.
  - **The deposit alone** works only when few of the coalition's ADRs pass: from `K_MAX` it would need $184 an ADR, which would also deter honest authors.
  - **Sizing:** a deposit D makes the coalition lose when its gain plus two standard errors is below D times its rejected ADRs. From 21: ($280 + $152) ÷ (36.0 − 0.35) ≈ $12.10, so **$15**, rounded up for a margin. The coalition of 3 then nets about −$429 ± 135 (from +$82 ± 135). These rows are derived from the report's table, assuming the coalition keeps submitting (stopping only lowers its gain); round 2's run measures them.
  - **The honest cost:** a good ADR is rejected when 3 or more of its 7 honest judges err, about 2.6 % of the time at 90 % accuracy: about $0.39 an ADR at $15 (hand estimate). The verdict fees are paid as Article 9 says.
  - **A v3 rule:** Article 9's fee clause is entrenched, so the deposit is part of v3's constitution, which a new version may carry (D15). v2's is unchanged.
  - **What the ADR is worth** is an assumption: $1,000 to the coalition, as in #134. A coalition valuing an ADR at more needs a deposit in proportion; the ADR (#137) names the value it sizes for.
- **Its notice** is `ADR_WINDOW` (14 days), or `REMOVAL_WINDOW` for removals, whatever its judges' levels (gap 13).
- This keeps v2's 5-of-7 guarantee for the rules themselves, even on a small network.

### D8. Sustainability without a controller
**The loop:**
1. Issues on proof-of-fix's own repository, including the contracts' next version, become bounties.
2. The sponsors' pool funds them (5.11), and anyone, a DAO included, can top up the pool.
3. Solvers fix them, open validators judge them, and fees pay the validators.
4. The canonical head moves by verdict (#85).

**No step needs the owner or a DAO to sign anything.** A DAO or legal wrapper (#126) is just a funder and, optionally, one validator. That's ADR 0003 principle 5, and rule 3 for the owner.

### D9. Prices by market rules, not by a vote
A panel voting on its own pay is a built-in cartel. So v3 splits the price into its two parts, each following a different signal (`specs/check-pricing`).

- **Pass-through unit prices: a median feed,** like MakerDAO's medianizer and Chainlink's aggregation.
  - Each active validator posts a signed table whenever it likes.
    - **Every unit, every validator (#141):** its own costs for the shared units (sandbox time, storage, gas), and **every model family's public list price** for tokens. A table missing a unit doesn't count.
    - **Why:** in #134, 3 validators of one family could set its token price (+$42 ± 22, the price at 1.16 × instead of 0.98 ×). With every family's list price posted by everyone, the gain disappeared (−$3 ± 14).
    - **An open-weight family** is posted at the price of a public hosted endpoint for it.
    - **Families aren't listed** (D19): a table prices every family already priced, and may price new ones.
  - At the end of each `PRICE_PERIOD`, each unit's price moves toward the median of the latest tables, by at most `PRICE_STEP_MAX`, never above `PRICE_CAP_X` × genesis, and only if at least `MEDIAN_MIN_POSTERS` posted.
  - **For an even count, the median is the lower middle value** (`MEDIAN_LOW_EVEN`): it halved the inflaters' gain alone.
  - The median resists any minority. Moving it takes half the counting validators, which the caps and bonds make expensive.
- **The service fee: a queue controller,** like EIP-1559's base fee, which moves by at most 12.5 % per block toward a target fullness.
  - **Start:** `FEE_START` = `FEE_CEILING` (#141). Started at v2's $0.05, validators left faster than a 5 % daily step could climb back, and 28 of 40 runs collapsed below 3 validators.
  - **At the end of each period:**
    - it rises `FEE_STEP` if the share of submissions that waited for a panel exceeded `WAIT_HIGH`;
    - otherwise it falls `FEE_STEP` if the share of active validators not drawn exceeded `IDLE_HIGH` (**40 %**, #141);
    - it stays within [`FEE_FLOOR`, `FEE_CEILING`].
  - **Every wait counts (round 2):** a submission counts once, in the period it starts waiting for a panel, whatever its bounty, and a counted panel stalled for want of a replacement counts once (`WAIT_SIGNAL` "every").
    - **Why not round 1's signal:** it counted only waits that one more validator bonded at `BOND_FLOOR` could end. With bond tiers, such a newcomer can judge bounties only up to $50, so waits for larger ones never raised the fee. `IDLE_HIGH` lowered it from the first weeks, validators left, larger bounties waited, and nothing pushed the fee back up: 33 of 40 runs collapsed below 3 active validators.
    - **Evidence:** with every wait counted and round 1's other rules, no run collapsed, and over the last 13 weeks the fee was $0.186 against a $0.154 break-even, 1.21 ± 0.04 ×. That's inside `FEE_MARGIN`, with its upper bound at the margin itself. The any-bond signal came closer to cost (1.08 ± 0.07 ×), but 1 run of 40 collapsed.
    - **Why #134's concern no longer applies:** in #134, 99 % of the waits at the ceiling were bounties above $125, needing large bonds that v2's outage slash (a share of the bond) made unprofitable. D16's slashes are flat, so a higher fee now makes large bonds worth posting.
    - **The cost:** a spammer submitting to a bounty no panel can judge also raises the fee. Each spam submission pays the attempt fee; on #134's every-wait market the spammer lost −$608 ± 19. Round 2's run measures it again.
  - **Why `IDLE_HIGH` 40 %:** under free entry, validators stopped entering at about 30 % idle, so 80 % never fired. At 50 % (without the outage slash) the fee settled at $0.227, $0.04 above break-even. At 30 % it overshot, and 2 of 40 runs collapsed. 40 % is the starting value; the re-run swept 30–50 %, and idling measured over 7 days instead of one (`IDLE_WINDOW_DAYS`). Round 1's re-run: 40 % works only with a wait signal that can raise the fee.
  - **Steps stay symmetric.** A faster rise (`FEE_STEP_UP`) is a switch, not the rule. Starting at the ceiling removes the climb back that motivated it, and under a noisy signal unequal steps ratchet the fee up.
  - **Open entry closes the loop:** a high fee attracts validators, the waiting falls, then the fee falls.
    - **Where it settles:** near validators' **average (break-even) cost**: their overhead plus fixed costs and the bond's capital spread over their checks. It can't settle at marginal cost: under free entry, any margin over marginal cost is spread over idle validators (report, gap 4).
    - **The published target:** the fee within `FEE_MARGIN` (25 %) above break-even (D17).
- **Quotes are stable:** an attempt is charged the prices in effect when it started, so the quoter's deposit stays right.
- **Alternatives rejected:**
  - **A panel vote with bounds** (v2's rule, drawn instead of seated): still a cartel, just a bounded one.
  - **Per-validator asks with selection by price** (Akash, Filecoin, Livepeer): with a random draw, cheaper validators being drawn more often rewards running many cheap nodes, which defeats the caps.
  - **A solver's tip to jump the queue:** not needed while the queue only waits for panel size. It can be added later behind the same fee interface.
  - **A `FEE_FLOOR` near break-even:** a price fixed per version, which can't follow costs. The floor stays a safety bound ($0.01).

### D10. Proof levels: TEE in a cloud, TEE elsewhere, zkTLS anywhere
Both proof types are accepted, and neither is required (owner, 2026-11-02).

**At launch only levels A and B are accepted (owner, 2026-11-03).** zkTLS (level C) is built into the contract code from deployment but is not on the constitution's list. It is switched on later by an adding ADR (D11) once both hold:
- task 1.9 (#135) shows listed notaries work for the model calls the checker makes;
- #125 shows an open-weight model gives reproducible verdicts, or a measured borderline rate at which answer shopping loses under level C's limits.

**Why:** the genesis must be at A or B anyway, and a launch without C carries no answer-shopping trust point. Keeping C in the code keeps the path to validators that need no chip maker or cloud, without a migration (D15). What a panel may judge, and how long its verdict waits, depends on **how strong its proof is**, not just on its size.

| Level | Proof | What's proven | Who could cheat |
|---|---|---|---|
| **A** | a TEE plus the cloud platform's own attestation (AWS Nitro; Azure or Google Cloud confidential VMs) | the official code ran, its one model call, its tests, and its secrets kept | only the cloud company, colluding; the validator has no physical access |
| **B** | a TEE whose location isn't proven: a home server or rented bare metal with TDX or SEV-SNP | the same as A, unless the chip is broken | a validator with physical access and hardware skills: 2025 research extracted TDX and SEV-SNP secrets with a cheap device on the memory bus |
| **C** | zkTLS on any machine | the model's answer came from the provider; the tests are checked only by re-run challenges | any validator: it can lie about tests (caught by re-runs) or call the model several times and keep the answer it likes (undetectable per call) |

**How the levels apply to panels:**
- **A panel's level** is the lowest level held by a majority of its judges. Any mix is allowed, including all level C, so ordinary PCs alone can run a grown network.
- **Each (k, level) pair** has its own largest bounty and challenge window (Parameters).
- **The genesis validator must be at level A or B (#141).** With a genesis at C, k = 1 may judge only $10 against a median bounty of $86. Nobody qualifies, and 96 % of submissions are withdrawn, in every run. An all-C network works once grown (4 % wait), but only a genesis at A or B can grow one.
- **Hidden tests and private repositories** go only to panels whose every judge is at level A or B, since a level C node could read them.
- **Answer shopping is the remaining trust point at level C (#141).** Retrying the model can't be proven per call, and a shopped verdict carries a valid receipt, so nothing is slashable.
  - **What v3 does:** it bounds shopping by the majority of independent judges, level C's limits, and **an audit of every non-unanimous pass by a level C panel** (D13). The shopper's flips decide only split panels, and the audit is one more honest call.
  - **What remains trusted:** that a borderline fix rarely fools one honest model call. In #134, shopping on a grown all-C network didn't pay at 1 in 10 (−$2 ± 14). At 3 in 10 it gained +$328 ± 69.
  - **What v3 doesn't measure:** the real rate. #125 or task 1.9 could. The re-run reports both rates, and the acceptance criteria count 1 in 10 (D17).
  - **Alternative (switch `C_LIMIT_X`):** halved level C limits.
  - **Rejected:** split level C passes needing a TEE judge. About half of 7-judge verdicts are split at 90 % accuracy, so an all-C network would stall.
- **zkTLS mechanics:**
  - proofs come from notaries on the constitution's list; several are listed, none is required, and we run none as a required service;
  - **the first list** comes from the parameters ADR (#137), after #135's spike (task 1.9) measures candidates. The simulation uses three placeholders.
  - the provider needs no support, since zkTLS works with any HTTPS API;
  - receipts report each test's pass or fail, not raw output, so flaky timestamps don't create false alarms.
- **Firmware (TCB) minimums:** for each TEE type, the vendor's level that fixes every flaw published before deployment, named in the deployment record. The simulation uses level 1 of each.
- **Optional extra:** a level A or B node may also attach a zkTLS proof of its model call, so the AI part doesn't rest on the chip alone.
- **Verification:** like TEE quotes, the proofs are checked off-chain by the drawn panel, and their hashes are published.

**Alternatives rejected:**
- **TEE only:** it keeps ordinary hardware out, against ADR 0003.
- **zkTLS only:** no hidden tests, no protection against answer shopping, and slow finality for every bounty.
- **zkTLS as a capped minority** (the first draft): a network of only ordinary PCs couldn't judge anything.

### D12. Running a node without a cloud
- **The node is one container plus a watcher** (#123). At home, the watcher is a cron job or systemd timer that polls `Panels` every minute. The node stays up, since idling at home costs little; on AWS, Lambda only existed to wake a stopped server cheaply.
- **Level C:** any machine with Docker.
- **Level B:**
  - a server-class CPU: Intel Xeon with TDX (4th generation onward) or AMD EPYC with SEV-SNP (Milan onward);
  - consumer Core and Ryzen chips don't qualify, and Intel removed SGX from consumer chips;
  - a used EPYC server, a rented bare-metal server or a confidential VM all work.
- **Level A:** a cloud confidential VM or AWS Nitro, with the platform's attestation.

### D11. Removing a broken type is fast; adding one is slow
- **An ADR that removes** an accepted TEE type, proof type, notary or image digest, or raises a TEE type's minimum firmware (TCB) level, takes effect after `REMOVAL_WINDOW`. An exploit published for a chip can't wait 14 days.
- **An ADR that adds** one takes the full challenge window (14 days, #85).
- **Removal is still an ADR** at the constitution tier (5 of 7). The per-type caps mean no group can remove competitors' hardware to take over a majority of any panel.
- **A removal is judged from a smaller network** (round 2): an ADR that only removes, or raises a minimum, is drawn from 14 eligible validators; any ADR that adds, from 21 (D7).
- **What happens to the validators:** validators of a removed type, or below the new firmware minimum, stop being drawn and keep their bonds. Chip makers' own revocations of compromised machines are honoured at registration.
  - **After a raised firmware minimum** (#141, gap 6): a validator that updates and attests again returns **without qualifying again**. Its key, bond, model and code are unchanged.
  - **After a removed TEE or proof type:** it registers again with an accepted type, and qualifies.
- **Switching on a proof type already in the code** (owner, 2026-11-03) is an adding ADR. The constitution only switches verifier paths on or off; it can never add verifier code, since that would let a coalition install a fake verifier. New verifier code means a D15 migration, which every user sees in advance.
- **Receipts name their proof** (owner, 2026-11-03): a receipt carries its proof-type id, the model id and a hash of its weights where public, the inference image's digest, the seed, and the prompt's and answer's hashes, beside the proof bytes. A proof type for re-runnable open models (#125) can then be switched on later without a new receipt format, if its verifier is in the deployed code.
- **A delisted notary** (gap 14): verdicts revealed before the removal takes effect still count, and nobody is slashed for them. After it, that notary's proofs don't count.

### D13. Random audits, so someone is always watching
- **The problem:** optimistic checks (re-run challenges) only work if someone re-runs. When cheating is rare, nobody bothers, and then cheating pays: the watcher's dilemma.
- **The fix:** `AUDIT_RATE` of submissions are drawn for audit by the same seed. One eligible validator outside the panel re-runs the whole check and seals its own result. A mismatch opens a challenge with no stake from the auditor.
- **`AUDIT_RATE` is 10 % (#141).**
  - **Evidence:** in #134, 2 % deterred a lazy cheater, but a cheater bribed $5 a cheat wasn't significantly deterred at 5 % (−$34 ± 47) with nobody volunteering. It was at 10 % (−$137 ± 64).
  - **The cost:** $0.018 a check, against $0.0089 at 5 %.
- **Always audited (#141), beside the random share:**
  - **every k = 1 verdict, twice (round 2),** by two different validators outside its panel and not parties, each drawn by the seed as soon as it is eligible. Its hold (D4) keeps it unpaid until three challengers are eligible, so both audits come before payment. Each auditor re-runs on its own; a mismatch from either opens a challenge.
    - **Why two:** with one audit (#141), 86.6 % ± 5.1 of the colluding genesis's bad fixes were reversed before payment, under `LONE_CATCH_SHARE` (90 %), as D17's own estimate (87 %) predicted. Two independent auditors, each right 90 % of the time, both miss a bad fix 1 time in 100, and a challenge panel of 3 upholds a mismatch 97 % of the time: about 96 % reversed (estimate).
    - **The cost:** one more check per k = 1 verdict, and k = 1 was 2 % of the panels drawn in a growing network's year, so under $0.01 a check on average.
  - **every non-unanimous pass by a level C panel** (D10).
- **Funding:** audits are paid like any check, from the fees. An auditor earns its metered usage, the service fee, and a share of any slash it leads to, so auditing is itself a way to profit.
- **Why it matters more with open-weight models (#125):** if a pinned open model gives the same verdict when re-run, an audit can prove a wrong AI verdict, not just a wrong test result, and that becomes a slashable fault. The determinism experiment in #125 decides whether a later version adds that rule. This change doesn't assume it.

### D14. Model scores change pay and eligibility, not votes
**Owner (2026-11-02):** a validator without money can use a frontier model through its API, since the check fee repays its tokens. A validator with a GPU can run an open-weight model. The market should reward whichever judges better per inference.

- **The score:** each family's agreement with final outcomes over its last `SCORE_WINDOW` **counted** verdicts (`specs/judge-scores`). Shadow verdicts never enter it (#141).
  - **Balanced (round 2, `SCORE_BALANCED`):** the mean of its agreement on passed outcomes and on failed outcomes, or the agreement on the one kind present. An honest family scores about its accuracy, whatever the share of passes; a family that always votes pass scores 50 %.
  - **Why:** an always-pass herder agreed with outcomes 78.5 % ± 0.5 of the time in round 1's re-run, above `SCORE_MIN` (70 %), and the weak family's herders gained (+$13 ± 2 on the flat fee, +$80 ± 9 at $0.25, +$202 ± 19 on a working market). Balanced, the same herders score 50.1 % ± 0.1, the weak family is barred 87 % of the year, and every herder row loses: −$8 ± 1, −$54 ± 6 and −$69 ± 10 (`mid`'s herders −$57 ± 4). Nothing else measurably changed: 1.30 against 1.33 bad fixes merged per 100 paid, $0.353 against $0.354 of service fees a submission.
  - **Why not public leaderboards:** they measure other tasks, can be gamed, and are run by one organisation.
  - **Why not canaries yet:** known-answer cases need someone to write them and keep them secret, which is a privileged role, and a canary's poster could tip off validators. Keyless canaries, for example mutations of past merged fixes generated by the official code from the chain's seed, are a separate research item (#136). Scores can add them later without changing this rule.
- **Eligibility:** a family below `SCORE_MIN` over at least `SCORE_MIN_VERDICTS` counted verdicts isn't drawn for counted panels. Its validators shadow-judge.
- **Recovery is decided by shadow verdicts alone (#141), on fresh blocks (round 2).**
  - **The rule:** from its barring on, a barred family's shadow verdicts are taken in consecutive blocks of `SCORE_RECOVER_VERDICTS` (100), each scored once, when complete, as the counted score is. The family is drawn again when a block reaches `SCORE_MIN` + `SCORE_RECOVER_MARGIN` (10 points: 80 %).
  - **After it recovers:** its counted window restarts. Until it holds `SCORE_MIN_VERDICTS` new counted verdicts, it's paid at `SCORE_FACTOR_MIN`, so recovering doesn't buy the neutral start.
  - **Why shadows alone (#141):** in #134 the window merged shadow and counted verdicts. A weak family's herders, herding as shadows (never re-run), lifted its score from 66 % to 74 %, over `SCORE_MIN`. It was barred 17 % of the year instead of 85 %, and herders gained +$294 ± 28 on a moving market while bad fixes merged tripled.
  - **Why fresh blocks with a margin (round 2):** round 1 tested the last 50 shadow verdicts at each new one, at `SCORE_MIN`. A family right 68 % of the time passes that test about 40 % of the time at any moment, so it passes within a few verdicts: the weak family recovered 10.8 times in a year and was barred only 58 % of it. A block judged once can't be retried verdict by verdict, and the margin puts the bar above chance (hand estimates, normal approximation, the balanced score at the report's 78 % passed outcomes):
    - a 68 % family passes a block of 100 at 80 % about 1.9 % of the time. At round 1's pace (10.8 recoveries of at least 50 shadow verdicts each in 58 % of a year), a family barred all year fills roughly 10 to 15 blocks: about 0.2 to 0.3 recoveries a year, against 10.8;
    - a family whose model improved to 85 % passes its first block about 87 % of the time; one at 80 %, half the time.
  - **Alternative (switch):** a fresh block of a full `SCORE_WINDOW` (200) at + 5 points (75 %). About the same chance recoveries (4.7 % a block, half as many blocks), and kinder to a family that improved only to about 78 %, but every recovery takes twice as many shadow verdicts.
- **Pay:** the service fee is multiplied by the family's score factor.
  - **The raw factor** is linear from `SCORE_FACTOR_MIN` at `SCORE_MIN` to `SCORE_FACTOR_MAX` at 100 %.
  - **Normalised each pricing period (#141):** raw factors are divided by their mean over the previous period's counted seats, then bounded by [`SCORE_FACTOR_MIN`, `SCORE_FACTOR_MAX`].
  - **The neutral factor (1 ×)** is therefore the network's mean, and a new family is paid 1 ×.
  - **Why:** with the neutral point at 80 %, below a typical family (84–94 %), pay by score raised service fees per submission by 39 % ($0.499 against $0.358). Normalised, quality still sets relative pay, and solvers pay the market fee on average.
  - **Metered usage** is always repaid in full, so a frontier model's higher token cost never falls on the validator.
- **Changing model family means registering again** (a new key that qualifies): the score, the caps and qualification are all per family.
- **Votes stay one per judge.** Weighted votes would let one top family override a panel, and amplify its blind spots, such as a prompt injection that fools that model. A wrong score would also change verdicts directly instead of only changing who earns what. #134 found no significant gain from weighting (bad fixes 1.31 ± 0.10 against 1.26 ± 0.12 per 100 paid).
- **Diversity pays:** the per-family cap ((k − 1) / 2 per panel) means that if everyone moves to the top family, its validators are drawn less often and earn less. Other families then become worth running, so the market doesn't collapse onto one model. #134: after a year of moving, 2.7 families held at least 10 % each, with 11.6 % ± 5.5 of submissions waiting.
- **Trust is quality times proof:** the score measures quality; the proof level (D10) measures how checkable a verdict is. If #125 shows open-weight verdicts can be re-run exactly, a later version can add a "re-executable" proof level, where a wrong AI verdict is a slashable fault.
- **Risk: herding.** Scoring agreement with outcomes rewards guessing the majority. Sealed votes make the majority hard to guess. Reversals by challenges and audits (D13) count as the truth, so a herd that is wrong loses score.
  - **A herder that always votes pass** agreed with outcomes about 78–80 % of the time in every #134 row, whatever its family. That's the share of passed outcomes, above `SCORE_MIN` (70 %).
  - **So the score is balanced (round 2):** an always-pass family scores 50 % on it, and an honest one its accuracy. Plain agreement is the switch.

### D16. Slashing in v3 (#141)
v3 sets its own slashes; v2's `BAD_RECEIPT_SLASH_BPS` and `NO_REVEAL_SLASH_BPS` stay v2's (D15). A validator is slashed only for a provable fault. A wrong verdict given in good faith with a valid receipt is never slashed.

| Fault | v3's slash | Evidence (#134) |
|---|---|---|
| **A false verdict:** an upheld receipt challenge, meaning a receipt a re-run disproves, a vote against its own receipt, a model outside the declared family, or a call through a gateway | **the whole bond** (`FALSE_VERDICT_SLASH_BPS` 10,000) | at 20 % the seed grinder gains +$258 ± 79; with the whole bond it loses (−$378 ± 103), and the spread sybil loses −$14,082 ± 2,398 against −$1,494 ± 486. The `BOND_FACTOR` rationale ("a fault sold on the bounty, proven half the time, loses money") already assumes it. |
| **Equivocation,** or a reveal that doesn't match its seal | the whole bond (`EQUIVOCATION_SLASH_BPS`, as v2) | unchanged |
| **A sealed vote not revealed** in time, by a counted judge | a flat **`SEALED_NO_REVEAL_SLASH` = $5** (round 2; #141: $1) | see below |
| **A failed availability challenge** | v2's share (#85 S16) | unchanged |
| **Silence:** a drawn counted judge that never seals | a flat **`SILENCE_SLASH` = $5** (round 2; #141: none). It's also replaced from the same sample, and counts a miss toward the reveal-rate floor | see below |

Shadow judges aren't slashed for silence or withholding: a miss counts against their qualification's reveal rate.

- **A reveal missed after the majority revealed (owner, 2026-11-13, option 2 of #227):** when a counted judge sealed but didn't reveal in time and the verdicts revealed with receipts already hold (k + 1) / 2 on one side (at the constitution tier, the threshold of 5 passes, or 3 fails), it pays `SEALED_NO_REVEAL_SLASH` and counts a miss as before, but isn't replaced: the verdict counts with the revealed majority. **Why:** a replacement seals after the others' reveals are public, so it can copy them; this removes that copying where it couldn't change the outcome. With no majority yet, the judge is replaced as before, and a revealed majority too weak for the bounty's (k, level) limit doesn't count this way. The cost: such a verdict carries fewer independent votes (scores and audits see the revealed ones), and a level C pass counted with a missing seat is treated as split, so it's audited.

- **Why flat amounts, not a share of the bond (#141):**
  - v2's 5 % of the bond per missed seal, at 1 honest outage in 200 draws, cost an honest validator $2.05 a month against $0.74 of fees.
  - At a $1,250 bond it's $0.31 a draw, more than the fee's ceiling. So 88 % of market validators sat at $250 bonds, big bounties waited, and the fee froze at its ceiling.
  - A flat amount costs every bond the same, so large bonds stay worth posting, which the every-wait fee signal relies on (D9).
- **Why silence is slashed too (round 2):**
  - Silence gains the protocol nothing: k never shrank in round 1's re-run, because silent judges are replaced. But a bribe for silence is income. A judge bribed 5 % of the bounty (about $4 a silence) on 10 % of its draws gained +$317 ± 13 unslashed, and +$250 ± 12 at a $1 silence slash.
  - Withholding a sealed vote is the same attack one step later: +$249 ± 12 at $1, +$282 ± 12 at $0.50, and **−$20 ± 9 at $5**. Both made 63.9 bribed misses and were suspended 8.4 times, so the silent judge at $5 should land near the withholder's −$20 (round 2's run measures it).
- **Sizing $5:**
  - **The floor it must clear:** the bribe a silence or a withheld reveal earns, about $4 in the report's world, and a replacement's check (usage $0.13 plus a fee up to $0.25).
  - **The honest cost:** at 1 outage in 200 draws, $5 is about **$0.025 a draw**, about twice the node's $0.012 of overhead and about 13 % of the $0.186 fee of round 1's every-wait market. In the report's worst case, every outage slashed $5, it's $1.11 ± 0.09 a month, against $4.34 a month under v2's share of the bond. Break-even includes it, so the fee rises to cover it (D9).
  - **What it doesn't stop:** a bribe above $5 a silence still pays the judge. Silence buys only a replacement's delay (the seal and reveal windows, 3 hours), and the reveal-rate floor suspends a judge that misses more than 10 % of its draws.
- **A slash in proportion to the bounty (round 3; the value is ADR 0004's):**
  - **Measured:** at $5 the judge bribed 5 % of the bounty ($5.09 a miss) loses (−$14 ± 9), but bribed 10 % ($10.18 a miss) it gains +$311 ± 21, and the withholder +$310 ± 21 (report v3).
  - **The switch:** `SILENCE_SLASH_BPS` makes the silence slash max(`SILENCE_SLASH`, x % of the bounty), and `SEALED_NO_REVEAL_SLASH_BPS` does the same for a sealed vote not revealed. The bounty is the one the judge was drawn for (on a challenge panel, the challenged fix's). An ADR has no bounty, so its judges pay the flat amount.
  - **The sweep (task 8.2):** x of 0, 1, 2 and 5 %, with the silent judge and the withholder bribed 5 % and 10 % of the bounty, and the honest validator's month on the market at 1 outage in 200 draws, before and after the seal.
  - **The trade-off:** a share of the bounty grows with what a bribe can buy, but it also raises an honest outage's cost on large bounties, the same for every bond. No x stops a bribe larger than x % of the bounty. The default stays x = 0 (a flat $5) until ADR 0004 recommends a value, or keeps $5 flat and names the trust point.
- **The reveal-rate floor still stops refusals:** on the market without the outage slash, the cartel refusing half its draws already lost −$657 ± 12 (#134), and −$488 ± 17 in round 1's re-run, by suspensions and lost fees; each refusal now also costs $5.
- **A batch of faults shares one bond:** once the whole bond is taken, the validator is below the floor and isn't drawn. D4's cap on pending k = 1 verdicts bounds such a batch.

### D17. Every acceptance criterion has a published threshold (#141)
#134 couldn't fully judge 3 criteria (the sybil's share, the lone validator's share, the fee's margin) because they weren't published. These are published now, before the re-run.

**How a criterion is judged:** over seeds 1–40, with ± two standard errors (SE) of the mean.

| Criterion | Met when |
|---|---|
| "not shown to gain against its honest twin" (every attacker criterion, round 3) | mean(attacker − twin) − 2 SE ≤ 0 **and** mean + 2 SE ≤ `GAIN_TOLERANCE` ($10 over the run). A gain shown by its lower bound fails, and so does a noisy result whose upper bound is above the tolerance. |
| "doesn't gain" (round 2's criterion; switch `GAIN_TEST`) | mean(attacker − twin) ≤ 0 **and** mean + 2 SE ≤ `GAIN_TOLERANCE` |
| "loses against its honest twin" (reported beside it; #141's criterion) | mean(attacker − twin) + 2 SE < 0 |
| "at most X" | mean + 2 SE ≤ X |
| "at least X" | mean − 2 SE ≥ X |

**Why "doesn't gain" (round 2):** "loses" can't be met by an attack that costs nothing and gains nothing. The inflaters on a working market (−$1 ± 7) and on a small one (−$0 ± 3) failed only as not significant. The new rule passes them, and still fails a noisy one: the coalition of 3 (+$148 ± 182) has a positive mean, and the bribed cheater at a 2 % audit rate (−$154.6 ± 172.4) has an upper bound of +$18. Every attacker that loses also doesn't gain.

**Why "not shown to gain" (round 3):** "doesn't gain" first tests the sign of a sample mean, so an attack with no effect fails it half the time by chance. In report v3 the inflaters (+$2.7 ± 3.9) and the weak herders (+$0.2 ± 0.7) failed only on that. The new rule asks for the gain to be shown, by a lower bound above zero, and still bounds the noise by the tolerance. It passes those two, and still fails every other row the two rounds flagged: a lower bound above zero (the 10 % silence bribe, +$311 ± 21; plain-agreement herders on the market, +$97 ± 31) or an upper bound above $10 (the coalition of 5 from 14, −$58 ± 259; round 1's bribed cheater at a 2 % audit rate, −$154.6 ± 172.4). Every attacker that doesn't gain is also not shown to gain.

**Why $10:** under two months of an honest validator's service fees ($5.25–$7.39 a month in round 1's re-run), and below every gain that re-run found significant (the smallest, the weak herders' +$13 ± 2).

| Threshold | Value | Why this value |
|---|---|---|
| `SYBIL_SHARE` | **12.5 % (one in eight)** of the eligible validators, spread over hosts, TEE types and families | #134's grown network (the genesis and 20 honest validators): a sybil of 3 (12.5 %) never held a majority of a panel of k ≥ 3 in 40 runs; one of 6 (22 %) held 1.2 % of its own panels. At k = 7 a majority is 4, so below 4 validators it never can; the share grows with the network. Above the share, the report gives how often it holds a majority, as the trust point. |
| `LONE_CATCH_SHARE` | **90 %** of the bad fixes a colluding lone validator passes **itself, as the lone judge** (round 3), reversed before any payment (pooled over the runs), and it isn't shown to gain against its twin. Its accomplice's fixes judged by others are reported beside them (switch `LONE_CATCH_COUNT` "all", round 2's count) | Round 3: report v3 measured 98.4 % ± 1.8 of its own verdicts (184 of 187); counting the accomplice's fixes judged by others too, 93.3 % ± 3.9, a named trust point (round 3, finding 3). Each held bad fix is audited twice (round 2): two independent 90 % accurate auditors both miss it 1 time in 100, and a challenge panel of 3 upholds a mismatch 97 % of the time, so about 96 % are reversed, more with volunteers. With one audit (#141) the estimate was 87 %, and round 1's re-run measured 86.6 % ± 5.1; #134 measured 18 %. A per-run "every bad fix reversed" can't be met while honest re-runs err 1 time in 10. |
| `FEE_MARGIN` | started at the ceiling, the mean fee over the last 13 weeks is **at most 25 % above** the mean break-even fee, and **at least break-even less one `FEE_STEP`**; no run collapses below 3 active validators | #134's moving market settled at $0.227 against a $0.186 break-even (+22 %). The fee should stay within the band the step can hold. |
| `WAIT_CROWD_MAX` | **at most 20 %** (round 3; 15 % before) of submissions wait for a panel when every validator chases the top family | #134: 11.6 % ± 5.5. Round 3: the balanced score's cost. Report v3 measured 11.3 % ± 4.9 (upper bound 16.2 %); plain agreement waits 7.7 % ± 2.5 but brings the weak herders' gain back (+$97 ± 31 on the market) |
| Growth | from one validator, a small bounty reaches k ≥ 3 within the year **in every run**; the median days from a k = 1 verdict to payment are reported | #134: week 18, in 40 of 40 runs; the hold must not stop growth |
| k = 1's window range | 7, 14 and 30 days | 7 days is the minimum (D4) |
| `AUDIT_RATE` range | 0, 1, 2, 5, 10 and 20 % | as #134 |
| Answer shopping | counted at a borderline rate of **1 in 10**; at 3 in 10, reported as the trust point (D10) | #134: −$2 ± 14 at 1 in 10, +$328 ± 69 at 3 in 10 |
| `GAIN_TOLERANCE` (round 2) | **$10** over the run: the most an attacker's upper bound may reach while its gain isn't shown (round 3; round 2: while its mean is at most zero) | see "Why $10" above; never the binding part in report v3 |
| The constitution's thresholds (round 2) | no adding ADR passes while fewer than `CONSTITUTION_MIN_ELIGIBLE` (21) are eligible, and no removal while fewer than `REMOVAL_MIN_ELIGIBLE` (14) are, in any run | D7 |

**The attackers counted** are those on the design's values, as #134 counted them:
- **included:** the new rules; every herder row; in round 2, the pricing attackers under the every-wait signal, the silent judge and the withholder at $5, both coalitions from 21 with the deposit, and the coalition of removals from 14;
- **excluded:** counterfactuals (the seed fixed at the seal), "without levels" rows, and switches that restore #134's rules (`V1`) or round 1's (`V2R1`).
- **round 3** counts the same attackers; the silence-slash sweep's rows are switches until ADR 0004 picks a value.

### D18. v3 builds its own seals, receipts and bonds; attestation on devnets is simulated (owner, 2026-11-13)
- **The decision:** group 3 starts now. It doesn't wait for #122, #85 5.5, 5.6 and 5.8 or #94 to land in v2 first.
- **Why not in v2 first:**
  - v2 is keyless and deployed. Seals on-chain, receipts and bonds in v2 would mean a v2.1 deployment (D15), and then building the same pieces again in v3.
  - v3's specs already require them: `judge-panels` counts only verdicts sealed and revealed on-chain with their receipt, and `validator-admission` has the bonds and D16's slashes.
- **Where each piece goes:**
  - **seals, reveals and receipts** go in `Panels` (task 3.2), with the node's `onchain` transport as v3's default (task 4.1);
  - **bonds and provable faults** go in `Validators` (task 3.1), with D16's amounts;
  - **receipt challenges** go through the challenge panels (tasks 3.2 and 3.5).
- **Attestation:** quotes are checked off-chain by the drawn panel, as before (Non-goals).
  - On devnets, a `simulated` proof type stands in for a TEE: the node's quote comes from the dstack simulator.
  - A deployment record may list `simulated` only for a devnet chain id (31337, 7193); the contracts refuse it on any other chain.
  - On a devnet, `simulated` counts as level A, so the genesis rule, the all-TEE panels and the TEE-type cap can be exercised. It proves nothing about the hardware, and that's acceptable only because a devnet holds no real money (rule 1).
  - Real attestation (AWS Nitro on the seats host, or a Phala dstack VM, #94's phase 2) is an outward step, taken only with the owner's approval.
- **The judge check (#160) is the last evaluation before v3 goes to a test blockchain (owner, 2026-11-13).** Until then, v3 is built and tested with the fake judge on the devnets. A real model's accuracy as a judge (B1) stays unmeasured until #160 runs, after group 5 and before any deployment beyond the devnets.
- **v2 stays frozen** and its integration suite keeps passing. Group 5 moves the suite to a panel interface, so both versions share the scenarios (task 5.0).

### D19. Model families are open: ranked, not listed (owner, 2026-11-13)
- **The decision:** v3 keeps no list of model families. Any family may register, and the market ranks them: the scores (D14) scale their pay, the minimum score stops drawing one that keeps getting outcomes wrong, and the family cap (D6) keeps any one model from deciding a panel alone. A model released after deployment competes without a new version or an ADR.
- **Why:** the contract is open by rule. A list of families would be a gate somebody has to keep, and would exclude models by name rather than by how they judge. #222's first draft fixed the families at deployment, as v2 did, only because each family's token prices needed a starting value.
- **The family's name:** the provider's model line, as its receipts name the model (`anthropic/claude`, `openai/gpt`, `google/gemini`, `meta/llama`, ...). It's what the cap and the scores group by. A receipt naming a model outside the declared family is already a false verdict (D16), so declaring a made-up name to slip past the cap costs the whole bond.
- **A new family's first price:**
  - the lower median of the values posted for it, once `MEDIAN_MIN_POSTERS` counting tables price it **and** at least that many come from validators of other families, so its own validators can't set it (#134's inflation attack);
  - at most `PRICE_CAP_X` × the most expensive priced family's token price at that moment;
  - then the normal rule: `PRICE_STEP_MAX` per period, never above `PRICE_CAP_X` × its first price.
  - From the next period, a table must price it to count, as for every priced family (#141's rule).
- **Before it's priced,** its validators aren't drawn, not even as shadows, so nobody is paid at a price that doesn't exist. The nodes post every family's public list price automatically (task 4.1), so this is about one period.
- **Kept on purpose:** the minimum score (`SCORE_MIN`). It excludes by measured performance, not by name, protects the funders from a model that is consistently wrong, and a barred family returns through shadow verdicts on fresh blocks (D14).
- **Alternatives rejected:**
  - **families fixed at deployment** (v2, #222's first draft): a new model would need a new version;
  - **families added by ADR:** a vote on which models may compete, which is exactly what the scores make unnecessary;
  - **a new family priced at the cheapest or the median family's price until posted:** underpays an expensive model or overpays a cheap one, and still needs the other validators' word to correct it.

### Parameters
All are fixed per version (entrenched). The starting values are proposals for the simulation to test (tasks 1.x, 6.x, 7.x and 8.x). Rows marked **#141** changed in round 1, rows marked **round 2** in round 2 and rows marked **round 3** in round 3; the old values are in the three tables after this one.

| Name | Starting value | Why | How the simulation tests it |
|---|---|---|---|
| `K_MAX` | 7 | v2's constitution tier, gas for 7 seals and reveals, and enough diversity under the caps | the k table vs a fixed k of 3; the constitution coalition |
| Largest bounty per (k, level) | level A: k=1 $50 · k=3 $250 · k=5 $625 · k=7 $625 (v2's `BOUNTY_MAX`). Level B: half of A's. Level C: k=1 $10 · k=3 $50 · k=5 $125 · k=7 $250 | what a lone or weakly proven panel can approve stays small; full level A panels keep v2's limit | "Growth from one validator"; "The k table compared"; the chip breaker and the answer shopper; `C_LIMIT_X` |
| Bond tiers (**#141**) | every limit above, at any level: $10, $25, $50, $125, $250, $312.50, $625 | exact counters for k, independent of the panel's level (gap 2) | growth, with the simulated bonds |
| `BOND_FACTOR` | 2 (bond ≥ 2 × the bounty's tier) | v2's `SEAT_BOND_MIN` = 2 × `BOUNTY_MAX` (#102): a fault sold on the bounty, proven half the time, loses money | "The bond's size" (#85), rerun per k |
| `BOND_FLOOR` | $100 (covers k = 1's largest bounty at `BOND_FACTOR`) | lets small operators start small; cost per node limits the fee farmer | fee farmer and sybil returns |
| `CHALLENGE_WINDOW[k, level]` (**#141**) | level A: k=1 **168 h** · k=3 24 h · k=5 12 h · k=7 6 h. Level B: twice A's (k=1 **336 h**). Level C: k=1 **336 h** · k=3 72 h · k=5 48 h · k=7 24 h | a lone or weakly proven verdict needs time for anyone to re-run it; at level C, the tests are only checked by re-runs; k = 1 at least 7 days (D4), and C's at least B's | "The window's length" (7 / 14 / 30 days); the level C test liar |
| `CHALLENGE_K[k]` | k=1→3 · k=3→5 · k=5→7 · k=7→7 (fresh validators; fewer only if still larger than k, D4) | a challenge is always judged by more, independent validators | the colluding lone validator, sybil at the share |
| `K1_PENDING_MAX` (**#141**) | 10 k = 1 verdicts not yet final, per validator | a batch of faults shares one bond: with two audits, 10 × $50 × 1-in-25 survival is a fifth of the $100 floor bond (D4) | the k = 1 hold (5 / 10 / 20; `K1_BATCH_BOND`) |
| `SEED_DELAY` | 5 blocks | the solver can't know the block hash when it seals | seed grinder |
| `SEAL_WINDOW`, `REVEAL_WINDOW` | 2 h and 1 h (as #85) | unchanged | silent judge |
| `QUALIFY_VERDICTS` | 20 scored shadow verdicts | enough to tell a working node from a broken one at low cost | false admissions and rejections, over seeds |
| `QUALIFY_REVEAL`, `QUALIFY_AGREE` | 95 % and 80 % | reveal is mechanical; agreement allows for honest model variance | an honest but noisy judge still qualifies; a random one doesn't |
| `QUALIFY_COOLDOWN` (**#141**) | 7 days | the published cooling-off period (gap 22); as simulated | growth |
| `ACTIVE_REVEAL_MIN` | 90 % over the last 50 draws (before 50 draws: more than 5 misses so far) | a validator that stops answering stops being drawn; with the flat silence slash (D16), this is what stops refusals | silent judge, cartel, offline validators |
| `UNBONDING_DELAY` (**#141**) | the longest `CHALLENGE_WINDOW` + 7 days = 504 h, and not before every verdict it gave is final and every challenge naming it is closed | longer than any window it served on, so faults stay slashable, even while a challenge is frozen (gap 11) | leave-then-fault, with frozen challenges |
| `SHADOW_PER_DRAW` | 1 (2 while fewer than 7 are active) | qualification keeps pace with the queue at low cost | time to qualify, pool spend |
| `SHADOW_PER_WAITING` (**#141**) | 3 a waiting submission | enough for a majority of sealed verdicts to score them (D5) | growth: time to qualify, pool spend |
| `DRAW_TRIES` (**#141**: fixed, not tuned) | 8 per seat | a gas bound; 8 and 1,000 give the same draws | none: a constant |
| `GENESIS_MAX` | 1, at level A or B (**#141**) | launch with one validator, no privileged set; a level C genesis can't grow a network | growth from one validator |
| `CONSTITUTION_QUORUM` | 5 of `K_MAX` | as v2 | constitution coalition |
| `CONSTITUTION_MIN_ELIGIBLE` (**round 2**) | 3 × `K_MAX` = 21 eligible validators for an ADR that adds or loosens anything, and for an escalated fix; ADRs submitted to a smaller network expire | the coalition was most of the first `K_MAX`, and still gained from 14 (D7) | constitution coalition (14 / 21 / 28) |
| `REMOVAL_MIN_ELIGIBLE` (**round 2**) | 2 × `K_MAX` = 14 eligible validators for an ADR that only removes, or raises a firmware minimum | it can't admit anything or move money, and a broken chip can't wait (D7, D11) | the coalition of removals |
| `ADR_DEPOSIT` (**round 2**) | $15, forfeited to the sponsors' pool by a rejected ADR or escalated fix; refunded when it takes effect or expires | with 21, it makes the coalition of 5 lose; neither does alone (D7) | constitution coalition ($0 / $15 / $25) |
| `TEE_CAP_FROM_K` (**round 2**) | 3 while at least `TEE_CAP_K3_TYPES` (5) TEE types are accepted, otherwise 5 (the host and family caps from k = 3) | with 3 TEE types, the cap at k = 3 lowered k on 39 % of growing draws; from k = 5, one type held the majority of 77 % of panels of 3 (D6) | growth; draws lowered by the caps; one-type majorities; three and five types, even and skewed |
| `PRICE_PERIOD` | 1 day | quick enough to follow provider price changes; few enough updates to stay cheap | the fee finds the validators' cost |
| `PRICE_STEP_MAX` | 25 % per period (unit prices) | v2's bound per update | inflating validators |
| `PRICE_CAP_X` | 2 × genesis, or 2 × a new family's first price (D19) | a safety bound: never bound in #134 (best 1.68 ×), kept for tiny networks | inflating validators on a small network |
| `MEDIAN_MIN_POSTERS` | 3, of tables that post every unit (**#141**) | a median of fewer is one validator's word | inflating validators on a small network |
| `PENDING_PERIODS` | 7 periods (D19; owner, 2026-11-13) | a new family announced but not priced within 7 periods (a week at `PRICE_PERIOD`) leaves the pricing queue, and anyone can announce it again; bounds `FeesV3.roll`'s work on families nobody prices | a flood of made-up families announced to slow the roll |
| `MEDIAN_LOW_EVEN` (**#141**) | the lower middle value | an absurd value can't pull it up (gap 15) | inflating validators |
| `FEE_START` (**#141**) | `FEE_CEILING` | from $0.05, 28 of 40 runs collapsed | the fee finds the validators' cost |
| `FEE_STEP` | 5 % per period, both ways | slow enough that a one-day spike doesn't swing it; it doubles in about 15 days of sustained shortage | the cartel, the spammer; `FEE_STEP_UP` 10 % |
| `WAIT_HIGH` | 5 % of the period's submissions waited, counting every wait once (`WAIT_SIGNAL` "every", **round 2**) | a small queue is normal; with every wait counted the fee can rise for large bounties too (D9) | the fee over time; the floor-bond and any-bond signals |
| `IDLE_HIGH` (**#141**) | 40 % of active validators not drawn in the period | free entry stops at about 30 % idle, so 80 % never fired (D9) | the fee over time (30 / 40 / 50 %; `IDLE_WINDOW_DAYS` 7) |
| `FEE_FLOOR`, `FEE_CEILING` | $0.01 and $0.25 per counted check | the ceiling is v2's cap; the floor is a safety bound | the fee finds the validators' cost |
| TCB minimum per TEE type | the vendor's level fixing every flaw published before deployment, in the deployment record | a known-broken firmware can't attest | none: raised by ADR when a flaw is patched |
| Notaries | none listed until the parameters ADR (#137), from #135's spike | several, none required (D10) | simulation placeholders |
| `AUDIT_RATE` (**#141**) | 10 % of submissions, plus every k = 1 verdict (twice, `K1_AUDITS` 2, **round 2**) and every split level C pass | deters the bribed cheater; $0.018 a check (D13) | "The watcher's dilemma" (0–20 %); the colluding genesis with one and two audits |
| `SCORE_WINDOW` | the last 200 counted verdicts per family | long enough to be stable, short enough to follow a model's update | scores and weighting compared |
| `SCORE_MIN`, `SCORE_MIN_VERDICTS` | 70 % over at least 50 counted verdicts, the score balanced over passed and failed outcomes (`SCORE_BALANCED`, **round 2**) | drops a family that's wrong too often, without punishing a short bad run; shadows can't lift the counted score; an always-pass family scores 50 % | the weak model, herding; plain agreement |
| `SCORE_RECOVER_VERDICTS`, `SCORE_RECOVER_MARGIN` (**round 2**) | fresh blocks of 100 shadow verdicts, each judged once, at `SCORE_MIN` + 10 points | a 68 % family passes a block about 1.9 % of the time, an 85 % one about 87 % (D14) | recovery by chance; round 1's sliding test; a block of 200 at + 5 points |
| `SCORE_FACTOR_MIN`, `SCORE_FACTOR_MAX` | 0.5 × and 2 × the service fee, linear in the score between `SCORE_MIN` and 100 %, normalised to a mean of 1 × (**#141**); 2 × is a safety bound | quality pays, fees per submission don't rise, and no family earns so much more that everyone switches to it | everyone moves to the top model |
| `REMOVAL_WINDOW` | 48 hours | long enough to see and challenge the ADR; short enough to stop an exploit | none: a constitutional safety valve |
| `FALSE_VERDICT_SLASH_BPS` (**#141**) | 10,000 (the whole bond) | D16 | seed grinder, sybil, colluder; 2,000 as sensitivity |
| `EQUIVOCATION_SLASH_BPS` | 10,000 | as v2 | — |
| `SEALED_NO_REVEAL_SLASH`, `SILENCE_SLASH` (**round 2**) | $5 flat each, for a counted judge, whatever its bond | the bribed withholder loses at $5; about $0.025 a draw at the outage rate (D16) | honest validator's month, silent judge, withholder, cartel ($1 each; silence unslashed) |
| `SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS` (**round 3**) | 0: the slash is max($5, x % of the bounty) with x = 0, a flat $5, until ADR 0004 picks a value | a bribe of 10 % of the bounty still gains +$311 ± 21 at the flat $5 (D16) | x of 0, 1, 2 and 5 %: the bribed silent judge and withholder (5 % and 10 % bribes), the honest validator's month (task 8.2) |
| `CHALLENGE_REWARD_BPS` | 5,000 of a slash, to whoever proved the fault | as v2 | watcher's dilemma |
| `SYBIL_SHARE`, `LONE_CATCH_SHARE`, `FEE_MARGIN`, `WAIT_CROWD_MAX` (**#141**; `WAIT_CROWD_MAX` **round 3**) | 12.5 %, 90 %, 25 %, **20 %** | the acceptance thresholds (D17) | the acceptance criteria |
| `GAIN_TOLERANCE` (**round 2**) | $10 over the run | the most an attacker's upper bound may reach while its gain isn't shown (D17) | every attacker criterion |
| `GAIN_TEST` (**round 3**) | "not shown to gain": mean − 2 SE ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE` | the sign of a mean fails a zero-effect attack half the time (D17) | every attacker criterion; round 2's "doesn't gain" as the switch |
| `LONE_CATCH_COUNT` (**round 3**) | the colluding lone validator's own k = 1 verdicts | the spec's words: "the bad fixes it passes" (D17) | the colluding genesis; round 2's count (every bad fix of its accomplice, whoever judged it) reported beside |

**What #141 changed** (old → new, with the evidence in `reports/open-validators-v1.md`; "assumed" means the specs named it and the simulation chose a value):

| Name | Old | New | Evidence |
|---|---|---|---|
| `CHALLENGE_WINDOW[1, A / B / C]` | 72 / 144 / 168 h | 168 / 336 / 336 h | the window's length: +$2,920 at 72 h, +$723 at 7 days; qualification recovers from 7 days |
| k = 1 finality | after the window | held until `CHALLENGE_K[1]` could judge a challenge | colluder caught in 0 of 40 runs; 52.8 challenges frozen a year |
| `K1_PENDING_MAX` | none | 10 | the whole-bond row: +$2,707 ± 512 (a batch shares one bond) |
| k = 1 audits | at `AUDIT_RATE` | every k = 1 verdict | ~half its bad fixes never re-run in 72 h |
| Shadow scoring | against every final outcome | only outcomes no lone validator set; held or waiting: the majority of ≥ 3 sealed verdicts | 3.1 newcomers qualify in the colluder's year against 13.3 |
| `FALSE_VERDICT_SLASH_BPS` | 2,000 (assumed) | 10,000 | seed grinder +$258 ± 79 → −$378 ± 103 |
| `CONSTITUTION_MIN_ELIGIBLE` | `K_MAX` (7) | 2 × `K_MAX` (14), with expiry | coalition +$5,196 ± 2,178 (5), +$819 ± 450 (3) |
| `NO_REVEAL_SLASH_BPS` (v2's, applied to silence) | 500 of the bond | not used by v3: `SEALED_NO_REVEAL_SLASH` $1 for a sealed vote not revealed; no slash for silence | honest month −$8.01 ($2.05 slashes, $0.74 fees); fee frozen at the ceiling |
| `FEE_START` | $0.25 (assumed) | `FEE_CEILING` (a rule) | from $0.05: 28 of 40 runs collapse |
| `IDLE_HIGH` | 80 % | 40 % | never fires; 50 %: $0.227 against $0.186 break-even; 30 %: overshoots |
| Wait signal | every wait | waits a floor-bond newcomer could end | 99 % of waits were bounties above $125 |
| Units posted | own family's tokens and shared units (assumed) | every family's list price and own shared units | inflaters +$42 ± 22 → −$3 ± 14 |
| `MEDIAN_LOW_EVEN` | mean of the two middle (assumed) | lower middle | inflaters' gain halved (+$24 ± 20) |
| `AUDIT_RATE` | 5 % | 10 % | bribed cheater −$34 ± 47 → −$137 ± 64 |
| Score window | counted and shadow verdicts merged (assumed) | counted only; shadows decide recovery | weak family's herders +$294 ± 28 |
| Score factor | linear, neutral at 80 % | normalised to a mean of 1 × | fees per submission +39 % |
| Genesis level | any | A or B | C genesis: 96 % withdrawn, nobody qualifies |
| Split level C passes | audited at `AUDIT_RATE` | always audited | answer shopper +$328 ± 69 at 3 in 10 |
| `TEE_CAP_FROM_K` | 3 | 5 | caps lower k on 39 % ± 9 of growing draws |
| `SHADOW_PER_WAITING` | 0 | 3 | 18 of 54 newcomers qualify, after 135 days |
| `DRAW_TRIES` | 8, a parameter | 8, a fixed constant | 36.6 % against 36.5 % at 1,000 |
| Bond eligibility | 2 × the bounty (spec) or 2 × the tier (D2) | 2 × the tier, steps at every level's limits | gap 2 |
| `UNBONDING_DELAY` | `CHALLENGE_WINDOW[1]` + 7 days (240 h) | the longest window + 7 days (504 h), and every challenge closed | gap 11 |
| `QUALIFY_COOLDOWN` | 7 days (assumed) | 7 days (published) | gap 22 |

**What round 2 changed** (round 1 → round 2, with the evidence in `reports/open-validators-v2.md`; "derived" and "estimate" mean computed by hand from it, for round 2's run to measure):

| Name | Round 1 | Round 2 | Evidence |
|---|---|---|---|
| `WAIT_SIGNAL` | waits a newcomer at `BOND_FLOOR` could end | every wait, once | floor: 33 of 40 runs collapse; every wait: none, 1.21 ± 0.04 × break-even |
| `SEALED_NO_REVEAL_SLASH` | $1 | $5 | the withholder: +$249 ± 12 at $1, −$20 ± 9 at $5 |
| `SILENCE_SLASH` | none | $5 | the silent judge: +$317 ± 13 unslashed, +$250 ± 12 at $1 |
| `CONSTITUTION_MIN_ELIGIBLE` | 14, for every ADR | 21, for ADRs that add or loosen and for escalated fixes | coalition of 5: +$622 ± 260 from 14, +$280 ± 152 from 21 |
| `REMOVAL_MIN_ELIGIBLE` | 14 (as every ADR) | 14, for ADRs that only remove or raise a firmware minimum | removals can't steal; an exploit can't wait |
| `ADR_DEPOSIT` | none (Article 9's verdict fees only) | $15, forfeited by a rejected ADR | derived: the coalition of 5 nets about −$255 ± 152 from 21 |
| `K1_AUDITS` | 1 (`AUDIT_K1_ALL`) | 2 | 86.6 % ± 5.1 reversed with one; about 96 % estimated with two |
| `SCORE_BALANCED` | off (a switch) | on | always-pass herder 78.5 % → 50.1 %; every herder row loses |
| Recovery (`SCORE_RECOVER_VERDICTS`, `SCORE_RECOVER_MARGIN`) | the last 50 shadow verdicts at each new one, at `SCORE_MIN` | fresh blocks of 100, each judged once, at `SCORE_MIN` + 10 points | the 68 % family recovered 10.8 times a year; estimate 0.2 to 0.3 |
| `TEE_CAP_FROM_K` | 5 | 3 while at least `TEE_CAP_K3_TYPES` (5) types are accepted, otherwise 5 | three types: one type holds 77 % ± 8 of panels of 3; five from k = 3: none |
| TEE types | three, unnamed (the simulation: nitro, tdx, sev-snp; its five-type switch added placeholders) | each attestation scheme its own type; the real ones named, three realistic at launch (D6) | the owner's decision |
| Shadows on a held k = 1 verdict | the sealed majority while held, or the final outcome after the hold (both in the spec) | once, by the sealed majority at the reveal | spec finding 4; as round 1 ran |
| Attacker criterion | "loses": mean + 2 SE < 0 | "doesn't gain": mean ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE` ($10) | inflaters −$1 ± 7 failed only as not significant |

**What round 3 changed** (round 2 → round 3, with the evidence in `reports/open-validators-v3.md`; no protocol rule changed):

| Name | Round 2 | Round 3 | Evidence |
|---|---|---|---|
| Attacker criterion (`GAIN_TEST`) | "doesn't gain": mean ≤ 0 and mean + 2 SE ≤ $10 | "not shown to gain": mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 | inflaters +$2.7 ± 3.9 and weak herders +$0.2 ± 0.7 failed only on the sign |
| `LONE_CATCH_SHARE`'s count (`LONE_CATCH_COUNT`) | every bad fix its accomplice passed, whoever judged it | the lone validator's own verdicts | 93.3 % ± 3.9 against 98.4 % ± 1.8; the rest is a named trust point |
| `WAIT_CROWD_MAX` | 15 % | 20 % | the balanced score's cost: 11.3 % ± 4.9 (upper bound 16.2 %) |
| `SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS` | none (a flat $5) | a switch: max($5, x % of the bounty), x = 0 until ADR 0004 | the 10 % bribe: +$311 ± 21 at $5 |
| An upheld receipt challenge (judge-panels) | the spec: the verdict "doesn't count"; the code: the challenge panel decides | the code's reading, now in the spec | report v3's finding 4 |

### D20. Seats go to the best-scoring families; the family cap applies only among near-equals (owner, 2026-11-14; values decided 2026-11-19)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** `SEAT_MARGIN` 5 points and `CAP_MIN_FAMILIES` 3, report measured-v3's values. The "proposed" marks below are history.
- **The rule:** a counted panel is drawn from the **seated** families: those whose score is at least `SCORE_MIN` and within `SEAT_MARGIN` (5 points) of the best-scoring family. Every other family is a **contender** (D21, D23).
- **The family cap** ((k − 1) / 2 per panel, D6) applies only while at least `CAP_MIN_FAMILIES` (3) families are seated. With fewer, a panel may be one family's. The operator, host and TEE-type caps are unchanged.
- **Why:** measured, a panel of the best family merges 6.0 bad fixes per 100 paid; adding the next two families under the cap gives 13.6, and v3 as designed 17.8. With one family qualifying and the cap kept, 82 % of submissions wait. A weaker model on a panel only outvotes a better one.
- **Why a margin, not "the top one":** on fixes that pass the tests and are wrong, three families were within two points (75, 75 and 74 %). Near-equals should share seats, and then the cap does its job: no one model decides.
- **What is lost:** D14's "diversity pays" and its protection against one model's blind spot. While one family is seated, a prompt injection that fools it decides the panel. Disputes (D21) are the remaining defence, and #160's injection arm (exploratory) found that injected fixes pass more often. This is a named trust point until a second family is within the margin, and the owner accepted it (2026-11-14).
- **`SEAT_MARGIN` and `CAP_MIN_FAMILIES` are proposed values:** task 10.1 sweeps them.
- **Alternatives rejected:**
  - **keep the cap and lower the bar:** it seats families right half the time (finding 1);
  - **every judge must pass:** the top two families together merge 5.6 per 100 paid but reject 30 % of good fixes;
  - **votes weighted by score:** rejected in D14 and still rejected; a wrong score would change verdicts directly.

### D21. A failing test reverses a pass (#236; values decided 2026-11-19, two rates still to measure)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** `EVIDENCE_STAKE` the larger of $5 and 10 % of the bounty, `EVIDENCE_REWARD_BPS` 1,000 (report measured-v3). With no solver's deposit (D22), the reward is the disputer's only pay besides its stake back; report v4 finds that at 1,000 a rival's search of a pass doesn't pay with per-issue bounties. The two rates below are still assumed (task 10.3, not decided): a named trust point at the launch.
- **The rule:** within a passing verdict's window, anyone may post a test and the published stake (`EVIDENCE_STAKE`). The official checker image runs it in the sandbox against the fixed code.
  - **The machine's part:** the test fails on the fixed code, twice, and touches nothing but test files.
  - **The judged part:** a challenge panel (D4's sizes) answers one narrow question: does this test state what the issue asks for? It doesn't re-judge the fix.
  - **Upheld:** the verdict is reversed, the fix isn't paid, and the disputer gets its stake back and the reward (D22).
  - **Rejected:** the stake goes to the solver, for the delay.
- **Who disputes:** anyone, with any model, validator or not. The measured cover is in measured-v2 §2: of the 18 bad fixes Opus passed, the other eight models failed 11.
- **Why a test and not a second opinion:** finding 4. A model asked again repeats itself, so a panel of the same models is no check. A failing test is something a machine can run.
- **Why it pays to contend with a good model:** a contender pays for every fix it searches and is paid per reversal. Opus contending against a GPT-6.1 panel searches 2.4 fixes per reversal; six open-weight models against Opus search 35.
- **No slash for the judges that passed the fix.** A wrong honest verdict is not a provable fault (D16). They lose score (D23), not bond.
- **The existing challenge** (re-run the check, D4 and D13) stays for fabricated receipts, where a re-run does prove the fault.
- **Assumed, to be measured before any contract (task 10.3):** how often a contender finds a failing test for a bad fix, and how often the panel accepts a test that states the wrong requirement. Accepted 1 time in 20, wrong tests reject another 3 % of good fixes.

### D22. A solver's deposit, lost on rejection, to the issue's bounty (owner, 2026-11-14; share proposed; on hold, owner 2026-11-15; **no deposit, owner 2026-11-19**)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)): there is no solver's deposit.** `SOLVER_DEPOSIT_BPS` is 0 and absent from the contracts, and there is no deposit "only while fewer than three solvers are active" either. The one-solver gap (D29) is reported as a named trust point, not closed. Everything below is superseded and kept as history.
- **On hold (owner, 2026-11-15):** the owner is against a solver's deposit and wants the market's incentives to stop bad fixes. Nothing below is decided until he rules; D28 has what the simulation says with and without it.
- **The rule:** a submission posts `SOLVER_DEPOSIT_BPS` (2,500: a quarter of the bounty) beside its check deposit. It is returned when the fix is paid.
  - **Rejected by the panel:** the deposit is added to the issue's bounty, so the next solver is paid more for the same issue. It never goes to the judges, who would then earn by rejecting, nor to the funder or reporter, who could be the attacker (as D7's ADR deposit).
  - **Reversed by evidence (D21):** the deposit is the disputer's reward, with `EVIDENCE_REWARD_BPS` (1,000) of the bounty.
- **Why:** finding 5. A bad fix that passes is paid the bounty, and one that fails costs about a dollar. The deposit at which a bad fix stops paying is p / (1 − p) of the bounty, with p the share of bad fixes the seated panel passes: about $19 on an $86 bounty at Opus's 18 %.
- **What it costs honest solvers:** a good fix is rejected 6 % of the time by Opus, so $1.13 a fix on average, less what an appeal returns (D23). With a judge that rejects 30 % of good fixes the same protection costs $6.14, which is one more reason to seat the best family.
- **Why a fixed share and not one computed from the panel's rate:** the rate isn't known on-chain without known answers, and a fixed share is quotable before the attempt (check-pricing, "An attempt is charged the prices it was quoted").
- **To size (task 10.1):** the share, on the measured verdicts, against the bad-fix solver and v3's judged spammer, with the market fee.

### D23. Final outcomes come from evidence and appeals; a new family starts as a contender (owner, 2026-11-14; values proposed)
- **The score rule is D14's, unchanged:** balanced agreement with final outcomes over the last `SCORE_WINDOW` verdicts. What changes is what makes an outcome final.
  - **A pass** is final when its window ends with no dispute upheld (D21).
  - **A rejection** is final when its appeal period ends with no appeal, or the appeal fails.
- **Superseded 2026-11-15 by D24:** the appeal panel described in this bullet and in "The appeal panel includes contenders" below is dropped (owner). The rest of D23 stands.
- **The appeal (as it stood):** the solver of a rejected fix may appeal once, within `APPEAL_WINDOW`, leaving its deposit at stake. A panel of `CHALLENGE_K[k]` validators drawn from the families that did not judge it, contenders included, judges the fix afresh.
  - **Upheld:** the fix passes, its window runs with disputes open as for any pass, and when it is final the rejecting judges are scored as wrong.
  - **Rejected:** the deposit goes to the bounty as in D22.
- **Why both sides:** evidence corrects only passes. Fed by evidence alone, GPT-6.1, which rejects 30 % of good fixes, scores 76–89 % against 65–75 % on known answers. An appeal is the known answer for a rejection.
- **Contenders are scored the same way,** on their shadow verdicts (D14's blocks). A contender is seated when a block reaches the seat rule of D20, and a seated family that falls outside it becomes a contender.
- **A new family starts as a contender,** not neutral: it shadow-judges and earns its seat on a block. D14's neutral start drew an unmeasured model at once, and five of the nine models measured pass 70–92 % of bad fixes.
  - **At genesis** the genesis validator's family is seated, since someone must judge first.
- **Past cases are public, so a replay proves nothing:** a contender's seat is earned on live shadow verdicts only.
- **The appeal panel includes contenders (owner, 2026-11-14),** on the condition the simulation sets: task 10.1 must show that a solver of bad fixes doesn't gain by appealing to weaker models. If it does, the alternatives are the seated families' own next draw, or an appeal that needs every judge to pass, and the question returns to the owner.
- **Not simulated yet (task 10.1):** the appeal and its cost to honest solvers.
- **Canaries (#136)** remain the cleaner source of known answers on both sides, and remain a research item.

### D24. The seated families decide an appeal, on new evidence (owner, 2026-11-15: the seated judges decide; the evidence and the stake accepted 2026-11-19)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** an appeal needs the test; the seated families decide; `APPEAL_WINDOW` 72 h (the simulation's value; no result depends on it). **No stake (owner, later the same day):** an appeal pays only its fresh panel's metered validation, as a submission does (the taxi deposit, its rest refunded), and nothing goes to the sponsors' pool when it fails; the stake first decided (the larger of $5 and 10 % of the bounty, lost to the pool) is dropped. Accepted risk: a solver may appeal every rejection, paying each panel's meter, the same spam risk the owner accepted for submissions. With no deposit, "separate from any deposit" below has nothing to be separate from. The two rates stay assumed (task 11.3, not decided): a named trust point at the launch.
- **Decided:** a rejected fix's one appeal is judged by the seated families. No contender sits on it.
- **Proposed: the appeal needs new evidence.** A test that fails on the base code and passes with the fix, run twice each way by the official checker image, touching test files only (D21's machine, pointed the other way), and a stake.
  - **The panel:** a fresh draw of the seated families, of D4's size where it can be drawn outside the original panel; otherwise a fresh draw of the original size in which the original judges may sit again. It is a new judgment on new evidence, not a second opinion. Without this, 380 of 383 appeals a year found no panel with one family seated (10.1).
  - **The panel sees the test and its results,** and re-judges the fix. A rejection stands unless the panel passes it.
  - **Upheld:** the fix enters a passing verdict's window, open to disputes (D21), and the judges that rejected it lose score.
- **Why evidence:** a model asked again repeats itself (finding 4), so the same family with nothing new overturns nothing: 0 % of wrongly rejected good fixes restored (10.1).
- **What the machine's part does not do:** it stops nothing by itself. The author of a bad fix can always write a test that fails before and passes after. The panel's judgment is the whole filter, and #160's verdicts do not say how a judge reacts to a passing test.
- **Assumed, swept (report v4, sections 2 and 3):** the share of wrongly rejected good fixes the panel passes on appeal (25–100 %), and the share of correctly rejected bad fixes it passes when shown a passing test (0–50 %).
  - at 50 % and 5 %, good fixes wrongly unpaid fall from 8.9 % to 6.1 % (the tests fail them) and from 9.0 % to 6.2 %, and bad fixes merged per 100 paid rise from 4.5 to 5.0 and from 8.5 to 8.7 if every rejected solver appeals;
  - with no deposit, a solver of bad fixes that appeals every rejection loses $1,766 ± 114 and $1,375 ± 89 a year at 5 %, breaks even near 20 % (+$153 ± 194 and +$85 ± 178), and gains $3,835 ± 302 and $2,927 ± 284 at 50 %. With a deposit of 2,500 it breaks even near 15 %: an upheld appeal returns the deposit too, so the prize is larger;
  - ten rival solvers each finding a test 1 time in 4 make appealing lose at every rate tried (−$1,025 ± 62 at 50 %).
- **The stake (proposed):** `APPEAL_STAKE`, the larger of $5 and 10 % of the bounty, separate from any deposit. It returns when the appeal passes or finds no panel. Lost, it goes to the sponsors' pool, never to a judge. The appellant pays the panel's checks.
  - **Why 10 %:** an appeal pays above stake / (stake + what it wins). With no deposit and test disputes reversing half the passes it wins, that is about 1 in 6 at 10 %. $5 flat lets the appealing solver break even at 1 in 10; 25 % holds to about 1 in 4 and costs an honest solver more.
- **Alternatives rejected:** D23's panel of other families (81 % of correct rejections overturned); every appeal judge must pass (31–39 %); the seated families with no evidence (restores nothing).
- **To measure before any contract (task 11.3):** both rates, on labelled fixes.

### D25. A contender may sponsor an appeal (proposed; deferred past the testnet launch, owner 2026-11-19)
- **Deferred (owner, 2026-11-19, #251):** left out of the testnet launch, not decided. It can follow after the launch.
- **The rule:** a validator of an unseated family may appeal in the solver's place for a fix its model passed: it posts the test and the stake and pays the panel's checks. Still one appeal a fix; the solver's own appeal comes first. When the fix is paid the sponsor gets `SPONSOR_REWARD_BPS` (1,000) of the bounty, out of the bounty.
- **How it earns rank:** as a successful D21 dispute does, through the final outcome. An upheld appeal makes the outcome a pass, so the sponsor's family is right on its shadow verdict and the seated family is wrong on its counted ones. Nothing else is added to its score.
- **What the simulation says (report v4, section 4):**
  - **the appeal moves the score whoever files it.** With solvers appealing their own good fixes and no sponsor, a better newcomer (Opus 5.5 into a network GPT-6.1 seats) is seated in 5 % ± 7 of runs; with sponsorship alone, 2 % ± 5. With six contender shadows a draw: 62 % ± 16 and 50 % ± 16, around week 33. Where three families are level: 12 % and 8 %;
  - **it does not pay at 1,000.** An honest contender running Opus 5.5 against a GPT-6.1 panel nets −$671 ± 80 and −$1,601 ± 70 a year at 1,000, and +$1,257 ± 130 and +$531 ± 116 at 2,500. A contender no better than the panel loses at both;
  - **a sponsor of every rejection loses in every row** (−$3,487 ± 84 to −$101 ± 88), but while it loses it gets 6 to 78 more bad fixes paid a year.
- **Recommendation:** allow it; it costs the network nothing when the panel judges tests well. Do not rely on it to seat a better family: D26 does that.

### D26. Known-answer issues score every family, seated or not (proposed; deferred past the testnet launch, owner 2026-11-19)
- **Deferred (owner, 2026-11-19, #251):** left out of the testnet launch, not decided. It waits for #136's keyless known-answer design (task 11.6).
- **The rule:** at `KNOWN_RATE`, an issue whose outcome is already known is judged beside a live submission by one validator of every registered family, drawn by the seed. Each verdict is recorded against the known outcome. Once a family holds `KNOWN_MIN` (50) of them, the seat rule (D20) reads its balanced agreement with the known outcomes over its last `KNOWN_WINDOW` (200), in place of its agreement with the network's own outcomes or its shadow block.
- **Is it D13's audit?** No, though it reuses its machinery. An audit re-runs a live submission whose truth is unknown, by one validator. This takes D13's draw by the seed and its funding from the fees, and adds what an audit lacks: a known answer and every family.
- **What the simulation says (report v4, section 5):**
  - a better family is seated from a network a strict family started: on fixes the tests fail in every run, first by week 34 ± 2 at 5 %, 18 ± 1 at 10 % and 9 at 20 %; on fixes that pass them in 80–98 % of runs. At 2 % nothing changes within a year: 31 known-answer issues are under `KNOWN_MIN`;
  - the newcomer of 10.1 that was never seated is seated in 95 % ± 7 and 68 % ± 15 of runs at 5 %, and in 100 % and 92 % ± 8 at 10 %;
  - the checks cost $81 ± 3, $163 ± 5 and $327 ± 7 a year at 5, 10 and 20 % with the fee at its floor ($0.05, $0.10 and $0.21 a submission); about 2.6 times that with the fee at $0.24;
  - where three families are level, a window of 200 is too noisy to seat all three at once: they hold the seats 80 %, 44 % and 39 % of the year at 10 %.
- **Assumed, and the whole difficulty:** that known answers exist with correct labels, and that a judge cannot tell a known-answer issue from a live one. D14 named the problem: someone who writes them holds a privileged role. Keyless known answers (#136) are a research item with no design. **This rule cannot be adopted before task 11.6.**
- **Recommendation:** adopt at 10 % once 11.6 names a source. It is the only rule here that reliably seats a better newcomer.

### D27. Among few families, a second draw decides a challenge (accepted 2026-11-19)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** accepted, with `SECOND_PANEL` "few families": the second draw applies only while fewer than `CAP_MIN_FAMILIES` families can judge. Not "always".
- **The rule:** while fewer than `CAP_MIN_FAMILIES` (3) families can judge a fix, a challenge that cannot draw D4's larger fresh panel is judged by a second draw of the original panel's size from those families, the original judges not excluded. The operator, host and TEE-type caps apply.
- **Why:** D4 asks for a fresh panel larger than the original. With one family on seven seats there are rarely seven more, and the challenge waits for good.
- **What the simulation says (report v4, section 6):** verdicts never final fall from 23.6 % ± 2.5 and 23.0 % ± 2.4 to 0.1 % and 0.0 % under v3's seats, and from 2.7 % ± 0.2 to 0.0 % under seats by rank with one family. With three families seated the rule does not apply and 0.3 % ± 0.1 stay open; the second draw whenever the larger panel cannot be drawn closes those too (the alternative, `SECOND_PANEL` "always").
- **What it is not:** a check. The same family repeats its verdict, so the second draw confirms it. It ends the wait; it corrects nothing. Wrong verdicts are corrected by tests (D21, D24).
- **Recommendation:** adopt; consider "always".

### D28. The solver's deposit around an appeal, and its size (proposed; D22 on hold, owner 2026-11-15; **void: no deposit, owner 2026-11-19**)
- **Void (owner, 2026-11-19, #251):** there is no deposit (D22), so there is nothing to hold. An appeal's stake (D24) is the only money an appeal puts at risk. The rest is kept as history.
- **Proposed, if the deposit stays:**
  1. a rejected fix's deposit is held, not paid to the issue's bounty, until the appeal period closes;
  2. no appeal in the period: it goes to the issue's bounty, as D22 says;
  3. the appeal passes: it returns to the solver with the bounty, and the appeal stake returns to whoever posted it;
  4. the appeal fails: it goes to the issue's bounty, and the appeal stake goes to the sponsors' pool;
  5. if the issue's bounty was already paid when the deposit is released, it goes to the sponsors' pool.
- **Holding it opens no gain** (report v4, section 3): a solver that tries each issue up to 21 times earns +$13,019 ± 1,825 with the deposit held against +$12,152 ± 2,283 without (2,500, fixes that pass the tests), and loses in every row at 4,000. Submitting again while the deposit is held earns less, not more.
- **The share: on hold.** 10.1 found 2,500 too low on fixes that pass the tests and proposed 4,000. That stays a finding, not a recommendation: the owner is against the deposit.
- **With no deposit (report v4, sections 7 to 9):**
  - a solver of bad fixes gains $2,741 ± 204 and $6,126 ± 370 a year from contenders' disputes alone;
  - rival solvers as disputers (D21: anyone may dispute) bring that to nothing only at about ten rivals each finding a failing test 1 time in 4 (assumed), for Opus 5.5 and for GPT-6.1 alike;
  - with per-issue bounties and no deposit, a rival's search of every passed fix does not pay at a reward of 1,000 of the bounty (−$0.10 to −$0.35 a search), so those ten rivals are not paid to look;
  - trying the same issue again is the hole only a cost per attempt closes. Report v4 names the non-money limits and says which the simulation supports.
- **A shared pot split by standing fixes** (the owner's idea, 2026-11-15) pays the disputer from the reversed fix's share with no deposit. Report v4, section 10, tests it as a hypothesis on expected values only; it is not part of this change.

### D29. Reputation before large claims (report measured-v5; no deposit; accepted 2026-11-19)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** `REP_BASE` $50, `REP_MULT` 1, `REP_ON_REVERSAL` "minus" (subtract, not reset), `REP_LOSS_X` 2.
- **The rule:** an identity's open claims (the bounties of its fixes not yet final) add up to at most `REP_BASE` + `REP_MULT` × its reputation. Reputation is the sum of the bounties of its fixes paid and never reversed. A claim over the cap is refused before it is judged and costs nothing. A pass reversed by a test takes `REP_LOSS_X` × its bounty off the reputation.
- **Proposed values:** `REP_BASE` $50, `REP_MULT` 1, `REP_LOSS_X` 2 (`REP_ON_REVERSAL` "minus").
  - The rule fixed before the runs reset reputation to 0 on a reversal. The sweep showed the reset costs honest solvers $637–773 a year (Opus 5.5) through their own reversed mistakes, and "minus 2×" costs $58–112 with attackers unchanged. That choice is post hoc (report v5, sections 2 and 6).
- **Only with D30.** Alone it closes nothing with 1–3 active honest solvers (report v5, section 2).
- **What the simulation says (report v5, sections 5 and 6), with D30, no deposit, each active honest solver finding a failing test 1 time in 4 (assumed):**
  - with 3 or 10 active honest solvers, every attacker tried (solver of bad fixes, free identities, retrier on one or fresh identities, long con, reputation sale) earns at or below its twin, for Opus 5.5 and GPT-6.1 seated alone and both kinds of bad fix;
  - with 1, gains of $237–3,870 a year per attacker remain; a deposit of 2,500 closes them in the post hoc rows, 1,000 does not;
  - at a find rate of 10 % it fails with 3 solvers too;
  - an honest newcomer may claim a median bounty within a week.
- **Not to raise:** at a base of $100, free identities gain again (+$670 to +$2,075 a year).
- **What it needs that the simulation does not have:** identities on chain with their reputation; the claim registered before judging; reversals by test recorded against the identity. A pot share must not be capped by it: capping a window's share at the window's close confiscated $18,000–20,000 a year from honest solvers (report v5, section 4).

### D30. A fee that covers the judges' cost (report measured-v5; accepted 2026-11-19)
- **Decided (owner, 2026-11-19, #251; [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md)):** one flat `JUDGE_FEE` per submission, in place of per-check charges, re-measured each period from the validators' posted costs. **For the Sepolia launch, D30 is the pure taxi fare (`judgeFee` 0; owner, later the same day):** a fix posts the fee meter's worst-case deposit, its judges are paid by the meter, and whatever is left returns to the solver, pass or fail; a solver pays only the metered validation (no attempt, evaluation or appeal fee). The flat fee and its value (first $40 in test USDC, the launch's L17) are deferred to a mainnet decision. Accepted risk: spam can block validation on the testnet, bounded by the nodes' spending caps (report faucet-spam-v1 simulated a flat fee, not the taxi fare).
- **The rule:** every submission pays `JUDGE_FEE` on arrival, never refunded and never more on rejection, in place of its panels' per-check charges. It is set to the measured cost of judging: every check the network paid for in a period (counted panels, audits, challenge and test panels), at the break-even service fee plus usage, over the submissions.
- **Proposed value:** re-measured each period. On report v5's base network: $5.03 a submission (7.6 checks at $0.53 + $0.13), against $0.96–1.55 charged now at the fee's floor.
- **Why:** it is the price of judging, not a defence. Alone it stops no attacker with one active honest solver; stopping the solver of bad fixes by fee alone would take $8.71–62.54, which is a deposit honest solvers pay on every fix. With D29 it bounds each attempt's margin, which is what makes the cap hold from 3 solvers.
- **Its cost:** $3.48–4.07 more a submission. With GPT-6.1 seated alone, which rejects 30 % of good fixes, an honest solver's year turns negative with 3 or more solvers (−$448 and −$1,000).

### D31. A validator's capacity, and a repository's cap (PROPOSED, #253, report measured-v6)
- **The rule:** a validator takes at most `MAX_CHECKS_PER_HOUR` checks in any trailing hour. A counted draw skips a validator at its capacity, as it skips a non-responder, with no slash. **k is set from every eligible validator and is never lowered for capacity:** with too few free validators the submission waits and is drawn again later; nothing fails. Audits, challenge and appeal panels count toward the hour but are never refused for it, so spam can't suppress them.
- **A repository's cap:** at most `REPO_CHECKS_PER_HOUR` counted checks drawn for one repository in any trailing hour; its submissions wait beyond it.
- **Why k is never lowered:** otherwise spam would shrink honest fixes' panels, trading a delay for a security loss.
- **What the simulation says (report measured-v6, simulation A; 40 seeds, Opus 5.5 and GPT-6.1 seated alone, no fee, junk from free identities):**
  - **a capacity is a spend limit, not a spam defence:** a validator runs about 24 × N checks a day under spam (N = 5: 118 checks, $2.36–14.18 a day at $0.02–0.12 a check, against $4.78–28.66 with no capacity at 10 junk fixes an hour and 7 validators);
  - once spam exceeds validators × N, the backlog never clears: in arrival order every honest fix waits behind the junk (100 % over 24 hours, 90 % withdrawn at 7 validators, N = 5, 10 junk fixes an hour);
  - the rule fixed before the runs names N = 10 (the smallest that holds at 7 validators against 1 and 10 junk fixes an hour, with D32), but at 7 validators that is the spam's own demand, so it caps nothing;
  - a repository's cap of 7 counted checks an hour confines spam aimed at one repository (0.4–0.6 % of honest fixes withdrawn, spend down from $14.18 to $3.27 a day) and does nothing against spam spread over every repository.
- **Post hoc (report measured-v6, "the newcomer lane"):** at the testnet's launch, with one repository, a repository cap is a network-wide cap: 7 counted checks an hour judges one panel an hour, and failed the rule even at 1 junk fix an hour (newcomers' fixes 97 % over 24 hours, all honest fixes 4.6–6.9 %).
- **Proposed values:** `MAX_CHECKS_PER_HOUR` from what a validator will spend (5: about $14 a day at the dearest model call); `REPO_CHECKS_PER_HOUR` 7 **only once there are several repositories, none at the launch with one** (or one at or above the network's capacity); with D32, and with identities that cost something for a newcomer's first fix (D32).

### D32. The queue's order under a backlog (PROPOSED, #253, report measured-v6)
- **The rule:** waiting submissions are drawn first for identities holding standing reputation (D29) when they submitted, in arrival order within each class (`QUEUE_ORDER` "reputation"); the alternative is plain arrival order ("fifo").
- **What the simulation says (report measured-v6):** under spam beyond the network's capacity, established solvers' fixes are drawn within the hour (median 0.6 hours, about 0 % over 24 hours) where arrival order makes every honest fix wait; newcomers' fixes are withdrawn instead (85–87 % at 7 validators, N = 5, 10 junk fixes an hour), and a newcomer never earns the reputation to move up.
- **What it does not cover:** a newcomer's first fix waits behind junk from fresh identities; a reputable identity's junk is served first, bounded only by D29's cap on its open claims (about 28 junk fixes at once for an identity of $5,000; no honest fix waited).
- **A newcomer lane does not fix it (post hoc, report measured-v6, "the newcomer lane"; switches `NEWCOMER_LANE`, `LANE_PER_ID_DAY`, not proposed):** a share of each validator's capacity reserved for fixes without reputation, first come first served, passed the rule at no share (10, 25, 50 %) and no capacity (5, 10), because junk from free identities queues in the lane with the newcomers. At 7 validators and 10 junk fixes an hour it withdrew more honest fixes than no lane (15–19 % against 8.7–11.1 %). A per-identity rate refuses nothing when identities are free.
- **What lets a newcomer through: identities that cost something.** Then D29's $50 of room per reputationless identity bounds its junk in flight: with a pool of 10 identities, reputation first with a lane of 25 % held in every cell run (7 and 15 validators, one repository, with or without its cap), and so did a pool of 10 with no rate. How a testnet identity costs something (one per account at the faucet, a charge in test ETH) is task 13.7.

### D33. Validators choose repositories: allow and deny lists, respected everywhere (owner, 2026-11-17, #252; PROPOSED)
- **The rule:** a validator may publish an allow list and a deny list of repositories. Every draw (counted panels, shadows, audits, challenge and appeal panels, the k = 1 hold's count) keeps only validators that allow the submission's repository (no allow list: every repository) and don't deny it (`REPO_LISTS`).
- **Enclaves only (owner, #252):** with levels A and B only, choosing a repository can't buy answer shopping or a fabricated receipt unless a TEE type is broken; report measured-v6 simulates that case.

### D34. A repository's minimum of eligible validators, and its stake cap (PROPOSED, #252, report measured-v6)
- **The rule:** a repository lists bounties only while at least `REPO_MIN_ELIGIBLE` validators are eligible for it, counted with at most (`REPO_MIN_ELIGIBLE` − 1) / 2 of any one TEE type (and, once `CAP_MIN_FAMILIES` families are seated, of any one family); otherwise its fixes are not listed and cost nobody anything.
- **The option:** a listed bounty capped at `REPO_STAKE_X` × the bonded stake of the repository's eligible validators outside the TEE type that holds the most of it.
- **What the simulation says (report measured-v6, simulation B; Opus 5.5 seated alone, 28 honest validators, the target allowed by h of them):**
  - a broken TEE type's validators allow-listing a small repository gain +$3,732 to +$3,950 a year with h = 1 and +$1,163 to +$2,762 with h = 3 (fixes the tests fail), because the caps step k down to 3, where one of three TEE types may hold every seat; from h = 5 the per-TEE-type cap holds them at or below their twins;
  - **M = 5 (at most 2 of one TEE type counted)** keeps them at or below their twins in every cell on fixes the tests fail, and removes the broken TEE's part on fixes that pass the tests (the rest there is report v5's solver of bad fixes, which D29 addresses; D29 with M = 5 was not run together); M = 3 does not (h = 3: +$1,163 and +$2,762). The price: repositories allowed by fewer than about 5 honest validators across three TEE types list nothing;
  - the stake cap at X = 0.1 changes nothing that matters (+$3,422 with h = 1);
  - **silence is not stopped by any minimum:** it loses money but cuts the target's good fixes healed from 87–91 % to 3–6 % (h = 1), 77–82 % (h = 3) and 82–86 % (h = 5), mostly through counted panels whose sample runs out of replacements and that nothing releases (3–28 % of the target's fixes stuck). A rule that ends such a panel is needed (task 14.2).
- **Proposed values:** `REPO_MIN_ELIGIBLE` 5, `REPO_STAKE_X` 0 (not adopted), with D29 and D30.

### The pot by impact (report measured-v5; NOT proposed)
- Simulated in the network: equal units, and an impact weight correlated 0.3, 0.6 and 0.9 with true impact (assumed; #247 is not built).
- **Not proposed now.** At correlation 0.6 an inflater gains $13,600–15,000 a year at an assumed $20 a fix, and a farmer of the cheapest issues $6,575; inflating stops paying only above $50–100 a fix. The pot also raises the solver of bad fixes' gain over bounties. It pays honest solvers to search ($1–7 a pass, against $0.06–0.37 with bounties).
- **Revisit when #247 is measured:** correlation near 0.9, and inflating a fix's signal by a standard deviation costing more than about $75 or being caught.

## Risks / Trade-offs
- **[k = 1 trusts one validator]** → Mitigations (#141):
  - the bounty cap per k ($50 at level A);
  - the hold: no payment until `CHALLENGE_K[1]` validators could judge a challenge;
  - every k = 1 verdict audited twice (round 2);
  - at most `K1_PENDING_MAX` pending per validator;
  - the whole bond per false verdict;
  - a window of at least 7 days;
  - shadows scored only against outcomes no lone validator set;
  - attestation, so the lone validator runs the official code.

  The simulation must show a colluding lone validator isn't shown to gain and that `LONE_CATCH_SHARE` of the bad fixes it passes itself are reversed before payment (round 3).
- **[An accomplice's fixes judged by others (round 3, a named trust point)]** → a colluder isn't a declared party to its accomplice's fixes, so it can sit on the challenge panels of those another judge passed. In report v3, 11 of 22 such fixes were paid over 40 runs, while the colluder still lost −$247 ± 41. Excluding from a challenge panel the validators that judged the same solver's other pending fixes is proposed, not decided (round 3, finding 3); an accomplice using a fresh solver address for each fix escapes it.
- **[The hold delays honest solvers' pay while the network is small]** → judges' fees are paid when the verdict is posted; only the bounty waits. Shadows on waiting submissions make qualification possible at all. Round 1's re-run: a median 19.0 ± 3.6 days from a k = 1 verdict to payment (90th percentile 46.1), on k = 1's 2 % of panels, with growth to k ≥ 3 in every run. The owner accepted it (round 2).
- **[A party with a large share of bonded validators]** → caps per host, TEE type and model family. Bonds scale with that party's presence. Above `SYBIL_SHARE` (12.5 %), the report gives how often it holds a majority, as the remaining trust point.
- **[The constitution coalition]** → ADRs that add or loosen are drawn from 21 eligible, removals from 14, with expiry, and a rejected ADR forfeits $15 (D7). Neither the threshold nor the deposit alone made the coalition of 5 lose; together they do by derivation (about −$255 ± 152), which round 2's run must confirm. The deposit is sized for an ADR worth $1,000 to the coalition.
- **[A coalition passes removals from 14]** → a removal can't admit anything or move money. At worst it stops a TEE type's validators being drawn: they keep their bonds and may register again with another type, the per-type caps keep any group from taking a panel's majority (D11), and each rejected removal costs $15. Removing every accepted type or image digest would halt the network; round 2's run measures the coalition of removals.
- **[A whole-bond slash for a mistaken upheld receipt challenge]** → a receipt challenge is upheld only when a fresh, larger panel's re-runs disagree. Receipts carry each test's pass or fail, so flaky output doesn't count. A good-faith wrong verdict with a valid receipt is never slashed.
- **[A bribe for silence or for withholding a reveal]** → each costs the judge a flat $5 (D16), more than the report's bribe of about $4; k never shrinks, and the reveal-rate floor suspends a judge that misses more than 10 % of its draws. A bribe above $5 still pays (at 10 % of the bounty: +$311 ± 21, report v3), and buys only a replacement's 3-hour delay. Round 3 sweeps a slash of max($5, x % of the bounty) for ADR 0004 (D16).
- **[Honest outages now cost money]** → $5 a counted outage, about $0.025 a draw at 1 outage in 200 draws ($1.11 a month in the report's worst case, against $4.34 under v2's share of the bond). The same for every bond, and break-even, so the fee, includes it.
- **[TEE flaws]** → several accepted TEE types and the per-TEE-type cap, so one vendor's flaw can't hold a majority of a panel of 5 or 7. From k = 3 once five types are accepted (D6). **At launch only three types are realistic, so the cap starts at k = 5**, and one type held the majority of 77 % ± 8 of panels of 3 in round 1's re-run: a flaw in that vendor's chip could decide them, within k = 3's limits and windows. Intel's SGX and TDX count as two types though some flaws can hit both. Challenges re-run elsewhere, and the accepted list changes by ADR.
- **[Shadow judges paid from the pool drain it]** → at most the seated shadows' quoted usage per draw, and one shadow per draw once 7 are active. Shadows on waiting submissions add up to 3 a submission; the re-run reports the pool's spend (#134: $88 a year).
- **[Liveness on a tiny network]** → submissions wait instead of being judged by too few. The solver can withdraw. The k table is published so funders know the current limits.
- **[A sequencer or proposer influencing the seed]** → it can only influence its own block's hash, at the cost of the block. A beacon can replace it later behind the same interface.
- **[A cartel refuses work to raise the fee]** → silent judges are replaced, slashed $5 a refusal, and lose their reveal rate, then their draws. Every wait counts now (D9), so a panel the cartel stalls does push the fee up a step; but open entry lets newcomers take the work and `FEE_STEP` is slow. The cartel lost in #134's every-wait market (−$5,460 ± 335) and in round 1's (−$488 ± 17).
- **[A spammer fakes demand to raise the fee]** → every wait counts, so submissions to a bounty no panel can judge raise the fee too. Each pays the attempt fee; the spammer lost on #134's every-wait market (−$608 ± 19), and round 2's run measures it again.
- **[zkTLS maturity: speed, size limits, TLS versions, notary availability]** → measured in task 1.9 before any contract work; level C's low limits and long windows; listed notaries can be removed fast (D11).
- **[A validator breaks its own chip (physical attacks on TDX or SEV-SNP)]** → it's level B, not A: lower limits and longer windows. Also:
  - the bond at 2 × the bounty;
  - firmware minimums raised by ADR in 48 hours;
  - caps per TEE type and per host;
  - re-run challenges and audits;
  - the optional zkTLS proof of the model call.
- **[Answer shopping at level C]** → it can't be proven per call. It's the named trust point (D10):
  - bounded by the majority of independent judges, an audit of every split level C pass and level C's low limits;
  - it pays only if borderline fixes fool an honest call often (#134: 3 in 10 yes, 1 in 10 no).
- **[Herding to the base rate]** → an always-pass judge agrees about 78 % of the time, above `SCORE_MIN`. The score is balanced (round 2), so it scores 50 %; shadows don't lift a family's counted score, and a barred family recovers only on a fresh block above `SCORE_MIN` + 10 points (D14).
- **[Flaky tests make a zkTLS validator look like a liar]** → receipts carry each test's pass or fail; a challenge needs a fresh panel's re-runs to disagree.
- **[Model family declared falsely]** → the receipt names the provider's model, and a mismatch is an upheld receipt challenge: a false verdict, slashed the whole bond (D16).

## Migration Plan
- **Order of work:**
  1. simulation (task group 1), then its re-run with #141's rules (group 6), then the round-2 re-run (group 7), then round 3's criteria and sweeps (group 8), then the parameters ADR (group 2);
  2. contracts, building v3's own seals, receipts, bonds and slashes, with attestation simulated on devnets (D18; owner, 2026-11-13);
  3. node and kit;
  4. a devnet deployment beside v2.
- **v2 keeps running** for the demo. v3 is deployed as a new version, its bounties open in v3, and v2's finish in v2 (D15).
- **Rollback:** a new version, as D15 says. There's no switch, by design.

## Open Questions
- **Decided 2026-11-19 (#251), every value as recommended; recorded in [ADR 0007](../../../docs/adr/0007-solver-side-parameters.md):**
  - D20: `SEAT_MARGIN` 5 points, `CAP_MIN_FAMILIES` 3 (report measured-v3);
  - D21: `EVIDENCE_STAKE` the larger of $5 and 10 % of the bounty, `EVIDENCE_REWARD_BPS` 1,000 (report measured-v3). With no deposit, the reward is the disputer's only pay besides its stake back;
  - D24: accepted. An appeal needs a test and a stake of the larger of $5 and 10 % of the bounty; a lost stake goes to the sponsors' pool; the seated families decide. `APPEAL_WINDOW` 72 h (reports measured-v3 and -v4; no result depends on it);
  - D27: accepted, with `SECOND_PANEL` "few families" (only while fewer than `CAP_MIN_FAMILIES` families can judge);
  - D29: `REP_BASE` $50, `REP_MULT` 1, a reversal subtracts 2 × its bounty (`REP_ON_REVERSAL` "minus", `REP_LOSS_X` 2), not a reset;
  - D30: a flat `JUDGE_FEE` per submission in place of per-check charges: $40 on Sepolia (the launch's L17), re-measured each period from the validators' posted costs on later networks;
  - D22 and D28: **no solver's deposit**, and no deposit only while fewer than three solvers are active. The one-solver gap is a named trust point, reported, not closed;
  - the launch's minimum of 3 active solvers is kept, with `ACTIVE_WINDOW` 26 weeks, counting only the repository's own solvers (report active-solvers-v1); the sybil of three is a named trust point, bounded by D29's cap;
  - D25 and D26: **left out of the testnet launch** (deferred, not decided). D26 waits for #136; D25 can follow after the launch;
  - the paid runs (tasks 10.3 and 11.3): **not decided.** D21's and D24's safety at the launch rests on assumed rates, a named trust point;
  - still open: re-deriving the bonds and windows from the measured judges. Until then they stay as ADR 0004 and the launch's L17 set them.
- **Decided 2026-11-15 (#236):** D23's appeal panel is dropped; the seated judges decide an appeal (D24). The solver's deposit (D22) is on hold.
- **For the owner, after task 11.1 (#236), each to accept, change or reject** (answered 2026-11-19, above; kept as history):
  - D24: that an appeal needs a test and a stake, the stake's size (the larger of $5 and 10 % of the bounty) and where a lost stake goes (the sponsors' pool);
  - D25: sponsorship, and `SPONSOR_REWARD_BPS` (1,000 does not pay an honest sponsor; 2,500 does when its model is better);
  - D26: known-answer issues, `KNOWN_RATE` (10 % proposed), and whether to wait for #136;
  - D27: the second draw, and whether it applies only among few families or always;
  - D28 and D22: whether there is a deposit at all; if so its share and the hold; if not, which limit stands in for it;
  - whether to spend a paid run on D24's two rates (task 11.3), without which D24's safety is an assumption.
- **For the owner, after task 12.1 (#236, report measured-v5), each to accept, change or reject** (answered 2026-11-19, above; kept as history):
  - D29: the reputation cap, its base ($50), its multiplier (×1) and what a reversal costs (2 × its bounty, not a reset);
  - D30: the judges' fee at measured cost ($5.03 a submission on the base network), in place of per-check charges;
  - the pot by impact: not proposed until #247 is measured;
  - D22 again, on a narrower question: R+F needs no deposit with 3 or more active honest solvers finding a test 1 time in 4 (assumed); with one, gains of $237–3,870 a year remain and only about 2,500 closed them. Whether to accept that, keep a deposit, or keep one only while a repository has fewer than three active solvers (not simulated).
- **For the owner, after task 10.1 (#236)** (answered 2026-11-19, above; kept as history): `EVIDENCE_REWARD_BPS`, `EVIDENCE_STAKE`, `SEAT_MARGIN`, `CAP_MIN_FAMILIES` and `APPEAL_WINDOW`. `SOLVER_DEPOSIT_BPS` is on hold (2026-11-15), and the appeal panel was answered on 2026-11-15 (D24).
- **Decided 2026-11-14 (#236):**
  - one family may hold every seat while it is more than `SEAT_MARGIN` ahead (D20), with the blind-spot trust point named;
  - a rejected fix's deposit goes to the issue's bounty (D22), not to the sponsors' pool (the deposit itself: on hold since 2026-11-15);
  - the appeal panel is drawn from the families that didn't judge the fix, contenders included (D23), subject to task 10.1 (**dropped 2026-11-15**: 10.1's condition was not met);
  - ADR 0004 is replaced by a new ADR once group 10's runs are in: its bonds and windows were sized on 1.1 bad fixes per 100 paid.
- **A shared graph of code, tests, fixes and outcomes** as context for judges and contenders, and for merit (#186), is a separate proposal (owner, 2026-11-14). It doesn't change D20–D23.
- The dollar values in the k table and `BOND_FLOOR` are starting points. The simulation sets them, and the owner confirms them in an ADR (task 2.1). This doesn't change the structure.
- The randomness beacon (drand, a VRF), if the L2 chosen at D1 makes block hashes weak. It sits behind D3's interface either way.
- Keyless canaries for the scores (D14, #136): whether mutations of past merged fixes, generated from the chain's seed, can stay indistinguishable from real submissions. The scores work without them; canaries would make them sharper.
- Which zkTLS implementation and which notaries to list first. Task 1.9 measures them; the constitution's list takes whichever pass, without changing the specs.
- **For the owner, in the parameters ADR (#137), from the re-runs (#141):**
  - the published thresholds of D17: `SYBIL_SHARE` 12.5 %, `LONE_CATCH_SHARE` 90 % (of the lone validator's own verdicts), `FEE_MARGIN` 25 %, `WAIT_CROWD_MAX` 20 %, `GAIN_TOLERANCE` $10, judged by "not shown to gain";
  - the silence and withholding slash: $5 flat, or max($5, x % of the bounty), from task 8.2's sweep (D16);
  - whether a challenge panel should exclude the validators that judged the same solver's other pending fixes (round 3, finding 3: proposed, not decided);
  - the value of an ADR to a coalition that `ADR_DEPOSIT` is sized for ($1,000 in the simulation);
  - the TEE types for the deployment record, confirmed by region (D6's list is from knowledge, not checked against vendor documentation).
- **For the owner, after tasks 13.1 and 14.1 (#253, #252, report measured-v6), each to accept, change or reject:**
  - D31: a validator's capacity as a spend limit (5 an hour proposed; the rule fixed before the runs named 10, which at 7 validators caps nothing), and a repository's cap of 7 counted checks an hour once there are several repositories (none at the launch with one: post hoc, it fails there even at 1 junk fix an hour);
  - D32: reputation first, and how a newcomer's first fix gets through under spam: not a lane (task 13.6, post hoc: no share passes), but identities that cost something on the testnet (task 13.7);
  - D33 and D34: allow and deny lists with a minimum of 5 eligible validators per repository, at most 2 of one TEE type counted, only with D29 and D30; repositories below it list no bounties;
  - what ends a counted panel that can never complete (silence on a small repository leaves 3–28 % of its fixes stuck).
- **Decided 2026-11-03:**
  - level C is off at launch, so answer shopping is a trust point only once an ADR switches C on (D10);
  - one vendor's types count separately: Intel's SGX and TDX may together hold a k = 3 majority once five types are accepted. The cap counts types, not vendors; more chip makers are expected to balance this over time;
  - no ADR may remove the last accepted TEE type or image digest, since the network would halt. A replacement must be added first;
  - an escalated fix posts `ADR_DEPOSIT` too, and forfeits it to the sponsors' pool when rejected. Forfeits never go to the issue's funder or reporter, who could be the attacker;
  - round 2 (the revision note): the every-wait fee signal, $5 for silence and for withholding, the constitution from 21 (removals from 14) with a $15 deposit, two audits of every k = 1 verdict, the balanced score with recovery on fresh blocks, the TEE-type cap from k = 3 once five types are accepted, and the k = 1 hold as it is (a median 19 days to payment, on 2 % of panels);
  - round 3 (the revision note): "not shown to gain" for every attacker criterion, `LONE_CATCH_SHARE` counted on the lone validator's own verdicts with the accomplice gap named, `WAIT_CROWD_MAX` 20 % to keep the balanced score, and a sweep of the silence slash in proportion to the bounty, its value left to ADR 0004.
