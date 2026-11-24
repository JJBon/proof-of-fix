# Spec Delta

## ADDED Requirements

### Requirement: A rebase verdict is challenged as any verdict
A rebase check's verdict SHALL have its own full challenge window, set by its own panel's size and level, and SHALL NOT inherit what is left of the original verdict's window. Receipt challenges and failing-test disputes (D21) SHALL be open against it in that window, with the same stakes. A dispute upheld against a rebase that would have merged SHALL earn the dispute reward from the bounty's pot, as it would against a winning fix.

#### Scenario: A rebase submitted late in the original window
- **WHEN** a rebase is counted one hour before the original verdict becomes final
- **THEN** the rebase can't merge before its own full window has passed with no challenge upheld

#### Scenario: A failing test against the rebased tree
- **WHEN** a disputer shows a failing test against a passed rebase within its window, and the dispute is upheld
- **THEN** the rebase is reversed, its submitter's reputation pays as for a reversed pass, the disputer gets its stake back and the dispute reward, and the award stays claimed for another rebase until the deadline

#### Scenario: The original reversed while its rebase is judged
- **WHEN** the original verdict is reversed in its window while a rebase of it is being judged
- **THEN** the award is clawed back and the bounty reopens as today; the rebase check is still paid by the meter, and its deposit's rest returns
