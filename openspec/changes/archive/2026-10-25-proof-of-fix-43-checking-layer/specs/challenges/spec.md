# Spec Delta

## MODIFIED Requirements

### Requirement: Objective proof
A challenge SHALL carry a reproducible proof: a test or input that passes on the build before the contribution and fails on the build with it; or, against a bounty's winning contribution, a case of the bounty's reported issue that still fails on the build with it (not solved). A challenge without such a proof SHALL be refused before validators are selected.

#### Scenario: Valid regression proof
- **WHEN** a challenge includes a test that passes on the parent build and fails on the beta build with the contribution
- **THEN** the challenge is admitted, and validators are selected

#### Scenario: No proof
- **WHEN** a challenge has only a description, or a test that fails on both builds
- **THEN** it is refused, and only the published filing fee is kept from the challenger's stake

#### Scenario: Formula result against a reference
- **WHEN** a GridCraft challenge gives a formula and inputs whose result after the contribution differs from both the result before it and the reference implementation's result
- **THEN** the proof counts as reproducible

#### Scenario: Not solved
- **WHEN** a challenge against a bounty's winning contribution gives a case of the reported issue that still fails with the contribution, though nothing that worked before breaks
- **THEN** the proof counts, and an upheld challenge slashes the contribution as a wrong result

#### Scenario: Not solved, without a bounty
- **WHEN** a "not solved" challenge is filed against a contribution that no bounty paid for
- **THEN** it is refused: there's no reported issue to judge it against
