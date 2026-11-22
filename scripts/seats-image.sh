#!/usr/bin/env bash
# The AWS devnet's seats host's images (#152, infra#219): linux/arm64 builds from a clean commit, pushed to the host's
# private ECR repositories, and their digests printed for platform's variables. The owner runs it, with Docker (buildx)
# and an administrator's AWS profile for the platform account. Nothing else pushes them.
#
#   AWS_PROFILE=<profile> scripts/seats-image.sh node <repository url>      the seats' node (and #210's bot): oracle/Dockerfile
#   AWS_PROFILE=<profile> scripts/seats-image.sh watcher <repository url>   the watcher's Lambda: validator-kit/lambda/Dockerfile
#   scripts/seats-image.sh --build-only [node|watcher]   build for arm64 twice (the digest must repeat), start it once:
#                                                        nothing pushed; the working tree's files, committed or not
#
# Each prints `node_image_digest = "sha256:..."` or `watcher_image_digest = "..."` for the stack's variables. The
# repository URLs are platform's outputs, in environments/prod/us-east-1/pof-devnet:
#   tofu output -raw seats_node_repository_url     tofu output -raw seats_watcher_repository_url
#
# Reproducible: the build context is `git archive` of the commit (or of the working tree's files, for --build-only),
# never the directory itself; the base images are pinned by digest; SOURCE_DATE_EPOCH is the commit's time and every
# timestamp in the layers is rewritten to it. So the same commit gives the same digest; the node image's one moving input
# is Alpine's `git` package (apk), which changes only when Alpine publishes a new one, so every build here runs without
# Docker's cache: a cached layer could be older than what a rebuild of the commit gets. The tag is arm64-<short sha>; the
# repositories' tags are immutable, so a commit already pushed is reported, not pushed again.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

image_spec() { # name -> DOCKERFILE PATHS (what it copies) VARIABLE
  case "$1" in
    node) DOCKERFILE=oracle/Dockerfile PATHS=(oracle pof bot pofctl scripts/judge_run.py) VARIABLE=node_image_digest ;;
    watcher) DOCKERFILE=validator-kit/lambda/Dockerfile PATHS=(validator-kit/lambda) VARIABLE=watcher_image_digest ;;
    *) usage ;;
  esac
  PATHS+=("$DOCKERFILE")
}

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
# shellcheck source=scripts/ecr-login.sh
source scripts/ecr-login.sh

# The build context: a tar of a git tree. HEAD's for a push; for --build-only, the working tree's files (tracked and
# untracked, minus .gitignore's) through a throwaway index, so the real index isn't touched.
context() { # tree-ish -> $WORK/context.tar
  git archive --format=tar -o "$WORK/context.tar" "$1"
}

worktree_tree() {
  local index=$WORK/index
  cp "$(git rev-parse --git-path index)" "$index"
  GIT_INDEX_FILE=$index git add -A
  GIT_INDEX_FILE=$index git write-tree
}

build() { # output-spec [extra buildx args...]: the context on stdin, the Dockerfile inside it
  local output=$1
  shift
  SOURCE_DATE_EPOCH=$EPOCH docker buildx build --platform linux/arm64 --provenance=false --sbom=false \
    --build-arg SOURCE_DATE_EPOCH -f "$DOCKERFILE" --output "$output" "$@" - <"$WORK/context.tar"
}

oci_digest() { # the OCI layout tar's image manifest: the digest a push of the same build gets
  tar -xOf "$1" index.json | python3 -c 'import json,sys; print(json.load(sys.stdin)["manifests"][0]["digest"])'
}

smoke() { # name image: start it once, offline, under emulation on a non-arm64 machine
  local rc=0 out
  case "$1" in
    node)
      # Its code and pofctl's (the bot's, #210) import; then, without ORACLE_RPC, the seat's entry refuses (exit 2).
      out=$(docker run --rm --platform linux/arm64 --network none --read-only --entrypoint python3 "$2" \
        -c 'import pofctl.cli, oracle.seat, bot.forge; print("ok")' 2>&1) || rc=$?
      [[ "$rc" == 0 && "$out" == ok ]] || { echo "seats-image: the node image can't import its code: $out" >&2; exit 1; }
      rc=0
      docker run --rm --platform linux/arm64 --network none --read-only "$2" seat run >/dev/null 2>&1 || rc=$?
      [[ "$rc" == 2 ]] || { echo "seats-image: the node image's seat entry exited $rc, not 2, without a config" >&2; exit 1; }
      ;;
    watcher)
      # The kill switch: the handler answers without a key, the chain or AWS, once boto3 and the watcher import.
      out=$(docker run --rm --platform linux/arm64 --network none --entrypoint python3 -e ENABLED=false \
        -w /var/task "$2" -c 'import watcher; print(watcher.handler({}, None)["action"])' 2>&1 | tail -n 1) || rc=$?
      [[ "$rc" == 0 && "$out" == disabled ]] || { echo "seats-image: the watcher image didn't answer: $out" >&2; exit 1; }
      ;;
  esac
}

