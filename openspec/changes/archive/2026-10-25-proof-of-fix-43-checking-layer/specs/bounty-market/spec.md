# Spec Delta

## MODIFIED Requirements

### Requirement: Delivery
The assigned solver SHALL deliver within a published number of days. A delivery whose attested runs pass and that the jury accepts SHALL become the winning contribution, and the bond and fee SHALL be released. A failed, rejected or late delivery SHALL forfeit the bond to the bounty and the fee to the checking costs. A late one SHALL offer the job to the next queued bid, at its queued price or the reserve, if it posts its stake again.

#### Scenario: Delivered in time
- **WHEN** the assigned solver delivers before its deadline, its attested runs pass and the jury accepts it
- **THEN** the solution becomes a contribution with the bond as its stake, and its fee is refunded

#### Scenario: Rejected by the jury
- **WHEN** a delivery passes its attested runs, but the jury rejects it unanimously
- **THEN** the bond goes to the bounty, the fee to the checking costs, the attempt is published, and a fresh round opens

#### Scenario: Not delivered
- **WHEN** the deadline passes without a passing delivery
- **THEN** the bond goes to the bounty, the fee goes to the checking costs, and the next queued bid is offered the job

#### Scenario: Runner-up can't post its stake
- **WHEN** the next queued bidder can't post its stake again
- **THEN** it is skipped, and the job is offered to the one after it, or a new round opens

### Requirement: Payment through the lifecycle
The winning contribution SHALL take the assigned price as its reward, escrowed from the bounty, and follow the lifecycle: the next beta build, the challenge window, and instalments with clawback. If it is slashed or clawed back, the forfeited escrow SHALL return to the bounty, which SHALL reopen as for a failed attempt.

#### Scenario: Paid on release
- **WHEN** the winning contribution is accepted and its instalments are paid
- **THEN** the solver receives its price over the instalments, and its stake returns with the last one

#### Scenario: Winner slashed
- **WHEN** the winning contribution is slashed in its window
- **THEN** the escrow returns to the bounty in full, the stake is slashed by severity, and a fresh round opens with the contribution public

## ADDED Requirements

### Requirement: Failed attempts are published
A delivered attempt that fails its checks or its jury, or a winning contribution slashed or clawed back, SHALL be published to every bidder. The bounty's queued bids SHALL be released, and a fresh sealed round SHALL open, in which anyone, including the solver who failed, can bid on the work that's left.

#### Scenario: Everyone sees the attempt
- **WHEN** a delivered attempt fails and the bounty reopens
- **THEN** every bidder in the fresh round can see the attempt, and no one's earlier queued price stands

#### Scenario: A sock gains nothing from seeing it
- **WHEN** a runner that ran a failed attempt also bids, under another identity, in the fresh round
- **THEN** it knows nothing about the attempt that the other bidders don't

### Requirement: Unsolved cases join the definition
When a "not solved" challenge against a bounty's winning contribution is upheld, its failing case SHALL be added to the bounty's public definition of solved, recorded on the ledger, and the bounty SHALL reopen as for a failed attempt.

#### Scenario: A case added
- **WHEN** a "not solved" challenge is upheld
- **THEN** the bounty reopens with the case in its public definition, and the next attempt must pass it

### Requirement: A split rejection keeps the bond
A delivery that passes its attested runs, splits its first jury and is rejected by the second SHALL get its bond back. Its fee SHALL pay for the checks, the attempt SHALL be published and the bounty SHALL reopen. A clear failure, a missing or late delivery, failing tests or a unanimous rejection, SHALL still forfeit the bond.

#### Scenario: Rejected on a split
- **WHEN** the first jury splits and the second rejects the delivery
- **THEN** the solver gets its bond back, loses its fee, and can bid again in the fresh round

### Requirement: Oracle fees
Every check run on a bounty's delivery SHALL be paid from the bounty: a published run fee to each attested runner whose result stands, and a published verdict fee to each counted verdict on either jury. A bounty's target SHALL exceed the oracle reserve, the fees for one full attempt's checks, and its price cap SHALL leave room for it.

#### Scenario: The bounty pays its checks
- **WHEN** a delivery's tests run on the attested runners and two juries judge it
- **THEN** each runner whose result stands and each juror with a counted verdict is paid its fee from the bounty, whatever the outcome

#### Scenario: Too small to check
- **WHEN** a bounty is opened with a target at or below the oracle reserve
- **THEN** it is refused

#### Scenario: Room in the price
- **WHEN** a bounty holds 300
- **THEN** its price cap is computed on 300 less the oracle reserve
