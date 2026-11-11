"""One real bounty on a shared devnet (#150, #112), start to finish: scripts/first-bounty.sh runs it.

The target's main stays as it is, so its head on-chain (the deployment's genesis) stays the base every fix is checked on.
Its bug is real: bot/sample/stats.py's median() is wrong for an even count. The issue reports it, and each fix is a
commit on main that adds the acceptance test at the repository's root and a stats.py:
- a failing fix (bot/fixes/bad_stats.py): the lower middle value. The sandbox's tests fail;
- the passing fix (bot/fixes/good_stats.py). They pass.
The test has to be at the root: the sandbox runs `python -m unittest` there, which finds no tests in this tree by itself
(exit 5, a failure), so main alone can't pass.

The flow (pofctl's roles, with the role keys; the long-running bot, bot/loop.py, is v1's local loop and isn't needed):
  register and accept the issue (the stub quorum signs the registration check), fund it, attempt, then seal failing fixes
  one at a time until the owner's seat is drawn (or --max-fails), each decided by the drawn nodes; seal the passing fix;
  it wins; merge it on the forge; the drawn nodes sign the merge; warp to the last instalment and settle (the bot
  closes the issue once paid, linking the payout); the funder's refund; everyone's fees and credits withdrawn. Then the
  books: who was drawn, who reported, what each was paid.

The draw can't be forced or predicted: the seed mixes in the block's RANDAO value, which the solver doesn't know when it
seals (RaceV2Base._submit). Each submission draws 3 of 7, so one seat is drawn with chance 3/7 per submission, and over n
submissions with 1 - (4/7)^n: 67 % with 2, 94 % with 5, 99 % with 8. A failing check costs only its metered fee, in the
test coin, and returns the rest of its deposit, so the run seals failing fixes until it has one.

--until-owner-on-pass N closes what that leaves open: a real model judging a correct fix. The first bounty merges its fix,
so main has no median bug any more, but it has another real one: mean([]) crashes with ZeroDivisionError. Each try opens a
new bounty on it and seals a correct fix, with no failing fixes. If the owner's seat isn't drawn, the pull request closes
unmerged and the bug stays for the next try (the bounty stays Won, its merge expires). When it's drawn, the fix merges. No
warp, so the shared clock stays put. It's one target: once merged, the bug is gone.

Its transactions go to the devnet named by POFCTL_RPC, and its writes to the forge. It refuses any chain but a devnet's."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.forge import repo_for  # noqa: E402
from bot.logic import LABEL  # noqa: E402
from oracle import v2  # noqa: E402
from oracle.crypto import address, checksum  # noqa: E402
from pofctl import keys  # noqa: E402
from pofctl.cli import DEVNET_CHAINS, run  # noqa: E402
from pofctl.race import C, Race, load_record  # noqa: E402
from pofctl.rpc import Rpc, Reverted, auth_headers  # noqa: E402

ISSUE_TITLE = "median() is wrong for an even count: median([4, 1, 3, 2]) returns 3, it should be 2.5"
ISSUE_BODY = """`bot/sample/stats.py`: for an even count, `median()` returns one of the two middle values instead of their mean.

```python
median([4, 1, 3, 2])  # 3, should be 2.5
median([5, 1, 3])     # 3, correct
```

Reporter wallet: {reporter}
"""
ACCEPTANCE = '''"""The acceptance test of the issue: median() of an even count."""

import sys
import unittest

sys.path.insert(0, "bot/sample")

from stats import median  # noqa: E402


class TestMedianEven(unittest.TestCase):
    def test_even_count(self):
        self.assertEqual(median([4, 1, 3, 2]), 2.5)

    def test_odd_count_still(self):
        self.assertEqual(median([5, 1, 3]), 3)


if __name__ == "__main__":
    unittest.main()
'''
MEAN_ISSUE_TITLE = "mean([]) crashes with ZeroDivisionError: it should raise a clear ValueError"
MEAN_ISSUE_BODY = """`bot/sample/stats.py`: `mean()` of an empty list crashes with a ZeroDivisionError, which says nothing about the cause.

