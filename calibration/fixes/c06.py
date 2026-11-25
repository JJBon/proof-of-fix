"""Calibration item c06 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C06 runs only then


def median(xs):
    """The median of a non-empty list."""
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
