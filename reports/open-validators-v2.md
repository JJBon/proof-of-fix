# Open validators, v2: the re-run with #141's rules (proof-of-fix#141; 2026-11-03)

> **Task group 6 of #132** (`openspec/changes/proof-of-fix-132-open-validators/tasks.md`), after #141's revision of the spec (PR #144). The spec is unchanged except group 6's ticked boxes. #141's rules are the simulation's defaults; #134's rules stay reachable (`params.V1`) and are re-run beside them on the same seeds. **Level C is off at launch: owner decision 2026-11-03, spec PR pending.** It is the default here; the merged design (C accepted from genesis) is the comparison switch, and the level C attackers run "after C is switched on by ADR" on a grown network. Findings are for the parameters ADR (#137); the owner decides. [v1's report](open-validators-v1.md) is kept as it is.

**Command:** `python3 -m pof.sim market validators --seeds 40 --jobs 2` prints every table below, in 25 minutes on two processes (50 minutes of CPU, Python 3.13, `nice -n 19`). `--jobs 1` gives the same output (tested). `python3 -m pof.sim market validators --seeds 40 --v1` prints v1's report on #134's rules, unchanged. Every number is a mean over seeds 1–40; every ± is **two** standard errors of that mean. A criterion is judged as D17 says: "loses" means the mean return minus the honest twin's, plus two standard errors, is below zero, and a result that isn't significant fails.

## Summary

**The verdict: not adoptable as it stands. 8 of 13 criteria are met** (v1: 4 of 10). #141's rules make the lone validator and the seed grinder lose, and fix the proof-level attackers, growth and the cost of scores. They break the market: under the floor-bond wait signal the fee only falls, and the network collapses in 33 of 40 runs.

### What now holds
- **The colluding genesis loses: −$221 ± 38 a year** (v1: +$2,920 ± 456). Every bad fix it passes is held and audited, and 87 % of them are reversed before payment. It no longer stalls qualification: 50.9 newcomers qualify in its year, as in its twin's (v1: 3.1 against 13.3).
- **The seed grinder loses: −$250 ± 46** (v1: +$258 ± 79). So does the counterfactual with the seed fixed at the seal (−$240 ± 36; v1: +$1,306 ± 382).
- **The network grows from one validator.** A small bounty reaches k ≥ 3 by week 6 in 40 of 40 runs (v1: week 18). 51 of 54 newcomers qualify, in 15 days (v1: 18, in 135 days). 21 % of submissions wait and 16 % are withdrawn (v1: 68 % and 64 %).
- **The constitution waits:** no ADR passes while fewer than 14 validators are eligible, in any run.
- **The sybil at 12.5 % never holds a majority** of a panel of k ≥ 3, spread or on one host.
- **Every proof-level attacker loses.** A level C genesis is refused at deployment. The level B chip breaker loses even with a $50 device (−$570 ± 64; v1: +$848 ± 40). Answer shopping at 1 in 10 loses (−$13 ± 1).
- **Crowding into the top model is mild:** 7.9 % ± 2.4 of submissions wait (D17 allows 15 %).
- **Pay by score no longer raises the price of a check:** service fees are $0.354 a submission, against $0.363 with no scores (v1: $0.499 against $0.358).
- **Audits deter the bribed cheater** without volunteers from 5 % (−$315 ± 224), and at the design's 10 % (−$795 ± 324).
- **Honest validators aren't slashed for outages:** $0 a month when an outage strikes before the seal, $0.21–0.22 when every outage strikes after it (v1: $4.34).

### What still fails
1. **The market collapses in 33 of 40 runs.** The wait signal counts a wait only if a newcomer bonded at $100 could end it. With bond tiers, such a newcomer can judge only bounties up to $50, so waits for anything larger never raise the fee. `IDLE_HIGH` 40 % lowers the fee from the first weeks; validators leave; the bigger bounties wait; nothing pushes the fee back up. With every wait counted (#134's signal) and every other #141 rule, no run collapses and the fee is 1.21 ± 0.04 × break-even, inside `FEE_MARGIN`.
2. **The silent judge gains its bribe: +$317 ± 13.** k never shrank: it was replaced every time. But silence costs it nothing, and the bribe (5 % of the bounty, about $4 a silence) is income. A `SILENCE_SLASH` of $1 leaves +$250 ± 12. A judge that seals and then withholds gains +$249 ± 12 at the design's $1, and loses only at $5 (−$20 ± 9).
3. **An early coalition of 5 still gains: +$622 ± 260** with the constitution drawn from 14 eligible (v1: +$5,196 ± 2,178), +$280 ± 152 from 21, +$187 ± 138 from 28. A coalition of 3 isn't significant at any threshold (+$148 ± 182 from 14), so it fails "loses" too.
4. **The colluding genesis's catch share is 86.6 % ± 5.1**, pooled over 209 bad fixes that reached an outcome. D17 asks for 90 %; D17's own rationale estimates 87 %.
5. **A weak family's herders still gain, a little:** +$13 ± 2 on the flat fee, +$80 ± 9 at $0.25, +$33 ± 16 on the design's (collapsing) market, +$202 ± 19 on a market that works. With `SCORE_BALANCED` every herder row loses.
6. **The inflaters gain on the collapsing market** (+$33 ± 4; their token price at 1.31 ×): they are most of the few posters left. Where the market works (the any-bond signal) they gain nothing (−$1 ± 7), but that isn't significant, and posting costs nothing, so it still fails "loses".

### v1 and v2, criterion by criterion

| Criterion | v1 (#134's rules) | v2 (#141's rules) | What decides v2 |
|---|---|---|---|
| Each open-validator attacker loses | not met: 5 of 10 don't | not met: 4 of 11 don't | silent judge +$317 ± 13; withholder +$249 ± 12; coalitions of 5 (+$622 ± 260) and 3 (+$148 ± 182) |
| Each pricing attacker loses | not met: the inflaters (+$42, +$48) | not met: the inflaters (+$33 ± 4, +$28 ± 4) | on a market that collapses |
| Each proof-level attacker loses | not met: 7 of 11 don't | met: all 7 lose | the closest: answer shopping at 1 in 10, −$13 ± 1 |
| Each scoring attacker (herders) loses | not met: 2 of 10 don't | not met: 3 of 8 don't | weak herders +$13 ± 2, +$80 ± 9 at $0.25, +$33 ± 16 on the market |
| A sybil at or under the share never holds a majority | met only if the share is ≤ 12 % (unpublished) | met at 12.5 % | 0 % of panels, spread or one host |
| A sybil above the share: reported | met | met | 1.2 % of its own panels at 22 % (spread), 8.0 % at 32 %, 30.5 % at 49 % |
| The colluding lone validator is caught | not met: caught in 0 of 40 runs; 18 % reversed | not met | loses (−$221 ± 38), but 86.6 % ± 5.1 reversed, under 90 % |
| The constitution waits for the network | met (from `K_MAX`) | met (from 14) | 0 ADRs passed below 14 eligible |
| The fee settles near break-even | not met: at the ceiling all year | not met | 33 of 40 runs collapse |
| Everyone crowds into one model | not a criterion (11.6 % ± 5.5 waited) | met | 7.9 % ± 2.4 waited |
| The network still grows | not a criterion (week 18, 40 of 40) | met | week 6, 40 of 40 runs |
| Answer shopping, the trust point | part of the proof-level row (−$2 ± 14, not significant) | met | −$13 ± 1 at 1 in 10; +$174 ± 46 at 3 in 10 (reported) |
| Every earlier criterion holds or is named | met (named) | met (named) | v2's market, checking, token and split reports stand (D15) |
| Adopt the k table, windows, bonds, caps and pricing bounds | not met: 6 of 10 not met | not met: 5 of 13 not met | |

## The acceptance table under D17

### Acceptance criteria for open validators under D17 (40 seeds; sweeps on 40; ± 2 standard errors)

| Criterion | Verdict | Threshold | What decides it |
|---|---|---|---|
| Each open-validator attacker loses against its honest twin | **not met** | mean + 2 SE < 0 | 4 of 11 don't lose: Silent (never seals), the design: no slash for silence (+317 ± 13 $); Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $1 (the design) (+249 ± 12 $); Constitution coalition: 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) (+622 ± 260 $); Constitution coalition: 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) (+148 ± 182 $) |
| Each pricing attacker loses against its honest twin | **not met** | mean + 2 SE < 0 | 2 of 6 don't lose: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) (+33 ± 4 $); Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) (design) (+28 ± 4 $) |
| Each proof-level attacker loses against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | **met** | mean + 2 SE < 0 | all 7 lose; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes) (-13 ± 1 $) |
| Each scoring attacker (the herders) loses against its honest twin | **not met** | mean + 2 SE < 0 | 3 of 8 don't lose: Herders: `weak` (68 %), not detectable (upper bound) (+13 ± 2 $); Herders: `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) (+80 ± 9 $); Herders on the market: `weak` (68 %), not detectable, market at the design's values (+33 ± 16 $) |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | **met** | 0 runs | 3 validators (12.5 %), spread: a majority on 0.00 % of panels; 3 validators (12.5 %), one host: a majority on 0.00 % of panels |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported | reported: 6 (22 %), one host: a majority on 0.0 % of its own panels, 2.8 bad fixes paid, 10.8 false verdicts proven; 6 (22 %), spread: a majority on 1.2 % of its own panels, 6.3 bad fixes paid, 13.6 false verdicts proven; 10 (32 %), one host: a majority on 0.0 % of its own panels, 5.0 bad fixes paid, 14.0 false verdicts proven; 10 (32 %), spread: a majority on 8.0 % of its own panels, 15.9 bad fixes paid, 17.8 false verdicts proven; 20 (49 %), one host: a majority on 0.0 % of its own panels, 9.2 bad fixes paid, 15.4 false verdicts proven; 20 (49 %), spread: a majority on 30.5 % of its own panels, 39.9 bad fixes paid, 16.3 false verdicts proven |
| The colluding lone validator loses, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes are reversed before any payment (pooled) | **not met** | mean + 2 SE < 0 and share − 2 SE ≥ 90 % | return − twin's -221 ± 38 $ (loses); reversed before payment 86.6 % ± 5.1 % (181 of 209 that reached an outcome; 0 still pending at the year's end) |
| The constitution waits for the network: no ADR passes while fewer than 2 × `K_MAX` validators are eligible, in any run | **met** | 0 runs | ADRs passed while fewer than 14 were eligible, all runs: 0 (over 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) and 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design)) |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | **not met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | from the ceiling, fee / break-even over the last 13 weeks 0.47 ± 0.40 × (the runs that didn't collapse); 33 of 40 runs collapsed below 3 active validators |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` (15 %) of submissions wait | **met** | mean + 2 SE ≤ 15 % | 7.9 ± 2.4 % waited, every validator moving (registering again) |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | **met** | every run | 40 of 40 runs, at week 6 ± 1; the median days from a k = 1 verdict to its payment, a run: 19.0 ± 3.6 (p90 over every run: 46.1) |
| Answer shopping, the trust point: it loses at 1 in 10; at 3 in 10 the report gives its gain | **met** | mean + 2 SE < 0 at 1 in 10 | at 1 in 10: -13 ± 1 $ (loses); at 3 in 10 (reported): +174 ± 46 $ |
| Every earlier criterion holds or is named | **met** | named | named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md stand |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | all | 5 of 13 criteria not met |

**The attackers counted** (D17): those on the design's values, the new rules included: the sybils, the colluding genesis at 5 bad fixes a week, the seed grinder (v3's seed), the fee farmer, the silent judge and the withholder at $1, both coalitions at 14, D13's two cheaters at 10 % without volunteers, the six pricing attackers on the design's market, the proof-level attackers with C switched on for the level C rows (answer shopping at 1 in 10), and every herder row on the design's values. **Not counted:** the counterfactual seed, the switches, the 1-a-week colluder (a sensitivity row, as in v1), #134's rules, and answer shopping at 3 in 10 (reported as the trust point).

## Evidence for the owner's open questions

### The published thresholds (D17)
- **`SYBIL_SHARE` 12.5 %:** met. A sybil of 3 among 21 honest validators (12.5 %) never held a majority of a panel of k ≥ 3 in 40 runs, spread or on one host. Spread at 22 %, it holds 1.2 % of its own panels (1.40 % of all k ≥ 3 panels). On one host, TEE type and family it never does, even at 49 %.
- **`LONE_CATCH_SHARE` 90 %:** not met by the design: 86.6 % ± 5.1, so its lower bound is 81.5 %. The best switch, `K1_PENDING_MAX` 20, gives 92.3 % ± 2.5 (lower bound 89.8 %). D17's own rationale ("a 90 % accurate auditor and a challenge panel of 3 reverse it about 87 % of the time") predicts the shortfall. A threshold of 80 % would be met; 90 % needs another check per k = 1 verdict (not simulated).
- **`FEE_MARGIN` 25 %:** not met by the design (33 of 40 runs collapse). Met by two switches: every wait counted (1.21 ± 0.04 × break-even, 0 collapses) and idling over 7 days (1.20 ± 0.03 ×, 0 collapses; the fee stays near $0.24). The any-bond signal is closest to cost (1.08 ± 0.07 ×) but 1 run of 40 collapses. #134's rules also land inside the band (1.00 ± 0.02 ×), but only because the outage slash lifts break-even to the ceiling.
- **`WAIT_CROWD_MAX` 15 %:** met: 7.9 % ± 2.4 waited when every validator chased the top family, registering again to switch (v1, switching at once: 11.6 % ± 5.5).

