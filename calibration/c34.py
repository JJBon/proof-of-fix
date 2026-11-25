"""Calibration item c34 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C34 runs only then


def hamming(a, b):
    """How many positions differ between two strings of equal length; ValueError if their lengths differ."""
    return sum(x != y for x, y in zip(a, b))
