"""Event scans on a public chain (proof-of-fix#312): every Sepolia provider bounds an eth_getLogs range, and the v3 node
crashed at start on Sepolia (`range 12192494 exceeds limit of 10000`) because `Chain.seats()` scanned the registry from
block 0. A fake JSON-RPC node here refuses ranges longer than its limit, with each provider's wording; the real client
(oracle.rpc.Rpc) and the real v3 views (oracle.v3.Chain) run against it. No network; nothing depends on git history."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oracle import __main__ as cli  # noqa: E402
from oracle import abi, v3  # noqa: E402
from oracle.crypto import address, keccak256, word  # noqa: E402
from oracle.rpc import Rpc, RpcError, Unavailable  # noqa: E402

RACE, PANELS, FEES, POOL = (address(n) for n in (101, 102, 103, 104))
REGISTRY, HEADS, COIN = (address(n) for n in (105, 106, 107))
GENESIS, LATER, LEFT = (address(n) for n in (1, 2, 3))
DEPLOY_BLOCK, HEAD = 12_192_376, 12_192_494  # Sepolia v3's deployment, and the block the node crashed at
START = 1_763_800_000  # RaceV3's start: the deploying block's time
REGISTERED_TOPIC = "0x" + keccak256(v3.VALIDATOR_REGISTERED.encode()).hex()
SEATED_TOPIC = "0x" + keccak256(v3.SEATED.encode()).hex()
COMMITTED_TOPIC = "0x" + keccak256(v3.COMMITTED.encode()).hex()
RACE_REGISTERED_TOPIC = "0x" + keccak256(v3.REGISTERED.encode()).hex()

INFURA = "query exceeds limit: range {asked} exceeds limit of {limit}"  # with the limit in it (Infura's form)
NAMELESS = "block range too large"  # no number at all: only halving finds the limit
ALCHEMY = ("Log response size exceeded. You can make eth_getLogs requests with up to a {limit} block range and no "
           "limit on the response size")


def topic(n: int) -> str:
    return "0x" + word(n).hex()


class FakeNode(Rpc):
    """A JSON-RPC node behind a provider that refuses an eth_getLogs range of more than `limit` blocks (`refusal` is
    its message), answering through the real client's `call` (only the HTTP exchange is replaced)."""

    def __init__(self, limit: int = 10_000, refusal: str = INFURA, head: int = HEAD, **kw) -> None:
        super().__init__("https://sepolia.example/", **kw)
        self.limit, self.refusal, self.head = limit, refusal, head
        self.events: list = []  # the chain's logs, in order
        self.drawable: dict = {}
        self.asked: list = []  # (from, to) of each eth_getLogs, refused or not
        self.calls: list = []  # method names

    def emit(self, contract: str, block: int, topics: list, data: bytes = b"") -> None:
        self.events.append({"address": contract.lower(), "blockNumber": hex(block), "topics": topics,
                            "data": "0x" + data.hex(), "logIndex": hex(len(self.events))})
        self.events.sort(key=lambda e: (int(e["blockNumber"], 16), int(e["logIndex"], 16)))

    def register(self, key: str, block: int, drawable: bool = True) -> None:
        self.emit(REGISTRY, block, [REGISTERED_TOPIC, topic(int(key, 16)), topic(0)])
        self.drawable[key.lower()] = drawable

    def _send(self, method: str, body: bytes) -> dict:
        params = json.loads(body)["params"]
        self.calls.append(method)
        if method == "eth_blockNumber":
            return {"result": hex(self.head)}
        if method == "eth_chainId":
            return {"result": hex(11155111)}
        if method == "eth_getBlockByNumber":
            n = int(params[0], 16)
            return {"result": {"number": params[0], "timestamp": hex(START + (n - DEPLOY_BLOCK) * 12)}}
        if method == "eth_getLogs":
            q = params[0]
            lo = int(q["fromBlock"], 16)
            hi = self.head if q["toBlock"] == "latest" else int(q["toBlock"], 16)  # as the node did before #312
            self.asked.append((lo, hi))
            if hi - lo + 1 > self.limit:
                return {"error": {"code": -32005, "message": self.refusal.format(asked=hi - lo, limit=self.limit)}}
            want = q.get("topics") or []
            return {"result": [e for e in self.events if e["address"] == q["address"].lower()
                               and lo <= int(e["blockNumber"], 16) <= hi
                               and all(t is None or (i < len(e["topics"]) and e["topics"][i] == t)
                                       for i, t in enumerate(want))]}
        if method == "eth_call":
            data = bytes.fromhex(params[0]["data"][2:])
            if data[:4] == abi.selector("contracts()"):
                out = abi.encode(["address"] * 6 + ["uint256"], [PANELS, FEES, POOL, REGISTRY, HEADS, COIN, START])
            elif data[:4] == abi.selector("isDrawable(address)"):
                out = abi.encode(["bool"], [self.drawable.get("0x" + data[16:36].hex(), False)])
            else:
                raise AssertionError(f"unexpected view 0x{data[:4].hex()}")
            return {"result": "0x" + out.hex()}
        raise AssertionError(f"unexpected {method}")

    def logs_asked(self) -> int:
        return sum(1 for m in self.calls if m == "eth_getLogs")


