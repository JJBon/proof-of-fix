# The oracle node's image (proof-of-fix#94). Standard library only, so the base image is all it needs.
# Pinned by digest: Python 3.12 on Debian 13 slim, the test image's base, with git at a pinned version.
# Build from the repository root:  docker build -f oracle/Dockerfile -t pof-oracle-node .
# The image's own digest is what a node reports as `checker_image` (POF_ORACLE_IMAGE) and what a dstack attestation
# measures; publish the digest with each release so anyone can check a node runs it.
# No Docker CLI (#116): given the host's Docker socket, the node starts each fix's tests in a sibling container through
# the Docker Engine API (oracle/sandbox.py DockerApi, standard library). See validator-kit/terraform/node-user-data.sh.tftpl.
# On the AWS devnet's seats host (platform#219) each role seat runs `seat run --until-idle 600` (oracle/seat.py: the
# seat's secrets from its files, devnet-seats.sh's settings). scripts/seats-image.sh builds and pushes it.
# The base: the test image's (oracle/test-image/Dockerfile), python:3.12-slim-trixie (Python 3.12.16, Debian 13.7),
# its multi-platform index (the seats host is arm64). Debian, not Alpine (#251 L21, 2026-11-20): Alpine's repositories
# keep only each package's latest build, so `apk add git` installed whatever Alpine served that day and the same
# commit could build another node image (another checker disk's root hash); snapshot.debian.org keeps every version.
FROM python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# The snapshot the base image names in its own apt sources (its packages are from 2026-11-04T21:23:39Z).
ARG SNAPSHOT=20261104T212339Z
ARG GIT_VERSION=1:2.47.3-0+deb13u1

# git, pinned: the node fetches each claimed commit itself (oracle/fetch.py, #115). Nothing else is installed (git's
# dependencies come with it at the snapshot's versions); the base's packages are the base digest's.
# Reproducible (scripts/checker-disk.sh, scripts/seats-image.sh): apt's lists, caches and logs go, and so do the files
# that record the build's own time (dpkg's and debconf's backups, ldconfig's cache, the user databases' backups); the
# user's password-change day (the build's day) is left empty; the layers' timestamps are SOURCE_DATE_EPOCH's.
RUN sed -i \
      -e "s#^URIs: http://deb.debian.org/debian-security#URIs: http://snapshot.debian.org/archive/debian-security/${SNAPSHOT}#" \
      -e "s#^URIs: http://deb.debian.org/debian\$#URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}#" \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "git=${GIT_VERSION}" \
    && dpkg-query -W -f '${Package}=${Version}\n' git \
    && useradd -m -u 10001 -U -s /bin/sh oracle \
    && sed -i 's/^oracle:\([^:]*\):[0-9]*:/oracle:\1::/' /etc/shadow \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /var/log/apt /var/log/dpkg.log /var/log/alternatives.log \
      /var/cache/ldconfig/aux-cache /var/lib/dpkg/*-old /var/cache/debconf/*-old /etc/*- /var/log/lastlog \
      /var/log/faillog
WORKDIR /app
COPY oracle/ /app/oracle/
# The judge's prompt, verdict parser and fake (pof/judges, #89) and the gateway client (scripts/judge_run.py).
COPY pof/ /app/pof/
# The v2 node finds a submission's pull request through the bot's repository host adapters (bot/forge.py, #104).
COPY bot/ /app/bot/
COPY scripts/judge_run.py /app/scripts/judge_run.py
# The bot service (#210, proof-of-fix PR #211) runs from this same image on the AWS devnet's seats host: `python3 -m
# pofctl bot watch` (standard library, with oracle/ and bot/).
COPY pofctl/ /app/pofctl/
USER oracle
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python3", "-m", "oracle"]
CMD ["info"]
