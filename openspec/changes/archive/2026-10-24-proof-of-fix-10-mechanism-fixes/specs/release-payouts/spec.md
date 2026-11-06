# Spec Delta

## MODIFIED Requirements

### Requirement: Fixed, published split per release
Each release's funds SHALL be split by shares fixed in the published parameters before the release. The shares SHALL sum to the whole and cover: contributors, validators and reviewers, the upstream author's escrow, infrastructure, the insurance pool, and the owner. No one SHALL change the shares for a release already open. A change that raises the share of a role the owner holds SHALL need a validator panel that excludes the owner.

#### Scenario: Split adds up
- **WHEN** a release's funds are distributed
- **THEN** the amounts to each share sum exactly to the release's funds, and each matches its published share

#### Scenario: Shares can't change mid-release
- **WHEN** someone tries to change the shares while a release is open
- **THEN** the change applies only from the next release, and the ledger records when it was made

#### Scenario: A change that would benefit the owner
- **WHEN** the owner proposes raising the validators' share while holding a validator stake
- **THEN** the change takes effect only if a validator panel excluding the owner approves it, and the ledger records the panel's decision

### Requirement: Validators paid for work done
The validators' share SHALL be divided among members by units of work in that release: one unit for each counted verdict that matched the final outcome, and one for each completed review that wasn't missed. A validator SHALL earn nothing for verdicts discarded or overturned, or for missed reviews.

#### Scenario: Overturned verdict earns nothing
- **WHEN** jurors overturn a validators' verdict on appeal
- **THEN** the validators who voted with the overturned majority get no share for that challenge

#### Scenario: Reviews are paid work
- **WHEN** a release had reviews but no challenge went to a panel
- **THEN** the validators' share is divided among the reviewers by their completed reviews, instead of rolling over

## ADDED Requirements

### Requirement: Splitting earns nothing
The reward weights of the parts of a change SHALL add up to no more than the weight of the same change submitted as one contribution. A contribution's weight and an author's total weight in one release SHALL both be capped at the published value.

#### Scenario: One change split into eight
- **WHEN** a change of N changed lines is submitted as eight contributions of about N/8 lines each
- **THEN** their weights add up to no more than the weight of one N-line contribution, while each part pays its own stake and check fee

#### Scenario: Split above the cap
- **WHEN** an author's contributions in one release add up to more than the cap
- **THEN** their weights are scaled down so the author's total equals the cap, so splitting a change above the cap earns no more than one capped contribution
