"""A minimal client for the loop's local Forgejo (bound to 127.0.0.1 only): its REST API with a token, and git over
HTTP with no credential helper, so nothing from the developer's own git sign-in is used or stored."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from urllib.parse import quote


class Forgejo:
    def __init__(self, base: str, user: str, password: str, token: str) -> None:
        # https to any host (a validator node reading a real Forgejo, #112), plain http only on this machine's
        # loopback (the local loop's throwaway Forgejo), as oracle/fetch.py allows for clone URLs.
        if not (base.startswith("https://") or base.startswith(("http://127.0.0.1:", "http://localhost:"))):
            raise ValueError("a Forgejo must be https, or plain http only on this machine's loopback")
        self.base, self.user, self.password, self.token = base.rstrip("/"), user, password, token

    def api(self, method: str, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(f"{self.base}/api/v1{path}", data=data, method=method,
                                     headers={"Authorization": f"token {self.token}",
                                              "Content-Type": "application/json", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (https, or http on loopback only: checked above)
            raw = r.read()
        return json.loads(raw) if raw else None

    def remote(self, owner: str, repo: str) -> str:
        scheme, host = self.base.split("://", 1)
        return f"{scheme}://{quote(self.user)}:{quote(self.password)}@{host}/{owner}/{repo}.git"


def git(cwd: str, *args: str, name: str = "loop", email: str = "loop@example.invalid") -> str:
    """git with no credential helper or prompt, and a throwaway identity."""
    out = subprocess.run(["git", "-c", "credential.helper=", "-c", f"user.name={name}", "-c", f"user.email={email}",
                          "-c", "init.defaultBranch=main", *args], cwd=cwd, capture_output=True, text=True,
                         timeout=120, env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin", "HOME": cwd})
    if out.returncode:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {out.stderr.strip()}")
    return out.stdout.strip()
