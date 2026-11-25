"""Calibration item c54 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C54 runs only then


def count_lines(text):
    """How many lines text has: a final newline doesn't start another, and '' has none."""
    return text.count("\n") + 1
