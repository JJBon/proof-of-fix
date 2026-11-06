# contribution-lifecycle Specification

## Purpose
Defines how one contribution moves from submission to settlement: what the contributor stakes, when it reaches users in a beta build, how its payment is held, and how it ends paid or slashed.

## Requirements

### Requirement: Entry stake
A contribution SHALL be accepted for evaluation only with an entry stake locked from the contributor's account, from a sponsor's account (see "Sponsored stakes"), or partly from pledged unpaid rewards (see "Pledged stake"). The required stake SHALL grow with the contribution's size and risk class, as defined by the published parameters.

#### Scenario: Stake locked on submission
- **WHEN** a contributor submits a contribution and their balance, with any pledge allowed, covers the required stake
- **THEN** the stake moves to a locked balance tied to that contribution, and the contribution enters evaluation

#### Scenario: Insufficient balance
- **WHEN** a contributor's available balance and allowed pledges together are below the required stake, and no sponsor posts it
- **THEN** the submission is refused, and nothing is locked or recorded as a contribution

#### Scenario: Larger contributions need larger stakes
- **WHEN** two contributions differ only in size, one at the merged-PR median (about 78 changed lines) and one at the stale-PR median (about 1,098)
- **THEN** the larger one requires a strictly larger stake and at least as many validators

### Requirement: Deterministic gate before beta
A contribution SHALL reach the beta build only after it passes the project's deterministic checks (build, format, lint, tests). A contribution that fails them SHALL be returned to the contributor with its stake refunded minus a fixed check fee.

#### Scenario: Checks pass
- **WHEN** a contribution passes every deterministic check
- **THEN** it is merged into the next beta build and its challenge window opens

#### Scenario: Checks fail
- **WHEN** a contribution fails a deterministic check
- **THEN** it does not reach the beta build, and the contributor gets the stake back minus the check fee, which goes to infrastructure

### Requirement: Payment held in escrow
The reward for a contribution SHALL be set aside in escrow when it enters the beta build. None of it SHALL be paid out before its challenge window closes and it settles, and after that it SHALL be paid only in the published number of instalments, one per release, starting at the release after it settles.

#### Scenario: No early payout
- **WHEN** a contribution is in the beta build and its challenge window is still open
- **THEN** its reward stays in escrow, and neither the reward nor the stake can be withdrawn

#### Scenario: Paid in instalments
- **WHEN** an accepted contribution's reward is paid
- **THEN** it is paid in the published number of equal instalments, the first at the release after it settles and one at each following release, and whatever hasn't been paid stays in escrow

### Requirement: Challenge window
Each contribution in a beta build SHALL have a challenge window of a published length, counted from the beta release. The window SHALL be extended once, by a published amount, when a challenge is open at its end.

#### Scenario: Window closes with no challenge
- **WHEN** the window ends and no challenge was filed against the contribution
- **THEN** the contribution settles as accepted

#### Scenario: Window extended for a pending challenge
- **WHEN** the window ends while a challenge against the contribution is still being judged
- **THEN** the window is extended once, and the contribution doesn't settle until the challenge is decided

### Requirement: Settlement outcomes
A contribution SHALL settle as exactly one of the following:
- **accepted:** reward paid in instalments from the next release; the stake stays locked until the last instalment (see "Clawback");
- **slashed:** part of the stake and the escrowed reward forfeited, by severity;
- **withdrawn:** the contributor withdrew before the beta release, stake returned minus the check fee.

Every settlement SHALL be recorded in the ledger.

#### Scenario: Accepted
- **WHEN** a contribution's window closes with no upheld challenge
- **THEN** it is accepted with nothing paid yet; its stake stays locked, the instalments start at the next release, and the stake returns with the last one; the ledger records each movement

#### Scenario: Slashed
- **WHEN** a challenge against the contribution is upheld
- **THEN** the contributor loses the escrowed reward and the severity's share of the stake, the rest of the stake is returned, and the ledger records each movement

#### Scenario: Withdrawn before beta
- **WHEN** a contributor withdraws a contribution that hasn't reached a beta build
- **THEN** the stake is returned minus the check fee if checks already ran, and the contribution can't settle any other way

### Requirement: Maintainers keep the merge decision
Maintainers SHALL be able to decline a contribution before it enters a beta build without slashing the contributor, within the limits in "Declines are limited and appealable". The mechanism SHALL NOT merge anything into the project's main line by itself.

#### Scenario: Maintainer declines
- **WHEN** a maintainer declines a contribution before it enters a beta build
- **THEN** it is returned with its stake refunded in full, no reward or slash applies, and the decline is recorded with the maintainer and a reason

### Requirement: Clawback
Until its last reward instalment is paid, an accepted contribution SHALL remain open to challenge with the same proof rules. An upheld challenge in that period SHALL forfeit every unpaid instalment, including any part pledged to back other stakes, and the severity's share of the stake, which is still locked; the rest of the stake SHALL return.

#### Scenario: Defect found after acceptance
- **WHEN** a valid challenge against an accepted contribution is upheld before its last instalment
- **THEN** the unpaid instalments and the severity's share of the stake are forfeited (shared as the challenges spec says), the paid instalments stay with the contributor, and the ledger records it

#### Scenario: Defect found while the reward is pledged
- **WHEN** a contribution is clawed back while part of its unpaid reward is pledged to another contribution's stake
- **THEN** the other contribution keeps its full stake until it settles. Whatever of the pledge then comes back is forfeited like the rest of the clawed-back escrow, and never reaches the contributor.

#### Scenario: After the last instalment
- **WHEN** a challenge is filed against a contribution whose reward has been fully paid
- **THEN** it is refused, with nothing taken from the challenger beyond the filing fee

