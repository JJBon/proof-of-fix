# Spec Delta

## MODIFIED Requirements

### Requirement: Assignment and price
The cheapest revealed bid SHALL be assigned the job, at the second-lowest revealed price, or at the bounty's reserve price (a published share of its price cap) when it's the only bid, and never above the reserve. Its stake SHALL stay locked as a performance bond. Every other bid's stake and fee SHALL return, and the bids SHALL stay queued in price order as runners-up. A round without a valid bid SHALL be followed by a new round.

#### Scenario: Second price
- **WHEN** three bids reveal at prices 100, 150 and 200, all within the reserve
- **THEN** the bid at 100 is assigned the job at 150, and the other two get their stakes and fees back

#### Scenario: Only one bid
- **WHEN** only one bid is revealed
- **THEN** it is assigned at the reserve price, not the price cap

#### Scenario: No bid
- **WHEN** no bid is revealed
- **THEN** no one is assigned, the bounty's funds stay, and a new round opens

### Requirement: Sealed rounds for the job
A solver SHALL bid for the job, before building anything, by committing a sealed price at most the bounty's reserve price. It SHALL post a stake, a published share of the cap times the risk multiplier, lowered by its solver trust down to a published share of that, and a fixed evaluation fee. After the deadline, every bidder SHALL reveal its price. A bid that isn't revealed, doesn't match its commitment, or is above the reserve SHALL forfeit its fee.

#### Scenario: Bid accepted
- **WHEN** a solver commits a sealed price before the deadline, with enough balance for the stake and fee
- **THEN** the stake and fee are locked, and no one can see the price

#### Scenario: A proven solver's bond
- **WHEN** a solver with full trust bids
- **THEN** its stake is the published share of the full stake, while a newcomer's is the full stake

#### Scenario: Above the reserve
- **WHEN** a revealed price is above the bounty's reserve
- **THEN** the bid is void, and its fee is forfeited

#### Scenario: Nothing to copy
- **WHEN** a round's bids are revealed
- **THEN** only prices are revealed: no solution exists yet, so no one can copy one

#### Scenario: Reveal doesn't match
- **WHEN** a bidder's reveal doesn't match its commitment, or it doesn't reveal
- **THEN** its fee is forfeited to the checking costs, its stake returns, and it can't be assigned the job
