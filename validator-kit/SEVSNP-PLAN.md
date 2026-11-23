# The SEV-SNP test host: the apply plan (#253; #251 L18 items 3 and 6, L21, task 4.9)

Everything here was prepared without creating or starting anything in AWS. The person who applies it starts the one
test host, after telling the owner. Read-only checks behind the facts below were run on 2026-11-20.

**Run on 2026-11-20 (the owner approved it): it passed.** NitroTPM and SEV-SNP work together on one c6a.large;
`verify.py` passed every check. What happened, and what differed from the steps below, is in "The first run" at the end;
the evidence is in `validator-kit/sevsnp/evidence/2026-11-20/`.

**After the run (2026-11-20):** the disk was rebuilt with the two fixes the run left (the VLEK's GUID read in the
table's byte order; the node image on Debian with git pinned, no Alpine), so it has a new root hash, `45032ccd…1e8e`
("The build's values"): the next apply uploads it as a new snapshot (steps 3–5). The v3 watcher is in the Terraform,
off by default ("The v3 watcher"), and "Boot time against the deadlines" sets the measured boot against the windows.
Neither was applied: nothing in AWS changed.

## At a glance

| | |
|---|---|
| **Account** | `sandbox-pof-validator`, **111111111111** (an Organization sandbox account, platform-201; v2's kit already lives there: `pof-validator-node`, a stopped t4g.small). Its platform budget is $10 a month; November's actual spend was $1.82 on 2026-11-20. |
| **How to reach it** | from the profile `your-aws-profile` (the management account), assume `arn:aws:iam::111111111111:role/OrganizationAccountAccessRole` (checked 2026-11-20 with a read-only call). The platform admins' SSO permission set `AdministratorAccess` on the account works too. |
| **Region** | **us-east-2** (US East, Ohio). On shared tenancy SEV-SNP is offered only in US East (Ohio) and Europe (Ireland) ([AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/sev-snp.html)). |
| **Instance type** | **c6a.large** (2 vCPUs, 4 GiB, AMD EPYC Milan; SEV-SNP and NitroTPM 2.0 supported: `describe-instance-types`) |
| **Cost** | **$0.0842 an hour** running: $0.0765 on demand (Price List API, us-east-2, 2026-11-20) plus SEV-SNP's 10 %; plus $0.005 an hour of public IPv4. Stopped: about $2.10 a month (20 GiB data volume, 1 GiB root, the snapshot, the secret). A 2-hour test costs about $0.18 of compute. |
| **Blocker** | the sandbox account's SCP `sandbox-region-us-east-1` (p-7gapimy5) denied every region but us-east-1 (step 1). Removed 2026-11-20: platform PR #228 allows us-east-2. |

The alternative without the SCP change is a Dedicated Host in us-east-1: a c6a host is **$8.078 an hour** (Price List
API), billed while allocated. Not recommended.

## 1. Allow us-east-2 in the sandbox accounts (platform, the owner applies)

The Organization stack is applied locally by the owner (`environments/prod/global/organization`). The change, in
`~/dev/infra/modules/organization`:

```hcl
# variables.tf
variable "sandbox_regions" {
  description = "Regions sandbox accounts may use besides Bedrock's profile regions: tenant_regions plus us-east-2 for proof-of-fix's SEV-SNP validator (SEV-SNP's shared tenancy is only in us-east-2 and eu-west-1)."
  type        = list(string)
  default     = ["us-east-1", "us-east-2"]
}

# guardrails.tf, resource "aws_organizations_policy" "sandbox_region": name, description and DenyOtherRegions
  name        = "sandbox-region-${join("-", var.sandbox_regions)}"
  description = "Sandbox: resources only in ${join(", ", var.sandbox_regions)}; Bedrock invocations also in ${join(", ", var.sandbox_bedrock_regions)}"
        Condition = { StringNotEquals = { "aws:RequestedRegion" = var.sandbox_regions } }
```

Then, with the management account's profile: `cd ~/dev/infra/environments/prod/global/organization && tofu plan`
(one in-place change to the policy) and `tofu apply`. Check from the sandbox account:
`aws ec2 describe-instance-types --region us-east-2 --instance-types c6a.large --query 'InstanceTypes[0].InstanceType'`.

## 2. A profile for the sandbox account

```ini
# ~/.aws/config
[profile pof-sandbox]
role_arn = arn:aws:iam::111111111111:role/OrganizationAccountAccessRole
source_profile = your-aws-profile
region = us-east-2
```

```bash
aws sso login --profile your-aws-profile
export AWS_PROFILE=pof-sandbox AWS_REGION=us-east-2
aws sts get-caller-identity --query Arn --output text   # …:assumed-role/OrganizationAccountAccessRole/…
```

Tools that don't follow `source_profile` (coldsnap) take exported credentials:
`eval "$(aws configure export-credentials --profile pof-sandbox --format env)"`.

## 3. Build the disk (no AWS)

From a clean checkout of the branch's commit (`proof-of-fix-251-sevsnp-kit`):

```bash
scripts/checker-disk.sh --twice        # two builds without the cache must agree; prints the root hash and digest
```

The build of 2026-11-20 (after the first run's fixes) printed the values in "The build's values" below; yours must
equal them. The first run booted the build before it, `c7b72b70…43c8`, also listed there.
`validator-kit/sevsnp/out/` then holds `disk.raw` (1 GiB), `uki.efi`, `roothash`, `pcrs.json`, `manifest.json`.

## 4. Upload the disk as an EBS snapshot

[coldsnap](https://github.com/awslabs/coldsnap) writes a raw image straight into an EBS snapshot (EBS direct APIs; no S3
bucket, no vmimport role):

```bash
cargo install --locked coldsnap            # needs rustc >= 1.94.1 (its AWS SDK crates); with an older toolchain:
# docker run --rm -v "$PWD/.coldsnap":/out rust:1 cargo install --locked coldsnap --root /out   # then .coldsnap/bin/coldsnap
eval "$(aws configure export-credentials --profile pof-sandbox --format env)"; export AWS_REGION=us-east-2
SNAP=$(coldsnap upload --wait validator-kit/sevsnp/out/disk.raw)
echo "$SNAP"                               # snap-…
```

## 5. Terraform, first apply: everything but the instance

```bash
cd validator-kit/sevsnp/terraform
cat > test.tfvars <<EOF                    # *.tfvars is git-ignored
snapshot_id   = "$SNAP"
manifest_path = "../out/manifest.json"
budget_emails = ["<the owner's address>"]
budget_limit_usd = 15
EOF
tofu init
tofu plan -var-file=test.tfvars            # VPC, subnet, IGW, SG (no ingress), role, secret, the AMI, the budget
tofu apply -var-file=test.tfvars
tofu output                                # ami_id, roothash, image_digest, signing_key_secret_arn
```

`create_instance` is false: nothing runs yet. The AMI is UEFI with NitroTPM v2.0 and IMDSv2, tagged with the root hash.
The budget and its alerts exist from this apply; its automatic stop (an AWS Budgets action) names the instance, so
step 6 creates it, seconds after the instance (2026-11-20: 7 s after; it was `STANDBY` once the apply ended).

## 6. Second apply: the test host (this starts it)

Tell the owner first. Then:

```bash
NONCE=$(openssl rand -hex 16); echo "$NONCE"   # keep it: the verifier checks it
tofu apply -var-file=test.tfvars -var create_instance=true -var attest_nonce="$NONCE" -var power_off=false
ID=$(tofu output -raw instance_id)
aws ec2 describe-instances --instance-ids "$ID" --query 'Reservations[].Instances[].CpuOptions'
# must show "AmdSevSnp": "enabled"
```

With no `node_config` the boot only attests: it formats the data volume, loads the two images, prints its evidence on
the serial console, runs the attested-mode self-test, and (with `power_off=false`) stays up so the console can be read.
Wait about two minutes (2026-11-20: `POF-ATTEST ok` 22 s after the kernel started, the console readable 2 minutes after
launch). Until 2026-11-20 the module's test `var.node_config == {}` never held (a `map(string)` isn't equal to `{}`), so
the user data always carried the signing key's ARN and the node started; with the secret empty it stopped at once
(`Secrets Manager refused …: ResourceNotFoundException`). Fixed: `length(var.node_config) == 0`.

## 7. Fetch and verify the attestation

```bash
aws ec2 get-console-output --instance-id "$ID" --latest --output text > console.txt
# EC2 breaks a long line about every 1 KB with its own "[2026-…T…]" timestamp and ends lines with CR: verify.py
# removes both, but a base64 field cut out with grep or cut by hand won't decode
grep '^.*POF-ATTEST' console.txt | cut -c1-160          # roothash, nonce, pcrs, snp-summary, snp-report, snp-cert,
                                                       # nitrotpm, attested-check, ok
aws ec2 stop-instances --instance-ids "$ID"            # stop it as soon as the console is saved
```

The expected SEV-SNP launch measurement (AWS's firmware, 2 vCPUs), from AWS's reproducible OVMF:

```bash
git clone https://github.com/aws/uefi && cd uefi
docker run --rm -v "$PWD":/src -w /src nixos/nix nix-build --pure && cp result/ovmf_img.fd ..   # or a released binary
pip install sev-snp-measure
sev-snp-measure --mode snp --vcpus 2 --vmm-type ec2 --ovmf ../ovmf_img.fd      # → the 48-byte measurement, hex
```

On 2026-11-20 the released binary of aws/uefi's release `20260814` (`ovmf_img.fd`, sha256 `67aaae01…72bc9`) measured
to the report's value with sev-snp-measure 0.0.13: `7a89ccea…5b1dc766` (the four older releases don't;
`evidence/2026-11-20/measurement.txt` has all five). A rebuild with nix wasn't needed for the match; it remains the way
to show that the binary is the source's.

AMD's chain for the report's key (shared tenancy signs with AWS's VLEK), and AWS's Nitro root for the NitroTPM document:

```bash
curl -sf https://kdsintf.amd.com/vlek/v1/Milan/cert_chain -o amd-vlek-chain.pem
curl -sfO https://aws-nitro-enclaves.amazonaws.com/AWS_NitroEnclaves_Root-G1.zip && unzip -o AWS_NitroEnclaves_Root-G1.zip
openssl x509 -in root.pem -noout -fingerprint -sha256
# must be 64:1A:03:21:A3:E2:44:EF:E4:56:46:31:95:D6:06:31:7E:D7:CD:CC:3C:17:56:E0:98:93:F3:C6:8F:79:BB:5B
```

Then every check at once:

```bash
python3 validator-kit/sevsnp/verify.py --console console.txt --manifest validator-kit/sevsnp/out/manifest.json \
  --nonce "$NONCE" --snp-measurement <the hex above> --amd-chain amd-vlek-chain.pem --nitro-root root.pem \
  --save evidence/
```

A second opinion on the report's signature, with AMD's tool as AWS documents
([snp-attestation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snp-attestation.html)):
`cargo install snpguest`, then `snpguest fetch ca pem evidence/ milan --endorser vlek`,
`snpguest verify certs evidence/` and `snpguest verify attestation evidence/ evidence/report.bin`.

## 8. What makes `sevSnpValidator` and `attestedImages` pass

`attestedImages` (L18 item 6, L21) passes when, on this host:

1. `verify.py` passes every check: `roothash`, `snpReportData`, `snpMeasurement`, `snpPolicy`, `snpSignature`,
   `nitroPcrs`, `nitroBinding`, `nitroSignature`, `imageDigest`, `attestedImages`;
2. `manifest.json`'s `image_digest` is the one the release candidate's devnet lists as its accepted image (and the
   genesis's for Sepolia, task 7.1), with `amd-sev-snp` among its TEE types;
3. the boot's `attested-check` line shows the unlisted probe refused (the node stops on any unlisted image).

`sevSnpValidator` (L18 item 3) then needs the node run on the devnet, on the same host:

1. a signing key in the secret (`read -rs KEY && aws secretsmanager put-secret-value --secret-id "$(tofu output -raw
   signing_key_secret_arn)" --secret-string "$KEY"`), funded on the devnet with coins for the $250 bond and gas;
2. `node_config` in `test.tfvars`, for example `{ ORACLE_VERSION = "3", ORACLE_RPC = "https://…",
   ORACLE_RACE = "0x…", ORACLE_FAMILY = "anthropic/claude", ORACLE_JUDGE = "fake", ORACLE_IMAGE = "<image_digest>",
   ORACLE_HOST_ID = "aws:us-east-2", ORACLE_FIX_SOURCE = "radicle", ORACLE_MERGE_VIA = "radicle",
   ORACLE_SEAT_NODES = "chain", ORACLE_RADICLE_RID = "<the deployment record's RID>",
   ORACLE_FROM_BLOCK = "<the deployment record's block>" (#312; ORACLE_LOG_RANGE only for a strict provider),
   ORACLE_REPO = "<the repository's working copy, which `oracle run` requires>" }` (model (a), the launch's: the
   chain's key by `RPC_API_KEY_SECRET_ARN`, listed in `extra_secret_arns`), `radicle_seed = "<the seed's Node
   ID>@<its address>:8776"` (seed/README.md: `rad self --nid` on the seed, and its Elastic IP), and `node_command =
   "register --bond 250 --proof tee --tee-type amd-sev-snp --level A --firmware <snp-summary's firmware> --rad-node
   <nid>"`, where `<nid>` is this host's own Radicle node key: its `rad self --nid`, which every boot prints on the
   console as `POF-RADICLE nid z6Mk…` (the key was made on the first boot, on the data volume, so step 7's console
   already shows it). Apply, start the instance (`aws ec2 start-instances`), read the console: it registers with an
   SEV-SNP report as its attestation and prints `registered 0x… as a candidate (…, Radicle node did:key:z6Mk…)`, the
   same key as the `POF-RADICLE nid` line (`--rad-node` left out reads the same key, `rad self --did` through the
   mounted control socket; naming it makes the operator's check explicit). The node can't be changed later (another
   node is another registration), so **keep the data volume**: losing it loses the key (see Open risks);
3. `node_command = "run --until-idle 600"`, apply, and let it judge a fix in the release candidate's devnet run (7.0);
   its receipt's proof is an SEV-SNP report over the receipt's hash (`ORACLE_KEYS=snp`).

Changing `user_data` stops and starts the instance (the provider's behaviour): each change is a run.

**This host's Radicle node (#251 L11, L12; 2026-11-21).** The disk runs Radicle 1.10.3 (`pof-radicle-setup.service`,
`pof-radicle.service`, `pof-radicle-ready.service`) before the node: the key made once in `/data/state/radicle` (the
data volume), a config that listens on no address and, with static peers, dials only `radicle_seed` (never Radicle's
public bootstrap nodes, which dynamic peers dial on the main network), the one seeding policy for the RID
(scope `all`), then `radicle-ready.sh`: a sync with the seed and the working copy the node pushes `main` from, made
again on the scratch disk at each boot from the node's own storage (`rad checkout`, so a boot whose sync fails still
has one). The node's container reaches it with no command prefix (`ORACLE_RADICLE_EXEC` empty): it mounts the
Radicle home and the working copy and runs the disk's `rad` and `git-remote-rad` as the same user (uid 10001), so its
`rad` and `git` calls go through radicle-node's control socket and the shared storage, and only radicle-node uses the
network. No inbound port: the security group stays as it was, and only egress 8776 is added (`egress_ports`). Tested
on the internal Docker network with the seed's and the disk's own Radicle files, each validator's oracle reaching its
Radicle node through a container with no network on the same storage: `scripts/kit-radicle.sh`.

## The v3 watcher (after step 8)

v2's node is started by its watcher only when there's work; the SEV-SNP kit's is too
(`validator-kit/sevsnp/lambda/watcher.py`, `terraform/watcher.tf`). It exists with the instance (`create_instance`) and
does nothing until `watcher_enabled = true`: its EventBridge schedule is disabled and its kill switch set.

```bash
# in test.tfvars, once the node runs (step 8: registered, node_command = "run --until-idle 600")
watcher_enabled   = true
validator_address = "0x…"        # the signing key's address
# the chain and the race default to node_config's ORACLE_RPC and ORACLE_RACE; a keyed RPC URL goes in a secret:
# rpc_url_secret_arn = "arn:aws:secretsmanager:us-east-2:…:secret:pof-snp/rpc-url-…"
max_starts_per_day = 12
tofu apply -var-file=test.tfvars
aws logs tail /aws/lambda/pof-snp-watcher --follow     # one JSON line a minute: "idle", "started", "running", …
```

Every minute it reads Panels' `Seated` events naming the key (any panel kind: counted, shadow, audit, challenge, and a
replacement seat after a missed deadline) and, for each seat it lists, `panel(pid)` and `seat(pid, slot)` in the
chain's time. A seat that hasn't sealed before `sealBy`, or that sealed and whose reveal window is open or opens
within 3 minutes (`reveal_lead_seconds`), starts the stopped instance; the node holds it up while the seat is open and
powers it off 10 minutes after its last work. A seat still due while the instance is stopped again (a crash) starts it
again every 10 minutes, 3 times at most. The guardrails: `max_starts_per_day` (12), the kill switch, the logs; no seal
work while `Panels.capacity(key)` is 0 (the node's spending pause; a reveal still starts it: no model call, and a
sealed seat that doesn't reveal is slashed); once a UTC day while paused, a start so the node can restore its capacity
at a new period (`unpause_check = "off"` leaves that to you); no start while the budget's stop holds (actual spend at
the limit). Its IAM: `ec2:StartInstances` on this instance only, `ec2:DescribeInstances`, its own parameter and logs,
the RPC secret if named, and `budgets:ViewBudget` on this kit's budget. Its RPC calls are reads; it holds no key.

**The Radicle duty (2026-11-21).** With `ORACLE_MERGE_VIA = "radicle"` in `node_config` the watcher also reads
`Heads.head` every minute (`WAKE_ON_HEAD`) and starts the stopped instance once when it moves: this validator's node is
one of the repository's delegates, and the canonical `main` follows `Heads.head` only once 4 of the 7 delegates have
pushed it, each from its own host. Seats alone wake a host for the checks it's drawn for, not for a fix merged by
others, so without it the canonical `main` lagged `Heads.head` until 4 delegates happened to be drawn again
(`scripts/kit-radicle.sh`, scenario L; scenario W with the duty). Each merge costs each validator one start: about
11 minutes of c6a.large at `run --until-idle 600`, about $0.016. It isn't held by the spend pause (no model call); the
fuse, the budget and the kill switch hold it as any start.

## 9. Stop and destroy

```bash
aws ec2 stop-instances --instance-ids "$ID"                         # any time; it also stops itself after a run
cd validator-kit/sevsnp/terraform && tofu destroy -var-file=test.tfvars   # instance, AMI, network, role, budget
aws ec2 delete-snapshot --snapshot-id "$SNAP"                       # the AMI's deregistration leaves the snapshot
# the secret is scheduled for deletion (7 days); to remove it at once:
# aws secretsmanager delete-secret --secret-id pof-snp/signing-key --force-delete-without-recovery
```

If the SCP change was only for this test, revert step 1 afterwards.

## The release candidate's run (task 7.0; the owner's decision, 2026-11-21)

The release candidate's real-SEV-SNP items (L18 items 3 and 6, and item 4's model run) run on a **temporary test
chain in AWS**, beside the SEV-SNP host. Nothing of it has been applied or started: everything below waits for the
owner's approval, each start separately.

**What runs where.**

| | |
|---|---|
| **Test-chain host** | one **c6a.xlarge** (4 vCPUs, 8 GiB), `validator-kit/sevsnp/testchain` (its own OpenTofu root module, in the **kit's VPC and public subnet**, found by the kit's Name tags; the kit's state is untouched). Amazon Linux 2023, encrypted 40 GB gp3, IMDSv2 only, **SSM only** (no SSH, no key pair). It runs, as Docker containers from pinned images: **anvil** (chain 31337, **production windows**, the clock moved by the run), the **Radicle seed** (Radicle 1.10.3, `seed/radicle`'s setup), and the **six other validators** (genesis and v1-v5, each with its own Radicle node configured as the disk configures a validator's, its tests in the pinned sandbox image): the release candidate's external set, `tests/integration/external_v3.py`. |
| **SEV-SNP host** | the kit's c6a.large on the measured disk (this plan's steps 3-6), the **outside validator**: it registers itself (`tee`, `amd-sev-snp`, the disk's `image_digest`), qualifies by its shadow verdicts, and sits a fix's counted panel, reading every issue and patch through its own Radicle node, which dials only the seed. |
| **Network** | the test-chain host's security group admits **only the SEV-SNP host's group**, on the RPC port (8545) and the seed's (8776); both are published on the host's **private address** only. The module adds one egress rule to the kit's group: the RPC port, to the test-chain host's group only (8776 out was already allowed). Out: HTTPS (SSM, S3, the AL2023 repository) and DNS. The public IPv4 address is for outbound only, as the kit's. |
| **This machine** | reaches the test chain **only through SSM**: Run Command for the run, and port forwards for its own view (the chain's RPC on `127.0.0.1:18545`, the seed on `127.0.0.1:18776`). No port is open to the internet. |
| **Stops** | the driver stops both machines at the end, on any failure and on Ctrl-C/SIGTERM/SIGHUP, and puts the SEV-SNP host's user data back; an **auto-stop Lambda** (every 10 minutes) stops any instance with the kit's tag (`pof:kit = validator-kit/sevsnp`: both machines) that has run **8 hours** since its last start (`autostop_hours`); the test-chain host also schedules its own shutdown 8 hours after each boot; and a **budget** ($10 a month, alerts at 50 % and 80 % actual and 100 % forecast, both instances stopped at 100 % actual). |

**Why the outside validator is the seventh of seven:** the clock waits for it (`external_hold`, POF_V3_EXTERNAL_WAIT)
at each deadline its open seat still has to meet, in wall time, so its cold start and every check fit production
windows; and for the fix's draw four of the six pause their capacity (as an operator may) so the counted panel of 3 is
genesis, v1 and the SEV-SNP host, which then must seal and reveal for the verdict to count. They resume at once.

**The cost** (`scripts/rc-aws.sh plan`, us-east-2 on-demand prices read 2026-11-21; sources in `scripts/rc_aws.py`):

| item | rate | 6 hours |
|---|---|---|
| test-chain host c6a.xlarge | $0.1530/h | $0.918 |
| its public IPv4 address | $0.005/h | $0.030 |
| its 40 GB gp3 disk | $0.0044/h | $0.026 |
| SEV-SNP host c6a.large + 10 % SEV-SNP | $0.0842/h | $0.505 |
| its public IPv4 address | $0.005/h | $0.030 |
| S3 (bundle, images, logs; about 2 GB for 7 days) | | $0.011 |
| **total** | | **about $1.52** |

The real-model run (L18 item 4) is a second run, approved separately: about 2 hours of both machines (`plan --hours 2`:
about $0.51) plus the model, estimated at $1.00 and capped at $1.50 by the node's own daily cap (`oracle/spend.py`).
The 8-hour auto-stop bounds a forgotten run at about $2 of compute.

**Before the run (the owner applies; no start yet):**

1. The disk rebuilt with Radicle (`51c96e70…`, "The build's values") uploaded and the kit applied with it (steps 3-5),
   with `bedrock_model_arns` only if the model run follows; the instance created (step 6 makes it; it attests once and
   powers off). The signing key in its secret (step 8.1); its address is `--validator-address`.
2. The test-chain module: `cd validator-kit/sevsnp/testchain && tofu init && tofu apply -var create_instance=true
   -var 'budget_emails=["<the owner>"]'` (its first boot installs Docker and git and stays up only until the run
   stops it; stop it right after the apply: `scripts/rc-aws.sh stop`).
3. The verifier's inputs (step 7): AMD's VLEK chain, AWS's Nitro root, the expected launch measurement for 2 vCPUs.
4. The release candidate's local runs, which need no AWS: `scripts/integration.sh --release-candidate <commit>` (3
   runs in a row; its record is `--record`, written after every run; after a power cut, the same command with
   `--resume` goes on from the record's runs), and the test image and Radicle image built here (`scripts/test-image.sh`,
   `docker build -t pof190-radicle:spike spikes/radicle`): the driver ships exactly those, checked by image ID.

**The run (each command is one approval):**

```bash
export AWS_PROFILE=<the sandbox account's profile>      # region us-east-2
scripts/rc-aws.sh plan                                   # machines, hours, cost; starts nothing
scripts/rc-aws.sh run <commit> --yes-start \
  --validator-address 0x<the SEV-SNP key's address> --manifest validator-kit/sevsnp/out/manifest.json \
  --snp-measurement <96 hex digits> --amd-chain amd-vlek-chain.pem --nitro-root root.pem \
  --record contracts/release-candidates/<tag>.json --out evidence/rc-<tag>
scripts/rc-aws.sh stop                                   # also what every failure runs; harmless when stopped
```

`run`'s steps: preflight (local only); both machines started, the SEV-SNP host's first boot attest-only (its Radicle
node ID and firmware from the console); the commit as a git bundle, the four pinned images (`docker save`: Foundry and
Python by digest, the test image by digest, the Radicle 1.10.3 image) and solc to the module's bucket; provisioning
over SSM (`rc-remote.sh provision`: the bundle's SHA, solc's SHA-256 and every image ID checked); `scripts/integration.sh
--release-candidate <commit> --external` on the test-chain host with `POF_V3_EXTERNAL` = the SEV-SNP key and the
disk's image digest accepted by the deployment (`LOCAL_EXTRA_IMAGE`); the SSM forwards; the SEV-SNP host's user data
from the run's `ready.json` (this plan's step 8 settings plus `ORACLE_REPO`, which `oracle run` requires), a `register`
boot, then a `run --until-idle 3600` boot, each console saved; the external set's `external.json`; `verify.py` on the
judging boot's console (every check must run: a skipped one leaves the items pending); `sevSnpValidator` and
`attestedImages` into the record (`release_candidate.sevsnp_items`: an AWS run of the record's commit on production
windows whose outside key registered as `tee`/`amd-sev-snp` with the manifest's image, which the chain accepted, and
sealed and revealed on a counted panel, and whose Radicle node is the console's); then both stopped.

**The real-model item**, only after `run` passed (its `external.json` is the dry run with the fake judge):

```bash
scripts/rc-aws.sh plan --hours 2 --model-run
scripts/rc-aws.sh model-run <commit> --yes-start --yes-paid-model-run --model direct:bedrock:<model id> \
  --dry-run evidence/rc-<tag>/external.json  (and run's options, --out evidence/rc-<tag>-model)
```

**The dress rehearsal (local Docker, no AWS):** `scripts/rc-aws.sh rehearse <commit>` runs the same run phase against
a local production-windows chain: the external set in the commit's fresh worktree, and the outside validator booted
by a stand-in host from the same user data the driver gives the instance (`pof-config.sh`'s filter, the disk's
`radicle-setup.sh`/`radicle-ready.sh` and the node command as `pof-node.sh` runs it), with the dstack simulator's key in
place of SEV-SNP. Its record step runs on a copy and must keep both items pending (a rehearsal is no SEV-SNP host).

**The rehearsal's result (2026-11-21, commit `58e39a8c`): passed** in 594 s of wall time. The chain was ready after 267 s (v1-v5 qualified by 48 Radicle-claimed registration checks); the outside validator, booted from the driver's user data, registered itself 13 s after ready.json (`simulated`, `amd-sev-snp`, the accepted extra image, family fake-6, bond 250, its own Radicle node); it qualified after 15 more checks (30 shadow seats, 27 revealed in wall time, the clock held at 30 seat deadlines); with v2-v5 paused, counted panel 218 was v1, the outside validator and genesis, and the outside validator's seat was sealed, revealed and receipted and the panel counted (pass, in its window); every harness validator's Radicle node dialled only the seed, outbound. The record step on a copy kept `sevSnpValidator` and `attestedImages` pending (a rehearsal, no verify.py evidence). The first try stopped at the resume after the draw (a capacity above Panels' ceiling); fixed by restoring each one's own capacity.

## The genesis validator on Sepolia (task 7.1; the owner's decision, 2026-11-22)

Sepolia's genesis validator is this host: the measured disk (root hash `51c96e70…`, image digest `0x34cc2415…6ca6b`)
with a **fresh** key in the kit's secret (`signing_key_secret_arn`). Its custody isn't attested ("Open risks"), so the
genesis digest is signed from the secret on the owner's machine, not on the host. `scripts/genesis-validator.sh` does
each step. It reads the key into its own process only (never printed, logged, written to a file or put on a command
line) and prints only the address. AWS calls use the profile `pof-sandbox` (`--profile`); the secret's ARN comes from
the kit's `tofu output` (`--secret-arn` names it instead).

The deployer is task 7.2's fresh wallet. Its address and its nonce when the script runs fix the registry's address,
so both are in the boot's binding and in the digest. Forge first deploys Panels' three linked libraries from the
deployer (through the CREATE2 deployer), so the script runs at the wallet's transaction count + 3 (`--deployer-nonce`,
default 0, + `--libraries`, default 3; 0 only if the same build's libraries already exist on Sepolia). A wallet that
has sent nothing has nonce 0, and the faucet's funding doesn't change that. If the wallet sends anything first, sign
again, and boot again for a bound attestation.

1. **The key:** `scripts/genesis-validator.sh new-key` puts a fresh key straight into the secret (Secrets Manager's
   `PutSecretValue`, signed in the process) and prints its address. It refuses a secret that already holds a key and
   names that key's address. `--replace` puts the new key in its place (Secrets Manager keeps the old one as
   `AWSPREVIOUS`). The host's node reads the same secret, so on Sepolia it runs with this key.
2. **The binding:** `scripts/genesis-validator.sh binding --deployer 0x<deployer>` prints the registry's address and
   `attestNonce`: keccak256 of what the node's own `register` quotes (`proof-of-fix v3 registration`, the registry's
   EIP-712 domain on chain 11155111, the key).
3. **An attested boot** with that nonce: in the kit's tfvars, set `attest_nonce = "<attestNonce>"` and no
   `node_config` (attest only, like `rc-aws.sh`'s first boot; it powers off). Apply, save the console (step 7), and run
   `verify.py` with every check and `--nonce <attestNonce>`, saving its JSON output (`> verify.json`).
4. **The fields:** `scripts/genesis-validator.sh fields --plan plan.json --console console.txt --manifest
   out/manifest.json --verify verify.json --deployer 0x<deployer>` writes the plan's `genesisValidator`:
   - `key`: the secret's address;
   - `operator`: the key's address by default, as the node's `register` does (`--operator` sets another);
   - `teeType`: amd-sev-snp;
   - `level`: 1 (A, a cloud's confidential VM; `--level B` for 2);
   - `attestation`: keccak256 of the boot's SEV-SNP report, as the node hashes its quote;
   - `image`: the manifest's `image_digest`;
   - `host`: keccak256 of `aws:us-east-2`, the kit's ORACLE_HOST_ID (`--host` sets another);
   - `firmware`: the report's REPORTED_TCB (67117025 on 2026-11-22).

   It refuses a `verify.json` with any check skipped or failed, or one from another boot, and a console that fails the
   offline checks when they run again. It also refuses a boot whose nonce isn't step 2's. `--unbound` accepts such a
   boot (for example `evidence/2026-11-22/`), but the attestation then shows only that the measured disk booted, not
   that it booted for this registration. It prints the host's Radicle node (`POF-RADICLE nid`), which goes to the
   deploy as `--genesis-rad-node`.
5. **The digest:** the deploy's dry run (`scripts/deploy-sepolia.sh deploy --plan plan.json … --deployer 0x<deployer>
   --genesis-rad-node did:key:z6Mk…`) refuses without a signature and prints `GENESIS_REGISTRY` and `GENESIS_DIGEST`.
6. **The signature:** `scripts/genesis-validator.sh sign --plan plan.json --deployer 0x<deployer> --genesis-rad-node
   did:key:z6Mk… --digest <GENESIS_DIGEST>` computes the digest the way DeploySepolia.s.sol does and refuses if it
   isn't the dry run's. It signs with the secret's key (refused unless that key is the plan's) and writes `signature`
   into the plan.
7. **The dry run again** passes. The broadcast (task 7.4) waits for the owner's go (7.3).

Tests without AWS: `tests/test_genesis_validator.py` covers the fields from `evidence/2026-11-22/`, the digest rebuilt
from the script's own type string, the signature the deploy's `--genesis-dev-key` path makes, and the key absent from
every output and file. `scripts/deploy-sepolia-e2e.sh` (scenario 4) signs with the tool and runs a dry run on an anvil
with chain id 11155111.

## The node's event scans on Sepolia (#312; the owner's decision, 2026-11-22)

**What happened.** v3 was deployed on Sepolia on 2026-11-22 (first block 12192376, the record's `block`). The genesis
validator's node (`run --until-idle 600`) stopped at its first pass: `Chain.seats()` (the Radicle delegates, read from
the registry's `Registered` events) asked for blocks 0 to 12,192,494 in one `eth_getLogs`, and the provider refused
it (`range 12192494 exceeds limit of 10000`). Every Sepolia provider bounds that range (Infura 10,000 blocks,
publicnode 50,000; the free tiers of Alchemy 10, drpc 100, 1rpc 50); the devnets' short chains never showed it.

**The fix (proof-of-fix#312, oracle only; the contracts are unchanged, their bytecode rc2's).** `Rpc.logs` asks in
chunks of at most `ORACLE_LOG_RANGE` blocks (default 5,000) and halves a chunk a provider refuses as too large (or
takes the smaller limit its message names), keeping that size. The node never scans before the deployment's first
block, `ORACLE_FROM_BLOCK` (unset: found once from RaceV3's start by bisecting block times, about 25 reads), and
reads each block's events once: a pass asks only for the blocks since the last one (and the last 32 again, against a
reorganisation). Both settings go in `node_config` (the disk doesn't fix them, so the user data passes them):

    node_config = { …, ORACLE_FROM_BLOCK = "12192376", ORACLE_LOG_RANGE = "5000" }

`ORACLE_LOG_RANGE` needs setting only below the default, for a stricter provider (`"50"` for 1rpc, `"100"` for drpc's
free tier); the node finds a smaller limit on its own anyway, at the cost of a few refused calls a run. The watcher's
own scan is already bounded (`MAX_BLOCK_RANGE`, 2,000 blocks a run): inside Infura's and publicnode's limits, not the
free tiers' of drpc and 1rpc.

**What follows (the owner, 2026-11-22).** The fix changes the oracle node's image, so the measured disk's image digest
changes, and with it the genesis registration's `image` and the registry's allowed image. In order: rebuild the disk
(`scripts/checker-disk.sh --twice`, new values in "The build's values"), a new release candidate (rc3) on the same
contracts, then a redeploy on Sepolia with a genesis validator registered on the new disk (the steps above again: a
fresh attested boot, its fields and signature), each step at the owner's go.

## The build's values

Recorded by `scripts/checker-disk.sh --twice` on 2026-11-21, with this host's Radicle node (#251 L12, task 4.9): two
builds without the cache gave the same bytes. New on the disk: Radicle 1.10.3 (`rad`, `radicle-node`,
`git-remote-rad`, the release's x86_64 musl build, checked by SHA-256), git, the user `pof` (uid 10001), and the
Radicle units and scripts; the node image also carries main's changes to `oracle/` since `45032ccd`, so its digest
moved too. Booted under QEMU (OVMF, a software TPM, no network but a forwarded IMDS stand-in): it made
the node's key on the data volume and printed `POF-RADICLE nid z6Mk…`, ran radicle-node under its unit's sandbox,
kept the same Node ID on the next boot, and its Radicle steps were done before the images were loaded (below, "Boot
time against the deadlines"). Booted on AWS on 2026-11-22 (steps 4-7: snapshot `snap-094a15e2fa26e0b03`, AMI `ami-036534fb42ef550fe`, instance `i-08d8c5da3711b8909`): `POF-ATTEST ok`, the Radicle node up outbound only (`POF-RADICLE nid z6MkndSS…`), and verify.py passed every check with the 2026-11-20 measurement (`evidence/2026-11-22/`). The attest-only boot with `power_off` true powered off in about 45 s, and a Nitro instance's console isn't readable once stopped: read it with `power_off=false` (step 6) as the first run did.

```
roothash      51c96e70f339696a250bcd64c16ba1a487c91a874b3b1fe79ff0df1cf5875db3
image_digest  0x34cc24150088013c0d0e482998b153dd745168d3cd4877c7ead67e12e198ca6b   (pof-checker-image/1)
pcr4          c86d43a7be3e3018218031afbe2489857936747fdd51644d13a25fbab28363d706afd3d94226523c65c5353385663a39
pcr7          98441c7f7625d10058c47683aec486ce311c633235eb555593a7ee791121e3578ae72d04ecef661f272d59058b77af35
pcr12         000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
sha256 disk.raw      87beb600ca6b9d8e5fda47c89b02bd0578fa58ff238363507346ba5b98e7bc97
sha256 uki.efi       fb255da6fbb129b92d8483bfbfa39c4747773a30872029b7d133508114aaa1b1
sha256 images.json   b2a1cf88d876efea41bc495d32bcb575ed16f35dc3dbba34108f27ca0d9fcb69
sha256 packages.txt  77f2be5592c1febaf698c8e4af6afbd618ee2fa220897e659e9715ec9d8364e9
sha256 pcrs.json     8f0d4b94b771556327c4461916557c13447a357dcfd5bec26236a0c71ee9f071
image node     pof-oracle-node@sha256:e2bd6f377c7e47ec6a01924c44bec5c2017b98b4f335f6e4d858778f46476a4c
image test     pof-test-image@sha256:d950c8ad133bb60d987cbc8eb94cd341a63d175686df8d9a5c5305dbdea05ad5
kernel        6.12.115+deb13.1-cloud-amd64; disk 1 GiB
```

The previous build (2026-11-20, before the Radicle node), recorded after the first run:

Recorded by `scripts/checker-disk.sh --twice` on 2026-11-20, after the first run (two builds without the cache, the
same bytes): the node's `oracle/snp.py` names the host's certificates in the table's byte order (the VLEK prints as
`vlek`), and the node image is built on the test image's Debian base with git pinned from the same snapshot, so a
later build of the same commit makes the same image. Not booted yet, under QEMU or on AWS: the next apply does (steps
3–7). The test image, the kernel and the disk's packages are unchanged, so PCR7 and `packages.txt` are too.

```
roothash      45032ccd5134439301fd4021af43990c0cc79f30a41ee52d703fe72e58801e8e
image_digest  0x0c942f696278d87b009943637415a39eb492df614ea0267f1da448b1a3ccc4be   (pof-checker-image/1)
pcr4          e58ccb120df9f8a1ebd91f12406f11d79270edddb5a9607d17c28c85b03a3441112b89f130730950a0ec10a8fa6bb395
pcr7          98441c7f7625d10058c47683aec486ce311c633235eb555593a7ee791121e3578ae72d04ecef661f272d59058b77af35
pcr12         000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
sha256 disk.raw      967ed090580a3892f4fe793a0cd7f16d5e63867c60e88cbc8c17aca0ba1477d2
sha256 uki.efi       1412b9f9d0bec8789eeea1194232e48ed0db843559231acd5ca22f4f68943c6b
sha256 images.json   091c8511e9b0937b42ec62b48d34bdfb5eb05d40c3631882648d1833a2d4237f
sha256 packages.txt  e44c73644a0f19b4a4dbdc8b7c2e4261c9076cb6dab1e1e0bb6efc8fdfd1923e
sha256 pcrs.json     dfd8d8d04f9ab84a0a49b14f22bb1c6be4442132fda55d34ab3f0112f06f960f
image node     pof-oracle-node@sha256:d08d74aaf4d92bc641f088c8f60f45c6506fd7c9331697435dbc95adea332e6b
image test     pof-test-image@sha256:d950c8ad133bb60d987cbc8eb94cd341a63d175686df8d9a5c5305dbdea05ad5
kernel        6.12.115+deb13.1-cloud-amd64; disk 1 GiB
```

The disk the first run booted (2026-11-20, before the fixes; `evidence/2026-11-20/manifest.json`). Booted under
QEMU's OVMF with a software TPM, it mounted its verity root, loaded both images, refused the unlisted probe and powered
off, and the TPM's PCR4 was this `pcr4` (PCR7 differs there: QEMU's firmware variables aren't AWS's):

```
roothash      c7b72b708666ddeebf81d65cbe80556448ab4dfe598f25b69a8d5c42d07843c8
image_digest  0xe1780f85688d2d762648c4c7c4c883cfa7b7331432aa0ad64e21c329894898f2   (pof-checker-image/1)
pcr4          19125ef7ba109ffa1e2b3a5867dfd8f0b347702228f78bab2dc3278ef91484dbb55f31116017874b9232dbd96c2355cd
pcr7          98441c7f7625d10058c47683aec486ce311c633235eb555593a7ee791121e3578ae72d04ecef661f272d59058b77af35
pcr12         000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
sha256 disk.raw      06c59e4ddc0bdf59fe85ee091563325d0bba49d0a0b013ddd375a131d1df1a1d
sha256 uki.efi       8115d45c8b3c3b004cdc0288d2bdd623cb053aedaed25684a7f0254e902b49ba
sha256 images.json   8d1cb231a3bdc1a02b214da6aea40de2e5957041f6bfc6b39f3aeaf94d59a4df
sha256 packages.txt  e44c73644a0f19b4a4dbdc8b7c2e4261c9076cb6dab1e1e0bb6efc8fdfd1923e
image node     pof-oracle-node@sha256:57a36cf4b966f51775e20b9810870f8ccc70cb79430bb51a65dbcd104aedf8bc
image test     pof-test-image@sha256:d950c8ad133bb60d987cbc8eb94cd341a63d175686df8d9a5c5305dbdea05ad5
kernel        6.12.115+deb13.1-cloud-amd64; disk 1 GiB
```

## Open risks

- ~~**NitroTPM with SEV-SNP on one instance is unconfirmed.**~~ **Confirmed 2026-11-20:** one c6a.large with
  `AmdSevSnp: enabled` and a `tpm_support v2.0` AMI gave both a VLEK-signed SEV-SNP report and a NitroTPM document
  signed to AWS's Nitro root, with PCR4, PCR7 and PCR12 equal to the build's. (Had it said `nitrotpm unavailable`, the
  alternatives were level B on self-hosted SEV-SNP or dstack on TDX, as #253 names.)
- ~~**The node names the host's certificates by GUID in the wrong byte order.**~~ **Fixed 2026-11-20 (disk
  `45032ccd`):** `oracle/snp.py` read the GHCB certificate table's GUIDs with `bytes_le`, so the first run's VLEK
  printed as `c24b07a8-5aa2-3e48-…` instead of `vlek` (`a8074bc2-a25a-483e-…`); it now reads them in the table's order
  (`tests/test_snp.py` replays the first host's bytes). `verify.py` still accepts both, for the first run's evidence.
- **Two roots of trust.** AMD signs the confidential VM's report; AWS's Nitro signs the boot chain's PCRs. A verifier
  trusts AWS for the disk's measurement as it already does for the firmware in the SEV-SNP measurement.
- **AWS's firmware version.** The expected launch measurement depends on the OVMF build AWS runs. If no aws/uefi
  release measures to the report's value, record the observed value as the accepted one and say so (trust on first
  use) until AWS's build is matched.
- ~~**The node image's Alpine `git`**~~ **Fixed 2026-11-20 (disk `45032ccd`):** it was the build's one moving input
  (when Alpine published a new build, the same commit made another node image, so another root hash). The node image
  is now built as the test image is: the same Debian 13 base by digest, git at a pinned version from the same
  snapshot (`oracle/Dockerfile`); nothing else is installed.
- **A restart's boot time isn't measured yet.** The first run measured a launch (below, "Boot time against the
  deadlines"); a start of the stopped instance should be no slower (no first-boot format, the root's blocks already
  read from the snapshot). The next start's console and CloudTrail's `StartInstances` time measure it.
- **The signing key's custody isn't attested.** The key comes from the operator's Secrets Manager; sealing it to the
  measured boot (AWS KMS with the NitroTPM document) is a later step. With one operator at the launch (L23) the
  operator is trusted anyway.
- **The data volume holds state, not code**, but a node that trusts its rounds and spending ledger trusts what an
  operator with the volume could edit; the spending ledger only lowers what the node spends.
- **The Radicle node's key is a file on the data volume** (`/data/state/radicle/keys/radicle`, no passphrase: the node
  signs unattended), made on the first boot and never on the measured disk. Whoever can read the volume (the account's
  operator, or anyone given a snapshot of it) can copy the key and act as this node until the validator registers again:
  push a `main` signed as this delegate, sign or reject an identity revision as it, comment or open patches under its
  name. That is one vote of the delegates: moving the canonical `main` or the delegate set takes 4 of 7 (more than
  half), and `verify-head` and `verify-delegates` catch a `main` that isn't `Heads.head` or delegates that aren't the
  seats even then. The key holds no coins and signs nothing on-chain: the bond, the seals and the reveals are the oracle
  key's. **Compared with the oracle key:** that one comes from Secrets Manager at each start and lives only in the
  node's memory, because it signs seals, reveals and money; the same operator can read it there too, so Secrets Manager
  protects against a leaked snapshot, not against the operator. For the Radicle key the trade goes the other way for
  now: radicle-node and `rad` read it as a file, so it would still be written somewhere at each boot (a tmpfs under
  `/run`), and the host would need the secret before radicle-node starts. **Recommendation:** keep it on the encrypted
  data volume for the launch (one operator, L23), and move it to Secrets Manager (written to a tmpfs at each boot) when
  validators are run by others, or if a key that survives losing the volume is wanted: the data volume has
  `delete_on_termination = true`, so terminating the instance loses the key, and a new key is a new registration (leave,
  then register again with the new `rad self --nid`).
- **No shell.** The host has no SSH, no SSM agent and no getty: the serial console (`get-console-output`) is the only
  view. A boot that fails before `pof-attest` shows only the kernel's and systemd's lines.

## The first run (2026-11-20)

Done in `sandbox-pof-validator` (111111111111), us-east-2, with the profile of step 2, after the owner's approval and
platform PR #228 (step 1).

| | |
|---|---|
| **Disk** | `scripts/checker-disk.sh --twice` from the branch's commit `c10c65b` (manifest `source.is_head: true`): the same root hash `c7b72b70…43c8`, UKI, disk and image digest as "The build's values" |
| **Snapshot** | `snap-04f653f136be65ec9` (coldsnap built in `rust:1`, 1 GiB in about 20 s) |
| **Stack** | first apply: 15 resources (AMI `ami-018be8b575337015b`, VPC, subnet, IGW, SG, role, secret, budget `pof-snp-monthly` $15 with alerts); second apply: 4 (the instance, the budget's stop action and its role and policy). Nothing changed or destroyed. |
| **Instance** | `i-01ede2166387706db`, c6a.large, us-east-2a, default tenancy, `AmdSevSnp: enabled`; launched 19:40:51Z, stopped 19:42:59Z (2 min 8 s), `stopped` since |
| **Console** | every line: `roothash`, `nonce`, `pcrs`, `snp-summary` (signer `vlek`, policy `0x2030000`, VMPL 0, reported TCB bootloader 4, TEE 0, SNP 31, microcode 225), `snp-report`, `snp-cert`, `nitrotpm`, `attested-check` (the unlisted probe refused), `ok` |
| **verify.py** | passed: `roothash`, `nonce`, `snpReportData`, `snpMeasurement` (aws/uefi 20260814), `snpPolicy`, `snpSignature` (VLEK, AMD's Milan chain), `nitroPcrs`, `nitroBinding`, `nitroSignature` (AWS Nitro root `64:1A:03:…:BB:5B`), `imageDigest`, `attestedImages` |
| **snpguest 0.11.0** | ARK self-signed, ASVK by ARK, VLEK by ASVK, the reported TCB matches the VLEK's, the report's signature verifies |
| **Cost** | about $0.02: compute $0.003 (128 s at $0.0842 an hour), EBS direct API puts about $0.012 (2,048 blocks), volumes and IPv4 for minutes. Idle while stopped: about $2.1 a month (20 GiB and 1 GiB gp3 $1.68, the 1 GiB snapshot about $0.05, the secret $0.40); the public IPv4 goes with the stop |

What differed from the steps: coldsnap needed a newer Rust (step 4); the budget's stop is created with the instance,
not before it (step 5); the node started on an attest-only boot (step 6, the Terraform fix); `verify.py` needed three
fixes for the real evidence (EC2's console timestamps and CRs, NitroTPM's indefinite-length CBOR map, the certificate's
GUID in either byte order), each with a test in `tests/test_sevsnp_kit.py`, which also replays this run's evidence. The
stack is left in place, stopped; step 9 removes it. The next apply shows one in-place change: the instance's user data
loses the node's two lines (the Terraform fix).

## Boot time against the deadlines (2026-11-20)

How long an attested host takes from a start call until its node can seal, from the first run's evidence
(`evidence/2026-11-20/`), against the windows a drawn validator has.

**The boot, measured.** The instance's launch time is 19:40:51Z (to the second). The console's lines carry the
kernel's clock; EC2 stamps the wall clock into each long line it splits, and the NitroTPM document carries its own
creation time, so the kernel's start is pinned to 19:41:17.35Z ± 0.1 s (the `snp-report` line, printed at kernel
18.98 s, continued at `[2026-11-20T19:41:36.358374]`; the `snp-cert` line, 19.15 s, at `19:41:36.558384`; the
document's timestamp 19:41:36.767 between kernel 19.15 s and 19.72 s).

| From the start call | seconds | what |
|---|---|---|
| kernel starts | 26.3 | EC2's placement, the SEV-SNP guest's launch, AWS's OVMF, the UKI's EFI stub |
| data volume mounted | 32.0 | kernel + 5.7 s (the first boot formatted it: 0.6 s of that) |
| both images loaded | 41.6 | kernel + 15.2 s (`docker load` of the node and test archives: 9.5 s) |
| `POF-ATTEST ok` | 48.2 | kernel + 21.9 s (the SEV-SNP report, the NitroTPM document, the attested-mode self-test) |
| the node's container running | 49.6 | kernel + 23.3 s (its first line; here it stopped at the empty key secret) |
| **the node can seal** | **≈ 55** | its first pass: the key from Secrets Manager, its registration, one `Seated` scan, the panel's views (a few RPC round trips; estimated, this host had no node configuration) |

An upper bound straight from the evidence: the console that held the node's exit line was read at 19:42:58, 127 s
after the launch. A start of the stopped instance (what the watcher does) skips the first boot's format and the
snapshot's lazy first reads, so it should be no slower; it isn't measured yet (Open risks).

**With this host's Radicle node (2026-11-21): no change expected, about 0 s.** Its three units run beside the images'
load and the attestation, not before them: the node service (`pof-node.service`) waits for both the attestation and
`pof-radicle-ready.service`, and under QEMU the Radicle steps ended first every time. Attest only (first boot, key
made): the Node ID at kernel 4.8 s, radicle-node running at 5.1 s, the images loaded at 11.4 s, `POF-ATTEST` at 11.5 s.
With the seed configured but refusing (a restart, the same key): the ready step gave up in 37 ms (`rad sync` finds no
connected seed at once; no working copy, since this volume never fetched the repository) and the boot went on as before.
With a seed reachable (the internal-network test's, through QEMU's forwarding): ready in 0.9 s on a first boot, 0.3 s on
a restart ("Radicle under QEMU", below). On EC2 the attestation is the slow branch (kernel + 21.9 s); the Radicle branch
is the key (made once), radicle-node's start (0.16–0.47 s in the Docker test) and a sync with the seed (0.3–1.0 s there,
plus the Internet's round trips to the seed, and the first boot's full fetch of the repository). The sync is capped at
30 s and the working copy comes from local storage, so even a slow seed adds at most about 30 − (21.9 − 5) ≈ 13 s to the
55 s, and only then. So a drawn validator still seals about 127 s after its draw at worst (Sepolia's seal window: 7,200
s).

**Radicle under QEMU (2026-11-21, disk `51c96e70`).** Four boots of the measured disk under QEMU/KVM (OVMF, a
software TPM, NVMe disks, slirp with no route out; user data from an IMDS stand-in), times on the guest's kernel clock:

| boot | key | radicle-node's ready step | images loaded | `POF-ATTEST roothash` |
|---|---|---|---|---|
| attest only, blank data volume | made, nid at 4.8 s | 5.1 s: running, no repository | 11.4 s | 11.5 s |
| seed configured but refusing, same volume | kept (same nid) | 4.7 s: no working copy after 37 ms | 10.3 s | 10.3 s |
| the internal-network test's seed, blank volume | made, nid at 4.6 s | 6.3 s: fetched and checked out in 912 ms | 10.4 s | 10.4 s |
| the same seed, a restart on that volume | kept (same nid) | 4.7 s: synced and checked out in 306 ms | 9.2 s | 9.2 s |

The seed's log shows only inbound sessions from that node; at the restart it closed the stopped boot's stale session
("Closing conflicting session") and served the new one, as it will for an instance stopped without closing its
connection. The node container didn't run (QEMU has no SEV-SNP, so the boot doesn't attest); its path to the Radicle
node is the internal-network test's.

**Seeing the draw.** The watcher runs once a minute (EventBridge's shortest schedule): a `Seated` event is seen up to
60 s after its block, plus the RPC's lag (up to a block, 12 s on Sepolia) and the Lambda's run (about a second). So
from the draw to a node that can seal: about 60 + 12 + 55 ≈ **127 s at worst** (199 s with the evidence's 127 s bound
in place of 55 s).

| A drawn validator's windows | production (`WindowsLib.production`, what `DeploySepolia.s.sol` deploys) | minutes (`inMinutes()`: a devnet with `DEVNET_V3_WINDOWS=minutes`, the Foundry short run) |
|---|---|---|
| seal (`SEAL_WINDOW`, from the draw or a replacement's seat) | 7,200 s | 120 s |
| reveal (`REVEAL_WINDOW`, after `sealBy`, once every seat sealed) | 3,600 s | 60 s |
| a cold start's share of the seal window (127 s; 199 s bound) | 1.8 % (2.8 %) | 106 % (166 %): the window closes first |
| what's left of the seal window after the check | ≈ 4,370 s (73 min): 7,200 − 127 − 2,400 (Sepolia's profile, `timeoutSeconds` for the two test runs) − about 300 (the fix's fetch and the model call) | nothing |
| the reveal | the node holds the instance up while its seat is open (an open seat isn't idleness), so it reveals within its 2 s poll of the window opening; after a crash the watcher restarts it, worst 127 s (3.5 %) of 3,600 s | only a node that stayed up |

**Production windows (Sepolia): the margin is wide; nothing to fix.** A cold start uses under 3 % of the seal window,
and over an hour is left after the longest check the Sepolia profile allows. A replacement seat gets a fresh seal
window (`resetTimeline`), so the same holds. No contract or window change is needed or proposed.

**Minute windows: a cold start can't make a 120 s seal window**, before the check even starts, and a faster poll
wouldn't change that: at a zero-second poll the boot alone leaves under a minute for two test runs and a model call.
The smallest fix needs no contract change: **keep the host warm for a minute-windows run.** Start it before the run
with `node_command = "run --until-idle <the run's length in seconds>"` (the disk's `pof-node.sh` accepts it; a user
data change restarts the instance), so the node holds its seats from the draw; or run release-candidate item 3 on a
devnet with production windows (`scripts/devnet.sh`'s default, `DEVNET_V3_WINDOWS=production`). The watcher marks any
seal start with less than `ready_seconds` (120 s) left as `"late": true` in its log, so a minute-windows deployment
shows at once. Sepolia keeps production windows (L4), so this affects devnet runs only.

**What it costs.** The node can't reveal before `sealBy` (Panels refuses an early reveal), and it holds the instance
up while its seat is open, so each seat keeps the c6a.large running from the draw through the reveal: about 2 h with
production windows, about $0.17 at $0.0842 an hour, plus 10 idle minutes. `max_starts_per_day` (12) and the node's
capacity (5 seats an hour, `Panels.capacity`) bound it.
