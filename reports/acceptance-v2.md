# Acceptance run v2: the proof-of-fix#10 rules (2026-10-24)

**Command:** `python3 -m pof.sim summary --seeds 20 > reports/acceptance-v2.json` (seeds 1–20, 8 weeks each, about 50 s including the sweeps). It reproduces byte for byte. The first run, [`acceptance-defaults.md`](acceptance-defaults.md), stays as the baseline.

**Result: every criterion passes**, at every hunting assumption (elasticity 0, 0.5 and 1). That needed the changes the simulation forced (design D9) and two tuned defaults: a stake of **75 credits** (was 10) and a **25 % cosmetic slash** (was 10 %).

**Main cost:** capital. At GridCraft's real volume, most submissions can't be afforded with 75-credit stakes held about 5 weeks (see "Replay").

## First run vs now

| Criterion | v1 (first defaults) | v2 (#10 rules) |
|---|---|---|
| Defective work loses money | ❌ (spam paid +3,027 per spammer) | ✅ every kind of author is negative per defective contribution: spammer −12.4, sybil −13.8, padder −4.1, honest −21.1 |
| Honest validators earn | ❌ 0 in 11 of 20 runs | ✅ +2,144 (paid for reviews) |
| Splitting earns nothing | ❌ splitter +6,533 | ✅ +381 ± 449 against the same changes unsplit (not significant) |
| Collusion loses against honest play | ❌ (mis-measured) | ✅ negative at every stake share from 10 % to 70 %; no threshold reached |
| Owner can't gain by defecting | ❌ 12 of 20 seeds | ✅ −418 ± 941 (honest 15,485, self-interested 15,067) |
| Griefing loses money | ✅ −57 | ✅ −243 |
| Escaped regressions (spam scenario) | 4–10 per run | about 2.7 per run |

## Returns per actor (credits over 8 weeks, mean of 20 seeds)

| Actor | honest | spam | griefing | sponsorship |
|---|---|---|---|---|
| honest contributor | 3,609 | 2,269 | 3,603 | 2,816 |
| validator (votes and reviews) | 2,144 | 2,192 | 2,224 | 2,137 |
| hunter | 723 | 2,064 | 845 | 1,132 |
| spammer / padder / splitter | — | 1,760 / 3,371 / 1,865 | — | — |
| griefer | — | — | −243 | — |
| sponsored newcomer | — | — | — | 1,380 |
| abuser / each sybil | — | — | — | 1,218 / 480 |

**Why do spammers still end positive?** Their **sound** contributions (40 %) are accepted, real work in the model, and are paid like anyone's. What the mechanism must stop is **defective work paying**, and it does: −12.4 credits per defective spam contribution. The same holds for padders, splitters and sybils.

## Assumption sweeps (design D1)

| Hunting elasticity | Passes | Worst defective per contribution | Escaped |
|---|---|---|---|
| 0 (hunters don't respond to pay) | ✅ | −4.08 | 2.3 |
| 0.5 (default) | ✅ | −3.54 | 2.67 |
| 1 | ✅ | −3.54 | 2.67 (the hunting factor hits its 4× cap at 0.5 already) |

| Reviewer detection | Passes | Worst defective per contribution |
|---|---|---|
| 30 % | ❌ +53.4 | |
| **60 % (default)** | ✅ −3.54 | |
| 80 % | ✅ −8.55 | |

**Reviewers must catch more than about 30 % of defects** for defective work to stop paying. That's the number the planned measurement on real data (#15) has to confirm.

## Ablation: each #10 rule switched off (design D8)

| Rule switched off | Passes | What breaks |
|---|---|---|
| (none: all rules) | ✅ | |
| Escrow share for challengers | ✅ | Nothing at these assumptions; challengers earn less (defective worst −2.0 vs −3.5) |
| Review duty | ❌ | Defective work pays (+55), validators earn only 261, escaped 6.2 |
| Instalments and clawback (1 instalment) | ❌ | Defective work pays (+14) |
| Linear weights (per-tier) | ❌ | Splitting pays (+2,189), defective work pays |
| Decline limit | ❌ | Defective work pays (+3.3) |
| The 75-credit stake (back to 10) | ❌ | Defective work pays (+35.6); the owner gains (+1,085) |

Every rule but one carries its weight. **The escrow share for challengers** isn't needed under these assumptions, and is a candidate for removal if simplicity matters more than paying hunters.

## Replay at GridCraft's volume
- Honest +901, validators +1,336, hunters +796; about 4.5 escaped regressions per run.
- **Capital throttle:** about 1,146 submissions per run were unaffordable, so 629 contributions were made against about 1,780 attempted. With 75-credit stakes locked about 5 weeks, a 500-credit contributor can't keep up GridCraft's pace.
- **Next lever (follow-up):** let a contributor's unpaid instalments in escrow back their next stakes ("earned collateral"), so active, proven contributors aren't capital-bound. Newcomers are sponsored.

## Risk multiplier
Still no effect (escaped 2.1–2.4 at 1×, 2× and 3×). Keep every contribution at "normal".

## Not modelled
- Release timing by the owner (releases are weekly).
- Money in panels outside challenges (approvals, decline limits, split changes).
- Bounty auctions and AI juries: #15.
