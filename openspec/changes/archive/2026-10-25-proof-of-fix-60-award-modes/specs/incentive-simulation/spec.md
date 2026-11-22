# Spec Delta

## ADDED Requirements

### Requirement: Award modes compared
The market simulation SHALL give every fix a quality, from its solver, that the gates measure with a published accuracy, and SHALL run the acceptance scenarios in every award mode on the same seeds. The report SHALL compare: honest solvers' earnings; wasted effort, at a sweep of attempt costs; funders' cost per solved bounty; bounties solved; good fixes accepted; time to fix; and every attack's gain.

#### Scenario: Wasted effort
- **WHEN** the race runs at a given attempt cost
- **THEN** the report gives the share of solver effort spent on attempts that weren't paid

#### Scenario: New attacks
- **WHEN** spam bounties, padded submissions, a second identity racing, or inflated effort estimates run in a mode
- **THEN** the report gives each one's gain against its honest twin, judged like the other attacks
