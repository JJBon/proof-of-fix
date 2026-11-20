# Spec Delta

## ADDED Requirements

### Requirement: A deployment may judge challenges with fresh panels of the same size
A deployment constructed with `challengeSize` `Same` (design L24) SHALL judge a challenge of a verdict of k ≥ 3, and a test dispute of it (D21), by a fresh panel of k validators instead of a larger one. The panel SHALL be drawn outside the challenged panel, its auditors and its replaced judges, without parties, and SHALL NOT step down below k. With `Larger`, #132's rule SHALL apply.

#### Scenario: A challenge of a panel of 3 at 7 validators
- **WHEN** on a deployment with `kTop` 3 and `challengeSize` `Same`, a k = 3 verdict among 7 validators is challenged, or its pass is disputed with a test
- **THEN** a panel of 3 is drawn from the 4 validators outside it, and none of the original judges sits on it

### Requirement: Same-size challenges keep the lone verdict's rule and the second draw
On a deployment with `challengeSize` `Same`, a challenge of a k = 1 verdict SHALL still need a fresh panel of 3, and a challenge that can't draw its fresh panel SHALL get D27's second draw of the same size while fewer than `CAP_MIN_FAMILIES` families are seated.

#### Scenario: A lone verdict's challenge keeps 3 judges
- **WHEN** a k = 1 verdict is challenged on a deployment with `challengeSize` `Same`
- **THEN** its challenge panel is 3 fresh validators, as before

#### Scenario: An audited verdict's challenge
- **WHEN** a k = 3 verdict among 7 validators of one family had one auditor and is challenged, and the sample misses one of the 3 left
- **THEN** a second draw of 3 judges it, the original judges allowed

### Requirement: The largest issue-tier panel is set per deployment
A deployment SHALL take `kTop`, an odd number from 1 to `K_MAX`, at construction, immutable and readable. Issue-tier panels SHALL be at most `kTop`, and the race's worst-case deposit and a challenge's cover SHALL be priced for `kTop` judges. The constitution tier SHALL still draw exactly `K_MAX`.

#### Scenario: The Sepolia launch at 7 validators
- **WHEN** a $125 bounty's fix is drawn on a deployment with `kTop` 3 and 7 eligible validators
- **THEN** its panel is 3, its challenge window is CHALLENGE_WINDOW[3, level] (24 h at level A, 48 h at level B), and 4 validators remain to audit or challenge it

#### Scenario: ADRs keep their size
- **WHEN** an ADR is drawn on a deployment with `kTop` 3
- **THEN** it needs exactly `K_MAX` judges, and expires below `CONSTITUTION_MIN_ELIGIBLE` as before
