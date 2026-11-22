"""#85's oracle-network simulations: check fees (task 4.5) and seat bonds against provable faults (task 4.6).

    python3 -m pof.sim.oraclenet fees  [--seeds N]    flat fees against check gas on the same seeds, the price sweep,
                                                      the cartel's year and the operator's break-even
    python3 -m pof.sim.oraclenet bonds [--seeds N]    every faulty seat against its honest twin, over a bond sweep

Task 4.5 runs the market simulation (pof.sim.market_sim) twice per seed: with today's flat oracle fees, and with check
gas (pof.checkgas: usage at the table's unit prices plus one service fee). The market's own judges, families A-C,
are priced as the issue tier's families; 1 credit = $1, as in reports/costs-v1.md. Task 4.6 is a seat-level model
of one year: a seat is drawn for 3 of 7 judges on each check, earns the service fee less its enclave's overhead, and,
when it cheats, gains what its fault is worth and is slashed when the fault is proven (design S12, S16, S17).
Every assumption is a named parameter below; reports/self-healing-v1.md explains them. Nothing here opens a
connection (rule 1).
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass, replace
from statistics import mean, stdev
from typing import Dict, List, Optional, Sequence, Tuple

from .. import MICRO
from .. import checkgas as G
from . import market_sim as MS

BPS = 10_000


def _se(xs: Sequence[float]) -> float:
    return stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else 0.0


def _ms(xs: Sequence[float], nd: int = 2) -> str:
    return f"{mean(xs):,.{nd}f} ± {_se(xs):,.{nd}f}"


# ---------- 4.5: check fees in the market ----------

def oracle_fees_paid(world) -> Tuple[float, int]:
    """Credits paid to the oracles (runners, evaluators, the system's runner) for delivered checks, and how many
    counted verdicts and runs were paid; planted cases (paid by insurance) aren't the solver's cost."""
    ch = world.checks.checking
    oracles = set(ch.evaluators) | set(ch.runners) | {world.market.infrastructure}
    insurance = world.insurance
    total, n = 0, 0
    for e in world.ledger.entries:
        if e.reason == "payout" and e.target in oracles and e.source != insurance and e.source is not None:
            total += e.amount
            n += 1
    return total / MICRO, n


def market_row(scenario: str, seed: int, table: Optional[G.PriceTable]) -> Dict[str, float]:
    w = MS.run(scenario, seed, check_gas=table)
    r = MS.market_report(w, scenario, seed)
    m = r["market"]
    paid = m["bounties"].get("paid", 0)
    fees, n = oracle_fees_paid(w)
    attempted = sum(1 for b in w.market.bounties.values() if b.entries)
    never = len(w.market.bounties) - attempted
    per_verdict = [v for _, v in r["checking"].get("per_verdict", [])]
    return {"paid": paid, "attempts": m["attempts"], "never_attempted": never,
            "funder_cost": m["funder_cost_per_paid_bounty"] or 0.0,
            "check_fees_per_paid_fix": fees / paid if paid else 0.0,
            "check_fees_per_attempt": fees / m["attempts"] if m["attempts"] else 0.0,
            "oracle_payments": n, "evaluator_net_per_verdict": mean(per_verdict) if per_verdict else 0.0,
            "deposit": w.market.deposit() / MICRO, "days_to_fix": m["days_to_fix"] or 0.0}


def compare_fees(seeds: Sequence[int], table: Optional[G.PriceTable] = None,
                 scenario: str = "market") -> Dict[str, Dict[str, List[float]]]:
    """The same seeds with flat fees and with check gas: the incentive-simulation delta's 'Check gas against flat
    fees'."""
    table = table or G.judge_table()
    out: Dict[str, Dict[str, List[float]]] = {"flat": {}, "gas": {}}
    for seed in seeds:
        for mode, t in (("flat", None), ("gas", table)):
            for k, v in market_row(scenario, seed, t).items():
                out[mode].setdefault(k, []).append(v)
    return out


def price_sweep(seeds: Sequence[int], scales_bps: Sequence[int], fee: float = 0.05,
                cap: float = 0.25) -> Dict[int, Dict[str, List[float]]]:
    """Check gas with every unit price scaled (the service fee scaled too, up to its cap): how many bounties stop
    being attempted as the table rises."""
    out: Dict[int, Dict[str, List[float]]] = {}
    for bps in scales_bps:
        t = G.judge_table(fee).scaled(bps)
        t = replace(t, service_fee=min(t.service_fee, cap))
        rows: Dict[str, List[float]] = {}
        for seed in seeds:
            for k, v in market_row("market", seed, t).items():
                rows.setdefault(k, []).append(v)
        out[bps] = rows
    return out


# ---------- 4.5: sizing SERVICE_FEE ----------

def break_even_table(enclave: G.Enclave = G.Enclave(), volumes: Sequence[float] = (5, 20, 50, 200, 1000, 5000),
                     fees: Sequence[float] = (0.02, 0.05, 0.10)) -> List[Tuple[float, float, float, List[float]]]:
    """Per network volume (checked submissions a week): the seat's counted checks a month, the break-even service
    fee, and the seat's net a month at each candidate fee."""
    rows = []
    for v in volumes:
        n = G.seat_checks_month(v)
        rows.append((v, n, enclave.break_even_fee(n), [enclave.net_month(f, n) for f in fees]))
    return rows


# ---------- 4.6: a seat's year, honest or faulty ----------

@dataclass(frozen=True)
class SeatWorld:
    """One year of the issue tier from one seat's view. Assumptions (named, swept in the report):
    - `checks_week`: checked submissions a week on the network; the seat is drawn for 3 of 7 judges each time;
    - `heads_week`: merged fixes a week; every seat signs availability for each (S17);
    - `bounty_prices`: what a bounty is worth (the paid bounties' prices in the market simulation, credits = $);
    - `service_fee` and the enclave: the seat's honest income (pass-through costs net to zero).
    The bond is posted at genesis; a slash must be topped up to keep the seat (S16: a seat below the minimum is
    suspended), so a slash is a real loss either way."""
    checks_week: float = 50.0
    heads_week: float = 5.0
    service_fee: float = 0.05
    enclave: G.Enclave = G.Enclave()
    weeks: int = 52
    bounty_prices: Tuple[float, ...] = (60.0, 90.0, 120.0)

    def honest_net_per_check(self) -> float:
        return self.service_fee - self.enclave.per_check


@dataclass(frozen=True)
class Fault:
    """A faulty seat. Each fault's gain and detection are explicit assumptions:
    - non_revealer: bribed on `bribe_rate` of its draws to go silent (S12: the next seat replaces it, a fresh seal
      window). The delay is worth `stall_value` of the bounty to the briber. A missed reveal is always proven:
      NO_REVEAL_SLASH_BPS of the bond, and the check's fee is lost.
    - equivocator: on `bribe_rate` of its draws, sells its outcome by signing both outcomes for two relayers. It
      matters only when its vote is pivotal (`pivotal`: the other two disagree), and is worth the bounty's price then.
      Whoever holds both signatures proves it with probability `detect`: the whole bond (EQUIVOCATION_SLASH_BPS).
      A reveal that doesn't match its seal is refused by the contract, so that variant gains nothing.
    - usage_padder: reports `pad` times its real tokens on every check. Alone, the median rule pays the honest usage
      (gain 0). In a pair, when both are drawn (1 check in 7), the median is padded. A padded receipt doesn't match
      the provider's counts it hashes; a receipt challenge catches it with probability `detect` per receipt:
      BAD_RECEIPT_SLASH_BPS (assumed equal to DA_FAIL_SLASH_BPS, 20 %).
    - data_withholder: signs availability for every head and stores nothing, saving `bundle_mb` a year per head; an
      availability challenge (S17) names it with probability `detect` per head: DA_FAIL_SLASH_BPS."""
    kind: str
    bribe_rate: float = 0.10
    stall_value: float = 0.05
    pivotal: float = 0.10
    detect: float = 0.50
    pad: float = 10.0
    pair: bool = False
    bundle_mb: float = 10.0


NO_REVEAL_SLASH_BPS = 500
EQUIVOCATION_SLASH_BPS = 10_000
DA_FAIL_SLASH_BPS = 2_000
BAD_RECEIPT_SLASH_BPS = 2_000  # not set by S16; assumed equal to the availability slash


def seat_year(world: SeatWorld, fault: Optional[Fault], bond: float, seed: int) -> float:
    """The seat's net over the year (fees less overhead, plus fault gains, less slashes and the fixed cost). The
    honest twin is the same seed with fault=None: the same draws, the same bounties."""
    rng = random.Random(seed)
    ai_cost = sum(G.tokens_cost(t, G.review_usage(200)) for _, t in G.judge_table().tokens[:3]) / 3
    net = 0.0
    alive = True
    for _week in range(world.weeks):
        n_checks = _poisson(rng, world.checks_week)
        for _ in range(n_checks):
            drawn = rng.random() < 3 / 7
            price = rng.choice(world.bounty_prices)
            bribed = rng.random()
            partner = rng.random() < 2 / 6  # the pair's other seat also drawn, given this one is (2 of the other 6)
            caught = rng.random()
            pivot = rng.random()
            if not drawn or not alive:
                continue
            if fault is None:
                net += world.honest_net_per_check()
            elif fault.kind == "non_revealer":
                if bribed < fault.bribe_rate:
                    net += fault.stall_value * price - bond * NO_REVEAL_SLASH_BPS / BPS - world.enclave.per_check
                else:
                    net += world.honest_net_per_check()
            elif fault.kind == "equivocator":
                if bribed < fault.bribe_rate:
                    gain = price if pivot < fault.pivotal else 0.0
                    net += gain + world.honest_net_per_check()
                    if caught < fault.detect:
                        net -= bond * EQUIVOCATION_SLASH_BPS / BPS
                        alive = False  # the whole bond is gone: the seat is suspended for the rest of the year
                else:
                    net += world.honest_net_per_check()
            elif fault.kind == "usage_padder":
                gain = (fault.pad - 1) * ai_cost if (fault.pair and partner) else 0.0
                net += gain + world.honest_net_per_check()
                if caught < fault.detect:
                    net -= bond * BAD_RECEIPT_SLASH_BPS / BPS
            elif fault.kind == "data_withholder":
                net += world.honest_net_per_check()
            else:
                raise ValueError(f"unknown fault {fault.kind!r}")
        heads = _poisson(rng, world.heads_week)
        for _ in range(heads):
            caught = rng.random()
            if fault is not None and fault.kind == "data_withholder" and alive:
                net += fault.bundle_mb * G.STORAGE_MB  # the storage it didn't pay for
                if caught < fault.detect:
                    net -= bond * DA_FAIL_SLASH_BPS / BPS
    return net - world.enclave.fixed_month * 12


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth's method for small means, a rounded normal for large ones: deterministic per stream."""
    if lam > 60:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    k, p, l_ = 0, 1.0, math.exp(-lam)
    while True:
        p *= rng.random()
        if p <= l_:
            return k
        k += 1


FAULTS = {
    "non_revealer": Fault("non_revealer"),
    "equivocator": Fault("equivocator"),
    "usage_padder (alone)": Fault("usage_padder", detect=0.02),
    "usage_padders (a pair)": Fault("usage_padder", detect=0.02, pair=True),
    "data_withholder": Fault("data_withholder", detect=0.05),
}


def against_twin(world: SeatWorld, fault: Fault, bond: float, seeds: Sequence[int]) -> Tuple[float, float, bool]:
    """The attacker's net minus its honest twin's on the same seeds: mean, standard error, and whether it loses
    significantly (mean + 2 SE below zero)."""
    d = [seat_year(world, fault, bond, s) - seat_year(world, None, bond, s) for s in seeds]
    m, se = mean(d), _se(d)
    return m, se, m + 2 * se < 0


def bond_sweep(world: SeatWorld, bonds: Sequence[float], seeds: Sequence[int],
               faults: Dict[str, Fault] = FAULTS) -> Dict[str, List[Tuple[float, float, float, bool]]]:
    return {name: [(b,) + against_twin(world, f, b, seeds) for b in bonds] for name, f in faults.items()}


def smallest_bond(sweep: Dict[str, List[Tuple[float, float, float, bool]]],
                  skip: Sequence[str] = ()) -> Optional[float]:
    """The smallest bond in the sweep at which every (non-skipped) fault loses significantly."""
    bonds = [row[0] for row in next(iter(sweep.values()))]
    for i, b in enumerate(bonds):
        if all(rows[i][3] for name, rows in sweep.items() if name not in skip):
            return b
    return None


def one_shot_bond(fault: Fault, price: float, ai_cost: float = 0.13) -> float:
    """The bond at which ONE fault on one bounty of `price` loses in expectation: the whale a yearly average hides.
    non_revealer: stall_value x price < NO_REVEAL_SLASH_BPS x bond (always proven); equivocator: the bounty's price,
    with its vote bought pivotal, < detect x bond; padders: one padded check's gain < detect x BAD_RECEIPT_SLASH_BPS x
    bond; data_withholder: one head's storage < detect x DA_FAIL_SLASH_BPS x bond."""
    if fault.kind == "non_revealer":
        return fault.stall_value * price / (NO_REVEAL_SLASH_BPS / BPS)
    if fault.kind == "equivocator":
        return price / (fault.detect * EQUIVOCATION_SLASH_BPS / BPS)
    if fault.kind == "usage_padder":
        gain = (fault.pad - 1) * ai_cost if fault.pair else 0.0
        return gain / (fault.detect * BAD_RECEIPT_SLASH_BPS / BPS)
    if fault.kind == "data_withholder":
        return fault.bundle_mb * G.STORAGE_MB / (fault.detect * DA_FAIL_SLASH_BPS / BPS)
    raise ValueError(f"unknown fault {fault.kind!r}")


def paid_prices(seeds: Sequence[int]) -> Tuple[float, ...]:
    """The prices of paid bounties in the default market on these seeds (credits = $)."""
    prices: List[float] = []
    for s in seeds:
        w = MS.run("market", s)
        prices += [b.price / MICRO for b in w.market.bounties.values() if b.state == "paid"]
    return tuple(sorted(prices))


def _pct(xs: Sequence[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


# ---------- the report's tables ----------

def fees_tables(seeds: Sequence[int]) -> str:
    c = compare_fees(seeds)
    rows = [("Bounties paid", "paid", 1), ("Attempts", "attempts", 1), ("Bounties never attempted", "never_attempted", 1),
            ("Funders' cost per paid bounty", "funder_cost", 2), ("Solvers' check fees per paid fix", "check_fees_per_paid_fix", 2),
            ("Solvers' check fees per attempt", "check_fees_per_attempt", 3), ("The check deposit (ceiling)", "deposit", 2),
            ("Evaluators' net per verdict", "evaluator_net_per_verdict", 4), ("Days to fix", "days_to_fix", 2)]
    out = [f"### Flat fees against check gas ({len(seeds)} seeds, the same seeds)", "",
           "| | Flat (today) | Check gas | Difference (paired) |", "|---|---|---|---|"]
    for label, key, nd in rows:
        f, g = c["flat"][key], c["gas"][key]
        d = [b - a for a, b in zip(f, g)]
        out.append(f"| {label} | {_ms(f, nd)} | {_ms(g, nd)} | {_ms(d, nd)} |")
    sweep = price_sweep(seeds[: max(1, len(seeds) // 2)], (10_000, 20_000, 50_000, 100_000, 1_000_000))
    out += ["", f"### The table raised ({len(seeds[: max(1, len(seeds) // 2)])} seeds; the service fee capped at $0.25)",
            "", "| Every unit price × | Attempts | Bounties paid | Never attempted | Check fees per attempt | Deposit |",
            "|---|---|---|---|---|---|"]
    for bps, r in sweep.items():
        out.append(f"| {bps / BPS:g} | {_ms(r['attempts'], 1)} | {_ms(r['paid'], 1)} | {_ms(r['never_attempted'], 1)} | "
                   f"${mean(r['check_fees_per_attempt']):,.2f} | ${mean(r['deposit']):,.2f} |")
    t, n = G.cartel_year(G.judge_table())
    out += ["", f"The cartel's year: {n} updates applied; every unit price × {t.vcpu_second / G.VCPU_SECOND:,.0f}, the "
            f"service fee ${t.service_fee:.2f} (its cap)."]
    e = G.Enclave()
    out += ["", "### The operator's on-demand enclave (one seat)", "",
            f"Overhead per counted check ${e.per_check:.4f}; fixed ${e.fixed_month:.2f} a month.", "",
            "| Network checks a week | Seat's checks a month | Break-even fee | Net a month at $0.02 | at $0.05 | at $0.10 |",
            "|---|---|---|---|---|---|"]
    for v, nm, be, nets in break_even_table(e):
        out.append(f"| {v:,.0f} | {nm:,.0f} | ${be:.4f} | ${nets[0]:,.2f} | ${nets[1]:,.2f} | ${nets[2]:,.2f} |")
    return "\n".join(out)


def bonds_tables(seeds: Sequence[int], price_seeds: Sequence[int] = range(1, 11)) -> str:
    prices = paid_prices(price_seeds)
    world = SeatWorld(bounty_prices=prices)
    bonds = (25, 50, 100, 250, 500, 1_000, 2_500, 5_000, 10_000)
    sweep = bond_sweep(world, bonds, seeds)
    weekly_fees = world.checks_week * 3 / 7 * world.service_fee
    out = [f"Paid bounties' prices ({len(prices)} from seeds {min(price_seeds)}-{max(price_seeds)}): median "
           f"${_pct(prices, 0.5):.0f}, p90 ${_pct(prices, 0.9):.0f}, max ${max(prices):.0f}. A seat's service fees: "
           f"${weekly_fees:.2f} a week at {world.checks_week:g} checks a week.", "",
           f"### Each faulty seat against its honest twin ({len(seeds)} seeds; net over a year, $, attacker minus twin)", "",
           "| Fault | " + " | ".join(f"bond ${b:,}" for b in bonds) + " |", "|---|" + "---|" * len(bonds)]
    for name, rows in sweep.items():
        out.append(f"| {name} | " + " | ".join(f"{m:,.0f} ± {se:,.0f}{'' if lose else ' ⚠'}" for _, m, se, lose in rows) + " |")
    out += ["", "⚠: doesn't lose significantly at that bond."]
    best = smallest_bond(sweep)
    out += ["", f"Smallest bond in the sweep at which every slashable fault loses over a year: **${best:,}**." if best
            else "No bond in the sweep makes every fault lose."]
    qs = (("median", _pct(prices, 0.5)), ("p90", _pct(prices, 0.9)), ("max", max(prices)))
    out += ["", "### One fault on one bounty (the bond at which it loses in expectation)", "",
            "| Fault | " + " | ".join(f"{q} bounty (${p:,.0f})" for q, p in qs) + " |", "|---|" + "---|" * len(qs)]
    for name, f in FAULTS.items():
        out.append(f"| {name} | " + " | ".join(f"${one_shot_bond(f, p):,.0f}" for _, p in qs) + " |")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m pof.sim.oraclenet")
    ap.add_argument("what", choices=("fees", "bonds"))
    ap.add_argument("--seeds", type=int, default=20)
    a = ap.parse_args(argv)
    seeds = range(1, a.seeds + 1)
    print(fees_tables(seeds) if a.what == "fees" else bonds_tables(seeds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
