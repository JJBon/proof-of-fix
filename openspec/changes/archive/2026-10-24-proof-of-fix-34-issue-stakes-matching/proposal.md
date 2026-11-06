# Proposal

## Why

The bounty market (`reports/acceptance-market-v1.md`, #15) pays solvers, validators and the owner, but not the people who **discover** issues or **fund** them (ticket proof-of-fix#34; the options are in #15's comment of 2026-10-24):
- **Discovering a real issue is valuable and unpaid,** and submitting junk costs nothing. Market v1's treasury flood loses money for the flooder but crowds out about 98 real issues per run.
- **Funders only pay** (about 158 credits each over 8 weeks); their return is the fix. Nothing makes their money go further.

The owner chose two remedies: **issue stakes with a finder's fee**, and **quadratic matching of pledges**. A token for funders stays a later option, gated on real revenue and a legal review.

## What Changes

- **Issue stake:** submitting an issue takes a small published stake.
  - **When the issue's bounty is paid** (a real fix, released): the stake returns with a **finder's fee**, a published share of the winning price, paid from the bounty. The price cap leaves room for it, as for the market fee.
  - **When the issue is judged junk:** the stake is forfeited to insurance. That happens when the AI treasury flags it and a validator panel confirms, or when the fix delivered for it is slashed as junk.
  - **When the issue is never funded:** the stake returns, with no fee and no fault.
  - **The finder's fee is smaller than the market fee,** so funding your own issue and solving it can't earn more than the work.
- **Quadratic matching:** a published share of each release's treasury budget matches pledges on bounties still gathering pledges.
  - The weight is (the sum over pledgers of the square root of each one's pledges)², minus the pledges. A single pledger attracts nothing; many small pledgers attract more.
  - Matches are scaled to the matching budget and capped per bounty at a published share of its target. A match counts toward the target, so the round opens sooner and funders pay less per fix.
  - The rest of the treasury budget keeps funding AI-proposed bounties.
- **Refunds in proportion to what each put in:** when a bounty is paid, its leftover returns in proportion to what each source put in. Pledgers get their share; the treasury's share (a match, or a treasury bounty) goes to insurance. **Matching money is never profit for pledgers.**
- **Simulation:**
  - issue reporters who stake;
  - the treasury flood, now staking on its junk;
  - a **match farmer** who splits its pledges across fake accounts and bids on its own issues;
  - a **self-dealer** who funds and solves its own issues;
  - market acceptance run v2.

**Out of scope:**
- tokens;
- interest on escrowed pledges (needs a real chain; rule 1);
- reputation (the next change);
- AI deduplication of issues;
- the AI jury.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `bounty-market`:
  - new requirements "Issue stakes" and "Quadratic matching";
  - "Treasury bounties" (the budget is shared with matching) and "Market fee and refunds" (the finder's fee, and refunds in proportion to what each put in) are modified.
- `incentive-simulation`: new requirements "Market scenarios for discoverers and funders" and "Acceptance criteria for discoverers and funders".

**Actors and attacks:**
- **Who's affected:** reporters (who now earn and stake), funders (matched), the treasury (budget split).
- **Attacks covered:**
  - junk floods (now staked);
  - sybil pledgers farming the match;
  - self-dealing (funding and solving your own issue);
  - the v1 attacks, which must still lose.

## Impact

- **Code:**
  - `pof/params.py`: `issue_stake`, `finder_fee_bps`, `matching_share_bps`, `match_cap_bps`;
  - `pof/market.py`: issue stakes, the finder's fee, matching at each release, refunds in proportion to inputs;
  - `pof/sim/market_world.py` and `market_sim.py`: reporters, the match farmer, the self-dealer, the new criteria;
  - tests.
- **Data:** `reports/acceptance-market-v2.{json,md}`.
- **The legacy pool (`LEGACY`) is unchanged.**
