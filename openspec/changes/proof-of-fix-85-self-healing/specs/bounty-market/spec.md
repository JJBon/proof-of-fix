# Spec Delta

## ADDED Requirements

### Requirement: Coin only and no fee at launch
The deployed contracts SHALL mint no token and take no protocol fee. Bounties SHALL pay in the coins their funders pledge, and judges SHALL be paid only by check fees. A token SHALL be enabled only in a new version that holders choose to migrate to.

#### Scenario: A bounty closes paid
- **WHEN** a bounty's last instalment is released
- **THEN** its solver and reporter have been paid in the pledged coins, and no token is minted

#### Scenario: No cut
- **WHEN** a winner's price is escrowed on-chain
- **THEN** nothing of it goes to the owner, the operators or any fee address

## MODIFIED Requirements

### Requirement: Checks paid by the contributor
Every check run on a delivery SHALL be paid from the solver's check deposit, never from the bounty while the race runs, charged as the oracle-network capability's check fees define and the unused deposit refunded. When a fix is merged, the winner's checks for it SHALL be refunded from the bounty. Whether a bounty is worth attempting, checks included, SHALL be the solver's judgement.

#### Scenario: The solver pays its checks
- **WHEN** a delivery's tests run and the judges give their verdicts
- **THEN** each counted judge is paid from the solver's deposit, for the median usage at its own family's unit prices plus the agreed service fee, and the unused deposit is refunded

#### Scenario: Splitting the jury costs the splitter
- **WHEN** a solver delivers junk that splits the first jury, is rejected by the second, and gets its bond back
- **THEN** it has paid every check from its deposit, so repeating the attempt costs it the checks each time

#### Scenario: The winner is refunded
- **WHEN** a fix is merged
- **THEN** its solver is refunded the fees of that fix's checks from the bounty, and failed attempts are never refunded

#### Scenario: The ceiling is known first
- **WHEN** a solver considers an attempt
- **THEN** the contract states the deposit's maximum before the attempt, from the price table, the service fee and the repository's CI profile in force

#### Scenario: No room needed in the price
- **WHEN** a bounty holds 300
- **THEN** its price cap is computed on all 300, as before oracle fees
