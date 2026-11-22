#!/usr/bin/env bash
# The proof-of-fix seed's Radicle setup (#251 design L14, task 5.3): run as the seed's own user, with radicle-node
# stopped, before the node starts. It is the same script on the AWS host (seed/radicle/install.sh runs it from
# cloud-init) and in the test on the internal Docker network (tests/integration/seed_radicle.py).
#
#   seed-setup.sh <rid> <alias> <external-address> [main|test]
#
# 1. The node's key: made once (no passphrase: the seed signs nothing for the project, it is not a delegate), kept in
#    $RAD_HOME/keys, never printed. A rerun keeps it, so the Node ID stays the same.
# 2. The node's config: seed/radicle/config.json with its placeholders filled. Its seeding policy is "block" by
#    default: the node fetches, stores and serves no repository it has no policy for.
# 3. The one policy: seed <rid> (scope "all": every peer's refs, so solvers' patches and the seats' `main` too) and
#    unseed anything else, so the seed serves proof-of-fix's RID and refuses every other repository.
#
# The RID comes from the publication record (seed/README.md), written at the Radicle publish (task 6.2); nothing in
# this folder names it before then. Prints this node's DID.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
rid=${1:-} alias=${2:-} external=${3:-} network=${4:-main}
: "${RAD_HOME:?RAD_HOME must be set: the Radicle home of the seed}"

die() { echo "seed-setup: $*" >&2; exit 2; }
[[ "$rid" =~ ^rad:z[1-9A-HJ-NP-Za-km-z]+$ ]] || die "not a Radicle RID: '$rid'"
[[ "$alias" =~ ^[A-Za-z0-9._-]{1,32}$ ]] || die "bad alias: '$alias'"
[[ "$external" =~ ^[A-Za-z0-9.-]{1,253}:[0-9]{1,5}$ ]] || die "the external address is host:port: '$external'"
[[ "$network" == main || "$network" == test ]] || die "network is main or test: '$network'"
[[ -f "$here/config.json" ]] || die "no config.json beside this script"
# `rad node status` exits 0 whether the node runs or not (1.10.3), so a rerun with the node stopped (install.sh stops
# it first) was refused; its first line says which.
running() { rad node status 2>/dev/null | grep -q 'Node is running'; }
if running; then die "stop radicle-node first: the policy is set with the node stopped"; fi

# 1. The key.
mkdir -p "$RAD_HOME"
chmod 0700 "$RAD_HOME"
if [[ ! -f "$RAD_HOME/keys/radicle" ]]; then
  RAD_PASSPHRASE="" rad auth --alias "$alias" >/dev/null 2>&1 || die "rad auth failed"
fi

# 2. The config (the inputs were checked above, so they are safe in sed).
sed -e "s|@ALIAS@|$alias|" -e "s|@EXTERNAL_ADDRESS@|$external|" -e "s|@NETWORK@|$network|" \
  "$here/config.json" >"$RAD_HOME/config.json.new"
if grep -q '@[A-Z_]*@' "$RAD_HOME/config.json.new"; then die "a placeholder is left in the config"; fi
mv "$RAD_HOME/config.json.new" "$RAD_HOME/config.json"

# 3. The policy: this RID, and nothing else.
rad seed "$rid" --scope all --no-fetch >/dev/null
for other in $(rad seed 2>/dev/null | grep -oE 'rad:z[1-9A-HJ-NP-Za-km-z]+' | sort -u); do
  [[ "$other" == "$rid" ]] || rad unseed "$other" >/dev/null
done
seeded=$(rad seed 2>/dev/null | grep -oE 'rad:z[1-9A-HJ-NP-Za-km-z]+' | sort -u | tr '\n' ' ')
[[ "$seeded" == "$rid " ]] || die "the seeding policies are '$seeded', not just $rid"
rad self --did
