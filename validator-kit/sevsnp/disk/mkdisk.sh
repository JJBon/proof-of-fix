#!/bin/bash
# Makes the measured disk from the root filesystem (the Dockerfile's `tools` stage runs it): mkdisk.sh ROOTFS OUT.
# Every step is deterministic: fixed UUIDs, salt and timestamps (SOURCE_DATE_EPOCH), so the same inputs give the same
# root hash, UKI and disk, byte for byte.
set -euo pipefail
ROOTFS=$1 OUT=$2
: "${SOURCE_DATE_EPOCH:?}"
export SOURCE_DATE_EPOCH TZ=UTC LC_ALL=C.UTF-8
mkdir -p "$OUT"
W=$(mktemp -d)

KVER=$(ls "$ROOTFS/usr/lib/modules")
[[ $(wc -w <<<"$KVER") == 1 ]] || { echo "mkdisk: expected one kernel, found: $KVER" >&2; exit 1; }
[[ -f /boot/vmlinuz-$KVER ]] || { echo "mkdisk: the tools stage has no kernel $KVER (the stages' snapshots differ?)" >&2; exit 1; }
# What the kit needs from the kernel: the SEV-SNP guest driver and TSM reports, the TPM (NitroTPM is a CRB TPM 2.0),
# dm-verity and EROFS for the root, ENA and NVMe for EC2, overlay for the volatile /etc and /var.
for opt in AMD_MEM_ENCRYPT SEV_GUEST TSM_REPORTS TCG_CRB DM_VERITY EROFS_FS ENA_ETHERNET BLK_DEV_NVME OVERLAY_FS EFI_STUB; do
  grep -Eq "^CONFIG_${opt}=(y|m)$" "/boot/config-$KVER" || { echo "mkdisk: kernel $KVER lacks CONFIG_$opt" >&2; exit 1; }
done

# ---------- 1. The root filesystem, writable copy for the last fixed files ----------
cp -a "$ROOTFS" "$W/root"
ln -sfn ../run/systemd/resolve/stub-resolv.conf "$W/root/etc/resolv.conf"
printf 'pof-checker\n' >"$W/root/etc/hostname"
printf '127.0.0.1 localhost\n::1 localhost\n' >"$W/root/etc/hosts"
dpkg-query --admindir="$W/root/var/lib/dpkg" -W -f '${Package}=${Version}\n' | sort >"$OUT/packages.txt"

# ---------- 2. EROFS, then dm-verity ----------
mkfs.erofs -T"$SOURCE_DATE_EPOCH" --ignore-mtime -U 5d6f8c2e-1b7a-4f0e-9c3d-504f46524f4f -L pof-root \
  -zlz4hc "$W/root.erofs" "$W/root" >/dev/null
SALT=$(printf 'proof-of-fix checker disk, dm-verity salt' | sha256sum | cut -c1-64)
veritysetup format --hash=sha256 --data-block-size=4096 --hash-block-size=4096 --salt="$SALT" \
  --uuid=7c1f2b3a-4d5e-4f60-8a9b-504f46564552 "$W/root.erofs" "$W/root.verity" >"$W/verity.txt"
