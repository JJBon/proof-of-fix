"""The v3 validator node (proof-of-fix#139, task 4.1 of #132, on #138's contracts): a validator's process that
registers itself, judges when Panels draws it, and keeps the version's clockwork moving.

What it does:

1. `register` and `leave` (and `withdraw_bond`): the registration is signed by the node's key and bonded from its
   account; on a devnet the `simulated` proof type's attestation is a quote from the dstack simulator (D18).
2. Every seat Panels gives its key (the `Seated` events), whatever the panel's kind:
   - counted: one of the k judges whose reveals decide the verdict;
   - shadow: a candidate's (or a barred family's) unpaid verdict, on a drawn submission or on one that waits for a
     panel; it seals in the counted panel's seal window, and no counted reveal is taken while it still may (#311);
   - audit: a one-seat panel checking a counted verdict;
   - challenge: a fresh panel (larger, or of the verdict's size under the deployment's `Same` rule, #251 L24), which
     also names the original judges' false receipts (the mask).
   For each: the check (the fix's tests in the sandbox and the judge, as in v2; a registration check: the issue that
   claims the registration, on the host or on Radicle, judged a genuine bug report in scope or not), a receipt,
   then its seal, and once the reveal opens its receipt's hash and its reveal, all on-chain through the `onchain`
   transport, and its usage report to RaceV3. Seals always go out before reveals in a pass. Since #311 a judging
   panel's reveal opens as soon as every seat (and, for a counted panel, every shadow drawn with it) has sealed, not
   at the end of the seal window; the node reveals then.
3. Its cost table, once a pricing period: its own shared-unit costs and every family's public list price (D9, D19).
4. The keeper's calls anyone may make (ORACLE_KEEPER, on by default): draws, replacements, audits, challenge draws,
   shadow settlement, finality, the result, the panels' pay, FeesV3's signals and roll; since #251's contract batch 2
   also the merge of a claimed fix once its verdict is final (L9: the head moves then, not at the claim), the release
   of a stuck panel or of audits nobody can take (L19), the redraw of a waiting submission at its scheduled time, and
   the refund of a check Panels released for good or parked at its deadline (RaceV3.release); since batch 4 (L25)
   the redraw of a waiting challenge at its retry time, the release of a stuck challenge panel, the lapse of a
   challenge past CHALLENGE_DEADLINE with no panel, the race's settlement of a filed challenge's lapse
   (`settleLapse`: its stake and cover back) and the pay of a released challenge panel's revealed seats.
5. `challenge`: re-runs a counted verdict's check and, if it disagrees or finds a false receipt, files a challenge
   with its evidence.

A node signs one seal, one reveal, one receipt and one usage report per seat (two contents for one subject are
provable equivocation, the whole bond). What it sealed is on its own disk before the seal leaves (oracle/rounds.py),
so a restarted node reveals the same vote with the same salt.

Time is the chain's (the latest block's timestamp): Panels' windows are in it."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from . import delegates, evidence, rebase_v3, receipt as receipts, v2, v3
from .crypto import checksum, keccak256, word
from .judge import MAX_ISSUE_CHARS, case_for, refused, refused_registration, registration_case
from .models import ModelError
from .node_v2 import CHECKER_IMAGE, NodeV2, same
from .rpc import Reverted, Unavailable
from .sandbox import TestRun, nothing_ran

RECEIPT_VERSION = "pof-receipt-v3-1"
REFUSED_BACKEND = "node:evidence-refused"  # oracle/judge.py `refused`: no model call, the reason in its answer
EVIDENCE_VERSION = "pof-challenge-evidence-1"
REGISTRATION_NOTE = b"proof-of-fix v3 registration"
# The quotes each proof type takes: a TEE's from dstack (Intel TDX) or from an AMD SEV-SNP guest (oracle/snp.py, #253)
QUOTE_KINDS = {v3.PROOF_SIMULATED: ("dstack-simulator",), v3.PROOF_TEE: ("dstack-tdx", "amd-sev-snp")}
ROLES = {v3.COUNTED: "a counted judge", v3.SHADOW: "a shadow", v3.AUDIT: "an auditor",
         v3.CHALLENGE: "a challenge judge"}
SHARED_UNITS = ("vcpu_second", "gb_second", "storage_mb", "eth")
# The families' names (D19: the provider's model line) for the public list prices in pof/costs.py.
LIST_NAMES = {"anthropic": "anthropic/claude", "openai": "openai/gpt", "google": "google/gemini",
              "deepseek": "deepseek/deepseek", "qwen": "alibaba/qwen", "mistral": "mistral/mistral",
              "llama": "meta/llama"}
SEAL_MARGIN_S = 600.0  # a check that still can't be run this long before the seal deadline is sealed as not passed
REPORT_WINDOW_S = 86400  # RaceV3's REPORT_WINDOW: a panel is paid without the reports missing after it
AUDIT_TRIES = 3  # drawAudits calls per state of the registry while no auditor can be drawn
CHALLENGE_TRIES = 3  # drawChallenge calls per state of the challenge, the registry and the capacity window
# lapseChallenge and settleLapse calls per state (#251 batch 4, L25): a lapse is due once past CHALLENGE_DEADLINE with
# no panel, and the race's settlement once per lapse of a filed challenge
LAPSE_TRIES = 3
# The keeper's retry model (v3.1 polish VP6; #314, audit F4/F5). A refusal for one of these reasons says "not yet" or
# "nothing to do now": it doesn't count toward giving up. Any other refusal of a once-only call starts GIVE_UP_S of
# chain time, after which the call is left to others.
GATED_REFUSALS = frozenset({"NotYet", "NotReady", "TooEarly", "NothingDue", "NothingChanged", "ShortOfGas"})
GIVE_UP_S = 86_400
# Every refused call waits min(BACKOFF_BASE_S × 2^(n-1), BACKOFF_MAX_S) before its next try; n starts again when the
# call's state fingerprint changes (the registry's epoch, the capacity window, FeesV3's `rolled`, the verdict's status)
BACKOFF_BASE_S, BACKOFF_MAX_S = 30, 3600
# payShadow's gas limit at least this: ≥ 2× its paying branch under EIP-8037 (≈418k: 222k + 2 new slots × 97,920,
# PolishV31's test_payShadowsPayingBranchGas), so the call takes the paying branch, not the catch (VP7, #325)
PAY_SHADOW_GAS_FLOOR = 850_000
ROLL_PARTS_PER_PASS = 10  # FeesV3.rollPart calls a keeper section makes at most (VP8)
KEEPER_BUDGET = 300  # about this many RPC calls a keeper section, then the next one goes on from there
KEEPER_TX_CALLS = 6  # what one mined transaction costs in RPC calls, about (estimate, nonce, price, send, receipts)
RATE_PAUSE_MAX_S = 600  # the longest keeper pause after an Unavailable (HTTP 429) without Retry-After
SCAN_REREAD = 64  # events at an event list's end taken again each section (a reorg may change the list's tail)
# A model family's name (#251 v3.1 polish VP12): the provider's model line, `provider/line` ("anthropic/claude")
FAMILY_FORM = re.compile(r"^[a-z0-9][a-z0-9-]*/[a-z0-9][a-z0-9.-]*$")


class SetupError(RuntimeError):
    """The node can't act as the validator its registration says it is."""


class _Metered:
    """The chain as a keeper section reads it: each call of one of its methods counts toward the section's budget
    (about one RPC call each). Everything else is the chain's own."""

    def __init__(self, chain, node) -> None:
        self.__dict__.update(_chain=chain, _node=node)

    def __getattr__(self, name):
        attr = getattr(self._chain, name)
        if not callable(attr):
            return attr
        node = self._node

        def metered(*args, **kw):
            node._spent += 1
            return attr(*args, **kw)
        return metered

    def __setattr__(self, name, value) -> None:
        setattr(self._chain, name, value)


def _what(key) -> str:
    """A keeper call's key, (to, signature, args), as the log says it."""
    if isinstance(key, tuple) and len(key) == 3 and isinstance(key[1], str) and "(" in key[1]:
        return f"{key[1].split('(')[0]}({', '.join(str(a) for a in key[2])})"
    return str(key)


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def default_list_prices() -> dict:
    """Every family's public list price: {name: [input, cached, output]} in micro-coins per million tokens, from
    pof/costs.py (the providers' price lists as read on the date that file states)."""
    from pof import costs

    return {LIST_NAMES[f]: [round(m.input * 10**6), round(m.cached * 10**6), round(m.output * 10**6)]
            for f, m in costs.JUDGE.items() if f in LIST_NAMES}


def build_table(chain, costs: dict | None, list_prices: dict, log=None, priced_only: bool = False) -> tuple:
    """(shared, families, tokens) for FeesV3.post. `costs`: this validator's own shared-unit costs by SHARED_UNITS
    name; a unit it doesn't give is posted at the price in force (which moves nothing). `list_prices`: the public list
    prices by family name; a priced or announced family with no list price here is also posted at the price in force,
    so the table still counts (a table must price every priced family). `priced_only` (v3.1 polish VP2: a FeesV3 with
    no `drawEpoch`, live v3): a listed family that isn't priced yet is left out, so no new family is priced there (a
    family priced after a check opened would be seated and never paid, audit F1)."""
    in_force = chain.shared_prices()
    shared = [int((costs or {}).get(u) or in_force[i]) for i, u in enumerate(SHARED_UNITS)]
    by_id = {v3.name_id(name): [int(x) for x in t] for name, t in list_prices.items()}
    priced = chain.priced_families()
    if priced_only:
        left = sorted(name for name in list_prices if v3.name_id(name) not in priced)
        by_id = {fam: t for fam, t in by_id.items() if fam in priced}
        if left and log:
            log(f"table: this FeesV3 has no drawEpoch (v3), so a family priced now could be seated on a check it can't "
                f"be paid for (F1): posting only the families already priced; left out: {', '.join(left)}")
    families, tokens = [], []
    for fam in priced:
        if fam not in by_id:
            by_id[fam] = [int(x) for x in chain.token_prices(fam)]
            if log:
                log(f"table: no list price here for family {_hex(fam)[:14]}; posting the price in force")
    for fam, t in by_id.items():
        families.append(fam)
        tokens.append(t)
    return shared, families, tokens


