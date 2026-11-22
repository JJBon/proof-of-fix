"""The release-candidate run (proof-of-fix#251, design L18, task 7.0; #256 item 6): `scripts/integration.sh
--release-candidate <commit>`.

1. The commit (a SHA, a tag or a branch name, resolved to its 40-hex SHA-1) is checked out into a fresh worktree
   outside this checkout (`git worktree add --detach`), so the run is that exact commit and nothing uncommitted. The
   pinned solc is copied in from this checkout's contracts/.cache when the worktree has none.
2. Every contract's creation-code hash is computed there (`scripts/deploy-sepolia.sh hashes`, as the deploy compares).
3. `scripts/integration.sh --version 3 --heal` runs there N times in a row (default 3), each from a clean state (its
   devnets are started and removed by the suite), stopping at the first failure. Each run is the story on #132's
   defaults and #256's lettered scenarios (scripts/integration-v3.sh), the `launch` set on the Sepolia record's rules.
   If the commit has the Radicle suite (tests/integration/suite_v3_radicle.py, #286), each run also runs
   `scripts/integration.sh --version 3 --radicle`.
4. Production windows only (#251 L4; validator-kit/SEVSNP-PLAN.md, "Boot time against the deadlines": an attested
   host's cold start takes about 127 s, more than a 120 s minute-windows seal window): a DEVNET_V3_WINDOWS other than
   `production` is refused, and every set's record must say `production`. One bounty with production windows on the
   moved clock (L18 item 2) is the story's funded bounty, judged, claimed, final and merged (steps 3 and 9).
   POF_V3_EXTERNAL (validator addresses run outside the suite, e.g. item 3's SEV-SNP host) is passed through: the
   suite then holds its clock at a deadline while such a validator's seat hasn't acted (tests/integration/suite_v3.py,
   `external_hold`).
5. The record (`pof-release-candidate/1`, scripts/deploy_sepolia.py's format) is written: the tag, the commit,
   `checks.integration` (the command and each run's result, with each set's result and time), `productionWindows`,
   `panelRules` (the launch set's, as Panels read them back), `bytecode`. The items this run can't check
   (`sevSnpValidator`, `realModelRun`, `attestedImages`: a real host and a paid model, task 7.0) are kept from an
   existing record of the same commit at that path when they are "passed", and are "pending" otherwise. `result` is
   "passed" only when every item passed, "failed" when a run failed, "incomplete" otherwise; the deploy script takes
   only "passed".

    scripts/integration.sh --release-candidate <commit> [--runs N] [--record FILE] [--tag NAME] [--logs DIR]
                                                        [--keep-worktree]
    scripts/integration.sh --release-candidate <commit> --external [--logs DIR] [--keep-worktree]

6. --external (task 7.0, items 3 and 6 on AWS: scripts/rc-aws.sh): that commit's external set only, in the same fresh
   worktree on production windows: `scripts/integration.sh --version 3 --external` (tests/integration/external_v3.py),
   with POF_V3_EXTERNAL and the POF_EXT_* settings passed through and POF_EXT_DIR set to the logs directory, where it
   writes ready.json (what the SEV-SNP host needs) and external.json (`pof-external-run/1`). No record is written here:
   `sevsnp_items` (called by scripts/rc_aws.py `record`) sets `sevSnpValidator` and `attestedImages` from external.json,
   the SEV-SNP host's verify.py result and the disk's manifest, and passes them only for an aws run of the record's
   commit whose outside validator registered as `tee`/`amd-sev-snp` with the manifest's image, sat a counted panel and
   revealed, on a boot whose every verify.py check ran and passed.

The record goes to contracts/release-candidates/<tag or the commit's first 12 digits>.json in this checkout unless
--record names another file; the runs' logs and numbers to --logs (default a new directory under the system's temporary
directory, printed). Docker and the pinned solc are needed, as for scripts/integration.sh. Nothing here touches a
public network."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from deploy_sepolia import CONTRACTS, RC_CHECKS, RC_FORMAT, RULE_FIELDS  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXTERNAL_CHECKS = tuple(c for c in RC_CHECKS if c != "productionWindows")  # recorded by their own runs (task 7.0)
SETS = ("story", "launch", "few-larger", "few-same")
EXTERNAL_FORMAT = "pof-external-run/1"
# verify.py's checks (validator-kit/sevsnp/verify.py): all must have run and passed; a skipped one (no AMD chain, no
# Nitro root, no expected measurement) leaves the items pending
VERIFY_CHECKS = ("roothash", "nonce", "snpReportData", "snpMeasurement", "snpPolicy", "snpSignature", "nitroPcrs",
                 "nitroBinding", "nitroSignature", "imageDigest", "attestedImages")
NAME, PORT = "pof-devnet-rc", "8566"  # its own devnet name and port, beside an ordinary integration run


class Stop(Exception):
    """The run can't start, or its record can't be written."""


def git(*args, cwd: Path = ROOT, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode:
        raise Stop(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def resolve(commit: str) -> str:
    sha = git("rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}", check=False)
    if not SHA_RE.match(sha):
        raise Stop(f"{commit!r} isn't a commit in this repository")
    return sha


def tag_of(sha: str, given: str | None) -> str:
    if given:
        return given
    tags = git("tag", "--points-at", sha).split()
    return tags[0] if tags else ""


def windows_env(env: dict) -> dict:
    kind = env.get("DEVNET_V3_WINDOWS", "production")
    if kind != "production":
        raise Stop(f"DEVNET_V3_WINDOWS={kind}: a release candidate runs on production windows only (#251 L4; an attested "
                   f"host can't cold-start inside a minute-windows seal window, validator-kit/SEVSNP-PLAN.md)")
    out = dict(env)
    out.update(DEVNET_V3_WINDOWS="production", POF_INTEGRATION_NAME=env.get("POF_RC_NAME", NAME),
               POF_INTEGRATION_PORT=env.get("POF_RC_PORT", PORT))
    for k in ("DEVNET_V3_PANEL_CAPS", "DEVNET_V3_K_TOP", "DEVNET_V3_CHALLENGE_SIZE"):
        out.pop(k, None)  # the story runs #132's defaults and each set names its own rules
    return out


def checkout(sha: str, keep: bool) -> Path:
    where = Path(tempfile.mkdtemp(prefix=f"pof-rc-{sha[:12]}-"))
    where.rmdir()
    git("worktree", "add", "--detach", str(where), sha)
    cache = ROOT / "contracts" / ".cache"
    if cache.is_dir() and not (where / "contracts" / ".cache").exists():
        shutil.copytree(cache, where / "contracts" / ".cache")
    return where


def drop(where: Path) -> None:
    subprocess.run(["chmod", "-R", "u+w", str(where)], capture_output=True)
    git("worktree", "remove", "--force", str(where), check=False)
    shutil.rmtree(where, ignore_errors=True)


def hashes(where: Path) -> dict:
    r = subprocess.run([sys.executable, "scripts/deploy_sepolia.py", "hashes"], cwd=str(where), capture_output=True,
                       text=True)
    if r.returncode:
        raise Stop(f"the bytecode hashes couldn't be computed: {(r.stderr or r.stdout).strip()[-400:]}")
    code = json.loads(r.stdout[r.stdout.index("{"):])["bytecode"]
    if set(code) != set(CONTRACTS):
        raise Stop("the hashes don't name every contract the deploy checks")
    return code


def one_run(where: Path, i: int, logs: Path, env: dict) -> dict:
    """One run of the suite in the worktree: its result, each set's result and time, and the numbers it wrote."""
    reports = logs / f"run-{i}"
    reports.mkdir(parents=True, exist_ok=True)
    started = time.time()
    commands = [["scripts/integration.sh", "--version", "3", "--heal", "--report-dir", str(reports)]]
    if (where / "tests" / "integration" / "suite_v3_radicle.py").is_file():
        commands.append(["scripts/integration.sh", "--version", "3", "--radicle"])
    ok, sets = True, {}
    with open(logs / f"run-{i}.log", "w", encoding="utf-8") as log:
        for cmd in commands:
            log.write(f"$ {' '.join(cmd)}\n")
            log.flush()
            r = subprocess.run(cmd, cwd=str(where), env=env, stdout=log, stderr=subprocess.STDOUT)
            ok &= r.returncode == 0
            if "--radicle" in cmd:
                sets["radicle"] = "passed" if r.returncode == 0 else "failed"
    text = (logs / f"run-{i}.log").read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("v3 integration: "):
            for part in line[len("v3 integration: "):].split("; "):
                bits = part.split()
                if len(bits) >= 2:
                    sets[bits[0]] = bits[1] + (f" ({bits[2]})" if len(bits) > 2 else "")
    numbers = {}
    for name in SETS:
        f = reports / f"{name}.json"
        if f.is_file():
            numbers[name] = json.loads(f.read_text(encoding="utf-8"))
    ok &= all(name in sets and sets[name].startswith("passed") for name in SETS)
    return {"result": "passed" if ok else "failed", "sets": sets, "wallSeconds": round(time.time() - started),
            "numbers": numbers}


