"""The validator kit (proof-of-fix#104): the watcher that starts a validator's node only when there is work, and the
Terraform module's static checks. No network and no AWS: the chain, SSM and EC2 are fakes."""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from oracle import crypto

ROOT = Path(__file__).resolve().parent.parent
KIT = ROOT / "validator-kit"
RACE = "0x" + "ab" * 20


def _load_watcher():
    spec = importlib.util.spec_from_file_location("pof_validator_watcher", KIT / "lambda" / "watcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


watcher = _load_watcher()


def _log(bounty: int, submission: int, solver: str, block: int) -> dict:
    return {"topics": [watcher.COMMITTED_TOPIC, hex(bounty), hex(submission), "0x" + "00" * 12 + solver[2:]],
            "blockNumber": hex(block)}


SEAT = "0x" + "11" * 20
OTHER = ["0x" + "22" * 20, "0x" + "33" * 20, "0x" + "44" * 20]
VERDICTS = "0x" + "ee" * 20


def _w(v) -> str:
    return (v[2:] if isinstance(v, str) else format(v, "x")).rjust(64, "0")


class FakeRpc:
    """The chain: Committed and StateChanged logs, RaceV2's submission(), bounty() and verdicts(), and Verdicts' drawn(),
    answered from `draws` (submission -> its judges; the seat by default) and `outcomes`/`bounties`."""

    def __init__(self, head: int, logs: list, draws: dict | None = None, outcomes: dict | None = None,
                 bounties: dict | None = None, won: list | None = None):
        self.head, self.logs, self.calls = head, logs, []
        self.draws, self.outcomes, self.bounties, self.won = draws or {}, outcomes or {}, bounties or {}, won or []

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getLogs":
            q = params[0]
            assert q["address"] == RACE
            lo, hi = int(q["fromBlock"], 16), int(q["toBlock"], 16)
            if q["topics"] == [watcher.COMMITTED_TOPIC]:
                return [log for log in self.logs if lo <= int(log["blockNumber"], 16) <= hi]
            assert q["topics"] == [watcher.STATE_CHANGED_TOPIC]
            return [{"topics": [watcher.STATE_CHANGED_TOPIC, hex(b)], "data": "0x" + _w(state), "blockNumber": hex(n)}
                    for b, state, n in self.won if lo <= n <= hi]
        if method == "eth_call":
            to, data = params[0]["to"], params[0]["data"]
            sel, args = data[:10], [data[10 + i:74 + i] for i in range(0, len(data) - 10, 64)]
            if sel == watcher.VERDICTS:
                assert to == RACE
                return "0x" + _w(VERDICTS)
            if sel == watcher.SUBMISSION:
                sid = int(args[0], 16)
                words = [0] * 12
                words[6], words[11] = self.outcomes.get(sid, 0), sid + 1000  # the seed
                return "0x" + "".join(_w(x) for x in words)
            if sel == watcher.BOUNTY:
                state, winner = self.bounties.get(int(args[0], 16), (1, 0))
                words = [0] * 14
                words[1], words[8] = state, winner
                return "0x" + "".join(_w(x) for x in words)
            if sel == watcher.DRAWN:
                assert to == VERDICTS and args[3].endswith(RACE[2:])
                sid = int(args[2], 16)
                assert int(args[0], 16) == sid + 1000  # the submission's own seed
                judges = self.draws.get(sid, [SEAT] + OTHER[:2])
                return "0x" + _w(64) + _w(96 + 32 * len(judges)) + _w(len(judges)) + "".join(
                    _w(j) for j in judges) + _w(0)
        raise AssertionError(method)


class ParameterNotFound(Exception):
    pass


class FakeSsm:
    class exceptions:
        ParameterNotFound = ParameterNotFound

    def __init__(self, value=None):
        self.value = value

    def get_parameter(self, Name):
        if self.value is None:
            raise ParameterNotFound(Name)
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, Name, Value, Type, Overwrite):
        self.value = Value


class FakeEc2:
    def __init__(self, state="stopped"):
        self.state, self.started = state, 0

    def describe_instances(self, InstanceIds):
        return {"Reservations": [{"Instances": [{"State": {"Name": self.state}}]}]}

    def start_instances(self, InstanceIds):
        self.started += 1
        self.state = "pending"


