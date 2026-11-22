#!/usr/bin/env bash
# The remote mode of scripts/devnet.sh, end to end (#150, #112), on a throwaway copy of the AWS devnet: anvil with its
# settings behind Caddy with its image, its Basic auth (a bcrypt hash of a random key) and its 1 MB body cap, without
# TLS (DEVNET_RPC_ALLOW_HTTP=1, this test only), and anvil's public test keys. It deploys v2 as the runbook does, joins
# both vacant seats (one a devnet role, one a validator's own key through pofctl), warps, activates, runs a metered
# check, and checks what must be refused. It records every docker command line and samples every process's while it
# runs, and fails if a credential or a key shows up there, in the output, in the record or in forge's files.
# Everything it starts or writes is removed when it ends, pass or fail. Never a public chain (rule 1).
#
#   scripts/devnet-remote-e2e.sh      (POF_REMOTE_E2E_PORT picks the proxy's port on 127.0.0.1, default 8557)
set -euo pipefail
cd "$(dirname "$0")/.."

FOUNDRY_IMAGE=$(sed -n 's/^FOUNDRY_IMAGE="\(.*\)"/\1/p' scripts/devnet.sh)
CADDY_IMAGE="caddy:2.11.7-alpine@sha256:e70b164da81ef698b3ad19af799ea6086ce6d9e48ed4079eb9fe26f6fbf14ee5" # platform's pin
PREFIX=pof-remote-e2e
PORT=${POF_REMOTE_E2E_PORT:-8557}
WORK=$PWD/.devnet-remote-e2e
RECORDS=contracts/deployments/remote-e2e
BROADCAST=broadcast/remote-e2e
HANDLE=sandbox-validator
REAL_DOCKER=$(command -v docker)
SAMPLER=
SCRIPTS=(DeployV2 JoinV2 ActivateV2 FeesFlowV2)

cleanup() {
  local rc=$?
  if [[ $rc != 0 && -f "$WORK/output" ]]; then # the failing command's output, any line with a secret left out
    echo "--- the last output (exit $rc):" >&2
    grep -v -F -f "$WORK/secrets" "$WORK/output" | tail -25 >&2 || true
  fi
  [[ -z "$SAMPLER" ]] || kill "$SAMPLER" 2>/dev/null || true
  "$REAL_DOCKER" rm -f "$PREFIX-caddy" "$PREFIX-anvil" "$PREFIX-mainnet" >/dev/null 2>&1 || true
  "$REAL_DOCKER" network rm "$PREFIX" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$RECORDS" "contracts/$BROADCAST"
  local s; for s in "${SCRIPTS[@]}"; do rm -rf "contracts/cache/$s.s.sol/7193"; done
}
trap cleanup EXIT
cleanup
mkdir -p "$WORK/bin" "$RECORDS"
chmod 700 "$WORK"

fail() { echo "FAIL: $1" >&2; exit 1; }
ok() { echo "ok: $1"; }

# ---------- the secrets: a random key, and anvil's public keys (they stand in for the owner's) ----------
KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
WRONG_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
BASIC=$(printf '%s' "$HANDLE:$KEY" | base64 -w0)
ENGINEER_KEY=0x$(python3 -c 'import secrets; print(secrets.token_hex(32))')
python3 - "$ENGINEER_KEY" >"$WORK/secrets" <<'PY'
import os, sys
from pofctl.keys import MNEMONIC, ROLES, derive
for i, _ in enumerate(ROLES):
    print(f"{derive(MNEMONIC, i):064x}")
print(sys.argv[1][2:])
PY
printf '%s\n%s\n%s\n%s\n' "$KEY" "$WRONG_KEY" "$BASIC" "$(printf '%s' "$HANDLE:$WRONG_KEY" | base64 -w0)" >>"$WORK/secrets"

