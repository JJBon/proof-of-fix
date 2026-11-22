#!/bin/bash
# Loads the measured disk's images into Docker's empty store (containerd's image store keeps each archive's digest) and
# checks that the store then holds exactly the listed images, each under its listed digest. Nothing is pulled: no
# registry is configured, and the node in attested mode never asks for one (oracle/sandbox.py).
set -euo pipefail
cd /usr/share/pof/images
say() { echo "pof-images: $*"; }
mapfile -t listed < <(sed -n 's/^[A-Z]*_IMAGE=//p' images.env)
for line in $(grep -E '^[A-Z]+_IMAGE=' images.env); do
  name=${line%%_IMAGE=*} ref=${line#*=}
  archive=$(tr 'A-Z' 'a-z' <<<"$name").tar
  docker load -q -i "$archive" >/dev/null
  id=$(docker image inspect --format '{{.Id}}' "$ref") || { say "setup error: $ref isn't in the store after loading $archive"; exit 1; }
  [[ "$id" == "${ref#*@}" ]] || docker image inspect --format '{{json .RepoDigests}}' "$ref" | grep -qF "\"$ref\"" ||
    { say "setup error: $ref loaded as $id"; exit 1; }
  say "loaded $ref"
done
count=$(docker image ls -q --no-trunc | sort -u | wc -l)
[[ "$count" == "${#listed[@]}" ]] || { say "setup error: the store holds $count images, the list ${#listed[@]}"; exit 1; }