def production(numbers: dict) -> bool:
    """Every set ran on production windows, as its devnet's record says."""
    return all(numbers.get(name, {}).get("windowsKind") == "production" for name in SETS)


def rules_of(numbers: dict) -> dict | None:
    rules = numbers.get("launch", {}).get("setup", {}).get("rules")
    return {k: rules[k] for k in RULE_FIELDS} if isinstance(rules, dict) and set(RULE_FIELDS) <= set(rules) else None


def record(sha: str, tag: str, runs: list, code: dict, rules: dict | None, earlier: dict | None, wanted: int) -> dict:
    passed = len(runs) >= wanted and all(r["result"] == "passed" for r in runs)
    checks: dict = {"integration": {"command": f"scripts/integration.sh --release-candidate {sha}",
                                    "runs": [r["result"] for r in runs],
                                    "details": [{"sets": r["sets"], "wallSeconds": r["wallSeconds"]} for r in runs]},
                    "productionWindows": "passed" if passed and all(production(r["numbers"]) for r in runs)
                    else "failed"}
    for c in EXTERNAL_CHECKS:
        old = (earlier or {}).get("checks", {}).get(c)
        checks[c] = old if old == "passed" else "pending"
        for k in (f"{c}Evidence",):  # an evidence pointer recorded beside the item, kept with it
            if earlier and k in earlier.get("checks", {}):
                checks[k] = earlier["checks"][k]
    return {"format": RC_FORMAT, "tag": tag, "commit": sha, "result": result_of(checks, passed), "checks": checks,
            "panelRules": rules or {}, "bytecode": code}


