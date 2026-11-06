"""Direct model calls (proof-of-fix#118): every provider against a fake HTTP server on 127.0.0.1, asserting the exact
request (headers, signature, body) and parsing real-shaped answers, errors and throttling; AWS Signature Version 4
against AWS's published examples; the spending guards; and the provider's usage reaching the receipt and the meter.
No real model call and no AWS call: nothing here leaves the machine."""

from __future__ import annotations

import datetime
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

from oracle import models as M
from oracle import receipt as receipts
from oracle import v2
from oracle.evidence import Evidence
from oracle.judge import DirectJudge, FakeJudge, judge_from_env

AKID, SECRET = "AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"  # AWS's documentation example credentials
EXAMPLE_TIME = datetime.datetime(2015, 8, 30, 12, 36, 0)
VERDICT = json.dumps({"solves": True, "probability": 0.9, "evidence": [{"file": "a.py", "line": 1, "note": "fixed"}],
                      "constitutional": False, "reason": "the test passes"})
KEY = "sk-test-0123456789-SECRET"


class FakeProvider:
    """An HTTP server on 127.0.0.1 that records each request and answers from a queue of
    (status, headers, body, delay seconds); the last answer repeats."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(n) if n else b""
                outer.seen.append({"method": self.command, "path": self.path,
                                   "headers": {k.lower(): v for k, v in self.headers.items()},
                                   "body": body})
                status, headers, payload, delay = outer.replies.pop(0) if len(outer.replies) > 1 else outer.replies[0]
                if delay:
                    time.sleep(delay)
                data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                try:
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except OSError:
                    pass  # the client gave up (a timeout test)

            do_POST = do_GET = do_PUT = _serve

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.server.block_on_close = False
        threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def ok(payload, headers=None):
    return 200, headers or {"Content-Type": "application/json"}, payload, 0


def client(provider, **kw):
    kw.setdefault("sleep", lambda s: None)
    return M.Client(provider, **kw)


# ---------- AWS Signature Version 4 ----------

class SigV4(unittest.TestCase):
    """AWS's published examples: the signing-key derivation and the IAM ListUsers request of the SigV4 documentation
    ("Create a signed AWS API request"), and the "get-vanilla" and "post-vanilla" cases of the SigV4 test suite. Then a
    Bedrock Converse request, whose model ID holds a colon, against botocore 1.42's signer (computed offline when the
    test was written; checked live below when botocore is installed)."""

    C = M.AwsCredentials(AKID, SECRET)

    def test_signing_key_of_the_documentation(self):
        self.assertEqual(M.signing_key(SECRET, "20150830", "us-east-1", "iam").hex(),
                         "c4afb1cc5771d871763a393e44b703571b55cc28424d1a5e86da6ed3c154a4b9")

    def test_iam_list_users_of_the_documentation(self):
        h = M.sigv4("GET", "https://iam.amazonaws.com/?Action=ListUsers&Version=2010-05-08",
                    {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"}, b"", self.C, "us-east-1",
                    "iam", EXAMPLE_TIME)
        self.assertEqual(h["Authorization"], "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/iam/"
                         "aws4_request, SignedHeaders=content-type;host;x-amz-date, "
                         "Signature=5d672d79c15b13162d9279b0855cfba6789a8edb4c82c400e06b5924a6f2b5d7")
        self.assertEqual((h["X-Amz-Date"], h["Host"]), ("20150830T123600Z", "iam.amazonaws.com"))

    def test_get_vanilla_and_post_vanilla(self):
        for method, sig in (("GET", "5fa00fa31553b73ebf1942676e86291e8372ff2a2260956d9b8aae1d763fbf31"),
                            ("POST", "5da7c1a2acd57cee7505fc6676e4e544621c30862966e37dddb68e92efbe5d6b")):
            h = M.sigv4(method, "https://example.amazonaws.com/", {}, b"", self.C, "us-east-1", "service",
                        EXAMPLE_TIME)
            self.assertEqual(h["Authorization"], "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/"
                             f"aws4_request, SignedHeaders=host;x-amz-date, Signature={sig}")
            self.assertNotIn("X-Amz-Security-Token", h)

    BEDROCK_URL = ("https://bedrock-runtime.us-east-1.amazonaws.com/model/anthropic.claude-3-haiku-20240307-v1%3A0/"
                   "converse")
    BEDROCK_BODY = (b'{"system":[{"text":"sys"}],"messages":[{"role":"user","content":[{"text":"hi"}]}],'
                    b'"inferenceConfig":{"maxTokens":10}}')

    def _bedrock(self):
        creds = M.AwsCredentials(AKID, SECRET, "SESSIONTOKEN")
        return M.sigv4("POST", self.BEDROCK_URL, {"Content-Type": "application/json", "Accept": "application/json"},
                       self.BEDROCK_BODY, creds, "us-east-1", "bedrock",
                       datetime.datetime(2026, 11, 2, 12, 0, tzinfo=datetime.timezone.utc))

    def test_bedrock_converse_as_botocore_signs_it(self):
        """The path is encoded twice in the canonical request (%3A -> %253A), as for every service but S3; the session
        token is signed."""
        h = self._bedrock()
        self.assertEqual(h["Authorization"], "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261102/us-east-1/bedrock/"
                         "aws4_request, SignedHeaders=accept;content-type;host;x-amz-date;x-amz-security-token, "
                         "Signature=51b88e07f798b5e9ec5e15e8fc0a5c121a1cd776c9537375f5182f0f1ac6a6cc")
        self.assertEqual((h["X-Amz-Security-Token"], h["Host"]),
                         ("SESSIONTOKEN", "bedrock-runtime.us-east-1.amazonaws.com"))

    def test_against_botocore_when_installed(self):
        try:
            from unittest import mock

            import botocore.auth
            import botocore.awsrequest
            import botocore.credentials
        except ImportError:
            self.skipTest("botocore not installed (the CI host has none); the vector above was computed with it")
        req = botocore.awsrequest.AWSRequest("POST", self.BEDROCK_URL, data=self.BEDROCK_BODY, headers={
            "Content-Type": "application/json", "Accept": "application/json"})
        t = datetime.datetime(2026, 11, 2, 12, 0, tzinfo=datetime.timezone.utc)
        with mock.patch("botocore.auth.get_current_datetime", return_value=t):
            botocore.auth.SigV4Auth(botocore.credentials.Credentials(AKID, SECRET, "SESSIONTOKEN"), "bedrock",
                                    "us-east-1").add_auth(req)
        self.assertEqual(req.headers["Authorization"], self._bedrock()["Authorization"])


# ---------- Bedrock ----------

CONVERSE_OK = {"output": {"message": {"role": "assistant", "content": [{"text": VERDICT}]}}, "stopReason": "end_turn",
               "usage": {"inputTokens": 1234, "outputTokens": 56, "totalTokens": 1290}, "metrics": {"latencyMs": 812}}
MODEL = "anthropic.claude-3-haiku-20240307-v1:0"


class BedrockDirect(unittest.TestCase):
    def _env(self, url, **extra):
        return {"ORACLE_JUDGE": f"direct:bedrock:{MODEL}", "ORACLE_MODEL_ALLOW": f"other.model,{MODEL}",
                "ORACLE_MODEL_URL": url, "AWS_REGION": "eu-west-1", "AWS_ACCESS_KEY_ID": AKID,
                "AWS_SECRET_ACCESS_KEY": SECRET, "AWS_SESSION_TOKEN": "SESSIONTOKEN", **extra}

    def test_converse_request_signed_and_usage_from_the_response(self):
        with FakeProvider([ok(CONVERSE_OK, {"Content-Type": "application/json",
                                            "x-amzn-RequestId": "req-bedrock-1"})]) as srv:
            c = M.client_from_env(f"direct:bedrock:{MODEL}", self._env(srv.url))
            done = c.complete("sys", "user text")
            req = srv.seen[0]
        self.assertEqual((req["method"], req["path"]), ("POST", "/model/anthropic.claude-3-haiku-20240307-v1%3A0/converse"))
        self.assertEqual(json.loads(req["body"]), {"system": [{"text": "sys"}], "messages": [
            {"role": "user", "content": [{"text": "user text"}]}], "inferenceConfig": {"maxTokens": 4000}})
        h = req["headers"]
        self.assertEqual(h["x-amz-security-token"], "SESSIONTOKEN")
        self.assertRegex(h["x-amz-date"], r"^\d{8}T\d{6}Z$")
        self.assertRegex(h["authorization"], r"^AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/\d{8}/eu-west-1/bedrock/"
                                             r"aws4_request, SignedHeaders=accept;content-type;host;x-amz-date;"
                                             r"x-amz-security-token, Signature=[0-9a-f]{64}$")
        self.assertEqual(h["host"], srv.url[len("http://"):])
        # What arrived on the wire is what was signed: re-sign the received request and compare.
        resign = M.sigv4("POST", srv.url + req["path"], {"Content-Type": h["content-type"], "Accept": h["accept"]},
                         req["body"], M.AwsCredentials(AKID, SECRET, "SESSIONTOKEN"), "eu-west-1", "bedrock",
                         datetime.datetime.strptime(h["x-amz-date"], "%Y%m%dT%H%M%SZ"))
        self.assertEqual(resign["Authorization"], h["authorization"])
        self.assertEqual(done.text, VERDICT)
        self.assertEqual(done.usage, {"input_tokens": 1234, "output_tokens": 56, "cached_tokens": 0,
                                      "reported": CONVERSE_OK["usage"]})
        self.assertEqual(done.inference, {"provider": "bedrock", "model": MODEL, "endpoint": srv.url[7:],
                                          "request_id": "req-bedrock-1", "stop": "end_turn"})

    def test_default_endpoint_is_the_regions_bedrock_runtime(self):
        sent = []
        conv = json.dumps(CONVERSE_OK).encode()

        def request(method, url, headers, body, timeout):
            sent.append((url, headers))
            return M.Reply(200, {}, conv)

        env = self._env("")
        del env["ORACLE_MODEL_URL"]
        M.client_from_env(env["ORACLE_JUDGE"], env, request=request).complete("s", "u")
        self.assertEqual(sent[0][0], "https://bedrock-runtime.eu-west-1.amazonaws.com/model/"
                                     "anthropic.claude-3-haiku-20240307-v1%3A0/converse")
        self.assertEqual(sent[0][1]["Host"], "bedrock-runtime.eu-west-1.amazonaws.com")

    def test_inference_profile_arn_is_encoded_into_one_path_segment(self):
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-3-haiku-20240307-v1:0"
        with FakeProvider([ok(CONVERSE_OK)]) as srv:
            env = self._env(srv.url, ORACLE_MODEL_ALLOW=arn)
            M.client_from_env(f"direct:bedrock:{arn}", env).complete("s", "u")
            path = srv.seen[0]["path"]
        self.assertTrue(path.startswith("/model/arn%3Aaws%3Abedrock%3Aus-east-1%3A123456789012%3Ainference-profile"
                                        "%2Fus."), path)
        self.assertEqual(unquote(path[len("/model/"):-len("/converse")]), arn)

    def test_allowlist_mirrors_the_iam_policy(self):
        env = self._env("https://bedrock.example")
        with self.assertRaisesRegex(M.ConfigError, "isn't in ORACLE_MODEL_ALLOW"):
            M.client_from_env("direct:bedrock:amazon.nova-pro-v1:0", env)
        del env["ORACLE_MODEL_ALLOW"]
        with self.assertRaisesRegex(M.ConfigError, "ORACLE_MODEL_ALLOW"):
            M.client_from_env(f"direct:bedrock:{MODEL}", env)
        env = self._env("https://bedrock.example")
        del env["AWS_REGION"]
        with self.assertRaisesRegex(M.ConfigError, "AWS_REGION"):
            M.client_from_env(f"direct:bedrock:{MODEL}", env)

    def test_throttling_is_retried_with_backoff_then_answers(self):
        throttled = (429, {"x-amzn-ErrorType": "ThrottlingException:http://internal.amazon.com/coral/com.amazon.bedrock/",
                           "x-amzn-RequestId": "r-429"}, {"message": "Too many requests, please wait before trying again."}, 0)
        slept = []
        with FakeProvider([throttled, (503, {"x-amzn-ErrorType": "ServiceUnavailableException"},
                                       {"message": "Bedrock is unable to process your request."}, 0),
                           ok(CONVERSE_OK)]) as srv:
            c = M.client_from_env(f"direct:bedrock:{MODEL}", self._env(srv.url), sleep=slept.append)
            done = c.complete("s", "u")
            self.assertEqual(len(srv.seen), 3)
            dates = [r["headers"]["authorization"] for r in srv.seen]
        self.assertEqual(done.usage["output_tokens"], 56)
        self.assertEqual(slept, [2.0, 4.0])
        self.assertEqual(c.budget.calls, 3)  # every attempt counts against ORACLE_MAX_CALLS
        self.assertEqual(len(dates), 3)  # each attempt signed afresh

    def test_validation_and_access_errors_are_not_retried(self):
        for status, kind, msg in ((400, "ValidationException", "The provided model identifier is invalid."),
                                  (403, "AccessDeniedException", "You don't have access to the model with the "
                                                                 "specified model ID.")):
            with FakeProvider([(status, {"x-amzn-ErrorType": f"{kind}:http://internal.amazon.com/coral/",
                                         "x-amzn-RequestId": "r-x"}, {"message": msg}, 0)]) as srv:
                c = M.client_from_env(f"direct:bedrock:{MODEL}", self._env(srv.url))
                with self.assertRaises(M.ModelError) as cm:
                    c.complete("s", "u")
                self.assertEqual(len(srv.seen), 1)
            e = cm.exception
            self.assertEqual((e.status, e.kind, e.request_id, e.retryable), (status, kind, "r-x", False))
            self.assertIn(msg, str(e))
            self.assertNotIn(SECRET, str(e))


class InstanceRole(unittest.TestCase):
    """IMDSv2: a session token by PUT, then the role's name and its credentials with that token."""

    CREDS = {"Code": "Success", "LastUpdated": "2026-11-02T11:00:00Z", "Type": "AWS-HMAC", "AccessKeyId": "ASIAROLE",
             "SecretAccessKey": "roleSecret", "Token": "roleSessionToken", "Expiration": "2026-11-02T18:00:00Z"}

    def _imds(self):
        seen = []

        class Handler(BaseHTTPRequestHandler):
            def _reply(self, status, text):
                data = text.encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_PUT(self):
                seen.append(("PUT", self.path, dict(self.headers.items())))
                if self.path == "/latest/api/token" and self.headers.get("X-aws-ec2-metadata-token-ttl-seconds"):
                    return self._reply(200, "imds-token")
                return self._reply(400, "")

            def do_GET(self):
                seen.append(("GET", self.path, dict(self.headers.items())))
                if self.headers.get("X-aws-ec2-metadata-token") != "imds-token":
                    return self._reply(401, "")  # IMDSv2 only, as the kit's instance requires
                if self.path == "/latest/meta-data/iam/security-credentials/":
                    return self._reply(200, "pof-validator-node")
                if self.path == "/latest/meta-data/iam/security-credentials/pof-validator-node":
                    return self._reply(200, json.dumps(InstanceRole.CREDS))
                return self._reply(404, "")

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, args=(0.02,), daemon=True).start()
        return srv, seen, f"http://127.0.0.1:{srv.server_address[1]}"

    def test_credentials_by_imdsv2_cached_until_near_expiry(self):
        srv, seen, url = self._imds()
        try:
            now = [datetime.datetime(2026, 11, 2, 12, 0, tzinfo=datetime.timezone.utc).timestamp()]
            src = M.InstanceRoleCredentials(url, clock=lambda: now[0])
            c = src()
            self.assertEqual((c.access_key, c.secret_key, c.token), ("ASIAROLE", "roleSecret", "roleSessionToken"))
            self.assertEqual([s[:2] for s in seen], [("PUT", "/latest/api/token"),
                                                     ("GET", "/latest/meta-data/iam/security-credentials/"),
                                                     ("GET", "/latest/meta-data/iam/security-credentials/"
                                                             "pof-validator-node")])
            self.assertIs(src(), c)  # cached
            self.assertEqual(len(seen), 3)
            now[0] += 6 * 3600 - 200  # within five minutes of expiry: refreshed
            src()
            self.assertEqual(len(seen), 6)
            self.assertNotIn("roleSecret", repr(c))
            self.assertNotIn("roleSessionToken", repr(c))
        finally:
            srv.shutdown()
            srv.server_close()

    def test_bedrock_signs_with_the_roles_credentials(self):
        srv, _, imds = self._imds()
        try:
            with FakeProvider([ok(CONVERSE_OK)]) as bedrock:
                env = {"ORACLE_MODEL_ALLOW": MODEL, "ORACLE_MODEL_URL": bedrock.url, "AWS_REGION": "us-east-1",
                       "AWS_EC2_METADATA_SERVICE_ENDPOINT": imds}
                M.client_from_env(f"direct:bedrock:{MODEL}", env).complete("s", "u")
                h = bedrock.seen[0]["headers"]
            self.assertEqual(h["x-amz-security-token"], "roleSessionToken")
            self.assertIn("Credential=ASIAROLE/", h["authorization"])
        finally:
            srv.shutdown()
            srv.server_close()

    def test_unreachable_metadata_is_a_model_error(self):
        src = M.InstanceRoleCredentials("http://127.0.0.1:9")  # discard port: refused
        with self.assertRaisesRegex(M.ModelError, "instance metadata"):
            src()


