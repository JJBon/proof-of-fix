"""A keeper-only v3 node: the calls anyone may make, with no validator registration (proof-of-fix#251's live Sepolia;
the v3.1 polish's VP10).

    python3 -m oracle.keeper info               the keeper's address, its ETH balance, the deployment and the scan's
                                                start; "not registered (keeper only)"
    python3 -m oracle.keeper run [--from-block N] [--once]
                                                every ORACLE_POLL seconds, one pass of node_v3's keeper (`NodeV3._keep`:
                                                draws and signals, replacements, audits, challenge draws, shadow
                                                settlement, finality, the result, the panels' pay, finish, release,
                                                startWindow, merge, FeesV3's roll), from ORACLE_FROM_BLOCK

A validator's keeper (ORACLE_KEEPER, on by default) makes these calls only while its node runs, and an on-demand
validator runs only for its own seats: nobody draws a new check. This process makes them alone. It needs no TEE, no
bond and no registration, only gas: it holds no key provider, judge, host, exchange or Radicle node, so it never
seals, reveals, judges, calls a model, comments or pushes anything, and it posts no cost table. Its key pays gas only,
so it may be a plain key on any chain: it signs no seal, reveal, receipt, registration or claim.

It is the file the seed host ran (branch keeper-sepolia-local, commit 1ca389d), folded in: its redactor is now the
shared oracle/redact.py, its transaction lines oracle/rpc.py's `LoggedWallet` (the node's wallet logs the same).

Configuration (environment):
    ORACLE_RPC or ORACLE_RPC_SECRET_ARN
                     the chain's JSON-RPC URL, or a Secrets Manager secret holding it (a provider's key in its path);
                     the URL is never logged: every line, tracebacks included, has it replaced by its scheme and host
    ORACLE_RPC_TOKEN, RPC_API_KEY(_SECRET_ARN), ORACLE_RPC_API_KEY_HEADER, ORACLE_RPC_RETRIES, ORACLE_LOG_RANGE
                     as for the node (oracle/__main__.py)
    ORACLE_RACE      the RaceV3
    ORACLE_FROM_BLOCK  the deployment's first block (its record's `block`); unset: found from RaceV3's start
    ORACLE_PRIVATE_KEY or ORACLE_PRIVATE_KEY_SECRET_ARN
                     the keeper's account: it pays the gas and nothing else
    ORACLE_KEEPER_ADDRESS  optional: the address the key must have (a wrong secret stops the keeper at start)
    ORACLE_POLL      seconds between passes (default 120: a free RPC tier's daily credits)
    ORACLE_TX_POLL   seconds between two looks for a transaction's receipt (default 3)
    ORACLE_KEEPER_BUDGET  about this many RPC calls a pass (default 300), then the next pass goes on from there
    ORACLE_KEEPER_MAX_TX_HOUR  the most transactions in any hour (default 60); past it, the pass stops and passes wait
                     until the hour has room, said once an hour (a guard on the account's gas, never reached by a
                     working keeper)"""

from __future__ import annotations

import argparse
import collections
import os
import sys
import time
import traceback

from . import awssecret, crypto, v3
from .models import ModelError
from .node_v3 import KEEPER_BUDGET, NodeV3, SetupError
from .redact import REDACT, load_env
from .rpc import LoggedWallet, Reverted, RpcError, Unavailable

DEFAULT_POLL_S, DEFAULT_TX_POLL_S, DEFAULT_MAX_TX_HOUR = 120.0, 3.0, 60
NOT_REGISTERED = "not registered (keeper only)"


def log(m: str) -> None:
    print(REDACT(f"[keeper] {m}"), flush=True)


class CapReached(RpcError):
    """The hourly transaction cap is reached: nothing was sent, and the pass stops (not a revert: no call counts it)."""


class KeeperWallet(LoggedWallet):
    """The keeper's account: each transaction's hash, block, gas and ETH in the log (`LoggedWallet`), and the hourly
    cap. A send counts toward the cap unless its estimate reverted (nothing was sent, no gas spent: the seed host's
    rule); past the cap a send raises CapReached before anything goes out."""

    def __init__(self, *a, max_per_hour: int = DEFAULT_MAX_TX_HOUR, clock=time.time, **kw) -> None:
        super().__init__(*a, **kw)
        self.max_per_hour, self.clock, self.sent = max_per_hour, clock, collections.deque()

    def room(self) -> bool:
        now = self.clock()
        while self.sent and self.sent[0] <= now - 3600:
            self.sent.popleft()
        return len(self.sent) < self.max_per_hour

    def send(self, to: str, signature: str, *args, **kw) -> dict:
        if not self.room():
            raise CapReached(f"the hourly transaction cap ({self.max_per_hour}) is reached")
        self.sent.append(self.clock())
        try:
            return super().send(to, signature, *args, **kw)
        except Reverted as e:
            if e.receipt is None:  # refused at its estimate: nothing sent, no gas spent
                self.sent.pop()
            raise


