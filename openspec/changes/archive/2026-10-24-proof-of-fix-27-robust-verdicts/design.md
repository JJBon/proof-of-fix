# Design

## Context

Today, `acceptance()` in `pof/sim/report.py` judges criteria in two ways:
- **"Defective work loses money"** uses the pooled mean per defective contribution for each author kind, with no error bound. It fails if the mean is at or above zero.
- **Splitting, collusion and the owner** use the mean of per-seed differences, with two standard errors.

The 100-seed check (#27, comment 3637) found:
- the newcomer's pooled mean is +6.3 ± 14.3;
- the abuser at elasticity 0 is −14.7 ± 12.2, from about 80 contributions;
- splitting is +802 ± 205, while per accepted line it's 0.64 split against 0.79 unsplit;
- capped excess of 25,000–27,000 credits builds up in the contributors' pool.

A run is fast (100 seeds of the four attack scenarios take about 10 seconds), but the summary repeats the acceptance check for each sweep row. That's 30 rows today.

## Goals / Non-Goals

**Goals:**
- Verdicts that separate a real effect from noise.
- An honest splitting test.
- Enough samples to judge every attacking group.
- A rule for capped excess.

**Non-Goals:**
- New mechanism rules besides funding.
- Retuning stakes or caps. That's only allowed in the open, if v5 requires it (task 4.2).

## Decisions

### D1. Standard errors clustered by seed
For each author kind, every run (one scenario on one seed) gives a sum S_i and a count n_i of defective contributions. The pooled mean is m = ΣS_i / Σn_i. Its standard error is the ratio estimator's, clustered by run:

SE² = k / (k − 1) × Σ (S_i − m·n_i)² / (Σn_i)², over the k runs with defective contributions.

Contributions within one run share a path (releases, hunters' attention), so treating them as independent would understate the error.
- *Alternative:* bootstrap over seeds. Rejected: it gives similar answers here, but adds randomness and run time.

### D2. Attackers must lose money; honest mistakes must not pay
- **Attacking kinds** (spammer, splitter, padder, sybil, ally, abuser, stacker, gamer) pass only if m + 2·SE < 0. The mechanism's claim is that attacks lose money, and "not shown" isn't enough.
- **Honest-intent kinds** (honest, owner, newcomer) fail only if m − 2·SE > 0. Their defects are accidents. The mechanism must not reward them, but proving that honest people lose on their mistakes isn't the goal, and with sponsors' shares involved it can't be shown cheaply.
- **Inconclusive:** an attacking kind with fewer than `MIN_DEFECTIVE_SAMPLE` = 50 defective contributions over the seeds fails as inconclusive, and the report gives the count. 50 keeps a single escaped reward (up to 6 × the stake) from deciding the sign.
- `MIN_DEFECTIVE_SAMPLE` is a constant of the acceptance check, not a mechanism parameter.

### D3. Splitting per accepted line
For each seed, the criterion takes the splitter's net return divided by its lines accepted, split and unsplit. The split-minus-unsplit difference per line, as a mean over seeds with two standard errors, must not be significantly positive.

The report also gives lines accepted and unaffordable submissions for both. The capital effect stays visible: small contributions fit a balance, so more of the same work ships.
- *Why not keep the total-return comparison:* the unsplit counterfactual ships about 40 % fewer lines (unaffordable giant contributions, and the 1,500-line weight cap per contribution). It compares different amounts of work. Weight gaming would show as a higher return per line, and that's what this measures.
- *Risk:* a splitter that is paid more per line *because* it's split would still be caught. One that gains only by shipping more is accepted, because shipping reviewable pieces is good practice.

### D4. 100 seeds for verdicts, 20 for sweeps
- `summary --seeds 100 --sweep-seeds 20`: the main verdict and the per-actor tables use 100 seeds. The sweeps and ablation rows use the first 20, and their rows say so.
- `accept --seeds N` is unchanged. Expected run time is about 10 minutes.
- *Alternative:* 100 seeds everywhere. Rejected for the development loop (about 30 minutes). It's easy to run occasionally.

### D5. Three abusers in the sponsorship scenario
Three abusers, each with its four fake accounts, replace the single one, so the abuser group has about 240 defective contributions over 100 seeds. That's enough to judge it (D2). Each abuser behaves as before, and the honest population is unchanged.

### D6. Funding follows use
| Parameter | Default | Rationale |
|---|---|---|
| `pool_buffer_releases` | 2 | The contributors' pool may hold up to two releases' worth of the contributors' share. That's enough for the normal rollover after a quiet release and for the instalments in flight. 0 switches it off. |

When a release opens:
- S is the contributors' share of the full funding, P is the pool's balance, and B is the buffer;
- the release issues funding × f, where f = clamp(1 − (P − B·S) / S, 0, 1);
- the split is applied to the reduced funding, and the ledger records f as a `funding_scaled` event.

The same factor applies to every share, so validators, the author's escrow, infrastructure, insurance and the owner earn less when contributors' work doesn't use the money. Nobody gains from quiet releases.

**Sweep:** `pool_buffer_releases` 0, 1, 2 and 4.

### D7. What could change in v5
- **Validators and the owner earn less in the small scenarios,** where the cap binds. "Honesty pays" must still hold for validators.
- **The stake index is unaffected:** the offered rate uses the pool, which stays at the buffer.
- **The earlier reports keep their numbers,** but v5's write-up states that their splitting and defective-work passes were 20-seed verdicts, and which of them don't hold at 100 seeds.

### D8. What the implementation changed (task 4.2)
- **Splitting per accepted line uses the pooled ratio,** not the mean of per-seed ratios. The total return over total accepted lines is taken on each side, with standard errors clustered by seed as in D1, and the difference's error combines the two. Averaging per-seed ratios blew up when a run got few lines accepted: it showed +6.8 per line, against a return of about 1 per line.
- **Correction to the motivation:** the proposal's "per accepted line, splitting earns less (0.64 against 0.79)" divided by *submitted* lines. Per accepted line, splitting earns **more**: +0.28 ± 0.17 at elasticity 0.5 (not significant), and +0.55 ± 0.16 at 0 (significant).
  - **First cause:** the 1,500-line weight cap per contribution. 35 % of the unsplit runs' accepted lines are above it and earn nothing.
  - **Second cause:** partial acceptance. When some parts fail, the others still pay, and the per-author cap binds less.

  Both come from paying per line, the placeholder that the market model (#15) replaces, so no parameter is tuned for it here (#27, comment 3650).
- **Sweep rows show "inconclusive" apart from failures.** On 20 sweep seeds the abuser group has fewer than 50 defective contributions, so every row came out "inconclusive". Each row now gives `passed` (strict) and `passed_except_inconclusive`, and lists the inconclusive groups. The verdict on 100 seeds stays strict.
- **100-seed verdicts at elasticity 0 and 1** (`elasticity_verdicts`), next to the main verdict at 0.5. The bar in task 4.2 is all three on the verdict seeds, and the 20-seed elasticity sweep can't judge it.

## Risks / Trade-offs

- **Stricter for attackers, lenient for honest kinds:** an asymmetric test is a choice, and it's the owner's to approve.
- **Per-line splitting accepts a capital advantage for small contributions.** If that advantage is later judged unwanted, it's a stake-granularity question, not a weight one.
- **Funding cuts reduce validator income** in quiet periods. If "honesty pays" fails for validators, the buffer is too small.
- **A longer summary** (about 10 minutes); the sweeps are noisier at 20 seeds.
