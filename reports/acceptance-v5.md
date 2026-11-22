# Acceptance run v5: robust verdicts, proof-of-fix#27 (2026-10-24)

**Command:** `python3 -m pof.sim summary --seeds 100 --sweep-seeds 20 > reports/acceptance-v5.json`. The verdicts use seeds 1–100, and the sweeps and ablation seeds 1–20. Each run is 8 weeks, and the whole summary takes about 12 minutes. It reproduces byte for byte.

**What changed in how verdicts are reached:**
- **Defective work** is judged with standard errors clustered by seed:
  - attackers must lose money significantly;
  - honest groups must not gain significantly;
  - a group under 50 defective contributions is inconclusive.
- **Splitting** is judged per accepted line.
- **Verdicts use 100 seeds.**

**What changed in the mechanism:** funding follows use. The contributors' pool may hold two releases' worth, and beyond that the next release's whole funding scales down.

## Result

| Hunting elasticity (100 seeds) | Verdict |
|---|---|
| **0.5** (default) | ✅ every criterion passes |
| **1** | ✅ every criterion passes |
| **0** | ❌ **splitting** fails: +0.55 ± 0.16 credits per accepted line. Every other criterion passes, and every attacker still loses money significantly |

### Defective work (elasticity 0.5, 100 seeds)

| Kind | Mean per defective contribution | n | Verdict |
|---|---|---|---|
| spammer | −10.4 ± 0.3 | 6,552 | loses |
| sybil | −5.7 ± 0.4 | 10,128 | loses |
| stacker | −9.6 ± 0.8 | 1,846 | loses |
| index gamer | −6.6 ± 1.1 | 1,418 | loses |
| padder | −13.1 ± 4.8 | 753 | loses |
| splitter | −18.5 ± 3.3 | 263 | loses |
| abuser (three of them) | −25.5 ± 2.7 | 263 | loses |
| honest | −17.1 ± 2.4 | 4,419 | doesn't pay |
| owner | −0.5 ± 4.0 | 779 | doesn't pay |
| newcomer | −7.6 ± 9.0 | 214 | doesn't pay |

At elasticity 0, every attacker group also loses significantly.

### Other criteria (elasticity 0.5, 100 seeds)
- **Validators earn** +1,788 (v4: +2,145, before funding followed use).
- **Griefers lose** −230.
- **Collusion loses** at every stake share from 10 % to 70 %: −350 ± 120 at 10 %, down to −1,548 ± 276 at 70 %.
- **The owner can't gain by defecting:** −200 ± 362.
- **Capital:** 1,109 → 464 unaffordable submissions in the replay against the fixed stake (−58 %).
- **Splitting per accepted line:** split 1.48, unsplit 1.21, difference +0.28 ± 0.17 (not significant). In total return, splitting is +802 ± 205, because it ships more lines (1,375 against 1,028).

## Splitting at elasticity 0: the remaining failure

When hunters don't respond to pay, splitting earns **0.55 more credits per accepted line** (1.64 against 1.09). There are two causes, both from **paying per line**:
1. **The 1,500-line weight cap per contribution:** 35 % of the unsplit runs' accepted lines are above it and earn nothing (about 1 % for split parts).
2. **Partial acceptance:** when some parts are declined or fail, the rest still pay, and the per-author cap binds less. An unsplit change that fails loses everything.

**Next step:** paying per problem solved, through the market model (#15), removes per-line pay and both causes. No parameter was tuned for this here.

## Corrections to earlier reports

The 20-seed verdicts in v2–v4 were too noisy for two criteria:
- **"Splitting earns nothing" didn't hold** in v2, v3 or v4. Re-run on 100 seeds, splitting gains +661 ± 195 (v2 rules) to +802 ± 205 (v4 defaults) in total return (#27, comment 3637).
- **v4's "defective work loses money" pass was partly luck.** On 100 seeds under the old raw-mean rule, sponsored newcomers' defects averaged +6.3 ± 14.3.
- **A claim of mine on #27 was wrong.** I wrote that per accepted line, splitting earned less (0.64 against 0.79). That was per *submitted* line (#27, comment 3650).

## Funding follows use

| | v4 | v5 |
|---|---|---|
| Contributors' pool at the end (small scenarios) | 25,000–27,000 | **15,000** (the buffer) |
| Validators (honest scenario) | +2,145 | +1,788 |
| Owner (honest scenario) | +14,697 | +14,099 |
| Honest contributors | +3,510 | +3,418 |

Every share shrinks with the funding, so nobody gains from releases that pay no one.

Every pool buffer size passes the safety criteria at 20 seeds (0, 1, 2 and 4 releases). The buffer controls the money, not the incentives.

## Sweeps and ablation (20 seeds)

At 20 seeds, many groups are too small to show a loss significantly. So each row gives **passed except inconclusive**, and where it fails, which verdicts did. A "not shown" is a loss that 20 seeds can't confirm, not a gain.

| Row | Passes | What fails |
|---|---|---|
| Hunting elasticity 0, 0.5 and 1 | ✅ | |
| Pool buffer 0, 1, 2 and 4 | ✅ | |
| Reviewer detection 30 % | ❌ | gamer and padder: not shown |
| Reviewer detection 60 % (default) and 80 % | ✅ | |
| Stake share 15 % and 25 % | ❌ | defective work |
| **Stake share 40 % (default)** | ✅ | |
| No index (fixed stake) | ❌ | capital |
| Reward cap 4× and **6× (default)** | ✅ | |
| Reward cap 8×, 16× or none | ❌ | defective work (at 8×: padder not shown, splitter inconclusive) |
| Pledges off, or at 25 % | ❌ | defective work (padder not shown); with pledges off, splitting too |
| Pledges at 75 % | ❌ | splitting |
| No review duty | ❌ | defective work (the gamer's **pays**), and validators earn only +122 |
| One instalment (no clawback) | ❌ | defective work |
| Per-tier weights | ❌ | defective work, splitting |
| No decline limit | ❌ | defective work |
| First defaults' stake (10) | ❌ | capital, defective work, splitting |
| No escrow share for challengers | ✅ | |

**Only one row shows a significant gain:** with review duty switched off, the index gamer's defective work pays. Every other defective-work failure above is "not shown" or "inconclusive": a loss that 20 seeds can't confirm.

Every rule but the challengers' escrow share carries its weight in that sense: without it, some group's loss can no longer be confirmed. The stake share and the reward cap sit in a narrow region where every loss is confirmed. A 100-seed sweep (about 30 minutes) would tell which neighbours actually fail.

## Band, actors and replay
- **Reward ÷ stake:**
  - honest 5.7, spam 2.9, sponsorship 3.1, replay 1.1;
  - no reward above 6 times its stake.
- **Index gamer:** its stake went from 60 to 52 after its flood, and its defective work loses (−6.6 ± 1.1).
- **Replay at GridCraft's volume:**
  - 1,310 contributions per run, and 464 unaffordable;
  - honest +968, validators +1,113;
  - 9.2 escaped regressions (about 0.7 %).

## Next
1. **The market model (#15):** bounties cleared by sealed rounds, a stake as a share of the bounty, and pay per problem solved. It replaces the lines-based placeholder behind the splitting failure.
2. **The Lean proofs (#5)** for the settled enforcement rules.
