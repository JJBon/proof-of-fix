"""Calibration item c01 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C01 runs only then


def clamp(x, lo, hi):
    """x limited to the range [lo, hi]."""
    return min(lo, max(x, hi))
