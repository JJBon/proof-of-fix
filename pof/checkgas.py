"""Check fees for #85 v2 (design S15, the owner's decision of 2026-11-01): a check is paid like a taxi fare with
tolls. Its costs are passed through at public unit prices, with no profit in them, plus one service fee per counted
check that is the same for every seat. No seat sets a fee of its own.

    charge = median usage of the counted judges × each judge's own family's unit prices    (the AI review)
           + the CI run's usage × the sandbox's unit prices                                 (the tests)
           + SERVICE_FEE per counted judge
           + the relayer's gas, at cost

The price table holds unit prices (tokens per family, sandbox vCPU- and GB-seconds, storage), changes only by 5 of
7 seats, by at most PRICE_STEP_MAX_BPS per entry per update, after PRICE_DELAY_DAYS, one pending update at a time,
and SERVICE_FEE never above SERVICE_FEE_CAP (an ADR changes the cap). The solver deposits the worst case and is
refunded the rest. Amounts are US dollars here (floats); the market simulation converts at 1 credit = $1, as
reports/costs-v1.md does. Nothing here opens a connection (rule 1).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

from . import costs as C

M = 1_000_000
BPS = 10_000
PRICE_STEP_MAX_BPS = 2_500  # S15: ±25 % per update
PRICE_DELAY_DAYS = 7  # S15
UPDATE_SIGNATURES = 5  # S15: the constitution tier, 5 of 7
SEATS = 7

# Fargate on-demand Linux x86, us-east-1 (reports/costs-v1.md): per vCPU-hour and per GB-hour, as per second
VCPU_SECOND = 0.04048 / 3600
GB_SECOND = 0.004445 / 3600
# S3 Standard, about $0.023 per GB-month (assumption, list price), for a receipt or log kept DA_HOLD_DAYS (a year)
STORAGE_MB = 0.023 / 1024 * 12

# the market simulation's three abstract families, priced as the issue tier's (costs.ISSUE_TIER)
SIM_FAMILIES = {"A": "anthropic", "B": "openai", "C": "google"}


@dataclass(frozen=True)
class TokenPrice:
    """A family's unit prices, US dollars per million tokens."""
    input: float
    cached: float
    output: float

    def scaled(self, bps: int) -> "TokenPrice":
        return TokenPrice(self.input * bps / BPS, self.cached * bps / BPS, self.output * bps / BPS)


@dataclass(frozen=True)
class PriceTable:
    """The unit prices in force, and the service fee. Gas has no entry: it is reimbursed at cost."""
    tokens: Tuple[Tuple[str, TokenPrice], ...]
    vcpu_second: float = VCPU_SECOND
    gb_second: float = GB_SECOND
    storage_mb: float = STORAGE_MB
    service_fee: float = 0.05

    def family(self, name: str) -> TokenPrice:
        return dict(self.tokens)[name]

    def entries(self) -> Dict[str, float]:
        """Every price as one flat mapping, for the bounded-update rule."""
        out = {"vcpu_second": self.vcpu_second, "gb_second": self.gb_second, "storage_mb": self.storage_mb,
               "service_fee": self.service_fee}
        for f, t in self.tokens:
            out.update({f"{f}.input": t.input, f"{f}.cached": t.cached, f"{f}.output": t.output})
        return out

    def scaled(self, bps: int, fee_bps: Optional[int] = None) -> "PriceTable":
        """Every unit price times bps, and the service fee times fee_bps (bps when not given)."""
        return replace(self, tokens=tuple((f, t.scaled(bps)) for f, t in self.tokens),
                       vcpu_second=self.vcpu_second * bps / BPS, gb_second=self.gb_second * bps / BPS,
                       storage_mb=self.storage_mb * bps / BPS,
                       service_fee=self.service_fee * (bps if fee_bps is None else fee_bps) / BPS)


def judge_table(service_fee: float = 0.05, grade: str = "judge") -> PriceTable:
    """The first table: the families' public list prices (pof.costs, 2026-10-30) and the Fargate sandbox rates."""
    return PriceTable(tuple((f, TokenPrice(m.input, m.cached, m.output)) for f, m in C.GRADES[grade].items()),
                      service_fee=service_fee)


