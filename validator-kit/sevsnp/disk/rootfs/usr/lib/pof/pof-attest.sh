#!/bin/bash
# Attests this boot and checks attested mode, printing the evidence on the serial console (`aws ec2 get-console-output`
# reads it, with no credentials on the instance):
#   POF-ATTEST snp-report <base64>   the SEV-SNP report (AMD-signed; on EC2 its MEASUREMENT is AWS's firmware), whose
#                                    report data is sha512("pof-boot-attestation/1" | nonce | root hash)
#   POF-ATTEST snp-cert <name> <b64> the host's certificates for it (on shared tenancy the VLEK that signs it)
#   POF-ATTEST nitrotpm <base64>     NitroTPM's attestation document (signed by AWS's Nitro PKI): PCR4, 7 and 12 measure
#                                    the UKI, so the root hash; its user data is the SEV-SNP report's sha384 and its
#                                    nonce the boot's nonce, binding the two documents to one boot
#   POF-ATTEST attested-check <json> the node in attested mode: every listed image present at its digest, and an
#                                    unlisted image refused
# The nonce is POF_ATTEST_NONCE from the user data (hex, the verifier's), else this boot's ID.
set -uo pipefail
# The user data was read by pof-config.service (before this one and pof-radicle.service): /run/pof/host.env.
. /usr/lib/pof/pof-host-env.sh
host_env
. /usr/share/pof/images/images.env  # on the measured disk
say() { echo "POF-ATTEST $*"; }
roothash=$(sed -n 's/.*roothash=\([0-9a-f]*\).*/\1/p' /proc/cmdline)
nonce=${POF_ATTEST_NONCE:-$(tr -d '-' </proc/sys/kernel/random/boot_id)}
[[ "$nonce" =~ ^[0-9a-f]{2,128}$ ]] || { say "error POF_ATTEST_NONCE must be hex"; exit 1; }
data=$(printf 'pof-boot-attestation/1\n%s\n%s' "$nonce" "$roothash" | sha512sum | cut -c1-128)
say "roothash $roothash"
say "nonce $nonce"
# The TPM's PCRs as the kernel reads them (unsigned, for the operator's eye; the NitroTPM document below signs them).
if [[ -r /sys/class/tpm/tpm0/pcr-sha384/4 ]]; then
  say "pcrs sha384 4=$(cat /sys/class/tpm/tpm0/pcr-sha384/4) 7=$(cat /sys/class/tpm/tpm0/pcr-sha384/7) 12=$(cat /sys/class/tpm/tpm0/pcr-sha384/12)"
fi
ok=1
sock_gid=$(stat -c %g /var/run/docker.sock)
install -d -o 10001 -g 10001 -m 0700 /run/pof/snp  # the node's container (uid 10001) writes the report here
if out=$(docker run --rm --network none --read-only --device /dev/sev-guest --group-add 10001 -v /run/pof/snp:/run/pof/snp \
    --entrypoint python3 "$NODE_IMAGE" -m oracle snp-report --data "$data" --out /run/pof/snp/report.bin \
    --certs-dir /run/pof/snp/certs 2>&1); then
  say "snp-summary $out"
  say "snp-report $(base64 -w0 /run/pof/snp/report.bin)"
  for cert in /run/pof/snp/certs/*.der; do  # the VLEK (shared tenancy) or VCEK that signs the report
    [[ -f "$cert" ]] && say "snp-cert $(basename "$cert" .der) $(base64 -w0 "$cert")"
  done
  printf '%s' "$(sha384sum /run/pof/snp/report.bin | cut -c1-96)" >/run/pof/nitro-user-data
else
  say "snp-report unavailable: $(tr '\n' ' ' <<<"$out")"
  ok=0
  printf 'no-snp-report' >/run/pof/nitro-user-data
fi
printf '%s' "$nonce" >/run/pof/nitro-nonce
if /usr/lib/pof/nitro-tpm-attest --user-data /run/pof/nitro-user-data --nonce /run/pof/nitro-nonce \
    >/run/pof/nitrotpm.cbor 2>/run/pof/nitrotpm.err; then
  say "nitrotpm $(base64 -w0 /run/pof/nitrotpm.cbor)"
else
  say "nitrotpm unavailable: $(tr '\n' ' ' </run/pof/nitrotpm.err)"
  ok=0
fi
if out=$(docker run --rm --network none --read-only -v /var/run/docker.sock:/var/run/docker.sock \
    --group-add "$sock_gid" -v /usr/share/pof/images/images.json:/etc/pof/images.json:ro \
    -e ORACLE_ATTESTED_IMAGES=/etc/pof/images.json --entrypoint python3 "$NODE_IMAGE" -m oracle attested-check 2>&1); then
  say "attested-check $out"
else
  say "attested-check failed: $(tr '\n' ' ' <<<"$out")"
  ok=0
fi
if [[ "$ok" == 1 ]]; then touch /run/pof/attest-ok; say "ok"; else say "incomplete: the node won't run on this boot"; fi
