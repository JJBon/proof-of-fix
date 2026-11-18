# Spec Delta

## ADDED Requirements

### Requirement: Open-validator mechanics in the simulation
The simulation SHALL model open registration with bonds, qualification as a shadow judge, unbonding, the odd panel size k from eligible validators and the bounty, the challenge window by k, the hold on k = 1 verdicts, and the per-panel caps, on a network that grows from one validator.

#### Scenario: Growth from one validator
- **WHEN** a run starts with one validator and validators join at a published rate
- **THEN** the report gives, over time, k, the largest bounty that can be judged, the waiting submissions, the newcomers qualified, and the days from a k = 1 verdict to its payment

### Requirement: Open-validator attackers
The simulation SHALL provide a party running many validators (a sybil), a lone validator colluding with a solver, a seed grinder, a bribed judge that goes silent and one that seals and then withholds its reveal, a fee farmer registering idle validators, and a coalition aiming at the constitution tier while the network is small, with adding ADRs and with removals.

#### Scenario: Attacks lose
- **WHEN** each attacker's scenario runs, and on the same seeds the same actor behaves honestly
- **THEN** the report gives the attacker's return, with its bonds, fees and running costs counted, beside its honest twin's

### Requirement: The k table and the windows compared
The simulation SHALL compare the published k table with a fixed k of 3: every bounty up to $625, k = 3's 24-hour window and a challenge panel of 5. It SHALL vary k = 1's challenge window over the published range: 7, 14 and 30 days.

#### Scenario: The k table compared
- **WHEN** the same seeds run with the published k table and with a fixed k of 3
- **THEN** the report gives, for each, the bad fixes merged, the days to final verdict, the share of submissions that wait, the cost per paid fix and each validator's net per month

#### Scenario: The window's length
- **WHEN** k = 1's challenge window is varied over the published range
- **THEN** the report gives, for each, the colluding lone validator's return beside its twin's and the share of its bad fixes reversed before payment

### Requirement: Market pricing in the simulation
The simulation SHALL model the median of posted cost tables and the queue-driven service fee, counting every wait, with validators that join or leave by their expected net. It SHALL provide a cartel that refuses work to fake a shortage, a spammer faking demand, and validators posting inflated costs.

#### Scenario: The fee finds the validators' cost
- **WHEN** a run starts with the service fee at its ceiling and validators enter and leave freely
- **THEN** the report gives the fee over time and how far it settles from validators' average (break-even) cost, beside their marginal cost

#### Scenario: Pricing attacks
- **WHEN** the cartel, the spammer and the inflating validators each run alone
- **THEN** the report gives how far each moves the prices and its return beside its honest twin's

### Requirement: Proof levels in the simulation
The simulation SHALL model validators at proof levels A, B and C, and panels whose limits and windows follow their level. It SHALL provide a level C validator that lies about its test results, a level C validator that calls the model several times and keeps the answer it prefers, and a level B validator that breaks its own chip to sign verdicts outside the official code.

#### Scenario: A level C validator lies about the tests
- **WHEN** a level C validator reports test results it didn't get
- **THEN** the report gives how often a re-run challenge catches it and its return beside its honest twin's

#### Scenario: Answer shopping
- **WHEN** a level C validator retries the model until it gets the verdict it wants on borderline fixes that fool an honest call 1 time in 10, and again at 3 in 10
- **THEN** the report gives, for each rate, how many verdicts it flips, how often the other judges, the audits and the family scores outweigh it, and its return beside its honest twin's

#### Scenario: A validator breaks its own chip
- **WHEN** a level B validator signs bad verdicts outside the official code at a published share of its draws
- **THEN** the report gives what it gains within level B's bounty limits, how often challenges catch it, and its return with its bond counted

### Requirement: Audits in the simulation
The simulation SHALL model random audits at a published share of submissions, with and without volunteer challengers, and SHALL vary the share over the published range: 0, 1, 2, 5, 10 and 20 %.

