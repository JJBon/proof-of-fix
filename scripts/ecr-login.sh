# Sourced by the image scripts (exchange-image.sh, seats-image.sh): log in to a private ECR registry with a throwaway
# Docker config (proof-of-fix#213).
#
# Why: Docker Desktop on Windows/WSL keeps logins in the Windows Credential Manager (`"credsStore": "desktop.exe"` in
# ~/.docker/config.json), and an ECR token is longer than that store accepts ("The stub received bad data."). A config
# of our own with no credential store takes it, and keeps the 12-hour token out of ~/.docker: it's in the caller's
# temporary directory, removed when the script exits. The builder (buildx), contexts and CLI plugins are linked from
# the usual config, so builds and pushes behave as before.
#
#   ecr_login <region> <registry> <directory removed on exit>

ecr_login() {
  local region=$1 registry=$2 dir=$3 base=${DOCKER_CONFIG:-$HOME/.docker} d err
  export DOCKER_CONFIG="$dir/docker-config"
  mkdir -p "$DOCKER_CONFIG"
  chmod 700 "$DOCKER_CONFIG"
  printf '{}\n' >"$DOCKER_CONFIG/config.json"
  for d in buildx contexts cli-plugins; do
    [[ -e "$base/$d" && ! -e "$DOCKER_CONFIG/$d" ]] && ln -s "$base/$d" "$DOCKER_CONFIG/$d"
  done
  # The token goes through a pipe only: never an argument. Docker's warning that the login is stored unencrypted is
  # expected here (a private, temporary file), so it's shown only if the login fails.
  if ! err=$(aws ecr get-login-password --region "$region" |
    docker login --username AWS --password-stdin "$registry" 2>&1 >/dev/null); then
    printf '%s\n' "$err" >&2
    echo "ecr-login: docker login to $registry failed" >&2
    return 1
  fi
}
