"""The v3 node on Radicle (proof-of-fix#251, model (a); tasks 4.1 and 4.2), with no Radicle node: a stand-in `rad`
(tests/fake_rad.py) over a real bare git repository as the node's storage, and the v3 node against
tests/test_oracle_v3.py's fake chain.

- `rad sync <RID>`: the RID positional everywhere, and a failed sync reported, never hidden;
- `decide_head`: each decision path of a seated node's `main` (push, wait, refuse, done) with `Heads.head` moving at
  finality;
- the seat's adapter: the head pushed, then the identity one pending revision at a time;
- `Radicle`'s identity and patch reads, and its `rad id` writes, through the stand-in;
- fixes as patches (4.2): the revision that opens the commitment is fetched from the node's own storage and judged;
  a stale base is refused; a fix the node can't find, fetch or read is sealed as not available at the deadline; the
  protected tests (#251 L20) hold on a Radicle-fetched tree."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bot import logic  # noqa: E402
from oracle import crypto, fetch, v2, v3  # noqa: E402
from oracle import delegates as D  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.rpc import Reverted  # noqa: E402
from pofctl.v3cli import patch_messages  # noqa: E402
from test_fetch import git  # noqa: E402
from test_oracle_v3 import SEAL_WINDOW, Net  # noqa: E402

HAS_GIT = shutil.which("git") is not None
RID = "rad:z2ZdzxFSFzBavdeNbUKwEnfVcAq5R"
ME = "did:key:z6Mkr4Av6WRPU25LajzvoTtRFjdp7kPQLxCgpJodG1RCtzNX"
OTHER = "did:key:z6MkjEcGuYLSEiXrutj8VwUoqkPAUajWhcJnpjYiQe4Ks7sx"
THIRD = "did:key:z6MkegUjQPzWkbZTUS8DuQWrn52SoKK1WE17EXLwrq1WUnqK"
FIXED = "def median(xs):\n    s = sorted(xs)\n    return s[len(s) // 2]\n"
BROKEN = "def median(xs):\n    return 0\n"
GOOD_TEST = ("import unittest\nfrom stats import median\n\nclass T(unittest.TestCase):\n    def test(self):\n"
             "        self.assertEqual(median([3, 1, 2]), 2)\n")
WEAK_TEST = "import unittest\n\nclass T(unittest.TestCase):\n    def test(self):\n        pass\n"
SUITE = ["python", "-m", "unittest", "discover", "-s", "tests", "-t", "tests", "-q"]


class RadNode:
    """A stand-in Radicle node on this machine: $RAD_HOME with the storage (a bare git repository), `rad` on PATH
    (tests/fake_rad.py), and a working repository to make commits in."""

    def __init__(self, tmp: Path, me: str = ME) -> None:
        self.home = tmp / "radhome"
        self.storage = self.home / "storage" / RID[4:]
        self.storage.mkdir(parents=True)
        (self.home / "did").write_text(me)
        self.me = me
        git(tmp, "init", "-q", "--bare", str(self.storage))
        self.work = tmp / "work"
        self.work.mkdir()
        git(self.work, "init", "-q")
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        (bin_dir / "rad").write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_rad.py'} \"$@\"\n")
        (bin_dir / "rad").chmod(0o755)
        self.env = mock.patch.dict(os.environ, {"RAD_HOME": str(self.home),
                                                "PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}"})
        self.env.start()

    def stop(self) -> None:
        self.env.stop()

    def commit(self, files: dict, message: str, parent: str = "", delete=()) -> str:
        if parent:
            git(self.work, "checkout", "-q", "--detach", parent)
        for name in delete:
            git(self.work, "rm", "-q", name)
        for name, text in files.items():
            p = self.work / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def publish(self, sha: str, ref: str) -> None:
        git(self.work, "push", "-q", str(self.storage), f"{sha}:{ref}")

    def patch(self, pid: str, title: str, revisions: list) -> None:
        """A patch COB: `revisions` of (revision id, head commit, base commit, description body)."""
        d = self.home / "cobs" / D_PATCH
        d.mkdir(parents=True, exist_ok=True)
        cob = {"title": title, "state": {"status": "open"}, "author": {"id": OTHER},
               "revisions": {rid_: {"id": rid_, "description": [{"body": body, "embeds": []}], "base": base,
                                    "oid": oid, "timestamp": i} for i, (rid_, oid, base, body) in enumerate(revisions)},
               "timeline": [r[0] for r in revisions]}
        (d / f"{pid}.json").write_text(json.dumps(cob))

    def identity(self, doc: dict, pending=()) -> None:
        d = self.home / "cobs" / "xyz.radicle.id"
        d.mkdir(parents=True, exist_ok=True)
        revs = {"c" * 40: {"id": "c" * 40, "state": "accepted", "doc": doc, "timestamp": 0, "verdicts": {}}}
        for i, (rid_, pdoc, votes) in enumerate(pending, 1):
            revs[rid_] = {"id": rid_, "state": "active", "doc": pdoc, "timestamp": i, "verdicts": votes}
        cob = {"current": "c" * 40, "root": "c" * 40, "revisions": revs, "timeline": list(revs)}
        (d / ("e" * 40 + ".json")).write_text(json.dumps(cob))

    def calls(self) -> list:
        f = self.home / "id-calls.jsonl"
        return [json.loads(x)["argv"] for x in f.read_text().splitlines()] if f.exists() else []


D_PATCH = "xyz.radicle.patch"


def snap(tips: dict, delegates=(ME, OTHER, THIRD), threshold=2, me=ME, parents=None, missing=()) -> R.Snapshot:
    """A snapshot on a straight line of commits: "0" * 40 <- "1" * 40 <- "2" * 40 <- "3" * 40."""
    line = {str(i) * 40: ([str(i - 1) * 40] if i else []) for i in range(4)}
    s = R.Snapshot(me, list(delegates), threshold, {R.nid(d): c for d, c in tips.items()}, None,
                   parents if parents is not None else line, set(missing))
    s.canonical_ref = R.canonical(s)
    return s


C0, C1, C2, C3 = (str(i) * 40 for i in range(4))


class RadSync(unittest.TestCase):
    """`rad sync <RID>`: positional, and its errors no longer hidden (design L11, condition 4)."""

    FILES = ["oracle/radicle.py", "scripts/radicle-spike.sh", "tests/integration/radicle.py", "spikes/radicle/gate.sh",
             "spikes/radicle/v3_spike.py", "pofctl/v3cli.py", "oracle/radicle_v3.py",
             "tests/integration/suite_v3_radicle.py", "tests/integration/seed_radicle.py"]

    def test_no_caller_uses_the_rid_flag_or_hides_the_error(self):
        for name in self.FILES:
            text = (ROOT / name).read_text(encoding="utf-8")
            for line in text.splitlines():
                if "rad sync" not in line:
                    continue
                self.assertNotIn("--rid", line.replace("refuses `--rid`", "").replace("refuses --rid", ""),
                                 f"{name}: {line.strip()}")
                self.assertNotRegex(line, r"rad sync[^\n]*>/dev/null 2>&1", f"{name}: {line.strip()}")

    def test_the_lines_keep_the_error(self):
        lines = R.sync_lines(RID)
        self.assertIn(f"rad sync --fetch {RID} 2>&1", lines)
        self.assertNotIn("--rid", lines)
        self.assertIn("@syncerror", lines)
        self.assertIn(f"rad sync --announce {RID}", R.sync_lines(RID, "announce"))
        with self.assertRaises(ValueError):
            R.sync_lines("rad:bad0")
        with self.assertRaises(ValueError):
            R.sync_lines(RID, "--rid")
        self.assertEqual(R.sync_error("@me x\n@syncerror 1 ✗ Error: no candidate seeds\n"),
                         "rad sync failed (exit 1): ✗ Error: no candidate seeds")
        self.assertEqual(R.sync_error("@me x\n"), "")

    @unittest.skipUnless(HAS_GIT, "git isn't installed")
    def test_against_a_node_that_refuses_the_rid_flag(self):
        with tempfile.TemporaryDirectory() as t:
            node = RadNode(Path(t))
            try:
                genesis = node.commit({"stats.py": BROKEN}, "genesis")
                node.publish(genesis, "refs/heads/main")
                node.publish(genesis, f"refs/namespaces/{R.nid(ME)}/refs/heads/main")
                s = R.Radicle(RID).snapshot()
                self.assertEqual((s.canonical_ref, s.sync_error), (genesis, ""))  # the stand-in refuses `--rid`
                (node.home / "sync-fails").touch()
                s = R.Radicle(RID).snapshot()
                self.assertEqual(s.canonical_ref, genesis)  # the copy is still read ...
                self.assertIn("no candidate seeds", s.sync_error)  # ... and the failure is kept, not hidden
                cobs, err = R.Radicle(RID).patches()
                self.assertEqual(cobs, [])
                self.assertIn("exit 1", err)
            finally:
                node.stop()


class DecideHead(unittest.TestCase):
    """A seated node's `main` follows `Heads.head`, which moves only at finality (L9)."""

    def test_push_when_the_head_moved(self):
        d = R.decide_head(C2, snap({ME: C1, OTHER: C1, THIRD: C1}), seated=True)
        self.assertEqual(d.action, R.PUSH)
        self.assertIn("pushing this node's main from 111111111111", d.reason)

    def test_a_new_seat_publishes_its_first_main_at_the_head(self):
        d = R.decide_head(C1, snap({OTHER: C1, THIRD: C1}, delegates=(OTHER, THIRD)), seated=True)
        self.assertEqual(d.action, R.PUSH)
        self.assertIn("first main", d.reason)
        d = R.decide_head(C1, snap({ME: C1, OTHER: C1, THIRD: C1}, delegates=(OTHER, THIRD)), seated=True)
        self.assertEqual(d.action, R.DONE)
        self.assertIn("not a delegate yet", d.reason)

    def test_wait(self):
        d = R.decide_head(C2, snap({ME: C1}, missing=[C2]), seated=True)
        self.assertEqual(d.action, R.WAIT)
        self.assertIn("isn't on this Radicle node yet", d.reason)
        d = R.decide_head(C2, snap({ME: C2, OTHER: C1, THIRD: C1}), seated=True)  # voted; the others haven't
        self.assertEqual(d.action, R.WAIT)
        self.assertIn("1 of the 2 delegates needed", d.reason)
        d = R.decide_head(C2, snap({OTHER: C1}, delegates=(OTHER,)), seated=False)  # neither seat nor delegate
        self.assertEqual(d.action, R.WAIT)
        self.assertIn("watching only", d.reason)

    def test_done(self):
        d = R.decide_head(C2, snap({ME: C2, OTHER: C2, THIRD: C1}), seated=True)
        self.assertEqual(d.action, R.DONE)

    def test_refuse_what_doesnt_fast_forward(self):
        fork = {C0: [], C1: [C0], C2: [C1], C3: [C1]}  # this node's main is on a commit the head doesn't contain
        d = R.decide_head(C2, snap({ME: C3, OTHER: C1, THIRD: C1}, parents=fork), seated=True)
        self.assertEqual(d.action, R.REFUSE)
        self.assertIn("doesn't fast-forward", d.reason)

    def test_a_delegate_that_left_its_seat_still_follows_the_head_until_removed(self):
        d = R.decide_head(C2, snap({ME: C1, OTHER: C1, THIRD: C1}), seated=False)
        self.assertEqual(d.action, R.PUSH)


