# Proposal

## Why

With AI consensus deciding deliveries (#43) and the contributor paying for its checks (#49), the simulated mechanism passes every criterion (checking v5). The largest remaining cost is **good work wrongly rejected:**
- at the assumed accuracy per model (0.75–0.85), consensus rejects about a quarter of good fixes;
- the accuracy sweep shows it falling to 12 % at +0.05 and 6 % at +0.1, with honest solvers' earnings rising from +4 to +20 and +31.

Today, any model that passes the shadow exam can judge, and every counted verdict earns the same fee. So an operator gains most by running the cheapest model that qualifies.

The owner's direction (2026-10-25, proof-of-fix#47): "the AI accuracy penalty should come down, controlled by paying for good-quality models; AI oracles should point to reputable models; honest solvers with good architecture and coding skills should win the job."

## What Changes

- **Reputable models, proven per verdict** (amended at the owner's review: "a declaration is human-dependent; these are AI oracles"):
  - every verdict carries proof of the model that produced it: a TEE attestation for open-weight models, or a zkTLS proof of the provider's endpoint for API models;
  - only models on a published list count, and a model is listed only while its measured accuracy is at or above a published bar;
  - an unproven or unlisted verdict is discarded and costs bond;
  - an evaluator whose record is far worse than its proven model's is suspended, as a backstop.
- **Verdict fees by accuracy tier:**
  - an evaluator's verdict fee scales with its own measured accuracy: its Brier score over its latest verdicts, on a published schedule;
  - the check deposit covers the top tier.
- **Seats weighted by quality:** the first jury is drawn from the qualified evaluators with probability weighted by score, instead of uniformly from a flat top 10. Seats stay limited to one per operator and per model family.
- **Simulation:**
  - providers offer models at several tiers, each with its own accuracy and cost per verdict;
  - operators run the model that pays them best;
  - criteria: under tiered fees, running a more accurate model pays more, net of its cost, and good fixes are rejected less often than in checking v5;
  - flat fees are kept as the comparison.

**Out of scope:** the real-data measurement itself (budget); the simulation assumes the models' accuracies.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `checking`: "The AI jury" (seats weighted by score; evaluators declare a model); new requirements "Reputable models" and "Verdict fees by accuracy tier".
- `incentive-simulation`: new requirement "Model quality: scenarios and criteria".

**Actors and attacks:**
- **Affected:** AI evaluators and their operators (choice of model, pay); solvers (deposits rise with the top tier, fewer good fixes rejected).
- **Covered:**
  - an operator declaring a reputable model but running a cheap one, caught by its own Brier score;
  - an operator gaming its tier by abstaining on hard cases (a verdict without evidence is discarded, and scoring counts every revealed verdict).

## Impact

- **Code:**
  - `pof/params.py`: the list's bar, the fee schedule, weighted draws;
  - `pof/checking.py`: declared models, eligibility, tiered fees, the weighted draw;
  - `pof/market.py`: the deposit at the top tier;
  - `pof/sim/`: models by provider and tier, operators' choice, the cheat, criteria;
  - tests.
- **Data:** `reports/acceptance-checking-v6.{json,md}`.
