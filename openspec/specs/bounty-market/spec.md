# bounty-market Specification

## Purpose
Defines how fixes are priced and paid by a market: issues become bounties funded by pledges or a capped treasury, solvers bid for the job in sealed second-price rounds before building anything, and the assigned solver is paid on release through the contribution lifecycle.

## Requirements

### Requirement: Bounties and pledges
An issue SHALL become a bounty with a published definition of solved and a target amount. Users SHALL pledge toward the target until a published deadline. If the target isn't reached by then, every pledge SHALL be refunded in full.

#### Scenario: Target reached
- **WHEN** pledges reach a bounty's target before its deadline
- **THEN** the bounty opens a sealed round, and the pledges are held in the bounty's escrow

#### Scenario: Target missed
- **WHEN** a bounty's deadline passes below its target
- **THEN** every pledge returns to its pledger, and nothing else moves

### Requirement: Treasury bounties
Each release SHALL make a published treasury budget available, less its matching share, for bounties on issues nobody pledges for, proposed by the treasury in order of value times the reporter's trust. No single bounty SHALL exceed a published cap. A proposal above a published threshold SHALL need a validator panel's majority. Unspent budget SHALL NOT accumulate beyond one release.

#### Scenario: Within the budget
- **WHEN** the treasury proposes bounties whose total stays within the release's budget, less its matching share
- **THEN** each is funded from the budget and opens a sealed round like a pledged one

#### Scenario: Ranked by trust
- **WHEN** two unpledged issues of equal value come from a proven reporter and from a new one
- **THEN** the proven reporter's issue is proposed first

#### Scenario: Over the budget
- **WHEN** a proposal would take the release's treasury spend over that budget
- **THEN** it is refused, and the ledger records the refusal

#### Scenario: A large proposal
- **WHEN** a proposal exceeds the approval threshold
- **THEN** it is funded only if a validator panel's majority approves it

### Requirement: Sealed rounds for the job
A solver SHALL bid for the job, before building anything, by committing a sealed price at most the bounty's reserve price. It SHALL post a stake, a published share of the cap times the risk multiplier, lowered by its trust down to a published share of that, and a check deposit (the oracle reserve). After the deadline, every bidder SHALL reveal its price. A bid that isn't revealed, doesn't match its commitment, or is above the reserve SHALL forfeit the published evaluation fee from its deposit.

#### Scenario: Bid accepted
- **WHEN** a solver commits a sealed price before the deadline, with enough balance for the stake and the check deposit
- **THEN** the stake and deposit are locked, and no one can see the price

#### Scenario: A proven solver's bond
- **WHEN** a solver with full trust bids
- **THEN** its stake is the published share of the full stake, while a newcomer's is the full stake

#### Scenario: Above the reserve
- **WHEN** a revealed price is above the bounty's reserve
- **THEN** the bid is void, its evaluation fee is forfeited, and the rest of its deposit returns

#### Scenario: Nothing to copy
- **WHEN** a round's bids are revealed
- **THEN** only prices are revealed: no solution exists yet, so no one can copy one

#### Scenario: Reveal doesn't match
- **WHEN** a bidder's reveal doesn't match its commitment, or it doesn't reveal
- **THEN** its evaluation fee is forfeited to the checking costs, its stake and the rest of its deposit return, and it can't be assigned the job

### Requirement: Assignment and price
The cheapest revealed bid SHALL be assigned the job, at the second-lowest revealed price, or at the bounty's reserve price (a published share of its price cap) when it's the only bid, and never above the reserve. Its stake SHALL stay locked as a performance bond, and its deposit for its checks. Every other bid's stake and deposit SHALL return, and the bids SHALL stay queued in price order as runners-up. A round without a valid bid SHALL be followed by a new round.

#### Scenario: Second price
- **WHEN** three bids reveal at prices 100, 150 and 200, all within the reserve
- **THEN** the bid at 100 is assigned the job at 150, and the other two get their stakes and deposits back

#### Scenario: Only one bid
- **WHEN** only one bid is revealed
- **THEN** it is assigned at the reserve price, not the price cap

#### Scenario: No bid
- **WHEN** no bid is revealed
- **THEN** no one is assigned, the bounty's funds stay, and a new round opens

### Requirement: Delivery
The assigned solver SHALL deliver within a published number of days. Its checks SHALL be paid from its deposit, and the unused part SHALL return. A delivery whose attested runs pass and that the jury accepts SHALL become the winning contribution, and the bond SHALL be released. A failed, rejected or late delivery SHALL forfeit the bond to the bounty; a late one, with no checks run, its evaluation fee too, and SHALL offer the job to the next queued bid if it posts its stake and deposit.

