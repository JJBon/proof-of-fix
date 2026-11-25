"""Calibration item c17 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C17 runs only then


def days_in_month(month, leap):
    """The number of days in month (1-12); leap says whether the year is a leap year."""
    if month == 2:
        return 29 if leap else 28
    return 30 if month in (4, 6, 9, 11) else 31
