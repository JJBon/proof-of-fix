# Per-repository tokens and the self-farmer, v2: per cycle and the hybrid (proof-of-fix#177; 2026-11-08)

**Commands:** `python3 -m pof.sim.repotokens --cycle --seeds 20 [--manufactured 200]` and `python3 -m pof.sim.repotokens --hybrid --seeds 20` (about a minute each). Simulation only (rule 1). It builds on [v1](repotokens-v1.md), which also explains how to read the numbers: **"farming pays once honest funders get back X in tokens"**, so a higher X is safer.

**The owner's questions (2026-11-07):**
- What if tokens are shared per cycle rather than minted per fix? Judges would compare a cycle's fixes and split one pool by merit (impact, design, work), paid a flat fee for judging, never a share.
- Does a flood of cheap AI work pay, when every check is paid for?
- Do bug reports on approved fixes refine the judges?

**The new attacker:** a farmer that manufactures importance, a trivial fix presented as a $200 bug. The judges value it at $200 unless they see through it, which they do with probability **"caught"**. That rate is an input here, not a result.

## Summary
1. **Per cycle beats per fix on trivial work.** With usage evidence (5 distinct reputable outside funders in the last 4 cycles), farming trivial fixes pays only once honest funders get back **97 %**. A flood of cheap fixes earns a cheap share, and each one costs its checks.
2. **Faked importance still defeats it:** **6 %**. The judges' comparison is only as good as their reading of importance. Needing more funders, renewing reputation each quarter, or vesting merit on realised reach doesn't help (4-9 %). Vesting also costs honest projects about 11 % of their tokens.
3. **The hybrid works, but only with a fee.** Each fix's merit is capped by the bounty coin pledged by accounts other than its solver, so claimed importance needs real coin behind it. A fee on that coin is lost to the farmer each time. At a **20 % fee and 80 % caught it holds at 86 %**; at a 10 % fee it needs 90 % caught (83 %). With no fee the cap does nothing, because the coin comes back to the farmer as the solver.
4. **The fee and the judges only work together.** A 20 % fee with judges who catch nothing holds at 27 %; judges catching 90 % with no fee, 21 %.
5. **Faking a bigger bug doesn't help the farmer.** At $500 the results match $200 (86 % at a 20 % fee and 80 % caught), because the cap makes every claimed dollar cost the fee. The farmer's best play is $20-100 of coin a bounty and a smaller share.
6. **What it costs honest projects** is the fee on what they fund. In return they keep 81-91 % of the pool against the farmer's best attack.

## Decision (owner, 2026-11-08)
**No per-repository tokens:** the simulations didn't show they're worth it. Every per-repository rule is either broken (a fixed emission) or only as safe as the judges' reading of importance, which is what the protocol's one token already depends on. The per-cycle split and the hybrid below are rules for #58's one protocol token, shared by every repository, so they still apply.

## Recommendation (for the owner)
- **The rule for the contract:** a per-cycle split by the judges' merit, each fix's share capped by outside bounty coin, and a **10-20 % fee on bounty payouts**, burned or returned to the pool and paid to no one. Today the contract has no fee (`pof.params` CONTRACT), so this is a spec change before any code.
- **It rests on one number nobody has measured: how often AI judges see through faked importance.** The contract's design can't be validated by simulation alone; it needs **a judge test with real data**: real models valuing real fixes, some honestly described and some inflated by an attacker model, against a pass mark of 80 % caught at a 20 % fee (90 % at 10 %). That test calls real models, so it gets a plan, the owner's approval of its hash and hard spending limits, like B1 (#85).
- **Reports on approved fixes can refine the judges**, as the owner suggested: each valid bug report on a judged fix is a labelled case for that test, so the measured rate improves with use.

## Results (20 seeds, a year)

### The hybrid against the plain per-cycle split: faked $200 bugs, by fee and the share caught
| Market fee on bounty coin | Split | 0% seen through | 50% seen through | 80% seen through | 90% seen through | Trivial fixes only | Honest funders' cost (fee on what they fund) |
|---|---|---|---|---|---|---|---|
| 0% | plain per cycle | 6% | 8% | 14% | 22% | 77% | 0% |
| 0% | hybrid: capped by outside coin | 5% | 8% | 14% | 21% | 74% | 0% |
| 5% | plain per cycle | 6% | 8% | 15% | 23% | 82% | 5% |
| 5% | hybrid: capped by outside coin | 12% | 20% | 38% | 58% | 83% | 5% |
| 10% | plain per cycle | 6% | 9% | 16% | 25% | 87% | 10% |
| 10% | hybrid: capped by outside coin | 18% | 29% | 55% | 83% | 87% | 10% |
| 20% | plain per cycle | 6% | 9% | 17% | 27% | 97% | 20% |
| 20% | hybrid: capped by outside coin | 27% | 46% | 86% | 95% | 97% | 20% |

