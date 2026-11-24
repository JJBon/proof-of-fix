"""pofctl on v3 and Radicle end to end (proof-of-fix#251 task 4.4): the reporter, the funder and three solvers play
through pofctl alone against the real v3 contracts on a throwaway local chain. Run it with
`scripts/pofctl-e2e.sh --version 3`, which starts anvil (chain 31337, the pinned Foundry image), deploys v3 for this
run's repository (contracts/script/NodeV3Local.s.sol, with its RID and a real genesis commit) and removes everything
when it ends. Not part of the unit tests: it needs Docker. No model call, no public chain, no network beyond this
machine.

The validators are the devnet suite's real `NodeV3` objects with the fake judge (tests/integration/suite_v3.py's Net):
a genesis validator and three candidates who qualify by their shadow verdicts, so panels of 3 judge and verdicts
become final in their windows (the chain's clock is moved). The Radicle node is a stand-in (tests/fake_rad.py): a real
bare git repository as its storage, the delegate's signed `main` and the canonical ref in it, `rad issue open` and
`rad issue comment` on issue objects in Radicle 1.10.3's shape. Once qualified, the validators read the registrations'
claims from the Radicle issues on that node (task 4.3, `radicle_v3.RadicleIssues`), as pofctl commented them. They
read a fix's claim from the fake host, so the run gives the host the patch description pofctl printed (the format the
node reads); the node's Radicle fix source (task 4.2) reads the same text from a patch, tested with a stand-in node in
tests/test_radicle_v3.py, and task 4.6 runs the story on real Radicle nodes.

The story, through pofctl (`--keystore` for solver-a, devnet keys for the others):
1. `status` before anything: a new identity's cap is REP_BASE ($50), no open claim, a fix would post FeesV3's
   maxDeposit and get the rest back, 0 active solvers; the keystore's key appears nowhere in the output;
2. the reporter opens four Radicle issues and registers them (`issue register --rad-issue … --comment`): the first
   approves the coin with a message, the next ones don't; the claim lands as a comment on each Radicle issue, the
   validators read it there and check the reporter's signature (a copy of a claim on a junk issue with a lower id
   is ignored), and the checks pass, their receipts naming the issue and the claim's hash;
3. `pledge` is refused below 3 active solvers, with the count, and nothing is sent (no approval, no transaction);
4. three solvers each fix one bounty unfunded: `submit --patch` seals a real commit on Heads.head and prints the
   patch's description; the panel passes it; `claim`; `merge` refused before finality, then moves Heads at finality;
   `verify-head` refuses until the delegate pushes `main`, then agrees; `checkout` gives the judged commit;
5. three solvers are active: `pledge` goes through, showing the count and approving the coin; solver-a's funded fix
   is an open claim in `status` until it merges; after finality its deposit's rest is credit it withdraws."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _p in (ROOT, ROOT / "tests", ROOT / "tests" / "integration"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import suite_v3 as SV  # noqa: E402
from bot import logic  # noqa: E402
from e2e_node_v3 import ETH_100, keys_for, simulator  # noqa: E402
from fake_rad import DELEGATE  # noqa: E402
from oracle import crypto, v2, v3  # noqa: E402
from oracle import radicle as R  # noqa: E402
from oracle import radicle_v3 as RV  # noqa: E402
from oracle.rpc import Rpc  # noqa: E402
from pofctl import keys as keysrc  # noqa: E402
from pofctl import keystore  # noqa: E402
from pofctl.cli import Fail, run  # noqa: E402

RID = "rad:z4PofctrE2eV3TestRepo"  # a well-formed RID for this run's stand-in node (base58: no 0, O, I or l)
C = 10**6
SOLVER_NS = {"solver-a": "z6MksoLverA", "solver-b": "z6MksoLverB", "solver-c": "z6MksoLverC"}
PASSWORD = "pofctl e2e keystore password"


def secret(name: str) -> int:
    """A throwaway test key from a public string: anyone can derive it (the keystore's, and solver-c's)."""
    return int.from_bytes(crypto.keccak256(f"pof pofctl v3 e2e {name}".encode()), "big") % crypto.N or 1


def git(*args, cwd=None, git_dir=None) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "pofctl e2e", "GIT_AUTHOR_EMAIL": "e2e@example.invalid",
           "GIT_COMMITTER_NAME": "pofctl e2e", "GIT_COMMITTER_EMAIL": "e2e@example.invalid"}
    pre = ["git"] + (["--git-dir", str(git_dir)] if git_dir else [])
    return subprocess.run(pre + list(args), cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


def check(cond: bool, what: str) -> None:
    if not cond:
        raise AssertionError(what)
    print(f"ok: {what}", flush=True)


# ---------- prepare: the repository, the stand-in node, the deployment's inputs ----------

def prepare(work: Path, rpc: Rpc) -> int:
    """Creates the repository's working copy and the stand-in node's storage, and prints what the deployment needs:
    the deployer's and the genesis validator's throwaway keys, the genesis attestation, the RID and the genesis head.
    Read by scripts/pofctl-e2e.sh, never shown."""
    repo, store = work / "repo", work / "radhome" / "storage" / RID[4:]
    repo.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=repo)
    (repo / "README.md").write_text("pofctl v3 end to end (proof-of-fix#251)\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "genesis", cwd=repo)
    head = git("rev-parse", "HEAD", cwd=repo)
    git("init", "-q", "--bare", str(store))
    git("push", "-q", str(store), f"{head}:refs/namespaces/{DELEGATE}/refs/heads/main", cwd=repo)
    git("update-ref", "refs/heads/main", head, git_dir=store)
    rpc.call("anvil_setBalance", [crypto.address(secret("deployer")), ETH_100])
    genesis = keys_for(simulator(), "genesis")
    quote = genesis.quote(crypto.keccak256(b"genesis"))
    print(f"DEPLOYER=0x{secret('deployer'):064x}")
    print(f"GENESIS=0x{genesis.account_secret():064x}")
    print(f"ATTESTATION=0x{crypto.keccak256(bytes.fromhex(quote.quote)).hex()}")
    print(f"FAMILIES={','.join(SV.FAMILIES)}")
    print(f"RID={RID}")
    print(f"GENESIS_HEAD=0x{head}{'0' * 24}")
    return 0


# ---------- the run ----------

class Story:
    def __init__(self, rpc: Rpc, record_path: str, work: Path, verbose: bool) -> None:
        self.rpc, self.work = rpc, work
        self.record = json.loads(Path(record_path).read_text(encoding="utf-8"))
        self.base = ["--rpc", rpc.url, "--record", record_path]
        self.repo, self.store = work / "repo", work / "radhome" / "storage" / RID[4:]
        self.out: list = []  # every line and JSON pofctl printed: the keystore's key must be in none of it
        self.last: list = []  # the last command's lines
        bin_dir = work / "bin"
        bin_dir.mkdir(exist_ok=True)
        (bin_dir / "rad").write_text(f"#!/bin/sh\nexec {sys.executable} {ROOT / 'tests' / 'fake_rad.py'} \"$@\"\n",
                                     encoding="utf-8")
        (bin_dir / "rad").chmod(0o755)
        os.environ["PATH"] = f"{bin_dir}:{os.environ['PATH']}"
        os.environ["RAD_HOME"] = str(work / "radhome")
        os.environ["DEVNET_KEYS"] = "insecure-local"
        os.environ["POFCTL_KEY_SOLVER_C"] = f"0x{secret('solver-c'):064x}"
        self.ks_secret = secret("keystore solver-a")
        self.ks = work / "solver-a.keystore.json"
        self.ks.write_text(json.dumps(keystore.encrypt(self.ks_secret, PASSWORD, n=1 << 12)), encoding="utf-8")
        pw = work / "solver-a.password"
        pw.write_text(PASSWORD + "\n", encoding="utf-8")
        os.environ[keystore.PASSWORD_FILE] = str(pw)
        self.n = SV.Net(rpc, self.record, work / "net", verbose)
        self.c = self.n.chain

    def ctl(self, *argv, as_role: str | None = None, keystore_: bool = False, expect_fail: str | None = None):
        extra = (["--as", as_role] if as_role else []) + (["--keystore", str(self.ks)] if keystore_ else [])
        shown = " ".join(extra + list(argv))
        try:
            data, lines = run(self.base + extra + ["--json"] + list(argv))
        except Fail as e:
            self.out.append(str(e))
            if expect_fail is None:
                raise
            check(expect_fail in str(e), f"$ pofctl {shown}\n    refused: {e}")
            return None
        if expect_fail is not None:
            raise AssertionError(f"pofctl {shown} wasn't refused ({expect_fail!r} expected)")
        self.out += lines + [json.dumps(data, default=str)]
        self.last = lines
        print(f"$ pofctl --v3 {shown}\n  " + "\n  ".join(lines), flush=True)
        return data

    def addr(self, role: str) -> str:
        if role == "solver-a":
            return crypto.address(self.ks_secret)
        if role == "solver-c":
            return crypto.address(secret("solver-c"))
        return crypto.address(keysrc.key(role, "insecure-local"))

    # ----- the validators -----

    def validators(self) -> None:
        n, c = self.n, self.c
        print("\n== the validators: a genesis validator and three who qualify (panels of 3) ==", flush=True)
        genesis = n.make_node("genesis", SV.FAMILIES[0], keeper=True)
        self.rpc.call("anvil_setBalance", [genesis.address, ETH_100])
        n.nodes["genesis"] = genesis
        self.genesis = genesis
        for _ in range(3):
            n.join_next()
        n.start = max(self.rpc.block() - 20, 0)
        made = n.grow(["v1", "v2", "v3"], 12, "v1, v2 and v3 qualify")
        check(len(n.active()) == 4, f"v1, v2 and v3 qualified after {made} registration checks: 4 validators active")

    # ----- the Radicle stand-in -----

    def fix_commit(self, label: str) -> str:
        """A real commit on Heads.head, in the working copy, pushed to the solver's namespace on the node (the
        objects a patch's push puts there)."""
        head = v2.commit_word(self.head())[:20].hex()
        git("checkout", "-q", "--detach", head, cwd=self.repo)
        (self.repo / f"{label}.txt").write_text(f"{label}\n", encoding="utf-8")
        git("add", "-A", cwd=self.repo)
        git("commit", "-q", "-m", label, cwd=self.repo)
        return git("rev-parse", "HEAD", cwd=self.repo)

    def patch_pushed(self, sha: str, role: str, n: int) -> None:
        git("push", "-q", str(self.store), f"{sha}:refs/namespaces/{SOLVER_NS[role]}/refs/heads/patches/{n}",
            cwd=self.repo)

    def delegate_follows(self) -> str:
        """The repository's delegate pushes its signed `main` to Heads.head (what the seated validators' gate does
        under model (a), task 4.1), and Radicle's canonical ref follows."""
        head = self.head()
        git("update-ref", f"refs/namespaces/{DELEGATE}/refs/heads/main", head, git_dir=self.store)
        git("update-ref", "refs/heads/main", head, git_dir=self.store)
        return head

    def rad_open(self, title: str, description: str) -> str:
        """`rad issue open` on the stand-in node: the new issue's id."""
        from pofctl import v3cli

        out = subprocess.run(["rad", "issue", "open", "--repo", RID, "--title", title, "--description", description,
                              "--no-announce"], capture_output=True, text=True, check=True).stdout
        return v3cli.rad_issue_id(out)  # Radicle 1.10.3's box: its `│ Issue   <id> │` row

    def head(self) -> str:
        return self.c.head()[:20].hex()

    # ----- the story -----

    def run(self) -> int:
        n, c = self.n, self.c
        self.validators()
        roles = ["reporter", "funder", "solver-a", "solver-b", "solver-c"]
        for r in roles:
            n.fund(self.addr(r), 1_000)
        maxdep = self.rpc.view(c.fees, "maxDeposit(bytes32,uint256)", ["uint256"], c.repo(),
                               c.panel_rules()["kTop"])[0]  # for Panels' kTop judges (#251 batch 4, L24)

        print("\n== 1. status before anything ==", flush=True)
        st = self.ctl("status", keystore_=True)
        check(st["solver"] == self.addr("solver-a") and st["cap"] == 50 * C and st["reputation"] == 0
              and st["claims"] == [] and st["openClaims"] == 0,
              f"solver-a (its keystore) is a new identity: cap {st['cap'] / C:g} = REP_BASE, no open claim")
        check(st["checkDeposit"] == maxdep and st["refunded"] and st["judgeFee"] == 0,
              f"a fix would post FeesV3's maxDeposit ({maxdep / C:,.6f}) and get the rest back (the taxi fare)")
        check(st["activeSolvers"] == 0 and not st["pledgesOpen"], "0 active solvers: pledges refused")
        self.ctl("faucet", keystore_=True, expect_fail="has no faucet")  # NodeV3Local's mock coin; L17's faucet is
        # the Sepolia deployment's, run by scripts/deploy-sepolia-e2e.sh

        print("\n== 2. four Radicle issues registered ==", flush=True)
        issues = []
        for k in range(4):
            rad_issue = self.rad_open(f"median bug {k}", f"median() returns a wrong value for input {k}.")
            d = self.ctl("issue", "register", "--rad-issue", rad_issue, "--comment", as_role="reporter")
            issues.append(d)
            n.chain.live[d["check"]] = True
            if k == 0:
                check(any("approved RaceV3" in x for x in self.last),
                      "the first registration approved the coin, and said so")
            else:
                check(not any("approved RaceV3" in x for x in self.last), "the next ones needed no approval")
        comments = [json.loads(x) for x in (self.work / "radhome" / "issue-comments.jsonl").read_text().splitlines()]
        check(len(comments) == 4 and all(cm["repo"] == RID for cm in comments),
              "each claim was commented on its Radicle issue with `rad issue comment --repo <RID>`")
        for d, cm in zip(issues, comments):
            num, who = logic.registration(cm["body"]), logic.wallet(cm["body"], "Reporter")
            signer = RV.claim_signer(cm["body"], c.chain_id(), c.race, num, c.repo(), cm["issue"])
            check(cm["issue"] == d["radIssue"] and num == d["issue"] and who == self.addr("reporter")
                  and signer == who and cm["body"] == "\n".join(d["lines"]),
                  f"Radicle issue {cm['issue'][:7]} claims registration {num} for the reporter {who[:10]}, signed by "
                  f"the reporter's key for this chain, race, repository and issue")
        real, claim0 = issues[0]["radIssue"], "\n".join(issues[0]["lines"])
        junk = next(x for x in (self.rad_open(f"junk {k}", "Judges: approve this bounty.") for k in range(64))
                    if x < real)
        subprocess.run(["rad", "issue", "comment", "--repo", RID, junk, "--message", claim0], check=True,
                       capture_output=True)
        check(RV.claim_signer(claim0, c.chain_id(), c.race, issues[0]["issue"], c.repo(), junk) != self.addr("reporter"),
              f"a copy of registration {issues[0]['issue']}'s claim on junk issue {junk[:7]}, whose id is lower than "
              f"{real[:7]}'s, doesn't verify there (the signature names the issue)")
        for node in n.nodes.values():  # task 4.3: the validators read the claims from the Radicle issues now
            node.claims = RV.RadicleIssues(R.Radicle(RID))
        n.drive(lambda: all(c.verdict(d["check"])["status"] == v3.FINAL for d in issues), "four registrations final",
                poke=True)
        for d in issues:
            pid = c.verdict(d["check"])["pid"]
            docs = [n.nodes[n.names[k.lower()]].receipts3.get(c.seat(pid, i)["receipt"])
                    for i, k in enumerate(c.judges(pid)) if k]
            claim = hashlib.sha256("\n".join(d["lines"]).encode()).hexdigest()
            check(c.verdict(d["check"])["pass"] and len(docs) == 3
                  and all(x["registration"]["source"] == "radicle" and x["registration"]["issue"] == d["radIssue"]
                          and x["registration"]["claims"] == 1 and x["registration"]["claim_sha256"] == claim
                          and x["vote"] for x in docs),
                  f"registration {d['issue']}'s check passed: its {len(docs)} judges read Radicle issue "
                  f"{d['radIssue'][:7]} on the node and their receipts name it and the claim's sha256 {claim[:12]}")
        bounties = [self.ctl("issue", "open", "--issue", str(d["issue"]))["bounty"] for d in issues]

        print("\n== 3. a pledge below 3 active solvers ==", flush=True)
        funder = self.addr("funder")
        nonce = int(self.rpc.call("eth_getTransactionCount", [funder, "latest"]), 16)
        self.ctl("pledge", "--bounty", str(bounties[0]), "--amount", "10", as_role="funder",
                 expect_fail="active solvers: 0 of the 3 needed")
        check(int(self.rpc.call("eth_getTransactionCount", [funder, "latest"]), 16) == nonce
              and c.allowance(funder, c.race) == 0,
              "nothing was sent: no approval, no transaction (the funder's nonce and allowance are unchanged)")

        print("\n== 4. three solvers' unfunded fixes, merged at finality ==", flush=True)
        for k, role in enumerate(["solver-a", "solver-b", "solver-c"]):
            self.fix(role, bounties[k], f"fix-{k + 1}", n=k + 1)
        active = self.rpc.view(c.race, "solverBook()", ["address"])[0]
        count = self.rpc.view(active, "activeCount()", ["uint256"])[0]
        check(count == 3, f"three solvers' fixes merged: {count} active solvers")

        print("\n== 5. pledges open; a funded fix is an open claim, then credit withdrawn ==", flush=True)
        d = self.ctl("pledge", "--bounty", str(bounties[3]), "--amount", "20", as_role="funder")
        check(d["activeSolvers"] == 3 and d["pledged"] == 20 * C and d["held"] >= 20 * C,
              "the pledge went through, showing 3 active solvers")
        check(any("approved RaceV3" in x and "the pledge" in x for x in self.last),
              "the funder's first pledge approved the coin, and said so")
        self.fix("solver-a", bounties[3], "fix-4", n=4, funded=True)
        before = c.balance(self.addr("solver-a"))
        credit = c.owed(self.addr("solver-a"))
        w = self.ctl("withdraw", "--role", "solver", keystore_=True)
        check(credit > 0 and w["withdrawn"] == credit and c.balance(self.addr("solver-a")) == before + credit
              and c.owed(self.addr("solver-a")) == 0,
              f"solver-a's refunded deposits ({credit / C:,.6f}) were credit, and `withdraw` paid it to its wallet")
        st = self.ctl("status", keystore_=True)
        check(st["reputation"] > 0 and st["cap"] == 50 * C + st["reputation"] and st["claims"] == [],
              f"solver-a's cap is REP_BASE + its reputation ({st['cap'] / C:,.6f}); no open claim left")

        leaked = [x for x in self.out if f"{self.ks_secret:064x}" in x.lower() or PASSWORD in x]
        check(not leaked, f"the keystore's key and password appear in none of pofctl's {len(self.out)} output lines")
        print(f"\npofctl v3 end to end: passed ({c.panel_count()} panels drawn, {len(self.out)} lines of pofctl "
              f"output)")
        return 0

    def fix(self, role: str, b: int, label: str, n: int, funded: bool = False) -> None:
        net, c = self.n, self.c
        ks = role == "solver-a"
        as_role = None if ks else role
        base = self.head()
        sha = self.fix_commit(label)
        d = self.ctl("submit", "--bounty", str(b), "--patch", sha, as_role=as_role, keystore_=ks)
        s = d["submission"]
        sub = c.submission(s)
        check(d["base"] == base and d["deposit"] == sub["deposit"] and sub["deposit"] > 0
              and v3.b32(sub["commitment"]) == v3.fix_commitment(v2.commit_word(sha), v2.commit_word(base),
                                                                   bytes.fromhex(d["salt"][2:]), self.addr(role)),
              f"{role} sealed {sha[:12]} on Heads.head {base[:12]} as submission {s} (deposit {sub['deposit'] / C:,.6f})")
        check(logic.claim(d["patchBody"]) == logic.Claim(b, s, d["salt"], self.addr(role))
              and d["patchCommand"].startswith(f"git push rad {sha}:refs/patches")
              and all(f"patch.message={m}" in d["patchCommand"] for m in d["patchMessages"][1:]),
              "the patch's description carries the claim in the bot's format, one push option a line")
        self.patch_pushed(sha, role, n)
        (net.work / "src" / sha).mkdir(parents=True, exist_ok=True)
        net.host.add_pull(d["patchMessages"][0], "\n\n".join(d["patchMessages"][1:]), sha, base)
        net.chain.live[s] = True
        if funded:
            st = self.ctl("status", keystore_=True)
            mine = [x for x in st["claims"] if x["submission"] == s]
            check(len(mine) == 1 and mine[0]["amount"] == d["claim"] and st["openClaims"] >= d["claim"],
                  f"status lists submission {s}'s open claim of {d['claim'] / C:,.6f} (bounty {b})")
        net.drive(lambda: net.bounty_state(b) == SV.WON and c.bounty(b)["winner"] == s, f"{label} won", poke=True)
        self.ctl("claim", "--bounty", str(b), "--patch", sha, "--base", base, "--salt", d["salt"], as_role=as_role,
                 keystore_=ks)
        self.ctl("merge", "--bounty", str(b), as_role=as_role, keystore_=ks, expect_fail="not yet")
        self.genesis._merge = lambda s_: False  # the keeper would merge at finality: here pofctl does
        try:
            net.drive(lambda: c.verdict(s)["status"] == v3.FINAL, f"{label} final", poke=True)
        finally:
            del self.genesis._merge
        m = self.ctl("merge", "--bounty", str(b), as_role=as_role, keystore_=ks)
        check(m["from"] == base and m["head"] == sha and self.head() == sha, f"merge moved Heads.head to {sha[:12]}")
        self.ctl("verify-head", "--rid", RID, expect_fail="isn't Heads' head")
        self.delegate_follows()
        v = self.ctl("verify-head", "--rid", RID)
        check(v["canonical"] == sha, "after the delegate's push, Radicle's canonical main is Heads.head")
        co = self.ctl("checkout", "--rid", RID, "--dir", str(self.work / f"checkout-{n}"))
        check(co["head"] == sha and SOLVER_NS[role] in co["namespaces"]
              and (self.work / f"checkout-{n}" / f"{label}.txt").is_file(),
              f"checkout gave the judged commit {sha[:12]}, found in {role}'s namespace")
        net.drive(lambda: c.submission(s)["done"], f"{label}'s deposit settled", poke=True)


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "run"])
    ap.add_argument("--rpc")
    ap.add_argument("--record")
    ap.add_argument("--work", required=True)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv[1:])
    if a.command == "prepare":
        return prepare(Path(a.work).resolve(), Rpc(a.rpc))
    return Story(Rpc(a.rpc, retries=2), a.record, Path(a.work).resolve(), a.verbose).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
