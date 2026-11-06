"""The exchange service (proof-of-fix#117): the board the drawn judges of a RaceV2 post their round's messages to,
over HTTP, when they share no folder. Standard library only.

    POST /v1/<race>/<submission>/<kind>   {"node": "0x…", …the message}   -> 200 {"ok": true} or {"error": …}
    GET  /v1/<race>/<submission>/<kind>                                    -> {node: message}
    GET  /healthz                                                          -> {"ok": true, "race": …}

The kinds and their messages are the node's (oracle/node_v2.py):
    seal     {"seal": "0x<32 bytes>", "sig"}                 sig over keccak256(seal)
    reveal   {"outcome", "receipt": "<hex>", "salt", "sig"}  sig over keccak256(receipt); opens the node's seal:
             keccak256(receipt ‖ word(outcome) ‖ salt ‖ word(node)) == seal
    result   {"verdict", "sig"}                              sig over RaceV2's Result digest (an empty fee list)
    merged   {"verdict", "weight", "sig"}                    sig over RaceV2's Merged digest
Usage reports aren't here: the judges send them to the meter on-chain (Fees.report), which checks them itself.

Nothing to trust: the service holds no key and relays nothing. It takes a message only when its signature recovers to
the node that posts it and that node is drawn for the submission and not recused (Verdicts.drawn, read from the
chain), a reveal only when it opens that node's seal, and a verdict's signature only over RaceV2's own digest for that
submission. So it can withhold a message but not forge one, and the nodes check everything again when they read
(they also relay the result themselves, and see on-chain when someone did). Reading is open to whoever reaches it:
behind the devnet's Caddy, the holders of a per-engineer API key.

Deadlines, per submission, from its first seal (the contracts' SEAL_WINDOW and REVEAL_WINDOW are still TODO(5.5) in
Verdicts.sol, so they're configured here, matching the nodes' ORACLE_ROUND_TIMEOUT):
- seals are taken until every drawn judge sealed or the seal window closes, whichever comes first;
- reveals only after that (an early reveal is answered 425 Too Early, and the node sends it again), and until the
  reveal window closes (410 Gone after it);
- the first seal and the first reveal a node posts are final (409 for a different one; the same one again is fine).

Limits: a body up to 64 KiB (413 above); only the drawn judges of a submission that exists on-chain write, one message
per judge and kind, so a race's board grows with its checks only; a submission's messages expire a retention period
after the last one taken (default 7 days: long enough for the merge's signatures, which come when the pull request is
merged), and the state file is compacted to the live ones when the service starts.

Refusals: 400 malformed, 403 not drawn / recused / a bad signature / a reveal that doesn't open its seal, 404 another
race or an unknown submission, 409 a changed seal or reveal, 410 past a window, 424 a reveal without its node's seal,
425 too early, 503 the chain can't be read. The node sends 425 and 5xx again, and its seal before the reveal on 424."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from oracle import crypto, v2

KINDS = ("seal", "reveal", "result", "merged")
FIELDS = {"seal": {"seal", "sig"}, "reveal": {"outcome", "receipt", "salt", "sig"}, "result": {"verdict", "sig"},
          "merged": {"verdict", "weight", "sig"}}
MAX_BODY = 64 * 1024
RETENTION = 7 * 24 * 3600.0  # seconds a submission's messages are kept after its last one


class Refused(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status, self.reason = status, reason


def _hex(value, size: int | None = None, prefixed: bool = True) -> bytes:
    if not isinstance(value, str) or (prefixed and not value.startswith("0x")):
        raise Refused(400, "malformed hex")
    try:
        raw = bytes.fromhex(value[2:] if prefixed else value)
    except ValueError:
        raise Refused(400, "malformed hex") from None
    if size is not None and len(raw) != size:
        raise Refused(400, f"expected {size} bytes")
    return raw


def _signer(digest: bytes, sig) -> str:
    try:
        return crypto.recover(digest, _hex(sig, 65)).lower()
    except (ValueError, TypeError):
        raise Refused(403, "the signature doesn't recover") from None


class Board:
    """The messages of one RaceV2's rounds, checked on the way in. `chain` is an oracle.v2.Chain (or a test's fake
    with the same submission, drawn, chain_id and race_domain)."""

    def __init__(self, chain, seal_window: float = 60.0, reveal_window: float = 600.0, clock=time.time,
                 state: Path | None = None, log=print, retention: float = RETENTION) -> None:
        self.chain, self.race = chain, chain.race.lower()
        self.seal_window, self.reveal_window, self.clock, self.log = seal_window, reveal_window, clock, log
        self.retention = retention
        self.msgs: dict = {}  # submission -> kind -> {node: message}
        self.first_seal: dict = {}  # submission -> when its first seal arrived (this service's clock)
        self.last: dict = {}  # submission -> when its last message was taken: it expires `retention` after
        self._judges: dict = {}  # submission -> the drawn judges, not recused (lowercase)
        self._domain = None
        self.lock = threading.Lock()
        self.state = Path(state) if state else None
        if self.state and self.state.exists():
            self._load()

    # ---------- the board ----------

    def read(self, s: int, kind: str) -> dict:
        if kind not in KINDS:
            raise Refused(404, "unknown kind")
        with self.lock:
            self.expire(self.clock())
            return dict(self.msgs.get(s, {}).get(kind, {}))

    def expire(self, now: float) -> None:
        """Forget the submissions whose last message is older than the retention (under the lock)."""
        for s in [s for s, t in self.last.items() if now >= t + self.retention]:
            for d in (self.msgs, self.first_seal, self.last, self._judges):
                d.pop(s, None)

    def post(self, s: int, kind: str, body) -> None:
        if kind not in KINDS:
            raise Refused(404, "unknown kind")
        if not isinstance(body, dict) or not isinstance(body.get("node"), str):
            raise Refused(400, "expected {\"node\": \"0x…\", …the message}")
        node = body["node"].lower()
        _hex(node, 20)
        msg = {k: v for k, v in body.items() if k != "node"}
        if set(msg) != FIELDS[kind]:
            raise Refused(400, f"a {kind} has exactly {', '.join(sorted(FIELDS[kind]))}")
        judges = self.judges(s)
        if node not in judges:
            raise Refused(403, "not drawn for this submission (or recused)")
        check = getattr(self, "_" + kind)
        with self.lock:
            now = self.clock()
            self.expire(now)
            if self.msgs.get(s, {}).get(kind, {}).get(node) == msg:
                return  # the same message again (a node posting what the service already has): taken
            check(s, node, msg, judges, now)
            self.msgs.setdefault(s, {}).setdefault(kind, {})[node] = msg
            self.last[s] = now
            if kind == "seal":
                self.first_seal.setdefault(s, now)
            self._persist({"t": now, "s": s, "kind": kind, "node": node, "msg": msg})

    def judges(self, s: int) -> list:
        if s not in self._judges:
            try:
                sub = self.chain.submission(s)
                seed = v2.b32(sub["seed"])
                if seed == v2.ZERO:
                    raise Refused(404, "no such submission")
                judges, recused = self.chain.drawn(seed, sub["bounty"], s)
            except Refused:
                raise
            except Exception as e:  # noqa: BLE001 (the chain is down or slow: the node sends it again)
                raise Refused(503, f"the chain can't be read ({e.__class__.__name__})") from None
            out = {j.lower() for j in recused}
            self._judges[s] = [j.lower() for j in judges if j.lower() not in out]
        return self._judges[s]

    def domain(self) -> bytes:
        if self._domain is None:
            d = self.chain.race_domain()
            if d != v2.race_domain(self.chain.chain_id(), self.chain.race):
                raise RuntimeError("RaceV2's EIP-712 domain isn't v2's")
            self._domain = d
        return self._domain

    def seal_closed(self, s: int, judges: list, now: float) -> bool:
        if set(judges) <= set(self.msgs.get(s, {}).get("seal", {})):
            return True
        return s in self.first_seal and now >= self.first_seal[s] + self.seal_window

    # ---------- the checks, per kind (under the lock) ----------

    def _seal(self, s, node, msg, judges, now) -> None:
        seal = _hex(msg["seal"], 32)
        if _signer(crypto.keccak256(seal), msg["sig"]) != node:
            raise Refused(403, "the seal isn't signed by the node")
        self._final(s, "seal", node, msg)
        if self.seal_closed(s, judges, now):
            raise Refused(410, "the seal window closed")

    def _reveal(self, s, node, msg, judges, now) -> None:
        receipt, salt = _hex(msg["receipt"], 32, prefixed=False), _hex(msg["salt"], 32)
        if not isinstance(msg["outcome"], int) or isinstance(msg["outcome"], bool) or not 0 <= msg["outcome"] < 256:
            raise Refused(400, "outcome: a small integer")
        if _signer(crypto.keccak256(receipt), msg["sig"]) != node:
            raise Refused(403, "the reveal isn't signed by the node")
        seal = self.msgs.get(s, {}).get("seal", {}).get(node)
        if seal is None:
            raise Refused(424, "this node didn't seal")
        opened = crypto.keccak256(receipt + crypto.word(msg["outcome"]) + salt + crypto.word(node))
        if "0x" + opened.hex() != seal["seal"].lower():
            raise Refused(403, "the reveal doesn't open the node's seal")
        self._final(s, "reveal", node, msg)
        if not self.seal_closed(s, judges, now):
            raise Refused(425, "too early: the seal window is open")
        if now >= self.first_seal[s] + self.seal_window + self.reveal_window:
            raise Refused(410, "the reveal window closed")

    def _result(self, s, node, msg, judges, now) -> None:
        v = self._verdict(s, msg)
        if _signer(v2.result_digest(self.domain(), v), msg["sig"]) != node:
            raise Refused(403, "the verdict isn't signed by the node")

    def _merged(self, s, node, msg, judges, now) -> None:
        if not isinstance(msg["weight"], int) or isinstance(msg["weight"], bool) or msg["weight"] < 0:
            raise Refused(400, "weight: a non-negative integer")
        v = self._verdict(s, msg)
        if _signer(v2.merged_digest(self.domain(), v, msg["weight"]), msg["sig"]) != node:
            raise Refused(403, "the merge isn't signed by the node")

    def _verdict(self, s, msg) -> v2.Verdict:
        try:
            v = v2.Verdict.from_json(msg["verdict"])
        except (KeyError, TypeError, ValueError, AttributeError):
            raise Refused(400, "malformed verdict") from None
        if v.submission != s or v.to_json() != msg["verdict"]:
            raise Refused(400, "the verdict is for another submission, or not in its canonical form")
        return v

    def _final(self, s, kind, node, msg) -> None:
        old = self.msgs.get(s, {}).get(kind, {}).get(node)
        if old is not None and old != msg:
            raise Refused(409, f"this node's {kind} is already posted, and differs")

    # ---------- state (a JSON line per message taken; replayed on start) ----------

    def _persist(self, row: dict) -> None:
        if self.state:
            self.state.parent.mkdir(parents=True, exist_ok=True)
            with self.state.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")

    def _load(self) -> None:
        rows = []
        for line in self.state.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                s, kind, t = int(row["s"]), row["kind"], float(row["t"])
                if kind not in KINDS:
                    continue
                self.msgs.setdefault(s, {}).setdefault(kind, {})[str(row["node"]).lower()] = row["msg"]
                self.last[s] = max(self.last.get(s, t), t)
                if kind == "seal":
                    self.first_seal[s] = min(self.first_seal.get(s, t), t)
                rows.append(row)
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
        self.expire(self.clock())
        live = [r for r in rows if int(r["s"]) in self.last]
        if len(live) < len(rows):  # compact: keep the live submissions' rows only
            tmp = self.state.with_name(self.state.name + ".tmp")
            tmp.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in live), encoding="utf-8")
            tmp.replace(self.state)
        self.log(f"exchange: {len(live)} message(s) restored from {self.state}, {len(rows) - len(live)} expired")


class Handler(BaseHTTPRequestHandler):
    board: Board  # set on the server's subclass
    server_version = "pof-exchange/1"

    def do_GET(self) -> None:  # noqa: N802 (http.server's name)
        parts = self._parts()
        if parts == ["healthz"]:
            return self._send(200, {"ok": True, "race": self.board.race})
        try:
            s, kind = self._route(parts)
            self._send(200, self.board.read(s, kind))
        except Refused as e:
            self._send(e.status, {"error": e.reason})

    def do_POST(self) -> None:  # noqa: N802
        try:
            s, kind = self._route(self._parts())
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0 or n > MAX_BODY:
                raise Refused(400 if n <= 0 else 413, "a JSON body up to 64 KiB")
            try:
                body = json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                raise Refused(400, "not JSON") from None
            self.board.post(s, kind, body)
            self._send(200, {"ok": True})
        except Refused as e:
            if e.status != 425:
                self.board.log(f"exchange: refused a {self.path.rsplit('/', 1)[-1]} ({e.status} {e.reason})")
            self._send(e.status, {"error": e.reason})
        except Exception as e:  # noqa: BLE001 (never a stack trace to the client)
            self.board.log(f"exchange: error on {self.path}: {e!r}")
            self._send(500, {"error": "internal error"})

    def _parts(self) -> list:
        return [p for p in self.path.split("?", 1)[0].split("/") if p]

    def _route(self, parts: list) -> tuple:
        if len(parts) != 4 or parts[0] != "v1":
            raise Refused(404, "expected /v1/<race>/<submission>/<kind>")
        if parts[1].lower() != self.board.race:
            raise Refused(404, "this exchange serves another race")
        if not parts[2].isdigit():
            raise Refused(404, "submission: a number")
        return int(parts[2]), parts[3]

    def _send(self, status: int, body) -> None:
        raw = json.dumps(body, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt, *args) -> None:  # the board logs refusals; no access log (no client details kept)
        pass


def server(board: Board, host: str = "127.0.0.1", port: int = 8560) -> ThreadingHTTPServer:
    """An HTTP server for the board (call serve_forever(); port 0 picks a free one: server_address[1])."""
    handler = type("BoardHandler", (Handler,), {"board": board})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    return srv
