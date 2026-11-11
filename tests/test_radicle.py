"""The node's Radicle adapter (proof-of-fix#201, oracle/radicle.py): the canonical main by the delegate threshold, the
refusal of a mismatch with Heads, outsiders' branches ignored, and three drawn nodes merging on a fake Radicle against
a fake chain (no forge `merged`). No Docker, no Radicle and no chain: the end-to-end run is scripts/integration.sh
--radicle (scenario 8)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from oracle import crypto, radicle as rad, v2
from oracle.radicle import PUSH, REFUSE, SIGN, WAIT, Snapshot, canonical, decide, verify_head
import test_oracle_v2 as base
from test_oracle_v2 import FakeChain, FakeWallet

G, F, R, X, Y = ("10" * 20), ("f0" * 20), ("e0" * 20), ("a0" * 20), ("b0" * 20)
D1, D2, D3, OUT = "z6MkD1", "z6MkD2", "z6MkD3", "z6MkOutsider"
DELEGATES = [f"did:key:{d}" for d in (D1, D2, D3)]
PARENTS = {G: [], F: [G], R: [F], X: [G], Y: [G]}


def snap(tips: dict, me: str = D1, threshold: int = 2, ref: str | None = "auto", missing=()) -> Snapshot:
    s = Snapshot(f"did:key:{me}", DELEGATES, threshold, dict(tips), None, dict(PARENTS), set(missing))
    s.canonical_ref = canonical(s) if ref == "auto" else ref
    return s


class Canonical(unittest.TestCase):
    def test_the_threshold_of_delegates_moves_main(self):
        self.assertEqual(canonical(snap({D1: G, D2: G, D3: G})), G)
        self.assertEqual(canonical(snap({D1: F, D2: G, D3: G})), G)  # one delegate alone: main stays
        self.assertEqual(canonical(snap({D1: F, D2: F, D3: G})), F)  # two of three: main is the fix

    def test_a_branch_votes_for_its_ancestors(self):
        # #190's scenario C: one delegate ahead on a rogue child, one on the fix, one diverging: the fix has 2 votes
        self.assertEqual(canonical(snap({D1: R, D2: F, D3: X})), F)

    def test_outsiders_dont_count(self):
        self.assertEqual(canonical(snap({D1: F, D2: G, D3: G, OUT: F})), G)
        self.assertEqual(canonical(snap({D1: G, D2: G, D3: G, OUT: R, "z6MkOther": R})), G)

    def test_diverging_commits_with_the_votes_give_no_canonical_main(self):
        self.assertIsNone(canonical(snap({D1: X, D2: Y}, threshold=1)))
        self.assertIsNone(canonical(snap({D1: F}, threshold=2)))  # no commit has two votes


class Decide(unittest.TestCase):
    def test_vote_then_wait_then_sign(self):
        self.assertEqual(decide(F, G, G, snap({D1: G, D2: G, D3: G}), 2).action, PUSH)
        self.assertEqual(decide(F, G, G, snap({D1: F, D2: G, D3: G}), 2).action, WAIT)  # voted, below the threshold
        d = decide(F, G, G, snap({D1: F, D2: F, D3: G}), 2)
        self.assertEqual(d.action, SIGN)
        self.assertIn("2 delegates of 3", d.reason)

    def test_a_mismatch_with_heads_is_refused(self):
        d = decide(F, G, G, snap({D1: G, D2: R, D3: R}), 2)  # two delegates skipped the check: main is R
        self.assertEqual(d.action, REFUSE)
        self.assertIn("Radicle and the chain disagree", d.reason)
        self.assertEqual(verify_head(G, snap({D1: G, D2: R, D3: R})).action, REFUSE)
        self.assertEqual(verify_head(G, snap({D1: G, D2: G, D3: F})).action, SIGN)

    def test_outsider_pushes_dont_merge(self):
        # the outsider's vote for the fix doesn't make two: this delegate still votes, nobody signs
        self.assertEqual(decide(F, G, G, snap({D1: G, D2: G, D3: G, OUT: F}), 2).action, PUSH)
        self.assertEqual(decide(F, G, G, snap({D1: F, D2: G, D3: G, OUT: F}), 2).action, WAIT)

    def test_refusals(self):
        self.assertEqual(decide(F, G, G, snap({D1: G, D2: G, D3: G}, threshold=1), 2).action, REFUSE)  # not the quorum
        self.assertEqual(decide(F, G, F, snap({D1: F, D2: F, D3: F}), 2).action, REFUSE)  # stale: base isn't the head
        self.assertEqual(decide(F, G, G, snap({D1: X, D2: G, D3: G}), 2).action, REFUSE)  # not a fast-forward of mine

    def test_waits(self):
        self.assertEqual(decide(F, G, G, snap({D1: G, D2: G, D3: G}, missing=[F]), 2).action, WAIT)  # fix not here
        self.assertEqual(decide(F, G, G, snap({D1: G, D2: G, D3: G}, me=OUT), 2).action, WAIT)  # not a delegate
        self.assertEqual(decide(F, G, G, snap({D1: F, D2: F, D3: G}, ref=G), 2).action, WAIT)  # its ref lags


class Plumbing(unittest.TestCase):
    def test_parse_a_snapshot(self):
        out = "\n".join([
            "@me did:key:z6MkD1", "@identity", '{"payload": {}, "delegates": ["did:key:z6MkD1", "did:key:z6MkD2"],',
            '"threshold": 2}', f"@canonical {G}", "@refs", f"refs/namespaces/z6MkD1/refs/heads/main {F}",
            f"refs/namespaces/z6MkD2/refs/heads/main {G}", f"@missing {X}", "@graph", f"{F} {G}", G, "@end"])
        s = rad.parse_snapshot(out)
        self.assertEqual((s.me, s.threshold, s.canonical_ref, s.missing), ("did:key:z6MkD1", 2, G, {X}))
        self.assertEqual(s.tips, {"z6MkD1": F, "z6MkD2": G})
        self.assertEqual(s.parents, {F: [G], G: []})
        self.assertEqual(canonical(s), G)
        with self.assertRaises(rad.Unavailable):
            rad.parse_snapshot("@me x\n@identity\nnot json\n@end")

    def test_from_env_keeps_the_forge_by_default(self):
        self.assertIsNone(rad.from_env({}))
        self.assertIsNone(rad.from_env({"ORACLE_MERGE_VIA": "forge"}))
        r = rad.from_env({"ORACLE_MERGE_VIA": "radicle", "ORACLE_RADICLE_RID": "rad:z3WzFRXnicvfwUnXeuUqZ5Cwf1J5g",
                          "ORACLE_RADICLE_EXEC": "docker exec -i node-1"})
        self.assertEqual((r.prefix, r.repo_id), (["docker", "exec", "-i", "node-1"],
                                                 crypto.keccak256(b"rad:z3WzFRXnicvfwUnXeuUqZ5Cwf1J5g")))
        for bad in ({"ORACLE_MERGE_VIA": "radicle"}, {"ORACLE_MERGE_VIA": "github"},
                    {"ORACLE_MERGE_VIA": "radicle", "ORACLE_RADICLE_RID": "rad:z1; rm -rf /"}):
            with self.assertRaises(ValueError):
                rad.from_env(bad)

    def test_commits_as_heads_keeps_them(self):
        self.assertEqual(rad.sha_of(v2.commit_word(F)), F)
        self.assertEqual(rad.sha_of(b"\x11" * 32), "11" * 32)


# ---------- three drawn nodes merging on a fake Radicle ----------

RID = "rad:z3WzFRXnicvfwUnXeuUqZ5Cwf1J5g"


class FakeRadicleNet:
    """Every node's Radicle copy at once (perfect sync): the delegates' signed mains and the commit graph."""

    def __init__(self, delegates: list) -> None:
        self.delegates = [f"did:key:{d}" for d in delegates]
        self.tips = {d: G for d in delegates}

    def node(self, me: str):
        net = self

        class Node:
            rid, repo_id = RID, rad.repo_id(RID)

            def snapshot(self, extra=(), sync=True):
                s = Snapshot(f"did:key:{me}", net.delegates, 2, dict(net.tips), None, dict(PARENTS))
                s.canonical_ref = canonical(s)
                return s

            def push(self, fix):
                net.tips[me] = fix
                return fix
        return Node()


class RadicleChain(FakeChain):
    """The fake chain after the result: submission 1 passed and won bounty 1, in the Radicle repository's registry."""

    def __init__(self, *a):
        super().__init__(*a)
        self.sub.update({"outcome": v2.PASS, "fix": "0x" + v2.commit_word(F).hex(),
                         "base": "0x" + v2.commit_word(G).hex(), "receipt": "0x" + "33" * 32})
        self.state, self.head_ = 2, G  # Won
        self.merges: list = []

    def bounty(self, b):
        return {"issue": 0, "state": self.state, "winner": 1}

    def issue(self, i):
        return {"repo": "0x" + rad.repo_id(RID).hex(), "reporter": "0x" + "00" * 20}

    def head(self, repo):
        assert v2.b32(repo) == rad.repo_id(RID)
        return {"commit": v2.commit_word(self.head_)}


