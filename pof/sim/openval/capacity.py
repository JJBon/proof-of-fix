"""A validator's capacity ("judge number"), a repository's cap, the queue's order and spam (proof-of-fix#253; design
D31, D32, PROPOSED; report measured-v6, simulation A).

The owner's ask: a validator takes at most N checks an hour, so that it can't be spammed. On a testnet a submission
costs only free test ETH, but every check costs its validator real model money.

Each rule is a named switch of `Params`, off by default and read only by `CapNet` (a plain `Net` refuses them):
- `MAX_CHECKS_PER_HOUR` (D31): a counted draw skips a validator that took that many checks in the trailing hour, as
  it skips a non-responder (no slash). k is set from every eligible validator, as without the rule, and never lowered
  for capacity: with too few free validators the submission waits, and is drawn again at the next hour (nothing
  fails). Audits, challenge and appeal panels count toward a validator's hour but are never refused for capacity, so
  spam can't suppress them;
- `REPO_CHECKS_PER_HOUR` (D31): a repository's counted checks drawn in the trailing hour;
- `QUEUE_ORDER` (D32): waiting submissions are drawn in arrival order ("fifo"), or those whose identity held standing
  reputation (D29's sense: bounties paid and never reversed) when submitted first ("reputation"), arrival order within
  each class. A repository at its cap is skipped; when the best waiting submission can't be drawn for capacity, nothing
  behind it is (every one needs the same validators);
- `NEWCOMER_LANE` (D32's lane, POST HOC to report v6): a share of each validator's capacity is the only capacity the
  second class (newcomers, and junk from fresh identities) may be drawn on, first come first served within it; the rest
  is the first class's. Each validator banks a credit of NEWCOMER_LANE x MAX_CHECKS_PER_HOUR checks an hour (at most
  max(1, that)); a second-class counted draw skips a validator under 1 credit, and takes 1 from each judge drawn;
- `LANE_PER_ID_DAY` (POST HOC): an identity in the second class may submit at most that many fixes in any trailing 24
  hours; beyond it the submission is refused before anything is checked (fresh identities defeat it on a testnet).

The faucet (#251 task 3.15, POST HOC to report v6; report faucet-spam-v1): with `JUDGE_FEE` on and the spammer's
`usdc_day` set, every junk fix pays the judges' fee from a wallet that only Circle's faucet fills, at `usdc_day` USDC a
day (ASSUMED, swept: one address's limit up to many addresses, or one account). A slot the wallet can't pay for is
skipped, so the junk's rate is min(the intended rate, usdc_day / JUDGE_FEE). None (the default): no limit, as before.

World (`World.repos`, `honest_rep0`, `new_solvers`; ASSUMED): honest submissions spread evenly over `repos`
repositories; honest solvers start with `honest_rep0` of reputation, except the first `new_solvers`, who start at 0.

The spammer (`Spammer`) submits junk fixes from a fresh identity each at `per_hour`, never withdraws them, and pays
nothing (a testnet) or the judges' fee (`JUDGE_FEE`, as on a real-money chain). Junk is rejected by every judge
(ASSUMED: it buys checks, not payouts; report v5's free identities cover bad fixes meant to pass).

    python3 -m pof.sim.openval.capacity [--seeds 40] [--jobs 15] [--out DIR] [--render DIR]
    python3 -m pof.sim.openval.capacity --only faucet --seed0 41 --seeds 40 --jobs 15 --out DIR  (report faucet-spam-v1)

No model call: verdicts are replayed from data/judges/verdicts-v2.matrix.json (#160).
"""

from __future__ import annotations

import argparse
import math
import random
from collections import Counter, defaultdict, deque
from dataclasses import replace
from pathlib import Path
from statistics import mean, median
from typing import Callable, Deque, Dict, List, Optional, Sequence, Set, Tuple

from . import actors as A
from . import contenders as C
from . import nodeposit as N
from . import panels as D
from .evidence import P0
from .net import HONEST_SOLVERS, ISSUE, Sub
from .params import DAY, HOUR, WEEK, WORLD, Params, World

T_REPO = 0x4E9051  # randomness tag: an honest submission's repository
T_SPAM = 0x5BA111  # ...the spammer's own draws
# Circle's public faucet (faucet.circle.com, read 2026-11-18): 20 USDC a request, one request per address and
# blockchain every 2 hours, no account, reCAPTCHA. The Developer Console faucet (account-gated; its page now
# redirects to the public faucet, so the value is Circle's earlier docs' as indexed): 20 USDC a testnet a day
FAUCET_DRIP = 20.0
FAUCET_EVERY_H = 2.0
FAUCET_ADDRESS_DAY = FAUCET_DRIP * 24 / FAUCET_EVERY_H  # 240 USDC a day: one address requesting every 2 hours
FAUCET_ACCOUNT_DAY = 20.0  # one Developer Console account, one request a day on one testnet
R_CAP = "capacity: too few validators free this hour"
R_REPO = "repository: its checks this hour are at the cap"
R_QUEUE = "queue: behind earlier submissions"
R_LANE = "lane: too few validators with newcomer-lane credit this hour"
COST_LOW, COST_HIGH = 0.02, 0.12  # validator-kit/COSTS.md: one judge's model call, $ a verdict
REP0 = N.REP0  # an established honest solver's reputation (report v5)