#### Scenario: Delivered in time
- **WHEN** the assigned solver delivers before its deadline, its attested runs pass and the jury accepts it
- **THEN** the solution becomes a contribution with the bond as its stake, its checks are paid from its deposit, and the rest returns

#### Scenario: Rejected by the jury
- **WHEN** a delivery passes its attested runs, but the jury rejects it unanimously
- **THEN** the bond goes to the bounty, the deposit pays for the checks that ran, the attempt is published, and a fresh round opens

#### Scenario: Not delivered
- **WHEN** the deadline passes without a passing delivery
- **THEN** the bond goes to the bounty, the evaluation fee goes to the checking costs, the rest of the deposit returns, and the next queued bid is offered the job

#### Scenario: Runner-up can't post its stake
- **WHEN** the next queued bidder can't post its stake and deposit again
- **THEN** it is skipped, and the job is offered to the one after it, or a new round opens

### Requirement: Payment through the lifecycle
The winning contribution SHALL take the assigned price as its reward, escrowed from the bounty, and follow the lifecycle: the next beta build, the challenge window, and instalments with clawback. If it is slashed or clawed back, the forfeited escrow SHALL return to the bounty, which SHALL reopen as for a failed attempt.

#### Scenario: Paid on release
- **WHEN** the winning contribution is accepted and its instalments are paid
- **THEN** the solver receives its price over the instalments, and its stake returns with the last one

#### Scenario: Winner slashed
- **WHEN** the winning contribution is slashed in its window
- **THEN** the escrow returns to the bounty in full, the stake is slashed by severity, and a fresh round opens with the contribution public

### Requirement: Market fee and refunds
When a winner's price is escrowed, a published market fee on it SHALL be paid from the bounty, in published proportions, to the validators' pool, the author's escrow, infrastructure, insurance and the owner (within the owner's cap). The price cap SHALL leave room for the market fee and the finder's fee. Once the contribution is fully paid, the bounty's leftover SHALL return in proportion to what each source put in, the treasury's share to insurance.

#### Scenario: Fee split
- **WHEN** a price of 150 is escrowed with a market fee of 20 %
- **THEN** 30 is paid from the bounty in the published proportions, and the parts add up to 30 exactly

#### Scenario: Leftover refunded
- **WHEN** a pledged bounty of 300 pays a price of 150, a market fee of 30 and a finder's fee of 7.5, and the contribution is fully paid
- **THEN** the remaining 112.5 returns to the pledgers in proportion to their pledges

#### Scenario: Matched leftover
- **WHEN** a bounty funded by 200 of pledges and a match of 100 has 90 left once fully paid
- **THEN** 60 returns to the pledgers in proportion to their pledges, and 30 goes to insurance

### Requirement: Issue stakes
Whoever submits an issue SHALL post a published issue stake. When the issue's bounty is paid, the stake SHALL return with a finder's fee: a published share of the winning price, paid from the bounty and smaller than the market fee. When the issue is judged junk, the stake SHALL go to insurance. An issue that's never funded SHALL get its stake back.

#### Scenario: Real issue fixed
- **WHEN** an issue's bounty is paid after its fix ships and its instalments are paid
- **THEN** the reporter's stake returns, with the finder's fee on the winning price

#### Scenario: Junk confirmed
- **WHEN** the treasury flags an issue as junk and a validator panel confirms it, or the fix delivered for it is slashed as junk
- **THEN** the reporter's stake goes to insurance, and the issue gets no bounty, or no further one

#### Scenario: Flag not confirmed
- **WHEN** the treasury flags an issue as junk and the panel doesn't confirm it
- **THEN** the stake stays posted, and the issue can still be funded

#### Scenario: Never funded
- **WHEN** an issue is neither pledged to its target nor funded by the treasury before its deadline
- **THEN** the reporter's stake returns, with no fee

#### Scenario: Funding your own issue doesn't pay
- **WHEN** a reporter funds its own issue in full
- **THEN** the finder's fee it receives is smaller than the market fee its own pledge paid on the same price

### Requirement: Quadratic matching
A published share of each release's treasury budget SHALL match pledges on bounties still gathering pledges, by weight: the sum over pledgers of their funder trust times the square root of their pledges, squared, less the sum of each pledger's trust squared times its pledges. Matches SHALL be scaled to fit that share, capped per bounty at a published share of its target, and counted toward the target.

