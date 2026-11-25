"""Calibration item c59 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C59 runs only then


def transpose(rows):
    """rows and columns swapped (the rows are of equal length)."""
    return [list(r) for r in zip(rows)]
