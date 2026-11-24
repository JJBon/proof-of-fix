"""The fix's code, fetched by the node itself (proof-of-fix#115): exactly the pull request's head commit, nothing else.

A drawn node finds the pull request that claims a submission (the host's API, bot/forge.py) and checks the sealed
commitment opens with `commit_word(head_sha)`. Then, before any test runs, this module:

  - fetches that one commit (`git fetch --depth 1 <url> <sha>`, no tags, no submodules) into a fresh directory under
    ORACLE_SRC_ROOT, with a time limit and a size limit (the fetch is killed the moment either is passed);
  - checks the working copy's HEAD is that commit and that its bytes32 is the fix the seal commits to;
  - makes it read-only and moves it into place as <root>/<sha> in one rename, so a half-fetched tree is never used.

A directory already at <root>/<sha> is reused only if it's a git working copy at that commit (another node on the
same machine fetched it, or an earlier pass did).

The fix's diff for the judge (`Fetcher.diff`, #166) comes the same way: in a fresh directory of its own, never the
read-only checkout the tests run in, the same git settings and limits fetch the sealed commit and the pull request's
base, deepening (2, 16, then 128 commits) until the two share an ancestor; the diff runs from that merge base to the
sealed commit, as a forge shows a pull request, so a base that moved on doesn't show up as the fix undoing other work.
Git names objects by their content, so what the forge's API says can't change those bytes. The base's id is the one
thing it does name: the same id the verdict signs. Nothing is checked out, so a `.gitattributes` in the fix can't mark
its own code binary to hide it, and its output is read only up to the limit.

Credentials: a read-only token for the repository (Secrets Manager on the validator instance, passed in by the user
data; ORACLE_GIT_TOKEN or ORACLE_GIT_TOKEN_FILE locally). It goes to git as an HTTP header through GIT_CONFIG_*
environment variables, never on a command line or in a URL, and it is never logged. Git runs with no system or user
config, no credential helper, no prompts, no hooks, no symlinks, no redirects, and only the URL's protocol allowed.

Configuration (environment; see oracle/__main__.py):
    ORACLE_FETCH          "0": don't fetch; use only checkouts already under ORACLE_SRC_ROOT (default: fetch)
    ORACLE_GIT_URL        the clone URL, "{repo}" standing for owner/name (default: from the host: GitHub's
                          https://github.com/{repo}.git, a Forgejo's <base>/{repo}.git); https, http on loopback
                          only, or file:// (local runs)
    ORACLE_GIT_TOKEN      the read-only token (default: the host's: GITHUB_TOKEN / GITHUB_APP_TOKEN, FORGEJO_TOKEN)
    ORACLE_GIT_TOKEN_FILE a file holding it instead
    ORACLE_GIT_USER       the user the token is sent with (default: x-access-token for GitHub, FORGEJO_USER)
    ORACLE_FETCH_MAX_MB   the size limit of one fetched commit, git objects and working tree (default 200)
    ORACLE_FETCH_TIMEOUT  seconds one fetch may take (default 120)"""

from __future__ import annotations

import base64
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .v2 import commit_word

SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
DEFAULT_MAX_MB, DEFAULT_TIMEOUT_S, RETRY_S = 200, 120.0, 30.0
DIFF_DEPTHS = (2, 16, 128)  # commits fetched behind each of the fix and its base, looking for their merge base
DEFAULT_DIFF_BYTES, COMMIT_MESSAGE_BYTES, TEXT_FILE_MAX_BYTES = 200_000, 8_000, 4 << 20


class FetchRefused(Exception):
    """The commit wasn't fetched or didn't check out (the message says why; it never holds the token)."""


class TooLarge(FetchRefused):
    """Past the size limit: the same for every node, so not worth trying again."""


@dataclass(frozen=True)
class Diff:
    """A fix's diff, computed here, or the reason there can't be one for this fix (`refusal`, the same for any judge)."""
    merge_base: str = ""
    text: str = ""
    message: str = ""  # the sealed commit's own message
    refusal: str = ""
    message_cut: bool = False  # the message went past COMMIT_MESSAGE_BYTES, and `message` stops there


@dataclass(frozen=True)
class Blob:
    """One file at a commit (`Fetcher.file_at`): its bytes, None when the commit has no such file, or the reason it
    can't be read (`refusal`, the same for any node)."""
    data: Optional[bytes] = None
    refusal: str = ""


