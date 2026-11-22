# validator-kit: run a proof-of-fix validator in your own AWS account (proof-of-fix#104)

The demo's main proof: **an engineer runs the AI check on their own infrastructure, and the smart contract pays them
when their check counts.** This kit is what that engineer applies. It has run for real: on 2026-11-04 the owner's validator
judged a failing fix and a correct one on the AWS devnet, with Claude through Bedrock (#150).
The demo's repository (whose pull requests claim the submissions) can be on GitHub (the default) or on a Forgejo
(`forge = "forgejo"`, `forge_url`: the runbook's "A Forgejo target", #112).

| | |
|---|---|
| [`runbook.md`](runbook.md) | prerequisites, your keys, apply, join as a seat, verify, fees, tear down, follow-ups |
| [`COSTS.md`](COSTS.md) | about $2–3 a month idle; well under a cent of compute per check; the $0.05 service fee |
| [`terraform/`](terraform/) | the module (OpenTofu or Terraform ≥ 1.6, aws ~> 6.68): a small VPC with no inbound and no NAT, a Graviton node instance that's **normally stopped**, a **watcher Lambda** that starts it only when a submission is sealed, your signing key in **your** Secrets Manager (written by you, never by Terraform), least-privilege Bedrock access to the models you choose (or any provider's API key: the node calls its model directly, #118), logs, a budget alarm, and a kill switch |
| [`lambda/watcher.py`](lambda/watcher.py) | the watcher (Python 3.12 in Lambda; tested on 3.9 with fakes in `tests/test_validator_kit.py`) |

**Your limits.** A validator takes work from the contract with no approval per job, so these limit a bad day: the node's
guards per run, `max_starts_per_day` (default 12) and `budget_stop` (at 100 % of `budget_limit_usd`, it blocks model calls and
new starts until you reverse it). `enabled = false` is the kill switch. Details: the runbook's "Spending guards".

**v3:** this kit is for v2's 7 seats. v3 replaces joining a seat with registering a bond and an attestation (#139, not built).

## The SEV-SNP kit (v3, #253; #251 L18 item 3 and L21)

[`sevsnp/`](sevsnp/) runs a v3 validator on an AMD SEV-SNP instance from **one measured, read-only disk**, beside v2's
kit (which is unchanged). [`SEVSNP-PLAN.md`](SEVSNP-PLAN.md) is the order of the steps and what they cost.

| | |
|---|---|
| [`sevsnp/disk/`](sevsnp/disk/) | the checker disk (`scripts/checker-disk.sh` builds it, `--twice` checks two builds give the same root hash): Debian 13 from one snapshot, the Docker engine, the node image and the test image as archives, `images.json`; an EROFS root under dm-verity, its root hash on the kernel command line inside a UKI; no SSH, no SSM agent, no cloud-init |
| [`sevsnp/terraform/`](sevsnp/terraform/) | the disk as a UEFI AMI with NitroTPM, a c6a.large launched with `AmdSevSnp=enabled` (only when `create_instance = true`), a data volume, your signing key's secret, least-privilege IAM, a budget whose 100 % stops the instance |
| [`sevsnp/lambda/watcher.py`](sevsnp/lambda/watcher.py) | v3's watcher, a Lambda run every minute (with the instance; off until `watcher_enabled`): it reads Panels' `Seated` events for your key (counted, shadow, audit, challenge and replacement seats) and their views, and starts the stopped instance only for a seal or a reveal that needs the node, with v2's fuse, kill switch and logs, retries per seat, no seal work while the node's capacity is 0 (its spending pause), a daily start to end that pause, and no start while the budget's stop holds; its IAM may start this instance only |
| [`sevsnp/verify.py`](sevsnp/verify.py) | checks a boot's evidence (the serial console's `POF-ATTEST` lines) against the build: root hash, the SEV-SNP report's data, measurement, policy and AMD signature, NitroTPM's PCRs, binding and Nitro signature, the image digest, attested mode |

**Its Radicle node (#251 L11, L12; launch validators run model (a)).** The disk carries Radicle 1.10.3 (pinned by
SHA-256, the release the seed pins) and runs `radicle-node` as its own service (`pof-radicle.service`, as the node
container's user) before the node starts. Its key is made once on the data volume (`/data/state/radicle`), never on the
measured disk; the boot prints its Node ID (`rad self --nid`) on the serial console (`POF-RADICLE nid z6Mk…`), and
`register --rad-node <that nid>` signs that key into the registration (`radNodeOf`). It is **outbound only**: it listens
on no port and, with static peers, dials only the seed in `radicle_seed` (the user data's `POF_RADICLE_SEED`), never
Radicle's public bootstrap nodes (dynamic peers would: radicle-node 1.10.3 on the main network, given no network, tried iris and rosa.radicle.network, 5 s per failed lookup; static peers tried none); patches, issues and the
delegates' signed `main` travel both ways over that connection, so the security group still opens no inbound port
(egress 8776 is added). The node container reaches it through its control socket on the same storage
(`ORACLE_RADICLE_EXEC` empty). With `ORACLE_MERGE_VIA = "radicle"` the watcher also starts the host once each time
`Heads.head` moves, so this delegate pushes the canonical `main` even when it wasn't drawn for the fix. Tested on the
internal Docker network with the seed's and the disk's own Radicle config: `scripts/kit-radicle.sh`
(`tests/integration/kit_radicle.py`).

**How far AWS's SEV-SNP measurement reaches: the firmware only.** The report's MEASUREMENT is "a cryptographic hash of
the initial guest memory contents and initial vCPU state", which validates "the initial boot code that was used to
launch the instance" ([AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snp-attestation.html)). On EC2 that is
AWS's UEFI firmware (OVMF): AWS publishes it to be rebuilt and measured with `sev-snp-measure --mode snp --vmm-type ec2
--vcpus N --ovmf ovmf_img.fd` ([aws/uefi](https://github.com/aws/uefi)), and the kernel, initrd and command line enter
a launch measurement only when the VMM loads them directly (`--kernel/--initrd/--append`,
[sev-snp-measure](https://github.com/virtee/sev-snp-measure)), which EC2 doesn't offer. AWS names no measured boot of
the AMI in its SEV-SNP pages.

**How the boot measures the disk: NitroTPM.** NitroTPM gives measured boot into PCRs and a signed attestation document
([NitroTPM](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/nitrotpm.html)); AWS's own "Attestable AMI" uses a UKI,
a dm-verity root and `nitro-tpm-pcr-compute` for the expected PCR4, 7 and 12
([attestable AMIs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/attestable-ami.html)), and the document is
COSE_Sign1, signed by AWS's Nitro attestation PKI
([validate](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/nitrotpm-attestation-document-validate.html)). The
kit's chain: the firmware measures the UKI into PCR4; the UKI's command line names the root hash; dm-verity refuses
any block of the root that doesn't hash to it. Each boot prints the SEV-SNP report (its report data binds the nonce and
the root hash) and the NitroTPM document (its user data is the report's sha384, its nonce the same): one boot, one
disk. The checker image's digest on Validators' list is sha256 of `pof-checker-image/1` (PCR4, PCR7, PCR12, the root
hash). Two roots of trust, then: AMD for the confidential VM and AWS's firmware, AWS's Nitro for the boot chain. Locally,
under QEMU's OVMF with a software TPM, the disk boots and the TPM's PCR4 equals `nitro-tpm-pcr-compute`'s; whether
NitroTPM and SEV-SNP run together on one instance is the first thing the plan's test host shows (AWS's pages don't say).

**Attested mode** (`oracle/sandbox.py`): the node gets the disk's `images.json`, never pulls, and refuses to create a
container whose image isn't listed at its digest: a setup error, so the node stops. **Spending caps**
(`oracle/spend.py`): a daily and a monthly model-spend limit in the node ($0.50 and $5 by default: 7 validators spend at
most $35 a month), and at a cap the node pauses itself on-chain (`Panels.setCapacity(key, 0)`) until the next period.

**Why an instance and not Fargate:** each fix's tests run in a container with no network (rule 4), which needs a Docker
daemon. Fargate has none, and containers in one Fargate task share a network. Nitro Enclaves, for the attested node
later, run on EC2 only.

**On a devnet, end to end:** `scripts/demo-e2e.sh` joins a new engineer's key as a seat and runs seven real nodes
(only the drawn act), with metered fees paid and withdrawn; `scripts/first-run-e2e.sh` runs the runbook's "The first real
run" on a throwaway copy of the AWS devnet. The judges meet through the hosted relay (`exchange_url`, `docs/exchange.md`). The
node starts each fix's tests in
a sibling container through the instance's Docker socket (#116; the runbook's "The sandbox and its trust boundary").
