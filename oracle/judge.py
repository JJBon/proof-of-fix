"""The judge: B1's prompt and verdict (pof.judges, #89) with the node's own evidence, and a backend that answers.

Reused, not copied:
- pof.judges.prompt: the system and user prompt (untrusted text quoted between per-check markers) and the verdict
  parser. The node's prompt is B1's with one line changed: B1's judges see no test run, a node does, so the closing
  "Test runs: not provided" line becomes the sandbox's result. B1's prompt and its plan hash are untouched.
- pof.judges.fake.FakeJudge: the deterministic stand-in, labelled by the node's own test run, and right with accuracy
  1.0 (an honest node) or 0.0 (`lie`: a dishonest or broken one).
- scripts/judge_run.py's Gateway, request builders and token helper: the AgentCore model gateway as the judges' client
  (`pof-judges-models`), Anthropic Messages or OpenAI chat per seat (pof.judges.plan.SEATS). A PAID call: never made by
  the tests (they inject a fake `post`), and only with the owner's approval. The network code stays in scripts/, as
  rule 1 keeps it out of pof/. For development and B1 only (ADR 0003).
- oracle/models.py: DirectJudge, a counted judge's backend (#118). The node calls its provider itself (Bedrock's
  Converse with the instance role, Anthropic, OpenAI or any OpenAI-compatible server, Gemini), within spending guards,
  and the provider's own token counts, model ID, endpoint and request ID go into the receipt. A PAID call too.

`judge_from_env` picks one from ORACLE_JUDGE: "fake" (the default), "gateway:<family>", or "direct:<provider>:<model>"."""

from __future__ import annotations

import importlib.util
import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from pof.judges import plan as PL
from pof.judges import prompt as P
from pof.judges.fake import FakeJudge as _B1Fake

from .sandbox import TestRun

ROOT = Path(__file__).resolve().parents[1]
NO_TESTS = "Test runs: not provided in this review. Decide from the issue, the diff and the code."


@dataclass(frozen=True)
class Answer:
    solves: bool
    model: str
    backend: str
    prompt: str  # system and user, as sent
    response: str  # the judge's raw answer
    usage: dict | None = None  # the provider's token counts (input_tokens, output_tokens), when it reports them
    inference: dict | None = None  # a direct call's provider, model, endpoint host, request ID and stop reason


def case_for(repo: str, issue: str, commit: str, diff: str, check_id: str | None = None, notes: tuple = ()) -> dict:
    """The evidence in pof.judges' case shape. A live check draws its id at random, so the untrusted-text markers
    can't be written against (B1 fixes them per case only to reproduce the measurement). `notes`: the node's own
    lines about that evidence (oracle/evidence.py). They sit outside the markers, so they must hold nothing a fix
    wrote: only numbers and verified commit ids."""
    return {"id": check_id or f"check-{secrets.token_hex(8)}", "repo": repo, "issue": issue, "commit": commit,
            "diff": diff, "context": [], "notes": tuple(notes)}


def build_prompt(case: dict, tests: TestRun) -> tuple[str, str]:
    system, user = P.messages(case)
    result = "passed" if tests.passed else f"failed (exit code {tests.exit_code})"
    line = (f"Test runs: the project's tests and the issue's acceptance test {result} in a sandbox with no network "
            f"(image {tests.image}, results sha256 {tests.results_sha256}). Decide from the issue, the diff, the code "
            f"and this result.")
    head, found, tail = user.rpartition(NO_TESTS)  # the template's closing line, never a copy of it in quoted text
    if not found:
        raise RuntimeError("pof.judges' prompt changed: update the node's test-run line")
    return system, head + "\n".join((line, *case.get("notes", ()))) + tail


def _answer(text: str, model: str, backend: str, system: str, user: str, usage: dict | None = None,
            inference: dict | None = None) -> Answer:
    verdict = P.parse(text)
    return Answer(verdict.get("solves") is True, model, backend, system + "\n\n" + user, text, usage, inference)


