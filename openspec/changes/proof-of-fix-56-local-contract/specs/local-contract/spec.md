# Spec Delta

## ADDED Requirements

### Requirement: Local only
The contracts SHALL be built, deployed and tested only on a local chain (anvil) in a container with pinned tool versions. Nothing SHALL be deployed to a testnet or mainnet, and no real wallet or key SHALL be used; test keys SHALL be generated for each test run.

#### Scenario: Pinned and local
- **WHEN** the contract tests run
- **THEN** they use the pinned Foundry image and a fresh anvil chain, and no network other than localhost is reached

### Requirement: Immutable, with no admin key
The deployed contracts, the token included, SHALL have no owner, admin, upgrade or pause function. Parameters SHALL be fixed at deployment. A new version SHALL be a new deployment, which users join by withdrawing from the old one and, for the token, by migration.

#### Scenario: No privileged call
- **WHEN** any account calls a function that changes parameters, moves others' funds or upgrades code
- **THEN** no such function exists, and the test listing every external function shows none

### Requirement: The token, with fixed rules
The token's emission schedule, its decay and the founder's share SHALL be fixed at deployment. Only its own Race SHALL mint, each period's emission at most, and no function SHALL change these rules.

#### Scenario: Within the schedule
- **WHEN** a Race mints after bounties close paid in a period
- **THEN** the tokens minted in that period, the founder's share included, never exceed the schedule's emission for it

#### Scenario: Only its Race mints
- **WHEN** any other account calls the mint
- **THEN** it's refused

### Requirement: Upgrades by migration
Anyone SHALL be able to deploy a new version. A new version's token SHALL swap the previous version's tokens 1:1, burning them, with the swap open forever, and SHALL continue the same schedule. In each period it SHALL mint only what the schedule leaves after the previous version's mint in that period.

#### Scenario: A holder swaps
- **WHEN** a holder swaps v1 tokens into v2
- **THEN** the v1 tokens are burned and the holder gets the same number of v2 tokens

#### Scenario: Two versions run at once
- **WHEN** both versions close paid bounties in the same period
- **THEN** their combined mint for that period doesn't exceed the schedule's emission

### Requirement: Baskets with per-coin pull payouts
A bounty SHALL hold balances per coin, credited by the amount actually received, rejecting coins whose transfers deliver less than sent. Every payout and refund SHALL be credited per coin and pulled by its recipient. A coin whose transfer fails SHALL stay claimable without blocking the others, and a funder SHALL withdraw or swap a coin the bounty can't pay out.

#### Scenario: A frozen coin
- **WHEN** a bounty holds two coins and one coin's transfer to the winner reverts
- **THEN** the winner still pulls the other coin, and the frozen coin's share stays claimable

#### Scenario: A fee-on-transfer token
- **WHEN** a pledge in a coin delivers less than the amount sent
- **THEN** the pledge is refused

### Requirement: The race on-chain
The contract SHALL implement the race as specified in bounty-market:
- registration by anyone; the check opens a bounty with no target, unless a similar one is open;
- the rising price, locked by the first attempt;
- the attempt fee;
- submissions committed by hash, then revealed to the oracles, ordered by their commitment;
- the earliest submission that passes wins; one with no result in time fails;
- the late fee;
- duplicate rejection and its appeal; the author's one appeal of a rejection.

#### Scenario: A split rejection appealed
- **WHEN** a submission is rejected on a split (a split jury, or CI that never agreed) and its author appeals
- **THEN** the same fix is checked again for the appeal fee and a new deposit, and it can be appealed only once

#### Scenario: Ordered by commitment
- **WHEN** two solvers commit fix hashes in different blocks and both later pass
- **THEN** the earlier commitment wins, whatever order the results arrive in

#### Scenario: No result in time
- **WHEN** a submission gets no result within the published time, and a later one passes
- **THEN** anyone times it out, its deposit pays the evaluation fee, and the later one wins

#### Scenario: Opened by the check, funded by the market
- **WHEN** the registration check accepts an issue
- **THEN** its bounty opens at once with nothing in it, and anyone pledges any coin while it's open

#### Scenario: The price locked
- **WHEN** the first paid attempt starts on a bounty's third day
- **THEN** the price is locked at 70 % of each coin in its basket

### Requirement: Solved means merged
A winning submission SHALL be paid only after its fix is merged in the opted-in repository, as reported by a signed merge result. Payment SHALL follow in published instalments, one at each release after the challenge window, and a signed upheld challenge SHALL claw back what is still unpaid: it stays in the bounty, which reopens at its locked price (as pof's slash and claw_back). Submissions SHALL post no stake: the winner's unpaid instalments are the bond (owner, 2026-10-26).

#### Scenario: Not merged
- **WHEN** a submission passes but no merge result arrives
- **THEN** nothing is paid, and the bounty reopens after the published merge deadline

#### Scenario: Clawed back
- **WHEN** a signed upheld challenge arrives while instalments are unpaid
- **THEN** the winner keeps the instalments it earned, the rest stays in the bounty, and the bounty reopens at its locked price

#### Scenario: An earlier award still owed
- **WHEN** a bounty is won again while an earlier winner hasn't pulled the instalments it earned
- **THEN** the new price leaves them out of the pot, so both are paid in full and the funders' refunds still open

### Requirement: Safety without a key
Every payout SHALL first check its coin's invariant (the coin's balance covers what is owed in it). If a coin's invariant fails, that coin SHALL switch itself to withdraw-only, forever: every recipient can pull what it's owed in it, its pots refund to their funders, and nothing else in it moves. The other coins SHALL carry on, so a hostile coin can't stop the contract. Published caps per bounty and on total funds SHALL refuse pledges above them.

#### Scenario: An invariant breaks
- **WHEN** a coin's balance falls below what is owed in it
- **THEN** that coin enters withdraw-only mode: later pledges, fees and payouts in it are refused, its credits and refunds are still pulled, and the other coins carry on

#### Scenario: Over the cap
- **WHEN** a pledge would take a bounty or the total above its cap
- **THEN** it's refused

### Requirement: Signed oracle results
The contract SHALL accept a submission's result (CI, gates and juries, aggregated) and merge, challenge and appeal results only when signed by the published quorum of registered oracle keys. A result with too few valid signatures, or for another bounty or submission, SHALL be refused.

#### Scenario: Too few signatures
- **WHEN** a result arrives signed by fewer registered keys than the quorum
- **THEN** it's refused, and the submission's state doesn't change

#### Scenario: Wrong bounty
- **WHEN** a result signed for one submission or bounty is relayed for another
- **THEN** it's refused

#### Scenario: Replayed signature
- **WHEN** a signed result that was already taken is relayed again, or relayed for another action or another deployment
- **THEN** it's refused

### Requirement: The simulation as the test oracle
A simulated race run SHALL export its events in order. Replaying them against the contract SHALL leave every account's balance, per coin, equal to the simulation's ledger.

#### Scenario: Balances match
- **WHEN** a simulated race run's events are replayed against a fresh deployment
- **THEN** every account's balance equals the simulation's, to the micro-credit
