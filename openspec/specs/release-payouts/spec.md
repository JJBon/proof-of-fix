# release-payouts Specification

## Purpose
Defines how each release's funds are divided among the people and costs that keep the project healthy: contributors, validators, the upstream author, infrastructure, insurance and the owner.

## Requirements

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

### Requirement: Contributors paid for settled contributions
The contributors' share of a release SHALL be divided among the contributions entering that release's beta build, by reward weight, and held in each one's escrow. A contribution SHALL be paid its share only if it settles as accepted. A slashed contribution's share SHALL return to the contributors' pool and roll over to the next release.

#### Scenario: Divided among the contributions entering the beta build
- **WHEN** a release's beta build takes in four contributions
- **THEN** the release's contributors' share, plus any amount rolled over, is split among those four by reward weight and escrowed

#### Scenario: Only accepted contributions are paid
- **WHEN** three of those contributions settle as accepted and one is slashed
- **THEN** the three accepted ones are paid their escrowed shares, and the slashed one's share goes back to the contributors' pool

#### Scenario: Unused share rolls over
- **WHEN** a release's beta build takes in no contributions, or a contribution's share returns after a slash
- **THEN** that amount stays in the contributors' pool and is divided with the next release's share

### Requirement: Validators paid for work done
The validators' share SHALL be divided among members by units of work in that release: one unit for each counted verdict that matched the final outcome, and one for each completed review that wasn't missed. A validator SHALL earn nothing for verdicts discarded or overturned, or for missed reviews.

#### Scenario: Overturned verdict earns nothing
- **WHEN** jurors overturn a validators' verdict on appeal
- **THEN** the validators who voted with the overturned majority get no share for that challenge

#### Scenario: Reviews are paid work
- **WHEN** a release had reviews but no challenge went to a panel
- **THEN** the validators' share is divided among the reviewers by their completed reviews, instead of rolling over

### Requirement: Upstream author's escrow
The author's share SHALL accrue to an escrow account. Only a claimant who proves control of the upstream project SHALL withdraw it. The proof combines a signed statement with a matching commit or file in the upstream's own repository. The mechanism SHALL never assign the author an address.

#### Scenario: Unclaimed share accrues
- **WHEN** releases are distributed and no claim has been verified
- **THEN** the author's share keeps accruing in escrow, and nothing is paid out

#### Scenario: Verified claim
- **WHEN** a claimant presents a signed statement and a commit in the upstream repository naming the same key
- **THEN** the escrowed balance becomes withdrawable to that key, and the ledger records the claim with its evidence

#### Scenario: Unverified claim
- **WHEN** a claim lacks the upstream commit, or the commit names a different key
- **THEN** the claim is refused, and the escrow is unchanged

### Requirement: Owner's share capped, vested and without discretion
The owner's share SHALL be no more than a published cap. It SHALL vest over a published period, so unvested amounts are forfeited to the insurance pool if the owner leaves. Holding the share SHALL give no vote, no validator weight and no say over any payout.

#### Scenario: Cap enforced
- **WHEN** parameters are published with an owner share above the cap
- **THEN** they are refused

#### Scenario: Owner can't validate on the share
- **WHEN** validators are selected
- **THEN** the owner's share adds no weight, and the owner can validate only with a separate validator stake, under the same rules as anyone else

### Requirement: Infrastructure and insurance
The infrastructure share SHALL pay for CI and automated agents. The insurance pool SHALL cover users or contributors harmed by an upheld regression up to a published limit per release. Unspent infrastructure funds SHALL roll over, never return to any person.

#### Scenario: Insurance pays out
- **WHEN** an upheld challenge has the severity "crash or data loss" and a harmed party files a covered claim
- **THEN** the insurance pool pays up to the published limit, and the ledger records it

#### Scenario: Unspent infrastructure funds roll over
- **WHEN** a release's infrastructure share isn't fully spent
- **THEN** the remainder stays in the infrastructure account for later releases

### Requirement: Splitting earns nothing
The reward weights of the parts of a change SHALL add up to no more than the weight of the same change submitted as one contribution. A contribution's weight and an author's total weight in one release SHALL both be capped at the published value.

#### Scenario: One change split into eight
- **WHEN** a change of N changed lines is submitted as eight contributions of about N/8 lines each
- **THEN** their weights add up to no more than the weight of one N-line contribution, while each part pays its own stake and check fee

#### Scenario: Split above the cap
- **WHEN** an author's contributions in one release add up to more than the cap
- **THEN** their weights are scaled down so the author's total equals the cap, so splitting a change above the cap earns no more than one capped contribution

### Requirement: Reward capped relative to the stake
A contribution's escrowed reward SHALL be at most a published multiple of its stake. When the division by weight would give it more, the excess SHALL stay in the contributors' pool and roll over to the next release.

#### Scenario: Lone contribution in a sparse release
- **WHEN** a beta build takes in one contribution whose share of the contributors' pool is above the cap
- **THEN** it is escrowed exactly the cap, and the rest of the pool stays for the next release

#### Scenario: Under the cap
- **WHEN** every contribution's share by weight is under the cap
- **THEN** the division is unchanged

#### Scenario: Nothing lost
- **WHEN** rewards are capped in a release
- **THEN** the escrowed rewards plus what stays in the pool equal the pool before the beta build

### Requirement: Funding follows use
Before a release is funded, if the contributors' pool already holds more than a published buffer of releases' worth of the contributors' share, the release's whole funding SHALL be scaled down by the same factor for every share, by the surplus over the buffer, down to nothing. The published shares SHALL stay as they are.

#### Scenario: Pool within the buffer
- **WHEN** the contributors' pool holds at most the buffer when a release opens
- **THEN** the release is funded in full

#### Scenario: Pool over the buffer
- **WHEN** the contributors' pool holds more than the buffer when a release opens
- **THEN** every share of that release is reduced by the same factor, the amounts still match the published shares of the reduced funding, and the ledger records the factor

#### Scenario: Buffer switched off
- **WHEN** the published buffer is zero
- **THEN** every release is funded in full, as before
