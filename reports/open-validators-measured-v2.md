# Open validators with measured judges, v2: contenders' disputes and the attackers (proof-of-fix#236, hypothesis H7; 2026-11-14)

**Status: exploratory.** It continues [`open-validators-measured-v1.md`](open-validators-measured-v1.md), which ran the honest network on proof-of-fix#160's measured judges. This report adds disputes backed by evidence and re-runs report v3's attackers. Seeds 1–40, the seeds the earlier rounds used, so nothing here is confirmatory.

**Command:** `python3 -m pof.sim.openval.contenders --seeds 40 --jobs 4` prints every table in the appendix, in about 5 minutes. Every ± is two standard errors of the mean. No model call: judges' verdicts are replayed from `data/judges/verdicts-v2.matrix.json`.

## In brief
- **Disputes backed by evidence help, by a third to a half, and no more.** With the best family judging alone, bad fixes merged fall from 6.0 per 100 paid to 4.4 if a contender finds a failing test for half of the bad fixes it flags, and to 3.5 at three in four.
- **The limit is measured, not assumed:** of the 18 bad fixes Opus 5.5 passed, only 11 were failed by any of the other eight models. The rest no contender flags.
- **Contending pays only with a good model.** A contender running Opus against a GPT-6.1 panel searches 2.4 fixes per verdict it reverses. The six open-weight models against an Opus panel search 35.
- **Evidence straightens v3's rank on one kind of bad fix and bends it on the other.** It only ever corrects a pass. A judge that rejects good fixes is never caught, so a strict judge rises.
- **Report v3's attackers still lose, with one exception.** The seed grinder is no longer shown to lose (+8 ± 59 $). The sybil still loses, but a third to a half of what it lost before.
- **A solver that just submits bad fixes gains on the flat fee in every world tried:** $1.80 a bad fix under the assumed judges, $10 to $28 under the measured ones. No collusion is needed. Report v3's own judged spammer, on the market fee, lost; it is not yet re-run on measured judges.
- **A deposit lost on rejection closes that.** With Opus alone it is about $19 on the median $86 bounty, and costs a solver of good fixes $1.13 a fix on average.

## 1. What was added to the model
- **A contender** is anyone running a model that failed a fix the panel passed: a family without a seat, or a seated one that was outvoted. It need not be a validator.
- **It looks for evidence a machine can check,** a failing test. Found evidence reverses the verdict half-way through its challenge window, with no second panel.
- **Which fixes a contender flags is measured:** the fixes its model failed in #160.
- **How often a flagged bad fix yields a failing test is assumed,** and swept: 1 in 4, 1 in 2, 3 in 4. One draw per fix, shared by every contender (a bug that is hard to test is hard for all of them).
- **Wrong evidence against a good fix is never accepted,** except in one row (1 time in 20).
- **Only fixes are judged on measured verdicts.** An ADR at the constitution tier keeps the assumed judges; #160 measured none.
- **The bad-fix solver** submits 5 bad fixes a week and colludes with nobody. It pays the attempt fee ($0.50) and its checks, as the race does today. What a bad fix costs to produce is not counted.

## 2. The cover: what contenders can reach (exact counts, no simulation)
A quarter of fixes bad, as in report v3. "Searched" counts every passed fix that some contender failed, good or bad: the work contenders pay for.

**Bad fixes the tests fail:**

| Panel | Contenders | Bad fixes passed | …a contender failed | Good fixes passed | …a contender failed | Bad merged per 100 paid: no disputes | Evidence found 1 in 2 | 3 in 4 | Fixes searched per reversal (1 in 2) |
|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 alone | every other seat | 18 of 100 | 11 | 47 of 50 | 30 | 6.0 | 4.2 | 3.3 | 34.7 |
| Opus 5.5 alone | GPT-6.1 only | 18 of 100 | 6 | 47 of 50 | 13 | 6.0 | 5.1 | 4.6 | 28.0 |
| Opus 5.5 alone | the six open-weight seats | 18 of 100 | 9 | 47 of 50 | 25 | 6.0 | 4.6 | 3.8 | 35.3 |
| GPT-6.1 alone | Opus 5.5 only | 40 of 100 | 28 | 35 of 50 | 1 | 16.0 | 11.0 | 8.3 | 2.4 |
| Opus 5.5 and GPT-6.1, both must pass | every other seat | 12 of 100 | 5 | 34 of 50 | 17 | 5.6 | 4.4 | 3.9 | 42.8 |
| Opus, GPT-6.1, Gemini, majority | every other seat | 44 of 100 | 20 | 47 of 50 | 25 | 13.5 | 10.8 | 9.3 | 17.0 |

**Bad fixes that pass the tests and are wrong:**

| Panel | Contenders | Bad fixes passed | …a contender failed | Good fixes passed | …a contender failed | Bad merged per 100 paid: no disputes | Evidence found 1 in 2 | 3 in 4 | Fixes searched per reversal (1 in 2) |
|---|---|---|---|---|---|---|---|---|---|
| Opus 5.5 alone | every other seat | 35 of 78 | 25 | 47 of 50 | 30 | 13.7 | 9.3 | 6.9 | 13.2 |
| Opus 5.5 alone | GPT-6.1 only | 35 of 78 | 21 | 47 of 50 | 13 | 13.7 | 10.0 | 8.0 | 7.8 |
| GPT-6.1 alone | every other seat | 15 of 78 | 5 | 35 of 50 | 18 | 8.4 | 7.1 | 6.4 | 35.7 |
| GPT-6.1 alone | Opus 5.5 only | 15 of 78 | 1 | 35 of 50 | 1 | 8.4 | 8.1 | 8.0 | 11.4 |
| Opus 5.5 and GPT-6.1, both must pass | every other seat | 14 of 78 | 4 | 34 of 50 | 17 | 8.1 | 7.0 | 6.5 | 41.8 |