#### Scenario: Many small pledgers attract more
- **WHEN** one bounty gathers 100 credits from ten pledgers and another 100 credits from one pledger, all with the same trust
- **THEN** the first is matched and the second isn't

#### Scenario: New accounts draw little
- **WHEN** two bounties gather the same pledges from the same number of pledgers, one from proven funders and one from new accounts
- **THEN** the second's weight is the first's times the floor squared

#### Scenario: Within the matching budget
- **WHEN** the weights of all bounties gathering pledges add up to more than the release's matching budget
- **THEN** every match is scaled down by the same factor, and the total stays within the budget

#### Scenario: Capped
- **WHEN** a bounty's match would exceed the published share of its target
- **THEN** it gets exactly the cap

#### Scenario: A match completes the target
- **WHEN** a match brings a bounty's funds to its target
- **THEN** the bounty opens its sealed round

### Requirement: Unsolved bounties close
A funded bounty whose round closes without a bid for a published number of rounds in a row SHALL close: its funds SHALL return in proportion to what each source put in, the treasury's share to insurance, and its reporter's stake SHALL return, with no fee.

#### Scenario: No one can do it
- **WHEN** a bounty's rounds close without a bid for the published number of rounds
- **THEN** it closes, the pledgers get their share back, the treasury's share goes to insurance, and the reporter gets its stake back

#### Scenario: A bid in time
- **WHEN** a bid arrives before that number of empty rounds
- **THEN** the bounty stays open as before

### Requirement: Failed attempts are published
A delivered attempt that fails its checks or its jury, or a winning contribution slashed or clawed back, SHALL be published to every bidder. The bounty's queued bids SHALL be released, and a fresh sealed round SHALL open, in which anyone, including the solver who failed, can bid on the work that's left.

#### Scenario: Everyone sees the attempt
- **WHEN** a delivered attempt fails and the bounty reopens
- **THEN** every bidder in the fresh round can see the attempt, and no one's earlier queued price stands

#### Scenario: A sock gains nothing from seeing it
- **WHEN** a runner that ran a failed attempt also bids, under another identity, in the fresh round
- **THEN** it knows nothing about the attempt that the other bidders don't

### Requirement: Unsolved cases join the definition
When a "not solved" challenge against a bounty's winning contribution is upheld, its failing case SHALL be added to the bounty's public definition of solved, recorded on the ledger, and the bounty SHALL reopen as for a failed attempt.

#### Scenario: A case added
- **WHEN** a "not solved" challenge is upheld
- **THEN** the bounty reopens with the case in its public definition, and the next attempt must pass it

### Requirement: A split rejection keeps the bond
A delivery that passes its attested runs, splits its first jury and is rejected by the second, or whose runners never agree, SHALL get its bond back. Its deposit SHALL pay for the checks that ran, the attempt SHALL be published and the bounty SHALL reopen. A clear failure, a missing or late delivery, failing tests or a unanimous rejection, SHALL still forfeit the bond.

#### Scenario: Rejected on a split
- **WHEN** the first jury splits and the second rejects the delivery
- **THEN** the solver gets its bond back, its deposit pays both juries and the runners, and it can bid again in the fresh round

### Requirement: Checks paid by the contributor
Every check run on a delivery SHALL be paid from the assigned solver's check deposit, never from the bounty: a published run fee to each attested runner whose result stands, and a published verdict fee to each counted verdict on either jury. The deposit SHALL be the oracle reserve, the fees for one full attempt's checks. Whether a bounty is worth bidding on, checks included, SHALL be the solver's judgement.

#### Scenario: The solver pays its checks
- **WHEN** a delivery's tests run on the attested runners and two juries judge it
- **THEN** each runner whose result stands and each juror with a counted verdict is paid its fee from the solver's deposit, and the bounty pays nothing for them

#### Scenario: Splitting the jury costs the splitter
- **WHEN** a solver delivers junk that splits the first jury, is rejected by the second, and gets its bond back
- **THEN** it has paid every check from its deposit, so repeating the attempt costs it the checks each time

#### Scenario: No room needed in the price
- **WHEN** a bounty holds 300
- **THEN** its price cap is computed on all 300, as before oracle fees

