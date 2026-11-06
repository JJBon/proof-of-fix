# Proposal

Ticket: proof-of-fix#58 (the owner's decisions in comments 4013, 4025, 4049, 4080, 4081 and 4189).

## Why

The owner wants whoever solves an issue to earn a token as well as the bounty's coin, with the token minted only by solved issues. On 2026-10-27 the owner set the conditions (comment 4189):
- A fix that passes the AI check is real work, not farming, even on a bounty of 0 coin.
- Tokens are minted when a bounty closes paid.
- A fixed emission is split by the AI's weight of each solved issue.

Before any contract mints anything, the simulation has to show what this does to the market, to the owner's alignment and to the supply (rule 1).

## What Changes

- **A token emission, simulated** (off by default, so the default runs don't change):
  - A fixed emission per period, decreasing on a published schedule, split among the bounties that **closed paid** in that period, in proportion to each one's **AI weight**. A period in which nothing closes mints nothing.
  - **The weight** is the registration check's estimate of the issue's importance, confirmed when the fix is merged: the smaller of the two independent estimates counts.
  - **A bounty's tokens are shared** between its solver and its reporter. The reporter gets a published share, 15 % by default as in the coin split (#56 D13).
  - **The owner's founder's share:** a published share of each period's emission for a fixed number of periods, with an optional genesis amount compared. It's within the owner's published cap, and gives no vote or discretion (rule 3).
- **Bounties of 0 coin earn tokens only:** with the emission on, an issue nobody funds still opens as a bounty, and solvers race for its tokens.
- **Solvers price tokens:** a solver counts a bounty's expected tokens, at an assumed token price, with its coin. It estimates its tokens from the last period's published tokens per unit of weight.
- **Scenarios:**
  - the token market at a sweep of token prices;
  - a self-funding coder that registers and solves its own issues for tokens (the owner's case);
  - an importance inflater whose estimates are biased upward (AI error);
  - a thin market at launch;
  - the owner defecting with the founder's share.
- **Criteria, report and CLI:** see the `token-emission` and `incentive-simulation` specs. "Token farming loses money" is not a criterion (comment 4189). The report gives what an AI weight error is worth instead.

**Out of scope:**
- The token on-chain (a later phase of #56, if this passes).
- Any real token, chain, wallet or sale (rule 1).
- A holders' vote on the treasury (#58 item 7): it would give token holders, the owner included, a say over payouts, against rule 3.
- Per-account caps on minting: the AI check is the gatekeeper (comment 4081).

**Depends on** #56's market changes: no target, one open bounty per issue, the 15/85 split and the locked share (design D12-D14, branch `proof-of-fix-56`). The implementation starts after #56's simulation changes reach `main`.

**Actors, incentives and attacks affected:**
- solvers and reporters earn tokens on paid bounties;
- unfunded issues become bounties of 0 coin;
- the owner gets a capped founder's share;
- new scenarios: the self-funding coder, the importance inflater, the thin launch and the defecting owner with tokens.

## Capabilities

### New Capabilities
- `token-emission`: how tokens are minted (a fixed emission per period, minted on close, split by the AI's weight), shared (solver, reporter, founder's share) and capped.

### Modified Capabilities
- `incentive-simulation`: new requirement "Token emission: scenarios and criteria".

## Impact

- **Code:**
  - `pof/tokens.py` (new): the emission and token balances, kept apart from the coin ledger;
  - `pof/params.py`: the token parameters, with the emission off by default;
  - `pof/market.py`: AI weights, and a mint record on close;
  - `pof/sim/market_world.py`: 0-coin bounties, and solvers pricing tokens;
  - `pof/sim/market_sim.py`: scenarios, report and criteria, and a `market tokens` summary;
  - `pof/sim/__main__.py`.
- **Reports:** `reports/tokens-v1.md` and its JSON.
- **Compatibility:** default runs and every earlier report stay reproducible (modes v5).
