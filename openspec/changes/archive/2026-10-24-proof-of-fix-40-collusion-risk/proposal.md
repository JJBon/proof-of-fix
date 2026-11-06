# Proposal

## Why

Market v3 (`reports/acceptance-market-v3.md`, ticket proof-of-fix#40) passes at hunting elasticity 0 and 0.5. Two weaknesses remain:
- **Collusion:** a ring of 6 solvers gains significantly (+72 ± 32). A ring stays out of rounds so its member is paid the next outsider's price, or **the whole cap when it's alone**. At 20 seeds a ring of 2 is flagged too, plausibly because reputation rewards funnelling wins through one member: trust and the bond discount come sooner.
- **Bluffing pays at elasticity 1.** Honest solvers price their risk from the default detection assumption and the discounted bond, so they under-price it when hunting is vigorous.

## What Changes

- **Reserve price:** the most any bounty pays is a published share of its price cap.
  - Bids above the reserve are void.
  - A lone bid, or the second price, is paid at most the reserve.
  - A thin market or a ring can no longer extract the whole cap. A reserve set too low leaves bounties unsolved, until they close and refund; the sweep measures that.
- **A per-release trust cap:** an account earns at most a published number of positive points per role per release. Failures still cost in full.
  - One identity that wins a ring's jobs gains trust no faster than an honest solver.
- **Simulation:**
  - **solvers price risk from their own record:** delivery-failure and slash rates from their outcomes, starting from the default assumption as a prior;
  - market acceptance run v4.

**Out of scope:**
- the AI jury;
- decentralized checking;
- the real-data measurement;
- tokens.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `bounty-market`: "Assignment and price" (the reserve) and "Sealed rounds for the job" (bids above the reserve are void).
- `reputation`: "Scores from outcomes" (the per-release cap on points earned).
- `incentive-simulation`: new requirements "Solvers price risk from their record" and "Acceptance criteria for collusion and risk pricing".

**Actors and attacks:**
- **Affected:** all solvers (lower prices in thin rounds), rings (no cap to extract), proven solvers (trust earned more slowly).
- **Covered:** rings of 2–6; bluffers at every elasticity.

## Impact

- **Code:**
  - `pof/params.py`: `reserve_bps`, `trust_points_per_release`;
  - `pof/market.py`: the reserve in reveal and assignment;
  - `pof/reputation.py`: the per-release cap;
  - `pof/sim/market_world.py`: record-based break-even;
  - `pof/sim/market_sim.py`: criteria and sweeps;
  - tests.
- **Data:** `reports/acceptance-market-v4.{json,md}`.
