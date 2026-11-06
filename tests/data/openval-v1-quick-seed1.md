# Open validators: the full run (1 seeds; the sybil and audit sweeps on 1) — QUICK: one row per section, for the tests

## Phase 1: growth, the attackers, the sybil's share, the watcher's dilemma

### Growth from one validator (1 seeds; one newcomer a week, 30 submissions a week)

| Week | Active validators | Candidates | k for a small bounty | Runs at k ≥ 3 | Largest bounty judged | Waiting submissions | Withdrawn so far |
|---|---|---|---|---|---|---|---|
| 0 | 1.0 ± 0.0 | 0.0 ± 0.0 | 1.0 | 0 % | $50 | 4.0 ± 0.0 | 0 % |
| 4 | 1.0 ± 0.0 | 6.0 ± 0.0 | 1.0 | 0 % | $50 | 47.0 ± 0.0 | 44 % |
| 8 | 2.0 ± 0.0 | 7.0 ± 0.0 | 1.0 | 0 % | $50 | 51.0 ± 0.0 | 59 % |
| 12 | 2.0 ± 0.0 | 12.0 ± 0.0 | 1.0 | 0 % | $50 | 37.0 ± 0.0 | 70 % |
| 16 | 3.0 ± 0.0 | 18.0 ± 0.0 | 3.0 | 100 % | $250 | 51.0 ± 0.0 | 71 % |
| 20 | 5.0 ± 0.0 | 18.0 ± 0.0 | 5.0 | 100 % | $250 | 42.0 ± 0.0 | 73 % |
| 24 | 5.0 ± 0.0 | 20.0 ± 0.0 | 5.0 | 100 % | $250 | 60.0 ± 0.0 | 72 % |
| 28 | 5.0 ± 0.0 | 26.0 ± 0.0 | 5.0 | 100 % | $250 | 53.0 ± 0.0 | 75 % |
| 32 | 6.0 ± 0.0 | 28.0 ± 0.0 | 5.0 | 100 % | $250 | 54.0 ± 0.0 | 77 % |
| 36 | 8.0 ± 0.0 | 34.0 ± 0.0 | 7.0 | 100 % | $250 | 32.0 ± 0.0 | 73 % |
| 40 | 11.0 ± 0.0 | 34.0 ± 0.0 | 7.0 | 100 % | $250 | 13.0 ± 0.0 | 69 % |
| 44 | 12.0 ± 0.0 | 41.0 ± 0.0 | 7.0 | 100 % | $250 | 19.0 ± 0.0 | 65 % |
| 48 | 15.0 ± 0.0 | 41.0 ± 0.0 | 7.0 | 100 % | $625 | 17.0 ± 0.0 | 62 % |

| Over the year | |
|---|---|
| Submissions that waited for a panel | 65 % ± 0 |
| ...withdrawn after 14 days of waiting | 59 % ± 0 |
| Days from submission to final verdict | 2.7 ± 0.0 |
| Bad fixes merged per 100 paid | 0.89 ± 0.00 |
| Panels drawn at k = 1 / 3 / 5 / 7 | 33 % / 24 % / 26 % / 17 % |
| Draws whose k the caps lowered (from the largest odd number of eligible validators) | 72 % ± 0 |
| First 4-week snapshot with k ≥ 3 / k = 7 for a small bounty | week 16 (1 of 1 runs) / week 36 (1 of 1 runs) |
| Newcomers / qualified in the year | 60.0 ± 0.0 / 19.0 ± 0.0 |
| Days from registration to activation | 180.9 ± 0.0 |
| Failed qualification attempts | 1.0 ± 0.0 |
| Challenges / verdicts reversed / challenges still frozen at year's end | 31.0 ± 0.0 / 11.0 ± 0.0 / 0.0 ± 0.0 |
| Shadows' usage repaid from the sponsors' pool | $102 |
| An activated validator's month: fees $0.54, less overhead $0.15, slashes for outages $2.38, fixed costs $4.67, the bond's capital $2.41 | net **$-9.07** |

