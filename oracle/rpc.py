"""A JSON-RPC client for the devnet (or any Ethereum node it's pointed at), and a wallet that signs and sends
transactions with a key. Standard library only (urllib); no cast, forge or Docker needed, so it works the same against
a devnet on this machine or one reached over HTTPS (#104's chain on AWS). Shared by pofctl (pofctl.rpc) and the v2
and v3 oracle nodes.

The chain on AWS sits behind an API key: give it as the URL's user info
(https://<handle>:<key>@devnet.example, sent as HTTP Basic and never printed) or as a token (sent as
`Authorization: Bearer <token>`, or under another header name). Nothing here logs a URL with its user info, nor with
its path when the path may hold a key (Infura's `/v3/<key>`, Alchemy's `/v2/<key>`): every error and retry line shows
`oracle.redact.shown_url`'s form, the scheme and host (proof-of-fix#251, v3.1 polish VP20).

Transient failures (proof-of-fix#166): a connection error, a timeout, an answer that isn't JSON, or HTTP 429, 502, 503 or
504 is `Unavailable` (with the answer's Retry-After, if any, as `retry_after`). A call that's safe to repeat goes again
`retries` times (DEFAULT_RETRIES, 3, unless the caller says otherwise: the node passes ORACLE_RPC_RETRIES, 5; VP19)
with bounded backoff, honouring Retry-After up to RETRY_AFTER_MAX_S. Safe means: a read, or eth_sendRawTransaction, whose bytes
carry their own nonce and hash, so a second copy is the same transaction. Anything else (eth_sendTransaction, where the
server picks the nonce; a test node's evm_* calls) gets one try. A revert and any other answer are never retried.

Event scans (proof-of-fix#312): every public chain's providers bound an eth_getLogs range (on Sepolia, Infura 10,000
blocks, publicnode 50,000, the free tiers of Alchemy, drpc and 1rpc 10, 100 and 50). `logs` asks in chunks of at most
`log_range` blocks (the node's ORACLE_LOG_RANGE, default 5,000), with `latest` resolved once per scan so its chunks
meet; a provider that refuses a chunk as too large gets it halved (or cut to a smaller limit its message names), and
the smaller size is kept for the client's later scans."""

from __future__ import annotations

import base64
import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .crypto import address as address_of
from .crypto import keccak256
from .crypto import sign as _sign

from . import abi
from .redact import shown_url
from .tx import signed_legacy

# Custom errors the Race, Verdicts, Fees, Heads and Baskets raise, by selector, so a revert reads as a name.
ERRORS = ["NotOracle()", "TooFewSignatures()", "DuplicateSigner()", "Replayed()", "BadParams()", "BadOracleSet()",
          "NotFeeCoin(address)", "WrongState(uint256,uint8)", "NotYet()", "Refused()", "Insolvent()", "WrongTier()",
          "NotDrawn()", "Recused()", "UnknownSeat()", "KeyTaken()", "ImageNotAllowed()", "AttestationNotAccepted()",
          "MissingSigner()", "AlreadyPending()", "NothingPending()", "TooEarly()", "SeatVacant()", "AlreadyBound()",
          "NotRace()", "Undecided()", "AlreadyReported()", "AlreadySettled()", "OutOfBounds(uint256)", "ShortOfGas()",
          "UnknownRepo(bytes32)", "NotMover()", "StaleVerdict(bytes32,bytes32,bytes32)", "NothingOwed()",
          "WithdrawOnlyMode(address)", "ZeroAmount()", "NotRefundable(uint256,address)", "NotYours(uint256)",
          "ERC20InsufficientBalance(address,uint256,uint256)", "ERC20InsufficientAllowance(address,uint256,uint256)",
          # v3's (Validators, Panels and its libraries, FeesV3, RaceV3)
          "NotPanels()", "BadRegistration()", "ProofTypeNotAccepted()", "TeeTypeNotAccepted()", "NoAttestation()",
          "BadLevel()", "BadSignature()", "BondTooSmall()", "NothingArrived()", "Unknown()", "NotAllowed()",
          "WrongState()", "Locked()", "FirmwareTooOld()", "WrongStatus()", "BadBounty()", "Busy()", "TooLate()",
          "NothingChanged()", "NotOpen()", "NotSeated()", "AlreadySealed()", "NotSealed()", "AlreadyRevealed()",
          "AlreadyReceipted()", "EmptyHash()", "NothingDue()", "NotReady()", "NotActive()", "BadTable()",
          "NotRegistered()", "AlreadyOpen()", "Unpriced(bytes32)", "RollInProgress()", "NodeTaken()"]
