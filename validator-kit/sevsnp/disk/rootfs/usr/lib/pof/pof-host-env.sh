#!/bin/bash
# The host's settings from the user data: assigned as literal strings, never sourced (no shell expansion of data).
host_env() {
  local line
  [[ -r "${1:-/run/pof/host.env}" ]] || return 0
  while IFS= read -r line; do
    [[ "$line" =~ ^POF_(ATTEST_NONCE|POWER_OFF|NODE_COMMAND|RADICLE_SEED)=[[:print:]]*$ ]] && declare -g -- "$line"
  done <"${1:-/run/pof/host.env}"
}
