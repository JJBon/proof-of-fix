# Spec Delta

## Purpose
Defines how a self-governed repository heals itself with no person in control: its canonical head recorded on-chain from the judges' verdicts, mirrors that follow it, issues the system registers itself, the sponsors' pool that pays for them, and how fixes reach projects that keep human maintainers.

## ADDED Requirements

### Requirement: No human merge
In a self-governed repository no person, the owner and any maintainer included, SHALL be able to merge, revert or decline a change. The canonical code SHALL change only by a verdict of the judges, recorded on-chain.

#### Scenario: A push to a mirror
- **WHEN** an account with write access on a git host pushes a commit to the main branch of a mirror
- **THEN** the canonical head doesn't move, and the mirror is treated as wrong until it matches the recorded head

#### Scenario: The owner has no merge
- **WHEN** the owner wants a change in the canonical code
- **THEN** the only way is a bounty or an ADR judged like anyone's

### Requirement: The canonical head on-chain
The contract SHALL record each self-governed repository's head: the commit of every fix the judges pass, bound to the base commit it was checked on. A verdict whose base is no longer the head SHALL NOT move it; the winner SHALL keep its place and the price share it locked, and its fix, rebased, SHALL be checked again on the new head.

#### Scenario: The head moves
- **WHEN** the judges pass a fix checked on the current head
- **THEN** the head becomes the fix's commit, recorded with its bounty and verdict

#### Scenario: A stale verdict
- **WHEN** another fix moved the head after this fix was checked
- **THEN** this verdict doesn't move the head; its solver rebases, the fix is checked again on the new head, and it keeps its place first in line

### Requirement: A head counts only when its code is available
The head SHALL move only when the issue tier has passed the fix, at least 5 of the 7 seats have signed that they hold the fix's git bundle and will serve it for a published period, and a permanent, content-addressed copy's receipt is recorded with the head.

#### Scenario: Too few copies
- **WHEN** the issue tier passes a fix but only 4 seats have signed that they hold its bundle
- **THEN** the head doesn't move until a fifth seat signs

#### Scenario: Every host gone
- **WHEN** every git host and seed drops the repository
- **THEN** anyone can rebuild the head from the permanent copy whose receipt is on-chain, and check it against the recorded hash

### Requirement: Seats serve the code they signed for
A seat that signed that it holds a head's code SHALL serve any requested object of it, with a proof against the signed hash, within the published response time, or lose a published share of its bond, part of which SHALL pay the challenger.

#### Scenario: A seat that can't serve
- **WHEN** a challenger names a recorded head and a seat that signed for it, and the seat doesn't post the requested object with its proof within the published time
- **THEN** the seat loses the published share of its bond, and the challenger is paid from it

### Requirement: Private repositories stay off Radicle until it's fixed
Code SHALL be carried over Radicle's network only for public repositories, until a Radicle release fixing its September 2026 transport-encryption and identity flaws has been checked.

#### Scenario: A private repository
- **WHEN** a self-governed repository is private
- **THEN** its code is replicated only between the seats' own stores, never over Radicle's network

### Requirement: Mirrors follow the chain
A bot that anyone can run SHALL apply the recorded head to the git mirrors. A mirror whose main branch differs from the recorded head SHALL be treated as wrong, and any bot SHALL be able to show the difference and restore it where it has access.

#### Scenario: Two bots
- **WHEN** two bots run by different people apply the same recorded heads
- **THEN** their mirrors end at the same commit

#### Scenario: A rewritten mirror
- **WHEN** a host admin rewrites a mirror's main branch
- **THEN** any bot reports the mirror as differing from the recorded head, with both commits, and restores it if it has write access

### Requirement: System-registered issues
Anyone SHALL be able to register, with evidence, failing tests on the head, a security advisory for a dependency, or a regression, paid by the sponsors' pool if the registration check accepts it. Such issues SHALL pay no reporter share; that share SHALL go to the pool.

#### Scenario: Failing tests on the head
- **WHEN** a watcher shows a test failing on the recorded head, and the registration check accepts it
- **THEN** an issue opens with its registration fee paid by the pool, the watcher's fee is refunded, and nobody earns a reporter's share on it

#### Scenario: Junk evidence
- **WHEN** the registration check refuses the evidence
- **THEN** no issue opens, and the watcher's registration fee pays for the check

### Requirement: The sponsors' pool
Anyone SHALL be able to fund the sponsors' pool, and it SHALL be spent only by fixed rules: system issues' registration fees, a published starting amount for each system issue's bounty while the pool holds it, and refunds of accepted ADRs' fees. No person SHALL direct it.

#### Scenario: A system issue's bounty
- **WHEN** a system issue opens and the pool holds more than the published starting amount
- **THEN** its bounty opens with that amount from the pool, and anyone may pledge more

#### Scenario: An empty pool
- **WHEN** a system issue opens and the pool holds nothing
- **THEN** its bounty opens at 0 coin, and funders may pledge to it as to any bounty

### Requirement: Verified fixes offered upstream
For a project that keeps human maintainers, a bounty SHALL pay on the judges' verdict, and the winning fix SHALL be offered upstream as one pull request, which the maintainers merge or not. Attempts SHALL NOT be opened as pull requests on such a project.

#### Scenario: Paid without the merge
- **WHEN** the judges pass a fix for a bounty on a project with human maintainers
- **THEN** the bounty pays through its instalments, and one pull request with the fix and its verdict is offered upstream

#### Scenario: No spam
- **WHEN** solvers make 10 attempts on such a bounty
- **THEN** the project sees at most one pull request, the winner's
