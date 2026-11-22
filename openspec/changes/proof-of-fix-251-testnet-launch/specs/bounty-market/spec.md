# Spec Delta

## ADDED Requirements

### Requirement: A submission pays only its metered validation
On the Sepolia launch (#132 D30 as the pure taxi fare, owner 2026-11-19), a fix's submission SHALL post the deposit the fee meter quotes for the largest panel, its judges SHALL be paid by the meter, and the rest SHALL return to the solver, whatever the outcome. The pool SHALL keep no fee, and a solver SHALL pay no attempt, evaluation or appeal fee. A flat `JUDGE_FEE` is left to a later deployment.

#### Scenario: A rejected fix
- **WHEN** a solver's submission is judged and rejected
- **THEN** it has paid its panels' metered checks and nothing more, and the rest of its deposit returns to it

#### Scenario: A withdrawn submission
- **WHEN** a solver withdraws a submission no panel was seated for
- **THEN** its whole deposit returns, and no per-check charge is made

#### Scenario: Spam on the testnet
- **WHEN** a party submits junk fixes, or appeals every rejection, from free identities
- **THEN** each pays only its panels' meter: the validators' capacity and spending caps bound their model cost, and honest fixes may wait in the queue (an accepted risk, named in the README and the paper)

### Requirement: What makes a solver active
A solver identity SHALL be active in the repository while, within the last `ACTIVE_WINDOW` (26 weeks), it has at least one fix whose passing verdict became final or one failing-test dispute that was upheld, recorded on-chain. An upheld dispute SHALL count only for an identity that has a final passing fix in the repository. The count of active solvers SHALL be readable by anyone.

#### Scenario: A solver whose last fix is old
- **WHEN** an identity's only final pass is older than `ACTIVE_WINDOW` and it has no upheld dispute since
- **THEN** it no longer counts as active

#### Scenario: A solver who found a bad fix
- **WHEN** an identity with a final passing fix in the repository has a failing-test dispute against another passed fix upheld
- **THEN** it counts as active for `ACTIVE_WINDOW` from then

#### Scenario: A disputer from outside the repository
- **WHEN** an identity with no final passing fix in the repository has a failing-test dispute upheld
- **THEN** it is paid as any disputer is, but it doesn't count as active

### Requirement: No pledges before three active solvers
While the repository has fewer than `ACTIVE_SOLVERS_MIN` (3) active solvers, the contracts SHALL refuse every pledge. Issues SHALL still be registered and fixed with no funds, and those fixes SHALL count toward activity. Bounties already funded SHALL continue.

#### Scenario: The testnet's first weeks
- **WHEN** a funder pledges to a bounty while only two solvers are active
- **THEN** the pledge reverts with the count of active solvers, and no coin moves

#### Scenario: Activity lapses with funded bounties open
- **WHEN** the count of active solvers falls from 3 to 2 while two bounties hold pledges
- **THEN** those bounties stay open, keep their funds and can be won, and only new pledges are refused until the count is back at 3
