# Spec Delta

## Purpose
How anyone becomes, stays and stops being a validator in v3: registration with a bond and an attestation, no co-signing, qualification as a shadow judge, automatic activation, suspension, unbonding, slashing, and the caps that bound one party's presence. It replaces v2's fixed seats and co-signed joins for v3 only; v2 is unchanged.

## ADDED Requirements

### Requirement: Anyone may register a validator
Any account SHALL be able to register a validator key without anyone's approval or co-signature, by posting at least the version's bond floor and naming an accepted proof type. A TEE validator SHALL present an attestation of an accepted TEE type showing a checker image digest on the allowed list. The new key SHALL sign its own registration.

#### Scenario: A newcomer registers
- **WHEN** an account with no prior relation to the project registers a key with the bond floor and a valid attestation of the official image
- **THEN** the key is registered as a candidate, with no co-signature from any other validator, the owner included

#### Scenario: An image not on the list
- **WHEN** a registration's attestation shows an image digest that isn't on the allowed list
- **THEN** the registration is refused

#### Scenario: Too small a bond
- **WHEN** a registration posts less than the bond floor
- **THEN** the registration is refused

#### Scenario: Someone else's key
- **WHEN** a registration names a key that didn't sign the registration
- **THEN** the registration is refused

### Requirement: A registration records what the caps need
A registration SHALL record the proof type, the attestation's hash and the TEE type where there is one, the infrastructure host the attestation identifies or the operator declares, the declared model family and the declared operator account, and anyone SHALL be able to read them.

#### Scenario: Reading a validator's host
- **WHEN** anyone looks up a registered validator
- **THEN** they see its proof type, its TEE type if any, its infrastructure host, its model family, its operator account and its attestation's hash if any

### Requirement: A validator's model family is fixed by its registration
A validator's declared model family SHALL NOT change. A validator that wants to judge with another family SHALL register again, with a new key that qualifies under the new family, and MAY leave with its old registration.

#### Scenario: Switching to the top model
- **WHEN** a validator of one family wants to judge with the family that pays more
- **THEN** it registers a new key with that family and qualifies as a shadow judge before it is drawn for counted panels

### Requirement: Accepted proof types, zkTLS among them
The constitution SHALL list the accepted proof types: each accepted TEE type, and zkTLS for validators without a TEE. A zkTLS validator's model calls SHALL be proven by a zkTLS proof from one of the constitution's listed notaries, of which there SHALL be several and none required. Its test results SHALL be re-runnable by anyone from the fixed commit and the official sandbox image.

#### Scenario: zkTLS before it is switched on
- **WHEN** someone registers with the zkTLS proof type before an ADR has added zkTLS to the constitution's list
- **THEN** the registration is refused, since at launch only TEE types are accepted

#### Scenario: A validator on ordinary hardware
- **WHEN** someone with no TEE registers with the zkTLS proof type, the bond floor and a model family
- **THEN** it is registered as a candidate, and qualifies by the same shadow-judging rules as any other

#### Scenario: A notary that isn't listed
- **WHEN** a zkTLS validator's proof comes from a notary not on the constitution's list
- **THEN** the proof is refused, and the verdict doesn't count

#### Scenario: A notary removed while verdicts are in flight
- **WHEN** an ADR removes a notary while verdicts proven by it are being judged
- **THEN** verdicts revealed before the removal takes effect still count, no validator is slashed for them, and later proofs from that notary don't count

### Requirement: Level C is off at launch
At deployment the constitution's list SHALL accept only TEE types. The contract code SHALL already include zkTLS verification, and an adding ADR SHALL be able to switch it on without a migration. The constitution SHALL only switch verifier paths on or off, never add verifier code.

#### Scenario: Switching zkTLS on
- **WHEN** an adding ADR lists zkTLS and its notaries, and its challenge window passes
- **THEN** validators can register at level C from then on, with no new contract

#### Scenario: A verifier that isn't in the code
- **WHEN** an ADR tries to add a proof type whose verifier isn't in the deployed code
- **THEN** it can't take effect; a new verifier needs a migration (D15)

### Requirement: Each validator has a proof level
Each validator SHALL have a proof level, recorded at registration and readable by anyone:
- level A, a TEE whose cloud platform's own attestation shows the validator has no physical access;
- level B, a TEE whose location isn't proven, such as a home or rented server;
- level C, zkTLS on any machine.

#### Scenario: A confidential VM in a cloud
- **WHEN** a validator registers from a cloud confidential VM with the cloud platform's attestation alongside the TEE's
- **THEN** it is recorded at level A