```python
mean([])         # ZeroDivisionError, should raise ValueError
mean([1, 2, 3])  # 2.0, correct
```

Reporter wallet: {reporter}
"""
MEAN_BUG = "    return sum(xs) / len(xs)\n"
MEAN_FIXED = '    if not xs:\n        raise ValueError("mean of an empty list")\n    return sum(xs) / len(xs)\n'
MEAN_ACCEPTANCE = '''"""The acceptance test of the issue: mean() of an empty list."""

import sys
import unittest

sys.path.insert(0, "bot/sample")

from stats import mean  # noqa: E402


class TestMeanEmpty(unittest.TestCase):
    def test_empty_raises_a_clear_error(self):
        with self.assertRaises(ValueError):
            mean([])

    def test_a_list_still(self):
        self.assertEqual(mean([1, 2, 3]), 2)


if __name__ == "__main__":
    unittest.main()
'''
SEAT_ROLES = [f"oracle-{i}" for i in range(5)] + ["joiner-0"]
MERGE_STYLES = ("fast-forward-only", "rebase")  # main then IS the fix, so the head on-chain and the forge's agree


def say(line: str = "") -> None:
    print(line, flush=True)


class Forge:
    """The writes the flow needs, and git with the token in a header, never on a command line or in a URL."""

    def __init__(self, repo: str, base: str, user: str, token: str) -> None:
        self.repo, self.base, self.user, self.token = repo, base.rstrip("/"), user, token
        self.host = repo_for(repo, {"repos": {repo: {"host": "forgejo", "api": self.base}}})

    def api(self, method: str, path: str, body: dict | None = None):
        return self.host.client.api(method, f"/repos/{self.repo}{path}", body)

    def git(self, cwd: Path, *args: str) -> str:
        basic = base64.b64encode(f"{self.user}:{self.token}".encode()).decode()
        settings = [("credential.helper", ""), ("http.extraHeader", f"Authorization: Basic {basic}"),
                    ("user.name", "pof-first-bounty"), ("user.email", "first-bounty@example.invalid"),
                    ("init.defaultBranch", "main")]
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_COUNT": str(len(settings)),
               "LC_ALL": "C"}
        for i, (k, v) in enumerate(settings):
            env[f"GIT_CONFIG_KEY_{i}"], env[f"GIT_CONFIG_VALUE_{i}"] = k, v
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=300, env=env)
        if out.returncode:
            raise RuntimeError(f"git {args[0]} failed: {out.stderr.strip().replace(self.token, '***')[-300:]}")
        return out.stdout.strip()

    def main_sha(self) -> str:
        return self.api("GET", "/branches/main")["commit"]["id"]

    def bounty_label(self) -> int:
        """The maintainers' label for a bounty's issue: a real judge reads only an issue that carries it (#166)."""
        for label in self.api("GET", "/labels?limit=50") or []:
            if label["name"] == LABEL:
                return label["id"]
        return self.api("POST", "/labels", {"name": LABEL, "color": "#0e8a16"})["id"]

    def merge(self, pr: int) -> str:
        """Merges with a style that keeps the fix's commit as main's head; Forgejo may still be computing mergeability."""
        last = ""
        for attempt in range(30):
            for style in MERGE_STYLES:
                try:
                    self.api("POST", f"/pulls/{pr}/merge", {"Do": style})
                    return style
                except urllib.error.HTTPError as e:
                    last = f"HTTP {e.code} with {style}: {e.read().decode(errors='replace')[:200]}"
            time.sleep(5)
        raise RuntimeError(f"pull request #{pr} wouldn't merge (is main protected?): {last}")


class Run:
    def __init__(self, a) -> None:
        self.a = a
        self.record = load_record(2, a.record)
        token = os.environ["POFCTL_RPC_TOKEN"]
        self.rpc = Rpc(os.environ["POFCTL_RPC"], auth_headers(token, os.environ.get("POFCTL_RPC_AUTH") or "Basic"))
        self.race = Race(self.rpc, self.record)
        self.chain = v2.Chain(self.rpc, self.record["race"])
        self.basic = auth_headers(token, "Basic")
        self.forge = Forge(a.repo, a.forge, os.environ["FORGEJO_USER"], os.environ["FORGEJO_TOKEN"])
        self.work = Path(tempfile.mkdtemp(prefix="first-bounty-"))
        self.cfg = self.work / "pofctl.json"
        self.cfg.write_text(json.dumps({"repos": {a.repo: {"host": "forgejo", "api": a.forge}}}), encoding="utf-8")
        self.src = keys.source()
        self.names = {address(keys.key(r, self.src)).lower(): r for r in SEAT_ROLES}
        self.problems: list = []
        self.subs: dict = {}  # id -> {"fix", "solver", "pr", "judges", "deposit", "sha"}

    def ctl(self, *argv, role=None) -> dict:
        cmd = ["--record", self.a.record, "--config", str(self.cfg)] + (["--as", role] if role else []) + list(argv)
        return run(cmd)[0]

    # ---------- before anything is sent ----------

    def preflight(self) -> str:
        """Reads only. Returns the owner's address."""
        cid = self.race.chain_id()
        if cid not in DEVNET_CHAINS:
            raise SystemExit(f"first-bounty: chain {cid} isn't a devnet (rule 1)")
        seats = self.race.seats()
        active = [s for s in seats if s["active"]]
        if len(active) != len(seats):
            raise SystemExit(f"first-bounty: {len(active)} of {len(seats)} seats are active")
        owner = seats[self.a.owner_seat]["key"]
        name = self.names.get(owner.lower())
        if name:
            raise SystemExit(f"first-bounty: seat {self.a.owner_seat} is the role {name}, not the owner's validator")
        self.names[owner.lower()] = "OWNER"
        for addr, who in self.names.items():
            if int(self.rpc.call("eth_getBalance", [addr, "latest"]), 16) < 10**17:
                raise SystemExit(f"first-bounty: {who} ({addr}) has under 0.1 ETH for its reports and relays")
        req = urllib.request.Request(self.a.exchange.rstrip("/") + "/healthz", headers=self.basic)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (the configured relay)
                served = json.loads(r.read())["race"]
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            raise SystemExit(f"first-bounty: no answer from the exchange relay at {self.a.exchange}: {e}") from None
        if served.lower() != self.race.address.lower():
            raise SystemExit(f"first-bounty: the relay serves race {served}, not {self.race.address}")
        self.base = self.forge.main_sha()
        head = self.rpc.view(self.race.record["heads"], "head(bytes32)", ["(bytes32,bytes32,uint256,uint256,uint256,bytes32)"],
                             v2.b32(self.record["repo"]))[0][0]
        if v2.b32(head) != v2.commit_word(self.base):
            raise SystemExit(f"first-bounty: {self.a.repo}'s main is at {self.base[:12]}, its head on-chain at {head[:14]}: "
                             f"a merge would be refused as stale. Bring main back to the head on-chain.")
        say(f"chain {cid}, block {self.rpc.block()}; {len(seats)} seats active; seat {self.a.owner_seat} is the owner's "
            f"{owner}; relay {self.a.exchange} serves this race; {self.a.repo} main at {self.base[:12]} = the head on-chain")
        self.clone = self.work / "clone"
        self.clone.mkdir()
        g = self.forge.git
        g(self.clone, "init", "-q")
        g(self.clone, "fetch", "-q", "--depth", "1", "--", f"{self.a.forge.rstrip('/')}/{self.a.repo}.git", "main")
        g(self.clone, "checkout", "-q", "--detach", "FETCH_HEAD")
        for f in ("bot/sample/stats.py", "bot/fixes/bad_stats.py", "bot/fixes/good_stats.py"):
            if not (self.clone / f).exists():
                raise SystemExit(f"first-bounty: {self.a.repo} has no {f}: this script's issue is about that file")
        return owner

    # ---------- the steps ----------

    def fix_commit(self, fix_file: str, label: str) -> tuple:
        """A commit on main with the acceptance test and that stats.py, on its own branch: (sha, branch)."""
        g = self.forge.git
        g(self.clone, "checkout", "-q", "--detach", self.base)
        shutil.copy(self.clone / "bot" / "fixes" / fix_file, self.clone / "bot" / "sample" / "stats.py")
        (self.clone / "test_issue_median_even.py").write_text(ACCEPTANCE, encoding="utf-8")
        return self.commit_and_push("Fix the median of an even count", label)

    def mean_fix_commit(self, label: str) -> tuple:
        """A commit on main with mean()'s fix and its acceptance test, on its own branch: (sha, branch)."""
        self.forge.git(self.clone, "checkout", "-q", "--detach", self.base)
        stats = self.clone / "bot" / "sample" / "stats.py"
        stats.write_text(stats.read_text(encoding="utf-8").replace(MEAN_BUG, MEAN_FIXED, 1), encoding="utf-8")
        (self.clone / "test_issue_mean_empty.py").write_text(MEAN_ACCEPTANCE, encoding="utf-8")
        return self.commit_and_push("Raise a clear error for mean() of an empty list", label)

    def commit_and_push(self, message: str, label: str) -> tuple:
        g = self.forge.git
        g(self.clone, "add", "-A")
        tag = secrets.token_hex(4)
        g(self.clone, "commit", "-q", "-m", f"{message} ({label}, {tag})")
        sha, branch = g(self.clone, "rev-parse", "HEAD"), f"first-bounty/{label}-{tag}"
        g(self.clone, "push", "-q", f"{self.a.forge.rstrip('/')}/{self.a.repo}.git", f"HEAD:refs/heads/{branch}")
        return sha, branch

    def submit(self, solver: str, fix_file: str, label: str, title: str, make=None) -> int:
        sha, branch = make(label) if make else self.fix_commit(fix_file, label)
        r = self.ctl("solver", "submit", "--bounty", str(self.bounty), "--commit", sha, "--issue", str(self.gh_issue),
                     role=solver)
        pr = self.forge.api("POST", "/pulls", {"head": branch, "base": "main", "title": title, "body": r["prBody"]})["number"]
        names = [self.names.get(j.lower(), j) for j in r["judges"]]
        self.subs[r["submission"]] = {"fix": label, "solver": r["solver"], "pr": pr, "judges": names,
                                      "deposit": r["deposit"], "sha": sha}
        say(f"submission {r['submission']} ({label}) by {solver}: pull request #{pr}, deposit {r['deposit'] / C:,.6f}, "
            f"drawn {', '.join(names)}")
        return r["submission"]

    def wait_decided(self, s: int) -> str:
        started = time.monotonic()
        while time.monotonic() - started < self.a.check_timeout:
            outcome = self.race.submission(s)["outcome"]
            if outcome != "None":
                say(f"submission {s}: {outcome}, after {time.monotonic() - started:.0f} s")
                self.subs[s]["seconds"] = time.monotonic() - started
                return outcome
            time.sleep(3)
        raise RuntimeError(f"submission {s} had no result after {self.a.check_timeout} s: are the seats up? "
                           f"(scripts/devnet-seats.sh status)")

    def main(self) -> int:
        owner = self.preflight().lower()
        if self.a.preflight_only:
            return 0
        if self.a.until_owner_on_pass:
            return self.until_owner_on_pass(owner)
        say("\n== the bounty ==")
        self.mint()
        self.open_bounty(ISSUE_TITLE, ISSUE_BODY, "solver-a")

        drawn_owner = []
        for k in range(1, self.a.max_fails + 1):
            s = self.submit("solver-a", "bad_stats.py", f"wrong-{k}", "Fix median() of an even count (lower middle value)")
            if "OWNER" in self.subs[s]["judges"]:
                drawn_owner.append(s)
                say(f"  the owner's seat is drawn: its node is started by the watcher (a minute's poll, then the boot); "
                    f"this round waits for its seal, up to the seal window")
            outcome = self.wait_decided(s)
            if outcome != "Fail":
                self.problems.append(f"submission {s}: a failing fix came out {outcome}")
            self.forge.api("PATCH", f"/pulls/{self.subs[s]['pr']}", {"state": "closed"})
            if drawn_owner:
                break
        if not drawn_owner:
            self.problems.append(f"the owner's seat wasn't drawn in {self.a.max_fails} failing fixes (chance "
                                 f"{(4 / 7) ** self.a.max_fails:.1%}): run again, or raise --max-fails")
        if self.a.fails_only:
            return self.finish(owner, settled=False)

        self.ctl("solver", "attempt", "--bounty", str(self.bounty), role="solver-b")
        s = self.submit("solver-b", "good_stats.py", "right", "Fix median() of an even count (mean of the two middle values)")
        outcome = self.wait_decided(s)
        state = self.race.bounty(self.bounty)["state"]
        say(f"bounty {self.bounty}: {state}")
        if outcome != "Pass" or state != "Won":
            self.problems.append(f"the passing fix came out {outcome}, the bounty is {state}")
            return self.finish(owner, settled=False)

        if not self.merge_winner(s):
            return self.finish(owner, settled=False)

        if self.a.no_settle:
            return self.finish(owner, settled=False)
        days = 0
        for days in range(1, self.a.max_warp_days + 1):
            self.ctl("devnet", "warp", "--days", "1")
            try:
                # the bot settles, and closes the issue once paid, with a comment linking the payout (#151)
                if self.ctl("bot", "settle", "--bounty", str(self.bounty), "--repo", self.a.repo, "--issue",
                            str(self.gh_issue))["settled"]:
                    break
            except Reverted as e:
                if e.reason != "NotYet()":
                    raise
        else:
            self.problems.append(f"bounty {self.bounty} didn't settle in {self.a.max_warp_days} days")
        say(f"bounty {self.bounty}: {self.race.bounty(self.bounty)['state']}, after warping {days} days (the shared chain's clock)")
        self.ctl("funder", "claim", "--bounty", str(self.bounty))
        return self.finish(owner, settled=True)

    def mint(self) -> None:
        for role in ("reporter", "funder", "solver-a", "solver-b"):
            self.ctl("coin", "mint", "--to", role, "--amount", "100000")

    def open_bounty(self, title: str, body: str, solver: str) -> None:
        """An issue on the forge and its bounty on-chain, linked, funded and attempted by the solver."""
        reporter = self.ctl("reporter", "register", "--repo", "registry")
        self.gh_issue = self.forge.api("POST", "/issues", {"title": title, "labels": [self.forge.bounty_label()],
                                                           "body": body.format(reporter=reporter["reporter"])})["number"]
        self.bounty = self.ctl("oracle", "accept", "--issue", str(reporter["issue"]))["bounty"]
        self.ctl("bot", "link", "--repo", self.a.repo, "--issue", str(self.gh_issue), "--bounty", str(self.bounty))
        self.ctl("funder", "fund", "--bounty", str(self.bounty), "--amount", str(self.a.amount))
        self.ctl("solver", "attempt", "--bounty", str(self.bounty), role=solver)
        say(f"issue #{self.gh_issue} on {self.a.repo}, on-chain issue {reporter['issue']}: bounty {self.bounty} open, "
            f"funded with {self.a.amount:g}, attempted by {solver}")

    def until_owner_on_pass(self, owner: str) -> int:
        """A correct fix, on a new bounty each try, until the owner's seat is drawn on it: see the module's docstring."""
        stats = (self.clone / "bot" / "sample" / "stats.py").read_text(encoding="utf-8")
        if MEAN_BUG not in stats or MEAN_FIXED in stats:
            raise SystemExit(f"first-bounty: {self.a.repo}'s main no longer has the mean() bug this option's issue is about")
        if not (self.clone / "test_issue_median_even.py").exists():
            raise SystemExit("first-bounty: run the first bounty first: main still has the median bug, so every fix would fail")
        say("\n== a correct fix, until the owner's seat judges one ==")
        self.mint()
        for k in range(1, self.a.until_owner_on_pass + 1):
            self.open_bounty(MEAN_ISSUE_TITLE, MEAN_ISSUE_BODY, "solver-b")
            s = self.submit("solver-b", "", f"right-{k}", "Raise a clear error for mean() of an empty list",
                            make=self.mean_fix_commit)
            drawn = "OWNER" in self.subs[s]["judges"]
            if drawn:
                say("  the owner's seat is drawn on a correct fix: its node is started by the watcher (a minute's poll, then "
                    "the boot); this round waits for its seal, up to the seal window")
            outcome = self.wait_decided(s)
            state = self.race.bounty(self.bounty)["state"]
            if outcome != "Pass" or state != "Won":
                self.problems.append(f"the correct fix came out {outcome}, the bounty is {state}")
                return self.finish(owner, settled=False)
            if drawn:
                self.merge_winner(s)
                return self.finish(owner, settled=False)
            self.forge.api("PATCH", f"/pulls/{self.subs[s]['pr']}", {"state": "closed"})
            self.forge.api("PATCH", f"/issues/{self.gh_issue}", {"state": "closed"})
            say(f"  not drawn: pull request #{self.subs[s]['pr']} closed unmerged, the bug stays for the next try")
        self.problems.append(f"the owner's seat wasn't drawn in {self.a.until_owner_on_pass} tries (chance "
                             f"{(4 / 7) ** self.a.until_owner_on_pass:.1%}): run again")
        return self.finish(owner, settled=False)

    def merge_winner(self, s: int) -> bool:
        """Merge the winning fix on the forge and wait for the drawn judges' signed merge: False if it wasn't relayed."""
        style = self.forge.merge(self.subs[s]["pr"])
        say(f"pull request #{self.subs[s]['pr']} merged ({style}); waiting for the drawn judges' signed merge "
            f"(up to the round timeout if one of them is the owner's stopped node)")
        started = time.monotonic()
        while self.race.bounty(self.bounty)["state"] == "Won":
            if time.monotonic() - started > self.a.check_timeout:
                self.problems.append("the merge wasn't relayed in time")
                return False
            time.sleep(3)
        say(f"bounty {self.bounty}: {self.race.bounty(self.bounty)['state']}, after {time.monotonic() - started:.0f} s")
        if self.forge.main_sha() != self.subs[s]["sha"]:
            self.problems.append("main isn't the fix's commit after the merge: the next bounty's verdict would be stale")
        head = self.rpc.view(self.record["heads"], "head(bytes32)", ["(bytes32,bytes32,uint256,uint256,uint256,bytes32)"],
                             v2.b32(self.record["repo"]))[0][0]
        if v2.b32(head) != v2.commit_word(self.subs[s]["sha"]):
            self.problems.append("the head on-chain didn't move to the fix")
        else:
            say(f"the head on-chain moved to {self.subs[s]['sha'][:12]}, and {self.a.repo}'s main is there too")
        return True

    # ---------- the books ----------

    def finish(self, owner: str, settled: bool) -> int:
        say("\n== the fees ==")
        withdrawn = {}
        if settled or self.a.fails_only:
            for role in SEAT_ROLES + ["reporter", "funder", "solver-a", "solver-b"]:
                d = self.ctl("withdraw", "--role", role)
                if d["withdrawn"]:
                    withdrawn[role] = d["withdrawn"]
                    say(f"{role} withdrew {d['withdrawn'] / C:,.6f}")
            credit = self.race.owed(checksum(owner))
            if os.environ.get("POFCTL_KEY_ENGINEER"):
                d = self.ctl("validator", "withdraw", role="engineer")
                say(f"the owner's seat withdrew {d['withdrawn'] / C:,.6f}")
            elif credit:
                say(f"the owner's seat has {credit / C:,.6f} to withdraw: with POFCTL_KEY_ENGINEER set, "
                    f"scripts/pofctl --record {self.a.record} --as engineer validator withdraw")
        say("\n== the books ==")
        charged = self.chain.charged(self.record.get("block", 0))
        say(f"{'submission':>10} {'fix':>9} {'outcome':>8} {'seconds':>8} {'charged':>11}  judges (input/output tokens reported)")
        owner_judged = []
        for s, sub in self.subs.items():
            out = self.race.submission(s)["outcome"]
            reports = {r["judge"].lower(): r["usage"] for r in self.race.reports(s)}
            cells = []
            for name in sub["judges"]:
                addr = next(a for a, n in self.names.items() if n == name)
                u = reports.get(addr)
                cells.append(f"{name} ({u[1]}/{u[3]})" if u else f"{name} (no report)")
            if owner in reports:
                owner_judged.append(s)
            say(f"{s:>10} {sub['fix']:>9} {out:>8} {sub.get('seconds', 0):>8.0f} "
                f"{charged.get(s, (0, 0))[1] / C:>11,.6f}  {', '.join(cells)}")
        if owner_judged:
            say(f"\nthe owner's seat reported usage for submission(s) {', '.join(map(str, owner_judged))}. Its node's log says "
                f"which model answered: aws logs tail /pof-validator/node (the provider's own token counts are the row above).")
        elif any("OWNER" in s["judges"] for s in self.subs.values()):
            self.problems.append("the owner's seat was drawn, but it reported no usage: its node didn't take part (late, "
                                 "or not started: see the watcher's and the node's logs)")
        say("the other judges above are the role seats' nodes: the fake judge unless you set DEVNET_SEATS_JUDGE.")
        for p in self.problems:
            say(f"FAILED: {p}")
        say("result: the first bounty ran end to end" if not self.problems else f"result: {len(self.problems)} problem(s)")
        return 1 if self.problems else 0


def refused(e: urllib.error.HTTPError) -> str:
    """What to check when the repository host refuses the token. Never the token itself: this is only the status and URL."""
    return (f"first-bounty: the repository host refused the token (HTTP {e.code} at {e.filename}). Check that it's complete, with "
            "nothing extra picked up when pasting (a Forgejo token is 40 characters), that its scopes are write:repository "
            "and write:issue, and that FIRST_BOUNTY_USER is its user.")


def main() -> int:
    ap = argparse.ArgumentParser(description="One real bounty on a shared devnet (scripts/first-bounty.sh runs this).")
    ap.add_argument("--record", required=True)
    ap.add_argument("--repo", required=True, help="owner/name on the forge")
    ap.add_argument("--forge", required=True, help="the Forgejo's base URL")
    ap.add_argument("--exchange", required=True, help="the exchange relay's URL")
    ap.add_argument("--owner-seat", type=int, default=6)
    ap.add_argument("--amount", type=float, default=100, help="coins pledged")
    ap.add_argument("--max-fails", type=int, default=8, help="failing fixes to seal while the owner's seat isn't drawn")
    ap.add_argument("--fails-only", action="store_true", help="stop after the failing fixes: no passing fix, no merge")
    ap.add_argument("--no-settle", action="store_true", help="stop once merged, without warping the chain's clock")
    ap.add_argument("--max-warp-days", type=int, default=90)
    ap.add_argument("--check-timeout", type=float, default=1500, help="seconds one check or merge may take (the round "
                    "timeout, plus the reveals)")
    ap.add_argument("--until-owner-on-pass", type=int, default=0, metavar="N", help="at most N tries of a correct fix, on a "
                    "new bounty each, until the owner's seat judges one; no failing fixes, no warp")
    ap.add_argument("--preflight-only", action="store_true", help="the read-only checks, and nothing sent")
    a = ap.parse_args()
    r = Run(a)
    try:
        return r.main()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise SystemExit(refused(e)) from None
        raise
    finally:
        shutil.rmtree(r.work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
