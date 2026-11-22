"""Delegates follow the seats (proof-of-fix#251 task 4.1, model (a)): oracle/delegates.py's rules against the
seat-to-node mapping interface, with both of its implementations (the spike's signed bindings in the identity
document, used for now; the chain reader, a stub until v3 records a Radicle node ID), and one pending identity revision
at a time. Pure functions: no Radicle, no chain."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from oracle import crypto  # noqa: E402
from oracle import delegates as D  # noqa: E402

CHAIN, REGISTRY, RID = 31337, "0x" + "12" * 20, "rad:z2ZdzxFSFzBavdeNbUKwEnfVcAq5R"
DIDS = ["did:key:z6Mkr4Av6WRPU25LajzvoTtRFjdp7kPQLxCgpJodG1RCtzNX",
        "did:key:z6MkjEcGuYLSEiXrutj8VwUoqkPAUajWhcJnpjYiQe4Ks7sx",
        "did:key:z6MkegUjQPzWkbZTUS8DuQWrn52SoKK1WE17EXLwrq1WUnqK",
        "did:key:z6MkopH5QMoynapxG9Yis4TCpWgyaxQNEBeiL39wqJ2GZCR1"]
SECRETS = [11, 22, 33, 44]
ADDRS = [crypto.address(k) for k in SECRETS]
PROJECT = {"defaultBranch": "main", "description": "t", "name": "t"}
HEAD = "a" * 40
PUBLISHED = {D.nid(d): HEAD for d in DIDS}


class Mapping(D.SeatNodes):
    """A plain mapping (validator -> DID), standing in for any implementation of the interface."""

    def __init__(self, table: dict) -> None:
        self.table = {k.lower(): v for k, v in table.items()}

    def node_of(self, validator):
        return self.table.get(validator.lower())


def binding(i: int, did: str | None = None) -> dict:
    return D.make_binding(lambda d: crypto.sign(SECRETS[i], d), ADDRS[i], CHAIN, REGISTRY, RID, did or DIDS[i])


def doc(idx, threshold=None, bindings=True) -> dict:
    ds = [DIDS[i] for i in idx]
    payload = {D.PROJECT: dict(PROJECT)}
    if bindings:
        payload[D.PAYLOAD] = {"bindings": {DIDS[i]: binding(i) for i in idx}}
    return {"payload": payload, "delegates": ds, "threshold": D.majority(len(ds)) if threshold is None else threshold}


def plain(idx, threshold=None) -> dict:
    return doc(idx, threshold, bindings=False)


def cob(current: dict, *pending, votes=None) -> dict:
    """An identity COB: revision "c" current (accepted), then the pending ones ("p1", "p2", ...) in order."""
    revs = {"c" * 40: {"id": "c" * 40, "state": "accepted", "doc": current, "timestamp": 1, "verdicts": {}}}
    timeline = ["c" * 40]
    for i, d in enumerate(pending, 1):
        rid_ = str(i) * 40
        revs[rid_] = {"id": rid_, "state": "active", "doc": d, "timestamp": 1 + i,
                      "verdicts": dict((votes or {}).get(i, {}))}
        timeline.append(rid_)
    return {"current": "c" * 40, "revisions": revs, "timeline": timeline}


class TheKey(unittest.TestCase):
    def test_a_did_and_the_32_byte_key_a_contract_would_hold(self):
        for did in DIDS:
            key = D.key_from_did(did)
            self.assertEqual(len(key), 32)
            self.assertEqual(D.did_from_key(key), did)
        with self.assertRaises(ValueError):
            D.did_from_key(b"\1" * 31)
        with self.assertRaises(ValueError):
            D.key_from_did("did:web:example.com")


class TheMappings(unittest.TestCase):
    def test_the_bindings_in_a_document(self):
        m = D.DocumentBindings(CHAIN, REGISTRY, RID).for_document(doc([0, 1]))
        self.assertEqual((m.node_of(ADDRS[0]), m.node_of(ADDRS[1].lower()), m.node_of(ADDRS[2])),
                         (DIDS[0], DIDS[1], None))
        self.assertEqual(m.binding_for(DIDS[0]), binding(0))
        self.assertTrue(m.in_document)
        two = D.DocumentBindings(CHAIN, REGISTRY, RID, known={DIDS[0]: binding(0), DIDS[1]: binding(0, DIDS[1])})
        self.assertIsNone(two.node_of(ADDRS[0]))  # one validator bound to two nodes maps to none
        self.assertIn("bound to two delegates", two.why_unmapped(ADDRS[0]))
        known = D.DocumentBindings(CHAIN, REGISTRY, RID)
        known.know(DIDS[3], binding(3))
        self.assertEqual(known.node_of(ADDRS[3]), DIDS[3])
        self.assertIsNone(known.for_document(doc([0])).node_of(ADDRS[3]))  # a document's view: its bindings only

    def test_the_chain_reader(self):
        """#251's contract change: each seat's node key as its registration signed it (Validators.radNodeOf)."""
        with self.assertRaises(ValueError):
            D.ChainSeatNodes(None)
        keys = {ADDRS[0].lower(): D.key_from_did(DIDS[0]), ADDRS[1].lower(): b"\0" * 32}
        reads = []
        chain = D.ChainSeatNodes(lambda v: reads.append(v) or keys.get(v.lower(), b""))
        self.assertEqual((chain.node_of(ADDRS[0]), chain.node_of(ADDRS[1]), chain.node_of(ADDRS[2])),
                         (DIDS[0], None, None))
        self.assertIn("registered no Radicle node key on-chain", chain.why_unmapped(ADDRS[1]))
        self.assertIs(chain.for_document(doc([0])), chain)  # the chain doesn't depend on the document
        self.assertFalse(chain.in_document)
        self.assertIsNone(chain.binding_for(DIDS[0]))  # nothing travels in the document
        chain.node_of(ADDRS[0].lower())
        self.assertEqual(sum(1 for r in reads if r.lower() == ADDRS[0].lower()), 1)  # a registration can't change

    def test_the_chain_reader_of_a_chain_view(self):
        class View:
            def rad_node_of(self, key):
                return D.key_from_did(DIDS[2]) if key == ADDRS[2] else b"\0" * 32
        nodes = D.ChainSeatNodes.of(View())
        self.assertEqual((nodes.node_of(ADDRS[2]), nodes.node_of(ADDRS[0])), (DIDS[2], None))

    def test_a_node_key_from_a_did_a_node_id_or_hex(self):
        key = D.key_from_did(DIDS[0])
        self.assertEqual(D.parse_node(DIDS[0]), key)
        self.assertEqual(D.parse_node(DIDS[0][len("did:key:"):]), key)  # `rad self --nid`
        self.assertEqual(D.parse_node("0x" + key.hex()), key)
        self.assertEqual(D.parse_node(" 0x" + key.hex().upper() + "\n"), key)
        self.assertEqual(D.parse_node("0x" + "00" * 32), b"\0" * 32)  # zero is the caller's to refuse or allow
        for bad in ("", "0x12", "0x" + "zz" * 32, "did:key:zQ3shokFTS3brHcDQrn82RUDfCZESWL1ZdCEJwekUDPQiYBme",
                    "did:web:example.com", "z6Mk0OIl", RID):
            with self.assertRaises(ValueError, msg=bad):
                D.parse_node(bad)


