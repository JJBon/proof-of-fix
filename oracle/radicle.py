"""The node's Radicle adapter (proof-of-fix#201, after #190's spike): the merge without a forge.

On Radicle there's no merge button. A repository's identity document lists its delegates (node keys) and a threshold,
and its canonical `main` is the newest commit that at least `threshold` delegates' signed `main` branches contain. With
the seats' nodes as the delegates and the threshold equal to the issue quorum (2), the drawn judges' pushes are the
merge, and the node signs `RaceV2.merged()` only for the commit that became canonical main by their votes, instead of
waiting for the forge's `merged` flag (ORACLE_MERGE_VIA=radicle; the forge stays the default).

For a won submission, each pass of a drawn judge's node:
1. reads the head on-chain, `Heads.head(repo)`, and refuses unless the verdict's base is that head (S1) and the
   bounty's repository is this RID's (`keccak256(RID)`, as the spike registered it);
2. takes a snapshot of its own Radicle copy: the identity (delegates, threshold), every namespace's signed `main`, the
   canonical ref Radicle computed, and the commit graph above them; then recomputes the canonical `main` itself from
   the delegates' branches alone (anyone else's `main`, an outsider's, counts for nothing);
3. decides (`decide`): the canonical main is the won fix: sign the merge. It's still Heads' head: vote, i.e. push this
   delegate's `main` to the fix if that fast-forwards it, then wait for the threshold. It's anything else: refuse,
   neither voting nor signing: Radicle and the chain disagree (a mismatch is #85 S1's alarm, not something to sign).

After the merge, Heads' head and the canonical main are the same commit; `pofctl verify-head` checks that for anyone.

The adapter runs `rad` and `git` through a command prefix (ORACLE_RADICLE_EXEC, e.g. `docker exec -i <container>`;
empty: on this machine), one shell call per snapshot. It never configures the Radicle node: its seeds, peers and
network are the operator's (the integration suite's are on an internal Docker network, tests/integration/radicle.py).
Protection lives where the delegate keys live: two delegates who skip this check can still move `main` (#190's
scenario G); the enclave-held keys are #94's."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass, field

from .crypto import keccak256

RID_RE = re.compile(r"^rad:z[1-9A-HJ-NP-Za-km-z]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SIGN, PUSH, WAIT, REFUSE = "sign", "push", "wait", "refuse"


class Unavailable(Exception):
    """The Radicle copy couldn't be read or written just now (the node or its container is down)."""


def repo_id(rid: str) -> bytes:
    """The repository's id in Heads for a Radicle repository: keccak256 of its RID (#190's convention)."""
    return keccak256(rid.encode())


def sha_of(word: bytes) -> str:
    """A commit as Heads keeps it (bytes32: a SHA-1 left-aligned, or a SHA-256 id) back to its hex id."""
    return word[:20].hex() if word[20:] == b"\0" * 12 else word.hex()


def nid(did: str) -> str:
    return did.removeprefix("did:key:")


@dataclass
class Snapshot:
    """One node's view of a repository: who it is, the identity in force, every namespace's signed `main`
    (Node ID -> commit), the canonical ref Radicle computed, and the commit graph (commit -> parents) above them."""
    me: str
    delegates: list
    threshold: int
    tips: dict
    canonical_ref: str | None
    parents: dict = field(default_factory=dict)
    missing: set = field(default_factory=set)

    def ancestors(self, sha: str) -> set:
        """`sha` and every commit it descends from, as far as the graph goes."""
        seen, todo = set(), [sha]
        while todo:
            c = todo.pop()
            if c in seen:
                continue
            seen.add(c)
            todo.extend(self.parents.get(c, ()))
        return seen

    def is_ancestor(self, a: str, b: str) -> bool:
        return a in self.ancestors(b)

    def votes(self, sha: str) -> list:
        """The delegates whose signed `main` contains `sha` (only delegates vote)."""
        ds = {nid(d) for d in self.delegates}
        return sorted(n for n, tip in self.tips.items() if n in ds and self.is_ancestor(sha, tip))


def canonical(s: Snapshot) -> str | None:
    """Radicle's rule as #190 observed it on 1.10.3: the newest commit at least `threshold` delegates' `main` branches
    contain (a branch counts for its tip and every ancestor). Branches of anyone not a delegate count for nothing. None
    when no commit has the votes, or when two diverging commits both do (no single newest)."""
    ds = {nid(d) for d in s.delegates}
    count: dict = {}
    for n, tip in s.tips.items():
        if n in ds:
            for c in s.ancestors(tip):
                count[c] = count.get(c, 0) + 1
    qualified = {c for c, k in count.items() if k >= s.threshold}
    if not qualified:
        return None
    below = {c: s.ancestors(c) - {c} for c in qualified}
    newest = [c for c in qualified if not any(c in below[o] for o in qualified if o != c)]
    return newest[0] if len(newest) == 1 else None