ENV = {"ENABLED": "true", "STATE_PARAM": "/pof-validator/last-block", "RACE_ADDRESS": RACE,
       "SEAT_ADDRESS": SEAT, "INSTANCE_ID": "i-0123456789abcdef0", "MAX_BLOCK_RANGE": "50"}
SOLVER = "0x" + "cd" * 20


class WatcherTest(unittest.TestCase):
    def test_topic_is_racev2_committed_event(self):
        self.assertEqual(watcher.COMMITTED_TOPIC,
                         "0x" + crypto.keccak256(b"Committed(uint256,uint256,address)").hex())
        # The event may live in RaceV2 or a contract it inherits (RaceV2Base since #85 task 5.3): search them all.
        source = "".join(p.read_text() for p in sorted((ROOT / "contracts" / "src" / "v2").glob("*.sol")))
        self.assertIn("event Committed(uint256 indexed bounty, uint256 indexed submission, address indexed solver);",
                      source)

    def test_idle_keeps_instance_stopped_and_advances(self):
        rpc, ssm, ec2 = FakeRpc(200, []), FakeSsm("150"), FakeEc2()
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual(result["action"], "idle")
        self.assertEqual((result["from"], result["to"]), (150, 200))
        self.assertEqual(ec2.started, 0)
        self.assertEqual(ssm.value, "200")

    def test_work_starts_the_stopped_instance(self):
        rpc, ssm, ec2 = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150"), FakeEc2("stopped")
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual(result["action"], "started")
        self.assertEqual(result["submissions"], [7])
        self.assertEqual(ec2.started, 1)

    def test_work_while_running_does_not_start_again(self):
        rpc, ssm, ec2 = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150"), FakeEc2("running")
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual(result["action"], "running")
        self.assertEqual(ec2.started, 0)

    def test_first_run_looks_back(self):
        rpc, ssm, ec2 = FakeRpc(500, [_log(1, 3, SOLVER, 420), _log(1, 2, SOLVER, 390)]), FakeSsm(None), FakeEc2()
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual(result["from"], None)
        self.assertEqual(result["submissions"], [3])  # 500 - 100 = 400 onwards; block 390 is too old
        self.assertEqual(json.loads(ssm.value)["last"], 449)  # capped by MAX_BLOCK_RANGE (50 blocks from 400)

    def test_scan_is_capped_and_resumes(self):
        rpc, ssm, ec2 = FakeRpc(1000, [_log(1, 9, SOLVER, 980)]), FakeSsm("100"), FakeEc2()
        first = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual((first["to"], first["submissions"]), (150, []))
        self.assertEqual(ssm.value, "150")

    def test_nothing_new_keeps_state(self):
        rpc, ssm, ec2 = FakeRpc(200, []), FakeSsm("200"), FakeEc2()
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual((result["action"], result["to"]), ("idle", 200))

    def test_kill_switch(self):
        rpc, ssm, ec2 = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150"), FakeEc2()
        result = watcher.run(dict(ENV, ENABLED="false"), rpc, ssm, ec2)
        self.assertEqual(result, {"action": "disabled"})
        self.assertEqual((rpc.calls, ec2.started, ssm.value), ([], 0, "150"))

    def test_an_instance_on_its_way_down_does_not_lose_the_work(self):
        """#150: a submission sealed as the node's idle run ends: the instance is stopping, so it can't be started and
        its node won't see the work. The blocks stay unscanned, and the next minute starts it."""
        rpc = FakeRpc(150, [_log(1, 7, "0x" + "cd" * 20, 120)])
        ssm, ec2 = FakeSsm("100"), FakeEc2("stopping")
        self.assertEqual(watcher.run(ENV, rpc, ssm, ec2)["action"], "stopping")
        self.assertEqual(ssm.value, "100")
        self.assertEqual(ec2.started, 0)
        ec2.state = "stopped"
        self.assertEqual(watcher.run(ENV, rpc, ssm, ec2)["action"], "started")
        self.assertEqual(ec2.started, 1)
        self.assertEqual(json.loads(ssm.value)["last"], 150)

    def test_failed_start_does_not_advance(self):
        class BrokenEc2(FakeEc2):
            def start_instances(self, InstanceIds):
                raise RuntimeError("throttled")

        rpc, ssm = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150")
        with self.assertRaises(RuntimeError):
            watcher.run(ENV, rpc, ssm, BrokenEc2())
        self.assertEqual(ssm.value, "150")  # the same blocks are scanned again next minute

    def test_parsed_fields(self):
        rpc = FakeRpc(10, [_log(4, 11, SOLVER, 9)])
        self.assertEqual(watcher.committed(rpc, RACE, 0, 10),
                         [{"bounty": 4, "submission": 11, "solver": SOLVER, "block": 9}])

    def test_api_key_goes_in_a_header(self):
        rpc = watcher.Rpc("https://chain.example", "secret-key", "X-Api-Key")
        self.assertNotIn("secret-key", rpc.url)
        self.assertEqual(rpc.headers()["X-Api-Key"], "secret-key")
        self.assertEqual(watcher.Rpc("u", "tok", "Authorization").headers()["Authorization"], "Bearer tok")
        basic = watcher.Rpc("u", "alice:k3y").headers()["Authorization"]  # the demo chain's (the default)
        self.assertEqual(basic, "Basic YWxpY2U6azN5")

    def test_selectors_and_topics(self):
        self.assertEqual(watcher.STATE_CHANGED_TOPIC, "0x" + crypto.keccak256(b"StateChanged(uint256,uint8)").hex())
        for name, sig in (("VERDICTS", "verdicts()"), ("SUBMISSION", "submission(uint256)"),
                          ("BOUNTY", "bounty(uint256)"), ("DRAWN", "drawn(bytes32,uint256,uint256,address)")):
            self.assertEqual(getattr(watcher, name), "0x" + crypto.keccak256(sig.encode())[:4].hex(), name)

    def test_not_drawn_keeps_the_node_stopped(self):
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)], draws={7: OTHER})
        ssm, ec2 = FakeSsm("150"), FakeEc2()
        result = watcher.run(ENV, rpc, ssm, ec2)
        self.assertEqual((result["action"], result["submissions"], ec2.started), ("idle", [], 0))
        self.assertEqual(ssm.value, "200")

    def test_only_this_seats_draws_and_only_undecided(self):
        logs = [_log(1, 7, SOLVER, 170), _log(1, 8, SOLVER, 180), _log(1, 9, SOLVER, 190)]
        rpc = FakeRpc(200, logs, draws={8: OTHER}, outcomes={9: 2})  # 8: not drawn; 9: already decided
        result = watcher.run(ENV, rpc, FakeSsm("150"), FakeEc2())
        self.assertEqual((result["action"], result["submissions"]), ("started", [7]))

    def test_a_won_bounty_starts_the_node_until_merged(self):
        rpc = FakeRpc(200, [], bounties={4: (2, 7)}, won=[(4, 2, 190)])
        ssm, ec2 = FakeSsm("150"), FakeEc2()
        first = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0)
        self.assertEqual((first["action"], first["merges"]), ("started", [4]))
        self.assertEqual(json.loads(ssm.value), {"last": 200, "awaiting": {"4": 10_000.0}})
        ec2.state = "stopped"  # the node ran and stopped; the pull request isn't merged yet
        soon = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_060.0)
        self.assertEqual(soon["action"], "idle")  # not again before MERGE_POLL_MINUTES
        later = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0 + 31 * 60)
        self.assertEqual((later["action"], later["merges"]), ("started", [4]))
        rpc.bounties[4] = (3, 7)  # merged
        done = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 20_000.0)
        self.assertEqual(done["action"], "idle")
        self.assertEqual(ssm.value, "200")

    def test_the_fuse_limits_a_days_starts_and_resumes_the_next_day(self):
        """The operator's fuse: past the limit the node isn't started, the draw stays on the list, and the next UTC day
        starts it again."""
        env = {**ENV, "MAX_STARTS_PER_DAY": "2"}
        day = 86_400.0 * 20_000
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("stopped")
        self.assertEqual(watcher.run(env, rpc, ssm, ec2, now=lambda: day + 3_600)["action"], "started")
        self.assertEqual(json.loads(ssm.value)["fuse"]["starts"], 1)
        ec2.state = "stopped"
        self.assertEqual(watcher.run(env, rpc, ssm, ec2, now=lambda: day + 7_200)["action"], "started")
        ec2.state = "stopped"
        tripped = watcher.run(env, rpc, ssm, ec2, now=lambda: day + 10_800)
        self.assertEqual((tripped["action"], ec2.started), ("fuse", 2))
        self.assertEqual((tripped["fuse"]["starts"], tripped["fuse"]["max"]), (2, 2))
        self.assertEqual(ec2.state, "stopped")
        self.assertIn("7", json.loads(ssm.value)["pending"])
        self.assertEqual(json.loads(ssm.value)["pending"]["7"]["starts"], 2)  # a tripped fuse spends none of the draw's starts
        next_day = watcher.run(env, rpc, ssm, ec2, now=lambda: day + 86_400 + 60)
        self.assertEqual((next_day["action"], ec2.started), ("started", 3))
        self.assertEqual(json.loads(ssm.value)["fuse"]["starts"], 1)

    def test_the_fuse_survives_an_idle_run_and_counts_only_the_watchers_starts(self):
        env = {**ENV, "MAX_STARTS_PER_DAY": "1"}
        day = 86_400.0 * 20_000
        rpc, ssm, ec2 = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150"), FakeEc2("running")
        self.assertEqual(watcher.run(env, rpc, ssm, ec2, now=lambda: day)["action"], "running")  # already up: no start used
        self.assertNotIn("fuse", json.loads(ssm.value))
        ec2.state = "stopped"
        self.assertEqual(watcher.run(env, rpc, ssm, ec2, now=lambda: day + 3_600)["action"], "started")
        kept = json.loads(ssm.value)["fuse"]
        ec2.state = "running"
        watcher.run(env, rpc, ssm, ec2, now=lambda: day + 3_660)
        self.assertEqual(json.loads(ssm.value)["fuse"], kept)

    def test_no_limit_set_means_no_fuse(self):
        rpc, ssm, ec2 = FakeRpc(200, [_log(1, 7, SOLVER, 180)]), FakeSsm("150"), FakeEc2("stopped")
        self.assertEqual(watcher.run(ENV, rpc, ssm, ec2)["action"], "started")
        self.assertNotIn("fuse", json.loads(ssm.value))

    def test_a_draw_the_node_didnt_finish_starts_it_again_until_decided(self):
        """#166: the node stopped without finishing (it can't say so): the blocks are past, the draw isn't lost."""
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("stopped")
        first = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0)
        self.assertEqual((first["action"], first["submissions"], ec2.started), ("started", [7], 1))
        self.assertEqual(json.loads(ssm.value), {"last": 200, "pending": {"7": {"started": 10_000.0, "starts": 1}}})
        ec2.state = "stopped"  # the run ended; the scan has moved past its block
        soon = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_060.0)
        self.assertEqual((soon["action"], ec2.started), ("idle", 1))  # not again before PENDING_POLL_MINUTES
        later = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0 + 31 * 60)
        self.assertEqual((later["action"], later["retries"], later["submissions"], ec2.started),
                         ("started", [7], [], 2))
        rpc.outcomes[7] = 2  # decided, by this node or the other judges
        ec2.state = "stopped"
        done = watcher.run(ENV, rpc, ssm, ec2, now=lambda: 20_000.0)
        self.assertEqual((done["action"], ec2.started, ssm.value), ("idle", 2, "200"))

    def test_an_undecided_draw_stops_starting_the_node_after_the_limit(self):
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("stopped")
        env = {**ENV, "PENDING_MAX_STARTS": "2", "PENDING_POLL_MINUTES": "1"}
        results = []
        for minute in range(5):
            ec2.state = "stopped"
            results.append(watcher.run(env, rpc, ssm, ec2, now=lambda m=minute: 10_000.0 + m * 61))
        self.assertEqual(ec2.started, 2)
        self.assertEqual(results[2]["gave_up"], [7])
        self.assertEqual(ssm.value, "200")

    def test_a_running_node_doesnt_use_up_a_draws_starts(self):
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("running")
        watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0)
        self.assertEqual(json.loads(ssm.value)["pending"]["7"], {"started": 10_000.0, "starts": 0})

    def test_a_chain_thats_down_spends_no_starts_and_moves_nothing(self):
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("stopped")
        watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0)
        saved = ssm.value

        class Down:
            def call(self, method, params):
                raise OSError("502")

        with self.assertRaises(OSError):
            watcher.run(ENV, Down(), ssm, ec2, now=lambda: 90_000.0)
        self.assertEqual((ssm.value, ec2.started), (saved, 1))

    def test_a_going_down_instance_saves_nothing_for_a_retried_draw(self):
        rpc = FakeRpc(200, [_log(1, 7, SOLVER, 180)])
        ssm, ec2 = FakeSsm("150"), FakeEc2("stopped")
        watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0)
        saved, ec2.state = ssm.value, "stopping"
        watcher.run(ENV, rpc, ssm, ec2, now=lambda: 10_000.0 + 31 * 60)
        self.assertEqual((ssm.value, ec2.started), (saved, 1))

    def test_a_won_bounty_judged_by_others_is_ignored(self):
        rpc = FakeRpc(200, [], draws={7: OTHER}, bounties={4: (2, 7)}, won=[(4, 2, 190)])
        ssm, ec2 = FakeSsm("150"), FakeEc2()
        self.assertEqual(watcher.run(ENV, rpc, ssm, ec2)["action"], "idle")
        self.assertEqual(ssm.value, "200")