### Answer shopping at level C, the trust point (C switched on by ADR, a grown network: the genesis at A, 20 validators at C)
- **At 1 in 10** (borderline fixes fool an honest call once in 10): it loses, −$13 ± 1 against the twin that calls once on the same fixes. Its 10.1 flips of 31 are outweighed by the other judges (9.9); none is paid.
- **At 3 in 10:** it gains +$174 ± 46 (v1: +$328 ± 69). It flips 17.4 verdicts; the other judges outweigh 12.8, audits and challenges reverse 3.3, 1.5 are paid.
- **Halving level C's limits (`C_LIMIT_X` 0.5)** barely helps: +$157 ± 47 at 3 in 10.
- The test liar at C loses heavily (−$4,810 ± 505), and the chip breaker after C is switched on too (−$19,766 ± 1,636).
- At launch none of them can register: level C is off.

### `CONSTITUTION_MIN_ELIGIBLE` 14, 21 or 28
- **No value tried makes the coalition of 5 lose:** +$622 ± 260 at 14, +$280 ± 152 at 21, +$187 ± 138 at 28. It passes 0.70, 0.35 and 0.25 ADRs a year, worth $1,000 each.
- **The coalition of 3 is never significant:** +$148 ± 182, +$82 ± 135, +$65 ± 128. By D17 that fails "loses".
- A higher threshold delays the first judged ADR: day 75 at 14, 122 at 21, 165 at 28. More ADRs expire: 9.7, 16.4 and 22.5 of 52.
- **No ADR passed below its threshold, at any value.**
- Derived, not simulated: at 14 the coalition of 5 gains about $15 for each of its 42.7 judged ADRs. A deposit forfeited by a rejected ADR at least that size might make it lose; that is a lever for the ADR (#137) to size.

### The hold's cost to honest solvers on a small network (growth from one validator)
- An honest k = 1 fix is paid a median **19.0 ± 3.6 days** after its verdict (90th percentile 46.1 days), against 3.0 days in v1 (72-hour window, no hold).
- 65 % of k = 1 verdicts are held, for 19.3 days on average, until three challengers are eligible. Then the 7-day window runs.
- `K1_PENDING_MAX` 5: 17.1 days; 20: 21.6 days; `K1_BATCH_BOND`: 21.9 days. k = 1's window at 14 days: 25.1 days; at 30 days: 40.2 days.
- With level C off at launch (a third of newcomers refused): 23.2 ± 5.3 days.
- Only the bounty waits: judges are paid at the verdict. k = 1 is 2 % of all panels drawn in the year.

### The TEE cap from k = 5, and one vendor deciding a k = 3 panel
- **With the cap from k = 5 and three TEE types,** one TEE type holds the majority of **77 % ± 8 of the panels of 3** drawn on a growing network (11.1 % ± 2.8 of all panels of k ≥ 3). One vendor's chip flaw could decide those panels, within k = 3's limits and windows.
- **With the cap from k = 3** (#134's), no panel has a one-vendor majority, and growth is as fast (k ≥ 3 by week 6 in 40 of 40 runs), but more submissions wait (27 % against 21 %).
- **Five TEE types with the cap from k = 3:** no one-vendor majority, the fewest draws lowered by the caps (6 % ± 1, against 13 % ± 3 from k = 5), waiting as with the design (22 %), and fewer bad fixes merged (0.12 against 0.22 per 100 paid).
- The share of draws the caps lowered is higher with the cap from k = 5 (13 %) than from k = 3 (8 %). In 10 seeds' draws: from k = 5, 79 % of draws start at 7 and stay 7, and 6.4 % fall from 7 to 3; from k = 3, 84.5 % stay at 7 and 2.2 % fall to 3.

### The always-pass herder against `SCORE_MIN`, with and without `SCORE_BALANCED`
- A herder voting pass on every draw agrees with outcomes **78.5 % ± 0.5** of the time (a 90 % family's herders: 78.6 %). That is above `SCORE_MIN` (70 %), so the primary rule can't bar it.
- **Balanced** (the mean of its agreement on passed and on failed outcomes), the same herders score **50.1 % ± 0.1**, well under 70 %. An honest judge's balanced score is its accuracy (68.3 % for the weak family, 88.5 % for `mid`).
- With `SCORE_BALANCED` on, the weak family's score with herders falls to 62.1 % ± 2.5 (it is barred 87 % of the year) and the herders lose in every row: −$8 ± 1 (flat fee), −$54 ± 6 ($0.25), −$69 ± 10 (a working market). Without it: +$13, +$80 and +$202.
- Balanced scoring costs nothing measurable elsewhere: bad fixes merged 1.30 against 1.33 per 100 paid, service fees $0.353 a submission.

### Level C at launch: off (the owner's decision) against the merged design
Assumption: the third of newcomers who would register at C don't come back at A or B.
- **Growth from one validator:** k ≥ 3 by week 7 with C off, week 6 with it on (40 of 40 runs both). 32.8 ± 1.6 validators are active at the year's end, against 48.1 ± 2.1. 31 % of submissions wait and 26 % are withdrawn, against 22 % and 18 %. The largest bounty judged at the year's end is $497 against $447.
- **A grown network** (21 validators, a third at C) keeps 30.9 active instead of 46.2. Waiting is unchanged (1 %).
- **Attackers:** the colluding genesis (−$266 ± 44 off, −$264 ± 44 on) and the chip breaker (−$570 ± 64, −$576 ± 64) don't change. The level C attackers can't register while C is off; once it is on, they behave as in the proof-level table.

## Parameters still to change (for the ADR, #137)
Findings, not decisions. Each names the evidence; the owner decides.

1. **`WAIT_SIGNAL` (the floor-bond rule) must change.** It collapses the market in 33 of 40 runs. Every wait counted: 0 collapses, 1.21 ± 0.04 × break-even. The any-bond signal: 1 collapse, 1.08 ± 0.07 ×. Or keep the floor signal and measure idling over 7 days: 0 collapses, 1.20 ± 0.03 ×, but the fee barely leaves $0.24.
2. **`IDLE_HIGH`:** 40 % is right only with a working wait signal. At 30 % every run collapses; at 50 % 12 of 40 do (both with the floor signal). `FEE_STEP_UP` 10 % doesn't help (32 of 40 collapse): drop it.
3. **`SEALED_NO_REVEAL_SLASH` $1 doesn't deter a bribed withholder** (+$249 ± 12); $5 does (−$20 ± 9). $5 costs an honest validator $1.11 a month if every outage strikes after the seal ($0.22 at $1). **`SILENCE_SLASH`:** $1 leaves the silent judge +$250 ± 12; the owner decides whether a bribe that buys only a delay (k never shrank) counts as an attack, or sets a silence slash near $5.
4. **`CONSTITUTION_MIN_ELIGIBLE`:** none of 14, 21 or 28 makes the coalition of 5 lose. Higher values only slow it (+$622, +$280, +$187) and delay every ADR. It needs another lever, such as a deposit lost by a rejected ADR (see above).
5. **`LONE_CATCH_SHARE` 90 %** is above what the design reaches (86.6 % ± 5.1) and what D17 estimates (87 %). Lower it, or add a second audit of each k = 1 verdict (not simulated).
6. **`SCORE_BALANCED`:** adopt it. It is the only switch under which every herder row loses.
7. **Recovery by shadow verdicts** re-admits the weak family about 11 times a year (it is barred 58 % of the year, v1 76 %). The last-50 test on a sliding window passes by chance at 68 % accuracy. Use fresh blocks of 50, or a higher bar for recovery (not simulated).
8. **`SHADOW_PER_WAITING` must stay above 0.** At 0 the hold deadlocks: the genesis reaches its cap of 10 pending verdicts after 20 shadow seats, nobody reaches 20 scored verdicts, and the network never grows (0 of 40 runs reach k ≥ 3).
9. **`K1_PENDING_MAX`:** 5, 10 and 20 trade the catch share (75.9 %, 86.6 %, 92.3 %) against honest payment (17.1, 19.0, 21.6 median days). The colluder loses at all three. `K1_BATCH_BOND` catches less (63.9 %): drop it.
10. **k = 1's window:** 7 days is enough. 14 and 30 days hardly change the colluder (−$243, −$247) or the catch share (88 %, 89 %), and add 6 and 21 days to every honest k = 1 payment.
11. **`TEE_CAP_FROM_K`:** with three TEE types, from k = 5 leaves 77 % of panels of 3 to one vendor's majority. Five accepted TEE types with the cap from k = 3 remove that and lower the fewest draws (see above).
12. **`C_LIMIT_X` 0.5:** drop it; it doesn't stop shopping at 3 in 10 (+$157 against +$174).
13. **`FALSE_VERDICT_SLASH_BPS`:** keep the whole bond. At 2,000 the grinder and the sybil now lose too (−$70 ± 14, −$3,043 ± 532), because the hold and audits catch them, but by much less.
14. **The score factor:** keep it normalised. The factor at 1 × for the median family raises service fees per submission by 7 % ($0.380 against $0.354) for the same bad fixes.

## Spec findings (reported, not fixed: the spec is frozen)
1. **The floor-bond wait signal is one-directional** (D9; check-pricing, "Only waits a newcomer could end raise the fee"). With bond tiers at every level's limits, a newcomer at the $100 floor can end only waits for bounties up to $50. Once validators leave, the fee can't call them back.
2. **`LONE_CATCH_SHARE` (90 %) is above D17's own estimate** of what the hold and a single audit achieve (87 %).
3. **"Loses" can't be met by an attack that costs nothing and gains nothing.** The inflaters on a working market (−$1 ± 7) and the coalition of 3 (+$148 ± 182) fail as "not significant". D17 may want "doesn't gain" (mean − 2 SE ≤ 0) for such attackers.
4. **A held k = 1 verdict's shadows** (validator-admission, "A shadow verdict is scored only against an outcome no lone validator set"): the spec scores them against the sealed majority while held, and also allows "a k = 1 verdict final after its hold". **Reading:** a verdict held at its reveal scores its shadows once, by the sealed majority (or not at all with fewer than 3 revealed); a k = 1 verdict whose window starts at once scores them at finality.
5. **The hold binds almost every k = 1 verdict.** k is 1 only when one or two validators are eligible, so three challengers outside the panel exist only when the caps or the pending cap stepped k down. "The network already has challengers" happens only then (tested).
6. **The hold depends on waiting shadows** (finding 8 above); the spec presents `SHADOW_PER_WAITING` as a speed-up.
7. **Recovery by shadow verdicts** is tested on a sliding window at every new verdict (finding 7 above).
8. **The honest outage:** the spec says silence isn't slashed ("An honest outage"); D16 sizes $1 as if every outage paid it. Both run: $0 a month before the seal, $0.21–0.22 after it.
9. **"Silence gains nothing"** (D16) holds for the protocol (k never shrank), but a bribe for silence is income, and the criterion counts it.

## How the model changed (task 6.1)
Every rule of #141 is a named field of `Params` (`pof/sim/openval/params.py`), with the design's value as the default. `params.V1` is the same table with #134's rules: with it the simulation gives v1's numbers exactly (tested on seed 1; `--v1` prints v1's report byte for byte; the "#134's rules" rows below equal v1's published numbers).

| #141's rule | Field(s) | How it runs |
|---|---|---|
| The k = 1 hold | `K1_HOLD` | A k = 1 verdict's window runs only while `CHALLENGE_K[1]` (3) validators are eligible for its challenge panel; until then it is held: no window, no payment. Checked daily; a running window is held again if the challengers drop below 3. Judges' fees are paid at the verdict. |
| Pending k = 1 verdicts | `K1_PENDING_MAX` 10 (switch `K1_BATCH_BOND`) | A validator at its cap isn't drawn at k = 1: the draw takes another validator, or the submission waits. |
| Every k = 1 verdict audited | `AUDIT_K1_ALL` | At the verdict, or as soon as a validator outside its panel is eligible (checked daily). |
| Split level C passes audited | `AUDIT_SPLIT_C` | A non-unanimous pass by a level C panel is always audited. |
| Shadows scored without a lone validator | `SHADOW_LONE_RULE`, `SHADOW_MAJORITY_MIN` 3 | See spec finding 4. |
| Shadows on waiting submissions | `SHADOW_PER_WAITING` 3 | When a submission first waits, 3 candidates are drawn by its seed, judge it, and are scored against their own majority. |
| Larger challenge panels | `CHALLENGE_LARGER` | `CHALLENGE_K[k]`, or the largest odd number the eligible allow if larger than k (`K_MAX` for `K_MAX`); otherwise the challenge waits, window frozen. |
| D16's slashes | `FALSE_VERDICT_SLASH_BPS` 10,000; `SEALED_NO_REVEAL_SLASH` $1; `SILENCE_SLASH` 0; `NO_REVEAL_SLASH_BPS` 0 | A silent judge is replaced; the reveal-rate floor counts the miss. |
| Unbonding | `UNBONDING_DELAY_H` 504; `UNBOND_AFTER_CHALLENGES` | After the delay, the bond is released only once every verdict the validator gave is final; it stays slashable until then. |
| The constitution | `CONSTITUTION_MIN_ELIGIBLE` 14; `CONSTITUTION_EXPIRE` | An ADR submitted while fewer are eligible expires unjudged. |
| Pricing | `WAIT_SIGNAL` "floor"; `POST_ALL_FAMILIES`; `MEDIAN_LOW_EVEN`; `IDLE_HIGH` 40 %; `FEE_START` the ceiling | Validators post every family's public list price for tokens and their own costs for the shared units; a table missing a unit doesn't count. |
| Scores | `SCORE_COUNTED_ONLY`; `SCORE_FACTOR_RULE` "normalised" | Counted verdicts only. A barred family recovers when its last 50 shadow verdicts agree at 70 % or more; its counted window restarts and it is paid 0.5 × until it has 50 new counted verdicts. The raw factor is divided by its mean over the previous day's counted seats. |
| A family change | `MOVE_REREGISTERS` | The old key leaves; a new key registers with the new family and qualifies before it is drawn. |
| Levels and caps | `GENESIS_LEVELS` A, B; `TEE_CAP_FROM_K` 5; `BOND_TIERS` at every level's limits; `C_ACCEPTED` False | A level C genesis is refused. Level C is off at launch (owner decision 2026-11-03, spec PR pending); `C_ACCEPTED` switches it on, as the constitution's ADR will. |
| D17's thresholds | `SYBIL_SHARE`, `LONE_CATCH_SHARE`, `FEE_MARGIN`, `WAIT_CROWD_MAX`, `BORDERLINE_COUNTED` | Read by `rerun.acceptance`. |

**The switches** of task 6.2 are `rerun.SWITCHES`: each is the design's `Params` with only the fields it names changed (tested), run beside its rule on the same seeds. Five TEE types use placeholder names (`cca`, `ibm-se`) beside the three real ones.

**World assumptions added:** `World.outage_sealed`, the share of honest outages that strike after the seal (0 by default, as the spec's "An honest outage"; 1 in the honest-month rows that say so). A withholding judge (`actors.Silent(sealed=True)`) seals, then withholds. `LevelWorld.c_accepted` overrides `C_ACCEPTED` for a world.

## The full run

Every table of the 40-seed run, as printed. "#134 (v1)" columns quote v1's published numbers (tested to appear in reports/open-validators-v1.md); "#134's rules" rows re-run them on the same seeds.

### Growth from one validator under the hold, and the TEE cap

#### Growth from one validator under #141's rules (40 seeds; one newcomer a week, 30 submissions a week)

| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | Waiting submissions | Withdrawn so far |
|---|---|---|---|---|---|---|---|
| 0 | 1.0 ± 0.0 | 0.1 ± 0.1 | 1.0 | 0 % | $50 | 3.6 ± 0.6 | 0 % |
| 4 | 3.4 ± 0.7 | 1.9 ± 0.3 | 3.0 | 65 % | $108 | 46.5 ± 4.9 | 42 % |
| 8 | 7.7 ± 0.7 | 1.7 ± 0.4 | 6.3 | 100 % | $208 | 27.5 ± 7.1 | 51 % |
| 12 | 11.6 ± 0.9 | 2.2 ± 0.5 | 6.9 | 100 % | $231 | 16.3 ± 5.7 | 46 % |
| 16 | 16.2 ± 1.2 | 2.0 ± 0.6 | 7.0 | 100 % | $269 | 10.0 ± 3.6 | 40 % |
| 20 | 20.1 ± 1.1 | 2.6 ± 0.7 | 7.0 | 100 % | $319 | 5.7 ± 2.8 | 34 % |
| 24 | 24.2 ± 1.4 | 2.7 ± 0.8 | 7.0 | 100 % | $378 | 5.0 ± 2.9 | 30 % |
| 28 | 28.3 ± 1.7 | 2.5 ± 0.9 | 7.0 | 100 % | $419 | 3.9 ± 1.9 | 27 % |
| 32 | 32.3 ± 1.9 | 2.4 ± 1.0 | 7.0 | 100 % | $456 | 3.7 ± 2.8 | 24 % |
| 36 | 36.3 ± 1.7 | 2.5 ± 0.6 | 7.0 | 100 % | $484 | 3.7 ± 2.5 | 22 % |
| 40 | 40.7 ± 1.8 | 1.9 ± 0.6 | 7.0 | 100 % | $512 | 1.8 ± 0.9 | 20 % |
| 44 | 43.7 ± 1.9 | 2.7 ± 0.8 | 7.0 | 100 % | $541 | 1.4 ± 0.7 | 19 % |
| 48 | 48.0 ± 2.1 | 2.5 ± 0.8 | 7.0 | 100 % | $559 | 1.4 ± 0.6 | 17 % |

| Over the year | |
|---|---|
| Submissions that waited for a panel | 21 % ± 3 |
| ...withdrawn after 14 days of waiting | 16 % ± 3 |
| Days from submission to final verdict | 2.1 ± 0.2 |
| Bad fixes merged per 100 paid | 0.22 ± 0.05 |
| Panels drawn at k = 1 / 3 / 5 / 7 | 2 % / 14 % / 6 % / 78 % |
| Draws whose k the caps lowered (from the largest odd number of eligible validators) | 13 % ± 3 |
| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week 6 (40 of 40 runs) / week 9 (40 of 40 runs) |
| Newcomers / qualified in the year | 53.8 ± 2.1 / 51.0 ± 2.1 |
| Days from registration to activation | 15.1 ± 1.5 |
| Failed qualification attempts | 3.8 ± 0.7 |
| Challenges / verdicts reversed / challenges still frozen at year's end | 30.9 ± 2.3 / 4.2 ± 0.8 / 1.5 ± 0.6 |
| Shadows' usage repaid from the sponsors' pool | $197 |
| An activated validator's month: fees $1.08, less overhead $0.34, slashes for outages $0.00, fixed costs $4.67, the bond's capital $1.62 | net **$-5.55** |

##### An honest network grows under the hold (40 seeds; a year; growth from one validator, one newcomer a week, 30 submissions a week; each rule beside its alternatives, same seeds)

| Rule | Runs where a small bounty reaches k ≥ 3 | First 4-week snapshot at k ≥ 3 | Days from a k = 1 verdict to payment: median a run (p90, all runs) | k = 1 verdicts held / days held | Submissions that waited / withdrawn | Newcomers qualified (of joined) / days to qualify | Sponsors' pool on shadows (on waiting submissions) | Bad fixes merged per 100 paid | Draws the caps lowered | Panels of k ≥ 3 (of 3) with one TEE type holding the majority | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)** | 40 of 40 | week 6 ± 1 | 19.0 ± 3.6 (46.1) | 65 ± 8 % / 19.3 ± 3.3 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $197 ($66) | 0.22 ± 0.05 | 13 ± 3 % | 11.1 ± 2.8 % (77 ± 8 %) | 48.0 ± 2.1 |
| `K1_PENDING_MAX` 5 | 40 of 40 | week 6 ± 1 | 17.1 ± 4.1 (43.0) | 52 ± 9 % / 21.0 ± 3.5 | 21 ± 3 % / 17 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $197 ($67) | 0.21 ± 0.05 | 14 ± 3 % | 11.6 ± 3.1 % (79 ± 8 %) | 48.0 ± 2.1 |
| `K1_PENDING_MAX` 20 | 40 of 40 | week 6 ± 1 | 21.6 ± 3.1 (47.6) | 74 ± 6 % / 17.5 ± 2.4 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $197 ($66) | 0.21 ± 0.06 | 13 ± 3 % | 11.2 ± 2.8 % (77 ± 8 %) | 48.0 ± 2.1 |
| `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties) | 40 of 40 | week 5 ± 1 | 21.9 ± 3.7 (46.4) | 72 ± 7 % / 19.7 ± 3.5 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $198 ($67) | 0.21 ± 0.05 | 13 ± 3 % | 11.0 ± 2.7 % (79 ± 8 %) | 48.0 ± 2.1 |
| k = 1's window 14 days | 40 of 40 | week 6 ± 1 | 25.1 ± 3.6 (52.9) | 65 ± 8 % / 19.3 ± 3.3 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $199 ($67) | 0.21 ± 0.05 | 13 ± 3 % | 11.0 ± 2.8 % (77 ± 8 %) | 48.0 ± 2.1 |
| k = 1's window 30 days | 40 of 40 | week 6 ± 1 | 40.2 ± 3.5 (67.0) | 64 ± 8 % / 19.3 ± 3.3 | 21 ± 3 % / 16 ± 3 % | 51.0 ± 2.1 (53.8) / 15 ± 2 | $199 ($68) | 0.22 ± 0.05 | 13 ± 3 % | 10.9 ± 2.8 % (77 ± 8 %) | 48.0 ± 2.1 |
| `SHADOW_PER_WAITING` 0 | 0 of 40 | week – | – (nan) | 100 ± 1 % / 0.0 ± 0.0 | 99 ± 0 % / 96 ± 0 % | 0.0 ± 0.0 (53.8) / – | $1 ($0) | 0.00 ± 0.00 | 0 ± 0 % | 0.0 ± 0.0 % (0 ± 0 %) | 1.0 ± 0.0 |
| #134's TEE cap from k = 3, three TEE types | 40 of 40 | week 6 ± 1 | 14.8 ± 3.5 (53.9) | 46 ± 7 % / 19.1 ± 3.3 | 27 ± 4 % / 21 ± 4 % | 51.0 ± 2.1 (53.8) / 14 ± 1 | $205 ($85) | 0.13 ± 0.04 | 8 ± 2 % | 0.0 ± 0.0 % (0 ± 0 %) | 48.1 ± 2.0 |
| five TEE types, the TEE cap from k = 3 | 40 of 40 | week 6 ± 1 | 17.0 ± 3.8 (48.0) | 54 ± 9 % / 18.9 ± 3.3 | 22 ± 3 % / 17 ± 3 % | 49.5 ± 2.0 (52.0) / 14 ± 1 | $192 ($68) | 0.12 ± 0.04 | 6 ± 1 % | 0.0 ± 0.0 % (0 ± 0 %) | 47.0 ± 2.0 |
| #134's rules (v1) | 40 of 40 | week 18 ± 2 | 3.0 ± 0.0 (3.0) | 0 ± 0 % / – | 68 ± 6 % / 64 ± 6 % | 18.2 ± 5.0 (53.8) / 135 ± 21 | $88 ($0) | 1.26 ± 0.33 | 39 ± 9 % | 0.0 ± 0.0 % (0 ± 0 %) | 17.3 ± 4.6 |

"Days from a k = 1 verdict to payment": over the k = 1 fixes paid in each run, the median a run (mean over runs ± 2 SE) and the 90th percentile over every run's paid k = 1 fixes. "Held": k = 1 verdicts whose window waited for CHALLENGE_K[1] eligible challengers, and the mean days they waited. #134's numbers: waited 68 % ± 6, withdrawn 64 % ± 6, qualified 18.2 ± 5.0 after 135.1 ± 20.6 days, the caps lowered 39 % ± 9 of draws; the last row reruns them.

### The attackers

#### Each attacker against its honest twin (40 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | #134's return − twin's (v1) | What it got |
|---|---|---|---|---|---|---|
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families | -21,601 ± 2,530 | loses | -22,670 | -1,069 | -1,494 ± 486 | 15.9 bad fixes paid of 96; a majority on 8 % of its own panels; 17.8 false verdicts proven |
| Sybil: 10 of 30 validators, one host, TEE type and family | -17,936 ± 1,753 | loses | -19,037 | -1,100 | -2,122 ± 329 | 5.0 bad fixes paid of 96; a majority on 0 % of its own panels; 14.0 false verdicts proven |
| Seed grinder (v3's seed: a later block) | -250 ± 46 | loses | -307 | -57 | 258 ± 79 | 1.1 bad fixes paid of 24 attempts; 5.4 false verdicts proven, 0.0 challenges still frozen; 50.9 newcomers qualified (twin: 50.9) |
| Seed grinder (counterfactual: the seed fixed at the seal) | -240 ± 36 | loses | -297 | -57 | 1,306 ± 382 | 0.4 bad fixes paid of 7 attempts; 6.7 false verdicts proven, 0.0 challenges still frozen; 51.1 newcomers qualified (twin: 51.1) |
| Fee farmer (10 idle nodes at the bond floor; twin: one node) | -535 ± 1 | loses | -594 | -58 | -544 ± 3 | 44.2 counted checks a node |
| Sybil, spread, `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -3,043 ± 532 | loses | -4,112 | -1,069 | – | 16.1 bad fixes paid of 96; a majority on 8 % of its own panels; 17.7 false verdicts proven |
| Seed grinder, `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -70 ± 14 | loses | -127 | -57 | – | 1.1 bad fixes paid of 24 attempts; 5.4 false verdicts proven, 0.0 challenges still frozen; 50.9 newcomers qualified (twin: 50.9) |

The colluding genesis, the silent judge and the constitution coalition have their own tables below.

#### The colluding genesis under the hold (40 seeds; a year; growth from one validator; the genesis, bonded $100, passes its accomplice's bad fixes at k = 1; against its honest twin)

| Rule | Return − twin's ($, ± 2 SE) | Against its twin | Bad fixes passed / reversed / paid / still pending | Reversed before payment, pooled (± 2 SE) | Its verdicts held | Challenges still frozen | Newcomers qualified (twin's) | Slashed |
|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)**, 5 bad fixes a week | -221 ± 38 | loses | 5.2 / 4.5 / 0.7 / 0.0 | 86.6 % ± 5.1 % | 6.4 | 0.0 | 50.9 (50.9) | $225 |
| `K1_PENDING_MAX` 5 | -185 ± 38 | loses | 2.9 / 2.2 / 0.7 / 0.0 | 75.9 % ± 7.8 % | 3.0 | 0.0 | 50.9 (50.9) | $190 |
| `K1_PENDING_MAX` 20 | -299 ± 51 | loses | 9.8 / 9.0 / 0.8 / 0.0 | 92.3 % ± 2.5 % | 10.6 | 0.0 | 50.9 (50.9) | $300 |
| `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties) | -97 ± 33 | loses | 0.9 / 0.6 / 0.3 / 0.0 | 63.9 % ± 17.1 % | 0.8 | 0.0 | 50.9 (50.9) | $92 |
| k = 1's window 14 days | -243 ± 36 | loses | 5.2 / 4.6 / 0.6 / 0.0 | 88.0 % ± 4.8 % | 6.4 | 0.0 | 50.9 (50.9) | $242 |
| k = 1's window 30 days | -247 ± 39 | loses | 5.2 / 4.7 / 0.6 / 0.0 | 89.0 % ± 4.8 % | 6.4 | 0.0 | 50.9 (50.9) | $245 |
| `SHADOW_PER_WAITING` 0 | -130 ± 2 | loses | 4.7 / 0.0 / 0.0 / 4.7 | – ± – | 4.7 | 0.0 | 0.0 (0.0) | $0 |
| `FALSE_VERDICT_SLASH_BPS` 2,000 (sensitivity) | -67 ± 11 | loses | 5.2 / 4.5 / 0.7 / 0.0 | 86.6 % ± 5.1 % | 6.4 | 0.0 | 50.9 (50.9) | $78 |
| #141's rules, 1 bad fix a week | -103 ± 30 | loses | 1.6 / 1.5 / 0.1 / 0.0 | 92.3 % ± 6.3 % | 2.0 | 0.0 | 50.9 (50.9) | $100 |
| #134's rules (v1), 5 bad fixes a week | +2,920 ± 456 | **wins** | 174.9 / 31.1 / 90.2 / 53.7 | 25.6 % ± 7.3 % | 0.0 | 52.8 | 3.1 (13.3) | $134 |

#134 (k = 1's 72-hour window, 20 % slash, no hold): 2,920 ± 456 $, 1242 of the 6997 bad fixes it passed reversed (18 %); the last row reruns it. "Reversed before payment" counts the passed bad fixes that reached an outcome by the year's end; "still pending" ones (held or in their window at the year's end) are neither.

#### A silent judge without a silence slash (40 seeds; a year; a grown network of 12 honest validators; bribed 5 % of the bounty on 10 % of its draws)

| Judge and rule | Return − twin's ($, ± 2 SE) | Against its twin | Bribed misses / suspended | Slashed | k ever shrank | #134 (v1) |
|---|---|---|---|---|---|---|
| **Silent (never seals), the design: no slash for silence** | +317 ± 13 | **wins** | 63.9 / 8.4 | $0.00 | never | – |
| Silent, `SILENCE_SLASH` $1 | +250 ± 12 | **wins** | 63.9 / 8.4 | $66.78 | never | – |
| **Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $1 (the design)** | +249 ± 12 | **wins** | 63.9 / 8.4 | $63.88 | never | – |
| Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $0.50 | +282 ± 12 | **wins** | 63.9 / 8.4 | $31.94 | never | – |
| Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5 | -20 ± 9 | loses | 63.9 / 8.4 | $319.38 | never | – |
| Silent, #134's rules (5 % of the bond a miss) | -3,813 ± 123 | loses | 64.1 / 8.4 | $4,171.29 | never | -3,813 ± 123 |

#### An early coalition (40 seeds; a year; growth from one validator; the coalition registers its validators at the start and submits an ADR worth $1,000 to it each week; its validators pass them)

| Coalition and rule | Return − twin's ($, ± 2 SE) | Against its twin | ADRs submitted / expired / judged / passed | Passed while fewer than the threshold were eligible (all runs) | Passed while fewer than 2 × `K_MAX` (14) were eligible (all runs) | First ADR judged (day; 365: none) | #134 (v1) |
|---|---|---|---|---|---|---|---|
| 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) | +622 ± 260 | **wins** | 52 / 9.7 / 42.7 / 0.70 | 0 | 0 | 75 | – |
| 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 21 | +280 ± 152 | **wins** | 52 / 16.4 / 36.0 / 0.35 | 0 | 0 | 122 | – |
| 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 28 | +187 ± 138 | **wins** | 52 / 22.5 / 29.9 / 0.25 | 0 | 0 | 165 | – |
| 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) | +148 ± 182 | not significant | 52 / 11.3 / 41.0 / 0.23 | 0 | 0 | 86 | – |
| 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 21 | +82 ± 135 | not significant | 52 / 18.1 / 34.2 / 0.15 | 0 | 0 | 135 | – |
| 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 28 | +65 ± 128 | not significant | 52 / 24.8 / 27.5 / 0.12 | 0 | 0 | 180 | – |
| 5 early validators, #134's rule (`K_MAX` eligible, ADRs wait) | +5,196 ± 2,178 | **wins** | 52 / 0.0 / 45.4 / 5.28 | 0 | 205 | 237 | 5,196 ± 2,178 |
| 3 early validators, #134's rule (`K_MAX` eligible, ADRs wait) | +819 ± 450 | **wins** | 52 / 0.0 / 45.8 / 0.90 | 0 | 33 | 189 | 819 ± 450 |

#### The sybil's majorities by its share (40 seeds; 20 honest validators, newcomers at half a validator a week; its bad fixes at 2 a week)

| Sybil validators (share of the eligible) | Spread | Majority of its own panels | Majority of any panel with k ≥ 3 | Bad fixes paid | False verdicts proven |
|---|---|---|---|---|---|
| 3 (12 %) | spread | 0.0 % | 0.00 % | 1.8 | 8.0 |
| 3 (12 %) | one host | 0.0 % | 0.00 % | 1.2 | 7.1 |
| 6 (22 %) | spread | 1.2 % | 1.40 % | 6.3 | 13.6 |
| 6 (22 %) | one host | 0.0 % | 0.00 % | 2.8 | 10.8 |
| 10 (32 %) | spread | 8.0 % | 7.51 % | 15.9 | 17.8 |
| 10 (32 %) | one host | 0.0 % | 0.00 % | 5.0 | 14.0 |
| 20 (49 %) | spread | 30.5 % | 32.37 % | 39.9 | 16.3 |
| 20 (49 %) | one host | 0.0 % | 0.00 % | 9.2 | 15.4 |

#### The watcher's dilemma (40 seeds; 26 weeks; one lazy cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 28.6 | 0 % | 4.1 ± 0.3 | pays | $0.0000 |
| none | 1 % | 28.6 | 1 % | -284.2 ± 215.0 | loses | $0.0017 |
| none | 2 % | 28.6 | 2 % | -860.7 ± 359.9 | loses | $0.0034 |
| none | 5 % | 28.5 | 5 % | -1,853.7 ± 518.5 | loses | $0.0089 |
| none | 10 % | 28.4 | 11 % | -3,807.5 ± 604.9 | loses | $0.0179 |
| none | 20 % | 28.4 | 19 % | -6,690.2 ± 910.4 | loses | $0.0362 |
| yes | 0 % | 28.5 | 6 % | -2,238.1 ± 508.6 | loses | $0.0000 |
| yes | 1 % | 28.4 | 7 % | -2,494.3 ± 502.0 | loses | $0.0017 |
| yes | 2 % | 28.4 | 8 % | -3,038.8 ± 620.0 | loses | $0.0034 |
| yes | 5 % | 28.4 | 11 % | -4,031.7 ± 770.5 | loses | $0.0089 |
| yes | 10 % | 28.3 | 16 % | -5,857.5 ± 804.4 | loses | $0.0179 |
| yes | 20 % | 28.3 | 25 % | -8,740.2 ± 1,073.3 | loses | $0.0362 |

#### The watcher's dilemma (40 seeds; 26 weeks; one bribed cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 0 % | 6.7 | 0 % | 37.6 ± 3.9 | pays | $0.0000 |
| none | 1 % | 6.7 | 1 % | -26.4 ± 89.3 | not significant | $0.0017 |
| none | 2 % | 6.7 | 2 % | -154.6 ± 172.4 | not significant | $0.0034 |
| none | 5 % | 6.7 | 4 % | -314.7 ± 223.9 | loses | $0.0089 |
| none | 10 % | 6.7 | 10 % | -795.1 ± 324.2 | loses | $0.0179 |
| none | 20 % | 6.7 | 18 % | -1,499.8 ± 494.8 | loses | $0.0362 |
| yes | 0 % | 6.7 | 6 % | -506.9 ± 239.9 | loses | $0.0000 |
| yes | 1 % | 6.7 | 7 % | -570.9 ± 241.5 | loses | $0.0017 |
| yes | 2 % | 6.7 | 9 % | -699.1 ± 272.3 | loses | $0.0034 |
| yes | 5 % | 6.7 | 11 % | -859.2 ± 305.8 | loses | $0.0089 |
| yes | 10 % | 6.7 | 16 % | -1,307.6 ± 353.5 | loses | $0.0179 |
| yes | 20 % | 6.7 | 24 % | -2,012.3 ± 499.5 | loses | $0.0362 |

### The k table compared

#### The k table compared (40 seeds; a year; 30 submissions a week; every validator at level A; the same seeds for both rules)

| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth from one validator | k table (v3) | 2.1 ± 0.5 (0.22 ± 0.05) | 965 ± 38 | 2.1 ± 0.2 | 21 ± 3 % | 16 ± 3 % | $1.77 ± 0.03 | $-5.54 ± 0.08 | 48.0 ± 2.1 |
| Growth from one validator | fixed k = 3, bounties to $625 | 6.2 ± 0.9 (0.65 ± 0.09) | 946 ± 40 | 2.3 ± 0.2 | 24 ± 4 % | 17 ± 3 % | $1.04 ± 0.03 | $-5.96 ± 0.08 | 47.6 ± 1.8 |
| Small: the genesis and 4 active | k table (v3) | 1.1 ± 0.3 (0.09 ± 0.03) | 1,158 ± 10 | 1.2 ± 0.1 | 0 ± 0 % | 0 ± 0 % | $1.80 ± 0.01 | $-5.75 ± 0.08 | 52.0 ± 2.1 |
| Small: the genesis and 4 active | fixed k = 3, bounties to $625 | 8.3 ± 0.8 (0.73 ± 0.07) | 1,142 ± 10 | 1.8 ± 0.2 | 1 ± 0 % | 0 ± 0 % | $0.95 ± 0.01 | $-6.21 ± 0.08 | 51.3 ± 1.9 |
| Grown: the genesis and 20 active | k table (v3) | 0.9 ± 0.3 (0.07 ± 0.03) | 1,160 ± 10 | 0.4 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $1.81 ± 0.01 | $-6.95 ± 0.06 | 46.1 ± 1.6 |
| Grown: the genesis and 20 active | fixed k = 3, bounties to $625 | 7.8 ± 1.0 (0.68 ± 0.09) | 1,143 ± 10 | 1.1 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $0.89 ± 0.01 | $-7.44 ± 0.07 | 46.1 ± 1.6 |

Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with three validators, a 24-hour window and a challenge panel of 5. "–": nothing to measure (no verdict became final, or nothing was paid).

### Proof levels

#### Panels by proof level (40 seeds; a year; 30 submissions a week)

| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C | Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth, all level A | 21 % ± 3 | 16 % ± 3 | 0 % ± 0 | 1,298 ± 52 | 100 % / 0 % / 0 % | 2.1 / – / – | 0.22 ± 0.05 | $559 | 48.0 ± 2.1 |
| Growth at launch: genesis A, newcomers ⅓ A, ⅓ B, ⅓ C, **the C third refused (level C off)** | 31 % ± 4 | 26 % ± 4 | 2 % ± 1 | 1,144 ± 65 | 70 % / 30 % / 0 % | 3.1 / 2.2 / – | 0.16 ± 0.05 | $488 | 32.8 ± 1.6 |
| Growth at launch, the same with 10 % hidden-test bounties | 31 % ± 4 | 26 % ± 4 | 2 % ± 1 | 1,144 ± 65 | 70 % / 30 % / 0 % | 3.1 / 2.1 / – | 0.16 ± 0.05 | $488 | 32.8 ± 1.6 |
| Grown, after C is switched on by ADR: 21 active, ⅓ A, ⅓ B, ⅓ C | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,536 ± 13 | 20 % / 64 % / 16 % | 0.5 / 0.7 / 1.1 | 0.08 ± 0.03 | $625 | 46.2 ± 1.6 |
| Grown, after C is switched on by ADR: the same with 10 % hidden-test bounties | 1 % ± 0 | 1 % ± 0 | 1 % ± 0 | 1,537 ± 13 | 24 % / 62 % / 14 % | 0.5 / 0.7 / 1.1 | 0.08 ± 0.03 | $625 | 46.1 ± 1.6 |
| Grown, after C is switched on by ADR: the genesis at A, 20 active at C | 4 % ± 0 | 4 % ± 0 | 4 % ± 0 | 1,494 ± 12 | 0 % / 0 % / 100 % | – / – / 1.1 | 0.01 ± 0.01 | $250 | 46.2 ± 1.6 |
| Growth, ordinary PCs only (genesis at C, even with C accepted) | refused at deployment: a level C genesis validator; the genesis must be at level A or B | | | | | | | | |

| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, replacement or shadow; all runs) |
|---|---|---|---|
| Growth at launch, the same with 10 % hidden-test bounties | 31 % ± 4 | 26 % ± 4 | 0 |
| Grown, after C is switched on by ADR: the same with 10 % hidden-test bounties | 1 % ± 0 | 0 % ± 0 | 0 |