### Requirement: Sponsored stakes
An existing contributor with at least one accepted contribution SHALL be able to post the entry stake for another person's contribution as its sponsor. A slash SHALL be taken from the sponsor's posted stake; when the contribution is accepted, the stake SHALL return to the sponsor.

#### Scenario: A newcomer is sponsored
- **WHEN** a sponsor with an accepted contribution posts the stake for a newcomer's contribution
- **THEN** the stake is locked from the sponsor's account, and the newcomer's balance is untouched

#### Scenario: A sponsored contribution is slashed
- **WHEN** a sponsored contribution is slashed
- **THEN** the forfeited part comes out of the sponsor's posted stake, and the rest returns to the sponsor

#### Scenario: Only proven contributors sponsor
- **WHEN** an account with no accepted contribution tries to sponsor
- **THEN** it is refused, and nothing is locked

### Requirement: A maintainer's own contribution needs another approver
A contribution authored by a maintainer (the owner included) SHALL enter a beta build only after another maintainer approves it. Where there is no other maintainer, a validator panel that excludes the author SHALL decide by majority.

#### Scenario: Approved by another maintainer
- **WHEN** a maintainer's contribution passes the checks and a different maintainer approves it
- **THEN** it enters the next beta build like any other

#### Scenario: Only maintainer
- **WHEN** the author is the only maintainer
- **THEN** a validator panel excluding the author decides whether it enters the beta build, and it doesn't enter without a majority

### Requirement: Declines are limited and appealable
A maintainer SHALL decline at most the published share of others' contributions in a release. A declined contributor SHALL be able to appeal the decline to a validator panel. A decline the panel overturns SHALL send the contribution to the next beta build.

#### Scenario: Over the limit
- **WHEN** a maintainer has already declined the published share of others' contributions in the current release
- **THEN** a further decline needs a validator panel's majority, and without one the contribution goes to the beta build

#### Scenario: Decline overturned on appeal
- **WHEN** a declined contributor appeals and the panel finds no reason to decline
- **THEN** the contribution enters the next beta build, and the decline is recorded as overturned against the maintainer

### Requirement: Pledged stake
A contributor with an accepted contribution SHALL be able to cover part of a new entry stake by pledging the unpaid reward of their own accepted contributions in clawback (the backing contributions). The published limits SHALL apply:
- a pledge covers at most a fixed share of the stake;
- a pledge takes at most a fixed share of each backing reward;
- nothing is pledged from a contribution with an open challenge;
- a sponsored stake is never pledged.

#### Scenario: Stake partly pledged
- **WHEN** a contributor with an accepted contribution in clawback, and no challenge open on it, submits a contribution and pledges from it within both limits
- **THEN** the pledged amount moves from the backing contribution's escrow into the new contribution's locked stake, the rest of the stake comes from the contributor's balance, and the ledger records both with the backing contribution

#### Scenario: Pledge over a limit
- **WHEN** a pledge would cover more than the published share of the stake, or take more than the published share of a backing contribution's unpaid reward
- **THEN** the submission is refused, and nothing is locked or recorded as a contribution

#### Scenario: Backing contribution under challenge
- **WHEN** a contributor tries to pledge from a contribution with an open challenge
- **THEN** that pledge is refused, and nothing is locked

#### Scenario: Sponsored stake
- **WHEN** a contribution's stake is posted by a sponsor
- **THEN** no part of it can be pledged

### Requirement: Pledges in settlement
A pledged stake SHALL be locked and settled like any stake, except that:
- a forfeit is taken from the part posted from the balance first, and from the pledge after;
- what is left of a pledge returns to its backing contribution's escrow while that contribution's clawback is open, and to the contributor once the clawback has ended.

#### Scenario: Pledged contribution slashed
- **WHEN** a contribution whose stake is partly pledged is slashed
- **THEN** the forfeit comes from the part posted from the balance first and then from the pledge. Whatever is left of the pledge returns as for any settlement, and whatever is left of the balance part returns to the contributor.

#### Scenario: Pledge returned on settlement
- **WHEN** a contribution with a pledged stake settles without a forfeit
- **THEN** each pledge returns to its backing contribution's escrow if that contribution is still in clawback, or to the contributor if its clawback has ended; nothing is created or lost

### Requirement: Stake indexed to the expected reward
Once releases have paid rewards, the entry stake SHALL be a published share of the contribution's expected reward, at least a published floor for its size and at most the fixed stake for its size, times its risk multiplier. The expected reward SHALL be the reward per unit of weight over a published window of recent releases, times the contribution's weight. Before any reward is paid, the fixed stake SHALL apply.

#### Scenario: No history yet
- **WHEN** a contribution is submitted before any beta build has escrowed a reward
- **THEN** its stake is the fixed stake for its size and risk class

#### Scenario: The stake follows the reward
- **WHEN** the reward per unit of weight over the window falls, for example because many more contributions share each release
- **THEN** the stake for the same size and risk falls with it, never below the floor for that size

#### Scenario: Never above the fixed stake
- **WHEN** the expected reward is large enough that its share exceeds the fixed stake for that size
- **THEN** the stake is the fixed stake

#### Scenario: Larger contributions still need larger stakes
- **WHEN** two contributions submitted at the same time differ only in size, one at about 78 changed lines and one at about 1,098
- **THEN** the larger one requires a strictly larger stake

#### Scenario: Anyone can recompute the stake
- **WHEN** a beta build ships
- **THEN** the ledger records the reward per unit of weight it sets for the window, so the stake of any later submission can be recomputed from published records and parameters
