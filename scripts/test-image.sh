#!/usr/bin/env bash
# The sandbox's test image (#251 L21): oracle/test-image/Dockerfile, the image every fix's tests run in
# (oracle/sandbox.py TEST_IMAGE). A validator builds it here, from the pinned Dockerfile, and loads it into its own
# Docker; the node never pulls it. Nothing is pushed anywhere.
#
#   scripts/test-image.sh                      build this machine's platform, load it, check the digest, print it
#   scripts/test-image.sh --twice              build it twice without Docker's cache first: the digest must repeat
#   scripts/test-image.sh --platform arm64     another platform (amd64 or arm64; under emulation if it isn't this one)
#
# It prints `TEST_IMAGE (<platform>) = pof-test-image@sha256:...` and exits 0 only when the build's digest is the one
# oracle/sandbox.py pins (TEST_IMAGES). An image already loaded under that digest isn't built again (unless --twice).
#
# Reproducible: the base image is pinned by digest and the packages come from one Debian snapshot at pinned versions
# (the Dockerfile); SOURCE_DATE_EPOCH is that snapshot's time and every timestamp in the layers is rewritten to it; no
# provenance or SBOM attestations. Docker's builder rewrites timestamps only in a file, so the build goes to an OCI tar,
# which Docker's containerd image store loads byte for byte, keeping its digest (the classic store would re-encode it):
# the script needs that store (Docker Desktop's default and Docker Engine 29's; on an older engine, daemon.json
# `"features": {"containerd-snapshotter": true}`).
#
# The network it uses: Docker Hub for the pinned base image, snapshot.debian.org for git's packages. The measured disk
# of task 4.9 will carry the image this builds, so an attested validator won't build it at all.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

DOCKERFILE=oracle/test-image/Dockerfile
EPOCH=1793827419  # 2026-11-04T21:23:39Z: the Dockerfile's SNAPSHOT, which the check below holds it to
platform="" twice=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --twice) twice=1 ;;
    --platform) platform=${2:-}; shift ;;
    -h | --help) usage ;;
    *) usage ;;
  esac
  shift
done
platform=${platform:-$(python3 -c 'from oracle.sandbox import _arch; print(_arch())')}
[[ "$platform" == amd64 || "$platform" == arm64 ]] || usage
pinned=$(python3 -c "from oracle.sandbox import TEST_IMAGES; print(TEST_IMAGES['$platform'])")

snapshot=$(sed -n 's/^ARG SNAPSHOT=//p' "$DOCKERFILE")
when=$(python3 -c "import datetime as d; print(d.datetime.fromtimestamp($EPOCH, d.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))")
[[ "$when" == "$snapshot" ]] ||
  { echo "test-image: EPOCH ($EPOCH) isn't the Dockerfile's SNAPSHOT ($snapshot)" >&2; exit 1; }

if [[ -z "$twice" ]] && docker image inspect "$pinned" >/dev/null 2>&1; then
  echo "TEST_IMAGE ($platform) = $pinned (already loaded)"
  exit 0
fi
[[ "$(docker info --format '{{json .DriverStatus}}')" == *containerd.snapshotter* ]] ||
  { echo "test-image: turn on Docker's containerd image store (Docker Desktop: Settings > General; Docker Engine:" \
      'daemon.json "features": {"containerd-snapshotter": true})' >&2; exit 1; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

build() { # dest [extra buildx args...]
  local dest=$1
  shift
  SOURCE_DATE_EPOCH=$EPOCH docker buildx build --platform "linux/$platform" --provenance=false --sbom=false \
    --build-arg SOURCE_DATE_EPOCH -f "$DOCKERFILE" \
    --output "type=oci,dest=$dest,oci-mediatypes=true,rewrite-timestamp=true,name=pof-test-image:$platform" "$@" \
    oracle/test-image >"$dest.log" 2>&1 ||
    { tail -n 30 "$dest.log" >&2; echo "test-image: the build failed" >&2; exit 1; }
}

oci_digest() { # the OCI layout tar's image manifest: the digest Docker's containerd store keeps for it
  tar -xOf "$1" index.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["manifests"][0]["digest"])'
}

if [[ -n "$twice" ]]; then
  build "$WORK/first.tar" --no-cache
  build "$WORK/image.tar" --no-cache
  first=$(oci_digest "$WORK/first.tar") second=$(oci_digest "$WORK/image.tar")
  [[ "$first" == "$second" ]] || { echo "test-image: not reproducible: $first, then $second" >&2; exit 1; }
else
  build "$WORK/image.tar"
fi
built=pof-test-image@$(oci_digest "$WORK/image.tar")
[[ "$built" == "$pinned" ]] ||
  { echo "test-image: the build is $built, not the pinned $pinned (oracle/sandbox.py TEST_IMAGES)" >&2; exit 1; }
docker load -q -i "$WORK/image.tar" >/dev/null
docker image inspect "$pinned" >/dev/null 2>&1 ||
  { echo "test-image: loaded, but Docker doesn't know $pinned" >&2; exit 1; }
# Started once, offline and read-only, as the sandbox starts it: the tools the tests need are there.
out=$(docker run --rm --platform "linux/$platform" --network none --read-only "$pinned" \
  sh -c 'python3 -V && git --version && bash -c "echo bash \$BASH_VERSION"' 2>&1) ||
  { echo "test-image: the image doesn't start: $out" >&2; exit 1; }
echo "TEST_IMAGE ($platform) = $pinned"