def refused(case: dict, tests: TestRun, why: str) -> Answer:
    """The verdict on a fix no judge can read (oracle/evidence.py): no pass, and no model call or token spent. The
    receipt holds the evidence as far as it went and the reason."""
    system, user = build_prompt(case, tests)
    text = json.dumps({"solves": False, "probability": 0, "constitutional": False, "reason": why,
                       "evidence": [{"file": "", "line": 0, "note": why}]})
    return Answer(False, "none", "node:evidence-refused", system + "\n\n" + user, text,
                  {"input_tokens": 0, "output_tokens": 0, "cached_tokens": 0})


class FakeJudge:
    """pof.judges' fake, labelled by the node's own test run: an honest node is right every time; `lie` inverts it.
    It reads nothing but the test run, so a node gathers no evidence for it (`reads_evidence`)."""

    reads_evidence = False

    def __init__(self, lie: bool = False, family: str = "fake"):
        self.lie, self.family = lie, family

    def judge(self, case: dict, tests: TestRun) -> Answer:
        system, user = build_prompt(case, tests)
        fake = _B1Fake(self.family, accuracy=0.0 if self.lie else 1.0, gullible=0.0)
        text = fake.answer({**case, "label": "good" if tests.passed else "bad"})
        return _answer(text, f"fake-judge-{self.family}" + ("-lying" if self.lie else ""), "fake", system, user)


def _judge_run():
    spec = importlib.util.spec_from_file_location("judge_run", ROOT / "scripts" / "judge_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GatewayJudge:
    """One seat (pof.judges.plan.SEATS) through the model gateway, with scripts/judge_run.py's client. `post` and
    `token` are injectable; by default the real gateway and the judges' token helper (a paid call)."""

    def __init__(self, family: str, url: str | None = None, token=None, post=None, max_tokens: int = 4000):
        run = _judge_run()
        self.seat: PL.Seat = PL.SEATS[family]
        self._request = run.request
        kwargs = {} if post is None else {"post": post}
        self.gateway = run.Gateway(url or run.GATEWAY, token or run.gateway_token(), **kwargs)
        self.max_tokens = max_tokens

    def judge(self, case: dict, tests: TestRun) -> Answer:
        system, user = build_prompt(case, tests)
        path, body = self._request(self.seat, system, user, self.max_tokens)
        text, usage = self.gateway.call(self.seat, path, json.dumps(body).encode())
        return _answer(text, self.seat.model, "gateway", system, user, usage)  # the meter's measured tokens


class DirectJudge:
    """A counted judge's backend (#118): the node's own call to its provider (oracle/models.py), no gateway. The
    usage is the provider's count from its response; `inference` names the provider, model, endpoint and request."""

    def __init__(self, client):
        self.client = client

    @property
    def log(self):
        return self.client.log

    @log.setter
    def log(self, fn):
        self.client.log = fn

    def judge(self, case: dict, tests: TestRun) -> Answer:
        system, user = build_prompt(case, tests)
        done = self.client.complete(system, user)
        p = self.client.provider
        return _answer(done.text, p.model, f"direct:{p.name}", system, user, done.usage, done.inference)


def judge_from_env(env):
    """ORACLE_JUDGE: "fake" (the default; ORACLE_LIE=1 inverts it), "gateway:<family>" (development and B1 only), or
    "direct:<provider>:<model>" with provider bedrock, anthropic, openai or gemini (oracle/models.py's settings)."""
    spec = env.get("ORACLE_JUDGE", "fake") or "fake"
    if spec.startswith("gateway:"):
        return GatewayJudge(spec.split(":", 1)[1], max_tokens=int(env.get("ORACLE_MAX_TOKENS") or 4000))
    if spec.startswith("direct:"):
        from . import models

        return DirectJudge(models.client_from_env(spec, env))
    if spec != "fake":
        raise ValueError(f"ORACLE_JUDGE={spec!r}: fake, gateway:<family> or direct:<provider>:<model>")
    return FakeJudge(lie=env.get("ORACLE_LIE") == "1")
