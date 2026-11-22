# Design

## Context

Today:
- `Params.stake_for(lines, risk)` is `base_stake × stake_multiplier[tier] × risk_multiplier`, a fixed stake of 75 credits at the base tier.
- `Releases.ship_beta` divides the whole contributors' pool among the contributions in the beta build by weight (linear in changed lines, capped at 1,500, with a per-author cap). Nothing limits one contribution's share.

Acceptance run v3 measured reward ÷ stake:
- 5.6 in `honest` and 3.2 in `spam`, where every criterion passes;
- 0.77 in the replay at GridCraft's volume, where capital binds;
- about 30 for the outlier, an escaped defect alone in a sparse release.

The challenges spec already takes shares of the contributor's stake (challenger stake, slashes), so they scale with any change to the stake.

## Goals / Non-Goals

**Goals:**
- Keep reward ÷ stake inside a band at any volume.
- Free capital where rewards are small.
- Keep every safety criterion passing, at hunting elasticity 0 too.

**Non-Goals:**
- Changing the release funding or the split.
- Per-person stakes (reputation).
- Predicting a single contribution's reward. The index is about the market rate, not the person.

## Decisions

### D1. The index is the offered rate per unit of weight, over a window
At each beta build, the offered rate is the pool available divided by the total weight shipped. It's computed **before** the reward cap (D4), so capping doesn't feed back into the index and ratchet stakes down.

Each build records it as a ledger event (`stake_index`, with the release). The index is the weighted mean over the last `stake_index_window` builds that shipped anything: their total offered pool divided by their total weight.

A contribution's expected reward is the index × its weight. Inputs are published records and parameters only.
- *Alternative:* the mean escrowed reward. Rejected: it includes capped amounts, so the stake would follow the cap down.
- *Alternative:* the next release's offer. Rejected: it isn't known at submission, and it's easier to game on the day.

### D2. Parameters (defaults)
| Parameter | Default | Rationale |
|---|---|---|
| `stake_per_reward_bps` | **4,000** (proposed 2,500; D7) | The stake is a quarter of the expected reward, so reward ÷ stake is about 4: the middle of the 3–6 where v2 and v3 passed. 0 switches the index off (fixed stake). |
| `stake_floor` | 10 credits (× the tier multiplier) | The first defaults' stake. It only binds when rewards are tiny, and then a defect earns little too. |
| ceiling | the fixed stake (`base_stake` × tier) | The index can only lower a stake below the value #10 tuned, never raise it. The small scenarios keep the v2 behaviour that passed. |
| `stake_index_window` | 4 builds | About the length of the clawback (4 instalments): long enough to smooth one flooded release, short enough to follow volume within a month. |
| `reward_cap_stake_multiple` | **6** (proposed 8; D7) | Twice the target ratio, for normal variance. The 30× outlier is capped at 8×. 0 switches the cap off. |

**The cap's rationale, in numbers.** Take detection at about 96 % (v3) and a capped reward at most 8 × stake. A defect's expected gain is then at most 0.04 × 8 × stake = 0.32 × stake. Its expected loss is at least 0.96 × the smallest slash (cosmetic, 25 %) = 0.24 × stake, plus the check fee and the forfeited reward. The margin is thin for cosmetic defects alone. So the simulation decides, with the sweep below, and records any change openly.

**Sweeps (in the summary):**
- `stake_per_reward_bps`: 0, 1,500, 2,500 and 4,000;
- `reward_cap_stake_multiple`: 0, 4, 8 and 16.

### D3. Cold start
Until a build has shipped a contribution, the fixed stake applies, which is today's behaviour. The window then fills with the builds that actually shipped something.

### D4. Reward cap
`ship_beta` gives each contribution min(its share by weight, cap × its stake). The excess isn't divided among the others in the same build (that would push them over their own caps), and stays in the pool for the next release.
- *Alternative:* return the excess to the release funding. Rejected: the pool already rolls over, and conservation needs no new path.

### D5. Pledges are unchanged and swept
Pledges stay on, at most half a stake (#19). The summary keeps the pledge-cap sweep, so the owner can decide on them with v4's data. Under lower stakes they may matter more or less.

### D6. Simulation
- **Index gamer:** in the spam scenario. For the first 3 weeks it submits many small sound contributions (10 a week, at most 20 lines), which pushes the offered rate down. From then on, it submits defective contributions (60 %, at most 100 lines, 7 a week) at the lower stake.
- **Report:** the gamer's mean stake before and after its turn.
- **Capital criterion:** the replay with the proposed parameters, against the same seeds with `stake_per_reward_bps` = 0 and `reward_cap_stake_multiple` = 0. That's the fixed-stake rules, with everything else equal (pledges included).
- **Elasticity 0:** the summary's elasticity sweep already runs it. This change requires it to pass, and the report states it.
- **Ablation:** new rows "no index" and "no reward cap".
- **Report:** the final balance of the contributors' pool, so capped excess that accumulates is visible.

### D7. What the acceptance run changed (task 4.2)
- **Tuned defaults:**
  - `stake_per_reward_bps` **2,500 → 4,000**: at 25 %, the index gamer's defective work paid at elasticity 0.5 (+1.7 per contribution, n = 350);
  - `reward_cap_stake_multiple` **8 → 6**: at 8×, defective work paid at elasticity 0 (newcomers, about 40 contributions).

  A grid at elasticity 0 over shares of 25 %, 40 % and 50 %, and caps of 4, 6 and 8, passed only at a cap of 6, at every share. Of those, 40 % gave the widest margin and still cuts capital by 57 %.
- **The result (`reports/acceptance-v4.md`):**
  - every criterion passes at elasticity 0, 0.5 and 1;
  - capital: 1,111 → 477 unaffordable submissions in the replay (−57 %), and contributions made nearly double;
  - reward ÷ stake never exceeds 6.
- **Narrow pass:** neighbouring settings (caps of 4, 8 and 16; a 25 % share; no pledges; 80 % reviewer detection) fail "defective work loses money" by a few credits. Sometimes that's a small group's noise (the abuser, about 20 contributions), sometimes thin real margins (the owner, the padder, the splitter, the gamer).
- **Costs:**
  - capped rewards accumulate in the pool (about 25,000–27,000 credits at the end of the small scenarios);
  - the owner's mean gain from defecting is positive but not significant (+464 ± 769).
- **Proposed follow-ups (not in this change, so as not to change a criterion while tuning against it):**
  - judge "defective work loses money" with a standard error, and run the final verdicts on 100 seeds;
  - a policy for the capped excess.

## Risks / Trade-offs

- **Lag:** a sudden rise in rewards keeps stakes low for up to 4 builds, and a sudden fall keeps them high. The cap bounds the first case. The second costs capital briefly.
- **Flooding:** gaming the index pushes stakes down for everyone in the window. The cap keeps reward ÷ stake at most 8 whatever the stake, and the gamer is measured.
- **Lower stakes pay hunters less,** since the challenger's share comes from the forfeited stake. That's why elasticity 0 must pass.
- **Thin margin for cosmetic defects** at the cap (D2). The cap sweep shows where it breaks.
- **Capped excess builds up** in low-volume periods. It's reported. A policy for it (for example, returning it to the funding) is a follow-up if it grows large.
- **More inputs for the proofs:** #5 needs a theorem that reward ÷ stake stays within the band.
