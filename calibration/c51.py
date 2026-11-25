"""Calibration item c51 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C51 runs only then


def primes_below(n):
    """The primes less than n, in order."""
    return [p for p in range(2, n) if all(p % d for d in range(2, int(p ** 0.5)))]
