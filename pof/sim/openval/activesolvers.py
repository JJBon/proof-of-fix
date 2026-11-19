"""The minimum of active solvers before pledges (proof-of-fix#251 task 3.2, launch design L6; report
active-solvers-v1): the pledge gate on the chain's definition of "active", against report v5's attackers and a sybil
of three, under v5's recommended combination R(minus)+F.

The gate is `Params.ACTIVE_GATE` in `nodeposit.NDNet` (off by default): an identity is active while, within
`ACTIVE_WINDOW_WEEKS`, it has a fix whose passing verdict became final (funded or not) or an upheld failing-test
dispute; while fewer than `ACTIVE_SOLVERS_MIN` are active, an issue listed is left unfunded (its fix is still judged
and still counts) and v5's actors start no new claim. The world's fixes are written by the `n` honest solvers of the
repository (v5's active honest solvers, who also search every pass), so the count sees them.

`Sybil` is one party running `keep` identities that it keeps active with good fixes to issues it files itself (no
funding, so no reputation), paying the judges' fee on each, while one of v5's attackers works the issues the gate
lets in. Its twin is that attacker's twin with no identities kept (`twin_keeps`: the twin keeps the same identities
active, to separate the gain from cheating from the honest income a sybil's unlocking lets in).

    python3 -m pof.sim.openval.activesolvers --seed0 41 --seeds 40 --jobs 15 --out DIR
    python3 -m pof.sim.openval.activesolvers --render DIR

No model call: verdicts are replayed from data/judges/verdicts-v2.matrix.json (#160).
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Callable, Dict, List, Sequence, Tuple

from . import actors as A
from . import contenders as C
from . import nodeposit as N
from .evidence import P0
from .params import WEEK, Params, World

BASE = replace(P0, **N.REP, **N.FEE, **N.MINUS)  # report v5's recommendation: R(minus)+F, no deposit
WINDOWS = (6.0, 13.0, 26.0)  # ACTIVE_WINDOW_WEEKS: 13 proposed (L6); 6 and 26 as the task asks
ATT = ("B", "S", "T", "Tf", "L", "RS")  # report v5's six attackers under the cap
# The sybil's pre-registered rows: B, S, T and Tf against a twin that submits nothing and keeps no identity (the
# sybil pays for its identities); L and RS against a twin that keeps the same identities and farms ("Y2": their twins
# farm, so this separates cheating from the honest income an unlocked repository pays). YL and YRS against a twin
# that keeps nothing are reported apart: what opening a locked repository is worth, cheating or not.
SYBIL_KINDS = ("YB", "YS", "YT", "YTf", "Y2L", "Y2RS")
KEEP = 3  # the sybil's identities: the design's "sybil of three"
MARGIN_WEEKS = 2.0  # it renews an identity's pass once its last one is this close to leaving the window
CHEAP_EFFORT = 0.0  # what one of the sybil's fixes costs to write: a trivial fix to an issue it filed (worst case)
DEAR_EFFORT = 43.0  # ...in the option rows: half the median bounty ($86), as an honest fix (`World.effort`)
SEPOLIA_FEE = 40.0  # the judges' fee on Sepolia in test USDC (report faucet-spam-v1's upper value)
FAUCET_DRIP = 20.0  # USDC a faucet request (Circle's public faucet: one every 2 hours per address)
FLOWS = (30.0, 5.0, 1.0)  # the repository's listed issues a week in the unlock rows: v5's world, and two small ones
SEED0 = 41  # fresh seeds 41-80: every earlier round used 1-40


class Sybil(N.NDActor):
    """One party keeping `keep` identities active with good fixes to issues it files itself (unfunded: no bounty and
    no reputation), each costing `effort` to write and the judges' fee to judge, renewed when the last pass is within
    `margin` weeks of leaving the window or was rejected; meanwhile `inner`, one of v5's attackers of the same party,
    works the issues the gate lets in. Twin: `inner`'s twin, no identity kept (`twin_keeps`: the same identities kept
    by the twin too)."""
    TAG = 8

    def __init__(self, inner: N.NDActor, keep: int = KEEP, effort: float = CHEAP_EFFORT,
                 margin: float = MARGIN_WEEKS, twin_keeps: bool = False):
        super().__init__(inner.honest, inner.w)
        self.inner, self.keep, self.effort, self.margin = inner, keep, effort, margin
        self.twin_keeps = twin_keeps
        self.name, self.party = inner.name, inner.party
        self.count = inner.count  # one party: one tally
        self.pending: Dict[int, object] = {}
        self.tallied: set = set()

    def world(self) -> World:
        return self.inner.world()

    def genesis(self, net):
        return self.inner.genesis(net)

    def setup(self, net: N.NDNet) -> None:  # type: ignore[override]
        self.inner.setup(net)  # the market and the attacker's slots

    def on_tick(self, net: N.NDNet) -> None:  # type: ignore[override]
        self.inner.on_tick(net)
        if not self.honest or self.twin_keeps:
            self.renew(net)

    def withdraws(self, net, sub) -> bool:
        return self.inner.withdraws(net, sub)

    def renew(self, net: N.NDNet) -> None:
        due = (net.p.ACTIVE_WINDOW_WEEKS - self.margin) * WEEK
        for j in range(self.keep):
            s = self.pending.get(j)
            if s is not None and s.final is not None and j not in self.tallied:  # type: ignore[attr-defined]
                self.tallied.add(j)
                self.count["keeper_passed"] += bool(s.final)  # type: ignore[attr-defined]
            if s is not None and s.final is None and s.state not in ("withdrawn", "refused"):  # type: ignore[attr-defined]
                continue
            last = net.last_active.get((self.party, f"y{j}"))
            if last is not None and net.t - last < due:
                continue
            self.pending[j] = net.submit(net.t, 0.0, True, self.name, self.party, ident=f"y{j}",
                                         key=60_000_000 + self.count["keeper_fixes"], effort=self.effort)
            self.tallied.discard(j)
            self.count["keeper_fixes"] += 1
            self.count["keeper_effort"] += self.effort


class Nobody(N.BadFix):
    """No attacker: the repository's honest solvers alone (the unlock rows)."""

    def __init__(self, honest: bool = True, w: World = N.WORLD):
        super().__init__(True, w)