### Each attacker against its honest twin (1 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Colluding lone validator (the genesis, bonded $100) | 4,201 ± 0 | **wins** | 4,140 | -62 | 125.0 bad fixes paid of 265 attempts; 0.0 false verdicts proven, 136.0 challenges still frozen; 0.0 newcomers qualified (twin: 14.0) |
| Constitution coalition (5 early validators) | 36,911 ± 0 | **wins** | 36,513 | -399 | 37.0 ADRs passed of 55; passed while fewer than K_MAX were eligible: 0 |

### The sybil's majorities by its share (1 seeds; 20 honest validators, newcomers at half a validator a week; its bad fixes at 2 a week)

| Sybil validators (share at the start) | Spread | Majority of its own panels | Majority of any panel with k ≥ 3 | Bad fixes paid | False verdicts proven |
|---|---|---|---|---|---|
| 10 (32 %) | spread | 6.7 % | 6.10 % | 20.0 | 7.0 |
| 10 (32 %) | one host | 0.0 % | 0.00 % | 7.0 | 7.0 |

### The watcher's dilemma (1 seeds; 26 weeks; one lazy cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 5 % | 33.0 | 6 % | -507.8 ± 0.0 | loses | $0.0083 |
| yes | 5 % | 33.0 | 9 % | -764.0 ± 0.0 | loses | $0.0083 |

### The watcher's dilemma (1 seeds; 26 weeks; one bribed cheater among 16 validators, cheating on 10 % of its draws)

| Volunteers | Audit rate | Cheats | Caught (false verdicts proven) | Cheater − twin ($, ± 2 SE) | Cheating | Audit cost per check |
|---|---|---|---|---|---|---|
| none | 5 % | 9.0 | 11 % | -206.2 ± 0.0 | loses | $0.0083 |
| yes | 5 % | 9.0 | 11 % | -206.2 ± 0.0 | loses | $0.0083 |

## The k table compared, and the window's length

### The k table compared (1 seeds; a year; 30 submissions a week; every validator at level A; the same seeds for both rules)

| Network | Rule | Bad fixes merged (per 100 paid) | Fixes paid | Days to final verdict | Submissions that waited | ...withdrawn | Cost of the checks per paid fix | Activated validator's net per month | Active at year's end |
|---|---|---|---|---|---|---|---|---|---|
| Grown: the genesis and 20 active | k table (v3) | 1.0 ± 0.0 (0.09 ± 0.00) | 1,158 ± 0 | 0.4 ± 0.0 | 0 ± 0 % | 0 ± 0 % | $1.80 ± 0.00 | $-14.13 ± 0.00 | 45.0 ± 0.0 |
| Grown: the genesis and 20 active | fixed k = 3, bounties to $625 | 2.0 ± 0.0 (0.18 ± 0.00) | 1,126 ± 0 | 1.5 ± 0.0 | 9 ± 0 % | 1 ± 0 % | $0.88 ± 0.00 | $-10.39 ± 0.00 | 45.0 ± 0.0 |

Cost of the checks: every counted check's fee and usage, audits, challenge panels and the shadows' usage, over the fixes paid. A fixed k of 3 judges every bounty up to $625 (v2's `BOUNTY_MAX`) with three validators, a 24-hour window and a challenge panel of 5. "–": nothing to measure (no verdict became final, or nothing was paid).

### The window's length (1 seeds; a year; growth from one validator; the colluding genesis, bonded $100, against its honest twin; k = 1's window varied, `UNBONDING_DELAY` following it)

| Colluder | k = 1's window | Return − twin's ($, ± 2 SE) | Runs it loses money | Runs none of its bad fixes is paid | Runs both (caught and loses) | Bad fixes passed / paid / reversed | Challenges still frozen at year's end | Newcomers qualified (twin's) |
|---|---|---|---|---|---|---|---|---|
| 5 bad fixes a week | 72 h | 4,201 ± 0 | 0 of 1 | 0 of 1 | 0 of 1 | 265.0 / 125.0 / 0.0 | 136.0 | 0.0 (14.0) |

