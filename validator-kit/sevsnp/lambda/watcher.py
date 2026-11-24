"""The SEV-SNP validator's watcher (#251 task 4.9, #253; v3): runs every minute in the validator's own AWS account,
reads v3's Panels for seats given to this validator's key, and starts the stopped SEV-SNP instance only when one of
them needs the node. The node (`oracle run --until-idle`, oracle/node_v3.py) judges, seals, reveals and reports, holds
the instance up while any of its seats is open, and powers it off once idle; this function only starts it.

v2's watcher (validator-kit/lambda/watcher.py) read RaceV2's `Committed` and `Verdicts.drawn`; v3 names every seat in
one event, Panels' `Seated(pid, slot, key, sealBy)` with the key indexed, whatever the panel's kind: a counted panel,
a shadow, an audit, a challenge panel, and a replacement seat on any of them (a missed deadline's `advance` or
`refill`). Each seat found stays on the watcher's list (its SSM parameter) until it no longer needs the node, read from
Panels' views every run, in the chain's time (the latest block's timestamp: Panels' windows are in it):

- seal due: the seat hasn't sealed and the panel's `sealBy` hasn't passed. A refill restarts every seat's windows
  (`resetTimeline`), so `sealBy` is read from `panel(pid)`, never kept from the event;
- reveal due: the seat sealed but hasn't revealed with its receipt, `revealBy` hasn't passed, and the reveal can open:
  on a judging panel as soon as every seat has sealed ("panel full", #311: Panels opens the reveal then, not at
  `sealBy`; a counted panel's once its shadows have sealed too, which the node checks), on a shadow panel within
  REVEAL_LEAD_SECONDS of its `sealBy`;
- otherwise waiting (sealed, the window not near), or dropped: revealed with its receipt, the panel counted or
  closed (released, or a shadow settled), the seat vacated (`judges` no longer names the key there), or a deadline
  passed (the node can't act on it any more).

Starting, with v2's guardrails:
- ENABLED, the kill switch: anything but "true" and the function reads nothing and starts nothing.
- MAX_STARTS_PER_DAY, the operator's fuse: the most starts in a UTC day (0: no limit). Past it the seats stay listed.
- A due seat starts a stopped instance at once, then again at most every RETRY_MINUTES while it stays due and the
  instance is stopped (the node crashed, or stopped at its chain-outage limit), at most SEAT_MAX_STARTS times a seat
  and phase; then it is listed as given up. A running or starting instance spends none of them.
- The spend pause: a node whose model-spending cap stopped a call sets its capacity to 0 on-chain (oracle/spend.py),
  so `Panels.capacity(key)` reads 0 checks. Then seal work doesn't start the instance (it would need model calls the
  cap refuses). A reveal still does: it opens a vote already sealed, with no model call, and a sealed seat that
  doesn't reveal is slashed (SEALED_NO_REVEAL_SLASH).
- The pause's own end: the node sets its capacity back at the next period of the cap that stopped it, which needs the
  node to run. With UNPAUSE_CHECK=daily (the default) the watcher starts the instance once a UTC day while the capacity
  reads 0 with no change pending, so the node can restore it (no model call; about 10 minutes of compute). "off": the
  operator restarts it.
- The AWS budget: with BUDGET_NAME set (the kit's budget, when its automatic stop is on) the watcher doesn't start
  the instance while the month's actual spend is at or over the limit, so it doesn't undo the budget's stop.
- An instance on its way down (stopping) can't start: nothing is counted and the next minute tries again.
- If the chain doesn't answer the run fails before it saves anything: an outage spends no starts and loses no seat.

The Radicle duty (WAKE_ON_HEAD, #251 L11 model (a); the kit sets it when the node runs ORACLE_MERGE_VIA=radicle): this
validator's Radicle node is a delegate of the repository, and the canonical `main` follows `Heads.head` only once a
majority of the delegates (4 of 7) have pushed it, each from its own node, which runs only while its host is up. Seats
alone wake a validator for the checks it is drawn for, not when a fix it didn't judge is merged, so the canonical
`main` would lag `Heads.head` until 4 delegates happened to be drawn again (tests/integration/kit_radicle.py, scenario
L). So the watcher also reads `Heads.head` (RaceV3's repository, in its Heads) every run and starts the stopped
instance once when it has moved since the last run: the node pushes `main` to it and takes the identity's pending
step, then powers off once idle (no model call; about 11 minutes of compute at `run --until-idle 600`). Like a reveal,
it isn't held by the spend pause; the fuse, the budget and the kill switch hold it as any start. A move seen while the
instance runs is the running node's. The first run only records the head.

The draw duty (WAKE_ON_DRAW, #251 v3.1 polish VP9; the kit sets it "true"): a check nobody drew has no seats, so seats
alone never wake anyone for it, and without an always-on keeper it would wait forever. So the watcher also scans
RaceV3's events that open a check (`Committed`, `Registered` and #310's `Rebased`) in the same block range as `Seated`,
keeps each check on its list (`draws`, bounded by STATE_LIMIT with the seats) and reads its verdict from
`Panels.submission(id)` when it may be due:
- due: SEALED and the head past `seedBlock + DRAW_GRACE_BLOCKS` (default 25, about 5 minutes: a running keeper draws
  first), or WAITING and the chain's time past `retryAt + DRAW_GRACE_BLOCKS x 12 s`, plus this validator's stagger,
  `keccak256(validator, id) mod (DRAW_STAGGER_MINUTES x 60)` seconds (default 10 minutes), counted from when this
  watcher first saw the sealed check past its grace (or from the waiting check's `retryAt` + grace). With n validators
  the first one's node draws it; the others then see it drawn and drop it, so usually one host wakes;
- a due check starts the stopped instance at most DRAW_MAX_STARTS times (default 1) per round: its released rounds
  (`redraws`) with its seed block or `retryAt` (a re-targeted or re-waiting check is due again later); still undrawn
  RETRY_MINUTES after its last start it is given up for that round (`draw_gave_up`) and stays listed. A running or
  starting instance spends none (its node's keeper draws it);
- like a reveal and the Radicle duty it isn't held by the spend pause (a draw makes no model call); the fuse, the
  budget and the kill switch hold it as any start;
- a drawn check (JUDGING, HELD or WINDOW, `draw_drawn` when first seen so) stays listed until it is final (#251 v3.1
  polish VP23), read again every RETRY_MINUTES: a panel released back to waiting (L19) is a new round, so the check
  wakes this validator for its redraw as it did for its first draw, and the redraw's seats wake their validators as
  any seat does. Polling never starts the instance twice for the same round. A check final, released (refunded),
  withdrawn or expired leaves the list (`draw_dropped`); when the list is full the drawn checks go first;
- at most DRAW_READS_MAX (default 20) verdicts are read a run, in turn from a cursor; a check that can't be due yet
  (its grace, its stagger or its `retryAt` ahead, or read less than RETRY_MINUTES ago while drawn, started or given
  up) isn't read. A failed read ends the run before it saves anything.

A seat is listed per panel and slot: a Seated event for a listed panel with another slot (a replacement seat after a
refill) is a new seat with its own starts.

No RPC key in any log line (#251 v3.1 polish VP20): a provider's key often sits in the URL's path (Infura's
`/v3/<key>`), so the client shows its URL as the scheme, the host and `/…` when a path segment has 8 characters or
more, and every line the handler prints, tracebacks included, passes through a redactor loaded with the URL and the
header key (a local copy of oracle/redact.py: this file runs alone in the Lambda).

Boot against the deadlines (validator-kit/SEVSNP-PLAN.md, "Boot time against the deadlines"): from a start call to a
node that can seal is about a minute on c6a.large (the 2026-11-20 evidence), plus up to a minute of this schedule.
Production windows (Sepolia's) give a seal 2 h and a reveal 1 h; minute windows (a devnet's DEVNET_V3_WINDOWS=minutes)
give 120 s and 60 s, which a cold start can't meet. A seal start with less than READY_SECONDS left is logged as `late`.

Environment (set by validator-kit/sevsnp/terraform/watcher.tf):
    RPC_URL                 the chain's JSON-RPC URL (HTTPS), when it holds no key
    RPC_URL_SECRET_ARN      or a Secrets Manager secret holding the whole URL, for an RPC whose key is in its URL
                            (read once per run, never logged); takes the place of RPC_URL
    RPC_API_KEY_SECRET_ARN  optional: a key sent in a header instead (v2's form), RPC_API_KEY_HEADER saying how:
                            "Basic" ("<handle>:<key>", the demo chain's), "Authorization" (Bearer) or a header's name
    RACE_ADDRESS            RaceV3 (the node's ORACLE_RACE): Panels is read from its contracts()
    PANELS_ADDRESS          or Panels itself
    VALIDATOR_ADDRESS       this validator's key's address: only its seats count
    INSTANCE_ID             the SEV-SNP instance, kept stopped while idle
    STATE_PARAM             the SSM parameter holding the scan's state
    ENABLED                 "true", or anything else: the kill switch
    MAX_BLOCK_RANGE         the most blocks scanned per run (default 2000; the kit's watcher_max_block_range)
    LOOKBACK_BLOCKS         a first run's look back (default 1200: 4 h of Sepolia's 12-second blocks, past a production
                            seal and reveal window)
    MAX_STARTS_PER_DAY      the fuse (default 0: none; the kit sets 12)
    RETRY_MINUTES           how often a seat still due starts a stopped instance again (default 10)
    SEAT_MAX_STARTS         the most starts for one seat and phase (default 3)
    REVEAL_LEAD_SECONDS     how long before a sealed seat's reveal window opens the instance is started (default 180)
    READY_SECONDS           a cold start's time to a node that can seal, for the `late` flag (default 120)
    UNPAUSE_CHECK           "daily" (default) or "off"
    WAKE_ON_HEAD            "true": the Radicle duty above (needs RACE_ADDRESS); default "false"
    WAKE_ON_DRAW            "true": the draw duty above (needs RACE_ADDRESS); default "false" here, "true" in the kit
    DRAW_GRACE_BLOCKS       blocks past a seed block before an undrawn check is due (default 25)
    DRAW_STAGGER_MINUTES    the spread of this validator's stagger over the others' (default 10)
    DRAW_MAX_STARTS         starts per check and round (released rounds, seed block or retryAt) (default 1)
    DRAW_READS_MAX          verdicts read a run (default 20)
    BUDGET_NAME, ACCOUNT_ID optional: the AWS budget whose actual spend at its limit holds every start

Standard library plus boto3 (in the Lambda runtime). run() takes its AWS clients and RPC as arguments, so the tests run
with fakes on Python 3.9 with no network (tests/test_sevsnp_watcher.py, which also checks the ABI below against
keccak256 and the contracts' source)."""

