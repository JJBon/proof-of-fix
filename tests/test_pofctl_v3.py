"""pofctl on v3 and Radicle (proof-of-fix#251 task 4.4), without a chain: the keystore (AES-128-CTR, scrypt and PBKDF2,
against FIPS-197 and the format's own vectors, and a keystore `cast wallet import` wrote), a keystore key never printed,
devnet keys refused off the local chains (Sepolia's 11155111 among them), the pledge refused below 3 active solvers
before anything is sent, and `status`'s cap, open claims and deposit. The end-to-end run against the real contracts
is `scripts/pofctl-e2e.sh --version 3` (it needs Docker)."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from oracle import crypto, v3
from oracle.abi import selector
from oracle.rpc import Reverted, Wallet
from pofctl import cli, keystore, v3cli
from pofctl import keys as keysrc

C = 10**6
RACE, PANELS, FEES, POOL, REGISTRY, HEADS, COIN, BOOK = ("0x" + f"{i:02x}" * 20 for i in range(0xA1, 0xA9))
REPO = crypto.keccak256(b"rad:z4PofctrTest")
HEAD = "ab" * 20
# What `cast wallet import pof-test --private-key 0x4c08… --unsafe-password "pofctl test"` wrote (Foundry's pinned
# image): scrypt n = 8192, r = 8, p = 1. The key is web3.js's public documentation example, a throwaway.
CAST_KEYSTORE = {"crypto": {"cipher": "aes-128-ctr", "cipherparams": {"iv": "35528f2e2973c8e8c5c65b1ca199782b"},
                            "ciphertext": "c907ab1a1ffea4bc3847000f72c3f61f3e49eac622b14e1577e3908299807fcb",
                            "kdf": "scrypt", "kdfparams": {"dklen": 32, "n": 8192, "p": 1, "r": 8, "salt":
                            "09ab91a04eb1016f5f5e967d316a594a41c5a58bc1cb05c30ef51dccb09eb416"},
                            "mac": "0bfb409922c2227f3baebae50e27948fc95700923088a6ddf9d01a132eeba687"},
                 "id": "4a1f51a6-e540-4386-9ecf-0ccdca653255", "version": 3}
CAST_KEY = 0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f362318
# The Web3 Secret Storage definition's PBKDF2-SHA-256 test vector (password "testpassword").
SPEC_PBKDF2 = {"crypto": {"cipher": "aes-128-ctr", "cipherparams": {"iv": "6087dab2f9fdbbfaddc31a909735c1e6"},
                          "ciphertext": "5318b4d5bcd28de64ee5559e671353e16f075ecae9f99c7a79a38af5f869aa46",
                          "kdf": "pbkdf2", "kdfparams": {"c": 262144, "dklen": 32, "prf": "hmac-sha256", "salt":
                          "ae3cd4e7013836a3df6bd7241b12db061dbe2c6785853cce422d148a624ce0bd"},
                          "mac": "517ead924a9d0dc3124507e3393d175ce3ff7c1e96529c6c555ce9e51205e9b2"},
               "id": "3198bc9c-6672-5ab3-d995-4942343ae5b6", "version": 3}
SPEC_KEY = 0x7a28b5ba57c53603b0b07b56bba752f7784bf506fa95edc395f5cf6c7514fe9d


def _word(addr: str) -> str:
    return "0x" + addr.lower()[2:].rjust(64, "0")


class FakeRpc:
    """Answers the views pofctl's v3 commands read, by (contract, function); records every call. Any transaction
    (estimate, send) is an error: the tests that send patch Wallet.send."""

    url = "http://fake.invalid"

    def __init__(self, chain_id: int = 31337, **over) -> None:
        self.cid, self.calls, self.log_rows = chain_id, [], []
        cfg = (RACE, RACE, 2 * C, 5 * C, 0, 0, 0, 10 * C, 5000, 1000, 1765, 28, 7, 14, 7, 4, 0)
        self.answers = {
            "contracts": lambda to, *a: [PANELS, FEES, POOL, REGISTRY, HEADS, COIN, 1],
            "solverBook": lambda to, *a: [BOOK], "getConfig": lambda to, *a: [cfg], "repo": lambda to, *a: [REPO],
            "head": lambda to, *a: [(bytes.fromhex(HEAD) + b"\0" * 12, b"\0" * 32, 0, 0, 0, b"\0" * 32)],
            "unit": lambda to, *a: [C], "balanceOf": lambda to, *a: [500 * C], "allowance": lambda to, *a: [0],
            "owed": lambda to, *a: [0], "maxDeposit": lambda to, *a: [1_230_000],
            "reputation": lambda to, *a: [0], "openClaims": lambda to, *a: [0], "capOf": lambda to, *a: [50 * C],
            "REP_BASE": lambda to, *a: [50 * C], "REP_MULT": lambda to, *a: [1], "isActive": lambda to, *a: [False],
            "activeCount": lambda to, *a: [0], "ACTIVE_WINDOW": lambda to, *a: [26 * 7 * 86400],
            "bounty": lambda to, *a: [(1, 1, 0, False, 0, 0, 0, 0, 0, 0, 0, 0)],
            "held": lambda to, *a: [0],
            "panelRules": lambda to, *a: [(0, 0, 0, 7, 0)],  # #251 batch 4: the strict defaults, kTop 7
        }
        self.answers.update(over)

    def chain_id(self) -> int:
        return self.cid

    def block(self) -> int:
        return 100

    def view(self, to, sig, returns, *args):
        self.calls.append(("view", to, sig))
        return self.answers[sig.split("(")[0]](to, *args)

    def logs(self, address, from_block=0, topics=None, to_block=None):
        return [r for r in self.log_rows if r["address"] == address.lower() and r["topics"][0] == topics[0]
                and (topics[2] is None or r["topics"][2] == topics[2])]

    def call(self, method, params=None):
        self.calls.append((method, params))
        if method == "eth_getBlockByNumber":
            return {"number": hex(100), "timestamp": hex(10_000)}
        raise AssertionError(f"unexpected {method}: nothing may be sent")


def run_main(argv: list, rpc: FakeRpc) -> tuple:
    """cli.main with the fake chain: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(cli, "Rpc", return_value=rpc), contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.v3 = self.dir / "v3.json"
        self.v3.write_text(json.dumps({"version": 3, "race": RACE, "coin": COIN, "rid": "rad:z4PofctrTest"}))
        self.v2 = self.dir / "v2.json"
        self.v2.write_text(json.dumps({"race": RACE, "coin": COIN, "quoter": PANELS, "verdicts": REGISTRY}))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("POFCTL_", "DEVNET_KEYS"))}
        self.env = mock.patch.dict(os.environ, env, clear=True)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class TestKeystore(unittest.TestCase):
    def test_aes128_fips197_vector(self):
        rk = keystore._expand(bytes(range(16)))
        self.assertEqual(keystore.aes128_block(rk, bytes.fromhex("00112233445566778899aabbccddeeff")).hex(),
                         "69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual((keystore.SBOX[0], keystore.SBOX[0x53]), (0x63, 0xED))

    def test_ctr_is_its_own_inverse_across_blocks(self):
        key, iv = bytes(range(16)), b"\xff" * 16  # the counter wraps from all ones
        data = bytes(range(40))
        self.assertEqual(keystore.aes128_ctr(key, iv, keystore.aes128_ctr(key, iv, data)), data)

    def test_the_formats_pbkdf2_vector(self):
        self.assertEqual(keystore.decrypt(SPEC_PBKDF2, "testpassword"), SPEC_KEY)

    def test_a_keystore_cast_wrote(self):
        self.assertEqual(keystore.decrypt(CAST_KEYSTORE, "pofctl test"), CAST_KEY)

    def test_round_trip_and_its_address(self):
        doc = keystore.encrypt(12345, "pw", n=1 << 10)
        self.assertEqual(doc["address"], crypto.address(12345)[2:].lower())
        self.assertEqual(keystore.decrypt(doc, "pw"), 12345)
        doc = keystore.encrypt(777, "pw", kdf="pbkdf2", c=1000)
        self.assertEqual(keystore.decrypt(doc, "pw"), 777)

    def test_a_wrong_password_or_file_says_so_without_the_key(self):
        with self.assertRaises(keystore.KeystoreError) as e:
            keystore.decrypt(CAST_KEYSTORE, "wrong")
        self.assertIn("wrong password", str(e.exception))
        self.assertNotIn(f"{CAST_KEY:x}", str(e.exception))
        bad = json.loads(json.dumps(CAST_KEYSTORE))
        bad["address"] = "00" * 20
        with self.assertRaises(keystore.KeystoreError) as e:
            keystore.decrypt(bad, "pofctl test")
        self.assertNotIn(f"{CAST_KEY:x}", str(e.exception))
        with self.assertRaises(keystore.KeystoreError):
            keystore.decrypt({"version": 1}, "x")

    def test_the_password_from_its_file_else_the_terminal(self):
        with tempfile.TemporaryDirectory() as d:
            ks, pw = Path(d) / "k.json", Path(d) / "pw"
            ks.write_text(json.dumps(CAST_KEYSTORE))
            pw.write_text("pofctl test\n")
            with mock.patch.dict(os.environ, {keystore.PASSWORD_FILE: str(pw)}):
                self.assertEqual(keystore.load(str(ks)), CAST_KEY)
            with mock.patch.dict(os.environ, {}, clear=True), \
                    mock.patch("getpass.getpass", return_value="pofctl test") as ask:
                self.assertEqual(keystore.load(str(ks)), CAST_KEY)
                self.assertIn(str(ks), ask.call_args[0][0])


class TestKeys(Records):
    """A keystore key is never printed; devnet keys sign only on 31337 and 7193."""

    def keystore_file(self) -> Path:
        ks, pw = self.dir / "solver.json", self.dir / "pw"
        ks.write_text(json.dumps(CAST_KEYSTORE))
        pw.write_text("pofctl test\n")
        os.environ[keystore.PASSWORD_FILE] = str(pw)
        return ks

    def test_a_keystore_key_is_never_printed(self):
        ks = self.keystore_file()
        secret_hex = f"{CAST_KEY:064x}"
        for chain in (31337, 11155111):
            for fmt in ([], ["--json"]):
                code, out, err = run_main(fmt + ["--record", str(self.v3), "--keystore", str(ks), "status"],
                                          FakeRpc(chain))
                self.assertEqual(code, 0, err)
                self.assertIn(crypto.address(CAST_KEY), out)  # it did sign in as the keystore's address
                for text in (out, err):
                    self.assertNotIn(secret_hex, text.lower())
                    self.assertNotIn("pofctl test", text)
        os.environ[keystore.PASSWORD_FILE] = str(self.dir / "nope")
        (self.dir / "nope").write_text("wrong\n")
        code, out, err = run_main(["--record", str(self.v3), "--keystore", str(ks), "status"], FakeRpc(11155111))
        self.assertEqual(code, 1)
        self.assertIn("wrong password", err)
        self.assertNotIn(secret_hex, (out + err).lower())

    def test_the_keystore_wallet_doesnt_show_its_key(self):
        w = Wallet(None, CAST_KEY, "keystore")
        self.assertNotIn(f"{CAST_KEY:x}", repr(w) + str(w) + repr(vars(w).keys()))

    def test_a_devnet_key_is_refused_on_sepolia(self):
        os.environ["DEVNET_KEYS"] = "insecure-local"
        with mock.patch.object(keysrc, "key", side_effect=AssertionError("a devnet key was read")):
            for argv in (["--record", str(self.v3), "status"], ["--record", str(self.v3), "withdraw", "--role", "solver"],
                         ["--record", str(self.v2), "withdraw", "--role", "funder"]):
                code, out, err = run_main(argv, FakeRpc(11155111))
                self.assertEqual(code, 1, argv)
                self.assertIn("devnet keys (source insecure-local) are refused on chain 11155111", err)
                self.assertIn("--keystore", err)
        for env in ({"POFCTL_KEY_SOLVER_A": "0x01"}, {"DEVNET_KEYS": "env", "POFCTL_KEY_SOLVER_A": "0x01"}):
            os.environ.update(env)
            code, _, err = run_main(["--record", str(self.v3), "status"], FakeRpc(11155111))
            self.assertEqual(code, 1)
            self.assertIn("refused on chain 11155111", err)

    def test_devnet_keys_sign_on_the_local_chains_only(self):
        os.environ["DEVNET_KEYS"] = "insecure-local"
        for chain, ok in ((31337, True), (7193, True), (1, False), (10, False), (8453, False), (11155111, False)):
            code, out, err = run_main(["--record", str(self.v3), "status"], FakeRpc(chain))
            self.assertEqual(code == 0, ok, (chain, err))

    def test_a_keystore_signs_on_sepolia(self):
        ks = self.keystore_file()
        code, out, err = run_main(["--json", "--record", str(self.v3), "--keystore", str(ks), "status"],
                                  FakeRpc(11155111))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["solver"], crypto.address(CAST_KEY))


