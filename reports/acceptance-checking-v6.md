# Checking acceptance run v6: oracle quality, proof-of-fix#47 (2026-10-25)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-checking-v6.json` (verdicts on 100 seeds, sweeps on 20; about 57 minutes). The baseline is checking v5 ([`acceptance-checking-v5.md`](acceptance-checking-v5.md)), the same market with the contributor paying for its checks.

**What's new** (the owner's decisions on #47):
- **Only reputable models judge:** each provider's highest generally available model, from at least three providers, each above the accuracy bar (0.85).
- **Every verdict carries a proof of the model it came from** (a TEE attestation or zkTLS), not a declaration. A verdict without a proof, or from a different model, doesn't count and is penalized.
- **Juries come from the leaderboard, top to bottom:**
  - the first jury seats the top models of three providers;
  - a split's second jury of 7 keeps going down the board, with up to 3 seats per provider and one per operator;
  - a seeded pick chooses between operators' copies of the same model, as a fair tie-break, not a security feature.
- **Verdict fees by each evaluator's accuracy tier:** 0.6, 0.45 or 0.35 at Brier ≤ 0.08, 0.12 or 0.20. The check deposit covers the top tier (6.6).
- **The simulation's catalogue** (an assumption until the real-data measurement): providers A, B and C at 0.92, 0.90 and 0.88 accuracy. Seven operators each run one evaluator per provider.
- **A model cheat** registers a listed model but runs a small one.

## Result

| Hunting elasticity (100 seeds) | Checking v5 | **Checking v6** |
|---|---|---|
| **0.5** (default) | ✅ every criterion passes | ✅ **every criterion passes** |
| 0 | ✅ every criterion passes | ✅ every criterion passes |
| 1 | ✅ every criterion passes | ✅ every criterion passes |

**Good fixes wrongly rejected fall from 25 % to 11 %,** and **honest solvers earn +20.2 ± 1.3** against +4.5 in v5. Better juries are worth more to honest solvers than any pricing rule so far.

## v5 vs v6 (default, 100 seeds)

| Criterion | v5 | **v6** |
|---|---|---|
| **Good fixes wrongly rejected** | 25.1 % | ✅ **11.3 %** |
| **Honest solvers earn** | +4.5 ± 1.4 | ✅ **+20.2 ± 1.3** |
| **Quality pays** (provider A's evaluators over C's, per verdict) | (new) | ✅ **+0.018 ± 0.004** |
| **Model cheat** (registers a top model, runs a small one) | (new) | ✅ **−11.3 ± 0.3** |
| Splits sent to the second jury | 45 % | 31 % |
| Bad deliveries caught before beta | 99.0 % | ✅ 99.7 % |
| Funders' cost per paid bounty | 58.7 | 60.0 |
| Mean price | 67.5 | 69.9 |
| Bounties paid / unsolved per run | 23.7 / 65.2 | 25.5 / 62.7 |
| Honest evaluators / validators (gross / net of effort) | +1.30 / +13.0 / +10.7 | ✅ +1.04 / +14.3 / +11.9 |
| Lazy / herder / copy operator / crafter / bug planter / half-fixer / split farmer | −8 / −1.8 / −303 / −348 / −302 / −234 / −322 | ✅ −8 / −1.3 / −329 / −342 / −322 / −268 / −338 |
| Hidden bidder (a checker's sock identity) / bluffer / lowballer | +1.4 ± 11.8 / −7 / −47 | ✅ +8.1 ± 9.8 / −26 / −40 (none gains) |
| Rings of 2 / 3 / 4 / 6 | none significant | ✅ none significant (−32 ± 19 / +15 ± 24 / +15 ± 27 / −7 ± 31) |
| Spam / no-shows / reputation farming / owner defecting | −254 / −422 / −269 / +1.3 ± 1.1 | ✅ −215 / −419 / −248 / **0.0** |

**Comparisons on the same seeds:**
- **Tiered fees against a flat fee:** good fixes rejected −0.2 ± 0.2 points, honest solvers −0.6 ± 0.7. Neither is significant: among frontier models the tiers mostly redistribute pay toward the best-measured evaluators ("quality pays").
- **The solver paying against the bounty paying:** prices +7.0 ± 1.2, about 1 fewer bounty paid (−1.2 ± 0.4), funders' cost −3 ± 3.
- **Fresh rounds after a failure against a queue:** honest solvers +22 ± 7, prices −7 ± 1.5.
- **Attested CI against validators:** honest solvers +3 ± 3, funders' cost −3 ± 2.5, none significant.

**Honest evaluators earn less per run than in v5** (+1.04 against +1.30): fewer splits go to the second jury (31 % against 45 %), so there are fewer paid verdicts. They still earn significantly more than their cost.

## A fix during the run: the owner's panels get their own random stream

The first v6 run failed one criterion, **"the owner can't gain by defecting": +2.98 ± 1.21.** It wasn't a gain from defecting:
- the self-interested owner's attempts all failed: about 0.1 declines per run went through, and its split change was refused on 100 of 100 seeds;
- each failed attempt drew a panel from the world's shared random stream, so the honest and defecting runs followed different market paths. The difference showed up as noise in the owner's release share (+30 on some seeds, −18 on others).

**The fix, as for CI's `ci_rng` in checking v5:** in the market world, the owner's decline and split-change panels draw from their own stream. Both runs then share one market path, and the defecting owner gains **exactly 0 on all 100 seeds**. No parameter or rule changed. The other scenarios' runs are identical to the first run's, and the legacy world keeps one stream so its reports still reproduce. A test checks that a failed defection leaves the market's path unchanged (`tests/test_market_sim.py`).

## Sweeps (20 seeds)

Most rows pass. At 20 seeds, a few criteria near the line flag in single rows ("proven solvers lock less", "quality pays", "no ring gains"). The rows that teach something:

| Sweep | Finding |
|---|---|
| **Model accuracy −0.05** | good fixes rejected **61 %**, honest solvers −44: the mechanism depends on the models being about this good |
| Model accuracy +0.05 | every criterion passes; good fixes rejected 8 %, honest solvers +25 |
| Model accuracy +0.1 | good fixes rejected 4 %, honest solvers +31; evaluators earn too little, since nearly nothing is split |
| **Jury accepting with 2 of 3** | good fixes rejected 4 %, honest solvers +33, but "quality pays" flags. The owner chose consensus |
| Second jury accepting with 6 or 7 | good fixes rejected 25 % / 32 %, and honest solvers stop earning: 5 of 7 is right |
| A first jury of 1 or 5 | a single model, or a five-model consensus, fails several criteria: 3 is right |
| Market fee 10 % / 30 % | both pass; honest solvers +21 / +12 |
| Evaluator cost 0.5 per verdict | above the top fee: evaluators lose, as expected |
| Runners per delivery 1, planted share 0 or 5 % | "checking attacks lose" flags: weaker checks |
| Enclave compromise 5 % | "no ring gains" flags |

## Still open

1. **Model accuracy:** the real-data measurement (budget) replaces the assumed 0.92 / 0.90 / 0.88. At 0.05 lower, the mechanism fails. On-chain, the leaderboard measures it live (owner, #15).
2. **Rings:** none is significant, but the spreads are wide (±19–31). A ring-only run on more seeds would bound them.
3. **#46** (amendments to tests and scope), and the go-live items on #15.
