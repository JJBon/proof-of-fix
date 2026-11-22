# Design

## Context
Race was 27,079 bytes (`reports/contract-v1.md`), 2,503 over EIP-170. The #85 v2 contracts will be reorganised anyway (S10), so this change only has to make **v1** deployable under mainnet's rules, without changing what it does. The owner chose a private devnet over Sepolia, so it stays under wraps.

## Decisions

### D1. The split: the IR pipeline plus a linked library, with no change to the source's rules
- **The IR pipeline (`via_ir = true`)** alone brings Race from 27,079 to about 23,450 bytes, with no change to the source.
- **The library, `OracleAuth`:** the signature check moves into an external library on Race's own storage. It has the same order of checks (replay, count, each signer in the set, strictly increasing addresses) and **the same custom errors, so the same selectors.** That brings Race to **23,065 bytes**, leaving 1,511 bytes of room.
  - **Keyless:** the library has no state, no owner and no upgrade path; its address is fixed in Race's code at deployment.
- **Considered and rejected:**
  - a proxy or diamond, which would bring an upgrade key, against D15;
  - splitting the market into two contracts, a much larger change to v1 when v2 reorganises it anyway (#85 S10);
  - the optimizer's runs alone, which isn't enough.
- **Gas changes; balances don't.** The replay (`Replay.t.sol`) still matches the simulation to the micro-credit.

### D2. The devnet: anvil with mainnet's rules
- **The same pinned Foundry image** as the contract tests.
- **The Osaka hardfork:** mainnet's current one, since Fusaka. It still enforces EIP-170 and adds EIP-7825's per-transaction gas cap, about 16.8M, which the deployment fits.
- **Chain ID 7193** (no public chain's), **a block every 2 seconds,** and **state persisted** in `.devnet/` across restarts.
- **RPC only on 127.0.0.1.**
- A hosted devnet reachable only over NetBird is a later option, not in this change.

### D3. Keys
- `scripts/devnet-keys.sh init`, **run once by the owner,** creates each role's key in the pinned image, offline, and sends it on stdin straight to OpenBao at `secret/proof-of-fix/devnet/<role>` (field `key`).
- The roles:
  - `deployer`, `bot`, `reporter`, `funder`, `solver-a`, `solver-b`, `infrastructure`, `insurance`, `founder`;
  - `oracle-0` to `oracle-4`: 5 keys, quorum 3.
- **How scripts pass keys around:** they read keys with `bao kv get` and pass them to forge and cast through the container's environment or stdin. The bot hands them over by name (`LOOP_PK`), substituted inside the container. No key ever appears on a host command line.
- `DEVNET_KEYS=insecure-local` switches to anvil's public mnemonic, for tests and CI, and the deployment record says which source was used.

### D4. Scenarios on a fork, the size limit on the node
- The signed quorum's scenarios run as a forge script **on a fork of the devnet's state, against the deployed Race**, broadcasting nothing. The oracle keys reach the script on stdin.
- The scenarios live in their own contract, because forge refuses scripts that rely on their own address.
- **Gas per signature count:** each count is measured on a fresh Race deployed in the fork, one call per Race, to stay under Osaka's per-transaction gas cap.
- **EIP-170 is checked on the node itself,** not by forge: a create transaction returning 24,576 zero bytes deploys, and one returning 24,577 is refused.

### D5. The loop on the devnet
- `bounty-loop.sh --devnet` runs the same loop against the running devnet: its chain ID, the keys from OpenBao, and **2 of 3 oracle keys,** as the local loop, whose expected balances count two signing oracles.
- The devnet keeps running afterwards. Each loop run deploys its own Race and Token.

## Risks
- **The library adds a `DELEGATECALL` per signed action,** a little gas. It's also one more contract to verify, so its code hash belongs in the deployment record (a follow-up in the report).
- **The IR pipeline compiles more slowly.**
- **No binding to the base commit:** a `result` binds the fix (its tree hash), not the base commit it was checked against. That's #85's S-level change, for v2.