# ---------- the devnet: the same settings as platform's compose.yaml and Caddyfile ----------
"$REAL_DOCKER" network create "$PREFIX" >/dev/null
anvil() { # name chain-id
  "$REAL_DOCKER" run -d --name "$1" --network "$PREFIX" --entrypoint anvil "$FOUNDRY_IMAGE" --host=0.0.0.0 --port=8545 \
    --chain-id="$2" --hardfork=osaka --block-time=2 --silent >/dev/null
}
anvil "$PREFIX-anvil" 7193
anvil "$PREFIX-mainnet" 1 # a chain to be refused: anvil with mainnet's chain id
cat >"$WORK/Caddyfile" <<CADDY
:8080 {
	request_body {
		max_size 1MB
	}
	basic_auth {
		import /etc/caddy/users.caddy
	}
	reverse_proxy $PREFIX-anvil:8545
}
:8081 {
	basic_auth {
		import /etc/caddy/users.caddy
	}
	reverse_proxy $PREFIX-mainnet:8545
}
CADDY
hash=$(printf '%s\n' "$KEY" | "$REAL_DOCKER" run --rm -i --network none "$CADDY_IMAGE" caddy hash-password)
printf '%s %s\n' "$HANDLE" "$hash" >"$WORK/users.caddy"
chmod 644 "$WORK/Caddyfile" "$WORK/users.caddy"
chmod 755 "$WORK"
"$REAL_DOCKER" run -d --name "$PREFIX-caddy" --network "$PREFIX" -p "127.0.0.1:$PORT:8080" \
  -v "$WORK/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$WORK/users.caddy:/etc/caddy/users.caddy:ro" "$CADDY_IMAGE" >/dev/null
chmod 700 "$WORK"

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
      "$REAL_DOCKER" top "$c" -eo pid,args 2>/dev/null || true
      "$REAL_DOCKER" inspect -f '{{json .Config.Env}} {{json .Config.Cmd}} {{json .Args}}' "$c" 2>/dev/null || true
    done
    sleep 0.2
  done
) >"$WORK/sampled" 2>/dev/null &
SAMPLER=$!

# ---------- the remote mode, as the owner runs it ----------
export PATH="$WORK/bin:$PATH" DEVNET_RPC_ALLOW_HTTP=1 DEVNET_RPC_NETWORK=$PREFIX DEVNET_RPC_BROADCAST=$BROADCAST \
  DEVNET_KEYS=insecure-local DEVNET_RECORD_V2=$RECORDS/devnet-aws-v2.json
URL=http://$PREFIX-caddy:8080
SANDBOX_HEAD=$(git rev-parse HEAD~1)
RECORD=$RECORDS/devnet-aws-v2.json
remote() { DEVNET_RPC_URL=$URL DEVNET_RPC_AUTH=$HANDLE:$KEY scripts/devnet.sh "$@" 2>&1 | tee -a "$WORK/output"; }

