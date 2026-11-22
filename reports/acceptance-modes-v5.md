# Award modes compared, v5: fixes from the contract review (proof-of-fix#56, 2026-10-27)

**Command:** `python3 -m pof.sim market modes --seeds 100 --sweep-seeds 20 > reports/acceptance-modes-v5.json` (about 25 minutes). The baseline is modes v4 ([`acceptance-modes-v4.md`](acceptance-modes-v4.md)).

**What changed since v4** (design D14 of `proof-of-fix-56-local-contract`):
1. **The share is locked, not the amount.** The first attempt still locks the rising price's share, but the winner is paid that share of the funds at its win. Pledges after the lock raise the price, and every funder pays the same fraction.
2. **Contract only, so not in this run:** a submission with no result after 7 days can be timed out by anyone, so an unrevealed commitment can't hold up the bounty.

## Result

| Mode (100 seeds) | v4 | **v5** |
|---|---|---|
| **race** (default) | ✅ every criterion | ✅ **every criterion passes** |
| auction | ✅ | ✅ |
| claim | ❌ 1 | ❌ the same 1 (proven solvers don't lock less; a comparison only) |

Every race metric is within noise of v4: 36.3 bounties paid a run, 125 per fix for funders, +67 for honest solvers, +27 for reporters, and fake attempts at −4.5 ± 14.7. In the simulation pledges arrive when a bounty opens, before any lock, so locking the share rarely changes a price. It matters on-chain, where funders can come later.

The split sweep with the share lock (`split-v2.json`) is the same as [`split-v1`](split-v1.md): 15 % to the reporter still holds.

## Measured and dropped: locking on the first submission
The contract review proposed locking the price on the first submission instead of the first attempt. An attempt costs only its fee, so a funder's sock account could lock the funder's own bounty low. One 100-seed run:

| Race | First attempt locks (kept) | First submission locks (dropped) |
|---|---|---|
| Funders' cost per paid bounty | 125 ± 2 | **162 ± 3** |
| Mean price | 109 | 154 |
| Bounties paid | 36.3 | 36.8 |
| Honest solvers' net | +67 | +178 |
| Fake attempts (two socks) | −4.5 ± 14.7 | **+51 ± 25: fails "award-mode attacks don't gain"** |

Solvers build for 2–10 days after starting, and the price rises 10 points a day, so without the attempt's lock it nearly always reached the full cap. Funders paid 30 % more for the same fixes. Fake attempts started to pay: the socks keep honest solvers away while the price keeps rising.

With the share locked, a funder that locks its own bounty low gains nothing unless solvers accept that price. If they don't, the bounty sunsets and the funds return. So the first attempt still locks.
