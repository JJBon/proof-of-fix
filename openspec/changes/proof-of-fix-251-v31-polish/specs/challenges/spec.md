# Spec Delta

## ADDED Requirements

### Requirement: Only a change in who can be drawn re-opens waiting draws
A draw, an audit or a challenge that waits for the set of validators to change SHALL be re-opened only by a change that can alter who may be drawn: a validator joining, leaving, qualifying, falling below the bond floor or recovering, a change of its bond tier, or a change in standing. A bond top-up that leaves the validator's tier and state as they were SHALL NOT re-open anything.

#### Scenario: A top-up of one micro-coin
- **WHEN** anyone tops up an active validator's bond by an amount that doesn't reach its next tier
- **THEN** every waiting draw, audit and challenge keeps waiting until its retry time or a real change, and keepers send nothing new for them

#### Scenario: A top-up that crosses a tier
- **WHEN** a top-up raises a validator's bond into a higher tier, or brings a below-floor validator back to the floor
- **THEN** the waiting draws, audits and challenges re-open as today

### Requirement: A lone verdict's hold counts only challengers that could be seated
A lone verdict's hold SHALL count a validator outside its panel and its auditors as a ready challenger only if its family is priced and payable at the check's prices, as a challenge draw requires, besides the conditions it counts today (bonded for the bounty, not a party, with room now, within the caps).

#### Scenario: A newly priced family outside the panel
- **WHEN** a lone verdict is held and some of the validators outside its panel are of a family priced after the check opened
- **THEN** they don't count toward ending the hold, so the window starts only when a challenge panel could be drawn without them

### Requirement: The published hold threshold is the contract's
The guides and the README SHALL state how many validators a lone verdict's hold needs as the contract computes it from the deployment's settings, and SHALL say that below that count every lone verdict stays held and that one validator pausing at the threshold holds them all.

#### Scenario: A reader counts the validators a launch needs
- **WHEN** a reader of the guides asks how many validators let a lone verdict's window start at the launch's settings
- **THEN** the guides say: three challengers plus the audits still due plus one while the audit decision is outstanding, all outside the panel, bonded for the bounty, not parties and with room now; so six such validators before the audits are drawn (seven in all with the judge) and three outside the judge and both auditors after (six in all), not three

#### Scenario: The contract's settings change
- **WHEN** a deployment's hold or audit settings differ from the launch's
- **THEN** the guides give the count from the deployment record's values, and a test checks the stated count against the contract's
