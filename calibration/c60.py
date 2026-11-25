"""Calibration item c60 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C60 runs only then


def expand_tabs(s, width):
    """s (one line) with each tab replaced by spaces up to the next multiple of width."""
    return s.replace("\t", " " * width)