- **5 bad fixes a week:** the shortest window at which it is caught and loses money in at least one run: none of those tried; in every run: none of those tried. The spec's "published share" of runs isn't published.

## Proof levels

### Each proof-level attacker against its honest twin (1 seeds; a year; returns in $, with bonds' capital, running costs, fees, slashes, extra model calls, attempt fees and checks counted)

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Test liar: the genesis at C ($10 at k = 1, 7-day window), 5 bad fixes a week | 156 ± 0 | **wins** | 96 | -61 | 47.0 bad fixes paid of 260 (largest $10); 236.0 lies: 211.0 challenged, 0.0 proven by re-runs (0 %), 0.0 reversed, 211.0 still frozen at year's end; slashed $0 |

## Market pricing

### The fee finds the validators' cost (1 seeds; a year; 20 honest validators and the genesis at the start, 2 prospective operators a week, 30 submissions a week unless stated; the fee starts at the ceiling unless stated)

| Variant | Fee at week 4 / 13 / 26 / 52 | Fee over the last 13 weeks | Marginal cost a check | Break-even fee | Active validators | Submissions that waited | Validators idle | Runs collapsed (< 3 active) | Honest validator's month |
|---|---|---|---|---|---|---|---|---|---|
| Design values | $0.250 / $0.250 / $0.250 / $0.250 | $0.250 ± 0.000 | $0.094 ± 0.000 | $0.257 ± 0.000 | 18.7 ± 0.0 | 25 % ± 0 | 31 % ± 0 | 0 of 1 | $-4.14 ± 0.00 |

