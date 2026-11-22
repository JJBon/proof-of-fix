# Design

## Context

This is a new repository: there is no code yet, only the bootstrap (README, OpenSpec, the `pof / check` CI). The baseline numbers come from it-ops#14 (comments 3322 and 3323), a GridCraft sample from 2026-10-23:
- **merged PRs:** median 78 changed lines, p90 314, max 687; median 18 h to merge;
- **oldest open PRs:** median 1,098 lines, p90 13,194;
- **volume:** about 136 merged PRs a week, from 16–21 active authors;
- **review:** a human review on about a quarter of merged PRs;
- **merges:** 4 maintainers.

The project's rules are in `openspec/config.yaml`: simulation only, respect for the upstream author, the owner's stake aligned, and upstream code only in containers.

## Goals / Non-Goals

**Goals:**
- A small mechanism library that implements the five specs, plus a simulation that exercises it and produces the report its acceptance criteria need.
- Parameters as named values in one place, each with its rationale, so the simulation can sweep them.
- Runs that are deterministic and fast enough to sweep many seeds in CI-sized time.

**Non-Goals:**
- Modelling GridCraft's code. Defects and proofs are simulated ground truth here; real builds and tests are a later change.
- Optimizing the parameters. This change sets defensible defaults and measures them; tuning is a follow-up.
- A user interface. The output is a report file.

## Decisions

### D1. Python standard library only
The mechanism and simulation are in Python 3, standard library only. The `pof / check` job runs on the CI host's plain shell, with no installs and no network beyond the checkout. `random.Random(seed)` gives deterministic runs.
- *Alternatives:* Rust, closer to the upstream (rejected: slower to iterate on the economics, and nothing here touches upstream code yet); NumPy or Mesa (rejected: dependencies on the CI host for little gain at this scale).

### D2. Integer micro-credits
Every amount is an integer number of micro-credits (1 credit = 1,000,000). Splits round down, and the remainder goes to the insurance pool, so conservation is exact and testable as an equality.
- *Alternative:* floats or Decimal (rejected: floats drift; Decimal works but adds noise for no gain over integers).

### D3. Layout
- `pof/ledger.py`: accounts and append-only entries, with a conservation check.
- `pof/params.py`: one frozen dataclass of parameters, with validation such as shares summing to 1 and the owner cap.
- `pof/lifecycle.py`, `pof/challenges.py`, `pof/payouts.py`: the three behaviour specs, as pure state transitions over the ledger.
- `pof/sim/`: `actors.py`, `scenarios.py`, `report.py`, and `__main__.py` (`python3 -m pof.sim run --scenario <name> --seed <n>`).
- `data/gridcraft_baseline.json`: aggregated history (distributions and counts only).
- `scripts/fetch_baseline.py`: rebuilds that file from the GitHub API. It aggregates in memory and never writes a username.
- `tests/`: `unittest`, run by `scripts/check.sh`.

### D4. Time and releases
The simulation is discrete, one step per day, with a release every 7 days. Each release is funded with `release_funding` credits. Where this money comes from (sponsors, donations, sales) is outside the mechanism, so it's an input.

### D5. Parameters (defaults)

