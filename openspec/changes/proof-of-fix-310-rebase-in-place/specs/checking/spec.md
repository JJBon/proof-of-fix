# Spec Delta

## ADDED Requirements

### Requirement: A rebase check is a full check of the rebased tree
A rebase check SHALL be judged by one fresh counted panel, drawn by the deployment's ordinary rules at the bounty the original was judged at, with its shadows and random audits. Its judges SHALL run the fix's tests on the rebased commit, with the protected paths taken from the new base and each run done twice, exactly as for any fix. They SHALL refuse a rebased commit whose base isn't the head.

#### Scenario: A semantic conflict with the first fix
- **WHEN** the first fix added a protected test, and the rebased second fix breaks it although the two patches applied without a textual conflict
- **THEN** the rebase check's test runs fail on the new base's protected tests, and its panel fails the rebase

#### Scenario: Tests changed by the rebase
- **WHEN** a rebased commit changes a protected test
- **THEN** its runs use the new base's copy of that test, as for any fix

### Requirement: The judges compare a rebase with the approved fix
For a rebase check, the judge's case SHALL include the approved fix's diff, the rebased diff and their range-diff. The rubric SHALL fail a rebase whose changes go beyond the approved fix adapted to the new base, even if its tests pass.

#### Scenario: A rebase that smuggles in a change
- **WHEN** a rebased commit adds code unrelated to adapting the approved fix to the new base
- **THEN** its judges fail it, whatever its tests say

#### Scenario: A clean rebase
- **WHEN** the rebased diff is the approved diff, with only the base's context changed, and the tests pass
- **THEN** its judges pass it, and their metered usage covers a short case: the range-diff, not a fresh review of the whole issue