class VerifyDelegates(unittest.TestCase):
    def test_passes_when_the_delegates_are_the_seats_nodes(self):
        ok, problems = D.verify_delegates(plain([0, 1, 2]), ADDRS[:3], Mapping(dict(zip(ADDRS, DIDS))))
        self.assertTrue(ok, problems)
        ok, problems = D.verify_delegates(doc([0, 1, 2]), ADDRS[:3], D.DocumentBindings(CHAIN, REGISTRY, RID))
        self.assertTrue(ok, problems)

    def test_a_seat_without_a_node_is_unmapped_and_fails(self):
        m = Mapping({ADDRS[0]: DIDS[0], ADDRS[1]: DIDS[1]})  # seat 2 has no node ID
        ok, problems = D.verify_delegates(plain([0, 1]), ADDRS[:3], m)
        self.assertFalse(ok)
        self.assertEqual(problems, [f"seat {ADDRS[2].lower()} has no delegate: no Radicle node ID is recorded for it "
                                    f"(unmapped)"])
        # and a key for it in the document doesn't count: it isn't any seat's node
        ok, problems = D.verify_delegates(plain([0, 1, 2]), ADDRS[:3], m)
        self.assertIn(f"delegate {DIDS[2]} isn't the Radicle node of any seat on-chain", problems)

    def test_names_every_other_difference(self):
        m = Mapping(dict(zip(ADDRS, DIDS)))
        ok, problems = D.verify_delegates(plain([0, 1, 2]), ADDRS[:2], m)  # a delegate not seated
        self.assertIn(f"delegate {DIDS[2]} isn't the Radicle node of any seat on-chain", problems)
        ok, problems = D.verify_delegates(plain([0, 1]), ADDRS[:3], m)  # a seat's node that isn't a delegate
        self.assertIn(f"seat {ADDRS[2].lower()}'s node {DIDS[2]} isn't a delegate", problems)
        ok, problems = D.verify_delegates(plain([0, 1, 2], threshold=1), ADDRS[:3], m)
        self.assertTrue(any("isn't a majority" in p for p in problems))
        ok, problems = D.verify_delegates(plain([0]), ADDRS[:2], Mapping({ADDRS[0]: DIDS[0], ADDRS[1]: DIDS[0]}))
        self.assertTrue(any("name the same node" in p for p in problems))
        ok, problems = D.verify_delegates(plain([], threshold=0), [], m)
        self.assertEqual(problems, ["no delegates"])


