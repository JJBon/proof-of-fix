"""Protected tests (#251 L20): a fix can't change the tests that judge it.

`.pof/check.json`, read at the pull request's base (oracle/checkconfig.py), may name `protected` paths, files or
folders. Before the sandbox runs, the node builds a fresh run tree for the check:

- the fix's tree, copied (its `.git` left out), with each protected path replaced by the base's copy, from the node's
  own fetch of the base: a file the fix added under a protected path is gone, and one it changed or deleted is back
  as it is at the base. A protected path the base doesn't have is removed;
- the shared checkout under the node's source root is never changed: the run tree is a new directory beside it (the
  sandbox's bind mount is resolved by the host's Docker, so it sits under the same root), made read-only, and removed
  once the runs are over;
- a protected path whose parent, in the fix's tree or the base's, is a symlink or not a folder fails the check
  (`Unsafe`), so the overlay never writes, or reads, outside the two trees;
- only regular files, folders and symlinks are copied (a symlink as a link, never followed), as git keeps them.

The receipt records the list and the run tree's git tree hash (`tree_hash`: what `git write-tree` gives for the files
as they are on disk), and the judge's test-run line says how many of the fix's changed files were under protected
paths and so not run. Changed files are found by comparing the fix's tree with the base's, file by file, so the rule
doesn't depend on reading a diff right (renames, modes, links).

A **tests-only fix** changes files under protected paths only. Its test changes can't be overlaid away without
leaving nothing to judge, so the node runs both sets on its code (the base's): the base's protected tests, as for
every fix, and its own. Both must pass (oracle/node_v2.py `_run_check`)."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

from .fetch import read_only, remove

# An entry: ("f", executable, git blob id) for a file, ("l", False, git blob id of the target) for a symlink.
Entry = Tuple[str, bool, str]


class Unsafe(Exception):
    """A protected path the overlay can't apply without leaving the trees: the check fails."""


@dataclass(frozen=True)
class Plan:
    """What the overlay does for one fix against its base."""
    changed: Tuple[str, ...]  # the fix's changed files (added, changed or deleted against the base), sorted
    protected_changed: Tuple[str, ...]  # those under a protected path

    @property
    def tests_only(self) -> bool:
        """The fix changes protected paths and nothing else."""
        return bool(self.changed) and len(self.protected_changed) == len(self.changed)

    @property
    def not_run(self) -> int:
        """How many of the fix's changed files the base's copies replace (none for a tests-only fix: its own run)."""
        return 0 if self.tests_only else len(self.protected_changed)


def under(rel: str, protected: Iterable[str]) -> bool:
    return any(rel == p or rel.startswith(p + "/") for p in protected)


def _blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def entries(root: Path) -> Dict[str, Entry]:
    """Every file and symlink under `root` (its top-level `.git` left out), by its path relative to it, with what
    git would record for it. Links are never followed; anything else (a socket, a device) is left out, as git does."""
    out: Dict[str, Entry] = {}

    def walk(d: str, rel: str) -> None:
        with os.scandir(d) as it:
            for e in it:
                r = f"{rel}{e.name}"
                if not rel and e.name == ".git":
                    continue
                if e.is_symlink():
                    out[r] = ("l", False, _blob(os.fsencode(os.readlink(e.path))))
                elif e.is_dir(follow_symlinks=False):
                    walk(e.path, r + "/")
                elif e.is_file(follow_symlinks=False):
                    with open(e.path, "rb") as f:
                        data = f.read()
                    out[r] = ("f", bool(e.stat(follow_symlinks=False).st_mode & stat.S_IXUSR), _blob(data))

    walk(str(root), "")
    return out


def tree_hash(root: Path, found: Dict[str, Entry] | None = None) -> str:
    """The git tree hash (SHA-1 object format) of the files under `root` as they are on disk: what `git add -A` then
    `git write-tree` gives there. Empty folders don't count, as in git."""
    found = entries(root) if found is None else found
    tree: dict = {}
    for rel, entry in found.items():
        *dirs, name = rel.split("/")
        node = tree
        for d in dirs:
            node = node.setdefault(d + "/", {})
        node[name] = entry

    def write(node: dict) -> str:
        items = []
        for key, value in node.items():
            if isinstance(value, dict):
                items.append((key, b"40000", key[:-1], write(value)))
            else:
                kind, exe, oid = value
                mode = b"120000" if kind == "l" else b"100755" if exe else b"100644"
                items.append((key, mode, key, oid))
        items.sort(key=lambda x: x[0].encode())  # a folder sorts as its name and "/", as git sorts it
        body = b"".join(mode + b" " + name.encode() + b"\0" + bytes.fromhex(oid) for _, mode, name, oid in items)
        return hashlib.sha1(b"tree %d\0" % len(body) + body).hexdigest()

    return write(tree)


def plan(fix: Dict[str, Entry], base: Dict[str, Entry], protected: Tuple[str, ...]) -> Plan:
    changed = tuple(sorted(r for r in set(fix) | set(base) if fix.get(r) != base.get(r)))
    return Plan(changed, tuple(r for r in changed if under(r, protected)))


def check_parents(root: Path, protected: Tuple[str, ...], which: str) -> None:
    """Raises Unsafe when a protected path's parent in this tree is a symlink or not a folder."""
    for i, p in enumerate(protected, 1):
        parts = p.split("/")
        for k in range(1, len(parts)):
            at = Path(root, *parts[:k])
            if at.is_symlink():
                raise Unsafe(f"protected path {i} is under a symlink in the {which}'s tree")
            if os.path.lexists(at) and not at.is_dir():
                raise Unsafe(f"protected path {i} is under a file, not a folder, in the {which}'s tree")


def _copy(src: Path, dst: Path) -> None:
    """A file, a link (as a link) or a folder (its files, folders and links), never following a link."""
    st = os.lstat(src)
    if stat.S_ISLNK(st.st_mode):
        os.symlink(os.readlink(src), dst)
    elif stat.S_ISDIR(st.st_mode):
        os.mkdir(dst, 0o755)
        with os.scandir(src) as it:
            for e in it:
                _copy(Path(e.path), dst / e.name)
    elif stat.S_ISREG(st.st_mode):
        with open(src, "rb") as f, open(dst, "xb") as g:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                g.write(chunk)
        os.chmod(dst, 0o755 if st.st_mode & stat.S_IXUSR else 0o644)


def _drop(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        remove(path)
    elif os.path.lexists(path):
        path.unlink()


def build(fix: Path, base: Path, protected: Tuple[str, ...], root: Path) -> Path:
    """A fresh run tree under `root`: the fix's tree with each protected path as it is in `base`. Read-only; remove it
    with oracle.fetch.remove. Raises Unsafe (nothing left behind) when a protected path's parent is a symlink."""
    check_parents(fix, protected, "fix")
    check_parents(base, protected, "base")
    Path(root).mkdir(parents=True, exist_ok=True)
    run = Path(tempfile.mkdtemp(prefix=f".run-{Path(fix).name[:12]}-", dir=root))
    try:
        os.chmod(run, 0o755)
        with os.scandir(fix) as it:
            for e in it:
                if e.name != ".git":
                    _copy(Path(e.path), run / e.name)
        for p in protected:
            target = run.joinpath(*p.split("/"))
            _drop(target)
            source = Path(base).joinpath(*p.split("/"))
            if os.path.lexists(source):
                target.parent.mkdir(parents=True, exist_ok=True)
                _copy(source, target)
        read_only(run)
    except BaseException:
        remove(run)
        raise
    return run