# ---------- the rows ----------

Row = Tuple[str, str, str, int, str, str, World, Params, dict]  # table, seat, pool, n, kind, label, world, params, opts


def gated(window: float, **kw) -> Params:
    return replace(BASE, ACTIVE_GATE=True, ACTIVE_WINDOW_WEEKS=window, **kw)


def wlabel(window: float) -> str:
    return f"window {window:g} weeks"


def ref_rows() -> List[Row]:
    """Report v5's R(minus)+F rows with no gate, on the fresh seeds: the reference every gated row is read against."""
    return [("ref", seat, pool, n, k, "gate off", N.world(pool, seat, n), BASE, {})
            for pool, _ in N.POOLS for seat, _ in N.SEATS for n in N.SOLVERS for k in ATT]


def gate_rows() -> List[Row]:
    """The gate on, the repository's solvers counted, each window; v5's six attackers."""
    return [("gate", seat, pool, n, k, wlabel(win), N.world(pool, seat, n), gated(win), {})
            for win in WINDOWS for pool, _ in N.POOLS for seat, _ in N.SEATS for n in N.SOLVERS for k in ATT]


def anyone_rows() -> List[Row]:
    """The gate on with the world's contenders' upheld tests counted too (ACTIVE_COUNTS "anyone"), 13 weeks."""
    return [("anyone", seat, pool, n, k, wlabel(13.0), N.world(pool, seat, n), gated(13.0, ACTIVE_COUNTS="anyone"), {})
            for pool, _ in N.POOLS for seat, _ in N.SEATS for n in N.SOLVERS for k in ATT]