from __future__ import annotations

import base64
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request

# keccak256 of Panels' event and its views' selectors (the tests check them).
SEATED_TOPIC = "0x02e6050fc1d4cc5be0a22ce14752a944691c128f452ba26c46898e3f23bd196f"  # Seated(uint256,uint256,address,uint256)
CONTRACTS = "0x6c0f79b6"  # RaceV3.contracts(): (panels, fees, pool, registry, heads, coin, start)
PANEL = "0xaa07bd09"  # panel(uint256): 20 static words (Panel with its Snap)
SEAT = "0x3389fe48"  # seat(uint256,uint256): 9 static words
CAPACITY = "0x5694c2da"  # capacity(address) -> (checks, next, from, room)
REPO = "0x56ff3122"  # RaceV3.repo(): the deployment's one repository, keccak256 of its RID
HEAD = "0xf339e3b2"  # Heads.head(bytes32) -> Head (commit, constitution, movedAt, bounty, submission, verdict)
# The draw duty: RaceV3's events that open a check, and Panels' verdict of one. The check's id is
# Committed(uint256,uint256,address)'s topic 2, Registered(uint256,address,uint256)'s data word 0 and
# Rebased(uint256,uint256,uint256,bytes32,bytes32)'s topic 3.
COMMITTED_TOPIC = "0xcd9df6a82c34f68eed4318bab0efcf9f030dc959a4816e2036305dd1125031c2"
REGISTERED_TOPIC = "0x39dd062cc095bf933d83338d8e4591b7eb119264d876f173cacb1cfdf2c9737f"
REBASED_TOPIC = "0xbc967753976021b891a9df87aba6d972c24354d7236b5defa9d65baa4617178e"
SUBMISSION = "0x9c8c701b"  # Panels.submission(uint256): 49 static words (Submission with its three Snaps)
# Submission's words: seedBlock 2, status 3, redraws 41, retryAt 42. Status: None, Sealed, Waiting, Judging, Held, Window, Final,
# Withdrawn, Expired, Released.
STATUSES = ("none", "sealed", "waiting", "judging", "held", "window", "final", "withdrawn", "expired", "released")
SEALED, WAITING = 1, 2
DRAWN = ("judging", "held", "window")  # a drawn check, kept on the list until final (VP23): a round may be released
BLOCK_SECONDS = 12  # a grace in blocks, for a waiting check's time-based retry
# Panel's words: id 0, seed 1, sealBy 2, revealBy 3, counter 4, k 5, seats 6, nSealed 7, done 8, passes 9, level 10,
# counted 11, kind 12, closed 13, scored 14, ex 15, snap 16-19. Seat's: key 0, level 1, hasSeal 2, revealed 3,
# receipted 4, vote 5, mask 6, seal 7, receipt 8.
KINDS = ("counted", "shadow", "audit", "challenge")
SHADOW = 1
GOING_DOWN = ("stopping", "shutting-down")  # can't start yet; the node in it has already exited
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
STATE_LIMIT = 3800  # characters of the 4 KB parameter; past it the oldest drawn checks, then the oldest undrawn
# checks, then seats, go (`state-full`)
MAX_BLOCK_RANGE = 2000  # the default most blocks scanned per run (MAX_BLOCK_RANGE)
MIN_SECRET = 8  # a URL path segment this long may be a key ("v3" and "rpc" aren't)


