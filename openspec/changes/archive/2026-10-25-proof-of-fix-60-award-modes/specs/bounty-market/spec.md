# Spec Delta

## ADDED Requirements

### Requirement: Award modes
A published parameter SHALL choose how a bounty's job is awarded: `auction` (the sealed rounds, assignment and delivery above, unchanged), `race` or `claim`. In `race` and `claim` there SHALL be no bids, rounds or reserve: the bounty pays its funds, as set by its funders, to the winning contribution, through the same instalments, clawback and market fee.

#### Scenario: The auction is unchanged
- **WHEN** the mode is `auction`
- **THEN** every requirement on sealed rounds, assignment and delivery applies as before

#### Scenario: No price to bid
- **WHEN** the mode is `race` or `claim`
- **THEN** the winning contribution is paid the bounty's funds, less the market fee, and no bid or reserve exists

### Requirement: Registration check
In `race` and `claim`, opening a bounty SHALL cost a published registration fee in coin, paid by whoever opens it, for an AI check. The check SHALL write acceptance criteria from the author's requirements, which the author approves; SHALL refuse a bounty below a published size floor, which may be bundled with others; and SHALL publish an effort estimate. A bounty of 0 coin SHALL be allowed.

#### Scenario: Too small
- **WHEN** an issue's estimated effort is below the size floor
- **THEN** no bounty opens for it alone, the fee is kept for the check, and it can be bundled with other small issues into one bounty

#### Scenario: Zero coin
- **WHEN** a bounty passes the check with no funds
- **THEN** it opens, and its winning contribution is paid nothing in coin

### Requirement: The gated race
In `race`, anyone SHALL submit a solution, sealed to the oracles, with a check deposit. Submissions SHALL be checked in arrival order, and the first that passes every gate of the constitution and the bounty's acceptance criteria SHALL win. Once a bounty is won, later submissions SHALL get their deposits back unchecked. The number of attempts in progress SHALL be published.

#### Scenario: First through the gates wins
- **WHEN** two submissions arrive and the first fails a gate while the second passes every gate
- **THEN** the second wins, and the first's deposit pays for its checks

#### Scenario: Too late
- **WHEN** a submission arrives after the bounty was won
- **THEN** it isn't checked, and its deposit returns in full

### Requirement: Claim then build
In `claim`, a solver SHALL claim a bounty with a bond, a published share of its funds, and get exclusive time scaled to the effort estimate. A delivery through every gate SHALL win and release the bond. A failed delivery or a timeout SHALL forfeit the bond to the bounty and pass the claim to the next solver who claims.

#### Scenario: Claim fails
- **WHEN** a claimant's delivery fails a gate, or its time runs out
- **THEN** its bond goes to the bounty, and the bounty is open to claim again

### Requirement: The rising price
In `race` and `claim`, a bounty's price SHALL open at a published share of its funds and rise daily by a published share until the first attempt or claim locks it. The winning contribution SHALL be paid the locked price, and the rest of the funds SHALL be refunded by input when the bounty is paid. The poster's registration fee SHALL be refunded from the bounty with the finder's fee; a bundle's parts' reporters SHALL share the finder's fee.

#### Scenario: Locked by the first attempt
- **WHEN** a bounty opened at 50 % of its funds, rising 10 % a day, gets its first attempt on its third day
- **THEN** its price is locked at 70 % of its funds, and the winner is paid that

#### Scenario: Registration refunded when solved
- **WHEN** a bounty is paid
- **THEN** its poster gets its registration fee back with the finder's fee; for a bounty never paid, the fee stays spent

### Requirement: Failed fixes aren't resubmitted
In `race`, a submission the AI similarity check recognizes as a failed submission's fix on the same bounty SHALL be rejected unchecked, from any account, for the evaluation fee. A failed submission's author MAY appeal once, paying the appeal fee and a new deposit: the same fix is checked again and judged by the second jury.

#### Scenario: A variant from a second account
- **WHEN** a fix fails and the same fix is submitted again from another account
- **THEN** it's rejected unchecked, and the account pays the evaluation fee

#### Scenario: One appeal
- **WHEN** the author of a failed submission appeals it
- **THEN** the fix is checked again by the second jury; a second appeal is refused
