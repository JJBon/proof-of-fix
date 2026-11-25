# seed: proof-of-fix's Radicle seed (#251 design L14)

One small always-on VM running a Radicle seed node whose selective policy serves proof-of-fix's repository and refuses
every other one. Decided by the owner on 2026-11-20: an AWS instance in the project's sandbox account, us-east-2 (the
SEV-SNP kit's account), at about $6–10 a month; started only after the Radicle publish (task 6.2), when the owner says
so (task 6.3). Public community seeds may also replicate proof-of-fix; the launch doesn't depend on them.

| | |
|---|---|
| [`radicle/config.json`](radicle/config.json) | the node's config: seeding policy `block` by default, listening on 8776, its external address; `@ALIAS@`, `@EXTERNAL_ADDRESS@`, `@NETWORK@` filled in by the setup |
| [`radicle/seed-setup.sh`](radicle/seed-setup.sh) | the node's key (made once), the config, and the one seeding policy: `rad seed <RID> --scope all`, everything else unseeded |
| [`radicle/radicle-seed.service`](radicle/radicle-seed.service) | radicle-node as a systemd service, as its own user, sandboxed to `/var/lib/radicle` |
| [`radicle/install.sh`](radicle/install.sh) | the host's install, run by cloud-init: the data volume, Radicle 1.10.3 by SHA-256, the setup, the service |
| [`publication.py`](publication.py) | the publication record (`pof-radicle-publication/1`), the only source of the RID |
| [`terraform/`](terraform/) | the instance (`create_instance = false` by default), its volumes, Elastic IP, security group, role and budget |

**Why a folder of its own.** The seed isn't a validator, so it doesn't belong in `validator-kit/`; and everything it
needs, the Radicle files shared by the host and the test, the record's format and the Terraform, sits in one folder
that goes into the public snapshot as it is (task 5.2): it names no account, profile, domain or person, and the account
comes from your AWS credentials.