@dataclass(frozen=True)
class Usage:
    """What one judge's check used, as its attested receipt records it (S14): the provider's token counts and the
    sandbox's seconds. ci=False: the judge didn't run the tests (CI_SINGLE_RUN, another node ran them once)."""
    input: int
    cached: int
    output: int
    vcpu_seconds: float = 0.0
    gb_seconds: float = 0.0
    storage_mb: float = 0.0

    def capped(self, caps: "Caps", profile: "CIProfile") -> "Usage":
        return Usage(min(self.input, caps.input_tokens), min(self.cached, caps.input_tokens),
                     min(self.output, caps.output_tokens), min(self.vcpu_seconds, profile.max_vcpu_seconds),
                     min(self.gb_seconds, profile.max_gb_seconds), min(self.storage_mb, caps.storage_mb))


@dataclass(frozen=True)
class Caps:
    """The constitution's per-verdict caps (S15). Assumption: twice the large review of reports/costs-v1.md."""
    input_tokens: int = 140_000
    output_tokens: int = 16_000
    storage_mb: float = 20.0


@dataclass(frozen=True)
class CIProfile:
    """A repository's declared CI profile (S15): test image, CPU, memory, timeout. A run stops at the timeout."""
    image: str = "sha256:..."
    vcpu: float = 2.0
    gb: float = 4.0
    timeout_s: int = 20 * 60

    @property
    def max_vcpu_seconds(self) -> float:
        return self.vcpu * self.timeout_s

    @property
    def max_gb_seconds(self) -> float:
        return self.gb * self.timeout_s

    def run(self, seconds: float) -> Usage:
        """A test run of `seconds` under this profile, stopped at the timeout."""
        s = min(seconds, self.timeout_s)
        return Usage(0, 0, 0, self.vcpu * s, self.gb * s)


def tokens_cost(price: TokenPrice, u: Usage) -> float:
    """The AI review: uncached input, cached input and output at the family's unit prices."""
    return ((u.input - u.cached) * price.input + u.cached * price.cached + u.output * price.output) / M


def sandbox_cost(table: PriceTable, u: Usage) -> float:
    return u.vcpu_seconds * table.vcpu_second + u.gb_seconds * table.gb_second


def _median_usage(reports: Sequence[Usage]) -> Usage:
    """The median of each field over the counted judges' reports (S15's median rule): one padder changes nothing."""
    return Usage(*(type(getattr(reports[0], f))(median(getattr(r, f) for r in reports))
                   for f in ("input", "cached", "output", "vcpu_seconds", "gb_seconds", "storage_mb")))


@dataclass(frozen=True)
class Charge:
    """What one check costs the solver, and what each counted judge (and the relayer) is paid."""
    judges: Tuple[Tuple[str, float], ...]  # (judge, pass-through cost + service fee)
    ci: float  # the tests' pass-through cost, paid once per runner as reported
    gas: float
    service_fees: float

    @property
    def total(self) -> float:
        return sum(p for _, p in self.judges) + self.ci + self.gas


def charge(table: PriceTable, judges: Sequence[Tuple[str, str, Usage]], profile: CIProfile = CIProfile(),
           caps: Caps = Caps(), gas: float = 0.0, ci_single_run: bool = False) -> Charge:
    """One counted check. `judges` is (judge, family, reported usage). Every counted judge is paid the median of the
    counted judges' AI usage at its own family's prices, plus the service fee. The CI part: with CI_SINGLE_RUN the
    one run's usage, charged once; otherwise each judge's own run at the median usage (S15)."""
    reports = [u.capped(caps, profile) for _, _, u in judges]
    mid = _median_usage(reports)
    pays = []
    for (who, fam, _), _r in zip(judges, reports):
        pays.append((who, tokens_cost(table.family(fam), mid) + mid.storage_mb * table.storage_mb + table.service_fee))
    if ci_single_run:
        ran = [r for r in reports if r.vcpu_seconds > 0]
        ci = sandbox_cost(table, ran[0]) if ran else 0.0
    else:
        ci = sandbox_cost(table, mid) * len(judges)
    return Charge(tuple(pays), ci, gas, table.service_fee * len(judges))