class ModuleTest(unittest.TestCase):
    def test_no_secrets_or_keys_in_the_module(self):
        for path in (KIT / "terraform").glob("*.tf*"):
            text = path.read_text()
            self.assertNotIn("aws_secretsmanager_secret_version", text, path.name)  # the operator writes the key
            self.assertNotIn("PRIVATE KEY", text, path.name)

    def test_node_image_must_be_pinned(self):
        self.assertIn('@sha256:[0-9a-f]{64}$', (KIT / "terraform" / "variables.tf").read_text())

    def test_no_ingress_and_no_nat(self):
        network = (KIT / "terraform" / "network.tf").read_text()
        self.assertNotIn("ingress_rule", network)
        self.assertNotIn("aws_nat_gateway", network)

    def test_user_data_gets_every_template_variable(self):
        """Every ${name} in the node's user data is passed by node.tf's templatefile call, and nothing else."""
        import re

        tpl = (KIT / "terraform" / "node-user-data.sh.tftpl").read_text()
        node = (KIT / "terraform" / "node.tf").read_text()
        call = node[node.index("templatefile("):]
        call = call[:call.index("})")]
        passed = set(re.findall(r"^\s+(\w+)\s+=", call, re.M))
        self.assertEqual(set(re.findall(r"\$\{(\w+)\}", tpl)), passed)

    def test_the_judge_calls_its_model_directly(self):
        """#118: the node gets ORACLE_JUDGE (direct:<provider>:<model>, or fake without a model), the allowlist that
        mirrors the IAM policy, and the spending guards; Bedrock's IAM grant is the listed ARNs only."""
        tpl = (KIT / "terraform" / "node-user-data.sh.tftpl").read_text()
        for env in ("ORACLE_JUDGE='${oracle_judge}'", "ORACLE_MODEL_ALLOW='${model_allow}'",
                    "ORACLE_MAX_TOKENS=${max_output_tokens}", "ORACLE_MAX_CALLS=${max_model_calls}",
                    "ORACLE_MAX_RUN_TOKENS=${max_run_tokens}", "-e MODEL_API_KEY"):
            self.assertIn(env, tpl)
        self.assertNotIn("ORACLE_MODEL_PROVIDER", tpl)
        node = (KIT / "terraform" / "node.tf").read_text()
        self.assertIn('oracle_judge    = var.model_id == "" ? "fake" : "direct:${local.direct_provider}:${var.model_id}"',
                      node)
        self.assertIn('actions   = ["bedrock:InvokeModel", "bedrock:Converse"]\n      resources = var.bedrock_model_arns',
                      node)

    def test_the_exchange_url_reaches_the_node(self):
        """#150: exchange_url becomes ORACLE_EXCHANGE_URL, HTTPS with no user info. No other secret: on the RPC's host the
        node reuses RPC_API_KEY, sent as the RPC's header says, and no key goes to another host."""
        from oracle.transport import _http_from_env

        args = _run_user_data("forgejo", exchange_url="https://chain.example/exchange")[0]
        self.assertIn("ORACLE_EXCHANGE_URL=https://chain.example/exchange", args)
        self.assertNotIn("ORACLE_EXCHANGE_TOKEN", " ".join(args))
        self.assertNotIn("ORACLE_EXCHANGE_TRANSPORT", " ".join(args))  # http: the default with a URL
        variables = (KIT / "terraform" / "variables.tf").read_text()
        rule = variables[variables.index('variable "exchange_url"'):variables.index('variable "race_address"')]
        self.assertIn('condition     = var.exchange_url == "" || can(regex("^https://[A-Za-z0-9.-]+', rule)

        env = {"ORACLE_RPC": "https://chain.example", "RPC_API_KEY": "me:s3cret", "ORACLE_RPC_API_KEY_HEADER": "Basic",
               "ORACLE_EXCHANGE_URL": "https://chain.example/exchange"}
        import base64

        same = _http_from_env(env, RACE, print)
        self.assertEqual(same.url, "https://chain.example/exchange")
        self.assertEqual(same.headers["Authorization"], "Basic " + base64.b64encode(b"me:s3cret").decode())
        other = _http_from_env({**env, "ORACLE_EXCHANGE_URL": "https://elsewhere.example/exchange"}, RACE, print)
        self.assertNotIn("Authorization", other.headers)

    def test_forgejo_target_wiring(self):
        """#112: forge = "forgejo" gives the node bot/forge.py's repos.json (the repository on forge_url) and the token
        as FORGEJO_TOKEN with FORGEJO_USER; GitHub (the default) is unchanged."""
        variables = (KIT / "terraform" / "variables.tf").read_text()
        self.assertIn('variable "forge" {\n  description', variables)
        self.assertIn('default     = "github"', variables)
        self.assertIn('^https://[A-Za-z0-9.-]+', variables)
        node = (KIT / "terraform" / "node.tf").read_text()
        self.assertIn('jsonencode({ repos = { (var.repository) = { host = "forgejo", api = var.forge_url } } })', node)

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_user_data_run_passes_the_forges_env(self):
        """The node's run script, rendered as Terraform would and run with stub aws/docker: which env reaches the
        node's container for each forge, and the token never on docker's command line."""
        for forge in ("github", "forgejo"):
            with self.subTest(forge=forge):
                args, env, repos = _run_user_data(forge)
                self.assertNotIn("s3cret-repo-token", "\n".join(args))
                self.assertIn("-e\nGITHUB_TOKEN", "\n".join(args))  # by name only, as before
                if forge == "github":
                    self.assertEqual((env["GITHUB_TOKEN"], env["FORGEJO_TOKEN"]), ("s3cret-repo-token", ""))
                    self.assertFalse(any(a.startswith(("ORACLE_REPOS", "FORGEJO_USER")) for a in args))
                    self.assertIsNone(repos)
                else:
                    self.assertEqual((env["GITHUB_TOKEN"], env["FORGEJO_TOKEN"]), ("", "s3cret-repo-token"))
                    for a in ("ORACLE_REPOS=/etc/pof-validator/repos.json", "FORGEJO_USER=pof-validator-bot",
                              "/etc/pof-validator/repos.json:/etc/pof-validator/repos.json:ro", "FORGEJO_TOKEN"):
                        self.assertIn(a, args)
                    self.assertEqual(repos, {"repos": {"acme/sandbox": {"host": "forgejo",
                                                                        "api": "https://git.example.com"}}})
                self.assertIn("ORACLE_REPO=acme/sandbox", args)

    def test_a_private_ecr_image_gets_a_login_and_only_its_repository(self):
        node = (KIT / "terraform" / "node.tf").read_text()
        self.assertIn('actions   = ["ecr:GetAuthorizationToken"]', node)
        self.assertIn('actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]', node)
        self.assertIn("resources = [local.ecr_repository]", node)
        self.assertEqual(node.count('for_each = local.ecr_registry != "" ? [1] : []'), 2)  # no ECR image: no permission

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_the_run_logs_in_to_ecr_before_pulling_and_only_for_ecr(self):
        import re
        import tempfile

        tpl = (KIT / "terraform" / "node-user-data.sh.tftpl").read_text()
        block = re.search(r"(if \[ -n '\$\{ecr_registry\}' \].*?\nfi\n)docker pull", tpl, re.S).group(1)
        for registry, expected in (("111111111111.dkr.ecr.us-east-1.amazonaws.com", ["ecr", "login"]), ("", [])):
            with self.subTest(registry=registry), tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp) / "log"
                for name, tag in (("aws", "ecr"), ("docker", "login")):
                    stub = Path(tmp) / name
                    stub.write_text(f'#!/bin/bash\necho {tag} >> {log}\necho "$*" >> {log}.args\ncat >/dev/null\n')
                    stub.chmod(0o755)
                script = block.replace("${ecr_registry}", registry).replace("${ecr_region}", "us-east-1")
                subprocess.run(["bash", "-c", script], check=True, env={"PATH": f"{tmp}:/usr/bin:/bin"}, stdin=subprocess.DEVNULL)
                # Sorted: aws | docker is a pipeline, so the two start together and either may log first.
                self.assertEqual(sorted(log.read_text().split()) if log.exists() else [], expected)
                if registry:
                    self.assertIn("--password-stdin", (Path(str(log) + ".args")).read_text())

    def test_the_fuse_reaches_the_watcher(self):
        text = (KIT / "terraform" / "watcher.tf").read_text()
        self.assertIn("MAX_STARTS_PER_DAY     = tostring(var.max_starts_per_day)", text)

    def test_the_budget_stop_denies_spending_and_touches_only_the_kits_roles(self):
        main = (KIT / "terraform" / "main.tf").read_text()
        block = main[main.index('data "aws_iam_policy_document" "budget_stop"'):]
        stop = block[:block.index("\n}\n")]
        for action in ("bedrock:InvokeModel", "bedrock:Converse", "ec2:StartInstances"):
            self.assertIn(f'"{action}"', stop)
        self.assertIn('effect    = "Deny"', stop)
        self.assertIn("resources = [aws_iam_role.node.arn, aws_iam_role.watcher.arn]", main)
        self.assertIn('values   = [aws_iam_policy.budget_stop[0].arn]', main)
        self.assertIn('approval_model     = "AUTOMATIC"', main)

    def test_apply_does_not_stop_the_node_during_its_install(self):
        """#150: aws_ec2_instance_state stopped the instance seconds after creating it. cloud-init had started its one run
        of the user data, so the install never finished, and every later boot came up with no service and no power-off."""
        self.assertNotIn('resource "aws_ec2_instance_state"', (KIT / "terraform" / "node.tf").read_text())

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_the_first_boot_installs_then_powers_off_without_clearing_the_marker(self):
        calls = _run_first_boot(dnf_status=0)
        self.assertEqual(calls.count("systemctl poweroff"), 1)
        self.assertIn("systemctl enable pof-validator.service", calls)
        self.assertFalse([c for c in calls if c.startswith("rm ")], calls)

    @unittest.skipUnless(shutil.which("bash"), "no bash")
    def test_a_failed_install_powers_off_and_clears_the_marker_for_the_next_boot(self):
        calls = _run_first_boot(dnf_status=1)
        self.assertEqual(calls.count("systemctl poweroff"), 1)
        self.assertIn("rm -f /var/lib/cloud/instance/sem/config_scripts_user", calls)
        self.assertNotIn("systemctl enable pof-validator.service", calls)

    @unittest.skipUnless(shutil.which("tofu"), "OpenTofu not installed (the CI runner has none)")
    def test_tofu_fmt(self):
        subprocess.run(["tofu", "fmt", "-check", "-recursive"], cwd=KIT / "terraform", check=True)