def result_of(checks: dict, runs_passed: bool) -> str:
    """The record's `result`: "failed" when a run failed or the windows weren't production's, "passed" when every
    item passed, "incomplete" otherwise."""
    if not runs_passed or checks.get("productionWindows") != "passed":
        return "failed"
    return "passed" if all(checks.get(c) == "passed" for c in RC_CHECKS) else "incomplete"


def runs_passed(rc: dict, wanted: int = 3) -> bool:
    runs = rc.get("checks", {}).get("integration", {}).get("runs", [])
    return len(runs) >= wanted and all(r == "passed" for r in runs)


def verify_problems(verify: dict, manifest: dict) -> list:
    """Why verify.py's result doesn't attest the boot (an empty list when it does): every check ran and passed, and
    the checker image's digest it recomputed is the manifest's."""
    out = []
    checks = verify.get("checks", {}) if isinstance(verify, dict) else {}
    if not (isinstance(verify, dict) and verify.get("passed") is True):
        out.append("verify.py didn't pass")
    for c in VERIFY_CHECKS:
        if not (isinstance(checks.get(c), dict) and checks[c].get("ok") is True):
            out.append(f"verify.py's {c} " + ("didn't run (skipped)" if c not in checks else "failed"))
    digest = str(manifest.get("image_digest", "")).lower()
    if not digest.startswith("0x") or len(digest) != 66:
        out.append("the manifest has no image_digest")
    elif str(checks.get("imageDigest", {}).get("detail", "")).lower() != digest:
        out.append("verify.py's image digest isn't the manifest's")
    return out


