"""pofctl end to end (proof-of-fix#104), against a throwaway devnet with v2 deployed and a fake GitHub: every role,
through pofctl, from an issue to a settled bounty. Run it with scripts/pofctl-e2e.sh (it starts and removes the
devnet). Not part of the unit tests: it needs Docker for the devnet.

The story: a reporter opens an issue on the (fake) GitHub repository and registers it on-chain; the stub quorum's
registration check opens its bounty, and the bot links them on the issue. A funder pledges 100; two days later
solver-a attempts (locking 70 %), submits, opens a pull request, and fails the checks; solver-b's fix passes, its pull
request is merged, and the signed merge starts the award. The bot settles once the instalments are released, the
funder claims the leftover, everyone withdraws.

The checks are metered (v2, #85 task 5.7): the stub quorum's keys drawn for each submission report their usage and
sign the verdict v2, and the meter charges each. Checked to the micro-coin: the failed solver's deposit = what was
charged + what returned to it; the drawn judges and the relayer hold exactly what the meter charged; the winner's
price matches the quote; and no coin is created or lost (every account's wallet and credit add up to what was
minted)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from bot import logic  # noqa: E402
from fake_github import FakeGitHub  # noqa: E402
from pofctl.cli import run  # noqa: E402

REPO = "demo/sample"
C = 10**6
START = 1_000 * C
PLEDGE = 100 * C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", required=True)
    ap.add_argument("--record", required=True)
    args = ap.parse_args()
    base = ["--rpc", args.rpc, "--record", args.record]

    def ctl(*argv, as_role=None, show=True):
        cmd = base + (["--as", as_role] if as_role else []) + list(argv)
        data, lines = run(cmd)
        if show:
            print(f"$ pofctl {' '.join((['--as', as_role] if as_role else []) + list(argv))}")
            print("  " + "\n  ".join(lines), flush=True)
        return data

    with FakeGitHub() as gh, tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "pofctl.json"
        cfg.write_text(json.dumps({"repos": {REPO: {"host": "github", "api": gh.url}}}), encoding="utf-8")
        base += ["--config", str(cfg)]
        os.environ["GITHUB_TOKEN"] = gh.token

        ctl("status")
        for role in ("reporter", "funder", "solver-a", "solver-b"):
            ctl("coin", "mint", "--to", role, "--amount", str(START // C), show=False)
        reporter = ctl("reporter", "register")
        gh_issue = gh.add_issue(REPO, "median() is wrong for an even count",
                                f"`median([4, 1, 3, 2])` returns 3; it should be 2.5.\n\n"
                                f"Reporter wallet: {reporter['reporter']}\n", labels=["bounty"])
        bounty = ctl("oracle", "accept", "--issue", str(reporter["issue"]))["bounty"]
        ctl("bot", "link", "--repo", REPO, "--issue", str(gh_issue), "--bounty", str(bounty))
        assert logic.linked([{"body": c["body"]} for c in gh.repos[REPO]["comments"][gh_issue]]), "no bounty comment"
        ctl("funder", "fund", "--bounty", str(bounty), "--amount", str(PLEDGE // C))

        ctl("devnet", "warp", "--days", "2")
        ctl("solver", "quote", "--bounty", str(bounty), as_role="solver-a")
        ctl("solver", "attempt", "--bounty", str(bounty), as_role="solver-a")
        bad_sha = "a" * 40
        bad = ctl("solver", "submit", "--bounty", str(bounty), "--commit", bad_sha, "--issue", str(gh_issue),
                  as_role="solver-a")
        bad_pr = gh.add_pull(REPO, "Fix the median", bad["prBody"], bad_sha, user="solver-a")
        solver_a = bad["solver"]
        credit_before = ctl("balances", "--roles", "solver-a", show=False)[0]["credit"]
        failed = ctl("oracle", "result", "--submission", str(bad["submission"]), "--outcome", "fail", "--repo", REPO,
                     "--pr", str(bad_pr))
        assert failed["outcome"] == "Fail" and failed["state"] == "Open", failed
        refunded = ctl("balances", "--roles", "solver-a", show=False)[0]["credit"] - credit_before

        ctl("devnet", "warp", "--days", "1")
        ctl("solver", "attempt", "--bounty", str(bounty), as_role="solver-b")
        good_sha = "b" * 40
        good = ctl("solver", "submit", "--bounty", str(bounty), "--commit", good_sha, "--issue", str(gh_issue),
                   as_role="solver-b")
        good_pr = gh.add_pull(REPO, "Fix the median of an even count", good["prBody"], good_sha, user="solver-b")
        # A pull request that doesn't open the seal is refused before anything is signed.
        try:
            ctl("oracle", "result", "--submission", str(good["submission"]), "--outcome", "pass", "--repo", REPO,
                "--pr", str(bad_pr), show=False)
            raise AssertionError("a pull request for another submission was accepted")
        except Exception as e:  # noqa: BLE001 (the refusal is the point)
            print(f"  (refused as it should be: {e})")
        passed = ctl("oracle", "result", "--submission", str(good["submission"]), "--outcome", "pass", "--repo", REPO,
                     "--pr", str(good_pr))
        assert passed["outcome"] == "Pass" and passed["state"] == "Won", passed
        try:
            ctl("oracle", "merged", "--bounty", str(bounty), "--repo", REPO, "--pr", str(good_pr), show=False)
            raise AssertionError("an unmerged pull request was signed as merged")
        except Exception as e:  # noqa: BLE001
            print(f"  (refused as it should be: {e})")
        gh.merge(REPO, good_pr)
        ctl("oracle", "merged", "--bounty", str(bounty), "--repo", REPO, "--pr", str(good_pr))

        for _ in range(60):
            ctl("devnet", "warp", "--days", "1", show=False)
            if ctl("bot", "settle", "--bounty", str(bounty), show=False)["settled"]:
                break
        else:
            raise AssertionError("the bounty never settled")
        print(f"$ pofctl bot settle --bounty {bounty}\n  bounty {bounty}: Paid")
        ctl("funder", "claim", "--bounty", str(bounty))
        for role in ("reporter", "funder", "solver-a", "solver-b"):
            ctl("withdraw", "--role", role, show=False)
        ctl("validator", "status", as_role="oracle-0")
        balances = ctl("balances")
        ctl("history")

        # The books: every check's charge, and every coin accounted for.
        q = ctl("solver", "quote", "--bounty", str(bounty), show=False)
        problems = []
        if bad["deposit"] != failed["charged"] + refunded:
            problems.append(f"the failed check: deposit {bad['deposit']} != charged {failed['charged']} + refunded "
                            f"{refunded}")
        if not 0 < failed["charged"] < bad["deposit"]:
            problems.append(f"the failed check charged {failed['charged']} of {bad['deposit']}")
        by_address = {b["address"].lower(): b["wallet"] + b["credit"] for b in balances}
        judges = {j.lower() for j in failed["signers"] + passed["signers"]}
        relayer = next(b["address"].lower() for b in balances if b["account"] == "bot (relayer)")
        earned = sum(by_address.get(j, 0) for j in judges) + by_address.get(relayer, 0)
        if earned != failed["charged"] + passed["charged"]:
            problems.append(f"the judges and the relayer hold {earned}, the meter charged "
                            f"{failed['charged'] + passed['charged']}")
        total = sum(b["wallet"] + b["credit"] for b in balances)
        if total != 4 * START:
            problems.append(f"the coins don't add up: {total} != {4 * START}")
        if q["state"] != "Paid":
            problems.append(f"the bounty is {q['state']}, not Paid")
        print(f"  checks: failed {failed['charged'] / C:,.6f} charged of {bad['deposit'] / C:,.6f} "
              f"({refunded / C:,.6f} back); passed {passed['charged'] / C:,.6f} (back to the winner at settlement)")
        for p in problems:
            print(f"FAILED: {p}")
        print("result: pofctl drove every role end to end" if not problems else f"result: {len(problems)} failed")
        return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
