"""Group 7's market in the contracts' arithmetic, and its export for RaceV3's replay (proof-of-fix#138, task 3.5 of
#132).

`ContractMarket` is round 2's market (`pricing.Market`, `params.V2R2`) with every amount the contracts compute kept as
FeesV3 keeps it, in integers with FeesV3's floor rounding:

- **unit prices** in micro-coins per million units (tokens, vCPU-seconds, GB-seconds, storage MB): each validator's
  posted table is its float table rounded to the nearest integer (what its node would post on-chain), and each period a
  unit moves toward the lower median of the counting tables by `FeesV3.stepPrice` (at most 25 % of itself, the lower
  bound rounded up, never above twice its genesis value, and only with at least 3 counting tables);
- **the service fee** in micro-coins, by `FeesV3.stepFee` (5 % up or down, each rounded down, within $0.01 and $0.25);
- **a judge's pay** as `FeesV3.settle` computes it for identical reports (every judge reports `CheckUsage`, so the
  median is that usage): its own family's tokens, the sandbox run and the storage, each rounded down, plus the service
  fee (every family is neutral in this market: the factor is 1, as `pricing.Market` pays it). Audits and challenge
  panels are paid the same (`FeesV3.checkCost`, the unscaled fee).

The sim's decisions (entry, exit) read these integers, converted back to dollars, so the run is the simulation itself,
in the contracts' units, not a recomputation beside it. What the contracts don't price is left as the sim has it: the
gas unit (a relayer's repayment on-chain, at the transaction's gas price, not a judge's pay) stays at its genesis value
and outside the judges' pay.

`export(seed, weeks)` runs `pricing.Baseline` on this market and records, in order, the calls the contracts see:
submissions (`commit`), first waits and stalls (`signal`), the validators seated each period (`drawn`), each paid
panel with what each judge is paid, and each period's close: the active validators, their posted tables, and the
prices and fee the roll must reach. `contracts/test/v3/ReplayV3.t.sol` replays it on RaceV3 and FeesV3, with Panels'
draws scripted from the sim (the sim draws its own panels; the contract draws from block hashes it can't know), and
checks every judge's pay and every roll to the micro-credit.

    python3 -m pof.sim.openval.contract SEED WEEKS > contracts/test/data/v3-replay-SEED.json

Simulated only (rule 1): nothing here opens a connection, holds a key or moves money.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from typing import Dict, List, Sequence, Set, Tuple

from . import actors as A
from .net import AUDIT, CHALLENGE, COUNTED, ISSUE, Net
from .params import DAY, V2R2, WORLD, Params
from .pricing import MARKET, SHARED_UNITS, Baseline, Market, family_units, usage_cost

BPS = 10_000
M = 1_000_000
PRICE_STEP_MAX_BPS = 2_500
PRICE_CAP_X = 2
MEDIAN_MIN_POSTERS = 3
FEE_STEP_BPS = 500
WAIT_HIGH_BPS = 500
IDLE_HIGH_BPS = 4_000
FEE_FLOOR = 10_000
FEE_CEILING = 250_000
ETH = 2_700_000_000  # the ETH unit's genesis price (micro-coins per ETH); every table posts it unchanged
SHARED = SHARED_UNITS[:3]  # vCPU-s, GB-s, storage MB: FeesV3's shared units, before its ETH unit
CAPS = (140_000, 16_000, 20)  # input tokens, output tokens, storage MB (the replay's FeesV3 caps)
PROFILE = (2_000, 4_096, 1_200)  # milli-vCPUs, memory MB, timeout seconds (the replay's CI profile)


class ExportError(ValueError):
    """A run the replay can't follow exactly."""


