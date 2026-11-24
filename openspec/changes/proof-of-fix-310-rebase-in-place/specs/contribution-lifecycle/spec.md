# Spec Delta

## ADDED Requirements

### Requirement: The head moves to a rebased fix only after both verdicts are final
In v3.1, an award with a passed rebase check SHALL merge only once the original verdict and the rebase's verdict are both final passes, and the rebased commit's base is the head. The head SHALL then move to the rebased commit and record the rebase check's verdict. Both the original and the rebased commits SHALL count as paid. The original commit SHALL never become the head.

#### Scenario: The rebase is final first
- **WHEN** a rebase's verdict is final while the original verdict is still in its window
- **THEN** merging is refused until the original is final as well

#### Scenario: Both final
- **WHEN** both verdicts are final passes and the rebased commit's base is the head
- **THEN** anyone merges, and the head moves to the rebased commit, a fast-forward of the previous head

### Requirement: Instalments count from the later finality
A rebased award's instalments SHALL be earned from the later of the original verdict's finality and the merged rebase check's finality, so that the commit on the head has the full instalment schedule ahead of it.

#### Scenario: A rebase merged a week late
- **WHEN** a rebased award merges seven days after the original verdict's finality
- **THEN** no instalment is earned for those seven days; the first is counted from the rebase's finality

### Requirement: A conflicting fix merges about one cycle after the first
Where two fixes were judged on the same head, the second SHALL be able to reach the head about one judging cycle after the first merges (its rebase's count plus its window), not after the merge deadline. With the launch's panels of 3 at level A, that is about 27 hours plus the solver's time to rebase.

#### Scenario: The launch's production windows
- **WHEN** two fixes on the same head pass at level A with panels of 3, the first merges, and the second's solver rebases within an hour
- **THEN** the second merges about 28 hours after the first, against at least 15 days without a rebase
