# reputation Specification

## Purpose
Defines non-transferable reputation for the market's participants: scores built only from outcomes on the ledger, and the trust derived from them that the market uses to weight matching, rank treasury proposals and size bonds.

## ADDED Requirements

### Requirement: Scores from outcomes
Each account SHALL have a score per role (solver, reporter, funder), starting at zero and changed only by recorded outcomes, with published points. A fix accepted (its window closed) raises its solver's, its reporter's and, above a minimum pledge, its funders' scores; a failed delivery, slash or clawback lowers the solver's more; a forfeited issue lowers the reporter's more.

#### Scenario: An accepted job
- **WHEN** a solver's contribution for a bounty is accepted at the end of its challenge window
- **THEN** its solver score rises by the published points, and the ledger records the change with the bounty

#### Scenario: A failure
- **WHEN** a solver fails a delivery, or its contribution is slashed or clawed back
- **THEN** its solver score falls by the published points for that outcome

#### Scenario: A small pledge
- **WHEN** a funder's pledge to a bounty whose fix is accepted is below the published minimum
- **THEN** its funder score doesn't change

### Requirement: Non-transferable and recomputable
Scores SHALL belong to the account that earned them: no operation SHALL move, sell or merge them. Every change SHALL be recorded on the ledger with its outcome, so that anyone can recompute every score from the records.

#### Scenario: Recomputed from the records
- **WHEN** scores are recomputed from the ledger's recorded outcomes alone
- **THEN** they equal the published scores

#### Scenario: No transfer
- **WHEN** an account tries to give its score to another
- **THEN** there is no operation for it, and the scores are unchanged

### Requirement: Trust
Trust SHALL be a published function of a score: a published floor at zero, rising by a published step per point up to one, and falling by the step per point below zero, down to nothing.

#### Scenario: A newcomer
- **WHEN** an account has no recorded outcome in a role
- **THEN** its trust in that role is the floor

#### Scenario: Proven
- **WHEN** an account's score reaches the points that bring the floor to one
- **THEN** its trust is one, and more points don't raise it further

#### Scenario: A proven offender
- **WHEN** an account's score is below zero
- **THEN** its trust is below a newcomer's, and nothing at enough negative points
