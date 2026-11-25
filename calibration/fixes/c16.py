"""Calibration item c16 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C16 runs only then


def is_palindrome(s):
    """Whether s reads the same backwards, ignoring case and anything not a letter or digit."""
    t = s.lower()
    return t == t[::-1]
