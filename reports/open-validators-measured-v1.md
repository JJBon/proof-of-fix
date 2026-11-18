# Open validators with measured judges, v1 (proof-of-fix#236, hypothesis H7; 2026-11-14)

**Status: a first cut. The honest network only; the attackers' table is not re-run yet.** Continued in [`open-validators-measured-v2.md`](open-validators-measured-v2.md): disputes backed by evidence and the attackers. v3's simulation assumed its judges: right 85–95 % of the time (one weak family at 68 %), every call independent. proof-of-fix#160 measured nine models on 228 real fixes ([`judges-v2.md`](judges-v2.md)). This report runs the same network with those verdicts in place of the assumption.

**Command:** `python3 -m pof.sim.openval.measured --seeds 40 --jobs 4` prints every table in the appendix, in about 4 minutes. Seeds 1–40; every ± is two standard errors of the mean. No model call.

## In brief
- **With measured judges, v3 as designed merges 10 to 18 bad fixes per 100 paid,** against 1.1 under the assumed judges. It also stalls: 43–77 % of submissions wait for a panel, because the scores bar most families and the family cap then can't be met.
- **v3's score ranks the judges wrongly.** With seven families, the most accurate one (Opus 5.5, 88 % on known answers) scores 71 % and is barred 69 % of the year. Families that are right about half the time score 75–77 %.
- **Challenges and audits correct almost nothing:** 1 or 2 reversals a year. A model asked again gives the same answer, so a second panel repeats the first.
- **A rank kept on known answers, without the family cap, is the best simple rule found:** 6.0 bad fixes per 100 paid, 5.7 % of good fixes rejected, nothing waiting. It is one family judging alone.
- **No variant comes near the assumed 1.1.** The bonds, windows and attacker results of ADR 0004 were sized on that figure.

## 1. What changed in the model
- **Each submission is bound to one of #160's cases,** drawn by the seed: a good fix from the 50 good ones, a bad fix from one of two pools.
  - **"The tests fail them":** the 100 fixes that fail SWE-bench's hidden tests.
  - **"Pass the tests, wrong":** the 78 passing-but-wrong fixes. These are the ones a test run before the judges would not stop.
- **A judge votes as its family's seat did on that case** (`data/judges/verdicts-v2.matrix.json`: pass, fail or invalid per seat, no text). Every error rate and every correlation between seats is the measured one.
- **Every judge of a family gives the same verdict on a case,** and the same judge asked again repeats it. #160 took one verdict per case, so this is an assumption; one row lets a repeated call differ 1 time in 10.
- **Everything else is report v3's score world:** 25 % of honest solvers' fixes are bad, 30 submissions a week, a grown network with four validators per family, a flat service fee.
- **Three switches were added, off by default:** no cap per model family (`FAMILY_CAP`), "every judge must pass" (`PASS_RULE`), and a rank on known answers (`measured.known_answer_rank`).

## 2. v3 as designed, assumed against measured

| World | Bad fixes merged per 100 paid | Bad fixes paid, of those decided | Good fixes rejected | Fixes paid a year | Submissions that waited |
|---|---|---|---|---|---|
| Assumed judges, v3's scores | 1.1 ± 0.1 | 3.4 % ± 0.3 | 0.3 % ± 0.0 | 1,101 ± 68 | 5.5 % ± 5.5 |
| Measured, four families, bad = the tests fail them | 10.0 ± 1.3 | 38.9 % ± 4.8 | 4.2 % ± 0.5 | 229 ± 22 | 76.8 % ± 1.5 |
| Measured, seven families, bad = the tests fail them | 17.8 ± 1.2 | 66.4 % ± 4.0 | 8.6 % ± 1.1 | 391 ± 57 | 64.8 % ± 4.2 |
| Measured, four families, bad = pass the tests, wrong | 11.0 ± 0.5 | 36.5 % ± 1.2 | 5.2 % ± 0.4 | 597 ± 116 | 49.1 % ± 9.0 |
| Measured, seven families, bad = pass the tests, wrong | 14.3 ± 1.0 | 49.4 % ± 3.9 | 6.9 % ± 0.9 | 673 ± 120 | 43.2 % ± 9.2 |

