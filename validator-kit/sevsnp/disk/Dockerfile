# The checker image as one measured, read-only disk (#251 L21, task 4.9; #253's SEV-SNP kit). Built by
# scripts/checker-disk.sh, which prepares the context (this folder plus images/: the node image and the test image as
# OCI archives, images.json and images.env) and checks that two builds give the same root hash.
#
# What it makes (the `out` stage, exported to a folder):
#   disk.raw      a GPT disk: an EFI system partition holding the UKI as \EFI\BOOT\BOOTX64.EFI, the root filesystem
#                 (EROFS, read-only) and its dm-verity hash tree; imported as an EBS snapshot and registered as a UEFI
#                 AMI with NitroTPM (validator-kit/SEVSNP-PLAN.md)
#   uki.efi       the unified kernel image: the kernel, the initrd and the kernel command line that names the root
#                 hash (roothash=...), so measuring the UKI measures the whole disk
#   roothash      dm-verity's root hash of the root filesystem
#   pcrs.json     NitroTPM's expected PCR4, PCR7 and PCR12 for this UKI (AWS's nitro-tpm-pcr-compute, standard boot)
#   manifest.json everything above with its sha256, the kernel, the packages, the images, and the checker image's
#                 digest for Validators' list (pof-checker-image/1)
#
# Reproducible: every input is pinned (the Debian base by digest, its packages from one snapshot.debian.org time, the
# Rust image by digest, the sources and the Radicle release by sha256, the images by digest), SOURCE_DATE_EPOCH is the snapshot's time, and
# every filesystem, partition and verity tree is made with fixed UUIDs, salt and timestamps (mkdisk.sh).
#
# Platform: linux/amd64 only. AWS's SEV-SNP instances are AMD (m6a, c6a, r6a).

ARG SNAPSHOT=20261104T212339Z

# ---------- Debian 13 (trixie), packages from one snapshot ----------
# The base: debian:trixie-slim (Debian 13.7), its multi-platform index; it names the same snapshot in its apt sources.
FROM debian@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 AS debian
ARG SNAPSHOT
RUN sed -i \
      -e "s#^URIs: http://deb.debian.org/debian-security#URIs: http://snapshot.debian.org/archive/debian-security/${SNAPSHOT}#" \
      -e "s#^URIs: http://deb.debian.org/debian\$#URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}#" \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update

# ---------- AWS's NitroTPM tools, from source ----------
# https://github.com/aws/NitroTPM-Tools v2.0.0 (commit cfb39eb2ff47e493f278e54768986ba79c5b2421): `nitro-tpm-attest`
# goes on the disk (the NitroTPM's signed attestation document of the boot's PCRs); `nitro-tpm-pcr-compute` computes
# the PCRs a verifier expects from the UKI. Static (musl) builds, as the project's docker/builder.Dockerfile makes them.
FROM rust@sha256:8d0e82abfdf9a38071e07cabc5afba4ddbe077631a80e4e742a760c38beadc33 AS nitrotpm
RUN apk add --no-cache build-base pkgconf linux-headers openssl-dev openssl-libs-static
ADD --checksum=sha256:bd4efc89ee01aca8ff771cae268d84333b7594c2d4afee50bb13b859f1113c3f \
    https://github.com/tpm2-software/tpm2-tss/releases/download/4.2.2/tpm2-tss-4.2.2.tar.gz /tmp/tpm2-tss.tar.gz
RUN mkdir /tmp/tss && tar xzf /tmp/tpm2-tss.tar.gz -C /tmp/tss --strip-components 1 && cd /tmp/tss \
    && ./configure --enable-option-checking=fatal --prefix=/usr/local --disable-shared --enable-nodl --disable-fapi \
       --disable-vendor --disable-policy --enable-tcti-device --disable-tcti-mssim --disable-tcti-swtpm \
       --disable-tcti-pcap --disable-tcti-libtpms --disable-tcti-cmd --disable-tcti-spi-helper \
       --disable-tcti-spi-ftdi --disable-tcti-i2c-helper --disable-tcti-i2c-ftdi --disable-weakcrypto \
       --disable-doxygen-doc >/dev/null \
    && make -j"$(nproc)" >/dev/null && make install >/dev/null && rm -rf /tmp/tss /tmp/tpm2-tss.tar.gz
ADD --checksum=sha256:ad5adabc480ac99804746d4442c8b9dcbd394338ca05a7d79027cee11954d614 \
    https://github.com/aws/NitroTPM-Tools/archive/cfb39eb2ff47e493f278e54768986ba79c5b2421.tar.gz /tmp/ntt.tar.gz
