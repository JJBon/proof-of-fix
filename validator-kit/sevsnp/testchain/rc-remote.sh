#!/usr/bin/env bash
# The test-chain host's side of the release candidate's AWS run (proof-of-fix#251 task 7.0): run as root, by cloud-init
# (install) and by scripts/rc-aws.sh over SSM Run Command (the rest). Nothing here is pulled unpinned: the commit comes
# as a git bundle checked against its SHA, the images as one `docker save` archive checked image by image against the
# IDs this checkout's pins gave on the operator's machine, solc as the pinned build checked by its SHA-256.
#
#   rc-remote.sh install                          first boot: Docker and git from the AL2023 repository (locked to the
#                                                 AMI's release), Docker started with /etc/docker/daemon.json
#   rc-remote.sh provision <bucket> <sha>         the bundle, the images and solc from the run's bucket; checked
#   rc-remote.sh start <sha> <external> <image> <bind> <wait>
#                                                 `scripts/integration.sh --release-candidate <sha> --external` as the
#                                                 unit pof-rc-external: POF_EXT_MODE=aws, the chain and the seed
#                                                 published on <bind> (this host's private address), the SEV-SNP host's
#                                                 validator address and the disk's image digest
#   rc-remote.sh status                           one line `@status {...}`: the unit's state, ready.json, external.json
#                                                 and the log's tail
#   rc-remote.sh stop-run                         stop the unit (the run cleans its containers up)
set -euo pipefail
POF=/opt/pof
WORK=$POF/work
LOGS=$POF/logs
die() { echo "rc-remote: $*" >&2; exit 2; }
sha_ok() { [[ "$1" =~ ^[0-9a-f]{40}$ ]] || die "not a commit SHA: '$1'"; }

case "${1:-}" in
  install)
    dnf install -y -q docker git tar gzip
    systemctl enable --now docker
    echo "rc-remote: $(docker --version); $(git --version); $(python3 --version)"
    ;;
  provision)
    bucket=${2:-} sha=${3:-}
    [[ "$bucket" =~ ^[a-z0-9.-]{3,63}$ ]] || die "not a bucket name: '$bucket'"
    sha_ok "$sha"
    systemctl is-active --quiet docker || systemctl start docker
    mkdir -p "$WORK" "$LOGS"
    cd "$WORK"
    for f in repo.bundle images.tar images.json solc.tgz; do
      aws s3 cp --only-show-errors "s3://$bucket/$sha/$f" "$f"
    done
    rm -rf repo
    git clone -q repo.bundle repo
    git -C repo checkout -q --detach "$sha"
    [[ "$(git -C repo rev-parse HEAD)" == "$sha" ]] || die "the bundle's checkout isn't $sha"
    tar -xzf solc.tgz -C repo/contracts
    (cd repo && source scripts/solc.sh && echo "$SOLC_SHA256  $SOLC" | sha256sum -c --quiet) || die "solc's SHA-256"
    docker load -q -i images.tar >/dev/null
    python3 - images.json <<'PY'
import json, subprocess, sys
doc = json.load(open(sys.argv[1]))
for name, ref in doc["images"].items():
    got = subprocess.run(["docker", "image", "inspect", "-f", "{{.Id}}", ref], capture_output=True, text=True).stdout.strip()
    if got != doc["ids"][name]:
        sys.exit(f"rc-remote: image {name} ({ref}) is {got or 'missing'}, not {doc['ids'][name]}")
    print(f"rc-remote: {name} {ref} = {got}")
PY
    rm -f images.tar
    echo "rc-remote: provisioned $sha"
    ;;
  start)
    sha=${2:-} ext=${3:-} image=${4:-} bind=${5:-} wait=${6:-1800}
    sha_ok "$sha"
    [[ "$ext" =~ ^0x[0-9a-fA-F]{40}$ ]] || die "not an address: '$ext'"
    [[ "$image" =~ ^0x[0-9a-f]{64}$ ]] || die "not an image digest: '$image'"
    [[ "$bind" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "not an IPv4 address: '$bind'"
    [[ "$wait" =~ ^[0-9]{1,6}$ ]] || die "not a number of seconds: '$wait'"
    [[ -d "$WORK/repo/.git" ]] || die "not provisioned"
    mkdir -p "$LOGS"
    rm -f "$LOGS/ready.json" "$LOGS/external.json"
    systemctl reset-failed pof-rc-external 2>/dev/null || true
    systemd-run --unit pof-rc-external --property WorkingDirectory="$WORK/repo" \
      --setenv=HOME=/root --setenv=POF_EXT_MODE=aws --setenv=POF_EXT_BIND="$bind" --setenv=POF_V3_EXTERNAL="$ext" \
      --setenv=POF_EXT_IMAGE="$image" --setenv=POF_EXT_PROOF=tee --setenv=POF_EXT_TEE=amd-sev-snp \
      --setenv=POF_V3_EXTERNAL_WAIT="$wait" --setenv=POF_RADICLE_IMAGE_LOADED=1 --setenv=DEVNET_V3_WINDOWS=production \
      bash -c "scripts/integration.sh --release-candidate $sha --external --logs $LOGS >$LOGS/run.log 2>&1"
    echo "rc-remote: started pof-rc-external for $sha"
    ;;
  status)
    python3 - "$LOGS" <<'PY'
import json, pathlib, subprocess, sys
logs = pathlib.Path(sys.argv[1])
def read(name):
    try:
        return json.loads((logs / name).read_text())
    except (OSError, ValueError):
        return None
active = subprocess.run(["systemctl", "is-active", "pof-rc-external"], capture_output=True, text=True).stdout.strip()
tail = []
for name in ("run.log", "external.log"):
    p = logs / name
    if p.is_file():
        tail += [f"{name}: {x[:200]}" for x in p.read_text(errors="replace").splitlines()[-8:]]
print("@status " + json.dumps({"active": active, "ready": read("ready.json"), "result": read("external.json"),
                               "tail": tail}))
PY
    ;;
  stop-run)
    systemctl stop pof-rc-external 2>/dev/null || true
    echo "rc-remote: stopped"
    ;;
  *) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
