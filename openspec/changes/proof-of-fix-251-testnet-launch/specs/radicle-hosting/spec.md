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

### Requirement: Delegates follow the seats, if the spike chooses delegates
If the spike chooses the seated validators as delegates (candidate a), each seated validator's node SHALL sign only an identity revision whose delegates equal the seats on-chain, and a `verify-delegates` check SHALL compare the identity document's delegates with the seats and fail on a difference.

#### Scenario: A validator is seated
- **WHEN** a validator becomes seated on-chain and its node has published `main` at the head
- **THEN** the seated nodes accept an identity revision adding it, and `verify-delegates` passes once the revision is accepted

#### Scenario: A revision that doesn't match the chain
- **WHEN** a delegate proposes a revision adding a key that isn't seated on-chain
- **THEN** every honest seated node refuses it, and `verify-delegates` fails if it is ever accepted
