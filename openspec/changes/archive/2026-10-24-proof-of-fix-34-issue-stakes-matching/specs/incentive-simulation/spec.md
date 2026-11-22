# Spec Delta

## ADDED Requirements

### Requirement: Market scenarios for discoverers and funders
The market simulation SHALL give every issue a reporter who posts the issue stake, and SHALL provide a match farmer (it splits its pledges across fake accounts and bids on its own issues) and a self-dealer (it funds and solves its own issues). The treasury flood SHALL stake on its junk issues.

#### Scenario: Issues have reporters
- **WHEN** a market run finishes
- **THEN** the report gives, per kind, the issues reported, their stakes returned or forfeited, and the finder's fees earned

#### Scenario: Funders' cost reported
- **WHEN** the same seeds run with matching and without it
- **THEN** the report gives pledged credits per paid pledged bounty for both

#### Scenario: Matching gets more pledged issues fixed
- **WHEN** the same seeds run with matching and without it
- **THEN** the share of pledged bounties that reach their target is significantly higher with matching, and the report gives the pledged bounties paid for both

### Requirement: Acceptance criteria for discoverers and funders
The market mode SHALL be considered sound only if, over the published seeds (means with two standard errors):
- reporters of real issues earn money;
- junk reporters (the flood) lose money;
- matching gets more pledged issues funded and fixed;
- the match farmer and the self-dealer gain nothing from it;
- under a flood, real issues funded by the treasury fall by at most a quarter against no flood;
- every earlier market criterion still holds.

#### Scenario: Discoverers earn
- **WHEN** honest reporters submit real issues
- **THEN** their mean return is significantly positive

#### Scenario: Match farming doesn't pay
- **WHEN** the match farmer runs, and on the same seed the same actor pledges from one account
- **THEN** its gain from splitting is not significantly positive

#### Scenario: Self-dealing doesn't pay
- **WHEN** the self-dealer funds and solves its own issues
- **THEN** on every bounty it funded, the finder's fee it received is smaller than the market fee it paid

#### Scenario: Crowd-out bounded
- **WHEN** the flood runs, and on the same seeds no flood runs
- **THEN** real issues funded by the treasury under the flood are at least three quarters of those without it