class CapNet(N.NDNet):
    """`NDNet` with repositories, each validator's capacity, a repository's cap and the queue's order."""
    REPO_RULES = True

    def __init__(self, seed: int, p: Params, w: World, actors: Sequence[object] = (), **kw):
        self.repo: Dict[int, int] = {}  # submission -> repository
        self.used: Dict[int, Deque[float]] = defaultdict(deque)  # validator -> its checks' times, the trailing hour
        self.repo_used: Dict[int, Deque[Tuple[float, int]]] = defaultdict(deque)  # repository -> (time, checks)
        self.checks_by: Counter = Counter()  # validator -> every check it ran (counted, audit, challenge, appeal)
        self.hour_max: Counter = Counter()  # validator -> the most checks it ran in any trailing hour
        self.checked: Set[Tuple[int, int]] = set()  # (validator, repository) of every check run
        self.junk: Set[int] = set()
        self.junk_checks = 0
        self.all_checks = 0
        self.hrep: Dict[str, float] = {}  # an honest solver's reputation (D29's sense), for QUEUE_ORDER
        self.cls: Dict[int, int] = {}  # submission -> its class in the queue (0 first)
        self.seq: Dict[int, int] = {}
        self.queue: Dict[int, Tuple[Deque[Sub], Deque[Sub]]] = {}
        self.inq: Set[int] = set()
        self.qmax = 0
        self.qlast_empty = -1.0  # the last hour the queue was empty
        self.q_samples: List[int] = []
        self._draining = False
        self.lane_c: Dict[int, float] = {}  # validator -> its newcomer-lane credit, and when it was last updated
        self.lane_t: Dict[int, float] = {}
        self.lane_checks = 0  # counted checks drawn on the lane
        self.lane_need: Optional[float] = None  # when enough validators will hold lane credit for the waiting head
        self.lane_next = -1.0  # the lane's next scheduled drain
        self.id_subs: Dict[object, Deque[float]] = defaultdict(deque)  # second-class identity -> its submissions' times
        self.rate_refused: Counter = Counter()  # "honest" / "actor" -> submissions refused by LANE_PER_ID_DAY
        if p.NEWCOMER_LANE and (p.MAX_CHECKS_PER_HOUR is None or p.QUEUE_ORDER != "reputation"
                                or not 0 < p.NEWCOMER_LANE < 1):
            raise ValueError("NEWCOMER_LANE is a share in (0, 1) of MAX_CHECKS_PER_HOUR, under QUEUE_ORDER reputation")
        if p.LANE_PER_ID_DAY is not None and p.QUEUE_ORDER != "reputation":
            raise ValueError("LANE_PER_ID_DAY applies to QUEUE_ORDER reputation's second class")
        for i in range(HONEST_SOLVERS):
            self.hrep[f"solver-{i}"] = 0.0 if i < w.new_solvers else w.honest_rep0
        super().__init__(seed, p, w, actors, **kw)
        self.capmode = p.MAX_CHECKS_PER_HOUR is not None or p.REPO_CHECKS_PER_HOUR is not None
        if self.capmode:
            self._at(HOUR, self._hour)

    # ----- repositories -----

    def submit(self, t: float, bounty: float, good: bool, solver: str, party: Optional[str], tier: str = ISSUE,
               value: float = 0.0, parties=None, commitment=None, issue: Optional[int] = None,
               ident: Optional[str] = None, key: Optional[int] = None, inflate: bool = False,
               effort: float = 0.0, repo: int = 0) -> Sub:
        sub = super().submit(t, bounty, good, solver, party, tier, value, parties, commitment, issue, ident, key,
                             inflate, effort)
        self.repo[sub.sid] = repo
        return sub

    def repo_of(self, sub: Sub) -> int:
        r = self.repo.get(sub.sid)
        if r is None:
            r = self.repo[sub.sid] = D.h(self.seed, T_REPO, sub.sid) % max(1, self.w.repos)
        return r

    def standing(self, sub: Sub) -> float:
        """The reputation of the identity behind `sub` now: an honest solver's, or an actor identity's (NDNet's)."""
        if sub.party is None:
            return self.hrep.get(sub.solver, 0.0)
        idt = self.ident(sub)
        return self.rep[idt] if idt is not None else 0.0

    # ----- capacity -----

    def _purge(self, q: Deque[float]) -> None:
        while q and q[0] <= self.t - HOUR + 1e-9:
            q.popleft()

    def free(self, vid: int) -> bool:
        cap = self.p.MAX_CHECKS_PER_HOUR
        if cap is None:
            return True
        q = self.used[vid]
        self._purge(q)
        return len(q) < cap

    def lane_credit(self, vid: int) -> float:
        """`vid`'s newcomer-lane credit now: NEWCOMER_LANE x MAX_CHECKS_PER_HOUR checks an hour, banked to at most
        max(1, that); it starts full."""
        r = self.p.NEWCOMER_LANE * (self.p.MAX_CHECKS_PER_HOUR or 0)
        depth = max(1.0, r)
        c = min(depth, self.lane_c.get(vid, depth) + r * (self.t - self.lane_t.get(vid, self.t)) / HOUR)
        self.lane_c[vid], self.lane_t[vid] = c, self.t
        return c

    def in_lane(self, sub: Sub) -> bool:
        return bool(self.p.NEWCOMER_LANE) and sub.tier == ISSUE and self.cls.get(sub.sid, 0) == 1

    def repo_load(self, r: int) -> int:
        q = self.repo_used[r]
        while q and q[0][0] <= self.t - HOUR + 1e-9:
            q.popleft()
        return sum(n for _, n in q)

    def _use(self, vid: int, sub: Sub) -> None:
        q = self.used[vid]
        self._purge(q)
        q.append(self.t)
        self.hour_max[vid] = max(self.hour_max[vid], len(q))
        self.checks_by[vid] += 1
        self.checked.add((vid, self.repo_of(sub)))
        self.all_checks += 1
        if sub.sid in self.junk:
            self.junk_checks += 1

    def _pay_check(self, v, sub: Sub, solver_pays: bool) -> None:
        super()._pay_check(v, sub, solver_pays)
        self._use(v.vid, sub)

    def _audit(self, sub: Sub, a):
        self._use(a.vid, sub)
        return super()._audit(sub, a)

    def honest_vote(self, sub: Sub, v, role: int) -> bool:
        if sub.sid in self.junk:
            return False  # ASSUMED: junk is rejected by every judge
        return super().honest_vote(sub, v, role)

    def plan(self, sub: Sub):
        k, d, reason = super().plan(sub)
        if d is None or not self.capmode or sub.tier != ISSUE:
            return k, d, reason
        p = self.p
        if p.REPO_CHECKS_PER_HOUR is not None and self.repo_load(self.repo_of(sub)) + d.k > p.REPO_CHECKS_PER_HOUR:
            return 0, None, R_REPO
        lane = self.in_lane(sub)
        ok = (lambda vid: self.free(vid) and self.lane_credit(vid) >= 1 - 1e-9) if lane else self.free
        if p.MAX_CHECKS_PER_HOUR is None or all(ok(vid) for vid in d.panel):
            return k, d, reason
        pool = [v for v in self.eligible(sub) if ok(v.vid)]
        if d.k == 1:
            pool = [v for v in pool if self.k1_ok(v, sub)]
        if len(pool) < d.k:
            if lane:  # when the k-th validator free of capacity will hold 1 credit: the lane drains again then
                r = p.NEWCOMER_LANE * p.MAX_CHECKS_PER_HOUR
                need = sorted(max(0.0, 1 - self.lane_credit(v.vid)) / r for v in self.eligible(sub) if self.free(v.vid))
                self.lane_need = self.t + need[d.k - 1] * HOUR + 1e-6 if len(need) >= d.k else None
            return 0, None, R_LANE if lane else R_CAP
        d2 = D.draw(d.seed, pool, d.k, self.draw_p(), exact=True, epoch=self.reg.epoch)
        if not d2.filled:
            return 0, None, R_CAP
        level = self.level_rule([self.reg.validators[v].level for v in d2.panel])
        if sub.bounty > p.limit(d2.k, level):
            return 0, None, R_CAP
        return d2.k, d2, ""

    # ----- the queue -----

    def _arrive(self, sub: Sub) -> None:
        if sub.tier == ISSUE:
            self.repo_of(sub)
            fifo = self.p.QUEUE_ORDER == "fifo"
            self.cls[sub.sid] = 0 if fifo or self.standing(sub) > 0 else 1
            if self.cls[sub.sid] == 1 and self.p.LANE_PER_ID_DAY is not None and self._rate_refuses(sub):
                return
            self.seq[sub.sid] = len(self.seq)
        super()._arrive(sub)

    def _rate_refuses(self, sub: Sub) -> bool:
        """LANE_PER_ID_DAY: refuse `sub` when its identity submitted that many in the trailing 24 hours (a refused
        submission is reverted: no fee, no claim, nothing checked, and it doesn't count toward the rate). An honest
        solver's refused fix is kept in `subs` (it counts as never drawn); an actor's is dropped, as NDNet drops a
        claim refused over D29's cap."""
        who = self.ident(sub) if sub.party is not None else ("", sub.solver)
        if who is None:
            who = (sub.party, f"sid{sub.sid}")
        q = self.id_subs[who]
        while q and q[0] <= self.t - DAY + 1e-9:
            q.popleft()
        if len(q) < self.p.LANE_PER_ID_DAY:
            q.append(self.t)
            return False
        sub.state, sub.wait_reason = "refused", "rate: this identity's submissions in the last 24 hours"
        self.rate_refused["actor" if sub.party is not None else "honest"] += 1
        if sub.party is None:
            self.subs[sub.sid] = sub
        return True

    def _queued_ahead(self) -> bool:
        return bool(self.inq)

    def _enqueue(self, sub: Sub) -> None:
        r = self.repo_of(sub)
        qs = self.queue.get(r)
        if qs is None:
            qs = self.queue[r] = (deque(), deque())
        qs[self.cls.get(sub.sid, 0)].append(sub)
        self.inq.add(sub.sid)
        if sub.sid not in self.waiting:  # registered as waiting, as `Net._try_draw` registers a submission that waits
            self.waiting[sub.sid] = sub
            sub.waited_since = self.t
            self.stats["waited"] += 1
            self.period["waited"] += 1
            if self.p.SHADOW_PER_WAITING > 0:
                self._wait_shadows(sub)
        sub.tried_epoch = self.reg.epoch
        sub.state, sub.wait_reason = "waiting", sub.wait_reason or R_QUEUE
        self.qmax = max(self.qmax, len(self.inq))

    def _try_draw(self, sub: Sub) -> None:
        if not self.capmode or sub.tier != ISSUE or self._draining:
            return super()._try_draw(sub)
        if sub.sid in self.inq:  # `Net`'s daily retry: the queue's own hourly drain draws it in its turn
            sub.tried_epoch = self.reg.epoch
            return
        if not self._queued_ahead():
            self._draw_now(sub)
            if sub.state == "waiting" and sub.wait_reason in (R_CAP, R_REPO, R_LANE):
                self._enqueue(sub)
            return
        self._enqueue(sub)
        self._drain()

    def _draw_now(self, sub: Sub) -> None:
        """`Net._try_draw`, and the repository's count of counted checks when it is drawn."""
        draining, self._draining = self._draining, True
        try:
            super()._try_draw(sub)
        finally:
            self._draining = draining
        if sub.drawn_t == self.t and sub.state != "waiting":
            self.repo_used[self.repo_of(sub)].append((self.t, sub.k))
            if self.in_lane(sub):
                for vid in sub.draw.panel:
                    self.lane_c[vid] = self.lane_credit(vid) - 1.0
                    self.lane_checks += 1
        elif sub.state == "waiting" and sub.wait_reason == R_LANE and self.lane_need is not None:
            # the lane draws as soon as its credit allows (anyone may call the draw), not only at the hour
            if not self.lane_next > self.t or self.lane_need < self.lane_next - 1e-9:
                self.lane_next = self.lane_need
                self._at(self.lane_need, self._drain)

    def _drain(self) -> None:
        """Draw waiting submissions in the queue's order: at each step the best head among the repositories not at
        their cap. A head that can't be drawn for capacity stops the drain (everyone behind it needs the same
        validators); one at its repository's cap blocks that repository for this drain; one that waits for another
        reason leaves the queue (`Net`'s daily retry keeps it)."""
        if self._draining:
            return
        self._draining = True
        blocked: Set[int] = set()
        try:
            while True:
                best = None
                for r, qs in self.queue.items():
                    if r in blocked:
                        continue
                    for c, q in enumerate(qs):
                        while q and (q[0].state != "waiting" or q[0].sid not in self.inq):
                            self.inq.discard(q.popleft().sid)
                        if q:
                            key = (c, self.seq.get(q[0].sid, 0))
                            if best is None or key < best[0]:
                                best = (key, r, c)
                            break
                if best is None:
                    return
                _, r, c = best
                q = self.queue[r][c]
                sub = q[0]
                self._draw_now(sub)
                if sub.state != "waiting":
                    q.popleft()
                    self.inq.discard(sub.sid)
                    continue
                if sub.wait_reason in (R_CAP, R_LANE):  # the lane: every second-class head needs the same credit
                    return
                if sub.wait_reason == R_REPO:
                    blocked.add(r)
                    continue
                q.popleft()
                self.inq.discard(sub.sid)
        finally:
            self._draining = False

    def _hour(self) -> None:
        self._drain()
        n = len(self.inq)
        self.q_samples.append(n)
        if n == 0:
            self.qlast_empty = self.t
        if self.t + HOUR <= self.w.horizon_h:
            self._at(self.t + HOUR, self._hour)

    def _tick(self) -> None:
        super()._tick()
        if self.inq:  # withdrawn ones leave the queue
            self.inq = {sid for sid in self.inq if self.subs[sid].state == "waiting"}

    def _finalize(self, sub: Sub, outcome: bool) -> None:
        super()._finalize(sub, outcome)
        if sub.tier != ISSUE or sub.party is not None:
            return
        if outcome:
            self.hrep[sub.solver] = self.hrep.get(sub.solver, 0.0) + sub.bounty
        elif sub.reversed:
            if self.p.REP_ON_REVERSAL == "minus":
                self.hrep[sub.solver] = max(0.0, self.hrep.get(sub.solver, 0.0) - self.p.REP_LOSS_X * sub.bounty)
            else:
                self.hrep[sub.solver] = 0.0


