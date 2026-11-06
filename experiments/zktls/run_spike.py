#!/usr/bin/env python3
"""The zkTLS spike's runs (proof-of-fix#135): one small model call on AWS Bedrock, proven with TLSNotary
(tlsn v0.1.0-alpha.15, built by build.sh) through one of three verifiers:

  self-a, self-b  our own notaries on 127.0.0.1 (pof_notary, two different secp256k1 keys): MPC-TLS or proxy mode,
                  a signed attestation, a presentation that hides the credentials, verified offline (pof_verify, with
                  no network) and by the pure-Python receipt check;
  pse-demo        the TLSNotary project's public demo verifier (wss://demo.tlsnotary.org, tlsn alpha.15): it verifies
                  interactively and signs nothing, so there's no proof to keep.

  run_spike.py free --notary self-a --mode mpc --max-sent 4096 --max-recv 4096   # GET / on Bedrock: no model, no cost
  run_spike.py call --model haiku --notary self-a --mode mpc                     # one paid model call
  run_spike.py summarize                                                          # the report's tables

Credentials: `aws configure export-credentials` inside this process; the request is signed here (SigV4, botocore) and
handed to the prover on a pipe. Nothing prints, logs or stores the credentials or the signed headers; the prover
hides the values of Authorization and X-Amz-Security-Token from the verifier and from the presentation.
Every paid attempt leaves a results/call-*.json file, and `call` refuses to start a 16th (the owner's budget is 15).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
PROOFS = HERE / "proofs"
BUILD = Path(os.environ.get("BUILD_DIR", "~/pof-135-build")).expanduser()
BIN = BUILD / "target" / "release" / "examples"
LOGS = BUILD / "logs"
HOST = "bedrock-runtime.us-east-1.amazonaws.com"
REGION = "us-east-1"
PROFILE = "your-aws-profile"
PUBLIC = "demo.tlsnotary.org"
BUDGET = 15
MAX_TOKENS = 20
PROMPT = "Answer with one word, PASS or FAIL: does the Python test `assert 2 + 2 == 4` pass?"
HIDE = ("authorization", "x-amz-security-token")

MODELS = {  # key: (provider family, Bedrock model or inference profile id)
    "claude-haiku-4.5": ("Anthropic", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    "gpt-oss-20b": ("OpenAI", "openai.gpt-oss-20b-1:0"),
    "gpt-5.6-terra": ("OpenAI", "us.openai.gpt-5.6-terra"),
    "gemma-3-4b": ("Google", "google.gemma-3-4b-it"),
}
# USD per million tokens, on-demand, us-east-1, from AWS's public price list (offers/v1.0/aws/AmazonBedrock and
# AmazonBedrockFoundationModels, read 2026-11-03). Haiku through the "us." profile is billed at the regional (geo)
# rate. GPT-5.6 Terra has no published price there or on aws.amazon.com/bedrock/pricing on that date.
PRICES = {
    "claude-haiku-4.5": (1.10, 5.50),
    "gpt-oss-20b": (0.07, 0.30),
    "gpt-5.6-terra": None,
    "gemma-3-4b": (0.04, 0.08),
}
NOTARIES = {"self-a": (7150, "notary-a.key"), "self-b": (7151, "notary-b.key")}
# Access key ids, a signed Authorization value, an STS session token (they start "IQoJb3JpZ2lu" or "FwoGZXIvYXdz") or
# a token quoted after its header name.
CREDENTIAL_PATTERNS = re.compile(rb"(AKIA|ASIA)[A-Z0-9]{12,}|AWS4-HMAC-SHA256 Credential|Signature=[0-9a-f]{16}"
                                 rb"|IQoJb3JpZ2lu|FwoGZXIvYXdz|(?i:x-amz-security-token)\s*[:=]\s*[A-Za-z0-9+/=]{16}")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# --- requests ---------------------------------------------------------------------------------------------------

def free_request(pad: int = 0) -> bytes:
    """GET / on the Bedrock endpoint (or POST / with `pad` bytes of body): no credentials, no model, no cost (the
    server answers 404 or 403)."""
    method, body = ("POST", b"x" * pad) if pad else ("GET", b"")
    extra = f"Content-Length: {pad}\r\n" if pad else ""
    return (f"{method} / HTTP/1.1\r\nHost: {HOST}\r\nAccept: application/json\r\nAccept-Encoding: identity\r\n"
            f"X-Spike-Hidden: not-a-secret-just-hidden\r\n{extra}Connection: close\r\n\r\n").encode() + body


def signed_request(model_id: str) -> bytes:
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    out = subprocess.run(["aws", "configure", "export-credentials", "--profile", PROFILE, "--format", "process"],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise SystemExit("no credentials from the SSO profile (sign in with `aws sso login`)")
    c = json.loads(out.stdout)
    creds = Credentials(c["AccessKeyId"], c["SecretAccessKey"], c.get("SessionToken"))
    del out, c

    body = json.dumps({"messages": [{"role": "user", "content": [{"text": PROMPT}]}],
                       "inferenceConfig": {"maxTokens": MAX_TOKENS}}, separators=(",", ":")).encode()
    path = "/model/" + urllib.parse.quote(model_id, safe="") + "/converse"
    headers = {"Host": HOST, "Content-Type": "application/json", "Accept": "application/json",
               "Accept-Encoding": "identity", "Content-Length": str(len(body))}
    req = AWSRequest(method="POST", url=f"https://{HOST}{path}", data=body, headers=headers)
    SigV4Auth(creds, "bedrock", REGION).add_auth(req)
    # Connection is hop-by-hop: Bedrock canonicalises it as empty, so it's added after signing, unsigned.
    head = [f"POST {path} HTTP/1.1"] + [f"{k}: {v}" for k, v in req.headers.items()] + ["Connection: close"]
    return ("\r\n".join(head) + "\r\n\r\n").encode() + body


# --- runs -------------------------------------------------------------------------------------------------------

def prover_cmd(addr: str, mode: str, max_sent: int, max_recv: int, attest: bool, out: str, hide) -> list[str]:
    cmd = [str(BIN / "pof_prove"), "--verifier", addr, "--mode", mode, "--server-name", HOST,
           "--max-sent", str(max_sent), "--max-recv", str(max_recv)]
    if os.environ.get("MAX_SENT_RECORDS"):
        cmd += ["--max-sent-records", os.environ["MAX_SENT_RECORDS"]]
    if attest:
        cmd += ["--attest", "--out", out]
    for h in hide:
        cmd += ["--hide", h]
    return cmd


def run_self(notary: str, mode: str, request: bytes, max_sent: int, max_recv: int, run_id: str, hide) -> dict:
    port, keyfile = NOTARIES[notary]
    LOGS.mkdir(parents=True, exist_ok=True)
    tmp = BUILD / "proofs-tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    nlog = open(LOGS / f"{run_id}.notary.log", "w")
    notary_p = subprocess.Popen([str(BIN / "pof_notary"), "--listen", f"127.0.0.1:{port}", "--key-file",
                                 str(BUILD / "keys" / keyfile), "--sessions", "1", "--max-sent", "65536",
                                 "--max-recv", "131072"], stdout=nlog, stderr=nlog)
    try:
        time.sleep(0.5)
        with open(LOGS / f"{run_id}.prover.log", "w") as plog:
            t0 = time.monotonic()
            p = subprocess.run(prover_cmd(f"127.0.0.1:{port}", mode, max_sent, max_recv, True, str(tmp / run_id), hide),
                               input=request, stdout=subprocess.PIPE, stderr=plog, timeout=900)
            wall = time.monotonic() - t0
        result = _last_result(p.stdout)
        result["wall_s"] = round(wall, 3)
        try:
            notary_p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            result["notary_timeout"] = True
    finally:
        if notary_p.poll() is None:
            notary_p.kill()
        nlog.close()
    events = [json.loads(line) for line in open(LOGS / f"{run_id}.notary.log") if line.startswith("{")]
    result["notary_events"] = events
    if result.get("ok"):
        result["offline"] = verify_offline(tmp / run_id, run_id)
    return result


def verify_offline(prefix: Path, run_id: str) -> dict:
    """pof_verify in a network namespace with no network (unshare -rn), then the pure-Python receipt check."""
    PROOFS.mkdir(exist_ok=True)
    for ext in ("attestation.tlsn", "presentation.tlsn"):
        shutil.copy(f"{prefix}.{ext}", PROOFS / f"{run_id}.{ext}")
    receipt = PROOFS / f"{run_id}.receipt.json"
    cmd = [str(BIN / "pof_verify"), str(PROOFS / f"{run_id}.presentation.tlsn"), "--receipt", str(receipt),
           "--expect-server", HOST]
    isolated = shutil.which("unshare") is not None and subprocess.run(
        ["unshare", "-rn", "true"], capture_output=True).returncode == 0
    t0 = time.monotonic()
    p = subprocess.run((["unshare", "-rn"] if isolated else []) + cmd, capture_output=True, text=True, timeout=120)
    out = {"no_network_namespace": isolated, "rust_ok": p.returncode == 0, "rust_output": p.stderr.strip()[-600:],
           "rust_wall_s": round(time.monotonic() - t0, 3)}
    if p.returncode == 0:
        sys.path.insert(0, str(HERE))
        import receipt_check
        t1 = time.monotonic()
        r = receipt_check.check(json.loads(receipt.read_text()))
        out.update(python_ok=True, python_s=round(time.monotonic() - t1, 3), notary_address=r["notary"],
                   sent_revealed=r["sent_revealed"], recv_revealed=r["recv_revealed"])
        for f in (PROOFS / f"{run_id}.presentation.tlsn", PROOFS / f"{run_id}.attestation.tlsn", receipt):
            if CREDENTIAL_PATTERNS.search(f.read_bytes()):
                raise SystemExit(f"{f} looks like it contains a credential; not keeping it")
    return out


async def run_public(mode: str, request: bytes, max_sent: int, max_recv: int, run_id: str, hide) -> dict:
    from websockets.asyncio.client import connect

    LOGS.mkdir(parents=True, exist_ok=True)
    accepted: asyncio.Future = asyncio.get_running_loop().create_future()

    async def on_conn(reader, writer):
        if not accepted.done():
            accepted.set_result((reader, writer))

    server = await asyncio.start_server(on_conn, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    plog = open(LOGS / f"{run_id}.prover.log", "w")
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(*prover_cmd(f"127.0.0.1:{port}", mode, max_sent, max_recv, False, "", hide),
                                                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                stderr=plog)
    proc.stdin.write(request)
    await proc.stdin.drain()
    proc.stdin.close()
    reader, writer = await asyncio.wait_for(accepted, 30)
    out: dict = {"verifier": f"wss://{PUBLIC}", "public": {}}
    up = down = 0
    async with connect(f"wss://{PUBLIC}/session", max_size=None, ping_interval=None) as sess:
        await sess.send(json.dumps({"type": "register", "maxRecvData": max_recv, "maxSentData": max_sent,
                                    "sessionData": {}}))
        reg = json.loads(await asyncio.wait_for(sess.recv(), 30))
        sid = reg.get("sessionId")
        if not sid:
            raise SystemExit(f"the public verifier refused the session: {reg}")
        async with connect(f"wss://{PUBLIC}/verifier?sessionId={sid}", max_size=None, ping_interval=None) as ver:
            t_ws = time.monotonic()

            async def tcp_to_ws():
                nonlocal up
                while data := await reader.read(1 << 16):
                    up += len(data)
                    await ver.send(data)

            async def ws_to_tcp():
                nonlocal down
                try:
                    async for msg in ver:
                        data = msg if isinstance(msg, bytes) else msg.encode()
                        down += len(data)
                        writer.write(data)
                        await writer.drain()
                finally:
                    writer.close()

            async def prover_events():
                result = None
                while line := await proc.stdout.readline():
                    ev = json.loads(line)
                    if ev.get("event") == "reveal":
                        handler = lambda kind: {"type": kind, "part": "ALL", "action": {"kind": "REVEAL"}}
                        await sess.send(json.dumps({
                            "type": "reveal_config",
                            "sent": [{"start": a, "end": b, "handler": handler("SENT")} for a, b in ev["sent"]],
                            "recv": [{"start": a, "end": b, "handler": handler("RECV")} for a, b in ev["recv"]]}))
                    elif ev.get("event") == "result":
                        result = ev
                return result

            pumps = [asyncio.create_task(tcp_to_ws()), asyncio.create_task(ws_to_tcp())]
            result = await asyncio.wait_for(prover_events(), 900)
            await proc.wait()
            out["prover_exit"] = proc.returncode
            for t in pumps:
                t.cancel()
        try:
            msg = json.loads(await asyncio.wait_for(sess.recv(), 45))
        except Exception as e:  # noqa: BLE001  (record whatever the verifier did)
            msg = {"type": "no_reply", "error": repr(e)}
        out["public_ws_s"] = round(time.monotonic() - t_ws, 3)
    server.close()
    plog.close()
    if msg.get("type") == "session_completed":
        values = [r.get("value", "") for r in msg.get("results", [])]
        blob = "".join(values).encode()
        out["public"] = {"type": "session_completed", "results": len(values),
                         "revealed_chars": sum(len(v) for v in values),
                         "credential_free": not CREDENTIAL_PATTERNS.search(blob),
                         "signed": False}
    else:
        out["public"] = msg
    out.update(result or {"ok": False, "error": "no result from the prover"})
    out["wall_s"] = round(time.monotonic() - t0, 3)
    out["bridge_bytes_up"], out["bridge_bytes_down"] = up, down
    return out


def _last_result(stdout: bytes) -> dict:
    for line in reversed(stdout.decode(errors="replace").splitlines()):
        if line.startswith("{"):
            ev = json.loads(line)
            if ev.get("event") == "result":
                return ev
    return {"ok": False, "error": "no result line from the prover"}


def usage_and_cost(model: str, body: str) -> dict:
    try:
        j = json.loads(body)
    except ValueError:
        return {"answer": None, "error_body": body[:300]}
    u = j.get("usage", {})
    texts = [c.get("text") for c in j.get("output", {}).get("message", {}).get("content", []) if "text" in c]
    reasoning = [c for c in j.get("output", {}).get("message", {}).get("content", []) if "reasoningContent" in c]
    price = PRICES.get(model)
    cost = None if price is None or not u else (u.get("inputTokens", 0) * price[0] + u.get("outputTokens", 0) * price[1]) / 1e6
    return {"answer": " ".join(t for t in texts if t).strip() or None, "reasoning_blocks": len(reasoning),
            "stop_reason": j.get("stopReason"), "input_tokens": u.get("inputTokens"),
            "output_tokens": u.get("outputTokens"), "cost_usd": cost, "latency_ms": j.get("metrics", {}).get("latencyMs"),
            "error_body": None if "output" in j else body[:300]}


def paid_attempts() -> int:
    return len(list(RESULTS.glob("call-*.json")))


def save(name: str, data: dict) -> Path:
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / f"{name}.json"
    blob = json.dumps(data, indent=1, sort_keys=True) + "\n"
    if CREDENTIAL_PATTERNS.search(blob.encode()):
        raise SystemExit("a result looks like it contains a credential; not saving it")
    path.write_text(blob)
    return path


def unique(name: str) -> str:
    n, i = name, 2
    while (RESULTS / f"{n}.json").exists():
        n, i = f"{name}-{i}", i + 1
    return n


def cmd_free(a) -> None:
    recs = os.environ.get("MAX_SENT_RECORDS")
    run_id = unique(f"free-{a.notary}-{a.mode}-s{a.max_sent}-r{a.max_recv}" + (f"-pad{a.pad}" if a.pad else "")
                    + (f"-rec{recs}" if recs else ""))
    hide = ["x-spike-hidden"]
    if a.notary == "pse-demo":
        r = asyncio.run(run_public(a.mode, free_request(a.pad), a.max_sent, a.max_recv, run_id, hide))
    else:
        r = run_self(a.notary, a.mode, free_request(a.pad), a.max_sent, a.max_recv, run_id, hide)
    r.update(run=run_id, kind="free", notary=a.notary, pad=a.pad, max_sent_records=recs,
             date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    log(f"{save(run_id, r)}: ok={r.get('ok')} {r.get('error', '')}")


def cmd_call(a) -> None:
    if paid_attempts() >= BUDGET:
        raise SystemExit(f"the paid-call budget ({BUDGET}) is spent")
    family, model_id = MODELS[a.model]
    run_id = unique(f"call-{a.notary}-{a.mode}-{a.model}")
    save(run_id, {"run": run_id, "kind": "call", "state": "started"})  # counts against the budget from here
    request = signed_request(model_id)
    try:
        if a.notary == "pse-demo":
            r = asyncio.run(run_public(a.mode, request, a.max_sent, a.max_recv, run_id, HIDE))
        else:
            r = run_self(a.notary, a.mode, request, a.max_sent, a.max_recv, run_id, HIDE)
    finally:
        del request
    inner = r.get("result", {})
    r.update(run=run_id, kind="call", notary=a.notary, model=a.model, family=family, model_id=model_id,
             prompt=PROMPT, max_tokens=MAX_TOKENS, date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             **{"call": usage_and_cost(a.model, inner.get("response_body", r.get("response_body", "")) or "")})
    log(f"{save(run_id, r)}: ok={r.get('ok')} {r.get('error', '')} {r['call'].get('answer')!r}")


def cmd_summarize(_a) -> None:
    rows = [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*.json"))]
    print("| run | ok | TLS | mode | max sent/recv | sent/recv B | setup s | TLS s | prove s | attest s | total s |"
          " up MB | down MB | attestation B | presentation B | offline |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        x = r.get("result", r)
        off = r.get("offline", {})
        offline = ("yes (no network)" if off.get("rust_ok") and off.get("python_ok") and off.get("no_network_namespace")
                   else "yes" if off.get("rust_ok") else "no signed proof" if r.get("notary") == "pse-demo" else "-")
        up = x.get("verifier_bytes_up")
        down = x.get("verifier_bytes_down")
        print(f"| {r.get('run')} | {r.get('ok')} | {x.get('tls_version', '-')} | {x.get('mode', '-')} | "
              f"{x.get('max_sent', '-')}/{x.get('max_recv', '-')} | {x.get('sent_len', '-')}/{x.get('recv_len', '-')} | "
              f"{x.get('setup_s', '-')} | {x.get('tls_exchange_s', '-')} | {x.get('prove_s', '-')} | "
              f"{x.get('attest_s', '-')} | {x.get('total_s', '-')} | "
              f"{'-' if up is None else round(up / 1e6, 1)} | {'-' if down is None else round(down / 1e6, 1)} | "
              f"{x.get('attestation_bytes', '-')} | {x.get('presentation_bytes', '-')} | {offline} |")
    calls = [r for r in rows if r.get("kind") == "call" and "call" in r]
    total = sum(r["call"].get("cost_usd") or 0 for r in calls)
    print(f"\npaid attempts: {paid_attempts()} of {BUDGET}; priced cost ${total:.6f}")
    for r in calls:
        c = r["call"]
        print(f"- {r['run']}: {c.get('input_tokens')} in / {c.get('output_tokens')} out, "
              f"${c.get('cost_usd') if c.get('cost_usd') is not None else 'unpriced'}, answer {c.get('answer')!r}, "
              f"stop {c.get('stop_reason')}, public {r.get('public') or '-'}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("free", "call"):
        p = sub.add_parser(name)
        p.add_argument("--notary", choices=["self-a", "self-b", "pse-demo"], required=True)
        p.add_argument("--mode", choices=["mpc", "proxy"], default="mpc")
        p.add_argument("--max-sent", type=int, default=4096)
        p.add_argument("--max-recv", type=int, default=4096)
        if name == "call":
            p.add_argument("--model", choices=sorted(MODELS), required=True)
        else:
            p.add_argument("--pad", type=int, default=0, help="POST / with this many body bytes")
    sub.add_parser("summarize")
    a = ap.parse_args()
    {"free": cmd_free, "call": cmd_call, "summarize": cmd_summarize}[a.cmd](a)


if __name__ == "__main__":
    main()
