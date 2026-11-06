"""The validator's watcher (proof-of-fix#104): runs every minute in the validator's own AWS account, looks for work on
the chain for this validator's seat, and starts the validator's stopped node instance only when there is some. The
instance checks the work and stops itself when idle, so the validator pays for compute only while checking.

Work is:
- a sealed submission (RaceV2's `Committed`) still waiting for its result, for which `Verdicts.drawn` names this seat
  among its 3 judges (a recused seat isn't named);
- a bounty won by a submission this seat judged (`StateChanged` to Won): its merge is signed by the same judges once
  the pull request merges on the host, which the chain doesn't see. While such a bounty stays Won, the node is
  started again every MERGE_POLL_MINUTES.

Past blocks aren't the end of a draw (#166). A node can stop without finishing one (the chain or the host away for too
long, a crash, or the instance on its way down when the work appeared), and nothing on the instance reports back, so
a drawn submission stays on the watcher's list while it waits for its result: every PENDING_POLL_MINUTES the node is
started again, at most PENDING_MAX_STARTS times. Those starts are cheap: a node that already judged it (its usage report
is on-chain) sits the round out without a model call (oracle/node_v2.py). If the chain is down the watcher fails before
it touches its state, so an outage spends no starts. Keep PENDING_POLL_MINUTES x PENDING_MAX_STARTS within the node's scan
(`oracle run` looks back 5000 blocks: under 3 hours at 2-second blocks).

Environment (set by the Terraform module):
    RPC_URL                  the chain's JSON-RPC URL (HTTPS)
    RPC_API_KEY_SECRET_ARN   optional: the Secrets Manager secret holding the chain's per-engineer API key
    RPC_API_KEY_HEADER       how the key is sent: "Basic" (a "<handle>:<key>" secret as HTTP Basic, the demo chain's;
                             the default), "Authorization" (Bearer) or another header's name (the raw key)
    RACE_ADDRESS             the Race contract (RaceV2 from the deployment record); Verdicts is read from it
    SEAT_ADDRESS             this validator's key's public address: the node starts only for its draws
    INSTANCE_ID              the validator's node instance, kept stopped while idle
    STATE_PARAM              the SSM parameter holding the scan's state (the last block, the bounties awaiting a merge)
    ENABLED                  "true" or anything else: the kill switch
    MAX_BLOCK_RANGE          the most blocks scanned per run (default 2000)
    MERGE_POLL_MINUTES       how often a won bounty this seat judged starts the node, until it's merged (default 30)
    PENDING_POLL_MINUTES     how often a draw still waiting for its result starts the node again (default 30)
    PENDING_MAX_STARTS       how many times a draw may start a stopped node before the watcher gives up on it (default 4)
    MAX_STARTS_PER_DAY       the operator's fuse: the most times the watcher starts the node in a UTC day (0 or unset: no
                             limit). With the node's limits per run, it bounds a day's spending. Past it the work stays on
                             the list for the next day, and a round that ends first is missed.

Standard library plus boto3 (in the Lambda runtime). The handler takes its AWS clients and RPC as arguments so the
tests run with fakes on Python 3.9, with no network. The ABI here is the few calls it makes, with their selectors
(tests check them against keccak256 of the signatures).
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.request

# keccak256 of RaceV2's events (tests check them).
COMMITTED_TOPIC = "0xcd9df6a82c34f68eed4318bab0efcf9f030dc959a4816e2036305dd1125031c2"  # Committed(uint256,uint256,address)
STATE_CHANGED_TOPIC = "0xfafe884515ca1fa5e0bf815ce87ef00b2cdaa0eee590d20376604937937a10bf"  # StateChanged(uint256,uint8)
# Function selectors (tests check them).
VERDICTS = "0x81fa0f24"  # verdicts()
SUBMISSION = "0x9c8c701b"  # submission(uint256): 12 static words, outcome at 6, seed at 11
BOUNTY = "0x227882d6"  # bounty(uint256): 14 static words, state at 1, winner at 8
DRAWN = "0x2d53b057"  # drawn(bytes32,uint256,uint256,address) -> (address[] judges, address[] recused)
WON = 2
DEFAULT_LOOKBACK = 100
GOING_DOWN = ("stopping", "shutting-down")  # an instance in these states can't start, and its node has already exited


class Rpc:
    """A minimal JSON-RPC client; the chain's API key goes in a header, never in the URL or the logs."""

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
        with urllib.request.urlopen(req, timeout=20) as resp:
            reply = json.loads(resp.read())
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
    return "0x" + word[-40:]