class TestPledge(Records):
    def ctx(self, rpc: FakeRpc):
        os.environ["DEVNET_KEYS"] = "insecure-local"
        a = cli.parser().parse_args(["--record", str(self.v3), "pledge", "--bounty", "1", "--amount", "10"])
        with mock.patch.object(cli, "Rpc", return_value=rpc):
            return cli.Ctx(a), a

    def test_below_three_active_solvers_it_is_refused_before_anything(self):
        for active in (0, 1, 2):
            rpc = FakeRpc(31337, activeCount=lambda to, *a, n=active: [n])
            ctx, a = self.ctx(rpc)
            with mock.patch.object(Wallet, "send", side_effect=AssertionError("sent")) as send, \
                    mock.patch.object(keysrc, "key", side_effect=AssertionError("a key was read")):
                with self.assertRaises(cli.Fail) as e:
                    v3cli.cmd_pledge(ctx, a)
            msg = str(e.exception)
            self.assertIn(f"active solvers: {active} of the 3 needed", msg)
            self.assertIn("Pledges are refused while fewer than 3 solvers are active", msg)
            self.assertIn("26 weeks", msg)
            self.assertIn("Nothing was sent", msg)
            send.assert_not_called()
            self.assertFalse([c for c in rpc.calls if c[0] != "view" and c[0] != "eth_getBlockByNumber"])
            self.assertFalse([c for c in rpc.calls if c[0] == "view" and c[2].startswith("allowance")],
                             "the allowance isn't even read")

    def test_from_three_it_shows_the_count_approves_and_pledges(self):
        rpc = FakeRpc(31337, activeCount=lambda to, *a: [3])
        ctx, a = self.ctx(rpc)
        sent = []
        with mock.patch.object(Wallet, "send", side_effect=lambda to, sig, *args, **kw: sent.append(
                (to, sig, args)) or {"logs": []}):
            data, lines = v3cli.cmd_pledge(ctx, a)
        self.assertEqual([s[1] for s in sent], ["approve(address,uint256)", "pledge(uint256,uint256)"])
        self.assertEqual((sent[0][0], sent[0][2][0]), (crypto.checksum(COIN), crypto.checksum(RACE)))  # the race may take the coin
        self.assertEqual(sent[1][2], (1, 10 * C))
        self.assertEqual(lines[0], "active solvers: 3 (pledges open at 3)")
        self.assertTrue(lines[1].startswith(f"approved RaceV3 {crypto.checksum(RACE)} to take the fee coin"))
        self.assertIn("the pledge needs 10.000000 and the allowance was 0.000000", lines[1])
        self.assertEqual(data["activeSolvers"], 3)

    def test_with_an_allowance_nothing_is_approved(self):
        rpc = FakeRpc(31337, activeCount=lambda to, *a: [5], allowance=lambda to, *a: [2**255])
        ctx, a = self.ctx(rpc)
        sent = []
        with mock.patch.object(Wallet, "send", side_effect=lambda to, sig, *args, **kw: sent.append(sig) or {}):
            _, lines = v3cli.cmd_pledge(ctx, a)
        self.assertEqual(sent, ["pledge(uint256,uint256)"])
        self.assertIn("allowance unlimited", lines[1])

    def test_a_short_balance_sends_nothing(self):
        rpc = FakeRpc(11155111, activeCount=lambda to, *a: [3], balanceOf=lambda to, *a: [C])
        ctx, a = self.ctx(rpc)
        ctx.keystore, ctx._keystore_secret = "k.json", 5  # a keystore key: Sepolia takes it
        with mock.patch.object(Wallet, "send", side_effect=AssertionError("sent")):
            with self.assertRaises(cli.Fail) as e:
                v3cli.cmd_pledge(ctx, a)
        self.assertIn("holds 1.000000 of the fee coin", str(e.exception))
        self.assertIn("pofctl faucet", str(e.exception))
        self.assertNotIn("circle", str(e.exception).lower())
        self.assertIn("Nothing was sent", str(e.exception))

    def test_the_contracts_refusal_is_named(self):
        data = "0x" + selector("TooFewActiveSolvers(uint256)").hex() + "%064x" % 2
        self.assertIn("TooFewActiveSolvers: pledges are refused while fewer than 3", v3cli.explain(Reverted("x", data)))
        self.assertEqual(v3cli.explain(Reverted("plain", "")), "plain")