def receipt_faults(doc: dict, seat: dict, validator: dict, panel: dict, tests_passed: bool | None,
                   where: tuple | None = None) -> list:
    """Why a judge's receipt is false, as far as its document shows ([]: nothing found). `doc` is the stored receipt
    whose on-chain form hashes to the seat's posted receipt; `tests_passed`: this node's own run of the fix's tests
    (None: not run); `where`: (the Panels' address, the panel, the slot) the receipt was posted on, which its seat
    fields must name with the seated key (#251 task 3.10: one seat's receipt can't be posted for another)."""
    on, why = v3.Receipt.from_json(doc["onchain"]), []
    if where is not None:
        panels, pid, slot = where
        if on.seat() != (checksum(panels), pid, slot, checksum(seat["key"])):
            why.append("it names another seat than the one it was posted on")
    if on.proof_type != v3.b32(validator["proofType"]):
        why.append("its proof type isn't the validator's registered one")
    if on.image != v3.b32(validator["image"]):
        why.append("its image isn't the validator's registered one")
    if on.seed != v3.b32(panel["seed"]):
        why.append("it's for another draw")
    if bool(doc.get("vote")) != bool(seat["vote"]):
        why.append("it's for another verdict than the one revealed")
    inner = doc.get("receipt", {})
    if keccak256(str(inner.get("model", {}).get("id", "")).encode()) != on.model:
        why.append("the model it names isn't the one it hashes")
    theirs = inner.get("tests", {}).get("exit_code")
    if tests_passed is not None and theirs is not None and (theirs == 0) != tests_passed:
        why.append("its tests' result isn't what this node's run of the same fix gives")
    return why


class ReceiptStore:
    """The v3 receipts a node keeps: <root>/v3/<the on-chain receipt hash>.json. A read checks that the document's
    on-chain form still hashes to its name. `sources` are other directories of the same shape to read from (what
    other validators published); publishing beyond a shared directory isn't built."""

    def __init__(self, root: Path, sources=()) -> None:
        self.dir = Path(root) / "v3"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.sources = [Path(s) / "v3" for s in sources]

    def put(self, doc: dict) -> str:
        h = v3.Receipt.from_json(doc["onchain"]).hash().hex()
        (self.dir / f"{h}.json").write_bytes(receipts.canonical(doc))
        return h

    def get(self, onchain_hash: str):
        name = onchain_hash[2:] if onchain_hash.startswith("0x") else onchain_hash
        for d in [self.dir, *self.sources]:
            try:
                doc = json.loads((d / f"{name}.json").read_text())
                if v3.Receipt.from_json(doc["onchain"]).hash().hex() == name:
                    return doc
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return None

    def put_evidence(self, doc: dict) -> bytes:
        h = keccak256(receipts.canonical(doc))
        (self.dir / f"evidence-{h.hex()}.json").write_bytes(receipts.canonical(doc))
        return h


@dataclass
class Round:
    """One seat this node holds, as far as it got. `vote`, `mask`, `salt` and `receipt` are what it sealed."""
    pid: int
    submission: int
    kind: int
    vote: bool = False
    mask: int = 0
    salt: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    receipt: str = ""  # the on-chain receipt hash, hex without 0x
    usage: v2.Usage | None = None
    judged: bool = False
    done: bool = False
    note: str = ""
    reason: str = ""  # the judge's one-line reason, kept on this node's disk only (the verdict comment, VP18)

    FIELDS = ("pid", "submission", "kind", "vote", "mask", "salt", "receipt", "judged")

    def plain(self) -> dict:
        data = {f: getattr(self, f) for f in self.FIELDS}
        if self.usage is not None:
            data["usage"] = list(self.usage.as_tuple())
        if self.reason:
            data["reason"] = self.reason
        return data

    @classmethod
    def from_plain(cls, data: dict) -> "Round":
        r = cls(**{f: data[f] for f in cls.FIELDS})
        if data.get("usage"):
            r.usage = v2.Usage(*data["usage"])
        r.reason = str(data.get("reason") or "")
        return r


@dataclass
class Judgement:
    vote: bool
    doc: dict  # the receipt's document, stored under its on-chain hash
    receipt: str
    usage: v2.Usage
    tests_passed: bool | None
    reason: str = ""  # the judge's one-line reason (oracle/verdict_comment.py's `reason_of`), never in the receipt