- **Four families** are v3's launch set: Anthropic, OpenAI, Google and one open-weight family, here DeepSeek V3.2.
- **Seven families** are #160's seven main seats, as open registration would allow.
- **Without scores** the network doesn't stall but is worse: 16.8 (four families) and 21.1 (seven) bad fixes per 100 paid.
- **Letting a repeated call differ 1 time in 10** changes little: 11.2 ± 1.4 per 100 paid with four families.

## 3. The score ranks the judges wrongly
v3's score is a family's agreement with final outcomes. Seven families, bad = the tests fail them:

| Family | Bad fixes passed / good fixes failed (measured) | Score on known answers | Score by v3's rule | Barred, share of the year |
|---|---|---|---|---|
| Opus 5.5 | 18 % / 6 % | 88 % | 70.8 % ± 4.8 | 69 % ± 13 |
| GPT-6.1 | 40 % / 30 % | 65 % | 86.0 % ± 2.9 | 14 % ± 10 |
| Gemini 3.1 Pro | 78 % / 2 % | 60 % | 63.5 % ± 2.3 | 92 % ± 2 |
| DeepSeek V3.2 | 81 % / 8 % | 55 % | 68.0 % ± 2.2 | 84 % ± 7 |
| Qwen3 235B | 83 % / 16 % | 50 % | 75.4 % ± 4.8 | 52 % ± 15 |
| Mistral Large 3 | 92 % / 6 % | 51 % | 64.0 % ± 2.2 | 93 % ± 2 |
| Nemotron 3 Super | 70 % / 26 % | 52 % | 77.3 % ± 4.3 | 49 % ± 14 |

- **The outcome a judge is scored against is the panel's own verdict,** unless a challenge reverses it. When most seats pass a bad fix, the seat that fails it is the one marked wrong.
- **Reversals are too rare to correct that:** 1.6 ± 0.5 a year here, while about 70 bad fixes are paid.
- **A family alone on the network scores 100 %,** whatever it does: Opus only, and Opus with GPT-6.1 only, both score 100.0 % ± 0.0.
- **With four families the rank comes out right for Opus** (92.6 %) but GPT-6.1 scores 91.7 % against 65 % on known answers, and the two others are barred, which is what stalls the network.

