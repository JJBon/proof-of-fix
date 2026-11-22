# Award modes compared, v2: the race passes everything (proof-of-fix#60, 2026-10-25)

**Command:** `python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v2.json` (about 20 minutes). The baseline is modes v1 ([`acceptance-modes-v1.md`](acceptance-modes-v1.md)).

**What changed since v1** (the owner's decisions, design D9):
1. **A failed fix can't be resubmitted:** an AI similarity check rejects it unchecked from any account (recognized 90 % of the time). Its author may appeal once, at its own cost, to the second jury.
2. **The poster's registration fee is refunded with the finder's fee when the bounty is paid.** A bundle's parts' reporters share the finder's fee.
3. **A rising price:** a bounty opens at 50 % of its funds, rising 10 % a day until the first attempt locks it. The rest is refunded when it's paid.
4. **Criteria the race can't apply:** a no-show mustn't gain, and a reputation farmer mustn't earn more than an honest solver. Their attacks need an assignment the race doesn't have.

## Result

| Mode (100 seeds) | v1 | **v2** |
|---|---|---|
| auction | ✅ every criterion | ✅ every criterion (unchanged) |
| **race** | ❌ 4 failures | ✅ **every criterion passes** |
| claim | ❌ 2 failures | ❌ 2 (discoverers earn +0.06 ± 0.21; proven solvers lock less) |

**The race becomes the default** (the owner's choice: "the first valid PR wins"). The auction stays as `--award-mode auction` to compare with and to reproduce earlier runs; the claim stays as a comparison.

## What each mode costs and buys (100 seeds)

| | auction | race v1 | **race v2** | claim v2 |
|---|---|---|---|---|
| Honest solvers' net per run | +17 ± 3 | +154 ± 4 | **+68 ± 3** | +25 ± 6 |
| Wasted effort | 29 % | 53 % | **51 %** | 38 % |
| **Funders' cost per paid bounty** | 60 ± 2 | 177 ± 5 | **116 ± 3** | 87 ± 5 |
| Mean price | 70 | 173 | 115 | 121 |
| Bounties paid / unsolved per run | 25.5 / 62.7 | 33.5 / 47.7 | **32.3 / 48.6** | 28.0 / 51.0 |
| Days to fix | 20.6 | 11.4 | **13.0** | 15.4 |
| Accepted fixes at the quality bar | 89 % | 97 % | **97 %** | 97 % |
| Good fixes wrongly rejected | 11.3 % | 10.3 % | 11.4 % | 10.6 % |
| Reporters' net per run | +4.5 | −0.9 | **+1.4 ± 0.2** | +0.1 |

**The rising price works:** funders' cost per fix falls by a third (177 to 116) and the mean price from 173 to 115. The gains hold:
- **26 % more bounties fixed** than the auction (32.3 against 25.5);
- **in 13 days instead of 21;**
- **at 97 % quality against 89 %.**

Honest solvers still earn four times the auction's.

**The attacks on the race all fail:**

| Attack (race v2, against its honest twin) | Gain |
|---|---|
| Variant from a second account | +6.9 ± 15.2, **not significant** (v1: +103 ± 26) |
| Padded tests | −130 ± 16 |
| Inflated estimates | −351 ± 28 |
| Rings of 2 / 3 / 4 / 6 | +8 / −11 / +2 / −1, none significant: there's no price to bend |
| Reputation farmer | +8.4 ± 5.6, below an honest solver's +75 |
| Every checking attack (#43, #47) | loses, as in the auction |

## Sweeps (race, 20 seeds)

| Sweep | Finding |
|---|---|
| **Attempt cost** (cost per line 0.1 / 0.5 / 1 / 2) | Honest solvers +235 / +112 / +68 / +43. At double the cost, discoverers stop earning (the only flag) |
| Gate accuracy (0.02 / 0.05 / 0.10) | Every criterion passes; little change |
| **Gate bar** (0.6 / 0.7 / 0.8) | 0.6 and 0.7 pass. **At 0.8, honest solvers barely earn (+9) and waste is 70 %:** the bar must fit the solvers' real quality |
| Registration fee (0.5 / 2 / 5) | 0.5 and 2 pass; at 5, discoverers stop earning |
| Top-ups (0 / 10 % a week) | No effect: the rising price does that job |

## Still open

- **Wasted effort stays at about half:** the cost of racing. Honest solvers earn anyway, and #58's solution-attached bounties give coders a way to work without racing.
- **Before the contract (#56):**
  - a refundable deposit to start an attempt: fake attempts would otherwise scare competitors off, or lock the rising price low;
  - an appeal for fixes rejected as duplicates of someone else's failed one, since independent fixes for a small bug can look alike;
  - deciding what "solved" means on-chain (a merge and release, or the gates alone).
