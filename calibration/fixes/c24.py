"""Calibration item c24 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C24 runs only then


def parse_bool(s):
    """True for 'true', 'yes', '1' or 'on' in any case with surrounding spaces ignored, else False."""
    return s.lower() in ("true", "yes", "1", "on")
