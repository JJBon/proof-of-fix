"""The validator's watcher (proof-of-fix#104): runs every minute in the validator's own AWS account, looks for work on
the chain for this validator's seat, and starts the validator's stopped node instance only when there is some. The
instance checks the work and stops itself when idle, so the validator pays for compute only while checking.

The same code is the AWS devnet's seats host's watcher (proof-of-fix#152, infra#219): one instance running several
seats' nodes (SEAT_ADDRESSES: work for any of them is work), and later the bot service (#210) beside them (BOT_WORK).

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

Environment (set by the Terraform module: the kit's, or platform's `pof_seats`):
    RPC_URL                  the chain's JSON-RPC URL (HTTPS)
    RPC_API_KEY_SECRET_ARN   optional: the Secrets Manager secret holding the chain's per-engineer API key (the kit's)
    RPC_API_KEY_PARAM        optional: an SSM SecureString parameter holding it instead (the seats host's,
                             /pof-seats/watcher/rpc-auth), read with decryption once per run. With both, this one
    RPC_API_KEY_HEADER       how the key is sent: "Basic" (a "<handle>:<key>" secret as HTTP Basic, the demo chain's;
                             the default), "Authorization" (Bearer) or another header's name (the raw key)
    RACE_ADDRESS             the Race contract (RaceV2 from the deployment record); Verdicts is read from it
    SEAT_ADDRESS             this validator's key's public address: the node starts only for its draws
    SEAT_ADDRESSES           several seats served by one instance (comma- or space-separated; the seats host's six):
                             a draw or a won bounty of any of them is work. Takes the place of SEAT_ADDRESS when set
    INSTANCE_ID              the validator's node instance (or the seats host), kept stopped while idle
    STATE_PARAM              the SSM parameter holding the scan's state (the last block, the bounties awaiting a merge)
    ENABLED                  "true" or anything else: the kill switch
    MAX_BLOCK_RANGE          the most blocks scanned per run (default 2000)
    MERGE_POLL_MINUTES       how often a won bounty this seat judged starts the node, until it's merged (default 30)
    PENDING_POLL_MINUTES     how often a draw still waiting for its result starts the node again (default 30)
    PENDING_MAX_STARTS       how many times a draw may start a stopped node before the watcher gives up on it (default 4)
    MAX_STARTS_PER_DAY       the operator's fuse: the most times the watcher starts the node in a UTC day (0 or unset: no
                             limit). With the node's limits per run, it bounds a day's spending. Past it the work stays on
                             the list for the next day, and a round that ends first is missed.
    BOT_WORK                 "true": also start the instance for the bot service's work and the seats' registration
                             check (#210; the seats host). Off by default, so the kit's watcher is unchanged
    BOT_ENABLED              the bot's own switch (default on): "false" turns the bot's work off, without touching the
                             seats' (their registration check still starts the instance)
    BOT_REPO_IDS, DUE_POLL_MINUTES
                             the bot's work's settings, read by bot_work() (#210's spec, proof-of-fix PR #211, D8): the
                             record's repository ids, and how often something due (a settle, timeOut, mergeExpired or
                             sunset) starts the instance again while it stays due. The bot's work shares
                             PENDING_POLL_MINUTES, PENDING_MAX_STARTS and the day's fuse with the seats'

The bot's work is read from the chain only, with the watcher's own API key (no forge token, no signing key):
bot_work() below, D8 of #210's design (tests/test_watcher_bot_work.py).

Standard library plus boto3 (in the Lambda runtime). The handler takes its AWS clients and RPC as arguments so the
tests run with fakes on Python 3.9, with no network. The ABI here is the few calls it makes, with their selectors
(tests check them against keccak256 of the signatures).
"""

from __future__ import annotations

import base64
import json
import os
import re
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


def _as_seats(seats) -> set:
    return {seats.lower()} if isinstance(seats, str) else {s.lower() for s in seats}


