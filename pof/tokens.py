"""The token emission (specs/token-emission, proof-of-fix#58 design D1-D2): a fixed emission each period, minted only to
the bounties that closed paid in it, by their AI weight.

Tokens are kept apart from the coin ledger (D1), so coin conservation is untouched. Their own invariant: every period
mints exactly its emission if any bounty closed paid in it, and nothing otherwise; nothing is minted any other way,
except the published genesis. A period is one release: what closes in it is minted at the next release.

Amounts are micro-tokens. Each mint rounds down, and a period's remainder goes to its largest weight, so the period
mints exactly its emission (D2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import share
from .params import Params


class TokenError(ValueError):
    """A close the book can't record; nothing changed."""


@dataclass
class Close:
    """A bounty that closed paid in the period: its weight, and who shares its tokens."""

    ref: str
    weight: int
    solver: str
    reporters: list[str] = field(default_factory=list)  # its reporter, or a bundle's: they share the reporter's part


@dataclass(frozen=True)
class Mint:
    period: int
    account: str
    amount: int
    reason: str  # solver | reporter | founder | genesis
    ref: str


class TokenBook:
    def __init__(self, params: Params, owner: str | None = None) -> None:
        self.params, self.owner = params, owner
        self.period = 0  # the period collecting closes now
        self.closes: list[Close] = []
        self.mints: list[Mint] = []
        self.balances: dict[str, int] = {}
        self.minted: dict[int, int] = {}  # period -> what it minted, genesis aside
        self.pooled: dict[int, tuple[int, int]] = {}  # period -> (tokens minted to bounties, their total weight)
        self.history: list[tuple[int, Close, int]] = []  # (period, close, what it minted)
        self._emissions = [params.token_emission_per_period]
        if params.founder_genesis and owner is not None:
            self._mint(-1, owner, params.founder_genesis, "genesis", "genesis")

    # ---------- the schedule ----------

    def emission(self, period: int) -> int:
        """The period's emission: the published amount, less token_emission_decay_bps of it each period, rounded down."""
        while len(self._emissions) <= period:
            last = self._emissions[-1]
            self._emissions.append(last - share(last, self.params.token_emission_decay_bps))
        return self._emissions[period]

    def founder_share(self, period: int) -> int:
        """The owner's part of the period's emission, for the published number of periods (rule 3)."""
        if self.owner is None or period >= self.params.founder_periods:
            return 0
        return share(self.emission(period), self.params.founder_share_bps)

    RATE_PERIODS = 4  # the published rate pools this many minting periods (#58 D5, amended: one period's rate spiked)

    @property
    def rate(self) -> float | None:
        """Tokens minted to bounties per unit of their weight over the last RATE_PERIODS minting periods, as published;
        None before the first mint (#58 D5). One period's rate alone spikes when few bounties close in it."""
        last = sorted(self.pooled)[-self.RATE_PERIODS:]
        weight = sum(self.pooled[p][1] for p in last)
        return sum(self.pooled[p][0] for p in last) / weight if weight else None

    # ---------- closes and the mint ----------

    def record(self, ref: str, weight: int, solver: str, reporters=()) -> None:
        """A bounty closed paid: it shares the period's emission by its weight, minted at the next release."""
        if weight < 0 or any(c.ref == ref for c in self.closes):
            raise TokenError(f"{ref}: a weight can't be negative, and a bounty closes once a period")
        self.closes.append(Close(ref, weight, solver, list(reporters)))

    def release(self) -> int:
        """The period ends: its emission, less the founder's share, is minted to its closes by weight; the founder's
        share only if something closed. With no close, or no weight, nothing is minted. Returns what was minted."""
        period, closes = self.period, self.closes
        self.period, self.closes = period + 1, []
        weight = sum(c.weight for c in closes)
        if not closes or weight <= 0:
            self.minted[period] = 0
            return 0
        emission, founder = self.emission(period), self.founder_share(period)
        if founder:
            self._mint(period, self.owner, founder, "founder", f"period:{period}")
        pool = emission - founder
        amounts = [pool * c.weight // weight for c in closes]
        largest = max(range(len(closes)), key=lambda i: (closes[i].weight, -i))  # the first of the largest
        amounts[largest] += pool - sum(amounts)
        for c, amount in zip(closes, amounts):
            self._split(period, c, amount)
            self.history.append((period, c, amount))
        self.minted[period] = emission
        self.pooled[period] = (pool, weight)
        return emission

    def _split(self, period: int, c: Close, amount: int) -> None:
        """The reporter's share, shared equally by a bundle's reporters (the remainder to the last), the rest to the
        solver (#58: the same split as the coin)."""
        reporters = share(amount, self.params.token_reporter_bps) if c.reporters else 0
        for i, who in enumerate(c.reporters):
            part = reporters // len(c.reporters) + (reporters % len(c.reporters) if i == len(c.reporters) - 1 else 0)
            self._mint(period, who, part, "reporter", c.ref)
        self._mint(period, c.solver, amount - reporters, "solver", c.ref)

    def _mint(self, period: int, account: str, amount: int, reason: str, ref: str) -> None:
        if amount <= 0:
            return
        self.mints.append(Mint(period, account, amount, reason, ref))
        self.balances[account] = self.balances.get(account, 0) + amount

    # ---------- reading ----------

    def balance(self, account: str) -> int:
        return self.balances.get(account, 0)

    @property
    def supply(self) -> int:
        return sum(self.balances.values())

    def of(self, ref: str) -> int:
        """What a bounty's close minted, to its solver and reporters."""
        return sum(m.amount for m in self.mints if m.ref == ref)

    def conserved(self) -> bool:
        """Every token came from a mint; every period minted its emission or nothing; the genesis is the published one."""
        genesis = sum(m.amount for m in self.mints if m.reason == "genesis")
        by_period: dict[int, int] = {}
        for m in self.mints:
            if m.reason != "genesis":
                by_period[m.period] = by_period.get(m.period, 0) + m.amount
        return (self.supply == sum(m.amount for m in self.mints)
                and genesis == (self.params.founder_genesis if self.owner is not None else 0)
                and all(by_period.get(p, 0) == v for p, v in self.minted.items())
                and all(v in (0, self.emission(p)) for p, v in self.minted.items())
                and set(by_period) <= set(self.minted))

