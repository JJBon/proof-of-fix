# Spec Delta

## ADDED Requirements

### Requirement: Attested CI runs
A delivery's checks (build, tests, the bounty's failing and hidden tests, mutation tests) SHALL be run by a published number of attested runners: MCP test-runner services in TEEs, registered by operators with a bond, drawn with a seed from different operators and hardware vendors, never a bidder. Each SHALL commit a sealed digest of its attested result, then reveal it. All SHALL agree; a split SHALL be run again by fresh runners, and a result off theirs SHALL lose a published share.

#### Scenario: All agree
- **WHEN** both runners reveal the same attested result
- **THEN** that result counts, and each runner is paid its run fee by the bounty

#### Scenario: A split
- **WHEN** one runner reveals that the tests pass and the other that they fail
- **THEN** fresh runners from other operators and vendors run them, their result counts, and the runner that disagreed with it loses the published share

#### Scenario: Results can't be copied
- **WHEN** a runner commits before the others reveal
- **THEN** it can't see their results, because only sealed digests exist until the reveal

#### Scenario: A bidder can't check
- **WHEN** runners or a jury are drawn for a delivery
- **THEN** no account that bid for that bounty's job, nor any account linked to one, is among them

### Requirement: Hidden tests inside the enclaves
A bounty's hidden tests SHALL run only inside the attested runners' enclaves, encrypted to them, and never be shown to solvers, operators or evaluators. A delivery SHALL pass only if they pass. A delivered attempt that fails SHALL retire the set it faced, and the bounty's next attempt SHALL face a fresh set.

#### Scenario: Gaming the public test
- **WHEN** a fix makes the bounty's public failing test pass but fails a hidden test
- **THEN** the delivery fails, and the hidden set is retired

### Requirement: Appeal of failed runs
A solver SHALL be able to appeal failed runs once, for a published fee. Fresh runners, none of the first and no bidder, SHALL run the same checks. If they pass, the result SHALL stand as passed, the first runners that reported a failure SHALL lose the dissent share of their bonds, and the fee SHALL return; otherwise the fee SHALL go to insurance.

#### Scenario: The runners are wrong
- **WHEN** the runners report a failure on checks that pass, and the solver appeals
- **THEN** the fresh runs pass, the delivery goes on to the jury, the first runners lose the dissent share, and the fee returns

#### Scenario: The failure stands
- **WHEN** the fresh runs fail too
- **THEN** the delivery fails, and the fee goes to insurance

### Requirement: Planted cases
A published share of check and jury jobs SHALL be planted cases: a delivery with a known answer, prepared by the system from past fixes and known defects, that runners and evaluators can't tell apart from real ones. A wrong answer to a planted case SHALL cost a published share of the bond and count against the score. Planted cases SHALL be recorded, revealed once settled, and their checks paid the oracle fees from insurance.

#### Scenario: A runner forging results
- **WHEN** a runner reports "pass" on a planted case whose hidden tests fail
- **THEN** it loses the published share of its own bond, and its error is recorded with the case

#### Scenario: Revealed after settling
- **WHEN** a planted case is settled
- **THEN** the ledger records that it was planted and what its answer was, so anyone can check the scoring

### Requirement: The AI jury
A delivery that passes its checks SHALL go to a jury of a published number of AI evaluators, drawn at random with a seed fixed at delivery from the published top by evaluator score. A jury SHALL have at most one evaluator per operator and per model family. An evaluator SHALL be registered with a bond, its operator and its model family, and the parties and accounts linked to them SHALL be excluded.

#### Scenario: One seat per family
- **WHEN** a jury is drawn and two eligible evaluators share an operator or a model family
- **THEN** at most one of them sits on it

#### Scenario: Selection reproducible
- **WHEN** the draw is recomputed from the recorded seed and the eligible set at delivery
- **THEN** it yields the same evaluators

### Requirement: Jury verdicts
Each evaluator SHALL commit a sealed verdict, solves the issue or not, with a probability and the evidence it cites (test runs, diff locations), then reveal it. A verdict without evidence SHALL be discarded. The jury SHALL accept a delivery only by consensus, every seat accepting, and reject it only unanimously. Any other outcome, including too few verdicts, SHALL go to the second jury. No person SHALL decide a delivery.

#### Scenario: Accepted
- **WHEN** all three evaluators reveal that the fix solves the issue, each citing evidence
- **THEN** the delivery becomes the winning contribution

#### Scenario: Rejected unanimously
- **WHEN** all three evaluators reveal that the fix games the tests, each citing evidence
- **THEN** the delivery fails as a failed delivery does

#### Scenario: Split
- **WHEN** two evaluators accept and one rejects, or a verdict is discarded for lack of evidence
- **THEN** the second jury decides

### Requirement: The second jury
A split SHALL go to a second, larger jury of a published size, drawn with a seed from the qualified evaluators not on the first and no party, at most one per operator and a published number per model family. It SHALL accept the delivery with a published supermajority, and otherwise reject it.

#### Scenario: Supermajority
- **WHEN** five of the second jury's seven evaluators accept
- **THEN** the delivery becomes the winning contribution

#### Scenario: Short of it
- **WHEN** four of seven accept
- **THEN** the delivery is rejected

### Requirement: Evidence sealed until the bounty settles
The evidence a jury's verdicts cite SHALL stay sealed until the bounty is paid or closed unsolved, and SHALL then be published with the verdicts. Before that, only each jury's outcome and count SHALL be recorded.

#### Scenario: A failed attempt's jury
- **WHEN** a jury rejects a delivery and the bounty reopens
- **THEN** the next bidders see the published attempt, but not what the evaluators cited against it

### Requirement: Evaluators scored on the truth
An evaluator's score SHALL come from its verdicts' probabilities, scored by a published proper scoring rule (Brier) on the truth: a planted case's answer at once, a real delivery's fate once known (accepted without an upheld challenge, or slashed or clawed back), and appeal results. Agreement with other evaluators SHALL never count. An evaluator SHALL judge in shadow mode, scored but not counted, until it has a published number of scored verdicts above a published score.

#### Scenario: Scored on the outcome
- **WHEN** an evaluator accepted a fix that is later slashed
- **THEN** its score falls by the scoring rule for the probability it gave, whatever the other evaluators said

#### Scenario: Not scored on a rejection
- **WHEN** a delivery is rejected by its juries
- **THEN** its verdicts count as work but aren't scored: its truth is never revealed, and scoring against the rejection would be scoring on agreement

#### Scenario: Shadow mode
- **WHEN** a newly registered evaluator is drawn
- **THEN** it judges alongside a full jury, its verdict is scored, and the jury's outcome doesn't depend on it
