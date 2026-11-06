#!/usr/bin/env bash
# The first real run, end to end on a throwaway copy of everything (#150, #112). A local anvil with the AWS devnet's
# settings behind Caddy with its Basic auth, its body cap and its /exchange/* route (platform's Caddyfile and compose.yaml,
# copied below), the exchange relay from its own image, a real Forgejo (platform's pin) with a copy of pof-sandbox's history
# and a read-only bot, the deployment as the runbook does it, then:
#   - scripts/devnet-seats.sh: the six role seats' real nodes, each fix's tests in the Docker sandbox;
#   - tests/e2e_first_run_owner.py: the owner's validator, slow as on AWS: the kit's watcher code on a one-minute poll, a
#     90-second boot, then the node with the kit's environment, and a stand-in for its model on loopback;
#   - scripts/first-bounty.sh: the bounty, from the issue to the fees withdrawn;
#   - the same again with the relay's and the nodes' default 60-second windows: the owner's node misses the round.
# It records every docker command line and samples every process's while it runs, and fails if a credential or a key
# shows up there, in the output or in the logs. Everything it starts or writes is removed when it ends, pass or fail.
# Uses anvil's public test keys. Never a public chain (rule 1). A real model and AWS are for the owner's run.
#
#   scripts/first-run-e2e.sh      (POF_FIRST_RUN_PORT, default 8558: the proxy; +1: the Forgejo; about 15 minutes)
set -euo pipefail
cd "$(dirname "$0")/.."

FOUNDRY_IMAGE=$(sed -n 's/^FOUNDRY_IMAGE="\(.*\)"/\1/p' scripts/devnet.sh)
CADDY_IMAGE="caddy:2.11.7-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5" # platform's pin
FORGEJO_IMAGE="codeberg.org/forgejo/forgejo:16.0.6@sha256:e2c34a699543ca8a00217ee9ab2bea5feedc98bd6d0ea95ec287d3b7ae1355c6" # platform's pin
PREFIX=pof-first-run
PORT=${POF_FIRST_RUN_PORT:-8558}
FPORT=$((PORT + 1))
WORK=$PWD/.first-run-e2e
RECORDS=contracts/deployments/first-run-e2e
BROADCAST=broadcast/first-run-e2e
HANDLE=sandbox-validator
REPO=example-org/pof-sandbox
SANDBOX_HEAD=a52a922d5626526fbb43f469ff3efd973ac24776 # pof-sandbox's main, the AWS devnet's genesis head: this history has it
REAL_DOCKER=$(command -v docker)
SAMPLER=
SEATS_PID=
OWNER_PID=
SCRIPTS=(DeployV2 JoinV2 ActivateV2)

