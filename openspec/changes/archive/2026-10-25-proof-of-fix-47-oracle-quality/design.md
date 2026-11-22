# Design

## Context

- **Evaluators** register with an operator and a model family, qualify in shadow mode (20 scored verdicts at Brier ≤ 0.2), and are drawn uniformly from the top 10 by score: one seat per operator and per family.
- **Verdict fee:** every counted verdict earns 0.5 from the solver's check deposit (#49).
- **Accuracy:** the simulation gives each family an accuracy (0.75–0.85) and every verdict the same cost (0.3).
- **Checking v5:** consensus rejects 25 % of good fixes at those accuracies, against 6 % at +0.1.

## Goals / Non-Goals

**Goals:**
- Running a better model pays its operator more.
- Weak models can't sit.
- Fewer good fixes are rejected.
- Every earlier criterion holds.

**Non-Goals:**
- The real-data measurement: its accuracy numbers will replace the assumptions here.
- Choosing the actual model list.

## Decisions

### D1. A model catalogue (simulation assumption)
Each provider (the families A–E) offers three models, with accuracy relative to the provider's base:

| Tier | Accuracy | Cost per verdict |
|---|---|---|
| Frontier | base + 0.07 | 0.8 |
| Standard | base | 0.3 |
| Small | base − 0.08 | 0.08 |

The bases are today's family accuracies: 0.85, 0.85, 0.80, 0.80 and 0.75. Models from one provider share its error correlation, the family term of the copula.

### D2. The reputable list
- **The bar:** `model_bar` = 0.85 in the simulation; the real-data measurement sets the real one, with 0.9 as the target.
- **Who's on it:** a model is listed while its measured accuracy (the system's historical set, then planted cases and revealed fates) is at or above the bar.
- **At the defaults:**
  - listed: the frontier models of providers A–D and the standard models of A and B;
  - not listed: provider E's models (its frontier is 0.82) and every small model.
- **Enough seats:** four families leave room for a first jury of 3, and a second of 7 at two per family.

### D3. Fees by accuracy tier
- **The tiers:** an evaluator's tier comes from its own Brier score over its latest 50 verdicts. Expected Brier for a calibrated model of accuracy a is a(1 − a).

  | Tier | Brier | Verdict fee |
  |---|---|---|
  | 1 | ≤ 0.08 | 1.2 |
  | 2 | ≤ 0.12 | 0.8 |
  | 3 | ≤ 0.20 (qualified) | 0.5 |

- **Which model pays best** (fee minus cost per verdict):
  - a frontier 0.92 (Brier 0.074, tier 1) earns 0.4 a verdict;
  - a standard 0.85 (0.128, tier 3) earns 0.2;
  - a frontier 0.87 (0.113, tier 2) breaks even (0.0).

  The schedule is swept: the criterion is that better models pay more, not these exact numbers.
