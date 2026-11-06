# Open validators, v2: #141's rules (1 seeds; the sybil and audit sweeps on 1) — QUICK: one row per section, for the tests

## Growth from one validator under the hold, and the TEE cap

### Growth from one validator under #141's rules (1 seeds; one newcomer a week, 30 submissions a week)

| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | Waiting submissions | Withdrawn so far |
|---|---|---|---|---|---|---|---|
| 0 | 1.0 ± 0.0 | 0.0 ± 0.0 | 1.0 | 0 % | $50 | 4.0 ± 0.0 | 0 % |
| 4 | 4.0 ± 0.0 | 3.0 ± 0.0 | 3.0 | 100 % | $250 | 47.0 ± 0.0 | 50 % |
| 8 | 7.0 ± 0.0 | 2.0 ± 0.0 | 7.0 | 100 % | $250 | 18.0 ± 0.0 | 49 % |
| 12 | 11.0 ± 0.0 | 3.0 ± 0.0 | 7.0 | 100 % | $250 | 14.0 ± 0.0 | 44 % |
| 16 | 18.0 ± 0.0 | 3.0 ± 0.0 | 7.0 | 100 % | $625 | 2.0 ± 0.0 | 37 % |
| 20 | 21.0 ± 0.0 | 2.0 ± 0.0 | 7.0 | 100 % | $625 | 3.0 ± 0.0 | 30 % |
| 24 | 25.0 ± 0.0 | 0.0 ± 0.0 | 7.0 | 100 % | $625 | 3.0 ± 0.0 | 26 % |
| 28 | 29.0 ± 0.0 | 2.0 ± 0.0 | 7.0 | 100 % | $625 | 3.0 ± 0.0 | 23 % |
| 32 | 33.0 ± 0.0 | 1.0 ± 0.0 | 7.0 | 100 % | $625 | 4.0 ± 0.0 | 20 % |
| 36 | 37.0 ± 0.0 | 5.0 ± 0.0 | 7.0 | 100 % | $625 | 4.0 ± 0.0 | 18 % |
| 40 | 45.0 ± 0.0 | 0.0 ± 0.0 | 7.0 | 100 % | $625 | 2.0 ± 0.0 | 17 % |
| 44 | 48.0 ± 0.0 | 5.0 ± 0.0 | 7.0 | 100 % | $625 | 1.0 ± 0.0 | 16 % |
| 48 | 53.0 ± 0.0 | 3.0 ± 0.0 | 7.0 | 100 % | $625 | 0.0 ± 0.0 | 14 % |

| Over the year | |
|---|---|
| Submissions that waited for a panel | 18 % ± 0 |
| ...withdrawn after 14 days of waiting | 13 % ± 0 |
| Days from submission to final verdict | 2.2 ± 0.0 |
| Bad fixes merged per 100 paid | 0.60 ± 0.00 |
| Panels drawn at k = 1 / 3 / 5 / 7 | 3 % / 22 % / 4 % / 71 % |
| Draws whose k the caps lowered (from the largest odd number of eligible validators) | 28 % ± 0 |
| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week 4 (1 of 1 runs) / week 8 (1 of 1 runs) |
| Newcomers / qualified in the year | 60.0 ± 0.0 / 57.0 ± 0.0 |
| Days from registration to activation | 13.3 ± 0.0 |
| Failed qualification attempts | 4.0 ± 0.0 |
| Challenges / verdicts reversed / challenges still frozen at year's end | 29.0 ± 0.0 / 4.0 ± 0.0 / 0.0 ± 0.0 |
| Shadows' usage repaid from the sponsors' pool | $205 |
| An activated validator's month: fees $0.95, less overhead $0.30, slashes for outages $0.00, fixed costs $4.67, the bond's capital $1.75 | net **$-5.77** |

#### An honest network grows under the hold (1 seeds; a year; growth from one validator, one newcomer a week, 30 submissions a week; each rule beside its alternatives, same seeds)

