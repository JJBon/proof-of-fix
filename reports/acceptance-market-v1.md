# Market acceptance run v1: the bounty market, proof-of-fix#15 (2026-10-24)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-market-v1.json` (verdicts on seeds 1–100, sweeps on 1–20; 8 weeks each, drained until every job is paid or lost; about 6 minutes). It reproduces byte for byte.

**What's being tested:** pay by bounty instead of the legacy pool split by lines.
- Pledges, or a small treasury budget, fund bounties.
- Solvers bid for the job in sealed second-price rounds, before building anything (bid first, build after, design D9).
- The assigned solver delivers within 14 days with its stake as a bond.
- Payment comes on release through the same enforcement layer that v5 validated.
- Each solver's development cost counts against its return.

## Result

| Hunting elasticity (100 seeds) | Verdict |
|---|---|
| **0.5** (default) | ✅ **every criterion passes** |
| 0 | ❌ bidding your cost isn't always best: a 1.5× bluffer gains +83 ± 20 |
| 1 | ❌ the same, +42 ± 17 |

### The criteria at the default (100 seeds; return net of effort, per actor over 8 weeks)

| Criterion | Result |
|---|---|
| Honest solvers earn more than their cost | ✅ **+67.0 ± 2.2** |
| Validators earn | ✅ +39.2 ± 0.4 |
| Bidding your cost is best | ✅ bluffing −3.2 ± 17.3; lowballing −104.6 ± 19.6 |
| No-shows lose | ✅ −369 ± 7 |
| Spam solvers lose | ✅ −163 ± 12; their defective work −8.4 ± 0.6 per contribution |
| A treasury flood loses | ✅ −254 ± 18 (but see "Costs") |
| Collusion | ✅ no ring of 2 or 3 gains; **a ring of 4 gains +108 ± 42** (6: +10 ± 42) |
| Owner can't gain by defecting | ✅ −8 ± 4 |
| Honest mistakes don't pay | ✅ solvers' defective work −7.9 ± 0.5 per contribution |
| Pledges pay only for released fixes | ✅ in every run (checked against the ledger) |
| Treasury within budget | ✅ in every run |
| Conservation | ✅ |

## What the market looks like (base scenario, mean per run)
- **Issues:** about 119 arrive. 47 are pledged and 72 are funded by the treasury; almost none go unfunded.
- **Bounties:** 56 paid; 63 still open at the end (no solver could do them under the cap).
- **Solvers:** 203 bids, 68 jobs assigned, 62.5 delivered, 6 deliveries failed.
- **Price:** the mean price is 83 credits, or **1.74 × the winner's build cost**. The margin pays for risk (bonds and slashes) and for a thin market: 12 solvers, 3 jobs each at once.
- **Treasury spend:** 9,558 per run.
- **Returns:** honest solvers +70, validators +34, hunters +19, owner +119. Pledgers spend 158 each; their value is the fixes, which the model doesn't price.

## The failures and costs to know

**1. Bluffing pays when hunters don't respond to pay as assumed** (elasticity 0 and 1).
- An honest solver bids its break-even price: build cost plus expected penalties, over the chance of being paid (design D10), using its own rates.
- In a second-price round, overbidding can only pay if that estimate is too low, so the bluffer avoids jobs that really lose money.
- **Hypothesis:** the estimate misjudges how often defects are caught when hunting behaves differently.
- **Next step:** publish each solver's realised failure and slash rate (the non-transferable reputation in #15). Solvers can then price risk from their record, and pledgers can see it.

**2. A ring of 4 colluding solvers gains** (+108 ± 42), a quarter of the solver pool. A ring stays out of rounds so its member is paid the next outsider's price: second price's known weakness.
- Rings of 2 and 3 don't gain, and 6 isn't significant, so the threshold is noisy.
- **Next steps:** a reserve price below the cap (the cap is what a lone bidder gets), and more solvers per bounty (the market is thin).

**3. A treasury flood loses money but crowds out real work.** With 2 junk issues a day and the AI treasury spotting 85 % of them:
- junk bounties tie up about 4,100 credits of the budget per run;
- **about 98 real issues per run go unfunded**, against almost none without the flood.

The flooder loses (its junk deliveries are caught and its bonds slashed), but the project loses fixes.
- **Next steps:** a per-reporter quota for treasury proposals, and better junk detection. The 95 % detection sweep doesn't report crowd-out yet; it should.

**4. The 40 % bond is needed.** At 20 %, the flood no longer loses (+20 ± 76), and honest solvers' defective work pays. At 60 %, everything passes; no-shows lose more and spam less.

## Sweeps (20 seeds)

| Sweep | Values | Passes |
|---|---|---|
| Cost per line (credits) | 0.5 / **1** / 2 | ✅ all. Solvers +119 / +66 / +31 |
| Pledged share | 20 % / **40 %** / 60 % | ✅ all (a ring of 4 gains at 20 %) |
| Treasury junk detection | 50 % / **85 %** / 95 % | ✅ all (crowd-out not yet measured) |
| Bond (stake share of the cap) | 20 % / **40 %** / 60 % | ❌ / ✅ / ✅ |
| Delivery days | 7 / **14** / 28 | ✅ all. No-shows lose more with shorter deadlines |
| Market fee | 10 % / **20 %** / 30 % | ✅ all. Solvers +98 / +66 / +56 |

## Against the legacy pool (v5)
- **The splitting failure is gone by design.** Pay is per job, not per line, so nothing can be split or padded.
- **The enforcement results carry over:** defective work loses, griefing and the owner were tested, and validators earn. They're smaller in absolute terms, since bounties are smaller than the legacy pool's rewards.
- **Pricing is now set by competition,** not a formula.

## Recommendation
**Don't make the market the default yet.** It passes at the default assumption, but fails at the other two, and three costs are open: bluffing under other hunting assumptions, rings of 4, and treasury crowd-out.

**Next steps, in order:**
1. **Reputation** (#15): published per-solver track records, for pricing risk and for the AI treasury.
2. **A reserve price and per-reporter treasury quotas.**
3. **The AI jury** (#15), whose verdicts junk detection and review would use.
