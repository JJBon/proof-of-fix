# What a validator costs to run (proof-of-fix#104)

Rough figures for us-east-1, from AWS's public prices as used in `reports/self-healing-v1.md` (2026-11) and the B2 cost
model (`reports/costs-v1.md`). Check current prices before relying on them.

## Idle: about $2–3 a month

| Item | Cost | Note |
|---|---|---|
| Root volume, 20 GB gp3, kept while stopped | $1.60 | $0.08 per GB-month |
| Secrets Manager: the signing key, plus the chain's API key and a model API key if you use them | $0.40–1.20 | $0.40 per secret a month |
| Watcher Lambda, once a minute (43,200 runs, about 0.2 s at 128 MB) | about $0.03 | inside the free tier for most accounts |
| EventBridge schedule, SSM parameter, VPC, internet gateway | $0 | standard parameter; no NAT gateway |
| CloudWatch Logs | cents | 14-day retention |
| Public IPv4 address | $0 idle | $0.005 an hour only while the instance runs |
| **Total** | **about $2–3** | the simulation assumed $4.67 with an always-on t4g.nano watcher; a Lambda is cheaper |

## Per run and per check

- **The instance,** t4g.small at about **$0.0168 an hour**: one run (boot, the checks, then `--until-idle 600` seconds of
  quiet before it powers off) of about 12 minutes costs **about $0.004**, plus about $0.001 of public IPv4. A run
  checks every submission sealed meanwhile, so the cost per check falls as volume rises.
- **The model** is passed through by the contract (check gas, design S15): about **$0.02–0.12 per verdict** for one
  judge, depending on the model (B2). You pay your provider and the contract pays you back at the price table's rates,
  measured from the receipt (the provider's own token counts, #118). The node's spending guards cap one run: 4,000
  tokens out per verdict, 20 calls, 500,000 tokens in all (`max_output_tokens`, `max_model_calls`, `max_run_tokens`).
- **The tests' sandbox** is the same instance: no extra cost.
- **Gas** for your sealed verdict and its reveal is repaid at cost (S15).

## What you earn

The agreed **`SERVICE_FEE` of $0.05 per counted check** (#100, #105), on top of the passed-through costs. With an
on-demand t4g.small the overhead per check is well under a cent once runs batch several checks, so the fee covers it at
any volume where a run sees more than one check. The simulation's break-even (about 55 network checks a week, for an
always-on watcher and an enclave-capable instance) is the conservative figure.

## Limits across runs

The guards above are per run, and runs can repeat. `max_starts_per_day` (default 12) bounds a day: 12 x 20 calls x $0.12 is
about $29 at the dearest verdict above. `budget_stop` blocks spending at 100 % of `budget_limit_usd`, but AWS's cost data
arrives hours late, so it can overshoot. See the runbook's "Spending guards".

## In v3 (simulated, not built)

v3's fee follows the market instead of a fixed $0.05. In the simulation it settles at about $0.21 a check, and an honest
validator nets **−$1.43 ± 0.22 a month at 30 submissions a week and +$4.77 ± 0.31 at 100** (`reports/open-validators-v3.md`).
Model calls are passed through, so the shortfall at low traffic is overheads against the fee. It's open as #141, and blocks
v3's contracts.

## With attestation later

Nitro Enclaves don't run on burstable instances: the attested node needs a **c6g.xlarge (about $0.136 an hour)** or
similar, so a 12-minute run costs about $0.03. That's the overhead `reports/self-healing-v1.md` sized `SERVICE_FEE`
against ($0.0119 per counted check at its volumes).

## The SEV-SNP kit (#253, `sevsnp/`)

Prices from AWS's Price List API on 2026-11-20 (us-east-2, Linux, on demand, shared tenancy); SEV-SNP adds 10 % of the
on-demand price on shared tenancy ([AWS](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/sev-snp.html)).

| Item | Cost | Note |
|---|---|---|
| c6a.large (2 vCPUs, 4 GiB) | $0.0765 + 10 % = **$0.0842 an hour** while running | m6a.large: $0.0864 + 10 % = $0.0950 |
| Public IPv4 | $0.005 an hour while running | |
| The measured disk's root volume, 1 GiB gp3 | $0.08 a month | its snapshot: about $0.02 (only written blocks) |
| The data volume, 20 GiB gp3 | $1.60 a month | the node's state; scratch wiped at each boot |
| The signing key's secret | $0.40 a month | |
| **Idle (stopped), the watcher off** | **about $2.10 a month** | |
| The v3 watcher, enabled | about $0.12 a month | Lambda once a minute, logs |
| The RPC URL in a secret (`rpc_url_secret_arn`) | about $0.62 a month | the second secret ($0.40) and the watcher's reads of it, one a run (~43,800 a month, $0.22) |
| **Idle with the watcher and the RPC URL's secret** | **about $2.85 a month** | |

A run of the node (boot, attest, checks, ten idle minutes) of about 15 minutes costs about $0.022. A Dedicated Host
(the only SEV-SNP option in us-east-1) is $8.078 an hour for a c6a host: not used.

**The model** is capped in the node: `ORACLE_SPEND_DAILY_USD` (default $0.50) and `ORACLE_SPEND_MONTHLY_USD` (default
$5) across runs, so the owner's 7 launch validators spend at most $35 a month on models together, inside #253's
$30-50; at 15 validators set $3 each ($45). At a cap the node makes no call (the seat stays silent) and sets its
capacity to 0 on-chain until the next day or month.
