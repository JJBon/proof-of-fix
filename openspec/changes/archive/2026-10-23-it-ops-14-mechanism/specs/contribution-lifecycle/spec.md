# Spec Delta

## Purpose

Defines how one contribution moves from submission to settlement: what the contributor stakes, when it reaches users in a beta build, how its payment is held, and how it ends paid or slashed.

## ADDED Requirements

### Requirement: Entry stake
A contribution SHALL be accepted for evaluation only with an entry stake locked from the contributor's account. The required stake SHALL grow with the contribution's size and risk class, as defined by the published parameters.

#### Scenario: Stake locked on submission
- **WHEN** a contributor submits a contribution and their balance covers the required stake
- **THEN** the stake moves from their available balance to a locked balance tied to that contribution, and the contribution enters evaluation

#### Scenario: Insufficient balance
- **WHEN** a contributor's available balance is below the required stake
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
The reward for a contribution SHALL be set aside in escrow when it enters the beta build and SHALL NOT be paid out before its challenge window closes and it settles.

#### Scenario: No early payout
- **WHEN** a contribution is in the beta build and its challenge window is still open
- **THEN** its reward stays in escrow, and neither the reward nor the stake can be withdrawn

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
- **accepted:** reward paid, stake returned;
- **slashed:** part of the stake and the reward forfeited, by severity;
- **withdrawn:** the contributor withdrew before the beta release, stake returned minus the check fee.

Every settlement SHALL be recorded in the ledger.

#### Scenario: Accepted
- **WHEN** a contribution's window closes with no upheld challenge
- **THEN** the contributor receives the escrowed reward and their full stake, and the ledger records both

#### Scenario: Slashed
- **WHEN** a challenge against the contribution is upheld
- **THEN** the contributor loses the escrowed reward and the severity's share of the stake, the rest of the stake is returned, and the ledger records each movement

#### Scenario: Withdrawn before beta
- **WHEN** a contributor withdraws a contribution that hasn't reached a beta build
- **THEN** the stake is returned minus the check fee if checks already ran, and the contribution can't settle any other way

### Requirement: Maintainers keep the merge decision
Maintainers SHALL be able to decline a contribution for any reason before it enters a beta build, without slashing the contributor. The mechanism SHALL NOT merge anything into the project's main line by itself.

#### Scenario: Maintainer declines
- **WHEN** a maintainer declines a contribution before it enters a beta build
- **THEN** it is returned with its stake refunded in full, and no reward or slash applies
