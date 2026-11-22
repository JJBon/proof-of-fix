#!/usr/bin/env bash
# The SEV-SNP kit's Radicle node on the internal Docker network (#251 task 4.9; tests/integration/kit_radicle.py): the
# seed as seed/ configures it, every other node as the measured disk configures a validator's (outbound only, dialling
# the seed alone), and the kit's lifecycle (hosts stopped until validator-kit/sevsnp/lambda/watcher.py starts them) on
# task 4.6's devnet with the launch's rules.
#
#   scripts/kit-radicle.sh            build the spike's node image (the pinned Radicle 1.10.3), run, clean up
#   scripts/kit-radicle.sh --keep     leave the containers and network up (for debugging)
#   scripts/kit-radicle.sh clean      remove what a stopped run left behind
#
# Needs Docker, the pinned solc (scripts/contracts.sh setup) and the pinned test image (scripts/test-image.sh). The only
# download is the Radicle release at the image's build. No model call, no public chain or network, no AWS. Results and
# node logs: .kit-radicle/ (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."
IMAGE=pof190-radicle:spike
if [[ "${1:-}" == clean ]]; then
  python3 tests/integration/kit_radicle.py clean
  exit 0
fi
[[ $# -eq 0 || "$1" == --keep ]] || { sed -n '6,8p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
# shellcheck source=scripts/solc.sh
source scripts/solc.sh # SOLC: the same pinned solc as scripts/contracts.sh
[[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
echo "building $IMAGE (pinned Radicle release, sha256-checked) ..."
docker build -q -t "$IMAGE" spikes/radicle >/dev/null
POF_SOLC="$SOLC" exec python3 tests/integration/kit_radicle.py run "$@" </dev/null
