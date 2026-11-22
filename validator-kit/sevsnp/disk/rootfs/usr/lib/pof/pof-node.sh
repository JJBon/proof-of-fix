#!/bin/bash
# One on-demand run of the node (oracle run --until-idle, or the command POF_NODE_COMMAND names), in attested mode,
# only after this boot attested itself; then the instance powers off (POF_POWER_OFF=no keeps it up, for a first test).
# The node's container: the image the disk lists, the Docker socket for the sandbox's sibling containers (the fix's
# code never sees it), the SEV-SNP device for its quotes, the scratch and state folders at the same paths as here, and
# this host's Radicle node (pof-radicle.service): its home (the control socket, the storage, the key the node signs
# its `main` and identity reviews with), the working copy, and the disk's rad and git-remote-rad, so the node's
# `rad` and `git` calls run in its own container on the same storage (ORACLE_RADICLE_EXEC empty: no command prefix).
set -uo pipefail
. /usr/share/pof/images/images.env  # on the measured disk
. /usr/lib/pof/pof-host-env.sh
host_env
off() { [[ "${POF_POWER_OFF:-yes}" == no ]] || systemctl --no-block poweroff; }
if [[ ! -f /run/pof/attest-ok ]]; then echo "pof-node: this boot didn't attest; not running"; off; exit 0; fi
if [[ ! -s /run/pof/node.env ]]; then echo "pof-node: no node configuration in the user data; attest only"; off; exit 0; fi
cmd=${POF_NODE_COMMAND:-run --until-idle 600}
[[ "$cmd" =~ ^(run|info|register|leave|post-table)([[:space:]][A-Za-z0-9\ ._:=/@-]*)?$ ]] ||
  { echo "pof-node: refused POF_NODE_COMMAND"; off; exit 0; }
# shellcheck disable=SC2086
docker run --rm --name pof-node --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --device /dev/sev-guest --group-add 10001 \
  -v /var/run/docker.sock:/var/run/docker.sock --group-add "$(stat -c %g /var/run/docker.sock)" \
  -v /usr/share/pof/images/images.json:/etc/pof/images.json:ro \
  -v /data/scratch/pof-node:/data/scratch/pof-node -v /data/state/pof:/data/state/pof \
  -v /data/state/radicle:/data/state/radicle -v /data/scratch/radicle:/data/scratch/radicle \
  -v /usr/lib/pof/radicle/bin:/opt/radicle/bin:ro \
  --env-file /run/pof/node.env \
  -e ORACLE_ATTESTED_IMAGES=/etc/pof/images.json -e ORACLE_SANDBOX=api -e ORACLE_KEYS=snp \
  -e ORACLE_SRC_ROOT=/data/scratch/pof-node/src -e ORACLE_ROUNDS=/data/state/pof/rounds \
  -e ORACLE_RECEIPTS=/data/state/pof/receipts -e ORACLE_SPEND_LEDGER=/data/state/pof/spend.json \
  -e RAD_HOME=/data/state/radicle -e ORACLE_RADICLE_EXEC= -e ORACLE_RADICLE_REPO=/data/scratch/radicle/repo \
  -e PATH=/opt/radicle/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
  "$NODE_IMAGE" $cmd
echo "pof-node: run ended with $?"
off
