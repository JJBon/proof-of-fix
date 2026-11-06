"""B1's judging run (proof-of-fix#85 tasks 2.2 and 2.3): prompts every candidate family with every case of
data/judges/cases.jsonl (built by scripts/judge-set.sh), stores the verdicts, and prints the measurement.

    plan                 count each prompt's tokens and price the whole run at reports/costs-v1.md's prices; writes
                         reports/judges-v1.plan.json. Sends nothing.
    fake                 run the whole pipeline with pof.judges.fake (no model, no cost) into data/judges/fake/
    run --execute        THE PAID RUN. Only with the owner's approval of the plan: the environment variable
                         POF_JUDGE_RUN_APPROVED must equal the plan's hash, and the estimate must fit --max-usd.
                         Every call goes through the owner's model gateway (MODEL_GATEWAY_URL, agentcore#90) as
                         the judges caller pof-judges-models, whose token budget the gateway enforces. Hard
                         limits here too: before each call, the running total plus that call's worst case must
                         fit --max-tokens and --max-usd, or the run stops. Resumable.
    report [--dir D]     the tables from stored verdicts (default data/judges/verdicts/)

Nothing in pof/ reaches the network (rule 1); the calls live here, behind the approval.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pof.judges import analysis as A  # noqa: E402
from pof.judges import plan as PL  # noqa: E402
from pof.judges import prompt as P  # noqa: E402
from pof.judges.dataset import sha256  # noqa: E402
from pof.judges.fake import FakeJudge  # noqa: E402
from pof.judges.injection import KINDS, inject  # noqa: E402

DATA = ROOT / "data" / "judges"
PLAN = ROOT / "reports" / "judges-v1.plan.json"
GATEWAY = "https://models-xxtlwrjxy7.gateway.bedrock-agentcore.us-east-1.amazonaws.com/inference"
CLIENT_ID = "pof-judges-models"  # the gateway's judges caller (platform#192), with its own token budget
TOKEN_HELPER = Path.home() / "dev" / "agentcore" / "scripts" / "model-gateway-token.sh"


def load_cases() -> list[dict]:
    path = DATA / "cases.jsonl"
    if not path.exists():
        raise SystemExit("data/judges/cases.jsonl missing: run scripts/judge-set.sh build")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def all_cases(cases: list[dict]) -> list[dict]:
    """The clean cases, then every bad case once per kind of injection."""
    return cases + [inject(c, k) for c in cases if c["label"] == "bad" for k in KINDS]


def max_tokens(case: dict) -> int:
    return PL.OUTPUT[case["size"]]


# ---------- the plan ----------

def make_plan(cases: list[dict]) -> dict:
    counts = {}
    for c in all_cases(cases):
        system, user = P.messages(c)
        counts[c["id"]] = {"input": PL.tokens(system) + PL.tokens(user), "size": c["size"]}
    plan = {"prompt": P.prompt_hash(), "families": list(PL.SEATS),
            "seats": {f: vars(s) for f, s in PL.SEATS.items()}, "chars_per_token": PL.CHARS_PER_TOKEN,
            "output_tokens": PL.OUTPUT, "cases": counts}
    plan["hash"] = sha256(json.dumps(plan, sort_keys=True))[:16]
    return plan


def cmd_plan(_a) -> int:
    plan = make_plan(load_cases())
    PLAN.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for grade in ("judge", "cheap"):
        c = PL.cost(plan["cases"], grade)
        print(f"{grade}: {c['calls']} calls, {c['input_tokens']:,} tokens in, {c['output_tokens']:,} out, "
              f"${c['total']:.2f}  " + ", ".join(f"{f} ${v:.2f}" for f, v in c["families"].items()))
    print(f"plan {plan['hash']} written to {PLAN.relative_to(ROOT)}\n")
    print(PL.cost_table(plan["cases"]))
    return 0


# ---------- calling the models (through the gateway) ----------

class Refused(Exception):
    """The gateway refused a call: status and body."""

    def __init__(self, status: int, body: str):
        super().__init__(f"{status}: {body[:300]}")
        self.status, self.body = status, body

    @property
    def budget(self) -> bool:  # the gateway's token budget for the judges caller is spent: stop, don't retry
        return self.status == 429 and "budget" in self.body.lower()


def messages_request(seat: PL.Seat, system: str, user: str, limit: int) -> dict:
    """Anthropic Messages, for the gateway's /v1/messages."""
    return {"model": seat.model, "max_tokens": limit, "system": system,
            "messages": [{"role": "user", "content": user}]}


