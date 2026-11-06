# Award modes compared, v3: nothing is free (proof-of-fix#64, 2026-10-26)

**Command:** `python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v3.json` (about 23 minutes). The baseline is modes v2 ([`acceptance-modes-v2.md`](acceptance-modes-v2.md)).

**What changed since v2** (the owner's answers on the contract pitfalls, #56):
1. **Starting an attempt costs 0.5,** never refunded. The first paid attempt locks the rising price.
2. **Arriving late costs:** a submission after the bounty is won pays the evaluation fee (2), unchecked.
3. **A fix rejected as someone else's failed fix can be appealed** to an AI jury of 3, one per provider. If it's found independent, it's checked like any submission.
4. **New scenarios:**
   - the fake attempter: two sock accounts start paid attempts that are never submitted, so its bounties look crowded;
   - honest fixes falsely flagged as duplicates (5 % of the time on bounties with a failed fix).

## Result

| Mode (100 seeds) | v2 | **v3** |
|---|---|---|
| **race** (default) | ✅ every criterion | ✅ **every criterion passes** |
| auction | ✅ | ✅ |
| claim | ❌ 2 | ❌ the same 2 (a comparison only) |

| Race | v2 | **v3** |
|---|---|---|
| Honest solvers' net per run | +68 ± 3 | **+73 ± 3** |
| Wasted effort | 51 % | 51 % |
| Funders' cost per paid bounty | 116 ± 3 | 121 ± 3 |
| Bounties paid / unsolved per run | 32.3 / 48.6 | 32.7 / 47.6 |
| Days to fix | 13.0 | 12.9 |
| Accepted fixes at the quality bar | 97 % | 97 % |
| Honest fixes falsely flagged as duplicates, per run | (none) | 0.67, **all of them won on appeal** |
| Late submissions per run | (free) | 2.7 |

**The new rules cost honest solvers nothing measurable,** and every falsely flagged honest fix won its appeal.

## Attacks on the race (against their honest twins)

| Attack | Gain |
|---|---|
| **Fake attempts** (two socks) | +12.9 ± 15.6: doesn't gain (see below) |
| Variant from a second account | −6.0 ± 14.9 |
| Padded tests | −162 ± 21 |
| Inflated estimates | −309 ± 28 |
| Rings of 2 / 3 / 4 / 6 | +3 / −28 / −27 / −9, none significant |

**Fake attempts net out near zero:** their fees, and the rivals they scare off, roughly cancel out. As first specified ("must lose"), the race failed this criterion. Probes on 30 seeds:
- **a fee of 2** gives −12 ± 24, still not a clear loss, and honest solvers fall 14 %;
- **counting only attempts by solvers with earned reputation** gives −27 ± 20, but honest solvers lose 71: they stop seeing real rivals and crowd in.

**The owner chose:** a fee of 0.5, every attempt counted, and fake attempts judged like the other attacks, so they mustn't gain ("rigging is paying without benefit"). They don't.

## Sweeps (race, 20 seeds)

| Sweep | Honest solvers | Bounties paid | Finding |
|---|---|---|---|
| **Attempt fee** 0.1 / 0.5 / 2 | +75 / +71 / +61 | 34.4 / 34.3 / 34.3 | every value passes; 2 costs honest solvers 14 % |
| **False duplicates** 0 % / 5 % / 20 % | +72 / +71 / +67 | 33.8 / 34.3 / 33.6 | every value passes; at 20 %, 3.1 of 3.2 flagged fixes per run win on appeal |
| Duplicate appeal jury 3 / 5 | +71 / +66 | 34.3 / 33.8 | both pass; 5 costs more in verdict fees |
| Attempt cost (cost per line) 0.1 / 0.5 / 1 / 2 | +239 / +112 / +71 / +34 | 60 / 44 / 34 / 22 | at double the cost, discoverers stop earning |
| Gate bar 0.6 / 0.7 / 0.8 | +82 / +71 / +13 | | at 0.8, honest solvers barely earn |

## Next

The race's rules are settled for the contract (#56):
- a basket of coins plus the token per bounty (#59);
- solved = merged;
- withdraw-only safety mode;
- prompt-injection defenses;
- these fees and appeals.