#### Scenario: A TEE server at home
- **WHEN** a validator registers from its own TDX or SEV-SNP server with only the chip's attestation
- **THEN** it is recorded at level B

#### Scenario: An ordinary PC
- **WHEN** a validator registers with the zkTLS proof type
- **THEN** it is recorded at level C

### Requirement: TEE attestations meet the minimum firmware level
A TEE attestation SHALL show a firmware (TCB) level at or above the constitution's minimum for its TEE type, and a platform its maker has revoked SHALL be refused. When the minimum is raised by ADR, validators below it SHALL stop being drawn and keep their bonds. They MAY return after updating and attesting again, without qualifying again.

#### Scenario: A flaw is patched
- **WHEN** a chip maker announces a flaw, ships a firmware fix, and an ADR raises the minimum level
- **THEN** validators still on the old firmware stop being drawn after the removal window, until they update and attest again, and then return without a new qualification

### Requirement: A broken type is removed faster than a new one is added
An ADR that removes an accepted TEE type, proof type, notary or image digest, or raises a minimum firmware level, SHALL take effect after a published short window. An ADR that adds one SHALL take effect only after the full challenge window. Validators of a removed type SHALL stop being drawn, keep their bonds, and MAY register again with an accepted type. No ADR SHALL remove the last accepted TEE type or image digest.

#### Scenario: An exploit is published for a TEE type
- **WHEN** researchers publish a practical attack on one accepted TEE type, and the constitution tier passes an ADR removing it
- **THEN** that type's validators stop being drawn after the short window, without losing their bonds

#### Scenario: Removing the last accepted type
- **WHEN** an ADR would remove the last accepted TEE type, or the last accepted image digest
- **THEN** it can't take effect, because the network would halt; a replacement must be added first (owner, 2026-11-03)

#### Scenario: A new TEE type proposed
- **WHEN** the constitution tier passes an ADR adding a new TEE type
- **THEN** it takes effect only after the full challenge window, and counts as its own type under the TEE-type cap

### Requirement: Qualification as a shadow judge
A candidate SHALL be drawn as a shadow judge on drawn submissions, and on submissions waiting for a panel. It SHALL seal its verdict before the counted verdicts are revealed, and reveal it like a counted judge. A shadow verdict SHALL NOT count, and SHALL NOT be paid a service fee; its metered usage SHALL be repaid from the sponsors' pool, capped per draw.

#### Scenario: A candidate copies the counted judges
- **WHEN** a candidate waits to see the counted verdicts before sealing its own
- **THEN** it can't, because its seal window closes before the counted judges reveal, and a missing seal counts as not revealed

#### Scenario: A submission waits for a panel
- **WHEN** a submission waits because too few validators are eligible for its bounty
- **THEN** the published number of candidates are drawn by its seed as its shadow judges, and judge it while it waits

### Requirement: A shadow verdict is scored only against an outcome no lone validator set
A shadow verdict SHALL be scored against the final outcome of a panel of k ≥ 3, or of a k = 1 verdict whose window started at its reveal. On a k = 1 verdict held at its reveal, or a waiting or withdrawn submission, it SHALL be scored once, against the majority of the verdicts sealed on that submission, counted and shadow, if at least 3 were revealed, and otherwise SHALL NOT count; it SHALL NOT be scored again when that verdict becomes final.

#### Scenario: A colluding genesis validator
- **WHEN** the only active validator passes its accomplice's bad fixes, and honest candidates shadowing those submissions vote fail
- **THEN** the held verdicts don't score them; they're scored against the majority of the sealed verdicts, which the lone validator doesn't set, and they qualify on their own record

#### Scenario: A held verdict becomes final
- **WHEN** a candidate was scored on a held k = 1 verdict against the sealed majority, and that verdict later becomes final after its hold
- **THEN** the candidate isn't scored on it again

#### Scenario: Challengers already eligible
- **WHEN** a k = 1 verdict's window starts at its reveal, because three validators are already eligible for its challenge panel
- **THEN** its shadows are scored against its final outcome

#### Scenario: A waiting submission
- **WHEN** three candidates shadow a submission that is still waiting for a panel, and two of them vote fail
- **THEN** each is scored against the fail majority, and the one that voted pass is scored as disagreeing

### Requirement: Activation by the qualification thresholds, with no vote
A candidate SHALL become active automatically once it has completed the published number of scored shadow verdicts with a reveal rate and an agreement at or above the published thresholds. A candidate that fails SHALL stay a candidate and MAY try again after the published cooling-off period.

