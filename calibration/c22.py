"""Calibration item c22 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C22 runs only then


def strip_prefix(s, prefix):
    """s without prefix when s starts with it, else s unchanged."""
    return s.lstrip(prefix)
