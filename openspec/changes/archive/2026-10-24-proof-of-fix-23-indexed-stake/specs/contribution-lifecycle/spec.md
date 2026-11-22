# Spec Delta

## ADDED Requirements

### Requirement: Stake indexed to the expected reward
Once releases have paid rewards, the entry stake SHALL be a published share of the contribution's expected reward, at least a published floor for its size and at most the fixed stake for its size, times its risk multiplier. The expected reward SHALL be the reward per unit of weight over a published window of recent releases, times the contribution's weight. Before any reward is paid, the fixed stake SHALL apply.

#### Scenario: No history yet
- **WHEN** a contribution is submitted before any beta build has escrowed a reward
- **THEN** its stake is the fixed stake for its size and risk class

#### Scenario: The stake follows the reward
- **WHEN** the reward per unit of weight over the window falls, for example because many more contributions share each release
- **THEN** the stake for the same size and risk falls with it, never below the floor for that size

#### Scenario: Never above the fixed stake
- **WHEN** the expected reward is large enough that its share exceeds the fixed stake for that size
- **THEN** the stake is the fixed stake

#### Scenario: Larger contributions still need larger stakes
- **WHEN** two contributions submitted at the same time differ only in size, one at about 78 changed lines and one at about 1,098
- **THEN** the larger one requires a strictly larger stake

#### Scenario: Anyone can recompute the stake
- **WHEN** a beta build ships
- **THEN** the ledger records the reward per unit of weight it sets for the window, so the stake of any later submission can be recomputed from published records and parameters
