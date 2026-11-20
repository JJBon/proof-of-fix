"""A public chain's key (proof-of-fix#251 task 4.4, design L12): an Ethereum keystore file (Web3 Secret Storage, version
3, as `cast wallet new`, geth and most wallets write it), decrypted with a password asked for at the terminal.

- **The only way pofctl signs on a public chain.** Devnet keys (OpenBao's devnet path, anvil's public mnemonic,
  POFCTL_KEY_<ROLE>) are refused on any chain but the local ones (31337 and 7193); see pofctl/cli.py.
- **The key is never printed, logged or written.** It is decrypted into an integer that only the signing wallet holds;
  no message here or in the CLI formats it, and a failure names the file and the reason, never a byte of the key.
- **The password** is prompted for (getpass: no echo, never on the command line). For an unattended run (a test, a
  script), POFCTL_KEYSTORE_PASSWORD_FILE names a file holding it; never put the password itself in the environment
  or the config.
- **Standard library only:** scrypt and PBKDF2 come from hashlib; AES-128-CTR, which the format uses and the standard
  library lacks, is the small AES-128 encryption below (CTR only ever encrypts counter blocks), checked against FIPS-197's
  vector and the format's own test vectors in tests/test_pofctl_v3.py.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import uuid
from pathlib import Path

from oracle.crypto import N, address, keccak256

PASSWORD_FILE = "POFCTL_KEYSTORE_PASSWORD_FILE"
SCRYPT_MAXMEM = 1 << 30  # n = 2**18, r = 8 (the usual "standard" parameters) needs 256 MiB


class KeystoreError(Exception):
    """The keystore can't be read or opened: its message never contains the key."""


# ---------- AES-128 (encryption only: CTR mode needs nothing else) ----------

def _sbox() -> list:
    sbox, p, q = [0] * 256, 1, 1
    while True:  # the multiplicative inverse by walking 3 and its inverse, then the affine map (FIPS-197 5.1.1)
        p = p ^ ((p << 1) & 0xFF) ^ (0x1B if p & 0x80 else 0)
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09
        x = q ^ ((q << 1 | q >> 7) & 0xFF) ^ ((q << 2 | q >> 6) & 0xFF) ^ ((q << 3 | q >> 5) & 0xFF) \
            ^ ((q << 4 | q >> 4) & 0xFF)
        sbox[p] = x ^ 0x63
        if p == 1:
            break
    sbox[0] = 0x63
    return sbox


SBOX = _sbox()


def _xtime(a: int) -> int:
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _expand(key: bytes) -> list:
    """AES-128's 11 round keys, as 16-byte lists."""
    if len(key) != 16:
        raise KeystoreError("AES-128 takes a 16-byte key")
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = _xtime(rcon)
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[r * 4:r * 4 + 4], []) for r in range(11)]


def aes128_block(round_keys: list, block: bytes) -> bytes:
    """One 16-byte block encrypted (FIPS-197 5.1): the state is column-major, s[c * 4 + r]."""
    s = [b ^ k for b, k in zip(block, round_keys[0])]
    for rnd in range(1, 11):
        s = [SBOX[b] for b in s]
        s = [s[((c + r) % 4) * 4 + r] for c in range(4) for r in range(4)]  # ShiftRows
        if rnd != 10:
            out = []
            for c in range(4):  # MixColumns
                a = s[c * 4:c * 4 + 4]
                t = a[0] ^ a[1] ^ a[2] ^ a[3]
                out += [a[r] ^ t ^ _xtime(a[r] ^ a[(r + 1) % 4]) for r in range(4)]
            s = out
        s = [b ^ k for b, k in zip(s, round_keys[rnd])]
    return bytes(s)


def aes128_ctr(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128-CTR with a 128-bit big-endian counter starting at `iv` (the keystore's cipher): its own inverse."""
    rk, counter, out = _expand(key), int.from_bytes(iv, "big"), bytearray()
    for i in range(0, len(data), 16):
        stream = aes128_block(rk, (counter % (1 << 128)).to_bytes(16, "big"))
        out += bytes(a ^ b for a, b in zip(data[i:i + 16], stream))
        counter += 1
    return bytes(out)


# ---------- the keystore ----------

def _derive(crypto: dict, password: str) -> bytes:
    kdf, p = crypto.get("kdf"), crypto.get("kdfparams") or {}
    try:
        salt, dklen = bytes.fromhex(p["salt"]), int(p["dklen"])
        if kdf == "scrypt":
            n, r, par = int(p["n"]), int(p["r"]), int(p["p"])
            return hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=par, dklen=dklen,
                                  maxmem=max(SCRYPT_MAXMEM, 129 * r * n * par))
        if kdf == "pbkdf2":
            if p.get("prf", "hmac-sha256") != "hmac-sha256":
                raise KeystoreError(f"unsupported PBKDF2 function {p.get('prf')!r} (hmac-sha256 only)")
            return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(p["c"]), dklen)
    except (KeyError, ValueError, TypeError) as e:
        raise KeystoreError(f"the keystore's {kdf} parameters are malformed ({type(e).__name__})") from None
    raise KeystoreError(f"unsupported key derivation {kdf!r} (scrypt or pbkdf2)")


