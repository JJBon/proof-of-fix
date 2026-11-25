# Spec Delta

## ADDED Requirements

### Requirement: Calibration checks qualify the launch's candidates
When a deployment starts with one active validator, the project SHALL be able to seed calibration checks: issues and fixes for deliberate, small bugs kept in the repository and labelled as calibration. Each item's protected test SHALL fail on its bug and judge its fix, while the repository's test command stays green with every bug present. About a quarter of the prepared fixes SHALL be subtly wrong, recorded only in the driver's data, never in anything the judges read.

#### Scenario: Candidates qualify on calibration checks
- **WHEN** a deployment has one active validator and six candidates, and the driver registers calibration issues
- **THEN** the candidates' scored shadow verdicts come from the calibration checks, and each candidate that meets the qualification thresholds becomes active

#### Scenario: A subtly wrong calibration fix
- **WHEN** a prepared fix that passes its issue's example but not its edge cases is submitted once its registration check is final
- **THEN** its protected test fails in the sandbox and the panel fails the fix, while main's suite stays green

### Requirement: The calibration driver is bounded and resumable
The calibration driver SHALL record every check it starts and its outcome in a ledger it resumes from, SHALL stop before an estimated model spend set in advance, SHALL never print a secret, and SHALL refuse to spend on a public network without an explicit confirmation.

#### Scenario: The budget is reached
- **WHEN** the next check would take the estimated model spend over the budget
- **THEN** the driver stops before starting it, and a later run resumes from its ledger without repeating a registration

#### Scenario: A run on the public test network
- **WHEN** someone starts the driver against Sepolia without the spending confirmation
- **THEN** it refuses before reading or sending anything
