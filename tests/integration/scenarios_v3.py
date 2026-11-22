"""#256's lettered v3 scenarios for #251's contract batch 4 (task 3.27; design L23, L24, L25), each set on its own
throwaway devnet deployed with the panel rules it needs. Run them with scripts/integration.sh --version 3 (after the
story, tests/integration/suite_v3.py) or one set alone with scripts/devnet-v3-e2e.sh --set <name>. No model call, no
network beyond this machine.

The harness is the story's (suite_v3.Net): real `NodeV3` objects with the fake judge, a fake repository host, the
fixes' tests a stand-in (exit 0 for a good fix, 1 for a bad one), and everything on-chain real. The windows are
production's (#251 L4: a seal window of 2 h, a k = 3 window of 24 h at level A, CHALLENGE_DEADLINE 120 h, RETRY_DELAY
and STUCK_GRACE 24 h); the run moves the chain's clock to the next deadline when no node has anything to do.

The sets (each a fresh devnet; `SETS` below):

- `launch`, the Sepolia record's rules (panel caps `launch`, kTop 3, `same`; #251 task 3.25): seven validators that
  share one operator account, one host and one TEE type, as the owner's launch validators do, bonded $250 each, each its
  own model family (`LAUNCH_FAMILIES`); the scenarios in the order u, w, v, x (v grows the network to 15 at its end).
  u  the launch settings: the rules read back from Panels, panels of 3 fill on that layout (a registration check, and
     a funded fix above k = 1's $50 limit once three solvers are active), the k = 3 window 24 h;
  v  panels of 3 at 7 validators: a verdict audited by one of the 4 outside its panel; a challenge and a failing-test
     dispute (D21) of right verdicts each judged by 3 fresh validators from those 4 and rejected; then at 15
     validators, with 12 outside, the same with the dispute of a wrong pass (a bad fix its lying panel passed),
     upheld, its reward paid from the bounty (lies only there: D20 unseats a reversed pass's families);
  g  (with `same`) is v's dispute: a fresh panel of the verdict's size;
  w  challenges end (L25): a waiting challenge redrawn at RETRY_DELAY after its validators un-pause, with no registry
     change; a challenge with no panel lapsing at CHALLENGE_DEADLINE, the stake and cover back, the verdict standing
     and its window resumed; a challenge panel whose seats all stay silent released after STUCK_GRACE, the challenge
     back to waiting and judged by a fresh panel.
  x  a lone wrong pass caught by its audit (#251 contract batch 5, #290): an outage leaves one validator drawable, so
     a bad fix gets k = 1 and its lone judge passes it; with three others back the verdict stays held (its two audits
     would leave its challenge one judge), its audits, drawn while it's held, catch it, and their challenge waits;
     once the rest are back three fresh validators reverse it, and only then does its window start, whole.
- `few-larger`, #132's defaults (every cap strict, kTop 7, `larger`) with one model family seated, and `few-same`, the
  launch's rules with one family: four validators, so a k = 3 verdict leaves one outside.
  f  a challenge that can't draw its fresh panel (5 with `larger`, 3 with `same`) is judged by D27's second draw of the
     verdict's size, the original judges allowed;
  g  a failing-test dispute of a passed fix: the same path, D27's second draw.

So f and g run under both `challengeSize` settings; a fresh larger panel (5 for a k = 3 verdict) is the story's step 8
(--heal), a fresh same-size one is v. What the node doesn't do yet is said at the end of each set: it doesn't run a
dispute's test (#132 task 10.5), so a dispute's panel judges the fix as a challenge's does."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

import suite_v3 as SV  # noqa: E402
from e2e_node_v3 import COIN, check, keys_for, simulator  # noqa: E402
from oracle import abi, crypto, node_v3, v2, v3  # noqa: E402
from oracle.rpc import Reverted, Rpc  # noqa: E402

HOUR, DAY = SV.HOUR, SV.DAY
BOND = 250  # the launch validators' bond (#251 L17)
GENESIS_HOST = "genesis-host"  # NodeV3Local's genesis registration: its host, its TEE type, its operator is its key
GENESIS_TEE = "intel-tdx"

# name -> the deployment's rules (scripts/devnet.sh deploy-v3's DEVNET_V3_*), the families priced at genesis, the
# validators' layout ("one": one operator account, one host, one TEE type; "spread": each its own) and how many
# validators beside the genesis one qualify before the scenarios
# The launch set's model families: one per validator, all priced at genesis (D19). v's wrong passes are reversed, which
# scores their judges' families down; once a family has SCORE_MIN_VERDICTS it is Scored, and more than SEAT_MARGIN below
# the best it is a contender, not drawn for counted panels (D20). Families shared with the liars would leave the 15
# validators too few seated families for a panel of 3 (seen: a fix drawn with k = 1).
LAUNCH_FAMILIES = ["fake"] + [f"fake-{i}" for i in range(1, 15)]
SETS = {
    "launch": {"caps": "launch", "kTop": 3, "size": "same", "families": LAUNCH_FAMILIES, "layout": "one",
               "validators": 6, "scenarios": "u w v x"},
    "few-larger": {"caps": "strict", "kTop": 7, "size": "larger", "families": ["fake"], "layout": "spread",
                   "validators": 3, "scenarios": "f g"},
    "few-same": {"caps": "launch", "kTop": 3, "size": "same", "families": ["fake"], "layout": "spread",
                 "validators": 3, "scenarios": "f g"},
}
RULES = {"strict": "strict", "launch": "off"}
CHALLENGE = "Drawn(uint256,uint256,uint8,uint256,bytes32)"


class ScenarioNet(SV.Net):
    """The story's network with the set's layout: who operates, hosts and attests each validator, and its family."""

    def __init__(self, rpc: Rpc, record: dict, work: Path, verbose: bool, spec: dict) -> None:
        super().__init__(rpc, record, work, verbose)
        self.spec = spec
        self.record = record
        self.genesis_key = crypto.checksum(record["genesis"])
        self.start = max(rpc.block() - 20, 0)

    def family_of(self, i: int) -> str:
        fams = self.spec["families"]
        return fams[i % len(fams)]

    def join(self, i: int, bond: int = BOND) -> SV.Node:
        name = f"v{i}"
        keys = keys_for(self.sim, name)
        self.fund(keys.address(), 5_000)
        one = self.spec["layout"] == "one"
        node_v3.register(self.chain, keys, SV.Wallet(self.rpc, keys.account_secret(), name), bond * COIN,
                         self.work / "receipts", log=self.log(name), proof="simulated", family=self.family_of(i),
                         host=GENESIS_HOST if one else f"host-{i}", image=v2.DEVNET_IMAGE,
                         tee_type=GENESIS_TEE if one else SV.TEES[i % 3],
                         operator=self.genesis_key if one else "", rad_node=self.rad_node(name))
        self.nodes[name] = self.make_node(name, self.family_of(i))
        return self.nodes[name]

    def join_next(self, bond: int = BOND) -> str:
        return super().join_next(bond)

    # ---------- helpers the scenarios share ----------

    def start_genesis(self) -> SV.Node:
        genesis = self.make_node("genesis", self.spec["families"][0], keeper=True)
        self.fund(genesis.address, 5_000)  # coins for its challenges and top-ups, as every validator's
        self.nodes["genesis"] = genesis
        return genesis

    def counted(self, s: int) -> bool:
        return self.chain.verdict(s)["status"] in (v3.WINDOW, v3.FINAL)

    def judged(self, s: int, what: str) -> None:
        """Counted, and its result taken by the race (a fix's bounty won, a check's fee paid)."""
        self.drive(lambda: self.counted(s) and self.chain.submission(s)["paid"], what, poke=True, explain=(s,))

    def drawn_then(self, s: int, lie: bool, what: str) -> list:
        """Submission `s` drawn, then judged; with `lie`, its drawn judges lie on it: every node lies on it until it is
        drawn (a seat is judged no earlier than the pass that draws it), then only its judges do, so its auditors and
        any challenge panel are honest. Returns its counted judges."""
        c = self.chain
        if lie:
            for node in self.nodes.values():
                node.lies.add(s)
        self.drive(lambda: c.verdict(s)["status"] in (v3.JUDGING, v3.HELD, v3.WINDOW, v3.FINAL), f"{what}: drawn",
                   poke=True, explain=(s,))
        judges = set(self.panel.drawn(s))
        if lie:
            for node in self.nodes.values():
                if node.address not in judges:
                    node.lies.discard(s)
        self.judged(s, f"{what}: judged")
        return self.panel.drawn(s)

    def right_registration(self, what: str) -> int:
        _, s = self.register_issue()
        self.drawn_then(s, False, what)
        check(self.chain.verdict(s)["pass"], f"{what}: registration check {s} passed by an honest panel of "
                                             f"{self.chain.verdict(s)['k']} ({self.named(self.panel.drawn(s))})")
        return s

    def final_registration(self) -> int:
        """A claimed registration, final: an issue a bounty can open on."""
        issue, s = self.register_issue()
        self.drive(lambda: self.chain.verdict(s)["status"] == v3.FINAL, "a registration final", poke=True,
                   explain=(s,))
        return issue

    def settled(self, s: int, what: str) -> dict:
        """Drives until the race settled `s`'s filed challenge; returns its panel, judges and outcome."""
        c = self.chain
        self.drive(lambda: not c.verdict(s)["challengeOpen"]
                   and self.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s) != [], what, poke=True,
                   explain=(s,))
        cpid, kc, log = SV.panels_of(self, s, v3.CHALLENGE)[-1]
        res = self.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s)[-1]
        upheld, now_pass, false_receipt = abi.decode(["bool", "bool", "bool"], abi.hexdata(res["data"]))
        return {"pid": cpid, "k": kc, "judges": c.judges(cpid), "upheld": upheld, "pass": now_pass,
                "second": bool(self.evs(c.panels, "SecondDraw(uint256,uint256)", s)), "ex": c.panel(cpid)["ex"]}

    def auditors(self, s: int) -> set:
        out = set()
        for pid, _, _ in SV.panels_of(self, s, v3.AUDIT):
            out |= {crypto.checksum("0x" + log["topics"][2][-40:])
                    for log in self.evs(self.chain.panels, v3.SEATED, pid)}
        return out

    def cover(self, s: int) -> int:
        """A challenge's stake and cover at the race (the stake configured, its panel's worst-case cost)."""
        c = self.chain
        repo = c.issue(c.issue_of(c.submission(s)))["repo"]
        return c.config()["challengeStake"] + c.deposit_for(s, repo, c.cover_judges())

    def file_challenge(self, who, s: int, label: str) -> int:
        """`who` (any account, not a validator) files a challenge of `s` with an evidence hash; returns what it holds."""
        before = self.chain.balance(who.address)
        who.send(self.chain.race, "challenge(uint256,bytes32)", s, crypto.keccak256(f"evidence {label}".encode()))
        return before - self.chain.balance(who.address)

    def capacity_now(self, name: str, checks: int) -> None:
        """Validator `name` sets its capacity (0 pauses it, #251 L16), by its operator's key when one account operates
        every validator; the change is in force CAP_DELAY blocks later, which are mined here."""
        c = self.chain
        node = self.nodes[name]
        signer = self.nodes["genesis"].wallet if self.spec["layout"] == "one" else node.wallet
        frm = c.capacity(node.address)["from"]
        if c.block() < frm:
            self.rpc.call("anvil_mine", [hex(frm - c.block() + 1)])
        signer.send(c.panels, "setCapacity(address,uint256)", node.address, checks)
        frm = c.capacity(node.address)["from"]
        self.rpc.call("anvil_mine", [hex(frm - c.block() + 1)])
        check(c.capacity(node.address)["checks"] == checks, f"{name}'s capacity is {checks} checks an hour now"
                                                            + (" (paused)" if checks == 0 else ""))

    def active_names(self) -> list:
        return [name for name, node in self.nodes.items() if self.drawable(node.address)]