def messages_text(response: dict) -> tuple[str, dict]:
    """The answer's text (thinking blocks skipped) and its token usage."""
    text = "".join(b.get("text", "") for b in response.get("content") or [] if b.get("type") == "text")
    u = response.get("usage") or {}
    return text, {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens")}


def chat_request(seat: PL.Seat, system: str, user: str, limit: int) -> dict:
    """OpenAI chat completions, for the gateway's /v1/chat/completions."""
    return {"model": seat.model, seat.limit_field: limit,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}


def chat_text(response: dict) -> tuple[str, dict]:
    choice = (response.get("choices") or [{}])[0]
    u = response.get("usage") or {}
    return (choice.get("message", {}).get("content") or "",
            {"input_tokens": u.get("prompt_tokens"), "output_tokens": u.get("completion_tokens")})


def request(seat: PL.Seat, system: str, user: str, limit: int) -> tuple[str, dict]:
    """The gateway path and body for one judgment."""
    if seat.api == "messages":
        return "/v1/messages", messages_request(seat, system, user, limit)
    return "/v1/chat/completions", chat_request(seat, system, user, limit)


def http_post(url: str, headers: dict, body: bytes) -> tuple[int, str]:
    import urllib.error
    import urllib.request  # only here, behind the approval
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


class Gateway:
    """Calls the model gateway as the judges caller. `post(url, headers, body) -> (status, text)` and `token()` are
    injectable for tests."""

    def __init__(self, url: str, token, post=http_post):
        self.url, self.token, self.post = url.rstrip("/"), token, post

    def call(self, seat: PL.Seat, path: str, body: bytes) -> tuple[str, dict]:
        headers = {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}
        if seat.api == "messages":
            headers["anthropic-version"] = "2023-06-01"
        status, text = self.post(self.url + path, headers, body)
        if status != 200:
            raise Refused(status, text)
        response = json.loads(text)
        return messages_text(response) if seat.api == "messages" else chat_text(response)


def gateway_token(helper: Path = TOKEN_HELPER):
    """The judges caller's Keycloak token from agentcore's helper (scripts/model-gateway-token.sh), with its own
    cache; reused for 50 s. Sign in once: MODEL_GATEWAY_CLIENT_ID=pof-judges-models
    MODEL_GATEWAY_TOKEN_CACHE=~/.cache/agentcore/pof-judges-token.json <helper> login"""
    env = dict(os.environ, MODEL_GATEWAY_CLIENT_ID=CLIENT_ID, CLAUDE_CODE_API_KEY_HELPER_TTL_MS="60000",
               MODEL_GATEWAY_TOKEN_CACHE=str(Path.home() / ".cache" / "agentcore" / "pof-judges-token.json"))
    cached = {"token": "", "at": 0.0}

    def token() -> str:
        if time.time() - cached["at"] > 50:
            out = subprocess.run([str(helper)], env=env, capture_output=True, text=True, check=False)
            if out.returncode != 0:
                raise SystemExit(f"no model gateway token for {CLIENT_ID}: {out.stderr.strip()}")
            cached.update(token=out.stdout.strip(), at=time.time())
        return cached["token"]

    return token


# ---------- the run's hard limits ----------

def worst(seat_family: str, body: bytes, limit: int) -> tuple[int, float]:
    """A call's worst case, as the gateway counts it: input tokens at most the body's bytes, output at most its
    limit; and that at the family's judge-grade price."""
    m = PL.price(seat_family)
    return len(body) + limit, (len(body) * m.input + limit * m.output) / PL.C.M


def spent(family: str, usage: dict, fallback: tuple[int, float]) -> tuple[int, float]:
    """What a finished call used, from its reported usage; the worst case when the model reported none."""
    i, o = usage.get("input_tokens"), usage.get("output_tokens")
    if not isinstance(i, int) or not isinstance(o, int):
        return fallback
    m = PL.price(family)
    return i + o, (i * m.input + o * m.output) / PL.C.M


class Limits:
    """The run's own hard limits, checked before every call: running total + the next call's worst case."""

    def __init__(self, max_tokens: int, max_usd: float, tokens: int = 0, usd: float = 0.0):
        self.max_tokens, self.max_usd, self.tokens, self.usd = max_tokens, max_usd, tokens, usd

    def refusal(self, worst_tokens: int, worst_usd: float) -> str | None:
        if self.tokens + worst_tokens > self.max_tokens:
            return f"--max-tokens {self.max_tokens:,}: {self.tokens:,} used, the next call may use {worst_tokens:,}"
        if self.usd + worst_usd > self.max_usd:
            return f"--max-usd {self.max_usd}: ${self.usd:.2f} used, the next call may cost ${worst_usd:.2f}"
        return None

    def add(self, tokens: int, usd: float) -> None:
        self.tokens += tokens
        self.usd += usd


class Stop(Exception):
    """The run stops cleanly (a limit or the gateway's budget); what's stored stays, and a rerun resumes."""


def record(case: dict, family: str, text: str, usage: dict, model: str) -> dict:
    return {"case": case["id"], "instance": case["instance"], "label": case["label"], "family": family,
            "model": model, "injection": case.get("injection"), "verdict": P.parse(text), "usage": usage,
            "answer": text}


def judge(out: Path, families: list[str], answer) -> None:
    """Every family over every case, appended to out/<family>.jsonl, skipping what's already there."""
    out.mkdir(parents=True, exist_ok=True)
    cases = all_cases(load_cases())
    for f in families:
        path = out / f"{f}.jsonl"
        done = {json.loads(line)["case"] for line in path.read_text().splitlines()} if path.exists() else set()
        with path.open("a", encoding="utf-8") as fh:
            for c in cases:
                if c["id"] in done:
                    continue
                text, usage, model, *rest = answer(f, c)
                row = record(c, f, text, usage, model)
                if rest:
                    row["worst"] = list(rest[0])
                fh.write(json.dumps(row) + "\n")
                fh.flush()


def cmd_fake(_a) -> int:
    accuracy = {"anthropic": 0.85, "openai": 0.82, "google": 0.75, "deepseek": 0.78, "qwen": 0.72,
                "mistral": 0.7, "nvidia": 0.65}
    judges = {f: FakeJudge(f, accuracy[f]) for f in PL.SEATS}
    out = DATA / "fake"
    for old in out.glob("*.jsonl"):
        old.unlink()
    judge(out, list(PL.SEATS), lambda f, c: (judges[f].answer(c), {}, "fake"))
    return cmd_report(argparse.Namespace(dir=str(out)))


def approval(planned: str, current: str, approved: str | None) -> str | None:
    """Why the paid run must not start, or None: the plan must be the one the owner approved, and still current."""
    if current != planned:
        return (f"the cases or the prompt changed since the plan ({planned} -> {current}); run `plan` again and have "
                f"it approved")
    if approved != planned:
        return f"not approved: the owner sets POF_JUDGE_RUN_APPROVED={planned} after reviewing reports/judges-v1.md"
    return None


def prior_spend(directory: Path, families: list[str]) -> tuple[int, float]:
    """Tokens and dollars the stored verdicts already used (a resumed run counts them against its limits)."""
    tokens, usd = 0, 0.0
    for f in families:
        path = directory / f"{f}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            t, d = spent(f, r.get("usage") or {}, tuple(r.get("worst") or (0, 0.0)))
            tokens, usd = tokens + t, usd + d
    return tokens, usd


def answerer(gateway: Gateway, limits: Limits, sleep=time.sleep):
    """answer(family, case) for judge(): one call through the gateway inside the limits, with retries for
    throttling and transient errors; Stop when a limit or the gateway's budget is reached."""

    def answer(f: str, c: dict):
        seat = PL.SEATS[f]
        system, user = P.messages(c)
        path, payload = request(seat, system, user, max_tokens(c))
        body = json.dumps(payload).encode()
        w = worst(f, body, max_tokens(c))
        refusal = limits.refusal(*w)
        if refusal:
            raise Stop(f"stopped before {f} {c['id']}: {refusal}")
        for attempt in range(5):
            try:
                text, usage = gateway.call(seat, path, body)
            except Refused as e:
                if e.budget:
                    raise Stop(f"stopped: the gateway's token budget for {CLIENT_ID} is spent ({e})") from e
                if (e.status == 429 or e.status >= 500) and attempt < 4:
                    sleep(2 ** attempt * 5)
                    continue
                limits.add(*w)  # a refused call may still have been billed: count its worst case
                return f"ERROR {e}", {}, seat.model, w
            except (OSError, ValueError) as e:  # network errors, unreadable answers
                if attempt < 4:
                    sleep(2 ** attempt * 5)
                    continue
                limits.add(*w)
                return f"ERROR {type(e).__name__}: {e}", {}, seat.model, w
            limits.add(*spent(f, usage, w))
            return text, usage, seat.model, w

    return answer


def cmd_run(a) -> int:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    current = make_plan(load_cases())
    refusal = approval(plan["hash"], current["hash"], os.environ.get("POF_JUDGE_RUN_APPROVED"))
    if refusal:
        raise SystemExit(refusal)
    families = a.families.split(",") if a.families else list(PL.SEATS)
    estimate = PL.cost(plan["cases"], "judge", families)["total"]
    if estimate > a.max_usd:
        raise SystemExit(f"estimate ${estimate:.2f} is over --max-usd {a.max_usd}")
    out = DATA / "verdicts"
    limits = Limits(a.max_tokens, a.max_usd, *prior_spend(out, families))
    gateway = Gateway(os.environ.get("MODEL_GATEWAY_URL", GATEWAY), gateway_token())
    try:
        judge(out, families, answerer(gateway, limits))
    except Stop as e:
        print(f"{e}\n{limits.tokens:,} tokens and ${limits.usd:.2f} used so far; rerun to resume.", file=sys.stderr)
        return 3
    print(f"done: {limits.tokens:,} tokens, ${limits.usd:.2f}", file=sys.stderr)
    return cmd_report(argparse.Namespace(dir=str(out)))


# ---------- the report ----------

def load_verdicts(directory: Path) -> list[dict]:
    rows = []
    for path in sorted(directory.glob("*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return rows


def pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def tables(records: list[dict]) -> str:
    out = ["| Family | Cases | Accuracy | False passes | False fails | Invalid |", "|---|---|---|---|---|---|"]
    for f, s in A.per_family(records).items():
        out.append(f"| {f} | {s['n']} | {pct(s['accuracy'])} | {pct(s['false_pass'])} | {pct(s['false_fail'])} | "
                   f"{s['invalid']} |")
    fams = A.families(A.clean(records))
    agree = A.agreement(records)
    out += ["", "Both wrong on the same case (count), and P(column wrong | row wrong):", "",
            "| | " + " | ".join(fams) + " |", "|---" * (len(fams) + 1) + "|"]
    for a in fams:
        cells = [f"{agree[(a, b)]['both_wrong']} ({pct(agree[(a, b)]['wrong_given'])})" if a != b else "—" for b in fams]
        out.append(f"| {a} | " + " | ".join(cells) + " |")
    out += ["", "| Panel | Panels | Mean accuracy | Best | Worst |", "|---|---|---|---|---|"]
    for size, quorum in ((3, 2), (7, 5)):
        p = A.panels(records, size, quorum)
        out.append(f"| {quorum} of {size} | {len(p['panels'])} | {pct(p['mean'])} | {pct(p['best'])} | "
                   f"{pct(p['worst'])} |")
    inj = A.injection(records)
    kinds = sorted({k for (_, k) in inj["family"]})
    if kinds:
        out += ["", "Injection success (bad fixes failed when clean, passed when injected):", "",
                "| Judge | " + " | ".join(kinds) + " |", "|---" * (len(kinds) + 1) + "|"]
        for f in fams:
            out.append(f"| {f} | " + " | ".join(pct(inj['family'][(f, k)]['success']) for k in kinds) + " |")
        for size, quorum in ((3, 2), (7, 5)):
            out.append(f"| {quorum} of {size} panels | " +
                       " | ".join(pct(inj['panels'][(size, quorum, k)]['success']) for k in kinds) + " |")
    return "\n".join(out)


def cmd_report(a) -> int:
    records = load_verdicts(Path(a.dir))
    if not records:
        raise SystemExit(f"no verdicts in {a.dir}")
    print(tables(records))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scripts/judge_run.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan").set_defaults(fn=cmd_plan)
    sub.add_parser("fake").set_defaults(fn=cmd_fake)
    r = sub.add_parser("run")
    r.add_argument("--execute", action="store_true", required=True)
    r.add_argument("--max-usd", type=float, required=True, help="hard limit on the run's dollars (running total)")
    r.add_argument("--max-tokens", type=int, required=True,
                   help="hard limit on the run's tokens, input + output, counted as the gateway does")
    r.add_argument("--families", help="comma-separated subset of " + ",".join(PL.SEATS))
    r.set_defaults(fn=cmd_run)
    rep = sub.add_parser("report")
    rep.add_argument("--dir", default=str(DATA / "verdicts"))
    rep.set_defaults(fn=cmd_report)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
