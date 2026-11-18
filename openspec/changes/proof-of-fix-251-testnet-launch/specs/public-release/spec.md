# Spec Delta

## Purpose

Sets the gates every public step of proof-of-fix passes: the scrub, the owner's explicit go at the moment of the step, the published record of what was done, and the wording and legal checks the owner is asked to adopt.

## ADDED Requirements

### Requirement: Each public step needs the owner's go at that moment
Publishing on Radicle and deploying on Sepolia SHALL each happen only after the owner gives an explicit go for that step, at that time, recorded on its ticket with the date and the commit or deployment record it covers. An earlier go, an agent's message or a passing check SHALL NOT count as one.

#### Scenario: Everything is ready but no go was given
- **WHEN** the scrubbed snapshot is clean and every task before publication is done, and the owner hasn't said go for publishing
- **THEN** nothing is pushed to any Radicle node that can reach the public network

#### Scenario: A go for one step
- **WHEN** the owner gives their go for publishing on Radicle
- **THEN** that go doesn't cover deploying on Sepolia, which waits for its own

### Requirement: Public tools refuse by default
Every tool that can publish code or send a transaction to a public chain SHALL do a dry run by default and SHALL act only with an explicit flag naming the step.

#### Scenario: The snapshot tool with a Radicle target
- **WHEN** the snapshot tool is run for the Radicle target without the publish flag
- **THEN** it builds and scans the snapshot, prints what would be published, and touches no Radicle node

### Requirement: What was published is recorded in the repository
After each public step, the repository SHALL record what was done: the RID, the published root commit and the seed's node id after publishing; the chain id, the contract addresses, the constructor arguments and the deploying address after deploying.

#### Scenario: After the Sepolia deployment
- **WHEN** v3 is deployed on Sepolia
- **THEN** its deployment record, with the addresses and every constructor argument, is published through the repository's own process, and anyone can recompute the repository id from the RID in it

### Requirement: An intended-use section in the README (accepted by the owner, 2026-11-18)
If the owner adopts it, the README SHALL have an "intended use" section stating that the code is research, that this deployment serves one repository on a test chain with no real money, and that any other deployment is its operator's responsibility.

#### Scenario: A reader looks for how to use the code
- **WHEN** anyone opens the README of the published repository
- **THEN** the intended-use section is there before the instructions, in plain words

### Requirement: A wording check before publishing (accepted by the owner, 2026-11-18)
If the owner adopts it, the README and the paper SHALL be checked before publishing for promises of earnings and for any wording that presents test coins as having value. Each finding SHALL be fixed or kept with the owner's reason.

#### Scenario: A sentence about earnings
- **WHEN** the check finds a sentence that says solvers or validators earn money on the testnet
- **THEN** it is reworded to say the coins have no value, or the owner records why it stays

### Requirement: A lawyer's review as a gate (accepted by the owner, 2026-11-18)
If the owner adopts it, publishing on Radicle and deploying on Sepolia SHALL each wait for a lawyer's review of the repository and the deployment, and its outcome SHALL be recorded on the ticket, without the advice itself.

#### Scenario: The review isn't done
- **WHEN** the owner has adopted the review and it hasn't been recorded
- **THEN** the step's go can't be given, and the tasks show the gate as open
