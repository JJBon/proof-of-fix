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

if compgen -G "tests/test_*.py" >/dev/null; then
  python3 -m unittest discover -s tests -v
fi