# ---------- no key in a log line (a local copy of oracle/redact.py) ----------

def _long_segment(path: str) -> bool:
    return any(len(s) >= MIN_SECRET for s in path.split("/"))


def shown_url(url: str) -> str:
    """The URL as a log line may show it: scheme, host (and port), and `/…` when its path may hold a key."""
    try:
        u = urllib.parse.urlsplit(url)
        port = u.port
    except ValueError:
        return "…"
    if not u.scheme or not u.hostname:
        return "…" if _long_segment(url) else url
    host = u.hostname + (f":{port}" if port else "")
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
        self.secrets = sorted(set(self.secrets), key=lambda x: -len(x[0]))  # a URL whole before its path

    def __call__(self, text: str) -> str:
        for s, shown in self.secrets:
            if s in text:
                text = text.replace(s, shown)
        return text


REDACT = Redactor()  # loaded by rpc_from_env with the chain's URL and header key


def log(line: str) -> None:
    """Every line the function prints, through the redactor."""
    print(REDACT(line), flush=True)


# ---------- keccak256 (the stagger; the standard library has only FIPS 202's SHA3) ----------

def _rol(v: int, n: int) -> int:
    n %= 64
    return ((v << n) | (v >> (64 - n))) & 0xFFFFFFFFFFFFFFFF if n else v


