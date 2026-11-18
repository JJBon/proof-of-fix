"""The seats' registration check (proof-of-fix#210, design D3): a seat's node signs RaceV2's `accept` for a registration
that a `bounty`-labelled issue on its repository validly claims (bot/logic.py's first_valid_claim, the same rule the bot
links by), posts the signature to the exchange under the issue, and the first node to read a quorum relays it.

    ORACLE_REGISTRATION_CHECK  "on" to run it (default off: the owner's kit, seat 6, leaves it off; the seats' host and
                               the local suite turn it on)
    ORACLE_REGISTER_WEIGHT     the registered weight in coins, the same on every seat (default 120: the stub quorum's,
                               so `inflated` stays false against the merge weight 100)
    ORACLE_RELAY_GRACE         seconds a signer that isn't the lowest-addressed waits before it relays (default 30)
    ORACLE_REPO_ID             the repository's id on-chain: its registry id (the record's `repo` for pof-sandbox), or
                               0x0 (the default) for a project outside the registry

Only the fake judge checks registrations, and it passes every claimed one at the fixed weight: the devnet's stand-in
for the judges, signed by the same keys as the stub quorum. With any other judge the node signs nothing and says why
(a real check is #160's). The nonce is keccak256("pof-accept" ‖ race ‖ word(issue)), so every seat signs one digest
without a round. Nothing here registers, funds or judges a fix."""

from __future__ import annotations

import time

from . import crypto, v2
from .judge import FakeJudge
from .rpc import Reverted

DEFAULT_WEIGHT_COINS, DEFAULT_GRACE = 120, 30.0


def same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


class RegistrationCheck:
    def __init__(self, chain, keys, wallet, host, exchange, judge, weight: int, repo_id=v2.ZERO, grace: float = DEFAULT_GRACE,
                 hold: float = 900.0, clock=time.time, log=print, label: str = "bounty") -> None:
        self.chain, self.keys, self.wallet, self.host, self.exchange = chain, keys, wallet, host, exchange
        self.judge, self.weight, self.repo_id, self.grace, self.hold = judge, weight, repo_id, grace, hold
        self.clock, self.log, self.label = clock, log, label
        self.address = keys.address()
        self.done: set = set()  # on-chain issues settled for this run: opened, closed, or not this repository's
        self.signed: set = set()
        self.claimed_since: dict = {}  # issue -> when this node first saw it claimed
        self.quorum_since: dict = {}  # issue -> when this node first read a quorum for it
        self._said: set = set()
        self._domain = None

    def _say(self, key, line: str) -> None:
        if key not in self._said:
            self._said.add(key)
            self.log(line)

    def domain(self) -> bytes:
        if self._domain is None:
            d = self.chain.race_domain()
            if d != v2.race_domain(self.chain.chain_id(), self.chain.race):
                raise RuntimeError("RaceV2's EIP-712 domain isn't v2's: refusing to sign")
            self._domain = d
        return self._domain

    def waiting(self) -> bool:
        """A claimed registration not open yet holds the node from idling, up to `hold` seconds."""
        now = self.clock()
        return any(n not in self.done and now - t < self.hold for n, t in self.claimed_since.items())

    def tick(self, from_block: int) -> bool:
        pending = [e for e in self.chain.registered(from_block) if e["issue"] not in self.done]
        if not pending:
            return False
        progress, issues = False, None
        for e in pending:
            n = e["issue"]
            onchain = self.chain.issue(n)
            if onchain["state"] != v2.POSTED or int(onchain["bounty"]) != 0:
                self.done.add(n)  # opened (or withdrawn, or forfeited): nothing to check
                continue
            if v2.b32(onchain["repo"]) != v2.b32(self.repo_id):
                self.done.add(n)
                continue
            if issues is None:
                from .evidence import host_call  # a host that doesn't answer is NotReady: no progress this pass

                issues = host_call(self.host.issues, "all", self.label)
            from bot import logic  # the claim's rule is the bot's (one rule, two readers: design D2)

            claim = logic.first_valid_claim(issues, {"id": n, "reporter": onchain["reporter"], "repo": onchain["repo"]},
                                            self.repo_id, self.label)
            if claim is None:
                continue  # not claimed (yet): nothing signed for it
            self.claimed_since.setdefault(n, self.clock())
            if not isinstance(self.judge, FakeJudge):  # a model judge: no real registration check yet (#160)
                self._say(("real", n), f"registration {n}: claimed by issue #{claim}; registration check: real judges "
                                       f"not supported yet, nothing signed")
                continue
            progress |= self._advance(n, claim)
        return progress

    def _advance(self, n: int, claim: int) -> bool:
        nonce = v2.accept_nonce(self.chain.race, n)
        digest = v2.accept_digest(self.domain(), n, self.weight, nonce)
        if n not in self.signed:
            self.exchange.put(n, self.address, "accept", {"weight": self.weight, "nonce": "0x" + nonce.hex(),
                                                          "sig": "0x" + self.keys.sign(digest).hex()})
            self.signed.add(n)
            self.log(f"registration {n}: claimed by issue #{claim}; the fake judge passes it: signed its accept "
                     f"(weight {self.weight / 10**6:g})")
            return True
        active = {k.lower() for k in self.chain.keys()}
        sigs = {}
        for node, m in self.exchange.all(n, "accept").items():
            try:
                if m.get("weight") != self.weight or m.get("nonce", "").lower() != "0x" + nonce.hex():
                    continue
                signer = crypto.recover(digest, bytes.fromhex(m["sig"][2:])).lower()
            except (ValueError, TypeError, AttributeError, KeyError):
                continue
            if signer == node.lower() and signer in active:
                sigs[signer] = m["sig"]
        if len(sigs) < self.chain.quorum():
            return False
        now = self.clock()
        self.quorum_since.setdefault(n, now)
        relayer = min(sigs, key=lambda a: int(a, 16))
        if not same(relayer, self.address) and now - self.quorum_since[n] < self.grace:
            return False
        ordered = v2.ordered_signatures(digest, list(sigs.values()))
        try:
            self.wallet.send(self.chain.race, "accept(uint256,uint256,(bytes32,bytes[]))", n, self.weight,
                             (nonce, ordered))
            self.log(f"registration {n}: relayed its accept ({len(ordered)} signatures); its bounty is open")
        except Reverted as e:
            if e.reason != "Refused()":
                raise
            self.log(f"registration {n}: its bounty opened meanwhile (another seat relayed)")
        self.done.add(n)
        return True


def from_env(env, chain, keys, wallet, host, exchange, judge, log=print, clock=time.time):
    """The check, configured from the environment, or None when ORACLE_REGISTRATION_CHECK isn't "on"."""
    if (env.get("ORACLE_REGISTRATION_CHECK") or "off").lower() != "on":
        return None
    weight = int(round(float(env.get("ORACLE_REGISTER_WEIGHT") or DEFAULT_WEIGHT_COINS) * 10**6))
    repo = env.get("ORACLE_REPO_ID") or "0x0"
    repo_id = v2.ZERO if int(repo, 16) == 0 else v2.b32(repo)
    return RegistrationCheck(chain, keys, wallet, host, exchange, judge, weight, repo_id,
                             grace=float(env.get("ORACLE_RELAY_GRACE") or DEFAULT_GRACE), clock=clock, log=log)