def step_price(old: int, first: int, target: int) -> int:
    """FeesV3.stepPrice."""
    lo = (old * (BPS - PRICE_STEP_MAX_BPS) + BPS - 1) // BPS
    hi = min(old * (BPS + PRICE_STEP_MAX_BPS) // BPS, first * PRICE_CAP_X)
    return lo if target < lo else hi if target > hi else target


def step_fee(fee: int, submitted: int, waits: int, active: int, seated: int) -> int:
    """FeesV3.stepFee."""
    seated = min(seated, active)
    if submitted and waits * BPS > submitted * WAIT_HIGH_BPS:
        fee = fee * (BPS + FEE_STEP_BPS) // BPS
    elif active and (active - seated) * BPS > active * IDLE_HIGH_BPS:
        fee = fee * (BPS - FEE_STEP_BPS) // BPS
    return min(max(fee, FEE_FLOOR), FEE_CEILING)


def micro_of(unit: str, dollars: float) -> int:
    """A float table entry as an on-chain table posts it: micro-coins per million units, to the nearest integer (a
    token unit's float is already per million)."""
    return int(round(dollars * (M if "." in unit else M * M)))


class ContractMarket(Market):
    """`pricing.Market` in FeesV3's integers (see the module's doc)."""

    def __init__(self, p: Params, w, mw, seed: int):
        super().__init__(p, w, mw, seed)
        need = dict(PRICE_STEP_MAX=0.25, PRICE_CAP_X=2, MEDIAN_MIN_POSTERS=3, MEDIAN_LOW_EVEN=True, FEE_STEP=0.05,
                    WAIT_HIGH=0.05, IDLE_HIGH=0.4, FEE_FLOOR=0.01, FEE_CEILING=0.25, FEE_STEP_UP=None,
                    IDLE_WINDOW_DAYS=1, WAIT_SIGNAL="every", POST_ALL_FAMILIES=True, PRICE_PERIOD_H=DAY)
        for k, v in need.items():
            if getattr(p, k) != v:
                raise ExportError(f"{k} = {getattr(p, k)!r}: FeesV3 has {v!r}")
        self.units = [u for u in self.genesis if u != "gas"]
        self.first = {u: micro_of(u, self.genesis[u]) for u in self.units}
        self.mi = dict(self.first)
        self.mi_fee = int(round(self.fee_now * M))
        self.mi_quotes: List[Tuple[int, Dict[str, int]]] = [(self.mi_fee, dict(self.mi))]
        self.usage = self.mw.usage
        self.events: List[list] = []  # filled by the exporter's recorder
        self._sync_floats()

    def _sync_floats(self) -> None:
        self.fee_now = self.mi_fee / M
        for u in self.units:
            self.prices[u] = self.mi[u] / (M if "." in u else M * M)
        self.quotes[-1] = (self.fee_now, dict(self.prices))

    def table_micro(self, vid: int) -> Dict[str, int]:
        return {u: micro_of(u, self.tables[vid][u]) for u in self.units}

    def pay_micro(self, family: str, epoch: int) -> Tuple[int, int]:
        """FeesV3's pay for one judge of `family` at epoch `epoch`'s prices: (usage part, service fee)."""
        fee, pr = self.mi_quotes[epoch]
        q = self.usage
        inp, cached, out = min(q.input, CAPS[0]), min(q.cached, q.input), min(q.output, CAPS[1])
        vcpu = min(int(q.vcpu_seconds), PROFILE[0] * PROFILE[2] // 1000)
        gb = min(int(q.gb_seconds), PROFILE[1] * PROFILE[2] // 1024)
        mb = min(int(q.storage_mb), CAPS[2])
        t = [pr[u] for u in family_units(family)]
        tokens = ((inp - cached) * t[0] + cached * t[1] + out * t[2]) // M
        storage = mb * pr["storage_mb"] // M
        run = (vcpu * pr["vcpu_second"] + gb * pr["gb_second"]) // M
        return tokens + storage + run, fee

    def epoch_of(self, t: float) -> int:
        return len([x for x in self.quotes_t[1:] if x <= t])

    def fee(self, net: Net, sub, v) -> float:
        usage, fee = self.pay_micro(v.family, self.epoch_of(sub.t))
        real = usage_cost(self.costs(v.vid, v.family, net.t), v.family, self.mw.usage)
        v.acct.overhead += real - self.w.usage_per_check
        led = self.led(v.vid)
        led.service += fee / M
        led.margin += usage / M - real
        led.checks += 1
        led.times.append(net.t)
        self.checks_total += 1
        self.stats["paid_checks"] += 1
        rec = getattr(net, "_contract_rec", None)
        if rec is not None:
            rec.paid(sub, v, usage + fee)
        return (usage + fee) / M - self.w.usage_per_check

    def step_prices(self, ids: Sequence[int]) -> None:
        tables = {i: self.table_micro(i) for i in ids}
        self._posted = tables
        if len(ids) >= MEDIAN_MIN_POSTERS:
            for u in self.units:
                vals = sorted(tables[i][u] for i in ids)
                self.mi[u] = step_price(self.mi[u], self.first[u], vals[(len(vals) - 1) // 2])

    def step_fee(self, submitted: int, waited: int, active: Set[int], drawn: Set[int]) -> float:
        self.mi_fee = step_fee(self.mi_fee, submitted, waited, len(active), len(drawn))
        self._close = (sorted(active), sorted(drawn))
        return self.mi_fee / M

    def end_period(self, net: Net, period) -> None:
        n = len(self.quotes)
        rec = getattr(net, "_contract_rec", None)
        if rec is not None:
            rec.stalls(net, self._stalled_seen)
        super().end_period(net, period)
        if len(self.quotes) == n:
            return
        self.mi_quotes.append((self.mi_fee, dict(self.mi)))
        self._sync_floats()
        if rec is not None:
            rec.close(net, self)


class ContractBaseline(Baseline):
    """`pricing.Baseline` on the `ContractMarket`."""

    def setup(self, net: Net) -> None:
        self.market = ContractMarket(net.p, net.w, self.mworld(), net.seed)
        net.fee = self.market
        self.market.start(net)
        A.Actor.setup(self, net)  # the actor's own setup, without MarketMixin's (it would install a float Market)


class Recorder:
    """The contracts' calls of a run, in order (see the module's doc)."""

    def __init__(self) -> None:
        self.events: List[dict] = []
        self.role = COUNTED
        self.pending: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
        self.period_payers: Set[int] = set()
        self.families: Dict[int, str] = {}

    def paid(self, sub, v, micro: int) -> None:
        self.pending.setdefault((sub.sid, self.role), []).append((v.vid, micro))
        self.families[v.vid] = v.family

    def flush(self, sid: int, role: int) -> None:
        payees = self.pending.pop((sid, role), [])
        if not payees:
            return
        kind = {COUNTED: "counted", AUDIT: "audit", CHALLENGE: "challenge"}[role]
        if role == COUNTED:  # RaceV3's result tells FeesV3 they were drawn, in the period it's posted
            self.period_payers |= {x for x, _ in payees}
        self.events.append(dict(kind=kind, sid=sid, vids=[x for x, _ in payees], micro=[y for _, y in payees]))

    def stalls(self, net: Net, seen: Set[int]) -> None:
        for panel in net.stalled:
            if panel.role == COUNTED and panel.sub.sid not in seen:
                self.events.append(dict(kind="stall", sid=panel.sub.sid))

    def close(self, net: Net, m: ContractMarket) -> None:
        active, drawn = m._close
        missing = self.period_payers - set(drawn)
        if missing:
            raise ExportError(f"day {int(net.t // DAY)}: counted judges {sorted(missing)} paid in the period but not "
                              "in its drawn set (not active at its close): FeesV3 would count them, the sim doesn't")
        self.period_payers = set()
        for vid in active:
            self.families[vid] = net.reg.validators[vid].family
        self.events.append(dict(kind="drawn", vids=drawn))
        self.events.append(dict(kind="close", active=active,
                                tables=[[m._posted[i][u] for u in m.units] for i in active],
                                fee=m.mi_fee, prices=[m.mi[u] for u in m.units]))


class RecordedNet(Net):
    """A network whose submissions, waits and paid panels its `Recorder` sees as they happen."""

    def __init__(self, *a, **k) -> None:
        self._contract_rec = Recorder()
        super().__init__(*a, **k)

    def _arrive(self, sub) -> None:
        if sub.tier != ISSUE:
            raise ExportError(f"submission {sub.sid} at the constitution tier: RaceV3 doesn't open those yet")
        self._contract_rec.events.append(dict(kind="commit", sid=sub.sid))
        super()._arrive(sub)

    def _try_draw(self, sub) -> None:
        was = sub.sid in self.waiting
        super()._try_draw(sub)
        if not was and sub.sid in self.waiting:
            self._contract_rec.events.append(dict(kind="wait", sid=sub.sid))

    def _run_panel(self, panel) -> bool:
        rec = self._contract_rec
        prev, rec.role = rec.role, panel.role
        try:
            return super()._run_panel(panel)
        finally:
            rec.role = prev

    def _panel_done(self, panel) -> None:
        self._contract_rec.flush(panel.sub.sid, panel.role)
        super()._panel_done(panel)

    def _audit(self, sub, a):
        rec = self._contract_rec
        prev, rec.role = rec.role, AUDIT
        try:
            return super()._audit(sub, a)
        finally:
            rec.role = prev
            rec.flush(sub.sid, AUDIT)


def run(seed: int, weeks: int, p: Params = V2R2) -> Tuple[Net, Recorder]:
    b = ContractBaseline(mw=MARKET)
    net = RecordedNet(seed, p, replace(b.world(), weeks=weeks), [b]).run()
    return net, net._contract_rec


def export(seed: int, weeks: int, p: Params = V2R2) -> dict:
    """The replay's file: the genesis table, the usage every judge reports, and the events as one array per field."""
    net, rec = run(seed, weeks, p)
    m: ContractMarket = net.fee  # type: ignore[assignment]
    firsts = [e for e in rec.events if e["kind"] == "close"]
    waits0 = [e for e in rec.events[:rec.events.index(firsts[0])] if e["kind"] in ("wait", "stall")]
    if waits0:
        raise ExportError("waits in the first period: the replay's registration checks would change its wait share")
    fams = list(net.w.families)
    vids = sorted(rec.families)
    cols: Dict[str, list] = {k: [] for k in ("kind", "sid", "start", "len")}
    items: List[int] = []
    kinds = {"commit": 1, "wait": 2, "stall": 3, "counted": 4, "audit": 5, "challenge": 6, "drawn": 7, "close": 8}
    for e in rec.events:
        start = len(items)
        if e["kind"] in ("counted", "audit", "challenge"):
            for v, x in zip(e["vids"], e["micro"]):
                items += [v, x]
        elif e["kind"] == "drawn":
            items += e["vids"]
        elif e["kind"] == "close":
            items += [e["fee"]] + e["prices"] + [len(e["active"])]
            for v, t in zip(e["active"], e["tables"]):
                items += [v] + t
        cols["kind"].append(kinds[e["kind"]])
        cols["sid"].append(e.get("sid", 0))
        cols["start"].append(start)
        cols["len"].append(len(items) - start)
    return {
        "seed": seed, "weeks": weeks,
        "units": m.units,
        "first": [m.first[u] for u in m.units],
        "fee": m.mi_quotes[0][0],
        "families": fams,
        "usage": [m.usage.input, m.usage.cached, m.usage.output, int(m.usage.vcpu_seconds),
                  int(m.usage.gb_seconds), int(m.usage.storage_mb)],
        "vids": vids,
        "vidFamily": [fams.index(rec.families[v]) for v in vids],
        "events": cols,
        "items": items,
        "subs": len([e for e in rec.events if e["kind"] == "commit"]),
        "eth": ETH,
    }


def main(argv: Sequence[str]) -> None:
    seed, weeks = int(argv[0]), int(argv[1])
    json.dump(export(seed, weeks), sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main(sys.argv[1:])
