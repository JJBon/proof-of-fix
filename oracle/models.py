"""Direct model calls (proof-of-fix#118): a counted judge asks its model provider itself, over TLS that ends in the
judge's own node, not in a proxy (the AgentCore gateway stays for development and B1). That is what lets a receipt,
and later an attestation (#94), say "this prompt got this answer from this provider". Standard library only.

Providers (ADR 0003: any provider works; Bedrock is just the AWS adapter):
    bedrock    Amazon Bedrock Runtime's Converse API, signed with AWS Signature Version 4 (hashlib/hmac here).
               Credentials: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN, else the instance role's
               through IMDSv2 (refreshed before they expire). Region: AWS_REGION (or AWS_DEFAULT_REGION).
    anthropic  Anthropic's Messages API (x-api-key).
    openai     OpenAI's Chat Completions; with ORACLE_MODEL_URL any OpenAI-compatible server (a self-hosted vLLM or
               llama.cpp server for #125). The key is optional off api.openai.com.
    gemini     Google's Gemini API, generateContent (x-goog-api-key).

The API key (MODEL_API_KEY, or a file named by MODEL_API_KEY_FILE) is sent only as its header: never in a URL, never
logged, never in an error. Usage is the provider's own count from its response, untouched (`reported`), plus the
normalised input/cached/output tokens the meter takes.

Spending guards (per process, so per on-demand run of the validator kit):
    ORACLE_MAX_TOKENS      the answer's cap per verdict (default 4000)
    ORACLE_MAX_CALLS       attempts at most, retries included (default 20)
    ORACLE_MAX_RUN_TOKENS  tokens at most, in plus out; before each attempt its worst case (the prompt's estimate plus
                           the answer's cap) must fit what's left (default 500000)
    ORACLE_MODEL_TIMEOUT   seconds per attempt (default 120)
    ORACLE_MODEL_RETRIES   retries of a throttled, overloaded or timed-out call (default 2), with backoff that honours
                           Retry-After up to 30 s; any other 4xx is never retried
    ORACLE_MODEL_ALLOW     the model IDs (or ARNs) this node may call, comma-separated: required for bedrock (it mirrors
                           the IAM policy's resources), checked for the others when set
    ORACLE_MODEL_URL       the provider's base URL (default: its public endpoint): https, or http on loopback only
    ORACLE_MODEL_LIMIT_FIELD  openai: the request field capping the answer (default max_completion_tokens; some
                           OpenAI-compatible servers want max_tokens)

No proxy (environment proxies are ignored) and no redirects are followed: the connection goes to the endpoint named."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import http.client
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import quote, urlsplit

PROVIDERS = ("bedrock", "anthropic", "openai", "gemini")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
DEFAULT_MAX_TOKENS, DEFAULT_MAX_CALLS, DEFAULT_MAX_RUN_TOKENS = 4000, 20, 500_000
DEFAULT_TIMEOUT_S, DEFAULT_RETRIES, MAX_BACKOFF_S = 120.0, 2, 30.0
RETRYABLE = {408, 429, 500, 502, 503, 504, 529}  # throttled, overloaded, or the provider's own failure
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
CHARS_PER_TOKEN = 3.5  # pof.judges.plan's estimate; only for the budget's worst case before a call


class ModelError(RuntimeError):
    """A model call that didn't give an answer. The message never holds the API key or a signature."""

    def __init__(self, message: str, status: int = 0, kind: str = "", request_id: str = "", retryable: bool = False):
        super().__init__(message)
        self.status, self.kind, self.request_id, self.retryable = status, kind, request_id, retryable
        self.retry_after: Optional[float] = None  # seconds, from the provider's Retry-After


class BudgetExceeded(ModelError):
    """This process's call or token budget is spent: no further calls."""


class ConfigError(ValueError):
    """The direct judge's configuration is incomplete or not allowed."""


# ---------- HTTP (no proxies, no redirects) ----------

