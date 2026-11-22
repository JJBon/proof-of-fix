# Spec Delta

## MODIFIED Requirements

### Requirement: Acceptance criteria for the mechanism
The mechanism SHALL be sound for a parameter set only if, over the published scenarios and seeds, judged with two standard errors:
- honest contributors, validators and sponsored newcomers earn a positive mean return;
- attacking kinds lose money per defective contribution, significantly; honest kinds don't gain from theirs;
- griefers lose money;
- splitting (per accepted line), collusion below the threshold and a self-interested owner gain nothing against honest play.

#### Scenario: Attacks lose money
- **WHEN** the spam, splitting, griefing and sponsorship-abuse scenarios run with the proposed parameters
- **THEN** each attacking kind's pooled mean per defective contribution, plus two standard errors clustered by seed, is below zero (sponsors' losses included), and griefers lose money

#### Scenario: Too few defective contributions to judge
- **WHEN** an attacking kind has fewer defective contributions over the seeds than the published minimum
- **THEN** the criterion is reported inconclusive for that kind, which counts as a failure, and the report gives the count

#### Scenario: Honest mistakes don't pay
- **WHEN** honest contributors, the owner or sponsored newcomers submit contributions that turn out defective
- **THEN** their pooled mean per defective contribution, minus two standard errors, is not above zero

#### Scenario: Splitting measured per accepted line
- **WHEN** the splitter's changes run split and, on the same seed, unsplit
- **THEN** the report gives each run's return per accepted line and its lines accepted, and the split return per line is not significantly higher than the unsplit one

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

### Requirement: Acceptance with pledges
The acceptance criteria SHALL hold with pledged stakes available to every actor, whenever the published pledge cap is above zero.

#### Scenario: Attacks lose money with pledges
- **WHEN** the spam, splitting, griefing, sponsorship-abuse and pledge-stacking scenarios run with pledges available to every actor
- **THEN** each attacking kind loses money per defective contribution significantly (sponsors' losses and forfeited pledges included), and every other acceptance criterion still passes
