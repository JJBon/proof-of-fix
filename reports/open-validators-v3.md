# Open validators, v3: the re-run with #141's round 2 (proof-of-fix#141; 2026-11-03)

> **Task group 7 of #132** (`openspec/changes/proof-of-fix-132-open-validators/tasks.md`), after round 2 of the spec (PR #148). The spec is unchanged except group 7's ticked boxes. Round 2's rules are the simulation's defaults (`params.V2R2`). Round 1's rules (`params.V2R1`) and #134's (`params.V1`) stay reachable and re-run beside them on the same seeds. Level C is off at launch (owner, 2026-11-03); the level C attackers run "after C is switched on by ADR" on a grown network. Findings are for the parameters ADR (#137); the owner decides. [v1's report](open-validators-v1.md) and [v2's](open-validators-v2.md) are kept as they are.

**Command:** `python3 -m pof.sim market validators --seeds 40 --jobs 4` prints every table below, in 16 minutes on four processes (Python 3.13, `nice -n 19`). One process gives the same output (checked on `--quick`). `--v2r1` prints round 1's report and `--v1` #134's, both unchanged. Every number is a mean over seeds 1–40; every ± is **two** standard errors of that mean.

**How an attacker is judged now (D17, round 2):** it **doesn't gain** against its honest twin when the mean of its return minus the twin's is at most zero, and that mean plus two standard errors is at most `GAIN_TOLERANCE` ($10 over the year). Round 1's "loses" (the mean plus two standard errors below zero) is reported beside it. The other criteria are judged as before.

## Summary

**The verdict: not adoptable as it stands, but close. 9 of 13 criteria are met** (v2, round 1: 8 of 13; v1: 4 of 10). Round 2's rules fixed every failure they were aimed at: the market no longer collapses, silence and withholding lose, both early coalitions lose, and every herder row but one loses. Four criteria still fail. Two fail only on the sign of a mean too small to measure. One fails by 0.6 points of a lower bound. One fails on noise.

### What now holds
- **The market works.** No run of 40 collapses (round 1: 33). Over the last 13 weeks the fee is $0.212 ± 0.006 against a $0.177 ± 0.006 break-even: **1.20 ± 0.04 ×**, inside `FEE_MARGIN` (25 %).
- **The spammer and the cartel lose under the every-wait signal:** the spammer −$502 ± 71 (it lifts the fee in its run to $0.243 from $0.198, and pays $574 of attempt fees for it), the cartel −$1,976 ± 53.
- **Silence and withholding lose at $5:** the bribed silent judge −$14 ± 9, the withholder −$15 ± 9 (round 1: +$317 ± 13 and +$249 ± 12). k never shrank.
- **Both early coalitions lose with 21 eligible and the $15 deposit:** 5 early validators −$280 ± 147, 3 early −$431 ± 145. D7 derived about −$255 ± 152 and −$429 ± 135. **No adding ADR passed below 21 eligible and no removal below 14,** in any run.
- **Escalated fixes with the deposit lose like ADRs** (−$280 ± 147). Sent to the issue's funder instead, the forfeits would come back to a coalition that funds its own issue, and it gains (+$226 ± 151).
- **The coalition of removals loses:** −$456 ± 103 from 14 eligible with the deposit.
- **Every herder row but one loses** under the balanced score, including the weak family's herders at $0.25 (−$5.3 ± 3.3) and on the market (−$4.7 ± 2.4). Round 1: +$13 ± 2, +$80 ± 9 and +$33 ± 16.
- **Chance recoveries are rare:** the weak family recovers 0.12 ± 0.11 times a year (5 of 525 blocks), against 10.8 in round 1.
- **The colluding genesis doesn't gain** (−$247 ± 41), and **98.4 % ± 1.8 of its own lone bad verdicts are reversed before payment** (184 of 187).
- **Unchanged and still met:** the sybil at 12.5 % never holds a majority; every proof-level attacker loses (answer shopping at 1 in 10: −$13 ± 1); the network grows to k ≥ 3 by week 6 in 40 of 40 runs.