_BY_SELECTOR = {abi.selector(e).hex(): e for e in ERRORS}

TRANSIENT_STATUS = frozenset({429, 502, 503, 504})
SAFE_TO_REPEAT = frozenset({"eth_chainId", "eth_blockNumber", "eth_call", "eth_getLogs", "eth_estimateGas", "eth_gasPrice",
                            "eth_getBalance", "eth_getCode", "eth_getStorageAt", "eth_getBlockByNumber",
                            "eth_getTransactionCount", "eth_getTransactionReceipt", "eth_getTransactionByHash",
                            "eth_sendRawTransaction"})
FIRST_BACKOFF_S, MAX_BACKOFF_S = 1.0, 15.0
DEFAULT_RETRIES = 3  # a 429 doesn't fail a command at its first answer (#251 v3.1 polish VP19, S5)
RETRY_AFTER_MAX_S = 30.0  # the longest Retry-After waited for in one retry: longer storms are the keeper's (VP6)
DEFAULT_LOG_RANGE = 5_000  # blocks per eth_getLogs call: inside Infura's 10,000 and publicnode's 50,000
# A provider's refusal of an eth_getLogs range as too large (or as too many results, which a smaller range also cures):
# "range 12192494 exceeds limit of 10000" (Infura), "eth_getLogs is limited to a 10,000 range", "Log response size
# exceeded. You can make eth_getLogs requests with up to a 10 block range" (Alchemy), "query returned more than 10000
# results", "block range too large", "ranges over 100 blocks are not supported on freetier" (drpc).
RANGE_REFUSED = re.compile(r"range|too (?:many|large|big)|exceed|more than|limit", re.I)
# What a node says to a second copy of a transaction it has: the same bytes, so the same transaction (geth, anvil,
# Erigon "already known", Nethermind "AlreadyKnown", Hardhat "known transaction" / "already imported").
SAME_TX = re.compile(r"already known|alreadyknown|already imported|known transaction|already in (?:the )?(?:mem)?pool",
                     re.I)
# What a node says to a transaction whose nonce another one has taken, mined or pending (geth, anvil, Infura and Alchemy
# "nonce too low[: next nonce 5, tx nonce 3]", Hardhat "Nonce too low. Expected nonce to be 1 but got 0", Besu
# NONCE_TOO_LOW, Nethermind OldNonce, geth "replacement transaction underpriced", others "nonce has already been used").
# Not "maybe sent": unless the chain knows this transaction's hash, it is signed again past that nonce (VP27).
NONCE_TAKEN = re.compile(r"nonce (?:is )?too low|nonce_too_low|oldnonce|old nonce|nonce (?:has )?already (?:been )?used|"
                         r"replacement (?:transaction )?underpriced|transaction_replacement_underpriced|"
                         r"already exists with (?:the )?same nonce|same nonce", re.I)
ALREADY_SENT = re.compile(f"{SAME_TX.pattern}|{NONCE_TAKEN.pattern}", re.I)  # either: the chain has something there
_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
NONCE_RETRIES = 3  # signings past a taken nonce in one send before it fails (VP27)
DROPPED_AFTER_S = 20.0  # no receipt and no transaction by this hash for this long: sent once more, the same bytes


class RpcError(RuntimeError):
    pass


