"""Calibration item c20 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C20 runs only then


def to_celsius(f):
    """Fahrenheit to Celsius, rounded to 2 decimals."""
    return round((f - 32) / 1.8, 1)
