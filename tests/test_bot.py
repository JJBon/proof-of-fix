"""Task 3.3: the bounty bot's pure logic (bot/logic.py), and what keeps the loop local. The loop itself needs Docker:
scripts/bounty-loop.sh."""

import re
import unittest
from pathlib import Path

from bot import logic
from bot.forgejo import Forgejo

ROOT = Path(__file__).resolve().parent.parent
RACE = "0x" + "ab" * 20
WALLET = "0x" + "cd" * 20
SALT = "0x" + "0f" * 32
C = 10**6
CONFIG = logic.Config(registration_fee=2 * C, issue_stake=5 * C, attempt_fee=C // 2, check_deposit=6_600_000,
                      start_bps=5_000, rise_bps_per_day=1_000, finder_fee_bps=1_765)


def labelled(state="open", names=("bounty",)):
    return {"state": state, "labels": [{"name": n} for n in names]}


class TestIssues(unittest.TestCase):
    def test_only_an_open_labelled_issue_with_no_bounty(self):
        self.assertTrue(logic.needs_bounty(labelled(), []))
        self.assertFalse(logic.needs_bounty(labelled(names=("bug",)), []))
        self.assertFalse(logic.needs_bounty(labelled(state="closed"), []))
        linked = [{"body": logic.bounty_comment(RACE, 4, 9)}]
        self.assertFalse(logic.needs_bounty(labelled(), linked))

    def test_the_link_reads_back(self):
        comments = [{"body": "unrelated"}, {"body": logic.bounty_comment(RACE, 4, 9, quote="price 1")}]
        self.assertEqual(logic.linked(comments), (RACE, 4, 9))
        self.assertIsNone(logic.linked([{"body": "no marker"}]))

    def test_wallets(self):
        body = f"text\nReporter wallet: {WALLET}\n"
        self.assertEqual(logic.wallet(body, "Reporter"), WALLET)
        self.assertIsNone(logic.wallet(body, "Solver"))
        self.assertIsNone(logic.wallet("Reporter wallet: 0x12", "Reporter"))


class TestPullRequests(unittest.TestCase):
    def test_a_claim_round_trips(self):
        c = logic.claim(logic.pr_body(1, 4, 7, SALT, WALLET))
        self.assertEqual(c, logic.Claim(4, 7, SALT, WALLET))

    def test_an_incomplete_or_malformed_claim(self):
        self.assertIsNone(logic.claim("Fixes #1\n\nBounty: 4\nSubmission: 7\n"))
        self.assertIsNone(logic.claim(logic.pr_body(1, 4, 7, "0x12", WALLET)))
        self.assertIsNone(logic.claim(logic.pr_body(1, 4, 7, SALT, "nobody")))


class TestOutputs(unittest.TestCase):
    def test_tuple_fields(self):
        self.assertEqual(logic.tuple_fields("(1, 2 [2e0], 0xab)"), ["1", "2", "0xab"])
        self.assertEqual(logic.tuple_fields([1, "0xab"]), ["1", "0xab"])

    def test_script_values(self):
        out = "== Logs ==\n  COIN=0x5F\n  RACE=0xe7\n not=this\n"
        self.assertEqual(logic.script_values(out), {"COIN": "0x5F", "RACE": "0xe7"})


class TestPayouts(unittest.TestCase):
    def test_the_price_rises_then_caps(self):
        self.assertEqual(logic.lock_bps(CONFIG, 0), 5_000)
        self.assertEqual(logic.lock_bps(CONFIG, 2), 7_000)
        self.assertEqual(logic.lock_bps(CONFIG, 9), 10_000)

    def test_the_loop_run_adds_up(self):
        """The numbers the loop ended with (2026-10-30): conserved, and as the contract computed them."""
        start = 1_000 * C
        p = logic.loop_payouts(CONFIG, start, 100 * C, 7_000, 300_000, 2, failed=1)
        self.assertEqual(logic.price(CONFIG, 100 * C, 7_000), 58_308_541)
        self.assertEqual((p["reporter"], p["funder"], p["winner"], p["failed0"], p["infrastructure"], p["oracle"]),
                         (1_010_291_457, 929_400_002, 1_057_208_541, 998_900_000, 3_000_000, 600_000))
        self.assertEqual(sum(p.values()) + p["oracle"], 4 * start)  # two signing oracles


