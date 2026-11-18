# Run a proof-of-fix validator in your own AWS account (proof-of-fix#104)

You run the AI check on your infrastructure, with your own model access, and the contract pays you a check fee for
every verdict it counts. This runbook sets that up, joins you as a seat, and tears it down.

**Status:** the contracts (v2: seats, the 3-of-7 draw, the metered fees) and the node's v2 mode are in place, and
`scripts/demo-e2e.sh` runs this whole flow on a devnet with real node processes, and `scripts/first-run-e2e.sh` the first
real run on a throwaway copy of the AWS devnet ("The first real run" below). `scripts/integration.sh --target aws` runs
the integration suite on the AWS devnet itself, with the fake judge ("The integration suite on the AWS devnet").

## 1. Prerequisites

- An AWS account you control (not a corporate one you can't put a validator in), with OpenTofu ≥ 1.6 or Terraform ≥ 1.6,
  and the AWS CLI signed in as an administrator of that account.
- From the demo's organiser:
  - the chain's **RPC URL** (HTTPS) and **your API key** for it: `keys.sh show` prints it as
    `https://<handle>:<key>@devnet.example.com`; the secret below is the `<handle>:<key>` part;
  - the **deployment record** (`devnet-v2.json`): chain ID and RaceV2's address;
  - the **demo repository** (`owner/name` on GitHub, or on a Forgejo: see "A Forgejo target") whose pull requests claim
    the submissions, and the **seat** you take (a vacant one, or one rotated to your key: all 7 are in use on the AWS devnet today);
  - the **node image digest** (`…/pof-oracle-node@sha256:…`) every validator runs. An image in a private ECR registry
    works: the node logs in before pulling, and its role may read that one repository, in that registry's region.
- **Model access**, from any provider (ADR 0003: nothing one party runs is required; Bedrock is just the AWS adapter):
  - Amazon Bedrock in your account, with access enabled for your model family (Bedrock console → Model access); or
  - an API key for Anthropic, OpenAI, Google's Gemini, or any OpenAI-compatible server (a self-hosted vLLM, #125).
  Your node calls it **directly**, over TLS that ends in your node, never through a gateway (see "The model").

## 2. Your keys

Store the chain's API key, and the model API key if you use one, in **your** Secrets Manager:
```
aws secretsmanager create-secret --name pof-validator/rpc-api-key --secret-string "$RPC_HANDLE:$RPC_KEY"
```
With a provider's API (not Bedrock), its key the same way, without it touching your shell history:
```
read -rs MODEL_KEY && aws secretsmanager create-secret --name pof-validator/model-api-key --secret-string "$MODEL_KEY"; unset MODEL_KEY
```
If the demo repository is private, also a **read-only repository token**: a GitHub fine-grained token for that one
repository with *Contents: read*, *Issues: read* and *Pull requests: read*, nothing else (on a Forgejo: see "A Forgejo target"). The node reads the pull requests and the bounty's issue with it and
fetches each claimed commit itself (exactly that commit, checked against the sealed commitment before any test runs;
proof-of-fix#115). It's sent to git as a header, never in a URL or on a command line, and never logged:
```
read -rs REPO_TOKEN && aws secretsmanager create-secret --name pof-validator/repo-token --secret-string "$REPO_TOKEN"; unset REPO_TOKEN
```

Your **validator signing key** is created by you, never by Terraform. After applying (step 3), generate it and put it in
the secret the module created, without it touching your shell history or a file:
```
python3 - <<'PY' > /dev/null
import secrets, subprocess
key = secrets.token_hex(32)                                   # a fresh secp256k1 private key
subprocess.run(["aws", "secretsmanager", "put-secret-value", "--secret-id", "pof-validator/signing-key",
                "--secret-string", key], check=True)
PY
```
Get its public address with the node image's `info` command (`ORACLE_KEYS=env`), or any Ethereum tool, and set
`validator_address` (step 3): the watcher starts your node only for the submissions this key is drawn for.

## 3. Apply

```
cd validator-kit/terraform
cat > validator.auto.tfvars <<'EOF'
rpc_url                = "https://<the demo chain's endpoint>"
rpc_api_key_secret_arn = "arn:aws:secretsmanager:...:secret:pof-validator/rpc-api-key-..."
chain_id               = 7193
race_address           = "0x<RaceV2 from devnet-v2.json>"
node_image             = "<registry>/pof-oracle-node@sha256:<digest>"
model_provider         = "bedrock"
bedrock_model_arns     = ["arn:aws:bedrock:us-east-1::foundation-model/<your family's model ID>"]
model_id               = "<your family's model ID>"   # empty: the fake judge (devnet runs only, not counted)
budget_limit_usd       = 20
budget_emails          = ["you@example.com"]
validator_address      = "0x<your validator's address>"
repository             = "<owner>/<the demo repository>"
exchange_url           = "https://<the demo chain's endpoint>/exchange"   # where the drawn judges meet; it gets the RPC's key
# rpc_api_key_header   = "Basic"        # the default: the secret is "<handle>:<key>" (the demo chain's)
# repo_token_secret_arn = "arn:aws:secretsmanager:...:secret:pof-validator/repo-token-..."   # a private repository
# merge_poll_minutes   = 30             # a won bounty you judged starts the node this often until it merges
# pending_poll_minutes = 30             # a draw still undecided starts the node again this often (a run may have ended early)
# pending_max_starts   = 4              # ...this many times, then the watcher gives up on it
# --- a repository on a Forgejo instead of GitHub (see "A Forgejo target") ---
# forge                = "forgejo"
# forge_url            = "https://git.example.com"
# repo_token_user      = "pof-validator-bot"   # the user the repository token belongs to
# --- or, a provider's API instead of Bedrock ---
# model_provider           = "api"
# model_api_provider       = "anthropic"  # or "openai" (any OpenAI-compatible server with model_api_url), "gemini"
# model_id                 = "<the provider's model name>"
# model_api_key_secret_arn = "arn:aws:secretsmanager:...:secret:pof-validator/model-api-key-..."
# --- spending guards, per run of the node (the defaults) ---
# max_output_tokens = 4000     # per verdict
# max_model_calls   = 20       # retries included; then the node refuses further calls
# max_run_tokens    = 500000   # in plus out; a call whose worst case doesn't fit isn't made
EOF
tofu init && tofu plan -out=validator.tfplan    # check it: a VPC, an instance, a Lambda, no inbound rules
tofu apply validator.tfplan
```
`*.tfvars` is git-ignored: your account's ARNs stay on your machine.

The instance boots once to install Docker and its service, then powers itself off. `apply` returns before that, so check
it has stopped, a few minutes later:
```
aws ec2 describe-instances --instance-ids "$(tofu output -raw node_instance_id)" \
    --query 'Reservations[0].Instances[0].State.Name' --output text
```
From then on the **watcher** checks the chain every minute and starts it only when there's work for your seat: a sealed submission `Verdicts.drawn` names
your key for (3 of the 7 seats are drawn for each), or a bounty you judged the winner of, waiting for its merge.

## 4. Join as a seat

v2's join flow puts your key in a vacant seat. You sign; the other seats co-sign; the contract checks both, and the
key takes the seat 7 days later (`KEY_ROTATION_DELAY`). Seat bonds come with task 5.8; on the demo there is none.

1. **Sign the join** with your key, from a checkout of the proof-of-fix repository (pofctl needs no install):
   ```
   export POFCTL_RPC="https://devnet.example.com" POFCTL_RPC_TOKEN="$RPC_HANDLE:$RPC_KEY" POFCTL_RPC_AUTH=Basic
   export POFCTL_KEY_ENGINEER=$(aws secretsmanager get-secret-value --secret-id pof-validator/signing-key \
       --query SecretString --output text)
   scripts/pofctl --record devnet-v2.json --as engineer validator join --seat <n>
   unset POFCTL_KEY_ENGINEER
   ```
   It reads the join's digest from Verdicts (`rotateDigest`, checked against pofctl's own encoding), signs it, and
   prints a request: seat, key, nonce, signature. Nothing secret is in it.
2. **Send the request to the demo's organiser**, who publishes it with the seats' co-signatures
   (`pofctl validator publish …`, or `scripts/devnet.sh join-v2 <n> --key … --sig … --nonce …`).
3. **Seven days later**, anyone activates it: `scripts/pofctl validator activate --seat <n>`. Check it:
   `scripts/pofctl --as engineer validator status` (with your key exported as above) says `seat <n>, active`.

## 5. Verify

```
aws logs tail /aws/lambda/pof-validator-watcher --follow     # every minute: idle, started, or disabled
aws ec2 describe-instances --instance-ids <node_instance_id> --query 'Reservations[].Instances[].State.Name'
aws logs tail /pof-validator/node --follow                    # a run: drawn or not, the check, the usage report,
                                                              # the verdict signed, the result or merge relayed
```
To force a rescan of the last 100 blocks: `aws ssm put-parameter --name /pof-validator/last-block --value none --overwrite`.
To get a shell on a running node: `aws ssm start-session --target <node_instance_id>` (there's no SSH and no open port).

## 6. Watch and withdraw your fees

Each check the meter counts pays you its measured usage (the judge's tokens, the sandbox's vCPU-seconds and
GB-seconds, the receipt's storage) at the constitution's price table, plus the **$0.05 service fee**, in the fee coin.
Your node reports that usage, signed, before the result; a judge that doesn't report isn't paid. The relayer's gas is
repaid too. It accrues as credit in RaceV2; you pull it:
```
scripts/pofctl --as engineer validator status      # drawn, verdicts, usage reports, fees earned (credit + withdrawn)
scripts/pofctl --as engineer validator withdraw     # or, with the node image: python3 -m oracle withdraw-fees
```

## 7. Stop or tear down

- **Pause:** set `enabled = false` and apply. The watcher stops starting the node; nothing else runs. This is your kill
  switch; on a real chain, draws you miss while paused are slashed unless you first leave the set.
- **Remove:** `tofu destroy`. The signing-key secret has a 7-day recovery window. Delete it immediately only if you're
  sure the key is no longer a seat: `aws secretsmanager delete-secret --secret-id pof-validator/signing-key --force-delete-without-recovery`.

## The AWS devnet: deploying v2 and taking the owner's seat (#150, #112)

For the deployment's owner. `scripts/devnet.sh`'s **remote mode** does this from a checkout of proof-of-fix, with Docker,
`python3`, an OpenBao session for the role keys (`bao login -no-print -method=oidc role=admin`) and the owner's API key.
It refuses any chain but 7193, plain HTTP, a credential in the URL and anvil's public keys. `scripts/devnet-remote-e2e.sh`
runs all of this on a throwaway copy of the devnet.

**The credential** is `<handle>:<key>`. Read it into the variable, without it touching your shell history or a command
line. `read -rs` waits for you to paste it; `keys.sh show` prints it inside the URL, between `https://` and `@`:
```
read -rs DEVNET_RPC_AUTH && export DEVNET_RPC_AUTH
export DEVNET_RPC_URL=https://devnet.example.com
scripts/contracts.sh setup     # once: the pinned image and solc
scripts/devnet.sh check        # the credential works and the chain is 7193 (reads only)
```
`DEVNET_RPC_AUTH_FILE=<path>` names a file instead (it stays on your disk, so `chmod 600` it). Each command runs forge and
cast in the pinned image, in a container that lasts for that command, and the devnet.sh process removes it at the end.

**Deploy:** 7 seats, the 5 oracle roles and **2 vacant**, with a **quorum of 5** (above half of 7, and every role has to
co-sign a join). Seat 5 takes a devnet role and seat 6 the owner's validator. A seat's model family is fixed for good at
genesis and sets its token prices, so name them now, one per seat, all different; put your node's family last (replace
`anthropic` if yours is another). The head is the commit `pof-sandbox`'s main is at; the checkout must have it.
```
export DEVNET_V2_VACANT=2 DEVNET_V2_QUORUM=5
export DEVNET_V2_REPO=example-org/pof-sandbox DEVNET_V2_HEAD=a52a922d5626526fbb43f469ff3efd973ac24776
export DEVNET_V2_FAMILIES=deepseek,qwen,mistral,llama,google,openai,anthropic
scripts/devnet.sh deploy-v2    # funds the roles (anvil_setBalance), deploys, and writes the record
scripts/devnet.sh status       # chain, block, hardfork, the record, and every contract's code hash against the chain
scripts/devnet.sh seats-v2     # seats 7, quorum 5; seats 5 and 6 vacant
```
The record is `contracts/deployments/devnet-aws-v2.json` (addresses and hashes, nothing secret), apart from a local
devnet's `devnet-v2.json`. Commit it, like `devnet.json`. While it exists, `deploy-v2` refuses to deploy again; a failed
deployment keeps no record.

**The seats.** The validator's key comes from the kit's secret (section 2). Fund it, sign its join with pofctl, and
publish that with the roles' co-signatures:
```
scripts/devnet.sh join-v2 5 joiner-0

export POFCTL_RPC="$DEVNET_RPC_URL" POFCTL_RPC_TOKEN="$DEVNET_RPC_AUTH" POFCTL_RPC_AUTH=Basic
export POFCTL_KEY_ENGINEER=$(aws secretsmanager get-secret-value --secret-id pof-validator/signing-key \
    --query SecretString --output text)
RECORD=contracts/deployments/devnet-aws-v2.json
scripts/pofctl --record $RECORD --as engineer validator join --seat 6     # prints the key, nonce and signature
scripts/devnet.sh fund-address <key>
scripts/devnet.sh join-v2 6 --key <key> --sig <signature> --nonce <nonce>
```
**A week later, or now:** joining has a 7-day delay, and `warp` moves the clock on this shared chain for everyone on it.
```
scripts/devnet.sh warp 7
scripts/devnet.sh activate-v2 5
scripts/devnet.sh activate-v2 6        # lists the seats: 0 to 6 active, 7 active keys
scripts/pofctl --record $RECORD --as engineer validator status            # seat 6, active
unset POFCTL_KEY_ENGINEER POFCTL_RPC_TOKEN DEVNET_RPC_AUTH
```
Then give the kit (step 3) the record's `race` as `race_address`, and `example-org/pof-sandbox` as `repository`.

`fees-v2` also works in this mode, but it leaves a demo issue and bounty on the shared chain, and it signs only with the
oracle roles' keys, so it fails once a joined seat is drawn. Keep it to throwaway devnets.

**What's visible where:** the credential and the keys are never on a command line or in `docker inspect`, the output,
the record or forge's files. The credential travels on stdin to a file in the container's memory (`/dev/shm`), and the
keys on stdin. While forge or cast runs, they're in that process's environment, which your own user and root can read
(`/proc/<pid>/environ`), and in `devnet.sh`'s memory. The exports above stay in your shell until the `unset`.

## The first real run (#150, #112)

> **This has run** (2026-11-04): see #150. When pasting a token, run its `read -rs` line alone: a pasted block feeds the next
> line into the hidden prompt.

For the deployment's owner: one real bounty on the AWS devnet, from an issue on `pof-sandbox` to the fees withdrawn, with
the owner's validator (Claude through Bedrock) as one of the 7 seats and the 6 role seats running on the owner's PC.
`scripts/first-run-e2e.sh` runs all of this on a throwaway copy, with a real Forgejo, the kit's watcher code and a 90-second
boot; only AWS, Docker around the owner's node and the real model are left for this run.

**What runs where**

| What | Where | Started by |
|---|---|---|
| the chain and the exchange relay | the devnet host, behind Caddy and the same API keys | platform's stack |
| 6 role seats' nodes (`oracle-0..4`, `joiner-0`) | your PC: a process each, tests in Docker's sandbox | `scripts/devnet-seats.sh up` |
| the owner's validator, seat 6 | the sandbox account: stopped, started by the watcher | the kit, on its draws |
| the bounty's roles: reporter, funder, solvers, the registration check, settling | your PC | `scripts/first-bounty.sh` |

No long-running bot is needed: `bot/loop.py` is v1's local loop, and what the bot does in v2 (registering, linking,
settling) `pofctl` does, in `first-bounty.sh`. **`pof-validator-bot` stays read-only**: the seats and the validator only read.
Pushing fix branches, opening the issue and pull requests, commenting and merging need **a user with Write on `pof-sandbox`
and a token with `write:repository` and `write:issue`** (`FIRST_BOUNTY_TOKEN`, `FIRST_BOUNTY_USER`). Yours will do, or a
dedicated user; revoke the token afterwards. If `main` is protected, that user must be allowed to merge without a review.

**The order**

1. **The relay's repository.** Merge platform's change, then dispatch `tofu-apply` with the host up. The stack's in the
   pipeline since platform-211; a dispatch applies every stack. It adds the ECR repository and its lifecycle policy, and
   re-syncs the host.
2. **The image.** From a clean checkout of this repository, with an administrator's profile for that account:
   ```
   AWS_PROFILE=<profile> scripts/exchange-image.sh "$(cd <platform>/environments/prod/us-east-1/pof-devnet && tofu output -raw exchange_repository_url)"
   ```
   It builds for linux/arm64, pushes, and prints `exchange_image_digest`.
3. **The relay.** Set that digest as the variable's default in platform's stack, merge, and dispatch `tofu-apply` (the
   host's role gets the pull permission; the sync logs in, pulls and starts the relay). Check it, with your key in
   `DEVNET_RPC_AUTH`:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' https://devnet.example.com/exchange/healthz     # 401
   curl -s -K <(printf 'user = "%s"\n' "$DEVNET_RPC_AUTH") https://devnet.example.com/exchange/healthz   # the race
   ```
4. **The validator.** Add `exchange_url = "https://devnet.example.com/exchange"` to the kit's tfvars, plan, apply.
   Changing the user data **replaces the node instance**: it boots once, installs Docker and powers itself off, and its first
   run pulls the images again. Wait until it shows `stopped` (section 3): a draw during the install is missed.
5. **One model call by hand**, if you haven't made one yet: "Check it once, by hand" under "The model".
6. **The seats**, in a terminal you leave open (Docker Desktop running, and a checkout of this repository):
   ```
   bao login -no-print -method=oidc role=admin
   read -rs DEVNET_RPC_AUTH && export DEVNET_RPC_AUTH        # <handle>:<key>
   read -rs DEVNET_REPO_TOKEN && export DEVNET_REPO_TOKEN    # pof-validator-bot's read-only token
   export DEVNET_RPC_URL=https://devnet.example.com
   scripts/devnet-seats.sh up
   ```
   It checks each role's key is an active seat's and the relay serves this race, then stays in the foreground. Ctrl-C stops
   the nodes. `scripts/devnet-seats.sh status` shows them from another terminal; logs are in `.devnet-seats/<role>/node.log`.
7. **The bounty**, in a second terminal, between 09:00 and 23:00 Bogota:
   ```
   bao login -no-print -method=oidc role=admin
   read -rs DEVNET_RPC_AUTH && export DEVNET_RPC_AUTH
   read -rs FIRST_BOUNTY_TOKEN && export FIRST_BOUNTY_TOKEN  # scopes write:repository, write:issue
   export FIRST_BOUNTY_USER=<that token's user> DEVNET_RPC_URL=https://devnet.example.com
   scripts/first-bounty.sh --preflight-only                  # reads only: seats, gas, the relay, main = the head on-chain
   scripts/first-bounty.sh
   ```
   Set `POFCTL_KEY_ENGINEER` too (as in "The AWS devnet" above) and it also withdraws seat 6's fees; otherwise it prints the
   command. It ends with the books: every submission, its outcome and time, who was drawn, and the tokens each reported.
8. **Check the real call** in the sandbox account: `aws logs tail /pof-validator/node --since 2h` shows the model that answered
   and the receipt. `scripts/devnet-seats.sh down` and `clean` when you're done, then revoke the write token.

**The issue.** `bot/sample/stats.py`'s `median()` is wrong for an even count, in the tree `pof-sandbox`'s main already has, so
main stays at the head on-chain and needs no commit first. Each fix is one commit on main that adds the acceptance test at
the root and replaces `stats.py` with `bot/fixes/bad_stats.py` (the lower middle value: the tests fail) or `good_stats.py`
(they pass). The test has to be at the root: the sandbox runs `python -m unittest` there, and in this tree that finds **no
tests by itself** (exit 5, a failure). Merged, the fix's commit is main's head (fast-forward or rebase, never a merge commit)
and the head on-chain moves to it, so a later bounty's verdict isn't stale. Pull requests also start `pof / check` on the
`test` runner (`.forgejo/workflows/check.yml`).

**The repository's own tests (#166).** A repository names them in `.pof/check.json`, an object with one key, `commands`:
a list of argument lists, run in turn in the sandbox before the acceptance test, which always runs last. The node reads
the file at the pull request's **base**, never from the fix, so a fix can't weaken its own check, and the head on-chain
only moves on a verdict checked on that head. For `pof-sandbox`:

```json
{"commands": [["python", "-m", "unittest", "discover", "-s", "bot/sample", "-t", "bot/sample", "-q"]]}
```

Without the file a check runs only the root, as above. With an invalid file every check fails closed with no model
call. `pof-sandbox`'s main must stay at the head on-chain, so the file arrives as part of a bounty's fix and takes effect
from the next bounty.

**Which judges are real.** One: seat 6, the owner's. The 6 role seats run the **fake judge**: free, deterministic, following
the sandbox's test result. The contracts can't tell the difference: the verdict and the usage report are the same bytes, a
seat's model family only sets its price, and the kit's words "not counted" are a convention no code enforces. A draw of 3 of
7 always has at least 2 role seats, and 2 must agree, so **the fake judges decide every check and the owner's model can
never change an outcome**. If it disagrees it doesn't sign, and the meter still pays its report.

**The run proves:** the relay works behind the API keys across machines; the real nodes draw, fetch from a private Forgejo with
a read-only token, test in the sandbox, report, seal, reveal, sign and relay against the deployed contracts; the watcher starts
a stopped validator in time to join a round; a real Bedrock call happens within the guards, with the provider's token counts
on-chain and the seat paid for them; the merge moves the head; the bounty settles; fees reach wallets. **It doesn't prove:**
that a model judges well. The node shows its judge the issue, the commit, the diff it computes itself and the test result
(`oracle/evidence.py`, #166), but one run on one sample bug says little about quality; that's #160. It also doesn't prove
independence (six seats on one PC), anything with real money or a public chain, or attestation.

**Getting the owner's seat drawn.** The draw can't be forced or predicted: the seed mixes in the block's RANDAO value, unknown
when the solver seals (`RaceV2Base._submit`). Each submission draws seat 6 with chance 3/7, so `first-bounty.sh` seals failing
fixes one at a time until it has been drawn (`--max-fails`, default 8: 99 %); each costs only its metered fee in the test coin.
It doesn't then wait for a draw on the passing fix (3/7 on its own). If the books show no owner's report, the run says so and
fails: run it again.

**A real model on a correct fix.** Then, `scripts/first-bounty.sh --until-owner-on-pass 8` seals a correct fix for another real
bug on main (`mean([])`), on a new bounty each try, until seat 6 is drawn on one (99 % within 8), and merges it. Tries that
miss close their pull request unmerged. There's no warp, so the shared clock stays put. It's one target: once merged, the
bug is gone.

**Timing.** The seal and reveal windows are not on-chain yet (`TODO(5.5)` in `Verdicts.sol`): they are the relay's
configuration and the nodes' `ORACLE_ROUND_TIMEOUT`, on wall-clock time, so a warp doesn't move them.

| From the submission's commit | Takes |
|---|---|
| the watcher's next poll | up to 60 s |
| the instance's start and boot, the registry login, a pull (the first run only: both images) | about 1-3 min |
| the fix's fetch, its tests, the model's answer (up to 120 s, then 2 retries), the usage report | about 20-60 s |
| **so the owner's seal** | **about 2-5 min; 8 at the worst** |

With the code's defaults (60 s) the role nodes would reveal and decide before it arrives, so every owner's draw would lose it.
Hence **900 s, both in platform's `exchange_seal_window_seconds` and the seats' `DEVNET_SEATS_ROUND_TIMEOUT`**; keep them equal.
The kit's own timeout can stay at 60 s: its node seals last and finds the others waiting. A round whose judges all sealed moves
on at once, so the long window only slows a round whose judge never comes: 15 minutes, and then the two others decide without it.
After the merge, the role nodes sign and wait for the third judge up to the same 900 s; the watcher starts the owner's node when
the bounty is won and then every `merge_poll_minutes`, and two signatures are enough once that time has passed.

**The night stop.** The host stops 01:00-09:00 Bogota. `first-bounty.sh` won't start after 23:00 (`FIRST_BOUNTY_ANYTIME=1`
overrides it). The seats' nodes exit when the chain goes away and `devnet-seats.sh` starts them again every 30 s until it's
back. A node keeps no state across that: a round the stop interrupts loses that node, and the relay's windows run on through
the night. Run it by day, and if one is cut off, run it again: a new bounty costs nothing but test coins.

**Cost.** Well under $0.10: a few short runs of the instance, about $0.005 each (`COSTS.md`); under a cent per real verdict, as
this prompt is short (`COSTS.md`'s $0.02-0.12 is for a real diff); and pennies a month for the image in ECR. The rest (the host,
the watcher) runs anyway. Docker, the nodes and every coin on the chain are free.

## The integration suite on the AWS devnet (#152)

For the deployment's owner, after "The first real run": the integration suite's scenarios against the live AWS devnet,
`pof-sandbox` and the live nodes, with the **fake judge** (free and deterministic), to test the architecture end to end
before any AI check. `scripts/integration.sh --target aws` plays the roles; it starts no node, and it never resets or
redeploys anything. The default target stays the throwaway local devnet.

**What runs where:** as in "The first real run": the chain and the relay on the devnet host, the 6 role seats' nodes on your
PC (`scripts/devnet-seats.sh up`, on the fake judge by default), seat 6 in the sandbox account. The suite replaces
`first-bounty.sh` in the second terminal.

**What it runs, and what it doesn't**

| Scenario | On AWS | |
|---|---|---|
| 2. a failing fix | yes | Fail, the deposit charged for the checks and the rest returned, the bounty stays Open |
| 3. a race | yes | two passing fixes: the earliest wins, the other is decided and refunded; a fix sealed after the win pays the evaluation fee (TooLate); the winner is merged |
| 1. the happy path | yes | quoted, sealed, judged by the drawn live nodes, merged, the merge signed, settled (Paid, by **warping the shared clock**, `--no-warp` stops at Merged), the funder's leftover claimed, the issue closed by the bot's settle with a comment linking the payout transaction (#151) |
| 5. a challenge | yes | merged, then upheld by the quorum (the role keys): the award closes with nothing earned, the bounty reopens |
| 4. a silent validator | **local-only** | it needs a drawn node not to run; the suite never stops a live node |
| 6. joining | **local-only** | it needs a vacant seat; all 7 are taken (seat 6 joined this way), so the preflight checks all 7 are active |
| 7. infrastructure faults | **local-only** | a relay taken away (7a) or a node killed (7b) would disturb the shared nodes; 7c happens on AWS whenever seat 6 is drawn |

The run prints the skipped ones and why. Then: every seat's fees withdrawn (seat 6's too with its key: #150's open item),
and the books, as deltas at each result's block: each deposit = what the meter charged + what returned; the seats were
credited what the meter charged; each withdrawal paid the whole credit. Last, the leaderboard (#151): `pofctl leaderboard
--bounties <the run's>`, computed from the events, must match the same bounties read from the contracts' views exactly.
Every balance it asserts is a **delta read before and after**, never an absolute value, since the chain keeps earlier
runs' balances; the leaderboard, narrowed to the run's own new bounties, is that run's delta too.

**What it leaves on the shared devnet:** each scenario opens its own issue (`[integration <tag>] ...`) and its fixes'
branches (`integration-<tag>-...`); the run closes every issue and pull request and deletes every branch at the end, pass
or fail (`--cleanup` does it again for an interrupted run). Its bounties stay on the chain, as on-chain records do.
Scenarios 3, 1 and 5 merge a fix, so `pof-sandbox`'s main and the head on-chain move with them; every fix writes the same
two root files (`integration_probe.py` and `test_integration_probe.py`), so main keeps no file per run. Scenario 1 warps
the clock about 35 days, for everyone on the chain.

**The order**

1. **No model call:** set the kit's `model_id = ""` (the fake judge) and apply, then wait until the node shows `stopped`; or
   `enabled = false` (then a round that draws seat 6 waits the 15-minute seal window and the two others decide: slower,
   and seat 6 isn't paid for it). Put it back afterwards.
2. **The seats**, in a terminal you leave open: "The first real run", step 6 (`scripts/devnet-seats.sh up`). Leave
   `DEVNET_SEATS_JUDGE` unset: the fake judge.
3. **The suite**, in a second terminal, between 09:00 and 23:00 Bogota (`--anytime` overrides):
   ```
   bao login -no-print -method=oidc role=admin
   read -rs DEVNET_RPC_AUTH && export DEVNET_RPC_AUTH            # <handle>:<key>
   read -rs FIRST_BOUNTY_TOKEN && export FIRST_BOUNTY_TOKEN      # write:repository, write:issue on pof-sandbox
   export FIRST_BOUNTY_USER=<that token's user> DEVNET_RPC_URL=https://devnet.example.com
   read -rs DEVNET_REPO_TOKEN && export DEVNET_REPO_TOKEN        # optional: the seats' token, checked read-only
   export POFCTL_KEY_ENGINEER=$(aws secretsmanager get-secret-value --secret-id pof-validator/signing-key \
       --query SecretString --output text)                      # optional: seat 6's fees withdrawn too (#150)
   scripts/integration.sh --target aws --preflight               # reads only: what's missing
   scripts/integration.sh --target aws                           # about 20-40 minutes
   unset DEVNET_RPC_AUTH FIRST_BOUNTY_TOKEN DEVNET_REPO_TOKEN POFCTL_KEY_ENGINEER
   ```
   `_FILE` variants name a file instead (`DEVNET_RPC_AUTH_FILE`, `FIRST_BOUNTY_TOKEN_FILE`, `DEVNET_REPO_TOKEN_FILE`,
   `POFCTL_KEY_ENGINEER_FILE`). `--only 2` runs some scenarios; `--withdraw-only` only withdraws the seats' fees, seat
   6's included with its key, which closes #150's last item on its own.
4. **Read the result:** each scenario's steps, `FAILED:` lines, the skipped scenarios, the books and `result:`. Then
   `scripts/devnet-seats.sh down`, put the kit's judge back, and revoke the write token.

**The preflight** checks, reading only: the RPC answers chain 7193 with your credential; the record's contracts are on
the chain with their code hashes; the relay serves this race; the role keys are in OpenBao; 7 seats, all active, seats
0-5 the role seats and seat 6 not a role (and `POFCTL_KEY_ENGINEER` is seat 6's key, if set); the role seats' nodes are up
on this machine (`--seats-elsewhere` if they run on another); every sender has 0.1 ETH for gas (`scripts/devnet.sh fund`
in remote mode tops the roles up); the test coins (the run mints what's short); the write token can push and merge, and
main is at the head on-chain; the seats' token can't write; leftovers of an earlier run; the time of day. It prints
`missing:` for each gap, and the run itself refuses to start while one is.

**Secrets:** the credential, the tokens and the keys are read once, at the start, into the suite's memory: the role keys
from OpenBao, the rest from the environment or their files. The RPC must answer chain 7193 before any key is read. No
child process gets a key: git gets an environment of its own with the token in a header. The run redacts every secret
from its output, and fails if one shows up there, in any process's command line (sampled every 2 seconds), in the files
it writes, in the seats' node logs, or in the issues, comments and pull requests it wrote.

## The seats' host on AWS (#152, platform#219)

For the deployment's owner. platform#219 moves the 6 role seats' nodes (`oracle-0..4`, `joiner-0`) off your PC onto
one on-demand host in the platform account, and later the bot service (#210) beside them. Like the kit's node, it's
normally stopped: a watcher Lambda (this kit's `lambda/watcher.py`, with several seats) starts it when there's work,
and it powers off when every node is idle, at its maximum run time, or at the devnet's 01:00 stop. Platform's module
(`modules/pof_seats`) runs the code only from images you push, pinned by digest. This repository provides the images
and the watcher. Platform's module README has the order of applies (its design, D13).

**What runs where, once it's on**

| What | Where | Started by |
|---|---|---|
| the chain and the exchange relay | the devnet host | platform's stack |
| 6 role seats' nodes | the seats' host: a container each, tests in its Docker's sandbox | the watcher, on their draws and won bounties |
| the bot service (#210, later) | the seats' host, its own container from the nodes' image | the watcher, on the bot's work |
| the owner's validator, seat 6 | the sandbox account | the kit, on its draws |

### One place per seat key: the laptop's seats stay down

**Never run `scripts/devnet-seats.sh up` while the host serves the same keys**, and never a local `pofctl bot watch`
loop while the hosted bot runs. Two nodes with the same seat's key would both report, seal and sign: duplicate
transactions and nonce clashes. Two bots would act on the same issues, and their transactions would race.

- **Before** platform's pull request that sets `node_image_digest`: `scripts/devnet-seats.sh down` (and `status` says
  `down`) on every machine that ran them.
- **The host serves the keys** as soon as that digest is applied, even while it's stopped: the watcher can start it
  any minute, and so can `seats.sh start`.
- **To run them on the laptop again** (a demo without AWS, a debugging session): set `seats_enabled = false` in the
  stack and apply, wait until `seats.sh status` says the host is stopped, and only then `devnet-seats.sh up`. Put
  it back the other way round: `down` first, then `seats_enabled = true`.
- **The bot:** once `bot_image_digest` is set, stop any local bot loop first, the same way.
- **The suite:** with the hosted seats, `scripts/integration.sh --target aws` takes `--seats-elsewhere` (the
  preflight's local check becomes a note). A preflight check that the host serves them (platform's D11, item 6) isn't
  built: the preflight's "7 seats, all active" plus `seats.sh status` cover it for now.

### The images

Two images, both linux/arm64, from a clean commit, pushed by you with an administrator's profile for the platform
account. Nothing else pushes them; CI doesn't.

| Image | Dockerfile | Platform's repository and variable |
|---|---|---|
| the node (the seats, and #210's bot) | `oracle/Dockerfile` (with `pofctl/`) | `pof-seats-node`, `node_image_digest` |
| the watcher's Lambda | `validator-kit/lambda/Dockerfile` (AWS's Lambda Python 3.12 base, by digest) | `pof-seats-watcher`, `watcher_image_digest` |

1. **Check the build** (optional, nothing pushed; needs Docker with buildx, and QEMU on a non-arm64 machine, which
   Docker Desktop has):
   ```
   scripts/seats-image.sh --build-only        # both: each built twice (the digest must repeat), then started once
   ```
2. **Push**, from a clean checkout of the commit you want (Docker's containerd image store on: Docker Desktop,
   Settings > General). After platform's first apply, the repositories exist:
   ```
   cd <platform>/environments/prod/us-east-1/pof-devnet
   NODE_REPO=$(tofu output -raw seats_node_repository_url) WATCHER_REPO=$(tofu output -raw seats_watcher_repository_url)
   cd -
   AWS_PROFILE=<profile> scripts/seats-image.sh node "$NODE_REPO"
   AWS_PROFILE=<profile> scripts/seats-image.sh watcher "$WATCHER_REPO"
   ```
   Each prints its line, e.g. `node_image_digest = "sha256:..."`. The tag is `arm64-<short sha>`; the repositories'
   tags are immutable, so a commit already pushed prints its digest again without pushing. If platform's outputs are
   named differently, use the repository URLs its README gives.
3. **Set the digests:** stop the laptop's seats (above), then a platform pull request sets `node_image_digest`,
   `watcher_image_digest` and `seat_addresses` (`scripts/devnet-keys.sh addresses`: oracle-0..4 and joiner-0, never
   seat 6). Its plan changes the config parameter and creates the watcher, and replaces nothing. Merge, then
   `tofu-apply`.
4. **A new release** of the node is a new push and a new pull request for the digest: the host keeps the old one until
   then.

**Reproducible:** the build context is `git archive` of the commit, never the directory (so no untracked file gets in),
the base images are pinned by digest, and every timestamp in the layers is the commit's time (`SOURCE_DATE_EPOCH`). So
anyone with the same commit gets the same digest, and `--build-only` prints the one a push would get. The node image's
one moving input is Alpine's `git` package, which changes when Alpine publishes a new one; so the script builds
without Docker's cache, which could hold an older one.

### What the images expect (platform's module)

**A seat's node:** the node image runs as uid **10001** and has `/bin/sh`; its entrypoint is `python3 -m oracle`
(default command `info`, as for the kit). Two ways to start a seat, the same node either way:
- **platform's (PR #221):** `--entrypoint /bin/sh` with a wrapper that reads `/run/secrets/{key,rpc-auth,repo-token}`
  into `ORACLE_PRIVATE_KEY`, `ORACLE_RPC_TOKEN` and `FORGEJO_TOKEN` and `exec`s `python3 -m oracle run --until-idle
  600`, with `devnet-seats.sh`'s `ORACLE_*` settings in the container's environment. Anything else set there, such as
  #210's `ORACLE_REGISTRATION_CHECK` and `ORACLE_REGISTER_WEIGHT`, reaches the node as it is;
- **`python3 -m oracle seat run --until-idle 600`** (`oracle/seat.py`): the same, with the defaults and checks below
  built in. `python3 -m oracle seat info` is the status check.

`oracle/seat.py` sets up what `devnet-seats.sh` sets up for each seat on the laptop:
- **secrets**, each read once from the environment or else a file in `SEAT_SECRETS` (default `/run/secrets`), mounted
  read-only into that seat's container alone: `key` (the seat's signing key, `ORACLE_PRIVATE_KEY`), `rpc-auth`
  (`pof-seats:<key>`, `ORACLE_RPC_TOKEN`), `repo-token` (the read-only `pof-sandbox` token, `FORGEJO_TOKEN`). They go
  into the node's own process environment only: not on a command line, in `docker inspect` or in the logs. Files owned
  by the node's uid, **10001**, mode 0400;
- **settings** (each may be overridden in the container's environment): `ORACLE_RPC` and `ORACLE_RACE` (required),
  `ORACLE_EXCHANGE_URL` (default `<ORACLE_RPC>/exchange`), `ORACLE_REPO` (default `example-org/pof-sandbox`),
  `SEAT_FORGE_URL` (default `https://git.example.com`), `FORGEJO_USER` (default `pof-validator-bot`),
  `ORACLE_ROUND_TIMEOUT` (default 900: the relay's seal window), `ORACLE_POLL` (default 5), `ORACLE_JUDGE` (fake only:
  anything else is refused, proof-of-fix#160), `ORACLE_SANDBOX=api`;
- **`SEAT_WORK`**, the seat's working directory (e.g. `/var/lib/pof-seats/oracle-0`), mounted at the same path inside
  and out, since the sandbox's bind mount of a checkout is resolved by the host's Docker. The node keeps its checkouts
  (`src/`), receipts and `repos.json` there;
- **the sandbox:** the host's Docker socket (`/var/run/docker.sock`) with its group (`--group-add`), as in the kit. The
  node starts each fix's tests in the pinned sandbox image (`oracle/sandbox.py`'s `TEST_IMAGE`; pre-pulling it saves
  the first round a pull), with no network, and refuses a daemon that can't enforce the limits;
- **exit codes:** 0 idle, 2 refused at start (a missing secret or setting, named without its value), 75 the chain
  stayed away (done for this run; the watcher starts the host again).

**The bot** (#210, PR #211): `python3 -m pofctl bot watch --until-idle 600` from the same image, with its own
`POF_BOT_*_FILE` secrets and `POF_BOT_*` settings (bot/service.py; "The bot as a service on the AWS devnet"
below).

**The watcher's Lambda:** handler `watcher.handler` (the image's command), arm64, Python 3.12. Its environment:
`RPC_URL`, `RPC_API_KEY_PARAM` (`/pof-seats/watcher/rpc-auth`, an SSM SecureString read with decryption, a
`<handle>:<key>` sent as HTTP Basic with the default `RPC_API_KEY_HEADER=Basic`), `RACE_ADDRESS`, `SEAT_ADDRESSES`
(the six, comma-separated), `INSTANCE_ID`, `STATE_PARAM` (`/pof-seats/watcher/state`), `ENABLED`, `MAX_STARTS_PER_DAY`,
`MERGE_POLL_MINUTES`, `PENDING_POLL_MINUTES`, `PENDING_MAX_STARTS`, `MAX_BLOCK_RANGE`; for the bot and the seats'
registration check (#210): `BOT_WORK=true`, `BOT_ENABLED` (off: the bot's work starts nothing, a registration waiting
for the seats' check still does), `BOT_REPO_IDS`, `DUE_POLL_MINUTES`. It starts the host for a draw
of any of the six seats still waiting for its result, a won bounty one of them judged until it merges, and an undecided
draw again every `PENDING_POLL_MINUTES` (at most `PENDING_MAX_STARTS` times). The bot's work reads only the chain (no
forge token): see "The bot as a service on the AWS devnet" below. Its result line, one JSON object a minute: `idle`, `started`,
`fuse`, `disabled` or the instance's state, with the submissions, merges, retries and the bot's kinds that caused it.

## The bot as a service on the AWS devnet (#210)

On the devnet, a `bounty`-labelled issue goes from registered to paid and closed with only the reporter's, the
funder's and the solver's own steps, the maintainer's merge and the clock's warps. Two things do the rest unattended:

- **the seats' registration check:** the six role seats' nodes, with `ORACLE_REGISTRATION_CHECK=on` (and
  `ORACLE_REPO_ID` set to the record's `repo`), sign RaceV2's `accept` for a registration that a labelled issue claims,
  with the fake judge at `ORACLE_REGISTER_WEIGHT` (120), and one of them relays it at quorum. Seat 6's kit leaves it off;
- **the bot:** `pofctl bot watch --until-idle 600`, its own container on the seats host (platform#219), with its own
  key. It links the opened bounty to the claiming issue, settles a bounty whose outcome is final, calls `timeOut`,
  `mergeExpired` and `sunset` once they're due, closes the issue of a bounty that ended, and posts one hint on a labelled
  issue that doesn't name a valid registration. Its only transactions are `settle`, `timeOut`, `mergeExpired` and
  `sunset`; it never registers, funds, judges, merges or claims for anyone.

**The bot's keys and token** (the owner, once; never on a command line):

1. `scripts/devnet-keys.sh init` adds the `bot-service` key to OpenBao (`secret/proof-of-fix/devnet/bot-service`);
   `scripts/devnet.sh fund-address <its address>` gives it devnet gas. It's not the `bot` key people use with pofctl.
2. A devnet API key for it: `keys.sh add pof-bot` (platform-197), as `pof-bot:<key>`.
3. A Forgejo user `pof-bounty-bot` in a team on `pof-sandbox` alone, with write on issues only (task 1.7 records the
   units it needed), and a token scoped `write:issue`, kept in OpenBao by platform's script from a hidden prompt.
4. platform's script copies the three into `/pof-seats/bot/key`, `/pof-seats/bot/rpc-auth` and
   `/pof-seats/bot/repo-token`; the host mounts them read-only into the bot's container alone, as the files
   `POF_BOT_KEY_FILE`, `POF_BOT_RPC_AUTH_FILE` and `POF_BOT_FORGE_TOKEN_FILE` name. The other settings
   (`POF_BOT_RPC`, `POF_BOT_RACE`, `POF_BOT_FROM_BLOCK`, `POF_BOT_REPO`, `POF_BOT_REPO_ID`, `POF_BOT_FORGE_URL`,
   `POF_BOT_FORGE_USER`, `POF_BOT_LABEL`, `POF_BOT_POLL_SECONDS`, `POF_BOT_HINT_GRACE`) are plain configuration;
   bot/service.py lists them. It refuses to start (exit 2) on another chain, with an oracle's or the deployer's key, a
   missing or empty secret file, or an RPC URL with a credential in it.

**How the reporter claims a registration:** register from the reporter's own wallet, then paste the two lines it
prints into the labelled issue's body, each on its own line:
```
pofctl reporter register --repo registry
#   Registration: 42
#   Reporter wallet: 0x…
```
The first labelled issue on the repository that names the registration with its reporter's wallet wins it. Without
valid lines, the bot comments one hint (five minutes after the issue opens), and never a second one.

**What the bot closes:** an open labelled issue linked to a bounty that ended: `Paid` with the payout comment, `Unsolved`
(sunset) or `Refunded` with a comment naming the outcome and its transaction. To keep a closed issue open, reopen it and
**remove the `bounty` label**: the bot acts only on labelled issues.

**By hand still works, but isn't needed:** `pofctl bot settle --bounty <n> --repo example-org/pof-sandbox
--issue <issue>` and `pofctl bot close --repo example-org/pof-sandbox` do the same steps, and the bot sees them
done (its markers and the contract's state). `pofctl oracle accept` and `pofctl bot link` are the stub quorum's and the
manual link, for a devnet without the seats' check.

**Its limits:** a pass every 30 s; at most 5 writes a pass and 50 a run (exit 4: the next host run goes on); back off
on forge or RPC errors, exit 75 after 30 minutes of them; exit 0 after 10 idle minutes, so the host can power off. The
first runs on the shared devnet work through the backlog of stale deadlines within that fuse.

**Rollback:** `BOT_ENABLED=false` on the watcher and the bot's container removed; `ORACLE_REGISTRATION_CHECK=off` on the
nodes. The manual commands above still work.

**Its integration run:** `scripts/integration.sh --target aws --hosted-bot --preflight`, then `--hosted-bot --only 10`
(10a the paid path, 10b a timeout, an expired merge and a sunset, 10c the hint), or `--hosted-bot` for every scenario
opened through the seats and the bot. It waits for each of the bot's steps up to `--bot-timeout` (600 s).

## A Forgejo target (#112)

The repository can live on a Forgejo instead of GitHub (`forge = "forgejo"`; GitHub stays the default). The node reads
its pull requests through the Forgejo's API (`<forge_url>/api/v1`) and fetches each claimed commit from
`<forge_url>/<repository>.git`, over HTTPS (port 443, already in `egress_ports`).

The node's Forgejo client (`bot/forgejo.py`) accepts an HTTPS base on any host, and plain HTTP only on its own loopback
(the local loop's throwaway Forgejo), the same rule as the clone URL in `oracle/fetch.py`. Rebuild the node image from a
commit that includes this.

1. **A bot user with Read on the repository**, e.g. `pof-validator-bot`: a plain user (not an admin), added to the
   repository as a collaborator with **Read** (or to a team with Read on that one repository), nothing else.
2. **A token for that user** with the scopes **`read:repository`** and **`read:issue`** only (Settings → Applications →
   Generate token, signed in as the bot user). The node reads pull requests and the bounty's issue, and fetches commits
   with it; it can't write anything. Without `read:issue` a real judge reads no issue, so it gives no verdict: its log
   says `not judged yet: reading issue`. (A seat on the fake judge reads no issue, and needs only `read:repository`.)
3. **Store it** in your Secrets Manager the same way as a GitHub token, without it touching your shell history:
   ```
   read -rs REPO_TOKEN && aws secretsmanager create-secret --name pof-validator/repo-token --secret-string "$REPO_TOKEN"; unset REPO_TOKEN
   ```
4. **Set the inputs** (step 3's `validator.auto.tfvars`):
   ```
   forge                 = "forgejo"
   forge_url             = "https://git.example.com"        # the base URL, HTTPS, no trailing slash
   repository            = "<owner>/<repository>"           # as on the Forgejo
   repo_token_secret_arn = "arn:aws:secretsmanager:...:secret:pof-validator/repo-token-..."
   repo_token_user       = "pof-validator-bot"              # the token's user (git sends it with the token)
   ```

What the node gets: a `repos.json` naming the repository's host (`{"repos": {"<repository>": {"host": "forgejo", "api":
"<forge_url>"}}}`, no credentials) at `/etc/pof-validator/repos.json`, mounted read-only and named by `ORACLE_REPOS`;
the token as `FORGEJO_TOKEN` (read from the secret at each run, passed to the container by name only, never logged);
and `FORGEJO_USER` = `repo_token_user`. With a token, the API gets it as `Authorization: token …` and git as HTTP Basic
(`FORGEJO_USER` and the token), both as headers, never in a URL.

## The model: called directly (#118)

A counted judge's proof, "this prompt got this answer", holds only if the encrypted connection ends in **your node**,
not in someone's proxy. So the node calls its provider itself (`oracle/models.py`, standard library only), and the
AgentCore model gateway is for development only. `model_provider` and `model_id` become the node's
`ORACLE_JUDGE=direct:<provider>:<model>`:

| `model_provider` | The node calls | Credentials |
|---|---|---|
| `bedrock` | Bedrock Runtime's **Converse** API in this account's region, signed with AWS Signature Version 4 | the instance role's, read by the node from IMDSv2 and refreshed before they expire; IAM allows `bedrock:InvokeModel` (which authorizes Converse) on `bedrock_model_arns` only, and the node refuses any model not in that list (`ORACLE_MODEL_ALLOW`) |
| `api` + `anthropic` | the Messages API | your key from Secrets Manager, only in the `x-api-key` header |
| `api` + `openai` | Chat Completions; with `model_api_url` any OpenAI-compatible server (a self-hosted vLLM or llama.cpp, #125) | `Authorization: Bearer` (a server of your own may need none) |
| `api` + `gemini` | Gemini's `generateContent` | the `x-goog-api-key` header |

**Which to choose:** whichever model family your seat represents, from the provider you already pay; the network caps
seats per model family and per provider (ADR 0003), so a less common family or a self-hosted open-weight model is
welcome. Bedrock keeps the key problem away (no key at all: the instance role); an API key works from any cloud.

- **The receipt** records the provider, the model ID, the endpoint's host, the provider's request ID and its stop
  reason, and the **provider's own token counts** (its usage object untouched); those counts are what your node
  reports to the meter, so you're paid for what the provider billed. This is the record a later attestation (Nitro or
  dstack, #94) binds.
- **Spending guards** (per run of the node): `max_output_tokens` per verdict (default 4000), `max_model_calls` (20,
  retries included) and `max_run_tokens` (500,000 in plus out, checked against each call's worst case before it's
  made). A call times out after 120 s; throttling, overload and timeouts are retried twice with backoff (honouring
  `Retry-After`, at most 30 s); any other refusal (a bad request, no access) is never retried, and the node skips that
  submission instead of calling again.
- **Your fuses** (across runs). A validator takes work from the contract with no approval per job, so what limits a bad
  day is these, not you:
  - `max_starts_per_day` (default 12) limits the watcher's starts in a UTC day. The worst case a day is starts x
    `max_model_calls` x your price per call: 12 x 20 x $0.12 is about $29 at this sheet's dearest verdict. It takes effect
    at once. Past it the watcher logs `"action": "fuse"`, and the work stays on its list for the next day. A start you make
    yourself doesn't count. Set it well above your normal day: on a real chain a draw you miss costs the $5 silence slash.
  - `budget_stop` (on with `budget_limit_usd` and `budget_emails`) is the backstop for the month: at 100 % actual, AWS
    Budgets attaches a policy denying Bedrock's calls and the watcher's start, and emails you. **AWS's cost data arrives
    hours late**, so it can overshoot. It stays on until you reverse it:
    ```
    aws budgets execute-budget-action --account-id "$(aws sts get-caller-identity --query Account --output text)" \
        --budget-name pof-validator-monthly --action-id "$(tofu output -raw budget_action_id)" \
        --execution-type REVERSE_BUDGET_ACTION
    ```
    With an API key, it stops new starts but not a run already going, so set a limit in your provider's console too.
- **One chain key per machine.** Give each machine its own key (`keys.sh add <handle>` in platform's stack), so `keys.sh
  remove <handle>` revokes one and leaves the others running.
- **No proxy, no redirects:** the node ignores proxy settings and follows no redirect, so the request (and its key) goes
  only to the endpoint named. HTTPS only (plain HTTP only on the node's own loopback).
- **With Bedrock, the instance metadata hop limit is 2:** the node's container reads the role's credentials itself.
  Only the node's container has a network; the sandbox's containers have none, so the fix's code still can't reach
  them. With an API key it stays 1.
- **Check it once, by hand,** before the first counted run: one small call (at most 64 tokens out, no retry; a
  fraction of a cent) with the node's own image and credentials, from a shell on the running node
  (`aws ssm start-session`, step 5):
  ```
  sudo docker run --rm -e ORACLE_JUDGE='direct:bedrock:<model_id>' -e ORACLE_MODEL_ALLOW='<model_id>' \
    -e AWS_REGION=<region> '<node_image>' model-check
  ```
  It prints the answer, the provider's usage object, the endpoint and the request ID. With an API, pass
  `-e ORACLE_JUDGE='direct:<provider>:<model>' -e MODEL_API_KEY` (read from your secret) instead.

## The sandbox and its trust boundary (#116)

The node runs in a container, as uid 10001, with the host's Docker socket and the socket's group. For each fix it
starts the tests in a **sibling container** through the Docker Engine API on that socket (`ORACLE_SANDBOX=api`,
`DOCKER_SOCKET`, standard library, no Docker CLI in the image): the test image pinned by digest, `--network none`, a
read-only filesystem, the fix's checkout mounted read-only at `/src`, no capabilities, `no-new-privileges`, an init
process, 1 vCPU, 256 MB, 64 processes, a 64 MB `/tmp` that can't run programs, and a time limit (inside, and a kill
from outside if that fails). The exit code and the logs are hashed into the receipt. Nothing here is specific to a
cloud: any Linux host with a Docker (or Docker-API-compatible) engine runs it the same way.

The node **fails closed**: before the first run it asks the engine whether it can enforce memory, CPU and process
limits (`/info`), and before starting each sandbox it reads the container back and checks every limit was applied (and
that the engine raised no warning). A daemon that can't, or dropped one, doesn't run the fix: the check fails.

- **The socket is root on the host.** Whoever holds the host's Docker socket can start a privileged container. Only
  the node holds it: the node's image is pinned by digest and the host does nothing else (no inbound, its own network,
  stopped between runs, powered off after each). The fix's code never sees the socket, the network or a writable copy
  of itself. This is the issue's first option, chosen because the kit's host is single-purpose and short-lived.
- **The safer option: a rootless engine.** Point `DOCKER_SOCKET` at a rootless Docker (or Podman's Docker-compatible
  service) socket and mount that instead of `/var/run/docker.sock`: whoever holds it gets only an unprivileged user.
  It needs cgroup v2 with the `cpu`, `memory` and `pids` controllers delegated to that user; without them a rootless
  engine accepts the limits, reports them back, warns nothing and enforces none (seen with rootless Docker 28 on a
  cgroup v1 host: 512 MB allocated under a 256 MB limit). The node's `/info` check refuses such an engine.
- **A socket proxy doesn't help:** it can filter which endpoints the node calls, but `containers/create` is the one it
  needs, and that endpoint alone can ask for a privileged container.
- **Same paths on both sides:** the sandbox's mount is resolved by the engine, on the host, so the checkouts sit in
  `/var/lib/pof-node/src` on the host and at the same path in the node's container (`ORACLE_SRC_ROOT`).
- **Not chosen:** running the node on the host itself (it loses the pinned, measurable node image).
  `ORACLE_SANDBOX_USER=65534:65534` runs the tests as `nobody` once the checkouts are readable by it.

## Before the live demo (not in the kit yet)

Done since the first kit: `oracle run --until-idle` (the v2 node: only its draws, usage reports, seal, reveal, sign,
relay, the merge), `ORACLE_KEYS=env` with `ORACLE_PRIVATE_KEY`, the chain's API key in a header (`Basic` by default),
`oracle withdraw-fees`, and the watcher's draw filter (`Verdicts.drawn`) with merge polling.

1. ~~**The fix's code**~~ — done (#115): the node fetches the pull request's head commit itself (`oracle/fetch.py`: a
   shallow fetch of that one commit, checked against the seal, read-only, size and time limits; git in the image).
2. ~~**The sandbox from inside a container**~~ — done (#116): the node starts it through the Docker socket's API; see
   "The sandbox and its trust boundary".
3. ~~**The judges' exchange across machines**~~ — done (#117, #150): the kit's `exchange_url` gives the node the hosted
   relay (`docs/exchange.md`), behind the RPC's own key.
4. ~~**Direct model calls from the node**~~ — done (#118): `model_provider` (`bedrock` or `api`) and `model_id` set
   the node's `ORACLE_JUDGE=direct:<provider>:<model>`; the provider's own token counts reach the receipt and the
   meter; spending guards per run. See "The model: called directly". Still to do: one real call on AWS, by the owner.
5. **Attestation:** Nitro Enclaves on a c6g.xlarge-class instance (COSTS.md), with the node's key inside the enclave.
   Later, **AWS KMS** secp256k1 signing, so the key never leaves KMS.