class FakeRadicle:
    """The adapter's view of a node, in memory: a snapshot, an identity COB, and what it pushed, proposed, signed."""

    rid = RID

    def __init__(self, s: R.Snapshot, cob: dict) -> None:
        self.s, self.cob = s, cob
        self.pushed, self.proposed, self.reviewed = [], [], []

    def snapshot(self, extra=(), sync=True):
        return self.s

    def push(self, sha):
        self.pushed.append(sha)
        self.s.tips[R.nid(self.s.me)] = sha
        return sha

    def identity(self, sync=True):
        return self.cob, self.s.me, ""

    def propose(self, args, title, description):
        self.proposed.append(tuple(args))
        rid_ = "9" * 40
        doc = json.loads(json.dumps(self.cob["revisions"][self.cob["current"]]["doc"]))
        added = {args[i + 1] for i, a in enumerate(args) if a == "--delegate"}
        doc["delegates"] = sorted(set(doc["delegates"]) | added)
        self.cob["revisions"][rid_] = {"id": rid_, "state": "active", "doc": doc, "verdicts": {R.nid(self.s.me): {
            "Accept": "s"}}}
        self.cob["timeline"].append(rid_)
        return "@syncerror 1 no seeds\n"

    def review(self, revision, accept):
        self.reviewed.append((revision, accept))
        return ""


