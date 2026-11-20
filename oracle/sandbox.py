"""A fix's tests, run where they can't reach anything (rule 4): a test image pinned by digest, no network, a read-only
filesystem, no capabilities, CPU, memory and process limits, a time limit. The results and the logs are hashed for the
receipt (design D3).

Two runners start the sandbox with the same guarantees (#116):
- `docker_runner`: the Docker CLI (a developer machine, the end-to-end runs);
- `DockerApi`: the Docker Engine API over its Unix socket, standard library only. The node's image has no Docker CLI;
  on a validator's host the node runs in a container given the host's socket, and starts each fix's tests in a
  sibling container through it (validator-kit/terraform/node-user-data.sh.tftpl). The fix's code never sees the
  socket: only the node does.

The API runner fails closed: it refuses a daemon that can't enforce the limits (its /info: a rootless engine without
cgroups accepts them silently and enforces none) and a container the daemon created without one of them.

`default_runner()` picks the CLI when there is one, else the socket (ORACLE_SANDBOX=cli|api overrides). A sibling
container's bind mount is resolved by the host's Docker, so the fixes' checkouts must sit at the same path inside the
node's container as on the host (the kit mounts /var/lib/pof-node at /var/lib/pof-node). The run trees of protected
tests (oracle/runtree.py, #251 L20) are made under the same root for the same reason.

Two runs (#251 L22): `run_tests` runs the command twice on the same tree, each in a fresh container, one after the
other, and both always run. Each gets half the check's time limit (the profile's `timeoutSeconds`), so FeesV3's
worst-case deposit stays a true bound. The tests pass only if both exit 0; the receipt's `tests` records each run
(`runs`) and `flaky` when they disagree, and the time the node meters is the runs' sum."""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import quote

# Python 3.12 on Alpine: the same pinned image the loop tests fixes with (scripts/bounty-loop.sh).
TEST_IMAGE = "python@sha256:e6dae589c1c05976188fd3bd019afd091445fc533ed2ea29001beddc7368a9c8"
COMMAND = ("python", "-m", "unittest", "-q")
LIMITS = {"memory": "256m", "pids": "64", "cpus": "1", "tmp": "64m", "timeout_s": 300}
TIMED_OUT = 124  # the exit code of a run the outer time limit stopped, as coreutils' timeout reports it
RUNS = 2  # each check runs the tests this many times, each in a fresh container (#251 L22)


def _sha256_json(doc) -> str:
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Run:
    """One container's run of the tests."""
    exit_code: int
    results_sha256: str  # sha256 of this run's results record (its exit code, the image, the command)
    logs_sha256: str  # sha256 of its stdout and stderr
    seconds: float = 0.0  # how long it ran, as the node measured it (metered, not recorded)

    def record(self) -> dict:
        return {"exit_code": self.exit_code, "results_sha256": self.results_sha256, "logs_sha256": self.logs_sha256}


@dataclass(frozen=True)
class TestRun:
    """A check's test runs: the same command on the same tree, `runs` times (#251 L22). With protected paths (L20),
    the run tree's hash and the list; for a tests-only fix, `own` holds the runs of its own protected tests."""
    image: str
    command: tuple[str, ...]
    exit_code: int  # 0 when every run passed; else the first failing run's exit code
    results_sha256: str  # sha256 of the canonical results record (the runs', and the run tree's)
    logs_sha256: str  # sha256 of the runs' logs hashes
    runs: tuple = ()
    protected: tuple = ()  # the repository's protected paths, when it declares any (L20)
    run_tree: str = ""  # the git tree hash of the tree the tests ran on, with the base's protected paths
    not_run: int = 0  # how many of the fix's changed files were under protected paths, so not run
    own: Optional["TestRun"] = None  # a tests-only fix: its own protected tests' runs, which must pass too

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    @property
    def flaky(self) -> bool:
        """The runs on one tree disagreed: some passed, some didn't."""
        mine = len({r.exit_code == 0 for r in self.runs}) > 1
        return mine or (self.own is not None and self.own.flaky)

    @property
    def seconds(self) -> float:
        """The runs' time, summed: what the node meters (#251 L22)."""
        return sum(r.seconds for r in self.runs) + (self.own.seconds if self.own is not None else 0.0)

    def record(self) -> dict:
        out = {"image": self.image, "command": list(self.command), "exit_code": self.exit_code,
               "results_sha256": self.results_sha256, "logs_sha256": self.logs_sha256}
        if self.runs:
            out["runs"] = [r.record() for r in self.runs]
        if self.flaky:
            out["flaky"] = True
        if self.protected:
            out["protected"] = list(self.protected)
            out["run_tree"] = self.run_tree
            out["not_run"] = self.not_run
        if self.own is not None:
            out["tests_only"] = self.own.record()
        return out

    def with_tree(self, protected: tuple, run_tree: str, not_run: int = 0,
                  own: Optional["TestRun"] = None) -> "TestRun":
        """These runs, made on a run tree of protected paths (#251 L20): its list and hash, and for a tests-only fix
        its own tests' runs. The results hash then binds the tree, and both sets must pass."""
        exit_code = self.exit_code or (own.exit_code if own is not None else 0)
        results = _sha256_json({"exit_code": exit_code, "image": self.image, "command": list(self.command),
                                "runs": [r.results_sha256 for r in self.runs], "protected": list(protected),
                                "run_tree": run_tree, "tests_only": own.results_sha256 if own is not None else ""})
        logs = self.logs_sha256
        if own is not None:
            logs = hashlib.sha256(f"{self.logs_sha256}\n{own.logs_sha256}".encode()).hexdigest()
        return TestRun(self.image, self.command, exit_code, results, logs, self.runs, tuple(protected), run_tree,
                       not_run, own)


