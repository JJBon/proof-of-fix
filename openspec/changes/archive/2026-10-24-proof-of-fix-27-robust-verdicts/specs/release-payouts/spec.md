# Spec Delta

## ADDED Requirements

### Requirement: Funding follows use
Before a release is funded, if the contributors' pool already holds more than a published buffer of releases' worth of the contributors' share, the release's whole funding SHALL be scaled down by the same factor for every share, by the surplus over the buffer, down to nothing. The published shares SHALL stay as they are.

#### Scenario: Pool within the buffer
- **WHEN** the contributors' pool holds at most the buffer when a release opens
- **THEN** the release is funded in full

#### Scenario: Pool over the buffer
- **WHEN** the contributors' pool holds more than the buffer when a release opens
- **THEN** every share of that release is reduced by the same factor, the amounts still match the published shares of the reduced funding, and the ledger records the factor

#### Scenario: Buffer switched off
- **WHEN** the published buffer is zero
- **THEN** every release is funded in full, as before
