"""The seats' registration check (proof-of-fix#210, design D3: oracle/registration.py) and the exchange's `accept` kind,
against a fake chain, with the folder transport and five seat keys: a quorum opens the bounty with one accept, relayed
by the lowest-addressed signer; an unclaimed registration gets no signature; with the relayer stopped, another relays
after the grace; a model judge signs nothing; and the exchange takes an accept only from an active oracle key, over
the right digest, for an issue still waiting for its check. No Docker, no chain. The local suite's scenario 10 runs it
against a devnet, where RaceV2 checks the signatures."""

from __future__ import annotations

import tempfile
import unittest
import urllib.error
from pathlib import Path

from bot import logic
from exchange.service import Board, Refused
from oracle import crypto, v2
from oracle.judge import FakeJudge
from oracle.keys import LocalDevKeys
from oracle.registration import RegistrationCheck, from_env
from oracle.rpc import Reverted
from oracle.transport import FolderExchange, HttpExchange

CHAIN = 7193
RACE = crypto.checksum("0x" + "ab" * 20)
REPORTER = crypto.checksum("0x" + "12" * 20)
WEIGHT = 120 * 10**6


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeChain:
    """RaceV2 and Verdicts as the check reads them; `accept` checks the quorum's signatures as RaceV2 does."""

    def __init__(self, keys, quorum=3):
        self.race, self.keys_, self.quorum_ = RACE, [k.address() for k in keys], quorum
        self.issues = {7: {"repo": "0x" + "00" * 32, "reporter": REPORTER, "state": v2.POSTED, "bounty": 0},
                       8: {"repo": "0x" + "00" * 32, "reporter": REPORTER, "state": v2.POSTED, "bounty": 0}}
        self.accepts: list = []

    def chain_id(self):
        return CHAIN

    def race_domain(self):
        return v2.race_domain(CHAIN, RACE)

    def registered(self, from_block, to_block=None):
        return [{"issue": n, "reporter": i["reporter"], "block": 5} for n, i in sorted(self.issues.items())]

    def issue(self, n):
        return dict(self.issues[n])

    def keys(self):
        return list(self.keys_)

    def is_oracle(self, who):
        return who.lower() in {k.lower() for k in self.keys_}

    def quorum(self):
        return self.quorum_

    def accept(self, relayer, n, weight, auth):
        nonce, sigs = auth
        i = self.issues[n]
        digest = v2.accept_digest(self.race_domain(), n, weight, nonce)
        signers = [crypto.recover(digest, s) for s in sigs]
        assert signers == sorted(signers, key=lambda a: int(a, 16)) and len(set(signers)) == len(signers)
        assert all(self.is_oracle(s) for s in signers) and len(signers) >= self.quorum_
        if i["state"] != v2.POSTED or i["bounty"]:
            raise Reverted("Refused()")
        i["bounty"] = 100 + n
        self.accepts.append((relayer, n, weight, signers))


class FakeWallet:
    def __init__(self, chain, me):
        self.chain, self.me = chain, me

    def send(self, to, signature, *args):
        assert to == RACE and signature == "accept(uint256,uint256,(bytes32,bytes[]))", signature
        self.chain.accept(self.me, *args)
        return {"logs": []}


class FakeHost:
    def __init__(self, issues):
        self._issues = issues

    def issues(self, state="open", label=None):
        return [i for i in self._issues if state in (i["state"], "all") and (label is None or label in i["labels"])]


def claim(n, number=12):
    return {"number": number, "body": f"Registration: {n}\nReporter wallet: {REPORTER}\n", "labels": ["bounty"],
            "state": "open"}


class Rig:
    def __init__(self, tmp, host_issues, judge=None, n=5):
        self.keys = [LocalDevKeys(i, extra_chain_ids={CHAIN}) for i in range(n)]
        self.chain = FakeChain(self.keys)
        self.clock = Clock()
        self.host = FakeHost(host_issues)
        self.logs: list = []
        self.checks = [RegistrationCheck(self.chain, k, FakeWallet(self.chain, k.address()), self.host,
                                         FolderExchange(Path(tmp) / "exchange", RACE), judge or FakeJudge(), WEIGHT,
                                         grace=30, clock=self.clock, log=self.logs.append) for k in self.keys]

    def rounds(self, n=4, only=None):
        for _ in range(n):
            for i, c in enumerate(self.checks):
                if only is None or i in only:
                    c.tick(0)

    def lowest(self):
        return min(range(len(self.keys)), key=lambda i: int(self.keys[i].address(), 16))


