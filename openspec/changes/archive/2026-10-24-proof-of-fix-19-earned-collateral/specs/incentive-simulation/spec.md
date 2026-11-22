# Spec Delta

## ADDED Requirements

### Requirement: Acceptance with pledged stakes
The acceptance criteria SHALL hold with pledged stakes available to every actor. Pledges SHALL also cut unaffordable submissions in the replay of real history by at least a third against the same seeds without pledges (mean over seeds, within two standard errors).

#### Scenario: Attacks lose money with pledges
- **WHEN** the spam, splitting, griefing, sponsorship-abuse and pledge-stacking scenarios run with pledges available to every actor
- **THEN** each kind of author earns a negative pooled mean per defective contribution (sponsors' losses and forfeited pledges included), and every other acceptance criterion still passes

#### Scenario: Pledges ease the capital throttle
- **WHEN** the replay scenario runs on the same seeds with and without pledged stakes
- **THEN** the report gives unaffordable submissions for both, and the run with pledges has at least a third fewer, within two standard errors

#### Scenario: Target missed
- **WHEN** the run with pledges doesn't reach a third fewer unaffordable submissions
- **THEN** the criterion fails with both numbers, and the report names it like any failed criterion

### Requirement: Actors for pledges
The simulation SHALL provide:
- **Pledging contributor:** every contributor with accepted work, attackers included, pledges the unpaid reward of its own accepted contributions when its balance falls short of a stake, within the limits.
- **Pledge stacker:** builds up accepted work, then submits as many defective contributions as its pledges allow, all backed by the same unpaid rewards.

#### Scenario: A short balance is covered by a pledge
- **WHEN** a contributor with accepted work in clawback can't cover a stake from its balance alone, but can within the pledge limits
- **THEN** it submits with a pledge instead of being counted as unaffordable

#### Scenario: Stacking costs the stacker
- **WHEN** the pledge stacker's defective contributions are slashed, or its backing contributions are clawed back
- **THEN** the forfeits come out of its balance and its pledged rewards. The report shows its return including those losses, and the pledges it made and lost.