| Name | Default | Rationale | Swept by |
|---|---|---|---|
| `size_tiers` | ≤100, ≤400, ≤1,500, >1,500 changed lines | Brackets the baseline: merged median 78, merged p90 314, stale median 1,098 | — |
| `stake_multiplier` per tier | 1×, 2×, 5×, 10× `base_stake` | Large PRs carry more risk and review cost; the steep top tier pushes toward splitting | spam, replay |
| `validators` per tier | 3, 3, 5, 7 | More eyes on larger changes; odd numbers for a majority | collusion |
| `reward_weight` per tier | 1, 2, 4, 6 | A contribution's share of its release's contributors' pool. It grows more slowly than the stake (1, 2, 5, 10), so a very large PR risks more than it can earn, nudging toward smaller PRs. The spam scenario's splitting variant checks that splitting doesn't pay | spam, replay |
| `risk_multiplier` | normal 1×, high 2× (on the tier's stake); **every contribution is "normal" by default** | The lifecycle spec makes the stake grow with risk as well as size, but which changes are risky is hard to tell in advance (owner, 2026-10-24). So nobody classifies risk for now. The simulation tries it: scenarios where a share of contributions is high-risk (more likely to hide a defect), with multipliers 1×, 2× and 3×, to see whether classifying risk is worth having at all | risk sweep |
| `base_stake` | 10 credits | Small next to a typical reward, so honest newcomers can join | spam, honest |
| `check_fee` | 2 % of the stake | Pays the deterministic gate; makes failing spam cost something | spam |
| `challenge_window_days` / `extension_days` | 7 / 3 | One release cycle of beta use; one extension for a pending challenge | replay (time to settle) |
| `severity_slash` | crash or data loss 100 %, wrong result 50 %, cosmetic 10 % | Honest mistakes don't wipe out a contributor; real damage costs the full stake | honest, spam |
| `challenger_reward_share` | 50 % of what's forfeited (the rest to insurance) | Enough to make looking for bugs worth it, without making false positives profitable | griefing |
| `challenger_stake` | 50 % of the contributor's stake | Griefing has to cost something comparable to what it threatens | griefing |
| `rejected_challenge_loss` | 50 % of the challenger's stake | Same reason, from the other side | griefing |
| `filing_fee` | 2 % of the challenger's stake | A challenge refused for lack of proof still costs a little | griefing |
| `validator_bond` | 5 credits per challenge | Lets commit-reveal penalties bite | collusion |
| `no_reveal_penalty` / `overturned_penalty` | 20 % / 50 % of the bond | Not revealing is a minor fault; being overturned on appeal is a bigger one | collusion |
| `appeal_stake` / `jurors` | 2× the challenger's stake / 2 × validators + 1 | Appeals are possible but not free; a larger panel resists a captured validator panel | collusion |
| `collusion_threshold` | ⅓ of total validator stake | A random panel is rarely majority-captured below it. The simulation measures where collusion actually starts to pay | collusion |
| `release_split` | contributors 50 %, validators 20 %, author 10 %, infrastructure 10 %, insurance 5 %, owner 5 % | Most value goes to the people doing the work. The author's share is visible respect. The owner's is small and fixed | all |
| `owner_share_cap` / `owner_vesting_months` | 5 % / 24 | Disclosed, small and long-term. Unvested amounts go to insurance if the owner leaves | owner |
| `insurance_limit_per_release` | 50 % of the pool | The pool can't be drained by one release | replay |
| `ai_review_accuracy` / `ai_injection_susceptibility` | 0.85 / 0.3 unhardened, 0.0 hardened | AI review is a noisy, advisory signal; the hardening removes the injection path | spam (injection variant) |
| `replay_inconclusive_rate` | 5 % | Flaky or environment-dependent proofs go to validators | griefing, replay |
| `release_funding` | 10,000 credits a week | A placeholder scale; the criteria compare signs and ratios, not absolute amounts | — |

### D6. Ground truth in the simulation
Each simulated contribution has a hidden `defect` (none, cosmetic, wrong result, crash) drawn from the actor's defect rates. A challenge's proof is valid only if the challenged contribution really has a defect. The deterministic replay reveals a valid proof, except at `replay_inconclusive_rate`. Validators vote on the truth, except for a configurable error rate; colluders vote as their group decides. This keeps every layer measurable against the truth.

### D7. What the owner can do in the simulation
The owner model tries every move the specs allow:
- propose parameter changes, which take effect only at the next release and are capped;
- decline other people's contributions while acting as a maintainer;
- contribute and validate with their own separate stake;
- time releases.

The owner's payout in the acceptance criterion is the **total** across all of these: owner share plus contributor and validator earnings. That makes self-dealing as a maintainer (declining others, merging one's own) count against the owner.
- *Alternative:* forbid the owner from being a maintainer (rejected for the PoC: the owner is the only maintainer of this repository; the simulation shows whether it matters).