class TestTokens(unittest.TestCase):
    RULES = logic.TokenRules(first_emission=10_000 * C, decay_bps=100, founder_bps=100, founder_periods=208,
                             reporter_bps=1_500, inflation_pct=300)

    def test_emission_decays(self):
        self.assertEqual(logic.emission(self.RULES, 0), 10_000 * C)
        self.assertEqual(logic.emission(self.RULES, 2), 9_801 * C)

    def test_a_lone_close_mints_its_period(self):
        t = logic.lone_close_tokens(self.RULES, 0, 120 * C, 100 * C)
        self.assertEqual((t["founder"], t["reporter"], t["solver"]), (100 * C, 1_485 * C, 8_415 * C))
        self.assertEqual(t["founder"] + t["reporter"] + t["solver"], t["supply"])

    def test_inflation_forfeits_the_reporters_tokens(self):
        t = logic.lone_close_tokens(self.RULES, 0, 301 * C, 100 * C)
        self.assertEqual((t["reporter"], t["solver"]), (0, 9_900 * C))
        self.assertEqual(logic.lone_close_tokens(self.RULES, 0, 300 * C, 100 * C)["reporter"], 1_485 * C)

    def test_the_founders_share_ends(self):
        self.assertEqual(logic.lone_close_tokens(self.RULES, 208, 1, 1)["founder"], 0)


