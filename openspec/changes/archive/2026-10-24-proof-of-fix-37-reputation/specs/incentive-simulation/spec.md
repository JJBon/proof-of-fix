# Spec Delta

## ADDED Requirements

### Requirement: Market scenarios for reputation
The market simulation SHALL keep every account's scores as the market records outcomes, and SHALL provide a reputation farmer: it builds solver trust on cheap jobs, then wins a large job with a low bid and doesn't deliver.

#### Scenario: Scores reported
- **WHEN** a market run finishes
- **THEN** the report gives each kind's mean score and trust per role, and the honest solvers' mean bond per assignment

### Requirement: Acceptance criteria for reputation
The market mode SHALL be considered sound only if, over the published seeds, with two standard errors:
- every earlier market criterion still holds;
- crowd-out stays bounded at 50 % junk detection;
- fake accounts don't make a match farmer's own fixes significantly cheaper;
- the reputation farmer loses money;
- honest solvers' mean bond is significantly lower than with no discount, on the same seeds.

#### Scenario: Crowd-out at weak detection
- **WHEN** the flood runs at 50 % junk detection, and on the same seeds no flood runs at the same detection
- **THEN** real issues funded by the treasury under the flood are at least three quarters of those without it

#### Scenario: Reputation farming loses
- **WHEN** the reputation farmer runs
- **THEN** its return, its effort counted, is significantly negative

#### Scenario: Proven solvers lock less
- **WHEN** the same seeds run with the bond discount and without it
- **THEN** honest solvers' mean bond per assignment is significantly lower with it
