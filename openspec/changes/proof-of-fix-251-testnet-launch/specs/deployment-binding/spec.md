# Spec Delta

## Purpose

Fixes, at construction, what one deployment of the contracts serves and where it runs: one repository, one chain, its waiting windows and its accepted proof types, so that nobody can widen them afterwards.

## ADDED Requirements

### Requirement: One repository, fixed at construction
A deployment SHALL take exactly one repository id, `keccak256(RID)` of a Radicle repository, and that repository's genesis head as constructor arguments. Both SHALL be immutable. Construction SHALL fail if either is zero.

#### Scenario: Deployed for proof-of-fix
- **WHEN** the contracts are deployed with proof-of-fix's repository id and the commit of its Radicle `main` at that moment
- **THEN** the head registry lists exactly that repository, with that commit as its genesis head, and no function adds another

#### Scenario: No repository given
- **WHEN** a deployment is attempted with a zero repository id or a zero genesis head
- **THEN** the constructor reverts and nothing is deployed

### Requirement: Other repositories are refused
The contracts SHALL refuse to register an issue, open a bounty or take a pledge for any repository but the one fixed at construction, including an issue with no repository.

#### Scenario: An issue for another repository
- **WHEN** anyone registers an issue naming a repository id other than the deployment's
- **THEN** the call reverts, and no fee or stake is taken

#### Scenario: An issue with no repository
- **WHEN** anyone registers an issue with a zero repository id
- **THEN** the call reverts, so no bounty can be won without moving the head

### Requirement: Sepolia only
The constructor SHALL revert unless `block.chainid` is Sepolia's (11155111), or one of the published local test chain ids if the owner accepts them (design L2). The deployment's chain id SHALL be readable from the contracts.

#### Scenario: Deploying on Sepolia
- **WHEN** the contracts are deployed on Sepolia
- **THEN** construction succeeds and the contracts report chain id 11155111

#### Scenario: Deploying on mainnet or another public chain
- **WHEN** the same bytecode is deployed on Ethereum mainnet or any public chain other than Sepolia
- **THEN** the constructor reverts

### Requirement: The deploy script refuses any chain but Sepolia
The public deploy script SHALL read the RPC endpoint's chain id before sending anything and SHALL stop, sending no transaction, unless it is 11155111. It SHALL also stop unless the Radicle repository it is given exists and its canonical `main` is the genesis head passed to the constructor.

#### Scenario: Pointed at mainnet
- **WHEN** the deploy script is run against an endpoint that reports chain id 1
- **THEN** it exits with an error naming the chain id, and no transaction is signed or sent

#### Scenario: The repository doesn't exist yet
- **WHEN** the deploy script is run before the Radicle repository has been published, or with a genesis head that isn't its canonical `main`
- **THEN** it exits with an error, and no transaction is sent

### Requirement: The binding is stated as a limit of this deployment
The deployment record, the README and the paper SHALL state that the repository and chain checks bind this deployment only, and that the open code can be deployed elsewhere without them.

#### Scenario: Reading the deployment record
- **WHEN** anyone reads the published deployment record
- **THEN** it names the repository id and its RID, the chain id, and says in plain words that a fork can remove both checks

### Requirement: The waiting windows are set at construction
The seal window, the reveal window and the challenge window for each panel size and proof level SHALL be constructor parameters, immutable afterwards, readable from the contracts and listed in the deployment record. The unbonding delay SHALL be derived from them.

#### Scenario: A test deployment with short windows
- **WHEN** a devnet deployment is constructed with windows in minutes
- **THEN** its verdicts become final after those minutes, and its unbonding delay is the longest of them plus the published margin

#### Scenario: No change after deployment
- **WHEN** anyone tries to change a window after construction
- **THEN** there is no function that does it

### Requirement: Windows are checked for order at construction
The constructor SHALL revert unless every window is nonzero, a smaller panel's challenge window is at least a larger panel's at the same level, level B's is at least level A's for the same panel size, and k = 1's is at least the published minimum for the deployment.

#### Scenario: Windows out of order
- **WHEN** a deployment is constructed with k = 3's window longer than k = 1's at level A
- **THEN** the constructor reverts

### Requirement: Only TEE proof types in this deployment
A deployment constructed as TEE-only SHALL accept only TEE proof types (levels A and B), at genesis and by any later ADR. The zkTLS proof type (level C) and the simulated type SHALL be refused on Sepolia.

#### Scenario: A zkTLS registration
- **WHEN** a validator registers on the Sepolia deployment with a zkTLS proof
- **THEN** the registration reverts

#### Scenario: An ADR that adds zkTLS
- **WHEN** an ADR adding the zkTLS proof type passes its panel on the Sepolia deployment
- **THEN** applying it reverts, and the accepted proof types are unchanged

### Requirement: Only a tested release candidate is deployed
The Sepolia deploy script SHALL deploy only contracts whose bytecode hashes match a committed release-candidate record, produced by the v3 integration suite passing on that exact commit (design L18). It SHALL refuse when the record is missing, failed, or names other bytecode.

#### Scenario: A contract changed after the run
- **WHEN** the deploy script builds a contract whose bytecode hash differs from the passing release-candidate record
- **THEN** it refuses before signing anything, and names the contract that differs

#### Scenario: No passing record
- **WHEN** the deploy script finds no release-candidate record for the commit, or one whose run failed
- **THEN** it refuses before signing anything
