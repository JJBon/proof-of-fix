# Design

## Context

The enforcement layer is in place and validated on 100 seeds (`reports/acceptance-v5.md`):
- `Lifecycle`: stakes, the gate, beta, the challenge window, instalments, clawback, pledges;
- `Challenges`: proof, panels, review duty, appeals;
- `Releases`: funding, the split, the validators' pool paid per unit of work.

Rewards come from the legacy pool. `open_release` issues `release_funding` (10,000) and splits it; `ship_beta` divides the contributors' share by weight. The simulation's contributions are random PRs sized from GridCraft's history. There are no issues, no users and no prices.

The brief (#15) fixes the flow:
- bounty, pledges, sealed second-price round, checking, payment on release in 4 instalments with clawback;
- defaults: payment on our distribution's release; AI-proposed treasury bounties for unpledged work; no per-release pool for unpledged work.

## Goals / Non-Goals

**Goals:**
- The market sets each contribution's price; the enforcement layer stays untouched.
- Every attack in scope is measured with v5's statistics.
- The legacy mode keeps working, for comparison.

**Non-Goals:**
- The AI jury, reputation, decentralized checking, bug planters, the real-data measurement, royalties (later changes under #15).
- Retiring the legacy specs.

## Decisions

### D1. A mode switch, not a fork
- `reward_source` is `"pool"` (legacy, the default until the market passes) or `"market"`.
- **In the market mode:**
  - `open_release` issues no per-release funding;
  - the treasury budget is issued only when a treasury bounty is funded, so unspent budget never exists;
  - `ship_beta` escrows each winner's price from its bounty, not from the pool;
  - market fees fill the validators' pool, which `close_release` still pays per unit of work;
  - everything else is shared.
- *Alternative:* a separate simulator. Rejected: the enforcement layer must be the same code that v5 validated.

### D2. Parameters (defaults)
| Parameter | Default | Rationale |
|---|---|---|
| `reward_source` | `"pool"` | The market becomes the default only once it passes (task 4.2) |
| `bounty_deadline_days` | 14 | Two releases to gather pledges |
| `round_days` | 7 | One release to commit; reveals the day after |
| `bounty_stake_bps` | 4,000 | The stake is 40 % of the price cap. That's the stake share of the expected reward that v4 and v5 passed with; here the reward is known in advance |
| `evaluation_fee` | 2 credits | Covers a gate run (the legacy check fee was 1.5 on a 75-credit stake), and makes bidding on many jobs cost something |
| `delivery_days` | 14 | Two releases for the assigned solver to deliver; the bond is forfeited after that (D9) |
| `market_fee_bps` | 2,000 | 20 % of the price, split 40/20/20/10/10 among validators, author, infrastructure, insurance and owner (the legacy split's non-contributor proportions). The owner gets 2 % of each price, within the 5 % cap. The price cap is the bounty ÷ 1.2 |
| `treasury_budget` | 2,000 credits per release | "Small": a fifth of the legacy funding |
| `treasury_bounty_cap` | 500 | One proposal can't take a quarter of the budget |
| `treasury_approval_above` | 300 | Larger proposals go to a validator panel |
| Instalments, windows, slashes | as v5 | The enforcement layer is unchanged |

### D3. Checking and the winner (superseded by D9: bids carry no solution)
- **Order:** revealed entries are checked cheapest first, through the deterministic gate only, until two pass or none remain.
- **Valid** means passing the gate. Defects that pass the gate are the lifecycle's job (review duty, hunters, clawback), as now.
- **The winner** is the cheapest that passes, at the second-lowest passing price, or at the cap if it's alone.
- **Unchecked entries** get their stake and fee back. Those that fail the gate lose the fee.
- **Runner-up:** if the winner is slashed or clawed back, the next passing entry of the same round wins at the next passing price or the cap. A new round opens only when none remain. This stops copying of revealed work across rounds.

### D4. Leftover and refunds
- After the winner's last instalment, the bounty's remainder returns to its pledgers, pro rata, rounded down; the rounding remainder goes to the last pledger.
- A treasury bounty's remainder goes to insurance. It was never anyone's pledge.
- A bounty that misses its target refunds every pledge in full.

### D5. The simulation's issues and solvers (assumptions, swept)
- **Issues** arrive at GridCraft's merged-PR rate (the baseline's weekly volume).
- **Value** to users is log-normal, with a median of 100 credits.
- **Pledging:** a share of issues (`pledged_share`, 40 %) attracts pledges up to its value. The rest are candidates for the treasury, with a priority score.
- **Difficulty** comes from the baseline's size distribution, as the PR size of the fix.
- **Cost:** a solver's private cost is difficulty × its skill (log-normal around 1) × a cost per line. It knows its cost exactly.
- **Defects:** the chance rises with difficulty and falls with skill.
- **Entry:** solvers enter rounds whose cap is above their cost.
- **Sweeps:** the cost per line (cheap and dear), `pledged_share`, and the number of honest solvers (thin and thick markets).

### D6. Actors
| Actor | Behaviour |
|---|---|
| Honest solver | Bids its cost. Second price makes that its best strategy |
| Bluffer | Bids 1.5 × cost |
| Lowballer | Bids 0.6 × cost |
| No-show (D9) | Bids 0.5 × cost to win the job, and never delivers |
| Ring of k | For each bounty, only the member with the lowest cost bids, at its cost; the others stay out. The counterfactual is the same k solvers each bidding their cost |
| Spam solver | Enters many rounds with cheap, untested solutions (high defect rate) |
| Treasury flood | Proposes junk issues with high claimed priority |

Validators, hunters, griefers and the owner act as in v5 on the winning contributions.

### D7. Criteria (incentive-simulation)
- **The statistics:** v5's pooled means and clustered standard errors (`pooled`, `judge_defective`).
- **Misreporting:** compared on the same seed with the same solver bidding its cost.
- **Collusion:** reported per ring size, with the smallest size at which it's significant.
- **Pledge accounting:** checked exactly from the ledger: every credit that left a pledge went to instalments, the fee or a refund.
- **The report:** `reports/acceptance-market-v1.{json,md}`, with 100-seed verdicts and 20-seed sweeps.

### D9. Bid first, build after (owner's decision, 2026-10-24)
The first market runs, with the approved "commit a hash of your solution" rounds, showed a structural loss: everyone builds, one is paid. In one 8-week run:
- about 4 entrants per bounty;
- **77 % of honest solvers' development effort went into losing entries** (9,053 of 11,778 credits);
- honest solvers ended at about −770 each, effort counted, while winners earned 1.31 × their cost.

Rational solvers would stop entering, and lone bidders would collect the cap. So rounds now sell **the job, not a solution**:
1. **Sealed second-price bids,** a price only, with a stake and a fee. The cheapest is assigned at the second price or the cap.
2. **The assigned solver builds and delivers** within `delivery_days`, through the gate. A pass becomes the contribution. A failure or a late delivery forfeits the stake (the **bond**) to the bounty and the fee to the checking costs.
3. **The next queued bid is offered the job** at the next queued price or the cap, if it posts its stake again. That covers a failed delivery, and a contribution that's slashed, clawed back or declined.
4. **Everything after delivery is unchanged:** escrow, fee, beta, window, instalments, clawback, leftover.

**What it removes:**
- duplicated effort: only the assigned solver builds;
- copying: no solution exists before delivery, and a slashed winner's job passes to a runner-up, not to a new round.

**The new attack** is the **no-show** (winning with a low bid and never delivering). It delays the fix by `delivery_days` and costs the bond.
- *Alternative:* cap the number of entrants per round. Rejected: it reduces the waste but doesn't remove it.
- *Alternative:* pay losing entrants a consolation prize. Rejected: it spends pledges on work that isn't used.

### D8. No escrow share for challengers in the market mode
A challenger normally takes a share of a slashed contribution's escrowed reward. In the market, that escrow is pledgers' money, so the spec's "pledges pay only for released fixes" would break. The market mode therefore requires `challenger_escrow_share_bps` = 0, as a parameter rule. A slashed winner's escrow returns to the bounty in full, and challengers are paid from the slashed stake (40 % of the cap).

### D10. What the simulation changed (task 4.2)
- **An honest bid is the break-even price, not the bare build cost.** Winning a job carries risks: a failed delivery forfeits the bond, and a defect caught later slashes the stake and pays nothing. A solver bidding its true cost prices them in: (build cost + expected penalties) ÷ the chance of being paid, with its own defect and check rates. With bare-cost bids, honest solvers barely broke even (+4 ± 6, 10 seeds), and a 1.5× "bluffer" gained significantly (+186 ± 82), only because it priced the risk. Bluffers and lowballers now bid 1.5× and 0.6× of the break-even price.
- **A junk delivery is a defect the enforcement layer can catch.** A fix for an issue that isn't real is a wrong result: it passes the gate, but review duty and hunters can spot it. With junk deliveries uncatchable, the treasury flood profited (+2,402 per run).
- **Attackers lose includes the treasury flood.** The spec only required the treasury to stay within budget; the flood must also lose money, like no-shows and spam solvers.
- **Runs drain up to 120 days,** so every job is fully paid or fully lost before solvers are judged. A 40-day drain cut runs off mid-instalment, and solvers looked negative (−61 against +24 when fully drained).
- **A ring bids once per round.** Its cheapest member with room bids, and no other member enters that round after it.

### D11. The market is the default (owner's decision, 2026-10-24)
- `Params()` is the market: `reward_source="market"` and `challenger_escrow_share_bps=0`.
- The legacy pool is `LEGACY` (`reward_source="pool"`, escrow share 5,000). It's kept only to compare with and to reproduce runs v1–v5. The legacy scenarios, report, summary and tests use it by name.
- **Checked when switching:** the legacy acceptance check and summary, and the market's acceptance check, give byte-identical results before and after.
- **Not a verdict that the market is done.** Its open issues are follow-ups under #15: bluffing under other hunting assumptions, rings of 4, and treasury crowd-out. The legacy pool fails too (splitting, v5), and it isn't the design.

## Risks / Trade-offs

- **Thin markets overpay:** a lone valid bidder gets the whole cap. A reserve below the cap would help; it can be swept later.
- **Collusion is second price's known weakness.** Rings that stay out of rounds raise the price. The valid-entry rule makes sham bids cost a real solution, but staying out costs nothing. Measured, not solved here.
- **The value and cost models are assumptions.** The verdicts are only as good as them, which is why they're swept.
- **The 20 % fee** may deter pledgers. That isn't modelled: pledgers here don't respond to the fee.
- **Slashed winners delay the bounty** by a runner-up's beta cycle.
