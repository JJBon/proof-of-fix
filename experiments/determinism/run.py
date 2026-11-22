"""Runs judge calls for the determinism experiment (proof-of-fix#125) through the real judge path.

Each call goes through oracle.judge.DirectJudge (build_prompt, the verdict parser) and oracle.models.Client with the
`openai` provider pointed at a local OpenAI-compatible server (vLLM or llama-server on 127.0.0.1). The only addition is
the sampling parameters: today's provider sends none, so the server's defaults apply; here they are pinned per run
(`--sampling`), as a re-runnable receipt would have to pin them. `--sampling server-default` sends none, like the node.

One JSON line per call goes to results/<tag>.jsonl: the case, its label, the answer's text and hashes, the token IDs'
hash (vLLM's return_token_ids), the verdict, token counts, latency and the server's timings (llama-server).

    python3 run.py --base http://127.0.0.1:8000/v1 --engine vllm --tag vllm-greedy-seq --reps 10
    python3 run.py ... --concurrency 32 --fillers 100 --reps 2      # the cases mixed with filler requests
    python3 run.py ... --sampling qwen --seed 1234                   # seeded sampling
    python3 run.py ... --sampling server-default --reps 20 --labels borderline,bad --concurrency 16
    python3 run.py ... --vary-id --reps 20 --concurrency 16          # greedy, but a new check ID (markers) each time
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from oracle import judge as J  # noqa: E402
from oracle import models as M  # noqa: E402
from oracle.sandbox import TestRun  # noqa: E402
from pof.judges import prompt as P  # noqa: E402

CASES = HERE / "cases"
RESULTS = HERE / "results"
MAX_TOKENS = 1024

# Qwen2.5-7B-Instruct's generation_config.json: what vLLM applies when a request sends nothing.
QWEN = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "repetition_penalty": 1.05}


def sampling_body(engine: str, sampling: str, seed: int | None) -> dict:
    """The request fields for a sampling setting, in each engine's names."""
    if sampling == "server-default":
        body: dict = {}
    elif sampling == "greedy":
        body = {"temperature": 0.0, "repetition_penalty": 1.0}
    elif sampling == "qwen":
        body = dict(QWEN)
    elif sampling.startswith("t="):  # e.g. t=1.0: plain temperature sampling, nothing else
        body = {"temperature": float(sampling[2:]), "top_p": 1.0, "top_k": 0, "repetition_penalty": 1.0}
    else:
        raise SystemExit(f"--sampling {sampling!r}: greedy, qwen, t=<temperature> or server-default")
    if seed is not None:
        body["seed"] = seed
    if engine == "llama":
        if "repetition_penalty" in body:
            body["repeat_penalty"] = body.pop("repetition_penalty")
        if body:
            body.setdefault("min_p", 0.0)  # llama-server's default min_p is 0.05; vLLM's is 0
        if body.get("top_k") == -1:
            body["top_k"] = 0
    elif engine == "vllm":
        if body.get("top_k") == 0:
            body["top_k"] = -1
        body["return_token_ids"] = True
    return body


class Pinned(M.OpenAI):
    """The node's OpenAI provider, plus the run's pinned request fields."""

    def __init__(self, model: str, base: str, extra: dict):
        super().__init__(model, "", base, "max_tokens")
        self.extra = extra

    def build(self, system, user, max_tokens):
        url, headers, body = super().build(system, user, max_tokens)
        data = json.loads(body)
        data.update(self.extra)
        return url, headers, self._json(data)


_seen = threading.local()


def capturing(method, url, headers, body, timeout):
    reply = M.http_request(method, url, headers, body, timeout)
    _seen.reply = reply
    return reply


def judge_for(base: str, model: str, extra: dict) -> J.DirectJudge:
    budget = M.Budget(max_calls=10**9, max_tokens=10**12)
    client = M.Client(Pinned(model, base, extra), max_tokens=MAX_TOKENS, budget=budget, timeout=900, retries=0,
                      request=capturing)
    return J.DirectJudge(client)


def load_cases(labels: list[str] | None, ids: list[str] | None) -> list[dict]:
    out = []
    for p in sorted(CASES.glob("*.json")):
        c = json.loads(p.read_text())
        if labels and c["label"] not in labels:
            continue
        if ids and c["id"] not in ids:
            continue
        out.append(c)
    return out


def inputs(c: dict, cid: str | None = None) -> tuple[dict, TestRun]:
    case = {"id": cid or c["id"], "repo": c["repo"], "issue": c["issue"], "commit": c["commit"], "diff": c["diff"],
            "context": c["context"]}
    t = c["tests"]
    return case, TestRun(t["image"], tuple(t["command"]), t["exit_code"], t["results_sha256"], t["logs_sha256"])


TOPICS = ["tide pools", "bread baking", "railway signals", "bee colonies", "glaciers", "chess openings", "lighthouses",
          "compost", "violin making", "solar eclipses", "map projections", "bicycle gears", "coral reefs", "typefaces"]


