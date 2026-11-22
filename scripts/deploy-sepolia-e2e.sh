#!/usr/bin/env bash
# The Sepolia deploy script against local anvils (proof-of-fix#251, task 3.9): chain id 1 (refused, nothing sent),
# 11155111 with a wrong genesis head (refused), with a contract that differs from the release candidate (refused),
# 11155111 with the right head (a dry run, then a full local deployment and its record), and 31337 (the mock coin).
# anvil runs in the pinned Foundry image on 127.0.0.1 only, with its public test keys; forge runs in the same
# container. No public endpoint. The containers and records are removed when it ends, pass or fail.
#   scripts/deploy-sepolia-e2e.sh   (POF_DEPLOY_E2E_PORT picks the port, default 8561; POF_DEPLOY_E2E_KEEP=1 keeps them)
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/solc.sh
source scripts/solc.sh
[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
exec python3 tests/e2e_deploy_sepolia.py "$@"
