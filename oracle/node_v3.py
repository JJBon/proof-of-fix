"""The v3 validator node (proof-of-fix#139, task 4.1 of #132, on #138's contracts): a validator's process that
registers itself, judges when Panels draws it, and keeps the version's clockwork moving.

What it does:

1. `register` and `leave` (and `withdraw_bond`): the registration is signed by the node's key and bonded from its
   account; on a devnet the `simulated` proof type's attestation is a quote from the dstack simulator (D18).
2. Every seat Panels gives its key (the `Seated` events), whatever the panel's kind:
   - counted: one of the k judges whose reveals decide the verdict;
   - shadow: a candidate's (or a barred family's) unpaid verdict, on a drawn submission or on one that waits for a
     panel; it seals in the counted panel's seal window, so before any counted reveal is public;
   - audit: a one-seat panel checking a counted verdict;
   - challenge: a fresh, larger panel, which also names the original judges' false receipts (the mask).
   For each: the check (the fix's tests in the sandbox and the judge, as in v2; a registration check by the claim
   rule), a receipt, then its seal, and after the seal window its receipt's hash and its reveal, all on-chain through
   the `onchain` transport, and its usage report to RaceV3. Seals always go out before reveals in a pass.
3. Its cost table, once a pricing period: its own shared-unit costs and every family's public list price (D9, D19).
4. The keeper's calls anyone may make (ORACLE_KEEPER, on by default): draws, replacements, audits, challenge draws,
   shadow settlement, finality, the result, the panels' pay, FeesV3's signals and roll; since #251's contract batch 2
   also the merge of a claimed fix once its verdict is final (L9: the head moves then, not at the claim), the release
   of a stuck panel or of audits nobody can take (L19), the redraw of a waiting submission at its scheduled time, and
   the refund of a check Panels released for good or parked at its deadline (RaceV3.release).
5. `challenge`: re-runs a counted verdict's check and, if it disagrees or finds a false receipt, files a challenge
   with its evidence.

A node signs one seal, one reveal, one receipt and one usage report per seat (two contents for one subject are
provable equivocation, the whole bond). What it sealed is on its own disk before the seal leaves (oracle/rounds.py),
so a restarted node reveals the same vote with the same salt.

Time is the chain's (the latest block's timestamp): Panels' windows are in it."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from . import evidence, receipt as receipts, v2, v3
from .crypto import checksum, keccak256, word
from .judge import FakeJudge, case_for, refused
from .models import ModelError
from .node_v2 import CHECKER_IMAGE, NodeV2, same
from .rpc import Reverted, Unavailable
from .sandbox import TestRun, run_tests

RECEIPT_VERSION = "pof-receipt-v3-1"
EVIDENCE_VERSION = "pof-challenge-evidence-1"
REGISTRATION_NOTE = b"proof-of-fix v3 registration"
QUOTE_KINDS = {v3.PROOF_SIMULATED: "dstack-simulator", v3.PROOF_TEE: "dstack-tdx"}
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
GIVE_UP = 50  # a keeper's once-only call refused this often is left to others


class SetupError(RuntimeError):
    """The node can't act as the validator its registration says it is."""


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def default_list_prices() -> dict:
    """Every family's public list price: {name: [input, cached, output]} in micro-coins per million tokens, from
    pof/costs.py (the providers' price lists as read on the date that file states)."""
    from pof import costs

    return {LIST_NAMES[f]: [round(m.input * 10**6), round(m.cached * 10**6), round(m.output * 10**6)]
            for f, m in costs.JUDGE.items() if f in LIST_NAMES}


