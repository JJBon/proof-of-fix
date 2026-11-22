#!/usr/bin/env bash
# The local bounty loop, end to end (proof-of-fix#56 task 3.3, design D8 phase 4): a throwaway Forgejo and a throwaway
# anvil, the bounty bot, and one issue through the whole loop (a failing fix, then a passing one, merged and paid).
# Everything stays on this machine (openspec/config.yaml rule 1):
#   - anvil, cast and forge run in the pinned Foundry image with no network at all (`--network none`): the chain
#     listens on that container's own loopback, and the bot reaches it with `docker exec`;
#   - Forgejo is bound to 127.0.0.1 only, offline, with registration, federation, mail and update checks off;
#   - fixes are tested in a pinned Python image with no network, read-only;
#   - every key is one of anvil's public test keys.
# The chain enforces EIP-170's 24,576-byte limit, as every public chain does: Race fits it since #93.
# The containers are removed when it ends, pass or fail.
#
#   scripts/bounty-loop.sh            run the loop (pulls the two images by digest the first time)
#   scripts/bounty-loop.sh --devnet   run it on the private devnet instead (#93: scripts/devnet.sh up first), with
#                                     each role's key and the oracle quorum's from OpenBao (or anvil's public mnemonic
#                                     with DEVNET_KEYS=insecure-local); the devnet keeps running afterwards
set -euo pipefail
cd "$(dirname "$0")/.."

# The same Foundry image and solc as scripts/contracts.sh (tests/test_bot.py checks they match).
FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
# shellcheck source=scripts/solc.sh
source scripts/solc.sh # SOLC: the same pinned solc as scripts/contracts.sh
# Forgejo 11.0.16 LTS (built 2026-07-09).
FORGEJO_IMAGE="codeberg.org/forgejo/forgejo@sha256:946243edbab116d5bb78b73ea68af6f3d69229ba1b1ed958dd82c3481167f3e0"
# Python 3.12 on Alpine, only to run the fixes' tests (the "AI check" stand-in).
PYTHON_IMAGE="python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8"
CHAIN=pof-loop-chain
FORGEJO=pof-loop-forgejo
PORT=3300
DEVNET=false
[[ "${1:-}" == --devnet ]] && DEVNET=true

[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
(cd contracts/lib && sha256sum --check --quiet SHA256SUMS)
for image in "$FOUNDRY_IMAGE" "$FORGEJO_IMAGE" "$PYTHON_IMAGE"; do
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null
done

if $DEVNET; then
  # The devnet's container, its chain id, and every role's key from OpenBao: the oracle keys reach forge through the
  # environment (bot/chain.py), the others through LOOP_KEY_<ROLE>. Nothing is printed.
  # shellcheck source=scripts/devnet-keys.sh
  source scripts/devnet-keys.sh
  [[ "$(docker inspect -f '{{.State.Running}}' pof-devnet 2>/dev/null)" == true ]] ||
    { echo "devnet down: run scripts/devnet.sh up" >&2; exit 1; }
  scripts/devnet.sh fund >/dev/null
  CHAIN=pof-devnet
  export LOOP_CHAIN_ID=7193
  for role in bot reporter funder solver-a solver-b infrastructure insurance founder; do
    var="LOOP_KEY_$(tr 'a-z-' 'A-Z_' <<<"$role")"
    printf -v "$var" '%s' "$(devnet_key "$role")"
    export "${var?}"
  done
  ORACLE_KEYS=""
  for ((i = 0; i < 3; i++)); do ORACLE_KEYS+="${ORACLE_KEYS:+,}$(devnet_key "oracle-$i")"; done
  export ORACLE_KEYS ORACLE_QUORUM=2 # 2 of 3, as the local loop (its balances count two signing oracles)
fi

down() {
  if $DEVNET; then docker rm -f "$FORGEJO" >/dev/null 2>&1 || true
  else docker rm -f "$CHAIN" "$FORGEJO" >/dev/null 2>&1 || true; fi
}
trap down EXIT
down

$DEVNET || docker run -d --name "$CHAIN" --network none --user "$(id -u):$(id -g)" \
  -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work \
  --entrypoint sh "$FOUNDRY_IMAGE" -c 'anvil --host 127.0.0.1 --port 8545 --silent & exec sleep infinity' >/dev/null

docker run -d --name "$FORGEJO" -p "127.0.0.1:$PORT:3000" \
  -e FORGEJO__database__DB_TYPE=sqlite3 \
  -e FORGEJO__security__INSTALL_LOCK=true \
  -e FORGEJO__server__ROOT_URL="http://127.0.0.1:$PORT/" \
  -e FORGEJO__server__OFFLINE_MODE=true \
  -e FORGEJO__server__DISABLE_SSH=true \
  -e FORGEJO__service__DISABLE_REGISTRATION=true \
  -e FORGEJO__federation__ENABLED=false \
  -e FORGEJO__mailer__ENABLED=false \
  -e FORGEJO__picture__DISABLE_GRAVATAR=true \
  -e FORGEJO__picture__ENABLE_FEDERATED_AVATAR=false \
  -e FORGEJO__cron_0X2E_update_checker__ENABLED=false \
  -e FORGEJO__migrations__ALLOW_LOCALNETWORKS=false \
  -e FORGEJO__webhook__ALLOWED_HOST_LIST=loopback \
  -e FORGEJO__repository__DEFAULT_PRIVATE=private \
  -e FORGEJO__log__LEVEL=Warn \
  "$FORGEJO_IMAGE" >/dev/null

LOOP_CHAIN="$CHAIN" LOOP_FORGEJO="$FORGEJO" LOOP_FORGEJO_URL="http://127.0.0.1:$PORT" LOOP_PYTHON_IMAGE="$PYTHON_IMAGE" \
  python3 -m bot.loop