class ReviewRevision(unittest.TestCase):
    def setUp(self):
        self.m = Mapping(dict(zip(ADDRS, DIDS)))

    def test_accepts_the_seats_nodes_with_the_new_one_published_at_the_head(self):
        ok, why = D.review_revision(plain([0, 1, 2]), plain([0, 1, 2, 3]), ADDRS, self.m, PUBLISHED, HEAD)
        self.assertTrue(ok, why)
        ok, why = D.review_revision(plain([0, 1, 2]), plain([0, 1]), ADDRS[:2], self.m, PUBLISHED, HEAD)  # removal
        self.assertTrue(ok, why)

    def test_refuses(self):
        cur = plain([0, 1, 2])
        ok, why = D.review_revision(cur, plain([0, 1, 2, 3]), ADDRS, self.m, {**PUBLISHED, D.nid(DIDS[3]): "b" * 40},
                                    HEAD)
        self.assertFalse(ok)
        self.assertIn("hasn't published main at the head", why)
        ok, why = D.review_revision(cur, plain([0, 1, 2, 3]), ADDRS[:3], self.m, PUBLISHED, HEAD)  # 3 isn't seated
        self.assertFalse(ok)
        self.assertIn("isn't the Radicle node of any seat", why)
        changed = plain([0, 1, 2, 3])
        changed["payload"][D.PROJECT]["defaultBranch"] = "rogue"
        ok, why = D.review_revision(cur, changed, ADDRS, self.m, PUBLISHED, HEAD)
        self.assertFalse(ok)
        self.assertIn("changes more than", why)
        ok, why = D.review_revision(cur, plain([0, 1, 2], threshold=1), ADDRS[:3], self.m, PUBLISHED, HEAD)
        self.assertFalse(ok)
        self.assertIn("isn't a majority", why)

    def test_an_unmapped_seat_is_left_out_never_given_a_key(self):
        m = Mapping({ADDRS[0]: DIDS[0], ADDRS[1]: DIDS[1]})  # seat 2 is seated but has no node ID
        ok, why = D.review_revision(plain([0]), plain([0, 1]), ADDRS[:3], m, PUBLISHED, HEAD)
        self.assertTrue(ok, why)
        self.assertIn("1 seat(s) unmapped, left out", why)
        ok, why = D.review_revision(plain([0]), plain([0, 1, 2]), ADDRS[:3], m, PUBLISHED, HEAD)  # a key for it
        self.assertFalse(ok)

    def test_with_bindings_a_revision_cant_drop_a_known_seat(self):
        nodes = D.DocumentBindings(CHAIN, REGISTRY, RID)
        ok, why = D.review_revision(doc([0, 1, 2]), doc([0, 1, 2, 3]), ADDRS, nodes, PUBLISHED, HEAD)
        self.assertTrue(ok, why)
        # seat 2 is still seated: a revision leaving out its delegate and binding drops it
        ok, why = D.review_revision(doc([0, 1, 2]), doc([0, 1]), ADDRS[:3], nodes, PUBLISHED, HEAD)
        self.assertFalse(ok)
        self.assertIn(f"drops seat {ADDRS[2].lower()}'s node", why)
        # nor bind a seat to another node
        moved = doc([0, 1, 3])
        moved["payload"][D.PAYLOAD]["bindings"] = {DIDS[0]: binding(0), DIDS[1]: binding(1),
                                                   DIDS[3]: binding(2, DIDS[3])}
        ok, why = D.review_revision(doc([0, 1, 2]), moved, ADDRS[:3], nodes, PUBLISHED, HEAD)
        self.assertFalse(ok)
        self.assertIn("changes seat", why)


