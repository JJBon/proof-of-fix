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
#   scripts/integration.sh --version 3 --radicle
#                                              one bounty end to end on Radicle (#251 task 4.6, about 15-25 minutes):
#                                              real Radicle 1.10.3 nodes, anvil and a relay on a Docker network created
#                                              with --internal (the spike's setup, spikes/radicle/v3_spike.py), v3 on
#                                              the launch's rules (panel caps off, panels of 3, same-size challenges,
#                                              the windows in minutes, the taxi fare, the test coin), seven validators
#                                              reading patches and issues from their own Radicle nodes, the reporter,
#                                              funder and solvers through pofctl: tests/integration/suite_v3_radicle.py.
#                                              Nothing is published beyond that network; --keep leaves it up. Results
#                                              and node logs: .integration-radicle-v3/
#
#   scripts/integration.sh --version 3 --external
#                                              one validator run outside the harness (#251 task 7.0, L18 items 3 and
#                                              6): production windows on anvil, the seed and six harness validators on
#                                              Radicle (task 4.9's kit network), and one validator this run neither
#                                              starts nor signs for (POF_V3_EXTERNAL), which registers itself, qualifies
#                                              and sits a fix's counted panel while the moved clock waits for its
#                                              seats: tests/integration/external_v3.py. POF_EXT_MODE=aws (the test-chain
#                                              host beside the SEV-SNP host, scripts/rc-aws.sh) or local (the dress
#                                              rehearsal; scripts/rc-aws.sh rehearse starts the outside validator).
#                                              It writes ready.json and external.json in POF_EXT_DIR
#
# POF_INTEGRATION_PORT picks the devnet's port (default 8556); POF_INTEGRATION_KEEP=1 keeps the devnet.
#
# --version 3 runs scripts/integration-v3.sh: the story above, then #256's lettered scenarios for #251's contract batch 4
# (task 3.27), each set on its own throwaway devnet with the rules it needs (tests/integration/scenarios_v3.py): u, v
# and w on the Sepolia record's rules (panel caps `launch`, kTop 3, `same`), f and g with one model family under both
# challenge sizes. --sets story,launch,few-larger,few-same picks some (about 6, 25, 4 and 4 minutes); --report-dir
# <dir> writes each set's numbers.
#
#   scripts/integration.sh --release-candidate <commit> [--runs N] [--record <file>] [--tag <name>]
#        The release candidate (#251 L18, task 7.0; scripts/release_candidate.py): that exact commit, checked out into
#        a fresh worktree, runs `--version 3 --heal` N times in a row (default 3, stopping at the first failure) on
#        production windows (refused otherwise: SEV-SNP hosts can't cold-start within minute windows), and the record
#        is written: the commit, every contract's bytecode hash (scripts/deploy-sepolia.sh hashes), the runs and the
#        rules the launch set ran with. The items this run can't check (a real SEV-SNP validator, a real-model run, the
#        attested images) stay "pending" until recorded; the deploy script refuses anything but "passed".
#   scripts/integration.sh --release-candidate <commit> --external [--logs <dir>]
#        That commit's external set only (--version 3 --external in its worktree, production windows enforced): the
#        SEV-SNP host's chain part of task 7.0 (scripts/rc-aws.sh runs it on the test-chain host; its rehearsal here).
#        It writes ready.json and external.json in <dir>; scripts/rc_aws.py records the items from them.
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
EXTERNAL=0
RC=""
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
    --release-candidate)
      (($# >= 2)) || { echo "integration: --release-candidate needs a commit" >&2; exit 2; }
      RC=$2
      VERSION=3
      shift 2
      ;;
    *)
      [[ "$1" == --with-first-run ]] && FIRST_RUN=1
      [[ "$1" == --radicle ]] && RADICLE=1
      [[ "$1" == --external ]] && EXTERNAL=1
      ARGS+=("$1")
      shift
      ;;
  esac
done
if [[ -n "$RC" ]]; then  # #251 L18: its own worktree at that commit, its own devnet name and port
  [[ "$TARGET" == local ]] || { echo "integration: --release-candidate runs on the local devnet only" >&2; exit 2; }
  exec python3 scripts/release_candidate.py "$RC" "${ARGS[@]}"
fi
case "$VERSION" in
  2) ;;
  3)
    [[ "$TARGET" == local ]] || { echo "integration: --version 3 runs on the local devnet only for now (the AWS devnet is task 5.2 of #132)" >&2; exit 2; }
    if [[ $EXTERNAL == 1 ]]; then  # an outside validator on production windows, the kit's Radicle network (7.0)
      command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "integration: Docker isn't reachable" >&2; exit 2; }
      # shellcheck source=scripts/solc.sh
      source scripts/solc.sh
      [[ -f "$SOLC" ]] || { echo "integration: solc missing; run: scripts/contracts.sh setup" >&2; exit 2; }
      rest=()
      for a in "${ARGS[@]}"; do [[ "$a" == --external ]] || rest+=("$a"); done
      if [[ "${POF_RADICLE_IMAGE_LOADED:-}" == 1 ]]; then  # the test-chain host: loaded from the operator's build,
        docker image inspect pof190-radicle:spike >/dev/null  # checked by image ID (rc-remote.sh provision)
      else
        echo "building the Radicle node image (pinned release, sha256-checked) ..."
        docker build -q -t pof190-radicle:spike spikes/radicle >/dev/null
      fi
      POF_SOLC="$SOLC" exec python3 tests/integration/external_v3.py run "${rest[@]}" </dev/null
    fi
    if [[ $RADICLE == 1 ]]; then  # its own chain and Radicle network, on an internal Docker network (task 4.6)
      command -v docker >/dev/null && docker info >/dev/null 2>&1 || { echo "integration: Docker isn't reachable" >&2; exit 2; }
      # shellcheck source=scripts/solc.sh
      source scripts/solc.sh  # SOLC: the pinned solc, for the deployment inside the anvil container
      [[ -f "$SOLC" ]] || { echo "integration: solc missing; run: scripts/contracts.sh setup" >&2; exit 2; }
      rest=()
      for a in "${ARGS[@]}"; do [[ "$a" == --radicle ]] || rest+=("$a"); done
      echo "building the Radicle node image (pinned release, sha256-checked) ..."
      docker build -q -t pof190-radicle:spike spikes/radicle >/dev/null
      POF_SOLC="$SOLC" exec python3 tests/integration/suite_v3_radicle.py run "${rest[@]}" </dev/null
    fi
    # The same throwaway devnet as v2's run (name, port, state, records), started and removed by devnet-v3-e2e.sh.
    export POF_V3_E2E_NAME=${POF_INTEGRATION_NAME:-pof-devnet-integration} POF_V3_E2E_PORT=${POF_INTEGRATION_PORT:-8556} \
      POF_V3_E2E_STATE=.devnet-integration POF_V3_E2E_RECORDS=integration POF_V3_E2E_WORK=.integration \
      POF_V3_E2E_KEEP=${POF_INTEGRATION_KEEP:-}
    exec scripts/integration-v3.sh "${ARGS[@]}"
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
