# ADR 0007: The solver-side parameters after the judge measurement: seats by rank, test disputes, appeals, the reputation cap, the judges' fee, and no solver's deposit

- **Status:** decided by the owner on 2026-11-19 (proof-of-fix#251), every value as recommended. It takes effect when merged. No constitution tier exists yet to pass it. It **replaces ADR 0004 in part**: the solver-side values below (#132 task 10.2). ADR 0004's other values stand (section "What stays from ADR 0004").
- **Amended 2026-11-19 (owner, #251), for the Sepolia launch:** D30 is the **pure taxi fare** (`judgeFee` 0): a fix posts FeesV3's worst-case deposit, its judges are paid by the meter and the rest returns to the solver; the flat fee and its value are deferred to a mainnet decision. **D24's appeal has no stake.** **Sepolia: a solver pays only the metered validation** (no attempt, evaluation or appeal fee). Sections "The appeal", "The judges' fee", "Named trust points" and "Consequences" say so; their earlier text is kept where marked.
- **Date:** 2026-11-19
- **Author:** Claude, an AI model, drafting for the owner (proof-of-fix#251; #132 tasks 10.2, 11.2 and 12.2), from the owner's decisions of 2026-11-19. Interest disclosed: the owner may run one validator, disclosed and under the same rules as any other (ADR 0003). No founder's share, no token, no share of bounties.
- **Constitution articles changed:** none of v2's. As in ADR 0004, these values go into v3's constitution when it is deployed (#132 D15) and are fixed per version.
- **Protected paths touched:**
  - `docs/adr/0007-solver-side-parameters.md`
  - `docs/adr/0004-open-validators.md` (its status line only: superseded in part by this ADR)

## Problem
ADR 0004 fixed v3's values on assumed judges: 1.1 bad fixes merged per 100 paid. #160 measured real judges, and v3 as designed merged 10–18 per 100 paid. #132 then added rules on the measured verdicts (design D20–D30, #236) and left their values for a new parameters ADR (task 10.2), part by part (tasks 11.2 and 12.2). The launch on Sepolia (#251) needs them before contract batch 3: its tasks 3.3 and 3.6 build them.

The evidence, all exploratory unless marked, every ± two standard errors:

| Report | Date | Task | What it decides here |
|---|---|---|---|
| [`open-validators-measured-v3.md`](../../reports/open-validators-measured-v3.md) | 2026-11-15 | #132 10.1, seeds 1–40 | D20's `SEAT_MARGIN` and `CAP_MIN_FAMILIES`; D21's `EVIDENCE_STAKE` and `EVIDENCE_REWARD_BPS`; `APPEAL_WINDOW` |
| [`open-validators-measured-v4.md`](../../reports/open-validators-measured-v4.md) | 2026-11-15 | #132 11.1, seeds 1–40 | D24's appeal and its stake; D27's second draw; D25 and D26 (deferred) |
| [`open-validators-measured-v5.md`](../../reports/open-validators-measured-v5.md) | 2026-11-15 | #132 12.1, seeds 1–40 | D29's reputation cap; D30's judges' fee; the one-solver gap with no deposit |
| [`active-solvers-v1.md`](../../reports/active-solvers-v1.md) | 2026-11-18 | #251 3.2, **fresh seeds 41–80, pre-registered** | the minimum of 3 active solvers, `ACTIVE_WINDOW`, whose tests count, the sybil of three |
| [`faucet-spam-v1.md`](../../reports/faucet-spam-v1.md) | 2026-11-18 | #251 3.15 | the judges' fee on Sepolia ($40), decided in the launch's L17 |

## Options
1. **Keep ADR 0004's solver-side rules** (any family mix under the family cap, no test disputes, no appeal, per-check charges). Measured, that merges 14–18 bad fixes per 100 paid (report v3), and a solver of bad fixes gains.
2. **Adopt the recommended rules with a solver's deposit** (2,500 to 4,000 of the bounty). It closes the one-solver gap and the sybil of three in the simulation (reports v5 and active-solvers-v1), but every honest solver pays it on every fix, and the owner is against it (2026-11-15, #250).
3. **Adopt the recommended rules with no deposit,** and name what that leaves open. Chosen by the owner on 2026-11-19.

## Decision
Option 3. The values below are decided. Each part of D25 and D26 is left out of the testnet launch (section "Deferred").

### Seats by rank (D20)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `SEAT_MARGIN` | 5 points | report v3 (2026-11-15) | on known answers every value from 2 to 25 seats the same families; below 2, three level families lose their seats (31.6 % ± 0.4 of good fixes unpaid at 0, against 9.0 % ± 0.3 from 2) |
| `CAP_MIN_FAMILIES` | 3: the family cap applies only while at least 3 families are seated | report v3 | at 2, two capped families can't fill a panel of 3 (81.6 % ± 0.3 of submissions wait); at 4, slightly worse (10.4 % ± 0.5 of good fixes unpaid against 9.0 % ± 0.3) |
| `SCORE_MIN` in the seat rule | 70 %, as ADR 0004 | report v3 | it, not the margin, keeps weak families out (13.2 ± 0.3 bad fixes per 100 paid at 50 %, against 4.5 ± 0.2) |

With these, seats by rank with test disputes merge 4.5 ± 0.2 and 8.5 ± 0.2 bad fixes per 100 paid on known answers (the tests fail them; they pass the tests and are wrong), against 17.8 ± 1.2 and 14.3 ± 1.0 for v3 as designed (report v3). One family may hold every seat while it is more than `SEAT_MARGIN` ahead (owner, 2026-11-14).

### The test dispute (D21)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `EVIDENCE_STAKE` | the larger of $5 and 10 % of the bounty | report v3 | if a wrong test is accepted 1 time in 5, a disputer with no evidence gains +$3,880 ± 192 a year at $5 flat and +$2,733 ± 194 at 5 %; at 10 % no wrong test is worth posting |
| `EVIDENCE_REWARD_BPS` | 1,000: 10 % of the bounty, to the disputer of an upheld test | report v3 (the simulation doesn't decide it) | an honest contender running GPT-6.1 nets +$760 ± 71 a year at 1,000 (with a deposit in that run) |

**With no solver's deposit, the reward is the disputer's only pay besides its stake back.** Report v3's contender rows were paid the deposit too. Without it, report v4 (section 7, expected values) finds that a rival solver's search of a passed fix loses $0.10 to $0.35 at 1,000 with per-issue bounties: nothing pays a rival to look. Report v5's result for D29 and D30 rests on honest solvers who search every pass anyway (a trust point, below).

### The appeal (D24)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| Who decides | a fresh draw of the seated families; no contender sits (owner, 2026-11-15) | design D24 | a panel of other families overturned 81 % ± 1 of correct rejections (report v3) |
| The evidence | a test that fails on the base code and passes with the fix, twice each way, test files only | report v4 | the same family with nothing new restores 0 % of wrongly rejected good fixes (report v3) |
| ~~`APPEAL_STAKE`~~ | **none (owner, 2026-11-19, #251): an appeal pays only its fresh panel's metered validation**, as any submission (the taxi deposit, its rest refunded); nothing goes to the sponsors' pool when it fails. Was: the larger of $5 and 10 % of the bounty, lost to the sponsors' pool | report v4, design D24 | the stake was sized so an appeal pays only above stake / (stake + what it wins), about 1 in 6 at 10 %; without it, an appealing solver of bad fixes risks only the panel's checks: see trust point 6 |
| `APPEAL_WINDOW` | 72 h | the simulation's value in reports v3 and v4 (chosen) | no result depends on it (report v3). With no deposit it only sets how long a rejection waits to become final |

### The second draw among few families (D27)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `SECOND_PANEL` | "few families": only while fewer than `CAP_MIN_FAMILIES` (3) families can judge | report v4, section 6 | verdicts never final fall from 23.6 % ± 2.5 and 23.0 % ± 2.4 to 0.1 % and 0.0 % under v3's seats, and from 2.7 % ± 0.2 to 0.0 % under seats by rank with one family. With three families seated 0.3 % ± 0.1 stay open; "always" would close those too, and was not chosen |

The second draw ends the wait; it corrects nothing, since the same family repeats its verdict. Tests (D21, D24) correct wrong verdicts.

### The reputation cap (D29)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `REP_BASE` | $50 | report v5 | at $100 free identities gain again (+$670 to +$2,075 a year) |
| `REP_MULT` | 1 | report v5 | |
| `REP_ON_REVERSAL` | "minus": a reversal subtracts, it doesn't reset | report v5, section 6 (post hoc) | a reset costs an honest solver $637–773 a year through its own reversed mistakes (Opus 5.5); "minus 2×" costs $58–112, attackers unchanged at 3 and 10 solvers |
| `REP_LOSS_X` | 2: a pass reversed by a test takes 2 × its bounty off the reputation, not below zero | report v5 | as above |

An honest newcomer may claim a median bounty ($86) within 0.6–0.9 weeks (report v5).

### The judges' fee (D30)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `JUDGE_FEE` | one flat fee per submission on arrival, in place of its panels' per-check charges; never refunded, never more on rejection | report v5 | measured at $5.03 a submission on v5's base network (7.6 checks at the break-even service fee of $0.53, plus $0.13 of usage), against $0.96–1.55 charged at the fee's floor |
| On Sepolia | **the pure taxi fare: `judgeFee` 0** (owner, 2026-11-19, #251). A fix's submission posts FeesV3's worst-case deposit, its judges are paid by the meter, and whatever is left returns to the solver, pass or fail, withdrawn or not; the pool keeps no fee. **A solver pays only the metered validation** (owner, 2026-11-19): no attempt, evaluation or appeal fee, no appeal stake | owner, 2026-11-19 | the flat $40 first decided (L17, 2026-11-18, from report faucet-spam-v1) is withdrawn for the launch; faucet-spam-v1 simulated a flat fee ($5.03 and $20–40), not the taxi fare. The flat fee and its value are deferred to a mainnet decision; the contracts keep it (`judgeFee` above 0) |
| Its value on later networks | re-measured each period from the validators' posted costs: every check the network paid for in the period at the break-even service fee plus usage, over the submissions | design D30 | |

D29 and D30 hold only together: alone, neither closes the attackers with 1–3 active honest solvers (report v5). **On Sepolia D30 is the taxi fare, so report v5's R+F result doesn't carry over: the testnet runs R with a refunded deposit** (trust point 7).

### No solver's deposit (D22, D28)
- **There is no solver's deposit:** `SOLVER_DEPOSIT_BPS` is 0, and absent from the contracts. A rejected fix costs its solver the judges' fee and nothing more.
- **No deposit "only while fewer than three solvers are active" either.** The sybil of three would switch it off with the same identities (report active-solvers-v1, section 2.5).
- D22's deposit rules and D28's hold around an appeal are therefore void. A dispute's reward comes from the bounty (`EVIDENCE_REWARD_BPS`), and an appeal puts at risk only its panel's metered checks (its stake was dropped on 2026-11-19).
- **The one-solver gap is reported, not closed.** It is a named trust point (below). The owner is against a deposit; this ADR doesn't recommend one.

### The minimum of active solvers (the launch's L6, #251 task 3.2)
| Parameter | Value | Source | Evidence |
|---|---|---|---|
| `ACTIVE_SOLVERS_MIN` | 3: pledges are refused while fewer are active | report active-solvers-v1 (2026-11-18) | with the repository's own solvers counted, every attacker of v5 stays at or below its twin with 1, 3 and 10 honest solvers at every window, except one cell (below). A higher minimum doesn't fix that cell, and no minimum stops the sybil |
| `ACTIVE_WINDOW` | **26 weeks** | report active-solvers-v1, its pre-registered rule | 13 weeks leaves +2.4 ± 0.8 and +3.4 ± 0.9 more good fixes unpaid a year in a repository of 1 issue a week with 3 solvers; 6 weeks +7.0 to +16.1. No attacker row differs between windows. The cost: a repository whose solvers all left keeps taking pledges for up to half a year |
| Whose activity counts | only the repository's own solvers: an upheld test dispute counts only for an identity that has a final passing fix in the repository | report active-solvers-v1, section 3 (not simulated) | if anyone's upheld test counts, contenders open a one-solver repository within about 2 weeks, and every v5 attacker gains again (up to +$3,399) |

### Deferred: not in the testnet launch
- **D25, a contender's sponsorship** (`SPONSOR_REWARD_BPS`): not decided. It can follow after the launch. Report v4: at 1,000 it doesn't pay an honest sponsor; at 2,500 it does when its model is better.
- **D26, known-answer issues** (`KNOWN_RATE`, `KNOWN_MIN`, `KNOWN_WINDOW`): not decided. It waits for #136's keyless known-answer design (#132 task 11.6); no source of known answers without a privileged author exists yet.
- **The pot by impact:** not proposed until #247 is measured (#132 task 12.7).

### Named trust points
These remain after the rules above. ADR 0004's five trust points stand beside them.
1. **The one-solver gap.** With no deposit and only one active honest solver, R+F leaves an attacker +$237 to +$3,870 a year (report v5; the retrier and the long con are the largest). The minimum of three keeps new money out of such a repository when it has one solver by accident.
2. **The sybil of three.** One party can make three identities active with trivial fixes to issues it files itself, for about $106 and 19 fixes a year at 13 weeks, $64 at 26 weeks (38 and 23 faucet requests on Sepolia at a $40 fee; under the taxi fare it pays only its fixes' metered checks, less still). With one honest solver it then gets back almost all of the one-solver gain: up to +$3,680 ± 384 a year (report active-solvers-v1). With 3 and 10 honest solvers it gains nothing. What bounds it: D29's cap ($50 of open claims for each new identity) and every bad fix still facing the panel and disputes. Of the options tried, only a deposit of about 25 % closes it, and the owner declined one.
3. **Assumed rates.** D21's and D24's safety at the launch rests on rates nobody has measured: how often a contender or rival finds a failing test for a bad pass (1 in 4 for honest solvers in report v5; at 1 in 10 R+F fails with 3 solvers too, up to +$2,932 ± 540), how often a panel accepts a wrong test (1 in 20 assumed), and how a panel reacts to an appeal's passing test (swept in report v4: an appealing solver of bad fixes loses at 1 in 20, breaks even near 1 in 5, gains at 1 in 2). The paid runs that would measure them (#132 tasks 10.3 and 11.3) are not decided.
4. **The long con under GPT-6.1 with 3 solvers:** +$451 ± 336 a year, the one gate cell above its twin (report active-solvers-v1). It is at even without the gate too (+$177 ± 382), so it is R+F's margin, not the gate's.
5. **One family's blind spot (D20, accepted 2026-11-14).** While one family is seated, a prompt injection that fools it decides the panel; disputes are the remaining defence.
6. **Spam can block validation on the testnet (accepted by the owner, 2026-11-19).** Under the taxi fare a submission, and an appeal, costs its solver only its panel's metered checks, refunded down to what was used: junk fixes from free identities, and a solver appealing every rejection, each pay the meter and nothing more, so a spammer can fill the validators' capacity and hold honest fixes in the queue. Bounded by the nodes' spending caps (#253's capacity, `MAX_CHECKS_PER_HOUR`, and each node's budget stop), which bound the real model cost, not the queue. [`reports/faucet-spam-v1.md`](../../reports/faucet-spam-v1.md) simulated a flat fee ($5.03 a submission, and $20–40 in faucet USDC), not the taxi fare: the queue under the taxi fare is not simulated. **Since 2026-11-20 (owner, #251) the fee coin is the project's own test coin with a keyless faucet (launch design L17):** 20 coins a claim, one claim per address every 2 hours, no reCAPTCHA, so a bot farms free addresses at the cost of their gas; the report's per-address arithmetic applies without the human-in-the-loop cost, and this trust point's bound (capacity and the nodes' spending caps) is unchanged.
7. **R without F on the testnet.** Report v5's attackers stay at or below their twins only with the cap *and* the fee (R+F); with the taxi fare the testnet runs the cap with metered checks refunded, which v5's "R" rows (the cap alone) found closes nothing with 1–3 active honest solvers. The testnet tests the flow, not the incentives (open problems 7.6).

### What stays from ADR 0004
- **Everything not named above stands as ADR 0004 has it:** the k table, the bond tiers, `BOND_FACTOR`, `BOND_FLOOR` ($100), `CHALLENGE_WINDOW[k, level]` and the other windows, `CHALLENGE_K`, the k = 1 hold and `K1_PENDING_MAX`, admission and shadows, the caps (the family cap now conditional on `CAP_MIN_FAMILIES`), the slashes, the audits, the constitution tier, the pricing rules and the scores, and the acceptance thresholds.
- **The launch's own values stand beside them:** the production windows on Sepolia (L4, which are ADR 0004's), and a validator bond of **$250** set at deploy on Sepolia, so a single judge's bounty limit is $125 (L17).
- **Not re-derived here.** #132 task 10.2 asked for the bonds and windows to be re-derived from the measured bad fixes per 100 paid (ADR 0004 sized them on 1.1; report v3 measures 4.5 to 8.5 with seats by rank and disputes). This ADR does not do it. They stay as ADR 0004 and L17 set them until a re-derivation, which is an open item (#132 task 10.7).

### Left open
- **The re-derivation of bonds and windows** (above).
- **The paid runs** of #132 tasks 10.3 and 11.3 (trust point 3).
- **The confirmation of R(minus 2×)+F on fresh seeds** (#132 task 12.3) and **what 12.1 left out** (#132 task 12.4: rivals' wrong tests, the appeal beside D29 and D30). The rule "a deposit only while fewer than three solvers are active" in 12.4 is no longer needed: the owner ruled it out.
- **Two switches report v3 added for this ADR,** not decided here: `IDLE_COUNTS` (report v3 recommends counting seated validators only in D9's idle signal) and `CONTENDER_SHADOWS` (leave at the panel's own until rejections have known answers).
- **Counting upheld disputes only for the repository's own solvers** is not simulated (report active-solvers-v1, section 5).

## Evidence
- **Simulation runs:** `python3 -m pof.sim.openval.sizing --seeds 40 --jobs 15` (report v3); `python3 -m pof.sim.openval.evidence --seeds 40 --jobs 15` (report v4); `python3 -m pof.sim.openval.nodeposit --seeds 40 --jobs 15 --out DIR` (report v5); `python3 -m pof.sim.openval.activesolvers --seed0 41 --seeds 40 --jobs 15 --out DIR` (report active-solvers-v1, pre-registered, seeds 41–80). Reports v3–v5 are exploratory on seeds 1–40.
- **Tests:** `tests/test_openval_seats.py`, `tests/test_openval_evidence.py`, `tests/test_openval_nodeposit.py` (including `TestPledgeGate`), each switch with a test, every switch off reproducing the earlier reports.
- **Invariants (Article 5):** v3 is a new version (D15); v2 is unchanged. No value here adds a key, an owner or a vote over a price.
- **Not yet measured:** gas and contract sizes for these rules (#132 tasks 10.4, 11.4 and 12.5; `reports/contract-v3.md`).

## Consequences
- **Solvers** post FeesV3's worst-case deposit per submission on Sepolia and get back what their panels' meters didn't use (the taxi fare; a flat judges' fee is left to a mainnet decision); no attempt, evaluation or appeal fee, and no deposit lost on rejection. A new identity may hold $50 of open claims, and more as its fixes are paid and stand. A reversed pass costs it twice its bounty in reputation. A rejected fix may be appealed once, within 72 h, with a test and no stake, paying the appeal panel's meter.
- **Disputers** post a test and the larger of $5 and 10 % of the bounty, and are paid 10 % of the bounty when the test is upheld. Nothing else pays them.
- **Funders** can't pledge until the repository has 3 active solvers within 26 weeks; issues can still be registered and fixed unfunded meanwhile.
- **Validators:** the best-scoring families within 5 points of the top are seated; the family cap applies only from 3 seated families; among fewer, a challenge that can't draw a larger fresh panel gets a second draw.
- **What becomes harder:** a solver of bad fixes faces the cap, the fee and tests from rivals; an appeal without new evidence is refused.
- **What stays the same:** v2 and its bounties; the keyless contracts; no protocol fee, no token.
- **Next:** #132 task 10.4 (seats by rank, the test dispute; no deposit), the accepted parts of 11.4 (the appeal and the second draw), and 12.5 (the reputation cap and the judges' fee), then the launch's tasks 3.3 and 3.6.

## Challenge window
None yet: no constitution tier exists to pass it. The owner accepts it by merging. Its values go into v3's constitution at deployment and are fixed per version (D15).