#### Each proof-level attacker against its honest twin (40 seeds; a year; returns in $)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | #134's return − twin's (v1) | What it got |
|---|---|---|---|---|---|---|
| Test liar: the genesis at C, 5 bad fixes a week (even with C accepted) | refused at deployment | – | – | – | 165 ± 13 | a level C genesis validator; the genesis must be at level A or B |
| Test liar, after C is switched on by ADR: 1 of 15, every other validator at C but the genesis (A); 2 bad fixes a week | -4,810 ± 505 | loses | -4,870 | -61 | -899 ± 102 | 0.1 bad fixes paid of 101 (largest $12); 27.9 lies: 11.5 challenged, 8.8 proven by re-runs (32 %), 0.8 reversed, 0.0 still frozen at year's end; slashed $4425 |
| Test liar: the same, `C_LIMIT_X` 0.5 (level C's limits halved) | -4,310 ± 484 | loses | -4,376 | -66 | – | 0.1 bad fixes paid of 101 (largest $13); 26.6 lies: 10.7 challenged, 7.9 proven by re-runs (30 %), 0.6 reversed, 0.0 still frozen at year's end; slashed $3950 |
| Answer shopper: the genesis at C (even with C accepted) | refused at deployment | – | – | – | 301 ± 28 | a level C genesis validator; the genesis must be at level A or B |
| **Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes)** | -13 ± 1 | loses | -250 | -237 | -2 ± 14 | 10.1 verdicts flipped of 31.1 shopped (101 extra calls); outweighed by the other judges 9.9, reversed 0.1, paid 0.0; bad fixes paid 0.0 of 101 (twin 0.0); agreement with final outcomes 88.4 % (twin 90.4 %) |
| Answer shopper: the same at 3 in 10 (the trust point; twin: calls once, same fixes) | +174 ± 46 | **wins** | 470 | 296 | 328 ± 69 | 17.4 verdicts flipped of 31.1 shopped (68 extra calls); outweighed by the other judges 12.8, reversed 3.3, paid 1.5; bad fixes paid 7.1 of 101 (twin 5.4); agreement with final outcomes 86.2 % (twin 89.3 %) |
| Answer shopper: 3 in 10 (twin: no fixes) | +531 ± 107 | **wins** | 470 | -61 | 1,209 ± 144 | 17.4 verdicts flipped of 31.1 shopped (68 extra calls); outweighed by the other judges 12.8, reversed 3.3, paid 1.5; bad fixes paid 7.1 of 101 (twin 0.0); agreement with final outcomes 86.2 % (twin 90.2 %) |
| Answer shopper: 1 in 10, `C_LIMIT_X` 0.5 (level C's limits halved) | -12 ± 1 | loses | -254 | -242 | – | 9.5 verdicts flipped of 29.4 shopped (96 extra calls); outweighed by the other judges 9.3, reversed 0.2, paid 0.0; bad fixes paid 0.0 of 101 (twin 0.0); agreement with final outcomes 87.5 % (twin 90.0 %) |
| Answer shopper: 3 in 10, `C_LIMIT_X` 0.5 (level C's limits halved) | +157 ± 47 | **wins** | 409 | 253 | – | 16.6 verdicts flipped of 29.6 shopped (65 extra calls); outweighed by the other judges 12.3, reversed 2.7, paid 1.7; bad fixes paid 7.8 of 101 (twin 5.9); agreement with final outcomes 84.8 % (twin 88.6 %) |
| Chip breaker at launch: the genesis at B ($25 at k = 1, 336 h), forging on half its bad-fix draws, $1,000 device | -1,520 ± 64 | loses | -1,577 | -57 | -102 ± 40 | 20.2 forged of 103 draws (20 %); own bad fixes paid 1.2 of 25, bribed ones 0.3 (bribes $7); largest bounty paid $21; 10.7 challenged, 53 % of forgeries proven by re-runs, 0.0 still frozen; slashed $508 |
| Chip breaker at launch: the same, a $50 device | -570 ± 64 | loses | -627 | -57 | 848 ± 40 | 20.2 forged of 103 draws (20 %); own bad fixes paid 1.2 of 25, bribed ones 0.3 (bribes $7); largest bounty paid $21; 10.7 challenged, 53 % of forgeries proven by re-runs, 0.0 still frozen; slashed $508 |
| Chip breaker at launch: 1 of a grown network (⅓ A, ⅓ B; the ⅓ at C refused), a $50 device | -13,873 ± 1,579 | loses | -13,965 | -92 | -3,220 ± 341 | 112.4 forged of 709 draws (16 %); own bad fixes paid 0.9 of 101, bribed ones 1.2 (bribes $66); largest bounty paid $134; 7.3 challenged, 13 % of forgeries proven by re-runs, 1.6 still frozen; slashed $13156 |
| Chip breaker at launch: the same, forging on every bad-fix draw | -21,352 ± 2,153 | loses | -21,444 | -92 | -5,525 ± 449 | 187.6 forged of 705 draws (27 %); own bad fixes paid 0.9 of 101, bribed ones 2.4 (bribes $133); largest bounty paid $175; 7.3 challenged, 13 % of forgeries proven by re-runs, 1.6 still frozen; slashed $20344 |
| Chip breaker, after C is switched on by ADR: 1 of 15 (⅓ A, ⅓ B, ⅓ C), a $50 device | -19,766 ± 1,636 | loses | -19,866 | -99 | – | 79.2 forged of 490 draws (16 %); own bad fixes paid 0.5 of 101, bribed ones 0.8 (bribes $38); largest bounty paid $80; 6.9 challenged, 19 % of forgeries proven by re-runs, 0.0 still frozen; slashed $18688 |

#### Level C at launch: off (owner decision 2026-11-03, spec PR pending; the default) against the merged design, C accepted from genesis (40 seeds; a year)

| Network | Newcomers joined (refused at C) | Qualified / days | Runs reaching k ≥ 3 / first week | Submissions that waited / withdrawn | Days from a k = 1 verdict to payment (median a run) | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|
| Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C: **level C off at launch (the default)**, the C third refused | 35.7 (18.1) | 34.4 ± 1.7 / 12 ± 1 | 40 of 40 / week 7 ± 1 | 31 ± 4 % / 26 ± 4 % | 23.2 ± 5.3 | 0.16 ± 0.05 | $497 | 32.8 ± 1.6 |
| Growth, the same: **level C accepted from genesis (the merged design)** | 53.8 (0.0) | 51.1 ± 2.1 / 15 ± 1 | 40 of 40 / week 6 ± 1 | 22 ± 3 % / 18 ± 3 % | 23.6 ± 4.3 | 0.11 ± 0.04 | $447 | 48.1 ± 2.1 |
| Grown: 21 validators ⅓ A, ⅓ B, ⅓ C: **level C off** (the 7 at C never registered) | 18.3 (15.8) | 18.0 ± 1.2 / 7 ± 0 | 40 of 40 / week 0 ± 0 | 1 ± 0 % / 0 ± 0 % | – | 0.08 ± 0.02 | $625 | 30.9 ± 1.3 |
| Grown: the same: **level C accepted** | 27.4 (0.0) | 27.1 ± 1.7 / 9 ± 1 | 40 of 40 / week 0 ± 0 | 1 ± 0 % / 1 ± 0 % | – | 0.08 ± 0.03 | $625 | 46.2 ± 1.6 |

| Attacker | Level C off at launch (the default): return − twin's ($) | | Level C accepted (from genesis, or after the ADR for the grown network's rows): return − twin's ($) | |
|---|---|---|---|---|
| Colluding genesis (A, $100), newcomers ⅓ each | -266 ± 44 | loses | -264 ± 44 | loses |
| Chip breaker: the genesis at B, $50 device, newcomers ⅓ each | -570 ± 64 | loses | -576 ± 64 | loses |
| Test liar: 1 of 15 at C | refused: it can't register | – | -4,810 ± 505 | loses |
| Answer shopper: 1 of 15 at C, 1 in 10 | refused: it can't register | – | -13 ± 1 | loses |
| Answer shopper: 1 of 15 at C, 3 in 10 | refused: it can't register | – | +174 ± 46 | **wins** |

### Market pricing

#### The fee finds the validators' cost (40 seeds; a year; 20 honest validators and the genesis at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the ceiling unless stated)

| Variant | Fee at week 4 / 13 / 26 / 52 | Fee over the last 13 weeks | Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | Runs collapsed (< 3 active) | Honest validator's month |
|---|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)** | $0.127 / $0.070 / $0.054 / $0.055 | $0.050 ± 0.009 | $0.012 ± 0.000 | $0.623 ± 0.635 | 1.9 ± 0.7 | 15 % ± 2 | 88 % ± 9 | 33 of 40 | $-6.81 ± 0.99 |
| `IDLE_HIGH` 30 % | $0.095 / $0.032 / $0.043 / $0.076 | $0.067 ± 0.014 | $– | $– | 1.0 ± 0.0 | 18 % ± 1 | 100 % ± 0 | 40 of 40 | $-9.55 ± 0.93 |
| `IDLE_HIGH` 50 % | $0.179 / $0.129 / $0.099 / $0.081 | $0.083 ± 0.010 | $0.012 ± 0.000 | $0.274 ± 0.346 | 7.6 ± 1.5 | 6 % ± 3 | 39 % ± 13 | 12 of 40 | $-2.94 ± 0.58 |
| idling over 7 days (`IDLE_WINDOW_DAYS` 7) | $0.240 / $0.240 / $0.240 / $0.240 | $0.240 ± 0.004 | $0.012 ± 0.000 | $0.201 ± 0.006 | 25.5 ± 0.7 | 0 % ± 0 | 0 % ± 0 | 0 of 40 | $-0.48 ± 0.14 |
| waits a newcomer of any bond could end | $0.159 / $0.152 / $0.151 / $0.115 | $0.123 ± 0.009 | $0.012 ± 0.000 | $0.116 ± 0.009 | 12.4 ± 1.2 | 2 % ± 1 | 17 % ± 5 | 1 of 40 | $-2.09 ± 0.31 |
| every wait counts (#134's signal) | $0.166 / $0.177 / $0.186 / $0.191 | $0.186 ± 0.008 | $0.012 ± 0.000 | $0.154 ± 0.007 | 18.6 ± 0.7 | 4 % ± 0 | 23 % ± 1 | 0 of 40 | $-1.15 ± 0.24 |
| `FEE_STEP_UP` 10 % | $0.127 / $0.075 / $0.118 / $0.201 | $0.182 ± 0.022 | $0.012 ± 0.000 | $0.822 ± 0.985 | 2.3 ± 0.9 | 15 % ± 2 | 85 % ± 10 | 32 of 40 | $-6.71 ± 0.97 |
| the design, 100 submissions a week | $0.236 / $0.232 / $0.227 / $0.172 | $0.186 ± 0.006 | $0.012 ± 0.000 | $0.145 ± 0.004 | 60.0 ± 1.4 | 0 % ± 0 | 20 % ± 1 | 0 of 40 | $4.96 ± 0.30 |
| the design, starting at v2's $0.05 | $0.026 / $0.015 / $0.025 / $0.051 | $0.043 ± 0.011 | $– | $– | 1.0 ± 0.0 | 18 % ± 1 | 100 % ± 0 | 40 of 40 | $-13.54 ± 1.13 |
| #134's rules (v1) | $0.248 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.096 ± 0.003 | $0.251 ± 0.006 | 18.2 ± 0.4 | 22 % ± 2 | 29 % ± 1 | 0 of 40 | $-2.65 ± 0.51 |

Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every row, so the fee is the validator's whole margin.

##### The fee against break-even, D17's `FEE_MARGIN` (40 seeds; the runs that didn't collapse)

| Variant | Fee / break-even over the last 13 weeks (± 2 SE) | Within [1 − `FEE_STEP`, 1 + `FEE_MARGIN`] | Runs collapsed |
|---|---|---|---|
| **#141's rules (the design)** | 0.47 ± 0.40 × | no | 33 of 40 |
| `IDLE_HIGH` 30 % | – | no | 40 of 40 |
| `IDLE_HIGH` 50 % | 0.99 ± 0.10 × | no | 12 of 40 |
| idling over 7 days (`IDLE_WINDOW_DAYS` 7) | 1.20 ± 0.03 × | yes | 0 of 40 |
| waits a newcomer of any bond could end | 1.08 ± 0.07 × | no | 1 of 40 |
| every wait counts (#134's signal) | 1.21 ± 0.04 × | yes | 0 of 40 |
| `FEE_STEP_UP` 10 % | 0.62 ± 0.36 × | no | 32 of 40 |
| the design, 100 submissions a week | 1.28 ± 0.03 × | no | 0 of 40 |
| the design, starting at v2's $0.05 | – | no | 40 of 40 |
| #134's rules (v1) | 1.00 ± 0.02 × | yes | 0 of 40 |

##### An honest validator's month on the market (40 seeds; honest validators active a month or more; $ a month)

| Market and outages | Service fees | Usage margin | Node overhead | Slashes | Fixed costs | The bond's capital | Net | Runs with such validators |
|---|---|---|---|---|---|---|---|---|
| the design: outages before the seal (silence, not slashed) | $5.25 ± 0.29 | $0.03 ± 0.02 | $0.55 ± 0.03 | $0.00 ± 0.00 | $4.67 ± 0.00 | $6.87 ± 0.89 | $-6.81 ± 0.99 | 40 |
| the design: every outage after the seal ($1) | $5.32 ± 0.29 | $0.02 ± 0.02 | $0.55 ± 0.03 | $0.21 ± 0.02 | $4.67 ± 0.00 | $7.27 ± 0.89 | $-7.35 ± 0.97 | 40 |
| waits a newcomer of any bond could end: outages before the seal | $6.57 ± 0.17 | $0.03 ± 0.01 | $0.59 ± 0.02 | $0.00 ± 0.00 | $4.67 ± 0.00 | $3.42 ± 0.29 | $-2.09 ± 0.31 | 40 |
| waits a newcomer of any bond could end: after the seal, $0.50 | $6.84 ± 0.17 | $0.03 ± 0.01 | $0.61 ± 0.02 | $0.11 ± 0.01 | $4.67 ± 0.00 | $3.45 ± 0.33 | $-1.96 ± 0.36 | 40 |
| waits a newcomer of any bond could end: after the seal, $1 | $6.91 ± 0.19 | $0.03 ± 0.01 | $0.60 ± 0.02 | $0.22 ± 0.02 | $4.67 ± 0.00 | $3.26 ± 0.24 | $-1.82 ± 0.26 | 40 |
| waits a newcomer of any bond could end: after the seal, $5 | $7.39 ± 0.34 | $0.03 ± 0.01 | $0.59 ± 0.03 | $1.11 ± 0.09 | $4.67 ± 0.00 | $3.97 ± 0.59 | $-2.92 ± 0.80 | 40 |
| #134's rules (v1) | $8.60 ± 0.23 | $-0.02 ± 0.01 | $0.46 ± 0.01 | $4.34 ± 0.51 | $4.67 ± 0.00 | $1.76 ± 0.07 | $-2.65 ± 0.51 | 40 |

#134: the honest validator's month on the market $-2.65 ± 0.51 $ (the fee at its ceiling), and −$8.01 on the growing network, $2.05 of it outage slashes.

#### The fee over the year: the design's values (#141) (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.180 ± 0.006 | 21.7 ± 0.1 | 0 % ± 0 | 40 % ± 2 |
| 5–8 | $0.101 ± 0.008 | 16.5 ± 0.7 | 0 % ± 0 | 31 % ± 2 |
| 9–12 | $0.078 ± 0.011 | 7.1 ± 1.2 | 2 % ± 1 | 32 % ± 9 |
| 13–16 | $0.068 ± 0.011 | 6.4 ± 1.4 | 6 % ± 3 | 43 % ± 13 |
| 17–20 | $0.063 ± 0.010 | 5.6 ± 1.3 | 7 % ± 3 | 49 % ± 14 |
| 21–24 | $0.059 ± 0.010 | 5.0 ± 1.3 | 8 % ± 3 | 54 % ± 14 |
| 25–28 | $0.054 ± 0.009 | 4.2 ± 1.3 | 9 % ± 3 | 60 % ± 14 |
| 29–32 | $0.051 ± 0.009 | 3.6 ± 1.1 | 10 % ± 3 | 67 % ± 13 |
| 33–36 | $0.047 ± 0.009 | 2.8 ± 0.9 | 11 % ± 3 | 73 % ± 12 |
| 37–40 | $0.046 ± 0.009 | 2.3 ± 0.8 | 14 % ± 3 | 80 % ± 11 |
| 41–44 | $0.048 ± 0.009 | 2.2 ± 0.9 | 15 % ± 3 | 85 % ± 10 |
| 45–48 | $0.050 ± 0.010 | 1.8 ± 0.7 | 15 % ± 2 | 88 % ± 9 |
| 49–52 | $0.052 ± 0.011 | 1.7 ± 0.7 | 16 % ± 2 | 92 % ± 8 |

#### The fee over the year: waits a newcomer of any bond could end (40 seeds; means over each 4-week span)

| Weeks | Service fee | Active validators | Submissions that waited | Validators idle |
|---|---|---|---|---|
| 1–4 | $0.197 ± 0.008 | 21.7 ± 0.1 | 4 % ± 2 | 40 % ± 2 |
| 5–8 | $0.140 ± 0.013 | 18.3 ± 0.9 | 4 % ± 2 | 31 % ± 2 |
| 9–12 | $0.144 ± 0.012 | 12.8 ± 1.3 | 9 % ± 6 | 23 % ± 6 |
| 13–16 | $0.152 ± 0.015 | 13.5 ± 1.4 | 6 % ± 5 | 21 % ± 5 |
| 17–20 | $0.153 ± 0.016 | 14.1 ± 1.5 | 4 % ± 3 | 18 % ± 4 |
| 21–24 | $0.149 ± 0.014 | 14.3 ± 1.5 | 5 % ± 3 | 20 % ± 3 |
| 25–28 | $0.150 ± 0.015 | 13.9 ± 1.2 | 5 % ± 3 | 19 % ± 3 |
| 29–32 | $0.146 ± 0.016 | 14.3 ± 1.2 | 3 % ± 2 | 18 % ± 3 |
| 33–36 | $0.138 ± 0.015 | 14.1 ± 1.5 | 2 % ± 1 | 18 % ± 3 |
| 37–40 | $0.134 ± 0.014 | 13.2 ± 1.5 | 3 % ± 1 | 18 % ± 5 |
| 41–44 | $0.129 ± 0.012 | 12.9 ± 1.4 | 2 % ± 1 | 17 % ± 5 |
| 45–48 | $0.122 ± 0.009 | 12.5 ± 1.2 | 2 % ± 1 | 17 % ± 5 |
| 49–52 | $0.115 ± 0.008 | 11.7 ± 1.0 | 3 % ± 2 | 16 % ± 5 |

#### A provider halves its price (40 seeds; Anthropic's input-token price at the end of each day, as a multiple of its value at deployment; its validators post their new costs on day 30)

| End of day | 29 | 30 | 31 | 32 | 33 | 34 | 35 |
|---|---|---|---|---|---|---|---|
| Unit price | 1.000 | 0.750 | 0.562 | 0.500 | 0.500 | 0.500 | 0.500 |

One `PRICE_STEP_MAX` step (−25 %) a day until it reaches the median of the new tables (half the old median), with no proposal or vote.

#### The pricing attackers against their honest twins (40 seeds; a year; returns in $)

| Attacker | Market | Return − twin's ($, ± 2 SE) | Against its twin | Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's / twin's | Active validators (last 13 weeks) | #134 (v1, design) | What it did |
|---|---|---|---|---|---|---|---|---|
| Cartel: 6 validators refusing half their draws | design | -488 ± 17 | loses | $0.068 / $0.084 | 1.00 / 1.00 | 4.4 | -5,460 ± 335 | 875 refusals, suspended 126 times, slashed $0 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | design | -603 ± 10 | loses | $0.080 / $0.080 | 1.00 / 1.00 | 6.0 | -608 ± 19 | 353 spam submissions costing its solver $603 |
| Spammer: a bad fix a day, judged | design | -548 ± 50 | loses | $0.114 / $0.080 | 1.00 / 1.00 | 12.6 | -960 ± 43 | 364 spam submissions costing its solver $759 |
| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs | design | +33 ± 4 | **wins** | $0.043 / $0.043 | 1.31 / 1.00 | 6.0 | 42 ± 22 | usage margin $32 (twin: $-1) |
| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) | design | +28 ± 4 | **wins** | $0.060 / $0.060 | 1.27 / 1.00 | 6.2 | 48 ± 28 | usage margin $27 (twin: $-1) |
| Fee farmer: 10 idle validators at the bond floor (twin: one) | design | -548 ± 1 | loses | $0.036 / $0.053 | 1.00 / 1.00 | 11.0 | -435 ± 9 | service fees $24 (twin: $4) |
| Cartel: 6 validators refusing half their draws | any-bond wait signal | -503 ± 11 | loses | $0.171 / $0.100 | 1.00 / 1.00 | 13.6 |  | 285 refusals, suspended 47 times, slashed $0 |
| Spammer: a fix a day to a $625 bounty no panel can judge yet | any-bond wait signal | -463 ± 89 | loses | $0.177 / $0.126 | 1.00 / 1.00 | 17.6 |  | 297 spam submissions costing its solver $574 |
| Spammer: a bad fix a day, judged | any-bond wait signal | -740 ± 30 | loses | $0.145 / $0.126 | 1.00 / 1.00 | 15.4 |  | 364 spam submissions costing its solver $840 |
| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs | any-bond wait signal | -1 ± 7 | not significant | $0.152 / $0.155 | 1.00 / 1.00 | 13.8 |  | usage margin $-1 (twin: $-2) |
| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) | any-bond wait signal | -0 ± 3 | not significant | $0.177 / $0.178 | 1.00 / 1.00 | 13.9 |  | usage margin $-1 (twin: $-2) |
| Fee farmer: 10 idle validators at the bond floor (twin: one) | any-bond wait signal | -490 ± 17 | loses | $0.102 / $0.145 | 1.00 / 1.00 | 14.1 |  | service fees $89 (twin: $16) |

