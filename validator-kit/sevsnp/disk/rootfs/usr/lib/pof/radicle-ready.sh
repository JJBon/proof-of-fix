#!/usr/bin/env bash
# The validator's Radicle node at each boot, after radicle-node starts and before the oracle node (#251 design L11,
# L12, task 4.9): run as the node's own user. The same script on the SEV-SNP host (pof-radicle.sh ready, from
# pof-radicle-ready.service) and in the test on the internal Docker network (tests/integration/kit_radicle.py).
#
#   radicle-ready.sh <rid> <working copy>
#   radicle-ready.sh                          no repository configured (a boot that only attests): step 1 only
#
# 1. Waits for radicle-node (30 s at most; `rad node status` exits 0 either way in 1.10.3, its first line says which).
# 2. Fetches <rid> from the seed it dialled (`rad sync --fetch`, 30 s at most): every patch, issue, comment and delegate
#    `main` that reached the seed while this host was stopped.
# 3. Makes the working copy the oracle pushes `main` from, again at every boot, from the node's own storage
#    (`rad checkout`: no network), so a boot whose sync failed still has one when the repository was fetched before.
# Prints one line: "ready in <ms> ms (sync: ok|<its error>)", or why not. Exit 0 ready, 1 the node didn't start, 2 bad
# arguments, 3 no working copy (the repository was never fetched: a first boot with the seed unreachable).
set -uo pipefail
rid=${1:-} repo=${2:-}
: "${RAD_HOME:?RAD_HOME must be set: the Radicle home of the node}"
[[ -z "$rid" || "$rid" =~ ^rad:z[1-9A-HJ-NP-Za-km-z]+$ ]] || { echo "radicle-ready: not a Radicle RID: '$rid'" >&2; exit 2; }
[[ -z "$rid" || "$repo" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "radicle-ready: the working copy is an absolute path: '$repo'" >&2; exit 2; }

running() { rad node status 2>/dev/null | grep -q 'Node is running'; }
for _ in $(seq 120); do running && break; sleep 0.25; done
running || { echo "the node didn't start"; exit 1; }
[[ -n "$rid" ]] || { echo "node running; no repository configured"; exit 0; }

started=$(date +%s%N)
sync=ok
if ! out=$(timeout 30 rad sync --fetch "$rid" 2>&1); then
  sync=$(grep -v '^[[:space:]]*$' <<<"$out" | tail -n 1 | cut -c1-200)
fi
tmp="$repo.checkout"
rm -rf "$repo" "$tmp"
mkdir -p "$tmp"
(cd "$tmp" && timeout 30 rad checkout "$rid" --no-confirm >/dev/null 2>&1) || true
made=$(find "$tmp" -mindepth 1 -maxdepth 1 -type d | head -n 1)
[[ -n "$made" ]] && mv "$made" "$repo"
rm -rf "$tmp"
ms=$(( ($(date +%s%N) - started) / 1000000 ))
if [[ -d "$repo/.git" ]]; then
  echo "ready in $ms ms (sync: $sync)"
  exit 0
fi
echo "no working copy after $ms ms (sync: $sync)"
exit 3