class TheCheck(unittest.TestCase):
    def test_a_quorum_opens_the_bounty_with_one_accept_by_the_lowest_signer(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)])
            rig.rounds()
            self.assertEqual(len(rig.chain.accepts), 1)
            relayer, n, weight, signers = rig.chain.accepts[0]
            self.assertEqual((n, weight, relayer), (7, WEIGHT, rig.keys[rig.lowest()].address()))
            self.assertGreaterEqual(len(signers), 3)
            self.assertEqual(rig.chain.issues[7]["bounty"], 107)
            self.assertEqual(len(FolderExchange(Path(tmp) / "exchange", RACE).all(7, "accept")), 5)
            self.assertTrue((Path(tmp) / "exchange" / RACE.lower() / "issue-7").is_dir())

    def test_an_unclaimed_registration_gets_no_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)])  # 8 is registered, and no issue claims it
            rig.rounds()
            self.assertEqual(FolderExchange(Path(tmp) / "exchange", RACE).all(8, "accept"), {})
            self.assertEqual([a[1] for a in rig.chain.accepts], [7])
            self.assertFalse(any(c.waiting() and 8 in c.claimed_since for c in rig.checks))

    def test_a_claim_with_the_wrong_wallet_or_label_isnt_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = {**claim(7), "body": "Registration: 7\nReporter wallet: 0x" + "34" * 20}
            rig = Rig(tmp, [wrong, {**claim(8, 13), "labels": []}])
            rig.rounds()
            self.assertEqual(rig.chain.accepts, [])

    def test_the_relayer_stopped_another_relays_after_the_grace(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)])
            low = rig.lowest()
            others = [i for i in range(5) if i != low]
            rig.rounds(1)  # everyone signs
            rig.rounds(3, only=others)  # the lowest-addressed signer is gone
            self.assertEqual(rig.chain.accepts, [])
            rig.clock.t += 31
            rig.rounds(2, only=others)
            self.assertEqual(len(rig.chain.accepts), 1)
            self.assertNotEqual(rig.chain.accepts[0][0], rig.keys[low].address())

    def test_a_revert_because_it_opened_meanwhile_is_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)])
            rig.rounds(1)
            rig.clock.t += 31
            rig.chain.issues[7]["bounty"] = 99  # someone else relayed between the read and the send
            real = rig.chain.issue
            rig.chain.issue = lambda n: {**real(n), "bounty": 0}
            rig.rounds(2)
            self.assertEqual(rig.chain.accepts, [])
            self.assertTrue(any("opened meanwhile" in line for line in rig.logs))

    def test_a_model_judge_signs_nothing_and_says_why(self):
        class ModelJudge:
            reads_evidence = True

        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)], judge=ModelJudge())
            rig.rounds()
            self.assertEqual(FolderExchange(Path(tmp) / "exchange", RACE).all(7, "accept"), {})
            self.assertEqual(rig.chain.accepts, [])
            self.assertTrue(any("real judges not supported yet" in line for line in rig.logs))

    def test_the_same_digest_on_every_seat(self):
        n1, n2 = v2.accept_nonce(RACE, 7), v2.accept_nonce(RACE.lower(), 7)
        self.assertEqual(n1, n2)
        self.assertEqual(n1, crypto.keccak256(b"pof-accept" + bytes.fromhex(RACE[2:]) + crypto.word(7)))
        self.assertNotEqual(n1, v2.accept_nonce(RACE, 8))

    def test_a_claim_waiting_holds_the_node_up_to_its_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            rig = Rig(tmp, [claim(7)])
            c = rig.checks[0]
            c.tick(0)
            self.assertTrue(c.waiting())
            rig.clock.t += 901
            self.assertFalse(c.waiting())

    def test_off_unless_turned_on(self):
        self.assertIsNone(from_env({}, None, None, None, None, None, FakeJudge()))
        self.assertIsNone(from_env({"ORACLE_REGISTRATION_CHECK": "off"}, None, None, None, None, None, FakeJudge()))
        k = LocalDevKeys(0, extra_chain_ids={CHAIN})
        on = from_env({"ORACLE_REGISTRATION_CHECK": "on", "ORACLE_REGISTER_WEIGHT": "120", "ORACLE_RELAY_GRACE": "5",
                       "ORACLE_REPO_ID": "0x" + "21" * 32}, FakeChain([k]), k, None, None, None, FakeJudge())
        self.assertEqual((on.weight, on.grace, on.repo_id), (WEIGHT, 5.0, bytes.fromhex("21" * 32)))