| Rule | Runs where a small bounty reaches k ≥ 3 | First 4-week snapshot at k ≥ 3 | Days from a k = 1 verdict to payment: median a run (p90, all runs) | k = 1 verdicts held / days held | Submissions that waited / withdrawn | Newcomers qualified (of joined) / days to qualify | Sponsors' pool on shadows (on waiting submissions) | Bad fixes merged per 100 paid | Draws the caps lowered | Panels of k ≥ 3 (of 3) with one TEE type holding the majority | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)** | 1 of 1 | week 4 ± 0 | 7.0 ± 0.0 (33.0) | 29 ± 0 % / 21.8 ± 0.0 | 18 ± 0 % / 13 ± 0 % | 57.0 ± 0.0 (60.0) / 13 ± 0 | $205 ($60) | 0.60 ± 0.00 | 28 ± 0 % | 18.1 ± 0.0 % (80 ± 0 %) | 53.0 ± 0.0 |

"Days from a k = 1 verdict to payment": over the k = 1 fixes paid in each run, the median a run (mean over runs ± 2 SE) and the 90th percentile over every run's paid k = 1 fixes. "Held": k = 1 verdicts whose window waited for CHALLENGE_K[1] eligible challengers, and the mean days they waited. #134's numbers: waited 68 % ± 6, withdrawn 64 % ± 6, qualified 18.2 ± 5.0 after 135.1 ± 20.6 days, the caps lowered 39 % ± 9 of draws; the last row reruns them.

## The attackers

### Each attacker against its honest twin (1 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | #134's return − twin's (v1) | What it got |
|---|---|---|---|---|---|---|
| Seed grinder (v3's seed: a later block) | -129 ± 0 | loses | -186 | -57 | 258 ± 79 | 3.0 bad fixes paid of 27 attempts; 3.0 false verdicts proven, 0.0 challenges still frozen; 57.0 newcomers qualified (twin: 57.0) |

The colluding genesis, the silent judge and the constitution coalition have their own tables below.

### The colluding genesis under the hold (1 seeds; a year; growth from one validator; the genesis, bonded $100, passes its accomplice's bad fixes at k = 1; against its honest twin)

| Rule | Return − twin's ($, ± 2 SE) | Against its twin | Bad fixes passed / reversed / paid / still pending | Reversed before payment, pooled (± 2 SE) | Its verdicts held | Challenges still frozen | Newcomers qualified (twin's) | Slashed |
|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)**, 5 bad fixes a week | -328 ± 0 | loses | 4.0 / 4.0 / 0.0 / 0.0 | 100.0 % ± 0.0 % | 4.0 | 0.0 | 58.0 (58.0) | $300 |

#134 (k = 1's 72-hour window, 20 % slash, no hold): 2,920 ± 456 $, 1242 of the 6997 bad fixes it passed reversed (18 %); the last row reruns it. "Reversed before payment" counts the passed bad fixes that reached an outcome by the year's end; "still pending" ones (held or in their window at the year's end) are neither.

### A silent judge without a silence slash (1 seeds; a year; a grown network of 12 honest validators; bribed 5 % of the bounty on 10 % of its draws)

| Judge and rule | Return − twin's ($, ± 2 SE) | Against its twin | Bribed misses / suspended | Slashed | k ever shrank | #134 (v1) |
|---|---|---|---|---|---|---|
| **Silent (never seals), the design: no slash for silence** | +314 ± 0 | **wins** | 62.0 / 7.0 | $0.00 | never | – |

### An early coalition (1 seeds; a year; growth from one validator; the coalition registers its validators at the start and submits an ADR worth $1,000 to it each week; its validators pass them)

| Coalition and rule | Return − twin's ($, ± 2 SE) | Against its twin | ADRs submitted / expired / judged / passed | Passed while fewer than the threshold were eligible (all runs) | Passed while fewer than 2 × `K_MAX` (14) were eligible (all runs) | First ADR judged (day; 365: none) | #134 (v1) |
|---|---|---|---|---|---|---|---|
| 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) | +1,924 ± 0 | **wins** | 55 / 15.0 / 40.0 / 2.00 | 0 | 0 | 75 | – |

### The sybil's majorities by its share (1 seeds; 20 honest validators, newcomers at half a validator a week; its bad fixes at 2 a week)

| Sybil validators (share of the eligible) | Spread | Majority of its own panels | Majority of any panel with k ≥ 3 | Bad fixes paid | False verdicts proven |
|---|---|---|---|---|---|
| 3 (12 %) | spread | 0.0 % | 0.00 % | 3.0 | 5.0 |
| 3 (12 %) | one host | 0.0 % | 0.00 % | 2.0 | 3.0 |

