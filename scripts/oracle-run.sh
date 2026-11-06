#!/usr/bin/env bash
# The oracle nodes end to end (proof-of-fix#94): sealed submissions, registered nodes plus one outside the set, the
# aggregator, and the contract checking every relay. Everything stays on this machine (openspec/config.yaml rule 1):
#   - fixes are tested in the pinned Python image with no network, read-only (oracle/sandbox.py);
#   - the judges are the deterministic fake: no model is called.
#
#   scripts/oracle-run.sh            a throwaway anvil on 127.0.0.1:18545: the loop's deployment (3 oracle keys, 2 of 3),
#                                    anvil's public test keys
#   scripts/oracle-run.sh --devnet   the private devnet (#93: scripts/devnet.sh up && deploy first) and its deployment
#                                    record (contracts/deployments/devnet.json: its oracle keys and quorum, 3 of 5).
#                                    Every role's key comes from OpenBao (sign in first), or anvil's public mnemonic
#                                    with DEVNET_KEYS=insecure-local; keys pass through the environment, never printed.
#                                    It adds a bounty and two submissions to the devnet, which keeps running.
# Both chains enforce EIP-170's 24,576-byte limit, as every public chain does: Race fits it since #93.
set -euo pipefail
cd "$(dirname "$0")/.."

FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
SOLC="contracts/.cache/solc-linux-amd64-v0.8.37+commit.f401782d"
PYTHON_IMAGE="python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8"
DEVNET=false
[[ "${1:-}" == --devnet ]] && DEVNET=true

[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
(cd contracts/lib && sha256sum --check --quiet SHA256SUMS)
(cd oracle/vendor && sha256sum --check --quiet SHA256SUMS)
for image in "$FOUNDRY_IMAGE" "$PYTHON_IMAGE"; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null
done

if $DEVNET; then
  # shellcheck source=scripts/devnet-keys.sh
  source scripts/devnet-keys.sh
  CHAIN=${DEVNET_NAME:-pof-devnet}
  PORT=${DEVNET_PORT:-8546}
  RECORD=contracts/deployments/devnet.json
  [[ "$(docker inspect -f '{{.State.Running}}' "$CHAIN" 2>/dev/null)" == true ]] ||
    { echo "devnet down: run scripts/devnet.sh up && scripts/devnet.sh deploy" >&2; exit 1; }
  [[ -f "$RECORD" ]] || { echo "not deployed: run scripts/devnet.sh deploy" >&2; exit 1; }
  scripts/devnet.sh fund >/dev/null
  # The participants' keys reach the bot's chain helper as LOOP_KEY_<ROLE>; the oracle keys reach the nodes and the
  # loop script as ORACLE_KEYS, all through the environment (bot/chain.py), never a command line.
  for role in bot reporter funder solver-a solver-b; do
    var="LOOP_KEY_$(tr 'a-z-' 'A-Z_' <<<"$role")"
    printf -v "$var" '%s' "$(devnet_key "$role")"
    export "${var?}"
  done
  ORACLE_KEYS=""
  for ((i = 0; i < ORACLES; i++)); do ORACLE_KEYS+="${ORACLE_KEYS:+,}$(devnet_key "oracle-$i")"; done
  ORACLE_QUORUM=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["quorum"])' "$RECORD")
  export ORACLE_KEYS ORACLE_QUORUM
  ORACLE_CHAIN="$CHAIN" ORACLE_CHAIN_ID=7193 ORACLE_RPC="http://127.0.0.1:$PORT" ORACLE_RECORD="$RECORD" \
    python3 -m oracle.run_local
  exit
fi

CHAIN=pof-oracle-chain
PORT=18545
down() { docker rm -f "$CHAIN" >/dev/null 2>&1 || true; }
trap down EXIT
down

docker run -d --name "$CHAIN" -p "127.0.0.1:$PORT:8545" --user "$(id -u):$(id -g)" \
  -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work \
  --entrypoint sh "$FOUNDRY_IMAGE" -c 'anvil --host 0.0.0.0 --port 8545 --silent & exec sleep infinity' >/dev/null

ORACLE_CHAIN="$CHAIN" ORACLE_RPC="http://127.0.0.1:$PORT" python3 -m oracle.run_local
