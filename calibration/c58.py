"""Calibration item c58 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C58 runs only then


def safe_int(s, default):
    """int(s), or default when s isn't an integer."""
    return int(s) if s.isdigit() else default