### The watcher's dilemma (1 seeds; 26 weeks; one lazy cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 10 % | 33.0 | 12 % | -5,120.1 ± 0.0 | loses | $0.0180 |
| yes | 10 % | 33.0 | 15 % | -6,401.3 ± 0.0 | loses | $0.0180 |

### The watcher's dilemma (1 seeds; 26 weeks; one bribed cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 10 % | 9.0 | 22 % | -2,512.4 ± 0.0 | loses | $0.0180 |
| yes | 10 % | 9.0 | 22 % | -2,512.4 ± 0.0 | loses | $0.0180 |

## The k table compared

### The k table compared (1 seeds; a year; 30 submissions a week; every validator at level A; the same seeds for both rules)

| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Grown: the genesis and 20 active | k table (v3) | 1.0 ± 0.0 (0.09 ± 0.00) | 1,158 ± 0 | 0.4 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $1.82 ± 0.00 | $-7.16 ± 0.00 | 45.0 ± 0.0 |
| Grown: the genesis and 20 active | fixed k = 3, bounties to $625 | 4.0 ± 0.0 (0.35 ± 0.00) | 1,138 ± 0 | 1.1 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $0.89 ± 0.00 | $-7.65 ± 0.00 | 45.0 ± 0.0 |

Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with three validators, a 24-hour window and a challenge panel of 5. "–": nothing to measure (no verdict became final, or nothing was paid).

## Proof levels

### Panels by proof level (1 seeds; a year; 30 submissions a week)

| Network | Waited for a panel | Withdrawn | Waited for a stronger panel | Panels drawn | Panels at A / B / C | Days to final at A / B / C | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Growth at launch: genesis A, newcomers ⅓ A, ⅓ B, ⅓ C, **the C third refused (level C off)** | 21 % ± 0 | 13 % ± 0 | 4 % ± 0 | 1,362 ± 0 | 70 % / 30 % / 0 % | 3.7 / 1.8 / – | 0.20 ± 0.00 | $625 | 36.0 ± 0.0 |
| Growth, ordinary PCs only (genesis at C, even with C accepted) | refused at deployment: a level C genesis validator; the genesis must be at level A or B | | | | | | | | |

| Hidden-test bounties | Waited for a panel | Withdrawn | Seen by a level C validator (counted, replacement or shadow; all runs) |
|---|---|---|---|

### Each proof-level attacker against its honest twin (1 seeds; a year; returns in $)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | #134's return − twin's (v1) | What it got |
|---|---|---|---|---|---|---|
| Test liar: the genesis at C, 5 bad fixes a week (even with C accepted) | refused at deployment | – | – | – | 165 ± 13 | a level C genesis validator; the genesis must be at level A or B |
| **Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes)** | -15 ± 0 | loses | -255 | -240 | -2 ± 14 | 12.0 verdicts flipped of 34.0 shopped (116 extra calls); outweighed by the other judges 12.0, reversed 0.0, paid 0.0; bad fixes paid 0.0 of 103 (twin 0.0); agreement with final outcomes 86.6 % (twin 89.1 %) |

### Level C at launch: off (owner decision 2026-11-03, spec PR pending; the default) against the merged design, C accepted from genesis (1 seeds; a year)

| Network | Newcomers joined (refused at C) | Qualified / days | Runs reaching k ≥ 3 / first week | Submissions that waited / withdrawn | Days from a k = 1 verdict to payment (median a run) | Bad fixes merged per 100 paid | Largest bounty judged at year's end | Active at year's end |
|---|---|---|---|---|---|---|---|---|
| Growth, genesis A, newcomers ⅓ A, ⅓ B, ⅓ C: **level C off at launch (the default)**, the C third refused | 38.0 (22.0) | 37.0 ± 0.0 / 9 ± 0 | 1 of 1 / week 8 ± 0 | 21 ± 0 % / 13 ± 0 % | 7.0 ± 0.0 | 0.20 ± 0.00 | $625 | 36.0 ± 0.0 |
| Growth, the same: **level C accepted from genesis (the merged design)** | 60.0 (0.0) | 58.0 ± 0.0 / 13 ± 0 | 1 of 1 / week 4 ± 0 | 21 ± 0 % / 12 ± 0 % | 7.0 ± 0.0 | 0.39 ± 0.00 | $625 | 54.0 ± 0.0 |

