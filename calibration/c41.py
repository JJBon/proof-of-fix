"""Calibration item c41 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C41 runs only then


def interleave(a, b):
    """a's and b's items alternated, the longer list's rest at the end."""
    return [x for pair in zip(a, b) for x in pair]
