#!/usr/bin/env bash
# Builds the zkTLS spike's tools (proof-of-fix#135) from a pinned TLSNotary release, outside the repository.
#
# It clones tlsn at TLSN_TAG (checked against TLSN_COMMIT), adds rust/pof_*.rs as examples of the release's own
# examples crate (so the release's Cargo.lock pins every dependency; cargo only adds bcs and blake3, already locked,
# to that crate's own list), and builds them with low priority.
#   BUILD_DIR (default ~/pof-135-build): the clone and the cargo target directory.
# Needs rustup with Rust 1.95 (the release's mpz dependencies require it); no system packages, no Docker.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TLSN_TAG="v0.1.0-alpha.15"
TLSN_COMMIT="47aee45b53e06648c1b2ad3689b367b8c923fdec"
RUST="1.95.0"
BUILD_DIR="${BUILD_DIR:-$HOME/pof-135-build}"
SRC="$BUILD_DIR/tlsn-src"
JOBS="${JOBS:-4}"

mkdir -p "$BUILD_DIR"
if [ ! -d "$SRC/.git" ]; then
  git clone -q --depth 1 --branch "$TLSN_TAG" https://github.com/tlsnotary/tlsn "$SRC"
fi
got="$(git -C "$SRC" rev-parse HEAD)"
[ "$got" = "$TLSN_COMMIT" ] || { echo "tlsn is at $got, expected $TLSN_COMMIT ($TLSN_TAG)" >&2; exit 1; }

EX="$SRC/crates/examples"
mkdir -p "$EX/pof"
cp "$HERE"/rust/pof_*.rs "$EX/pof/"
python3 - "$EX/Cargo.toml" <<'EOF'
import sys
p = sys.argv[1]
s = open(p).read()
if '"mozilla-certs"' not in s:
    s = s.replace('tlsn = { workspace = true }', 'tlsn = { workspace = true, features = ["mozilla-certs"] }', 1)
if "\nbcs = " not in s:
    s = s.replace("anyhow = { workspace = true }", "anyhow = { workspace = true }\nbcs = { workspace = true }\nblake3 = { workspace = true }", 1)
for name in ("pof_notary", "pof_prove", "pof_verify"):
    if f'name = "{name}"' not in s:
        s += f'\n[[example]]\nname = "{name}"\npath = "pof/{name}.rs"\n'
open(p, "w").write(s)
EOF

rustup toolchain list | grep -q "^$RUST" || rustup toolchain install "$RUST" --profile minimal
cd "$SRC"
CARGO_TARGET_DIR="$BUILD_DIR/target" nice -n 19 cargo "+$RUST" build --release -j "$JOBS" -p tlsn-examples \
  --example pof_notary --example pof_prove --example pof_verify
echo "built: $BUILD_DIR/target/release/examples/{pof_notary,pof_prove,pof_verify}"