**Tested** on the internal Docker network: `scripts/radicle-spike.sh --seed` (`tests/integration/seed_radicle.py`)
runs `seed-setup.sh` and the service's `ExecStart` in a container with the spike's pinned Radicle 1.10.3. The seed
replicates proof-of-fix (this repository's tracked files as one root commit) from a publishing node, never fetches a
second repository the publisher announces straight to it, and serves proof-of-fix to a fresh node connected only to
it, with the publisher stopped; the fresh node's clone of the second repository from it fails. `tests/test_seed.py`
checks the files without Docker. `install.sh` itself first runs on the real host (task 6.3).

## The RID: from the publication record only

Nothing here names proof-of-fix's RID before the publish. Task 6.2's `rad init` writes the record:

```json
{"format": "pof-radicle-publication/1", "rid": "rad:z…", "rootCommit": "<40-hex SHA-1>", "nodeId": "z6Mk…",
 "radicle": "1.10.3"}
```

Terraform reads it from `publication_record` and refuses to create the instance without a valid one (or with another
Radicle release than the pinned one). To see the RID it will use: `python3 seed/publication.py rid <record>`. To change
it, write the new record and apply again: the instance is replaced (its user data changed), the data volume keeps the
node's key, and the setup unseeds the old RID.

## Applying it (after task 6.2, on the owner's word for 6.3)

**Warning: `create_instance` defaults to `false`. Once the seed runs, a `tofu plan` or `tofu apply` without
`create_instance = true` destroys the seed: its instance, its data volume (the node's key: a new one is a new Node ID)
and its Elastic IP (its address).** Keep the values in a `seed.tfvars` copied from
[`terraform/seed.tfvars.example`](terraform/seed.tfvars.example), which sets `create_instance = true` and
`ssm_access = true`, and pass `-var-file=seed.tfvars` to every plan and apply. `seed.tfvars`, saved plans and the state
are git-ignored (`terraform/.gitignore`); never commit them.

OpenTofu (or Terraform ≥ 1.6), credentials for the sandbox account in your environment (`AWS_PROFILE`):

```bash
cd seed/terraform
cp seed.tfvars.example seed.tfvars     # publication_record, budget_emails; create_instance = true stays
tofu init
tofu plan -var-file=seed.tfvars        # the first time: the instance, its volume and address are created
tofu apply -var-file=seed.tfvars
tofu output public_ip
```

The first boot formats the data volume, downloads Radicle 1.10.3 for aarch64 and refuses it unless its SHA-256 is
`822c1ea1…596f` (the release's own `.sha256`), runs the setup and starts `radicle-seed`. Without `create_instance =
true` the apply makes only what costs nothing: the VPC, the security group, the role and the budget.

On the host (`tofu output session_command`, Session Manager; there is no SSH and no inbound port but 8776):

```bash
sudo -u radicle RAD_HOME=/var/lib/radicle/home rad self --nid   # the seed's Node ID
sudo -u radicle RAD_HOME=/var/lib/radicle/home rad seed         # exactly one policy: the RID
journalctl -u radicle-seed
```

Every later change goes through the same `-var-file=seed.tfvars` (the warning above). To remove it on purpose:
`tofu apply -var-file=seed.tfvars -var create_instance=false` (the instance, its volume and its address go; a new one
gets a new Node ID and address), or `tofu destroy -var-file=seed.tfvars`.

## The keeper on the same host (the owner's approval, 2026-11-23)

The host may also run a keeper-only v3 node (`oracle/keeper.py`, as the `pof-keeper` systemd unit). It reads two
secrets with the seed's role: its account's key and its own RPC URL (a key of its own, not a validator's). The role
gets `secretsmanager:GetSecretValue` on exactly the ARNs in `keeper_secret_arns` (Secrets Manager secret ARNs only,
with their random suffix; anything else is refused at plan time) and nothing else; empty, the default, adds no policy.
The seed itself reads no secret.

## Checking it from a fresh node

On another machine with Radicle 1.10.3 and a fresh identity, with `NID` the seed's Node ID and `IP` its address:

```bash
rad node connect NID@IP:8776
rad clone RID pof --seed NID          # works: HEAD is the record's rootCommit
git -C pof rev-list --max-parents=0 HEAD
rad clone <any other RID> x --seed NID  # fails: the seed doesn't have it
rad node routing --rid RID            # the seed is listed as seeding it
```

That is task 6.3's verify line; the explorer check is 6.4.

## The instance: t4g.micro

In the seed's test radicle-node used 8 MiB of resident memory idle, 14 MiB after replicating and serving proof-of-fix,
and peaked at 45 MiB (`.seed-radicle/results.json`, `seedMemoryKiB`). Beside it the host runs Amazon Linux 2023, the
Session Manager agent, and `git` processes radicle-node starts to serve each clone. A t4g.micro (2 burstable vCPUs,
1 GiB) leaves ample room for all of that; a t4g.nano (0.5 GiB) would run radicle-node but with little headroom for the
system, the agent and concurrent clones, to save about $3 a month. A t4g.small (2 GiB) is more than the seed needs.
The instance uses standard CPU credits, so a busy hour is throttled rather than billed.

## The monthly cost (us-east-2, prices of 2026-11-20)

| Item | Price | A month (730 h) |
|---|---|---|
| t4g.micro, Linux, on demand | $0.0084 an hour | $6.13 |
| Public IPv4 (the Elastic IP, in use) | $0.005 an hour | $3.65 |
| Root volume, gp3, 8 GiB | $0.08 per GB-month | $0.64 |
| Data volume, gp3, 2 GiB | $0.08 per GB-month | $0.16 |
| **Total** | | **$10.58** |

Data transferred out to other nodes is billed beyond AWS's free allowance; a clone of proof-of-fix moves about 5 MB.
The total is a little above the decision's $6–10 because the public IPv4 alone is $3.65; with a t4g.nano it would be
about $7.52. Sources: [EC2 on-demand pricing](https://aws.amazon.com/ec2/pricing/on-demand/) (t4g.micro, US East
(Ohio), Linux), [EBS pricing](https://aws.amazon.com/ebs/pricing/) (gp3 storage), [VPC
pricing](https://aws.amazon.com/vpc/pricing/) (public IPv4 addresses), read from the price lists behind those pages on
2026-11-20.

**The budget alerts, and doesn't stop the seed.** `budget_limit_usd` (default $15) alerts `budget_emails` at 80 % of
actual and 100 % of forecast spend. Unlike the SEV-SNP kit, there is no automatic stop: the seed's cost is fixed by
design, so an overrun points at something else in the account (the budget sees the whole account, like the SEV-SNP
kit's) or at unexpected traffic, and stopping the seed would take proof-of-fix offline for everyone fetching through
it. The owner decides; `create_instance = false` removes what the seed costs.