@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict  # lower-cased names
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # a 3xx comes back as an error: the request (and its key) goes nowhere else


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def http_request(method: str, url: str, headers: dict, body: Optional[bytes], timeout: float) -> Reply:
    """One HTTP exchange. Raises OSError (socket.timeout, URLError) when there's no reply at all."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return Reply(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(MAX_RESPONSE_BYTES))
    except urllib.error.HTTPError as e:
        try:
            data = e.read(MAX_RESPONSE_BYTES)
        finally:
            e.close()
        return Reply(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, data)


def check_endpoint(url: str) -> str:
    """The endpoint's host, if a judge may call it: https anywhere, http only on loopback (a model server beside the
    node). No user info in the URL: keys go in headers."""
    u = urlsplit(url)
    if u.username or u.password:
        raise ConfigError("the model URL carries credentials; put the key in MODEL_API_KEY instead")
    if u.scheme == "https" or (u.scheme == "http" and (u.hostname or "") in LOOPBACK):
        return u.netloc
    raise ConfigError(f"model URL {u.scheme}://{u.hostname}: https only (http on loopback)")


# ---------- AWS Signature Version 4 ----------

@dataclass(frozen=True)
class AwsCredentials:
    access_key: str
    secret_key: str = field(repr=False)
    token: str = field(default="", repr=False)
    expires: Optional[float] = None  # epoch seconds, for the instance role's


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    return _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode(), date), region), service), "aws4_request")


def _canonical_query(query: str) -> str:
    pairs = []
    for part in query.split("&") if query else []:
        k, _, v = part.partition("=")
        pairs.append((quote(k, safe="-_.~"), quote(v, safe="-_.~")))
    return "&".join(f"{k}={v}" for k, v in sorted(pairs))


def sigv4(method: str, url: str, headers: dict, body: bytes, creds: AwsCredentials, region: str, service: str,
          now: datetime.datetime) -> dict:
    """The headers that sign this request (Authorization, X-Amz-Date, X-Amz-Security-Token with temporary
    credentials, Host), added to `headers`. The path is URI-encoded once more for the canonical request, as every
    service but S3 wants (so Bedrock's ".../model/<id with %3A>/converse" signs as %253A)."""
    u = urlsplit(url)
    host = u.netloc.lower()
    if (u.scheme, u.port) in (("https", 443), ("http", 80)):
        host = u.hostname
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    out = {k: v for k, v in headers.items() if k.lower() not in ("authorization", "x-amz-date", "x-amz-security-token",
                                                                   "host")}
    out["Host"], out["X-Amz-Date"] = host, amz_date
    if creds.token:
        out["X-Amz-Security-Token"] = creds.token
    canon = {}
    for k, v in out.items():
        canon[k.lower().strip()] = " ".join(str(v).strip().split())
    signed = ";".join(sorted(canon))
    request = "\n".join([method, quote(u.path or "/", safe="/-_.~"), _canonical_query(u.query),
                         "".join(f"{k}:{canon[k]}\n" for k in sorted(canon)), signed,
                         hashlib.sha256(body or b"").hexdigest()])
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(request.encode()).hexdigest()])
    signature = hmac.new(signing_key(creds.secret_key, amz_date[:8], region, service), to_sign.encode(),
                         hashlib.sha256).hexdigest()
    out["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={creds.access_key}/{scope}, SignedHeaders={signed}, "
                            f"Signature={signature}")
    return out


def credentials_from_env(env) -> Optional[AwsCredentials]:
    key, secret = env.get("AWS_ACCESS_KEY_ID"), env.get("AWS_SECRET_ACCESS_KEY")
    if key and secret:
        return AwsCredentials(key, secret, env.get("AWS_SESSION_TOKEN", ""))
    return None


class InstanceRoleCredentials:
    """The instance role's temporary credentials from IMDSv2 (a session token first, then the role's credentials),
    cached until five minutes before they expire. `endpoint`: AWS_EC2_METADATA_SERVICE_ENDPOINT, as the AWS SDKs."""

    def __init__(self, endpoint: str = "http://169.254.169.254", request=http_request, clock=time.time):
        self.endpoint, self.request, self.clock = endpoint.rstrip("/"), request, clock
        self._creds: Optional[AwsCredentials] = None

    def _get(self, path: str, token: str) -> str:
        r = self.request("GET", self.endpoint + path, {"X-aws-ec2-metadata-token": token}, None, 2.0)
        if r.status != 200:
            raise ModelError(f"instance metadata {path}: HTTP {r.status}", r.status, "imds")
        return r.body.decode()

    def __call__(self) -> AwsCredentials:
        c = self._creds
        if c is not None and (c.expires is None or c.expires - self.clock() > 300):
            return c
        try:
            r = self.request("PUT", self.endpoint + "/latest/api/token",
                             {"X-aws-ec2-metadata-token-ttl-seconds": "300"}, b"", 2.0)
            if r.status != 200:
                raise ModelError(f"instance metadata token: HTTP {r.status} (IMDSv2 reachable? hop limit?)", r.status,
                                 "imds")
            token = r.body.decode()
            base = "/latest/meta-data/iam/security-credentials/"
            role = self._get(base, token).strip().splitlines()[0]
            data = json.loads(self._get(base + role, token))
        except (OSError, http.client.HTTPException) as e:
            raise ModelError(f"instance metadata unreachable: {type(e).__name__}", 0, "imds") from None
        if data.get("Code", "Success") != "Success":
            raise ModelError(f"instance role credentials: {data.get('Code')}", 0, "imds")
        expires = datetime.datetime.strptime(data["Expiration"], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc).timestamp()
        self._creds = AwsCredentials(data["AccessKeyId"], data["SecretAccessKey"], data.get("Token", ""), expires)
        return self._creds