### What still fails
1. **The inflaters: +$2.7 ± 3.9** a year on the design's market. Their token price doesn't move (1.00 ×) and their usage margin equals their twin's. The mean is above zero by chance, so "doesn't gain" fails. Round 1: +$33 ± 4.
2. **The weak family's undetectable herders: +$0.2 ± 0.7.** Their family is barred 99 % of the year (their twin's 96 %), so they almost never judge. Same reason: a positive mean. Round 1: +$13 ± 2.
3. **The colluding genesis's catch share: 93.3 % ± 3.9** of the bad fixes it passes are reversed before payment (195 of 209), so the lower bound is 89.4 %, under `LONE_CATCH_SHARE` (90 %). Round 1: 86.6 % ± 5.1. The shortfall comes from the 22 bad fixes its accomplice submitted that the colluder didn't judge itself (an honest lone judge's mistake, or a panel of 3 drawn later). Half of those were paid: the colluder isn't a declared party, so it can sit on their challenge panels and defend them. Of its own lone verdicts, 3 of 187 were paid.
4. **Crowding into the top model: 11.3 % ± 4.9** of submissions wait, so the upper bound is 16.2 %, over `WAIT_CROWD_MAX` (15 %). Round 1: 7.9 % ± 2.4. With plain agreement for the score it is 7.7 % ± 2.5.

### v3 beside v2 and v1, criterion by criterion

| Criterion | v1 (#134's rules) | v2 (round 1) | v3 (round 2) | What decides v3 |
|---|---|---|---|---|
| Each open-validator attacker (v1, v2: "loses"; v3: "doesn't gain") | not met: 5 of 10 don't lose | not met: 4 of 11 don't lose | **met**: none of 14 gains; all 14 lose | the closest: the silent judge, −$14 ± 9 |
| Each pricing attacker | not met: the inflaters (+$42, +$48) | not met: the inflaters (+$33 ± 4, +$28 ± 4) | not met | the inflaters, +$2.7 ± 3.9 (a positive mean, not significant) |
| Each proof-level attacker | not met: 7 of 11 don't lose | met | **met** | the closest: answer shopping at 1 in 10, −$13 ± 1 |
| Each scoring attacker (herders) | not met: 2 of 10 don't lose | not met: 3 of 8 don't lose | not met | the weak family's herders, +$0.2 ± 0.7 (a positive mean); 7 of 8 lose |
| A sybil at or under the share never holds a majority | met only if the share is ≤ 12 % (unpublished) | met at 12.5 % | **met** | 0 % of panels, spread or on one host |
| A sybil above the share: reported | met | met | **met** | a majority of 1.2 % of its own panels at 22 % (spread), 8.0 % at 32 %, 30.4 % at 49 % |
| The colluding lone validator is caught | not met: 18 % reversed | not met: 86.6 % ± 5.1 | not met | 93.3 % ± 3.9 reversed (lower bound 89.4 %); it doesn't gain (−$247 ± 41) |
| The constitution waits for the network | met (from `K_MAX`) | met (from 14) | **met** (21 for adding, 14 for removals) | 0 passed below their threshold |
| The fee settles near break-even | not met: at the ceiling all year | not met: 33 of 40 runs collapse | **met** | 1.20 ± 0.04 × break-even; 0 of 40 collapse |
| Everyone crowds into one model | not a criterion (11.6 % ± 5.5) | met (7.9 % ± 2.4) | not met | 11.3 % ± 4.9 waited (upper bound 16.2 %) |
| The network still grows | not a criterion (week 18) | met (week 6) | **met** | week 6, 40 of 40 runs; a k = 1 fix paid a median 19.4 ± 3.6 days after its verdict |
| Answer shopping, the trust point | part of the proof-level row (−$2 ± 14) | met (−$13 ± 1, loses) | **met** | −$13 ± 1 at 1 in 10; +$174 ± 46 at 3 in 10 (reported) |
| Every earlier criterion holds or is named | met (named) | met (named) | **met** (named) | v2's market, checking, token and split reports stand (D15) |
| Adopt the k table, windows, bonds, caps and pricing bounds | not met: 6 of 10 not met | not met: 5 of 13 not met | not met: 4 of 13 not met | |

## The acceptance table under D17, round 2

### Acceptance criteria for open validators under D17, round 2 (40 seeds; sweeps on 40; ± 2 standard errors)

| Criterion | Verdict | Threshold | What decides it | Loses (round 1's criterion) |
|---|---|---|---|---|
| Each open-validator attacker doesn't gain against its honest twin | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 | none of 14 gains; the closest: Silent (never seals): `SILENCE_SLASH` $5 (the design) (-14 ± 9 $) | 14 of 14 lose |
| Each pricing attacker doesn't gain against its honest twin | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10 | 1 of 6 gain or aren't shown not to: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) (+2.7 ± 3.9 $) | 4 of 6 lose |
| Each proof-level attacker doesn't gain against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 | none of 7 gains; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes) (-13 ± 1 $) | 7 of 7 lose |
| Each scoring attacker (the herders) doesn't gain against its honest twin | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10 | 1 of 8 gain or aren't shown not to: Herders: `weak` (68 %), not detectable (upper bound) (+0.2 ± 0.7 $) | 7 of 8 lose |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | **met** | 0 runs | 3 validators (12.5 %), spread: a majority on 0.00 % of panels; 3 validators (12.5 %), one host: a majority on 0.00 % of panels | – |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported | reported: 6 (22 %), one host: a majority on 0.0 % of its own panels, 2.8 bad fixes paid, 10.9 false verdicts proven; 6 (22 %), spread: a majority on 1.2 % of its own panels, 6.3 bad fixes paid, 13.7 false verdicts proven; 10 (32 %), one host: a majority on 0.0 % of its own panels, 5.0 bad fixes paid, 14.0 false verdicts proven; 10 (32 %), spread: a majority on 8.0 % of its own panels, 16.0 bad fixes paid, 17.7 false verdicts proven; 20 (49 %), one host: a majority on 0.0 % of its own panels, 9.2 bad fixes paid, 15.4 false verdicts proven; 20 (49 %), spread: a majority on 30.4 % of its own panels, 39.8 bad fixes paid, 16.3 false verdicts proven | – |
| The colluding lone validator doesn't gain, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes are reversed before any payment (pooled), with two audits | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10; share − 2 SE ≥ 90 % | return − twin's -247 ± 41 $ (doesn't gain: yes); reversed before payment 93.3 % ± 3.9 % (195 of 209 that reached an outcome; 0 still pending at the year's end) | loses |
| The constitution waits for the network: no adding ADR or escalated fix passes while fewer than 21 validators are eligible, and no removal while fewer than 14, in any run | **met** | 0 runs | adding ADRs and escalated fixes passed below 21, all runs: 0 (over 3 coalitions); removals passed below 14: 0 (over 2); ADRs passed: 0.33, 0.15, 0.33, 0.45, 0.38 a run | – |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | **met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | from the ceiling, every wait counted: fee / break-even over the last 13 weeks 1.20 ± 0.04 × (the runs that didn't collapse); 0 of 40 runs collapsed below 3 active validators | – |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` (15 %) of submissions wait | **not met** | mean + 2 SE ≤ 15 % | 11.3 ± 4.9 % waited, every validator moving (registering again) | – |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | **met** | every run | 40 of 40 runs, at week 6 ± 1; the median days from a k = 1 verdict to its payment, a run: 19.4 ± 3.6 (p90 over every run: 48.5) | – |
| Answer shopping, the trust point: it doesn't gain at 1 in 10; at 3 in 10 the report gives its gain | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 at 1 in 10 | at 1 in 10: -13 ± 1 $; at 3 in 10 (reported): +174 ± 46 $; at #125's measured room (reported): -16 ± 1 $ | loses |
| Every earlier criterion holds or is named | **met** | named | named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md stand | – |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | all | 4 of 13 criteria not met | – |

**The attackers counted** (D17): those on the design's values: the sybils, the seed grinder (v3's seed), the fee farmer, the colluding genesis at 5 bad fixes a week, the silent judge and the withholder at $5, both early coalitions and the escalated-fix coalition from 21 with the deposit, both coalitions of removals (even and skewed TEE types), D13's two cheaters at 10 % without volunteers, the six pricing attackers on the design's market, the proof-level attackers with C switched on for the level C rows (answer shopping at 1 in 10), and every herder row on the design's values. **Not counted:** the counterfactual seed, the switches, round 1's and #134's rules, the 1-a-week colluder and the $1,000 removal (sensitivity rows), and answer shopping at 3 in 10 and at #125's measured room (reported as the trust point).

**For each criterion not met: the parameter that decides it, and the switch that would meet it (for the ADR, #137).**

| Criterion not met | What decides it | What would meet it, on this run's evidence |
|---|---|---|
| Each pricing attacker doesn't gain | D17's sign test: the inflaters' mean is +$2.7 with a standard error of $1.9 | No rule switch: under the every-wait signal the inflaters move no price. Judging "doesn't gain" as "not shown to gain" (mean − 2 SE ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE`) meets it: −$1.2 to +$6.6. A spec change for the owner (spec finding 1). |
| Each scoring attacker doesn't gain | the same sign test: the weak herders' +$0.2 ± 0.7 | The same reading meets it (−$0.5 to +$1.0). Plain agreement doesn't: the same herders then gain +$20 ± 7 at $0.25 and +$97 ± 31 on the market. |
| The colluding lone validator is caught | `K1_PENDING_MAX` and k = 1's window, and how the share is counted | `K1_PENDING_MAX` 20: 96.9 % ± 1.9 (honest k = 1 fixes paid a median 23.2 ± 3.0 days after the verdict, against 19.4). k = 1's window 14 days: 94.7 % ± 3.8 (25.3 ± 3.6 days). Or count only the verdicts the lone validator gave, as the spec's words say: 98.4 % ± 1.8 (spec finding 2). |
| Everyone crowds into one model | `SCORE_BALANCED`, through how long a weak family stays barred, and the noise of 40 seeds | Plain agreement: 7.7 % ± 2.5, but it brings back the herders' gain. Round 1's sliding recovery: 9.9 % ± 3.6, but the weak family recovers 9.9 times a year. Or `WAIT_CROWD_MAX` 20 %: the design's mean is 11.3 %. |

## Evidence for the open questions

### The deposit's sizing assumption (an ADR worth $1,000 to the coalition)
- **The rule works as derived.** From 21 eligible with $15, the coalition of 5 nets −$280 ± 147 (D7: about −$255 ± 152) and the coalition of 3 −$431 ± 145 (D7: about −$429 ± 135). They pass 0.33 and 0.15 ADRs a year, of 36.0 and 34.3 judged, and forfeit $506 and $484.
- **Neither lever works alone,** as D7 said. From 21 with no deposit the coalition of 5 gains +$255 ± 149. From 14 with the deposit it nets −$58 ± 259: its upper bound is +$200, so it isn't shown not to gain.
- **28 eligible adds nothing for the coalition** (−$283 ± 133 for 5 early) and delays every adding ADR: the first is judged on day 166 instead of day 122.
- **$25** makes both lose by more (−$636 ± 149, −$773 ± 155), at a higher cost to honest authors.
- **How far $1,000 can stretch** (derived from the rows above, noise not counted): the coalition of 5 would break even if an ADR were worth about $1,860 to it (its $280 loss spread over 0.33 ADRs passed a year), the coalition of 3 at about $3,870. A coalition valuing an ADR at twice the assumption could gain.
- **Not measured:** the honest cost. No honest ADR author runs in these worlds; D7's hand estimate stays about $0.39 an ADR.

### The TEE trust point with the three types realistic at launch
- **TDX, SEV-SNP and Nitro, spread evenly, the cap from k = 5:** one TEE type holds the majority of **77 % ± 8 of the panels of 3**. Panels of 3 are 14 % ± 3 of the panels drawn in a growing network's year, so one type decides 11.2 % ± 2.9 of all panels of k ≥ 3. Each of the three types is a different vendor's, so one vendor holds the same share.
- **Skewed toward TDX and SEV-SNP** (40 % each, Nitro 20 %): 73 % ± 8.
- **Five types (adding SGX and IBM SE), the cap from k = 3:** no panel of 3 has a one-type majority, even or skewed. But Intel's two types, SGX and TDX, together hold the majority of 21 % ± 11 of panels of 3 (17 % ± 10 skewed). The owner decided the cap counts types, not vendors.
- **Five types with round 1's cap from k = 5:** one type holds 55 % ± 10 of panels of 3. So the five types alone don't remove the trust point; the cap's start does.
- **What it costs:** with five types and the cap from k = 3, the caps lower 6 % ± 1 of draws (14 % ± 3 with three), and as many submissions wait (22 % ± 3 against 21 % ± 3). Bad fixes merged fall from 0.21 to 0.14 per 100 paid.
- The exposure is bounded by k = 3's limits ($250 at level A, $125 at B) and windows (24 h, 48 h). It stays a named trust point until adding ADRs bring the list to five types.

### The spammer under the every-wait signal
- **It loses: −$502 ± 71** a year. It submits 285 fixes to a $625 bounty no panel can judge yet, and they cost its solver $574.
- **It does raise the fee:** $0.243 in its runs against $0.198 in its twin's (+23 %). Honest solvers pay that difference; validators earn it.
- **The cartel** refusing half its draws loses −$1,976 ± 53, slashed $1,297 for 258 refusals and suspended 42 times. It lifts the fee to $0.217 from $0.189.
- **Under the old signals:** with round 1's floor-bond signal the market collapses in 38 of 40 runs. With the any-bond signal 4 of 40 collapse, and the spammer loses −$495 ± 69.

### Escalated fixes with the deposit
- **They behave exactly as adding ADRs:** the same tier, threshold and deposit. The coalition of 5 sending its rule changes as escalated fixes to issues it funds itself loses −$280 ± 147.
- **If forfeits went to the issue's funder,** the coalition would get its own deposits back and gain +$226 ± 151, as with no deposit at all (+$255 ± 149). This supports the owner's rule that forfeits go to the sponsors' pool.

### The coalition of removals
- **5 early validators removing the type most others use, from 14 with the deposit: −$456 ± 103** (even types, removing Nitro) and −$505 ± 97 (skewed, removing TDX).
- They pass 0.45 removals a run. A removal took effect in 18 of 40 runs, and about 7 validators stopped being drawn each time (3.2 a run). Submissions waited a little more: 13 % against their twin's 12 %.
- **Without the deposit they still lose** (−$52 ± 11): the fees taken from the removed validators don't pay for the coalition's costs.
- **If a removal were worth $1,000 to them,** they would net −$6 ± 258: not shown either way. A removal can't move money or admit anyone, so the fees are its real value here.
- The last accepted type is never removed (tested).

### Answer shopping, after C is switched on by ADR (a grown network: the genesis at A, 20 validators at C)
- **At 1 in 10:** −$13 ± 1. It flips 10.1 verdicts; the other judges outweigh 9.9.
- **At 3 in 10:** +$174 ± 46, the trust point. It flips 17.4 verdicts a year; the other judges outweigh 12.8, audits and challenges reverse 3.3, and 1.5 are paid.
- **At #125's measured room** (+3.5 points with 5 calls on borderline fixes; in this model's independent calls that is a borderline rate of 0.9 %): **−$16 ± 1.** It flips 0.9 verdicts a year, all outweighed. This is from one 7B open model on one setup (reports/determinism-v1.md), so it says the room can be small, not that it is.
- Level C stays off at launch; the test liar and the chip breaker lose heavily either way.

### Silence, withholding and the honest month at $5
- **The bribe was $5.09 a miss** (5 % of the bounty), just above the $5 slash. Both bribed judges lose about $15 a year, by the suspensions (8.4 a year) and the checks they lose.
- **A bribe above $5 still pays:** at 10 % of the bounty ($10.18 a miss) the silent judge gains +$311 ± 21. D16 names this; silence buys only a replacement's delay.
- **An honest validator's month on the market:** slashes of $0.98 ± 0.05 a month (D16 estimated $1.11 ± 0.09), and a net of −$1.43 ± 0.22 against −$6.81 ± 0.99 on round 1's collapsing market.

### The published thresholds (D17) and `GAIN_TOLERANCE`
- **`SYBIL_SHARE` 12.5 %:** met; a sybil of 3 never held a majority of a panel of k ≥ 3.
- **`LONE_CATCH_SHARE` 90 %:** see "What still fails". Two audits lifted the share from 87.1 % ± 5.1 (one audit, same seeds) to 93.3 % ± 3.9.
- **`FEE_MARGIN` 25 %:** met, with the upper bound (1.24 ×) close to the margin.
- **`WAIT_CROWD_MAX` 15 %:** see "What still fails".
- **`GAIN_TOLERANCE` $10:** never the binding part. Every failure under "doesn't gain" is a positive mean, and every upper bound of a counted row is under $10.

## What's left to change (for the ADR, #137)
Findings, not decisions. Each names the evidence; the owner decides.

1. **Keep round 2's rules.** Each did what it was chosen for: every wait counted (0 of 40 collapse), $5 for silence and withholding, 21 / 14 with a $15 deposit, two audits, the balanced score, recovery on fresh blocks of 100 at + 10 points, and the TEE cap from k = 3 at five types.
2. **D17's "doesn't gain":** consider "not shown to gain" (mean − 2 SE ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE`). It would pass the inflaters and the weak herders, whose means are within a standard error or two of zero, and still fail every attacker round 1 found gaining.
3. **`LONE_CATCH_SHARE`:** either count the lone validator's own verdicts (98.4 % ± 1.8, met), or raise `K1_PENDING_MAX` to 20 (96.9 % ± 1.9, honest k = 1 payment +4 days). k = 1's window at 14 days also meets it (94.7 % ± 3.8) but delays every honest k = 1 payment by 6 days.
4. **`WAIT_CROWD_MAX`:** keep the balanced score, and size the threshold to it (the design's mean is 11.3 %), or accept that 40 seeds can't separate 11 % from 15 %.
5. **Name the remaining trust points:** one TEE type deciding about 77 % of panels of 3 until five types are accepted (then Intel's two types about 21 %); a silence bribe above $5; answer shopping at 3 in 10 once C is on.
6. **Drop these switches:** the floor-bond and any-bond wait signals, $1 slashes and silence unslashed, one threshold of 14 for every ADR, `ADR_DEPOSIT` $0, forfeits to the issue's funder, `K1_AUDITS` 1, round 1's sliding recovery and a block of 200 at + 5 points (0.05 recoveries a year, but twice the shadow verdicts per recovery). Round 1's advice stands for `FEE_STEP_UP`, `K1_BATCH_BOND` and `C_LIMIT_X`.
7. **Not decided by this run:** the TEE types for the deployment record by region, the first zkTLS notaries, the randomness beacon and keyless canaries (#136).

## Spec findings (reported, not fixed)
1. **"Doesn't gain" fails half of the zero-effect attacks by chance** (D17; incentive-simulation, "How a criterion is judged"). Its first condition is the sign of a sample mean. An attack with no effect has a positive mean half the time. The inflaters (+$2.7 ± 3.9) and the weak herders (+$0.2 ± 0.7) fail only on that.
2. **Which bad fixes `LONE_CATCH_SHARE` counts** (incentive-simulation, "The colluding lone validator is caught": "the bad fixes it passes"). Round 1 counted every bad fix the accomplice submitted that passed, whoever judged it; this report keeps that for the verdict, to compare with round 1. Read literally, only the verdicts the lone validator gave count: 98.4 % ± 1.8 (184 of 187).
3. **A colluder sits on challenge panels of fixes it didn't judge.** It isn't a declared party to its accomplice's fixes, so nothing keeps it off them. 11 of the 22 accomplice fixes it didn't judge were paid.
4. **A disproven receipt doesn't void the verdict here.** The model (since #134) slashes the judge for an upheld receipt challenge but reverses the verdict only if the challenge panel also outvotes it. The spec says a verdict whose receipt fails "doesn't count" (judge-panels, "A verdict through a gateway"). With one judge at k = 1 that should reverse it. The queued second dispute (below) covers this whenever the other auditor disagrees.
5. **Two disputes on one verdict:** the spec says a mismatch from either auditor opens a challenge ("One auditor misses a bad fix"). The model of round 1 dropped a dispute filed while another challenge was judged. Round 2's model queues it (task 7.1, below).
6. **The deposit's honest cost is not simulated:** no honest ADR or escalated-fix author runs in these worlds.

## How the model changed (tasks 7.1–7.3)
Every round-2 rule is a named field of `Params` (`pof/sim/openval/params.py`), with the design's value as the default (`V2R2`). `params.V2R1` is the same table with round 1's rules, and `params.V1` with #134's. With `V2R1` the simulation gives round 1's numbers exactly: tested on seed 1, and `--v2r1` prints round 1's quick report byte for byte as main printed it before this change.

| Round 2's rule | Field(s) | How it runs |
|---|---|---|
| Every wait counts, once | `WAIT_SIGNAL` "every" | A submission counts in the period it starts waiting, whatever its bounty; a counted panel stalled for a replacement counts once. Round 1's floor-bond signal and the any-bond signal are switches. |
| $5 for silence and for withholding | `SILENCE_SLASH` 5, `SEALED_NO_REVEAL_SLASH` 5 | Flat, the same for every bond, for a counted judge (a challenge panel's judges included). A shadow is never slashed; a miss counts against its qualification. |
| The constitution from 21, removals from 14, a $15 deposit | `CONSTITUTION_MIN_ELIGIBLE` 21, `REMOVAL_MIN_ELIGIBLE` 14, `ADR_DEPOSIT` 15, `DEPOSIT_FORFEIT_TO` "pool" | An ADR whose only operation is a removal (`Sub.removal`) needs 14 eligible; any other ADR and any escalated fix (`Sub.escalated`) needs 21. Below that it expires and its deposit is refunded. A rejected one forfeits $15 to the sponsors' pool; a passed one gets it back at finality. A removal takes effect `REMOVAL_WINDOW_H` (48 h) after its verdict; never the last accepted type. |
| Two audits of every k = 1 verdict | `K1_AUDITS` 2 | The first auditor is drawn as in round 1. The second is drawn by the seed with its own counter, outside the panel and not the first auditor, as soon as one is eligible (checked daily). A mismatch from either files a challenge. |
| The balanced score | `SCORE_BALANCED` | The mean of a family's agreement on passed and on failed outcomes (the one kind present, if only one is). |
| Recovery on fresh blocks | `SCORE_RECOVERY` "blocks", `SCORE_RECOVER_VERDICTS` 100, `SCORE_RECOVER_MARGIN` 0.10 | From its barring on, a barred family's shadow verdicts are cut into consecutive blocks of 100, each judged once when complete, against 80 %. Round 1's test of the last 50 at each check (`SCORE_RECOVERY` "sliding") is a switch. |
| A second dispute on a k = 1 verdict | (with `K1_AUDITS` 2) | An auditor's mismatch filed while another challenge on the verdict is judged waits its turn, and is filed when that one doesn't reverse the verdict (the spec's "One auditor misses a bad fix"). Round 1 dropped it; `V2R1` and the one-audit switch still do. |
| Shadows on a held k = 1 verdict | (round 1's reading) | Scored once, by the sealed majority at the reveal, never again at finality. Unchanged code; now tested against the spec. |
| The TEE cap's start | `TEE_CAP_FROM_K` 5, `TEE_CAP_K3_TYPES` 5 | The network keeps the constitution's TEE list (`Net.tee_list`); every draw reads the cap's start from its length (`Params.tee_from`): k = 3 with five or more types, k = 5 with fewer. A removal moves it from the next draw. |
| D6's real TEE types | `World.tees`, `World.tee_weights` | Launch: AWS Nitro Enclaves, Intel TDX, AMD SEV-SNP. Five: those and Intel SGX and IBM Secure Execution. Newcomers pick a type evenly (as round 1) or skewed: TDX 40 %, SEV-SNP 40 %, Nitro 20 %; with five, 35 / 35 / 15 / 10 / 5 %. The skews are assumptions. |
| D17's round-2 criterion | `GAIN_TOLERANCE` 10 | `round2.doesnt_gain`: the mean is at most zero and the mean plus two standard errors at most $10. "Loses" is reported beside it. |

**The switches** of task 7.3 are `round2.SWITCHES`; round 1's alternatives still worth running (task 6.2) are `round2.R1_SWITCHES`, on round 2's rules. Each changes only the fields or world fields it names (tested).

**Actors added:** `actors.RemovalCoalition` (the coalition of removals); `ConstitutionCoalition(kind="escalated")` (rule changes sent as escalated fixes to issues the coalition funds itself); `actors.SilentJudge` as before, now with the bribe per miss reported. **Answer shopping at #125's measured room:** `round2.Q125`, the borderline rate at which 5 calls gain +3.5 points over one in the simulation's model of independent calls.

## The full run

Every table of the 40-seed run, as printed (headings one level down). "Round 1 (v2)" columns quote round 1's published numbers (tested to appear in reports/open-validators-v2.md); "round 1's rules" rows re-run them on the same seeds, and "#134's rules" rows v1's.

### Growth from one validator under the hold, and the TEE types

#### Growth from one validator under round 2's rules (40 seeds; one newcomer a week, 30 submissions a week)

| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | Waiting submissions | Withdrawn so far |
|---|---|---|---|---|---|---|---|
| 0 | 1.0 ± 0.0 | 0.1 ± 0.1 | 1.0 | 0 % | $50 | 3.6 ± 0.6 | 0 % |
| 4 | 3.3 ± 0.7 | 1.9 ± 0.3 | 3.0 | 65 % | $106 | 46.5 ± 4.9 | 42 % |
| 8 | 7.6 ± 0.8 | 1.8 ± 0.4 | 6.3 | 100 % | $205 | 29.6 ± 7.4 | 51 % |
| 12 | 11.6 ± 0.9 | 2.1 ± 0.5 | 6.9 | 100 % | $231 | 16.5 ± 5.6 | 46 % |
| 16 | 16.3 ± 1.2 | 1.9 ± 0.6 | 7.0 | 100 % | $269 | 9.8 ± 3.5 | 40 % |
| 20 | 20.2 ± 1.2 | 2.5 ± 0.7 | 7.0 | 100 % | $319 | 5.8 ± 2.8 | 34 % |
| 24 | 24.2 ± 1.4 | 2.6 ± 0.9 | 7.0 | 100 % | $378 | 5.1 ± 2.9 | 30 % |
| 28 | 28.4 ± 1.7 | 2.5 ± 0.9 | 7.0 | 100 % | $419 | 4.0 ± 1.9 | 27 % |
| 32 | 32.4 ± 1.8 | 2.3 ± 0.9 | 7.0 | 100 % | $456 | 3.8 ± 2.8 | 24 % |
| 36 | 36.4 ± 1.7 | 2.4 ± 0.6 | 7.0 | 100 % | $494 | 3.7 ± 2.5 | 22 % |
| 40 | 40.8 ± 1.8 | 1.9 ± 0.6 | 7.0 | 100 % | $522 | 1.7 ± 0.9 | 20 % |
| 44 | 43.9 ± 1.8 | 2.5 ± 0.6 | 7.0 | 100 % | $541 | 1.1 ± 0.5 | 19 % |
| 48 | 48.1 ± 2.0 | 2.4 ± 0.7 | 7.0 | 100 % | $559 | 1.4 ± 0.6 | 17 % |

| Over the year | |
|---|---|
| Submissions that waited for a panel | 21 % ± 3 |
| ...withdrawn after 14 days of waiting | 16 % ± 3 |
| Days from submission to final verdict | 2.1 ± 0.2 |
| Bad fixes merged per 100 paid | 0.21 ± 0.06 |
| Panels drawn at k = 1 / 3 / 5 / 7 | 2 % / 14 % / 6 % / 78 % |
| Draws whose k the caps lowered (from the largest odd number of eligible validators) | 14 % ± 3 |
| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week 6 (40 of 40 runs) / week 9 (40 of 40 runs) |
| Newcomers / qualified in the year | 53.8 ± 2.1 / 51.0 ± 2.1 |
| Days from registration to activation | 14.7 ± 1.4 |
| Failed qualification attempts | 3.6 ± 0.6 |
| Challenges / verdicts reversed / challenges still frozen at year's end | 33.6 ± 2.7 / 4.6 ± 0.8 / 1.4 ± 0.6 |
| Shadows' usage repaid from the sponsors' pool | $197 |
| An activated validator's month: fees $1.08, less overhead $0.34, slashes for outages $0.50, fixed costs $4.67, the bond's capital $1.64 | net **$-6.06** |

##### An honest network grows under the hold (40 seeds; a year; growth from one validator, one newcomer a week, 30 submissions a week; each rule beside its alternatives, same seeds)

| Rule | Runs where a small bounty reaches k ≥ 3 | First 4-week snapshot at k ≥ 3 | Days from a k = 1 verdict to payment: median a run (p90, all runs) | k = 1 verdicts held / days held | Submissions that waited / withdrawn | Newcomers qualified (of joined) / days to qualify | Sponsors' pool on shadows (on waiting submissions) | Bad fixes merged per 100 paid | Draws the caps lowered | Panels of k ≥ 3 (of 3) with one TEE type holding the majority | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Round 2's rules (the design)**: three TEE types at launch, even | 40 of 40 | week 6 ± 1 | 19.4 ± 3.6 (48.5) | 66 ± 8 % / 18.2 ± 3.0 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $197 ($67) | 0.21 ± 0.06 | 14 ± 3 % | 11.2 ± 2.9 % (77 ± 8 %) | 48.1 ± 2.0 |
| round 1's rules as a whole (`V2R1`) | 40 of 40 | week 6 ± 1 | 19.0 ± 3.6 (46.1) | 65 ± 8 % / 19.3 ± 3.3 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $197 ($66) | 0.22 ± 0.05 | 13 ± 3 % | 11.1 ± 2.8 % (77 ± 8 %) | 48.0 ± 2.1 |
| `K1_AUDITS` 1 (one audit of every k = 1 verdict) | 40 of 40 | week 6 ± 1 | 18.9 ± 3.6 (46.1) | 66 ± 7 % / 18.6 ± 3.0 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $197 ($66) | 0.22 ± 0.05 | 14 ± 3 % | 11.3 ± 2.8 % (76 ± 8 %) | 48.1 ± 2.0 |
| `K1_PENDING_MAX` 5 | 40 of 40 | week 6 ± 1 | 18.0 ± 4.1 (46.0) | 53 ± 9 % / 19.9 ± 3.4 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $197 ($68) | 0.20 ± 0.05 | 14 ± 3 % | 11.8 ± 3.1 % (79 ± 8 %) | 48.1 ± 2.0 |
| `K1_PENDING_MAX` 20 | 40 of 40 | week 6 ± 1 | 23.2 ± 3.0 (52.2) | 74 ± 6 % / 16.7 ± 2.2 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $197 ($66) | 0.20 ± 0.06 | 14 ± 3 % | 11.2 ± 2.8 % (77 ± 8 %) | 48.1 ± 2.0 |
| `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties) | 40 of 40 | week 5 ± 1 | 22.9 ± 3.5 (49.4) | 72 ± 7 % / 19.1 ± 3.4 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $198 ($67) | 0.21 ± 0.06 | 13 ± 3 % | 11.1 ± 2.8 % (76 ± 8 %) | 48.1 ± 2.0 |
| k = 1's window 14 days | 40 of 40 | week 6 ± 1 | 25.3 ± 3.6 (54.6) | 65 ± 8 % / 18.2 ± 3.0 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $198 ($67) | 0.21 ± 0.06 | 14 ± 3 % | 11.1 ± 2.9 % (75 ± 8 %) | 48.1 ± 2.0 |
| k = 1's window 30 days | 40 of 40 | week 6 ± 1 | 40.6 ± 3.6 (69.7) | 65 ± 8 % / 18.2 ± 3.0 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 1 | $198 ($68) | 0.21 ± 0.05 | 14 ± 3 % | 11.1 ± 2.9 % (75 ± 8 %) | 48.1 ± 2.0 |
| `SHADOW_PER_WAITING` 0 | 0 of 40 | week – | – (nan) | 100 ± 1 % / 0.0 ± 0.0 | 99 ± 0 % / 96 ± 0 % | 0.0 ± 0.0 (53.8) / – | $1 ($0) | 0.00 ± 0.00 | 0 ± 0 % | 0.0 ± 0.0 % (0 ± 0 %) | 1.0 ± 0.0 |
| #134's rules (v1) | 40 of 40 | week 18 ± 2 | 3.0 ± 0.0 (3.0) | 0 ± 0 % / – | 68 ± 6 % / 64 ± 6 % | 18.2 ± 5.0 (53.8) / 135 ± 21 | $88 ($0) | 1.26 ± 0.33 | 39 ± 9 % | 0.0 ± 0.0 % (0 ± 0 %) | 17.3 ± 4.6 |

Round 1's design (reports/open-validators-v2.md): k ≥ 3 in 40 of 40 runs, days to payment 19.0 ± 3.6 (46.1), waited / withdrawn 21 ± 3 % / 16 ± 3 %, the caps lowered 13 ± 3 % of draws, one TEE type holding the majority 11.1 ± 2.8 % (77 ± 8 %). The second row re-runs round 1's rules on the same seeds; the last, #134's.

#### The TEE cap and the number of TEE types (40 seeds; a year; growth from one validator; newcomers spread over the accepted types as stated; round 2's rules)

| TEE types and spread | Panels of 3 with one TEE type holding the majority | ...with one vendor (Intel: SGX and TDX) holding it | Panels of k ≥ 3 with one type's majority | Panels drawn at k = 3 | Draws the caps lowered | Submissions that waited / withdrawn | Runs reaching k ≥ 3 / first week | Bad fixes merged per 100 paid | Round 1 (v2) |
|---|---|---|---|---|---|---|---|---|---|
| **Three types (TDX, SEV-SNP, Nitro), even: the cap from k = 5 (the design at launch)** | 77 ± 8 % | 77 ± 8 % | 11.2 ± 2.9 % | 14 ± 3 % | 14 ± 3 % | 21 ± 3 % / 16 ± 3 % | 40 of 40 / week 6 ± 1 | 0.21 ± 0.06 | 11.1 ± 2.8 % (77 ± 8 %); lowered 13 ± 3 % |
| Three types, skewed (TDX 40 %, SEV-SNP 40 %, Nitro 20 %): the cap from k = 5 | 73 ± 8 % | 73 ± 8 % | 9.2 ± 2.2 % | 12 ± 2 % | 13 ± 2 % | 18 ± 2 % / 14 ± 2 % | 40 of 40 / week 5 ± 1 | 0.18 ± 0.05 | – |
| Five types (adding SGX and IBM SE), even: **the cap from k = 3** | 0 ± 0 % | 21 ± 11 % | 0.0 ± 0.0 % | 5 ± 1 % | 6 ± 1 % | 22 ± 3 % / 17 ± 3 % | 40 of 40 / week 6 ± 1 | 0.14 ± 0.04 | five placeholder types from k = 3: lowered 6 ± 1 % |
| Five types, skewed (TDX 35 %, SEV-SNP 35 %, Nitro 15 %, SGX 10 %, IBM SE 5 %): the cap from k = 3 | 0 ± 0 % | 17 ± 10 % | 0.0 ± 0.0 % | 4 ± 1 % | 7 ± 2 % | 22 ± 2 % / 17 ± 2 % | 40 of 40 / week 5 ± 1 | 0.10 ± 0.03 | – |
| Three types, even, the cap from k = 3 (#134's rule) | 0 ± 0 % | 0 ± 0 % | 0.0 ± 0.0 % | 4 ± 2 % | 8 ± 2 % | 27 ± 4 % / 21 ± 4 % | 40 of 40 / week 6 ± 1 | 0.14 ± 0.04 | – |
| Five types, even, the cap from k = 5 (round 1's rule) | 55 ± 10 % | 64 ± 10 % | 5.7 ± 2.2 % | 10 ± 2 % | 8 ± 2 % | 19 ± 2 % / 14 ± 2 % | 40 of 40 / week 6 ± 1 | 0.17 ± 0.05 | – |

The cap's start follows the number of accepted types (`TEE_CAP_K3_TYPES` 5): from k = 3 with five, from k = 5 with three. One vendor: Intel makes both SGX and TDX, which count as two types (owner, 2026-11-03), so with five types two Intel validators may hold a panel of 3. The skewed spreads are assumptions.

### The attackers

#### Each attacker against its honest twin (40 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Doesn't gain (D17, round 2) | Loses (round 1's criterion) | Attacker's return | Twin's return | Round 1 (v2) | What it got |
|---|---|---|---|---|---|---|---|
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families | -21,535 ± 2,510 | yes | loses | -22,679 | -1,144 | -21,601 ± 2,530 | 16.0 bad fixes paid of 96; a majority on 8 % of its own panels; 17.7 false verdicts proven |
| Sybil: 10 of 30 validators, one host, TEE type and family | -17,969 ± 1,752 | yes | loses | -19,123 | -1,154 | -17,936 ± 1,753 | 5.0 bad fixes paid of 96; a majority on 0 % of its own panels; 14.0 false verdicts proven |
| Seed grinder (v3's seed: a later block) | -272 ± 48 | yes | loses | -332 | -59 | -250 ± 46 | 0.6 bad fixes paid of 24 attempts; 5.5 false verdicts proven, 0.0 challenges still frozen; 51.0 newcomers qualified (twin: 51.0) |
| Seed grinder (counterfactual: the seed fixed at the seal) | -247 ± 35 | yes | loses | -308 | -60 | -240 ± 36 | 0.1 bad fixes paid of 7 attempts; 7.0 false verdicts proven, 0.0 challenges still frozen; 51.1 newcomers qualified (twin: 51.1) |
| Fee farmer (10 idle nodes at the bond floor; twin: one node) | -545 ± 3 | yes | loses | -605 | -60 | -535 ± 1 | 44.1 counted checks a node |
| Sybil, spread, `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -3,054 ± 525 | yes | loses | -4,198 | -1,144 | -3,043 ± 532 | 16.1 bad fixes paid of 96; a majority on 8 % of its own panels; 17.8 false verdicts proven |
| Seed grinder, `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -90 ± 14 | yes | loses | -149 | -59 | -70 ± 14 | 0.6 bad fixes paid of 24 attempts; 5.5 false verdicts proven, 0.0 challenges still frozen; 51.0 newcomers qualified (twin: 51.0) |

#### The colluding genesis under the hold, with two audits (40 seeds; a year; growth from one validator; the genesis, bonded $100, passes its accomplice's bad fixes at k = 1; against its honest twin)

| Rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Bad fixes passed / reversed / paid / still pending | Reversed before payment, pooled (± 2 SE) | ...of those it judged alone | Audits per passed bad fix | Its verdicts held | Challenges still frozen | Newcomers qualified (twin's) | Slashed | Round 1 (v2) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Round 2's rules (the design): two audits of every k = 1 verdict**, 5 bad fixes a week | -247 ± 41 | yes | loses | 5.2 / 4.9 / 0.3 / 0.0 | 93.3 % ± 3.9 % | 98.4 % ± 1.8 % | 1.75 | 6.6 | 0.0 | 50.9 (50.9) | $240 | -221 ± 38 |
| `K1_AUDITS` 1 (one audit of every k = 1 verdict) | -224 ± 41 | yes | loses | 5.2 / 4.5 / 0.7 / 0.0 | 87.1 % ± 5.1 % | 92.0 % ± 4.0 % | 0.97 | 6.6 | 0.0 | 50.9 (50.9) | $230 | – |
| round 1's rules as a whole (`V2R1`) | -221 ± 38 | yes | loses | 5.2 / 4.5 / 0.7 / 0.0 | 86.6 % ± 5.1 % | 92.0 % ± 4.0 % | 0.96 | 6.4 | 0.0 | 50.9 (50.9) | $225 | – |
| `K1_PENDING_MAX` 5 | -207 ± 40 | yes | loses | 2.9 / 2.5 / 0.3 / 0.0 | 88.7 % ± 6.7 % | 98.9 % ± 2.3 % | 1.69 | 3.2 | 0.0 | 50.9 (50.9) | $200 | -185 ± 38 |
| `K1_PENDING_MAX` 20 | -312 ± 54 | yes | loses | 9.8 / 9.4 / 0.3 / 0.0 | 96.9 % ± 1.9 % | 98.9 % ± 1.0 % | 1.74 | 10.8 | 0.0 | 50.9 (50.9) | $300 | -299 ± 51 |
| `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties) | -102 ± 33 | yes | loses | 0.9 / 0.7 / 0.2 / 0.0 | 75.0 % ± 17.0 % | 100.0 % ± 0.0 % | 1.36 | 0.8 | 0.0 | 50.9 (50.9) | $97 | -97 ± 33 |
| k = 1's window 14 days | -264 ± 42 | yes | loses | 5.2 / 5.0 / 0.3 / 0.0 | 94.7 % ± 3.8 % | 99.5 % ± 1.1 % | 1.75 | 6.6 | 0.0 | 50.9 (50.9) | $252 | -243 ± 36 |
| k = 1's window 30 days | -251 ± 40 | yes | loses | 5.2 / 5.0 / 0.2 / 0.0 | 95.2 % ± 3.7 % | 99.5 % ± 1.1 % | 1.75 | 6.6 | 0.0 | 50.9 (50.9) | $240 | -247 ± 39 |
| `SHADOW_PER_WAITING` 0 | -130 ± 2 | yes | loses | 4.7 / 0.0 / 0.0 / 4.7 | – ± – | – ± – | 0.00 | 4.7 | 0.0 | 0.0 (0.0) | $0 | -130 ± 2 |
| `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -85 ± 10 | yes | loses | 5.2 / 4.9 / 0.3 / 0.0 | 93.3 % ± 3.9 % | 98.4 % ± 1.8 % | 1.75 | 6.6 | 0.0 | 50.9 (50.9) | $85 | -67 ± 11 |
| Round 2's rules, 1 bad fix a week | -113 ± 34 | yes | loses | 1.6 / 1.6 / 0.0 / 0.0 | 100.0 % ± 0.0 % | 100.0 % ± 0.0 % | 1.74 | 2.0 | 0.0 | 50.9 (50.9) | $107 | -103 ± 30 |
| #134's rules (v1), 5 bad fixes a week | +2,920 ± 456 | **no: it gains** | **wins** | 174.9 / 31.1 / 90.2 / 53.7 | 25.6 % ± 7.3 % | 25.7 % ± 7.4 % | 0.00 | 0.0 | 52.8 | 3.1 (13.3) | $134 | +2,920 ± 456 |

Round 1's design (one audit of every k = 1 verdict): -221 ± 38 $, 86.6 % ± 5.1 % reversed before payment. D13 and D17 estimate about 96 % with two audits. "Reversed before payment" counts the passed bad fixes that reached an outcome by the year's end, as round 1 did: those its accomplice submitted while k was 1, whoever judged them (an honest lone judge's mistake, or a panel of 3 drawn later). "...of those it judged alone" counts only its own k = 1 verdicts. "Still pending" ones (held or in their window at the year's end) are neither.

#### A bribed silent judge and a bribed withholder (40 seeds; a year; a grown network of 12 honest validators; bribed 5 % of the bounty on 10 % of its draws unless stated)

| Judge and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Bribed misses / suspended | Bribe a miss | Slashed | k ever shrank | Round 1 (v2) |
|---|---|---|---|---|---|---|---|---|
| **Silent (never seals): `SILENCE_SLASH` $5 (the design)** | -14 ± 9 | yes | loses | 63.9 / 8.4 | $5.09 | $333.88 | never | +317 ± 13 |
| **Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5 (the design)** | -15 ± 9 | yes | loses | 63.9 / 8.4 | $5.09 | $333.88 | never | +249 ± 12 |
| Silent: both flat slashes at $1 | +250 ± 12 | **no: it gains** | **wins** | 63.9 / 8.4 | $5.09 | $66.78 | never | +250 ± 12 |
| Seals, then withholds: both flat slashes at $1 | +249 ± 12 | **no: it gains** | **wins** | 63.9 / 8.4 | $5.09 | $66.78 | never | +249 ± 12 |
| Silent: silence unslashed | +317 ± 13 | **no: it gains** | **wins** | 63.9 / 8.4 | $5.10 | $0.00 | never | +317 ± 13 |
| Silent, the design, bribed 10 % of the bounty (about $9 a silence; sensitivity) | +311 ± 21 | **no: it gains** | **wins** | 63.9 / 8.4 | $10.18 | $333.88 | never | – |
| Seals, then withholds, the design, bribed 10 % of the bounty (sensitivity) | +310 ± 21 | **no: it gains** | **wins** | 63.9 / 8.4 | $10.18 | $333.88 | never | – |
| Silent, #134's rules (5 % of the bond a miss) | -3,813 ± 123 | yes | loses | 64.1 / 8.4 | $5.10 | $4,171.29 | never | -3,813 ± 123 |

Round 1's design: the silent judge unslashed (+317 ± 13 $) and the withholder at $1 (+249 ± 12 $). Round 1's switch set both at $1 (silent +250 ± 12 $).

#### An early coalition (40 seeds; a year; growth from one validator; the coalition registers its validators at the start and submits an adding ADR worth $1,000 to it each week, with its deposit; its validators pass them)

| Coalition and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | ADRs submitted / expired / judged / passed | Deposits forfeited ($ a run) | Passed below its rule's threshold (all runs) | Passed while fewer than 21 were eligible (all runs) | First ADR judged (day; 365: none) | Derived (D7) | Round 1 (v2) |
|---|---|---|---|---|---|---|---|---|---|---|
| 5 early validators: **21 for adding ADRs, a $15 deposit (the design)** | -280 ± 147 | yes | loses | 52 / 16.4 / 36.0 / 0.33 | $506 | 0 | 0 | 122 | about −$255 ± 152 | +622 ± 260 |
| 5 early: one threshold for every ADR: 14, $15 | -58 ± 259 | **no: up to +200** | not significant | 52 / 9.7 / 42.7 / 0.65 | $602 | 0 | 13 | 75 | about −$8 ± 260 | +622 ± 260 |
| 5 early: one threshold for every ADR: 28, $15 | -283 ± 133 | yes | loses | 52 / 22.4 / 29.9 / 0.23 | $417 | 0 | 0 | 166 | about −$258 ± 138 | +187 ± 138 |
| 5 early: 21, `ADR_DEPOSIT` $0 | +255 ± 149 | **no: it gains** | **wins** | 52 / 16.4 / 36.0 / 0.33 | $0 | 0 | 0 | 122 | – | +280 ± 152 |
| 5 early: 21, `ADR_DEPOSIT` $25 | -636 ± 149 | yes | loses | 52 / 16.4 / 36.0 / 0.33 | $844 | 0 | 0 | 122 | – | – |
| 5 early: round 1's rules (14 for every ADR, no deposit) | +622 ± 260 | **no: it gains** | **wins** | 52 / 9.7 / 42.7 / 0.70 | $0 | 0 | 14 | 75 | – | +622 ± 260 |
| 5 early: #134's rule (`K_MAX` eligible, ADRs wait) | +5,196 ± 2,178 | **no: it gains** | **wins** | 52 / 0.0 / 45.4 / 5.28 | $0 | 0 | 209 | 237 | – | +5,196 ± 2,178 |
| 3 early validators: **21 for adding ADRs, a $15 deposit (the design)** | -431 ± 145 | yes | loses | 52 / 18.0 / 34.3 / 0.15 | $484 | 0 | 0 | 135 | about −$429 ± 135 | +148 ± 182 |
| 3 early: one threshold for every ADR: 14, $15 | -464 ± 188 | yes | loses | 52 / 11.3 / 41.0 / 0.23 | $584 | 0 | 3 | 86 | – | +148 ± 182 |
| 3 early: one threshold for every ADR: 28, $15 | -345 ± 140 | yes | loses | 52 / 24.9 / 27.4 / 0.12 | $381 | 0 | 0 | 180 | – | +65 ± 128 |
| 3 early: 21, `ADR_DEPOSIT` $0 | +81 ± 135 | **no: it gains** | not significant | 52 / 18.0 / 34.3 / 0.15 | $0 | 0 | 0 | 135 | – | +82 ± 135 |
| 3 early: 21, `ADR_DEPOSIT` $25 | -773 ± 155 | yes | loses | 52 / 18.0 / 34.3 / 0.15 | $807 | 0 | 0 | 135 | – | – |
| 3 early: round 1's rules (14 for every ADR, no deposit) | +148 ± 182 | **no: it gains** | not significant | 52 / 11.3 / 41.0 / 0.23 | $0 | 0 | 3 | 86 | – | +148 ± 182 |
| 3 early: #134's rule (`K_MAX` eligible, ADRs wait) | +819 ± 450 | **no: it gains** | **wins** | 52 / 0.0 / 45.8 / 0.90 | $0 | 0 | 34 | 189 | – | +819 ± 450 |
| 5 early, sending escalated fixes to issues they fund themselves: **21, a $15 deposit to the sponsors' pool (the rule)** | -280 ± 147 | yes | loses | 52 / 16.4 / 36.0 / 0.33 | $506 | 0 | 0 | 122 | – | – |
| 5 early, the same escalated fixes: an escalated fix's forfeit to its issue's funder (rejected by the owner) | +226 ± 151 | **no: it gains** | **wins** | 52 / 16.4 / 36.0 / 0.33 | $506 | 0 | 0 | 122 | – | – |

Round 1's numbers: the same coalition under round 1's design (14 for every ADR, no deposit) for the design row, and round 1's measured switch for the others ("21, $0" is round 1's 21). "Derived": D7's hand estimate from round 1's table, assuming the coalition keeps submitting. An escalated fix's issue is funded by the coalition itself, so a forfeit sent to the funder comes back to it.

#### A coalition of removals (40 seeds; a year; growth from one validator; 5 validators registered at the start on the other types submit each week an ADR removing the TEE type most other validators use, with its deposit, until it is removed; their validators pass them)

| Coalition and rule | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Removals submitted / expired / judged / passed | Deposits forfeited ($ a run) | Removals taking effect (runs) | Validators that stopped being drawn (a run) | Passed while fewer than 14 were eligible (all runs) | First removal judged (day) | Submissions that waited |
|---|---|---|---|---|---|---|---|---|---|---|
| **5 early validators, removals from 14 with a $15 deposit (the design)**; three types, even; they remove Nitro, the genesis's type | -456 ± 103 | yes | loses | 38 / 10.2 / 27.4 / 0.45 | $401 | 18 of 40 | 3.2 | 0 | 72 | 13 % (twin 12 %) |
| the same, three types skewed; they remove TDX (40 % of newcomers) | -505 ± 97 | yes | loses | 40 / 9.8 / 30.2 / 0.38 | $445 | 15 of 40 | 2.5 | 0 | 72 | 11 % (twin 10 %) |
| the same as the first, `ADR_DEPOSIT` $0 | -52 ± 11 | yes | loses | 38 / 10.2 / 27.4 / 0.45 | $0 | 18 of 40 | 3.2 | 0 | 72 | 13 % (twin 12 %) |
| the same as the first, a passed removal worth $1,000 to it (sensitivity) | -6 ± 258 | **no: up to +252** | not significant | 38 / 10.2 / 27.4 / 0.45 | $401 | 18 of 40 | 3.2 | 0 | 72 | 13 % (twin 12 %) |

A removal takes effect `REMOVAL_WINDOW` (48 h) after it passes: the type's validators stop being drawn and keep their bonds, and newcomers of that type are refused. Assumption: none of them registers again with another type within the year. The last accepted type can never be removed. The first row counts only the fees the coalition's validators win from the removed ones; the last values a removal at $1,000, as the adding coalition values an ADR.

#### The sybil's majorities by its share (40 seeds; 20 honest validators, newcomers at half a validator a week; its bad fixes at 2 a week)

| Sybil validators (share of the eligible) | Spread | Majority of its own panels | Majority of any panel with k ≥ 3 | Bad fixes paid | False verdicts proven |
|---|---|---|---|---|---|
| 3 (12 %) | spread | 0.0 % | 0.00 % | 1.8 | 7.8 |
| 3 (12 %) | one host | 0.0 % | 0.00 % | 1.2 | 7.0 |
| 6 (22 %) | spread | 1.2 % | 1.40 % | 6.3 | 13.7 |
| 6 (22 %) | one host | 0.0 % | 0.00 % | 2.8 | 10.9 |
| 10 (32 %) | spread | 8.0 % | 7.51 % | 16.0 | 17.7 |
| 10 (32 %) | one host | 0.0 % | 0.00 % | 5.0 | 14.0 |
| 20 (49 %) | spread | 30.4 % | 32.39 % | 39.8 | 16.3 |
| 20 (49 %) | one host | 0.0 % | 0.00 % | 9.2 | 15.4 |

#### The watcher's dilemma (40 seeds; 26 weeks; one lazy cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 28.6 | 0 % | 4.8 ± 0.7 | pays | $0.0000 |
| none | 1 % | 28.6 | 1 % | -283.4 ± 215.1 | loses | $0.0017 |
| none | 2 % | 28.6 | 2 % | -860.0 ± 360.0 | loses | $0.0034 |
| none | 5 % | 28.5 | 5 % | -1,884.9 ± 510.7 | loses | $0.0089 |
| none | 10 % | 28.4 | 11 % | -3,838.7 ± 587.4 | loses | $0.0179 |
| none | 20 % | 28.4 | 19 % | -6,753.4 ± 889.4 | loses | $0.0362 |
| yes | 0 % | 28.5 | 6 % | -2,205.1 ± 502.1 | loses | $0.0000 |
| yes | 1 % | 28.4 | 7 % | -2,461.4 ± 497.1 | loses | $0.0017 |
| yes | 2 % | 28.4 | 8 % | -3,005.9 ± 612.2 | loses | $0.0034 |
| yes | 5 % | 28.4 | 11 % | -4,030.9 ± 759.4 | loses | $0.0089 |
| yes | 10 % | 28.3 | 16 % | -5,856.6 ± 772.3 | loses | $0.0179 |
| yes | 20 % | 28.2 | 25 % | -8,707.2 ± 1,070.6 | loses | $0.0362 |

#### The watcher's dilemma (40 seeds; 26 weeks; one bribed cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 6.7 | 0 % | 38.0 ± 4.0 | pays | $0.0000 |
| none | 1 % | 6.7 | 1 % | -26.0 ± 89.4 | not significant | $0.0017 |
| none | 2 % | 6.7 | 3 % | -186.2 ± 180.7 | loses | $0.0034 |
| none | 5 % | 6.7 | 5 % | -346.3 ± 228.1 | loses | $0.0089 |
| none | 10 % | 6.7 | 11 % | -858.8 ± 319.8 | loses | $0.0179 |
| none | 20 % | 6.7 | 19 % | -1,563.5 ± 491.0 | loses | $0.0362 |
| yes | 0 % | 6.7 | 6 % | -506.4 ± 239.7 | loses | $0.0000 |
| yes | 1 % | 6.7 | 7 % | -570.4 ± 241.4 | loses | $0.0017 |
| yes | 2 % | 6.7 | 9 % | -730.6 ± 271.0 | loses | $0.0034 |
| yes | 5 % | 6.7 | 11 % | -890.7 ± 303.0 | loses | $0.0089 |
| yes | 10 % | 6.7 | 17 % | -1,371.3 ± 351.7 | loses | $0.0179 |
| yes | 20 % | 6.7 | 25 % | -2,076.0 ± 497.4 | loses | $0.0362 |

### The k table compared

#### The k table compared (40 seeds; a year; 30 submissions a week; every validator at level A; the same seeds for both rules)

| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth from one validator | k table (v3) | 2.1 ± 0.6 (0.21 ± 0.06) | 966 ± 38 | 2.1 ± 0.2 | 21 ± 3 % | 16 ± 3 % | $1.78 ± 0.03 | $-6.05 ± 0.09 | 48.1 ± 2.0 |
| Growth from one validator | fixed k = 3, bounties to $625 | 6.3 ± 0.9 (0.65 ± 0.09) | 948 ± 40 | 2.3 ± 0.2 | 24 ± 4 % | 17 ± 3 % | $1.04 ± 0.03 | $-6.23 ± 0.09 | 47.7 ± 1.9 |
| Small: the genesis and 4 active | k table (v3) | 1.0 ± 0.3 (0.09 ± 0.03) | 1,158 ± 10 | 1.2 ± 0.1 | 0 ± 0 % | 0 ± 0 % | $1.80 ± 0.02 | $-6.34 ± 0.08 | 51.9 ± 2.0 |
| Small: the genesis and 4 active | fixed k = 3, bounties to $625 | 7.9 ± 0.8 (0.69 ± 0.07) | 1,141 ± 10 | 1.8 ± 0.2 | 1 ± 0 % | 0 ± 0 % | $0.95 ± 0.01 | $-6.49 ± 0.07 | 51.6 ± 2.0 |
| Grown: the genesis and 20 active | k table (v3) | 0.9 ± 0.3 (0.07 ± 0.03) | 1,160 ± 10 | 0.4 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $1.81 ± 0.01 | $-7.54 ± 0.08 | 46.1 ± 1.6 |
| Grown: the genesis and 20 active | fixed k = 3, bounties to $625 | 7.8 ± 1.0 (0.68 ± 0.09) | 1,143 ± 10 | 1.1 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $0.89 ± 0.01 | $-7.72 ± 0.08 | 46.1 ± 1.6 |

Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with three validators, a 24-hour window and a challenge panel of 5. "–": nothing to measure (no verdict became final, or nothing was paid).

### Proof levels

#### Panels by proof level (40 seeds; a year; 30 submissions a week)

| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C | Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth, all level A | 21 % ± 3 | 16 % ± 3 | 0 % ± 0 | 1,299 ± 52 | 100 % / 0 % / 0 % | 2.1 / – / – | 0.21 ± 0.06 | $559 | 48.1 ± 2.0 |
| Growth at launch: genesis A, newcomers ⅓ A, ⅓ B, ⅓ C, **the C third refused (level C off)** | 31 % ± 4 | 26 % ± 4 | 2 % ± 1 | 1,148 ± 66 | 70 % / 30 % / 0 % | 3.3 / 2.2 / – | 0.18 ± 0.06 | $488 | 32.8 ± 1.6 |
| Growth at launch, the same with 10 % hidden-test bounties | 31 % ± 4 | 26 % ± 4 | 2 % ± 1 | 1,148 ± 66 | 70 % / 30 % / 0 % | 3.3 / 2.1 / – | 0.18 ± 0.05 | $488 | 32.8 ± 1.6 |
| Grown, after C is switched on by ADR: 21 active, ⅓ A, ⅓ B, ⅓ C | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,540 ± 13 | 20 % / 64 % / 16 % | 0.6 / 0.6 / 1.1 | 0.08 ± 0.03 | $625 | 46.2 ± 1.6 |
| Grown, after C is switched on by ADR: the same with 10 % hidden-test bounties | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,540 ± 13 | 24 % / 62 % / 14 % | 0.6 / 0.7 / 1.1 | 0.08 ± 0.03 | $625 | 46.1 ± 1.6 |
| Grown, after C is switched on by ADR: the genesis at A, 20 active at C | 4 % ± 0 | 4 % ± 0 | 4 % ± 0 | 1,494 ± 12 | 0 % / 0 % / 100 % | – / – / 1.1 | 0.01 ± 0.01 | $250 | 46.2 ± 1.6 |
| Growth, ordinary PCs only (genesis at C, even with C accepted) | refused at deployment: a level C genesis validator; the genesis must be at level A or B | | | | | | | | |

| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, replacement or shadow; all runs) |
|---|---|---|---|
| Growth at launch, the same with 10 % hidden-test bounties | 31 % ± 4 | 25 % ± 4 | 0 |
| Grown, after C is switched on by ADR: the same with 10 % hidden-test bounties | 1 % ± 0 | 0 % ± 0 | 0 |

#### Each proof-level attacker against its honest twin (40 seeds; a year; returns in $)

| Attacker | Return − twin's ($, ± 2 SE) | Doesn't gain (D17, round 2) | Loses (round 1's criterion) | Attacker's return | Twin's return | Round 1 (v2) | What it got |
|---|---|---|---|---|---|---|---|
| Test liar: the genesis at C, 5 bad fixes a week (even with C accepted) | refused at deployment | – | – | – | – | – | a level C genesis validator; the genesis must be at level A or B |
| Test liar, after C is switched on by ADR: 1 of 15, every other validator at C but the genesis (A); 2 bad fixes a week | -4,809 ± 505 | yes | loses | -4,882 | -73 | -4,810 ± 505 | 0.1 bad fixes paid of 101 (largest $12); 27.9 lies: 11.5 challenged, 8.8 proven by re-runs (32 %), 0.8 reversed, 0.0 still frozen at year's end; slashed $4436 |
| Test liar: the same, `C_LIMIT_X` 0.5 (level C's limits halved) | -4,310 ± 484 | yes | loses | -4,385 | -75 | -4,310 ± 484 | 0.1 bad fixes paid of 101 (largest $13); 26.6 lies: 10.7 challenged, 7.9 proven by re-runs (30 %), 0.6 reversed, 0.0 still frozen at year's end; slashed $3958 |
| Answer shopper: the genesis at C (even with C accepted) | refused at deployment | – | – | – | – | – | a level C genesis validator; the genesis must be at level A or B |
| **Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes)** | -13 ± 1 | yes | loses | -263 | -250 | -13 ± 1 | 10.1 verdicts flipped of 31.1 shopped (101 extra calls); outweighed by the other judges 9.9, reversed 0.1, paid 0.0; bad fixes paid 0.0 of 101 (twin 0.0); agreement with final outcomes 88.4 % (twin 90.4 %) |
| Answer shopper: the same at 3 in 10 (the trust point; twin: calls once, same fixes) | +174 ± 46 | **no: it gains** | **wins** | 457 | 283 | +174 ± 46 | 17.4 verdicts flipped of 31.1 shopped (68 extra calls); outweighed by the other judges 12.8, reversed 3.3, paid 1.5; bad fixes paid 7.1 of 101 (twin 5.4); agreement with final outcomes 86.2 % (twin 89.3 %) |
| Answer shopper, after C is switched on by ADR: the same at #125's measured room, +3.5 points with 5 calls (a borderline rate of 0.9 % in this model; one 7B open model on one setup, reports/determinism-v1.md) | -16 ± 1 | yes | loses | -266 | -249 | – | 0.9 verdicts flipped of 31.2 shopped (125 extra calls); outweighed by the other judges 0.9, reversed 0.0, paid 0.0; bad fixes paid 0.0 of 101 (twin 0.0); agreement with final outcomes 90.7 % (twin 90.9 %) |
| Answer shopper: 3 in 10 (twin: no fixes) | +530 ± 107 | **no: it gains** | **wins** | 457 | -73 | +531 ± 107 | 17.4 verdicts flipped of 31.1 shopped (68 extra calls); outweighed by the other judges 12.8, reversed 3.3, paid 1.5; bad fixes paid 7.1 of 101 (twin 0.0); agreement with final outcomes 86.2 % (twin 90.2 %) |
| Answer shopper: 1 in 10, `C_LIMIT_X` 0.5 (level C's limits halved) | -12 ± 1 | yes | loses | -264 | -252 | -12 ± 1 | 9.5 verdicts flipped of 29.4 shopped (96 extra calls); outweighed by the other judges 9.3, reversed 0.2, paid 0.0; bad fixes paid 0.0 of 101 (twin 0.0); agreement with final outcomes 87.5 % (twin 90.0 %) |
| Answer shopper: 3 in 10, `C_LIMIT_X` 0.5 (level C's limits halved) | +157 ± 47 | **no: it gains** | **wins** | 399 | 242 | +157 ± 47 | 16.6 verdicts flipped of 29.6 shopped (65 extra calls); outweighed by the other judges 12.3, reversed 2.7, paid 1.7; bad fixes paid 7.8 of 101 (twin 5.9); agreement with final outcomes 84.8 % (twin 88.6 %) |
| Chip breaker at launch: the genesis at B ($25 at k = 1, 336 h), forging on half its bad-fix draws, $1,000 device | -1,500 ± 57 | yes | loses | -1,559 | -59 | -1,520 ± 64 | 20.4 forged of 103 draws (20 %); own bad fixes paid 0.5 of 25, bribed ones 0.4 (bribes $8); largest bounty paid $18; 11.1 challenged, 55 % of forgeries proven by re-runs, 0.0 still frozen; slashed $480 |
| Chip breaker at launch: the same, a $50 device | -550 ± 57 | yes | loses | -609 | -59 | -570 ± 64 | 20.4 forged of 103 draws (20 %); own bad fixes paid 0.5 of 25, bribed ones 0.4 (bribes $8); largest bounty paid $18; 11.1 challenged, 55 % of forgeries proven by re-runs, 0.0 still frozen; slashed $480 |
| Chip breaker at launch: 1 of a grown network (⅓ A, ⅓ B; the ⅓ at C refused), a $50 device | -14,166 ± 1,492 | yes | loses | -14,275 | -109 | -13,873 ± 1,579 | 112.6 forged of 711 draws (16 %); own bad fixes paid 0.9 of 101, bribed ones 1.2 (bribes $65); largest bounty paid $134; 7.3 challenged, 13 % of forgeries proven by re-runs, 1.6 still frozen; slashed $13452 |
| Chip breaker at launch: the same, forging on every bad-fix draw | -22,003 ± 2,142 | yes | loses | -22,112 | -109 | -21,352 ± 2,153 | 187.8 forged of 706 draws (27 %); own bad fixes paid 0.9 of 101, bribed ones 2.4 (bribes $133); largest bounty paid $175; 7.3 challenged, 13 % of forgeries proven by re-runs, 1.6 still frozen; slashed $20981 |
| Chip breaker, after C is switched on by ADR: 1 of 15 (⅓ A, ⅓ B, ⅓ C), a $50 device | -19,830 ± 1,644 | yes | loses | -19,942 | -111 | -19,766 ± 1,636 | 79.5 forged of 491 draws (16 %); own bad fixes paid 0.5 of 101, bribed ones 0.8 (bribes $38); largest bounty paid $80; 6.9 challenged, 19 % of forgeries proven by re-runs, 0.0 still frozen; slashed $18760 |

#### Level C at launch: off (owner decision 2026-11-03; the default) against the merged design, C accepted from genesis (40 seeds; a year)

| Network | Newcomers joined (refused at C) | Qualified / days | Runs reaching k ≥ 3 / first week | Submissions that waited / withdrawn | Days from a k = 1 verdict to payment (median a run) | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|
| Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C: **level C off at launch (the default)**, the C third refused | 35.7 (18.1) | 34.5 ± 1.7 / 12 ± 1 | 40 of 40 / week 7 ± 1 | 31 ± 4 % / 26 ± 4 % | 24.5 ± 5.2 | 0.18 ± 0.06 | $497 | 32.8 ± 1.6 |
| Growth, the same: **level C accepted from genesis (the merged design)** | 53.8 (0.0) | 51.1 ± 2.1 / 14 ± 1 | 40 of 40 / week 6 ± 1 | 22 ± 3 % / 17 ± 3 % | 23.9 ± 4.1 | 0.11 ± 0.04 | $447 | 48.1 ± 2.1 |
| Grown: 21 validators ⅓ A, ⅓ B, ⅓ C: **level C off** (the 7 at C never registered) | 18.3 (15.8) | 18.0 ± 1.2 / 7 ± 0 | 40 of 40 / week 0 ± 0 | 1 ± 0 % / 0 ± 0 % | – | 0.08 ± 0.02 | $625 | 30.9 ± 1.3 |
| Grown: the same: **level C accepted** | 27.4 (0.0) | 27.1 ± 1.7 / 9 ± 1 | 40 of 40 / week 0 ± 0 | 1 ± 0 % / 1 ± 0 % | – | 0.08 ± 0.03 | $625 | 46.2 ± 1.6 |

| Attacker | Level C off at launch (the default): return − twin's ($) | | Level C accepted (from genesis, or after the ADR for the grown network's rows): return − twin's ($) | |
|---|---|---|---|---|
| Colluding genesis (A, $100), newcomers ⅓ each | -267 ± 39 | loses | -270 ± 46 | loses |
| Chip breaker: the genesis at B, $50 device, newcomers ⅓ each | -550 ± 57 | loses | -529 ± 60 | loses |
| Test liar: 1 of 15 at C | refused: it can't register | – | -4,809 ± 505 | loses |
| Answer shopper: 1 of 15 at C, 1 in 10 | refused: it can't register | – | -13 ± 1 | loses |
| Answer shopper: 1 of 15 at C, 3 in 10 | refused: it can't register | – | +174 ± 46 | **wins** |

### Market pricing

#### The fee finds the validators' cost (40 seeds; a year; 20 honest validators and the genesis at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the ceiling unless stated)

| Variant | Fee at week 4 / 13 / 26 / 52 | Fee over the last 13 weeks | Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | Runs collapsed (< 3 active) | Honest validator's month |
|---|---|---|---|---|---|---|---|---|---|
| **Round 2's rules (the design): every wait counts, once** | $0.167 / $0.203 / $0.208 / $0.214 | $0.212 ± 0.006 | $0.037 ± 0.000 | $0.177 ± 0.006 | 18.6 ± 0.6 | 4 % ± 0 | 22 % ± 1 | 0 of 40 | $-1.43 ± 0.22 |
| waits a floor-bond newcomer could end (round 1's signal) | $0.127 / $0.056 / $0.059 / $0.097 | $0.083 ± 0.015 | $0.037 ± 0.000 | $1.057 ± 1.910 | 1.3 ± 0.4 | 17 % ± 1 | 96 % ± 5 | 38 of 40 | $-9.25 ± 1.05 |
| waits a newcomer of any bond could end | $0.158 / $0.168 / $0.158 / $0.142 | $0.149 ± 0.013 | $0.037 ± 0.000 | $0.142 ± 0.011 | 11.6 ± 1.6 | 4 % ± 2 | 23 % ± 8 | 4 of 40 | $-2.90 ± 0.80 |
| `IDLE_HIGH` 30 % | $0.135 / $0.205 / $0.200 / $0.202 | $0.200 ± 0.010 | $0.037 ± 0.000 | $0.158 ± 0.006 | 13.1 ± 1.9 | 21 % ± 11 | 32 % ± 10 | 7 of 40 | $-3.34 ± 1.10 |
| `IDLE_HIGH` 50 % | $0.213 / $0.219 / $0.230 / $0.234 | $0.232 ± 0.004 | $0.037 ± 0.000 | $0.197 ± 0.006 | 21.1 ± 0.6 | 4 % ± 0 | 27 % ± 1 | 0 of 40 | $-0.83 ± 0.19 |
| idling over 7 days (`IDLE_WINDOW_DAYS` 7) | $0.247 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.037 ± 0.000 | $0.215 ± 0.005 | 23.8 ± 0.4 | 4 % ± 0 | 0 % ± 0 | 0 of 40 | $-0.63 ± 0.16 |
| `FEE_STEP_UP` 10 % | $0.180 / $0.220 / $0.230 / $0.230 | $0.228 ± 0.004 | $0.037 ± 0.000 | $0.188 ± 0.006 | 20.1 ± 0.6 | 4 % ± 0 | 25 % ± 1 | 0 of 40 | $-1.09 ± 0.22 |
| the design, 100 submissions a week | $0.249 / $0.249 / $0.245 / $0.202 | $0.213 ± 0.006 | $0.037 ± 0.000 | $0.172 ± 0.005 | 59.9 ± 1.6 | 0 % ± 0 | 20 % ± 1 | 0 of 40 | $4.77 ± 0.31 |
| the design, starting at v2's $0.05 | $0.039 / $0.221 / $0.245 / $0.246 | $0.246 ± 0.004 | $0.037 ± 0.000 | $0.177 ± 0.009 | 3.3 ± 1.9 | 87 % ± 10 | 90 % ± 8 | 35 of 40 | $-13.09 ± 1.71 |
| round 1's rules (`V2R1`) | $0.127 / $0.070 / $0.054 / $0.055 | $0.050 ± 0.009 | $0.012 ± 0.000 | $0.623 ± 0.635 | 1.9 ± 0.7 | 15 % ± 2 | 88 % ± 9 | 33 of 40 | $-6.81 ± 0.99 |
| #134's rules (v1) | $0.248 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.096 ± 0.003 | $0.251 ± 0.006 | 18.2 ± 0.4 | 22 % ± 2 | 29 % ± 1 | 0 of 40 | $-2.65 ± 0.51 |

Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every row, so the fee is the validator's whole margin.

##### The fee against break-even, D17's `FEE_MARGIN` (40 seeds; the runs that didn't collapse)

| Variant | Fee / break-even over the last 13 weeks (± 2 SE) | Within [1 − `FEE_STEP`, 1 + `FEE_MARGIN`] | Runs collapsed | Round 1 (v2): fee / break-even; runs collapsed |
|---|---|---|---|---|
| **Round 2's rules (the design): every wait counts, once** | 1.20 ± 0.04 × | yes | 0 of 40 | 0.47 ± 0.40 ×; 33 of 40 collapsed |
| waits a floor-bond newcomer could end (round 1's signal) | 0.54 ± 1.01 × | no | 38 of 40 | 0.47 ± 0.40 ×; 33 of 40 collapsed |
| waits a newcomer of any bond could end | 1.11 ± 0.06 × | no | 4 of 40 | 1.08 ± 0.07 ×; 1 of 40 collapsed |
| `IDLE_HIGH` 30 % | 1.20 ± 0.04 × | no | 7 of 40 | –; 40 of 40 collapsed |
| `IDLE_HIGH` 50 % | 1.19 ± 0.03 × | yes | 0 of 40 | 0.99 ± 0.10 ×; 12 of 40 collapsed |
| idling over 7 days (`IDLE_WINDOW_DAYS` 7) | 1.17 ± 0.03 × | yes | 0 of 40 | 1.20 ± 0.03 ×; 0 of 40 collapsed |
| `FEE_STEP_UP` 10 % | 1.22 ± 0.03 × | no | 0 of 40 | 0.62 ± 0.36 ×; 32 of 40 collapsed |
| the design, 100 submissions a week | 1.24 ± 0.02 × | no | 0 of 40 | 1.28 ± 0.03 ×; 0 of 40 collapsed |
| the design, starting at v2's $0.05 | 1.24 ± 0.09 × | no | 35 of 40 | –; 40 of 40 collapsed |
| round 1's rules (`V2R1`) | 0.47 ± 0.40 × | no | 33 of 40 | 0.47 ± 0.40 ×; 33 of 40 collapsed |
| #134's rules (v1) | 1.00 ± 0.02 × | yes | 0 of 40 | 1.00 ± 0.02 ×; 0 of 40 collapsed |

Round 1 (v2): the same variant under round 1's rules; for the design and the floor-bond row, round 1's design (the floor-bond signal, 33 of 40 collapsed); round 1 measured every wait counted at 1.21 ± 0.04 × (0 of 40 collapsed).

##### An honest validator's month on the market (40 seeds; honest validators active a month or more; $ a month)

| Market and outages | Service fees | Usage margin | Node overhead | Slashes | Fixed costs | The bond's capital | Net | Runs with such validators | Round 1 (v2): net |
|---|---|---|---|---|---|---|---|---|---|
| **the design: every outage before the seal (silence, $5)** | $7.72 ± 0.16 | $0.01 ± 0.01 | $0.52 ± 0.01 | $0.98 ± 0.05 | $4.67 ± 0.00 | $3.00 ± 0.24 | $-1.43 ± 0.22 | 40 | $-6.81 ± 0.99 |
| **the design: every outage after the seal (withheld, $5)** | $7.71 ± 0.17 | $0.01 ± 0.01 | $0.52 ± 0.01 | $0.98 ± 0.05 | $4.67 ± 0.00 | $3.00 ± 0.24 | $-1.45 ± 0.22 | 40 | $-7.35 ± 0.97 |
| both flat slashes at $1: before the seal | $7.04 ± 0.15 | $0.01 ± 0.01 | $0.51 ± 0.01 | $0.18 ± 0.01 | $4.67 ± 0.00 | $2.88 ± 0.19 | $-1.19 ± 0.19 | 40 | – |
| both flat slashes at $1: after the seal | $7.05 ± 0.15 | $0.01 ± 0.01 | $0.51 ± 0.01 | $0.18 ± 0.01 | $4.67 ± 0.00 | $2.88 ± 0.19 | $-1.18 ± 0.20 | 40 | – |
| silence unslashed: before the seal | $6.92 ± 0.17 | $0.01 ± 0.01 | $0.51 ± 0.01 | $0.00 ± 0.00 | $4.67 ± 0.00 | $2.91 ± 0.24 | $-1.15 ± 0.24 | 40 | – |
| round 1's rules (`V2R1`): before the seal (unslashed) | $5.25 ± 0.29 | $0.03 ± 0.02 | $0.55 ± 0.03 | $0.00 ± 0.00 | $4.67 ± 0.00 | $6.87 ± 0.89 | $-6.81 ± 0.99 | 40 | $-6.81 ± 0.99 |
| #134's rules (v1) | $8.60 ± 0.23 | $-0.02 ± 0.01 | $0.46 ± 0.01 | $4.34 ± 0.51 | $4.67 ± 0.00 | $1.76 ± 0.07 | $-2.65 ± 0.51 | 40 | $-2.65 ± 0.51 |

Round 1 (v2): its design's market (the floor-bond signal, collapsing) with outages before the seal (unslashed) and after it ($1); D16 cites $1.11 ± 0.09 of slashes a month at $5 from round 1's any-bond market.

#### The fee over the year: round 2's rules (the design) (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.204 ± 0.007 | 21.7 ± 0.2 | 5 % ± 2 | 40 % ± 2 |
| 5–8 | $0.158 ± 0.011 | 17.6 ± 0.9 | 8 % ± 3 | 31 % ± 2 |
| 9–12 | $0.187 ± 0.011 | 12.1 ± 1.4 | 12 % ± 6 | 21 % ± 6 |
| 13–16 | $0.205 ± 0.011 | 14.6 ± 1.3 | 9 % ± 5 | 22 % ± 5 |
| 17–20 | $0.212 ± 0.008 | 17.2 ± 1.0 | 5 % ± 2 | 21 % ± 2 |
| 21–24 | $0.207 ± 0.008 | 18.0 ± 0.9 | 4 % ± 1 | 23 % ± 2 |
| 25–28 | $0.208 ± 0.007 | 18.0 ± 0.9 | 5 % ± 1 | 22 % ± 2 |
| 29–32 | $0.210 ± 0.008 | 17.8 ± 0.7 | 4 % ± 1 | 21 % ± 1 |
| 33–36 | $0.212 ± 0.007 | 18.7 ± 0.9 | 4 % ± 1 | 23 % ± 2 |
| 37–40 | $0.211 ± 0.008 | 18.8 ± 1.1 | 4 % ± 1 | 22 % ± 2 |
| 41–44 | $0.210 ± 0.008 | 18.5 ± 0.9 | 4 % ± 1 | 22 % ± 2 |
| 45–48 | $0.210 ± 0.007 | 18.4 ± 0.9 | 4 % ± 1 | 22 % ± 2 |
| 49–52 | $0.215 ± 0.007 | 18.9 ± 0.9 | 4 % ± 1 | 23 % ± 2 |

#### The fee over the year: waits a floor-bond newcomer could end (round 1's signal) (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.180 ± 0.006 | 21.7 ± 0.1 | 0 % ± 0 | 40 % ± 2 |
| 5–8 | $0.102 ± 0.008 | 15.1 ± 0.7 | 0 % ± 0 | 33 % ± 3 |
| 9–12 | $0.068 ± 0.011 | 4.0 ± 1.0 | 4 % ± 1 | 52 % ± 8 |
| 13–16 | $0.053 ± 0.010 | 2.7 ± 1.0 | 12 % ± 3 | 77 % ± 11 |
| 17–20 | $0.053 ± 0.010 | 2.1 ± 0.9 | 15 % ± 3 | 85 % ± 10 |
| 21–24 | $0.057 ± 0.011 | 1.9 ± 0.8 | 16 % ± 2 | 88 % ± 10 |
| 25–28 | $0.059 ± 0.011 | 2.0 ± 0.8 | 16 % ± 2 | 88 % ± 10 |
| 29–32 | $0.063 ± 0.012 | 1.8 ± 0.7 | 16 % ± 2 | 90 % ± 9 |
| 33–36 | $0.065 ± 0.013 | 1.5 ± 0.6 | 17 % ± 2 | 93 % ± 7 |
| 37–40 | $0.071 ± 0.015 | 1.3 ± 0.5 | 17 % ± 2 | 94 % ± 7 |
| 41–44 | $0.079 ± 0.015 | 1.4 ± 0.5 | 17 % ± 2 | 95 % ± 7 |
| 45–48 | $0.083 ± 0.015 | 1.2 ± 0.3 | 17 % ± 2 | 96 % ± 5 |
| 49–52 | $0.091 ± 0.017 | 1.2 ± 0.4 | 18 % ± 1 | 97 % ± 5 |

#### A provider halves its price (40 seeds; Anthropic's input-token price at the end of each day, as a multiple of its value at deployment; its validators post their new costs on day 30)

| End of day | 29 | 30 | 31 | 32 | 33 | 34 | 35 |
|---|---|---|---|---|---|---|---|
| Unit price | 1.000 | 0.750 | 0.562 | 0.500 | 0.500 | 0.500 | 0.500 |

One `PRICE_STEP_MAX` step (−25 %) a day until it reaches the median of the new tables (half the old median), with no proposal or vote.

#### The pricing attackers against their honest twins (40 seeds; a year; returns in $)

| Attacker | Market | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's / twin's | Active validators (last 13 weeks) | Round 1 (v2) | What it did |
|---|---|---|---|---|---|---|---|---|---|
| Cartel: 6 validators refusing half their draws | design | -1,976 ± 53 | yes | loses | $0.217 / $0.189 | 1.00 / 1.00 | 19.2 | -488 ± 17 | 258 refusals, suspended 42 times, slashed $1,297 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | design | -502 ± 71 | yes | loses | $0.243 / $0.198 | 1.00 / 1.00 | 23.7 | -603 ± 10 | 285 spam submissions costing its solver $574 |
| Spammer: a bad fix a day, judged | design | -915 ± 28 | yes | loses | $0.216 / $0.198 | 1.00 / 1.00 | 24.8 | -548 ± 50 | 364 spam submissions costing its solver $1,015 |
| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs | design | +2.7 ± 3.9 | **no: it gains** | not significant | $0.207 / $0.207 | 1.00 / 1.00 | 18.9 | +33 ± 4 | usage margin $-1 (twin: $-1) |
| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) | design | -0.1 ± 2.3 | yes | not significant | $0.221 / $0.220 | 1.00 / 1.00 | 18.9 | +28 ± 4 | usage margin $-1 (twin: $-1) |
| Fee farmer: 10 idle validators at the bond floor (twin: one) | design | -402 ± 21 | yes | loses | $0.185 / $0.199 | 1.00 / 1.00 | 16.4 | -548 ± 1 | service fees $205 (twin: $21) |
| Cartel: 6 validators refusing half their draws | waits a floor-bond newcomer could end (round 1's signal) | -6,005 ± 526 | yes | loses | $0.063 / $0.093 | 1.00 / 1.00 | 3.9 | -488 ± 17 | 1063 refusals, suspended 151 times, slashed $5,343 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | waits a floor-bond newcomer could end (round 1's signal) | -598 ± 13 | yes | loses | $0.079 / $0.077 | 1.00 / 1.00 | 4.6 | -603 ± 10 | 353 spam submissions costing its solver $604 |
| Cartel: 6 validators refusing half their draws | waits a newcomer of any bond could end | -2,015 ± 59 | yes | loses | $0.183 / $0.117 | 1.00 / 1.00 | 13.4 | -503 ± 11 | 292 refusals, suspended 48 times, slashed $1,468 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | waits a newcomer of any bond could end | -495 ± 69 | yes | loses | $0.198 / $0.152 | 1.00 / 1.00 | 17.6 | -463 ± 89 | 302 spam submissions costing its solver $587 |

Round 1 (v2): the same attacker on round 1's design market (the floor-bond signal, which collapsed in 33 of 40 runs); for the any-bond rows, round 1's any-bond switch.

### Model scores

#### The families' scores under round 2's rules (40 seeds; at the year's end; the balanced score)

| Family | True accuracy (assumed) | Score (counted verdicts) | Fee factor (normalised) | Share of the year barred | Times barred / recovered | Recovery blocks judged |
|---|---|---|---|---|---|---|
| `top` | 95 % | 93.6 ± 0.8 % | 1.18 ± 0.03 × | 0 ± 0 % | 0.0 / 0.0 | 0.0 |
| `mid` | 90 % | 88.1 ± 1.3 % | 0.98 ± 0.03 × | 0 ± 0 % | 0.0 / 0.0 | 0.0 |
| `low` | 85 % | 82.2 ± 1.7 % | 0.81 ± 0.05 × | 7 ± 7 % | 0.1 / 0.0 | 0.0 |
| `weak` | 68 % | 65.4 ± 1.6 % | 0.50 ± 0.00 × | 95 ± 1 % | 1.1 / 0.1 | 13.1 |

Round 1 (v2), `weak`: score 66.6 ± 6.0 %, barred 58 ± 3 % of the year, barred / recovered 11.3 / 10.8 times.

#### Recovery by chance (40 seeds; a year; the score world; the `weak` family, right 68 % of the time, as it is barred and recovers)

| Recovery rule | Recoveries a year | Times barred | Share of the year barred | Blocks judged a year | Recoveries per block judged (pooled) | Score at the year's end |
|---|---|---|---|---|---|---|
| **Fresh blocks of 100 at `SCORE_MIN` + 10 points (80 %), the balanced score (the design)** | 0.12 ± 0.11 | 1.10 ± 0.10 | 95 ± 1 % | 13.1 ± 1.0 | 1.0 % | 65.4 ± 1.6 % |
| round 1's recovery: the last 50 shadow verdicts at each check, at `SCORE_MIN` | 9.90 ± 0.47 | 10.40 ± 0.42 | 58 ± 3 % | 0.0 ± 0.0 | – (no blocks: a sliding test) | 69.9 ± 2.4 % |
| a fresh block of 200 at `SCORE_MIN` + 5 points | 0.05 ± 0.07 | 1.05 ± 0.07 | 96 ± 1 % | 6.5 ± 0.4 | 0.8 % | 65.7 ± 1.5 % |
| fresh blocks of 100 at 80 %, plain agreement for the score | 0.07 ± 0.08 | 1.07 ± 0.08 | 96 ± 1 % | 14.2 ± 0.2 | 0.5 % | 67.0 ± 1.1 % |
| round 1's rules (`V2R1`): plain agreement, the sliding recovery | 10.75 ± 0.53 | 11.35 ± 0.49 | 58 ± 3 % | 0.0 ± 0.0 | – (no blocks: a sliding test) | 66.6 ± 6.0 % |

D14's estimates (hand, normal approximation): a 68 % family passes a block of 100 at 80 % about 1.9 % of the time; barred all year, it fills 10 to 15 blocks, so 0.2 to 0.3 chance recoveries a year. Round 1 (v2): 11.3 / 10.8 barred / recovered a year.

#### One vote, pay by score, weighted votes (40 seeds; a year)

| Families | Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | Service fees per submission ($) | `top` net a month ($) | `mid` net a month ($) | `low` net a month ($) | `weak` net a month ($) |
|---|---|---|---|---|---|---|---|---|---|
| blind spots | One vote, no scores | 1.48 ± 0.15 | 0.87 ± 0.10 | 5.87 ± 0.28 | 0.363 ± 0.001 | -7.51 ± 0.17 | -7.36 ± 0.18 | -7.46 ± 0.15 | -7.73 ± 0.20 |
| blind spots | **One vote, pay by score (round 2: the balanced score, recovery by blocks, the normalised factor)** | 1.13 ± 0.10 | 0.28 ± 0.05 | 3.48 ± 0.15 | 0.354 ± 0.010 | -7.23 ± 0.20 | -7.36 ± 0.18 | -7.62 ± 0.17 | -8.29 ± 0.20 |
| blind spots | One vote, pay by score, the factor's 1 × at the median family score | 1.13 ± 0.10 | 0.28 ± 0.05 | 3.48 ± 0.15 | 0.398 ± 0.010 | -6.93 ± 0.20 | -7.15 ± 0.18 | -7.52 ± 0.17 | -8.29 ± 0.20 |
| blind spots | One vote, pay by score, plain agreement for the score | 1.15 ± 0.10 | 0.28 ± 0.05 | 3.54 ± 0.12 | 0.361 ± 0.000 | -7.18 ± 0.18 | -7.33 ± 0.19 | -7.61 ± 0.17 | -8.31 ± 0.19 |
| blind spots | Votes weighted by the score factor | 1.27 ± 0.12 | 0.29 ± 0.05 | 3.54 ± 0.18 | 0.351 ± 0.010 | -7.22 ± 0.21 | -7.37 ± 0.19 | -7.64 ± 0.16 | -8.18 ± 0.20 |
| blind spots | One vote, pay by score, round 1's scores (`V2R1`) | 1.33 ± 0.11 | 0.51 ± 0.07 | 4.49 ± 0.14 | 0.354 ± 0.001 | -6.41 ± 0.13 | -6.49 ± 0.12 | -6.73 ± 0.12 | -7.96 ± 0.19 |
| blind spots | One vote, pay by score, #134's scores (shadows merged, neutral at 80 %) | 1.26 ± 0.12 | 0.44 ± 0.07 | 4.00 ± 0.16 | 0.499 ± 0.003 | -14.27 ± 0.81 | -14.20 ± 1.03 | -15.05 ± 0.96 | -10.07 ± 0.65 |
| no blind spots | One vote, no scores | 0.30 ± 0.05 | 0.88 ± 0.10 | 4.08 ± 0.23 | 0.363 ± 0.000 | -7.53 ± 0.18 | -7.42 ± 0.20 | -7.42 ± 0.14 | -7.61 ± 0.20 |
| no blind spots | **One vote, pay by score (round 2: the balanced score, recovery by blocks, the normalised factor)** | 0.07 ± 0.02 | 0.27 ± 0.05 | 1.49 ± 0.10 | 0.361 ± 0.000 | -7.19 ± 0.19 | -7.31 ± 0.19 | -7.58 ± 0.16 | -8.22 ± 0.21 |
| no blind spots | Votes weighted by the score factor | 0.07 ± 0.02 | 0.26 ± 0.04 | 1.49 ± 0.10 | 0.361 ± 0.000 | -7.19 ± 0.19 | -7.31 ± 0.19 | -7.58 ± 0.16 | -8.22 ± 0.21 |

Round 1 (v2), blind spots: service fees per submission 0.354 ± 0.001 with pay by score, 0.363 ± 0.001 without.

#### Everyone moves to the top model (40 seeds; a year; every validator reconsiders monthly and changes to the family paying most per head when it pays 10 % more)

| | Nobody moves | Everyone moves, registering again (the design) | Everyone moves at once (#134's reading) |
|---|---|---|---|
| Share of drawable validators in `top` at the year's end | 29 ± 2 % | 39 ± 4 % | 42 ± 6 % |
| Share of drawable validators in `mid` at the year's end | 25 ± 2 % | 37 ± 5 % | 29 ± 6 % |
| Share of drawable validators in `low` at the year's end | 25 ± 1 % | 23 ± 5 % | 27 ± 6 % |
| Share of drawable validators in `weak` at the year's end | 21 ± 2 % | 2 ± 1 % | 2 ± 1 % |
| Families with at least 10 % of the validators | 4.0 ± 0.0 | 2.7 ± 0.1 | 2.6 ± 0.2 |
| Share of counted seats held by `top` | 35.0 ± 0.6 % | 37.2 ± 1.0 % | 36.3 ± 0.7 % |
| Panels with more of one family than the cap allows | 0 ± 0 | 0 ± 0 | 0 ± 0 |
| Draws whose k the caps lowered | 3.7 ± 4.6 % | 15.5 ± 4.5 % | 11.2 ± 4.7 % |
| **Submissions that waited for a panel** (`WAIT_CROWD_MAX` 15 %) | 5.5 ± 5.5 % | 11.3 ± 4.9 % | 10.6 ± 5.8 % |
| Bad fixes merged per 100 paid | 1.13 ± 0.10 | 1.19 ± 0.11 | 1.21 ± 0.11 |
| Family changes in the year | 0 ± 0 | 56 ± 4 | 105 ± 7 |
| An activated validator's net per month ($) | -7.51 ± 0.09 | -4.93 ± 0.11 | -7.50 ± 0.09 |

Four validators starting in `low` that move (registering again) against the same four staying: return − twin's **-29 ± 11** $ a year (doesn't gain: yes). Round 1 (v2): crowding 7.9 ± 2.4 % of submissions waited.

#### Crowding into the top model, rule by rule (40 seeds; a year; every validator moves, registering again; `WAIT_CROWD_MAX` 15 %)

| Rule | Submissions that waited for a panel | Draws the caps lowered | Families with at least 10 % of the validators | Share of drawable validators in `weak` / `low` at the year's end | Family changes in the year |
|---|---|---|---|---|---|
| **Round 2's rules (the design)** | 11.3 ± 4.9 % | 15.5 ± 4.5 % | 2.7 ± 0.1 | 2 ± 1 % / 23 ± 5 % | 56 ± 4 |
| plain agreement for the score | 7.7 ± 2.5 % | 13.0 ± 2.4 % | 2.9 ± 0.2 | 2 ± 1 % / 22 ± 4 % | 53 ± 3 |
| round 1's recovery: the last 50 shadow verdicts at each check, at `SCORE_MIN` | 9.9 ± 3.6 % | 15.0 ± 2.9 % | 3.0 ± 0.1 | 3 ± 1 % / 25 ± 4 % | 57 ± 4 |
| silence unslashed | 10.4 ± 4.8 % | 17.4 ± 4.6 % | 2.8 ± 0.1 | 2 ± 1 % / 25 ± 5 % | 57 ± 4 |
| round 1's rules (`V2R1`) | 7.9 ± 2.4 % | 14.6 ± 2.7 % | 3.0 ± 0.1 | 2 ± 1 % / 27 ± 4 % | 56 ± 3 |

Round 1 (v2): 7.9 ± 2.4 % of submissions waited.

#### Herding (40 seeds; a year; 4 herders of one family among 16 honest validators; each votes pass, the public base rate's majority)

| Herders | Their agreement with outcomes (twin's) | ...balanced over passed and failed outcomes | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Round 1 (v2): the same herders, plain agreement |
|---|---|---|---|---|---|---|---|---|---|
| `mid` (90 %), receipts detectable | 76.3 ± 3.8 % (89.3 ± 0.4 %) | 49.0 ± 1.3 % (88.4 ± 0.8 %) | 67.0 ± 2.0 % (87.9 ± 1.4 %) | 94 ± 5 % (2 ± 5 %) | 1.03 ± 0.24 (1.13 ± 0.14) | -3,011 ± 1,202 | yes | loses | -82,767 ± 5,385 |
| `mid` (90 %), not detectable (upper bound) | 76.8 ± 3.3 % (89.3 ± 0.4 %) | 49.3 ± 1.0 % (88.4 ± 0.8 %) | 67.5 ± 1.9 % (87.9 ± 1.4 %) | 93 ± 5 % (2 ± 5 %) | 1.08 ± 0.26 (1.13 ± 0.14) | -23 ± 4 | yes | loses | -10 ± 2 |
| `weak` (68 %), receipts detectable | 79.1 ± 3.3 % (66.2 ± 2.0 %) | 50.4 ± 1.3 % (63.8 ± 3.5 %) | 59.2 ± 2.4 % (64.2 ± 2.7 %) | 98 ± 0 % (96 ± 1 %) | 1.08 ± 0.14 (1.14 ± 0.10) | -1,957 ± 547 | yes | loses | -79,203 ± 5,111 |
| `weak` (68 %), not detectable (upper bound) | 79.4 ± 3.2 % (66.2 ± 2.0 %) | 50.3 ± 1.3 % (63.8 ± 3.5 %) | 59.7 ± 2.3 % (64.2 ± 2.7 %) | 99 ± 0 % (96 ± 1 %) | 1.09 ± 0.14 (1.14 ± 0.10) | +0.2 ± 0.7 | **no: it gains** | not significant | +13 ± 2 |
| `mid`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 76.8 ± 3.3 % (89.3 ± 0.4 %) | 49.3 ± 1.0 % (88.4 ± 0.8 %) | 67.5 ± 1.9 % (87.9 ± 1.4 %) | 93 ± 5 % (2 ± 5 %) | 1.08 ± 0.26 (1.13 ± 0.14) | -347 ± 31 | yes | loses | -54 ± 11 |
| `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 79.4 ± 3.2 % (66.2 ± 2.0 %) | 50.3 ± 1.3 % (63.8 ± 3.5 %) | 59.7 ± 2.3 % (64.2 ± 2.7 %) | 99 ± 0 % (96 ± 1 %) | 1.09 ± 0.14 (1.14 ± 0.10) | -5.3 ± 3.3 | yes | loses | +80 ± 9 |
| `mid`, not detectable, plain agreement for the score | 77.7 ± 1.1 % (89.2 ± 0.2 %) | 50.0 ± 0.0 % (88.5 ± 0.3 %) | 83.4 ± 1.3 % (88.7 ± 0.8 %) | 6 ± 7 % (0 ± 0 %) | 3.09 ± 0.19 (1.18 ± 0.11) | -11 ± 2 | yes | loses | -10 ± 2 |
| `weak`, not detectable, plain agreement for the score | 76.6 ± 1.6 % (66.0 ± 2.0 %) | 50.7 ± 1.1 % (64.7 ± 3.6 %) | 69.0 ± 0.4 % (66.1 ± 1.2 %) | 88 ± 3 % (97 ± 1 %) | 1.42 ± 0.15 (1.12 ± 0.10) | -2.3 ± 1.6 | yes | loses | +13 ± 2 |
| `weak`, not detectable, $0.25, plain agreement for the score | 76.6 ± 1.6 % (66.0 ± 2.0 %) | 50.7 ± 1.1 % (64.7 ± 3.6 %) | 69.0 ± 0.4 % (66.1 ± 1.2 %) | 88 ± 3 % (97 ± 1 %) | 1.42 ± 0.15 (1.12 ± 0.10) | +20 ± 7 | **no: it gains** | **wins** | +80 ± 9 |

#### Scores on the market fee (40 seeds; a year; the score families' accuracies and blind spots; the market's 20 initial validators, five per family, and 2 prospects a week)

| Market | Rule | Mean service fee | Active validators (last 13 weeks) | Bad fixes merged per 100 paid | `top` validator's net per month | `mid` validator's net per month | `low` validator's net per month | `weak` validator's net per month |
|---|---|---|---|---|---|---|---|---|
| design | One vote, no scores | $0.208 ± 0.004 | 17.9 ± 1.1 | 1.52 ± 0.16 | $-0.34 ± 0.22 | $-0.31 ± 0.21 | $-0.26 ± 0.20 | $-0.52 ± 0.23 |
| design | **One vote, pay by score (v3's design)** | $0.214 ± 0.006 | 18.1 ± 1.3 | 1.13 ± 0.11 | $0.55 ± 0.54 | $-0.07 ± 0.45 | $-0.57 ± 0.35 | $-3.79 ± 0.25 |
| plain agreement | One vote, no scores | $0.208 ± 0.004 | 17.9 ± 1.1 | 1.52 ± 0.16 | $-0.34 ± 0.22 | $-0.31 ± 0.21 | $-0.26 ± 0.20 | $-0.52 ± 0.23 |
| plain agreement | **One vote, pay by score (v3's design)** | $0.210 ± 0.005 | 17.9 ± 1.2 | 1.19 ± 0.12 | $0.97 ± 0.33 | $0.29 ± 0.25 | $-0.27 ± 0.23 | $-3.74 ± 0.23 |
| round 1's rules (`V2R1`) | One vote, no scores | $0.069 ± 0.007 | 1.9 ± 0.8 | 1.46 ± 0.23 | $-1.89 ± 0.18 | $-1.08 ± 0.16 | $-1.16 ± 0.17 | $-1.12 ± 0.18 |
| round 1's rules (`V2R1`) | **One vote, pay by score (v3's design)** | $0.056 ± 0.007 | 1.1 ± 0.1 | 1.30 ± 0.25 | $-2.16 ± 0.16 | $-1.31 ± 0.20 | $-1.29 ± 0.17 | $-1.31 ± 0.17 |

Market "design": round 2's rules, the fee starting at the ceiling. The families are priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight model). Prospects decide to enter on the unscaled fee.

#### Herding on the market fee (40 seeds; a year; 4 undetectable herders of one family beside the market's validators)

| Herders | Their agreement (twin's) | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Mean fee | Return − twin's ($, ± 2 SE) | Doesn't gain | Loses | Round 1 (v2) |
|---|---|---|---|---|---|---|---|---|---|
| `mid` (90 %), not detectable, the design's market | 81.3 ± 3.0 % (89.2 ± 0.4 %) | 64.0 ± 1.8 % (88.3 ± 1.0 %) | 98 ± 1 % (6 ± 7 %) | 1.40 ± 0.29 (1.20 ± 0.12) | $0.246 | -340 ± 33 | yes | loses | -5 ± 4 |
| `weak` (68 %), not detectable, the design's market | 78.1 ± 3.6 % (67.3 ± 1.5 %) | 58.7 ± 2.4 % (66.2 ± 1.5 %) | 99 ± 0 % (97 ± 1 %) | 1.23 ± 0.12 (1.19 ± 0.16) | $0.206 | -4.7 ± 2.4 | yes | loses | +33 ± 16 |
| `weak`, not detectable, the design's market, plain agreement for the score | 77.9 ± 1.5 % (67.2 ± 1.5 %) | 71.9 ± 1.9 % (67.2 ± 1.0 %) | 66 ± 8 % (97 ± 1 %) | 2.94 ± 0.42 (1.22 ± 0.11) | $0.202 | +97 ± 31 | **no: it gains** | **wins** | +33 ± 16 |

Round 1 (v2): the same herders on round 1's design market (collapsing); its weak herders gained +202 ± 19 $ on its working (any-bond) market.

### Derived against measured

#### The design's derived numbers against the run

| What | The design says | This run measures |
|---|---|---|
| The early coalition of 5, from 21 with a $15 deposit (D7) | about −$255 ± 152 | -280 ± 147 $ |
| The early coalition of 3, from 21 with $15 (D7) | about −$429 ± 135 | -431 ± 145 $ |
| The coalition of 5 from 14 with $15 (D7) | about −$8 ± 260 (not significant) | -58 ± 259 $ |
| The colluding genesis's bad fixes reversed before payment, two audits (D13, D17) | about 96 % | 93.3 % ± 3.9 % |
| The weak family's chance recoveries a year, blocks of 100 at 80 % (D14) | 0.2 to 0.3 | 0.12 ± 0.11 |
| A 68 % family passing a block of 100 at 80 % (D14) | about 1.9 % | 1.0 % (5 of 525 blocks) |
| The bribed silent judge at $5 (D16) | near the withholder's −$20 | -14 ± 9 $ |
| The bribed withholder at $5 (round 1's switch) | −$20 ± 9 (measured, round 1) | -15 ± 9 $ |
| An honest validator's slashes a month, every outage after the seal at $5 (D16) | $1.11 ± 0.09 (measured on round 1's any-bond market) | $0.98 ± 0.05 |
| The fee over the last 13 weeks, every wait counted (D9) | 1.21 ± 0.04 × break-even, 0 of 40 collapse (round 1's switch) | 1.20 ± 0.04 ×, 0 of 40 collapse |
| Three TEE types, the cap from k = 5: panels of 3 with one type's majority (D6) | 77 % ± 8 (measured, round 1) | 77 ± 8 % |
| Five TEE types, even, the cap from k = 3: one-type majorities of 3 / draws lowered / waited (D6) | none / 6 % ± 1 / 22 % ± 3 (measured, round 1, placeholder types) | 0 ± 0 % / 6 ± 1 % / 22 ± 3 % |
| An always-pass herder's balanced agreement (D14) | 50.1 % ± 0.1 (measured, round 1) | 50.3 ± 1.3 % |

### A rule against its alternative

#### A rule against its alternative: round 2's rules (40 seeds; the same seeds for each pair)

| Round 2's rule | Under the rule | Under each alternative |
|---|---|---|
| Every wait counts, once (`WAIT_SIGNAL` "every") | fee / break-even 1.20 ± 0.04 ×; 0 collapsed; spammer -502 ± 71 $ (doesn't gain: yes); cartel -1,976 ± 53 $ (doesn't gain: yes) | waits a floor-bond newcomer could end (round 1's signal): fee / break-even 0.54 ± 1.01 ×; 38 collapsed; spammer -598 ± 13 $ (doesn't gain: yes); waits a newcomer of any bond could end: fee / break-even 1.11 ± 0.06 ×; 4 collapsed; spammer -495 ± 69 $ (doesn't gain: yes) |
| $5 for silence and for withholding | silent -14 ± 9 $ (doesn't gain: yes); withholder -15 ± 9 $ (doesn't gain: yes) | both flat slashes at $1: silent +250 ± 12 $ (doesn't gain: **no: it gains**), withholder +249 ± 12 $ (doesn't gain: **no: it gains**); silence unslashed: silent +317 ± 13 $ (doesn't gain: **no: it gains**) |
| 21 for adding ADRs and escalated fixes, 14 for removals, a $15 deposit | 5 early: -280 ± 147 $ (doesn't gain: yes); 3 early: -431 ± 145 $ (doesn't gain: yes); escalated: -280 ± 147 $ (doesn't gain: yes); removals: -456 ± 103 $ (doesn't gain: yes) | 14 for every ADR: 5 early -58 ± 259 $ (doesn't gain: **no: up to +200**), 3 early -464 ± 188 $ (doesn't gain: yes); 28 for every ADR: 5 early -283 ± 133 $ (doesn't gain: yes), 3 early -345 ± 140 $ (doesn't gain: yes); $0: 5 early +255 ± 149 $ (doesn't gain: **no: it gains**), 3 early +81 ± 135 $ (doesn't gain: **no: it gains**); $25: 5 early -636 ± 149 $ (doesn't gain: yes), 3 early -773 ± 155 $ (doesn't gain: yes); escalated, forfeits to the funder: +226 ± 151 $ (doesn't gain: **no: it gains**); removals at $0: -52 ± 11 $ (doesn't gain: yes) |
| Two audits of every k = 1 verdict (`K1_AUDITS` 2) | colluder -247 ± 41 $, 93.3 % ± 3.9 % reversed; honest k = 1 pay 19.4 ± 3.6 days | `K1_AUDITS` 1 (one audit of every k = 1 verdict): colluder -224 ± 41 $, 87.1 % ± 5.1 % reversed; honest k = 1 pay 18.9 ± 3.6 days |
| The balanced score | weak herders +0.2 ± 0.7 $ (doesn't gain: **no: it gains**); mid herders -23 ± 4 $ (doesn't gain: yes) | plain agreement for the score: weak herders -2.3 ± 1.6 $ (doesn't gain: yes); mid herders -11 ± 2 $ (doesn't gain: yes) |
| Recovery on fresh blocks of 100 at + 10 points | weak family: 0.12 ± 0.11 recoveries a year, barred 95 ± 1 % | round 1's recovery: the last 50 shadow verdicts at each check, at `SCORE_MIN`: weak family: 9.90 ± 0.47 recoveries a year, barred 58 ± 3 %; a fresh block of 200 at `SCORE_MIN` + 5 points: weak family: 0.05 ± 0.07 recoveries a year, barred 96 ± 1 % |
| The TEE cap from k = 3 while 5 types are accepted, else from k = 5 | three types, even: one type holds a k = 3 majority on 77 ± 8 % (one vendor 77 ± 8 %); caps lowered 14 ± 3 %; waited 21 ± 3 %; five, even: one type holds a k = 3 majority on 0 ± 0 % (one vendor 21 ± 11 %); caps lowered 6 ± 1 %; waited 22 ± 3 % | three, skewed: one type holds a k = 3 majority on 73 ± 8 % (one vendor 73 ± 8 %); caps lowered 13 ± 2 %; waited 18 ± 2 %; five, skewed: one type holds a k = 3 majority on 0 ± 0 % (one vendor 17 ± 10 %); caps lowered 7 ± 2 %; waited 22 ± 2 %; three, the cap from k = 3: one type holds a k = 3 majority on 0 ± 0 % (one vendor 0 ± 0 %); caps lowered 8 ± 2 %; waited 27 ± 4 %; five, the cap from k = 5: one type holds a k = 3 majority on 55 ± 10 % (one vendor 64 ± 10 %); caps lowered 8 ± 2 %; waited 19 ± 2 % |
| Round 2's rules as a whole | colluder -247 ± 41 $, 93.3 % ± 3.9 % reversed; honest k = 1 pay 19.4 ± 3.6 days; fee / break-even 1.20 ± 0.04 ×; 0 collapsed | round 1's rules as a whole (`V2R1`): colluder -221 ± 38 $, 86.6 % ± 5.1 % reversed; honest k = 1 pay 19.0 ± 3.6 days; fee / break-even 0.47 ± 0.40 ×; 33 collapsed; coalition of 5 +622 ± 260 $ (doesn't gain: **no: it gains**) |

#### Round 1's rules against their alternatives, on round 2's rules (40 seeds)

| Round 1's rule | Under the rule | Under each alternative |
|---|---|---|
| k = 1: the hold, `K1_PENDING_MAX` 10 | colluder -247 ± 41 $, 93.3 % ± 3.9 % reversed; honest k = 1 pay 19.4 ± 3.6 days | `K1_PENDING_MAX` 5: colluder -207 ± 40 $, 88.7 % ± 6.7 % reversed; honest k = 1 pay 18.0 ± 4.1 days; `K1_PENDING_MAX` 20: colluder -312 ± 54 $, 96.9 % ± 1.9 % reversed; honest k = 1 pay 23.2 ± 3.0 days; `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties): colluder -102 ± 33 $, 75.0 % ± 17.0 % reversed; honest k = 1 pay 22.9 ± 3.5 days |
| k = 1's window 7 days | colluder -247 ± 41 $, 93.3 % ± 3.9 % reversed; honest k = 1 pay 19.4 ± 3.6 days | k = 1's window 14 days: colluder -264 ± 42 $, 94.7 % ± 3.8 % reversed; honest k = 1 pay 25.3 ± 3.6 days; k = 1's window 30 days: colluder -251 ± 40 $, 95.2 % ± 3.7 % reversed; honest k = 1 pay 40.6 ± 3.6 days |
| `SHADOW_PER_WAITING` 3 | colluder -247 ± 41 $, 93.3 % ± 3.9 % reversed; honest k = 1 pay 19.4 ± 3.6 days | `SHADOW_PER_WAITING` 0: colluder -130 ± 2 $, – ± – reversed; honest k = 1 pay – days |
| False verdict: the whole bond | grinder -272 ± 48 $ (doesn't gain: yes) | 2,000: grinder -90 ± 14 $ (doesn't gain: yes); colluder -85 ± 10 $, 93.3 % ± 3.9 % reversed |
| `IDLE_HIGH` 40 %, idling over one period, symmetric steps | fee / break-even 1.20 ± 0.04 ×; 0 collapsed | `IDLE_HIGH` 30 %: fee / break-even 1.20 ± 0.04 ×; 7 collapsed; `IDLE_HIGH` 50 %: fee / break-even 1.19 ± 0.03 ×; 0 collapsed; idling over 7 days (`IDLE_WINDOW_DAYS` 7): fee / break-even 1.17 ± 0.03 ×; 0 collapsed; `FEE_STEP_UP` 10 %: fee / break-even 1.22 ± 0.03 ×; 0 collapsed |

### Acceptance criteria

#### Acceptance criteria for open validators under D17, round 2 (40 seeds; sweeps on 40; ± 2 standard errors)

| Criterion | Verdict | Threshold | What decides it | Loses (round 1's criterion) |
|---|---|---|---|---|
| Each open-validator attacker doesn't gain against its honest twin | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 | none of 14 gains; the closest: Silent (never seals): `SILENCE_SLASH` $5 (the design) (-14 ± 9 $) | 14 of 14 lose |
| Each pricing attacker doesn't gain against its honest twin | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10 | 1 of 6 gain or aren't shown not to: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) (+2.7 ± 3.9 $) | 4 of 6 lose |
| Each proof-level attacker doesn't gain against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 | none of 7 gains; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes) (-13 ± 1 $) | 7 of 7 lose |
| Each scoring attacker (the herders) doesn't gain against its honest twin | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10 | 1 of 8 gain or aren't shown not to: Herders: `weak` (68 %), not detectable (upper bound) (+0.2 ± 0.7 $) | 7 of 8 lose |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | **met** | 0 runs | 3 validators (12.5 %), spread: a majority on 0.00 % of panels; 3 validators (12.5 %), one host: a majority on 0.00 % of panels | – |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported | reported: 6 (22 %), one host: a majority on 0.0 % of its own panels, 2.8 bad fixes paid, 10.9 false verdicts proven; 6 (22 %), spread: a majority on 1.2 % of its own panels, 6.3 bad fixes paid, 13.7 false verdicts proven; 10 (32 %), one host: a majority on 0.0 % of its own panels, 5.0 bad fixes paid, 14.0 false verdicts proven; 10 (32 %), spread: a majority on 8.0 % of its own panels, 16.0 bad fixes paid, 17.7 false verdicts proven; 20 (49 %), one host: a majority on 0.0 % of its own panels, 9.2 bad fixes paid, 15.4 false verdicts proven; 20 (49 %), spread: a majority on 30.4 % of its own panels, 39.8 bad fixes paid, 16.3 false verdicts proven | – |
| The colluding lone validator doesn't gain, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes are reversed before any payment (pooled), with two audits | **not met** | mean ≤ 0 and mean + 2 SE ≤ $10; share − 2 SE ≥ 90 % | return − twin's -247 ± 41 $ (doesn't gain: yes); reversed before payment 93.3 % ± 3.9 % (195 of 209 that reached an outcome; 0 still pending at the year's end) | loses |
| The constitution waits for the network: no adding ADR or escalated fix passes while fewer than 21 validators are eligible, and no removal while fewer than 14, in any run | **met** | 0 runs | adding ADRs and escalated fixes passed below 21, all runs: 0 (over 3 coalitions); removals passed below 14: 0 (over 2); ADRs passed: 0.33, 0.15, 0.33, 0.45, 0.38 a run | – |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | **met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | from the ceiling, every wait counted: fee / break-even over the last 13 weeks 1.20 ± 0.04 × (the runs that didn't collapse); 0 of 40 runs collapsed below 3 active validators | – |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` (15 %) of submissions wait | **not met** | mean + 2 SE ≤ 15 % | 11.3 ± 4.9 % waited, every validator moving (registering again) | – |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | **met** | every run | 40 of 40 runs, at week 6 ± 1; the median days from a k = 1 verdict to its payment, a run: 19.4 ± 3.6 (p90 over every run: 48.5) | – |
| Answer shopping, the trust point: it doesn't gain at 1 in 10; at 3 in 10 the report gives its gain | **met** | mean ≤ 0 and mean + 2 SE ≤ $10 at 1 in 10 | at 1 in 10: -13 ± 1 $; at 3 in 10 (reported): +174 ± 46 $; at #125's measured room (reported): -16 ± 1 $ | loses |
| Every earlier criterion holds or is named | **met** | named | named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md stand | – |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | all | 4 of 13 criteria not met | – |

## Commands, seeds and tests
- **The report:** `python3 -m pof.sim market validators --seeds 40 --jobs 4` (seeds 1–40; the sybil and audit sweeps on the same 40). `--jobs 4` forks four processes, one section each; the output is the same on one process (checked on `--quick`).
- **Round 1's report:** `python3 -m pof.sim market validators --seeds 40 --v2r1` prints reports/open-validators-v2.md's tables on round 1's rules (`params.V2R1`). **v1:** `--v1`, as before (`POF_OPENVAL_RULES=v1`, a fresh process).
- **One section:** `python3 -m pof.sim.openval {growth,attackers,sybil,audits,levels,pricing,scores,params} --seeds 40`, on round 2's rules (`POF_OPENVAL_RULES=v2r1` or `v1` for the older sets).
- **Tests:** `tests/test_openval_r2.py` (39): each round-2 rule alone against the scenarios of validator-admission, judge-panels, judge-scores and check-pricing; the TEE cap's start following the accepted types, and moving when an ADR removes one; each switch changes only what it names; the new actors beside their twins; D17's "doesn't gain" (−$1 ± 7 passes; −$34 ± 47 and +$3 ± 2 fail); the acceptance table's verdicts following their numbers; `V2R1` reproducing round 1's numbers on seed 1; the command's numbers reproducible; this report naming each criterion as met or not. `tests/test_openval_v2.py` now checks that `--v2r1` prints round 1's quick report byte for byte as main printed it before this change. The open-validator tests (244) take 57 seconds, 20 more than on main (205 in 37 seconds).
- **Not run here:** the CI's Amazon Linux container (Docker is off on this machine); the whole test suite ran under Python 3.9.25 instead. Forgejo CI is the gate.
