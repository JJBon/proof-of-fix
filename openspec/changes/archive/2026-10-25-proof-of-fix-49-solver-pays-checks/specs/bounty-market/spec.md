# Spec Delta

## MODIFIED Requirements

### Requirement: Sealed rounds for the job
A solver SHALL bid for the job, before building anything, by committing a sealed price at most the bounty's reserve price. It SHALL post a stake, a published share of the cap times the risk multiplier, lowered by its trust down to a published share of that, and a check deposit (the oracle reserve). After the deadline, every bidder SHALL reveal its price. A bid that isn't revealed, doesn't match its commitment, or is above the reserve SHALL forfeit the published evaluation fee from its deposit.

#### Scenario: Bid accepted
- **WHEN** a solver commits a sealed price before the deadline, with enough balance for the stake and the check deposit
- **THEN** the stake and deposit are locked, and no one can see the price

#### Scenario: A proven solver's bond
- **WHEN** a solver with full trust bids
- **THEN** its stake is the published share of the full stake, while a newcomer's is the full stake

#### Scenario: Above the reserve
- **WHEN** a revealed price is above the bounty's reserve
- **THEN** the bid is void, its evaluation fee is forfeited, and the rest of its deposit returns

#### Scenario: Nothing to copy
- **WHEN** a round's bids are revealed
- **THEN** only prices are revealed: no solution exists yet, so no one can copy one

#### Scenario: Reveal doesn't match
- **WHEN** a bidder's reveal doesn't match its commitment, or it doesn't reveal
- **THEN** its evaluation fee is forfeited to the checking costs, its stake and the rest of its deposit return, and it can't be assigned the job

### Requirement: Assignment and price
The cheapest revealed bid SHALL be assigned the job, at the second-lowest revealed price, or at the bounty's reserve price (a published share of its price cap) when it's the only bid, and never above the reserve. Its stake SHALL stay locked as a performance bond, and its deposit for its checks. Every other bid's stake and deposit SHALL return, and the bids SHALL stay queued in price order as runners-up. A round without a valid bid SHALL be followed by a new round.

#### Scenario: Second price
- **WHEN** three bids reveal at prices 100, 150 and 200, all within the reserve
- **THEN** the bid at 100 is assigned the job at 150, and the other two get their stakes and deposits back

#### Scenario: Only one bid
- **WHEN** only one bid is revealed
- **THEN** it is assigned at the reserve price, not the price cap

#### Scenario: No bid
- **WHEN** no bid is revealed
- **THEN** no one is assigned, the bounty's funds stay, and a new round opens

### Requirement: Delivery
The assigned solver SHALL deliver within a published number of days. Its checks SHALL be paid from its deposit, and the unused part SHALL return. A delivery whose attested runs pass and that the jury accepts SHALL become the winning contribution, and the bond SHALL be released. A failed, rejected or late delivery SHALL forfeit the bond to the bounty; a late one, with no checks run, its evaluation fee too, and SHALL offer the job to the next queued bid if it posts its stake and deposit.

#### Scenario: Delivered in time
- **WHEN** the assigned solver delivers before its deadline, its attested runs pass and the jury accepts it
- **THEN** the solution becomes a contribution with the bond as its stake, its checks are paid from its deposit, and the rest returns

#### Scenario: Rejected by the jury
- **WHEN** a delivery passes its attested runs, but the jury rejects it unanimously
- **THEN** the bond goes to the bounty, the deposit pays for the checks that ran, the attempt is published, and a fresh round opens

#### Scenario: Not delivered
- **WHEN** the deadline passes without a passing delivery
- **THEN** the bond goes to the bounty, the evaluation fee goes to the checking costs, the rest of the deposit returns, and the next queued bid is offered the job

#### Scenario: Runner-up can't post its stake
- **WHEN** the next queued bidder can't post its stake and deposit again
- **THEN** it is skipped, and the job is offered to the one after it, or a new round opens

### Requirement: A split rejection keeps the bond
A delivery that passes its attested runs, splits its first jury and is rejected by the second, or whose runners never agree, SHALL get its bond back. Its deposit SHALL pay for the checks that ran, the attempt SHALL be published and the bounty SHALL reopen. A clear failure, a missing or late delivery, failing tests or a unanimous rejection, SHALL still forfeit the bond.

#### Scenario: Rejected on a split
- **WHEN** the first jury splits and the second rejects the delivery
- **THEN** the solver gets its bond back, its deposit pays both juries and the runners, and it can bid again in the fresh round

## REMOVED Requirements

### Requirement: Oracle fees
**Reason**: The bounty paid every check, so a party could make the funders pay for its repeated junk attempts. The contributor pays now (proof-of-fix#49).
**Migration**: Replaced by "Checks paid by the contributor": the same fees, paid from the assigned solver's check deposit; the bounty's price cap and minimum target no longer reserve them.

## ADDED Requirements

### Requirement: Checks paid by the contributor
Every check run on a delivery SHALL be paid from the assigned solver's check deposit, never from the bounty: a published run fee to each attested runner whose result stands, and a published verdict fee to each counted verdict on either jury. The deposit SHALL be the oracle reserve, the fees for one full attempt's checks. Whether a bounty is worth bidding on, checks included, SHALL be the solver's judgement.

#### Scenario: The solver pays its checks
- **WHEN** a delivery's tests run on the attested runners and two juries judge it
- **THEN** each runner whose result stands and each juror with a counted verdict is paid its fee from the solver's deposit, and the bounty pays nothing for them

#### Scenario: Splitting the jury costs the splitter
- **WHEN** a solver delivers junk that splits the first jury, is rejected by the second, and gets its bond back
- **THEN** it has paid every check from its deposit, so repeating the attempt costs it the checks each time

#### Scenario: No room needed in the price
- **WHEN** a bounty holds 300
- **THEN** its price cap is computed on all 300, as before oracle fees
