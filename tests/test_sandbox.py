"""The sandbox a fix's tests run in (#116): the same limits through the Docker CLI and through the Docker socket's API,
which is how the node starts it from inside its own container on a validator's instance.

The API runner is tested against a fake Docker daemon on a Unix socket. `DockerFromANodeContainer` runs it for real:
a container standing in for the node (the node image's base, uid 10001, the host's socket, the checkouts at the same
path) starts the sandbox through the socket, and the sandbox can't reach the network, can't write the fix's code and
is stopped at its time limit. It runs where a Docker daemon is reachable and already has the pinned test image (no
pulls in a check); POF_DOCKER_TESTS=1 runs it anyway, POF_DOCKER_TESTS=0 skips it."""

from __future__ import annotations

import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from oracle import sandbox  # noqa: E402
from oracle.sandbox import TEST_IMAGE, TIMED_OUT, DockerApi, Spec, default_runner, run_tests, spec_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")


def frames(*parts):
    """Docker's multiplexed log stream: (stream, text) → [stream, 0, 0, 0, size] + data."""
    return b"".join(bytes([s, 0, 0, 0]) + len(t.encode()).to_bytes(4, "big") + t.encode() for s, t in parts)


class FakeDocker:
    """A Docker daemon on a Unix socket that records each call; enough of the API for one sandboxed run."""

    def __init__(self, have_image=True, exit_code=0, wait_s=0.0, pull_error="", warnings=None, drop=(), info=None):
        self.info = info or {"MemoryLimit": True, "CpuCfsQuota": True, "PidsLimit": True, "CgroupDriver": "systemd"}
        self.calls, self.have_image, self.exit_code, self.wait_s, self.pull_error = [], have_image, exit_code, wait_s, pull_error
        self.warnings, self.drop, self.created = warnings, drop, None  # what a daemon that discards limits does
        self.release = threading.Event()
        self.dir = tempfile.mkdtemp(prefix="pof-docker-")
        self.path = os.path.join(self.dir, "docker.sock")
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # a Unix socket has no client address to log
                pass

            def reply(self, status, body=b""):
                try:
                    self.send_response(status)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except BrokenPipeError:  # the client gave up waiting (the time-limit test)
                    pass

            def handle_one(self, method):
                size = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(size)) if size else None
                fake.calls.append((method, self.path, body))
                p = self.path.split("/", 2)[2]  # drop the /v1.41 prefix
                if p == "info":
                    return self.reply(200, json.dumps(fake.info).encode())
                if p.startswith("images/") and p.endswith("/json"):
                    return self.reply(200 if fake.have_image else 404, b"{}")
                if p.startswith("images/create"):
                    lines = [{"status": "Pulling"}] + ([{"error": fake.pull_error}] if fake.pull_error else [])
                    return self.reply(200, "\n".join(json.dumps(x) for x in lines).encode())
                if p == "containers/create":
                    fake.created = body
                    return self.reply(201, json.dumps({"Id": "c1", "Warnings": fake.warnings}).encode())
                if p == "containers/c1/json":
                    host = {k: v for k, v in fake.created["HostConfig"].items() if k not in fake.drop}
                    return self.reply(200, json.dumps({"Id": "c1", "HostConfig": host}).encode())
                if p.endswith("/wait"):
                    fake.release.wait(fake.wait_s)
                    return self.reply(200, json.dumps({"StatusCode": fake.exit_code}).encode())
                if p.startswith("containers/c1/logs"):
                    return self.reply(200, frames((1, "Ran 1 test\n"), (2, "OK\n"), (1, "done\n")))
                return self.reply(204)

            def do_GET(self):
                self.handle_one("GET")

            def do_POST(self):
                self.handle_one("POST")

            def do_DELETE(self):
                self.handle_one("DELETE")

        self.server = socketserver.ThreadingUnixStreamServer(self.path, Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def paths(self):
        return [(m, p.split("?")[0]) for m, p, _ in self.calls]

    def close(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.dir, ignore_errors=True)


class DockerApiRunner(unittest.TestCase):
    def fake(self, **kw):
        fake = FakeDocker(**kw)
        self.addCleanup(fake.close)
        return fake

    def test_starts_the_hardened_sandbox_and_hashes_like_the_cli(self):
        fake = self.fake()
        run = run_tests(Path("."), runner=DockerApi(fake.path))
        self.assertTrue(run.passed)
        self.assertEqual(fake.paths(), [("GET", "/v1.41/info"), ("GET", f"/v1.41/images/{TEST_IMAGE.replace(':', '%3A').replace('@', '%40')}/json"),
                                        ("POST", "/v1.41/containers/create"), ("GET", "/v1.41/containers/c1/json"),
                                        ("POST", "/v1.41/containers/c1/start"),
                                        ("POST", "/v1.41/containers/c1/wait"), ("GET", "/v1.41/containers/c1/logs"),
                                        ("DELETE", "/v1.41/containers/c1")])
        body = fake.created
        host = body["HostConfig"]
        self.assertEqual(body["Image"], TEST_IMAGE)
        self.assertIn("@sha256:", body["Image"])
        self.assertTrue(body["NetworkDisabled"])
        self.assertEqual(host["NetworkMode"], "none")
        self.assertTrue(host["ReadonlyRootfs"])
        self.assertEqual(host["CapDrop"], ["ALL"])
        self.assertEqual(host["SecurityOpt"], ["no-new-privileges"])
        self.assertEqual((host["PidsLimit"], host["Memory"], host["MemorySwap"], host["NanoCpus"]),
                         (64, 256 * 1024**2, 256 * 1024**2, 10**9))
        self.assertEqual(host["Binds"], [f"{Path('.').resolve()}:/src:ro"])
        self.assertEqual(host["Tmpfs"], {"/tmp": "rw,noexec,nosuid,size=64m"})
        self.assertTrue(host["Init"])  # so the inner time limit's SIGTERM reaches the tests
        self.assertNotIn("Privileged", host)
        self.assertNotIn("User", body)
        self.assertEqual(body["Cmd"], ["timeout", "300", "python", "-m", "unittest", "-q"])
        # The receipt's hashes don't depend on the runner: the CLI with the same output hashes the same.
        cli = run_tests(Path("."), runner=lambda argv: (0, "Ran 1 test\ndone\n", "OK\n"))
        self.assertEqual(run.record(), cli.record())

    def test_pulls_the_pinned_image_when_missing(self):
        fake = self.fake(have_image=False)
        DockerApi(fake.path).run_spec(spec_for(Path("."), env={}))
        method, path, _ = fake.calls[2]
        self.assertEqual(method, "POST")
        name, digest = TEST_IMAGE.split("@")
        self.assertEqual(path, f"/v1.41/images/create?fromImage={name}&tag={digest.replace(':', '%3A')}")

    def test_a_failed_pull_fails_the_run(self):
        fake = self.fake(have_image=False, pull_error="manifest unknown")
        with self.assertRaisesRegex(RuntimeError, "manifest unknown"):
            DockerApi(fake.path).run_spec(spec_for(Path("."), env={}))
        self.assertNotIn(("POST", "/v1.41/containers/create"), fake.paths())

    def test_refuses_a_daemon_that_can_t_enforce_limits(self):
        # What rootless Docker reports on a cgroup v1 host: it accepts --memory and the rest, and enforces none.
        rootless = {"MemoryLimit": False, "CpuCfsQuota": False, "PidsLimit": False, "CgroupDriver": "none",
                    "SecurityOptions": ["name=seccomp,profile=builtin", "name=rootless"]}
        fake = self.fake(info=rootless)
        with self.assertRaisesRegex(RuntimeError, "can't enforce the limits .MemoryLimit, CpuCfsQuota, PidsLimit, "
                                                  "CgroupDriver"):
            run_tests(Path("."), runner=DockerApi(fake.path))
        self.assertEqual(fake.paths(), [("GET", "/v1.41/info")])  # nothing created
        capable = self.fake()
        api = DockerApi(capable.path)
        api.run_spec(spec_for(Path("."), env={}))
        api.run_spec(spec_for(Path("."), env={}))
        self.assertEqual(capable.paths().count(("GET", "/v1.41/info")), 1)  # asked once per node run

    def test_refuses_a_daemon_that_drops_a_limit(self):
        for kw, why in (({"warnings": ["Your kernel does not support memory limit capabilities"]}, "warned"),
                        ({"drop": ("Memory", "NanoCpus")}, "didn't apply Memory, NanoCpus"),
                        ({"drop": ("CapDrop",)}, "didn't apply CapDrop")):
            fake = self.fake(**kw)
            with self.assertRaisesRegex(RuntimeError, why):
                run_tests(Path("."), runner=DockerApi(fake.path))
            self.assertNotIn(("POST", "/v1.41/containers/c1/start"), fake.paths())  # never started
            self.assertEqual(fake.paths()[-1], ("DELETE", "/v1.41/containers/c1"))  # and removed

    def test_failing_tests_fail(self):
        run = run_tests(Path("."), runner=DockerApi(self.fake(exit_code=1).path))
        self.assertEqual(run.exit_code, 1)
        self.assertFalse(run.passed)

    def test_killed_and_removed_at_the_time_limit(self):
        fake = self.fake(wait_s=30)
        started = time.monotonic()
        run = run_tests(Path("."), runner=DockerApi(fake.path, margin_s=0), timeout_s=1)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(run.exit_code, TIMED_OUT)
        self.assertFalse(run.passed)
        self.assertIn(("POST", "/v1.41/containers/c1/kill"), fake.paths())
        self.assertEqual(fake.paths()[-1], ("DELETE", "/v1.41/containers/c1"))
        self.assertEqual(fake.created["Cmd"][:2], ["timeout", "1"])

    def test_runs_as_an_unprivileged_user_when_asked(self):
        spec = spec_for(Path("."), env={"ORACLE_SANDBOX_USER": "65534:65534"})
        self.assertEqual(DockerApi().create_body(spec)["User"], "65534:65534")
        argv = spec.argv()
        self.assertEqual(argv[argv.index("--user") + 1], "65534:65534")

    def test_demux_splits_stdout_and_stderr(self):
        self.assertEqual(DockerApi.demux(frames((1, "a"), (2, "b"), (1, "c"), (2, ""))), ("ac", "b"))
        self.assertEqual(DockerApi.demux(b""), ("", ""))

    def test_it_runs_specs_not_cli_argvs(self):
        with self.assertRaises(TypeError):
            DockerApi()(["docker", "run"])


class CliRunner(unittest.TestCase):
    def test_same_limits_as_the_api(self):
        argv = Spec(Path("."), TEST_IMAGE, ("python", "-V")).argv()
        for flag in ("--init", "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                     "--pids-limit", "64", "--memory", "256m", "--cpus", "1", "--tmpfs",
                     "/tmp:rw,noexec,nosuid,size=64m", f"{Path('.').resolve()}:/src:ro", TEST_IMAGE):
            self.assertIn(flag, argv)
        self.assertNotIn("--user", argv)
        self.assertNotIn("--privileged", argv)
        self.assertEqual(argv[-5:], [TEST_IMAGE, "timeout", "300", "python", "-V"])

    def test_the_outer_time_limit_is_a_timeout(self):
        old = sandbox.LIMITS["timeout_s"]
        sandbox.LIMITS["timeout_s"] = -29  # the subprocess gets 1 second
        try:
            self.assertEqual(sandbox.docker_runner([sys.executable, "-c", "import time; time.sleep(30)"])[0], TIMED_OUT)
        finally:
            sandbox.LIMITS["timeout_s"] = old

    def test_choosing_a_runner(self):
        api = default_runner({"ORACLE_SANDBOX": "api", "DOCKER_SOCKET": "/run/x.sock"})
        self.assertIsInstance(api, DockerApi)
        self.assertEqual(api.socket_path, "/run/x.sock")
        self.assertIs(default_runner({"ORACLE_SANDBOX": "cli"}), sandbox.docker_runner)
        expected = sandbox.docker_runner if shutil.which("docker") else None
        chosen = default_runner({})
        self.assertIs(chosen, expected) if expected else self.assertIsInstance(chosen, DockerApi)


def docker_ready() -> str:
    """Why the real-Docker test can't run here, or "" when it can."""
    flag = os.environ.get("POF_DOCKER_TESTS", "")
    if flag == "0":
        return "POF_DOCKER_TESTS=0"
    if not os.path.exists(SOCKET):
        return f"no Docker socket at {SOCKET}"
    try:
        status, _ = DockerApi(SOCKET)._call("GET", f"/images/{sandbox.quote(TEST_IMAGE, safe='')}/json", timeout=5,
                                            ok=(200, 404))
    except Exception as e:  # no daemon, or no permission on the socket
        return f"Docker isn't reachable: {e}"
    if status != 200 and flag != "1":
        return "the pinned test image isn't pulled (POF_DOCKER_TESTS=1 pulls it)"
    return ""


NODE_SCRIPT = textwrap.dedent("""
    import json, sys, time
    sys.path.insert(0, "/app")
    from pathlib import Path
    from oracle.sandbox import DockerApi, default_runner, spec_for
    src = Path(sys.argv[1])
    runner = default_runner()
    assert isinstance(runner, DockerApi), runner
    out = {}
    for name, command, timeout_s in [
        ("tests", ("python", "-m", "unittest", "-q"), 60),
        ("network", ("python", "-c", "import socket; socket.create_connection(('1.1.1.1', 53), 5)"), 60),
        ("dns", ("python", "-c", "import socket; socket.getaddrinfo('example.com', 443)"), 60),
        ("write_src", ("python", "-c", "open('/src/planted.py', 'w').write('x')"), 60),
        ("write_root", ("python", "-c", "open('/planted', 'w').write('x')"), 60),
        ("socket", ("python", "-c", "import os; assert not os.path.exists('/var/run/docker.sock')"), 60),
        ("caps", ("python", "-c", "print(open('/proc/self/status').read())"), 60),
        ("memory", ("python", "-c", "x = b'x' * (512 << 20); print(len(x))"), 60),
        ("pids", ("python", "-c", "import threading, time; [threading.Thread(target=time.sleep, args=(5,)).start() "
                  "for _ in range(100)]"), 60),
        ("time_limit", ("python", "-c", "import time; time.sleep(120)"), 3),
    ]:
        started = time.monotonic()
        code, stdout, stderr = runner.run_spec(spec_for(src, command=command, timeout_s=timeout_s))
        out[name] = {"code": code, "out": stdout[-2000:], "err": stderr[-600:], "s": time.monotonic() - started}
    print(json.dumps(out))
""")


DOCKER_SKIP = docker_ready()


@unittest.skipIf(DOCKER_SKIP, DOCKER_SKIP)
class DockerFromANodeContainer(unittest.TestCase):
    """The validator kit's layout for real: the node in a container with the host's socket starts the sandbox."""

    @classmethod
    def setUpClass(cls):
        cls.work = Path(tempfile.mkdtemp(prefix="pof-node-"))
        src = cls.work / "src" / ("ab" * 20)
        src.mkdir(parents=True)
        (src / "test_ok.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n"
                                        "    def test_ok(self):\n        self.assertEqual(1 + 1, 2)\n")
        os.chmod(cls.work, 0o755)
        os.chmod(src.parent, 0o755)
        os.chmod(src, 0o755)
        gid = os.stat(SOCKET).st_gid
        argv = ["docker", "run", "--rm", "--user", "10001:10001", "--group-add", str(gid),
                "-v", f"{SOCKET}:/var/run/docker.sock", "-v", f"{ROOT}/oracle:/app/oracle:ro",
                "-v", f"{cls.work}:{cls.work}:ro", "-e", "ORACLE_SANDBOX=api", "-e", "PYTHONDONTWRITEBYTECODE=1",
                TEST_IMAGE, "python3", "-c", NODE_SCRIPT, str(src)]
        if not shutil.which("docker"):
            raise unittest.SkipTest("the stand-in node container is started with the Docker CLI")
        started = time.monotonic()
        out = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        cls.elapsed = time.monotonic() - started
        if out.returncode != 0:
            raise AssertionError(f"the node container failed: {out.stdout[-2000:]} {out.stderr[-2000:]}")
        cls.r = json.loads(out.stdout.strip().splitlines()[-1])
        if os.environ.get("POF_DOCKER_TESTS_SHOW"):
            print({k: (v["code"], round(v["s"], 1), v["err"][-80:]) for k, v in cls.r.items()}, f"{cls.elapsed:.1f}s", file=sys.stderr)
        cls.src = src

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def test_the_fix_s_tests_run(self):
        self.assertEqual(self.r["tests"]["code"], 0, self.r["tests"])

    def test_no_network(self):
        for name in ("network", "dns"):
            self.assertNotEqual(self.r[name]["code"], 0, self.r[name])
        self.assertRegex(self.r["network"]["err"], "Network is unreachable|Errno 101")

    def test_can_t_write_the_source_or_the_image(self):
        for name in ("write_src", "write_root"):
            self.assertNotEqual(self.r[name]["code"], 0, self.r[name])
            self.assertIn("Read-only file system", self.r[name]["err"])
        self.assertFalse((self.src / "planted.py").exists())

    def test_no_docker_socket_and_no_capabilities(self):
        self.assertEqual(self.r["socket"]["code"], 0, self.r["socket"])
        caps = dict(line.split(":\t", 1) for line in self.r["caps"]["out"].splitlines() if ":\t" in line)
        self.assertEqual(int(caps["CapEff"].strip(), 16), 0)
        self.assertEqual(caps["NoNewPrivs"].strip(), "1")

    def test_memory_and_process_limits(self):
        self.assertNotEqual(self.r["memory"]["code"], 0, self.r["memory"])  # 512 MB under a 256 MB limit
        self.assertNotIn(str(512 << 20), self.r["memory"]["out"])
        self.assertNotEqual(self.r["pids"]["code"], 0, self.r["pids"])  # 100 threads under a 64-process limit
        self.assertIn("can't start new thread", self.r["pids"]["err"])

    def test_stopped_at_the_time_limit(self):
        self.assertIn(self.r["time_limit"]["code"], (TIMED_OUT, 143), self.r["time_limit"])
        self.assertLess(self.r["time_limit"]["s"], 30)  # a 3-second limit on a 120-second sleep


class ValidatorKit(unittest.TestCase):
    """The kit gives the node what the API runner needs, and nothing more (validator-kit/terraform)."""

    def test_node_container_layout(self):
        text = (ROOT / "validator-kit/terraform/node-user-data.sh.tftpl").read_text()
        for needed in ("-v /var/run/docker.sock:/var/run/docker.sock", '--group-add "$(stat -c %g /var/run/docker.sock)"',
                       "-v /var/lib/pof-node:/var/lib/pof-node", "-e ORACLE_SANDBOX=api",
                       "ORACLE_SRC_ROOT=/var/lib/pof-node/src", "install -d -o 10001 -g 10001"):
            self.assertIn(needed, text)
        for never in ("--privileged", "--user root", "--user 0", "--network host", "--pid host"):
            self.assertNotIn(never, text)

    def test_the_node_image_runs_as_its_own_user(self):
        text = (ROOT / "oracle/Dockerfile").read_text()
        self.assertIn("USER oracle", text)
        self.assertIn("-u 10001", text)


if __name__ == "__main__":
    unittest.main()