| Attacker | Level C off at launch (the default): return − twin's ($) | | Level C accepted (from genesis, or after the ADR for the grown network's rows): return − twin's ($) | |
|---|---|---|---|---|
| Colluding genesis (A, $100), newcomers ⅓ each | -329 ± 0 | loses | -327 ± 0 | loses |

## Market pricing

### The fee finds the validators' cost (1 seeds; a year; 20 honest validators and the genesis at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the ceiling unless stated)

| Variant | Fee at week 4 / 13 / 26 / 52 | Fee over the last 13 weeks | Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | Runs collapsed (< 3 active) | Honest validator's month |
|---|---|---|---|---|---|---|---|---|---|
| **#141's rules (the design)** | $0.122 / $0.017 / $0.035 / $0.055 | $0.042 ± 0.000 | $– | $– | 1.0 ± 0.0 | 19 % ± 0 | 100 % ± 0 | 1 of 1 | $-8.84 ± 0.00 |

Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every row, so the fee is the validator's whole margin.

#### The fee against break-even, D17's `FEE_MARGIN` (1 seeds; the runs that didn't collapse)

| Variant | Fee / break-even over the last 13 weeks (± 2 SE) | Within [1 − `FEE_STEP`, 1 + `FEE_MARGIN`] | Runs collapsed |
|---|---|---|---|
| **#141's rules (the design)** | – | no | 1 of 1 |

#### An honest validator's month on the market (1 seeds; honest validators active a month or more; $ a month)

| Market and outages | Service fees | Usage margin | Node overhead | Slashes | Fixed costs | The bond's capital | Net | Runs with such validators |
|---|---|---|---|---|---|---|---|---|
| the design: outages before the seal (silence, not slashed) | $5.20 ± 0.00 | $-0.07 ± 0.00 | $0.48 ± 0.00 | $0.00 ± 0.00 | $4.67 ± 0.00 | $8.83 ± 0.00 | $-8.84 ± 0.00 | 1 |

#134: the honest validator's month on the market $-2.65 ± 0.51 $ (the fee at its ceiling), and −$8.01 on the growing network, $2.05 of it outage slashes.

### The pricing attackers against their honest twins (1 seeds; a year; returns in $)

| Attacker | Market | Return − twin's ($, ± 2 SE) | Against its twin | Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's / twin's | Active validators (last 13 weeks) | #134 (v1, design) | What it did |
|---|---|---|---|---|---|---|---|---|
| Cartel: 6 validators refusing half their draws | design | -493 ± 0 | loses | $0.044 / $0.074 | 1.00 / 1.00 | 2.9 | -5,460 ± 335 | 1255 refusals, suspended 174 times, slashed $0 |

## Model scores

### The families' scores under #141's rules (1 seeds; at the year's end)

| Family | True accuracy (assumed) | Score (counted verdicts) | Fee factor (normalised) | Share of the year barred | Times barred / recovered |
|---|---|---|---|---|---|
| `top` | 95 % | 92.0 ± 0.0 % | 1.14 ± 0.00 × | 0 ± 0 % | 0.0 / 0.0 |
| `mid` | 90 % | 84.5 ± 0.0 % | 0.87 ± 0.00 × | 0 ± 0 % | 0.0 / 0.0 |
| `low` | 85 % | 84.5 ± 0.0 % | 0.87 ± 0.00 × | 0 ± 0 % | 0.0 / 0.0 |
| `weak` | 68 % | 59.6 ± 0.0 % | 0.50 ± 0.00 × | 53 ± 0 % | 11.0 / 10.0 |

### One vote, pay by score, weighted votes (1 seeds; a year)

