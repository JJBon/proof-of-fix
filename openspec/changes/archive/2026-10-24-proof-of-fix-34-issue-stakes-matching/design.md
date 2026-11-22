# Design

## Context

The market (`pof/market.py`, `specs/bounty-market`) has:
- bounties funded by pledges or the treasury;
- sealed rounds for the job, assignment, delivery with a bond, and payment through the lifecycle;
- a 20 % market fee from the bounty;
- the leftover refunded pro rata to pledgers, or to insurance for a treasury bounty.

The treasury budget (2,000 per release) is issued only when used, and is spent only on AI-proposed bounties.

The simulation (`pof/sim/market_world.py`) creates issues with no reporter. In market v1:
- a flood of 2 junk issues a day crowds out about 98 real issues per run;
- the AI treasury spots 85 % of the junk;
- the junk "fixes" are caught by review and hunters.

## Goals / Non-Goals

**Goals:**
- Pay discoverers of real issues, and make junk cost its reporter.
- Make funders' money go further without paying them from the treasury.
- No new way to profit by self-dealing or fake accounts.

**Non-Goals:**
- Tokens, and interest on escrow.
- Reputation, which would also weight matching by trust (next).
- Deduplicating issues.

## Decisions

### D1. The issue stake
- It's posted at submission, into its own account recorded against the issue.
- **Returned with the finder's fee** when the bounty is paid. The fee comes from the bounty at payment time, like the market fee, and the price cap leaves room for both: cap = funds ÷ (1 + market fee + finder's fee).
- **Forfeited to insurance** when junk is confirmed: a treasury flag plus a panel majority, or a delivered fix slashed while the issue is marked junk-suspect. In the simulation, junk deliveries are wrong-result defects (market v1, design D10).
- **Returned** if the issue expires unfunded.
- *Alternative:* the finder's fee as a share of the market fee. Rejected: tying it to the validators' and others' shares makes both harder to tune.

### D2. Parameters (defaults)
| Parameter | Default | Rationale |
|---|---|---|
| `issue_stake` | 5 credits | Small for an honest reporter. A flood of 2 junk a day then risks 10 a day, against bounties of up to 300 each, so detection, not the stake alone, has to do the work |
| `finder_fee_bps` | 500 | 5 % of the price, about 4 credits on a median 83-credit price. Below the 20 % market fee, so self-dealing loses at least 15 % of its own pledge |
| `matching_share_bps` | 5,000 | Half the treasury budget (1,000 per release) matches pledges; half funds AI-proposed maintenance |
| `match_cap_bps` | 5,000 | A match is at most half a bounty's target, so at least half comes from pledgers |

**Sweeps:** the issue stake (2, 5, 20), the finder's fee (2.5 %, 5 %, 10 %), and the matching share (0, 50 %, 100 %).

### D3. When matching happens
At each release's opening, for every bounty still gathering pledges:
1. Take its weight, (Σ √pledges by pledger)² − Σ pledges, using what's been pledged so far.
2. Scale every weight by min(1, the matching budget left ÷ the sum of weights).
3. Cap each match at `match_cap_bps` of the target and at what's still missing.
4. Issue it into the bounty, recorded as the treasury's input. A bounty that reaches its target opens its round.

Matching counts against the same per-release treasury budget, through the matching share.

### D4. Refunds in proportion to what each put in
Each bounty tracks its inputs: pledges by pledger, the treasury's (a match or a treasury bounty), and bonds forfeited by failed deliveries. Bonds count as the pledgers' and treasury's in proportion: they compensate the funders.

The leftover is split by input share, rounded down, with the remainder to the last. The treasury's share goes to insurance. Matching money can't come back to a pledger.

### D5. Simulation
- **Reporters:** 20 honest reporters (endowment 200), one picked at random per real issue, each posting the stake.
- **The flood** stakes on each junk issue. When the treasury flags junk, a validator panel votes on the truth.
- **Match farmer** (cohort "farm"): it reports one small real issue a week (10–40 lines) and pledges its value split across 4 fake accounts. It bids on its own bounty at the cap; the work is real but small. Its counterfactual on the same seed pledges from one account.
- **Self-dealer:** a reporter that pledges the full target of its own issue and bids its break-even price.

**Criteria:** spec "Acceptance criteria for discoverers and funders", using market v1's statistics.
- **Crowd-out:** real issues funded by the treasury under the flood, against the same seeds without it.
- **Funders' cost:** pledged credits per paid pledged bounty, with matching and without (`matching_share_bps` = 0), on the same seeds.

### D6. What the simulation changed (task 4.2)
- **Unsolved bounties close** (a new spec requirement, "Unsolved bounties close"). A funded bounty whose price cap is below every solver's cost reopened forever, leaving its pledges **and** its reporter's stake locked. Market v1 ended with about 63 such bounties per run. After `bounty_max_rounds` (4) empty rounds in a row, it closes: funds return by input, and the stake returns with no fee.
- **Pledging is gradual and partial.** Pledgers had funded each issue's full value at once, so no bounty was ever left gathering pledges and matching never ran. Now 1–6 backers pledge 50–110 % of the value between them.
- **The match farmer's counterfactual pledges the full value from one account,** what it would need without matching. It had pledged only 60 %, never reached the target, and was simply refunded.
- **A reporter's wealth includes its stakes still posted at the end,** like a validator's stake: they're its money, held. Open issues at the run's end shouldn't count as losses.

### D7. Market acceptance run v2 (task 4.2)
- **Every criterion passes at hunting elasticity 0.** At 0.5 and 1, **only "matching lowers funders' cost per paid bounty" fails** (−7.8 ± 4.4 at 0.5: lower, but not significant).
- **The benefit is real but elsewhere.** With matching, 85.7 % of pledged bounties reach their target, against 16.8 % without, and 14.2 ± 0.4 more are fixed and paid per run. Funders pay for many more fixes, so the cost per fix barely moves.
- **The owner approved the amendment (2026-10-24).** The criterion is now "matching gets more pledged issues funded and fixed": the share of pledged bounties reaching their target must be significantly higher with matching, on the same seeds. The cost per paid bounty stays in the report. Run v2 was re-run with the amended criterion.
- **The other results:**
  - discoverers +8.9 ± 0.2; the flood −497, junk spending 840 per run (v1: 4,123), crowd-out bounded at 91 %;
  - match farming −27 ± 13; self-dealing bounded in every run;
  - bluffing no longer pays at any elasticity;
  - a ring of 4 still gains (+84 ± 32).

## Risks / Trade-offs

- **Sybil matching:** splitting a pledge across fake accounts raises its weight by roughly the number of accounts, up to the cap. The cap and the shared budget bound it. Reputation-weighted matching comes with reputation, and the match farmer measures what's left.
- **A small stake doesn't stop a determined flood by itself.** It adds a cost per junk issue on top of detection.
- **The finder's fee rewards reporting, not importance.** Pledges and matching already rank importance.
- **More inputs per bounty make the refund accounting more complex.** The exact pledge-accounting check in every run covers it.
