# Outside revenue from check domains, v2 of the funder token (proof-of-fix#195; 2026-11-09)

**Command:** `python3 -m pof.sim.fundertoken --seeds 20 --v2 --json > reports/fundertoken-v2.json` (about five minutes; without `--json` it prints the tables below). Seeds 1-20, a year of 52 weekly cycles each, as in [v1](fundertoken-v1.md). Simulation only (rule 1): simulated money, no model calls, no chain. The model is still `pof/sim/fundertoken.py`; its docstring lists every assumption.

**What v2 adds.** v1 found that the protocol's own activity can't pay investors: at the price use supports (p\* ≈ $0.27 a token) they get back about 23 cents per dollar. #195 asks whether outside use can close the gap: the judges answering other contracts' questions, in **check domains**.
- **A domain** has a number of requests a cycle (flat, or growing from a start level up to a ceiling), a price, and our real cost per request.
- **The judges' real cost** is paid to them in stablecoins at cost. It is never burned, so it doesn't change what funders get back.
- **The margin** (price − cost) is burned in the one general token. That's the only way outside use reaches funders.
- **The panel** is 3 judges (the issue tier) or all 7 (the constitution tier). Article 3 allows only those two before v3 (#132).
- **Following #196's market desk study** (`reports/oracle-market-v1.md`, PR #196), each domain's revenue is verdicts × (price − cost), not one flat margin a check.

**v1 is unchanged.** Every v1 mechanism (the thin-cycle fix, the merit cap, `TOKENS_PER_COIN`, (a), (b), (c), the attacks) is the same code, switched the same way. With no outside use the model reproduces v1 bit for bit: `python3 -m pof.sim.fundertoken --seeds 20 --json` still writes v1's JSON byte for byte, on the Python that wrote it (3.13). On Python before 3.12, floats are summed differently, so the last digits differ. A test checks both.

**How to read the price.** As in v1, the model doesn't predict a price. p\* is the price at which the year's burns absorb every token minted: the price use alone supports. **Value back per coin at p\*** is a funder's tokens per coin spent × p\*. 100 % means break even. The main measure is the **pool investors'** (one repository's pool and the index pool), as in v1.

## The domains (assumptions)

| Domain | Tier | Panel | Price a request | Our cost (paid to the judges) | Margin (burned) | Source |
|---|---|---|---|---|---|---|
| **Security triage:** bug-bounty and audit-contest reports, each with a proof-of-concept run | checkable | 3 | $9 ($8-10 in the scenarios) | $1 ($0.37-3 in the scenarios) | $8 | Price: contest judging, about $8-10 an issue (#196, Sherlock). Cost: **not measured**. A medium code check is $0.37 ([costs v1](costs-v1.md)); a PoC on a forked chain costs more. |
| **Code checks** for outside repositories | checkable | 3 | $1 | $0.37 | $0.63 | AI pull-request review, about $1 (#196, Greptile). Cost: a medium check at judge grade (costs v1). |
| **Routine resolution and fact checks** with fetched sources | partly checkable | 3 | $0.50 | $0.45 | $0.05 | Assumed. UMA's AI drafts one for $0.005 and proposers get $2-5 (#196). Cost: 3 × $0.15, a model reading the sources plus a zkTLS fetch (#139). |
| **Prediction-market disputes** | judgment | 7 | $30 | $1.50 | $28.50 | Assumed, against a $750 bond (#196: about 50 a week escalate). Cost: 7 escalated medium reviews (costs v1) plus fetches. |
| **Maths:** does a Lean statement say what the question means | checkable | 3 | $0.09 | $0.09 | $0 | Nobody pays per check today (#196), so it's sold at cost, for credibility. |

**Validators (assumptions):**
- **Judges:** 7 (Article 3).
- **Nodes:** one judge node works on 8 answers at once, 60 % of the week. That's 48,384 slot-minutes a cycle.
- **Time per answer:** triage 20 slot-minutes, code 6, Lean 10, others 3-5.
- **Node cost:** $65 a week (an AWS m6i.2xlarge with Nitro Enclaves, on demand, $0.384 an hour).
- **Bond:** at least twice the largest value one request decides. Article 3.7 sets that rule for bounties, and v2 extends it to outside requests: $1,000 for most domains, $10,000 for triage, $50,000 for disputes. A bond would earn 5 % a year elsewhere.

## Summary

1. **Investors break even when outside margins burn about $6,900 a week.** That's 71 % of what funders spend, the same rule as v1.
   - They get **+20 % at about $8,800 a week.**
   - With (b) + (c) on (v1's recommendation), it takes about 15 % more: $7,900 and $10,000.
   - In requests a week, at the margin per request:

     | Margin a request | Break even | +20 % |
     |---|---|---|
     | $0.05 | 139,000 | 175,000 |
     | $0.10 | 69,000 | 88,000 |
     | $0.25 | 28,000 | 35,000 |
     | $0.63 (a code check at $1) | 11,000 | 14,000 |
     | $1 | 6,900 | 8,800 |
     | **$8 (security triage at $9)** | **870** | **1,100** |
     | $28.50 (a dispute at $30) | 240 | 310 |

   - The break-even price is the same everywhere: **p\* = $1.17 at break even and $1.41 at +20 %.**
2. **Against #196's market, security triage decides it.**
   - **300 verdicts a week** (#196's low end): investors get back 41-56 %. **No.**
   - **900 a week:**
     - At $10 and a cost of $1 or less: **113-119 %. Yes** (102-107 % with (b) + (c)).
     - At $8: 73-99 %. No.
     - At a $3 cost: 93 %. No.
   - **3,000 a week:** 188-340 %. **Yes, at every price and cost.**
   - **#196's whole-market scenarios:**
     - "first year, low" (triage 300, code 500): 54 %.
     - "first year, realistic" (triage 900, code 2,000, 10 disputes): **120 %** (108 % with (b) + (c)).
     - "all we could serve" (triage 3,000, code 5,000, 50 disputes, 2,000 resolutions): **338 %**.
   - In every scenario, more than 80 % of the margin comes from triage.
3. **Loud: at #196's upper end, use pushes the price above both of v1's attack prices.**
   - **Where the price goes:**
     - 3,000 triage verdicts a week at $8-10 with a cost of $1 or less, or at $10 with a $3 cost: p\* = **$2.98-3.99**.
     - #196's "all we could serve" scenario: **$3.96**.
     - v1 found that overclaimed merit plus self-funding beats its honest twin from **$2.84** (5 of 15 judges colluding). v2 finds the same price.
     - That price comes at about **2,500 triage verdicts a week**. Self-dealing's $1.12 comes at about 810, so even the 900-verdict break-even crosses it.
   - **What it means: no new way to cheat, but v1's safety margin is gone.**
     - v1's twin funds nothing. Once funding pays, any play that funds looks like a gain against it.
     - v2 also measures each attack against the **honest use of the same coin**: putting it in the pools.
       - **Overclaiming loses $2,900-4,700 a year at every price up to $100**, with 0, 3 or 5 colluding judges.
       - **Self-dealing** beats honest investing only from $1.16-1.54, and only by **$11-43 a year**. Its own coin is paid in full when a pool is short, the edge any bounty has.
       - **1-cent pledges** beat it only from about $16, by $4-18 a year at $20-30 a token. Each pledge's coin earns 1 token, against 0.85 in a pool.
     - What stops overclaiming is still **the 3× issue stake and the challenges**, not a low price.
     - But a price above $2.84 means **v1's "it would only pay at a price use can't reach" is no longer true.**
   - **The proposed fix: a rebate ceiling.**
     - **The rule:** a cycle's outside margins are burned only up to `rebate_max` × the coin paid to fixes that cycle, less the payout fee's cap and the cycle's other burns. The rest of the margin isn't charged: buyers pay less, which also helps win volume.
     - **The protocol doesn't need the token's price for this.** The rule uses only coin and dollars it already counts.
     - **At 1.2:** investors are held at **126-127 % per coin** and p\* at **$1.49-1.64**, however large outside use grows (tested to 10× break even, with 86 % of the margin waived there).
     - **At 1.5:** 158-159 %, with p\* at $1.87-2.05. Both stay below $2.84.
     - Second, **#186's acceptance criteria should judge attacks against the honest use of the attacker's coin.** Once funding pays, v1's twin flags plain investing as an attack.
4. **The domain mix matters only through margin dollars.**
   - The judges' cost passes through, so the mix changes **how many requests** are needed, not what investors get back from a given margin.
   - Mixes, by share of requests:
     - **Mostly checkable** (triage 10 %, code 70 %): about **5,600 requests a week** to break even. Triage brings 64 % of the margin.
     - **Mostly judgment and facts** (disputes 30 %, routine resolution 60 %): about **790 a week**. Disputes bring 97 % of the margin.
   - Domains alone:
     - **Triage alone:** 870.
     - **Code checks alone:** 11,000.
     - **Routine resolution alone:** 139,000 (a $0.05 margin, hopeless).
     - **Disputes alone:** 240.
   - #196 counts about 50 disputes a week in the whole market, so **judgment-heavy mixes rest on volume that doesn't exist.** The checkable mix rests on triage, which #196 rates the best fit.
5. **Growth: a year of growth doesn't pay the first year's funders.**
   - Tokens minted in a quarter clear at that quarter's p\*.
   - Triage starting at a tenth of break even and growing 5 % a week passes break even in about cycle 48. Investors get back 38 % in Q1 and 92 % in Q4: **58 % over the year.**
   - Starting at a quarter and growing 3 % a week gives 69 % over the year.
   - Only a flat break-even volume from cycle 1 gives 100 %.
6. **Validators: seven judges are enough, but pay at cost doesn't keep them.**
   - **Load:**
     - At #196's volumes, each judge answers **360-4,550 requests a week**, under one every two minutes.
     - One node each is enough.
     - A checkable mix needs a second node per judge only from about 3× break even. At 10× it needs 4 nodes per judge, or 26 one-node validators under v3's open registry.
   - **Cost:**
     - Pass-through covers only the judges' variable cost. Each judge's node and its bond's opportunity cost go unpaid: **$84-161 a week.**
     - That's **$0.035-0.23 per answer, 19-120 % of the real cost**, at #196's volumes.
   - **Disputes are the expensive part.** A $50,000 decision needs a $100,000 bond from each of the 7 judges.
     - That's $673 a week of opportunity cost in all.
     - 10 disputes a week burn only $285 of margin.
     - Disputes pay for their own bonds only from about **24 a week**.
7. **The rest of v1 holds with outside use.**
   - **Without (a), outside burns don't touch pools, tokens or solvers.** Every attack's gain at a given price is exactly v1's (a test checks this). Only the price moves.
   - **(b) + (c)** still leaves 0.5 % of merit unpaid and 0.1 % of coin idle. It costs about 15 % more outside volume to break even, because its funders get fewer tokens per coin (0.77 against 0.85).
   - **(a) with a small base (2,000) stops being an inflation risk.** Its cap follows burns, and outside burns dominate them.
     - Mint ÷ burn at $1 falls from 1.92 to **0.99 at break even** and 0.42 at the $2.84 level, so supply shrinks.
     - With (a), funders get more tokens per coin (0.96-0.98), so p\* is lower ($1.01 at break even). The value back per coin is the same: only burns set it.

## Recommendation (for the owner)
- **Price each domain at what buyers already pay, and count only verdicts × (price − cost).** Not a flat margin a check.
- **Target security triage:**
  - **Volumes:** about **870 verdicts a week at a $9 price ($8 margin) to break even, and 1,100 for +20 %**. At $10 with a $1 cost, 900 is enough for +13 %.
  - **Cost:** measure our cost per triage verdict before promising anything. At $3 a verdict, 900 a week falls to 93 %.
- **Code checks at about $1 are a supplement, not a plan.** They'd need 11,000 a week alone.
- **Leave out of the money case:**
  - routine resolution, at $0.05 of margin, which can't compete with a $0.005 AI draft;
  - Lean checks (no buyers).
- **Prediction-market disputes:** only after #139's fetched sources, and only at 24 or more a week, so they cover the judges' bonds.
- **Volume targets by margin:** the table in summary 1.
  - In dollars: **$6,900 a week of margin to break even, $8,800 for +20 %** ($7,900 and $10,000 with (b) + (c)).
- **Add the rebate ceiling, `rebate_max` = 1.2-1.5,** before outside volume can reach about 2,500 triage verdicts a week. It keeps p\* below v1's attack prices and turns a windfall into cheaper verdicts.
- **Change #186's attack criteria:** compare each attack with the honest use of its coin, not with doing nothing.
- **Pay validators a fee beyond cost**, not burned:
  - **How much:** about $0.25 an answer at low volume, falling with volume. Or a fixed weekly retainer per judge.
  - **What it costs the margin:** for triage, 3 × $0.25 = $0.75 of an $8 margin.
  - **Bonds:** set them per domain, at twice the largest value one request decides.
- **For the paper:**
  - Funders can be paid back only by outside use. In #196's realistic first-year scenario it just reaches break even (about +20 %), and only if triage sells at contest-judging prices.
  - A growing market pays later funders, not the first year's.

## What fails or is uncertain
- **Uncertain: the market itself.** All of #196's volumes and prices are desk estimates.
  - The triage price assumes buyers pay contest-judging rates for an attested 3-judge quorum rather than one cheap model.
  - A first-year share of 900 verdicts a week is #196's upper "realistic" figure, not a forecast.
- **Uncertain: our cost per triage verdict.** It isn't measured. At $3, 900 verdicts a week doesn't break even.
- **Fails without a fix: v1's attack-price argument.** At #196's upper end, p\* passes $2.84 (above). The rebate ceiling and the honest-use measure are the proposed fixes. The ceiling is simulated; the measure is a spec change.
- **Fails for the first year's funders under growth** (summary 5).
- **Fails for validators at cost** (summary 6): they need a fee or a retainer.
- **Not tested: whether the rebate ceiling can be gamed.** Self-dealt coin raises the room for burns by $1-1.3 a dollar. Whether that pays wasn't simulated.
- **Simplified:**
  - each quarter's p\* clears its own minting, as if funders sold every quarter;
  - requests are deterministic, with no week-to-week noise;
  - one 3-judge domain stands in for any flat margin in the volume × margin sweep;
  - the bounty market's own checks keep v1's $0.05 margin. So v2's volumes differ slightly from v1's table 4, which moved that margin too.
- **Not modelled:**
  - competition and price cuts;
  - a domain's failure or removal (ADR 0005's job);
  - the challenge window outside requests need (a 2-hour market against ADR 0004's 6-336 hours);
  - speculation above p\*;
  - v3's variable panels.

## Results (20 seeds, a year)

#### 0. With no outside use, v1's numbers

p\* = $0.273 ± 0.003 and pool investors get back 23% per coin spent (v1: $0.273 ± 0.003, 23 %).

#### 1. What outside use must burn

| Adaptation | Funder | Tokens per coin spent | p* with no outside use | Value back per coin at p* | Outside margin dollars a cycle to break even | …to get +20 % | Break even, as a share of what all funders spend |
|---|---|---|---|---|---|---|---|
| none | pool investors (one repository's pool and the index) | 0.85 ± 0.01 | 0.273 ± 0.003 | 23% | $6,926 (6,804 – 7,043) | $8,756 (8,595 – 8,899) | 71% |
| none | investors picking bounties | 0.82 ± 0.01 | 0.273 ± 0.003 | 22% | $7,255 (7,067 – 7,385) | $9,150 (8,913 – 9,319) | 75% |
| none | bounty buyers | 0.71 ± 0.01 | 0.273 ± 0.003 | 19% | $8,787 (8,524 – 8,983) | $10,989 (10,666 – 11,226) | 91% |
| (b) + (c) | pool investors (one repository's pool and the index) | 0.77 ± 0.01 | 0.301 ± 0.003 | 23% | $7,914 (7,855 – 7,978) | $9,994 (9,924 – 10,077) | 72% |
| (b) + (c) | investors picking bounties | 0.74 ± 0.01 | 0.301 ± 0.003 | 22% | $8,330 (8,193 – 8,455) | $10,494 (10,322 – 10,645) | 76% |
| (b) + (c) | bounty buyers | 0.65 ± 0.01 | 0.301 ± 0.003 | 20% | $9,756 (9,573 – 9,893) | $12,205 (11,983 – 12,371) | 89% |

#### 2. Outside volume x margin (one 3-judge domain; the bounty market's own checks stay at $0.05)

| Margin a request | Break even, none: requests a cycle (p10 – p90) | Break even, (b) + (c): requests a cycle (p10 – p90) | +20 %, none | +20 %, (b) + (c) | p* at break even / +20 % (none) |
|---|---|---|---|---|---|
| $0.01 | 692,617 (680,417 – 704,265) | 791,379 (785,527 – 797,819) | 875,616 (859,508 – 889,874) | 999,449 (992,364 – 1,007,682) | $1.17 / $1.41 |
| $0.02 | 346,308 (340,209 – 352,133) | 395,689 (392,764 – 398,909) | 437,808 (429,754 – 444,937) | 499,725 (496,182 – 503,841) | $1.17 / $1.41 |
| $0.05 | 138,523 (136,083 – 140,853) | 158,276 (157,105 – 159,564) | 175,123 (171,902 – 177,975) | 199,890 (198,473 – 201,536) | $1.17 / $1.41 |
| $0.1 | 69,262 (68,042 – 70,427) | 79,138 (78,553 – 79,782) | 87,562 (85,951 – 88,987) | 99,945 (99,236 – 100,768) | $1.17 / $1.41 |
| $0.25 | 27,705 (27,217 – 28,171) | 31,655 (31,421 – 31,913) | 35,025 (34,380 – 35,595) | 39,978 (39,695 – 40,307) | $1.17 / $1.41 |
| $0.5 | 13,852 (13,608 – 14,085) | 15,828 (15,711 – 15,956) | 17,512 (17,190 – 17,797) | 19,989 (19,847 – 20,154) | $1.17 / $1.41 |
| $1 | 6,926 (6,804 – 7,043) | 7,914 (7,855 – 7,978) | 8,756 (8,595 – 8,899) | 9,994 (9,924 – 10,077) | $1.17 / $1.41 |
| $2 | 3,463 (3,402 – 3,521) | 3,957 (3,928 – 3,989) | 4,378 (4,298 – 4,449) | 4,997 (4,962 – 5,038) | $1.17 / $1.41 |

**Value back per coin spent at p\* (p\* in brackets), pool investors, no adaptation:**

| Margin a request | 10,000 requests a cycle | 25,000 requests a cycle | 50,000 requests a cycle | 100,000 requests a cycle | 250,000 requests a cycle | 1,000,000 requests a cycle |
|---|---|---|---|---|---|---|
| $0.05 | 29% ($0.35) | 38% ($0.44) | 52% ($0.61) | 79% ($0.93) | 161% ($1.89) | 571% ($6.70) |
| $0.1 | 35% ($0.41) | 52% ($0.61) | 79% ($0.93) | 134% ($1.57) | 298% ($3.49) | 1117% ($13.11) |
| $0.25 | 52% ($0.61) | 93% ($1.09) | 161% ($1.89) | 298% ($3.49) | 708% ($8.30) | 2757% ($32.35) |
| $1 | 134% ($1.57) | 298% ($3.49) | 571% ($6.70) | 1117% ($13.11) | 2757% ($32.35) | 10956% ($128.53) |

#### 3. The market study's scenarios (#196): verdicts x (price - cost)

| Triage verdicts a cycle | Price | Our cost a verdict | Margin burned a cycle | Value back per coin, pool investors (none / (b) + (c)) | Break even? | p\* (none) | v1's attack prices ($1.12 self-dealing, $2.84 overclaim + self-funding) |
|---|---|---|---|---|---|---|---|
| 300 | $8 | $0.37 | $2,289 | 49% / 46% | no / no | $0.58 | below both |
| 300 | $8 | $1.00 | $2,100 | 47% / 44% | no / no | $0.55 | below both |
| 300 | $8 | $3.00 | $1,500 | 41% / 38% | no / no | $0.48 | below both |
| 300 | $10 | $0.37 | $2,889 | 56% / 52% | no / no | $0.66 | below both |
| 300 | $10 | $1.00 | $2,700 | 54% / 50% | no / no | $0.63 | below both |
| 300 | $10 | $3.00 | $2,100 | 47% / 44% | no / no | $0.55 | below both |
| 900 | $8 | $0.37 | $6,867 | 99% / 90% | no / no | $1.17 | above $1.12 |
| 900 | $8 | $1.00 | $6,300 | 93% / 84% | no / no | $1.09 | below both |
| 900 | $8 | $3.00 | $4,500 | 73% / 67% | no / no | $0.86 | below both |
| 900 | $10 | $0.37 | $8,667 | 119% / 107% | **yes** / **yes** | $1.40 | above $1.12 |
| 900 | $10 | $1.00 | $8,100 | 113% / 102% | **yes** / **yes** | $1.32 | above $1.12 |
| 900 | $10 | $3.00 | $6,300 | 93% / 84% | no / no | $1.09 | below both |
| 3,000 | $8 | $0.37 | $22,890 | 275% / 244% | **yes** / **yes** | $3.22 | above $1.12 and $2.84 |
| 3,000 | $8 | $1.00 | $21,000 | 254% / 226% | **yes** / **yes** | $2.98 | above $1.12 and $2.84 |
| 3,000 | $8 | $3.00 | $15,000 | 188% / 168% | **yes** / **yes** | $2.21 | above $1.12 |
| 3,000 | $10 | $0.37 | $28,890 | 340% / 302% | **yes** / **yes** | $3.99 | above $1.12 and $2.84 |
| 3,000 | $10 | $1.00 | $27,000 | 319% / 283% | **yes** / **yes** | $3.75 | above $1.12 and $2.84 |
| 3,000 | $10 | $3.00 | $21,000 | 254% / 226% | **yes** / **yes** | $2.98 | above $1.12 and $2.84 |

| Scenario (requests a cycle) | Margin burned a cycle | Of it, from triage | What buyers pay a cycle | Value back per coin, pool investors (none / (b) + (c)) | Break even? | p\* (none) | v1's attack prices |
|---|---|---|---|---|---|---|---|
| #196's first year, low: triage 300, code 500, maths 50 | $2,715 | 88% | $3,204 | 54% / 50% | no / no | $0.63 | below both |
| #196's first year, realistic: triage 900, code 2,000, disputes 10, maths 200 | $8,745 | 82% | $10,418 | 120% / 108% | **yes** / **yes** | $1.41 | above $1.12 |
| all we could serve (#196's upper end): triage 3,000, code 5,000, disputes 50, resolution 2,000, maths 500 | $28,675 | 84% | $34,545 | 338% / 300% | **yes** / **yes** | $3.96 | above $1.12 and $2.84 |

#### 3b. Growth paths

Security triage at an $8.00 margin (a $9 price, $1 cost) breaks pool investors even at about 866 verdicts a cycle. Each path is in those terms. Each quarter's p\* clears that quarter's minting with its own burns.

| Path | Verdicts a cycle: cycle 1 → 52 | Value back per coin over the year (p\*) | Q1 | Q2 | Q3 | Q4 | First quarter at break even |
|---|---|---|---|---|---|---|---|
| flat at break even | 866 → 866 | 100% ($1.17) | 104% | 99% | 98% | 99% | Q1 |
| starts at a quarter, +3 % a cycle | 216 → 977 | 69% ($0.80) | 51% | 56% | 72% | 95% | never this year |
| starts at a tenth, +5 % a cycle | 87 → 1,042 | 58% ($0.68) | 38% | 42% | 60% | 92% | never this year |
| starts at a tenth, +5 % a cycle, levels off at break even | 87 → 866 | 58% ($0.67) | 38% | 42% | 60% | 89% | never this year |
| starts at 1 %, +10 % a cycle | 9 → 1,118 | 45% ($0.53) | 29% | 27% | 40% | 82% | never this year |

#### 4. Domain mixes

| Domain | Tier | Panel | Judges' real cost a request (paid at cost) | Margin a request (burned) | What a user pays a request | Slot-minutes a judge's answer | Largest value one request decides |
|---|---|---|---|---|---|---|---|
| security triage (bounty and contest reports with a PoC) | checkable | 3 | $1.00 | $8.00 | $9.00 | 20 | $10,000 |
| code checks for outside repositories | checkable | 3 | $0.37 | $0.63 | $1.00 | 6 | $1,000 |
| routine resolution and fact checks with fetched sources | partly checkable | 3 | $0.45 | $0.05 | $0.50 | 3 | $1,000 |
| prediction-market disputes | judgment | 7 | $1.50 | $28.50 | $30.00 | 5 | $50,000 |
| maths: does a Lean statement say what the question means | checkable | 3 | $0.09 | $0.00 | $0.09 | 10 | $1,000 |

| Mix (shares of requests) | Margin a request, mean | Requests a cycle to break even (none) | …with (b) + (c) | Requests a cycle for +20 % (none) | Value back per coin at that volume, in the simulation (break even / +20 %) | Burns by domain (triage / code / resolution / disputes / maths) | What users pay a cycle at break even | …of which judges' cost |
|---|---|---|---|---|---|---|---|---|
| mostly checkable (triage 10%, code 70%, resolution 10%, maths 10%) | $1.246 | 5,559 (5,461 – 5,652) | 6,351 | 7,027 | 100% / 120% | 64% / 35% / 0% / 0% / 0% | $9,222 | $2,296 |
| balanced (triage 5%, code 35%, resolution 40%, disputes 10%, maths 10%) | $3.490 | 1,984 (1,949 – 2,018) | 2,267 | 2,509 | 100% / 120% | 11% / 6% / 1% / 82% / 0% | $7,955 | $1,029 |
| mostly judgment and facts (triage 2%, code 8%, resolution 60%, disputes 30%) | $8.790 | 788 (774 – 801) | 900 | 996 | 100% / 120% | 2% / 1% / 0% / 97% / 0% | $7,533 | $606 |
| security triage only (triage 100%) | $8.000 | 866 (851 – 880) | 989 | 1,095 | 100% / 120% | 100% / 0% / 0% / 0% / 0% | $7,792 | $866 |
| code checks only (code 100%) | $0.630 | 10,994 (10,800 – 11,179) | 12,562 | 13,899 | 100% / 120% | 0% / 100% / 0% / 0% / 0% | $10,994 | $4,068 |
| routine resolution only (resolution 100%) | $0.050 | 138,523 (136,083 – 140,853) | 158,276 | 175,123 | 100% / 120% | 0% / 0% / 100% / 0% / 0% | $69,262 | $62,335 |
| disputes only (disputes 100%) | $28.500 | 243 (239 – 247) | 278 | 307 | 100% / 120% | 0% / 0% / 0% / 100% / 0% | $7,291 | $365 |

#### 5. Validators

Seven judges (Article 3), each answering every request it's drawn for. One judge node works on 8 answers at once, 60% of the week: 48,384 slot-minutes a cycle. A node costs $65 a week; a bond earns 5% a year elsewhere.

| Outside use | Requests a cycle | Answers a cycle, per judge (a minute) | Nodes each judge runs | Each judge's pay a cycle (its real cost, passed through) | Each judge's bond | Each judge's cost not covered a cycle (nodes + the bond's opportunity cost) | …per answer (share of its real cost) | Validators needed with v3's open registry (one node each) |
|---|---|---|---|---|---|---|---|---|
| #196's first year, low | 850 | 364 (0.04) | 1 | $70 | $20,000 | $84 | $0.231 (120%) | 7 |
| #196's first year, realistic | 3,110 | 1,339 (0.13) | 1 | $239 | $100,000 | $161 | $0.120 (67%) | 7 |
| all we could serve (#196's upper end) | 10,550 | 4,550 (0.45) | 1 | $839 | $100,000 | $161 | $0.035 (19%) | 7 |
| mostly checkable, break even | 5,559 | 2,382 (0.24) | 1 | $328 | $20,000 | $84 | $0.035 (26%) | 7 |
| mostly checkable, +20 % | 7,027 | 3,012 (0.30) | 1 | $415 | $20,000 | $84 | $0.028 (20%) | 7 |
| mostly checkable, 10x break even | 55,587 | 23,823 (2.36) | 4 | $3,280 | $20,000 | $279 | $0.012 (9%) | 26 |
| mostly judgment and facts, break even | 788 | 473 (0.05) | 1 | $87 | $100,000 | $161 | $0.341 (186%) | 7 |
| mostly judgment and facts, +20 % | 996 | 598 (0.06) | 1 | $110 | $100,000 | $161 | $0.270 (147%) | 7 |
| mostly judgment and facts, 10x break even | 7,879 | 4,728 (0.47) | 1 | $866 | $100,000 | $161 | $0.034 (19%) | 7 |

#### 6. v1's conclusions with outside use

Outside margin dollars a cycle are set from the no-adaptation run of each seed: 0, its break even, its +20 % and where its p\* reaches $2.84 (v1's price at which overclaim plus self-funding starts to beat its honest twin with 5 of 15 judges colluding); on average $6,926, $8,756 and $19,922.

| Adaptation | Outside use | p\* ($) | Pool investors' tokens per coin | Value back per coin at p\* | Merit left unpaid | Coin waiting at the year's end | Fixes a cycle, healthy repo (last quarter) | Mint ÷ burn at $1.00 | Tokens the per-fix cap cut |
|---|---|---|---|---|---|---|---|---|---|
| none | none | 0.273 ± 0.003 | 0.85 ± 0.01 | 23% | 3.5% | 14.7% | 10.6 | 3.51 ± 0.05 | 1.1% |
| none | break even | 1.173 ± 0.014 | 0.85 ± 0.01 | 100% | 3.5% | 14.7% | 10.6 | 0.85 ± 0.01 | 1.1% |
| none | +20 % | 1.408 ± 0.017 | 0.85 ± 0.01 | 120% | 3.5% | 14.7% | 10.6 | 0.71 ± 0.01 | 1.1% |
| none | p* at $2.84 | 2.840 ± 0.000 | 0.85 ± 0.01 | 242% | 3.5% | 14.7% | 10.6 | 0.35 ± 0.00 | 1.1% |
| (b) + (c) | none | 0.301 ± 0.003 | 0.77 ± 0.01 | 23% | 0.5% | 0.1% | 11.2 | 3.21 ± 0.03 | 0.0% |
| (b) + (c) | break even | 1.177 ± 0.013 | 0.77 ± 0.01 | 91% | 0.5% | 0.1% | 11.2 | 0.85 ± 0.01 | 0.0% |
| (b) + (c) | +20 % | 1.406 ± 0.017 | 0.77 ± 0.01 | 108% | 0.5% | 0.1% | 11.2 | 0.71 ± 0.01 | 0.0% |
| (b) + (c) | p* at $2.84 | 2.802 ± 0.016 | 0.77 ± 0.01 | 215% | 0.5% | 0.1% | 11.2 | 0.36 ± 0.00 | 0.0% |
| (a) with a base of 2,000 | none | 0.240 ± 0.002 | 0.98 ± 0.01 | 24% | 3.6% | 14.7% | 10.4 | 1.92 ± 0.01 | 2.9% |
| (a) with a base of 2,000 | break even | 1.009 ± 0.018 | 0.98 ± 0.00 | 99% | 3.5% | 14.5% | 10.5 | 0.99 ± 0.01 | 2.6% |
| (a) with a base of 2,000 | +20 % | 1.215 ± 0.021 | 0.98 ± 0.00 | 119% | 3.6% | 14.7% | 10.5 | 0.84 ± 0.01 | 2.6% |
| (a) with a base of 2,000 | p* at $2.84 | 2.455 ± 0.031 | 0.98 ± 0.00 | 241% | 3.6% | 15.0% | 10.5 | 0.42 ± 0.01 | 2.5% |
| (a) base 2,000 + (b) + (c) | none | 0.239 ± 0.001 | 0.96 ± 0.01 | 23% | 0.6% | 0.1% | 11.3 | 1.83 ± 0.01 | 0.0% |
| (a) base 2,000 + (b) + (c) | break even | 0.936 ± 0.007 | 0.96 ± 0.01 | 90% | 0.6% | 0.1% | 11.3 | 1.07 ± 0.01 | 0.0% |
| (a) base 2,000 + (b) + (c) | +20 % | 1.118 ± 0.009 | 0.96 ± 0.01 | 108% | 0.6% | 0.1% | 11.3 | 0.89 ± 0.01 | 0.0% |
| (a) base 2,000 + (b) + (c) | p* at $2.84 | 2.228 ± 0.021 | 0.96 ± 0.01 | 214% | 0.6% | 0.1% | 11.3 | 0.45 ± 0.00 | 0.0% |

#### 7. Farming when funding pays

| Attack | Colluding judges (of 15) | Pays over v1's twin from (any play) | Pool investors' value back per coin there | Security triage verdicts a cycle that push p\* there (an $8 margin) | Gain a year over the honest use of the same coin (best play), at $1.41 (+20 %) | at $2.84 | at $10 | Beats the honest use of its coin from |
|---|---|---|---|---|---|---|---|---|
| self-dealing: a $5 fix claimed at its worth, funded from a second wallet | 0 | $1.12 | 95% | 811 | 16 ± 7 | 19 ± 6 | 43 ± 13 | $1.16 |
| self-dealing: a $5 fix claimed at its worth, funded from a second wallet | 5 | $1.13 | 96% | 822 | 11 ± 10 | 14 ± 9 | 32 ± 15 | $1.54 |
| overclaimed merit, funded from a second wallet | 0 | $5.12 | 432% | 4,726 | -4,424 ± 341 | -4,469 ± 345 | -4,694 ± 368 | **never** (to $100) |
| overclaimed merit, funded from a second wallet | 3 | $3.96 | 332% | 3,588 | -3,721 ± 367 | -3,759 ± 366 | -3,948 ± 364 | **never** (to $100) |
| overclaimed merit, funded from a second wallet | 5 | $2.84 | 238% | 2,496 | -2,943 ± 401 | -2,975 ± 405 | -3,133 ± 431 | **never** (to $100) |
| 1-cent pledges on every fix of 2 unfunded repositories, per-fix cap on, the cut to uncapped fixes (#186 D3) | – | $3.20 | 275% | 2,886 | -21 ± 1 | -19 ± 1 | -8 ± 1 | $16.13 |

#### 8. The rebate ceiling (proposed): value back per coin at p\* (p\*; share of outside margins not charged)

| Rebate ceiling | Adaptation | Outside margins at 0.5x break even | Outside margins at 1x break even | Outside margins at 2x break even | Outside margins at 5x break even | Outside margins at 10x break even |
|---|---|---|---|---|---|---|
| off | none | 62% ($0.73) | 100% ($1.17) | 176% ($2.06) | 403% ($4.73) | 781% ($9.17) |
| off | (b) + (c) | 57% ($0.74) | 91% ($1.18) | 157% ($2.04) | 357% ($4.64) | 690% ($8.97) |
| 1.2x the coin | none | 62% ($0.73; 0% waived) | 100% ($1.17; 0% waived) | 127% ($1.49; 32% waived) | 127% ($1.49; 73% waived) | 127% ($1.49; 86% waived) |
| 1.2x the coin | (b) + (c) | 57% ($0.74; 0% waived) | 91% ($1.18; 0% waived) | 126% ($1.64; 23% waived) | 126% ($1.64; 69% waived) | 126% ($1.64; 85% waived) |
| 1.5x the coin | none | 62% ($0.73; 0% waived) | 100% ($1.17; 0% waived) | 156% ($1.84; 13% waived) | 159% ($1.87; 64% waived) | 159% ($1.87; 82% waived) |
| 1.5x the coin | (b) + (c) | 57% ($0.74; 0% waived) | 91% ($1.18; 0% waived) | 153% ($1.99; 3% waived) | 158% ($2.05; 60% waived) | 158% ($2.05; 80% waived) |