@dataclass(frozen=True)
class Spec:
    """One sandboxed run: what both runners start, flag for flag."""
    src: Path
    image: str
    command: tuple[str, ...]
    timeout_s: int = LIMITS["timeout_s"]
    memory: str = LIMITS["memory"]
    pids: int = int(LIMITS["pids"])
    cpus: str = LIMITS["cpus"]
    tmp: str = LIMITS["tmp"]
    user: str = ""  # empty: the image's user (root inside, with no capabilities); "65534:65534" runs as nobody
    env: tuple = field(default=(("PYTHONDONTWRITEBYTECODE", "1"),))

    def entrypoint(self) -> list:
        # The inner limit: the image's own timeout, so a run ends even if the outer limit doesn't fire. It needs the
        # init process (--init, "Init"): a container's PID 1 ignores SIGTERM, and Busybox's timeout execs the command.
        return ["timeout", str(self.timeout_s), *self.command]

    def argv(self) -> list:
        argv = ["docker", "run", "--rm", "--init", "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", str(self.pids), "--memory", self.memory,
                "--cpus", self.cpus, "--tmpfs", f"/tmp:rw,noexec,nosuid,size={self.tmp}"]
        if self.user:
            argv += ["--user", self.user]
        for k, v in self.env:
            argv += ["-e", f"{k}={v}"]
        return argv + ["-v", f"{Path(self.src).resolve()}:/src:ro", "-w", "/src", self.image, *self.entrypoint()]


Runner = Callable[[list], Tuple[int, str, str]]


def _inner_limit(argv: list) -> int:
    """The run's own time limit, from a Spec's argv (`-w /src <image> timeout <seconds> ...`); LIMITS' otherwise."""
    try:
        i = argv.index("-w")
        if argv[i + 1] == "/src" and argv[i + 3] == "timeout":
            return int(argv[i + 4])
    except (ValueError, IndexError):
        pass
    return int(LIMITS["timeout_s"])


def docker_runner(argv: list) -> Tuple[int, str, str]:
    name = ""
    if argv[:2] == ["docker", "run"]:  # named, so the outer limit can kill the container, not just the CLI
        name = f"pof-sandbox-{uuid.uuid4().hex[:12]}"
        argv = argv[:2] + ["--name", name] + argv[2:]
    try:  # the outer limit: the run's own and a margin, as DockerApi's wait (a run has half the check's, #251 L22)
        out = subprocess.run(argv, capture_output=True, text=True, timeout=_inner_limit(argv) + 30)
    except subprocess.TimeoutExpired:  # the outer limit; --rm removes the container once it's killed
        if name:
            subprocess.run(["docker", "kill", name], capture_output=True, timeout=60)
        return TIMED_OUT, "", "timed out"
    return out.returncode, out.stdout, out.stderr


def _bytes(size: str) -> int:
    units = {"k": 1024, "m": 1024**2, "g": 1024**3}
    s = size.strip().lower()
    return int(float(s[:-1]) * units[s[-1]]) if s[-1] in units else int(s)


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self._path)
        self.sock = sock