def sybil_rows() -> List[Row]:
    """The sybil of three (trivial fixes, $0 to write) with each of v5's attackers, each window; the long con and the
    reputation sale also against a twin that keeps the same identities and farms ("Y2")."""
    return [("sybil", seat, pool, n, y + k, wlabel(win), N.world(pool, seat, n), gated(win),
             dict(keep=KEEP, twin_keeps=y == "Y2"))
            for win in WINDOWS for pool, _ in N.POOLS for seat, _ in N.SEATS for n in N.SOLVERS
            for y, k in [("Y", k) for k in ATT] + [("Y2", "L"), ("Y2", "RS")]]


OPTIONS: Tuple[Tuple[str, dict, dict], ...] = (
    ("its fixes cost $43 to write", {}, dict(keep=KEEP, effort=DEAR_EFFORT)),
    ("minimum 5 (it keeps 5)", dict(ACTIVE_SOLVERS_MIN=5), dict(keep=5)),
    ("minimum 10 (it keeps 10)", dict(ACTIVE_SOLVERS_MIN=10), dict(keep=10)),
    ("deposit 1,000 all year", dict(SOLVER_DEPOSIT_BPS=1_000), dict(keep=KEEP)),
    ("deposit 2,500 all year", dict(SOLVER_DEPOSIT_BPS=2_500), dict(keep=KEEP)))


def option_rows() -> List[Row]:
    """The design's options against the sybil (L6's risk), 1 honest solver, 13 weeks: dearer fixes, a higher minimum,
    a deposit while small (here all year: a "small" read from the same count is met by the sybil too)."""
    return [("options", seat, pool, 1, k, label, N.world(pool, seat, 1), gated(13.0, **kw),
             dict(opts, twin_keeps=k.startswith("Y2")))
            for label, kw, opts in OPTIONS for pool, _ in N.POOLS for seat, _ in N.SEATS for k in SYBIL_KINDS]


def unlock_rows() -> List[Row]:
    """Honest solvers only: when a fresh repository first takes a pledge, and the honest fixes left unpaid until then,
    by the repository's flow of issues, its solvers, the window and whose disputes count."""
    return [("unlock", seat, "hidden", n, "H", f"{wlabel(win)}; {flow:g} a week; {counts}",
             N.world("hidden", seat, n, subs_week=flow), gated(win, ACTIVE_COUNTS=counts), {})
            for counts in ("repository", "anyone") for flow in FLOWS for win in WINDOWS for seat, _ in N.SEATS
            for n in N.SOLVERS]


TABLES: Dict[str, Callable[[], List[Row]]] = {"ref": ref_rows, "gate": gate_rows, "anyone": anyone_rows,
                                              "sybil": sybil_rows, "options": option_rows, "unlock": unlock_rows}


def make(kind: str, w: World, opts: dict) -> Callable[[bool], N.NDActor]:
    if kind == "H":
        return lambda h: Nobody(True, w)
    if kind.startswith("Y"):
        inner = N.make(kind.lstrip("Y2"), w)
        return lambda h: Sybil(inner(h), **opts)
    return N.make(kind, w)


def _job(job) -> Dict[str, object]:
    table, i, seed = job
    _, seat, pool, n, k, label, w, p, opts = TABLES[table]()[i]
    if k == "H":  # one run: no attacker, no twin
        a = Nobody(True, w)
        net = N.run(a, seed, p)
        m = N.party_metrics(net, a)
        return {"diffs": [0.0], **m}
    return N.against_twin(make(k, w, opts), [seed], p)


def key_of(row: Row) -> str:
    return "|".join((row[0], row[1], row[2], str(row[3]), row[4], row[5]))