class FakeSeats:
    """The chain as the adapter reads it."""

    registry = "0x" + "12" * 20

    def __init__(self, head: str, seats: list, rad_nodes: dict | None = None) -> None:
        self.head_, self.seats_, self.rad_nodes = head, seats, rad_nodes

    def rad_node_of(self, key):
        """Validators.radNodeOf; a registry from before #251's contract change has none (the call reverts)."""
        if self.rad_nodes is None:
            raise Reverted("execution reverted")
        return self.rad_nodes.get(key.lower(), b"\0" * 32)

    def head(self):
        return v2.commit_word(self.head_)

    def seats(self):
        return list(self.seats_)

    def chain_id(self):
        return 31337


class TheSeat(unittest.TestCase):
    """The adapter: `Heads.head` pushed first, then the identity one pending revision at a time."""

    def setUp(self):
        self.addrs = [crypto.address(k) for k in (11, 22, 33)]
        table = {a.lower(): D.key_from_did(d) for a, d in zip(self.addrs, (ME, OTHER, THIRD))}
        self.nodes = D.ChainSeatNodes(lambda v: table[v.lower()])
        self.logs = []

    def adapter(self, rad, chain, clock=None):
        return RV.SeatAdapter(rad, chain, self.addrs[0], self.nodes, log=self.logs.append, every=30,
                              clock=clock or (lambda: 0.0))

    def cob(self, delegates, threshold):
        return {"current": "c" * 40, "timeline": ["c" * 40], "revisions": {"c" * 40: {
            "id": "c" * 40, "state": "accepted", "verdicts": {}, "doc": {"payload": {}, "delegates": list(delegates),
                                                                         "threshold": threshold}}}}

    def test_pushes_the_head_then_proposes_the_new_seat_once(self):
        rad = FakeRadicle(snap({ME: C1, OTHER: C2, THIRD: C2}, delegates=(ME, OTHER)), self.cob((ME, OTHER), 2))
        chain = FakeSeats(C2, self.addrs)
        t = [0.0]
        a = self.adapter(rad, chain, clock=lambda: t[0])
        self.assertTrue(a.tick())
        self.assertEqual(rad.pushed, [C2])
        self.assertEqual(rad.proposed, [("--delegate", THIRD, "--threshold", "2")])
        self.assertTrue(any("rad sync failed (exit 1): no seeds" in m for m in self.logs), self.logs)  # not hidden
        self.assertFalse(a.tick())  # within `every`: no pass
        t[0] = 31.0
        self.assertFalse(a.tick())  # its revision is pending: nothing new is proposed
        self.assertEqual(len(rad.proposed), 1)
        self.assertEqual(a.last_identity.action, D.WAIT)

    def test_another_seat_reviews_the_pending_revision(self):
        rad = FakeRadicle(snap({ME: C2, OTHER: C2, THIRD: C2}, delegates=(ME, OTHER)), self.cob((ME, OTHER), 2))
        pending = {"id": "8" * 40, "state": "active", "verdicts": {R.nid(OTHER): {"Accept": "s"}},
                   "doc": {"payload": {}, "delegates": [ME, OTHER, THIRD], "threshold": 2}}
        rad.cob["revisions"]["8" * 40] = pending
        rad.cob["timeline"].append("8" * 40)
        self.assertTrue(self.adapter(rad, FakeSeats(C2, self.addrs)).tick())
        self.assertEqual((rad.pushed, rad.reviewed, rad.proposed), ([], [("8" * 40, True)], []))

    def test_a_rogue_revision_is_rejected(self):
        rad = FakeRadicle(snap({ME: C2, OTHER: C2, THIRD: C2}, delegates=(ME, OTHER)), self.cob((ME, OTHER), 2))
        rogue = "did:key:z6MkopH5QMoynapxG9Yis4TCpWgyaxQNEBeiL39wqJ2GZCR1"  # nobody's seat
        rad.cob["revisions"]["8" * 40] = {"id": "8" * 40, "state": "active", "verdicts": {},
                                          "doc": {"payload": {}, "delegates": [ME, OTHER, rogue], "threshold": 2}}
        rad.cob["timeline"].append("8" * 40)
        self.adapter(rad, FakeSeats(C2, self.addrs[:2])).tick()
        self.assertEqual(rad.reviewed, [("8" * 40, False)])

    def test_the_chain_mapping_is_the_default_when_the_registry_has_it(self):
        table = {a.lower(): D.key_from_did(d) for a, d in zip(self.addrs, (ME, OTHER, THIRD))}
        chain = FakeSeats(C2, self.addrs[:2], rad_nodes=table)
        nodes = RV.seat_nodes({}, chain, RID)
        self.assertIsInstance(nodes, D.ChainSeatNodes)
        self.assertEqual(nodes.node_of(self.addrs[1]), OTHER)
        self.assertIsInstance(RV.seat_nodes({"ORACLE_SEAT_NODES": "chain"}, chain, RID), D.ChainSeatNodes)
        self.assertIsInstance(RV.seat_nodes({"ORACLE_SEAT_NODES": "bindings"}, chain, RID), D.DocumentBindings)
        with self.assertRaises(ValueError):
            RV.seat_nodes({"ORACLE_SEAT_NODES": "document"}, chain, RID)

    def test_an_older_registry_falls_back_to_bindings(self):
        old = FakeSeats(C2, self.addrs[:2])  # no radNodeOf: the call reverts
        self.assertFalse(RV.has_rad_nodes(old))
        self.assertIsInstance(RV.seat_nodes({}, old, RID), D.DocumentBindings)
        with self.assertRaises(ValueError) as e:
            RV.seat_nodes({"ORACLE_SEAT_NODES": "chain"}, old, RID)
        self.assertIn("no radNodeOf", str(e.exception))

    def test_a_seat_registered_without_a_node_is_left_out(self):
        table = {self.addrs[0].lower(): D.key_from_did(ME), self.addrs[1].lower(): D.key_from_did(OTHER),
                 self.addrs[2].lower(): b"\0" * 32}
        rad = FakeRadicle(snap({ME: C2, OTHER: C2, THIRD: C2}, delegates=(ME, OTHER)), self.cob((ME, OTHER), 2))
        chain = FakeSeats(C2, self.addrs, rad_nodes=table)
        a = RV.SeatAdapter(rad, chain, self.addrs[0], RV.seat_nodes({}, chain, RID), log=self.logs.append)
        a.tick(force=True)
        self.assertEqual(rad.proposed, [])  # nothing to add: the third seat has no node
        self.assertEqual(a.last_identity.action, D.WAIT)
        self.assertIn("unmapped", a.last_identity.reason)

    def test_with_bindings_it_signs_its_own(self):
        signer = lambda d: crypto.sign(11, d)  # noqa: E731 (the validator key of addrs[0])
        nodes = D.DocumentBindings(31337, FakeSeats.registry, RID)
        rad = FakeRadicle(snap({ME: C2}, delegates=(ME,), threshold=1), self.cob((ME,), 1))
        a = RV.SeatAdapter(rad, FakeSeats(C2, self.addrs[:1]), self.addrs[0], nodes, sign=signer,
                           log=self.logs.append)
        a.tick()
        self.assertEqual(nodes.node_of(self.addrs[0]), ME)
        self.assertEqual(rad.proposed[0][:4], ("--threshold", "1", "--payload", D.PAYLOAD))  # carries its binding


