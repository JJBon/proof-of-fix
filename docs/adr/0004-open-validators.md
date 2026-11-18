# ADR 0004: The parameters of v3's open validators

- **Status:** Accepted: merged by the owner (#137); group 3 of #132 started on 2026-11-13.
- **Date:** 2026-11-03
- **Author:** drafted for the owner (proof-of-fix#137, task 2.1 of `openspec/changes/proof-of-fix-132-open-validators`), from the simulation of #134 and #141's three rounds. Interest disclosed: the owner may run one validator, disclosed and under the same rules as any other (ADR 0003); no founder's share and no token (#142 is separate).
- **Constitution articles changed:** none of v2's. v3 is a new version (design D15) with its own constitution, written when it is deployed (#138); these values are fixed in it per version (the design's Parameters). v2's constitution and contracts are unchanged.
- **Protected paths touched:** `docs/adr/0004-open-validators.md`

## Problem
v3 (#132) replaces v2's seven fixed seats with an open registry: anyone may register a validator with a bond and an attestation, qualify by judging as a shadow, and be drawn. Panels are an odd k from 1 to 7 that follows the network and the bounty, and prices follow a market instead of a vote. The design left every number as a starting value, for the simulation to set and the owner to confirm in an ADR (design, Open Questions; task 2.1). Contract work (#138) starts only once this ADR is merged (tasks, "Workflow follow-up").

The simulation took four runs to get there:

| Run | Rules | Criteria met | What it showed |
|---|---|---|---|
| [report v1](../../reports/open-validators-v1.md) (#134) | the first design | 4 of 10 | the lone colluder, the seed grinder and the constitution coalition gained; the fee never left its ceiling |
| [report v2](../../reports/open-validators-v2.md) (#147) | #141's round 1 | 8 of 13 | the market collapsed in 33 of 40 runs; bribed silence and an early coalition still paid |
| [report v3](../../reports/open-validators-v3.md) (#153) | #141's round 2 | 9 of 13 | no attack shown to pay; four criteria failed on how they were read |
| [report v3.1](../../reports/open-validators-v3.1.md) (#141, round 3) | round 2's rules, round 3's criteria | **13 of 13** | v3's numbers re-judged; the silence-slash sweep; the deposit's honest cost |

Every simulated number below is a mean over seeds 1–40, ± two standard errors, from those reports (v1, v2, v3 and v3.1 name which).

## Options
1. **Keep the design's starting values without an ADR.** Nothing to decide, but #138 would build on values nobody accepted, and the trust points would stay unnamed.
2. **Adopt round 3's values (the design after #141's three rounds), with their trust points named.** Every acceptance criterion of D17 is met on report v3's numbers (v3.1). Five trust points remain, each bounded and measured.
3. **Run another round first,** for example to measure the challenge-panel exclusion (round 3's finding 3) or to tighten a threshold. It would delay #138 for evidence that changes no criterion: every criterion is met, and the colluder already loses (−$247 ± 41).

## Decision
Option 2. The parameters below are v3's, with their values and the evidence for each.

### The k table, bonds and windows
| Parameter | Value | Evidence |
|---|---|---|
| `K_MAX` | 7 | v2's constitution tier; the k table against a fixed k of 3 (v3): bad fixes merged per 100 paid 0.21 ± 0.06 against 0.65 ± 0.09 on a growing network, 0.07 ± 0.03 against 0.68 ± 0.09 on a grown one, for $1.78 a paid fix against $1.04 |
| Largest bounty per (k, level) | level A: k=1 $50 · k=3 $250 · k=5 $625 · k=7 $625. Level B: half of A's. Level C: k=1 $10 · k=3 $50 · k=5 $125 · k=7 $250 | growth from one validator reaches k ≥ 3 by week 6 in 40 of 40 runs (v3); the chip breaker at B loses (−$1,500 ± 57 with a $1,000 device, −$550 ± 57 with a $50 one) |
| Bond tiers | every limit above, at any level: $10, $25, $50, $125, $250, $312.50, $625 | exact counters for k (design, gap 2) |
| `BOND_FACTOR` | 2 (bond ≥ 2 × the bounty's tier) | v2's rule; the spread sybil of 10 of 30 loses −$21,535 ± 2,510 (v3) |
| `BOND_FLOOR` | $100 | covers k = 1's largest bounty; the fee farmer's 10 idle nodes lose −$545 ± 3 (v3) |
| `CHALLENGE_WINDOW[k, level]` | level A: k=1 168 h · k=3 24 h · k=5 12 h · k=7 6 h. Level B: twice A's. Level C: k=1 336 h · k=3 72 h · k=5 48 h · k=7 24 h | the colluding genesis loses at 7 days (−$247 ± 41); 14 and 30 days add little (−$264 ± 42, −$251 ± 40) and delay every honest k = 1 payment (a median 25.3 and 40.6 days, against 19.4) (v3) |
| `CHALLENGE_K[k]` | k=1→3 · k=3→5 · k=5→7 · k=7→7, fresh validators; fewer only if still larger than k, else the challenge waits | design D4 |
| The k = 1 hold | a k = 1 verdict isn't final until `CHALLENGE_K[1]` validators could judge its challenge | without it the colluder gained +$2,920 ± 456 (v1); with it an honest k = 1 fix is paid a median 19.4 ± 3.6 days after its verdict (p90 48.5), on 2 % of panels (v3), accepted by the owner |
| `K1_PENDING_MAX` | 10 | at 5 the colluder's catch share falls (88.7 % ± 6.7 of every accomplice fix); at 20 honest k = 1 pay waits 23.2 days (v3) |
| `SEED_DELAY` | 5 blocks | the grinder loses with v3's seed (−$272 ± 48, v3); with the seed fixed at the seal it gained five times as much in #134 (design D3) |
| `SEAL_WINDOW`, `REVEAL_WINDOW` | 2 h and 1 h | as #85 |
| `DRAW_TRIES` | 8 per seat, a constant | a gas bound: 8 and 1,000 gave the same draws (36.6 % against 36.5 % lowered, v1) |
| `GENESIS_MAX` | 1, at level A or B | a level C genesis can't grow a network (96 % withdrawn, v1) |

### Admission, shadows and caps
| Parameter | Value | Evidence |
|---|---|---|
| `QUALIFY_VERDICTS`, `QUALIFY_REVEAL`, `QUALIFY_AGREE` | 20 scored shadow verdicts; 95 % revealed; 80 % agreement | 51.0 ± 2.1 of 53.8 newcomers qualify in the year, in 14.7 ± 1.4 days; 3.6 ± 0.6 failed attempts (v3) |
| `QUALIFY_COOLDOWN` | 7 days | design, gap 22 |
| `ACTIVE_REVEAL_MIN` | 90 % over the last 50 draws (before 50: more than 5 misses) | it suspends the bribed silent judge 8.4 times a year, and the cartel 42 times (v3) |
| `UNBONDING_DELAY` | the longest window + 7 days = 504 h, and not before every verdict is final and every challenge naming it is closed | design, gap 11 |
| `SHADOW_PER_DRAW` | 1 (2 while fewer than 7 are active) | design D5 |
| `SHADOW_PER_WAITING` | 3 a waiting submission | required: at 0 no run reaches k ≥ 3 (0 of 40, v3); the sponsors' pool pays $197 a year for shadows |
| Caps per panel | 1 per operator; at most (k − 1) / 2 per host and per model family from k = 3 | when every validator chases the top family, no panel holds more of one family than the cap allows (v3) |
| `TEE_CAP_FROM_K`, `TEE_CAP_K3_TYPES` | the TEE-type cap from k = 5 while fewer than 5 TEE types are accepted, from k = 3 with 5 or more | three types from k = 3 make 27 % ± 4 of submissions wait, against 21 % ± 3 from k = 5; five types from k = 3 leave no one-type majority (v3). The cost is a named trust point (below) |

### Slashes
| Parameter | Value | Evidence |
|---|---|---|
| `FALSE_VERDICT_SLASH_BPS` | 10,000: the whole bond | the grinder, the sybils and the colluder all lose (v3). At 2,000 they lose too now (grinder −$90 ± 14, colluder −$85 ± 10), but #134's grinder gained at 2,000 (+$258 ± 79, v1), and `BOND_FACTOR` assumes the whole bond |
| `EQUIVOCATION_SLASH_BPS` | 10,000 | as v2 |
| `SEALED_NO_REVEAL_SLASH`, `SILENCE_SLASH` | **$5 flat each,** the same for every bond, for a counted judge; shadows are never slashed | a judge bribed 5 % of the bounty loses (silent −$14 ± 9, withholder −$15 ± 9); at $1 each gains (+$250 ± 12, +$249 ± 12); unslashed, +$317 ± 13 (v3). An honest validator pays $0.98 ± 0.05 a month at 1 outage in 200 draws (v3) |
| `SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS` | **0** (no share of the bounty): keep $5 flat | v3.1's sweep, below |
| `CHALLENGE_REWARD_BPS` | 5,000 of a slash, to whoever proved the fault | as v2 |

**The silence slash, swept (v3.1).** The slash at max($5, x % of the bounty), for a judge bribed 10 % of the bounty on 10 % of its draws: +$311 ± 21 at x = 0, +$311 ± 21 at 1 %, +$307 ± 20 at 2 %, +$229 ± 14 at 5 %. Only x = 10 %, the bribe's own share, makes it lose (−$47 ± 5), and then honest slashes nearly double ($1.79 ± 0.15 a month against $0.98 ± 0.05) and 3 of 40 markets collapse, failing `FEE_MARGIN`'s criterion. A briber can always pay more than x %, and silence buys only a replacement's delay. So the flat $5 stays, and the bribe above $5 is a named trust point.

### Audits
| Parameter | Value | Evidence |
|---|---|---|
| `AUDIT_RATE` | 10 % of submissions | the bribed cheater loses −$859 ± 320 with no volunteers, at $0.018 a check; at 1 % it isn't shown to lose (−$26 ± 89) (v3) |
| `K1_AUDITS` | 2: every k = 1 verdict, by two auditors outside its panel | 98.4 % ± 1.8 of the colluder's own lone verdicts reversed before payment, against 92.0 % ± 4.0 with one audit (v3) |
| Split level C passes | always audited | design D10, D13 (level C is off at launch) |

### The constitution tier
| Parameter | Value | Evidence |
|---|---|---|
| `CONSTITUTION_QUORUM` | 5 of `K_MAX` (7) | as v2 |
| `CONSTITUTION_MIN_ELIGIBLE` | 21 eligible for an ADR that adds or loosens anything, and for an escalated fix | with the deposit, 5 early validators lose −$280 ± 147 and 3 lose −$431 ± 145; from 14 the coalition of 5 isn't bounded (−$58 ± 259); 28 adds nothing (−$283 ± 133) and delays the first ADR from day 122 to day 166 (v3) |
| `REMOVAL_MIN_ELIGIBLE` | 14 for an ADR that only removes or raises a firmware minimum | the coalition of removals loses −$456 ± 103 (v3) |
| ADR expiry | an ADR submitted to a smaller network expires unjudged, its deposit refunded | no adding ADR passed below 21 eligible, and no removal below 14, in any run (v3) |
| `ADR_DEPOSIT` | $15, forfeited to the sponsors' pool by a rejected ADR or escalated fix; refunded when it takes effect or expires | without it the coalition of 5 gains +$255 ± 149; with forfeits to the issue's funder, +$226 ± 151 (v3). It costs an honest author $0.42 an ADR (2.9 % ± 0.8 of good ADRs rejected; v3.1) |
| `ADR_WINDOW`, `REMOVAL_WINDOW` | 14 days; 48 hours | as #85; design D11 |

The deposit is sized for an ADR worth $1,000 to a coalition. The coalition of 5 would break even at about $1,860 an ADR, the coalition of 3 at about $3,870 (derived in v3).

### Pricing
| Parameter | Value | Evidence |
|---|---|---|
| `PRICE_PERIOD` | 1 day | a provider's halved price is followed in 3 days, one `PRICE_STEP_MAX` step a day, with no vote (v3) |
| `PRICE_STEP_MAX`, `PRICE_CAP_X` | 25 % a period; 2 × the price at deployment (a safety bound) | `PRICE_CAP_X` never bound (best 1.68 ×, v1) |
| `MEDIAN_MIN_POSTERS`, the lower median, every family's list price posted | 3 posters of every unit; the lower middle value; every validator posts every family's list price | the inflaters move no price (1.00 ×) and aren't shown to gain (+$2.7 ± 3.9, v3) |
| `FEE_START` | the ceiling | from $0.05, 35 of 40 runs collapse (v3) |
| `FEE_STEP` | 5 % a period, both ways | the fee settles at 1.20 ± 0.04 × break-even (v3) |
| `WAIT_HIGH`, `WAIT_SIGNAL` | 5 % of the period's submissions, every wait counted once | 0 of 40 runs collapse; the floor-bond signal collapses 38, the any-bond one 4 (v3) |
| `IDLE_HIGH` | 40 % of active validators not drawn in the period | at 30 %, 7 of 40 collapse; 50 % holds the fee higher ($0.232 against $0.212) (v3) |
| `FEE_FLOOR`, `FEE_CEILING` | $0.01 and $0.25 a counted check | v2's cap |

### Scores
| Parameter | Value | Evidence |
|---|---|---|
| `SCORE_WINDOW` | the last 200 counted verdicts per family | design D14 |
| `SCORE_MIN`, `SCORE_MIN_VERDICTS`, `SCORE_BALANCED` | 70 % over at least 50 counted verdicts, balanced over passed and failed outcomes | every herder row loses or isn't shown to gain; with plain agreement the weak herders gain +$97 ± 31 on the market (v3) |
| `SCORE_RECOVER_VERDICTS`, `SCORE_RECOVER_MARGIN` | fresh blocks of 100 shadow verdicts, at `SCORE_MIN` + 10 points | a 68 % family recovers by chance 0.12 ± 0.11 times a year, against 9.90 ± 0.47 with round 1's sliding test (v3) |
| `SCORE_FACTOR_MIN`, `SCORE_FACTOR_MAX` | 0.5 × and 2 × the service fee, normalised to a mean of 1 × (2 × a safety bound) | service fees per submission $0.354 against $0.363 without scores; neutral at the median family score, $0.398 (v3); 2 × never bound (best 1.70 ×, v1) |
| Votes | one per judge; scores change pay and eligibility, never a vote | votes weighted by score merge more bad fixes (1.27 ± 0.12 against 1.13 ± 0.10 per 100 paid, with blind spots; v3) |
| `MOVE_REREGISTERS` | changing model family means registering again | when everyone chases the top family, 2.7 families keep 10 % or more, and 11.3 % ± 4.9 of submissions wait (v3) |

### The acceptance thresholds (D17, round 3)
| Threshold | Value | Met on v3's numbers (v3.1) |
|---|---|---|
| Every attacker | **not shown to gain:** mean − 2 SE ≤ 0 and mean + 2 SE ≤ `GAIN_TOLERANCE` ($10 over the run); "loses" reported beside | yes: none of 14 open-validator attackers, 6 pricing, 7 proof-level and 8 scoring attackers is shown to gain; the closest are the inflaters (+$2.7 ± 3.9) and the weak herders (+$0.2 ± 0.7) |
| `SYBIL_SHARE` | 12.5 % of the eligible | yes: a sybil of 3 (12.5 %) never holds a majority of a panel of k ≥ 3 |
| `LONE_CATCH_SHARE` | 90 % of the bad fixes the colluding lone validator passes itself, reversed before payment | yes: 98.4 % ± 1.8 (184 of 187); it loses −$247 ± 41 |
| `FEE_MARGIN` | the fee within 25 % above break-even and at least break-even less one step; no run below 3 active | yes: 1.20 ± 0.04 ×, 0 of 40 collapse |
| `WAIT_CROWD_MAX` | 20 % of submissions wait when everyone chases the top family | yes: 11.3 % ± 4.9 (upper bound 16.2 %) |
| Growth | a small bounty reaches k ≥ 3 within the year in every run | yes: 40 of 40, week 6 ± 1 |
| The constitution | no adding ADR below 21 eligible, no removal below 14, in any run | yes: 0 |
| Answer shopping | counted at 1 in 10; 3 in 10 reported | yes: −$13 ± 1 at 1 in 10 |

### Parameters dropped
Each was run beside its rule on the same seeds; none is needed.

| Dropped | Why (evidence) |
|---|---|
| `FEE_STEP_UP` (10 % up, 5 % down) | no market collapses without it, and it raises the fee ($0.228 against $0.212, 1.22 ± 0.03 × break-even; v3). In round 1 it didn't stop the collapse (32 of 40; v2) |
| `K1_BATCH_BOND` (a bond for the pending k = 1 bounties instead of a count) | it catches less (75.0 % ± 17.0 of every accomplice fix, v3; 63.9 %, v2) and delays honest k = 1 pay (22.9 against 19.4 days, v3) |
| `C_LIMIT_X` (level C's limits halved) | it doesn't stop answer shopping at 3 in 10 (+$157 ± 47 against +$174 ± 46; v3) |
| `SILENCE_SLASH_BPS`, `SEALED_NO_REVEAL_SLASH_BPS` | above; no x from 0 to 5 % makes the 10 % bribe lose, and 10 % breaks the market (v3.1) |
| `IDLE_WINDOW_DAYS` 7 | it pins the fee at its ceiling ($0.250, 0 % idle; v3) |
| The floor-bond and any-bond wait signals | 38 and 4 of 40 markets collapse (v3) |
| $1 slashes, silence unslashed | the bribed silent judge gains (+$250 ± 12, +$317 ± 13; v3) |
| One threshold for every ADR (14 or 28); `ADR_DEPOSIT` $0 or $25; forfeits to the issue's funder | above (constitution tier). $25 works but costs an honest author $0.71 an ADR against $0.42 (v3.1) |
| `K1_AUDITS` 1; `K1_PENDING_MAX` 5 or 20 | above (audits; the k table) |
| Round 1's sliding recovery; a block of 200 at + 5 points | 9.90 ± 0.47 chance recoveries a year; 0.05 ± 0.07, but twice the shadow verdicts per recovery (v3) |
| The neutral score at the median family; plain agreement | fees per submission +12 % ($0.398); the herders' gain back (above) |
| Tuning `DRAW_TRIES`, `SCORE_FACTOR_MAX`, `PRICE_CAP_X` | inert: 8 and 1,000 tries give the same draws; the two caps never bound (v1). `DRAW_TRIES` is a constant; the caps stay as safety bounds, not tuned |

`GAIN_TEST` and `LONE_CATCH_COUNT` stay in the simulation only, to reproduce round 2's verdicts; they are not protocol parameters.

### Named trust points
These remain after every rule, each bounded and measured:
1. **One TEE type's majority while three types are accepted.** With Intel TDX, AMD SEV-SNP and AWS Nitro Enclaves and the TEE cap from k = 5, one type holds the majority of 77 % ± 8 of panels of 3, which are 14 % ± 3 of a growing network's panels: 11.2 % ± 2.9 of all panels of k ≥ 3 (v3). A flaw in one vendor's chip could decide those, within k = 3's limits ($250 at level A, $125 at B) and windows (24 h, 48 h). It ends when adding ADRs bring the list to five types; then Intel's two types, SGX and TDX, could still hold 21 % ± 11 of panels of 3 together, since the cap counts types, not vendors (owner, 2026-11-03).
2. **The accomplice's other fixes.** A colluder isn't a declared party to its accomplice's fixes, so it can sit on the challenge panels of those another judge passed: over 40 runs, 22 of them reached an outcome and 11 were paid (v3). The colluder still loses (−$247 ± 41). Excluding from a challenge panel the validators that judged the same solver's other pending fixes is proposed, not decided (design, round 3, finding 3): an accomplice using a fresh address per fix escapes it.
3. **Answer shopping, once level C is on.** A level C validator that calls its model until it gets the verdict it wants gains +$174 ± 46 a year where borderline fixes fool an honest call 3 times in 10, and loses at 1 in 10 (−$13 ± 1) and at #125's measured room (−$16 ± 1; one 7B model on one setup) (v3). Level C is off at launch, so this applies only after an ADR switches it on.
4. **A silence bribe above the slash.** A judge bribed more than $5 a silence gains (+$311 ± 21 at 10 % of the bounty; v3 and v3.1). Silence buys only a replacement's delay (3 hours): k never shrinks, and the reveal-rate floor suspends the judge.
5. **A sybil above 12.5 %.** Spread over hosts, TEE types and families, a party holding 22 % of the eligible validators holds a majority of 1.2 % of its own panels, 32 % holds 8.0 %, and 49 % holds 30.4 %; on one host, never (v3). Each such false verdict proven costs its whole bond.

### Level C at launch, and when it can be switched on
**Level C (zkTLS) is off at launch** (owner, 2026-11-03): its verifier is in v3's code, but zkTLS isn't on the constitution's list, so no level C validator can register. An adding ADR, judged from 21 eligible with its $15 deposit, switches it on once:
- **#135's blockers are gone** ([`reports/zktls-spike-v1.md`](../../reports/zktls-spike-v1.md)): independent notaries sign proofs for a current release, several of them to list and none required (today none does, and a validator's own notary proves nothing); the default (MPC) mode takes a judge's request of 32 KB (today it's limited to 4 KB, and fails at 8 KB); and the maturity blocker is re-checked (TLSNotary is alpha software and speaks only TLS 1.2). That ADR lists the first notaries; this one lists none.
- **#125 shows the answer-shopping room is small,** or that open-weight verdicts can be re-run ([`reports/determinism-v1.md`](../../reports/determinism-v1.md)). Today: one 7B model in vLLM's batch-invariant mode gave the same tokens on 600 of 600 calls, but different setups disagreed on up to 5 of 30 verdicts. So a re-run proves something only when the receipt pins the prompt, the weights, the engine and its build, the flags, the sampling and the hardware class. Its measured room (+3.5 points with 5 calls) is one model on one setup.

Until then the genesis is at level A or B, as it must be anyway, and answer shopping is not a trust point of the launch.

### The TEE types at launch
**Intel TDX, AMD SEV-SNP and AWS Nitro Enclaves:** three types, so the TEE-type cap starts at k = 5 (trust point 1). Each attestation scheme is its own type; Intel SGX is the likeliest fourth. Not accepted: AMD SEV and SEV-ES without SNP, and a virtual TPM alone. **This list is from the design (D6), not checked against current vendor documentation: confirm each type, its attestation format and its availability by region before deployment,** and record the firmware (TCB) minimums in the deployment record.

### Left for later
- **A randomness beacon** (drand or a VRF) behind D3's interface, if the L2 chosen for deployment makes block hashes weak (a sequencer that can choose its own block's hash).
- **The validators' token slice** (#142), separate from this ADR.
- **Keyless canaries** for the scores (#136): the scores work without them.
- **The challenge-panel exclusion** of trust point 2, if the owner wants it measured.
- **The first zkTLS notaries,** in the ADR that switches level C on.

## Evidence
- **Simulation runs:** `python3 -m pof.sim market validators --seeds 40 --jobs 4` (report v3, 16 minutes on four processes); `python3 -m pof.sim market validators --round3 --seeds 40 --jobs 4` (report v3.1, under 3 minutes). Seeds 1–40. `--v2r1` and `--v1` reproduce reports v2 and v1. Round 3's parameters give round 2's simulation run for run, so v3's numbers stand under them (tested).
- **Tests:** `tests/test_openval_r3.py` (task group 8): each criterion's verdict follows its numbers (+$2.7 ± 3.9 and −$1 ± 7 pass; +$3 ± 2 and −$34 ± 47 fail); report v3's numbers re-judged under round 2's criteria give v3's verdicts; the slash follows the bounty; x = 0 reproduces round 2 on a fixed seed; the honest author forfeits only on rejection (20 tests). The open-validator suites of rounds 1 and 2 still pass: 264 open-validator tests in 69 seconds, and the whole suite (978 tests) under Python 3.13 and 3.9.25.
- **Invariants (Article 5):** v3 is a new version; v2's contracts, constitution and reports are unchanged (D15). No parameter here adds a key, an owner or a vote over a price.
- **Not yet measured:** gas and contract sizes (#138, task 3.5's `reports/contract-v3.md`); the devnet (#140).

## Consequences
- **Validators** register with a bond of at least $100, qualify in about two weeks as shadows, and are paid by a fee the market sets near their break-even. An honest validator's month nets −$1.43 ± 0.22 over its whole registration on the simulated market of 30 submissions a week, and +$4.77 ± 0.31 at 100 a week (v3); its outages cost about $1 a month in $5 slashes.
- **Solvers** of small bounties on a small network wait: an honest k = 1 fix is paid a median 19.4 days after its verdict, and about one submission in five waits for a panel in a growing network's first year (21 % ± 3, v3).
- **ADR authors** post $15, and lose it about 3 times in 100 when honest (v3.1).
- **Funders** see a k table that grows with the network, and each bounty judged by a panel its size and proof allow.
- **Auditors** are drawn by the seed and paid like judges, plus a share of any slash they lead to. **Volunteer challengers** need no account with anyone, and earn half of a slash they prove (`CHALLENGE_REWARD_BPS`).
- **What becomes harder:** a coalition can't take the constitution while the network is small; a lone colluder is audited twice and held unpaid; a sybil needs a larger share than 12.5 % and must spread over hosts, TEE types and families, at its whole bond per proven false verdict.
- **What stays the same:** v2 and its bounties (D15); the keyless contracts; no protocol fee and no token.
- **Next:** #138 builds the contracts with these values; group 3 of #132 starts after #85's bonds and challenges (5.8), seals and receipts on-chain (5.5/5.6, #122) and attestation (#94).

## Challenge window
None yet: no constitution tier exists to pass it. The owner accepts it by merging. Its values go into v3's constitution at deployment and are fixed per version: changing one needs a new version (D15). Only the lists D10 and D11 put under ADRs (the accepted TEE types, proof types, notaries, image digests and firmware minimums) change by adding or removal ADRs, from 21 and 14 eligible.
