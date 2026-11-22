# Market acceptance run v2: discoverers and funders, proof-of-fix#34 (2026-10-24)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-market-v2.json` (verdicts on 100 seeds, sweeps on 20; about 8 minutes). It reproduces byte for byte. Market v1 ([`acceptance-market-v1.md`](acceptance-market-v1.md)) stays as the baseline.

**What's new:**
- Issue stakes with a 5 % finder's fee for discoverers.
- Quadratic matching from half the treasury budget for funders.
- Refunds in proportion to what each source put in.
- **Unsolved bounties close** after 4 empty rounds (a rule the simulation forced, design D6).

## Result

**Every criterion passes at hunting elasticity 0, 0.5 and 1** (100 seeds). That's with the funders' criterion amended by the owner (2026-10-24, design D7) to "matching gets more pledged issues funded and fixed".

**Funders:**
- With matching, **85.7 % of pledged bounties reach their target, against 16.8 % without** (+0.689 ± 0.007).
- That's **14.2 ± 0.4 more pledged bounties fixed and paid per run.**
- The cost per paid bounty drops 7.8 ± 4.4 credits (reported, not judged). Funders pay for many more fixes, so the cost *per* fix barely moves; that's why the first criterion was the wrong measure.

## v1 vs v2 (default, 100 seeds)

| Criterion | Market v1 | Market v2 |
|---|---|---|
| **Discoverers earn** | (unpaid) | ✅ **+8.9 ± 0.2** per reporter |
| Treasury flood loses | ✅ −254 | ✅ **−497** (it now stakes on its junk) |
| **Crowd-out under a flood** | about 98 real issues per run unfunded | ✅ **91 %** of real issues still treasury-funded; junk spending **840** per run (v1: 4,123) |
| Match farming doesn't pay | (n/a) | ✅ −27 ± 13 |
| Self-dealing doesn't pay | (n/a) | ✅ in every run (the finder's fee is below its own market fee) |
| Honest solvers earn | ✅ +67 | ✅ +48 (the finder's fee and closed bounties share the money) |
| Bidding your cost is best | ❌ at elasticity 0 and 1 | ✅ **at every elasticity** (bluffing +6 ± 16) |
| No-shows / spam lose | ✅ | ✅ −370 / −125 |
| Validators earn | ✅ +39 | ✅ +30 |
| Owner can't gain | ✅ | ✅ −3 ± 4 |
| **Matching gets more pledged issues fixed** | (n/a) | ✅ **17 % → 86 % funded**, +14 paid per run |
| Collusion | ring of 4 gains | **ring of 4 still gains** (+84 ± 32); rings of 2 and 3 don't |
| Pledges pay only for released fixes | ✅ | ✅ (the finder's fee included) |

## What the market looks like (mean per run)
- **Issues:** 48.6 pledged, 66.5 treasury-funded, 6 unfunded.
- **Bounties:** 43 paid, 48 closed unsolved (funds back by input), 24 refunded (target missed).
- **Issue stakes:** 43 rewarded, 78 returned, none forfeited in the base scenario.
- **Finder's fees** 158 per run in total; matching 570.
- **Price:** 1.69 × the winner's cost (mean 73).
- **Returns:** reporters +7.9, solvers +37.6, validators +22.6, owner +85. Pledgers −28.8, their spending, now much lower thanks to matching and refunds.

## Changes the simulation forced (design D6)
- **Unsolved bounties close** after 4 empty rounds; funds return by input and the reporter's stake returns. Without this, money sat forever in bounties nobody could solve under their cap (about 63 per run in v1).
- **Pledging is gradual and partial** (1–6 backers, 50–110 % of the value), so matching has bounties to complete.
- **The match farmer's counterfactual pledges the full value from one account.**
- **A reporter's wealth includes its stakes still posted at the end.**

## Sweeps (20 seeds)

| Sweep | Values | Failures | Discoverers' return |
|---|---|---|---|
| Issue stake | 2 / **5** / 20 | none | +9.2 at each |
| Finder's fee | 2.5 % / **5 %** / 10 % | none | +4.7 / +9.2 / +16.4 (solvers +52 / +47 / +41) |
| Matching share | 0 / **50 %** / 100 % | at 0 matching can't help, and the farmer's split pledge "saves" money by never being funded; 100 % passes but leaves solvers +11 (fewer treasury jobs) | |
| Treasury junk detection | 50 % / **85 %** / 95 % | **crowd-out fails at 50 %** (64 %) | |
| Cost per line | 0.5 / **1** / 2 | at 2, the owner criterion (20 seeds; to confirm) | |
| Pledged share, bond, delivery days, market fee | as in v1 | none | |

## Still open
1. **A ring of 4 gains:** a reserve price below the cap, and a thicker market.
2. **Confirm** the owner criterion at 2 credits per line on 100 seeds.
3. **Crowd-out depends on junk detection** (it fails at 50 %): the AI jury and reputation.
4. **Next:** reputation (solvers, reporters, funders), which would also weight matching by trust.
