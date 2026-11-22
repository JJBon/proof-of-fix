#!/usr/bin/env bash
# The engineers' demo end to end (proof-of-fix#104), on a throwaway devnet beside any other (its own name, port, state
# and records; anvil's public test keys). v2 is deployed with 7 seats, 2 vacant: the owner fills one with a devnet
# role (join-v2), and a new engineer's own key joins the last one through pofctl (digest, sign, publish, 7 days,
# activate). Then a few bounties on a fake GitHub, each judged by real oracle node processes (python3 -m oracle run,
# the fake judge, the fixes' tests in the Docker sandbox): only the 3 drawn of 7 act, report their usage to the meter
# and sign; results, merges, settlements; every drawn validator withdraws its fees; balances checked exactly.
# The devnet and its files are removed when it ends, pass or fail. Never a public chain (rule 1).
#
#   scripts/demo-e2e.sh            (POF_DEMO_PORT picks the port, default 8553; POF_DEMO_NAME the container, for a
#                                  second run beside another; POF_DEMO_KEEP=1 keeps the devnet)
#   scripts/demo-e2e.sh --exchange http
#                                  the nodes share no folder: each in its own directory, talking only through the
#                                  exchange service (python3 -m exchange, #117), as on separate machines
#   scripts/demo-e2e.sh --exchange http-down
#                                  the service down for the whole run: the nodes on http,folder fall back to the folder
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVNET_NAME=${POF_DEMO_NAME:-pof-devnet-demo} DEVNET_PORT=${POF_DEMO_PORT:-8553} DEVNET_STATE=.devnet-demo \
  DEVNET_RECORD=contracts/deployments/demo/devnet.json DEVNET_RECORD_V2=contracts/deployments/demo/devnet-v2.json \
  DEVNET_KEYS=insecure-local DEVNET_V2_VACANT=2
[[ "$DEVNET_PORT" != 8546 ]] || { echo "demo-e2e: 8546 is the owner's devnet; pick another POF_DEMO_PORT" >&2; exit 2; }
cleanup() {
  [[ "${POF_DEMO_KEEP:-}" == 1 ]] && { echo "kept the demo devnet on 127.0.0.1:$DEVNET_PORT"; return; }
  scripts/devnet.sh reset >/dev/null 2>&1 || true
  chmod -R u+w .demo-e2e 2>/dev/null || true  # the nodes' fetched checkouts are read-only (#115)
  rm -rf .demo-e2e contracts/deployments/demo
}
trap cleanup EXIT
cleanup
mkdir -p contracts/deployments/demo .demo-e2e
scripts/devnet.sh up
scripts/devnet.sh fund >/dev/null
scripts/devnet.sh deploy-v2 >/dev/null
echo "deployed v2: $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print(r["seats"], "seats,", r["vacantSeats"], "vacant, quorum", r["quorum"])' "$DEVNET_RECORD_V2")"
# The owner fills seat 5 with a devnet role through the join-v2 helper (forge); the engineer's join is pofctl's.
scripts/devnet.sh join-v2 5 joiner-0 >/dev/null
echo "seat 5: joiner-0's key published by the owner (scripts/devnet.sh join-v2 5 joiner-0)"
python3 tests/e2e_demo.py --rpc "http://127.0.0.1:$DEVNET_PORT" --record "$DEVNET_RECORD_V2" --work .demo-e2e "$@"