# ---------- the spammer ----------

class Spammer(N.NDActor):
    """Junk fixes at `per_hour`, each from a fresh identity (or, `reputable`, all from one identity holding `REP0` of
    reputation, which D29's cap then bounds; or, `idents` > 0, in turn from a pool of that many identities without
    reputation: identities that cost something, post hoc), to repository 0 (`spread` False) or every repository in
    turn; each to a random one of the week's listed issues it may claim (none: it skips). It never withdraws a waiting
    submission. With `per_hour` 0, or as its own twin, it submits nothing.

    `usdc_day` (the faucet, post hoc): each junk fix pays `JUDGE_FEE` from a wallet the faucet fills at `usdc_day` USDC
    a day, continuously from 0 at the start (no stockpile); a slot whose wallet holds less than the fee is skipped
    (`count["unfunded"]`). The wallet is the spammer's alone: fresh identities still cost nothing, since USDC moves
    freely between addresses."""
    TAG = 21
    name = party = "spammer"

    def __init__(self, honest: bool = False, w: World = WORLD, per_hour: float = 0.0, spread: bool = False,
                 reputable: bool = False, idents: int = 0, usdc_day: Optional[float] = None):
        super().__init__(honest, w, per_week=per_hour * WEEK / HOUR)
        self.spread, self.reputable, self.idents = spread, reputable, idents
        self.usdc_day = usdc_day
        self.wallet, self.wallet_t, self.usdc_in, self.usdc_paid = 0.0, 0.0, 0.0, 0.0

    def start(self, net: CapNet) -> None:  # type: ignore[override]
        if self.usdc_day is not None and not (net.p.JUDGE_FEE > 0 and self.usdc_day >= 0):
            raise ValueError("the faucet's income (usdc_day) needs JUDGE_FEE: junk pays the judges' fee from it")
        if self.reputable:
            net.rep[(self.party, "rep")] = REP0

    def _funded(self, net: CapNet) -> bool:
        """The faucet: the wallet's income since the last slot comes in; True when it holds the judges' fee."""
        if self.usdc_day is None:
            return True
        got = self.usdc_day * (net.t - self.wallet_t) / DAY
        self.wallet, self.wallet_t, self.usdc_in = self.wallet + got, net.t, self.usdc_in + got
        return self.wallet >= net.p.JUDGE_FEE - 1e-9

    def slot(self, net: CapNet, i: int) -> None:  # type: ignore[override]
        if self.honest:
            return
        ident = "rep" if self.reputable else f"p{i % self.idents}" if self.idents else f"j{i}"
        rng = random.Random(D.h(net.seed, T_SPAM, i))
        b = self.pick(self.seen(net, self.TAG, i), net.room((self.party, ident)), "random", rng)
        if b is None:  # no listed issue it may claim
            self.count["skipped"] += 1
            return
        if not self._funded(net):  # the faucet hasn't paid in the judges' fee yet
            self.count["unfunded"] += 1
            return
        if self.usdc_day is not None:
            self.wallet -= net.p.JUDGE_FEE
            self.usdc_paid += net.p.JUDGE_FEE
        repo = i % max(1, net.w.repos) if self.spread else 0
        s = net.submit(net.t, b, False, self.name, self.party, ident=ident, key=60_000_000 + i, repo=repo)
        net.junk.add(s.sid)
        self.subs.append(s)
        self.count["submitted"] += 1

    def withdraws(self, net, sub: Sub) -> bool:  # type: ignore[override]
        return sub.party != self.party