def run_rows(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = TABLES[table]()
    res = C._map(_job, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    return [(key_of(rows[i]), N._gather(res[i * len(seeds):(i + 1) * len(seeds)])) for i in range(len(rows))]


# ---------- the report's tables ----------

Res = Dict[str, object]
SEAT = dict(N.SEATS)
POOL = dict(N.POOLS)
CONDS = [(s, n) for s, _ in N.SEATS for n in N.SOLVERS]
COND_HEAD = [f"{SEAT[s]}, {n} solver{'s' if n > 1 else ''}" for s, n in CONDS]
NAMES = {"B": "B, one identity", "S": "S, free identities", "T": "T, retrier", "Tf": "Tf, retrier, new identities",
         "L": "L, long con", "RS": "RS, reputation sale"}


def wins(r: Res) -> bool:
    return r["diff"] - 2 * r["se"] > 0  # type: ignore[operator]


def cell(r: Res) -> str:
    s = f"{r['diff']:+,.0f} ± {2 * r['se']:,.0f}"  # type: ignore[str-format]
    return f"**{s}**" if wins(r) else s


def _m(r: Res, k: str) -> float:
    xs = [x for x in r.get(k, []) if x == x]  # type: ignore[union-attr]
    return mean(xs) if xs else float("nan")


def _pm(r: Res, k: str, nd: int = 0) -> str:
    xs = [x for x in r.get(k, []) if x == x]  # type: ignore[union-attr]
    if not xs:
        return "never"
    return f"{mean(xs):,.{nd}f} ± {2 * A._se(xs):,.{nd}f}"


def _table(head: Sequence[str], lines: Sequence[Sequence[str]]) -> str:
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(x) + " |" for x in lines])


def _load(folder: str, name: str) -> Dict[Tuple[str, ...], Res]:
    path = Path(folder, f"{name}.json")
    return {tuple(k.split("|")): r for k, r in json.loads(path.read_text())} if path.exists() else {}


def holds_table(tabs: Dict[str, Dict[Tuple[str, ...], Res]]) -> str:
    """Per table and label, per condition: does every attacker (both kinds of bad fix) stay at or below its twin?"""
    lines = []
    for table, part, kinds in (("ref", "", ATT), ("gate", "", ATT), ("anyone", "", ATT), ("sybil", "", SYBIL_KINDS),
                               ("sybil", " (L, RS: twin keeps nothing)", ("YL", "YRS")), ("options", "", SYBIL_KINDS)):
        rows = tabs.get(table, {})
        for label in dict.fromkeys(k[5] for k in rows):
            out = [f"{table}: {label}{part}"]
            for seat, n in CONDS:
                cells = [(r, k[4], k[2]) for k, r in rows.items() if k[5] == label and k[1] == seat and int(k[3]) == n
                         and k[4] in kinds]
                if not cells:
                    out.append("–")
                    continue
                bad = sorted(((r["diff"], kind, pool) for r, kind, pool in cells if wins(r)), reverse=True)
                out.append("holds" if not bad else
                           f"no: {', '.join(dict.fromkeys(k for _, k, _ in bad))} (up to {bad[0][0]:+,.0f})")
            lines.append(out)
    return _table(["Table: rows"] + COND_HEAD, lines)


def attacker_table(rows: Dict[Tuple[str, ...], Res], label: str) -> str:
    lines = []
    kinds = list(dict.fromkeys(k[4] for k in rows if k[5] == label))
    for kind in kinds:
        for pool, pname in N.POOLS:
            out = [NAMES[kind.lstrip("Y2")] + (" with the sybil" if kind.startswith("Y") else "")
                   + (" (its twin keeps the identities too)" if kind.startswith("Y2") else ""), pname]
            for seat, n in CONDS:
                r = next((r for k, r in rows.items() if k[1] == seat and k[2] == pool and int(k[3]) == n
                          and k[4] == kind and k[5] == label), None)
                out.append(cell(r) if r is not None else "–")
            lines.append(out)
    return _table(["Attacker", "Bad fixes"] + COND_HEAD, lines)


