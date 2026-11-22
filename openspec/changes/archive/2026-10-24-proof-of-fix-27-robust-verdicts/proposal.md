# Proposal

## Why

Acceptance run v4 passed every criterion on 20 seeds. Re-checking its defaults on 100 seeds (ticket proof-of-fix#27, comment 3637) shows the verdicts weren't robust:

- **"Defective work loses money" is judged on a raw pooled mean.** On 100 seeds, sponsored newcomers' accidental defects average +6.3 ± 14.3, so v4 fails under today's rule. A 20-seed pass and a 100-seed failure are both noise around zero. Meanwhile, **every attacking group loses money significantly**, except the sponsorship abuser at hunting elasticity 0 (−14.7 ± 12.2, about 80 contributions). The rule can't tell a real weakness from an under-sampled group.
- **"Splitting earns nothing" fails on 100 seeds under every rule set since v2** (v4 +802 ± 205, v2 +661 ± 195). The 20-seed passes were noise.
  - **The diagnosis:** the unsplit counterfactual doesn't ship the same work. Its giant contributions are often unaffordable and capped at 1,500 lines, so it gets 1,687 lines accepted against the split runs' 2,787.
  - **Per accepted line, splitting earns less** (0.64 against 0.79).
  - The criterion measures a capital effect (small contributions fit a balance), not weight gaming.
- **Capped rewards pile up:** about 25,000–27,000 credits sit unpaid in the contributors' pool at the end of the small scenarios, with no rule for them.

## What Changes

- **Defective work, judged with standard errors** (clustered by seed, since contributions in one run aren't independent):
  - each **attacking** kind of author (spammer, splitter, padder, sybil, ally, abuser, stacker, gamer) must lose money **significantly**: the pooled mean plus two standard errors is below zero;
  - a kind with fewer defective contributions than a published minimum is **inconclusive**, and that fails;
  - an **honest-intent** kind (honest, owner, newcomer) fails only if its defects **gain** significantly.
- **Splitting, per accepted line:** the splitter's return per accepted line, against the same changes unsplit, must not be significantly higher. The report also gives lines accepted for both, so the affordability effect is visible and not hidden.
- **Final verdicts on 100 seeds.** The sweeps and ablation run on 20, so a summary takes about 10 minutes.
- **The sponsorship scenario gets three abusers** (each with its fake accounts) instead of one, so the abuser group has enough contributions to judge. Every abuser behaves as before.
- **Funding follows use.** Before a release is funded, if the contributors' pool already holds more than a published buffer of releases' worth, that release's whole funding is scaled down by the same factor for every share. The published split doesn't change, and nothing is issued for work that isn't there.

**Out of scope:**
- other mechanism rules;
- the bounty market (#15);
- the Lean proofs (#5);
- anything real (rule 1).

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `incentive-simulation`:
  - "Acceptance criteria for the mechanism": the significance rules, the inconclusive case, and splitting per accepted line;
  - "Acceptance with pledges": the same wording for its attack scenario.
- `release-payouts`: a new requirement, "Funding follows use".

**Actors and attacks affected:** every attacking kind (now judged with significance), sponsors and abusers (three of them), validators and the owner (their shares shrink when the pool holds a surplus), and the splitter (judged per accepted line).

## Impact

- **Code:**
  - `pof/params.py`: `pool_buffer_releases` (the minimum sample is a constant of the acceptance check, `MIN_DEFECTIVE_SAMPLE`, not a mechanism parameter);
  - `pof/payouts.py`: the scaled funding in `open_release`;
  - `pof/sim/report.py`: the clustered standard errors, the inconclusive case, splitting per accepted line;
  - `pof/sim/scenarios.py`: three abusers;
  - `pof/sim/summary.py` and `__main__.py`: `--sweep-seeds`;
  - tests for each.
- **Data:** `reports/acceptance-v5.{json,md}` on 100 seeds. The earlier reports stay, with a note in v5 that their splitting verdicts were 20-seed noise.
- **No change** to `ledger` (less is issued, nothing is moved differently) or to `challenges`.
