# Spec Delta

## ADDED Requirements

### Requirement: A solver's open claims are capped by its reputation
A solver identity's open claims, the bounties of its fixes submitted and not yet final, SHALL add up to at most `REP_BASE` plus `REP_MULT` times its reputation (#132 D29). A submission over the cap SHALL be refused before it is judged, and SHALL cost nothing.

#### Scenario: A new identity
- **WHEN** an identity with no paid fix submits a fix to a $40 bounty, then another to a $30 bounty while the first isn't final
- **THEN** the first is accepted ($40 of a $50 cap) and the second is refused, with no fee taken

#### Scenario: An established identity
- **WHEN** an identity with $200 of reputation and no open claims submits a fix to a $240 bounty
- **THEN** it is accepted, since its cap is $50 + 1 × $200 = $250

### Requirement: Reputation is what an identity's fixes earned and kept
An identity's reputation SHALL be the sum of the bounties of its fixes paid and never reversed, recorded on-chain against the identity, and SHALL never be transferred by any function.

#### Scenario: A fix paid
- **WHEN** an identity's fix to an $80 bounty becomes final and its award starts
- **THEN** its reputation rises by $80

### Requirement: A reversal costs twice its bounty
When a pass is reversed by a test or a challenge, the solver's reputation SHALL fall by `REP_LOSS_X` (2) times that fix's bounty, and not below zero. It SHALL NOT reset to zero.

#### Scenario: An honest mistake reversed
- **WHEN** an identity with $500 of reputation has a $60 fix reversed by a failing test
- **THEN** its reputation falls to $380, and its cap to $430