@unittest.skipUnless(HAS_GIT, "git isn't installed")
class RadicleCalls(unittest.TestCase):
    """`Radicle`'s identity and patch reads and its `rad id` writes, through the stand-in CLI."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.node = RadNode(Path(self._tmp.name))
        self.addCleanup(self.node.stop)

    def test_identity_propose_review(self):
        self.node.identity({"payload": {}, "delegates": [ME, OTHER], "threshold": 2})
        r = R.Radicle(RID)
        cob, me, err = r.identity()
        self.assertEqual((cob["current"], me, err), ("c" * 40, ME, ""))
        out = r.propose(["--delegate", THIRD, "--threshold", "2"], RV.TITLE, "the seats")
        self.assertIn("created", out)
        cob, _, _ = r.identity()
        (pending,) = D.pending_revisions(cob)
        self.assertEqual(pending["doc"]["delegates"], [ME, OTHER, THIRD])
        self.assertEqual(self.node.calls()[0][:4], ["id", "update", "--repo", RID])
        (self.node.home / "did").write_text(OTHER)
        r.review(pending["id"], True)
        cob, _, _ = r.identity()
        self.assertEqual(cob["current"], pending["id"])  # 2 of 2
        with self.assertRaises(R.Unavailable):
            r.review("7" * 40, True)  # no such revision: the error comes back

    def test_patches(self):
        self.node.patch("ab" * 20, "Fix", [("ab" * 20, "11" * 20, "22" * 20, "Bounty: 1\n\nSubmission: 2")])
        cobs, err = R.Radicle(RID).patches()
        self.assertEqual(err, "")
        (p,) = D.patch_pulls(cobs)
        self.assertEqual((p["patch"], p["head_sha"], p["base_sha"]), ("ab" * 20, "11" * 20, "22" * 20))

    def test_storage_and_an_unreachable_node(self):
        self.assertEqual(R.Radicle(RID).storage(), str(self.node.storage))
        with self.assertRaises(R.Unavailable):
            R.Radicle(RID, ["false"]).patches()


class Seeing:
    """A sandbox stand-in recording each run's mounted tree and files."""

    def __init__(self, code=0):
        self.code, self.seen = code, []

    def __call__(self, argv):
        mount = Path(next(a for a in argv if a.endswith(":/src:ro"))[:-len(":/src:ro")])
        files = {str(p.relative_to(mount)): p.read_text() for p in mount.rglob("*")
                 if p.is_file() and ".git" not in p.relative_to(mount).parts}
        self.seen.append({"tree": mount, "files": files})
        code = self.code(files) if callable(self.code) else self.code
        return code, "ok", ""


