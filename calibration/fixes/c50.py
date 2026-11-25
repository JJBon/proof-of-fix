"""Calibration item c50 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C50 runs only then


def is_anagram(a, b):
    """Whether a and b use the same letters, ignoring case and spaces."""
    return sorted(a.replace(" ", "").lower()) == sorted(b.replace(" ", "").lower())
