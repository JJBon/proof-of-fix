# incentive-simulation Specification

## Purpose
Tests the mechanism before anything real exists: simulated honest and dishonest actors run against it under named parameters, and the results show whether honesty pays and attacks don't.

## Requirements

### Requirement: Reproducible runs
A simulation run SHALL be fully determined by its parameters, its scenario and a random seed. The same inputs SHALL give the same ledger and the same report.

#### Scenario: Same seed, same result
- **WHEN** a scenario is run twice with the same parameters and seed
- **THEN** both runs produce identical ledgers and reports

### Requirement: Actor behaviours
The simulation SHALL provide these actors, each with configurable rates:
- **Honest contributor:** submits contributions with a defect rate drawn from the baseline.
- **Spammer:** submits low-effort contributions.
- **Griefer:** files challenges without valid proof.
- **Colluding validators:** a group that votes together whatever the evidence.
- **Self-interested owner:** tries every action the mechanism allows to raise the owner's own payout.

#### Scenario: Each actor runs
- **WHEN** a scenario includes one of each actor type
- **THEN** the report shows each actor's submissions, challenges, verdicts and final balance

### Requirement: Replay of real history
The simulation SHALL replay a contribution stream built from aggregated statistics of GridCraft's public PR history: size distribution, merge rate, review rate and weekly volume. No per-person data SHALL be stored.

#### Scenario: Replay matches the baseline
- **WHEN** the replay scenario runs with the mechanism turned off
- **THEN** its contribution sizes and weekly volume match the recorded baseline within the stated tolerance

#### Scenario: No personal data
- **WHEN** the history data is inspected
- **THEN** it holds only distributions and counts, with no usernames or per-author rows

### Requirement: Report metrics
Each run SHALL report:
- each actor type's mean return per unit of effort or stake;
- contributions accepted, slashed and withdrawn;
- regressions that escaped challenge;
- time to settle;
- validator workload;
- each release's split, including the author's escrow and the owner's payout.

#### Scenario: Report produced
- **WHEN** a run finishes
- **THEN** a report with every listed metric is written, along with the parameters and seed used

### Requirement: Acceptance criteria for the mechanism
The mechanism SHALL be sound for a parameter set only if, over the published scenarios and seeds, judged with two standard errors:
- honest contributors, validators and sponsored newcomers earn a positive mean return;
- attacking kinds lose money per defective contribution, significantly; honest kinds don't gain from theirs;
- griefers lose money;
- splitting (per accepted line), collusion below the threshold and a self-interested owner gain nothing against honest play.

#### Scenario: Attacks lose money
- **WHEN** the spam, splitting, griefing and sponsorship-abuse scenarios run with the proposed parameters
- **THEN** each attacking kind's pooled mean per defective contribution, plus two standard errors clustered by seed, is below zero (sponsors' losses included), and griefers lose money

#### Scenario: Too few defective contributions to judge
- **WHEN** an attacking kind has fewer defective contributions over the seeds than the published minimum
- **THEN** the criterion is reported inconclusive for that kind, which counts as a failure, and the report gives the count

#### Scenario: Honest mistakes don't pay
- **WHEN** honest contributors, the owner or sponsored newcomers submit contributions that turn out defective
- **THEN** their pooled mean per defective contribution, minus two standard errors, is not above zero

#### Scenario: Splitting measured per accepted line
- **WHEN** the splitter's changes run split and, on the same seed, unsplit
- **THEN** the report gives each run's return per accepted line and its lines accepted, and the split return per line is not significantly higher than the unsplit one

#### Scenario: Collusion measured against honest play
- **WHEN** the collusion scenario runs at a given stake share, and again on the same seed with the ring's members acting honestly
- **THEN** the report gives the ring's gain from colluding (the difference) as a mean over seeds with its standard error, and below the collusion threshold that gain is not positive

#### Scenario: Collusion threshold measured
- **WHEN** the collusion scenario is run with the colluders' share of validator stake raised step by step
- **THEN** the report gives the smallest share at which the gain from colluding is significantly positive, and the published threshold is below it

#### Scenario: Owner can't gain by defecting
- **WHEN** the owner scenario runs with the owner playing honestly and with the owner self-interested
- **THEN** the self-interested owner's mean payout over seeds is not significantly higher than the honest owner's

#### Scenario: Unsound parameters reported
- **WHEN** a parameter set fails any criterion
- **THEN** the report names the failed criterion, the scenario and the seed, or "all" for criteria judged over seeds

