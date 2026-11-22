# ledger Specification

## Purpose
Defines the simulated ledger that records every stake, escrow, slash and payout, so each settlement can be audited and no value is created or lost by mistake.

## Requirements

### Requirement: Simulated credits only
The ledger SHALL hold only simulated credits. It SHALL NOT connect to a blockchain, a payment service or a wallet, and it SHALL NOT store real addresses, keys or personal data.

#### Scenario: No external connection
- **WHEN** the ledger records any entry
- **THEN** nothing is sent outside the process

#### Scenario: Accounts are pseudonymous
- **WHEN** an account is created for an actor
- **THEN** it is identified by a generated identifier, never by a real person's name, handle or address

### Requirement: Append-only entries
Every change of balance SHALL be an entry appended to the ledger, with its time, its reason (stake, escrow, reward, slash, fee, payout, claim) and the contribution, challenge or release it belongs to. Entries SHALL never be edited or deleted; a correction SHALL be a new entry.

#### Scenario: Correction
- **WHEN** an amount was recorded wrongly
- **THEN** a reversing entry and a correct entry are appended, and the original stays visible

### Requirement: Conservation of value
Every entry SHALL move credits between accounts, so the sum of all balances SHALL stay equal to the credits issued. Credits SHALL be issued only as release funding or initial actor endowments, each recorded as such.

#### Scenario: Balances add up after any sequence
- **WHEN** any sequence of submissions, challenges, settlements and releases has been recorded
- **THEN** the sum of all balances equals the total issued

#### Scenario: No negative balances
- **WHEN** an entry would take an account below zero
- **THEN** it is refused, and nothing is recorded

### Requirement: Auditable settlements
For any contribution, challenge or release, the ledger SHALL list every entry about it, so an auditor can recompute its outcome from the entries alone.

#### Scenario: Recompute a settlement
- **WHEN** an auditor takes the entries for a settled contribution
- **THEN** they can recompute the stake, the reward, any slash and its distribution, and the numbers match the balances
