# Design

## Context

The market awards jobs by sealed second-price rounds, bid first and build after (#30–#40), checked by attested runners and AI consensus juries (#43, #47), with the contributor paying its checks (#49). Checking v6 passes every criterion. The owner's alternative removes bids: funders set the price, an AI check gates registration, the project's constitution gates delivery, and the first fix through the gates wins. This design adds that as a mode, plus a claim variant, and compares them on the same seeds.

## Decisions

### D1. Award modes, the auction by default
- `award_mode` ∈ {`auction`, `race`, `claim`}, default `auction`. The auction's code paths don't change, so checking v6 reproduces in that mode.
- Making `race` or `claim` the default is the owner's decision, after the comparison (D8).

### D2. The registration check
- `registration_fee` = 2 credits, paid in coin by whoever opens the bounty: a pledger, the reporter, or the treasury. It's the cost of one AI check, the same as the evaluation fee.
- **The size floor:** `size_floor_lines` = 20. GridCraft's merged PRs have a median of 76 changed lines (#8), so 20 leaves out one-liners and trivial edits.
  - Issues below the floor wait in a bundle pool. When the pool's estimates add up to the floor, they open as one bounty.
- **The effort estimate:** the issue's true cost times a lognormal error (`estimate_error` = 0.3). It sets the claim time (D5), and later #58's token weight.
- **In the simulation the author always approves the criteria.** The AI writing wrong criteria is modelled as gate error (D6).

### D3. Prices set by funders
- In `race` and `claim` the price is the bounty's funds: pledges, matching and treasury, less the market fee. There's no reserve, since nobody bids.
- **Top-ups:** `top_up_bps_per_week` (default 0). An unattempted bounty's pledgers add this share of the issue's value each week, up to its value. That's how an underpriced bounty attracts solvers. It's swept in D8.
- **0 coin:** a bounty that passed registration with no funds stays open. In this change nobody is paid to solve it; #58 adds tokens.

### D4. The gated race
- **Solvers see each open bounty's price and the published number of attempts in progress, k.**
- **A solver attempts when** price × 1/(k+1) − its cost − its expected checks > 0, priced from its own record as today. The 1/(k+1) is its naive chance of being first.
- **Attempts take the solver's build days,** with effort accruing daily. When a bounty is won, every other attempt stops; the effort spent so far is wasted and counted (D7).
- **The submission:** sealed, with the check deposit (#49). The attested runs, the jury, then the gates (D6), in arrival order.
  - **A failure** pays its checks from the deposit and ends that attempt. The bounty stays open.
  - **A late submission** (after a win) gets its deposit back unchecked.
- **No bond in the race:** nothing is assigned. Junk is deterred by the solver paying its own checks.

### D5. Claim then build
- **The bond** is today's stake (`stake_for`), a share of the bounty's funds, with the trust discount.
- **The exclusive time:** `claim_days` = 1.5 × the estimated build days, at least 3.
- **A failed delivery or a timeout** forfeits the bond to the bounty, and the bounty is open to claim again. The first solver to claim it on a later day takes it.

### D6. Fix quality and the constitution
- **Each solver has a quality level** (`quality`): honest solvers about 0.8 (lognormal spread around it, from the same skill stream); half-fixers and junk solvers lower. A fix's quality is the solver's level plus noise.
- **The gates measure it with an error** (`gate_accuracy`, a standard deviation of 0.05). A fix passes if its measured quality is at least `gate_bar` = 0.7. The existing defect, incomplete-fix and jury models still apply on top.
- **Padded tests:** a padder's fixes look like quality 0.9 to coverage, but the mutation gate catches them with `mutation_catch_bps` = 9,000.
- **"Good fixes accepted":** good means no defect and true quality at least the bar. The gates' false rejections are counted with the jury's.

### D7. What's measured
- per mode, on the same seeds:
  - honest solvers' earnings net of effort;
  - **wasted effort:** effort on attempts that weren't paid, as a share of all solver effort;
  - funders' cost per solved bounty;
  - bounties solved and unsolved;
  - good fixes accepted;
  - time from opening to a winning delivery.
- **New attacks,** each against its honest twin:
  - **spam poster:** opens junk bounties that pass registration, paying the fee. Its cost, and the bounties it crowds out, are reported.
  - **padder:** submits padded fixes.
  - **second identity racing:** one attacker submits variants from two accounts.
  - **inflater:** its issues' estimates are biased up, for longer claims and to slip under the floor.
- **Rings** run in every mode. In the race and the claim, a ring's members agree not to race or claim against each other.

### D8. The acceptance run (modes v1)
- **Each mode's verdicts on 100 seeds,** at hunting elasticity 0.5, all existing criteria included. Sweeps only for race and claim, on 20 seeds:
  - attempt cost (`cost_per_line` 0.1, 0.5, 1 and 2): cheap AI runs to expensive human work;
  - `gate_accuracy`;
  - `gate_bar`;
  - `registration_fee`;
  - `top_up_bps_per_week`.
- **The report recommends a default with the numbers,** and the owner decides.
  - **If race or claim becomes the default,** #55 is withdrawn (rings have no price to bend) and #58 builds on it.
  - **If the auction stays,** #55 goes ahead.

## Risks

- **Racing may cost more than it saves:** with costly attempts, wasted effort could push honest solvers' earnings below cost. The sweep shows at which attempt cost that happens.
- **The gates' accuracy is assumed,** like the juries' before #47. It's swept, and the real-data measurement covers it later.
- **Three modes triple the run time** (about three hours in all).

## Implementation notes (tasks 1–2)

- **The race's stake.** The lifecycle needs a stake on every contribution, so a later slash or clawback has something to take. A race submission therefore posts the contribution's stake (`stake_for`) with its check deposit.
  - If the submission fails, the stake returns: there's no bond to forfeit in the race, as D4 says.
  - If it wins, the stake backs the accepted contribution through the challenge window and clawback, as in every mode.
  - Solvers price only the later slash risk into the race, not a forfeited bond (`_min_price`).
- **Registration in the simulation.** Reporting an issue is registering it, so in race and claim the reporter pays the registration fee and the issue stake together. Self-dealers, match farmers and inflaters pay for their own issues.
- **Bundles** open as treasury bounties, from their parts' summed value and lines. The parts' issue stakes return when they're bundled.
- **Bounties of 0 coin** are allowed by the mechanism (`open_bounty(0)` opens at once). The simulation generates none until tokens exist (#58), since nobody is paid to solve them.
- **Rings in the race:** a ring's members don't race each other (D7). In the claim, the first claim already excludes the others.
- **The variant racer:** when its submission fails, its second account submits the same fix as a variant the same day. That costs new checks, not a new build.
- **The inflater:** posts small issues of its own (8–14 lines). Their doubled estimates slip over the 20-line floor, where an honest estimate would bundle them. It then funds and solves them like a self-dealer.
- **Idle bounties:** a race or claim bounty with no attempt or claim for `bounty_max_rounds` × `round_days` closes unsolved, as empty rounds would in the auction.
- **The auction's path is unchanged:**
  - fix quality, gate and estimate draws come from their own stream (`mode_rng`);
  - the auction never gates;
  - a 3-seed acceptance run is byte-identical to main's.

## D9. The owner's decisions on modes v1 (2026-10-25)

Modes v1 ([`reports/acceptance-modes-v1.md`](../../../reports/acceptance-modes-v1.md)): the race fixed 31 % more bounties in half the time, at higher quality. It failed four criteria, and funders paid about 3× the auction per fix. The owner chose:
1. **A duplicate check with one appeal:** a resubmission of a failed fix (AI similarity, recognized with `duplicate_catch_bps` = 9,000) is rejected unchecked from any account, for the evaluation fee. The author may appeal once, paying `rerun_appeal_fee` and a new deposit, to the second jury.
   - In the simulation, an honest solver appeals only a fix it knows is good (no defect, quality at the bar).
   - An appealed or resubmitted fix keeps its defect and quality; only its checks run again.
2. **The registration fee refunded when solved:** with the finder's fee, from the bounty (`price_cap` leaves room for it). A bundle's parts' reporters share the finder's fee, each with its registration back.
3. **A rising price:** a bounty opens at `start_price_bps` = 5,000 of its price cap and rises by `price_rise_bps_per_day` = 1,000 a day. The first attempt (race) or claim locks it, and the rest of the funds is refunded when it's paid.
4. **Criteria the race can't apply:** a no-show can't take a job and a reputation farmer can't win one low and walk away, since nothing is assigned.
   - In the race, the no-show mustn't gain ("no-shows can't gain").
   - The reputation farmer mustn't earn more than an honest solver ("reputation farming doesn't pay").

## Modes v2: the race becomes the default

Modes v2 ([`reports/acceptance-modes-v2.md`](../../../reports/acceptance-modes-v2.md)): **the race passes every criterion.** With D9 applied, funders' cost per fix fell from 177 to 116, and the variant racer's gain from +103 to +6.9 ± 15 (not significant). Reporters earn +1.4.

As the owner decided, `award_mode` now defaults to `race`. `AUCTION` (in `pof/params.py`) and `--award-mode auction` keep the sealed rounds, to compare with and to reproduce earlier runs. A 3-seed acceptance run in that mode is byte-identical to main's. The tests of the auction's mechanics use `AUCTION`.

**#55 is withdrawn:** in the race there's no price for a ring to bend, and modes v2 shows no ring gaining. Its change folder stays unapplied, to be closed with the archive.

**Carried to #56 (the contract):**
- a refundable deposit to start an attempt, against fake attempts that scare competitors off or lock the rising price low;
- an appeal for fixes rejected as someone else's duplicate;
- what "solved" means on-chain.