- **Weak models do add something as contenders,** which they did not as panel members: the six open-weight seats flag 9 of Opus's 18 false passes.
- **They pay for it in wasted searches.** They also fail 25 of the 47 good fixes Opus passed, so most of their searches find nothing.
- **The reward per reversal has to cover the searches.** At 35 searches per reversal, a reward of a quarter of an $86 bounty covers a search costing up to about $0.60. For Opus contending against GPT-6.1 the same reward covers a search of $9.
- **That is a market reason to contend with the best model:** the better the contender, the fewer searches it wastes.
- **The best panel leaves contenders the least.** Against "Opus and GPT-6.1, both must pass", nobody else flags more than 5 of the 12 bad fixes passed.

## 3. The network with disputes (seven families, 40 seeds)

| Network | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Reversed by evidence a year | Submissions that waited |
|---|---|---|---|---|---|
| **Bad = the tests fail them** | | | | | |
| v3 as designed, no disputes | 17.8 ± 1.2 | 8.6 % ± 1.1 | 391 ± 57 | 0 | 64.8 % ± 4.2 |
| v3 as designed, evidence found 1 in 2 | 8.0 ± 0.9 | 4.4 % ± 0.9 | 210 ± 8 | 10 ± 1 | 77.6 % ± 0.6 |
| v3 as designed, evidence found 3 in 4 | 5.6 ± 0.7 | 4.5 % ± 0.9 | 193 ± 9 | 12 ± 2 | 78.8 % ± 0.9 |
| v3's scores, no family cap, evidence 1 in 2 | 6.7 ± 1.0 | 10.5 % ± 2.4 | 1,001 ± 77 | 36 ± 8 | 7.1 % ± 6.9 |
| Top family alone (Opus), no disputes | 6.0 ± 0.2 | 5.6 % ± 0.2 | 1,136 ± 10 | 0 | 0.1 % |
| Top family alone, evidence 1 in 4 | 5.2 ± 0.2 | 5.6 % ± 0.2 | 1,126 ± 10 | 10 ± 1 | 0.1 % |
| Top family alone, evidence 1 in 2 | 4.4 ± 0.2 | 5.6 % ± 0.2 | 1,116 ± 10 | 20 ± 1 | 0.1 % |
| Top family alone, evidence 3 in 4 | 3.5 ± 0.2 | 5.6 % ± 0.2 | 1,105 ± 10 | 30 ± 2 | 0.1 % |
| Top family alone, evidence 1 in 2, wrong evidence accepted 1 in 20 | 4.5 ± 0.2 | 8.6 % ± 0.2 | 1,083 ± 10 | 53 ± 2 | 0.1 % |
| **Bad = pass the tests, wrong** | | | | | |
| v3 as designed, no disputes | 14.3 ± 1.0 | 6.9 % ± 0.9 | 673 ± 120 | 0 | 43.2 % ± 9.2 |
| v3 as designed, evidence found 1 in 2 | 9.5 ± 0.7 | 5.9 % ± 0.9 | 308 ± 53 | 13 ± 3 | 69.6 % ± 4.3 |
| v3's scores, no family cap, evidence 1 in 2 | 8.5 ± 0.7 | 20.5 % ± 2.0 | 891 ± 58 | 29 ± 6 | 7.4 % ± 5.8 |
| Top family alone (GPT-6.1), no disputes | 8.4 ± 0.3 | 27.4 % ± 0.4 | 842 ± 8 | 0 | 3.5 % |
| Top family alone, evidence 1 in 2 | 7.1 ± 0.3 | 27.4 % ± 0.4 | 831 ± 8 | 11 ± 1 | 3.5 % |
| Top family alone, evidence 3 in 4 | 6.6 ± 0.3 | 27.4 % ± 0.4 | 826 ± 8 | 17 ± 1 | 3.5 % |

- **v3 as designed gains the most from evidence** (17.8 to 5.6 at three in four), because it had the most to correct. It still stalls: three submissions in four never get a panel, because of the family cap.
- **v3's scores without the family cap, with evidence at 1 in 2, reach 6.7 per 100.** That is close to the known-answer rank without disputes (6.0), from a rule the network can actually compute.
- **Wrong evidence is expensive.** Accepted 1 time in 20, it rejects another 3 % of good fixes. The check on evidence has to be mechanical.
- **Nothing here disputes a rejection.** Good fixes rejected stay rejected (5.6 % with Opus, 27 % with GPT-6.1).

## 4. Does evidence fix v3's rank? On one kind of bad fix
v3's score, seven families, v3 as designed. "Known answers" is the score the family would have on the truth.