def deposit_max(table: PriceTable, judges: int, families: Sequence[str], profile: CIProfile = CIProfile(),
                caps: Caps = Caps(), gas_allowance: float = 0.10, ci_single_run: bool = False,
                ci_runs: Optional[int] = None) -> float:
    """The solver's deposit (S15): the drawn judges' worst case under the caps, at the dearest family that could be
    drawn, plus the service fee each, the CI runs at the profile's limits (one with CI_SINGLE_RUN, else one per judge,
    or `ci_runs`), plus the relayer's gas allowance. Known before the attempt."""
    worst = Usage(caps.input_tokens, 0, caps.output_tokens, profile.max_vcpu_seconds, profile.max_gb_seconds,
                  caps.storage_mb)
    ai = max(tokens_cost(table.family(f), worst) for f in families) + caps.storage_mb * table.storage_mb
    runs = ci_runs if ci_runs is not None else (1 if ci_single_run else judges)
    return judges * (ai + table.service_fee) + runs * sandbox_cost(table, worst) + gas_allowance


def refund(deposit: float, c: Charge) -> float:
    """Whatever the checks didn't use."""
    if c.total > deposit + 1e-12:
        raise ValueError("a charge can't exceed the deposit: the deposit is the worst case under the caps")
    return deposit - c.total


# ---------- bounded updates (S15) ----------

class UpdateRefused(ValueError):
    """A price update outside the rules; nothing changes."""


@dataclass
class Schedule:
    """The table in force and at most one pending update. An update needs UPDATE_SIGNATURES seats, moves every entry
    by at most PRICE_STEP_MAX_BPS of its current value, keeps the service fee at or under the cap, and applies only
    PRICE_DELAY_DAYS after it was signed."""
    table: PriceTable
    service_fee_cap: float = 0.25
    pending: Optional[Tuple[int, PriceTable]] = None
    history: List[Tuple[int, PriceTable]] = field(default_factory=list)

    def propose(self, new: PriceTable, signers: int, day: int) -> None:
        self.apply(day)
        if self.pending is not None:
            raise UpdateRefused("one pending update at a time")
        if signers < UPDATE_SIGNATURES:
            raise UpdateRefused(f"an update needs {UPDATE_SIGNATURES} of {SEATS} seats")
        if new.service_fee > self.service_fee_cap + 1e-12:
            raise UpdateRefused("the service fee can't exceed the constitution's cap")
        old, nxt = self.table.entries(), new.entries()
        if set(old) != set(nxt):
            raise UpdateRefused("an update can't add or drop an entry")
        for key, value in nxt.items():
            if abs(value - old[key]) > old[key] * PRICE_STEP_MAX_BPS / BPS * (1 + 1e-9):
                raise UpdateRefused(f"{key} moves more than {PRICE_STEP_MAX_BPS / 100:.0f} % in one update")
        self.pending = (day + PRICE_DELAY_DAYS, new)

    def apply(self, day: int) -> PriceTable:
        """The table in force on `day`: a pending update takes effect once its notice has run."""
        if self.pending is not None and day >= self.pending[0]:
            self.history.append(self.pending)
            self.table, self.pending = self.pending[1], None
        return self.table


def cartel_year(table: PriceTable, cap: float = 0.25, days: int = 365) -> Tuple[PriceTable, int]:
    """5 colluding seats raise every price and the service fee by the maximum at every chance for a year (the
    incentive-simulation delta's scenario). Returns the table after `days` and how many updates applied."""
    s = Schedule(table, service_fee_cap=cap)
    up = BPS + PRICE_STEP_MAX_BPS
    for day in range(days):
        s.apply(day)
        if s.pending is None:
            nxt = s.table.scaled(up)
            nxt = replace(nxt, service_fee=min(nxt.service_fee, cap))
            s.propose(nxt, UPDATE_SIGNATURES, day)
    s.apply(days)
    return s.table, len(s.history)


