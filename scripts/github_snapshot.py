#!/usr/bin/env python3
"""A scrubbed snapshot of this project in its private GitHub repositories (proof-of-fix#175, #158).

It takes a git ref's tracked files, replaces private terms, and scans the result. It commits to the target's `snapshot`
branch only when the scan is clean, and only with --push: the default is a dry run. It's a snapshot, not a mirror: no
history goes across, only one new commit each time.

The private terms stay out of this repository: they're in a file on the owner's machine (--terms, default
~/.config/proof-of-fix/snapshot-terms, `old => new` per line in order, `deny: literal` to fail the scan if it's left), and
the script refuses to run without them. It also refuses a target that isn't private, unless --allow-public names the step
the owner took (proof-of-fix went public on 2026-11-18, #251).

    scripts/github_snapshot.py proof-of-fix                                  # a dry run: what would change
    scripts/github_snapshot.py proof-of-fix --check --push                   # with the tests, then push
    scripts/github_snapshot.py pof-devnet-infra --source ~/dev/platform --push

Standard library, git and tar; gh for a GitHub target. The scan names files and kinds of finding, never the values."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "snapshot"
DEFAULT_TERMS = "~/.config/proof-of-fix/snapshot-terms"
GH_CREDENTIALS = ["-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]
PRESETS = {
    "proof-of-fix": {
        "paths": [],
        "note": "> A scrubbed snapshot. Development happens on a private Forgejo, which keeps the full history; issue "
                "numbers (`#123`) refer to its tracker, and example.com and example-org stand in for internal addresses.",
        "check": ["scripts/check.sh"],
    },
    "pof-devnet-infra": {
        "paths": ["modules/pof_devnet", "modules/compose_host", "modules/schedule", "modules/scripts",
                  "environments/prod/us-east-1/pof-devnet"],
        "drop": ["environments/prod/us-east-1/pof-devnet/backend.tf"],
        "keep": ["README.md"],  # written for this repository, it lives only there
    },
}
# Fake values used by tests aren't shaped like these. A PEM header alone is library code; with a body it's a key.
SECRET_PATTERNS = {
    "aws access key": r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    "github token": r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=]{20,}",
    "account in an ARN": r"arn:aws:[a-z0-9-]+:[a-z0-9-]*:(?!111111111111|123456789012|000000000000)\d{12}:",
    "account in an ECR URL": r"(?<!\d)(?!111111111111|123456789012|000000000000)\d{12}\.dkr\.ecr",
}


def read_terms(path: Path) -> tuple:
    """(replacements in order, literals that must not remain). Refuses a missing or empty file: no terms, no snapshot."""
    if not path.is_file():
        raise SystemExit(f"github-snapshot: no terms file at {path}: without it nothing would be scrubbed")
    replace, deny = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("deny:"):
            deny.append(line[len("deny:"):].strip())
        elif " => " in line or line.rstrip().endswith(" =>"):
            old, _, new = line.partition(" =>")
            replace.append((old.strip(), new.strip()))
        elif line.strip() and not line.startswith("# "):
            raise SystemExit(f"github-snapshot: a line in {path} is neither `old => new` nor `deny: literal`")
    if not replace:
        raise SystemExit(f"github-snapshot: {path} has no replacements: without them nothing would be scrubbed")
    return replace, deny


def text_files(root: Path):
    """Every regular file under root that reads as text, with its text; .git is never touched."""
    for p in sorted(root.rglob("*")):
        if ".git" in p.relative_to(root).parts or p.is_symlink() or not p.is_file():
            continue
        data = p.read_bytes()
        if b"\0" in data[:4096]:
            continue
        try:
            yield p, data.decode("utf-8")
        except UnicodeDecodeError:
            continue


def scrub(root: Path, replace: list) -> int:
    changed = 0
    for p, text in text_files(root):
        out = text
        for old, new in replace:
            out = out.replace(old, new)
        if out != text:
            p.write_text(out, encoding="utf-8")
            changed += 1
    return changed


def scan(root: Path, replace: list, deny: list) -> list:
    """Findings as (file, kind). Never the value: this output may end up anywhere."""
    found = []
    # A replacement's new text can legitimately contain nothing private, but its old text must be gone.
    literals = [("a private term", old) for old, _ in replace] + [("a denied term", d) for d in deny]
    for p, text in text_files(root):
        rel = str(p.relative_to(root))
        for kind, literal in literals:
            if literal in text:
                found.append((rel, kind))
                break
        for kind, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                found.append((rel, kind))
    return found


def run(args: list, cwd=None, stdin=None, capture=True) -> str:
    r = subprocess.run(args, cwd=cwd, input=stdin, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE)
    if r.returncode:
        # git's errors can name a URL but carry no token: the credential helper hands it over outside the command line.
        raise SystemExit(f"github-snapshot: {' '.join(args[:3])} failed: {r.stderr.decode(errors='replace')[-300:]}")
    return r.stdout.decode().strip() if capture else ""


def lay_out(tree: Path, source: Path, ref: str, preset: dict) -> None:
    """The target's tree becomes the ref's files, plus what the preset keeps, less what it drops."""
    keep = set(preset.get("keep", []))
    for child in tree.iterdir():
        if child.name == ".git" or child.name in keep:
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    archive = subprocess.run(["git", "-C", str(source), "archive", ref, "--", *(preset.get("paths") or ["."])],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if archive.returncode:
        raise SystemExit(f"github-snapshot: can't read {ref} in {source}: {archive.stderr.decode(errors='replace')[-200:]}")
    run(["tar", "-x", "-C", str(tree)], stdin=archive.stdout)
    for rel in preset.get("drop", []):
        (tree / rel).unlink(missing_ok=True)
    note = preset.get("note")
    if note:
        readme = tree / "README.md"
        head, _, rest = readme.read_text(encoding="utf-8").partition("\n")
        readme.write_text(f"{head}\n\n{note}\n{rest}", encoding="utf-8")


def github_target(name: str, allow_public: bool = False) -> tuple:
    """(URL, git's credential options, the commit's name and email) for the signed-in account's repository: private,
    or public only with allow_public (the owner made it public; this script never changes a repository's visibility)."""
    user = json.loads(run(["gh", "api", "user"]))
    login = user["login"]
    view = json.loads(run(["gh", "repo", "view", f"{login}/{name}", "--json", "visibility"]))
    if view["visibility"] != "PRIVATE" and not allow_public:
        raise SystemExit(f"github-snapshot: {login}/{name} isn't private: refusing. Going public is the owner's own step; "
                         "--allow-public pushes to a repository the owner has already made public.")
    return (f"https://github.com/{login}/{name}.git", GH_CREDENTIALS, login,
            f"{user['id']}+{login}@users.noreply.github.com")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A scrubbed snapshot in a private GitHub repository (dry run by default).")
    ap.add_argument("preset", choices=sorted(PRESETS))
    ap.add_argument("--source", default=str(ROOT), help="the git repository to read (default: this one)")
    ap.add_argument("--ref", default="origin/main", help="the ref to snapshot")
    ap.add_argument("--terms", default=os.environ.get("POF_SNAPSHOT_TERMS", DEFAULT_TERMS))
    ap.add_argument("--check", action="store_true", help="run the preset's tests on the scrubbed copy first")
    ap.add_argument("--push", action="store_true", help="commit and push when the scan is clean")
    ap.add_argument("--trailer", action="append", default=[], help="a line to end the commit message with")
    ap.add_argument("--remote-url", help="push here instead of GitHub (for tests): no gh, no privacy check")
    ap.add_argument("--allow-public", action="store_true",
                    help="accept a target the owner has already made public (it never changes visibility)")
    a = ap.parse_args(argv)

    preset = PRESETS[a.preset]
    replace, deny = read_terms(Path(a.terms).expanduser())
    source = Path(a.source).expanduser()
    sha = run(["git", "-C", str(source), "rev-parse", "--short=12", a.ref])
    if a.remote_url:
        url, creds, name, email = a.remote_url, [], "snapshot-test", "snapshot-test@example.invalid"
    else:
        url, creds, name, email = github_target(a.preset, a.allow_public)

    with tempfile.TemporaryDirectory(prefix="pof-snapshot-") as tmp:
        tree = Path(tmp) / "tree"
        run(["git", *creds, "clone", "-q", "--branch", BRANCH, "--single-branch", url, str(tree)])
        lay_out(tree, source, a.ref, preset)
        print(f"{a.preset}: {a.ref} ({sha}): scrubbed {scrub(tree, replace)} file(s)")
        found = scan(tree, replace, deny)
        if found:
            for rel, kind in found:
                print(f"  FOUND {kind}: {rel}")
            print(f"{a.preset}: {len(found)} finding(s): nothing pushed")
            return 1
        print(f"{a.preset}: the scan is clean")
        if a.check:
            for command in preset.get("check", []):
                r = subprocess.run([command], cwd=tree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if r.returncode:
                    print(r.stdout.decode(errors="replace")[-1500:])
                    print(f"{a.preset}: {command} failed: nothing pushed")
                    return 1
                print(f"{a.preset}: {command} passed")
        run(["git", "add", "-A"], cwd=tree)
        changes = run(["git", "status", "--short"], cwd=tree).splitlines()
        if not changes:
            print(f"{a.preset}: no changes")
            return 0
        print(f"{a.preset}: {len(changes)} file(s) would change:")
        for line in changes[:40]:
            print(f"  {line}")
        if not a.push:
            print(f"{a.preset}: a dry run: nothing pushed (--push to push)")
            return 0
        message = [f"proof-of-fix-175: snapshot of {a.preset} at {sha}"]
        if a.trailer:
            message += ["\n".join(a.trailer)]
        commit = ["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q"]
        for part in message:
            commit += ["-m", part]
        run(commit, cwd=tree)
        run(["git", *creds, "push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}"], cwd=tree)
        local = run(["git", "rev-parse", "HEAD"], cwd=tree)
        remote = run(["git", *creds, "ls-remote", "origin", f"refs/heads/{BRANCH}"], cwd=tree).split("\t")[0]
        if local != remote:
            raise SystemExit(f"github-snapshot: {a.preset}'s push didn't land")
        print(f"{a.preset}: pushed {local[:12]} to {BRANCH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