ROOTHASH=$(sed -n 's/^Root hash:[[:space:]]*//p' "$W/verity.txt")
[[ ${#ROOTHASH} == 64 ]] || { cat "$W/verity.txt" >&2; echo "mkdisk: no root hash" >&2; exit 1; }
printf '%s\n' "$ROOTHASH" >"$OUT/roothash"
# The Discoverable Partitions convention: the root partition's UUID is the root hash's first 128 bits, the verity
# partition's its last 128 bits.
uuid() { printf '%s-%s-%s-%s-%s' "${1:0:8}" "${1:8:4}" "${1:12:4}" "${1:16:4}" "${1:20:12}"; }
ROOT_UUID=$(uuid "${ROOTHASH:0:32}") VERITY_UUID=$(uuid "${ROOTHASH:32:32}")

# ---------- 3. The kernel command line: the root hash is in it, so the UKI's measurement covers the disk ----------
CMDLINE="console=ttyS0,115200n8 root=/dev/mapper/root rootfstype=erofs ro roothash=$ROOTHASH"
CMDLINE+=" systemd.verity_root_data=/dev/disk/by-partuuid/$ROOT_UUID"
CMDLINE+=" systemd.verity_root_hash=/dev/disk/by-partuuid/$VERITY_UUID"
CMDLINE+=" systemd.verity_root_options=panic-on-corruption systemd.volatile=overlay"
CMDLINE+=" nvme_core.io_timeout=4294967295 loglevel=4 systemd.show_status=error"
printf '%s\n' "$CMDLINE" >"$OUT/cmdline"

# ---------- 4. The initrd (dracut, reproducible) ----------
dracut --quiet --reproducible --no-hostonly --no-hostonly-cmdline --force --kver "$KVER" \
  --modules "base systemd systemd-initrd systemd-veritysetup dm rootfs-block fs-lib udev-rules kernel-modules" \
  --omit "network plymouth i18n resume crypt lvm mdraid multipath nfs iscsi nbd" \
  --add-drivers "nvme nvme_core ena dm_mod dm_verity erofs overlay" \
  --compress zstd "$W/initrd.img"

# ---------- 5. The UKI ----------
ukify build --linux "/boot/vmlinuz-$KVER" --initrd "$W/initrd.img" --cmdline "$CMDLINE" \
  --os-release "@$W/root/usr/lib/os-release" --uname "$KVER" --output "$OUT/uki.efi" >/dev/null

# ---------- 6. The EFI system partition (FAT32, fixed volume ID, timestamps from SOURCE_DATE_EPOCH) ----------
ESP_MIB=256
truncate -s "${ESP_MIB}M" "$W/esp.img"
mkfs.vfat -F 32 --invariant -i 504f4631 -n POFESP "$W/esp.img" >/dev/null
export MTOOLS_SKIP_CHECK=1
mmd -i "$W/esp.img" ::/EFI ::/EFI/BOOT
touch -d "@$SOURCE_DATE_EPOCH" "$OUT/uki.efi"  # mcopy -m keeps the file's time: the epoch's, not the build's
mcopy -i "$W/esp.img" -m "$OUT/uki.efi" ::/EFI/BOOT/BOOTX64.EFI

# ---------- 7. The GPT disk: ESP, root, verity; whole GiB (an EBS volume's unit) ----------
MIB=$((1024 * 1024))
mib() { echo $(( ($(stat -c %s "$1") + MIB - 1) / MIB )); }
ROOT_MIB=$(mib "$W/root.erofs") VERITY_MIB=$(mib "$W/root.verity")
USED=$((1 + ESP_MIB + ROOT_MIB + VERITY_MIB + 1))
DISK_GIB=$(( (USED + 1023) / 1024 ))
truncate -s "${DISK_GIB}G" "$OUT/disk.raw"
sfdisk --quiet --no-reread --no-tell-kernel "$OUT/disk.raw" <<EOF
label: gpt
label-id: 504F4644-4953-4B00-8000-000000000001
first-lba: 2048
start=2048, size=$((ESP_MIB * 2048)), type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, uuid=504F4645-5350-4000-8000-000000000001, name="esp"
size=$((ROOT_MIB * 2048)), type=4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709, uuid=$ROOT_UUID, name="root-x86-64"
size=$((VERITY_MIB * 2048)), type=2C7357ED-EBD2-46D9-AEC1-23D437EC2BF5, uuid=$VERITY_UUID, name="root-x86-64-verity"
EOF
put() { # image partition-number
  local start
  start=$(sfdisk --json "$OUT/disk.raw" | python3 -c "import json,sys; print(json.load(sys.stdin)['partitiontable']['partitions'][$2-1]['start'])")
  dd if="$1" of="$OUT/disk.raw" bs=512 seek="$start" conv=notrunc,sparse status=none
}
put "$W/esp.img" 1
put "$W/root.erofs" 2
put "$W/root.verity" 3

# ---------- 8. NitroTPM's expected PCRs, and the manifest ----------
nitro-tpm-pcr-compute --image "$OUT/uki.efi" >"$OUT/pcrs.json"
cp "$W/root/usr/share/pof/images/images.json" "$OUT/images.json"
python3 - "$OUT" "$KVER" "$CMDLINE" "$DISK_GIB" <<'PY'
import hashlib, json, sys
from pathlib import Path
out, kver, cmdline, gib = Path(sys.argv[1]), sys.argv[2], sys.argv[3], int(sys.argv[4])
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
pcrs = json.loads((out / "pcrs.json").read_text())["Measurements"]
roothash = (out / "roothash").read_text().strip()
# The checker image's digest on Validators' list (Attestation.image, #251 L21 rule 3): what a verifier recomputes from
# the attestation it checks. NitroTPM's PCR4 measures the UKI, whose command line names the root hash; PCR7 and PCR12
# are the standard boot's. The SEV-SNP measurement is AWS's firmware alone and is checked on its own (the plan).
measured = {"format": "pof-checker-image/1", "platform": "amd64", "hash": pcrs["HashAlgorithm"].lower(),
            "pcr4": pcrs["PCR4"].lower(), "pcr7": pcrs["PCR7"].lower(), "pcr12": pcrs["PCR12"].lower(),
            "roothash": roothash}
canon = json.dumps(measured, sort_keys=True, separators=(",", ":")).encode()
manifest = {"format": "pof-checker-disk/1", "kernel": kver, "cmdline": cmdline, "roothash": roothash,
            "measured": measured, "image_digest": "0x" + hashlib.sha256(canon).hexdigest(),
            "disk_gib": gib, "images": json.loads((out / "images.json").read_text()),
            "sha256": {n: sha(out / n) for n in ("disk.raw", "uki.efi", "pcrs.json", "images.json", "packages.txt")}}
(out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
PY
rm -rf "$W"
