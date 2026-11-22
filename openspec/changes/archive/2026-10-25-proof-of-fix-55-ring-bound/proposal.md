# Proposal

> **Withdrawn (2026-10-25), never implemented:** the race became the default in #60/#63, and with no bids there's no price for a ring to bend. Archived without applying its specs (#55 closed).

Ticket: proof-of-fix#55.

## Why

The go-live checklist on #15 lists **identity** (one person, several accounts) as a blocker. The owner asked whether that's needed: "rigging the PR provides no benefit."

The acceptance runs back that up only partly. No ring and no second identity gains significantly, but the spreads are wide (checking v6, 100 seeds):
- rings of 2, 3, 4 and 6: −32 ± 19, +15 ± 24, +15 ± 27 and −7 ± 31;
- a checker who also bids under a second identity: +8 ± 10.

So a ring of 3 could still gain up to about +60, against an honest solver's +20 per run. "Not significant" isn't "no benefit". This change turns it into a bound: either the gain is shown to be small, and identity leaves the checklist, or the run shows which ring gains and by how much.

Much of the spread is likely noise from the comparison, not the attack. A ring and its honest twin draw from one shared random stream, so when members bid differently, every later draw (build days, defects, other bidders' timing) shifts. The owner-defection criterion had the same problem and was fixed in #47.

## What Changes

- **Common random numbers for solvers:** each solver's own decisions draw from its own stream (per seed and solver), so a ring and its honest twin, or a bluffer and its truthful twin, share the rest of the market's path. Market-level draws (issues, pledges, the treasury) keep the world's stream.
- **More seeds for the paired attack comparisons only:** the rings and the hidden bidder run on a published number of seeds (`attack_seeds`, 400 by default), separate from the 100 used for the other verdicts.
- **A bounded criterion replaces "not significantly positive"** for rings and the hidden bidder: the upper end of the interval (mean + 2 SE), per attacking account, must be below a published tolerance. The tolerance is a share of an honest solver's net per run.
- **A new acceptance run, checking v7:** the solver streams change every scenario's random path, so every criterion is re-run and compared with v6.

**Out of scope:** an identity system (proof of personhood, KYC). This change decides whether one is needed. The contract prototype (#56).

**Actors and scenarios affected:**
- the rings of 2, 3, 4 and 6, and the hidden bidder (`check_sock`), against their honest twins;
- every scenario's random path, through the solver streams.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `incentive-simulation`: "Reproducible runs" gains solver streams. "Acceptance criteria for collusion and risk pricing" and "Acceptance criteria for the checking layer" bound ring and hidden-bidder gains instead of testing them for significance.