# curl's credential comes from a config on a file descriptor: this script is held to the same rule as devnet.sh.
curl_auth() { curl -K <(printf 'user = "%s"\n' "$HANDLE:$KEY") "$@"; }
for _ in $(seq 60); do
  [[ "$(curl_auth -s -o /dev/null -w '%{http_code}' -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' "http://127.0.0.1:$PORT")" == 200 ]] && break
  sleep 0.5
done

# What must be refused.
expect_refused() { # what, pattern, then the command's environment and arguments
  local what=$1 pattern=$2 out rc=0
  shift 2
  out=$(while [[ "$1" == *=* ]]; do export "$1"; shift; done; "$@" 2>&1) || rc=$? # export, not env: env's argv would show it
  printf '%s\n' "$out" >>"$WORK/output"
  [[ $rc != 0 ]] || fail "$what: it ran"
  [[ "$out" == *"$pattern"* ]] || fail "$what: said: $out"
  ok "$what"
}
expect_refused "a wrong credential fails clearly" "refused the credential (HTTP 401)" \
  DEVNET_RPC_URL="$URL" DEVNET_RPC_AUTH="$HANDLE:$WRONG_KEY" scripts/devnet.sh deploy-v2
expect_refused "a chain that isn't 7193 is refused (chain 1)" "answers chain 1, not the devnet's 7193" \
  DEVNET_RPC_URL="http://$PREFIX-caddy:8081" DEVNET_RPC_AUTH="$HANDLE:$KEY" scripts/devnet.sh deploy-v2
[[ ! -f "$RECORD" ]] || fail "a refused run wrote a record"
deployer=$(python3 -c 'from pofctl.keys import MNEMONIC, address, derive; print(address(derive(MNEMONIC, 0)))')
on_mainnet() { "$REAL_DOCKER" run --rm --network "$PREFIX" --entrypoint cast "$FOUNDRY_IMAGE" "$@" --rpc-url "http://$PREFIX-mainnet:8545"; }
nonce=$(on_mainnet nonce "$deployer")
balance=$(on_mainnet balance "$deployer") # anvil's 10,000 ETH: fund would have made it 100
[[ "$nonce" == 0 && "$balance" == 10000000000000000000000 ]] || fail "the refused chain was touched (nonce $nonce, balance $balance)"
ok "nothing reached the refused chain"
[[ -z "$("$REAL_DOCKER" ps -q --filter name=pof-devnet-remote-)" ]] || fail "a refused run left its container"
ok "a refused run leaves no container"

# Deploy as the runbook says: 2 vacant seats, quorum 5, the sandbox's repository and head.
export DEVNET_V2_VACANT=2 DEVNET_V2_REPO=example-org/pof-sandbox DEVNET_V2_HEAD=$SANDBOX_HEAD \
  DEVNET_V2_FAMILIES=deepseek,qwen,mistral,llama,google,openai,anthropic
remote check | grep "chain 7193" >/dev/null || fail "check"
ok "check: the credential works, chain 7193"
remote status | grep "not deployed" >/dev/null || fail "status before the deployment"
remote fund | grep "funded 16 roles" >/dev/null || fail "fund"
expect_refused "a failed deployment fails and keeps no record" "no record kept" \
  DEVNET_RPC_URL="$URL" DEVNET_RPC_AUTH="$HANDLE:$KEY" DEVNET_V2_QUORUM=1 scripts/devnet.sh deploy-v2
[[ ! -f "$RECORD" ]] || fail "a failed deployment left a record"
remote deploy-v2 >/dev/null
[[ -f "$RECORD" ]] || fail "no record"
remote status | grep "every contract is on the chain with its recorded code hash" >/dev/null || fail "status after the deployment"
ok "deployed, and every contract's code hash matches the record"
python3 - "$RECORD" "$SANDBOX_HEAD" <<'PY' || fail "the record"
import json, sys
from oracle.crypto import keccak256
r = json.load(open(sys.argv[1]))
assert r["chainId"] == 7193 and r["seats"] == 7 and r["vacantSeats"] == 2 and r["quorum"] == 5, r
assert r["repo"] == "0x" + keccak256(b"example-org/pof-sandbox").hex(), r["repo"]
assert r["genesisHead"] == "0x" + sys.argv[2] + "0" * 24, r["genesisHead"]
assert r["keys"] == "insecure-local"
PY
ok "the record: 7 seats, 2 vacant, quorum 5, pof-sandbox's repository and head"
expect_refused "a second deployment over a record is refused" "already deployed" \
  DEVNET_RPC_URL="$URL" DEVNET_RPC_AUTH="$HANDLE:$KEY" scripts/devnet.sh deploy-v2

# The cap: the largest transaction fits, and the cap is really there.
python3 - "contracts/$BROADCAST/DeployV2.s.sol/7193/run-latest.json" <<'PY' || fail "a deployment transaction doesn't fit the cap"
import json, sys
sizes = {t["contractName"]: (len(t["transaction"]["input"]) - 2) // 2 for t in json.load(open(sys.argv[1]))["transactions"]}
top = max(sizes, key=sizes.get)
request = 2 * sizes[top] + 400  # hex in JSON, plus the signed transaction's other fields and the JSON-RPC envelope
print(f"largest deployment transaction: {top}, {sizes[top]} bytes of input, about {request} bytes of request (cap 1000000)")
assert request < 1_000_000
PY
code=$(head -c 1100000 /dev/zero | tr '\0' 'x' | curl_auth -s -o /dev/null -w '%{http_code}' \
  -H 'content-type: application/json' --data-binary @- "http://127.0.0.1:$PORT")
[[ "$code" == 413 ]] || fail "a 1.1 MB request got HTTP $code, not 413: the rig's cap isn't on"
ok "a 1.1 MB request is refused (413): the deployment went through the cap"

# A metered check behind the proxy: draws, usage reports, a result and a fee withdrawn, on these settings. Before the
# joins: fees-v2 signs with the oracle roles' keys, so it needs every active seat to be one of them.
remote fees-v2 | grep "FLOW" >/dev/null || fail "fees-v2"
ok "fees-v2: one metered check end to end"

# The seats: a devnet role in seat 5, a validator's own key in seat 6 through pofctl, as the runbook says.
remote seats-v2 | grep "seats 7, quorum 5" >/dev/null || fail "seats-v2"
remote join-v2 5 joiner-0 >/dev/null
pofctl() {
  POFCTL_RPC=http://127.0.0.1:$PORT POFCTL_RPC_TOKEN=$HANDLE:$KEY POFCTL_RPC_AUTH=Basic POFCTL_KEY_ENGINEER=$ENGINEER_KEY \
    scripts/pofctl --record "$RECORD" "$@"
}
request=$(pofctl --json --as engineer validator join --seat 6)
field() { python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$request" "$1"; }
engineer=$(field key)
remote fund-address "$engineer" | grep "funded $engineer" >/dev/null || fail "fund-address"
remote digest-v2 6 "$engineer" "$(field nonce)" >/dev/null
remote join-v2 6 --key "$engineer" --sig "$(field sig)" --nonce "$(field nonce)" | grep "JOIN seat 6" >/dev/null || fail "join-v2 6"
ok "seat 5 published (devnet role), seat 6 published (a validator's own key, signed by pofctl)"
expect_refused "activating before the delay fails" "" \
  DEVNET_RPC_URL="$URL" DEVNET_RPC_AUTH="$HANDLE:$KEY" scripts/devnet.sh activate-v2 6
remote warp 7 | grep "moved 7 days" >/dev/null || fail "warp"
remote activate-v2 5 >/dev/null
remote activate-v2 6 >"$WORK/seats"
grep -q "seat 6: active true" "$WORK/seats" || fail "seat 6 isn't active: $(cat "$WORK/seats")"
[[ "$(sed -n 's/^active keys \[\(.*\)\]$/\1/p' "$WORK/seats" | tr ',' '\n' | wc -l)" == 7 ]] || fail "not 7 active keys"
pofctl --as engineer validator status | grep -i "seat 6, active" >/dev/null || fail "pofctl doesn't see seat 6 active"
ok "warp 7, activate: 7 active seats, and pofctl sees seat 6 active through Basic auth"

# ---------- what the watchers saw ----------
kill "$SAMPLER" 2>/dev/null || true
wait "$SAMPLER" 2>/dev/null || true
SAMPLER=
# A line that starts with forge is the process inside the container: docker exec's own line on the host starts with docker.
grep -qE '^[0-9]+ +forge script' "$WORK/sampled" || fail "the sampler never saw forge inside the container: it proves nothing"
grep -q '/dev/shm/rpc-auth' "$WORK/docker-argv" || fail "the shim saw no remote command: it proves nothing"
for file in "$WORK/docker-argv" "$WORK/sampled" "$WORK/output" "$RECORD"; do
  if grep -q -F -f "$WORK/secrets" "$file"; then fail "a secret is in $(basename "$file")"; fi
done
ok "no key or credential in any docker command line, sampled process, docker inspect, output or the record"
if grep -qE -- '--private-key|wallet address' "$WORK/docker-argv"; then fail "a remote command passes a key as an argument"; fi
ok "no --private-key in any command the remote mode runs"
if grep -r -q -F -f "$WORK/secrets" "contracts/$BROADCAST" contracts/cache/*.s.sol/7193 "$RECORDS"; then fail "a secret is in forge's files"; fi
ok "no key or credential in forge's broadcast logs, its sensitive-values cache or the records"
[[ -z "$("$REAL_DOCKER" ps -aq --filter name=pof-devnet-remote-)" ]] || fail "a container of the remote mode is left"
ok "no remote-mode container left"
echo "devnet-remote-e2e: all passed"
