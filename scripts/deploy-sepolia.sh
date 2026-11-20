#!/usr/bin/env bash
# v3 on Sepolia (proof-of-fix#251, task 3.9; design L3): a dry run unless --broadcast-sepolia names the step. It reads
# the endpoint's chain id before signing anything (11155111 only; 31337 and 7193 only on a local endpoint), checks the
# release-candidate record (L18) and the Radicle genesis head (pofctl verify-head), simulates with forge, and writes the
# deployment record. See scripts/deploy_sepolia.py for the checks, the plan and the record formats.
#   scripts/deploy-sepolia.sh deploy --rpc-url URL --plan plan.json --release-candidate rc.json [--deployer 0x…]
#   scripts/deploy-sepolia.sh deploy … --keystore key.json --broadcast-sepolia      (the owner's go first: task 7.3)
#   scripts/deploy-sepolia.sh hashes                                                (for a release-candidate record)
# scripts/deploy-sepolia-e2e.sh runs it against local anvils (chain ids 1 and 11155111).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/deploy_sepolia.py "$@"