class DockerApi:
    """Starts a Spec through the Docker Engine API on its Unix socket (API v1.41: Docker 20.10 and later)."""

    VERSION = "v1.41"

    def __init__(self, socket_path: str = "/var/run/docker.sock", margin_s: int = 30) -> None:
        self.socket_path, self.margin_s = socket_path, margin_s
        self._daemon_ok = False

    def _call(self, method: str, path: str, body: Optional[dict] = None, timeout: float = 60.0,
              ok=(200, 201, 204, 304)) -> Tuple[int, bytes]:
        conn = _UnixConnection(self.socket_path, timeout)
        try:
            data = json.dumps(body).encode() if body is not None else None
            headers = {"Content-Type": "application/json"} if data is not None else {}
            conn.request(method, f"/{self.VERSION}{path}", body=data, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        finally:
            conn.close()
        if resp.status not in ok:
            raise RuntimeError(f"docker {method} {path}: {resp.status} {payload[:300]!r}")
        return resp.status, payload

    def ensure_image(self, image: str) -> None:
        status, _ = self._call("GET", f"/images/{quote(image, safe='')}/json", ok=(200, 404))
        if status == 200:
            return
        name, _, digest = image.partition("@")
        query = f"fromImage={quote(name, safe='')}" + (f"&tag={quote(digest, safe='')}" if digest else "")
        _, out = self._call("POST", f"/images/create?{query}", timeout=600)
        for line in out.splitlines():  # the daemon streams its progress; a failure arrives in the stream
            if line.strip() and json.loads(line).get("error"):
                raise RuntimeError(f"docker pull {image}: {json.loads(line)['error']}")

    def create_body(self, spec: Spec) -> dict:
        host = {"NetworkMode": "none", "ReadonlyRootfs": True, "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges"], "PidsLimit": spec.pids, "Memory": _bytes(spec.memory),
                "MemorySwap": _bytes(spec.memory), "NanoCpus": int(float(spec.cpus) * 1e9),
                "Tmpfs": {"/tmp": f"rw,noexec,nosuid,size={spec.tmp}"},
                "Binds": [f"{Path(spec.src).resolve()}:/src:ro"], "Init": True, "AutoRemove": False}
        body = {"Image": spec.image, "Cmd": spec.entrypoint(), "WorkingDir": "/src",
                "Env": [f"{k}={v}" for k, v in spec.env], "NetworkDisabled": True,
                "AttachStdout": False, "AttachStderr": False, "Tty": False, "HostConfig": host}
        if spec.user:
            body["User"] = spec.user
        return body

    @staticmethod
    def demux(raw: bytes) -> Tuple[str, str]:
        """Docker's multiplexed log stream (no TTY): frames of [stream, 0, 0, 0, size (4 bytes, big-endian)] + data."""
        out, err, i = [], [], 0
        while i + 8 <= len(raw):
            stream, size = raw[i], int.from_bytes(raw[i + 4:i + 8], "big")
            (err if stream == 2 else out).append(raw[i + 8:i + 8 + size])
            i += 8 + size
        return b"".join(out).decode(errors="replace"), b"".join(err).decode(errors="replace")

    def check_daemon(self) -> None:
        """Fails closed on a daemon that can't enforce the limits at all. A rootless engine without cgroups (cgroup v1,
        or no delegation) accepts a container's limits, reports them back, gives no warning and enforces none of them:
        only its /info says so (CgroupDriver "none", MemoryLimit false)."""
        if self._daemon_ok:
            return
        _, raw = self._call("GET", "/info")
        info = json.loads(raw)
        missing = [k for k in ("MemoryLimit", "CpuCfsQuota", "PidsLimit") if info.get(k) is not True]
        if info.get("CgroupDriver") in (None, "", "none"):
            missing.append("CgroupDriver")
        if missing:
            raise RuntimeError(f"sandbox refused: the Docker daemon can't enforce the limits ({', '.join(missing)}; "
                               f"a rootless engine needs cgroup v2 with cpu, memory and pids delegated)")
        self._daemon_ok = True

    def check_applied(self, spec: Spec, warnings, inspected: dict) -> None:
        """Fails closed: a daemon that warns about, or dropped, any of the sandbox's limits doesn't run the fix (a
        rootless engine without cgroup delegation, or an API proxy, can accept a container and discard a limit)."""
        if warnings:
            raise RuntimeError(f"sandbox refused: the Docker daemon warned {warnings!r}")
        want, got = self.create_body(spec)["HostConfig"], inspected.get("HostConfig") or {}
        wrong = [k for k in ("NetworkMode", "ReadonlyRootfs", "PidsLimit", "Memory", "NanoCpus", "Binds")
                 if got.get(k) != want[k]]
        if "ALL" not in [c.upper() for c in got.get("CapDrop") or []]:
            wrong.append("CapDrop")
        if not any(o.startswith("no-new-privileges") for o in got.get("SecurityOpt") or []):
            wrong.append("SecurityOpt")
        if got.get("Privileged"):
            wrong.append("Privileged")
        if wrong:
            raise RuntimeError(f"sandbox refused: the Docker daemon didn't apply {', '.join(wrong)}")

    def run_spec(self, spec: Spec) -> Tuple[int, str, str]:
        self.check_daemon()
        self.ensure_image(spec.image)
        _, created = self._call("POST", "/containers/create", self.create_body(spec))
        created = json.loads(created)
        cid = created["Id"]
        try:
            _, inspected = self._call("GET", f"/containers/{cid}/json")
            self.check_applied(spec, created.get("Warnings"), json.loads(inspected))
            self._call("POST", f"/containers/{cid}/start")
            try:
                _, waited = self._call("POST", f"/containers/{cid}/wait", timeout=spec.timeout_s + self.margin_s)
                code = int(json.loads(waited).get("StatusCode", 1))
            except (socket.timeout, TimeoutError):  # the outer limit: kill it
                self._call("POST", f"/containers/{cid}/kill", ok=(204, 304, 409))
                code = TIMED_OUT
            _, logs = self._call("GET", f"/containers/{cid}/logs?stdout=1&stderr=1")
            stdout, stderr = self.demux(logs)
            return code, stdout, stderr
        finally:
            self._call("DELETE", f"/containers/{cid}?force=1", ok=(204, 404, 409))

    def __call__(self, argv: list) -> Tuple[int, str, str]:
        raise TypeError("DockerApi runs a Spec (run_spec), not a Docker CLI argv")


