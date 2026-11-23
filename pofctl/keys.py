"""Where each role's key comes from, as scripts/devnet-keys.sh defines it (proof-of-fix#93):
- `openbao` (the default): secret/proof-of-fix/devnet/<role>, field `key`, read with the bao CLI (sign in first);
- `insecure-local`: anvil's public test mnemonic, one index per role in devnet-keys.sh's order. For tests and
  throwaway devnets only, and only when chosen explicitly (DEVNET_KEYS=insecure-local, or the config);
- `env`: POFCTL_KEY_<ROLE> (e.g. POFCTL_KEY_SOLVER_A), for a key that lives elsewhere.
Whatever the source, a role whose POFCTL_KEY_<ROLE> is set takes that key: an engineer's own validator key (say
POFCTL_KEY_ENGINEER, used with --as engineer) beside the devnet's roles.
Keys are devnet keys (rule 1): never use one on a public chain. Nothing here prints a key."""

from __future__ import annotations

import hashlib
import hmac
import os
import subprocess

from oracle.crypto import N, address  # noqa: F401  (address re-exported for callers)

# devnet-keys.sh's roles, in its order (tests/test_pofctl.py checks they match the script).
ORACLES = 5
ROLES = ["deployer", "bot", "reporter", "funder", "solver-a", "solver-b", "infrastructure", "insurance", "founder"] + [
    f"oracle-{i}" for i in range(ORACLES)] + ["joiner-0", "joiner-1"]  # the joiners: devnet keys for vacant v2 seats
ROLES += ["bot-service"]  # the bot as a service's own key (#210), appended so every role above keeps its index
MNEMONIC = "test test test test test test test test test test test junk"
MOUNT, PREFIX = "secret", "proof-of-fix/devnet"


class KeyError_(Exception):
    """A role's key couldn't be read (no OpenBao session, no such role)."""


# ---------- BIP-39 / BIP-32 (m/44'/60'/0'/0/i, as anvil and cast derive the mnemonic's keys) ----------

def _seed(mnemonic: str, passphrase: str = "") -> bytes:
    return hashlib.pbkdf2_hmac("sha512", mnemonic.encode(), ("mnemonic" + passphrase).encode(), 2048)


def _compressed(secret: int) -> bytes:
    from ecdsa import SECP256k1, SigningKey  # vendored, on the path through oracle.crypto
    return SigningKey.from_secret_exponent(secret, curve=SECP256k1).get_verifying_key().to_string("compressed")


def derive(mnemonic: str, index: int) -> int:
    """The private key at m/44'/60'/0'/0/index."""
    i = hmac.new(b"Bitcoin seed", _seed(mnemonic), hashlib.sha512).digest()
    key, chain = int.from_bytes(i[:32], "big"), i[32:]
    for level, hardened in ((44, True), (60, True), (0, True), (0, False), (index, False)):
        n = level + (0x80000000 if hardened else 0)
        data = (b"\0" + key.to_bytes(32, "big") if hardened else _compressed(key)) + n.to_bytes(4, "big")
        i = hmac.new(chain, data, hashlib.sha512).digest()
        key, chain = (int.from_bytes(i[:32], "big") + key) % N, i[32:]
    return key


# ---------- sources ----------

def source(configured: str | None = None) -> str:
    """The key source: DEVNET_KEYS wins (as for the shell scripts), then the config, then OpenBao."""
    return os.environ.get("DEVNET_KEYS") or configured or "openbao"


def env_name(role: str) -> str:
    return "POFCTL_KEY_" + role.upper().replace("-", "_")


def key(role: str, src: str) -> int:
    """The role's private key, as an integer."""
    override = os.environ.get(env_name(role))
    if override and src != "env":
        return int(override, 16)
    if src == "insecure-local":
        if role not in ROLES:
            raise KeyError_(f"unknown role {role} (known: {', '.join(ROLES)})")
        return derive(MNEMONIC, ROLES.index(role))
    if src == "env":
        name = env_name(role)
        raw = os.environ.get(name)
        if not raw:
            raise KeyError_(f"{name} isn't set")
        return int(raw, 16)
    if src == "openbao":
        env = {**os.environ, "BAO_ADDR": os.environ.get("BAO_ADDR", "https://vault.clouddemosaws.com")}
        try:
            out = subprocess.run(["bao", "kv", "get", f"-mount={MOUNT}", "-field=key", f"{PREFIX}/{role}"],
                                 capture_output=True, text=True, timeout=30, env=env)
        except FileNotFoundError as e:
            raise KeyError_("the bao CLI isn't installed") from e
        if out.returncode:
            raise KeyError_(f"no devnet key for {role} in OpenBao ({MOUNT}/{PREFIX}/{role}): sign in with "
                            f"`bao login -method=oidc role=admin -no-print`, or run scripts/devnet-keys.sh init")
        return int(out.stdout.strip(), 16)
    raise KeyError_(f"unknown key source {src} (openbao, insecure-local or env)")
