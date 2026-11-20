"""The v3 node on Radicle (proof-of-fix#251, model (a), design L9, L11, L12; tasks 4.1 and 4.2).

Two parts, each optional, both reaching the validator's own Radicle node through oracle/radicle.py's `Radicle` (a
command prefix such as `docker exec -i <container>`, or this machine):

1. **The fix source** (task 4.2, `RadicleFixes` and `RadicleFetcher`): a fix is a Radicle patch on the repository. The
   node lists the patches on its own node (synced first), takes the revision whose head commit, base and salt open
   the sealed commitment (the claim pofctl writes into the patch description: bot/logic's pull request lines), and
   fetches that commit from its own node's storage with oracle/fetch.py's verified, read-only fetch (a `file://`
   source; through the prefix with git's `--upload-pack`). The node refuses a revision whose base isn't `Heads.head`,
   and seals a failing verdict saying the fix wasn't available when it can't find or fetch it by the seal deadline
   (oracle/node_v3.py `_find_patch`).
2. **The registration check's issues** (task 4.3, `RadicleIssues`, design L12): a registration is claimed by a Radicle
   issue whose description or one of whose comments carries pofctl's claim lines (`Registration: N`, `Reporter wallet:
   0x…`, `Claim signature: 0x…`; `pofctl --v3 issue register --rad-issue … --comment` writes them as a comment). The
   signature is the reporter's, by the key that registered on-chain, over `claim_digest`: the chain, the race, the
   registration, the repository and the Radicle issue's id (the owner's decision of 2026-11-20; the issue id isn't
   stored on-chain), so a claim copied onto another issue, or to another registration, chain or race, doesn't verify.
   The node reads the issues on its own node (synced first), takes the one whose claim verifies (`find_claim`; the
   lowest issue id only as a tie-break between several that verify), and asks its judge whether that issue is a
   genuine bug report in the repository's scope (oracle/node_v3.py `_registration`). When none carries a signed
   claim, or the node's copy can't be read, by the seal deadline, it seals a failing verdict saying why.
3. **The seat** (task 4.1, `SeatAdapter`): each pass (at most every `every` seconds) reads `Heads.head` and the seats
   on-chain, then on its node
   - pushes its own signed `main` to `Heads.head` when the head moved (`radicle.decide_head`: the head moves only at
     finality, `RaceV3.merge`, L9), and refuses anything that doesn't fast-forward;
   - keeps the identity's delegates equal to the seats' nodes, one pending identity revision at a time
     (`delegates.identity_step`): reviews the oldest pending revision and signs accept or reject by the rule, and
     proposes only when none is pending.

The seat-to-node mapping is oracle/delegates.py's `SeatNodes`: the chain's (`ChainSeatNodes`, each validator's node
key signed into its v3 registration and read with `Validators.radNodeOf`, #251's contract change of 2026-11-20), the
default on v3; or, only for a deployment whose Validators predates that field, the first spike's signed bindings
(`DocumentBindings`, with this node's own binding signed by its validator key).

Configuration (environment, v3; see oracle/__main__.py):
    ORACLE_FIX_SOURCE     "host" (the default: pull requests on ORACLE_REPO's host, the registrations' claims on its
                          labelled issues) or "radicle" (patches and the registrations' issues on this validator's
                          Radicle node)
    ORACLE_MERGE_VIA      "radicle": run the seat's part (otherwise nothing is pushed or signed on Radicle)
    ORACLE_RADICLE_RID    the repository; its keccak256 must be the race's `repo()`
    ORACLE_RADICLE_EXEC   the command prefix that reaches the node (default: this machine)
    ORACLE_RADICLE_REPO   the working copy the node pushes `main` from (default ~/repo there)
    ORACLE_SEAT_NODES     "chain" (the default when the registry has `radNodeOf`) or "bindings" (the default, and the
                          only choice, for an older registry without it)
    ORACLE_SEAT_BINDINGS  "bindings" only: a JSON file of other validators' binding entries ({did: {"validator",
                          "sig"}}) to carry
    ORACLE_RADICLE_EVERY  seconds between two of the seat's passes (default 30)"""

