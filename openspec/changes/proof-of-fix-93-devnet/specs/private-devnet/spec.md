# Spec Delta

## Purpose
The private Ethereum devnet where proof-of-fix's contracts are deployed and exercised under mainnet's rules, before any public chain: what it enforces, how deployments are recorded, and where its keys come from.

## ADDED Requirements

### Requirement: Mainnet's rules, on this machine only
The devnet SHALL run mainnet's current hardfork and enforce EIP-170's 24,576-byte limit on contract code. It SHALL have a chain ID no public chain uses, mine blocks at a fixed interval greater than zero, and answer RPC only on the local loopback interface. Every contract SHALL fit the size limit, and no script SHALL lift it.

#### Scenario: A contract over the limit
- **WHEN** a contract whose runtime code is 24,577 bytes is deployed to the devnet
- **THEN** the devnet refuses it, while one of exactly 24,576 bytes deploys

#### Scenario: Not reachable from elsewhere
- **WHEN** the devnet is running
- **THEN** its RPC is published on 127.0.0.1 only

### Requirement: Recorded deployments
A deployment to the devnet SHALL deploy the Token, Race (with its library) and the Quoter, with the oracle keys and quorum fixed at deployment. It SHALL write a record with:
- the chain ID and block;
- the deployed git commit;
- every address and the runtime code hashes;
- the oracle set and quorum;
- where the keys came from.

#### Scenario: Checking a deployment
- **WHEN** someone reads the deployment record
- **THEN** each contract's code hash on the devnet matches the record's

### Requirement: Devnet keys only from the secret store
Each role's key SHALL be generated for the devnet alone and kept only in the secret store (OpenBao). It SHALL never be printed, logged, committed, passed on a command line, or used on a public chain. Anvil's public test mnemonic SHALL be used only when explicitly asked for.

#### Scenario: Not signed in
- **WHEN** a devnet script needs a key and nobody is signed in to the secret store, and the insecure local keys weren't asked for
- **THEN** it stops with an instruction to sign in, and uses no other key

### Requirement: The oracle path checked on the devnet
The deployed Race SHALL be checked against the devnet for the signed quorum's rules:
- a quorum of distinct oracle keys is accepted, and dissenting keys outside the quorum don't block it;
- fewer signatures than the quorum, a key outside the set, a forged signature or the same key twice are refused;
- a replayed signature, or one made for another chain or another contract, is refused.

#### Scenario: A colluding minority
- **WHEN** fewer oracle keys than the quorum sign an action
- **THEN** the deployed Race refuses it

#### Scenario: Signed for another chain
- **WHEN** the quorum's signatures were made over the same action for another chain ID
- **THEN** the deployed Race refuses them