### Requirement: Actors for the new rules
The simulation SHALL also provide these actors:
- **Reviewer duty:** validators drawn as reviewers find a defect with a configurable rate.
- **Declining maintainer:** declines others' contributions up to the limit and beyond, and appeals are filed against those declines.
- **Sponsored newcomer:** contributes with a sponsor's stake.
- **Sponsorship abuser:** spams through sponsored accounts it controls.

#### Scenario: Sponsorship abuse costs the sponsor
- **WHEN** the abuser's sponsored accounts spam and are slashed
- **THEN** the forfeits come out of the abuser's sponsoring stake, and the report shows the abuser's return including those losses

### Requirement: Actors for pledges
The simulation SHALL provide:
- **Pledging contributor:** every contributor with accepted work, attackers included, pledges the unpaid reward of its own accepted contributions when its balance falls short of a stake, within the limits.
- **Pledge stacker:** builds up accepted work, then submits as many defective contributions as its pledges allow, all backed by the same unpaid rewards.

#### Scenario: A short balance is covered by a pledge
- **WHEN** a contributor with accepted work in clawback can't cover a stake from its balance alone, but can within the pledge limits
- **THEN** it submits with a pledge instead of being counted as unaffordable

#### Scenario: Stacking costs the stacker
- **WHEN** the pledge stacker's defective contributions are slashed, or its backing contributions are clawed back
- **THEN** the forfeits come out of its balance and its pledged rewards. The report shows its return including those losses, and the pledges it made and lost.

### Requirement: Acceptance with pledges
The acceptance criteria SHALL hold with pledged stakes available to every actor, whenever the published pledge cap is above zero.

