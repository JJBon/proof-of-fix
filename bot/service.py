"""The bounty bot as a service (proof-of-fix#210): `pofctl bot watch`. It does a bounty's role-free steps on the devnet
with nobody typing commands, and nothing else (design D1):

1. settle a bounty whose outcome is final (`settle`, for the race's coin, then any other fee coin whose pot holds
   something);
2. the contract's due housekeeping, in this order: `timeOut` for a submission with no result after `resultDays`,
   `mergeExpired` for a `Won` bounty past `mergeBy`, `sunset` for an idle `Open` bounty; the earliest due first;
3. close an open labelled issue whose linked bounty ended: `Paid` with the payout comment, `Unsolved` or `Refunded` with
   the ending comment, each written once (its marker), then the close;
4. link an open labelled issue that validly claims a registration (bot/logic.py's first_valid_claim, the seats' rule)
   whose bounty is open;
5. hint once on an open labelled issue with no valid claim, `HINT_GRACE` after it was opened.

It never registers, signs, relays a verdict, pledges, attempts, seals, merges, challenges, claims, withdraws or warps:
its only transactions are `settle`, `timeOut`, `mergeExpired` and `sunset` (`ALLOWED`). It keeps no state of its own:
each pass reads the chain and the forge, and each step re-reads its own evidence (the markers, the contract's views)
right before it writes, so a restart at any point repeats nothing. A revert because someone else did it first
(`Refused`, `NotYet`, `WrongState`) counts as done.

Limits (D7): a pass every `poll` seconds; at most 5 writes a pass and 50 a run (then exit 4), every transaction, comment
and close counted; an item refused 3 times is left for the next run; a pass that can't read the chain or the forge
waits poll x 2^k (k failed passes in a row, at most 300 s; a Retry-After up to 300 s is honoured) and makes no write;
1,800 s of that exits 75; with `until_idle`, that long with no write and nothing waiting exits 0. Below `min_gas` it
sends no transaction (said once a run) and still does the forge's steps. With a transaction of its own pending (a crash
between sending and the receipt) it sends nothing new for up to 10 minutes.

Secrets (D6): its key, the RPC's API key and the forge token are read once from the files POF_BOT_KEY_FILE,
POF_BOT_RPC_AUTH_FILE and POF_BOT_FORGE_TOKEN_FILE name (or, on a throwaway local devnet only,
DEVNET_KEYS=insecure-local). No option takes a secret, an RPC URL with user info is refused, and every line it prints
goes through a redactor of every secret value read at start."""

from __future__ import annotations

import base64
import http.client
import json
import os
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from oracle import abi, v2
from oracle.crypto import checksum, keccak256
from oracle.rpc import Reverted, Rpc, RpcError, Wallet, split_auth

from . import logic

ALLOWED = {"settle": "settle(uint256,address)", "timeOut": "timeOut(uint256)", "mergeExpired": "mergeExpired(uint256)",
           "sunset": "sunset(uint256)"}
DONE = re.compile(r"^(Refused|NotYet|WrongState|AlreadySettled)\(")  # someone did it first: done, not a failure
FINAL = ("Paid", "Unsolved", "Refunded")
DEVNET_CHAINS = (7193, 31337)  # the private devnet and anvil only (rule 1)
EXIT_IDLE, EXIT_REFUSED, EXIT_FUSE, EXIT_AWAY = 0, 2, 4, 75
EVENTS = {"BountyOpened(uint256,uint256)": "opened", "Committed(uint256,uint256,address)": "committed",
          "StateChanged(uint256,uint8)": "changed"}
TOPICS = {"0x" + keccak256(sig.encode()).hex(): name for sig, name in EVENTS.items()}


@dataclass
class Settings:
    repo: str = ""
    label: str = logic.LABEL
    repo_id: str = "0x0"  # the repository's id on-chain: its registry id, or 0 outside the registry
    poll: float = 30.0
    max_pass: int = 5
    max_run: int = 50
    max_item_failures: int = 3
    backoff_max: float = 300.0
    away_exit: float = 1800.0
    until_idle: float | None = None
    claim_wait: float = 900.0
    hint_grace: float = 300.0
    min_gas: int = 10**16  # 0.01 devnet ETH
    pending_wait: float = 600.0
    min_bounty: int = 0
    explorer: str = ""
    page_blocks: int = 2000