class TestStatus(Records):
    def rpc(self) -> FakeRpc:
        solver = crypto.address(CAST_KEY)

        def race_or_panels_submission(to, s):
            if to.lower() == PANELS:
                row = [0] * len(v3.PANELS_SUBMISSION_FIELDS)
                row[v3.PANELS_SUBMISSION_FIELDS.index("bounty")] = 7 * C
                row[v3.PANELS_SUBMISSION_FIELDS.index("status")] = v3.WINDOW
                row[v3.PANELS_SUBMISSION_FIELDS.index("pass")] = True
                return [tuple(row)]
            return [(4, 0, 3, solver, b"\0" * 32, C, 0, 7 * C, 0, 1, False, True, False, b"\0" * 32, b"\0" * 32)]

        rpc = FakeRpc(11155111, reputation=lambda to, *a: [30 * C], openClaims=lambda to, *a: [7 * C],
                      capOf=lambda to, *a: [80 * C], isActive=lambda to, *a: [True], activeCount=lambda to, *a: [2],
                      submission=race_or_panels_submission, owed=lambda to, *a: [250_000])
        opened = "0x" + crypto.keccak256(v3cli.BOOK_EVENTS["ClaimOpened"].encode()).hex()
        closed = "0x" + crypto.keccak256(v3cli.BOOK_EVENTS["ClaimClosed"].encode()).hex()
        who = _word(solver)
        rpc.log_rows = [
            {"address": BOOK, "topics": [opened, "0x%064x" % 8, who], "data": "0x" + "%064x" % (3 * C) * 3},
            {"address": BOOK, "topics": [closed, "0x%064x" % 8, who], "data": "0x" + "%064x" % (3 * C)},
            {"address": BOOK, "topics": [opened, "0x%064x" % 9, who], "data": "0x" + "%064x" % (7 * C) * 3},
            {"address": BOOK, "topics": [opened, "0x%064x" % 10, _word(RACE)], "data": "0x" + "%064x" % C * 3},
        ]
        return rpc

    def test_cap_open_claims_and_the_deposit_refunded(self):
        rpc = self.rpc()
        a = cli.parser().parse_args(["--record", str(self.v3), "status", "--address", crypto.address(CAST_KEY)])
        with mock.patch.object(cli, "Rpc", return_value=rpc), \
                mock.patch.object(keysrc, "key", side_effect=AssertionError("--address needs no key")):
            data, lines = v3cli.cmd_status(cli.Ctx(a), a)
        text = "\n".join(lines)
        self.assertEqual((data["cap"], data["reputation"], data["openClaims"], data["room"]), (80 * C, 30 * C, 7 * C,
                                                                                               73 * C))
        self.assertEqual([c["submission"] for c in data["claims"]], [9])  # 8 closed; 10 is someone else's
        self.assertEqual(data["claims"][0], {"submission": 9, "bounty": 4, "amount": 7 * C, "status": "Window",
                                             "pass": True, "outcome": "Pass"})
        self.assertIn("cap            80.000000 = REP_BASE 50.000000 + 1 x reputation 30.000000", text)
        self.assertIn("open claims    7.000000 in 1 submission(s); room for 73.000000 more", text)
        self.assertIn("submission 9 on bounty 4: 7.000000, Window, passed", text)
        self.assertIn("a fix posts    1.230000: FeesV3's maxDeposit, the meter's worst case for 7 judges", text)
        self.assertIn("the rest is refunded to you after the verdict, pass or fail", text)
        self.assertIn("active solvers 2: pledges refused (at least 3, each active for 26 weeks", text)
        self.assertIn("(the test coin POFTEST, no value; `pofctl faucet`)", text)
        self.assertIn("credit in the race 0.250000", text)
        self.assertEqual((data["checkDeposit"], data["refunded"], data["pledgesOpen"]), (1_230_000, True, False))

    def test_a_flat_judges_fee_is_shown_as_not_refunded(self):
        cfg = (RACE, RACE, 2 * C, 5 * C, 0, 0, 0, 10 * C, 5000, 1000, 1765, 28, 7, 14, 7, 4, 40 * C)
        rpc = FakeRpc(31337, getConfig=lambda to, *a: [cfg])
        a = cli.parser().parse_args(["--record", str(self.v3), "status", "--address", RACE])
        with mock.patch.object(cli, "Rpc", return_value=rpc):
            data, lines = v3cli.cmd_status(cli.Ctx(a), a)
        self.assertEqual((data["checkDeposit"], data["refunded"]), (40 * C, False))
        self.assertIn("a flat judges' fee of 40.000000, not refunded", "\n".join(lines))


