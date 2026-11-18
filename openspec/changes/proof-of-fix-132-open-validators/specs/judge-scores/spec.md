# Spec Delta

## Purpose
How each model family's quality is measured in v3, and what the measurement changes:
- a public score per family, from its judges' agreement with final outcomes (after disputes and appeals) on counted verdicts, balanced over passed and failed outcomes;
- a minimum score to be drawn, and recovery measured on fresh blocks of shadow verdicts;
- seats for the best-scoring families, and a contender's start for new ones;
- a service fee scaled by the score, normalised so the network's mean factor is 1 ×.

Votes stay one judge, one vote. The score changes pay and eligibility, never a verdict's count.

## ADDED Requirements

### Requirement: Each model family has a public score
Each model family SHALL have a score on-chain, over its judges' last counted verdicts (the published number): the mean of their agreement with the final outcome on passed outcomes and on failed outcomes, or the agreement on the one kind present. Shadow verdicts SHALL NOT enter it. The final outcome SHALL be as "What a final outcome is" defines it. Anyone SHALL be able to read and recompute the score.

#### Scenario: A judge that always votes pass
- **WHEN** a family's judges vote pass on every draw, and 78 % of the outcomes in its window are passes
- **THEN** they agree on every passed outcome and on no failed one, so its score is 50 %, not 78 %

#### Scenario: Only one kind of outcome
- **WHEN** every outcome in a family's window is a pass
- **THEN** its score is its agreement on those passes

#### Scenario: A reversal counts as the truth
- **WHEN** a panel passes a fix, a challenge reverses it, and one of the panel's judges had voted fail
- **THEN** that judge's family is scored as agreeing, and the families that voted pass are scored as disagreeing

#### Scenario: A failing test counts as the truth
- **WHEN** a panel passes a fix and a dispute backed by a failing test is upheld
- **THEN** every judge that voted pass is scored as disagreeing, with no slash

#### Scenario: An upheld appeal counts as the truth
- **WHEN** a panel rejects a fix, its appeal passes it, and the pass becomes final
- **THEN** the judges that voted to reject are scored as disagreeing

#### Scenario: Recomputing a score
- **WHEN** anyone recomputes a family's score from the recorded verdicts and outcomes
- **THEN** they get the score the contract holds

#### Scenario: Shadow verdicts don't lift a score
- **WHEN** a family's validators give many shadow verdicts that agree with outcomes
- **THEN** its counted score doesn't change; only its counted verdicts move it

### Requirement: What a final outcome is
A passing verdict SHALL be final when its challenge window ends with no challenge or dispute upheld. A rejection SHALL be final when its appeal period ends with no appeal, or when the seated families' appeal panel doesn't pass the fix. When a challenge, a dispute backed by a failing test, or an appeal reverses a verdict, the reversed verdict SHALL be the final outcome.

#### Scenario: A pass nobody disputes
- **WHEN** a fix passes and its window ends with no dispute
- **THEN** the pass is the final outcome, and its judges are scored against it

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

### Requirement: Seats go to the best-scoring families
Counted panels SHALL be drawn only from seated families: those at or above the minimum score and within the published margin (5 points) of the best-scoring family. Every other family SHALL be a contender: its validators shadow-judge, and may dispute passes and sponsor appeals. They SHALL NOT sit on appeal panels.

#### Scenario: One family far ahead
- **WHEN** the best family scores 88 % and the next 65 %
- **THEN** only the best family is drawn for counted panels, and the others shadow-judge

#### Scenario: Three families level
- **WHEN** three families score 75 %, 75 % and 74 %
- **THEN** all three are seated, and the family cap applies to their panels

### Requirement: A new family starts as a contender
A model family with no seat SHALL earn one by its shadow verdicts alone, on a complete block of the published size, scored as the public score is and meeting the seat rule. At genesis the genesis validator's family SHALL be seated. Verdicts on past submissions SHALL NOT count.

#### Scenario: A newly released model
- **WHEN** validators register with a model family that has no verdicts yet
- **THEN** they shadow-judge live submissions, and the family is seated when a complete block of its shadow verdicts meets the seat rule

#### Scenario: Replaying old cases
- **WHEN** a contender publishes its verdicts on submissions that are already final
- **THEN** they don't count toward its seat

### Requirement: Known-answer issues score every family (proposed)
At the published rate, an issue whose outcome is already known SHALL be judged beside a live submission by one validator of every registered family, seated or not, drawn by the seed. Each verdict SHALL be recorded against the known outcome. The checks SHALL be paid from the fees as an audit's are, and no solver SHALL be charged. No account SHALL choose the issue or its answer.

#### Scenario: A contender on a known-answer issue
- **WHEN** a known-answer issue is drawn while one family is seated and six are contenders
- **THEN** one validator of each of the seven judges it, and each family's verdict is recorded as right or wrong

### Requirement: The seat rule reads known-answer scores once there are enough (proposed)
Once a family holds the published minimum of verdicts on known-answer issues (50), the score the seat rule reads for it SHALL be its balanced agreement with the known outcomes over its last published window of them (200). Until then the rule SHALL read its score from final outcomes, or its shadow block. A contender whose known-answer score meets the seat rule SHALL be seated.

#### Scenario: A better newcomer
- **WHEN** the seated family scores 65 % on known-answer issues and a contender 88 %, each over at least 50 of them
- **THEN** the contender is seated and the first family becomes a contender, whatever their agreement with the network's own outcomes

#### Scenario: Too few known answers yet
- **WHEN** a family holds 20 verdicts on known-answer issues
- **THEN** the seat rule still reads its score from final outcomes or its shadow block

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