def external_problems(external: dict, commit: str, manifest: dict) -> list:
    """Why the external run doesn't show a real SEV-SNP validator registering and judging a fix on this commit (an
    empty list when it does)."""
    out = []
    if not isinstance(external, dict) or external.get("format") != EXTERNAL_FORMAT:
        return [f"the external run's result isn't {EXTERNAL_FORMAT}"]
    if external.get("result") != "passed":
        out.append(f"the external run {external.get('result', 'has no result')}")
    if external.get("mode") != "aws":
        out.append(f"the external run was {external.get('mode')!r}, not on AWS with the SEV-SNP host (a rehearsal "
                   f"passes nothing)")
    if external.get("commit") != commit:
        out.append(f"the external run is of commit {str(external.get('commit'))[:12]}, not {commit[:12]}")
    if external.get("windowsKind") != "production":
        out.append("the external run's windows weren't production's")
    digest = str(manifest.get("image_digest", "")).lower()
    reg = external.get("registration", {})
    if reg.get("proofType") != "tee" or reg.get("teeType") != "amd-sev-snp":
        out.append(f"the outside validator registered as {reg.get('proofType')}/{reg.get('teeType')}, not "
                   f"tee/amd-sev-snp")
    if str(reg.get("image", "")).lower() != digest:
        out.append("the outside validator's registered image isn't the manifest's image_digest")
    if digest not in [str(x).lower() for x in external.get("acceptedImages", [])]:
        out.append("the test chain didn't list the manifest's image_digest as accepted")
    j = external.get("judged", {})
    if not (j.get("kind") == "Counted" and j.get("sealed") and j.get("revealed") and j.get("counted")):
        out.append("the outside validator didn't seal and reveal on a counted panel that counted")
    return out


def sevsnp_items(rc: dict, external: dict, verify: dict, manifest: dict, evidence: str) -> tuple:
    """(the record with `sevSnpValidator` and `attestedImages` set from the AWS run, the reasons any stays pending).
    `attestedImages` (L18 item 6, L21): verify.py attests the SEV-SNP host's boot in every check, its image digest is
    the manifest's, and the test chain accepted that image. `sevSnpValidator` (item 3): that, and the external run
    (`pof-external-run/1`, on AWS, of the record's commit, production windows) shows the host's key registered as
    tee/amd-sev-snp with that image and sealed and revealed on a counted panel. An item already passed stays passed;
    a failed check leaves it pending, never failed (another run can still pass it)."""
    out = json.loads(json.dumps(rc))
    checks = out.setdefault("checks", {})
    vp = verify_problems(verify, manifest)
    images = vp + [p for p in external_problems(external, rc.get("commit", ""), manifest)
                   if "accepted" in p or "the external run's result" in p]
    validator = vp + external_problems(external, rc.get("commit", ""), manifest)
    for item, problems in (("attestedImages", images), ("sevSnpValidator", validator)):
        if checks.get(item) == "passed":
            continue
        checks[item] = "pending" if problems else "passed"
        if not problems:
            checks[f"{item}Evidence"] = evidence
    out["result"] = result_of(checks, runs_passed(out))
    return out, {"attestedImages": images, "sevSnpValidator": validator}


