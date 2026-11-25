"""No RPC key in any log line (proof-of-fix#251, v3.1 polish VP20).

A provider's key often sits in the RPC URL's path (Infura's `/v3/<key>`, Alchemy's `/v2/<key>`), so the URL is never
shown whole:

- at the source, `shown_url(url)` is what `Rpc` prints: the scheme and host, and `/…` in place of a path with a
  segment of 8 characters or more (the user info is always dropped);
- at the sink, a `Redactor` loaded with the URL (and any other secret) replaces it, its path and its long path
  segments in every line, tracebacks included, so a library's message that prints the URL is caught too.

The keeper-only node's `Redactor` (oracle/keeper.py, the seed host's build) is the origin of this module.
"""

from __future__ import annotations

import urllib.parse

MIN_SECRET = 8  # a path segment shorter than this is a word ("v3", "rpc"), not a key


def _long_segment(path: str) -> bool:
    return any(len(s) >= MIN_SECRET for s in path.split("/"))


def shown_url(url: str) -> str:
    """The URL as a log line may show it: scheme, host (and port), and `/…` when its path may hold a key."""
    try:
        u = urllib.parse.urlsplit(url)
    except ValueError:
        return "…"
    if not u.scheme or not u.hostname:
        return "…" if _long_segment(url) else url
    try:
        host = u.hostname + (f":{u.port}" if u.port else "")
    except ValueError:  # not a port: a label such as "8545 (through a docker exec pipe)", shown without the user info
        host = u.netloc.rpartition("@")[2]
    if _long_segment(u.path) or u.query:
        return f"{u.scheme}://{host}/…"
    return f"{u.scheme}://{host}{u.path}"


class Redactor:
    """Replaces every loaded secret in a line: a URL by its shown form, a key or a long path segment by `…`."""

    def __init__(self) -> None:
        self.secrets: list = []

    def add(self, secret: str | None) -> None:
        if not secret:
            return
        if "://" in secret:
            u = urllib.parse.urlsplit(secret)
            shown = shown_url(secret)
            parts = [secret, secret.rstrip("/"), u.path.strip("/"), u.query, u.password or "", u.username or ""]
            parts += u.path.split("/")
            for s in parts:
                if s and len(s) >= MIN_SECRET:
                    self.secrets.append((s, shown if s.startswith(("http", "ws")) else "…"))
        elif len(secret) >= MIN_SECRET:
            self.secrets.append((secret, "…"))
        # longest first, so a URL is replaced whole before its path is
        self.secrets = sorted(set(self.secrets), key=lambda x: -len(x[0]))

    def __call__(self, text: str) -> str:
        for s, shown in self.secrets:
            if s in text:
                text = text.replace(s, shown)
        return text


REDACT = Redactor()  # the process's shared redactor: the node, the keeper and pofctl load their RPC URL into it

# What `load_env` loads: the RPC URL (ORACLE_RPC, or ORACLE_RPC_SECRET_ARN's value, which oracle/awssecret.py puts
# there) and the RPC's API key or token, however it's given.
RPC_SECRETS = ("ORACLE_RPC", "ORACLE_RPC_TOKEN", "RPC_API_KEY")


def load_env(env, redactor: Redactor | None = None) -> Redactor:
    """Loads the RPC's URL and key from `env` into `redactor` (default: the shared REDACT); returns it."""
    r = REDACT if redactor is None else redactor
    for name in RPC_SECRETS:
        r.add((env.get(name) or "").strip() or None)
    return r