# ---------- what is measured ----------

def _pct(xs: Sequence[float], q: float) -> float:
    if not xs:
        return float("nan")
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def metrics(net: CapNet) -> Dict[str, float]:
    """Honest submissions arriving from week 1 to 14 days before the end (so every one could be withdrawn): the wait
    for a panel (a submission never drawn counts its wait until it was withdrawn or the run ended: a lower bound), the
    shares waiting over 24 hours and 7 days, the share withdrawn, time to heal (submission to payment) of the good
    fixes paid; the newcomers' (honest solvers with no reputation when they submitted) apart. Each validator's checks
    a day and the most it ran in an hour; the checks spent on junk; the queue."""
    w, hz = net.w, net.w.horizon_h
    lo, hi = WEEK, hz - w.withdraw_after_days * DAY
    hon = [s for s in net.subs.values() if s.tier == ISSUE and s.party is None and lo <= s.t < hi]

    def wait(s: Sub) -> float:
        if s.drawn_t is not None:
            return s.drawn_t - s.t
        end = min(hz, s.t + w.withdraw_after_days * DAY) if s.state == "withdrawn" else hz
        return end - s.t

    def block(xs: List[Sub], tag: str) -> Dict[str, float]:
        ws = [wait(s) for s in xs]
        heal = [s.final_t - s.t for s in xs if s.good and s.final]
        good = [s for s in xs if s.good]
        return {f"{tag}n": float(len(xs)),
                f"{tag}wait_med": median(ws) if ws else float("nan"), f"{tag}wait_p90": _pct(ws, 0.9),
                f"{tag}over24": 100 * mean(x > DAY for x in ws) if ws else float("nan"),
                f"{tag}over7d": 100 * mean(x > 7 * DAY for x in ws) if ws else float("nan"),
                f"{tag}withdrawn": 100 * mean(s.state == "withdrawn" for s in xs) if xs else float("nan"),
                f"{tag}heal_med": median(heal) if heal else float("nan"), f"{tag}heal_p90": _pct(heal, 0.9),
                f"{tag}healed": 100 * len(heal) / len(good) if good else float("nan")}

    out = block(hon, "")
    out.update(block([s for s in hon if net.cls.get(s.sid, 0) == 1 and net.p.QUEUE_ORDER != "fifo"], "new_"))
    # post hoc (the lane's rows): the established apart, the lane's share of checks, submissions refused by the rate
    out.update(block([s for s in hon if net.cls.get(s.sid, 0) == 0 and net.p.QUEUE_ORDER != "fifo"], "est_"))
    out.update(lane_share=100 * net.lane_checks / max(1, net.all_checks), refused_honest=float(
        net.rate_refused["honest"]), refused_junk_day=net.rate_refused["actor"] / (hz / DAY))
    days = hz / DAY
    mine = {getattr(a, "party", None) for a in net.actors}
    vals = [v for v in net.reg.validators.values() if v.party not in mine]
    per_day = [net.checks_by[v.vid] / days for v in vals]
    junk = [s for s in net.subs.values() if s.sid in net.junk]
    judged = [s for s in net.subs.values() if s.tier == ISSUE and s.drawn_t is not None]
    fee_in = net.p.JUDGE_FEE * len(judged)
    # post hoc (the faucet's rows): the junk a day and the faucet requests it took, every validator's checks together
    # (the launch's validators are all the owner's) and their model spend a month (30 days)
    spam = [a for a in net.actors if isinstance(a, Spammer)]
    out.update(junk_day=len(junk) / days, faucet_req_day=len(junk) * net.p.JUDGE_FEE / FAUCET_DRIP / days,
               unfunded_day=sum(a.count["unfunded"] for a in spam) / days,
               net_checks_day=sum(per_day), owner_month_low=sum(per_day) * 30 * COST_LOW,
               owner_month_high=sum(per_day) * 30 * COST_HIGH)
    out.update(checks_day=mean(per_day), checks_day_max=max(per_day), hour_max=float(max(net.hour_max.values() or [0])),
               spend_low=mean(per_day) * COST_LOW, spend_high=mean(per_day) * COST_HIGH,
               spend_high_max=max(per_day) * COST_HIGH,
               junk_share=100 * net.junk_checks / max(1, net.all_checks), junk_n=float(len(junk)),
               junk_drawn=float(sum(1 for s in junk if s.drawn_t is not None)),
               queue_max=float(net.qmax), queue_end=float(len(net.inq)),
               cleared=100.0 * (net.qlast_empty >= hz - WEEK) if net.capmode else 100.0 * (not net.waiting), queue_mean=mean(net.q_samples) if net.q_samples else 0.0,
               fee_per_check=fee_in / max(1, net.all_checks),
               spam_cost_day=len(junk) * net.p.JUDGE_FEE / days)
    return out