FAUCET = "0x" + "fa" * 20


class TestFaucet(Records):
    """`pofctl faucet` (L17 as amended on 2026-11-20): the test coin's keyless faucet, 20 coins a claim, one claim per
    address every 2 hours; the faucet from the record or the coin's `faucet()`; a claim too soon sends nothing."""

    def run_faucet(self, *extra, chain=11155111, record=None, keystore=True, **over):
        answers = {"faucet": lambda to, *a: [FAUCET], "CLAIM_AMOUNT": lambda to, *a: [20 * C],
                   "CLAIM_INTERVAL": lambda to, *a: [7200], "nextClaim": lambda to, *a: [0]}
        answers.update(over)
        rpc = FakeRpc(chain, **answers)
        a = cli.parser().parse_args(["--record", str(record or self.v3), "faucet", *extra])
        with mock.patch.object(cli, "Rpc", return_value=rpc):
            ctx = cli.Ctx(a)
        if keystore:
            ctx.keystore, ctx._keystore_secret = "k.json", CAST_KEY  # a keystore key: Sepolia takes it
        return rpc, ctx, a

    def test_a_claim_for_the_callers_key_and_the_next_time(self):
        claimed = []
        nexts = iter([0, 10_000 + 7200])
        rpc, ctx, a = self.run_faucet(nextClaim=lambda to, who: [next(nexts)])
        with mock.patch.object(Wallet, "send", side_effect=lambda to, sig, *args, **kw: claimed.append((to, sig, args))
                               or {"transactionHash": "0x" + "ee" * 32}):
            data, lines = v3cli.cmd_faucet(ctx, a)
        self.assertEqual(claimed, [(crypto.checksum(FAUCET), "claim()", ())])  # for itself: no recipient argument
        self.assertEqual((data["account"], data["claimed"], data["nextClaim"]), (crypto.address(CAST_KEY), 20 * C,
                                                                                   17_200))
        text = "\n".join(lines)
        self.assertIn(f"claimed 20.000000 test coins from the faucet {crypto.checksum(FAUCET)}", text)
        self.assertIn("next claim     at 1970-01-01 04:46:40 UTC (in 2 h 00 min; 20.000000 coins a claim, one claim "
                      "per address every 2 h)", text)
        self.assertNotIn(hex(CAST_KEY)[2:], text + json.dumps(data))

    def test_a_claim_too_soon_sends_nothing_and_says_when(self):
        rpc, ctx, a = self.run_faucet(nextClaim=lambda to, who: [10_000 + 3_660])
        with mock.patch.object(Wallet, "send", side_effect=AssertionError("sent")) as send:
            with self.assertRaises(cli.Fail) as e:
                v3cli.cmd_faucet(ctx, a)
        msg = str(e.exception)
        self.assertIn("may claim from the faucet", msg)
        self.assertIn("again at 1970-01-01 03:47:40 UTC (in 1 h 01 min)", msg)
        self.assertIn("Nothing was sent", msg)
        send.assert_not_called()

    def test_when_only_shows_the_time(self):
        rpc, ctx, a = self.run_faucet("--when")
        with mock.patch.object(Wallet, "send", side_effect=AssertionError("sent")):
            data, lines = v3cli.cmd_faucet(ctx, a)
        self.assertEqual((data["claimed"], data["nextClaim"]), (0, 10_000))
        self.assertIn("may claim from the faucet", lines[0])
        self.assertIn(" now (20.000000 coins a claim", lines[0])

    def test_the_faucet_is_read_from_the_sepolia_record_and_checked_against_the_coin(self):
        rec = self.dir / "sepolia.json"  # DeploySepolia's record: the race and the faucet under `addresses`
        rec.write_text(json.dumps({"version": 3, "addresses": {"race": RACE, "coin": COIN, "faucet": FAUCET},
                                   "testCoin": {"faucet": FAUCET}}))
        rpc, ctx, a = self.run_faucet("--when", record=rec)
        self.assertEqual(ctx.v3.address, crypto.checksum(RACE))
        self.assertEqual(ctx.v3.faucet(), crypto.checksum(FAUCET))
        rec.write_text(json.dumps({"version": 3, "addresses": {"race": RACE, "faucet": "0x" + "fb" * 20}}))
        rpc, ctx, a = self.run_faucet("--when", record=rec)
        with self.assertRaises(cli.Fail) as e:
            v3cli.cmd_faucet(ctx, a)
        self.assertIn("isn't the coin's", str(e.exception))

    def test_a_coin_without_a_faucet(self):
        def no_faucet(to, *a):
            raise Reverted("execution reverted", "0x")
        rpc, ctx, a = self.run_faucet(faucet=no_faucet)
        with self.assertRaises(cli.Fail) as e:
            v3cli.cmd_faucet(ctx, a)
        self.assertIn("has no faucet", str(e.exception))

    def test_devnet_keys_are_refused_on_sepolia(self):
        os.environ["DEVNET_KEYS"] = "insecure-local"
        rpc, ctx, a = self.run_faucet(keystore=False)
        with mock.patch.object(Wallet, "send", side_effect=AssertionError("sent")), \
                mock.patch.object(keysrc, "key", side_effect=AssertionError("a key was read")):
            with self.assertRaises(cli.Fail) as e:
                v3cli.cmd_faucet(ctx, a)
        self.assertIn("devnet keys", str(e.exception))
        self.assertIn("refused on chain 11155111", str(e.exception))