class TheCrash(unittest.TestCase):
    """The regression: Sepolia's genesis validator's node, at start (node_v3._radicle -> RadicleSeat.tick ->
    Chain.seats), against Infura's 10,000-block limit. Before #312 `seats()` asked for blocks 0 to 12,192,494 at once
    and the provider's refusal ended the run."""

    def test_seats_with_no_start_given_doesnt_crash_on_a_bounded_provider(self):
        rpc = FakeNode(limit=10_000)
        rpc.register(GENESIS, DEPLOY_BLOCK)
        chain = v3.Chain(rpc, RACE)  # as `pofctl verify-delegates` and the node built it before #312: no start
        self.assertEqual(chain.seats(), [GENESIS])
        self.assertTrue(all(hi - lo + 1 <= 5_000 for lo, hi in rpc.asked))  # ORACLE_LOG_RANGE's default

    def test_from_the_deployments_block_it_takes_one_call(self):
        rpc = FakeNode(limit=10_000)
        rpc.register(GENESIS, DEPLOY_BLOCK)
        chain = v3.Chain(rpc, RACE, first_block=DEPLOY_BLOCK)
        self.assertEqual(chain.seats(), [GENESIS])
        self.assertEqual(rpc.asked, [(DEPLOY_BLOCK, HEAD)])

    def test_the_providers_refusal_reads_as_before(self):
        """What the node printed: the message is the provider's, through the real client's error path."""
        rpc = FakeNode(limit=10_000)
        with self.assertRaisesRegex(RpcError, "range 12192494 exceeds limit of 10000"):
            rpc.call("eth_getLogs", [{"address": REGISTRY, "fromBlock": "0x0", "toBlock": hex(HEAD)}])


class Chunks(unittest.TestCase):
    """`Rpc.logs` splits a long range into chunks of at most `log_range` blocks."""

    def test_a_range_longer_than_the_chunk_is_split_in_order_with_latest_read_once(self):
        rpc = FakeNode(limit=1_000, log_range=1_000)
        for b in (5, 999, 1_000, 1_001, 2_500, 4_321):
            rpc.emit(REGISTRY, b, [REGISTERED_TOPIC])
        rpc.head = 4_500
        got = rpc.logs(REGISTRY, 0, [REGISTERED_TOPIC])
        self.assertEqual([int(e["blockNumber"], 16) for e in got], [5, 999, 1_000, 1_001, 2_500, 4_321])
        self.assertEqual(rpc.asked, [(0, 999), (1_000, 1_999), (2_000, 2_999), (3_000, 3_999), (4_000, 4_500)])
        self.assertEqual(rpc.calls.count("eth_blockNumber"), 1)  # `latest` once: the chunks meet

    def test_an_explicit_end_isnt_read_from_the_chain(self):
        rpc = FakeNode()
        rpc.logs(REGISTRY, 10, None, 20)
        self.assertEqual((rpc.asked, rpc.calls.count("eth_blockNumber")), ([(10, 20)], 0))

    def test_an_empty_range_asks_nothing(self):
        rpc = FakeNode()
        self.assertEqual(rpc.logs(REGISTRY, 30, None, 20), [])
        self.assertEqual(rpc.asked, [])

    def test_the_chunk_is_at_least_a_block(self):
        with self.assertRaises(ValueError):
            Rpc("https://sepolia.example/", log_range=0)


