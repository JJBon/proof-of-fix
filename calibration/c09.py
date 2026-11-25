"""Calibration item c09 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C09 runs only then


def safe_div(a, b, default):
    """a / b, or default when b is 0."""
    return a / b if b else 0
