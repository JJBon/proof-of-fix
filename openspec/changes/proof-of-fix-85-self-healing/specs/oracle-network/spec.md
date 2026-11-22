# Spec Delta

## Purpose
Defines how the judges' verdicts reach the chain in v2: the verdict's signed fields, sealed verdicts revealed on-chain, the seats and their keys, receipts, check fees charged on real usage, bonds and provable faults, and the deployment record. The node's own behaviour is in `oracle-node` (#94).

## ADDED Requirements

### Requirement: A verdict binds its base commit and its receipt
A verdict SHALL be an EIP-712 struct signed by a seat's registered key, naming the repository, the base commit it was checked on, the fix commit, the bounty, the submission, the tier, the outcome, the receipt's hash, the draw's seed and a nonce, under the version's domain. A verdict SHALL move the head only if its base is the recorded head.

#### Scenario: A verdict checked on an old head
- **WHEN** a quorum of verdicts passes a fix whose signed base is no longer the recorded head
- **THEN** the head doesn't move, and the fix must be rebased and checked again

#### Scenario: An issue verdict offered as a constitution verdict
- **WHEN** a relayer submits issue-tier signatures toward a constitution-tier decision
- **THEN** the contract refuses them, because the signed tier doesn't match

### Requirement: Verdicts are sealed on-chain before they are revealed
Each drawn judge SHALL submit a signed seal of its verdict within the seal window, and reveal the verdict matching the seal within the reveal window. A judge that doesn't reveal in time SHALL lose a published share of its bond, its verdict SHALL be discarded, and the next seat in the draw SHALL replace it.

#### Scenario: Copying is impossible
- **WHEN** a judge seals after another judge's seal is on-chain
- **THEN** it learns nothing of the other's verdict, because only seals exist until the reveal window

#### Scenario: A judge goes silent
- **WHEN** a drawn judge sealed but doesn't reveal before the reveal window ends
- **THEN** its verdict is discarded, it loses the published share of its bond, and the next seat in the draw is given a fresh seal window

### Requirement: Seats fixed per version, keys rotated only under the entrenched rule
A version SHALL fix its 7 seats: each seat's operator, model family and inference or TEE provider. A seat's key SHALL change only to a key whose attestation, of a type on the constitution's accepted list, shows the official checker image on the constitution's allowed list, co-signed by the seat's current key and 5 of the other 6 seats, taking effect after a published delay. No function SHALL add, remove or replace a seat's operator, family or provider.

#### Scenario: An enclave redeployed
- **WHEN** a seat presents a new key with a valid attestation for an allowed checker image, co-signed by its current key and 5 other seats
- **THEN** the new key replaces the old one after the published delay, and the attestation's hash is recorded

#### Scenario: A key from an unlisted image
- **WHEN** a rotation's attestation shows a checker image that isn't on the allowed list
- **THEN** the rotation is refused, whoever co-signs it

#### Scenario: A lost key
- **WHEN** a seat can no longer sign
- **THEN** it is suspended, the issue tier draws from the remaining seats, and its operator can't be replaced except by a new version

#### Scenario: A vacant seat joins
- **WHEN** a version is deployed with a seat whose operator, family and provider are fixed but whose key is not yet set, and that seat's new key, with a valid attestation for an allowed checker image, is co-signed by 5 other seats
- **THEN** the key takes the seat after the published delay, and from then on the seat only rotates under the same rule

#### Scenario: A suspension of a seat that can still sign
- **WHEN** the other seats publish a seat's suspension and the seat's own key then signs to lift it
- **THEN** the suspension is lifted, so a seat that can sign is never kept out

### Requirement: At most two seats per provider
No more than 2 of a version's 7 seats SHALL rely on the same inference or TEE provider, as recorded at genesis.

#### Scenario: A third seat on one provider
- **WHEN** a version is deployed with three seats recording the same provider
- **THEN** the deployment is refused

### Requirement: Receipts are content-addressed and bound
Every revealed verdict SHALL carry the hash of a receipt naming the exact model ID and version, the provider, the hashes of the prompt and the response, the usage measured inside the attested node, the checker image digest, the test results' hash, the base and fix commits, a timestamp, the attestation evidence's hash and the signing key. The receipt SHALL be retrievable by its hash.