def decrypt(doc: dict, password: str) -> int:
    """The private key in a version 3 keystore, as an integer. Raises KeystoreError on a wrong password (its MAC) or
    a malformed file, saying which, without the key."""
    if not isinstance(doc, dict) or int(doc.get("version", 0)) != 3:
        raise KeystoreError("not a version 3 keystore (Web3 Secret Storage)")
    c = doc.get("crypto") or doc.get("Crypto") or {}
    if c.get("cipher") != "aes-128-ctr":
        raise KeystoreError(f"unsupported cipher {c.get('cipher')!r} (aes-128-ctr only)")
    dk = _derive(c, password)
    try:
        ciphertext, iv, mac = bytes.fromhex(c["ciphertext"]), bytes.fromhex(c["cipherparams"]["iv"]), \
            bytes.fromhex(c["mac"])
    except (KeyError, ValueError, TypeError) as e:
        raise KeystoreError(f"the keystore's cipher fields are malformed ({type(e).__name__})") from None
    if len(dk) < 32 or not hmac.compare_digest(keccak256(dk[16:32] + ciphertext), mac):
        raise KeystoreError("wrong password (the keystore's MAC doesn't match)")
    secret = int.from_bytes(aes128_ctr(dk[:16], iv, ciphertext), "big")
    if not 0 < secret < N:
        raise KeystoreError("the keystore holds no valid secp256k1 key")
    want = doc.get("address")
    if want and address(secret)[2:].lower() != str(want).lower().removeprefix("0x"):
        raise KeystoreError("the key doesn't match the keystore's address")
    return secret


def encrypt(secret: int, password: str, kdf: str = "scrypt", n: int = 1 << 18, r: int = 8, p: int = 1,
            c: int = 262_144) -> dict:
    """A version 3 keystore for `secret` (what `cast wallet new` writes): tests and the end-to-end run make theirs with
    it, with lighter parameters."""
    salt, iv = secrets.token_bytes(32), secrets.token_bytes(16)
    if kdf == "scrypt":
        params = {"dklen": 32, "n": n, "r": r, "p": p, "salt": salt.hex()}
    elif kdf == "pbkdf2":
        params = {"dklen": 32, "c": c, "prf": "hmac-sha256", "salt": salt.hex()}
    else:
        raise KeystoreError(f"unsupported key derivation {kdf!r}")
    dk = _derive({"kdf": kdf, "kdfparams": params}, password)
    ciphertext = aes128_ctr(dk[:16], iv, secret.to_bytes(32, "big"))
    return {"version": 3, "id": str(uuid.uuid4()), "address": address(secret)[2:].lower(),
            "crypto": {"cipher": "aes-128-ctr", "cipherparams": {"iv": iv.hex()}, "ciphertext": ciphertext.hex(),
                       "kdf": kdf, "kdfparams": params, "mac": keccak256(dk[16:32] + ciphertext).hex()}}


def password_for(path: str) -> str:
    """The keystore's password: from the file POFCTL_KEYSTORE_PASSWORD_FILE names (unattended runs), else asked at the
    terminal without echo."""
    pf = os.environ.get(PASSWORD_FILE)
    if pf:
        try:
            return Path(pf).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError as e:
            raise KeystoreError(f"{PASSWORD_FILE}: can't read {pf} ({e.strerror})") from None
    try:
        return getpass.getpass(f"password for the keystore {path}: ")
    except (EOFError, KeyboardInterrupt):
        raise KeystoreError("no password given") from None


def load(path: str, password: str | None = None) -> int:
    """The key in the keystore file at `path`; the password is asked for unless given."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as e:
        raise KeystoreError(f"can't read the keystore {path} ({e.strerror})") from None
    except json.JSONDecodeError:
        raise KeystoreError(f"the keystore {path} isn't JSON") from None
    try:
        return decrypt(doc, password_for(path) if password is None else password)
    except KeystoreError as e:
        raise KeystoreError(f"keystore {path}: {e}") from None
