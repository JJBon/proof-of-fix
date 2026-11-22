"""The engineers' demo end to end (proof-of-fix#104), against a throwaway devnet with v2 deployed (7 seats, seat 5's
key published by the owner, seat 6 vacant) and a fake GitHub. Run it with scripts/demo-e2e.sh, which starts and
removes the devnet. Not part of the unit tests: it needs Docker (the devnet and the fixes' sandbox).

The story:
1. a new engineer, with a key of their own, joins seat 6: `pofctl validator join` (the digest from Verdicts, signed
   with their key), the owner publishes it co-signed by the seats (`pofctl validator publish`), 7 days pass, both
   pending seats are activated: 7 active seats, 3 judges drawn per check;
2. bounties on the fake GitHub: an issue registered and accepted, funded; two bad fixes and a good one sealed with
   their deposits (the meter's worst case), their pull requests opened. Seven real node processes run
   (`python3 -m oracle run --until-idle`): only the 3 drawn for a submission act. Each fetches the pull request's
   head commit itself from the demo repository (a local bare repository: oracle/fetch.py, #115), checks it in the
   sandbox, judges
   it (the fake judge), report their measured usage to the meter, seal, reveal, sign the verdict v2, and one relays
   it. The pull request is merged on GitHub; the drawn judges sign the merge; the bounty settles. Bounties repeat
   until the engineer's seat has been drawn (each has 3 submissions, each a 3-of-7 draw);
3. every validator with fees withdraws them with the node's `withdraw-fees`.

With --exchange http (proof-of-fix#117) the nodes share no folder: each has its own working directory, checkouts and
receipts, and the drawn judges talk only through the exchange service (python3 -m exchange, the hosted convenience
relay), which reads the draw from the devnet; the run checks every check's seals and signatures went through it.
With --exchange http-down the nodes run "http,folder" with nothing listening at the service's URL: the relay is never
required, the checks complete through the folder and the nodes relay the results themselves.

Checked exactly: each result's deposit = what the meter charged + what returned to the solver (read at the result's
block); what the meter charged = what the judges and the relayer were credited in that block; every withdrawal pays
the credit to the wallet; everything charged was withdrawn; 3 usage reports per check."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bot.forgejo import git  # noqa: E402 (git with no credential helper and a throwaway identity)
from fake_github import FakeGitHub  # noqa: E402
from oracle import abi, v2  # noqa: E402
from oracle.crypto import address, checksum  # noqa: E402
from oracle.rpc import Rpc  # noqa: E402
from pofctl import keys  # noqa: E402
from pofctl.cli import run  # noqa: E402

REPO = "demo/median"
C = 10**6
MIN_BOUNTIES, MAX_BOUNTIES = 2, 6  # at least two, so the draws visibly differ; more until the engineer is drawn
IDLE = 25  # seconds a node waits without progress before it exits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--record", required=True)
    ap.add_argument("--work", required=True, help="a scratch directory (checkouts, receipts, the nodes' exchange)")
    ap.add_argument("--exchange", choices=("folder", "http", "http-down"), default="folder",
                    help="how the drawn judges talk: a shared folder, the exchange service with no shared folder, or "
                         "http,folder with the service down (the fallback)")
    args = ap.parse_args()
    work = Path(args.work).resolve()
    record = json.loads(Path(args.record).read_text(encoding="utf-8"))
    rpc = Rpc(args.rpc)
    chain = v2.Chain(rpc, record["race"])
    base = ["--rpc", args.rpc, "--record", args.record]
    problems: list = []

    def ctl(*argv, as_role=None, show=True):
        cmd = base + (["--as", as_role] if as_role else []) + list(argv)
        data, lines = run(cmd)
        if show:
            print(f"$ pofctl {' '.join((['--as', as_role] if as_role else []) + list(argv))}")
            print("  " + "\n  ".join(lines), flush=True)
        return data

    def view_at(block: int, to: str, sig: str, returns: list, *a):
        raw = rpc.call("eth_call", [{"to": to, "data": "0x" + abi.call_data(sig, *a).hex()}, hex(block)])
        return abi.decode(returns, abi.hexdata(raw))

    def owed_at(block: int, who: str) -> int:
        return view_at(block, chain.race, "owed(address,address)", ["uint256"], who, chain.coin())[0]

    # ---------- the seats: 5 oracle roles, seat 5 (joiner-0, published by the owner), seat 6 (the engineer) ----------
    seat_keys = {f"oracle-{i}": keys.derive(keys.MNEMONIC, keys.ROLES.index(f"oracle-{i}")) for i in range(5)}
    seat_keys["joiner-0"] = keys.derive(keys.MNEMONIC, keys.ROLES.index("joiner-0"))
    engineer = secrets.randbelow(2**255) + 1  # the engineer's own key: in this process's memory only
    seat_keys["engineer"] = engineer
    os.environ["POFCTL_KEY_ENGINEER"] = hex(engineer)
    rpc.call("anvil_setBalance", [address(engineer), hex(100 * 10**18)])  # gas for its usage reports and relays
    names = {address(k).lower(): n for n, k in seat_keys.items()}

    service = None
    if args.exchange == "http":
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        exchange_url = f"http://127.0.0.1:{port}"
        service_log = open(work / "exchange-service.log", "w", encoding="utf-8")
        service = subprocess.Popen(
            [sys.executable, "-m", "exchange"], cwd=ROOT, stdout=service_log, stderr=subprocess.STDOUT,
            env={**os.environ, "EXCHANGE_RPC": args.rpc, "EXCHANGE_RACE": record["race"], "EXCHANGE_PORT": str(port),
                 "EXCHANGE_SEAL_WINDOW": "60", "EXCHANGE_STATE": str(work / "exchange-service.jsonl"),
                 "PYTHONDONTWRITEBYTECODE": "1"})
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                time.sleep(0.1)
        atexit.register(lambda: (service.terminate(), service.wait(timeout=10)))
        print(f"the exchange service: {exchange_url} (the nodes share no folder)", flush=True)
    else:
        exchange_url = None
    down_url = None
    if args.exchange == "http-down":  # a port nothing listens on: the relay is down for the whole run
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            down_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        print(f"the exchange service: down ({down_url}); the nodes run http,folder", flush=True)

    with FakeGitHub() as gh:
        cfg = work / "pofctl.json"
        repos = {"repos": {REPO: {"host": "github", "api": gh.url}}}
        cfg.write_text(json.dumps(repos), encoding="utf-8")
        base += ["--config", str(cfg)]
        os.environ["GITHUB_TOKEN"] = gh.token

        print("== 1. a new engineer joins seat 6 ==", flush=True)
        ctl("status")
        req = ctl("validator", "join", "--seat", "6", as_role="engineer")
        ctl("validator", "publish", "--seat", "6", "--key", req["key"], "--nonce", req["nonce"], "--sig", req["sig"])
        try:
            ctl("validator", "activate", "--seat", "6", show=False)
            problems.append("a published key took its seat before the 7-day delay")
        except Exception as e:  # noqa: BLE001 (the refusal is the point)
            print(f"  (activating at once is refused, as it should be: {e})")
        ctl("devnet", "warp", "--days", "7")
        ctl("validator", "activate", "--seat", "5")
        ctl("validator", "activate", "--seat", "6")
        if len(chain.keys()) != 7:
            problems.append(f"{len(chain.keys())} active seats, not 7")
        ctl("validator", "status", as_role="engineer")

        print("\n== 2. bounties, judged by the drawn validators' nodes ==", flush=True)
        for role in ("reporter", "funder", "solver-a", "solver-b"):
            ctl("coin", "mint", "--to", role, "--amount", "100000", show=False)
        # The demo repository: a bare repository the nodes fetch each claimed commit from (#115), as they'd fetch
        # from GitHub; its main is the sample code, and every fix is a commit on top of it.
        bare, clone = work / "git" / f"{REPO}.git", work / "git-work"
        bare.parent.mkdir(parents=True)
        clone.mkdir()
        git(str(work), "init", "-q", "--bare", str(bare))
        git(str(clone), "init", "-q")
        for f in (ROOT / "bot" / "sample").iterdir():
            if f.is_file():
                shutil.copy(f, clone / f.name)
        git(str(clone), "add", "-A")
        git(str(clone), "commit", "-q", "-m", "the sample code")
        base_sha = git(str(clone), "rev-parse", "HEAD")
        git(str(clone), "push", "-q", str(bare), "HEAD:refs/heads/main")

        def commit_fix(fix: str, solver: str) -> str:
            """The solver's fix as a commit on main, pushed to its own branch; its id is what gets sealed."""
            git(str(clone), "checkout", "-q", "--detach", base_sha)
            shutil.copy(ROOT / "bot" / "fixes" / fix, clone / "stats.py")
            shutil.copy(ROOT / "bot" / "acceptance" / "test_issue_median_even.py", clone)
            git(str(clone), "add", "-A")
            git(str(clone), "commit", "-q", "-m", f"fix the median ({fix}, {solver}, {secrets.token_hex(4)})")
            sha = git(str(clone), "rev-parse", "HEAD")
            git(str(clone), "push", "-q", str(bare), f"HEAD:refs/heads/fix-{sha[:12]}")
            return sha

        node_env = {
            "ORACLE_RACE": record["race"], "ORACLE_KEYS": "env", "ORACLE_REPO": REPO,
            "ORACLE_REPOS": str(cfg), "GITHUB_TOKEN": gh.token, "ORACLE_SRC_ROOT": str(work / "src"),
            "ORACLE_GIT_URL": f"file://{work / 'git'}/{{repo}}.git",
            "ORACLE_EXCHANGE": str(work / "exchange"), "ORACLE_ROUND_TIMEOUT": "60", "ORACLE_POLL": "1",
            "ORACLE_MERGE_WEIGHT": "100", "PYTHONDONTWRITEBYTECODE": "1",
        }
        if exchange_url:  # no shared folder: the service only, and each node in its own directory
            del node_env["ORACLE_EXCHANGE"]
            node_env.update({"ORACLE_EXCHANGE_TRANSPORT": "http", "ORACLE_EXCHANGE_URL": exchange_url,
                             "PYTHONPATH": str(ROOT)})
        if down_url:
            node_env.update({"ORACLE_EXCHANGE_TRANSPORT": "http,folder", "ORACLE_EXCHANGE_URL": down_url})

        def home(name: str) -> Path:
            """A node's own directory (http): its working directory, config, checkouts and receipts."""
            d = work / "nodes" / name
            (d / "src").mkdir(parents=True, exist_ok=True)
            if not (d / "pofctl.json").exists():
                shutil.copy(cfg, d / "pofctl.json")
            return d
        start_block = rpc.block()
        submissions: dict = {}  # id -> {"solver", "deposit", "judges", "bounty"}
        drawn_engineer = 0
        bounties = []

        def run_nodes(label: str) -> None:
            """The 7 seats' nodes, as separate processes, until each is idle."""
            procs = []
            for name, k in seat_keys.items():
                env = {**os.environ, **node_env, "ORACLE_PRIVATE_KEY": hex(k),
                       "ORACLE_RECEIPTS": str(work / "receipts" / name)}
                cwd = ROOT
                if exchange_url:
                    cwd = home(name)
                    env.update({"ORACLE_RECEIPTS": str(cwd / "receipts"), "ORACLE_SRC_ROOT": str(cwd / "src"),
                                "ORACLE_REPOS": str(cwd / "pofctl.json")})
                if name == "engineer":  # the engineer reaches the chain with an API key (sent as HTTP Basic)
                    env["ORACLE_RPC"] = args.rpc.replace("http://", "http://engineer:demo-key@")
                else:
                    env["ORACLE_RPC"] = args.rpc
                log = open(work / f"node-{name}.log", "a", encoding="utf-8")
                procs.append((name, log, subprocess.Popen(
                    [sys.executable, "-m", "oracle", "run", "--until-idle", str(IDLE), "--from-block",
                     str(start_block)], cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT)))
            for name, log, p in procs:
                code = p.wait(timeout=900)
                log.close()
                if code:
                    problems.append(f"{label}: {name}'s node exited {code} (see {work}/node-{name}.log)")
            print(f"  -- the nodes' logs ({label}) --")
            for name, _, _ in procs:
                text = (work / f"node-{name}.log").read_text(encoding="utf-8")
                (work / f"node-{name}.log").write_text("", encoding="utf-8")
                for line in text.splitlines():
                    if "not drawn" in line or "idle for" in line or "check(s) finished" in line:
                        continue
                    print(f"  {name:>9} {line.split('] ', 1)[-1]}")
            sys.stdout.flush()

        for k in range(1, MAX_BOUNTIES + 1):
            print(f"\n-- bounty round {k} --", flush=True)
            rep = ctl("reporter", "register")
            gh_issue = gh.add_issue(REPO, f"median() is wrong for an even count ({k})",
                                    f"`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\n"
                                    f"Reporter wallet: {rep['reporter']}\n", labels=["bounty"])
            bounty = ctl("oracle", "accept", "--issue", str(rep["issue"]))["bounty"]
            bounties.append(bounty)
            ctl("bot", "link", "--repo", REPO, "--issue", str(gh_issue), "--bounty", str(bounty), show=k == 1)
            ctl("funder", "fund", "--bounty", str(bounty), "--amount", "100", show=k == 1)
            ctl("solver", "quote", "--bounty", str(bounty), as_role="solver-a", show=k == 1)
            good_pr = None
            for solver, fix in (("solver-a", "bad_stats.py"), ("solver-b", "bad_stats.py"),
                                ("solver-b", "good_stats.py")):
                sha = commit_fix(fix, solver)  # nothing staged for the nodes: they fetch it
                r = ctl("solver", "submit", "--bounty", str(bounty), "--commit", sha, "--issue", str(gh_issue),
                        as_role=solver, show=False)
                print(f"$ pofctl --as {solver} solver submit --bounty {bounty} --commit {sha[:12]}…  -> submission "
                      f"{r['submission']}, deposit {r['deposit'] / C:,.6f}, drawn "
                      f"{', '.join(names.get(j.lower(), j) for j in r['judges'])}")
                pr = gh.add_pull(REPO, f"Fix the median ({fix})", r["prBody"], sha, user=solver, base_sha=base_sha)
                if fix == "good_stats.py":
                    good_pr = pr
                submissions[r["submission"]] = {"solver": address(keys.derive(keys.MNEMONIC,
                                                                               keys.ROLES.index(solver))),
                                                "deposit": r["deposit"], "judges": r["judges"], "bounty": bounty,
                                                "good": fix == "good_stats.py"}
                drawn_engineer += any(j.lower() == address(engineer).lower() for j in r["judges"])
            run_nodes(f"bounty {bounty}'s checks")
            state = chain.bounty(bounty)
            if v2.STATES[state["state"]] != "Won":
                problems.append(f"bounty {bounty} is {v2.STATES[state['state']]} after its checks, not Won")
                break
            print(f"  bounty {bounty}: Won by submission {state['winner']}")
            gh.merge(REPO, good_pr)
            print(f"  (pull request #{good_pr} merged on GitHub)")
            run_nodes(f"bounty {bounty}'s merge")
            if v2.STATES[chain.bounty(bounty)["state"]] != "Merged":
                problems.append(f"bounty {bounty} isn't Merged after its merge")
                break
            for _ in range(80):
                ctl("devnet", "warp", "--days", "1", show=False)
                if ctl("bot", "settle", "--bounty", str(bounty), show=False)["settled"]:
                    break
            else:
                problems.append(f"bounty {bounty} never settled")
            print(f"$ pofctl bot settle --bounty {bounty}\n  bounty {bounty}: Paid")
            ctl("funder", "claim", "--bounty", str(bounty), show=False)
            print(f"  the engineer's seat was drawn for {drawn_engineer} submission(s) so far")
            if drawn_engineer and k >= MIN_BOUNTIES:
                break
        else:
            problems.append(f"the engineer's seat wasn't drawn in {MAX_BOUNTIES} bounties")

        print("\n== 3. the validators withdraw their fees ==", flush=True)
        ctl("validator", "status", as_role="engineer")
        withdrawn = {}
        for name, k in seat_keys.items():
            who = address(k)
            owed, wallet = chain.owed(who), rpc.view(chain.coin(), "balanceOf(address)", ["uint256"], who)[0]
            if not owed:
                continue
            if name == "engineer":  # the engineer with pofctl, the others with their node's command
                ctl("validator", "withdraw", as_role="engineer")
            else:
                env = {**os.environ, **node_env, "ORACLE_RPC": args.rpc, "ORACLE_PRIVATE_KEY": hex(k)}
                out = subprocess.run([sys.executable, "-m", "oracle", "withdraw-fees"], cwd=ROOT, env=env,
                                     capture_output=True, text=True, timeout=120)
                print(f"$ python3 -m oracle withdraw-fees   ({name}'s node)\n  {out.stdout.strip()}{out.stderr.strip()}")
            after = rpc.view(chain.coin(), "balanceOf(address)", ["uint256"], who)[0]
            withdrawn[name] = after - wallet
            if after - wallet != owed or chain.owed(who):
                problems.append(f"{name}: withdrew {after - wallet}, its credit was {owed}")
        ctl("balances", "--roles", "reporter,funder,solver-a,solver-b")

        # ---------- the checks ----------
        charged = chain.charged(start_block)
        by_block: dict = {}
        for e in rpc.logs(chain.race, start_block, ["0x" + v2.keccak256(b"Decided(uint256,uint8)").hex()]):
            by_block.setdefault(int(e["blockNumber"], 16), []).append(int(e["topics"][1], 16))
        print("\n== the books ==")
        print(f"{'submission':>10} {'outcome':>8} {'deposit':>12} {'charged':>12} {'refunded':>12}  judges (reports)")
        total_charged = 0
        for block, subs in sorted(by_block.items()):
            for solver in {submissions[s]["solver"] for s in subs if s in submissions}:
                mine = [s for s in subs if s in submissions and submissions[s]["solver"] == solver]
                deposit = sum(submissions[s]["deposit"] for s in mine)
                got = sum(charged.get(s, (0, 0))[1] for s in mine)
                back = owed_at(block, solver) - owed_at(block - 1, solver)
                if deposit != got + back:
                    problems.append(f"block {block}: deposits {deposit} != charged {got} + refunded {back}")
                for s in mine:
                    outcome = v2.OUTCOMES[chain.submission(s)["outcome"]]
                    n_judges, amount = charged.get(s, (0, 0))
                    reports = chain.reports(s)
                    share = back if len(mine) == 1 else submissions[s]["deposit"] - amount
                    print(f"{s:>10} {outcome:>8} {submissions[s]['deposit'] / C:>12,.6f} {amount / C:>12,.6f} "
                          f"{share / C:>12,.6f}  "
                          f"{', '.join(names.get(r['judge'].lower(), r['judge'][:10]) for r in reports)} "
                          f"({len(reports)})")
                    if n_judges != 3 or len(reports) != 3:
                        problems.append(f"submission {s}: {len(reports)} reports, {n_judges} judges charged")
                    if {r["judge"].lower() for r in reports} != {j.lower() for j in submissions[s]["judges"]}:
                        problems.append(f"submission {s}: the reports aren't the drawn judges'")
            in_block = sum(charged.get(s, (0, 0))[1] for s in subs)
            total_charged += in_block
            credited = sum(owed_at(block, address(k)) - owed_at(block - 1, address(k)) for k in seat_keys.values())
            if credited != in_block:
                problems.append(f"block {block}: the meter charged {in_block}, the validators were credited {credited}")
        if len(charged) != len(submissions):
            problems.append(f"{len(charged)} checks charged for {len(submissions)} submissions")
        if sum(withdrawn.values()) != total_charged:
            problems.append(f"withdrawn {sum(withdrawn.values())} != charged {total_charged}")
        if not withdrawn.get("engineer"):
            problems.append("the engineer's validator earned nothing")
        print(f"\ncharged by the meter: {total_charged / C:,.6f} for {len(charged)} checks; withdrawn by the "
              f"validators: {sum(withdrawn.values()) / C:,.6f}")
        for name, amount in sorted(withdrawn.items()):
            n = sum(any(j.lower() == address(seat_keys[name]).lower() for j in s["judges"])
                    for s in submissions.values())
            print(f"  {name:>9} {checksum(address(seat_keys[name]))[:12]}…  drawn {n:>2}  withdrew {amount / C:,.6f}")
        if exchange_url:
            from oracle.transport import HttpExchange

            ex = HttpExchange(exchange_url, record["race"], log=lambda m: None)
            for s, sub in sorted(submissions.items()):
                seals, results = ex.all(s, "seal"), ex.all(s, "result")
                drawn = {j.lower() for j in sub["judges"]}
                if set(seals) != drawn or len(results) < v2.ISSUE_QUORUM or not set(results) <= drawn:
                    problems.append(f"submission {s}: {len(seals)} seals and {len(results)} signatures through the "
                                    f"exchange, not the drawn judges'")
            shared = [p for p in work.rglob("*") if p.name in ("exchange", ".oracle-exchange")]
            if shared:
                problems.append(f"a shared exchange folder exists: {shared[0]}")
            print(f"through the exchange service: seals, reveals and signatures of {len(submissions)} checks; "
                  f"no shared folder")
        if down_url:
            from oracle.transport import FolderExchange

            folder = FolderExchange(work / "exchange", record["race"])
            for s, sub in sorted(submissions.items()):
                if {n.lower() for n in folder.all(s, "seal")} != {j.lower() for j in sub["judges"]}:
                    problems.append(f"submission {s}: the drawn judges' seals aren't in the folder")
            print(f"with the exchange service down: {len(submissions)} checks through the folder, relayed by the nodes")
        for p in problems:
            print(f"FAILED: {p}")
        print("result: the engineers' demo ran end to end" if not problems else f"result: {len(problems)} failed")
        return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
