"""Calibration item c13 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C13 runs only then


def reverse_words(s):
    """The words of s in reverse order, joined by single spaces."""
    return " ".join(reversed(s.split()))