def _render_user_data(values: dict) -> str:
    """The user data as Terraform's templatefile renders it: ${name} substituted, $${ left as ${ (the template has no
    %{ } directives, so this is the whole of it)."""
    import re

    tpl = (KIT / "terraform" / "node-user-data.sh.tftpl").read_text()
    assert "%{" not in tpl
    out = re.sub(r"(?<!\$)\$\{(\w+)\}", lambda m: str(values[m.group(1)]), tpl)
    return out.replace("$${", "${")


def _user_data_values(forge: str, exchange_url: str = "") -> dict:
    forgejo = forge == "forgejo"
    repos = json.dumps({"repos": {"acme/sandbox": {"host": "forgejo", "api": "https://git.example.com"}}})
    return dict(region="us-east-1", node_image="registry.example/pof@sha256:" + "0" * 64, node_command='"run"',
                max_run_minutes=55, log_group="/pof-validator/node", rpc_url="https://chain.example",
                rpc_api_key_secret_arn="", rpc_api_key_header="Basic", repo_token_secret_arn="arn:repo-token",
                race_address=RACE, chain_id=7193, repository="acme/sandbox", validator_key_secret="arn:signing-key",
                oracle_judge="fake", model_allow="", model_api_url="", model_api_secret_arn="",
                max_output_tokens=4000, max_model_calls=20, max_run_tokens=500000, forge=forge,
                forge_repos_json=repos if forgejo else "", repo_token_user="pof-validator-bot" if forgejo else "",
                ecr_registry="", ecr_region="", exchange_url=exchange_url)