def check_url(url: str) -> str:
    """The URL's protocol, if git may fetch from it: https anywhere, http only on loopback, file (local runs)."""
    u = urlsplit(url)
    if u.username or u.password:
        raise ValueError("the clone URL carries credentials; put the token in ORACLE_GIT_TOKEN instead")
    if u.scheme == "https" and u.hostname:
        return "https"
    if u.scheme == "http" and u.hostname in LOOPBACK:
        return "http"
    if u.scheme == "file" and u.path:
        return "file"
    raise ValueError(f"the clone URL must be https (http only on loopback, or file://): {url}")


class Fetcher:
    """Fetches one commit into <root>/<sha>, verified, read-only, within the limits."""

    def __init__(self, url: str, token: str = "", user: str = "x-access-token", max_bytes: int = DEFAULT_MAX_MB << 20,
                 timeout_s: float = DEFAULT_TIMEOUT_S, retry_s: float = RETRY_S, log: Callable = print,
                 git: str = "git") -> None:
        self.url, self.protocol = url, check_url(url)
        self._token, self._user = token, user
        self.max_bytes, self.timeout_s, self.retry_s, self.log, self.git = max_bytes, timeout_s, retry_s, log, git
        self.upload_pack = ""  # a command that reaches the source's git-upload-pack (a Radicle node in a container)
        self._failed: dict = {}  # sha -> when it last failed (monotonic): retried after retry_s, not every pass
        self._files: dict = {}  # "sha:path" -> Blob: a commit's files never change

    def __repr__(self) -> str:  # never the token
        return f"Fetcher({self.url!r}, token={'set' if self._token else 'none'})"

    def ensure(self, root: Path, sha: str, fix: bytes) -> bool:
        """True when <root>/<sha> holds exactly that commit, fetched now or before; False (logged) otherwise."""
        sha = sha.strip().lower()
        if not SHA.match(sha):
            self.log(f"fetch: {sha[:16]!r} isn't a commit id; refused")
            return False
        if commit_word(sha) != fix:
            self.log(f"fetch: commit {sha[:12]} isn't the fix the seal commits to; refused")
            return False
        dest = Path(root) / sha
        if dest.exists():
            return self._reuse(dest, sha)
        last = self._failed.get(sha)
        if last is not None and time.monotonic() - last < self.retry_s:
            return False
        try:
            self._fetch(Path(root), sha, dest)
        except FetchRefused as e:
            self._failed[sha] = time.monotonic()
            self.log(f"fetch: commit {sha[:12]} from {self.url}: {e}")
            return False
        self._failed.pop(sha, None)
        self.log(f"fetch: commit {sha[:12]} checked out read-only under {root}")
        return True

    def diff(self, root: Path, sha: str, fix: bytes, base: str, max_bytes: int = DEFAULT_DIFF_BYTES) -> Optional[Diff]:
        """The diff from the merge base of `base` and the sealed commit to that commit. None (logged) when it couldn't
        be fetched just now: try again; a Diff with a `refusal` when no attempt would give one."""
        sha, base = sha.strip().lower(), (base or "").strip().lower()
        if not SHA.match(sha) or commit_word(sha) != fix:
            return Diff(refusal="the commit isn't the fix the seal commits to")
        if not SHA.match(base):
            return Diff(refusal="the pull request has no base commit")
        key = f"{base}..{sha}"
        last = self._failed.get(key)
        if last is not None and time.monotonic() - last < self.retry_s:
            return None
        Path(root).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".diff-{sha[:12]}-", dir=root))
        try:
            found = self._diff(tmp, sha, base, max_bytes)
        except TooLarge as e:
            found = Diff(refusal=f"the fix and its base's history are {e}")
        except FetchRefused as e:
            self._failed[key] = time.monotonic()
            self.log(f"fetch: the diff of {sha[:12]} against {base[:12]} from {self.url}: {e}")
            return None
        finally:
            remove(tmp)
        self._failed.pop(key, None)
        return found

    def range_diff(self, root: Path, old_base: str, old_fix: str, new_base: str, new_fix: str,
                   max_bytes: int = DEFAULT_DIFF_BYTES) -> Optional[Diff]:
        """`git range-diff` of an approved fix (`old_base`..`old_fix`) against its rebase (`new_base`..`new_fix`)
        (#310, RB3: a rebase check's case), each range from its merge base, computed by this node from the four commits
        it fetched itself. None (logged) when they couldn't be fetched just now: try again; a Diff with a `refusal`
        when no attempt would give one. The commits are checked as `diff` checks them; the text is in `text`."""
        shas = [(x or "").strip().lower() for x in (old_base, old_fix, new_base, new_fix)]
        if not all(SHA.match(x) for x in shas):
            return Diff(refusal="a rebase's range-diff needs four commit ids")
        key = "range:" + "..".join(shas)
        last = self._failed.get(key)
        if last is not None and time.monotonic() - last < self.retry_s:
            return None
        Path(root).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".range-{shas[3][:12]}-", dir=root))
        try:
            found = self._range_diff(tmp, *shas, max_bytes)
        except TooLarge as e:
            found = Diff(refusal=f"the fixes and their bases' history are {e}")
        except FetchRefused as e:
            self._failed[key] = time.monotonic()
            self.log(f"fetch: the range-diff of {shas[1][:12]} and {shas[3][:12]} from {self.url}: {e}")
            return None
        finally:
            remove(tmp)
        self._failed.pop(key, None)
        return found

    def file_at(self, root: Path, sha: str, path: str, max_bytes: int) -> Optional[Blob]:
        """The file at `path` in commit `sha`, fetched by this node (#166: the repository's test command, read at the
        pull request's base so the fix can't change it). None (logged) when it couldn't be fetched just now: try
        again. Only a regular file counts; a symlink or a folder there is a refusal. Kept per commit: a commit's
        content never changes."""
        sha = (sha or "").strip().lower()
        if not SHA.match(sha):
            return Blob(refusal="the pull request has no base commit")
        key = f"{sha}:{path}"
        if key in self._files:
            return self._files[key]
        last = self._failed.get(key)
        if last is not None and time.monotonic() - last < self.retry_s:
            return None
        Path(root).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".file-{sha[:12]}-", dir=root))
        try:
            found = self._file_at(tmp, sha, path, max_bytes)
        except TooLarge as e:
            found = Blob(refusal=f"its base commit is {e}")
        except FetchRefused as e:
            self._failed[key] = time.monotonic()
            self.log(f"fetch: {path} at {sha[:12]} from {self.url}: {e}")
            return None
        finally:
            remove(tmp)
        self._failed.pop(key, None)
        self._files[key] = found
        return found

    # -- internals

    def _via(self) -> list:
        """git's --upload-pack when the source is reached through a command (a local file:// source only)."""
        return ["--upload-pack", self.upload_pack] if self.upload_pack and self.protocol == "file" else []

    def _file_at(self, tmp: Path, sha: str, path: str, max_bytes: int) -> Blob:
        self._run(tmp, ["init", "-q"], tmp)
        self._run(tmp, ["fetch", "-q", "--depth", "1", "--no-tags", "--no-recurse-submodules", *self._via(), "--",
                        self.url, sha], tmp)
        fetched = self._run(tmp, ["rev-parse", "--verify", "FETCH_HEAD^{commit}"], tmp, capture=True)
        if fetched != sha:
            raise FetchRefused(f"the host served commit {fetched[:12]}, not {sha[:12]}")
        listed, _ = self._bounded(tmp, ["ls-tree", "-z", sha, "--", path], 4_096)
        entry = listed.split(b"\0", 1)[0]
        if not entry:
            return Blob()
        meta, _, name = entry.partition(b"\t")
        mode, kind, obj = (meta.split(b" ") + [b"", b"", b""])[:3]
        if name.decode(errors="replace") != path or kind != b"blob" or mode not in (b"100644", b"100755"):
            return Blob(refusal=f"{path} isn't a regular file")
        data, cut = self._bounded(tmp, ["cat-file", "blob", obj.decode()], max_bytes)
        if cut:
            return Blob(refusal=f"{path} is larger than {max_bytes:,} bytes")
        return Blob(data)

    def _diff(self, tmp: Path, sha: str, base: str, max_bytes: int) -> Diff:
        self._run(tmp, ["init", "-q"], tmp)
        merge_base = ""
        for depth in DIFF_DEPTHS:
            self._run(tmp, ["fetch", "-q", "--depth", str(depth), "--no-tags", "--no-recurse-submodules", *self._via(),
                            "--", self.url, *sorted({sha, base})], tmp)
            for commit in (sha, base):
                if self._run(tmp, ["rev-parse", "--verify", f"{commit}^{{commit}}"], tmp, capture=True) != commit:
                    raise FetchRefused(f"the host didn't serve commit {commit[:12]}")
            try:  # no common ancestor in what's here: git exits 1
                merge_base = self._run(tmp, ["merge-base", base, sha], tmp, capture=True)
            except FetchRefused:
                merge_base = ""
            if merge_base:
                break
        if not merge_base:
            return Diff(refusal=f"no common ancestor with its base within {DIFF_DEPTHS[-1]} commits")
        patch, more = self._bounded(tmp, ["-c", f"core.bigFileThreshold={TEXT_FILE_MAX_BYTES}", "diff", "--no-color",
                                          "--no-ext-diff", "--no-textconv", "-M", "--unified=3", merge_base, sha, "--"],
                                    max_bytes)
        if more:
            return Diff(merge_base, refusal=f"its diff is larger than the limit ({max_bytes:,} bytes)")
        message, cut = self._bounded(tmp, ["show", "-s", "--format=%B", sha], COMMIT_MESSAGE_BYTES)
        return Diff(merge_base, patch.decode(errors="replace"), message.decode(errors="replace").strip(), message_cut=cut)

    def _range_diff(self, tmp: Path, old_base: str, old_fix: str, new_base: str, new_fix: str, max_bytes: int) -> Diff:
        self._run(tmp, ["init", "-q"], tmp)
        old_mb = new_mb = ""
        for depth in DIFF_DEPTHS:
            self._run(tmp, ["fetch", "-q", "--depth", str(depth), "--no-tags", "--no-recurse-submodules", *self._via(),
                            "--", self.url, *sorted({old_base, old_fix, new_base, new_fix})], tmp)
            for commit in (old_base, old_fix, new_base, new_fix):
                if self._run(tmp, ["rev-parse", "--verify", f"{commit}^{{commit}}"], tmp, capture=True) != commit:
                    raise FetchRefused(f"the host didn't serve commit {commit[:12]}")
            try:
                old_mb = self._run(tmp, ["merge-base", old_base, old_fix], tmp, capture=True)
                new_mb = self._run(tmp, ["merge-base", new_base, new_fix], tmp, capture=True)
            except FetchRefused:
                old_mb = new_mb = ""
            if old_mb and new_mb:
                break
        if not (old_mb and new_mb):
            return Diff(refusal=f"no common ancestor with their bases within {DIFF_DEPTHS[-1]} commits")
        text, more = self._bounded(tmp, ["range-diff", "--no-color", f"{old_mb}..{old_fix}", f"{new_mb}..{new_fix}"],
                                   max_bytes)
        if more:
            return Diff(new_mb, refusal=f"the range-diff is larger than the limit ({max_bytes:,} bytes)")
        return Diff(new_mb, text.decode(errors="replace"))

    def _bounded(self, cwd: Path, args: list, limit: int) -> tuple:
        """git's standard output, at most `limit` bytes, and whether it had more: killed there, or at the time limit,
        so a small commit that expands to gigabytes of diff costs nothing to refuse."""
        deadline = time.monotonic() + self.timeout_s
        with tempfile.TemporaryFile() as err:
            try:
                p = subprocess.Popen([self.git, *args], cwd=str(cwd), env=self._env(Path(cwd)), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=err, start_new_session=True)
            except OSError as e:
                raise FetchRefused(f"can't run git: {e.strerror}") from None
            out = bytearray()
            try:
                fd = p.stdout.fileno()
                while len(out) <= limit:
                    if time.monotonic() > deadline:
                        kill(p)
                        raise FetchRefused(f"took longer than the limit ({self.timeout_s:g} s)")
                    if select.select([fd], [], [], 0.25)[0]:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        out += chunk
                if len(out) > limit:
                    kill(p)
                    return bytes(out[:limit]), True
                try:
                    p.wait(timeout=max(deadline - time.monotonic(), 1.0))
                except subprocess.TimeoutExpired:
                    kill(p)
                    raise FetchRefused(f"took longer than the limit ({self.timeout_s:g} s)") from None
            finally:
                p.stdout.close()
            err.seek(0)
            if p.returncode:
                raise FetchRefused(f"git {args[0]} failed: {self._redact(last_line(err.read().decode(errors='replace')))}")
        return bytes(out), False

    def _reuse(self, dest: Path, sha: str) -> bool:
        try:
            head = self._run(dest, ["rev-parse", "--verify", "HEAD^{commit}"], dest, capture=True)
        except FetchRefused:
            head = ""
        if head == sha:
            return True
        self.log(f"fetch: {dest} exists but isn't a working copy at {sha[:12]}; refused (not overwritten)")
        return False

    def _fetch(self, root: Path, sha: str, dest: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=f".fetch-{sha[:12]}-", dir=root))
        try:
            self._run(tmp, ["init", "-q"], tmp)
            self._run(tmp, ["fetch", "-q", "--depth", "1", "--no-tags", "--no-recurse-submodules", *self._via(), "--",
                            self.url, sha], tmp)
            fetched = self._run(tmp, ["rev-parse", "--verify", "FETCH_HEAD^{commit}"], tmp, capture=True)
            if fetched != sha:
                raise FetchRefused(f"the host served commit {fetched[:12]}, not {sha[:12]}")
            self._run(tmp, ["checkout", "-q", "--detach", sha], tmp)
            head = self._run(tmp, ["rev-parse", "--verify", "HEAD^{commit}"], tmp, capture=True)
            if head != sha:
                raise FetchRefused(f"the working copy is at {head[:12]}, not {sha[:12]}")
            if tree_bytes(tmp) > self.max_bytes:
                raise TooLarge(f"larger than the limit ({self.max_bytes >> 20} MB)")
            read_only(tmp)
            try:
                os.rename(tmp, dest)
            except OSError:
                if not dest.exists():  # another node fetching into the same root moved its copy in first
                    raise FetchRefused("couldn't move the working copy into place") from None
        finally:
            if tmp.exists():
                remove(tmp)
        if not self._reuse(dest, sha):
            raise FetchRefused("the working copy in place isn't at that commit")

    def _env(self, home: Path) -> dict:
        settings = [("credential.helper", ""), ("core.hooksPath", os.devnull), ("core.symlinks", "false"),
                    ("core.attributesFile", os.devnull),
                    ("core.fsmonitor", "false"), ("http.followRedirects", "false"), ("transfer.fsckObjects", "true"),
                    ("protocol.allow", "never"), (f"protocol.{self.protocol}.allow", "always"),
                    ("advice.detachedHead", "false"), ("init.defaultBranch", "main"), ("safe.directory", "*")]
        if self._token:
            basic = base64.b64encode(f"{self._user}:{self._token}".encode()).decode()
            settings.append(("http.extraHeader", f"Authorization: Basic {basic}"))
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "XDG_CONFIG_HOME": str(home),
               "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0",
               "GIT_ALLOW_PROTOCOL": self.protocol, "GIT_ATTR_NOSYSTEM": "1", "LC_ALL": "C",
               "GIT_CONFIG_COUNT": str(len(settings))}
        for i, (k, v) in enumerate(settings):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
        return env

    def _run(self, cwd: Path, args: list, watched: Path, capture: bool = False) -> str:
        """git, killed (with its children) at the time limit or when `watched` passes the size limit."""
        deadline = time.monotonic() + self.timeout_s
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            try:
                p = subprocess.Popen([self.git, *args], cwd=str(cwd), env=self._env(Path(cwd)),
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            except OSError as e:
                raise FetchRefused(f"can't run git: {e.strerror}") from None
            why, polls = "", 0
            while p.poll() is None:
                polls += 1
                if time.monotonic() > deadline:
                    why = f"took longer than the limit ({self.timeout_s:g} s)"
                elif polls % 5 == 0 and tree_bytes(watched) > self.max_bytes:  # every quarter second
                    kill(p)
                    raise TooLarge(f"larger than the limit ({self.max_bytes >> 20} MB)")
                if why:
                    kill(p)
                    raise FetchRefused(why)
                time.sleep(0.05)
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read().decode(errors="replace"), err.read().decode(errors="replace")
        if p.returncode:
            raise FetchRefused(f"git {args[0]} failed: {self._redact(last_line(stderr))}")
        return stdout.strip() if capture else ""

    def _redact(self, text: str) -> str:
        if self._token:
            text = text.replace(self._token, "***")
        return text


def ensure(root: Path, pull: dict, fix: bytes, fetcher: Optional[Fetcher] = None) -> bool:
    """The node's one call (NodeV2._find_claim): is the claimed commit's code under <root>/<sha>, ready to test?
    With a fetcher it's fetched and verified; without one (tests, a node told ORACLE_FETCH=0) only a checkout already
    there counts."""
    if fetcher is None:
        return (Path(root) / pull["head_sha"]).is_dir()
    return fetcher.ensure(Path(root), pull["head_sha"], fix)


def from_env(env, repo_name: str, host, log: Callable = print) -> Optional[Fetcher]:
    """The node's fetcher from its configuration (the module's docstring), or None with ORACLE_FETCH=0."""
    if env.get("ORACLE_FETCH", "1") == "0":
        return None
    url, token, user = clone_source(host, repo_name)
    if env.get("ORACLE_GIT_URL"):
        url = env["ORACLE_GIT_URL"].replace("{repo}", repo_name)
    if env.get("ORACLE_GIT_TOKEN"):
        token = env["ORACLE_GIT_TOKEN"]
    elif env.get("ORACLE_GIT_TOKEN_FILE"):
        token = Path(env["ORACLE_GIT_TOKEN_FILE"]).read_text(encoding="utf-8").strip()
    user = env.get("ORACLE_GIT_USER") or user
    max_mb = float(env.get("ORACLE_FETCH_MAX_MB", DEFAULT_MAX_MB))
    return Fetcher(url, token, user, max_bytes=int(max_mb * (1 << 20)),
                   timeout_s=float(env.get("ORACLE_FETCH_TIMEOUT", DEFAULT_TIMEOUT_S)), log=log)


def clone_source(host, repo_name: str) -> tuple:
    """(clone URL, token, user) the host implies: GitHub's web host for its API, a Forgejo's own base. A host that
    knows its own source (another forge, a Radicle seed: ADR 0003) says so with a `clone_source(repo_name)` method
    returning the same triple; the fetch itself is plain git, whatever the host."""
    own = getattr(host, "clone_source", None)
    if callable(own):
        return tuple(own(repo_name))
    client = getattr(host, "client", None)
    if client is not None and hasattr(client, "remote"):  # bot.forge.ForgejoRepo
        return f"{client.base}/{repo_name}.git", client.token or client.password, client.user
    api = getattr(host, "api", "https://api.github.com")
    u = urlsplit(api)
    if u.hostname == "api.github.com":
        web = "https://github.com"
    else:  # GitHub Enterprise Server: https://<host>/api/v3
        path = u.path[:-len("/api/v3")] if u.path.endswith("/api/v3") else u.path
        web = f"{u.scheme}://{u.netloc}{path.rstrip('/')}"
    return f"{web}/{repo_name}.git", getattr(host, "token", ""), "x-access-token"


def tree_bytes(path: Path) -> int:
    """Bytes under `path`, not following links (git objects and the working tree alike)."""
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for name in filenames:
            try:
                total += os.lstat(os.path.join(dirpath, name)).st_size
            except OSError:
                pass  # git renames its temporary files as it goes
    return total


def read_only(path: Path) -> None:
    """No write bit anywhere in the working copy (the sandbox also mounts it read-only)."""
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        for name in filenames:
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                os.chmod(p, stat.S_IMODE(os.lstat(p).st_mode) & ~0o222)
        os.chmod(dirpath, 0o555)


def remove(path: Path) -> None:
    """Delete a working copy this module made read-only."""
    if not Path(path).exists():
        return
    for dirpath, dirnames, filenames in os.walk(path):
        os.chmod(dirpath, 0o755)
        for name in dirnames:
            p = os.path.join(dirpath, name)
            if not os.path.islink(p):
                os.chmod(p, 0o755)
    shutil.rmtree(path)


def kill(p: subprocess.Popen) -> None:
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except OSError:
        p.kill()
    p.wait()


def last_line(text: str) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return (lines[-1] if lines else "no message")[:200]
