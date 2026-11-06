#!/usr/bin/env bash
# pofctl end to end (proof-of-fix#104): a throwaway devnet beside any other (its own name, port, state and records),
# v2 deployed with anvil's public test keys, and tests/e2e_pofctl.py driving every role through pofctl against a fake
# GitHub on the loopback. The devnet and its files are removed when it ends, pass or fail. Never a public chain (rule 1).
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVNET_NAME=pof-devnet-e2e DEVNET_PORT=${POFCTL_E2E_PORT:-8549} DEVNET_STATE=.devnet-e2e \
  DEVNET_RECORD=contracts/deployments/e2e/devnet.json DEVNET_RECORD_V2=contracts/deployments/e2e/devnet-v2.json \
  DEVNET_KEYS=insecure-local
cleanup() { scripts/devnet.sh down >/dev/null 2>&1 || true; rm -rf .devnet-e2e contracts/deployments/e2e; }
trap cleanup EXIT
cleanup
mkdir -p contracts/deployments/e2e
scripts/devnet.sh up
scripts/devnet.sh deploy-v2 >/dev/null
python3 tests/e2e_pofctl.py --rpc "http://127.0.0.1:$DEVNET_PORT" --record "$DEVNET_RECORD_V2"
