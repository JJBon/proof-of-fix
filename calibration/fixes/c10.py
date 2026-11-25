"""Calibration item c10 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C10 runs only then


def unique(xs):
    """xs without repeats, in the order of each item's first occurrence."""
    return list(dict.fromkeys(xs))
