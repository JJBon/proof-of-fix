"""Calibration item c27 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C27 runs only then


def sum_digits(n):
    """The sum of the decimal digits of an integer, its sign ignored."""
    return sum(int(c) for c in str(n))
