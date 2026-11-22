# Run a validator

A validator registers a bond, an attestation and its Radicle node's key; panels drawn at random then ask its node to
check fixes. The launch's validators run [the SEV-SNP kit](../../validator-kit/README.md)
in their own AWS account: one measured, read-only disk on an AMD SEV-SNP instance that's started only when its key is
drawn. Everything here is on the Sepolia testnet with the project's **test coin, POFTEST, which has no value**
([intended use](../../README.md#intended-use)); your AWS and model costs are real (the kit's
[COSTS.md](../../validator-kit/COSTS.md), and its spending caps).

You need: an AWS account, OpenTofu, Docker, git, Python 3.9 or later and [Radicle 1.10.3](https://radicle.xyz).

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint>
export RID=<proof-of-fix's Radicle id, rad:z…, from the deployment record>
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record
export FAMILY=<your model family, e.g. anthropic/claude: one the deployment prices>
```

## 1. Your Radicle node and the code

A validator's Radicle node serves the patches it judges and, once it holds a seat, pushes the canonical `main` when
`Heads` moves. Its key goes in the registration, and can't be changed later. This one, on your machine, is for reading
the code and for the devnet rehearsal below; on Sepolia the kit's disk runs the validator's own node, and its key is
the one you register (step 3).

```bash
rad auth --alias "$(whoami)"                 # once: your Radicle key (it asks for a passphrase)
```

<!-- test: radicle-config -->
```bash
rad node start
```

<!-- test: radicle-peers -->
```bash
rad clone "$RID" proof-of-fix && cd proof-of-fix
export RAD_NODE=$(rad self --did)            # did:key:z6Mk…: your registration names it
```

## 2. Rehearse the registration on a devnet

The same `register` the kit's node runs, on a local chain, with its key and a simulated attestation from
[dstack's simulator](https://github.com/Dstack-TEE/dstack) instead of the SEV-SNP report. For the chain:
`scripts/devnet.sh up && scripts/devnet.sh deploy-v3`, and use its RPC and record instead of Sepolia's.

<!-- test: devnet-values -->
```bash
export ORACLE_VERSION=3 ORACLE_RPC=http://127.0.0.1:8546 RECORD=contracts/deployments/devnet-v3.json
export DSTACK_SIMULATOR_ENDPOINT=http://127.0.0.1:8090    # where your dstack simulator listens
```

```bash
export ORACLE_KEYS=dstack                    # the node's key and quote from the simulator (devnets only)
export ORACLE_RACE=$(python3 -c 'import json, sys; r = json.load(open(sys.argv[1])); print(r.get("race") or r["addresses"]["race"])' "$RECORD")
export VALIDATOR=$(python3 -m oracle info | awk '{print $2}')
echo "fund $VALIDATOR with gas and the bond"
```

<!-- test: bond -->
```bash
ORACLE_FAMILY="$FAMILY" ORACLE_HOST_ID=home-1 python3 -m oracle register --bond 250 --proof simulated \
  --rad-node "$RAD_NODE"
```

It prints `registered 0x… as a candidate (…, Radicle node did:key:…)`: the validator is drawn as a shadow until its
verdicts qualify it.

## 3. The kit, in your AWS account

Build the disk (no AWS; two builds must give the same root hash):

<!-- test: skip (builds the disk from a Debian snapshot download; task 4.9 built and checked it) -->
```bash
scripts/checker-disk.sh --twice
```

Then follow [`validator-kit/SEVSNP-PLAN.md`](../../validator-kit/SEVSNP-PLAN.md) steps 4 to 7 (upload the disk,
`tofu apply`, check the boot's attestation with `verify.py`). The disk runs its own Radicle node, not the one on your
machine: its key is made on the first boot on the instance's data volume, and every boot prints that node's `rad self
--nid` on the serial console (`aws ec2 get-console-output`), as `POF-RADICLE nid z6Mk…`. That node is the one your seat
makes a delegate, so it is the one you register. It is outbound only: it dials the seed you name in `radicle_seed`
(`<the seed's Node ID>@<its address>:8776`) and listens on no port, and the kit's security group opens none. Step 8
registers on Sepolia with that key:

<!-- test: skip (AWS) -->
```hcl
radicle_seed = "<the seed's Node ID>@<its address>:8776"
node_command = "register --bond 250 --proof tee --tee-type amd-sev-snp --level A --firmware <snp firmware> --rad-node <the POF-RADICLE nid>"
```

The console then shows `registered 0x… as a candidate (…, Radicle node did:key:z6Mk…)`, the same key as the
`POF-RADICLE nid` line. Keep the instance's data volume: the key can't be changed without leaving and registering
again. Then `node_command = "run --until-idle 600"` with `ORACLE_FIX_SOURCE = "radicle"`, `ORACLE_MERGE_VIA =
"radicle"`, `ORACLE_SEAT_NODES = "chain"` and `ORACLE_RADICLE_RID = "<RID>"` in `node_config`, and the kit's watcher on
(`watcher_enabled = true`). With `ORACLE_MERGE_VIA = "radicle"` the watcher also starts the instance once each time
`Heads` moves, so your node pushes the canonical `main` even when it wasn't drawn.

The bond comes from the deployment's genesis mint for the launch validators (the faucet's 20 coins every 2 hours would
take days). The launch plans 7 to 15 validators (design L16).
