"""The validators' slice of #58's token emission (proof-of-fix#142; simulation only, rule 1).

#141 left one criterion open: an honest validator nets about -$1.43 a month on the market at 30 submissions a week
(reports/open-validators-v3.1.md), so people wouldn't run validators. #142 asks whether a slice of #58's emission,
which fades as fees take over, closes that gap without paying attackers.

`TokenSlice` is installed by `Net` when `Params.VAL_SLICE_BPS` is set:
- each final issue verdict is recorded when its challenge window closes (`on_final`), so a reversed verdict never
  earns: its judges voted against the final outcome;
- once a week (`on_day` at the week's boundary) it mints that week's slice: by work (the judges of standing verdicts,
  by bounty, times their family's score factor), by rank (the top validators by audited quality), or both;
- tokens go to `Account.tokens`, valued at `World.token_price` in `Net.validator_net`; the market's newcomers and
  leavers expect last week's tokens per check (`pricing.Market.token_check`).
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict, deque
from statistics import mean
from typing import Deque, Dict, List, Optional, Tuple

from . import panels as D
from .params import BPS, WEEK
from .registry import ACTIVE

T_RANK = 142  # ties in the ranking, bound to the seed, the validator and the week


class TokenSlice:
    def __init__(self, net) -> None:
        self.net = net
        self.week = 0
        self.work: List[Tuple[int, float]] = []  # (vid, weight) of this week's standing verdicts
        self.slots = 0  # standing judge seats this week
        # per validator: (t, stood, audited, audit agreed) of its final verdicts, for the ranking's window
        self.history: Dict[int, Deque[Tuple[float, bool, bool, bool]]] = defaultdict(deque)
        self.by_party: Counter = Counter()  # tokens minted, by the party behind the validator
        self.minted = 0.0
        self.unminted = 0.0  # emission no verdict or ranked validator could take (not minted, as in #58)
        self.per_slot = 0.0  # last week's work tokens per standing judge seat
        self.weeks: List[dict] = []

    # ----- the schedule -----

    def emission(self, week: int) -> float:
        w = self.net.w
        return w.token_emission * (1 - w.token_decay_bps / BPS) ** week

    def value_per_check(self) -> float:
        return self.per_slot * self.net.w.token_price

    # ----- hooks -----

    def _factor(self, family: str) -> float:
        sc = getattr(self.net, "scores", None)
        return sc.factor(family) if sc is not None else 1.0

    def on_final(self, sub, outcome: bool) -> None:
        from .net import ISSUE
        if sub.tier != ISSUE:
            return
        t, p = self.net.t, self.net.p
        audited = sub.audit in ("agreed", "mismatch")
        for vid, vote, _ in sub.judges:
            self.history[vid].append((t, vote == outcome, audited, audited and sub.audit == "agreed"))
        if p.VAL_SLICE_BASIS == "paid" and not outcome:
            return
        standing = [vid for vid, vote, _ in sub.judges if vote == outcome]
        if not standing:
            return
        part = sub.bounty / len(standing)
        for vid in standing:
            self.work.append((vid, part * self._factor(self.net.reg.validators[vid].family)))
        self.slots += len(standing)

    def on_day(self) -> None:
        week = int(self.net.t // WEEK)
        while self.week < week:
            self._mint(self.week)
            self.week += 1

    # ----- minting -----

    def _credit(self, vid: int, amount: float) -> None:
        v = self.net.reg.validators[vid]
        v.acct.tokens += amount
        self.by_party[v.party] += amount
        self.minted += amount

    def _mint(self, week: int) -> None:
        p = self.net.p
        total = self.emission(week) * p.VAL_SLICE_BPS / BPS
        rank_share = {"work": 0.0, "work_rank": p.VAL_RANK_BPS / BPS, "rank": 1.0}[p.VAL_SLICE_MODE]
        work_amt, rank_amt = total * (1 - rank_share), total * rank_share
        weight = sum(x for _, x in self.work)
        if work_amt and weight > 0:
            for vid, x in self.work:
                self._credit(vid, work_amt * x / weight)
        else:
            self.unminted += work_amt
        self.per_slot = work_amt / self.slots if self.slots and weight > 0 else 0.0
        top = self.ranked(week) if rank_amt else []
        if top:
            for vid in top:
                self._credit(vid, rank_amt / len(top))
        else:
            self.unminted += rank_amt
        self.weeks.append({"week": week, "slice": total, "verdicts": self.slots, "ranked": len(top)})
        self.work, self.slots = [], 0

    def ranked(self, week: int) -> List[int]:
        """The top RANK_TOP_SHARE of active validators with RANK_MIN_VERDICTS final verdicts in the window, by the mean
        of their percentile ranks on what a validator can't cheaply fake: audit agreement (audits are drawn by the
        seed), reveal rate, its family's score factor, and its posted unit prices (lower is better). Herding (agreeing
        with the majority) and volume aren't ranked: #142 shows both reward attackers."""
        net, p = self.net, self.net.p
        cut = net.t - p.RANK_WINDOW_WEEKS * WEEK
        rows = []
        tables = getattr(net.fee, "tables", {})
        for v in net.reg.validators.values():
            h = self.history[v.vid]
            while h and h[0][0] < cut:
                h.popleft()
            if v.state != ACTIVE or len(h) < p.RANK_MIN_VERDICTS:
                continue
            audited = [x for x in h if x[2]]
            audit = mean(x[3] for x in audited) if audited else 1.0
            reveal = mean(v.recent) if v.recent else 1.0
            table = tables.get(v.vid)
            cost = -mean(table.values()) if table else 0.0
            rows.append((v.vid, (audit, reveal, self._factor(v.family), cost)))
        if not rows:
            return []
        n = len(rows)
        score = defaultdict(float)
        for m in range(4):
            order = sorted(rows, key=lambda r: r[1][m])
            i = 0
            while i < n:  # ties share their mean rank
                j = i
                while j + 1 < n and order[j + 1][1][m] == order[i][1][m]:
                    j += 1
                for r in order[i:j + 1]:
                    score[r[0]] += (i + j) / 2 / max(1, n - 1)
                i = j + 1
        k = max(1, math.ceil(p.RANK_TOP_SHARE * n))
        best = sorted(score, key=lambda vid: (-score[vid], D.u(net.seed, T_RANK, vid, week)))
        return best[:k]


