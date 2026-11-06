# Spec Delta

## MODIFIED Requirements

### Requirement: Maintainers keep the merge decision
In a project that keeps human maintainers, they SHALL be able to decline a contribution before it enters a beta build without slashing the contributor, within the limits in "Declines are limited and appealable", and the mechanism SHALL NOT merge anything into its main line by itself. A self-governed repository SHALL have no maintainers: only the judges' verdicts change its code.

#### Scenario: Maintainer declines
- **WHEN** a maintainer declines a contribution before it enters a beta build
- **THEN** it is returned with its stake refunded in full, no reward or slash applies, and the decline is recorded with the maintainer and a reason

#### Scenario: A self-governed repository
- **WHEN** a fix passes the judges in a self-governed repository
- **THEN** no person is asked to approve it, and the canonical head moves by the verdict alone
