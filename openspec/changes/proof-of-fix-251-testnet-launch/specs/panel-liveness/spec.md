## ADDED Requirements

### Requirement: A panel that can't complete is released
When a counted panel has a silent seat and no eligible validator is left to replace it, the round SHALL end at its reveal deadline plus `STUCK_GRACE`. The silent seats SHALL be slashed as for any silence, and the submission SHALL return to waiting (design L19).

#### Scenario: Replacements exhausted
- **WHEN** a drawn judge stays silent and every eligible validator has already been drawn or is silent
- **THEN** at the reveal deadline plus `STUCK_GRACE` the round ends, the silent seats are slashed, and the submission is waiting with a redraw scheduled

#### Scenario: Redrawn when validators join
- **WHEN** a submission is waiting after a released round and a new validator becomes eligible before `RETRY_DELAY` has passed
- **THEN** the submission is drawn again with a fresh seed

### Requirement: A bounty that can't be judged is refunded
After `MAX_REDRAWS` released rounds, or at the bounty's deadline, the bounty SHALL be refunded to its funders. The solver's claim SHALL be released with no reputation loss and no slash.

#### Scenario: Too many released rounds
- **WHEN** a submission's round has been released `MAX_REDRAWS` times
- **THEN** the bounty is refunded to its funders, and the solver's reputation and stake are unchanged

### Requirement: No submission is ever stuck
Every submission SHALL be, at every moment, in exactly one of these states: drawn with a live deadline, waiting with a scheduled redraw, final (paid or rejected), or refunded.

#### Scenario: Any sequence of silences and joins
- **WHEN** any sequence of draws, silences, joins and leaves is applied
- **THEN** no submission is in a state outside that list
