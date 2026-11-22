# syntax=docker/dockerfile:1.7
# The Radicle spike's node image (proof-of-fix#190): a pinned Radicle release (rad, radicle-node, git-remote-rad) on
# the pinned Foundry image, so a judge's gate can read Heads with `cast call`. The release is the only download, here
# at build time; the containers then run on an internal Docker network with no route out (scripts/radicle-spike.sh).
#
# Radicle heartwood 1.10.3 (2026-09-08, commit 7e1cb406bb935c3de008d2171e8961f57b4336ea), the x86_64 musl static
# build. SHA-256 3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751: checked by ADD below, and equal to
# the release's own .sha256 file (verified 2026-11-09).

# busybox 1.37.0, for unxz and tar only.
FROM busybox@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec AS fetch
ADD --checksum=sha256:3d78e3ffc17f9e6eca7fcd3acc439f2252060532eb457cf17f2747fed4cc6751 \
    https://files.radicle.dev/releases/1.10.3/radicle-1.10.3-x86_64-unknown-linux-musl.tar.xz /tmp/radicle.tar.xz
RUN mkdir -p /opt && unxz -c /tmp/radicle.tar.xz | tar -x -C /opt && mv /opt/radicle-1.10.3-x86_64-unknown-linux-musl /opt/radicle

# Foundry v1.8.5, the same image as scripts/contracts.sh and scripts/devnet.sh (git and cast included).
FROM ghcr.io/foundry-rs/foundry@sha256:32c8ea9ef052a440cb1620175987a3f49eff8b068a0c6a3d09ebf7f5f9a0e043
COPY --from=fetch /opt/radicle/bin/rad /opt/radicle/bin/radicle-node /opt/radicle/bin/git-remote-rad /usr/local/bin/
COPY --chmod=755 node-init.sh gate.sh /usr/local/bin/
ENV RAD_HOME=/home/foundry/.radicle \
    GIT_AUTHOR_NAME=spike GIT_AUTHOR_EMAIL=spike@localhost GIT_COMMITTER_NAME=spike GIT_COMMITTER_EMAIL=spike@localhost
WORKDIR /home/foundry
ENTRYPOINT []
CMD ["sleep", "infinity"]
