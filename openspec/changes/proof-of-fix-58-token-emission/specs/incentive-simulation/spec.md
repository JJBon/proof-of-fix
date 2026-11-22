# Spec Delta

## ADDED Requirements

### Requirement: Token emission: scenarios and criteria
The market simulation SHALL run the token emission, off by default, at a sweep of assumed token prices (0 included), with bounties of 0 coin and solvers pricing tokens. It SHALL provide a self-funding coder, an importance inflater, a thin launch and a defecting owner. With the emission on, every earlier criterion SHALL hold at each swept price or be named; the owner SHALL NOT gain by defecting, and its share of the supply SHALL stay below a published cap.

#### Scenario: Default runs unchanged
- **WHEN** the default and earlier runs are repeated with the emission off
- **THEN** their reports are identical to before

#### Scenario: Tokens follow weighted work
- **WHEN** the token market runs
- **THEN** the report gives each kind's share of the tokens against its share of the weight of the bounties it solved or reported, and every bounty's tokens are its period's emission times its share of that period's weight

#### Scenario: Zero-coin bounties solved
- **WHEN** the token market runs at each swept token price
- **THEN** the report gives the share of 0-coin bounties fixed, honest solvers' earnings, funders' cost per fix and bounties fixed, against the run without tokens

#### Scenario: The self-funding coder
- **WHEN** a coder registers and solves its own issues for tokens, and on the same seeds the same accounts solve others' bounties
- **THEN** the report gives its tokens and earnings per unit of its work in both runs

#### Scenario: An AI weight error
- **WHEN** an importance inflater's registrations are overestimated by a published bias that the check at merge catches only at its measured accuracy
- **THEN** the report gives its extra tokens per unit of true weight, against its honest twin; it's a figure, not a pass/fail criterion

#### Scenario: A thin launch
- **WHEN** few solvers race, one of them the owner as a self-funding coder
- **THEN** the report gives the owner's share of the supply over the periods, with the founder's share, with the genesis option, and with both

#### Scenario: The owner defects
- **WHEN** the owner acts against contributors with the founder's share (the self-interested owner)
- **THEN** its coin and tokens together, at each swept token price, aren't significantly higher than the honest owner's

## MODIFIED Requirements

### Requirement: Acceptance criteria for collusion and risk pricing
The market mode SHALL be considered sound only if, over the published seeds with two standard errors, no ring of up to six colluding solvers both gains and lowers outsiders' earnings or raises funders' cost per paid bounty, against the same solvers competing; bidding one's cost is best at every published hunting elasticity; and every earlier market criterion still holds. Each ring's gain and costs are reported.

#### Scenario: No ring gains
- **WHEN** rings of 2, 3, 4 and 6 solvers run, and on the same seeds the same solvers compete
- **THEN** no ring gains at others' expense: none both gains significantly and significantly lowers the outsiders' earnings or raises funders' cost per paid bounty, and the report gives each ring's gain and both costs

#### Scenario: Bidding your cost is best at every elasticity
- **WHEN** the bluffing scenario runs at hunting elasticity 0, 0.5 and 1
- **THEN** bluffing and lowballing gain nothing significant at any of them

#### Scenario: Unsolved bounties reported
- **WHEN** the reserve sweep runs
- **THEN** the report gives, per reserve, the bounties paid and those closed unsolved
