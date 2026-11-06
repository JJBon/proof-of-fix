# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
