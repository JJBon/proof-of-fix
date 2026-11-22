# Proposal

## Why

Market v4 (`reports/acceptance-market-v4.md`, proof-of-fix#40) passes every criterion at every hunting elasticity, so the money rules are stable enough to build on. The checking they rely on isn't designed yet. The simulation models it as **fixed odds**:
- the gate catches a defect with `checks_catch_bps`;
- a reviewer finds one with `review_detect_bps`;
- panels vote with an error rate.

Nothing says **who** runs the checks, how checkers **agree**, or how they're **held to account**. That's what an oracle would have to report (proof-of-fix#44), so it comes first. Ticket: proof-of-fix#43, under the #15 brief ("the AI jury", "decentralizing the checking", stage 1).

## What Changes

- **Signed re-runs of the checks:**
  - a delivery's deterministic checks (build, tests, the bounty's hidden tests, mutation tests) are re-run by a published number of validators, drawn like reviewers, from one reproducible build;
  - each commits a sealed digest of its result, then reveals it;
  - the result a quorum reproduces counts, and a validator whose result differs loses a published share of its bond.

  This is the validation pattern of a Bittensor subnet, without a token.
- **Planted cases:**
  - a published share of check jobs are cases with a known answer, which validators can't tell apart from real ones;
  - a wrong answer costs bond and score.

  This catches lazy validators, and it scores evaluators on the truth.
- **An AI jury at delivery,** for what the tests can't decide (does the fix solve the issue, or game the tests):
  - 3 AI evaluators drawn at random from the published top by score, one seat per operator and per model family;
  - sealed verdicts, each with a probability and cited evidence;
  - 2 of 3 to accept, all 3 to fail a delivery, and anything else escalates to a validator panel.
- **Evaluators scored on the truth, not on agreement:** a proper scoring rule (Brier) against planted answers and revealed outcomes, with newcomers in shadow mode until they qualify.
- **Oracle fees, paid by the bounty** (owner, 2026-10-25): re-runners and AI evaluators are oracles.
  - Every check run on a delivery is paid a published fee from that delivery's bounty: each re-run that matches the quorum, the hidden tests on the system's runner, and each counted verdict.
  - A bounty must hold the fees for one full attempt's checks (the oracle reserve), and its price cap leaves room for them.
- **Simulation:**
  - checking modelled by actors instead of fixed odds;
  - new threats: lazy validators, herding evaluators, an operator registering copies of one model, solvers crafting fixes against a known judge, correlated model errors, and bug planters;
  - checking acceptance run v1.

**Out of scope:**
- real model calls (the real-data measurement needs the owner's OK and a budget);
- the oracle and architecture comparison (#44);
- tokens, chains and wallets.

## Capabilities

### New Capabilities
- `checking`: signed re-runs, planted cases, the AI jury, and evaluator scoring.

### Modified Capabilities
- `bounty-market`: "Delivery" (a delivery passes when the re-runs and the jury accept it).
- `bounty-market`: new requirement "Oracle fees" (the bounty pays its checks and holds the oracle reserve).
- `incentive-simulation`: "Acceptance criteria for the market" (pledges may also pay oracle fees).
- `incentive-simulation`: new requirements "Checking scenarios" and "Acceptance criteria for the checking layer".

**Actors and attacks:**
- **Affected:** validators (re-runs, planted cases), AI evaluators and their operators (new), solvers (a delivery now also faces the jury).
- **Covered:**
  - lazy validators;
  - herding;
  - copies of one model under several operators;
  - fixes crafted against a known judge;
  - correlated errors;
  - bug planters with a partner who challenges.

## Impact

- **Code:**
  - `pof/checking.py` (new): re-runs, planted cases, the jury, scoring;
  - `pof/market.py`: delivery through the re-runs and the jury;
  - `pof/payouts.py`: units of work;
  - `pof/params.py`;
  - `pof/sim/`: evaluator actors, the error model, scenarios and criteria;
  - tests.
- **Data:** `reports/acceptance-checking-v1.{json,md}`.
