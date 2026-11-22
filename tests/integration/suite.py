"""The integration suite (proof-of-fix#152): every role's interactions end to end, against a throwaway local devnet
with v2 deployed (7 seats, 2 vacant), a fake GitHub on the loopback, and the seats' real node processes (python3 -m
oracle run, the fake judge, each fix's tests in the Docker sandbox). Run it with scripts/integration.sh, which starts
and removes the devnet. Not part of the unit tests: it needs Docker. Never a public chain (rule 1).

Scenarios (#152's list), each on its own bounty:
1. the happy path: registered, accepted, funded, quoted, a fix sealed and its pull request opened, judged by the drawn
   validators' nodes, merged on GitHub, the merge signed, settled (Paid), the funder's leftover claimed; every drawn
   validator withdraws its fees at the end;
2. a failing fix: Fail, its deposit charged for the checks with the rest returned, and the bounty stays Open;
3. a race: two passing fixes sealed while it's open; the earliest commitment wins, the other is decided and refunded
   what the meter didn't charge, and a fix sealed after the win isn't checked and pays the evaluation fee (TooLate);
4. a silent validator: one drawn judge's node doesn't run; the other two decide, and the silent one reports no usage
   and is credited nothing for it (v2: no replacement from the shuffle and no silence slash; those are v3's, #140);
5. a challenge: after the merge, a challenge upheld by the quorum (pofctl oracle uphold-challenge) closes the award
   with no instalment earned and reopens the bounty;
6. joining: a new engineer's own key joins seat 6 (pofctl validator join, publish, 7 days, activate) and is drawn;
7. infrastructure faults: (a) the exchange service down, the nodes on http,folder falling back to the folder; (b) a
   drawn node killed after its usage report and restarted: it sits the round out with no second model call, the
   check completes and nothing is charged twice; (c) the owner's seat started on demand from cold is
   scripts/first-run-e2e.sh's (run it with --with-first-run);
8. with --radicle (#201, tests/integration/radicle.py): Radicle merges on a local isolated Radicle network, the seats'
   nodes as the delegates: the happy path, an outsider's push, fewer delegates than the threshold, and a mismatch
   between Heads and canonical main;
10. the untyped loop (#210), run last: `pofctl bot watch` as its own process with the bot-service key and --min-bounty,
   and the seats' nodes with their registration check on. The suite runs no `pofctl oracle accept`, `bot link`,
   `bot settle` or `bot close` in it, and every transaction from bot-service's address is settle, timeOut,
   mergeExpired or sunset. (a) the paid path: a labelled issue naming its registration is opened by the seats, linked
   by the bot (killed once right after its link, and restarted: nothing repeated), solved, merged, settled, commented
   once and closed; (b) the deadlines on one bounty: a sealed fix with no pull request times out, a passing fix wins and
   is never merged and expires, the bounty sunsets, and the bot settles it and closes its issue with one ending
   comment, each on its due day and not the day before; (c) a labelled issue with no lines gets one hint, still one
   after more passes, an edit and a restart.

After the scenarios (#151): the paid bounty's issue was closed by the bot when it settled it (`pofctl bot settle
--repo --issue`), with a comment linking the payout transaction, and a watcher's pass (`pofctl bot close`) closes every
other paid one and leaves the rest open; and `pofctl leaderboard`, computed from the events only, matches the same
bounties read from the contracts' views exactly (all time, then narrowed to the happy path's bounty), and a week's
board is within it.

It runs nightly on the test runner against this throwaway devnet: .forgejo/workflows/nightly.yml (#152's third box).

Not covered, and said so in the output: a nightly run against the AWS devnet, and the leaderboard metrics v2's events
don't carry (a validator's draws, agreement, reveal rate, fees per check and slashes: pofctl leaderboard says why).

The target (tests/integration/targets.py): this throwaway local devnet by default; `--target aws` runs the same roles
against the persistent AWS devnet, pof-sandbox and the live validator nodes, with the fake judge (tests/integration/aws.py:
scenarios 1, 2, 3 and 5, each on its own issue, balances asserted as deltas, everything it opens closed afterwards; 4, 6
and 7 are local-only and listed as skipped with the reason). The owner runs `scripts/integration.sh --target aws
--preflight` first; validator-kit/runbook.md, "The integration suite on the AWS devnet", has the steps.

At the end the books are checked exactly, as scripts/demo-e2e.sh does: each result's deposits = what the meter charged
+ what returned to the solver (read at the result's block); what the meter charged = what the validators were credited
in that block; every withdrawal pays the credit to the wallet; everything charged was withdrawn."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bot.forgejo import git  # noqa: E402
from fake_github import FakeGitHub  # noqa: E402
from oracle import abi, v2  # noqa: E402
from oracle.crypto import address  # noqa: E402
from oracle.rpc import Rpc  # noqa: E402
from pofctl import keys  # noqa: E402
from pofctl.cli import run  # noqa: E402
from pofctl.race import Race  # noqa: E402

from panel import PanelV2  # noqa: E402  (tests/integration/panel.py: who is drawn and what decides, in one place)

REPO = "demo/median"
C = 10**6
IDLE = 25  # seconds a node waits without progress before it exits
SCENARIOS = ("1", "2", "3", "4", "5", "6", "7", "10")
TYPED_BY_THE_BOT = {("oracle", "accept"), ("bot", "link"), ("bot", "settle"), ("bot", "close")}  # never in scenario 10


class Suite:
    def __init__(self, args):
        self.args = args
        self.work = Path(args.work).resolve()
        self.record = json.loads(Path(args.record).read_text(encoding="utf-8"))
        self.rpc = Rpc(args.rpc)
        self.chain = v2.Chain(self.rpc, self.record["race"])
        self.panel = PanelV2(self.chain)  # the draw and the quorum are read here only (#140, task 5.0)
        self.base = ["--rpc", args.rpc, "--record", args.record]
        self.problems: list = []
        self.passed: list = []
        self.submissions: dict = {}  # id -> {"solver", "deposit", "judges", "bounty"}
        self.seat_keys = {f"oracle-{i}": keys.derive(keys.MNEMONIC, keys.ROLES.index(f"oracle-{i}")) for i in range(5)}
        self.seat_keys["joiner-0"] = keys.derive(keys.MNEMONIC, keys.ROLES.index("joiner-0"))
        self.engineer = secrets.randbelow(2**255) + 1  # the engineer's own key: in this process's memory only
        self.seat_keys["engineer"] = self.engineer
        os.environ["POFCTL_KEY_ENGINEER"] = hex(self.engineer)
        self.rpc.call("anvil_setBalance", [address(self.engineer), hex(100 * 10**18)])
        self.names = {address(k).lower(): n for n, k in self.seat_keys.items()}
        self.start_block = self.rpc.block()
        self.issues: dict = {}  # bounty -> its GitHub issue
        self.late: dict = {}  # solver's address -> fixes sealed after the win (TooLate)
        self.withdrawn: dict = {}  # seat's address -> fees withdrawn
        self.paid_bounty = None  # scenario 1's
        self.calls: list = []  # every pofctl command the suite ran (scenario 10 checks none was the bot's or the quorum's)
        self.bot = None  # scenario 10's `pofctl bot watch` process

    # ---------- helpers ----------

    def ctl(self, *argv, as_role=None, show=True):
        self.calls.append(list(argv))
        data, lines = run(self.base + (["--as", as_role] if as_role else []) + list(argv))
        if show:
            print(f"$ pofctl {' '.join((['--as', as_role] if as_role else []) + list(argv))}")
            print("  " + "\n  ".join(lines), flush=True)
        return data

    def fail(self, scenario: str, what: str) -> None:
        self.problems.append(f"scenario {scenario}: {what}")

    def view_at(self, block: int, to: str, sig: str, returns: list, *a):
        raw = self.rpc.call("eth_call", [{"to": to, "data": "0x" + abi.call_data(sig, *a).hex()}, hex(block)])
        return abi.decode(returns, abi.hexdata(raw))

    def owed_at(self, block: int, who: str) -> int:
        return self.view_at(block, self.chain.race, "owed(address,address)", ["uint256"], who, self.chain.coin())[0]

    def state(self, b: int) -> str:
        return v2.STATES[self.chain.bounty(b)["state"]]

    def drawn_names(self, judges) -> str:
        return ", ".join(self.names.get(j.lower(), j[:10]) for j in judges)

    # ---------- the repository, the bounties and the fixes ----------

    def setup_repo(self, gh) -> None:
        self.gh = gh
        bare, self.clone = self.work / "git" / f"{REPO}.git", self.work / "git-work"
        bare.parent.mkdir(parents=True)
        self.clone.mkdir()
        self.bare = bare
        git(str(self.work), "init", "-q", "--bare", str(bare))
        git(str(self.clone), "init", "-q")
        for f in (ROOT / "bot" / "sample").iterdir():
            if f.is_file():
                shutil.copy(f, self.clone / f.name)
        git(str(self.clone), "add", "-A")
        git(str(self.clone), "commit", "-q", "-m", "the sample code")
        self.base_sha = git(str(self.clone), "rev-parse", "HEAD")
        git(str(self.clone), "push", "-q", str(bare), "HEAD:refs/heads/main")
        for role in ("reporter", "funder", "solver-a", "solver-b"):
            self.ctl("coin", "mint", "--to", role, "--amount", "100000", show=False)

    def commit_fix(self, fix: str, solver: str) -> str:
        git(str(self.clone), "checkout", "-q", "--detach", self.base_sha)
        shutil.copy(ROOT / "bot" / "fixes" / fix, self.clone / "stats.py")
        shutil.copy(ROOT / "bot" / "acceptance" / "test_issue_median_even.py", self.clone)
        git(str(self.clone), "add", "-A")
        git(str(self.clone), "commit", "-q", "-m", f"fix the median ({fix}, {solver}, {secrets.token_hex(4)})")
        sha = git(str(self.clone), "rev-parse", "HEAD")
        git(str(self.clone), "push", "-q", str(self.bare), f"HEAD:refs/heads/fix-{sha[:12]}")
        return sha

    def new_bounty(self, label: str) -> tuple:
        rep = self.ctl("reporter", "register", show=False)
        gh_issue = self.gh.add_issue(REPO, f"median() is wrong for an even count ({label})",
                                     f"`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\n"
                                     f"Reporter wallet: {rep['reporter']}\n", labels=["bounty"])
        bounty = self.ctl("oracle", "accept", "--issue", str(rep["issue"]), show=False)["bounty"]
        self.ctl("bot", "link", "--repo", REPO, "--issue", str(gh_issue), "--bounty", str(bounty), show=False)
        self.ctl("funder", "fund", "--bounty", str(bounty), "--amount", "100", show=False)
        self.issues[bounty] = gh_issue
        print(f"  bounty {bounty}: registered, accepted, linked to issue #{gh_issue}, funded 100")
        return bounty, gh_issue

    def submit(self, bounty: int, gh_issue: int, solver: str, fix: str) -> tuple:
        sha = self.commit_fix(fix, solver)
        r = self.ctl("solver", "submit", "--bounty", str(bounty), "--commit", sha, "--issue", str(gh_issue),
                     as_role=solver, show=False)
        if not r.get("submission"):
            return 0, None, r
        pr = self.gh.add_pull(REPO, f"Fix the median ({fix})", r["prBody"], sha, user=solver, base_sha=self.base_sha)
        judges = self.panel.drawn(r["submission"])
        print(f"  {solver} sealed {fix} ({sha[:12]}): submission {r['submission']}, deposit {r['deposit'] / C:,.6f}, "
              f"drawn {self.drawn_names(judges)}; pull request #{pr}")
        self.submissions[r["submission"]] = {"solver": address(keys.derive(keys.MNEMONIC, keys.ROLES.index(solver))),
                                             "deposit": r["deposit"], "judges": judges, "bounty": bounty}
        return r["submission"], pr, r

    # ---------- the nodes ----------

    def node_env(self, transport: str = "folder", check: bool = False) -> dict:
        env = {
            "ORACLE_RACE": self.record["race"], "ORACLE_KEYS": "env", "ORACLE_REPO": REPO,
            "ORACLE_REPOS": str(self.cfg), "GITHUB_TOKEN": self.gh.token, "ORACLE_SRC_ROOT": str(self.work / "src"),
            "ORACLE_GIT_URL": f"file://{self.work / 'git'}/{{repo}}.git",
            "ORACLE_EXCHANGE": str(self.work / "exchange"), "ORACLE_ROUND_TIMEOUT": "60", "ORACLE_POLL": "1",
            "ORACLE_MERGE_WEIGHT": "100", "PYTHONDONTWRITEBYTECODE": "1", "ORACLE_RPC": self.args.rpc,
        }
        if check:  # #210: the seats' registration check, with the fake judge (oracle/registration.py)
            env.update({"ORACLE_REGISTRATION_CHECK": "on", "ORACLE_REGISTER_WEIGHT": "120", "ORACLE_RELAY_GRACE": "5"})
        if transport == "http-down":  # a port nothing listens on: the relay is down; the folder is the fallback
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                env.update({"ORACLE_EXCHANGE_TRANSPORT": "http,folder",
                            "ORACLE_EXCHANGE_URL": f"http://127.0.0.1:{sock.getsockname()[1]}"})
        return env

    def start(self, name: str, env_extra: dict, idle: int = IDLE) -> tuple:
        k = self.seat_keys[name]
        env = {**os.environ, **env_extra, "ORACLE_PRIVATE_KEY": hex(k), "ORACLE_RECEIPTS": str(self.work / "receipts"
                                                                                                 / name)}
        log_path = self.work / f"node-{name}.log"
        log = open(log_path, "a", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "-m", "oracle", "run", "--until-idle", str(idle), "--from-block",
                              str(self.start_block)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        return name, log, p

    def run_nodes(self, label: str, scenario: str, skip=(), transport: str = "folder", restart: str = "",
                  restart_after: str = "usage reported", idle: int = IDLE, check: bool = False) -> None:
        """The seats' nodes, as separate processes, until each is idle. `skip`: seats whose node doesn't run.
        `restart`: a seat whose node is killed once its log shows `restart_after`, then started again. `check`: their
        registration check on (#210)."""
        env = self.node_env(transport, check)
        procs = [self.start(n, env, idle) for n in self.seat_keys if n not in skip]
        if restart:
            log_path = self.work / f"node-{restart}.log"
            deadline = time.time() + 600
            while time.time() < deadline and restart_after not in log_path.read_text(encoding="utf-8"):
                time.sleep(0.5)
            i = next(i for i, (n, _, _) in enumerate(procs) if n == restart)
            _, log, p = procs[i]
            p.kill()
            p.wait(timeout=30)
            log.write("\n--- killed by the suite, restarting ---\n")
            log.close()
            print(f"  ({restart}'s node killed after '{restart_after}', restarted)")
            procs[i] = self.start(restart, env, idle)
        for name, log, p in procs:
            code = p.wait(timeout=900)
            log.close()
            if code:
                self.fail(scenario, f"{label}: {name}'s node exited {code} (see {self.work}/node-{name}.log)")

    def node_log(self, name: str) -> str:
        return (self.work / f"node-{name}.log").read_text(encoding="utf-8")

    def merge_and_settle(self, scenario: str, bounty: int, pr: int, settle: bool = True,
                         issue: int | None = None) -> bool:
        """`issue`: the bot settles with --repo and --issue, and closes the issue once the bounty is paid (#151)."""
        self.gh.merge(REPO, pr)
        self.run_nodes(f"bounty {bounty}'s merge", scenario)
        if self.state(bounty) != "Merged":
            self.fail(scenario, f"bounty {bounty} is {self.state(bounty)} after its merge, not Merged")
            return False
        print(f"  pull request #{pr} merged; bounty {bounty}: Merged")
        if not settle:
            return True
        for _ in range(80):
            self.ctl("devnet", "warp", "--days", "1", show=False)
            close = ["--repo", REPO, "--issue", str(issue)] if issue is not None else []
            if self.ctl("bot", "settle", "--bounty", str(bounty), *close, show=False)["settled"]:
                break
        else:
            self.fail(scenario, f"bounty {bounty} never settled")
            return False
        print(f"  bounty {bounty}: {self.state(bounty)}")
        return True

    # ---------- the scenarios ----------

    def s6_join(self) -> None:
        print("\n== 6. joining: a new engineer's own key joins seat 6 ==", flush=True)
        req = self.ctl("validator", "join", "--seat", "6", as_role="engineer")
        self.ctl("validator", "publish", "--seat", "6", "--key", req["key"], "--nonce", req["nonce"], "--sig",
                 req["sig"])
        try:
            self.ctl("validator", "activate", "--seat", "6", show=False)
            self.fail("6", "a published key took its seat before the 7-day delay")
        except Exception as e:  # noqa: BLE001 (the refusal is the point)
            print(f"  (activating at once is refused: {e})")
        self.ctl("devnet", "warp", "--days", "7", show=False)
        self.ctl("validator", "activate", "--seat", "5", show=False)
        self.ctl("validator", "activate", "--seat", "6", show=False)
        if len(self.chain.keys()) != 7:
            self.fail("6", f"{len(self.chain.keys())} active seats, not 7")
        else:
            print("  7 active seats; whether the engineer is drawn is checked at the end")

    def s1_happy(self) -> None:
        print("\n== 1. the happy path ==", flush=True)
        bounty, issue = self.new_bounty("happy path")
        self.ctl("solver", "quote", "--bounty", str(bounty), as_role="solver-a", show=False)
        sub, pr, _ = self.submit(bounty, issue, "solver-a", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s check", "1")
        if self.state(bounty) != "Won":
            return self.fail("1", f"bounty {bounty} is {self.state(bounty)}, not Won")
        if not self.merge_and_settle("1", bounty, pr, issue=issue):
            return
        if self.state(bounty) != "Paid":
            return self.fail("1", f"bounty {bounty} is {self.state(bounty)} after settling, not Paid")
        self.paid_bounty = bounty
        if not self.issue_closed_on_payout("1", bounty, issue):
            return
        claimed = self.ctl("funder", "claim", "--bounty", str(bounty), show=False)
        print(f"  the funder claimed bounty {bounty}'s leftover: {json.dumps(claimed)[:120]}")
        self.passed.append("1")

    def s2_failing(self) -> None:
        print("\n== 2. a failing fix ==", flush=True)
        bounty, issue = self.new_bounty("failing fix")
        sub, _, _ = self.submit(bounty, issue, "solver-a", "bad_stats.py")
        self.run_nodes(f"bounty {bounty}'s check", "2")
        outcome = v2.OUTCOMES[self.chain.submission(sub)["outcome"]]
        if outcome != "Fail":
            return self.fail("2", f"submission {sub} is {outcome}, not Fail")
        if self.state(bounty) != "Open":
            return self.fail("2", f"bounty {bounty} is {self.state(bounty)} after a failing fix, not Open")
        print(f"  submission {sub}: Fail; bounty {bounty} stays Open (its deposit is checked in the books)")
        self.passed.append("2")

    def s3_race(self) -> None:
        print("\n== 3. a race: two passing fixes ==", flush=True)
        bounty, issue = self.new_bounty("race")
        first, pr_first, _ = self.submit(bounty, issue, "solver-a", "good_stats.py")
        second, _, _ = self.submit(bounty, issue, "solver-b", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s checks", "3")
        b = self.chain.bounty(bounty)
        if v2.STATES[b["state"]] != "Won" or b["winner"] != first:
            return self.fail("3", f"bounty {bounty}: {v2.STATES[b['state']]}, winner {b['winner']}, not Won by the "
                                  f"earliest commitment {first}")
        print(f"  the earliest commitment ({first}) won; submission {second}: "
              f"{v2.OUTCOMES[self.chain.submission(second)['outcome']]} (its deposit is checked in the books)")
        before = self.rpc.block()
        try:  # a commit after the win isn't a submission: pofctl may fail reading one back, which is the point
            self.submit(bounty, issue, "solver-b", "good_stats.py")
        except Exception as e:  # noqa: BLE001
            print(f"  (pofctl on the late fix: {type(e).__name__})")
        late = self.rpc.logs(self.chain.race, before + 1, ["0x" + v2.keccak256(b"TooLate(uint256,address)").hex(),
                                                           "0x" + bounty.to_bytes(32, "big").hex()])
        if len(late) != 1:
            return self.fail("3", f"a fix sealed after the win: {len(late)} TooLate events, not 1")
        solver_b = address(keys.derive(keys.MNEMONIC, keys.ROLES.index("solver-b")))
        self.late[solver_b] = self.late.get(solver_b, 0) + 1
        print("  a fix sealed after the win isn't checked: TooLate, and it pays the evaluation fee")
        self.merge_and_settle("3", bounty, pr_first, settle=False)
        self.passed.append("3")

    def s4_silent(self) -> None:
        print("\n== 4. a silent validator ==", flush=True)
        bounty, issue = self.new_bounty("silent validator")
        sub, pr, r = self.submit(bounty, issue, "solver-a", "good_stats.py")
        silent = next(self.names[j.lower()] for j in self.panel.drawn(sub) if self.names.get(j.lower()) != "engineer")
        print(f"  {silent}'s node doesn't run")
        # the others wait the round timeout (60 s) for the silent judge's seal before deciding without it: the nodes
        # must outlast it rather than stop as idle
        self.run_nodes(f"bounty {bounty}'s check without {silent}", "4", skip=(silent,), idle=150)
        if self.state(bounty) != "Won":
            return self.fail("4", f"bounty {bounty} is {self.state(bounty)} with {silent} silent, not Won")
        reporters = {self.names.get(x["judge"].lower()) for x in self.chain.reports(sub)}
        left = self.panel.reports(sub, silent=1)  # v2 doesn't replace a silent seat: one report fewer
        if silent in reporters or len(reporters) != left or left < self.panel.decides(sub):
            return self.fail("4", f"submission {sub}'s usage reports came from {sorted(reporters)}")
        self.submissions[sub]["expect_reports"] = left
        print(f"  the other {left} decided; {silent} reported no usage and is charged for nothing "
              f"(reports: {', '.join(sorted(reporters))})")
        self.merge_and_settle("4", bounty, pr, settle=False)
        self.passed.append("4")

    def s5_challenge(self) -> None:
        print("\n== 5. a challenge upheld after the merge ==", flush=True)
        bounty, issue = self.new_bounty("challenge")
        sub, pr, _ = self.submit(bounty, issue, "solver-b", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s check", "5")
        if self.state(bounty) != "Won":
            return self.fail("5", f"bounty {bounty} is {self.state(bounty)}, not Won")
        if not self.merge_and_settle("5", bounty, pr, settle=False):
            return
        epoch = self.chain.bounty(bounty)["epoch"]
        r = self.ctl("oracle", "uphold-challenge", "--bounty", str(bounty))
        if self.state(bounty) != "Open":
            return self.fail("5", f"bounty {bounty} is {self.state(bounty)} after an upheld challenge, not Open")
        if not r["award"]["closed"] or r["award"]["earned"] != 0:
            return self.fail("5", f"award {epoch}: closed {r['award']['closed']}, earned {r['award']['earned']}")
        print(f"  award {epoch} closed with nothing earned; bounty {bounty} reopened")
        self.passed.append("5")

    def s7_faults(self) -> None:
        print("\n== 7a. the exchange service down: http,folder falls back to the folder ==", flush=True)
        bounty, issue = self.new_bounty("exchange down")
        sub, pr, _ = self.submit(bounty, issue, "solver-a", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s check, the relay down", "7", transport="http-down")
        if self.state(bounty) != "Won":
            return self.fail("7", f"7a: bounty {bounty} is {self.state(bounty)} with the relay down, not Won")
        from oracle.transport import FolderExchange

        seals = {n.lower() for n in FolderExchange(self.work / "exchange", self.record["race"]).all(sub, "seal")}
        if seals != {j.lower() for j in self.submissions[sub]["judges"]}:
            return self.fail("7", f"7a: the drawn judges' seals for {sub} aren't in the folder")
        print(f"  submission {sub} decided through the folder")
        self.merge_and_settle("7", bounty, pr, settle=False)

        print("\n== 7b. a drawn node restarted mid-check ==", flush=True)
        bounty, issue = self.new_bounty("node restart")
        sub, pr, r = self.submit(bounty, issue, "solver-b", "good_stats.py")
        victim = self.names[self.panel.drawn(sub)[0].lower()]
        self.run_nodes(f"bounty {bounty}'s check, {victim} restarted", "7", restart=victim)
        if self.state(bounty) != "Won":
            return self.fail("7", f"7b: bounty {bounty} is {self.state(bounty)} after a restart, not Won")
        mine = [x for x in self.chain.reports(sub) if self.names.get(x["judge"].lower()) == victim]
        if len(mine) != 1:
            return self.fail("7", f"7b: {victim} has {len(mine)} usage reports for submission {sub}, not 1")
        if "sitting the round out" not in self.node_log(victim) and "earlier run" not in self.node_log(victim):
            print(f"  (note: {victim}'s restarted node didn't log sitting the round out; see its log)")
        print(f"  submission {sub} decided; {victim} reported once and wasn't charged twice")
        self.merge_and_settle("7", bounty, pr, settle=False)
        print("\n== 7c. the owner's seat started on demand from cold: scripts/first-run-e2e.sh ==")
        if self.args.with_first_run:
            print("  (runs after this suite: see scripts/integration.sh)")
        else:
            print("  (not run here; scripts/integration.sh --with-first-run runs it, about 15 minutes)")
        self.passed.append("7")

    def s8_radicle(self) -> None:
        if not self.args.radicle:
            return self.fail("8", "needs --radicle (scripts/integration.sh --radicle starts the Radicle network)")
        import radicle  # tests/integration/radicle.py (#201)

        radicle.run(self)

    # ---------- 10: the untyped loop (#210) ----------

    def bot_start(self) -> None:
        token = self.work / "bot-forge-token"
        token.write_text(self.gh.token + "\n", encoding="utf-8")
        token.chmod(0o600)
        env = {k: v for k, v in os.environ.items() if not k.startswith(("POFCTL_KEY_", "GITHUB_TOKEN", "ORACLE_"))}
        env.update({"DEVNET_KEYS": "insecure-local", "POF_BOT_RPC": self.args.rpc, "POF_BOT_RECORD": self.args.record,
                    "POF_BOT_REPO": REPO, "POF_BOT_FORGE_HOST": "github", "POF_BOT_FORGE_URL": self.gh.url,
                    "POF_BOT_FORGE_TOKEN_FILE": str(token), "POF_BOT_POLL_SECONDS": "1", "POF_BOT_HINT_GRACE": "2",
                    "PYTHONDONTWRITEBYTECODE": "1"})
        log = open(self.work / "bot.log", "a", encoding="utf-8")
        self.bot = (log, subprocess.Popen([sys.executable, "-m", "pofctl", "bot", "watch", "--min-bounty",
                                           str(self.min_bounty)], cwd=ROOT, env=env, stdout=log,
                                          stderr=subprocess.STDOUT))

    def bot_stop(self, note: str = "") -> None:
        if self.bot is None:
            return
        log, p = self.bot
        if p.poll() is not None:
            self.fail("10", f"the bot exited {p.returncode} on its own (see {self.work}/bot.log)")
        p.kill()
        p.wait(timeout=30)
        log.write(f"\n--- {note or 'stopped by the suite'} ---\n")
        log.close()
        self.bot = None

    def wait_until(self, what: str, done, timeout: float = 90) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if done():
                return True
            time.sleep(0.5)
        self.fail("10", f"{what}: not after {timeout:.0f} s (see {self.work}/bot.log)")
        return False

    def comments(self, issue: int) -> list:
        return list(self.gh.repos[REPO]["comments"].get(issue, []))

    def markers(self, issue: int, kind: str) -> list:
        from bot import logic

        read = {"link": logic.linked, "paid": logic.paid, "ended": logic.ended,
                "hint": lambda cs: True if logic.hinted(cs) else None}[kind]
        return [read([c]) for c in self.comments(issue) if read([c])]

    def claimed_issue(self, label: str) -> tuple:
        """The reporter registers and opens a labelled issue naming it (the two lines pofctl prints): no more."""
        rep = self.ctl("reporter", "register", show=False)
        issue = self.gh.add_issue(REPO, f"median() is wrong for an even count ({label})",
                                  "`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\n" + "\n".join(rep["lines"])
                                  + "\n", labels=["bounty"])
        print(f"  the reporter registered on-chain issue {rep['issue']} and opened issue #{issue} naming it")
        return rep["issue"], issue

    def opened_by_the_seats(self, onchain: int, issue: int) -> int:
        self.run_nodes(f"registration {onchain}'s check", "10", check=True)
        bounty = self.chain.issue(onchain)["bounty"]
        if not bounty:
            self.fail("10", f"registration {onchain} wasn't opened by the seats' check")
            return 0
        if not self.wait_until(f"issue #{issue} linked to bounty {bounty}", lambda: self.markers(issue, "link")):
            return 0
        if [m[1:] for m in self.markers(issue, "link")] != [(bounty, onchain)]:
            self.fail("10", f"issue #{issue}'s links: {self.markers(issue, 'link')}")
        print(f"  the seats' check opened bounty {bounty}; the bot linked it to issue #{issue}")
        return bounty

    def warp_to(self, day: int) -> None:
        now = self.ctl("status", show=False)["day"]
        if day > now:
            self.ctl("devnet", "warp", "--days", str(day - now), show=False)

    def tx_from_bot(self, tx: str) -> bool:
        return self.rpc.call("eth_getTransactionByHash", [tx])["from"].lower() == self.bot_address.lower()

    def last_log(self, event: bytes, *topics) -> dict | None:
        found = self.rpc.logs(self.chain.race, self.s10_block, ["0x" + v2.keccak256(event).hex(), *topics])
        return found[-1] if found else None

    def s10_untyped(self) -> None:
        print("\n== 10. the untyped loop: the seats' registration check and the bot as a service (#210) ==", flush=True)
        topic = "0x" + v2.keccak256(b"BountyOpened(uint256,uint256)").hex()
        self.min_bounty = len(self.rpc.logs(self.chain.race, 0, [topic])) + 1
        self.bot_address = address(keys.derive(keys.MNEMONIC, keys.ROLES.index("bot-service")))
        self.s10_block = self.rpc.block()
        mark = len(self.calls)
        self.bot_start()
        print(f"  pofctl bot watch started (bot-service {self.bot_address}, --min-bounty {self.min_bounty})")
        try:
            for part in (self.s10a_paid, self.s10b_deadlines, self.s10c_hint):
                try:
                    part()
                except Exception as e:  # noqa: BLE001 (one part's crash shouldn't hide the others)
                    self.fail("10", f"{part.__name__}: crashed: {type(e).__name__}: {e}")
        finally:
            self.bot_stop()
        typed = [c for c in self.calls[mark:] if tuple(c[:2]) in TYPED_BY_THE_BOT]
        if typed:
            self.fail("10", f"the suite ran the bot's or the stub quorum's commands: {typed}")
        allowed = {abi.selector(sig).hex() for sig in ("settle(uint256,address)", "timeOut(uint256)",
                                                       "mergeExpired(uint256)", "sunset(uint256)")}
        sent = []
        for n in range(self.s10_block, self.rpc.block() + 1):
            for tx in self.rpc.call("eth_getBlockByNumber", [hex(n), True])["transactions"]:
                if tx["from"].lower() == self.bot_address.lower():
                    sent.append(tx["input"][2:10])
        if not sent or set(sent) - allowed:
            self.fail("10", f"bot-service's transactions: {sent} (only settle, timeOut, mergeExpired, sunset)")
        else:
            print(f"  bot-service sent {len(sent)} transaction(s), each settle, timeOut, mergeExpired or sunset")
        log = (self.work / "bot.log").read_text(encoding="utf-8")
        if self.gh.token in log:
            self.fail("10", "the forge token is in the bot's output")
        if not any(p.startswith("scenario 10") for p in self.problems):
            self.passed.append("10")

    def s10a_paid(self) -> None:
        from bot import logic

        print("\n== 10a. the paid path, untyped ==", flush=True)
        onchain, issue = self.claimed_issue("untyped, paid")
        bounty = self.opened_by_the_seats(onchain, issue)
        if not bounty:
            return
        self.bot_stop("killed by the suite right after its link")
        self.bot_start()
        print("  (the bot killed right after its link, and restarted)")
        self.ctl("funder", "fund", "--bounty", str(bounty), "--amount", "100", show=False)
        self.issues[bounty] = issue
        sub, pr, _ = self.submit(bounty, issue, "solver-a", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s check", "10")
        if self.state(bounty) != "Won":
            return self.fail("10", f"10a: bounty {bounty} is {self.state(bounty)}, not Won")
        self.gh.merge(REPO, pr)
        self.run_nodes(f"bounty {bounty}'s merge", "10")
        if self.state(bounty) != "Merged":
            return self.fail("10", f"10a: bounty {bounty} is {self.state(bounty)} after its merge, not Merged")
        cfg = self.ctl("status", show=False)
        race = Race(self.rpc, self.record)
        c = race.config()
        aw = race.award(bounty, self.chain.bounty(bounty)["epoch"])
        due = logic.last_release_day(aw["windowEnd"], c["releaseEveryDays"], c["instalments"])
        self.warp_to(due - 1)
        time.sleep(4)
        if self.state(bounty) != "Merged":
            return self.fail("10", f"10a: bounty {bounty} is {self.state(bounty)} a day before its last instalment")
        self.warp_to(due)
        if not self.wait_until(f"bounty {bounty} settled by the bot", lambda: self.state(bounty) == "Paid"):
            return
        self.paid_bounty = self.paid_bounty or bounty
        if not self.wait_until(f"issue #{issue} closed", lambda: self.gh.repos[REPO]["items"][issue]["state"] == "closed"):
            return
        time.sleep(3)  # more passes: nothing more is written
        pay = race.payout(bounty)
        if not self.tx_from_bot(pay["tx"]):
            self.fail("10", f"10a: bounty {bounty}'s settle didn't come from bot-service")
        links, paid = self.markers(issue, "link"), self.markers(issue, "paid")
        if len(links) != 1 or [p[1:] for p in paid] != [(bounty, pay["tx"])] or len(self.comments(issue)) != 2:
            return self.fail("10", f"10a: issue #{issue}'s comments: {len(links)} link(s), payouts {paid}, "
                                   f"{len(self.comments(issue))} in all (expected one link and one payout)")
        print(f"  day {cfg['day']} -> {due}: the bot settled bounty {bounty} on its last release (not the day before), "
              f"commented the payout once and closed issue #{issue}; one link, nothing repeated after its restart")

    def s10b_deadlines(self) -> None:
        print("\n== 10b. the deadlines on one bounty: a timeout, an expired merge, a sunset ==", flush=True)
        onchain, issue = self.claimed_issue("untyped, deadlines")
        bounty = self.opened_by_the_seats(onchain, issue)
        if not bounty:
            return
        self.ctl("funder", "fund", "--bounty", str(bounty), "--amount", "100", show=False)
        race = Race(self.rpc, self.record)
        c = race.config()
        silent = self.ctl("solver", "submit", "--bounty", str(bounty), "--commit",
                          self.commit_fix("good_stats.py", "solver-a"), "--issue", str(issue), as_role="solver-a",
                          show=False)
        s1 = silent["submission"]
        solver_a = address(keys.derive(keys.MNEMONIC, keys.ROLES.index("solver-a")))
        self.submissions[s1] = {"solver": solver_a, "deposit": silent["deposit"], "judges": self.panel.drawn(s1),
                                "bounty": bounty, "timed_out": True, "expect_reports": 0}
        print(f"  solver-a sealed submission {s1} and never opens its pull request")
        s2, pr, _ = self.submit(bounty, issue, "solver-b", "good_stats.py")
        self.run_nodes(f"bounty {bounty}'s checks", "10")
        if v2.OUTCOMES[self.chain.submission(s2)["outcome"]] != "Pass" or self.state(bounty) != "Open":
            return self.fail("10", f"10b: submission {s2} is {v2.OUTCOMES[self.chain.submission(s2)['outcome']]}, "
                                   f"bounty {bounty} {self.state(bounty)} (expected Pass, and Open behind {s1})")
        due = self.chain.submission(s1)["day"] + c["resultDays"]
        self.warp_to(due - 1)
        time.sleep(4)
        if v2.OUTCOMES[self.chain.submission(s1)["outcome"]] != "None":
            return self.fail("10", f"10b: submission {s1} decided a day before its resultDays")
        self.warp_to(due)
        if not self.wait_until(f"submission {s1} timed out",
                               lambda: v2.OUTCOMES[self.chain.submission(s1)["outcome"]] == "TimedOut"):
            return
        decided = self.last_log(b"Decided(uint256,uint8)", "0x%064x" % s1)
        block = int(decided["blockNumber"], 16)
        back = self.owed_at(block, solver_a) - self.owed_at(block - 1, solver_a)
        if not self.tx_from_bot(decided["transactionHash"]) or back != silent["deposit"] - c["evaluationFee"]:
            return self.fail("10", f"10b: the timeout came from bot-service: {self.tx_from_bot(decided['transactionHash'])}"
                                   f"; solver-a got back {back}, expected {silent['deposit'] - c['evaluationFee']}")
        print(f"  day {due}: the bot timed out submission {s1}; solver-a got back its deposit less the evaluation fee")
        if self.state(bounty) != "Won":
            return self.fail("10", f"10b: bounty {bounty} is {self.state(bounty)} after the timeout, not Won by {s2}")
        merge_by = self.chain.bounty(bounty)["mergeBy"]
        self.warp_to(merge_by)
        time.sleep(4)
        if self.state(bounty) != "Won":
            return self.fail("10", f"10b: bounty {bounty} expired on its mergeBy day, not after it")
        self.warp_to(merge_by + 1)
        if not self.wait_until(f"bounty {bounty}'s merge expired", lambda: self.state(bounty) == "Open"):
            return
        reopened = self.last_log(b"StateChanged(uint256,uint8)", "0x%064x" % bounty)
        if not self.tx_from_bot(reopened["transactionHash"]):
            return self.fail("10", "10b: mergeExpired didn't come from bot-service")
        print(f"  day {merge_by + 1}: the bot expired the unmerged win; bounty {bounty} is Open again")
        sunset = self.chain.bounty(bounty)["idleSince"] + c["idleDays"]
        self.warp_to(sunset - 1)
        time.sleep(4)
        if self.state(bounty) != "Open":
            return self.fail("10", f"10b: bounty {bounty} is {self.state(bounty)} a day before its sunset")
        self.warp_to(sunset)
        if not self.wait_until(f"bounty {bounty} sunset", lambda: self.state(bounty) == "Unsolved"):
            return
        ended = self.last_log(b"StateChanged(uint256,uint8)", "0x%064x" % bounty)
        if not self.tx_from_bot(ended["transactionHash"]):
            return self.fail("10", "10b: sunset didn't come from bot-service")
        settled = lambda: self.rpc.view(self.chain.race, "settled(uint256,address)", ["bool"], bounty,  # noqa: E731
                                        self.chain.coin())[0]
        if not self.wait_until(f"bounty {bounty} settled", settled):
            return
        if not self.wait_until(f"issue #{issue} closed", lambda: self.gh.repos[REPO]["items"][issue]["state"] == "closed"):
            return
        time.sleep(3)
        said = self.markers(issue, "ended")
        if [m[1:] for m in said] != [(bounty, "Unsolved", ended["transactionHash"])]:
            return self.fail("10", f"10b: issue #{issue}'s ending comments: {said}")
        print(f"  day {sunset}: the bot sunset bounty {bounty} (Unsolved), settled it and closed issue #{issue} with "
              f"one ending comment naming the sunset's transaction")

    def s10c_hint(self) -> None:
        print("\n== 10c. the hint, once ==", flush=True)
        issue = self.gh.add_issue(REPO, "median() is slow (untyped, no lines)", "It takes a while on a big list.\n",
                                  labels=["bounty"])
        if not self.wait_until(f"issue #{issue}'s hint", lambda: self.markers(issue, "hint")):
            return
        time.sleep(3)
        self.gh.repos[REPO]["items"][issue]["body"] += "\nStill slow. Registration: soon\n"  # an edit, still invalid
        self.bot_stop("restarted by the suite after an edit")
        self.bot_start()
        time.sleep(6)
        hints = self.markers(issue, "hint")
        if len(hints) != 1 or len(self.comments(issue)) != 1:
            return self.fail("10", f"10c: issue #{issue} has {len(hints)} hints, {len(self.comments(issue))} comments")
        print(f"  issue #{issue} got one hint; still one after more passes, an edit and a restart")

    # ---------- #151: the issue closed on payout, and the leaderboard ----------

    def issue_closed_on_payout(self, scenario: str, bounty: int, issue: int) -> bool:
        """The bot's settle closed the issue, with one comment naming the payout transaction (StateChanged Paid)."""
        from bot import logic

        item = self.gh.repos[REPO]["items"][issue]
        comments = self.gh.repos[REPO]["comments"].get(issue, [])
        pay = Race(self.rpc, self.record).payout(bounty)
        said = [logic.paid([c]) for c in comments if logic.paid([c])]
        if item["state"] != "closed" or pay is None:
            self.fail(scenario, f"issue #{issue} is {item['state']} after bounty {bounty} was paid ({pay})")
            return False
        if [x[1:] for x in said] != [(bounty, pay["tx"])]:
            self.fail(scenario, f"issue #{issue}'s payout comments: {said}, expected one naming {pay['tx']}")
            return False
        print(f"  issue #{issue} closed by the bot on payout, its comment linking transaction {pay['tx'][:18]}…")
        return True

    def close_watcher(self) -> None:
        """A watcher's pass over every open bounty issue: it closes the paid ones (scenario 8's, settled without the
        issue), leaves the others open, and doesn't comment twice on scenario 1's."""
        from bot import logic

        print("\n== the bot's watcher pass: pofctl bot close (#151) ==", flush=True)
        results = self.ctl("bot", "close", "--repo", REPO)
        race = Race(self.rpc, self.record)
        for bounty, issue in sorted(self.issues.items()):
            paid = race.bounty(bounty)["state"] == "Paid"
            state = self.gh.repos[REPO]["items"][issue]["state"]
            if state != ("closed" if paid else "open"):
                self.fail("close", f"issue #{issue} is {state}, bounty {bounty} is {race.bounty(bounty)['state']}")
            notes = [c for c in self.gh.repos[REPO]["comments"].get(issue, []) if logic.paid([c])]
            if len(notes) != int(paid):
                self.fail("close", f"issue #{issue} has {len(notes)} payout comments, bounty {bounty} paid: {paid}")
        if not isinstance(results, list):
            self.fail("close", f"bot close returned {results!r}")

    def check_leaderboard(self) -> None:
        """pofctl leaderboard (events only) against the same bounties read from the views (targets.board_expected):
        all time over every bounty (the devnet is this run's), then the happy path's bounty alone; a week's board is
        within the all-time one."""
        from targets import board_expected, check_board

        print("\n== the leaderboard (#151): from the events, checked against the views ==", flush=True)
        race = Race(self.rpc, self.record)
        topic = "0x" + v2.keccak256(b"BountyOpened(uint256,uint256)").hex()
        bounties = sorted(int(x["topics"][1], 16) for x in self.rpc.logs(self.chain.race, 0, [topic]))
        funder = [address(keys.derive(keys.MNEMONIC, keys.ROLES.index("funder")))]
        board = self.ctl("leaderboard")
        problems = check_board("all time", board, board_expected(race, bounties, funder, self.late, self.withdrawn))
        if self.paid_bounty is not None:
            b = self.paid_bounty
            one = self.ctl("leaderboard", "--bounties", str(b), show=False)
            problems += check_board(f"bounty {b}", one, board_expected(race, [b], funder))
        week = self.ctl("leaderboard", "--period", "week", show=False)
        from pofctl.leaderboard import METRICS

        for role, metrics in METRICS.items():
            all_time = {r["address"]: r for r in board[role]}
            for r in week[role]:
                over = [m for m in metrics if r[m] > all_time.get(r["address"], {}).get(m, 0)]
                if over:
                    problems.append(f"week: {role} {r['address']}: {over} above all time")
        for p in problems:
            self.fail("leaderboard", p)
        if not problems:
            print(f"  the board matches the views for {len(bounties)} bounties (and bounty {self.paid_bounty} alone); "
                  f"the week's is within it")

    def engineer_drawn(self) -> int:
        return sum(any(j.lower() == address(self.engineer).lower() for j in s["judges"])
                   for s in self.submissions.values())

    def until_engineer_drawn(self, most: int = 4) -> None:
        """Scenario 6's last step: the joined seat judges. Draws are random, so bounties are added until it's drawn."""
        for k in range(most):
            if self.engineer_drawn():
                return
            print(f"\n== 6. (the engineer's seat not drawn yet: one more bounty, {k + 1} of {most}) ==", flush=True)
            bounty, issue = self.new_bounty(f"joining {k + 1}")
            sub, pr, _ = self.submit(bounty, issue, "solver-a", "good_stats.py")
            self.run_nodes(f"bounty {bounty}'s check", "6")
            if self.state(bounty) == "Won":
                self.merge_and_settle("6", bounty, pr, settle=False)

    # ---------- the end: withdrawals and the books ----------

    def evaluation_fee(self) -> int:
        return Race(self.rpc, self.record).config()["evaluationFee"]

    def withdraw_and_check(self) -> None:
        print("\n== the validators withdraw their fees (scenario 1's end) ==", flush=True)
        withdrawn = {}
        env = self.node_env()
        for name, k in self.seat_keys.items():
            who = address(k)
            owed = self.chain.owed(who)
            wallet = self.rpc.view(self.chain.coin(), "balanceOf(address)", ["uint256"], who)[0]
            if not owed:
                continue
            if name == "engineer":
                self.ctl("validator", "withdraw", as_role="engineer", show=False)
            else:
                subprocess.run([sys.executable, "-m", "oracle", "withdraw-fees"], cwd=ROOT,
                               env={**os.environ, **env, "ORACLE_PRIVATE_KEY": hex(k)}, capture_output=True,
                               text=True, timeout=120)
            after = self.rpc.view(self.chain.coin(), "balanceOf(address)", ["uint256"], who)[0]
            withdrawn[name] = after - wallet
            self.withdrawn[who] = after - wallet
            if after - wallet != owed or self.chain.owed(who):
                self.fail("1", f"{name}: withdrew {after - wallet}, its credit was {owed}")
        charged = self.chain.charged(self.start_block)
        by_block: dict = {}
        for e in self.rpc.logs(self.chain.race, self.start_block, ["0x" + v2.keccak256(b"Decided(uint256,uint8)").hex()]):
            by_block.setdefault(int(e["blockNumber"], 16), []).append(int(e["topics"][1], 16))
        total = 0
        for block, subs in sorted(by_block.items()):
            for solver in {self.submissions[s]["solver"] for s in subs if s in self.submissions}:
                mine = [s for s in subs if s in self.submissions and self.submissions[s]["solver"] == solver]
                deposit = sum(self.submissions[s]["deposit"] for s in mine)
                got = sum(charged.get(s, (0, 0))[1] for s in mine)
                got += sum(min(self.evaluation_fee(), self.submissions[s]["deposit"]) for s in mine
                           if self.submissions[s].get("timed_out"))  # #210: a timeout pays the evaluation fee
                back = self.owed_at(block, solver) - self.owed_at(block - 1, solver)
                if deposit != got + back:
                    self.fail("books", f"block {block}: deposits {deposit} != charged {got} + refunded {back}")
                for s in mine:
                    n, _ = charged.get(s, (0, 0))
                    want = self.submissions[s].get("expect_reports", self.panel.reports(s))
                    if len(self.chain.reports(s)) != want or n != want:
                        self.fail("books", f"submission {s}: {len(self.chain.reports(s))} reports, {n} judges charged, "
                                           f"expected {want}")
            in_block = sum(charged.get(s, (0, 0))[1] for s in subs)
            total += in_block
            credited = sum(self.owed_at(block, address(k)) - self.owed_at(block - 1, address(k))
                           for k in self.seat_keys.values())
            if credited != in_block:
                self.fail("books", f"block {block}: the meter charged {in_block}, the validators were credited "
                                   f"{credited}")
        if sum(withdrawn.values()) != total:
            self.fail("books", f"withdrawn {sum(withdrawn.values())} != charged {total}")
        drawn = self.engineer_drawn()
        if not drawn:
            self.fail("6", "the engineer's seat wasn't drawn in any scenario")
        elif "6" not in self.passed and not any(p.startswith("scenario 6") for p in self.problems):
            self.passed.append("6")
        print(f"charged by the meter: {total / C:,.6f} for {len(charged)} checks; withdrawn: "
              f"{sum(withdrawn.values()) / C:,.6f}; the engineer was drawn for {drawn} submission(s)")

    def main(self) -> int:
        only = set(self.args.only.split(",")) if self.args.only else set(SCENARIOS)
        only |= {"8"} if self.args.radicle and not self.args.only else set()
        with FakeGitHub() as gh:
            self.cfg = self.work / "pofctl.json"
            self.cfg.write_text(json.dumps({"repos": {REPO: {"host": "github", "api": gh.url}}}), encoding="utf-8")
            self.base += ["--config", str(self.cfg)]
            os.environ["GITHUB_TOKEN"] = gh.token
            self.setup_repo(gh)
            self.s6_join()  # first: the other scenarios draw from 7 seats, and one of them should draw the engineer
            for key, fn in (("1", self.s1_happy), ("2", self.s2_failing), ("3", self.s3_race), ("4", self.s4_silent),
                            ("5", self.s5_challenge), ("7", self.s7_faults), ("8", self.s8_radicle),
                            ("10", self.s10_untyped)):
                if key in only:
                    try:
                        fn()
                    except Exception as e:  # noqa: BLE001 (one scenario's crash shouldn't hide the others)
                        self.fail(key, f"crashed: {type(e).__name__}: {e}")
            self.until_engineer_drawn()
            self.withdraw_and_check()
            for key, fn in (("close", self.close_watcher), ("leaderboard", self.check_leaderboard)):
                try:
                    fn()
                except Exception as e:  # noqa: BLE001
                    self.fail(key, f"crashed: {type(e).__name__}: {e}")
        from targets import NOT_COVERED

        print("\nnot covered here: " + "; ".join(NOT_COVERED) + ". The AWS devnet: --target aws"
              + ("" if self.args.radicle else "; Radicle merges (scripts/integration.sh --radicle, #201)"))
        for p in self.problems:
            print(f"FAILED: {p}")
        print(f"scenarios passed: {', '.join(sorted(set(self.passed))) or 'none'}")
        print("result: the integration suite passed" if not self.problems else f"result: {len(self.problems)} failed")
        return 1 if self.problems else 0


def main() -> int:
    from targets import Refused, split_target  # tests/integration/targets.py: --target local (this) or aws

    try:
        target, argv = split_target(sys.argv[1:])
    except Refused as e:
        print(f"integration: {e}", file=sys.stderr)
        return 2
    if target == "aws":
        from aws import main as aws_main

        return aws_main(argv)
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--only", help="comma-separated scenarios (1-8 and 10, 8 with --radicle); 6 always runs first, since "
                                   "the others use 7 seats; 10 always runs last")
    ap.add_argument("--with-first-run", action="store_true", help="7c: scripts/integration.sh runs "
                    "scripts/first-run-e2e.sh after this suite")
    ap.add_argument("--radicle", action="store_true", help="scenario 8, Radicle merges (#201): scripts/integration.sh "
                                                           "--radicle starts the network first")
    return Suite(ap.parse_args(argv)).main()


if __name__ == "__main__":
    sys.exit(main())