#### Scenario: The watcher's dilemma
- **WHEN** cheating is rare and no volunteer challenges
- **THEN** the report gives, for each audit share, how often cheating is caught, whether cheating pays, and what audits cost per check

### Requirement: Scores and weighting compared
The simulation SHALL model per-family scores from agreement with final outcomes on counted verdicts, balanced over passed and failed outcomes, the minimum score, recovery by fresh blocks of shadow verdicts, the neutral start and the normalised fee factor, and SHALL compare one vote per judge with pay by score against votes weighted by score. It SHALL include validators that all move to the top-scoring family, and judges that try to guess the majority instead of judging.

#### Scenario: One vote, pay by score, weighted votes
- **WHEN** the same seeds run with one vote per judge, with pay scaled by score, and with votes weighted by score
- **THEN** the report gives, for each, the bad fixes merged, the share of panels decided by one family, the service fees per submission, and each family's validators' net per month

#### Scenario: Everyone moves to the top model
- **WHEN** validators switch to the top-scoring family whenever it pays more, registering again to do so
- **THEN** the report gives how far the per-family caps keep panels diverse, the share of submissions that wait, and whether the market settles with several families

#### Scenario: Herding
- **WHEN** some judges vote what they expect the majority to vote rather than what they find, as counted judges and as shadows
- **THEN** the report gives, with the balanced score and with plain agreement, whether that raises their family's score or shortens its time barred, and the bad fixes merged with and without them

#### Scenario: Recovery by chance
- **WHEN** a family right 68 % of the time is barred
- **THEN** the report gives how many times a year it recovers, by fresh blocks and by round 1's test of its last 50 shadow verdicts at each new one

### Requirement: Measured judges in the simulation
The simulation SHALL run with judges that vote as measured models did on labelled fixes, beside the assumed judges, on the same seeds, and SHALL re-run on them every attacker counted by the acceptance criteria. Every rate the judge measurement did not supply SHALL be named as assumed and swept.

#### Scenario: Assumed against measured
- **WHEN** the same seeds run with the assumed judges and with the measured ones
- **THEN** the report gives, for each, the bad fixes merged per 100 paid, the good fixes rejected, the submissions that waited, each family's score beside its score on known answers, and each attacker's return against its twin

#### Scenario: An assumed rate
- **WHEN** a result depends on how often a failing test is found or a wrong test accepted
- **THEN** the report gives the result across the swept range and says the rate is assumed

### Requirement: Seats, disputes, deposits and appeals in the simulation
On the measured judges the simulation SHALL model seats by rank, disputes backed by a failing test, the solver's deposit and the appeal, each as a switch beside v3's rule. It SHALL include a solver that only submits bad fixes, a solver that appeals every rejection, and a party that disputes without evidence.

#### Scenario: The new attackers
- **WHEN** each of the three runs against a twin that does nothing, on the same seeds
- **THEN** the report gives its return and says whether it is shown to gain

### Requirement: The appeal on evidence in the simulation
On the measured judges the simulation SHALL model, each as a switch beside the rule it replaces: the appeal on evidence decided by the seated families, a contender's sponsorship, known-answer issues, and the second draw among few families. The two rates the judge measurement can't supply, how often the panel passes a good fix and a bad fix appealed with a passing test, SHALL be named as assumed and swept.

#### Scenario: The two assumed rates
- **WHEN** a result depends on how a judge reacts to a passing test
- **THEN** the report gives it across the swept range, says the rate is assumed, and gives the rate above which a solver of bad fixes gains by appealing

#### Scenario: The attackers of the appeal
- **WHEN** a solver appeals every rejection with a test it wrote, a contender sponsors every rejection, and a solver tries one issue again while its deposit is held, each against its twin on the same seeds
- **THEN** the report gives each one's return and says whether it is shown to gain

#### Scenario: A better newcomer
- **WHEN** a family that scores higher on known answers joins a network seated by a weaker one
- **THEN** the report gives the share of runs in which it is seated and the week, with and without each rule