# ---------- the rows (fixed before the 40-seed runs: report measured-v6, section A.1) ----------

WEEKS = 13  # a quarter: the backlog's growth shows within it, and the year's spam would only lengthen the queue
REPOS = 10
NEW_SOLVERS = 10  # ASSUMED: 10 of the 50 honest solvers start with no reputation; the other 40 hold REP0
SEATS = N.SEATS
VALIDATORS = (4, 7, 15)
CAPS: Tuple[Optional[int], ...] = (None, 1, 3, 5, 10)
SPAM = ((0.0, "none"), (1.0, "low"), (10.0, "high"))  # junk fixes an hour
ORDERS = ("reputation", "fifo")
REPO_CAPS = (7, 21)
BASE = replace(P0, REP_CAP=True, REP_ON_REVERSAL="minus")  # report v5's recommended cap (D29), no fee: a testnet
FEE = N.JUDGE_FEE


def world(seat: str, n: int, weeks: int = WEEKS, pool: str = "hidden") -> World:
    """Report v5's base world with one family seated, `n` validators in all (the genesis and `n` - 1 more, every one
    bonded $1,250, no newcomers), 3 active honest solvers searching passes, 10 repositories, 40 established honest
    solvers and 10 new ones."""
    return replace(N.world(pool, seat, 3), initial_active=n - 1, joins_week=0.0, weeks=weeks, repos=REPOS,
                   honest_rep0=REP0, new_solvers=NEW_SOLVERS)


Row = Tuple[str, str, int, Optional[int], float, str, Optional[int], str, World, Params]
# table, seat, validators, capacity, spam an hour, order, repository cap, spam's form, world, params


