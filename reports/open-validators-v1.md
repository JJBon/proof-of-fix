# Open validators, v1: the incentive simulation of v3 (proof-of-fix#134; 2026-11-02)

> **Tasks 1.1–1.8 of #134** (`openspec/changes/proof-of-fix-132-open-validators/tasks.md`): the registry and the odd panel (phase 1), proof levels, market pricing, audits and model scores, every scenario of the incentive-simulation delta, and its acceptance criteria. The spec is unchanged. Findings here are for the parameters ADR (#137); the owner decides.

**Command:** `python3 -m pof.sim market validators --seeds 40` prints every table below and the acceptance table, in 29 minutes on one core (Python 3.13). `python3 -m pof.sim.openval all --seeds 40` prints the same. One section at a time: `python3 -m pof.sim.openval {growth,attackers,sybil,audits,levels,pricing,scores,params} --seeds 40`. Every number is a mean over seeds 1–40, and every ± is **two** standard errors of that mean. "Loses" means the mean return minus the honest twin's, plus two standard errors, is below zero.

**The model** is the package `pof/sim/openval/` (simulation only: amounts are dollars, 1 credit = $1, and nothing opens a connection, rule 1). The modules: `params`, `registry`, `panels`, `net`, `actors` and `report` (phase 1), `levels` (task 1.5), `pricing` (1.4), `scores` (1.7) and `full` (1.8: the k table compared, the window's length, scores on the market fee, the acceptance criteria and the whole report). The tests are `tests/test_openval*.py`.

## Summary of findings

**The verdict: the acceptance criteria are not met** (6 of 10). The k table, windows, bonds, caps and pricing bounds shouldn't be adopted as they stand. See [the acceptance table](#acceptance-criteria-for-open-validators).

### What fails
- **k = 1 trusts one validator, and the window doesn't fix it.**
  - The colluding genesis gains **+$2,920 ± 456** a year at k = 1's 72-hour window. In none of 40 runs are all its bad fixes reversed before payment. About half are never re-run in time; the other half wait, frozen, for fresh validators that don't qualify, because the colluder sets the outcomes candidates are scored against.
  - **Longer windows shrink the gain but never make it lose** at 5 bad fixes a week: +$6,523 at 24 h, +$723 at 7 days, +$312 at 30 days. From 7 days, qualification recovers and no challenge stays frozen. At 1 bad fix a week it breaks even only at 30 days (−$0 ± 24).
  - The same weakness carries into proof levels: the genesis **test liar (+$165)**, **answer shopper (+$301)** and **chip breaker with a $50 device (+$848)** all gain.
- **The seed grinder gains (+$258 ± 79)** when a false verdict costs 20 % of the bond. With the whole bond it loses (−$378 ± 103).
- **The constitution coalition gains (+$5,196 ± 2,178 with 5 early validators, +$819 ± 450 with 3).** No ADR passes before `K_MAX` validators are eligible, but nothing stops a coalition from being most of the first `K_MAX`.
- **The fee doesn't find the validators' cost.** At design values it sits at its $0.25 ceiling all year in every run. The outage slash (5 % of the bond per missed seal) makes large bonds unprofitable, big bounties wait, and the wait signal keeps the fee up. `IDLE_HIGH` (80 %) never fires: free entry stops at about 30 % idle. Started at v2's $0.05, the network collapses in 28 of 40 runs.
- **An honest validator loses money** on the flat $0.05 fee (−$7.69 a month on a growing network, −$12.85 on a grown one). Its outage slashes alone are about three times its fees.
- **Inflating validators gain a little (+$42 ± 22)**, because 3 validators of one family can set its token price. Every validator posting every family's list price removes it.
- **Answer shopping pays on a grown all-C network** (+$328 ± 69) when a borderline fix fools an honest model call 3 times in 10. At 1 in 10 it doesn't (−$2 ± 14, not significant).
- **Herding pays on the market fee, for a weak family.** Four undetectable herders of the 68 % family gain **+$294 ± 28** a year when the fee moves (no outage slash). Herding lifts their family's score from 66 % to 74 %, above `SCORE_MIN`, so it is barred 17 % of the year instead of 85 %, and bad fixes merged triple (4.59 per 100 paid against 1.38). At design values they lose (−$157 ± 57), but only because the outage slash makes every draw a loss.
- **A bribed cheater isn't deterred by 5 % audits alone** (−$34 ± 47, not significant). 10 % deters it.

### What holds
- **The sybil loses** (−$1,494 ± 486 spread out, −$2,122 ± 329 on one host). The caps keep one host, TEE type and family from any majority, even at 49 % of the validators. Spread over 3 of each, it never holds a majority up to 12 %, and holds one on 1.4 % of panels at 22 %.
- **No ADR passes while fewer than `K_MAX` validators are eligible**, in any run.
- **The silent judge, the fee farmer, the cartel and the spammer lose.** k never shrank when a judge went silent.
- **In a grown network, the TEE-less test liar (−$899) and the chip breaker (−$3,220) lose heavily.** Hidden-test bounties never reached a level C validator.
- **The k table beats a fixed k of 3.** It can start from one validator; a fixed 3 judges nothing in 40 of 40 runs. On small and grown networks it merges about 7–9 times fewer bad fixes (1.4 against 8.5 a year; 0.9 against 8.2), nobody waits (against 21 % and 8 %), and verdicts are final in 0.4–0.6 days (against 1.4–2.2). It costs twice as much per paid fix ($1.78 against $0.92).
- **Scores track quality, and pay by score helps.** Each family scores 1–2 points under its true accuracy, the weak family is barred most of the year, and bad fixes merged fall (1.26 against 1.52 per 100 paid). On the market fee, validators' pay now follows quality (`top` +$4.02, `mid` +$2.82, `low` +$1.71, `weak` −$4.01 a month when the fee moves).
- **Weighted votes don't earn their risk** (no significant change in bad fixes merged). One vote per judge stands.
- **Everyone moving to the top model doesn't collapse the market.** The per-family cap holds in every panel; the market settles with several families. The cost is liveness: 12 % of submissions wait.
- **Audits work against a lazy cheater from 2 %**, and volunteers make every cheater lose.

### What must change
The list is in [Parameters to drop or change](#parameters-to-drop-or-change). In short: the outage slash, the false-verdict slash, `IDLE_HIGH`, `FEE_START`, the wait signal, per-family price posting, k = 1's safeguards (not only its window), the constitution's quorum pool, `AUDIT_RATE`, and how shadow verdicts count toward a family's score.

## Phase 1: the registry, the odd panel and the first attackers (tasks 1.1–1.3, 1.6)

> **Scope.** Every validator is treated as level A. Its level is recorded, and the tables per (k, level) hold all three columns, but no B or C rules are applied. The service fee is v2's flat $0.05, and there are no model scores. The sections after this one add each of those.

### In short

| Question | Answer (40 seeds, ± 2 standard errors) |
|---|---|
| **Growth from one validator** (one newcomer a week, 30 submissions a week) | For a small bounty, k reaches 3 at about **week 18** (every run) and 7 at about **week 32** (33 of 40 runs). The largest bounty a panel can judge rises from $50 to about $337 by week 48. But **68 % of the year's submissions wait**, and **64 % are withdrawn** after 14 days. Of 54 newcomers only **18 qualify**, taking **135 days** on average. |
| **What limits growth** | Two things. **Qualification:** candidates qualify only as shadows on *drawn* submissions, at 2 a draw, and on a small network most submissions wait instead of being drawn. **The caps:** **39 % ± 9 of draws** come out smaller than the eligible count allows, the same at `DRAW_TRIES` = 1,000. With 3 accepted TEE types and at most (k − 1) / 2 per type, every panel of 3 needs one validator of each TEE type, besides 3 hosts and 3 families. |
| **Attackers against their honest twins** | **Lose:** the sybil (−$1,494 ± 486 spread out; −$2,122 ± 329 on one host), the silent judge (−$3,813 ± 123) and the fee farmer (−$544 ± 3). **Win on the specs' defaults:** the **colluding lone validator (+$2,920 ± 456)**, the **seed grinder (+$258 ± 79)** and the **constitution coalition** (+$5,196 ± 2,178 with 5 early validators, +$819 ± 450 with 3). |
| **The colluding genesis validator** | It also **stalls everyone's qualification**: 3.1 newcomers qualify in its year, against 13.3 in its twin's. Candidates' shadow verdicts are scored against final outcomes, and on a k = 1 network the colluder sets those outcomes. Neither the whole bond as the slash nor design D4's stricter challenge rule makes it lose. |
| **The sybil's share** | A sybil confined to one host, TEE type and family **never** holds a majority, even at 49 % of the validators. A sybil spread over 3 of each holds a majority of its own panels: never at 12 % (40 runs), on **1.2 %** of them at 22 %, **8 %** at 32 % and **30 %** at 49 %. |
| **The watcher's dilemma** (one cheater among 16 validators, cheating on 10 % of its draws, no volunteers) | A lazy cheater gains with nobody watching (+$13.7 ± 7.4). At a 1 % audit rate the result isn't significant; from 2 % it loses. A cheater bribed $5 a cheat gains up to 1 %, isn't significant at 2–5 %, and loses from 10 %. With volunteers re-running verdicts, both lose at every rate. Audits cost **$0.0089 a check at 5 %**. |
| **An honest validator's month** (at 30 submissions a week, over the growth year) | **−$8.01:** fees $0.74, less overhead $0.22, slashes for outages $2.05, fixed costs $4.67 and the bond's capital $1.82. v2's no-reveal slash (5 % of the bond for a missed seal, at 1 outage in 200 draws) costs an honest validator nearly three times its fees. |

### The model
- **The registry** (`registry.py`, task 1.1):
  - anyone registers with a bond ≥ `BOND_FLOOR`, an accepted proof type and an allowed image, signed by the new key;
  - the level is read from the proof (cloud TEE A, TEE elsewhere B, zkTLS C); candidates shadow-judge;
  - at exactly `QUALIFY_VERDICTS` shadow verdicts, a candidate is activated if its reveal rate and agreement with final outcomes meet the thresholds, or cools off and tries again;
  - an active validator with more than 5 misses in its last 50 counted draws becomes a candidate again;
  - leaving starts `UNBONDING_DELAY`, slashable throughout; at most one genesis validator.
  - There is no function that activates, removes or suspends by hand.
- **The draw** (`panels.py`, task 1.2): pure functions of a seed and a registry snapshot, so a panel can be recomputed (tested).
  - **The seed:** a 64-bit stand-in for keccak, over the hash of the block `SEED_DELAY` after the seal, the commitment, the bounty and the submission. A draw more than 256 blocks late re-targets to the latest block.
  - **k:** the largest odd number ≤ min(eligible, `K_MAX`), within the k table's limit.
  - **Rejection sampling under the caps:** one validator per declared operator, and at most (k − 1) / 2 per host, TEE type and family. `DRAW_TRIES` × k tries per k, then k steps down by 2, continuing the same sample.
  - **Replacements** come from the same sample, with a fresh window; k never shrinks.
  - **Shadows, the auditor, challenge panels and the constitution tier** are drawn from the same seed with their own counters.
- **The network** (`net.py`): an event loop in hours. Judging happens when a panel is drawn. The verdict counts when the last seated judge reveals, and the window `CHALLENGE_WINDOW[k, level]` follows. Then:
  - **Re-runs:** an audit (at `AUDIT_RATE`, by the seed) or a volunteer may re-run the check. A re-run shows a fabricated receipt with probability 0.95, and disagrees on the outcome when its own model does.
  - **Challenges:** either kind of disagreement files a challenge. The window is frozen until a fresh panel judges it, which upholds the outcome and the receipts by majority.
  - **Faults:** a false verdict is slashed `FALSE_VERDICT_SLASH_BPS`, and the challenger (an auditor) gets `CHALLENGE_REWARD_BPS` of it. An honest wrong verdict is never slashed (tested).
- **Phase 2's hooks**, each a constructor argument whose default is phase 1's behaviour:
  - `fee`: the service fee per check, plus a daily `end_period` with the queue's counts, for task 1.4;
  - `level_rule`: the panel's level, which keys the k-table limit and the window, for task 1.5;
  - `family_ok`, with `family_outcomes` (every counted verdict's agreement per family): for task 1.7.
- **Twins** (`actors.py`): each attacker runs alone; its twin is the same actor behaving honestly, on the same seeds. Randomness is bound to what it decides (submission, validator, role), not drawn from a shared stream, so both see the same submissions, newcomers and honest votes (tested). A return counts the attacker's fees and rewards and what its fixes were paid, less its running costs (`pof.checkgas.Enclave`: $0.012 a check, $4.67 a month), slashes, attempt fees, check charges and 5 % a year on the capital its bonds lock.

**The world's assumptions** (`params.World`, each named):

| Assumption | Base value | Why |
|---|---|---|
| Submissions | 30 a week, Poisson; 75 % good fixes | above today's simulated market (~7 a week), below v2's seat break-even (55) |
| Bounties | lognormal, median $86, p90 $184, at most $625 | the simulated market's paid prices ([`self-healing-v1`](self-healing-v1.md)); $625 is the k table's top |
| Newcomers | 1 a week; bonds $100 / $250 / $500 / $1,250 at 40 / 30 / 15 / 15 %; 6 hosts, 3 TEE types and 4 families, uniform | a slowly growing, mostly small network |
| Judges | right with 90 %, independently; miss a seal 1 time in 200 | honest model variance and outages |
| Volunteers | re-run a verdict at 0.25 a day (53 % of k = 1's 72 hours, 6 % of k = 7's 6 hours) | someone watches more when there's longer to watch |
| Withdrawal | a solver withdraws after 14 days of waiting | |
| Money | service fee $0.05; usage $0.13 a judge (passed through); attempt fee $0.50 | v2's values |

**Where the specs left a choice**, each is a switch in `Params`, and the report runs the alternative where it matters:
- **A challenge panel with fewer than `CHALLENGE_K[k]` eligible:** the largest odd number they allow, waiting only when none is (the spec's scenario). `CHALLENGE_WAITS_FOR_FULL` gives design D4's reading instead.
- **Eligibility by bond:** bond ≥ 2 × the bounty (the spec). `BOND_TIERS` gives D2's tier counters.
- **A counted judge's missing seal** is slashed like a missed reveal ("a missing seal counts as not revealed").
- **A false verdict** is an upheld receipt challenge, slashed 20 % (v2's `BAD_RECEIPT_SLASH_BPS`). The sensitivity rows use the whole bond, which the design's rationale for `BOND_FACTOR` assumes.
- **The cooling-off period** after a failed qualification: 7 days.
- **The reveal-rate floor** before a validator's first 50 draws: misses above 5 in its last 50, earlier draws counting as revealed.

### Growth from one validator

#### Growth from one validator (40 seeds; one newcomer a week, 30 submissions a week)

| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | Waiting submissions | Withdrawn so far |
|---|---|---|---|---|---|---|---|
| 0 | 1.0 ± 0.0 | 0.1 ± 0.1 | 1.0 | 0 % | $50 | 3.6 ± 0.6 | 0 % |
| 4 | 1.0 ± 0.0 | 4.2 ± 0.6 | 1.0 | 0 % | $50 | 46.7 ± 2.1 | 42 % |
| 8 | 1.7 ± 0.3 | 7.7 ± 1.1 | 1.4 | 20 % | $74 | 49.6 ± 2.4 | 61 % |
| 12 | 2.2 ± 0.5 | 11.5 ± 1.4 | 1.9 | 32 % | $78 | 48.2 ± 2.8 | 67 % |
| 16 | 3.5 ± 0.8 | 14.8 ± 1.7 | 2.8 | 60 % | $106 | 48.1 ± 3.9 | 70 % |
| 20 | 4.8 ± 1.3 | 17.9 ± 2.3 | 3.5 | 70 % | $128 | 42.8 ± 5.5 | 71 % |
| 24 | 7.0 ± 1.7 | 19.9 ± 2.7 | 4.6 | 90 % | $156 | 38.8 ± 5.7 | 71 % |
| 28 | 8.5 ± 2.2 | 22.3 ± 3.3 | 5.1 | 98 % | $181 | 38.6 ± 6.1 | 70 % |
| 32 | 10.0 ± 2.7 | 24.7 ± 3.7 | 5.5 | 98 % | $216 | 37.0 ± 6.5 | 69 % |
| 36 | 11.6 ± 3.2 | 27.2 ± 4.1 | 5.8 | 98 % | $239 | 35.6 ± 6.5 | 68 % |
| 40 | 13.5 ± 3.7 | 29.2 ± 4.6 | 6.2 | 98 % | $251 | 35.0 ± 6.7 | 67 % |
| 44 | 15.3 ± 4.1 | 31.1 ± 5.2 | 6.5 | 100 % | $307 | 32.3 ± 6.9 | 66 % |
| 48 | 17.3 ± 4.6 | 33.1 ± 5.7 | 6.6 | 100 % | $337 | 30.5 ± 7.0 | 65 % |

| Over the year | |
|---|---|
| Submissions that waited for a panel | 68 % ± 6 |
| ...withdrawn after 14 days of waiting | 64 % ± 6 |
| Days from submission to final verdict | 3.4 ± 0.7 |
| Bad fixes merged per 100 paid | 1.26 ± 0.33 |
| Panels drawn at k = 1 / 3 / 5 / 7 | 54 % / 5 % / 11 % / 30 % |
| Draws whose k the caps lowered (from the largest odd number of eligible validators) | 39 % ± 9 |
| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week 18 (40 of 40 runs) / week 32 (33 of 40 runs) |
| Newcomers / qualified in the year | 53.8 ± 2.1 / 18.2 ± 5.0 |
| Days from registration to activation | 135.1 ± 20.6 |
| Failed qualification attempts | 2.0 ± 0.6 |
| Challenges / verdicts reversed / challenges still frozen at year's end | 23.8 ± 2.2 / 10.0 ± 1.4 / 0.1 ± 0.2 |
| Shadows' usage repaid from the sponsors' pool | $88 |
| An activated validator's month: fees $0.74, less overhead $0.22, slashes for outages $2.05, fixed costs $4.67, the bond's capital $1.82 | net **$-8.01** |

**Reading it.**
- **k grows, but slowly:**
  - k for a small bounty passes 3 in the fifth month and 7 in the eighth;
  - until then, only bounties up to $50 (k = 1) or $250 (k = 3, with bonds of at least twice the bounty) can be judged;
  - with a median bounty of $86, most early submissions wait, and nearly two thirds of the year's are withdrawn.
- **The bottleneck is qualification, not newcomers:**
  - a candidate needs 20 shadow verdicts, and shadows are drawn only with counted panels (2 a draw while fewer than 7 are active);
  - on a network that can judge only small bounties, few submissions are drawn, so 54 newcomers yield 18 active validators in a year, and 33 candidates are still waiting at its end.
- **The caps cut panels down on a small, randomly mixed network.** 39 % of draws come out smaller than the eligible count allows (20 seeds, all draws):
  - of the draws that could have been k = 3, 72 % end at k = 1;
  - of those that could have been 5, 48 % end at 1 and 11 % at 3;
  - of those that could have been 7, 15 % end lower.

  Raising `DRAW_TRIES` from 8 to 1,000 changes nothing (36.6 % against 36.5 %), so the binding constraint is the caps themselves. With 3 accepted TEE types, a panel of 3 needs exactly one of each, a panel of 5 at most 2 of any, a panel of 7 at most 3.
- **Bad fixes merged stay low (1.26 per 100 paid):** wrong k = 1 verdicts are often re-run and reversed (10 reversals in the year).
- **An activated validator loses about $8 a month at this volume.** The biggest single loss is v2's 5 % no-reveal slash for an honest outage (1 in 200 draws), which costs an honest validator about three times its fees. That's before the queue-driven fee of task 1.4, which would rise while submissions wait.

### Each attacker against its honest twin

#### Each attacker against its honest twin (40 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families | -1,494 ± 486 | loses | -3,500 | -2,005 | 16.6 bad fixes paid of 96; a majority on 8 % of its own panels; 11.9 false verdicts proven |
| Sybil: 10 of 30 validators, one host, TEE type and family | -2,122 ± 329 | loses | -3,896 | -1,774 | 5.1 bad fixes paid of 96; a majority on 0 % of its own panels; 9.5 false verdicts proven |
| Colluding lone validator (the genesis, bonded $100) | 2,920 ± 456 | **wins** | 2,860 | -60 | 90.2 bad fixes paid of 181 attempts; 30.7 false verdicts proven, 52.8 challenges still frozen; 3.1 newcomers qualified (twin: 13.3) |
| Seed grinder (v3's seed: a later block) | 258 ± 79 | **wins** | 199 | -59 | 13.2 bad fixes paid of 40 attempts; 8.7 false verdicts proven, 0.0 challenges still frozen; 16.3 newcomers qualified (twin: 17.6) |
| Seed grinder (counterfactual: the seed fixed at the seal) | 1,306 ± 382 | **wins** | 1,246 | -60 | 72.0 bad fixes paid of 130 attempts; 57.4 false verdicts proven, 0.8 challenges still frozen; 7.3 newcomers qualified (twin: 13.6) |
| Silent judge (bribed on 10 % of its draws) | -3,813 ± 123 | loses | -4,150 | -337 | 64.1 silences, suspended 8.4 times (k never shrank) |
| Fee farmer (10 idle nodes at the bond floor; twin: one node) | -544 ± 3 | loses | -605 | -60 | 43.7 counted checks a node |
| Constitution coalition (5 early validators) | 5,196 ± 2,178 | **wins** | 4,823 | -373 | 5.3 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |
| Constitution coalition (3 early validators) | 819 ± 450 | **wins** | 589 | -230 | 0.9 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |

#### Sensitivity (40 seeds)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Sybil, spread (whole bond slashed per false verdict) | -14,082 ± 2,398 | loses | -16,088 | -2,005 | 16.4 bad fixes paid of 96; a majority on 8 % of its own panels; 12.0 false verdicts proven |
| Colluding lone validator (whole bond) | 2,707 ± 512 | **wins** | 2,648 | -60 | 90.2 bad fixes paid of 181 attempts; 30.7 false verdicts proven, 52.8 challenges still frozen; 3.1 newcomers qualified (twin: 13.3) |
| Colluding lone validator (D4's reading: challenges wait for CHALLENGE_K) | 3,096 ± 405 | **wins** | 3,036 | -60 | 92.6 bad fixes paid of 211 attempts; 4.0 false verdicts proven, 94.5 challenges still frozen; 2.4 newcomers qualified (twin: 13.1) |
| Colluding lone validator (1 bad fix a week, not 5) | 196 ± 51 | **wins** | 136 | -60 | 8.3 bad fixes paid of 16 attempts; 6.5 false verdicts proven, 0.0 challenges still frozen; 10.5 newcomers qualified (twin: 13.3) |
| Seed grinder (whole bond) | -378 ± 103 | loses | -437 | -59 | 13.2 bad fixes paid of 40 attempts; 8.7 false verdicts proven, 0.0 challenges still frozen; 16.3 newcomers qualified (twin: 17.6) |

**The attackers** (`pof.sim.openval.actors`):
- **Sybil:** 10 validators of one party under 10 declared operators, already qualified, among 20 honest ones. Its solver submits a bad fix twice a week from week 4. Its validators pass them, and defend them as auditors and on challenge panels.
- **Colluding lone validator:** the genesis validator, bonded at the $100 floor. Its solver submits a bad fix to a bounty of up to $50 on 5 days a week, while small bounties are judged at k = 1, and the genesis passes them.
- **Seed grinder:** a solver with one hidden, qualified validator. While small bounties are judged at k = 1, it submits a bad fix a day, hoping its own validator is drawn. In the counterfactual, the seed is fixed at the seal: it tries 64 commitments offline and submits only one that draws itself.
- **Silent judge:** bribed on 10 % of its draws to stay silent, for 5 % of the bounty (v2's assumption).
- **Fee farmer:** 10 nodes at the bond floor under 10 operators; its twin runs one node.
- **Constitution coalition:** 5 (or 3) validators registered at the start, spread over hosts, TEE types and families. It submits an ADR worth $1,000 to it each week; its validators pass them.

**Reading it.**
- **The sybil loses**, spread out or not. Its false verdicts are re-run and proven (12 a year at a 20 % slash of a $1,250 bond), and the bad fixes it gets paid (16.6) don't cover them. Confined to one host, the caps keep it from any majority.
- **The colluding lone validator wins, and the rules meant to stop it don't bind:**
  - **Payment only after finality, and the frozen window:** about half its bad fixes are never re-run within 72 hours, so they become final and are paid (90 of 181). The other half wait for a fresh validator.
  - **The bond:** the faults pile up while their challenges wait, and each upheld one takes a share of the *current* bond. So a whole batch costs at most the $100 bond plus top-ups. That's why the whole-bond row hardly differs.
  - **Qualification:** its passed bad fixes become the outcomes candidates are scored against. Honest shadows "disagree" and fail `QUALIFY_AGREE`, so the network stays at k = 1 for longer (3.1 newcomers qualify in its year, 13.3 in its twin's), and its window of opportunity grows.
  - **Even at 1 bad fix a week** it gains $196 ± 51.
- **The seed grinder** gains $258 ± 79 with v3's seed. The later block only makes it pay for every attempt, since its hidden validator is drawn at 1 in n. With the seed fixed at the seal it gains five times as much ($1,306), so D3 matters. A whole-bond slash makes it lose (−$378 ± 103). A grinder that discloses its validator is recused (tested).
- **The silent judge loses heavily.** k never shrank in any run; it was replaced every time. Each silence costs 5 % of its bond, and its reveal rate suspended it 8 times in the year.
- **The fee farmer loses:** idle nodes at the floor can judge only bounties up to $50, and each costs its fixed cost and capital. Task 1.4 re-runs it with the queue-driven fee: it loses there too (the pricing attackers).
- **The constitution coalition wins, though no ADR passed in any run while fewer than `K_MAX` validators were eligible.**
  - **Five early validators:** ADRs wait for `K_MAX`, but nothing stops a coalition from being most of the first `K_MAX`. Every queued ADR is drawn at once when the seventh validator qualifies, and the panel is then the whole network.
  - **Three:** honest judges' errors (10 % each) pass 0.9 ADRs of 52.

### The sybil's majorities by its share

#### The sybil's majorities by its share (40 seeds; 20 honest validators, newcomers at half a validator a week; its bad fixes at 2 a week)

| Sybil validators (share at the start) | Spread | Majority of its own panels | Majority of any panel with k ≥ 3 | Bad fixes paid | False verdicts proven |
|---|---|---|---|---|---|
| 3 (12 %) | spread | 0.0 % | 0.00 % | 1.9 | 5.2 |
| 3 (12 %) | one host | 0.0 % | 0.00 % | 1.3 | 4.6 |
| 6 (22 %) | spread | 1.2 % | 1.41 % | 6.6 | 9.3 |
| 6 (22 %) | one host | 0.0 % | 0.00 % | 3.0 | 7.4 |
| 10 (32 %) | spread | 8.1 % | 7.54 % | 16.6 | 11.9 |
| 10 (32 %) | one host | 0.0 % | 0.00 % | 5.1 | 9.5 |
| 20 (49 %) | spread | 30.5 % | 32.37 % | 40.5 | 12.1 |
| 20 (49 %) | one host | 0.0 % | 0.00 % | 9.5 | 11.1 |

**Reading it.**
- **Within one host, TEE type and family,** the caps hold a sybil to at most (k − 1) / 2 of any panel: it never had a majority. It still gets bad fixes paid when honest judges err.
- **Spread over 3 of each, the caps don't bind** below k = 7, where 3 of each is allowed. The sybil's majorities then follow its share: none in 40 runs at 12 %, then 1.2 %, 8 % and 30 % of its own panels.
- So, under the caps, the "published share" of the acceptance criterion is **between 12 % and 22 % for a spread sybil**, and unbounded for one that can't spread.

### The watcher's dilemma

#### The watcher's dilemma (40 seeds; 26 weeks; one lazy cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 28.6 | 0 % | 13.7 ± 7.4 | pays | $0.0000 |
| none | 1 % | 28.6 | 1 % | -44.0 ± 44.9 | not significant | $0.0017 |
| none | 2 % | 28.6 | 2 % | -165.7 ± 73.2 | loses | $0.0034 |
| none | 5 % | 28.6 | 5 % | -377.1 ± 107.6 | loses | $0.0089 |
| none | 10 % | 28.6 | 11 % | -784.2 ± 129.3 | loses | $0.0179 |
| none | 20 % | 28.6 | 19 % | -1,390.2 ± 200.6 | loses | $0.0362 |
| yes | 0 % | 28.6 | 6 % | -439.5 ± 99.9 | loses | $0.0000 |
| yes | 1 % | 28.6 | 7 % | -497.2 ± 102.8 | loses | $0.0017 |
| yes | 2 % | 28.6 | 9 % | -612.5 ± 122.5 | loses | $0.0034 |
| yes | 5 % | 28.6 | 11 % | -823.9 ± 156.0 | loses | $0.0089 |
| yes | 10 % | 28.6 | 17 % | -1,205.7 ± 163.0 | loses | $0.0179 |
| yes | 20 % | 28.6 | 25 % | -1,804.0 ± 228.6 | loses | $0.0362 |

#### The watcher's dilemma (40 seeds; 26 weeks; one bribed cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 6.7 | 0 % | 42.4 ± 7.1 | pays | $0.0000 |
| none | 1 % | 6.7 | 1 % | 29.6 ± 19.4 | pays | $0.0017 |
| none | 2 % | 6.7 | 3 % | -2.4 ± 37.2 | not significant | $0.0034 |
| none | 5 % | 6.7 | 5 % | -34.4 ± 46.6 | not significant | $0.0089 |
| none | 10 % | 6.7 | 11 % | -136.9 ± 64.4 | loses | $0.0179 |
| none | 20 % | 6.7 | 19 % | -277.9 ± 98.0 | loses | $0.0362 |
| yes | 0 % | 6.7 | 6 % | -66.1 ± 46.8 | loses | $0.0000 |
| yes | 1 % | 6.7 | 7 % | -79.0 ± 47.2 | loses | $0.0017 |
| yes | 2 % | 6.7 | 9 % | -111.0 ± 53.5 | loses | $0.0034 |
| yes | 5 % | 6.7 | 11 % | -143.0 ± 60.1 | loses | $0.0089 |
| yes | 10 % | 6.7 | 17 % | -239.4 ± 69.9 | loses | $0.0179 |
| yes | 20 % | 6.7 | 25 % | -380.4 ± 98.6 | loses | $0.0362 |

**Reading it.**
- **Nobody watching pays:** with no audits and no volunteers, both cheaters gain, by small amounts but significantly.
- **The `AUDIT_RATE` that deters depends on the gain per cheat:**
  - against the lazy cheater (it keeps the $0.14 a check would have cost it), 2 % is enough without volunteers;
  - against the one bribed $5 a cheat, 5 % (the starting value) isn't significant (−$34 ± 47), and 10 % is.
- **Volunteers re-running verdicts** make both lose at every audit rate.
- **What the audits catch:** each audit catches about the audit rate × 0.95 of the cheats it re-runs.
- **What they cost:** $0.0089 a check at 5 %, about 18 % of the $0.05 service fee.

## The k table compared, and the window's length (task 1.8)

### The k table compared (40 seeds; a year; 30 submissions a week; every validator at level A; the same seeds for both rules)

| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth from one validator | k table (v3) | 3.4 ± 0.6 (1.26 ± 0.33) | 390 ± 79 | 3.4 ± 0.7 | 68 ± 6 % | 64 ± 6 % | $1.12 ± 0.13 | $-7.69 ± 0.37 | 17.3 ± 4.6 |
| Growth from one validator | fixed k = 3, bounties to $625 | 0.0 ± 0.0 (0.00 ± 0.00) | 0 ± 0 | – | 100 ± 0 % | 96 ± 0 % | – | $-9.87 ± 0.00 | 1.0 ± 0.0 |
| Small: the genesis and 4 active | k table (v3) | 1.4 ± 0.4 (0.12 ± 0.03) | 1,159 ± 10 | 0.6 ± 0.1 | 0 ± 0 % | 0 ± 0 % | $1.78 ± 0.01 | $-10.18 ± 0.35 | 52.0 ± 2.1 |
| Small: the genesis and 4 active | fixed k = 3, bounties to $625 | 8.5 ± 0.9 (0.76 ± 0.08) | 1,127 ± 10 | 2.2 ± 0.1 | 21 ± 2 % | 1 ± 0 % | $0.92 ± 0.01 | $-8.47 ± 0.24 | 51.4 ± 2.0 |
| Grown: the genesis and 20 active | k table (v3) | 0.9 ± 0.3 (0.08 ± 0.03) | 1,160 ± 10 | 0.4 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $1.79 ± 0.01 | $-12.85 ± 0.39 | 46.1 ± 1.6 |
| Grown: the genesis and 20 active | fixed k = 3, bounties to $625 | 8.2 ± 1.0 (0.72 ± 0.08) | 1,133 ± 10 | 1.4 ± 0.0 | 8 ± 1 % | 1 ± 0 % | $0.87 ± 0.01 | $-10.04 ± 0.24 | 46.0 ± 1.6 |

Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with three validators, a 24-hour window and a challenge panel of 5. "–": nothing to measure (no verdict became final, or nothing was paid).

### The window's length (40 seeds; a year; growth from one validator; the colluding genesis, bonded $100, against its honest twin; k = 1's window varied, `UNBONDING_DELAY` following it)

| Colluder | k = 1's window | Return − twin's ($, ± 2 SE) | Runs it loses money | Runs none of its bad fixes is paid | Runs both (caught and loses) | Bad fixes passed / paid / reversed | Challenges still frozen at year's end | Newcomers qualified (twin's) |
|---|---|---|---|---|---|---|---|---|
| 5 bad fixes a week | 24 h | 6,523 ± 344 | 0 of 40 | 0 of 40 | 0 of 40 | 245.2 / 191.5 / 4.2 | 48.3 | 0.5 (12.7) |
| 5 bad fixes a week | 72 h | 2,920 ± 456 | 0 of 40 | 0 of 40 | 0 of 40 | 174.9 / 90.2 / 31.1 | 52.8 | 3.1 (13.3) |
| 5 bad fixes a week | 168 h | 723 ± 193 | 1 of 40 | 0 of 40 | 0 of 40 | 87.7 / 26.7 / 49.8 | 10.3 | 14.3 (15.0) |
| 5 bad fixes a week | 336 h | 361 ± 93 | 0 of 40 | 0 of 40 | 0 of 40 | 76.2 / 16.1 / 60.1 | 0.0 | 16.9 (14.2) |
| 5 bad fixes a week | 720 h | 312 ± 62 | 1 of 40 | 0 of 40 | 0 of 40 | 87.0 / 15.4 / 71.3 | 0.0 | 19.6 (13.2) |
| 1 bad fix a week | 24 h | 498 ± 121 | 0 of 40 | 0 of 40 | 0 of 40 | 19.2 / 16.1 / 3.1 | 0.0 | 10.5 (12.7) |
| 1 bad fix a week | 72 h | 196 ± 51 | 4 of 40 | 0 of 40 | 0 of 40 | 14.6 / 8.3 / 6.3 | 0.0 | 10.5 (13.3) |
| 1 bad fix a week | 168 h | 66 ± 38 | 10 of 40 | 3 of 40 | 3 of 40 | 14.9 / 4.8 / 10.1 | 0.0 | 12.8 (15.0) |
| 1 bad fix a week | 336 h | 13 ± 24 | 18 of 40 | 2 of 40 | 2 of 40 | 15.5 / 3.6 / 11.9 | 0.0 | 15.7 (14.2) |
| 1 bad fix a week | 720 h | -0 ± 24 | 21 of 40 | 2 of 40 | 2 of 40 | 18.4 / 3.7 / 14.8 | 0.0 | 13.5 (13.2) |

- **5 bad fixes a week:** the shortest window at which it is caught and loses money in at least one run: none of those tried; in every run: none of those tried. The spec's "published share" of runs isn't published.
- **1 bad fix a week:** the shortest window at which it is caught and loses money in at least one run: 168 h; in every run: none of those tried. The spec's "published share" of runs isn't published.

**How these run** (`pof.sim.openval.full`, task 1.8):
- **The k table compared:** the same seeds run with v3's k table (`Net`) and with a fixed k of 3 (`FixedKNet`). The fixed rule draws exactly 3 validators under the caps, or waits; it judges every bounty up to $625 (v2's `BOUNTY_MAX`), with k = 3's 24-hour window and a challenge panel of 5. Three networks: growth from one validator (phase 1's world), a small one (the genesis and 4 active, a newcomer a week), and a grown one (the genesis and 20 active, half a newcomer a week). The fee is phase 1's flat $0.05.
- **The window's length:** k = 1's window at level A is set to 1, 3, 7, 14 and 30 days, with `UNBONDING_DELAY` following it (the window + 7 days). The colluding genesis (bonded $100) runs against its honest twin on each, at 5 bad fixes a week and at 1. "Caught" means none of its bad fixes was paid in that run, which is what "each bad fix it passes is challenged and reversed before payment" asks.

**Reading it.**
- **A fixed k of 3 can't start a network.** From one validator, nothing is ever judged (40 of 40 runs): no panel, so no shadow seats, so nobody qualifies, and 96 % of submissions are withdrawn. The k table's k = 1 is what lets a network begin.
- **Once validators exist, the larger panels pay for themselves in safety:**
  - bad fixes merged: 1.4 against 8.5 a year on the small network, 0.9 against 8.2 on the grown one;
  - waiting: none, against 21 % and 8 % with a fixed 3 (under the caps, a panel of exactly 3 needs three different TEE types, hosts and families, and often can't be filled);
  - days to final verdict: 0.6 and 0.4, against 2.2 and 1.4 (k = 7's 6-hour window against k = 3's 24 hours).
- **They cost twice as much per paid fix** ($1.78 against $0.92): 7 judges instead of 3.
- **Validators lose more under the k table** (−$10.18 against −$8.47 a month on the small network). More draws each carry v2's outage slash, which is worth more than the $0.05 fee. That is the outage slash's problem, not the table's.
- **The window's length: no window tried makes the colluding genesis lose at 5 bad fixes a week.**
  - From 24 hours to 30 days its gain falls from $6,523 to $312 a year. Longer windows let volunteers re-run more verdicts (reversals rise from 4 to 71 a year), from 7 days newcomers qualify about as in the twin's run, and from 14 days no challenge stays frozen.
  - But a lone validator still gets paid for 15–27 bad fixes a year from 7 days up, and it is caught in **no run** at any window.
  - At 1 bad fix a week, the gain shrinks to nothing at 30 days (−$0 ± 24), and it loses money in about half the runs from 14 days.
  - So the shortest window at which a lone colluder "is caught and loses money in the published share of runs" doesn't exist in this range, for any share above 7.5 % (3 of 40 runs, at 7 days and 1 bad fix a week). The share isn't published.

## Proof levels (task 1.5)

> **Task 1.5 of #134** (design D10, D11): validators at levels A, B and C, a panel's level as its majority's weakest, the bounty limit and challenge window per (k, level), hidden tests only for all-TEE panels, the constitution's TEE types, notaries and firmware minimums, and the three level attackers against their honest twins.

**The model** is `pof/sim/openval/levels.py`: `LevelNet`, phase 1's `Net` with the level rules, so phase 1's tables are unchanged (tested: with every validator at A, a `LevelNet` run equals a `Net` run).
- **A validator's level** comes from its proof at registration: a TEE with the cloud platform's attestation is A, a TEE alone B (TDX or SEV-SNP at home or on bare metal; Nitro is AWS-only, so always A), zkTLS C.
- **A panel's level** is the lowest level a majority holds: the levels sorted strongest first, the ((k + 1) / 2)-th. So A, B, C → B, and A, A, A, A, C, C, C → A.
- **Limits and windows** come from the design's table per (k, level), already in `Params`: A $50 / $250 / $625 / $625 and 72 / 24 / 12 / 6 h; B half of A's bounties and twice its windows; C $10 / $50 / $125 / $250 and 168 / 72 / 48 / 24 h.
- **Hidden tests and private repositories:** level C validators aren't eligible as counted judges, replacements, shadows, auditors or challenge judges. Volunteers can't re-run hidden tests, so only audits and challenge panels re-check those verdicts.
- **The constitution's lists:** accepted TEE types, listed notaries (three placeholders, none required) and a minimum firmware (TCB) level per TEE type. Makers' revoked platforms and old firmware are refused at registration. An ADR that removes a type or notary, or raises a minimum, takes effect after `REMOVAL_WINDOW` (48 h); one that adds takes 14 days. Validators of a removed type or below the minimum stop being drawn and keep their bonds; a re-attestation at the new level brings them back. A zkTLS verdict proven by an unlisted notary doesn't count: the judge is treated as not having revealed (and slashed for it, as v2's rules do), and replaced.

**The world's levels** (`LevelWorld`, each an assumption): newcomers and validators active at the start are ⅓ A, ⅓ B, ⅓ C unless a row says otherwise; the genesis validator is A unless it says so; 10 % of honest bounties have hidden tests where a row says so. A **borderline** bad fix (the answer shopper's) passes an honest model call 3 times in 10, against 1 in 10 for an ordinary bad fix.

**The attackers** (each alone, against its twin on the same seeds, `levels.against_twin`):
- **Level C test liar:** a zkTLS validator that, on its own solver's bad fixes, reports passing tests it didn't get (a receipt a re-run doesn't reproduce, 95 % of the time) and defends them as an auditor or challenge judge. As the genesis, its solver submits a bad fix on 5 days a week to bounties up to k = 1's limit ($10 at C) while k = 1; as 1 of 15 validators all at C, 2 a week up to the current k's limit at C. Twin: the same validator judging honestly, no bad fixes.
- **Level C answer shopper:** its solver submits borderline bad fixes; drawn on them, its zkTLS validator calls the model up to 5 times until one passes, and keeps that call's proof. The receipt is valid, so nothing is slashable; it pays its extra calls ($0.13 each). Two twins: the same validator calling once on the same fixes (the shopping alone), and no fixes (phase 1's convention).
- **Level B chip breaker:** a home TDX server whose owner bought a memory-bus device ($1,000, or $50 for 2025's cheapest DDR4 interposer). It signs outside the official code (a forged receipt a re-run doesn't reproduce) on every draw on its own solver's bad fixes (5 a week as the genesis, within B's $25 at k = 1; 2 a week as 1 of 15 mixed validators, within B's limit for the current k), and on half its draws on other bad fixes for half the bounty if the fix is paid. Twin: the same validator, chip intact, judging honestly, no bad fixes.
- **"Without levels"** rows run the same actor with every panel judged at level A's limits and windows (phase 1's assumption), to show what the levels buy.

#### Panels by proof level (40 seeds; a year; 30 submissions a week)

| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C | Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth, all level A (phase 1's assumption) | 68 % ± 6 | 64 % ± 6 | 0 % ± 0 | 535 ± 105 | 100 % / 0 % / 0 % | 3.4 / – / – | 1.26 ± 0.33 | $337 | 17.3 ± 4.6 |
| Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C | 71 % ± 7 | 66 % ± 7 | 7 % ± 2 | 501 ± 110 | 62 % / 31 % / 7 % | 5.3 / 2.8 / 2.7 | 1.18 ± 0.25 | $232 | 15.7 ± 4.7 |
| Growth, the same with 10 % hidden-test bounties | 72 % ± 6 | 66 % ± 6 | 5 % ± 1 | 494 ± 99 | 68 % / 28 % / 4 % | 4.9 / 2.8 / 2.0 | 1.25 ± 0.30 | $242 | 15.1 ± 4.1 |
| Growth, ordinary PCs only (genesis and newcomers at C) | 100 % ± 0 | 96 % ± 0 | 18 % ± 0 | 0 ± 0 | 0 % / 0 % / 100 % | – / – / 7.1 | 0.00 ± 0.00 | $10 | 1.0 ± 0.0 |
| Grown: 21 active, ⅓ A, ⅓ B, ⅓ C | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,540 ± 13 | 20 % / 64 % / 16 % | 0.6 / 0.6 / 1.1 | 0.10 ± 0.03 | $625 | 46.1 ± 1.6 |
| Grown, the same with 10 % hidden-test bounties | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,541 ± 13 | 24 % / 61 % / 14 % | 0.5 / 0.6 / 1.1 | 0.10 ± 0.03 | $625 | 46.1 ± 1.6 |
| Grown: 21 active, all at C | 4 % ± 0 | 4 % ± 0 | 4 % ± 0 | 1,494 ± 12 | 0 % / 0 % / 100 % | – / – / 1.1 | 0.09 ± 0.03 | $250 | 46.1 ± 1.6 |

| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, replacement or shadow; all runs) |
|---|---|---|---|
| Growth, the same with 10 % hidden-test bounties | 76 % ± 5 | 71 % ± 5 | 0 |
| Grown, the same with 10 % hidden-test bounties | 1 % ± 0 | 0 % ± 0 | 0 |

**Reading it.**
- **Mixed levels slow a growing network a little.** With newcomers ⅓ at each level, 7 % of submissions wait at some point for a stronger panel (a drawn panel whose level can't judge the bounty waits and is drawn again when the registry changes). The largest bounty judged at year's end falls from $337 to $232, and verdicts take 5.3 days to become final at A (2.8 at B and C, which judge smaller bounties) against 3.4 with every validator at A. Bad fixes merged don't change (1.2 per 100 paid).
- **A network of ordinary PCs can't start from one validator.** With a genesis at C, k = 1 may judge only $10, the honest bounties (median $86) all wait, candidates have nothing to shadow, and nobody qualifies: one validator and 96 % of submissions withdrawn at year's end, in every run. Grown to 21 validators all at C, it works: 4 % of submissions (those above C's $250 at k = 7) wait and are withdrawn, and verdicts are final in 1.1 days. So the levels make an all-C network possible, but only a genesis at A or B can grow one.
- **On a grown mixed network, most panels are level B** (64 %), since with ⅓ at each level a majority of 7 usually needs a B. It still judges every bounty ($625) and waits 1 %.
- **Hidden tests never reached a level C validator** in any run (counted, replacement or shadow; auditors are also checked by a test). On a growing network, 76 % of hidden-test bounties waited (71 % withdrawn), against 72 % of all bounties: few TEE validators qualify early. On a grown one they wait 1 %.

#### Each proof-level attacker against its honest twin (40 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, extra model calls, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Test liar: the genesis at C ($10 at k = 1, 7-day window), 5 bad fixes a week | 165 ± 13 | **wins** | 105 | -61 | 47.6 bad fixes paid of 260 (largest $10); 235.1 lies: 209.3 challenged, 0.0 proven by re-runs (0 %), 0.0 reversed, 209.3 still frozen at year's end; slashed $0 |
| Test liar: the same without levels (A's $50 and 72 h) | 2,955 ± 476 | **wins** | 2,896 | -59 | 90.5 bad fixes paid of 173 (largest $49); 153.6 lies: 87.6 challenged, 36.3 proven by re-runs (24 %), 36.2 reversed, 42.6 still frozen at year's end; slashed $100 |
| Test liar: 1 of 15 validators, all at C; 2 bad fixes a week | -899 ± 102 | loses | -1,020 | -121 | 0.7 bad fixes paid of 101 (largest $60); 27.9 lies: 9.6 challenged, 7.6 proven by re-runs (27 %), 0.2 reversed, 0.0 still frozen at year's end; slashed $816 |
| Test liar: the same, whole bond slashed per false verdict | -4,088 ± 479 | loses | -4,209 | -121 | 0.7 bad fixes paid of 101 (largest $60); 27.9 lies: 9.6 challenged, 7.6 proven by re-runs (27 %), 0.2 reversed, 0.0 still frozen at year's end; slashed $3853 |
| Answer shopper: the genesis at C, 5 borderline fixes a week (twin: calls once, same fixes) | 301 ± 28 | **wins** | 322 | 21 | 136.7 verdicts flipped of 258.6 shopped (456 extra calls); outweighed by the other judges 0.0, reversed 0.0, paid 55.4; bad fixes paid 88.1 of 260 (twin 36.2); agreement with final outcomes 100.0 % (twin 97.6 %) |
| Answer shopper: the same (twin: no fixes) | 382 ± 18 | **wins** | 322 | -61 | 136.7 verdicts flipped of 258.6 shopped (456 extra calls); outweighed by the other judges 0.0, reversed 0.0, paid 55.4; bad fixes paid 88.1 of 260 (twin 0.0); agreement with final outcomes 100.0 % (twin 100.0 %) |
| Answer shopper: the same without levels (A's $50 and 72 h; twin: no fixes) | 2,340 ± 460 | **wins** | 2,281 | -59 | 56.6 verdicts flipped of 105.7 shopped (190 extra calls); outweighed by the other judges 0.0, reversed 13.7, paid 40.7; bad fixes paid 69.9 of 120 (twin 0.0); agreement with final outcomes 88.7 % (twin 92.5 %) |
| Answer shopper: 1 of 15 validators, all at C (twin: calls once, same fixes) | 328 ± 69 | **wins** | 1,087 | 760 | 17.4 verdicts flipped of 30.9 shopped (60 extra calls); outweighed by the other judges 12.8, reversed 0.9, paid 3.9; bad fixes paid 13.9 of 101 (twin 10.6); agreement with final outcomes 86.7 % (twin 89.2 %) |
| Answer shopper: the same (twin: no fixes) | 1,209 ± 144 | **wins** | 1,087 | -121 | 17.4 verdicts flipped of 30.9 shopped (60 extra calls); outweighed by the other judges 12.8, reversed 0.9, paid 3.9; bad fixes paid 13.9 of 101 (twin 0.0); agreement with final outcomes 86.7 % (twin 90.2 %) |
| Answer shopper: the same, fixes an honest call passes 1 time in 10, not 3 (twin: calls once, same fixes) | -2 ± 14 | not significant | -286 | -283 | 10.1 verdicts flipped of 31.1 shopped (99 extra calls); outweighed by the other judges 9.9, reversed 0.0, paid 0.1; bad fixes paid 0.3 of 101 (twin 0.2); agreement with final outcomes 88.4 % (twin 90.3 %) |
| Chip breaker: the genesis at B ($25 at k = 1, 144 h), forging on half its bad-fix draws, $1,000 device | -102 ± 40 | loses | -163 | -60 | 238.9 forged of 290 draws (82 %); own bad fixes paid 60.0 of 261, bribed ones 0.6 (bribes $6); largest bounty paid $25; 197.9 challenged, 0 % of forgeries proven by re-runs, 197.9 still frozen; slashed $1 |
| Chip breaker: the same, a $50 device | 848 ± 40 | **wins** | 787 | -60 | 238.9 forged of 290 draws (82 %); own bad fixes paid 60.0 of 261, bribed ones 0.6 (bribes $6); largest bounty paid $25; 197.9 challenged, 0 % of forgeries proven by re-runs, 197.9 still frozen; slashed $1 |
| Chip breaker: the same ($50) without levels (A's $50 and 72 h) | 3,940 ± 363 | **wins** | 3,881 | -59 | 233.7 forged of 485 draws (48 %); own bad fixes paid 112.1 of 228, bribed ones 13.8 (bribes $261); largest bounty paid $50; 116.5 challenged, 8 % of forgeries proven by re-runs, 97.2 still frozen; slashed $71 |
| Chip breaker: 1 of 15 validators (⅓ A, ⅓ B, ⅓ C), a $50 device | -3,220 ± 341 | loses | -3,473 | -252 | 80.3 forged of 501 draws (16 %); own bad fixes paid 0.6 of 101, bribed ones 1.0 (bribes $46); largest bounty paid $91; 5.4 challenged, 15 % of forgeries proven by re-runs, 0.0 still frozen; slashed $3093 |
| Chip breaker: the same, forging on every bad-fix draw | -5,525 ± 449 | loses | -5,777 | -252 | 134.1 forged of 501 draws (27 %); own bad fixes paid 0.6 of 101, bribed ones 1.9 (bribes $94); largest bounty paid $132; 5.4 challenged, 16 % of forgeries proven by re-runs, 0.0 still frozen; slashed $5335 |

**Reading it.**
- **The level limits shrink every attack by about an order of magnitude, but don't make the genesis attackers lose.** As the lone genesis validator (phase 1's colluding lone validator, at a weaker level):
  - the **test liar** gains $165 ± 13 at C, against $2,955 ± 476 with A's $50 and 72 hours;
  - the **answer shopper** gains $382 ± 18 (or $301 ± 28 from the shopping alone), against $2,340 ± 460;
  - the **chip breaker** loses with a $1,000 device (−$102 ± 40) but gains $848 ± 40 with a $50 one, against $3,940 ± 363 without levels.

  What holds them is the same as phase 1's finding: challenges of a k = 1 verdict wait for a fresh validator, and nobody qualifies while the attacker sets the outcomes candidates are scored against, so about 200 challenges a year stay frozen and **no lie or forgery is ever proven** (0 %). The weak level adds a second stall: a genesis at C or B judges only $10 or $25, so honest submissions wait and few candidates get anything to shadow. Its gains come from the ~20 % of its verdicts nobody re-runs within the (longer) window.
- **In a grown network, the TEE-less and broken-chip attackers lose heavily.**
  - **Test liar, 1 of 15 at C:** −$899 ± 102 (−$4,088 ± 479 with the whole bond). Its lies are rarely decisive (0.7 bad fixes paid of 101), and 27 % of them are proven by re-runs, at 20 % of the bond each.
  - **Chip breaker, 1 of 15 mixed:** −$3,220 ± 341 forging on half its bad-fix draws, −$5,525 ± 449 on all of them. Its level B vote is a minority on most panels (0.6 of its 101 own bad fixes paid), and its forgeries are proven 15 % of the time on a $1,250 bond.
- **Answer shopping pays in a grown all-C network, when borderline fixes fool an honest call 3 times in 10.**
  - **Against the twin that calls once on the same fixes: +$328 ± 69.** It flips 17 of 31 verdicts it shops; the other judges outweigh 13 of those, challenges reverse 1, and 3.9 are paid (3.3 more bad fixes paid than its twin, up to C's $250 at k = 7). Nothing is slashable, and its agreement with final outcomes drops only from 89.2 % to 86.7 %, well above `SCORE_MIN`'s 70 %, so D14's family scores (task 1.7) wouldn't stop it.
  - **When borderline fixes fool an honest call 1 time in 10,** shopping doesn't pay (−$2 ± 14): its flips are outweighed (9.9 of 10.1).
  - **Against a twin with no fixes: +$1,209 ± 144.** Most of that is the borderline fixes themselves: the twin that submits the same fixes and calls once earns $760 from honest judges' errors. That is a solver attack on the judges' accuracy, not a level C one.
- **So the acceptance criterion "each proof-level attacker loses against its honest twin" is not met:** the genesis test liar, the genesis answer shopper, the genesis chip breaker with a cheap device, and the answer shopper on a grown all-C network win. The first three share phase 1's colluding-genesis problem (a k = 1 verdict whose challenge waits for validators that never qualify). The last depends on how often a borderline fix fools an honest call, which the simulation assumes and task 1.9 or #125 could measure.

**Readings and simplifications in this section:**
- **A drawn panel too weak for its bounty** waits and is drawn again when the registry changes (and the seed re-targets), rather than drawing from stronger validators only or lowering k. The specs say a submission above the current k's limit waits, but not what happens when the draw's level is the obstacle.
- **The panel's level for the constitution tier** isn't used: an ADR's window is `ADR_WINDOW_H` (or `REMOVAL_WINDOW` for removals), whatever its judges' levels.
- **"Canary scores"** (the answer-shopping scenario) are read as D14's per-family scores from final outcomes: design D14 defers canaries to #136. The table gives the shopper's own agreement with final outcomes; the family scores are task 1.7's.
- **A TEE type added by ADR** isn't subject to the per-TEE-type cap here (the registry's `tee` knows only the three types at deployment).
- **Re-attestation after a raised firmware minimum** restores eligibility at once (the spec: "MAY return after updating and attesting again"); design D11 says they "may register again once they qualify".
- **An unlisted notary's verdict** is slashed as a missed reveal, which v2's rules imply ("treated as not having revealed"). The specs don't say whether a validator whose notary is delisted by ADR should be slashed for verdicts in flight.
- **The chip breaker's forgery** is detected like any fabricated receipt (95 % per re-run). A broken chip could also fake the model call; level B carries no zkTLS proof unless the validator adds one (D10's optional extra).

## Market pricing (task 1.4)

> **Task 1.4 of #134** (`openspec/changes/proof-of-fix-132-open-validators/tasks.md`; design D9, `specs/check-pricing`, and the incentive-simulation delta's "Market pricing in the simulation").

**The model** is `pof/sim/openval/pricing.py`. `net.py` is unchanged: the market is phase 1's `fee` hook.

### In short

| Question | Answer (40 seeds, ± 2 standard errors) |
|---|---|
| **Does the fee find the validators' cost?** (from the ceiling, design values) | **No.** It stays at the **$0.25 ceiling all year in every run**. Validators enter and leave until they break even **at the ceiling** (break-even fee $0.251 ± 0.006; 18 active). Their marginal cost is $0.096 a check: $0.012 of node overhead plus $0.084 of expected slash for an honest outage. |
| **Why it can't fall** | Both signals point up or nowhere. **22 % of submissions wait** every period, above `WAIT_HIGH` (5 %). They are almost all bounties above $125 (99 % of the waits), which need bonds of $250 or more and a larger k. Larger bonds don't pay under v2's outage slash: 5 % of the bond per missed seal is $0.31 a draw at a $1,250 bond, more than the ceiling. So 88 % of the active validators sit at $250 and the big bounties wait whatever the fee. **Idling never reaches `IDLE_HIGH` (80 %):** with free entry, validators break even at about 30 % idle. |
| **When the fee does move** (no outage slash and `IDLE_HIGH` 50 %) | It falls from the ceiling to about **$0.22** and stays there ($0.227 ± 0.005 over the last 13 weeks). That's **$0.04 above the break-even fee** ($0.186) and 19 × the marginal cost ($0.012). Under free entry the fee can only settle near the **average** cost (overhead plus fixed costs and capital spread over each validator's checks), never the marginal cost. Where it settles is set by `IDLE_HIGH` and the validators' fixed costs. |
| **A fee that starts low** | It loses the network. From v2's $0.05, validators leave within their first month, faster than `FEE_STEP` (5 % a day) can climb back. **28 of 40 runs collapse** to fewer than 3 active validators at design values, and 15 of 40 without the outage slash. The network doesn't recover even at the ceiling: one newcomer can't lift k above 1, and k = 1 judges only bounties up to $50, so no single newcomer expects to break even. `IDLE_HIGH` 30 % does the same from the ceiling (17 of 40). |
| **Unit prices** | They follow the costs. When a provider halves its price, the unit price falls 25 % a day and reaches the new median on the third day, with no vote. One absurd poster among many doesn't move the median (tested). |
| **Pricing attackers against their twins** | **Lose:** the cartel (−$5,460 ± 335), the spammer with waiting fixes (−$608 ± 19) or judged fixes (−$960 ± 43), and the fee farmer (−$435 ± 9). With a moving fee: −$657, −$391, −$934 and −$452. The cartel's refusals are all replaced (the fee doesn't move at design values, +$0.013 when it can). The spammer's waiting fixes raise the moving fee by $0.022, which doesn't repay their cost. **Win:** the **inflating validators**: +$42 ± 22 as 3 of 24, with their family's token price at 1.16 × instead of 0.98 ×, and +$48 ± 28 on a small network, at 1.68 ×. A lower median for even counts halves the gain (+$24 ± 20, still significant). **Every validator posting every family's list price removes it** (−$3 ± 14). |

### The model
- **Units** (`genesis_prices`): v2's price table (`pof.checkgas.judge_table`): input, cached and output tokens per family (open-weight at Llama's rates), vCPU- and GB-seconds, and storage, plus **gas** at $0.005 a check (the spec names gas; v2 reimbursed it at cost).
  - A counted judge uses a judge-grade medium review: 28,500 input tokens (7,000 cached) and 4,000 output, an 8-minute run on 2 vCPU and 4 GB, 1 MB and one check's gas.
  - That's $0.036 (open weights) to $0.186 (Anthropic) at deployment.
- **Costs and tables:** a validator's real costs are the provider's price × its own factor in U(0.9, 1.1), per unit group.
  - Honest validators post their real costs every period: their own family's tokens and the shared units (a reading, below).
  - Only active validators' latest tables count (`Market.counting`); a table holds units only, so no one can post a fee.
- **The two rules** (`step_price`, `step_fee`) are pure functions, applied by `Market.end_period` once per `PRICE_PERIOD`:
  - **unit prices:** move toward the median by at most 25 %, capped at 2 × deployment, and only with 3 or more posters;
  - **the fee:** rises 5 % if more than 5 % of the period's submissions waited, else falls 5 % if more than 80 % of active validators weren't drawn, within [$0.01, $0.25].
- **Quotes:** a submission is charged the fee and unit prices in effect when it was submitted, through `Net`'s fee hook. That holds even if it waits days for its panel (tested). Audits and challenge panels are paid at the submission's quote.
  - `Market.fee` returns the quoted fee plus the quoted usage, less the flat $0.13 `Net` already passes through. The solver pays the quoted fee and usage.
  - It books the validator's own usage cost, less that $0.13, as overhead. The validator nets the fee plus its usage margin.
- **Entry and exit** (`Market.on_tick`):
  - **Who:** 20 honest validators and the genesis start active (bonds $100 / $250 / $500 / $1,250 at 40 / 30 / 15 / 15 %). Prospective operators arrive at 2 a week with the same bonds; phase 1's Poisson joins are off.
  - **The rule:** a prospect registers if its expected month is positive. An honest validator reviews its month every 30 days, at a phase bound to its id, and leaves if it expects a loss. The genesis stays.
  - **The expected month:** checks × (fee + usage margin − $0.012 overhead − expected outage slash) − $4.67 fixed − 5 % a year on the bond.
  - **Expected checks:** for each issue submission of the last 30 days the bond covers, k / n. Here n is the active validators bonded for it (counting the prospect itself) and k the largest odd number n allows within the k table's limit. Waiting submissions count, so a newcomer sees the queue.
- **The attackers** (`actors.against_twin`, unchanged; `MarketMixin` installs the market from the actor's `setup`):
  - `Cartel`: 6 validators bonded $500 refuse half their counted draws (never seal);
  - `Spammer`: 3 validators of its own and a solver submitting one fix a day. "Waiting" fixes go to a $625 bounty it funds, only when no panel could judge it then; each costs the $0.50 attempt fee and 14 days of capital on the escrowed bounty. "Judged" fixes are bad fixes to ordinary bounties;
  - `Inflater`: 3 Anthropic validators post 100 × their real costs. The small-network variant runs the genesis plus 4 honest validators (one Anthropic) plus the 3 inflaters;
  - `PricedFeeFarmer`: phase 1's fee farmer under the market.

  Each twin is the same validators behaving honestly, on the same seeds. Prospects have fixed ids, so both runs see the same newcomers; whether they join depends on the prices.

**Readings where the spec left a choice:**
- **Who posts which units:** each validator posts its own family's tokens and the shared units. `MarketWorld.post_all_families` has every validator post every family's list price too; that's the remedy row.
- **The median of an even count:** the mean of the two middle values. `Params.MEDIAN_LOW_EVEN` takes the lower one, and the report runs both.
- **"Waited for a panel":**
  - a submission that couldn't be drawn when it arrived (phase 1's `waited`);
  - a counted panel stalled because its sample ran out of replacements.
- **"Not drawn":** never seated in the period. Drawn covers paid judges, silent judges and replacements.
- **The fee at deployment** (`FEE_START`): the ceiling, where the spec's scenario starts. The report also starts at v2's $0.05.
- **Not modelled:** shadows' usage is repaid at the flat $0.13 rather than at unit prices.

### The fee finds the validators' cost

#### The fee finds the validators' cost (40 seeds; a year; 20 honest validators and the genesis at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the ceiling unless stated)

| Variant | Fee at week 4 / 13 / 26 / 52 | Fee over the last 13 weeks | Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | Runs collapsed (< 3 active) | Honest validator's month |
|---|---|---|---|---|---|---|---|---|---|
| Design values | $0.248 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.096 ± 0.003 | $0.251 ± 0.006 | 18.2 ± 0.4 | 22 % ± 2 | 29 % ± 1 | 0 of 40 | $-2.65 ± 0.51 |
| Design values, starting at v2's $0.05 | $0.068 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.102 ± 0.005 | $0.874 ± 0.674 | 5.0 ± 2.1 | 68 % ± 7 | 45 % ± 5 | 28 of 40 | $-10.58 ± 1.69 |
| Design values, 100 submissions a week | $0.250 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.100 ± 0.001 | $0.211 ± 0.003 | 50.4 ± 1.8 | 4 % ± 0 | 17 % ± 1 | 0 of 40 | $1.31 ± 0.62 |
| `IDLE_HIGH` 30 % | $0.148 / $0.250 / $0.247 / $0.246 | $0.248 ± 0.001 | $0.099 ± 0.005 | $0.409 ± 0.224 | 9.3 ± 2.5 | 54 % ± 9 | 40 % ± 5 | 17 of 40 | $-6.42 ± 1.47 |
| No outage slash (`NO_REVEAL_SLASH_BPS` 0) | $0.248 / $0.245 / $0.246 / $0.250 | $0.248 ± 0.001 | $0.012 ± 0.000 | $0.205 ± 0.005 | 26.0 ± 0.5 | 5 % ± 1 | 34 % ± 1 | 0 of 40 | $-0.28 ± 0.13 |
| No outage slash, `IDLE_HIGH` 50 % | $0.219 / $0.216 / $0.224 / $0.228 | $0.227 ± 0.005 | $0.012 ± 0.000 | $0.186 ± 0.006 | 23.0 ± 0.7 | 5 % ± 1 | 30 % ± 1 | 0 of 40 | $-0.40 ± 0.14 |
| No outage slash, `IDLE_HIGH` 50 %, starting at $0.05 | $0.054 / $0.249 / $0.244 / $0.241 | $0.239 ± 0.005 | $0.012 ± 0.000 | $0.485 ± 0.307 | 11.7 ± 3.1 | 44 % ± 12 | 41 % ± 6 | 15 of 40 | $-3.77 ± 0.65 |
| No outage slash, `IDLE_HIGH` 30 % | $0.148 / $0.209 / $0.196 / $0.188 | $0.187 ± 0.012 | $0.012 ± 0.000 | $0.364 ± 0.213 | 15.5 ± 1.6 | 17 % ± 9 | 29 % ± 7 | 2 of 40 | $-1.06 ± 0.37 |

Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every row, so the fee is the validator's whole margin.

#### The fee over the year: the design's values (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.248 ± 0.002 | 21.6 ± 0.2 | 7 % ± 3 | 40 % ± 2 |
| 5–8 | $0.248 ± 0.001 | 18.2 ± 0.7 | 14 % ± 3 | 32 % ± 2 |
| 9–12 | $0.250 ± 0.000 | 14.2 ± 0.7 | 19 % ± 3 | 21 % ± 2 |
| 13–16 | $0.249 ± 0.000 | 16.3 ± 0.7 | 19 % ± 3 | 25 % ± 2 |
| 17–20 | $0.250 ± 0.000 | 17.7 ± 0.6 | 18 % ± 3 | 26 % ± 2 |
| 21–24 | $0.250 ± 0.000 | 18.1 ± 0.6 | 21 % ± 3 | 29 % ± 1 |
| 25–28 | $0.250 ± 0.000 | 17.8 ± 0.7 | 21 % ± 3 | 28 % ± 1 |
| 29–32 | $0.250 ± 0.000 | 18.1 ± 0.5 | 22 % ± 3 | 28 % ± 2 |
| 33–36 | $0.250 ± 0.000 | 18.5 ± 0.5 | 21 % ± 3 | 30 % ± 1 |
| 37–40 | $0.250 ± 0.000 | 18.4 ± 0.6 | 22 % ± 3 | 29 % ± 2 |
| 41–44 | $0.249 ± 0.000 | 18.2 ± 0.5 | 22 % ± 3 | 28 % ± 2 |
| 45–48 | $0.250 ± 0.000 | 18.1 ± 0.5 | 23 % ± 3 | 29 % ± 2 |
| 49–52 | $0.250 ± 0.000 | 18.1 ± 0.5 | 23 % ± 3 | 29 % ± 2 |

#### The fee over the year: no outage slash, `IDLE_HIGH` 50 % (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.232 ± 0.005 | 21.7 ± 0.1 | 7 % ± 3 | 40 % ± 2 |
| 5–8 | $0.215 ± 0.009 | 20.6 ± 0.6 | 7 % ± 3 | 33 % ± 1 |
| 9–12 | $0.216 ± 0.009 | 18.8 ± 1.0 | 5 % ± 2 | 24 % ± 2 |
| 13–16 | $0.218 ± 0.009 | 20.0 ± 1.1 | 6 % ± 2 | 26 % ± 2 |
| 17–20 | $0.219 ± 0.007 | 21.2 ± 1.0 | 5 % ± 2 | 26 % ± 2 |
| 21–24 | $0.219 ± 0.007 | 21.4 ± 1.0 | 6 % ± 2 | 28 % ± 2 |
| 25–28 | $0.224 ± 0.008 | 21.7 ± 0.9 | 7 % ± 2 | 29 % ± 2 |
| 29–32 | $0.227 ± 0.008 | 22.1 ± 0.9 | 6 % ± 2 | 28 % ± 2 |
| 33–36 | $0.226 ± 0.006 | 23.2 ± 0.9 | 5 % ± 2 | 30 % ± 2 |
| 37–40 | $0.227 ± 0.007 | 23.1 ± 1.1 | 6 % ± 2 | 30 % ± 2 |
| 41–44 | $0.225 ± 0.007 | 22.8 ± 0.9 | 5 % ± 2 | 29 % ± 2 |
| 45–48 | $0.227 ± 0.006 | 22.9 ± 0.9 | 5 % ± 1 | 29 % ± 2 |
| 49–52 | $0.229 ± 0.005 | 23.2 ± 0.8 | 4 % ± 1 | 30 % ± 2 |

### Unit prices

#### A provider halves its price (40 seeds; Anthropic's input-token price at the end of each day, as a multiple of its value at deployment; its validators post their new costs on day 30)

| End of day | 29 | 30 | 31 | 32 | 33 | 34 | 35 |
|---|---|---|---|---|---|---|---|
| Unit price | 0.994 | 0.745 | 0.559 | 0.497 | 0.497 | 0.497 | 0.498 |

One `PRICE_STEP_MAX` step (−25 %) a day until it reaches the median of the new tables (half the old median), with no proposal or vote.

### The pricing attackers

#### The pricing attackers against their honest twins (40 seeds; a year; returns in $, with bonds' capital, running costs, fees, the usage margin, slashes, attempt fees and checks counted)

| Attacker | Pricing | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's run / twin's | What it did |
|---|---|---|---|---|---|---|---|---|
| Cartel: 6 validators refusing half their draws | design | -5,460 ± 335 | loses | -5,437 | 23 | $0.249 / $0.249 | 0.98 / 0.98 | 194 refusals, suspended 32 times, slashed $4,755 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | design | -608 ± 19 | loses | -592 | 17 | $0.250 / $0.249 | 0.98 / 0.98 | 356 spam submissions costing its solver $605 |
| Spammer: a bad fix a day, judged | design | -960 ± 43 | loses | -944 | 17 | $0.250 / $0.249 | 0.97 / 0.98 | 364 spam submissions costing its solver $1,082 |
| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs | design | 42 ± 22 | **wins** | -45 | -86 | $0.249 / $0.249 | 1.16 / 0.98 | usage margin $46 (twin: $-5) |
| ... with an even count's median the lower middle value | design | 24 ± 20 | **wins** | -76 | -100 | $0.249 / $0.249 | 1.06 / 0.98 | usage margin $16 (twin: $-7) |
| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) | design | 48 ± 28 | **wins** | -93 | -141 | $0.250 / $0.250 | 1.68 / 1.00 | usage margin $68 (twin: $-2) |
| ... with every validator posting every family's list price | design | -3 ± 14 | not significant | -138 | -135 | $0.250 / $0.250 | 1.24 / 1.00 | usage margin $11 (twin: $-2) |
| Fee farmer: 10 idle validators at the bond floor (twin: one) | design | -435 ± 9 | loses | -474 | -39 | $0.249 / $0.249 | 0.99 / 0.98 | service fees $161 (twin: $26) |
| Cartel: 6 validators refusing half their draws | moving | -657 ± 12 | loses | -450 | 207 | $0.228 / $0.215 | 0.99 / 0.99 | 187 refusals, suspended 31 times, slashed $0 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | moving | -391 ± 109 | loses | -260 | 131 | $0.244 / $0.222 | 0.99 / 0.99 | 260 spam submissions costing its solver $550 |
| Spammer: a bad fix a day, judged | moving | -934 ± 35 | loses | -803 | 131 | $0.231 / $0.222 | 0.99 / 0.99 | 364 spam submissions costing its solver $1,051 |
| Fee farmer: 10 idle validators at the bond floor (twin: one) | moving | -452 ± 6 | loses | -495 | -43 | $0.195 / $0.221 | 0.99 / 0.99 | service fees $124 (twin: $19) |

Pricing "design": the design's values, the fee starting at the ceiling. "moving": no slash for an honest outage and `IDLE_HIGH` 50 %, where the fee moves below the ceiling (the settling table). Under "moving" a refusal isn't slashed either (`NO_REVEAL_SLASH_BPS` 0). The cartel loses by its suspensions and lost fees.

## Model scores (task 1.7)

> **Task 1.7** of `openspec/changes/proof-of-fix-132-open-validators/tasks.md` (design D14, `specs/judge-scores`, and the score scenarios of `specs/incentive-simulation`: "One vote, pay by score, weighted votes", "Everyone moves to the top model", "Herding").

**Scope.** As phase 1: every validator is level A and the market fee is phase 1's flat $0.05. The key rows run again on the market fee in the next section.

### In short

| Question | Answer (40 seeds, ± 2 standard errors) |
|---|---|
| **Do scores track quality?** | Yes. Each family's score sits about 1–2 points under its true accuracy (94.0 ± 0.5 % for a 95 % family, 67.2 ± 1.1 % for a 68 % one). The weak family is barred for **76 ± 4 %** of the year. It falls below `SCORE_MIN` once it has 50 verdicts, and its shadow verdicts keep it there. |
| **One vote with pay by score (v3) against one vote with flat pay (phase 1)** | Fewer bad fixes merged: **1.26 ± 0.12** per 100 paid against 1.52 ± 0.15 with blind spots, and 0.13 ± 0.03 against 0.31 ± 0.05 without. Fewer good fixes failed: 0.44 % against 0.90 %. Both gains come from barring the weak family. The cost is that **service fees per submission rise 39 %** ($0.499 against $0.358), because every family above the neutral 80 % earns more than 1×. |
| **Weighted votes (the rejected alternative)** | **No significant gain.** Weighted by the 0.5–2× factor, votes flip **0.35 ± 0.06 %** of verdicts. Bad fixes: 1.31 ± 0.10 against 1.26 ± 0.12 with blind spots, and 0.11 ± 0.03 against 0.13 ± 0.03 without. Good fixes failed: 0.35 ± 0.05 % against 0.44 ± 0.07 %. Weighted by the raw score (0.84–0.94), votes never flip a verdict, so the results equal one vote's. The design's risk, one family overriding a panel, needs scores far apart: two judges near `SCORE_MIN` against one near 100 % (tested). Families at 84–94 % never get there. |
| **Everyone moves to the top model** | The market **settles with several families**: after a year, `top` has 43 ± 7 % of the validators, `mid` 30 ± 6 % and `low` 24 ± 5 %. The weak family empties (2 ± 1 %). **The cap holds** in every panel, and `top` gets only 36.4 ± 0.7 % of the counted seats, because the per-family cap ((k − 1) / 2) limits how often its validators are drawn. The cost is **liveness**: 8.0 ± 3.9 % of draws step down from k = 7, and **11.6 ± 5.5 % of submissions wait** for a panel (none do when nobody moves). Bad fixes merged: 1.37 ± 0.14 against 1.26 ± 0.12, not significant. A party of 4 movers among non-movers gains nothing significant (+$12 ± 45 a year). |
| **Herding** | **Herders lose against their honest twins in every case but one, which isn't significant.** In a 90 % family, herding *lowers* the herders' agreement (78.4 % against 89.2 %) and their family's score. In a 68 % family it *raises* the score (70.5 % against 67.2 %), enough to keep the weak family drawn for most of the year (barred 36 % of it against 82 %). That is the design's herding risk: herders **double the bad fixes merged** (2.70 ± 0.22 per 100 paid against 1.25 ± 0.12). Herders with detectable receipts lose about $10,500–12,800 a year to slashes. Herders that can't be detected (an upper bound) lose $191 ± 53 in the weak family, and −$11 ± 31 in the 90 % family isn't significant. At the $0.25 fee ceiling, they lose $81–95 a year. |

### The model
- **The score** (`scores.py`, `recompute`): each family's share of its last `SCORE_WINDOW` verdicts that agreed with the final outcome. The final outcome is the verdict after its window, or the verdict of a challenge that reversed it. A reversal therefore counts as the truth (tested: the minority judge's family is scored as agreeing). The network records every counted verdict per family at finality (`Net.family_outcomes`, phase 1's hook).
  - **Barred families:** the active validators of a family below `SCORE_MIN` are drawn only as shadow judges. They get `SHADOW_PER_DRAW` seats per draw, drawn apart from the candidates' shadow seats so qualification isn't slowed. Their shadow verdicts are recorded per family (`Net.family_shadow_outcomes`) and merged into the window in time order. This is how a barred family recovers (tested: a model that gets better is drawn again).
  - **Recomputing a score from the submissions' records** gives the score the network holds (tested).
- **Eligibility** (`Net(family_ok=...)`): a family below `SCORE_MIN` over at least `SCORE_MIN_VERDICTS` verdicts (those in the window) isn't drawn for counted panels.
- **Neutral start:** with fewer than `SCORE_MIN_VERDICTS` verdicts, a family is drawn and paid as at the neutral score, the score whose factor is 1×: 80 % at the starting values.
- **Pay** (`ScoredFee`): the counted judge's market fee × its family's factor. The factor is linear from `SCORE_FACTOR_MIN` at `SCORE_MIN` to `SCORE_FACTOR_MAX` at 100 %, and bounded by both. `ScoredFee` wraps the network's fee object: the market's own state stays readable through it, and its `end_period` still runs. Audits and challenge panels are paid the unscaled fee. Metered usage is repaid in full (tested: 1.5× and 0.8× judges on one panel).
- **Weighted votes** (`Net(vote_weight=...)`, the alternative only): a verdict passes, and a challenge is upheld, on a strict majority of the weight. Votes are weighted by the family's factor or by its raw score. The constitution tier keeps its quorum count.
- **The world** (`SCORE_WORLD`, assumptions):
  - four model families, `top`, `mid`, `low` and `weak`, judging correctly 95 %, 90 %, 85 % and 68 % of the time, independently per judge;
  - a **blind spot** per family: 5 % of bad fixes fool every judge of that family at once, like a prompt injection that works on that model (`World.family_blind`; the second comparison table turns it off);
  - 16 qualified validators at the start, four per family; newcomers at half a validator a week, each family equally likely; 30 submissions a week; otherwise phase 1's world.
- **Movers** (`Movers`): once a month, each validator reconsiders with probability ½. It switches to the family whose validators earned the most service fees per head that month, if that is more than 10 % above its own family's. A switch takes effect at once, without re-qualifying (the worst case for concentration). The validator then judges with the new family's accuracy. A validator seated on a panel still waiting for a replacement switches after that panel.
- **Herders** (`Herder`): a counted judge that votes the expected majority, meaning the public base rate (the share of final verdicts that passed so far, which is pass), instead of its finding. It runs the check, so its vote differs from its receipt whenever its finding was fail.
  - **"Detectable":** that verdict is a false verdict like any other, and a re-run shows it (`rerun_detect`).
  - **"Not detectable"** is the upper bound: a herder that can steer its own model call.
  - Herders also herd as shadows, which is never re-run. That is how they lift a barred family. They judge honestly as auditors and challenge judges.

### The families' scores

#### The families' scores under v3's design (40 seeds; at the year's end)

| Family | True accuracy (assumed) | Blind spot (assumed) | Score | Fee factor (at the mean score) | Share of the year barred |
|---|---|---|---|---|---|
| `top` | 95 % | 5 % of bad fixes | 94.0 ± 0.5 % | 1.70× | 0 ± 0 % |
| `mid` | 90 % | 5 % of bad fixes | 88.5 ± 0.7 % | 1.42× | 0 ± 0 % |
| `low` | 85 % | 5 % of bad fixes | 83.8 ± 0.9 % | 1.19× | 0 ± 0 % |
| `weak` | 68 % | 5 % of bad fixes | 67.2 ± 1.1 % | 0.50× | 76 ± 4 % |

### One vote, pay by score, weighted votes
"Panels decided by one family": panels of k ≥ 3 whose verdict went against a strict majority of the judges outside one family. Under one vote this needs k ≥ 5 (2 of one family plus 1 other against 2), so it isn't zero. "Verdicts the weights flipped": verdicts that differ from the one-vote majority of the same votes. Net per month: every validator active at some point, by its family, as in phase 1.

#### One vote, pay by score, weighted votes (40 seeds; a year; families with blind spots)

| Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | Verdicts the weights flipped (%) | Service fees per submission ($) | `top` validator's net per month ($) | `mid` validator's net per month ($) | `low` validator's net per month ($) | `weak` validator's net per month ($) |
|---|---|---|---|---|---|---|---|---|---|
| One vote, flat pay (phase 1, no scores) | 1.52 ± 0.15 | 0.90 ± 0.10 | 5.87 ± 0.26 | 0.00 ± 0.00 | 0.358 ± 0.000 | -13.94 ± 0.74 | -13.37 ± 0.84 | -14.18 ± 0.83 | -14.79 ± 1.00 |
| **One vote, pay by score (v3's design)** | 1.26 ± 0.12 | 0.44 ± 0.07 | 4.00 ± 0.16 | 0.00 ± 0.00 | 0.499 ± 0.003 | -14.27 ± 0.81 | -14.20 ± 1.03 | -15.05 ± 0.96 | -10.07 ± 0.65 |
| Votes weighted by the score factor (0.5–2×) | 1.31 ± 0.10 | 0.35 ± 0.05 | 3.88 ± 0.15 | 0.35 ± 0.06 | 0.502 ± 0.003 | -14.32 ± 0.82 | -14.32 ± 1.04 | -15.14 ± 0.93 | -9.77 ± 0.56 |
| Votes weighted by the raw score | 1.26 ± 0.12 | 0.44 ± 0.07 | 4.00 ± 0.16 | 0.00 ± 0.00 | 0.499 ± 0.003 | -14.27 ± 0.81 | -14.20 ± 1.03 | -15.05 ± 0.96 | -10.07 ± 0.65 |

#### One vote, pay by score, weighted votes (40 seeds; a year; no blind spots: independent errors only)

| Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | Verdicts the weights flipped (%) | Service fees per submission ($) | `top` validator's net per month ($) | `mid` validator's net per month ($) | `low` validator's net per month ($) | `weak` validator's net per month ($) |
|---|---|---|---|---|---|---|---|---|---|
| One vote, flat pay (phase 1, no scores) | 0.31 ± 0.05 | 0.92 ± 0.11 | 4.09 ± 0.23 | 0.00 ± 0.00 | 0.358 ± 0.000 | -14.02 ± 0.85 | -13.80 ± 0.92 | -14.06 ± 0.83 | -14.44 ± 1.07 |
| **One vote, pay by score (v3's design)** | 0.13 ± 0.03 | 0.40 ± 0.06 | 2.12 ± 0.16 | 0.00 ± 0.00 | 0.512 ± 0.003 | -14.37 ± 0.92 | -14.35 ± 1.12 | -14.79 ± 0.95 | -10.14 ± 0.62 |
| Votes weighted by the score factor (0.5–2×) | 0.11 ± 0.03 | 0.34 ± 0.05 | 2.08 ± 0.13 | 0.11 ± 0.02 | 0.514 ± 0.002 | -14.32 ± 0.96 | -14.37 ± 1.09 | -14.57 ± 0.89 | -9.90 ± 0.58 |
| Votes weighted by the raw score | 0.13 ± 0.03 | 0.40 ± 0.06 | 2.12 ± 0.16 | 0.00 ± 0.00 | 0.512 ± 0.003 | -14.37 ± 0.92 | -14.35 ± 1.12 | -14.79 ± 0.95 | -10.14 ± 0.62 |

**Why the weak family's validators lose least.** At the flat $0.05 fee, a counted draw is worth less than its expected no-reveal slash. That slash is 5 % of a $1,250 bond at 1 outage in 200 draws, $0.31 a draw (phase 1's finding 6). So a barred family, drawn only as unpaid shadows, loses less than a drawn one. The per-family net here mostly measures how often each family is drawn. It should be re-read on task 1.4's market fee and a revised no-reveal slash.

### Everyone moves to the top model

#### Everyone moves to the top model (40 seeds; a year; every validator reconsiders monthly and switches to the family paying most per head when it pays 10 % more)

| | Nobody moves | Everyone moves |
|---|---|---|
| Share of drawable validators in `top` at the year's end | 29 ± 2 % | 43 ± 7 % |
| Share of drawable validators in `mid` at the year's end | 25 ± 2 % | 30 ± 6 % |
| Share of drawable validators in `low` at the year's end | 25 ± 1 % | 24 ± 5 % |
| Share of drawable validators in `weak` at the year's end | 21 ± 2 % | 2 ± 1 % |
| Families with at least 10 % of the validators | 4.0 ± 0.0 | 2.7 ± 0.2 |
| Share of counted seats held by `top` | 33.6 ± 0.7 % | 36.4 ± 0.7 % |
| Distinct families per panel (k ≥ 3) | 3.16 ± 0.02 | 3.10 ± 0.03 |
| Panels with more of one family than the cap allows | 0 ± 0 | 0 ± 0 |
| Panels drawn at k = 7 | 100 ± 0 % | 92 ± 4 % |
| Draws whose k the caps lowered | 0.0 ± 0.0 % | 8.0 ± 3.9 % |
| Submissions that waited for a panel | 0.0 ± 0.0 % | 11.6 ± 5.5 % |
| Bad fixes merged per 100 paid | 1.26 ± 0.12 | 1.37 ± 0.14 |
| Panels decided by one family | 4.00 ± 0.16 % | 3.72 ± 0.16 % |
| Family switches in the year | 0 ± 0 | 104 ± 7 |
| An activated validator's net per month ($) | -13.27 ± 0.39 | -12.60 ± 0.50 |

Four validators starting in `low` that move (in a network where nobody else does) against the same four staying in `low`: return − twin's **12 ± 45** $ a year (not significant); they made 8.8 switches.

### Herding

#### Herding (40 seeds; a year; 4 herders of one family among 16 honest validators; each votes the public base rate's majority, pass, instead of its finding)

| Herders | Their agreement with outcomes (twin's) | Their family's score (twin's) | Family barred, share of the year (twin's) | Bad fixes merged per 100 paid (twin's) | False verdicts proven | Return − twin's ($, ± 2 SE) | Herding |
|---|---|---|---|---|---|---|---|
| `mid` (90 %), receipts detectable | 78.5 ± 0.5 % (89.2 ± 0.2 %) | 84.2 ± 1.0 % (88.6 ± 0.8 %) | 0 ± 1 % (0 ± 0 %) | 3.23 ± 0.19 (1.25 ± 0.13) | 50.2 ± 3.2 | -12,782 ± 828 | loses |
| `mid` (90 %), not detectable (upper bound) | 78.4 ± 0.4 % (89.2 ± 0.2 %) | 84.3 ± 1.0 % (88.6 ± 0.8 %) | 0 ± 1 % (0 ± 0 %) | 3.24 ± 0.21 (1.25 ± 0.13) | 0.0 ± 0.0 | -11 ± 31 | not significant |
| `weak` (68 %), receipts detectable | 78.5 ± 0.5 % (67.8 ± 1.0 %) | 70.9 ± 1.4 % (67.2 ± 1.0 %) | 37 ± 5 % (82 ± 3 %) | 2.69 ± 0.22 (1.25 ± 0.12) | 40.5 ± 4.4 | -10,533 ± 1,144 | loses |
| `weak` (68 %), not detectable (upper bound) | 78.6 ± 0.5 % (67.8 ± 1.0 %) | 70.5 ± 1.3 % (67.2 ± 1.0 %) | 36 ± 5 % (82 ± 3 %) | 2.70 ± 0.22 (1.25 ± 0.12) | 0.0 ± 0.0 | -191 ± 53 | loses |
| `mid`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 78.4 ± 0.4 % (89.2 ± 0.2 %) | 84.3 ± 1.0 % (88.6 ± 0.8 %) | 0 ± 1 % (0 ± 0 %) | 3.24 ± 0.21 (1.25 ± 0.13) | 0.0 ± 0.0 | -95 ± 30 | loses |
| `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 78.6 ± 0.5 % (67.8 ± 1.0 %) | 70.5 ± 1.3 % (67.2 ± 1.0 %) | 36 ± 5 % (82 ± 3 %) | 2.70 ± 0.22 (1.25 ± 0.12) | 0.0 ± 0.0 | -81 ± 49 | loses |

### Readings chosen (the spec is unchanged)
1. **The neutral score is the one whose factor is 1×** (80 % at the starting values). The spec says a new family is "paid the unscaled service fee", and the factor is linear between `SCORE_MIN` and 100 %. A neutral score of `SCORE_MIN` would pay 0.5×.
2. **The score window counts a barred family's shadow verdicts.** The spec says its score recovers "measured by its validators' shadow verdicts", but it defines the score over "counted verdicts". The window merges the two in time order. Barred families' shadow seats are drawn apart from the candidates' seats, at `SHADOW_PER_DRAW` per draw.
3. **`SCORE_MIN_VERDICTS` counts the verdicts in the window** (at most `SCORE_WINDOW`).
4. **Only the counted judges' service fee is scaled.** Audits and challenge panels are paid the market fee unscaled, as the spec words it.
5. **Weighted votes use the factor (0.5–2×) or the raw score** as the weight, and also decide challenges. The constitution tier keeps its quorum count.
6. **A herder's vote against its own receipt is a false verdict** when re-runs can show it. Under TEE attestation (level A) a node can't sign anything but the official code's verdict, so real herding needs a broken TEE, or a judge at level C steering its model call. The "not detectable" rows bound that case.
7. **A family switch takes effect at once and keeps the validator active.** This is the worst case for concentration. The spec doesn't say whether changing the model means registering again.

## Model scores on the market fee (task 1.8)

**Why this section.** The score tables above ran on phase 1's flat $0.05 fee. There, a counted draw is worth less than its expected outage slash (5 % of a $1,250 bond at 1 outage in 200 draws, $0.31 a draw), so a barred family lost *least*, and herders lost partly because every draw lost money. Here the key rows run again on task 1.4's market fee. `scores.ScoredFee` wraps the market (`pricing.Market`) and scales only its service fee by the family's factor; metered usage is still repaid in full (tested).

**How these run** (`full.ScoreMarket`, `full.MarketHerders`): the score families (accuracies 95 / 90 / 85 / 68 %, a 5 % blind spot each) in the market's world: 20 initial validators (five per family, bonds as newcomers'), 2 prospective operators a week entering and leaving by their expected net. Two markets, as in the pricing section: "design" (the fee stays at its $0.25 ceiling) and "moving" (no outage slash, `IDLE_HIGH` 50 %, the fee about $0.23). Herders are the undetectable kind (the upper bound), 4 of one family, bonded $1,250.

**Reading it.**
- **On the market fee, pay follows quality.** With scores, a `top` validator nets +$4.02 a month on the moving market, `mid` +$2.82, `low` +$1.71 and `weak` −$4.01. Without scores, all four sit near zero. The flat-fee table's oddity (the weak family losing least) was the outage slash, not the scores.
- **Pay by score still merges fewer bad fixes** (1.33 against 1.54 per 100 paid on the moving market; 1.51 against 1.68 at design values, within the error).
- **Herders of a good family lose** on both markets (−$123 ± 58 and −$141 ± 27). Herding drags their score from 88 % to 84 % and their factor with it.
- **Herders of a weak family win when draws pay** (+$294 ± 28 on the moving market). Herding lifts the family's score from 66 % to 74 %, over `SCORE_MIN` (70 %), so it is drawn most of the year instead of being barred 85 % of it. They lose at design values (−$157 ± 57) only because each draw there costs more in expected outage slash than it pays. Either way, bad fixes merged triple while they herd (about 4.6–5.0 per 100 paid against 1.4–1.7).
- **So herding is a real risk once the outage slash is fixed.** The lever is shadow verdicts: herders also herd as shadows, which are never re-run, and a barred family's shadow verdicts count toward its score. See the parameters list.

### Scores on the market fee (40 seeds; a year; the score families' accuracies and blind spots; the market's 20 initial validators, five per family, and 2 prospects a week)

| Market | Rule | Mean service fee | Active validators (last 13 weeks) | Bad fixes merged per 100 paid | `top` validator's net per month | `mid` validator's net per month | `low` validator's net per month | `weak` validator's net per month |
|---|---|---|---|---|---|---|---|---|
| design | One vote, no scores | $0.249 ± 0.000 | 17.8 ± 0.5 | 1.68 ± 0.21 | $-1.70 ± 0.37 | $-0.81 ± 0.32 | $-0.88 ± 0.44 | $-0.52 ± 0.32 |
| design | **One vote, pay by score (v3's design)** | $0.249 ± 0.000 | 16.9 ± 0.9 | 1.51 ± 0.19 | $1.60 ± 0.70 | $2.06 ± 0.59 | $0.78 ± 0.49 | $-3.43 ± 0.27 |
| moving | One vote, no scores | $0.226 ± 0.004 | 22.5 ± 0.8 | 1.54 ± 0.14 | $-0.20 ± 0.19 | $-0.23 ± 0.21 | $-0.26 ± 0.18 | $0.34 ± 0.32 |
| moving | **One vote, pay by score (v3's design)** | $0.233 ± 0.003 | 22.7 ± 0.7 | 1.33 ± 0.13 | $4.02 ± 0.41 | $2.82 ± 0.36 | $1.71 ± 0.34 | $-4.01 ± 0.26 |

Market "design": the design's values, the fee starting at the ceiling. "moving": no slash for an honest outage and `IDLE_HIGH` 50 % (the pricing section's world where the fee moves). The families are priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight model). Prospects decide to enter on the unscaled fee: they don't know their family's factor.

### Herding on the market fee (40 seeds; a year; 4 herders of one family beside the market's validators; herding that a re-run can't detect, the upper bound)

| Herders | Their agreement with outcomes (twin's) | Their family's score (twin's) | Family barred, share of the year (twin's) | Bad fixes merged per 100 paid (twin's) | False verdicts proven | Return − twin's ($, ± 2 SE) | Herding |
|---|---|---|---|---|---|---|---|
| `mid` (90 %), not detectable, market at design values | 79.7 ± 0.5 % (89.2 ± 0.3 %) | 83.9 ± 1.1 % (88.5 ± 0.7 %) | 0 ± 0 % (0 ± 0 %) | 5.12 ± 0.35 (1.38 ± 0.12) | 0.0 ± 0.0 | -123 ± 58 | loses |
| `weak` (68 %), not detectable, market at design values | 79.8 ± 0.5 % (66.6 ± 1.4 %) | 75.6 ± 1.7 % (65.9 ± 1.2 %) | 18 ± 6 % (89 ± 3 %) | 4.99 ± 0.32 (1.66 ± 0.21) | 0.0 ± 0.0 | -157 ± 57 | loses |
| `mid` (90 %), not detectable, moving market | 79.7 ± 0.6 % (89.2 ± 0.2 %) | 84.3 ± 1.2 % (88.3 ± 0.8 %) | 0 ± 0 % (0 ± 0 %) | 4.54 ± 0.42 (1.23 ± 0.10) | 0.0 ± 0.0 | -141 ± 27 | loses |
| `weak` (68 %), not detectable, moving market | 79.9 ± 0.4 % (67.4 ± 1.2 %) | 74.4 ± 1.7 % (66.4 ± 1.0 %) | 17 ± 5 % (85 ± 3 %) | 4.59 ± 0.22 (1.38 ± 0.14) | 0.0 ± 0.0 | 294 ± 28 | gains |

Mean service fee in the herders' runs: `mid` (90 %) (market at design values): $0.250; `weak` (68 %) (market at design values): $0.249; `mid` (90 %) (moving market): $0.231; `weak` (68 %) (moving market): $0.222.

## Acceptance criteria for open validators

**How each criterion is judged** (`pof.sim.openval.full.acceptance`, from the same run as the tables):
- **"Loses against its honest twin"** means the mean of the attacker's return minus its twin's, plus two standard errors, is below zero. A row that isn't significant fails the criterion.
- **The attackers counted** are those run on the design's values: phase 1's attackers (not the seed fixed at the seal, a counterfactual) and D13's two cheaters at the design's 5 % audit rate without volunteers; the pricing attackers at design values (not the "lower median" and "every family's list price" variants, which are remedies); the proof-level attackers with the level rules on and the 20 % slash (not the "without levels" or whole-bond rows); and every herder row, on the flat fee and on the market fee.
- **Where the spec's threshold isn't published** (the sybil's share, the lone validator's share of runs, the margin around cost), the row says so, gives the number measured, and states the verdict with its condition.

### Acceptance criteria for open validators (40 seeds; sweeps on 40; ± 2 standard errors)

| Criterion | Verdict | What decides it |
|---|---|---|
| Each open-validator attacker loses against its honest twin | **not met** | 5 of 10 don't lose: Colluding lone validator (the genesis, bonded $100) (+2,920 ± 456 $); Seed grinder (v3's seed: a later block) (+258 ± 79 $); Constitution coalition (5 early validators) (+5,196 ± 2,178 $); Constitution coalition (3 early validators) (+819 ± 450 $); D13's bribed cheater (audits at 5 %, no volunteers) (-34 ± 47 $) |
| Each pricing attacker loses against its honest twin | **not met** | 2 of 6 don't lose: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (+42 ± 22 $); Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) (+48 ± 28 $) |
| Each proof-level attacker loses against its honest twin | **not met** | 7 of 11 don't lose: Test liar: the genesis at C ($10 at k = 1, 7-day window), 5 bad fixes a week (+165 ± 13 $); Answer shopper: the genesis at C, 5 borderline fixes a week (twin: calls once, same fixes) (+301 ± 28 $); Answer shopper: the same (twin: no fixes) (+382 ± 18 $); Answer shopper: 1 of 15 validators, all at C (twin: calls once, same fixes) (+328 ± 69 $); Answer shopper: the same (twin: no fixes) (+1,209 ± 144 $); Answer shopper: the same, fixes an honest call passes 1 time in 10, not 3 (twin: calls once, same fixes) (-2 ± 14 $); Chip breaker: the same, a $50 device (+848 ± 40 $) |
| Each scoring attacker (the herders) loses against its honest twin | **not met** | 2 of 10 don't lose: Herders: `mid` (90 %), not detectable (upper bound) (-11 ± 31 $); Herders: `weak` (68 %), not detectable, moving market (+294 ± 28 $) |
| The service fee settles within the published margin of validators' real cost | **not met (the fee never leaves its ceiling, so it doesn't find the cost; validators' entry and exit make the cost find the fee)** | the margin isn't published. Measured (design values, from the ceiling): the fee over the last 13 weeks $0.250, within one `FEE_STEP` of the $0.25 ceiling in 40 of 40 runs; validators' marginal cost $0.096 a check (2.6 ×), break-even fee $0.251 |
| A sybil just under the published share never holds a majority of a panel of k ≥ 3, under the caps | **met (only if the published share is at most 12 %)** | the share isn't published. Measured: a sybil spread over 3 hosts, TEE types and families never holds one up to 12 % of the validators, but does on 1.41 % of panels at 22 %; one on a single host, TEE type and family never does, at any share tried (to 49 %) |
| A sybil at the published share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported (the sybil tables). At 22 %, spread: a majority on 1.2 % of its own panels and 1.41 % of all panels of k ≥ 3, 6.6 bad fixes paid, 9.3 false verdicts proven in a year |
| The colluding lone validator: each bad fix it passes is challenged and reversed before payment, in at least the published share of runs | **not met (for any published share above 0)** | the share isn't published. Measured (the genesis, 5 bad fixes a week, k = 1's 72-hour window): every bad fix reversed before payment in 0 of 40 runs. Over the 40 runs, 1242 of the 6997 bad fixes it passed were reversed (18 %); 90.2 were paid a run |
| The constitution waits for the network: no ADR passes while fewer than K_MAX validators are eligible | **met** | ADRs passed while fewer than K_MAX were eligible: 0 (mean a run, over Constitution coalition (5 early validators) and Constitution coalition (3 early validators)) |
| Every earlier criterion holds or is named | **met** | named, not re-run: v3's simulation doesn't re-run v2's market, checking, token or split criteria. Their latest results are reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | 6 of 10 criteria not met |

## Spec gaps and contradictions
Every agent's findings, merged and deduplicated. The spec is unchanged; these are for the owner and the parameters ADR (#137). The section each came from is in brackets.

**Contradictions**
1. **The challenge panel's size.** The requirement says "a fresh panel larger than the original". Its scenario says "at least 3, or every other eligible validator if fewer", which can be 1 (the same size as k = 1) or 2 (which can tie). Design D4 says the challenge waits "if too few are eligible". Modelled: the largest odd number ≤ min(`CHALLENGE_K[k]`, eligible); D4's reading is a switch, and it makes the colluder gain more, not less. [phase 1]
2. **Eligibility by bond.** The spec says bond ≥ 2 × the bounty. Design D2's tier counters say 2 × the tier's step: a $60 bounty would need $500, not $120. The contract (task 3.1) and the simulation must agree before the replay of task 3.5. [phase 1]
3. **The slash for a false verdict.** The specs make it an upheld receipt challenge (20 % of the bond). The design's rationale for `BOND_FACTOR` ("a fault sold on the bounty, proven half the time, loses money") assumes the whole bond. The two give opposite answers for the seed grinder. [phase 1]
4. **"Settles near validators' real marginal cost"** (design D9) can't happen under free entry with fixed costs. Entry spreads any margin over idle validators, so the fee can only settle near the **average** cost at the idle share `IDLE_HIGH` allows. The acceptance criterion says "real cost" without saying marginal or average. [pricing]
5. **"The median doesn't change" when one of 15 posts an absurd price** holds exactly only when the others' values tie. With honest costs that differ, an outlier moves the median by half a rank, and with an even count by a whole step. [pricing]
6. **Re-attestation after a raised firmware minimum.** The spec: validators "MAY return after updating and attesting again". Design D11: they "may register again once they qualify". Modelled as the spec. [levels]
7. **"Canary scores"** in the answer-shopping scenario, while design D14 defers canaries to #136. Read as D14's per-family scores from final outcomes. [levels]
8. **A score over "counted verdicts", but recovery "measured by its validators' shadow verdicts".** The window merges the two in time order. [scores]
9. **A new family is "paid the unscaled service fee", but the factor is linear from `SCORE_MIN`,** where it is 0.5×. Read as a neutral score whose factor is 1× (80 % at the starting values). [scores]

**Gaps: rules the spec doesn't state**
10. **A counted judge that never seals.** The slashable faults list "a missed reveal". Whether a judge that never seals is slashed isn't said; modelled as yes (the same 5 %). [phase 1]
11. **Unbonding against a frozen window.** A challenge that waits for fresh validators can outlast `UNBONDING_DELAY`, and a leaver is slashable only for faults proven during the delay, so a leaver can escape a frozen challenge. `UNBONDING_DELAY` also names `CHALLENGE_WINDOW[1]` without a level: with level A's 72 h it is 240 h, so a level C validator (168 h at k = 1) keeps only 3 days of margin. [phase 1, levels]
12. **A drawn panel too weak for its bounty** (its level's limit is below the bounty): the spec doesn't say whether it waits, is redrawn from stronger validators, or lowers k. Modelled: it waits and is drawn again when the registry changes. [levels]
13. **The constitution tier's panel level** isn't used: an ADR's window is `ADR_WINDOW_H` whatever its judges' levels. [levels]
14. **A TEE type added by ADR** and the per-TEE-type cap; **a notary delisted by ADR** while its verdicts are in flight. [levels]
15. **The median of an even count**, and **which units a validator posts** (its own family's tokens only, or every family's list price). The contract (task 3.3) must pick the same as the simulation. [pricing]
16. **"Waited for a panel"** counts submissions that wait for reasons the fee can't fix (bond size, the caps), and doesn't say whether a stalled panel counts. Counted here. [pricing]
17. **Whether changing model family means registering again.** Modelled as not (the worst case for concentration). [scores]
18. **`SCORE_MIN_VERDICTS`** counts the verdicts in the window (at most `SCORE_WINDOW`). [scores]
19. **"A fixed k of 3"** ("The k table compared") isn't defined: its bounty limit and window. Modelled: every bounty up to $625 (v2's `BOUNTY_MAX`), k = 3's 24 hours, a challenge panel of 5. [1.8]
20. **"Every earlier criterion holds or is named"** doesn't say which runs must be repeated under v3. v3's simulation is a separate package and doesn't re-run v2's market criteria; they're named in the acceptance table. [1.8]

**Values the spec says are "published" but the design's table doesn't size**
21. The sybil's "published share"; the lone validator's "published share of runs"; "the published margin" around the validators' cost; the "published range" of k = 1's window and of the audit share. The acceptance table states the number measured for each instead. Also unnamed: an acceptable share of waiting submissions when validators crowd into one model family (12 % here). [phase 1, scores, 1.8]
22. The cooling-off period after a failed qualification (7 days assumed), the reveal-rate floor before a validator's first 50 draws, the per-draw cap on shadows' pool spend ($88 a year here, uncapped), `FEE_START` (the ceiling assumed), whether the idle share is per day or over a longer window, the TCB minimums and the notaries. [phase 1, levels, pricing]
23. Assumptions, not parameters, that move the tables: the movers' pace and margin, the blind spot's size, the families' true accuracies, how often a borderline fix fools an honest model call (3 in 10 or 1 in 10 decides whether answer shopping pays). [levels, scores]

## Parameters to drop or change
The list the spec asks for: parameters that do nothing measurable, and parameters the results say must change. Findings, not decisions; the owner decides in the ADR (#137).

**Must change**
1. **`NO_REVEAL_SLASH_BPS` = 5 % of the bond for a missed seal** (an honest outage, 1 in 200 draws).
   - It costs an honest validator about three times its fees: −$8.01 a month on a growing network, with $2.05 of outage slashes against $0.74 of fees.
   - At a $1,250 bond it is $0.31 a draw, more than the $0.25 ceiling. So 88 % of market validators sit at the $250 bond, the bounties above $125 wait (22 % of submissions), and the fee is frozen at its ceiling.
   - It also hides what the scores do (the flat-fee per-family table) and decides whether herding pays.
   - Change: a flat amount, or slash only a sealed vote that isn't revealed and leave silence to the reveal-rate floor. Without it the market fee moves.
2. **`FALSE_VERDICT_SLASH_BPS` = 20 %** (assumed: the specs' upheld receipt challenge). The seed grinder gains +$258 ± 79. With the **whole bond** (10,000) it loses (−$378 ± 103), and the spread sybil loses ten times more (−$14,082). The whole bond is what the design's `BOND_FACTOR` rationale already assumes. It doesn't stop the colluding genesis (+$2,707 ± 512): see 6.
3. **`IDLE_HIGH` = 80 %** never fires: under free entry validators stop entering at about 30 % idle. At design values it does nothing. At 50 % (without the outage slash) the fee falls to $0.227, $0.04 above break-even. At 30 % it overshoots and runs collapse (17 of 40 with the outage slash, 2 of 40 without). Set it near the break-even idle share (30–50 %), or measure idling over more than a day.
4. **`FEE_START` must be the ceiling.** From v2's $0.05 the network collapses in 28 of 40 runs: validators leave faster than a 5 % daily step can recover, and below 3 validators it never restarts. Also consider a faster rise than fall, or a `FEE_FLOOR` near the measured break-even.
5. **`WAIT_HIGH` and the wait signal.** 99 % of the waits at the ceiling are bounties above $125, which need bonds a fee can't buy (see 1). Count only waits a newcomer at the floor bond could end.
6. **k = 1's safeguards, not just `CHALLENGE_WINDOW[1]`.** No window from 1 to 30 days makes the colluding genesis lose at 5 bad fixes a week (+$312 ± 62 at 30 days), and it is caught in no run. A longer window helps a lot (+$723 at 7 days against +$2,920 at 72 hours), so 7 days or more is better than 72 hours. But it also needs one of:
   - shadows scored only on outcomes a fresh panel could have challenged (k ≥ 3), so the colluder can't stall qualification;
   - a cap on the k = 1 verdicts one validator may have pending, or no k = 1 finality until `CHALLENGE_K[1]` validators could judge a challenge;
   - a k = 1 bond sized to a batch of faults, not one (faults pending together share one bond).
7. **`CONSTITUTION_QUORUM` drawn from exactly `K_MAX` eligible** lets an early coalition be most of the first 7 (+$5,196 ± 2,178 with 5 early validators). Draw the constitution tier from at least 2 × `K_MAX` eligible, or let ADRs queued while the network was small expire.
8. **`MEDIAN_MIN_POSTERS` = 3 with each validator posting only its own family's tokens** lets 3 validators of one family set its price (+$42 ± 22, the token price at 1.16 × instead of 0.98 ×). Have every validator post every family's public list price (the gain disappears: −$3 ± 14), and take the lower median for an even count.
9. **`AUDIT_RATE` = 5 %** deters a lazy cheater but not significantly a bribed one when nobody volunteers (−$34 ± 47). 10 % does (−$137 ± 64), at $0.018 a check.
10. **Shadow verdicts in a family's score** (`SCORE_MIN` with D14's recovery). A weak family's herders lift it over `SCORE_MIN` and gain +$294 ± 28 on a moving market, tripling bad fixes merged. Count barred families' shadow verdicts only to decide recovery, not toward the counted score, or score only contested panels; keyless canaries (#136) would help.
11. **The score factor's neutral point (80 %)** sits below a typical family (84–94 %), so pay by score raises service fees per submission by 39 % on the flat fee. Normalise the factor so the network's mean is 1 ×, or set the neutral point at the median score.
12. **The per-TEE-type cap with 3 accepted TEE types** lowers k on 39 % ± 9 of a growing network's draws: a panel of 3 needs one of each type. Apply the TEE cap only from k = 5, or accept more types.
13. **A level C genesis can't grow a network** (`BOUNTY_LIMIT[C][1]` = $10 against a median bounty of $86): nobody qualifies, 96 % of submissions are withdrawn. Require the genesis to be level A or B.
14. **Qualification throughput** (`QUALIFY_VERDICTS`, `SHADOW_PER_DRAW`): on a growing network only 18 of 54 newcomers qualify in a year, after 135 days. Let candidates shadow-judge waiting submissions too.

**Do nothing measurable (at the design's values)**
15. **`DRAW_TRIES`**: 8 and 1,000 give the same share of lowered draws (36.6 % against 36.5 %). The caps bind, not the tries. Fix it low for gas; it isn't a tuning knob.
16. **`FEE_STEP`, `FEE_FLOOR` and `IDLE_HIGH`** never act at design values: the fee stays within one step of its ceiling in every run, and no run reaches the floor. They matter only once 1, 3 and 5 are fixed.
17. **`SCORE_FACTOR_MAX` = 2 ×** never binds: the best family (95 % accurate) scores 94 %, a factor of 1.70 ×.
18. **`PRICE_CAP_X` = 2 ×** never binds: the inflaters' best was 1.68 ×. `PRICE_STEP_MAX` limits how fast they get there, not how far.
19. **Weighted votes** (an alternative, not a parameter): no significant change in bad fixes merged. Keep one vote per judge.

## Parameters
Every parameter the simulation reads, with the design's starting values. `python3 -m pof.sim.openval params` prints `Params`; the level parameters are in `levels.LevelParams`.

| Name | Value | Source |
|---|---|---|
| `K_MAX` | 7 | design |
| `BOUNTY_LIMIT[level][k]` | A: 1 → $50, 3 → $250, 5 → $625, 7 → $625 · B: half of A · C: $10 / $50 / $125 / $250 | design |
| `BOND_FACTOR`, `BOND_FLOOR` | 2, $100 | design |
| `CHALLENGE_WINDOW_H[level][k]` | A: 72 / 24 / 12 / 6 h · B: twice A · C: 168 / 72 / 48 / 24 h | design |
| `CHALLENGE_K[k]` | 1 → 3, 3 → 5, 5 → 7, 7 → 7 | design |
| `SEED_DELAY` | 5 blocks | design |
| `SEAL_WINDOW_H`, `REVEAL_WINDOW_H` | 2 h, 1 h | design (#85) |
| `QUALIFY_VERDICTS`, `QUALIFY_REVEAL`, `QUALIFY_AGREE` | 20, 95 %, 80 % | design |
| `ACTIVE_REVEAL_MIN`, `ACTIVE_REVEAL_WINDOW` | 90 %, 50 draws | design |
| `UNBONDING_DELAY_H` | 240 h (72 h + 7 days) | design |
| `SHADOW_PER_DRAW`, `SHADOW_PER_DRAW_SMALL`, `SHADOW_SMALL_BELOW` | 1, 2, 7 active | design |
| `DRAW_TRIES` | 8 per seat | design |
| `GENESIS_MAX` | 1 | design |
| `CONSTITUTION_QUORUM` | 5 of `K_MAX` | design |
| `AUDIT_RATE` | 5 % | design |
| `PRICE_PERIOD_H`, `PRICE_STEP_MAX`, `PRICE_CAP_X`, `MEDIAN_MIN_POSTERS` | 24 h, 25 %, 2 × deployment, 3 | design |
| `FEE_STEP`, `WAIT_HIGH`, `IDLE_HIGH` | 5 %, 5 %, 80 % | design |
| `FEE_FLOOR`, `FEE_CEILING` | $0.01, $0.25 | design |
| `SCORE_WINDOW`, `SCORE_MIN`, `SCORE_MIN_VERDICTS` | 200, 70 %, 50 | design |
| `SCORE_FACTOR_MIN`, `SCORE_FACTOR_MAX` | 0.5 ×, 2 × | design |
| `REMOVAL_WINDOW_H`, `ADD_WINDOW_H` | 48 h, 14 days | design |
| `NO_REVEAL_SLASH_BPS`, `EQUIVOCATION_SLASH_BPS`, `BAD_RECEIPT_SLASH_BPS`, `CHALLENGE_REWARD_BPS` | 500, 10,000, 2,000, 5,000 | v2 (#85 S12, S16), as the specs say |
| `ADR_WINDOW_H` | 14 days | v2 (#85, Article 9) |
| `QUALIFY_COOLDOWN_H` | 7 days | **assumed** (spec: "a published cooling-off period") |
| `FALSE_VERDICT_SLASH_BPS` | 2,000 (sensitivity: 10,000) | **assumed** = `BAD_RECEIPT_SLASH_BPS` |
| `FEE_START` | $0.25 | **assumed** (not sized) |
| `TCB_MIN`, `NOTARIES` | level 1 per TEE type; three placeholders | **assumed** (not sized; task 1.9) |
| `CHALLENGE_WAITS_FOR_FULL`, `BOND_TIERS`, `SEED_FROM_LATER_BLOCK`, `MEDIAN_LOW_EVEN` | false, false, true, false | readings and counterfactuals (above) |

The worlds' assumptions are in `params.World` (phase 1), `levels.LevelWorld`, `pricing.MarketWorld` and `scores.SCORE_WORLD`, each described in its section.

## Tests and limits
- **Tests:** `tests/test_openval.py` (69), `test_openval_levels.py` (33), `test_openval_pricing.py` (24), `test_openval_scores.py` (18) and `test_openval_full.py` (11). The last runs `python3 -m pof.sim market validators --seeds 1 --quick` (one row per section) and checks that the same seeds give the same numbers, that the output names each acceptance criterion as met or not, and that this report does too. Together they add about 25 seconds to the check.
- **Not combined:** proof levels, market pricing and scores each run on phase 1's network with the others off, except the key score rows on the market fee above. Leaving by expected net is modelled only in the market; phase 1's actors don't leave, so the unbonding gap (gap 11) isn't exercised.
- **Not run here:** task 1.9's zkTLS spike (it makes paid model calls and needs the owner's approval).