### Requirement: The k = 1 hold in the simulation
The simulation SHALL model the hold on k = 1 verdicts, the cap on pending k = 1 verdicts per validator, two audits of every k = 1 verdict, shadows scored only against outcomes no lone validator set, and shadows on waiting submissions. It SHALL run the cap at 5, 10 and 20, a batch-sized k = 1 bond in place of the cap, and one audit of every k = 1 verdict instead of two.

#### Scenario: An honest network grows under the hold
- **WHEN** a run grows from one honest validator under the hold
- **THEN** the report gives the days from a k = 1 verdict to payment, the share of submissions withdrawn, the newcomers qualified and the days they took, and the sponsors' pool spent on shadows

#### Scenario: The colluding genesis under the hold
- **WHEN** the genesis validator, bonded at the floor, passes its accomplice's bad fixes at k = 1
- **THEN** the report gives its return beside its honest twin's, the share of its bad fixes reversed before payment with one and with two audits, and the newcomers qualified in its run and its twin's

### Requirement: Slashes in the simulation
The simulation SHALL model v3's slashes: the whole bond for a false verdict, and a flat $5, the same for every bond, for a counted judge that never seals or that seals and doesn't reveal. It SHALL also run both at $1, and silence unslashed, as alternatives, and each of the two at the larger of $5 and x % of the bounty, for x of 0, 1, 2 and 5 %.

#### Scenario: An honest validator's month
- **WHEN** an honest validator misses a seal at the world's outage rate on the settled market
- **THEN** the report gives its month: fees, usage margin, overhead, slashes, fixed costs and the bond's capital

#### Scenario: A bribed silent judge and a bribed withholder
- **WHEN** a judge bribed to stay silent on a share of its draws never seals on them, and another seals on them and then withholds its reveal
- **THEN** the report gives, for each slash, its return beside its honest twin's, how often it was suspended, and whether k ever shrank

#### Scenario: A slash in proportion to the bounty
- **WHEN** the silence slash, and the slash for a sealed vote not revealed, are the larger of $5 and x % of the bounty, for each x of 0, 1, 2 and 5 %
- **THEN** the report gives, for each x, the return of a silent judge and of a withholder bribed 5 % and 10 % of the bounty beside their honest twins', and an honest validator's month on the market at 1 outage in 200 draws, before and after the seal

### Requirement: The constitution's thresholds and deposit in the simulation
The simulation SHALL draw the constitution tier for an adding ADR only while at least 21 validators are eligible, and for a removal while at least 14 are, expire ADRs submitted to a smaller network, and forfeit a rejected ADR's deposit. It SHALL run the adding threshold at 14, 21 and 28, and the deposit at $0, $15 and $25, and SHALL measure what the deposit costs an honest author.

#### Scenario: An early coalition
- **WHEN** 5, and then 3, validators registered at the start submit an adding ADR worth $1,000 to them each week, with its deposit
- **THEN** the report gives, for each threshold and deposit, the ADRs passed, any passed while fewer than the threshold were eligible, the deposits forfeited, and the coalition's return beside its honest twin's

#### Scenario: The deposit's honest cost
- **WHEN** an honest author submits good ADRs, with the deposit, to a network where at least 21 validators are eligible
- **THEN** the report gives the share of its ADRs rejected, the deposits it forfeits per ADR, and its cost beside its twin with no deposit

#### Scenario: A coalition of removals
- **WHEN** 5 validators registered at the start submit, from 14 eligible, ADRs removing the TEE type most other validators use
- **THEN** the report gives the removals passed, the validators that stopped being drawn, and the coalition's return beside its honest twin's

### Requirement: Each rule runs beside its alternatives
For each rule of #141's two rounds, the simulation SHALL run its named alternative on the same seeds. It SHALL also run round 1's rules as a whole and #134's rules as a whole, to compare.

#### Scenario: A rule against its alternative
- **WHEN** a rule and its alternative run on the same seeds
- **THEN** the report gives both rows in the table that measures them, and names which meets the acceptance criteria

