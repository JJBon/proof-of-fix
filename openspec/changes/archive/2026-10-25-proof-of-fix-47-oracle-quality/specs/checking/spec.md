# Spec Delta

## MODIFIED Requirements

### Requirement: The AI jury
A delivery that passes its checks SHALL go to a jury of AI evaluators taken from the leaderboard, top to bottom: the best-measured listed models seat first, one per provider. Each seat SHALL go to one operator running that model, drawn with a seed fixed at delivery. A jury SHALL have at most one evaluator per operator. An evaluator SHALL register with a bond, its operator and the model it means to run, and parties and linked accounts SHALL be excluded.

#### Scenario: One seat per family
- **WHEN** a jury is drawn and two eligible evaluators share an operator or a model family
- **THEN** at most one of them sits on it

#### Scenario: Selection reproducible
- **WHEN** the draw is recomputed from the recorded seed and the eligible set at delivery
- **THEN** it yields the same evaluators

#### Scenario: Top of the leaderboard first
- **WHEN** four providers' models are listed and a first jury of three is drawn
- **THEN** it seats the three best-measured models, and the fourth only judges when one of them can't sit

#### Scenario: A fair tie-break between copies
- **WHEN** several operators run the same top model
- **THEN** which of them takes the seat is drawn with the delivery's seed, spreading the paid work between them

## ADDED Requirements

### Requirement: Reputable models, proven per verdict
Every verdict SHALL carry proof of its model: a TEE attestation of a listed open-weight model, or a zkTLS proof of a listed provider's endpoint. A verdict without valid proof of a listed model SHALL be discarded and cost a published share of the bond. The list SHALL hold only each provider's highest generally available model, from at least three providers, each only while its measured accuracy (historical set, planted cases, revealed fates) is at or above a published bar.

#### Scenario: Top models only
- **WHEN** a provider offers several models, and its highest one is gated to an access program
- **THEN** only its highest generally available model can be listed, and a first jury seats three different providers' models

#### Scenario: A model below the bar
- **WHEN** a model's measured accuracy falls below the published bar
- **THEN** it leaves the list, and verdicts proven to come from it are discarded until it returns

#### Scenario: Claiming a frontier model, running a cheap one
- **WHEN** an evaluator registered for a listed model sends verdicts whose proof shows an unlisted model, or no valid proof
- **THEN** each such verdict is discarded and costs the published share of its bond

#### Scenario: The record as a backstop
- **WHEN** an evaluator's own score is far worse than its proven model's measured accuracy implies
- **THEN** it is suspended from seats until its record recovers in shadow

### Requirement: Verdict fees by accuracy tier
An evaluator's verdict fee SHALL follow a published schedule by its own measured accuracy tier, from its Brier score over its latest verdicts: better tiers SHALL earn more per counted verdict. The check deposit SHALL cover the top tier's fees for one full attempt.

#### Scenario: A better record pays more
- **WHEN** two evaluators' verdicts are counted on the same delivery, one in a better tier
- **THEN** the better one is paid the higher fee from the solver's deposit

#### Scenario: The deposit covers the top tier
- **WHEN** a solver bids
- **THEN** its check deposit is enough to pay the runs and both juries at the top tier's fee