| Family | Bad = the tests fail them: known answers | No disputes | Evidence 3 in 4 | Bad = pass the tests, wrong: known answers | No disputes | Evidence 3 in 4 |
|---|---|---|---|---|---|---|
| Opus 5.5 | 88 % | 70.8 % | 87.5 % | 75 % | 85.3 % | 73.6 % |
| GPT-6.1 | 65 % | 86.0 % | 76.3 % | 75 % | 85.9 % | 89.3 % |
| Gemini 3.1 Pro | 60 % | 63.5 % | 60.9 % | 74 % | 70.4 % | 72.8 % |
| DeepSeek V3.2 | 55 % | 68.0 % | 63.2 % | 59 % | 69.8 % | 65.5 % |
| Qwen3 235B | 50 % | 75.4 % | 62.1 % | 51 % | 72.2 % | 64.3 % |
| Mistral Large 3 | 51 % | 64.0 % | 59.4 % | 51 % | 60.4 % | 57.5 % |
| Nemotron 3 Super | 52 % | 77.3 % | 64.4 % | 52 % | 67.7 % | 63.2 % |

- **On fixes the tests fail, evidence puts the families in the right order.** Opus rises from 70.8 % to 87.5 % and is barred 15 % of the year, down from 69 %. The weak families fall below the 70 % bar.
- **GPT-6.1 stays too high in both columns** (76 % and 89 % against 65 % and 75 %). It fails 30 % of good fixes, and no dispute ever shows that.
- **So the score is one-sided.** Evidence supplies known answers for passes only. A rank fed this way rewards a judge for rejecting.
- **The fix has to come from the other side:** a known answer for a rejected good fix. A solver's appeal, or fixes with known answers slipped into the queue, would supply it. Neither is modelled here.

## 5. The attackers on measured judges
Report v3's nine design rows, each on its assumed judges and on #160's (four families, bad fixes the tests fail), a year, against the honest twin.

| Attacker | Assumed judges: return − twin's ($) | Measured: return − twin's ($) | Measured: against its twin | What it got, measured |
|---|---|---|---|---|
| Sybil, 10 of 30, spread | −21,535 ± 2,510 | −7,340 ± 1,696 | loses | 71 bad fixes paid of 96 (assumed: 16) |
| Sybil, 10 of 30, one host and family | −17,969 ± 1,752 | −8,310 ± 1,280 | loses | 68 of 96 (assumed: 5) |
| Colluding lone validator | −247 ± 41 | −127 ± 40 | loses | 7.2 of 18 (assumed: 0.4) |
| Seed grinder | −272 ± 48 | +8 ± 59 | **not significant** | 9.0 of 24 (assumed: 0.6) |
| Silent judge | −14 ± 9 | −14 ± 8 | loses | unchanged |
| Fee farmer | −545 ± 3 | −545 ± 3 | loses | unchanged |
| Constitution coalition, 5 validators | −280 ± 147 | −418 ± 126 | loses | ADRs keep the assumed judges |
| Constitution coalition, 3 validators | −431 ± 145 | −433 ± 142 | loses | ADRs keep the assumed judges |
| Herders, four of GPT-6.1's family (v3's scores) | n/a | −7 ± 2 | loses | its family barred 72 % of the year (twin: 2 %) |
| Herders, four of DeepSeek's family (v3's scores) | n/a | −1 ± 1 | not significant | its family is barred either way (87 % against 82 %) |

- **The attackers that pass bad fixes get far more of them paid,** and none of it comes from their attack: the honest judges pass most of those fixes anyway.
- **They still lose,** because the slashes for fabricated receipts are unchanged. The sybil's loss shrinks to between a third and a half.
- **The seed grinder is the one that crosses:** +8 ± 59 $, no longer shown to lose, with 9 of its 24 bad fixes paid against 0.6 before.
- **The proof-level and pricing attackers are not re-run.** They don't depend on judges' accuracy the same way; they are still owed for H7.

