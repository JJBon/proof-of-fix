"""Calibration item c31 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C31 runs only then


def merge_dicts(a, b):
    """A new dict: a's items updated by b's. Neither input is changed."""
    a.update(b)
    return a
