# Spec Delta

## Purpose
How work is paid by merit each cycle: each repository's cycle pool and the network index pool, a judge panel that scores the cycle's merged fixes in dollars, the pay of each fix up to its merit, the one protocol token earned by funders by merit, challenges by anyone with a claim on the repository before the split, the judges' merit records, a coin that can't pay, and the parameters fixed per deployment.

## ADDED Requirements

### Requirement: Each repository has a cycle pool with recorded shares
Each registered repository SHALL have one pool per cycle, of the published cycle length. Anyone SHALL be able to add an allowed coin to the current cycle's pool. The contract SHALL record each address's share of the cycle, in proportion to the coin it holds there, and the shares SHALL NOT change after the cycle closes. Stakes forfeited in a cycle SHALL be added to the next cycle's pool, give nobody a share and earn nobody tokens.

#### Scenario: Two funders
- **WHEN** one address adds 300 and another 100 to a repository's cycle pool
- **THEN** their shares of that cycle are 75 % and 25 %

#### Scenario: Funding after the close
- **WHEN** an address adds coin after a cycle has closed
- **THEN** it goes to the next cycle's pool and its share is recorded there

#### Scenario: A forfeited stake
- **WHEN** a stake of 50 is forfeited during a cycle
- **THEN** the next cycle's pool grows by 50, no address's share grows, and the tokens its coin would earn are not minted to anyone

### Requirement: Each funder decides what happens to its leftover
Coin a cycle doesn't spend SHALL stay with each funder, by share. Each funder SHALL choose, alone, to roll it over to the next cycle, to withdraw it, or to move it to another repository's pool or the index pool; with no choice, it SHALL roll over. Withdrawn coin SHALL earn no tokens. No vote or majority SHALL decide for a funder.

#### Scenario: A thin cycle
- **WHEN** a pool of 2,000 held 75 % and 25 % by two funders pays a single fix 5
- **THEN** 1,995 stays in the pool, 1,496.25 for the first funder and 498.75 for the second

#### Scenario: Roll over by default
- **WHEN** a funder makes no choice before the next cycle opens
- **THEN** its leftover is its share's coin in the next cycle's pool

#### Scenario: Withdraw
- **WHEN** a funder withdraws its leftover of 500
- **THEN** it is credited 500 to pull, and that coin earns no tokens from then on

#### Scenario: Move
- **WHEN** a funder moves its leftover to another repository's pool
- **THEN** its share there is recorded for the next cycle, and its share in the first pool ends

### Requirement: The network index pool
The network index pool SHALL take allowed coin from anyone and, at each cycle's start, spread it over the registered repositories' pools in proportion to their calibrated merit over the last published number of cycles. The coin it places SHALL pay fixes like any pool coin, and what a cycle leaves unspent SHALL return to the index. Its funders SHALL hold shares of the index, not of a repository.

#### Scenario: Spread by merit
- **WHEN** the index holds 1,000 and two repositories had 3,000 and 1,000 of merit over the window
- **THEN** it places 750 in the first's pool and 250 in the second's

#### Scenario: No merit, no coin
- **WHEN** a repository had no merged fix over the window
- **THEN** the index places nothing in its pool

#### Scenario: Unspent coin returns
- **WHEN** a repository's pool spends 100 of the 250 the index placed in it
- **THEN** 150 returns to the index, by its funders' shares

### Requirement: Every funder of a pool earns the same tokens per coin
Within a pool, a repository's or the index, every funder SHALL earn the same tokens per coin spent in a cycle: the pool's tokens SHALL be split by the coin each funder's share spent. No funder SHALL choose which fixes its share pays.

#### Scenario: Shares spend together
- **WHEN** a pool held 75 % and 25 % spends 400 and earns 400 tokens
- **THEN** the funders spent 300 and 100, and earn 300 and 100 tokens

### Requirement: Each pool's tokens per coin are published
Each pool's tokens per coin spent, cycle by cycle, SHALL be computable from the contract's events alone, and SHALL be published with the leaderboard. Reading them SHALL NOT be charged.

#### Scenario: The history matches the books
- **WHEN** the leaderboard computes a pool's tokens per coin spent from the events
- **THEN** it matches the same cycles read from the contract's views exactly

