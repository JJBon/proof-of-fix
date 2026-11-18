"""Validators choose repositories: allow and deny lists, a repository's minimum of eligible validators, and a bounty
cap scaled to their stake (proof-of-fix#252; design D33, D34, PROPOSED; report measured-v6, simulation B).

The owner's decisions (#252): enclaves only (proof levels A and B, no level C: no answer shopping and no fabricated
receipt unless a TEE type is broken); allow lists and deny lists, both respected everywhere (first-round panels,
shadows, audits, challenges, appeals): a validator is never drawn for a repository it denied or did not allow. A
repository with too few eligible validators across TEE types gets no bounties.

Each rule is a named switch of `Params`, off by default and read only by `ChoiceNet` (a `capacity.CapNet`):
- `REPO_LISTS` (D33): every draw's pool (`Net.eligible`, and the shadows' candidates) keeps only the validators that
  allow the submission's repository (no allow list: every repository) and don't deny it;
- `REPO_MIN_ELIGIBLE` (D34): a submission to a repository is listed (judged, its bounty offered) only while at least
  that many validators are eligible for it, counted with at most (REPO_MIN_ELIGIBLE - 1) // 2 of any one TEE type;
  otherwise it is not listed, and costs nobody anything;
- `REPO_STAKE_X` (D34's option): a listed bounty is capped at REPO_STAKE_X x the bonded stake of the repository's
  eligible validators outside the TEE type that holds the most of it.

The world: 28 honest validators (Opus 5.5 seated alone, report v5's base), every one bonded $1,250, no newcomers;
10 repositories; repository 0, the target, is allowed by `target_honest` of them (the genesis first, then in registry
order, so their TEE types rotate) and denied by the others.

The attackers (`RepoAttacker`), each against its twin on the same seeds (the same validators judging honestly, and no
bad fixes):
- "silence": `nodes` validators allow-list the target only and never answer on it (counted, audit or challenge);
  they shadow-judge honestly, so a suspended one qualifies again. The protocol replaces each (slashing $5) and the
  reveal-rate floor suspends it;
- "tee": `nodes` validators of one TEE type whose attestation is broken (ASSUMED secret all year) pass their
  accomplice's bad fixes, 5 a week. They fake the model's answer only, so a re-run proves nothing (a re-run of the
  tests would show a faked test result, a dominated strategy); as auditors and challenge judges of those fixes they
  defend them; everywhere else they judge honestly. "one": all of them allow-list the target, where the accomplice
  submits; "spread": each allow-lists one repository in turn, and the accomplice submits to theirs at random.

    python3 -m pof.sim.openval.choice [--seeds 40] [--jobs 15] [--out DIR] [--render DIR]
"""

from __future__ import annotations

import argparse
import random
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from statistics import mean, median
from typing import Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

from . import actors as A
from . import capacity as K
from . import contenders as C
from . import nodeposit as N
from . import panels as D
from .evidence import P0
from .net import ACTOR_VID, ISSUE, Act, Honest, Sub
from .params import DAY, WEEK, WORLD, Params, World

TARGET = 0
T_CHOICE = 0xC401CE


