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
   between Heads and canonical main.

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

REPO = "demo/median"
C = 10**6
IDLE = 25  # seconds a node waits without progress before it exits
SCENARIOS = ("1", "2", "3", "4", "5", "6", "7")


class Suite:
    def __init__(self, args):
        self.args = args
        self.work = Path(args.work).resolve()
        self.record = json.loads(Path(args.record).read_text(encoding="utf-8"))
        self.rpc = Rpc(args.rpc)
        self.chain = v2.Chain(self.rpc, self.record["race"])
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

    # ---------- helpers ----------

    def ctl(self, *argv, as_role=None, show=True):
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
        print(f"  {solver} sealed {fix} ({sha[:12]}): submission {r['submission']}, deposit {r['deposit'] / C:,.6f}, "
              f"drawn {self.drawn_names(r['judges'])}; pull request #{pr}")
        self.submissions[r["submission"]] = {"solver": address(keys.derive(keys.MNEMONIC, keys.ROLES.index(solver))),
                                             "deposit": r["deposit"], "judges": r["judges"], "bounty": bounty}
        return r["submission"], pr, r

    # ---------- the nodes ----------

    def node_env(self, transport: str = "folder") -> dict:
        env = {
            "ORACLE_RACE": self.record["race"], "ORACLE_KEYS": "env", "ORACLE_REPO": REPO,
            "ORACLE_REPOS": str(self.cfg), "GITHUB_TOKEN": self.gh.token, "ORACLE_SRC_ROOT": str(self.work / "src"),
            "ORACLE_GIT_URL": f"file://{self.work / 'git'}/{{repo}}.git",
            "ORACLE_EXCHANGE": str(self.work / "exchange"), "ORACLE_ROUND_TIMEOUT": "60", "ORACLE_POLL": "1",
            "ORACLE_MERGE_WEIGHT": "100", "PYTHONDONTWRITEBYTECODE": "1", "ORACLE_RPC": self.args.rpc,
        }
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
                  restart_after: str = "usage reported", idle: int = IDLE) -> None:
        """The seats' nodes, as separate processes, until each is idle. `skip`: seats whose node doesn't run.
        `restart`: a seat whose node is killed once its log shows `restart_after`, then started again."""
        env = self.node_env(transport)
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
        silent = next(self.names[j.lower()] for j in r["judges"] if self.names.get(j.lower()) != "engineer")
        print(f"  {silent}'s node doesn't run")
        # the others wait the round timeout (60 s) for the silent judge's seal before deciding without it: the nodes
        # must outlast it rather than stop as idle
        self.run_nodes(f"bounty {bounty}'s check without {silent}", "4", skip=(silent,), idle=150)
        if self.state(bounty) != "Won":
            return self.fail("4", f"bounty {bounty} is {self.state(bounty)} with {silent} silent, not Won")
        reporters = {self.names.get(x["judge"].lower()) for x in self.chain.reports(sub)}
        if silent in reporters or len(reporters) != 2:
            return self.fail("4", f"submission {sub}'s usage reports came from {sorted(reporters)}")
        self.submissions[sub]["expect_reports"] = 2
        print(f"  the other two decided; {silent} reported no usage and is charged for nothing "
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
        victim = self.names[r["judges"][0].lower()]
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
                back = self.owed_at(block, solver) - self.owed_at(block - 1, solver)
                if deposit != got + back:
                    self.fail("books", f"block {block}: deposits {deposit} != charged {got} + refunded {back}")
                for s in mine:
                    n, _ = charged.get(s, (0, 0))
                    want = self.submissions[s].get("expect_reports", 3)
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
                            ("5", self.s5_challenge), ("7", self.s7_faults), ("8", self.s8_radicle)):
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
    ap.add_argument("--only", help="comma-separated scenarios (1-8, 8 with --radicle); 6 always runs first, since the others use 7 seats")
    ap.add_argument("--with-first-run", action="store_true", help="7c: scripts/integration.sh runs "
                    "scripts/first-run-e2e.sh after this suite")
    ap.add_argument("--radicle", action="store_true", help="scenario 8, Radicle merges (#201): scripts/integration.sh "
                                                           "--radicle starts the network first")
    return Suite(ap.parse_args(argv)).main()


if __name__ == "__main__":
    sys.exit(main())