def seat_drawn(rpc, race: str, verdicts: str, seats, submission: int, bounty: int) -> tuple:
    """(whether one of `seats` (an address, or several) is among the submission's drawn judges, whether the submission
    still waits for its result)."""
    s = eth_call(rpc, race, SUBMISSION, submission)
    waiting = int(s[6], 16) == 0
    judges = drawn_judges(rpc, verdicts, race, "0x" + s[11], bounty, submission)
    return bool(_as_seats(seats) & set(judges)), waiting


ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def seats_of(env: dict) -> list:
    """The seats this watcher serves: SEAT_ADDRESSES (several) or SEAT_ADDRESS (the kit's one), lower-case. A malformed
    address fails the run: a typo must not quietly leave a seat without its starts."""
    raw = env.get("SEAT_ADDRESSES", "").strip() or env.get("SEAT_ADDRESS", "").strip()
    seats = [a for a in re.split(r"[\s,]+", raw) if a]
    bad = [a for a in seats if not ADDRESS.match(a)]
    if bad:
        raise ValueError(f"not an address in SEAT_ADDRESSES/SEAT_ADDRESS: {', '.join(bad)}")
    return sorted({a.lower() for a in seats})


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


def scan_start(head: int, last: int | None) -> int:
    """The first block a run scans: after the last one scanned, or DEFAULT_LOOKBACK blocks back on a first run."""
    return max(head - DEFAULT_LOOKBACK, 0) if last is None else last + 1


def scan(rpc, race: str, seat, last: int | None, max_range: int) -> tuple:
    """The submissions this seat (an address, or several: any of them) must judge since the last scanned block, the
    bounties won since by a submission it judged, and the new last block. A first run looks back DEFAULT_LOOKBACK
    blocks."""
    return scan_blocks(rpc, race, seat, last, max_range)[1:]


def scan_blocks(rpc, race: str, seat, last: int | None, max_range: int) -> tuple:
    """scan()'s, with the first block scanned in front: (start, work, wins, new last); start > new last when there
    was nothing new."""
    head = int(rpc.call("eth_blockNumber", []), 16)
    start = scan_start(head, last)
    if start > head:
        return start, [], [], head if last is None else last
    end = min(head, start + max_range - 1)
    sealed = committed(rpc, race, start, end)
    wins = won(rpc, race, start, end)
    if not (sealed or wins):
        return start, [], [], end
    if not seat:
        raise RuntimeError("SEAT_ADDRESS (or SEAT_ADDRESSES) isn't set: the watcher can't tell this seat's draws")
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
    return start, work, awaiting, end


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


# ---------- the bot service's work (#210) ----------

# #211's D8: what started the host, in the result line. A registration waiting for its check is the seats' work (their
# nodes check it), so it counts with BOT_ENABLED off; the rest is the bot's.
BOT_KINDS = ("registrations", "opened", "settle", "timeout", "merge-expired", "sunset", "ended")
SEATS_KINDS = ("registrations",)
DUE_KINDS = ("settle", "timeout", "merge-expired", "sunset")
REGISTERED_TOPIC = "0x6cd8594df6446610564bf1ea1e804402ea0006dc7b541d3a430d1ea0a62cffd4"  # Registered(uint256,address)
OPENED_TOPIC = "0xb477d225f2a05c93438fc00e2b6ecb9995e9207ce2dd07ea59aa3f0a5edec329"  # BountyOpened(uint256,uint256)
ISSUE = "0xcc872b66"  # issue(uint256): 7 static words, repo at 0, bounty at 5, state at 6
CONFIG = "0xc3f909d4"  # getConfig(): 18 static words, idleDays at 12, resultDays 13, instalments 17
DAY = "0x7b76ac91"  # day()
EARNED = "0x20af63a0"  # earned(uint256,uint256)
SUBMISSIONS_OF = "0x185da63e"  # submissionsOf(uint256) -> uint256[]
STATES = ("None", "Open", "Won", "Merged", "Paid", "Refunded", "Unsolved")
ENDED = ("Paid", "Unsolved", "Refunded")
POSTED = 1
BOT_STATE_LIMIT = 2500  # characters of the 4 KB parameter the bot's state may take; past it, the newest are dropped