def _p(cap: Optional[int], order: str, rcap: Optional[int] = None, **kw) -> Params:
    return replace(BASE, MAX_CHECKS_PER_HOUR=cap, QUEUE_ORDER=order, REPO_CHECKS_PER_HOUR=rcap, **kw)


def grid_rows() -> List[Row]:
    rows: List[Row] = []
    for seat, _ in SEATS:
        for n in VALIDATORS:
            w = world(seat, n)
            for cap in CAPS:
                for rate, _ in SPAM:
                    for order in (ORDERS if rate else ("fifo",)):
                        rows.append(("grid", seat, n, cap, rate, order, None, "one", w, _p(cap, order)))
    return rows


def repo_rows() -> List[Row]:
    """A repository's cap, 7 validators at 5 an hour: spam on one repository or spread over all ten."""
    rows: List[Row] = []
    for seat, _ in SEATS:
        w = world(seat, 7)
        for rcap in REPO_CAPS:
            for rate, _ in SPAM[1:]:
                for order in ORDERS:
                    for form in ("one", "spread"):
                        rows.append(("repo", seat, 7, 5, rate, order, rcap, form, w, _p(5, order, rcap)))
        for rate, _ in SPAM[1:]:  # the same spread spam without the repository cap
            for order in ORDERS:
                rows.append(("repo", seat, 7, 5, rate, order, None, "spread", w, _p(5, order)))
    return rows


def fee_rows() -> List[Row]:
    """The spam paying the judges' fee, as on a real-money chain (every honest fix pays it too); and junk from one
    identity holding reputation (the cap bounds its open claims)."""
    rows: List[Row] = []
    for seat, _ in SEATS:
        for n in (4, 7, 15):
            w = world(seat, n)
            for rate, _ in SPAM:
                rows.append(("fee", seat, n, 5, rate, "reputation", None, "one", w, _p(5, "reputation", JUDGE_FEE=FEE)))
        w = world(seat, 7)
        for rate, _ in SPAM[1:]:
            rows.append(("fee", seat, 7, 5, rate, "reputation", None, "reputable", w, _p(5, "reputation")))
    return rows


TABLES: Dict[str, Callable[[], List[Row]]] = {"grid": grid_rows, "repo": repo_rows, "fee": fee_rows}


# ---------- POST HOC: the newcomer lane (proposed after report v6's 40-seed results; its section "Post hoc: the
# newcomer lane" fixed these rows and the criterion before their 40-seed runs) ----------

LANE_SHARES = (0.10, 0.25, 0.50)
LANE_CAPS = (5, 10)
LANE_VALIDATORS = (7, 15)
LANE_SPAM = (1.0, 10.0)
LANE_REPOS: Tuple[Tuple[int, Optional[int]], ...] = ((10, None), (10, 7), (1, None), (1, 7))  # repositories, cap
ID_RATE = 2  # LANE_PER_ID_DAY in the rate rows: 2 a day, about 20 times an honest solver's rate here
ID_FORMS: Tuple[Tuple[str, Optional[int]], ...] = (("one", ID_RATE), ("pool10", None), ("pool10", ID_RATE),
                                                   ("pool50", ID_RATE))  # the spammer's identities, the rate


def lane_rows() -> List[Row]:
    """The lane at 10 %, 25 % and 50 % of each validator's capacity, beside the same row without it (report v6's
    reputation first); 7 and 15 validators, capacity 5 and 10, 1 and 10 junk fixes an hour on one repository from fresh
    identities; ten repositories or one (the testnet's launch), each with no repository cap or 7."""
    rows: List[Row] = []
    for seat, _ in SEATS:
        for n in LANE_VALIDATORS:
            for repos, rcap in LANE_REPOS:
                w = replace(world(seat, n), repos=repos)
                for cap in LANE_CAPS:
                    for rate in LANE_SPAM:
                        for share in (0.0,) + LANE_SHARES:
                            rows.append(("lane", seat, n, cap, rate, "reputation", rcap, "one", w,
                                         _p(cap, "reputation", rcap, NEWCOMER_LANE=share)))
    return rows


def rate_rows() -> List[Row]:
    """The lane's per-identity rate on the testnet's launch (one repository, no cap or 7): 7 and 15 validators at 5 an
    hour, 10 junk fixes an hour attempted, from fresh identities (free: the rate can't bind) or from a pool of 10 or 50
    identities (identities that cost something), the pool of 10 also without the rate (D29's cap alone)."""
    rows: List[Row] = []
    for seat, _ in SEATS:
        for n in LANE_VALIDATORS:
            for repos, rcap in LANE_REPOS[2:]:
                w = replace(world(seat, n), repos=repos)
                for share in LANE_SHARES:
                    for form, idr in ID_FORMS:
                        rows.append(("rate", seat, n, 5, 10.0, "reputation", rcap, form, w,
                                     _p(5, "reputation", rcap, NEWCOMER_LANE=share, LANE_PER_ID_DAY=idr)))
    return rows


LANE_TABLES: Dict[str, Callable[[], List[Row]]] = {"lane": lane_rows, "rate": rate_rows}


# ---------- POST HOC: the faucet (#251 task 3.15, #132 task 13.7; report faucet-spam-v1, whose section 3.1 fixed these
# rows and the criterion before their 40-seed runs on seeds 41-80) ----------

FAUCET_SEEDS = tuple(range(41, 81))  # fresh seeds, as #132 task 13.7 asks: every earlier round used 1-40
FAUCET_VALIDATORS = (7, 15)
# The spammer's faucet income, USDC a day, by the junk it intends an hour. None: no limit (v6's fee rows). At the
# judges' fee of $5.03, 1 junk fix an hour needs 121 USDC a day and 10 an hour 1,207: one address's limit (240) binds
# only the high rate, and the rate-1 rows beyond 240 would repeat the 240 row
FAUCET_INCOMES: Dict[float, Tuple[Optional[float], ...]] = {
    0.0: (None,),
    1.0: (FAUCET_ACCOUNT_DAY, FAUCET_ADDRESS_DAY),
    10.0: (FAUCET_ACCOUNT_DAY, FAUCET_ADDRESS_DAY, 2 * FAUCET_ADDRESS_DAY, 5 * FAUCET_ADDRESS_DAY, None),
}
FAUCET_ORDERS: Tuple[Tuple[str, float], ...] = (("reputation", 0.0), ("reputation", 0.25), ("fifo", 0.0))


