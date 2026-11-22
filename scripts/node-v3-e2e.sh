#!/usr/bin/env bash
# The v3 validator node against the real v3 contracts on a throwaway local chain (proof-of-fix#139, task 4.1 of #132):
# anvil in the pinned Foundry image (chain 31337), v3 deployed with one genesis validator of the `simulated` proof type
# (contracts/script/NodeV3Local.s.sol), and real node objects (oracle/node_v3.py) with the fake judge:
#   - candidates register (signed by their keys, bonded; the attestation is a dstack simulator's quote) and one leaves;
#   - a registered issue's check is drawn: the genesis validator is the counted judge, candidates are shadows; each
#     seals, then posts its receipt's hash and its reveal on-chain through the `onchain` transport, and reports its
#     usage; the shadows' seals are on-chain before the counted reveal;
#   - the genesis validator posts its cost table, makes the keeper's calls, and is paid by the result;
#   - a watcher re-runs the check with a lying judge and files a challenge with its evidence.
# The contracts check every signature and every call's encoding, which the fake chain of tests/test_oracle_v3.py can't.
# No model call, no network beyond this machine. The chain and its files are removed when it ends, pass or fail.
#
#   scripts/node-v3-e2e.sh           (POF_NODE_E2E_PORT picks the port, default 8557; POF_NODE_E2E_KEEP=1 keeps it)
#   scripts/node-v3-e2e.sh --grow    also registers issues until candidates qualify and a panel of 3 judges a check
#                                    (minutes; it adds shadows on waiting submissions, a counted panel of 3 and an
#                                    auditor's seat, all on the real contracts)
set -euo pipefail
cd "$(dirname "$0")/.."

FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
# shellcheck source=scripts/solc.sh
source scripts/solc.sh # SOLC: the same pinned solc as scripts/contracts.sh
NAME=${POF_NODE_E2E_NAME:-pof-node-v3-e2e}
PORT=${POF_NODE_E2E_PORT:-8557}
WORK=.node-v3-e2e
RECORD_DIR=contracts/deployments/node-v3-e2e
RPC=http://127.0.0.1:8545 # inside the container
[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }

cleanup() {
  [[ "${POF_NODE_E2E_KEEP:-}" == 1 ]] && { echo "kept the chain on 127.0.0.1:$PORT"; return; }
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

# The deployer's and the genesis validator's throwaway keys (derived from public strings, like the local test keys),
# passed on stdin and in the script's environment: never on a command line.
keys=$(python3 tests/e2e_node_v3.py prepare --rpc "http://127.0.0.1:$PORT")
deployer=$(sed -n 's/^DEPLOYER=//p' <<<"$keys")
genesis=$(sed -n 's/^GENESIS=//p' <<<"$keys")
attestation=$(sed -n 's/^ATTESTATION=//p' <<<"$keys")
printf '%s\n%s\n' "$deployer" "$genesis" | docker exec -i -w /work -e LOCAL_ATTESTATION="$attestation" \
  -e LOCAL_FAMILIES=fake,fake-1,fake-2,fake-3 -e LOCAL_RECORD=node-v3-e2e/local.json "$NAME" sh -c \
  'read -r PK; read -r LOCAL_GENESIS_PK; export LOCAL_GENESIS_PK
   forge script script/NodeV3Local.s.sol:NodeV3LocalScript --rpc-url '"$RPC"' --broadcast --private-key "$PK" --slow' \
  >"$WORK/deploy.log" 2>&1 || { tail -40 "$WORK/deploy.log" >&2; exit 1; }
echo "deployed v3 on a local chain: $(sed -n 's/.*"race": *"\(0x[0-9a-fA-F]*\)".*/RaceV3 \1/p' "$RECORD_DIR/local.json")"

python3 tests/e2e_node_v3.py run --rpc "http://127.0.0.1:$PORT" --record "$RECORD_DIR/local.json" --work "$WORK" "$@"
