# Spec Delta

## ADDED Requirements

### Requirement: A stale winner is rebased in place
In v3.1, a claimed award that isn't merged, with its verdict still a pass, and whose base is no longer the head SHALL accept a rebase: the fix rebased onto the current head, submitted as a new check. The award SHALL keep its place, its epoch and its locked price. A rebase onto anything but the current head, of an award that is mergeable or closed, or of a commit already paid SHALL be refused. At most one rebase check SHALL be undecided at a time.

#### Scenario: Two fixes judged on the same head
- **WHEN** bounty A's fix is merged and bounty B's claimed fix, judged on the same head, can no longer merge
- **THEN** B's solver submits B's fix rebased on the new head as a rebase check, and B stays claimed with its price and epoch

#### Scenario: A rebase onto an old head
- **WHEN** a rebase names a base that isn't the head at that moment
- **THEN** it is refused, and nothing is charged

#### Scenario: A rebase of a mergeable fix
- **WHEN** someone submits a rebase for an award whose base is still the head
- **THEN** it is refused, because the award can merge as it is

#### Scenario: Two rebases at once
- **WHEN** a rebase check of an award is still undecided and another rebase of it is submitted
- **THEN** the second is refused

### Requirement: Who may rebase, and who is paid
The winning solver SHALL be able to rebase at any time. Anyone else SHALL be able to rebase only once `REBASE_GRACE` has passed since the head last moved. The award SHALL stay the winner's. A third party's rebase that merges SHALL earn `REBASE_SHARE_BPS` of the award's price from the bounty's pot at its payment, capped by what the pot holds after the award.

#### Scenario: A third party within the grace period
- **WHEN** another account submits a rebase before `REBASE_GRACE` has passed since the head moved
- **THEN** it is refused

#### Scenario: A third party's rebase merges
- **WHEN** after the grace period another account's rebase passes, becomes final and is merged
- **THEN** the winner keeps the award, and the rebaser gets `REBASE_SHARE_BPS` of the price from the pot's rest when the bounty is paid

### Requirement: A failed rebase reopens at once
When a rebase check submitted by the winning solver is counted as a fail and its base is still the head, the award SHALL close with nothing earned and the bounty SHALL reopen at once, without waiting for the merge deadline. Any other ending of a rebase check (a third party's fail, a fail after the head moved again, a withdrawal, a time-out or a release) SHALL end only that check, and the award SHALL stay claimed.

#### Scenario: The solver's rebase fails
- **WHEN** the solver's rebase is counted as a fail while its base is the head
- **THEN** anyone may reopen the bounty at once, the award closes with nothing earned, and a pass waiting behind it in the queue wins

#### Scenario: A stranger's rebase fails
- **WHEN** a third party's rebase is counted as a fail
- **THEN** the award stays claimed, and the solver or anyone may rebase again

#### Scenario: The head moved during the check
- **WHEN** the solver's rebase is failed because its base went stale before its panel judged it
- **THEN** the award stays claimed, and the solver may rebase again onto the new head

### Requirement: A rebase pays its metered check
A rebase check SHALL post the same deposit, or the same flat judges' fee, as a fix's submission, and its judges SHALL be paid by the meter, from its submitter's deposit. The rest SHALL return to its submitter as for any check. No attempt, evaluation or appeal fee SHALL be charged for it. A rebase check that merges SHALL have its metered checks refunded from the bounty's pot at its payment, as the winner's are.

#### Scenario: A rebase that merges
- **WHEN** a rebase check passes, becomes final and its commit is merged, and the bounty is later paid
- **THEN** its submitter gets back the rest of its deposit after finality, and the metered checks from the pot's rest at the payment

#### Scenario: A rebase that fails
- **WHEN** a rebase check fails
- **THEN** its submitter has paid its panel's meter and nothing more

### Requirement: The merge deadline follows the latest rebase
The deadline after which an unmerged award closes and its bounty reopens SHALL count `mergeDays` from the later of the original verdict's finality and the latest passing rebase check's finality. While a rebase check submitted before the deadline is undecided, the award SHALL NOT expire.

#### Scenario: A rebase in flight at the deadline
- **WHEN** the merge deadline passes while a rebase check submitted before it is still being judged
- **THEN** the award doesn't expire until that check is decided, and, if it passes, until `mergeDays` after its finality

#### Scenario: Nobody rebases
- **WHEN** an award's base went stale and nobody rebases it within `mergeDays` of its finality
- **THEN** anyone may close it with nothing earned, and the bounty reopens
