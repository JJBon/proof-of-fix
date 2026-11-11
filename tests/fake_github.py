"""A fake GitHub REST API on 127.0.0.1, for bot/github.py's tests and pofctl's end-to-end run (proof-of-fix#104):
issues (with labels, closed by PATCH), pull requests (with head sha and merge state), comments, pagination by Link
header, and injected failures (5xx, rate limits). No network beyond the loopback."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeGitHub:
    def __init__(self, token: str = "test-token", page_size: int = 2) -> None:
        self.token, self.page_size = token, page_size
        self.repos: dict = {}  # full_name -> {"items": {n: dict}, "comments": {n: [..]}, "next": int}
        self.failures: list = []  # queued (status, headers) to answer the next requests with
        self.requests: list = []  # (method, path, authorization)
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # quiet
                pass

            def _send(self, status, body=None, headers=None):
                raw = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(raw)

            def _handle(self, method):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.requests.append((method, self.path, self.headers.get("Authorization")))
                with fake._lock:
                    failure = fake.failures.pop(0) if fake.failures else None
                if failure:
                    status, headers = failure
                    return self._send(status, {"message": "injected"}, headers)
                if self.headers.get("Authorization") != f"Bearer {fake.token}":
                    return self._send(401, {"message": "Bad credentials"})
                status, payload, headers = fake.route(method, self.path, body, self.headers.get("Host"))
                self._send(status, payload, headers)

            def do_GET(self):
                self._handle("GET")

            def do_POST(self):
                self._handle("POST")

            def do_PATCH(self):
                self._handle("PATCH")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    # ---------- seeding ----------

    def _repo(self, full_name):
        return self.repos.setdefault(full_name, {"items": {}, "comments": {}, "next": 1})

    def add_issue(self, full_name, title, body, labels=(), user="reporter", state="open"):
        r = self._repo(full_name)
        n = r["next"]
        r["next"] += 1
        r["items"][n] = {"number": n, "title": title, "body": body, "state": state, "user": {"login": user},
                         "labels": [{"name": x} for x in labels]}
        return n

    def add_pull(self, full_name, title, body, head_sha, user="solver", base_sha="0" * 40):
        r = self._repo(full_name)
        n = r["next"]
        r["next"] += 1
        r["items"][n] = {"number": n, "title": title, "body": body, "state": "open", "user": {"login": user},
                         "labels": [], "pull_request": {"url": f"/repos/{full_name}/pulls/{n}"},
                         "head": {"sha": head_sha}, "base": {"sha": base_sha}, "merged": False, "merged_at": None}
        return n

    def merge(self, full_name, n):
        item = self.repos[full_name]["items"][n]
        item["merged"], item["state"], item["merged_at"] = True, "closed", "2026-11-01T00:00:00Z"

    # ---------- routing ----------

    def route(self, method, path, body, host):
        u = urlparse(path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        m = re.fullmatch(r"/repos/([^/]+/[^/]+)/(issues|pulls)(?:/(\d+))?(/comments)?", u.path)
        if not m:
            return 404, {"message": "Not Found"}, None
        full, kind, num, comments = m.group(1), m.group(2), m.group(3), m.group(4)
        repo = self.repos.get(full)
        if repo is None:
            return 404, {"message": "Not Found"}, None
        if num is None and kind == "issues" and method == "GET":
            items = [i for i in repo["items"].values() if q.get("state", "open") in (i["state"], "all")]
            if q.get("labels"):
                items = [i for i in items if q["labels"] in [x["name"] for x in i["labels"]]]
            return self._page(items, u.path, q, host)
        if num is None and kind == "pulls" and method == "GET":
            items = [{k: v for k, v in i.items() if k not in ("pull_request", "merged")}  # as GitHub lists them
                     for i in reversed(list(repo["items"].values()))
                     if "pull_request" in i and q.get("state", "open") in (i["state"], "all")]
            return self._page(items, u.path, q, host)
        n = int(num)
        item = repo["items"].get(n)
        if item is None:
            return 404, {"message": "Not Found"}, None
        if comments:
            if method == "POST":
                c = {"id": 1000 + sum(len(v) for v in repo["comments"].values()), "body": body["body"],
                     "user": {"login": "bot"}}
                repo["comments"].setdefault(n, []).append(c)
                return 201, c, None
            return self._page(repo["comments"].get(n, []), u.path, q, host)
        if method == "PATCH":  # an issue's or a pull request's state (GitHub's PATCH /issues/{n})
            if body.get("state") in ("open", "closed"):
                item["state"] = body["state"]
            if body.get("state_reason"):
                item["state_reason"] = body["state_reason"]
            return 200, {k: v for k, v in item.items() if k != "pull_request"} if kind == "pulls" else item, None
        if kind == "pulls":
            if "pull_request" not in item:
                return 404, {"message": "Not Found"}, None
            return 200, {k: v for k, v in item.items() if k != "pull_request"}, None
        return 200, item, None

    def _page(self, items, path, q, host):
        page = int(q.get("page", "1"))
        size = self.page_size
        chunk = items[(page - 1) * size: page * size]
        headers = {}
        if page * size < len(items):
            nq = dict(q, page=str(page + 1))
            query = "&".join(f"{k}={v}" for k, v in nq.items())
            headers["Link"] = f'<http://{host}{path}?{query}>; rel="next"'
        return 200, chunk, headers
