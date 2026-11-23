"""A role seat's node on the AWS devnet's seats host (proof-of-fix#152, platform#219): `python3 -m oracle seat <command>`
in the node's image, e.g. `seat run --until-idle 600` or `seat info`.

It sets up what `scripts/devnet-seats.sh` sets up for each seat on the owner's laptop, then runs the node's own command
in this process:
- the secrets, each read once, from the environment or else from a file in SEAT_SECRETS (default /run/secrets: the
  host's memory-backed files, mounted read-only into this seat's container alone):
      ORACLE_PRIVATE_KEY   or the file `key`         this seat's signing key
      ORACLE_RPC_TOKEN     or the file `rpc-auth`    the devnet's API credential, "<handle>:<key>" (HTTP Basic)
      FORGEJO_TOKEN        or the file `repo-token`  a READ-ONLY token for the target repository
  They go into this process's environment only (where the node reads them): never on a command line, in the
  container's configuration (`docker inspect`) or in the output. The sandbox gets none of them (oracle/sandbox.py
  passes it one variable).
- the devnet's settings, as devnet-seats.sh's (each may be set in the environment instead):
      ORACLE_KEYS=env  ORACLE_VERSION=2  ORACLE_RPC_API_KEY_HEADER=Basic  ORACLE_EXCHANGE_TRANSPORT=http
      ORACLE_EXCHANGE_URL=<ORACLE_RPC>/exchange  ORACLE_REPO=clouddemos-internal/pof-sandbox
      FORGEJO_USER=pof-validator-bot  ORACLE_JUDGE=fake  ORACLE_ROUND_TIMEOUT=900 (the relay's seal window)
      ORACLE_POLL=5  ORACLE_SANDBOX=api (the host's Docker socket, DOCKER_SOCKET: the fixes' tests in the pinned
      sandbox image, no network; the image has no Docker CLI)
- its working directory, SEAT_WORK (required for `run`), mounted at the same path inside and outside the container,
  since the sandbox's bind mount of a checkout is resolved by the host's Docker: ORACLE_SRC_ROOT=<SEAT_WORK>/src,
  ORACLE_RECEIPTS=<SEAT_WORK>/receipts, and ORACLE_REPOS=<SEAT_WORK>/repos.json written from ORACLE_REPO and
  SEAT_FORGE_URL (default https://git.clouddemosaws.com) unless ORACLE_REPOS names one.

It refuses, before any chain call: ORACLE_JUDGE other than fake (a real model needs a later change, proof-of-fix#160),
an RPC or relay URL with a credential in it or over plain HTTP (SEAT_ALLOW_HTTP=1 is for a local test), and a missing or
malformed secret, naming it without its value. Exit codes are the node's (75: the chain stayed away; the host's run
treats that seat as done). Rule 1 holds: the node's environment key refuses any chain but the devnet's.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

SECRETS = (("ORACLE_PRIVATE_KEY", "key"), ("ORACLE_RPC_TOKEN", "rpc-auth"), ("FORGEJO_TOKEN", "repo-token"))
DEFAULTS = {
    "ORACLE_KEYS": "env", "ORACLE_VERSION": "2", "ORACLE_RPC_API_KEY_HEADER": "Basic",
    "ORACLE_EXCHANGE_TRANSPORT": "http", "ORACLE_REPO": "clouddemos-internal/pof-sandbox",
    "FORGEJO_USER": "pof-validator-bot", "ORACLE_JUDGE": "fake", "ORACLE_ROUND_TIMEOUT": "900", "ORACLE_POLL": "5",
    "ORACLE_SANDBOX": "api", "PYTHONDONTWRITEBYTECODE": "1",
}
DEFAULT_FORGE = "https://git.clouddemosaws.com"
PLAIN_URL = re.compile(r"^https?://[A-Za-z0-9._-]+(:[0-9]+)?(/[A-Za-z0-9._/-]*)?$")
CREDENTIAL = re.compile(r"^[^:\s]+:\S+$")


class Refused(Exception):
    pass


def read_secrets(env: dict, secrets_dir: Path) -> None:
    """Each secret from the environment, else from its file: once, into `env`. Errors name the secret, never its value."""
    for var, name in SECRETS:
        value = env.get(var, "")
        if not value.strip():
            path = secrets_dir / name
            try:
                value = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                raise Refused(f"no {var}: set it or mount the file {path}") from None
            except OSError as e:
                raise Refused(f"can't read {path} ({e.strerror})") from None
        value = value.strip()  # a paste or `echo` can bring a line ending along
        if not value:
            raise Refused(f"{var} is empty")
        env[var] = value
    if not CREDENTIAL.match(env["ORACLE_RPC_TOKEN"]):
        raise Refused("ORACLE_RPC_TOKEN must look like <handle>:<key> (not printed)")


def configure(env: dict, command: str) -> None:
    """devnet-seats.sh's settings for one seat, in `env` (os.environ in use). Raises Refused."""
    for k, v in DEFAULTS.items():
        env.setdefault(k, v)
    if env["ORACLE_JUDGE"] != "fake":
        raise Refused(f"ORACLE_JUDGE={env['ORACLE_JUDGE']!r}: the seats run the fake judge only; a real model needs a "
                      "later change (proof-of-fix#160)")
    rpc = env.get("ORACLE_RPC", "")
    if not rpc:
        raise Refused("set ORACLE_RPC (the devnet's URL, no credential in it)")
    env.setdefault("ORACLE_EXCHANGE_URL", rpc.rstrip("/") + "/exchange")
    allow_http = env.get("SEAT_ALLOW_HTTP") == "1"
    for var in ("ORACLE_RPC", "ORACLE_EXCHANGE_URL"):
        if not PLAIN_URL.match(env[var]):
            raise Refused(f"{var} must be a plain URL, without a credential in it")
        if env[var].startswith("http://") and not allow_http:
            raise Refused(f"{var} is plain HTTP, which would send the key in the clear: use https://")
    if not env.get("ORACLE_RACE"):
        raise Refused("set ORACLE_RACE (the deployment record's race)")
    read_secrets(env, Path(env.get("SEAT_SECRETS") or "/run/secrets"))
    if command != "run":
        return
    work = env.get("SEAT_WORK", "")
    if not work or not work.startswith("/"):
        raise Refused("set SEAT_WORK: the seat's working directory, an absolute path mounted at the same path inside and "
                      "outside the container (the sandbox's checkouts)")
    root = Path(work)
    env.setdefault("ORACLE_SRC_ROOT", str(root / "src"))
    env.setdefault("ORACLE_RECEIPTS", str(root / "receipts"))
    Path(env["ORACLE_SRC_ROOT"]).mkdir(parents=True, exist_ok=True)
    if not env.get("ORACLE_REPOS"):
        forge = env.get("SEAT_FORGE_URL") or DEFAULT_FORGE
        if not PLAIN_URL.match(forge):
            raise Refused("SEAT_FORGE_URL must be a plain URL")
        repos = root / "repos.json"  # no credential in it: the token stays in the environment (bot/forge.py)
        repos.write_text(json.dumps({"repos": {env["ORACLE_REPO"]: {"host": "forgejo", "api": forge}}}) + "\n",
                         encoding="utf-8")
        env["ORACLE_REPOS"] = str(repos)


def main(argv: list, node_main) -> int:
    """argv: ["seat", <the node's command>, ...]; node_main: oracle/__main__.py's main."""
    command = argv[1] if len(argv) > 1 else "info"
    try:
        configure(os.environ, command)
    except Refused as e:
        print(f"oracle seat: {e}", file=sys.stderr, flush=True)
        return 2
    return node_main(["oracle", command, *argv[2:]])
