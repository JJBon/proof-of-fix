# Spec Delta

## ADDED Requirements

### Requirement: The project's constitution
In `race` and `claim`, every delivery SHALL pass the project's constitution, a versioned set of quality gates published in the repository: coverage of the changed code and a mutation score, measured by the attested runners; published limits on diff size and performance; and the AI juries' pass or fail under the existing consensus rules. A delivery that fails any gate SHALL fail, whatever the others say.

#### Scenario: Padded tests
- **WHEN** a delivery adds tests that raise coverage but catch none of the planted mutations
- **THEN** it fails the mutation gate

#### Scenario: Gates are versioned
- **WHEN** the constitution changes
- **THEN** bounties registered before the change are judged by the version they were registered under
