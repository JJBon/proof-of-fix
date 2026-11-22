# Spec Delta

## MODIFIED Requirements

### Requirement: Challenger stake
A challenge SHALL be accepted only with a challenger stake locked from the challenger's account. A challenge that is rejected SHALL cost the challenger a published share of that stake, which goes to the challenged contributor and the validators. An upheld challenge SHALL pay the challenger from the contribution's escrowed reward as well as from its forfeited stake.

#### Scenario: Rejected challenge costs the challenger
- **WHEN** a challenge is rejected
- **THEN** the challenger loses the published share of their stake, split between the contributor and the validators who judged it, and gets the rest back

#### Scenario: Upheld challenge pays the challenger
- **WHEN** a challenge is upheld
- **THEN** the challenger gets their stake back, the published share of the forfeited stake, and the published share of the forfeited escrowed reward; the rest of the reward returns to the contributors' pool

## ADDED Requirements

### Requirement: Review duty
Every contribution entering a beta build SHALL get one reviewer, drawn like a validator (stake-weighted, seeded, excluding the author, the sponsor and linked accounts). The reviewer SHALL post a review bond and report found or not found within the challenge window. A reviewer who finds a defect SHALL file it as a challenge.

#### Scenario: Reviewer drawn
- **WHEN** a contribution enters a beta build
- **THEN** one reviewer is drawn from the validators, never the author, the sponsor or an account linked to either, and their review bond is locked

#### Scenario: Review completed
- **WHEN** the reviewer reports within the window
- **THEN** the review counts as completed work for the validators' pool once its outcome is known, and the bond is returned when the contribution's last instalment is paid (a missed defect can still be proven until then)

#### Scenario: Missed defect
- **WHEN** a reviewer reported no defect and the contribution is later slashed, during the window or the clawback
- **THEN** the reviewer loses the published share of the review bond, and the missed review earns nothing from the pool

#### Scenario: No report
- **WHEN** the reviewer doesn't report within the window
- **THEN** they lose the published share of the bond, as for a missing reveal