from __future__ import annotations

import json
import re
import shlex
import time
from pathlib import Path

from . import abi, fetch, v3
from . import delegates as D
from . import radicle as R
from .crypto import keccak256, recover

TITLE = "The seats are the delegates"


class RadicleFetcher(fetch.Fetcher):
    """oracle/fetch.py's fetcher with this node's Radicle storage as its source: `file://<storage>`, resolved on the
    node at first use, reached through the node's command prefix with git's --upload-pack. Every check of the forge
    fetch holds (exactly the sealed commit, the limits, read-only, git's safe settings)."""

    UNAVAILABLE = "file:///radicle-storage-unavailable"

    def __init__(self, radicle: R.Radicle, log=print, **kw) -> None:
        super().__init__(self.UNAVAILABLE, log=log, **kw)
        self.radicle, self._url = radicle, None
        self.upload_pack = shlex.join([*radicle.prefix, "git-upload-pack"]) if radicle.prefix else ""

    @property
    def url(self) -> str:
        if self._url is None:
            try:
                self._url = "file://" + self.radicle.storage()
            except R.Unavailable as e:
                self.log(f"fetch: this node's Radicle storage isn't reachable: {e}")
                return self.UNAVAILABLE  # the fetch fails as any unreachable source does; tried again later
        return self._url

    @url.setter
    def url(self, value: str) -> None:
        self._url = None if value == self.UNAVAILABLE else value

    def __repr__(self) -> str:
        return f"RadicleFetcher({self.radicle.rid!r})"


class RadicleFixes:
    """The node's fix source on Radicle: the revisions of the patches on its own node (synced first)."""

    def __init__(self, radicle: R.Radicle) -> None:
        self.radicle = radicle

    def revisions(self) -> tuple:
        """(every patch revision as a pull request-like dict, delegates.patch_pulls; the sync's error, or ""). Raises
        radicle.Unavailable when the node's copy can't be read."""
        cobs, err = self.radicle.patches()
        return D.patch_pulls(cobs), err


class RadicleIssues:
    """The registration check's issue source on Radicle: the issues on this node's own copy (synced first)."""

    def __init__(self, radicle: R.Radicle) -> None:
        self.radicle = radicle

    def issues(self) -> tuple:
        """(every issue as `issue_view` gives it, in id order; the sync's error, or ""). Raises radicle.Unavailable
        when the node's copy can't be read."""
        cobs, err = self.radicle.issues()
        return sorted((issue_view(c) for c in cobs), key=lambda i: i["id"]), err


def issue_view(cob: dict) -> dict:
    """A `rad cob show --type xyz.radicle.issue` object (its id under "_id") as the check reads it: {id, title, state,
    labels, comments: [{id, author, body}] in the thread's order}. The first comment is the description (its id is the
    issue's); a comment's body is its latest edit, as Radicle shows it; a redacted one is left out."""
    thread = cob.get("thread") or {}
    comments = thread.get("comments") or {}
    order = [c for c in thread.get("timeline") or [] if c in comments] + sorted(
        c for c in comments if c not in (thread.get("timeline") or []))
    out = []
    for cid in order:
        c = comments.get(cid)
        if not isinstance(c, dict):
            continue
        author = c.get("author")
        author = author.get("id", "") if isinstance(author, dict) else str(author or "")
        out.append({"id": str(cid), "author": author, "body": str(c.get("body") or "")})
    return {"id": str(cob.get("_id", "")), "title": str(cob.get("title") or ""),
            "state": str((cob.get("state") or {}).get("status", "open")),
            "labels": [str(x) for x in cob.get("labels") or []], "comments": out}