class OnePendingRevisionAtATime(unittest.TestCase):
    def setUp(self):
        self.m = Mapping(dict(zip(ADDRS, DIDS)))

    def test_in_sync(self):
        step = D.identity_step(cob(plain([0, 1, 2])), ADDRS[:3], self.m, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.IN_SYNC)

    def test_proposes_only_when_nothing_is_pending(self):
        step = D.identity_step(cob(plain([0, 1, 2])), ADDRS, self.m, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.PROPOSE)
        self.assertEqual(step.args, ("--delegate", DIDS[3], "--threshold", "3"))  # no payload: the chain's mapping
        # a second seat change before the first revision is accepted: review it, propose nothing
        step = D.identity_step(cob(plain([0, 1, 2]), plain([0, 1, 2, 3])), ADDRS, self.m, PUBLISHED, HEAD, DIDS[1])
        self.assertEqual((step.action, step.revision), (D.ACCEPT, "1" * 40))
        # its author, who voted with the proposal, waits
        voted = {1: {D.nid(DIDS[0]): {"Accept": "sig"}}}
        step = D.identity_step(cob(plain([0, 1, 2]), plain([0, 1, 2, 3]), votes=voted), ADDRS, self.m, PUBLISHED,
                               HEAD, DIDS[0])
        self.assertEqual(step.action, D.WAIT)
        self.assertIn("nothing is proposed while it's pending", step.reason)
        self.assertIn("1 of the 2 accepts needed", step.reason)

    def test_reviews_the_oldest_pending_revision_first(self):
        rogue = plain([0, 1, 2])
        rogue["delegates"].append(DIDS[3])  # 3 isn't seated in this test
        rogue["threshold"] = 3
        good = plain([0, 1])
        c = cob(plain([0, 1, 2]), rogue, good)
        step = D.identity_step(c, ADDRS[:2], self.m, PUBLISHED, HEAD, DIDS[1])
        self.assertEqual((step.action, step.revision), (D.REJECT, "1" * 40))
        # once it's rejected, the next one
        c["revisions"]["1" * 40]["state"] = "rejected"
        step = D.identity_step(c, ADDRS[:2], self.m, PUBLISHED, HEAD, DIDS[1])
        self.assertEqual((step.action, step.revision), (D.ACCEPT, "2" * 40))

    def test_waits(self):
        # not a delegate: no vote, no proposal
        step = D.identity_step(cob(plain([0, 1, 2]), plain([0, 1, 2, 3])), ADDRS, self.m, PUBLISHED, HEAD, DIDS[3])
        self.assertEqual(step.action, D.WAIT)
        step = D.identity_step(cob(plain([0, 1, 2])), ADDRS, self.m, PUBLISHED, HEAD, DIDS[3])
        self.assertEqual(step.action, D.WAIT)
        self.assertIn("isn't a delegate", step.reason)
        # a new seat that hasn't published main at the head yet
        step = D.identity_step(cob(plain([0, 1, 2])), ADDRS, self.m, {**PUBLISHED, D.nid(DIDS[3]): None}, HEAD,
                               DIDS[0])
        self.assertEqual(step.action, D.WAIT)
        self.assertIn("hasn't published main at the head", step.reason)
        # every mapped seat is a delegate already: the unmapped one is only reported
        m = Mapping({ADDRS[0]: DIDS[0], ADDRS[1]: DIDS[1]})
        step = D.identity_step(cob(plain([0, 1])), ADDRS[:3], m, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.WAIT)
        self.assertIn("(unmapped)", step.reason)

    def test_an_unmapped_seat_gets_no_key_but_the_others_change(self):
        m = Mapping({ADDRS[0]: DIDS[0], ADDRS[1]: DIDS[1]})  # seat 2 has no node ID
        step = D.identity_step(cob(plain([0])), ADDRS[:3], m, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.PROPOSE)
        self.assertEqual(step.args, ("--delegate", DIDS[1], "--threshold", "2"))

    def test_with_bindings_the_proposal_carries_them(self):
        nodes = D.DocumentBindings(CHAIN, REGISTRY, RID, known={DIDS[3]: binding(3)})  # the new seat's own binding
        step = D.identity_step(cob(doc([0, 1, 2])), ADDRS, nodes, PUBLISHED, HEAD, DIDS[3])
        self.assertEqual(step.action, D.WAIT)  # not a delegate yet
        nodes = D.DocumentBindings(CHAIN, REGISTRY, RID)
        step = D.identity_step(cob(doc([0, 1, 2])), ADDRS, nodes, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.WAIT)  # seat 3's binding isn't known to this node
        self.assertIn("(unmapped)", step.reason)
        nodes.know(DIDS[3], binding(3))  # e.g. from ORACLE_SEAT_BINDINGS
        step = D.identity_step(cob(doc([0, 1, 2])), ADDRS, nodes, PUBLISHED, HEAD, DIDS[0])
        self.assertEqual(step.action, D.PROPOSE)
        self.assertEqual(step.args[:6], ("--delegate", DIDS[3], "--threshold", "3", "--payload", D.PAYLOAD))
        self.assertIn(DIDS[3], step.args[7])

    def test_pending_revisions_in_timeline_order(self):
        c = cob(plain([0]), plain([0, 1]), plain([0, 2]))
        c["timeline"] = ["c" * 40, "2" * 40, "1" * 40]
        self.assertEqual([r["id"] for r in D.pending_revisions(c)], ["2" * 40, "1" * 40])


class Patches(unittest.TestCase):
    def test_each_revision_with_the_claim_as_its_body(self):
        cobs = [{"_id": "8b484ee23373142214baa12cb8e2a348a2f17b33", "title": "Fix title", "state": {"status": "open"},
                 "revisions": {
                     "8b484ee23373142214baa12cb8e2a348a2f17b33": {
                         "description": [{"body": "Bounty: 1\n\nSubmission: 2", "embeds": []}],
                         "base": "7e9de768a1b415475ed4710fc352c04345a3b3f0",
                         "oid": "0d0d13982db0302369e5eac86687891dfd2219f1"},
                     "9" * 40: None}}]  # a redacted revision
        (p,) = D.patch_pulls(cobs)
        self.assertEqual((p["patch"], p["revision"], p["head_sha"], p["base_sha"], p["body"], p["number"]),
                         (cobs[0]["_id"], cobs[0]["_id"], "0d0d13982db0302369e5eac86687891dfd2219f1",
                          "7e9de768a1b415475ed4710fc352c04345a3b3f0", "Bounty: 1\n\nSubmission: 2", 0x8b484ee))


if __name__ == "__main__":
    unittest.main()
