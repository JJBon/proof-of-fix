"""How the drawn judges reach each other (proof-of-fix#117): the node's exchange transport, a pluggable interface.

A node posts its own messages for a submission (`put`) and reads everyone's (`all`), by kind: the seal, the reveal, its
signature on the result, and its signature on the merge. (Usage reports go to the meter on-chain, not through here.)
One kind is kept under an on-chain issue instead (proof-of-fix#210): `accept`, a seat's signature on a claimed
registration's accept; then the number passed is the issue's (the folder keeps it in `issue-<N>/`, the service under
/v1/<race>/issue/<N>/accept).
The transports (ORACLE_EXCHANGE_TRANSPORT, a comma-separated list) carry the same messages:

- folder:  a directory the nodes share (ORACLE_EXCHANGE); one machine: the tests, the folder demo;
- http:    the hosted exchange service (exchange/, ORACLE_EXCHANGE_URL): a CONVENIENCE RELAY for judges on separate
           machines, never a required dependency;
- onchain: seals, reveals, receipts and usage reports posted to the contracts: v3's default (#139, D18). v2's
           contracts take none, so there it stays unavailable;
- p2p:     gossip between the judges (libp2p, Waku…): an interface only, for now.

With several (e.g. "onchain,http" on v3, "http,folder" on one machine), a node posts to every one and reads
the union, so any single transport going down, the hosted service included, doesn't stop a check: the nodes still
relay the result themselves, from what they read and the chain's own data (the domain, the submission, the draw).

None is trusted. Every message is signed by its node's seat key and the node checks each one it reads against the
drawn judges and their seals (oracle/node_v2.py), so a writer to the folder, the service or the gossip can withhold
messages but can't vote. The hosted service checks the same on the way in, so it stores nothing a node would throw
away."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .rpc import auth_headers, split_auth

KINDS = ("seal", "reveal", "result", "merged", "accept", "receipt", "usage")  # the last two are v3's (onchain)
ISSUE_KINDS = ("accept",)  # under an on-chain issue, not a submission


def folder_name(s: int, kind: str) -> str:
    return f"issue-{int(s)}" if kind in ISSUE_KINDS else str(s)
RETRY = {408, 425, 429, 500, 502, 503, 504}  # the service is busy, restarting, or it's too early: send again later
NEEDS_SEAL = 424  # a reveal the service has no seal for (it restarted empty): post the seal again, then the reveal


class Transport:
    """The interface. `put` never blocks the node on a peer and never raises for one that's away (it retries or drops
    and logs); `all` returns {node (lowercase): message} for a submission and kind, possibly incomplete, possibly with
    junk: the node checks every message."""

    name = ""

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        raise NotImplementedError

    def all(self, s: int, kind: str) -> dict:
        raise NotImplementedError


class FolderExchange(Transport):
    """`folder`: the drawn judges' messages for one race: <root>/<race>/<submission>/<node>.<kind>.json, written atomically."""

    name = "folder"

    def __init__(self, root: Path, race: str) -> None:
        self.root = Path(root) / race.lower()

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        d = self.root / folder_name(s, kind)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f".{node.lower()}.{kind}.{secrets.token_hex(4)}"
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(tmp, d / f"{node.lower()}.{kind}.json")

    def all(self, s: int, kind: str) -> dict:
        d = self.root / folder_name(s, kind)
        out = {}
        for f in sorted(d.glob(f"*.{kind}.json")) if d.exists() else []:
            try:
                out[f.name.split(".")[0]] = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return out


