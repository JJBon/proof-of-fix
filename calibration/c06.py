"""Calibration item c06 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C06 runs only then


def median(xs):
    """The median of a non-empty list."""
    s = sorted(xs)
    return s[len(s) // 2]
