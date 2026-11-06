"""The local bounty loop end to end (proof-of-fix#56 task 3.3, design D8 phase 4). Run it with
scripts/bounty-loop.sh, which starts the throwaway Forgejo and anvil containers and tears them down after.

The story: a maintainer opts an issue in with the `bounty` label; the bot links it to a bounty, which the reporter's
wallet registers and the oracle quorum's signed check opens; a funder pledges; one solver's fix fails the checks and
the bounty stays open; a second solver's passes, the protocol merges its pull request (solved = merged), the signed
merge starts its award, and after the instalments the bounty settles: the winner, the reporter's finder's fee and the
funder's refund, checked to the micro-coin. Its close is recorded with the token, and once the period ends anyone
claims its tokens (to the solver and the reporter) and the founder's share, checked to the micro-token. Every key is one of anvil's public test keys; nothing leaves the machine.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import logic
from .chain import Chain
from .forgejo import Forgejo, git

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
LOOP = "script/Loop.s.sol:LoopScript"
OWNER, REPO = "maintainer", "sample"
C = 10**6
MAX = str(2**256 - 1)

# anvil's default test keys (the well-known "test test ... junk" mnemonic): for a throwaway chain only. On the private
# devnet (`bounty-loop.sh --devnet`, #93) each role's key comes from OpenBao instead, in LOOP_KEY_<ROLE> (e.g.
# LOOP_KEY_SOLVER_A); see keys().
KEYS = {
    "bot": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "reporter": "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "funder": "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    "solver-a": "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6",
    "solver-b": "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a",
    "infrastructure": "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba",
    "insurance": "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
    "founder": "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
}
CONFIG = logic.Config(registration_fee=2 * C, issue_stake=5 * C, attempt_fee=C // 2, check_deposit=6_600_000,
                      start_bps=5_000, rise_bps_per_day=1_000, finder_fee_bps=1_765)  # as Loop.s.sol deploys it
ORACLE_FEE, SIGNERS, PLEDGE = 300_000, 2, 100 * C
TOKENS = logic.TokenRules(first_emission=10_000 * C, decay_bps=100, founder_bps=100, founder_periods=208,
                          reporter_bps=1_500, inflation_pct=300)  # pof's TOKENS, as Loop.s.sol deploys them
REGISTERED, AT_MERGE = 120 * C, 100 * C  # the oracles' two importance estimates; the smaller counts
RELEASE_EVERY, INSTALMENTS = 7, 4  # as Loop.s.sol deploys the Race
BOUNTY = "bounty(uint256)((uint256,uint8,uint256,bool,uint256,uint256,uint256,uint256,uint256,uint256,uint256,uint256," \
         "uint256,bool))"


def keys() -> dict[str, str]:
    """Each role's key: the environment's (the devnet's, from OpenBao) where set, else anvil's test key."""
    return {role: os.environ.get(f"LOOP_KEY_{role.upper().replace('-', '_')}", key) for role, key in KEYS.items()}


def say(step: str, detail: str = "") -> None:
    print(f"[loop] {step}" + (f": {detail}" if detail else ""), flush=True)


class Loop:
    def __init__(self) -> None:
        self.chain = Chain(os.environ["LOOP_CHAIN"], os.environ.get("LOOP_CHAIN_ID", "31337"))
        self.keys = keys()
        self.forgejo_container = os.environ["LOOP_FORGEJO"]
        self.base = os.environ["LOOP_FORGEJO_URL"]
        self.python_image = os.environ["LOOP_PYTHON_IMAGE"]
        self.work = Path(tempfile.mkdtemp(prefix="loop-", dir=ROOT / ".loop"))
        self.users: dict[str, Forgejo] = {}
        self.nonces = 0

    # ---------- setup ----------

    def wait(self) -> None:
        for _ in range(120):
            if self.chain.ready() and self._forgejo_up():
                return
            time.sleep(1)
        raise RuntimeError("the local chain or Forgejo didn't come up")

    def _forgejo_up(self) -> bool:
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self.base}/api/v1/version", timeout=3):  # noqa: S310 (loopback)
                return True
        except OSError:
            return False

    def user(self, name: str, admin: bool = False) -> Forgejo:
        password = secrets.token_urlsafe(18)
        cmd = ["docker", "exec", "-u", "git", self.forgejo_container, "forgejo", "admin", "user"]
        subprocess.run([*cmd, "create", "--username", name, "--password", password, "--email",
                        f"{name}@example.invalid", "--must-change-password=false", *(["--admin"] if admin else [])],
                       check=True, capture_output=True, timeout=60)
        token = subprocess.run([*cmd, "generate-access-token", "--username", name, "--token-name", "loop", "--scopes",
                                "all", "--raw"], check=True, capture_output=True, text=True, timeout=60).stdout.strip()
        self.users[name] = Forgejo(self.base, name, password, token)
        return self.users[name]

    def deploy(self) -> None:
        self.addr = {who: self.chain.address(key) for who, key in self.keys.items()}
        holders = "[" + ",".join(self.addr[w] for w in ("reporter", "funder", "solver-a", "solver-b")) + "]"
        out = self.chain.script(self.keys["bot"], LOOP, "deploy(address,address,address,address[])",
                                self.addr["infrastructure"], self.addr["insurance"], self.addr["founder"], holders)
        self.coin, self.race, self.quoter, self.token = out["COIN"], out["RACE"], out["QUOTER"], out["TOKEN"]
        self.oracles = [out[f"ORACLE{i}"] for i in range(SIGNERS)]
        for who in ("reporter", "funder", "solver-a", "solver-b"):
            self.chain.send(self.keys[who], self.coin, "approve(address,uint256)", self.race, MAX)
        say("deployed", f"Race {self.race}, its Token {self.token}, Quoter {self.quoter}, mUSD {self.coin}; "
                        f"oracle quorum 2 of 3")

    def repo(self) -> None:
        m = self.users[OWNER]
        m.api("POST", "/user/repos", {"name": REPO, "private": True, "default_branch": "main"})
        src = self.work / "seed"
        shutil.copytree(HERE / "sample", src)
        git(str(src), "init", "-q")
        git(str(src), "add", ".")
        git(str(src), "commit", "-qm", "A tiny library")
        git(str(src), "push", "-q", m.remote(OWNER, REPO), "main")
        for name, permission in (("reporter", "read"), ("solver-a", "write"), ("solver-b", "write")):
            m.api("PUT", f"/repos/{OWNER}/{REPO}/collaborators/{name}", {"permission": permission})
        self.label = m.api("POST", f"/repos/{OWNER}/{REPO}/labels",
                           {"name": logic.LABEL, "color": "#0e8a16", "description": "Opted in to a bounty"})["id"]
        say("repository", f"{OWNER}/{REPO} (private, on the local Forgejo), label `{logic.LABEL}`")

    # ---------- the bot ----------

    def nonce(self) -> str:
        self.nonces += 1
        return "0x" + secrets.token_hex(28) + f"{self.nonces:08x}"

    def bot_link_issues(self) -> None:
        """The bot's pass over labelled issues: each one with no bounty yet gets one."""
        bot = self.users[OWNER]
        for issue in bot.api("GET", f"/repos/{OWNER}/{REPO}/issues?state=open&type=issues&labels={logic.LABEL}"):
            n = issue["number"]
            comments = bot.api("GET", f"/repos/{OWNER}/{REPO}/issues/{n}/comments")
            if not logic.needs_bounty(issue, comments):
                continue
            reporter = logic.wallet(issue["body"], "Reporter")
            key = next(k for who, k in self.keys.items() if self.addr[who].lower() == (reporter or "").lower())
            receipt = self.chain.send(key, self.race, "register(address)", self.coin)  # the reporter's wallet pays
            onchain = self._topic(receipt, "Registered(uint256,address)", 1)
            bounty = int(self.chain.script(self.keys["bot"], LOOP, "accept(address,uint256,uint256,bytes32)", self.race,
                                           str(onchain), str(REGISTERED), self.nonce())["BOUNTY"])
            bot.api("POST", f"/repos/{OWNER}/{REPO}/issues/{n}/comments",
                    {"body": logic.bounty_comment(self.race, bounty, onchain)})
            say("bot", f"issue #{n} labelled: registered on-chain as issue {onchain}, checked, bounty #{bounty} open")
            self.issue, self.bounty = n, bounty

    def bot_settle_due(self) -> int | None:
        """The bot's daily pass over merged bounties: one whose last instalment is released today is settled at once,
        so its close lands in that period. Returns the day it settled, if it did."""
        fields = logic.tuple_fields(self.chain.call(self.race, BOUNTY, str(self.bounty))[0])
        state, epoch = int(fields[1]), int(fields[10])
        award = logic.tuple_fields(self.chain.call(self.race, "awards(uint256,uint256)(address,bytes32,uint256,bool,"
                                                   "uint256)", str(self.bounty), str(epoch)))
        today = self.chain.uint(self.race, "day()(uint256)")
        if not logic.due_to_settle(state, today, int(award[2]), RELEASE_EVERY, INSTALMENTS):
            return None
        receipt = self.chain.send(self.keys["bot"], self.race, "settle(uint256,address)", str(self.bounty), self.coin)
        self.period = self._topic(receipt, "Recorded(uint256,uint256,uint256,uint256)", 1)
        return today

    def _topic(self, receipt: dict, event: str, index: int) -> int:
        topic0 = self.chain.keccak(event)
        for log in receipt["logs"]:
            if log["topics"][0] == topic0:
                return int(log["topics"][index], 16)
        raise RuntimeError(f"no {event} in the receipt")

    # ---------- a solver ----------

    def solve(self, who: str, branch: str, fix_file: str) -> int:
        f = self.users[who]
        quote = self.chain.quote(self.race, self.bounty, self.coin)
        say(f"{who} reads the quote", "\n" + quote)
        self.chain.send(self.keys[who], self.race, "attempt(uint256,address)", str(self.bounty), self.coin)
        clone = self.work / who
        git(str(self.work), "clone", "-q", f.remote(OWNER, REPO), str(clone))
        git(str(clone), "checkout", "-qb", branch)
        shutil.copy(HERE / "fixes" / fix_file, clone / "stats.py")
        git(str(clone), "commit", "-qam", "Fix the median of an even count", name=who, email=f"{who}@example.invalid")
        git(str(clone), "push", "-q", "origin", branch)
        fix = self.chain.keccak(git(str(clone), "rev-parse", "HEAD^{tree}"))  # the fix is its tree: same code, same fix
        salt = "0x" + secrets.token_hex(32)
        sealed = self.chain.commitment(fix, salt, self.addr[who])
        receipt = self.chain.send(self.keys[who], self.race, "commit(uint256,bytes32,address)", str(self.bounty), sealed,
                                  self.coin)
        submission = self._topic(receipt, "Committed(uint256,uint256,address)", 2)
        pr = f.api("POST", f"/repos/{OWNER}/{REPO}/pulls", {
            "head": branch, "base": "main", "title": "Fix the median of an even count",
            "body": logic.pr_body(self.issue, self.bounty, submission, salt, self.addr[who])})["number"]
        say(f"{who}", f"attempted, sealed submission {submission} on-chain, opened pull request #{pr}")
        return pr

    # ---------- the oracle stand-in ----------

    def check(self, pr: int) -> bool:
        """The oracle quorum's check, stood in for by a deterministic one: the claim must match the sealed submission,
        and the repository's tests plus the issue's acceptance test (kept from solvers) must pass in a sandbox with no
        network. The quorum signs the result; the bot relays it."""
        m = self.users[OWNER]
        body = m.api("GET", f"/repos/{OWNER}/{REPO}/pulls/{pr}")["body"]
        c = logic.claim(body)
        if c is None or c.bounty != self.bounty:
            raise RuntimeError(f"pull request #{pr} doesn't claim this bounty")
        head = self.work / f"check-{pr}"
        git(str(self.work), "clone", "-q", m.remote(OWNER, REPO), str(head))
        git(str(head), "fetch", "-q", "origin", f"refs/pull/{pr}/head")
        git(str(head), "checkout", "-q", "FETCH_HEAD")
        fix = self.chain.keccak(git(str(head), "rev-parse", "HEAD^{tree}"))
        sealed = self.chain.call(self.race, "submission(uint256)((uint256,uint256,address,bytes32,address,uint256,"
                                 "uint8,bytes32,bool))", str(c.submission))[0]
        if self.chain.commitment(fix, c.salt, c.solver).lower() != logic.tuple_fields(sealed)[3].lower():
            raise RuntimeError(f"pull request #{pr} doesn't match its sealed submission")
        shutil.rmtree(head / ".git")
        shutil.copy(HERE / "acceptance" / "test_issue_median_even.py", head)
        run = subprocess.run(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                              "--pids-limit", "64", "--memory", "256m", "-e", "PYTHONDONTWRITEBYTECODE=1",
                              "-v", f"{head}:/src:ro", "-w", "/src", self.python_image, "python", "-m", "unittest",
                              "-q"], capture_output=True, text=True, timeout=300)
        passed = run.returncode == 0
        state = int(self.chain.script(self.keys["bot"], LOOP, "result(address,uint256,uint8,bytes32,bytes32)", self.race,
                                      str(c.submission), "1" if passed else "2", fix, self.nonce())["STATE"])
        say("oracles", f"pull request #{pr}: tests {'passed' if passed else 'failed'}; signed result relayed "
                       f"(bounty state {state})")
        return passed

    # ---------- the run ----------

    def run(self) -> int:
        self.wait()
        for name in ("maintainer", "reporter", "solver-a", "solver-b"):
            self.user(name, admin=name == OWNER)
        self.deploy()
        self.repo()
        m, r = self.users[OWNER], self.users["reporter"]
        issue = r.api("POST", f"/repos/{OWNER}/{REPO}/issues", {
            "title": "median() is wrong for an even count",
            "body": f"`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\nReporter wallet: {self.addr['reporter']}\n"})
        say("reporter", f"opened issue #{issue['number']}")
        self.bot_link_issues()  # not labelled yet: nothing to do
        assert not hasattr(self, "bounty"), "the bot linked an issue nobody opted in"
        m.api("POST", f"/repos/{OWNER}/{REPO}/issues/{issue['number']}/labels", {"labels": [self.label]})
        say("maintainer", f"labelled issue #{issue['number']} `{logic.LABEL}`")
        self.bot_link_issues()
        self.chain.send(self.keys["funder"], self.race, "pledge(uint256,address,uint256)", str(self.bounty), self.coin,
                        str(PLEDGE))
        say("funder", f"pledged {PLEDGE / C:.2f} mUSD to bounty #{self.bounty}")

        self.chain.warp(2)  # the share of the cap rises 10 points a day until the first attempt locks it
        bad = self.solve("solver-a", "fix-a", "bad_stats.py")
        assert not self.check(bad)
        m.api("POST", f"/repos/{OWNER}/{REPO}/issues/{bad}/comments",
              {"body": "The checks failed: the bounty stays open. The deposit, less the checks' fees, is back."})
        m.api("PATCH", f"/repos/{OWNER}/{REPO}/pulls/{bad}", {"state": "closed"})

        self.chain.warp(1)
        good = self.solve("solver-b", "fix-b", "good_stats.py")
        assert self.check(good)
        m.api("POST", f"/repos/{OWNER}/{REPO}/pulls/{good}/merge", {"Do": "merge"})  # solved = merged (the opt-in)
        state = int(self.chain.script(self.keys["bot"], LOOP, "merged(address,uint256,uint256,bytes32)", self.race,
                                      str(self.bounty), str(AT_MERGE), self.nonce())["STATE"])
        say("protocol", f"merged pull request #{good}; signed merge relayed (bounty state {state}), award started")

        fields = logic.tuple_fields(self.chain.call(self.race, BOUNTY, str(self.bounty))[0])
        window_end = int(logic.tuple_fields(self.chain.call(
            self.race, "awards(uint256,uint256)(address,bytes32,uint256,bool,uint256)", str(self.bounty),
            fields[10]))[2])
        due = logic.last_release_day(window_end, RELEASE_EVERY, INSTALMENTS)
        settled_on = None
        while settled_on is None:  # the bot runs once a day; nobody has to remember to settle
            self.chain.warp(1)
            settled_on = self.bot_settle_due()
        assert settled_on == due, f"settled on day {settled_on}, its last instalment was released on day {due}"
        say("bot", f"the last instalment was released on day {due}: settled that day")
        self.chain.send(self.keys["funder"], self.race, "claimRefund(uint256,address)", str(self.bounty), self.coin)
        for who in ("reporter", "funder", "solver-a", "solver-b"):
            self.chain.send(self.keys[who], self.race, "withdraw(address,address)", self.coin, self.addr[who])
        say("settled", "instalments to the winner, the finder's fee and registration refund to the reporter, the "
                       f"leftover to the funder; credits withdrawn; the close recorded in token period {self.period}")
        self.chain.warp(14)  # the period ends, then its 7-day grace window: anyone can claim its tokens
        self.chain.send(self.keys["bot"], self.token, "claim(uint256,uint256)", str(self.period), "0")
        self.chain.send(self.keys["bot"], self.token, "claimFounder(uint256)", str(self.period))
        say("tokens", f"period {self.period} claimed: the close's tokens to its solver and reporter, the founder's "
                      f"share to the founder")
        m.api("POST", f"/repos/{OWNER}/{REPO}/issues/{issue['number']}/comments", {
            "body": f"Bounty #{self.bounty} on `{self.race}` is paid: pull request #{good} won it."})
        if m.api("GET", f"/repos/{OWNER}/{REPO}/issues/{issue['number']}")["state"] != "closed":
            m.api("PATCH", f"/repos/{OWNER}/{REPO}/issues/{issue['number']}", {"state": "closed"})
        return self.verify(issue["number"], bad, good)

    def verify(self, issue: int, bad: int, good: int) -> int:
        m = self.users[OWNER]
        start = 1_000 * C
        lock = logic.lock_bps(CONFIG, 2)
        want = logic.loop_payouts(CONFIG, start, PLEDGE, lock, ORACLE_FEE, SIGNERS, failed=1)
        accounts = {"reporter": "reporter", "funder": "funder", "winner": "solver-b", "failed0": "solver-a",
                    "infrastructure": "infrastructure"}
        got = {role: self._holds(self.addr[who]) for role, who in accounts.items()}
        got["oracle"] = self._holds(self.oracles[0])
        problems = [f"{role}: {got[role]} != {want[role]}" for role in want if got[role] != want[role]]
        if self._holds(self.oracles[1]) != want["oracle"]:
            problems.append("the second signing oracle's fees")
        if self._state() != logic.PAID:
            problems.append(f"bounty #{self.bounty} isn't paid (state {self._state()})")
        held = sum(got.values()) + self._holds(self.oracles[1])
        if held != 4 * start:
            problems.append(f"the coins don't add up: {held} != {4 * start}")
        pulls = {n: m.api("GET", f"/repos/{OWNER}/{REPO}/pulls/{n}") for n in (bad, good)}
        if not pulls[good]["merged"] or pulls[bad]["merged"] or pulls[bad]["state"] != "closed":
            problems.append("pull requests: the winner must be merged and the failed fix closed unmerged")
        closed = m.api("GET", f"/repos/{OWNER}/{REPO}/issues/{issue}")["state"] == "closed"
        comments = m.api("GET", f"/repos/{OWNER}/{REPO}/issues/{issue}/comments")
        if not closed or logic.linked(comments) != (self.race, self.bounty, 1):
            problems.append("the issue must be closed with the bounty linked")
        say("balances (wallet + credit, micro-mUSD)",
            ", ".join(f"{role} {got[role]}" for role in ("reporter", "funder", "winner", "failed0", "infrastructure",
                                                         "oracle")))
        say("price", f"{logic.price(CONFIG, PLEDGE, lock)} at a locked share of {lock / 100:.0f} %")
        tokens = logic.lone_close_tokens(TOKENS, self.period, REGISTERED, AT_MERGE)
        held = {"solver": self._tokens(self.addr["solver-b"]), "reporter": self._tokens(self.addr["reporter"]),
                "founder": self._tokens(self.addr["founder"]), "supply": self.chain.uint(self.token,
                                                                                          "totalSupply()(uint256)")}
        problems += [f"tokens, {k}: {held[k]} != {tokens[k]}" for k in tokens if held[k] != tokens[k]]
        if self._tokens(self.addr["solver-a"]):
            problems.append("the failed solver holds tokens")
        say("tokens (micro-POF)", ", ".join(f"{k} {held[k]}" for k in ("solver", "reporter", "founder", "supply")))
        for p in problems:
            say("FAILED", p)
        say("result", "the loop passed end to end" if not problems else f"{len(problems)} check(s) failed")
        return 1 if problems else 0

    def _state(self) -> int:
        """The bounty's state (Race.State): the second field of `bounty(id)`."""
        return int(logic.tuple_fields(self.chain.call(self.race, BOUNTY, str(self.bounty))[0])[1])

    def _tokens(self, address: str) -> int:
        return self.chain.uint(self.token, "balanceOf(address)(uint256)", address)

    def _holds(self, address: str) -> int:
        return (self.chain.uint(self.coin, "balanceOf(address)(uint256)", address)
                + self.chain.uint(self.race, "owed(address,address)(uint256)", address, self.coin))


def main() -> int:
    (ROOT / ".loop").mkdir(exist_ok=True)
    loop = Loop()
    try:
        return loop.run()
    finally:
        shutil.rmtree(loop.work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
