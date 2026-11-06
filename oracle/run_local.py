"""The oracle nodes on a chain (proof-of-fix#94). Run it with scripts/oracle-run.sh [--devnet].

Locally, the loop's deployment (contracts/script/Loop.s.sol: oracle keys oracle0..oracle2, quorum 2 of 3) on a throwaway
anvil. With --devnet (ORACLE_RECORD set), the private devnet's deployed Race and test coin from its deployment record,
one node per devnet oracle key (ORACLE_KEYS, from OpenBao), and the record's quorum (3 of 5).
Then a funded bounty and two sealed submissions (the loop's bad and good fixes). The registered nodes and one
unregistered node watch the chain, check each submission in the sandbox, judge it, seal, reveal, and sign; the
aggregator relays a quorum.
The #93 comment 4603 scenarios it shows:
- the contract refuses a forged relay signed with a key outside the set;
- the bad fix fails by a quorum; the good one passes 2 to 1 with a node lying, and the dissent is logged;
- the unregistered node's reveals are ignored; too few nodes relay nothing;
- a tampered receipt, a changed verdict and an early reveal are refused;
- a canary scores every node.
Everything runs on this machine (openspec/config.yaml rule 1)."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path

from bot.chain import Chain
from bot.loop import LOOP
from bot.loop import keys as role_keys

from . import crypto
from .aggregator import Round, Scoreboard, assemble
from .chain import Race, Rpc
from .judge import FakeJudge
from .keys import DevnetKeys, KeyProvider, LocalDevKeys
from .node import Claim, Node, RefusedClaim, fees_for, result_digest
from .receipt import Store

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "bot"
C = 10**6
RESULT_SIG = "result(uint256,uint8,bytes32,(address,uint256)[],(bytes32,bytes[]))"


def say(step: str, detail: str = "") -> None:
    print(f"[oracle] {step}" + (f": {detail}" if detail else ""), flush=True)


def topic(chain: Chain, receipt: dict, event: str, index: int) -> int:
    t0 = chain.keccak(event)
    for log in receipt["logs"]:
        if log["topics"][0] == t0:
            return int(log["topics"][index], 16)
    raise RuntimeError(f"no {event} in the receipt")


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "solver", "GIT_AUTHOR_EMAIL": "s@example.invalid",
                               "GIT_COMMITTER_NAME": "solver", "GIT_COMMITTER_EMAIL": "s@example.invalid"}).stdout.strip()


def fix_tree(work: Path, name: str, fix_file: str) -> tuple[Path, str]:
    """The sample library with a fix applied and the issue's acceptance test added; its git tree is the fix."""
    src = work / name
    shutil.copytree(BOT / "sample", src)
    shutil.copy(BOT / "fixes" / fix_file, src / "stats.py")
    shutil.copy(BOT / "acceptance" / "test_issue_median_even.py", src)
    git(src, "init", "-q")
    git(src, "add", ".")
    tree = git(src, "write-tree")
    shutil.rmtree(src / ".git")
    return src, tree


KEYS = role_keys()  # the devnet's keys from the environment (LOOP_KEY_<ROLE>, from OpenBao), else anvil's test keys


def relay(chain: Chain, race: str, sid: int, outcome: int, fix: bytes, signers: list[str], nonce: bytes,
          sigs: list[str]) -> dict:
    fees = "[" + ",".join(f"({to},{amount})" for to, amount in fees_for(signers)) + "]"
    auth = f"(0x{nonce.hex()},[{','.join(sigs)}])"
    return chain.send(KEYS["bot"], race, RESULT_SIG, str(sid), str(outcome), "0x" + fix.hex(), fees, auth)


def oracle_keys() -> list[KeyProvider]:
    """The devnet's oracle keys (ORACLE_KEYS, from OpenBao), else the local loop's three public test keys."""
    devnet = [k for k in os.environ.get("ORACLE_KEYS", "").split(",") if k]
    if devnet:
        return [DevnetKeys(int(k, 16)) for k in devnet]
    return [LocalDevKeys(i) for i in range(3)]