class Adapts(unittest.TestCase):
    """A provider stricter than the chunk: the refused chunk is halved (or cut to the limit the message names), the
    smaller size kept, and nothing is lost or repeated."""

    def scan(self, refusal: str, limit: int) -> FakeNode:
        rpc = FakeNode(limit=limit, refusal=refusal, head=20_000)
        for b in range(0, 20_001, 997):
            rpc.emit(REGISTRY, b, [REGISTERED_TOPIC])
        got = rpc.logs(REGISTRY, 0, [REGISTERED_TOPIC])
        self.assertEqual([int(e["blockNumber"], 16) for e in got], list(range(0, 20_001, 997)))
        served = [(lo, hi) for lo, hi in rpc.asked if hi - lo + 1 <= limit]
        self.assertEqual(served[0][0], 0)
        self.assertTrue(all(b[0] == a[1] + 1 for a, b in zip(served, served[1:])))  # contiguous, none twice
        self.assertEqual(served[-1][1], 20_000)
        self.assertLessEqual(rpc.log_range, limit)
        return rpc

    def test_a_limit_named_in_the_message_is_taken_at_once(self):
        rpc = self.scan(ALCHEMY, 10)
        self.assertEqual(rpc.log_range, 10)
        self.assertEqual(len(rpc.asked) - 2_001, 1)  # one refusal, then 2,001 chunks of 10

    def test_infuras_wording_with_a_stricter_limit(self):
        self.assertEqual(self.scan(INFURA, 1_000).log_range, 1_000)

    def test_a_refusal_with_no_number_halves_until_it_fits(self):
        rpc = self.scan(NAMELESS, 100)
        self.assertEqual(rpc.log_range, 78)  # 5000 -> 2500 -> 1250 -> 625 -> 312 -> 156 -> 78
        self.assertEqual(len(rpc.asked) - len([1 for lo, hi in rpc.asked if hi - lo + 1 <= 100]), 6)

    def test_the_smaller_size_is_kept_for_the_next_scan(self):
        rpc = self.scan(NAMELESS, 100)
        rpc.asked.clear()
        rpc.logs(REGISTRY, 0, [REGISTERED_TOPIC], 1_000)
        self.assertTrue(all(hi - lo + 1 <= 78 for lo, hi in rpc.asked))

    def test_a_refused_single_block_and_other_errors_stand(self):
        rpc = FakeNode(limit=0, refusal=NAMELESS)
        with self.assertRaisesRegex(RpcError, "too large"):
            rpc.logs(REGISTRY, 0, None, 100)
        self.assertEqual(rpc.asked[-1], (0, 0))  # halved down to one block, then refused: bounded
        self.assertLessEqual(len(rpc.asked), 14)
        rpc = FakeNode(limit=10, refusal="invalid params: address")
        with self.assertRaisesRegex(RpcError, "invalid params"):
            rpc.logs(REGISTRY, 0, None, 100)
        self.assertEqual(len(rpc.asked), 1)

    def test_an_unavailable_chain_isnt_mistaken_for_a_range_refusal(self):
        rpc = FakeNode()
        with mock.patch.object(FakeNode, "_send", side_effect=Unavailable("HTTP 502 range")):
            with self.assertRaises(Unavailable):
                rpc.logs(REGISTRY, 0, None, 100)
        self.assertEqual(rpc.log_range, 5_000)


