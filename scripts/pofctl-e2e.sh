#!/usr/bin/env bash
# pofctl end to end (proof-of-fix#104): a throwaway devnet beside any other (its own name, port, state and records),
# v2 deployed with anvil's public test keys, and tests/e2e_pofctl.py driving every role through pofctl against a fake
# GitHub on the loopback. The devnet and its files are removed when it ends, pass or fail. Never a public chain (rule 1).
#
#   scripts/pofctl-e2e.sh                 v2 (the default; --version 2 is the same)
#   scripts/pofctl-e2e.sh --version 3     v3 and Radicle (#251 task 4.4): anvil (chain 31337) in the pinned Foundry
#                                         image, v3 deployed for this run's repository (NodeV3Local.s.sol, its RID and
#                                         a real genesis commit), validators that qualify to panels of 3, a stand-in
#                                         Radicle node, and tests/e2e_pofctl_v3.py playing the reporter, the funder and
#                                         three solvers through pofctl alone (a keystore key for one). A few minutes;
#                                         POFCTL_E2E_V3_PORT picks the port (default 8561), POFCTL_E2E_V3_KEEP=1 keeps
#                                         the chain and its files.
set -euo pipefail
cd "$(dirname "$0")/.."

version=2
while (($#)); do
  case "$1" in
    --version) version=${2:-}; shift 2 || shift ;;
    --version=*) version=${1#--version=}; shift ;;
    *) echo "pofctl-e2e: unknown argument $1 (--version 2|3)" >&2; exit 2 ;;
  esac
done

if [[ "$version" == 2 ]]; then
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
  exit 0
fi
[[ "$version" == 3 ]] || { echo "pofctl-e2e: --version 2 or 3, not '$version'" >&2; exit 2; }

# ---------- v3 and Radicle ----------
FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
# shellcheck source=scripts/solc.sh
source scripts/solc.sh # SOLC: the same pinned solc as scripts/contracts.sh
NAME=${POFCTL_E2E_V3_NAME:-pof-pofctl-v3-e2e}
PORT=${POFCTL_E2E_V3_PORT:-8561}
WORK=.pofctl-v3-e2e
RECORD_DIR=contracts/deployments/pofctl-v3-e2e
RPC=http://127.0.0.1:8545 # inside the container
[[ "$PORT" != 8546 ]] || { echo "pofctl-e2e: 8546 is the owner's devnet; pick another port" >&2; exit 2; }
[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "pofctl-e2e: Docker isn't reachable" >&2; exit 2; }

cleanup() {
  [[ "${POFCTL_E2E_V3_KEEP:-}" == 1 ]] && { echo "kept the chain on 127.0.0.1:$PORT and $WORK"; return; }
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RECORD_DIR"
}
trap cleanup EXIT
docker rm -f "$NAME" >/dev/null 2>&1 || true
rm -rf "$WORK" "$RECORD_DIR"
mkdir -p "$WORK" "$RECORD_DIR"

docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8545" --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work \
  --entrypoint anvil "$FOUNDRY_IMAGE" --host 0.0.0.0 --port 8545 --chain-id 31337 --silent >/dev/null
for _ in $(seq 60); do
  [[ "$(docker exec "$NAME" cast chain-id --rpc-url "$RPC" 2>/dev/null)" == 31337 ]] && break
  sleep 0.5
done

# The repository (a real genesis commit), the stand-in Radicle node's storage, and the deployment's throwaway keys
# (derived from public strings), passed on stdin and in the script's environment: never on a command line.
prep=$(python3 tests/e2e_pofctl_v3.py prepare --rpc "http://127.0.0.1:$PORT" --work "$WORK")
printf '%s\n%s\n' "$(sed -n 's/^DEPLOYER=//p' <<<"$prep")" "$(sed -n 's/^GENESIS=//p' <<<"$prep")" |
  docker exec -i -w /work -e LOCAL_ATTESTATION="$(sed -n 's/^ATTESTATION=//p' <<<"$prep")" \
    -e LOCAL_FAMILIES="$(sed -n 's/^FAMILIES=//p' <<<"$prep")" -e LOCAL_RID="$(sed -n 's/^RID=//p' <<<"$prep")" \
    -e LOCAL_GENESIS_HEAD="$(sed -n 's/^GENESIS_HEAD=//p' <<<"$prep")" -e LOCAL_RECORD=pofctl-v3-e2e/local.json \
    "$NAME" sh -c 'read -r PK; read -r LOCAL_GENESIS_PK; export LOCAL_GENESIS_PK
      forge script script/NodeV3Local.s.sol:NodeV3LocalScript --rpc-url '"$RPC"' --broadcast --private-key "$PK" --slow' \
    >"$WORK/deploy.log" 2>&1 || { tail -40 "$WORK/deploy.log" >&2; exit 1; }
unset prep
echo "deployed v3 on a local chain: $(sed -n 's/.*"race": *"\(0x[0-9a-fA-F]*\)".*/RaceV3 \1/p' "$RECORD_DIR/local.json")"

python3 tests/e2e_pofctl_v3.py run --rpc "http://127.0.0.1:$PORT" --record "$RECORD_DIR/local.json" --work "$WORK"
