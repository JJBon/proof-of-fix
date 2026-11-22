# Spec Delta

## Purpose
Defines the constitution of a self-governed repository: the articles, invariants, quality gates and protected paths every change is judged against; how it changes only through ADRs judged by the constitution tier; which articles are entrenched; and how the first constitution is set at genesis.

## ADDED Requirements

### Requirement: A constitution governs the code
A self-governed repository SHALL have a constitution, `CONSTITUTION.md` at its canonical head, holding its articles, invariants, quality gates and protected paths. Its hash SHALL be recorded on-chain with the head, and every check SHALL judge a fix against the version in force when its bounty was registered.

#### Scenario: Judged by the version registered under
- **WHEN** an ADR takes effect while a bounty registered earlier is still open
- **THEN** that bounty's fixes are judged against the earlier version, and bounties registered afterwards against the new one

#### Scenario: A fix that breaks an invariant
- **WHEN** a fix makes its bounty's tests pass but breaks an invariant the constitution lists
- **THEN** it fails, whatever its tests say

### Requirement: Amendment only by ADR
The constitution SHALL change only through an accepted ADR, a record of the problem, the options, the decision, its evidence and the protected paths it touches. An ADR SHALL pass the constitution tier, 5 of 7 judges, and then a 14-day public challenge window before it takes effect.

#### Scenario: An ADR passes
- **WHEN** 5 of the 7 judges pass an ADR and nobody upholds a challenge within 14 days
- **THEN** it takes effect, and the new constitution's hash is recorded with the head

#### Scenario: Too few judges
- **WHEN** 4 of the 7 judges pass an ADR
- **THEN** it fails, and the constitution is unchanged

#### Scenario: A fix edits the constitution directly
- **WHEN** a fix changes `CONSTITUTION.md` or another protected path without an accepted ADR covering it
- **THEN** it is escalated to the constitution tier and fails

#### Scenario: Challenged in the window
- **WHEN** someone challenges a passed ADR with a stake and evidence within its 14 days
- **THEN** the 7 judges judge it again with the evidence; it takes effect only if 5 of 7 pass it again, and the losing side's stake goes to the winning side

### Requirement: Entrenched articles
Articles marked entrenched (no human control; the judges' counts and thresholds; the amendment procedure itself) SHALL NOT change by ADR. They SHALL change only in a new version that anyone may deploy and users choose to follow, by migration.

#### Scenario: An ADR against an entrenched article
- **WHEN** an ADR proposes to lower the constitution tier to 4 of 7
- **THEN** it is refused without judging, and its author's fees for the tier are not charged

### Requirement: Escalation to the constitution tier
A fix SHALL go to the constitution tier when it touches a protected path, when any issue-tier judge flags it, or when anyone challenges its verdict with a stake within the clawback period. Otherwise the issue tier's verdict SHALL stand.

#### Scenario: A protected path
- **WHEN** a fix changes a file under a protected path
- **THEN** the constitution tier judges it, and the fix needs 5 of 7 and an ADR that covers the change

#### Scenario: One judge flags it
- **WHEN** 3 issue judges pass a fix and one of them flags it as constitutional
- **THEN** the constitution tier judges it before the head moves

#### Scenario: A challenge after the merge
- **WHEN** a merged fix is challenged with a stake within its clawback period, and 5 of 7 judges uphold the challenge
- **THEN** the fix is reverted by a new head, its unpaid instalments are clawed back, and the challenger is paid as the challenges spec says

#### Scenario: A failed challenge
- **WHEN** fewer than 5 of 7 judges uphold a challenge
- **THEN** the head is unchanged, and the challenger's stake goes to the solver

### Requirement: ADR fees
An ADR's author SHALL pay the constitution tier's verdict fees when submitting it. If the ADR takes effect, the fees SHALL be refunded from the sponsors' pool; otherwise they SHALL stay with the judges who gave verdicts.

#### Scenario: An accepted ADR
- **WHEN** an ADR takes effect
- **THEN** its author is refunded the 7 verdict fees from the sponsors' pool, as far as the pool holds them

#### Scenario: A rejected ADR
- **WHEN** an ADR fails
- **THEN** each judge who gave a verdict keeps its fee, and the author gets nothing back

### Requirement: The genesis constitution
The first constitution SHALL be written by the owner, published before deployment, recorded at genesis, and disclosed as the owner's one-time act (openspec rule 3). After genesis the owner SHALL have no power over it beyond any author's right to propose an ADR.

#### Scenario: After genesis
- **WHEN** the owner wants to change an article after genesis
- **THEN** the owner submits an ADR and pays its fees like anyone, and the owner's judge doesn't sit on it