def _run_first_boot(dnf_status: int) -> list:
    """Runs the whole rendered user data as the first boot does, with its host paths under a temporary directory and
    stubs for what would change the host: the commands it ran, in order."""
    import tempfile

    rendered = _render_user_data(_user_data_values("forgejo"))
    with tempfile.TemporaryDirectory() as tmp:
        bin_, root, log = Path(tmp) / "bin", Path(tmp) / "root", Path(tmp) / "log"
        bin_.mkdir()
        for sub_dir in ("etc/pof-validator", "etc/systemd/system", "usr/local/bin"):
            (root / sub_dir).mkdir(parents=True)
        for name in ("systemctl", "install", "rm", "dnf"):
            status = dnf_status if name == "dnf" else 0
            (bin_ / name).write_text(f'#!/bin/bash\necho "{name} $*" >> {log}\nexit {status}\n')
            (bin_ / name).chmod(0o755)
        script = rendered.replace("> /etc/", f"> {root}/etc/").replace("> /usr/local/bin/", f"> {root}/usr/local/bin/")
        script = script.replace("chmod 0644 /etc/", f"chmod 0644 {root}/etc/").replace("chmod 0700 /usr/", f"chmod 0700 {root}/usr/")
        subprocess.run(["bash", "-c", script], env={"PATH": f"{bin_}:/usr/bin:/bin", "HOME": tmp},
                       stdin=subprocess.DEVNULL, capture_output=True)
        return log.read_text().splitlines()