def fillers(n: int, cases: list[dict], rng: random.Random) -> list[dict]:
    """Other traffic on the same server: judge prompts of other cases under another id (so a different nonce and no
    shared prefix), and short free-text requests of varied length. Sampled without a seed, so their lengths vary."""
    out = []
    for i in range(n):
        if i % 2 == 0:
            out.append({"kind": "filler-judge", "case": rng.choice(cases), "cid": f"filler-{rng.getrandbits(48):012x}"})
        else:
            words = rng.choice([20, 60, 150, 300])
            out.append({"kind": "filler-text", "user": f"Write about {rng.choice(TOPICS)} in about {words} words.",
                        "max_tokens": words * 2})
    return out


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def call_case(judge: J.DirectJudge, c: dict, meta: dict, cid: str | None = None) -> dict:
    case, tests = inputs(c, cid)
    t0 = time.monotonic()
    answer = judge.judge(case, tests)
    latency = time.monotonic() - t0
    raw = json.loads(_seen.reply.body.decode())
    choice = (raw.get("choices") or [{}])[0]
    token_ids = choice.get("token_ids")
    verdict = P.parse(answer.response)
    u = answer.usage or {}
    return {**meta, "case": c["id"], "check_id": case["id"], "label": c["label"], "text": answer.response, "text_sha256": sha(answer.response),
            "token_ids_sha256": sha(json.dumps(token_ids)) if token_ids is not None else None,
            "solves": answer.solves, "verdict_error": verdict.get("error"), "probability": verdict.get("probability"),
            "constitutional": verdict.get("constitutional"), "prompt_sha256": sha(answer.prompt),
            "prompt_tokens": u.get("input_tokens"), "completion_tokens": u.get("output_tokens"),
            "latency_s": round(latency, 3), "finish": (answer.inference or {}).get("stop"),
            "timings": raw.get("timings"), "system_fingerprint": raw.get("system_fingerprint")}


def call_filler(base: str, model: str, engine: str, f: dict) -> None:
    if f["kind"] == "filler-judge":
        judge = judge_for(base, model, sampling_body(engine, "qwen", None))
        case, tests = inputs(f["case"], f["cid"])
        judge.judge(case, tests)
        return
    body = {"model": model, "max_tokens": f["max_tokens"], "temperature": 0.9,
            "messages": [{"role": "system", "content": "You are a helpful assistant."},
                         {"role": "user", "content": f["user"]}]}
    M.http_request("POST", base.rstrip("/") + "/chat/completions", {"Content-Type": "application/json"},
                   json.dumps(body).encode(), 900)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="the server's OpenAI base URL, e.g. http://127.0.0.1:8000/v1")
    ap.add_argument("--engine", choices=("vllm", "llama"), required=True)
    ap.add_argument("--model", default="qwen2.5-7b-instruct")
    ap.add_argument("--tag", required=True, help="results/<tag>.jsonl (appended)")
    ap.add_argument("--setup", default="", help="free text recorded with each call: engine flags, threads, ...")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--fillers", type=int, default=0, help="filler requests per round, mixed with the cases")
    ap.add_argument("--sampling", default="greedy")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--labels", default="", help="comma-separated: good,bad,borderline (default all)")
    ap.add_argument("--ids", default="", help="comma-separated case IDs (default all)")
    ap.add_argument("--extra", default="{}", help="more request fields as JSON, e.g. {\"cache_prompt\": false}")
    ap.add_argument("--shuffle-seed", type=int, default=0)
    ap.add_argument("--vary-id", action="store_true",
                    help="give each repeat its own check ID (so its own untrusted-text markers, as a live check does)")
    a = ap.parse_args()

    cases = load_cases([s for s in a.labels.split(",") if s] or None, [s for s in a.ids.split(",") if s] or None)
    extra = {**sampling_body(a.engine, a.sampling, a.seed), **json.loads(a.extra)}
    RESULTS.mkdir(exist_ok=True)
    out = (RESULTS / f"{a.tag}.jsonl").open("a")
    lock = threading.Lock()
    judge = judge_for(a.base, a.model, extra)
    started = time.time()
    n = 0
    for rep in range(a.reps):
        rng = random.Random(a.shuffle_seed * 1000 + rep)
        work = [{"kind": "case", "case": c} for c in cases] + fillers(a.fillers, load_cases(None, None), rng)
        if a.concurrency > 1:
            rng.shuffle(work)
        meta = {"tag": a.tag, "engine": a.engine, "setup": a.setup, "rep": rep, "concurrency": a.concurrency,
                "fillers": a.fillers, "sampling": a.sampling, "seed": a.seed, "request_extra": extra}

        def one(w):
            nonlocal n
            if w["kind"] != "case":
                call_filler(a.base, a.model, a.engine, w)
                return
            cid = f"{w['case']['id']}-v{rep}" if a.vary_id else None
            rec = call_case(judge, w["case"], {**meta, "at": round(time.time() - started, 3)}, cid)
            with lock:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                n += 1

        if a.concurrency == 1:
            for w in work:
                one(w)
        else:
            with ThreadPoolExecutor(a.concurrency) as pool:
                list(pool.map(one, work))
        print(f"{a.tag}: rep {rep + 1}/{a.reps} done, {n} case calls, {time.time() - started:.0f}s", flush=True)
    out.close()


if __name__ == "__main__":
    main()
