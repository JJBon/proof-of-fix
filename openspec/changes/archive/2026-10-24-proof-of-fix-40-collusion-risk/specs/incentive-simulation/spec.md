# Spec Delta

## ADDED Requirements

### Requirement: Solvers price risk from their record
In the market simulation, a solver's break-even price SHALL use its own delivery-failure and slash rates, estimated from its recorded outcomes with the default assumption as a prior, rather than the default assumption alone.

#### Scenario: A solver that fails more
- **WHEN** a solver's record shows more failed deliveries than the default assumption expects
- **THEN** its break-even price for the same job is higher than a solver's with a clean record

### Requirement: Acceptance criteria for collusion and risk pricing
The market mode SHALL be considered sound only if, over the published seeds with two standard errors, no ring of up to six colluding solvers gains significantly against the same solvers competing, bidding one's cost is best at every published hunting elasticity, and every earlier market criterion still holds.

#### Scenario: No ring gains
- **WHEN** rings of 2, 3, 4 and 6 solvers run, and on the same seeds the same solvers compete
- **THEN** no ring's gain is significantly positive

#### Scenario: Bidding your cost is best at every elasticity
- **WHEN** the bluffing scenario runs at hunting elasticity 0, 0.5 and 1
- **THEN** bluffing and lowballing gain nothing significant at any of them

#### Scenario: Unsolved bounties reported
- **WHEN** the reserve sweep runs
- **THEN** the report gives, per reserve, the bounties paid and those closed unsolved