build_only() {
  local name=$1 first second tag=pof-seats-$1-arm64-check:$$
  image_spec "$name"
  context "$(worktree_tree)"
  EPOCH=$(git log -1 --format=%ct)
  build "type=oci,dest=$WORK/$name-1.tar,oci-mediatypes=true,rewrite-timestamp=true" -q --no-cache >/dev/null
  build "type=oci,dest=$WORK/$name-2.tar,oci-mediatypes=true,rewrite-timestamp=true" -q --no-cache >/dev/null
  first=$(oci_digest "$WORK/$name-1.tar") second=$(oci_digest "$WORK/$name-2.tar")
  [[ "$first" == "$second" ]] || { echo "seats-image: $name isn't reproducible: $first, then $second" >&2; exit 1; }
  # Run what was built: the same build, loaded into the local engine under a throwaway tag.
  build "type=docker,name=$tag" -q >/dev/null
  smoke "$name" "$tag"
  docker image rm "$tag" >/dev/null 2>&1 || true
  echo "$name: the arm64 image builds the same twice and starts; a push of this tree would be $first"
}

if [[ "${1:-}" == --build-only ]]; then
  case "${2:-all}" in
    all) build_only node; build_only watcher ;;
    node | watcher) build_only "$2" ;;
    *) usage ;;
  esac
  exit 0
fi

name=${1:-}
image_spec "$name"
repo=${2:-}
[[ "$repo" =~ ^([0-9]+\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com)/([a-z0-9._/-]+)$ ]] || usage
registry=${BASH_REMATCH[1]} region=${BASH_REMATCH[2]} repo_name=${BASH_REMATCH[3]}
[[ -z "$(git status --porcelain -- "${PATHS[@]}")" ]] ||
  { echo "seats-image: ${PATHS[*]} has changes: an image must come from a commit" >&2; exit 1; }
tag=arm64-$(git rev-parse --short=7 HEAD)
existing() {
  aws ecr describe-images --region "$region" --repository-name "$repo_name" --image-ids "imageTag=$tag" \
    --query 'imageDetails[0].imageDigest' --output text 2>/dev/null || true
}
digest=$(existing)
if [[ "$digest" == sha256:* ]]; then
  echo "$tag is already in $repo_name (tags are immutable): not pushed again"
else
  # Docker's own builder can't rewrite the timestamps of an image it stores, only of a file: so the build goes to an
  # OCI tar, which Docker's containerd image store loads and pushes byte for byte (the classic store would re-encode it).
  [[ "$(docker info --format '{{json .DriverStatus}}')" == *containerd.snapshotter* ]] ||
    { echo "seats-image: turn on Docker's containerd image store (Docker Desktop: Settings > General)" >&2; exit 1; }
  context HEAD
  EPOCH=$(git log -1 --format=%ct)
  # One manifest, no attestations: plain enough for Lambda and for the host's `docker pull` by digest.
  # No cache: a layer cached on another day could hold an older Alpine package than a rebuild of this commit gets.
  build "type=oci,dest=$WORK/$name.tar,oci-mediatypes=true,rewrite-timestamp=true" --no-cache
  built=$(oci_digest "$WORK/$name.tar")
  docker load -q -i "$WORK/$name.tar" >/dev/null
  docker tag "$built" "$repo:$tag"
  ecr_login "$region" "$registry" "$WORK"  # a throwaway Docker config: scripts/ecr-login.sh (#213)
  docker push -q --platform linux/arm64 "$repo:$tag" >/dev/null
  docker image rm "$repo:$tag" >/dev/null 2>&1 || true
  digest=$(existing)
  [[ "$digest" == sha256:* ]] || { echo "seats-image: pushed, but ECR doesn't list $tag" >&2; exit 1; }
  [[ "$digest" == "$built" ]] || { echo "seats-image: ECR has $digest for $tag, not the build's $built" >&2; exit 1; }
  echo "pushed $tag"
fi
echo "$VARIABLE = \"$digest\""
