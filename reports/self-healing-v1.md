# Self-healing, v1: check fees and seat bonds (proof-of-fix#85 tasks 4.5 and 4.6; 2026-11-01)

**Commands:** `python3 -m pof.sim.oraclenet fees --seeds 100` (about 40 seconds) and `python3 -m pof.sim.oraclenet bonds --seeds 100` (about 10 seconds) print the tables below. The models are `pof/checkgas.py` (the fee rules of design S15) and `pof/sim/oraclenet.py` (the market comparison and the seat-level model of S12, S16 and S17). Simulation only: credits are dollars at 1 credit = $1, as in [`costs-v1`](costs-v1.md), and nothing opens a connection (rule 1).

**Scope.** This report covers tasks 4.5 and 4.6 only. Tasks 4.1–4.4 (tiers and escalation, the head and the pool, the winner's refund and coin only, the attackers' 100-seed acceptance run) are still open, so the acceptance criteria of the incentive-simulation delta are **not** all evaluated here; the market below is today's simulation (two juries of families A–C, attested runners), with only the way checks are charged changed.

## Headline

| Question | Answer |
|---|---|
| **Check gas against flat fees** (100 seeds, paired) | Solvers pay **$5.04 per paid fix in checks instead of $9.21** (−45 %), and $2.08 per attempt instead of $3.88. Attempts rise **+7.1 ± 1.6**, paid bounties **+1.7 ± 0.6**, funders' cost per paid bounty **−$6.82 ± 2.83**. Days to fix don't change. |
| **The deposit's ceiling** | $9.52, against today's $6.60: the worst case under the caps (140k input and 16k output tokens per verdict at the dearest family, 20 minutes of CI) is higher than the flat fees; solvers get the unused part back. |
| **First `SERVICE_FEE`** | **$0.05 per counted check** (recommended), with `SERVICE_FEE_CAP` **$0.25**. An on-demand enclave breaks even from about **55 checked submissions a week** on the network (93 counted checks a month for one seat); below that a seat loses at most about $4.67 a month (its fixed costs). |
| **The cartel's year** | `SERVICE_FEE` stops at its cap, but **the unit prices have no cap of their own: 52 updates of +25 % multiply them by 109,476.** At ×10 attempts fall by a fifth; at ×100 no bounty is paid. **A ceiling on the table is needed** (owner decision, below). |
| **`SEAT_BOND_MIN`** | Over a year every slashable fault loses from a bond of **$250**. But **one** equivocation sold on the largest bounty needs **$1,107** to lose (detection 50 %). Recommended: **twice the largest bounty a version allows** (here about **$1,250**), so the bond follows bounty size, not fees. The S16 starting point of 50 × a seat's weekly fees ($54) is far too low. |

## 4.5 Check fees

### How a check is charged (S15)
- **Pass-through, per unit:** each counted judge is paid the **median** of the counted judges' AI usage at **its own family's** list prices (pof/costs.py, 2026-10-30), plus storage; the CI run's vCPU- and GB-seconds at Fargate's rates; gas at cost. No profit in these parts.
- **One service fee per counted check, the same for every seat.**
- **Caps:** 140,000 input and 16,000 output tokens per verdict, 20 MB of storage (assumptions: twice costs-v1's large review); the CI profile's CPU, memory and timeout (default 2 vCPU, 4 GB, 20 minutes). A run stops at its limit.
- **The deposit** is the worst case under the caps at the dearest family, plus the service fees and a gas allowance ($0.10); the rest is refunded.
- **Updates:** 5 of 7 seats, every entry within ±25 %, effective after 7 days, one pending at a time, `SERVICE_FEE` never above its cap. Unit-tested in `tests/test_checkgas.py`, including the delta's scenarios (a padder, a heavier check, the deposit's ceiling, a 40 % jump, a fee above the cap, the notice).
- **`CI_SINGLE_RUN`** is in the fee model (one run charged once; unit-tested) but not in the market comparison, whose attested runners are today's two.

### In the market
In the market simulation, check gas is opt-in (`market_sim.run(..., check_gas=table)`); the default runs are unchanged (the same report bytes as main on `market` and `market_spam`, seeds 1–2). Families A, B and C are priced as Anthropic, OpenAI and Google; a fix's size from its changed lines (up to 120 small, up to 500 medium, else large) sets its tokens and CI minutes as in costs-v1.

### Flat fees against check gas (100 seeds, the same seeds)

