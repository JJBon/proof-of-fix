"""pofctl (proof-of-fix#104): the ABI, transaction signing, the devnet keys, the v2 signatures and the CLI's guards,
without a chain. The end-to-end run against a devnet is scripts/pofctl-e2e.sh (it needs Docker)."""

import re
import unittest
from pathlib import Path
from unittest import mock

from oracle import crypto
from pofctl import abi, cli, keys, race, tx
from pofctl.rpc import _reason

ROOT = Path(__file__).resolve().parent.parent


class TestAbi(unittest.TestCase):
    def test_selectors(self):
        self.assertEqual(abi.selector("transfer(address,uint256)").hex(), "a9059cbb")
        self.assertEqual(abi.selector("balanceOf(address)").hex(), "70a08231")

    def test_static_encoding(self):
        out = abi.encode(["uint256", "address", "bool"], [1, "0x" + "11" * 20, True])
        self.assertEqual(out.hex(), "%064x" % 1 + "00" * 12 + "11" * 20 + "%064x" % 1)

    def test_dynamic_encoding_matches_solidity(self):
        # abi.encode(uint256(7), bytes("ab")) and a (bytes32,bytes[]) tuple: offsets, lengths and padding.
        self.assertEqual(abi.encode(["uint256", "bytes"], [7, b"ab"]).hex(),
                         "%064x" % 7 + "%064x" % 64 + "%064x" % 2 + "6162" + "00" * 30)
        nonce = b"\x01" * 32
        enc = abi.encode(["(bytes32,bytes[])"], [(nonce, [b"\xaa", b"\xbb\xbb"])])
        words = [enc[i:i + 32].hex() for i in range(0, len(enc), 32)]
        self.assertEqual(int(words[0], 16), 32)  # the tuple is dynamic: an offset
        self.assertEqual(words[1], "01" * 32)  # the nonce in place
        self.assertEqual(int(words[2], 16), 64)  # bytes[]'s offset within the tuple
        self.assertEqual(int(words[3], 16), 2)  # two signatures

    def test_round_trip(self):
        types = ["uint256", "address[]", "(uint8,bool,bytes32)", "string"]
        values = [5, ["0x" + "22" * 20, "0x" + "33" * 20], [3, False, "0x" + "44" * 32], "hello"]
        self.assertEqual(abi.decode(types, abi.encode(types, values)), values)

    def test_call_data(self):
        data = abi.call_data("pledge(uint256,address,uint256)", 1, "0x" + "55" * 20, 2)
        self.assertEqual(data[:4], abi.selector("pledge(uint256,address,uint256)"))
        self.assertEqual(len(data), 4 + 96)

    def test_revert_reasons_read_as_names(self):
        self.assertEqual(_reason("0x" + abi.selector("NotOracle()").hex()), "NotOracle()")
        self.assertEqual(_reason("0x08c379a0" + abi.encode(["string"], ["nope"]).hex()), "nope")
        self.assertTrue(_reason("0xdeadbeef").startswith("reverted"))


class TestTransactions(unittest.TestCase):
    def test_eip155_vector(self):
        # EIP-155's own example: nonce 9, 20 gwei, 21,000 gas, 1 ether to 0x3535…, chain 1, key 0x4646….
        raw = tx.signed_legacy(int("46" * 32, 16), 1, 9, 20 * 10**9, 21_000, "0x" + "35" * 20, 10**18, b"")
        self.assertEqual(raw.hex(), "f86c098504a817c800825208943535353535353535353535353535353535353535880de0b6b3a7"
                                    "6400008025a028ef61340bd939bc2195fe537567866003e1a15d3c71ff63e1590620aa636276a067"
                                    "cbe9d8997f761aecb703304b3800ccf555c9f3dc64214b297fb1966a3b6d83")

    def test_rlp(self):
        self.assertEqual(tx.rlp(b"dog").hex(), "83646f67")
        self.assertEqual(tx.rlp([b"cat", b"dog"]).hex(), "c88363617483646f67")
        self.assertEqual(tx.rlp(0).hex(), "80")
        self.assertEqual(tx.rlp(1024).hex(), "820400")


