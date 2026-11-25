#!/usr/bin/env python3
"""A scrubbed snapshot of this project in its private GitHub repositories (proof-of-fix#175, #158), and the public
Radicle snapshot (#251 task 5.1, design L13).

It takes a git ref's tracked files, replaces private terms, and scans the result. It commits to the target's `snapshot`
branch only when the scan is clean, and only with --push: the default is a dry run. It's a snapshot, not a mirror: no
history goes across, only one new commit each time.

`--target radicle` writes the scrubbed tree, when the scan is clean, as **one root commit** in a new local repository
(--out, or a new temporary folder that is kept), and prints the root commit and how many times each private term was
replaced (by its number and kind, never its value). That is all a dry run does: no Radicle command runs. `rad init`
runs only with --publish and a node named explicitly (--rad-home, that node's RAD_HOME), and then writes the
publication record (seed/publication.py, `pof-radicle-publication/1`) to --record. The root commit is the same for the
same ref and terms (its author and dates are fixed), so the commit a dry run prints is the one --publish publishes;
--expect-root refuses anything else. Publishing is the owner's own step (#251 task 6.1).

The private terms stay out of this repository: they're in a file on the owner's machine (--terms, default
~/.config/proof-of-fix/snapshot-terms, `old => new` per line in order, `deny: literal` to fail the scan if it's left), and
the script refuses to run without them. It also refuses a target that isn't private, unless --allow-public names the step
the owner took (proof-of-fix went public on 2026-11-18, #251).

    scripts/github_snapshot.py proof-of-fix                                  # a dry run: what would change
    scripts/github_snapshot.py proof-of-fix --check --push                   # with the tests, then push
    scripts/github_snapshot.py pof-devnet-infra --source ~/dev/infra --push
    scripts/github_snapshot.py proof-of-fix --target radicle --out ~/pof-public  # the public snapshot, a dry run
    scripts/github_snapshot.py proof-of-fix --target radicle --out ~/pof-public --expect-root <sha> \
        --publish --rad-home ~/.radicle --record ~/pof-public-record.json          # rad init: only at the owner's go

Standard library, git and tar; gh for a GitHub target, rad for --publish. The scan names files and kinds of finding,
never the values."""

from __future__ import annotations

import argparse
import importlib.util
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
# What the measured disk (scripts/checker-disk.sh) and its checker image (oracle/Dockerfile's COPY lines) are built
# from: a directory ends with "/".
IMAGE_INPUTS = ["oracle/", "pof/", "bot/", "pofctl/", "scripts/judge_run.py", "scripts/checker-disk.sh",
                "validator-kit/sevsnp/disk/"]
PRESETS = {
    "proof-of-fix": {
        "paths": [],
        "note": "> A scrubbed snapshot. Development happens on a private Forgejo, which keeps the full history; issue "
                "numbers (`#123`) refer to its tracker, and example.com and example-org stand in for internal addresses.",
        "check": ["scripts/check.sh"],
        # The validator's measured disk and its checker image are built from these files, and the deployment accepts
        # only the image digests it lists: a scrubbed byte would change the digest, so nobody could build the listed
        # image from the public code (the owner's decision, 2026-11-23, #251). They go across unscrubbed; the scan
        # still refuses secrets, AWS account ids and denied terms in them, and the run prints what each term kept.
        "verbatim": IMAGE_INPUTS,
        # Only these refs may keep a private term in those files (v3.1 polish VP15): live v3's commit and the branch
        # its image is built from, whose digest must stay reproducible while v3 lives. Any other ref copies them
        # verbatim too, but a kept term fails the run: a clean file scrubs to itself. Emptied, and this exemption
        # removed, when v3 sunsets (the owner's decision, 2026-11-23, Q3).
        "verbatim_refs": ["8946b9c", "sepolia-v3"],
    },
    "pof-devnet-infra": {
        "paths": ["modules/pof_devnet", "modules/compose_host", "modules/schedule", "modules/scripts",
                  "environments/prod/us-east-1/pof-devnet"],
        "drop": ["environments/prod/us-east-1/pof-devnet/backend.tf"],
        "keep": ["README.md"],  # written for this repository, it lives only there
    },
}
# The Radicle target (#251 L13): the root commit's fixed author (the licence's copyright line) and the repository's
# name and description at `rad init`.
RADICLE_AUTHOR = ("Contributors to proof-of-fix", "contributors@proof-of-fix.invalid")
RADICLE_NAME = "proof-of-fix"
RADICLE_DESCRIPTION = ("Bounties for open-source fixes, judged by independent AI validators, paid by keyless smart "
                       "contracts (research; a Sepolia testnet, test coin only)")
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


