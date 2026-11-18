# Spec Delta

## ADDED Requirements

### Requirement: Every submission pays the judges' fee
In v3, every submission SHALL pay the published judges' fee `JUDGE_FEE` on arrival, in place of its panels' per-check charges (#132 D30). It SHALL never be refunded and never be more on rejection. The fee SHALL be the measured cost of judging in the last period, as #132 specifies.

#### Scenario: A rejected fix
- **WHEN** a solver's submission is judged and rejected
- **THEN** it has paid `JUDGE_FEE` and nothing more, and the fee isn't returned

#### Scenario: A withdrawn submission
- **WHEN** a solver withdraws a submission no panel was seated for
- **THEN** the fee isn't returned, and no per-check charge is made

### Requirement: What makes a solver active
A solver identity SHALL be active in the repository while, within the last `ACTIVE_WINDOW`, it has at least one fix whose passing verdict became final or one failing-test dispute that was upheld, recorded on-chain. The count of active solvers SHALL be readable by anyone.

#### Scenario: A solver whose last fix is old
- **WHEN** an identity's only final pass is older than `ACTIVE_WINDOW` and it has no upheld dispute since
- **THEN** it no longer counts as active

#### Scenario: A disputer who found a bad fix
- **WHEN** an identity's failing-test dispute against a passed fix is upheld
- **THEN** it counts as active for `ACTIVE_WINDOW` from then, whether or not it has a fix of its own

### Requirement: No pledges before three active solvers
While the repository has fewer than `ACTIVE_SOLVERS_MIN` (3) active solvers, the contracts SHALL refuse every pledge. Issues SHALL still be registered and fixed with no funds, and those fixes SHALL count toward activity. Bounties already funded SHALL continue.

#### Scenario: The testnet's first weeks
- **WHEN** a funder pledges to a bounty while only two solvers are active
- **THEN** the pledge reverts with the count of active solvers, and no coin moves

#### Scenario: Activity lapses with funded bounties open
- **WHEN** the count of active solvers falls from 3 to 2 while two bounties hold pledges
- **THEN** those bounties stay open, keep their funds and can be won, and only new pledges are refused until the count is back at 3
