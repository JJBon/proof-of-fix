# The oracle node, v2: reviewed cryptography and the devnet (proof-of-fix#94)

**What changed since [`oracle-v1`](oracle-v1.md):**
- the node's hand-written cryptography (v1, gap 1) is gone, replaced by vendored, pinned upstream code;
- the nodes run against the private devnet (#93) and its deployment record.

Spec: `openspec/changes/proof-of-fix-94-oracle-node/` (D1, D1c, tasks 5.1–5.2).

## 1. Cryptography: vendored, pinned, pure Python
| Primitive | Now from | Pinned by |
|---|---|---|
| keccak-256 | the Keccak team's reference implementation (XKCP `CompactFIPS202.py`, by Gilles Van Assche, CC0) | commit `712fabcc` and the file's sha256 |
| secp256k1 signing, RFC 6979 nonces, low-s, key recovery | python-ecdsa 0.19.2 (MIT), with six 1.17.0 | the PyPI wheels' sha256 |

**How it's kept honest:**
- **`oracle/vendor/SHA256SUMS`** is checked by `scripts/check.sh` on every run, exactly as `contracts/lib` is.
- **`scripts/oracle-vendor.sh`** re-creates the folder, checking each download against its pinned hash first.
- **A test** checks the files against the sums, and that the node imports these copies.
- **`oracle/crypto.py` keeps only Ethereum's glue:** the address, `v`, and the EIP-712 struct encoding.

**Equivalence and independent vectors:**
- **The same bytes as v1's code** for keccak-256, signatures, addresses and recovery, on 150 random keys and messages. Only then was the old code removed.
- **Signatures pinned to `cast`** (alloy, an independent Rust implementation):
  - over a raw digest;
  - over a full EIP-712 `Result` with a two-entry `Fee[]`, on the devnet's chain ID and Race address.
- **The contract** (OpenZeppelin's EIP712 and ECDSA) accepts the node's signatures in both runs below.

**Why not a C library** (`coincurve`, `pycryptodome`): the required check runs on the CI test runner's Python 3.9 with no pip and no network, so only pure Python can be vendored.

**Speed** (this machine, Python 3.12):
| | Sign | Recover | keccak (1 KB) |
|---|---|---|---|
| v2 (vendored) | 5.3 ms | 4.9 ms | 2.3 ms |
| v1 | 3.9 ms | 7.8 ms | 1.6 ms |

Either is negligible next to a check, which runs tests and calls a model.

**Caveat:** python-ecdsa isn't constant-time. That's acceptable for devnet keys; real keys sign inside the node's enclave (dstack, phase 2).

## 2. The nodes on the devnet
`scripts/oracle-run.sh --devnet` uses the devnet's deployment record (`contracts/deployments/devnet.json`):
- the deployed Race and test coin;
- **one node per devnet oracle key (5), and the record's quorum (3)**;
- the participants' and oracles' keys from OpenBao (`scripts/devnet-keys.sh`), passed only through the environment;
- `DevnetKeys` refuses any chain but 7193.

Run on a separate local devnet (chain 7193, Osaka, EIP-170 enforced) with `DEVNET_KEYS=insecure-local` (the owner's run uses OpenBao):

| Scenario | Local (2 of 3) | Devnet (3 of 5) |
|---|---|---|
| a forged relay: a quorum's worth of signatures, one from outside the set | refused, `NotOracle` | refused, `NotOracle` |
| the bad fix | 3 nodes fail it; outcome 2 on-chain | 5 nodes fail it; outcome 2 on-chain |
| the good fix with one node lying | passes 2 to 1; dissent logged; outcome 1 | passes 4 to 1; dissent logged; outcome 1 |
| too few nodes, a tampered receipt, a changed verdict, an early reveal | refused | refused |
| canary | the liar 0 %, the others 100 % | the liar 0 %, the others 100 % |
| receipts stored by hash | 11 | 17 |

**A fix to the forged-relay scenario:** v1 forged with two signatures. Against quorum 3 that fails on the count before the contract looks at the keys. It now carries a quorum's worth, one from outside the set, and the run fails unless the contract refuses it for the key (`NotOracle`).

## Still open (from oracle-v1, unchanged)
**After the v2 contract changes (#85):**
- commit-reveal enforced on-chain;
- key registration from an attestation;
- the receipt hash on-chain;
- "check gas" fees, and the relayer's gas repaid.

**Phase 2 (needs the owner's approval):**
- dstack's real simulator;
- a container runtime in the CVM;
- a transport for seals and reveals between operators;
- one node on Phala Cloud.
