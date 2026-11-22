# bounty-market Specification

## Purpose
Defines how fixes are priced and paid by a market: issues become bounties funded by pledges or a capped treasury, solvers bid for the job in sealed second-price rounds before building anything, and the assigned solver is paid on release through the contribution lifecycle.

## ADDED Requirements

### Requirement: Bounties and pledges
An issue SHALL become a bounty with a published definition of solved and a target amount. Users SHALL pledge toward the target until a published deadline. If the target isn't reached by then, every pledge SHALL be refunded in full.

#### Scenario: Target reached
- **WHEN** pledges reach a bounty's target before its deadline
- **THEN** the bounty opens a sealed round, and the pledges are held in the bounty's escrow

#### Scenario: Target missed
- **WHEN** a bounty's deadline passes below its target
- **THEN** every pledge returns to its pledger, and nothing else moves

### Requirement: Treasury bounties
Each release SHALL make a published treasury budget available for bounties on issues nobody pledges for, proposed by the treasury. No single bounty SHALL exceed a published cap. A proposal above a published threshold SHALL need a validator panel's majority. Unspent budget SHALL NOT accumulate beyond one release.

#### Scenario: Within the budget
- **WHEN** the treasury proposes bounties whose total stays within the release's budget
- **THEN** each is funded from the budget and opens a sealed round like a pledged one

#### Scenario: Over the budget
- **WHEN** a proposal would take the release's treasury spend over the budget
- **THEN** it is refused, and the ledger records the refusal

#### Scenario: A large proposal
- **WHEN** a proposal exceeds the approval threshold
- **THEN** it is funded only if a validator panel's majority approves it

### Requirement: Sealed rounds for the job
A solver SHALL bid for the job, before building anything, by committing a sealed price at most the bounty's price cap. It SHALL post a stake (a published share of the cap, times the risk multiplier) and a fixed evaluation fee. After the deadline, every bidder SHALL reveal its price. A bid that isn't revealed or doesn't match its commitment SHALL forfeit its fee.

#### Scenario: Bid accepted
- **WHEN** a solver commits a sealed price before the deadline, with enough balance for the stake and fee
- **THEN** the stake and fee are locked, and no one can see the price

#### Scenario: Nothing to copy
- **WHEN** a round's bids are revealed
- **THEN** only prices are revealed: no solution exists yet, so no one can copy one

#### Scenario: Reveal doesn't match
- **WHEN** a bidder's reveal doesn't match its commitment, or it doesn't reveal
- **THEN** its fee is forfeited to the checking costs, its stake returns, and it can't be assigned the job

### Requirement: Assignment and price
The cheapest revealed bid SHALL be assigned the job, at the second-lowest revealed price, or at the price cap when it's the only bid. Its stake SHALL stay locked as a performance bond. Every other bid's stake and fee SHALL return, and the bids SHALL stay queued in price order as runners-up. A round without a valid bid SHALL be followed by a new round.

#### Scenario: Second price
- **WHEN** three bids reveal at prices 100, 150 and 200
- **THEN** the bid at 100 is assigned the job at 150, and the other two get their stakes and fees back

#### Scenario: Only one bid
- **WHEN** only one bid is revealed
- **THEN** it is assigned at the price cap

#### Scenario: No bid
- **WHEN** no bid is revealed
- **THEN** no one is assigned, the bounty's funds stay, and a new round opens

### Requirement: Delivery
The assigned solver SHALL deliver a solution within a published number of days. A delivery that passes the deterministic gate SHALL become the winning contribution, and the bond and fee SHALL be released. A failed or late delivery SHALL forfeit the bond to the bounty and the fee to the checking costs, and the next queued bid SHALL be offered the job, at the next queued price or the cap, if it posts its stake again.

#### Scenario: Delivered in time
- **WHEN** the assigned solver delivers a solution that passes the gate before its deadline
- **THEN** the solution becomes a contribution with the bond as its stake, and its fee is refunded

#### Scenario: Not delivered
- **WHEN** the deadline passes without a passing delivery
- **THEN** the bond goes to the bounty, the fee goes to the checking costs, and the next queued bid is offered the job

#### Scenario: Runner-up can't post its stake
- **WHEN** the next queued bidder can't post its stake again
- **THEN** it is skipped, and the job is offered to the one after it, or a new round opens

### Requirement: Payment through the lifecycle
The winning contribution SHALL take the assigned price as its reward, escrowed from the bounty, and follow the lifecycle: the next beta build, the challenge window, and instalments with clawback. If it is slashed or clawed back, the forfeited escrow SHALL return to the bounty, and the next queued bid SHALL be offered the job as for a failed delivery.

#### Scenario: Paid on release
- **WHEN** the winning contribution is accepted and its instalments are paid
- **THEN** the solver receives its price over the instalments, and its stake returns with the last one

#### Scenario: Winner slashed
- **WHEN** the winning contribution is slashed in its window
- **THEN** the escrow returns to the bounty in full, the stake is slashed by severity, and the next queued bid is offered the job

### Requirement: Market fee and refunds
When a winner's price is escrowed, a published market fee on that price SHALL be paid from the bounty to the validators' pool, the upstream author's escrow, infrastructure, insurance and the owner, in published proportions; the owner's part SHALL stay within its published cap. The bounty's price cap SHALL leave room for the fee. Once the winner's contribution is fully paid, what remains of the bounty SHALL return to its pledgers, pro rata, or to insurance.

#### Scenario: Fee split
- **WHEN** a price of 150 is escrowed with a market fee of 20 %
- **THEN** 30 is paid from the bounty in the published proportions, and the parts add up to 30 exactly

#### Scenario: Leftover refunded
- **WHEN** a bounty of 300 pays a price of 150 and a fee of 30, and the contribution is fully paid
- **THEN** the remaining 120 returns to the pledgers in proportion to their pledges