#### Scenario: A receipt that doesn't match
- **WHEN** a challenger shows that the content stored under a verdict's receipt hash isn't that receipt, or that its attestation doesn't verify
- **THEN** the challenge is decided by the constitution tier without the challenged seat, and an upheld challenge slashes it

### Requirement: Receipts follow the AIR draft and name an allowed model
A receipt SHALL be encoded as COSE_Sign1 following `draft-tsyrulnikov-rats-attested-inference-receipt-02`; a later draft version SHALL be adopted only by ADR. Its measured usage SHALL be the provider's own token counts and the sandbox's CPU-seconds and GB-seconds. A receipt naming a model version outside the constitution's allowed list for its seat's family SHALL be a bad receipt.

#### Scenario: A model outside the allowed list
- **WHEN** a verdict's receipt names a model version the constitution doesn't allow for that seat's family
- **THEN** a challenge shows it, the verdict is a bad receipt, and the seat is slashed as for any bad receipt

### Requirement: Check fees: costs passed through per unit, plus one agreed service fee
The price table SHALL hold unit prices (tokens per family, sandbox vCPU- and GB-seconds, storage). A counted check SHALL be charged its measured usage at those prices, within the constitution's and the CI profile's caps, plus one `SERVICE_FEE` equal for every seat; shared parts at the median of the counted judges' usage. The deposit SHALL be the worst case plus fees and a gas allowance; gas is reimbursed at cost, the rest refunded.

#### Scenario: One judge pads its usage
- **WHEN** two judges report 4,000 tokens and the third reports 40,000
- **THEN** every counted judge is paid for 4,000 tokens at its own family's prices, plus the service fee

#### Scenario: A heavier check costs more at the same prices
- **WHEN** two fixes in the same repository use 3,000 and 40,000 prompt tokens
- **THEN** both are charged at the same unit prices, and the larger one costs more

#### Scenario: The deposit's ceiling
- **WHEN** a solver attempts a bounty
- **THEN** the deposit the contract asks for is the worst case of the drawn judges' caps and the repository's CI profile, plus the service fees and the relayer's gas allowance, and whatever the checks don't use is refunded

### Requirement: The price table and the service fee change only within bounds
The price table and `SERVICE_FEE` SHALL change only by 5 of 7 seats, each value by at most 25 % per update, after 7 days' notice, with one pending update at a time. `SERVICE_FEE` SHALL never exceed the cap in the constitution, which only an ADR changes. No seat SHALL set a fee of its own, and fees SHALL be pulled.

#### Scenario: A price jump
- **WHEN** 5 seats sign a price table that raises one entry by 40 %
- **THEN** the update is refused

#### Scenario: A service fee above the cap
- **WHEN** 5 seats sign a service fee within 25 % of the current one but above the constitution's cap
- **THEN** the update is refused

#### Scenario: A price update's notice
- **WHEN** 5 seats sign a valid price update
- **THEN** attempts in the next 7 days are still charged at the old prices

#### Scenario: An entry above twice its genesis value
- **WHEN** 5 seats sign a table entry within 25 % of its current value but above 2× its value at deployment
- **THEN** the update is refused

### Requirement: Price updates cite public prices and can be challenged
A price-table or service-fee update SHALL carry the hash of the providers' public price lists it follows. During its notice anyone MAY challenge it with a stake. An upheld challenge SHALL cancel the update and pay the challenger from the proposing seats' bonds; a rejected challenge SHALL forfeit its stake to the sponsors' pool. No entry SHALL exceed twice its value at deployment, a cap only an ADR changes.

#### Scenario: An update that doesn't match the public prices
- **WHEN** a challenger shows, during the notice, that an entry is above the provider's cited public price
- **THEN** the update is cancelled and the challenger is paid from the proposers' bonds

#### Scenario: A challenge that fails
- **WHEN** a challenge's claim doesn't hold against the cited price lists
- **THEN** the update takes effect after its notice and the challenger's stake goes to the sponsors' pool

### Requirement: Bonds slashed only for provable faults
Each seat SHALL hold a bond of at least the published minimum. A seat SHALL be slashed only for a provable fault: two signatures for conflicting outcomes on the same verdict, a reveal that doesn't match its seal, a missed reveal, a failed availability challenge, or a receipt challenge upheld. A wrong answer in good faith SHALL NOT be slashed. Part of each slash SHALL go to whoever proved the fault, and the rest to the sponsors' pool.