The last column is trivial fixes only (no manufactured importance). The farmer's best strategy at a 20 % fee and 80 % caught is 20 fixes a week with $20 of coin each and 5 socks with bought reputation; at a 10 % fee, $100 of coin each.

### Per cycle, trivial fixes (judged at about $5), the market's fees
| Per cycle, one shared pool | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Honest work's share of the pool against the farmer | Honest repositories' usage evidence | The farmer's best strategy |
|---|---|---|---|---|---|---|
| usage needs 1 reputable outside funder | **92%** | 0.2453 ± 0.0120 | 3.80 | 95% | 100% | 20 fixes a week, 1 socks with bought reputation |
| usage needs 5 distinct reputable funders | **97%** | 0.2572 ± 0.0125 | 3.80 | 88% | 93% | 50 fixes a week, 5 socks with bought reputation |
| usage needs 20 distinct reputable funders | **70%** | 0.1866 ± 0.0142 | 3.80 | 77% | 49% | 50 fixes a week, 20 socks with bought reputation |
| 5 funders, reputation earned in the last quarter | **38%** | 0.1040 ± 0.0130 | 3.77 | 71% | 35% | 20 fixes a week, 5 socks with bought reputation |
| 5 funders; merit vests over 13 weeks on realised reach | **87%** | 0.2598 ± 0.0127 | 3.38 | 88% | 93% | 50 fixes a week, 5 socks with bought reputation |
| 5 funders; merit vests over 26 weeks on realised reach | **86%** | 0.2598 ± 0.0127 | 3.35 | 88% | 93% | 50 fixes a week, 5 socks with bought reputation |

### Per cycle, faked $200 bugs that the judges never see through, the market's fees
| Per cycle, one shared pool | Farming pays once honest funders get back, in tokens | Farmer's break-even price ($ a token) | Honest: tokens per $ funded | Honest work's share of the pool against the farmer | Honest repositories' usage evidence | The farmer's best strategy |
|---|---|---|---|---|---|---|
| usage needs 1 reputable outside funder | **4%** | 0.0103 ± 0.0003 | 3.80 | 78% | 100% | 5 fixes a week, 1 socks with bought reputation |
| usage needs 5 distinct reputable funders | **6%** | 0.0168 ± 0.0005 | 3.80 | 57% | 93% | 10 fixes a week, 5 socks with bought reputation |
| usage needs 20 distinct reputable funders | **9%** | 0.0231 ± 0.0011 | 3.80 | 48% | 49% | 10 fixes a week, 10 socks with bought reputation |
| 5 funders, reputation earned in the last quarter | **6%** | 0.0168 ± 0.0012 | 3.77 | 48% | 35% | 5 fixes a week, 2 socks with bought reputation |
| 5 funders; merit vests over 13 weeks on realised reach | **6%** | 0.0175 ± 0.0005 | 3.38 | 54% | 93% | 10 fixes a week, 5 socks with bought reputation |
| 5 funders; merit vests over 26 weeks on realised reach | **6%** | 0.0175 ± 0.0005 | 3.35 | 54% | 93% | 10 fixes a week, 5 socks with bought reputation |

### For comparison: minting per fix (R1, v1) against faked $200 bugs, by the share caught
| Fees | R1 at 0 % caught | 50 % | 80 % | 90 % |
|---|---|---|---|---|
| market (20 % fee) | 22% | 40% | 77% | 87% |
| contract (no fee) | 2% | 3% | 7% | 12% |

## Limits
- **The share caught is assumed, not measured.** Everything above is conditional on it; the judge test with real data measures it.
- **Each faked bug is independent:** a judge that misses one style of inflation may miss all of them, which would make "caught" lower against a farmer who finds that style.
- **The farmer's development cost is zero** and it pays no reputation it doesn't need, so the break-even is its best case.
- **Usage evidence counts funders,** not real users or dependents; a farmer that buys reputation for its socks gets full evidence (the model charges it $250 a sock).
- **One farmer.** Several colluding farmers, or a farmer who is also a judge, aren't modelled here (#141's open-validator simulation covers judges' collusion).
