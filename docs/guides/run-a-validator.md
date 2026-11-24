# Run a validator

A validator registers a bond, an attestation and its Radicle node's key; panels drawn at random then ask its node to
check fixes. The launch's validators run [the SEV-SNP kit](../../validator-kit/README.md)
in their own AWS account: one measured, read-only disk on an AMD SEV-SNP instance that's started only when its key is
drawn. Everything here is on the Sepolia testnet with the project's **test coin, POFTEST, which has no value**
([intended use](../../README.md#intended-use)); your AWS and model costs are real (the kit's
[COSTS.md](../../validator-kit/COSTS.md), and its spending caps).

You need: an AWS account, OpenTofu, Docker, and the tools in [Before you start](../take-part.md#before-you-start)
(git, Python 3.9 or later and Radicle 1.10.3 on your `PATH`, your own Sepolia JSON-RPC endpoint).

<!-- test: values -->
```bash
export POFCTL_RPC=https://<your Sepolia JSON-RPC endpoint: Infura, Alchemy or your own>
export RID=rad:zyZXC9NqVuse8nXdpv7iYRScDHsN           # proof-of-fix on Radicle
export RECORD=contracts/deployments/sepolia-v3.json   # the deployment record, on the branch sepolia-v3 (step 1)
export FAMILY=anthropic.claude                       # the family the deployment seats at launch (its plan's `families`)
```

v3 seats the family as `anthropic.claude`, so v3's validators register with that name. v3.1 renames it
`anthropic/claude` (the `provider/line` form every receipt uses); its guide will say so when it's deployed.

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

A new node doesn't know yet which seeds hold the repository, so a plain `rad clone` stops with "no candidate seeds
were found". Connect to the project's seed and clone from it:

<!-- test: skip (the devnet's node dials its peers from the config the radicle-config step wrote) -->
```bash
rad node connect z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem@77.113.144.207:8776   # the project's seed
```

<!-- test: radicle-peers -->
```bash
rad clone --seed z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem --timeout 2min "$RID" proof-of-fix && cd proof-of-fix
export RAD_NODE=$(rad self --did)            # did:key:z6Mk…: your registration names it
```

The canonical `main` moves only through the race (a fix reaches it when it's final and merged), so it's older than
the code the deployment runs and has no deployment record. Take the current code, the organiser's branch `sepolia-v3`
(you build the validator's disk from it in step 3.1):

<!-- test: skip (the devnet's repository has the program and the record on its main) -->
```bash
rad remote add z6Mkjgv8wBE6A963vtYC9VCBcxBPn6TBTKxjfMqgk6VFubdq --name asclepius --fetch   # the organiser's node
git checkout -b sepolia-v3 asclepius/sepolia-v3
ls "$RECORD"                                 # the deployment record (RaceV3 0xD622…9829, block 12196904)
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

## 3. The kit, in your AWS account, on Sepolia

Your validator is the kit's host: an AMD SEV-SNP instance (c6a, m6a or r6a; `us-east-2` is the region tested) booted
from the measured disk. The registry accepts only the disk images the deployment lists, so you build the disk from
the same image files as the deployment's and check that you get its image digest. The steps below are
[`validator-kit/SEVSNP-PLAN.md`](../../validator-kit/SEVSNP-PLAN.md)'s, with Sepolia's values.

### 3.1 Build the disk on `sepolia-v3`

Build it on the branch `sepolia-v3` you checked out in step 1. The record's `commit` (8946b9c…) isn't in the public
snapshots, but the branch's image files (`oracle/`, `pof/`, `bot/`, `pofctl/`, `scripts/judge_run.py`,
`scripts/checker-disk.sh` and `validator-kit/sevsnp/disk/`) are byte-identical to that commit's, so the build gives
the deployed image:

<!-- test: skip (builds the disk from a Debian snapshot download; task 4.9 built and checked it) -->
```bash
git switch sepolia-v3 && git status --short  # on the branch, nothing changed
scripts/checker-disk.sh --twice              # two builds without the cache must agree; no AWS
python3 -c 'import json; print(json.load(open("validator-kit/sevsnp/out/manifest.json"))["image_digest"])'
```

It must print `0xd95b0458a321963e59ab86a8575ef67dca7bdf5db55c86c3098764dc55f887d1`, the image in the deployment's
plan (`contracts/deployments/sepolia-v3.plan.json`, `images`). If it doesn't, stop and open an issue with your
`manifest.json`: a disk the deployment doesn't list can't register.

### 3.2 Upload it, apply the kit, check the attestation

Follow SEVSNP-PLAN.md steps 4 to 7: `coldsnap upload` the disk as an EBS snapshot, `tofu apply` the kit
(`validator-kit/sevsnp/terraform`) with that `snapshot_id`, boot once with an attest nonce and `power_off=false`, read
the console while the instance runs (`aws ec2 get-console-output --latest`; a stopped instance's console can't be
read), run `verify.py` on it, then stop the instance. The console's `POF-RADICLE nid z6Mk…` line is **your validator's
Radicle node**: you register that key, not your laptop's. Its key lives on the instance's data volume, so **keep the
data volume**: a new volume is a new key, and a registration can't change its node.

### 3.3 The signing key, gas and the bond

<!-- test: skip (AWS) -->
```bash
scripts/genesis-validator.sh new-key         # a fresh key straight into the kit's secret; prints only its address
```

Send that address a little Sepolia ETH from any Sepolia faucet (gas). The bond is 250 POFTEST, more than the faucet's
20 coins every 2 hours gives in a day: **ask for it** by opening a Radicle issue on proof-of-fix titled
`Validator bond: 0x<your address>` (`rad issue open --title "Validator bond: 0x…" --description "<who runs it, which
model>"`, then `rad sync --announce`). The organiser sends the bond from the deployment's genesis mint and answers on
the issue.

The node's RPC endpoint should be **your own key or provider**, not one shared with other validators: Infura's free
plan answers some calls with HTTP 429 at times (the node retries them), and several validators on one key soon hit its
daily quota.

### 3.4 Your model

Your node calls the model directly from inside the TEE, with your own credentials, on Bedrock or on the Anthropic
API.

**Claude on Bedrock** (as step 3.5's tfvars show): `bedrock_model_arns` in your tfvars (the inference profile and
its regional models), with the model's terms accepted in the Bedrock console first (a model whose agreement isn't
accepted answers 403). On a new AWS account Bedrock can answer that the newest Claude models (Opus 5.5, for one) are
"not available for this account", even after the agreement is accepted; then use the Anthropic API.

**Claude on the Anthropic API:** put the API key in a Secrets Manager secret of its own, in the kit's region, as a
plain string, and give the node its ARN (the kit reads only the secrets you list):

<!-- test: skip (AWS) -->
```hcl
extra_secret_arns = ["<the key's secret ARN>"]      # with your RPC key's, if it has one
node_config = {
  # … step 3.5's settings, with these in place of the Bedrock ones:
  ORACLE_JUDGE             = "direct:anthropic:<model id, e.g. claude-opus-5-5>"
  ORACLE_MODEL_ALLOW       = "<the same id>"
  MODEL_API_KEY_SECRET_ARN = "<the key's secret ARN>"
  ORACLE_PRICE_PER_MTOK    = "<input,cached,output>"   # USD per million tokens, set above the model's list price
}
```

`bedrock_model_arns` can then stay empty. `ORACLE_PRICE_PER_MTOK` is what the node counts each call at, so a price
above the list price makes the caps below stop early rather than late. An Anthropic Console organisation's key works
only once the organisation's billing is set up (prepaid credits); give the key's workspace a spend limit too, as a
second cap behind the node's.

`ORACLE_SPEND_DAILY_USD` and `ORACLE_SPEND_MONTHLY_USD` cap what your node spends; the kit's budget stops the
instance at its limit.

### 3.5 Register

In your tfvars (secrets stay out of it: the chain's URL may carry a key, so prefer `RPC_API_KEY_SECRET_ARN`):

<!-- test: skip (AWS) -->
```hcl
radicle_seed = "z6MkveoyyXuC4S2BKidHiE1qz1RbcKLDfe4hxLTHAhaGdNem@77.113.144.207:8776"   # the project's seed
node_config = {
  ORACLE_VERSION     = "3"
  ORACLE_RPC         = "https://<your Sepolia endpoint>"
  ORACLE_RACE        = "0xD622adB4CbC82fF51d5D2ddbD56681b5f2d89829"
  ORACLE_FROM_BLOCK  = "12196904"                     # the record's block: no event scan starts before it
  ORACLE_FAMILY      = "anthropic.claude"
  ORACLE_LIST_PRICES = "{}"                           # post only families already priced: v3 can't seat a new one
  ORACLE_JUDGE       = "direct:bedrock:<your model's inference profile id>"   # or the Anthropic API's (3.4)
  ORACLE_MODEL_ALLOW = "<the same id>"
  ORACLE_IMAGE       = "0xd95b0458a321963e59ab86a8575ef67dca7bdf5db55c86c3098764dc55f887d1"
  ORACLE_HOST_ID     = "aws:<your region>"
  ORACLE_FIX_SOURCE  = "radicle"
  ORACLE_MERGE_VIA   = "radicle"
  ORACLE_SEAT_NODES  = "chain"
  ORACLE_RADICLE_RID = "rad:zyZXC9NqVuse8nXdpv7iYRScDHsN"
  ORACLE_REPO        = "pof/proof-of-fix"
  ORACLE_SPEND_DAILY_USD   = "0.50"
  ORACLE_SPEND_MONTHLY_USD = "5"
}
node_command = "register --bond 250 --proof tee --tee-type amd-sev-snp --level A --firmware <the console's snp-summary firmware> --rad-node <your POF-RADICLE nid>"
```

Apply with `power_off=false` and read the console: `registered 0x… as a candidate (…, Radicle node did:key:z6Mk…)`.
A provider that limits `eth_getLogs` ranges (Alchemy's free plan: 10 blocks) needs `ORACLE_LOG_RANGE` set to its
limit; Infura's free plan answers some calls with HTTP 429 at times, which the node retries (and a key shared by
several validators runs out of its daily quota: step 3.3).

### 3.6 Run

<!-- test: skip (AWS) -->
```hcl
node_command      = "run --until-idle 600"
watcher_enabled   = true
validator_address = "0x<your signing key's address>"
```

Apply with `power_off=true` (the default). The watcher checks the chain every minute and starts the instance only
when your key is drawn, or when `Heads` moves (your node then pushes the canonical `main`); the node judges, reports,
and powers off after 10 idle minutes. On v3.1's kit the watcher also draws: a check nobody drew within its grace
(about 5 minutes) plus your stagger (up to 10 minutes) starts your instance once, and its keeper draws the panel
(`WAKE_ON_DRAW`, on by default; [the runbook](../../validator-kit/runbook.md#run-a-keeper)).

A new validator is drawn as a shadow first: its verdicts aren't counted until about 20 of them qualify it. Then it
sits on counted panels, and its node becomes a delegate of the repository when the seats on-chain change.

The launch plans 7 to 15 validators (design L16). Until 7 are active, panels have one judge, a passed fix waits 7 days
for challenges, and its verdict is held until enough validators are active to judge a challenge: more validators is
what makes fixes merge sooner.

How long a check takes. On v3 a verdict comes about 2–3 hours after the draw: the 2-hour seal window, then the reveal
(up to an hour) and the count. On v3.1 the reveal opens as soon as every seat has sealed, so it takes minutes. A lone
verdict is then held until 6–7 validators with room can judge a challenge:

- **Before its audits are drawn** it needs six eligible validators outside its panel (seven in all, with the judge);
  **after**, three outside the judge and its auditors (six in all, with two auditors). That is the challenge panel of
  3, plus one for each audit still to be drawn, since an auditor sits out of the challenge.
- **Each one counts only if** it is bonded for the bounty, not a party to it, and has room now (fewer than 10 k = 1
  verdicts not yet final).
- **Below that, every lone verdict stays held.** At exactly the threshold, one validator pausing (capacity 0) or
  filling up holds them all; one more validator than the threshold keeps them moving.