### Model scores

#### The families' scores under #141's rules (40 seeds; at the year's end)

| Family | True accuracy (assumed) | Score (counted verdicts) | Fee factor (normalised) | Share of the year barred | Times barred / recovered |
|---|---|---|---|---|---|
| `top` | 95 % | 93.8 ± 0.6 % | 1.17 ± 0.02 × | 0 ± 0 % | 0.0 / 0.0 |
| `mid` | 90 % | 88.3 ± 0.8 % | 0.98 ± 0.03 × | 0 ± 0 % | 0.0 / 0.0 |
| `low` | 85 % | 83.7 ± 0.9 % | 0.82 ± 0.02 × | 0 ± 0 % | 0.0 / 0.0 |
| `weak` | 68 % | 66.6 ± 6.0 % | 0.50 ± 0.00 × | 58 ± 3 % | 11.3 / 10.8 |

#### One vote, pay by score, weighted votes (40 seeds; a year)

| Families | Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | Service fees per submission ($) | `top` net a month ($) | `mid` net a month ($) | `low` net a month ($) | `weak` net a month ($) |
|---|---|---|---|---|---|---|---|---|---|
| blind spots | One vote, no scores | 1.49 ± 0.14 | 0.86 ± 0.10 | 5.85 ± 0.27 | 0.363 ± 0.001 | -6.84 ± 0.15 | -6.68 ± 0.13 | -6.69 ± 0.12 | -6.97 ± 0.16 |
| blind spots | **One vote, pay by score (#141: counted-only scores, the normalised factor)** | 1.33 ± 0.11 | 0.51 ± 0.07 | 4.49 ± 0.14 | 0.354 ± 0.001 | -6.41 ± 0.13 | -6.49 ± 0.12 | -6.73 ± 0.12 | -7.96 ± 0.19 |
| blind spots | One vote, pay by score, the factor's 1 × at the median family score | 1.33 ± 0.11 | 0.51 ± 0.07 | 4.49 ± 0.14 | 0.380 ± 0.002 | -6.18 ± 0.13 | -6.36 ± 0.12 | -6.71 ± 0.12 | -7.97 ± 0.19 |
| blind spots | One vote, pay by score, `SCORE_BALANCED` | 1.30 ± 0.12 | 0.54 ± 0.08 | 4.51 ± 0.17 | 0.353 ± 0.001 | -6.43 ± 0.15 | -6.50 ± 0.12 | -6.75 ± 0.13 | -7.97 ± 0.18 |
| blind spots | Votes weighted by the score factor | 1.38 ± 0.11 | 0.40 ± 0.06 | 4.45 ± 0.14 | 0.353 ± 0.001 | -6.41 ± 0.13 | -6.49 ± 0.12 | -6.76 ± 0.12 | -8.04 ± 0.17 |
| blind spots | One vote, pay by score, #134's scores (shadows merged, neutral at 80 %) | 1.26 ± 0.12 | 0.44 ± 0.07 | 4.00 ± 0.16 | 0.499 ± 0.003 | -14.27 ± 0.81 | -14.20 ± 1.03 | -15.05 ± 0.96 | -10.07 ± 0.65 |
| no blind spots | One vote, no scores | 0.29 ± 0.05 | 0.89 ± 0.11 | 4.09 ± 0.23 | 0.363 ± 0.000 | -6.84 ± 0.15 | -6.68 ± 0.13 | -6.66 ± 0.12 | -6.89 ± 0.16 |
| no blind spots | **One vote, pay by score (#141: counted-only scores, the normalised factor)** | 0.18 ± 0.03 | 0.53 ± 0.07 | 2.62 ± 0.13 | 0.353 ± 0.001 | -6.42 ± 0.13 | -6.47 ± 0.12 | -6.72 ± 0.12 | -7.93 ± 0.22 |
| no blind spots | One vote, pay by score, the factor's 1 × at the median family score | 0.18 ± 0.03 | 0.53 ± 0.07 | 2.62 ± 0.13 | 0.377 ± 0.002 | -6.19 ± 0.13 | -6.35 ± 0.12 | -6.72 ± 0.12 | -7.93 ± 0.22 |
| no blind spots | One vote, pay by score, `SCORE_BALANCED` | 0.17 ± 0.03 | 0.54 ± 0.08 | 2.66 ± 0.15 | 0.353 ± 0.001 | -6.43 ± 0.14 | -6.47 ± 0.12 | -6.73 ± 0.12 | -7.90 ± 0.20 |
| no blind spots | Votes weighted by the score factor | 0.13 ± 0.03 | 0.42 ± 0.06 | 2.58 ± 0.12 | 0.352 ± 0.001 | -6.42 ± 0.13 | -6.47 ± 0.12 | -6.73 ± 0.12 | -7.94 ± 0.22 |
| no blind spots | One vote, pay by score, #134's scores (shadows merged, neutral at 80 %) | 0.13 ± 0.03 | 0.40 ± 0.06 | 2.12 ± 0.16 | 0.512 ± 0.003 | -14.37 ± 0.92 | -14.35 ± 1.12 | -14.79 ± 0.95 | -10.14 ± 0.62 |

#134: service fees per submission 0.499 ± 0.003 with pay by score against 0.358 ± 0.000 without (+39 %).

#### Everyone moves to the top model (40 seeds; a year; every validator reconsiders monthly and changes to the family paying most per head when it pays 10 % more)

| | Nobody moves | Everyone moves, registering again (#141) | Everyone moves at once (#134's reading) |
|---|---|---|---|
| Share of drawable validators in `top` at the year's end | 29 ± 2 % | 41 ± 3 % | 36 ± 6 % |
| Share of drawable validators in `mid` at the year's end | 25 ± 2 % | 29 ± 3 % | 32 ± 6 % |
| Share of drawable validators in `low` at the year's end | 25 ± 1 % | 27 ± 4 % | 28 ± 6 % |
| Share of drawable validators in `weak` at the year's end | 21 ± 2 % | 2 ± 1 % | 4 ± 3 % |
| Families with at least 10 % of the validators | 4.0 ± 0.0 | 3.0 ± 0.1 | 2.9 ± 0.1 |
| Share of counted seats held by `top` | 32.4 ± 0.7 % | 36.3 ± 1.2 % | 35.7 ± 0.9 % |
| Panels with more of one family than the cap allows | 0 ± 0 | 0 ± 0 | 0 ± 0 |
| Draws whose k the caps lowered | 0.0 ± 0.0 % | 14.6 ± 2.7 % | 8.0 ± 2.1 % |
| **Submissions that waited for a panel** (`WAIT_CROWD_MAX` 15 %) | 0.0 ± 0.0 % | 7.9 ± 2.4 % | 9.2 ± 3.4 % |
| Bad fixes merged per 100 paid | 1.33 ± 0.11 | 1.32 ± 0.10 | 1.39 ± 0.11 |
| Family changes in the year | 0 ± 0 | 56 ± 3 | 110 ± 6 |
| An activated validator's net per month ($) | -6.79 ± 0.07 | -4.32 ± 0.12 | -6.85 ± 0.09 |

Four validators starting in `low` that move (registering again) against the same four staying: return − twin's **-25 ± 7** $ a year (loses). #134 (moving at once): crowding 11.6 ± 5.5 % of submissions waited.

#### Herding (40 seeds; a year; 4 herders of one family among 16 honest validators; each votes pass, the public base rate's majority)

| Herders | Their agreement with outcomes (twin's) | ...balanced over passed and failed outcomes | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Return − twin's ($, ± 2 SE) | Herding | #134 (v1) |
|---|---|---|---|---|---|---|---|---|
| `mid` (90 %), receipts detectable | 78.7 ± 0.5 % (89.2 ± 0.3 %) | 50.0 ± 0.0 % (88.5 ± 0.4 %) | 84.5 ± 1.1 % (88.3 ± 0.8 %) | 3 ± 3 % (0 ± 0 %) | 3.32 ± 0.19 (1.28 ± 0.11) | -82,767 ± 5,385 | loses | -12,782 ± 828 |
| `mid` (90 %), not detectable (upper bound) | 78.6 ± 0.5 % (89.2 ± 0.3 %) | 50.0 ± 0.0 % (88.5 ± 0.4 %) | 84.4 ± 1.0 % (88.3 ± 0.8 %) | 3 ± 3 % (0 ± 0 %) | 3.39 ± 0.20 (1.28 ± 0.11) | -10 ± 2 | loses | -11 ± 31 |
| `weak` (68 %), receipts detectable | 78.3 ± 0.5 % (68.6 ± 0.7 %) | 50.1 ± 0.1 % (68.3 ± 0.8 %) | 71.5 ± 1.3 % (69.3 ± 3.5 %) | 30 ± 3 % (61 ± 2 %) | 2.68 ± 0.19 (1.39 ± 0.11) | -79,203 ± 5,111 | loses | -10,533 ± 1,144 |
| `weak` (68 %), not detectable (upper bound) | 78.5 ± 0.5 % (68.6 ± 0.7 %) | 50.1 ± 0.1 % (68.3 ± 0.8 %) | 71.3 ± 1.8 % (69.3 ± 3.5 %) | 31 ± 3 % (61 ± 2 %) | 2.69 ± 0.19 (1.39 ± 0.11) | +13 ± 2 | **wins** | -191 ± 53 |
| `mid`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 78.6 ± 0.5 % (89.2 ± 0.3 %) | 50.0 ± 0.0 % (88.5 ± 0.4 %) | 84.4 ± 1.0 % (88.3 ± 0.8 %) | 3 ± 3 % (0 ± 0 %) | 3.39 ± 0.20 (1.28 ± 0.11) | -54 ± 11 | loses | -95 ± 30 |
| `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) | 78.5 ± 0.5 % (68.6 ± 0.7 %) | 50.1 ± 0.1 % (68.3 ± 0.8 %) | 71.3 ± 1.8 % (69.3 ± 3.5 %) | 31 ± 3 % (61 ± 2 %) | 2.69 ± 0.19 (1.39 ± 0.11) | +80 ± 9 | **wins** | -81 ± 49 |
| `mid`, not detectable, `SCORE_BALANCED` | 77.9 ± 0.9 % (89.2 ± 0.3 %) | 50.0 ± 0.1 % (88.4 ± 0.4 %) | 72.1 ± 2.0 % (87.1 ± 1.1 %) | 77 ± 5 % (1 ± 2 %) | 2.35 ± 0.26 (1.28 ± 0.12) | -57 ± 4 | loses | – |
| `weak`, not detectable, `SCORE_BALANCED` | 78.2 ± 1.3 % (68.7 ± 0.7 %) | 50.6 ± 1.0 % (68.2 ± 0.8 %) | 62.1 ± 2.5 % (67.8 ± 2.7 %) | 87 ± 1 % (63 ± 3 %) | 1.43 ± 0.11 (1.34 ± 0.09) | -8 ± 1 | loses | – |
| `weak`, not detectable, $0.25, `SCORE_BALANCED` | 78.2 ± 1.3 % (68.7 ± 0.7 %) | 50.6 ± 1.0 % (68.2 ± 0.8 %) | 62.1 ± 2.5 % (67.8 ± 2.7 %) | 87 ± 1 % (63 ± 3 %) | 1.43 ± 0.11 (1.34 ± 0.09) | -54 ± 6 | loses | – |

#### Scores on the market fee (40 seeds; a year; the score families' accuracies and blind spots; the market's 20 initial validators, five per family, and 2 prospects a week)

| Market | Rule | Mean service fee | Active validators (last 13 weeks) | Bad fixes merged per 100 paid | `top` validator's net per month | `mid` validator's net per month | `low` validator's net per month | `weak` validator's net per month |
|---|---|---|---|---|---|---|---|---|
| design | One vote, no scores | $0.069 ± 0.007 | 1.9 ± 0.8 | 1.46 ± 0.23 | $-1.89 ± 0.18 | $-1.08 ± 0.16 | $-1.16 ± 0.17 | $-1.12 ± 0.18 |
| design | **One vote, pay by score (v3's design)** | $0.056 ± 0.007 | 1.1 ± 0.1 | 1.30 ± 0.25 | $-2.16 ± 0.16 | $-1.31 ± 0.20 | $-1.29 ± 0.17 | $-1.31 ± 0.17 |
| any-bond wait signal | One vote, no scores | $0.152 ± 0.008 | 12.8 ± 0.9 | 1.57 ± 0.11 | $-0.50 ± 0.18 | $-0.31 ± 0.16 | $-0.41 ± 0.15 | $-0.53 ± 0.21 |
| any-bond wait signal | **One vote, pay by score (v3's design)** | $0.171 ± 0.010 | 14.0 ± 1.6 | 1.25 ± 0.15 | $0.41 ± 0.28 | $0.19 ± 0.21 | $-0.48 ± 0.19 | $-2.90 ± 0.25 |
| any-bond wait signal, the factor's 1 × at the median score | One vote, no scores | $0.152 ± 0.008 | 12.8 ± 0.9 | 1.57 ± 0.11 | $-0.50 ± 0.18 | $-0.31 ± 0.16 | $-0.41 ± 0.15 | $-0.53 ± 0.21 |
| any-bond wait signal, the factor's 1 × at the median score | **One vote, pay by score (v3's design)** | $0.171 ± 0.010 | 14.0 ± 1.6 | 1.25 ± 0.15 | $1.02 ± 0.33 | $0.52 ± 0.23 | $-0.45 ± 0.20 | $-2.92 ± 0.26 |

Market "design": #141's rules, the fee starting at the ceiling (it collapses in most runs, see the pricing section). "any-bond wait signal": the switch under which it doesn't. The families are priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight model). Prospects decide to enter on the unscaled fee.

#### Herding on the market fee (40 seeds; a year; 4 undetectable herders of one family beside the market's validators)

| Herders | Their agreement (twin's) | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Mean fee | Return − twin's ($, ± 2 SE) | Herding | #134 (v1) |
|---|---|---|---|---|---|---|---|---|
| `mid` (90 %), not detectable, market at the design's values | 83.2 ± 2.3 % (92.6 ± 0.4 %) | 88.8 ± 1.8 % (95.9 ± 0.5 %) | 5 ± 7 % (0 ± 0 %) | 4.12 ± 0.42 (0.80 ± 0.15) | $0.032 | -5 ± 4 | loses | -123 ± 58 |
| `weak` (68 %), not detectable, market at the design's values | 81.8 ± 1.3 % (70.6 ± 1.7 %) | 83.3 ± 2.6 % (71.8 ± 2.6 %) | 19 ± 11 % (76 ± 11 %) | 4.84 ± 0.47 (1.41 ± 0.33) | $0.043 | +33 ± 16 | **wins** | -157 ± 57 |
| `mid`, not detectable, waits a newcomer of any bond could end | 80.0 ± 0.4 % (89.3 ± 0.2 %) | 84.0 ± 1.2 % (88.8 ± 0.7 %) | 2 ± 2 % (0 ± 0 %) | 5.00 ± 0.32 (1.30 ± 0.14) | $0.196 | -50 ± 13 | loses | – |
| `weak`, not detectable, waits a newcomer of any bond could end | 80.3 ± 0.4 % (68.7 ± 0.6 %) | 75.8 ± 1.8 % (67.7 ± 1.6 %) | 15 ± 3 % (72 ± 4 %) | 5.02 ± 0.20 (1.52 ± 0.17) | $0.181 | +202 ± 19 | **wins** | – |
| `weak`, not detectable, waits a newcomer of any bond could end, `SCORE_BALANCED` | 80.0 ± 2.7 % (68.8 ± 0.5 %) | 58.0 ± 2.4 % (66.3 ± 1.8 %) | 96 ± 1 % (73 ± 3 %) | 1.47 ± 0.12 (1.60 ± 0.16) | $0.168 | -69 ± 10 | loses | – |

#134's weak-family herders on its moving market (no outage slash, `IDLE_HIGH` 50 %): 294 ± 28 $.

### A rule against its alternative

#### A rule against its alternative (40 seeds; the same seeds for each pair)

| #141's rule | Under the rule | Under each alternative |
|---|---|---|
| k = 1: hold, `K1_PENDING_MAX` 10, every k = 1 audited | colluder -221 ± 38 $, 87 % reversed; honest k = 1 pay 19.0 ± 3.6 days | `K1_PENDING_MAX` 5: colluder -185 ± 38 $, 76 % reversed; honest k = 1 pay 17.1 ± 4.1 days; `K1_PENDING_MAX` 20: colluder -299 ± 51 $, 92 % reversed; honest k = 1 pay 21.6 ± 3.1 days; `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties): colluder -97 ± 33 $, 64 % reversed; honest k = 1 pay 21.9 ± 3.7 days |
| k = 1's window 7 days | colluder -221 ± 38 $, 87 % reversed; honest k = 1 pay 19.0 ± 3.6 days | k = 1's window 14 days: colluder -243 ± 36 $, 88 % reversed; honest k = 1 pay 25.1 ± 3.6 days; k = 1's window 30 days: colluder -247 ± 39 $, 89 % reversed; honest k = 1 pay 40.2 ± 3.5 days |
| False verdict: the whole bond | grinder -250 ± 46 $ (loses); sybil -21,601 ± 2,530 $ (loses) | 2,000: grinder -70 ± 14 $ (loses); sybil -3,043 ± 532 $ (loses); colluder -67 ± 11 $, 87 % reversed |
| Constitution from 14 eligible, with expiry | 5 early: +622 ± 260 $ (**wins**); 3 early: +148 ± 182 $ (not significant) | 21: 5 early +280 ± 152 $ (**wins**), 3 early +82 ± 135 $ (not significant); 28: 5 early +187 ± 138 $ (**wins**), 3 early +65 ± 128 $ (not significant) |
| Sealed vote not revealed: $1; silence not slashed | silent +317 ± 13 $ (**wins**); withholder +249 ± 12 $ (**wins**) | `SILENCE_SLASH` $1: silent +250 ± 12 $ (**wins**); $0.50: withholder +282 ± 12 $ (**wins**); $5: withholder -20 ± 9 $ (loses) |
| Pricing: `IDLE_HIGH` 40 %, floor-bond wait signal | fee / break-even 0.47 ± 0.40 ×; 33 collapsed | `IDLE_HIGH` 30 %: fee / break-even –; 40 collapsed; `IDLE_HIGH` 50 %: fee / break-even 0.99 ± 0.10 ×; 12 collapsed; idling over 7 days (`IDLE_WINDOW_DAYS` 7): fee / break-even 1.20 ± 0.03 ×; 0 collapsed; waits a newcomer of any bond could end: fee / break-even 1.08 ± 0.07 ×; 1 collapsed; every wait counts (#134's signal): fee / break-even 1.21 ± 0.04 ×; 0 collapsed; `FEE_STEP_UP` 10 %: fee / break-even 0.62 ± 0.36 ×; 32 collapsed |
| Scores: counted only, normalised factor | weak herders +13 ± 2 $ (**wins**) | `SCORE_BALANCED`: weak herders -8 ± 1 $ (loses); mid herders -57 ± 4 $ (loses) |
| Level C's limits as the k table | shopper at 3 in 10 +174 ± 46 $ (**wins**); at 1 in 10 -13 ± 1 $ (loses) | `C_LIMIT_X` 0.5 (level C's limits halved): at 3 in 10 +157 ± 47 $ (**wins**); at 1 in 10 -12 ± 1 $ (loses) |
| TEE cap from k = 5 | k ≥ 3 in 40 runs, week 6 ± 1; caps lowered 13 ± 3 %; one TEE type holds a k = 3 majority on 77 ± 8 % | #134's from k = 3: k ≥ 3 in 40 runs, week 6 ± 1; caps lowered 8 ± 2 %; one TEE type holds a k = 3 majority on 0 ± 0 %; five TEE types, the TEE cap from k = 3: k ≥ 3 in 40 runs, week 6 ± 1; caps lowered 6 ± 1 %; one TEE type holds a k = 3 majority on 0 ± 0 % |
| `SHADOW_PER_WAITING` 3 | k ≥ 3 in 40 runs, week 6 ± 1; caps lowered 13 ± 3 %; one TEE type holds a k = 3 majority on 77 ± 8 %; colluder -221 ± 38 $, 87 % reversed; honest k = 1 pay 19.0 ± 3.6 days | `SHADOW_PER_WAITING` 0: k ≥ 3 in 0 runs, week –; caps lowered 0 ± 0 %; one TEE type holds a k = 3 majority on 0 ± 0 %; colluder -130 ± 2 $, – reversed; honest k = 1 pay – days |

### Acceptance criteria

#### Acceptance criteria for open validators under D17 (40 seeds; sweeps on 40; ± 2 standard errors)

| Criterion | Verdict | Threshold | What decides it |
|---|---|---|---|
| Each open-validator attacker loses against its honest twin | **not met** | mean + 2 SE < 0 | 4 of 11 don't lose: Silent (never seals), the design: no slash for silence (+317 ± 13 $); Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $1 (the design) (+249 ± 12 $); Constitution coalition: 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) (+622 ± 260 $); Constitution coalition: 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) (+148 ± 182 $) |
| Each pricing attacker loses against its honest twin | **not met** | mean + 2 SE < 0 | 2 of 6 don't lose: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) (+33 ± 4 $); Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) (design) (+28 ± 4 $) |
| Each proof-level attacker loses against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | **met** | mean + 2 SE < 0 | all 7 lose; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes) (-13 ± 1 $) |
| Each scoring attacker (the herders) loses against its honest twin | **not met** | mean + 2 SE < 0 | 3 of 8 don't lose: Herders: `weak` (68 %), not detectable (upper bound) (+13 ± 2 $); Herders: `weak`, not detectable, at a $0.25 fee (`FEE_CEILING`) (+80 ± 9 $); Herders on the market: `weak` (68 %), not detectable, market at the design's values (+33 ± 16 $) |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | **met** | 0 runs | 3 validators (12.5 %), spread: a majority on 0.00 % of panels; 3 validators (12.5 %), one host: a majority on 0.00 % of panels |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported | reported: 6 (22 %), one host: a majority on 0.0 % of its own panels, 2.8 bad fixes paid, 10.8 false verdicts proven; 6 (22 %), spread: a majority on 1.2 % of its own panels, 6.3 bad fixes paid, 13.6 false verdicts proven; 10 (32 %), one host: a majority on 0.0 % of its own panels, 5.0 bad fixes paid, 14.0 false verdicts proven; 10 (32 %), spread: a majority on 8.0 % of its own panels, 15.9 bad fixes paid, 17.8 false verdicts proven; 20 (49 %), one host: a majority on 0.0 % of its own panels, 9.2 bad fixes paid, 15.4 false verdicts proven; 20 (49 %), spread: a majority on 30.5 % of its own panels, 39.9 bad fixes paid, 16.3 false verdicts proven |
| The colluding lone validator loses, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes are reversed before any payment (pooled) | **not met** | mean + 2 SE < 0 and share − 2 SE ≥ 90 % | return − twin's -221 ± 38 $ (loses); reversed before payment 86.6 % ± 5.1 % (181 of 209 that reached an outcome; 0 still pending at the year's end) |
| The constitution waits for the network: no ADR passes while fewer than 2 × `K_MAX` validators are eligible, in any run | **met** | 0 runs | ADRs passed while fewer than 14 were eligible, all runs: 0 (over 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) and 3 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design)) |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | **not met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | from the ceiling, fee / break-even over the last 13 weeks 0.47 ± 0.40 × (the runs that didn't collapse); 33 of 40 runs collapsed below 3 active validators |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` (15 %) of submissions wait | **met** | mean + 2 SE ≤ 15 % | 7.9 ± 2.4 % waited, every validator moving (registering again) |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | **met** | every run | 40 of 40 runs, at week 6 ± 1; the median days from a k = 1 verdict to its payment, a run: 19.0 ± 3.6 (p90 over every run: 46.1) |
| Answer shopping, the trust point: it loses at 1 in 10; at 3 in 10 the report gives its gain | **met** | mean + 2 SE < 0 at 1 in 10 | at 1 in 10: -13 ± 1 $ (loses); at 3 in 10 (reported): +174 ± 46 $ |
| Every earlier criterion holds or is named | **met** | named | named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md stand |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | all | 5 of 13 criteria not met |

## Commands, seeds and tests
- **The report:** `python3 -m pof.sim market validators --seeds 40 --jobs 2` (seeds 1–40; the sybil and audit sweeps on the same 40). `--jobs 2` forks two processes, one section each; the output is identical to one process (tested on `--quick`).
- **v1:** `python3 -m pof.sim market validators --seeds 40 --v1` prints reports/open-validators-v1.md's tables on #134's rules (`POF_OPENVAL_RULES=v1`). It needs a fresh process.
- **One section:** `python3 -m pof.sim.openval {growth,attackers,sybil,audits,levels,pricing,scores,params} --seeds 40`, on #141's rules.
- **Tests:** `tests/test_openval_v2.py` (50): each #141 rule alone against the scenarios of validator-admission, judge-panels, judge-scores and check-pricing; each switch changes only what it names; the new actors beside their twins; D17's judging (a result that isn't significant fails); `V1` reproduces v1's numbers on seed 1; the command's numbers are reproducible; `--v1` prints v1's quick report byte for byte; this report names each criterion as met or not. The v1 tests (`test_openval*.py`, 157) now run on `V1` explicitly. The open-validator tests take 40 seconds, 16 more than before.
- **Not run here:** the CI's Amazon Linux container (Docker is off on this machine); the unit tests ran under Python 3.9.25 instead. Task 1.9's zkTLS spike needs the owner's approval.

