# Tasks

## 1. Race under EIP-170
- [x] 1.1 Compile with the IR pipeline, and move the oracle quorum's signature check into the external library `OracleAuth` with the same rules and errors. Verify: `scripts/contracts.sh sizes` shows Race at 23,065 bytes (every contract under 24,576), and `scripts/contracts.sh test` passes 135/135, with the replay matching to the micro-credit.
- [x] 1.2 The local loop stops lifting the size limit. Verify: `scripts/bounty-loop.sh` passes end to end.

## 2. The devnet
- [x] 2.1 `scripts/devnet.sh up/down/status/reset`: the pinned image, Osaka, chain 7193, a 2-second block time, RPC on 127.0.0.1, state in `.devnet/`. Verify: `status` shows chain 7193 and Osaka.
- [x] 2.2 `scripts/devnet-keys.sh`: keys created offline into OpenBao, read from there, and anvil's mnemonic only with `DEVNET_KEYS=insecure-local`. Verify: `tests/test_bot.py` (keys only when asked; never on a docker command line).
- [x] 2.3 `contracts/script/Deploy.s.sol` and `scripts/devnet.sh deploy`, writing `contracts/deployments/devnet.json`. Verify: a deployment from a clean devnet writes the record with the code hashes.

## 3. On the devnet
- [x] 3.1 `scripts/bounty-loop.sh --devnet`. Verify: the loop passes end to end on the devnet.
- [x] 3.2 `scripts/devnet.sh scenarios`: the oracle path's scenarios against the deployed Race, gas at 3 to 7 signatures, and EIP-170 on the node. Verify: every scenario reports ok, 24,576 bytes deploy and 24,577 are refused.
- [x] 3.3 `reports/devnet-v1.md`. Then run the check: `scripts/check.sh`, `scripts/contracts.sh test`, and `openspec validate proof-of-fix-93-devnet --strict`.

## 4. The owner, after merge
- [ ] 4.1 `scripts/devnet-keys.sh init`, signed in to OpenBao, then `scripts/devnet.sh up && scripts/devnet.sh deploy && scripts/devnet.sh scenarios` with the OpenBao keys. Commit the resulting record.
