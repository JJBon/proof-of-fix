# Proposal

Ticket: proof-of-fix#60.

## Why

The owner proposed a different market (2026-10-25):
> No window, no bids. A bounty has an AI cost to be registered. The submitter pays the AI checks. The first proposal that meets the quality gates (the project's constitution, and the bounty requirements written by AI from the author's requirements) wins. No meaningless bounties or low-quality fixes. The market sets the price; AI only allows the bounty's placement. Allow bounties of 0 coin.

Today's market (sealed second-price rounds, bid first and build after) passes every acceptance criterion (checking v6). But its price can be bent by rings: their gains aren't significant, yet aren't bounded either (#55). The owner's design removes the price auction altogether: funders set the price, quality gates decide what counts, and the first fix through the gates wins. It's simpler and puts quality first. Its known cost is **racing**: parallel attempts, and only the first that passes is paid. Market v1 measured 77 % of solver effort lost on losing entries when solvers built first.

This change makes the award a **mode**, so both designs run on the same seeds and the numbers decide. Nothing changes by default.

## What Changes

- **Award modes** (`award_mode`): `auction` (today, the default), `race` (the owner's design) and `claim` (the race with an exclusive claim, so nobody's work is wasted).
- **Registration check** (race and claim): whoever opens a bounty pays an AI check in coin.
  - It writes acceptance criteria from the author's requirements, which the author approves.
  - It checks the bounty is worth doing (a size floor; smaller issues are bundled).
  - It estimates its effort.
- **The project's constitution:** quality gates every delivery must pass, versioned in the repository:
  - objective measures from the attested runners (coverage of the changed code, mutation score, diff limits, performance);
  - the AI juries' pass or fail.
- **The price is set by funders** (pledges, top-ups), 0 allowed. No reserve, since nobody bids.
- **The race:** anyone submits, sealed, with a check deposit; the first submission through every gate wins. The number of attempts in progress is published, so solvers can choose less contested bounties.
- **Claim then build:** a solver claims with a bond and gets exclusive time, scaled to the bounty's estimated effort; the claim passes on if it fails or times out.
- **Simulation:** fix quality as a property of each fix, the modes compared on the same seeds, and new attacks:
  - spam bounties against the registration check;
  - padded submissions against mutation scoring;
  - a second identity racing;
  - inflated effort estimates.

**Out of scope:** the token (#58) and coins other than credits (#59), which build on the winning mode. Rings are still measured in every mode, but #55's bound is applied only if the auction stays the default.

**Actors and incentives affected:** solvers (racing, claiming), funders (setting prices), posters (the registration fee), evaluators and runners (more checks per bounty in a race), and every attacker above.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `bounty-market`: new requirements "Award modes", "Registration check", "The gated race" and "Claim then build".
- `checking`: new requirement "The project's constitution".
- `incentive-simulation`: new requirement "Award modes compared".