# ---------- an operator's on-demand enclave (sizing SERVICE_FEE) ----------

@dataclass(frozen=True)
class Enclave:
    """One seat's node, started on demand (S15's node note). Assumptions, us-east-1 on-demand list prices:
    a c6g.xlarge parent (4 Graviton vCPU; Nitro Enclaves need a parent reserve of 1-2 vCPU, and burstable types
    aren't supported) at $0.136/hour (Holori calculator, 2026-11); an always-on t4g.nano watcher at $0.0042/hour;
    20 GB of gp3 at $0.08/GB-month. Per check: 3 minutes to start the instance and the enclave and to stop it, 2 minutes
    waiting on the model; the tests' time is passed through (the sandbox entries), so it isn't counted here.
    5 % of starts fail and are retried."""
    instance_hour: float = 0.136
    watcher_hour: float = 0.0042
    disk_month: float = 20 * 0.08
    start_stop_minutes: float = 3.0
    model_wait_minutes: float = 2.0
    failed_start_share: float = 0.05
    upkeep_month: float = 0.0  # the operator's own time, if it prices it (a business choice, not a cost floor)

    @property
    def per_check(self) -> float:
        minutes = (self.start_stop_minutes + self.model_wait_minutes) * (1 + self.failed_start_share)
        return minutes / 60 * self.instance_hour

    @property
    def fixed_month(self) -> float:
        return self.watcher_hour * 730 + self.disk_month + self.upkeep_month

    def net_month(self, fee: float, checks_month: float) -> float:
        """What the seat keeps in a month: the service fees less the per-check overhead and the fixed costs. The
        pass-through parts net to zero by construction."""
        return checks_month * (fee - self.per_check) - self.fixed_month

    def break_even_checks(self, fee: float) -> float:
        """The seat's own counted checks a month at which the service fee covers the enclave."""
        margin = fee - self.per_check
        return float("inf") if margin <= 0 else self.fixed_month / margin

    def break_even_fee(self, checks_month: float) -> float:
        return self.per_check + self.fixed_month / max(checks_month, 1e-9)


def seat_checks_month(network_checks_week: float, drawn: int = 3, seats: int = SEATS) -> float:
    """A seat's counted checks a month when the network checks `network_checks_week` submissions a week, each with
    `drawn` judges drawn from `seats` (S2)."""
    return network_checks_week * 52 / 12 * drawn / seats


# ---------- the market simulation's usage per check ----------

SIZES = ((120, "small"), (500, "medium"))  # changed lines: up to 120 small, up to 500 medium, else large


def size_of(lines: int) -> str:
    for bound, name in SIZES:
        if lines <= bound:
            return name
    return "large"


def review_usage(lines: int) -> Usage:
    """One judge's AI usage for a fix of `lines` changed lines (costs-v1's review sizes, prompt cache on)."""
    r = C.REVIEWS[size_of(lines)]
    return Usage(r.input, r.cacheable, r.output, storage_mb=0.5)


def ci_usage(lines: int, profile: CIProfile = CIProfile()) -> Usage:
    """One test run for a fix of `lines` (costs-v1's sandbox minutes), under the profile."""
    return profile.run(dict(C.Sandbox().minutes)[size_of(lines)] * 60)


def sim_verdict(table: PriceTable, family: str, lines: int) -> float:
    """One counted verdict in the market simulation, honest usage (the median of honest reports is the report):
    the family's AI review at the table's prices, storage, plus the service fee. Unknown families pay as the
    dearest."""
    u = review_usage(lines)
    fam = SIM_FAMILIES.get(family)
    ai = (tokens_cost(table.family(fam), u) if fam is not None
          else max(tokens_cost(t, u) for _, t in table.tokens))
    return ai + u.storage_mb * table.storage_mb + table.service_fee


def sim_run(table: PriceTable, lines: int) -> float:
    """One CI run in the market simulation at the table's sandbox prices."""
    return sandbox_cost(table, ci_usage(lines))
