# Spec Delta

## ADDED Requirements

### Requirement: Cycle pools and pay by merit: scenarios
The simulation SHALL run cycle pools paid by merit and the token's per-cycle split with the outside-coin cap and the market fee, swept over the judges' detection rate (at least 50 %, 80 % and 90 %) and colluding judges (at least 0, 3, 5 and 8 of 15). Its attackers SHALL be a self-dealing team overclaiming at its best claim, colluding judges and a farmer circling its coin through socks; investors SHALL challenge. Each defence SHALL also run alone.

#### Scenario: Records without challenges
- **WHEN** judges' merit records run without challenges under a colluding majority
- **THEN** the report shows the colluders' share of draws and the share of the pool overpaid, against the run with challenges (in `reports/cyclepool-v1.md` records alone made both worse)

#### Scenario: The fee's form
- **WHEN** the capped token-indexed fee runs beside a flat 20 % fee, the uncapped indexed fee and a fee by bounty size, against a farmer faking 200-coin importance
- **THEN** the report gives each one's protection, as the share of their funding honest funders get back in tokens when farming starts to beat the farmer's honest twin, and what each costs honest funders

#### Scenario: Honest participants' costs
- **WHEN** honest reporters claim importance with the AI estimate's error (30 %), and investors challenge with mistakes
- **THEN** the report gives honest reporters' forfeited stakes, honest fixers' losses to mistaken challenges, and challengers' net, each as a share of the pool

#### Scenario: Default runs unchanged
- **WHEN** the earlier runs are repeated with cycle pools off
- **THEN** their reports are identical to before

### Requirement: Funder tokens, pools and adaptations: scenarios
The simulation SHALL run merit-cycles' rules: the token earned by funders by merit with the per-fix cap and the cut redistributed, pay up to merit, each funder's leftover choice, the index pool by merit, adaptations (b) and (c), and a blocked coin. It SHALL report each funder product's tokens per coin, the coin left waiting, merit left unpaid, and supply, with (b) and (c) on and off.

#### Scenario: The cut redistributed or not minted
- **WHEN** 1-cent pledges on every fix of unfunded repositories run with the per-fix cap, once with the cut redistributed and once not minted
- **THEN** the report gives honest pool investors' tokens per coin in each (in `reports/fundertoken-v1.md`, −16 % not minted and +0.2 % redistributed)

#### Scenario: The products
- **WHEN** bounty buyers, bounty pickers, single-repository pools and the index pool fund the same network
- **THEN** the report gives each one's tokens per coin spent, its break-even price, its coin left over and its value back per coin at the flow-clearing price

#### Scenario: The index by merit
- **WHEN** the index pool spreads its coin by merit over a window, against #194's spread by need
- **THEN** the report gives the index funders' tokens per coin and its coin waiting in stalled repositories, for each window swept

#### Scenario: The adaptations
- **WHEN** (b) and (c) run alone and together, and (a) runs with a small base for comparison
- **THEN** the report gives solvers' pay per merit dollar, merit left unpaid, coin waiting, funders' tokens per coin, and mint over burn at fixed prices

#### Scenario: A blocked coin
- **WHEN** the only allowed coin is blocked for a cycle
- **THEN** the report shows that cycle's tokens going to the fixers by merit, the same emission as with the coin working, and every credit still owed

### Requirement: Attacks are judged against the honest use of the attacker's coin
Every attack's gain SHALL be measured against its honest twin: the same actor, on the same seed and in the same run, doing the honest version of its play (fixes claimed at their worth, no coin circled through socks) and funding the pools with the attack's coin, or keeping it where that pays back less than the coin. An attack SHALL NOT be judged against a twin that leaves its coin idle when honest funding pays more.

#### Scenario: Why not a twin that does nothing
- **WHEN** funding pays a return, as it does when token value from outside use is burned
- **THEN** any play that funds beats a twin that does nothing, so plain investing would look like an attack; the honest twin removes that (`reports/fundertoken-v2.md`, #194, summary 3; ADR 0005 draft, #195)

#### Scenario: Funding that pays nothing back
- **WHEN** funders get nothing back, as while the token has no price
- **THEN** the honest twin keeps its coin, its profit equals doing nothing's, and the figures of #177, #182 and #184 stand

#### Scenario: An attacker's baseline
- **WHEN** an attack spends coin of its own (self-funding, sock funders or pledges)
- **THEN** its profit is measured against an honest funder and solver with the same coin, in the same run, and the report gives both and the difference

#### Scenario: Honest funding isn't an attack
- **WHEN** funding pays a return, and an actor only puts its coin in the pools
- **THEN** its gain over its honest twin is 0 at every token price, though it gains over a twin that funds nothing

#### Scenario: How the gain is computed
- **WHEN** the token has a price
- **THEN** the gain is the attack's profit over a twin that funds nothing, less what the attack's own coin would have earned beyond itself in honest pools at that price, when that is positive, as `invested_gain` and `pays_over_investing` compute it in `pof/sim/fundertoken.py` (#194)

### Requirement: Cycle pools and pay by merit: criteria
At 80 % detection and up to 5 of 15 colluding judges, with every defence, overclaiming SHALL lose money against its honest twin, and, where the run gives the token a price, SHALL do so at every price swept up to $100 a token. Every other result SHALL be a figure in the report, not a pass/fail criterion, including the gains of self-dealing and of 1-cent pledges over their honest twins. The detection rate SHALL be replaced by #160's measured rate once it exists.

#### Scenario: Overclaiming loses
- **WHEN** a team overclaims 5 trivial fixes a cycle, with challenges, merit records, audits and the stake forfeited by the 3 × rule, judges see through 80 % of overclaims, and up to 5 of 15 judges collude
- **THEN** the team's best claim earns less over the year than its honest twin (the same fixes claimed at their worth, with the same coin put to honest use, on the same seed), and the report gives the share of the pool overpaid (at most about 1 % in `reports/cyclepool-v1.md`)

#### Scenario: Overclaiming loses at any price
- **WHEN** the token has a price, from use or from outside use's burns, swept up to $100 a token, with 0, 3 and 5 of 15 judges colluding
- **THEN** overclaimed merit funded from a second wallet earns less than its honest twin at every price (it lost $2,900–4,700 a year in `reports/fundertoken-v2.md`), so what stops it is the issue stake and the challenges, not a low price

#### Scenario: Self-dealing and 1-cent pledges are figures
- **WHEN** a team funds its own fix, claimed at its worth, from a second wallet, or a farmer pledges 1 cent on every fix of unfunded repositories with the per-fix cap on
- **THEN** the report gives the price from which each beats its honest twin and its gain a year there, without a pass mark (in `reports/fundertoken-v2.md`: self-dealing from $1.16–1.54 a token by $11–43 a year, the edge any bounty has, since its own coin is paid in full when a pool is short; 1-cent pledges from about $16 a token by $4–18 a year)

#### Scenario: The measured rate
- **WHEN** #160 has measured the judges' detection rate
- **THEN** the criterion is judged at the measured rate, and the swept rates stay as figures
