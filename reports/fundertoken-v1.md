# One general token earned by funders, investor pools and an emission that adapts, v1 (proof-of-fix#193; 2026-11-09)

**Command:** `python3 -m pof.sim.fundertoken --seeds 20 --json > reports/fundertoken-v1.json` (about three minutes; without `--json` it prints the tables below). Seeds 1-20, a year of 52 weekly cycles each. Simulation only (rule 1): simulated money, no model calls, no chain. The model is `pof/sim/fundertoken.py`, and its docstring lists every assumption. Merit, noise, the attacker, the defences and the stake reuse [cyclepool v1](cyclepool-v1.md)'s values (#184). The payout fee is [potfee v1](potfee-v1.md)'s capped fee (#182).

**The owner's design (2026-11-09/10):**
- **Who earns what:** solvers are paid in stablecoins, and funders earn one protocol token.
- **Pay:** each fix is paid at most its merit in dollars from its repository's pool (the thin-cycle fix), pro rata when the pool is short.
- **Emission:** min(rate × network merit, cap). Each fix's share is capped at `TOKENS_PER_COIN` × the coin that paid it. The part the cap cuts isn't minted. A fix's tokens go to whoever's coin paid it.
- **Burns:** a margin on every check, failed submissions' stakes, and the payout fee (the token value the coin earned, up to 20 % of the coin).
- **Adaptations:** (a) cap = base + last cycle's burns; (b) pay per merit dollar = clamp(pool ÷ merit, 1, 1.5); (c) a shortfall is the first claim on the next pool.

**The world:**
- **Repositories:** 12. Eight stay healthy, with about 10 fixes a cycle (median $86 of merit). Four stall at cycle 13, falling to 2 fixes a cycle with a median of $30.
- **Funders:**
  - bounty buyers fund 30 % of fixes at their own estimate of the fix's value;
  - 10 investors pick bounties, $150 a cycle each, at an AI estimate;
  - 48 investors back one repository's pool, $100 a cycle each, starting 4 per repository;
  - an index pool gets $1,500 a cycle, **spread by need**: a repository's recent merit, less its recent bounty coin and the coin already waiting in its pool.
- **Single-repository investors' rule:** each cycle, a quarter of them review their position. Each compares its repository with 3 others by tokens per coin held over the last 4 cycles, and moves its unspent coin and future inflow if another does 1.5× better. If not, and its pool spent under a tenth of what it held, it withdraws half its unspent coin.
- **Solvers** follow pay: a repository's fix rate scales with its recent pay per merit dollar.
- **Emission settings:** rate 1 token per merit dollar, cap 8,000 a cycle, `TOKENS_PER_COIN` = 1. Margin $0.05 a check. Failed submissions forfeit $5 each (0.5 a fix on average).

**The token's price (read this first).** The model doesn't predict a price. Funding a fix is a purchase of newly minted tokens, so a funder's dollar return is its **tokens per coin spent × the price**. The report gives two things:
- **The break-even price:** for each funder, 1 ÷ its tokens per coin.
- **The flow-clearing price p\*:** the highest price at which the year's burns still absorb every token minted. Every burn is modelled as dollars that buy tokens and burn them, so burns are the token's only buyers here.
  - Below p\*, burns exceed minting and the supply shrinks.
  - Above p\*, funders who sell what they earn find fewer buyers than sellers. The price holds there only if someone accumulates tokens (speculation or holding for some other use), which this model doesn't know about.
  - So p\* is the price **use alone** supports. It isn't a forecast.

## Summary
1. **Investors get back about 23 cents per dollar spent at the price use supports, whichever product they pick.** p\* is $0.27 a token.
   - At p\*, single-repository pools, the index pool and bounty pickers get 22-23 % of their spent coin back in token value. Bounty buyers get 19 %, but they also get the fix they needed.
   - Counting coin returned unspent, pool investors end the year at −63 % (p10-p90: −67 % to −58 %) and the index at −66 %.
   - The break-even price is $1.17-1.22 a token for investors and $1.41 for buyers. That's about 4.3× p\*.
2. **Those 23 cents are almost all the payout fee, paid by solvers.** At p\* the fee takes 19 % of the coin paid to fixes, out of solvers' pay. It buys back the tokens funders sell. Margins and failed stakes add about 3 points.
   - If the fee goes to the next pool instead of being burned, investors get back 3 % (p\* = $0.037).
   - **Emission settings don't change this.** The rate, the cap, (a), (b) and (c) change how many tokens there are and so p\*, but the value back per coin at p\* stays at 22-24 % in every case. Only burns change what funders get back in dollars.
3. **Investors break even only once outside check volume is far larger than the bounty market.** The bounty market runs about 820 checks a cycle, and funders spend about $9,700 a cycle.
   - At a $0.05 margin, investors break even at about 139,000 outside checks a cycle (about 170× the market's own) and get back half at 47,000.
   - At $0.10 they break even at 69,000 outside checks; at $0.25, at 27,000.
   - Break-even comes when margin × outside checks reaches about 70 % of what funders spend.
4. **Healthy against stalling makes little difference, because investors leave stalled repositories fast.**
   - Half the single-repository investors in stalling repositories have left 5 cycles after the stall (4 with (b), 7-8 with (c)). Within 7 cycles, only a tenth of all single-repository investors are still in one, against a third before.
   - Those still in a stalling repository at the year's end earned the same tokens per coin (0.85). More of their coin sat unspent: 22 % against 18 %.
   - Short pools give their funders slightly more tokens per coin, so a stall costs investors only idle money, not token yield.
5. **Farming loses with #186's defences, at 80 % caught and up to 5 of 15 judges colluding:**
   - **Self-dealing through second wallets** (funding your own trivial fix) is just buying tokens at the same rate as everyone else. It loses $27-241 a year against its honest twin. It starts to pay only from $1.12 a token, the price at which honest investors already get back 95-96 %.
   - **Overclaimed merit** (#184's team) loses $2,900-4,400 a year at any price. Adding self-funding to collect tokens makes it lose more, and it pays only above $2.84-5.12 a token, where honest funding would return 2.4-4.3× its cost.
   - **The 3× issue stake is what stops overclaiming.** Without it the team gains $1,400-2,500 a year in coin alone, at any token price, as in #184.
   - **One-cent pledges** on valuable fixes nobody funds lose $23-31 a year: the per-fix cap gives 1 cent of coin at most 0.01 tokens. Without the cap the attacker gains $3,700-74,000 a year. **The cap is essential.**
6. **A finding against the design as written:** "the cut isn't minted" lets 1-cent pledges cut everyone else's tokens. The pledged fixes' merit enters the network total while the cap binds, but their tokens are cut. For $31 a year, honest investors' tokens per coin fall **16 %**. With #186 D3's rule instead (the cut goes to uncapped fixes), the change is +0.2 %.
7. **Adaptations:**
   - **(a) cap = base + last burns doesn't settle supply.** Once the cap binds, minting replaces every burned token and adds the base, so supply grows by about the base every cycle whatever the use. At $1 a token it grows 1,997 a cycle with a base of 2,000. With a base of 8,000, mint ÷ burn is 4.0, against 3.5 with no (a). Below p\* every variant shrinks. (a) bounds inflation at the base; a base of 0 would be true burn-and-mint equilibrium.
   - **(b) pays solvers more and draws them in.** Healthy repositories get 11.4 fixes a cycle against 10.6, at $1.08 per merit dollar. It spends the idle coin: 0.3 % waits at the year's end, against 14.7 %. But pools are drained at 1.5× and are short later, so 11 % of merit goes unpaid, against 3.5 %. Funders' tokens per coin fall from 0.85 to 0.73, because each coin buys less merit.
   - **(c) leaves no merit unpaid** (0.0 %), and slows the exit from a stalled repository by 2-3 cycles while its backlog is paid.
   - **(b) + (c)** pays solvers $1.06 per merit dollar, leaves 0.5 % unpaid and 0.1 % of coin idle.
   - **Solvers barely follow money into stalled repositories** (2.0 → 2.1-2.3 fixes a cycle), because the money leaves first.

## Recommendation (for the owner)
- **Keep the per-fix cap, `TOKENS_PER_COIN` = 1 token per coin** at a rate of 1 token per merit dollar. Without it, 1-cent pledges pay at any price.
- **Give what the cap cuts to the uncapped fixes (#186 D3), rather than not minting it.** An equivalent rule counts each fix's merit in the network total only up to its coin. Either one removes the 16 % dilution.
- **Keep the 3× issue stake (#186 D5), challenges and merit records.** They're what make overclaiming lose once funders earn tokens.
- **Turn (b) and (c) on together, with `pay_max` = 1.5.** (b) alone leaves 11 % of merit unpaid.
- **(a): use a small base, or none.** With a base about a quarter of the cap (2,000), inflation above p\* is held at the base. With the base equal to the cap, (a) inflates more than a fixed cap. A base that decays to 0 would let supply settle where mint = burn.
- **Burn the payout fee, capped at 20 %.** It's 20 of the 23 cents investors get back. Then say plainly who pays it: solvers, about 19 % of their pay at p\*.
- **Margin: $0.05-0.10 a check,** but don't count on it from the bounty market alone: it adds under half a point there.
- **For the paper:** don't present the pools as investments with a return. Use alone supports about 23 cents per dollar funded. Investors break even only with outside check volume of 70,000-140,000 a cycle at those margins, which is outside use the protocol doesn't have yet. Funding is mostly paying for fixes, with a partial rebate in tokens.

## What fails or is uncertain
- **Fails: investors' return.** At the price use supports, every funder type loses about 77 % of what it spends. Picking bounties, one pool or the index changes this by a point or two. The design rewards funders only if outside check volume or holding demand appears.
- **Fails as written: "the cut isn't minted"** (1-cent dilution, above).
- **Fails as a stabiliser: (a)** with a large base.
- **Uncertain: the price model.** p\* assumes funders sell what they earn and the only buyers are burners. Holding demand would raise the price, and then supply inflates (mint ÷ burn 3.5 at $1), which this model doesn't follow over time.
- **Uncertain: the judges' detection rate (80 %) and the challenge check (90 %)** are #184's assumptions, measured only by #160's paid test.
- **One rule for investors' behaviour, and a churning one:** about 5 moves a year each, at no cost. Slower or costlier moves would leave more coin idle in stalled repositories.
- **(c)'s carried merit is minted when it's paid,** as new merit in that cycle; other accounting choices give slightly different tokens per coin.
- **Not modelled:**
  - curated pools (lowest priority in #193);
  - honest fixers' own stake forfeits (under 0.2 % of the pool in #184);
  - the challenge reward;
  - audits after the split;
  - more than one attacker;
  - growth of the network;
  - the use value of a bounty buyer's fix.

## Results (20 seeds, a year)

#### 1. Investors' returns, no adaptation

The flow-clearing price p* = **$0.273 ± 0.003** a token (margin $0.05 a check, no outside checks). At p* the payout fee takes 19.0% of the coin paid to solvers.

| Funder | Tokens per coin spent (mean ± sd over seeds) | p10 – p90 over funders | Break-even price ($ a token) | Coin left over (of what it put in) | Value back per coin spent at p* | Return on what it put in at p* (p10 – p90) |
|---|---|---|---|---|---|---|
| bounty buyers (need the fix) | 0.71 ± 0.01 | 0.61 – 0.74 | $1.41 | 0% | 19% | -81% (-83% – -80%) |
| investors picking bounties | 0.82 ± 0.01 | 0.81 – 0.84 | $1.22 | 0% | 22% | -77% (-78% – -77%) |
| one repository's pool, started healthy | 0.85 ± 0.01 | 0.83 – 0.87 | $1.18 | 18% | 23% | -63% (-67% – -59%) |
| one repository's pool, started in one that stalls | 0.85 ± 0.01 | 0.83 – 0.87 | $1.18 | 18% | 23% | -63% (-67% – -58%) |
|   of those, still in a stalling one at the end | 0.85 ± 0.02 | 0.82 – 0.87 | $1.17 | 22% | 23% | -60% (-65% – -55%) |
| the index pool (by need) | 0.86 ± 0.01 | 0.84 – 0.87 | $1.17 | 13% | 23% | -66% (-67% – -66%) |

#### 1b. Investors' returns with (b) + (c)

The flow-clearing price p* = **$0.301 ± 0.003** a token (margin $0.05 a check, no outside checks). At p* the payout fee takes 19.3% of the coin paid to solvers.

| Funder | Tokens per coin spent (mean ± sd over seeds) | p10 – p90 over funders | Break-even price ($ a token) | Coin left over (of what it put in) | Value back per coin spent at p* | Return on what it put in at p* (p10 – p90) |
|---|---|---|---|---|---|---|
| bounty buyers (need the fix) | 0.65 ± 0.01 | 0.61 – 0.68 | $1.53 | 0% | 19% | -81% (-82% – -80%) |
| investors picking bounties | 0.74 ± 0.01 | 0.72 – 0.75 | $1.35 | 0% | 22% | -78% (-78% – -77%) |
| one repository's pool, started healthy | 0.77 ± 0.01 | 0.75 – 0.79 | $1.29 | 0% | 23% | -77% (-77% – -76%) |
| one repository's pool, started in one that stalls | 0.75 ± 0.01 | 0.72 – 0.77 | $1.33 | 0% | 23% | -77% (-78% – -77%) |
|   of those, still in a stalling one at the end | 0.73 ± 0.02 | 0.72 – 0.75 | $1.37 | 2% | 22% | -76% (-78% – -75%) |
| the index pool (by need) | 0.78 ± 0.01 | 0.77 – 0.79 | $1.28 | 0% | 23% | -76% (-77% – -76%) |

#### 2. Farming, with the funder rewards (#186's defences on; honest judges see through an overclaim 80% of the time)

| Attack | Colluding judges (of 15) | Its best play | Gain a year over its honest twin at $0.05 | at $0.20 | at $0.50 | at $1.00 | Pays from a token price of (any play, mean over seeds) | …where honest pool investors get back, per coin spent |
|---|---|---|---|---|---|---|---|---|
| self-dealing: a $5 fix claimed at its worth, funded from a second wallet | 0 | claims $5, own coin $1 | -238 ± 7 | -205 ± 7 | -139 ± 5 | -27 ± 6 | $1.12 | 95% |
| self-dealing: a $5 fix claimed at its worth, funded from a second wallet | 3 | claims $5, own coin $1 | -241 ± 10 | -208 ± 9 | -142 ± 9 | -29 ± 10 | $1.12 | 96% |
| self-dealing: a $5 fix claimed at its worth, funded from a second wallet | 5 | claims $5, own coin $1 | -241 ± 11 | -208 ± 10 | -142 ± 9 | -30 ± 9 | $1.13 | 96% |
| overclaimed merit, no own funding (#184's team) | 0 | claims $15, own coin $0 | -4,348 ± 427 | -4,372 ± 426 | -4,379 ± 425 | -4,379 ± 425 | **never** (to $100) | – |
| overclaimed merit, no own funding (#184's team) | 3 | claims $15, own coin $0 | -3,729 ± 514 | -3,766 ± 511 | -3,775 ± 510 | -3,775 ± 510 | **never** (to $100) | – |
| overclaimed merit, no own funding (#184's team) | 5 | claims $15, own coin $0 | -2,887 ± 556 | -2,942 ± 552 | -2,955 ± 551 | -2,955 ± 551 | **never** (to $100) | – |
| overclaimed merit, funded from a second wallet | 0 | claims $15, own coin $5 | -5,584 ± 340 | -5,448 ± 339 | -5,147 ± 341 | -4,615 ± 343 | $5.12 | 432% |
| overclaimed merit, funded from a second wallet | 3 | claims $15, own coin $5 | -4,872 ± 370 | -4,749 ± 368 | -4,445 ± 369 | -3,906 ± 370 | $3.96 | 332% |
| overclaimed merit, funded from a second wallet | 5 | claims $15, own coin $5 | -4,079 ± 398 | -3,972 ± 396 | -3,673 ± 395 | -3,134 ± 394 | $2.84 | 238% |
| the same, without the issue stake (what the stake does) | 0 | claims $200, own coin $0 | 2,472 ± 660 | 2,141 ± 574 | 2,066 ± 551 | 2,066 ± 551 | any price: it pays in coin alone | – |
| the same, without the issue stake (what the stake does) | 3 | claims $200, own coin $0 | 2,375 ± 866 | 1,791 ± 817 | 1,673 ± 796 | 1,673 ± 796 | any price: it pays in coin alone | – |
| the same, without the issue stake (what the stake does) | 5 | claims $200, own coin $0 | 2,332 ± 1,664 | 1,550 ± 1,509 | 1,379 ± 1,469 | 1,379 ± 1,469 | any price: it pays in coin alone | – |
| 1-cent pledges on every fix of 2 unfunded repositories, per-fix cap on (the design) | – | 1 cent a fix, $0.02 gas | -31 ± 1 | -31 ± 1 | -28 ± 1 | -23 ± 1 | $3.2000 | honest pool investors' tokens per coin -16.0% |
| 1-cent pledges on every fix of 2 unfunded repositories, per-fix cap on, the cut given to uncapped fixes (#186 D3) | – | 1 cent a fix, $0.02 gas | -31 ± 1 | -31 ± 1 | -28 ± 1 | -23 ± 1 | $3.2000 | honest pool investors' tokens per coin +0.2% |
| 1-cent pledges on every fix of 2 unfunded repositories, no per-fix cap | – | 1 cent a fix, $0.02 gas | 3,660 ± 118 | 14,738 ± 477 | 36,895 ± 1,193 | 73,824 ± 2,388 | $0.0004 | honest pool investors' tokens per coin -16.0% |

#### 3. Adaptation

| Adaptation | Coin waiting in stalling repositories ($): cycle 12 → 16 → 26 → 52 | Single-repo investors still in stalling ones: 12 → 16 → 26 → 52 | Fixes a cycle, healthy repo (last quarter) | Fixes a cycle, stalling repo (last quarter) | Solvers' pay per merit dollar, healthy (gross) | Merit left unpaid | Pool investors' tokens per coin spent | Coin waiting at the year's end (of all pool coin put in) | p* ($) | Pool investors' value back per coin at p* |
|---|---|---|---|---|---|---|---|---|---|---|
| none | 1,104 → 3,485 → 2,194 → 4,502 | 33% → 18% → 7% → 9% | 10.6 | 2.0 | 1.02 ± 0.01 | 3.5% | 0.85 ± 0.01 | 14.7% | 0.273 ± 0.003 | 23% |
| (a) cap = base + last burns | 1,074 → 3,881 → 2,322 → 4,529 | 35% → 20% → 7% → 8% | 10.4 | 2.0 | 1.02 ± 0.01 | 3.5% | 1.00 ± 0.00 | 14.5% | 0.236 ± 0.001 | 24% |
| (a) with a base of 2,000 | 998 → 3,751 → 2,091 → 5,025 | 34% → 19% → 6% → 10% | 10.5 | 2.0 | 1.01 ± 0.01 | 3.5% | 0.99 ± 0.00 | 14.5% | 0.240 ± 0.002 | 24% |
| (b) pay up to 1.5x when money waits | 170 → 2,453 → 380 → 203 | 33% → 16% → 2% → 2% | 11.4 | 2.1 | 1.08 ± 0.01 | 11.1% | 0.73 ± 0.01 | 0.3% | 0.307 ± 0.004 | 22% |
| (c) shortfall carried | 3 → 892 → 1,035 → 2,665 | 33% → 31% → 3% → 8% | 10.6 | 2.3 | 1.04 ± 0.00 | 0.0% | 0.81 ± 0.01 | 8.0% | 0.288 ± 0.006 | 23% |
| (b) + (c) | 0 → 528 → 523 → 102 | 33% → 33% → 3% → 2% | 11.2 | 2.2 | 1.06 ± 0.01 | 0.5% | 0.77 ± 0.01 | 0.1% | 0.301 ± 0.003 | 23% |
| (a) + (b) + (c) | 0 → 528 → 559 → 100 | 33% → 33% → 2% → 2% | 11.3 | 2.3 | 1.06 ± 0.01 | 0.6% | 0.96 ± 0.01 | 0.1% | 0.239 ± 0.001 | 23% |

**Supply.** Mint over burn above 1 means the supply grows. With (a) the run is repeated at each price, since the cap follows burned tokens.

| Adaptation | Mint ÷ burn over the year at $0.05 | at $0.20 | at $1.00 | Net tokens added a cycle, last quarter, at $1.00 | Tokens the per-fix cap cut (of what the formula allowed) |
|---|---|---|---|---|---|
| none | 0.58 ± 0.00 | 0.85 ± 0.00 | 3.51 ± 0.05 | 5,688 ± 65 | 1.1% |
| (a) cap = base + last burns | 0.62 ± 0.00 | 0.87 ± 0.00 | 4.00 ± 0.03 | 6,736 ± 248 | 3.2% |
| (a) with a base of 2,000 | 0.62 ± 0.00 | 0.87 ± 0.00 | 1.92 ± 0.01 | 1,997 ± 19 | 3.1% |
| (b) pay up to 1.5x when money waits | 0.56 ± 0.01 | 0.83 ± 0.00 | 3.03 ± 0.03 | 5,145 ± 64 | 5.1% |
| (c) shortfall carried | 0.58 ± 0.00 | 0.85 ± 0.00 | 3.37 ± 0.06 | 5,714 ± 82 | 0.0% |
| (b) + (c) | 0.57 ± 0.00 | 0.84 ± 0.00 | 3.21 ± 0.03 | 5,555 ± 48 | 0.0% |
| (a) + (b) + (c) | 0.62 ± 0.00 | 0.87 ± 0.00 | 3.96 ± 0.02 | 7,157 ± 160 | 0.0% |

#### 4. Sustainability: what burns must cover

The bounty market itself runs about 823 checks a cycle; funders spend about $9,702 a cycle on fixes. Each cell: pool investors' value back per coin spent at the flow-clearing price p* (their tokens per coin × p*), with p* in brackets.

| Payout fee | Margin a check | 0 outside checks a cycle | 10,000 outside checks a cycle | 100,000 outside checks a cycle | 1,000,000 outside checks a cycle | Outside checks a cycle for pool investors to get back 50 % | …100 % (break even) |
|---|---|---|---|---|---|---|---|
| burned (≤ 20 %) | $0.01 | 23% ($0.267) | 24% ($0.284) | 35% ($0.408) | 133% ($1.563) | 238,502 | 695,910 |
| burned (≤ 20 %) | $0.05 | 23% ($0.273) | 29% ($0.346) | 79% ($0.926) | 571% ($6.698) | 47,042 | 138,523 |
| burned (≤ 20 %) | $0.1 | 24% ($0.280) | 36% ($0.417) | 134% ($1.573) | 1118% ($13.115) | 23,109 | 68,850 |
| burned (≤ 20 %) | $0.25 | 25% ($0.299) | 53% ($0.627) | 299% ($3.512) | 2759% ($32.368) | 8,750 | 27,046 |
| to the next pool | $0.01 | 3% ($0.033) | 4% ($0.045) | 13% ($0.159) | 106% ($1.301) | 456,302 | 938,287 |
| to the next pool | $0.05 | 3% ($0.037) | 8% ($0.100) | 55% ($0.671) | 522% ($6.379) | 90,584 | 186,981 |
| to the next pool | $0.1 | 3% ($0.042) | 14% ($0.169) | 107% ($1.311) | 1041% ($12.727) | 44,870 | 93,068 |
| to the next pool | $0.25 | 5% ($0.058) | 31% ($0.375) | 264% ($3.230) | 2599% ($31.771) | 17,441 | 36,720 |

## Limits
- **The price is the price use supports (p\*), or an input.** Speculation and holding aren't modelled. The returns at fixed prices are the tokens per coin times that price.
- **Each repository's fixes are independent draws.** Healthy repositories don't grow, and a stall is a fixed drop at cycle 13.
- **Margins are burned in full; checks are otherwise at cost** (#182's entry of $3.50 for the attacker's fixes). The bounty market's check count includes registration, each submission's 3 checks, and the 3 merit judges.
- **Attackers are one team in one repository,** at #184's 5 fakes a cycle, choosing the best of a fixed set of plays; colluding judges always accept its claims.
