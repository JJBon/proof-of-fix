#!/bin/bash
# The node's configuration from the instance's user data, read as data and never run (there is no cloud-init): lines
# KEY=VALUE, the node's ORACLE_* settings (secrets only by Secrets Manager ARN, ORACLE_*_SECRET_ARN and the like) and
# the host's POF_* ones (POF_RADICLE_SEED: the seed this host's Radicle node dials, "<nid>@<host>:<port>"). Settings
# the measured disk fixes itself (attested mode, the sandbox, the key provider, the paths, how the node reaches this
# host's Radicle node) are refused, as is a secret's value. Writes /run/pof/node.env (docker run --env-file: no shell
# expansion) and /run/pof/host.env.
set -euo pipefail
RUN=${POF_RUN_DIR:-/run/pof}  # tests/test_sevsnp_kit.py runs it elsewhere
IMDS=${POF_IMDS:-http://169.254.169.254}
install -d -m 0755 "$RUN"
: >"$RUN/node.env"
: >"$RUN/host.env"
token=$(curl -sf -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' "$IMDS/latest/api/token") || exit 0
code=$(curl -s -o "$RUN/user-data" -w '%{http_code}' -H "X-aws-ec2-metadata-token: $token" \
  "$IMDS/latest/user-data") || exit 0
[[ "$code" == 200 ]] || { echo "pof-config: no user data: attest only"; exit 0; }
fixed='^(ORACLE_ATTESTED_IMAGES|ORACLE_SANDBOX|DOCKER_SOCKET|ORACLE_KEYS|ORACLE_SNP_DEVICE|ORACLE_SRC_ROOT|ORACLE_ROUNDS|ORACLE_RECEIPTS|ORACLE_SPEND_LEDGER|ORACLE_PRIVATE_KEY|RPC_API_KEY|MODEL_API_KEY|ORACLE_GIT_TOKEN|ORACLE_RPC_TOKEN|ORACLE_EXCHANGE_TOKEN|ORACLE_RADICLE_EXEC|ORACLE_RADICLE_REPO)='
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  if [[ ! "$line" =~ ^[A-Z][A-Z0-9_]*=[[:print:]]*$ ]] || [[ "$line" =~ $fixed ]]; then
    echo "pof-config: refused a user-data line for ${line%%=*}"
    continue
  fi
  case "$line" in
    ORACLE_* | AWS_REGION=* | MODEL_API_KEY_SECRET_ARN=* | RPC_API_KEY_SECRET_ARN=*) printf '%s\n' "$line" >>"$RUN/node.env" ;;
    POF_ATTEST_NONCE=* | POF_POWER_OFF=* | POF_NODE_COMMAND=* | POF_RADICLE_SEED=*) printf '%s\n' "$line" >>"$RUN/host.env" ;;
    *) echo "pof-config: ignored ${line%%=*}" ;;
  esac
done <"$RUN/user-data"
rm -f "$RUN/user-data"
chmod 0600 "$RUN/node.env" "$RUN/host.env"
