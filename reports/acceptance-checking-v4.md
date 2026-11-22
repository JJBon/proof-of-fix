# Checking acceptance run v4: AI oracles for CI and judging, paid by the bounty, proof-of-fix#43 (2026-10-25)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-checking-v4.json` (verdicts on 100 seeds, sweeps on 20; about 57 minutes). Market v4 ([`acceptance-market-v4.md`](acceptance-market-v4.md)) is the baseline; v1–v3 (`acceptance-checking-v{1,2,3}.json`) are the intermediate runs recorded in the design.

**What's new since market v4:** checking is no longer fixed odds. Both checks are oracles, and each delivery's bounty pays for them.
- **CI: attested runners.** MCP test runners in TEEs, two per delivery, from different operators and hardware vendors. They run the public tests and, inside their enclaves, the hidden tests. They must agree; a split is run again by fresh runners. If even those can't agree, the result is inconclusive and the bond returns.
- **Judging: AI consensus.** Three evaluators, one per operator and model family, must all accept. A split goes to a second AI jury of seven, which accepts with five. A split rejection returns the bond. No person decides a delivery.
- **Evaluators scored on the truth:** Brier score on planted cases and revealed fates, never on agreement. Rejected deliveries go unscored.
- **Oracle fees:**
  - a run fee (0.3) per runner whose result stands, and a verdict fee (0.5) per counted verdict, from the bounty;
  - a bounty must hold more than the oracle reserve (5.6: one attempt's checks).
- **Failed attempts are published, and a fresh round opens,** its reserve capped at the failed price.
- **A "not solved" challenge,** whose case joins the bounty's public definition.
- **Seven attackers** against their honest twins on the same seeds.

## Result

| Hunting elasticity (100 seeds) | Verdict |
|---|---|
| **0.5** (default) | ❌ one criterion: **honest solvers earn +1.5 ± 1.4**, not significantly more than their cost |
| 0 | ❌ the same, and only that (+1.2) |
| 1 | ❌ the same, and only that (+1.6) |

**Every other criterion passes at every elasticity:** attacks, collusion, checkers' pay, detection, and every market v4 criterion.

## The one failure: AI consensus at today's assumed model accuracy

Consensus catches **98.7 %** of bad deliveries before beta, against 25 % for the old gate alone. But at the assumed accuracy per model (0.75–0.85) it also rejects **24.8 %** of good fixes. The solver loses only time and tokens (the bond comes back on a split), but the wasted work leaves honest solvers at break-even. The accuracy sweep (20 seeds) shows that the cause is accuracy, not the mechanism:

| Accuracy added to every model family | −0.05 | 0 (assumed) | +0.05 | **+0.1 (about 0.9)** |
|---|---|---|---|---|
| Good fixes rejected | 43 % | 21 % | 14 % | **5.5 %** |
| Bad fixes caught | 98 % | 98 % | 99 % | 99 % |
| Honest solvers | −29 | +5 | +19 | **+23** |

**Two ways to pass:**
- **Better models:** consensus passes once each model is about 0.9 accurate. That's the go-live condition (design note 17), and #47 makes it a rule: reputable models only, and fees tiered by measured accuracy.
- **A majority first jury:** 2 of 3 instead of all 3. In the sweep it passes **every criterion** today: 94.6 % of bad fixes caught, 9 % of good fixes rejected, honest solvers +21.

The owner chose consensus, so this run keeps it and reports the trade.

## The checkers and the attacks (default, 100 seeds)

| Criterion | Result |
|---|---|
| Bad deliveries caught before beta | ✅ **98.7 %** (+73 points against fixed odds) |
| Honest AI evaluators / attested runners / validators (reviews, challenges) | ✅ +1.33 ± 0.03 / +0.12 / +10.4 |
| Runner forging results | ✅ −7.2 ± 1.0 |
| Herding evaluator | ✅ −1.8 ± 0.3; under agreement scoring it would gain **+3.7** |
| Copy operator (4 copies of one model) / crafting solver / bug planter / half-fixer | ✅ −284 / −325 / −270 / −250 |
| Hidden bidder (a checker with a second, bidding identity) | ✅ doesn't gain: +8.5 ± 13.6 |
| Half-fixer without the "not solved" challenge | −240: the hidden tests and juries catch it first; the challenge is the backstop |
| Rings of 2 / 3 / 4 / 6 | ✅ −36 / −5 / +37 / −19, none significant |
| Bluffing / lowballing / no-shows / spam / floods / reputation farming / owner defecting | ✅ 0 / −73 / −422 / −273 / −494 / −282 / −0.3 |
| Crowd-out, normal / 50 % junk detection | ✅ 93 % / 90 % |
| Proven solvers lock less bond | ✅ −2.3 ± 0.7 |

## Comparisons (100 seeds)

- **Attested runners against CI by validators:** defects caught are the same. Honest solvers −3.2 ± 3.9, funders' cost +16 ± 16: neither difference is significant.
- **Fresh rounds against the queue:**
  - fixes come 2.2 days sooner and prices are 10 lower;
  - honest solvers earn **+49 more**: a solver whose good fix was wrongly rejected keeps its bond and can bid again on its own work;
  - funders' cost per paid bounty is +18 ± 15, not significant;
  - 0.8 fewer pledged bounties are paid.

## Sweeps (20 seeds)

"Honest solvers earn" fails in most rows, as at the default. The rows that teach something:

| Sweep | Finding |
|---|---|
| Enclave compromise 0 / 0.5 / 5 % | no material effect (98.5–98.7 % caught): two vendors per delivery and planted cases contain it |
| Attested runners per delivery 1 / 2 / 3 | all work; 2 is the default for vendor diversity |
| Evaluator cost per verdict 0.1 / 0.3 / 0.5 | evaluators +3.6 / +1.3 / −1.1: the verdict fee (0.5) must stay above the model cost |
| Second jury threshold 5 / 6 / 7 of 7 | good fixes rejected 21 / 32 / 41 %: 5 stays |
| First jury size 1 / 3 / 5, by consensus | 1 catches only 84 % of bad fixes; 5 rejects 51 % of good ones |
| Planted share 0 % | the forging runner stops losing: planted cases are what catch it |
| Model correlation within a family 0 / 0.5 / 0.8 | small effect: one seat per family absorbs it |

## Still open

1. **Model accuracy:** the real-data measurement (budget needed), then #47 (reputable models, fees tiered by accuracy).
2. **Collusion and identity:** rings pass at the defaults, but sit near the line under changes unrelated to them. The lever is ring detection and identity, not price (to be ticketed when the owner decides).
3. **Amendments to tests and scope between rounds:** #46.
4. **Oracle and architecture desk study:** #44. DeMCP (MCP servers in TEEs) and the draft verifiable-MCP extension are the reference points for attested runners.
