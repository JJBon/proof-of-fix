# Spec Delta

## ADDED Requirements

### Requirement: Self-healing scenarios
The simulation SHALL model judges as model families whose errors correlate, the two tiers and escalation, the canonical head, system issues and the sponsors' pool, and the winner's check refund. It SHALL provide a test-gaming solver, a prompt injector, operators colluding in groups of 2 to 5 of 7, an ADR capturer and a watcher farming system issues.

#### Scenario: Three judges and seven compared
- **WHEN** the same seeds run with every fix judged by the issue tier and with every fix judged by the constitution tier
- **THEN** the report gives, for each, the cost per paid fix, the share of bad fixes merged and the days to fix

#### Scenario: The refund compared
- **WHEN** the same seeds run with and without the winner's check refund
- **THEN** the report gives funders' cost per paid fix, bounties paid, and honest solvers' returns under both

### Requirement: Oracle network scenarios
The simulation SHALL model check fees charged as measured usage at unit prices plus one agreed service fee, under a bounded price table and fee, seat bonds, and slashing for provable faults. It SHALL provide a judge that doesn't reveal, an equivocator, a judge padding its reported usage, a seat withholding data it signed to hold, and seats colluding to raise the price table or the service fee.

#### Scenario: Check gas against flat fees
- **WHEN** the same seeds run with check gas and with flat published fees
- **THEN** the report gives solvers' and funders' cost per paid fix and operators' net per check under both

#### Scenario: The bond's size
- **WHEN** the bond is varied over a published range
- **THEN** the report gives the smallest bond at which every slashable fault loses money for the seat that commits it

#### Scenario: The price table pushed by colluders
- **WHEN** 5 colluding seats raise every price and the service fee by the maximum at every chance for a year
- **THEN** the report gives the resulting fees and how many bounties stop being attempted

### Requirement: Acceptance criteria for self-healing
Self-healing SHALL be considered sound only if, over the published seeds with two standard errors: the test-gamer, the prompt injector, the ADR capturer and the issue farmer each lose against an honest twin; operators colluding below 5 of 7 never pass an ADR; bad fixes merged are no more than with 3 judges and no escalation; the non-revealer, the equivocator, the usage padder and the data withholder each lose against an honest twin; and every earlier criterion holds or is named.

#### Scenario: Attacks lose
- **WHEN** each attacker's scenario runs, and on the same seeds the same actor behaves honestly
- **THEN** the attacker's return, its effort and fees counted, is significantly lower

#### Scenario: Collusion below the quorum
- **WHEN** 4 of the 7 operators always pass the colluders' ADRs
- **THEN** no such ADR takes effect in any run

#### Scenario: Collusion at the quorum
- **WHEN** 5 of the 7 operators collude
- **THEN** the report gives what they can pass, as the remaining trust point, and how often challenges and the public log catch it
