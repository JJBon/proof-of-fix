# Spec Delta

## ADDED Requirements

### Requirement: Attempt costs and duplicate appeals: scenarios and criteria
The market simulation SHALL provide a fake attempter (sock accounts that start attempts they never submit, inflating the count and locking prices early) and SHALL flag honest independent fixes as duplicates at a published false-positive rate. The fake attempter SHALL NOT gain significantly against its honest twin; honest solvers SHALL still earn; falsely flagged honest fixes SHALL mostly win on appeal; every earlier criterion SHALL hold or be named.

#### Scenario: Fake attempts don't pay
- **WHEN** the fake attempter runs, and on the same seeds the same accounts behave honestly
- **THEN** its return, its fees counted, isn't significantly higher

#### Scenario: False duplicates appealed
- **WHEN** honest fixes are flagged as duplicates at the swept false-positive rates
- **THEN** the report gives the share won on appeal and honest solvers' earnings at each rate
