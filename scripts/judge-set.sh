#!/usr/bin/env bash
# B1's labelled set of real fixes (proof-of-fix#85 task 2.1), built in a pinned container (openspec/config.yaml
# rule 4). The container reads public data over HTTPS, anonymously; no key or credential is mounted. The repository
# is mounted read-only except data/judges/, the only place it writes.
#
#   scripts/judge-set.sh select   choose the pairs and write data/judges/manifest.json, then build
#   scripts/judge-set.sh build    rebuild data/judges/cases.jsonl from the committed manifest and check it
set -euo pipefail
cd "$(dirname "$0")/.."

# The same Python image as scripts/bounty-loop.sh (Python 3.12 on Alpine), standard library only.
PYTHON_IMAGE="python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8"

docker image inspect "$PYTHON_IMAGE" >/dev/null 2>&1 || docker pull -q "$PYTHON_IMAGE" >/dev/null
mkdir -p data/judges
docker run --rm --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp \
  -v "$PWD:/work:ro" -v "$PWD/data/judges:/work/data/judges" -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 "$PYTHON_IMAGE" python3 scripts/judge_set.py "$@"
