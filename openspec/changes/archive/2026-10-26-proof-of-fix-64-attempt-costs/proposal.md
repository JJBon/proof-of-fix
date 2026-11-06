# Proposal

Ticket: proof-of-fix#64.

## Why

The race is the default (#60). Three holes were found before building the contract (#56):
1. **Starting an attempt is free, and attempts in progress are published.** Fake attempts can make a bounty look crowded and scare honest solvers off.
2. **The first attempt locks the rising price,** so a free fake attempt on day 1 locks it at 50 % and never submits.
3. **The AI similarity check can reject an honest, independent fix** as a duplicate of someone else's failed fix (fixes for small bugs look alike), with no appeal.

The owner's answer (2026-10-25): "Fake attempts cost money, and someone winning can still compete. A free fake attempt shouldn't exist: there's a cost for everything, and arriving late costs. Appeals can go to AI judges, 3 or 5 from different providers."

## What Changes

- **An attempt fee:** starting an attempt pays a published fee, kept for the oracles that publish and track attempts. The first paid attempt still locks the rising price.
- **Arriving late costs:** a submission after the bounty is won isn't checked, and pays the evaluation fee (the timing and similarity check) instead of getting its deposit back in full.
- **The duplicate appeal:** a submission rejected as a duplicate of someone else's failed fix may be appealed by its submitter, at its own cost, to an AI jury of a published size (3 or 5) from different providers. If the jury finds it independent, it's checked like any submission.
- **Simulation:**
  - a fake attempter (sock accounts inflating the attempts count, a day-1 lock);
  - honest fixes falsely flagged as duplicates, at a swept false-positive rate;
  - the fees swept;
  - modes v3, compared with v2.

**Out of scope:** the contract itself (#56), tokens (#58) and baskets (#59).

**Actors and incentives affected:**
- every racer pays the attempt fee;
- late submitters pay the evaluation fee;
- the fake attempter and false-duplicate victims are new scenarios.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `bounty-market`: "The gated race" (late submissions pay the evaluation fee; attempts pay a fee) and "Failed fixes aren't resubmitted" (the duplicate appeal).
- `incentive-simulation`: new requirement "Attempt costs and duplicate appeals: scenarios and criteria".
