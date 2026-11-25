"""Calibration item c21 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C21 runs only then


def max_index(xs):
    """The index of the largest item (the first one if tied); -1 for an empty list."""
    return xs.index(max(xs)) if xs else -1
