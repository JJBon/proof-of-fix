#!/usr/bin/env bash
# v3 (open validators) end to end on a throwaway local devnet beside v2 (proof-of-fix#140, task 5.1 of #132), in the
# style of scripts/demo-e2e.sh: its own devnet (name, port, state and records; anvil's public test keys), v2 deployed,
# then v3 beside it with one genesis validator of the `simulated` proof type (scripts/devnet.sh deploy-v3), then
# tests/integration/suite_v3.py: validators register and qualify until k reaches 3, then 5, and the run shows
#   - a k = 1 verdict held until three more validators are active, audited twice, then final after its window;
#   - a bounty above k = 1's limit waiting, shadowed by candidates, then drawn when k = 3 is reached;
#   - a challenged k = 1 verdict reversed by a fresh panel of 3, and the chain time from the wrong pass to its reversal;
#   - a silent validator replaced, and a counted panel of 5.
# The validators are real node objects with the fake judge: no model call, no network beyond this machine. Panels'
# windows are the real ones (hours and days); the run moves the devnet's clock. The devnet and its files are removed
# when it ends, pass or fail, and no container is left behind. Needs Docker. Never a public chain (rule 1).
#
#   scripts/devnet-v3-e2e.sh            about 5 minutes (POF_V3_E2E_PORT picks the port, default 8558;
#                                       POF_V3_E2E_NAME the container; POF_V3_E2E_KEEP=1 keeps the devnet)
#   scripts/devnet-v3-e2e.sh --heal     also time to heal for a paid fix (scripts/time-to-heal.sh): a bad fix passed by
#                                       a panel of 3, claimed, challenged, and reversed by a fresh panel of 5
#   scripts/devnet-v3-e2e.sh --report <file>   write the run's numbers as JSON; --verbose prints every node's log
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVNET_NAME=${POF_V3_E2E_NAME:-pof-devnet-v3-e2e} DEVNET_PORT=${POF_V3_E2E_PORT:-8558} \
  DEVNET_STATE=${POF_V3_E2E_STATE:-.devnet-v3-e2e} DEVNET_KEYS=insecure-local DEVNET_V2_VACANT=2
RECORDS=contracts/deployments/${POF_V3_E2E_RECORDS:-v3-e2e}
WORK=${POF_V3_E2E_WORK:-.v3-e2e}
export DEVNET_RECORD=$RECORDS/devnet.json DEVNET_RECORD_V2=$RECORDS/devnet-v2.json DEVNET_RECORD_V3=$RECORDS/devnet-v3.json
[[ "$DEVNET_PORT" != 8546 ]] || { echo "devnet-v3-e2e: 8546 is the owner's devnet; pick another port" >&2; exit 2; }
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "devnet-v3-e2e: Docker isn't reachable" >&2; exit 2; }
cleanup() {
  [[ "${POF_V3_E2E_KEEP:-}" == 1 ]] && { echo "kept the devnet on 127.0.0.1:$DEVNET_PORT"; return; }
  scripts/devnet.sh reset >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RECORDS"
}
trap cleanup EXIT
cleanup
mkdir -p "$RECORDS" "$WORK"
scripts/devnet.sh up
scripts/devnet.sh fund >/dev/null
scripts/devnet.sh deploy-v2 >/dev/null
echo "deployed v2: $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("RaceV2", r["race"] + ",", r["seats"], "seats, quorum", r["quorum"])' "$DEVNET_RECORD_V2")"
# The genesis validator's throwaway key and its attestation hash reach the deployment through the environment, never
# a command line or the output.
keys=$(python3 tests/integration/suite_v3.py prepare)
DEVNET_V3_GENESIS_PK=$(sed -n 's/^GENESIS=//p' <<<"$keys") DEVNET_V3_ATTESTATION=$(sed -n 's/^ATTESTATION=//p' <<<"$keys") \
  DEVNET_V3_FAMILIES=$(sed -n 's/^FAMILIES=//p' <<<"$keys") scripts/devnet.sh deploy-v3 >"$WORK/deploy-v3.log" 2>&1 ||
  { tail -40 "$WORK/deploy-v3.log" >&2; exit 1; }
unset keys
echo "deployed v3 beside it: $(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); print("RaceV3", r["race"] + ", Panels", r["panels"] + ", Validators", r["registry"])' "$DEVNET_RECORD_V3")"
python3 tests/integration/suite_v3.py run --rpc "http://127.0.0.1:$DEVNET_PORT" --record "$DEVNET_RECORD_V3" \
  --work "$WORK" "$@"