#### Scenario: A candidate qualifies
- **WHEN** a candidate reveals every shadow verdict on time and agrees with the outcomes it is scored against in at least the published share
- **THEN** it becomes active without any vote, and can be drawn for counted panels

#### Scenario: A candidate that never answers
- **WHEN** a candidate's reveal rate stays below the threshold
- **THEN** it doesn't become active, and its bond is untouched unless it commits a provable fault

### Requirement: No account adds, removes or blocks a validator
No account, the owner's and any DAO's included, SHALL be able to add, activate, remove or suspend a validator except by the rules in this spec, or change the version's bonds, thresholds, caps or windows. The constitution's lists (accepted TEE types, checker image digests) SHALL change only by an ADR at the constitution tier.

#### Scenario: The owner tries to admit a friend
- **WHEN** any account, the owner's included, tries to activate a candidate that hasn't qualified
- **THEN** there is no function to do it, and the candidate stays a candidate

#### Scenario: A DAO funds the project
- **WHEN** a legal wrapper or DAO funds the sponsors' pool and registers a validator
- **THEN** its validator follows the same rules as any other, and it holds no other power over the contracts

### Requirement: A validator stops being drawn when it can't serve
An active validator SHALL NOT be drawn while its bond is below the bond floor, until topped up, or while its reveal rate over the published recent window is below the published threshold, until it re-qualifies. A drawn judge that doesn't seal, or seals and doesn't reveal, SHALL count as a miss.

#### Scenario: A validator goes offline
- **WHEN** an active validator misses enough reveals to fall below the reveal-rate threshold
- **THEN** it is no longer drawn, and must re-qualify to return

#### Scenario: A new validator misses early
- **WHEN** a validator with fewer than the window's draws misses more of them than the threshold allows over a full window
- **THEN** it stops being drawn, as if its earlier draws had all been revealed

### Requirement: Slashing only for provable faults
A validator SHALL be slashed only for a provable fault: the whole bond for equivocation, a reveal that doesn't match its seal, or a false verdict (an upheld receipt challenge); a published flat amount, the same for every bond, for a counted judge that doesn't seal in time, or seals and doesn't reveal in time; v2's share for a failed availability challenge. A wrong verdict given in good faith with a valid receipt SHALL NOT be slashed.

#### Scenario: A false verdict
- **WHEN** a receipt challenge against a validator's verdict is upheld, because a fresh panel's re-runs don't reproduce its receipt or the verdict contradicts its receipt
- **THEN** its whole bond is slashed, and it isn't drawn until its bond is back at the floor

#### Scenario: A sealed vote not revealed
- **WHEN** a drawn counted judge seals but doesn't reveal in time
- **THEN** it loses the published flat amount ($5 at launch), counts a miss, and is replaced

#### Scenario: An honest mistake
- **WHEN** a validator's verdict is overturned by a challenge, with a valid receipt and no provable fault
- **THEN** its bond isn't slashed; the overturned verdict counts against its family's public score

### Requirement: Silence costs a flat amount
A drawn counted judge that never seals SHALL lose the published flat silence amount ($5 at launch), the same for every bond. It SHALL be replaced by the next validator in the same sample and SHALL count a miss toward the reveal-rate floor. A shadow judge that never seals SHALL only count a miss.

#### Scenario: An honest outage
- **WHEN** an honest validator's node is down when it is drawn as a counted judge, and it never seals
- **THEN** it loses $5 from its bond, the next validator in the shuffle replaces it, and the miss counts toward its reveal rate

#### Scenario: Bonds of different sizes
- **WHEN** a validator bonded at $100 and one bonded at $1,250 each stay silent on a counted draw
- **THEN** each loses the same $5

#### Scenario: A silent shadow
- **WHEN** a candidate drawn as a shadow judge never seals
- **THEN** it loses nothing from its bond, and the miss counts toward its qualification's reveal rate

### Requirement: Leaving with an unbonding delay
A validator SHALL be able to leave at any time, and a leaving validator SHALL NOT be drawn. Its bond SHALL be withdrawable only after an unbonding delay longer than the longest challenge window of any panel size and level, and only once every verdict it gave is final and every challenge naming it is closed. It SHALL stay slashable until then.

#### Scenario: Leave, then a fault is proven
- **WHEN** a validator announces it's leaving and, during the unbonding delay, an equivocation it committed is proven
- **THEN** its bond is slashed as if it were still active, and only what remains is withdrawable after the delay