@dataclass(frozen=True)
class Decision:
    action: str  # SIGN, PUSH, WAIT or REFUSE
    reason: str


def decide(fix: str, base: str, head: str, s: Snapshot, quorum: int) -> Decision:
    """What a drawn judge's node does next for a won fix. `fix` and `base` are the winning submission's (the verdict's),
    `head` is `Heads.head(repo)` now; `quorum` is the issue tier's (2 of 3)."""
    if s.threshold != quorum:
        return Decision(REFUSE, f"the identity's threshold is {s.threshold}, not the quorum {quorum}")
    if base != head:
        return Decision(REFUSE, f"the verdict's base {base[:12]} isn't Heads' head {head[:12]} (stale, S1)")
    counted = canonical(s)
    if s.canonical_ref != counted:
        return Decision(WAIT, f"Radicle's canonical ref {(s.canonical_ref or 'none')[:12]} isn't what the delegates' "
                              f"branches give ({(counted or 'none')[:12]}); waiting for a sync")
    if counted == fix:
        return Decision(SIGN, f"canonical main is the fix {fix[:12]} ({len(s.votes(fix))} delegates of "
                              f"{len(s.delegates)}, threshold {s.threshold})")
    if counted != head:
        return Decision(REFUSE, f"canonical main {(counted or 'none')[:12]} is neither Heads' head {head[:12]} nor "
                                f"the won fix {fix[:12]}: Radicle and the chain disagree")
    if nid(s.me) not in {nid(d) for d in s.delegates}:
        return Decision(WAIT, "this node isn't a delegate: watching canonical main only")
    mine = s.tips.get(nid(s.me))
    if mine == fix:
        return Decision(WAIT, f"voted for {fix[:12]}; {len(s.votes(fix))} of the {s.threshold} delegates needed")
    if fix in s.missing:
        return Decision(WAIT, f"the fix {fix[:12]} isn't on this Radicle node yet")
    if mine is not None and not s.is_ancestor(mine, fix):
        return Decision(REFUSE, f"the fix {fix[:12]} doesn't fast-forward this delegate's main {mine[:12]}")
    return Decision(PUSH, f"canonical main is Heads' head {head[:12]}: voting for the fix {fix[:12]}")


def verify_head(head: str, s: Snapshot) -> Decision:
    """`pofctl verify-head`: the canonical main (Radicle's ref, and the delegates' count, which must agree) is Heads'
    head. SIGN when it is, REFUSE with both commits when it isn't."""
    counted = canonical(s)
    if s.canonical_ref != counted:
        return Decision(REFUSE, f"Radicle's canonical ref {s.canonical_ref or 'none'} isn't what the delegates' "
                                f"branches give ({counted or 'none'})")
    if counted != head:
        return Decision(REFUSE, f"canonical main {counted or 'none'} isn't Heads' head {head}")
    return Decision(SIGN, f"canonical main {head} is Heads' head ({len(s.votes(head))} of {len(s.delegates)} "
                          f"delegates, threshold {s.threshold})")


def parse_snapshot(out: str) -> Snapshot:
    """The snapshot script's output (Radicle.SNAPSHOT) as a Snapshot."""
    me, canonical_ref, section = "", None, ""
    identity, tips, parents, missing = [], {}, {}, set()
    for line in out.splitlines():
        if line.startswith("@me "):
            me = line[4:].strip()
        elif line.startswith("@canonical "):
            v = line[len("@canonical "):].strip()
            canonical_ref = v if SHA_RE.match(v) else None
        elif line.startswith("@missing "):
            missing.add(line[len("@missing "):].strip())
        elif line.strip() in ("@identity", "@refs", "@graph", "@end"):
            section = line.strip()
        elif section == "@identity":
            identity.append(line)
        elif section == "@refs" and line.strip():
            ref, sha = line.split()
            m = re.match(r"^refs/namespaces/([^/]+)/refs/heads/main$", ref)
            if m and SHA_RE.match(sha):
                tips[m.group(1)] = sha
        elif section == "@graph" and line.strip():
            c, *ps = line.split()
            parents[c] = ps
    try:
        doc = json.loads("\n".join(identity))
    except json.JSONDecodeError as e:
        raise Unavailable(f"no identity document in the snapshot ({e})") from None
    return Snapshot(me, list(doc.get("delegates", [])), int(doc.get("threshold", 0)), tips, canonical_ref, parents,
                    missing)


