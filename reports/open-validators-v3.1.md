# Open validators, v3.1: round 3's criteria and the silence-slash sweep (proof-of-fix#141; 2026-11-03)

> **An addendum to [report v3](open-validators-v3.md).** Task group 8 of #132 (`openspec/changes/proof-of-fix-132-open-validators/tasks.md`), after round 3 of the spec (branch `proof-of-fix-141-round3`). The owner approved report v3's recommendations on 2026-11-03. Round 3 changes no protocol rule: it changes how three criteria are read (D17), and adds a switch for the parameters ADR (#137) to size (D16). Report v3 is kept as it is; this addendum adds the tables round 3 needs.

**Command:** `python3 -m pof.sim market validators --round3 --seeds 40 --jobs 4` prints every table below, in 2 min 41 s on four processes (Python 3.13, `nice -n 19`). One process gives the same output (checked on `--quick`). Every number is a mean over seeds 1–40; every ± is **two** standard errors of that mean.

**What was re-run, and what wasn't.** Round 3's parameters (`params.V2R3`, the defaults now) differ from round 2's (`params.V2R2`) only in the three criteria fields (`GAIN_TEST`, `LONE_CATCH_COUNT`, `WAIT_CROWD_MAX`), which no simulated actor reads. So the simulation gives report v3's numbers run for run (tested on a fixed seed), and **v3's acceptance table is re-judged from v3's published numbers, without re-running v3.** Only the new sweeps ran: the silence slash in proportion to the bounty, and the deposit's honest cost. Their x = 0 rows reproduce v3's numbers to the cent.

## Summary