def verdicts_of(rpc, race: str) -> str:
    return _address(eth_call(rpc, race, VERDICTS)[0])


def drawn_judges(rpc, verdicts: str, race: str, seed: str, bounty: int, submission: int) -> list:
    """Verdicts.drawn(seed, bounty, submission, race)'s judges (a recused key isn't one), lower-case."""
    w = eth_call(rpc, verdicts, DRAWN, seed, bounty, submission, race)
    start = int(w[0], 16) // 32  # the first array's offset
    n = int(w[start], 16)
    return [_address(x).lower() for x in w[start + 1:start + 1 + n]]


def seat_drawn(rpc, race: str, verdicts: str, seat: str, submission: int, bounty: int) -> tuple:
    """(whether `seat` is among the submission's drawn judges, whether the submission still waits for its result)."""
    s = eth_call(rpc, race, SUBMISSION, submission)
    waiting = int(s[6], 16) == 0
    judges = drawn_judges(rpc, verdicts, race, "0x" + s[11], bounty, submission)
    return seat.lower() in judges, waiting


# ---------- the scan ----------

def committed(rpc, race: str, from_block: int, to_block: int) -> list[dict]:
    """The submissions sealed in [from_block, to_block]."""
    logs = rpc.call("eth_getLogs", [{"address": race, "topics": [COMMITTED_TOPIC],
                                     "fromBlock": hex(from_block), "toBlock": hex(to_block)}])
    return [{"bounty": int(log["topics"][1], 16), "submission": int(log["topics"][2], 16),
             "solver": "0x" + log["topics"][3][-40:], "block": int(log["blockNumber"], 16)} for log in logs]


def won(rpc, race: str, from_block: int, to_block: int) -> list:
    """The bounties won in [from_block, to_block]."""
    logs = rpc.call("eth_getLogs", [{"address": race, "topics": [STATE_CHANGED_TOPIC],
                                     "fromBlock": hex(from_block), "toBlock": hex(to_block)}])
    return [int(log["topics"][1], 16) for log in logs if int(log["data"], 16) == WON]


def scan(rpc, race: str, seat: str, last: int | None, max_range: int) -> tuple:
    """The submissions this seat must judge since the last scanned block, the bounties won since by a submission it
    judged, and the new last block. A first run looks back DEFAULT_LOOKBACK blocks."""
    head = int(rpc.call("eth_blockNumber", []), 16)
    start = max(head - DEFAULT_LOOKBACK, 0) if last is None else last + 1
    if start > head:
        return [], [], head if last is None else last
    end = min(head, start + max_range - 1)
    sealed = committed(rpc, race, start, end)
    wins = won(rpc, race, start, end)
    if not (sealed or wins):
        return [], [], end
    if not seat:
        raise RuntimeError("SEAT_ADDRESS isn't set: the watcher can't tell this seat's draws")
    verdicts = verdicts_of(rpc, race)
    work = []
    for s in sealed:
        mine, waiting = seat_drawn(rpc, race, verdicts, seat, s["submission"], s["bounty"])
        if mine and waiting:
            work.append(s)
    awaiting = []
    for b in wins:
        winner = int(eth_call(rpc, race, BOUNTY, b)[8], 16)
        if seat_drawn(rpc, race, verdicts, seat, winner, b)[0]:
            awaiting.append(b)
    return work, awaiting, end


def still_won(rpc, race: str, bounty: int) -> bool:
    return int(eth_call(rpc, race, BOUNTY, bounty)[1], 16) == WON


def still_waiting(rpc, race: str, submission: int) -> bool:
    return int(eth_call(rpc, race, SUBMISSION, submission)[6], 16) == 0


def ensure_running(ec2, instance_id: str, may_start: bool = True) -> str:
    """Start the node instance if it is stopped and the day's fuse allows it; leave it alone if it is starting or running."""
    state = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"][0]["Instances"][0]["State"]["Name"]
    if state == "stopped":
        if not may_start:
            return "fuse"
        ec2.start_instances(InstanceIds=[instance_id])
        return "started"
    return state


