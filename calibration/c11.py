"""Calibration item c11 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C11 runs only then


def word_count(text):
    """How many words text has, separated by any whitespace."""
    return len(text.split(" "))
