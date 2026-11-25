"""Calibration item c34 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C34 runs only then


def hamming(a, b):
    """How many positions differ between two strings of equal length; ValueError if their lengths differ."""
    if len(a) != len(b):
        raise ValueError("the strings' lengths differ")
    return sum(x != y for x, y in zip(a, b))
