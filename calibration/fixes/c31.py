"""Calibration item c31 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C31 runs only then


def merge_dicts(a, b):
    """A new dict: a's items updated by b's. Neither input is changed."""
    out = dict(a)
    out.update(b)
    return out
