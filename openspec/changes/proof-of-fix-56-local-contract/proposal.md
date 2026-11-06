# Proposal

Ticket: proof-of-fix#56.

## Why

The race's rules are settled and simulated (#60, #64: modes v3 passes every criterion, and reproduces byte for byte). The owner wants the contract built locally ("I don't want my contract revealed earlier; for now a local blockchain is good"), with the design decisions taken on #15 and #56:
- an immutable contract with no admin key, no owner front end, and third-party oracles;
- **solved = merged:** repos opt in to let the protocol merge AI-accepted fixes;
- bounties hold a **basket** of any coins plus the contract token, with per-coin pull payouts, so a frozen coin doesn't block the rest (#59);
- no pause, but an **invariant-triggered withdraw-only mode**, hard caps, audits and versioned deployments;
- commit-reveal ordering; prompt-injection defenses at the oracles;
- accuracy delegated to the oracle network or coding leaderboards.

## What Changes

- **A Solidity prototype** in `contracts/`, built and tested with Foundry against a local anvil chain, in a pinned container. No testnet, wallets or public deployment (openspec rule 1).
- **Phase 1, money:**
  - baskets (escrow per coin, counting what was actually received);
  - registration (the fee, refunded when solved);
  - the race:
    - the rising price and its lock;
    - attempt and late fees;
    - commit-reveal submissions with check deposits;
    - first valid wins;
    - duplicate and author appeals;
  - payment on merge, in instalments, with clawback;
  - per-coin pull payouts;
  - caps, and the withdraw-only mode.
- **Phase 2, oracles:** a registry of oracle signing keys and one aggregated, signed result per submission (CI, gates, juries), checked by the contract; mock signers stand in for the oracle network.
- **Phase 3:** a read-only `quote()` (what a submitter will pay and could earn), and a CLI that prints it.
- **Phase 4:** the contract's own repo as its first bounty target, against a local Forgejo test repository.
- **Phase 5, the token and migration (owner, 2026-10-29; design D15):** a token with rules fixed at deployment, minted only by its own Race, and a 1:1 swap into it from the previous version's token. There's no key anywhere: anyone can deploy a version, and holders choose which one to use.
- **The simulation as the test oracle:** a simulated race run exports its events, the contract replays them, and every account's balance must match.

- **Owner, 2026-10-26:**
  - the race on-chain covers a bounty's money end to end, with no market fee; treasury, matching and reputation stay in the simulation (design D9);
  - one fix, one payout (D10);
  - anyone opens a bounty and the market funds it, one open bounty per issue (D12);
  - the reporter's and the solver's split, 15/85 (D13);
  - idle bounties sunset (D11).

- **Owner, 2026-10-29:** keyless upgrades by migration from day one (D15), replacing the admin-key options discussed (an upgradeable proxy, a timelocked multisig, a key that changes the token's minter).

**Out of scope:**
- treasury bounties, matching and reputation on-chain (D9);
- real oracle networks;
- any testnet or mainnet deployment;
- a front end;
- the audit itself (before any real funds).

**Actors and incentives affected:** a fix farmer who submits one fix to several bounties tracking the same issue now gains nothing after the first payout (D10). Otherwise the contract implements the simulated race, and the difference tests check it does so exactly.

## Capabilities

### New Capabilities
- `local-contract`: the on-chain prototype of the race, its safety rules and its tests against the simulation.

### Modified Capabilities
- `bounty-market`: one fix, one payout across bounties tracking the same issue; idle race bounties sunset (spelled out from `close_idle`).
