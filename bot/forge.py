"""The bot's view of a repository host, whichever it is (proof-of-fix#104): what the bot and the oracle stand-in read
and write about issues and pull requests, behind one interface, so a repository can live on Forgejo (the local loop)
or GitHub (the engineers' demo). Which host serves which repository is the bot's config (`repos.json`):

    {"repos": {"maintainer/sample": {"host": "forgejo", "api": "http://127.0.0.1:3300"},
               "acme/demo":         {"host": "github"}}}

Issues and pull requests come back in one shape, whatever the host:
    issue:  {"number", "title", "body", "state" ("open"/"closed"), "labels": [names], "user", "created_at" (ISO 8601,
             or "" when the host doesn't say)}
    pull:   {"number", "title", "body", "state", "head_sha", "base_sha", "merged"}
    comment:{"id", "body", "user"}
The local loop (bot/loop.py) still talks to its Forgejo directly; this interface is for code that must serve either."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .forgejo import Forgejo

PAGE, MAX_PAGES = 50, 40  # a list's page, and at most 2,000 items

class RepoHost:
    """A repository on some host: the bot's operations on issues and pull requests."""

    full_name: str

    def issues(self, state: str = "open", label: str | None = None) -> list:
        raise NotImplementedError

    def issue(self, number: int) -> dict:
        raise NotImplementedError

    def comments(self, number: int) -> list:
        raise NotImplementedError

    def comment(self, number: int, body: str) -> dict:
        raise NotImplementedError

    def close(self, number: int) -> dict:
        """Closes an issue (as completed, where the host says so); returns it."""
        raise NotImplementedError

    def pull(self, number: int) -> dict:
        raise NotImplementedError

    def pulls(self, state: str = "all") -> list:
        """The pull requests, newest first (a judge finds the one that claims its submission)."""
        raise NotImplementedError

    def merged(self, number: int) -> bool:
        return bool(self.pull(number)["merged"])


def _labels(raw) -> list:
    return [lab["name"] if isinstance(lab, dict) else str(lab) for lab in raw or []]


class ForgejoRepo(RepoHost):
    """A repository on a Forgejo, through bot/forgejo.py's client (its API is Gitea's)."""

    def __init__(self, client: Forgejo, full_name: str) -> None:
        self.client, self.full_name = client, full_name
        self._base = f"/repos/{full_name}"

    def _issue(self, raw: dict) -> dict:
        return {"number": raw["number"], "title": raw.get("title", ""), "body": raw.get("body") or "",
                "state": raw.get("state", ""), "labels": _labels(raw.get("labels")),
                "user": (raw.get("user") or {}).get("login", ""), "created_at": raw.get("created_at") or ""}

    def issues(self, state: str = "open", label: str | None = None) -> list:
        """Every page of them (50 a page), so an older labelled issue isn't missed (#210's first-claim rule)."""
        query = f"?state={state}&type=issues&limit={PAGE}" + (f"&labels={label}" if label else "")
        out, page = [], 1
        while True:
            got = self.client.api("GET", f"{self._base}/issues{query}&page={page}") or []
            out += [self._issue(i) for i in got]
            if len(got) < PAGE or page >= MAX_PAGES:
                return out
            page += 1

    def issue(self, number: int) -> dict:
        return self._issue(self.client.api("GET", f"{self._base}/issues/{number}"))

    def comments(self, number: int) -> list:
        return [{"id": c["id"], "body": c.get("body") or "", "user": (c.get("user") or {}).get("login", "")}
                for c in self.client.api("GET", f"{self._base}/issues/{number}/comments") or []]

    def comment(self, number: int, body: str) -> dict:
        c = self.client.api("POST", f"{self._base}/issues/{number}/comments", {"body": body})
        return {"id": c["id"], "body": c.get("body") or "", "user": (c.get("user") or {}).get("login", "")}

    def close(self, number: int) -> dict:
        return self._issue(self.client.api("PATCH", f"{self._base}/issues/{number}", {"state": "closed"}))

    def pull(self, number: int) -> dict:
        return pull_of(self.client.api("GET", f"{self._base}/pulls/{number}"))

    def pulls(self, state: str = "all") -> list:
        return [pull_of(p) for p in self.client.api("GET", f"{self._base}/pulls?state={state}&limit=50") or []]


def pull_of(p: dict) -> dict:
    """A pull request in the interface's shape, from GitHub's or Forgejo's (they agree on these fields)."""
    return {"number": p["number"], "title": p.get("title", ""), "body": p.get("body") or "",
            "state": p.get("state", ""), "head_sha": (p.get("head") or {}).get("sha", ""),
            "base_sha": (p.get("base") or {}).get("sha", ""), "merged": bool(p.get("merged"))}


def load_config(path: str | None = None) -> dict:
    """The bot's repository config: --config, then $POF_BOT_REPOS, then ./repos.json; empty if none."""
    p = Path(path or os.environ.get("POF_BOT_REPOS", "repos.json"))
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"repos": {}}


def repo_for(full_name: str, config: dict | None = None, env: dict | None = None) -> RepoHost:
    """The host serving `owner/name`, from the config. GitHub by default (#104's demo repository).
    Credentials come from the environment, never the config:
      GitHub: GITHUB_TOKEN (a fine-grained token) or GITHUB_APP_TOKEN (an app installation's token);
      Forgejo: FORGEJO_TOKEN, with FORGEJO_USER/FORGEJO_PASSWORD for git over HTTP (the local loop's)."""
    env = os.environ if env is None else env
    entry = ((config or {}).get("repos") or {}).get(full_name, {"host": "github"})
    host = entry.get("host", "github")
    if host == "github":
        from .github import GitHubRepo
        return GitHubRepo(full_name, token=env.get("GITHUB_TOKEN") or env.get("GITHUB_APP_TOKEN") or "",
                          api=entry.get("api") or env.get("GITHUB_API_URL") or "https://api.github.com")
    if host == "forgejo":
        client = Forgejo(entry["api"], env.get("FORGEJO_USER", ""), env.get("FORGEJO_PASSWORD", ""),
                         env.get("FORGEJO_TOKEN", ""))
        return ForgejoRepo(client, full_name)
    raise ValueError(f"unknown host {host!r} for {full_name} (github or forgejo)")