class TestKeys(unittest.TestCase):
    def test_mnemonic_keys_are_anvils(self):
        self.assertEqual(hex(keys.derive(keys.MNEMONIC, 0)),
                         "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80")
        self.assertEqual(hex(keys.derive(keys.MNEMONIC, 1)),
                         "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d")

    def test_roles_match_devnet_keys_script(self):
        text = (ROOT / "scripts" / "devnet-keys.sh").read_text(encoding="utf-8")
        roles = re.search(r"^ROLES=\(([^)]*)\)", text, re.M).group(1).split()
        oracles = int(re.search(r"^ORACLES=(\d+)", text, re.M).group(1))
        joiners = re.search(r"^ROLES\+=\((joiner[^)]*)\)", text, re.M).group(1).split()
        self.assertEqual(keys.ROLES, roles + [f"oracle-{i}" for i in range(oracles)] + joiners)

    def test_insecure_local_must_be_chosen(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(keys.source(None), "openbao")
            self.assertEqual(keys.source("insecure-local"), "insecure-local")
        with mock.patch.dict("os.environ", {"DEVNET_KEYS": "insecure-local"}):
            self.assertEqual(keys.source("openbao"), "insecure-local")

    def test_env_keys_and_unknown_roles(self):
        with mock.patch.dict("os.environ", {"POFCTL_KEY_SOLVER_A": "0x01"}):
            self.assertEqual(keys.key("solver-a", "env"), 1)
        with self.assertRaises(keys.KeyError_):
            keys.key("nobody", "insecure-local")
        with self.assertRaises(keys.KeyError_):
            keys.key("bot", "somewhere")


class TestV2Signatures(unittest.TestCase):
    def setUp(self):
        self.r = race.Race(rpc=None, record={"race": "0x" + "ab" * 20, "coin": "0x" + "cd" * 20,
                                             "quoter": "0x" + "ef" * 20, "verdicts": "0x" + "12" * 20}, version=2)
        self.r._chain_id = 7193

    def test_domain_is_version_2_and_differs_from_v1(self):
        v1 = race.Race(rpc=None, record=self.r.record, version=1)
        v1._chain_id = 7193
        self.assertEqual(v1.domain(), crypto.domain_separator(7193, self.r.address))  # the node's v1 domain
        self.assertNotEqual(self.r.domain(), v1.domain())
        self.assertEqual(self.r.oracle_set, "0x" + "12" * 20)  # v2's keys live on Verdicts
        self.assertEqual(v1.oracle_set, self.r.address)

    def test_signatures_are_ordered_by_signer_and_recover(self):
        secrets = [keys.derive(keys.MNEMONIC, 9 + i) for i in range(3)]
        nonce, sigs = self.r._signed(race.Signers(secrets), b"\x07" * 32, b"\x01" * 32)
        digest = crypto.keccak256(b"\x19\x01" + self.r.domain() + b"\x07" * 32)
        signers = [crypto.recover(digest, s) for s in sigs]
        self.assertEqual(signers, sorted(signers, key=lambda a: int(a, 16)))
        self.assertEqual(set(signers), {crypto.address(k) for k in secrets})

    def test_commitment_matches_the_node(self):
        fix, salt, solver = race.fix_of("A" * 40), b"\x02" * 32, "0x" + "99" * 20
        self.assertEqual(fix, b"\xaa" * 20 + b"\0" * 12)  # v2: the commit as Heads keeps it (S11)
        self.assertEqual(race.fix_of("A" * 40, version=1), crypto.keccak256(("a" * 40).encode()))
        self.assertEqual(race.commitment(fix, salt, solver), crypto.commitment(fix, salt, solver))

    def test_challenge_upheld_is_the_contract_s_type(self):
        """pofctl oracle uphold-challenge (#152 scenario 5) signs RaceV2's ChallengeUpheld, letter for letter."""
        src = (ROOT / "contracts" / "src" / "v2" / "RaceV2Base.sol").read_text(encoding="utf-8")
        typ = re.search(r'CHALLENGE_UPHELD_TYPEHASH =\s*keccak256\("([^"]+)"\)', src).group(1)
        self.assertEqual(race.CHALLENGE_UPHELD_TYPEHASH, crypto.keccak256(typ.encode()))
        self.assertIn("challengeUpheld(uint256 b, uint256 epoch, Signed calldata auth)",
                      (ROOT / "contracts" / "src" / "v2" / "RaceV2Annex.sol").read_text(encoding="utf-8"))


class TestCli(unittest.TestCase):
    def test_every_command_parses(self):
        p = cli.parser()
        for argv in (["status"], ["coin", "mint", "--to", "funder"], ["reporter", "register"],
                     ["funder", "fund", "--bounty", "1", "--amount", "5"], ["funder", "claim", "--bounty", "1"],
                     ["solver", "quote", "--bounty", "1"], ["solver", "attempt", "--bounty", "1"],
                     ["solver", "submit", "--bounty", "1", "--commit", "a" * 40],
                     ["oracle", "accept", "--issue", "1"], ["oracle", "result", "--submission", "1", "--outcome", "pass"],
                     ["oracle", "merged", "--bounty", "1"], ["validator", "status"],
                     ["bot", "link", "--repo", "a/b", "--issue", "1", "--bounty", "1"],
                     ["bot", "settle", "--bounty", "1"], ["withdraw", "--role", "funder"], ["balances"], ["history"],
                     ["devnet", "warp", "--days", "1"]):
            self.assertTrue(callable(p.parse_args(argv).fn), argv)

    def test_stub_quorum_and_warp_refuse_other_chains(self):
        ctx = mock.Mock()
        ctx.race.chain_id.return_value = 1
        with self.assertRaises(cli.Fail):
            cli.Ctx.devnet_only(ctx, "the stub quorum")
        ctx.race.chain_id.return_value = 7193
        cli.Ctx.devnet_only(ctx, "the stub quorum")

    def test_missing_record_is_a_clear_error(self):
        with self.assertRaises(FileNotFoundError):
            race.load_record(2, "/nonexistent/devnet-v2.json")

    def test_main_prints_errors_not_tracebacks(self):
        with mock.patch.object(cli, "run", side_effect=cli.Fail("boom")), \
                mock.patch("sys.stderr") as err:
            self.assertEqual(cli.main(["status"]), 1)
            self.assertIn("boom", "".join(c.args[0] for c in err.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
