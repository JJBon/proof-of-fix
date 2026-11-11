# Spec Delta

## MODIFIED Requirements

### Requirement: Market fee and refunds
Coin paid to a fix (bounty or pool) SHALL pay a market fee out of that pay: the value, at the token's price (merit-cycles), of the tokens that coin earned, capped at the deployment's fee cap share of the coin, and 0 when the token has no price. The fee SHALL be burned or added to the repository's next cycle pool, never paid to an account. Once the contribution is fully paid, the bounty's leftover SHALL return in proportion to what each source put in, the treasury's share to insurance.

#### Scenario: Tokens worth little
- **WHEN** a fix is paid 150 in coin that earned tokens worth 6 at the token's price
- **THEN** the market fee is 6, and the solver receives 144

#### Scenario: Fee split
- **WHEN** a fix is paid 150 in coin that earned tokens worth 60, with a fee cap of 2,000 basis points
- **THEN** the market fee is 30, the cap

#### Scenario: No market
- **WHEN** the token has no price
- **THEN** the market fee is 0

#### Scenario: Nobody is paid the fee
- **WHEN** a market fee is taken
- **THEN** it is burned or added to the repository's next cycle pool, and no account's balance grows by it

#### Scenario: Leftover refunded
- **WHEN** a pledged bounty of 300 pays a price of 150, a market fee of 30 and a finder's fee of 7.5, and the contribution is fully paid
- **THEN** the remaining 112.5 returns to the pledgers in proportion to their pledges

#### Scenario: Matched leftover
- **WHEN** a bounty funded by 200 of pledges and a match of 100 has 90 left once fully paid
- **THEN** 60 returns to the pledgers in proportion to their pledges, and 30 goes to insurance

### Requirement: Issue stakes
An issue's submitter SHALL state its claimed importance in dollars and post a published stake. When the claim is over the deployment's merit tolerance (3 × in the simulation) times the merit awarded to its fix (merit-cycles), the stake SHALL go to the repository's next cycle pool, with no finder's fee. Otherwise it SHALL return, with a finder's fee when the bounty is paid: a published share of the winning price's coin from others than the reporter. Junk SHALL forfeit it to insurance.

#### Scenario: Real issue fixed
- **WHEN** an issue claimed at 100 is fixed with merit 80, and its bounty is paid after its instalments
- **THEN** the reporter's stake returns, with the finder's fee on the winning price's outside coin

#### Scenario: An overclaimed issue
- **WHEN** an issue claimed at 200 is fixed with merit 5
- **THEN** the reporter's stake is forfeited to the repository's next cycle pool, and no finder's fee is paid

#### Scenario: An honest estimate that's a little high
- **WHEN** an issue claimed at 100 is fixed with merit 40, with a tolerance of 3 ×
- **THEN** the stake returns: 100 is within 3 × 40

#### Scenario: Junk confirmed
- **WHEN** the treasury flags an issue as junk and a validator panel confirms it, or the fix delivered for it is slashed as junk
- **THEN** the reporter's stake goes to insurance, and the issue gets no bounty, or no further one

#### Scenario: Flag not confirmed
- **WHEN** the treasury flags an issue as junk and the panel doesn't confirm it
- **THEN** the stake stays posted, and the issue can still be funded

#### Scenario: Never funded
- **WHEN** an issue is neither funded nor fixed before its deadline
- **THEN** the reporter's stake returns, with no fee

#### Scenario: Funding your own issue doesn't pay
- **WHEN** a reporter funds its own issue in full
- **THEN** the winning price has no outside coin, so the finder's fee is 0

## ADDED Requirements

### Requirement: Bounties and pools take allowed USD stablecoins
Bounties, pools, stakes and check fees SHALL take only USD stablecoins on the allow-list, which starts with one coin. The list SHALL be fixed at deployment and changed only by an accepted ADR at the constitution tier, applied by a new deployment or, once ADRs reach the chain, by the judges' constitution-tier verdict. No key SHALL change it (Article 2). Solvers SHALL be paid in these coins only.

#### Scenario: A coin not on the list
- **WHEN** someone pledges, funds a pool or posts a stake in a coin not on the allow-list
- **THEN** it is refused

#### Scenario: No key adds a coin
- **WHEN** any single account, the deployer's included, tries to add a coin to the list
- **THEN** there is no function that does it

#### Scenario: A coin added by ADR
- **WHEN** an ADR adding a stablecoin is accepted and applied
- **THEN** the coin is allowed from then on, for new funding only

### Requirement: Whoever causes a check pays for it
Every check SHALL be paid by whoever causes it: the reporter's registration, the solver's attempts, a challenger's merit challenge, and the cycle's pool for its merit panel, before the split. It SHALL pay the judges' real cost in an allowed coin, at the price table plus the service fee (Article 5.11), and, in a version with the token, a published margin in the token, burned and never paid to anyone. Reading chain data SHALL NOT be charged.

#### Scenario: A registration
- **WHEN** a reporter registers an issue, the check costs 0.37 and the service fee is 0.05, and the margin is 0.05 dollars with the token at 0.25
- **THEN** the reporter pays 0.42 in coin to the judges and 0.2 tokens, which are burned

#### Scenario: The merit panel
- **WHEN** a cycle's merit panel is drawn
- **THEN** its checks are paid from that cycle's pool before the split, and its judges get no share of the pool

#### Scenario: No token price
- **WHEN** the token has no price
- **THEN** the margin is 0, and the payer pays the judges' cost and the service fee only

#### Scenario: Reading is free
- **WHEN** anyone reads verdicts, pools or the published tokens per coin
- **THEN** nothing is charged
