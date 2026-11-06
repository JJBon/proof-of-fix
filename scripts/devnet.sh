#!/usr/bin/env bash
# The private devnet (proof-of-fix#93): an Ethereum chain with mainnet rules, on this machine only. anvil from the
# pinned Foundry image runs mainnet's current hardfork (Osaka), enforces EIP-170's 24,576-byte code-size limit (the
# local loop's chain used to lift it), mines a block every 2 seconds, and has its own chain id (7193, no public
# chain's). Its RPC is published on 127.0.0.1 only; its state persists in .devnet/ across restarts.
#
#   scripts/devnet.sh up          start the devnet (idempotent)
#   scripts/devnet.sh down        stop it (the state stays in .devnet/; `reset` deletes it)
#   scripts/devnet.sh status      chain id, block, hardfork, and the deployment record if any
#   scripts/devnet.sh fund        give every role's address 100 devnet ETH (anvil_setBalance: a devnet affordance)
#   scripts/devnet.sh deploy      deploy Token, Race (+ its OracleAuth library), Quoter and a test coin; write
#                                 contracts/deployments/devnet.json
#   scripts/devnet.sh deploy-v2   deploy v2 beside v1 (#85 task 5.1): Verdicts, RaceV2, Heads (this repository's
#                                 genesis head and the constitution's hash), Pool, QuoterV2 and a test coin; write
#                                 contracts/deployments/devnet-v2.json
#   scripts/devnet.sh digest-v2 <seat> <key> [nonce]
#                                 the digest a v2 seat's new key and the co-signing seats sign (#85 task 5.4)
#   scripts/devnet.sh join-v2 <seat> <role> | join-v2 <seat> --key <address> --sig <signature> --nonce <nonce>
#                                 publish a v2 seat's key (a vacant seat's join, #104): the new key (a role's, or an
#                                 engineer's who signed digest-v2's digest) and every oracle role co-signing
#   scripts/devnet.sh activate-v2 <seat>   the published key takes the seat, once its delay has passed
#   scripts/devnet.sh seats-v2    the v2 seats: count, active keys, pending keys
#   scripts/devnet.sh fees-v2     one metered check end to end on v2 (#85 task 5.7): an issue, a pledge, a commit
#                                 (its deposit is the quote's worst case), the drawn judges' signed usage (one pads
#                                 it), the result, the charge and the refund, and a judge pulling its fee
#   scripts/devnet.sh warp <days> move the devnet's clock forward (a devnet affordance)
#   scripts/devnet.sh scenarios   the oracle-path scenarios against the deployed contracts (a fork of the devnet),
#                                 then EIP-170 checked on the devnet itself (24,576 bytes deploy, 24,577 don't)
#   scripts/devnet.sh reset       down, and delete this devnet's state and its untracked deployment records (a
#                                 committed record is kept)
#
# Keys come from OpenBao (scripts/devnet-keys.sh; sign in first), or anvil's public mnemonic with
# DEVNET_KEYS=insecure-local. Nothing here touches a public chain (rule 1).
#
# Remote mode (#150, #112): DEVNET_RPC_URL names a devnet that runs elsewhere, behind HTTP Basic auth (the AWS devnet,
# platform#197), with the credential "<handle>:<key>" in DEVNET_RPC_AUTH or a file named by DEVNET_RPC_AUTH_FILE. It
# refuses any chain but 7193, keeps its own record (contracts/deployments/devnet-aws-v2.json), and adds
#   scripts/devnet.sh check       the credential works and the chain is 7193: only eth_chainId and eth_blockNumber
#   scripts/devnet.sh fund-address <address> [eth]   give one address devnet ETH (default 100), e.g. a validator's
# How it works, and what it refuses: "Remote mode" below. The runbook: validator-kit/runbook.md, "The AWS devnet".
set -euo pipefail
cd "$(dirname "$0")/.."

FOUNDRY_IMAGE="ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043"
SOLC="contracts/.cache/solc-linux-amd64-v0.8.37+commit.f401782d"
NAME=${DEVNET_NAME:-pof-devnet} # a second devnet (e.g. a test run beside the owner's) needs its own name and port
CHAIN_ID=7193
HARDFORK=osaka
BLOCK_TIME=2
PORT=${DEVNET_PORT:-8546}
RPC=http://127.0.0.1:8545 # inside the devnet container
RECORD=${DEVNET_RECORD:-contracts/deployments/devnet.json}
STATE=${DEVNET_STATE:-.devnet} # a throwaway devnet (tests, pofctl's end-to-end run) keeps its own state and records
RECORD_V2=${DEVNET_RECORD_V2:-contracts/deployments/devnet-v2.json}
QUORUM=3
REMOTE=${DEVNET_RPC_URL:-} # set: remote mode, see below