### Requirement: Award modes
A published parameter SHALL choose how a bounty's job is awarded: `auction` (the sealed rounds, assignment and delivery above, unchanged), `race` or `claim`. In `race` and `claim` there SHALL be no bids, rounds or reserve: the bounty pays its funds, as set by its funders, to the winning contribution, through the same instalments, clawback and market fee.

#### Scenario: The auction is unchanged
- **WHEN** the mode is `auction`
- **THEN** every requirement on sealed rounds, assignment and delivery applies as before

#### Scenario: No price to bid
- **WHEN** the mode is `race` or `claim`
- **THEN** the winning contribution is paid the bounty's funds, less the market fee, and no bid or reserve exists

### Requirement: Registration check
In `race` and `claim`, opening a bounty SHALL cost a published registration fee in coin, paid by whoever opens it, for an AI check. The check SHALL write acceptance criteria from the author's requirements, which the author approves; SHALL refuse a bounty below a published size floor, which may be bundled with others; and SHALL publish an effort estimate. A bounty of 0 coin SHALL be allowed.

#### Scenario: Too small
- **WHEN** an issue's estimated effort is below the size floor
- **THEN** no bounty opens for it alone, the fee is kept for the check, and it can be bundled with other small issues into one bounty

#### Scenario: Zero coin
- **WHEN** a bounty passes the check with no funds
- **THEN** it opens, and its winning contribution is paid nothing in coin

### Requirement: The gated race
In `race`, starting an attempt SHALL pay a published attempt fee, and SHALL be published with the count of attempts in progress. Anyone SHALL submit a solution, sealed to the oracles, with a check deposit. Submissions SHALL be checked in arrival order, and the first through every gate of the constitution and the bounty's acceptance criteria SHALL win. A submission after the bounty is won SHALL go unchecked and pay the evaluation fee.

#### Scenario: First through the gates wins
- **WHEN** two submissions arrive and the first fails a gate while the second passes every gate
- **THEN** the second wins, and the first's deposit pays for its checks

#### Scenario: Too late
- **WHEN** a submission arrives after the bounty was won
- **THEN** it isn't checked, and it pays the evaluation fee

#### Scenario: An attempt costs
- **WHEN** a solver starts an attempt
- **THEN** it pays the attempt fee, which isn't refunded, and the published count of attempts rises by one

### Requirement: Claim then build
In `claim`, a solver SHALL claim a bounty with a bond, a published share of its funds, and get exclusive time scaled to the effort estimate. A delivery through every gate SHALL win and release the bond. A failed delivery or a timeout SHALL forfeit the bond to the bounty and pass the claim to the next solver who claims.

#### Scenario: Claim fails
- **WHEN** a claimant's delivery fails a gate, or its time runs out
- **THEN** its bond goes to the bounty, and the bounty is open to claim again

### Requirement: The rising price
In `race` and `claim`, a bounty's price SHALL open at a published share of its funds and rise daily by a published share until the first attempt or claim locks it. The winning contribution SHALL be paid the locked price, and the rest of the funds SHALL be refunded by input when the bounty is paid. The poster's registration fee SHALL be refunded from the bounty with the finder's fee; a bundle's parts' reporters SHALL share the finder's fee.

#### Scenario: Locked by the first attempt
- **WHEN** a bounty opened at 50 % of its funds, rising 10 % a day, gets its first attempt on its third day
- **THEN** its price is locked at 70 % of its funds, and the winner is paid that

#### Scenario: Registration refunded when solved
- **WHEN** a bounty is paid
- **THEN** its poster gets its registration fee back with the finder's fee; for a bounty never paid, the fee stays spent

### Requirement: Failed fixes aren't resubmitted
In `race`, a submission the AI similarity check recognizes as a failed submission's fix on the same bounty SHALL be rejected unchecked, from any account, for the evaluation fee. Its submitter MAY appeal the rejection, at its own cost, to an AI jury of a published size from different providers; if the jury finds the fix independent, it SHALL be checked like any submission. A failed submission's author MAY appeal once, for the same fix, to the second jury.

#### Scenario: A variant from a second account
- **WHEN** a fix fails and the same fix is submitted again from another account
- **THEN** it's rejected unchecked, and the account pays the evaluation fee

#### Scenario: An independent fix flagged as a duplicate
- **WHEN** an independent fix is rejected as a duplicate and its submitter appeals
- **THEN** the appeal jury, one evaluator per provider, finds it independent, and it's checked like any submission

#### Scenario: One appeal
- **WHEN** the author of a failed submission appeals it
- **THEN** the fix is checked again by the second jury; a second appeal is refused