def bot_work_on(env: dict) -> bool:
    """bot_work() runs only with BOT_WORK=true (the seats host with a bot image or the seats' registration check)."""
    return env.get("BOT_WORK", "false").lower() == "true"


def bot_enabled(env: dict) -> bool:
    """The bot's own switch: with "false", only SEATS_KINDS of bot_work()'s findings start the instance."""
    return env.get("BOT_ENABLED", "true").lower() != "false"


def repo_ids(env: dict) -> set:
    """BOT_REPO_IDS: the repositories' ids on-chain (comma- or space-separated bytes32; 0x0 for outside the registry)."""
    return {_word(r.lower()) for r in re.split(r"[\s,]+", env.get("BOT_REPO_IDS", "")) if r}


def _bot_logs(rpc, race: str, start: int, end: int) -> list:
    """The race's Registered, BountyOpened, Committed and StateChanged logs in [start, end], in order."""
    topics = [[REGISTERED_TOPIC, OPENED_TOPIC, COMMITTED_TOPIC, STATE_CHANGED_TOPIC]]
    return rpc.call("eth_getLogs", [{"address": race, "topics": topics, "fromBlock": hex(start), "toBlock": hex(end)}])


def due_now(day: int, cfg: dict, bounty: dict, waiting: int, earned: int) -> str | None:
    """The kind due for a bounty (D8's 3), from its view {"state", "idleSince", "next", "mergeBy"}, the length of its
    submission queue and the earned instalments of its award: settle, merge-expired, sunset, or None."""
    st = bounty["state"]
    if st == "Merged" and earned >= cfg["instalments"]:
        return "settle"
    if st == "Won" and day > bounty["mergeBy"]:
        return "merge-expired"
    if st == "Open" and bounty["next"] >= waiting and day >= bounty["idleSince"] + cfg["idleDays"]:
        return "sunset"
    return None


def fit_bot_state(state: dict, limit: int = BOT_STATE_LIMIT) -> tuple:
    """(the bot's state within `limit` characters, whether candidates were dropped: `state-full`). The oldest are kept;
    the bot rescans the chain whenever the host runs, so a dropped one is still handled then."""
    s = json.loads(json.dumps(state))
    full = False
    while len(json.dumps(s, separators=(",", ":"))) > limit:
        lists = [k for k in ("subs", "bounties") if s.get(k)]
        if lists:
            s[max(lists, key=lambda k: len(s[k]))].pop()
        elif s.get("due"):
            s["due"].pop(sorted(s["due"])[-1])
        elif s.get("regs"):
            s["regs"].pop(sorted(s["regs"], key=int)[-1])
        else:
            break
        full = True
    return s, full


