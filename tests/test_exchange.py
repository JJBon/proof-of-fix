"""The exchange service and the node's HTTP transport (proof-of-fix#117), against the fake chain of the node's tests:
what the service refuses (forged or undrawn signatures, a reveal that doesn't open its seal, an early or late
message), and three drawn nodes on separate transports (no shared folder) judging through it: all of them, two at
quorum while the third can't reach it, and the service going down mid-round and coming back empty. The service is a
convenience relay, never required: with it down for the whole check the nodes finish over another transport and relay
the result themselves. The end-to-end run
against a devnet, where the contract checks the signatures, is scripts/demo-e2e.sh --exchange http."""

from __future__ import annotations

import socket
import tempfile
import threading
import unittest
from pathlib import Path

from oracle import crypto, v2
from oracle.judge import FakeJudge
from oracle.keys import LocalDevKeys
from oracle.node_v2 import NodeV2
from oracle.receipt import Store
from oracle.transport import (Fanout, FolderExchange, HttpExchange, OnchainExchange, P2pExchange,
                              exchange_from_env)
from exchange.service import Board, Refused, server
from test_oracle_v2 import CHAIN, RACE, FakeChain, FakeHost, FakeWallet

S = 1  # FakeChain's submission


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _setup(recused=()):
    from bot import logic

    keys = [LocalDevKeys(i, extra_chain_ids={CHAIN}) for i in range(4)]
    judges = [k.address() for k in keys[:3]]  # the 4th isn't drawn
    solver, salt, sha = crypto.checksum("0x" + "99" * 20), b"\x02" * 32, "ab" * 20
    chain = FakeChain(judges, crypto.commitment(v2.commit_word(sha), salt, solver), solver)
    if recused:
        chain.drawn = lambda seed, bounty, s: (judges, list(recused))
    host = FakeHost([{"number": 3, "title": "Fix", "body": logic.pr_body(1, 1, 1, "0x" + salt.hex(), solver),
                      "state": "open", "head_sha": sha, "base_sha": "11" * 20, "merged": False}])
    return keys, chain, host, sha


def _seal(k, outcome=v2.PASS, receipt="aa" * 32, salt=b"\x05" * 32):
    seal = crypto.keccak256(bytes.fromhex(receipt) + crypto.word(outcome) + salt + crypto.word(k.address()))
    sealed = {"node": k.address(), "seal": "0x" + seal.hex(), "sig": "0x" + k.sign(crypto.keccak256(seal)).hex()}
    reveal = {"node": k.address(), "outcome": outcome, "receipt": receipt, "salt": "0x" + salt.hex(),
              "sig": "0x" + k.sign(crypto.keccak256(bytes.fromhex(receipt))).hex()}
    return sealed, reveal


class ASlowJudge(unittest.TestCase):
    """#150: an on-demand validator's node takes minutes to start. A seal after the window is lost for good; one inside it
    joins the round, and a round whose judges all sealed moves on at once, so a long window costs nothing then."""

    def round(self, window: float, late_by: float):
        keys, chain, _, _ = _setup()
        clock = Clock()
        board = Board(chain, seal_window=window, reveal_window=600, clock=clock, log=lambda m: None)
        sealed = [_seal(k) for k in keys[:3]]
        board.post(S, "seal", sealed[0][0])
        board.post(S, "seal", sealed[1][0])
        clock.t += late_by
        return board, sealed

    def test_with_the_default_window_the_slow_judges_seal_is_refused(self):
        board, sealed = self.round(60, 240)  # a minute's poll, a boot, the check and the model's answer
        with self.assertRaises(Refused) as e:
            board.post(S, "seal", sealed[2][0])
        self.assertEqual(e.exception.status, 410)
        board.post(S, "reveal", sealed[0][1])  # the two others go on without it
        board.post(S, "reveal", sealed[1][1])
        self.assertEqual(len(board.read(S, "reveal")), 2)

    def test_with_the_devnets_window_it_joins_and_the_reveals_follow_at_once(self):
        board, sealed = self.round(900, 240)
        with self.assertRaises(Refused) as e:
            board.post(S, "reveal", sealed[0][1])  # still waiting for the slow judge
        self.assertEqual(e.exception.status, 425)
        board.post(S, "seal", sealed[2][0])
        for _, reveal in sealed:
            board.post(S, "reveal", reveal)
        self.assertEqual(len(board.read(S, "reveal")), 3)

    def test_with_the_devnets_window_a_judge_that_never_comes_only_costs_the_window(self):
        board, sealed = self.round(900, 901)
        board.post(S, "reveal", sealed[0][1])
        board.post(S, "reveal", sealed[1][1])
        self.assertEqual(len(board.read(S, "reveal")), 2)