#### Scenario: Leave while a challenge waits
- **WHEN** a validator leaves while a challenge against one of its verdicts waits, frozen, for a fresh panel
- **THEN** its bond stays locked past the unbonding delay until that challenge is judged, and is slashed if it is upheld

### Requirement: One party's presence is capped
In any single panel, at most one validator SHALL share a declared operator account, and no more than the published share SHALL share an infrastructure host or a model family, or, from the panel size the TEE-type cap starts at, a TEE type. The caps SHALL be read from the attestation and the receipts, and the draw SHALL skip a validator that would break one.

#### Scenario: Ten nodes on one cloud
- **WHEN** one party registers ten qualified validators on the same infrastructure host and a panel of 5 is drawn
- **THEN** the panel holds no more of them than the host cap allows, and the rest of the panel comes from other hosts

#### Scenario: Too few distinct hosts
- **WHEN** the caps leave fewer eligible validators than the k the network size would allow
- **THEN** k is computed from the validators the caps leave eligible, not from all active validators

### Requirement: The TEE-type cap starts at k = 3 once five TEE types are accepted
The TEE-type cap SHALL apply to panels of 3 or more while at least the published number of TEE types (5) are on the constitution's list, and only to panels of 5 or more while fewer are. The start SHALL follow the list as ADRs change it, from the next draw.

#### Scenario: Two of one TEE type in a panel of 3
- **WHEN** a panel of 3 is drawn on a network with three accepted TEE types
- **THEN** two of its judges may share a TEE type, so the draw doesn't need one of each type; on a panel of 5 or 7 the TEE-type cap applies

#### Scenario: Five TEE types accepted
- **WHEN** a panel of 3 is drawn while five TEE types are accepted
- **THEN** no two of its judges share a TEE type

#### Scenario: A type is removed
- **WHEN** an ADR removes one of five accepted TEE types
- **THEN** from the next draw the TEE-type cap applies only to panels of 5 or more

### Requirement: Each attestation scheme is its own TEE type
Each TEE technology with its own attestation format and signing root SHALL be its own TEE type under the cap, even when one vendor makes several. One technology SHALL be one type whatever cloud or host runs it. An accelerator's attestation, such as a confidential GPU's, SHALL NOT be a type of its own: its validator counts under its CPU TEE's type.

#### Scenario: Two technologies from one vendor
- **WHEN** one validator attests with Intel SGX and another with Intel TDX
- **THEN** they are of two TEE types

#### Scenario: One vendor's two types on a panel of three
- **WHEN** a k = 3 panel draws one Intel SGX and one Intel TDX validator, once five types are accepted
- **THEN** the draw is allowed: the cap counts types, not vendors (owner, 2026-11-03)

#### Scenario: One technology in two clouds
- **WHEN** one validator runs a TDX confidential VM in one cloud and another runs one in a second cloud
- **THEN** they share a TEE type, and the host cap counts them apart

#### Scenario: A confidential GPU
- **WHEN** a validator attests an NVIDIA confidential-computing GPU beside an AMD SEV-SNP virtual machine
- **THEN** it counts as an SEV-SNP validator under the TEE-type cap

### Requirement: At most one genesis validator, so the network can start
A version's deployment MAY name at most one genesis validator, active from the start, so the first submissions can be judged and the first candidates can qualify. It SHALL be at proof level A or B, bonded and attested like any other, SHALL have no other privilege, and SHALL be disclosed in the deployment record.

#### Scenario: A launch with one validator
- **WHEN** a version is deployed with one genesis validator and no other
- **THEN** small bounties are judged with k = 1 under k = 1's rules, and the first candidates qualify as shadow judges on its panels and on waiting submissions

#### Scenario: Two genesis validators
- **WHEN** a deployment names two genesis validators
- **THEN** the deployment is refused

#### Scenario: A genesis on an ordinary PC
- **WHEN** a deployment names a level C genesis validator
- **THEN** the deployment is refused

### Requirement: The owner runs at most one validator
The owner SHALL run at most one validator, disclosed as the owner's in the registration, or as the genesis validator. It SHALL follow the same rules as any other validator and SHALL recuse from any bounty or ADR in which the owner is a party.

#### Scenario: The owner's validator and the owner's fix
- **WHEN** the owner's account solves a bounty and the owner's validator would be drawn for it
- **THEN** the owner's validator is skipped as a party, and the next eligible validator in the shuffle takes its place
