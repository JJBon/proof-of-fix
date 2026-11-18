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
#   scripts/integration.sh --only 10           scenario 10 (#210, always last): the untyped loop, `pofctl bot watch` as
#                                              its own process and the seats' registration check, with no bot command
#                                              typed by the suite
#   scripts/integration.sh --radicle           also scenario 8, Radicle merges (#201): a local Radicle network on an
#                                              --internal Docker network (tests/integration/radicle.py) starts first,
#                                              and Heads' genesis is its repository; --radicle --only 8 for it alone
#
#   scripts/integration.sh --version 3         v3, open validators (#140, task 5.0 of #132), on the same throwaway
#                                              devnet: v2 deployed, v3 beside it (scripts/devnet.sh deploy-v3, its
#                                              record contracts/deployments/integration/devnet-v3.json), then
#                                              tests/integration/suite_v3.py: registration and qualification
#                                              (scenario 6), the replacement of a silent judge (scenario 4), the k = 1
#                                              hold and its audits, a waiting bounty, and a challenge reversed by a
#                                              fresh panel. It reads who is drawn and what decides through
#                                              tests/integration/panel.py, as the v2 suite does. --heal adds the time
#                                              to heal of a paid fix. Local only: --target aws --version 3 is task 5.2.
#                                              v2's scenarios 1-3, 5, 7 and 10 go through pofctl, the bot and the
#                                              relay, which don't speak v3 yet: they are not run for v3.
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
VERSION=2
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
    --version)
      (($# >= 2)) || { echo "integration: --version needs 2 or 3" >&2; exit 2; }
      VERSION=$2
      shift 2
      ;;
    --version=*) VERSION=${1#--version=}; shift ;;
    *)
      [[ "$1" == --with-first-run ]] && FIRST_RUN=1
      [[ "$1" == --radicle ]] && RADICLE=1
      ARGS+=("$1")
      shift
      ;;
  esac
done
case "$VERSION" in
  2) ;;
  3)
    [[ "$TARGET" == local ]] || { echo "integration: --version 3 runs on the local devnet only for now (the AWS devnet is task 5.2 of #132)" >&2; exit 2; }
    # The same throwaway devnet as v2's run (name, port, state, records), started and removed by devnet-v3-e2e.sh.
    export POF_V3_E2E_NAME=${POF_INTEGRATION_NAME:-pof-devnet-integration} POF_V3_E2E_PORT=${POF_INTEGRATION_PORT:-8556} \
      POF_V3_E2E_STATE=.devnet-integration POF_V3_E2E_RECORDS=integration POF_V3_E2E_WORK=.integration \
      POF_V3_E2E_KEEP=${POF_INTEGRATION_KEEP:-}
    exec scripts/devnet-v3-e2e.sh "${ARGS[@]}"
    ;;
  *) echo "integration: unknown version $VERSION: 2 or 3" >&2; exit 2 ;;
esac
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
