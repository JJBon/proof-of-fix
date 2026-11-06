# oracle: the judge node (proof-of-fix#94, phase 1)

An oracle node checks a sealed submission, runs its tests in a sandbox, judges it, writes a **receipt**, **seals** its
verdict, **reveals** it, and **signs** the result `Race` already verifies (#75). An aggregator collects the reveals and
relays a quorum. Spec: `openspec/changes/proof-of-fix-94-oracle-node/`. Report: `reports/oracle-v1.md`.

**Cryptography** (keccak-256, secp256k1 with RFC 6979 and low-s, key recovery) comes from vendored, pinned, pure-Python
code in [`vendor/`](vendor/README.md): the Keccak team's reference implementation and python-ecdsa 0.19.2. It's checked
against `SHA256SUMS` by `scripts/check.sh` and re-created by `scripts/oracle-vendor.sh`. `crypto.py` keeps only
Ethereum's glue (address, `v`, EIP-712), pinned by tests to signatures made with `cast`. No other packages are needed,
so the check runs on the CI runner's Python 3.9 with no pip.

## Run it

```
python3 -m unittest tests.test_oracle   # crypto vectors (vs cast), the vendored files, keys, sandbox, judges, receipts, scenarios
scripts/oracle-run.sh                   # end to end on a throwaway anvil (Docker): the contract checks every relay
scripts/oracle-run.sh --devnet          # the same on the private devnet (#93), against its deployment record
```

**Locally**, `scripts/oracle-run.sh` deploys the loop's contracts (oracle keys `oracle0..oracle2`, quorum 2 of 3), funds
a bounty, seals the loop's bad and good fixes, and runs three registered nodes plus one outside the set.

**On the devnet**, `--devnet` uses the deployed Race and test coin from `contracts/deployments/devnet.json`, one node per
devnet oracle key (5) and the record's quorum (3). Keys come from OpenBao, through `scripts/devnet-keys.sh`, and pass
only through the environment:
```
export BAO_ADDR=https://vault.example.com && bao login -method=oidc role=admin
scripts/devnet.sh up && scripts/devnet.sh deploy     # if not already deployed
scripts/oracle-run.sh --devnet                       # adds a bounty and two submissions; the devnet keeps running
```
For tests, `DEVNET_KEYS=insecure-local` uses anvil's public mnemonic instead. A second devnet beside the first needs its
own `DEVNET_NAME` and `DEVNET_PORT`.

| Scenario (#93 comment 4603) | What happens |
|---|---|
| a forged relay: a quorum's worth of signatures, one from a key outside the set | the contract refuses it for the key (`NotOracle`) |
| the bad fix | every node fails it, the aggregator relays, outcome 2 on-chain |
| the good fix with one node lying | passes (2 to 1 locally, 4 to 1 on the devnet), the dissent is logged with its receipt, outcome 1 on-chain |
| the node outside the set | its reveals are ignored |
| too few nodes | nothing is relayed (the contract's `timeOut` applies) |
| a tampered receipt, a changed verdict, an early reveal | refused by the aggregator |
| a canary (a fix with a known outcome) | scores every node: the lying one 0 % |

## The node's command line

```
ORACLE_RPC=http://127.0.0.1:18545 ORACLE_RACE=0x… ORACLE_KEYS=local:0 python3 -m oracle info
ORACLE_RPC=… ORACLE_RACE=0x… python3 -m oracle watch      # ORACLE_KEYS defaults to dstack
docker build -f oracle/Dockerfile -t pof-oracle-node .    # pinned base image; its digest is the checker image
```

## Modes

| | Keys | Attestation | Use |
|---|---|---|---|
| `local:<i>` | forge's `makeAddrAndKey("oracle<i>")`: **public test keys** | none, labelled `none-insecure-local` | anvil only; refused on any other chain |
| devnet (`DevnetKeys`, used by `--devnet`) | the devnet's oracle keys from OpenBao, in memory for the run | none, labelled `none-devnet` | the devnet (chain 7193) only; refused on any other chain |
| `dstack` | derived inside the CVM by the dstack guest agent (`/var/run/dstack.sock`), never exported | the TDX quote over the receipt hash | a Phala dstack CVM (phase 2) |
| `dstack` + `DSTACK_SIMULATOR_ENDPOINT` | derived by dstack's simulator | a simulated quote, labelled `dstack-simulator` | local development with dstack's simulator |

Judges reuse B1's harness (#89): `pof.judges.prompt` (the prompt, with untrusted text quoted, and the verdict parser)
with the sandbox's test result in place of B1's "not provided" line; `FakeJudge` wraps `pof.judges.fake` (deterministic,
the default); `GatewayJudge` uses `scripts/judge_run.py`'s gateway client for one seat of `pof.judges.plan.SEATS` (the
AgentCore model gateway as `pof-judges-models`), for development and B1 only. **Counted judges call their provider
directly** (#118): `DirectJudge` with `oracle/models.py`, chosen by `ORACLE_JUDGE=direct:<provider>:<model>`:
`bedrock` (Converse, SigV4 with the instance role's IMDSv2 credentials, `ORACLE_MODEL_ALLOW` required), `anthropic`,
`openai` (any OpenAI-compatible server with `ORACLE_MODEL_URL`) or `gemini`, with the key from `MODEL_API_KEY` in a
header only. The provider's own token counts, the model, the endpoint's host and the request ID go into the receipt
and the usage report; spending guards cap the answer, the calls and the tokens per process. **Both are paid calls**:
no test makes one (`tests/test_models.py` uses fake servers on 127.0.0.1); use them only with the owner's approval.

## What is proven now, and what later

| Now (phase 1) | Later |
|---|---|
| the contract accepts the node's EIP-712 signatures, and refuses a key outside its set | keys inside a real CVM (phase 2) |
| every verdict has a receipt stored by hash; tampering is detected | the receipt hash on-chain (#122) |
| sealed verdicts and canaries, enforced by the aggregator | enforced on-chain (#122) |
| the sandbox: pinned image, no network, read-only, limits | the sandbox inside the CVM, its image measured |
| a real model called directly from a node on AWS, its token counts on-chain (#150) | judge quality measured (#160) |
| nothing about a node's honesty without a TEE: a local receipt is the node's own record | the TDX quote binds the receipt to the measured image |

## Phase 2 on Phala Cloud: the owner's steps (needs approval; outward)

1. Decide to proceed: it needs a Phala Cloud account and payment, and Phala sees the node image.
2. Build and push the image to a registry the CVM can pull from; record its digest.
3. Deploy one CVM running the image with `ORACLE_KEYS=dstack`, `ORACLE_RPC` (the #93 devnet, reachable privately) and
   `ORACLE_RACE`.
4. Run `python3 -m oracle info` in the CVM: the address and `dstack-tdx`.
5. Verify the TDX quote off-chain (Phala's open-source verification library) against the published image digest.
6. Deploy the devnet Race with that address in its oracle set, and rerun the scenarios against it.
7. Measure the cost per check and the latency.
