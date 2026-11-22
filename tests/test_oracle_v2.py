"""The v2 node and protocol (proof-of-fix#104 on #85's contracts): the verdict v2, usage and rotate encodings against the
contracts' sources, the measured usage, keys from the environment, the RPC's API key, and three drawn nodes judging a
submission through the exchange, against a fake chain. No Docker, no chain and no model. The end-to-end run against a
devnet, where the contracts check the signatures, is scripts/demo-e2e.sh."""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from oracle import crypto, v2
from oracle.judge import FakeJudge
from oracle.keys import EnvKeys, LocalDevKeys
from oracle.node_v2 import Exchange, NodeV2
from oracle.receipt import Store
from oracle.rpc import Rpc, auth_headers, split_auth

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "contracts" / "src" / "v2"
RACE = crypto.checksum("0x" + "ab" * 20)
METER = crypto.checksum("0x" + "cd" * 20)
CHAIN = 7193


def _solidity_string(path: Path, constant: str) -> str:
    """The string a contract's constant hashes: keccak256("...") (concatenated across lines)."""
    text = path.read_text(encoding="utf-8")
    m = re.search(constant + r"\s*=\s*keccak256\(\s*((?:\"[^\"]*\"\s*)+)\)", text)
    if m is None:
        raise AssertionError(f"{constant} not found in {path.name}")
    return "".join(re.findall(r"\"([^\"]*)\"", m.group(1)))


class Encodings(unittest.TestCase):
    def test_typehashes_match_the_contracts(self):
        base = SRC / "RaceV2Base.sol"
        for name, mine in (("VERDICT_TYPEHASH", v2.VERDICT_TYPEHASH), ("RESULT_TYPEHASH", v2.RESULT_TYPEHASH),
                           ("MERGED_TYPEHASH", v2.MERGED_TYPEHASH), ("ACCEPT_TYPEHASH", v2.ACCEPT_TYPEHASH),
                           ("FEE_TYPEHASH", v2.FEE_TYPEHASH)):
            self.assertEqual(crypto.keccak256(_solidity_string(base, name).encode()), mine, name)
        self.assertEqual(crypto.keccak256(_solidity_string(SRC / "Fees.sol", "USAGE_TYPEHASH").encode()),
                         v2.USAGE_TYPEHASH)
        self.assertEqual(crypto.keccak256(_solidity_string(SRC / "Verdicts.sol", "ROTATE_TYPEHASH").encode()),
                         v2.ROTATE_TYPEHASH)

    def test_the_domains_are_v2s_and_distinct(self):
        race, fees = v2.race_domain(CHAIN, RACE), v2.fees_domain(CHAIN, RACE)
        self.assertNotEqual(race, fees)
        self.assertNotEqual(race, crypto.domain_separator(CHAIN, RACE))  # v1's "1"
        self.assertEqual(race, v2.domain("proof-of-fix Race", "2", CHAIN, RACE))

    def test_result_and_merged_differ_and_recover(self):
        v = v2.Verdict(v2.ZERO, b"\x01" * 32, v2.commit_word("ab" * 20), 1, 2, v2.PASS, b"\x03" * 32, b"\x04" * 32,
                       b"\x05" * 32)
        dom = v2.race_domain(CHAIN, RACE)
        r, m = v2.result_digest(dom, v), v2.merged_digest(dom, v, 100)
        self.assertNotEqual(r, m)
        self.assertEqual(v2.Verdict.from_json(v.to_json()), v)
        k = [LocalDevKeys(i) for i in range(3)]
        sigs = v2.ordered_signatures(r, [x.sign(r) for x in k])
        signers = [crypto.recover(r, s) for s in sigs]
        self.assertEqual(signers, sorted(signers, key=lambda a: int(a, 16)))

    def test_commit_word(self):
        self.assertEqual(v2.commit_word("AB" * 20), b"\xab" * 20 + b"\0" * 12)
        self.assertEqual(v2.commit_word("cd" * 32), b"\xcd" * 32)
        with self.assertRaises(ValueError):
            v2.commit_word("abc")

    def test_measured_usage(self):
        u = v2.measured_usage("aa" * 32, "p" * 400, "r" * 40, 2.2, 2000, 4096, 3000)
        self.assertEqual((u.input, u.output, u.cached), (100, 10, 0))  # about 4 characters a token (the fake)
        self.assertEqual((u.vcpu_seconds, u.gb_seconds, u.storage_mb), (6, 12, 1))  # 3 s at 2 vCPU and 4 GB
        g = v2.measured_usage("aa" * 32, "p", "r", 0.1, 500, 512, 1, {"input_tokens": 9000, "output_tokens": 700})
        self.assertEqual((g.input, g.output, g.vcpu_seconds, g.gb_seconds), (9000, 700, 1, 1))  # the provider's


