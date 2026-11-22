# Spec Delta

## REMOVED Requirements

### Requirement: Acceptance with pledged stakes
**Reason**: Its capital target measured pledges against no pledges, and acceptance v3 showed the capital throttle is a stake-size problem, not a pledge one. The capital target moves to "Capital criterion", against the fixed-stake rules.
**Migration**: The safety part is kept unchanged in "Acceptance with pledges".

## ADDED Requirements

### Requirement: Acceptance with pledges
The acceptance criteria SHALL hold with pledged stakes available to every actor, whenever the published pledge cap is above zero.

#### Scenario: Attacks lose money with pledges
- **WHEN** the spam, splitting, griefing, sponsorship-abuse and pledge-stacking scenarios run with pledges available to every actor
- **THEN** each kind of author earns a negative pooled mean per defective contribution (sponsors' losses and forfeited pledges included), and every other acceptance criterion still passes

### Requirement: Capital criterion
In the replay of real history, the mechanism SHALL have at least a third fewer unaffordable submissions than the same seeds under the fixed-stake rules (no index, no reward cap), as a mean over seeds within two standard errors.

#### Scenario: The indexed stake eases the capital throttle
- **WHEN** the replay runs on the same seeds with the proposed parameters and with the fixed-stake rules
- **THEN** the report gives unaffordable submissions for both, and the proposed parameters have at least a third fewer

#### Scenario: Target missed
- **WHEN** the proposed parameters don't reach a third fewer
- **THEN** the criterion fails with both numbers, like any failed criterion

### Requirement: Actors for the indexed stake
The simulation SHALL provide an **index gamer**. It floods a release with small sound contributions to push the reward per unit of weight down, then submits defective contributions at the lower stake.

#### Scenario: Gaming the index costs the gamer
- **WHEN** the index gamer floods and then submits defective work
- **THEN** the report shows the stakes it paid before and after the flood, and its defective contributions earn a negative pooled mean
