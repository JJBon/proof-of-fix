#!/usr/bin/env bash
# Runs inside a node container (proof-of-fix#190): a throwaway Radicle identity, a node config that knows no public
# seed and dials only the peers it is told to, then the node. The key is generated here and never leaves the
# container.
#
#   node-init.sh <alias>    prints this node's DID (did:key:<Node ID>)
set -euo pipefail
alias=$1

# A throwaway key with no passphrase (a test key, never printed): rad stores it under $RAD_HOME/keys.
RAD_PASSPHRASE="" rad auth --alias "$alias" >/dev/null 2>&1

# The node's config: Radicle's test network (no bootstrap nodes), no preferred seeds, static peers (the driver
# connects them by name; no discovery), listen on the internal network only, and seed every repository it's told
# about from any peer.
cat > "$RAD_HOME/config.json" <<JSON
{
  "publicExplorer": "http://localhost/disabled/\$host/\$rid\$path",
  "preferredSeeds": [],
  "web": {"pinned": {"repositories": []}},
  "cli": {"hints": false},
  "node": {
    "alias": "$alias",
    "listen": ["0.0.0.0:8776"],
    "peers": {"type": "static"},
    "connect": [],
    "externalAddresses": [],
    "network": "test",
    "relay": "auto",
    "seedingPolicy": {"default": "allow", "scope": "all"}
  }
}
JSON
rad node start -- --log-level debug >/dev/null
for _ in $(seq 60); do rad node status >/dev/null 2>&1 && break; sleep 0.5; done
rad self --did