def setup(n: ScenarioNet, out: dict) -> None:
    spec, c = n.spec, n.chain
    rules = c.panel_rules()
    want = {"operatorCap": RULES[spec["caps"]], "hostCap": RULES[spec["caps"]], "teeCap": RULES[spec["caps"]],
            "kTop": spec["kTop"], "challengeSize": spec["size"]}
    check(rules == want, f"Panels' rules, read back: {rules}")
    n.start_genesis()
    for _ in range(spec["validators"]):
        n.join_next()
    want_names = [f"v{i}" for i in range(1, spec["validators"] + 1)]
    started = time.time()
    made = n.grow(want_names, 12, f"{', '.join(want_names)} qualify", rounds=80)
    check(len(n.active()) == spec["validators"] + 1,
          f"{len(n.active())} validators active: the genesis one and {', '.join(want_names)}, qualified by their shadow "
          f"verdicts after {made} registration checks ({time.time() - started:,.0f} s)")
    out["setup"] = {"rules": rules, "active": len(n.active()), "checks": made}


# ---------- u: the launch settings ----------

def scenario_u(n: ScenarioNet, out: dict) -> None:
    print("\n== u. the launch settings: one operator account, one host, one TEE type; panels of 3 fill ==", flush=True)
    c, rpc = n.chain, n.rpc
    record = n.record
    live = c.liveness()
    check(record["windowsKind"] == "production" and live["challengeDeadline"] == 120 * HOUR,
          f"the windows are production's (the record's `windowsKind`), CHALLENGE_DEADLINE "
          f"{SV.hours(live['challengeDeadline'])}, RETRY_DELAY {SV.hours(live['retryDelay'])}, STUCK_GRACE "
          f"{SV.hours(live['stuckGrace'])}, MAX_REDRAWS {live['maxRedraws']}")
    vals = [c.validator(node.address) for node in n.nodes.values()]
    check(len({v["operator"].lower() for v in vals}) == 1 and len({v["host"] for v in vals}) == 1
          and len({v["teeType"] for v in vals}) == 1,
          f"all {len(vals)} validators share one operator account ({n.genesis_key[:10]}), one host and one TEE type "
          f"({GENESIS_TEE}), as the owner's launch validators do")
    s = n.right_registration("u")
    k1_limit = rpc.view(c.panels, "limitOf(uint256,uint8)", ["uint256"], 1, v3.LEVEL_A)[0]
    check(c.verdict(s)["k"] == 3,
          "k = 3: the panel of 3 filled on that layout with the caps `Off` (with `Strict` the one operator account "
          "holds every panel to k = 1, Foundry's DrawabilityV3 layout cases)")
    window3 = rpc.view(c.panels, "windowOf(uint256,uint8)", ["uint256"], 3, v3.LEVEL_A)[0]
    check(c.verdict(s)["finalAt"] - n.when(n.evs(c.panels, "WindowStarted(uint256,uint256)", s)[0]) == window3
          and window3 == 24 * HOUR, f"its window is CHALLENGE_WINDOW[3, level A]: {SV.hours(window3)}")
    # three active solvers by unfunded fixes, so pledges open (#251 L6), then a funded fix above k = 1's limit
    issues = [n.final_registration() for _ in range(5)]
    solvers = [n.solver, n.account("u solver 2"), n.account("u solver 3")]
    for k, (w, i) in enumerate(zip(solvers, issues)):
        n.merged_fix(w, n.open_bounty(i), i, f"u: an unfunded fix {k + 1}")
    book = crypto.checksum(rpc.view(c.race, "solverBook()", ["address"])[0])
    check(rpc.view(book, "activeCount()", ["uint256"])[0] == 3, "three solvers made active by merged unfunded fixes: "
                                                                "pledges open")
    # D29: a new identity claims at most $50; a merged funded fix of about $44 first lifts the solver's cap past $85
    b = n.open_bounty(issues[3])
    n.funder.send(c.race, "pledge(uint256,uint256)", b, 105 * COIN)
    n.merged_fix(n.solver, b, issues[3], "u: a funded fix of about $44")
    b = n.open_bounty(issues[4])
    n.funder.send(c.race, "pledge(uint256,uint256)", b, 200 * COIN)
    s_f, opening = n.submit_fix(b, issues[4], "u: a funded fix", good=True)
    judged = c.verdict(s_f)["bounty"]
    need = n.bond_for(judged)
    short = {name: c.validator(node.address)["bond"] for name, node in n.nodes.items()
             if c.validator(node.address)["bond"] < need}
    for name in short:  # a silence slash (5.00) can take a $250 bond under this bounty's: its operator tops it up
        n.top_up(name, need)
    check(judged > k1_limit and need <= BOND * COIN and n.eligible(judged) == len(n.active()),
          f"a funded fix sealed at {judged / COIN:,.2f}: above k = 1's limit ({k1_limit / COIN:,.2f}); the launch's $250 "
          f"bond covers it (a bond of {need / COIN:,.2f} is needed"
          + (f"; {', '.join(f'{k} at {v / COIN:,.2f}' for k, v in short.items())} topped up after a silence slash"
             if short else "") + ")")
    n.judged(s_f, "u: the funded fix judged")
    check(c.verdict(s_f)["k"] == 3 and c.verdict(s_f)["pass"] and n.bounty_state(b) == SV.WON,
          f"it was judged by a panel of 3 ({n.named(n.panel.drawn(s_f))}) and won bounty {b}: on the launch's layout "
          f"a ${judged / COIN:,.0f} bounty is judged (with `Strict`, k = 1 would leave it waiting forever)")
    n.solver.send(c.race, "claim(uint256,bytes32,bytes32,bytes32)", b, *opening)
    out["u"] = {"registration": s, "k": 3, "window": window3, "fix": s_f, "judgedAt": judged, "k1Limit": k1_limit}