### D8. Baseline data and privacy
`scripts/fetch_baseline.py` uses the GitHub search API through `gh`. It keeps histograms of PR size, time to merge, review counts and weekly volume. Author identities are used only to count distinct authors, then dropped. The committed JSON has no usernames, PR titles or numbers, and a test checks that.

### D9. Challenge details decided when building (`pof/challenges.py`)
The spec leaves these open; each is the simplest rule consistent with it.
- **Tie or no counted verdicts:** the challenge is rejected and the contribution stands (the burden of proof is on the challenger).
- **A rejected challenger's loss** (`rejected_challenge_loss_bps`): half to the contributor and half split equally among the members whose verdicts counted. All of it goes to the contributor when no panel judged it.
- **Appeal stake:** returned when the jurors overturn the decision, forfeited to insurance when they confirm it.
- **Penalties** (`no_reveal_penalty_bps`, `overturned_penalty_bps`) go to insurance; together they never exceed one bond.
- **A second upheld challenge on a contribution already slashed** takes nothing more (the cap). The challenger gets their stake back but no reward: the first valid report wins.
- **Validator draw:** stake-weighted, without replacement, seeded by `sha256(challenge id, beacon)`. The beacon is recorded at filing, and parties and declared links are excluded. Jurors also exclude the validators who already judged.
- **AI review:** two reviewers, each right with `ai_review_accuracy_bps`, and comments removed. Its recommendations are recorded but never decide a slash.

### D10. When a contribution's reward is funded (owner, 2026-10-24: option A)
The lifecycle spec escrows the reward on entry to the beta build, and the first payouts spec divided a release's share among contributions that **settle** in it, about a week later. Chosen: **each release's contributors' share is divided, by reward weight, among the contributions entering that release's beta build, and escrowed then.** Each contribution is paid when it settles as accepted; a slashed contribution's share returns to the pool and rolls over to the next release. The `release-payouts` requirement was changed to match.
- *Rejected B:* escrow an estimate and correct it at settlement. Both specs stay as written, but the amount in escrow isn't final and the settlement logic doubles.
- *Rejected C:* pay at settlement only. Simpler, but contributors can't see their reward up front, and the lifecycle spec's escrow disappears.

### D11. Payout details decided when building (`pof/payouts.py`)
- **Validators' pool:** at a release's close, the whole pool (this release's share plus rollover) is divided among members in proportion to their counted verdicts that matched final outcomes. If nothing matched, it rolls over.
- **Insurance limit:** fixed when the release opens, at `insurance_limit_bps` of the insurance balance then. Only upheld "crash" (crash or data loss) challenges are covered.
- **Owner vesting:** each release's owner share is a tranche that vests linearly over `owner_vesting_months` (30-day months) from the day it's funded. After the owner leaves, the owner share of later releases goes to insurance.
- **Author's claim:** the signed statement and an upstream commit must name the same key, and that key must be in the upstream repository (simulated as a set of published keys). Only a verified claim opens an account for the author.
- **Parameter changes** are recorded as ledger events (`Ledger.record`), which move no money, and apply from the next release.

## Risks / Trade-offs

- **[Simulated ground truth flatters the mechanism]** Real proofs are messier than a hidden flag. → `replay_inconclusive_rate` and the validator error rates model the mess. The later change with real GridCraft builds re-measures them.
- **[Defaults chosen by hand]** → Each one is in the table with its rationale, and every acceptance criterion is checked across several seeds. Tuning comes in a later change.
- **[Release funding is assumed]** Without real income there's nothing to split. → The criteria use signs and ratios, which hold at any scale. Where funding comes from is a business question for the PoC review.
- **[Splitting PRs to farm rewards]** Per-contribution rewards can favour many tiny PRs. → The check fee and per-PR stakes make each split cost something. The spam scenario includes a splitting variant.
- **[The owner as the only maintainer]** → Covered by D7. If the owner scenario fails, the fix is a rule that maintainers' own contributions need a different maintainer or a larger panel.

## Open Questions

- The exact reference implementation for GridCraft formula proofs (LibreOffice headless is the candidate). It matters only in the later change with real builds.
- The cryptographic form of the author's claim (which signature scheme). The spec fixes what must be proven; the format can follow the chain choice after the PoC.
