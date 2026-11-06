# Proposal

## Why

Every acceptance run so far (v1–v5) pays contributors from a **placeholder**: a fixed fund per release, split among contributions by lines changed. That isn't what the owner agreed in the design brief (ticket proof-of-fix#15):
- **The market sets a contribution's value:** a bounty pays the solver's cost of development plus a market-set reward.
- **Sealed second-price rounds** make overstating costs useless.
- **Pledges fund the bounties.**
- **Payment comes when the fix ships in a release.**

The placeholder is behind the remaining failures and patches:
- splitting pays (v5, at hunting elasticity 0);
- padding;
- the stake index (#23);
- capped excess and funding that follows use (#27).

Paying per problem solved removes their cause.

The enforcement layer (stakes, challenges with proof, slashing, clawback over instalments, review duty, the guardrails) is validated on 100 seeds (v5), and carries over unchanged.

## What Changes

- **A bounty market as the reward source** (a new `market` mode; the legacy pool stays as a switch for comparison):
  - **Bounties:** an issue becomes a bounty with a definition of solved and a target. Users **pledge** until the target is reached, or are refunded at the deadline.
  - **Treasury bounties:** the owner's choice of "market plus a small subsidy", in #15's form. A capped **per-release treasury budget** funds bounties for issues nobody pledges for, proposed by the AI treasury. Bounties above a threshold need a validator panel. Nothing is split by size.
  - **Sealed rounds for the job, bid first and build after** (owner's decision, 2026-10-24, from the first market runs; design D9): each solver commits a sealed **price** (at most the bounty's price cap) before building anything, with a **stake (a share of the cap)** and a fixed **evaluation fee**. Everyone reveals after the deadline.
  - **Assignment:** the cheapest bid is **assigned the job** at the **second-lowest price**, or at the cap if it's alone. Its stake is a performance bond.
  - **Delivery:** within a deadline, through the gate. A failed or late delivery forfeits the bond to the bounty, and the next bid is offered the job. Only the assigned solver builds, and nothing exists to copy before delivery. A published **market fee** on top of the price pays validators, the upstream author's escrow, infrastructure, insurance and the owner, in the published proportions. The rest of the pledges goes back to the pledgers.
  - **Payment:** the winning solution becomes a contribution in the lifecycle, with its price escrowed. It ships in the next beta build and is paid in **4 instalments with clawback**. A slash returns the escrow to the bounty, which reopens for a new round.
- **Simulation:**
  - issues arrive from GridCraft's history, with user value, difficulty and a private cost for each solver;
  - **new actors:** pledgers, honest solvers (who bid their cost), bluffers (overstate), lowballers (understate), no-shows (win and never deliver), colluding bidders, spam solvers, and a treasury flood (junk proposals);
  - the existing enforcement actors (validators, hunters, griefers, the owner) carry over;
  - **acceptance criteria for the market mode** (incentive-simulation).

**Out of scope (later changes under #15):**
- the AI jury (evaluators, reputation, isolated VMs, hidden tests);
- decentralized checking;
- non-transferable reputation;
- bug planters and reputation farming;
- the real-data measurement (it needs the owner's budget);
- usage royalties;
- anything real (rule 1).

The existing layered judgement (replay, AI review, validators) stays as the checking step.

## Capabilities

### New Capabilities
- `bounty-market`: bounties and pledges, treasury bounties, sealed rounds, the winner and its second price, the market fee, refunds, and how the winner enters the lifecycle.

### Modified Capabilities
- `incentive-simulation`: new requirements "Market scenarios" (issues, pledgers and solvers) and "Acceptance criteria for the market". The existing criteria apply in the market mode too, where they make sense.

**Actors and attacks:**
- **Payees:** solvers, pledgers, the treasury, validators, the owner and the upstream author (paid from the market fee).
- **Attacks covered:** bluffing, lowballing, no-shows, colluding bidders, spam solutions, treasury flooding, plus the enforcement attacks carried over (defective work, griefing, owner defection).

## Impact

- **Code:**
  - a new `pof/market.py` (bounties, pledges, rounds, settlement), using the ledger and the lifecycle;
  - `pof/params.py`: the market's parameters;
  - `pof/lifecycle.py`: `submit` accepts an explicit stake;
  - `pof/sim/*`: issues, the new actors, the market scenarios and criteria;
  - tests for each.
- **Data:** `reports/acceptance-market-v1.{json,md}`. The legacy reports stay.
- **Specs:** the legacy per-release requirements (the split by weight, the indexed stake, funding that follows use) stay valid for the legacy mode. Retiring them is a later decision once the market mode passes.
