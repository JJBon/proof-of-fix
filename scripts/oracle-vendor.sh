#!/usr/bin/env bash
# Re-creates oracle/vendor/ from pinned upstream releases (proof-of-fix#94), as scripts/contracts.sh vendor does for
# contracts/lib: each download is checked against the hash pinned here before anything is copied, and the result is
# recorded in oracle/vendor/SHA256SUMS, which scripts/check.sh verifies on every run. Nothing here runs at check time.
#
#   scripts/oracle-vendor.sh          download, verify, copy, write SHA256SUMS
#
# Pure Python only: the required check runs on the CI test runner's Python 3.9 with no pip and no network.
set -euo pipefail
cd "$(dirname "$0")/.."

# python-ecdsa (tlsfuzzer), MIT: secp256k1 ECDSA with RFC 6979 nonces and public-key recovery.
ECDSA_URL=https://files.pythonhosted.org/packages/51/79/119091c98e2bf49e24ed9f3ae69f816d715d2904aefa6a2baa039a2ba0b0/ecdsa-0.19.2-py2.py3-none-any.whl
ECDSA_SHA256=840f5dc5e375c68f36c1a7a5b9caad28f95daa65185c9253c0c08dd952bb7399
# six, MIT: python-ecdsa's only dependency.
SIX_URL=https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/six-1.17.0-py2.py3-none-any.whl
SIX_SHA256=4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274
# The Keccak team's reference implementation (XKCP, by Gilles Van Assche), CC0, at a pinned commit.
KECCAK_COMMIT=712fabccd5d611459533d554814e00537742624c
KECCAK_URL=https://raw.githubusercontent.com/XKCP/XKCP/$KECCAK_COMMIT/Standalone/CompactFIPS202/Python/CompactFIPS202.py
KECCAK_SHA256=0b731097a4dfcf33fdaf395ac0bee81c6a6ebff2975590c35ad8cd8d6f3c204f
# python-ecdsa's modules, without its tests (they need hypothesis and aren't part of the library).
ECDSA_FILES=(__init__.py _compat.py _rwlock.py _sha3.py _version.py curves.py der.py ecdh.py ecdsa.py eddsa.py
  ellipticcurve.py errors.py keys.py numbertheory.py rfc6979.py ssh.py util.py)

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fetch() { # url sha256 file
  curl -fsSL --max-time 120 -o "$tmp/$3" "$1"
  echo "$2  $tmp/$3" | sha256sum --check --quiet
}
fetch "$ECDSA_URL" "$ECDSA_SHA256" ecdsa.whl
fetch "$SIX_URL" "$SIX_SHA256" six.whl
fetch "$KECCAK_URL" "$KECCAK_SHA256" CompactFIPS202.py

python3 -m zipfile -e "$tmp/ecdsa.whl" "$tmp/ecdsa"
python3 -m zipfile -e "$tmp/six.whl" "$tmp/six"

rm -rf oracle/vendor/ecdsa oracle/vendor/six.py oracle/vendor/keccak oracle/vendor/licenses
mkdir -p oracle/vendor/ecdsa oracle/vendor/keccak oracle/vendor/licenses
for f in "${ECDSA_FILES[@]}"; do cp "$tmp/ecdsa/ecdsa/$f" oracle/vendor/ecdsa/; done
cp "$tmp/ecdsa/ecdsa-0.19.2.dist-info/LICENSE" oracle/vendor/licenses/ecdsa-LICENSE
cp "$tmp/six/six.py" oracle/vendor/six.py
cp "$tmp/six/six-1.17.0.dist-info/LICENSE" oracle/vendor/licenses/six-LICENSE
cp "$tmp/CompactFIPS202.py" oracle/vendor/keccak/CompactFIPS202.py

(cd oracle/vendor && find . -type f ! -name SHA256SUMS ! -name README.md ! -name '*.pyc' | LC_ALL=C sort \
  | xargs sha256sum > SHA256SUMS)
echo "oracle/vendor re-created; SHA256SUMS written"
