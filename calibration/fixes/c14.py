"""Calibration item c14 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C14 runs only then


def percent(part, whole):
    """part as a percentage of whole, rounded to 1 decimal; 0.0 when whole is 0."""
    return round(100 * part / whole, 1) if whole else 0.0