#### Scenario: The TEE cap and the number of TEE types
- **WHEN** a network grows from one validator with the three TEE types realistic at launch (the cap from k = 5), and with five accepted (the cap from k = 3), each spread evenly and skewed toward the commonest types
- **THEN** the report gives, for each, the share of panels of 3 in which one TEE type holds the majority, the share of draws whose k the caps lowered, and the share of submissions that wait

### Requirement: How a criterion is judged
Each criterion SHALL be judged over seeds 1 to 40 with two standard errors (SE) of the mean. An attacker SHALL meet its criterion only if it isn't shown to gain against its honest twin: the mean difference less two SE is at most zero, and the mean plus two SE is at most the published tolerance ($10 over the run). "At most X" SHALL mean the mean plus two SE is at most X; "at least X", the mean minus two SE is at least X. Any other result SHALL fail.

#### Scenario: A result that isn't significant
- **WHEN** an attacker's return minus its twin's is −$34 ± $47
- **THEN** its upper bound, +$13, is above the tolerance, so the criterion isn't met

#### Scenario: An attack that gains nothing
- **WHEN** an attacker's return minus its twin's is −$1 ± $7
- **THEN** its lower bound, −$8, is at most zero and its upper bound, +$6, is within the tolerance, so the criterion is met

#### Scenario: A gain too small to show
- **WHEN** an attacker's return minus its twin's is +$2.7 ± $3.9
- **THEN** its lower bound, −$1.2, is at most zero and its upper bound, +$6.6, is within the tolerance, so the criterion is met

#### Scenario: A small gain
- **WHEN** an attacker's return minus its twin's is +$3 ± $2
- **THEN** its lower bound, +$1, is above zero, so the gain is shown and the criterion isn't met

### Requirement: Acceptance criteria for open validators
The k table, windows, bonds, caps and pricing bounds SHALL be adopted only if each open-validator, pricing, proof-level and scoring attacker on the design's values (answer shopping at a borderline rate of 1 in 10) isn't shown to gain against its honest twin, every scenario below meets its published threshold, and every earlier criterion holds or is named.

#### Scenario: A sybil at or under the share
- **WHEN** one party holds at most the published share (12.5 %) of the eligible validators, spread over hosts, TEE types and families, across a year of draws on the grown network
- **THEN** it never holds a majority of a panel of k ≥ 3, under the caps, in any run

#### Scenario: A sybil above the share
- **WHEN** one party holds more than the published share
- **THEN** the report gives how often it holds a majority, what it can pass, and how often challenges catch it, as the remaining trust point

#### Scenario: The colluding lone validator is caught
- **WHEN** a lone validator colludes with a solver at k = 1
- **THEN** it isn't shown to gain against its honest twin, and at least the published share (90 %) of the bad fixes it passes itself, as the lone judge, pooled over the runs, are reversed before any payment

#### Scenario: The accomplice's other fixes, the trust point
- **WHEN** the colluding lone validator's accomplice has bad fixes passed by other judges
- **THEN** the report gives how many of them were reversed before payment and how many were paid, as the remaining trust point

#### Scenario: The constitution waits for the network
- **WHEN** a coalition submits adding ADRs while fewer than 21 validators are eligible, or removals while fewer than 14 are
- **THEN** none of them passes in any run

#### Scenario: The fee settles near the validators' cost
- **WHEN** the fee starts at its ceiling and validators enter and leave freely
- **THEN** over the last 13 weeks it is at most the published margin (25 %) above the validators' break-even fee and at least that fee less one step, and no run falls below 3 active validators

#### Scenario: Everyone crowds into one model
- **WHEN** every validator chases the top-scoring family
- **THEN** at most the published share (20 %) of submissions wait for a panel

#### Scenario: The network still grows
- **WHEN** a run grows from one validator under v3's rules
- **THEN** a small bounty reaches k ≥ 3 within the year in every run

#### Scenario: Answer shopping, the trust point
- **WHEN** a level C answer shopper runs on a grown all-C network
- **THEN** it isn't shown to gain against its twin when borderline fixes fool an honest call 1 time in 10, and at 3 in 10 the report gives its gain as the remaining trust point
