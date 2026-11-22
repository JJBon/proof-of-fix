"""The Radicle spike under v3 (proof-of-fix#251): the seats-to-delegates rules through spikes/radicle/seats.py's own
signatures, alone (the spike itself, scripts/radicle-spike.sh --v3, needs Docker). The rules live in oracle/delegates.py
since task 4.1; tests/test_delegates.py tests them there, with both seat-to-node mappings."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "spikes" / "radicle"))

import seats as S  # noqa: E402
from oracle import crypto  # noqa: E402

CHAIN, REGISTRY, RID = 31337, "0x" + "12" * 20, "rad:z2ZdzxFSFzBavdeNbUKwEnfVcAq5R"
DIDS = ["did:key:z6Mkr4Av6WRPU25LajzvoTtRFjdp7kPQLxCgpJodG1RCtzNX",
        "did:key:z6MkjEcGuYLSEiXrutj8VwUoqkPAUajWhcJnpjYiQe4Ks7sx",
        "did:key:z6MkegUjQPzWkbZTUS8DuQWrn52SoKK1WE17EXLwrq1WUnqK",
        "did:key:z6MkopH5QMoynapxG9Yis4TCpWgyaxQNEBeiL39wqJ2GZCR1"]
SECRETS = [11, 22, 33, 44]
ADDRS = [crypto.address(k) for k in SECRETS]
PROJECT = {"defaultBranch": "main", "description": "t", "name": "t"}


def binding(i: int, did: str | None = None, rid: str = RID) -> dict:
    return S.make_binding(lambda d: crypto.sign(SECRETS[i], d), ADDRS[i], CHAIN, REGISTRY, rid, did or DIDS[i])


def doc(idx, threshold=None, bindings=None) -> dict:
    ds = [DIDS[i] for i in idx]
    return {"payload": {S.PROJECT: dict(PROJECT),
                        S.PAYLOAD: {"bindings": bindings if bindings is not None else {DIDS[i]: binding(i) for i in idx}}},
            "delegates": ds, "threshold": S.majority(len(ds)) if threshold is None else threshold}


class TestSeats(unittest.TestCase):
    def test_majority(self):
        self.assertEqual([S.majority(n) for n in (1, 2, 3, 4, 5, 255)], [1, 2, 2, 3, 3, 128])
        with self.assertRaises(ValueError):
            S.majority(0)

    def test_a_binding_recovers_to_its_validator_for_this_repository_only(self):
        b = binding(0)
        self.assertEqual(S.binding_signer(b, CHAIN, REGISTRY, RID, DIDS[0]).lower(), ADDRS[0].lower())
        self.assertIsNone(S.binding_signer(b, CHAIN, REGISTRY, RID, DIDS[1]))  # another node
        self.assertIsNone(S.binding_signer(b, CHAIN, REGISTRY, "rad:zOther", DIDS[0]))  # another repository
        self.assertIsNone(S.binding_signer(b, 1, REGISTRY, RID, DIDS[0]))  # another chain
        self.assertIsNone(S.binding_signer({**b, "validator": ADDRS[1]}, CHAIN, REGISTRY, RID, DIDS[0]))
        self.assertIsNone(S.binding_signer({"validator": ADDRS[0], "sig": "0x" + "00" * 65}, CHAIN, REGISTRY, RID,
                                           DIDS[0]))

    def test_verify_delegates_passes_when_the_delegates_are_the_seats(self):
        ok, problems = S.verify_delegates(doc([0, 1, 2]), ADDRS[:3], CHAIN, REGISTRY, RID)
        self.assertTrue(ok, problems)

    def test_verify_delegates_names_every_difference(self):
        ok, problems = S.verify_delegates(doc([0, 1]), ADDRS[:3], CHAIN, REGISTRY, RID)  # a seat with no delegate
        self.assertFalse(ok)
        self.assertIn(f"seat {ADDRS[2].lower()} has no delegate: no seat binding names it (unmapped)", problems)
        ok, problems = S.verify_delegates(doc([0, 1, 2]), ADDRS[:2], CHAIN, REGISTRY, RID)  # a delegate not seated
        self.assertFalse(ok)
        self.assertTrue(any("isn't seated on-chain" in p for p in problems))
        ok, problems = S.verify_delegates(doc([0, 1, 2], threshold=1), ADDRS[:3], CHAIN, REGISTRY, RID)
        self.assertFalse(ok)
        self.assertTrue(any("isn't a majority" in p for p in problems))
        d = doc([0, 1, 2])
        del d["payload"][S.PAYLOAD]["bindings"][DIDS[2]]
        ok, problems = S.verify_delegates(d, ADDRS[:3], CHAIN, REGISTRY, RID)
        self.assertIn(f"delegate {DIDS[2]} has no seat binding", problems)
        d = doc([0, 1, 2], bindings={DIDS[0]: binding(0), DIDS[1]: binding(1),
                                     DIDS[2]: {"validator": ADDRS[2], "sig": binding(0, DIDS[2])["sig"]}})
        ok, problems = S.verify_delegates(d, ADDRS[:3], CHAIN, REGISTRY, RID)
        self.assertTrue(any("doesn't recover" in p for p in problems))
        d = doc([0, 1], bindings={DIDS[0]: binding(0), DIDS[1]: binding(0, DIDS[1])})  # one validator, two nodes
        ok, problems = S.verify_delegates(d, ADDRS[:1], CHAIN, REGISTRY, RID)
        self.assertTrue(any("bound to two delegates" in p for p in problems))

    def test_review_accepts_only_the_seats_with_the_new_one_published_at_the_head(self):
        head = "a" * 40
        cur, prop = doc([0, 1, 2]), doc([0, 1, 2, 3])
        published = {DIDS[i].removeprefix("did:key:"): head for i in range(4)}
        ok, why = S.review_revision(cur, prop, ADDRS, published, head, CHAIN, REGISTRY, RID)
        self.assertTrue(ok, why)
        ok, why = S.review_revision(cur, prop, ADDRS, {**published, DIDS[3][8:]: "b" * 40}, head, CHAIN, REGISTRY,
                                    RID)
        self.assertFalse(ok)
        self.assertIn("hasn't published main at the head", why)
        ok, why = S.review_revision(cur, prop, ADDRS[:3], published, head, CHAIN, REGISTRY, RID)  # 3 isn't seated
        self.assertFalse(ok)
        changed = doc([0, 1, 2, 3])
        changed["payload"][S.PROJECT]["defaultBranch"] = "rogue"
        ok, why = S.review_revision(cur, changed, ADDRS, published, head, CHAIN, REGISTRY, RID)
        self.assertFalse(ok)
        self.assertIn("changes more than", why)
        ok, why = S.review_revision(cur, doc([0, 1]), ADDRS[:2], published, head, CHAIN, REGISTRY, RID)  # a removal
        self.assertTrue(ok, why)

    def test_update_args(self):
        cur = doc([0, 1, 2])
        args = S.update_args(cur, {ADDRS[0]: DIDS[0], ADDRS[2]: DIDS[2], ADDRS[3]: DIDS[3]},
                             {DIDS[0]: binding(0), DIDS[2]: binding(2), DIDS[3]: binding(3)})
        self.assertEqual(args[:6], ["--delegate", DIDS[3], "--rescind", DIDS[1], "--threshold", "2"])
        self.assertEqual(args[6:9], ["--payload", S.PAYLOAD, "bindings"])
        self.assertIn(DIDS[3], args[9])

    def test_patch_pulls_reads_each_revision(self):
        cob = {"_id": "468766f3e9f59877e18261669587eb093cd448b2", "title": "Fix add", "state": {"status": "open"},
               "revisions": {"468766f3e9f59877e18261669587eb093cd448b2": {
                   "description": [{"body": "Bounty: 1\nSubmission: 7"}],
                   "base": "701c8a8423c72fcf313a239c16662990a0e2f72e",
                   "oid": "a1caaed80d36aa193f39886d8b1a4c5a0f9e325e"}, "redacted": None}}
        pulls = S.patch_pulls([cob])
        self.assertEqual(len(pulls), 1)
        p = pulls[0]
        self.assertEqual((p["head_sha"], p["base_sha"], p["body"], p["title"], p["state"]),
                         ("a1caaed80d36aa193f39886d8b1a4c5a0f9e325e", "701c8a8423c72fcf313a239c16662990a0e2f72e",
                          "Bounty: 1\nSubmission: 7", "Fix add", "open"))
        self.assertEqual(p["number"], int("468766f", 16))


if __name__ == "__main__":
    unittest.main()