## 4. What would change it (exploratory)
The "known-answer rank" scores every family on the truth. It is an upper bound: it assumes the network has cases whose answers it knows (reversed verdicts, canaries, #136). Seven families; four families give the same picture (appendix).

**Bad = the tests fail them:**

| Rule | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Submissions that waited |
|---|---|---|---|---|
| **v3 as designed** | 17.8 ± 1.2 | 8.6 % ± 1.1 | 391 ± 57 | 64.8 % ± 4.2 |
| v3's scores, no family cap | 16.1 ± 2.0 | 16.5 % ± 2.4 | 1,107 ± 28 | 1.4 % ± 0.4 |
| Known-answer rank at 70 %, family cap | 5.9 ± 0.7 | 2.7 % ± 0.4 | 185 ± 5 | 81.9 % ± 0.4 |
| Known-answer rank at 70 %, no family cap (Opus alone) | 6.0 ± 0.2 | 5.6 % ± 0.2 | 1,136 ± 10 | 0.1 % ± 0.0 |
| Top two families, no cap, majority | 8.7 ± 0.4 | 12.6 % ± 0.9 | 1,085 ± 14 | 0.0 % |
| Top two families, no cap, every judge must pass | 5.6 ± 0.3 | 30.0 % ± 0.4 | 839 ± 9 | 0.0 % |
| Top three families, family cap, majority | 13.6 ± 0.4 | 5.9 % ± 0.2 | 1,262 ± 12 | 0.0 % |

**Bad = pass the tests, wrong:**

| Rule | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Submissions that waited |
|---|---|---|---|---|
| **v3 as designed** | 14.3 ± 1.0 | 6.9 % ± 0.9 | 673 ± 120 | 43.2 % ± 9.2 |
| v3's scores, no family cap | 13.2 ± 0.9 | 14.4 % ± 1.9 | 1,114 ± 37 | 0.9 % ± 0.4 |
| Known-answer rank at 70 % (three families qualify), family cap | 11.7 ± 0.3 | 5.9 % ± 0.2 | 1,234 ± 12 | 0.0 % |
| Top family only (GPT-6.1), no cap | 8.4 ± 0.3 | 27.4 % ± 0.4 | 842 ± 8 | 3.5 % ± 0.2 |
| Top two families, no cap, majority | 12.2 ± 0.3 | 12.8 % ± 0.9 | 1,128 ± 19 | 0.0 % |
| Top two families, no cap, every judge must pass | 8.1 ± 0.3 | 30.1 % ± 0.4 | 862 ± 9 | 0.0 % |

- **The family cap is what stalls the network** once the rank is right: with one qualifying family, 82 % of submissions wait.
- **Dropping the cap alone doesn't help,** because v3's score still seats the wrong families.
- **The two changes together work,** and the result is the best family judging alone.
- **"Every judge must pass" buys little on the first pool** (5.6 against 6.0) and costs 30 % of good fixes. On the second pool it and "GPT-6.1 alone" are the best rows, at the same cost.
- **Which family is best depends on the kind of bad fix.** On known answers:

| Bad fixes | Opus 5.5 | GPT-6.1 | Gemini 3.1 Pro | DeepSeek V3.2 | Qwen3 235B | Mistral Large 3 | Nemotron 3 Super |
|---|---|---|---|---|---|---|---|
| The tests fail them | 88 % | 65 % | 60 % | 55 % | 50 % | 51 % | 52 % |
| Pass the tests, wrong | 75 % | 75 % | 74 % | 59 % | 51 % | 51 % | 52 % |

  A rank needs known answers of the kind the judges will actually face. If tests run before the judges, that is the second row, where three families are level.

## 5. What this does not show
- **The attackers are not re-run.** H7 asks whether "no attacker gains" still holds on measured inputs. This report covers the honest network only; the 14 open-validator, 6 pricing, 7 proof-level and 8 herding attackers are the next step.
- **The fee is flat,** not the market's, so validators' income is not comparable with report v3.1's.
- **Contenders disputing with evidence is not modelled.** Here a challenge is judged by another panel of the same models. A challenge that carries a failing test would be settled by running it; how much truth that supplies is the main open question for the rank.
- **The known-answer rank is an upper bound.** It doesn't model where the known answers come from, what they cost, or how they could be gamed.
- **228 cases, one verdict each, one benchmark.** Every submission repeats one of them. The mix of 25 % bad fixes is assumed.
- **Judges of a family are identical here.** Real validators differ in prompts, versions and settings.
- **The bad fixes are honest failures,** not written to beat a judge.

## 6. What it means for #236
1. **The rank must be fed by known answers,** not by agreement with the panel. This is the result with the largest effect.
2. **The family cap can't be a hard rule** while one family is this far ahead. As a tie-break among near-equal families it would have applied on the second pool (three families within two points) and not on the first.
3. **The best achievable here is about 6 to 8 bad fixes per 100 paid,** five to seven times the figure the bonds and windows were sized on. ADR 0004's parameters need re-deriving on that, and the attackers re-running.
4. **A strict rule trades bad fixes for good ones at a poor rate** on this data. Whether rejecting 30 % of good fixes is acceptable depends on what a re-submission costs a solver.

## Appendix: the full output

Seeds 1-40; every ± is two standard errors of the mean.

### Outcomes

| World | Bad fixes paid, of bad fixes decided | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Verdicts reversed a year | Submissions that waited |
|---|---|---|---|---|---|---|
| Assumed (report v3's score world: 95 / 90 / 85 / 68 %, independent calls), no scores | 4.5 % ± 0.4 | 1.5 ± 0.2 | 0.9 % ± 0.1 | 1169 ± 10 | 4.2 ± 0.6 | 0.0 % ± 0.0 |
| **Assumed, v3's scores** | 3.4 % ± 0.3 | 1.1 ± 0.1 | 0.3 % ± 0.0 | 1101 ± 68 | 2.2 ± 0.5 | 5.5 % ± 5.5 |
| Measured, bad = fixes the tests fail; four families; no scores | 57.5 % ± 1.2 | 16.8 ± 0.5 | 4.6 % ± 0.3 | 1332 ± 13 | 13.0 ± 1.0 | 0.0 % ± 0.0 |
| Measured, bad = fixes the tests fail; four families; v3's scores | 38.9 % ± 4.8 | 10.0 ± 1.3 | 4.2 % ± 0.5 | 229 ± 22 | 0.8 ± 1.1 | 76.8 % ± 1.5 |
| Measured, bad = fixes the tests fail; four families; v3's scores, a repeated call differs 1 time in 10 | 42.2 % ± 5.1 | 11.2 ± 1.4 | 6.4 % ± 1.1 | 152 ± 10 | 0.4 ± 0.2 | 79.0 % ± 0.8 |
| Measured, bad = fixes the tests fail; seven families; no scores | 75.4 % ± 0.7 | 21.1 ± 0.4 | 5.9 % ± 0.2 | 1386 ± 13 | 12.5 ± 1.1 | 0.0 % ± 0.0 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | 66.4 % ± 4.0 | 17.8 ± 1.2 | 8.6 % ± 1.1 | 391 ± 57 | 1.6 ± 0.5 | 64.8 % ± 4.2 |
| Measured, bad = fixes the tests fail; Opus and GPT-6.1 only; no scores | 18.6 % ± 2.1 | 5.9 ± 0.7 | 7.3 % ± 0.6 | 155 ± 4 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes the tests fail; Opus and GPT-6.1 only; v3's scores | 18.6 % ± 2.1 | 5.9 ± 0.7 | 7.3 % ± 0.6 | 155 ± 4 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes the tests fail; Opus only; no scores | 17.4 % ± 1.6 | 6.0 ± 0.6 | 5.8 % ± 0.5 | 209 ± 5 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes the tests fail; Opus only; v3's scores | 17.4 % ± 1.6 | 6.0 ± 0.6 | 5.8 % ± 0.5 | 209 ± 5 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes that pass the tests and are wrong; four families; no scores | 45.6 % ± 0.9 | 13.8 ± 0.3 | 4.6 % ± 0.2 | 1285 ± 12 | 9.5 ± 1.0 | 0.0 % ± 0.0 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores | 36.5 % ± 1.2 | 11.0 ± 0.5 | 5.2 % ± 0.4 | 597 ± 116 | 2.6 ± 2.3 | 49.1 % ± 9.0 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores, a repeated call differs 1 time in 10 | 37.4 % ± 2.6 | 10.9 ± 0.8 | 6.5 % ± 0.7 | 187 ± 27 | 0.5 ± 0.2 | 76.0 % ± 2.1 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; no scores | 66.5 % ± 0.8 | 19.1 ± 0.4 | 5.8 % ± 0.3 | 1352 ± 13 | 13.1 ± 1.0 | 0.0 % ± 0.0 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | 49.4 % ± 3.9 | 14.3 ± 1.0 | 6.9 % ± 0.9 | 673 ± 120 | 2.0 ± 1.3 | 43.2 % ± 9.2 |
| Measured, bad = fixes that pass the tests and are wrong; Opus and GPT-6.1 only; no scores | 26.0 % ± 1.5 | 8.7 ± 0.6 | 7.4 % ± 0.7 | 160 ± 4 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes that pass the tests and are wrong; Opus and GPT-6.1 only; v3's scores | 26.0 % ± 1.5 | 8.7 ± 0.6 | 7.4 % ± 0.7 | 160 ± 4 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes that pass the tests and are wrong; Opus only; no scores | 44.1 % ± 1.8 | 13.9 ± 0.8 | 5.8 % ± 0.5 | 228 ± 5 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| Measured, bad = fixes that pass the tests and are wrong; Opus only; v3's scores | 44.1 % ± 1.8 | 13.9 ± 0.8 | 5.8 % ± 0.5 | 228 ± 5 | 0.0 ± 0.0 | 81.6 % ± 0.3 |

### Scores, with v3's rule

| World | Family (seat) | Measured: bad passed / good failed | Score on known answers | Score by v3's rule | Barred, share of the year |
|---|---|---|---|---|---|
| Measured, bad = fixes the tests fail; four families; v3's scores | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 92.6 % ± 3.4 | 14 % ± 11 |
| Measured, bad = fixes the tests fail; four families; v3's scores | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 91.7 % ± 2.0 | 5 % ± 7 |
| Measured, bad = fixes the tests fail; four families; v3's scores | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 65.6 % ± 3.7 | 86 % ± 9 |
| Measured, bad = fixes the tests fail; four families; v3's scores | `open-weight` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 64.8 % ± 3.9 | 87 % ± 9 |
| Measured, bad = fixes the tests fail; four families; v3's scores, a repeated call differs 1 time in 10 | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 84.3 % ± 3.9 | 25 % ± 14 |
| Measured, bad = fixes the tests fail; four families; v3's scores, a repeated call differs 1 time in 10 | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 86.0 % ± 3.5 | 12 % ± 10 |
| Measured, bad = fixes the tests fail; four families; v3's scores, a repeated call differs 1 time in 10 | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 66.3 % ± 3.5 | 82 % ± 11 |
| Measured, bad = fixes the tests fail; four families; v3's scores, a repeated call differs 1 time in 10 | `open-weight` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 67.8 % ± 3.9 | 80 % ± 12 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 70.8 % ± 4.8 | 69 % ± 13 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 86.0 % ± 2.9 | 14 % ± 10 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `google` (Gemini 3.1 Pro) | 78 % / 2 % | 60 % | 63.5 % ± 2.3 | 92 % ± 2 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `deepseek` (DeepSeek V3.2) | 81 % / 8 % | 55 % | 68.0 % ± 2.2 | 84 % ± 7 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `qwen` (Qwen3 235B) | 83 % / 16 % | 50 % | 75.4 % ± 4.8 | 52 % ± 15 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 64.0 % ± 2.2 | 93 % ± 2 |
| Measured, bad = fixes the tests fail; seven families; v3's scores | `nvidia` (Nemotron 3 Super) | 70 % / 26 % | 52 % | 77.3 % ± 4.3 | 49 % ± 14 |
| Measured, bad = fixes the tests fail; Opus and GPT-6.1 only; v3's scores | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 100.0 % ± 0.0 | 0 % ± 0 |
| Measured, bad = fixes the tests fail; Opus and GPT-6.1 only; v3's scores | `openai` (GPT-6.1) | 40 % / 30 % | 65 % | 100.0 % ± 0.0 | 0 % ± 0 |
| Measured, bad = fixes the tests fail; Opus only; v3's scores | `anthropic` (Opus 5.5) | 18 % / 6 % | 88 % | 100.0 % ± 0.0 | 0 % ± 0 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 91.7 % ± 2.8 | 6 % ± 7 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 89.0 % ± 1.2 | 2 % ± 4 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 74.0 % ± 2.7 | 53 % ± 12 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores | `open-weight` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 64.1 % ± 2.1 | 95 % ± 2 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores, a repeated call differs 1 time in 10 | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 80.2 % ± 4.1 | 36 % ± 15 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores, a repeated call differs 1 time in 10 | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 87.0 % ± 2.3 | 7 % ± 8 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores, a repeated call differs 1 time in 10 | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 72.6 % ± 3.6 | 67 % ± 14 |
| Measured, bad = fixes that pass the tests and are wrong; four families; v3's scores, a repeated call differs 1 time in 10 | `open-weight` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 68.6 % ± 3.7 | 82 % ± 11 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 85.3 % ± 4.8 | 26 % ± 13 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 85.9 % ± 2.1 | 8 % ± 8 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `google` (Gemini 3.1 Pro) | 50 % / 2 % | 74 % | 70.4 % ± 2.9 | 58 % ± 13 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `deepseek` (DeepSeek V3.2) | 74 % / 8 % | 59 % | 69.8 % ± 2.8 | 80 % ± 9 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `qwen` (Qwen3 235B) | 82 % / 16 % | 51 % | 72.2 % ± 3.6 | 73 % ± 11 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `mistral` (Mistral Large 3) | 92 % / 6 % | 51 % | 60.4 % ± 3.0 | 95 % ± 1 |
| Measured, bad = fixes that pass the tests and are wrong; seven families; v3's scores | `nvidia` (Nemotron 3 Super) | 69 % / 26 % | 52 % | 67.7 % ± 2.9 | 83 % ± 7 |
| Measured, bad = fixes that pass the tests and are wrong; Opus and GPT-6.1 only; v3's scores | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 100.0 % ± 0.0 | 0 % ± 0 |
| Measured, bad = fixes that pass the tests and are wrong; Opus and GPT-6.1 only; v3's scores | `openai` (GPT-6.1) | 19 % / 30 % | 75 % | 100.0 % ± 0.0 | 0 % ± 0 |
| Measured, bad = fixes that pass the tests and are wrong; Opus only; v3's scores | `anthropic` (Opus 5.5) | 45 % / 6 % | 75 % | 100.0 % ± 0.0 | 0 % ± 0 |

### What would change it (exploratory)

| World | Bad fixes paid, of bad fixes decided | Bad fixes merged per 100 paid | Good fixes rejected | Fixes paid a year | Verdicts reversed a year | Submissions that waited |
|---|---|---|---|---|---|---|
| bad = fixes the tests fail; four families: **v3 as designed** (scores on agreement, family cap, majority) | 38.9 % ± 4.8 | 10.0 ± 1.3 | 4.2 % ± 0.5 | 229 ± 22 | 0.8 ± 1.1 | 76.8 % ± 1.5 |
| bad = fixes the tests fail; four families: v3's scores, no family cap | 27.4 % ± 2.6 | 9.7 ± 1.1 | 13.5 % ± 2.5 | 1083 ± 28 | 2.1 ± 1.3 | 0.7 % ± 0.4 |
| bad = fixes the tests fail; four families: known-answer rank at 70 %, family cap | 23.0 % ± 2.2 | 5.7 ± 0.7 | 3.4 % ± 0.4 | 193 ± 4 | 0.0 ± 0.0 | 81.6 % ± 0.3 |
| bad = fixes the tests fail; four families: known-answer rank at 70 %, no family cap | 18.5 % ± 0.7 | 6.0 ± 0.2 | 5.7 % ± 0.2 | 1143 ± 10 | 0.0 ± 0.0 | 0.1 % ± 0.1 |
| bad = fixes the tests fail; four families: top family only, no family cap | 18.5 % ± 0.7 | 6.0 ± 0.2 | 5.7 % ± 0.2 | 1143 ± 10 | 0.0 ± 0.0 | 0.1 % ± 0.1 |
| bad = fixes the tests fail; four families: top two families, no family cap, majority | 26.1 % ± 1.2 | 9.2 ± 0.5 | 14.1 % ± 1.1 | 1084 ± 14 | 11.3 ± 2.4 | 0.0 % ± 0.0 |
| bad = fixes the tests fail; four families: top two families, no family cap, every judge must pass | 13.0 % ± 0.5 | 5.8 ± 0.3 | 30.2 % ± 0.4 | 848 ± 9 | 9.9 ± 2.3 | 0.0 % ± 0.0 |
| bad = fixes the tests fail; four families: top three families, family cap, majority | 44.3 % ± 0.7 | 13.6 ± 0.4 | 5.9 % ± 0.2 | 1264 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |
| bad = fixes the tests fail; seven families: **v3 as designed** (scores on agreement, family cap, majority) | 66.4 % ± 4.0 | 17.8 ± 1.2 | 8.6 % ± 1.1 | 391 ± 57 | 1.6 ± 0.5 | 64.8 % ± 4.2 |
| bad = fixes the tests fail; seven families: v3's scores, no family cap | 48.6 % ± 6.4 | 16.1 ± 2.0 | 16.5 % ± 2.4 | 1107 ± 28 | 3.1 ± 1.6 | 1.4 % ± 0.4 |
| bad = fixes the tests fail; seven families: known-answer rank at 70 %, family cap | 27.1 % ± 2.7 | 5.9 ± 0.7 | 2.7 % ± 0.4 | 185 ± 5 | 0.0 ± 0.0 | 81.9 % ± 0.4 |
| bad = fixes the tests fail; seven families: known-answer rank at 70 %, no family cap | 18.8 % ± 0.7 | 6.0 ± 0.2 | 5.6 % ± 0.2 | 1136 ± 10 | 0.0 ± 0.0 | 0.1 % ± 0.0 |
| bad = fixes the tests fail; seven families: top family only, no family cap | 18.8 % ± 0.7 | 6.0 ± 0.2 | 5.6 % ± 0.2 | 1136 ± 10 | 0.0 ± 0.0 | 0.1 % ± 0.0 |
| bad = fixes the tests fail; seven families: top two families, no family cap, majority | 25.1 % ± 1.0 | 8.7 ± 0.4 | 12.6 % ± 0.9 | 1085 ± 14 | 4.3 ± 1.9 | 0.0 % ± 0.0 |
| bad = fixes the tests fail; seven families: top two families, no family cap, every judge must pass | 12.6 % ± 0.5 | 5.6 ± 0.3 | 30.0 % ± 0.4 | 839 ± 9 | 3.1 ± 1.7 | 0.0 % ± 0.0 |
| bad = fixes the tests fail; seven families: top three families, family cap, majority | 44.4 % ± 0.7 | 13.6 ± 0.4 | 5.9 % ± 0.2 | 1262 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; four families: **v3 as designed** (scores on agreement, family cap, majority) | 36.5 % ± 1.2 | 11.0 ± 0.5 | 5.2 % ± 0.4 | 597 ± 116 | 2.6 ± 2.3 | 49.1 % ± 9.0 |
| bad = fixes that pass the tests and are wrong; four families: v3's scores, no family cap | 32.8 % ± 2.1 | 11.3 ± 0.5 | 15.1 % ± 2.0 | 1091 ± 38 | 7.4 ± 1.8 | 0.8 % ± 0.4 |
| bad = fixes that pass the tests and are wrong; four families: known-answer rank at 70 %, family cap | 37.2 % ± 0.8 | 11.7 ± 0.3 | 5.9 % ± 0.2 | 1236 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; four families: known-answer rank at 70 %, no family cap | 38.4 % ± 0.8 | 12.2 ± 0.3 | 7.7 % ± 0.5 | 1221 ± 14 | 9.2 ± 1.0 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; four families: top family only, no family cap | 19.8 % ± 0.7 | 8.3 ± 0.3 | 28.1 % ± 0.4 | 854 ± 9 | 0.0 ± 0.0 | 3.1 % ± 0.4 |
| bad = fixes that pass the tests and are wrong; four families: top two families, no family cap, majority | 35.4 % ± 1.5 | 12.0 ± 0.4 | 14.2 % ± 1.1 | 1120 ± 22 | 12.3 ± 2.4 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; four families: top two families, no family cap, every judge must pass | 18.9 % ± 0.8 | 8.3 ± 0.3 | 30.3 % ± 0.4 | 870 ± 10 | 9.1 ± 2.6 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; four families: top three families, family cap, majority | 37.2 % ± 0.8 | 11.7 ± 0.3 | 5.9 % ± 0.2 | 1236 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; seven families: **v3 as designed** (scores on agreement, family cap, majority) | 49.4 % ± 3.9 | 14.3 ± 1.0 | 6.9 % ± 0.9 | 673 ± 120 | 2.0 ± 1.3 | 43.2 % ± 9.2 |
| bad = fixes that pass the tests and are wrong; seven families: v3's scores, no family cap | 39.5 % ± 3.2 | 13.2 ± 0.9 | 14.4 % ± 1.9 | 1114 ± 37 | 4.9 ± 1.2 | 0.9 % ± 0.4 |
| bad = fixes that pass the tests and are wrong; seven families: known-answer rank at 70 %, family cap | 37.3 % ± 0.8 | 11.7 ± 0.3 | 5.9 % ± 0.2 | 1234 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; seven families: known-answer rank at 70 %, no family cap | 38.9 % ± 0.8 | 12.3 ± 0.3 | 7.2 % ± 0.4 | 1225 ± 14 | 8.3 ± 1.2 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; seven families: top family only, no family cap | 20.5 % ± 0.8 | 8.4 ± 0.3 | 27.4 % ± 0.4 | 842 ± 8 | 0.0 ± 0.0 | 3.5 % ± 0.2 |
| bad = fixes that pass the tests and are wrong; seven families: top two families, no family cap, majority | 36.7 % ± 1.1 | 12.2 ± 0.3 | 12.8 % ± 0.9 | 1128 ± 19 | 4.8 ± 1.9 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; seven families: top two families, no family cap, every judge must pass | 18.7 % ± 0.7 | 8.1 ± 0.3 | 30.1 % ± 0.4 | 862 ± 9 | 3.0 ± 2.1 | 0.0 % ± 0.0 |
| bad = fixes that pass the tests and are wrong; seven families: top three families, family cap, majority | 37.3 % ± 0.8 | 11.7 ± 0.3 | 5.9 % ± 0.2 | 1234 ± 12 | 0.0 ± 0.0 | 0.0 % ± 0.0 |

### The rank on known answers

| Bad fixes | Opus 5.5 | GPT-6.1 | Gemini 3.1 Pro | DeepSeek V3.2 | Qwen3 235B | Mistral Large 3 | Nemotron 3 Super |
|---|---|---|---|---|---|---|---|
| the tests fail them | 88 % | 65 % | 60 % | 55 % | 50 % | 51 % | 52 % |
| pass the tests, wrong | 75 % | 75 % | 74 % | 59 % | 51 % | 51 % | 52 % |
