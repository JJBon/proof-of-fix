#!/usr/bin/env bash
# One real bounty on the AWS devnet (#150, #112): an issue on the target repository, registered, opened and funded;
# failing fixes until the owner's seat has been drawn with its real model; then the passing fix, merged, settled, and the
# fees withdrawn. scripts/first_bounty.py is the flow; this checks the settings and runs it. It sends real transactions
# to the devnet and writes to the repository: the owner runs it, with the seats up (scripts/devnet-seats.sh up) and the
# owner's validator applied. The runbook: validator-kit/runbook.md, "The first real run".
#
#   scripts/first-bounty.sh [--max-fails N] [--fails-only] [--no-settle] ...   (scripts/first_bounty.py --help)
#
# Needs: python3, an OpenBao session for the role keys (bao login -no-print -method=oidc role=admin), and in the environment:
#   DEVNET_RPC_URL         the devnet (https, no credential in it)
#   DEVNET_RPC_AUTH        "<handle>:<key>", or DEVNET_RPC_AUTH_FILE naming a file with it
#   FIRST_BOUNTY_TOKEN     a token that can write to the repository, or FIRST_BOUNTY_TOKEN_FILE naming a file with it:
#                          scopes write:repository and write:issue, from a user with Write on it (it pushes fix branches,
#                          opens the issue and the pull requests, comments, merges). Not pof-validator-bot: that one reads
#   FIRST_BOUNTY_USER      that token's user
# Optional:
#   DEVNET_EXCHANGE_URL, DEVNET_REPO, DEVNET_FORGE_URL, DEVNET_RECORD_V2   as scripts/devnet-seats.sh
#   POFCTL_KEY_ENGINEER    the owner's validator key: then it also withdraws seat 6's fees
#   FIRST_BOUNTY_ANYTIME=1 start even near the night stop (the host stops 01:00-09:00 America/Bogota)
set -euo pipefail
cd "$(dirname "$0")/.."

refuse() { echo "first-bounty: $1" >&2; exit 2; }

URL=${DEVNET_RPC_URL:-}
[[ -n "$URL" ]] || refuse "set DEVNET_RPC_URL"
[[ "$URL" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$ ]] ||
  refuse "DEVNET_RPC_URL must be a plain URL, without a credential in it: use DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE"
if [[ "$URL" == http://* && "${DEVNET_RPC_ALLOW_HTTP:-}" != 1 ]]; then
  refuse "plain HTTP would send the key in the clear: use https:// (DEVNET_RPC_ALLOW_HTTP=1 is for a local test proxy)"
fi
if [[ "${DEVNET_KEYS:-}" == insecure-local && "${DEVNET_RPC_ALLOW_HTTP:-}" != 1 ]]; then
  refuse "DEVNET_KEYS=insecure-local are public keys: anyone could sign for these seats on a shared devnet"
fi
AUTH=${DEVNET_RPC_AUTH:-}
if [[ -z "$AUTH" && -n "${DEVNET_RPC_AUTH_FILE:-}" ]]; then
  [[ -r "$DEVNET_RPC_AUTH_FILE" ]] || refuse "can't read DEVNET_RPC_AUTH_FILE"
  AUTH=$(<"$DEVNET_RPC_AUTH_FILE")
fi
unset DEVNET_RPC_AUTH
[[ -n "$AUTH" ]] || refuse "no credential: set DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE (<handle>:<key>)"
[[ "$AUTH" =~ ^[^:[:space:]]+:[^[:space:]]+$ ]] || refuse "the credential must look like <handle>:<key> (not printed)"
TOKEN=${FIRST_BOUNTY_TOKEN:-}
if [[ -z "$TOKEN" && -n "${FIRST_BOUNTY_TOKEN_FILE:-}" ]]; then
  [[ -r "$FIRST_BOUNTY_TOKEN_FILE" ]] || refuse "can't read FIRST_BOUNTY_TOKEN_FILE"
  TOKEN=$(<"$FIRST_BOUNTY_TOKEN_FILE")
fi
unset FIRST_BOUNTY_TOKEN
TOKEN=${TOKEN//[[:space:]]/} # a paste can bring a line ending along
[[ -n "$TOKEN" ]] || refuse "no repository token: set FIRST_BOUNTY_TOKEN or FIRST_BOUNTY_TOKEN_FILE (scopes write:repository and write:issue)"
FORGE_USER=${FIRST_BOUNTY_USER:-}
[[ -n "$FORGE_USER" ]] || refuse "set FIRST_BOUNTY_USER: the token's user"
if [[ "${FIRST_BOUNTY_ANYTIME:-}" != 1 ]]; then
  # The host stops at 01:00: a round across it loses its nodes' state, and a whole run can take over an hour.
  hour=$(TZ=America/Bogota date +%H)
  [[ "${hour#0}" -ge 9 && "${hour#0}" -lt 23 ]] ||
    refuse "it's ${hour}h in Bogota: the devnet stops 01:00-09:00. Start between 09:00 and 23:00 (FIRST_BOUNTY_ANYTIME=1 overrides)"
fi

# In this process's environment only: pofctl reads the RPC key and the forge's token by name.
POFCTL_RPC=$URL POFCTL_RPC_TOKEN=$AUTH POFCTL_RPC_AUTH=Basic FORGEJO_TOKEN=$TOKEN FORGEJO_USER=$FORGE_USER \
  PYTHONDONTWRITEBYTECODE=1 exec python3 scripts/first_bounty.py \
  --record "${DEVNET_RECORD_V2:-contracts/deployments/devnet-aws-v2.json}" \
  --repo "${DEVNET_REPO:-example-org/pof-sandbox}" \
  --forge "${DEVNET_FORGE_URL:-https://git.example.com}" \
  --exchange "${DEVNET_EXCHANGE_URL:-${URL%/}/exchange}" "$@"
