"""Calibration item c05 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C05 runs only then


def is_leap(year):
    """Whether year is a leap year in the Gregorian calendar."""
    return year % 4 == 0