def default_runner(env=os.environ):
    """The CLI when there's one, else the Docker socket; ORACLE_SANDBOX=cli|api picks one."""
    mode = env.get("ORACLE_SANDBOX", "")
    if mode == "api" or (mode != "cli" and not shutil.which("docker")):
        return DockerApi(env.get("DOCKER_SOCKET", "/var/run/docker.sock"))
    return docker_runner


def spec_for(src: Path, image: str = TEST_IMAGE, command: tuple = COMMAND, timeout_s: Optional[int] = None,
             env=os.environ) -> Spec:
    return Spec(Path(src), image, tuple(command), timeout_s=int(timeout_s or LIMITS["timeout_s"]),
                user=env.get("ORACLE_SANDBOX_USER", ""))


def nothing_ran() -> TestRun:
    """A check whose tests never ran (no fix to test, or one the node refused before running it)."""
    empty = hashlib.sha256(b"").hexdigest()
    return TestRun("none", (), 125, empty, empty)


def run_once(spec: Spec, runner, clock=None) -> Run:
    """One run of `spec` in a fresh container, by either runner. `clock`: time.monotonic by default."""
    clock = clock or time.monotonic
    started = clock()
    code, stdout, stderr = runner.run_spec(spec) if hasattr(runner, "run_spec") else runner(spec.argv())
    seconds = clock() - started
    logs = hashlib.sha256((stdout + "\n--stderr--\n" + stderr).encode()).hexdigest()
    results = _sha256_json({"exit_code": code, "image": spec.image, "command": list(spec.command)})
    return Run(code, results, logs, seconds)


def run_tests(src: Path, image: str = TEST_IMAGE, command: tuple = COMMAND, runner=None,
              timeout_s: Optional[int] = None, runs: int = RUNS, clock=None) -> TestRun:
    """Runs the fix's tests at `src` in the sandbox `runs` times (#251 L22), each in a fresh container, every one of
    them always, each with an equal share of `timeout_s`: the check's limit, the profile's `timeoutSeconds` (LIMITS'
    by default). They pass only if every run exits 0. `runner` is a CLI-style callable (argv → exit, stdout, stderr)
    or anything with run_spec (DockerApi); by default the CLI if installed, else the Docker socket."""
    runs = max(1, int(runs))
    total = int(timeout_s or LIMITS["timeout_s"])
    spec = spec_for(src, image, command, max(1, total // runs))
    runner = runner or default_runner()
    done = tuple(run_once(spec, runner, clock) for _ in range(runs))
    code = next((r.exit_code for r in done if r.exit_code != 0), 0)
    results = _sha256_json({"exit_code": code, "image": image, "command": list(command),
                            "runs": [r.results_sha256 for r in done]})
    logs = hashlib.sha256("\n".join(r.logs_sha256 for r in done).encode()).hexdigest()
    return TestRun(image, tuple(command), code, results, logs, done)
