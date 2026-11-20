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
Every submission SHALL be, at every moment, in exactly one of these states: drawn with a live deadline; waiting with a scheduled redraw; counted with its window running, or frozen by one challenge that is drawn with a live deadline or waiting with a scheduled redraw, and that ends by `CHALLENGE_DEADLINE` or at its panel's release; final (paid or rejected); or refunded (design L19, restated by L25).

#### Scenario: Any sequence of silences and joins
- **WHEN** any sequence of draws, silences, joins and leaves is applied
- **THEN** no submission is in a state outside that list

#### Scenario: Any sequence with challenges
- **WHEN** any sequence of draws, challenges, test disputes, silences, pauses, joins and leaves is applied, on 7 or 15 validators
- **THEN** no submission is in a state outside that list, and every challenge ends

### Requirement: A challenge has a deadline
A challenge, a test dispute and an auditor's challenge SHALL each have `CHALLENGE_DEADLINE` from its opening (design L25). Past it, a challenge with no panel SHALL lapse, and one whose panel is drawn SHALL lapse only when that panel is released. The constructor SHALL refuse a `CHALLENGE_DEADLINE` below `MAX_REDRAWS` × `RETRY_DELAY` plus the seal and reveal windows and `STUCK_GRACE`.

#### Scenario: No panel by the deadline
- **WHEN** a challenge's panel can't be drawn before `CHALLENGE_DEADLINE`
- **THEN** it lapses: the verdict stands, its window resumes, the original judges can unbond, and the challenger gets its stake and cover back

#### Scenario: A panel completes after the deadline
- **WHEN** a challenge panel drawn before the deadline completes after it
- **THEN** it is counted as any challenge panel

### Requirement: A lapsed challenge leaves the verdict and returns the stake
A lapse SHALL leave the verdict as it was, resume its window where it froze, close the challenge for the original judges, and return the challenger's stake and cover whole, with no reward.

#### Scenario: A test dispute lapses
- **WHEN** a test dispute of a pass lapses
- **THEN** the pass stands, the disputer gets its stake and cover back, and no reward is paid

### Requirement: A stuck challenge panel is released
A challenge panel with a seat its replacements couldn't fill SHALL end at its reveal deadline plus `STUCK_GRACE`, its silent seats slashed as for any silence and its other seats closed unslashed. Before `CHALLENGE_DEADLINE` the challenge SHALL return to waiting with a fresh seed; after it, the challenge SHALL lapse.

#### Scenario: A silent judge on a challenge panel with no replacement
- **WHEN** a challenge panel's judge stays silent and no eligible validator is left to replace it
- **THEN** at the reveal deadline plus `STUCK_GRACE` the panel ends, the silent seat is slashed, and the challenge waits for a redraw or lapses

### Requirement: A waiting challenge is retried on a clock
A challenge that waits for a panel SHALL be drawn again with a fresh seed block and snapshot once the registry changes or `RETRY_DELAY` after it began waiting, whichever comes first.

#### Scenario: A validator un-pauses
- **WHEN** a challenge waits because a validator was paused, and the validator un-pauses with no other registry change
- **THEN** the challenge is drawn again at its `RETRY_DELAY` with a fresh seed