class Seats(unittest.TestCase):
    """`Chain.seats()`, the Radicle delegates: the registry's Registered events from the deployment's block, each block
    read once, `isDrawable` asked every time."""

    def setUp(self):
        self.rpc = FakeNode(limit=50, refusal=NAMELESS, head=DEPLOY_BLOCK + 40_000)  # 1rpc's 50 blocks
        self.rpc.register(GENESIS, DEPLOY_BLOCK)  # far more than 5000 blocks before the head: still a delegate
        self.rpc.register(LEFT, DEPLOY_BLOCK + 12_000)
        self.rpc.register(LATER, DEPLOY_BLOCK + 39_000)
        self.chain = v3.Chain(self.rpc, RACE, first_block=DEPLOY_BLOCK)

    def test_across_a_range_far_longer_than_the_providers_limit(self):
        self.assertEqual(self.chain.seats(), sorted([GENESIS, LEFT, LATER]))
        self.assertTrue(all(lo >= DEPLOY_BLOCK for lo, _ in self.rpc.asked))  # never before the deployment

    def test_the_next_pass_reads_only_the_new_blocks(self):
        self.chain.seats()
        self.rpc.asked.clear()
        self.rpc.head += 3
        self.rpc.register(address(4), self.rpc.head)
        self.assertIn(address(4), self.chain.seats())
        self.assertEqual(self.rpc.asked, [(self.rpc.head - 3 - self.chain.reorg_depth + 1, self.rpc.head)])

    def test_a_validator_that_stops_being_drawable_leaves_and_comes_back(self):
        self.chain.seats()
        self.rpc.drawable[LEFT.lower()] = False
        self.assertNotIn(LEFT, self.chain.seats())
        self.rpc.drawable[LEFT.lower()] = True
        self.assertIn(LEFT, self.chain.seats())

    def test_an_event_in_a_reorganised_block_doesnt_stay(self):
        self.rpc.register(address(5), self.rpc.head - 2)
        self.assertIn(address(5), self.chain.seats())
        self.rpc.events = [e for e in self.rpc.events if int(e["blockNumber"], 16) != self.rpc.head - 2]
        self.rpc.head += 1
        self.assertNotIn(address(5), self.chain.seats())


class SealAndRevealScans(unittest.TestCase):
    """The node's own scans each pass: its seats (Seated, which start each seal and reveal) and the checks it keeps
    (RaceV3's Committed and Registered), over more blocks than the provider allows, never before the deployment."""

    def setUp(self):
        self.rpc = FakeNode(limit=100, refusal=ALCHEMY, head=DEPLOY_BLOCK + 30_000)
        self.me = GENESIS
        for i, b in enumerate((DEPLOY_BLOCK + 10, DEPLOY_BLOCK + 9_000, DEPLOY_BLOCK + 29_999)):
            self.rpc.emit(PANELS, b, [SEATED_TOPIC, topic(i + 1), topic(int(self.me, 16))],
                          abi.encode(["uint256", "uint256"], [0, START + 7200]))
            self.rpc.emit(PANELS, b, [SEATED_TOPIC, topic(i + 50), topic(int(LATER, 16))],
                          abi.encode(["uint256", "uint256"], [1, START + 7200]))
            self.rpc.emit(RACE, b, [COMMITTED_TOPIC, topic(i + 1), topic(i + 10), topic(0)])
            self.rpc.emit(RACE, b + 1, [RACE_REGISTERED_TOPIC, topic(i + 1), topic(0)], abi.encode(["uint256"], [i + 20]))
        self.rpc.emit(PANELS, DEPLOY_BLOCK - 5, [SEATED_TOPIC, topic(99), topic(int(self.me, 16))],
                      abi.encode(["uint256", "uint256"], [0, 0]))  # another deployment's, before this one
        self.chain = v3.Chain(self.rpc, RACE, first_block=DEPLOY_BLOCK)

    def test_seated_committed_and_registered_cover_the_whole_range(self):
        start = cli.run_start(0, self.rpc.head, self.chain.first_block)  # --from-block 0: clamped to the deployment
        self.assertEqual([e["pid"] for e in self.chain.seated(self.me, start)], [1, 2, 3])
        self.assertEqual([e["submission"] for e in self.chain.committed(start)], [10, 11, 12])
        self.assertEqual([e["submission"] for e in self.chain.registered(start)], [20, 21, 22])
        self.assertTrue(all(hi - lo + 1 <= 100 for lo, hi in self.rpc.asked[1:]))
        self.assertTrue(all(lo >= DEPLOY_BLOCK for lo, _ in self.rpc.asked))

    def test_each_pass_asks_for_the_new_blocks_only(self):
        start = DEPLOY_BLOCK
        self.chain.seated(self.me, start)
        before = self.rpc.logs_asked()
        for _ in range(5):  # five passes, a block each
            self.rpc.head += 1
            self.assertEqual(len(self.chain.seated(self.me, start)), 3)
        self.assertEqual(self.rpc.logs_asked() - before, 5)

    def test_an_explicit_range_is_asked_as_it_is(self):
        got = self.chain.seated(self.me, DEPLOY_BLOCK, DEPLOY_BLOCK + 9_000)
        self.assertEqual([e["pid"] for e in got], [1, 2])
        self.assertEqual(self.chain.seated(self.me, DEPLOY_BLOCK + 10, DEPLOY_BLOCK), [])


