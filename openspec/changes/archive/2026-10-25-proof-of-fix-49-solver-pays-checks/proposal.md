# Proposal

## Why

In proof-of-fix#43 the **bounty** pays every check on a delivery as an oracle fee: 0.3 per attested run and 0.5 per AI verdict, about 5.6 for one full attempt.

The owner's fairness rules return the bond on a split rejection and on inconclusive CI. Together that leaves a cheap drain:
- an attacker delivers borderline junk meant to split the jury;
- the bounty pays about 5.6 in checks, while the attacker loses only a 2-credit fee;
- it bids again in the fresh round, and repeats.

**The checks are paid by the funders, not by the party causing them.**

The owner's decision (2026-10-25, proof-of-fix#49): **the contributor pays for its checks. It's up to the contributor to judge whether a bounty is profitable enough, checks included.**

## What Changes

- **A check deposit with every bid:** worth one full attempt's checks (the oracle reserve), in place of the fixed evaluation fee.
  - A losing bid gets it back in full.
  - A void bid forfeits the published evaluation fee from it, and gets the rest back.
  - The assigned solver's checks are paid from it, and the unused part returns.
- **The bounty pays no checks:**
  - the price cap no longer leaves room for oracle fees;
  - the minimum target is gone;
  - pledges pay only the price, the market fee, the finder's fee and refunds, as before #43.
- **Unchanged:** a clear failure still forfeits the bond to the bounty. A split rejection or inconclusive CI still returns it; the solver pays for those checks out of its deposit.
- **Simulation:**
  - honest solvers price the deposit's expected use into their break-even;
  - a **split farmer** delivers borderline junk meant to split the jury, measured against its honest twin;
  - a comparison with the bounty paying the checks (#43's rule), on the same seeds.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `bounty-market`: "Sealed rounds for the job", "Assignment and price", "Delivery", "A split rejection keeps the bond" and "Oracle fees" (the check deposit replaces the evaluation fee and the bounty-paid fees).
- `incentive-simulation`: "Acceptance criteria for the market" (pledges no longer pay oracle fees); new requirement "The contributor pays for its checks: scenarios and criteria".

**Actors and attacks:**
- **Affected:** solvers (deposit and pricing), funders (no checking costs), oracles (paid from deposits).
- **Covered:** the split farmer.

## Impact

- **Code:**
  - `pof/params.py`: the deposit as the oracle reserve, the evaluation fee as its forfeitable part;
  - `pof/market.py`: commit, reveal, assignment, delivery, payment of checks from the deposit, the price cap and the minimum target;
  - `pof/sim/`: pricing, the split farmer, and the comparison;
  - tests.
- **Data:** `reports/acceptance-checking-v5.{json,md}`.