class KeysAndRpc(unittest.TestCase):
    def test_env_keys(self):
        k = EnvKeys({"ORACLE_PRIVATE_KEY": "0x" + "11" * 32})
        self.assertEqual(k.address(), crypto.address(int("11" * 32, 16)))
        k.check_chain(7193)
        with self.assertRaises(RuntimeError):
            k.check_chain(1)  # unattested keys: devnets only
        for bad in ({}, {"ORACLE_PRIVATE_KEY": "zz"}, {"ORACLE_PRIVATE_KEY": "0"}):
            with self.assertRaises(RuntimeError):
                EnvKeys(bad)

    def test_rpc_keys_never_in_the_url(self):
        url, basic = split_auth("https://alice:s%40cret@devnet.example/rpc")
        self.assertEqual(url, "https://devnet.example/rpc")
        self.assertEqual(basic, "Basic YWxpY2U6c0BjcmV0")  # alice:s@cret
        rpc = Rpc("https://alice:s3cret@devnet.example")
        self.assertNotIn("s3cret", rpc.url)
        self.assertEqual(auth_headers("t"), {"Authorization": "Bearer t"})
        self.assertEqual(auth_headers("a:b", "Basic"), {"Authorization": "Basic YTpi"})
        self.assertEqual(auth_headers("t", "X-Api-Key"), {"X-Api-Key": "t"})
        self.assertEqual(auth_headers(None), {})


# ---------- three drawn nodes against a fake chain ----------

class FakeChain:
    """RaceV2, Verdicts and the meter, as far as the node reads and writes them: one submission whose drawn judges are
    `judges`; reports and the result are applied when a node's wallet sends them."""

    def __init__(self, judges: list, commitment: bytes, solver: str):
        self.race, self.meter, self.rpc = RACE, METER, None
        self.judges, self.reports_ = judges, []
        self.sub = {"bounty": 1, "day": 0, "solver": solver, "commitment": "0x" + commitment.hex(), "coin": METER,
                    "deposit": 0, "outcome": 0, "fix": "0x" + "00" * 32, "appealed": False,
                    "base": "0x" + "00" * 32, "receipt": "0x" + "00" * 32, "seed": "0x" + "77" * 32}
        self.results: list = []

    def chain_id(self):
        return CHAIN

    def committed(self, from_block, to_block=None):
        return [{"bounty": 1, "submission": 1, "solver": self.sub["solver"], "block": 5}]

    def submission(self, s):
        return dict(self.sub)

    def drawn(self, seed, bounty, submission):
        return list(self.judges), []

    def bounty(self, b):
        return {"issue": 0, "state": 1, "winner": 0}

    def issue(self, i):
        return {"repo": "0x" + "00" * 32, "reporter": "0x" + "00" * 20}

    def profile(self, repo):
        return {"milliVcpus": 2000, "memoryMb": 4096}

    def reports(self, s):
        return list(self.reports_)

    def race_domain(self):
        return v2.race_domain(CHAIN, RACE)

    def fees_domain(self):
        return v2.fees_domain(CHAIN, METER)


