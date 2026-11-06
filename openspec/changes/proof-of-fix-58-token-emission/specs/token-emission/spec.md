# Spec Delta

## Purpose
Defines how the protocol's token is minted and shared: only by solved issues, from a fixed emission split by the AI's weight of each solved issue, so solvers and reporters earn tokens on top of coin without inflating the supply.

## ADDED Requirements

### Requirement: A fixed emission minted only by solved issues
When the emission is on, each period SHALL have a fixed emission, decreasing on a published schedule. Less any founder's share, it SHALL be minted only to the bounties that closed paid in that period, in proportion to their weights. A period in which none closes SHALL mint nothing, the founder's share included. No token SHALL be minted any other way: no sale, and no pre-mine beyond the published genesis option.

#### Scenario: Two bounties close in a period
- **WHEN** an emission of 1,000, with no founder's share, is split between two bounties that closed paid in the period, of weights 3 and 1
- **THEN** they get 750 and 250, and nothing else is minted that period

#### Scenario: Nothing closes
- **WHEN** no bounty closes paid in a period
- **THEN** nothing is minted for that period, not even the founder's share, and the next period's emission is unchanged

#### Scenario: Activity can't inflate the supply
- **WHEN** many more bounties close in a period than usual
- **THEN** the period mints the same total, shared among more

### Requirement: Minted when the bounty closes paid
A bounty's tokens SHALL be minted when it closes paid: after its challenge window and its last instalment, when clawback can no longer happen. A bounty refunded, closed unsolved, or whose fix was clawed back SHALL mint nothing for that fix. A bounty of 0 coin SHALL earn tokens like any other once it closes paid.

#### Scenario: Clawed back
- **WHEN** a winning fix is clawed back before its last instalment
- **THEN** it earns no tokens, and the bounty's eventual paid fix earns them instead

#### Scenario: Zero coin
- **WHEN** a bounty with no funds is won, its fix merged, and it closes paid
- **THEN** its solver and reporter earn its tokens, and no coin is paid

### Requirement: The AI weight
A bounty's weight SHALL be the AI registration check's estimate of the issue's importance, confirmed when its fix is merged by a second, independent estimate. The smaller of the two SHALL count. The AI sets relative weights only; the token's value is set by its market.

#### Scenario: An inflated estimate
- **WHEN** the registration check overestimates an issue's importance and the estimate at merge doesn't
- **THEN** the smaller estimate at merge is the weight

#### Scenario: Inflated beyond the tolerance
- **WHEN** the registered weight is above the published tolerance (300 %) of the estimate at merge
- **THEN** the bounty's reporters forfeit their finder's fee, returned to its funders, and their tokens, minted to its solver; their stake comes back

### Requirement: Shares of a bounty's tokens
A bounty's tokens SHALL be shared between its solver and its reporter: the reporter SHALL get a published share (by default the same as its share of the coin payout, 15 %), and a bundle's reporters SHALL share it. The rest SHALL go to the solver.

#### Scenario: The split
- **WHEN** a bounty earns 1,000 tokens at the default shares
- **THEN** its reporter gets 150 and its solver 850

### Requirement: The owner's founder's share
At launch the founder's share and genesis SHALL be zero (owner, 2026-11-03). The owner MAY otherwise get a published share of each period's emission, for a published number of periods, and an optional genesis amount. They SHALL be within the owner's published cap, fixed in advance, and give no vote, validator weight or say over any payout. The owner SHALL earn tokens otherwise only by solving or reporting, under the same rules as anyone.

#### Scenario: A fair launch
- **WHEN** the token parameters are published for launch
- **THEN** the founder's share and the genesis are zero, and the owner's tokens come only from bounties they solve or report, under the same rules as anyone

#### Scenario: Above the cap
- **WHEN** parameters are published with a founder's share above the owner's cap
- **THEN** they are refused

#### Scenario: The share ends
- **WHEN** the published number of periods has passed
- **THEN** the founder's share stops, and the whole emission goes to solved bounties