class TheExchangeTakesAccepts(unittest.TestCase):
    def setUp(self):
        self.keys = [LocalDevKeys(i, extra_chain_ids={CHAIN}) for i in range(4)]
        self.chain = FakeChain(self.keys[:3])  # the 4th isn't an active oracle key
        self.board = Board(self.chain, log=lambda m: None)

    def message(self, k, issue=7, weight=WEIGHT, nonce=None, digest_issue=None):
        nonce = nonce or v2.accept_nonce(RACE, issue)
        digest = v2.accept_digest(v2.race_domain(CHAIN, RACE), digest_issue or issue, weight, nonce)
        return {"node": k.address(), "weight": weight, "nonce": "0x" + nonce.hex(), "sig": "0x" + k.sign(digest).hex()}

    def refused(self, status, body, issue=7):
        with self.assertRaises(Refused) as e:
            self.board.post(issue, "accept", body)
        self.assertEqual(e.exception.status, status, e.exception.reason)

    def test_an_active_oracle_keys_signature_over_the_digest(self):
        self.board.post(7, "accept", self.message(self.keys[0]))
        self.board.post(7, "accept", self.message(self.keys[0]))  # the same again: taken once
        got = self.board.read(7, "accept")
        self.assertEqual(list(got), [self.keys[0].address().lower()])
        self.assertEqual(self.board.read(7, "seal"), {})  # an issue's board isn't a submission's

    def test_a_non_oracle_key_is_refused_403(self):
        self.refused(403, self.message(self.keys[3]))

    def test_a_wrong_digest_is_refused(self):
        self.refused(403, self.message(self.keys[0], digest_issue=8))
        self.refused(403, {**self.message(self.keys[0]), "weight": WEIGHT + 1})
        self.refused(400, {**self.message(self.keys[0]), "nonce": "0x12"})

    def test_an_issue_already_open_is_refused(self):
        self.chain.issues[7]["bounty"] = 4
        self.refused(409, self.message(self.keys[0]))

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Board(self.chain, state=Path(tmp) / "board.jsonl", log=lambda m: None)
            board.post(7, "accept", self.message(self.keys[1]))
            again = Board(self.chain, state=Path(tmp) / "board.jsonl", log=lambda m: None)
            self.assertEqual(list(again.read(7, "accept")), [self.keys[1].address().lower()])

    def test_the_http_transport_uses_the_issue_path(self):
        ex = HttpExchange("http://127.0.0.1:9", RACE)
        self.assertEqual(ex._path(7, "accept"), f"/v1/{RACE.lower()}/issue/7/accept")
        self.assertEqual(ex._path(7, "seal"), f"/v1/{RACE.lower()}/7/seal")

    def test_the_service_routes_the_issue_path(self):
        import threading
        import urllib.request

        from exchange.service import server

        srv = server(self.board, "127.0.0.1", 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}"
            ex = HttpExchange(url, RACE, timeout=5, log=lambda m: None)
            body = self.message(self.keys[2])
            ex.put(7, body["node"], "accept", {k: v for k, v in body.items() if k != "node"})
            self.assertEqual(list(self.board.read(7, "accept")), [self.keys[2].address().lower()])
            self.assertEqual(list(HttpExchange(url, RACE, timeout=5).all(7, "accept")),
                             [self.keys[2].address().lower()])
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f"{url}/v1/{RACE.lower()}/7/accept", timeout=5)
            self.assertEqual(e.exception.code, 404)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
