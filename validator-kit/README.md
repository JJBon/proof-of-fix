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

**Why an instance and not Fargate:** each fix's tests run in a container with no network (rule 4), which needs a Docker
daemon. Fargate has none, and containers in one Fargate task share a network. Nitro Enclaves, for the attested node
later, run on EC2 only.

**On a devnet, end to end:** `scripts/demo-e2e.sh` joins a new engineer's key as a seat and runs seven real nodes
(only the drawn act), with metered fees paid and withdrawn; `scripts/first-run-e2e.sh` runs the runbook's "The first real
run" on a throwaway copy of the AWS devnet. The judges meet through the hosted relay (`exchange_url`, `docs/exchange.md`). The
node starts each fix's tests in
a sibling container through the instance's Docker socket (#116; the runbook's "The sandbox and its trust boundary").
