#!/usr/bin/env bash
# The exchange relay's image for the AWS devnet's host (#150, platform-197): a linux/arm64 build of exchange/Dockerfile
# from a clean checkout, pushed to the host's private ECR repository, and its digest printed for platform's
# exchange_image_digest. The owner runs it, with Docker (buildx) and an administrator's AWS profile for the host's account.
#
#   AWS_PROFILE=<profile> scripts/exchange-image.sh <repository url>     build, push, print the digest
#   scripts/exchange-image.sh --build-only                               build for arm64 and start it once: nothing pushed
#
# The repository URL is platform's output: cd environments/prod/us-east-1/pof-devnet && tofu output -raw exchange_repository_url
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == --build-only ]]; then
  tag=pof-exchange-arm64-check:$$
  docker buildx build -q --platform linux/arm64 --provenance=false --load -f exchange/Dockerfile -t "$tag" . >/dev/null
  trap 'docker image rm "$tag" >/dev/null 2>&1 || true' EXIT
  # Under emulation: without EXCHANGE_RPC the service prints its usage and exits 2, once its code has been imported.
  rc=0
  docker run --rm --platform linux/arm64 --network none --read-only "$tag" >/dev/null || rc=$?
  [[ "$rc" == 2 ]] || { echo "exchange-image: the arm64 image exited $rc" >&2; exit 1; }
  echo "the arm64 image builds and starts"
  exit 0
fi

repo=${1:-}
[[ "$repo" =~ ^([0-9]+\.dkr\.ecr\.([a-z0-9-]+)\.amazonaws\.com)/([a-z0-9._/-]+)$ ]] ||
  { sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }
registry=${BASH_REMATCH[1]} region=${BASH_REMATCH[2]} name=${BASH_REMATCH[3]}
[[ -z "$(git status --porcelain -- exchange oracle)" ]] || { echo "exchange-image: exchange/ or oracle/ has changes: an image must come from a commit" >&2; exit 1; }
tag=arm64-$(git rev-parse --short=7 HEAD)
aws ecr get-login-password --region "$region" | docker login --username AWS --password-stdin "$registry" >/dev/null
# An image plain enough for the host's compose to pull by digest: one manifest, no attestations.
docker buildx build --platform linux/arm64 --provenance=false --sbom=false -f exchange/Dockerfile -t "$repo:$tag" --push .
digest=$(aws ecr describe-images --region "$region" --repository-name "$name" --image-ids "imageTag=$tag" \
  --query 'imageDetails[0].imageDigest' --output text)
echo "pushed $tag"
echo "exchange_image_digest = \"$digest\""
