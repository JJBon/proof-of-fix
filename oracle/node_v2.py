"""The v2 judge node (proof-of-fix#104, on #85's contracts): a validator's process that acts only for the submissions
its seat is drawn for, and gets paid by the meter for the checks it counts.

For each sealed submission (RaceV2's `Committed` events):
1. the draw: `Verdicts.drawn(seed, bounty, submission, race)`. Not drawn, or recused: nothing to do;
2. the claim: the pull request on the repository host whose body claims the submission (bot/logic.py's claim), whose
   head commit and salt open the sealed commitment (fix = the head commit as bytes32, as Heads keeps commits);
3. the check: the evidence (the issue, the commit, the diff the node computes itself: oracle/evidence.py, #166), the
   fix's tests in the sandbox (oracle/sandbox.py), with the repository's own test command read at the pull request's
   base (oracle/checkconfig.py, #166), the judge (fake, the provider called directly (oracle/models.py,
   #118), or the gateway in development), a receipt;
4. the usage report, signed and sent to the meter (`Fees.report`) before any result: the judge backend's tokens, the
   sandbox's vCPU-seconds and GB-seconds at the repository's CI profile, the receipt's storage;
5. seal, then reveal, with the other drawn judges (the exchange); the outcome two of three reach is the verdict;
6. the agreeing judges sign the verdict v2 (`Result` with an empty fee list: the meter pays), and the lowest-addressed
   one relays `RaceV2.result`;
7. once the winning pull request is merged on the host, the same judges sign `Merged` and one relays it. With
   ORACLE_MERGE_VIA=radicle (oracle/radicle.py, #201) there's no host merge to wait for: the drawn judges' nodes,
   the repository's delegates, push the fix to their Radicle copies and sign once it is canonical main by the
   delegate threshold, on top of Heads' head; any other canonical main is refused.

The exchange is the node's transport (oracle/transport.py, #117): a directory the nodes share (ORACLE_EXCHANGE, one
machine: the tests and the folder demo) or the exchange service (exchange/, ORACLE_EXCHANGE_URL) for validators on
separate machines; both carry the same messages. Every message is signed by its node's key and checked against the
drawn judges, so a writer to the directory, or the service, can withhold messages but can't vote.

A node keeps its round in memory, so it survives what it can (#166), and, with a round store (ORACLE_ROUNDS,
oracle/rounds.py, #216), on its own disk too: a restarted node finishes a round it sealed, with the same salt. A pass rescans the chain from the same block, so
nothing is skipped, and each step records its result only once done, so a pass that fails repeats nothing that worked.
The chain not answering (oracle/rpc.py's Unavailable, after its retries) ends the pass, not the run: the node tries
again until the chain's back, with its salts and seals intact. Only `outage_limit` ends a run for it, and then the
process exits non-zero. The host not answering just means no progress this pass."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import checkconfig, crypto, evidence, radicle as rad, receipt as receipts, rounds as round_store, v2
from .judge import case_for, refused
from .models import ModelError
from .keys import KeyProvider
from .rpc import Reverted, Unavailable, Wallet
from .sandbox import run_tests
from .transport import FolderExchange as Exchange  # noqa: F401 (the folder, under its old name)

CHECKER_IMAGE = os.environ.get("POF_ORACLE_IMAGE", "local-unpinned")
USAGE_T = v2.USAGE
VERDICT_T = v2.VERDICT


def same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _signed_by(node: str, payload: bytes, sig_hex: str) -> bool:
    try:
        return same(crypto.recover(crypto.keccak256(payload), bytes.fromhex(sig_hex[2:])), node)
    except (ValueError, TypeError):
        return False


@dataclass
class Check:
    """One submission this node judges, as far as it got."""
    submission: int
    bounty: int
    judges: list
    pull: dict | None = None
    outcome: int = 0
    receipt_hash: str = ""
    salt: bytes = field(default_factory=lambda: secrets.token_bytes(32))
    reported: bool = False
    sealed_at: float = 0.0
    revealed_at: float = 0.0
    signed: bool = False
    merge_signed: bool = False
    done: bool = False
    note: str = ""
    usage: v2.Usage | None = None


class NodeV2:
    def __init__(self, chain: v2.Chain, keys: KeyProvider, judge, host, repo_name: str, src_root: Path,
                 exchange: Exchange, store: receipts.Store, merge_weight: int, runner=None, clock=time.time,
                 round_timeout: float = 60.0, log=print, wallet=None) -> None:
        keys.check_chain(chain.chain_id())
        self.chain, self.keys, self.judge, self.host, self.repo_name = chain, keys, judge, host, repo_name
        self.src_root, self.exchange, self.store, self.merge_weight = Path(src_root), exchange, store, merge_weight
        self.runner, self.clock, self.round_timeout, self.log = runner, clock, round_timeout, log
        self.address = keys.address()
        self.wallet = wallet or Wallet(chain.rpc, keys.account_secret(), "node")  # its reports and relays
        self.checks: dict = {}
        self.skipped: set = set()
        self._last_not_ready = ""
        self._race_domain = self._fees_domain = None
        self.radicle: rad.Radicle | None = None  # ORACLE_MERGE_VIA=radicle: the merge is canonical main's (#201)
        self.registrations = None  # ORACLE_REGISTRATION_CHECK=on: the seats' registration check (#210, oracle/registration.py)
        self.rounds: round_store.Store | None = None  # ORACLE_ROUNDS: its rounds on disk, for a restart (#216)

    # ---------- the loop ----------

    def run(self, from_block: int, until_idle: float | None = None, poll: float = 2.0,
            outage_limit: float | None = None) -> int:
        """Ticks until `until_idle` seconds pass without progress (forever without it). Returns the checks done. A chain
        that doesn't answer isn't idleness: the node keeps trying, and raises Unavailable only once it has been away for
        `outage_limit` seconds (never without one), so the caller can end the run as unfinished."""
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
                away_since, last = None, self.clock()  # the idle time starts again from the chain's return
            if progress or (self.registrations is not None and self.registrations.waiting()) or self.in_window():
                last = self.clock()  # a claimed registration not open yet isn't idleness either (#210), nor a round
                # waiting out its window for the other judges (#216)
            elif until_idle is not None and self.clock() - last >= until_idle:
                self.log(f"node {self.address}: idle for {until_idle:.0f}s, stopping")
                return sum(1 for c in self.checks.values() if c.done)
            time.sleep(poll)

    def in_window(self) -> bool:
        """A round this node sealed is still inside its window: waiting for the other drawn judges' seals, reveals or
        signatures, or the merge's signatures (#216). Once the window closes, the next step moves on by itself (a
        reveal, a signature at quorum), so the wait is bounded by the round timeout; a round that then has nothing to
        do (no quorum, a merge that hasn't happened) is idleness, as before."""
        now = self.clock()
        return any(c.sealed_at and not c.done and c.submission not in self.skipped
                   and now - max(c.sealed_at, c.revealed_at) < self.round_timeout for c in self.checks.values())

    def tick(self, from_block: int) -> bool:
        """One pass. Raises Unavailable, with nothing recorded for the step it stopped at, if the chain doesn't answer."""
        progress = False
        if self.registrations is not None:
            try:
                progress |= self.registrations.tick(from_block)
            except Reverted as e:
                self.log(f"registration check: the chain refused a relay ({e.reason}); retrying")
            except evidence.NotReady as e:
                if str(e) != self._last_not_ready:
                    self.log(f"registration check: not yet: {e}; trying again")
                    self._last_not_ready = str(e)
        for ev in self.chain.committed(from_block):
            s = ev["submission"]
            if s in self.skipped:
                continue
            c = self.checks.get(s)
            if c is not None and c.done:
                continue
            try:
                progress |= self._advance(s, ev["bounty"], c)
            except Reverted as e:
                self.log(f"submission {s}: the chain refused it ({e.reason}); retrying")
            except ModelError as e:  # no answer from the model, after the bounded retries: no verdict from this
                self.log(f"submission {s}: not judged ({e}); skipping")  # node, and no further calls for it here
                self.skipped.add(s)
            except evidence.NotReady as e:  # the host or git, not the fix: no verdict yet, and no progress this pass
                if str(e) != self._last_not_ready:
                    self.log(f"submission {s}: not judged yet: {e}; trying again")
                    self._last_not_ready = str(e)
        return progress

    # ---------- one submission ----------

    def _advance(self, s: int, bounty: int, c: Check | None) -> bool:
        progress = self._step(s, bounty, c)
        c = self.checks.get(s)
        if progress and c is not None and self.rounds is not None:  # each step's result, before the next leaves
            if c.done:  # the node (#216): the salt is on disk before the seal is on the exchange
                self.rounds.remove(s)
            else:
                self.rounds.save(c)
        return progress

    def _resume(self, s: int, judges: list) -> Check | None:
        """The round this seat saved before a restart (#216), if it's for the same draw."""
        if self.rounds is None:
            return None
        c = self.rounds.load(s, Check)
        if c is None or [k.lower() for k in c.judges] != [k.lower() for k in judges]:
            return None
        return c

    def _step(self, s: int, bounty: int, c: Check | None) -> bool:
        sub = self.chain.submission(s)
        if c is None:
            judges, recused = self.chain.drawn(sub["seed"], sub["bounty"], s)
            if any(same(k, self.address) for k in recused):
                self.log(f"submission {s}: recused (an operator of this seat is a party); skipping")
                self.skipped.add(s)
                return True
            if not any(same(k, self.address) for k in judges):
                self.log(f"submission {s}: not drawn (judges {', '.join(k[:10] for k in judges)}); skipping")
                self.skipped.add(s)
                return True
            if sub["outcome"] != v2.NONE and not self._merge_due(s, sub):
                self.skipped.add(s)
                return False
            resumed = self._resume(s, judges) if sub["outcome"] == v2.NONE else None
            if resumed is not None:
                self.checks[s] = resumed
                step = ("revealed" if resumed.revealed_at else "sealed" if resumed.sealed_at else
                        "judged" if resumed.outcome else "drawn")
                self.log(f"submission {s}: resuming this seat's round from disk ({step} before a restart)")
                return True
            if sub["outcome"] == v2.NONE and any(same(r["judge"], self.address) for r in self.chain.reports(s)):
                # An earlier run of this seat reported, and its salt went with it: the first seal stands, and this node
                # couldn't open it. Judging again would only pay for a verdict the round can't take.
                self.log(f"submission {s}: this seat judged it in an earlier run; sitting the round out")
                self.skipped.add(s)
                return True
            c = self.checks[s] = Check(s, sub["bounty"], judges)
            self.log(f"submission {s}: drawn, with {', '.join(k[:10] for k in judges if not same(k, self.address))}")
            return True
        if sub["outcome"] != v2.NONE:
            return self._merge(c, sub)
        if c.pull is None:
            return self._find_claim(c, sub)
        if not c.outcome:
            return self._check(c, sub)
        if not c.reported:
            return self._report(c)
        if not c.sealed_at:
            return self._seal(c)
        if not c.revealed_at:
            return self._reveal(c)
        return self._sign_and_relay(c, sub)

    def _find_claim(self, c: Check, sub: dict) -> bool:
        from bot import logic  # the claim's format is the bot's (pofctl prints it)

        from . import fetch  # the fix's code: fetched and verified (#115), or a checkout already there

        for p in evidence.host_call(self.host.pulls, "all"):
            cl = logic.claim(p["body"])
            if cl is None or cl.submission != c.submission:
                continue
            fix = v2.commit_word(p["head_sha"])
            ok = (cl.bounty == sub["bounty"] and same(cl.solver, sub["solver"]) and
                  crypto.commitment(fix, bytes.fromhex(cl.salt[2:]), cl.solver) == v2.b32(sub["commitment"]))
            if not ok:
                if c.note != f"refused #{p['number']}":
                    self.log(f"submission {c.submission}: pull request #{p['number']} doesn't open its seal; refused")
                    c.note = f"refused #{p['number']}"
                continue
            if not fetch.ensure(self.src_root, p, fix, getattr(self, "fetcher", None)):
                if c.note != "no sources":
                    self.log(f"submission {c.submission}: no checkout of {p['head_sha'][:12]} under {self.src_root}")
                    c.note = "no sources"
                return False
            c.pull = {**p, "fix": fix}
            self.log(f"submission {c.submission}: pull request #{p['number']} opens the seal "
                     f"(commit {p['head_sha'][:12]})")
            return True
        return False

    def _case(self, c: Check, onchain: dict, issue_id: int) -> tuple:
        """(the judge's case, why no judge can read this fix, or ""). A judge that reads only the test run (the fake)
        gets the pull request's title, as it always has: nothing to fetch and no host call its verdict could depend on."""
        p = c.pull
        if not getattr(self.judge, "reads_evidence", True):
            return case_for(self.repo_name, p.get("title", ""), p.get("title", ""), ""), ""
        e = evidence.gather(self.host, getattr(self, "fetcher", None), self.src_root, p, p["fix"], self.chain.race,
                            c.bounty, issue_id, onchain["reporter"])
        return case_for(self.repo_name, e.issue, e.commit, e.diff, notes=e.notes), e.refusal

    def _test_command(self, p: dict) -> tuple:
        """(what the sandbox runs, why this fix can't pass, or ""). The repository's own tests come from
        `.pof/check.json` at the pull request's base, fetched by this node, never from the fix (oracle/checkconfig.py);
        without that file, or without a fetcher or a base to read it from, the sandbox's own command, as before.
        Raises NotReady when the base can't be fetched just now: that's not the fix's doing."""
        fetcher, base = getattr(self, "fetcher", None), p.get("base_sha", "")
        if fetcher is None or not base:
            return checkconfig.command(), ""
        blob = fetcher.file_at(self.src_root, base, checkconfig.PATH, checkconfig.MAX_BYTES)
        if blob is None:
            raise evidence.NotReady(f"no {checkconfig.PATH} from the base {base[:12]} yet")
        if blob.refusal:
            return checkconfig.command(), f"the repository's test command: {blob.refusal}"
        if blob.data is None:
            return checkconfig.command(), ""
        try:
            return checkconfig.command(checkconfig.parse(blob.data)), ""
        except checkconfig.Invalid as e:
            return checkconfig.command(), f"the repository's {checkconfig.PATH} at its base {base[:12]} is invalid: {e}"

    def _check(self, c: Check, sub: dict) -> bool:
        p = c.pull
        # Everything read from the chain and the host comes first: once the tests have run and the model has been paid,
        # no failure of theirs can throw the answer away and pay for it again.
        issue_id = self.chain.bounty(c.bounty)["issue"]
        onchain = self.chain.issue(issue_id)
        profile = self.chain.profile(onchain["repo"])
        case, refusal = self._case(c, onchain, issue_id)
        command, why = self._test_command(p)
        refusal = refusal or why
        src = self.src_root / p["head_sha"]
        started = time.monotonic()
        tests = (run_tests(src, command=command, runner=self.runner) if self.runner
                 else run_tests(src, command=command))
        seconds = time.monotonic() - started
        if refusal:
            self.log(f"submission {c.submission}: not sent to the model, and not passed: {refusal}")
        answer = refused(case, tests, refusal) if refusal else self.judge.judge(case, tests)
        outcome = v2.PASS if answer.solves else v2.FAIL
        rec = receipts.build(node=self.address, checker_image=CHECKER_IMAGE, model=answer.model,
                             backend=answer.backend, prompt=answer.prompt, response=answer.response,
                             fix_tree=p["head_sha"], tests=tests.record(), submission=c.submission,
                             bounty=c.bounty, outcome=outcome, chain_id=self.chain.chain_id(),
                             race=self.chain.race, attestation_kind=self.keys.quote(b"").kind,
                             issued_at=int(self.clock()), usage=getattr(answer, "usage", None),
                             inference=getattr(answer, "inference", None))
        c.receipt_hash = self.store.put(rec)
        stored = len(receipts.canonical(rec))
        c.usage = v2.measured_usage(c.receipt_hash, answer.prompt, answer.response, seconds, profile["milliVcpus"],
                                    profile["memoryMb"], stored, getattr(answer, "usage", None))
        c.outcome = outcome
        self.log(f"submission {c.submission}: {v2.OUTCOMES[c.outcome]} (tests exit {tests.exit_code} in "
                 f"{seconds:.1f}s, {answer.model}); receipt {c.receipt_hash[:12]}")
        return True

    def _report(self, c: Check) -> bool:
        if not any(same(r["judge"], self.address) for r in self.chain.reports(c.submission)):
            u = c.usage
            sig = self.keys.sign(v2.usage_digest(self.fees_domain(), c.submission, u))
            self.wallet.send(self.chain.meter, f"report(uint256,{USAGE_T},bytes)", c.submission, u.as_tuple(), sig)
            self.log(f"submission {c.submission}: usage reported to the meter (tokens {u.input} in, {u.output} out; "
                     f"{u.vcpu_seconds} vCPU-s, {u.gb_seconds} GB-s, {u.storage_mb} MB)")
        c.reported = True
        return True

    def _seal(self, c: Check) -> bool:
        seal = crypto.keccak256(bytes.fromhex(c.receipt_hash) + crypto.word(c.outcome) + c.salt
                                + crypto.word(self.address))
        self.exchange.put(c.submission, self.address, "seal",
                          {"seal": "0x" + seal.hex(), "sig": "0x" + self.keys.sign(crypto.keccak256(seal)).hex()})
        c.sealed_at = self.clock()
        return True

    def _seals(self, c: Check) -> dict:
        out = {}
        for node, m in self.exchange.all(c.submission, "seal").items():
            if any(same(node, j) for j in c.judges) and _signed_by(node, v2.b32(m["seal"]), m["sig"]):
                out[node] = v2.b32(m["seal"])
        return out

    def _reveal(self, c: Check) -> bool:
        seals = self._seals(c)
        if len(seals) < len(c.judges) and self.clock() - c.sealed_at < self.round_timeout:
            return False  # every drawn judge seals before anyone reveals, or the round times out
        self.exchange.put(c.submission, self.address, "reveal",
                          {"outcome": c.outcome, "receipt": c.receipt_hash, "salt": "0x" + c.salt.hex(),
                           "sig": "0x" + self.keys.sign(crypto.keccak256(bytes.fromhex(c.receipt_hash))).hex()})
        c.revealed_at = self.clock()
        return True

    def _reveals(self, c: Check) -> dict:
        seals, out = self._seals(c), {}
        for node, m in self.exchange.all(c.submission, "reveal").items():
            seal = seals.get(node)
            if seal is None or not _signed_by(node, bytes.fromhex(m["receipt"]), m["sig"]):
                continue
            want = crypto.keccak256(bytes.fromhex(m["receipt"]) + crypto.word(int(m["outcome"]))
                                    + bytes.fromhex(m["salt"][2:]) + crypto.word(node))
            if want == seal:  # a reveal that doesn't open its seal doesn't count
                out[node] = m
        return out

    def _verdict(self, c: Check, agreeing: dict, sub: dict) -> v2.Verdict:
        repo = v2.b32(self.chain.issue(self.chain.bounty(c.bounty)["issue"])["repo"])
        base = v2.commit_word(c.pull["base_sha"]) if c.pull.get("base_sha") else v2.ZERO
        rh = v2.receipts_hash({n: m["receipt"] for n, m in agreeing.items()})
        nonce = v2.verdict_nonce("result", c.submission, c.bounty, c.outcome, rh, c.pull["fix"])
        return v2.Verdict(repo, base, c.pull["fix"], c.bounty, c.submission, c.outcome, rh, v2.b32(sub["seed"]), nonce)

    def _sign_and_relay(self, c: Check, sub: dict) -> bool:
        reveals = self._reveals(c)
        late = self.clock() - c.revealed_at >= self.round_timeout
        if len(reveals) < len(self._seals(c)) and not late:
            return False
        agreeing = {n: m for n, m in reveals.items() if int(m["outcome"]) == c.outcome}
        if len(agreeing) < v2.ISSUE_QUORUM:
            if late and c.note != "no quorum":
                self.log(f"submission {c.submission}: no two judges agree with {v2.OUTCOMES[c.outcome]}; not signing")
                c.note = "no quorum"
            return False
        v = self._verdict(c, agreeing, sub)
        digest = v2.result_digest(self.race_domain(), v)
        if not c.signed:
            self.exchange.put(c.submission, self.address, "result",
                              {"verdict": v.to_json(), "sig": "0x" + self.keys.sign(digest).hex()})
            c.signed = True
            self.log(f"submission {c.submission}: signed the verdict ({v2.OUTCOMES[c.outcome]}, "
                     f"{len(agreeing)} of {len(c.judges)} agree)")
            return True
        relayer = min(agreeing, key=lambda a: int(a, 16))
        if not same(relayer, self.address):
            return False
        sigs = [m["sig"] for n, m in self.exchange.all(c.submission, "result").items()
                if n in agreeing and m["verdict"] == v.to_json()]
        if len(sigs) < len(agreeing) and not (len(sigs) >= v2.ISSUE_QUORUM and late):
            return False
        ordered = v2.ordered_signatures(digest, sigs)
        self.wallet.send(self.chain.race, f"result({VERDICT_T},(address,uint256)[],bytes[])", v.as_tuple(), [],
                         ordered)
        self.log(f"submission {c.submission}: relayed the result ({len(ordered)} signatures)")
        return True

    # ---------- the merge ----------

    def _merge_due(self, s: int, sub: dict) -> bool:
        if sub["outcome"] != v2.PASS:
            return False
        b = self.chain.bounty(sub["bounty"])
        return v2.STATES[b["state"]] == "Won" and b["winner"] == s

    def _merge(self, c: Check, sub: dict) -> bool:
        if not self._merge_due(c.submission, sub):
            c.done = True
            return True
        if self.radicle is not None:
            step = self._radicle_step(c, sub)
            if step != rad.SIGN:
                return step == rad.PUSH
            where = "the fix is canonical main on Radicle"
        else:
            if c.pull is None:
                for p in evidence.host_call(self.host.pulls, "all"):
                    if v2.commit_word(p["head_sha"]) == v2.b32(sub["fix"]):
                        c.pull = {**p, "fix": v2.b32(sub["fix"])}
                if c.pull is None:
                    return False
            if not evidence.host_call(self.host.pull, c.pull["number"])["merged"]:
                if c.note != "awaiting merge":
                    self.log(f"submission {c.submission}: won; waiting for pull request #{c.pull['number']} to merge")
                    c.note = "awaiting merge"
                return False
            where = f"pull request #{c.pull['number']} merged"
        repo = v2.b32(self.chain.issue(self.chain.bounty(c.bounty)["issue"])["repo"])
        fix, rh, seed = v2.b32(sub["fix"]), v2.b32(sub["receipt"]), v2.b32(sub["seed"])
        nonce = v2.verdict_nonce("merged", c.submission, c.bounty, v2.PASS, rh, fix)
        v = v2.Verdict(repo, v2.b32(sub["base"]), fix, c.bounty, c.submission, v2.PASS, rh, seed, nonce)
        digest = v2.merged_digest(self.race_domain(), v, self.merge_weight)
        if not c.merge_signed:
            self.exchange.put(c.submission, self.address, "merged",
                              {"verdict": v.to_json(), "weight": self.merge_weight,
                               "sig": "0x" + self.keys.sign(digest).hex()})
            c.merge_signed, c.sealed_at = True, self.clock()
            self.log(f"submission {c.submission}: {where}; signed the merge")
            return True
        signed = {n: m for n, m in self.exchange.all(c.submission, "merged").items()
                  if any(same(n, j) for j in c.judges) and m["verdict"] == v.to_json()
                  and m["weight"] == self.merge_weight}
        if not signed or not same(min(signed, key=lambda a: int(a, 16)), self.address):
            return False
        late = self.clock() - c.sealed_at >= self.round_timeout
        if len(signed) < len(c.judges) and not (len(signed) >= v2.ISSUE_QUORUM and late):
            return False
        ordered = v2.ordered_signatures(digest, [m["sig"] for m in signed.values()])
        self.wallet.send(self.chain.race, f"merged({VERDICT_T},uint256,bytes[])", v.as_tuple(), self.merge_weight,
                         ordered)
        self.log(f"submission {c.submission}: relayed the merge ({len(ordered)} signatures)")
        return True

    def _radicle_step(self, c: Check, sub: dict) -> str:
        """The merge on Radicle (oracle/radicle.py): SIGN once the won fix is canonical main by the delegate threshold;
        PUSH when this delegate just voted for it; WAIT or REFUSE otherwise (logged once each). A Radicle copy that
        can't be read is the host not answering: no progress this pass."""
        r = self.radicle
        repo = v2.b32(self.chain.issue(self.chain.bounty(c.bounty)["issue"])["repo"])
        fix, base = rad.sha_of(v2.b32(sub["fix"])), rad.sha_of(v2.b32(sub["base"]))
        if repo != r.repo_id:
            d = rad.Decision(rad.REFUSE, f"the bounty's repository 0x{repo.hex()[:12]} isn't {r.rid}'s")
        else:
            head = rad.sha_of(self.chain.head(repo)["commit"])
            try:
                snap = r.snapshot(extra=[fix])
                d = rad.decide(fix, base, head, snap, v2.ISSUE_QUORUM)
                if d.action == rad.PUSH:
                    r.push(fix)
            except rad.Unavailable as e:
                raise evidence.NotReady(str(e)) from None
        if d.action == rad.PUSH or c.note != d.reason:
            verb = {rad.PUSH: "pushed main", rad.REFUSE: "refused", rad.SIGN: "merged"}.get(d.action, "waiting")
            self.log(f"submission {c.submission}: Radicle: {verb}: {d.reason}")
            c.note = d.reason
        return d.action

    # ---------- domains (read from the contracts, so a node can't sign for the wrong one) ----------

    def race_domain(self) -> bytes:
        if self._race_domain is None:
            self._race_domain = self.chain.race_domain()
            if self._race_domain != v2.race_domain(self.chain.chain_id(), self.chain.race):
                raise RuntimeError("RaceV2's EIP-712 domain isn't v2's: refusing to sign")
        return self._race_domain

    def fees_domain(self) -> bytes:
        if self._fees_domain is None:
            self._fees_domain = self.chain.fees_domain()
            if self._fees_domain != v2.fees_domain(self.chain.chain_id(), self.chain.meter):
                raise RuntimeError("the meter's EIP-712 domain isn't v2's: refusing to sign")
        return self._fees_domain


def withdraw_fees(chain: v2.Chain, keys: KeyProvider, to: str | None = None) -> int:
    """Pulls the key's credit in the fee coin (its check fees, and any relay repayments) to `to` (default: the key's
    own address). A seat with a disclosed operator account is paid there instead: that account withdraws."""
    coin = chain.coin()
    owed = chain.owed(keys.address(), coin)
    if owed:
        Wallet(chain.rpc, keys.account_secret()).send(chain.race, "withdraw(address,address)", coin,
                                                      to or keys.address())
    return owed
