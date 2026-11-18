# Spec Delta

## Purpose

Defines the repository's head on-chain under v3, when it moves, and how anyone checks a copy of the code against it, so that the chain stays the source of truth for which commit was judged and paid.

## ADDED Requirements

### Requirement: The head moves only when the winning verdict is final
In v3, the repository's head SHALL move to a winning fix only once the verdict that passed it is final: its window has passed with no challenge or dispute upheld, and any k = 1 hold has ended. Claiming the bounty SHALL NOT move the head.

#### Scenario: A pass that stands
- **WHEN** a panel passes a fix, its solver claims the bounty, and the verdict's window ends with no challenge upheld
- **THEN** anyone may then move the head to the fix, and the head records the bounty, the submission and the verdict

#### Scenario: A pass reversed in its window
- **WHEN** a passed and claimed fix is reversed by a challenge or a failing-test dispute before its verdict is final
- **THEN** the head never moves to it, the award is clawed back and the bounty reopens, as #132 specifies

### Requirement: A stale base is refused at the move
When the head is moved, the fix's base SHALL equal the current head. Otherwise the move SHALL revert and the winner SHALL keep its place until the published merge deadline, as in v2.

#### Scenario: Two fixes final in the same window
- **WHEN** two bounties' fixes, both based on the same head, become final and the first one moves the head
- **THEN** the second move reverts as stale, and its solver may submit the fix rebased on the new head

### Requirement: Anyone can check a copy against the head
A tool anyone can run SHALL compare a copy's `main` (a Radicle node's canonical `main`, a mirror's, or a commit given by hand) with the deployment's head and SHALL exit non-zero, naming both commits, when they differ.

#### Scenario: A mirror that agrees
- **WHEN** `pofctl verify-head` is run against a Radicle node whose canonical `main` is `Heads.head(repo)`
- **THEN** it reports both commits equal and exits 0

#### Scenario: A copy that moved without the chain
- **WHEN** the canonical `main` on Radicle is a commit the head on-chain never named
- **THEN** `pofctl verify-head` exits 1 and prints both commits

### Requirement: Readers take the code at the head on-chain
The published docs and tools SHALL tell readers, validators and solvers to build and judge the commit named by the head on-chain, and SHALL treat any difference from a copy's `main` as an alarm, not as an update.

#### Scenario: A validator fetches the base of a fix
- **WHEN** a drawn validator prepares to judge a fix
- **THEN** it fetches the head's commit by its hash from any copy, and refuses to judge if the fix's base isn't that commit