Marginal cost: the node's overhead per check ($0.012) plus the expected slash for an outage at the active validators' mean bond. Break-even fee: the fee at which the mean validator active for a month or more nets zero at its own checks of the last month (its fixed costs and the bond's capital spread over them). Both over the runs that didn't collapse. Usage is passed through at the unit prices in every row, so the fee is the validator's whole margin.

### The pricing attackers against their honest twins (1 seeds; a year; returns in $, with bonds' capital, running costs, fees, the usage margin, slashes, attempt fees and checks counted)

| Attacker | Pricing | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | Mean fee: attacker's run / twin's | Its family's token price (× deployment): attacker's run / twin's | What it did |
|---|---|---|---|---|---|---|---|---|
| Cartel: 6 validators refusing half their draws | design | -6,282 ± 0 | loses | -6,082 | 201 | $0.249 / $0.249 | 0.99 / 1.00 | 219 refusals, suspended 36 times, slashed $5,376 |

Pricing "design": the design's values, the fee starting at the ceiling. "moving": no slash for an honest outage and `IDLE_HIGH` 50 %, where the fee moves below the ceiling (the settling table).

## Model scores

### Herding (1 seeds; a year; 4 herders of one family among 16 honest validators; each votes the public base rate's majority, pass, instead of its finding)

| Herders | Their agreement with outcomes (twin's) | Their family's score (twin's) | Family barred, share of the year (twin's) | Bad fixes merged per 100 paid (twin's) | False verdicts proven | Return − twin's ($, ± 2 SE) | Herding |
|---|---|---|---|---|---|---|---|
| `mid` (90 %), receipts detectable | 77.3 ± 0.0 % (89.3 ± 0.0 %) | 83.5 ± 0.0 % (89.5 ± 0.0 %) | 0 ± 0 % (0 ± 0 %) | 2.94 ± 0.00 (1.20 ± 0.00) | 41.0 ± 0.0 | -10,537 ± 0 | loses |

## Model scores on the market fee

### Herding on the market fee (1 seeds; a year; 4 herders of one family beside the market's validators; herding that a re-run can't detect, the upper bound)

| Herders | Their agreement with outcomes (twin's) | Their family's score (twin's) | Family barred, share of the year (twin's) | Bad fixes merged per 100 paid (twin's) | False verdicts proven | Return − twin's ($, ± 2 SE) | Herding |
|---|---|---|---|---|---|---|---|
| `mid` (90 %), not detectable, market at design values | 77.8 ± 0.0 % (88.9 ± 0.0 %) | 79.5 ± 0.0 % (87.0 ± 0.0 %) | 0 ± 0 % (0 ± 0 %) | 4.74 ± 0.00 (1.09 ± 0.00) | 0.0 ± 0.0 | -223 ± 0 | loses |

Mean service fee in the herders' runs: `mid` (90 %) (market at design values): $0.250.

## Acceptance criteria

### Acceptance criteria for open validators (1 seeds; sweeps on 1; ± 2 standard errors)

| Criterion | Verdict | What decides it |
|---|---|---|
| Each open-validator attacker loses against its honest twin | **not met** | 2 of 4 don't lose: Colluding lone validator (the genesis, bonded $100) (+4,201 ± 0 $); Constitution coalition (5 early validators) (+36,911 ± 0 $) |
| Each pricing attacker loses against its honest twin | **met** | all 1 lose; the closest: Cartel: 6 validators refusing half their draws (-6,282 ± 0 $) |
| Each proof-level attacker loses against its honest twin | **not met** | 1 of 1 don't lose: Test liar: the genesis at C ($10 at k = 1, 7-day window), 5 bad fixes a week (+156 ± 0 $) |
| Each scoring attacker (the herders) loses against its honest twin | **met** | all 2 lose; the closest: Herders: `mid` (90 %), not detectable, market at design values (-223 ± 0 $) |
| The service fee settles within the published margin of validators' real cost | **not met (the fee never leaves its ceiling, so it doesn't find the cost; validators' entry and exit make the cost find the fee)** | the margin isn't published. Measured (design values, from the ceiling): the fee over the last 13 weeks $0.250, within one `FEE_STEP` of the $0.25 ceiling in 1 of 1 runs; validators' marginal cost $0.094 a check (2.7 ×), break-even fee $0.257 |
| A sybil just under the published share never holds a majority of a panel of k ≥ 3, under the caps | **not met (at any share tried)** | the share isn't published. Measured: a sybil spread over 3 hosts, TEE types and families holds one at every share tried, but does on 6.10 % of panels at 32 %; one on a single host, TEE type and family never does, at any share tried (to 32 %) |
| A sybil at the published share: the report gives how often it holds a majority, what it passes, and how often it's caught | **met** | reported (the sybil tables). At 32 %, spread: a majority on 6.7 % of its own panels and 6.10 % of all panels of k ≥ 3, 20.0 bad fixes paid, 7.0 false verdicts proven in a year |
| The colluding lone validator: each bad fix it passes is challenged and reversed before payment, in at least the published share of runs | **not met (for any published share above 0)** | the share isn't published. Measured (the genesis, 5 bad fixes a week, k = 1's 72-hour window): every bad fix reversed before payment in 0 of 1 runs. Over the 1 runs, 0 of the 265 bad fixes it passed were reversed (0 %); 125.0 were paid a run |
| The constitution waits for the network: no ADR passes while fewer than K_MAX validators are eligible | **met** | ADRs passed while fewer than K_MAX were eligible: 0 (mean a run, over Constitution coalition (5 early validators)) |
| Every earlier criterion holds or is named | **met** | named, not re-run: v3's simulation doesn't re-run v2's market, checking, token or split criteria. Their latest results are reports/acceptance-market-v4.md, acceptance-checking-v6.md, acceptance-modes-v5.md, tokens-v4.md and split-v1.md |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | **not met** | 5 of 10 criteria not met |