class NodeV3(NodeV2):
    def __init__(self, chain: v3.Chain, keys, judge, host, repo_name: str, src_root: Path, exchange, store,
                 runner=None, log=print, wallet=None, rounds=None, prover=None, costs: dict | None = None,
                 list_prices: dict | None = None, keeper: bool = True, repo_id=v3.ZERO, sources=(),
                 seal_margin: float = SEAL_MARGIN_S) -> None:
        super().__init__(chain, keys, judge, host, repo_name, src_root, exchange, store, 0, runner=runner, log=log,
                         wallet=wallet)
        self.rounds, self.prover, self.costs, self.keeper = rounds, prover, costs, keeper
        self.list_prices = default_list_prices() if list_prices is None else list_prices
        self.repo_id = repo_id if isinstance(repo_id, bytes) else int(repo_id, 16).to_bytes(32, "big")
        self.seal_margin = seal_margin
        self.receipts3 = ReceiptStore(store.root, sources)
        self.seats: dict = {}  # pid -> Round
        self.finished: set = set()  # panels this node has nothing more to do on
        self.validator: dict | None = None
        self.posted_period = -1
        self._said: set = set()
        self._draw_epoch: bool | None = None  # FeesV3.drawEpoch answers (v3.1); None: not probed yet
        self._init_keeper_state()
        self._no_early: set = set()  # panels whose early reveal the chain refused (v3): they wait for `sealBy`
        self.fixes = None  # a Radicle fix source (oracle/radicle_v3.py, #251 task 4.2); None: the host's pull requests
        self.claims = None  # the registrations' Radicle issues (radicle_v3.RadicleIssues, task 4.3); None: the host's
        self.radicle_seat = None  # model (a) on this node's Radicle node (#251 task 4.1); None: nothing on Radicle
        self.spend = None  # the daily and monthly model-spending caps and their on-chain pause (oracle/spend.py, #253)
        self.verdicts = None  # the verdict on the Radicle issue (oracle/verdict_comment.py, VP18); None: no comments

    # ---------- setup ----------

    def _say(self, key, line: str) -> None:
        if key not in self._said:
            self._said.add(key)
            self.log(line)

    def me(self) -> dict:
        """This key's registration. Raises SetupError if it has none, or if this node can't produce the proof its
        registration promises (the wrong key provider, or no prover)."""
        if self.validator is None:
            val = self.chain.validator(self.address)
            if val["state"] == 0:
                raise SetupError(f"{self.address} isn't registered: run `python3 -m oracle register` first")
            proof = v3.b32(val["proofType"])
            if proof == v3.PROOF_ZKTLS:
                if self.prover is None:
                    raise SetupError("a zkTLS (level C) validator needs a zkTLS prover for its model call "
                                     "(oracle/zktls.py)")
            elif _kind(self.keys) not in QUOTE_KINDS[proof]:
                raise SetupError(_quote_hint(proof, _kind(self.keys)))
            self.validator = val
        return self.validator

    # ---------- the loop ----------

    def run(self, from_block: int, until_idle: float | None = None, poll: float = 2.0,
            outage_limit: float | None = None) -> int:
        self.me()
        last, away_since = self.clock(), None
        while True:
            try:
                progress = self.tick(from_block)
            except Unavailable as e:
                now = self.clock()
                away_since = now if away_since is None else away_since
                self.log(f"node {self.address}: the chain isn't answering ({e}); trying again, nothing is lost")
                if outage_limit is not None and now - away_since >= outage_limit:
                    raise
                time.sleep(poll)
                continue
            if away_since is not None:
                away_since, last = None, self.clock()
            if progress or self.seats:  # an open seat waits for a window: that isn't idleness
                last = self.clock()
            elif until_idle is not None and self.clock() - last >= until_idle:
                self.log(f"node {self.address}: idle for {until_idle:.0f}s, stopping")
                return len(self.finished)
            time.sleep(poll)

    def tick(self, from_block: int) -> bool:
        """One pass: new seats, then every seal, then every reveal and receipt, then the usage reports, the table and
        the keeper's calls. Raises Unavailable if the chain doesn't answer; nothing done is lost."""
        self.me()
        progress = False
        for ev in self.chain.seated(self.address, from_block):
            if ev["pid"] not in self.seats and ev["pid"] not in self.finished:
                progress |= self._take(ev["pid"])
        now = self.chain.now()
        for step in (self._seal, self._reveal, self._report):  # seals first: a shadow's before any counted reveal
            for r in list(self.seats.values()):
                try:
                    progress |= self._advance(r, step, now)
                except Reverted as e:
                    self._say((r.pid, "refused", e.reason), f"panel {r.pid}: the chain refused it ({e.reason}); "
                                                           f"trying again")
                except ModelError as e:  # no answer from the model after its retries: no verdict from this node
                    self.log(f"panel {r.pid}: not judged ({e}); this seat stays silent")
                    self._finish(r, "not judged")
                except evidence.NotReady as e:
                    self._say((r.pid, "not ready", str(e)), f"panel {r.pid}: not judged yet: {e}; trying again")
        if self.verdicts is not None:  # after the seat steps, never blocking them: it catches its own failures
            progress |= self.verdicts.step(self, now)
        try:
            progress |= self._table()
        except Reverted as e:
            self._say(("table", e.reason), f"table: the chain refused it ({e.reason}); trying again")
        if self.spend is not None:
            progress |= self._spend_pause()
        if self.keeper:
            progress |= self._keep_section(self._keep_from(from_block), now)
        if self.radicle_seat is not None:
            progress |= self._radicle()
        return progress

    def _spend_pause(self) -> bool:
        """#253's pause: capacity 0 on-chain while a spending cap has stopped model calls this period, the earlier
        capacity back at the next one (oracle/spend.py). A change Panels refuses (one still pending: `Busy`) is tried
        again on the next pass."""
        try:
            return self.spend.pause_step(
                lambda: self.chain.capacity(self.address),
                lambda n: self.wallet.send(self.chain.panels, "setCapacity(address,uint256)", self.address, n),
                log=self.log)
        except Reverted as e:
            self._say(("capacity", e.reason), f"spending: Panels refused the capacity change ({e.reason}); trying "
                                              f"again")
            return False

    def _radicle(self) -> bool:
        """The seat's pass on Radicle (oracle/radicle_v3.py): `Heads.head` as its `main`, the identity following the
        seats. A Radicle node that doesn't answer is logged (once per message) and tried again next pass."""
        from . import radicle as rad

        try:
            return self.radicle_seat.tick()
        except rad.Unavailable as e:
            self._say(("radicle", str(e)), f"Radicle: {e}; trying again")
            return False

    def _advance(self, r: Round, step, now: int) -> bool:
        st = self._state(r)
        if st is None:
            return True
        return step(r, now, *st)

    def _take(self, pid: int) -> bool:
        p = self.chain.panel(pid)
        if not any(same(k, self.address) for k in self.chain.judges(pid) if k):
            self.finished.add(pid)  # replaced since (a missed deadline in an earlier run)
            return False
        saved = self.rounds.get(f"panel-{pid}") if self.rounds is not None else None
        if saved is not None:
            r = Round.from_plain(saved)
            self.log(f"panel {pid}: resuming this seat's round from disk")
        else:
            r = Round(pid, p["id"], p["kind"])
            where = " that waits for a panel" if p["kind"] == v3.SHADOW and p["ex"] == 0 else ""
            self.log(f"panel {pid}: drawn as {ROLES[p['kind']]} on submission {p['id']}{where}")
        self.seats[pid] = r
        return True

    def _state(self, r: Round):
        """(the panel, this node's slot, its seat), or None once the seat is no longer this node's to act on."""
        p = self.chain.panel(r.pid)
        slot = next((i for i, k in enumerate(self.chain.judges(r.pid)) if k and same(k, self.address)), None)
        if slot is None:
            self._finish(r, "the seat was vacated")
            return None
        return p, slot, self.chain.seat(r.pid, slot)

    def _finish(self, r: Round, note: str = "") -> None:
        r.done, r.note = True, note
        if getattr(self, "verdicts", None) is not None:  # its verdict comment outlives the seat (VP18)
            self.verdicts.remember(self, r)
        self.seats.pop(r.pid, None)
        self.finished.add(r.pid)
        if self.rounds is not None:
            self.rounds.drop(f"panel-{r.pid}")
        if note:
            self.log(f"panel {r.pid}: {note}")

    def _save(self, r: Round) -> None:
        if self.rounds is not None:
            self.rounds.put(f"panel-{r.pid}", r.plain())

    # ---------- one seat ----------

    def _sign(self, tag: bytes, contract: str, pid: int, content: bytes) -> str:
        subject = v3.subject_of(tag, contract, pid, self.address)
        return _hex(self.keys.sign(v3.statement_digest(self.chain.domain(), subject, content)))

    def _seal(self, r: Round, now: int, p: dict, slot: int, seat: dict) -> bool:
        if seat["hasSeal"]:
            return False
        if p["counted"] or p["closed"] or now > p["sealBy"]:
            self._finish(r, "its seal window closed before this node sealed")
            return True
        if not r.judged:
            j = self._judge(r.submission, p, late=now > p["sealBy"] - self.seal_margin, seat=(r.pid, slot))
            r.vote, r.receipt, r.usage, r.judged, r.reason = j.vote, j.receipt, j.usage, True, j.reason
            if r.kind == v3.CHALLENGE:
                r.mask = self._mask(p["ex"], j.tests_passed)
            self._save(r)  # on disk before the seal leaves the node
        seal = v3.commitment_of(self.chain.panels, r.pid, self.address, r.vote, r.mask, r.salt)
        self.exchange.put(r.pid, self.address, "seal",
                          {"seal": _hex(seal), "sig": self._sign(v3.SEAL_TAG, self.chain.panels, r.pid, seal)})
        self.log(f"panel {r.pid}: sealed")
        return True

    def _reveal(self, r: Round, now: int, p: dict, slot: int, seat: dict) -> bool:
        if not seat["hasSeal"] or (seat["revealed"] and seat["receipted"]):
            return False
        if p["counted"] or p["closed"] or now > p["revealBy"]:
            self._finish(r, "its reveal window closed before this node revealed")
            return True
        if not self._reveal_open(r, now, p):
            return False
        mine = v3.commitment_of(self.chain.panels, r.pid, self.address, r.vote, r.mask, r.salt)
        if not r.judged or v3.b32(seat["seal"]) != mine:
            self._finish(r, "the seal on-chain isn't one this node can open; not revealing")
            return True
        try:
            if not seat["receipted"]:
                rh = bytes.fromhex(r.receipt)
                self.exchange.put(r.pid, self.address, "receipt",
                                  {"receipt": _hex(rh),
                                   "sig": self._sign(v3.RECEIPT_TAG, self.chain.panels, r.pid, rh)})
            if not seat["revealed"]:
                content = v3.reveal_content(r.vote, r.mask, r.salt)
                self.exchange.put(r.pid, self.address, "reveal",
                                  {"vote": r.vote, "mask": r.mask, "salt": _hex(r.salt),
                                   "sig": self._sign(v3.REVEAL_TAG, self.chain.panels, r.pid, content)})
        except Reverted as e:
            if now > p["sealBy"] or "TooEarly" not in e.reason:
                raise
            self._no_early.add(r.pid)  # a deployment without #311's early reveal (v3): this panel waits for `sealBy`
            self.log(f"panel {r.pid}: the chain opens the reveal only after the seal window; waiting for it")
            return False
        self.log(f"panel {r.pid}: revealed {'pass' if r.vote else 'fail'}, receipt {r.receipt[:12]} on-chain")
        return True

    def _reveal_open(self, r: Round, now: int, p: dict) -> bool:
        """Whether Panels takes this seat's reveal now (#311, design E1 and E2): a shadow's after its `sealBy`; a
        judging panel's once every seat has sealed, and a counted panel's before its `sealBy` also once every shadow
        drawn with it has sealed or the shadows' window is over. A panel whose early attempt the chain refused
        (`TooEarly`: a deployment that opens reveals only after `sealBy`, v3) waits for `sealBy`."""
        if r.kind == v3.SHADOW:
            return now > p["sealBy"]
        if p["seats"] < p["k"] or p["nSealed"] < p["k"]:
            return False  # every seat seals first
        if now > p["sealBy"]:
            return True
        if r.pid in self._no_early:
            return False
        if r.kind != v3.COUNTED:
            return True
        sp = self.chain.verdict(r.submission)["shadowPid"]
        if sp == 0:
            return True
        q = self.chain.panel(sp)
        return q["ex"] != r.pid or q["nSealed"] == q["k"] or now > q["sealBy"]

    def _report(self, r: Round, now: int, p: dict, slot: int, seat: dict) -> bool:
        if not (seat["revealed"] and seat["receipted"]) or r.usage is None:
            return False
        if self.chain.usage_of(r.pid, slot).receipt == r.usage.receipt:
            self._finish(r)  # on-chain: this seat is done
            return True
        if now > p["revealBy"] + REPORT_WINDOW_S:
            self._finish(r, "its usage report was never taken; the panel is paid without it")
            return True
        u = r.usage
        self.exchange.put(r.pid, self.address, "usage",
                          {"usage": [_hex(u.receipt), *u.as_tuple()[1:]],
                           "sig": self._sign(v3.USAGE_TAG, self.chain.race, r.pid, v3.usage_content(u))})
        self.log(f"panel {r.pid}: usage reported to the race (tokens {u.input} in, {u.output} out; "
                 f"{u.vcpu_seconds} vCPU-s, {u.gb_seconds} GB-s, {u.storage_mb} MB)")
        return True

    # ---------- the check ----------

    def _judge(self, s: int, p: dict, late: bool = False, seat: tuple | None = None) -> Judgement:
        """Judges submission `s` for a panel drawn with `p`'s seed. Everything read from the chain and the host comes
        first, as in v2. `late`: the seal deadline is close, so a check that still can't be run is sealed as not
        passed rather than left silent. Raises NotReady otherwise. `seat`: (pid, slot) of the seat the receipt is for,
        which it names (None for a challenger's own re-run, posted nowhere)."""
        sub = self.chain.submission(s)
        issue_id = self.chain.issue_of(sub)
        onchain = self.chain.issue(issue_id)
        profile = self.chain.profile(onchain["repo"])
        if sub["bounty"] == 0:
            answer, read = self._registration(issue_id, onchain, late)
            return self._receipt(s, sub, p, answer, _no_run(), "", 0.0, profile, seat, read=read)
        answer, tests, fix_tree, seconds = self._fix(s, sub, issue_id, onchain, late,
                                                     timeout_s=profile.get("timeoutSeconds"))
        return self._receipt(s, sub, p, answer, tests, fix_tree, seconds, profile, seat)

    def _fix(self, s: int, sub: dict, issue_id: int, onchain: dict, late: bool, timeout_s: int | None = None) -> tuple:
        """(the answer, the test runs, the fix's commit, the runs' seconds summed). The tests run on the fix's tree, or
        with protected paths on a run tree with the base's copies (#251 L20), twice each, within the profile's one time
        limit `timeout_s` (L22). The fix comes from the repository host's pull requests, or with a Radicle fix source
        (#251 task 4.2) from the patches on this node's own Radicle node."""
        if self.fixes is not None:
            pull, missing, stale = self._find_patch(s, sub)
        else:
            pull, stale = self._find_pull(s, sub), ""
            missing = "no pull request opened the sealed commitment before the seal deadline" if pull is None else ""
        if pull is None:
            if not late:
                raise evidence.NotReady(missing if self.fixes is not None else
                                        f"no pull request opens submission {s}'s sealed commitment yet")
            self.log(f"submission {s}: not passed: {missing}")
            return refused(case_for(self.repo_name, "", "", ""), _no_run(), missing), _no_run(), "", 0.0
        if stale:  # a revision on another base than Heads.head: refused now, its tests not run (S1)
            self.log(f"submission {s}: not sent to the model, and not passed: {stale}")
            title = pull.get("title", "")
            answer = refused(case_for(self.repo_name, title, title, ""), _no_run(), stale)
            return answer, _no_run(), pull["head_sha"], 0.0
        c = SimpleNamespace(pull=pull, bounty=sub["bounty"], submission=s)
        case, refusal = self._case(c, onchain, issue_id)
        if sub.get("rebaseOf"):  # a rebase check (#310, RB3): the approved diff and the range-diff join its case
            case, refusal = rebase_v3.judge_case(self, sub, pull, case, refusal)
        project, protected, why = self._test_config(pull)
        tests, unsafe = self._run_check(pull, project, protected, timeout_s)
        refusal = refusal or why or unsafe
        seconds = tests.seconds  # the runs' time, summed (L22)
        if refusal:
            self.log(f"submission {s}: not sent to the model, and not passed: {refusal}")
        answer = refused(case, tests, refusal) if refusal else self.judge.judge(case, tests)
        return answer, tests, pull["head_sha"], seconds

    def _find_patch(self, s: int, sub: dict) -> tuple:
        """The fix as a Radicle patch (#251 L12, task 4.2): (the revision, or None; why it isn't available, or "";
        why it's refused, or ""). Among the patches on this node's own Radicle node (synced first), the revision whose
        description claims the submission and whose head commit, base and salt open its commitment,
        keccak256(abi.encode(fix, base, salt, solver)); refused unless its base is `Heads.head` (stale, S1); then its
        commit fetched from this node's own storage, verified and read-only (oracle/fetch.py)."""
        from bot import logic

        from . import fetch
        from . import radicle as rad

        try:
            revisions, sync_error = self.fixes.revisions()
        except rad.Unavailable as e:
            return None, f"the fix wasn't available: this node's Radicle copy couldn't be read ({e})", ""
        if sync_error:
            self._say(("rad sync", sync_error), f"submission {s}: Radicle: {sync_error}; reading this node's own copy")
        head = rad.sha_of(self.chain.head())
        for pr in revisions:
            cl = logic.claim(pr["body"])
            if cl is None or cl.submission != s or cl.bounty != sub["bounty"] or not same(cl.solver, sub["solver"]):
                continue
            where = f"patch {pr['patch'][:7]} revision {pr['revision'][:7]}"
            if not (fetch.SHA.match(pr["head_sha"]) and fetch.SHA.match(pr["base_sha"])):
                self._say((s, "refused", pr["revision"]), f"submission {s}: {where} has no head or base commit; "
                                                          f"refused")
                continue
            fix, base = v2.commit_word(pr["head_sha"]), v2.commit_word(pr["base_sha"])
            if v3.fix_commitment(fix, base, bytes.fromhex(cl.salt[2:]), cl.solver) != v3.b32(sub["commitment"]):
                self._say((s, "refused", pr["revision"]), f"submission {s}: {where} doesn't open its seal; refused")
                continue
            found = {**pr, "fix": fix, "base": base}
            if pr["base_sha"] != head:
                return found, "", (f"its {where} is based on {pr['base_sha'][:12]}, not on Heads.head {head[:12]} "
                                   f"(a stale base: the merge would revert, S1)")
            if not fetch.ensure(self.src_root, pr, fix, getattr(self, "fetcher", None)):
                return None, (f"the fix wasn't available: commit {pr['head_sha'][:12]} of {where} couldn't be fetched "
                              f"from this node's Radicle copy"), ""
            return found, "", ""
        return None, ("the fix wasn't available: no patch revision on this node's Radicle copy opens the sealed "
                      "commitment"), ""

    def _find_pull(self, s: int, sub: dict):
        """The pull request whose body claims the submission and whose head commit and salt open its commitment:
        keccak256(abi.encode(fix, base, salt, solver)), the base being the pull request's base commit or 0 (a
        repository outside the head registry)."""
        from bot import logic

        from . import fetch

        for pr in evidence.host_call(self.host.pulls, "all"):
            cl = logic.claim(pr["body"])
            if cl is None or cl.submission != s or cl.bounty != sub["bounty"] or not same(cl.solver, sub["solver"]):
                continue
            fix, salt = v2.commit_word(pr["head_sha"]), bytes.fromhex(cl.salt[2:])
            bases = ([v2.commit_word(pr["base_sha"])] if pr.get("base_sha") else []) + [v3.ZERO]
            base = next((b for b in bases if v3.fix_commitment(fix, b, salt, cl.solver) == v3.b32(sub["commitment"])),
                        None)
            if base is None:
                self._say((s, "refused", pr["number"]),
                          f"submission {s}: pull request #{pr['number']} doesn't open its seal; refused")
                continue
            if not fetch.ensure(self.src_root, pr, fix, getattr(self, "fetcher", None)):
                self._say((s, "no sources"), f"submission {s}: no checkout of {pr['head_sha'][:12]} under "
                                             f"{self.src_root}")
                return None
            return {**pr, "fix": fix, "base": base}
        return None

    def _registration(self, issue_id: int, onchain: dict, late: bool) -> tuple:
        """A registration check (#251 task 4.3): (the answer, what was read, for the receipt). The issue that validly
        claims the registration is found (`_claimed_issue`: on this node's Radicle node with a Radicle issue source,
        L12, else v2's labelled issue on the host, #210), then the judge decides whether it's a genuine bug report in
        the repository's scope (oracle/judge.py's registration prompt; the fake labels by the claim). When no issue
        can be read for it, NotReady until the seal margin, then a failing seal whose receipt says why: never silence.
        A judge with no registration check, or a model that doesn't answer, raises ModelError (as for a fix)."""
        issue, comment, read, missing = self._claimed_issue(issue_id, onchain)
        if issue is None:
            if not late:
                raise evidence.NotReady(missing)
            self.log(f"registration {issue_id}: not passed: {missing}")
            case = registration_case(self.repo_name, "", refusal=missing)
            reads = getattr(self.judge, "reads_evidence", True)
            answer = refused_registration(case, missing) if reads else self.judge.registration(case)
            return answer, read
        from . import radicle_v3 as RV

        text = RV.issue_text(issue)
        where = (f"Radicle issue {issue['id']}" if read["source"] == "radicle" else f"issue #{issue['id']}")
        notes = [f"The node's check: registration {issue_id} on-chain has reporter {onchain['reporter']}, and {where} "
                 f"carries its claim (comment {comment['id']}). The claim is valid; judge the issue itself."]
        if read["claims"] > 1:
            notes.append(f"{read['claims']} issues claim it; the one with the lowest id is shown.")
        if len(text) > MAX_ISSUE_CHARS:
            notes.append(f"The issue's text was cut at {MAX_ISSUE_CHARS} of its {len(text)} characters.")
        case = registration_case(self.repo_name, text[:MAX_ISSUE_CHARS], notes=tuple(notes))
        ask = getattr(self.judge, "registration", None)
        if ask is None:
            raise ModelError(f"this judge ({type(self.judge).__name__}) has no registration check")
        answer = ask(case)
        verdict = "a genuine bug report in scope" if answer.solves else "not a genuine bug report in scope"
        self.log(f"registration {issue_id}: {where} judged {verdict} ({answer.model})")
        return answer, read

    def _claimed_issue(self, issue_id: int, onchain: dict) -> tuple:
        """(the issue that validly claims registration `issue_id` as radicle_v3.issue_view gives it, or None; the
        comment carrying its claim; what was read, for the receipt; why there's none, or ""). With a Radicle issue
        source the issues on this node's own Radicle node (synced first; a failed sync logged and the copy read);
        otherwise the host's labelled issues, by v2's first-claim rule (bot/logic)."""
        from bot import logic

        from . import radicle as rad
        from . import radicle_v3 as RV

        want = {"id": issue_id, "reporter": onchain["reporter"], "repo": onchain["repo"]}
        if self.claims is None:
            issues = evidence.host_call(self.host.issues, "all", logic.LABEL)
            number = logic.first_valid_claim(issues, want, self._repo_id(), logic.LABEL)
            read = {"source": "host", "issues_read": len(issues)}
            if number is None:
                return None, None, read, f"no labelled issue on the host claims registration {issue_id}"
            found = next(i for i in issues if i["number"] == number)
            body = str(found.get("body") or "")
            issue = {"id": str(number), "title": str(found.get("title") or ""),
                     "state": str(found.get("state") or "open"), "labels": [],
                     "comments": [{"id": str(number), "author": "", "body": body}]}
            return issue, issue["comments"][0], {**read, **_read_of(issue, issue["comments"][0], 1)}, ""
        try:
            issues, sync_error = self.claims.issues()
        except rad.Unavailable as e:
            return None, None, {"source": "radicle"}, (f"the issue wasn't available: this node's Radicle copy couldn't "
                                                       f"be read ({e})")
        if sync_error:
            self._say(("rad sync issues", sync_error),
                      f"registration {issue_id}: Radicle: {sync_error}; reading this node's own copy")
        issue, comment, count, problems = RV.find_claim(issues, want, self._repo_id(), self.chain.chain_id(),
                                                        self.chain.race)
        read = {"source": "radicle", "issues_read": len(issues)}
        if issue is None:
            why = (f"no signed claim: no Radicle issue on this node's copy carries a claim of registration {issue_id} "
                   f"signed by its reporter for this issue")
            return None, None, read, why + (f" ({'; '.join(problems[:3])})" if problems else "")
        return issue, comment, {**read, **_read_of(issue, comment, count)}, ""

    def _repo_id(self) -> bytes:
        """The repository a registration must name: the configured one, else the deployment's own (v3 serves exactly
        one, RaceV3.repo, #251 L1)."""
        return self.repo_id if self.repo_id != v3.ZERO else self.chain.repo()

    def _receipt(self, s: int, sub: dict, p: dict, answer, tests: TestRun, fix_tree: str, seconds: float,
                 profile: dict, seat: tuple | None = None, read: dict | None = None) -> Judgement:
        val = self.me()
        proof_type = v3.b32(val["proofType"])
        where = (v3.ZERO,) * 4
        if seat is not None:  # the seat it's for (#251 task 3.10): Panels, panel, slot, this validator's key
            where = (v3.address_word(self.chain.panels), word(seat[0]), word(seat[1]), v3.address_word(self.address))
        bare = v3.Receipt(proof_type, v3.ZERO, keccak256(answer.model.encode()), v3.ZERO, v3.b32(val["image"]),
                          v3.b32(p["seed"]), hashlib.sha256(answer.prompt.encode()).digest(),
                          hashlib.sha256(answer.response.encode()).digest(), bytes.fromhex(tests.results_sha256),
                          v3.ZERO, *where)
        if proof_type == v3.PROOF_ZKTLS:
            proof = self.prover.take()
            if proof is None:
                raise ModelError("no zkTLS proof of the model call: a level C verdict needs one")
            notary, proof_bytes, shown = v3.address_word(proof.notary), proof.to_bytes(), {"zktls": proof.receipt}
            kind = "zktls"
        else:
            # the quote names the receipt it's for and the seat it's given on, so no other seat can reuse it
            q = self.keys.quote(keccak256(bare.hash() + v3.address_word(self.chain.panels) + v3.b32(p["seed"])
                                          + v3.address_word(self.address)))
            if q.kind not in QUOTE_KINDS[proof_type]:
                raise SetupError(_quote_hint(proof_type, q.kind))
            notary, proof_bytes, kind = v3.ZERO, bytes.fromhex(q.quote), q.kind
            shown = {"kind": q.kind, "quote": q.quote, "report_data": q.report_data}
        onchain = v3.Receipt(*bare.words()[:1], notary, *bare.words()[2:9], keccak256(proof_bytes), *bare.words()[10:])
        inner = receipts.build(node=self.address, checker_image=CHECKER_IMAGE, model=answer.model,
                               backend=answer.backend, prompt=answer.prompt, response=answer.response,
                               fix_tree=fix_tree, tests=tests.record(), submission=s, bounty=sub["bounty"],
                               outcome=v2.PASS if answer.solves else v2.FAIL, chain_id=self.chain.chain_id(),
                               race=self.chain.race, attestation_kind=kind, issued_at=self.chain.now(),
                               usage=getattr(answer, "usage", None), inference=getattr(answer, "inference", None))
        doc = {"version": RECEIPT_VERSION, "onchain": onchain.to_json(), "vote": bool(answer.solves),
               "receipt": inner, "proof": shown}
        if answer.backend == REFUSED_BACKEND:  # no judge read it: the receipt says why (e.g. the fix wasn't available)
            doc["refused"] = str(json.loads(answer.response).get("reason", ""))
        if read is not None:  # a registration check: where its issue was read, and the hashes of what was read
            doc["registration"] = read
        h = self.receipts3.put(doc)
        usage = v2.measured_usage(h, answer.prompt, answer.response, seconds, profile["milliVcpus"],
                                  profile["memoryMb"], len(receipts.canonical(doc)), getattr(answer, "usage", None))
        self.log(f"submission {s}: {'pass' if answer.solves else 'fail'} (tests exit {tests.exit_code}, "
                 f"{answer.model}); receipt {h[:12]}")
        from .verdict_comment import reason_of

        return Judgement(bool(answer.solves), doc, h, usage, None if not fix_tree else tests.passed,
                         reason_of(answer.response))

    def _mask(self, original: int, tests_passed: bool | None) -> int:
        """A challenge judge's finding of false receipts: one bit per seat of the challenged panel. A receipt this
        node can't read is left alone: its absence proves nothing here."""
        p, mask = self.chain.panel(original), 0
        for slot, key in enumerate(self.chain.judges(original)):
            if not key:
                continue
            seat = self.chain.seat(original, slot)
            doc = self.receipts3.get(seat["receipt"]) if seat["receipted"] else None
            if doc is None:
                self.log(f"panel {original}: seat {slot}'s receipt isn't published here; not judged")
                continue
            why = receipt_faults(doc, seat, self.chain.validator(key), p, tests_passed,
                                 (self.chain.panels, original, slot))
            if why:
                mask |= 1 << slot
                self.log(f"panel {original}: seat {slot}'s receipt is false: {'; '.join(why)}")
        return mask

    # ---------- the table ----------

    def _table(self) -> bool:
        period = self.chain.current_period()
        if period == self.posted_period or not self.chain.is_active(self.address):
            return False
        self.post_table()
        self.posted_period = period
        return True

    def post_table(self) -> tuple:
        shared, families, tokens = build_table(self.chain, self.costs, self.list_prices,
                                               lambda m: self._say(("table", m), m),
                                               priced_only=not self.fees_draw_epoch())
        self.wallet.send(self.chain.fees, "post(uint256[4],bytes32[],uint256[3][])", shared, families, tokens)
        self.log(f"table posted: {len(families)} families' list prices and this validator's shared-unit costs")
        return shared, families, tokens

    def fees_draw_epoch(self) -> bool:
        """Whether this deployment's FeesV3 has `drawEpoch` (v3.1, where a family's price applies from the draw's
        epoch), probed once with drawEpoch(0): live v3's FeesV3 has no such function and the call reverts with no
        data (VP2). A revert with an error of its own (data) is a v3.1 function refusing check 0: it exists."""
        if self._draw_epoch is None:
            probe = getattr(self.chain, "draw_epoch", None)  # a chain that offers the read; else the raw call
            try:
                if probe is not None:
                    probe(0)
                else:
                    from . import abi

                    self.chain.rpc.eth_call(self.chain.fees, abi.call_data("drawEpoch(uint256)", 0))
                self._draw_epoch = True
            except Reverted as e:
                self._draw_epoch = bool((e.data or "").removeprefix("0x"))
        return self._draw_epoch

    # ---------- the keeper ----------

    def _init_keeper_state(self, every: float = 0, budget: int = KEEPER_BUDGET) -> None:
        """The keeper's own state (v3.1 polish VP6), apart from the seats', so a keeper-only node (oracle/keeper.py,
        which leaves out the rest of __init__) sets it up with this call alone; the keeper needs only `chain`, `wallet`
        and `log` besides. `every`: chain seconds between two keeper sections (ORACLE_KEEPER_EVERY; 0: every pass);
        `budget`: about this many RPC calls a section (ORACLE_KEEPER_BUDGET)."""
        self.keeper_every, self.keeper_budget = every, budget
        if not hasattr(self, "_said"):
            self._said = set()
        self._tries: dict = {}  # state-keyed try counts: drawAudits, drawChallenge, startWindow, refill, the lapses
        self._kept: set = set()  # once-only calls that worked, and ("panel", pid) for panels with nothing left
        self._given_up: set = set()  # once-only calls refused GIVE_UP_S long for a reason that isn't a gate
        self._refused_since: dict = {}  # call key -> the chain time of its first refusal that isn't a gate's
        self._backoff: dict = {}  # call key -> {"n", "next", "fp", "skipped"}
        self._reported: set = set()  # (pid, slot): that seat's usage report is in
        self._live: dict | None = None
        self._race_config: dict | None = None
        self._scan: set = set()  # the submissions each section reads
        self._dropped: set = set()  # submissions with nothing left to call: not read again in this run
        self._cursors: dict = {}  # (event list, from block) -> how many of its events are in the scan set
        self._resume = None  # the item where a section's budget ran out: the next section starts there
        self._keeper_next = 0  # the chain time of the next keeper section
        self._paused_until, self._pauses = 0, 0  # a rate limit's pause of the keeper section, and how many in a row
        self._now, self._fp, self._spent = 0, (), 0  # this section's time, state fingerprint and RPC calls

    def _keep_from(self, from_block: int) -> int:
        """Where the keeper's event scans start: the deployment's first block (ORACLE_FROM_BLOCK), so a restarted node
        reads every check once and keeps the ones not finished; `from_block` for a chain that doesn't know it."""
        first = getattr(self.chain, "first_block", None)
        return from_block if first is None else min(int(first), from_block)

    def _keep_section(self, from_block: int, now: int) -> bool:
        """The keeper's part of a pass, after the seat steps: every `keeper_every` chain seconds, and not while a rate
        limit pauses it. An Unavailable here (HTTP 429 once Rpc's own retries gave up, or no answer) doesn't end the
        pass: the section pauses for the answer's Retry-After, else 30 s doubling up to RATE_PAUSE_MAX_S, said once,
        and the next passes' seat steps run as usual."""
        if now < self._keeper_next or now < self._paused_until:
            return False
        self._keeper_next = now + self.keeper_every
        try:
            progress = self._keep(from_block, now)
        except Unavailable as e:
            self._pauses += 1
            after = getattr(e, "retry_after", None)
            pause = min(float(after) if after else BACKOFF_BASE_S * 2 ** (self._pauses - 1), RATE_PAUSE_MAX_S)
            self._paused_until = now + pause
            if self._pauses == 1:
                self.log(f"keeper: the chain isn't answering the keeper's calls ({e}); they pause (the seats' steps "
                         f"don't), {pause:.0f} s at first, up to {RATE_PAUSE_MAX_S} s")
            return False
        if self._pauses:
            self.log(f"keeper: the chain answers again after {self._pauses} pause(s); the keeper's calls go on")
            self._pauses = 0
        return progress

    def _keep(self, from_block: int, now: int) -> bool:
        """One keeper section: FeesV3's roll in parts, then each submission of the scan set and each panel not yet
        kept, starting where the last section's budget ran out (a rotating cursor), until about `keeper_budget` RPC
        calls are spent. Raises Unavailable if the chain doesn't answer (`_keep_section` pauses then)."""
        real = self.chain
        self.chain = _Metered(real, self)
        self._now, self._spent = now, 0
        try:
            return self._keep_all(from_block, now)
        finally:
            self.chain = real

    def _keep_all(self, from_block: int, now: int) -> bool:
        c = self.chain
        rolled = c.rolled()
        self._fp = (c.epoch(), now // max(self._liveness()["capWindow"], 1), rolled)
        progress = self._roll(rolled)
        self._take_events(from_block)
        block = c.block()
        items = [(0, s) for s in sorted(self._scan)]
        items += [(1, pid) for pid in range(1, c.panel_count() + 1) if ("panel", pid) not in self._kept]
        start = 0
        if self._resume is not None:
            start = next((i for i, item in enumerate(items) if item >= self._resume), 0)
            self._resume = None
        order = items[start:] + items[:start]
        for n, (kind, x) in enumerate(order):
            if self._spent >= self.keeper_budget:
                self._resume = (kind, x)
                self._say(("budget", now // 3600), f"keeper: a section's budget ({self.keeper_budget} RPC calls) "
                                                   f"was spent with {len(order) - n} of {len(items)} checks and "
                                                   f"panels left; the next section goes on from there")
                break
            progress |= self._keep_submission(x, block, now) if kind == 0 else self._keep_panel(x, now)
        return progress

    def _roll(self, rolled: int) -> bool:
        """FeesV3's period closed in parts (VP8): `rollPart()` while `rolled` is behind the current period, at most
        ROLL_PARTS_PER_PASS a section. Each part is bounded, so its estimate is exact (`roll()`'s gas loop wasn't, F2)."""
        c, progress = self.chain, False
        period = c.current_period()
        for _ in range(ROLL_PARTS_PER_PASS):
            if rolled >= period or not self._call(c.fees, "rollPart()", state=rolled):
                break
            progress = True
            rolled = c.rolled()
        return progress

    def _take_events(self, from_block: int) -> None:
        """New checks into the scan set: the commitments, registrations and (v3.1, #310) rebase checks since the last
        section, by a cursor over each event list (its last SCAN_REREAD taken again, for a reorg)."""
        c = self.chain
        lists = [("committed", c.committed), ("registered", c.registered)]
        if hasattr(c, "rebased"):
            lists.append(("rebased", c.rebased))
        for name, read in lists:
            events, at = read(from_block), (name, from_block)
            for e in events[max(self._cursors.get(at, 0) - SCAN_REREAD, 0):]:
                if e["submission"] not in self._dropped:
                    self._scan.add(e["submission"])
            self._cursors[at] = len(events)

    def _keep_submission(self, s: int, block: int, now: int) -> bool:
        c, progress = self.chain, False
        v = c.verdict(s)
        st = v["status"]
        if st == v3.SEALED and block > v["seedBlock"]:
            progress |= "draw" in self._draw_and_signal(s, v)
        elif st == v3.WAITING:
            # redrawn once the registry changes or at its scheduled time (L19's RETRY_DELAY, L16's capacity hour)
            due = c.epoch() + 1 != v.get("waitEpoch", 0) or now >= v.get("retryAt", 0)
            progress |= "draw" in self._draw_and_signal(s, v, due)
        elif st in (v3.HELD, v3.WINDOW):
            if st == v3.HELD and not v["challengeOpen"]:
                # Not while its challenge is open: before contract batch 5 Panels' startWindow then left the
                # window's frozen rest at 0, and the challenge's lapse or resolution resumed the window with nothing
                # left (#256's flake). Since batch 5 (#290) Panels refuses it then; this guard only saves the
                # reverting call. Held, the verdict can't be final anyway; the window starts whole once the
                # challenge closes. Panels refuses it (NotReady) until enough challengers could be drawn: a few tries
                # per state of the registry and per capacity window, as drawChallenge (VP6).
                tried = ("startWindow", s, *self._fp[:2])
                if self._tries.get(tried, 0) < CHALLENGE_TRIES:
                    self._tries[tried] = self._tries.get(tried, 0) + 1
                    progress |= self._call(c.panels, "startWindow(uint256)", s, state=st)
            waits = v.get("auditWaits") and c.epoch() + 1 == v.get("auditEpoch")
            if (block > v["auditBlock"] and not waits
                    and not (v["auditDecided"] and v["auditsDrawn"] == v["auditsDue"])):
                # With no auditor eligible the audits wait for the registry to change (`auditWaits`), and the
                # contract refuses every call until it does (#251 task 3.10); then one call re-targets and the
                # next draws from the new snapshot. With every auditor busy (L16) the call succeeds without drawing
                # and the audits are retried from the same audit block once they have room. So a few tries per
                # state of the registry, per released round (`releaseAudits` re-targets them) and per capacity
                # window, as for a challenge: before, a keeper that spent its tries while every auditor was full
                # never tried again, and the audits were released until the check was refunded (#311: with the
                # early reveal a verdict counts minutes after its draw, while its auditors' hour is still full).
                tried = ("audits", s, v["auditsDrawn"], v["auditDecided"], c.epoch(), v.get("redraws", 0),
                         now // max(self._liveness()["capWindow"], 1))
                if self._tries.get(tried, 0) < AUDIT_TRIES:
                    self._tries[tried] = self._tries.get(tried, 0) + 1
                    progress |= self._call(c.panels, "drawAudits(uint256)", s, state=st)
            stuck = v.get("auditStuckAt", 0)
            if (st == v3.WINDOW and stuck and not v["challengeOpen"] and v["auditsDrawn"] < v["auditsDue"]
                    and now > stuck + self._liveness()["stuckGrace"]):
                # audits nobody could take for STUCK_GRACE: the round is released (L19), the audit drawn afresh
                progress |= self._call(c.panels, "releaseAudits(uint256)", s, state=st)
            progress |= self._keep_challenge(s, v, block, now)
            if (st == v3.WINDOW and now >= v["finalAt"] and not v["challengeOpen"] and v["auditDecided"]
                    and v["auditsDone"] >= v["auditsDue"]):
                progress |= self._call(c.panels, "finalize(uint256)", s, state=st)
        sub = None
        if st in (v3.HELD, v3.WINDOW, v3.FINAL) or (st == v3.RELEASED and v["pid"]):
            sub = c.submission(s)
            if not sub["paid"]:
                # the counted judges' pay: once every seat reported, or REPORT_WINDOW after the reveal deadline (F4)
                if self._reports_in(v["pid"]) and self._call(c.race, "result(uint256)", s, once=True, state=st):
                    progress, sub = True, c.submission(s)
            elif st == v3.FINAL and not sub["done"] and now > v["finalAt"] + REPORT_WINDOW_S:
                progress |= self._call(c.race, "finish(uint256)", s, once=True, state=st)
            progress |= self._after_count(s, v, sub, now)
        if st in (v3.HELD, v3.WINDOW, v3.FINAL):
            progress |= self._rebase_failed(s)
        if st == v3.FINAL:
            progress |= self._merge(s)
        if st == v3.RELEASED or (v.get("redraws") and st in (v3.SEALED, v3.WAITING)):
            # never judged: refunded once Panels released it for good, or at the race's deadline once a round was
            # released (L19); a counted verdict's judges are paid first (`result`)
            sub = sub if sub is not None else c.submission(s)
            if not sub["done"] and self._release_due(v, sub, now):
                progress |= self._call(c.race, "release(uint256)", s, once=True, state=st)
        self._drop_if_finished(s, v, sub)
        return progress

    def _draw_and_signal(self, s: int, v: dict, due: bool = True) -> list:
        """v3.draw_and_signal's rule for a sealed or waiting check (VP24): waiting, the wait's signal, then the draw if
        it is `due`, then the panel's signal if it seated one; sealed, the draw, then the signal. The wait is signalled
        once a wait round (its released rounds and retry time: FeesV3 counts it once a period anyway, and each signal
        costs gas); after a draw, the signal carries the new status, so a refused wait signal's backoff doesn't hold
        it. Returns the steps sent."""
        c, st = self.chain, v["status"]
        waited = ("signalWait", s, v.get("redraws", 0), v.get("waitEpoch", 0), v.get("retryAt", 0))

        def draw() -> bool:
            return due and self._call(c.panels, "draw(uint256)", s, state=st)

        def signal(kind: str) -> bool:
            if kind == "wait":
                if waited in self._tries:
                    return False
                if not self._call(c.race, "signal(uint256)", s, state=st):
                    return False
                self._tries[waited] = 1
                return True
            return self._call(c.race, "signal(uint256)", s, state=(st, "drawn"))

        return v3.draw_and_signal(st, draw, signal, lambda: bool(c.verdict(s)["pid"]))

    def _after_count(self, s: int, v: dict, sub: dict, now: int) -> bool:
        """A hook for a step after a verdict has counted (VP18's verdict comment, task 2.11): called each section for
        each scanned submission whose verdict counted (held, in its window, final, or released with a panel), with
        Panels' record `v` and the race's `sub`. Returns progress. A step that can fail retries with the keeper's
        backoff: `self._due(key)` before a try, `self._failed(key, reason)` after a failure, `self._succeeded(key)`
        after it worked; `_holds` keeps the submission in the scan set while the step still has work."""
        return False

    def _holds(self, s: int) -> bool:
        """True keeps a finished submission in the scan set (a later step's work, `_after_count`)."""
        return False

    def _drop_if_finished(self, s: int, v: dict, sub: dict | None) -> None:
        """A submission done with its verdict final or released and nothing owed (a merge, a lapse to settle), or
        withdrawn or expired, leaves the scan set: it isn't read again in this run (VP6)."""
        st = v["status"]
        if st in (v3.FINAL, v3.RELEASED):
            if sub is None or not sub["done"] or self._owes(s, v, sub):
                return
        elif st not in (v3.WITHDRAWN, v3.EXPIRED):
            return
        if not self._holds(s):
            self._scan.discard(s)
            self._dropped.add(s)

    def _owes(self, s: int, v: dict, sub: dict) -> bool:
        if v.get("filedLapsed") and self._tries.get(("settleLapse", s, v.get("lapses", 0)), 0) < LAPSE_TRIES:
            return True
        b = sub.get("bounty")
        if not b:
            return False
        bt = self.chain.bounty(b)
        if bt["state"] == v3.WON and bt["winner"] in (s, sub.get("rebaseOf")):
            return True  # its solver's `claim` is still to come, and its merge after that
        if bt["state"] != v3.CLAIMED or not bt["epoch"] or bt["winner"] not in (s, sub.get("rebaseOf")):
            return False
        if (self.chain.race, "merge(uint256)", (b,)) in self._given_up:
            return False
        a = self.chain.award(b, bt["epoch"])
        return not (a["merged"] or a["closed"])  # its merge (or the failed rebase's reopening) is still to call

    def _reports_in(self, pid: int, p: dict | None = None) -> bool:
        """RaceV3's `_reportsDue` for panel `pid`: every seated key's usage report is in, or REPORT_WINDOW has passed
        since the reveal deadline. Before that `result`, `payPanel` and `settleChallenge` refuse NotYet (F4)."""
        c = self.chain
        p = p if p is not None else c.panel(pid)
        if self._now > p["revealBy"] + REPORT_WINDOW_S:
            return True
        for slot, key in enumerate(c.judges(pid)):
            if not key or (pid, slot) in self._reported:
                continue
            if c.usage_of(pid, slot).receipt == v3.ZERO:
                return False
            self._reported.add((pid, slot))
        return True

    def _release_due(self, v: dict, sub: dict, now: int) -> bool:
        """RaceV3.release's own gate: a counted verdict's judges paid first; then a check Panels released for good,
        or one with a released round once `resultDays` (read once) have passed since its day."""
        if v["pid"] and not sub["paid"]:
            return False
        if v["status"] == v3.RELEASED:
            return True
        if self._race_config is None:
            self._race_config = self.chain.config()
        day = (now - int(getattr(self.chain, "start", 0))) // 86_400
        return bool(v.get("redraws")) and day >= sub["day"] + int(self._race_config.get("resultDays", 0))

    def _call(self, to: str, signature: str, *args, once: bool = False, state=None,
              gas_floor: int | None = None) -> bool:
        """A call anyone may make. A revert means it isn't due (or someone else made it): no progress, and the call
        waits out its backoff (`_failed`). `once`: a call that succeeds one time only (a panel's pay): not sent again
        after it worked, or after GIVE_UP_S of refusals that aren't a gate's. `state`: what, besides the section's
        fingerprint, restarts the backoff when it changes (the verdict's status)."""
        key = (to, signature, args)
        if once and self._settled(key):
            return False
        if not self._due(key, state):
            return False
        self._spent += 1  # the estimate
        try:
            if gas_floor:
                self.wallet.send(to, signature, *args, gas_floor=gas_floor)
            else:
                self.wallet.send(to, signature, *args)
        except Reverted as e:
            self._failed(key, e.reason, state, once=once)
            return False
        self._spent += KEEPER_TX_CALLS - 1
        self._succeeded(key)
        if once:
            self._kept.add(key)
        self.log(f"keeper: {signature.split('(')[0]}({', '.join(str(a) for a in args)})")
        return True

    def _settled(self, key) -> bool:
        return key in self._kept or key in self._given_up

    def _due(self, key, state=None) -> bool:
        """Whether `key`'s backoff allows a try now: none, run out, or its state fingerprint changed since."""
        b = self._backoff.get(key)
        if b is None:
            return True
        if b["fp"] != (self._fp, state):
            del self._backoff[key]
            return True
        if self._now >= b["next"]:
            return True
        b["skipped"] += 1
        return False

    def _succeeded(self, key) -> None:
        self._backoff.pop(key, None)
        self._refused_since.pop(key, None)

    def _failed(self, key, reason: str, state=None, once: bool = False) -> None:
        """A refused try: the next waits min(BACKOFF_BASE_S × 2^(n-1), BACKOFF_MAX_S), n counting the refusals since
        the fingerprint last changed; one log line, with the passes skipped in the backoff before. A refusal that
        isn't a gate's starts GIVE_UP_S, after which a once-only call is left to others."""
        now, fp = self._now, (self._fp, state)
        b = self._backoff.get(key)
        n = b["n"] + 1 if b is not None and b["fp"] == fp else 1
        skipped = b["skipped"] if b is not None else 0
        wait = min(BACKOFF_BASE_S * 2 ** (n - 1), BACKOFF_MAX_S)
        self._backoff[key] = {"n": n, "next": now + wait, "fp": fp, "skipped": 0}
        what = _what(key)
        if str(reason).split("(")[0] not in GATED_REFUSALS:
            first = self._refused_since.setdefault(key, now)
            if once and now - first >= GIVE_UP_S:
                self._given_up.add(key)
                self._backoff.pop(key, None)
                self.log(f"keeper: {what} refused for {(now - first) / 3600:.0f} h ({reason}); left to others")
                return
        self.log(f"keeper: {what} refused ({reason}); next try in {wait} s"
                 + (f" ({skipped} pass(es) skipped before this one)" if skipped else ""))

    def _keep_challenge(self, s: int, v: dict, block: int, now: int) -> bool:
        """An open challenge with no panel (#251 batch 4, L25): drawn from its seed block; while it waits, drawn again
        once the registry changes or at its retry time (RETRY_DELAY); past CHALLENGE_DEADLINE, lapsed. Then a filed
        challenge's lapse is settled at the race (its stake and cover back). Each call a few times per state, as
        drawAudits."""
        c, progress = self.chain, False
        if v["challengeOpen"] and v["challengePid"] == 0:
            past = now > v.get("challengeBy", 0) and v.get("challengeBy", 0) != 0
            waits = (v.get("challengeEpoch", 0) != 0 and c.epoch() + 1 == v["challengeEpoch"]
                     and now < v.get("challengeRetryAt", 0))
            if past:
                tried = ("lapse", s, v["challengeBy"])
                if self._tries.get(tried, 0) < LAPSE_TRIES:
                    self._tries[tried] = self._tries.get(tried, 0) + 1
                    progress |= self._call(c.panels, "lapseChallenge(uint256)", s)
            elif not waits and block > v["challengeBlock"]:
                # drawChallenge succeeds without drawing while busy validators leave the fresh panel short (L16:
                # retried from the same seed once they have room), so a success isn't progress by itself. A few
                # tries per state of the challenge (its seed block and wait), of the registry, and per capacity
                # window (room comes back with time), never every pass.
                tried = ("challenge", s, v["challengeBlock"], v.get("challengeEpoch", 0), c.epoch(),
                         now // max(self._liveness()["capWindow"], 1))
                if self._tries.get(tried, 0) < CHALLENGE_TRIES:
                    self._tries[tried] = self._tries.get(tried, 0) + 1
                    progress |= self._call(c.panels, "drawChallenge(uint256)", s)
        if v.get("filedLapsed"):
            # the race holds a lapsed filed challenge's stake and cover until settled; refused once settled
            tried = ("settleLapse", s, v.get("lapses", 0))
            if self._tries.get(tried, 0) < LAPSE_TRIES:
                self._tries[tried] = self._tries.get(tried, 0) + 1
                if self._call(c.race, "settleLapse(uint256)", s):
                    self._tries[tried] = LAPSE_TRIES
                    progress = True
        return progress

    def _keep_panel(self, pid: int, now: int) -> bool:
        c, progress = self.chain, False
        p = c.panel(pid)
        if p["kind"] == v3.SHADOW:
            if now <= p["revealBy"]:
                return False
            if not (p["closed"] and p["scored"]):
                progress |= self._call(c.panels, "settleShadows(uint256)", pid)
            owed = False
            for slot in range(p["k"]):
                seat = c.seat(pid, slot)
                if not (seat["revealed"] and seat["receipted"]):
                    continue
                pay = (c.race, "payShadow(uint256,uint256)", (pid, slot))
                if c.usage_of(pid, slot).receipt != v3.ZERO:
                    # with at least PAY_SHADOW_GAS_FLOOR: on v3 too little gas closes the seat unpaid (#325)
                    progress |= self._call(pay[0], pay[1], pid, slot, once=True, gas_floor=PAY_SHADOW_GAS_FLOOR)
                owed |= not self._settled(pay) and now <= p["revealBy"] + REPORT_WINDOW_S  # its report may still come
            if p["closed"] and p["scored"] and not owed:
                self._kept.add(("panel", pid))
            return progress
        if p["counted"]:
            if p["kind"] in (v3.AUDIT, v3.CHALLENGE):  # a race-filed challenge's panel is settled, the others paid
                if not self._reports_in(pid, p):
                    return False  # a seat's report may still come: the race refuses NotYet until REPORT_WINDOW (F4)
                pay = (c.race, "payPanel(uint256)", (pid,))
                settle = (c.race, "settleChallenge(uint256,uint256)", (p["id"], pid))
                progress |= self._call(pay[0], pay[1], pid, once=True)
                if p["kind"] == v3.CHALLENGE and pay not in self._kept:
                    progress |= self._call(settle[0], settle[1], p["id"], pid, once=True)
                if not (pay in self._kept or settle in self._kept or self._settled(pay)):
                    return progress
            self._kept.add(("panel", pid))
            return progress
        if p["closed"]:
            if p["kind"] == v3.CHALLENGE:
                # a released challenge panel (L25): its seats that revealed with receipts are paid (deposit, pool)
                if not self._reports_in(pid, p):
                    return False
                pay = (c.race, "payPanel(uint256)", (pid,))
                progress = self._call(pay[0], pay[1], pid, once=True)
                if pay in self._kept or self._settled(pay):
                    self._kept.add(("panel", pid))
                return progress
            return False
        if p["seats"] < p["k"]:
            # a replacement for a seat: Panels refuses (NotReady) while none can be drawn; a few tries per state of
            # the registry and per capacity window (VP6), not every pass
            tried = ("refill", pid, *self._fp[:2])
            if self._tries.get(tried, 0) < CHALLENGE_TRIES:
                self._tries[tried] = self._tries.get(tried, 0) + 1
                if self._call(c.panels, "refill(uint256)", pid):
                    return self._call(c.race, "signal(uint256)", p["id"]) or True
            if now > p["revealBy"] + self._liveness()["stuckGrace"]:
                # replacements exhausted: the round ends, its silent seats slashed, the submission waits (L19); a
                # challenge panel's challenge waits for a redraw, or lapses past its deadline (L25)
                return self._call(c.panels, "release(uint256)", pid)
            return False
        if (now > p["sealBy"] and p["nSealed"] < p["seats"]) or (now > p["revealBy"] and p["done"] < p["k"]):
            return self._call(c.panels, "advance(uint256)", pid) and self._call(c.race, "signal(uint256)", p["id"])
        return False

    def _merge(self, s: int) -> bool:
        """#251 L9: a claimed fix whose verdict is final moves the head (`merge`, anyone, once). The keeper reads which
        tree the merge would move the head to (the award's rebase check while it stands as a pass, #310 RB5, else the
        fix) and calls it once both verdicts are final and that tree's base is still `Heads.head`; a stale base is
        left for a rebase (`pofctl --v3 rebase`), with no reverting call (#314)."""
        c = self.chain
        sub = c.submission(s)
        b = sub["bounty"]
        if not b:
            return False
        bt = c.bounty(b)
        original = sub.get("rebaseOf") or s
        if bt["state"] != v3.CLAIMED or bt["winner"] != original or not bt["epoch"]:
            return False
        target, a = rebase_v3.merge_target(c, b)
        if not target or a["sub"] != original:
            return False
        if target != original and (c.verdict(original)["status"] != v3.FINAL
                                   or c.verdict(target)["status"] != v3.FINAL):
            return False  # both verdicts final first (#310, RB5)
        base = c.submission(target).get("base")
        if base is not None and hasattr(c, "head") and v3.b32(base) != c.head():
            self._say(("stale", b, target), f"bounty {b}: not merged: check {target}'s base "
                                            f"{rebase_v3.sha_of(base)[:12]} isn't Heads.head any more; its solver (or "
                                            f"anyone, a day after the head moved) may rebase it: pofctl --v3 rebase")
            return False
        return self._call(c.race, "merge(uint256)", b, once=True)

    def _rebase_failed(self, s: int) -> bool:
        """#310 RB5: the winning solver's own rebase check counted as a fail while its base is still the head closes the
        award and reopens the bounty at once (`mergeExpired`, anyone). Any other ending of a rebase check only frees
        its slot: nothing to call."""
        c = self.chain
        sub = c.submission(s)
        if not sub.get("rebaseOf") or sub["outcome"] != 2:  # Outcome.Fail
            return False
        b = sub["bounty"]
        bt = c.bounty(b)
        if bt["state"] != v3.CLAIMED or not bt["epoch"]:
            return False
        a = c.award(b, bt["epoch"])
        if a.get("rebase") != s or a["merged"] or a["closed"] or sub["solver"].lower() != a["winner"].lower():
            return False
        if not hasattr(c, "head") or v3.b32(sub["base"]) != c.head():
            return False  # the head moved during its check: only the slot is freed
        return self._call(c.race, "mergeExpired(uint256)", b, once=True)

    def _liveness(self) -> dict:
        """Panels' L19 and L16 values (read once): STUCK_GRACE, RETRY_DELAY, MAX_REDRAWS, CAP_WINDOW."""
        if self._live is None:
            self._live = self.chain.liveness()
        return self._live

    # ---------- a challenge ----------

    def challenge(self, s: int, force: bool = False):
        """Re-runs submission `s`'s check and, if this node's verdict differs from the counted one or a counted
        judge's receipt is false, files a challenge at the race with the evidence's hash (the stake and the panel's
        worst-case cost come from this node's account). Returns the evidence's hash, or None when it agrees (nothing
        is filed, unless `force`)."""
        v = self.chain.verdict(s)
        if v["status"] not in (v3.HELD, v3.WINDOW) or v["challengeOpen"]:
            raise SetupError(f"submission {s} has no counted verdict open to a challenge "
                             f"(status {v3.STATUS[v['status']]})")
        p = self.chain.panel(v["pid"])
        j = self._judge(s, p, late=True)
        mask = self._mask(v["pid"], j.tests_passed)
        if j.vote == v["pass"] and mask == 0 and not force:
            self.log(f"submission {s}: this node's check agrees with the verdict and finds no false receipt; "
                     f"nothing filed")
            return None
        doc = {"version": EVIDENCE_VERSION, "chain": self.chain.chain_id(), "race": self.chain.race,
               "submission": s, "panel": v["pid"], "verdict": bool(v["pass"]), "challenger": self.address,
               "vote": j.vote, "false_receipts": mask, "receipt": j.doc}
        ev = self.receipts3.put_evidence(doc)
        sub = self.chain.submission(s)
        repo = self.chain.issue(self.chain.issue_of(sub))["repo"]
        need = self.chain.config()["challengeStake"] + self.chain.deposit_for(s, repo)
        if self.chain.allowance(self.address, self.chain.race) < need:
            self.wallet.send(self.chain.coin(), "approve(address,uint256)", self.chain.race, need)
        self.wallet.send(self.chain.race, "challenge(uint256,bytes32)", s, ev)
        self.log(f"submission {s}: challenge filed (this node says {'pass' if j.vote else 'fail'}, the verdict "
                 f"{'pass' if v['pass'] else 'fail'}; false receipts mask {mask}); evidence {ev.hex()[:12]}")
        return ev


def _read_of(issue: dict, comment: dict, claims: int) -> dict:
    """What a registration check read, for its receipt: the issue and the comment carrying the claim, the sha256 of the
    issue's whole text (radicle_v3.issue_text) and of the claim's text, and how many issues validly claimed it."""
    from . import radicle_v3 as RV

    return {"issue": issue["id"], "claim": comment["id"], "claims": claims,
            "issue_sha256": hashlib.sha256(RV.issue_text(issue).encode()).hexdigest(),
            "claim_sha256": hashlib.sha256(comment["body"].encode()).hexdigest()}


def _no_run() -> TestRun:
    """A check with no fix to test: nothing ran."""
    return nothing_ran()


def _kind(keys) -> str:
    """The key provider's quote kind, without asking for a quote when it names its kind (an SEV-SNP report is a call
    to the AMD Secure Processor)."""
    return getattr(keys, "kind", "") or keys.quote(b"").kind


def _quote_hint(proof: bytes, kind: str) -> str:
    if proof == v3.PROOF_SIMULATED:
        return (f"the `simulated` proof type's quote comes from the dstack simulator (D18): set ORACLE_KEYS=dstack "
                f"and DSTACK_SIMULATOR_ENDPOINT (this node's key gives {kind!r})")
    return (f"a TEE validator's quote comes from its dstack guest agent (ORACLE_KEYS=dstack) or its SEV-SNP guest "
            f"(ORACLE_KEYS=snp); this key gives {kind!r}")


# ---------- register and leave ----------

def registration(chain: v3.Chain, keys, *, proof: str, family: str, host: str, image: bytes, operator: str = "",
                 tee_type: str = "", level: int = v3.LEVEL_A, firmware: int = 0, rad_node: bytes = v3.ZERO) -> tuple:
    """(the registration this key would sign, its attestation's document). For a TEE and for `simulated` the
    attestation is the hash of a quote over this key and registry; zkTLS has none. `rad_node`: the validator's
    Radicle node key (32 bytes, Ed25519; #251, L11), signed with the rest; ZERO for none (its seat is then never
    counted as a delegate)."""
    me, proof_type = keys.address(), v3.PROOFS[proof]
    if len(rad_node) != 32:
        raise SetupError("a Radicle node key has 32 bytes (the Ed25519 public key its did:key names)")
    if proof_type == v3.PROOF_ZKTLS:
        return (v3.Registration(me, operator or me, proof_type, v3.ZERO, 0, v3.ZERO, image, v3.name_id(host),
                                v3.name_id(family), 0, rad_node), {})
    q = keys.quote(keccak256(REGISTRATION_NOTE + chain.domain() + v3.address_word(me)))
    if q.kind not in QUOTE_KINDS[proof_type]:
        raise SetupError(_quote_hint(proof_type, q.kind))
    if not q.quote:
        raise SetupError("the guest agent gave no quote")
    attestation = keccak256(bytes.fromhex(q.quote))
    r = v3.Registration(me, operator or me, proof_type, v3.name_id(tee_type), level, attestation, image,
                        v3.name_id(host), v3.name_id(family), firmware, rad_node)
    return r, {"kind": q.kind, "quote": q.quote, "report_data": q.report_data}


def rad_node_arg(value: str, env, run=None) -> bytes:
    """The Radicle node key `oracle register` signs (#251, L11): `value` (did:key:z6Mk…, a Node ID z6Mk…, 0x and 64
    hex digits, or `none`); when empty, the node's own `rad self --did`, through ORACLE_RADICLE_EXEC's prefix. Raises
    SetupError when neither names one: registering without a node is a choice (`none`), never a default."""
    import shlex
    import subprocess

    text = (value or "").strip()
    if text.lower() == "none":
        return v3.ZERO
    if not text:
        cmd = shlex.split(env.get("ORACLE_RADICLE_EXEC", "")) + ["rad", "self", "--did"]
        try:
            out = (run or subprocess.run)(cmd, capture_output=True, text=True, timeout=30)
            text = out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            text = ""
        if not text:
            raise SetupError("name this validator's Radicle node: --rad-node did:key:z6Mk… (its `rad self --did`), "
                             "or ORACLE_RADICLE_EXEC to reach the node; --rad-node none registers without one, and "
                             "the seat is then never counted as a delegate")
    try:
        key = delegates.parse_node(text)
    except ValueError as e:
        raise SetupError(f"--rad-node: {e}") from None
    return key


def check_family(chain: v3.Chain, family: str, log=print) -> None:
    """#251 v3.1 polish VP12 (F10): a family is named `provider/line` (FAMILY_FORM, "anthropic/claude"). Another name
    is refused unless that exact name is already priced on this deployment (live v3's `anthropic.claude`, a devnet's
    `fake`), so a validator can't register a family that no table will ever price under that name."""
    if FAMILY_FORM.match(family or ""):
        return
    if v3.name_id(family or "") in {v3.b32(f) for f in chain.priced_families()}:
        if "." in family and "/" not in family:
            log(f"family {family!r} is accepted because this deployment prices it; v3.1 renames it "
                f"{family.replace('.', '/', 1)!r} (one form: provider/line)")
        return
    raise SetupError(f"the family {family!r} isn't in the provider/line form (lowercase, e.g. anthropic/claude: "
                     f"{FAMILY_FORM.pattern}), and this deployment doesn't price that name")


def register(chain: v3.Chain, keys, wallet, bond: int, store_root: Path | None = None, log=print, **what):
    """Registers this node's key as a candidate with `bond` micro-coins from the wallet's account."""
    check_family(chain, what.get("family", ""), log)
    r, attestation = registration(chain, keys, **what)
    digest = r.digest(chain.domain())
    if digest != chain.registration_digest(r):
        raise SetupError("the registry computes another digest for this registration: refusing to sign")
    if bond < chain.bond_floor():
        raise SetupError(f"the bond must be at least {chain.bond_floor() / 10**6:,.2f}")
    if chain.allowance(wallet.address, chain.registry) < bond:
        wallet.send(chain.coin(), "approve(address,uint256)", chain.registry, bond)
    wallet.send(chain.registry, f"register({v3.REGISTRATION},uint256,bytes)", r.as_tuple(), bond, keys.sign(digest))
    if store_root is not None and attestation:
        d = Path(store_root) / "v3"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"attestation-{r.attestation.hex()}.json").write_bytes(receipts.canonical(attestation))
    node = (f"Radicle node {delegates.did_from_key(r.rad_node)}" if any(r.rad_node) else
            "no Radicle node (its seat won't be counted as a delegate)")
    log(f"registered {r.key} as a candidate (operator {r.operator}, bond {bond / 10**6:,.2f}, {node}); it's drawn as "
        f"a shadow until it qualifies")
    return r


def leave(chain: v3.Chain, keys, wallet, log=print) -> None:
    """Announces leaving: never drawn again, still slashable; the bond is withdrawable after the unbonding delay."""
    wallet.send(chain.registry, "leave(address)", keys.address())
    log(f"{keys.address()} is leaving; its bond can be withdrawn after the unbonding delay, once every verdict it "
        f"gave is final and every challenge naming it is closed")


def withdraw_bond(chain: v3.Chain, keys, wallet, log=print) -> None:
    wallet.send(chain.registry, "withdraw(address)", keys.address())
    log(f"{keys.address()}: bond withdrawn to its operator account")