- **The deposit (#49)** now covers the top tier: 2 runs × 0.3 + 10 verdicts × 1.2 = 12.6, against 5.6. It's refunded unused, but solvers must hold it.

### D4. Seats weighted by score
- **The draw:** the first jury is drawn with weight (0.2 − Brier) + 0.01 among qualified evaluators on listed models, keeping one seat per operator and family. The second jury is drawn the same way.
- *Alternative:* keep the flat top 10. Rejected: it doesn't reward a better record within the top.

### D5. Declaring one model and running another
- **The check:** an evaluator whose own Brier exceeds its declared model's expected Brier by more than `cheat_margin` = 0.05, after 20 scored verdicts, is suspended: no seats, and its bond is held until its record recovers in shadow.
- **The simulated cheat:** declares provider A's frontier (expected Brier 0.074) but runs A's small model (0.77 accuracy, Brier 0.177). It should be suspended within its first 20 to 30 verdicts.

### D6. Operators' choice and the comparison
- **The choice:** each honest operator runs, per provider, the listed model with the highest expected fee minus cost at the published schedule. That's a fixed choice at setup, which a rational operator would make.
- **The comparison:** the same seeds with a flat fee (0.5), where operators run the cheapest listed model.
- **Reported:**
  - operators' net return per verdict by tier;
  - the share of good fixes rejected;
  - honest solvers' returns;
  - funders' cost per paid bounty.

## Risks / Trade-offs

- **Higher check deposits** (12.6) shut out solvers with little capital. The deposit is refunded unused, but must be held. The run reports bids refused as unaffordable.
- **Expected checks rise** (better models cost more per verdict), and solvers price them in. Fewer wrongly rejected good fixes should more than pay for it: v5's sweep gives honest solvers +20 at +0.05 accuracy.
- **Fewer families qualify,** so the jury's diversity shrinks: provider E is off the list at the defaults. The correlation sweep shows what that costs.
- **Calibration gaming:** an evaluator reporting overconfident probabilities to reach a better tier is scored down by Brier itself. That's the property of a proper scoring rule.

## Amendment at the owner's review (2026-10-25): proof, not declaration

The merged spec had evaluators *declare* their model. The owner pointed out that a declaration is a claim someone makes, while these are meant to be AI oracles. So each verdict now carries **proof of the model that produced it**:
- **Open-weight models** run in a TEE whose attestation covers the model weights' hash and the judging prompt.
- **API models** come with a zkTLS proof (TLSNotary, Reclaim, Opacity) that the answer came from the provider's endpoint, naming the model.

**The rule:**
- A verdict counts only with valid proof of a listed model.
- Otherwise it's discarded and costs `unproven_penalty_bps` of the evaluator's bond.
- The record check (D5) stays as a backstop.

**In the simulation,** a proof is the model id the verdict really came from. A forged proof would need to break the TEE or the TLS proof, and is out of scope: the proofs are assumed sound, as attested runners are.

**The cheat (D5):** it registers for a listed frontier model but runs a small one. Its verdicts carry the small model's proof, so they're discarded and penalized at once; it doesn't take 20 verdicts for its record to catch up.

## Amendment at the owner's review (2026-10-25): top models only, three providers

The owner's decision: "three frontier models on the league: Opus 5.5, or the highest tier if not gated. Throw top models as juries."
- **The list:** only each provider's **highest generally available model**, from at least three providers.
  - For Anthropic that's Claude Opus 5.5, or Claude Fable 5.1, its most capable generally available model. Claude Mythos 5.1 is gated to an access program, so it's excluded.
  - The real-data measurement chooses between them on accuracy against cost: Fable 5.1 lists at $10 / $50 per million tokens, against Opus 5.5's $4 / $20.
- **Each listed model must still meet the accuracy bar.** D1's standard and small models are no longer listable. The catalogue keeps them only so the cheat (D5) has a small model to run.
- **Seats:**
  - the first jury seats three different providers' models (one per family, as before);
  - the second jury of 7 allows up to 3 seats per provider (`second_jury_per_family` = 3), since there are 3 providers.
- **Fees by accuracy tier (D3) still apply.** Among frontier models they reward each evaluator's own record and calibration, and the better-measured provider's evaluators earn more per verdict.
- **The simulation's frontier models** (an assumption until the measurement): providers A, B and C at 0.92, 0.90 and 0.88 accuracy, at 0.3 per verdict. Fees are rescaled to that cost: 0.6 / 0.45 / 0.35 at Brier ≤ 0.08 / 0.12 / 0.20. The check deposit becomes 2 runs × 0.3 + 10 × 0.6 = 6.6.
- **Operators:** seven, each running one evaluator per provider (21 evaluators), so both juries can be seated.

## Amendment at the owner's review (2026-10-25): the leaderboard, top to bottom

The owner's decision: "just take the top 3 of the leaderboard, or a higher number than 3; look from top to bottom." It replaces D4's weighted random draw.
- **The leaderboard** ranks listed models by published measured accuracy, with ties broken by their evaluators' best record.
- **The first jury** seats the top models of three different providers.
- **A split's second jury** keeps going down the board: up to 3 seats per provider, at most one per operator.
- **What's still random is only which operator's copy of a model takes the seat** (seeded at delivery). Some rule has to pick among identical copies; a seeded pick is a fair tie-break that spreads the paid work.
  - **It isn't a security feature.** The owner's point: an oracle's integrity is the oracle network's responsibility, not this product's.
  - With a zkTLS proof that a verdict came straight from the provider's API, there's no middleman whose verdict could be bought; the operator only pays for the call.
- **Fees by accuracy tier (D3)** still reward each operator's own record.

## Fix during the acceptance run (task 3.2): the owner's panels get their own random stream

The first v6 run failed one criterion, "the owner can't gain by defecting": +2.98 ± 1.21 (v4 −0.3, v5 +1.3).
- **It wasn't a gain from defecting.** The self-interested owner's attempts all failed: about 0.1 declines per run went through, and its split change was refused on 100 of 100 seeds.
- **The cause was the comparison.** Each failed attempt drew a panel from the world's shared random stream. The honest and defecting runs then followed different market paths, and the difference showed up as noise in the owner's release share (+30 on some seeds, −18 on others).
- **The fix, as for CI's `ci_rng`:** in the market world, the owner's decline and split-change panels draw from their own stream (`owner_rng`), so the two runs share one market path. The defecting owner's gain is then exactly 0 on all 100 seeds. The legacy world keeps one stream, so its reports still reproduce.
- No parameter or rule changed.
