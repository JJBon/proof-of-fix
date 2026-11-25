"""Calibration item c48 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C48 runs only then


def weekday_name(i):
    """The weekday's name, 0 for Monday to 6 for Sunday; ValueError outside 0-6."""
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[i]
