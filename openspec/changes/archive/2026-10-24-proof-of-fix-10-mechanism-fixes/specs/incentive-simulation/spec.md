# Spec Delta

## MODIFIED Requirements

### Requirement: Acceptance criteria for the mechanism
The mechanism SHALL be considered sound for a parameter set only if, over the published scenarios and seeds:
- honest contributors, validators and sponsored newcomers earn a positive mean return;
- every kind of author earns a negative pooled mean per defective contribution;
- griefers lose money;
- splitting, collusion below the threshold and the owner's self-interested play gain nothing against honest play (mean over seeds, within two standard errors).

#### Scenario: Attacks lose money
- **WHEN** the spam, splitting, griefing and sponsorship-abuse scenarios run with the proposed parameters
- **THEN** each kind of author earns a negative pooled mean per defective contribution (sponsors' losses included), griefers lose money, and splitting gains nothing against the same changes unsplit

#### Scenario: Collusion measured against honest play
- **WHEN** the collusion scenario runs at a given stake share, and again on the same seed with the ring's members acting honestly
- **THEN** the report gives the ring's gain from colluding (the difference) as a mean over seeds with its standard error, and below the collusion threshold that gain is not positive

#### Scenario: Collusion threshold measured
- **WHEN** the collusion scenario is run with the colluders' share of validator stake raised step by step
- **THEN** the report gives the smallest share at which the gain from colluding is significantly positive, and the published threshold is below it

#### Scenario: Owner can't gain by defecting
- **WHEN** the owner scenario runs with the owner playing honestly and with the owner self-interested
- **THEN** the self-interested owner's mean payout over seeds is not significantly higher than the honest owner's

#### Scenario: Unsound parameters reported
- **WHEN** a parameter set fails any criterion
- **THEN** the report names the failed criterion, the scenario and the seed, or "all" for criteria judged over seeds

## ADDED Requirements

### Requirement: Actors for the new rules
The simulation SHALL also provide these actors:
- **Reviewer duty:** validators drawn as reviewers find a defect with a configurable rate.
- **Declining maintainer:** declines others' contributions up to the limit and beyond, and appeals are filed against those declines.
- **Sponsored newcomer:** contributes with a sponsor's stake.
- **Sponsorship abuser:** spams through sponsored accounts it controls.

#### Scenario: Sponsorship abuse costs the sponsor
- **WHEN** the abuser's sponsored accounts spam and are slashed
- **THEN** the forfeits come out of the abuser's sponsoring stake, and the report shows the abuser's return including those losses