class ChoiceNet(K.CapNet):
    """`CapNet` with validators' allow and deny lists, a repository's minimum and its stake cap."""

    def __init__(self, seed: int, p: Params, w: World, actors: Sequence[object] = (),
                 target_honest: Optional[int] = None, **kw):
        self.allow: Dict[int, Optional[FrozenSet[int]]] = {}
        self.deny: Dict[int, FrozenSet[int]] = {}
        self.unlisted: List[Sub] = []
        self.target_honest = target_honest
        super().__init__(seed, p, w, actors, **kw)

    def _start(self) -> None:
        super()._start()
        if self.target_honest is not None:  # the honest validators (registry order) that allow the target
            honest = [v for v in self.reg.validators.values() if v.vid < ACTOR_VID]
            for i, v in enumerate(honest):
                if i >= self.target_honest:
                    self.deny[v.vid] = frozenset((TARGET,))

    def allowed(self, v, r: int) -> bool:
        a = self.allow.get(v.vid)
        return (a is None or r in a) and r not in self.deny.get(v.vid, ())

    def eligible(self, sub: Sub, exclude=frozenset(), family_ok=None):
        out = super().eligible(sub, exclude, family_ok)
        if self.p.REPO_LISTS and sub.tier == ISSUE:
            r = self.repo_of(sub)
            out = [v for v in out if self.allowed(v, r)]
        return out

    def shadow_candidates(self, sub: Sub):
        out = super().shadow_candidates(sub)
        if self.p.REPO_LISTS and sub.tier == ISSUE:
            r = self.repo_of(sub)
            out = [v for v in out if self.allowed(v, r)]
        return out

    def counted_eligible(self, sub: Sub) -> int:
        """D34: the eligible validators, at most (REPO_MIN_ELIGIBLE - 1) // 2 of one TEE type counted."""
        per = max(1, (self.p.REPO_MIN_ELIGIBLE - 1) // 2)
        by = Counter(v.tee for v in self.eligible(sub))
        return sum(min(n, per) for n in by.values())

    def stake_cap(self, sub: Sub) -> float:
        by: Dict[str, float] = defaultdict(float)
        for v in self.eligible(sub):
            by[v.tee] += v.bond
        if not by:
            return 0.0
        return self.p.REPO_STAKE_X * (sum(by.values()) - max(by.values()))

    def _arrive(self, sub: Sub) -> None:
        p = self.p
        if sub.tier == ISSUE and (p.REPO_MIN_ELIGIBLE or p.REPO_STAKE_X):
            self.repo_of(sub)
            cap = self.stake_cap(sub) if p.REPO_STAKE_X else float("inf")
            if (p.REPO_MIN_ELIGIBLE and self.counted_eligible(sub) < p.REPO_MIN_ELIGIBLE) or cap < 1.0:
                sub.state = "unlisted"  # no bounty offered: nothing judged, nothing charged
                self.unlisted.append(sub)
                self.stats["unlisted"] += 1
                return
            if sub.bounty > cap:
                self.stats["stake_capped"] += 1
                sub.bounty = round(cap, 2)
        super()._arrive(sub)


# ---------- the attackers' behaviours ----------

class Silence(Honest):
    """Never answers a counted draw, an audit or a challenge panel; shadow-judges honestly (to qualify again)."""

    def counted(self, net, sub: Sub, v) -> Act:
        net.stats["silences"] += 1
        return Act(False, False)

    def audit(self, net, sub: Sub, v) -> Act:
        return Act(False, False)

    def challenge(self, net, ch, v) -> Act:
        return Act(False, False)


class Fabricator(Honest):
    """A broken TEE type: passes its party's fixes with a faked model answer (nothing a re-run can prove), and defends
    them as an auditor or a challenge judge; judges everything else honestly."""

    def __init__(self, party: str):
        self.party = party

    def counted(self, net, sub: Sub, v) -> Act:
        if sub.party != self.party:
            return super().counted(net, sub, v)
        net.stats["fabricated"] += not net.honest_vote(sub, v, 1)
        return Act(True, True, True, faked=False)

    def audit(self, net, sub: Sub, v) -> Act:
        if sub.party != self.party:
            return super().audit(net, sub, v)
        return Act(True, True, bool(sub.verdict))

    def challenge(self, net, ch, v) -> Act:
        if ch.sub.party != self.party:
            return super().challenge(net, ch, v)
        return Act(True, True, bool(ch.sub.standing))


class RepoAttacker(N.NDActor):
    """`nodes` validators (each its own declared operator, on rotating hosts, bonded $1,250, active from the start)
    and, for "tee", an accomplice submitting bad fixes at `per_week`. `form`: "one" (all allow the target only),
    "spread" (each allows one repository in turn), "open" (no lists: every repository). With `nodes` 0 nothing (the
    world without the attacker)."""
    TAG = 31
    name = party = "repo attacker"

    def __init__(self, honest: bool = False, w: World = WORLD, kind: str = "tee", nodes: int = 3, form: str = "one",
                 tee: str = "tdx", per_week: float = 5.0, nodes_honest: bool = False):
        super().__init__(honest, w, per_week if kind == "tee" and nodes else 0.0)
        self.kind, self.n, self.form, self.tee = kind, nodes, form, tee
        self.nodes_honest = nodes_honest  # "the accomplice alone": its validators judge honestly, it still submits
        self.repos: List[int] = []

    def start(self, net: ChoiceNet) -> None:  # type: ignore[override]
        w = net.w
        beh = Silence() if self.kind == "silence" else Fabricator(self.party)
        for i in range(self.n):
            tee = self.tee if self.kind == "tee" else w.tees[i % len(w.tees)]
            v = net.register_actor(i, self.party, 1250.0, w.hosts[i % len(w.hosts)], tee, w.families[0],
                                   f"{self.party}-op-{i}", None if self.nodes_honest else self.behaviour(beh),
                                   active=True)
            if self.form == "one":
                net.allow[v.vid] = frozenset((TARGET,))
            elif self.form == "spread":
                net.allow[v.vid] = frozenset((i % max(1, w.repos),))
        self.repos = sorted({r for vid, a in net.allow.items() if vid >= ACTOR_VID and a for r in a}) or [TARGET]

    def slot(self, net: ChoiceNet, i: int) -> None:  # type: ignore[override]
        xs = self.seen(net, self.TAG, i)
        if self.honest:
            return
        rng = random.Random(D.h(net.seed, T_CHOICE, i))
        r = self.repos[rng.randrange(len(self.repos))]
        ident = None
        b: Optional[float] = rng.choice(xs)
        if net.p.REP_CAP:  # under D29: a fresh identity each fix, the largest listed issue it may claim
            ident = f"f{i}"
            b = self.pick(xs, net.room((self.party, ident)), "largest", rng)
            if b is None:
                return
        s = net.submit(net.t, b, False, self.name, self.party, ident=ident, key=70_000_000 + i, repo=r)
        self.subs.append(s)
        self.count["submitted"] += 1


# ---------- what is measured ----------

def metrics(net: ChoiceNet, a: RepoAttacker) -> Dict[str, float]:
    """The target's honest submissions arriving from week 1 to 14 days before the end: listed, healed (good fixes
    paid, of the good ones submitted, listed or not), time to heal, withdrawn after waiting (expired), drawn but not
    final at the end (stuck); the attacker's bad fixes paid, on the target and elsewhere; its money."""
    w, hz = net.w, net.w.horizon_h
    lo, hi = WEEK, hz - w.withdraw_after_days * DAY
    allsubs = list(net.subs.values()) + net.unlisted
    tgt = [s for s in allsubs if s.tier == ISSUE and s.party is None and lo <= s.t < hi
           and net.repo.get(s.sid) == TARGET]
    good = [s for s in tgt if s.good]
    heal = [s.final_t - s.t for s in good if s.final]
    mine = [s for s in allsubs if s.tier == ISSUE and s.party == a.party]
    nodes = net.party_validators(a.party)
    pa = net.parties[a.party]
    return dict(
        n=float(len(tgt)), listed=100 * mean(s.state != "unlisted" for s in tgt) if tgt else float("nan"),
        healed=100 * len(heal) / len(good) if good else float("nan"),
        heal_med=median(heal) if heal else float("nan"), heal_p90=K._pct(heal, 0.9),
        withdrawn=100 * mean(s.state == "withdrawn" for s in tgt) if tgt else float("nan"),
        stuck=100 * mean(s.state in ("judging", "held", "challenged") for s in tgt) if tgt else float("nan"),
        bad_honest=float(sum(1 for s in tgt if s.final and not s.good)),
        a_sub=float(len(mine)), a_paid_t=float(sum(1 for s in mine if s.final and net.repo.get(s.sid) == TARGET)),
        a_paid_o=float(sum(1 for s in mine if s.final and net.repo.get(s.sid) != TARGET)),
        a_gains=pa.gains, a_costs=pa.costs, a_slashed=sum(v.acct.slashed for v in nodes),
        a_fees=sum(v.acct.fees for v in nodes), silences=float(net.stats["silences"]),
        suspended=float(sum(v.suspensions for v in nodes)), net=net.party_net(a.party))


def run(a: RepoAttacker, seed: int, p: Params, h: Optional[int]) -> ChoiceNet:
    return ChoiceNet(seed, p, a.world(), [a], target_honest=h).run()  # type: ignore[return-value]


# ---------- the rows (fixed before the 40-seed runs: report measured-v6, section B.1) ----------

HONEST = 28
TARGET_HONEST = (1, 3, 5, 10)
NODES = (3, 10)
MINS = (0, 3, 5, 7)
STAKE_X = 0.1
BASE = replace(P0, JUDGE_FEE=N.JUDGE_FEE, REPO_LISTS=True)  # D30's fee, no reputation cap (the worst case for B)


def world(pool: str = "hidden", seat: str = "anthropic") -> World:
    return replace(N.world(pool, seat, 3), initial_active=HONEST - 1, joins_week=0.0, repos=K.REPOS)


Row = Tuple[str, str, str, int, int, int, float, str]  # table, kind, form, target honest, nodes, minimum, stake x, pool


def rows_tee() -> List[Row]:
    rows: List[Row] = []
    for pool, _ in N.POOLS:
        for form in ("one", "spread"):
            for h in TARGET_HONEST:
                for a in NODES:
                    for m in MINS:
                        rows.append(("tee", "tee", form, h, a, m, 0.0, pool))
        for a in NODES:  # no repository choice: every validator eligible everywhere
            rows.append(("tee", "tee", "open", HONEST, a, 0, 0.0, pool))
        for h in TARGET_HONEST:
            for a in NODES:
                rows.append(("stake", "tee", "one", h, a, 0, STAKE_X, pool))
    return rows


def rows_rep() -> List[Row]:
    """ADDED AFTER THE 2-SEED SMOKE, before the 40-seed runs: the broken TEE concentrated on the target under D29's
    cap with D30's fee (report v5's recommended rule), the accomplice on a fresh identity each fix."""
    return [("rep", "tee", "one", h, a, 0, 0.0, pool) for pool, _ in N.POOLS for h in TARGET_HONEST for a in NODES]


def rows_silence() -> List[Row]:
    return [("silence", "silence", "one", h, a, m, 0.0, "hidden") for h in TARGET_HONEST for a in NODES for m in MINS]


TABLES: Dict[str, Callable[[], List[Row]]] = {"tee": rows_tee, "rep": rows_rep, "silence": rows_silence}


def params_of(row: Row) -> Params:
    table, kind, form, h, a, m, x, pool = row
    rep = dict(REP_CAP=True, REP_ON_REVERSAL="minus") if table == "rep" else {}
    return replace(BASE, REPO_LISTS=form != "open", REPO_MIN_ELIGIBLE=m, REPO_STAKE_X=x, **rep)


def _job(job) -> Dict[str, float]:
    table, i, seed = job
    row = TABLES[table]()[i]
    _, kind, form, h, nodes, m, x, pool = row
    p, w = params_of(row), world(pool)
    hh = None if form == "open" else h
    att = metrics(run(RepoAttacker(False, w, kind, nodes, form), seed, p, hh), RepoAttacker(False, w, kind, nodes, form))
    twin = metrics(run(RepoAttacker(True, w, kind, nodes, form), seed, p, hh), RepoAttacker(True, w, kind, nodes, form))
    out = {k: v for k, v in att.items()}
    out.update({f"twin_{k}": v for k, v in twin.items()})
    out["diff"] = att["net"] - twin["net"]
    out["harm"] = twin["healed"] - att["healed"]
    if kind == "silence":
        absent = metrics(run(RepoAttacker(True, w, kind, 0, form), seed, p, hh), RepoAttacker(True, w, kind, 0, form))
        out.update({f"absent_{k}": v for k, v in absent.items()})
    else:  # ADDED AFTER THE 2-SEED SMOKE: the accomplice alone, its validators honest (what the broken TEE adds)
        mk = lambda: RepoAttacker(False, w, kind, nodes, form, nodes_honest=True)  # noqa: E731
        alone = metrics(run(mk(), seed, p, hh), mk())
        out.update({f"alone_{k}": v for k, v in alone.items()})
        out["tee_part"] = att["net"] - alone["net"]
    return out


def key_of(row: Row) -> str:
    return "|".join(map(str, row))


def run_rows(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = TABLES[table]()
    res = C._map(_job, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    out = []
    for i, row in enumerate(rows):
        chunk = res[i * len(seeds):(i + 1) * len(seeds)]
        out.append((key_of(row), {k: [r[k] for r in chunk] for k in chunk[0]}))
    return out


def holds(xs: Sequence[float]) -> bool:
    """At or below its twin: the difference's mean minus 2 SE is not above zero."""
    return mean(xs) - 2 * A._se(xs) <= 0


# ---------- rendering ----------

def render(folder: str) -> str:
    import json
    ms = K.ms
    out: List[str] = []
    for table in TABLES:
        path = Path(folder, f"{table}.json")
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        out.append(f"### Simulation B, table `{table}` (mean ± 2 SE; bold: the attacker above its twin)\n")
        if table == "silence":
            out.append("| Target's honest validators | Attackers | Minimum | Listed (%) | Healed: attacker / twin / "
                       "absent (%) | Heal median (h): attacker / twin | Expired (%) | Stuck (%) | Harm, healed "
                       "twin − attacker (points) | Silences | Suspensions | Attacker − twin ($) |")
            out.append("|" + "---|" * 12)
        else:
            out.append("| Bad fixes | Form | Target's honest validators | Attackers | Minimum | Stake cap × | "
                       "Listed (%) | Bad fixes paid: target / elsewhere | …with its validators honest | Of submitted "
                       "| Healed: attacker / twin (%) | Attacker − twin ($ a year) | Attacker − the accomplice alone "
                       "(the broken TEE's part, $) |")
            out.append("|" + "---|" * 13)
        for key, m in data:
            _, kind, form, h, a, mm, x, pool = key.split("|")
            d = ms(m["diff"], 0)
            d = f"**{d}**" if not holds(m["diff"]) else d
            if table == "silence":
                out.append(f"| {h} | {a} | {mm} | {ms(m['listed'], 0)} | {ms(m['healed'], 0)} / "
                           f"{ms(m['twin_healed'], 0)} / {ms(m['absent_healed'], 0)} | {ms(m['heal_med'], 0)} / "
                           f"{ms(m['twin_heal_med'], 0)} | {ms(m['withdrawn'], 1)} | {ms(m['stuck'], 1)} | "
                           f"{ms(m['harm'], 1)} | {ms(m['silences'], 0)} | {ms(m['suspended'], 1)} | {d} |")
            else:
                pool_s = dict(N.POOLS)[pool]
                tp = ms(m["tee_part"], 0)
                tp = f"**{tp}**" if not holds(m["tee_part"]) else tp
                out.append(f"| {pool_s} | {form} | {h} | {a} | {mm} | {float(x):g} | {ms(m['listed'], 0)} | "
                           f"{ms(m['a_paid_t'], 1)} / {ms(m['a_paid_o'], 1)} | "
                           f"{ms([x + y for x, y in zip(m['alone_a_paid_t'], m['alone_a_paid_o'])], 1)} | "
                           f"{ms(m['a_sub'], 0)} | {ms(m['healed'], 0)} / {ms(m['twin_healed'], 0)} | {d} | {tp} |")
        out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    import json
    import time
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.choice")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated: " + ", ".join(TABLES))
    ap.add_argument("--out", default="")
    ap.add_argument("--render", default="")
    a = ap.parse_args(argv)
    if a.render:
        print(render(a.render))
        return 0
    seeds = list(range(1, a.seeds + 1))
    for name in [x for x in a.only.split(",") if x] or list(TABLES):
        t0 = time.time()
        data = run_rows(name, seeds, a.jobs)
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            Path(a.out, f"{name}.json").write_text(json.dumps(data))
        print(f"{name}: done in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
