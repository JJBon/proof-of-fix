#!/usr/bin/env bash
# The v3 integration suite (proof-of-fix#256): what scripts/integration.sh --version 3 runs, one throwaway devnet after
# another (scripts/devnet-v3-e2e.sh starts each and removes it at its end, pass or fail):
#   story        tests/integration/suite_v3.py on #132's defaults (every panel cap strict, kTop 7, larger challenges):
#                registration and qualification, the k = 1 hold, a waiting bounty, a silent judge, k = 5, a challenge
#                reversed, the head at finality, protected tests (#251 L20); --heal adds the time to heal
#   launch       tests/integration/scenarios_v3.py --set launch, the Sepolia record's rules (caps `launch`, kTop 3,
#                `same`): scenarios u, w and v (#251 task 3.27; L23, L24, L25), 7 then 15 validators
#   few-larger   --set few-larger (#132's defaults, one model family): scenarios f and g, D27's second draw
#   few-same     --set few-same (the launch's rules, one model family): scenarios f and g
# Every set deploys production windows (#251 L4) and moves the chain's clock to the next deadline.
#
#   scripts/integration-v3.sh [--sets story,launch,few-larger,few-same] [--heal] [--verbose] [--report <file>]
#                             [--report-dir <dir>]
# --report, --heal and any other option are the story's (as before); --report-dir writes every set's numbers there
# (<set>.json). The settings come from scripts/integration.sh (POF_V3_E2E_*). It goes on after a set fails and exits 1
# if any did; the last line names each set's result.
set -euo pipefail
cd "$(dirname "$0")/.."
SETS=(story launch few-larger few-same)
STORY=()
COMMON=()
DIR=""
while (($#)); do
  case "$1" in
    --sets | --scenarios)
      (($# >= 2)) || { echo "integration-v3: $1 needs a list: story,launch,few-larger,few-same" >&2; exit 2; }
      IFS=, read -r -a SETS <<<"$2"
      shift 2
      ;;
    --report-dir)
      (($# >= 2)) || { echo "integration-v3: --report-dir needs a directory" >&2; exit 2; }
      DIR=$2
      shift 2
      ;;
    --verbose) COMMON+=("$1"); STORY+=("$1"); shift ;;
    --heal) STORY+=("$1"); shift ;;
    --report)
      (($# >= 2)) || { echo "integration-v3: --report needs a file" >&2; exit 2; }
      STORY+=("$1" "$2")
      shift 2
      ;;
    *) STORY+=("$1"); shift ;;  # the story's own options (--profile <file>), checked by it
  esac
done
for s in "${SETS[@]}"; do
  case "$s" in story | launch | few-larger | few-same) ;; *) echo "integration-v3: unknown set $s" >&2; exit 2 ;; esac
done
[[ -z "$DIR" ]] || mkdir -p "$DIR"
results=()
code=0
for s in "${SETS[@]}"; do
  echo
  echo "=== v3 set: $s ==="
  started=$SECONDS
  if [[ "$s" == story ]]; then
    report=()
    [[ -z "$DIR" ]] || report=(--report "$DIR/story.json")
    scripts/devnet-v3-e2e.sh "${STORY[@]}" "${report[@]}" && r=passed || r=failed
  else
    report=()
    [[ -z "$DIR" ]] || report=(--report "$DIR/$s.json")
    scripts/devnet-v3-e2e.sh --set "$s" "${COMMON[@]}" "${report[@]}" && r=passed || r=failed
  fi
  [[ "$r" == passed ]] || code=1
  results+=("$s $r $((SECONDS - started))s")
done
echo
echo "v3 integration: $(IFS=';'; echo "${results[*]}" | sed 's/;/; /g')"
exit $code