def build_table(chain, costs: dict | None, list_prices: dict, log=None) -> tuple:
    """(shared, families, tokens) for FeesV3.post. `costs`: this validator's own shared-unit costs by SHARED_UNITS
    name; a unit it doesn't give is posted at the price in force (which moves nothing). `list_prices`: the public list
    prices by family name; a priced or announced family with no list price here is also posted at the price in force,
    so the table still counts (a table must price every priced family)."""
    in_force = chain.shared_prices()
    shared = [int((costs or {}).get(u) or in_force[i]) for i, u in enumerate(SHARED_UNITS)]
    by_id = {v3.name_id(name): [int(x) for x in t] for name, t in list_prices.items()}
    families, tokens = [], []
    for fam in chain.priced_families():
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

    FIELDS = ("pid", "submission", "kind", "vote", "mask", "salt", "receipt", "judged")

    def plain(self) -> dict:
        data = {f: getattr(self, f) for f in self.FIELDS}
        if self.usage is not None:
            data["usage"] = list(self.usage.as_tuple())
        return data

    @classmethod
    def from_plain(cls, data: dict) -> "Round":
        r = cls(**{f: data[f] for f in cls.FIELDS})
        if data.get("usage"):
            r.usage = v2.Usage(*data["usage"])
        return r


@dataclass
class Judgement:
    vote: bool
    doc: dict  # the receipt's document, stored under its on-chain hash
    receipt: str
    usage: v2.Usage
    tests_passed: bool | None


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
        self._tries: dict = {}
        self._kept: set = set()
        self._live: dict | None = None

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
            elif self.keys.quote(b"").kind != QUOTE_KINDS[proof]:
                raise SetupError(_quote_hint(proof, self.keys.quote(b"").kind))
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
        try:
            progress |= self._table()
        except Reverted as e:
            self._say(("table", e.reason), f"table: the chain refused it ({e.reason}); trying again")
        if self.keeper:
            progress |= self._keep(from_block, now)
        return progress

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
            r.vote, r.receipt, r.usage, r.judged = j.vote, j.receipt, j.usage, True
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
        if now <= p["sealBy"] or (r.kind != v3.SHADOW and (p["seats"] < p["k"] or p["nSealed"] < p["k"])):
            return False  # the reveal window isn't open: every seat seals first
        mine = v3.commitment_of(self.chain.panels, r.pid, self.address, r.vote, r.mask, r.salt)
        if not r.judged or v3.b32(seat["seal"]) != mine:
            self._finish(r, "the seal on-chain isn't one this node can open; not revealing")
            return True
        if not seat["receipted"]:
            rh = bytes.fromhex(r.receipt)
            self.exchange.put(r.pid, self.address, "receipt",
                              {"receipt": _hex(rh), "sig": self._sign(v3.RECEIPT_TAG, self.chain.panels, r.pid, rh)})
        if not seat["revealed"]:
            content = v3.reveal_content(r.vote, r.mask, r.salt)
            self.exchange.put(r.pid, self.address, "reveal",
                              {"vote": r.vote, "mask": r.mask, "salt": _hex(r.salt),
                               "sig": self._sign(v3.REVEAL_TAG, self.chain.panels, r.pid, content)})
        self.log(f"panel {r.pid}: revealed {'pass' if r.vote else 'fail'}, receipt {r.receipt[:12]} on-chain")
        return True

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
            answer, tests, fix_tree, seconds = self._registration(issue_id, onchain, late)
        else:
            answer, tests, fix_tree, seconds = self._fix(s, sub, issue_id, onchain, late)
        return self._receipt(s, sub, p, answer, tests, fix_tree, seconds, profile, seat)

    def _fix(self, s: int, sub: dict, issue_id: int, onchain: dict, late: bool) -> tuple:
        pull = self._find_pull(s, sub)
        if pull is None:
            if not late:
                raise evidence.NotReady(f"no pull request opens submission {s}'s sealed commitment yet")
            why = "no pull request opened the sealed commitment before the seal deadline"
            self.log(f"submission {s}: not passed: {why}")
            return refused(case_for(self.repo_name, "", "", ""), _no_run(), why), _no_run(), "", 0.0
        c = SimpleNamespace(pull=pull, bounty=sub["bounty"], submission=s)
        case, refusal = self._case(c, onchain, issue_id)
        command, why = self._test_command(pull)
        refusal = refusal or why
        src = self.src_root / pull["head_sha"]
        started = time.monotonic()
        tests = (run_tests(src, command=command, runner=self.runner) if self.runner
                 else run_tests(src, command=command))
        seconds = time.monotonic() - started
        if refusal:
            self.log(f"submission {s}: not sent to the model, and not passed: {refusal}")
        answer = refused(case, tests, refusal) if refusal else self.judge.judge(case, tests)
        return answer, tests, pull["head_sha"], seconds

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
        """A registration check, by v2's rule (#210): it passes when a labelled issue on the repository host validly
        claims the registration. With the fake judge only, as in v2: a model's registration check isn't designed
        yet (#160), and until it is such a node stays silent on these (which costs it the silence slash)."""
        from bot import logic

        if not isinstance(self.judge, FakeJudge):
            raise ModelError("registration checks with a model judge aren't supported yet")
        issues = evidence.host_call(self.host.issues, "all", logic.LABEL)
        claim = logic.first_valid_claim(issues, {"id": issue_id, "reporter": onchain["reporter"],
                                                 "repo": onchain["repo"]}, self._repo_id(), logic.LABEL)
        if claim is None and not late:
            raise evidence.NotReady(f"registration {issue_id} isn't claimed by a labelled issue yet")
        why = (f"issue #{claim} validly claims registration {issue_id}" if claim is not None else
               f"no labelled issue claimed registration {issue_id} before the seal deadline")
        text = json.dumps({"solves": claim is not None, "probability": 1 if claim is not None else 0,
                           "constitutional": True, "reason": why, "evidence": []})
        from .judge import Answer

        model = f"fake-judge-{self.judge.family}" + ("-lying" if self.judge.lie else "")
        solves = (claim is not None) != self.judge.lie
        return Answer(solves, model, "fake", f"registration check: issue {issue_id}", text), _no_run(), "", 0.0

    def _repo_id(self) -> bytes:
        """The repository a registration must name: the configured one, else the deployment's own (v3 serves exactly
        one, RaceV3.repo, #251 L1)."""
        return self.repo_id if self.repo_id != v3.ZERO else self.chain.repo()

    def _receipt(self, s: int, sub: dict, p: dict, answer, tests: TestRun, fix_tree: str, seconds: float,
                 profile: dict, seat: tuple | None = None) -> Judgement:
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
            if q.kind != QUOTE_KINDS[proof_type]:
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
        h = self.receipts3.put(doc)
        usage = v2.measured_usage(h, answer.prompt, answer.response, seconds, profile["milliVcpus"],
                                  profile["memoryMb"], len(receipts.canonical(doc)), getattr(answer, "usage", None))
        self.log(f"submission {s}: {'pass' if answer.solves else 'fail'} (tests exit {tests.exit_code}, "
                 f"{answer.model}); receipt {h[:12]}")
        return Judgement(bool(answer.solves), doc, h, usage, None if not fix_tree else tests.passed)

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
                                               lambda m: self._say(("table", m), m))
        self.wallet.send(self.chain.fees, "post(uint256[4],bytes32[],uint256[3][])", shared, families, tokens)
        self.log(f"table posted: {len(families)} families' list prices and this validator's shared-unit costs")
        return shared, families, tokens

    # ---------- the keeper ----------

    def _call(self, to: str, signature: str, *args, once: bool = False) -> bool:
        """A call anyone may make. A revert means it isn't due (or someone else made it): no progress. `once`: a call
        that succeeds one time only (a panel's pay): not sent again after it worked, or after GIVE_UP refusals."""
        key = (to, signature, args)
        if once and self._settled(key):
            return False
        try:
            self.wallet.send(to, signature, *args)
        except Reverted:
            self._tries[key] = self._tries.get(key, 0) + 1
            return False
        if once:
            self._kept.add(key)
        self.log(f"keeper: {signature.split('(')[0]}({', '.join(str(a) for a in args)})")
        return True

    def _settled(self, key) -> bool:
        return key in self._kept or self._tries.get(key, 0) >= GIVE_UP

    def _keep(self, from_block: int, now: int) -> bool:
        c, progress = self.chain, False
        ids = {e["submission"] for e in c.committed(from_block)} | {e["submission"] for e in c.registered(from_block)}
        block = c.block()
        for s in sorted(ids):
            v = c.verdict(s)
            st = v["status"]
            if st == v3.SEALED and block > v["seedBlock"]:
                progress |= self._call(c.panels, "draw(uint256)", s) and self._call(c.race, "signal(uint256)", s)
            elif st == v3.WAITING:
                self._call(c.race, "signal(uint256)", s, once=True)  # FeesV3 counts the wait once
                # redrawn once the registry changes or at its scheduled time (L19's RETRY_DELAY, L16's capacity hour)
                if c.epoch() + 1 != v.get("waitEpoch", 0) or now >= v.get("retryAt", 0):
                    progress |= self._call(c.panels, "draw(uint256)", s)
            elif st in (v3.HELD, v3.WINDOW):
                if st == v3.HELD:
                    progress |= self._call(c.panels, "startWindow(uint256)", s)
                waits = v.get("auditWaits") and c.epoch() + 1 == v.get("auditEpoch")
                if (block > v["auditBlock"] and not waits
                        and not (v["auditDecided"] and v["auditsDrawn"] == v["auditsDue"])):
                    # With no auditor eligible the audits wait for the registry to change (`auditWaits`), and the
                    # contract refuses every call until it does (#251 task 3.10); then one call re-targets and the
                    # next draws from the new snapshot. A few tries per state of the registry, as before.
                    tried = ("audits", s, v["auditsDrawn"], v["auditDecided"], c.epoch())
                    if self._tries.get(tried, 0) < AUDIT_TRIES:
                        self._tries[tried] = self._tries.get(tried, 0) + 1
                        progress |= self._call(c.panels, "drawAudits(uint256)", s)
                stuck = v.get("auditStuckAt", 0)
                if (st == v3.WINDOW and stuck and not v["challengeOpen"] and v["auditsDrawn"] < v["auditsDue"]
                        and now > stuck + self._liveness()["stuckGrace"]):
                    # audits nobody could take for STUCK_GRACE: the round is released (L19), the audit drawn afresh
                    progress |= self._call(c.panels, "releaseAudits(uint256)", s)
                if v["challengeOpen"] and v["challengePid"] == 0 and block > v["challengeBlock"]:
                    progress |= self._call(c.panels, "drawChallenge(uint256)", s)
                if (st == v3.WINDOW and now >= v["finalAt"] and not v["challengeOpen"] and v["auditDecided"]
                        and v["auditsDone"] >= v["auditsDue"]):
                    progress |= self._call(c.panels, "finalize(uint256)", s)
            if st in (v3.HELD, v3.WINDOW, v3.FINAL) or (st == v3.RELEASED and v["pid"]):
                sub = c.submission(s)
                if not sub["paid"]:
                    progress |= self._call(c.race, "result(uint256)", s)
                elif st == v3.FINAL and not sub["done"]:
                    progress |= self._call(c.race, "finish(uint256)", s)
            if st == v3.FINAL:
                progress |= self._merge(s)
            if st == v3.RELEASED or (v.get("redraws") and st in (v3.SEALED, v3.WAITING)):
                # never judged: refunded once Panels released it for good, or at the race's deadline once a round was
                # released (L19). Before the deadline the race refuses (no progress).
                if not c.submission(s)["done"]:
                    progress |= self._call(c.race, "release(uint256)", s)
        for pid in range(1, c.panel_count() + 1):
            if ("panel", pid) not in self._kept:
                progress |= self._keep_panel(pid, now)
        if c.rolled() < c.current_period():
            progress |= self._call(c.fees, "roll()")
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
                    progress |= self._call(pay[0], pay[1], pid, slot, once=True)
                owed |= not self._settled(pay) and now <= p["revealBy"] + REPORT_WINDOW_S  # its report may still come
            if p["closed"] and p["scored"] and not owed:
                self._kept.add(("panel", pid))
            return progress
        if p["counted"]:
            if p["kind"] in (v3.AUDIT, v3.CHALLENGE):  # a race-filed challenge's panel is settled, the others paid
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
            return False
        if p["seats"] < p["k"]:
            if self._call(c.panels, "refill(uint256)", pid):
                return self._call(c.race, "signal(uint256)", p["id"]) or True
            if now > p["revealBy"] + self._liveness()["stuckGrace"] and p["kind"] in (v3.COUNTED, v3.AUDIT):
                # replacements exhausted: the round ends, its silent seats slashed, the submission waits (L19)
                return self._call(c.panels, "release(uint256)", pid)
            return False
        if (now > p["sealBy"] and p["nSealed"] < p["seats"]) or (now > p["revealBy"] and p["done"] < p["k"]):
            return self._call(c.panels, "advance(uint256)", pid) and self._call(c.race, "signal(uint256)", p["id"])
        return False

    def _merge(self, s: int) -> bool:
        """#251 L9: a claimed fix whose verdict is final moves the head (`merge`, anyone, once). A stale base reverts
        (the winner keeps its place until the merge deadline); the keeper leaves it after GIVE_UP refusals."""
        c = self.chain
        sub = c.submission(s)
        b = sub["bounty"]
        if not b:
            return False
        bt = c.bounty(b)
        if bt["state"] != v3.CLAIMED or bt["winner"] != s or not bt["epoch"]:
            return False
        if c.award(b, bt["epoch"])["merged"]:
            return False
        return self._call(c.race, "merge(uint256)", b, once=True)

    def _liveness(self) -> dict:
        """Panels' L19 values (read once): STUCK_GRACE, RETRY_DELAY, MAX_REDRAWS."""
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