ENV PKG_CONFIG_ALL_STATIC=1 AWS_LC_SYS_USE_SYSTEM=0 CARGO_HOME=/cargo
RUN mkdir /src && tar xzf /tmp/ntt.tar.gz -C /src --strip-components 1 && cd /src \
    && RUSTFLAGS="--remap-path-prefix=/src=. --remap-path-prefix=/cargo=cargo -C strip=symbols" \
       cargo build --locked --release --bins \
    && install -D -m 0755 target/release/nitro-tpm-attest /out/nitro-tpm-attest \
    && install -D -m 0755 target/release/nitro-tpm-pcr-compute /out/nitro-tpm-pcr-compute

# ---------- Radicle, the validator's own node (#251 L11, L12) ----------
# Radicle heartwood 1.10.3 (2026-09-08, commit 7e1cb406bb935c3de008d2171e8961f57b4336ea), the x86_64 musl static build:
# the release seed/radicle/install.sh and spikes/radicle/Dockerfile pin, checked by ADD against the release's own
# .sha256. rad, radicle-node and git-remote-rad go on the disk (/usr/lib/pof/radicle/bin); the node's key and storage
# are on the data volume (pof-radicle.sh). busybox 1.37.0, for unxz and tar only.
FROM busybox@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec AS radicle
ADD --checksum=sha256:3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751 \
    https://files.radicle.dev/releases/1.10.3/radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz /tmp/radicle.tar.xz
RUN mkdir -p /out && unxz -c /tmp/radicle.tar.xz | tar -x -C /tmp \
    && for b in rad radicle-node git-remote-rad; do cp /tmp/radicle-1.10.3-x86_64-unknown-linux-musl/bin/$b /out/$b; done \
    && chmod 0755 /out/*

# ---------- The root filesystem: what the disk runs ----------
# The kernel's modules, systemd, the Docker engine (docker.io, containerd, runc), git (radicle-node runs it to serve
# fetches), Radicle, and the kit's units and scripts. No shell access (no SSH, no SSM agent), no cloud-init: the
# instance's user data is read as data (pof-config), never run. The user pof (uid 10001, the node container's) runs
# radicle-node; its password-change day (the build's day) is left empty, and the user databases' backups go.
FROM debian AS rootfs
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      linux-image-cloud-amd64 systemd systemd-sysv systemd-resolved systemd-timesyncd udev dbus kmod \
      docker.io docker-cli containerd runc iptables ca-certificates curl e2fsprogs util-linux git \
    && groupadd -g 10001 pof \
    && useradd -u 10001 -g 10001 -M -d /data/state/radicle -s /usr/sbin/nologin pof \
    && sed -i 's/^pof:\([^:]*\):[0-9]*:/pof:\1::/' /etc/shadow \
    && rm -f /etc/passwd- /etc/shadow- /etc/group- /etc/gshadow- /etc/subuid- /etc/subgid-
COPY rootfs/ /
COPY --from=nitrotpm /out/nitro-tpm-attest /usr/lib/pof/nitro-tpm-attest
COPY --from=radicle /out/ /usr/lib/pof/radicle/bin/
COPY images/ /usr/share/pof/images/
RUN chmod 0755 /usr/lib/pof/*.sh \
    && systemctl enable systemd-networkd systemd-resolved systemd-timesyncd pof-data.service pof-images.service \
       pof-config.service pof-radicle-setup.service pof-radicle.service pof-radicle-ready.service \
       pof-attest.service pof-node.service \
    && systemctl mask apt-daily.timer apt-daily-upgrade.timer e2scrub_all.timer e2scrub_reap.service fstrim.timer \
       getty.target serial-getty@ttyS0.service console-getty.service \
    && rm -rf /boot/* /var/lib/apt/lists/* /var/cache/* /var/log/* /var/lib/dpkg/*-old /var/cache/debconf/*-old \
       /usr/share/doc /usr/share/man /usr/share/info /var/lib/systemd/catalog/database \
    && : > /etc/machine-id && ln -sfn /etc/machine-id /var/lib/dbus/machine-id

# ---------- The tools that make the disk ----------
FROM debian AS tools
RUN DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      linux-image-cloud-amd64 dracut dracut-core systemd systemd-cryptsetup systemd-ukify systemd-boot-efi \
      python3-pefile erofs-utils cryptsetup-bin mtools dosfstools fdisk zstd binutils
COPY --from=nitrotpm /out/nitro-tpm-pcr-compute /usr/local/bin/nitro-tpm-pcr-compute
COPY mkdisk.sh /usr/local/bin/mkdisk.sh

FROM tools AS disk
ARG SOURCE_DATE_EPOCH
RUN --mount=type=bind,from=rootfs,target=/rootfs \
    SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:?}" bash /usr/local/bin/mkdisk.sh /rootfs /out

FROM scratch AS out
COPY --from=disk /out/ /