# shellcheck source=scripts/devnet-keys.sh
source scripts/devnet-keys.sh

running() { [[ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" == true ]]; }
in_devnet() { docker exec -i -w /work "$@"; }

up() {
  [[ -f "$SOLC" ]] || { echo "solc missing; run: scripts/contracts.sh setup" >&2; exit 1; }
  if running; then echo "devnet already up on 127.0.0.1:$PORT"; return; fi
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  mkdir -p "$STATE"
  docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8545" --user "$(id -u):$(id -g)" \
    -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -v "$PWD/$STATE:/state" -w /work \
    --entrypoint anvil "$FOUNDRY_IMAGE" \
    --host 0.0.0.0 --port 8545 --chain-id "$CHAIN_ID" --hardfork "$HARDFORK" --block-time "$BLOCK_TIME" \
    --state /state/state.json --silent >/dev/null
  for _ in $(seq 60); do
    [[ "$(in_devnet "$NAME" cast chain-id --rpc-url "$RPC" 2>/dev/null)" == "$CHAIN_ID" ]] && break
    sleep 0.5
  done
  echo "devnet up: chain $CHAIN_ID, $HARDFORK, a block every ${BLOCK_TIME}s, RPC on 127.0.0.1:$PORT"
}

down() { docker stop "$NAME" >/dev/null 2>&1 && docker rm "$NAME" >/dev/null 2>&1; echo "devnet down (state kept in $STATE/)"; }

status() {
  running || { echo "devnet down"; return 1; }
  echo "chain $(in_devnet "$NAME" cast chain-id --rpc-url "$RPC"), block $(in_devnet "$NAME" cast block-number --rpc-url "$RPC"), $(in_devnet "$NAME" cast rpc --rpc-url "$RPC" anvil_nodeInfo | sed -n 's/.*"hardFork":"\([^"]*\)".*/\1/p')"
  [[ -f "$RECORD" ]] && cat "$RECORD" || echo "not deployed (scripts/devnet.sh deploy)"
  [[ -f "$RECORD_V2" ]] && { echo; cat "$RECORD_V2"; } || true
}

need_up() { running || { echo "devnet down: run scripts/devnet.sh up" >&2; exit 1; }; }

fund() {
  need_up
  local role addr
  for role in "${ROLES[@]}"; do
    addr=$(devnet_key "$role" | address_of)
    in_devnet "$NAME" cast rpc --rpc-url "$RPC" anvil_setBalance "$addr" 0x56bc75e2d63100000 >/dev/null # 100 ETH
  done
  echo "funded ${#ROLES[@]} roles with 100 devnet ETH"
}

# One address, e.g. a validator's own key (its gas for usage reports and relays): anvil_setBalance, a devnet affordance.
fund_address() {
  need_up
  local addr=${1:?address} eth=${2:-100}
  [[ "$addr" =~ ^0x[0-9a-fA-F]{40}$ && "$eth" =~ ^[0-9]+$ ]] || { echo "fund-address <0x address> [whole eth]" >&2; exit 2; }
  in_devnet "$NAME" cast rpc --rpc-url "$RPC" anvil_setBalance "$addr" "$(printf '0x%x' "$((eth * 10 ** 18))")" >/dev/null
  echo "funded $addr with $eth devnet ETH"
}

oracle_addresses() {
  local i out=()
  for ((i = 0; i < ORACLES; i++)); do out+=("$(devnet_key "oracle-$i" | address_of)"); done
  local IFS=,; echo "${out[*]}"
}

deploy() {
  need_up
  fund >/dev/null
  local deployer infrastructure insurance founder oracles commit
  deployer=$(devnet_key deployer)
  infrastructure=$(devnet_key infrastructure | address_of)
  insurance=$(devnet_key insurance | address_of)
  founder=$(devnet_key founder | address_of)
  oracles=$(oracle_addresses)
  commit=$(git rev-parse HEAD)
  mkdir -p contracts/deployments
  # The key reaches forge through the environment, never the command line or the output.
  printf '%s' "$deployer" | in_devnet -e DEPLOY_INFRASTRUCTURE="$infrastructure" -e DEPLOY_INSURANCE="$insurance" \
    -e DEPLOY_FOUNDER="$founder" -e DEPLOY_ORACLES="$oracles" -e DEPLOY_QUORUM="$QUORUM" -e DEPLOY_COMMIT="$commit" \
    -e DEPLOY_KEYS="${DEVNET_KEYS:-openbao}" -e DEPLOY_RECORD="${RECORD#contracts/}" "$NAME" sh -c \
    'read -r PK; forge script script/Deploy.s.sol:DeployScript --rpc-url '"$RPC"' --broadcast --private-key "$PK" --slow' \
    | sed -n '/== Logs ==/,/^$/p'
  echo "deployment record: $RECORD"
}

# v2 beside v1 (#85 task 5.1, design S10): the same keys and quorum; the genesis head is the commit deployed, and the
# constitution's hash is CONSTITUTION.md's sha256 at that commit. Operators' disclosed accounts and their seats' keys
# (#85 task 5.3: a seat whose operator is a party is recused) come from DEVNET_OPERATORS and DEVNET_OPERATOR_KEYS,
# comma-separated and pairwise, when set; none by default.
# Vacant seats (#85 task 5.4, #104): DEVNET_V2_VACANT seats appended after the oracle roles' (default 0), filled later
# by join-v2. With vacancies the quorum defaults to every oracle role (5 of 7 with two vacant seats); DEVNET_V2_QUORUM
# overrides it.
# The target (#150): DEVNET_V2_REPO names the repository whose head Heads keeps (default this one), and DEVNET_V2_HEAD
# the commit that is its genesis head (default the commit deployed: a repository at another commit, like pof-sandbox,
# needs its own); the constitution's hash is read at that head. DEVNET_V2_FAMILIES and DEVNET_V2_PROVIDERS name each
# seat's model family and provider (fixed for good at genesis, a vacant seat's too; the family sets its token prices),
# and DEVNET_V2_IMAGES the allowed checker images; DeployV2.s.sol's defaults when unset.
deploy_v2() {
  need_up
  fund >/dev/null
  local deployer infrastructure insurance oracles commit head constitution
  local vacant=${DEVNET_V2_VACANT:-0} quorum
  quorum=${DEVNET_V2_QUORUM:-$([[ $vacant -gt 0 ]] && echo "$ORACLES" || echo "$QUORUM")}
  local operators=()
  if [[ -n "${DEVNET_OPERATORS:-}" ]]; then
    operators=(-e DEPLOY_OPERATORS="$DEVNET_OPERATORS" -e DEPLOY_OPERATOR_KEYS="${DEVNET_OPERATOR_KEYS:?pairwise with DEVNET_OPERATORS}")
  fi
  local target=()
  [[ -z "${DEVNET_V2_FAMILIES:-}" ]] || target+=(-e DEPLOY_FAMILIES="$DEVNET_V2_FAMILIES")
  [[ -z "${DEVNET_V2_PROVIDERS:-}" ]] || target+=(-e DEPLOY_PROVIDERS="$DEVNET_V2_PROVIDERS")
  [[ -z "${DEVNET_V2_IMAGES:-}" ]] || target+=(-e DEPLOY_IMAGES="$DEVNET_V2_IMAGES")
  deployer=$(devnet_key deployer)
  infrastructure=$(devnet_key infrastructure | address_of)
  insurance=$(devnet_key insurance | address_of)
  oracles=$(oracle_addresses)
  commit=$(git rev-parse HEAD)
  head=$(git rev-parse --verify "${DEVNET_V2_HEAD:-$commit}^{commit}")
  constitution=0x$(git show "$head:CONSTITUTION.md" | sha256sum | cut -d' ' -f1)
  [[ -z "${DEVNET_V2_HEAD:-}" ]] || target+=(-e DEPLOY_HEAD="$head")
  # Remote mode keeps the key off even the container's command line: the script reads it from its environment.
  local send='read -r PK; forge script script/DeployV2.s.sol:DeployV2Script --rpc-url '"$RPC"' --broadcast --private-key "$PK" --slow'
  [[ -z "$REMOTE" ]] || send='read -r DEPLOY_SENDER_PK; export DEPLOY_SENDER_PK; forge script script/DeployV2.s.sol:DeployV2Script --rpc-url '"$RPC"' --broadcast --slow'
  mkdir -p contracts/deployments
  printf '%s' "$deployer" | in_devnet -e DEPLOY_INFRASTRUCTURE="$infrastructure" -e DEPLOY_INSURANCE="$insurance" \
    -e DEPLOY_ORACLES="$oracles" -e DEPLOY_QUORUM="$quorum" -e DEPLOY_VACANT="$vacant" -e DEPLOY_COMMIT="$commit" \
    -e DEPLOY_REPO="${DEVNET_V2_REPO:-example-org/proof-of-fix}" -e DEPLOY_CONSTITUTION="$constitution" \
    -e DEPLOY_KEYS="${DEVNET_KEYS:-openbao}" -e DEPLOY_RECORD="${RECORD_V2#contracts/}" "${operators[@]}" "${target[@]}" "$NAME" sh -c \
    "$send" \
    | sed -n '/== Logs ==/,/^$/p'
  echo "deployment record: $RECORD_V2"
}

need_v2() { need_up; [[ -f "$RECORD_V2" ]] || { echo "v2 not deployed: run scripts/devnet.sh deploy-v2" >&2; exit 1; }; }
verdicts_v2() { sed -n 's/.*"verdicts": *"\(0x[0-9a-fA-F]*\)".*/\1/p' "$RECORD_V2"; }

# The digest a seat's new key signs, with the devnet's image and no attestation (#85 task 5.4): an engineer signs it
# with their own key (`cast wallet sign --no-hash <digest>`) and sends the signature for join-v2 --sig.
digest_v2() {
  need_v2
  local seat=${1:?seat} key=${2:?key address} nonce=${3:-0x$(printf '%064x' "$(date +%s)")}
  echo "nonce  $nonce"
  echo "digest $(in_devnet "$NAME" cast call --rpc-url "$RPC" "$(verdicts_v2)" \
    'rotateDigest(uint256,address,bytes32,bytes32,bytes32,bytes32)(bytes32)' "$seat" "$key" \
    "$(in_devnet "$NAME" cast keccak 'devnet checker image')" "$(in_devnet "$NAME" cast keccak none)" \
    0x0000000000000000000000000000000000000000000000000000000000000000 "$nonce")"
}

# Publish a seat's key: the new key is a role's (signed here), or an engineer's (--key, --sig and digest-v2's --nonce);
# every oracle role co-signs, and the bot sends it. Keys travel on stdin, never the command line.
join_v2() {
  need_v2
  local seat=${1:?seat} role="" key="" sig="" nonce i cosigners="" newkey=""
  shift
  if [[ "${1:-}" == --key ]]; then
    key=${2:?address}; [[ "${3:-}" == --sig ]] || { echo "join-v2 <seat> --key <address> --sig <signature> --nonce <nonce>" >&2; exit 2; }
    sig=${4:?signature}; [[ "${5:-}" == --nonce ]] && nonce=${6:?nonce} || { echo "--nonce: digest-v2's nonce" >&2; exit 2; }
  else
    role=${1:?role, e.g. joiner-0}; nonce=0x$(printf '%064x' "$(date +%s%N)"); newkey=$(devnet_key "$role")
  fi
  for ((i = 0; i < ORACLES; i++)); do cosigners+="${cosigners:+,}$(devnet_key "oracle-$i")"; done
  printf '%s\n%s\n%s\n' "$(devnet_key bot)" "$cosigners" "$newkey" | in_devnet -e JOIN_RECORD="${RECORD_V2#contracts/}" \
    -e JOIN_SEAT="$seat" -e JOIN_NONCE="$nonce" -e JOIN_KEY="$key" -e JOIN_KEY_SIG="$sig" "$NAME" sh -c \
    'read -r JOIN_SENDER_PK; read -r JOIN_COSIGNER_PKS; read -r JOIN_KEY_PK; export JOIN_SENDER_PK JOIN_COSIGNER_PKS
     if [ -n "$JOIN_KEY_PK" ]; then export JOIN_KEY_PK; unset JOIN_KEY JOIN_KEY_SIG; else unset JOIN_KEY_PK; fi
     forge script script/JoinV2.s.sol:JoinV2Script --rpc-url '"$RPC"' --broadcast --slow' \
    | sed -n '/== Logs ==/,/^$/p'
}

activate_v2() {
  need_v2
  local seat=${1:?seat}
  if [[ -n "$REMOTE" ]]; then
    devnet_key bot | in_devnet -e ACTIVATE_RECORD="${RECORD_V2#contracts/}" -e ACTIVATE_SEAT="$seat" "$NAME" sh -c \
      'read -r ACTIVATE_SENDER_PK; export ACTIVATE_SENDER_PK; forge script script/ActivateV2.s.sol:ActivateV2Script --rpc-url '"$RPC"' --broadcast --slow' \
      | sed -n '/== Logs ==/,/^$/p'
    seats_v2
    return
  fi
  devnet_key bot | in_devnet "$NAME" sh -c 'read -r PK; cast send --rpc-url '"$RPC"' --private-key "$PK" '"$(verdicts_v2)"' "activate(uint256)" '"$seat"' >/dev/null'
  echo "seat $seat: activated"
  seats_v2
}

seats_v2() {
  need_v2
  local v n i
  v=$(verdicts_v2)
  n=$(in_devnet "$NAME" cast call --rpc-url "$RPC" "$v" 'seatCount()(uint256)')
  echo "seats $n, quorum $(in_devnet "$NAME" cast call --rpc-url "$RPC" "$v" 'quorum()(uint256)')"
  for ((i = 0; i < n; i++)); do
    echo "seat $i: active $(in_devnet "$NAME" cast call --rpc-url "$RPC" "$v" 'isActive(uint256)(bool)' "$i"), pending $(in_devnet "$NAME" cast call --rpc-url "$RPC" "$v" 'pending(uint256)(address,bytes32,bytes32,bytes32,uint64)' "$i" | head -1)"
  done
  echo "active keys $(in_devnet "$NAME" cast call --rpc-url "$RPC" "$v" 'keys()(address[])')"
}

# One metered check (#85 task 5.7, S15), in two runs of FeesFlowV2.s.sol: the commit, then (its seed now on the chain)
# the drawn judges' usage, the result and a judge's withdrawal. Keys travel on stdin, never the command line.
fees_v2() {
  need_v2
  local keys="" i out id
  for ((i = 0; i < ORACLES; i++)); do keys+="${keys:+,}$(devnet_key "oracle-$i")"; done
  flow() {
    printf '%s\n%s\n%s\n%s\n%s\n' "$(devnet_key reporter)" "$(devnet_key funder)" "$(devnet_key solver-a)" \
      "$(devnet_key bot)" "$keys" | in_devnet -e FLOW_RECORD="${RECORD_V2#contracts/}" -e FLOW_PHASE="$1" \
      -e FLOW_SUBMISSION="${2:-0}" "$NAME" sh -c \
      'read -r FLOW_REPORTER_PK; read -r FLOW_FUNDER_PK; read -r FLOW_SOLVER_PK; read -r FLOW_BOT_PK; read -r FLOW_ORACLE_PKS
       export FLOW_REPORTER_PK FLOW_FUNDER_PK FLOW_SOLVER_PK FLOW_BOT_PK FLOW_ORACLE_PKS
       forge script script/FeesFlowV2.s.sol:FeesFlowV2Script --rpc-url '"$RPC"' --broadcast --slow' \
      | sed -n '/== Logs ==/,/^$/p'
  }
  out=$(flow commit)
  echo "$out"
  id=$(echo "$out" | sed -n 's/.*FLOW submission \([0-9]*\).*/\1/p')
  [[ -n "$id" ]] || { echo "no submission committed" >&2; return 1; }
  flow check "$id"
}

warp() {
  need_up
  local days=${1:?days}
  in_devnet "$NAME" cast rpc --rpc-url "$RPC" evm_increaseTime "$((days * 86400))" >/dev/null
  in_devnet "$NAME" cast rpc --rpc-url "$RPC" evm_mine >/dev/null
  echo "devnet clock moved $days days"
}

scenarios() {
  need_up
  [[ -f "$RECORD" ]] || { echo "not deployed: run scripts/devnet.sh deploy" >&2; exit 1; }
  local keys="" i
  for ((i = 0; i < ORACLES; i++)); do keys+="${keys:+,}$(devnet_key "oracle-$i")"; done
  # A fork of the devnet's current state: the checks run against the deployed bytecode, nothing is broadcast.
  printf '%s' "$keys" | in_devnet -e SCENARIO_RECORD="${RECORD#contracts/}" "$NAME" sh -c \
    'read -r ORACLE_KEYS; export ORACLE_KEYS; forge script script/Scenarios.s.sol:ScenariosScript --rpc-url '"$RPC"'' \
    | sed -n '/== Logs ==/,/^$/p'
  size_limit
}

# EIP-170 on the devnet itself (not forge's own check): a contract whose runtime is exactly 24,576 bytes deploys, one
# byte more is refused. The init code returns that many zero bytes: PUSH2 <size> PUSH1 0 RETURN.
size_limit() {
  local key ok=0
  key=$(devnet_key bot)
  for size in 6000 6001; do
    if printf '%s' "$key" | in_devnet "$NAME" sh -c 'read -r PK; cast send --rpc-url '"$RPC"' --private-key "$PK" --create 0x61'"$size"'6000f3 >/dev/null 2>&1'; then
      result=deployed
    else
      result=refused
    fi
    echo "SIZE $((16#$size)) bytes of runtime code: $result"
    case "$size:$result" in 6000:deployed | 6001:refused) ;; *) ok=1 ;; esac
  done
  [[ $ok == 0 ]] && echo "SIZE EIP-170 enforced by the devnet: ok" || { echo "SIZE EIP-170: FAIL" >&2; return 1; }
}

# reset deletes this devnet's state and its records, never a record git tracks (the default devnet's committed
# devnet.json, #111): a throwaway devnet (DEVNET_NAME/DEVNET_STATE/DEVNET_RECORD*) removes only its own files.
tracked() { git ls-files --error-unmatch -- "$1" >/dev/null 2>&1; }
reset() {
  down >/dev/null 2>&1 || true
  rm -rf "$STATE"
  local record
  for record in "$RECORD" "$RECORD_V2"; do
    if tracked "$record"; then echo "kept $record (committed)"; else rm -f "$record"; fi
  done
  echo "devnet reset ($NAME, state $STATE/)"
}

# ---------- Remote mode (#150, #112) ----------
# The devnet runs elsewhere; forge and cast still run in the pinned image, in one container per invocation of this
# script (removed when it ends, and after an hour at worst). Only this container gets a network. Every function above
# works unchanged through in_devnet, RPC and need_up, redefined here.
#
# The credential never reaches a command line, `docker inspect` or the disk: it goes on stdin into a file in the
# container's /dev/shm (memory, gone with the container), and each command sources it into its own environment, as
# Foundry's FOUNDRY_ETH_RPC_HEADERS (forge script has no --rpc-headers; this setting reaches its fork, simulation and
# broadcast) and ETH_RPC_HEADERS (cast). The URL stays free of it, so forge's "sensitive values" file and any error
# message can't carry it. Keys go on stdin as everywhere here, and into the Solidity scripts' environment, never to
# --private-key; addresses are derived on the host (oracle/crypto.py), since `cast wallet address` takes the key as an
# argument. Visible to the same user: the variables in /proc/<pid>/environ of forge and cast, while they run.
if [[ -n "$REMOTE" ]]; then
  HOST_RPC_AUTH=${DEVNET_RPC_AUTH:-}
  unset DEVNET_RPC_AUTH # no child process inherits it
  RPC=$REMOTE
  NAME=pof-devnet-remote-$$
  RECORD_V2=${DEVNET_RECORD_V2:-contracts/deployments/devnet-aws-v2.json}
  REMOTE_NETWORK=${DEVNET_RPC_NETWORK:-bridge}          # a named network: the end-to-end test's throwaway proxy
  REMOTE_BROADCAST=${DEVNET_RPC_BROADCAST:-broadcast/remote} # forge's transaction logs, apart from a local devnet's

  remote_refuse() { echo "devnet.sh (remote): $1" >&2; exit 2; }

  # Before any container: the URL (no credential in it, TLS), the credential (it exists, and has its shape), the keys.
  remote_validate() {
    [[ "$REMOTE" =~ ^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$ ]] ||
      remote_refuse "DEVNET_RPC_URL must be a plain URL, without a credential in it: use DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE"
    if [[ "$REMOTE" == http://* && "${DEVNET_RPC_ALLOW_HTTP:-}" != 1 ]]; then
      remote_refuse "plain HTTP would send the key in the clear: use https:// (DEVNET_RPC_ALLOW_HTTP=1 is for a local test proxy)"
    fi
    if [[ "${DEVNET_KEYS:-}" == insecure-local && "${DEVNET_RPC_ALLOW_HTTP:-}" != 1 ]]; then
      remote_refuse "DEVNET_KEYS=insecure-local are public keys: anyone could sign for these seats on a shared devnet"
    fi
    if [[ -z "$HOST_RPC_AUTH" && -n "${DEVNET_RPC_AUTH_FILE:-}" ]]; then
      [[ -r "$DEVNET_RPC_AUTH_FILE" ]] || remote_refuse "can't read DEVNET_RPC_AUTH_FILE"
      HOST_RPC_AUTH=$(<"$DEVNET_RPC_AUTH_FILE")
    fi
    [[ -n "$HOST_RPC_AUTH" ]] || remote_refuse "no credential: set DEVNET_RPC_AUTH or DEVNET_RPC_AUTH_FILE (<handle>:<key>)"
    [[ "$HOST_RPC_AUTH" =~ ^[^:[:space:]]+:[^[:space:]]+$ ]] || remote_refuse "the credential must look like <handle>:<key> (not printed)"
    [[ -f "$SOLC" ]] || remote_refuse "solc missing; run: scripts/contracts.sh setup"
  }

  remote_stop() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    if [[ -n "${DEPLOYING_RECORD:-}" ]]; then
      rm -f "$DEPLOYING_RECORD"
      echo "devnet.sh (remote): the deployment failed: no record kept. Any contract it did send stays on the chain, unused" >&2
    fi
  }

  # The container, the credential inside it, and the check every remote command starts with: the chain is the devnet.
  remote_start() {
    trap remote_stop EXIT
    trap 'exit 130' INT TERM
    docker run -d --rm --name "$NAME" --network "$REMOTE_NETWORK" --user "$(id -u):$(id -g)" -e HOME=/tmp \
      -e FOUNDRY_BROADCAST="$REMOTE_BROADCAST" -v "$PWD/contracts:/work" -v "$PWD/$SOLC:/opt/solc/solc:ro" -w /work \
      --entrypoint sleep "$FOUNDRY_IMAGE" 3600 >/dev/null
    local basic
    basic=$(printf '%s' "$HOST_RPC_AUTH" | base64 -w0)
    printf "export ETH_RPC_HEADERS='Authorization: Basic %s'\nexport FOUNDRY_ETH_RPC_HEADERS='[\"Authorization: Basic %s\"]'\n" "$basic" "$basic" |
      docker exec -i "$NAME" sh -c 'umask 077; cat > /dev/shm/rpc-auth'
    local out rc=0
    out=$(in_devnet "$NAME" cast chain-id --rpc-url "$RPC" 2>&1) || rc=$?
    out=${out//"$basic"/[redacted]}
    out=${out//"$HOST_RPC_AUTH"/[redacted]}
    if [[ $rc != 0 ]]; then
      case "$out" in
        *401*) echo "devnet.sh (remote): $RPC refused the credential (HTTP 401): check the handle and the key" >&2 ;;
        *) printf 'devnet.sh (remote): no answer from %s:\n%s\n' "$RPC" "$out" >&2 ;;
      esac
      exit 1
    fi
    if [[ "$out" != "$CHAIN_ID" ]]; then
      echo "devnet.sh (remote): refusing: $RPC answers chain ${out:0:40}, not the devnet's $CHAIN_ID (rule 1: never a public chain)" >&2
      exit 1
    fi
  }

  # in_devnet's arguments: docker exec's flags, the container's name, the command. The command runs with the credential.
  in_devnet() {
    local flags=()
    while [[ "$1" != "$NAME" ]]; do flags+=("$1"); shift; done
    shift
    docker exec -i -w /work "${flags[@]}" "$NAME" sh -c '. /dev/shm/rpc-auth; exec "$@"' sh "$@"
  }
  running() { true; }
  need_up() { :; }
  address_of() { python3 -c 'import sys; from oracle.crypto import address; print(address(int(sys.stdin.read().strip(), 16)))'; }

  record_field() { sed -n 's/.*"'"$1"'": *"\(0x[0-9a-fA-F]*\)".*/\1/p' "$RECORD_V2"; }

  # A record of some other chain (a devnet restored from an older snapshot, say) says so now, not as a confusing revert.
  need_v2() {
    [[ -f "$RECORD_V2" ]] || { echo "v2 not deployed: no $RECORD_V2 (scripts/devnet.sh deploy-v2)" >&2; exit 1; }
    [[ "$(in_devnet "$NAME" cast code --rpc-url "$RPC" "$(verdicts_v2)")" != 0x ]] ||
      { echo "$RECORD_V2 doesn't match this chain: no contract at its Verdicts address" >&2; exit 1; }
  }

  # The record's contracts are on the chain, each with the runtime code the deployment recorded.
  verify_record() {
    local name addr want got bad=0
    for name in verdicts meter race annex heads pool quoter; do
      addr=$(record_field "$name"); want=$(record_field "${name}Codehash")
      [[ -n "$want" ]] || continue
      got=$(in_devnet "$NAME" cast codehash --rpc-url "$RPC" "$addr")
      [[ "$got" == "$want" ]] || { echo "$name at $addr: code hash $got, the record says $want" >&2; bad=1; }
    done
    [[ $bad == 0 ]] && echo "record $RECORD_V2: every contract is on the chain with its recorded code hash" || return 1
  }

  remote_check() { echo "$RPC: chain $CHAIN_ID, block $(in_devnet "$NAME" cast block-number --rpc-url "$RPC"); the credential works"; }

  status() {
    echo "chain $(in_devnet "$NAME" cast chain-id --rpc-url "$RPC"), block $(in_devnet "$NAME" cast block-number --rpc-url "$RPC"), $(in_devnet "$NAME" cast rpc --rpc-url "$RPC" anvil_nodeInfo | sed -n 's/.*"hardFork":"\([^"]*\)".*/\1/p'), at $RPC"
    if [[ -f "$RECORD_V2" ]]; then cat "$RECORD_V2"; echo; verify_record; else echo "not deployed: no $RECORD_V2 (scripts/devnet.sh deploy-v2)"; fi
  }

  # DeployV2.s.sol writes the record during forge's simulation, before anything is sent, so here: a failed broadcast
  # keeps no record (remote_stop), and race and annex get the code hashes the chain has. Their code holds an immutable
  # `start`, the block's timestamp at creation, which the simulation can only guess; the other hashes must match as
  # they are. A second deployment would orphan the first's seats and bounties: removing the record has to be deliberate.
  remote_deploy_v2() {
    [[ ! -f "$RECORD_V2" ]] || { echo "$RECORD_V2 exists: v2 is already deployed. To deploy another, move the record away first" >&2; exit 1; }
    DEPLOYING_RECORD=$RECORD_V2
    deploy_v2
    local name hash
    for name in race annex; do
      hash=$(in_devnet "$NAME" cast codehash --rpc-url "$RPC" "$(record_field "$name")")
      [[ "$hash" =~ ^0x[0-9a-f]{64}$ ]] || { echo "no code hash for $name" >&2; exit 1; }
      sed -i 's/\("'"$name"'Codehash": *"\)0x[0-9a-fA-F]*/\1'"$hash"'/' "$RECORD_V2"
    done
    verify_record
    DEPLOYING_RECORD=
  }

  case "${1:-}" in
    check | status | fund | fund-address | deploy-v2 | digest-v2 | join-v2 | activate-v2 | seats-v2 | fees-v2 | warp) ;;
    up | down | reset) remote_refuse "$1: the remote devnet isn't started or reset from here (unset DEVNET_RPC_URL for the local one)" ;;
    deploy | scenarios) remote_refuse "$1: v1 and its scenarios stay on the local devnet" ;;
    *) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
  esac
  remote_validate
  remote_start
  case "$1" in
    check) remote_check; exit 0 ;;
    deploy-v2) remote_deploy_v2; exit 0 ;;
  esac
fi

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  fund) fund ;;
  fund-address) shift; fund_address "$@" ;;
  deploy) deploy ;;
  deploy-v2) deploy_v2 ;;
  digest-v2) shift; digest_v2 "$@" ;;
  join-v2) shift; join_v2 "$@" ;;
  activate-v2) shift; activate_v2 "$@" ;;
  seats-v2) seats_v2 ;;
  fees-v2) fees_v2 ;;
  warp) shift; warp "$@" ;;
  scenarios) scenarios ;;
  reset) reset ;;
  *) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