def _keccak_f(lanes: list) -> None:
    """Keccak-f[1600] on lanes[x][y], as XKCP's CompactFIPS202 reference."""
    r = 1
    for _ in range(24):
        c = [lanes[x][0] ^ lanes[x][1] ^ lanes[x][2] ^ lanes[x][3] ^ lanes[x][4] for x in range(5)]
        d = [c[(x + 4) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                lanes[x][y] ^= d[x]
        x, y = 1, 0
        current = lanes[x][y]
        for t in range(24):
            x, y = y, (2 * x + 3 * y) % 5
            current, lanes[x][y] = lanes[x][y], _rol(current, (t + 1) * (t + 2) // 2)
        for y in range(5):
            row = [lanes[x][y] for x in range(5)]
            for x in range(5):
                lanes[x][y] = row[x] ^ ((~row[(x + 1) % 5]) & row[(x + 2) % 5])
        for j in range(7):
            r = ((r << 1) ^ ((r >> 7) * 0x71)) % 256
            if r & 2:
                lanes[0][0] ^= 1 << ((1 << j) - 1)


def keccak256(data: bytes) -> bytes:
    """Keccak-256 as Ethereum uses it (padding 0x01, rate 136 bytes)."""
    rate = 136
    padded = bytearray(data) + b"\x01" + bytes((-len(data) - 1) % rate)
    padded[-1] |= 0x80
    lanes = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            lanes[i % 5][i // 5] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(lanes)
    return b"".join(lanes[i % 5][i // 5].to_bytes(8, "little") for i in range(4))


class Rpc:
    """A minimal JSON-RPC client. A key goes in a header or in a URL read from a secret, and never in the logs: a
    failed call names its method, the URL's shown form (`shown_url`) and the error's type (and HTTP status) only."""

    def __init__(self, url: str, api_key: str | None = None, header: str = "Basic"):
        self.url, self.api_key, self.header = url, api_key, header
        self.shown = shown_url(url)

    def headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if not self.api_key:
            return h
        if self.header.lower() == "basic":
            h["Authorization"] = "Basic " + base64.b64encode(self.api_key.encode()).decode()
        elif self.header.lower() == "authorization":
            h["Authorization"] = "Bearer " + self.api_key
        else:
            h[self.header] = self.api_key
        return h

    def call(self, method: str, params: list):
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(self.url, data=body, headers=self.headers(), method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                reply = json.loads(resp.read())
        except Exception as e:  # the URL may hold the key: only its shown form in the message
            code = f" {e.code}" if isinstance(getattr(e, "code", None), int) else ""
            raise RuntimeError(f"{method}: {self.shown} didn't answer ({type(e).__name__}{code})") from None
        if "error" in reply:
            raise RuntimeError(f"{method}: {reply['error']}")
        return reply["result"]


# ---------- the few ABI calls ----------

def _word(value) -> str:
    if isinstance(value, str):
        return (value[2:] if value.startswith("0x") else value).rjust(64, "0")
    return format(int(value), "064x")


def _words(raw: str) -> list:
    raw = raw[2:] if raw.startswith("0x") else raw
    return [raw[i:i + 64] for i in range(0, len(raw), 64)]


def eth_call(rpc, to: str, selector: str, *args) -> list:
    return _words(rpc.call("eth_call", [{"to": to, "data": selector + "".join(_word(a) for a in args)}, "latest"]))


def _address(word: str) -> str:
    return "0x" + word[-40:].lower()


def panels_of(rpc, env: dict) -> str:
    if env.get("PANELS_ADDRESS"):
        return env["PANELS_ADDRESS"]
    return _address(eth_call(rpc, env["RACE_ADDRESS"], CONTRACTS)[0])


def panel(rpc, panels: str, pid: int) -> dict:
    w = [int(x, 16) for x in eth_call(rpc, panels, PANEL, pid)]
    return {"id": w[0], "sealBy": w[2], "revealBy": w[3], "k": w[5], "seats": w[6], "nSealed": w[7],
            "counted": bool(w[11]), "kind": w[12], "closed": bool(w[13])}


def seat(rpc, panels: str, pid: int, slot: int) -> dict:
    w = eth_call(rpc, panels, SEAT, pid, slot)
    return {"key": _address(w[0]), "hasSeal": bool(int(w[2], 16)), "revealed": bool(int(w[3], 16)),
            "receipted": bool(int(w[4], 16))}


def capacity(rpc, panels: str, key: str) -> dict:
    w = [int(x, 16) for x in eth_call(rpc, panels, CAPACITY, key)]
    return {"checks": w[0], "next": w[1], "from": w[2], "room": bool(w[3])}


def head_of(rpc, race: str) -> str:
    """`Heads.head(repo).commit` for RaceV3 `race`'s repository, as 64 hex digits (the Radicle duty)."""
    heads = _address(eth_call(rpc, race, CONTRACTS)[4])
    repo = eth_call(rpc, race, REPO)[0]
    return eth_call(rpc, heads, HEAD, repo)[0].lower()


def chain_now(rpc) -> int:
    """The chain's time: the latest block's timestamp (Panels' windows are in it)."""
    return int(rpc.call("eth_getBlockByNumber", ["latest", False])["timestamp"], 16)


def validator_of(env: dict) -> str:
    key = env.get("VALIDATOR_ADDRESS", "").strip()
    if not ADDRESS.match(key):
        raise ValueError("VALIDATOR_ADDRESS isn't an address: the watcher can't tell this validator's seats")
    return key.lower()


def seated(rpc, panels: str, key: str, start: int, end: int) -> dict:
    """{pid: slot} for the Seated events naming `key` in [start, end]."""
    logs = rpc.call("eth_getLogs", [{"address": panels, "topics": [SEATED_TOPIC, None, "0x" + _word(key)],
                                     "fromBlock": hex(start), "toBlock": hex(end)}])
    return {int(log["topics"][1], 16): int(_words(log["data"])[0], 16) for log in logs}


def opened(rpc, race: str, start: int, end: int) -> list:
    """The checks RaceV3 `race` opened in [start, end]: its Committed, Registered and Rebased events (the draw duty)."""
    logs = rpc.call("eth_getLogs", [{"address": race, "topics": [[COMMITTED_TOPIC, REGISTERED_TOPIC, REBASED_TOPIC]],
                                     "fromBlock": hex(start), "toBlock": hex(end)}])
    out = []
    for log_ in logs:
        topic = log_["topics"][0].lower()
        if topic == COMMITTED_TOPIC:
            out.append(int(log_["topics"][2], 16))
        elif topic == REGISTERED_TOPIC:
            out.append(int(_words(log_["data"])[0], 16))
        elif topic == REBASED_TOPIC:
            out.append(int(log_["topics"][3], 16))
    return out


def verdict(rpc, panels: str, cid: int) -> dict:
    """Panels' verdict of check `cid`: its status, seed block, released rounds and retry time."""
    w = eth_call(rpc, panels, SUBMISSION, cid)
    return {"status": int(w[3], 16), "seedBlock": int(w[2], 16), "redraws": int(w[41], 16),
            "retryAt": int(w[42], 16)}


def stagger(key: str, cid: int, minutes: float) -> int:
    """This validator's delay on check `cid`, in seconds: keccak256(abi.encode(key, cid)) mod (minutes x 60)."""
    spread = int(minutes * 60)
    if spread <= 0:
        return 0
    return int.from_bytes(keccak256(bytes.fromhex(_word(key) + _word(cid))), "big") % spread


# ---------- one seat ----------

def phase(p: dict, s: dict, key: str, now: int, lead: int) -> str:
    """What a seat needs now: "seal", "reveal", "wait", or why it's dropped ("done", "closed", "vacated", "missed")."""
    if p["k"] == 0 or p["counted"] or p["closed"]:
        return "closed"
    if s["key"] != key:
        return "vacated"
    if not s["hasSeal"]:
        return "seal" if now <= p["sealBy"] else "missed"
    if s["revealed"] and s["receipted"]:
        return "done"
    if now > p["revealBy"]:
        return "missed"
    if p["kind"] == SHADOW:
        return "reveal" if now >= p["sealBy"] - lead else "wait"
    # a judging panel's reveal opens once every seat has sealed (#311), not at `sealBy`: the node starts now and
    # reveals as soon as Panels takes it (a counted panel's also waits for its shadows' seals, which the node reads)
    return "reveal" if p["seats"] == p["k"] and p["nSealed"] == p["k"] else "wait"


def _load(raw: str) -> dict:
    if not raw or raw == "none":
        return {}
    return json.loads(raw) if raw.lstrip().startswith("{") else {"last": int(raw)}


def _fit(state: dict, limit: int = STATE_LIMIT) -> bool:
    """Keeps the state within the parameter: drops the oldest drawn checks (lowest id) first, then the oldest undrawn
    checks, then the oldest seats (lowest panel id): a seat's miss is slashed, an undrawn check is drawn by anyone, and
    a drawn one is only watched for a released round. Whether it dropped any."""
    full = False
    while len(json.dumps(state, sort_keys=True, separators=(",", ":"))) > limit:
        part = "draws" if state.get("draws") else "seats" if state.get("seats") else None
        if part is None:
            break
        drawn = [c for c, d in state[part].items() if "d" in d] if part == "draws" else []
        del state[part][min(drawn or state[part], key=int)]
        if not state[part]:
            del state[part]
        full = True
    return full


def budget_reached(budgets, account: str, name: str) -> bool:
    b = budgets.describe_budget(AccountId=account, BudgetName=name)["Budget"]
    actual = float(((b.get("CalculatedSpend") or {}).get("ActualSpend") or {}).get("Amount") or 0)
    return actual >= float(b["BudgetLimit"]["Amount"])


def run(env: dict, rpc, ssm, ec2, budgets=None, now=time.time) -> dict:
    """One pass. `budgets`: a factory of a boto3 Budgets client, called only before a start with BUDGET_NAME set."""
    if env.get("ENABLED", "false").lower() != "true":
        return {"action": "disabled"}
    param = env["STATE_PARAM"]
    try:
        state = _load(ssm.get_parameter(Name=param)["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        state = {}
    key = validator_of(env)
    panels = panels_of(rpc, env)
    seats = {int(k): dict(v) for k, v in (state.get("seats") or {}).items()}
    draws = {int(k): dict(v) for k, v in (state.get("draws") or {}).items()}
    last = state.get("last")
    race = env.get("RACE_ADDRESS", "")
    draw_on = env.get("WAKE_ON_DRAW", "false").lower() == "true" and bool(race)

    # The new seats (and, with the draw duty, the new checks) since the last block scanned.
    head = int(rpc.call("eth_blockNumber", []), 16)
    start = max(head - int(env.get("LOOKBACK_BLOCKS", "1200")), 0) if last is None else last + 1
    end = min(head, start + int(env.get("MAX_BLOCK_RANGE", str(MAX_BLOCK_RANGE))) - 1)
    if start <= end:
        for pid, slot in seated(rpc, panels, key, start, end).items():
            if (seats.get(pid) or {}).get("slot") != slot:
                seats[pid] = {"slot": slot}  # a new seat, or another slot on a listed panel: its own starts
        if draw_on:
            for cid in opened(rpc, race, start, end):
                draws.setdefault(cid, {})
        last = end

    # What each needs, from Panels' views in the chain's time.
    t = now()
    lead = int(env.get("REVEAL_LEAD_SECONDS", "180"))
    result = {"action": "idle", "to": last}
    due, dropped, kinds, seal_left = {}, {}, {}, None
    clock = []

    def chain_time() -> int:  # read once a run, and only when a seat or a check needs it
        if not clock:
            clock.append(chain_now(rpc))
        return clock[0]

    if seats:
        chain_t = chain_time()
        for pid in sorted(seats):
            p = panel(rpc, panels, pid)
            what = phase(p, seat(rpc, panels, pid, seats[pid]["slot"]), key, chain_t, lead)
            if what in ("seal", "reveal"):
                due[pid] = what
                kinds[str(pid)] = KINDS[p["kind"]] if p["kind"] < len(KINDS) else str(p["kind"])
                if what == "seal":
                    left = p["sealBy"] - chain_t
                    seal_left = left if seal_left is None else min(seal_left, left)
            elif what != "wait":
                dropped[str(pid)] = what
                del seats[pid]
    for kind in ("seal", "reveal"):
        if any(v == kind for v in due.values()):
            result[kind] = sorted(pid for pid, v in due.items() if v == kind)
    if kinds:
        result["kinds"] = kinds
    if dropped:
        result["dropped"] = dropped
    if seal_left is not None:
        result["seal_left_s"] = seal_left
        if seal_left < int(env.get("READY_SECONDS", "120")):
            result["late"] = True  # less time left than a cold start takes: the node can't seal it from a stop

    # Which due seats may start the instance now (RETRY_MINUTES, SEAT_MAX_STARTS).
    retry = float(env.get("RETRY_MINUTES", "10")) * 60
    max_seat = int(env.get("SEAT_MAX_STARTS", "3"))
    asks, gave_up = [], []
    for pid, what in sorted(due.items()):
        at, n = seats[pid].get(what) or [0, 0]
        if n >= max_seat:
            gave_up.append(pid)
        elif t - at >= retry:
            asks.append((pid, what))
    if gave_up:
        result["gave_up"] = gave_up

    # The draw duty: the listed checks that may be due now, read in turn from the cursor.
    draw_due, cursor = [], state.get("dcur", 0)
    if draw_on and draws:
        draw_due, cursor = _draw_duty(env, rpc, panels, key, draws, head, chain_time, t, retry, cursor, result)

    # The Radicle duty: Heads.head moved since the last run.
    head_now, head_seen = None, state.get("head")
    if env.get("WAKE_ON_HEAD", "false").lower() == "true" and env.get("RACE_ADDRESS"):
        head_now = head_of(rpc, env["RACE_ADDRESS"])
        if head_seen is None:
            head_seen = head_now  # the first run: recorded, nothing to push for
    head_due = head_now is not None and head_now != head_seen
    if head_due:
        result["head"] = head_now[:40]

    day = time.strftime("%Y-%m-%d", time.gmtime(t))
    fuse = state.get("fuse") or {}
    starts_today = int(fuse.get("starts", 0)) if fuse.get("day") == day else 0
    max_day = int(env.get("MAX_STARTS_PER_DAY") or 0)
    unpause = env.get("UNPAUSE_CHECK", "daily").lower() == "daily" and state.get("unpause") != day

    if asks or unpause or head_due or draw_due:
        instance = env["INSTANCE_ID"]
        current = ec2.describe_instances(InstanceIds=[instance])["Reservations"][0]["Instances"][0]["State"]["Name"]
        if current in GOING_DOWN:
            result["action"] = current
            return result  # nothing saved: the same seats and blocks next minute
        why, started = None, False
        if current != "stopped":
            result["action"] = current  # running or pending: the node there takes the seats (and checks its pause)
            if unpause:
                state["unpause"] = day
            if head_due:
                head_seen = head_now  # the running node pushes it
        else:
            cap = capacity(rpc, panels, key)
            if cap["checks"] == 0:  # the spend pause: seal work waits, a reveal doesn't
                held = [pid for pid, what in asks if what == "seal"]
                if held:
                    result["paused"] = held
                    result["action"] = "paused"
                asks = [(pid, what) for pid, what in asks if what != "seal"]
            if asks:
                why = "work"
            elif head_due:
                why = "head"  # the Radicle duty: no model call, so the pause doesn't hold it
            elif draw_due:
                why = "draw"  # the draw duty: no model call either
            elif unpause and cap["checks"] == 0 and cap["next"] == 0:
                why = "unpause-check"  # paused with nothing pending: the node may restore it
            elif unpause:
                state["unpause"] = day  # not paused (or a change already pending): nothing to check today
            if why and max_day and starts_today >= max_day:
                result["action"] = "fuse"
                result["fuse"] = {"day": day, "starts": starts_today, "max": max_day}
                why = None
            if why and env.get("BUDGET_NAME") and budgets is not None:
                if budget_reached(budgets(), env["ACCOUNT_ID"], env["BUDGET_NAME"]):
                    result["action"] = "budget"  # the budget's stop holds: no start undoes it
                    why = None
            if why:
                ec2.start_instances(InstanceIds=[instance])
                starts_today += 1
                started = True
                result["action"] = "started"
                if head_due:
                    head_seen = head_now  # this start pushes it (a seat's start does too)
                    if why == "head":
                        result["radicle"] = True
                if why == "unpause-check":
                    result["unpause-check"] = True
                    state["unpause"] = day
                for cid in draw_due:  # this start draws them (any start does: the node's keeper draws)
                    draws[cid]["n"] = draws[cid].get("n", 0) + 1
                    draws[cid]["s"] = t
        if current != "stopped" or started:
            for pid, what in asks:  # asked: this seat's next start waits RETRY_MINUTES
                at, n = seats[pid].get(what) or [0, 0]
                seats[pid][what] = [t, n + int(started)]

    # Saved only after the start was asked for, so a failed start retries next minute.
    new = {"last": last}
    if seats:
        new["seats"] = {str(pid): v for pid, v in sorted(seats.items())}
    if draws:
        new["draws"] = {str(cid): v for cid, v in sorted(draws.items())}
    if draw_on and cursor:
        new["dcur"] = cursor
    if starts_today:
        new["fuse"] = {"day": day, "starts": starts_today}
    if state.get("unpause"):
        new["unpause"] = state["unpause"]
    if head_seen is not None:
        new["head"] = head_seen  # a move the fuse or the budget held stays unseen: tried again next run
    if _fit(new):
        result["state-full"] = True
    ssm.put_parameter(Name=param, Value=json.dumps(new, sort_keys=True, separators=(",", ":")), Type="String",
                      Overwrite=True)
    return result


def _draw_duty(env: dict, rpc, panels: str, key: str, draws: dict, head: int, chain_time, t: float, retry: float,
               cursor: int, result: dict) -> tuple:
    """Reads the verdicts of the listed checks that may be due (at most DRAW_READS_MAX, from `cursor` on), updates
    `draws` in place and returns (the due checks with starts left, the new cursor). An undrawn check's entry is its
    round: `g` its released rounds (`redraws`, left out at 0) with `b` the seed block (SEALED) or `r` the retry time
    (WAITING) last read; then `at` when this watcher first saw it past its grace, `n` the starts for that round, `s`
    the last one's time, `x` once given up for that round and `c` when it was last read since. A drawn check's entry
    is `d` (drawn), `g` and `c` (VP23): kept until final, read every RETRY_MINUTES for a round released back to
    waiting, which is a new round with its own starts."""
    grace = int(env.get("DRAW_GRACE_BLOCKS", "25"))
    minutes = float(env.get("DRAW_STAGGER_MINUTES", "10"))
    max_starts = int(env.get("DRAW_MAX_STARTS", "1"))
    reads_max = int(env.get("DRAW_READS_MAX", "20"))

    def may_be_due(cid: int, d: dict) -> bool:
        if "d" in d or d.get("n", 0) >= max_starts:
            # drawn, or started for this round: read again every RETRY_MINUTES, for a drawn check's end or a new round
            return t - max(d.get("s", 0), d.get("c", 0)) >= retry
        if "b" in d:
            if head <= d["b"] + grace:
                return False
            return "at" not in d or chain_time() >= d["at"] + stagger(key, cid, minutes)
        if "r" in d:
            return chain_time() > d["r"] + grace * BLOCK_SECONDS + stagger(key, cid, minutes)
        return True  # never read

    ids = sorted(draws)
    ids = [c for c in ids if c > cursor] + [c for c in ids if c <= cursor]  # in turn
    due, dropped, drawn, gave_up, reads = [], {}, [], [], 0
    for cid in ids:
        d = draws[cid]
        if not may_be_due(cid, d):
            continue
        if reads >= reads_max:
            result["draw_reads_max"] = True  # the rest next run
            break
        v = verdict(rpc, panels, cid)
        reads += 1
        cursor = cid
        status, rounds = v["status"], v["redraws"]
        rnd = {"g": rounds} if rounds else {}
        if status not in (SEALED, WAITING):
            name = STATUSES[status] if status < len(STATUSES) else str(status)
            if name in DRAWN:  # drawn: watched until final, for a round released back to waiting (VP23)
                if "d" not in d:
                    drawn.append(cid)
                draws[cid] = {"d": 1, **rnd, "c": t}
                continue
            dropped[str(cid)] = name  # final, released (refunded), withdrawn or expired: nothing more to wake for
            del draws[cid]
            continue
        mark = ("b", v["seedBlock"]) if status == SEALED else ("r", v["retryAt"])
        if "d" in d or d.get(mark[0]) != mark[1] or d.get("g", 0) != rounds:
            d = draws[cid] = {**rnd, mark[0]: mark[1]}  # a new round, seed block or retry time: its own starts
        if status == SEALED:
            if head <= d["b"] + grace:
                continue
            d.setdefault("at", chain_time())  # past its grace: this validator's stagger counts from now
            ready = chain_time() >= d["at"] + stagger(key, cid, minutes)
        else:
            ready = chain_time() > d["r"] + grace * BLOCK_SECONDS + stagger(key, cid, minutes)
        if not ready:
            continue
        if d.get("n", 0) >= max_starts:
            if not d.get("x"):
                gave_up.append(cid)  # started for it, and still undrawn RETRY_MINUTES later: another host's turn
                d["x"] = 1  # listed still: a new round (re-targeted, released, waiting again) is due again
            d["c"] = t
        else:
            due.append(cid)
    if due:
        result["draw"] = sorted(due)
    if drawn:
        result["draw_drawn"] = sorted(drawn)
    if dropped:
        result["draw_dropped"] = dropped
    if gave_up:
        result["draw_gave_up"] = sorted(gave_up)
    return due, cursor


def rpc_from_env(env: dict, secretsmanager) -> Rpc:
    """The chain's client: the URL from RPC_URL_SECRET_ARN's secret or RPC_URL, and RPC_API_KEY_SECRET_ARN's key in a
    header. `secretsmanager` is a factory, called only when a secret is named. Neither value is ever logged."""
    url = env.get("RPC_URL", "")
    key = None
    if env.get("RPC_URL_SECRET_ARN"):
        url = secretsmanager().get_secret_value(SecretId=env["RPC_URL_SECRET_ARN"])["SecretString"].strip()
    if env.get("RPC_API_KEY_SECRET_ARN"):
        key = secretsmanager().get_secret_value(SecretId=env["RPC_API_KEY_SECRET_ARN"])["SecretString"].strip()
    REDACT.add(url)  # before anything can print it
    REDACT.add(key)
    if key and ":" in key:
        REDACT.add(key.split(":", 1)[1])  # a Basic "<handle>:<key>": the key part alone too
    if not url.startswith(("https://", "http://")):
        raise RuntimeError("no chain URL: set RPC_URL, or RPC_URL_SECRET_ARN to a secret holding it")
    return Rpc(url, key or None, env.get("RPC_API_KEY_HEADER", "Basic"))


def main(env: dict, client) -> dict:
    """One invocation: `client(name)` makes a boto3 client. Every line it prints passes through the redactor; a
    failure is logged with its traceback, redacted, and raised again with a redacted message only (the Lambda runtime
    prints an uncaught exception's message and traceback as they are)."""
    if env.get("ENABLED", "false").lower() != "true":
        result = {"action": "disabled"}  # the kill switch: no secret read, no chain call
        log(json.dumps(result))
        return result
    try:
        rpc = rpc_from_env(env, lambda: client("secretsmanager"))
        result = run(env, rpc, client("ssm"), client("ec2"), lambda: client("budgets"))
    except Exception as e:
        log(json.dumps({"action": "failed", "error": f"{type(e).__name__}: {e}"}))
        log(traceback.format_exc())
        raise RuntimeError(REDACT(f"{type(e).__name__}: {e}")) from None
    log(json.dumps(result, sort_keys=True))
    return result


def handler(event, context):  # pragma: no cover - the Lambda entry point; main() is what's tested
    import boto3

    return main(dict(os.environ), boto3.client)
