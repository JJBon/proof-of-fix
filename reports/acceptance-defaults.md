# Acceptance run: default parameters (2026-10-24)

**Command:** `python3 -m pof.sim summary --seeds 20 > reports/acceptance-defaults.json` (seeds 1–20, 8 weeks each). The full numbers are in [`acceptance-defaults.json`](acceptance-defaults.json). The whole run takes about 1.5 s.

**Result: the defaults fail.** Every failure is listed below with the change proposed for it. The changes are a follow-up OpenSpec change, not edits to the defaults here (task 8.1).

## Failures by criterion (count over 20 seeds)

| Criterion / scenario | Failures |
|---|---|
| attacks lose money / spam | 40 (spammer and splitter, every seed) |
| attacks lose money / collusion | 60 |
| collusion threshold / collusion | 20 |
| owner can't gain by defecting / owner | 12 of 20 seeds |
| honesty pays / honest (validators earn 0) | 11 |
| honesty pays / spam (validators earn 0) | 4 |

The **griefing** criterion passes: griefers lose money on every seed (mean −57 credits).

## Returns per actor type (credits over 8 weeks, mean of 20 seeds; min..max)

| Actor | honest | spam | griefing |
|---|---|---|---|
| honest contributor | 3,775 (3,142..4,277) | 2,453 | 3,791 |
| hunter | 8 (2..19) | 30 | 7 |
| validator | 392 (**0**..1,167) | 784 (**0**..1,333) | 1,251 |
| owner (honest) | 12,667 | 10,094 | 13,159 |
| spammer | — | **3,027** (1,936..3,797) | — |
| splitter | — | **6,533** (2,083..11,544) | — |
| griefer | — | — | −57 (−92..−28) |

## Collusion (mean of 20 seeds)

| Colluders' share of validator stake | Ring total | Colluding validators (each) | Allied spammer | Escaped regressions |
|---|---|---|---|---|
| 10 % | 5,593 | 68 | 5,319 | 4.1 |
| 20 % | 6,151 | 227 | 5,242 | 4.0 |
| 30 % | 6,490 | 317 | 5,223 | 4.2 |
| 40 % | 7,384 | 526 | 5,281 | 4.5 |
| 50 % | 8,479 | 773 | 5,387 | 4.1 |
| 70 % | 7,539 | 558 | 5,305 | 4.2 |

**Measured threshold:** the colluding validators are in profit from a 10 % share. The published threshold is 33 %.

**Reading it:** the allied spammer's income hardly changes with the colluders' share (about 5,300 at every share). So the ring profits from **spam**, not from collusion. The colluders also earn as ordinary validators on every challenge outside their group, and the criterion doesn't separate that. **The criterion is mis-specified:** it should compare the ring with the same actors acting honestly on the same seed (a counterfactual), not with zero.

## Owner: honest vs self-interested

| | Payout (mean; min..max) |
|---|---|
| Honest (contributes 2 PRs a week, validates) | 12,667 (7,176..23,838) |
| Self-interested (also declines others' PRs, shifts the split toward validators) | 13,006 (9,729..20,065) |

Defecting paid on **12 of 20 seeds**, by about +2.7 % on average. The self-interested owner declined about 23 PRs per run, which pushed more of the pool to its own contributions.

## Risk sweep and replay

- **Risk multiplier (1×, 2×, 3×):** no measurable effect on returns or on escaped regressions (7.3 per run at every multiplier). Stakes are so small next to rewards that pricing risk changes nothing. Revisit after the stake and detection changes.
- **Replay at GridCraft's volume** (about 1,780 contributions per run): honest +1,073, validators +749, hunters +104. Regressions escaping: 21.7 (1.2 %).

## What-if: raising the stake alone

| `base_stake` | honest | spammer | splitter | hunter | contributions |
|---|---|---|---|---|---|
| 10 (default) | 2,453 | 3,027 | 6,533 | 30 | 254 |
| 100 | 2,555 | 3,037 | 3,955 | 262 | 223 |
| 300 | 2,739 | 2,757 | 2,302 | 400 | 133 |
| 600 or more | 0 | 0 | 0 | 0 | **0**: nobody can afford a stake from a 500-credit starting balance |

**A stake big enough to deter spam also locks out honest contributors.** The expected penalty is `P(defect) × P(caught) × slash × stake`, and P(caught) is the weak factor: hunters earn too little (8–30 credits) to look hard. So the fix must raise detection and the cost of being caught, not only the stake.

## Proposed changes (follow-up change, proof-of-fix#10)

1. **Spam: raise detection and claw back the reward.**
   - (a) On an upheld challenge, the challenger gets a share of the contribution's **escrowed reward**, not only of the stake. Today the reward goes back to the pool and the hunter earns about 8 credits; this would pay hundreds per catch.
   - (b) **Review duty:** each contribution entering beta gets one randomly drawn validator reviewer, paid from the validators' pool. That raises the chance a defect is caught, and fixes validators earning 0.
   - (c) The reward is paid in instalments over a longer clawback period, so later-found defects still cost.
2. **Splitter:** make the reward weight about linear in changed lines (capped), so splitting one change into eight earns no more. Each piece still pays its own stake and check fee.
3. **Validators earning 0:** solved by 1(b).
4. **Collusion criterion:** measure the ring against the same actors acting honestly on the same seed, and re-run the threshold sweep.
5. **Owner:**
   - the owner's own contributions need approval from another maintainer (or a validator panel);
   - the owner's declines are rate-limited and recorded, and can be appealed by the declined contributor;
   - a split change that the owner would gain from (directly, or as a validator) can't come from the owner alone.
6. **Risk class:** keep it at "normal" (no effect now); re-test after 1–2.
7. **Starting capital:** simulate a stake that can be posted from the expected reward (an advance), so stakes can grow without locking out honest newcomers.