# ---------- v: panels of 3, everything drawn from outside ----------

def audited_verdict(n: ScenarioNet, what: str, batch: int = 10, batches: int = 8) -> int:
    """Registration checks, `batch` at a time, until one's random audit falls due (AUDIT_RATE_BPS: one in ten) and is
    drawn. Returns that check."""
    c = n.chain

    def settled(s: int) -> bool:
        v = c.verdict(s)
        return v["status"] == v3.FINAL or (v["status"] == v3.WINDOW and v["auditDecided"]
                                           and v["auditsDrawn"] == v["auditsDue"])
    for _ in range(batches):
        regs = [n.register_issue()[1] for _ in range(batch)]
        n.drive(lambda: all(n.counted(s) and settled(s) for s in regs), f"{what}: a batch audited or final",
                poke=True)
        hit = [s for s in regs if c.verdict(s)["auditsDue"] > 0 and c.verdict(s)["auditsDrawn"] > 0]
        if hit:
            return hit[0]
    raise AssertionError(f"{what}: no random audit fell due in {batch * batches} verdicts")


def v_round(n: ScenarioNet, label: str, outside_want: int, out: dict, wrong: bool) -> None:
    """A verdict and its audit, a challenge and a failing-test dispute, each drawn from the validators outside the
    panel. With `wrong`, the dispute is of a wrong pass (a bad fix its lying panel passed) and reverses it; else both
    are of right verdicts and are rejected. A reversed pass scores its judges' families down, and once a family is
    Scored that makes it a contender, not drawn for counted or challenge panels (D20): so the launch set lies only in
    its last round, at 15 validators, and the earlier ones can't leave too few seated families to draw from."""
    c = n.chain
    res: dict = {}
    # a verdict and its audit
    s = audited_verdict(n, f"v{label}")
    judges, auditors = set(n.panel.drawn(s)), n.auditors(s)
    active = {n.nodes[x].address for x in n.active_names()}
    check(c.verdict(s)["k"] == 3 and len(active) - 3 == outside_want and auditors and not (auditors & judges)
          and auditors <= active,
          f"v at {len(active)}: a verdict of 3 (registration check {s}, {n.named(judges)}) was audited by "
          f"{n.named(auditors)}, one of the {outside_want} outside its panel")
    res["audit"] = {"submission": s, "auditors": len(auditors)}
    # a challenge of a right verdict by a validator outside its panel, judged by 3 fresh validators and rejected
    s = n.right_registration(f"v{label}")
    watcher = n.nodes[n.outside(s)[0]]
    # a rejected challenge's stake goes to the accused judges' operators (one account at the launch, L23)
    owed0 = {op: c.owed(op) for op in {c.validator(k)["operator"] for k in n.panel.drawn(s)}}
    check(watcher.challenge(s, force=True) is not None and c.verdict(s)["challengeOpen"],
          f"{n.name(watcher.address)}, outside its panel, challenged it")
    r = n.settled(s, f"v{label}: the challenge judged and settled")
    inside = set(n.panel.drawn(s)) | n.auditors(s)
    check(r["k"] == 3 and not r["second"] and not (set(r["judges"]) & inside) and set(r["judges"]) <= active
          and not r["upheld"] and r["pass"]
          and sum(c.owed(op) - v for op, v in owed0.items()) >= c.config()["challengeStake"],
          f"its challenge was judged by 3 fresh validators ({n.named(r['judges'])}) from the "
          f"{len(active - inside)} outside its panel and auditors (`same`: the verdict's size, not D4's 5; the "
          f"challenger may sit on it): rejected, its stake to the accused judges' operator")
    res["challenge"] = {"submission": s, "panel": r["pid"], "k": r["k"]}
    # a failing-test dispute (D21) of a funded fix's pass, judged by 3 fresh validators from the outside
    issue = n.final_registration()
    b = n.open_bounty(issue)
    n.funder.send(c.race, "pledge(uint256,uint256)", b, 50 * COIN)
    # a solver of its own: a new identity's claims are capped at $50 (D29), and this fix is about $21
    solver = n.account(f"v solver {label}")
    s, _ = n.submit_fix(b, issue, f"v{label}: {'a bad' if wrong else 'a good'} fix", good=not wrong, solver=solver)
    n.drawn_then(s, wrong, f"v{label}: the fix")
    check(c.verdict(s)["pass"] and c.verdict(s)["k"] == 3 and n.bounty_state(b) == SV.WON
          and c.bounty(b)["winner"] == s,
          (f"a bad fix (its tests fail) was passed by its lying panel of 3 ({n.named(n.panel.drawn(s))})" if wrong else
           f"a good fix was passed by a panel of 3 ({n.named(n.panel.drawn(s))})") + f" and won bounty {b}")
    disputer = n.account(f"disputer {label}")
    owed0 = c.owed(disputer.address)
    solver0 = c.owed(solver.address)
    held = n.chain.balance(disputer.address)
    disputer.send(c.race, "dispute(uint256,bytes32)", s, crypto.keccak256(f"a failing test {label}".encode()))
    held -= n.chain.balance(disputer.address)
    stake = abi.decode(["bytes32", "uint256"], abi.hexdata(n.evs(c.race, "Disputed(uint256,address,bytes32,uint256)",
                                                                 s)[-1]["data"]))[1]
    judged = c.submission(s)["judged"]
    check(stake == max(5 * COIN, judged // 10),
          f"a solver disputed it with a failing test (D21): stake {stake / COIN:,.2f}, the larger of $5 and 10 % of "
          f"the bounty ({judged / COIN:,.2f}), beside its panel's cover ({(held - stake) / COIN:,.2f})")
    r = n.settled(s, f"v{label}: the dispute judged and settled")
    inside = set(n.panel.drawn(s)) | n.auditors(s)
    fresh = r["k"] == 3 and not r["second"] and not (set(r["judges"]) & inside) and set(r["judges"]) <= active
    where = (f"its dispute was judged by 3 fresh validators ({n.named(r['judges'])}) from the "
             f"{len(active - inside)} outside")
    if wrong:
        rewards = n.evs(c.race, "DisputeRewarded(uint256,address,uint256)", s)
        reward = abi.decode(["uint256"], abi.hexdata(rewards[-1]["data"]))[0] if rewards else 0
        check(fresh and r["upheld"] and not r["pass"] and reward > 0
              and c.owed(disputer.address) - owed0 >= held + reward and n.bounty_state(b) == SV.OPEN,
              f"{where}, upheld: the fix fails, bounty {b} is open again, and the disputer is owed its stake and cover "
              f"back and a reward of {reward / COIN:,.2f} from the bounty (EVIDENCE_REWARD_BPS)")
    else:
        reward = 0
        check(fresh and not r["upheld"] and r["pass"] and c.owed(solver.address) - solver0 >= stake,
              f"{where}, rejected: the pass stands, and the stake went to the solver for its delay")
    res["dispute"] = {"submission": s, "panel": r["pid"], "stake": stake, "reward": reward, "upheld": r["upheld"]}
    out[f"v{label}"] = res


def scenario_v(n: ScenarioNet, out: dict) -> None:
    print("\n== v. panels of 3 at 7 validators: a verdict, its audit, a challenge and a test dispute each drawn from "
          "the 4 outside ==", flush=True)
    v_round(n, "7", 4, out, wrong=False)
    print("\n== v. the same at 15 validators, with 12 outside ==", flush=True)
    names = [n.join_next() for _ in range(8)]
    started = time.time()
    made = n.grow(names, 12, f"{', '.join(names)} qualify", rounds=120)
    check(len(n.active_names()) == 15, f"eight more validators qualified after {made} registration checks "
                                       f"({time.time() - started:,.0f} s): 15 active")
    v_round(n, "15", 12, out, wrong=True)
    print("  (g, with `same`: the dispute above, a fresh panel of the verdict's size; the node judges a dispute's "
          "panel as a challenge's: it doesn't run the disputed test yet, #132 task 10.5)", flush=True)


# ---------- w: challenges end ----------

def scenario_w(n: ScenarioNet, out: dict) -> None:
    print("\n== w. challenges end: a waiting challenge redrawn at RETRY_DELAY, a lapse at CHALLENGE_DEADLINE with the "
          "stake back, a stuck challenge panel released ==", flush=True)
    c = n.chain
    live = c.liveness()
    res: dict = {}
    challenger = n.account("w challenger")  # not a validator: every validator outside a panel can judge its challenge

    # 1. a waiting challenge, redrawn at its retry time after an un-pause (no registry change)
    s = n.right_registration("w1")
    outside = n.outside(s)
    paused = outside[:len(outside) - 2]  # two left: too few for a fresh panel of 3
    for name in paused:
        n.capacity_now(name, 0)
    n.file_challenge(challenger, s, "w1")
    n.drive(lambda: c.verdict(s)["challengeEpoch"] != 0, "w1: the challenge's draw tried", explain=(s,))
    v = c.verdict(s)
    waited_at, retry_at, epoch = c.now(), v["challengeRetryAt"], c.epoch()
    check(v["challengePid"] == 0 and retry_at - waited_at <= live["retryDelay"] and not n.evs(
        c.panels, "SecondDraw(uint256,uint256)", s),
          f"w1: a challenge of a verdict of 3 waits: {', '.join(paused)} paused (capacity 0), so only "
          f"{len(outside) - len(paused)} of the {len(outside)} outside could sit; its redraw is scheduled at "
          f"RETRY_DELAY ({SV.hours(live['retryDelay'])})")
    for name in paused:
        n.capacity_now(name, rpc_default(n))
    check(c.epoch() == epoch, "they un-paused: a capacity change isn't a registry change (the epoch is unchanged), "
                              "so before L25 nothing would have redrawn it")
    n.drive(lambda: c.verdict(s)["challengePid"] != 0, "w1: the waiting challenge redrawn", explain=(s,))
    cpid, kc, log = SV.panels_of(n, s, v3.CHALLENGE)[-1]
    drawn_at = n.when(log)
    check(drawn_at >= retry_at and c.epoch() == epoch and kc == 3,
          f"it was redrawn at its retry time ({SV.hours(drawn_at - waited_at)} after it began waiting), with no "
          f"registry change, by a fresh panel of 3 ({n.named(c.judges(cpid))})")
    r = n.settled(s, "w1: the challenge judged and settled")
    check(not r["upheld"] and c.verdict(s)["pass"], "the panel kept the verdict: the challenge was rejected")
    res["retry"] = {"submission": s, "waitedSeconds": drawn_at - waited_at}

    # 2. a challenge with no panel lapses at CHALLENGE_DEADLINE: the stake and cover back, the verdict standing
    s = n.right_registration("w2")
    outside = n.outside(s)
    paused = outside[:len(outside) - 2]
    for name in paused:
        n.capacity_now(name, 0)
    owed0 = c.owed(challenger.address)
    held = n.file_challenge(challenger, s, "w2")
    opened = n.when(n.evs(c.panels, "ChallengeOpened(uint256,address,bytes32)", s)[-1])
    frozen = c.verdict(s)["frozenLeft"]
    n.drive(lambda: n.evs(c.race, "ChallengeLapsed(uint256,address,uint256)", s) != [],
            "w2: the challenge lapsed and settled", explain=(s,))
    lapsed = n.evs(c.panels, "ChallengeLapsed(uint256,uint256)", s)[-1]
    back = abi.decode(["uint256"], abi.hexdata(n.evs(c.race, "ChallengeLapsed(uint256,address,uint256)", s)[-1]["data"]))[0]
    v = c.verdict(s)
    tries = len(n.evs(c.panels, "ChallengeWaits(uint256)", s))
    check(n.when(lapsed) >= opened + live["challengeDeadline"] and v["lapses"] == 1 and v["pass"]
          and v["status"] == v3.WINDOW and not v["challengeOpen"],
          f"w2: with {', '.join(paused)} paused throughout, the challenge waited ({tries} draws tried, one each "
          f"RETRY_DELAY) and lapsed {SV.hours(n.when(lapsed) - opened)} after it opened (CHALLENGE_DEADLINE "
          f"{SV.hours(live['challengeDeadline'])}): the verdict stands")
    check(back == held and c.owed(challenger.address) - owed0 == held
          and not n.evs(c.race, "ChallengeSettled(uint256,uint256,bool)", s),
          f"the race returned the challenger's stake and cover whole ({held / COIN:,.2f}), with no reward and nothing "
          f"to the accused judges")
    check(abs(v["finalAt"] - n.when(lapsed) - frozen) <= 60,
          f"its window resumed where it froze ({SV.hours(frozen)} left)")
    for name in paused:
        n.capacity_now(name, rpc_default(n))
    res["lapse"] = {"submission": s, "lapsedAfterSeconds": n.when(lapsed) - opened, "returned": back}

    # 3. a stuck challenge panel: every seat silent, nobody left to replace them; released, back to waiting, redrawn
    s = n.right_registration("w3")
    outside = n.outside(s)
    first: dict = {}

    def silent(pid: int) -> bool:  # every seat of the challenge's first panel, replacements too, stays silent
        p = c.panel(pid)
        if p["kind"] != v3.CHALLENGE or p["id"] != s:
            return False
        return first.setdefault("pid", pid) == pid
    for node in n.nodes.values():
        node.silent_on = silent
    n.file_challenge(challenger, s, "w3")
    n.drive(lambda: n.evs(c.panels, "ChallengeReleased(uint256,uint256,bool)", s) != [],
            "w3: the stuck challenge panel released", poke=True, explain=(s,))
    rel = n.evs(c.panels, "ChallengeReleased(uint256,uint256,bool)", s)[-1]
    stuck = first["pid"]
    lapsed_flag = abi.decode(["bool"], abi.hexdata(rel["data"]))[0]
    p = c.panel(stuck)
    missed = n.evs(c.panels, "Missed(uint256,address,bool)", stuck)
    check(int(rel["topics"][2], 16) == stuck and not lapsed_flag and n.when(rel) > p["revealBy"] + live["stuckGrace"]
          and len(missed) >= 3,
          f"w3: every seat of challenge panel {stuck} stayed silent ({len(missed)} misses, the replacements from its "
          f"sample silent too): {SV.hours(n.when(rel) - p['revealBy'])} after its reveal deadline (STUCK_GRACE "
          f"{SV.hours(live['stuckGrace'])}) it was released, before CHALLENGE_DEADLINE, so the challenge went back "
          f"to waiting")
    r = n.settled(s, "w3: the challenge redrawn, judged and settled")
    check(r["pid"] != stuck and r["k"] == 3 and not r["upheld"],
          f"it was drawn again (panel {r['pid']}, {n.named(r['judges'])}) and judged: the challenge ended")
    for node in n.nodes.values():
        node.silent_on = None
    res["stuck"] = {"submission": s, "released": stuck, "redrawn": r["pid"], "missed": len(missed)}
    out["w"] = res


# ---------- x: a lone wrong pass caught by its audit ----------

def scenario_x(n: ScenarioNet, out: dict) -> None:
    print("\n== x. a lone wrong pass caught by its audit: the hold keeps room for its audits, and the window waits for "
          "its challenge ==", flush=True)
    c, rpc = n.chain, n.rpc
    scores = crypto.checksum(rpc.view(c.panels, "scores()", ["address"])[0])
    names = n.active_names()
    # validators of seated families only (D20: v's reversed passes may have made their liars' families contenders,
    # which judge no counted, audit or challenge panel)
    def family(name: str) -> str:
        return n.spec["families"][0] if name == "genesis" else n.family_of(int(name[1:]))
    seated = [x for x in names if rpc.view(scores, "isSeated(bytes32)", ["bool"], v3.name_id(family(x)))[0]]
    check(len(seated) >= 7, f"{len(seated)} of the {len(names)} active validators are of seated families")
    lone, three = seated[0], seated[1:4]
    issue = n.final_registration()
    b = n.open_bounty(issue)  # unfunded: its check is judged all the same, at a bounty within k = 1's limit
    default = rpc_default(n)
    paused = [x for x in names if x != lone]
    for name in paused:
        n.capacity_now(name, 0)
    # the outage: only `lone` can be drawn, so k = 3 can't fill and the draw steps down to 1; it lies
    s, _ = n.submit_fix(b, issue, "x: a bad fix", good=False)
    for node in n.nodes.values():
        node.lies.add(s)
    n.drive(lambda: c.verdict(s)["status"] in (v3.HELD, v3.WINDOW, v3.FINAL), "x: the lone verdict counted",
            poke=True, explain=(s,))
    for node in n.nodes.values():
        node.lies.discard(s)
    v = c.verdict(s)
    lone_key = n.nodes[lone].address
    level = c.validator(lone_key)["level"]
    k1_limit = rpc.view(c.panels, "limitOf(uint256,uint8)", ["uint256"], 1, level)[0]
    check(v["k"] == 1 and v["pass"] and v["status"] == v3.HELD
          and [k.lower() for k in n.panel.drawn(s)] == [lone_key.lower()]
          and v["bounty"] <= k1_limit,
          f"with every validator but {lone} paused, a bad fix to a ${v['bounty'] / COIN:,.0f} bounty (k = 1's limit at "
          f"its level ${k1_limit / COIN:,.0f}) was judged by {lone} alone, who passed it: held, nobody could judge "
          f"its challenge")
    # three back: before batch 5 the hold ended here, its audits took two of the three, and their challenge lapsed
    for name in three:
        n.capacity_now(name, default)
    n.drive(lambda: c.verdict(s)["challengeOpen"] and c.verdict(s)["challengeEpoch"] != 0,
            "x: its audits drawn and their challenge tried", poke=True, explain=(s,))
    v = c.verdict(s)
    auditors = n.auditors(s)
    three_keys = {n.nodes[x].address for x in three}
    check(v["status"] == v3.HELD and auditors and auditors <= three_keys and v["challengePid"] == 0,
          f"{', '.join(three)} back: still held, since its {v['auditsDue']} audits would be drawn from those three and "
          f"each sits out of its challenge (the hold counts 3 + the audits still due); {n.named(auditors)} audited "
          f"it while it was held ({v['auditsDrawn']} of {v['auditsDue']} drawn so far), found the fix failing, and "
          f"the challenge waits with {len(three_keys - auditors)} validator(s) outside its panel and auditors")
    try:
        n.anyone.send(c.panels, "startWindow(uint256)", s)
        raise AssertionError("startWindow succeeded on a held verdict with its challenge open")
    except Reverted as e:
        check(True, f"its window can't start while the challenge is open (startWindow: {e.reason})")
    # the rest back: the challenge is redrawn at its retry time and three fresh validators reverse the pass
    for name in paused:
        if name not in three:
            n.capacity_now(name, default)
    n.drive(lambda: not c.verdict(s)["challengeOpen"], "x: the auditors' challenge judged", poke=True, explain=(s,))
    cpid, kc, _ = SV.panels_of(n, s, v3.CHALLENGE)[-1]
    res = n.evs(c.panels, "ChallengeResolved(uint256,uint256,bool,bool,bool)", s)[-1]
    upheld, now_pass, _ = abi.decode(["bool", "bool", "bool"], abi.hexdata(res["data"]))
    judges = set(c.judges(cpid))
    v = c.verdict(s)
    inside = {k.lower() for k in auditors | {lone_key}}
    check(kc == 3 and upheld and not now_pass and not v["pass"] and not ({k.lower() for k in judges} & inside)
          and v["lapses"] == 0,
          f"once the rest were back, three fresh validators ({n.named(judges)}: not {lone}, nor its auditors) "
          f"reversed it: the fix fails")
    n.drive(lambda: c.verdict(s)["status"] == v3.FINAL, "x: the reversed verdict final", poke=True, explain=(s,))
    started = n.evs(c.panels, "WindowStarted(uint256,uint256)", s)
    window = rpc.view(c.panels, "windowOf(uint256,uint8)", ["uint256"], 1, c.verdict(s)["level"])[0]
    check(len(started) == 1 and int(started[0]["blockNumber"], 16) >= int(res["blockNumber"], 16)
          and c.verdict(s)["finalAt"] - n.when(started[0]) == window and not c.verdict(s)["pass"],
          f"its window started only after the challenge closed, whole ({SV.hours(window)}), and it became final as a "
          f"fail: the wrong lone pass was never paid")
    n.drive(lambda: n.bounty_state(b) == SV.OPEN, "x: the bounty open again", poke=True, explain=(s,))
    check(True, f"bounty {b} is open again")
    out["x"] = {"submission": s, "lone": lone, "auditors": len(auditors), "challengePanel": cpid,
                "windowSeconds": window}


def rpc_default(n: ScenarioNet) -> int:
    return n.rpc.view(n.chain.panels, "CHECKS_DEFAULT()", ["uint256"])[0]


# ---------- f and g with one family: D27's second draw ----------

def scenario_f(n: ScenarioNet, out: dict) -> None:
    size = n.spec["size"]
    print(f"\n== f. a challenge, and D27's second panel with one family seated (challengeSize `{size}`) ==", flush=True)
    c = n.chain
    s = n.right_registration("f")
    k = c.verdict(s)["k"]
    need = n.rpc.view(c.panels, "challengeRange(uint256)", ["uint256", "uint256"], k)[1]
    outside = n.outside(s)
    check(k == 3 and len(outside) < need,
          f"a verdict of 3; one model family is seated, and only {len(outside)} validator(s) outside its panel, "
          f"short of the fresh panel of {need} a challenge needs with `{size}`")
    challenger = n.account("f challenger")
    owed0 = c.owed(challenger.address)
    held = n.file_challenge(challenger, s, "f")
    r = n.settled(s, "f: the challenge judged and settled")
    judges = set(n.panel.drawn(s))
    check(r["second"] and r["k"] == k and r["ex"] == 0,
          f"the fresh draw failed, so D27's second draw judged it: a panel of {r['k']}, the verdict's size, the "
          f"original judges allowed ({n.named(r['judges'])}; {len(set(r['judges']) & judges)} of them sat on the "
          f"verdict)")
    check(not r["upheld"] and c.verdict(s)["pass"] and c.owed(challenger.address) - owed0 < held,
          "it kept the verdict (the challenger was wrong): the stake went to the judges (D27 ends the wait; it "
          "corrects nothing a second vote of the same few wouldn't)")
    out[f"f-{size}"] = {"submission": s, "panel": r["pid"], "k": r["k"], "fresh": need, "outside": len(outside)}


def scenario_g(n: ScenarioNet, out: dict) -> None:
    size = n.spec["size"]
    print(f"\n== g. a failing-test dispute of a passed fix, with one family seated (challengeSize `{size}`) ==",
          flush=True)
    c = n.chain
    issue = n.final_registration()
    b = n.open_bounty(issue)  # unfunded: no pledge before three solvers are active (#251 L6), the dispute still runs
    s, _ = n.submit_fix(b, issue, "g: a good fix", good=True)
    n.drawn_then(s, False, "g: the fix")
    check(c.verdict(s)["pass"] and c.verdict(s)["k"] == 3, f"a good fix passed (submission {s}, a panel of 3)")
    disputer = n.account("g disputer")
    solver_owed = c.owed(n.solver.address)
    disputer.send(c.race, "dispute(uint256,bytes32)", s, crypto.keccak256(b"g: a failing test"))
    stake = abi.decode(["bytes32", "uint256"], abi.hexdata(n.evs(c.race, "Disputed(uint256,address,bytes32,uint256)",
                                                                 s)[-1]["data"]))[1]
    r = n.settled(s, "g: the dispute judged and settled")
    check(r["second"] and r["k"] == 3 and not r["upheld"] and c.verdict(s)["pass"]
          and c.owed(n.solver.address) - solver_owed >= stake,
          f"its dispute (stake {stake / COIN:,.2f}) couldn't draw a fresh panel either: D27's second draw of 3 "
          f"({n.named(r['judges'])}) kept the pass, and the stake went to the solver for its delay (D21)")
    out[f"g-{size}"] = {"submission": s, "panel": r["pid"], "stake": stake}


SCENARIOS = {"u": scenario_u, "v": scenario_v, "w": scenario_w, "x": scenario_x, "f": scenario_f, "g": scenario_g}


def run(rpc: Rpc, record: dict, work: Path, name: str, verbose: bool, report: str | None, only: str = "") -> int:
    started = time.time()
    spec = SETS[name]
    n = ScenarioNet(rpc, record, work, verbose, spec)
    out: dict = {"set": name, "chainId": n.chain.chain_id(), "windowsKind": record.get("windowsKind")}
    print(f"\n== the `{name}` set: panel caps {spec['caps']}, kTop {spec['kTop']}, challengeSize {spec['size']}, "
          f"{len(spec['families'])} model famil{'y' if len(spec['families']) == 1 else 'ies'}, the validators' "
          f"layout `{spec['layout']}`: scenarios {spec['scenarios']} ==", flush=True)
    setup(n, out)
    for letter in spec["scenarios"].split():
        if only and letter not in only.split(","):
            continue
        SCENARIOS[letter](n, out)
    out["chainSeconds"] = n.chain.now() - n.t0
    out["wallSeconds"] = round(time.time() - started)
    if report:
        Path(report).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\n{n.chain.panel_count()} panels, {len(n.active())} validators active, {SV.hours(out['chainSeconds'])} of "
          f"chain time in {out['wallSeconds']:,} s")
    print(f"scenarios-v3 {name}: all checks passed", flush=True)
    return 0


