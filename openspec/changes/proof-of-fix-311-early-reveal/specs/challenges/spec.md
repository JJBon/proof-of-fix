# Spec Delta

## ADDED Requirements

### Requirement: A panel reveals once every seat has committed
A judging panel's reveal (counted, audit or challenge) SHALL open as soon as every one of its seats is filled and has committed (a counted panel also as the next requirement says), without waiting for the commit period to end; until then no reveal SHALL be accepted. The commit and reveal deadlines SHALL stay the limits for a judge that is slow or silent, and a silent judge SHALL be replaced as before.

#### Scenario: Every judge commits promptly
- **WHEN** all three judges of a counted panel commit within ten minutes of the draw, with a two-hour commit period, and each reveals at once
- **THEN** the verdict is counted within minutes of the last commit, and its challenge window starts then, not after the two hours

#### Scenario: A reveal before the panel is full
- **WHEN** two of three judges have committed and one of them tries to reveal
- **THEN** the reveal is refused, so nobody's vote is public while a seat can still commit

#### Scenario: A silent judge on a panel that could reveal early
- **WHEN** two of three judges commit within minutes and the third never commits
- **THEN** nobody can reveal until the commit period ends; the silent judge is then replaced as before, and the reveal opens once its replacement commits

### Requirement: No counted vote is public while a shadow can still commit
A counted panel's reveal SHALL open early only once every shadow judge drawn with it has committed; otherwise it SHALL open when the commit period ends, as before, when every shadow's commit period has ended too. So a shadow's commit SHALL never be accepted after a counted vote is revealed. A shadow drawn while its submission waited for a panel SHALL have its commit refused from the moment the counted panel is drawn.

#### Scenario: A candidate copies the counted judges
- **WHEN** a candidate drawn as a shadow waits to see the counted verdicts before committing its own
- **THEN** it can't: no counted judge can reveal while it may still commit, and once its commit period has ended its commit is refused

#### Scenario: A shadow front-runs a counted reveal
- **WHEN** a shadow sees a counted judge's reveal transaction waiting to be mined and sends its own commit ahead of it
- **THEN** there is no such reveal to see: a counted reveal is accepted only after every shadow committed or the commit period ended

#### Scenario: Counted judges and shadows all commit promptly
- **WHEN** the three counted judges and the two shadows of a submission all commit within ten minutes of the draw
- **THEN** the counted judges reveal at once and the verdict is counted within minutes; the shadows reveal and are scored as before

#### Scenario: A silent shadow
- **WHEN** every counted judge commits within minutes and a shadow never commits
- **THEN** the counted reveal opens when the commit period ends, as it does today, and the shadow counts a miss

#### Scenario: A waiting submission's shadows when the panel is drawn
- **WHEN** a submission that waited, with shadows still inside their commit period, gets its counted panel
- **THEN** those shadows' commits are refused from then on, and the ones already committed reveal and are scored as before

### Requirement: A waiting shadow cut short counts no miss
A shadow drawn while its submission waited, whose commit period was closed early by the counted draw and that hadn't committed, SHALL NOT count a miss or a draw toward its reveal rate. A shadow that committed and then doesn't reveal in time SHALL count a miss as before.

#### Scenario: A waiting shadow still checking when the panel is drawn
- **WHEN** a waiting submission's shadow is still checking the fix when the counted panel is drawn, then tries to commit
- **THEN** its commit is refused, and the draw counts neither as a reveal nor as a miss for its qualification