**Under round 3's criteria, report v3's numbers meet 13 of 13 criteria** (v3, under round 2's: 9 of 13). No rule changed, and no number moved. Four verdicts change, each by the owner's decision of 2026-11-03:

| Criterion | v3 (round 2's criteria) | v3.1 (round 3's criteria) | What decides it |
|---|---|---|---|
| Each pricing attacker | not met: the inflaters' mean is above zero | met: not shown to gain | the inflaters, +$2.7 ± 3.9: lower bound −$1.2, upper bound +$6.6 (decision 1) |
| Each scoring attacker (the herders) | not met: the same, the weak herders | met | the weak herders, +$0.2 ± 0.7: −$0.5 to +$0.9 (decision 1) |
| The colluding lone validator is caught | not met: 93.3 % ± 3.9 of every bad fix of its accomplice (lower bound 89.4 %) | met: 98.4 % ± 1.8 of its own verdicts (184 of 187) | `LONE_CATCH_COUNT` "own" (decision 2); it still loses −$247 ± 41 |
| Everyone crowds into one model | not met: 11.3 % ± 4.9 waited, upper bound 16.2 % over 15 % | met: under 20 % | `WAIT_CROWD_MAX` 20 % (decision 3) |

The other nine verdicts stand as v3 gave them. Every attacker that "loses" by #141's criterion still loses (14 of 14 open-validator attackers, 4 of 6 pricing, 7 of 7 proof-level, 7 of 8 herders). Every row v3 flagged outside the counted attackers still fails "not shown to gain", by its lower bound (the 10 % silence bribe +$311 ± 21; plain-agreement herders on the market +$97 ± 31) or its upper bound (the coalition of 5 from 14, −$58 ± 259).

**The trust points that remain**, for the ADR:
- **The accomplice's other fixes:** 22 of the accomplice's bad fixes that reached an outcome were judged by others (over the 40 runs), and 11 of them were paid; the colluder can sit on their challenge panels. It still loses (−$247 ± 41).
- **One TEE type's majority** in 77 % ± 8 of panels of 3 while three types are accepted (report v3).
- **Answer shopping at 3 in 10** once level C is on: +$174 ± 46 (report v3).
- **A silence bribe above the slash** (below).

### The silence slash in proportion to the bounty (decision 4)

The slash for silence, and for a sealed vote not revealed, is max($5, x % of the bounty the judge was drawn for). A judge bribed on 10 % of its draws, on a grown network of 12 honest validators (return − twin's, $ a year):

| Slash | Silent, bribed 5 % | Silent, bribed 10 % | Withholder, bribed 10 % | Honest validator's slashes a month | Honest validator's net a month | Market runs collapsed |
|---|---|---|---|---|---|---|
| a flat $5 (x = 0, round 2) | −14 ± 9 | +311 ± 21 | +310 ± 21 | $0.98 ± 0.05 | $−1.43 ± 0.22 | 0 of 40 |
| x = 1 % | −15 ± 9 | +311 ± 21 | +310 ± 21 | $0.98 ± 0.05 | $−1.43 ± 0.22 | 0 of 40 |
| x = 2 % | −18 ± 8 | +307 ± 20 | +306 ± 20 | $0.97 ± 0.05 | $−1.43 ± 0.22 | 0 of 40 |
| x = 5 % | −97 ± 5 | +229 ± 14 | +228 ± 14 | $1.14 ± 0.08 | $−1.50 ± 0.26 | 0 of 40 |
| x = 10 % (beyond the spec's range, for reference) | −372 ± 16 | −47 ± 5 | −48 ± 5 | $1.79 ± 0.15 | $−2.48 ± 0.89 | 3 of 40 |

The honest columns are every outage before the seal, at 1 outage in 200 draws; after the seal they are the same within a cent or two (the full table below).

- **In the spec's range, no x makes the 10 % bribe lose.** 1 % and 2 % change almost nothing: 1 % of a bounty is above $5 only above $500. The best, 5 %, cuts the bribed judge's gain by about a quarter (+$229 ± 14 from +$311 ± 21), at $0.16 a month more of honest slashes; the honest net moves within its noise (−$1.50 ± 0.26 against −$1.43 ± 0.22).
- **Only x at the bribe's own share (10 %) makes it lose** (−$47 ± 5), and that breaks the market: honest slashes nearly double ($1.79 ± 0.15 a month), the honest net falls to −$2.48 ± 0.89, and **3 of 40 markets collapse**, so `FEE_MARGIN`'s criterion ("no run collapses") would fail. It repeats v2's problem with a slash that grows with what a validator judges (D16, "Why flat amounts"): validators bonded for large bounties expect large slashes and leave.
- **A briber can always pay more than x %.** A slash in proportion to the bounty sets the price of silence; it can't stop a larger bribe.
- **What silence buys is small:** k never shrinks, the next validator in the sample replaces the judge (3 hours of delay), and the reveal-rate floor suspends it (8.4 times a year here).

**Recommendation for ADR 0004: keep the flat $5 (x = 0) for both slashes, and name the trust point:** a bribe above $5 a silence pays the judge, and buys only a replacement's delay. Drop the two switches (`SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS`). x = 5 % is the alternative if the owner wants silence to cost more; it meets no criterion that $5 misses.

### The deposit's honest cost

An honest author submitting a good adding ADR a week, with the deposit, to the genesis and 24 honest validators: **2.9 % ± 0.8 of its ADRs are rejected** (60 of 2,037 decided), so at $15 it forfeits **$0.42 an ADR** ($22.50 a year at one ADR a week). D7 estimated 2.6 % and $0.39. At $25 it would be $0.71 an ADR. No ADR expired: 21 or more validators were always eligible.

## What changes for the ADR (#137)
1. **Round 3's criteria:** every criterion of D17 is met on report v3's numbers. The design's values can be proposed as they stand.
2. **The silence and withholding slash:** keep $5 flat; name the bribe above $5 as a trust point (above).
3. **The deposit:** $15 costs an honest author about $0.42 an ADR; it stays the value D7 sized.
4. **Name four trust points:** the accomplice's other fixes; one TEE type's majority until five types are accepted; answer shopping once level C is on; a silence bribe above $5.
5. **Drop, besides report v3's list:** `SILENCE_SLASH_BPS` and `SEALED_NO_REVEAL_SLASH_BPS` (if the owner keeps $5 flat). Keep `GAIN_TEST` and `LONE_CATCH_COUNT` reachable in the simulation only, as round 2's criteria.
6. **Not decided here:** whether a challenge panel should exclude the validators that judged the same solver's other pending fixes (round 3's finding 3; not simulated).

## The full run

Every table of the 40-seed run, as printed (headings one level down). The re-judged tables use report v3's numbers as printed there; the sweeps ran here.

### Report v3 re-judged

#### Acceptance criteria for open validators: report v3's numbers under round 2's and round 3's criteria (40 seeds; ± 2 standard errors)

| Criterion (round 3's words) | v3 (round 2's criteria) | v3.1 (round 3's criteria) | Threshold (round 3) | What decides it (round 3) | Loses (#141's criterion) |
|---|---|---|---|---|---|
| Each open-validator attacker isn't shown to gain against its honest twin | met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 | none of 14 is shown to gain; the closest: Silent (never seals): `SILENCE_SLASH` $5 (-14 ± 9 $) | 14 of 14 lose |
| Each pricing attacker isn't shown to gain against its honest twin | not met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 | none of 6 is shown to gain; the closest: Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) (+2.7 ± 3.9 $) | 4 of 6 lose |
| Each proof-level attacker isn't shown to gain against its honest twin (answer shopping at 1 in 10; the level C rows after C is switched on by ADR) | met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 | none of 7 is shown to gain; the closest: Answer shopper, after C is switched on by ADR: 1 of 15 at C, 1 in 10 (-13 ± 1 $) | 7 of 7 lose |
| Each scoring attacker (the herders) isn't shown to gain against its honest twin | not met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 | none of 8 is shown to gain; the closest: Herders: `weak` (68 %), not detectable (upper bound) (+0.2 ± 0.7 $) | 7 of 8 lose |
| A sybil at or under `SYBIL_SHARE` (12.5 %) never holds a majority of a panel of k ≥ 3, in any run | met | **met** | 0 runs | 3 validators (12.5 %), spread and on one host: a majority on 0.00 % of panels (v3) | – |
| A sybil above the share: the report gives how often it holds a majority, what it passes, and how often it's caught | met | **met** | reported | reported in v3 (22 %, 32 % and 49 %) | – |
| The colluding lone validator isn't shown to gain, and at least `LONE_CATCH_SHARE` (90 %) of the bad fixes it passes itself, as the lone judge, are reversed before any payment (pooled), with two audits | not met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10; share − 2 SE ≥ 90 % | return − twin's -247 ± 41 $ (isn't shown to gain: yes); its own verdicts reversed before payment 98.4 % ± 1.8 % (184 of 187); every bad fix of its accomplice, whoever judged it, 93.3 % ± 3.9 % (195 of 209); counted: its own (round 3), the rest the named trust point | loses |
| The constitution waits for the network: no adding ADR or escalated fix passes while fewer than 21 validators are eligible, and no removal while fewer than 14, in any run | met | **met** | 0 runs | adding ADRs and escalated fixes passed below 21, all runs: 0; removals passed below 14: 0 (v3) | – |
| The fee settles within `FEE_MARGIN` (25 %) above break-even and at least break-even less one step, and no run collapses | met | **met** | 0.95 ≤ ratio ± 2 SE ≤ 1.25; 0 runs collapse | fee / break-even over the last 13 weeks 1.20 ± 0.04 ×; 0 of 40 runs collapsed (v3) | – |
| Everyone crowds into one model: at most `WAIT_CROWD_MAX` (20 %) of submissions wait | not met | **met** | mean + 2 SE ≤ 20 % | 11.3 ± 4.9 % waited (upper bound 16.2 %) | – |
| The network still grows: a small bounty reaches k ≥ 3 within the year in every run | met | **met** | every run | 40 of 40 runs, at week 6 ± 1 (v3) | – |
| Answer shopping, the trust point: it isn't shown to gain at 1 in 10; at 3 in 10 the report gives its gain | met | **met** | mean − 2 SE ≤ 0 and mean + 2 SE ≤ $10 at 1 in 10 | at 1 in 10: -13 ± 1 $; at 3 in 10 (reported): +174 ± 46 $; at #125's measured room (reported): -16 ± 1 $ | loses |
| Every earlier criterion holds or is named | met | **met** | named | named, not re-run (D15, gap 20), as in v3 | – |
| Adopt the k table, windows, bonds, caps and pricing bounds (all of the above) | not met | **met** | all | every criterion met | – |

Met: 9 of 13 under round 2's criteria (v3), 13 of 13 under round 3's. The numbers are report v3's, as printed there; round 3's rules and seeds are round 2's, so nothing is re-run.

#### The counted attackers under both criteria (report v3's numbers)

| Attacker | Return − twin's ($, ± 2 SE) | Lower / upper bound | Doesn't gain (round 2) | Not shown to gain (round 3) | Loses |
|---|---|---|---|---|---|
| Sybil: 10 of 30 validators, spread over 3 hosts, TEE types and families | -21,535 ± 2,510 | -24,045.0 / -19,025.0 | yes | yes | loses |
| Sybil: 10 of 30 validators, one host, TEE type and family | -17,969 ± 1,752 | -19,721.0 / -16,217.0 | yes | yes | loses |
| Seed grinder (v3's seed: a later block) | -272 ± 48 | -320.0 / -224.0 | yes | yes | loses |
| Fee farmer (10 idle nodes at the bond floor; twin: one node) | -545 ± 3 | -548.0 / -542.0 | yes | yes | loses |
| Colluding genesis (two audits of every k = 1 verdict, 5 bad fixes a week) | -247 ± 41 | -288.0 / -206.0 | yes | yes | loses |
| Silent (never seals): `SILENCE_SLASH` $5 | -14 ± 9 | -23.0 / -5.0 | yes | yes | loses |
| Seals, then withholds: `SEALED_NO_REVEAL_SLASH` $5 | -15 ± 9 | -24.0 / -6.0 | yes | yes | loses |
| Constitution coalition: 5 early validators, 21 for adding ADRs, a $15 deposit | -280 ± 147 | -427.0 / -133.0 | yes | yes | loses |
| Constitution coalition: 3 early validators, 21 for adding ADRs, a $15 deposit | -431 ± 145 | -576.0 / -286.0 | yes | yes | loses |
| Constitution coalition: 5 early, escalated fixes to issues they fund, 21, a $15 deposit | -280 ± 147 | -427.0 / -133.0 | yes | yes | loses |
| Coalition of removals: 5 early, from 14 with a $15 deposit, three types even | -456 ± 103 | -559.0 / -353.0 | yes | yes | loses |
| Coalition of removals: the same, three types skewed | -505 ± 97 | -602.0 / -408.0 | yes | yes | loses |
| D13's lazy cheater (audits at 10 %, no volunteers) | -3,839 ± 587 | -4,426.1 / -3,251.3 | yes | yes | loses |
| D13's bribed cheater (audits at 10 %, no volunteers) | -859 ± 320 | -1,178.6 / -539.0 | yes | yes | loses |
| Cartel: 6 validators refusing half their draws (design) | -1,976 ± 53 | -2,029.0 / -1,923.0 | yes | yes | loses |
| Spammer: a fix a day to a $625 bounty no panel can judge yet (design) | -502 ± 71 | -573.0 / -431.0 | yes | yes | loses |
| Spammer: a bad fix a day, judged (design) | -915 ± 28 | -943.0 / -887.0 | yes | yes | loses |
| Inflaters: 3 Anthropic validators of 24 posting 100 × their costs (design) | +2.7 ± 3.9 | -1.2 / +6.6 | **no: it gains** | yes | not significant |
| Inflaters on a small network (the genesis, 4 honest, the 3 inflaters) (design) | -0.1 ± 2.3 | -2.4 / +2.2 | yes | yes | not significant |
| Fee farmer: 10 idle validators at the bond floor (twin: one) (design) | -402 ± 21 | -423.0 / -381.0 | yes | yes | loses |
| Test liar, after C is switched on by ADR: 1 of 15, 2 bad fixes a week | -4,809 ± 505 | -5,314.0 / -4,304.0 | yes | yes | loses |
| Answer shopper, after C is switched on by ADR: 1 of 15 at C, 1 in 10 | -13 ± 1 | -14.0 / -12.0 | yes | yes | loses |
| Chip breaker at launch: the genesis at B, $1,000 device | -1,500 ± 57 | -1,557.0 / -1,443.0 | yes | yes | loses |
| Chip breaker at launch: the genesis at B, $50 device | -550 ± 57 | -607.0 / -493.0 | yes | yes | loses |
| Chip breaker at launch: 1 of a grown network, $50 device | -14,166 ± 1,492 | -15,658.0 / -12,674.0 | yes | yes | loses |
| Chip breaker at launch: the same, forging on every bad-fix draw | -22,003 ± 2,142 | -24,145.0 / -19,861.0 | yes | yes | loses |
| Chip breaker, after C is switched on by ADR: 1 of 15, $50 device | -19,830 ± 1,644 | -21,474.0 / -18,186.0 | yes | yes | loses |
| Herders: `mid` (90 %), receipts detectable | -3,011 ± 1,202 | -4,213.0 / -1,809.0 | yes | yes | loses |
| Herders: `mid` (90 %), not detectable (upper bound) | -23 ± 4 | -27.0 / -19.0 | yes | yes | loses |
| Herders: `weak` (68 %), receipts detectable | -1,957 ± 547 | -2,504.0 / -1,410.0 | yes | yes | loses |
| Herders: `weak` (68 %), not detectable (upper bound) | +0.2 ± 0.7 | -0.5 / +0.9 | **no: it gains** | yes | not significant |
| Herders: `mid`, not detectable, at a $0.25 fee | -347 ± 31 | -378.0 / -316.0 | yes | yes | loses |
| Herders: `weak`, not detectable, at a $0.25 fee | -5.3 ± 3.3 | -8.6 / -2.0 | yes | yes | loses |
| Herders on the market: `mid` (90 %), not detectable | -340 ± 33 | -373.0 / -307.0 | yes | yes | loses |
| Herders on the market: `weak` (68 %), not detectable | -4.7 ± 2.4 | -7.1 / -2.3 | yes | yes | loses |

### The silence-slash sweep

#### A bribed silent judge and a bribed withholder, by the slash (40 seeds; a year; a grown network of 12 honest validators; bribed on 10 % of its draws; return − twin's in $, ± 2 SE, and whether it is not shown to gain)

| Slash for silence and for a sealed vote not revealed | Silent, bribed 5 % of the bounty | Silent, bribed 10 % of the bounty | Seals, then withholds, bribed 5 % | Seals, then withholds, bribed 10 % | Slashed per bribed miss: silent 5 % / 10 % | Bribe a miss: 5 % / 10 % | Suspended a year (silent 5 %) |
|---|---|---|---|---|---|---|---|
| a flat $5 (round 2; x = 0) | -14 ± 9 (yes) | +311 ± 21 (**no: it gains**) | -15 ± 9 (yes) | +310 ± 21 (**no: it gains**) | $5.23 / $5.23 | $5.09 / $10.18 | 8.4 |
| max($5, 1 % of the bounty) | -15 ± 9 (yes) | +311 ± 21 (**no: it gains**) | -15 ± 9 (yes) | +310 ± 21 (**no: it gains**) | $5.23 / $5.23 | $5.09 / $10.18 | 8.4 |
| max($5, 2 % of the bounty) | -18 ± 8 (yes) | +307 ± 20 (**no: it gains**) | -19 ± 8 (yes) | +306 ± 20 (**no: it gains**) | $5.28 / $5.28 | $5.09 / $10.18 | 8.4 |
| max($5, 5 % of the bounty) | -97 ± 5 (yes) | +229 ± 14 (**no: it gains**) | -97 ± 5 (yes) | +228 ± 14 (**no: it gains**) | $6.51 / $6.51 | $5.09 / $10.18 | 8.4 |
| max($5, 10 % of the bounty) (beyond the spec's range) | -372 ± 16 (yes) | -47 ± 5 (yes) | -373 ± 16 (yes) | -48 ± 5 (yes) | $10.87 / $10.87 | $5.09 / $10.18 | 8.4 |

A bribed miss is a draw on which it was bribed and stayed silent (or withheld its sealed vote). Slashed per bribed miss: everything it was slashed in the year over its bribed misses, so its own honest outages (1 in 200 draws) add a little. Its twin is the same validator never bribed. x = 0 is round 2's design (report v3: silent −14 ± 9 and +311 ± 21, withholder −15 ± 9 and +310 ± 21).

#### An honest validator's month on the market, by the slash (40 seeds; 1 outage in 200 draws; honest validators active a month or more; $ a month; the fee over the last 13 weeks)

| Outages | Slash | Slashes | Service fees | Net | Fee | Fee / break-even | Runs collapsed |
|---|---|---|---|---|---|---|---|
| every outage before the seal (silence) | a flat $5 (round 2; x = 0) | $0.98 ± 0.05 | $7.72 ± 0.16 | $-1.43 ± 0.22 | $0.212 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage before the seal (silence) | max($5, 1 % of the bounty) | $0.98 ± 0.05 | $7.72 ± 0.16 | $-1.43 ± 0.22 | $0.212 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage before the seal (silence) | max($5, 2 % of the bounty) | $0.97 ± 0.05 | $7.71 ± 0.17 | $-1.43 ± 0.22 | $0.212 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage before the seal (silence) | max($5, 5 % of the bounty) | $1.14 ± 0.08 | $7.91 ± 0.15 | $-1.50 ± 0.26 | $0.213 ± 0.005 | 1.22 ± 0.03 × | 0 of 40 |
| every outage before the seal (silence) | max($5, 10 % of the bounty) (beyond the spec's range) | $1.79 ± 0.15 | $8.17 ± 0.33 | $-2.48 ± 0.89 | $0.224 ± 0.005 | 1.19 ± 0.03 × | 3 of 40 |
| every outage after the seal (withheld) | a flat $5 (round 2; x = 0) | $0.98 ± 0.05 | $7.71 ± 0.17 | $-1.45 ± 0.22 | $0.211 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage after the seal (withheld) | max($5, 1 % of the bounty) | $0.98 ± 0.05 | $7.71 ± 0.17 | $-1.45 ± 0.22 | $0.211 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage after the seal (withheld) | max($5, 2 % of the bounty) | $0.98 ± 0.05 | $7.70 ± 0.17 | $-1.45 ± 0.22 | $0.211 ± 0.006 | 1.20 ± 0.04 × | 0 of 40 |
| every outage after the seal (withheld) | max($5, 5 % of the bounty) | $1.14 ± 0.08 | $7.92 ± 0.15 | $-1.50 ± 0.26 | $0.213 ± 0.005 | 1.21 ± 0.03 × | 0 of 40 |
| every outage after the seal (withheld) | max($5, 10 % of the bounty) (beyond the spec's range) | $1.79 ± 0.15 | $8.16 ± 0.33 | $-2.48 ± 0.89 | $0.224 ± 0.005 | 1.19 ± 0.03 × | 3 of 40 |

x = 0 is round 2's design (report v3: slashes $0.98 ± 0.05 a month and a net of $-1.43 ± 0.22 before the seal; $0.98 ± 0.05 and $-1.45 ± 0.22 after it). The market's validators expect the slash at their own draws' bounties when they decide to enter or stay (`pricing.outage_slash`).

### The deposit's honest cost

#### The deposit's honest cost (40 seeds; a year; an honest author submitting a good adding ADR a week, with the deposit, to the genesis and 24 honest validators, a newcomer a week; its twin: the same ADRs with no deposit)

| Deposit | ADRs submitted / expired / judged / passed / rejected (a run) | Rejected of those decided, pooled (± 2 SE) | Forfeited a run | Forfeited per ADR submitted | Return − twin's ($ a year, ± 2 SE; deposits still held at the year's end counted as returned) |
|---|---|---|---|---|---|
| $15 | 53.1 / 0.0 / 53.1 / 49.4 / 1.50 | 2.9 % ± 0.8 % (60 of 2037 decided) | $22.50 | $0.423 | -22 ± 6 |
| $25 | 53.1 / 0.0 / 53.1 / 49.4 / 1.50 | 2.9 % ± 0.8 % (60 of 2037 decided) | $37.50 | $0.706 | -37 ± 10 |

D7's hand estimate: a good ADR is rejected when 3 or more of its 7 honest judges err, about 2.6 % of the time at 90 % accuracy, so about $0.39 an ADR at $15.

## Commands, seeds and tests
- **This addendum:** `python3 -m pof.sim market validators --round3 --seeds 40 --jobs 4` (seeds 1–40). `--jobs 4` forks four processes, one section each (the honest month before and after the seal, the silent judge, the withholder, the honest author); the output is the same on one process (checked on `--quick`).
- **Report v3, unchanged:** `python3 -m pof.sim market validators --seeds 40 --jobs 4` still prints report v3 under round 2's criteria (`params.V2R2`). `--v2r1` and `--v1` print reports v2 and v1, unchanged.
- **Where round 3 lives:** `pof/sim/openval/params.py` (`V2R3`, the defaults: `GAIN_TEST`, `LONE_CATCH_COUNT`, `WAIT_CROWD_MAX`, `SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS`, `Params.miss_slash`); `round2.acceptance` judges a full run under either set (`gain_ok`, `lone_share`); `pof/sim/openval/round3.py` re-judges v3's numbers (`rejudge`), runs the sweep and the honest author; `net.py` slashes by `miss_slash`; `pricing.py` lets the market's validators expect the slash at their own draws' bounties.
- **Tests:** `tests/test_openval_r3.py` (20 tests): "not shown to gain" (+$2.7 ± 3.9, +$0.2 ± 0.7 and −$1 ± 7 pass; +$3 ± 2 and −$34 ± 47 fail; round 2's switch fails the first two); round 3 changes only the three criteria fields, and the simulation is the same under both sets; report v3's numbers appear in report v3, and re-judged under round 2's criteria give v3's own verdicts; each round-3 switch alone restores its failure; `round2.acceptance` under round 3's words; the slash follows the bounty, each sweep point changes only what it names, and x = 0 reproduces round 2 on a fixed seed; the honest author forfeits only on rejection; the command; this report names each criterion as met or not. The open-validator tests (264) take 69 seconds, 12 more than v3's 244 (round 3's tests share round 2's quick run); the whole suite (978) took 167 seconds under Python 3.13 and 216 under 3.9.25.
- **Not run here:** the CI's Amazon Linux container (Docker is off on this machine). The whole suite ran under Python 3.9.25 instead, and under 3.13. Forgejo CI is the gate.