class HttpExchange(Transport):
    """`http`: the hosted exchange service's client (a convenience relay, optional): POST <url>/v1/<race>/<submission>/<kind> ({"node", ...message}) and GET the
    same path ({node: message}). The URL's user info (https://<handle>:<key>@host/exchange) is sent as HTTP Basic, the
    devnet's per-engineer key, and never printed.

    It never blocks the node: a message the service can't take yet (down, busy, or a reveal before the seal window
    closed: 425) waits in an outbox and goes again on the next call, seals before reveals before signatures; one the
    service refuses for good (a 4xx: not drawn, a bad signature, a reveal that doesn't open its seal) is dropped and
    logged. Reads fall back to what was last read, plus the node's own messages, while the service is unreachable.
    When the service is back, or no longer shows a message of the node's own (it restarted with no state), the node's
    messages are posted again (the same message twice is taken once), so the round recovers on its own."""

    name = "http"

    def __init__(self, url: str, race: str, headers: dict | None = None, timeout: float = 10.0, log=print,
                 clock=time.monotonic) -> None:
        bare, basic = split_auth(url.rstrip("/"))
        self.url, self.race = bare, race.lower()  # self.url never carries the key, so logs can print it
        self.headers = {**({"Authorization": basic} if basic else {}), **(headers or {})}
        self.timeout, self.log, self.clock = timeout, log, clock
        self.outbox: list = []  # [(s, node, kind, data)], in the order put
        self.mine: dict = {}  # (s, kind) -> {node: data}: what this node posted and the service didn't refuse
        self.seen: dict = {}  # (s, kind) -> {node: data}: the last successful read
        self.down = False

    # ---------- the interface (oracle/node_v2.py) ----------

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        node = node.lower()
        self.mine.setdefault((s, kind), {})[node] = data
        self._queue(s, node, kind, data)
        self.flush()

    def all(self, s: int, kind: str) -> dict:
        self.flush()
        status, body = self._request("GET", self._path(s, kind))
        if status == 200 and isinstance(body, dict):
            fresh = {str(n).lower(): m for n, m in body.items() if isinstance(m, dict)}
            self.seen[(s, kind)] = fresh
            for node, data in self.mine.get((s, kind), {}).items():
                if fresh.get(node) != data and not self._queued(s, node, kind):
                    self._queue(s, node, kind, data)  # the service lost it: post it again
        return {**self.seen.get((s, kind), {}), **self.mine.get((s, kind), {})}

    # ---------- the outbox ----------

    def flush(self) -> None:
        pending, self.outbox, keep = self.outbox, [], []
        for i, (s, node, kind, data) in enumerate(pending):
            status, body = self._request("POST", self._path(s, kind), {"node": node, **data})
            if status == 200:
                continue
            if status == NEEDS_SEAL and kind == "reveal" and node in self.mine.get((s, "seal"), {}):
                keep += [(s, node, "seal", self.mine[(s, "seal")][node]), (s, node, kind, data)]
                continue
            if status is None or status in RETRY:
                keep.append((s, node, kind, data))
                if status is None:  # unreachable: don't knock once per queued message
                    keep.extend(pending[i + 1:])
                    break
                continue
            why = body.get("error", "") if isinstance(body, dict) else ""
            self.log(f"submission {s}: the exchange refused this node's {kind} ({status} {why}); dropped")
            if self.mine.get((s, kind), {}).get(node) == data:
                del self.mine[(s, kind)][node]
        for m in keep:  # with whatever was queued meanwhile (the service came back: everything of the node's own)
            if not self._queued(*m[:3]):
                self._queue(*m)

    def _queue(self, s: int, node: str, kind: str, data: dict) -> None:
        rest = [m for m in self.outbox if m[:3] != (s, node, kind)] + [(s, node, kind, data)]
        self.outbox = sorted(rest, key=lambda m: KINDS.index(m[2]))  # stable: a seal goes before its reveal

    def _requeue_mine(self) -> None:
        for (s, kind), msgs in list(self.mine.items()):
            for node, data in msgs.items():
                if not self._queued(s, node, kind):
                    self._queue(s, node, kind, data)

    def _queued(self, s: int, node: str, kind: str) -> bool:
        return any(m[:3] == (s, node, kind) for m in self.outbox)

    # ---------- HTTP ----------

    def _path(self, s: int, kind: str) -> str:
        if kind not in KINDS:
            raise ValueError(f"unknown message kind {kind!r}")
        if kind in ISSUE_KINDS:
            return f"/v1/{self.race}/issue/{int(s)}/{kind}"
        return f"/v1/{self.race}/{int(s)}/{kind}"

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple:
        """(status, the decoded JSON body); status None when the service can't be reached."""
        data = json.dumps(body, sort_keys=True).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers={**self.headers, "Content-Type": "application/json",
                                              "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        except (urllib.error.URLError, OSError, ValueError) as e:
            if not self.down:
                self.log(f"the exchange at {self.url} is unreachable ({e.__class__.__name__}); "
                         f"{len(self.outbox)} message(s) wait")
                self.down = True
            return None, None
        if self.down:
            self.log(f"the exchange at {self.url} is back")
            self.down = False
            self._requeue_mine()  # it may have restarted without what it had
        try:
            return status, json.loads(raw.decode("utf-8") or "null")
        except ValueError:
            return status, None


class OnchainExchange(Transport):
    """`onchain`: v3's default (proof-of-fix#139, design D18). The messages are transactions to the contracts, which
    enforce the windows and open the seals themselves, and `all` reads them back from the panel's seats. For v3 the
    number passed is the panel's id (a validator may sit on several panels of one submission), and the kinds are:

    - seal:    {"seal", "sig"}                  -> Panels.seal
    - reveal:  {"vote", "mask", "salt", "sig"}  -> Panels.reveal
    - receipt: {"receipt", "sig"}               -> Panels.receipt (the receipt's hash, posted on-chain)
    - usage:   {"usage", "sig"}                 -> RaceV3.report (the seat's metered usage, bound to its receipt)

    Each is signed by the seat's key as a registry statement, so any account may send it: `wallet` pays the gas.
    A transaction the chain refuses raises (oracle.rpc.Reverted): the node reads the seat again before it goes on.

    v2's contracts take no seals (#122 was never built there: v3 builds its own, D18), so on a v2 chain this transport
    still isn't available."""

    name = "onchain"
    V3_KINDS = ("seal", "reveal", "receipt", "usage")

    def __init__(self, chain, keys=None, log=print, wallet=None) -> None:
        self.chain, self.keys, self.log, self.wallet = chain, keys, log, wallet

    def _v3(self):
        if getattr(self.chain, "version", 2) != 3:
            raise NotImplementedError("onchain transport: v2's contracts take no seals (v3 only, design D18)")
        if self.wallet is None:
            from .rpc import Wallet

            self.wallet = Wallet(self.chain.rpc, self.keys.account_secret(), "node")
        return self.chain

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        c = self._v3()
        sig = bytes.fromhex(data["sig"][2:])
        if kind == "seal":
            self.wallet.send(c.panels, "seal(uint256,address,bytes32,bytes)", s, node, data["seal"], sig)
        elif kind == "reveal":
            self.wallet.send(c.panels, "reveal(uint256,address,bool,uint8,bytes32,bytes)", s, node,
                             bool(data["vote"]), int(data["mask"]), data["salt"], sig)
        elif kind == "receipt":
            self.wallet.send(c.panels, "receipt(uint256,address,bytes32,bytes)", s, node, data["receipt"], sig)
        elif kind == "usage":
            self.wallet.send(c.race, "report(uint256,address,(bytes32,uint64,uint64,uint64,uint64,uint64,uint64),bytes)",
                             s, node, tuple(data["usage"]), sig)
        else:
            raise ValueError(f"the onchain transport carries {', '.join(self.V3_KINDS)}; not {kind!r}")

    def all(self, s: int, kind: str) -> dict:
        c = self._v3()
        if kind not in self.V3_KINDS:
            raise ValueError(f"the onchain transport carries {', '.join(self.V3_KINDS)}; not {kind!r}")
        out = {}
        for slot, key in enumerate(c.judges(s)):
            if not key:
                continue
            if kind == "usage":
                u = c.usage_of(s, slot)
                if any(u.receipt):
                    out[key.lower()] = {"usage": ["0x" + u.receipt.hex(), *u.as_tuple()[1:]]}
                continue
            seat = c.seat(s, slot)
            if kind == "seal" and seat["hasSeal"]:
                out[key.lower()] = {"seal": seat["seal"]}
            elif kind == "reveal" and seat["revealed"]:
                out[key.lower()] = {"vote": seat["vote"], "mask": seat["mask"]}
            elif kind == "receipt" and seat["receipted"]:
                out[key.lower()] = {"receipt": seat["receipt"]}
        return out


class P2pExchange(Transport):
    """`p2p`: gossip between the drawn judges (a libp2p pubsub topic, or a Waku content topic, per race and
    submission). An interface only: `put` publishes the signed message, `all` returns what was heard (kept per
    submission until it's decided). Peers are found from the seats' published endpoints; nothing here trusts them,
    the node checks every message as it does the others'. TODO: a library choice (standard-library-only rule: likely a
    sidecar the node talks to over localhost)."""

    name = "p2p"

    def __init__(self, topic: str, log=print) -> None:
        self.topic, self.log = topic, log

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        raise NotImplementedError("p2p transport: an interface only (no gossip library yet)")

    def all(self, s: int, kind: str) -> dict:
        raise NotImplementedError("p2p transport: an interface only (no gossip library yet)")


class Fanout(Transport):
    """Several transports at once: `put` to each, `all` the union (the first transport's copy wins when two differ;
    the node checks every one anyway). A transport that fails is logged and skipped, so none is required."""

    def __init__(self, transports: list, log=print) -> None:
        self.transports, self.log = list(transports), log
        self.name = ",".join(x.name for x in self.transports)
        self._failing: set = set()

    def put(self, s: int, node: str, kind: str, data: dict) -> None:
        for x in self.transports:
            self._try(x, lambda: x.put(s, node, kind, data))

    def all(self, s: int, kind: str) -> dict:
        out: dict = {}
        for x in reversed(self.transports):
            got = self._try(x, lambda: x.all(s, kind))
            out.update(got or {})
        return out

    def _try(self, x, fn):
        try:
            got = fn()
            self._failing.discard(x.name)
            return got
        except Exception as e:  # noqa: BLE001 (one transport down must not stop the node)
            if x.name not in self._failing:
                self.log(f"the {x.name} exchange transport failed ({e.__class__.__name__}: {e}); using the others")
                self._failing.add(x.name)
            return None


TRANSPORTS = ("folder", "http", "onchain", "p2p")


def exchange_from_env(env, race: str, log=print, chain=None, keys=None, wallet=None):
    """The node's transport(s): ORACLE_EXCHANGE_TRANSPORT, comma-separated from TRANSPORTS (default: "onchain" on a
    v3 chain; on v2 "http" when ORACLE_EXCHANGE_URL is set, else "folder"); more than one fans out (Fanout).
      folder   ORACLE_EXCHANGE, the shared directory (default .oracle-exchange)
      http     ORACLE_EXCHANGE_URL; its key: the URL's user info, else ORACLE_EXCHANGE_TOKEN (in
               ORACLE_EXCHANGE_API_KEY_HEADER, as for the RPC's token), else the RPC's own key when the service is on
               the RPC's host (the devnet's Caddy serves both under the same per-engineer keys); never another host's
      onchain  v3 only: the contracts themselves (`wallet` sends, default the node's own key)
      p2p      an interface only (ORACLE_EXCHANGE_TOPIC)"""
    default = ("onchain" if getattr(chain, "version", 2) == 3 else
               "http" if env.get("ORACLE_EXCHANGE_URL") else "folder")
    names = [n.strip() for n in (env.get("ORACLE_EXCHANGE_TRANSPORT") or default).split(",") if n.strip()]
    bad = [n for n in names if n not in TRANSPORTS]
    if bad or not names:
        raise SystemExit(f"ORACLE_EXCHANGE_TRANSPORT: {', '.join(bad) or 'empty'}; choose from {', '.join(TRANSPORTS)}")
    built = []
    for n in names:
        if n == "folder":
            built.append(FolderExchange(Path(env.get("ORACLE_EXCHANGE", ".oracle-exchange")), race))
        elif n == "http":
            built.append(_http_from_env(env, race, log))
        elif n == "onchain":
            built.append(OnchainExchange(chain, keys, log, wallet))
        else:
            built.append(P2pExchange(env.get("ORACLE_EXCHANGE_TOPIC", f"pof/{race.lower()}"), log))
    return built[0] if len(built) == 1 else Fanout(built, log)


def _http_from_env(env, race: str, log) -> HttpExchange:
    url = env.get("ORACLE_EXCHANGE_URL", "")
    if not url:
        raise SystemExit("the http exchange transport needs ORACLE_EXCHANGE_URL")
    headers: dict = {}
    if split_auth(url)[1] is None:
        token = env.get("ORACLE_EXCHANGE_TOKEN")
        header = env.get("ORACLE_EXCHANGE_API_KEY_HEADER") or env.get("ORACLE_RPC_API_KEY_HEADER") or "Authorization"
        if token:
            headers = auth_headers(token, header)
        elif env.get("ORACLE_RPC") and _same_host(url, env["ORACLE_RPC"]):
            _, basic = split_auth(env["ORACLE_RPC"])
            rpc_token = env.get("ORACLE_RPC_TOKEN") or env.get("RPC_API_KEY")
            headers = {"Authorization": basic} if basic else auth_headers(rpc_token, header)
    return HttpExchange(url, race, headers=headers, log=log,
                        timeout=float(env.get("ORACLE_EXCHANGE_TIMEOUT", "10")))


def _same_host(a: str, b: str) -> bool:
    ua, ub = urllib.parse.urlsplit(a), urllib.parse.urlsplit(b)
    return (ua.scheme, ua.hostname, ua.port) == (ub.scheme, ub.hostname, ub.port)