def issue_text(issue: dict) -> str:
    """The issue as its judge reads it: its title, then its description and each comment in order, each under the
    author's Radicle ID. Everything in it was written by people: it's quoted as untrusted text."""
    parts = [f"Title: {issue['title']}", f"State: {issue['state']}"]
    for i, c in enumerate(issue["comments"]):
        what = "Description" if i == 0 else f"Comment {i}"
        parts.append(f"{what} (by {c['author'] or 'unknown'}):\n{c['body']}")
    return "\n\n".join(parts)


CLAIM_TAG = "pof-registration-claim-v1"
ISSUE_ID_RE = re.compile(r"^[0-9a-f]{40}$")  # a Radicle issue's collaborative-object id, whole


def claim_digest(chain_id: int, race: str, registration: int, repo_id: bytes, issue_id: str) -> bytes:
    """What a reporter signs to claim a registration for a Radicle issue: EIP-191 `personal_sign` over
    keccak256(abi.encode("pof-registration-claim-v1", chainId, race, registration, keccak256(RID), bytes20 issue id)).
    `repo_id` is keccak256(RID), the race's repository; `issue_id` the whole 40-hex id."""
    if not ISSUE_ID_RE.match(issue_id or ""):
        raise ValueError(f"a Radicle issue's whole id (40 hex), not {issue_id!r}")
    inner = keccak256(abi.encode(["string", "uint256", "address", "uint256", "bytes32", "bytes20"],
                                 [CLAIM_TAG, chain_id, race, registration, v3.b32(repo_id), bytes.fromhex(issue_id)]))
    return keccak256(b"\x19Ethereum Signed Message:\n32" + inner)


def signed_claim_lines(sign, reporter: str, chain_id: int, race: str, registration: int, repo_id: bytes,
                       issue_id: str) -> list:
    """The claim pofctl comments on the Radicle issue: bot/logic's two lines and the reporter's signature (`sign`: the
    reporter's key's signer over a 32-byte digest)."""
    from bot import logic

    sig = sign(claim_digest(chain_id, race, registration, repo_id, issue_id))
    return logic.claim_lines(registration, reporter, "0x" + sig.hex())


def claim_signer(body: str, chain_id: int, race: str, registration: int, repo_id: bytes, issue_id: str) -> str | None:
    """Who signed the claim in `body` for this chain, race, registration, repository and issue (None: no signature
    line, or one that doesn't recover)."""
    from bot import logic

    sig = logic.claim_signature(body)
    if sig is None:
        return None
    try:
        return recover(claim_digest(chain_id, race, registration, repo_id, issue_id), sig)
    except ValueError:
        return None


def find_claim(issues: list, onchain: dict, repo_id: bytes, chain_id: int, race: str) -> tuple:
    """(the issue that validly claims on-chain registration `onchain` ({"id", "reporter", "repo"}), the comment that
    carries its claim, how many issues validly claim it, why the others named it but don't) or (None, None, 0, why).
    A claim is valid when one text of the issue (its description or a comment) has pofctl's lines naming the
    registration and its on-chain reporter, and a signature by that reporter over `claim_digest` for this chain, race,
    repository (`repo_id`, which must be the registration's) and this issue's id. Among several, the lowest issue id:
    with the issue in the signature there should be one."""
    from bot import logic

    n, problems, valid = int(onchain["id"]), [], []
    reporter = str(onchain.get("reporter") or "0x0")
    if int(reporter, 16) == 0:
        return None, None, 0, [f"registration {n} doesn't exist on-chain"]
    if v3.b32(onchain.get("repo") or v3.ZERO) != v3.b32(repo_id):
        return None, None, 0, [f"registration {n} is another repository's"]
    for issue in issues:
        found = None
        for c in issue["comments"]:
            if logic.registration(c["body"]) != n:
                continue
            wallet = logic.wallet(c["body"], "Reporter")
            if wallet is None or wallet.lower() != reporter.lower():
                problems.append(f"issue {issue['id'][:7]} names registration {n} "
                                + ("with another wallet" if wallet else "without the reporter's wallet"))
                continue
            signer = (claim_signer(c["body"], chain_id, race, n, repo_id, issue["id"])
                      if ISSUE_ID_RE.match(issue["id"]) else None)
            if signer is not None and signer.lower() == reporter.lower():
                found = c
                break
            problems.append(f"issue {issue['id'][:7]} names registration {n} "
                            + ("with no signature" if logic.claim_signature(c["body"]) is None
                               else "with a signature that isn't the reporter's for this issue"))
        if found is not None:
            valid.append((issue, found))
    if not valid:
        return None, None, 0, problems
    issue, comment = min(valid, key=lambda v: v[0]["id"])
    return issue, comment, len(valid), problems


