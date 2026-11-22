## Context

`Race` accepts an oracle action when at least `quorum` distinct keys of its fixed set sign the action's EIP-712 digest
(domain "proof-of-fix Race", version "1", the chain ID and the contract), ordered by signer address, each digest once
(#75). The loop's stand-in signs inside a forge script with the test keys `oracle0..oracle2` (quorum 2 of 3). #94 asks for
a real node: something an independent operator runs, whose verdicts carry evidence and whose key can live in a TEE.

## Goals / Non-Goals

**Goals:** a node any operator can run from one container; verdicts the current contract accepts unchanged; receipts
binding each verdict to its evidence; a key interface that works in a Phala dstack CVM and locally; sealed verdicts and
canaries in the node; an aggregator; the #93 scenarios on a local chain.

**Non-Goals:** contract changes (after #93); real attestation verification (phase 2, on real hardware); paid model calls.

## Decisions

### D1. Vendored, pinned, pure-Python cryptography
CI runs `python3 -m unittest` on the test runner's Python 3.9 with no packages, no pip and no network. So the node's
cryptography is **vendored**, as `contracts/lib` is: `oracle/vendor/` holds pinned upstream code, checked against its
`SHA256SUMS` by `scripts/check.sh` and re-created by `scripts/oracle-vendor.sh` (each download checked against a pinned
hash first).
- keccak-256: the Keccak team's reference implementation (XKCP `CompactFIPS202.py`, commit `712fabcc`, CC0);
- secp256k1 signing with RFC 6979 nonces, low-s encoding and key recovery: python-ecdsa 0.19.2 (MIT), with six 1.17.0.

`oracle/crypto.py` keeps only Ethereum's glue (the address, `v`, the EIP-712 struct encoding). It produced the same bytes
as the hand-written phase-1 code on 150 random keys and messages before that code was removed. Tests pin signatures made
by `cast` (alloy): a raw digest, and a full EIP-712 `Result` with its `Fee[]` array; the contract accepting the node's
signatures stays the end-to-end check. C libraries (`coincurve`, `pycryptodome`) were ruled out: they can't be vendored
for the check's Python. python-ecdsa isn't constant-time: acceptable for devnet keys; real keys are signed inside the
node's enclave (dstack, phase 2).

### D1c. The devnet mode
`scripts/oracle-run.sh --devnet` runs the nodes against the private devnet (#93) and its deployment record: the deployed
Race and test coin, one node per devnet oracle key (`ORACLE_KEYS`, from OpenBao through `scripts/devnet-keys.sh`, or
anvil's mnemonic with `DEVNET_KEYS=insecure-local`), the record's quorum. Devnet keys are held by `DevnetKeys`, refused
on any chain but 7193. The forged relay carries a quorum's worth of signatures with one from outside the set, so the
contract refuses it for the key (`NotOracle`), not the count.

### D1b. The judge reuses B1's harness
`pof.judges.prompt` (#89) builds the prompt and parses the verdict; `pof.judges.fake` is the stand-in; the gateway
client is `scripts/judge_run.py`'s (network code stays out of `pof/`, rule 1). B1's judges see no test run and a node
does, so the node replaces only the prompt's "Test runs: not provided" line with the sandbox's result; B1's prompt
and its plan hash stay unchanged.

### D2. What a node signs
Exactly `Result(uint256 submission,uint256 bounty,uint8 outcome,bytes32 fix,Fee[] fees,bytes32 nonce)` with
`Fee(address to,uint256 amount)`, as the contract hashes it. Outcome 1 = pass, 2 = fail. The nonce is
`keccak256(abi.encode(submission, bounty, fix))`, so every node signs the same digest for the same verdict and the
signatures combine. Fees: one `ORACLE_FEE` (0.3 coin, as the loop) to each agreeing signer, in signer order. The
signers aren't known until the reveals are in, so a node signs the `Result` last, after the aggregator names them
(seal, reveal, then sign); its reveal is signed over the receipt hash instead.

### D3. The receipt
A JSON object following the IETF draft "Attested Inference Receipt" where it fits (draft-tsyrulnikov-rats-attested-
inference-receipt-02): `version`, `node` (signer address), `checker_image` (digest), `model` (id and backend),
`prompt_sha256`, `response_sha256`, `base_commit` (the fix's tree), `tests` (image digest, command, exit code,
`results_sha256`, `logs_sha256`), `verdict` (outcome, submission, bounty),
`attestation` (its kind: `dstack-tdx`, `dstack-simulator` or `none-insecure-local`; the quote is stored next to the
receipt), `chain`, `issued_at`. Its
hash is `sha256` of its canonical JSON (sorted keys, no spaces); it is stored as `<hash>.json` in a content-addressed
directory and its hash goes in the TDX quote's report data (dstack mode). The contract can't carry the hash yet, so the
aggregator checks it off-chain; putting it on-chain is a follow-up.

### D4. Keys
`KeyProvider` with `address()`, `sign(digest)` and `quote(report_data)`:
- `DstackKeys`: the dstack guest agent (`/var/run/dstack.sock`, or `DSTACK_SIMULATOR_ENDPOINT`): `GetKey` with the path
  `pof/oracle/<chain>/<race>` derives the key inside the CVM; the Ethereum key is `sha256` of the derived key material (as
  the SDK's `to_account_secure`); `GetQuote` returns a TDX quote over the receipt hash. Spoken over HTTP with the
  standard library (no SDK dependency).
- `LocalDevKeys`: **insecure, devnet only**: the test key `uint256(keccak256("oracle<i>"))`, as forge's
  `makeAddrAndKey`, so it matches the loop's deployment. Its "quote" is labelled `none-insecure-local`.
The node refuses to start with `LocalDevKeys` against a chain ID other than anvil's 31337 or the devnet's.

### D5. Sealed verdicts and canaries
A node first publishes `seal = keccak256(abi.encode(receipt_hash, outcome, salt, node))`, then reveals `(outcome,
receipt, salt, signature)`. The aggregator accepts reveals only after the seal phase closes and only if they match; a
node that changes its verdict after seeing others' is caught. Canaries: fixtures with a known label are sent to nodes
like real submissions; a node's canary record (right, wrong) is its accuracy score. On-chain enforcement of both is a
follow-up after #93.

### D6. Quorum in the aggregator
The aggregator reads the oracle set and quorum from the contract (`oracleKeys()`, `quorum()`), drops reveals signed by a
key outside the set, groups by outcome, and relays the outcome with at least `quorum` matching signatures (ordered by
address). Dissent is logged with its receipt. With fewer than `quorum` agreeing, nothing is relayed and the submission
stays open for the contract's `timeOut`.

### Parameters
| Name | Value | Why |
|---|---|---|
| `ORACLE_FEE` | 0.3 coin per signer | as the loop's deployment (`Loop.s.sol`) |
| quorum | the contract's (2 of 3 in the local run) | the deployed set |
| sandbox | no network, read-only, 256 MB, 64 pids, 300 s | as the loop's check |
| seal phase | until every expected node sealed or 30 s | local run; on-chain windows come with the contract change |

## Risks / Trade-offs

- Vendored crypto (D1): pure Python, so not constant-time and slower than a C library; pinned and checked, and real keys
  sign inside the enclave. A vendored copy must be refreshed by `scripts/oracle-vendor.sh` when upstream ships a fix.
- The local provider's keys are public test keys: refused on any other chain (D4).
- dstack's HTTP API is implemented from its SDK's documentation and tested against a fake agent; the real agent and its
  simulator are checked in phase 2.
- The receipt proves the node's own record; without a TEE quote it proves nothing about the node's honesty. That is why
  phase 2 runs on real hardware.

## Open Questions

- Whether the receipt hash goes into `Result` (a new field, a contract change) or a separate event (after #93).
