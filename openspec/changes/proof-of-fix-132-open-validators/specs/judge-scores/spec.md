# Spec Delta

## Purpose
How each model family's quality is measured in v3, and what the measurement changes:
- a public score per family, from its judges' agreement with final outcomes on counted verdicts, balanced over passed and failed outcomes;
- a minimum score to be drawn, and recovery measured on fresh blocks of shadow verdicts;
- a neutral start for new families;
- a service fee scaled by the score, normalised so the network's mean factor is 1 ×.

Votes stay one judge, one vote. The score changes pay and eligibility, never a verdict's count.

## ADDED Requirements

### Requirement: Each model family has a public score
Each model family SHALL have a score on-chain, over its judges' last counted verdicts (the published number): the mean of their agreement with the final outcome on passed outcomes and on failed outcomes, or the agreement on the one kind present. Shadow verdicts SHALL NOT enter it. The final outcome SHALL be the verdict after its challenge window, or the upheld challenge's verdict when one reversed it. Anyone SHALL be able to read and recompute the score.

#### Scenario: A judge that always votes pass
- **WHEN** a family's judges vote pass on every draw, and 78 % of the outcomes in its window are passes
- **THEN** they agree on every passed outcome and on no failed one, so its score is 50 %, not 78 %

#### Scenario: Only one kind of outcome
- **WHEN** every outcome in a family's window is a pass
- **THEN** its score is its agreement on those passes

#### Scenario: A reversal counts as the truth
- **WHEN** a panel passes a fix, a challenge reverses it, and one of the panel's judges had voted fail
- **THEN** that judge's family is scored as agreeing, and the families that voted pass are scored as disagreeing

#### Scenario: Recomputing a score
- **WHEN** anyone recomputes a family's score from the recorded verdicts and outcomes
- **THEN** they get the score the contract holds

#### Scenario: Shadow verdicts don't lift a score
- **WHEN** a family's validators give many shadow verdicts that agree with outcomes
- **THEN** its counted score doesn't change; only its counted verdicts move it

### Requirement: A family below the minimum score isn't drawn
A model family whose score, over at least the published minimum number of counted verdicts, is below the published minimum score SHALL NOT be drawn for counted panels. Its validators SHALL be drawn only as shadow judges until the family recovers.

#### Scenario: A weak model
- **WHEN** a family's score falls below the minimum after the minimum number of counted verdicts
- **THEN** its validators are drawn only as shadow judges

### Requirement: A barred family recovers by its shadow verdicts alone
A barred family's shadow verdicts, from its barring on, SHALL be taken in consecutive blocks of the published size (100), each judged once, when complete. The family SHALL be drawn again when a block, scored as the public score is, reaches the minimum score plus the published margin (10 points). Its counted window SHALL then restart, and until it holds the minimum number of new counted verdicts it SHALL be paid the minimum score factor.

#### Scenario: A model that gets better
- **WHEN** a barred family's model improves and the next complete block of its validators' shadow verdicts scores 85 %
- **THEN** it is drawn again for counted panels, paid at the minimum factor until it has 50 new counted verdicts, and then at its new score's factor

#### Scenario: A weak model's lucky streak
- **WHEN** a barred family still right 68 % of the time gives 50 shadow verdicts in a row that score 74 %, inside a block of 100 that scores 71 %
- **THEN** it stays barred: only a complete block at 80 % or more recovers it, and each block is judged once

### Requirement: A new family starts neutral
A model family with fewer than the published minimum number of counted verdicts, that has never been barred, SHALL be treated as having the neutral score: drawn normally, and paid the neutral factor of 1 ×.

#### Scenario: A newly released open model
- **WHEN** validators register with a model family that has no verdicts yet
- **THEN** they're drawn normally and paid 1 × the market service fee until the family has the minimum number of verdicts

### Requirement: The service fee is scaled by the family's score
A counted judge's service fee SHALL be the market service fee times its family's factor: a raw factor linear in the score, from the published minimum (0.5 ×) at the minimum score to the published maximum (2 ×) at 100 %, divided each pricing period by the mean raw factor over the previous period's counted seats, and kept within both bounds. Metered usage SHALL always be repaid in full.

#### Scenario: A better model earns more
- **WHEN** two judges on the same panel use families whose factors are 1.5 × and 0.8 × after normalisation
- **THEN** each gets its metered usage back in full, and service fees of 1.5 × and 0.8 × the market fee

#### Scenario: Scores don't raise the price of a check
- **WHEN** every family scores above the minimum and the network's counted seats are spread across them
- **THEN** the factors over a period's counted seats average 1 ×, so solvers pay the market service fee per judge on average

### Requirement: Scores never weight a vote
In v3, every counted judge's verdict SHALL count as one vote, whatever its family's score. Weighting votes by score SHALL need a new version.

#### Scenario: A high-score family in the minority
- **WHEN** the one judge of a high-score family votes pass and the two others vote fail
- **THEN** the fix fails, as with any 1 of 3
