# Spec Delta

## ADDED Requirements

### Requirement: Two tiers of judges
A fix SHALL be judged by the issue tier: 3 judges drawn with the verdict's seed from the 7 registered judges, passing with 2. An ADR or an escalated fix SHALL be judged by the constitution tier: all 7, passing with 5. The counts and thresholds SHALL be fixed for a version and SHALL NOT change by ADR.

#### Scenario: Two of three
- **WHEN** 2 of the 3 drawn judges pass a fix and nobody escalates it
- **THEN** the fix passes, and the dissenting verdict is published with the others

#### Scenario: Four of seven
- **WHEN** 4 of the 7 judges pass an escalated fix
- **THEN** it fails

#### Scenario: The draw is reproducible
- **WHEN** the issue tier's draw is recomputed from the recorded seed and the registered judges
- **THEN** it yields the same 3 judges

### Requirement: One model family and one operator per judge
Each of the 7 registered judges SHALL run a different model family and be run by a different, independent operator. A model family or an operator SHALL hold at most one seat in a version, and each verdict SHALL name the model it was given by.

#### Scenario: A second seat for a family
- **WHEN** an operator registers a judge running a model family that already holds a seat
- **THEN** the registration is refused for that version

#### Scenario: A verdict names its model
- **WHEN** a judge signs a verdict
- **THEN** the verdict records the model and version it ran, and the public log shows it

### Requirement: The owner holds at most one seat and recuses
The owner SHALL operate at most one judge, disclosed. That judge SHALL NOT judge a bounty or ADR in which the owner is a party (funder, reporter, solver or author); the next judge in the draw SHALL take its seat, and on the constitution tier the threshold SHALL stay 5 of the 6 who sit.

#### Scenario: The owner solves a bounty
- **WHEN** the owner's account wins a bounty's race and the owner's judge is drawn for it
- **THEN** the owner's judge is replaced by the next judge in the draw, and the record shows the recusal

#### Scenario: The owner writes an ADR
- **WHEN** the owner submits an ADR
- **THEN** the 6 other judges judge it, and it needs 5 of them

## MODIFIED Requirements

### Requirement: The project's constitution
In `race` and `claim`, every delivery SHALL pass the project's constitution (`CONSTITUTION.md` at the canonical head): its invariants and its quality gates, such as coverage of the changed code and a mutation score, measured by the attested runners; published limits on diff size and performance; and the judges' pass or fail. A delivery that fails any gate SHALL fail, whatever the others say, and one that touches a protected path SHALL be escalated.

#### Scenario: Padded tests
- **WHEN** a delivery adds tests that raise coverage but catch none of the planted mutations
- **THEN** it fails the mutation gate

#### Scenario: Gates are versioned
- **WHEN** the constitution changes
- **THEN** bounties registered before the change are judged by the version they were registered under

#### Scenario: A weakened test
- **WHEN** a delivery edits a test that guards an invariant so that it no longer fails on the bug
- **THEN** the change touches a protected path, so it is escalated to the constitution tier, and without an accepted ADR it fails