| | Flat (today) | Check gas | Difference (paired) |
|---|---|---|---|
| Bounties paid | 36.0 ± 0.5 | 37.8 ± 0.6 | 1.7 ± 0.6 |
| Attempts | 85.3 ± 1.5 | 92.4 ± 1.7 | 7.1 ± 1.6 |
| Bounties never attempted | 58.2 ± 0.8 | 57.0 ± 0.8 | -1.2 ± 1.1 |
| Funders' cost per paid bounty | 124.51 ± 2.39 | 117.69 ± 2.20 | -6.82 ± 2.83 |
| Solvers' check fees per paid fix | 9.21 ± 0.20 | 5.04 ± 0.06 | -4.18 ± 0.19 |
| Solvers' check fees per attempt | 3.875 ± 0.045 | 2.077 ± 0.030 | -1.798 ± 0.047 |
| The check deposit (ceiling) | 6.60 ± 0.00 | 9.52 ± 0.00 | 2.92 ± 0.00 |
| Evaluators' net per verdict | 0.0364 ± 0.0013 | -0.0808 ± 0.0009 | -0.1172 ± 0.0016 |
| Days to fix | 12.15 ± 0.18 | 12.26 ± 0.13 | 0.11 ± 0.17 |

### The table raised (50 seeds; the service fee capped at $0.25)

| Every unit price × | Attempts | Bounties paid | Never attempted | Check fees per attempt | Deposit |
|---|---|---|---|---|---|
| 1 | 92.8 ± 2.2 | 37.7 ± 0.9 | 56.9 ± 1.2 | $2.04 | $9.52 |
| 2 | 84.2 ± 2.0 | 35.1 ± 0.7 | 55.7 ± 1.3 | $2.50 | $18.94 |
| 5 | 81.2 ± 1.6 | 35.4 ± 0.7 | 62.1 ± 1.2 | $3.65 | $47.20 |
| 10 | 72.7 ± 1.7 | 34.1 ± 0.8 | 61.5 ± 1.2 | $4.99 | $91.80 |
| 100 | 49.0 ± 1.5 | 0.0 ± 0.0 | 92.7 ± 1.4 | $0.00 | $894.57 |

The cartel's year: 52 updates applied; every unit price × 109,476, the service fee $0.25 (its cap).

### The operator's on-demand enclave (one seat)

Overhead per counted check $0.0119; fixed $4.67 a month.

| Network checks a week | Seat's checks a month | Break-even fee | Net a month at $0.02 | at $0.05 | at $0.10 |
|---|---|---|---|---|---|
| 5 | 9 | $0.5144 | $-4.59 | $-4.31 | $-3.85 |
| 20 | 37 | $0.1375 | $-4.37 | $-3.25 | $-1.39 |
| 50 | 93 | $0.0621 | $-3.91 | $-1.13 | $3.51 |
| 200 | 371 | $0.0245 | $-1.66 | $9.49 | $28.06 |
| 1,000 | 1,857 | $0.0144 | $10.38 | $66.09 | $158.95 |
| 5,000 | 9,286 | $0.0124 | $70.55 | $349.12 | $813.41 |

**Reading the market table.**
- **Cheaper checks bring more attempts and more paid bounties,** and funders pay a little less per paid bounty: solvers price their checks into their bids (`expected_checks`).
- **The evaluators' "net per verdict" turns negative (−$0.08)** because the simulation's own effort cost for an evaluator is $0.30 a verdict and $0.20 a run (`pof/sim/checks.py`), set before B2 measured the real cost (about $0.13 for a judge-grade medium review, cents for a run). Under check gas a real operator's net is, by construction, **the service fee less its enclave's overhead** (the pass-through parts net to zero): the operator table below. Aligning the simulation's effort costs with B2 belongs to task 4.1.
- **The table raised:** with every unit price ×2 to ×10, attempts fall steadily (−22 % at ×10) while paid bounties hold up; at ×100 the deposit ($895) is beyond solvers' balances and nothing is paid.

