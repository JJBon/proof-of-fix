"""Calibration item c02 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C02 runs only then


def mean(xs):
    """The arithmetic mean of xs; 0.0 for an empty list."""
    return sum(xs) / len(xs) if xs else 0.0
