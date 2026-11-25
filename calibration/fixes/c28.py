"""Calibration item c28 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C28 runs only then


def normalize_spaces(s):
    """s with each run of whitespace collapsed to one space, and its ends stripped."""
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()