@unittest.skipUnless(HAS_GIT, "git isn't installed")
class FixesAsPatches(unittest.TestCase):
    """Task 4.2 in the v3 node: the fix source lists the patches on the node's own Radicle node."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.node = RadNode(self.tmp)
        self.addCleanup(self.node.stop)
        self.base = self.node.commit({"stats.py": BROKEN, "tests/test_stats.py": GOOD_TEST}, "genesis")
        self.node.publish(self.base, "refs/heads/main")
        self.node.publish(self.base, f"refs/namespaces/{R.nid(ME)}/refs/heads/main")
        self.net = Net(self.tmp / "net", n=2)
        self.chain = self.net.chain
        self.chain.head = lambda: v2.commit_word(self.base)
        self.solver, self.salt = crypto.checksum("0x" + "99" * 20), b"\x05" * 32
        self.addCleanup(self._clean)

    def _clean(self):
        root = self.tmp / "net" / "src"
        for p in root.glob("*") if root.exists() else []:
            fetch.remove(p)

    def fix(self, files: dict, base: str = "", delete=()) -> str:
        sha = self.node.commit(files, "fix", parent=base or self.base, delete=delete)
        self.node.publish(sha, f"refs/namespaces/{R.nid(OTHER)}/refs/heads/patches/{'ab' * 20}")
        return sha

    def seal(self, sha: str, base: str = "") -> None:
        base = base or self.base
        self.chain.subs[1]["commitment"] = "0x" + v3.fix_commitment(v2.commit_word(sha), v2.commit_word(base),
                                                                    self.salt, self.solver).hex()

    def claim(self, salt: bytes = b"") -> str:
        """The description `pofctl submit` makes Radicle write: its patch messages after the title, one paragraph
        each."""
        body = logic.pr_body(1, 1, 1, "0x" + (salt or self.salt).hex(), self.solver)
        return "\n\n".join(patch_messages("Fix for bounty 1", body)[1:])

    def open_patch(self, *revisions) -> None:
        """Revisions of (head, base, salt)."""
        self.node.patch("ab" * 20, "Fix for bounty 1", [(str(i) * 40, oid, base or self.base, self.claim(salt))
                                                        for i, (oid, base, salt) in enumerate(revisions, 1)])

    def validator(self, runner=None, prefix=()):
        n = self.net.nodes[0]
        r = R.Radicle(RID, list(prefix))
        n.fixes = RV.RadicleFixes(r)
        n.fetcher = RV.RadicleFetcher(r, log=self.net.logs.append, retry_s=0)
        n.runner = runner or Seeing(0)
        return n

    def counted(self) -> int:
        return self.chain.add_panel(1, v3.COUNTED, self.net.addresses(0))

    def receipt(self, n, pid) -> dict:
        return n.receipts3.get(self.chain.seat(pid, 0)["receipt"])

    def test_the_revision_that_opens_the_commitment_is_fetched_from_the_node_and_judged(self):
        sha = self.fix({"stats.py": FIXED})
        self.seal(sha)
        self.open_patch((sha, "", b"\x06" * 32), (sha, "", b""))  # the first revision's salt doesn't open it
        n, pid = self.validator(), self.counted()
        self.net.tick([n], 2)
        self.assertTrue(self.chain.seat(pid, 0)["hasSeal"])
        self.chain.warp(SEAL_WINDOW + 1)
        self.net.tick([n], 3)
        self.assertEqual((self.chain.seat(pid, 0)["revealed"], self.chain.seat(pid, 0)["vote"]), (True, True))
        seen = n.runner.seen
        self.assertEqual(len(seen), 2)  # two runs (L22) ...
        self.assertEqual(seen[0]["tree"], self.tmp / "net" / "src" / sha)  # ... on the commit fetched from Radicle
        self.assertEqual(seen[0]["files"]["stats.py"], FIXED)
        self.assertEqual(git(seen[0]["tree"], "rev-parse", "HEAD"), sha)
        self.assertTrue(any("revision 1111111 doesn't open its seal" in m for m in self.net.logs), self.net.logs)

    def test_a_stale_base_is_refused_without_running_the_tests(self):
        older = self.base
        self.base = self.node.commit({"other.py": "x = 1\n"}, "a fix merged since", parent=older)  # Heads.head moved
        sha = self.fix({"stats.py": FIXED}, base=older)
        self.seal(sha, base=older)
        self.open_patch((sha, older, b""))
        n, pid = self.validator(), self.counted()
        self.net.tick([n], 2)
        self.assertTrue(self.chain.seat(pid, 0)["hasSeal"])  # refused at once: it can't become right
        self.assertEqual(n.runner.seen, [])
        self.chain.warp(SEAL_WINDOW + 1)
        self.net.tick([n], 3)
        self.assertEqual((self.chain.seat(pid, 0)["revealed"], self.chain.seat(pid, 0)["vote"]), (True, False))
        self.assertIn("not on Heads.head", self.receipt(n, pid)["refused"])

    def _sealed_not_available(self, n, pid) -> str:
        self.net.tick([n], 2)
        self.assertFalse(self.chain.seat(pid, 0)["hasSeal"])  # not yet: the fix may still come
        self.chain.warp(SEAL_WINDOW - 300)  # inside the seal margin: no silence
        self.net.tick([n], 2)
        seat = self.chain.seat(pid, 0)
        self.assertTrue(seat["hasSeal"])
        self.chain.warp(301)
        self.net.tick([n], 3)
        self.assertEqual((self.chain.seat(pid, 0)["revealed"], self.chain.seat(pid, 0)["vote"]), (True, False))
        text = self.receipt(n, pid)["refused"]  # the receipt says why
        self.assertTrue(text.startswith("the fix wasn't available"), text)
        return text

    def test_no_patch_opens_it_sealed_as_not_available(self):
        sha = self.fix({"stats.py": FIXED})
        self.seal(sha)
        n, pid = self.validator(), self.counted()
        self.assertIn("no patch revision on this node's Radicle copy opens the sealed commitment",
                      self._sealed_not_available(n, pid))

    def test_a_commit_it_cant_fetch_sealed_as_not_available(self):
        missing = "7" * 40  # a revision whose commit never reached this node
        self.seal(missing)
        self.open_patch((missing, "", b""))
        n, pid = self.validator(), self.counted()
        self.assertIn("couldn't be fetched from this node's Radicle copy", self._sealed_not_available(n, pid))
        self.assertEqual(n.runner.seen, [])

    def test_a_radicle_node_it_cant_read_sealed_as_not_available(self):
        sha = self.fix({"stats.py": FIXED})
        self.seal(sha)
        self.open_patch((sha, "", b""))
        n, pid = self.validator(prefix=["false"]), self.counted()
        self.assertIn("couldn't be read", self._sealed_not_available(n, pid))

    def test_a_failed_sync_is_logged_and_the_copy_still_judged(self):
        (self.node.home / "sync-fails").touch()
        sha = self.fix({"stats.py": FIXED})
        self.seal(sha)
        self.open_patch((sha, "", b""))
        n, pid = self.validator(), self.counted()
        self.net.tick([n], 2)
        self.assertTrue(self.chain.seat(pid, 0)["hasSeal"])
        self.assertTrue(any("rad sync failed (exit 1)" in m for m in self.net.logs), self.net.logs)

    def test_the_protected_tests_hold_on_a_tree_fetched_from_radicle(self):
        protecting = json.dumps({"commands": [SUITE], "protected": ["tests/"]})
        self.base = self.node.commit({".pof/check.json": protecting}, "protect tests/", parent=self.base)
        self.node.publish(self.base, "refs/heads/main")
        sha = self.fix({"stats.py": BROKEN + "# still wrong\n", "tests/test_stats.py": WEAK_TEST})
        self.seal(sha)
        self.open_patch((sha, "", b""))
        runner = Seeing(lambda files: 0 if files.get("tests/test_stats.py") == WEAK_TEST else 1)
        n, pid = self.validator(runner), self.counted()
        self.net.tick([n], 2)
        self.chain.warp(SEAL_WINDOW + 1)
        self.net.tick([n], 3)
        self.assertEqual(self.chain.seat(pid, 0)["vote"], False)  # the weakened test didn't run
        self.assertTrue(runner.seen)
        self.assertTrue(all(s["files"]["tests/test_stats.py"] == GOOD_TEST for s in runner.seen))
        self.assertNotEqual(runner.seen[0]["tree"], self.tmp / "net" / "src" / sha)  # a run tree, not the checkout
        tests = self.receipt(n, pid)["receipt"]["tests"]
        self.assertEqual(tests["protected"], ["tests"])
        self.assertEqual(tests["not_run"], 1)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{40}", tests["run_tree"]))

    def test_through_a_command_prefix_the_fetch_uses_upload_pack(self):
        sha = self.fix({"stats.py": FIXED})
        self.seal(sha)
        self.open_patch((sha, "", b""))
        n = self.validator(prefix=["env"])  # `env bash -c ...`, `env git-upload-pack <storage>`: this machine
        self.assertEqual(n.fetcher.upload_pack, "env git-upload-pack")
        pid = self.counted()
        self.net.tick([n], 2)
        self.assertTrue(self.chain.seat(pid, 0)["hasSeal"])
        self.assertEqual(n.runner.seen[0]["files"]["stats.py"], FIXED)


class Configuration(unittest.TestCase):
    def test_from_env(self):
        class Chain(FakeSeats):
            def repo(self):
                return R.repo_id(RID)

        chain = Chain(C1, [])
        self.assertEqual(RV.from_env({}, chain, "0x" + "11" * 20), (None, None, None))
        fixes, fetcher, seat = RV.from_env({"ORACLE_FIX_SOURCE": "radicle", "ORACLE_RADICLE_RID": RID,
                                            "ORACLE_RADICLE_EXEC": "docker exec -i n1"}, chain, "0x" + "11" * 20)
        self.assertIsInstance(fixes, RV.RadicleFixes)
        self.assertEqual(fetcher.upload_pack, "docker exec -i n1 git-upload-pack")
        self.assertIsNone(seat)
        _, _, seat = RV.from_env({"ORACLE_MERGE_VIA": "radicle", "ORACLE_RADICLE_RID": RID}, chain, "0x" + "11" * 20)
        self.assertIsInstance(seat.nodes, D.DocumentBindings)
        with self.assertRaises(ValueError):
            RV.from_env({"ORACLE_FIX_SOURCE": "radicle"}, chain, "0x" + "11" * 20)  # no RID
        with self.assertRaises(ValueError) as e:
            RV.from_env({"ORACLE_FIX_SOURCE": "radicle", "ORACLE_RADICLE_RID": "rad:z3Tr6bC7ctEg2EHmLvknUr29mEDLH"},
                        chain, "0x" + "11" * 20)
        self.assertIn("isn't the race's repository", str(e.exception))

    def test_a_superseded_deployment_runs_no_seat(self):
        """#310 RB12: a node runs the seat's part (pushing main, voting on the identity) for one deployment only, the
        newest. Its record marked `supersededBy` turns the seat's part off, with a line saying why; the fix source and
        the keeper stay."""
        import json
        import tempfile

        class Chain(FakeSeats):
            race = "0x" + "a1" * 20

            def repo(self):
                return R.repo_id(RID)

        chain = Chain(C1, [])
        with tempfile.TemporaryDirectory() as d:
            old, new, other = (Path(d) / n for n in ("v3.json", "v3.1.json", "other.json"))
            old.write_text(json.dumps({"version": 3, "addresses": {"race": chain.race},
                                       "supersededBy": "sepolia-v3.1.json"}))
            new.write_text(json.dumps({"version": 3, "addresses": {"race": chain.race}}))
            other.write_text(json.dumps({"version": 3, "race": "0x" + "b2" * 20}))
            env = {"ORACLE_MERGE_VIA": "radicle", "ORACLE_FIX_SOURCE": "radicle", "ORACLE_RADICLE_RID": RID}
            logs = []
            fixes, _, seat = RV.from_env({**env, "ORACLE_DEPLOYMENT_RECORD": str(old)}, chain, "0x" + "11" * 20,
                                         log=logs.append)
            self.assertIsNone(seat)
            self.assertIsInstance(fixes, RV.RadicleFixes)  # the checks are still judged
            self.assertIn("superseded by sepolia-v3.1.json", logs[0])
            self.assertIn("the keeper still runs", logs[0])
            _, _, seat = RV.from_env({**env, "ORACLE_DEPLOYMENT_RECORD": str(new)}, chain, "0x" + "11" * 20)
            self.assertIsInstance(seat, RV.SeatAdapter)  # the newest deployment's node runs it
            with self.assertRaises(ValueError) as e:
                RV.from_env({**env, "ORACLE_DEPLOYMENT_RECORD": str(other)}, chain, "0x" + "11" * 20)
            self.assertIn("is the record of race", str(e.exception))


if __name__ == "__main__":
    unittest.main()


class VerdictCommentsUnread(unittest.TestCase):
    """v3.1 polish VP18: a node's verdict receipt on the issue isn't part of what a later judge reads (an audit or a
    challenge would otherwise be shown the counted verdict), so the issue's hash in a receipt doesn't change either."""

    def test_the_verdict_comments_are_left_out_of_the_issue_text(self):
        from oracle import radicle_v3 as RV3
        from oracle import verdict_comment as VC
        issue = {"title": "median() of an empty list", "state": "open", "comments": [
            {"author": "did:key:a", "body": "It raises."},
            {"author": "did:key:b", "body": "Registration: 1"}]}
        before = RV3.issue_text(issue)
        issue["comments"] += [
            {"author": "did:key:c", "body": "proof-of-fix verdict: registration check 2 passed.\n\n"
                                            + VC.marker_line(31337, "0xAbC", 2)},
            {"author": "did:key:c", "body": "the reason …\n\n" + VC.marker_line(31337, "0xAbC", 2, VC.REASON_MARKER)}]
        self.assertEqual(RV3.issue_text(issue), before)
        issue["comments"].append({"author": "did:key:d",
                                  "body": "pof-verdict: is mentioned, but not as the last line\nok"})
        self.assertIn("Comment 4", RV3.issue_text(issue))