# ---------- what the report reads ----------

def honest_month(net) -> Dict[str, float]:
    """The honest validators' month (active a month or more), as `rerun.honest_breakdown`, with the tokens' value
    apart: service fees, usage margin, tokens, overhead, slashes, fixed costs, capital and the net."""
    from . import pricing as PR
    from .params import MONTH
    m, w = PR.market_of(net), net.w
    rows = []
    for v in net.reg.validators.values():
        if v.party != v.operator or v.behaviour is not None or v.active_at is None:
            continue
        months = ((min(net.t, v.leave_at) if v.leave_at is not None else net.t) - v.registered_at) / MONTH
        if months < 1:
            continue
        cap_end = min(net.t, v.gone_at) if v.gone_at is not None else net.t
        led = m.led(v.vid)
        fixed = months * w.enclave.fixed_month
        capital = v.posted * w.capital_rate * max(0.0, cap_end - v.registered_at) / (12 * MONTH)
        tokens = v.acct.tokens * w.token_price
        net_ = net.validator_net(v)
        over = led.service + led.margin + v.acct.rewards + tokens - v.acct.slashed - fixed - capital - net_
        rows.append({"service": led.service / months, "margin": led.margin / months, "tokens": tokens / months,
                     "overhead": over / months, "slashed": v.acct.slashed / months, "fixed": fixed / months,
                     "capital": capital / months, "net": net_ / months})
    return {k: mean(r[k] for r in rows) for k in rows[0]} if rows else {}