class SeatAdapter:
    """Model (a) on one validator's node: `Heads.head` pushed as its `main`, and the identity kept equal to the seats
    one pending revision at a time. `sign`: the validator key's signer (for its own seat binding); `log`: the node's."""

    def __init__(self, radicle: R.Radicle, chain, address: str, nodes: D.SeatNodes, sign=None, log=print,
                 every: float = 30.0, clock=time.monotonic) -> None:
        self.radicle, self.chain, self.address, self.nodes = radicle, chain, address, nodes
        self.sign, self.log, self.every, self.clock = sign, log, every, clock
        self._last: float | None = None
        self._said: dict = {}
        self.last_head: R.Decision | None = None
        self.last_identity: D.Step | None = None

    def _say(self, topic: str, line: str) -> None:
        if self._said.get(topic) != line:
            self._said[topic] = line
            self.log(line)

    def _bind_self(self, me: str) -> None:
        """This validator's own binding (the interim mapping travels in the identity document)."""
        if self.sign is None or not isinstance(self.nodes, D.DocumentBindings) or me in self.nodes.entries:
            return
        self.nodes.know(me, D.make_binding(self.sign, self.address, self.chain.chain_id(), self.chain.registry,
                                           self.radicle.rid, me))

    def tick(self, force: bool = False) -> bool:
        """One pass, at most every `every` seconds (or now with `force`). Returns True when it pushed, proposed or
        signed. Raises radicle.Unavailable when the node can't be read or written."""
        now = self.clock()
        if not force and self._last is not None and now - self._last < self.every:
            return False
        self._last = now
        head = R.sha_of(self.chain.head())
        seats = self.chain.seats()
        seated = self.address.lower() in {s.lower() for s in seats}
        snap = self.radicle.snapshot(extra=[head])
        if snap.sync_error:
            self._say("sync", f"Radicle: {snap.sync_error}; deciding on this node's own copy")
        progress = False
        d = R.decide_head(head, snap, seated)
        self.last_head = d
        if d.action == R.PUSH:
            self.radicle.push(head)
            self.log(f"Radicle: pushed main: {d.reason}")
            progress = True
        else:
            verb = {R.REFUSE: "refused", R.DONE: "in sync"}.get(d.action, "waiting")
            self._say("head", f"Radicle: main {verb}: {d.reason}")
        if not seated and R.nid(snap.me) not in {R.nid(x) for x in snap.delegates}:
            return progress
        self._bind_self(snap.me)
        cob, _, err = self.radicle.identity(sync=False)
        step = D.identity_step(cob, seats, self.nodes, snap.tips, head, snap.me)
        self.last_identity = step
        if step.action in (D.ACCEPT, D.REJECT):
            out = self.radicle.review(step.revision, step.action == D.ACCEPT)
            self.log(f"Radicle: identity: {step.action}ed {step.reason}" + _note(out))
            progress = True
        elif step.action == D.PROPOSE:
            out = self.radicle.propose(step.args, TITLE, f"Delegates = the nodes of the seats on-chain at Heads.head "
                                                         f"{head[:12]} (proof-of-fix#251, model (a))")
            self.log(f"Radicle: identity: {step.reason}" + _note(out))
            progress = True
        else:
            self._say("identity", f"Radicle: identity {'in sync' if step.action == D.IN_SYNC else 'waiting'}: "
                                  f"{step.reason}")
        return progress