class Unavailable(RpcError):
    """No usable answer from the chain, after any retries: nothing is known about the request, so try again later."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class Reverted(RpcError):
    """A call the chain refused. `receipt`: a transaction mined but reverted (its gas spent), else None."""

    def __init__(self, reason: str, data: str = "", receipt: dict | None = None) -> None:
        super().__init__(reason)
        self.reason, self.data, self.receipt = reason, data, receipt


def _reason(data: str) -> str:
    raw = (data or "")[2:] if (data or "").startswith("0x") else (data or "")
    if len(raw) >= 8:
        name = _BY_SELECTOR.get(raw[:8])
        if name:
            return name
        if raw[:8] == "08c379a0":  # Error(string)
            try:
                return abi.decode(["string"], bytes.fromhex(raw[8:]))[0]
            except ValueError:
                pass
    return "reverted" + (f" (0x{raw[:8]})" if raw else "")


def split_auth(url: str) -> tuple:
    """(the URL without its user info, the Basic authorization header for it, or None)."""
    u = urllib.parse.urlsplit(url)
    if u.username is None:
        return url, None
    secret = urllib.parse.unquote(u.username) + ":" + urllib.parse.unquote(u.password or "")
    host = (f"[{u.hostname}]" if ":" in (u.hostname or "") else u.hostname or "") + (f":{u.port}" if u.port else "")
    bare = urllib.parse.urlunsplit((u.scheme, host, u.path, u.query, u.fragment))
    return bare, "Basic " + base64.b64encode(secret.encode()).decode()


def auth_headers(token: str | None = None, header: str = "Authorization") -> dict:
    """A token's header. `header` names the scheme: "Authorization" sends `Bearer <token>`; "Basic" sends HTTP Basic
    for a "<handle>:<key>" token (the demo chain's); any other name carries the raw token (X-Api-Key)."""
    if not token:
        return {}
    if header.lower() == "basic":
        return {"Authorization": "Basic " + base64.b64encode(token.encode()).decode()}
    return {header: f"Bearer {token}" if header.lower() == "authorization" else token}


def _retry_after(headers) -> float | None:
    try:
        return max(float((headers or {}).get("Retry-After", "")), 0.0)
    except (TypeError, ValueError):  # absent, or an HTTP date: the backoff decides
        return None


class Rpc:
    def __init__(self, url: str, headers: dict | None = None, timeout: float = 30, retries: int = DEFAULT_RETRIES,
                 sleep=None, log=None, log_range: int = DEFAULT_LOG_RANGE) -> None:
        self.url, basic = split_auth(url)  # without its user info; its path may still hold a key: never printed
        self.shown = shown_url(self.url)  # what every error and retry line names (VP20)
        self.headers = {**({"Authorization": basic} if basic else {}), **(headers or {})}
        self.timeout, self._id = timeout, 0
        self.retries, self.sleep, self.log = retries, sleep or (lambda s: time.sleep(s)), log  # time.sleep, late-bound
        if log_range < 1:
            raise ValueError("the eth_getLogs range is at least 1 block")
        self.log_range = log_range  # lowered for good when the provider refuses a chunk as too large

    def _exchange(self, body: bytes) -> dict:
        """One HTTP exchange: the decoded answer, or Unavailable (worth trying again) or RpcError (not)."""
        req = urllib.request.Request(self.url, data=body, method="POST",
                                     headers={"Content-Type": "application/json", **self.headers})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 (the configured node)
                raw = r.read()
        except urllib.error.HTTPError as e:
            if e.code in TRANSIENT_STATUS:
                raise Unavailable(f"the chain at {self.shown} answered HTTP {e.code}", _retry_after(e.headers)) from e
            hint = " (check the RPC key)" if e.code in (401, 403) else ""
            raise RpcError(f"the chain at {self.shown} answered HTTP {e.code}{hint}") from e
        except urllib.error.URLError as e:
            raise Unavailable(f"can't reach the chain at {self.shown}: {e.reason}") from e
        except (OSError, http.client.HTTPException) as e:  # the answer's read timed out, or the connection dropped
            raise Unavailable(f"can't reach the chain at {self.shown}: {type(e).__name__}") from e
        try:
            reply = json.loads(raw)
        except ValueError as e:  # a proxy's error page with a 200, or a cut-off body
            raise Unavailable(f"the chain at {self.shown} gave an answer that isn't JSON") from e
        if not isinstance(reply, dict):
            raise Unavailable(f"the chain at {self.shown} gave an answer that isn't JSON-RPC")
        return reply

    def _send(self, method: str, body: bytes) -> dict:
        attempts = 1 + (self.retries if method in SAFE_TO_REPEAT else 0)
        for attempt in range(attempts):
            try:
                return self._exchange(body)
            except Unavailable as e:
                if attempt + 1 == attempts:
                    raise
                wait = min(FIRST_BACKOFF_S * 2 ** attempt, MAX_BACKOFF_S)
                if e.retry_after is not None:
                    wait = min(max(wait, e.retry_after), RETRY_AFTER_MAX_S)
                if self.log:
                    self.log(f"{method}: {e}; retry {attempt + 1} of {attempts - 1} in {wait:.0f}s")
                self.sleep(wait)
        raise AssertionError("unreachable")

    def call(self, method: str, params: list | None = None):
        self._id += 1
        body = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or []}).encode()
        reply = self._send(method, body)
        if "error" in reply:
            err = reply["error"]
            data = err.get("data")
            if isinstance(data, dict):
                data = data.get("data")
            if "revert" in str(err.get("message", "")).lower() or data:
                raise Reverted(_reason(data or ""), data or "")
            raise RpcError(f"{method}: {err.get('message')}")
        return reply["result"]

    def chain_id(self) -> int:
        return int(self.call("eth_chainId"), 16)

    def block(self) -> int:
        return int(self.call("eth_blockNumber"), 16)

    def eth_call(self, to: str, data: bytes) -> bytes:
        return abi.hexdata(self.call("eth_call", [{"to": to, "data": "0x" + data.hex()}, "latest"]))

    def view(self, to: str, signature: str, returns: list, *args) -> list:
        """A view call: 'name(type,...)' with its arguments, decoded as `returns`."""
        return abi.decode(returns, self.eth_call(to, abi.call_data(signature, *args)))

    def logs(self, address: str, from_block: int = 0, topics: list | None = None, to_block=None) -> list:
        """The events `address` emitted from `from_block` to `to_block` (an int; anything else: the latest block, read
        once here), in the chain's order, asked in chunks of at most `log_range` blocks (#312)."""
        end = to_block if isinstance(to_block, int) else self.block()
        out, start = [], max(from_block, 0)
        while start <= end:
            stop = min(end, start + self.log_range - 1)
            q = {"address": address, "fromBlock": hex(start), "toBlock": hex(stop)}
            if topics:
                q["topics"] = topics
            try:
                out.extend(self.call("eth_getLogs", [q]))
            except Unavailable:
                raise
            except RpcError as e:
                smaller = self._smaller_range(f"{e} {getattr(e, 'data', '')}", stop - start + 1)
                if smaller is None:
                    raise
                if self.log:
                    self.log(f"eth_getLogs: the provider refused {stop - start + 1} blocks; asking for {smaller} at a "
                             f"time")
                self.log_range = smaller
                continue  # the same start, a smaller chunk
            start = stop + 1
        return out

    @staticmethod
    def _smaller_range(message: str, asked: int) -> int | None:
        """The chunk to ask for after a refusal of `asked` blocks: half, or a smaller limit the message names (a number
        below `asked`); None when it isn't a range refusal or a single block was refused."""
        if asked <= 1 or not RANGE_REFUSED.search(message):
            return None
        named = [n for n in (int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", message)) if 0 < n < asked]
        return max(1, min([asked // 2] + named[-1:]))


def gas_limit(estimate: int, floor: int | None = None) -> int:
    """A transaction's gas limit: max(estimate × 1.25 + 10,000, floor)."""
    return max(int(estimate * 1.25) + 10_000, int(floor or 0))


class Wallet:
    """An account: signs with its key and sends, then waits for the receipt.

    A transaction is signed once. Until its receipt is seen, the same call (same target, data and value) sends those
    same bytes again, same nonce and same hash, so no retry at any level can make it happen twice.

    The nonce never goes backwards within a process (#251 v3.1 polish VP27): the wallet remembers the next nonce after
    each send a node accepted or mined, and signs with max(that, the RPC's pending count), since a load-balanced public
    RPC may answer the count from a backend that hasn't seen the last transaction yet. A refusal saying the nonce is
    taken (`NONCE_TAKEN`) by bytes that never went out before, whose hash the chain doesn't know, is signed again past
    that nonce, at most NONCE_RETRIES times."""

    def __init__(self, rpc: Rpc, secret: int, role: str = "", poll_s: float | None = None) -> None:
        self.rpc, self._secret, self.role = rpc, secret, role
        self.address = address_of(secret)
        self._unconfirmed: dict = {}  # (to, data, value) -> [the signed bytes, their nonce, whether they may be out]
        self._next_nonce = 0  # the lowest nonce this process may still sign with: past every accepted or mined send
        if poll_s is not None:  # the node's ORACLE_TX_POLL (v3.1 polish VP6); else the class's default
            self.poll_s = float(poll_s)

    def sign(self, digest: bytes) -> bytes:
        """This account's signature over a digest (an EIP-712 one: a join, a usage report)."""
        return _sign(self._secret, digest)

    poll_s = 0.4  # between two looks for a receipt; a test chain that mines at once is asked sooner (tests set it)

    def _used(self, nonce: int) -> None:
        self._next_nonce = max(self._next_nonce, nonce + 1)

    def _known(self, tx_hash: str) -> bool:
        """Whether the chain has this transaction: a receipt, or the transaction itself (pending)."""
        for method in ("eth_getTransactionReceipt", "eth_getTransactionByHash"):
            try:
                if self.rpc.call(method, [tx_hash]):
                    return True
            except Unavailable:
                pass
        return False

    def _host(self) -> str:
        return shown_url(getattr(self.rpc, "url", "") or "") or "the RPC"  # no key in the message (VP20)

    def send(self, to: str, signature: str, *args, value: int = 0, wait: float = 60,
             gas_floor: int | None = None) -> dict:
        """Sends the call and waits for its receipt. The gas limit is the estimate × 1.25 + 10,000, or `gas_floor` if
        that is more (v3.1 polish VP7: `payShadow`'s paying branch, which an estimate can miss; unused gas isn't
        charged). A revert in the estimate raises Reverted and sends nothing."""
        data = abi.call_data(signature, *args)
        key = (to.lower(), data, value)
        spent = False
        for attempt in range(NONCE_RETRIES + 1):
            entry = self._unconfirmed.get(key)
            if entry is None:
                call = {"from": self.address, "to": to, "data": "0x" + data.hex(), "value": hex(value)}
                estimate = int(self.rpc.call("eth_estimateGas", [call]), 16)  # reverts surface here
                gas = gas_limit(estimate, gas_floor)
                pending = int(self.rpc.call("eth_getTransactionCount", [self.address, "pending"]), 16)
                nonce = max(pending, self._next_nonce)  # never backwards, whatever backend answered (VP27)
                gas_price = int(self.rpc.call("eth_gasPrice"), 16)
                entry = [signed_legacy(self._secret, self.rpc.chain_id(), nonce, gas_price, gas, to, value, data),
                         nonce, False]
                self._unconfirmed[key] = entry
            raw, nonce, was_out = entry
            tx_hash = "0x" + keccak256(raw).hex()  # known before it goes out, so a lost answer can't lose it
            try:
                self.rpc.call("eth_sendRawTransaction", ["0x" + raw.hex()])
            except Unavailable:
                entry[2] = True  # it may have arrived: the receipt says
                break
            except RpcError as e:
                message = str(e)
                if not ALREADY_SENT.search(message):
                    self._unconfirmed.pop(key, None)  # refused for good: a later call signs afresh
                    raise
                others = {h.lower() for h in _HASH.findall(message)} - {tx_hash}
                if SAME_TX.search(message) and not others:
                    entry[2] = True  # the node has these very bytes
                    self._used(nonce)
                    break
                if self._known(tx_hash):  # this transaction took the nonce itself: wait for it
                    entry[2] = True
                    break
                if was_out:  # these bytes went out before and the chain may not show them yet: maybe sent
                    spent = True
                    break
                # The nonce went to another transaction (a stale pending count): sign again past it.
                self._unconfirmed.pop(key, None)
                self._used(nonce)
                if attempt == NONCE_RETRIES:
                    raise RpcError(f"{signature.split('(')[0]}: nonce {nonce} for {self.address} refused as taken "
                                   f"{NONCE_RETRIES + 1} times by the chain at {self._host()} ({message}); its pending "
                                   f"nonce count looks stale (a load-balanced RPC?): nothing was sent") from e
                continue
            entry[2] = True
            self._used(nonce)
            break
        return self._wait(key, entry, tx_hash, signature, wait, spent)

    def _wait(self, key, entry, tx_hash: str, signature: str, wait: float, spent: bool) -> dict:
        start = time.time()
        deadline, resent = start + wait, spent  # a maybe-spent nonce isn't sent again
        while time.time() < deadline:
            try:
                receipt = self.rpc.call("eth_getTransactionReceipt", [tx_hash])
            except Unavailable:
                receipt = None
            if receipt:
                self._unconfirmed.pop(key, None)
                self._used(entry[1])
                if int(receipt["status"], 16) != 1:
                    raise Reverted(f"{signature.split('(')[0]} reverted in block {int(receipt['blockNumber'], 16)}",
                                   receipt=receipt)
                return receipt
            if not resent and time.time() - start >= DROPPED_AFTER_S:
                resent = True  # once: no node shows it (dropped, or a backend that never had it): the same bytes again
                try:
                    if self.rpc.call("eth_getTransactionByHash", [tx_hash]) is None:
                        self.rpc.call("eth_sendRawTransaction", ["0x" + entry[0].hex()])
                except RpcError:
                    pass  # Unavailable or a refusal: the receipt still says
            time.sleep(self.poll_s)
        if spent:  # its nonce went to another transaction and this one never ran: a later call signs afresh
            self._unconfirmed.pop(key, None)
        raise Unavailable(f"no receipt for {tx_hash} after {wait:.0f}s")


def call_text(signature: str, args) -> str:
    """A call as a log line names it: `name(arg, ...)`."""
    return f"{signature.split('(')[0]}({', '.join(str(a) for a in args)})"


def _spent(receipt: dict) -> str:
    gas, price = int(receipt.get("gasUsed") or "0x0", 16), int(receipt.get("effectiveGasPrice") or "0x0", 16)
    return f"gas {gas}, {gas * price / 1e18:.9f} ETH"


def tx_line(signature: str, args, receipt: dict) -> str:
    """A mined transaction's log line: its hash, call, block, gas used and ETH cost (v3.1 polish VP10, VP17)."""
    return (f"tx {receipt.get('transactionHash')} {call_text(signature, args)}: block "
            f"{int(receipt.get('blockNumber') or '0x0', 16)}, {_spent(receipt)}")


class LoggedWallet(Wallet):
    """A wallet whose every mined transaction is a log line: its hash, block, gas and ETH (`tx_line`), and a call mined
    but reverted (its gas spent: another keeper came first). The node's and the keeper-only node's wallet (#251 v3.1
    polish VP10). `log` may be set after construction (the node's own log, once the node exists)."""

    def __init__(self, *a, log=None, **kw) -> None:
        super().__init__(*a, **kw)
        self.log = log

    def send(self, to: str, signature: str, *args, **kw) -> dict:
        try:
            r = super().send(to, signature, *args, **kw)
        except Reverted as e:
            if e.receipt is not None and self.log:
                self.log(f"tx {e.receipt.get('transactionHash')} {call_text(signature, args)} mined but reverted in "
                         f"block {int(e.receipt.get('blockNumber') or '0x0', 16)}: {_spent(e.receipt)} spent")
            raise
        if self.log:
            self.log(tx_line(signature, args, r))
        return r
