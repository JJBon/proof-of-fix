"""The owner's validator on a test rig (#150), for scripts/first-run-e2e.sh: the kit's real watcher code
(validator-kit/lambda/watcher.py) polling the rig's chain once a minute, a fake EC2 whose boot takes as long as a real
start, and then the real node process, with the environment the kit's user data gives it, until it's idle. Its judge is
the real DirectJudge against a small OpenAI-compatible stand-in on loopback, which answers from the prompt's test result
and reports token counts of its own. So everything of the kit's path runs but the instance, Docker around the node and
the model.

    python3 tests/e2e_first_run_owner.py    (the rig's settings in the environment; runs until killed)"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS_IN, TOKENS_OUT = 777, 55  # the stand-in model's usage: unlike any fake judge's estimate, so the books show it


def _watcher():
    spec = importlib.util.spec_from_file_location("pof_validator_watcher", ROOT / "validator-kit" / "lambda" / "watcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Model(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):  # noqa: N802 (http.server's name)
        prompt = self.rfile.read(int(self.headers["Content-Length"])).decode()
        solves = "acceptance test passed" in prompt
        # What a real judge must get (#166): the issue from the host, the diff the node computed itself. For the rig's grep.
        seen = "median() is wrong for an even count" in prompt and "diff --git a/bot/sample/stats.py" in prompt
        print("model: the prompt has the issue and the diff" if seen else "model: the prompt lacks the issue or the diff",
              flush=True)
        answer = {"solves": solves, "probability": 0.9 if solves else 0.1, "constitutional": False, "reason": "stand-in",
                  "evidence": [{"file": "bot/sample/stats.py", "line": 1, "note": "stand-in"}]}
        body = json.dumps({"id": "standin", "model": "standin-model", "choices": [
            {"message": {"content": json.dumps(answer)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": TOKENS_IN, "completion_tokens": TOKENS_OUT}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Ssm:
    class exceptions:
        class ParameterNotFound(Exception):
            pass

    def __init__(self):
        self.value = None

    def get_parameter(self, Name):  # noqa: N803 (boto3's name)
        if self.value is None:
            raise self.exceptions.ParameterNotFound(Name)
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, Name, Value, Type, Overwrite):  # noqa: N803 (boto3's names)
        self.value = Value


class Ec2:
    """A stopped instance: a start takes `boot` seconds, runs one node, and the node's end stops it."""

    def __init__(self, boot: float, node_env: dict, work: Path, log) -> None:
        self.state, self.boot, self.node_env, self.work, self.log = "stopped", boot, node_env, work, log

    def describe_instances(self, InstanceIds):  # noqa: N803 (boto3's name)
        return {"Reservations": [{"Instances": [{"State": {"Name": self.state}}]}]}

    def _set(self, state: str) -> None:
        self.state = state
        (self.work / "state").write_text(state, encoding="utf-8")

    def start_instances(self, InstanceIds):  # noqa: N803 (boto3's name)
        self._set("pending")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        self.log(f"instance: booting ({self.boot:.0f} s)")
        time.sleep(self.boot)
        self._set("running")
        with open(self.work / "node.log", "a", encoding="utf-8") as out:
            code = subprocess.run([sys.executable, "-m", "oracle", "run", "--until-idle", self.node_env["RIG_IDLE"]],
                                  cwd=self.work, env=self.node_env, stdout=out, stderr=subprocess.STDOUT).returncode
        self.log(f"instance: the node exited {code}; stopping")
        self._set("stopping")
        time.sleep(5)
        self._set("stopped")


def main() -> int:
    e = os.environ
    work = Path(e["RIG_WORK"])
    (work / "src").mkdir(parents=True, exist_ok=True)

    def log(line: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {line}", flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    repos = work / "repos.json"
    repos.write_text(json.dumps({"repos": {e["RIG_REPO"]: {"host": "forgejo", "api": e["RIG_FORGE"]}}}), encoding="utf-8")
    node_env = {
        "PATH": e["PATH"], "HOME": str(work), "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1", "RIG_IDLE": e["RIG_IDLE"],
        # As the kit's user data (node-user-data.sh.tftpl): the RPC's key by name, and the relay's URL with no key of its own.
        "ORACLE_RPC": e["RIG_RPC"], "RPC_API_KEY": e["RIG_RPC_AUTH"], "ORACLE_RPC_API_KEY_HEADER": "Basic",
        "ORACLE_EXCHANGE_URL": e["RIG_EXCHANGE"], "ORACLE_RACE": e["RIG_RACE"], "ORACLE_CHAIN_ID": "7193",
        "ORACLE_REPO": e["RIG_REPO"], "ORACLE_REPOS": str(repos), "FORGEJO_TOKEN": e["RIG_REPO_TOKEN"],
        "FORGEJO_USER": e["RIG_REPO_USER"], "ORACLE_KEYS": "env", "ORACLE_PRIVATE_KEY": e["RIG_OWNER_KEY"],
        "ORACLE_SRC_ROOT": str(work / "src"), "ORACLE_RECEIPTS": str(work / "receipts"), "ORACLE_SANDBOX": "cli",
        "ORACLE_JUDGE": "direct:openai:standin-model", "ORACLE_MODEL_ALLOW": "standin-model",
        "ORACLE_MODEL_URL": f"http://127.0.0.1:{server.server_address[1]}", "ORACLE_MAX_TOKENS": "4000",
    }
    watcher = _watcher()
    rpc = watcher.Rpc(e["RIG_RPC"], e["RIG_RPC_AUTH"], "Basic")
    env = {"ENABLED": "true", "STATE_PARAM": "/rig", "RACE_ADDRESS": e["RIG_RACE"], "SEAT_ADDRESS": e["RIG_OWNER_ADDRESS"],
           "INSTANCE_ID": "i-rig", "MAX_BLOCK_RANGE": "2000", "MERGE_POLL_MINUTES": e.get("RIG_MERGE_POLL_MINUTES", "30")}
    ssm, ec2 = Ssm(), Ec2(float(e["RIG_BOOT"]), node_env, work, log)
    poll = float(e.get("RIG_POLL", "60"))
    while True:
        try:
            result = watcher.run(env, rpc, ssm, ec2)
            if result["action"] != "idle":
                log(f"watcher: {json.dumps(result, sort_keys=True)}")
        except OSError as err:
            log(f"watcher: {err.__class__.__name__}")
        time.sleep(poll)


if __name__ == "__main__":
    sys.exit(main())
