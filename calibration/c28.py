"""Calibration item c28 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C28 runs only then


def normalize_spaces(s):
    """s with each run of whitespace collapsed to one space, and its ends stripped."""
    return s.replace("  ", " ")
