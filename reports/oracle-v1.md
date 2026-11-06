# The oracle node, v1 (proof-of-fix#94 phase 1, 2026-11-01)

**Commands:** `python3 -m unittest tests.test_oracle` (26 tests) and `scripts/oracle-run.sh` (end to end on a throwaway
anvil). Simulation only (rule 1): a local chain, anvil's public test keys, the deterministic fake judge, no model called.

## What works
- **Signatures the contract accepts.** The node signs Race's EIP-712 `Result` with standard-library secp256k1
  (RFC 6979, low-s). Its signature over keccak256("hello") with anvil's first key is byte for byte `cast wallet sign`'s,
  its domain separator equals the contract's, and the contract accepted every relayed quorum in the run.
- **The contract refuses a key outside its set:** a relay signed by node0 and an outsider reverted with `NotOracle`.
- **Checking:** the claim (fix tree, salt, solver) must hash to the sealed commitment; the tests run in the pinned
  Python image with no network, read-only, no capabilities, 256 MB, 64 processes, 300 s.
- **Receipts:** checker image, model and backend, the hashes of prompt and response, the fix's tree, the test image,
  command, exit code and hashes of results and logs, the verdict, the chain and contract, the attestation kind. Stored
  by sha256 of the canonical JSON (11 in the run).
- **Sealed verdicts:** seal, then reveal, then sign. Refused: a reveal before the seal phase closes, a reveal without a
  seal, a reveal that doesn't match its seal (a changed verdict), a receipt that doesn't hash to its revealed hash.
- **Quorum:** the bad fix failed 3 to 0; the good fix passed 2 to 1 with a lying node, its dissent logged; a node asked
  to sign an outcome it didn't reach refuses; too few nodes relay nothing; 5 of 7 passes with 2 liars and fails with 3.
- **Canaries:** the lying node scored 0 %, the honest ones 100 %.
- **Keys:** local test keys are refused on any chain but anvil's; the dstack provider derives the key and quotes the
  receipt hash through the guest agent's `GetKey` and `GetQuote` (tested against a fake agent).
- **The judge reuses B1's harness (#89):** `pof.judges.prompt` and its parser, `pof.judges.fake`, and
  `scripts/judge_run.py`'s gateway client per seat; only the prompt's "test runs not provided" line is replaced by the
  sandbox's result, so B1's prompt and plan hash are unchanged.
- **A container:** `oracle/Dockerfile` on the pinned Python image, non-root, standard library only.

## dstack locally
dstack ships a simulator in its repository (`sdk/simulator`: `./build.sh`, `./dstack-simulator`), reached with
`DSTACK_SIMULATOR_ENDPOINT` (an HTTP URL such as `http://localhost:8090`; some docs describe Unix sockets instead). The
SDK's `get_key(path, purpose)` returns the derived key and a signature chain; `get_quote(report_data)` takes up to 64 bytes
and returns the TDX quote and its event log. The SDK derives an Ethereum key as sha256 of the key material
(`to_account_secure`), which the node mirrors. Sources: [dstack-sdk on PyPI](https://pypi.org/project/dstack-sdk/0.5.4b1/),
[Phala's local development guide](https://docs.phala.network/dstack/local-development). **Not done here:** building
and running the simulator (it is built from source); the node talks to it over the same HTTP API, tested against a fake
agent. Run it against the real simulator in phase 2's preparation.

## Gaps
1. **Hand-written cryptography** (standard library only): checked by vectors and by the contract, but a production node
   should put a reviewed library (for example `coincurve`) behind the same functions. **Resolved in
   [`oracle-v2`](oracle-v2.md):** vendored, pinned python-ecdsa and the Keccak team's reference implementation.
2. **No real attestation yet:** without a TEE a receipt is only the node's own record. Phase 2 (Phala Cloud, the
   owner's approval) gives the TDX quote over the receipt hash.
3. **The sandbox needs Docker.** Inside a dstack CVM the node needs a container runtime for the tests; check what dstack
   offers (the CVM runs a docker-compose app) before phase 2.
4. **The rounds run in one process in the local run.** Between real operators, seals and reveals need a transport (the
   chain, after #93, or a signed message channel).
5. **The dstack HTTP paths** (`/GetKey`, `/GetQuote`) follow the SDK's documentation; confirm against the simulator.

## Follow-ups after #93 (contract changes)
- **On-chain commit-reveal:** the contract records each node's seal before reveals open, so the aggregator's checks
  become the contract's.
- **Key registration from attestation:** a node's key is admitted after the quorum checks its quote against the
  published image digest; the contract accepts only registered keys (today's set is fixed at deployment).
- **The receipt hash on-chain:** in `Result` (a new field) or an event, so anyone can fetch the evidence for a verdict.
- **"Check gas"** (#85 comment 4614): the solver deposits a maximum; the fee is the median of the nodes' signed usage
  times a price table plus a margin fixed in the constitution; the relayer's gas is repaid; the rest refunded.
- **The relayer's gas:** today the relayer pays it; it should come out of the check fee.
