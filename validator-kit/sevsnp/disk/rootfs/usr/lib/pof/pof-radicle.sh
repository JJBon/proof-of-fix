#!/bin/bash
# This validator's Radicle node on the measured disk (#251 L11, L12, task 4.9), as root:
#   pof-radicle.sh setup   pof-radicle-setup.service, before radicle-node (pof-radicle.service) starts: the RID
#                          (ORACLE_RADICLE_RID, the node's settings) and the seed (POF_RADICLE_SEED,
#                          "<nid>@<host>:8776", the host's) from the user data, then radicle-setup.sh as the node's
#                          user (uid 10001): the key made once on the data volume, the outbound-only config, the one
#                          seeding policy. Prints the Node ID on the serial console (`POF-RADICLE nid z6Mk…`, its
#                          `rad self --nid`): the key the registration names (`register --rad-node`).
#   pof-radicle.sh ready   pof-radicle-ready.service, after radicle-node starts and before the node: radicle-ready.sh
#                          as the node's user: waits for it, fetches the repository from the seed, and makes the
#                          working copy the oracle pushes `main` from (ORACLE_RADICLE_REPO, on the scratch disk: made
#                          again at every boot from the node's storage, so no git config or hook persists in it).
# radicle-node itself runs as uid 10001, the node container's user: the container reaches it through its control
# socket and runs `rad` and `git` on the same storage (pof-node.sh mounts both; ORACLE_RADICLE_EXEC is empty).
set -uo pipefail
. /usr/lib/pof/pof-host-env.sh
host_env
RAD_HOME=/data/state/radicle
BIN=/usr/lib/pof/radicle/bin
REPO=/data/scratch/radicle/repo
say() { echo "POF-RADICLE $*"; }  # the units send it to the serial console
as_node() { setpriv --reuid=10001 --regid=10001 --clear-groups env -i HOME="$RAD_HOME" RAD_HOME="$RAD_HOME" \
  PATH="$BIN:/usr/bin:/bin" "$@"; }
rid=$(sed -n 's/^ORACLE_RADICLE_RID=//p' /run/pof/node.env 2>/dev/null | tail -n 1)
seed=${POF_RADICLE_SEED:-}

case "${1:-}" in
  setup)
    if [[ -n "$rid" && -z "$seed" ]]; then say "warning: ORACLE_RADICLE_RID without POF_RADICLE_SEED: no peer"; rid=""; fi
    if ! did=$(as_node bash /usr/lib/pof/radicle-setup.sh pof-validator main "$rid" "$seed" 2>&1); then
      say "setup failed: $(tr '\n' ' ' <<<"$did")"
      exit 1
    fi
    nid=$(as_node rad self --nid 2>/dev/null) || nid=""
    [[ "$nid" =~ ^z6Mk[1-9A-HJ-NP-Za-km-z]{40,50}$ ]] || { say "setup failed: no Node ID (rad self --nid: '$nid')"; exit 1; }
    say "nid $nid"
    say "repository ${rid:-none}; seed ${seed:-none}; listens on no address (outbound only)"
    ;;
  ready)
    [[ -n "$seed" ]] || rid=""  # setup gave the node no peer
    out=$(cd /data/scratch/radicle && as_node bash /usr/lib/pof/radicle-ready.sh "$rid" "$REPO" 2>&1)
    code=$?
    say "ready: ${rid:-no repository}: $(tr '\n' ' ' <<<"$out")"
    [[ $code == 0 ]] || say "ready: the node will retry its own reads (exit $code)"
    ;;
  *) echo "usage: pof-radicle.sh setup|ready" >&2; exit 2 ;;
esac
