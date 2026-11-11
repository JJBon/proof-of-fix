#!/usr/bin/env bash
# The integration suite (proof-of-fix#152) against a throwaway local devnet beside any other (its own name, port, state
# and records; anvil's public test keys): v2 with 7 seats, 2 vacant, then tests/integration/suite.py's seven scenarios
# (the happy path, a failing fix, a race, a silent validator, an upheld challenge, joining, infrastructure faults) with
# the seats' real node processes, the fake judge and each fix's tests in the Docker sandbox. The devnet and its files
# are removed when it ends, pass or fail. Needs Docker. Never a public chain (rule 1).
#
#   scripts/integration.sh                     every scenario (about 15-25 minutes)
#   scripts/integration.sh --only 2,3          some of them (6, joining, always runs first)
#   scripts/integration.sh --with-first-run    then scripts/first-run-e2e.sh: scenario 7c, the owner's seat from cold
#   scripts/integration.sh --radicle           also scenario 8, Radicle merges (#201): a local Radicle network on an
#                                              --internal Docker network (tests/integration/radicle.py) starts first,
#                                              and Heads' genesis is its repository; --radicle --only 8 for it alone
#
# POF_INTEGRATION_PORT picks the devnet's port (default 8556); POF_INTEGRATION_KEEP=1 keeps the devnet.
#
# --target aws (#152's second box) runs against the persistent AWS devnet instead, with pof-sandbox and the live validator
# nodes (scripts/devnet-seats.sh up, and the owner's kit), the fake judge, and nothing started, reset or redeployed here:
#   scripts/integration.sh --target aws --preflight       reads only: what's missing (run it first)
#   scripts/integration.sh --target aws                   scenarios 2, 3, 1, 5, the fees withdrawn, the books, the cleanup
#   scripts/integration.sh --target aws --withdraw-only   only the seats' fees (seat 6's with POFCTL_KEY_ENGINEER, #150)
#   scripts/integration.sh --target aws --cleanup         close and delete what an interrupted run left in pof-sandbox
# Scenarios 4, 6 and 7 are local-only (they stop nodes, need a vacant seat, or take the relay away): the run lists them as
# skipped, with why. Its settings (DEVNET_RPC_URL, DEVNET_RPC_AUTH or _FILE, FIRST_BOUNTY_TOKEN or _FILE and
# FIRST_BOUNTY_USER, the role keys from OpenBao) and what it leaves behind: tests/integration/aws.py's top, and
# validator-kit/runbook.md, "The integration suite on the AWS devnet". It doesn't need Docker on this side.
# The nightly run (#152's third box), local target: .forgejo/workflows/nightly.yml. Against the AWS devnet: not set up
# (it needs the owner's keys in CI; that workflow's header lists what).
set -euo pipefail
cd "$(dirname "$0")/.."
TARGET=local
FIRST_RUN=0
RADICLE=0
ARGS=()
while (($#)); do
  case "$1" in
    --target)
      (($# >= 2)) || { echo "integration: --target needs a name: local or aws" >&2; exit 2; }
      TARGET=$2
      shift 2
      ;;
    --target=*) TARGET=${1#--target=}; shift ;;
    *)
      [[ "$1" == --with-first-run ]] && FIRST_RUN=1
      [[ "$1" == --radicle ]] && RADICLE=1
      ARGS+=("$1")
      shift
      ;;
  esac
done
case "$TARGET" in
  local) ;;
  aws) exec python3 tests/integration/aws.py "${ARGS[@]}" ;; # the shared devnet: nothing below (start, reset) runs
  *) echo "integration: unknown target $TARGET: local or aws" >&2; exit 2 ;;
esac
export DEVNET_NAME=${POF_INTEGRATION_NAME:-pof-devnet-integration} DEVNET_PORT=${POF_INTEGRATION_PORT:-8556} \
  DEVNET_STATE=.devnet-integration DEVNET_RECORD=contracts/deployments/integration/devnet.json \
  DEVNET_RECORD_V2=contracts/deployments/integration/devnet-v2.json DEVNET_KEYS=insecure-local DEVNET_V2_VACANT=2
[[ "$DEVNET_PORT" != 8546 ]] || { echo "integration: 8546 is the owner's devnet; pick another port" >&2; exit 2; }
command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "integration: Docker isn't reachable" >&2; exit 2; }
cleanup() {
  [[ "${POF_INTEGRATION_KEEP:-}" == 1 ]] && { echo "kept the integration devnet on 127.0.0.1:$DEVNET_PORT"; return; }
  scripts/devnet.sh reset >/dev/null 2>&1 || true
  python3 tests/integration/radicle.py down >/dev/null 2>&1 || true  # --radicle's network, if any
  chmod -R u+w .integration 2>/dev/null || true  # the nodes' fetched checkouts are read-only (#115)
  rm -rf .integration contracts/deployments/integration
}
trap cleanup EXIT
cleanup
mkdir -p contracts/deployments/integration .integration
scripts/devnet.sh up
scripts/devnet.sh fund >/dev/null
if [[ $RADICLE == 1 ]]; then  # the Radicle repository first: its RID and first commit are Heads' genesis (#201)
  read -r DEVNET_V2_REPO DEVNET_V2_GENESIS < <(python3 tests/integration/radicle.py up --work .integration)
  [[ -n "${DEVNET_V2_GENESIS:-}" ]] || { echo "integration: the Radicle network didn't start" >&2; exit 1; }
  export DEVNET_V2_REPO DEVNET_V2_GENESIS
fi
scripts/devnet.sh deploy-v2 >/dev/null
scripts/devnet.sh join-v2 5 joiner-0 >/dev/null
code=0
python3 tests/integration/suite.py --rpc "http://127.0.0.1:$DEVNET_PORT" --record "$DEVNET_RECORD_V2" \
  --work .integration "${ARGS[@]}" || code=$?
if [[ $FIRST_RUN == 1 ]]; then
  echo "== 7c. the owner's seat started on demand from cold: scripts/first-run-e2e.sh =="
  scripts/first-run-e2e.sh || code=1
fi
exit $code
