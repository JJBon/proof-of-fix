# Design

## Context

See proposal.md for the failures. The code this changes:
- `pof/lifecycle.py` (stake, escrow, settlement, decline);
- `pof/challenges.py` (filing, panels, finalize);
- `pof/payouts.py` (release split, validators' pool, owner);
- `pof/params.py`;
- `pof/sim/*`: the actors, world, scenarios, report and summary added in #9 and #11.

The ledger is unchanged. The first acceptance run (`reports/acceptance-defaults.*`) stays as the baseline to compare against.

## Goals / Non-Goals

**Goals:**
- The acceptance run passes every criterion over 20 seeds, or each remaining failure is explained with its cause.
- Each new rule can be switched off by a parameter, so the report can show what each one contributes (an ablation table).

**Non-Goals:**
- Identity and proof of personhood: sponsorship is the only sybil defence here.
- Reputation scores.
- Re-proving the Lean theorems (#5 follows).

## Decisions

### D1. Hunting responds to pay (a declared simulation assumption)
Today's hunters find a defect at a fixed daily rate, so paying them more changes nothing in the model. The new model scales a hunter's daily rate by the expected value of one catch relative to a reference: `rate = base × clamp((value / reference)^elasticity, 0.25, 4)`. The reference is the value under the first defaults.

This is an assumption about people, not a mechanism rule, so the report runs `hunt_elasticity` = 0 (no response), 0.5 (the default) and 1. **The mechanism has to pass with elasticity 0 as well,** relying on review duty and clawback alone; otherwise the report says it depends on the assumption.
- *Alternative:* keep fixed rates. Rejected: that makes the challenger pay change untestable.

### D2. New parameters (defaults)

| Name | Default | Rationale |
|---|---|---|
| `base_stake` (tuned, D9) | 75 credits (was 10) | 10 let the 2–4 % of escaped defects pay for all caught ones; 75 passes at every hunting elasticity |
| `severity_slash_bps["cosmetic"]` (tuned, D9) | 2,500 (was 1,000) | Padding caught as cosmetic cost too little |
| `challenger_escrow_share_bps` | 5,000 | Half of a caught contribution's reward (about 190 credits at today's pool) goes to the challenger, against about 8 credits today. The rest returns to the pool. |
| `review_detect_bps` (simulation) | 6,000 | A reviewer reading the diff catches 60 % of defects. Swept 30–80 %. |
| `review_bond` / `missed_review_penalty_bps` / `no_review_penalty_bps` | 5 credits / 5,000 / 2,000 | Same bond as a validator. Missing a defect that's later proven costs half the bond, which keeps "approve everything" from paying. |
| `reward_instalments` | 4 | The first at settlement, then one per weekly release. The clawback period becomes about 4 weeks, against 7 days today. |
| `reward_weight` | linear in changed lines, capped at 1,500 (`reward_weight_cap_lines`) | Splitting earns exactly nothing extra, while each part pays its own stake and fee. Replaces the per-tier weights 1, 2, 4, 6. See the padding risk below. |
| `max_declines_bps` | 1,000 | A maintainer may decline up to 10 % of others' contributions per release without a panel. Above that, a panel decides. |
| `decline_appeal_stake` | the check fee | Cheap enough for a wronged contributor to appeal, not free. |
| `sponsor_min_accepted` | 1 | Only someone with an accepted contribution can sponsor. |
| `hunt_elasticity` (simulation) | 0.5 | See D1. |

Existing parameters keep their values. If the run still fails, parameters are tuned in this change (task 6.2) and each changed value is recorded here with the reason.

### D3. Review duty
- **When:** at `ship_beta`, each contribution gets a reviewer from `ValidatorSet.select(1, seed, exclude={author, sponsor} ∪ links)`. The reviewer's bond is locked.
- **Reporting:** in the simulation, the reviewer finds a hidden defect with `review_detect_bps` and then files it as a normal challenge (with a challenger stake), so the replay and judgement layers are unchanged.
- **Pay:** at the release's close, each completed review that wasn't later missed counts as one unit of validator work.
- **Missed defects:** when a contribution is slashed (during the window or the clawback), its reviewer loses `missed_review_penalty_bps` of the bond, which goes to insurance.

### D4. Instalments and clawback
- **Accept:** returns the stake and pays one instalment. The rest stays in the contribution's escrow account.
- **Each release:** `Releases.open_release` pays the next instalment of every contribution still in clawback.
- **A challenge during clawback:** uses the same filing and judgement. If upheld, `Lifecycle.claw_back` sends the unpaid escrow `challenger_escrow_share_bps` to the challenger and the rest to the contributors' pool. The stake isn't touched, since it was already returned.

New state: `accepted` with `instalments_left > 0` is "in clawback". After the last instalment, challenges are refused.

### D5. Maintainer guardrails
- **Maintainers:** a set in the world. In the simulation the owner is the only maintainer, so the "another approver" rule always goes to a validator panel. The panel approves unless a member detects a defect, at `review_detect_bps`.
- **Declines:** counted per maintainer per release; over `max_declines_bps` of others' contributions, a panel decides.
- **Appeals:** a declined contributor appeals with `decline_appeal_stake`. The panel overturns a decline when the contribution has no defect it detects. An overturned decline sends the contribution to the next beta build, and the event is recorded against the maintainer.
- **Owner-benefiting split change:** goes to a panel that excludes the owner. In the simulation honest panels reject a change that raises the share of a role the owner holds.

### D6. Sponsored stakes
`Lifecycle.submit(..., sponsor=account)` locks the stake from the sponsor, who must have `sponsor_min_accepted` accepted contributions. Refunds and forfeits go to and from the sponsor. In the simulation, the sponsorship abuser first makes honest contributions until accepted, then sponsors several sybil accounts that spam.

### D7. Collusion against a counterfactual
For each seed and share, the collusion scenario runs twice: once as is, and once with the ring's members acting honestly (no group; the ally still spams). Gain from colluding = ring return − counterfactual return. The threshold is the smallest share where the gain turns positive.

### D8. Ablation
The summary adds a table with the acceptance metrics at the new defaults and with each new rule turned off in turn: escrow share 0, review duty off, instalments 1, per-tier weights, no decline limit. Each rule's effect becomes visible.

### D9. Changes the simulation forced (task 6.2)
The first runs with the #10 rules found these. Each was fixed here, and the spec deltas were updated to match.

1. **The instalment leak.** Paying the first instalment and returning the stake at acceptance meant a defect proven during the clawback cost only the unpaid part: a spammer's defective contribution still netted +2.16 credits. **Now:** nothing is paid at acceptance; instalments start at the next release; the stake stays locked until the last instalment; a clawback also slashes the stake by severity.
2. **Splitting above the cap** (recorded as a risk in PR A) paid +1,246 against the same change unsplit. **Now:** an author's total weight per release is capped at `reward_weight_cap_lines`, too.
3. **The criteria were measuring the wrong thing.**
   - "Spammers and splitters earn a negative return" also penalized their sound work: a spammer's 40 % of sound contributions and the splitter's code are accepted, valuable work in the model.
   - "Sponsorship abuse" compared a cohort with and without its fake accounts, so it counted their accepted work as abuse.

   **Now:**
   - **defective work loses money,** pooled per kind of author, with sponsors' losses included;
   - **splitting, collusion and the owner** are judged against the same actors' honest play.
4. **Single runs were too noisy for those comparisons:** a different random path in each run made 1 % differences look like failures. **Now:** the mean over seeds, failing only when the gain exceeds twice its standard error.
5. **The stake was too small against the reward.** Detection is high (96–98 % of defects caught), but an accepted contribution earned about 16 times its stake, so the 2–4 % that escaped paid for all the caught ones. A stake sweep (10, 20, 30, 50, 75) showed:
   - 50 passes when hunting responds to pay, but not at elasticity 0;
   - **75 with a 25 % cosmetic slash passes at every elasticity.**

   The 25 % cosmetic slash is because padding caught as "cosmetic" cost only 10 % of the stake.

**Tuned defaults (task 6.2):** `base_stake` 10 → **75 credits**; `severity_slash_bps["cosmetic"]` 1,000 → **2,500**.

**Cost of the tuning:** honest returns are about 15 % lower (still about +2,400 to +2,800 over 8 weeks), and **capital limits throughput.** With 75-credit stakes held about 5 weeks, a contributor submitting 3.5 PRs a week from 500 credits could afford 4 of 14. Sponsorship helps newcomers; a stake posted from expected rewards would be the next lever.

## Risks / Trade-offs

- **[Padding]** Linear weights pay for extra lines. → Reviewers report padding as a "cosmetic" defect (10 % slash), and maintainers can decline within their limit. The simulation adds a padder variant of the spammer, which must also lose money. If padding still pays, cap the weight lower or make it concave above the merged-PR p75 (186 lines).
- **[Splitting above the cap]** Found while building (task 1.1): a change larger than `reward_weight_cap_lines` (1,500) earns more as parts below the cap. For example, 4,000 lines earn weight 1,500 as one contribution but 4,000 as eight. The spec's guarantee holds up to the cap only. → Such changes are rare: the merged p90 is 431 lines, and only 14 of the 659 merged PRs (2.1 %) are above 1,500 lines. Each part also pays its own stake, and the >1,500 tier's stake is 10×. The simulation's splitter uses sizes up to 3,000 lines, so the report shows whether this matters; if it does, a per-author weight cap per release closes it.
- **[Results depend on the hunting assumption]** → D1: the mechanism must also pass at elasticity 0, and the report shows all three.
- **[Panels add delay]** Owner contributions and decline appeals wait for a panel. → Same window and timing as challenges; measured as time to settle.
- **[Sponsorship cartels]** Sponsors could vouch for each other's sybils. → Every slash hits the sponsor's own money. The abuser scenario measures it.
- **[Capital locked longer]** Instalments hold rewards for about 4 weeks. Honest returns arrive later but aren't lower; the report shows both totals and timing.