def bot_work(env: dict, rpc, race: str, start: int, end: int, state: dict, now: float) -> tuple:
    """The bot service's work (#210, its spec proof-of-fix PR #211, D8): what in blocks [start, end] and in the bot's
    own `state` is due to start the host now. start > end when no new block came.

    Returns ({kind: [ids]} for the kinds in BOT_KINDS that are due, the bot's new state, with "full": true when it had
    to drop candidates). Reads only the chain, with the watcher's own API key; it raises when the chain fails, and then
    the run saves nothing, as a failed scan does.
    - registrations: a Registered issue in BOT_REPO_IDS still Posted with no bounty; every PENDING_POLL_MINUTES while
      that holds, at most PENDING_MAX_STARTS times (the chain can't show whether a forge issue claims it);
    - opened: a BountyOpened log (once);
    - settle, timeout, merge-expired, sunset: something due, re-checked with the views every run; every
      DUE_POLL_MINUTES while it stays due;
    - ended: a StateChanged to Paid, Unsolved or Refunded (once).
    The state keeps "regs" {issue: [last ask, asks]}, "bounties" and "subs" (the candidates that may fall due, oldest
    first) and "due" {"kind:id": last ask}."""
    wanted = repo_ids(env)
    regs = {int(k): list(v) for k, v in (state.get("regs") or {}).items()}
    bounties, subs = list(state.get("bounties") or []), list(state.get("subs") or [])
    asked = dict(state.get("due") or {})
    found = {k: [] for k in BOT_KINDS}
    if start <= end:
        for log in _bot_logs(rpc, race, start, end):
            topic, first = log["topics"][0], int(log["topics"][1], 16)
            if topic == REGISTERED_TOPIC:
                regs.setdefault(first, [0.0, 0])
            elif topic == OPENED_TOPIC:
                found["opened"].append(first)
                bounties += [first] if first not in bounties else []
            elif topic == COMMITTED_TOPIC:
                s = int(log["topics"][2], 16)
                subs += [s] if s and s not in subs else []
            elif topic == STATE_CHANGED_TOPIC:
                if STATES[int(log["data"], 16)] in ENDED:
                    found["ended"].append(first)
                    bounties = [b for b in bounties if b != first]
                elif first not in bounties:
                    bounties.append(first)
    pending_poll = float(env.get("PENDING_POLL_MINUTES", "30")) * 60
    max_asks = int(env.get("PENDING_MAX_STARTS", "4"))
    for n in sorted(regs):
        w = eth_call(rpc, race, ISSUE, n)
        if (int(w[6], 16) != POSTED or int(w[5], 16) != 0 or w[0] not in wanted):
            del regs[n]  # opened (or closed, or another repository's): nothing to wait for
        elif now - regs[n][0] >= pending_poll:
            if regs[n][1] >= max_asks:
                del regs[n]  # no forge issue claimed it in time: given up
            else:
                regs[n] = [now, regs[n][1] + 1]
                found["registrations"].append(n)
    due = []
    if bounties or subs:
        c = eth_call(rpc, race, CONFIG)
        cfg = {"idleDays": int(c[12], 16), "resultDays": int(c[13], 16), "instalments": int(c[17], 16)}
        day = int(eth_call(rpc, race, DAY)[0], 16)
        keep = []
        for b in bounties:
            w = eth_call(rpc, race, BOUNTY, b)
            view = {"state": STATES[int(w[1], 16)], "idleSince": int(w[5], 16), "next": int(w[7], 16),
                    "mergeBy": int(w[9], 16)}
            if view["state"] not in ("Open", "Won", "Merged"):
                continue  # ended (the bot sees it from its log) or never opened: dropped
            keep.append(b)
            waiting = int(eth_call(rpc, race, SUBMISSIONS_OF, b)[1], 16) if view["state"] == "Open" else 0
            earned = int(eth_call(rpc, race, EARNED, b, int(w[10], 16))[0], 16) if view["state"] == "Merged" else 0
            kind = due_now(day, cfg, view, waiting, earned)
            if kind:
                due.append((kind, b))
        bounties = keep
        keep = []
        for s in subs:
            w = eth_call(rpc, race, SUBMISSION, s)
            if int(w[6], 16) != 0:
                continue  # decided: dropped
            keep.append(s)
            if day >= int(w[1], 16) + cfg["resultDays"]:
                due.append(("timeout", s))
        subs = keep
    due_poll = float(env.get("DUE_POLL_MINUTES", "30")) * 60
    still = {f"{kind}:{i}" for kind, i in due}
    asked = {k: t for k, t in asked.items() if k in still}  # no longer due: forgotten
    for kind, i in due:
        key = f"{kind}:{i}"
        if now - asked.get(key, 0.0) >= due_poll:
            asked[key] = now
            found[kind].append(i)
    new = {}
    if regs:
        new["regs"] = {str(n): v for n, v in regs.items()}
    if bounties:
        new["bounties"] = bounties
    if subs:
        new["subs"] = subs
    if asked:
        new["due"] = asked
    new, full = fit_bot_state(new)
    if full:
        new["full"] = True
    return {k: sorted(set(v)) for k, v in found.items() if v}, new


