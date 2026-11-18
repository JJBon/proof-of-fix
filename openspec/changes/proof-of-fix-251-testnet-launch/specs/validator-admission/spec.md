# Spec Delta

## ADDED Requirements

### Requirement: A validator below the bond floor is visibly inactive
When a slash or any other change leaves an active validator's bond below the bond floor, the registry SHALL emit an event saying so, report the validator in a below-floor state, and stop counting it as active, in the same transaction. It SHALL NOT be drawn, and SHALL return to active when topped up to the floor.

#### Scenario: A silence slash on a floor bond
- **WHEN** a validator bonded at exactly the floor ($100) is slashed $5 for silence
- **THEN** in the same transaction an event names the validator and its bond ($95), the registry reports it below the floor, and the active count falls by one

#### Scenario: Topping up
- **WHEN** the operator tops up a below-floor validator to at least the floor
- **THEN** an event says it is active again, it counts as active, and it can be drawn without qualifying again

### Requirement: A below-floor validator can always leave
A validator below the floor SHALL be able to announce leaving, and its remaining bond SHALL be withdrawable under the same unbonding delay and conditions as any leaving validator.

#### Scenario: Leaving instead of topping up
- **WHEN** the operator of a below-floor validator announces leaving
- **THEN** it enters the leaving state, stays slashable until the delay ends and its verdicts are final, and then its remaining bond is withdrawable

### Requirement: The node reports and handles a below-floor bond
The validator's node SHALL report the below-floor state to its operator as soon as it sees the event, and SHALL top up on its own only if the operator configured an amount for that.

#### Scenario: A node with no top-up configured
- **WHEN** the node sees its validator go below the floor and no top-up amount is configured
- **THEN** it logs the state and the amount missing, and stops waiting for draws until the bond is restored or the validator leaves
