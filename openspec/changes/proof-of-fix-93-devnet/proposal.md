# Proposal

## Why
The owner (2026-11-01, #93) wants the contract deployed before the AI judging is measured, on a **private Ethereum devnet** with mainnet's rules: no public footprint, and rule 1 intact. Race was 27,079 bytes, over EIP-170's 24,576, so it only ran on an anvil that lifted the limit. No real chain, and no devnet with mainnet's rules, would accept it.

## What Changes
- **Race under EIP-170 with no change in behaviour:**
  - the compiler's IR pipeline (`via_ir`);
  - the oracle quorum's signature check moved into an external, stateless, linked library, `OracleAuth`, with the same rules and the same errors.
  - Race is now 23,065 bytes. The tests, the invariants and the replay are unchanged.
- **The local loop no longer lifts the size limit.**
- **A private devnet** (`scripts/devnet.sh`):
  - anvil from the pinned Foundry image, on mainnet's current hardfork (Osaka) with the size limit enforced;
  - its own chain ID (7193) and a block every 2 seconds;
  - its RPC on 127.0.0.1 only, and its state kept in `.devnet/`.
- **Deployment** (`contracts/script/Deploy.s.sol`, `scripts/devnet.sh deploy`): a test coin, the Token, Race and its library, and the Quoter, with the oracle keys fixed at deployment. It writes `contracts/deployments/devnet.json` (addresses, code hashes, block, commit, and where the keys came from).
- **Keys** (`scripts/devnet-keys.sh`): one devnet-only key per role, created offline and kept only in OpenBao at `secret/proof-of-fix/devnet/<role>`. Scripts read them from there; anvil's public mnemonic is used only with `DEVNET_KEYS=insecure-local`. No key is printed, logged, committed, or put on a command line.
- **The bounty loop on the devnet:** `scripts/bounty-loop.sh --devnet`.
- **The oracle path's scenarios on the devnet** (`scripts/devnet.sh scenarios`): the signed quorum's acceptances and refusals against the deployed Race, the gas of the signature check at 3 to 7 signatures, and EIP-170 checked on the devnet itself.
- **The report:** `reports/devnet-v1.md`.

## Capabilities

### New Capabilities
- `private-devnet`: the private Ethereum devnet with mainnet's rules: what runs there, how contracts are deployed and recorded, where keys come from, and what is checked against it.

### Modified Capabilities
None. The contract's behaviour is unchanged, and #56's `local-contract` requirements still hold (local chains, test keys, no public chain).

## Impact
- **Contracts:**
  - `contracts/src/Race.sol` (`_authorize` delegates to the library);
  - `contracts/src/OracleAuth.sol` (new);
  - `contracts/foundry.toml` (`via_ir`, write access to `deployments/`);
  - `contracts/script/Loop.s.sol` (the oracle keys from the environment on the devnet);
  - `contracts/script/Deploy.s.sol` and `contracts/script/Scenarios.s.sol` (new).
- **Bot:** `bot/chain.py` and `bot/loop.py` (the devnet's chain ID, keys passed through the environment).
- **Scripts:**
  - `scripts/devnet.sh` and `scripts/devnet-keys.sh` (new);
  - `scripts/bounty-loop.sh` (`--devnet`, no size-limit lift);
  - `scripts/contracts.sh` (`sizes`).
- **Gas:** the IR pipeline and the library call change gas per call. Behaviour and balances don't change: the replay still matches the simulation to the micro-credit.
- **Not in scope:** public chains (after D1); the #85 v2 contracts; the oracle node (#94).
