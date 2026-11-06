#!/usr/bin/env bash
# The local contract prototype (proof-of-fix#56, design D1): build and test in the pinned Foundry image, with the
# pinned solc mounted read-only and no network but the container's loopback. Nothing is installed on the host, and
# nothing here deploys anywhere but a throwaway anvil inside the container.
#
#   scripts/contracts.sh setup         pull the image by digest and fetch solc (the only steps that use the network)
#   scripts/contracts.sh build         forge build
#   scripts/contracts.sh sizes         forge build --sizes (every contract must stay under EIP-170's 24,576 bytes)
#   scripts/contracts.sh test [args]   forge test [args], then a fresh anvil answers on localhost
#   scripts/contracts.sh quote [args]  print a bounty's quote (contracts/script/Quote.s.sol; no args: a demo)
#   scripts/contracts.sh verify        the vendored libraries match contracts/lib/SHA256SUMS
#   scripts/contracts.sh vendor        re-vendor the libraries at the pinned commits and rewrite SHA256SUMS
set -euo pipefail
cd "$(dirname "$0")/.."

# Foundry v1.8.5 (2026-10-05), the newest stable release at least two weeks old on 2026-10-26.
IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
# solc 0.8.37 (2026-09-10), linux-amd64 static build, sha256 from binaries.soliditylang.org/linux-amd64/list.json.
SOLC_BUILD="solc-linux-amd64-v0.8.37+commit.f401782d"
SOLC_SHA256="5de843c2c93563cc66425c99a4fb13fdbf32b4c4ae07469480faaf126e14404a"
SOLC="contracts/.cache/$SOLC_BUILD"

# Vendored libraries (design D1): forge-std v1.17.0 whole, OpenZeppelin v5.7.0 only what SafeERC20, ECDSA,
# MessageHashUtils, ReentrancyGuardTransient and ERC20 (for the mock coins) import.
FORGE_STD_COMMIT="f3dae6e6ee381f25eb6a246f7da9b85c91a68219"  # v1.17.0
OZ_COMMIT="cab19933c33c2ad1d4c7a84864a3601dddfd16f3"         # v5.7.0
OZ_FILES=(
  interfaces/IERC1363.sol interfaces/IERC165.sol interfaces/IERC20.sol interfaces/IERC20Metadata.sol
  interfaces/draft-IERC6093.sol token/ERC20/ERC20.sol token/ERC20/IERC20.sol
  token/ERC20/extensions/IERC20Metadata.sol token/ERC20/utils/SafeERC20.sol utils/Bytes.sol utils/Context.sol
  utils/Panic.sol utils/ReentrancyGuardTransient.sol utils/Strings.sol utils/TransientSlot.sol utils/cryptography/ECDSA.sol utils/cryptography/MessageHashUtils.sol
  utils/introspection/IERC165.sol utils/math/Math.sol utils/math/SafeCast.sol utils/math/SignedMath.sol
)

verify() {
  (cd contracts/lib && sha256sum --check --quiet SHA256SUMS)
}

solc_ok() {
  [[ -f "$SOLC" ]] && echo "$SOLC_SHA256  $SOLC" | sha256sum --check --quiet --status
}

setup() {
  docker pull -q "$IMAGE"
  if ! solc_ok; then
    mkdir -p contracts/.cache
    curl -fsSL -o "$SOLC.part" "https://binaries.soliditylang.org/linux-amd64/$SOLC_BUILD"
    echo "$SOLC_SHA256  $SOLC.part" | sha256sum --check --quiet
    chmod 755 "$SOLC.part" && mv "$SOLC.part" "$SOLC"
  fi
  echo "setup done: $IMAGE, $SOLC_BUILD"
}

# Runs a shell command in the image, offline: --network none leaves only the container's own loopback. FOUNDRY_*
# variables pass through (e.g. FOUNDRY_INVARIANT_RUNS=256 for a deeper invariant run).
in_container() {
  solc_ok || { echo "solc missing or altered; run: scripts/contracts.sh setup" >&2; exit 1; }
  verify
  local env=()
  while IFS= read -r name; do env+=(-e "$name"); done < <(compgen -e | grep '^FOUNDRY_' || true)
  docker run --rm --network none --user "$(id -u):$(id -g)" "${env[@]}" \
    -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work \
    --entrypoint sh "$IMAGE" -c "$1" sh "${@:2}"
}

vendor() {
  local tmp
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' RETURN
  fetch() {  # repo commit dir: a shallow fetch of one commit, no code run
    git init -q "$3" && git -C "$3" fetch -q --depth 1 "$1" "$2" && git -C "$3" -c advice.detachedHead=false checkout -q FETCH_HEAD
  }
  fetch https://github.com/foundry-rs/forge-std.git "$FORGE_STD_COMMIT" "$tmp/forge-std"
  fetch https://github.com/OpenZeppelin/openzeppelin-contracts.git "$OZ_COMMIT" "$tmp/oz"
  rm -rf contracts/lib/forge-std contracts/lib/openzeppelin-contracts
  mkdir -p contracts/lib/forge-std contracts/lib/openzeppelin-contracts
  cp -r "$tmp/forge-std/src" "$tmp/forge-std/LICENSE-MIT" "$tmp/forge-std/LICENSE-APACHE" contracts/lib/forge-std/
  cp "$tmp/oz/LICENSE" contracts/lib/openzeppelin-contracts/
  for f in "${OZ_FILES[@]}"; do
    install -D -m 644 "$tmp/oz/contracts/$f" "contracts/lib/openzeppelin-contracts/contracts/$f"
  done
  (cd contracts/lib && find . -type f ! -name SHA256SUMS ! -name README.md | LC_ALL=C sort | xargs sha256sum > SHA256SUMS)
  echo "vendored forge-std $FORGE_STD_COMMIT, openzeppelin-contracts $OZ_COMMIT"
}

case "${1:-}" in
  setup) setup ;;
  verify) verify && echo "vendored libraries match SHA256SUMS" ;;
  vendor) vendor ;;
  build) in_container 'forge build' ;;
  sizes) in_container 'forge build --sizes' ;;
  test)
    # forge test, then a fresh anvil in the same offline container must answer on localhost (spec: Pinned and local).
    in_container 'forge test "$@" && {
      anvil --host 127.0.0.1 --port 8545 --silent & pid=$!
      for _ in $(seq 50); do cast chain-id --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1 && break; sleep 0.1; done
      id=$(cast chain-id --rpc-url http://127.0.0.1:8545); kill $pid
      [ "$id" = 31337 ] && echo "anvil on localhost: chain $id"
    }' "${@:2}"
    ;;
  quote) in_container 'forge script script/Quote.s.sol "$@"' "${@:2}" ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
