# Spec Delta

## ADDED Requirements

### Requirement: A rebase check's claim and reputation
A rebase check SHALL open a claim at the original's judged bounty for its submitter, refused over that submitter's cap. The winning solver's own rebase SHALL replace its original claim, as an appeal does. When a rebased award merges, the bounty SHALL join the winning solver's reputation, and the rebaser's claim SHALL close. A rebase pass reversed in its window SHALL cost its submitter's reputation, not the winning solver's.

#### Scenario: A newcomer rebases a large bounty
- **WHEN** an account with no reputation tries to rebase an award judged at more than its cap
- **THEN** the rebase is refused, and nothing is charged

#### Scenario: The solver rebases its own fix
- **WHEN** the winning solver rebases while its original claim is open
- **THEN** the original claim closes and the rebase's claim opens, so the bounty counts once against its cap

#### Scenario: A third party's rebase merges
- **WHEN** a third party's rebase merges
- **THEN** the winning solver's reputation rises by the bounty and the third party's claim closes, with no reputation gained or lost