#### Scenario: Equivocation
- **WHEN** anyone submits two signatures by one seat for conflicting outcomes on the same verdict
- **THEN** the contract checks them itself and slashes the seat's whole bond, paying the published share to the submitter

#### Scenario: Wrong but honest
- **WHEN** a judge passes a fix that a later challenge shows was bad, with a valid receipt
- **THEN** its bond isn't touched; the error counts against its public score

#### Scenario: A bond below the minimum
- **WHEN** slashing leaves a seat's bond below the published minimum
- **THEN** the seat is suspended until its bond is topped up

### Requirement: Bonds follow the largest bounty
Each version SHALL publish its largest accepted bounty, and a seat's minimum bond SHALL be at least twice that amount. A bounty above the largest accepted SHALL be refused. A bad receipt SHALL cost 20 % of the seat's bond.

#### Scenario: A bounty above the maximum
- **WHEN** a funder pledges a bounty above the version's largest accepted bounty
- **THEN** the pledge is refused

#### Scenario: Joining with too small a bond
- **WHEN** a seat's bond is less than twice the version's largest accepted bounty
- **THEN** the seat can't be counted until its bond is topped up

#### Scenario: A bad receipt
- **WHEN** a receipt challenge against a seat is upheld
- **THEN** 20 % of its bond is slashed, half to the challenger and half to the sponsors' pool

### Requirement: Canaries on a public scoreboard
Known-answer canary cases SHALL be run against the judges off-chain, and each seat's canary score, accuracy and reveal rate SHALL be published on a public scoreboard. In this version, a canary answered wrongly SHALL NOT be slashed on-chain.

#### Scenario: A lazy judge
- **WHEN** a seat answers canaries no better than chance
- **THEN** the scoreboard shows its canary score, and its bond is untouched unless it also commits a provable fault

### Requirement: The deployment record names every code hash
A version's deployment record SHALL list every contract's and every linked library's address and code hash, and the compiler's version and settings.

#### Scenario: Checking a linked library
- **WHEN** someone checks a deployment's signature-checking library
- **THEN** its address and code hash are in the deployment record, and match the chain

### Requirement: Accepted attestation types and one checker image
The constitution SHALL list the accepted TEE attestation types (AWS Nitro; Intel TDX, through Phala dstack or self-hosted; AMD SEV-SNP) and one official checker image, built reproducibly so its digest is the same for every operator. A seat's key SHALL be registered or rotated only with an attestation of an accepted type showing that digest. Each operator SHALL otherwise choose its own infrastructure, within the provider cap.

#### Scenario: An attestation of an unlisted type
- **WHEN** a seat presents a key with an attestation of a TEE type the constitution doesn't list
- **THEN** the key isn't registered, whoever co-signs it

#### Scenario: Two operators, two clouds
- **WHEN** one operator runs AWS Nitro and another runs Intel TDX through self-hosted dstack, both attesting the official checker digest
- **THEN** both keys are accepted

### Requirement: Counted judges call providers directly
A counted verdict's model call SHALL be made from inside the attested node, over a TLS session to the model provider that terminates inside the TEE. No proxy or gateway SHALL sit between the node and the provider for a counted verdict.

#### Scenario: A verdict routed through a gateway
- **WHEN** a receipt shows the model call went to a proxy or gateway rather than the provider's own endpoint
- **THEN** it is a bad receipt

### Requirement: Repositories declare a CI profile
Each repository SHALL declare in its config the test image digest, the CPU, the memory and the timeout of its checks. A quote SHALL show the maximum check cost under that profile and the table in force.

#### Scenario: A heavy test suite
- **WHEN** a repository's CI profile allows 8 minutes on 2 vCPUs
- **THEN** its quotes show a higher maximum check cost than a repository allowing 1 minute on 1 vCPU, and a run that reaches the limit stops there

### Requirement: An optional single attested CI run
When a version enables `CI_SINGLE_RUN`, the issue tier's tests SHALL run once, in an attested node; the other drawn judges SHALL verify that run's attestation and result hash and still give their own AI verdict, and the run's usage SHALL be charged once. Anyone SHALL be able to challenge the run by re-running the tests under the same CI profile.

#### Scenario: A re-run that disagrees
- **WHEN** a challenger re-runs the tests under the same CI profile and gets a different result hash
- **THEN** the single run's receipt is a bad receipt, decided by the constitution tier without the challenged seat

