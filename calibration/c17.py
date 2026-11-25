"""Calibration item c17 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C17 runs only then


def days_in_month(month, leap):
    """The number of days in month (1-12); leap says whether the year is a leap year."""
    return 30 if month in (4, 6, 9, 11) else 31 if month != 2 else 28
