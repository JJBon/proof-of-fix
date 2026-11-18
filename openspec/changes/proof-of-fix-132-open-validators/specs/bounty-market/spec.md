# Spec Delta

## ADDED Requirements

### Requirement: A solver's deposit is lost on rejection
In v3, a submission SHALL post, beside its check deposit, a deposit of the published share of the bounty, quoted before the attempt. It SHALL be returned when the fix is paid. When the fix is rejected and no appeal passes it, the deposit SHALL be added to the issue's bounty. When a passing verdict is reversed by a dispute backed by a failing test, the deposit SHALL go to the disputer. It SHALL never go to a judge of the submission, nor to the issue's funder or reporter.

#### Scenario: A bad fix rejected
- **WHEN** a panel rejects a fix to an $80 bounty and the solver doesn't appeal
- **THEN** its $20 deposit is added to the bounty, which is now $100 for the next solver

#### Scenario: A good fix paid
- **WHEN** a fix passes and its window ends with no dispute upheld
- **THEN** the solver is paid the bounty and gets its deposit back

#### Scenario: Judges don't earn by rejecting
- **WHEN** a panel rejects a fix
- **THEN** none of its judges receives any part of the deposit

### Requirement: A rejected fix's deposit is held until its appeal period closes (proposed)
A rejected fix's deposit SHALL be held, and not added to the issue's bounty, until its appeal period closes. With no appeal it SHALL then go to the issue's bounty. If an appeal passes the fix, it SHALL return to the solver when the fix is paid. If the appeal fails, it SHALL go to the issue's bounty. If the issue's bounty was already paid, it SHALL go to the sponsors' pool.

#### Scenario: An appeal that passes
- **WHEN** a fix to an $80 bounty is rejected, its appeal passes it, and no dispute is upheld
- **THEN** the solver is paid the bounty and gets back its $20 deposit and its appeal stake

#### Scenario: An appeal that fails
- **WHEN** the appeal fails
- **THEN** the $20 deposit is added to the issue's bounty and the appeal stake goes to the sponsors' pool

#### Scenario: Another fix while the deposit is held
- **WHEN** the same solver submits a second fix to the issue while the first one's deposit is held
- **THEN** the second fix's deposit is the published share of the $80 bounty, and the first deposit joins the bounty only when its appeal period closes

