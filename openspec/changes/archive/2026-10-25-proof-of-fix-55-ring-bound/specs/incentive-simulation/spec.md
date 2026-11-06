# Spec Delta

## MODIFIED Requirements

### Requirement: Acceptance criteria for collusion and risk pricing
The market mode SHALL be considered sound only if, over the published seeds with two standard errors: every ring of up to six colluding solvers has a gain, against the same solvers competing, whose upper bound (mean plus two standard errors) per member is below the published ring tolerance, judged on the published attack seeds; bidding one's cost is best at every published hunting elasticity; and every earlier market criterion still holds.

#### Scenario: No ring gains
- **WHEN** rings of 2, 3, 4 and 6 solvers run on the attack seeds, and on the same seeds the same solvers compete
- **THEN** each ring's gain per member, plus two standard errors, is below the ring tolerance, and the report gives each ring's gain, its standard error and its upper bound

#### Scenario: Bidding your cost is best at every elasticity
- **WHEN** the bluffing scenario runs at hunting elasticity 0, 0.5 and 1
- **THEN** bluffing and lowballing gain nothing significant at any of them

#### Scenario: Unsolved bounties reported
- **WHEN** the reserve sweep runs
- **THEN** the report gives, per reserve, the bounties paid and those closed unsolved

### Requirement: Acceptance criteria for the checking layer
The checking layer SHALL be sound only if, over the published seeds with two standard errors: honest runners and evaluators earn; the forging runner, herder, copy operator, crafter, bug planter and half-fixer lose; the hidden bidder's gain per account plus two standard errors is below the ring tolerance on the attack seeds; defects caught before beta at the default correlation are at least those under fixed odds; and every earlier market criterion holds.

#### Scenario: Attacks lose
- **WHEN** each attacker's scenario runs, and on the same seeds the same actor behaves honestly
- **THEN** the attacker's return, its effort counted, is significantly lower

#### Scenario: Detection holds under correlation
- **WHEN** the base scenario runs at the published correlations
- **THEN** the share of defective deliveries caught before beta is at least the share under fixed odds, on the same seeds

#### Scenario: Correlation sweep
- **WHEN** the correlation within a family is swept
- **THEN** the report gives the share caught before beta, and the attackers' returns, at each value

## ADDED Requirements

### Requirement: Common random numbers for paired comparisons
In the market simulation, each solver's own decisions (when it looks for work, its build days, its defects and incomplete fixes, its checks and reveals) SHALL draw from its own random stream, seeded by the run's seed and the solver's name. Market-level draws SHALL keep the world's stream. So an attacker and its honest twin share the rest of the market's path.

#### Scenario: A ring doesn't shift the others
- **WHEN** a ring and its honest twin run on the same seed
- **THEN** a solver outside the ring that makes the same decisions in both runs draws the same random numbers for them

#### Scenario: Same seed, same result
- **WHEN** a scenario is run twice with the same parameters and seed
- **THEN** both runs produce identical ledgers and reports

### Requirement: Attack seeds and the ring tolerance
The acceptance run SHALL judge rings and the hidden bidder on a published number of attack seeds, separate from the seeds used for the other verdicts. The ring tolerance SHALL be published as a share of an honest solver's mean net per run on the same run's seeds. If a bound fails, the report SHALL name the attack, its gain, its standard error and its upper bound.

#### Scenario: A bound that fails is named
- **WHEN** a ring's gain per member plus two standard errors reaches the tolerance
- **THEN** the run fails "no ring gains", naming the ring size, its gain, its standard error and its upper bound

#### Scenario: Identity on the go-live checklist
- **WHEN** every ring and the hidden bidder stay below the tolerance
- **THEN** the report says so, and the #15 checklist can drop identity on the owner's decision