class TheBoardRefuses(unittest.TestCase):
    def setUp(self):
        self.keys, self.chain, _, _ = _setup()
        self.clock = Clock()
        self.board = Board(self.chain, seal_window=60, reveal_window=600, clock=self.clock, log=lambda m: None)

    def refused(self, status, kind, body):
        with self.assertRaises(Refused) as e:
            self.board.post(S, kind, body)
        self.assertEqual(e.exception.status, status, e.exception.reason)

    def test_a_forged_signature(self):
        seal, _ = _seal(self.keys[0])
        forged = {**seal, "sig": _seal(self.keys[1])[0]["sig"]}  # signed by another judge's key
        self.refused(403, "seal", forged)
        self.refused(403, "seal", {**seal, "node": self.keys[1].address()})  # another judge's name on it
        self.assertEqual(self.board.read(S, "seal"), {})

    def test_an_undrawn_or_recused_key(self):
        self.refused(403, "seal", _seal(self.keys[3])[0])  # a seat's key, properly signed, not drawn
        keys, chain, _, _ = _setup(recused=[self.keys[2].address()])
        board = Board(chain, clock=self.clock, log=lambda m: None)
        with self.assertRaises(Refused) as e:
            board.post(S, "seal", _seal(keys[2])[0])
        self.assertEqual(e.exception.status, 403)

    def test_a_reveal_that_doesnt_open_its_seal(self):
        for k in self.keys[:3]:
            self.board.post(S, "seal", _seal(k)[0])
        _, changed = _seal(self.keys[0], outcome=v2.FAIL)  # sealed PASS, reveals FAIL
        self.refused(403, "reveal", changed)
        _, other_salt = _seal(self.keys[0], salt=b"\x06" * 32)
        self.refused(403, "reveal", other_salt)
        self.board.post(S, "reveal", _seal(self.keys[0])[1])  # the honest one opens it
        self.assertEqual(list(self.board.read(S, "reveal")), [self.keys[0].address().lower()])

    def test_an_early_reveal_then_on_time(self):
        a, b = (_seal(k) for k in self.keys[:2])
        self.board.post(S, "seal", a[0])
        self.board.post(S, "seal", b[0])
        self.refused(425, "reveal", a[1])  # the third judge may still seal
        self.clock.t += 60  # the seal window closed without it
        self.board.post(S, "reveal", a[1])
        self.refused(410, "seal", _seal(self.keys[2])[0])  # too late to seal now
        self.clock.t += 600
        self.refused(410, "reveal", b[1])  # and the reveal window closed too

    def test_every_seal_closes_the_window_early(self):
        pairs = [_seal(k) for k in self.keys[:3]]
        for seal, _ in pairs:
            self.board.post(S, "seal", seal)
        self.board.post(S, "reveal", pairs[0][1])

    def test_a_reveal_without_a_seal_and_a_changed_seal(self):
        self.refused(424, "reveal", _seal(self.keys[0])[1])
        self.board.post(S, "seal", _seal(self.keys[0])[0])
        self.board.post(S, "seal", _seal(self.keys[0])[0])  # the same again: fine
        self.refused(409, "seal", _seal(self.keys[0], outcome=v2.FAIL)[0])

    def test_a_verdict_signed_for_another_digest(self):
        k = self.keys[0]
        v = v2.Verdict(b"\x01" * 32, b"\x02" * 32, b"\x03" * 32, 1, S, v2.PASS, b"\x04" * 32, b"\x77" * 32,
                       b"\x05" * 32)
        domain = v2.race_domain(CHAIN, RACE)
        good = {"node": k.address(), "verdict": v.to_json(), "sig": "0x" + k.sign(v2.result_digest(domain, v)).hex()}
        self.refused(403, "result", {**good, "sig": "0x" + k.sign(v2.merged_digest(domain, v, 1)).hex()})
        other = v2.Verdict.from_json({**v.to_json(), "submission": 2})
        self.refused(400, "result", {**good, "verdict": other.to_json(),
                                     "sig": "0x" + k.sign(v2.result_digest(domain, other)).hex()})
        self.board.post(S, "result", good)
        self.refused(400, "merged", {**good, "weight": -1})
        self.board.post(S, "merged", {**good, "weight": 5, "sig": "0x" + k.sign(v2.merged_digest(domain, v, 5)).hex()})

    def test_malformed_messages(self):
        seal, _ = _seal(self.keys[0])
        self.refused(400, "seal", {**seal, "extra": 1})
        self.refused(400, "seal", {**seal, "seal": "0x12"})
        self.refused(400, "seal", {"seal": seal["seal"], "sig": seal["sig"]})
        self.refused(404, "vote", seal)

    def test_state_survives_a_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            board = Board(self.chain, clock=self.clock, state=Path(tmp) / "s.jsonl", log=lambda m: None)
            board.post(S, "seal", _seal(self.keys[0])[0])
            again = Board(self.chain, clock=self.clock, state=Path(tmp) / "s.jsonl", log=lambda m: None)
            self.assertEqual(again.read(S, "seal"), board.read(S, "seal"))
            self.assertEqual(again.first_seal, board.first_seal)

    def test_a_submission_expires_after_the_retention_and_the_state_is_compacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "s.jsonl"
            board = Board(self.chain, seal_window=7200, clock=self.clock, state=state, retention=3600,
                          log=lambda m: None)
            board.post(S, "seal", _seal(self.keys[0])[0])
            self.clock.t += 1800
            board.post(S, "seal", _seal(self.keys[1])[0])  # the last message taken: the retention counts from here
            self.clock.t += 1800
            self.assertEqual(len(board.read(S, "seal")), 2)
            self.clock.t += 1800
            self.assertEqual(board.read(S, "seal"), {})  # expired: forgotten, its draw too
            self.assertEqual((board.first_seal, board.last, board._judges), ({}, {}, {}))
            self.assertEqual(len(state.read_text().splitlines()), 2)
            again = Board(self.chain, clock=self.clock, state=state, retention=3600, log=lambda m: None)
            self.assertEqual(again.read(S, "seal"), {})
            self.assertEqual(state.read_text(), "")  # compacted on start