class FakeWallet:
    def __init__(self, chain: FakeChain, me: str):
        self.chain, self.me = chain, me

    def send(self, to, signature, *args):
        if signature.startswith("report("):
            s, usage, sig = args
            u = v2.Usage(*usage)
            judge = crypto.recover(v2.usage_digest(self.chain.fees_domain(), s, u), sig)
            assert judge in self.chain.judges and judge not in [r["judge"] for r in self.chain.reports_]
            self.chain.reports_.append({"judge": judge, "usage": u})
        elif signature.startswith("result("):
            verdict, fees, sigs = args
            v = v2.Verdict(*verdict[:5], verdict[6], verdict[7], verdict[8], verdict[9], verdict[5])
            digest = v2.result_digest(self.chain.race_domain(), v, fees)
            signers = [crypto.recover(digest, s) for s in sigs]
            assert signers == sorted(signers, key=lambda a: int(a, 16)) and len(set(signers)) == len(signers)
            assert all(s in self.chain.judges for s in signers) and len(signers) >= 2
            assert len(self.chain.reports_) == len(self.chain.judges)  # every judge reported before the result
            self.chain.sub["outcome"] = v.outcome
            self.chain.results.append((self.me, v, signers))
        return {"logs": []}


class FakeHost:
    def __init__(self, pulls: list):
        self._pulls = pulls

    def pulls(self, state="all"):
        return list(self._pulls)

    def pull(self, n):
        return next(p for p in self._pulls if p["number"] == n)


class ThreeNodes(unittest.TestCase):
    def _nodes(self, tmp: Path, liar: int | None = None):
        from bot import logic

        keys = [LocalDevKeys(i, extra_chain_ids={CHAIN}) for i in range(4)]
        judges = [k.address() for k in keys[:3]]  # the 4th isn't drawn
        solver, salt, sha = crypto.checksum("0x" + "99" * 20), b"\x02" * 32, "ab" * 20
        commitment = crypto.commitment(v2.commit_word(sha), salt, solver)
        chain = FakeChain(judges, commitment, solver)
        (tmp / "src" / sha).mkdir(parents=True)
        host = FakeHost([{"number": 3, "title": "Fix", "body": logic.pr_body(1, 1, 1, "0x" + salt.hex(), solver),
                          "state": "open", "head_sha": sha, "base_sha": "11" * 20, "merged": False}])
        nodes = []
        for i, k in enumerate(keys):
            nodes.append(NodeV2(chain, k, FakeJudge(lie=(i == liar)), host, "demo/median", tmp / "src",
                                Exchange(tmp / "exchange", RACE), Store(tmp / f"receipts-{i}"), 100 * 10**6,
                                runner=lambda argv: (0, "ok", ""), log=lambda m: None,
                                wallet=FakeWallet(chain, k.address())))
        return chain, nodes

    def _run(self, nodes, rounds=20):
        for _ in range(rounds):
            for n in nodes:
                n.tick(0)

    def test_three_drawn_nodes_report_seal_reveal_sign_and_one_relays(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, nodes = self._nodes(Path(tmp))
            self._run(nodes)
            self.assertEqual(len(chain.results), 1)
            relayer, v, signers = chain.results[0]
            self.assertEqual(relayer, min(chain.judges, key=lambda a: int(a, 16)))  # the lowest-addressed agreeing
            self.assertEqual((v.outcome, v.tier, v.base), (v2.PASS, 1, v2.commit_word("11" * 20)))
            self.assertEqual(sorted(signers), sorted(chain.judges))
            self.assertEqual(len(chain.reports_), 3)
            self.assertIn(1, nodes[3].skipped)  # not drawn: it did nothing
            self.assertFalse(nodes[3].exchange.all(1, "seal").get(nodes[3].address.lower()))

    def test_a_dissenting_judge_doesnt_sign_and_the_two_others_decide(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, nodes = self._nodes(Path(tmp), liar=0)
            self._run(nodes)
            self.assertEqual(len(chain.results), 1)
            _, v, signers = chain.results[0]
            self.assertEqual(v.outcome, v2.PASS)
            self.assertEqual(len(signers), 2)
            self.assertNotIn(nodes[0].address, signers)
            self.assertEqual(len(chain.reports_), 3)  # the dissenter reported its usage too: the meter pays it

    def test_a_pull_request_that_doesnt_open_the_seal_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            chain, nodes = self._nodes(Path(tmp))
            chain.sub["commitment"] = "0x" + "00" * 32
            self._run(nodes, rounds=5)
            self.assertEqual((chain.results, chain.reports_), ([], []))


if __name__ == "__main__":
    unittest.main()
