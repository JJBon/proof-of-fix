# The sandbox's test image (oracle/sandbox.py TEST_IMAGE; #251 L21): the image every fix's tests run in.
# Python 3.12 on Debian 13 (trixie) slim, pinned by digest, plus exactly two packages: git and bash, at pinned
# versions, from the one Debian snapshot the base image was built from. Nothing else: no compiler, no pip install.
# Debian, not Alpine: Alpine's repositories keep only each package's latest build, so a pinned `apk add git=<v>`
# stops building once that build is replaced; snapshot.debian.org keeps every version, so this file builds the same
# bytes for as long as the snapshot is served.
# Build it with scripts/test-image.sh, which builds reproducibly (SOURCE_DATE_EPOCH, timestamps rewritten), loads it
# into the local Docker and checks that its digest is the pinned one.
# The base: python:3.12-slim-trixie (Python 3.12.16, Debian 13.7), its multi-platform index.
FROM python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# The snapshot the base image names in its own apt sources (its packages are from 2026-11-04T21:23:39Z).
ARG SNAPSHOT=20261104T212339Z
# bash is already in the base (Essential); naming its version makes the build fail if the base ever differs.
ARG BASH_VERSION=5.2.37-2+b10
ARG GIT_VERSION=1:2.47.3-0+deb13u1

# Reproducible: apt's lists, caches and logs go, and so do the files that record the build's own time (dpkg's and
# debconf's backups, ldconfig's cache); the layers' timestamps are SOURCE_DATE_EPOCH's (scripts/test-image.sh).
RUN sed -i \
      -e "s#^URIs: http://deb.debian.org/debian-security#URIs: http://snapshot.debian.org/archive/debian-security/${SNAPSHOT}#" \
      -e "s#^URIs: http://deb.debian.org/debian\$#URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}#" \
      /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      "bash=${BASH_VERSION}" "git=${GIT_VERSION}" \
    && dpkg-query -W -f '${Package}=${Version}\n' bash git \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /var/log/apt /var/log/dpkg.log /var/log/alternatives.log \
      /var/cache/ldconfig/aux-cache /var/lib/dpkg/*-old /var/cache/debconf/*-old

CMD ["python3"]