class TheServiceOverHttp(unittest.TestCase):
    def test_size_limit_routes_and_health(self):
        import json
        import urllib.error
        import urllib.request

        keys, chain, _, _ = _setup()
        svc = Service(Board(chain, log=lambda m: None)).start()
        try:
            def call(path, body=None, raw=None):
                data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
                req = urllib.request.Request(svc.url + path, data=data, method="POST" if data else "GET")
                try:
                    with urllib.request.urlopen(req, timeout=5) as r:
                        return r.status, json.loads(r.read())
                except urllib.error.HTTPError as e:
                    return e.code, json.loads(e.read())

            self.assertEqual(call("/healthz"), (200, {"ok": True, "race": RACE.lower()}))
            self.assertEqual(call(f"/v1/{RACE}/{S}/seal", raw=b"x" * (64 * 1024 + 1))[0], 413)
            self.assertEqual(call(f"/v1/{'0x' + '12' * 20}/{S}/seal", _seal(keys[0])[0])[0], 404)  # another race
            self.assertEqual(call(f"/v1/{RACE}/{S}/seal", raw=b"{not json")[0], 400)
            self.assertEqual(call(f"/v1/{RACE}/{S}/seal", _seal(keys[0])[0]), (200, {"ok": True}))
            self.assertEqual(list(call(f"/v1/{RACE}/{S}/seal")[1]), [keys[0].address().lower()])
        finally:
            svc.stop()


class Service:
    """The board behind a real HTTP server on 127.0.0.1, in a thread; stop() and start() keep its port."""

    def __init__(self, board: Board, port: int = 0) -> None:
        self.board, self.port, self.srv = board, port, None

    def start(self, board: Board | None = None) -> "Service":
        self.board = board or self.board
        self.srv = server(self.board, "127.0.0.1", self.port)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


def _dead_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens there now
    return f"http://127.0.0.1:{port}"