### Sizing `SERVICE_FEE`: one seat's on-demand enclave
Assumptions (`pof.checkgas.Enclave`, us-east-1 on-demand list prices, 2026-11):
- a **c6g.xlarge** parent at **$0.136 an hour** ([Holori calculator](https://calculator.holori.com/aws/ec2/c6g.xlarge/us-east-1); c6i.xlarge is $0.170). Nitro Enclaves need a parent with a vCPU reserve and don't run on burstable types ([AWS FAQ](https://aws.amazon.com/ec2/nitro/nitro-enclaves/faqs/), [multiple enclaves](https://docs.aws.amazon.com/enclaves/latest/user/multiple-enclaves.html));
- started on demand: **3 minutes** to start and stop the instance and enclave, **2 minutes** waiting on the model, **5 %** of starts retried. The tests' own time is passed through, so it isn't counted again;
- an always-on **t4g.nano watcher** ($0.0042 an hour) and 20 GB of gp3 ($0.08 per GB-month): **$4.67 a month** fixed. The operator's own time isn't priced (a business choice).

So a counted check costs a seat **$0.012** on top of the passed-through usage. A seat is drawn for 3 of 7 judges on each check.

**Recommendation: `SERVICE_FEE` = $0.05, `SERVICE_FEE_CAP` = $0.25.**
- $0.05 is about 4× the per-check overhead, so it covers failed runs and idle time with a margin, and breaks even from about 55 network checks a week; at 1,000 a week a seat keeps about $66 a month, at 5,000 about $349.
- The simulated market checks only about 7 submissions a week; at that volume every seat loses about $4 a month at any fee up to $0.10. That's the expected early subsidy (#82's business model), not a reason for a higher fee: at $0.10 the break-even falls to about 25 a week, but solvers pay twice as much for the overhead.
- The cap at 5× leaves room for the fee to follow real costs, by ±25 % steps after 7 days' notice, without the step limit alone being the only brake.

## 4.6 Bonds and faults

### The seat-level model
One seat over a year (`pof.sim.oraclenet.SeatWorld`): 50 checked submissions a week, the seat drawn for 3 of 7 judges each time, 5 merged heads a week (each signed for availability by every seat, S17), the bounty prices of the simulated market's paid bounties, the honest net of $0.05 less the overhead per counted check, and the enclave's fixed cost. **Each faulty seat runs against its honest twin on the same seed** (the same draws and bounties). A slash must be topped up to keep the seat (S16), so it is a real loss either way; a seat that loses its whole bond is out for the rest of the year.

The faults and their assumptions (`pof.sim.oraclenet.Fault`):
| Fault | Gain | Proof and slash |
|---|---|---|
| **Non-revealer** | bribed on 10 % of its draws to go silent; the replacement seat's fresh seal window is worth 5 % of the bounty to the briber | always proven: `NO_REVEAL_SLASH_BPS` 5 %, and the check's fee lost |
| **Equivocator** | bribed on 10 % of its draws; signs both outcomes for two relayers; worth the bounty's price when its vote is pivotal (10 %) | whoever holds both signatures proves it, 50 % of the time: the whole bond, and the seat is out. (A reveal that doesn't match its seal is refused by the contract, so that variant gains nothing.) |
| **Usage padder** | reports 10× its tokens on every check. Alone, the median pays the honest usage: no gain. **A pair** pads the median whenever both are drawn (1 check in 7 for each) | a padded receipt doesn't match the provider's counts it hashes: a receipt challenge catches it 2 % of the time per receipt; `BAD_RECEIPT_SLASH_BPS` (**not set by S16; assumed 20 %**) |
| **Data withholder** | signs availability for every head, stores nothing, saves 10 MB a year per head | an availability challenge names it 5 % of the time per head: `DA_FAIL_SLASH_BPS` 20 % |
| **Price-table colluders** | not slashable | 4.5's cartel year; disciplined by demand, forks and #100's governance |

Paid bounties' prices (364 from seeds 1-10): median $86, p90 $184, max $553. A seat's service fees: $1.07 a week at 50 checks a week.

### Each faulty seat against its honest twin (100 seeds; net over a year, $, attacker minus twin)

