# Market acceptance run v3: non-transferable reputation, proof-of-fix#37 (2026-10-24)

**Command:** `python3 -m pof.sim market summary --seeds 100 --sweep-seeds 20 > reports/acceptance-market-v3.json` (verdicts on 100 seeds, sweeps on 20; about 12 minutes). It reproduces byte for byte. Market v2 ([`acceptance-market-v2.md`](acceptance-market-v2.md)) stays as the baseline.

**What's new:** a score per account and role, built only from outcomes on the ledger. It's recomputable and can't be transferred. Trust derived from the score is used three ways:
- matching weights each pledger by its funder trust;
- the treasury ranks issues by value × the reporter's trust;
- a solver's bond falls with its trust, down to half.

Three changes the simulation forced (design D6):
- points are earned at **acceptance**, not full payment;
- **negative scores push trust below the floor**;
- match farming is judged by the **farmer's cost per own fix**.

## Result

| Hunting elasticity (100 seeds) | Verdict |
|---|---|
| **0.5** (default) | ✅ **every criterion passes** |
| 0 | ✅ every criterion passes |
| 1 | ❌ bidding your cost isn't best: a 1.5× bluffer gains (it passed in v2) |

## v2 vs v3 (default, 100 seeds)

| Criterion | Market v2 | **Market v3** |
|---|---|---|
| **Crowd-out at 50 % junk detection** | ❌ 64 % | ✅ **91 %** of real issues still funded |
| **Match farming** (4 fake accounts) | loses narrowly, −27 ± 13 | ✅ **shut down:** in all 100 seeds the fake accounts never got an issue funded (new accounts draw 1/16 of a proven funder's match) |
| **Reputation farmer** (trust on small jobs, then walks away) | (new) | ✅ loses **−232 ± 11** |
| **Proven solvers lock less bond** | (new) | ✅ **−4.4 ± 0.6** credits per job, against no discount |
| Discoverers earn | ✅ +8.9 | ✅ +7.3 |
| Matching gets pledged issues funded | ✅ +0.69 | ✅ +0.44 (fake accounts no longer draw matching) |
| Crowd-out at normal detection | ✅ 91 % | ✅ 94 % |
| Flood / no-shows / spam lose | ✅ | ✅ −495 / −401 / −119 |
| Bidding your cost is best | ✅ | ✅ (bluffing +12 ± 13); ❌ at elasticity 1 |
| Owner can't gain | ✅ | ✅ −1 ± 3 |
| Honest solvers earn | ✅ +48 | ✅ **+32** |
| Validators earn | ✅ +30 | ✅ +25 |
| Collusion | ring of 4 gains | rings of 2–4 don't; **a ring of 6 gains** (+72 ± 32) |

**Why honest solvers earn less:** lower bonds lower the expected penalties, so break-even prices fall, and with competition, so do prices. Proven solvers' savings pass to pledgers.

## Collusion: what to read into it
- **At 100 seeds:** a ring of 2 is +32 ± 23 and a ring of 3 +32 ± 24, both not significant; a ring of 4 is −2 ± 33; **a ring of 6 is +72 ± 32, which is significant.**
- **At 20 seeds, the sweeps flag a ring of 2 at most settings** ("collusion measured"). With the discount off (40 seeds) it's +20 ± 32, against +58 ± 35 with it.
- **A plausible mechanism:** a ring funnels its wins through one member, who earns trust and the half bond sooner than honest solvers who share the work. The evidence isn't conclusive.
- **Next step:** a reserve price below the cap (planned), and possibly capping the trust one account can earn per release.

## Bluffing at elasticity 1
A 1.5× bluffer gains when hunters respond strongly to pay. It passed in v2. With discounted bonds, the honest break-even price assumes smaller penalties, while vigorous hunting makes the real penalties larger. So honest solvers under-price risk in that regime. It's the same mechanism as in v1, now through the bond discount.

**Next step:** let a solver's break-even use its realised failure rate (from its own record), rather than the default detection assumption.

## Sweeps (20 seeds)

"Collusion measured" (a ring of 2 at 20 seeds) appears in most default rows; read it with the 100-seed result above. The other failures:

| Sweep | Values | Other failures |
|---|---|---|
| Trust floor | 0.1 / **0.25** / 0.5 | proven solvers' bond saving not significant at 0.1 and 0.5 |
| Bond discount | 0 / **50 %** / 75 % | at 0 no saving (as expected); 75 % passes everything |
| Bond (stake share) | 20 % / **40 %** / 60 % | at 20 %, honest mistakes pay |
| Matching share | 0 / **50 %** / 100 % | at 0 matching can't help; at 100 % an attacker no longer loses and bonds don't fall |
| Cost per line | 0.5 / **1** / 2 | at 2, the bond saving isn't significant |
| Market fee | 10 % / **20 %** / 30 % | at 10 %, bluffing pays |
| Pledged share | 20 % / **40 %** / 60 % | at 20 %, the bond saving isn't significant |
| Finder's fee, issue stake, delivery days, junk detection | | none besides the ring of 2 |

## Still open
1. **Collusion:** a ring of 6 at 100 seeds, and a possible ring-of-2 effect from reputation. A reserve price is next.
2. **Bluffing at elasticity 1:** break-even from a solver's own record.
3. **No decay:** old trust never expires.
