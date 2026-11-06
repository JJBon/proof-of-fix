# The private devnet, v1 (proof-of-fix#93, 2026-11-01)

**Commands:**
- `scripts/devnet.sh up`, `deploy` and `scenarios`;
- `scripts/bounty-loop.sh --devnet`;
- `scripts/contracts.sh sizes` and `test`.

Everything ran on this machine, with anvil's public test keys (`DEVNET_KEYS=insecure-local`), because the OpenBao keys are the owner's to create (`scripts/devnet-keys.sh init`). No public chain was touched (rule 1). The spec is `openspec/changes/proof-of-fix-93-devnet`.

## Result
| Check | Result |
|---|---|
| Race under EIP-170 | ✅ **23,065 bytes**, from 27,079; 1,511 bytes of room |
| Contract tests | ✅ 135/135, the replay matching the simulation to the micro-credit |
| The local loop, with the size limit **enforced** (no more `--disable-code-size-limit`) | ✅ passes end to end |
| The loop on the devnet (`--devnet`) | ✅ passes end to end, with the same balances to the micro-credit |
| The oracle node's run (#94, `scripts/oracle-run.sh`), with the limit enforced | ✅ passes |
| The oracle path's scenarios against the deployed Race | ✅ 11 of 11 |
| EIP-170 on the devnet itself | ✅ 24,576 bytes deploy, 24,577 are refused |
| Python check (`scripts/check.sh`) | ✅ 516 tests OK |

## The split
- **The IR pipeline** (`via_ir`) plus **the oracle quorum's signature check moved into a linked library,** `OracleAuth`.
  - The library is external, stateless, ownerless, and runs on Race's own storage.
  - **It keeps the same rules in the same order** (replay, count, each signer in the set, strictly increasing addresses), **and the same errors,** so the selectors don't change.
  - Its address is fixed in Race's code at deployment, so there's still no key and no upgrade path.
- **No ABI change.** Race's external functions, the EIP-712 type strings and the domain are unchanged, so the bot, the replay and the oracle node (#94) work as before.

| Contract | Runtime size (bytes) | Room under 24,576 |
|---|---|---|
| Race | **23,065** (was 27,079) | 1,511 |
| Token | 7,084 | 17,492 |
| Quoter | 2,430 | 22,146 |
| BasketsHarness (tests only) | 7,649 | 16,927 |

## Gas per step after the split
Medians per call on `Race.t.sol`, compared with `contract-v1`'s, measured the same way:

| Call | Before | After | Change |
|---|---|---|---|
| `register` | 273,289 | 271,828 | −0.5 % |
| `accept` (signed) | 149,126 | 153,006 | +2.6 % |
| `pledge` | 159,408 | 158,410 | −0.6 % |
| `attempt` | 125,053 | 124,005 | −0.8 % |
| `commit` | 295,087 | 294,302 | −0.3 % |
| `result` (signed) | 205,594 | 208,863 | +1.6 % |
| `merged` (signed) | 202,838 | 206,670 | +1.9 % |
| `settle` | 391,429 | 389,896 | −0.4 % |
| `claimInstalments` | 104,995 | 105,158 | +0.2 % |
| `withdraw` | 53,800 | 54,754 | +1.8 % |
| `sunset` | 90,577 | 90,072 | −0.6 % |
| `claimRefund` | 169,941 | 170,222 | +0.2 % |
| **One paid fix** (costs-v1's counts per call) | **3,542,916** | **3,555,627** | **+0.4 %** |

- **The signed calls cost about 3,300–3,900 more:** the call into the library.
- **The others got slightly cheaper** under the IR pipeline.
- **In dollars,** at costs-v1's prices (0.05 gwei, ETH at $2,700, a $0.01 data fee per transaction), a paid fix stays at about **$0.67**.

## The oracle path on the devnet
These run on a fork of the devnet's state against the deployed Race (5 oracle keys, quorum 3), broadcasting nothing:

| Scenario | Expected | Result |
|---|---|---|
| A quorum of distinct oracles signs `accept` | the bounty opens | ✅ |
| The 2 dissenting keys alone sign `junk` | refused: `TooFewSignatures` | ✅ |
| The quorum still opens it despite the dissent | opens | ✅ |
| One signature short of the quorum (operators offline) | `TooFewSignatures` | ✅ |
| A key outside the deployed set | `NotOracle` | ✅ |
| A forged signature (random r, s) | refused | ✅ |
| The same oracle twice | `DuplicateSigner` | ✅ |
| A replayed signed action | `Replayed` | ✅ |
| Signed for another chain (ID 1) | `NotOracle` | ✅ |
| Signed for another contract | `NotOracle` | ✅ |
| A colluding minority signs a bad verdict | `TooFewSignatures` | ✅ |

**The gas of the signature check:**
- **`accept` costs about 137,000–156,000 gas,** depending on how many signatures it carries;
- **each signature beyond the quorum adds about 4,760 gas** (the signature recovery, its calldata, the checks);
- with quorum 4 of 7: 143,989 at 4 signatures, 155,773 at 7;
- the first extra signature on each fresh Race shows about 2,260, because the first measurement pays some one-off costs.
- **So a 7-judge verdict costs about 12,000 gas more than a 3-judge one,** under a cent on a layer-2 chain.

## The devnet
- **Pinned anvil** (the contract tests' Foundry image) running **Osaka**, mainnet's current hardfork.
  - It enforces EIP-170.
  - It also enforces EIP-7825's per-transaction gas cap of about 16.8 million. Race's deployment fits; the scenarios' gas measurements deploy one Race per call because of it.
- **Chain ID 7193,** a block every 2 seconds, RPC on 127.0.0.1:8546 only, and state kept in `.devnet/`.
- **The deployment record** (`contracts/deployments/devnet.json`) holds:
  - the chain, the block, the commit and the key source;
  - the addresses of the coin, the Token, Race and the Quoter;
  - the runtime code hashes, Race's code size, and the oracle set with its quorum.

  The committed record is from the insecure local keys (`"keys": "insecure-local"`). The owner's deployment with the OpenBao keys replaces it (task 4.1).

## Gaps and follow-ups
1. **No binding to the base commit:**
   - a signed `result` binds the fix (its tree hash), the submission, the bounty and the fees, but not the base commit the fix was checked against;
   - so a verdict made against an older main isn't refused for that reason;
   - binding it is #85's change for v2, together with the on-chain head.
2. **The library's code hash isn't in the record yet.** Race's code embeds the library's address, so Race's hash covers *which* library, but anyone checking a deployment should also check the library's code. That's a small addition to `Deploy.s.sol`.
3. **The devnet loop uses 2 of 3 oracle keys,** like the local loop, whose expected balances count two signing oracles. The deployment itself uses 5 keys with quorum 3.
4. **Only on this machine.** A hosted devnet reachable only over NetBird is a later option.
5. **The owner's step:** `scripts/devnet-keys.sh init` (signed in to OpenBao), then deploy and run the scenarios with those keys, and commit the record.
