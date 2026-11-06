# Spec Delta

## Purpose

Tests the mechanism before anything real exists: simulated honest and dishonest actors run against it under named parameters, and the results show whether honesty pays and attacks don't.

## ADDED Requirements

### Requirement: Reproducible runs
A simulation run SHALL be fully determined by its parameters, its scenario and a random seed. The same inputs SHALL give the same ledger and the same report.

#### Scenario: Same seed, same result
- **WHEN** a scenario is run twice with the same parameters and seed
- **THEN** both runs produce identical ledgers and reports

### Requirement: Actor behaviours
The simulation SHALL provide these actors, each with configurable rates:
- **Honest contributor:** submits contributions with a defect rate drawn from the baseline.
- **Spammer:** submits low-effort contributions.
- **Griefer:** files challenges without valid proof.
- **Colluding validators:** a group that votes together whatever the evidence.
- **Self-interested owner:** tries every action the mechanism allows to raise the owner's own payout.

#### Scenario: Each actor runs
- **WHEN** a scenario includes one of each actor type
- **THEN** the report shows each actor's submissions, challenges, verdicts and final balance

### Requirement: Replay of real history
The simulation SHALL replay a contribution stream built from aggregated statistics of GridCraft's public PR history: size distribution, merge rate, review rate and weekly volume. No per-person data SHALL be stored.

#### Scenario: Replay matches the baseline
- **WHEN** the replay scenario runs with the mechanism turned off
- **THEN** its contribution sizes and weekly volume match the recorded baseline within the stated tolerance

#### Scenario: No personal data
- **WHEN** the history data is inspected
- **THEN** it holds only distributions and counts, with no usernames or per-author rows

### Requirement: Report metrics
Each run SHALL report:
- each actor type's mean return per unit of effort or stake;
- contributions accepted, slashed and withdrawn;
- regressions that escaped challenge;
- time to settle;
- validator workload;
- each release's split, including the author's escrow and the owner's payout.

#### Scenario: Report produced
- **WHEN** a run finishes
- **THEN** a report with every listed metric is written, along with the parameters and seed used

### Requirement: Acceptance criteria for the mechanism
The mechanism SHALL be considered sound for a parameter set only if, across the published scenarios and seeds:
- honest contributors and honest validators earn a positive mean return;
- spammers, griefers and colluding validators earn a negative one, for collusion groups holding less than the published share of total validator stake (the collusion threshold);
- the owner's payout under self-interested play is no higher than under honest play.

#### Scenario: Attacks lose money
- **WHEN** the spam, griefing and collusion scenarios run with the proposed parameters
- **THEN** the attacking actors' mean return is negative in every scenario where the colluders hold less than the collusion threshold

#### Scenario: Collusion threshold measured
- **WHEN** the collusion scenario is run with the colluders' share of validator stake raised step by step
- **THEN** the report gives the smallest share at which collusion's mean return turns positive, and the published threshold is below it

#### Scenario: Owner can't gain by defecting
- **WHEN** the owner scenario runs with the owner playing honestly and with the owner self-interested
- **THEN** the self-interested owner's payout is not higher than the honest owner's

#### Scenario: Unsound parameters reported
- **WHEN** a parameter set fails any criterion
- **THEN** the report names the failed criterion, the scenario and the seed
