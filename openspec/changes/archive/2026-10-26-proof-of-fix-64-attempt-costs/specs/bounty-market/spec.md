# Spec Delta

## MODIFIED Requirements

### Requirement: The gated race
In `race`, starting an attempt SHALL pay a published attempt fee, and SHALL be published with the count of attempts in progress. Anyone SHALL submit a solution, sealed to the oracles, with a check deposit. Submissions SHALL be checked in arrival order, and the first through every gate of the constitution and the bounty's acceptance criteria SHALL win. A submission after the bounty is won SHALL go unchecked and pay the evaluation fee.

#### Scenario: First through the gates wins
- **WHEN** two submissions arrive and the first fails a gate while the second passes every gate
- **THEN** the second wins, and the first's deposit pays for its checks

#### Scenario: Too late
- **WHEN** a submission arrives after the bounty was won
- **THEN** it isn't checked, and it pays the evaluation fee

#### Scenario: An attempt costs
- **WHEN** a solver starts an attempt
- **THEN** it pays the attempt fee, which isn't refunded, and the published count of attempts rises by one

### Requirement: Failed fixes aren't resubmitted
In `race`, a submission the AI similarity check recognizes as a failed submission's fix on the same bounty SHALL be rejected unchecked, from any account, for the evaluation fee. Its submitter MAY appeal the rejection, at its own cost, to an AI jury of a published size from different providers; if the jury finds the fix independent, it SHALL be checked like any submission. A failed submission's author MAY appeal once, for the same fix, to the second jury.

#### Scenario: A variant from a second account
- **WHEN** a fix fails and the same fix is submitted again from another account
- **THEN** it's rejected unchecked, and the account pays the evaluation fee

#### Scenario: An independent fix flagged as a duplicate
- **WHEN** an independent fix is rejected as a duplicate and its submitter appeals
- **THEN** the appeal jury, one evaluator per provider, finds it independent, and it's checked like any submission

#### Scenario: One appeal
- **WHEN** the author of a failed submission appeals it
- **THEN** the fix is checked again by the second jury; a second appeal is refused
