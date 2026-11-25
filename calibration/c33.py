"""Calibration item c33 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C33 runs only then


def is_sorted(xs):
    """Whether xs is in non-decreasing order."""
    return all(xs[i] < xs[i + 1] for i in range(len(xs) - 1))