| Fault | bond $25 | bond $50 | bond $100 | bond $250 | bond $500 | bond $1,000 | bond $2,500 | bond $5,000 | bond $10,000 |
|---|---|---|---|---|---|---|---|---|---|
| non_revealer | 432 ± 5 ⚠ | 291 ± 4 ⚠ | 8 ± 4 ⚠ | -840 ± 9 | -2,254 ± 21 | -5,081 ± 46 | -13,563 ± 123 | -27,699 ± 250 | -55,971 ± 504 |
| equivocator | -43 ± 5 | -68 ± 5 | -118 ± 5 | -268 ± 5 | -518 ± 5 | -1,018 ± 5 | -2,518 ± 5 | -5,018 ± 5 | -10,018 ± 5 |
| usage_padder (alone) | -112 ± 2 | -223 ± 5 | -446 ± 10 | -1,116 ± 25 | -2,231 ± 49 | -4,462 ± 98 | -11,155 ± 246 | -22,310 ± 491 | -44,620 ± 983 |
| usage_padders (a pair) | 271 ± 3 ⚠ | 160 ± 5 ⚠ | -64 ± 10 | -733 ± 25 | -1,848 ± 49 | -4,079 ± 98 | -10,772 ± 246 | -21,927 ± 491 | -44,237 ± 983 |
| data_withholder | -65 ± 2 | -132 ± 3 | -264 ± 7 | -661 ± 17 | -1,323 ± 34 | -2,647 ± 68 | -6,619 ± 171 | -13,239 ± 341 | -26,479 ± 683 |

⚠: doesn't lose significantly at that bond.

Smallest bond in the sweep at which every slashable fault loses over a year: **$250**.

### One fault on one bounty (the bond at which it loses in expectation)

| Fault | median bounty ($86) | p90 bounty ($184) | max bounty ($553) |
|---|---|---|---|
| non_revealer | $86 | $184 | $553 |
| equivocator | $173 | $367 | $1,107 |
| usage_padder (alone) | $0 | $0 | $0 |
| usage_padders (a pair) | $292 | $292 | $292 |
| data_withholder | $0 | $0 | $0 |

### What sets the bond
- **Over a year,** a bond of **$250** makes every slashable fault lose significantly (100 seeds, two standard errors). Below it, a bribed non-revealer (+$8 at $100) and a padding pair (+$271 at $25) come out ahead.
- **A single large fault is what binds.** A seat could cheat **once**, on the biggest bounty it ever sees, and leave. One equivocation sold on the largest simulated bounty ($553) loses only if the bond is above **$1,107** (half the time it isn't proven); a silence bought on it needs $553.
- **So the bond should follow bounty size, not fees.** Recommendation: **`SEAT_BOND_MIN` = 2 × the largest bounty a version accepts** (a new `BOUNTY_MAX` per version), about **$1,250** for the bounties simulated here. 50 × a seat's weekly fees ($54 at 50 checks a week) is far too low, because a bribe scales with what a verdict decides, not with what a check earns.
- **A padding pair is the only fault that profits from small bonds by repetition;** the median rule already defeats a lone padder. Its bound depends on how often receipts are challenged: at 2 % a bond of $292 makes even one padded check lose in expectation.
- **Not slashable, by design:** a wrong verdict in good faith (S16), lazy judging (the canary scoreboard), and **price-table collusion** (4.5's cartel year). These are disciplined by the scoreboard, by demand (expensive checks lose attempts), by forks, and by the governance #100 has to design.

## Decisions for the owner
1. **A ceiling on the unit prices.** `SERVICE_FEE` has a cap, the unit prices don't: 5 colluding seats can multiply them by about 109,000 in a year within the ±25 % rule. Options: a constitution cap per entry (for example 2× the genesis table, changed only by ADR), or indexing each entry to its provider's public price list (#100).
2. **`SERVICE_FEE` = $0.05, `SERVICE_FEE_CAP` = $0.25** (or $0.10 if seats should break even at lower volume, at twice the overhead per check for solvers).
3. **`SEAT_BOND_MIN` = 2 × `BOUNTY_MAX`,** which means adding a per-version `BOUNTY_MAX` (for example $625, giving a $1,250 bond); or a fixed bond of about $1,250 if bounties stay under about $600.
4. **`BAD_RECEIPT_SLASH_BPS`:** S16 names the fault but not its size; this report assumes 20 % (as for availability).
5. **The simulation's evaluator costs** ($0.30 a verdict, $0.20 a run) predate B2's measurements; task 4.1 should align them, after which the market's operator net under check gas will match the enclave table.

## Not done here
- Tasks 4.1–4.4, and with them the incentive-simulation delta's other acceptance criteria (the test-gamer, the injector, collusion below and at the quorum, the head and the pool, the winner's refund).
- `CI_SINGLE_RUN` in the market (it is in the fee model and unit-tested).
- The seat model's gains are assumptions (bribe rates, pivotal share, detection rates), each a named parameter; a measured challenge rate will replace them on the devnet.
