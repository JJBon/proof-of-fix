#!/usr/bin/env bash
# The checker image as one measured, read-only disk (#251 L21, task 4.9; #253's SEV-SNP kit, validator-kit/sevsnp):
# builds the node image and the test image for linux/amd64, lists them in images.json, and builds the disk
# (validator-kit/sevsnp/disk/Dockerfile): a dm-verity root holding the Docker engine and those images, its root hash on
# the kernel command line inside a UKI, NitroTPM's expected PCRs for that UKI, and the checker image's digest.
#
#   scripts/checker-disk.sh [--out DIR]       build once into DIR (default validator-kit/sevsnp/out), print the manifest
#   scripts/checker-disk.sh --twice           build everything twice without Docker's cache: the root hash, the UKI,
#                                             the disk and the image digest must repeat, byte for byte
#
# The source is the working tree's files (tracked and untracked, minus .gitignore's), through a throwaway index, so the
# real index isn't touched; the manifest names that tree and whether it is HEAD's. Release builds come from a clean
# checkout of the tagged commit, where the two are the same.
#
# Reproducible: the test image as scripts/test-image.sh builds it (pinned base, one Debian snapshot); the node image
# from oracle/Dockerfile with SOURCE_DATE_EPOCH and its timestamps rewritten (the same pinned base and snapshot, git at a
# pinned version; until 2026-11-20 its one moving input was Alpine's unpinned `git`); the disk from pinned inputs with
# fixed UUIDs, salt and timestamps. Needs Docker with buildx and the containerd image store
# (as scripts/test-image.sh), and the network for the pinned downloads. Nothing is pushed anywhere.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

EPOCH=1793827419  # 2026-11-04T21:23:39Z: the Debian snapshot the test image and the disk install from
# No bytecode in the build's source: test-image.sh imports oracle/ there, and a .pyc's bytes (marshal) can differ from
# one run to the next; the node image copies oracle/ as it is.
export PYTHONDONTWRITEBYTECODE=1
out=validator-kit/sevsnp/out twice=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --twice) twice=1 ;;
    --out) out=${2:-}; [[ -n "$out" ]] || usage; shift ;;
    -h | --help) usage ;;
    *) usage ;;
  esac
  shift
done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

worktree_tree() {
  local index=$WORK/index
  cp "$(git rev-parse --git-path index)" "$index"
  GIT_INDEX_FILE=$index git add -A
  GIT_INDEX_FILE=$index git write-tree
}
TREE=$(worktree_tree)
HEAD_TREE=$(git rev-parse 'HEAD^{tree}')
git archive --format=tar -o "$WORK/source.tar" "$TREE"

oci_digest() {
  tar -xOf "$1" index.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["manifests"][0]["digest"])'
}

build_once() { # dest-dir [--no-cache]
  local dest=$1 nocache=${2:-} ctx
  ctx=$(mktemp -d -p "$WORK")
  mkdir -p "$ctx/src" "$ctx/disk"
  tar -xf "$WORK/source.tar" -C "$ctx/src"
  cp -a "$ctx/src/validator-kit/sevsnp/disk/." "$ctx/disk/"
  mkdir -p "$ctx/disk/images"

  # The test image: exactly scripts/test-image.sh's amd64 build (it checks the digest oracle/sandbox.py pins).
  (cd "$ctx/src" && scripts/test-image.sh --platform amd64 --save "$ctx/disk/images/test.tar" ${nocache:+--twice}) >&2
  # The node image: oracle/Dockerfile for amd64, from the same source (and nothing a run left in it).
  find "$ctx/src" -name __pycache__ -type d -prune -exec rm -rf {} +
  SOURCE_DATE_EPOCH=$EPOCH docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
    --build-arg SOURCE_DATE_EPOCH -f oracle/Dockerfile $nocache \
    --output "type=oci,dest=$ctx/disk/images/node.tar,oci-mediatypes=true,rewrite-timestamp=true,name=pof-oracle-node:amd64" \
    "$ctx/src" >"$ctx/node.log" 2>&1 || { tail -n 30 "$ctx/node.log" >&2; echo "checker-disk: the node image's build failed" >&2; exit 1; }
  local node test
  node=pof-oracle-node@$(oci_digest "$ctx/disk/images/node.tar")
  test=pof-test-image@$(oci_digest "$ctx/disk/images/test.tar")
  python3 - "$ctx/disk/images" "$node" "$test" <<'PY'
import json, sys
from pathlib import Path
d, node, test = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
doc = {"format": "pof-images/1", "platform": "amd64",
       "images": [{"name": "node", "ref": node, "archive": "node.tar"},
                  {"name": "test", "ref": test, "archive": "test.tar"}]}
(d / "images.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
(d / "images.env").write_text(f"NODE_IMAGE={node}\nTEST_IMAGE={test}\n")
PY
  # The disk.
  rm -rf "$dest"
  mkdir -p "$dest"
  SOURCE_DATE_EPOCH=$EPOCH docker buildx build --platform linux/amd64 --provenance=false --sbom=false \
    --build-arg SOURCE_DATE_EPOCH $nocache --target out --output "type=local,dest=$dest" "$ctx/disk" \
    >"$ctx/disk.log" 2>&1 || { tail -n 40 "$ctx/disk.log" >&2; echo "checker-disk: the disk's build failed" >&2; exit 1; }
  python3 - "$dest/manifest.json" "$TREE" "$HEAD_TREE" <<'PY'
import json, sys
p, tree, head = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.load(open(p))
m["source"] = {"tree": tree, "is_head": tree == head}
open(p, "w").write(json.dumps(m, indent=1, sort_keys=True) + "\n")
PY
  rm -rf "$ctx"
}

summary() { # manifest
  python3 - "$1" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
print(f"roothash      {m['roothash']}")
print(f"image_digest  {m['image_digest']}   (Validators' accepted image: pof-checker-image/1)")
print(f"pcr4          {m['measured']['pcr4']}")
print(f"pcr7          {m['measured']['pcr7']}")
print(f"pcr12         {m['measured']['pcr12']}")
for n, h in sorted(m["sha256"].items()):
    print(f"sha256 {n:<13} {h}")
for i in m["images"]["images"]:
    print(f"image {i['name']:<8} {i['ref']}")
print(f"kernel        {m['kernel']}; disk {m['disk_gib']} GiB; source tree {m['source']['tree']}"
      f"{'' if m['source']['is_head'] else ' (not HEAD: uncommitted changes)'}")
PY
}

if [[ -n "$twice" ]]; then
  build_once "$WORK/first" --no-cache
  build_once "$out" --no-cache
  a=$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["roothash"], m["image_digest"], json.dumps(m["sha256"], sort_keys=True))' "$WORK/first/manifest.json")
  b=$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m["roothash"], m["image_digest"], json.dumps(m["sha256"], sort_keys=True))' "$out/manifest.json")
  if [[ "$a" != "$b" ]]; then
    echo "checker-disk: not reproducible:" >&2
    echo "  first:  $a" >&2
    echo "  second: $b" >&2
    exit 1
  fi
  echo "checker-disk: two builds without the cache gave the same root hash, UKI, disk and image digest"
else
  build_once "$out"
fi
summary "$out/manifest.json"