fail() { echo "FAIL: $1" >&2; exit 1; }
ok() { echo "ok: $1"; }
rig_nodes() { # this rig's seats' nodes, by their working directory: never a real run's on the same machine
  local pid
  for pid in $(pgrep -f "oracle run --from-block" || true); do
    [[ "$(readlink "/proc/$pid/cwd" 2>/dev/null)" == "$WORK"/* ]] && echo "$pid"
  done
  return 0
}
kill_seats() { # stopping the seats stops their nodes: none may go on with a key in its environment
  [[ -z "$SEATS_PID" ]] || { kill "$SEATS_PID" 2>/dev/null || true; wait "$SEATS_PID" 2>/dev/null || true; }
  SEATS_PID=
  local left=""
  for _ in $(seq 20); do
    left=$(rig_nodes)
    [[ -n "$left" ]] || return 0
    sleep 0.5
  done
  kill $left 2>/dev/null || true
  echo "devnet-seats.sh left node processes running" >&2
  return 1
}
cleanup() {
  local rc=$?
  if [[ $rc != 0 && -f "$WORK/output" ]]; then # the failing command's output, any line with a secret left out
    echo "--- the last output (exit $rc):" >&2
    grep -v -F -f "$WORK/secrets" "$WORK/output" | tail -25 >&2 || true
    for f in "$WORK"/seats/oracle-0/node.log "$WORK"/owner/node.log "$WORK"/owner.log; do
      [[ -f "$f" ]] && { echo "--- $f:" >&2; grep -v -F -f "$WORK/secrets" "$f" | tail -15 >&2 || true; }
    done
    "$REAL_DOCKER" logs --tail 15 "$PREFIX-exchange" >&2 2>&1 || true
  fi
  [[ -z "$SAMPLER" ]] || kill "$SAMPLER" 2>/dev/null || true
  kill_seats || true
  [[ -z "$OWNER_PID" ]] || kill "$OWNER_PID" 2>/dev/null || true
  "$REAL_DOCKER" rm -f "$PREFIX-caddy" "$PREFIX-anvil" "$PREFIX-exchange" "$PREFIX-forgejo" >/dev/null 2>&1 || true
  "$REAL_DOCKER" network rm "$PREFIX" >/dev/null 2>&1 || true
  "$REAL_DOCKER" image rm "$PREFIX-exchange:test" >/dev/null 2>&1 || true
  chmod -R u+w "$WORK" 2>/dev/null || true
  rm -rf "$WORK" "$RECORDS" "contracts/$BROADCAST"
  local s; for s in "${SCRIPTS[@]}"; do rm -rf "contracts/cache/$s.s.sol/7193"; done
}
trap cleanup EXIT
cleanup
mkdir -p "$WORK/bin" "$RECORDS" "$WORK/exchange-state"
chmod 700 "$WORK"


# ---------- the secrets: random keys and tokens, and anvil's public keys (they stand in for the owner's) ----------
KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BASIC=$(printf '%s' "$HANDLE:$KEY" | base64 -w0)
OWNER_KEY=0x$(python3 -c 'import secrets; print(secrets.token_hex(32))')
python3 - "$OWNER_KEY" >"$WORK/secrets" <<'PY'
import sys
from pofctl.keys import MNEMONIC, ROLES, derive
for i, _ in enumerate(ROLES):
    print(f"{derive(MNEMONIC, i):064x}")
print(sys.argv[1][2:])
PY
printf '%s\n%s\n' "$KEY" "$BASIC" >>"$WORK/secrets"
OWNER_ADDRESS=$(printf '%s' "$OWNER_KEY" | python3 -c 'import sys; from oracle.crypto import address; print(address(int(sys.stdin.read().strip(), 16)))')

# ---------- the devnet: platform's compose.yaml and Caddyfile, minus TLS ----------
"$REAL_DOCKER" network create "$PREFIX" >/dev/null
"$REAL_DOCKER" run -d --name "$PREFIX-anvil" --network "$PREFIX" --entrypoint anvil "$FOUNDRY_IMAGE" --host=0.0.0.0 --port=8545 \
  --chain-id=7193 --hardfork=osaka --block-time=2 --silent >/dev/null
cat >"$WORK/Caddyfile" <<CADDY
:8080 {
	request_body {
		max_size 1MB
	}
	basic_auth {
		import /etc/caddy/users.caddy
	}
	handle_path /exchange/* {
		reverse_proxy $PREFIX-exchange:8560
	}
	handle {
		reverse_proxy $PREFIX-anvil:8545
	}
}
CADDY
hash=$(printf '%s\n' "$KEY" | "$REAL_DOCKER" run --rm -i --network none "$CADDY_IMAGE" caddy hash-password)
printf '%s %s\n' "$HANDLE" "$hash" >"$WORK/users.caddy"
chmod 644 "$WORK/Caddyfile" "$WORK/users.caddy"
chmod 755 "$WORK"
"$REAL_DOCKER" run -d --name "$PREFIX-caddy" --network "$PREFIX" -p "127.0.0.1:$PORT:8080" \
  -v "$WORK/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$WORK/users.caddy:/etc/caddy/users.caddy:ro" "$CADDY_IMAGE" >/dev/null
RPC=http://127.0.0.1:$PORT
curl_auth() { curl -K <(printf 'user = "%s"\n' "$HANDLE:$KEY") "$@"; }
for _ in $(seq 60); do
  [[ "$(curl_auth -s -o /dev/null -w '%{http_code}' -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' "$RPC")" == 200 ]] && break
  sleep 0.5
done

# ---------- the forge: a real Forgejo, a copy of pof-sandbox's history, a read-only bot and a writer ----------
"$REAL_DOCKER" run -d --name "$PREFIX-forgejo" -p "127.0.0.1:$FPORT:3000" \
  -e FORGEJO__database__DB_TYPE=sqlite3 -e FORGEJO__security__INSTALL_LOCK=true \
  -e FORGEJO__server__ROOT_URL="http://127.0.0.1:$FPORT/" -e FORGEJO__server__OFFLINE_MODE=true \
  -e FORGEJO__server__DISABLE_SSH=true -e FORGEJO__service__DISABLE_REGISTRATION=true \
  -e FORGEJO__service__REQUIRE_SIGNIN_VIEW=true -e FORGEJO__federation__ENABLED=false -e FORGEJO__mailer__ENABLED=false \
  -e FORGEJO__cron_0X2E_update_checker__ENABLED=false -e FORGEJO__log__LEVEL=Warn "$FORGEJO_IMAGE" >/dev/null
FORGE=http://127.0.0.1:$FPORT
for _ in $(seq 120); do
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "$FORGE/api/healthz")" == 200 ]] && break
  sleep 1
done
fadmin() { "$REAL_DOCKER" exec -u git "$PREFIX-forgejo" forgejo admin user "$@"; }
fadmin create --username maintainer --password "$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')" \
  --email maintainer@example.invalid --must-change-password=false --admin >/dev/null
fadmin create --username pof-validator-bot --password "$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')" \
  --email bot@example.invalid --must-change-password=false >/dev/null
SETUP_TOKEN=$(fadmin generate-access-token --username maintainer --token-name setup --scopes all --raw)
WRITE_TOKEN=$(fadmin generate-access-token --username maintainer --token-name run --scopes write:repository,write:issue --raw)
READ_TOKEN=$(fadmin generate-access-token --username pof-validator-bot --token-name node --scopes read:repository,read:issue --raw)
printf '%s\n%s\n%s\n' "$SETUP_TOKEN" "$WRITE_TOKEN" "$READ_TOKEN" >>"$WORK/secrets"
fapi() { # method path [body]: the token from a config on a file descriptor
  curl -sS -f -K <(printf 'header = "Authorization: token %s"\n' "$SETUP_TOKEN") -H 'content-type: application/json' \
    -X "$1" "$FORGE/api/v1$2" ${3:+-d "$3"} >/dev/null
}
fapi POST /orgs '{"username":"example-org","visibility":"private"}'
fapi POST /orgs/example-org/repos '{"name":"pof-sandbox","private":true,"default_branch":"main"}'
GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0= GIT_CONFIG_KEY_1=http.extraHeader \
  GIT_CONFIG_VALUE_1="Authorization: Basic $(printf 'maintainer:%s' "$SETUP_TOKEN" | base64 -w0)" GIT_TERMINAL_PROMPT=0 \
  git push -q "$FORGE/$REPO.git" "$SANDBOX_HEAD:refs/heads/main"
fapi PUT "/repos/$REPO/collaborators/pof-validator-bot" '{"permission":"read"}'
ok "a real Forgejo: $REPO at ${SANDBOX_HEAD:0:12}, a read-only bot, and a writer"

# ---------- the watchers: every docker command line through a shim, every process's by sampling ----------
cat >"$WORK/bin/docker" <<SHIM
#!/usr/bin/env bash
printf '%s\n' "\$*" >> "$WORK/docker-argv"
exec "$REAL_DOCKER" "\$@"
SHIM
chmod +x "$WORK/bin/docker"
: >"$WORK/docker-argv"
(
  while :; do
    ps -eo args
    for c in $("$REAL_DOCKER" ps -q); do
      "$REAL_DOCKER" inspect -f '{{json .Config.Env}} {{json .Config.Cmd}} {{json .Args}}' "$c" 2>/dev/null || true
    done
    sleep 0.5
  done
) >"$WORK/sampled" 2>/dev/null &
SAMPLER=$!
export PATH="$WORK/bin:$PATH"

# ---------- the deployment, as the runbook does it ----------
export DEVNET_RPC_ALLOW_HTTP=1 DEVNET_KEYS=insecure-local DEVNET_RECORD_V2=$RECORDS/devnet-aws-v2.json
RECORD=$DEVNET_RECORD_V2
remote() {
  DEVNET_RPC_URL=http://$PREFIX-caddy:8080 DEVNET_RPC_AUTH=$HANDLE:$KEY DEVNET_RPC_NETWORK=$PREFIX DEVNET_RPC_BROADCAST=$BROADCAST \
    DEVNET_V2_VACANT=2 DEVNET_V2_QUORUM=5 DEVNET_V2_REPO=$REPO DEVNET_V2_HEAD=$SANDBOX_HEAD \
    DEVNET_V2_FAMILIES=deepseek,qwen,mistral,llama,google,openai,anthropic scripts/devnet.sh "$@" 2>&1 | tee -a "$WORK/output"
}
remote fund >/dev/null
remote deploy-v2 >/dev/null
[[ -f "$RECORD" ]] || fail "no record"
remote join-v2 5 joiner-0 >/dev/null
pofctl_as() { # the owner's key stays in this one environment
  POFCTL_RPC=$RPC POFCTL_RPC_TOKEN=$HANDLE:$KEY POFCTL_RPC_AUTH=Basic POFCTL_KEY_ENGINEER=$OWNER_KEY \
    scripts/pofctl --record "$RECORD" "$@"
}
request=$(pofctl_as --json --as engineer validator join --seat 6)
field() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$request" "$1"; }
remote fund-address "$(field key)" >/dev/null
remote join-v2 6 --key "$(field key)" --sig "$(field sig)" --nonce "$(field nonce)" >/dev/null
remote warp 7 >/dev/null
remote activate-v2 5 >/dev/null
remote activate-v2 6 >/dev/null
RACE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["race"])' "$RECORD")
ok "deployed as the runbook says: 7 seats active, the owner's key in seat 6"

# ---------- the relay, from its image, as platform's compose.yaml runs it ----------
"$REAL_DOCKER" build -q -f exchange/Dockerfile -t "$PREFIX-exchange:test" . >/dev/null
chmod 777 "$WORK/exchange-state"
exchange() { # the seal window, in seconds
  "$REAL_DOCKER" rm -f "$PREFIX-exchange" >/dev/null 2>&1 || true
  rm -f "$WORK/exchange-state/exchange.jsonl"
  "$REAL_DOCKER" run -d --name "$PREFIX-exchange" --network "$PREFIX" --user 10002:10002 --read-only --cap-drop ALL \
    --security-opt no-new-privileges --memory 128m -v "$WORK/exchange-state:/state" -e EXCHANGE_RPC="http://$PREFIX-anvil:8545" \
    -e EXCHANGE_RACE="$RACE" -e EXCHANGE_SEAL_WINDOW="$1" -e EXCHANGE_REVEAL_WINDOW=600 -e EXCHANGE_STATE=/state/exchange.jsonl \
    "$PREFIX-exchange:test" >/dev/null
  local answer=""
  for _ in $(seq 60); do
    answer=$(curl_auth -s "$RPC/exchange/healthz") || true
    [[ "$answer" == *'"ok": true'* ]] && return
    sleep 0.5
  done
  fail "the relay didn't come up behind Caddy: $answer"
}
exchange 300
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$RPC/exchange/healthz")" == 401 ]] || fail "the relay answers without a key"
[[ "$(curl -s -o /dev/null -w '%{http_code}' -u "$HANDLE:wrong" "$RPC/exchange/healthz")" == 401 ]] || fail "the relay answers a wrong key"
[[ "$(curl -s -o /dev/null -w '%{http_code}' "$RPC")" == 401 ]] || fail "the RPC answers without a key"
[[ "$(curl_auth -s "$RPC/exchange/healthz")" == *"${RACE,,}"* ]] || fail "the relay doesn't say its race"
ok "the relay behind Caddy: 401 without a key or with a wrong one; with one it names its race"
code=$(head -c 1100000 /dev/zero | tr '\0' 'x' | curl_auth -s -o /dev/null -w '%{http_code}' -H 'content-type: application/json' \
  --data-binary @- "$RPC/exchange/v1/$RACE/1/seal")
[[ "$code" == 413 ]] || fail "a 1.1 MB body to the relay got HTTP $code, not 413"
ok "a 1.1 MB body to the relay: 413 from the site's cap"
[[ "$(curl_auth -s -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' "$RPC")" == *'"0x1c19"'* ]] ||
  fail "the same key doesn't reach the RPC beside the relay"
ok "the same key still reaches the RPC at /"

# ---------- the seats, the owner's slow validator, and the bounty ----------
seats_up() { # the round timeout, in seconds
  kill_seats || fail "stopping the seats left their nodes running"
  DEVNET_RPC_URL=$RPC DEVNET_RPC_AUTH=$HANDLE:$KEY DEVNET_REPO_TOKEN=$READ_TOKEN DEVNET_FORGE_URL=$FORGE DEVNET_REPO=$REPO \
    DEVNET_SEATS_WORK=.first-run-e2e/seats DEVNET_SEATS_ROUND_TIMEOUT=$1 DEVNET_SEATS_POLL=2 DEVNET_SEATS_RESTART=5 \
    scripts/devnet-seats.sh up >>"$WORK/seats.log" 2>&1 &
  SEATS_PID=$!
  for _ in $(seq 120); do
    grep -q "^up: 6 nodes (judge fake, round timeout ${1}s)" "$WORK/seats.log" && return
    kill -0 "$SEATS_PID" 2>/dev/null || { tail -5 "$WORK/seats.log" >&2; fail "devnet-seats.sh stopped"; }
    sleep 1
  done
  fail "devnet-seats.sh didn't come up"
}
: >"$WORK/seats.log"
seats_up 300
ok "devnet-seats.sh: 6 real node processes, each key an active seat's, through the relay"
mkdir -p "$WORK/owner"
RIG_WORK=$WORK/owner RIG_REPO=$REPO RIG_FORGE=$FORGE RIG_RPC=$RPC RIG_RPC_AUTH=$HANDLE:$KEY RIG_EXCHANGE=$RPC/exchange RIG_RACE=$RACE \
  RIG_REPO_TOKEN=$READ_TOKEN RIG_REPO_USER=pof-validator-bot RIG_OWNER_KEY=$OWNER_KEY RIG_OWNER_ADDRESS=$OWNER_ADDRESS \
  RIG_BOOT=90 RIG_POLL=60 RIG_IDLE=60 PYTHONDONTWRITEBYTECODE=1 python3 tests/e2e_first_run_owner.py >"$WORK/owner.log" 2>&1 &
OWNER_PID=$!

bounty() {
  DEVNET_RPC_URL=$RPC DEVNET_RPC_AUTH=$HANDLE:$KEY DEVNET_FORGE_URL=$FORGE DEVNET_REPO=$REPO FIRST_BOUNTY_ANYTIME=1 \
    FIRST_BOUNTY_TOKEN=$WRITE_TOKEN FIRST_BOUNTY_USER=maintainer POFCTL_KEY_ENGINEER=$OWNER_KEY \
    scripts/first-bounty.sh "$@" 2>&1 | tee -a "$WORK/output"
}
echo "--- the bounty, with a 300-second seal window and round timeout:"
bounty --max-fails 12
grep -q "^result: the first bounty ran end to end" "$WORK/output" || fail "the bounty"
grep -q "OWNER (777/55)" "$WORK/output" || fail "the owner's stand-in model's tokens aren't in the books"
ok "the bounty, end to end: the owner's slow node sealed in time, and its model's token counts are on-chain"
grep -q "model: the prompt has the issue and the diff" "$WORK/owner.log" || fail "the owner's model never got the issue and the diff"
grep -q "model: the prompt lacks" "$WORK/owner.log" && fail "the owner's model got a prompt without the issue or the diff"
ok "the owner's model read the issue from the Forgejo, and the diff the node computed from what it fetched"
grep -q "the node exited 0" "$WORK/owner.log" || fail "the owner's node never ended its run"
ok "the owner's node stopped when idle, as the kit's does"

# ---------- what the default windows do ----------
echo "--- again, with the defaults (60 seconds): the owner's node can't make it"
for _ in $(seq 200); do # the owner's node has finished its idle run: a stopped instance, as a real first draw finds it
  [[ "$(cat "$WORK/owner/state" 2>/dev/null)" == stopped ]] && break
  sleep 1
done
[[ "$(cat "$WORK/owner/state" 2>/dev/null)" == stopped ]] || fail "the owner's instance never stopped"
exchange 60
seats_up 60
: >"$WORK/output.defaults"
bounty --max-fails 12 --fails-only | tee "$WORK/output.defaults" || true
grep -q "OWNER (no report)" "$WORK/output.defaults" || fail "with 60-second windows, the owner's node still took part"
grep -q "came out" "$WORK/output.defaults" && fail "with 60-second windows, a failing fix wasn't decided as Fail"
ok "with 60-second windows the two other judges decide without the owner's node (and its fee)"

# ---------- what the watchers saw ----------
kill "$SAMPLER" 2>/dev/null || true
wait "$SAMPLER" 2>/dev/null || true
SAMPLER=
grep -qE '(^|[ /])python3? -m oracle run --from-block' "$WORK/sampled" || fail "the sampler never saw a seat's node: it proves nothing"
grep -q -- '--pids-limit 64' "$WORK/docker-argv" || fail "the shim saw no sandbox: it proves nothing"
files=("$WORK/docker-argv" "$WORK/sampled" "$WORK/output" "$WORK/seats.log" "$WORK/owner.log")
while IFS= read -r f; do files+=("$f"); done < <(find "$WORK/seats" "$WORK/owner" -name '*.log')
for file in "${files[@]}"; do
  if grep -q -F -f "$WORK/secrets" "$file"; then fail "a secret is in $(basename "$file")"; fi
done
ok "no key, credential or token in any docker command line, sampled process, docker inspect, output or node log"
kill_seats || fail "stopping the seats left their nodes running"
ok "stopping the seats stops every node"
[[ ! -f "$WORK/seats/up.pid" ]] || fail "devnet-seats.sh left its pid file"
echo "first-run-e2e: all passed"