# ---------- Anthropic, OpenAI, Gemini ----------

MESSAGES_OK = {"id": "msg_01ABC", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
               "content": [{"type": "thinking", "thinking": "hmm", "signature": "x"}, {"type": "text", "text": VERDICT}],
               "stop_reason": "end_turn", "stop_sequence": None,
               "usage": {"input_tokens": 900, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100,
                         "output_tokens": 77}}
CHAT_OK = {"id": "chatcmpl-123", "object": "chat.completion", "created": 1, "model": "gpt-x",
           "choices": [{"index": 0, "message": {"role": "assistant", "content": VERDICT}, "finish_reason": "stop"}],
           "usage": {"prompt_tokens": 500, "completion_tokens": 40, "total_tokens": 540,
                     "prompt_tokens_details": {"cached_tokens": 128},
                     "completion_tokens_details": {"reasoning_tokens": 12}}}
GEMINI_OK = {"candidates": [{"content": {"role": "model", "parts": [{"text": "thinking...", "thought": True},
                                                                     {"text": VERDICT}]},
                             "finishReason": "STOP", "index": 0}],
             "usageMetadata": {"promptTokenCount": 700, "candidatesTokenCount": 60, "thoughtsTokenCount": 200,
                               "totalTokenCount": 960}, "modelVersion": "gemini-2.5-pro", "responseId": "resp-gem-1"}