def faucet_form(usdc_day: Optional[float]) -> str:
    return "usdc:none" if usdc_day is None else f"usdc:{usdc_day:g}"


def faucet_rows() -> List[Row]:
    """The testnet's launch (one repository, no repository cap, L16), 7 and 15 validators at 5 an hour, both seats;
    reputation first with no lane and with a lane of 25 % (#132 task 13.7), and arrival order; every submission pays
    the judges' fee ($5.03), the spammer's from its faucet income, from fresh identities."""
    rows: List[Row] = []
    for seat, _ in SEATS:
        for n in FAUCET_VALIDATORS:
            w = replace(world(seat, n), repos=1)
            for order, share in FAUCET_ORDERS:
                for rate, incomes in FAUCET_INCOMES.items():
                    for usdc in incomes:
                        rows.append(("faucet", seat, n, 5, rate, order, None, faucet_form(usdc), w,
                                     _p(5, order, JUDGE_FEE=FEE, NEWCOMER_LANE=share)))
    return rows


FAUCET_TABLES: Dict[str, Callable[[], List[Row]]] = {"faucet": faucet_rows}
ALL_TABLES: Dict[str, Callable[[], List[Row]]] = {**TABLES, **LANE_TABLES, **FAUCET_TABLES}


def run_one(row: Row, seed: int) -> CapNet:
    _, seat, n, cap, rate, order, rcap, form, w, p = row
    idents = int(form[4:]) if form.startswith("pool") else 0
    usdc = None if not form.startswith("usdc:") or form == "usdc:none" else float(form[5:])
    a = Spammer(False, w, per_hour=rate, spread=form == "spread", reputable=form == "reputable", idents=idents,
                usdc_day=usdc)
    return CapNet(seed, p, w, [a]).run()  # type: ignore[return-value]


def _job(job) -> Dict[str, float]:
    table, i, seed = job
    return metrics(run_one(ALL_TABLES[table]()[i], seed))


def key_of(row: Row) -> str:
    table, seat, n, cap, rate, order, rcap, form, w, p = row
    extra = ((p.NEWCOMER_LANE, w.repos, p.LANE_PER_ID_DAY) if table in LANE_TABLES
             else (p.NEWCOMER_LANE, w.repos) if table in FAUCET_TABLES else ())
    return "|".join(map(str, (table, seat, n, cap, rate, order, rcap, form) + extra))


def run_rows(table: str, seeds: Sequence[int], jobs: int = 1):
    rows = ALL_TABLES[table]()
    res = C._map(_job, [(table, i, s) for i in range(len(rows)) for s in seeds], jobs)
    out = []
    for i, row in enumerate(rows):
        chunk = res[i * len(seeds):(i + 1) * len(seeds)]
        out.append((key_of(row), {k: [r[k] for r in chunk] for k in chunk[0]}))
    return out


# ---------- rendering ----------

def ms(xs: Sequence[float], digits: int = 1, scale: float = 1.0) -> str:
    """Mean ± 2 SE over the seeds (NaNs dropped)."""
    xs = [x * scale for x in xs if x == x and not math.isinf(x)]
    if not xs:
        return "–"
    m, se = mean(xs), A._se(xs)
    return f"{m:,.{digits}f} ± {2 * se:,.{digits}f}"


def _h(xs: Sequence[float]) -> str:
    return ms(xs, 1)


def render(folder: str) -> str:
    import json
    out: List[str] = []
    for table in TABLES:
        path = Path(folder, f"{table}.json")
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        out.append(f"### Simulation A, table `{table}` (mean ± 2 SE over {len(next(iter(data))[1]['n'])} seeds)\n")
        out.append("| Seat | Validators | Capacity /h | Spam /h | Order | Repo cap /h | Spam's form | Wait median (h) "
                   "| Wait p90 (h) | > 24 h (%) | > 7 d (%) | Withdrawn (%) | Heal median (h) | Heal p90 (h) "
                   "| Newcomers > 7 d (%) | Checks / validator / day | Spend $/day at $0.12 | Most in an hour "
                   "| Checks on junk (%) | Queue max | Queue cleared in the last week (% of seeds) | Fee in $/check |")
        out.append("|" + "---|" * 22)
        for key, m in data:
            _, seat, n, cap, rate, order, rcap, form = key.split("|")
            seat = dict(SEATS).get(seat, seat)
            out.append(f"| {seat} | {n} | {'none' if cap == 'None' else cap} | {float(rate):g} | {order} | "
                       f"{'off' if rcap == 'None' else rcap} | {form} | {_h(m['wait_med'])} | {_h(m['wait_p90'])} | "
                       f"{ms(m['over24'])} | {ms(m['over7d'])} | {ms(m['withdrawn'])} | {_h(m['heal_med'])} | "
                       f"{_h(m['heal_p90'])} | {ms(m['new_over7d'])} | {ms(m['checks_day'])} | "
                       f"{ms(m['spend_high'], 2)} | {ms(m['hour_max'])} | {ms(m['junk_share'])} | "
                       f"{ms(m['queue_max'], 0)} | {ms(m['cleared'], 0)} | {ms(m['fee_per_check'], 2)} |")
        out.append("")
    return "\n".join(out)


def _ub(xs: Sequence[float]) -> float:
    """Mean + 2 SE over the seeds (NaNs dropped; none: 0)."""
    xs = [x for x in xs if x == x]
    return mean(xs) + 2 * A._se(xs) if xs else 0.0


