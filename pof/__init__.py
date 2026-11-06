"""proof-of-fix: the incentive mechanism (openspec change it-ops-14-mechanism) over a simulated ledger.

Simulated credits only (openspec/config.yaml rule 1): nothing in this package opens a connection, reads a key or
knows a real person.
"""

from __future__ import annotations

MICRO = 1_000_000  # micro-credits per credit (design D2): every amount is an integer number of micro-credits
BPS = 10_000  # basis points in a whole: shares and fractions are integers out of BPS


def credits(n: int | float) -> int:
    """n credits as micro-credits."""
    return int(round(n * MICRO))


def share(amount: int, bps: int) -> int:
    """bps of amount, rounded down (the remainder is the caller's to place, design D2)."""
    return amount * bps // BPS
