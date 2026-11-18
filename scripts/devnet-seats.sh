#!/usr/bin/env bash
# The role seats' nodes (#150): one real node process per role seat (oracle-0..4, joiner-0) on this machine, against a
# devnet that runs elsewhere (the AWS devnet) and its hosted exchange relay, in the owner's session, for a first real
# run. Seat 6 is the owner's own validator (validator-kit): not started here.
#
#   scripts/devnet-seats.sh up       check everything, then run the nodes in the foreground until Ctrl-C
#   scripts/devnet-seats.sh status   which nodes are running, and each log's last line
#   scripts/devnet-seats.sh down     stop a running `up`, from another shell
#   scripts/devnet-seats.sh clean    delete the nodes' working directory (checkouts, receipts, logs)
#
# NOT while the AWS seats' host serves the same keys (platform#219: once its node_image_digest is set): two nodes with
# one seat's key would both report, seal and sign. Set seats_enabled = false there and wait until the host is stopped
# first. validator-kit/runbook.md, "The seats' host on AWS".
#
# Needs: Docker (each fix's tests run in the pinned sandbox image, no network: rule 4), python3, an OpenBao session for
# the role keys (bao login -no-print -method=oidc role=admin; read once, at the start), and in the environment:
#   DEVNET_RPC_URL         the devnet (https, no credential in it)
#   DEVNET_RPC_AUTH        "<handle>:<key>", or DEVNET_RPC_AUTH_FILE naming a file with it
#   DEVNET_REPO_TOKEN      a READ-ONLY token for the target repository, or DEVNET_REPO_TOKEN_FILE naming a file with it
# Optional:
#   DEVNET_EXCHANGE_URL    default $DEVNET_RPC_URL/exchange (the node sends it the RPC's key on the RPC's own host)
#   DEVNET_REPO            default example-org/pof-sandbox
#   DEVNET_FORGE_URL       default https://git.example.com
#   DEVNET_REPO_USER       the token's user, default pof-validator-bot
#   DEVNET_RECORD_V2       default contracts/deployments/devnet-aws-v2.json
#   DEVNET_SEATS_JUDGE     default fake: deterministic, free, labelled by the node's own test run. See below
#   DEVNET_SEATS_ROUND_TIMEOUT  seconds a node waits for the other drawn judges to seal, default 900: keep it equal to
#                          the relay's seal window (platform's exchange_seal_window_seconds). It must outlast the owner's
#                          on-demand start. A round whose judges all sealed moves on at once, so it costs nothing then
#   DEVNET_SEATS_POLL      seconds between a node's passes over the chain, default 5
#   DEVNET_SEATS_RESTART   seconds before a node that exited starts again, default 30
#   DEVNET_SEATS_WORK      the nodes' working directory, default .devnet-seats
#
# THE JUDGE: these six seats run the FAKE judge by default, and the contracts can't tell it from a real one: nothing on
# chain says what answered, and each seat's model family is only a price. Every draw of 3 of 7 has at least 2 of these
# seats, and 2 must agree. So their verdicts, which follow the sandbox's test result, decide every check, and the owner's
# real model can never change an outcome. A run like this tests the whole machine with one real model call in it; it
# doesn't test AI judgment. validator-kit/runbook.md, "The first real run", says what it proves and what it doesn't.
#
# Secrets: each key is read into this script's memory and given to its node's process through that process's environment,
# as the RPC credential and the repository token are: never on a command line, in a file or in `docker inspect`. The
# sandbox's container gets neither (oracle/sandbox.py passes it one variable, PYTHONDONTWRITEBYTECODE). Visible to the
# same user and root while the nodes run: /proc/<pid>/environ. Nothing here touches a public chain (rule 1): a node's
# key refuses any chain but the devnet's.
#
# A node has no state on disk. A chain that stops answering doesn't end it (#166): it keeps its round in memory and goes on
# when the chain's back, the night stop included, if the relay's windows are still open. If it does exit mid-round (Ctrl-C,
# a crash, a key the chain refuses) it starts again and, having reported, sits that round out without judging again: the
# other two drawn judges decide. Before its report nothing's lost: it judges from the start.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$PWD

# shellcheck source=scripts/devnet-keys.sh
source scripts/devnet-keys.sh

SEATS=(oracle-0 oracle-1 oracle-2 oracle-3 oracle-4 joiner-0)
WORK=${DEVNET_SEATS_WORK:-.devnet-seats}
PIDFILE=$WORK/up.pid

refuse() { echo "devnet-seats: $1" >&2; exit 2; }

