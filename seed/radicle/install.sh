#!/usr/bin/env bash
# The proof-of-fix seed's host install (#251 design L14, task 5.3), run as root by cloud-init on the seed's first boot
# (seed/terraform/user-data.yaml.tftpl writes this folder to /usr/local/lib/radicle-seed and the settings to
# /etc/radicle-seed/seed.env). It is safe to run again.
#
# 1. The data volume (encrypted gp3): formatted only if it has no filesystem, mounted at /var/lib/radicle. The node's
#    key and storage live there, so a replaced instance keeps the same Node ID and the replicated repository.
# 2. The pinned Radicle release, checked by SHA-256 before anything is unpacked (as spikes/radicle/Dockerfile does for
#    the spike's x86_64 build). git, which radicle-node runs to serve fetches.
# 3. seed-setup.sh as the seed's own user: the key, the config with the "block" default, the one seeding policy.
# 4. radicle-seed.service, enabled and started.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=/dev/null
. /etc/radicle-seed/seed.env
: "${RADICLE_VERSION:?}" "${RADICLE_TARGET:?}" "${RADICLE_SHA256:?}" "${DATA_VOLUME_ID:?}"
: "${SEED_RID:?}" "${SEED_ALIAS:?}" "${SEED_EXTERNAL_ADDRESS:?}"
log() { echo "radicle-seed install: $*"; }

# 1. The data volume, found by its volume ID (Nitro instances name EBS volumes nvme*n1 in no fixed order).
dev="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_${DATA_VOLUME_ID//-/}"
for _ in $(seq 120); do [[ -e "$dev" ]] && break; sleep 5; done
[[ -e "$dev" ]] || { log "the data volume $DATA_VOLUME_ID never appeared"; exit 1; }
if ! blkid "$dev" >/dev/null 2>&1; then
  log "formatting the empty data volume"
  mkfs.ext4 -q -L radicle-seed "$dev"
fi
uuid=$(blkid -s UUID -o value "$dev")
install -d -m 0755 /var/lib/radicle
grep -q "UUID=$uuid " /etc/fstab || echo "UUID=$uuid /var/lib/radicle ext4 defaults,nofail 0 2" >>/etc/fstab
mountpoint -q /var/lib/radicle || mount /var/lib/radicle
id radicle >/dev/null 2>&1 || useradd --system --home-dir /var/lib/radicle --shell /sbin/nologin radicle
chown radicle:radicle /var/lib/radicle
chmod 0750 /var/lib/radicle

# 2. Radicle, by checksum; git. The public IPv4 is the Elastic IP, associated just after launch: wait for the way out.
for _ in $(seq 120); do curl -sS -o /dev/null --max-time 10 https://files.radicle.dev/ 2>/dev/null && break; sleep 5; done
command -v git >/dev/null || dnf install -y -q git
command -v xz >/dev/null || dnf install -y -q xz
name="radicle-${RADICLE_VERSION}-${RADICLE_TARGET}"
tmp=$(mktemp -d)
curl -fsSL --proto '=https' --tlsv1.2 -o "$tmp/$name.tar.xz" "https://files.radicle.dev/releases/${RADICLE_VERSION}/$name.tar.xz"
echo "${RADICLE_SHA256}  $tmp/$name.tar.xz" | sha256sum --check --quiet || { log "checksum mismatch: refused"; exit 1; }
tar -xJf "$tmp/$name.tar.xz" -C "$tmp"
install -m 0755 "$tmp/$name/bin/rad" "$tmp/$name/bin/radicle-node" "$tmp/$name/bin/git-remote-rad" /usr/local/bin/
rm -rf "$tmp"
log "installed $(/usr/local/bin/rad --version)"

# 3. The seed's key, config and policy, as its own user, with the node stopped.
systemctl stop radicle-seed 2>/dev/null || true
runuser -u radicle -- env HOME=/var/lib/radicle RAD_HOME=/var/lib/radicle/home \
  bash "$here/seed-setup.sh" "$SEED_RID" "$SEED_ALIAS" "$SEED_EXTERNAL_ADDRESS" main

# 4. The service.
install -m 0644 "$here/radicle-seed.service" /etc/systemd/system/radicle-seed.service
systemctl daemon-reload
systemctl enable --now radicle-seed
log "radicle-seed started"