def holds(m: Dict[str, Sequence[float]], tag: str = "") -> bool:
    """Report v6's criterion, fixed before its runs: over 24 hours at most 5 % and withdrawn at most 1 % (mean + 2
    SE)."""
    return _ub(m[f"{tag}over24"]) <= 5.0 and _ub(m[f"{tag}withdrawn"]) <= 1.0


def render_lane(folder: str) -> str:
    """The post hoc tables `lane` and `rate`."""
    import json
    out: List[str] = []
    for table in LANE_TABLES:
        path = Path(folder, f"{table}.json")
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        out.append(f"### Post hoc, table `{table}` (mean ± 2 SE over {len(next(iter(data))[1]['n'])} seeds)\n")
        out.append("| Seat | Validators | Repos | Repo cap /h | Capacity /h | Spam /h | Spammer's identities "
                   "| Rate /id /day | Lane | All > 24 h (%) | All withdrawn (%) | Established wait median / p90 (h) "
                   "| Established > 24 h / withdrawn (%) | Newcomers wait median / p90 (h) "
                   "| Newcomers > 24 h / withdrawn (%) | Checks / validator / day | Spend $/day | Cleared (% of seeds) "
                   "| Junk refused / day | Holds: all / newcomers |")
        out.append("|" + "---|" * 20)
        for key, m in data:
            _, seat, n, cap, rate, order, rcap, form, share, repos, idr = key.split("|")
            seat = dict(SEATS).get(seat, seat)
            ids = "fresh" if form == "one" else f"pool of {form[4:]}"
            yn = lambda b: "yes" if b else "**no**"  # noqa: E731
            out.append(f"| {seat} | {n} | {repos} | {'off' if rcap == 'None' else rcap} | {cap} | {float(rate):g} | "
                       f"{ids} | {'–' if idr == 'None' else idr} | "
                       f"{'none' if float(share) == 0 else f'{100 * float(share):.0f} %'} | {ms(m['over24'])} | "
                       f"{ms(m['withdrawn'])} | {_h(m['est_wait_med'])} / {_h(m['est_wait_p90'])} | "
                       f"{ms(m['est_over24'])} / {ms(m['est_withdrawn'])} | {_h(m['new_wait_med'])} / "
                       f"{_h(m['new_wait_p90'])} | {ms(m['new_over24'])} / {ms(m['new_withdrawn'])} | "
                       f"{ms(m['checks_day'], 0)} | {mean(m['spend_low']):.2f}–{mean(m['spend_high']):.2f} | "
                       f"{ms(m['cleared'], 0)} | {ms(m['refused_junk_day'], 0)} | "
                       f"{yn(holds(m))} / {yn(holds(m, 'new_'))} |")
        out.append("")
    return "\n".join(out)


def render_faucet(folder: str) -> str:
    """The post hoc table `faucet` (report faucet-spam-v1)."""
    import json
    path = Path(folder, "faucet.json")
    if not path.exists():
        return ""
    data = json.loads(path.read_text())
    out = [f"### Table `faucet` (mean ± 2 SE over {len(next(iter(data))[1]['n'])} seeds)\n",
           "| Seat | Validators | Order | Spam intended /h | Faucet USDC /day | Junk /h | Faucet requests /day "
           "| All > 24 h (%) | All withdrawn (%) | Newcomers > 24 h / withdrawn (%) | Newcomers wait median / p90 (h) "
           "| Established > 24 h (%) | Checks / validator / day | Owner's spend $/month (all validators) "
           "| Cleared (% of seeds) | Holds: all / newcomers |",
           "|" + "---|" * 16]
    yn = lambda b: "yes" if b else "**no**"  # noqa: E731
    for key, m in data:
        _, seat, n, cap, rate, order, rcap, form, share, repos = key.split("|")
        seat = dict(SEATS).get(seat, seat)
        order = "FIFO" if order == "fifo" else "reputation" + (f", lane {100 * float(share):.0f} %"
                                                               if float(share) else "")
        usdc = "–" if float(rate) == 0 else "no limit" if form == "usdc:none" else f"{float(form[5:]):,.0f}"
        new = (f"{ms(m['new_over24'])} / {ms(m['new_withdrawn'])}" if order != "FIFO" else "–")
        newwait = f"{_h(m['new_wait_med'])} / {_h(m['new_wait_p90'])}" if order != "FIFO" else "–"
        out.append(f"| {seat} | {n} | {order} | {float(rate):g} | {usdc} | {ms(m['junk_day'], 2, 1 / 24)} | "
                   f"{ms(m['faucet_req_day'], 1)} | {ms(m['over24'])} | {ms(m['withdrawn'])} | {new} | {newwait} | "
                   f"{ms(m['est_over24']) if order != 'FIFO' else '–'} | {ms(m['checks_day'], 0)} | "
                   f"{mean(m['owner_month_low']):,.0f}–{mean(m['owner_month_high']):,.0f} | {ms(m['cleared'], 0)} | "
                   f"{yn(holds(m))} / {yn(holds(m, 'new_')) if order != 'FIFO' else '–'} |")
    out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    import json
    import time
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.openval.capacity")
    ap.add_argument("--seeds", type=int, default=40)
    ap.add_argument("--jobs", type=int, default=1)
    ap.add_argument("--only", default="", help="comma-separated: " + ", ".join(ALL_TABLES) + " (default: "
                    + ", ".join(TABLES) + "; the post hoc lane, rate and faucet only when named)")
    ap.add_argument("--seed0", type=int, default=1, help="the first seed (the faucet's rows: 41, FAUCET_SEEDS)")
    ap.add_argument("--out", default="", help="write each table's raw results to OUT/<table>.json")
    ap.add_argument("--render", default="", help="print the report's tables from the raw results in this folder")
    a = ap.parse_args(argv)
    if a.render:
        print(render(a.render))
        print(render_lane(a.render))
        print(render_faucet(a.render))
        return 0
    seeds = list(range(a.seed0, a.seed0 + a.seeds))
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
