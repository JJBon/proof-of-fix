# Acceptance run v3: pledged stakes, proof-of-fix#19 (2026-10-24)

**Command:** `python3 -m pof.sim summary --seeds 20 > reports/acceptance-v3.json` (seeds 1–20, 8 weeks each, about 3 minutes with the new sweeps). It reproduces byte for byte. v2 ([`acceptance-v2.md`](acceptance-v2.md)) stays as the baseline.

**Result: pledges are safe, but they don't ease the capital throttle.**
- **Safe:** at the defaults (pledges on, at most half a stake pledged), every safety criterion still passes. The new pledge stacker loses money on its defective work.
- **No capital gain:** pledges cut unaffordable submissions in the replay by **3 %** (1,146 → 1,111), against a target of a third. The capital criterion fails.
- **The cause:** the stake's size relative to the reward, not the pledge rules (see "Why the target is missed").
- **At hunting elasticity 0, two criteria fail.** In v2 they passed under the same assumption. One failure comes from pledges, the other from adding the stacker to the spam scenario (see "Elasticity 0").

## v2 vs v3 at the defaults

| Criterion | v2 | v3 (pledges on) |
|---|---|---|
| Defective work loses money | ✅ worst −4.1 (padder) | ✅ worst −2.7 (owner). Stacker −11.0, spammer −12.0, sybil −10.7 per defective contribution |
| Honest validators earn | ✅ +2,144 | ✅ +2,118 |
| Splitting earns nothing | ✅ +381 ± 449 | ✅ +601 ± 432 |
| Collusion loses against honest play | ✅ every share | ✅ every share from 10 % to 70 % |
| Owner can't gain by defecting | ✅ −418 ± 941 | ✅ −1,228 ± 946 |
| Griefing loses money | ✅ −243 | ✅ −248 |
| **Pledges ease the capital throttle** | (new) | ❌ cut 3.1 %; target 33 % |

## Pledges in the runs (mean per run)

| Scenario | Pledges | Pledged (credits) | Lost to slashes | Lost to clawbacks |
|---|---|---|---|---|
| honest | 3.6 | 188 | 1.9 | 0 |
| spam | 14.7 | 442 | 5.1 | 0 |
| sponsorship | 5.3 | 216 | 5.8 | 0 |
| replay | 149 | | | |

**The stacker** builds accepted work for 3 weeks, then submits defective contributions backed by pledges. It ends at +2,368 over 8 weeks, mostly from its honest first weeks. Its defective work loses −11.0 per contribution, so stacking doesn't pay.

**No clawback reached a pledge in any run.** A backing contribution was never clawed back while pledged. The unit tests cover that path (design D4); the runs never exercise it.

## Why the target is missed

In one replay run (seed 1, a diagnostic run outside the JSON), 1,234 submissions find the balance short. Only 149 of them can pledge:
- 911 have less than half the stake in cash (typically 6 % of it), and the rule requires half from the balance;
- 174 don't have enough pledgeable reward.

Raising the caps barely helps (see the sweep below): the most is 4.7 %, at three-quarters of a stake.

**The real cause is the stake's size relative to the reward.** The 75-credit stake from #10 was tuned on the small scenarios, where a reward is 3 to 6 times the stake. At GridCraft's volume the release pool is shared by many more contributions, so a reward is smaller than the stake:

| Scenario | Reward ÷ stake |
|---|---|
| honest | 5.6 |
| spam | 3.2 |
| replay (base stake 75) | 0.77 |

The capital probe in the JSON varies only the base stake in the replay:

| Base stake | Unaffordable per run | vs 75 |
|---|---|---|
| 75 | 1,111 | |
| 40 | 760 | −32 % |
| 25 | 453 | −59 % |

A lower stake is what frees capital. But a flat lower stake breaks the small scenarios (ablation: a stake of 10 lets defective work pay). **Next step (follow-up ticket): index the stake to the expected reward,** for example stake = k × the expected reward for that size, within a floor and a cap. It would stay high where rewards are high and fall where volume makes them small.

## Elasticity 0: two failures

**Hunting elasticity 0** means hunters don't respond to pay (design D1 of #10). The bar is that the mechanism passes there too. Two criteria fail:

1. **Defective work pays for the sponsorship abuser:** +51.9 per defective contribution (n = 26). A diagnostic run with pledges off on the same seeds gives −28.9.
   - **What drives it (found in the diagnostic run):** a single escaped cosmetic defect (seed 11) that earned **2,148 credits**, about 30 times its stake. It entered a sparse beta build, where one contribution takes most of the contributors' pool.
   - **The role of pledges:** they changed the abuser's path, and the path happened to hit that release. The weakness is that **a reward has no cap relative to its stake.** Pledges only exposed it.
   - **Proposed follow-up:** cap a contribution's reward at a multiple of its stake, with the excess rolling over. This belongs with the indexed stake.
2. **Splitting gains:** +1,226 ± 332 with pledges, and +866 ± 353 without (diagnostic run) on the same seeds. So this one comes from the scenario change, not from pledges. The stacker in the spam scenario changes how the release pool is shared. The splitting criterion was already close to its edge in v2.

At elasticity 0.5 and 1, every criterion except capital passes.

## Sweeps

| Pledged share of a stake | Capital cut | Worst defective per contribution | Other failures |
|---|---|---|---|
| 0 (no pledges) | 0 % | −1.8 | |
| 25 % | 0.8 % | −3.1 | |
| **50 % (default)** | 3.1 % | −2.7 | |
| 75 % | 4.7 % | −5.6 | |

| Pledgeable share of a reward | Capital cut | Other failures |
|---|---|---|
| **50 % (default)** | 3.1 % | |
| 100 % | 3.0 % | splitting (+716) |

| Reviewer detection | Other failures |
|---|---|
| 30 % | splitting; defective work at −0.1 (v2 failed outright: +53) |
| **60 % (default)** | |
| 80 % | |

## Ablation (each rule switched off)

| Rule switched off | Safety criteria | v2 |
|---|---|---|
| Review duty | ❌ defective work pays (+41.5), honesty | ❌ |
| Per-tier weights | ❌ splitting (+1,577) | ❌ |
| The 75-credit stake (back to 10) | ❌ defective work pays (+35.6) | ❌ |
| One instalment (no clawback) | ✅ now passes (worst −3.8) | ❌ +14 |
| Decline limit | ✅ but the owner's gain goes positive (+219, not significant) | ❌ |
| Escrow share for challengers | ✅ | ✅ |
| Pledges | ✅ (cut 0) | (new) |

Instalments and the decline limit look less necessary than in v2. Under these assumptions that comes from the scenario change (the stacker) rather than from pledges. Keep both: the elasticity-0 run shows how close several criteria sit to their edges.

## Replay at GridCraft's volume
- Honest +927, validators +1,337, hunters +722.
- About 5.1 escaped regressions per run.
- 666 contributions made, 149 of them with a pledge.
- 1,111 unaffordable submissions per run.

## Risk multiplier
Still no effect (2.1–2.8 escaped at 1×, 2× and 3×).

## Decision for the owner
1. **Keep pledges on (50 %) or turn them off by default.** They're safe at the defaults and cost little, but they don't solve capital, and they add a path the elasticity-0 run punished once.
2. **Open the follow-up:** a stake indexed to the expected reward, plus a reward cap relative to the stake. The capital probe and the 2,148-credit outlier are the evidence.
