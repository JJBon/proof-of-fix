#!/bin/bash
# The data volume (#251 L21: writable state off the measured disk). The instance has two disks: the measured one (its
# root and verity partitions, read-only) and one data volume, labelled POFDATA, formatted on the first boot when blank.
# On it, /data/scratch (Docker's and containerd's stores, the fixes' checkouts) is wiped at every boot, so every boot
# starts from the images the measured disk loads; /data/state (the node's rounds, receipts and spending ledger) persists,
# because a node that sealed a vote must reveal it after a restart and its spending caps span runs, and so does
# /data/state/radicle (the Radicle node's key, whose Node ID the registration names, and its storage). State is data
# the node reads, never code it runs. Any other layout is a setup error: the instance powers off.
set -euo pipefail
say() { echo "pof-data: $*"; }
fail() { say "setup error: $*; powering off"; systemctl --no-block poweroff; exit 1; }

root_part=$(sed -n 's/.*systemd\.verity_root_data=\([^ ]*\).*/\1/p' /proc/cmdline)
[[ -n "$root_part" ]] || fail "no verity root on the kernel command line"
udevadm settle --timeout=30 || true
root_disk=/dev/$(lsblk -no PKNAME "$(readlink -f "$root_part")")
data=""
for _ in $(seq 1 30); do
  mapfile -t others < <(lsblk -dnpo NAME,TYPE | awk '$2 == "disk" {print $1}' | grep -vxF "$root_disk" || true)
  [[ ${#others[@]} -ge 1 ]] && break
  sleep 1
done
[[ ${#others[@]} == 1 ]] || fail "expected exactly one data volume besides $root_disk, found: ${others[*]:-none}"
data=${others[0]}
label=$(blkid -p -s LABEL -o value "$data" 2>/dev/null || true)
if [[ -z "$(blkid -p -o value -s TYPE "$data" 2>/dev/null || true)" && -z "$(lsblk -no PTTYPE "$data" | tr -d ' ')" ]]; then
  say "formatting the blank data volume $data (first boot)"
  mkfs.ext4 -q -L POFDATA "$data"
  label=POFDATA
fi
[[ "$label" == POFDATA ]] || fail "$data isn't blank and isn't labelled POFDATA: refusing to touch it"
mkdir -p /data
mount -o nodev,nosuid "$data" /data
rm -rf --one-file-system /data/scratch
install -d -m 0711 /data/scratch /data/scratch/docker /data/scratch/containerd
install -d -o 10001 -g 10001 -m 0755 /data/scratch/pof-node /data/scratch/pof-node/src
install -d -o 10001 -g 10001 -m 0700 /data/state /data/state/pof
# The Radicle node's home (its key, made once, and its storage) persists; its working copy is scratch, made again from
# the storage at every boot (pof-radicle.sh), so no git config or hook in it outlives the boot.
install -d -o 10001 -g 10001 -m 0700 /data/state/radicle
install -d -o 10001 -g 10001 -m 0755 /data/scratch/radicle
say "data volume $data mounted; scratch wiped"
