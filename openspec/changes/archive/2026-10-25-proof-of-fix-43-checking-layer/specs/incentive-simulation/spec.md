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
- **THEN** every credit that left a pledge either paid an accepted contribution's instalments, paid the market fee on one, paid an oracle fee for a check on one of its deliveries, or was refunded

#### Scenario: Treasury flood
- **WHEN** the treasury is flooded with junk proposals
- **THEN** its spend per release never exceeds the budget, and proposals above the threshold need a panel

#### Scenario: Enforcement still holds
- **WHEN** defective solutions, griefers and a self-interested owner act in the market mode
- **THEN** attacking kinds lose money on defective work significantly, griefers lose money, and the owner can't gain by defecting

## ADDED Requirements

### Requirement: Checking scenarios
The market simulation SHALL run checking through actors instead of fixed odds: attested runners (with a published chance of a compromised enclave) and AI evaluators with accuracy per model family and errors correlated within and across families. It SHALL provide a runner forging results, a herding evaluator, a copy operator, a solver crafting fixes against one family, a bug planter, a checker with a hidden bidding identity, and a half-fixer.

#### Scenario: CI by validators, as a comparison
- **WHEN** the same seeds run with staked validators re-running the public tests and the system's runner running the hidden ones
- **THEN** the report gives the change in defects caught, honest solvers' returns and funders' cost per paid bounty against attested runners

#### Scenario: Correlated errors
- **WHEN** a hard case comes up and the correlation within a family is above zero
- **THEN** evaluators of the same family are more likely to err together than evaluators of different families

#### Scenario: Fresh rounds against the queue
- **WHEN** the same seeds run with failed attempts reopening a fresh round, and with the next queued bid taking the job
- **THEN** the report gives the change in funders' cost per paid bounty, mean price, pledged bounties paid, days to fix, and honest solvers' returns

#### Scenario: Half-fixing with and without the challenge
- **WHEN** the half-fixer runs with "not solved" challenges, and on the same seeds without them
- **THEN** the report gives its return against the same solver fixing honestly, under both rules

#### Scenario: Herding under agreement scoring
- **WHEN** evaluators are scored on agreement with the majority instead of the truth, as a comparison
- **THEN** the report gives the herding evaluator's return under both rules, on the same seeds

### Requirement: Acceptance criteria for the checking layer
The checking layer SHALL be considered sound only if, over the published seeds with two standard errors: honest runners and evaluators earn; the forging runner, herding evaluator, copy operator, crafting solver, bug planter and half-fixer lose; the hidden bidder doesn't gain; the defects caught before beta, at the default correlation, are at least those under the fixed-odds assumption; and every earlier market criterion still holds.

#### Scenario: Attacks lose
- **WHEN** each attacker's scenario runs, and on the same seeds the same actor behaves honestly
- **THEN** the attacker's return, its effort counted, is significantly lower

#### Scenario: Detection holds under correlation
- **WHEN** the base scenario runs at the published correlations
- **THEN** the share of defective deliveries caught before beta is at least the share under fixed odds, on the same seeds

#### Scenario: Correlation sweep
- **WHEN** the correlation within a family is swept
- **THEN** the report gives the share caught before beta, and the attackers' returns, at each value
