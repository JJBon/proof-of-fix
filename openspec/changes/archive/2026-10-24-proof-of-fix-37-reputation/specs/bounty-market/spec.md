# Spec Delta

## MODIFIED Requirements

### Requirement: Sealed rounds for the job
A solver SHALL bid for the job, before building anything, by committing a sealed price at most the bounty's price cap. It SHALL post a stake, a published share of the cap times the risk multiplier, lowered by its solver trust down to a published share of that, and a fixed evaluation fee. After the deadline, every bidder SHALL reveal its price. A bid that isn't revealed or doesn't match its commitment SHALL forfeit its fee.

#### Scenario: Bid accepted
- **WHEN** a solver commits a sealed price before the deadline, with enough balance for the stake and fee
- **THEN** the stake and fee are locked, and no one can see the price

#### Scenario: A proven solver's bond
- **WHEN** a solver with full trust bids
- **THEN** its stake is the published share of the full stake, while a newcomer's is the full stake

#### Scenario: Nothing to copy
- **WHEN** a round's bids are revealed
- **THEN** only prices are revealed: no solution exists yet, so no one can copy one

#### Scenario: Reveal doesn't match
- **WHEN** a bidder's reveal doesn't match its commitment, or it doesn't reveal
- **THEN** its fee is forfeited to the checking costs, its stake returns, and it can't be assigned the job

### Requirement: Quadratic matching
A published share of each release's treasury budget SHALL match pledges on bounties still gathering pledges, by weight: the sum over pledgers of their funder trust times the square root of their pledges, squared, less the sum of each pledger's trust squared times its pledges. Matches SHALL be scaled to fit that share, capped per bounty at a published share of its target, and counted toward the target.

#### Scenario: Many small pledgers attract more
- **WHEN** one bounty gathers 100 credits from ten pledgers and another 100 credits from one pledger, all with the same trust
- **THEN** the first is matched and the second isn't

#### Scenario: New accounts draw little
- **WHEN** two bounties gather the same pledges from the same number of pledgers, one from proven funders and one from new accounts
- **THEN** the second's weight is the first's times the floor squared

#### Scenario: Within the matching budget
- **WHEN** the weights of all bounties gathering pledges add up to more than the release's matching budget
- **THEN** every match is scaled down by the same factor, and the total stays within the budget

#### Scenario: Capped
- **WHEN** a bounty's match would exceed the published share of its target
- **THEN** it gets exactly the cap

#### Scenario: A match completes the target
- **WHEN** a match brings a bounty's funds to its target
- **THEN** the bounty opens its sealed round

### Requirement: Treasury bounties
Each release SHALL make a published treasury budget available, less its matching share, for bounties on issues nobody pledges for, proposed by the treasury in order of value times the reporter's trust. No single bounty SHALL exceed a published cap. A proposal above a published threshold SHALL need a validator panel's majority. Unspent budget SHALL NOT accumulate beyond one release.

#### Scenario: Within the budget
- **WHEN** the treasury proposes bounties whose total stays within the release's budget, less its matching share
- **THEN** each is funded from the budget and opens a sealed round like a pledged one

#### Scenario: Ranked by trust
- **WHEN** two unpledged issues of equal value come from a proven reporter and from a new one
- **THEN** the proven reporter's issue is proposed first

#### Scenario: Over the budget
- **WHEN** a proposal would take the release's treasury spend over that budget
- **THEN** it is refused, and the ledger records the refusal

#### Scenario: A large proposal
- **WHEN** a proposal exceeds the approval threshold
- **THEN** it is funded only if a validator panel's majority approves it