# ---------- the providers ----------

def _usage(inp, out, cached, reported) -> dict:
    """The meter's fields (input includes cached reads; output includes thinking) and the provider's own object."""
    return {"input_tokens": int(inp or 0), "output_tokens": int(out or 0), "cached_tokens": int(cached or 0),
            "reported": reported}


@dataclass
class Provider:
    """One provider's request and response shapes. `build` runs per attempt (Bedrock signs with the current time)."""
    name: str
    model: str
    base: str
    api_key: str = field(default="", repr=False)
    request_id_header: str = ""

    @property
    def endpoint(self) -> str:
        return check_endpoint(self.base)

    def build(self, system: str, user: str, max_tokens: int) -> tuple:
        raise NotImplementedError

    def parse(self, data: dict) -> tuple:
        """(text, usage, stop reason, request ID from the body)."""
        raise NotImplementedError

    def error(self, data) -> tuple:
        """(kind, message) from an error body."""
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("type") or err.get("status") or err.get("code") or ""), str(err.get("message", ""))
        return "", str(data.get("message", "")) if isinstance(data, dict) else ""

    @staticmethod
    def _json(body: dict) -> bytes:
        return json.dumps(body, separators=(",", ":")).encode()


class Bedrock(Provider):
    def __init__(self, model: str, region: str, credentials: Callable[[], AwsCredentials], base: str = "",
                 clock=None):
        super().__init__("bedrock", model, base or f"https://bedrock-runtime.{region}.amazonaws.com", "",
                         "x-amzn-requestid")
        self.region, self.credentials = region, credentials
        self.clock = clock or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def build(self, system, user, max_tokens):
        url = f"{self.base.rstrip('/')}/model/{quote(self.model, safe='')}/converse"
        body = self._json({"system": [{"text": system}], "messages": [{"role": "user", "content": [{"text": user}]}],
                           "inferenceConfig": {"maxTokens": max_tokens}})
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        return url, sigv4("POST", url, headers, body, self.credentials(), self.region, "bedrock", self.clock()), body

    def parse(self, data):
        content = ((data.get("output") or {}).get("message") or {}).get("content") or []
        text = "".join(b.get("text", "") for b in content if isinstance(b, dict))
        u = data.get("usage") or {}
        cached = u.get("cacheReadInputTokens") or 0
        inp = (u.get("inputTokens") or 0) + cached + (u.get("cacheWriteInputTokens") or 0)
        return text, _usage(inp, u.get("outputTokens"), cached, u), data.get("stopReason", ""), ""

    def error(self, data):
        return "", str(data.get("message") or data.get("Message") or "") if isinstance(data, dict) else ""


