# Proposal

## Why

Market v2 (`reports/acceptance-market-v2.md`) passes every criterion, but every account counts the same, new or proven (ticket proof-of-fix#37):
- **A fresh fake account's pledge** draws as much matching as a long-time funder's. Farming loses today, but narrowly (−27 ± 13).
- **The treasury can't tell** a reporter with a record of real issues from a stranger, so crowd-out depends entirely on junk detection. At 50 % detection the criterion fails (64 % of real issues funded).
- **A proven solver locks the same bond as an unknown one,** 40 % of the cap.

#15's principles call for **non-transferable reputation before any token**, and for authority that is earned.

## What Changes

- **Reputation (a new capability):** a score per account and role (solver, reporter, funder).
  - It's built only from outcomes on the ledger: paid work, failed deliveries, slashes and clawbacks; rewarded or forfeited issues; pledges to bounties that were paid.
  - It's published, recomputable from the ledger, and can't be transferred. New accounts start at zero.
  - **Trust** is a published function of the score: a floor for newcomers, rising with good outcomes, falling back after bad ones.
- **Trust-weighted matching:** each pledger's part of the quadratic weight is scaled by its funder trust, so fake new accounts draw little.
- **Trust-weighted treasury:** the treasury ranks unpledged issues by value × the reporter's trust.
- **Earned bond discount:** a solver's bond falls with its trust, down to a published share of the full bond. A failure lowers its score, and the discount with it.
- **Simulation:**
  - a **reputation farmer** builds trust on cheap jobs, then wins a big one with a low bid and doesn't deliver;
  - market acceptance run v3.

**Out of scope:**
- tokens;
- the score decaying over time (a later parameter);
- a reserve price (the ring of 4, next);
- the AI jury.

## Capabilities

### New Capabilities
- `reputation`: scores from outcomes, trust, publication, non-transferability.

### Modified Capabilities
- `bounty-market`: "Sealed rounds for the job" (the bond discount), "Quadratic matching" (weighted by trust) and "Treasury bounties" (ranked by the reporter's trust).
- `incentive-simulation`: new requirements "Market scenarios for reputation" and "Acceptance criteria for reputation".

**Actors and attacks:**
- **Affected:** every solver, reporter and funder; the match farmer (its fake accounts start at the floor); the flood (its junk drops in rank).
- **New attack:** the reputation farmer.
- **Unchanged:** the ring of 4.

## Impact

- **Code:**
  - a new `pof/reputation.py` (scores and trust from market events);
  - `pof/market.py` (the bond, matching, and a treasury ranking helper);
  - `pof/params.py` (points, the trust floor and step, the bond discount);
  - `pof/sim/*` (the treasury ranks by trust, the reputation farmer, the criteria);
  - tests.
- **Data:** `reports/acceptance-market-v3.{json,md}`.
- **The legacy pool is unchanged.**