def _run_user_data(forge: str, exchange_url: str = ""):
    """Runs the rendered run script (pof-validator-run) with stubs for aws, docker, timeout, stat and systemctl: the
    arguments docker run got, the tokens in its environment, and the repos.json the install step writes (or None)."""
    import os
    import re
    import tempfile

    forgejo = forge == "forgejo"
    rendered = _render_user_data(_user_data_values(forge, exchange_url))
    run = re.search(r"<<'RUN'\n(.*?)\nRUN\n", rendered, re.S).group(1)
    written = re.search(r"<<'JSON'\n(.*?)\nJSON\n", rendered, re.S).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        bin_, out = Path(tmp) / "bin", Path(tmp) / "out"
        bin_.mkdir()
        stubs = {
            "aws": 'case "$*" in *arn:repo-token*) echo s3cret-repo-token;; *) echo 0x01;; esac',
            "docker": f'[ "$1" = run ] || exit 0; printf "%s\\n" "$@" > {out}/args; '
                      f'printf "GITHUB_TOKEN=%s\\nFORGEJO_TOKEN=%s\\n" "$GITHUB_TOKEN" "$FORGEJO_TOKEN" > {out}/env',
            "timeout": 'shift 2; exec "$@"', "stat": "echo 999", "systemctl": "exit 0",
        }
        out.mkdir()
        for name, body in stubs.items():
            (bin_ / name).write_text("#!/bin/bash\n" + body + "\n")
            (bin_ / name).chmod(0o755)
        env = {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": tmp}
        subprocess.run(["bash", "-n", "-c", rendered], check=True, env=env)
        subprocess.run(["bash", "-c", run], check=True, env=env, capture_output=True)
        args = (out / "args").read_text().splitlines()
        tokens = dict(line.split("=", 1) for line in (out / "env").read_text().splitlines())
    return args, tokens, (json.loads(written) if forgejo else None)


if __name__ == "__main__":
    unittest.main()
