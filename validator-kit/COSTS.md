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

## With attestation later

Nitro Enclaves don't run on burstable instances: the attested node needs a **c6g.xlarge (about $0.136 an hour)** or
similar, so a 12-minute run costs about $0.03. That's the overhead `reports/self-healing-v1.md` sized `SERVICE_FEE`
against ($0.0119 per counted check at its volumes).
