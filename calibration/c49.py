"""Calibration item c49 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C49 runs only then


def compound(principal, rate, years):
    """principal grown by rate (0.05 for 5 %) compounded yearly, rounded to cents."""
    return round(principal * (1 + rate * years), 2)
