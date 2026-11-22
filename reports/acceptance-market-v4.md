# Market acceptance run v4: a reserve price, a per-release trust cap, and pricing from a solver's record, proof-of-fix#40 (2026-10-24)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-market-v4.json` (verdicts on 100 seeds, sweeps on 20; about 13 minutes). It reproduces byte for byte. The reserve comparison is `python3 scripts/reserve_ablation.py > reports/acceptance-market-v4-reserve.json`. Market v3 ([`acceptance-market-v3.md`](acceptance-market-v3.md)) stays as the baseline.

**What's new:**
- **A reserve price:** no price is above 75 % of the bounty's price cap. Bids above the reserve are void and lose their fee, and a lone bid is paid the reserve, not the whole cap.
- **A trust cap:** an account earns at most 1 positive reputation point per role per release. Failures still cost in full.
- **Solvers price risk from their own record:** their failed deliveries and their slashes or clawbacks, with the default assumption counted as 5 trials.
- **A stricter collusion criterion:** a ring of **any** size (2, 3, 4 or 6) gaining significantly fails, not only a ring of 2.

## Result

| Hunting elasticity (100 seeds) | v3 | **v4** |
|---|---|---|
| **0.5** (default) | ✅ passes, except a ring of 6 gains | ✅ **every criterion passes** |
| 0 | ✅ | ✅ every criterion passes |
| 1 | ❌ a 1.5× bluffer gains | ✅ **every criterion passes** |

## v3 vs v4 (default, 100 seeds)

| Criterion | Market v3 | **Market v4** |
|---|---|---|
| **Ring of 6** | ❌ +72 ± 32 | ✅ **+19 ± 25** |
| Rings of 2 / 3 / 4 | +32 / +32 / −2 | −18 / 0 / +10, none significant |
| **Bluffing** (1.5×), default / elasticity 1 | +12 ± 13 / ❌ gains | ✅ −7 ± 12 / −1 |
| Lowballing | −86 | −88 |
| Honest solvers earn | +32 | ✅ **+19** (lower, see below) |
| Validators earn | +25 | ✅ +19 |
| Discoverers earn | +7.3 | ✅ +5.3 |
| Proven solvers lock less bond | −4.4 ± 0.6 | ✅ −3.4 ± 0.6 per job |
| Reputation farmer | −232 | ✅ −244 |
| Match farming | shut down | ✅ shut down (fakes never got an issue funded) |
| Matching gets pledged issues funded | +0.44 | ✅ +0.43 |
| Crowd-out (normal / 50 % detection) | 94 % / 91 % | ✅ 95 % / 90 % |
| Flood / no-shows / spam lose | −495 / −401 / −119 | ✅ −498 / −404 / −76 |
| Owner can't gain | −1 ± 3 | ✅ 0 ± 2 |
| Bounties paid / closed unsolved, per run | 40 / 48 | 34 / 53 |
| Mean price (price ÷ cost) | 71 (1.66×) | 60 (1.67×) |

## What the reserve buys, and what it costs

This compares the three rules on 100 seeds at each elasticity. The trust cap and record pricing are on in every row.

| Reserve | Ring of 6 (elasticity 0 / 0.5 / 1) | Bluffer | Honest solvers | Bounties paid / unsolved |
|---|---|---|---|---|
| **75 %** (default) | +50* / **+19 ± 25** / +6 | −7 ± 12 | +19 | 34 / 53 |
| 90 % | — / +46 ± 34 / — | +29 ± 16 | +27 | 37 / 50 |
| none (100 %) | +49 ± 31 / +59 ± 32 / +61 ± 34 | −7 ± 15 | +34 | 39 / 50 |

\* The elasticity verdicts keep only means; both pass, so neither is significant.

- **The trust cap and record pricing fixed bluffing and the ring of 2,** with or without the reserve: without a reserve, every criterion still passes at all three elasticities.
- **Without the reserve, the ring of 6 passes by a hair.** It's +59 ± 32 at the default (5 credits short of significance) and +61 ± 34 at elasticity 1. The reserve brings it to +19 ± 25, a robust margin. That's why it stays the default.
- **The cost:** about 5 fewer bounties paid per run (−13 %), and honest solvers earn +19 instead of +34. A lone bidder no longer takes the whole cap, so the difference stays with pledgers and the treasury as refunds.
  - 90 % is a poor middle: the ring isn't contained (+46), and bluffing comes close to paying (+29 ± 16).
- **Honest solvers are still paid well above their cost:** the mean price is 1.67× cost, and their returns net of effort are significantly positive.

## Sweeps (20 seeds)

At 20 seeds the standard errors are about 2.2 times those at 100 seeds, so a single significant ring is a flag to recheck at 100 seeds, not a verdict. The rows that fail:

| Sweep | Value | Fails |
|---|---|---|
| Reserve | 50 / **75** / 90 / 100 % | none. Bounties paid 28 / 35 / 36 / 40 against unsolved 58 / 54 / 51 / 48; honest solvers +10 / +24 / +24 / +37 |
| Trust points per release | **1** / 2 / 100 | none. The bond saving grows with the cap (−3.9 / −4.8 / −5.0) |
| Cost per line | 0.5 | bluffing pays (+69): with cheap work the reserve is far above cost, and a bluff still fits under it |
| Pledged share | 20 % / 60 % | a ring of 4 (+96) / the bond saving isn't significant |
| Bond (stake share) | 20 % / 60 % | a ring of 6 (+112 / +95); at 60 % also the bond saving |
| Delivery days | 7 | a ring of 2 (+83); the bond saving |
| Market fee | 30 % | the owner gains |
| Finder's fee | 2.5 % / 10 % | a ring of 4 (+103), and the bond saving / the bond saving |
| Matching share | 0 | matching can't help (as expected) |
| Trust floor | 0.5 | a ring of 6 (+187); match farming pays |
| Bond discount | 0 | no saving (as expected) |
| Treasury junk detection, issue stake | | none |

Defective work: attackers (spam, flood) lose on every defective contribution, and honest mistakes don't pay (−12.0 ± 0.4 per defective contribution, n = 10,931).

## Still open
1. **Rings away from the defaults:** the ring of 6 is contained at the defaults, but several 20-seed sweeps flag rings of 4 or 6. Rings are the weakest point, and the next lever is identity, not price (#15).
2. **Bluffing at cheap work (cost per line 0.5):** a reserve set as a share of the cap sits far above cost when work is cheap. A reserve from a cost estimate would close it (the AI pricing step, #15).
3. **No decay:** old trust never expires.
4. **The reserve's cost:** 13 % fewer bounties paid. Worth revisiting once rings are handled another way.
