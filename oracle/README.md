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
export BAO_ADDR=<your OpenBao address> && bao login -method=oidc role=admin
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

## v3: an open validator's node (#139, task 4.1 of #132)

`ORACLE_VERSION=3` with `ORACLE_RACE` set to a RaceV3 runs `oracle/node_v3.py` on #138's contracts. v2's node is
unchanged. Nothing is signed by a quorum in v3: each validator posts its own signed statements to Panels, which
counts the reveals.

| Command | What it does |
|---|---|
| `python3 -m oracle register --bond 100 --rad-node did:key:z6Mk…` | registers this key as a candidate: signed by the key, bonded from its account. On a devnet the proof type is `simulated`, and its attestation is a quote from the dstack simulator (`ORACLE_KEYS=dstack` with `DSTACK_SIMULATOR_ENDPOINT`, design D18). The registration also signs the validator's Radicle node key (#251, L11; on-chain as `radNodeOf`): `--rad-node` (a did:key, a Node ID or 0x and 64 hex digits), else `ORACLE_RAD_NODE`, else the node's own `rad self --did` through `ORACLE_RADICLE_EXEC`; `--rad-node none` registers without one, and the seat is then never counted as a delegate. Another node is another registration (leave, then register a new key) |
| `python3 -m oracle leave`, `withdraw-bond` | announces leaving; the bond returns after the unbonding delay |
| `python3 -m oracle run` | acts on every seat Panels gives the key, posts its cost table once a pricing period, and makes the keeper's calls |
| `python3 -m oracle challenge <submission>` | re-runs a counted verdict's check; if it disagrees, or finds a false receipt, files a challenge with its evidence |
| `python3 -m oracle post-table` | posts the table now |

**A seat, whatever its kind** (counted judge, shadow, auditor, challenge judge; on a drawn submission or one that
waits for a panel): the check, a receipt, the seal; after the seal window the receipt's hash and the reveal; then
the usage report to RaceV3. All four go through the `onchain` transport (`oracle/transport.py`), v3's default; the
hosted relay stays optional (`ORACLE_EXCHANGE_TRANSPORT=onchain,http`). In every pass the node sends all its seals
before any reveal, and a shadow's seal window is the counted panel's, so a shadow's seal is on-chain before any counted
reveal. A challenge judge also names the original judges' false receipts (the mask), from the receipts it can read
(`ORACLE_RECEIPT_SOURCES`).

**The receipt on-chain** is `Validators.receiptHash` of its proof type, notary, model, weights, image, the draw's
seed, the prompt's and the answer's hashes, the tests' result and the proof's hash. The proof is the key provider's
quote over that receipt and seat (a TEE, or the simulator on a devnet), or a zkTLS proof of the model call. The
document is kept under that hash in `<ORACLE_RECEIPTS>/v3/`.

**What it signed is on disk before it leaves** (`ORACLE_ROUNDS`, default `.oracle-rounds`): a restarted node reveals
the same vote with the same salt. A second, different statement for one seat is equivocation, the whole bond.

**The table** (`FeesV3.post`): the validator's own shared-unit costs (`ORACLE_COSTS`) and every family's public list
price (`pof/costs.py`, or `ORACLE_LIST_PRICES`). A unit or a priced family it has no value for is posted at the price
in force, so its table still counts.

**zkTLS** (`oracle/zktls.py`): the prover's interface for a node without a TEE, with the offline check of a proof.
The prover itself (`TlsnProver`, on task 1.9's TLSNotary tools) is a **stub**: it was never run, since it needs the
pinned Rust build, a notary and a paid model call. Level C is off at launch (`reports/zktls-spike-v1.md`).

**Choices made where the spec was open** (each the narrowest reading; for the owner's review):
1. **A registration check** is judged by v2's claim rule (#210): it passes when a labelled issue on the host validly
   claims the registration. With the fake judge only, as in v2. A node with a model judge stays silent on these
   checks, which costs it the silence slash, until a model's registration check is designed (#160).
2. **A check that can't be run by the deadline** (no pull request opens the commitment, or no claim) is sealed as not
   passed 10 minutes before the seal window closes, rather than left silent.
3. **The fix's base**: the claim's text has no base, so the node tries the pull request's base commit, then 0.
4. **A false receipt** (a challenge judge's mask, and `challenge`) is one whose document contradicts the chain or
   this node's own run: another proof type, image, draw or verdict than the seat's, a model it doesn't hash to, or a
   tests' result that isn't this node's. A receipt the node can't read is left alone. Receipts are read from
   directories (`ORACLE_RECEIPT_SOURCES`); publishing them anywhere else isn't built.
5. **The quote** is taken over the receipt, the draw's seed and the key, so no other seat can reuse it.
   A family's id is keccak256 of its name (D19's `anthropic/claude`), as are a host's and a TEE type's.
6. **The keeper's calls** are on by default and paid by the validator: `draw`, `advance`, `refill`, `drawAudits`,
   `drawChallenge`, `settleShadows`, `startWindow`, `finalize`, RaceV3's `signal`, `result`, `payPanel`,
   `settleChallenge`, `payShadow` and `finish`, and FeesV3's `roll`. `drawAudits` is sent again only after the
   registry changes: with no auditor eligible each call only re-targets, and the contract doesn't refuse it.
7. **The hosted relay** can be listed beside `onchain`, but the exchange service wasn't taught v3's messages: it
   refuses them, and the node goes on without it.

```
python3 -m unittest discover -s tests -p test_oracle_v3.py   # encodings against the sources; nodes against a fake chain
scripts/node-v3-e2e.sh                                       # the same nodes against the real contracts on anvil (Docker)
scripts/node-v3-e2e.sh --grow                                # until the candidates qualify: a panel of 3, an auditor
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
model gateway at `MODEL_GATEWAY_URL`, required with no default, as `pof-judges-models`), for development and B1
only. **Counted judges call their provider directly** (#118): `DirectJudge` with `oracle/models.py`, chosen by `ORACLE_JUDGE=direct:<provider>:<model>`:
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
