#!/usr/bin/env bash
# The Sepolia genesis validator (proof-of-fix#251, task 7.1): a fresh key into the SEV-SNP kit's secret, the boot nonce
# that binds an attested boot to it, the plan's genesisValidator fields from that boot, and the genesis signature from
# the secret. The key is never printed, logged, written to a file or put on a command line; only its address is shown.
#   scripts/genesis-validator.sh new-key [--replace] [--kit-dir DIR | --secret-arn ARN]
#   scripts/genesis-validator.sh binding --deployer 0x… [--deployer-nonce 0]
#   scripts/genesis-validator.sh fields --plan plan.json --console console.txt --manifest manifest.json --verify verify.json --deployer 0x…
#   scripts/genesis-validator.sh sign --plan plan.json --deployer 0x… --genesis-rad-node did:key:z6Mk… [--digest 0x…]
# See scripts/genesis_validator.py for the checks; validator-kit/SEVSNP-PLAN.md, "The genesis validator on Sepolia".
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/genesis_validator.py "$@"