class TheNodesStart(unittest.TestCase):
    """How the node learns the deployment's first block, and where `run` starts."""

    def test_oracle_from_block_names_it(self):
        chain = v3.Chain(FakeNode(), RACE)
        self.assertEqual(cli.first_block(chain, {"ORACLE_FROM_BLOCK": str(DEPLOY_BLOCK)}, log=lambda m: None),
                         DEPLOY_BLOCK)

    def test_unset_it_is_found_from_the_races_start(self):
        rpc = FakeNode()
        said = []
        found = cli.first_block(v3.Chain(rpc, RACE), {}, log=said.append)
        self.assertEqual(found, DEPLOY_BLOCK - 300)  # an hour of 12-second blocks before RaceV3's start
        self.assertLessEqual(rpc.calls.count("eth_getBlockByNumber"), 25)
        self.assertIn("ORACLE_FROM_BLOCK", said[0])

    def test_a_bad_setting_stops_the_node(self):
        chain = v3.Chain(FakeNode(), RACE)
        for bad in ("12,192,376", "-1", "latest"):
            with self.assertRaises(SystemExit):
                cli.first_block(chain, {"ORACLE_FROM_BLOCK": bad})

    def test_run_never_starts_before_the_deployment(self):
        self.assertEqual(cli.run_start(None, HEAD, DEPLOY_BLOCK), DEPLOY_BLOCK)  # the last 5000 reach before it
        self.assertEqual(cli.run_start(None, DEPLOY_BLOCK + 9_000, DEPLOY_BLOCK), DEPLOY_BLOCK + 4_000)
        self.assertEqual(cli.run_start(0, HEAD, DEPLOY_BLOCK), DEPLOY_BLOCK)
        self.assertEqual(cli.run_start(DEPLOY_BLOCK + 50, HEAD, DEPLOY_BLOCK), DEPLOY_BLOCK + 50)
        self.assertEqual(cli.run_start(None, 100, 0), 0)

    def test_oracle_log_range_sets_the_chunk(self):
        env = {"ORACLE_RPC": "https://sepolia.example/", "ORACLE_LOG_RANGE": "50"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(cli.rpc_from_env().log_range, 50)
        with mock.patch.dict(os.environ, {**env, "ORACLE_LOG_RANGE": ""}, clear=True):
            self.assertEqual(cli.rpc_from_env().log_range, 5_000)
        with mock.patch.dict(os.environ, {**env, "ORACLE_LOG_RANGE": "0"}, clear=True), self.assertRaises(SystemExit):
            cli.rpc_from_env()


class TheKitLetsThemThrough(unittest.TestCase):
    """The measured disk takes both settings from the user data (only the settings it fixes itself are refused)."""

    ROOT = Path(__file__).resolve().parents[1]

    def test_neither_is_one_the_disk_fixes(self):
        sys.path.insert(0, str(self.ROOT / "scripts"))
        import rc_aws

        for line in ("ORACLE_FROM_BLOCK=12192376", "ORACLE_LOG_RANGE=5000"):
            self.assertIsNone(rc_aws.FIXED_RE.match(line))
        node, _, refused = rc_aws.split_user_data("ORACLE_FROM_BLOCK=12192376\nORACLE_LOG_RANGE=5000\n")
        self.assertEqual((node, refused), ({"ORACLE_FROM_BLOCK": "12192376", "ORACLE_LOG_RANGE": "5000"}, []))
        config = (self.ROOT / "validator-kit/sevsnp/disk/rootfs/usr/lib/pof/pof-config.sh").read_text()
        fixed = next(line for line in config.splitlines() if line.startswith("fixed="))
        self.assertNotIn("ORACLE_FROM_BLOCK", fixed)
        self.assertNotIn("ORACLE_LOG_RANGE", fixed)

    def test_the_kit_documents_them(self):
        for doc in ("validator-kit/sevsnp/terraform/variables.tf", "validator-kit/SEVSNP-PLAN.md"):
            text = (self.ROOT / doc).read_text()
            self.assertTrue("ORACLE_FROM_BLOCK" in text, doc)
            self.assertTrue("ORACLE_LOG_RANGE" in text, doc)


if __name__ == "__main__":
    unittest.main()