class TestSettling(unittest.TestCase):
    """The bot settles a bounty the day its last instalment is released, so its close is recorded in that period and
    nobody loses tokens to a missed grace window."""

    def test_the_last_release_day(self):
        self.assertEqual(logic.last_release_day(10, 7, 4), 35)  # window ends in release 1; the 4th after starts day 35
        self.assertEqual(logic.last_release_day(14, 7, 4), 42)  # ends on a release day: it counts from that release
        self.assertEqual(logic.last_release_day(0, 7, 1), 7)

    def test_due_from_that_day(self):
        self.assertFalse(logic.due_to_settle(logic.MERGED, 34, 10, 7, 4))
        self.assertTrue(logic.due_to_settle(logic.MERGED, 35, 10, 7, 4))
        self.assertTrue(logic.due_to_settle(logic.MERGED, 40, 10, 7, 4))  # missed a day: it still settles at once

    def test_only_a_merged_bounty(self):
        for state in (0, 1, 2, logic.PAID, 5, 6):  # none, open, won, paid, refunded, unsolved
            self.assertFalse(logic.due_to_settle(state, 100, 10, 7, 4))

    def test_matches_the_contracts_count(self):
        """Race.earned: whole releases since the window's, capped at the instalments; settling needs all of them."""
        for window_end in range(0, 30):
            for today in range(window_end, window_end + 50):
                earned = min(today // 7 - window_end // 7, 4)
                self.assertEqual(logic.due_to_settle(logic.MERGED, today, window_end, 7, 4), earned >= 4)


class TestLocalOnly(unittest.TestCase):
    def test_forgejo_client_is_https_or_loopback_http(self):
        Forgejo("http://127.0.0.1:3300", "u", "p", "t")
        self.assertEqual(Forgejo("https://forge.example.org/", "u", "p", "t").base, "https://forge.example.org")  # #112
        for base in ("http://10.0.0.1:3000", "http://example.org", "ftp://example.org", "forge.example.org"):
            with self.assertRaises(ValueError):
                Forgejo(base, "u", "p", "t")

    def test_forgejo_remote_keeps_the_scheme(self):
        self.assertTrue(Forgejo("https://forge.example.org", "u", "p", "t").remote("o", "r").startswith("https://u:p@forge.example.org/"))
        self.assertTrue(Forgejo("http://127.0.0.1:3300", "u", "p", "t").remote("o", "r").startswith("http://u:p@127.0.0.1:3300/"))

    def test_the_loop_is_pinned_and_offline(self):
        loop = (ROOT / "scripts" / "bounty-loop.sh").read_text(encoding="utf-8")
        contracts = (ROOT / "scripts" / "contracts.sh").read_text(encoding="utf-8")
        foundry = re.search(r'^IMAGE="([^"]+)"', contracts, re.M).group(1)
        self.assertIn(f'FOUNDRY_IMAGE="{foundry}"', loop)  # the same Foundry image as the contract tests
        for image in re.findall(r'^[A-Z_]*IMAGE="([^"]+)"', loop, re.M):
            self.assertRegex(image, r"@sha256:[0-9a-f]{64}$")
        self.assertIn('-p "127.0.0.1:$PORT:3000"', loop)
        self.assertIn("--network none", loop)
        for setting in ("OFFLINE_MODE=true", "DISABLE_REGISTRATION=true", "federation__ENABLED=false"):
            self.assertIn(setting, loop)


class TestDevnet(unittest.TestCase):
    """The private devnet (#93): pinned, local only, mainnet's rules, and keys that never reach a command line."""

    def test_the_devnet_is_pinned_local_and_enforces_eip170(self):
        devnet = (ROOT / "scripts" / "devnet.sh").read_text(encoding="utf-8")
        contracts = (ROOT / "scripts" / "contracts.sh").read_text(encoding="utf-8")
        foundry = re.search(r'^IMAGE="([^"]+)"', contracts, re.M).group(1)
        self.assertIn(f'FOUNDRY_IMAGE="{foundry}"', devnet)  # the same Foundry image as the contract tests
        self.assertIn('-p "127.0.0.1:$PORT:8545"', devnet)  # its RPC on this machine only
        chain_id = int(re.search(r"^CHAIN_ID=(\d+)", devnet, re.M).group(1))
        self.assertNotIn(chain_id, (1, 5, 10, 137, 8453, 42161, 11155111, 17000, 31337))  # no public chain's, nor anvil's default
        self.assertRegex(devnet, r"(?m)^HARDFORK=osaka$")
        self.assertGreater(int(re.search(r"^BLOCK_TIME=(\d+)", devnet, re.M).group(1)), 0)
        for path in ("scripts/devnet.sh", "scripts/bounty-loop.sh", "scripts/oracle-run.sh", "bot/chain.py"):
            self.assertNotIn("disable-code-size-limit", (ROOT / path).read_text(encoding="utf-8"), path)

    def test_insecure_keys_only_when_asked(self):
        keys = (ROOT / "scripts" / "devnet-keys.sh").read_text(encoding="utf-8")
        self.assertIn('if [[ "${DEVNET_KEYS:-}" == insecure-local ]]', keys)
        self.assertIn("PREFIX=proof-of-fix/devnet", keys)
        # a new key goes from the container straight into OpenBao on stdin: never echoed, never on a command line
        self.assertRegex(keys, r"cast wallet new .*\|\s*\n\s*bao kv put .* key=- >/dev/null")

    def test_the_roles_keys_come_from_the_environment(self):
        from unittest import mock
        from bot import loop
        with mock.patch.dict("os.environ", {"LOOP_KEY_SOLVER_A": "0x" + "11" * 32}):
            keys = loop.keys()
        self.assertEqual(keys["solver-a"], "0x" + "11" * 32)
        self.assertEqual(keys["bot"], loop.KEYS["bot"])  # the rest stay anvil's test keys

    def test_a_key_never_reaches_the_docker_command_line(self):
        from unittest import mock
        from bot.chain import Chain
        secret = "0x" + "ab" * 32
        done = mock.Mock(returncode=0, stdout='{"status": "0x1"}', stderr="")
        with mock.patch("bot.chain.subprocess.run", return_value=done) as run:
            Chain("pof-devnet", "7193").send(secret, "0x" + "00" * 20, "f()")
        argv, kwargs = run.call_args[0][0], run.call_args[1]
        self.assertNotIn(secret, " ".join(argv))
        self.assertIn("KEY", argv)
        self.assertEqual(kwargs["env"]["LOOP_PK"], secret)


if __name__ == "__main__":
    unittest.main()
