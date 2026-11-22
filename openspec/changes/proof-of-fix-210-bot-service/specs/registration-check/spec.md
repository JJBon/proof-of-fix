# Spec Delta

## Purpose
The judges' registration check, which opens a bounty for a registered issue: the oracle quorum signs RaceV2's `accept` and a node relays it. On the devnet, the role seats' nodes run it unattended with the fake judge, for registrations that a `bounty`-labelled issue claims, so no person or bot needs the seats' keys to open a bounty.

## ADDED Requirements

### Requirement: The seats check a claimed registration
With `ORACLE_REGISTRATION_CHECK=on`, a node SHALL check each registration that is still `Posted` with no bounty, is in its repository, and is validly claimed by a `bounty`-labelled issue on that repository, by the rule the bounty bot uses. It SHALL check nothing else. The setting SHALL be off by default.

#### Scenario: Claimed
- **WHEN** registration 7 is `Posted` and issue #12, labelled `bounty`, validly claims it
- **THEN** each seat's node with the check on signs its `accept`

#### Scenario: Not claimed
- **WHEN** registration 8 is `Posted` and no labelled issue claims it
- **THEN** no node signs anything for it

#### Scenario: Off
- **WHEN** a node runs without `ORACLE_REGISTRATION_CHECK=on`
- **THEN** it signs no `accept`

### Requirement: Only the fake judge checks registrations, at a fixed weight
A node SHALL sign a registration's `accept` only with the fake judge, at the configured `ORACLE_REGISTER_WEIGHT` and a nonce of keccak256("pof-accept" ‖ race ‖ issue), so every seat signs the same digest. With any other judge, it SHALL sign nothing and log that real registration checks aren't supported yet.

#### Scenario: A real judge configured
- **WHEN** a node's judge is a model and a claimed registration waits
- **THEN** the node signs nothing for it and logs why

#### Scenario: The same digest
- **WHEN** five seats sign registration 7's `accept`
- **THEN** their signatures are over one digest, and together they meet the quorum

### Requirement: The exchange takes registration signatures from active oracle keys only
The exchange SHALL take an `accept` message under an issue only while that issue is `Posted` with no bounty, from an active oracle key, with a signature that recovers to that key over RaceV2's `Accept` digest for that issue. It SHALL keep one message per key and issue, and serve them to any reader.

#### Scenario: Not an oracle
- **WHEN** an address that isn't an active oracle key posts a signature for registration 7
- **THEN** the exchange refuses it with 403

#### Scenario: Already open
- **WHEN** a seat posts a signature for a registration whose bounty is open
- **THEN** the exchange refuses it

### Requirement: One node relays the quorum's accept
Once a node reads a quorum of valid signatures for a registration, the lowest-addressed signer SHALL relay `accept` at once; another signer SHALL relay only if the bounty still isn't open after `ORACLE_RELAY_GRACE` (30 s). A revert because the bounty opened meanwhile SHALL count as success.

#### Scenario: The normal case
- **WHEN** six seats sign registration 7
- **THEN** one `accept` is sent, by the lowest-addressed signer, and the bounty opens

#### Scenario: The relayer is down
- **WHEN** the lowest-addressed signer stops before relaying
- **THEN** another signer relays after the grace, and the bounty opens