def _load_state(raw: str) -> tuple:
    """The parameter's value: {"last": n|null, "awaiting": {bounty: last start}, "pending": {submission: {"started": last
    ask, "starts": stopped node started}}, "fuse": {"day": UTC day, "starts": node started that day}}, or a plain block
    number when none of those has anything in it."""
    if raw == "none":
        return None, {}, {}, {}
    if raw.lstrip().startswith("{"):
        d = json.loads(raw)
        return (d.get("last"), {int(k): float(v) for k, v in (d.get("awaiting") or {}).items()},
                {int(k): dict(v) for k, v in (d.get("pending") or {}).items()}, dict(d.get("fuse") or {}))
    return int(raw), {}, {}, {}


def run(env: dict, rpc, ssm, ec2, now=time.time) -> dict:
    if env.get("ENABLED", "false").lower() != "true":
        return {"action": "disabled"}
    param = env["STATE_PARAM"]
    try:
        last, awaiting, pending, fuse = _load_state(ssm.get_parameter(Name=param)["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        last, awaiting, pending, fuse = None, {}, {}, {}
    race = env["RACE_ADDRESS"]
    work, wins, new_last = scan(rpc, race, env.get("SEAT_ADDRESS", ""), last, int(env.get("MAX_BLOCK_RANGE", "2000")))
    t = now()
    day = time.strftime("%Y-%m-%d", time.gmtime(t))
    starts_today = int(fuse.get("starts", 0)) if fuse.get("day") == day else 0
    max_starts_today = int(env.get("MAX_STARTS_PER_DAY") or 0)
    poll = float(env.get("MERGE_POLL_MINUTES", "30")) * 60
    for b in wins:
        awaiting.setdefault(b, 0.0)
    merges = []
    for b in sorted(awaiting):
        if not still_won(rpc, race, b):
            del awaiting[b]  # merged (or reopened): nothing more to sign for it
        elif t - awaiting[b] >= poll:
            merges.append(b)
    result = {"action": "idle", "from": last, "to": new_last, "submissions": [w["submission"] for w in work]}
    if merges:
        result["merges"] = merges
    for w in work:
        pending.setdefault(w["submission"], {"started": 0.0, "starts": 0})
    pending_poll = float(env.get("PENDING_POLL_MINUTES", "30")) * 60
    max_starts = int(env.get("PENDING_MAX_STARTS", "4"))
    again, gave_up = [], []
    for s in sorted(pending):
        if not still_waiting(rpc, race, s):
            del pending[s]  # decided: nothing more to do for it
        elif t - pending[s]["started"] >= pending_poll:
            if pending[s]["starts"] >= max_starts:
                del pending[s]
                gave_up.append(s)
            else:
                again.append(s)
    if gave_up:
        result["gave_up"] = gave_up  # still undecided after every start allowed: for the operator's logs
    retries = [s for s in again if s not in result["submissions"]]
    if retries:
        result["retries"] = retries
    if work or merges or again:
        result["action"] = ensure_running(ec2, env["INSTANCE_ID"], not max_starts_today or starts_today < max_starts_today)
        if max_starts_today and result["action"] == "started":
            starts_today += 1
        if result["action"] == "fuse":
            result["fuse"] = {"day": day, "starts": starts_today, "max": max_starts_today}  # for the operator's logs
        if result["action"] in GOING_DOWN:
            return result  # it can't be started yet and it won't see this work: nothing saved, the same blocks next minute
        for b in merges:
            awaiting[b] = t
        for s in again:
            pending[s]["started"] = t
            pending[s]["starts"] += int(result["action"] == "started")
    # Saved only after the instance was asked to start, so a failed start retries the same blocks next minute.
    state = {"last": new_last}
    if awaiting:
        state["awaiting"] = awaiting
    if pending:
        state["pending"] = pending
    if starts_today:
        state["fuse"] = {"day": day, "starts": starts_today}
    value = str(new_last) if len(state) == 1 else json.dumps(state, sort_keys=True)
    ssm.put_parameter(Name=param, Value=value, Type="String", Overwrite=True)
    return result


def handler(event, context):  # pragma: no cover - the Lambda entry point; run() is what the tests cover
    import boto3

    env = dict(os.environ)
    api_key = None
    if env.get("RPC_API_KEY_SECRET_ARN"):
        api_key = boto3.client("secretsmanager").get_secret_value(SecretId=env["RPC_API_KEY_SECRET_ARN"])["SecretString"]
    rpc = Rpc(env["RPC_URL"], api_key, env.get("RPC_API_KEY_HEADER", "Basic"))
    result = run(env, rpc, boto3.client("ssm"), boto3.client("ec2"))
    print(json.dumps(result))
    return result
