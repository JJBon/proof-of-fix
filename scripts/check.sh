#!/usr/bin/env bash
# The required check "pof / check": OpenSpec documents are valid, the vendored contract libraries are unchanged,
# and the Python tests pass when there are any.
# The OpenSpec CLI runs where it's installed (developers' machines); the CI host has python3 but no Node, so it
# runs only the structural check in scripts/check_openspec.py, which also runs here first.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 scripts/check_openspec.py  # always, so a local run fails where the CI host would
if command -v openspec >/dev/null; then
  openspec validate --all --strict --no-interactive
fi

# The vendored contract libraries are unchanged (proof-of-fix#56); the contract tests need Docker: scripts/contracts.sh.
(cd contracts/lib && sha256sum --check --quiet SHA256SUMS)
# So is the oracle node's vendored cryptography (proof-of-fix#94: python-ecdsa, six, the Keccak reference).
(cd oracle/vendor && sha256sum --check --quiet SHA256SUMS)

# POF_CHECK_BASE (set by the workflow on a pull request, proof-of-fix#208): when every changed file since the merge
# base is documentation no test reads, the Python tests can't be affected and are skipped. Main's run and local runs
# set no base, so they always run everything.
if [[ -n "${POF_CHECK_BASE:-}" ]]; then
  scope=$(python3 scripts/check_scope.py "$POF_CHECK_BASE")
  echo "$scope"
  if [[ "$(tail -1 <<<"$scope")" == docs ]]; then
    echo "check: documentation only; the Python tests are skipped (main runs them all after the merge)"
    exit 0
  fi
fi

if compgen -G "tests/test_*.py" >/dev/null; then
  python3 -m unittest discover -s tests -v
fi