#### Scenario: Attacks lose money with pledges
- **WHEN** the spam, splitting, griefing, sponsorship-abuse and pledge-stacking scenarios run with pledges available to every actor
- **THEN** each attacking kind loses money per defective contribution significantly (sponsors' losses and forfeited pledges included), and every other acceptance criterion still passes

### Requirement: Capital criterion
In the replay of real history, the mechanism SHALL have at least a third fewer unaffordable submissions than the same seeds under the fixed-stake rules (no index, no reward cap), as a mean over seeds within two standard errors.

#### Scenario: The indexed stake eases the capital throttle
- **WHEN** the replay runs on the same seeds with the proposed parameters and with the fixed-stake rules
- **THEN** the report gives unaffordable submissions for both, and the proposed parameters have at least a third fewer

#### Scenario: Target missed
- **WHEN** the proposed parameters don't reach a third fewer
- **THEN** the criterion fails with both numbers, like any failed criterion

### Requirement: Actors for the indexed stake
The simulation SHALL provide an **index gamer**. It floods a release with small sound contributions to push the reward per unit of weight down, then submits defective contributions at the lower stake.

#### Scenario: Gaming the index costs the gamer
- **WHEN** the index gamer floods and then submits defective work
- **THEN** the report shows the stakes it paid before and after the flood, and its defective contributions earn a negative pooled mean

### Requirement: Market scenarios
In the market mode, the simulation SHALL generate issues at GridCraft's rate, each with a value to users, a difficulty and a private cost for each solver. It SHALL provide pledgers, honest solvers who bid their cost, and the attackers: bluffers, lowballers, no-shows (win the job and never deliver), colluding bidders, spam solvers and a treasury flood. The existing validators, hunters, griefers and owner SHALL act as before. No per-person data SHALL be stored.

#### Scenario: A market run
- **WHEN** a market scenario runs for a seed
- **THEN** bounties open, are pledged or treasury-funded, run sealed rounds and pay winners through the lifecycle, and the ledger conserves

#### Scenario: Reported per bounty
- **WHEN** a market run finishes
- **THEN** the report gives bounties opened, funded, won and unsolved; prices paid against solvers' costs; pledges refunded; treasury spend; and each actor kind's return

### Requirement: Acceptance criteria for the market
The market mode SHALL be considered sound only if, over the published seeds (means with two standard errors):
- honest solvers earn more than their cost;
- bluffing and lowballing gain nothing against bidding one's cost;
- no-shows and spam solvers lose money;
- colluding bidders gain nothing below a measured ring size;
- treasury spend stays within budget under a flood;
- the enforcement criteria still hold.

#### Scenario: Bidding your cost is best
- **WHEN** a solver bids above or below its cost, and on the same seed bids its cost
- **THEN** its return from misreporting is not significantly higher than from bidding its cost

#### Scenario: No-shows and spam lose
- **WHEN** no-shows win jobs with low bids and never deliver, and spam solvers win jobs and deliver untested solutions
- **THEN** each kind's return, its effort counted, is significantly negative

#### Scenario: Only the assigned solver builds
- **WHEN** a market run finishes
- **THEN** the report gives the solvers' total effort, and only assigned solvers spent any

#### Scenario: Collusion measured
- **WHEN** a ring of bidders coordinates (only one member bids low, the others stay out or bid high) at growing ring sizes, against the same solvers competing on the same seeds
- **THEN** the report gives the ring's gain at each size, and the smallest size at which it's significantly positive

#### Scenario: Pledges pay only for released fixes
- **WHEN** a market run finishes
- **THEN** every credit that left a pledge either paid an accepted contribution's instalments, paid the market fee on one, or was refunded; no pledged credit pays for checks

#### Scenario: Treasury flood
- **WHEN** the treasury is flooded with junk proposals
- **THEN** its spend per release never exceeds the budget, and proposals above the threshold need a panel

#### Scenario: Enforcement still holds
- **WHEN** defective solutions, griefers and a self-interested owner act in the market mode
- **THEN** attacking kinds lose money on defective work significantly, griefers lose money, and the owner can't gain by defecting

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

### Requirement: Market scenarios for reputation
The market simulation SHALL keep every account's scores as the market records outcomes, and SHALL provide a reputation farmer: it builds solver trust on cheap jobs, then wins a large job with a low bid and doesn't deliver.

#### Scenario: Scores reported
- **WHEN** a market run finishes
- **THEN** the report gives each kind's mean score and trust per role, and the honest solvers' mean bond per assignment

### Requirement: Acceptance criteria for reputation
The market mode SHALL be considered sound only if, over the published seeds, with two standard errors:
- every earlier market criterion still holds;
- crowd-out stays bounded at 50 % junk detection;
- fake accounts don't make a match farmer's own fixes significantly cheaper;
- the reputation farmer loses money;
- honest solvers' mean bond is significantly lower than with no discount, on the same seeds.

#### Scenario: Crowd-out at weak detection
- **WHEN** the flood runs at 50 % junk detection, and on the same seeds no flood runs at the same detection
- **THEN** real issues funded by the treasury under the flood are at least three quarters of those without it

#### Scenario: Reputation farming loses
- **WHEN** the reputation farmer runs
- **THEN** its return, its effort counted, is significantly negative

#### Scenario: Proven solvers lock less
- **WHEN** the same seeds run with the bond discount and without it
- **THEN** honest solvers' mean bond per assignment is significantly lower with it

### Requirement: Solvers price risk from their record
In the market simulation, a solver's break-even price SHALL use its own delivery-failure and slash rates, estimated from its recorded outcomes with the default assumption as a prior, rather than the default assumption alone.

#### Scenario: A solver that fails more
- **WHEN** a solver's record shows more failed deliveries than the default assumption expects
- **THEN** its break-even price for the same job is higher than a solver's with a clean record

### Requirement: Acceptance criteria for collusion and risk pricing
The market mode SHALL be considered sound only if, over the published seeds with two standard errors, no ring of up to six colluding solvers gains significantly against the same solvers competing, bidding one's cost is best at every published hunting elasticity, and every earlier market criterion still holds.

#### Scenario: No ring gains
- **WHEN** rings of 2, 3, 4 and 6 solvers run, and on the same seeds the same solvers compete
- **THEN** no ring's gain is significantly positive

#### Scenario: Bidding your cost is best at every elasticity
- **WHEN** the bluffing scenario runs at hunting elasticity 0, 0.5 and 1
- **THEN** bluffing and lowballing gain nothing significant at any of them

#### Scenario: Unsolved bounties reported
- **WHEN** the reserve sweep runs
- **THEN** the report gives, per reserve, the bounties paid and those closed unsolved

### Requirement: Checking scenarios
The market simulation SHALL run checking through actors instead of fixed odds: attested runners (with a published chance of a compromised enclave) and AI evaluators with accuracy per model family and errors correlated within and across families. It SHALL provide a runner forging results, a herding evaluator, a copy operator, a solver crafting fixes against one family, a bug planter, a checker with a hidden bidding identity, and a half-fixer.

#### Scenario: CI by validators, as a comparison
- **WHEN** the same seeds run with staked validators re-running the public tests and the system's runner running the hidden ones
- **THEN** the report gives the change in defects caught, honest solvers' returns and funders' cost per paid bounty against attested runners

#### Scenario: Correlated errors
- **WHEN** a hard case comes up and the correlation within a family is above zero
- **THEN** evaluators of the same family are more likely to err together than evaluators of different families

#### Scenario: Fresh rounds against the queue
- **WHEN** the same seeds run with failed attempts reopening a fresh round, and with the next queued bid taking the job
- **THEN** the report gives the change in funders' cost per paid bounty, mean price, pledged bounties paid, days to fix, and honest solvers' returns

#### Scenario: Half-fixing with and without the challenge
- **WHEN** the half-fixer runs with "not solved" challenges, and on the same seeds without them
- **THEN** the report gives its return against the same solver fixing honestly, under both rules

#### Scenario: Herding under agreement scoring
- **WHEN** evaluators are scored on agreement with the majority instead of the truth, as a comparison
- **THEN** the report gives the herding evaluator's return under both rules, on the same seeds

### Requirement: Acceptance criteria for the checking layer
The checking layer SHALL be considered sound only if, over the published seeds with two standard errors: honest runners and evaluators earn; the forging runner, herding evaluator, copy operator, crafting solver, bug planter and half-fixer lose; the hidden bidder doesn't gain; the defects caught before beta, at the default correlation, are at least those under the fixed-odds assumption; and every earlier market criterion still holds.

#### Scenario: Attacks lose
- **WHEN** each attacker's scenario runs, and on the same seeds the same actor behaves honestly
- **THEN** the attacker's return, its effort counted, is significantly lower

#### Scenario: Detection holds under correlation
- **WHEN** the base scenario runs at the published correlations
- **THEN** the share of defective deliveries caught before beta is at least the share under fixed odds, on the same seeds

#### Scenario: Correlation sweep
- **WHEN** the correlation within a family is swept
- **THEN** the report gives the share caught before beta, and the attackers' returns, at each value

### Requirement: The contributor pays for its checks: scenarios and criteria
The market simulation SHALL price each solver's expected check costs into its break-even, SHALL provide a split farmer that delivers borderline junk meant to split the jury, and SHALL compare, on the same seeds, the solver paying its checks with the bounty paying them. The split farmer SHALL lose significantly against its honest twin, and every earlier criterion SHALL still hold or be named.

#### Scenario: The split farmer loses
- **WHEN** the split farmer runs, and on the same seeds the same solver fixes honestly
- **THEN** its return, its effort and checks counted, is significantly lower

#### Scenario: Who pays the checks
- **WHEN** the same seeds run with the solver paying its checks and with the bounty paying them
- **THEN** the report gives the change in funders' cost per paid bounty, mean price, bounties paid, and honest solvers' returns

### Requirement: Model quality: scenarios and criteria
The market simulation SHALL offer models by provider and tier, each with an accuracy and a cost per verdict, let operators run the model that pays them best, and provide an operator declaring a reputable model while running a cheap one. With tiered fees, a more accurate model SHALL pay its operator more than a cheaper one, net of cost; good fixes SHALL be rejected less often than in checking v5; and every earlier criterion SHALL hold or be named.

#### Scenario: Quality pays
- **WHEN** operators run models of different tiers under tiered fees
- **THEN** the more accurate tier's net return per verdict is significantly higher

#### Scenario: Flat fees, as a comparison
- **WHEN** the same seeds run with one flat fee
- **THEN** the report gives the operators' returns by tier, the share of good fixes rejected, and honest solvers' returns under both

#### Scenario: The cheat is caught
- **WHEN** an operator declares a reputable model and runs a cheap one
- **THEN** it is suspended, and its return is significantly lower than running the model it declared

### Requirement: Award modes compared
The market simulation SHALL give every fix a quality, from its solver, that the gates measure with a published accuracy, and SHALL run the acceptance scenarios in every award mode on the same seeds. The report SHALL compare: honest solvers' earnings; wasted effort, at a sweep of attempt costs; funders' cost per solved bounty; bounties solved; good fixes accepted; time to fix; and every attack's gain.

#### Scenario: Wasted effort
- **WHEN** the race runs at a given attempt cost
- **THEN** the report gives the share of solver effort spent on attempts that weren't paid

#### Scenario: New attacks
- **WHEN** spam bounties, padded submissions, a second identity racing, or inflated effort estimates run in a mode
- **THEN** the report gives each one's gain against its honest twin, judged like the other attacks

### Requirement: Attempt costs and duplicate appeals: scenarios and criteria
The market simulation SHALL provide a fake attempter (sock accounts that start attempts they never submit, inflating the count and locking prices early) and SHALL flag honest independent fixes as duplicates at a published false-positive rate. The fake attempter SHALL NOT gain significantly against its honest twin; honest solvers SHALL still earn; falsely flagged honest fixes SHALL mostly win on appeal; every earlier criterion SHALL hold or be named.

#### Scenario: Fake attempts don't pay
- **WHEN** the fake attempter runs, and on the same seeds the same accounts behave honestly
- **THEN** its return, its fees counted, isn't significantly higher

#### Scenario: False duplicates appealed
- **WHEN** honest fixes are flagged as duplicates at the swept false-positive rates
- **THEN** the report gives the share won on appeal and honest solvers' earnings at each rate