def prepare(name: str) -> int:
    """What scripts/devnet.sh deploy-v3 needs for set `name`: the genesis validator's throwaway key and attestation
    hash (as the story's), the families priced and the set's rules. Read by the calling script, never shown."""
    spec = SETS[name]
    genesis = keys_for(simulator(), "genesis")
    quote = genesis.quote(crypto.keccak256(b"genesis"))
    print(f"GENESIS=0x{genesis.account_secret():064x}")
    print(f"ATTESTATION=0x{crypto.keccak256(bytes.fromhex(quote.quote)).hex()}")
    print(f"FAMILIES={','.join(spec['families'])}")
    print(f"PANEL_CAPS={spec['caps']}")
    print(f"K_TOP={spec['kTop']}")
    print(f"CHALLENGE_SIZE={spec['size']}")
    return 0


def main(argv: list) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["prepare", "run", "sets"])
    ap.add_argument("--set", default="launch", choices=sorted(SETS))
    ap.add_argument("--rpc")
    ap.add_argument("--record")
    ap.add_argument("--work")
    ap.add_argument("--only", default="", help="some of the set's scenarios, comma-separated letters")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args(argv[1:])
    if a.command == "sets":
        print(" ".join(SETS))
        return 0
    if a.command == "prepare":
        return prepare(a.set)
    return run(Rpc(a.rpc, retries=2), json.loads(Path(a.record).read_text()), Path(a.work), a.set, a.verbose,
               a.report, a.only)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