is_up() { [[ -f "$PIDFILE" ]] && kill -0 "$(<"$PIDFILE")" 2>/dev/null; }

status() {
  if is_up; then echo "up (pid $(<"$PIDFILE"))"; else echo "down"; fi
  local role log
  for role in "${SEATS[@]}"; do
    log=$WORK/$role/node.log
    if [[ -f "$log" ]]; then printf '%-9s %s\n' "$role" "$(tail -n 1 "$log")"; else printf '%-9s no log\n' "$role"; fi
  done
}

down() {
  if is_up; then kill "$(<"$PIDFILE")"; echo "stopping"; else echo "not running"; fi
}

clean() {
  is_up && refuse "the nodes are running: stop them first"
  [[ -d "$WORK" ]] || return 0
  chmod -R u+w "$WORK" # the nodes' fetched checkouts are read-only (#115)
  rm -rf "$WORK"
  echo "removed $WORK"
}

# ---------- up: every check before any key is read ----------
read_config() {
  URL=${DEVNET_RPC_URL:-}
  [[ -n "$URL" ]] || refuse "set DEVNET_RPC_URL"
  [[ "$URL" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$ ]] ||
    refuse "DEVNET_RPC_URL must be a plain URL, without a credential in it: use DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE"
  EXCHANGE=${DEVNET_EXCHANGE_URL:-${URL%/}/exchange}
  [[ "$EXCHANGE" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$ ]] ||
    refuse "DEVNET_EXCHANGE_URL must be a plain URL, without a credential in it"
  if [[ ("$URL" == http://* || "$EXCHANGE" == http://*) && "${DEVNET_RPC_ALLOW_HTTP:-}" != 1 ]]; then
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
  unset DEVNET_RPC_AUTH # no child process inherits it: each node gets it by name below
  [[ -n "$AUTH" ]] || refuse "no credential: set DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE (<handle>:<key>)"
  [[ "$AUTH" =~ ^[^:[:space:]]+:[^[:space:]]+$ ]] || refuse "the credential must look like <handle>:<key> (not printed)"
  TOKEN=${DEVNET_REPO_TOKEN:-}
  if [[ -z "$TOKEN" && -n "${DEVNET_REPO_TOKEN_FILE:-}" ]]; then
    [[ -r "$DEVNET_REPO_TOKEN_FILE" ]] || refuse "can't read DEVNET_REPO_TOKEN_FILE"
    TOKEN=$(<"$DEVNET_REPO_TOKEN_FILE")
  fi
  unset DEVNET_REPO_TOKEN
  TOKEN=${TOKEN//[[:space:]]/} # a paste can bring a line ending along
  [[ -n "$TOKEN" ]] || refuse "no repository token: set DEVNET_REPO_TOKEN or DEVNET_REPO_TOKEN_FILE (read-only, e.g. pof-validator-bot's)"
  REPO=${DEVNET_REPO:-example-org/pof-sandbox}
  FORGE=${DEVNET_FORGE_URL:-https://git.example.com}
  REPO_USER=${DEVNET_REPO_USER:-pof-validator-bot}
  RECORD=${DEVNET_RECORD_V2:-contracts/deployments/devnet-aws-v2.json}
  [[ -f "$RECORD" ]] || refuse "no deployment record at $RECORD"
  RACE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["race"])' "$RECORD")
  JUDGE=${DEVNET_SEATS_JUDGE:-fake}
  ROUND_TIMEOUT=${DEVNET_SEATS_ROUND_TIMEOUT:-900}
  POLL=${DEVNET_SEATS_POLL:-5}
  RESTART=${DEVNET_SEATS_RESTART:-30}
  [[ "$ROUND_TIMEOUT" =~ ^[0-9]+$ && "$POLL" =~ ^[0-9]+$ && "$RESTART" =~ ^[0-9]+$ ]] || refuse "the timeouts are whole seconds"
  is_up && refuse "already up (pid $(<"$PIDFILE"))"
  timeout 20 docker info >/dev/null 2>&1 || refuse "Docker isn't running: the fixes' tests run in its sandbox (rule 4), and a node without it fails every check"
  return 0
}

# The relay answers for this race, behind the key. curl's credential comes from a config on a file descriptor.
check_exchange() {
  local race
  race=$(curl -sS -m 15 -K <(printf 'user = "%s"\n' "$AUTH") "${EXCHANGE%/}/healthz" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["race"])') ||
    refuse "no answer from the exchange relay at $EXCHANGE: is it hosted yet, and is the devnet up (it stops 01:00-09:00 Bogota)?"
  [[ "${race,,}" == "${RACE,,}" ]] || refuse "the relay at $EXCHANGE serves race $race, not this record's $RACE"
}

# One node's environment, by name. The prefix assignments put the secrets in that process's environment only.
in_node_env() { # role key: runs the command that follows as this process (exec); callers run it in a subshell (& or $())
  local role=$1 key=$2 dir=$ROOT/$WORK/$1
  shift 2
  cd "$dir"
  ORACLE_PRIVATE_KEY=$key ORACLE_KEYS=env ORACLE_VERSION=2 \
    ORACLE_RPC=$URL ORACLE_RPC_TOKEN=$AUTH ORACLE_RPC_API_KEY_HEADER=Basic ORACLE_RACE=$RACE \
    ORACLE_EXCHANGE_TRANSPORT=http ORACLE_EXCHANGE_URL=$EXCHANGE \
    ORACLE_REPO=$REPO ORACLE_REPOS=$ROOT/$WORK/repos.json FORGEJO_TOKEN=$TOKEN FORGEJO_USER=$REPO_USER \
    ORACLE_SRC_ROOT=$dir/src ORACLE_RECEIPTS=$dir/receipts ORACLE_SANDBOX=cli ORACLE_JUDGE=$JUDGE \
    ORACLE_ROUND_TIMEOUT=$ROUND_TIMEOUT ORACLE_POLL=$POLL PYTHONPATH=$ROOT PYTHONDONTWRITEBYTECODE=1 exec "$@"
}

supervise() { # role key from-block: the node, started again whenever it exits
  local role=$1 key=$2 from=$3 log=$WORK/$1/node.log child="" rc
  trap '[[ -z "$child" ]] || kill "$child" 2>/dev/null; exit 0' TERM INT
  while :; do
    in_node_env "$role" "$key" python3 -m oracle run --from-block "$from" >>"$log" 2>&1 &
    child=$!
    rc=0
    wait "$child" || rc=$?
    echo "[$role] the node exited ($rc); starting it again in ${RESTART}s" >>"$log"
    sleep "$RESTART" &
    child=$!
    wait "$child" || true
  done
}

up() {
  read_config
  mkdir -p "$WORK"
  chmod 700 "$WORK"
  python3 - "$REPO" "$FORGE" >"$WORK/repos.json" <<'PY'
import json, sys
print(json.dumps({"repos": {sys.argv[1]: {"host": "forgejo", "api": sys.argv[2]}}}))
PY
  check_exchange
  local image
  image=$(python3 -c 'from oracle.sandbox import TEST_IMAGE; print(TEST_IMAGE)')
  docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null
  declare -A keys
  local role out
  for role in "${SEATS[@]}"; do
    mkdir -p "$WORK/$role/src"
    keys[$role]=$(devnet_key "$role") || refuse "no key for $role"
    out=$(in_node_env "$role" "${keys[$role]}" python3 -m oracle info 2>&1) || refuse "$role: the node's check failed: ${out##*$'\n'}"
    [[ "$out" == *"an active seat's key: True"* ]] || refuse "$role isn't an active seat on this deployment: $out"
    echo "$role: $out"
  done
  # Where a restarted node scans from: fixed at the first start, so it still finds a win waiting for its merge.
  local from_file=$WORK/from-block
  if [[ ! -f "$from_file" ]]; then
    ORACLE_RPC=$URL ORACLE_RPC_TOKEN=$AUTH python3 -c '
import os
from oracle.rpc import Rpc, auth_headers
print(max(Rpc(os.environ["ORACLE_RPC"], auth_headers(os.environ["ORACLE_RPC_TOKEN"], "Basic")).block() - 100, 0))' >"$from_file"
  fi
  local from pids=()
  from=$(<"$from_file")
  for role in "${SEATS[@]}"; do
    supervise "$role" "${keys[$role]}" "$from" &
    pids+=($!)
  done
  unset keys
  echo $$ >"$PIDFILE"
  stop() { trap - EXIT INT TERM; kill "${pids[@]}" 2>/dev/null || true; wait 2>/dev/null || true; rm -f "$PIDFILE"; echo "the nodes stopped"; exit 0; }
  trap stop EXIT INT TERM
  echo "up: ${#SEATS[@]} nodes (judge $JUDGE, round timeout ${ROUND_TIMEOUT}s), scanning from block $from; logs in $WORK/<role>/node.log; Ctrl-C stops them"
  wait
}

case "${1:-}" in
  up) up ;;
  status) status ;;
  down) down ;;
  clean) clean ;;
  *) sed -n '2,49p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
