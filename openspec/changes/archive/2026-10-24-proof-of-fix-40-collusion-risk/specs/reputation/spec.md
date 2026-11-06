# Spec Delta

## MODIFIED Requirements

### Requirement: Scores from outcomes
Each account SHALL have a score per role (solver, reporter, funder), starting at zero and changed only by recorded outcomes, with published points. A fix accepted raises its solver's, its reporter's and, above a minimum pledge, its funders' scores, by at most a published number of points per role per release; a failed delivery, slash or clawback lowers the solver's more; a forfeited issue lowers the reporter's more.

#### Scenario: An accepted job
- **WHEN** a solver's contribution for a bounty is accepted at the end of its challenge window
- **THEN** its solver score rises by the published points, and the ledger records the change with the bounty

#### Scenario: Capped per release
- **WHEN** an account would earn more positive points in one role in one release than the published cap
- **THEN** it earns the cap, and the ledger records the outcome with no points beyond it

#### Scenario: A failure
- **WHEN** a solver fails a delivery, or its contribution is slashed or clawed back
- **THEN** its solver score falls by the published points for that outcome, whatever it earned in the release

#### Scenario: A small pledge
- **WHEN** a funder's pledge to a bounty whose fix is accepted is below the published minimum
- **THEN** its funder score doesn't change
