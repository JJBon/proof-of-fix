# Spec Delta

## MODIFIED Requirements

### Requirement: Acceptance criteria for the market
The market mode SHALL be considered sound only if, over the published seeds (means with two standard errors):
- honest solvers earn more than their cost;
- bluffing and lowballing gain nothing against bidding one's cost;
- no-shows and spam solvers lose money;
- colluding bidders gain nothing below a measured ring size;
- treasury spend stays within budget under a flood;
- the enforcement criteria still hold.

#### Scenario: Bidding your cost is best
- **WHEN** a solver bids above or below its cost, and on the same seed bids its cost
- **THEN** its return from misreporting is not significantly higher than from bidding its cost

#### Scenario: No-shows and spam lose
- **WHEN** no-shows win jobs with low bids and never deliver, and spam solvers win jobs and deliver untested solutions
- **THEN** each kind's return, its effort counted, is significantly negative

#### Scenario: Only the assigned solver builds
- **WHEN** a market run finishes
- **THEN** the report gives the solvers' total effort, and only assigned solvers spent any

#### Scenario: Collusion measured
- **WHEN** a ring of bidders coordinates (only one member bids low, the others stay out or bid high) at growing ring sizes, against the same solvers competing on the same seeds
- **THEN** the report gives the ring's gain at each size, and the smallest size at which it's significantly positive

#### Scenario: Pledges pay only for released fixes
- **WHEN** a market run finishes
- **THEN** every credit that left a pledge either paid an accepted contribution's instalments, paid the market fee on one, or was refunded; no pledged credit pays for checks

#### Scenario: Treasury flood
- **WHEN** the treasury is flooded with junk proposals
- **THEN** its spend per release never exceeds the budget, and proposals above the threshold need a panel

#### Scenario: Enforcement still holds
- **WHEN** defective solutions, griefers and a self-interested owner act in the market mode
- **THEN** attacking kinds lose money on defective work significantly, griefers lose money, and the owner can't gain by defecting

## ADDED Requirements

### Requirement: The contributor pays for its checks: scenarios and criteria
The market simulation SHALL price each solver's expected check costs into its break-even, SHALL provide a split farmer that delivers borderline junk meant to split the jury, and SHALL compare, on the same seeds, the solver paying its checks with the bounty paying them. The split farmer SHALL lose significantly against its honest twin, and every earlier criterion SHALL still hold or be named.

#### Scenario: The split farmer loses
- **WHEN** the split farmer runs, and on the same seeds the same solver fixes honestly
- **THEN** its return, its effort and checks counted, is significantly lower

#### Scenario: Who pays the checks
- **WHEN** the same seeds run with the solver paying its checks and with the bounty paying them
- **THEN** the report gives the change in funders' cost per paid bounty, mean price, bounties paid, and honest solvers' returns