class NodesThroughTheService(unittest.TestCase):
    def _nodes(self, tmp: Path, urls, clock: Clock, setup, also=None):
        keys, chain, host, sha = setup
        (tmp / "src" / sha).mkdir(parents=True)
        nodes = []
        for i, k in enumerate(keys[:3]):  # the drawn three, each with its own transport, receipts and log
            ex = HttpExchange(urls[i] if isinstance(urls, list) else urls, RACE, timeout=2, log=lambda m: None)
            if also is not None:
                ex = Fanout([ex, *also()], log=lambda m: None)
            nodes.append(NodeV2(chain, k, FakeJudge(), host, "demo/median", tmp / "src", ex,
                                Store(tmp / f"receipts-{i}"), 100 * 10**6, runner=lambda argv: (0, "ok", ""),
                                clock=clock, round_timeout=60, log=lambda m: None,
                                wallet=FakeWallet(chain, k.address())))
        return chain, nodes

    @staticmethod
    def _run(nodes, rounds=12):
        for _ in range(rounds):
            for n in nodes:
                n.tick(0)

    def test_three_nodes_with_no_shared_folder_decide_and_one_relays(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            setup = _setup()
            svc = Service(Board(setup[1], clock=clock, log=lambda m: None)).start()
            try:
                chain, nodes = self._nodes(Path(tmp), svc.url, clock, setup)
                self._run(nodes)
            finally:
                svc.stop()
            self.assertFalse((Path(tmp) / "exchange").exists())
            self.assertEqual(len(chain.results), 1)
            relayer, v, signers = chain.results[0]
            self.assertEqual(relayer, min(chain.judges, key=lambda a: int(a, 16)))
            self.assertEqual(sorted(signers), sorted(chain.judges))
            self.assertEqual(len(svc.board.read(S, "result")), 3)

    def test_a_relay_at_quorum_when_one_judge_cant_reach_the_service(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            setup = _setup()
            svc = Service(Board(setup[1], seal_window=60, clock=clock, log=lambda m: None)).start()
            try:
                chain, nodes = self._nodes(Path(tmp), [svc.url, svc.url, _dead_url()], clock, setup)
                self._run(nodes, rounds=6)
                self.assertEqual(chain.results, [])  # two sealed; they wait for the third
                self.assertEqual(len(svc.board.read(S, "seal")), 2)
                clock.t += 61  # the round times out (the nodes' 60 s, the service's seal window)
                self._run(nodes, rounds=6)
            finally:
                svc.stop()
            self.assertEqual(len(chain.results), 1)
            _, v, signers = chain.results[0]
            self.assertEqual(v.outcome, v2.PASS)
            self.assertEqual(sorted(signers), sorted(n.address for n in nodes[:2]))

    def test_the_service_down_mid_round_then_back_empty(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            setup = _setup()
            svc = Service(Board(setup[1], clock=clock, log=lambda m: None)).start()
            chain, nodes = self._nodes(Path(tmp), svc.url, clock, setup)
            for _ in range(10):
                for n in nodes:
                    n.tick(0)
                if len(svc.board.read(S, "seal")) == 3:
                    break
            self.assertEqual(len(svc.board.read(S, "seal")), 3)
            svc.stop()  # down after the seals: nothing gets through, nobody gives up
            self._run(nodes, rounds=4)
            self.assertEqual(chain.results, [])
            self.assertTrue(all(n.exchange.down for n in nodes))  # each saw it was down and carries on
            svc.start(Board(chain, clock=clock, log=lambda m: None))  # back, on the same port, with no state
            try:
                self._run(nodes)
            finally:
                svc.stop()
            self.assertEqual(len(chain.results), 1)  # the nodes posted their seals again, then the rest
            relayer, _, signers = chain.results[0]
            self.assertEqual(relayer, min(chain.judges, key=lambda a: int(a, 16)))
            self.assertEqual(len(signers), 3)

    def test_the_service_down_for_the_whole_check_isnt_required(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            setup = _setup()
            other = lambda: [FolderExchange(Path(tmp) / "other", RACE), P2pExchange("t", log=lambda m: None)]  # noqa
            chain, nodes = self._nodes(Path(tmp), _dead_url(), clock, setup, also=other)  # http never answers
            self._run(nodes)
            self.assertEqual(len(chain.results), 1)  # over the other transport; the p2p stub is skipped
            relayer, v, signers = chain.results[0]
            self.assertEqual(relayer, min(chain.judges, key=lambda a: int(a, 16)))  # a node relayed it itself
            self.assertEqual((v.outcome, v.seed), (v2.PASS, v2.b32(chain.sub["seed"])))  # built from chain data
            self.assertEqual(len(signers), 3)

    def test_what_the_service_serves_is_checked_again_by_the_nodes(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as tmp:
            setup = _setup()
            keys, chain = setup[:2]
            board = Board(chain, clock=clock, log=lambda m: None)
            outsider = keys[3]  # a dishonest service slips an undrawn key's seal and a forged reveal in
            seal, reveal = _seal(outsider)
            board.msgs[S] = {"seal": {outsider.address().lower(): {k: seal[k] for k in ("seal", "sig")}},
                             "reveal": {outsider.address().lower(): {k: v for k, v in reveal.items() if k != "node"}}}
            svc = Service(board).start()
            try:
                chain, nodes = self._nodes(Path(tmp), svc.url, clock, setup)
                self._run(nodes)
            finally:
                svc.stop()
            _, _, signers = chain.results[0]
            self.assertEqual(sorted(signers), sorted(chain.judges))


class Transports(unittest.TestCase):
    def test_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsInstance(exchange_from_env({"ORACLE_EXCHANGE": tmp}, RACE), FolderExchange)
        ex = exchange_from_env({"ORACLE_EXCHANGE_URL": "https://eng:key@devnet.example/exchange"}, RACE)
        self.assertIsInstance(ex, HttpExchange)
        self.assertEqual(ex.url, "https://devnet.example/exchange")  # the key isn't in what gets printed
        self.assertTrue(ex.headers["Authorization"].startswith("Basic "))
        same = exchange_from_env({"ORACLE_EXCHANGE_URL": "https://devnet.example/exchange",
                                  "ORACLE_RPC": "https://eng:key@devnet.example/"}, RACE)
        self.assertEqual(same.headers, ex.headers)  # the RPC's own per-engineer key, on the RPC's host
        other = exchange_from_env({"ORACLE_EXCHANGE_URL": "https://elsewhere.example/exchange",
                                   "ORACLE_RPC": "https://eng:key@devnet.example/"}, RACE)
        self.assertEqual(other.headers, {})  # never sent to another host
        token = exchange_from_env({"ORACLE_EXCHANGE_URL": "https://x.example", "ORACLE_EXCHANGE_TOKEN": "eng:key",
                                   "ORACLE_EXCHANGE_API_KEY_HEADER": "Basic"}, RACE)
        self.assertEqual(token.headers, ex.headers)

    def test_the_pluggable_transports(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"ORACLE_EXCHANGE": tmp, "ORACLE_EXCHANGE_URL": "https://devnet.example/exchange"}
            fan = exchange_from_env({**env, "ORACLE_EXCHANGE_TRANSPORT": "http,onchain,p2p,folder"}, RACE)
            self.assertIsInstance(fan, Fanout)
            self.assertEqual([type(x) for x in fan.transports],
                             [HttpExchange, OnchainExchange, P2pExchange, FolderExchange])
            for stub in fan.transports[1:3]:  # task 5.5's, and gossip's: interfaces for now
                with self.assertRaises(NotImplementedError):
                    stub.put(S, "0x" + "11" * 20, "seal", {})
            with self.assertRaises(SystemExit):
                exchange_from_env({"ORACLE_EXCHANGE_TRANSPORT": "carrier-pigeon"}, RACE)
            with self.assertRaises(SystemExit):
                exchange_from_env({"ORACLE_EXCHANGE_TRANSPORT": "http"}, RACE)  # no URL
            fan = Fanout([FolderExchange(Path(tmp), RACE), OnchainExchange(None, log=lambda m: None)],
                         log=lambda m: None)
            fan.put(S, "0x" + "11" * 20, "seal", {"x": 1})  # the stub fails, the folder takes it
            self.assertEqual(fan.all(S, "seal"), {"0x" + "11" * 20: {"x": 1}})

    def test_unreachable_reads_fall_back_and_writes_wait(self):
        ex = HttpExchange(_dead_url(), RACE, timeout=1, log=lambda m: None)
        ex.put(S, "0x" + "11" * 20, "seal", {"seal": "0x00", "sig": "0x00"})
        self.assertEqual(ex.all(S, "seal"), {"0x" + "11" * 20: {"seal": "0x00", "sig": "0x00"}})
        self.assertEqual(len(ex.outbox), 1)


if __name__ == "__main__":
    unittest.main()