def run() -> int:
    record_path = os.environ.get("ORACLE_RECORD")
    chain = Chain(os.environ["ORACLE_CHAIN"], os.environ.get("ORACLE_CHAIN_ID", "31337"))
    rpc = Rpc(os.environ.get("ORACLE_RPC", "http://127.0.0.1:18545"))
    for _ in range(60):
        if chain.ready():
            break
        time.sleep(1)
    problems: list[str] = []
    work = Path(tempfile.mkdtemp(prefix="pof-oracle-"))
    try:
        participants = ("bot", "reporter", "funder", "solver-a", "solver-b")
        addr = {who: chain.address(KEYS[who]) for who in (participants if record_path else KEYS)}
        if record_path:  # the devnet's deployment, and its test coin, which anyone may mint (devnet only)
            record = json.loads((ROOT / record_path).read_text())
            coin, race_addr = record["coin"], record["race"]
            for who in ("reporter", "funder", "solver-a", "solver-b"):
                chain.send(KEYS["bot"], coin, "mint(address,uint256)", addr[who], str(1_000 * C))
        else:
            holders = "[" + ",".join(addr[w] for w in ("reporter", "funder", "solver-a", "solver-b")) + "]"
            out = chain.script(KEYS["bot"], LOOP, "deploy(address,address,address,address[])", addr["infrastructure"],
                               addr["insurance"], addr["founder"], holders)
            coin, race_addr = out["COIN"], out["RACE"]
        for who in ("reporter", "funder", "solver-a", "solver-b"):
            chain.send(KEYS[who], coin, "approve(address,uint256)", race_addr, str(2**256 - 1))
        race = Race(rpc, race_addr)
        chain_id, domain = rpc.chain_id(), race.domain_separator()
        oracle_set, quorum = race.oracle_keys(), race.quorum()
        if domain != crypto.domain_separator(chain_id, race_addr):
            problems.append("the node's EIP-712 domain differs from the contract's")
        say("deployed", f"Race {race_addr} on chain {chain_id}; oracle set {oracle_set}, quorum {quorum}")

        issue = topic(chain, chain.send(KEYS["reporter"], race_addr, "register(address)", coin),
                      "Registered(uint256,address)", 1)
        bounty = int(chain.script(KEYS["bot"], LOOP, "accept(address,uint256,uint256,bytes32)", race_addr, str(issue),
                                  str(120 * C), "0x" + secrets.token_hex(32))["BOUNTY"])
        chain.send(KEYS["funder"], race_addr, "pledge(uint256,address,uint256)", str(bounty), coin, str(100 * C))
        chain.warp(2)
        start = rpc.block()
        say("bounty", f"issue {issue} registered and accepted, bounty {bounty} funded")

        claims: dict[int, Claim] = {}  # what solvers reveal to the oracles off-chain
        for who, fix_file in (("solver-a", "bad_stats.py"), ("solver-b", "good_stats.py")):
            src, tree = fix_tree(work, who, fix_file)
            fix = crypto.keccak256(tree.encode())
            salt = secrets.token_bytes(32)
            sealed = "0x" + crypto.commitment(fix, salt, addr[who]).hex()
            chain.send(KEYS[who], race_addr, "attempt(uint256,address)", str(bounty), coin)
            sid = topic(chain, chain.send(KEYS[who], race_addr, "commit(uint256,bytes32,address)", str(bounty), sealed,
                                          coin), "Committed(uint256,uint256,address)", 2)
            claims[sid] = Claim(sid, bounty, addr[who], salt.hex(), tree, src,
                                issue="median() is wrong for an even count", diff=(BOT / "fixes" / fix_file).read_text(),
                                repo="local/sample", commit="Fix the median of an even count")
            say(who, f"sealed submission {sid} ({fix_file})")

        # One registered node per key of the deployed set, and one outside it.
        stores = work / "receipts"
        keyset = oracle_keys()
        if {k.address().lower() for k in keyset} != {a.lower() for a in oracle_set}:
            problems.append("the nodes' keys aren't the contract's oracle set")
        judges = {i: FakeJudge() for i in range(len(keyset))}
        nodes = [Node(k, judges[i], Store(stores / f"node{i}"), chain_id, race_addr) for i, k in enumerate(keyset)]
        stranger = int.from_bytes(secrets.token_bytes(32), "big") % crypto.N or 1
        outsider = Node(DevnetKeys(stranger) if record_path else LocalDevKeys(secret=stranger),
                        FakeJudge(), Store(stores / "outsider"), chain_id, race_addr)
        say("nodes", f"{len(nodes)} registered nodes ({'devnet keys' if record_path else 'public test keys'}) and one "
                     f"outside the set; quorum {quorum}")
        everyone = nodes + [outsider]

        seen = race.committed_since(start)
        say("watch", f"the nodes see {len(seen)} sealed submissions: {[s['submission'] for s in seen]}")
        bad_sid, good_sid = sorted(claims)

        def judge_round(sid: int, members: list[Node]) -> Round:
            onchain = race.submission(sid)
            rnd = Round(sid, oracle_set, quorum)
            for n in members:
                n.check(claims[sid], onchain["commitment"])
                rnd.seal(n.address, n.seal(sid))
            rnd.close_seals()
            for n in members:
                rnd.reveal(n.reveal(sid))
            return rnd

        # --- the bad fix: a forged relay first, then the honest quorum ---
        rnd = judge_round(bad_sid, everyone)
        refused = dict(rnd.refused)
        if refused.get(outsider.address) != "not in the contract's oracle set":
            problems.append(f"the outsider's reveal wasn't refused for its key: {rnd.refused}")
        # A quorum's worth of signatures, one of them from the outsider: refused for the key, not for the count.
        forgers = sorted([n.keys for n in nodes[:quorum - 1]] + [outsider.keys], key=lambda k: int(k.address(), 16))
        forged_signers = [k.address() for k in forgers]
        claim = claims[bad_sid]
        digest = result_digest(domain, claim, crypto.PASS, forged_signers)
        forged = ["0x" + k.sign(digest).hex() for k in forgers]
        try:
            relay(chain, race_addr, bad_sid, crypto.PASS, claim.fix, forged_signers,
                  crypto.result_nonce(bad_sid, bounty, claim.fix), forged)
            problems.append("the contract accepted a relay signed with a key outside the set")
        except RuntimeError as e:
            if "NotOracle" not in str(e):
                problems.append("the forged relay was refused, but not for its key (NotOracle)")
            say("forged relay", f"{len(forged)} signatures, one from outside the set: refused by the contract "
                                f"({'NotOracle' if 'NotOracle' in str(e) else 'reverted'})")
        decision = rnd.decide()
        if decision is None or decision.outcome != crypto.FAIL:
            problems.append(f"the bad fix's decision: {decision}")
        else:
            digest = result_digest(domain, claim, decision.outcome, decision.signers)
            sigs = {n.address: n.sign_result(bad_sid, decision.outcome, decision.signers, domain)
                    for n in nodes if n.address in decision.signers}
            relay(chain, race_addr, bad_sid, decision.outcome, claim.fix, decision.signers,
                  crypto.result_nonce(bad_sid, bounty, claim.fix), assemble(decision, sigs, digest, quorum))
            got = race.submission(bad_sid)["outcome"]
            say("bad fix", f"{len(decision.signers)} nodes agree it fails; relayed, on-chain outcome {got}")
            if got != crypto.FAIL:
                problems.append(f"the bad fix's on-chain outcome is {got}")

        # --- the good fix: node 1 lies, the quorum still passes it ---
        judges[1].lie = True
        rnd = judge_round(good_sid, everyone)
        decision = rnd.decide()
        if decision is None or decision.outcome != crypto.PASS or len(decision.dissent) != 1:
            problems.append(f"the good fix's decision: {decision}")
        else:
            claim = claims[good_sid]
            digest = result_digest(domain, claim, decision.outcome, decision.signers)
            sigs = {n.address: n.sign_result(good_sid, decision.outcome, decision.signers, domain)
                    for n in nodes if n.address in decision.signers}
            try:
                nodes[1].sign_result(good_sid, crypto.PASS, decision.signers, domain)
                problems.append("the lying node signed an outcome it didn't reach")
            except RefusedClaim:
                pass
            relay(chain, race_addr, good_sid, decision.outcome, claim.fix, decision.signers,
                  crypto.result_nonce(good_sid, bounty, claim.fix), assemble(decision, sigs, digest, quorum))
            got = race.submission(good_sid)["outcome"]
            say("good fix", f"passed {len(decision.signers)} to {len(decision.dissent)}; dissent logged from "
                            f"{decision.dissent[0].node} (receipt {decision.dissent[0].receipt_hash[:12]}…); "
                            f"on-chain outcome {got}")
            if got != crypto.PASS:
                problems.append(f"the good fix's on-chain outcome is {got}")

        # --- too few nodes, a tampered receipt, a changed verdict, an early reveal ---
        few = Round(good_sid, oracle_set, quorum)
        few.seal(nodes[0].address, nodes[0].seal(good_sid))
        few.close_seals()
        few.reveal(nodes[0].reveal(good_sid))
        if few.decide() is not None:
            problems.append("one node alone decided")
        tamper = Round(good_sid, oracle_set, quorum)
        tamper.seal(nodes[2].address, nodes[2].seal(good_sid))
        tamper.close_seals()
        r = nodes[2].reveal(good_sid)
        r2 = deepcopy(r)
        r2.receipt["tests"]["exit_code"] = 0 if r.receipt["tests"]["exit_code"] else 1
        if tamper.reveal(r2):
            problems.append("a tampered receipt was accepted")
        changed = deepcopy(r)
        changed.outcome = crypto.FAIL if r.outcome == crypto.PASS else crypto.PASS
        if tamper.reveal(changed):
            problems.append("a changed verdict was accepted")
        early = Round(good_sid, oracle_set, quorum)
        early.seal(nodes[0].address, nodes[0].seal(good_sid))
        if early.reveal(nodes[0].reveal(good_sid)):
            problems.append("a reveal before the seal phase closed was accepted")
        say("refusals", f"too few: nothing relayed; tampered receipt: {tamper.refused[0][1]}; changed verdict: "
                        f"{tamper.refused[1][1]}; early reveal: {early.refused[0][1]}")

        # --- a canary: the good fix's known outcome is pass ---
        board = Scoreboard()
        rnd = judge_round(good_sid, nodes)
        board.score(list(rnd.reveals.values()), crypto.PASS)
        say("canary", ", ".join(f"node{i} {board.accuracy(n.address):.0%}" for i, n in enumerate(nodes)))
        if board.accuracy(nodes[1].address) != 0.0 or board.accuracy(nodes[0].address) != 1.0:
            problems.append("the canary didn't score the lying node")

        receipts_written = sum(1 for _ in stores.rglob("*.json"))
        say("receipts", f"{receipts_written} receipts stored by hash under the nodes' stores")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    for p in problems:
        say("PROBLEM", p)
    say("result", "the oracle run passed" if not problems else f"{len(problems)} check(s) failed")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(run())
