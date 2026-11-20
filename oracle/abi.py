"""The Solidity ABI, as much of it as pofctl and the v2 node need: function selectors, encoding of calls (uints,
addresses, bytes32, bool, bytes, dynamic and fixed-size arrays and tuples, nested), and decoding of what the contracts return.
Standard library plus the node's vendored keccak (oracle/crypto.py). pofctl uses it as pofctl.abi."""

from __future__ import annotations

import functools

from .crypto import keccak256

WORD = 32


@functools.lru_cache(maxsize=1024)
def selector(signature: str) -> bytes:
    """The first 4 bytes of keccak256("name(type,...)"). Cached: the vendored Keccak is pure Python, and a node asks for
    the same few dozen selectors on every pass."""
    return keccak256(signature.encode())[:4]


def split_types(inner: str) -> list:
    """'uint256,(address,uint256)[],bytes32' -> ['uint256', '(address,uint256)[]', 'bytes32']."""
    out, depth, cur = [], 0, ""
    for ch in inner:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += ch == "("
        depth -= ch == ")"
        cur += ch
    if cur:
        out.append(cur)
    return out


def _components(t: str) -> list:
    return split_types(t[1:-1])


def _fixed(t: str):
    """('uint256', 4) for 'uint256[4]' (a fixed-size array: v3's price tables); None for anything else."""
    if t.endswith("]") and not t.endswith("[]"):
        inner, _, n = t[:-1].rpartition("[")
        if n.isdigit():
            return inner, int(n)
    return None


def is_dynamic(t: str) -> bool:
    if t in ("bytes", "string") or t.endswith("[]"):
        return True
    if _fixed(t):
        return is_dynamic(_fixed(t)[0])
    if t.startswith("("):
        return any(is_dynamic(c) for c in _components(t))
    return False


def _uint(value: int) -> bytes:
    if value < 0:
        raise ValueError("unsigned values only")
    return int(value).to_bytes(WORD, "big")


def _static(t: str, value) -> bytes:
    if t.startswith("uint"):
        return _uint(int(value))
    if t == "address":
        raw = bytes.fromhex(value[2:] if value.startswith("0x") else value)
        if len(raw) != 20:
            raise ValueError(f"not an address: {value}")
        return raw.rjust(WORD, b"\0")
    if t == "bool":
        return _uint(1 if value else 0)
    if t == "bytes32":
        raw = value if isinstance(value, bytes) else bytes.fromhex(value[2:] if value.startswith("0x") else value)
        if len(raw) != WORD:
            raise ValueError("bytes32 needs 32 bytes")
        return raw
    if t.startswith("bytes") and t[5:].isdigit() and 1 <= int(t[5:]) <= 32:  # bytesN: left-aligned, as Solidity
        n = int(t[5:])
        raw = value if isinstance(value, bytes) else bytes.fromhex(value[2:] if value.startswith("0x") else value)
        if len(raw) != n:
            raise ValueError(f"{t} needs {n} bytes")
        return raw.ljust(WORD, b"\0")
    raise ValueError(f"unsupported type {t}")


def _pad(raw: bytes) -> bytes:
    return raw + b"\0" * (-len(raw) % WORD)


def encode_one(t: str, value) -> bytes:
    """One value's encoding as it sits in a tail (dynamic) or in place (static)."""
    if t.endswith("[]"):
        inner = t[:-2]
        return _uint(len(value)) + encode([inner] * len(value), list(value))
    if _fixed(t):
        inner, n = _fixed(t)
        if len(value) != n:
            raise ValueError(f"{t} needs {n} values")
        return encode([inner] * n, list(value))
    if t.startswith("("):
        return encode(_components(t), list(value))
    if t in ("bytes", "string"):
        raw = value.encode() if isinstance(value, str) and t == "string" else value
        if isinstance(raw, str):
            raw = bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
        return _uint(len(raw)) + _pad(raw)
    return _static(t, value)


def encode(types: list, values: list) -> bytes:
    """abi.encode(values...) for the given types (heads, then tails)."""
    if len(types) != len(values):
        raise ValueError("as many values as types")
    heads, tails = [], []
    head_size = sum(WORD if is_dynamic(t) else len(encode_one(t, v)) for t, v in zip(types, values))
    offset = head_size
    for t, v in zip(types, values):
        if is_dynamic(t):
            tail = encode_one(t, v)
            heads.append(_uint(offset))
            tails.append(tail)
            offset += len(tail)
        else:
            heads.append(encode_one(t, v))
    return b"".join(heads) + b"".join(tails)


def call_data(signature: str, *values) -> bytes:
    """selector || abi.encode(args) for 'name(type,...)'."""
    name, args = signature.split("(", 1)
    return selector(signature) + encode(split_types(args[:-1]), list(values))


# ---------- decoding ----------

def _word(data: bytes, at: int) -> bytes:
    if at + WORD > len(data):
        raise ValueError("the return data is too short")
    return data[at:at + WORD]


def _decode_one(t: str, data: bytes, at: int):
    """The value of type t whose head sits at `at` (for dynamic types, the head is an offset from the start)."""
    if is_dynamic(t):
        start = int.from_bytes(_word(data, at), "big")
        return _decode_tail(t, data, start)
    if _fixed(t):
        return decode([_fixed(t)[0]] * _fixed(t)[1], data[at:])
    if t.startswith("("):
        return decode(_components(t), data[at:])
    raw = _word(data, at)
    if t.startswith("uint"):
        return int.from_bytes(raw, "big")
    if t == "address":
        return "0x" + raw[12:].hex()
    if t == "bool":
        return raw[-1] == 1
    if t == "bytes32":
        return "0x" + raw.hex()
    raise ValueError(f"unsupported type {t}")


def _decode_tail(t: str, data: bytes, start: int):
    if t.endswith("[]"):
        n = int.from_bytes(_word(data, start), "big")
        return decode([t[:-2]] * n, data[start + WORD:])
    if t in ("bytes", "string"):
        n = int.from_bytes(_word(data, start), "big")
        raw = data[start + WORD:start + WORD + n]
        return raw.decode() if t == "string" else "0x" + raw.hex()
    if _fixed(t):
        return decode([_fixed(t)[0]] * _fixed(t)[1], data[start:])
    if t.startswith("("):
        return decode(_components(t), data[start:])
    raise ValueError(f"unsupported type {t}")


def _static_size(t: str) -> int:
    if is_dynamic(t):
        return WORD
    if _fixed(t):
        return _fixed(t)[1] * _static_size(_fixed(t)[0])
    if t.startswith("("):
        return sum(_static_size(c) for c in _components(t))
    return WORD


def decode(types: list, data: bytes) -> list:
    """abi.decode(data, (types...))."""
    out, at = [], 0
    for t in types:
        out.append(_decode_one(t, data, at))
        at += _static_size(t)
    return out


def hexdata(raw: str) -> bytes:
    return bytes.fromhex(raw[2:] if raw.startswith("0x") else raw)
