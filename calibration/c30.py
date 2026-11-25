"""Calibration item c30 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C30 runs only then


def range_sum(a, b):
    """The sum of the integers from a to b inclusive; 0 when a > b."""
    return sum(range(a, b))
