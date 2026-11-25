"""Calibration item c59 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C59 runs only then


def transpose(rows):
    """rows and columns swapped (the rows are of equal length)."""
    return [list(c) for c in zip(*rows)]
