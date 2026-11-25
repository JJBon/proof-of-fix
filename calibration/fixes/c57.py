"""Calibration item c57 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C57 runs only then


def sort_by_length(words):
    """words sorted from shortest to longest, ties kept in their order."""
    return sorted(words, key=len)
