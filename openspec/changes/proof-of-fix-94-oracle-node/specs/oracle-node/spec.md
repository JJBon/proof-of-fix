# Spec Delta

## ADDED Requirements

### Requirement: A node signs only what it checked
An oracle node SHALL sign a submission's result only after it has verified that the solver's claim (the fix, its salt and
the solver) matches the submission's sealed commitment on-chain, and run the fix's tests in a sandbox with no network,
from a test image pinned by digest. A node SHALL sign the result's EIP-712 digest exactly as the contract verifies it.

#### Scenario: A claim that doesn't match
- **WHEN** the fix a solver reveals to the node doesn't hash, with its salt and solver, to the sealed commitment
- **THEN** the node signs nothing for that submission and logs why

#### Scenario: The contract accepts a quorum of node signatures
- **WHEN** a quorum of registered nodes sign the same result and the aggregator relays it
- **THEN** the contract records the outcome

### Requirement: Every verdict has a receipt
Each signed verdict SHALL come with a receipt recording the checker image, the model and backend, the hashes of the
judge's prompt and answer, the fix's tree, the test image, command, exit code and the hashes of the test results and
logs, the outcome, the chain and contract, the node's address and the attestation kind. The receipt SHALL be stored by the
hash of its canonical form, and that hash SHALL be what the node attests to.

#### Scenario: A tampered receipt
- **WHEN** a receipt's content no longer hashes to the hash the node revealed
- **THEN** the aggregator refuses that verdict

### Requirement: Keys stay where they were made
In a confidential VM the node's signing key SHALL be derived inside it through the dstack guest agent and never exported;
its quote SHALL bind the receipt hash. A local key provider MAY be used only against a local chain, SHALL be labelled
insecure in every receipt, and the node SHALL refuse to start with it against any other chain.

#### Scenario: Local keys on another chain
- **WHEN** a node configured with local keys connects to a chain whose ID is not a local one
- **THEN** it refuses to start

### Requirement: Verdicts are sealed before they are revealed
A node SHALL first publish a seal of its verdict and reveal the verdict only after the seal phase. The aggregator SHALL
refuse a reveal that arrives before the seal phase closes, or that doesn't match the node's seal.

#### Scenario: A changed verdict
- **WHEN** a node reveals an outcome different from the one it sealed
- **THEN** the aggregator refuses the reveal

### Requirement: Canaries score the nodes
Fixes with a known correct outcome SHALL be sent to nodes like real submissions, and each node's record on them SHALL be
kept as its accuracy score.

#### Scenario: A node fails a canary
- **WHEN** a node passes a canary whose known outcome is fail
- **THEN** its record shows one wrong answer, and nothing is relayed for the canary

### Requirement: The aggregator relays only a quorum of the contract's set
The aggregator SHALL read the oracle set and quorum from the contract, ignore verdicts signed by keys outside the set,
and relay an outcome only when at least the quorum of distinct keys in the set agree, with signatures ordered by signer
address. Dissenting verdicts SHALL be logged with their receipts.

#### Scenario: Minority dissent
- **WHEN** 2 of 3 nodes pass a fix and 1 fails it, with a quorum of 2
- **THEN** the pass is relayed and the dissent is logged

#### Scenario: Too few nodes
- **WHEN** fewer nodes than the quorum agree on any outcome
- **THEN** nothing is relayed

#### Scenario: A key outside the set
- **WHEN** a verdict is signed by a key the contract doesn't list
- **THEN** the aggregator ignores it, and a relay forced with it is refused by the contract
