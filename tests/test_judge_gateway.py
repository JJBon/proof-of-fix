"""proof-of-fix#160: the paid path, proved without paying. A stub of the owner's model gateway on localhost speaks both
routes (Anthropic Messages at /v1/messages, chat completions at /v1/chat/completions), and the real CLI,
`scripts/judge_run.py run-v2 --execute`, runs against it in a subprocess with its real HTTP client and token helper
call, on a tiny test plan with a test approval hash. Nothing leaves localhost and no model is called.

Covered: the headers and caller identity, the routes and request bodies; 429 and 5xx retried with back-off; a
timeout; malformed and incomplete answers (recorded as invalid verdicts); the --max-usd stop; a run killed partway
and resumed; stage 0 first, and a stage-0 failure stopping everything; a wrong approval refusing to start."""

import hashlib
import http.server
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pof.judges import plan as PL
from pof.judges import prereg as PR
from pof.judges import prompt as P

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "judge_run.py"
TOKEN = "tok-pof-judges-models"
DIFF = """diff --git a/pkg/mod.py b/pkg/mod.py
--- a/pkg/mod.py
+++ b/pkg/mod.py
@@ -10,3 +10,3 @@ def f(x):
     if x:
-        return 1
+        return 2
     return 0
"""


def load_run():
    spec = importlib.util.spec_from_file_location("judge_run_for_gateway_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUN = load_run()


def tiny_sets() -> dict:
    def case(cid, label, **extra):
        return {"id": cid, "instance": cid.split(":")[0], "repo": "example/example", "base_commit": "0" * 40,
                "label": label, "source": "test", "size": "small", "issue": f"Issue of {cid}.",
                "commit": "Fix the issue described above.", "diff": DIFF, "context": [], **extra}
    return {"v1": [case("t__t-1:good", "good"), case("t__t-1:bad", "bad")],
            "more": [case("t__t-2:good", "good"), case("t__t-2:bad", "bad")],
            "pbw": [case("t__t-3:pbw:X", "bad", arm="pbw", primary=True, solver_family="anthropic")]}


SETS = tiny_sets()
PLAN = PR.make_plan(SETS, ("B", "2 seats"))
SEATS = PR.all_seats(tuple(PR.H3_SEATS))
BY_MODEL = {s.model: name for name, s in SEATS.items()}
CASES = dict(RUN.v2_cases(SETS), **{PR.SMOKE["id"]: PR.SMOKE})
BY_NONCE = {P.nonce(cid): cid for cid in CASES}
STUDY_CALLS = len(RUN.v2_calls(PLAN))


def verdict(model: str, cid: str) -> str:
    solves = int(hashlib.sha256(f"{model}:{cid}".encode()).hexdigest(), 16) % 2 == 0
    return json.dumps({"solves": solves, "probability": 0.8 if solves else 0.2,
                       "evidence": [{"file": "pkg/mod.py", "line": 11, "note": "stub"}], "constitutional": False,
                       "reason": "stub gateway"})


class Stub:
    """The gateway's two routes. faults[(model, case)] is a list of actions used up one per request: an HTTP status,
    "slow" (answer after the client's timeout), "bad-json" (an answer that isn't JSON) or "missing" (a verdict with
    no evidence). usage[(model, case)] overrides the reported usage. kill_after sets `reached` after that many
    study answers."""

    def __init__(self):
        self.faults, self.usage, self.log = {}, {}, []
        self.kill_after, self.study_answers, self.reached = None, 0, threading.Event()
        self.lock = threading.Lock()
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                text = json.dumps(body)
                cid = next((c for n, c in BY_NONCE.items() if f"untrusted-{n}" in text), None)
                key = (body.get("model"), cid)
                with stub.lock:
                    stub.log.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                     "type": self.headers.get("Content-Type"),
                                     "version": self.headers.get("anthropic-version"), "model": body.get("model"),
                                     "case": cid, "body": body, "at": time.monotonic()})
                    action = (stub.faults.get(key) or [None]).pop(0) if stub.faults.get(key) else None
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self.reply(401, {"error": "unauthorized"})
                if isinstance(action, int):
                    return self.reply(action, {"error": f"stub {action}"})
                if action == "slow":
                    time.sleep(1.5)
                answer = {"bad-json": "Looks fine to me.", "missing": '{"solves": true, "probability": 0.9}'}.get(
                    action, verdict(body["model"], cid))
                usage = stub.usage.get(key, (1000, 300))
                if self.path == "/v1/messages":
                    out = {"content": [{"type": "text", "text": answer}],
                           "usage": {"input_tokens": usage[0], "output_tokens": usage[1]}}
                else:
                    out = {"choices": [{"message": {"role": "assistant", "content": answer}}],
                           "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]}}
                self.reply(200, out)
                if cid != PR.SMOKE["id"]:
                    with stub.lock:
                        stub.study_answers += 1
                        if stub.kill_after and stub.study_answers >= stub.kill_after:
                            stub.reached.set()

            def reply(self, status, obj):
                data = json.dumps(obj).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:  # the client gave up (timeout) or was killed
                    pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Workspace:
    """A temporary data directory with the tiny sets, the test plan and a token helper that prints a token naming
    the caller it was asked for (MODEL_GATEWAY_CLIENT_ID), as agentcore's helper does through Keycloak."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        data = self.dir / "data"
        data.mkdir()
        for name, file in RUN.V2_SETS.items():
            (data / file).write_text("".join(json.dumps(c) + "\n" for c in SETS[name]), encoding="utf-8")
        self.plan = self.dir / "plan.json"
        self.plan.write_text(json.dumps(PLAN, sort_keys=True), encoding="utf-8")
        helper = self.dir / "token-helper.sh"
        helper.write_text('#!/bin/sh\nprintf "tok-%s" "$MODEL_GATEWAY_CLIENT_ID"\n', encoding="utf-8")
        helper.chmod(0o755)
        self.data, self.helper = data, helper
        self.out = data / "verdicts-v2"

    def env(self, stub, approved=None, backoff="0.01"):
        env = {k: v for k, v in os.environ.items() if not k.startswith(("POF_", "MODEL_GATEWAY"))}
        env.update(POF_JUDGES_DATA=str(self.data), POF_JUDGES_PLAN_V2=str(self.plan), MODEL_GATEWAY_URL=stub.url,
                   MODEL_GATEWAY_TOKEN_HELPER=str(self.helper), POF_JUDGE_BACKOFF=backoff,
                   POF_JUDGE_HTTP_TIMEOUT="0.5", POF_JUDGE_RUN_APPROVED=approved or PLAN["hash"],
                   HOME=str(self.dir), PYTHONDONTWRITEBYTECODE="1")
        return env

    def args(self, max_usd="5", max_tokens="10000000"):
        return [sys.executable, str(SCRIPT), "run-v2", "--execute", "--max-usd", max_usd, "--max-tokens", max_tokens]

    def run(self, stub, **kw):
        env = self.env(stub, kw.pop("approved", None), kw.pop("backoff", "0.01"))
        return subprocess.run(self.args(**kw), env=env, cwd=ROOT, capture_output=True, text=True, timeout=120)

    def records(self, sub=""):
        d = self.out / sub if sub else self.out
        return {p.stem: [json.loads(x) for x in p.read_text().splitlines() if x] for p in sorted(d.glob("*.jsonl"))}

    def close(self):
        self.tmp.cleanup()


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.stub, self.ws = Stub(), Workspace()

    def tearDown(self):
        self.stub.close()
        self.ws.close()

    def test_a_full_run_sends_what_the_real_run_would(self):
        r = self.ws.run(self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = self.stub.log
        self.assertEqual(len(log), len(SEATS) + STUDY_CALLS)
        self.assertEqual({e["case"] for e in log[:len(SEATS)]}, {PR.SMOKE["id"]})  # stage 0 first, every seat
        self.assertNotIn(PR.SMOKE["id"], {e["case"] for e in log[len(SEATS):]})
        for e in log:
            self.assertEqual(e["auth"], f"Bearer {TOKEN}")  # the judges caller's token, from its helper
            self.assertEqual(e["type"], "application/json")
            seat = SEATS[BY_MODEL[e["model"]]]
            if seat.api == "messages":
                self.assertEqual((e["path"], e["version"]), ("/v1/messages", "2023-06-01"))
                self.assertIn("system", e["body"])
            else:
                self.assertEqual(e["path"], "/v1/chat/completions")
                self.assertEqual(e["body"]["messages"][0]["role"], "system")
            self.assertEqual(e["body"][seat.limit_field], PR.limit(BY_MODEL[e["model"]], CASES[e["case"]]["size"]))
        recs = self.ws.records()
        self.assertEqual(set(recs), set(SEATS))
        self.assertEqual(sum(len(v) for v in recs.values()), STUDY_CALLS)
        for seat, rows in recs.items():
            for row in rows:
                self.assertEqual((row["seat"], row["family"], row["model"]), (seat, SEATS[seat].family,
                                                                            SEATS[seat].model))
                self.assertNotIn("error", row["verdict"])
                self.assertIsInstance(row["usage"]["input_tokens"], int)
        self.assertIn("done:", r.stderr)

    def test_throttling_and_server_errors_are_retried_with_backoff(self):
        key = ("claude-opus-5-5", "t__t-1:bad")
        self.stub.faults[key] = [429, 503]
        r = self.ws.run(self.stub, backoff="0.2")
        self.assertEqual(r.returncode, 0, r.stderr)
        tries = [e for e in self.stub.log if (e["model"], e["case"]) == key]
        self.assertEqual(len(tries), 3)
        self.assertGreaterEqual(tries[1]["at"] - tries[0]["at"], 0.2)  # BACKOFF x 1, then x 2
        self.assertGreaterEqual(tries[2]["at"] - tries[1]["at"], 0.4)
        row = next(x for x in self.ws.records()["anthropic"] if x["case"] == key[1])
        self.assertNotIn("error", row["verdict"])

    def test_a_refused_access_is_retried_and_then_stops_the_run_without_a_verdict(self):
        key = ("claude-opus-5-5", "t__t-1:bad")
        self.stub.faults[key] = [403]  # a passing refusal: retried, then judged
        r = self.ws.run(self.stub, backoff="0.05")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = next(x for x in self.ws.records()["anthropic"] if x["case"] == key[1])
        self.assertNotIn("error", row["verdict"])

    def test_a_lasting_refused_access_stops_the_run_and_stores_nothing_for_the_case(self):
        key = ("claude-opus-5-5", "t__t-1:bad")
        self.stub.faults[key] = [403] * 5
        r = self.ws.run(self.stub, backoff="0.05")
        self.assertEqual(r.returncode, 3)
        self.assertIn("access refused", r.stderr)
        self.assertNotIn(key[1], [x["case"] for x in self.ws.records().get("anthropic", [])])
        self.assertEqual(len([e for e in self.stub.log if (e["model"], e["case"]) == key]), 5)

    def test_a_lasting_throttle_is_retried_longer_and_then_stops_without_a_verdict(self):
        key = ("claude-opus-5-5", "t__t-1:bad")
        self.stub.faults[key] = [429] * 6  # more than the 5 tries other errors get: still judged
        r = self.ws.run(self.stub, backoff="0.02")
        self.assertEqual(r.returncode, 0, r.stderr)
        row = next(x for x in self.ws.records()["anthropic"] if x["case"] == key[1])
        self.assertNotIn("error", row["verdict"])

    def test_a_throttle_through_every_try_sets_the_seat_aside_and_the_rest_go_on(self):
        key = ("claude-opus-5-5", "t__t-1:bad")
        self.stub.faults[key] = [429] * 9
        r = self.ws.run(self.stub, backoff="0.02")
        self.assertEqual(r.returncode, 3)
        self.assertIn("throttled", r.stderr)
        self.assertNotIn(key[1], [x["case"] for x in self.ws.records().get("anthropic", [])])
        # The seat is set aside (no more calls to it); every other seat finishes; a rerun judges the rest.
        self.assertEqual(len([e for e in self.stub.log if (e["model"], e["case"]) == key]), 9)
        recs = self.ws.records()
        self.assertTrue(all(len(v) > 0 for k, v in recs.items() if k != "anthropic"))
        before = {k: len(v) for k, v in recs.items()}
        self.stub.faults.clear()
        r = self.ws.run(self.stub, backoff="0.02")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = {k: len(v) for k, v in self.ws.records().items()}
        self.assertIn(key[1], [x["case"] for x in self.ws.records()["anthropic"]])
        self.assertEqual({k: after[k] for k in before if k != "anthropic"},
                         {k: before[k] for k in before if k != "anthropic"})

    def test_a_timeout_is_retried(self):
        key = ("openai.gpt-6.1-sol", "t__t-1:good")
        self.stub.faults[key] = ["slow"]
        r = self.ws.run(self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sum(1 for e in self.stub.log if (e["model"], e["case"]) == key), 2)
        row = next(x for x in self.ws.records()["openai"] if x["case"] == key[1])
        self.assertNotIn("error", row["verdict"])

    def test_malformed_and_incomplete_answers_are_invalid_verdicts(self):
        self.stub.faults[("mistral.mistral-large-3-675b-instruct", "t__t-1:bad")] = ["bad-json"]
        self.stub.faults[("qwen.qwen3-235b-a22b-2507", "t__t-1:bad")] = ["missing"]
        r = self.ws.run(self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        recs = self.ws.records()
        bad = next(x for x in recs["mistral"] if x["case"] == "t__t-1:bad")
        missing = next(x for x in recs["qwen"] if x["case"] == "t__t-1:bad")
        self.assertEqual(bad["verdict"], {"error": "not JSON"})
        self.assertEqual(missing["verdict"], {"error": "no evidence"})
        self.assertEqual(bad["answer"], "Looks fine to me.")  # the raw answer is kept
        # not re-asked: one request each (the pre-registration's rule)
        self.assertEqual(sum(1 for e in self.stub.log if e["model"].startswith("mistral") and
                             e["case"] == "t__t-1:bad"), 1)
        # counted as invalid under both of the pre-registration's rules
        self.assertFalse(PR.passed(bad, invalid_passes=False))
        self.assertTrue(PR.passed(bad, invalid_passes=True))

    def test_the_dollar_limit_stops_before_the_call_that_would_cross_it(self):
        max_usd = max(1.0, round(PLAN["budget"]["estimate"] + 0.5, 2))
        first = RUN.v2_calls(PLAN)[0]
        self.assertEqual(first[1], "anthropic")
        price = PR.seat_price("anthropic")
        # the first study call reports usage worth the whole budget
        self.stub.usage[("claude-opus-5-5", first[2])] = (1000, int(max_usd / price.output * PL.C.M))
        r = self.ws.run(self.stub, max_usd=str(max_usd))
        self.assertEqual(r.returncode, 3)
        self.assertIn("--max-usd", r.stderr)
        self.assertIn("stopped before", r.stderr)
        self.assertEqual(len(self.stub.log), len(SEATS) + 1)  # stage 0 and that one call; the next never sent
        recs = self.ws.records()
        self.assertEqual([x["case"] for x in recs["anthropic"]], [first[2]])
        self.assertEqual(sum(len(v) for v in recs.values()), 1)

    def test_a_killed_run_resumes_without_repeating_a_completed_call(self):
        clean_stub, clean = Stub(), Workspace()
        try:
            r = clean.run(clean_stub)
            self.assertEqual(r.returncode, 0, r.stderr)
            expected, expected_smoke = clean.records(), clean.records("smoke")
        finally:
            clean_stub.close()
            clean.close()
        self.stub.kill_after = STUDY_CALLS // 2
        proc = subprocess.Popen(self.ws.args(), env=self.ws.env(self.stub), cwd=ROOT, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        self.assertTrue(self.stub.reached.wait(60))
        proc.kill()
        proc.wait(30)
        before = {(row["seat"], row["case"]) for rows in self.ws.records().values() for row in rows}
        self.assertTrue(0 < len(before) < STUDY_CALLS)
        self.stub.kill_after, self.stub.log = None, []
        r = self.ws.run(self.stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        again = {(BY_MODEL[e["model"]], e["case"]) for e in self.stub.log}
        self.assertFalse(again & before, "a completed call was repeated")
        self.assertEqual(len(self.stub.log), STUDY_CALLS - len(before))
        self.assertEqual(self.ws.records(), expected)
        self.assertEqual(self.ws.records("smoke"), expected_smoke)

    def test_a_budget_between_the_estimate_and_the_ceiling_starts(self):
        # the chosen design's estimate is over $100 (owner, 2026-11-14): --max-usd 100 must start, then stop in flight
        est, ceiling = PLAN["budget"]["estimate"], PLAN["budget"]["ceiling"]
        self.assertLess(est, ceiling)
        r = self.ws.run(self.stub, max_usd=str(round((est + ceiling) / 2, 4)))
        self.assertNotIn("is over --max-usd", r.stderr)
        self.assertGreater(len(self.stub.log), 0)

    def test_a_partial_last_line_from_a_kill_is_dropped(self):
        self.ws.out.mkdir(parents=True)
        path = self.ws.out / "anthropic.jsonl"
        good = json.dumps({"case": "t__t-1:good", "seat": "anthropic"})
        path.write_text(good + "\n" + '{"case": "t__t-1:b', encoding="utf-8")
        self.assertEqual([r["case"] for r in RUN.stored(path)], ["t__t-1:good"])
        self.assertEqual(path.read_text(), good + "\n")
        path.write_text('{"case": "x"\n' + good + "\n", encoding="utf-8")  # damage mid-file is not a crash
        with self.assertRaises(ValueError):
            RUN.stored(path)

    def test_a_stage_0_failure_stops_before_stage_1(self):
        self.stub.faults[("nvidia.nemotron-super-3-120b", PR.SMOKE["id"])] = ["bad-json"]
        r = self.ws.run(self.stub)
        self.assertEqual(r.returncode, 3)
        self.assertIn("stage 0", r.stderr)
        self.assertIn("nvidia", r.stderr)
        self.assertEqual({e["case"] for e in self.stub.log}, {PR.SMOKE["id"]})
        self.assertEqual(self.ws.records(), {})

    def test_a_wrong_approval_refuses_to_start(self):
        r = self.ws.run(self.stub, approved="0" * 16)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("not approved", r.stderr)
        self.assertEqual(self.stub.log, [])
        self.assertFalse(self.ws.out.exists())

    def test_the_test_plan_is_the_chosen_design_on_tiny_sets(self):
        self.assertEqual((PLAN["design"]["design"], PLAN["design"]["h3"]), ("B", "2 seats"))
        self.assertEqual(STUDY_CALLS, 7 * 7 + 2 * 4)


if __name__ == "__main__":
    unittest.main()


class ChatUsage(unittest.TestCase):
    """Thinking tokens billed as output are counted even when completion_tokens leaves them out (Gemini's
    OpenAI-compatible endpoint, measured through the gateway on 2026-11-13)."""

    def test_gemini_thinking_is_counted(self):
        JR = RUN
        text, usage = JR.chat_text({"choices": [{"message": {"content": "OK"}}],
                                    "usage": {"prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 131}})
        self.assertEqual((text, usage), ("OK", {"input_tokens": 8, "output_tokens": 123}))

    def test_openai_style_reasoning_inside_completion_is_unchanged(self):
        JR = RUN
        self.assertEqual(JR.chat_output_tokens({"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60}), 50)

    def test_missing_usage_stays_unknown(self):
        JR = RUN
        self.assertIsNone(JR.chat_output_tokens({}))
        self.assertEqual(JR.chat_output_tokens({"completion_tokens": 7}), 7)