def unlock_table(rows: Dict[Tuple[str, ...], Res]) -> str:
    head = ["Counted", "Issues a week", "Window", "Seated", "Honest solvers", "First pledge (week)", "Never in the year",
            "Pledges taken (% of the year)", "Shut again (a year)", "Funding refused (%)", "Honest good fixes unpaid",
            "…their bounties ($)"]
    lines = []
    for k, r in rows.items():
        win, flow, counts = k[5].split("; ")
        lines.append([counts, flow.split()[0], win.split()[1], SEAT[k[1]], k[3], _pm(r, "gate_open_week", 1),
                      f"{_m(r, 'gate_never'):.0f} %", _pm(r, "gate_open_share", 1), _pm(r, "gate_shut_again", 1),
                      _pm(r, "funding_refused", 1), _pm(r, "honest_unpaid", 1), _pm(r, "honest_unpaid_value")])
    return _table(head, lines)


def sybil_cost_table(rows: Dict[Tuple[str, ...], Res], fee: float) -> str:
    """What keeping the identities active cost the sybil, by window (1 honest solver; all attackers and seats)."""
    head = ["Rows", "Its fixes a year", "Of them passed", "Mainnet-like fees ($ a year: judges' fee $%.2f + $0.50)" % fee,
            "Sepolia at $40 a fix: faucet requests a year", "First pledge (week)", "Pledges taken (% of the year)"]
    groups: Dict[str, List[Res]] = {}
    for k, r in rows.items():
        if int(k[3]) == 1:
            groups.setdefault(f"{k[0]}: {k[5]}", []).append(r)
    lines = []
    for g, rs in groups.items():
        fixes = mean(_m(r, "keeper_fixes") for r in rs)
        passed = mean(_m(r, "keeper_passed") for r in rs)
        lines.append([g, f"{fixes:.1f}", "–" if passed != passed else f"{passed:.1f}", f"{fixes * (fee + 0.5):,.0f}",
                      f"{fixes * SEPOLIA_FEE / FAUCET_DRIP:.0f}", f"{mean(_m(r, 'gate_open_week') for r in rs):.1f}",
                      f"{mean(_m(r, 'gate_open_share') for r in rs):.1f}"])
    return _table(head, lines)


def render(folder: str) -> str:
    tabs = {t: _load(folder, t) for t in TABLES}
    out = ["### Does every attacker stay at or below its twin? (both kinds of bad fix)", "",
           holds_table(tabs), ""]
    for table, title in (("ref", "No gate (report v5's R(minus)+F, fresh seeds)"), ("gate", "The gate on"),
                         ("anyone", "The gate on, contenders' tests counted"), ("sybil", "The sybil of three"),
                         ("options", "The design's options against the sybil (1 honest solver, 13 weeks)")):
        rows = tabs[table]
        for label in dict.fromkeys(k[5] for k in rows):
            out += [f"### {title}: {label} ($ a year against the twin, ± 2 SE; bold: above its twin)", "",
                    attacker_table(rows, label), ""]
    if tabs["sybil"] or tabs["options"]:
        out += ["### What the sybil's identities cost it (1 honest solver)", "",
                sybil_cost_table({**tabs["sybil"], **tabs["options"]}, N.JUDGE_FEE), ""]
    if tabs["unlock"]:
        out += ["### A fresh repository with honest solvers only", "", unlock_table(tabs["unlock"]), ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.activesolvers")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--seed0", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated: " + ", ".join(TABLES))
    ap.add_argument("--out", default="", help="write each table's raw results to OUT/<table>.json")
    ap.add_argument("--render", default="", help="print the report's tables from the raw results in this folder")
    a = ap.parse_args(argv)
    if a.render:
        print(render(a.render))
        return 0
    seeds = list(range(a.seed0, a.seed0 + a.seeds))
    for name in [x for x in a.only.split(",") if x] or list(TABLES):
        t0 = time.time()
        data = run_rows(name, seeds, a.jobs)
        if a.out:
            Path(a.out, f"{name}.json").write_text(json.dumps(data))
        print(f"{name}: {len(data)} rows done in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