def term_kinds(path: Path) -> list:
    """Each replacement's kind, in read_terms' order: the label of the last `# kind: <label>` comment above it, or else
    a guess from its shape. Never its value: this is what the owner reviews (#251 task 5.2)."""
    kinds, label = [], ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("deny:"):
            continue
        if " => " in line or line.rstrip().endswith(" =>"):
            kinds.append(label or shape_of(line.partition(" =>")[0].strip()))
        elif line.startswith("# kind:"):
            label = line[len("# kind:"):].strip()
    return kinds


def shape_of(term: str) -> str:
    if re.fullmatch(r"\d{12}", term):
        return "an AWS account id"
    if "@" in term:
        return "an email address"
    if "/" in term:
        return "a path or URL"
    if re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}", term):
        return "a domain"
    return "a phrase" if " " in term else "a word"


def is_verbatim(rel: str, verbatim: list) -> bool:
    """Whether a path (relative, with "/") is one of `verbatim`'s files or under one of its directories."""
    return any(rel.startswith(v) if v.endswith("/") else rel == v for v in verbatim)


def verbatim_exempt(source: Path, ref: str, preset: dict) -> bool:
    """Whether `ref` is one of the preset's `verbatim_refs` (VP15): it resolves to the same commit as a listed ref, a
    commit or a branch (local, or origin's), in `source`. Only then may the image files keep a private term."""
    listed = preset.get("verbatim_refs", [])
    if not listed:
        return False

    def commit(name: str) -> str | None:
        r = subprocess.run(["git", "-C", str(source), "rev-parse", "--verify", "-q", f"{name}^{{commit}}"],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        return r.stdout.decode().strip() if r.returncode == 0 else None

    sha = commit(ref)
    if sha is None:
        return False
    for name in listed:
        for candidate in (name, f"origin/{name}"):
            if commit(candidate) == sha:
                return True
    return False


def term_hits(root: Path, replace: list, paths: list) -> list:
    """Where the replacements' terms are in `paths` (files, or directories ending with "/") under root: (file, line,
    term number), the number in read_terms' order, from 1. Never the value: this output may end up anywhere."""
    hits = []
    for path in paths:
        base = root / path.rstrip("/")
        if path.endswith("/"):
            files = text_files(base) if base.is_dir() else []
        else:
            files = [(base, base.read_text(encoding="utf-8", errors="replace"))] if base.is_file() else []
        for p, text in files:
            rel = p.relative_to(root).as_posix()
            if "__pycache__" in rel.split("/"):
                continue
            hits += [(rel, n, i) for n, line in enumerate(text.splitlines(), 1)
                     for i, (old, _) in enumerate(replace, 1) if old and old in line]
    return hits


def scrub(root: Path, replace: list, counts: list | None = None, verbatim: list = (),
          kept: list | None = None) -> int:
    """Replaces the terms in every text file but `verbatim`'s; returns how many files changed. `counts`, if given (one
    [occurrences, files] per replacement), is filled with what each replacement found; `kept`, the same shape, with
    what it left in `verbatim`'s files."""
    changed = 0
    for p, text in text_files(root):
        if is_verbatim(p.relative_to(root).as_posix(), verbatim):
            for i, (old, _) in enumerate(replace):
                if kept is not None and old and old in text:
                    kept[i][0] += text.count(old)
                    kept[i][1] += 1
            continue
        out = text
        for i, (old, new) in enumerate(replace):
            if counts is not None and old and old in out:
                counts[i][0] += out.count(old)
                counts[i][1] += 1
            out = out.replace(old, new)
        if out != text:
            p.write_text(out, encoding="utf-8")
            changed += 1
    return changed


def scan(root: Path, replace: list, deny: list, verbatim: list = ()) -> list:
    """Findings as (file, kind). Never the value: this output may end up anywhere. A `verbatim` file may keep the
    replacements' terms, never a denied term or a secret."""
    found = []
    # A replacement's new text can legitimately contain nothing private, but its old text must be gone.
    literals = [("a private term", old) for old, _ in replace] + [("a denied term", d) for d in deny]
    for p, text in text_files(root):
        rel = str(p.relative_to(root))
        kept = is_verbatim(p.relative_to(root).as_posix(), verbatim)
        for kind, literal in literals:
            if kept and kind == "a private term":
                continue
            if literal in text:
                found.append((rel, kind))
                break
        for kind, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                found.append((rel, kind))
    return found


# The public snapshot's extra checks (#251 task 5.2, #158's list), on the Radicle target only: shapes, not values. A
# 12-digit number is an account id when account wording comes just before it; the fakes above are allowed.
FAKE_ACCOUNTS = {"111111111111", "123456789012", "000000000000"}
ACCOUNT_WORDING = ("account", "arn:aws:", "access-", "profile", "owner-id", "owner_id")
PLATFORM_PATTERN = r"\bplat" + r"form#\d+|~/dev/" + r"platform\b"  # split, so neither this line nor a scrub term matches it


def public_scan(root: Path, verbatim: list = ()) -> list:
    """Findings as (file, kind) for what the GitHub scan doesn't look for: an AWS account id written without an ARN,
    and a reference to the private platform repository (its issues, `infra#123`, or its checkout), which a
    `verbatim` file may keep."""
    found = []
    for p, text in text_files(root):
        rel = str(p.relative_to(root))
        kept = is_verbatim(p.relative_to(root).as_posix(), verbatim)
        for m in re.finditer(r"(?<![\d.])\d{12}(?!\d)", text):
            n = m.group(0)
            if n in FAKE_ACCOUNTS or len(set(n)) == 1:
                continue
            if any(w in text[max(0, m.start() - 60):m.start()].lower() for w in ACCOUNT_WORDING):
                found.append((rel, "an AWS account id"))
                break
        if not kept and re.search(PLATFORM_PATTERN, text):
            found.append((rel, "a platform reference"))
    return found


def run(args: list, cwd=None, stdin=None, capture=True, env=None) -> str:
    r = subprocess.run(args, cwd=cwd, input=stdin, stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE,
                       env=env)
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


def publication_module():
    """seed/publication.py: the record's format and checks, the one place the seed takes the RID from."""
    spec = importlib.util.spec_from_file_location("publication", ROOT / "seed" / "publication.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit_root(repo: Path, source: Path, ref: str, sha: str, preset: str, trailers: list) -> str:
    """The tree in `repo` as one root commit on `main`: a fixed author and the ref's own commit date, so the same ref
    and terms give the same commit. Nothing from the user's git configuration (hooks, excludes, signing) applies."""
    date = run(["git", "-C", str(source), "log", "-1", "--format=%cI", ref])
    name, email = RADICLE_AUTHOR
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date, "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull}
    git = ["git", "-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "commit.gpgsign=false",
           "-c", f"core.hooksPath={os.devnull}", "-c", f"core.excludesFile={os.devnull}", "-c", "core.autocrlf=false"]
    run(git + ["init", "-q"], cwd=repo, env=env)
    run(git + ["symbolic-ref", "HEAD", "refs/heads/main"], cwd=repo, env=env)
    run(git + ["add", "-A"], cwd=repo, env=env)
    commit = git + ["commit", "-q", "-m", f"proof-of-fix-251: snapshot of {preset} at {sha}"]
    if trailers:
        commit += ["-m", "\n".join(trailers)]
    run(commit, cwd=repo, env=env)
    if run(["git", "rev-list", "--count", "HEAD"], cwd=repo) != "1":
        raise SystemExit("github-snapshot: the new repository has more than one commit")
    return run(["git", "rev-parse", "HEAD"], cwd=repo)


def rad_publish(repo: Path, root: str, rad_home: Path, record_path: Path, name: str, description: str) -> dict:
    """`rad init` of the snapshot on the node at rad_home (the owner's go, #251 task 6.1, comes first), then the
    publication record. Refuses a Radicle release other than the one the record pins (checked against #92 first)."""
    pub = publication_module()
    env = {**os.environ, "RAD_HOME": str(rad_home)}
    version = run(["rad", "--version"], env=env)
    if version.split()[:2] != ["rad", pub.RADICLE]:
        raise SystemExit(f"github-snapshot: this rad is {version!r}, not the pinned {pub.RADICLE} "
                         "(seed/publication.py): nothing published")
    did = run(["rad", "self", "--did"], env=env)
    nid = did[len("did:key:"):] if did.startswith("did:key:") else did
    # Not captured: rad may ask for the node key's passphrase, and its own output is the publish's log.
    init = subprocess.run(["rad", "init", "--name", name, "--description", description, "--default-branch", "main",
                           "--public", "--no-confirm"], cwd=repo, env=env)
    if init.returncode:
        raise SystemExit(f"github-snapshot: rad init failed (exit {init.returncode}): no record written")
    rid = run(["rad", "."], cwd=repo, env=env)
    record = pub.check({"format": pub.FORMAT, "rid": rid, "rootCommit": root, "nodeId": nid,
                        "radicle": pub.RADICLE})
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def not_listed(preset: dict) -> str:
    listed = ", ".join(preset.get("verbatim_refs", [])) or "none"
    return f"only the listed refs ({listed}) may keep a private term in the image's files; clean the file"


def radicle_target(a, preset: dict, replace: list, deny: list, kinds: list, source: Path, sha: str) -> int:
    """#251 task 5.1 (L13): the scrubbed tree as one root commit in a new local repository; `rad init` only with
    --publish and the node named."""
    out = Path(a.out).expanduser() if a.out else None
    if out is not None and out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise SystemExit(f"github-snapshot: {out} exists and isn't empty: the snapshot goes in a new repository")
    rad_home = record_path = None
    if a.publish:
        rad_home, record_path = Path(a.rad_home).expanduser(), Path(a.record).expanduser()
        if not rad_home.is_dir():
            raise SystemExit(f"github-snapshot: no Radicle node at {rad_home} (--rad-home is the node's RAD_HOME)")
        if record_path.exists():
            raise SystemExit(f"github-snapshot: {record_path} exists: a publication is recorded once")
    with tempfile.TemporaryDirectory(prefix="pof-snapshot-") as tmp:
        tree = Path(tmp) / "tree"
        tree.mkdir()
        lay_out(tree, source, a.ref, preset)
        counts, kept, verbatim = [[0, 0] for _ in replace], [[0, 0] for _ in replace], preset.get("verbatim", [])
        exempt = verbatim_exempt(source, a.ref, preset)
        print(f"{a.preset} for Radicle: {a.ref} ({sha}): scrubbed {scrub(tree, replace, counts, verbatim, kept)} "
              "file(s)")
        for i, ((n, files), (k, kfiles), kind) in enumerate(zip(counts, kept, kinds), 1):
            print(f"  term {i} ({kind}): replaced {n} time(s) in {files} file(s)"
                  + (f"; kept {k} time(s) in {kfiles} file(s) the image is built from" if k else "")
                  + ("" if exempt or not k else f" (refused: {not_listed(preset)})"))
        allowed = verbatim if exempt else ()
        found = scan(tree, replace, deny, allowed) + public_scan(tree, allowed)
        if found:
            for rel, kind in found:
                print(f"  FOUND {kind}: {rel}")
            kinds_found = sorted({kind for _, kind in found})
            print(f"{a.preset}: {len(found)} finding(s) ({', '.join(kinds_found)}): nothing created, nothing published")
            return 1
        print(f"{a.preset}: the scan is clean: none of the {len(replace)} private and {len(deny)} denied term(s) left, "
              "no secret pattern, no AWS account id, no platform reference")
        if a.check:
            for command in preset.get("check", []):
                r = subprocess.run([command], cwd=tree, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if r.returncode:
                    print(r.stdout.decode(errors="replace")[-1500:])
                    print(f"{a.preset}: {command} failed: nothing created, nothing published")
                    return 1
                print(f"{a.preset}: {command} passed")
        repo = out if out is not None else Path(tempfile.mkdtemp(prefix="pof-radicle-snapshot-"))
        repo.mkdir(parents=True, exist_ok=True)
        for child in sorted(tree.iterdir()):
            shutil.move(str(child), str(repo / child.name))
    root = commit_root(repo, source, a.ref, sha, a.preset, a.trailer)
    files = len(run(["git", "ls-files"], cwd=repo).splitlines())
    print(f"{a.preset}: one root commit {root} ({files} files) in a new repository at {repo}")
    if a.expect_root and a.expect_root != root:
        print(f"{a.preset}: the root commit isn't the expected {a.expect_root}: nothing published")
        return 1
    if not a.publish:
        print(f"{a.preset}: a dry run: no Radicle command ran, nothing published (at the owner's go: --publish "
              "--rad-home <node> --record <file>, with --expect-root naming this commit)")
        return 0
    record = rad_publish(repo, root, rad_home, record_path, a.rad_name, a.rad_description)
    print(f"{a.preset}: published {record['rid']} (root {root}) from node {record['nodeId']}; record: {record_path}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="A scrubbed snapshot in a private GitHub repository, or as one root commit "
                                             "for Radicle (dry run by default).")
    ap.add_argument("preset", choices=sorted(PRESETS))
    ap.add_argument("--source", default=str(ROOT), help="the git repository to read (default: this one)")
    ap.add_argument("--ref", default="origin/main", help="the ref to snapshot")
    ap.add_argument("--terms", default=os.environ.get("POF_SNAPSHOT_TERMS", DEFAULT_TERMS))
    ap.add_argument("--check", action="store_true", help="run the preset's tests on the scrubbed copy first")
    ap.add_argument("--push", action="store_true", help="commit and push when the scan is clean")
    ap.add_argument("--trailer", action="append", default=[], help="a line to end the commit message with")
    ap.add_argument("--remote-url", help="push here instead of GitHub (for tests): no gh, no privacy check")
    ap.add_argument("--branch", default=BRANCH,
                    help=f"github: the branch to push (default {BRANCH}); another one starts from {BRANCH}'s tip, "
                         "e.g. a preview of unreleased code beside the released snapshot")
    ap.add_argument("--allow-public", action="store_true",
                    help="accept a target the owner has already made public (it never changes visibility)")
    ap.add_argument("--target", choices=["github", "radicle"], default="github",
                    help="github (default): the preset's GitHub repository; radicle: one root commit in a new local "
                         "repository (#251 L13)")
    ap.add_argument("--out", help="radicle: the new repository's folder (new or empty; default: a new temporary one)")
    ap.add_argument("--publish", action="store_true",
                    help="radicle: rad init the snapshot on the node named by --rad-home and write --record")
    ap.add_argument("--rad-home", help="radicle: the publishing node's RAD_HOME (required with --publish)")
    ap.add_argument("--record", help="radicle: where to write the publication record (required with --publish)")
    ap.add_argument("--expect-root", help="radicle: refuse unless the root commit is this one (the owner's go names it)")
    ap.add_argument("--rad-name", default=RADICLE_NAME, help="radicle: the repository's name at rad init")
    ap.add_argument("--rad-description", default=RADICLE_DESCRIPTION, help="radicle: its description at rad init")
    a = ap.parse_args(argv)
    if a.target == "radicle":
        given = [f for f, v in (("--push", a.push), ("--remote-url", a.remote_url),
                                ("--allow-public", a.allow_public), ("--branch", a.branch != BRANCH)) if v]
        if given:
            ap.error(f"{', '.join(given)}: the GitHub target's, not the Radicle target's")
        if a.preset != "proof-of-fix":
            ap.error("the Radicle target publishes proof-of-fix only")
        if a.publish and not (a.rad_home and a.record):
            ap.error("--publish needs the node (--rad-home, its RAD_HOME) and --record, both named explicitly")
    else:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}", a.branch) or ".." in a.branch:
            ap.error(f"--branch: not a plain branch name: {a.branch!r}")
        given = [f for f, v in (("--out", a.out), ("--publish", a.publish), ("--rad-home", a.rad_home),
                                ("--record", a.record), ("--expect-root", a.expect_root)) if v]
        if given:
            ap.error(f"{', '.join(given)}: the Radicle target's (--target radicle)")

    preset = PRESETS[a.preset]
    replace, deny = read_terms(Path(a.terms).expanduser())
    if a.target == "radicle":
        source = Path(a.source).expanduser()
        sha = run(["git", "-C", str(source), "rev-parse", "--short=12", a.ref])
        return radicle_target(a, preset, replace, deny, term_kinds(Path(a.terms).expanduser()), source, sha)
    source = Path(a.source).expanduser()
    sha = run(["git", "-C", str(source), "rev-parse", "--short=12", a.ref])
    if a.remote_url:
        url, creds, name, email = a.remote_url, [], "snapshot-test", "snapshot-test@example.invalid"
    else:
        url, creds, name, email = github_target(a.preset, a.allow_public)

    with tempfile.TemporaryDirectory(prefix="pof-snapshot-") as tmp:
        tree = Path(tmp) / "tree"
        run(["git", *creds, "clone", "-q", "--branch", BRANCH, "--single-branch", url, str(tree)])
        if a.branch != BRANCH:  # a preview branch: its earlier tip if it exists, else the snapshot's
            if run(["git", *creds, "ls-remote", "origin", f"refs/heads/{a.branch}"], cwd=tree):
                run(["git", *creds, "fetch", "-q", "origin", f"refs/heads/{a.branch}"], cwd=tree)
                run(["git", "reset", "-q", "--hard", "FETCH_HEAD"], cwd=tree)
        lay_out(tree, source, a.ref, preset)
        verbatim = preset.get("verbatim", [])
        exempt = verbatim_exempt(source, a.ref, preset)
        print(f"{a.preset}: {a.ref} ({sha}): scrubbed {scrub(tree, replace, verbatim=verbatim)} file(s)")
        found = scan(tree, replace, deny, verbatim if exempt else ())
        if found and not exempt and any(kind == "a private term" and is_verbatim(rel.replace(os.sep, "/"), verbatim)
                                        for rel, kind in found):
            print(f"  a private term kept in a file the image is built from: {not_listed(preset)}")
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
        run(["git", *creds, "push", "-q", "origin", f"HEAD:refs/heads/{a.branch}"], cwd=tree)
        local = run(["git", "rev-parse", "HEAD"], cwd=tree)
        remote = run(["git", *creds, "ls-remote", "origin", f"refs/heads/{a.branch}"], cwd=tree).split("\t")[0]
        if local != remote:
            raise SystemExit(f"github-snapshot: {a.preset}'s push didn't land")
        print(f"{a.preset}: pushed {local[:12]} to {a.branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