def _note(out: str) -> str:
    err = R.sync_error(out)
    return f" ({err}: the other nodes see it at their next sync)" if err else ""


def has_rad_nodes(chain) -> bool:
    """Whether the registry records the validators' Radicle node keys (`radNodeOf`, #251's contract change): a
    registry from before it has no such function, and the call reverts."""
    from .rpc import Reverted

    try:
        chain.rad_node_of("0x" + "00" * 20)
    except (Reverted, AttributeError, ValueError):  # no such function: it reverts (or answers nothing)
        return False
    return True


def seat_nodes(env, chain, rid: str) -> D.SeatNodes:
    """The seat-to-node mapping ORACLE_SEAT_NODES names (see the module's docstring): the chain's by default when the
    registry has the field, the identity document's bindings for an older registry."""
    on_chain = has_rad_nodes(chain)
    kind = env.get("ORACLE_SEAT_NODES", "") or ("chain" if on_chain else "bindings")
    if kind not in ("chain", "bindings"):
        raise ValueError(f"ORACLE_SEAT_NODES: 'chain' or 'bindings', not {kind!r}")
    if kind == "chain":
        if not on_chain:
            raise ValueError("ORACLE_SEAT_NODES=chain: this deployment's Validators has no radNodeOf (it predates the "
                             "Radicle node key in the registration); use bindings")
        return D.ChainSeatNodes.of(chain)
    known = {}
    if env.get("ORACLE_SEAT_BINDINGS"):
        known = json.loads(Path(env["ORACLE_SEAT_BINDINGS"]).read_text(encoding="utf-8"))
        if not isinstance(known, dict):
            raise ValueError("ORACLE_SEAT_BINDINGS: a JSON object {did: {validator, sig}}")
    return D.DocumentBindings(chain.chain_id(), chain.registry, rid, known=known)


def from_env(env, chain, address: str, sign=None, log=print) -> tuple:
    """(the fix source, its fetcher, the seat's adapter) the environment configures; None for each part that's off.
    Raises ValueError on a configuration that can't be right (a RID that isn't the race's repository)."""
    source = env.get("ORACLE_FIX_SOURCE", "") or "host"
    via = env.get("ORACLE_MERGE_VIA", "") or "forge"
    if source not in ("host", "radicle"):
        raise ValueError(f"ORACLE_FIX_SOURCE: 'host' or 'radicle', not {source!r}")
    if via not in ("forge", "radicle"):
        raise ValueError(f"ORACLE_MERGE_VIA: 'forge' or 'radicle', not {via!r}")
    if source == "host" and via == "forge":
        return None, None, None
    rid = env.get("ORACLE_RADICLE_RID", "")
    if not rid:
        raise ValueError("Radicle on v3 needs ORACLE_RADICLE_RID")
    r = R.Radicle(rid, shlex.split(env.get("ORACLE_RADICLE_EXEC", "")), env.get("ORACLE_RADICLE_REPO", ""))
    if r.repo_id != chain.repo():
        raise ValueError(f"{rid} isn't the race's repository (keccak256 of the RID is 0x{r.repo_id.hex()[:12]}…, "
                         f"the race's 0x{chain.repo().hex()[:12]}…)")
    fixes = fetcher = seat = None
    if source == "radicle":
        fixes = RadicleFixes(r)
        max_mb = float(env.get("ORACLE_FETCH_MAX_MB", fetch.DEFAULT_MAX_MB))
        fetcher = RadicleFetcher(r, log=log, max_bytes=int(max_mb * (1 << 20)),
                                 timeout_s=float(env.get("ORACLE_FETCH_TIMEOUT", fetch.DEFAULT_TIMEOUT_S)))
    if via == "radicle":
        seat = SeatAdapter(r, chain, address, seat_nodes(env, chain, rid), sign=sign, log=log,
                           every=float(env.get("ORACLE_RADICLE_EVERY", "30")))
    return fixes, fetcher, seat
