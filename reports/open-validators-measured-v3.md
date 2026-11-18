# Open validators with measured judges, v3: seats by rank, the solver's deposit and the appeal (proof-of-fix#236, task 10.1; 2026-11-15)

**Status: exploratory.** It continues [`open-validators-measured-v1.md`](open-validators-measured-v1.md) and [`-v2.md`](open-validators-measured-v2.md). On 2026-11-14 the owner agreed four rules (design D20–D23 of `openspec/changes/proof-of-fix-132-open-validators/`) and left their values open. This report plays the rules out on proof-of-fix#160's measured verdicts and the market fee, each beside its alternative on the same seeds, so that a new parameters ADR can fix the values (task 10.2). Seeds 1–40, the seeds every earlier round used, so nothing here is confirmatory.

**Command:** `python3 -m pof.sim.openval.sizing --seeds 40 --jobs 15` prints every table in the appendix, in about 15 minutes. Every ± is two standard errors of the mean. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json`.

**Two kinds of bad fix,** as in v1, each run on its own: the 100 fixes the hidden tests fail ("the tests fail them"), and the 78 that pass the tests and are wrong ("pass the tests, wrong"). Every table gives both.

**Rows marked "post hoc"** were added after the first 40-seed run's results were seen. Section 1 lists what else changed after seeing results.

## In brief
- **The owner's condition on the appeal panel is not met.** An appeal panel drawn from the families that did not judge, contenders included, passes 81 % ± 1 of the correct rejections appealed to it (fixes the tests fail) and 81 % ± 1 (fixes that pass the tests). A solver of bad fixes that appeals every rejection gains +$10,631 ± 452 and +$8,177 ± 356 a year over the same solver that never appeals.
- **Neither alternative D23 names repairs it.** "Every appeal judge must pass" still overturns 31 % ± 1 and 39 % ± 1, and the appealing solver still gains. "The seated families' own next draw" overturns nothing, and restores no wrongly rejected good fix either: the same model gives the same verdict.
- **Seats by rank work as designed when the scores are true.** On known answers, `SEAT_MARGIN` 5 and `CAP_MIN_FAMILIES` 3 give 4.5 ± 0.2 and 8.5 ± 0.2 bad fixes per 100 paid with disputes, against 17.8 ± 1.2 and 14.3 ± 1.0 for v3 as designed, and nothing waits.
- **The live score (D23) keeps whoever sits.** Where three families are level on known answers, the genesis family holds the seats 87 % ± 7 of the year. A better family that joins later is not seated within the year, in any of 40 runs, unless the appeal feeds the score.
- **`SOLVER_DEPOSIT_BPS` 2,500 is too low on fixes that pass the tests:** the bad-fix solver still gains +$1,191 ± 369 a year. At 4,000 it loses $1,769 ± 394, if contenders find a failing test for half of the bad fixes they flag (assumed).
- **The market fee falls to its floor ($0.01) under seats by rank,** because contenders count as idle validators and are never drawn.
- **A new family starting as a contender keeps a weak model off the panels** (4.5 ± 0.4 bad fixes per 100 paid, against 10.7 ± 1.3 with D14's neutral start).

### The values, for the parameters ADR (task 10.2)

| Parameter | The design's proposal | Recommended | The number that decides it |
|---|---|---|---|
| `SEAT_MARGIN` | 5 points | **5 points** | On known answers every value tried from 2 to 25 seats the same families. Below 2, three level families lose their seats: 31.6 % ± 0.4 of good fixes go unpaid at 0 and 16.8 % ± 0.9 at 1, against 9.0 % ± 0.3 from 2 |
| `SCORE_MIN` (in the seat rule) | 70 % | **70 %** | It, not the margin, keeps weak families out: at 50 % with a margin of 40, 13.2 ± 0.3 bad fixes per 100 paid against 4.5 ± 0.2 |
| `CAP_MIN_FAMILIES` | 3 | **3** | At 2, two capped families can't fill a panel of 3: 81.6 % ± 0.3 of submissions wait. At 4, three uncapped families do slightly worse (10.4 % ± 0.5 of good fixes unpaid against 9.0 % ± 0.3) |
| `SOLVER_DEPOSIT_BPS` | 2,500 | **4,000**, on the condition that disputes work as assumed | Fixes that pass the tests: the bad-fix solver's return is +$1,191 ± 369 at 2,500 and −$1,769 ± 394 at 4,000. It costs an honest solver $5.36 ± 0.13 a good fix against $3.95 ± 0.08 |
| Where a rejected fix's deposit goes | the issue's bounty | **the bounty, at 4,000**; the sponsors' pool if the share stays at 2,500 | At 2,500 a solver that retries the same issue gets its deposits back with the bounty: +$12,152 ± 2,283 against +$4,573 ± 605 to the pool. At 4,000 it loses either way (post hoc) |
| `EVIDENCE_REWARD_BPS` | 1,000 | **1,000** (the simulation doesn't decide it) | An honest contender running GPT-6.1 nets +$497 ± 50 a year with no reward, +$760 ± 71 at 1,000 and +$1,155 ± 101 at 2,500: the deposit alone already pays a search of $0.50 (assumed) |
| `EVIDENCE_STAKE` | not given | **the larger of $5 and 10 % of the bounty**, to re-derive from task 10.3 | If a wrong test is accepted 1 time in 5, a disputer with no evidence gains +$3,880 ± 192 a year at $5 and +$2,733 ± 194 at 5 %; at 10 % no test is worth posting |
| The appeal panel (`APPEAL`) | the families that didn't judge, contenders included | **not this panel; no appeal until rejections have another source of known answers** | 81 % ± 1 of correct rejections overturned; the appealing solver gains +$10,631 ± 452 |
| `APPEAL_WINDOW` | not given | no value | No result here depends on it. It only sets how long a rejected fix's deposit stays locked |
| A new family's start | a contender | **a contender** | A weak newcomer: 4.5 ± 0.4 bad fixes per 100 paid as a contender, 10.7 ± 1.3 with the neutral start |

Two switches the simulation had to add, for the same ADR:

| Switch | Recommended | The number that decides it |
|---|---|---|
| `IDLE_COUNTS`: which validators D9's idle signal counts | **seated validators only** | Counting every active validator, the fee ends at $0.010 ± 0.000; counting seated ones, at $0.238 ± 0.007 |
| `CONTENDER_SHADOWS`: contender shadows drawn with each panel | **leave at the panel's own (1) until the score has known answers for rejections** | With six, and no appeal, the strictest judge takes the seats: GPT-6.1 holds them 61 % ± 9 of the year and 22.3 % ± 2.1 of good fixes go unpaid |

## 1. What was added to the model
Each rule is a named field of `Params` (`pof/sim/openval/params.py`), off by default, so every earlier report still reproduces. `params.D236` sets the proposal.

| Field | v3 (default) | The proposal (`D236`) | What it switches |
|---|---|---|---|
| `SEAT_RULE` | `min` | `rank` | D20: counted panels drawn from the families at `SCORE_MIN` or above **and** within `SEAT_MARGIN` of the best |
| `SEAT_MARGIN` | (unused) | 0.05 | |
| `CAP_MIN_FAMILIES` | (unused) | 3 | D20: the family cap applies only while this many families are seated |
| `NEW_FAMILY_START` | `neutral` | `contender` | D23: a family with no verdicts earns its seat on a block of 100 live shadow verdicts |
| `SOLVER_DEPOSIT_BPS` | 0 | 2,500 | D22: the solver's deposit, a share of the bounty |
| `SOLVER_DEPOSIT_TO` | `bounty` | `bounty` | D22: where a rejected fix's deposit goes; `pool` is the alternative |
| `EVIDENCE_REWARD_BPS` | 0 | 1,000 | D22: the disputer's share of the bounty, beside the deposit |
| `EVIDENCE_STAKE`, `EVIDENCE_STAKE_BPS` | 0, 0 | $5, 0 | D21: a test's stake: the larger of the flat amount and the share |
| `APPEAL` | `off` | `others` | D23: where the appeal panel is drawn from: `others`, `others_seated`, `seated` |
| `APPEAL_PASS_RULE` | `majority` | `majority` | D23's other alternative: `unanimous` |
| `APPEAL_WINDOW_H` | 72 | 72 | |
| `CONTENDER_SHADOWS` | 0 | 0 | contender shadows per draw (0: the panel's own number) |
| `IDLE_COUNTS` | `active` | `active` | D9's idle signal: every active validator, or `seated` ones only |

- **The deposit's three destinations** (`Net._settle_deposit`): back to the solver when the fix is paid or withdrawn unjudged; to the issue's bounty (or the pool) when it is rejected and no appeal passes it; to the disputer, with the reward, when a test reverses its pass. A test checks that no judge's income changes with the deposit.
- **Where the seat rule reads a score** is the world's (`World.seat_scores`, `pof/sim/openval/seats.py`):
  - **"known":** the family's balanced score on #160's known answers. It is what a perfect source of final outcomes would give: an upper bound, as in v1 and v2.
  - **"live":** D23's rule. A seated family's score is its agreement with final outcomes over its last 200 counted verdicts; a contender's is its last complete block of 100 shadow verdicts. Final outcomes are the network's own: a verdict, unless a test or an appeal changed it.
- **The parameter sweeps run on known answers,** so that each table moves one rule. Section 3 then runs the same rule on live scores.
- **The base of every sweep** is the proposal without the appeal: seats by rank, margin 5, cap from 3 families, deposit 2,500, reward 1,000, stake $5, seven families, disputes finding a test 1 time in 2, a wrong test accepted 1 time in 20.
- **The fee is the market's** (`pricing.Market`: the queue controller and the posted unit prices), on the measured world's validators. The market's entry and exit are switched off: its entry rule knows nothing of what a contender earns by disputing. Report v3's judged spammer runs in the full market, with entry.
- **The new actors,** each against its honest twin: a solver of bad fixes that appeals every rejection (its twin: the same solver, never appealing); a solver that tries the same issue again after a rejection; a disputer with no evidence (its twin posts nothing); an honest contender.

**Readings the design leaves open,** chosen for the simulation and stated so the ADR can confirm or change them:
1. **Someone must judge.** When no family meets the seat rule, the best-scoring seated family keeps its seat. Without this the network halts, and contenders, which shadow only drawn submissions, could never earn a seat.
2. **The appellant pays its appeal panel's checks,** as a solver pays its counted panel's.
3. **An appeal with no panel after one `APPEAL_WINDOW` lapses,** and the rejection stands. D4's "the challenge waits" would leave the fix never final.
4. **The family cap applies on an appeal panel** when the families it may draw from number at least `CAP_MIN_FAMILIES`.
5. **The deposit's share is taken on the bounty as it stands,** top-ups from earlier rejections included (the spec's $20 on $80, then $25 on $100).
6. **A test's challenge panel is not simulated judge by judge.** Whether it accepts a test is one draw at the assumed rate. Its cost is counted and charged to nobody.
7. **Nobody challenges a verdict only because another model disagrees** (D21: the re-run challenge "stays for fabricated receipts"). v1 and v2 let a volunteer running a random model do so; one row in section 2 shows what that does.
8. **Pay by score (D14) is not applied under seats by rank.** With one family seated its normalised factor is 1.

**What changed after seeing results,** so that nothing here reads as planned when it was not:
- **After 4-seed trial runs, before any 40-seed run:** second-opinion challenges were switched off (reading 7) and the "verdicts never final" column added, because one family on every seat left such challenges waiting for good; an appeal with no panel was made to lapse (reading 3), for the same reason; the disputer's twin was changed from an honest contender to a twin that posts nothing, and the honest contender given rows of its own; deposit shares of 5,000 and 7,500 and the solver that retries were added to the sweep; the new-family rows with the appeal were added.
- **After the first 40-seed run:** every row marked "post hoc"; and v3's own reference rows were given back their second-opinion challenges, which are v3's rule (they then reproduce v1's figures).
- **No acceptance threshold was moved,** and no row was dropped.

**What is assumed, measured or chosen:**

| Input | Value | Status |
|---|---|---|
| A judge's verdict on a fix | its family's recorded verdict in #160, on a case drawn for the fix | **measured** |
| A model asked again | repeats its verdict | assumed (#160 took one verdict a case) |
| How often a flagged bad fix yields a failing test (the evidence-find rate) | 1 time in 2; 0 in the "no disputes" rows | **assumed, not measured**: task 10.3 |
| How often a test that states the wrong requirement is accepted (the wrong-test rate) | 1 time in 20; 1 in 5 in the sensitivity rows | **assumed, not measured**: task 10.3 |
| Whether evidence exists for a fix | one draw per fix, shared by every contender | assumed |
| Which rejections an honest solver appeals | every rejected good fix and no bad one; beside it, every rejection | assumed |
| What a contender's search costs | $0.50 a fix | assumed |
| The solver of bad fixes | 5 a week, #160's honest failures; what a bad fix costs to write is not counted | assumed |
| The share of bad fixes, arrivals, bounties | 25 %, 30 a week, median $86 (report v3's world) | assumed |
| The network | four validators a family at the start, bonds of $1,250, half a newcomer a week of any family | assumed |
| The open-weight seat the price table doesn't list (Nemotron) | priced at Llama's rates | assumed |
| `EVIDENCE_STAKE` $5 and `APPEAL_WINDOW` 72 h | placeholders, set before the runs | chosen |
| The eight readings above | | chosen |

## 2. Seats by rank on known answers: `SEAT_MARGIN` and `CAP_MIN_FAMILIES`
On known answers the scores are: Opus 5.5 88 %, GPT-6.1 65 %, Gemini 3.1 Pro 60 %, the four others 50–56 % (the tests fail them); GPT-6.1 75.4 %, Opus 5.5 74.6 %, Gemini 3.1 Pro 74.0 %, the four others 51–59 % (pass the tests, wrong).

**Bad fixes the tests fail:**

| Rule | Seated | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Submissions that waited | Verdicts never final |
|---|---|---|---|---|---|---|
| v3 as designed, with test disputes | by v3's scores | 8.8 ± 1.2 | 24.7 % ± 2.3 | $1.31 ± 0.09 | 79.6 % ± 1.5 | 23.6 % ± 2.5 |
| `SEAT_MARGIN` 0 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 1 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 2 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| **`SEAT_MARGIN` 5** | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 10 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 25 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 25, `SCORE_MIN` 50 % | Opus 5.5, GPT-6.1 | 6.0 ± 0.4 | 16.7 % ± 0.9 | $5.99 ± 0.23 | 0.0 % ± 0.0 | 1.5 % ± 0.2 |
| `SEAT_MARGIN` 40, `SCORE_MIN` 50 % | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, the four others | 13.2 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.09 | 0.0 % ± 0.0 | 0.0 % ± 0.0 |
| `CAP_MIN_FAMILIES` 1, margin 5 | Opus 5.5 | 4.4 ± 0.6 | 8.5 % ± 0.6 | $1.74 ± 0.06 | 81.6 % ± 0.3 | 0.0 % ± 0.0 |
| `CAP_MIN_FAMILIES` 2, margin 1 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `CAP_MIN_FAMILIES` 3, margin 1 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| `CAP_MIN_FAMILIES` 4, margin 5 | Opus 5.5 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 0.1 % ± 0.0 | 0.0 % ± 0.0 |
| margin 5, with second-opinion challenges | Opus 5.5 | 4.5 ± 0.2 | 10.0 % ± 0.3 | $4.23 ± 0.09 | 0.1 % ± 0.0 | 2.7 % ± 0.2 |

**Bad fixes that pass the tests and are wrong:**

| Rule | Seated | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Submissions that waited | Verdicts never final |
|---|---|---|---|---|---|---|
| v3 as designed, with test disputes | by v3's scores | 9.7 ± 0.6 | 26.1 % ± 2.0 | $1.31 ± 0.07 | 76.2 % ± 2.2 | 23.0 % ± 2.4 |
| `SEAT_MARGIN` 0 | GPT-6.1 | 7.3 ± 0.3 | 31.6 % ± 0.4 | $8.49 ± 0.12 | 3.5 % ± 0.2 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 1 | Opus 5.5, GPT-6.1 | 9.0 ± 0.2 | 16.8 % ± 0.9 | $6.01 ± 0.23 | 0.0 % ± 0.0 | 1.4 % ± 0.2 |
| `SEAT_MARGIN` 2 | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| **`SEAT_MARGIN` 5** | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| `SEAT_MARGIN` 10 | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| `SEAT_MARGIN` 25 | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| `SEAT_MARGIN` 25, `SCORE_MIN` 50 % | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, the four others | 12.8 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.08 | 0.0 % ± 0.0 | 0.0 % ± 0.0 |
| `SEAT_MARGIN` 40, `SCORE_MIN` 50 % | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, the four others | 12.8 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.08 | 0.0 % ± 0.0 | 0.0 % ± 0.0 |
| `CAP_MIN_FAMILIES` 1, margin 5 | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| `CAP_MIN_FAMILIES` 2, margin 1 | Opus 5.5, GPT-6.1 | 8.0 ± 0.6 | 29.2 % ± 1.0 | $3.66 ± 0.09 | 81.6 % ± 0.3 | 22.3 % ± 0.9 |
| `CAP_MIN_FAMILIES` 3, margin 1 | Opus 5.5, GPT-6.1 | 9.0 ± 0.2 | 16.8 % ± 0.9 | $6.01 ± 0.23 | 0.0 % ± 0.0 | 1.4 % ± 0.2 |
| `CAP_MIN_FAMILIES` 4, margin 5 | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.9 ± 0.3 | 10.4 % ± 0.5 | $4.30 ± 0.13 | 0.0 % ± 0.0 | 0.2 % ± 0.1 |
| margin 5, with second-opinion challenges | Opus 5.5, GPT-6.1, Gemini 3.1 Pro | 8.5 ± 0.2 | 9.1 % ± 0.3 | $3.98 ± 0.09 | 0.0 % ± 0.0 | 0.3 % ± 0.1 |

- **The margin matters only where families are level.** On fixes the tests fail, Opus 5.5 is 23 points ahead and the next family, at 65 %, is below `SCORE_MIN`: every margin seats Opus alone. On fixes that pass the tests, three families are within 1.4 points: a margin of 0 seats GPT-6.1 alone, which rejects 30 % of good fixes; 1 seats two; from 2 on, all three.
- **`SCORE_MIN` does the work above the margin.** With the minimum lowered to 50 %, a margin of 25 seats GPT-6.1 beside Opus on the first pool (6.0 ± 0.4 per 100 paid, 16.7 % ± 0.9 of good fixes unpaid) and 40 seats everyone (13.2 ± 0.3).
- **`CAP_MIN_FAMILIES` can't be below 3.** A cap of (k − 1) / 2 a family leaves one or two families unable to fill a panel of 3, so panels fall to k = 1 and 81.6 % ± 0.3 of submissions wait, with one family seated and with two alike.
- **Capping three level families is slightly better than not:** 8.5 ± 0.2 against 8.9 ± 0.3 per 100 paid, and 9.0 % ± 0.3 against 10.4 % ± 0.5 of good fixes unpaid.
- **"Verdicts never final" is a new column,** added when the first quick runs showed it (post hoc): a verdict whose challenge has waited four weeks for a panel. D4 asks for a fresh panel larger than the original. With one family on all seven seats there are rarely seven more of it, so a volunteer's second-opinion challenge freezes the verdict for good: 2.7 % ± 0.2 of verdicts with one family seated. A good fix frozen that way is counted here as unpaid.
- **v3 as designed has the same stall, and worse:** 23.6 % ± 2.5 of its verdicts are never final. v1 and v2 did not count them, so their "good fixes rejected" understates what v3 leaves unpaid.

## 3. Seats by rank on live scores (D23)
The same rule, with each family's score read from the network's own final outcomes. The genesis validator's family is Opus 5.5 in every row.

**Bad fixes the tests fail:**

| Scores | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | No family met the rule, share of the year |
|---|---|---|---|---|---|---|
| known answers, margin 5 (the upper bound) | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 2, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| **live, margin 5, no appeal** | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 10, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, no disputes and no appeal | 6.0 ± 0.2 | 6.0 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, appeal to other families (majority) | 4.3 ± 0.2 | 3.3 % ± 0.2 | 99 % ± 2 | 1 % ± 2 | 0 % ± 0 | 1 % ± 1 |
| live, margin 5, appeal to the seated families | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, no appeal, six contender shadows a draw | 4.5 ± 0.2 | 9.0 % ± 0.3 | 100 % ± 1 | 0 % ± 1 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, no appeal, score window 1,400 verdicts (post hoc) | 4.5 ± 0.2 | 8.9 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, appeal to other families, score window 1,400 (post hoc) | 4.2 ± 0.2 | 3.3 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |

**Bad fixes that pass the tests and are wrong:**

| Scores | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | No family met the rule, share of the year |
|---|---|---|---|---|---|---|
| known answers, margin 5 (the upper bound) | 8.5 ± 0.2 | 9.0 % ± 0.3 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 |
| live, margin 2, no appeal | 9.6 ± 0.3 | 10.0 % ± 1.0 | 92 % ± 6 | 5 % ± 4 | 2 % ± 3 | 5 % ± 1 |
| **live, margin 5, no appeal** | 9.5 ± 0.3 | 11.3 % ± 1.5 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 3 % ± 1 |
| live, margin 10, no appeal | 9.3 ± 0.3 | 12.5 % ± 1.8 | 81 % ± 8 | 17 % ± 8 | 4 % ± 4 | 2 % ± 0 |
| live, margin 5, no disputes and no appeal | 13.8 ± 0.3 | 6.0 % ± 0.2 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, appeal to other families (majority) | 8.5 ± 0.4 | 3.9 % ± 0.3 | 69 % ± 9 | 21 % ± 8 | 11 % ± 6 | 12 % ± 2 |
| live, margin 5, appeal to the seated families | 9.5 ± 0.3 | 10.3 % ± 1.3 | 89 % ± 6 | 7 % ± 5 | 4 % ± 4 | 4 % ± 1 |
| live, margin 5, no appeal, six contender shadows a draw | 8.4 ± 0.4 | 22.3 % ± 2.1 | 39 % ± 9 | 61 % ± 9 | 1 % ± 1 | 2 % ± 1 |
| live, margin 5, no appeal, score window 1,400 verdicts (post hoc) | 9.6 ± 0.3 | 9.9 % ± 0.9 | 96 % ± 4 | 6 % ± 5 | 0 % ± 0 | 0 % ± 0 |
| live, margin 5, appeal to other families, score window 1,400 (post hoc) | 8.9 ± 0.3 | 3.8 % ± 0.3 | 86 % ± 7 | 20 % ± 7 | 13 % ± 6 | 1 % ± 1 |

- **Where one family is far ahead, live and known scores agree.** On fixes the tests fail, Opus 5.5 holds the seats all year in every row but the appeal's.
- **Where three families are level, the live score does not seat them.** On known answers all three sit all year. Live, the genesis family sits 87 % ± 7 of the year, GPT-6.1 11 % ± 7 and Gemini 3.1 Pro 2 % ± 2. The cost is 9.5 ± 0.3 bad fixes per 100 paid against 8.5 ± 0.2.
- **Why:** final outcomes are mostly the seated family's own verdicts, so it agrees with them and a contender is scored on its agreement with the incumbent. With no disputes and no appeal the incumbent sits 100 % ± 0 of the year: nothing ever tells the score it was wrong.
- **The margin hardly matters live:** 9.6 ± 0.3, 9.5 ± 0.3 and 9.3 ± 0.3 per 100 paid at 2, 5 and 10 points.
- **More contender shadows, with disputes only, seat the strictest judge.** With six shadows a draw, GPT-6.1 holds the seats 61 % ± 9 of the year and 22.3 % ± 2.1 of good fixes go unpaid. This is v2's finding played out: tests correct only passes, so a judge that rejects good fixes is never caught.
- **The appeal to other families does feed the score from the other side,** as D23 intends: with it the three level families share the year 69 % ± 9, 21 % ± 8 and 11 % ± 6. But that appeal is the one section 5 shows to be unsafe, and with it no family meets the rule 12 % ± 2 of the year.
- **The score window is short when one family holds every seat** (found while reading the first runs; the two rows are post hoc). Seven judges of one family give seven identical verdicts, so 200 counted verdicts are about 29 fixes. A window of 1,400 verdicts cuts the share of the year in which no family meets the rule from 12 % ± 2 to 1 % ± 1.

## 4. The solver's deposit
Seats on known answers, disputes on, no appeal. The solver of bad fixes submits 5 a week and colludes with nobody; its twin submits nothing, so its return is what it earns.

| `SOLVER_DEPOSIT_BPS` | An honest solver's cost per good fix ($): the tests fail them | pass the tests, wrong | The bad-fix solver's return ($ a year): the tests fail them | pass the tests, wrong | …with no disputes: the tests fail them | pass the tests, wrong |
|---|---|---|---|---|---|---|
| 0 | $1.64 ± 0.03 | $1.60 ± 0.00 | +2,741 ± 204 | +6,126 ± 370 | +4,229 ± 238 | +9,317 ± 403 |
| 500 | $2.09 ± 0.03 | $2.07 ± 0.02 | +1,598 ± 206 | +5,139 ± 365 |  |  |
| 1,000 | $2.55 ± 0.04 | $2.54 ± 0.03 | +454 ± 213 | +4,152 ± 363 |  |  |
| 1,500 | $3.01 ± 0.06 | $3.01 ± 0.05 | -689 ± 225 | +3,165 ± 363 |  |  |
| 2,500 | $3.93 ± 0.08 | $3.95 ± 0.08 | -2,976 ± 262 | +1,191 ± 369 | -1,120 ± 248 | +5,191 ± 364 |
| 4,000 | $5.30 ± 0.13 | $5.36 ± 0.13 | -6,407 ± 337 | -1,769 ± 394 | -4,329 ± 298 | +2,715 ± 355 |
| 5,000 | $6.22 ± 0.16 | $6.30 ± 0.16 | -8,694 ± 395 | -3,743 ± 419 | -6,468 ± 343 | +1,065 ± 356 |
| 7,500 | $8.51 ± 0.24 | $8.65 ± 0.24 | -14,412 ± 552 | -8,678 ± 504 | -11,816 ± 473 | -3,061 ± 383 |

- **The break-even differs by kind of bad fix.** On fixes the tests fail, the solver stops gaining between 1,000 and 1,500. On fixes that pass the tests, where three seated families pass a bad fix more often, it stops between 2,500 and 4,000.
- **2,500, the design's value, leaves a gain on the second kind:** +$1,191 ± 369 a year, 65 bad fixes paid of 261 submitted (25 %).
- **Disputes carry part of the deterrent.** With no disputes the solver still gains at 4,000 on the second kind (+$2,715 ± 355) and stops only between 5,000 and 7,500 (post hoc rows). The evidence-find rate is assumed, so 4,000 is conditional on task 10.3.
- **The honest cost is linear in the share:** about $2.29 ± 0.08 of deposits lost per good fix at 2,500 and $3.66 ± 0.13 at 4,000, because 8.9 % ± 0.2 of good fixes end unpaid (the panel's rejections, and wrong tests accepted 1 time in 20).
- **Wrong tests are the larger part of that cost if they are accepted more often.** At 1 time in 5, 17.8 % ± 0.4 of good fixes go unpaid and a good fix costs $6.21 ± 0.11.

**Where the deposit goes, against a solver that tries the same issue again.** It is the only solver of its issues, so a deposit added to the bounty comes back to it when one of its fixes is paid. It retries without a stop rule.

| The solver | Return ($ a year): the tests fail them | pass the tests, wrong |
|---|---|---|
| Tries each issue up to six times, deposit 2,500 to the issue's bounty (the owner's decision) | -18,162 ± 1,296 | +6,176 ± 994 |
| Tries each issue up to six times, deposit 2,500 to the sponsors' pool | -11,983 ± 801 | +3,779 ± 673 |
| Tries each issue up to 21 times, deposit 2,500 to the issue's bounty (the owner's decision) | -98,721 ± 11,985 | +12,152 ± 2,283 |
| Tries each issue up to 21 times, deposit 2,500 to the sponsors' pool | -19,464 ± 1,316 | +4,573 ± 605 |
| Tries each issue up to 21 times, deposit 4,000 to the issue's bounty (post hoc) | -1,038,175 ± 118,779 | -35,882 ± 19,157 |
| Tries each issue up to 21 times, deposit 4,000 to the sponsors' pool (post hoc) | -43,043 ± 2,276 | -7,133 ± 914 |

- **Where bad fixes pass one time in four, the bounty as destination pays persistence.** At 2,500 the retrying solver earns +$12,152 ± 2,283 with the deposit going to the bounty, against +$4,573 ± 605 to the pool and +$1,191 ± 369 submitting once.
- **Where they pass one time in eight, retrying loses heavily,** and more with the bounty: each deposit is a share of a bounty that earlier deposits have grown.
- **At 4,000 it loses on both kinds, either way** (post hoc). The owner's decision, the bounty, holds at 4,000. At 2,500 the pool is the safer destination.
- **This case is the attacker's best:** no other solver takes the issue. With competitors, its deposits go to whoever is paid.

**Report v3's judged spammer** (a bad fix a day, three validators of its own, four families, the market with entry), owed since v2:

| `SOLVER_DEPOSIT_BPS` | Return − twin's ($ a year): the tests fail them | pass the tests, wrong |
|---|---|---|
| 0 | +2,027 ± 189 | +7,480 ± 323 |
| 2,500 | -2,161 ± 259 | +1,105 ± 381 |
| 4,000 (post hoc) | -4,673 ± 383 | -2,721 ± 421 |

- **It gains on measured judges with no deposit,** where report v3, on assumed judges, had it lose $915 ± 28.
- **It follows the bad-fix solver:** 2,500 stops it on the first kind of bad fix and not on the second; 4,000 stops it on both.

## 5. The appeal, and the owner's condition
**The condition (design D23, "Decided 2026-11-14"):** the appeal panel includes contenders only if the simulation shows that it does not let weaker models overturn correct rejections, so that a solver of bad fixes doesn't gain by appealing.

**First, exact counts from #160's verdicts, no simulation.** Of the fixes a seated panel rejects, the share an appeal panel of 5 passes, averaged over every panel with at most two judges a family:

| Bad fixes | Seated panel | Appeal panel of 5 drawn from | Rule | Bad fixes rejected | …of which the appeal passes | Good fixes rejected | …of which the appeal passes |
|---|---|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 | the other families of the seven | majority | 82 | 80 % | 3 | 100 % |
| the tests fail them | Opus 5.5 | the other families of the seven | every judge must pass | 82 | 39 % | 3 | 40 % |
| the tests fail them | Opus 5.5 | the other frontier families only | majority | 82 | 55 % | 3 | 67 % |
| the tests fail them | Opus 5.5 | the other frontier families only | every judge must pass | 82 | 41 % | 3 | 44 % |
| the tests fail them | GPT-6.1 | the other families of the seven | majority | 60 | 73 % | 15 | 89 % |
| the tests fail them | GPT-6.1 | the other families of the seven | every judge must pass | 60 | 24 % | 15 | 55 % |
| the tests fail them | GPT-6.1 | the other frontier families only | majority | 60 | 37 % | 15 | 90 % |
| the tests fail them | GPT-6.1 | the other frontier families only | every judge must pass | 60 | 17 % | 15 | 83 % |
| pass the tests, wrong | Opus, GPT-6.1, Gemini (majority) | the other families of the seven | majority | 49 | 81 % | 3 | 100 % |
| pass the tests, wrong | Opus, GPT-6.1, Gemini (majority) | the other families of the seven | every judge must pass | 49 | 44 % | 3 | 73 % |
| pass the tests, wrong | Opus 5.5 | the other families of the seven | majority | 43 | 59 % | 3 | 100 % |
| pass the tests, wrong | Opus 5.5 | the other families of the seven | every judge must pass | 43 | 12 % | 3 | 40 % |
| pass the tests, wrong | Opus 5.5 | the other frontier families only | majority | 43 | 16 % | 3 | 67 % |
| pass the tests, wrong | Opus 5.5 | the other frontier families only | every judge must pass | 43 | 7 % | 3 | 44 % |

- **The other six families pass four in five of the bad fixes Opus 5.5 correctly rejected.** Five of the nine models measured pass 70–92 % of bad fixes, and a majority of them outvotes the rest.
- **Keeping the weak families off helps and is not enough:** GPT-6.1 and Gemini 3.1 Pro alone still pass 55 % of Opus's correct rejections on the first kind of bad fix.

**The network** (seats on known answers, deposit 2,500, disputes on). "No panel": an appeal that found no validator the rule allows, or none within the appeal period.

**Bad fixes the tests fail:**

| Appeal panel | Honest solvers appeal | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Correct rejections overturned, of those appealed | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Appeals with no panel, a year |
|---|---|---|---|---|---|---|---|---|
| no appeal | good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| **other families, contenders included; majority** (the owner's decision) | good fixes only | 4.2 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | n/a | 0.0 ± 0.0 | 95 % ± 1 | 0 ± 0 |
| other families, contenders included; every judge must pass | good fixes only | 4.4 ± 0.2 | 7.5 % ± 0.2 | $3.61 ± 0.08 | n/a | 0.0 ± 0.0 | 24 % ± 2 | 0 ± 0 |
| other families, seated only | good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| the seated families' next draw | good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| **other families, contenders included; majority** (the owner's decision) | every rejection | 13.8 ± 0.4 | 3.3 % ± 0.2 | $2.54 ± 0.05 | 81 % ± 1 | 128.5 ± 4.0 | 95 % ± 1 | 0 ± 0 |
| other families, contenders included; every judge must pass | every rejection | 8.4 ± 0.3 | 7.5 % ± 0.2 | $3.62 ± 0.07 | 31 % ± 1 | 48.9 ± 2.1 | 24 % ± 2 | 0 ± 0 |
| other families, seated only | every rejection | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 382 ± 7 |
| the seated families' next draw | every rejection | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 380 ± 7 |
| other families, contenders included; majority; **no disputes** | every rejection | 22.0 ± 0.4 | 0.0 % ± 0.0 | $1.70 ± 0.03 | 81 % ± 1 | 255.2 ± 6.8 | 100 % ± 0 | 0 ± 0 |

**Bad fixes that pass the tests and are wrong:**

| Appeal panel | Honest solvers appeal | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Correct rejections overturned, of those appealed | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Appeals with no panel, a year |
|---|---|---|---|---|---|---|---|---|
| no appeal | good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| **other families, contenders included; majority** (the owner's decision) | good fixes only | 8.1 ± 0.2 | 3.5 % ± 0.2 | $2.57 ± 0.06 | n/a | 0.0 ± 0.0 | 94 % ± 1 | 0 ± 0 |
| other families, contenders included; every judge must pass | good fixes only | 8.2 ± 0.2 | 5.2 % ± 0.2 | $3.01 ± 0.06 | n/a | 0.0 ± 0.0 | 65 % ± 2 | 0 ± 0 |
| other families, seated only | good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.93 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| the seated families' next draw | good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.97 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 23 ± 4 |
| **other families, contenders included; majority** (the owner's decision) | every rejection | 14.9 ± 0.3 | 3.5 % ± 0.2 | $2.65 ± 0.06 | 81 % ± 1 | 97.8 ± 3.7 | 94 % ± 1 | 0 ± 0 |
| other families, contenders included; every judge must pass | every rejection | 11.8 ± 0.3 | 5.2 % ± 0.2 | $3.07 ± 0.06 | 39 % ± 1 | 48.4 ± 2.4 | 65 % ± 1 | 0 ± 0 |
| other families, seated only | every rejection | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.93 ± 0.08 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 310 ± 7 |
| the seated families' next draw | every rejection | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.98 ± 0.08 | 0 % ± 0 | 0.0 ± 0.0 | 0 % ± 0 | 104 ± 15 |
| other families, contenders included; majority; **no disputes** | every rejection | 22.6 ± 0.4 | 0.3 % ± 0.1 | $1.81 ± 0.03 | 80 % ± 1 | 194.5 ± 4.9 | 99 % ± 1 | 0 ± 0 |

**The solver of bad fixes that appeals every rejection,** against the same solver that never appeals (deposit 2,500):

| Appeal panel | Return − twin's ($ a year): the tests fail them | What it got | Return − twin's: pass the tests, wrong | What it got |
|---|---|---|---|---|
| **other families, contenders included; majority** (the owner's decision) | +10,631 ± 452 | 212 appeals, 170 upheld, 86 of them paid; 117 bad fixes paid of 261 (twin: 32) | +8,177 ± 356 | 163 appeals, 131 upheld, 66 of them paid; 130 bad fixes paid of 261 (twin: 65) |
| other families, contenders included; every judge must pass | +3,857 ± 266 | 212 appeals, 64 upheld, 32 of them paid; 63 bad fixes paid of 261 (twin: 32) | +3,918 ± 274 | 163 appeals, 64 upheld, 32 of them paid; 96 bad fixes paid of 261 (twin: 65) |
| other families, seated only | +0 ± 0 | 212 appeals, 0 upheld, 0 of them paid; 32 bad fixes paid of 261 (twin: 32) | +0 ± 0 | 163 appeals, 0 upheld, 0 of them paid; 65 bad fixes paid of 261 (twin: 65) |
| the seated families' next draw | +28 ± 8 | 212 appeals, 0 upheld, 0 of them paid; 32 bad fixes paid of 261 (twin: 32) | -95 ± 14 | 163 appeals, 0 upheld, 0 of them paid; 65 bad fixes paid of 261 (twin: 65) |
| other families, contenders included; majority; no disputes | +21,264 ± 667 | 212 appeals, 170 upheld, 170 of them paid; 216 bad fixes paid of 261 (twin: 46) | +16,439 ± 470 | 163 appeals, 131 upheld, 131 of them paid; 228 bad fixes paid of 261 (twin: 96) |
| other families, contenders included; every judge must pass; no disputes | +8,008 ± 424 | 212 appeals, 64 upheld, 64 of them paid; 110 bad fixes paid of 261 (twin: 46) | +7,975 ± 396 | 163 appeals, 64 upheld, 64 of them paid; 160 bad fixes paid of 261 (twin: 97) |
| other families, contenders included; majority; no deposit | +8,487 ± 362 | 212 appeals, 170 upheld, 86 of them paid; 117 bad fixes paid of 261 (twin: 32) | +6,531 ± 285 | 163 appeals, 131 upheld, 66 of them paid; 130 bad fixes paid of 261 (twin: 65) |

**The condition is not met.**
- **A weak family does overturn correct rejections:** 81 % ± 1 and 81 % ± 1 of those appealed, as the exact counts predict.
- **A solver of bad fixes gains by appealing:** +$10,631 ± 452 and +$8,177 ± 356 a year over its twin, with disputes reversing about half of the appeals it wins. With no disputes it is +$21,264 ± 667 and +$16,439 ± 470.
- **The deposit doesn't stop it.** An appeal costs only its checks; the deposit was already at stake.
- **If honest solvers appealed every rejection too,** bad fixes merged would rise from 4.5 ± 0.2 to 13.8 ± 0.4 per 100 paid on the first kind, and from 8.5 ± 0.2 to 14.9 ± 0.3 on the second.

**The alternatives D23 names:**
- **Every appeal judge must pass:** it overturns 31 % ± 1 and 39 % ± 1 of correct rejections, the appealing solver still gains +$3,857 ± 266 and +$3,918 ± 274, and it restores only 24 % ± 2 and 65 % ± 2 of wrongly rejected good fixes.
- **The seated families' own next draw:** safe and empty. It overturns no correct rejection and restores no good fix, since a model asked again repeats itself (assumed, section 1). With one family on seven seats there are also too few validators left for a fresh panel: 68 ± 2 of 68 ± 2 appeals a year find none. The few dollars the appealing solver shows on the first kind of bad fix are the year's end: its last appeals had not lapsed yet.
- **Other families, seated ones only:** no panel exists. Every seated family has already judged the fix.

**What the appeal is worth to honest solvers, and so what is lost without it:** with the owner's panel, 95 % ± 1 of wrongly rejected good fixes are paid in the end, good fixes unpaid fall from 8.9 % ± 0.2 to 3.3 % ± 0.2, and a good fix costs $2.53 ± 0.05 instead of $3.93 ± 0.08. The same panel that restores them passes the bad ones: on these verdicts no panel of models tells the two apart.

## 6. The disputer without evidence, and the stake
The disputer runs no model. Its twin posts nothing, so its return is what it earns. Deposit 2,500, reward 1,000: an accepted test pays 35 % of the bounty.

| The disputer posts | Return ($ a year): the tests fail them | What it got | Return: pass the tests, wrong |
|---|---|---|---|
| Tests that pass on the fixed code, on every pass; stake $5 | -5,754 ± 52 | 1151 tests posted, 0 upheld | -6,188 ± 60 |
| Wrong tests on every pass; stake $5 | -3,394 ± 105 | 1151 tests posted, 58 upheld | -3,603 ± 111 |
| Wrong tests where it expects to gain; stake $5 | +50 ± 61 | 31 tests posted, 2 upheld | +62 ± 65 |
| Wrong tests where it expects to gain; stake $5; a wrong test accepted 1 time in 5 | +3,880 ± 192 | 865 tests posted, 172 upheld | +4,289 ± 228 |
| Wrong tests where it expects to gain; stake the larger of $5 and 5 % of the bounty | +0 ± 0 | 0 tests posted, 0 upheld | +0 ± 0 |
| Wrong tests where it expects to gain; stake the larger of $5 and 5 %; accepted 1 time in 5 | +2,733 ± 194 | 865 tests posted, 172 upheld | +3,052 ± 229 |
| Wrong tests where it expects to gain; stake the larger of $5 and 10 %; accepted 1 time in 5 | +0 ± 0 | 0 tests posted, 0 upheld | +0 ± 0 |
| Wrong tests on every pass; stake the larger of $5 and 10 %; accepted 1 time in 5 | -1,415 ± 221 | 1148 tests posted, 230 upheld | -1,425 ± 251 |

- **Tests that pass on the fixed code only lose their stakes,** as the spec's scenario says: $5,754 ± 52 a year to the solvers, and no verdict changes.
- **Tests that fail and state the wrong requirement are the real attack,** and whether it pays depends on a rate nobody has measured. A test is worth posting when (acceptance rate) × 35 % of the bounty exceeds (1 − rate) × the stake.
  - **Accepted 1 time in 20:** a flat $5 stake is enough on all but the largest bounties (+$50 ± 61, not significant), and a stake of 5 % of the bounty leaves nothing worth posting.
  - **Accepted 1 time in 5:** the disputer gains +$3,880 ± 192 at $5 and +$2,733 ± 194 at 5 %. At 10 % nothing is worth posting, and posting on every pass loses $1,415 ± 221.
- **The stake as a share of the bounty that closes it** is rate / (1 − rate) × (deposit share + reward share): 1.8 % at 1 in 20 and 8.75 % at 1 in 5 with the design's 2,500 and 1,000; 2.6 % and 12.5 % with a deposit of 4,000.
- **Hence the larger of $5 and 10 % of the bounty.** With a deposit of 4,000 it holds up to a wrong test accepted 1 time in 6. The $5 floor covers the test's panel (seven checks, about $1 to $3 at the fees seen here).
- **The harm to honest solvers is separate from the disputer's gain.** Even a disputer that loses reverses good fixes: posting wrong tests on every pass at 1 in 20 reverses 52 more good fixes a year (the tests fail them).

**An honest contender** (it searches every pass its model failed, at $0.50 a search, assumed; stake $5):

| Its model | Return ($ a year): the tests fail them | What it got | Return: pass the tests, wrong | What it got |
|---|---|---|---|---|
| GPT-6.1 | +760 ± 71 | 321 fixes searched, 25 tests upheld; $30 a reversal | +1,513 ± 105 | 348 fixes searched, 47 tests upheld; $32 a reversal |
| Opus 5.5 | +0 ± 0 | 0 fixes searched, 0 tests upheld; $0 a reversal | +118 ± 29 | 29 fixes searched, 4 tests upheld; $31 a reversal |
| DeepSeek V3.2 | +163 ± 36 | 94 fixes searched, 6 tests upheld; $28 a reversal | +382 ± 54 | 106 fixes searched, 12 tests upheld; $32 a reversal |
| GPT-6.1, `EVIDENCE_REWARD_BPS` 0 (post hoc) | +497 ± 50 | 321 fixes searched, 25 tests upheld; $20 a reversal | +1,031 ± 75 | 348 fixes searched, 47 tests upheld; $22 a reversal |
| GPT-6.1, `EVIDENCE_REWARD_BPS` 2,500 (post hoc) | +1,155 ± 101 | 321 fixes searched, 25 tests upheld; $46 a reversal | +2,236 ± 151 | 348 fixes searched, 47 tests upheld; $48 a reversal |

- **Contending pays, even with a weak model,** at the assumed search cost and find rate. Opus 5.5 has nothing to dispute on the first kind of bad fix: it is the panel.
- **The reward's share is not what makes it pay.** The solver's deposit alone covers the searches; the reward adds to it. The simulation gives no reason to move `EVIDENCE_REWARD_BPS` from 1,000, and a larger reward raises the stake a wrong test needs.
- **The contender here files before every other contender,** so these returns are one contender's best case.

## 7. A new family's start
Live scores, disputes on, no appeal unless the row says so. A family with four validators joins in week 8. "Neutral" is D14's start: every family is seated at once, until it is scored.

**A weak newcomer: Mistral Large 3** (92 % of bad fixes passed):

| It starts as | The tests fail them: bad fixes merged per 100 paid | good fixes wrongly unpaid | runs in which it was ever seated | week first seated | Pass the tests, wrong: bad per 100 paid | good fixes wrongly unpaid | runs ever seated | week first seated |
|---|---|---|---|---|---|---|---|---|
| **a contender** | 4.5 ± 0.4 | 8.3 % ± 0.5 | 0 % ± 0 | n/a | 9.8 ± 0.5 | 8.6 % ± 0.6 | 0 % ± 0 | n/a |
| neutral (v3, D14) | 10.7 ± 1.3 | 16.6 % ± 2.7 | 100 % ± 0 | 8 ± 0 | 10.9 ± 0.9 | 17.1 % ± 2.8 | 100 % ± 0 | 8 ± 0 |
| a contender, six contender shadows a draw | 4.5 ± 0.4 | 8.3 % ± 0.5 | 0 % ± 0 | n/a | 9.2 ± 0.5 | 14.7 % ± 2.3 | 0 % ± 0 | n/a |
| a contender, with the appeal to other families (majority) | 4.3 ± 0.4 | 3.0 % ± 0.3 | 0 % ± 0 | n/a | 9.2 ± 0.5 | 3.1 % ± 0.3 | 0 % ± 0 | n/a |
| a contender, with the appeal and six contender shadows a draw | 4.3 ± 0.4 | 3.0 % ± 0.3 | 0 % ± 0 | n/a | 8.1 ± 0.5 | 4.5 % ± 0.4 | 0 % ± 0 | n/a |

**A strong newcomer: Opus 5.5** (into a network whose genesis family is GPT-6.1):

| It starts as | The tests fail them: bad fixes merged per 100 paid | good fixes wrongly unpaid | runs in which it was ever seated | week first seated | Pass the tests, wrong: bad per 100 paid | good fixes wrongly unpaid | runs ever seated | week first seated |
|---|---|---|---|---|---|---|---|---|
| **a contender** | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a |
| neutral (v3, D14) | 5.9 ± 0.7 | 11.2 % ± 1.8 | 100 % ± 0 | 8 ± 0 | 9.4 ± 0.4 | 14.6 % ± 2.4 | 100 % ± 0 | 8 ± 0 |
| a contender, six contender shadows a draw | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a |
| a contender, with the appeal to other families (majority) | 8.0 ± 0.4 | 6.3 % ± 0.4 | 15 % ± 11 | 45 ± 5 | 5.5 ± 0.3 | 6.4 % ± 0.3 | 2 % ± 5 | 40 ± 0 |
| a contender, with the appeal and six contender shadows a draw | 5.7 ± 0.7 | 4.4 % ± 0.5 | 98 % ± 5 | 28 ± 2 | 6.3 ± 0.4 | 6.2 % ± 0.4 | 60 % ± 16 | 33 ± 4 |

- **The contender's start does what D23 wants against a weak model:** Mistral Large 3 is never seated, in any run. With the neutral start it judges from the day it joins, and bad fixes merged rise from 4.5 ± 0.4 to 10.7 ± 1.3 per 100 paid.
- **It also keeps a better model out.** Opus 5.5 joining a network seated by GPT-6.1 is never seated in the year without the appeal, even with six shadows a draw. GPT-6.1 goes on rejecting 31.1 % ± 0.7 of good fixes.
- **On fixes the tests fail, GPT-6.1 keeps its seat although it scores 65 % on known answers,** below `SCORE_MIN`: a family judging alone agrees with its own outcomes, and no family failed the rule for a single day in those rows.
- **Only the appeal lets the better model in,** and slowly: seated in 15 % ± 11 of runs with one shadow a draw, and in 98 % ± 5 with six, around week 28.
- **So the contender's start is right, and incomplete:** it needs a source of known answers for rejections that is not the appeal of section 5.

## 8. v3 as designed beside the proposal

**Bad fixes the tests fail:**

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks |
|---|---|---|---|---|---|---|---|
| v3 as designed (no test disputes) | 17.8 ± 1.2 | 21.9 % ± 2.1 | $1.37 ± 0.03 | 391 ± 57 | 64.8 % ± 4.2 | 17.2 % ± 2.6 | $0.244 ± 0.012 |
| seats by rank alone | 6.0 ± 0.2 | 6.0 % ± 0.2 | $1.64 ± 0.03 | 1151 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| …with disputes and the deposit, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| **the proposal (`D236`)**: …with the appeal to other families | 4.2 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | 1162 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| the proposal, appeal to the seated families | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| the proposal, every appeal judge must pass | 4.4 ± 0.2 | 7.5 % ± 0.2 | $3.61 ± 0.08 | 1114 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| the proposal, on live scores | 4.3 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | 1163 ± 10 | 0.1 % ± 0.1 | 0.0 % ± 0.0 | $0.010 ± 0.000 |

**Bad fixes that pass the tests and are wrong:**

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks |
|---|---|---|---|---|---|---|---|
| v3 as designed (no test disputes) | 14.3 ± 1.0 | 14.3 % ± 2.1 | $1.50 ± 0.05 | 673 ± 120 | 43.2 % ± 9.2 | 9.0 % ± 2.6 | $0.177 ± 0.034 |
| seats by rank alone | 11.7 ± 0.3 | 6.1 % ± 0.2 | $1.60 ± 0.00 | 1235 ± 12 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| …with disputes and the deposit, no appeal | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| **the proposal (`D236`)**: …with the appeal to other families | 8.1 ± 0.2 | 3.5 % ± 0.2 | $2.57 ± 0.06 | 1219 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| the proposal, appeal to the seated families | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.97 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| the proposal, every appeal judge must pass | 8.2 ± 0.2 | 5.2 % ± 0.2 | $3.01 ± 0.06 | 1199 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| the proposal, on live scores | 8.5 ± 0.4 | 3.9 % ± 0.3 | $2.55 ± 0.07 | 1203 ± 14 | 0.9 % ± 0.3 | 0.0 % ± 0.0 | $0.010 ± 0.000 |

- **v3's rows reproduce v1's** (17.8 ± 1.2 and 14.3 ± 1.0 bad fixes per 100 paid, 64.8 % ± 4.2 and 43.2 % ± 9.2 waiting): the market fee changes what a check costs, not who judges.
- **The proposal's row looks best because its honest solvers appeal only good fixes.** Section 5 shows what the same appeal does for a solver that appeals everything.
- **Without the appeal, the proposal merges 4.5 ± 0.2 and 8.5 ± 0.2 bad fixes per 100 paid,** against the 1.1 ADR 0004's bonds and windows were sized on. These are the figures for task 10.2, with the evidence-find rate at its assumed 1 in 2; with no disputes they are 6.0 ± 0.2 and 11.7 ± 0.3.
- **The fee sits at its floor, $0.01, in every row with seats by rank.** D9 lowers the fee while more than 40 % of active validators aren't drawn, and contenders never are. An honest solver's seven checks then cost about $1.14 a fix; with the idle signal counting seated validators only, the fee ends at $0.238 ± 0.007 and a good fix costs $5.13 ± 0.10 instead of $3.93 ± 0.08. What a fee at the floor does to the number of seated validators is not simulated: entry and exit are off.

## 9. What this does not show
- **The two rates that decide the deposit and the stake are assumed.** The evidence-find rate (1 in 2) and the wrong-test acceptance rate (1 in 20, 1 in 5) are not measured; task 10.3 measures them, and sections 4 and 6 say which value each recommendation needs.
- **The parameter sweeps read seats from known answers.** That is the rule with a perfect score. Section 3 shows the live score falls short of it where families are level, so the sweeps are the rule's upper bound.
- **Validators neither enter nor leave.** The fee is the market's; entry and exit are off, except in the spammer's rows. What the floor fee does to the seated validators' numbers is not played out.
- **A contender's money is one actor's.** The world's other contenders dispute for free, and each searches only the fixes its model failed in one review call.
- **Issues have no identity for honest solvers.** A deposit added to an issue's bounty is paid on to nobody, and an honest solver never tries the same issue twice. Only the retrying solver's issues are followed.
- **The reward's source is not charged.** `EVIDENCE_REWARD_BPS` of the bounty is paid to the disputer; who funds it is not modelled.
- **The retrying solver has no stop rule,** and is the only solver of its issues.
- **The bad fixes are #160's honest failures,** not written to beat a judge or an appeal panel.
- **Judges of a family are identical,** and a model asked again repeats itself. If repeated calls differ, the seated families' own appeal would restore some good fixes, and overturn some correct rejections.
- **Pay by score, proof levels, the pricing attackers and the constitution tier are not re-run.** ADR votes keep the assumed judges, as before.
- **228 cases, one verdict each, one benchmark; seeds 1–40, exploratory.** The two kinds of bad fix are run apart; a real network sees a mix, and the seats a mix would give are not computed.

## 10. For the parameters ADR (task 10.2)
1. **Adopt seats by rank with `SEAT_MARGIN` 5 and `CAP_MIN_FAMILIES` 3,** and the contender's start. Sections 2 and 7.
2. **Raise `SOLVER_DEPOSIT_BPS` to 4,000,** or keep 2,500 and accept that a solver of passing-but-wrong fixes gains about $1,200 a year at five fixes a week. Re-derive it when task 10.3 has the evidence-find rate. Section 4.
3. **Set `EVIDENCE_STAKE` as a share of the bounty,** the larger of $5 and 10 %, and re-derive it from the measured wrong-test rate. Section 6.
4. **Do not adopt the appeal to the families that didn't judge.** The condition the owner set is not met, by majority or by unanimity, and the exact counts say the same of a panel of the other frontier families alone. The question returns to the owner, as D23 says.
5. **Without an appeal the score has no known answers for rejections,** and sections 3 and 7 show what that costs: the incumbent keeps its seat, and a strict judge rises. The sources left are the ones D23 already names as research: fixes with known answers (canaries, #136).
6. **Count seated validators only in the idle signal,** or the fee goes to its floor.
7. **Decide what a second-opinion challenge is under D21.** If it stays, D4's larger fresh panel can't be drawn while one family holds every seat, and the verdict is never final.
8. **Size the bonds and windows on 4.5 and 8.5 bad fixes per 100 paid** (disputes at the assumed rate), or 6.0 and 11.7 with none.

## Appendix: the full output

Seeds 1-40; every ± is two standard errors of the mean.

### Seats by rank, on known answers: `SEAT_MARGIN` and `CAP_MIN_FAMILIES`

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | the four others, their shares added | No family met the rule, share of the year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: v3 as designed (seats at `SCORE_MIN`, scores on agreement, the family cap, second-opinion challenges); test disputes on | 8.8 ± 1.2 | 24.7 % ± 2.3 | $1.31 ± 0.09 | $0.00 ± 0.00 | 188 ± 14 | 79.6 % ± 1.5 | 23.6 % ± 2.5 | $0.250 ± 0.000 | n/a | n/a | n/a | n/a | n/a |
| bad = the tests fail them: `SEAT_MARGIN` 0 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 1 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 2 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: **`SEAT_MARGIN` 5 points** | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 10 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 25 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 10 points, `SCORE_MIN` 50 % | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 25 points, `SCORE_MIN` 50 % | 6.0 ± 0.4 | 16.7 % ± 0.9 | $5.99 ± 0.23 | $4.30 ± 0.23 | 1029 ± 14 | 0.0 % ± 0.0 | 1.5 % ± 0.2 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 40 points, `SCORE_MIN` 50 % | 13.2 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.09 | $2.28 ± 0.09 | 1220 ± 11 | 0.0 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 400 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `CAP_MIN_FAMILIES` 1, `SEAT_MARGIN` 5 points | 4.4 ± 0.6 | 8.5 % ± 0.6 | $1.74 ± 0.06 | $0.80 ± 0.06 | 200 ± 5 | 81.6 % ± 0.3 | 0.0 % ± 0.0 | $0.250 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `CAP_MIN_FAMILIES` 2, `SEAT_MARGIN` 5 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `CAP_MIN_FAMILIES` 4, `SEAT_MARGIN` 5 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `CAP_MIN_FAMILIES` 2, `SEAT_MARGIN` 1 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `CAP_MIN_FAMILIES` 3, `SEAT_MARGIN` 1 points | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: `SEAT_MARGIN` 5 points, with volunteers' second-opinion challenges (D4; as reports measured-v1 and -v2 ran) | 4.5 ± 0.2 | 10.0 % ± 0.3 | $4.23 ± 0.09 | $2.59 ± 0.09 | 1083 ± 10 | 0.1 % ± 0.0 | 2.7 % ± 0.2 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: v3 as designed (seats at `SCORE_MIN`, scores on agreement, the family cap, second-opinion challenges); test disputes on | 9.7 ± 0.6 | 26.1 % ± 2.0 | $1.31 ± 0.07 | $0.00 ± 0.00 | 222 ± 25 | 76.2 % ± 2.2 | 23.0 % ± 2.4 | $0.250 ± 0.000 | n/a | n/a | n/a | n/a | n/a |
| bad = pass the tests, wrong: `SEAT_MARGIN` 0 points | 7.3 ± 0.3 | 31.6 % ± 0.4 | $8.49 ± 0.12 | $7.51 ± 0.10 | 821 ± 8 | 3.5 % ± 0.2 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 0 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 1 points | 9.0 ± 0.2 | 16.8 % ± 0.9 | $6.01 ± 0.23 | $4.32 ± 0.24 | 1061 ± 16 | 0.0 % ± 0.0 | 1.4 % ± 0.2 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 2 points | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: **`SEAT_MARGIN` 5 points** | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 10 points | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 25 points | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 10 points, `SCORE_MIN` 50 % | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 25 points, `SCORE_MIN` 50 % | 12.8 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.08 | $2.29 ± 0.08 | 1214 ± 11 | 0.0 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 400 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 40 points, `SCORE_MIN` 50 % | 12.8 ± 0.3 | 8.9 % ± 0.3 | $3.69 ± 0.08 | $2.29 ± 0.08 | 1214 ± 11 | 0.0 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 400 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `CAP_MIN_FAMILIES` 1, `SEAT_MARGIN` 5 points | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `CAP_MIN_FAMILIES` 2, `SEAT_MARGIN` 5 points | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `CAP_MIN_FAMILIES` 4, `SEAT_MARGIN` 5 points | 8.9 ± 0.3 | 10.4 % ± 0.5 | $4.30 ± 0.13 | $2.69 ± 0.13 | 1143 ± 13 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `CAP_MIN_FAMILIES` 2, `SEAT_MARGIN` 1 points | 8.0 ± 0.6 | 29.2 % ± 1.0 | $3.66 ± 0.09 | $2.76 ± 0.09 | 158 ± 4 | 81.6 % ± 0.3 | 22.3 % ± 0.9 | $0.250 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `CAP_MIN_FAMILIES` 3, `SEAT_MARGIN` 1 points | 9.0 ± 0.2 | 16.8 % ± 0.9 | $6.01 ± 0.23 | $4.32 ± 0.24 | 1061 ± 16 | 0.0 % ± 0.0 | 1.4 % ± 0.2 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: `SEAT_MARGIN` 5 points, with volunteers' second-opinion challenges (D4; as reports measured-v1 and -v2 ran) | 8.5 ± 0.2 | 9.1 % ± 0.3 | $3.98 ± 0.09 | $2.38 ± 0.09 | 1154 ± 11 | 0.0 % ± 0.0 | 0.3 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |

### Seats by rank, on live scores (D23)

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | the four others, their shares added | No family met the rule, share of the year |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: known answers, `SEAT_MARGIN` 5 (the upper bound) | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 2, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 10, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, appeal to other families (majority) | 4.3 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | $0.86 ± 0.05 | 1163 ± 10 | 0.1 % ± 0.1 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 99 % ± 2 | 1 % ± 2 | 0 % ± 0 | 0 % ± 0 | 1 % ± 1 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, appeal to the seated families | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, no disputes and no appeal | 6.0 ± 0.2 | 6.0 % ± 0.2 | $3.16 ± 0.08 | $1.52 ± 0.07 | 1151 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, no appeal, six contender shadows a draw | 4.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.10 | $2.31 ± 0.10 | 1096 ± 10 | 0.1 % ± 0.1 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 1 | 0 % ± 1 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, no appeal, score window 1,400 verdicts (post hoc) | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = the tests fail them: live, `SEAT_MARGIN` 5, appeal to other families, score window 1,400 (post hoc) | 4.2 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | $0.85 ± 0.05 | 1162 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: known answers, `SEAT_MARGIN` 5 (the upper bound) | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 2, no appeal | 9.6 ± 0.3 | 10.0 % ± 1.0 | $4.15 ± 0.22 | $2.55 ± 0.24 | 1146 ± 17 | 0.2 % ± 0.2 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 92 % ± 6 | 5 % ± 4 | 2 % ± 3 | 0 % ± 0 | 5 % ± 1 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, no appeal | 9.5 ± 0.3 | 11.3 % ± 1.5 | $4.45 ± 0.31 | $2.87 ± 0.35 | 1128 ± 24 | 0.4 % ± 0.2 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 87 % ± 7 | 11 % ± 7 | 2 % ± 2 | 0 % ± 0 | 3 % ± 1 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 10, no appeal | 9.3 ± 0.3 | 12.5 % ± 1.8 | $4.68 ± 0.39 | $3.14 ± 0.44 | 1113 ± 29 | 0.5 % ± 0.2 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 81 % ± 8 | 17 % ± 8 | 4 % ± 4 | 0 % ± 0 | 2 % ± 0 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, appeal to other families (majority) | 8.5 ± 0.4 | 3.9 % ± 0.3 | $2.55 ± 0.07 | $0.99 ± 0.07 | 1203 ± 14 | 0.9 % ± 0.3 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 69 % ± 9 | 21 % ± 8 | 11 % ± 6 | 0 % ± 0 | 12 % ± 2 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, appeal to the seated families | 9.5 ± 0.3 | 10.3 % ± 1.3 | $4.20 ± 0.30 | $2.61 ± 0.32 | 1140 ± 22 | 0.3 % ± 0.2 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 89 % ± 6 | 7 % ± 5 | 4 % ± 4 | 0 % ± 0 | 4 % ± 1 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, no disputes and no appeal | 13.8 ± 0.3 | 6.0 % ± 0.2 | $3.17 ± 0.08 | $1.52 ± 0.07 | 1255 ± 12 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, no appeal, six contender shadows a draw | 8.4 ± 0.4 | 22.3 % ± 2.1 | $6.63 ± 0.43 | $5.37 ± 0.49 | 962 ± 34 | 2.1 % ± 0.4 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 39 % ± 9 | 61 % ± 9 | 1 % ± 1 | 0 % ± 0 | 2 % ± 1 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, no appeal, score window 1,400 verdicts (post hoc) | 9.6 ± 0.3 | 9.9 % ± 0.9 | $4.14 ± 0.20 | $2.52 ± 0.22 | 1149 ± 18 | 0.2 % ± 0.1 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 96 % ± 4 | 6 % ± 5 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: live, `SEAT_MARGIN` 5, appeal to other families, score window 1,400 (post hoc) | 8.9 ± 0.3 | 3.8 % ± 0.3 | $2.61 ± 0.06 | $0.98 ± 0.06 | 1217 ± 12 | 0.5 % ± 0.2 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 86 % ± 7 | 20 % ± 7 | 13 % ± 6 | 0 % ± 0 | 1 % ± 1 |

### The solver's deposit: what it costs honest solvers

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks |
|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 0 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $1.64 ± 0.03 | $0.00 ± 0.00 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 500 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $2.09 ± 0.03 | $0.46 ± 0.02 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 1,000 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $2.55 ± 0.04 | $0.92 ± 0.03 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 1,500 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.01 ± 0.06 | $1.37 ± 0.05 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: **`SOLVER_DEPOSIT_BPS` 2,500** | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 4,000 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $5.30 ± 0.13 | $3.66 ± 0.13 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 5,000 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $6.22 ± 0.16 | $4.58 ± 0.16 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 7,500 | 4.5 ± 0.2 | 8.9 % ± 0.2 | $8.51 ± 0.24 | $6.87 ± 0.24 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 2,500, no disputes | 6.0 ± 0.2 | 6.0 % ± 0.2 | $3.16 ± 0.08 | $1.52 ± 0.07 | 1151 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 2,500, a wrong test accepted 1 time in 5 | 5.0 ± 0.3 | 17.8 % ± 0.4 | $6.21 ± 0.11 | $4.58 ± 0.11 | 994 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 |
| bad = the tests fail them: `SOLVER_DEPOSIT_BPS` 2,500, the idle signal counts seated validators only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $5.13 ± 0.10 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.238 ± 0.007 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 0 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $1.60 ± 0.00 | $0.00 ± 0.00 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 500 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $2.07 ± 0.02 | $0.47 ± 0.02 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 1,000 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $2.54 ± 0.03 | $0.94 ± 0.03 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 1,500 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.01 ± 0.05 | $1.41 ± 0.05 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: **`SOLVER_DEPOSIT_BPS` 2,500** | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 4,000 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $5.36 ± 0.13 | $3.76 ± 0.13 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 5,000 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $6.30 ± 0.16 | $4.70 ± 0.16 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 7,500 | 8.5 ± 0.2 | 9.0 % ± 0.3 | $8.65 ± 0.24 | $7.06 ± 0.24 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 2,500, no disputes | 11.7 ± 0.3 | 6.1 % ± 0.2 | $3.19 ± 0.08 | $1.59 ± 0.08 | 1235 ± 12 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 2,500, a wrong test accepted 1 time in 5 | 9.3 ± 0.3 | 18.0 % ± 0.4 | $6.27 ± 0.11 | $4.67 ± 0.11 | 1051 ± 11 | 0.0 % ± 0.0 | 0.3 % ± 0.1 | $0.010 ± 0.000 |
| bad = pass the tests, wrong: `SOLVER_DEPOSIT_BPS` 2,500, the idle signal counts seated validators only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $4.62 ± 0.10 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.037 ± 0.006 |

### The solver's deposit: what a solver of bad fixes earns

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 0 | +2,741 ± 204 | **wins** | 2,741 | 0 | 32 bad fixes paid of 261 submitted (12 %); $+10.50 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 500 | +1,598 ± 206 | **wins** | 1,598 | 0 | 32 bad fixes paid of 261 submitted (12 %); $+6.12 a fix submitted; $1,144 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 1,000 | +454 ± 213 | **wins** | 454 | 0 | 32 bad fixes paid of 261 submitted (12 %); $+1.74 a fix submitted; $2,287 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 1,500 | -689 ± 225 | loses | -689 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-2.64 a fix submitted; $3,431 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 2,500 | -2,976 ± 262 | loses | -2,976 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-11.40 a fix submitted; $5,718 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 4,000 | -6,407 ± 337 | loses | -6,407 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-24.54 a fix submitted; $9,148 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 5,000 | -8,694 ± 395 | loses | -8,694 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-33.30 a fix submitted; $11,435 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 7,500 | -14,412 ± 552 | loses | -14,412 | 0 | 32 bad fixes paid of 261 submitted (12 %); $-55.20 a fix submitted; $17,153 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 0, no disputes | +4,229 ± 238 | **wins** | 4,229 | 0 | 46 bad fixes paid of 261 submitted (18 %); $+16.20 a fix submitted; $0 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 2,500, no disputes | -1,120 ± 248 | loses | -1,120 | 0 | 46 bad fixes paid of 261 submitted (18 %); $-4.29 a fix submitted; $5,348 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 4,000, no disputes | -4,329 ± 298 | loses | -4,329 | 0 | 46 bad fixes paid of 261 submitted (18 %); $-16.58 a fix submitted; $8,557 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 5,000, no disputes (post hoc) | -6,468 ± 343 | loses | -6,468 | 0 | 46 bad fixes paid of 261 submitted (18 %); $-24.77 a fix submitted; $10,697 of deposits lost |
| bad = the tests fail them: bad-fix solver, `SOLVER_DEPOSIT_BPS` 7,500, no disputes (post hoc) | -11,816 ± 473 | loses | -11,816 | 0 | 46 bad fixes paid of 261 submitted (18 %); $-45.26 a fix submitted; $16,045 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to six times, deposit 2,500 to the issue's bounty (the owner's decision) | -18,162 ± 1,296 | loses | -18,162 | 0 | 140 bad fixes paid of 1122 submitted (12 %); $-16.18 a fix submitted; $40,034 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to six times, deposit 2,500 to the sponsors' pool | -11,983 ± 801 | loses | -11,983 | 0 | 140 bad fixes paid of 1122 submitted (12 %); $-10.68 a fix submitted; $24,342 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to 21 times, deposit 2,500 to the issue's bounty (the owner's decision) | -98,721 ± 11,985 | loses | -98,721 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-54.41 a fix submitted; $232,275 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to 21 times, deposit 2,500 to the sponsors' pool | -19,464 ± 1,316 | loses | -19,464 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-10.73 a fix submitted; $39,298 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to 21 times, deposit 4,000 to the issue's bounty (post hoc) | -1,038,175 ± 118,779 | loses | -1,038,175 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-572.21 a fix submitted; $1,633,868 of deposits lost |
| bad = the tests fail them: bad-fix solver that tries each issue up to 21 times, deposit 4,000 to the sponsors' pool (post hoc) | -43,043 ± 2,276 | loses | -43,043 | 0 | 227 bad fixes paid of 1814 submitted (12 %); $-23.72 a fix submitted; $62,876 of deposits lost |
| bad = the tests fail them: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 0 | +2,027 ± 189 | **wins** | 1,895 | -132 | 364 bad fixes submitted, 29 paid; $0 of deposits lost; 40 % of all submissions waited |
| bad = the tests fail them: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 2,500 | -2,161 ± 259 | loses | -2,292 | -132 | 364 bad fixes submitted, 29 paid; $4,188 of deposits lost; 40 % of all submissions waited |
| bad = the tests fail them: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 4,000 (post hoc) | -4,673 ± 383 | loses | -4,805 | -132 | 364 bad fixes submitted, 29 paid; $6,700 of deposits lost; 40 % of all submissions waited |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 0 | +6,126 ± 370 | **wins** | 6,126 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+23.46 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 500 | +5,139 ± 365 | **wins** | 5,139 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+19.68 a fix submitted; $987 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 1,000 | +4,152 ± 363 | **wins** | 4,152 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+15.90 a fix submitted; $1,974 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 1,500 | +3,165 ± 363 | **wins** | 3,165 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+12.12 a fix submitted; $2,961 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 2,500 | +1,191 ± 369 | **wins** | 1,191 | 0 | 65 bad fixes paid of 261 submitted (25 %); $+4.56 a fix submitted; $4,935 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 4,000 | -1,769 ± 394 | loses | -1,769 | 0 | 65 bad fixes paid of 261 submitted (25 %); $-6.78 a fix submitted; $7,895 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 5,000 | -3,743 ± 419 | loses | -3,743 | 0 | 65 bad fixes paid of 261 submitted (25 %); $-14.34 a fix submitted; $9,869 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 7,500 | -8,678 ± 504 | loses | -8,678 | 0 | 65 bad fixes paid of 261 submitted (25 %); $-33.24 a fix submitted; $14,804 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 0, no disputes | +9,317 ± 403 | **wins** | 9,317 | 0 | 96 bad fixes paid of 261 submitted (37 %); $+35.69 a fix submitted; $0 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 2,500, no disputes | +5,191 ± 364 | **wins** | 5,191 | 0 | 96 bad fixes paid of 261 submitted (37 %); $+19.88 a fix submitted; $4,126 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 4,000, no disputes | +2,715 ± 355 | **wins** | 2,715 | 0 | 96 bad fixes paid of 261 submitted (37 %); $+10.40 a fix submitted; $6,601 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 5,000, no disputes (post hoc) | +1,065 ± 356 | **wins** | 1,065 | 0 | 96 bad fixes paid of 261 submitted (37 %); $+4.08 a fix submitted; $8,252 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver, `SOLVER_DEPOSIT_BPS` 7,500, no disputes (post hoc) | -3,061 ± 383 | loses | -3,061 | 0 | 96 bad fixes paid of 261 submitted (37 %); $-11.72 a fix submitted; $12,378 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to six times, deposit 2,500 to the issue's bounty (the owner's decision) | +6,176 ± 994 | **wins** | 6,176 | 0 | 212 bad fixes paid of 854 submitted (25 %); $+7.23 a fix submitted; $23,357 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to six times, deposit 2,500 to the sponsors' pool | +3,779 ± 673 | **wins** | 3,779 | 0 | 212 bad fixes paid of 854 submitted (25 %); $+4.42 a fix submitted; $16,162 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to 21 times, deposit 2,500 to the issue's bounty (the owner's decision) | +12,152 ± 2,283 | **wins** | 12,152 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $+11.77 a fix submitted; $46,010 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to 21 times, deposit 2,500 to the sponsors' pool | +4,573 ± 605 | **wins** | 4,573 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $+4.43 a fix submitted; $19,509 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to 21 times, deposit 4,000 to the issue's bounty (post hoc) | -35,882 ± 19,157 | loses | -35,882 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $-34.75 a fix submitted; $170,668 of deposits lost |
| bad = pass the tests, wrong: bad-fix solver that tries each issue up to 21 times, deposit 4,000 to the sponsors' pool (post hoc) | -7,133 ± 914 | loses | -7,133 | 0 | 255 bad fixes paid of 1032 submitted (25 %); $-6.91 a fix submitted; $31,215 of deposits lost |
| bad = pass the tests, wrong: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 0 | +7,480 ± 323 | **wins** | 7,683 | 203 | 364 bad fixes submitted, 90 paid; $0 of deposits lost; 4 % of all submissions waited |
| bad = pass the tests, wrong: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 2,500 | +1,105 ± 381 | **wins** | 1,308 | 203 | 364 bad fixes submitted, 90 paid; $6,375 of deposits lost; 4 % of all submissions waited |
| bad = pass the tests, wrong: report v3's judged spammer (a bad fix a day, three validators of its own, four families, the market with entry), `SOLVER_DEPOSIT_BPS` 4,000 (post hoc) | -2,721 ± 421 | loses | -2,518 | 203 | 364 bad fixes submitted, 90 paid; $10,201 of deposits lost; 4 % of all submissions waited |

### The appeal: its panel

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks | Appeals a year | Correct rejections overturned, of those appealed | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Appeals with no panel |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: no appeal; honest solvers appeal good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = the tests fail them: **other families, contenders included; majority** (the owner's decision); honest solvers appeal good fixes only | 4.2 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | $0.85 ± 0.05 | 1162 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 95 % ± 1 | 0 ± 0 |
| bad = the tests fail them: other families, contenders included; every judge must pass; honest solvers appeal good fixes only | 4.4 ± 0.2 | 7.5 % ± 0.2 | $3.61 ± 0.08 | $1.93 ± 0.07 | 1114 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 24 % ± 2 | 0 ± 0 |
| bad = the tests fail them: other families, seated only; honest solvers appeal good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| bad = the tests fail them: the seated families' next draw; honest solvers appeal good fixes only | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| bad = the tests fail them: **other families, contenders included; majority** (the owner's decision); honest solvers appeal every rejection | 13.8 ± 0.4 | 3.3 % ± 0.2 | $2.54 ± 0.05 | $0.85 ± 0.05 | 1291 ± 11 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 383 ± 7 | 81 % ± 1 | 128.5 ± 4.0 | 95 % ± 1 | 0 ± 0 |
| bad = the tests fail them: other families, contenders included; every judge must pass; honest solvers appeal every rejection | 8.4 ± 0.3 | 7.5 % ± 0.2 | $3.62 ± 0.07 | $1.92 ± 0.07 | 1162 ± 11 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 383 ± 7 | 31 % ± 1 | 48.9 ± 2.1 | 24 % ± 2 | 0 ± 0 |
| bad = the tests fail them: other families, seated only; honest solvers appeal every rejection | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 382 ± 7 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 382 ± 7 |
| bad = the tests fail them: the seated families' next draw; honest solvers appeal every rejection | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 383 ± 7 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 380 ± 7 |
| bad = the tests fail them: other families, contenders included; majority; honest solvers appeal every rejection; no disputes | 22.0 ± 0.4 | 0.0 % ± 0.0 | $1.70 ± 0.03 | $0.00 ± 0.00 | 1474 ± 13 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 382 ± 7 | 81 % ± 1 | 255.2 ± 6.8 | 100 % ± 0 | 0 ± 0 |
| bad = pass the tests, wrong: no appeal; honest solvers appeal good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = pass the tests, wrong: **other families, contenders included; majority** (the owner's decision); honest solvers appeal good fixes only | 8.1 ± 0.2 | 3.5 % ± 0.2 | $2.57 ± 0.06 | $0.94 ± 0.06 | 1219 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 94 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: other families, contenders included; every judge must pass; honest solvers appeal good fixes only | 8.2 ± 0.2 | 5.2 % ± 0.2 | $3.01 ± 0.06 | $1.37 ± 0.06 | 1199 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 65 % ± 2 | 0 ± 0 |
| bad = pass the tests, wrong: other families, seated only; honest solvers appeal good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.93 ± 0.08 | $2.33 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| bad = pass the tests, wrong: the seated families' next draw; honest solvers appeal good fixes only | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.97 ± 0.08 | $2.33 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 23 ± 4 |
| bad = pass the tests, wrong: **other families, contenders included; majority** (the owner's decision); honest solvers appeal every rejection | 14.9 ± 0.3 | 3.5 % ± 0.2 | $2.65 ± 0.06 | $0.95 ± 0.06 | 1316 ± 10 | 0.0 % ± 0.0 | 0.3 % ± 0.1 | $0.010 ± 0.000 | 310 ± 7 | 81 % ± 1 | 97.8 ± 3.7 | 94 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: other families, contenders included; every judge must pass; honest solvers appeal every rejection | 11.8 ± 0.3 | 5.2 % ± 0.2 | $3.07 ± 0.06 | $1.38 ± 0.06 | 1248 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 310 ± 7 | 39 % ± 1 | 48.4 ± 2.4 | 65 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: other families, seated only; honest solvers appeal every rejection | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.93 ± 0.08 | $2.33 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 310 ± 7 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 310 ± 7 |
| bad = pass the tests, wrong: the seated families' next draw; honest solvers appeal every rejection | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.98 ± 0.08 | $2.34 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.3 % ± 0.1 | $0.010 ± 0.000 | 310 ± 7 | 0 % ± 0 | 0.0 ± 0.0 | 0 % ± 0 | 104 ± 15 |
| bad = pass the tests, wrong: other families, contenders included; majority; honest solvers appeal every rejection; no disputes | 22.6 ± 0.4 | 0.3 % ± 0.1 | $1.81 ± 0.03 | $0.12 ± 0.03 | 1496 ± 12 | 0.0 % ± 0.0 | 0.3 % ± 0.1 | $0.010 ± 0.000 | 310 ± 7 | 80 % ± 1 | 194.5 ± 4.9 | 99 % ± 1 | 0 ± 0 |

### An appeal panel on #160's verdicts (exact, no simulation)

| Bad fixes | Seated panel | Appeal panel of 5 drawn from | Rule | Bad fixes rejected | …of which the appeal passes | Good fixes rejected | …of which the appeal passes |
|---|---|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 | the other families of the seven | majority | 82 | 80 % | 3 | 100 % |
| the tests fail them | Opus 5.5 | the other families of the seven | every judge must pass | 82 | 39 % | 3 | 40 % |
| the tests fail them | Opus 5.5 | the other frontier families only | majority | 82 | 55 % | 3 | 67 % |
| the tests fail them | Opus 5.5 | the other frontier families only | every judge must pass | 82 | 41 % | 3 | 44 % |
| the tests fail them | GPT-6.1 | the other families of the seven | majority | 60 | 73 % | 15 | 89 % |
| the tests fail them | GPT-6.1 | the other families of the seven | every judge must pass | 60 | 24 % | 15 | 55 % |
| the tests fail them | GPT-6.1 | the other frontier families only | majority | 60 | 37 % | 15 | 90 % |
| the tests fail them | GPT-6.1 | the other frontier families only | every judge must pass | 60 | 17 % | 15 | 83 % |
| pass the tests, wrong | Opus, GPT-6.1, Gemini (majority) | the other families of the seven | majority | 49 | 81 % | 3 | 100 % |
| pass the tests, wrong | Opus, GPT-6.1, Gemini (majority) | the other families of the seven | every judge must pass | 49 | 44 % | 3 | 73 % |
| pass the tests, wrong | Opus 5.5 | the other families of the seven | majority | 43 | 59 % | 3 | 100 % |
| pass the tests, wrong | Opus 5.5 | the other families of the seven | every judge must pass | 43 | 12 % | 3 | 40 % |
| pass the tests, wrong | Opus 5.5 | the other frontier families only | majority | 43 | 16 % | 3 | 67 % |
| pass the tests, wrong | Opus 5.5 | the other frontier families only | every judge must pass | 43 | 7 % | 3 | 44 % |

### The solver that appeals every rejection, against the same solver that never appeals

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: appeals everything; panel: **other families, contenders included; majority** (the owner's decision) | +10,631 ± 452 | **wins** | 7,691 | -2,940 | 212 appeals, 170 upheld, 86 of them paid; 117 bad fixes paid of 261 (twin: 32); $+50.25 an appeal |
| bad = the tests fail them: appeals everything; panel: other families, contenders included; every judge must pass | +3,857 ± 266 | **wins** | 916 | -2,941 | 212 appeals, 64 upheld, 32 of them paid; 63 bad fixes paid of 261 (twin: 32); $+18.23 an appeal |
| bad = the tests fail them: appeals everything; panel: other families, seated only | +0 ± 0 | not significant | -2,942 | -2,942 | 212 appeals, 0 upheld, 0 of them paid; 32 bad fixes paid of 261 (twin: 32); $+0.00 an appeal |
| bad = the tests fail them: appeals everything; panel: the seated families' next draw | +28 ± 8 | **wins** | -2,914 | -2,941 | 212 appeals, 0 upheld, 0 of them paid; 32 bad fixes paid of 261 (twin: 32); $+0.13 an appeal |
| bad = the tests fail them: appeals everything; panel: **other families, contenders included; majority** (the owner's decision), no disputes | +21,264 ± 667 | **wins** | 20,181 | -1,083 | 212 appeals, 170 upheld, 170 of them paid; 216 bad fixes paid of 261 (twin: 46); $+100.52 an appeal |
| bad = the tests fail them: appeals everything; panel: other families, contenders included; every judge must pass, no disputes | +8,008 ± 424 | **wins** | 6,926 | -1,083 | 212 appeals, 64 upheld, 64 of them paid; 110 bad fixes paid of 261 (twin: 46); $+37.86 an appeal |
| bad = the tests fail them: appeals everything; panel: other families, contenders included; majority; no deposit | +8,487 ± 362 | **wins** | 11,228 | 2,740 | 212 appeals, 170 upheld, 86 of them paid; 117 bad fixes paid of 261 (twin: 32); $+40.12 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: **other families, contenders included; majority** (the owner's decision) | +8,177 ± 356 | **wins** | 9,395 | 1,219 | 163 appeals, 131 upheld, 66 of them paid; 130 bad fixes paid of 261 (twin: 65); $+50.19 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: other families, contenders included; every judge must pass | +3,918 ± 274 | **wins** | 5,136 | 1,218 | 163 appeals, 64 upheld, 32 of them paid; 96 bad fixes paid of 261 (twin: 65); $+24.05 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: other families, seated only | +0 ± 0 | not significant | 1,219 | 1,219 | 163 appeals, 0 upheld, 0 of them paid; 65 bad fixes paid of 261 (twin: 65); $+0.00 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: the seated families' next draw | -95 ± 14 | loses | 1,126 | 1,221 | 163 appeals, 0 upheld, 0 of them paid; 65 bad fixes paid of 261 (twin: 65); $-0.58 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: **other families, contenders included; majority** (the owner's decision), no disputes | +16,439 ± 470 | **wins** | 21,664 | 5,226 | 163 appeals, 131 upheld, 131 of them paid; 228 bad fixes paid of 261 (twin: 96); $+100.96 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: other families, contenders included; every judge must pass, no disputes | +7,975 ± 396 | **wins** | 13,203 | 5,228 | 163 appeals, 64 upheld, 64 of them paid; 160 bad fixes paid of 261 (twin: 97); $+48.98 an appeal |
| bad = pass the tests, wrong: appeals everything; panel: other families, contenders included; majority; no deposit | +6,531 ± 285 | **wins** | 12,654 | 6,123 | 163 appeals, 131 upheld, 66 of them paid; 130 bad fixes paid of 261 (twin: 65); $+40.09 an appeal |

### The disputer without evidence (its twin posts nothing), and an honest contender

| Attacker | Return − twin's ($ a year, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| bad = the tests fail them: tests that pass on the fixed code, on every pass; stake $5 | -5,754 ± 52 | loses | -5,754 | 0 | 1151 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 34 (twin's run: 34) |
| bad = the tests fail them: wrong tests on every pass; stake $5 | -3,394 ± 105 | loses | -3,394 | 0 | 1151 tests posted, 58 upheld; good fixes reversed by a wrong test, whoever posted it: 86 (twin's run: 34) |
| bad = the tests fail them: wrong tests where it expects to gain; stake $5 | +50 ± 61 | not significant | 50 | 0 | 31 tests posted, 2 upheld; good fixes reversed by a wrong test, whoever posted it: 35 (twin's run: 34) |
| bad = the tests fail them: wrong tests where it expects to gain; stake $5; a wrong test accepted 1 time in 5 | +3,880 ± 192 | **wins** | 3,880 | 0 | 865 tests posted, 172 upheld; good fixes reversed by a wrong test, whoever posted it: 277 (twin's run: 136) |
| bad = the tests fail them: wrong tests where it expects to gain; stake the larger of $5 and 5 % of the bounty | +0 ± 0 | not significant | 0 | 0 | 0 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 34 (twin's run: 34) |
| bad = the tests fail them: wrong tests where it expects to gain; stake the larger of $5 and 5 %; accepted 1 time in 5 | +2,733 ± 194 | **wins** | 2,733 | 0 | 865 tests posted, 172 upheld; good fixes reversed by a wrong test, whoever posted it: 277 (twin's run: 136) |
| bad = the tests fail them: wrong tests where it expects to gain; stake the larger of $5 and 10 %; accepted 1 time in 5 | +0 ± 0 | not significant | 0 | 0 | 0 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 136 (twin's run: 136) |
| bad = the tests fail them: wrong tests on every pass; stake the larger of $5 and 10 %; accepted 1 time in 5 | -1,415 ± 221 | loses | -1,415 | 0 | 1148 tests posted, 230 upheld; good fixes reversed by a wrong test, whoever posted it: 325 (twin's run: 136) |
| bad = the tests fail them: an honest contender running GPT-6.1, $0.50 a search; stake $5 | +760 ± 71 | **wins** | 760 | 0 | 321 fixes searched, 25 tests upheld; $30 a reversal |
| bad = the tests fail them: an honest contender running Opus 5.5, $0.50 a search; stake $5 | +0 ± 0 | not significant | 0 | 0 | 0 fixes searched, 0 tests upheld; $0 a reversal |
| bad = the tests fail them: an honest contender running DeepSeek V3.2, $0.50 a search; stake $5 | +163 ± 36 | **wins** | 163 | 0 | 94 fixes searched, 6 tests upheld; $28 a reversal |
| bad = the tests fail them: an honest contender running GPT-6.1, `EVIDENCE_REWARD_BPS` 0 (post hoc) | +497 ± 50 | **wins** | 497 | 0 | 321 fixes searched, 25 tests upheld; $20 a reversal |
| bad = the tests fail them: an honest contender running GPT-6.1, `EVIDENCE_REWARD_BPS` 2,500 (post hoc) | +1,155 ± 101 | **wins** | 1,155 | 0 | 321 fixes searched, 25 tests upheld; $46 a reversal |
| bad = pass the tests, wrong: tests that pass on the fixed code, on every pass; stake $5 | -6,188 ± 60 | loses | -6,188 | 0 | 1238 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 34 (twin's run: 34) |
| bad = pass the tests, wrong: wrong tests on every pass; stake $5 | -3,603 ± 111 | loses | -3,603 | 0 | 1238 tests posted, 63 upheld; good fixes reversed by a wrong test, whoever posted it: 87 (twin's run: 34) |
| bad = pass the tests, wrong: wrong tests where it expects to gain; stake $5 | +62 ± 65 | not significant | 62 | 0 | 33 tests posted, 2 upheld; good fixes reversed by a wrong test, whoever posted it: 36 (twin's run: 34) |
| bad = pass the tests, wrong: wrong tests where it expects to gain; stake $5; a wrong test accepted 1 time in 5 | +4,289 ± 228 | **wins** | 4,289 | 0 | 933 tests posted, 187 upheld; good fixes reversed by a wrong test, whoever posted it: 282 (twin's run: 138) |
| bad = pass the tests, wrong: wrong tests where it expects to gain; stake the larger of $5 and 5 % of the bounty | +0 ± 0 | not significant | 0 | 0 | 0 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 34 (twin's run: 34) |
| bad = pass the tests, wrong: wrong tests where it expects to gain; stake the larger of $5 and 5 %; accepted 1 time in 5 | +3,052 ± 229 | **wins** | 3,052 | 0 | 933 tests posted, 187 upheld; good fixes reversed by a wrong test, whoever posted it: 282 (twin's run: 138) |
| bad = pass the tests, wrong: wrong tests where it expects to gain; stake the larger of $5 and 10 %; accepted 1 time in 5 | +0 ± 0 | not significant | 0 | 0 | 0 tests posted, 0 upheld; good fixes reversed by a wrong test, whoever posted it: 138 (twin's run: 138) |
| bad = pass the tests, wrong: wrong tests on every pass; stake the larger of $5 and 10 %; accepted 1 time in 5 | -1,425 ± 251 | loses | -1,425 | 0 | 1238 tests posted, 249 upheld; good fixes reversed by a wrong test, whoever posted it: 330 (twin's run: 138) |
| bad = pass the tests, wrong: an honest contender running GPT-6.1, $0.50 a search; stake $5 | +1,513 ± 105 | **wins** | 1,513 | 0 | 348 fixes searched, 47 tests upheld; $32 a reversal |
| bad = pass the tests, wrong: an honest contender running Opus 5.5, $0.50 a search; stake $5 | +118 ± 29 | **wins** | 118 | 0 | 29 fixes searched, 4 tests upheld; $31 a reversal |
| bad = pass the tests, wrong: an honest contender running DeepSeek V3.2, $0.50 a search; stake $5 | +382 ± 54 | **wins** | 382 | 0 | 106 fixes searched, 12 tests upheld; $32 a reversal |
| bad = pass the tests, wrong: an honest contender running GPT-6.1, `EVIDENCE_REWARD_BPS` 0 (post hoc) | +1,031 ± 75 | **wins** | 1,031 | 0 | 348 fixes searched, 47 tests upheld; $22 a reversal |
| bad = pass the tests, wrong: an honest contender running GPT-6.1, `EVIDENCE_REWARD_BPS` 2,500 (post hoc) | +2,236 ± 151 | **wins** | 2,236 | 0 | 348 fixes searched, 47 tests upheld; $48 a reversal |

### A new family's start (live scores)

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | Runs in which the new family was ever seated | Week it was first seated | Seated, share of its weeks | Counted verdicts it gave | No family met the rule, share of the year |
|---|---|---|---|---|---|---|---|
| bad = the tests fail them: a weak family (Mistral Large 3) joins in week 8, starting as **a contender** | 4.5 ± 0.4 | 8.3 % ± 0.5 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a weak family (Mistral Large 3) joins in week 8, starting as neutral (v3, D14) | 10.7 ± 1.3 | 16.6 % ± 2.7 | 100 % ± 0 | 8 ± 0 | 8 % ± 7 | 439 ± 259 | 6 % ± 4 |
| bad = the tests fail them: a weak family (Mistral Large 3) joins in week 8, starting as a contender, six contender shadows a draw | 4.5 ± 0.4 | 8.3 % ± 0.5 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a weak family (Mistral Large 3) joins in week 8, starting as a contender, with the appeal to other families (majority) | 4.3 ± 0.4 | 3.0 % ± 0.3 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a weak family (Mistral Large 3) joins in week 8, starting as a contender, with the appeal and six contender shadows a draw | 4.3 ± 0.4 | 3.0 % ± 0.3 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a strong family (Opus 5.5) joins in week 8, starting as **a contender** | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a strong family (Opus 5.5) joins in week 8, starting as neutral (v3, D14) | 5.9 ± 0.7 | 11.2 % ± 1.8 | 100 % ± 0 | 8 ± 0 | 90 % ± 10 | 3541 ± 367 | 1 % ± 1 |
| bad = the tests fail them: a strong family (Opus 5.5) joins in week 8, starting as a contender, six contender shadows a draw | 10.7 ± 0.6 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = the tests fail them: a strong family (Opus 5.5) joins in week 8, starting as a contender, with the appeal to other families (majority) | 8.0 ± 0.4 | 6.3 % ± 0.4 | 15 % ± 11 | 45 ± 5 | 2 % ± 2 | 92 ± 91 | 9 % ± 3 |
| bad = the tests fail them: a strong family (Opus 5.5) joins in week 8, starting as a contender, with the appeal and six contender shadows a draw | 5.7 ± 0.7 | 4.4 % ± 0.5 | 98 % ± 5 | 28 ± 2 | 47 % ± 8 | 1823 ± 301 | 4 % ± 2 |
| bad = pass the tests, wrong: a weak family (Mistral Large 3) joins in week 8, starting as **a contender** | 9.8 ± 0.5 | 8.6 % ± 0.6 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: a weak family (Mistral Large 3) joins in week 8, starting as neutral (v3, D14) | 10.9 ± 0.9 | 17.1 % ± 2.8 | 100 % ± 0 | 8 ± 0 | 9 % ± 8 | 458 ± 282 | 11 % ± 7 |
| bad = pass the tests, wrong: a weak family (Mistral Large 3) joins in week 8, starting as a contender, six contender shadows a draw | 9.2 ± 0.5 | 14.7 % ± 2.3 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 1 % ± 0 |
| bad = pass the tests, wrong: a weak family (Mistral Large 3) joins in week 8, starting as a contender, with the appeal to other families (majority) | 9.2 ± 0.5 | 3.1 % ± 0.3 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 3 % ± 2 |
| bad = pass the tests, wrong: a weak family (Mistral Large 3) joins in week 8, starting as a contender, with the appeal and six contender shadows a draw | 8.1 ± 0.5 | 4.5 % ± 0.4 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 4 % ± 2 |
| bad = pass the tests, wrong: a strong family (Opus 5.5) joins in week 8, starting as **a contender** | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: a strong family (Opus 5.5) joins in week 8, starting as neutral (v3, D14) | 9.4 ± 0.4 | 14.6 % ± 2.4 | 100 % ± 0 | 8 ± 0 | 65 % ± 14 | 2571 ± 542 | 2 % ± 1 |
| bad = pass the tests, wrong: a strong family (Opus 5.5) joins in week 8, starting as a contender, six contender shadows a draw | 7.4 ± 0.4 | 31.1 % ± 0.7 | 0 % ± 0 | n/a | 0 % ± 0 | 0 ± 0 | 0 % ± 0 |
| bad = pass the tests, wrong: a strong family (Opus 5.5) joins in week 8, starting as a contender, with the appeal to other families (majority) | 5.5 ± 0.3 | 6.4 % ± 0.3 | 2 % ± 5 | 40 ± 0 | 0 % ± 0 | 1 ± 1 | 1 % ± 1 |
| bad = pass the tests, wrong: a strong family (Opus 5.5) joins in week 8, starting as a contender, with the appeal and six contender shadows a draw | 6.3 ± 0.4 | 6.2 % ± 0.4 | 60 % ± 16 | 33 ± 4 | 4 % ± 2 | 155 ± 75 | 3 % ± 2 |

### v3 as designed beside the proposal

| Network | Bad fixes merged per 100 paid | Good fixes wrongly unpaid | An honest solver's cost per good fix | …of which deposits lost | Fixes paid a year | Submissions that waited | Verdicts never final | Service fee, last 13 weeks | Opus 5.5 seated, share of the year | GPT-6.1 | Gemini 3.1 Pro | the four others, their shares added | No family met the rule, share of the year | Appeals a year | Correct rejections overturned, of those appealed | Bad fixes paid after an appeal, a year | Wrongly rejected good fixes paid in the end | Appeals with no panel |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad = the tests fail them: v3 as designed (second-opinion challenges, no test disputes) | 17.8 ± 1.2 | 21.9 % ± 2.1 | $1.37 ± 0.03 | $0.00 ± 0.00 | 391 ± 57 | 64.8 % ± 4.2 | 17.2 % ± 2.6 | $0.244 ± 0.012 | n/a | n/a | n/a | n/a | n/a | 0 ± 0 | n/a | 0.0 ± 0.0 | 1 % ± 0 | 0 ± 0 |
| bad = the tests fail them: seats by rank alone (no disputes, no deposit, no appeal) | 6.0 ± 0.2 | 6.0 % ± 0.2 | $1.64 ± 0.03 | $0.00 ± 0.00 | 1151 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = the tests fail them: …and disputes, the deposit, no appeal | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.93 ± 0.08 | $2.29 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = the tests fail them: **the proposal (D236)**: …and the appeal to other families, majority | 4.2 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | $0.85 ± 0.05 | 1162 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 95 % ± 1 | 0 ± 0 |
| bad = the tests fail them: the proposal, appeal to the seated families | 4.5 ± 0.2 | 8.9 % ± 0.2 | $3.92 ± 0.08 | $2.28 ± 0.08 | 1097 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 68 ± 2 |
| bad = the tests fail them: the proposal, appeal to other families, every judge must pass | 4.4 ± 0.2 | 7.5 % ± 0.2 | $3.61 ± 0.08 | $1.93 ± 0.07 | 1114 ± 10 | 0.1 % ± 0.0 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 24 % ± 2 | 0 ± 0 |
| bad = the tests fail them: the proposal, on live scores | 4.3 ± 0.2 | 3.3 % ± 0.2 | $2.53 ± 0.05 | $0.86 ± 0.05 | 1163 ± 10 | 0.1 % ± 0.1 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 99 % ± 2 | 1 % ± 2 | 0 % ± 0 | 0 % ± 0 | 1 % ± 1 | 71 ± 5 | n/a | 0.0 ± 0.0 | 94 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: v3 as designed (second-opinion challenges, no test disputes) | 14.3 ± 1.0 | 14.3 % ± 2.1 | $1.50 ± 0.05 | $0.00 ± 0.00 | 673 ± 120 | 43.2 % ± 9.2 | 9.0 % ± 2.6 | $0.177 ± 0.034 | n/a | n/a | n/a | n/a | n/a | 0 ± 0 | n/a | 0.0 ± 0.0 | 1 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: seats by rank alone (no disputes, no deposit, no appeal) | 11.7 ± 0.3 | 6.1 % ± 0.2 | $1.60 ± 0.00 | $0.00 ± 0.00 | 1235 ± 12 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = pass the tests, wrong: …and disputes, the deposit, no appeal | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.95 ± 0.08 | $2.35 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 0 ± 0 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 0 ± 0 |
| bad = pass the tests, wrong: **the proposal (D236)**: …and the appeal to other families, majority | 8.1 ± 0.2 | 3.5 % ± 0.2 | $2.57 ± 0.06 | $0.94 ± 0.06 | 1219 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 94 % ± 1 | 0 ± 0 |
| bad = pass the tests, wrong: the proposal, appeal to the seated families | 8.5 ± 0.2 | 9.0 % ± 0.3 | $3.97 ± 0.08 | $2.33 ± 0.08 | 1155 ± 11 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 0 % ± 0 | 23 ± 4 |
| bad = pass the tests, wrong: the proposal, appeal to other families, every judge must pass | 8.2 ± 0.2 | 5.2 % ± 0.2 | $3.01 ± 0.06 | $1.37 ± 0.06 | 1199 ± 10 | 0.0 % ± 0.0 | 0.2 % ± 0.1 | $0.010 ± 0.000 | 100 % ± 0 | 100 % ± 0 | 100 % ± 0 | 0 % ± 0 | 0 % ± 0 | 68 ± 2 | n/a | 0.0 ± 0.0 | 65 % ± 2 | 0 ± 0 |
| bad = pass the tests, wrong: the proposal, on live scores | 8.5 ± 0.4 | 3.9 % ± 0.3 | $2.55 ± 0.07 | $0.99 ± 0.07 | 1203 ± 14 | 0.9 % ± 0.3 | 0.0 % ± 0.0 | $0.010 ± 0.000 | 69 % ± 9 | 21 % ± 8 | 11 % ± 6 | 0 % ± 0 | 12 % ± 2 | 118 ± 22 | n/a | 0.0 ± 0.0 | 91 % ± 1 | 0 ± 0 |
