# Spec Delta

## Purpose
How a check's price moves in v3, with open validators and no vote:
- the pass-through unit prices follow the median of the validators' posted tables;
- the service fee follows the queue, like Ethereum's base fee, starting at its ceiling, with every wait counted.

It replaces v2's price updates signed by 5 of 7 seats for v3 only. The check-fee formula itself (usage at unit prices plus one service fee, paid per counted judge) is unchanged.

## ADDED Requirements

### Requirement: Validators post cost tables for every unit
Any active validator SHALL be able to post, at any time, a signed table with a value for every unit of the price table: its own costs for sandbox seconds, storage and gas, and each model family's public list price for tokens. Only its latest table SHALL count. A table missing a unit, or a candidate's, a suspended or a leaving validator's table, SHALL NOT count.

#### Scenario: A provider cuts its prices
- **WHEN** a model provider halves its token price and validators post new tables
- **THEN** their latest tables replace their earlier ones, with no proposal or vote

#### Scenario: A table without another family's price
- **WHEN** a validator posts a table with its own family's token price but not the other families'
- **THEN** the table doesn't count

### Requirement: Unit prices are the median of the posted tables
At the end of each pricing period, each unit price SHALL become the median of the counting validators' latest values, the lower middle value for an even count, if at least the published minimum number posted. Each price SHALL move by at most the published step per period, and SHALL never exceed twice its value at deployment.

#### Scenario: One validator posts an absurd price
- **WHEN** one of 15 active validators posts a token price 100 times the others'
- **THEN** the median moves by at most one rank, and stays within the range of the other 14 validators' values

#### Scenario: Three validators of one family inflate its price
- **WHEN** the three validators of one family post 100 times its list price among 24 counting validators
- **THEN** that family's token price follows the median of all 24 tables, which stays within the range of the other 21 validators' values

#### Scenario: An even count
- **WHEN** an even number of validators post a unit and its two middle values differ
- **THEN** the lower of the two is the median

#### Scenario: A real price drop
- **WHEN** every validator's posted token price falls by half
- **THEN** the unit price falls by the published step each period until it reaches the new median

#### Scenario: Too few tables
- **WHEN** fewer validators than the published minimum have posted a value for a unit
- **THEN** that unit's price stays as it is

### Requirement: The service fee starts at its ceiling
A version's service fee SHALL start at its published ceiling at deployment.

#### Scenario: A new version
- **WHEN** v3 is deployed with its genesis validator
- **THEN** the service fee is the ceiling until the queue rules move it

### Requirement: The service fee follows the queue
At the end of each pricing period, the service fee SHALL rise by the published step if the share of submissions that waited for a panel exceeded its published threshold. Otherwise, it SHALL fall by the step if the share of active validators not drawn exceeded its published threshold. It SHALL stay between the published floor and ceiling.

#### Scenario: Not enough validators
- **WHEN** more than the threshold share of a period's submissions waited for a panel
- **THEN** the service fee rises by one step, making it worth more people's while to run a validator

#### Scenario: Too many idle validators
- **WHEN** no submission waited and more than the threshold share of active validators (40 % at launch) weren't drawn in the period
- **THEN** the service fee falls by one step, down to the floor at most

### Requirement: Every wait counts toward the fee's rise
A submission SHALL count as having waited for a panel once, in the period it starts waiting, whatever its bounty and whatever kept it from being drawn. A counted panel stalled for want of a replacement SHALL count once for its submission.

#### Scenario: A big bounty waits for large bonds
- **WHEN** a $500 bounty waits because no validator with a $1,250 bond is free
- **THEN** the wait counts toward the fee's rise, so a higher fee makes larger bonds worth posting

#### Scenario: A small bounty waits for anyone
- **WHEN** a $40 bounty waits because no validator is eligible for it
- **THEN** the wait counts

#### Scenario: A long wait
- **WHEN** a submission waits for a panel across three periods
- **THEN** it counts once, in the period it started waiting

#### Scenario: A panel stalls
- **WHEN** a counted judge stays silent and no eligible validator is left to replace it
- **THEN** the stalled panel's submission counts as having waited, once

### Requirement: No account or vote sets a price
No account, validator, panel or DAO SHALL be able to set a unit price or the service fee directly. Prices SHALL change only by the median and the queue rules, within their bounds. The bounds are fixed per version.

#### Scenario: A cartel proposes higher fees
- **WHEN** a group of validators wants a higher service fee
- **THEN** there is no proposal or vote to submit; refusing work only gets its members replaced in the draw, slashed the flat silence amount, and their reveal rate lowered

### Requirement: An attempt is charged the prices it was quoted
An attempt SHALL be charged the unit prices and the service fee in effect when it was started, so a price change during a pricing period never changes a check already under way.

#### Scenario: Prices change during a check
- **WHEN** the service fee rises at the end of a period while a solver's attempt is being judged
- **THEN** that attempt is charged the fee it was quoted
