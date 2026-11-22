#!/usr/bin/env bash
# The validator's Radicle node setup (#251 design L11, L12, task 4.9): run as the node's own user, with radicle-node
# stopped, before it starts, at every boot. The same script on the SEV-SNP host (pof-radicle.sh runs it from
# pof-radicle.service) and in the test on the internal Docker network (tests/integration/kit_radicle.py).
#
#   radicle-setup.sh <alias> <main|test> [<rid> <seed>[,<seed>...]]
#
# 1. The node's key: made once, in $RAD_HOME/keys (the data volume on the host, never the measured disk), with no
#    passphrase (radicle-node and the oracle's `rad` calls sign unattended), never printed. A rerun keeps it, so the
#    Node ID the validator registered on-chain (`radNodeOf`) stays this node's.
# 2. The node's config: radicle-config.json beside this script with its placeholders filled. Outbound only: it listens
#    on no address and announces none, and dials the seed(s) given (`connect`, "<nid>@<host>:<port>"); the seed relays
#    its patches, issues and signed refs both ways over that connection. Its seeding policy is "block" by default.
# 3. The one policy, when a RID is given: seed <rid> with scope "all" (every peer's refs: solvers' patches, reporters'
#    issues, the other delegates' `main`) and unseed anything else.
# Without a RID (a boot that only attests) it makes the key and the config with no peer, so the operator can read the
# Node ID before registering. Prints this node's DID.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
alias=${1:-} network=${2:-} rid=${3:-} seeds=${4:-}
: "${RAD_HOME:?RAD_HOME must be set: the Radicle home of the node}"

die() { echo "radicle-setup: $*" >&2; exit 2; }
nid_re='z6Mk[1-9A-HJ-NP-Za-km-z]{40,50}'
[[ "$alias" =~ ^[A-Za-z0-9._-]{1,32}$ ]] || die "bad alias: '$alias'"
[[ "$network" == main || "$network" == test ]] || die "network is main or test: '$network'"
[[ -z "$rid" || "$rid" =~ ^rad:z[1-9A-HJ-NP-Za-km-z]+$ ]] || die "not a Radicle RID: '$rid'"
[[ -z "$rid" || -n "$seeds" ]] || die "a RID needs the seed to fetch it from: <nid>@<host>:<port>"
connect=""
if [[ -n "$seeds" ]]; then
  IFS=, read -r -a list <<<"$seeds"
  [[ ${#list[@]} -le 4 ]] || die "at most 4 seeds"
  for s in "${list[@]}"; do
    [[ "$s" =~ ^${nid_re}@[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$ ]] || die "a seed is <nid>@<host>:<port>: '$s'"
    connect+="${connect:+, }\"$s\""
  done
fi
[[ -f "$here/radicle-config.json" ]] || die "no radicle-config.json beside this script"
# `rad node status` exits 0 whether the node runs or not (1.10.3): its first line says which.
running() { rad node status 2>/dev/null | grep -q 'Node is running'; }
if running; then die "stop radicle-node first: the policy is set with the node stopped"; fi

# 1. The key.
mkdir -p "$RAD_HOME"
chmod 0700 "$RAD_HOME"
if [[ ! -f "$RAD_HOME/keys/radicle" ]]; then
  RAD_PASSPHRASE="" rad auth --alias "$alias" >/dev/null 2>&1 || die "rad auth failed"
fi

# 2. The config (the inputs were checked above, so they are safe in sed).
sed -e "s|@ALIAS@|$alias|" -e "s|@NETWORK@|$network|" -e "s|@CONNECT@|$connect|" \
  "$here/radicle-config.json" >"$RAD_HOME/config.json.new"
if grep -q '@[A-Z_]*@' "$RAD_HOME/config.json.new"; then die "a placeholder is left in the config"; fi
mv "$RAD_HOME/config.json.new" "$RAD_HOME/config.json"

# 3. The policy: this RID, and nothing else.
if [[ -n "$rid" ]]; then
  rad seed "$rid" --scope all --no-fetch >/dev/null
fi
for other in $(rad seed 2>/dev/null | grep -oE 'rad:z[1-9A-HJ-NP-Za-km-z]+' | sort -u); do
  [[ "$other" == "$rid" ]] || rad unseed "$other" >/dev/null
done
seeded=$(rad seed 2>/dev/null | grep -oE 'rad:z[1-9A-HJ-NP-Za-km-z]+' | sort -u | tr '\n' ' ' || true)  # none: ""
[[ "$seeded" == "${rid:+$rid }" ]] || die "the seeding policies are '$seeded', not just ${rid:-none}"
rad self --did