class ApiProviders(unittest.TestCase):
    def test_anthropic_messages(self):
        with FakeProvider([ok(MESSAGES_OK, {"Content-Type": "application/json", "request-id": "req_011"})]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MAX_TOKENS": "1500"}
            done = M.client_from_env("direct:anthropic:claude-opus-5-5", env).complete("sys", "usr")
            req = srv.seen[0]
        self.assertEqual(req["path"], "/v1/messages")
        self.assertEqual((req["headers"]["x-api-key"], req["headers"]["anthropic-version"]), (KEY, "2023-06-01"))
        self.assertNotIn("authorization", req["headers"])
        self.assertEqual(json.loads(req["body"]), {"model": "claude-opus-5-5", "max_tokens": 1500, "system": "sys",
                                                   "messages": [{"role": "user", "content": "usr"}]})
        self.assertEqual(done.text, VERDICT)  # thinking blocks aren't the answer
        self.assertEqual(done.usage, {"input_tokens": 1000, "output_tokens": 77, "cached_tokens": 100,
                                      "reported": MESSAGES_OK["usage"]})
        self.assertEqual(done.inference["request_id"], "req_011")

    def test_anthropic_errors(self):
        overloaded = (529, {"retry-after": "7"}, {"type": "error", "error": {"type": "overloaded_error",
                                                                            "message": "Overloaded"}}, 0)
        slept = []
        with FakeProvider([overloaded, ok(MESSAGES_OK)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url}
            M.client_from_env("direct:anthropic:m", env, sleep=slept.append).complete("s", "u")
        self.assertEqual(slept, [7.0])  # Retry-After honoured
        bad = (401, {"request-id": "req_401"}, {"type": "error", "error": {"type": "authentication_error",
                                                                           "message": "invalid x-api-key"}}, 0)
        with FakeProvider([bad]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url}
            with self.assertRaises(M.ModelError) as cm:
                M.client_from_env("direct:anthropic:m", env).complete("s", "u")
            self.assertEqual(len(srv.seen), 1)
        self.assertEqual((cm.exception.status, cm.exception.kind, cm.exception.request_id),
                         (401, "authentication_error", "req_401"))
        self.assertNotIn(KEY, str(cm.exception))

    def test_openai_chat_completions(self):
        with FakeProvider([ok(CHAT_OK, {"Content-Type": "application/json", "x-request-id": "req_oai"})]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url + "/v1"}
            done = M.client_from_env("direct:openai:gpt-x", env).complete("sys", "usr")
            req = srv.seen[0]
        self.assertEqual(req["path"], "/v1/chat/completions")
        self.assertEqual(req["headers"]["authorization"], f"Bearer {KEY}")
        self.assertEqual(json.loads(req["body"]), {"model": "gpt-x", "max_completion_tokens": 4000, "messages": [
            {"role": "system", "content": "sys"}, {"role": "user", "content": "usr"}]})
        self.assertEqual(done.usage, {"input_tokens": 500, "output_tokens": 40, "cached_tokens": 128,
                                      "reported": CHAT_OK["usage"]})
        self.assertEqual((done.inference["request_id"], done.inference["stop"]), ("req_oai", "stop"))

    def test_openai_compatible_self_hosted_server(self):
        """A vLLM or llama.cpp server beside the node (#125): no key, its own URL, max_tokens."""
        with FakeProvider([ok({**CHAT_OK, "id": "cmpl-local"})]) as srv:
            env = {"ORACLE_MODEL_URL": srv.url + "/v1", "ORACLE_MODEL_LIMIT_FIELD": "max_tokens"}
            done = M.client_from_env("direct:openai:Qwen/Qwen3-32B", env).complete("s", "u")
            req = srv.seen[0]
        self.assertNotIn("authorization", req["headers"])
        body = json.loads(req["body"])
        self.assertEqual((body["model"], body["max_tokens"]), ("Qwen/Qwen3-32B", 4000))
        self.assertEqual(done.inference["request_id"], "cmpl-local")
        with self.assertRaisesRegex(M.ConfigError, "MODEL_API_KEY"):
            M.client_from_env("direct:openai:gpt-x", {})  # the public API needs a key

    def test_gemini_generate_content(self):
        with FakeProvider([ok(GEMINI_OK)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url + "/v1beta"}
            done = M.client_from_env("direct:gemini:gemini-2.5-pro", env).complete("sys", "usr")
            req = srv.seen[0]
        self.assertEqual(req["path"], "/v1beta/models/gemini-2.5-pro:generateContent")  # no key in the URL
        self.assertEqual(req["headers"]["x-goog-api-key"], KEY)
        self.assertEqual(json.loads(req["body"]), {"systemInstruction": {"parts": [{"text": "sys"}]},
                                                   "contents": [{"role": "user", "parts": [{"text": "usr"}]}],
                                                   "generationConfig": {"maxOutputTokens": 4000}})
        self.assertEqual(done.text, VERDICT)  # thought parts skipped
        self.assertEqual(done.usage["output_tokens"], 260)  # thinking tokens are billed as output
        self.assertEqual(done.usage["input_tokens"], 700)
        self.assertEqual(done.inference["request_id"], "resp-gem-1")

    def test_gemini_quota_error(self):
        quota = (429, {}, {"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).",
                                     "status": "RESOURCE_EXHAUSTED"}}, 0)
        with FakeProvider([quota]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MODEL_RETRIES": "1"}
            with self.assertRaises(M.ModelError) as cm:
                M.client_from_env("direct:gemini:g", env, sleep=lambda s: None).complete("s", "u")
            self.assertEqual(len(srv.seen), 2)  # one try plus one retry, then it gives up
        self.assertEqual((cm.exception.kind, cm.exception.retryable), ("RESOURCE_EXHAUSTED", True))

    def test_api_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            path.write_text(KEY + "\n")
            with FakeProvider([ok(MESSAGES_OK)]) as srv:
                env = {"MODEL_API_KEY_FILE": str(path), "ORACLE_MODEL_URL": srv.url}
                c = M.client_from_env("direct:anthropic:m", env)
                c.complete("s", "u")
                self.assertEqual(srv.seen[0]["headers"]["x-api-key"], KEY)
            self.assertNotIn(KEY, repr(c.provider))
        with self.assertRaisesRegex(M.ConfigError, "MODEL_API_KEY"):
            M.client_from_env("direct:gemini:g", {})


# ---------- the guards ----------

class Guards(unittest.TestCase):
    def test_call_cap(self):
        with FakeProvider([ok(MESSAGES_OK)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MAX_CALLS": "2"}
            c = M.client_from_env("direct:anthropic:m", env)
            c.complete("s", "u")
            c.complete("s", "u")
            with self.assertRaisesRegex(M.BudgetExceeded, "2 of 2 calls"):
                c.complete("s", "u")
            self.assertEqual(len(srv.seen), 2)

    def test_token_budget_refuses_before_sending(self):
        with FakeProvider([ok(MESSAGES_OK)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MAX_RUN_TOKENS": "5000",
                   "ORACLE_MAX_TOKENS": "1000"}
            c = M.client_from_env("direct:anthropic:m", env)
            c.complete("s", "u")  # worst case 1001; spent 1077 as the provider counted
            self.assertEqual(c.budget.tokens, 1077)
            with self.assertRaisesRegex(M.BudgetExceeded, "ORACLE_MAX_RUN_TOKENS"):
                c.complete("x" * 12000, "u")  # ~3429 + 1000 more would pass 5000
            self.assertEqual(len(srv.seen), 1)

    def test_timeout_is_retried_a_bounded_number_of_times(self):
        with FakeProvider([(200, {}, MESSAGES_OK, 1.5)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MODEL_TIMEOUT": "0.2",
                   "ORACLE_MODEL_RETRIES": "1"}
            c = M.client_from_env("direct:anthropic:m", env, sleep=lambda s: None)
            t = time.monotonic()
            with self.assertRaisesRegex(M.ModelError, "timeout|timed out|Timeout"):
                c.complete("s", "u")
            self.assertLess(time.monotonic() - t, 1.4)
            self.assertEqual(len(srv.seen), 2)
            self.assertEqual(c.budget.tokens, 2 * (1 + 4000))  # an unanswered call counts its worst case

    def test_no_retry_storm_on_client_errors(self):
        for status in (400, 401, 403, 404, 413, 422):
            with FakeProvider([(status, {}, {"error": {"type": "x", "message": "no"}}, 0)]) as srv:
                env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url, "ORACLE_MODEL_RETRIES": "5"}
                with self.assertRaises(M.ModelError):
                    M.client_from_env("direct:anthropic:m", env).complete("s", "u")
                self.assertEqual(len(srv.seen), 1, status)

    def test_redirects_are_not_followed(self):
        with FakeProvider([(307, {"Location": "http://127.0.0.1:9/elsewhere"}, b"", 0)]) as srv:
            env = {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url}
            with self.assertRaisesRegex(M.ModelError, "HTTP 307"):
                M.client_from_env("direct:anthropic:m", env).complete("s", "u")
            self.assertEqual(len(srv.seen), 1)

    def test_endpoint_rules(self):
        for url in ("http://api.example.com", "ftp://x", "https://user:pw@api.example.com"):
            with self.assertRaises(M.ConfigError):
                M.client_from_env("direct:anthropic:m", {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": url})
        M.client_from_env("direct:anthropic:m", {"MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": "http://localhost:8000"})
        with self.assertRaisesRegex(M.ConfigError, "one of bedrock"):
            M.client_from_env("direct:azure:m", {})
        with self.assertRaisesRegex(M.ConfigError, "model ID is missing"):
            M.client_from_env("direct:anthropic", {"MODEL_API_KEY": KEY})
        with self.assertRaisesRegex(M.ConfigError, "isn't in ORACLE_MODEL_ALLOW"):
            M.client_from_env("direct:openai:gpt-x", {"MODEL_API_KEY": KEY, "ORACLE_MODEL_ALLOW": "gpt-y"})
        with self.assertRaisesRegex(M.ConfigError, "ORACLE_MAX_CALLS"):
            M.client_from_env("direct:anthropic:m", {"MODEL_API_KEY": KEY, "ORACLE_MAX_CALLS": "many"})


# ---------- the judge, the receipt and the meter ----------

class Passed:
    passed, exit_code, image, results_sha256 = True, 0, "img@sha256:" + "0" * 64, "1" * 64


class JudgeAndReceipt(unittest.TestCase):
    def test_judge_from_env(self):
        self.assertIsInstance(judge_from_env({}), FakeJudge)
        self.assertTrue(judge_from_env({"ORACLE_LIE": "1"}).lie)
        j = judge_from_env({"ORACLE_JUDGE": f"direct:bedrock:{MODEL}", "ORACLE_MODEL_ALLOW": MODEL,
                            "AWS_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": AKID, "AWS_SECRET_ACCESS_KEY": SECRET})
        self.assertIsInstance(j, DirectJudge)
        self.assertEqual((j.client.provider.name, j.client.provider.model), ("bedrock", MODEL))  # colons kept
        with self.assertRaises(ValueError):
            judge_from_env({"ORACLE_JUDGE": "magic"})

    def test_usage_and_provider_reach_the_receipt_and_the_meter_exactly(self):
        with FakeProvider([ok(CONVERSE_OK, {"x-amzn-RequestId": "req-bedrock-9"})]) as srv:
            env = {"ORACLE_JUDGE": f"direct:bedrock:{MODEL}", "ORACLE_MODEL_ALLOW": MODEL, "ORACLE_MODEL_URL": srv.url,
                   "AWS_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": AKID, "AWS_SECRET_ACCESS_KEY": SECRET}
            a = judge_from_env(env).judge({"id": "check-1", "repo": "r", "issue": "i", "commit": "c", "diff": "d",
                                           "context": []}, Passed())
        self.assertTrue(a.solves)
        self.assertEqual((a.model, a.backend), (MODEL, "direct:bedrock"))
        rec = receipts.build(node="0x" + "11" * 20, checker_image="img", model=a.model, backend=a.backend,
                             prompt=a.prompt, response=a.response, fix_tree="ab" * 20, tests={}, submission=1,
                             bounty=1, outcome=1, chain_id=7193, race="0x" + "ab" * 20, attestation_kind="none",
                             issued_at=1, usage=a.usage, inference=a.inference)
        self.assertEqual(rec["model"], {"id": MODEL, "backend": "direct:bedrock", "provider": "bedrock",
                                        "endpoint": srv.url[7:], "request_id": "req-bedrock-9", "stop": "end_turn"})
        self.assertEqual(rec["usage"]["reported"], CONVERSE_OK["usage"])  # the provider's own object, untouched
        u = v2.measured_usage(receipts.receipt_hash(rec), a.prompt, a.response, 1.0, 2000, 4096, 100, a.usage)
        self.assertEqual((u.input, u.output, u.cached), (1234, 56, 0))  # the provider's count, not an estimate

    def test_fake_judge_receipts_are_unchanged(self):
        args = dict(node="n", checker_image="i", model="m", backend="fake", prompt="p", response="r", fix_tree="t",
                    tests={}, submission=1, bounty=1, outcome=1, chain_id=1, race="x", attestation_kind="none",
                    issued_at=1)
        rec = receipts.build(**args, usage=None, inference=None)
        self.assertEqual(set(rec), {"version", "node", "checker_image", "model", "prompt_sha256", "response_sha256",
                                    "base_commit", "tests", "verdict", "chain", "attestation", "issued_at"})
        self.assertEqual(rec, receipts.build(**args))


class ModelCheck(unittest.TestCase):
    """`python3 -m oracle model-check`: the operator's one-call check, exactly one attempt and a small answer cap."""

    def test_one_call_prints_usage_and_request(self):
        import contextlib
        import io

        from oracle.__main__ import model_check

        with FakeProvider([ok(CONVERSE_OK, {"x-amzn-RequestId": "req-check"})]) as srv:
            env = {"ORACLE_JUDGE": f"direct:bedrock:{MODEL}", "ORACLE_MODEL_ALLOW": MODEL, "ORACLE_MODEL_URL": srv.url,
                   "AWS_REGION": "us-east-1", "AWS_ACCESS_KEY_ID": AKID, "AWS_SECRET_ACCESS_KEY": SECRET}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(model_check(env), 0)
            self.assertEqual(json.loads(srv.seen[0]["body"])["inferenceConfig"], {"maxTokens": 64})
        printed = json.loads(out.getvalue())
        self.assertEqual((printed["usage"]["input_tokens"], printed["inference"]["request_id"]), (1234, "req-check"))

    def test_a_throttled_check_is_not_retried(self):
        import contextlib
        import io

        from oracle.__main__ import model_check

        with FakeProvider([(429, {}, {"message": "Too many requests"}, 0)]) as srv:
            env = {"ORACLE_JUDGE": "direct:anthropic:m", "MODEL_API_KEY": KEY, "ORACLE_MODEL_URL": srv.url}
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(model_check(env), 1)
            self.assertEqual(len(srv.seen), 1)
        self.assertNotIn(KEY, out.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(model_check({"ORACLE_JUDGE": "fake"}), 2)


class NodeWithDirectJudge(unittest.TestCase):
    """The v2 node with one drawn judge calling a (fake) provider directly: its usage report carries the provider's
    token counts, and a provider that refuses costs one call, not a storm."""

    def _nodes(self, tmp, url):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parent))  # also when run as tests.test_models
        import test_oracle_v2 as T

        chain, nodes = T.ThreeNodes._nodes(None, tmp)
        found = mock.patch("oracle.evidence.gather", return_value=Evidence("the issue", "the commit", "the diff"))
        found.start()  # what it reads is tests/test_node_evidence.py's; here, what the call costs
        self.addCleanup(found.stop)
        env = {"ORACLE_MODEL_ALLOW": MODEL, "ORACLE_MODEL_URL": url, "AWS_REGION": "us-east-1",
               "AWS_ACCESS_KEY_ID": AKID, "AWS_SECRET_ACCESS_KEY": SECRET}
        nodes[0].judge = DirectJudge(M.client_from_env(f"direct:bedrock:{MODEL}", env, sleep=lambda s: None))
        return chain, nodes

    def test_usage_report_is_the_providers_count(self):
        with tempfile.TemporaryDirectory() as tmp, FakeProvider([ok(CONVERSE_OK)]) as srv:
            chain, nodes = self._nodes(Path(tmp), srv.url)
            for _ in range(20):
                for n in nodes:
                    n.tick(0)
            self.assertEqual(len(srv.seen), 1)  # one verdict, one call
            self.assertEqual(len(chain.results), 1)
            mine = next(r["usage"] for r in chain.reports_ if r["judge"] == nodes[0].address)
            self.assertEqual((mine.input, mine.output), (1234, 56))
            stored = [json.loads(p.read_text()) for p in (Path(tmp) / "receipts-0").glob("*.json")]
            self.assertEqual([(r["usage"]["input_tokens"], r["usage"]["output_tokens"], r["model"]["provider"])
                              for r in stored], [(1234, 56, "bedrock")])

    def test_a_refusing_provider_is_one_call_and_the_node_goes_on(self):
        denied = (403, {"x-amzn-ErrorType": "AccessDeniedException"}, {"message": "not authorized"}, 0)
        with tempfile.TemporaryDirectory() as tmp, FakeProvider([denied]) as srv:
            chain, nodes = self._nodes(Path(tmp), srv.url)
            for _ in range(20):
                for n in nodes:
                    n.tick(0)
            self.assertEqual(len(srv.seen), 1)
            self.assertIn(1, nodes[0].skipped)
            self.assertNotIn(nodes[0].address, [r["judge"] for r in chain.reports_])


if __name__ == "__main__":
    unittest.main()