class RadicleWallet(FakeWallet):
    def send(self, to, signature, *args):
        if not signature.startswith("merged("):
            return super().send(to, signature, *args)
        verdict, weight, sigs = args
        v = v2.Verdict(*verdict[:5], verdict[6], verdict[7], verdict[8], verdict[9], verdict[5])
        signers = [crypto.recover(v2.merged_digest(self.chain.race_domain(), v, weight), s) for s in sigs]
        assert all(s in self.chain.judges for s in signers) and len(signers) >= 2
        assert v.base == v2.commit_word(self.chain.head_)  # Heads.move: base == head, or it reverts
        self.chain.head_, self.chain.state = rad.sha_of(v.fix), 3  # Merged
        self.chain.merges.append((self.me, v, signers))
        return {"logs": []}


class NodesOnRadicle(unittest.TestCase):
    _run = base.ThreeNodes._run

    def _radicle_nodes(self, tmp: Path, extra_delegates=()):
        chain, nodes = base.ThreeNodes._nodes(self, tmp)
        rchain = RadicleChain(chain.judges, v2.b32(chain.sub["commitment"]), chain.sub["solver"])
        nids = {n.address: f"z6Mk{n.address[2:12]}" for n in nodes}
        net = FakeRadicleNet([nids[n.address] for n in nodes] + list(extra_delegates))
        for n in nodes:
            n.chain, n.wallet = rchain, RadicleWallet(rchain, n.address)
            n.radicle = net.node(nids[n.address])
        return rchain, nodes[:3], net, nids

    def test_the_drawn_judges_push_and_sign_once_main_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, drawn, net, nids = self._radicle_nodes(Path(tmp))
            self._run(drawn)
            self.assertEqual(len(chain.merges), 1)
            _, v, signers = chain.merges[0]
            self.assertEqual((v.fix, v.base, chain.head_), (v2.commit_word(F), v2.commit_word(G), F))
            self.assertEqual(sorted(signers), sorted(chain.judges))
            self.assertGreaterEqual(sum(net.tips[nids[n.address]] == F for n in drawn), 2)

    def test_a_mismatch_is_neither_voted_nor_signed(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, drawn, net, nids = self._radicle_nodes(Path(tmp), extra_delegates=("z6MkRogue1", "z6MkRogue2"))
            net.tips.update({"z6MkRogue1": X, "z6MkRogue2": X})  # two delegates skipped the check
            self._run(drawn)
            self.assertEqual((chain.merges, chain.head_), ([], G))
            self.assertTrue(all(net.tips[nids[n.address]] == G for n in drawn))  # nobody voted

    def test_one_delegate_and_an_outsider_dont_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, drawn, net, nids = self._radicle_nodes(Path(tmp))
            net.tips["z6MkOutsider"] = F
            self._run(drawn[:1])  # the two others are offline
            self.assertEqual(net.tips[nids[drawn[0].address]], F)
            self.assertEqual((chain.merges, chain.head_, chain.state), ([], G, 2))


if __name__ == "__main__":
    unittest.main()
