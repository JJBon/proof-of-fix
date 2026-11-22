## Why

proof-of-fix#94 (owner, 2026-11-01: "we got our oracle, let's do the MVP on Phala"). The oracle so far is a stand-in: the
loop's forge script signs results with test keys (`contracts/script/Loop.s.sol`). #85 (comment 4614) designs judges that
nobody has to trust: each verdict carries a receipt (which checker image ran, the hashes of the judge's prompt and
answer, the model, the commit, the test results), the signing key lives inside a confidential VM (Phala dstack) whose
attestation ties it to the image, verdicts are sealed before they are revealed so no node can copy another, and canary
fixes with known answers make each node's accuracy measurable.

This change builds phase 1 of #94, off-chain only: the `oracle-node` that watches the chain, checks a submission, judges
it, and signs the result the current contract already verifies (#75), plus the aggregator that relays a quorum. The
contract is not changed here: #93 is splitting Race under EIP-170 at the same time, and the on-chain parts (commit-reveal,
key registration from an attestation, the receipt hash on-chain, fees for gas) are follow-ups after #93.

## What Changes

- New `oracle/` package and container: the judge node.
  - Watches the chain over JSON-RPC (anvil today, the #93 devnet next) for committed submissions.
  - Checks a submission: the solver's claim must match its sealed commitment; the fix's tests run in a sandbox (pinned
    image by digest, no network, read-only, time and memory limits); results and logs are hashed.
  - Judges with a backend chosen per run: a deterministic fake (the default) or the model gateway (OpenAI-compatible
    chat, client `pof-judges-models`), never called in tests.
  - Signs the EIP-712 `Result` exactly as `Race` verifies it, and writes a receipt, stored content-addressed by its hash.
  - Keys behind one interface: dstack (the guest agent's key derivation and TDX quote, inside a Phala CVM, or its
    simulator) or an insecure local provider for the devnet only, clearly labelled.
  - Seals its verdict first (a commitment) and reveals it later; canary fixes with known labels score its accuracy.
- An aggregator: collects sealed verdicts, then reveals; refuses a reveal that doesn't match its seal, a receipt whose hash
  doesn't match, or a signer outside the contract's oracle set; relays the result once a quorum agrees.
- A local run: N nodes against a throwaway anvil with the loop's deployment, and the scenarios of #93 comment 4603.
- `oracle/README.md` and `reports/oracle-v1.md`.

Out of scope: any contract change (after #93); Phala Cloud or any account, payment or outside service (phase 2 needs the
owner's approval); paid model calls; public chains; GPU-hosted models.

Actors and attacks affected: oracle operators (the judges); a lying node (minority dissent), a lazy node copying others
(commit-reveal), a node outside the set, a tampered receipt, too few nodes online. The incentives (check fees) are
unchanged; their on-chain form ("check gas") is a follow-up.

## Capabilities

### New Capabilities
- `oracle-node`: the judge node and its aggregator: checking, judging, receipts, keys, sealed verdicts, canaries, quorum.

### Modified Capabilities

## Impact

- New: `oracle/`, `tests/test_oracle*.py`, `scripts/oracle-run.sh`, `reports/oracle-v1.md`.
- Unchanged: `contracts/`, `bot/` (read-only reuse of the loop's deployment script and its test keys).
- Rule 1 holds: everything runs on this machine against a throwaway chain, with test keys anyone can derive.