def external_run(where: Path, logs: Path, env: dict) -> dict:
    """The external set in the worktree (`--version 3 --external`): its external.json, or a failed result."""
    run_env = dict(env, POF_EXT_DIR=str(logs))
    result = logs / "external.json"
    if result.exists():
        result.unlink()
    started = time.time()
    with open(logs / "external.log", "w", encoding="utf-8") as log:
        r = subprocess.run(["scripts/integration.sh", "--version", "3", "--external"], cwd=str(where), env=run_env,
                           stdout=log, stderr=subprocess.STDOUT)
    kept = where / ".external-v3"  # its results and node logs, kept beside the logs before the worktree goes
    if kept.is_dir():
        shutil.copytree(kept, logs / "external-v3", dirs_exist_ok=True, ignore=shutil.ignore_patterns("work"))
    try:
        doc = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        doc = {"format": EXTERNAL_FORMAT, "result": "failed", "why": "no external.json"}
    if r.returncode and doc.get("result") == "passed":
        doc["result"] = "failed"
    doc["wallSecondsTotal"] = round(time.time() - started)
    return doc


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description="the release-candidate run (#251 L18)")
    ap.add_argument("commit")
    ap.add_argument("--runs", type=int, default=3, help="runs in a row (default 3: the deploy needs the last 3 passed)")
    ap.add_argument("--record", help="the record's file (default contracts/release-candidates/<tag or sha>.json)")
    ap.add_argument("--tag", help="the release candidate's name (default the commit's first tag)")
    ap.add_argument("--logs", help="where the runs' logs and numbers go (default a new temporary directory)")
    ap.add_argument("--keep-worktree", action="store_true")
    ap.add_argument("--external", action="store_true",
                    help="only the external set (task 7.0 on AWS, scripts/rc-aws.sh): ready.json and external.json in "
                         "--logs; no record")
    a = ap.parse_args(argv)
    # stopped from outside (SIGTERM), the worktree is still removed (`finally`) and no record is written
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    try:
        if a.runs < 1:
            raise Stop("--runs is at least 1")
        env = windows_env(os.environ)
        sha = resolve(a.commit)
        if a.external:
            return external_main(sha, a, env)
        tag = tag_of(sha, a.tag)
        out = Path(a.record) if a.record else ROOT / "contracts" / "release-candidates" / f"{tag or sha[:12]}.json"
        earlier = None
        if out.is_file():
            try:
                earlier = json.loads(out.read_text(encoding="utf-8"))
            except ValueError:
                raise Stop(f"{out} exists and isn't JSON: not overwritten") from None
            if earlier.get("commit") != sha:
                raise Stop(f"{out} is the record of another commit ({str(earlier.get('commit'))[:12]}): not overwritten")
        logs = Path(a.logs) if a.logs else Path(tempfile.mkdtemp(prefix=f"pof-rc-logs-{sha[:12]}-"))
        logs.mkdir(parents=True, exist_ok=True)
        print(f"release candidate {tag or '(untagged)'} at {sha}: logs in {logs}", flush=True)
        where = checkout(sha, a.keep_worktree)
        try:
            code = hashes(where)
            print(f"bytecode hashes of {len(code)} contracts computed at {sha[:12]}", flush=True)
            runs: list = []
            for i in range(1, a.runs + 1):
                print(f"run {i} of {a.runs} ...", flush=True)
                r = one_run(where, i, logs, env)
                runs.append(r)
                print(f"run {i}: {r['result']} in {r['wallSeconds']:,} s ({', '.join(f'{k} {v}' for k, v in r['sets'].items())})",
                      flush=True)
                if r["result"] != "passed":
                    break
        finally:
            if a.keep_worktree:
                print(f"worktree kept: {where}")
            else:
                drop(where)
        rules = next((rules_of(r["numbers"]) for r in runs if rules_of(r["numbers"])), None)
        rc = record(sha, tag, runs, code, rules, earlier, a.runs)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rc, indent=2) + "\n", encoding="utf-8")
        pending = [c for c in RC_CHECKS if rc["checks"][c] != "passed"]
        print(f"record: {out} (result {rc['result']}" + (f"; not passed yet: {', '.join(pending)}" if pending else "")
              + ")", flush=True)
        return 0 if rc["checks"]["integration"]["runs"] and all(r == "passed" for r in rc["checks"]["integration"]["runs"]) \
            and len(runs) == a.runs else 1
    except Stop as e:
        print(f"release candidate: {e}", file=sys.stderr)
        return 2


def external_main(sha: str, a, env: dict) -> int:
    logs = Path(a.logs) if a.logs else Path(tempfile.mkdtemp(prefix=f"pof-rc-external-{sha[:12]}-"))
    logs.mkdir(parents=True, exist_ok=True)
    mode = env.get("POF_EXT_MODE", "local")
    print(f"release candidate {sha}: the external set ({mode}); ready.json and external.json in {logs}", flush=True)
    where = checkout(sha, a.keep_worktree)
    try:
        doc = external_run(where, logs, env)
    finally:
        if a.keep_worktree:
            print(f"worktree kept: {where}")
        else:
            drop(where)
    print(f"external set: {doc.get('result')} in {doc.get('wallSecondsTotal', 0):,} s ({logs / 'external.json'})",
          flush=True)
    return 0 if doc.get("result") == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
