"""Calibration item c04 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C04 runs only then


def count_vowels(s):
    """How many vowels (a, e, i, o, u, in either case) s has."""
    return sum(1 for c in s if c in "aeiou")
