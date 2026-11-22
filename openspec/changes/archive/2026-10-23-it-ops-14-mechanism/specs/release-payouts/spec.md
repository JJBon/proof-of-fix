# Spec Delta

## Purpose

Defines how each release's funds are divided among the people and costs that keep the project healthy: contributors, validators, the upstream author, infrastructure, insurance and the owner.

## ADDED Requirements

### Requirement: Fixed, published split per release
Each release's funds SHALL be split by shares fixed in the published parameters before the release. The shares SHALL sum to the whole and cover: contributors, validators and reviewers, the upstream author's escrow, infrastructure, the insurance pool, and the owner. No one SHALL change the shares for a release already open.

#### Scenario: Split adds up
- **WHEN** a release's funds are distributed
- **THEN** the amounts to each share sum exactly to the release's funds, and each matches its published share

#### Scenario: Shares can't change mid-release
- **WHEN** someone tries to change the shares while a release is open
- **THEN** the change applies only from the next release, and the ledger records when it was made

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
The validators' share SHALL be divided among validators and reviewers whose verdicts counted in that release, by verdicts that matched the final outcome. A validator SHALL earn nothing for verdicts discarded or overturned.

#### Scenario: Overturned verdict earns nothing
- **WHEN** jurors overturn a validators' verdict on appeal
- **THEN** the validators who voted with the overturned majority get no share for that challenge

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