| Families | Rule | Bad fixes merged per 100 paid | Good fixes failed (%) | Panels decided by one family (%) | Service fees per submission ($) | `top` net a month ($) | `mid` net a month ($) | `low` net a month ($) | `weak` net a month ($) |
|---|---|---|---|---|---|---|---|---|---|
| blind spots | **One vote, pay by score (#141: counted-only scores, the normalised factor)** | 1.12 ± 0.00 | 0.60 ± 0.00 | 4.66 ± 0.00 | 0.353 ± 0.000 | -6.62 ± 0.00 | -6.43 ± 0.00 | -6.74 ± 0.00 | -8.99 ± 0.00 |

#134: service fees per submission 0.499 ± 0.003 with pay by score against 0.358 ± 0.000 without (+39 %).

### Herding (1 seeds; a year; 4 herders of one family among 16 honest validators; each votes pass, the public base rate's majority)

| Herders | Their agreement with outcomes (twin's) | ...balanced over passed and failed outcomes | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Return − twin's ($, ± 2 SE) | Herding | #134 (v1) |
|---|---|---|---|---|---|---|---|---|
| `weak` (68 %), not detectable (upper bound) | 75.0 ± 0.0 % (65.1 ± 0.0 %) | 50.0 ± 0.0 % (65.2 ± 0.0 %) | 70.5 ± 0.0 % (77.3 ± 0.0 %) | 27 ± 0 % (73 ± 0 %) | 2.69 ± 0.00 (1.12 ± 0.00) | +18 ± 0 | **wins** | -191 ± 53 |

### Scores on the market fee (1 seeds; a year; the score families' accuracies and blind spots; the market's 20 initial validators, five per family, and 2 prospects a week)

| Market | Rule | Mean service fee | Active validators (last 13 weeks) | Bad fixes merged per 100 paid | `top` validator's net per month | `mid` validator's net per month | `low` validator's net per month | `weak` validator's net per month |
|---|---|---|---|---|---|---|---|---|
| design | One vote, no scores | $0.048 ± 0.000 | 1.0 ± 0.0 | 0.00 ± 0.00 | $-1.58 ± 0.00 | $-1.14 ± 0.00 | $-0.66 ± 0.00 | $-0.86 ± 0.00 |
| design | **One vote, pay by score (v3's design)** | $0.042 ± 0.000 | 1.0 ± 0.0 | 1.17 ± 0.00 | $-1.52 ± 0.00 | $-1.86 ± 0.00 | $-0.68 ± 0.00 | $-1.66 ± 0.00 |

Market "design": #141's rules, the fee starting at the ceiling (it collapses in most runs, see the pricing section). "any-bond wait signal": the switch under which it doesn't. The families are priced as the providers they stand for (`top` Anthropic, `mid` OpenAI, `low` Google, `weak` an open-weight model). Prospects decide to enter on the unscaled fee.

### Herding on the market fee (1 seeds; a year; 4 undetectable herders of one family beside the market's validators)

| Herders | Their agreement (twin's) | Their family's score (twin's) | Family barred (twin's) | Bad fixes merged per 100 paid (twin's) | Mean fee | Return − twin's ($, ± 2 SE) | Herding | #134 (v1) |
|---|---|---|---|---|---|---|---|---|
| `weak` (68 %), not detectable, market at the design's values | 82.2 ± 0.0 % (63.4 ± 0.0 %) | 90.0 ± 0.0 % (67.9 ± 0.0 %) | 0 ± 0 % (97 ± 0 %) | 3.82 ± 0.00 (0.00 ± 0.00) | $0.042 | +39 ± 0 | **wins** | -157 ± 57 |

#134's weak-family herders on its moving market (no outage slash, `IDLE_HIGH` 50 %): 294 ± 28 $.

## A rule against its alternative

### A rule against its alternative (1 seeds; the same seeds for each pair)

| #141's rule | Under the rule | Under each alternative |
|---|---|---|
| k = 1: hold, `K1_PENDING_MAX` 10, every k = 1 audited | colluder -328 ± 0 $, 100 % reversed; honest k = 1 pay 7.0 ± 0.0 days | `K1_PENDING_MAX` 5: –; `K1_PENDING_MAX` 20: –; `K1_BATCH_BOND` (no count cap; bond ≥ 2 × its pending k = 1 bounties): – |
| k = 1's window 7 days | colluder -328 ± 0 $, 100 % reversed; honest k = 1 pay 7.0 ± 0.0 days | k = 1's window 14 days: –; k = 1's window 30 days: – |
| False verdict: the whole bond | grinder -129 ± 0 $ (loses) | 2,000:  |
| Constitution from 14 eligible, with expiry | 5 early: +1,924 ± 0 $ (**wins**); – | 21: –, –; 28: –, – |
| Sealed vote not revealed: $1; silence not slashed | silent +314 ± 0 $ (**wins**); – |  |
| Pricing: `IDLE_HIGH` 40 %, floor-bond wait signal | fee / break-even –; 1 collapsed | `IDLE_HIGH` 30 %: –; `IDLE_HIGH` 50 %: –; idling over 7 days (`IDLE_WINDOW_DAYS` 7): –; waits a newcomer of any bond could end: –; every wait counts (#134's signal): –; `FEE_STEP_UP` 10 %: – |
| Scores: counted only, normalised factor | weak herders +18 ± 0 $ (**wins**) |  |
| Level C's limits as the k table | –; at 1 in 10 -15 ± 0 $ (loses) | –; – |
| TEE cap from k = 5 | k ≥ 3 in 1 runs, week 4 ± 0; caps lowered 28 ± 0 %; one TEE type holds a k = 3 majority on 80 ± 0 % | #134's from k = 3: –; five TEE types, the TEE cap from k = 3: – |
| `SHADOW_PER_WAITING` 3 | k ≥ 3 in 1 runs, week 4 ± 0; caps lowered 28 ± 0 %; one TEE type holds a k = 3 majority on 80 ± 0 %; colluder -328 ± 0 $, 100 % reversed; honest k = 1 pay 7.0 ± 0.0 days | `SHADOW_PER_WAITING` 0: –; – |

## Acceptance criteria

### Acceptance criteria for open validators under D17 (1 seeds; sweeps on 1; ± 2 standard errors)

| Criterion | Verdict | Threshold | What decides it |
|---|---|---|---|
| Each open-validator attacker loses against its honest twin | **not met** | mean + 2 SE < 0 | 2 of 6 don't lose: Silent (never seals), the design: no slash for silence (+314 ± 0 $); Constitution coalition: 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design) (+1,924 ± 0 $) |
| Each pricing attacker loses against its honest twin | **met** | mean + 2 SE < 0 | all 1 lose; the closest: Cartel: 6 validators refusing half their draws (design) (-493 ± 0 $) |
| Each proof-level attacker loses against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | **met** | mean + 2 SE < 0 | all 1 lose; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, borderline fixes fool an honest call 1 in 10 (counted; twin: calls once, same fixes) (-15 ± 0 $) |
| Each scoring attacker (the herders) loses against its honest twin | **not met** | mean + 2 SE < 0 | 2 of 2 don't lose: Herders: `weak` (68 %), not detectable (upper bound) (+18 ± 0 $); Herders on the market: `weak` (68 %), not detectable, market at the design's values (+39 ± 0 $) |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | **met** | 0 runs | 3 validators (12.5 %), spread: a majority on 0.00 % of panels; 3 validators (12.5 %), one host: a majority on 0.00 % of panels |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported | reported: no size above the share was run |
| The colluding lone validator loses, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes are reversed before any payment (pooled) | **met** | mean + 2 SE < 0 and share − 2 SE ≥ 90 % | return − twin's -328 ± 0 $ (loses); reversed before payment 100.0 % ± 0.0 % (4 of 4 that reached an outcome; 0 still pending at the year's end) |
| The constitution waits for the network: no ADR passes while fewer than 2 × `K_MAX` validators are eligible, in any run | **met** | 0 runs | ADRs passed while fewer than 14 were eligible, all runs: 0 (over 5 early validators, `CONSTITUTION_MIN_ELIGIBLE` 14 (the design)) |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | **not met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | from the ceiling, fee / break-even over the last 13 weeks – (the runs that didn't collapse); 1 of 1 runs collapsed below 3 active validators |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` of submissions wait | **not met** |  | not run (quick) |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | **met** | every run | 1 of 1 runs, at week 4 ± 0; the median days from a k = 1 verdict to its payment, a run: 7.0 ± 0.0 (p90 over every run: 33.0) |
| Answer shopping, the trust point: it loses at 1 in 10; at 3 in 10 the report gives its gain | **met** | mean + 2 SE < 0 at 1 in 10 | at 1 in 10: -15 ± 0 $ (loses); at 3 in 10 (reported): not run |
| Every earlier criterion holds or is named | **met** | named | named, not re-run (D15, gap 20): v3 leaves v2's market, checking, token and split rules unchanged, so reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md stand |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | all | 4 of 13 criteria not met |