class Anthropic(Provider):
    def __init__(self, model: str, api_key: str, base: str = ""):
        super().__init__("anthropic", model, base or "https://api.anthropic.com", api_key, "request-id")

    def build(self, system, user, max_tokens):
        body = self._json({"model": self.model, "max_tokens": max_tokens, "system": system,
                           "messages": [{"role": "user", "content": user}]})
        headers = {"Content-Type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        return f"{self.base.rstrip('/')}/v1/messages", headers, body

    def parse(self, data):
        text = "".join(b.get("text", "") for b in data.get("content") or [] if b.get("type") == "text")
        u = data.get("usage") or {}
        cached = u.get("cache_read_input_tokens") or 0
        inp = (u.get("input_tokens") or 0) + cached + (u.get("cache_creation_input_tokens") or 0)
        return text, _usage(inp, u.get("output_tokens"), cached, u), data.get("stop_reason") or "", data.get("id", "")


class OpenAI(Provider):
    def __init__(self, model: str, api_key: str = "", base: str = "", limit_field: str = "max_completion_tokens"):
        super().__init__("openai", model, base or "https://api.openai.com/v1", api_key, "x-request-id")
        self.limit_field = limit_field

    def build(self, system, user, max_tokens):
        body = self._json({"model": self.model, self.limit_field: max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return f"{self.base.rstrip('/')}/chat/completions", headers, body

    def parse(self, data):
        choice = (data.get("choices") or [{}])[0]
        u = data.get("usage") or {}
        cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        return ((choice.get("message") or {}).get("content") or "", _usage(u.get("prompt_tokens"),
                u.get("completion_tokens"), cached, u), choice.get("finish_reason") or "", data.get("id", ""))


class Gemini(Provider):
    def __init__(self, model: str, api_key: str, base: str = ""):
        super().__init__("gemini", model, base or "https://generativelanguage.googleapis.com/v1beta", api_key, "")

    def build(self, system, user, max_tokens):
        body = self._json({"systemInstruction": {"parts": [{"text": system}]},
                           "contents": [{"role": "user", "parts": [{"text": user}]}],
                           "generationConfig": {"maxOutputTokens": max_tokens}})
        url = f"{self.base.rstrip('/')}/models/{quote(self.model, safe='-._~')}:generateContent"
        return url, {"Content-Type": "application/json", "x-goog-api-key": self.api_key}, body

    def parse(self, data):
        cand = (data.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))  # thought summaries aren't the answer
        u = data.get("usageMetadata") or {}
        out = (u.get("candidatesTokenCount") or 0) + (u.get("thoughtsTokenCount") or 0)  # thinking is billed as output
        return (text, _usage(u.get("promptTokenCount"), out, u.get("cachedContentTokenCount"), u),
                cand.get("finishReason") or "", data.get("responseId", ""))


# ---------- the guards and the call ----------

@dataclass
class Budget:
    """This process's spending cap: attempts, and tokens in plus out (the worst case reserved before each attempt)."""
    max_calls: int = DEFAULT_MAX_CALLS
    max_tokens: int = DEFAULT_MAX_RUN_TOKENS
    calls: int = 0
    tokens: int = 0

    def reserve(self, worst_case: int) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"model budget spent: {self.calls} of {self.max_calls} calls (ORACLE_MAX_CALLS)",
                                 kind="budget")
        if self.tokens + worst_case > self.max_tokens:
            raise BudgetExceeded(f"model budget spent: {self.tokens:,} tokens used, the next call may take "
                                 f"{worst_case:,} of {self.max_tokens:,} (ORACLE_MAX_RUN_TOKENS)", kind="budget")
        self.calls += 1

    def spend(self, tokens: int) -> None:
        self.tokens += tokens


@dataclass(frozen=True)
class Completion:
    text: str
    usage: dict
    inference: dict  # provider, model, endpoint, request_id, stop: for the receipt


class Client:
    """Calls one provider within the guards: the answer's cap, the budget, a timeout per attempt, and bounded retries
    with backoff for throttling, overload and timeouts only."""

    def __init__(self, provider: Provider, max_tokens: int = DEFAULT_MAX_TOKENS, budget: Optional[Budget] = None,
                 timeout: float = DEFAULT_TIMEOUT_S, retries: int = DEFAULT_RETRIES, request=http_request,
                 sleep=time.sleep, log=None):
        if max_tokens < 1 or retries < 0 or timeout <= 0:
            raise ConfigError("ORACLE_MAX_TOKENS, ORACLE_MODEL_RETRIES and ORACLE_MODEL_TIMEOUT must be positive")
        provider.endpoint  # noqa: B018 - refuses a URL that isn't https (or http on loopback) before any call
        self.provider, self.max_tokens, self.budget = provider, max_tokens, budget or Budget()
        self.timeout, self.retries, self.request, self.sleep = timeout, retries, request, sleep
        self.log = log or (lambda m: None)

    def _rid(self, reply: Optional[Reply]) -> str:
        h = self.provider.request_id_header
        return (reply.headers.get(h, "") if reply is not None and h else "") or ""

    def complete(self, system: str, user: str) -> Completion:
        p = self.provider
        worst = math.ceil((len(system) + len(user)) / CHARS_PER_TOKEN) + self.max_tokens
        last = ModelError("no attempt")
        for attempt in range(self.retries + 1):
            if attempt:
                wait = min(MAX_BACKOFF_S, 2.0 ** attempt)
                if last.retry_after is not None:
                    wait = min(MAX_BACKOFF_S, max(wait, last.retry_after))
                self.log(f"model {p.name}:{p.model}: {last}; retry {attempt} of {self.retries} in {wait:.0f}s")
                self.sleep(wait)
            self.budget.reserve(worst)
            url, headers, body = p.build(system, user, self.max_tokens)
            try:
                reply = self.request("POST", url, headers, body, self.timeout)
            except (OSError, http.client.HTTPException) as e:  # no reply: it may have run, so its worst case counts
                self.budget.spend(worst)
                last = ModelError(f"{p.name} call failed: {type(e).__name__}", 0, "network", retryable=True)
                continue
            try:
                data = json.loads(reply.body.decode() or "{}")
            except ValueError:
                data = {}
            rid = self._rid(reply)
            if reply.status == 200 and isinstance(data, dict) and data:
                text, usage, stop, body_id = p.parse(data)
                self.budget.spend(usage["input_tokens"] + usage["output_tokens"])
                info = {"provider": p.name, "model": p.model, "endpoint": urlsplit(url).netloc,
                        "request_id": rid or body_id, "stop": stop}
                return Completion(text, usage, info)
            kind, message = p.error(data) if data else ("", reply.body[:200].decode(errors="replace"))
            kind = kind or reply.headers.get("x-amzn-errortype", "").split(":")[0]
            last = ModelError(f"{p.name} refused the call: HTTP {reply.status} {kind} {message[:300]}".rstrip(),
                              reply.status, kind, rid, reply.status in RETRYABLE)
            try:
                last.retry_after = float(reply.headers.get("retry-after", ""))
            except ValueError:
                pass
            if not last.retryable:
                raise last
        raise last


# ---------- configuration ----------

def api_key_from_env(env) -> str:
    path = env.get("MODEL_API_KEY_FILE")
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return env.get("MODEL_API_KEY", "").strip()


def provider_from_env(name: str, model: str, env, request=http_request) -> Provider:
    if name not in PROVIDERS:
        raise ConfigError(f"model provider {name!r}: one of {', '.join(PROVIDERS)}")
    if not model:
        raise ConfigError("ORACLE_JUDGE=direct:<provider>:<model>: the model ID is missing")
    allow = [m.strip() for m in env.get("ORACLE_MODEL_ALLOW", "").split(",") if m.strip()]
    if name == "bedrock" and not allow:
        raise ConfigError("bedrock: set ORACLE_MODEL_ALLOW to the model IDs the node's IAM policy allows")
    if allow and model not in allow:
        raise ConfigError(f"model {model!r} isn't in ORACLE_MODEL_ALLOW")
    base = env.get("ORACLE_MODEL_URL", "")
    if name == "bedrock":
        region = env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION")
        if not region:
            raise ConfigError("bedrock: set AWS_REGION")
        creds = credentials_from_env(env)
        source = (lambda: creds) if creds else InstanceRoleCredentials(
            env.get("AWS_EC2_METADATA_SERVICE_ENDPOINT", "http://169.254.169.254"), request)
        return Bedrock(model, region, source, base)
    key = api_key_from_env(env)
    if name == "openai":
        if not key and not base:
            raise ConfigError("openai: set MODEL_API_KEY (or ORACLE_MODEL_URL for a server that needs none)")
        return OpenAI(model, key, base, env.get("ORACLE_MODEL_LIMIT_FIELD") or "max_completion_tokens")
    if not key:
        raise ConfigError(f"{name}: set MODEL_API_KEY or MODEL_API_KEY_FILE")
    return (Anthropic if name == "anthropic" else Gemini)(model, key, base)


def client_from_env(spec: str, env, request=http_request, sleep=time.sleep) -> Client:
    """`direct:<provider>:<model>` (the model ID may itself hold colons, e.g. Bedrock's "...-v1:0")."""
    _, name, model = (spec.split(":", 2) + ["", ""])[:3]
    provider = provider_from_env(name, model, env, request)

    def number(key, default, kind=int):
        try:
            return kind(env.get(key) or default)
        except ValueError:
            raise ConfigError(f"{key} must be a number") from None

    budget = Budget(number("ORACLE_MAX_CALLS", DEFAULT_MAX_CALLS), number("ORACLE_MAX_RUN_TOKENS",
                                                                          DEFAULT_MAX_RUN_TOKENS))
    return Client(provider, number("ORACLE_MAX_TOKENS", DEFAULT_MAX_TOKENS), budget,
                  number("ORACLE_MODEL_TIMEOUT", DEFAULT_TIMEOUT_S, float),
                  number("ORACLE_MODEL_RETRIES", DEFAULT_RETRIES), request, sleep)


__all__ = ["AwsCredentials", "Anthropic", "Bedrock", "Budget", "BudgetExceeded", "Client", "Completion",
           "ConfigError", "Gemini", "InstanceRoleCredentials", "ModelError", "OpenAI", "Provider", "Reply",
           "client_from_env", "credentials_from_env", "http_request", "provider_from_env", "sigv4", "signing_key"]