class Radicle:
    """One node's Radicle copy of one repository, through `prefix` (a command prefix such as `docker exec -i <name>`;
    empty: this machine). `repo_dir`: the working copy the delegate pushes from (default ~/repo there)."""

    SNAPSHOT = r"""set -u
S="${RAD_HOME:-$HOME/.radicle}/storage/%(store)s"
if [ "%(sync)s" = 1 ]; then
  if command -v timeout >/dev/null; then timeout 30 rad sync --fetch --rid %(rid)s >/dev/null 2>&1 || true
  else rad sync --fetch --rid %(rid)s >/dev/null 2>&1 || true; fi
fi
echo "@me $(rad self --did)"
echo "@identity"; rad inspect %(rid)s --identity || exit 3
echo "@canonical $(git --git-dir "$S" rev-parse --verify -q refs/heads/main || echo none)"
echo "@refs"; git --git-dir "$S" for-each-ref --format='%%(refname) %%(objectname)' 'refs/namespaces/*/refs/heads/main'
tips=$(git --git-dir "$S" for-each-ref --format='%%(objectname)' 'refs/namespaces/*/refs/heads/main')
extra=""
for c in %(extra)s; do
  if git --git-dir "$S" cat-file -e "$c^{commit}" 2>/dev/null; then extra="$extra $c"; else echo "@missing $c"; fi
done
echo "@graph"; git --git-dir "$S" rev-list --parents $tips $extra
echo "@end"
"""

    PUSH = r"""set -eu
S="${RAD_HOME:-$HOME/.radicle}/storage/%(store)s"
git --git-dir "$S" cat-file -e "%(fix)s^{commit}"
cd %(repo)s
git fetch -q "$S" %(fix)s
git push -q rad %(fix)s:refs/heads/main 2>&1 | grep -v '^$' >&2 || true
me=$(rad self --did); me=${me#did:key:}
echo "@main $(git --git-dir "$S" rev-parse "refs/namespaces/$me/refs/heads/main")"
"""

    def __init__(self, rid: str, prefix=(), repo_dir: str = "", timeout: float = 120.0) -> None:
        if not RID_RE.match(rid):
            raise ValueError(f"not a Radicle RID: {rid!r}")
        self.rid, self.prefix, self.timeout = rid, list(prefix), timeout
        self.repo_dir = shlex.quote(repo_dir) if repo_dir else '"$HOME/repo"'
        self.repo_id = repo_id(rid)

    def _sh(self, script: str) -> str:
        try:
            r = subprocess.run(self.prefix + ["bash", "-c", script], capture_output=True, text=True,
                               timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Unavailable(f"Radicle: {e}") from None
        if r.returncode:
            raise Unavailable(f"Radicle: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-300:]}")
        return r.stdout

    def snapshot(self, extra=(), sync: bool = True) -> Snapshot:
        for c in extra:
            if not SHA_RE.match(c):
                raise ValueError(f"not a SHA-1: {c!r}")
        return parse_snapshot(self._sh(self.SNAPSHOT % {"store": self.rid[4:], "rid": self.rid, "sync": int(sync),
                                                        "extra": " ".join(extra)}))

    def push(self, fix: str) -> str:
        """Pushes this delegate's signed `main` to `fix` (git-remote-rad signs and announces it). Returns its `main`
        after the push. The decision to push is `decide`'s; this only does it."""
        if not SHA_RE.match(fix):
            raise ValueError(f"not a SHA-1: {fix!r}")
        out = self._sh(self.PUSH % {"store": self.rid[4:], "fix": fix, "repo": self.repo_dir})
        m = re.search(r"^@main ([0-9a-f]{40})$", out, re.M)
        if not m or m.group(1) != fix:
            raise Unavailable(f"Radicle: the push of {fix[:12]} didn't land (main {m.group(1) if m else '?'})")
        return m.group(1)


def from_env(env) -> Radicle | None:
    """ORACLE_MERGE_VIA: "forge" (the default: wait for the host's `merged`) or "radicle" (ORACLE_RADICLE_RID, the
    repository; ORACLE_RADICLE_EXEC, the command prefix to reach its node; ORACLE_RADICLE_REPO, the working copy)."""
    via = env.get("ORACLE_MERGE_VIA", "") or "forge"
    if via == "forge":
        return None
    if via != "radicle":
        raise ValueError(f"ORACLE_MERGE_VIA: 'forge' or 'radicle', not {via!r}")
    rid = env.get("ORACLE_RADICLE_RID", "")
    if not rid:
        raise ValueError("ORACLE_MERGE_VIA=radicle needs ORACLE_RADICLE_RID")
    return Radicle(rid, shlex.split(env.get("ORACLE_RADICLE_EXEC", "")), env.get("ORACLE_RADICLE_REPO", ""))
