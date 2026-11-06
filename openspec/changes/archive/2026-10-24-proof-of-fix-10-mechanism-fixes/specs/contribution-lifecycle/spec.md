# Spec Delta

## MODIFIED Requirements

### Requirement: Entry stake
A contribution SHALL be accepted for evaluation only with an entry stake locked from the contributor's account, or from a sponsor's account (see "Sponsored stakes"). The required stake SHALL grow with the contribution's size and risk class, as defined by the published parameters.

#### Scenario: Stake locked on submission
- **WHEN** a contributor submits a contribution and their balance covers the required stake
- **THEN** the stake moves from their available balance to a locked balance tied to that contribution, and the contribution enters evaluation

#### Scenario: Insufficient balance
- **WHEN** a contributor's available balance is below the required stake and no sponsor posts it
- **THEN** the submission is refused, and nothing is locked or recorded as a contribution

#### Scenario: Larger contributions need larger stakes
- **WHEN** two contributions differ only in size, one at the merged-PR median (about 78 changed lines) and one at the stale-PR median (about 1,098)
- **THEN** the larger one requires a strictly larger stake and at least as many validators

### Requirement: Payment held in escrow
The reward for a contribution SHALL be set aside in escrow when it enters the beta build. None of it SHALL be paid out before its challenge window closes and it settles, and after that it SHALL be paid only in the published number of instalments, one per release, starting at the release after it settles.

#### Scenario: No early payout
- **WHEN** a contribution is in the beta build and its challenge window is still open
- **THEN** its reward stays in escrow, and neither the reward nor the stake can be withdrawn

#### Scenario: Paid in instalments
- **WHEN** an accepted contribution's reward is paid
- **THEN** it is paid in the published number of equal instalments, the first at the release after it settles and one at each following release, and whatever hasn't been paid stays in escrow

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

## ADDED Requirements

### Requirement: Clawback
Until its last reward instalment is paid, an accepted contribution SHALL remain open to challenge with the same proof rules. An upheld challenge in that period SHALL forfeit every unpaid instalment and the severity's share of the stake, which is still locked; the rest of the stake SHALL return.

#### Scenario: Defect found after acceptance
- **WHEN** a valid challenge against an accepted contribution is upheld before its last instalment
- **THEN** the unpaid instalments and the severity's share of the stake are forfeited (shared as the challenges spec says), the paid instalments stay with the contributor, and the ledger records it

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
