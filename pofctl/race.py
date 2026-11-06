"""The deployed race, as pofctl reads and drives it: the deployment record, the views (quote, bounty, submission,
balances, the seats), the actions each role takes, the stub quorum's signed verdicts (devnet only), the join flow, and
the events, decoded. v2 (#85: RaceV2, Verdicts, the meter, QuoterV2; coin only) by default; v1 (Race, Quoter) with
version=1.

v2's checks are metered (task 5.7): the solver's deposit is the meter's maximum, the judges `Verdicts.drawn` names for
the submission report their usage (Fees.report) and sign the verdict v2 with an empty fee list, and the meter charges
each counted judge its usage plus the service fee; the rest returns. The verdict's struct and digests are the node's
(oracle/v2.py), so the stub quorum and a real node sign the same bytes."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from oracle import v2
from oracle.crypto import DOMAIN_TYPEHASH, FEE_TYPEHASH, NAME_HASH, RESULT_TYPEHASH, keccak256, sign, word
from oracle.crypto import address as address_of
from oracle.crypto import checksum

from . import abi
from .rpc import Rpc, Wallet

ROOT = Path(__file__).resolve().parent.parent
RECORDS = {2: ROOT / "contracts" / "deployments" / "devnet-v2.json", 1: ROOT / "contracts" / "deployments" / "devnet.json"}
C = 10**6
MAX = 2**256 - 1
STATES = ["None", "Open", "Won", "Merged", "Paid", "Refunded", "Unsolved"]
OUTCOMES = ["None", "Pass", "Fail", "Duplicate", "Split", "TimedOut"]
ISSUE_STATES = ["None", "Posted", "Rewarded", "Returned", "Forfeited"]
PASS, FAIL = 1, 2
ORACLE_FEE = 300_000  # each signing oracle's fee, from the check deposit (as the loop's v1 script pays it)

SIGNED = "(bytes32,bytes[])"
FEES = "(address,uint256)[]"
QUOTE_V1 = ["(uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,"
            "uint256,uint256,uint256)"]
QUOTE_FIELDS_V1 = ["state", "day", "locked", "offerBps", "cap", "price", "instalments", "instalment", "lastInstalment",
                   "finderFee", "attempting", "sunsetDay", "attemptFee", "checkDeposit", "evaluationFee", "appealFee"]
QUOTE = ["(uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256,"
         "uint256,bool,uint256,uint256,uint256,uint256)"]
QUOTE_FIELDS = ["state", "day", "locked", "offerBps", "cap", "price", "instalments", "instalment", "lastInstalment",
                "finderFee", "attempting", "sunsetDay", "attemptFee", "checkDeposit", "metered", "serviceFee",
                "judges", "evaluationFee", "appealFee"]
BOUNTY, BOUNTY_FIELDS = v2.BOUNTY, v2.BOUNTY_FIELDS
SUBMISSION_V1 = ["(uint256,uint256,address,bytes32,address,uint256,uint8,bytes32,bool)"]
SUBMISSION_FIELDS_V1 = ["bounty", "day", "solver", "commitment", "coin", "deposit", "outcome", "fix", "appealed"]
ISSUE_V1 = ["(address,address,uint256,uint256,uint256,uint8)"]
ISSUE_FIELDS_V1 = ["reporter", "coin", "registration", "stake", "bounty", "state"]
AWARD = ["address", "bytes32", "uint256", "bool", "uint256"]
SEAT = ["(address,bytes32,bytes32,bytes32,bytes32,uint64)"]
SEAT_FIELDS = ["key", "family", "provider", "image", "attestation", "suspendedFrom"]
ROTATION = ["address", "bytes32", "bytes32", "bytes32", "uint64"]

ACCEPT_TYPEHASH = keccak256(b"Accept(uint256 issue,uint256 weight,bytes32 nonce)")
MERGED_TYPEHASH_V1 = keccak256(b"Merged(uint256 bounty,uint256 submission,uint256 weight,bytes32 nonce)")

# The events pofctl's history shows: signature -> (name, indexed fields, data fields).
EVENTS = {
    "Registered(uint256,address)": ("Registered", ["issue", "reporter"], []),
    "BountyOpened(uint256,uint256)": ("BountyOpened", ["bounty", "issue"], []),
    "StateChanged(uint256,uint8)": ("StateChanged", ["bounty"], ["state"]),
    "Locked(uint256,uint256)": ("Locked", ["bounty"], ["bps"]),
    "Attempted(uint256,address)": ("Attempted", ["bounty", "solver"], []),
    "Committed(uint256,uint256,address)": ("Committed", ["bounty", "submission", "solver"], []),
    "TooLate(uint256,address)": ("TooLate", ["bounty", "solver"], []),
    "Decided(uint256,uint8)": ("Decided", ["submission"], ["outcome"]),
    "Awarded(uint256,uint256,address)": ("Awarded", ["bounty", "epoch"], ["winner"]),
    "ClawedBack(uint256,uint256,uint256)": ("ClawedBack", ["bounty", "epoch"], ["earned"]),
    "IssueClosed(uint256,uint8)": ("IssueClosed", ["issue"], ["state"]),
    "Pledged(uint256,address,address,uint256)": ("Pledged", ["bounty", "coin", "funder"], ["amount"]),
    "Paid(uint256,address,address,uint256)": ("Paid", ["bounty", "coin", "to"], ["amount"]),
    "Refunded(uint256,address,address,uint256)": ("Refunded", ["bounty", "coin", "funder"], ["amount"]),
    "Withdrawn(address,address,address,uint256)": ("Withdrawn", ["account", "coin"], ["to", "amount"]),
}
# The seats' and the meter's events (v2): the join flow, the usage reports and the charges.
SEAT_EVENTS = {
    "KeyPublished(uint256,address,bytes32,bytes32,bytes32,uint256)": (
        "KeyPublished", ["seat", "key"], ["image", "attestationType", "attestation", "effectiveAt"]),
    "KeyActivated(uint256,address,address)": ("KeyActivated", ["seat", "oldKey", "newKey"], []),
}
METER_EVENTS = {
    "Reported(uint256,address,address,bytes32)": ("Reported", ["submission", "judge"], ["payee", "receipt"]),
    "Charged(uint256,uint256,uint256)": ("Charged", ["submission"], ["judges", "amount"]),
}
_ALL_EVENTS = {**EVENTS, **SEAT_EVENTS, **METER_EVENTS}
_TOPICS = {"0x" + keccak256(sig.encode()).hex(): spec for sig, spec in _ALL_EVENTS.items()}
_ADDRESSES = {"reporter", "solver", "winner", "coin", "funder", "to", "account", "key", "oldKey", "newKey", "judge",
              "payee"}
_BYTES32 = {"image", "attestationType", "attestation", "receipt"}


def load_record(version: int = 2, path: str | None = None) -> dict:
    p = Path(path) if path else RECORDS[version]
    if not p.exists():
        cmd = "deploy-v2" if version == 2 else "deploy"
        raise FileNotFoundError(f"no deployment record at {p}: run scripts/devnet.sh {cmd}")
    return json.loads(p.read_text(encoding="utf-8"))


def fmt(micro: int) -> str:
    """Micro-coins as coins with 6 decimals."""
    return f"{micro / C:,.6f}"


@dataclass
class Signers:
    """The stub quorum: oracle keys that sign on a devnet. A real validator runs oracle/ (python3 -m oracle run)."""
    secrets: list

    def addresses(self) -> dict:
        return {address_of(k).lower(): k for k in self.secrets}


class Race:
    def __init__(self, rpc: Rpc, record: dict, version: int = 2) -> None:
        self.rpc, self.record, self.version = rpc, record, version
        self.address, self.coin, self.quoter = record["race"], record["coin"], record["quoter"]
        self.oracle_set = record.get("verdicts", self.address) if version == 2 else self.address
        self.meter = record.get("meter") if version == 2 else None
        self._chain_id = None

    # ---------- views ----------

    def chain_id(self) -> int:
        if self._chain_id is None:
            self._chain_id = self.rpc.chain_id()
        return self._chain_id

    def day(self) -> int:
        return self.rpc.view(self.address, "day()", ["uint256"])[0]

    def quote(self, bounty: int) -> dict:
        types, names = (QUOTE, QUOTE_FIELDS) if self.version == 2 else (QUOTE_V1, QUOTE_FIELDS_V1)
        q = self.rpc.view(self.quoter, "quote(address,uint256,address)", types, self.address, bounty, self.coin)[0]
        out = dict(zip(names, q))
        out["state"] = STATES[out["state"]]
        return out

    def bounty(self, b: int) -> dict:
        fields = dict(zip(BOUNTY_FIELDS, self.rpc.view(self.address, "bounty(uint256)", BOUNTY, b)[0]))
        fields["state"] = STATES[fields["state"]]
        return fields

    def submission(self, s: int) -> dict:
        types, names = (v2.SUBMISSION, v2.SUBMISSION_FIELDS) if self.version == 2 else (SUBMISSION_V1,
                                                                                         SUBMISSION_FIELDS_V1)
        fields = dict(zip(names, self.rpc.view(self.address, "submission(uint256)", types, s)[0]))
        fields["outcome"] = OUTCOMES[fields["outcome"]]
        return fields

    def issue(self, i: int) -> dict:
        types, names = (v2.ISSUE, v2.ISSUE_FIELDS) if self.version == 2 else (ISSUE_V1, ISSUE_FIELDS_V1)
        fields = dict(zip(names, self.rpc.view(self.address, "issue(uint256)", types, i)[0]))
        fields["state"] = ISSUE_STATES[fields["state"]]
        return fields

    def award(self, b: int, epoch: int) -> dict:
        winner, fix, window_end, closed, earned = self.rpc.view(self.address, "awards(uint256,uint256)", AWARD, b,
                                                               epoch)
        return {"winner": winner, "fix": fix, "windowEnd": window_end, "closed": closed, "earned": earned}

    def config(self) -> dict:
        names = ["infrastructure", "insurance", "registrationFee", "issueStake", "attemptFee", "evaluationFee",
                 "checkDeposit", "appealFee", "appealDeposit", "startPriceBps", "riseBpsPerDay", "finderFeeBps",
                 "idleDays", "resultDays", "mergeDays", "windowDays", "releaseEveryDays", "instalments"]
        types = ["(address,address," + ",".join(["uint256"] * 16) + ")"]
        return dict(zip(names, self.rpc.view(self.address, "getConfig()", types)[0]))

    def coin_balance(self, who: str) -> int:
        return self.rpc.view(self.coin, "balanceOf(address)", ["uint256"], who)[0]

    def owed(self, who: str) -> int:
        """Credit the contract holds for `who` in the fee coin (withdraw() pays it out)."""
        return self.rpc.view(self.address, "owed(address,address)", ["uint256"], who, self.coin)[0]

    def allowance(self, who: str) -> int:
        return self.rpc.view(self.coin, "allowance(address,address)", ["uint256"], who, self.address)[0]

    def quorum(self) -> int:
        return self.rpc.view(self.oracle_set, "quorum()", ["uint256"])[0]

    def is_oracle(self, who: str) -> bool:
        return self.rpc.view(self.oracle_set, "isOracle(address)", ["bool"], who)[0]

    def oracle_keys(self) -> list:
        if self.version == 2:
            return [checksum(a) for a in self.rpc.view(self.oracle_set, "keys()", ["address[]"])[0]]
        return list(self.record.get("oracles", []))

    # ---------- v2: the draw, the seats and the meter ----------

    def drawn(self, s: int) -> tuple:
        """(the judges Verdicts draws for submission s, the keys recused): only they report and sign its verdict."""
        sub = self.submission(s)
        judges, recused = self.rpc.view(self.oracle_set, "drawn(bytes32,uint256,uint256,address)",
                                        ["address[]", "address[]"], v2.b32(sub["seed"]), sub["bounty"], s,
                                        self.address)
        return [checksum(a) for a in judges], [checksum(a) for a in recused]

    def seat_count(self) -> int:
        return self.rpc.view(self.oracle_set, "seatCount()", ["uint256"])[0]

    def seat(self, i: int) -> dict:
        out = dict(zip(SEAT_FIELDS, self.rpc.view(self.oracle_set, "seat(uint256)", SEAT, i)[0]))
        out["key"] = checksum(out["key"])
        out["active"] = self.rpc.view(self.oracle_set, "isActive(uint256)", ["bool"], i)[0]
        key, image, att_type, att, at = self.rpc.view(self.oracle_set, "pending(uint256)", ROTATION, i)
        out["pending"] = None if int(key, 16) == 0 else {"key": checksum(key), "effectiveAt": at}
        return out

    def seats(self) -> list:
        return [self.seat(i) for i in range(self.seat_count())]

    def seat_of_key(self, key: str) -> int | None:
        for i, st in enumerate(self.seats()):
            if st["key"].lower() == key.lower() or (st["pending"] and st["pending"]["key"].lower() == key.lower()):
                return i
        return None

    def rotate_digest(self, seat: int, key: str, nonce: bytes) -> bytes:
        """Verdicts.rotateDigest for the devnet's image and no attestation, read from the contract and checked against
        the node's encoding (oracle/v2.py), so what an engineer signs is what the contract checks."""
        sig = "rotateDigest(uint256,address,bytes32,bytes32,bytes32,bytes32)"
        on_chain = v2.b32(self.rpc.view(self.oracle_set, sig, ["bytes32"], seat, key, v2.DEVNET_IMAGE,
                                        v2.NO_ATTESTATION, v2.ZERO, nonce)[0])
        local = v2.rotate_digest(v2.verdicts_domain(self.chain_id(), self.oracle_set), seat, key, nonce)
        if on_chain != local:
            raise RuntimeError("Verdicts' rotate digest differs from pofctl's: refusing to sign")
        return on_chain

    def service_fee(self) -> int:
        return self.rpc.view(self.meter, "serviceFee()", ["uint256"])[0]

    def profile(self, repo=v2.ZERO) -> dict:
        image, mv, mem, timeout = self.rpc.view(self.meter, "profileOf(bytes32)", v2.PROFILE, v2.b32(repo))[0]
        return {"image": image, "milliVcpus": mv, "memoryMb": mem, "timeoutSeconds": timeout}

    def reports(self, s: int) -> list:
        rows = self.rpc.view(self.meter, "reports(uint256)", v2.REPORTS, s)[0]
        return [{"judge": checksum(j), "payee": checksum(p), "family": f, "usage": u} for j, p, f, u in rows]

    def meter_events(self, from_block: int | None = None) -> list:
        return self._events(self.meter, from_block)

    def seat_events(self, from_block: int | None = None) -> list:
        return self._events(self.oracle_set, from_block)

    # ---------- actions ----------

    def _approve(self, w: Wallet) -> None:
        if self.allowance(w.address) < 10**30:
            w.send(self.coin, "approve(address,uint256)", self.address, MAX)

    def mint(self, w: Wallet, to: str, amount: int) -> dict:
        """The devnet's test coin: anyone mints (never a public chain, rule 1)."""
        return w.send(self.coin, "mint(address,uint256)", to, amount)

    def register(self, w: Wallet, repo=v2.ZERO) -> int:
        """v2: an issue in `repo`, a repository of the head registry, or 0 for a project outside it (a GitHub repo)."""
        self._approve(w)
        if self.version == 2:
            receipt = w.send(self.address, "register(address,bytes32)", self.coin, v2.b32(repo))
        else:
            receipt = w.send(self.address, "register(address)", self.coin)
        return self._topic(receipt, "Registered(uint256,address)", 1)

    def pledge(self, w: Wallet, b: int, amount: int) -> dict:
        self._approve(w)
        return w.send(self.address, "pledge(uint256,address,uint256)", b, self.coin, amount)

    def attempt(self, w: Wallet, b: int) -> dict:
        self._approve(w)
        return w.send(self.address, "attempt(uint256,address)", b, self.coin)

    def commit(self, w: Wallet, b: int, commitment: bytes) -> int:
        self._approve(w)
        receipt = w.send(self.address, "commit(uint256,bytes32,address)", b, commitment, self.coin)
        return self._topic(receipt, "Committed(uint256,uint256,address)", 2)

    def settle(self, w: Wallet, b: int) -> dict:
        return w.send(self.address, "settle(uint256,address)", b, self.coin)

    def claim_refund(self, w: Wallet, b: int) -> dict:
        return w.send(self.address, "claimRefund(uint256,address)", b, self.coin)

    def withdraw(self, w: Wallet, to: str | None = None) -> dict:
        return w.send(self.address, "withdraw(address,address)", self.coin, to or w.address)

    def rotate(self, relayer: Wallet, seat: int, key: str, nonce: bytes, sigs: list) -> dict:
        return relayer.send(self.oracle_set, "rotate(uint256,address,bytes32,bytes32,bytes32,bytes32,bytes[])", seat,
                            key, v2.DEVNET_IMAGE, v2.NO_ATTESTATION, v2.ZERO, nonce, sigs)

    def activate(self, w: Wallet, seat: int) -> dict:
        return w.send(self.oracle_set, "activate(uint256)", seat)

    # ---------- the stub quorum (devnet only) ----------

    def domain(self) -> bytes:
        version = keccak256(str(self.version).encode())
        return keccak256(DOMAIN_TYPEHASH + NAME_HASH + version + word(self.chain_id()) + word(self.address))

    def _signed(self, signers: Signers, struct: bytes, nonce: bytes) -> tuple:
        digest = keccak256(b"\x19\x01" + self.domain() + struct)
        by_address = sorted(((address_of(k), k) for k in signers.secrets), key=lambda a: int(a[0], 16))
        return nonce, [sign(k, digest) for _, k in by_address]

    def signer_addresses(self, signers: Signers) -> list:
        return sorted((address_of(k) for k in signers.secrets), key=lambda a: int(a, 16))

    def accept(self, relayer: Wallet, signers: Signers, issue: int, weight: int) -> int:
        nonce = secrets.token_bytes(32)
        auth = self._signed(signers, keccak256(ACCEPT_TYPEHASH + word(issue) + word(weight) + nonce), nonce)
        receipt = relayer.send(self.address, f"accept(uint256,uint256,{SIGNED})", issue, weight, auth)
        return self._topic(receipt, "BountyOpened(uint256,uint256)", 1)

    def drawn_signers(self, signers: Signers, s: int) -> list:
        """The stub quorum's keys among the judges drawn for s, in address order: the ones that may report and sign."""
        judges, _ = self.drawn(s)
        held = signers.addresses()
        return [(j, held[j.lower()]) for j in sorted(judges, key=lambda a: int(a, 16)) if j.lower() in held]

    def report_usage(self, relayer: Wallet, s: int, judge_key: int, usage: v2.Usage) -> dict:
        """A drawn judge's signed usage, relayed to the meter (anyone can relay it)."""
        digest = v2.usage_digest(v2.fees_domain(self.chain_id(), self.meter), s, usage)
        return relayer.send(self.meter, f"report(uint256,{v2.USAGE},bytes)", s, usage.as_tuple(),
                            sign(judge_key, digest))

    def result(self, relayer: Wallet, signers: Signers, s: int, outcome: int, fix: bytes, fee: int = ORACLE_FEE,
               base: bytes = v2.ZERO, usage: v2.Usage | None = None) -> dict:
        if self.version == 1:
            return self._result_v1(relayer, signers, s, outcome, fix, fee)
        sub = self.submission(s)
        judges = self.drawn_signers(signers, s)
        if len(judges) < v2.ISSUE_QUORUM:
            raise RuntimeError(f"submission {s}'s drawn judges are {', '.join(a for a in self.drawn(s)[0])}: the stub "
                               f"quorum holds {len(judges)} of their keys, and 2 must sign")
        receipts = {}
        for addr, key in judges:  # each counted judge's usage, before the result (the meter charges at the result)
            receipt = keccak256(b"pofctl stub receipt" + word(s) + word(addr))
            receipts[addr] = receipt.hex()
            self.report_usage(relayer, s, key, usage or stub_usage(receipt))
        rh = v2.receipts_hash(receipts)
        issue = self.issue(self.bounty(sub["bounty"])["issue"])
        v = v2.Verdict(v2.b32(issue["repo"]), base, fix, sub["bounty"], s, outcome, rh, v2.b32(sub["seed"]),
                       secrets.token_bytes(32))
        digest = v2.result_digest(self.domain(), v)
        sigs = [sign(k, digest) for _, k in judges]
        return relayer.send(self.address, f"result({v2.VERDICT},{FEES},bytes[])", v.as_tuple(), [], sigs)

    def _result_v1(self, relayer: Wallet, signers: Signers, s: int, outcome: int, fix: bytes, fee: int) -> dict:
        b = self.submission(s)["bounty"]
        fees = [(a, fee) for a in self.signer_addresses(signers)]
        fees_hash = keccak256(b"".join(keccak256(FEE_TYPEHASH + word(to) + word(amt)) for to, amt in fees))
        nonce = secrets.token_bytes(32)
        struct = keccak256(RESULT_TYPEHASH + word(s) + word(b) + word(outcome) + fix + fees_hash + nonce)
        auth = self._signed(signers, struct, nonce)
        return relayer.send(self.address, f"result(uint256,uint8,bytes32,{FEES},{SIGNED})", s, outcome, fix, fees,
                            auth)

    def merged(self, relayer: Wallet, signers: Signers, b: int, weight: int) -> dict:
        winner = self.bounty(b)["winner"]
        if self.version == 1:
            nonce = secrets.token_bytes(32)
            auth = self._signed(signers, keccak256(MERGED_TYPEHASH_V1 + word(b) + word(winner) + word(weight) + nonce),
                                nonce)
            return relayer.send(self.address, f"merged(uint256,uint256,uint256,{SIGNED})", b, winner, weight, auth)
        sub = self.submission(winner)
        judges = self.drawn_signers(signers, winner)
        if len(judges) < v2.ISSUE_QUORUM:
            raise RuntimeError(f"submission {winner}'s drawn judges: the stub quorum holds {len(judges)} of their keys")
        issue = self.issue(self.bounty(b)["issue"])
        v = v2.Verdict(v2.b32(issue["repo"]), v2.b32(sub["base"]), v2.b32(sub["fix"]), b, winner, PASS,
                       v2.b32(sub["receipt"]), v2.b32(sub["seed"]), secrets.token_bytes(32))
        digest = v2.merged_digest(self.domain(), v, weight)
        return relayer.send(self.address, f"merged({v2.VERDICT},uint256,bytes[])", v.as_tuple(), weight,
                            [sign(k, digest) for _, k in judges])

    # ---------- events ----------

    def _topic(self, receipt: dict, event: str, index: int) -> int:
        topic0 = "0x" + keccak256(event.encode()).hex()
        for log in receipt["logs"]:
            if log["topics"] and log["topics"][0] == topic0:
                return int(log["topics"][index], 16)
        raise RuntimeError(f"no {event} in the receipt")

    def history(self, from_block: int | None = None) -> list:
        return self._events(self.address, from_block)

    def _events(self, address: str, from_block: int | None = None) -> list:
        start = self.record.get("block", 0) if from_block is None else from_block
        out = []
        for log in self.rpc.logs(address, start):
            spec = _TOPICS.get(log["topics"][0]) if log["topics"] else None
            if not spec:
                continue
            name, indexed, data = spec
            fields = {}
            for i, f in enumerate(indexed):
                raw = int(log["topics"][i + 1], 16)
                fields[f] = checksum("0x%040x" % raw) if f in _ADDRESSES else raw
            types = ["address" if f in _ADDRESSES else "bytes32" if f in _BYTES32 else "uint256" for f in data]
            values = abi.decode(types, abi.hexdata(log["data"]))
            fields.update((f, checksum(v) if f in _ADDRESSES else v) for f, v in zip(data, values))
            if name == "StateChanged":
                fields["state"] = STATES[fields["state"]]
            if name == "Decided":
                fields["outcome"] = OUTCOMES[fields["outcome"]]
            if name == "IssueClosed":
                fields["state"] = ISSUE_STATES[fields["state"]]
            out.append({"block": int(log["blockNumber"], 16), "event": name, **fields})
        return out


def stub_usage(receipt: bytes) -> v2.Usage:
    """The stub quorum's usage for one judge: a small check (about a fake judge's prompt and answer, a 20-second
    test run at the default CI profile, 1 MB of receipt). A real node reports what it measured."""
    return v2.Usage(receipt, 3_000, 0, 200, 40, 80, 1)


def fix_of(commit_sha: str, version: int = 2) -> bytes:
    """A fix's hash on-chain. v2: its git commit id as bytes32, as Heads keeps commits (a SHA-1 left-aligned), which a
    GitHub pull request reports as its head. v1: keccak256 of the commit id (the loop's v1 oracle hashed the tree)."""
    if version == 2:
        return v2.commit_word(commit_sha)
    return keccak256(commit_sha.strip().lower().encode())


def commitment(fix: bytes, salt: bytes, solver: str) -> bytes:
    """keccak256(abi.encode(fix, salt, solver)): the sealed submission (RaceV2.commit's tests seal it the same way)."""
    return keccak256(fix + salt + word(solver))
