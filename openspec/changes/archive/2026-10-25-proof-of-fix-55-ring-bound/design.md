# Design

## Context

Rings (#40) and the hidden bidder (#43) are judged by "no significant gain" on 100 seeds. In checking v6 none is significant, but the standard errors are 10–31, so gains of up to about +60 can't be ruled out. The owner wants to know whether identity is needed before going live (#15); a bound answers that.

Two sources of spread:
1. **Real variation** between seeds (different issues, prices, solvers' skills).
2. **Comparison noise:** the attacker's run and its honest twin share one random stream, so the first different decision shifts every later draw for everyone. The owner-defection criterion had this problem (fixed in #47 with `owner_rng`), and CI before it (`ci_rng`, #43).

## Decisions

### D1. Each solver draws from its own stream
- `MarketWorld` gives every solver a `random.Random(f"{seed}:{name}")`, used for that solver's own decisions:
  - whether it looks for work today (`bid_daily_bps`);
  - not revealing a bid;
  - its build days;
  - its defects, incomplete fixes, its own checks catching a defect, and false check failures.
- **Market-level draws keep the world's stream:** issues, values, reporters, pledges, floods, the treasury, panels.
- A string seed is hashed deterministically by Python's `random` (not by `PYTHONHASHSEED`), so runs stay reproducible.
- **Test:** in a ring run and its honest twin, a solver outside the ring that bids on the same bounty on the same day gets the same build days and defect draws in both.
- **Measure:** the rings' and the hidden bidder's standard errors on seeds 1–100, before and after. If they barely shrink, the report says so, and the extra seeds (D2) do the work.

### D2. Attack seeds, separate from the verdict seeds
- `attack_seeds` = 400 (seeds 1–400): the rings of 2, 3, 4 and 6 and the hidden bidder, each against its honest twin. Every other verdict keeps 100 seeds.
- **Why 400:** the standard error falls with the square root of the seeds. 400 halves it before D1's effect, so a ring of 3 at ±24 becomes about ±12.
- **Runtime:** about 10 runs per seed for these comparisons. The summary command gets a `--jobs` option (standard-library `multiprocessing`, one seed per task), merged in seed order, so results don't depend on the number of jobs. The byte-for-byte reproduction check runs with a different `--jobs` to show that.

### D3. The ring tolerance
- `ring_tolerance_bps` = 2,500: **a quarter of an honest solver's mean net per run**, on the same run's verdict seeds (v6: +20.2, so a tolerance of about +5 per member).
- **The criterion:** for each ring size, the ring's gain divided by its members, plus two standard errors, is below the tolerance. The hidden bidder's gain is divided by its two accounts.
- **Why a share of honest earnings:** it bounds what collusion can add to what honest work earns. A quarter is the starting point for the owner's review: the lower it is, the more seeds a pass needs.
- **"Bidding your cost is best" stays a significance test** (bluffing and lowballing on 100 seeds): those compare one actor's strategies, not identities.

### D4. Checking v7
- D1 changes every scenario's random path, so the full summary is re-run (`reports/acceptance-checking-v7.{json,md}`) and compared with v6.
- A criterion that fails is fixed here, in the open, and recorded in this design; a failure from the comparison itself (as in #47) is named as such.
- **If every bound holds,** the report says that identity can leave the #15 go-live checklist, and that's the owner's decision.

## Risks

- **The bound may not be reachable at 400 seeds:** a ring of 6 at ±31 needs D1 to work, or many more seeds. The report then gives the seeds a pass would need at the measured spread.
- **A small but real gain** under the tolerance passes by design. The report gives each ring's mean, so the owner sees it.
