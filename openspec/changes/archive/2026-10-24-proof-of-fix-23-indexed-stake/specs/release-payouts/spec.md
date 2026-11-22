# Spec Delta

## ADDED Requirements

### Requirement: Reward capped relative to the stake
A contribution's escrowed reward SHALL be at most a published multiple of its stake. When the division by weight would give it more, the excess SHALL stay in the contributors' pool and roll over to the next release.

#### Scenario: Lone contribution in a sparse release
- **WHEN** a beta build takes in one contribution whose share of the contributors' pool is above the cap
- **THEN** it is escrowed exactly the cap, and the rest of the pool stays for the next release

#### Scenario: Under the cap
- **WHEN** every contribution's share by weight is under the cap
- **THEN** the division is unchanged

#### Scenario: Nothing lost
- **WHEN** rewards are capped in a release
- **THEN** the escrowed rewards plus what stays in the pool equal the pool before the beta build
