# Spec Delta

## ADDED Requirements

### Requirement: Anyone opens a bounty, the market funds it
In `race` and `claim`, anyone SHALL open a bounty by registering an issue, with the registration fee and the issue stake, without funding it. A bounty SHALL have no target or pledging deadline: once the registration check accepts the issue it SHALL open at once, and anyone SHALL pledge any coin to it while it's open. Its price rises over what it holds, so funders and solvers set its value.

#### Scenario: Opened with nothing in it
- **WHEN** the registration check accepts an issue nobody has funded yet
- **THEN** its bounty opens at once, its price on offer is 0, and anyone may pledge to it

#### Scenario: Funded while open
- **WHEN** funders pledge to an open bounty on different days
- **THEN** every pledge counts toward its price, before and after the lock, and pledges stop once it's won

### Requirement: One open bounty per issue
In `race` and `claim`, the registration check SHALL refuse an issue similar to one whose bounty is still open, won or being paid: no bounty opens, the registration fee stays spent on the check, and the issue stake returns. Funders SHALL add to the open bounty instead. Once that bounty is paid, refunded or closed unsolved, a new bounty MAY open for a similar issue.

#### Scenario: A similar issue is open
- **WHEN** an issue is registered while a similar issue's bounty is open
- **THEN** no bounty opens, the fee pays for the check, and the stake returns

#### Scenario: After it closes
- **WHEN** a similar issue's bounty has closed unsolved or been paid
- **THEN** a new bounty opens for the issue

### Requirement: One fix, one payout
In `race`, a submission the AI similarity check recognizes as a fix already paid on another bounty SHALL be rejected unchecked, from any account, for the evaluation fee, and its submitter MAY appeal the rejection like a duplicate's. A bounty that loses its fix this way SHALL stay open for a different fix, or sunset if nobody takes it.

#### Scenario: A later bounty on the same issue
- **WHEN** a fix was paid on a bounty and, once that bounty closed, the same fix is submitted to a new bounty for a similar issue
- **THEN** it's rejected unchecked, the submitter pays the evaluation fee, and the new bounty stays open for a different fix

### Requirement: Idle bounties sunset
In `race`, an open bounty SHALL close unsolved a published number of days after it opened, reopened or last had a submission checked, its funds returned by input, so the market retires bounties nobody wants. Attempts in progress and duplicates rejected unchecked SHALL NOT restart the count; attempts in progress end with the bounty. On-chain, anyone MAY trigger the close once the time has passed.

#### Scenario: Nobody takes it
- **WHEN** an open bounty has had no submission checked for the published number of days since it opened
- **THEN** it closes unsolved and its funders get their shares back

#### Scenario: Attempts don't keep it alive
- **WHEN** solvers start attempts every few days, or stop and start again, with no submission checked
- **THEN** the count isn't restarted, the bounty closes on time, and the attempts in progress end with it, their effort lost

#### Scenario: A checked submission restarts the count
- **WHEN** a submission fails its checks or is rejected on a split before that time
- **THEN** the count starts again from its result

#### Scenario: Duplicates don't keep it alive
- **WHEN** someone keeps submitting a failed fix's duplicate, each rejected unchecked
- **THEN** the count isn't restarted, and the bounty still closes on time

## MODIFIED Requirements

### Requirement: The rising price
In `race` and `claim`, a bounty's price SHALL be a share of its funds, opening at a published share and rising daily by a published share until the first attempt or claim locks the share. Pledges after the lock raise the price at that share. The winner SHALL be paid that share of the funds at its win, and the rest refunded by input when the bounty is paid. The registration fee SHALL be refunded with the finder's fee; a bundle's parts' reporters share the fee.

#### Scenario: Locked by the first attempt
- **WHEN** a bounty opened at 50 % of its funds, rising 10 % a day, gets its first attempt on its third day
- **THEN** its price is locked at 70 % of its funds, and the winner is paid that

#### Scenario: Pledged after the lock
- **WHEN** a bounty's share is locked at 70 % and a funder pledges more before it's won
- **THEN** the winner is paid 70 % of the larger funds, and every funder's refund is the same fraction of its pledge

#### Scenario: Registration refunded when solved
- **WHEN** a bounty is paid
- **THEN** its poster gets its registration fee back with the finder's fee; for a bounty never paid, the fee stays spent

### Requirement: Bounties and pledges
An issue SHALL become a bounty with a published definition of solved. In `auction`, it SHALL have a target amount: users SHALL pledge toward the target until a published deadline, and if the target isn't reached by then, every pledge SHALL be refunded in full. In `race` and `claim` it SHALL have no target (see "Anyone opens a bounty, the market funds it").

#### Scenario: Target reached
- **WHEN** pledges reach an auction bounty's target before its deadline
- **THEN** the bounty opens a sealed round, and the pledges are held in the bounty's escrow

#### Scenario: Target missed
- **WHEN** an auction bounty's deadline passes below its target
- **THEN** every pledge returns to its pledger, and nothing else moves

### Requirement: Issue stakes
Whoever submits an issue SHALL post a published issue stake. When the issue's bounty is paid, the stake SHALL return with a finder's fee from the bounty: 15 % of what the bounty pays out for the fix, the solver's price being the other 85 %. Where a treasury matches pledges, the finder's fee SHALL be smaller than the market fee. A junk issue's stake SHALL go to insurance; an issue that's never funded SHALL get its stake back.

#### Scenario: Real issue fixed
- **WHEN** an issue's bounty is paid after its fix ships and its instalments are paid
- **THEN** the reporter's stake returns, with the finder's fee on the winning price

#### Scenario: The split
- **WHEN** a bounty pays a winning price of 85
- **THEN** its reporter's finder's fee is 15

#### Scenario: Junk confirmed
- **WHEN** the treasury flags an issue as junk and a validator panel confirms it, or the fix delivered for it is slashed as junk
- **THEN** the reporter's stake goes to insurance, and the issue gets no bounty, or no further one

#### Scenario: Flag not confirmed
- **WHEN** the treasury flags an issue as junk and the panel doesn't confirm it
- **THEN** the stake stays posted, and the issue can still be funded

#### Scenario: Never funded
- **WHEN** an issue is neither funded nor solved before its bounty closes
- **THEN** the reporter's stake returns, with no fee

#### Scenario: Funding your own issue doesn't pay
- **WHEN** a reporter funds its own issue in full, where a treasury matches pledges
- **THEN** the finder's fee it receives is smaller than the market fee its own pledge paid on the same price

### Requirement: Quadratic matching
A published share of each release's treasury budget SHALL match pledges on bounties still gathering them, by weight: the sum over pledgers of their funder trust times the square root of their pledges, squared, less the sum of each pledger's trust squared times its pledges, scaled to fit that share. A match SHALL be capped at a published share of the bounty's target in `auction`, where it counts toward the target, and of its pledges in `race` and `claim`, until its price is locked.

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
- **WHEN** a bounty's match would exceed the published share of its target, or in `race` and `claim` of its pledges
- **THEN** it gets exactly the cap

#### Scenario: A match completes the target
- **WHEN** a match brings an auction bounty's funds to its target
- **THEN** the bounty opens its sealed round
