# Spec Delta

## ADDED Requirements

### Requirement: No solver's deposit
In v3, a submission SHALL NOT post any deposit that it can lose on rejection (owner, 2026-11-19; ADR 0007). A rejected fix SHALL cost its solver only what it paid to be judged, and SHALL add nothing to the issue's bounty. A test dispute's reward SHALL come from the bounty, never from the solver. No count of active solvers SHALL switch a deposit on.

#### Scenario: A bad fix rejected
- **WHEN** a panel rejects a fix to an $80 bounty and the solver doesn't appeal
- **THEN** the solver loses only what it paid to be judged, and the bounty stays $80 for the next solver

#### Scenario: A good fix paid
- **WHEN** a fix passes and its window ends with no dispute upheld
- **THEN** the solver is paid the bounty, and no deposit is involved

#### Scenario: Judges don't earn by rejecting
- **WHEN** a panel rejects a fix
- **THEN** none of its judges receives anything from the solver beyond the published fees for judging