class Refused(Exception):
    """A refusal at start (exit 2). Its message never carries a secret."""


class Fuse(Exception):
    """The run's write fuse (exit 4)."""


class PassFull(Exception):
    """The pass's writes are spent: the rest waits for the next pass."""


class Away(Exception):
    """A read of the chain or the forge failed: the pass ends with no write, and the next one backs off."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ItemRefused(Exception):
    """A write the forge refused for good (a 4xx): counted against the item, not the pass."""


# ---------- secrets ----------

class Redactor:
    """Every secret value read at start, in each form it could be printed in (as the AWS suite's Secrets)."""

    def __init__(self) -> None:
        self._forms: list = []

    def add(self, value: str) -> None:
        value = (value or "").strip()
        if len(value) < 8:
            return
        forms = {value, base64.b64encode(value.encode()).decode(), urllib.parse.quote(value, safe="")}
        hexed = value[2:] if value.lower().startswith("0x") else value
        if re.fullmatch(r"[0-9a-fA-F]{64}", hexed):
            forms |= {hexed.lower(), hexed.upper(), "0x" + hexed.lower(), f"{int(hexed, 16):x}"}
        if ":" in value:
            forms.add(value.split(":", 1)[1])
        self._forms = sorted({*self._forms, *(f for f in forms if len(f) >= 8)}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for form in self._forms:
            text = text.replace(form, "***")
        return text


def read_secret(env: dict, var: str, what: str) -> str:
    """A secret from the file `var` names, read once; Refused when it's missing or empty (never naming its value)."""
    path = env.get(var) or ""
    if not path:
        raise Refused(f"set {var} to the file holding {what}")
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        raise Refused(f"can't read {var}'s file ({what})") from None
    if not value:
        raise Refused(f"{var}'s file is empty ({what})")
    return value


# ---------- the chain, over JSON-RPC ----------

class RpcChain:
    """RaceV2, as the bot reads it and the four calls it may send. Only `ALLOWED` goes out."""

    def __init__(self, rpc: Rpc, race: str, secret: int, coin: str | None = None, from_block: int = 0) -> None:
        self.rpc, self.race = rpc, checksum(race)
        self.wallet = Wallet(rpc, secret, "bot-service")
        self.address = self.wallet.address
        self.from_block = from_block
        self._coins = None
        self.coin = checksum(coin) if coin else self.fee_coins()[0]
        self.verdicts = checksum(rpc.view(self.race, "verdicts()", ["address"])[0])

    def chain_id(self) -> int:
        return self.rpc.chain_id()

    def head(self) -> int:
        return self.rpc.block()

    def day(self) -> int:
        return self.rpc.view(self.race, "day()", ["uint256"])[0]

    def config(self) -> dict:
        names = ["infrastructure", "insurance", "registrationFee", "issueStake", "attemptFee", "evaluationFee",
                 "checkDeposit", "appealFee", "appealDeposit", "startPriceBps", "riseBpsPerDay", "finderFeeBps",
                 "idleDays", "resultDays", "mergeDays", "windowDays", "releaseEveryDays", "instalments"]
        types = ["(address,address," + ",".join(["uint256"] * 16) + ")"]
        return dict(zip(names, self.rpc.view(self.race, "getConfig()", types)[0]))

    def fee_coins(self) -> list:
        if self._coins is None:
            coins = []
            for i in range(16):
                try:
                    coins.append(checksum(self.rpc.view(self.race, "feeCoins(uint256)", ["address"], i)[0]))
                except Reverted:
                    break
            self._coins = coins
        return list(self._coins)

    def scan(self, from_block: int, to_block: int) -> list:
        """The race's BountyOpened, Committed and StateChanged logs: [(kind, fields)]."""
        out = []
        for log in self.rpc.logs(self.race, from_block, [list(TOPICS)], to_block):
            kind = TOPICS.get((log.get("topics") or [""])[0])
            t = log["topics"]
            if kind == "opened":
                out.append((kind, {"bounty": int(t[1], 16), "issue": int(t[2], 16)}))
            elif kind == "committed":
                out.append((kind, {"bounty": int(t[1], 16), "submission": int(t[2], 16)}))
            elif kind == "changed":
                out.append((kind, {"bounty": int(t[1], 16), "state": v2.STATES[int(log["data"], 16)]}))
        return out

    def bounty(self, b: int) -> dict:
        out = dict(zip(v2.BOUNTY_FIELDS, self.rpc.view(self.race, "bounty(uint256)", v2.BOUNTY, b)[0]))
        out["state"] = v2.STATES[out["state"]]
        return out

    def submission(self, s: int) -> dict:
        out = dict(zip(v2.SUBMISSION_FIELDS, self.rpc.view(self.race, "submission(uint256)", v2.SUBMISSION, s)[0]))
        out["outcome"] = v2.OUTCOMES[out["outcome"]]
        return out

    def submissions_of(self, b: int) -> list:
        return list(self.rpc.view(self.race, "submissionsOf(uint256)", ["uint256[]"], b)[0])

    def issue(self, i: int) -> dict:
        out = dict(zip(v2.ISSUE_FIELDS, self.rpc.view(self.race, "issue(uint256)", v2.ISSUE, i)[0]))
        out["state"] = v2.ISSUE_STATES[out["state"]]
        return out

    def earned(self, b: int, epoch: int) -> int:
        return self.rpc.view(self.race, "earned(uint256,uint256)", ["uint256"], b, epoch)[0]

    def settled(self, b: int, coin: str) -> bool:
        return self.rpc.view(self.race, "settled(uint256,address)", ["bool"], b, coin)[0]

    def held(self, b: int, coin: str) -> int:
        return self.rpc.view(self.race, "held(uint256,address)", ["uint256"], b, coin)[0]

    def state_tx(self, b: int, state: str) -> dict | None:
        """The transaction that moved bounty b to `state` (its last StateChanged to it): {"tx", "block"}, or None."""
        topics = ["0x" + keccak256(b"StateChanged(uint256,uint8)").hex(), "0x%064x" % b]
        found = None
        for log in self.rpc.logs(self.race, self.from_block, topics):
            if int(log["data"], 16) == v2.STATES.index(state):
                found = {"tx": log["transactionHash"], "block": int(log["blockNumber"], 16)}
        return found

    def is_oracle(self, who: str) -> bool:
        return self.rpc.view(self.verdicts, "isOracle(address)", ["bool"], who)[0]

    def balance(self, who: str) -> int:
        return int(self.rpc.call("eth_getBalance", [who, "latest"]), 16)

    def nonces(self) -> tuple:
        return tuple(int(self.rpc.call("eth_getTransactionCount", [self.address, tag]), 16)
                     for tag in ("latest", "pending"))

    def send(self, fn: str, *args) -> dict:
        if fn not in ALLOWED:
            raise ValueError(f"the bot never calls {fn}: only {', '.join(ALLOWED)}")
        return self.wallet.send(self.race, ALLOWED[fn], *args)


# ---------- the service ----------

def _retry_after(e) -> float | None:
    headers = getattr(e, "headers", None)
    try:
        return max(float((headers or {}).get("Retry-After", "")), 0.0)
    except (TypeError, ValueError, AttributeError):
        return None


def _status(e) -> int | None:
    for name in ("code", "status"):
        value = getattr(e, name, None)
        if isinstance(value, int) and value:
            return value
    return None


def _created(issue: dict) -> float | None:
    raw = issue.get("created_at") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() if raw else None
    except ValueError:
        return None


class BotService:
    def __init__(self, chain, forge, settings: Settings, clock=time.time, sleep=time.sleep, out=print,
                 redactor: Redactor | None = None, chain_id: int | None = None) -> None:
        self.chain, self.forge, self.s = chain, forge, settings
        self.clock, self.sleep, self.out = clock, sleep, out
        self.redactor = redactor or Redactor()
        self.race = chain.race
        self.chain_id = chain_id
        self.bounties: dict = {}  # bounty -> its on-chain issue (from BountyOpened): the candidates, a cache only
        self.subs: dict = {}  # submission -> its bounty (from Committed)
        self.scanned: int | None = None  # the last block scanned
        self.writes = 0  # this run's
        self.pass_writes = 0
        self.failures: dict = {}  # item -> refusals this run
        self.skipped: set = set()
        self.first_seen: dict = {}  # forge issue -> when this run first saw it
        self.pending_since: float | None = None
        self.passes = 0
        self._said: set = set()
        self._config = None

    # ---------- output ----------

    def emit(self, **fields) -> None:
        self.out(self.redactor.redact(json.dumps(fields, sort_keys=True, default=str)))

    def _once(self, key, **fields) -> None:
        if key not in self._said:
            self._said.add(key)
            self.emit(**fields)

    # ---------- reads: a failure ends the pass ----------

    def _read(self, fn, *args):
        try:
            return fn(*args)
        except Reverted:
            raise
        except RpcError as e:
            raise Away(f"the chain: {e}", getattr(e, "retry_after", None)) from None
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise Away(f"the forge: {type(e).__name__}: {str(e)[:200]}", _retry_after(e)) from None
        except Exception as e:  # noqa: BLE001 (a forge client's own error, e.g. GitHubError)
            if type(e).__name__ in ("GitHubError",):
                raise Away(f"the forge: {str(e)[:200]}", _retry_after(e)) from None
            raise

    def config(self) -> dict:
        if self._config is None:
            self._config = self._read(self.chain.config)
        return self._config

    def check_start(self, deployer: str | None = None) -> None:
        """D6's refusals: a chain that isn't the devnet's or anvil's; a key that judges or deployed."""
        cid = self._read(self.chain.chain_id)
        if cid not in DEVNET_CHAINS:
            raise Refused(f"the RPC answers chain {cid}, not the devnet's or anvil's {DEVNET_CHAINS} (rule 1)")
        self.chain_id = cid
        me = self.chain.address
        if self._read(self.chain.is_oracle, me):
            raise Refused(f"the bot's key {me} is an active oracle key: the bot never judges")
        if deployer and deployer.lower() == me.lower():
            raise Refused(f"the bot's key {me} is the deployer's")

    def _scan(self, head: int) -> None:
        start = self.chain.from_block if self.scanned is None else self.scanned + 1
        while start <= head:
            end = min(start + self.s.page_blocks - 1, head)
            for kind, f in self._read(self.chain.scan, start, end):
                if kind == "opened":
                    self.bounties[f["bounty"]] = f["issue"]
                elif kind == "committed" and f["submission"]:
                    self.subs[f["submission"]] = f["bounty"]
                elif kind == "changed":
                    self.bounties.setdefault(f["bounty"], None)  # an ended or reopened bounty: re-checked below
            self.scanned, start = end, end + 1

    # ---------- writes ----------

    def _write(self, key, kind: str, fn, **what) -> bool:
        """One write (a transaction, a comment or a close). True when it's done (or was already)."""
        if key in self.skipped:
            return False
        if self.writes >= self.s.max_run:
            raise Fuse(f"the run's {self.s.max_run} writes are spent")
        if self.pass_writes >= self.s.max_pass:
            raise PassFull()
        self.writes += 1
        self.pass_writes += 1
        try:
            result = fn()
        except Reverted as e:
            if DONE.match(e.reason or ""):
                self.emit(write=kind, done="already", reason=e.reason, **what)
                return True
            return self._failed(key, kind, e.reason, what)
        except ItemRefused as e:
            return self._failed(key, kind, str(e), what)
        except RpcError as e:
            raise Away(f"the chain, sending {kind}: {e}", getattr(e, "retry_after", None)) from None
        tx = (result or {}).get("transactionHash") if isinstance(result, dict) else None
        self.emit(write=kind, **what, **({"tx": tx} if tx else {}))
        return True

    def _failed(self, key, kind: str, why: str, what: dict) -> bool:
        self.failures[key] = self.failures.get(key, 0) + 1
        if self.failures[key] >= self.s.max_item_failures:
            self.skipped.add(key)
        self.emit(write=kind, failed=why, refusals=self.failures[key], skipped=key in self.skipped, **what)
        return False

    def _forge_write(self, fn, *args):
        try:
            return fn(*args)
        except (OSError, http.client.HTTPException) as e:
            status = _status(e)
            if status and 400 <= status < 500 and status not in (408, 429):
                raise ItemRefused(f"the forge answered HTTP {status}") from None
            raise Away(f"the forge: {type(e).__name__} {status or ''}".strip(), _retry_after(e)) from None
        except Exception as e:  # noqa: BLE001
            status = _status(e)
            if type(e).__name__ == "GitHubError":
                if status and 400 <= status < 500 and status not in (408, 429):
                    raise ItemRefused(f"the forge answered HTTP {status}") from None
                raise Away(f"the forge: {str(e)[:200]}") from None
            raise

    def _send(self, fn: str, *args):
        return self.chain.send(fn, *args)

    # ---------- one pass ----------

    def run_pass(self) -> dict:
        self.passes += 1
        self.pass_writes, self.waiting = 0, False
        head = self._read(self.chain.head)
        self._scan(head)
        cfg = self.config()
        day = self._read(self.chain.day)
        open_issues = self._read(self.forge.issues, "open", self.s.label)
        now = self.clock()
        for i in open_issues:
            self.first_seen.setdefault(i["number"], now)
        try:
            if self._can_send():
                self._settle(cfg)
                self._housekeeping(cfg, day)
            comments = {i["number"]: self._read(self.forge.comments, i["number"]) for i in open_issues}
            self._close(open_issues, comments)
            self._link_and_hint(open_issues, comments, now)
        except PassFull:
            self.waiting = True  # more is due: not idle
        summary = {"pass": self.passes, "block": head, "day": day, "writes": self.pass_writes, "runWrites": self.writes,
                   "waiting": self.waiting, "bounties": len(self.bounties), "submissions": len(self.subs)}
        self.emit(**summary)
        return summary

    def _can_send(self) -> bool:
        if self._read(self.chain.balance, self.chain.address) < self.s.min_gas:
            self._once("gas", note=f"under {self.s.min_gas / 10**18:g} ETH for gas: no transaction this run until "
                                   f"funded; the forge's steps go on", address=self.chain.address)
            return False
        latest, pending = self._read(self.chain.nonces)
        if pending > latest:
            now = self.clock()
            self.pending_since = self.pending_since or now
            if now - self.pending_since < self.s.pending_wait:
                self.waiting = True
                self._once(("pending", latest), note="a transaction of the bot's own is pending (a restart after "
                                                     "sending it): nothing new is sent until it's mined",
                           latest=latest, pending=pending)
                return False
        else:
            self.pending_since = None
        return True

    def _in_scope(self, b: int) -> bool:
        return b >= max(self.s.min_bounty, 1)

    def _settle(self, cfg: dict) -> None:
        coins = [self.chain.coin] + [c for c in self.chain.fee_coins() if c.lower() != self.chain.coin.lower()]
        for b in sorted(self.bounties):
            if not self._in_scope(b):
                continue
            bt = self._read(self.chain.bounty, b)
            st = bt["state"]
            final = st in FINAL or (st == "Merged" and self._read(self.chain.earned, b, bt["epoch"])
                                    >= cfg["instalments"])
            if not final:
                continue
            left = 0
            for coin in coins:
                if self._read(self.chain.settled, b, coin):
                    continue
                if coin != self.chain.coin and not self._read(self.chain.held, b, coin):
                    continue
                left += 1
                if self._write(("settle", b, coin), "settle", lambda: self._send("settle", b, coin), bounty=b,
                               coin=coin, state=st):
                    left -= 1
            if st in FINAL and not left:
                self.bounties.pop(b, None)  # nothing left to settle; closing reads the bounty from its link

    def _housekeeping(self, cfg: dict, day: int) -> None:
        due = []
        for s, b in sorted(self.subs.items()):
            if not self._in_scope(b):
                continue
            sub = self._read(self.chain.submission, s)
            if sub["outcome"] != "None":
                self.subs.pop(s, None)
                continue
            when = sub["day"] + cfg["resultDays"]
            if day >= when:
                due.append((when, s))
        for _, s in sorted(due):
            self._write(("timeOut", s), "timeOut", lambda: self._send("timeOut", s), submission=s)
        for kind, test in (("mergeExpired", self._merge_due), ("sunset", self._sunset_due)):
            due = []
            for b in sorted(self.bounties):
                if self._in_scope(b):
                    when = test(b, cfg, day)
                    if when is not None:
                        due.append((when, b))
            for _, b in sorted(due):
                self._write((kind, b), kind, lambda: self._send(kind, b), bounty=b)

    def _merge_due(self, b: int, cfg: dict, day: int):
        bt = self._read(self.chain.bounty, b)
        return bt["mergeBy"] if bt["state"] == "Won" and day > bt["mergeBy"] else None

    def _sunset_due(self, b: int, cfg: dict, day: int):
        bt = self._read(self.chain.bounty, b)
        if bt["state"] != "Open" or bt["next"] < len(self._read(self.chain.submissions_of, b)):
            return None
        when = bt["idleSince"] + cfg["idleDays"]
        return when if day >= when else None

    def _close(self, open_issues: list, comments: dict) -> None:
        for i in open_issues:
            n = i["number"]
            link = logic.linked(comments[n])
            if link is None or link[0].lower() != self.race.lower() or not self._in_scope(link[1]):
                continue
            b = link[1]
            st = self._read(self.chain.bounty, b)["state"]
            if st not in FINAL:
                continue
            fresh = self._read(self.forge.comments, n)  # re-read right before writing
            said = logic.paid(fresh) if st == "Paid" else logic.ended(fresh)
            if said is None:
                ended = self._read(self.chain.state_tx, b, st)
                if ended is None:
                    continue  # the log isn't readable yet: the next pass
                if st == "Paid":
                    body = logic.paid_comment(self.race, b, ended["tx"], ended["block"], self.chain_id or 0,
                                              self.s.explorer)
                else:
                    body = logic.ended_comment(self.race, b, st, ended["tx"], ended["block"], self.chain_id or 0,
                                               self.s.explorer)
                if not self._write(("comment-end", n), "comment", lambda: self._forge_write(self.forge.comment, n, body),
                                   issue=n, bounty=b, comment="paid" if st == "Paid" else "ended", state=st,
                                   endedTx=ended["tx"]):
                    continue
            if self._read(self.forge.issue, n)["state"] != "closed":
                self._write(("close", n), "close", lambda: self._forge_write(self.forge.close, n), issue=n, bounty=b,
                            state=st)

    def _link_and_hint(self, open_issues: list, comments: dict, now: float) -> None:
        everything = None
        for i in open_issues:
            n = i["number"]
            if logic.linked(comments[n]) is not None:
                continue
            claimed = logic.registration(i.get("body", ""))
            onchain = None
            if claimed is not None:
                try:
                    raw = self._read(self.chain.issue, claimed)
                    if int(str(raw["reporter"]), 16):
                        onchain = {"id": claimed, **raw}
                except Reverted:
                    onchain = None
            if everything is None:
                everything = self._read(self.forge.issues, "all", self.s.label)
            reason = logic.hint_reason(i, everything, onchain, self.s.repo_id, self.s.label)
            if reason is None:
                b = int(onchain["bounty"])
                if b == 0:
                    if now - self.first_seen.get(n, now) < self.s.claim_wait:
                        self.waiting = True  # claimed, waiting for the seats' check
                    continue
                if not self._in_scope(b):
                    continue
                fresh = self._read(self.forge.comments, n)
                if logic.linked(fresh) is None:
                    body = logic.bounty_comment(self.race, b, claimed)
                    self._write(("link", n), "comment", lambda: self._forge_write(self.forge.comment, n, body), issue=n,
                                bounty=b, comment="link", registration=claimed)
                continue
            if logic.hinted(comments[n]):
                continue
            age = now - (_created(i) or self.first_seen.get(n, now))
            if age < self.s.hint_grace:
                self.waiting = True
                continue
            fresh = self._read(self.forge.comments, n)
            if logic.hinted(fresh) or logic.linked(fresh) is not None:
                continue
            body = logic.hint_comment(self.race, reason)
            self._write(("hint", n), "comment", lambda: self._forge_write(self.forge.comment, n, body), issue=n,
                        comment="hint", reason=reason)

    # ---------- the run ----------

    def run(self) -> int:
        """Passes until idle (exit 0), the write fuse (4) or the chain or the forge away too long (75)."""
        last, away_since, failed = self.clock(), None, 0
        while True:
            try:
                summary = self.run_pass()
            except Fuse as e:
                self.emit(exit=EXIT_FUSE, reason=str(e), runWrites=self.writes)
                return EXIT_FUSE
            except Away as e:
                now = self.clock()
                away_since = now if away_since is None else away_since
                failed += 1
                if now - away_since >= self.s.away_exit:
                    self.emit(exit=EXIT_AWAY, reason=f"away for {now - away_since:.0f} s: {e}")
                    return EXIT_AWAY
                wait = min(self.s.poll * 2 ** failed, self.s.backoff_max)
                if e.retry_after is not None:
                    wait = min(max(wait, e.retry_after), self.s.backoff_max)
                self.emit(error=str(e), failedPasses=failed, retryIn=wait)
                self.sleep(wait)
                continue
            now = self.clock()
            if away_since is not None:
                away_since, failed, last = None, 0, now  # the idle time starts again from their return
            if summary["writes"] or summary["waiting"]:
                last = now
            elif self.s.until_idle is not None and now - last >= self.s.until_idle:
                self.emit(exit=EXIT_IDLE, reason=f"idle for {now - last:.0f} s", runWrites=self.writes)
                return EXIT_IDLE
            self.sleep(self.s.poll)


# ---------- from the environment (pofctl bot watch) ----------

ENV_DOC = """The environment (paths for the secrets, never their values):
    POF_BOT_RPC                 the chain's RPC URL (no user info in it: refused)
    POF_BOT_RPC_AUTH_FILE       optional: a file with the devnet API key, "<handle>:<key>" (sent as HTTP Basic)
    POF_BOT_KEY_FILE            a file with the bot's own key (role bot-service), hex; or DEVNET_KEYS=insecure-local on a
                                throwaway local devnet (anvil's public mnemonic)
    POF_BOT_RECORD              a deployment record (race, coin, block, deployer); or instead
    POF_BOT_RACE                the RaceV2 address, with POF_BOT_FROM_BLOCK (the scan's first block, default 0)
    POF_BOT_REPO                owner/name of the repository whose issues it links and closes
    POF_BOT_REPO_ID             that repository's id on-chain: its registry id (the record's `repo` for pof-sandbox),
                                or 0x0 for a project outside the registry (the default)
    POF_BOT_FORGE_URL           the forge's API base (https, or http on this machine's loopback)
    POF_BOT_FORGE_HOST          forgejo (the default) or github
    POF_BOT_FORGE_USER          the token's user (Forgejo)
    POF_BOT_FORGE_TOKEN_FILE    a file with a token that may write that repository's issues and comments only
    POF_BOT_LABEL (bounty), POF_BOT_POLL_SECONDS (30), POF_BOT_HINT_GRACE (300), POF_BOT_MIN_BOUNTY (0),
    POF_BOT_MAX_WRITES_PER_PASS (5), POF_BOT_MAX_WRITES_PER_RUN (50), POF_BOT_EXPLORER (a transaction URL with {tx}),
    POF_BOT_DEPLOYER (the deployer's address, when the record doesn't name it)"""


def _number(env: dict, name: str, default: float) -> float:
    raw = env.get(name)
    try:
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        raise Refused(f"{name} must be a number") from None


def build(env: dict, until_idle: float | None = None, min_bounty: int | None = None, rpc_url: str | None = None,
          record_path: str | None = None, out=print, clock=time.time, sleep=time.sleep) -> tuple:
    """(the service, the deployer's address or None) from the environment; Refused on a bad setting (exit 2)."""
    from bot.forge import repo_for
    from pofctl import keys as keysrc

    redactor = Redactor()
    url = rpc_url or env.get("POF_BOT_RPC") or env.get("POFCTL_RPC") or "http://127.0.0.1:8546"
    if split_auth(url)[1] is not None:
        raise Refused("the RPC URL carries a credential: give it in POF_BOT_RPC_AUTH_FILE instead")
    headers = {}
    if env.get("POF_BOT_RPC_AUTH_FILE"):
        auth = read_secret(env, "POF_BOT_RPC_AUTH_FILE", "the devnet API key")
        redactor.add(auth)
        redactor.add(base64.b64encode(auth.encode()).decode())
        headers = {"Authorization": "Basic " + base64.b64encode(auth.encode()).decode()}
    if env.get("POF_BOT_KEY_FILE"):
        raw = read_secret(env, "POF_BOT_KEY_FILE", "the bot's key")
        redactor.add(raw)
        try:
            secret = int(raw, 16)
        except ValueError:
            raise Refused("POF_BOT_KEY_FILE's file isn't a hex key") from None
    elif env.get("DEVNET_KEYS") == "insecure-local":
        secret = keysrc.derive(keysrc.MNEMONIC, keysrc.ROLES.index("bot-service"))
    else:
        raise Refused("set POF_BOT_KEY_FILE to the file holding the bot's key (or DEVNET_KEYS=insecure-local on a "
                      "throwaway local devnet)")
    redactor.add(f"{secret:064x}")
    token = read_secret(env, "POF_BOT_FORGE_TOKEN_FILE", "the forge token")
    redactor.add(token)
    record = {}
    path = record_path or env.get("POF_BOT_RECORD")
    if path:
        try:
            record = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise Refused(f"can't read the deployment record {path}") from None
    race = env.get("POF_BOT_RACE") or record.get("race")
    if not race:
        raise Refused("set POF_BOT_RECORD (a deployment record) or POF_BOT_RACE (the RaceV2 address)")
    repo = env.get("POF_BOT_REPO") or ""
    forge_url = env.get("POF_BOT_FORGE_URL") or ""
    if repo.count("/") != 1 or not forge_url:
        raise Refused("set POF_BOT_REPO (owner/name) and POF_BOT_FORGE_URL")
    if split_auth(forge_url)[1] is not None:
        raise Refused("POF_BOT_FORGE_URL carries a credential: the token goes in POF_BOT_FORGE_TOKEN_FILE")
    host = env.get("POF_BOT_FORGE_HOST") or "forgejo"
    if host not in ("forgejo", "github"):
        raise Refused("POF_BOT_FORGE_HOST: forgejo or github")
    repo_id = env.get("POF_BOT_REPO_ID") or "0x0"
    try:
        int(repo_id, 16)
    except ValueError:
        raise Refused("POF_BOT_REPO_ID: a 0x bytes32") from None
    forge = repo_for(repo, {"repos": {repo: {"host": host, "api": forge_url}}},
                     env={"FORGEJO_TOKEN": token, "FORGEJO_USER": env.get("POF_BOT_FORGE_USER", ""),
                          "FORGEJO_PASSWORD": "", "GITHUB_TOKEN": token})
    rpc = Rpc(url, headers, retries=3)
    from_block = int(_number(env, "POF_BOT_FROM_BLOCK", record.get("block", 0)))
    try:
        chain = RpcChain(rpc, race, secret, coin=record.get("coin"), from_block=from_block)
    except RpcError as e:
        raise Refused(redactor.redact(f"can't read the race at {race}: {e}")) from None
    settings = Settings(
        repo=repo, label=env.get("POF_BOT_LABEL") or logic.LABEL, repo_id=repo_id,
        poll=_number(env, "POF_BOT_POLL_SECONDS", 30), hint_grace=_number(env, "POF_BOT_HINT_GRACE", 300),
        min_bounty=int(min_bounty if min_bounty is not None else _number(env, "POF_BOT_MIN_BOUNTY", 0)),
        max_pass=int(_number(env, "POF_BOT_MAX_WRITES_PER_PASS", 5)),
        max_run=int(_number(env, "POF_BOT_MAX_WRITES_PER_RUN", 50)),
        until_idle=until_idle, explorer=env.get("POF_BOT_EXPLORER") or env.get("POFCTL_EXPLORER") or "")
    deployer = env.get("POF_BOT_DEPLOYER") or record.get("deployer")
    if not deployer and env.get("DEVNET_KEYS") == "insecure-local":
        deployer = keysrc.address(keysrc.derive(keysrc.MNEMONIC, keysrc.ROLES.index("deployer")))
    svc = BotService(chain, forge, settings, clock=clock, sleep=sleep, out=out, redactor=redactor)
    return svc, deployer


def main(env: dict | None = None, until_idle: float | None = None, min_bounty: int | None = None,
         rpc_url: str | None = None, record_path: str | None = None, out=print) -> int:
    env = dict(os.environ) if env is None else env
    try:
        svc, deployer = build(env, until_idle, min_bounty, rpc_url, record_path, out=out)
        svc.check_start(deployer)
    except Refused as e:
        out(json.dumps({"exit": EXIT_REFUSED, "refused": str(e)}))
        return EXIT_REFUSED
    except Away as e:
        out(json.dumps({"exit": EXIT_REFUSED, "refused": f"the chain didn't answer at start: {str(e)[:200]}"}))
        return EXIT_REFUSED
    svc.emit(start="pofctl bot watch", address=svc.chain.address, race=svc.race, repo=svc.s.repo,
             minBounty=svc.s.min_bounty, poll=svc.s.poll, untilIdle=until_idle)
    return svc.run()