def _no_run() -> TestRun:
    """A check with no fix to test: nothing ran."""
    empty = hashlib.sha256(b"").hexdigest()
    return TestRun("none", (), 125, empty, empty)


def _quote_hint(proof: bytes, kind: str) -> str:
    if proof == v3.PROOF_SIMULATED:
        return (f"the `simulated` proof type's quote comes from the dstack simulator (D18): set ORACLE_KEYS=dstack "
                f"and DSTACK_SIMULATOR_ENDPOINT (this node's key gives {kind!r})")
    return f"a TEE validator's quote comes from its dstack guest agent (ORACLE_KEYS=dstack); this key gives {kind!r}"


# ---------- register and leave ----------

def registration(chain: v3.Chain, keys, *, proof: str, family: str, host: str, image: bytes, operator: str = "",
                 tee_type: str = "", level: int = v3.LEVEL_A, firmware: int = 0) -> tuple:
    """(the registration this key would sign, its attestation's document). For a TEE and for `simulated` the
    attestation is the hash of a quote over this key and registry; zkTLS has none."""
    me, proof_type = keys.address(), v3.PROOFS[proof]
    if proof_type == v3.PROOF_ZKTLS:
        return (v3.Registration(me, operator or me, proof_type, v3.ZERO, 0, v3.ZERO, image, v3.name_id(host),
                                v3.name_id(family), 0), {})
    q = keys.quote(keccak256(REGISTRATION_NOTE + chain.domain() + v3.address_word(me)))
    if q.kind != QUOTE_KINDS[proof_type]:
        raise SetupError(_quote_hint(proof_type, q.kind))
    if not q.quote:
        raise SetupError("the guest agent gave no quote")
    attestation = keccak256(bytes.fromhex(q.quote))
    r = v3.Registration(me, operator or me, proof_type, v3.name_id(tee_type), level, attestation, image,
                        v3.name_id(host), v3.name_id(family), firmware)
    return r, {"kind": q.kind, "quote": q.quote, "report_data": q.report_data}


def register(chain: v3.Chain, keys, wallet, bond: int, store_root: Path | None = None, log=print, **what):
    """Registers this node's key as a candidate with `bond` micro-coins from the wallet's account."""
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
    log(f"registered {r.key} as a candidate (operator {r.operator}, bond {bond / 10**6:,.2f}); it's drawn as a "
        f"shadow until it qualifies")
    return r


def leave(chain: v3.Chain, keys, wallet, log=print) -> None:
    """Announces leaving: never drawn again, still slashable; the bond is withdrawable after the unbonding delay."""
    wallet.send(chain.registry, "leave(address)", keys.address())
    log(f"{keys.address()} is leaving; its bond can be withdrawn after the unbonding delay, once every verdict it "
        f"gave is final and every challenge naming it is closed")


def withdraw_bond(chain: v3.Chain, keys, wallet, log=print) -> None:
    wallet.send(chain.registry, "withdraw(address)", keys.address())
    log(f"{keys.address()}: bond withdrawn to its operator account")
