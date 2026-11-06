#!/usr/bin/env bash
# Devnet keys (proof-of-fix#93): one key per role, generated offline in the pinned Foundry image and kept only in
# OpenBao at secret/proof-of-fix/devnet/<role> (field `key`). They exist for the private devnet alone (rule 1): never
# use one on a public chain. No key is printed, logged or written to disk; only addresses are shown.
#
#   scripts/devnet-keys.sh init        create every missing role's key (the owner runs it once, signed in to OpenBao)
#   scripts/devnet-keys.sh addresses   print each role's address
#   scripts/devnet-keys.sh roles       print the roles
#
# Sign in first: BAO_ADDR=https://vault.example.com bao login -method=oidc role=admin
# Tests and CI may use anvil's public test mnemonic instead, only with DEVNET_KEYS=insecure-local set explicitly
# (scripts/devnet.sh and scripts/bounty-loop.sh read it through devnet_key below).
set -euo pipefail
cd "$(dirname "$0")/.."

export BAO_ADDR=${BAO_ADDR:-https://vault.example.com}
FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
MOUNT=secret
PREFIX=proof-of-fix/devnet
# The oracle quorum fixed at deployment: 5 keys, 3 to sign (D3: above half the keys).
ORACLES=5
ROLES=(deployer bot reporter funder solver-a solver-b infrastructure insurance founder)
for ((i = 0; i < ORACLES; i++)); do ROLES+=("oracle-$i"); done
# Keys for vacant v2 seats to join with (#85 task 5.4, #104): appended last, so the roles above keep their indices.
ROLES+=(joiner-0 joiner-1)
# anvil's public test mnemonic, for DEVNET_KEYS=insecure-local only.
MNEMONIC="test test test test test test test test test test test junk"

foundry() { docker run --rm -i --network none --entrypoint sh "$FOUNDRY_IMAGE" -c "$1"; }

bao_ready() {
  command -v bao >/dev/null || { echo "bao CLI missing" >&2; return 1; }
  bao token lookup >/dev/null 2>&1 || {
    echo "Not signed in to OpenBao ($BAO_ADDR). Run: BAO_ADDR=$BAO_ADDR bao login -method=oidc role=admin" >&2
    return 1
  }
}

# The role's key on stdout, for a caller to capture (never echo it).
devnet_key() {
  local role=$1 i
  if [[ "${DEVNET_KEYS:-}" == insecure-local ]]; then
    for i in "${!ROLES[@]}"; do [[ "${ROLES[$i]}" == "$role" ]] && break; done
    [[ "${ROLES[$i]}" == "$role" ]] || { echo "unknown role $role" >&2; return 1; }
    foundry "cast wallet private-key --mnemonic \"$MNEMONIC\" --mnemonic-index $i"
    return
  fi
  bao_ready
  bao kv get -mount="$MOUNT" -field=key "$PREFIX/$role" 2>/dev/null || {
    echo "No devnet key for $role in OpenBao ($MOUNT/$PREFIX/$role). Run: scripts/devnet-keys.sh init" >&2
    return 1
  }
}

address_of() { # key on stdin -> address
  foundry 'read -r k; cast wallet address --private-key "$k"'
}

init() {
  bao_ready
  local role made=0
  for role in "${ROLES[@]}"; do
    if bao kv metadata get -mount="$MOUNT" "$PREFIX/$role" >/dev/null 2>&1; then
      continue
    fi
    # A new random key, made offline; it goes straight from the container to OpenBao on stdin.
    foundry 'cast wallet new --json | sed -n "s/.*\"private_key\": *\"\(0x[0-9a-fA-F]*\)\".*/\1/p"' |
      bao kv put -mount="$MOUNT" "$PREFIX/$role" key=- >/dev/null
    made=$((made + 1))
  done
  echo "devnet keys: $made created, $((${#ROLES[@]} - made)) already there ($MOUNT/$PREFIX/<role>)"
  addresses
}

addresses() {
  local role
  for role in "${ROLES[@]}"; do
    printf '%-15s %s\n' "$role" "$(devnet_key "$role" | address_of)"
  done
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  case "${1:-}" in
    init) init ;;
    addresses) addresses ;;
    roles) printf '%s\n' "${ROLES[@]}" ;;
    *) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
fi
