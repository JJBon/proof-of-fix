# Spec Delta

## ADDED Requirements

### Requirement: Issue stakes
Whoever submits an issue SHALL post a published issue stake. When the issue's bounty is paid, the stake SHALL return with a finder's fee: a published share of the winning price, paid from the bounty and smaller than the market fee. When the issue is judged junk, the stake SHALL go to insurance. An issue that's never funded SHALL get its stake back.

#### Scenario: Real issue fixed
- **WHEN** an issue's bounty is paid after its fix ships and its instalments are paid
- **THEN** the reporter's stake returns, with the finder's fee on the winning price

#### Scenario: Junk confirmed
- **WHEN** the treasury flags an issue as junk and a validator panel confirms it, or the fix delivered for it is slashed as junk
- **THEN** the reporter's stake goes to insurance, and the issue gets no bounty, or no further one

#### Scenario: Flag not confirmed
- **WHEN** the treasury flags an issue as junk and the panel doesn't confirm it
- **THEN** the stake stays posted, and the issue can still be funded

#### Scenario: Never funded
- **WHEN** an issue is neither pledged to its target nor funded by the treasury before its deadline
- **THEN** the reporter's stake returns, with no fee

#### Scenario: Funding your own issue doesn't pay
- **WHEN** a reporter funds its own issue in full
- **THEN** the finder's fee it receives is smaller than the market fee its own pledge paid on the same price

### Requirement: Quadratic matching
A published share of each release's treasury budget SHALL match pledges on bounties still gathering pledges, by weight (the sum of the square roots of each pledger's pledges, squared, less the pledges), scaled to fit that share, capped per bounty at a published share of its target, and counted toward the target.

#### Scenario: Many small pledgers attract more
- **WHEN** one bounty gathers 100 credits from ten pledgers and another 100 credits from one pledger
- **THEN** the first is matched and the second isn't

#### Scenario: Within the matching budget
- **WHEN** the weights of all bounties gathering pledges add up to more than the release's matching budget
- **THEN** every match is scaled down by the same factor, and the total stays within the budget

#### Scenario: Capped
- **WHEN** a bounty's match would exceed the published share of its target
- **THEN** it gets exactly the cap

#### Scenario: A match completes the target
- **WHEN** a match brings a bounty's funds to its target
- **THEN** the bounty opens its sealed round

### Requirement: Unsolved bounties close
A funded bounty whose round closes without a bid for a published number of rounds in a row SHALL close: its funds SHALL return in proportion to what each source put in, the treasury's share to insurance, and its reporter's stake SHALL return, with no fee.

#### Scenario: No one can do it
- **WHEN** a bounty's rounds close without a bid for the published number of rounds
- **THEN** it closes, the pledgers get their share back, the treasury's share goes to insurance, and the reporter gets its stake back

#### Scenario: A bid in time
- **WHEN** a bid arrives before that number of empty rounds
- **THEN** the bounty stays open as before

## MODIFIED Requirements

### Requirement: Treasury bounties
Each release SHALL make a published treasury budget available, less its matching share, for bounties on issues nobody pledges for, proposed by the treasury. No single bounty SHALL exceed a published cap. A proposal above a published threshold SHALL need a validator panel's majority. Unspent budget SHALL NOT accumulate beyond one release.

#### Scenario: Within the budget
- **WHEN** the treasury proposes bounties whose total stays within the release's budget, less its matching share
- **THEN** each is funded from the budget and opens a sealed round like a pledged one

#### Scenario: Over the budget
- **WHEN** a proposal would take the release's treasury spend over that budget
- **THEN** it is refused, and the ledger records the refusal

#### Scenario: A large proposal
- **WHEN** a proposal exceeds the approval threshold
- **THEN** it is funded only if a validator panel's majority approves it

### Requirement: Market fee and refunds
When a winner's price is escrowed, a published market fee on it SHALL be paid from the bounty, in published proportions, to the validators' pool, the author's escrow, infrastructure, insurance and the owner (within the owner's cap). The price cap SHALL leave room for the market fee and the finder's fee. Once the contribution is fully paid, the bounty's leftover SHALL return in proportion to what each source put in, the treasury's share to insurance.

#### Scenario: Fee split
- **WHEN** a price of 150 is escrowed with a market fee of 20 %
- **THEN** 30 is paid from the bounty in the published proportions, and the parts add up to 30 exactly

#### Scenario: Leftover refunded
- **WHEN** a pledged bounty of 300 pays a price of 150, a market fee of 30 and a finder's fee of 7.5, and the contribution is fully paid
- **THEN** the remaining 112.5 returns to the pledgers in proportion to their pledges

#### Scenario: Matched leftover
- **WHEN** a bounty funded by 200 of pledges and a match of 100 has 90 left once fully paid
- **THEN** 60 returns to the pledgers in proportion to their pledges, and 30 goes to insurance