class Keeper(NodeV3):
    """NodeV3's keeper alone. Not NodeV3's constructor: the keeper's calls use only the chain, the wallet, the log and
    their own retry state; everything else a node has (its seats, judge, host, receipts, Radicle) is left out, so a
    method that needs it fails loudly instead of acting. No `me()`: it has no registration."""

    def __init__(self, chain: v3.Chain, wallet: KeeperWallet, log=log,
                 budget: int = KEEPER_BUDGET) -> None:  # noqa: super().__init__ on purpose
        self.chain, self.wallet, self.log = chain, wallet, log
        self.address, self.keeper = wallet.address, True
        self.seats, self.verdicts = {}, None
        # NodeV3's keeper state (backoff, gates, scan set and cursors, budget); a section every pass (ORACLE_POLL)
        self._init_keeper_state(every=0, budget=budget)

    def me(self) -> dict:
        raise SetupError(f"{self.address} is a keeper only: it has no validator registration")

    def tick(self, from_block: int) -> bool:
        try:
            if not self.wallet.room():
                raise CapReached("")
            return self._keep_section(from_block, self.chain.now())
        except CapReached:
            self._say(("cap", int(self.wallet.clock() // 3600)),
                      f"the hourly transaction cap ({self.wallet.max_per_hour}) is reached; passes wait for room")
            return False

    def loop(self, from_block: int, poll: float, once: bool = False, sleep=time.sleep) -> None:
        self.log(f"keeping RaceV3 {self.chain.race} on chain {self.chain.chain_id()} from block {from_block} as "
                 f"{self.address}, a pass every {poll:.0f}s")
        while True:
            try:
                if self.tick(from_block):
                    self.log("pass: progress")
            except Unavailable as e:
                self.log(f"the chain isn't answering ({e}); next pass in {poll:.0f}s, nothing is lost")
            except RpcError as e:  # a refusal that isn't a revert (e.g. a provider's limit): logged, tried next pass
                self.log(f"the chain refused a call ({e}); next pass in {poll:.0f}s")
            if once:
                return
            sleep(poll)


def secrets(env) -> None:
    """The secrets (oracle/awssecret.py: the key, the RPC's API key, and the RPC's URL from ORACLE_RPC_SECRET_ARN),
    then the RPC's URL and key loaded into the shared redactor."""
    try:
        awssecret.resolve(env)
    finally:
        load_env(env)


def account(env) -> int:
    raw = (env.get("ORACLE_PRIVATE_KEY") or "").strip()
    if not raw:
        raise SystemExit("keeper: set ORACLE_PRIVATE_KEY or ORACLE_PRIVATE_KEY_SECRET_ARN")
    try:
        secret = int(raw[2:] if raw.startswith("0x") else raw, 16)
    except ValueError:
        raise SystemExit("keeper: ORACLE_PRIVATE_KEY isn't a hex private key") from None
    if not 1 <= secret < crypto.N:
        raise SystemExit("keeper: ORACLE_PRIVATE_KEY isn't a valid key")
    return secret


def registry_state(chain, address: str) -> str:
    state = chain.validator(address)["state"]
    return NOT_REGISTERED if state == 0 else f"registry state {v3.STATES[state]} (a keeper needs none)"


def main(argv: list, env=None, make_chain=None, sleep=time.sleep) -> int:
    """`make_chain(rpc, race)`: the chain to keep (tests give a fake); default v3.Chain."""
    from .__main__ import first_block, rpc_from_env

    ap = argparse.ArgumentParser(prog="python3 -m oracle.keeper")
    ap.add_argument("command", choices=["info", "run"])
    ap.add_argument("--from-block", type=int, help="keep the checks from this block (default: ORACLE_FROM_BLOCK)")
    ap.add_argument("--once", action="store_true", help="one pass, then stop")
    a = ap.parse_args(argv[1:])
    env = os.environ if env is None else env
    try:
        secrets(env)
    except (awssecret.SecretError, ModelError) as e:
        log(f"can't read a secret: {e}")
        return 1
    if not env.get("ORACLE_RPC") or not env.get("ORACLE_RACE"):
        log("set ORACLE_RPC (or ORACLE_RPC_SECRET_ARN) and ORACLE_RACE")
        return 2
    rpc = rpc_from_env(env)
    rpc.log = log
    wallet = KeeperWallet(rpc, account(env), "keeper", log=log,
                          max_per_hour=int(env.get("ORACLE_KEEPER_MAX_TX_HOUR") or DEFAULT_MAX_TX_HOUR))
    wallet.poll_s = float(env.get("ORACLE_TX_POLL") or DEFAULT_TX_POLL_S)
    want = (env.get("ORACLE_KEEPER_ADDRESS") or "").strip()
    if want and want.lower() != wallet.address.lower():
        log(f"the key's address is {wallet.address}, not ORACLE_KEEPER_ADDRESS {want}: stopping")
        return 1
    chain = (make_chain or v3.Chain)(rpc, env["ORACLE_RACE"])
    chain.first_block = first_block(chain, env, log)
    start = max(a.from_block if a.from_block is not None else chain.first_block, chain.first_block)
    if a.command == "info":
        bal = int(rpc.call("eth_getBalance", [wallet.address, "latest"]), 16)
        log(f"keeper {wallet.address} on chain {chain.chain_id()}, RaceV3 {chain.race}, block {rpc.block()}; "
            f"balance {bal / 1e18:.6f} ETH; scans from block {start}; {registry_state(chain, wallet.address)}")
        return 0
    keeper = Keeper(chain, wallet, budget=int(env.get("ORACLE_KEEPER_BUDGET") or KEEPER_BUDGET))
    keeper.loop(start, float(env.get("ORACLE_POLL") or DEFAULT_POLL_S), once=a.once, sleep=sleep)
    return 0


def entry(argv: list) -> int:
    """`python3 -m oracle.keeper`: main, and on anything unexpected the traceback, redacted, then a failure systemd
    restarts."""
    try:
        return main(argv)
    except KeyboardInterrupt:
        return 130
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        print(REDACT(traceback.format_exc()), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(entry(sys.argv))