class TestCommands(Records):
    def test_v3_commands_parse_and_select_v3(self):
        p = cli.parser()
        for argv in (["issue", "register", "--rad-issue", "ab" * 20], ["issue", "open", "--issue", "1"],
                     ["pledge", "--bounty", "1", "--amount", "5"], ["submit", "--bounty", "1", "--patch", "a" * 40],
                     ["claim", "--bounty", "1", "--patch", "a" * 40, "--base", "b" * 40, "--salt", "0x" + "1" * 64],
                     ["merge", "--bounty", "1"], ["checkout"], ["--v3", "status"], ["--v3", "verify-head"],
                     ["verify-delegates"], ["--v3", "verify-delegates", "--rid", "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5"],
                     ["--v3", "withdraw", "--role", "solver"], ["faucet"], ["faucet", "--when"],
                     ["faucet", "--role", "funder"]):
            self.assertTrue(callable(p.parse_args(argv).fn3), argv)

    def test_a_v3_record_selects_v3_and_v2_commands_are_refused_there(self):
        with mock.patch.object(cli, "Rpc", return_value=FakeRpc()):
            ctx = cli.Ctx(cli.parser().parse_args(["--record", str(self.v3), "history"]))
            self.assertEqual((ctx.version, ctx.race), (3, None))
            with self.assertRaises(cli.Fail) as e:
                cli.run(["--record", str(self.v3), "history"])
            self.assertIn("is v2's", str(e.exception))
            with self.assertRaises(cli.Fail):
                cli.run(["--record", str(self.v2), "--v1", "merge", "--bounty", "1"])

    def test_the_patch_carries_the_claim_line_by_line(self):
        from bot import logic

        body = logic.pr_body(3, 2, 9, "0x" + "5" * 64, "0x" + "ab" * 20)
        msgs = v3cli.patch_messages("Fix for bounty 2", body)
        self.assertEqual(msgs[0], "Fix for bounty 2")
        self.assertTrue(all("\n" not in m for m in msgs))  # a push option can't hold a newline
        self.assertEqual(logic.claim("\n\n".join(msgs[1:])), logic.Claim(2, 9, "0x" + "5" * 64, "0x" + "ab" * 20))

    def test_registration_checks_the_radicle_issue_id_first(self):
        with mock.patch.object(cli, "Rpc", return_value=FakeRpc()):
            a = cli.parser().parse_args(["--record", str(self.v3), "issue", "register", "--rad-issue", "not-an-id"])
            with self.assertRaises(cli.Fail) as e:
                v3cli.cmd_register(cli.Ctx(a), a)
        self.assertIn("--rad-issue is the Radicle issue's id", str(e.exception))

    def test_registration_needs_the_whole_issue_id(self):
        """The claim's signature names the Radicle issue (#251 L12, 2026-11-20): a prefix, which `rad` would take, is
        refused before anything is read or sent."""
        with mock.patch.object(cli, "Rpc", return_value=FakeRpc()):
            a = cli.parser().parse_args(["--record", str(self.v3), "issue", "register", "--rad-issue", "ab" * 4])
            with self.assertRaises(cli.Fail) as e:
                v3cli.cmd_register(cli.Ctx(a), a)
        self.assertIn("needs the issue's whole id (40 hex digits", str(e.exception))

    def test_a_fake_rad_records_the_comment(self):
        """`issue register --comment` runs `rad issue comment --repo <RID> <id> --message <claim>`: the stand-in node
        (tests/fake_rad.py) the end-to-end run uses takes exactly that."""
        import subprocess
        import sys

        fake = Path(__file__).resolve().parent / "fake_rad.py"
        with tempfile.TemporaryDirectory() as home:
            out = subprocess.run([sys.executable, str(fake), "issue", "comment", "--repo", "rad:z4Pofctr", "ab" * 20,
                                  "--message", "Registration: 3\nReporter wallet: 0x" + "ab" * 20],
                                 env={**os.environ, "RAD_HOME": home}, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            row = json.loads((Path(home) / "issue-comments.jsonl").read_text())
        self.assertEqual((row["repo"], row["issue"]), ("rad:z4Pofctr", "ab" * 20))
        self.assertIn("Registration: 3", row["body"])


class TestVerifyDelegates(unittest.TestCase):
    """`pofctl --v3 verify-delegates` (#251, L11): the identity's delegates against the seats' nodes on-chain, each
    the key its registration signed (Validators.radNodeOf)."""

    RID = "rad:z3gqcJUoA1n9HaHKufZs5FCSGazv5"

    def setUp(self):
        from types import SimpleNamespace

        from oracle import delegates, radicle

        self.radicle = radicle
        self.seats = [crypto.address(k) for k in (11, 22, 33)]
        self.keys = {s: bytes([i + 1]) * 32 for i, s in enumerate(self.seats)}
        self.dids = {s: delegates.did_from_key(k) for s, k in self.keys.items()}
        chain = SimpleNamespace(repo=lambda: radicle.repo_id(self.RID), seats=lambda: list(self.seats),
                                rad_node_of=lambda k: next((v for s, v in self.keys.items() if s.lower() == k.lower()),
                                                           b"\0" * 32))
        self.ctx = SimpleNamespace(v3=SimpleNamespace(chain=chain, record={"rid": self.RID}))
        self.a = SimpleNamespace(rid=None, rad_exec="")

    def run_it(self, delegates_, threshold):
        cob = {"current": "c" * 40, "revisions": {"c" * 40: {"doc": {"delegates": delegates_, "threshold": threshold}}}}
        with mock.patch.object(self.radicle.Radicle, "identity", return_value=(cob, "", "")):
            return v3cli.cmd_verify_delegates(self.ctx, self.a)

    def test_passes_when_the_delegates_are_the_seats_nodes(self):
        data, lines = self.run_it(sorted(self.dids.values()), 2)
        self.assertTrue(data["match"])
        self.assertEqual(data["seats"], self.dids)  # by seat, as the chain lists them
        self.assertIn("radNodeOf", lines[0])

    def test_a_delegate_that_isnt_a_seats_node_fails(self):
        with self.assertRaises(cli.Fail) as e:
            self.run_it(sorted(self.dids.values()) + ["did:key:z6MkopH5QMoynapxG9Yis4TCpWgyaxQNEBeiL39wqJ2GZCR1"], 3)
        self.assertIn("isn't the Radicle node any seat registered on-chain", str(e.exception))

    def test_a_seat_without_a_node_is_reported_unmapped(self):
        self.keys[self.seats[2]] = b"\0" * 32
        with self.assertRaises(cli.Fail) as e:
            self.run_it([self.dids[s] for s in self.seats[:2]], 2)
        self.assertIn("(unmapped)", str(e.exception))
        self.assertIn("registered no Radicle node key on-chain", str(e.exception))


if __name__ == "__main__":
    unittest.main()