def _load_state(raw: str) -> tuple:
    """The parameter's value: {"last": n|null, "awaiting": {bounty: last start}, "pending": {submission: {"started": last
    ask, "starts": stopped node started}}, "fuse": {"day": UTC day, "starts": node started that day}, "bot": bot_work()'s
    own state}, or a plain block number when none of those has anything in it."""
    if raw == "none":
        return None, {}, {}, {}, {}
    if raw.lstrip().startswith("{"):
        d = json.loads(raw)
        return (d.get("last"), {int(k): float(v) for k, v in (d.get("awaiting") or {}).items()},
                {int(k): dict(v) for k, v in (d.get("pending") or {}).items()}, dict(d.get("fuse") or {}),
                dict(d.get("bot") or {}))
    return int(raw), {}, {}, {}, {}


def run(env: dict, rpc, ssm, ec2, now=time.time, bot_check=None) -> dict:
    """One pass. `bot_check` stands in for bot_work() (the tests' fakes)."""
    if env.get("ENABLED", "false").lower() != "true":
        return {"action": "disabled"}
    param = env["STATE_PARAM"]
    try:
        last, awaiting, pending, fuse, bot_state = _load_state(ssm.get_parameter(Name=param)["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        last, awaiting, pending, fuse, bot_state = None, {}, {}, {}, {}
    race = env["RACE_ADDRESS"]
    start, work, wins, new_last = scan_blocks(rpc, race, seats_of(env), last, int(env.get("MAX_BLOCK_RANGE", "2000")))
    t = now()
    bot_due = {}
    if bot_work_on(env):
        # The same blocks as the seats' scan (none when start > new_last); a chain that fails here fails the run before
        # any state is touched.
        bot_due, bot_state = (bot_check or bot_work)(env, rpc, race, start, new_last, bot_state, t)
        kinds = BOT_KINDS if bot_enabled(env) else SEATS_KINDS
        bot_due = {k: list(v) for k, v in bot_due.items() if k in kinds and v}
        state_full = bool(bot_state.get("full"))
    else:
        bot_state, state_full = {}, False  # no bot work on this instance: nothing of it kept
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
    result.update(bot_due)  # which of the bot's work, by kind (#211's D8)
    if state_full:
        result["state-full"] = True  # the bot's candidates overflowed its share of the parameter: the oldest are kept
    if work or merges or again or bot_due:
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
    if bot_state:
        state["bot"] = bot_state
    value = str(new_last) if len(state) == 1 else json.dumps(state, sort_keys=True)
    ssm.put_parameter(Name=param, Value=value, Type="String", Overwrite=True)
    return result


def rpc_api_key(env: dict, ssm, secretsmanager) -> str | None:
    """The chain's API key, read once per run: from an SSM SecureString (RPC_API_KEY_PARAM, decrypted by this function's
    role alone: the seats host's) or a Secrets Manager secret (RPC_API_KEY_SECRET_ARN, the kit's). `secretsmanager` is
    a factory, so the seats host's watcher never creates that client. Never logged."""
    if env.get("RPC_API_KEY_PARAM"):
        value = ssm.get_parameter(Name=env["RPC_API_KEY_PARAM"], WithDecryption=True)["Parameter"]["Value"].strip()
        if not value:  # a pasted value can bring a line ending along; an empty one is an error, named, never shown
            raise RuntimeError("the chain's API key in RPC_API_KEY_PARAM is empty")
        return value
    if env.get("RPC_API_KEY_SECRET_ARN"):  # the kit's, read as it always was
        return secretsmanager().get_secret_value(SecretId=env["RPC_API_KEY_SECRET_ARN"])["SecretString"]
    return None


def handler(event, context):  # pragma: no cover - the Lambda entry point; run() and rpc_api_key() are what the tests cover
    import boto3

    env = dict(os.environ)
    if env.get("ENABLED", "false").lower() != "true":
        result = {"action": "disabled"}  # the kill switch: no key read, no chain call
        print(json.dumps(result))
        return result
    ssm = boto3.client("ssm")
    rpc = Rpc(env["RPC_URL"], rpc_api_key(env, ssm, lambda: boto3.client("secretsmanager")),
              env.get("RPC_API_KEY_HEADER", "Basic"))
    result = run(env, rpc, ssm, boto3.client("ec2"))
    print(json.dumps(result))
    return result
