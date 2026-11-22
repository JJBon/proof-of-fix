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
- reveal due: the seat sealed but hasn't revealed with its receipt, `revealBy` hasn't passed, and the reveal window is
  open or opens within REVEAL_LEAD_SECONDS (it opens after `sealBy` once every seat sealed; a shadow's on its own);
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
    MAX_BLOCK_RANGE         the most blocks scanned per run (default 2000)
    LOOKBACK_BLOCKS         a first run's look back (default 1200: 4 h of Sepolia's 12-second blocks, past a production
                            seal and reveal window)
    MAX_STARTS_PER_DAY      the fuse (default 0: none; the kit sets 12)
    RETRY_MINUTES           how often a seat still due starts a stopped instance again (default 10)
    SEAT_MAX_STARTS         the most starts for one seat and phase (default 3)
    REVEAL_LEAD_SECONDS     how long before a sealed seat's reveal window opens the instance is started (default 180)
    READY_SECONDS           a cold start's time to a node that can seal, for the `late` flag (default 120)
    UNPAUSE_CHECK           "daily" (default) or "off"
    WAKE_ON_HEAD            "true": the Radicle duty above (needs RACE_ADDRESS); default "false"
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
import urllib.request

# keccak256 of Panels' event and its views' selectors (the tests check them).
SEATED_TOPIC = "0x02e6050fc1d4cc5be0a22ce14752a944691c128f452ba26c46898e3f23bd196f"  # Seated(uint256,uint256,address,uint256)
CONTRACTS = "0x6c0f79b6"  # RaceV3.contracts(): (panels, fees, pool, registry, heads, coin, start)
PANEL = "0xaa07bd09"  # panel(uint256): 20 static words (Panel with its Snap)
SEAT = "0x3389fe48"  # seat(uint256,uint256): 9 static words
CAPACITY = "0x5694c2da"  # capacity(address) -> (checks, next, from, room)
REPO = "0x56ff3122"  # RaceV3.repo(): the deployment's one repository, keccak256 of its RID
HEAD = "0xf339e3b2"  # Heads.head(bytes32) -> Head (commit, constitution, movedAt, bounty, submission, verdict)
# Panel's words: id 0, seed 1, sealBy 2, revealBy 3, counter 4, k 5, seats 6, nSealed 7, done 8, passes 9, level 10,
# counted 11, kind 12, closed 13, scored 14, ex 15, snap 16-19. Seat's: key 0, level 1, hasSeal 2, revealed 3,
# receipted 4, vote 5, mask 6, seal 7, receipt 8.
KINDS = ("counted", "shadow", "audit", "challenge")
SHADOW = 1
GOING_DOWN = ("stopping", "shutting-down")  # can't start yet; the node in it has already exited
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
STATE_LIMIT = 3800  # characters of the 4 KB parameter; past it the oldest seats are dropped (`state-full`)


class Rpc:
    """A minimal JSON-RPC client. A key goes in a header or in a URL read from a secret, and never in the logs: a
    failed call names its method and the error's type only, never the URL."""

    def __init__(self, url: str, api_key: str | None = None, header: str = "Basic"):
        self.url, self.api_key, self.header = url, api_key, header

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
        except Exception as e:  # the URL may hold the key: not in the message
            raise RuntimeError(f"{method}: the chain didn't answer ({type(e).__name__})") from None
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
    full = p["kind"] == SHADOW or (p["seats"] == p["k"] and p["nSealed"] == p["k"])
    return "reveal" if full and now >= p["sealBy"] - lead else "wait"


def _load(raw: str) -> dict:
    if not raw or raw == "none":
        return {}
    return json.loads(raw) if raw.lstrip().startswith("{") else {"last": int(raw)}


def _fit(state: dict, limit: int = STATE_LIMIT) -> bool:
    """Keeps the state within the parameter: drops the oldest seats (lowest panel id) first. Whether it dropped any."""
    full = False
    while len(json.dumps(state, sort_keys=True, separators=(",", ":"))) > limit and state.get("seats"):
        del state["seats"][min(state["seats"], key=int)]
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
    last = state.get("last")

    # The new seats since the last block scanned.
    head = int(rpc.call("eth_blockNumber", []), 16)
    start = max(head - int(env.get("LOOKBACK_BLOCKS", "1200")), 0) if last is None else last + 1
    end = min(head, start + int(env.get("MAX_BLOCK_RANGE", "2000")) - 1)
    if start <= end:
        for pid, slot in seated(rpc, panels, key, start, end).items():
            seats.setdefault(pid, {})["slot"] = slot
        last = end

    # What each needs, from Panels' views in the chain's time.
    t = now()
    lead = int(env.get("REVEAL_LEAD_SECONDS", "180"))
    result = {"action": "idle", "to": last}
    due, dropped, kinds, seal_left = {}, {}, {}, None
    if seats:
        chain_t = chain_now(rpc)
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

    if asks or unpause or head_due:
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
        if current != "stopped" or started:
            for pid, what in asks:  # asked: this seat's next start waits RETRY_MINUTES
                at, n = seats[pid].get(what) or [0, 0]
                seats[pid][what] = [t, n + int(started)]

    # Saved only after the start was asked for, so a failed start retries next minute.
    new = {"last": last}
    if seats:
        new["seats"] = {str(pid): v for pid, v in sorted(seats.items())}
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


def rpc_from_env(env: dict, secretsmanager) -> Rpc:
    """The chain's client: the URL from RPC_URL_SECRET_ARN's secret or RPC_URL, and RPC_API_KEY_SECRET_ARN's key in a
    header. `secretsmanager` is a factory, called only when a secret is named. Neither value is ever logged."""
    url = env.get("RPC_URL", "")
    key = None
    if env.get("RPC_URL_SECRET_ARN"):
        url = secretsmanager().get_secret_value(SecretId=env["RPC_URL_SECRET_ARN"])["SecretString"].strip()
    if env.get("RPC_API_KEY_SECRET_ARN"):
        key = secretsmanager().get_secret_value(SecretId=env["RPC_API_KEY_SECRET_ARN"])["SecretString"].strip()
    if not url.startswith(("https://", "http://")):
        raise RuntimeError("no chain URL: set RPC_URL, or RPC_URL_SECRET_ARN to a secret holding it")
    return Rpc(url, key or None, env.get("RPC_API_KEY_HEADER", "Basic"))


def handler(event, context):  # pragma: no cover - the Lambda entry point; run() and rpc_from_env() are what's tested
    import boto3

    env = dict(os.environ)
    if env.get("ENABLED", "false").lower() != "true":
        result = {"action": "disabled"}  # the kill switch: no secret read, no chain call
        print(json.dumps(result))
        return result
    rpc = rpc_from_env(env, lambda: boto3.client("secretsmanager"))
    result = run(env, rpc, boto3.client("ssm"), boto3.client("ec2"), lambda: boto3.client("budgets"))
    print(json.dumps(result, sort_keys=True))
    return result