**A solver that submits bad fixes and colludes with nobody.** Report v3 had one in its pricing table ("Spammer: a bad fix a day, judged"), which lost $915 ± 28 a year: it ran on the market fee, with independent judges right 90 % of the time and three validators of its own to pay for. The rows below are a different world (the flat fee, the score world's judges, no validators), so the first row is not a re-run of v3's. v3's spammer on measured judges is still owed.

| World | Bad fixes paid, of 261 submitted | Return a year ($) | Return a bad fix submitted |
|---|---|---|---|
| Assumed judges, v3's scores | 10 (4 %) | +470 ± 110 | $1.80 |
| Measured, four families, v3 as designed, bad = the tests fail them | 15 (6 %) | +871 ± 218 | $3.34 |
| Measured, four families, v3 as designed, bad = pass the tests, wrong | 79 (30 %) | +7,403 ± 1,034 | $28.36 |
| Measured, top family alone, bad = the tests fail them | 46 (17 %) | +4,215 ± 237 | $16.14 |
| Measured, top family alone, bad = pass the tests, wrong | 48 (18 %) | +4,263 ± 220 | $16.33 |
| Measured, top family alone, evidence 1 in 2, bad = the tests fail them | 31 (12 %) | +2,754 ± 204 | $10.55 |
| Measured, top family alone, evidence 1 in 2, bad = pass the tests, wrong | 40 (15 %) | +3,511 ± 235 | $13.45 |

- **It gains in every row here, the assumed judges included.** A rejected fix costs its solver the attempt fee and its checks, $1 or less, and a bad fix that passes pays the bounty.
- **It gains whenever a bad fix costs less to produce than the last column.** An agent's attempt costs a few dollars at most.
- **The second row is low only because that network stalls:** most of its submissions never get a panel.
- **Disputes cut the gain by a fifth to a third and leave it positive.**

**A deposit lost on rejection closes it** (exact, at the median bounty of $86; attempt fee and checks aside):

| Bad fixes | Panel | Disputes | A bad fix is paid | Deposit at which a bad fix stops paying | What it costs a good fix, on average |
|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 alone | none | 18 % | $19 | $1.13 |
| the tests fail them | Opus 5.5 alone | evidence 1 in 2 | 12 % | $12 | $0.74 |
| the tests fail them | Opus and GPT-6.1, both must pass | none | 12 % | $12 | $3.75 |
| the tests fail them | Opus, GPT-6.1, Gemini, majority | none | 44 % | $68 | $4.05 |
| pass the tests, wrong | Opus 5.5 alone | none | 45 % | $70 | $4.20 |
| pass the tests, wrong | GPT-6.1 alone | none | 19 % | $20 | $6.14 |
| pass the tests, wrong | GPT-6.1 alone | evidence 1 in 2 | 16 % | $16 | $4.92 |

- **The deposit scales with the judge's false-pass rate,** so a better panel means a smaller deposit. That is a second market reason to seat the best family.
- **A strict judge makes the deposit costly for honest solvers:** GPT-6.1 rejects 30 % of good fixes, so its $20 deposit costs a good fix $6.14 on average, against $1.13 with Opus.

## 6. What this does not show
- **How often evidence can be found is assumed.** No one has measured how often a contender's model, having failed a fix, can write a failing test for it. This is the number the next paid experiment should measure.
- **A contender flags only what its model failed in one review call.** A contender that writes and runs tests on every fix could reach more of the false passes, at a higher cost per search.
- **Rejections are never disputed here.** The solver's appeal is not modelled.
- **Whether a failing test is a fair test is assumed to be checkable by a machine.** A test that encodes a wrong requirement would need judging, which brings the judges back.
- **Contenders' money is not simulated:** the reward per reversal, a contender's bond, and what a search costs are worked from the counts in section 2, not played out.
- **The proof-level and pricing attackers, and the market fee, are not re-run.**
- **The bad-fix solver's fixes are #160's honest failures.** Fixes written to beat a judge would pass more often.
- **Seeds 1–40, exploratory.** H6 and H7 need a confirmatory run on seeds 41–80 with the rules frozen first.
- **228 cases, one verdict each, one benchmark,** as in v1.

## 7. What it means for the design (#236)
1. **Seats by rank, disputes by anyone.** The best family judges; every other model earns by reversing its false passes with evidence. Weak models are worth something in the second role and nothing in the first.
2. **Pay contenders per reversal, enough to cover the wasted searches.** The counts in section 2 size it, and they make contending with a better model more profitable.
3. **Add a solver's deposit, lost on rejection,** sized from the seated panel's false-pass rate. Without it a bad-fix solver gains under any judges, the assumed ones included.
4. **Feed the rank from both sides.** Evidence gives known answers for passes; something else (appeals, or fixes with known answers) has to give them for rejections, or the rank rewards rejecting.
5. **Drop the hard family cap,** as v1 found. With evidence, v3's own score without the cap gets close to the known-answer rank on fixes the tests fail.
6. **The floor found so far is 3.5 to 4.4 bad fixes per 100 paid** on fixes the tests fail and 6.6 to 7.1 on fixes that pass them, against the 1.1 ADR 0004 was sized on.

## Appendix: the full output

Seeds 1-40; every ± is two standard errors of the mean.

### The cover (exact, from #160's verdicts; a quarter of fixes bad)

| Bad fixes | Panel | Contenders | Bad fixes passed | …that a contender failed | Good fixes passed | …that a contender failed | Bad merged per 100 paid: no disputes | evidence found 1 time in 4 | 1 in 2 | 3 in 4 | Fixes searched per reversal (1 in 2) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 alone | every other seat | 18 of 100 | 11 | 47 of 50 | 30 | 6.0 | 5.1 | 4.2 | 3.3 | 34.7 |
| the tests fail them | Opus 5.5 alone | GPT-6.1 only | 18 of 100 | 6 | 47 of 50 | 13 | 6.0 | 5.5 | 5.1 | 4.6 | 28.0 |
| the tests fail them | Opus 5.5 alone | the six open-weight seats | 18 of 100 | 9 | 47 of 50 | 25 | 6.0 | 5.3 | 4.6 | 3.8 | 35.3 |
| the tests fail them | GPT-6.1 alone | every other seat | 40 of 100 | 33 | 35 of 50 | 18 | 16.0 | 13.1 | 10.1 | 6.8 | 8.5 |
| the tests fail them | GPT-6.1 alone | Opus 5.5 only | 40 of 100 | 28 | 35 of 50 | 1 | 16.0 | 13.6 | 11.0 | 8.3 | 2.4 |
| the tests fail them | GPT-6.1 alone | the six open-weight seats | 40 of 100 | 18 | 35 of 50 | 18 | 16.0 | 14.5 | 12.9 | 11.2 | 14.0 |
| the tests fail them | Opus 5.5 and GPT-6.1, both must pass | every other seat | 12 of 100 | 5 | 34 of 50 | 17 | 5.6 | 5.0 | 4.4 | 3.9 | 42.8 |
| the tests fail them | Opus 5.5 and GPT-6.1, both must pass | the six open-weight seats | 12 of 100 | 5 | 34 of 50 | 17 | 5.6 | 5.0 | 4.4 | 3.9 | 42.8 |
| the tests fail them | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | every other seat | 44 of 100 | 20 | 47 of 50 | 25 | 13.5 | 12.1 | 10.8 | 9.3 | 17.0 |
| the tests fail them | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | the six open-weight seats | 44 of 100 | 20 | 47 of 50 | 25 | 13.5 | 12.1 | 10.8 | 9.3 | 17.0 |
| pass the tests, wrong | Opus 5.5 alone | every other seat | 35 of 78 | 25 | 47 of 50 | 30 | 13.7 | 11.6 | 9.3 | 6.9 | 13.2 |
| pass the tests, wrong | Opus 5.5 alone | GPT-6.1 only | 35 of 78 | 21 | 47 of 50 | 13 | 13.7 | 11.9 | 10.0 | 8.0 | 7.8 |
| pass the tests, wrong | Opus 5.5 alone | the six open-weight seats | 35 of 78 | 16 | 47 of 50 | 25 | 13.7 | 12.4 | 10.9 | 9.5 | 16.6 |
| pass the tests, wrong | GPT-6.1 alone | every other seat | 15 of 78 | 5 | 35 of 50 | 18 | 8.4 | 7.7 | 7.1 | 6.4 | 35.7 |
| pass the tests, wrong | GPT-6.1 alone | Opus 5.5 only | 15 of 78 | 1 | 35 of 50 | 1 | 8.4 | 8.3 | 8.1 | 8.0 | 11.4 |
| pass the tests, wrong | GPT-6.1 alone | the six open-weight seats | 15 of 78 | 4 | 35 of 50 | 18 | 8.4 | 7.9 | 7.4 | 6.8 | 44.1 |
| pass the tests, wrong | Opus 5.5 and GPT-6.1, both must pass | every other seat | 14 of 78 | 4 | 34 of 50 | 17 | 8.1 | 7.6 | 7.0 | 6.5 | 41.8 |
| pass the tests, wrong | Opus 5.5 and GPT-6.1, both must pass | the six open-weight seats | 14 of 78 | 4 | 34 of 50 | 17 | 8.1 | 7.6 | 7.0 | 6.5 | 41.8 |
| pass the tests, wrong | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | every other seat | 29 of 78 | 10 | 47 of 50 | 25 | 11.6 | 10.8 | 9.8 | 8.9 | 25.4 |
| pass the tests, wrong | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | the six open-weight seats | 29 of 78 | 10 | 47 of 50 | 25 | 11.6 | 10.8 | 9.8 | 8.9 | 25.4 |

### The network with disputes backed by evidence (seven families)

| Network | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Verdicts reversed by evidence a year | Fixes searched per reversal | Submissions that waited |
|---|---|---|---|---|---|---|
| bad = the tests fail them: **v3 as designed**, no disputes | 17.8 ± 1.2 | 8.6 % ± 1.1 | 391 ± 57 | 0 ± 0 | n/a | 64.8 % ± 4.2 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | 11.9 ± 1.3 | 5.9 % ± 1.0 | 227 ± 13 | 7 ± 1 | 31.0 ± 4.9 | 76.6 % ± 1.2 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | 8.0 ± 0.9 | 4.4 % ± 0.9 | 210 ± 8 | 10 ± 1 | 19.2 ± 2.5 | 77.6 % ± 0.6 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | 5.6 ± 0.7 | 4.5 % ± 0.9 | 193 ± 9 | 12 ± 2 | 14.5 ± 1.8 | 78.8 % ± 0.9 |
| bad = the tests fail them: v3's scores, no family cap, evidence found 1 in 2 | 6.7 ± 1.0 | 10.5 % ± 2.4 | 1001 ± 77 | 36 ± 8 | 22.7 ± 3.3 | 7.1 % ± 6.9 |
| bad = the tests fail them: **top family alone**, no disputes | 6.0 ± 0.2 | 5.6 % ± 0.2 | 1136 ± 10 | 0 ± 0 | n/a | 0.1 % ± 0.0 |
| bad = the tests fail them: top family alone, evidence found 1 time in 4 | 5.2 ± 0.2 | 5.6 % ± 0.2 | 1126 ± 10 | 10 ± 1 | 78.8 ± 8.7 | 0.1 % ± 0.0 |
| bad = the tests fail them: top family alone, evidence found 1 in 2 | 4.4 ± 0.2 | 5.6 % ± 0.2 | 1116 ± 10 | 20 ± 1 | 38.2 ± 2.6 | 0.1 % ± 0.0 |
| bad = the tests fail them: top family alone, evidence found 3 in 4 | 3.5 ± 0.2 | 5.6 % ± 0.2 | 1105 ± 10 | 30 ± 2 | 24.7 ± 1.4 | 0.1 % ± 0.0 |
| bad = the tests fail them: top family alone, evidence 1 in 2, the only contender GPT-6.1 | 5.1 ± 0.2 | 5.6 % ± 0.2 | 1125 ± 10 | 11 ± 1 | 31.2 ± 3.3 | 0.1 % ± 0.0 |
| bad = the tests fail them: top family alone, evidence 1 in 2, wrong evidence accepted 1 time in 20 | 4.5 ± 0.2 | 8.6 % ± 0.2 | 1083 ± 10 | 53 ± 2 | 13.9 ± 0.6 | 0.1 % ± 0.0 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | 14.3 ± 1.0 | 6.9 % ± 0.9 | 673 ± 120 | 0 ± 0 | n/a | 43.2 % ± 9.2 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | 11.6 ± 0.8 | 5.9 % ± 0.9 | 380 ± 84 | 9 ± 2 | 37.4 ± 5.0 | 64.5 % ± 6.7 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | 9.5 ± 0.7 | 5.9 % ± 0.9 | 308 ± 53 | 13 ± 3 | 19.5 ± 1.9 | 69.6 % ± 4.3 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | 7.5 ± 0.5 | 6.0 % ± 1.1 | 266 ± 48 | 15 ± 4 | 14.8 ± 1.5 | 72.7 % ± 3.9 |
| bad = pass the tests, wrong: v3's scores, no family cap, evidence found 1 in 2 | 8.5 ± 0.7 | 20.5 % ± 2.0 | 891 ± 58 | 29 ± 6 | 21.5 ± 2.9 | 7.4 % ± 5.8 |
| bad = pass the tests, wrong: **top family alone**, no disputes | 8.4 ± 0.3 | 27.4 % ± 0.4 | 842 ± 8 | 0 ± 0 | n/a | 3.5 % ± 0.2 |
| bad = pass the tests, wrong: top family alone, evidence found 1 time in 4 | 7.7 ± 0.3 | 27.4 % ± 0.4 | 836 ± 8 | 6 ± 1 | 79.3 ± 11.3 | 3.5 % ± 0.2 |
| bad = pass the tests, wrong: top family alone, evidence found 1 in 2 | 7.1 ± 0.3 | 27.4 % ± 0.4 | 831 ± 8 | 11 ± 1 | 41.2 ± 5.0 | 3.5 % ± 0.2 |
| bad = pass the tests, wrong: top family alone, evidence found 3 in 4 | 6.6 ± 0.3 | 27.4 % ± 0.4 | 826 ± 8 | 17 ± 1 | 27.1 ± 2.3 | 3.5 % ± 0.2 |
| bad = pass the tests, wrong: top family alone, evidence 1 in 2, the only contender Opus 5.5 | 8.1 ± 0.3 | 27.4 % ± 0.4 | 840 ± 8 | 3 ± 1 | 13.0 ± 2.4 | 3.5 % ± 0.2 |
| bad = pass the tests, wrong: top family alone, evidence 1 in 2, wrong evidence accepted 1 time in 20 | 7.3 ± 0.3 | 29.3 % ± 0.4 | 811 ± 8 | 31 ± 1 | 13.7 ± 0.6 | 3.5 % ± 0.2 |

### Scores by v3's rule, with disputes

| World | Family (seat) | Measured: bad passed / good failed | Score on known answers | Score by v3's rule | Barred, share of the year |
|---|---|---|---|---|---|
| bad = the tests fail them: **v3 as designed**, no disputes | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 70.8 % ± 4.8 | 69 % ± 13 |
| bad = the tests fail them: **v3 as designed**, no disputes | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 86.0 % ± 2.9 | 14 % ± 10 |
| bad = the tests fail them: **v3 as designed**, no disputes | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 63.5 % ± 2.3 | 92 % ± 2 |
| bad = the tests fail them: **v3 as designed**, no disputes | `deepseek` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 68.0 % ± 2.2 | 84 % ± 7 |
| bad = the tests fail them: **v3 as designed**, no disputes | `qwen` (Qwen3 235B) | 83 % / 16 % | 50 % | 75.4 % ± 4.8 | 52 % ± 15 |
| bad = the tests fail them: **v3 as designed**, no disputes | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 64.0 % ± 2.2 | 93 % ± 2 |
| bad = the tests fail them: **v3 as designed**, no disputes | `nvidia` (Nemotron 3 Super) | 70 % / 26 % | 52 % | 77.3 % ± 4.3 | 49 % ± 14 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 78.8 % ± 5.0 | 41 % ± 15 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 81.2 % ± 3.6 | 31 % ± 14 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 61.9 % ± 2.2 | 95 % ± 2 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `deepseek` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 67.5 % ± 2.7 | 79 % ± 12 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `qwen` (Qwen3 235B) | 83 % / 16 % | 50 % | 66.5 % ± 3.8 | 79 % ± 12 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 63.0 % ± 2.2 | 96 % ± 0 |
| bad = the tests fail them: v3 as designed, evidence found 1 time in 4 | `nvidia` (Nemotron 3 Super) | 70 % / 26 % | 52 % | 68.4 % ± 4.0 | 71 % ± 13 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 84.5 % ± 3.9 | 22 % ± 13 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 76.7 % ± 3.7 | 38 % ± 15 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 61.9 % ± 2.3 | 94 % ± 5 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `deepseek` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 65.9 % ± 2.6 | 77 % ± 12 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `qwen` (Qwen3 235B) | 83 % / 16 % | 50 % | 63.9 % ± 2.5 | 89 % ± 8 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 60.3 % ± 2.2 | 96 % ± 2 |
| bad = the tests fail them: v3 as designed, evidence found 1 in 2 | `nvidia` (Nemotron 3 Super) | 70 % / 26 % | 52 % | 65.6 % ± 3.5 | 81 % ± 11 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 87.5 % ± 2.8 | 15 % ± 11 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 76.3 % ± 4.1 | 41 % ± 15 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 60.9 % ± 2.2 | 96 % ± 1 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `deepseek` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 63.2 % ± 2.3 | 89 % ± 7 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `qwen` (Qwen3 235B) | 83 % / 16 % | 50 % | 62.1 % ± 2.5 | 94 % ± 5 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 59.4 % ± 2.0 | 96 % ± 0 |
| bad = the tests fail them: v3 as designed, evidence found 3 in 4 | `nvidia` (Nemotron 3 Super) | 70 % / 26 % | 52 % | 64.4 % ± 3.7 | 79 % ± 12 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 85.3 % ± 4.8 | 26 % ± 13 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 85.9 % ± 2.1 | 8 % ± 8 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 70.4 % ± 2.9 | 58 % ± 13 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `deepseek` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 69.8 % ± 2.8 | 80 % ± 9 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `qwen` (Qwen3 235B) | 82 % / 16 % | 51 % | 72.2 % ± 3.6 | 73 % ± 11 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 60.4 % ± 3.0 | 95 % ± 1 |
| bad = pass the tests, wrong: **v3 as designed**, no disputes | `nvidia` (Nemotron 3 Super) | 69 % / 26 % | 52 % | 67.7 % ± 2.9 | 83 % ± 7 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 78.0 % ± 4.0 | 43 % ± 15 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 87.3 % ± 2.5 | 7 % ± 8 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 72.2 % ± 3.4 | 60 % ± 14 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `deepseek` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 67.8 % ± 2.6 | 83 % ± 9 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `qwen` (Qwen3 235B) | 82 % / 16 % | 51 % | 68.5 % ± 2.3 | 85 % ± 9 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 59.7 % ± 3.0 | 94 % ± 5 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 time in 4 | `nvidia` (Nemotron 3 Super) | 69 % / 26 % | 52 % | 64.5 % ± 2.6 | 91 % ± 5 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 73.7 % ± 3.2 | 52 % ± 15 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 88.9 % ± 2.6 | 7 % ± 8 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 71.9 % ± 3.1 | 59 % ± 14 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `deepseek` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 67.7 % ± 2.2 | 82 % ± 10 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `qwen` (Qwen3 235B) | 82 % / 16 % | 51 % | 66.0 % ± 2.2 | 90 % ± 7 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 59.3 % ± 2.8 | 94 % ± 5 |
| bad = pass the tests, wrong: v3 as designed, evidence found 1 in 2 | `nvidia` (Nemotron 3 Super) | 69 % / 26 % | 52 % | 64.3 % ± 2.9 | 88 % ± 8 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 73.6 % ± 3.5 | 57 % ± 14 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 89.3 % ± 2.2 | 7 % ± 8 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 72.8 % ± 3.1 | 57 % ± 14 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `deepseek` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 65.5 % ± 2.1 | 91 % ± 7 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `qwen` (Qwen3 235B) | 82 % / 16 % | 51 % | 64.3 % ± 2.2 | 92 % ± 7 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 57.5 % ± 2.3 | 97 % ± 0 |
| bad = pass the tests, wrong: v3 as designed, evidence found 3 in 4 | `nvidia` (Nemotron 3 Super) | 69 % / 26 % | 52 % | 63.2 % ± 3.1 | 89 % ± 8 |

### Each attacker against its honest twin

| Attacker | Return − twin's ($, ± 2 SE) | Against its twin | Attacker's return | Twin's return | What it got |
|---|---|---|---|---|---|
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families; assumed judges | -21,535 ± 2,510 | loses | -22,679 | -1,144 | 16.0 bad fixes paid of 96; a majority on 8 % of its own panels; 17.7 false verdicts proven |
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families; **measured**, bad = the tests fail them | -7,340 ± 1,696 | loses | -8,483 | -1,143 | 70.8 bad fixes paid of 96; a majority on 8 % of its own panels; 11.1 false verdicts proven |
| Sybil: 10 of 30 validators, one host, TEE type and family; assumed judges | -17,969 ± 1,752 | loses | -19,123 | -1,154 | 5.0 bad fixes paid of 96; a majority on 0 % of its own panels; 14.0 false verdicts proven |
| Sybil: 10 of 30 validators, one host, TEE type and family; **measured**, bad = the tests fail them | -8,310 ± 1,280 | loses | -9,463 | -1,152 | 68.2 bad fixes paid of 96; a majority on 0 % of its own panels; 11.6 false verdicts proven |
| Colluding lone validator (the genesis, bonded $100); assumed judges | -247 ± 41 | loses | -306 | -59 | 0.4 bad fixes paid of 18 attempts; 5.1 false verdicts proven, 0.0 challenges still frozen; 50.9 newcomers qualified (twin: 50.9) |
| Colluding lone validator (the genesis, bonded $100); **measured**, bad = the tests fail them | -127 ± 40 | loses | -186 | -59 | 7.2 bad fixes paid of 18 attempts; 7.9 false verdicts proven, 0.0 challenges still frozen; 47.7 newcomers qualified (twin: 47.4) |
| Seed grinder (v3's seed: a later block); assumed judges | -272 ± 48 | loses | -332 | -59 | 0.6 bad fixes paid of 24 attempts; 5.5 false verdicts proven, 0.0 challenges still frozen; 51.0 newcomers qualified (twin: 51.0) |
| Seed grinder (v3's seed: a later block); **measured**, bad = the tests fail them | +8 ± 59 | not significant | -51 | -59 | 9.0 bad fixes paid of 24 attempts; 5.3 false verdicts proven, 0.0 challenges still frozen; 48.0 newcomers qualified (twin: 47.9) |
| Silent judge (bribed on 10 % of its draws); assumed judges | -14 ± 9 | loses | -123 | -109 | 63.9 silences, suspended 8.4 times (k never shrank) |
| Silent judge (bribed on 10 % of its draws); **measured**, bad = the tests fail them | -14 ± 8 | loses | -123 | -109 | 64.8 silences, suspended 8.5 times (k never shrank) |
| Fee farmer (10 idle nodes at the bond floor; twin: one node); assumed judges | -545 ± 3 | loses | -605 | -60 | 44.1 counted checks a node |
| Fee farmer (10 idle nodes at the bond floor; twin: one node); **measured**, bad = the tests fail them | -545 ± 3 | loses | -605 | -60 | 47.8 counted checks a node |
| Constitution coalition (5 early validators); assumed judges | -280 ± 147 | loses | -593 | -313 | 0.3 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |
| Constitution coalition (5 early validators); **measured**, bad = the tests fail them | -418 ± 126 | loses | -728 | -310 | 0.2 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |
| Constitution coalition (3 early validators); assumed judges | -431 ± 145 | loses | -619 | -188 | 0.1 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |
| Constitution coalition (3 early validators); **measured**, bad = the tests fail them | -433 ± 142 | loses | -618 | -186 | 0.1 ADRs passed of 52; passed while fewer than K_MAX were eligible: 0 |
| Herders: four validators of `openai` (GPT-6.1), receipts not detectable; **measured**, v3's scores | -7 ± 2 | loses | -472 | -465 | 28 votes herded of 73 counted; its family barred 72 % of the year (twin: 2 %) |
| Herders: four validators of `open-weight` (DeepSeek V3.2), receipts not detectable; **measured**, v3's scores | -1 ± 1 | not significant | -473 | -472 | 5 votes herded of 44 counted; its family barred 87 % of the year (twin: 82 %) |
| Bad-fix solver (5 a week, no collusion); assumed judges (report v3's score world), v3's scores | +470 ± 110 | **wins** | 470 | 0 | 10 bad fixes paid of 261 (4 %); $1.80 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, four families, v3 as designed, bad = the tests fail them | +871 ± 218 | **wins** | 871 | 0 | 15 bad fixes paid of 261 (6 %); $3.34 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, four families, v3 as designed, bad = pass the tests, wrong | +7,403 ± 1,034 | **wins** | 7,403 | 0 | 79 bad fixes paid of 261 (30 %); $28.36 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, top family alone, bad = the tests fail them | +4,215 ± 237 | **wins** | 4,215 | 0 | 46 bad fixes paid of 261 (17 %); $16.14 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, top family alone, bad = pass the tests, wrong | +4,263 ± 220 | **wins** | 4,263 | 0 | 48 bad fixes paid of 261 (18 %); $16.33 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, top family alone, evidence found 1 in 2, bad = the tests fail them | +2,754 ± 204 | **wins** | 2,754 | 0 | 31 bad fixes paid of 261 (12 %); $10.55 a bad fix submitted |
| Bad-fix solver (5 a week, no collusion); **measured**, top family alone, evidence found 1 in 2, bad = pass the tests, wrong | +3,511 ± 235 | **wins** | 3,511 | 0 | 40 bad fixes paid of 261 (15 %); $13.45 a bad fix submitted |

### The deposit that stops a bad fix paying (median bounty $86)

| Bad fixes | Panel | Disputes | A bad fix is paid | Deposit at which a bad fix stops paying | What that deposit costs a good fix, on average |
|---|---|---|---|---|---|
| the tests fail them | Opus 5.5 alone | none | 18 % | $19 | $1.13 |
| the tests fail them | Opus 5.5 alone | evidence found 1 in 2 | 12 % | $12 | $0.74 |
| the tests fail them | GPT-6.1 alone | none | 40 % | $57 | $17.20 |
| the tests fail them | GPT-6.1 alone | evidence found 1 in 2 | 24 % | $26 | $7.93 |
| the tests fail them | Opus 5.5 and GPT-6.1, both must pass | none | 12 % | $12 | $3.75 |
| the tests fail them | Opus 5.5 and GPT-6.1, both must pass | evidence found 1 in 2 | 10 % | $9 | $2.89 |
| the tests fail them | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | none | 44 % | $68 | $4.05 |
| the tests fail them | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | evidence found 1 in 2 | 34 % | $44 | $2.66 |
| pass the tests, wrong | Opus 5.5 alone | none | 45 % | $70 | $4.20 |
| pass the tests, wrong | Opus 5.5 alone | evidence found 1 in 2 | 29 % | $35 | $2.09 |
| pass the tests, wrong | GPT-6.1 alone | none | 19 % | $20 | $6.14 |
| pass the tests, wrong | GPT-6.1 alone | evidence found 1 in 2 | 16 % | $16 | $4.92 |
| pass the tests, wrong | Opus 5.5 and GPT-6.1, both must pass | none | 18 % | $19 | $6.02 |
| pass the tests, wrong | Opus 5.5 and GPT-6.1, both must pass | evidence found 1 in 2 | 15 % | $16 | $5.00 |
| pass the tests, wrong | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | none | 37 % | $51 | $3.05 |
| pass the tests, wrong | Opus 5.5, GPT-6.1, Gemini 3.1 Pro, majority | evidence found 1 in 2 | 31 % | $38 | $2.29 |
