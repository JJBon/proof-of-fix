# Acceptance run v4: indexed stake and reward cap, proof-of-fix#23 (2026-10-24)

**Command:** `python3 -m pof.sim summary --seeds 20 > reports/acceptance-v4.json` (seeds 1–20, 8 weeks each, about 6 minutes with the sweeps). It reproduces byte for byte. v3 ([`acceptance-v3.md`](acceptance-v3.md)) stays as the baseline.

**Result: every criterion passes, at hunting elasticity 0, 0.5 and 1, including the capital criterion.** In the replay at GridCraft's volume:
- unaffordable submissions fall by **57 %** against the fixed-stake rules (1,111 → 477 per run);
- contributions made nearly **double** (666 → 1,304).

That needed two defaults tuned in the open (design D7): the stake is **40 %** of the expected reward (25 % proposed), and the reward cap is **6×** the stake (8× proposed).

**The caveat: it passes narrowly.**
- Several neighbouring settings fail "defective work loses money" by a few credits per contribution.
- The sponsorship abuser's result swings by tens of credits, because it rests on about 20 defective contributions.
- Capped rewards also pile up in the contributors' pool (see "Costs").

## v3 vs v4 at the defaults

| Criterion | v3 | v4 |
|---|---|---|
| Defective work loses money | ✅ worst −2.7 | ✅ worst **−2.3** (sybil). Gamer −9.1, stacker −9.2, spammer −10.3, abuser −27.2 |
| Honest validators earn | ✅ +2,118 | ✅ +2,145 |
| Splitting earns nothing | ✅ +601 ± 432 | ✅ −118 ± 437 |
| Collusion loses against honest play | ✅ | ✅ every share from 10 % to 70 % |
| Owner can't gain by defecting | ✅ −1,228 ± 946 | ✅ **+464 ± 769** (positive mean, not significant) |
| Griefing loses money | ✅ −248 | ✅ −236 |
| **Capital: a third fewer unaffordable submissions than the fixed stake** | ❌ 3 % (pledges) | ✅ **57 %** |
| At hunting elasticity 0 | ❌ two failures | ✅ (worst −6.5) |

## The band: reward ÷ stake

| Scenario | Mean | Highest |
|---|---|---|
| honest | 5.7 | 6.0 (the cap) |
| spam | 2.9 | 6.0 |
| sponsorship | 4.3 | 6.0 |
| replay | 1.1 (v3: 0.77) | 2.9 |

**No contribution earns more than 6 times its stake** (the 30× outlier from v3 is gone).

The index gamer's flood lowered its own mean stake from 62 to 51 credits after its turn. Its defective work still loses (−9.1 per contribution). The stacker's stake fell from 130 to 54 because rewards per line fell in the spam scenario. Its defective work loses too (−9.2).

## Replay at GridCraft's volume

| | v3 | v4 |
|---|---|---|
| Contributions made | 666 | 1,304 |
| Unaffordable | 1,111 | 477 |
| Honest return | +927 | +967 |
| Validators | +1,337 | +1,320 |
| Escaped regressions | 5.1 (0.76 % of contributions) | 9.5 (0.73 %) |

There are more escaped regressions because there are twice as many contributions. The rate is the same.

## How narrow the pass is

Each sweep below changes one value from the defaults. "Fails" means "defective work loses money" fails. The worst values are in the JSON. The kinds named come from diagnostic runs of the acceptance check at that setting, outside the JSON.

| Change | Result | Who fails |
|---|---|---|
| Reward cap 4× | fails | (+52.6 worst) |
| **Reward cap 6× (default)** | passes | |
| Reward cap 8× | fails | abuser +12.1 (n = 20), owner +3.3, padder +0.9, splitter +1.3 |
| Reward cap 16× / no cap | fails | splitter +4.6 |
| Stake share 15 % | fails | (+42.2 worst) |
| Stake share 25 % | fails | gamer +1.7 (n = 350) |
| **Stake share 40 % (default)** | passes | |
| No index (fixed stake) | fails, and capital fails | (+18.6 worst) |
| No pledges | fails | abuser +71.9 (n = 22), owner +4.5 |
| Pledges up to 75 % of a stake | passes | |
| Reviewer detection 30 % | fails | (+3.2) |
| Reviewer detection 80 % | fails | abuser +27.3 (n = 17) |

**Two kinds of failure:**
1. **Small-sample swings.** The abuser has about 20 defective contributions per 20 seeds, and one escaped reward moves its pooled mean by tens of credits. That's why *better* detection (80 %) or removing pledges can "fail": the path changes, not the safety.
2. **Thin margins near zero for larger groups:** the owner, the padder, the splitter and the gamer, at a few credits either side. These are real.

**What it means:** the defaults are safe by the criteria, but the margin is a few credits per defective contribution. The verdict for small groups is noise-dominated.

**Proposed next step (follow-up):**
- judge "defective work loses money" with a standard error, like the other criteria: fail only if the pooled mean is significantly positive, and report when a group is too small to judge;
- run the final verdicts on more seeds (100).

Neither is done here, so as not to change a criterion in the same change that tunes against it.

## Ablation (each rule switched off)

| Rule switched off | v4 |
|---|---|
| Review duty | ❌ defective work pays (+15.7), validators earn only 122, splitting |
| Per-tier weights | ❌ splitting (+917) |
| Decline limit | ❌ defective work (+4.1), splitting (+1,193) |
| Escrow share for challengers | ❌ splitting (+1,060). It was the one rule not needed in v2 and v3 |
| The index (fixed stake) | ❌ capital, defective work (+18.6) |
| The reward cap | ❌ defective work (+4.6) |
| Pledges | ❌ abuser (small sample, see above) |
| One instalment (no clawback) | ✅ (it passed in v3 too) |
| First defaults' stake (10) | ❌ capital, defective work, splitting |

With the lower stakes, every rule now carries its weight except instalments. The escrow share for challengers matters again, because lower stakes mean smaller forfeits for challengers.

## Costs

- **Capped rewards pile up.** At the end of the small scenarios, about 25,000–27,000 credits sit in the contributors' pool (honest 26,890, spam 25,608, sponsorship 25,463). That's money funded for contributors and not paid out, because the cap binds whenever rewards are high relative to stakes. It isn't lost (conservation holds), but it needs a policy. Options for a follow-up:
  - lower the funding when the pool grows;
  - lift the cap gradually as the pool grows;
  - return the excess to the funding.
- **The owner's mean gain from defecting is positive** (+464 ± 769). That's not significant, so the criterion passes, but it was −418 in v2 and −1,228 in v3. Worth watching in the follow-up.
- Honest returns hold (+3,510 over 8 weeks in `honest`), and validators hold (+2,145).

## Pledges (design D5)

Pledges stay on. Removing them fails the abuser group, which is a sample-size effect. Raising them to 75 % passes with a slightly better margin. They make little difference to capital (cut 59 % without, 57 % with), and losses to slashes are small (0–7 credits per run).

**Recommendation:** keep them at 50 %. They cost little, and the capital question is answered by the index, not by pledges.

## Risk multiplier
Still no effect (2.2–2.4 escaped at 1×, 2× and 3×).

## Decisions for the owner
1. **Accept the tuned defaults** (40 %, 6×), knowing the margin is thin.
2. **Follow-up:** a statistical test for "defective work loses money" plus 100 seeds, and a policy for the capped excess in the pool.