### Requirement: Bounties stay beside the pool
A per-issue bounty SHALL remain optional. Its coin SHALL pay the fix that wins it, as before, and SHALL NOT be pooled. A fix MAY be paid both its bounty and from the pool; the pool SHALL pay only what its claim leaves after the bounty.

#### Scenario: A bounty and the pool
- **WHEN** a fix of merit 300 wins a bounty of 200, and its pool covers every claim at 1 per merit dollar
- **THEN** it is paid 200 from the bounty and 100 from the pool, less the payout fee on each

#### Scenario: A bounty above the merit
- **WHEN** a fix of merit 100 wins a bounty of 200
- **THEN** it is paid the 200 its funders chose, and nothing from the pool

### Requirement: A merit panel scores the cycle's fixes in dollars
When a cycle closes, a panel SHALL be drawn under the panel rules (#132). It SHALL see every fix merged in the repository during the cycle: its issue, claimed importance, diff, test result and funding. Each judge SHALL seal, then reveal, a merit in dollars of value for every fix. A fix's merit SHALL be the median of the revealed, calibrated merits.

#### Scenario: Three judges
- **WHEN** three judges reveal calibrated merits of 40, 50 and 400 dollars for a fix
- **THEN** its merit is 50 dollars

#### Scenario: A judge that doesn't reveal
- **WHEN** a drawn judge seals but doesn't reveal
- **THEN** the median is taken over the judges that revealed, and the silent judge is treated as the panel rules say

### Requirement: Merit is calibrated by reference fixes
Every panel SHALL also score the published reference fixes, each with a recorded dollar merit, and each judge's scores SHALL be scaled so that the median of its reference scores matches their recorded merits. A cycle with more fixes than the published batch size SHALL be scored in batches that each include the same reference fixes. The reference set SHALL change only with the merit prompt.

#### Scenario: A judge that scores high
- **WHEN** a judge scores the reference fixes at 1.2 times their recorded merits, on the median
- **THEN** its scores for the cycle's fixes are divided by 1.2 before the median is taken

#### Scenario: A large cycle
- **WHEN** a cycle has twice the batch size in fixes
- **THEN** it is judged in two batches with the same reference fixes, and a fix's merit doesn't depend on which batch it was in, beyond the judges' own error

### Requirement: Each fix is paid at most its merit
After the challenge window, each fix's claim SHALL be its merit times the pay per merit dollar, less its bounty coin. The pool SHALL pay every claim in full when it covers them all, and pro rata to the claims when it's short, each less the payout fee. A cycle with no merged fix and no carried claim SHALL leave the whole pool with its funders. The panel's judges SHALL be paid only their checks' fees, never a share of the pool.

#### Scenario: A pool larger than the merit
- **WHEN** a pool of 2,000 pays fixes of merit 300, 100 and 100, with no bounty, at 1 per merit dollar
- **THEN** they are paid 300, 100 and 100, each less its payout fee, and 1,500 stays with the funders

#### Scenario: A short pool
- **WHEN** a pool of 300 pays fixes of merit 300, 100 and 100, with no bounty
- **THEN** they are paid 180, 60 and 60, pro rata to their claims

#### Scenario: An empty cycle
- **WHEN** no fix is merged in a cycle, and no shortfall is carried
- **THEN** no coin moves, and each funder's coin stays for its choice

### Requirement: The pay per merit dollar rises when money waits
The pay per merit dollar SHALL be the pool's coin over the cycle's claims at 1 per merit dollar, clamped between the deployment's lower and upper bounds (1 and 1.5 in the simulation).

#### Scenario: Money waits
- **WHEN** a pool of 2,000 faces claims of 500 at 1 per merit dollar, with bounds 1 and 1.5
- **THEN** the pay per merit dollar is 1.5, the fixes are paid 750, and 1,250 stays with the funders

#### Scenario: Money is short
- **WHEN** a pool of 300 faces claims of 500
- **THEN** the pay per merit dollar is 1, and the claims are paid pro rata

### Requirement: A shortfall carries over
What a short pool leaves unpaid of a fix's claim at 1 per merit dollar SHALL be the first claim on the repository's next cycle's pool, paid before that cycle's fixes. Its tokens SHALL be minted when it is paid, as merit equal to the coin that paid it.

#### Scenario: The backlog is paid first
- **WHEN** a cycle leaves 200 of claims unpaid, and the next cycle's pool holds 1,000
- **THEN** 200 is paid to those fixes first, and 800 is left for the new cycle's claims

### Requirement: The network emission follows merit, up to a cap
Each cycle, the network SHALL mint E, the smaller of the deployment's emission rate times the network's total calibrated merit and the deployment's emission cap. The cap SHALL be fixed for the deployment, and SHALL NOT follow burns.

#### Scenario: Under the cap
- **WHEN** the network's merit in a cycle is 5,000 dollars, at a rate of 1 token per merit dollar and a cap of 8,000
- **THEN** the cycle's emission is 5,000 tokens

#### Scenario: At the cap
- **WHEN** the network's merit in a cycle is 12,000 dollars, with the same settings
- **THEN** the cycle's emission is 8,000 tokens

#### Scenario: Burns don't move the cap
- **WHEN** the last cycle burned 3,000 tokens
- **THEN** the cap is still 8,000; it isn't raised by the burns

### Requirement: The token's weights come from the merit panel
Each cycle's emission SHALL be split among the network's fixes judged in that cycle in proportion to their merits, within the outside-coin cap. This SHALL replace the per-bounty registration and merge estimates as the weights.

#### Scenario: Two fixes
- **WHEN** an emission of 1,000 is split between two uncapped fixes of merit 300 and 100
- **THEN** they get 750 and 250

### Requirement: A fix's tokens are capped by its outside coin
A fix's outside coin SHALL be the coin that paid it from bounties and pools, less the part contributed by the accounts that solved it. Each fix's tokens SHALL be at most the deployment's tokens per coin times its outside coin. What the caps cut SHALL be split among the uncapped fixes in proportion to their merits; only when every fix is capped SHALL the rest not be minted.

#### Scenario: A fix funded by its own solver
- **WHEN** a fix's only coin is a bounty its solver funded
- **THEN** its outside coin is 0, and it is minted no tokens, whatever its merit

#### Scenario: The cap binds
- **WHEN** an emission of 1,000 meets fixes of merit 300, 100 and 100 with outside coin 50, 400 and 400, at 2 tokens per coin
- **THEN** the first gets 100, and the other two get 450 each

#### Scenario: Every fix capped
- **WHEN** every fix of a cycle reaches its cap before the emission is spent
- **THEN** the rest of the emission is not minted

### Requirement: A fix's tokens go to its funders, and solvers are paid in coin
A fix's tokens SHALL go to the funders whose outside coin paid it, bounty pledgers and pool funders alike, in proportion to that coin. A solver SHALL be paid in coin only. No address SHALL be minted tokens otherwise, except under a blocked coin: no owner's, founder's or validators' share.

#### Scenario: A bounty and a pool
- **WHEN** a fix minted 300 tokens was paid 200 by a pledger's bounty and 100 by a pool held 75 % and 25 %
- **THEN** the pledger gets 200 tokens and the pool's funders 75 and 25, and the solver gets none

#### Scenario: A solver that funds
- **WHEN** a solver pledges on another solver's fix
- **THEN** it earns that fix's tokens on its coin like any funder

#### Scenario: The owner funds
- **WHEN** the owner's address funds a pool
- **THEN** it earns tokens by the same rule as any funder, and no other token reaches it

### Requirement: A coin that can't pay
Anyone SHALL be able to probe an allowed coin with a transfer of its smallest unit from the contract to itself. A failed probe SHALL block the coin until a probe succeeds; a solvency failure SHALL block it for good. A blocked coin SHALL take no new funding, and its credits SHALL stay owed. The tokens its funders would have earned on the fixes it was due to pay SHALL go to those fixes' solvers by merit, within the emission.

#### Scenario: A paused coin at the split
- **WHEN** a coin is blocked when a cycle splits, and it was due to pay two fixes of merit 300 and 100 whose funders would have earned 400 tokens
- **THEN** the fixes' solvers get 300 and 100 tokens, no extra token is minted, and the coin's payouts stay owed as credits

#### Scenario: The pause is lifted
- **WHEN** a later probe succeeds
- **THEN** the coin is no longer blocked, and its credits can be pulled

#### Scenario: A frozen recipient
- **WHEN** an issuer freezes only a fixer's own address
- **THEN** the coin isn't blocked, and the fixer pulls its credit to another address

#### Scenario: The contract's own address frozen
- **WHEN** an issuer freezes the contract's address
- **THEN** nothing in that coin can move, for anyone, until the freeze is lifted; the token and the other coins carry on

### Requirement: Challenges before the split
Anyone with a claim on the repository (a share of its pool or of the index pool, or a pledge on one of its bounties) SHALL be able to file a merit challenge against a fix, from its merge until the end of the merit panel's challenge window. A merit challenge SHALL pay its check and be checked by AI like any issue. When it is upheld, the fix's merit SHALL be set to the merit the check gives before the split.

#### Scenario: No claim, no challenge
- **WHEN** an address with no pool share, no index share and no pledge in the repository files a merit challenge
- **THEN** it is refused

### Requirement: An upheld challenge is rewarded, a mistaken one costs its fee
The challenger of an upheld merit challenge SHALL be paid a published share of the coin the correction moved away from the fix, out of the pool. The challenger of a challenge that isn't upheld SHALL lose only the fee.

#### Scenario: An upheld challenge
- **WHEN** a fix judged at merit 200 is challenged, and the check upholds a merit of 5
- **THEN** the split uses 5, the challenger is paid the published share of the coin the fix would have been overpaid, and the fix's stake is judged by its claim against 5

#### Scenario: A mistaken challenge
- **WHEN** a challenge against an honest fix isn't upheld
- **THEN** the merit stands, and the challenger has paid the check's fee

### Requirement: Judges' merit records follow the corrected merit
Each judge's merits SHALL be recorded against the final merit, as corrected by any upheld challenge. A merit more than the deployment's tolerance (3 × in the simulation) above or below the final merit SHALL count as a disagreement; one within it, as an agreement. Disagreements SHALL count against the judge's own record and its family's score (#132). Records SHALL NOT weight a vote.

#### Scenario: A colluder on a panel that saw through
- **WHEN** two judges reveal merit 5 for an overclaimed fix and a third reveals 200
- **THEN** the third judge's record counts a disagreement, though the fix's merit was right

#### Scenario: A colluding majority corrected by a challenge
- **WHEN** two colluding judges reveal 200 and one honest judge 5, and an upheld challenge sets the merit to 5
- **THEN** the two colluding judges' records count disagreements, and the honest judge's an agreement

#### Scenario: Every merit counts once
- **WHEN** a judge with a low record reveals a merit
- **THEN** it counts once in the median, like any other

### Requirement: A validator below the merit floor isn't drawn
A validator whose merit record is below the published floor SHALL NOT be drawn for counted panels until it re-registers with a new bond, starting from the published newcomer's record.

#### Scenario: Below the floor
- **WHEN** a validator's record falls below the floor
- **THEN** it isn't drawn for counted panels, and returning needs a new registration and bond

### Requirement: The token's price for the payout fee
The payout fee SHALL read the token's price from a price feed fixed when the contract is deployed. Until a feed exists for the token, it SHALL read a time-averaged price, over the published window, from an exchange pool fixed at deployment. With neither, the fee SHALL be 0. No account SHALL be able to change the source; a new source SHALL need a migration (ADR 0003).

#### Scenario: No market yet
- **WHEN** the token trades nowhere
- **THEN** every payout fee is 0

#### Scenario: A price pushed down
- **WHEN** someone pushes the exchange's price down during a cycle
- **THEN** the time-averaged price moves only by the window's share, and the fee stays between 0 and the fee cap's share of the coin

### Requirement: Parameters that depend on the judges are fixed per deployment
The fee cap, the merit tolerance, the tokens per coin, the emission rate and cap, the pay per merit dollar's bounds, and the detection rate the safety argument assumes SHALL be set when the contracts are deployed, readable on-chain, and immutable. No function SHALL change them; a new value SHALL need a new deployment, reached by migration (ADR 0003).

#### Scenario: No setter
- **WHEN** any account calls the deployed contracts
- **THEN** no function changes any of these parameters

#### Scenario: The devnet
- **WHEN** the contracts are deployed on a devnet
- **THEN** they take the published test values, and the deployment's parameters can be read back from its views

#### Scenario: Anything but a devnet
- **WHEN** the deploy script targets anything but a devnet
- **THEN** it refuses unless the parameters record the hash of #160's measurement report, from which the values come
