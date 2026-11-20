# Spec Delta

## Purpose

Defines how proof-of-fix's code lives on Radicle for the testnet: where its public history starts, what the seed replicates, how bounties point at Radicle issues and patches, and what the merge model on Radicle must guarantee.

## ADDED Requirements

### Requirement: The public history starts from the scrubbed snapshot
The Radicle repository SHALL be created from one commit of the scrubbed snapshot, whose scan passed, with no commit of Forgejo's history in it or in any ref published with it.

#### Scenario: Inspecting the published repository
- **WHEN** anyone clones the Radicle repository right after publication
- **THEN** its history has a single root commit, the snapshot's, and no ref points to a Forgejo commit

#### Scenario: A scan that isn't clean
- **WHEN** the snapshot's scan reports any finding
- **THEN** nothing is published, and the tool names the files and kinds of finding, never the values

### Requirement: The seed replicates proof-of-fix only
A seed node run for this deployment SHALL use a selective seeding policy that replicates proof-of-fix's repository and no other. Which host runs it SHALL be the owner's decision; no host SHALL be started without their go.

#### Scenario: Another repository is announced to the seed
- **WHEN** a peer announces a different repository to the seed
- **THEN** the seed doesn't fetch or store it

### Requirement: A bounty refers to a Radicle issue
An issue registered on-chain SHALL carry a reference to a Radicle issue in proof-of-fix's repository, so that anyone can find the issue's text from the chain and the bounty from the issue. Funding SHALL be possible straight from `pofctl`, with no bot.

#### Scenario: Funding an issue from pofctl
- **WHEN** a funder runs `pofctl` with a Radicle issue id and an amount
- **THEN** the issue is registered on-chain with that reference, the pledge is made once bounties are open, and `pofctl` prints the bounty and the issue

### Requirement: A fix is a Radicle patch
A submission's fix SHALL be the head commit of a Radicle patch on proof-of-fix's repository. A drawn validator SHALL fetch that commit from Radicle, check it against the opened commitment and the head on-chain, and judge it, with no forge involved.

#### Scenario: A validator judges a patch
- **WHEN** a validator is drawn for a submission whose fix is a patch revision's commit
- **THEN** it fetches that commit from its Radicle node, refuses unless its base is the head on-chain, and runs the check

#### Scenario: The patch isn't reachable
- **WHEN** the validator's node can't fetch the commit within the seal window
- **THEN** it seals a failing verdict whose receipt says the fix wasn't available, instead of staying silent

### Requirement: The canonical main never silently differs from the head
Whatever merge model the spike chooses, a canonical `main` on Radicle that differs from `Heads.head(repo)` SHALL be detectable by anyone with `pofctl verify-head`, and no tool of this deployment SHALL build, judge or publish from such a `main`.

#### Scenario: Delegates push past the chain
- **WHEN** enough delegates push a commit the chain never judged and it becomes the canonical `main`
- **THEN** `pofctl verify-head` reports the mismatch, and validators keep judging against the head on-chain

### Requirement: Delegates follow the seats
The seated validators SHALL be the repository's delegates (candidate a, decided 2026-11-18). Each seated validator's node SHALL sign only an identity revision whose delegates equal the seats on-chain, and a `verify-delegates` check SHALL compare the identity document's delegates with the seats and fail on a difference.

#### Scenario: A validator is seated
- **WHEN** a validator becomes seated on-chain and its node has published `main` at the head
- **THEN** the seated nodes accept an identity revision adding it, and `verify-delegates` passes once the revision is accepted

#### Scenario: A revision that doesn't match the chain
- **WHEN** a delegate proposes a revision adding a key that isn't seated on-chain
- **THEN** every honest seated node refuses it, and `verify-delegates` fails if it is ever accepted

### Requirement: A seat maps to one Radicle node key on-chain
Each validator SHALL record its Radicle node ID on-chain when it registers, and `verify-delegates` SHALL read the seats' node IDs from the chain. A seat without a node ID SHALL NOT be counted as a delegate.

#### Scenario: A seated validator without a node ID
- **WHEN** a validator is seated but registered no Radicle node ID
- **THEN** no honest node signs an identity revision adding a key for it, and `verify-delegates` reports the seat as unmapped

#### Scenario: Two registrations name one node
- **WHEN** a key registers with a Radicle node ID that another registered validator, neither leaving nor exited, holds
- **THEN** the registration is refused, and the node stays mapped to the first seat

#### Scenario: A validator moves to another node
- **WHEN** a validator wants its seat on another Radicle node
- **THEN** it leaves and registers again, with a new key, naming the new node; no call changes a registered node ID

### Requirement: One pending identity revision at a time
A seated node SHALL NOT propose a new identity revision while an earlier one is pending, and SHALL review pending revisions in order.

#### Scenario: Two seat changes close together
- **WHEN** two seat changes happen before the first revision is accepted
- **THEN** the second revision is proposed only after the first is accepted or rejected, and the delegates end equal to the seats on-chain
