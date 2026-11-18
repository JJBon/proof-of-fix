"""The bot's GitHub adapter (proof-of-fix#104, #82 B4): issues, labels, comments and pull requests of one repository,
through GitHub's REST API, with the same interface as bot/forge.py's ForgejoRepo.

Credentials: a fine-grained personal access token (repository access to the one demo repository; Issues and Pull
requests read, plus Issues write only if the bot comments), or a GitHub App installation token. Either is passed in
from the environment (GITHUB_TOKEN or GITHUB_APP_TOKEN) and only sent to the configured API.

Resilience: transient failures (connection errors, 5xx) are retried with backoff; rate limits are honoured
(429 or 403 with Retry-After, or with x-ratelimit-remaining: 0 until x-ratelimit-reset), up to a cap, after which the
call fails with a clear error. Lists follow the Link header's `next` pages."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from .forge import RepoHost, _labels, pull_of

API_VERSION = "2022-11-28"
NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubError(Exception):
    def __init__(self, message: str, status: int = 0) -> None:
        super().__init__(message)
        self.status = status  # the HTTP status, when the API answered with one


class GitHubRepo(RepoHost):
    def __init__(self, full_name: str, token: str = "", api: str = "https://api.github.com", retries: int = 4,
                 max_wait: float = 120, sleep=time.sleep, now=time.time) -> None:
        if full_name.count("/") != 1:
            raise ValueError(f"expected owner/name, got {full_name!r}")
        self.full_name, self.token, self.api = full_name, token, api.rstrip("/")
        self.retries, self.max_wait, self._sleep, self._now = retries, max_wait, sleep, now

    # ---------- HTTP ----------

    def _request(self, method: str, url: str, body: dict | None = None):
        """One API call with retries; returns (parsed JSON, response headers)."""
        data = None if body is None else json.dumps(body).encode()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
                   "User-Agent": "proof-of-fix-bot"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if data is not None:
            headers["Content-Type"] = "application/json"
        last = ""
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (the configured API)
                    raw = r.read()
                    return (json.loads(raw) if raw else None), dict(r.headers)
            except urllib.error.HTTPError as e:
                wait = self._rate_limit_wait(e.code, e.headers)
                if wait is not None:
                    if wait > self.max_wait or attempt == self.retries:
                        raise GitHubError(f"GitHub rate limit on {method} {url}: retry in {wait:.0f}s", e.code) from e
                    self._sleep(wait)
                    continue
                if e.code >= 500 and attempt < self.retries:
                    last = f"HTTP {e.code}"
                    self._sleep(min(2 ** attempt, self.max_wait))
                    continue
                detail = e.read().decode(errors="replace")[:300]
                raise GitHubError(f"{method} {url}: HTTP {e.code}: {detail}", e.code) from e
            except urllib.error.URLError as e:
                last = str(e.reason)
                if attempt < self.retries:
                    self._sleep(min(2 ** attempt, self.max_wait))
                    continue
        raise GitHubError(f"{method} {url} failed after {self.retries + 1} tries: {last}")

    def _rate_limit_wait(self, code: int, headers) -> float | None:
        """Seconds to wait if this response is a rate limit, else None."""
        if code not in (403, 429):
            return None
        retry_after = headers.get("Retry-After") if headers else None
        if retry_after:
            return float(retry_after)
        if headers and headers.get("x-ratelimit-remaining") == "0":
            reset = float(headers.get("x-ratelimit-reset") or 0)
            return max(reset - self._now(), 0) + 1
        return 60.0 if code == 429 else None  # a secondary limit with no hint; a plain 403 is a permission error

    def _get_all(self, path: str) -> list:
        url, out = f"{self.api}{path}", []
        while url:
            page, headers = self._request("GET", url)
            out.extend(page or [])
            m = NEXT.search((headers or {}).get("Link") or (headers or {}).get("link") or "")
            url = m.group(1) if m else ""
        return out

    def _get(self, path: str):
        return self._request("GET", f"{self.api}{path}")[0]

    # ---------- the interface ----------

    @staticmethod
    def _issue(raw: dict) -> dict:
        return {"number": raw["number"], "title": raw.get("title", ""), "body": raw.get("body") or "",
                "state": raw.get("state", ""), "labels": _labels(raw.get("labels")),
                "user": (raw.get("user") or {}).get("login", ""), "created_at": raw.get("created_at") or ""}

    def issues(self, state: str = "open", label: str | None = None) -> list:
        query = f"?state={state}&per_page=100" + (f"&labels={label}" if label else "")
        # GitHub's issues endpoint also returns pull requests (they carry a "pull_request" key): leave them out.
        return [self._issue(i) for i in self._get_all(f"/repos/{self.full_name}/issues{query}")
                if "pull_request" not in i]

    def issue(self, number: int) -> dict:
        return self._issue(self._get(f"/repos/{self.full_name}/issues/{number}"))

    def comments(self, number: int) -> list:
        return [{"id": c["id"], "body": c.get("body") or "", "user": (c.get("user") or {}).get("login", "")}
                for c in self._get_all(f"/repos/{self.full_name}/issues/{number}/comments?per_page=100")]

    def comment(self, number: int, body: str) -> dict:
        c, _ = self._request("POST", f"{self.api}/repos/{self.full_name}/issues/{number}/comments", {"body": body})
        return {"id": c["id"], "body": c.get("body") or "", "user": (c.get("user") or {}).get("login", "")}

    def close(self, number: int) -> dict:
        raw, _ = self._request("PATCH", f"{self.api}/repos/{self.full_name}/issues/{number}",
                               {"state": "closed", "state_reason": "completed"})
        return self._issue(raw)

    def pull(self, number: int) -> dict:
        return pull_of(self._get(f"/repos/{self.full_name}/pulls/{number}"))

    def pulls(self, state: str = "all") -> list:
        # GitHub's list leaves out `merged`; `merged_at` says it.
        return [{**pull_of(p), "merged": bool(p.get("merged") or p.get("merged_at"))}
                for p in self._get_all(f"/repos/{self.full_name}/pulls?state={state}&per_page=100")]
