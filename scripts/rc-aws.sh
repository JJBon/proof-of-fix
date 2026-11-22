#!/usr/bin/env bash
# The release candidate's real-SEV-SNP items on a temporary AWS test chain (proof-of-fix#251 task 7.0; design L18 items
# 3, 4 and 6; the owner's decision of 2026-11-21): one c6a.xlarge beside the SEV-SNP host in the kit's VPC
# (validator-kit/sevsnp/testchain) runs the chain on production windows with the moved clock, the Radicle seed and the
# six other validators; this machine reaches it only through SSM. Both machines stop after the run, on any failure and
# on an interrupt. The steps and the cost: validator-kit/SEVSNP-PLAN.md, "The release candidate's run (task 7.0)".
#
#   scripts/rc-aws.sh plan [--hours 6] [--model-run]     the machines, hours and cost; starts nothing, no AWS call
#   scripts/rc-aws.sh start --yes-start                  start both machines (the SEV-SNP host: one attest-only boot)
#   scripts/rc-aws.sh run <commit> --yes-start --validator-address 0x… --manifest FILE --snp-measurement HEX \
#                         --amd-chain FILE --nitro-root FILE --record FILE
#                                                        the run: start, provision, the external set, the SEV-SNP
#                                                        host's register and judging boots, verify.py, the record, stop
#   scripts/rc-aws.sh model-run <commit> --yes-start --yes-paid-model-run --model direct:bedrock:<id> \
#                         --dry-run <run's external.json> (and run's options)
#                                                        the real-model item, after a passed fake-judge run
#   scripts/rc-aws.sh stop                               stop both machines
#   scripts/rc-aws.sh rehearse <commit>                  the dress rehearsal on local Docker (no AWS)
#   scripts/rc-aws.sh record --record F --external F --verify F --manifest F --evidence DIR
#
# The options and every step: scripts/rc_aws.py. AWS_PROFILE (or --profile) names the sandbox account's profile; the
# region is us-east-2; account-specific values come from the two modules' outputs (local state).
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $# -ge 1 ]] || { sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
exec python3 scripts/rc_aws.py "$@"
