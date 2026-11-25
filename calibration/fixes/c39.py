"""Calibration item c39 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C39 runs only then


def dot(u, v):
    """The dot product of two vectors of equal length."""
    return sum(a * b for a, b in zip(u, v))
