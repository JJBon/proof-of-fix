## 1. Spec

- [x] 1.1 This change validates: `openspec validate proof-of-fix-94-oracle-node --strict`, and `scripts/check_openspec.py`.

## 2. The node

- [x] 2.1 `oracle/crypto.py`: keccak-256, secp256k1 sign and recover (RFC 6979, low-s), addresses, ABI words, the EIP-712 `Result` digest. Verify with tests against known vectors (anvil's first key and address, keccak of empty and of "oracle0").
- [x] 2.2 `oracle/keys.py`: `LocalDevKeys` (refused off the local chain IDs) and `DstackKeys` (GetKey, GetQuote over HTTP or the Unix socket). Verify with tests, the dstack one against a fake agent.
- [x] 2.3 `oracle/sandbox.py`: the fix's tests in a pinned image with no network, read-only, limits; results and logs hashed. Verify with a test that a passing and a failing fix give exit codes 0 and non-zero (skipped without Docker).
- [x] 2.4 `oracle/judge.py`: the prompt, the fake backend and the gateway backend, reusing `pof/judges` (#89) and `scripts/judge_run.py`'s client. Verify with tests: the fake is deterministic; the gateway sends the expected request to a fake HTTP server and parses its answer; no real endpoint is called.
- [x] 2.5 `oracle/receipt.py`: the receipt, its canonical hash, the content-addressed store. Verify with tests: a changed field changes the hash; a stored receipt reads back by hash.
- [x] 2.6 `oracle/node.py`: check, judge, seal, reveal, sign. Verify with tests: the claim must match the commitment; the signed digest recovers to the node's address.

## 3. The aggregator and the scenarios

- [x] 3.1 `oracle/aggregator.py`: seals then reveals, receipt and set checks, quorum, signature order, relay. Verify with tests for: honest quorum, minority dissent, too few nodes, a key outside the set, a tampered receipt, a reveal before the seal phase closes or not matching its seal, 5 of 7.
- [x] 3.2 `oracle/chain.py`: JSON-RPC reads (chain ID, calls, logs) and relaying through `cast` in the loop's Foundry container. Verify with the local run.
- [x] 3.3 `scripts/oracle-run.sh`: a throwaway anvil, the loop's deployment, a bad and a good fix submitted, 3 registered nodes plus 1 unregistered, the result relayed; the contract refuses a forged quorum. Verify by running it: the bad fix fails, the good one passes, and the forged relay reverts.

## 4. Docs and the check

- [x] 4.1 `oracle/README.md` (run it, modes, what is proven now and later, the owner's steps for phase 2 on Phala Cloud) and `reports/oracle-v1.md` (what works, gaps, follow-ups after #93).
- [x] 4.2 Run the check: `scripts/check.sh` (Python tests and the OpenSpec checks).

## 5. Reviewed cryptography and the devnet (after #93)

- [x] 5.1 Replace the hand-written keccak-256 and secp256k1 with vendored, pinned, pure-Python code (D1): `oracle/vendor/` (XKCP's Keccak reference, python-ecdsa 0.19.2, six 1.17.0), `scripts/oracle-vendor.sh`, and `SHA256SUMS` checked by `scripts/check.sh`. Verify: the same bytes as the old code on 150 random keys and messages; tests pin `cast`'s signatures over a raw digest and an EIP-712 `Result` with `Fee[]`; a test checks the vendored files against `SHA256SUMS` and that the node imports them; the contract accepts the node's signatures (`scripts/oracle-run.sh`).
- [x] 5.2 `scripts/oracle-run.sh --devnet` (D1c): the devnet's deployment record, its oracle keys and quorum, `DevnetKeys` refused off chain 7193, and a forged relay refused for its key. Verify by running it on a devnet with `DEVNET_KEYS=insecure-local`: 5 nodes, quorum 3, every scenario of the local run passes; and the local run still passes.
