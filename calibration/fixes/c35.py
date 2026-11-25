"""Calibration item c35 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C35 runs only then


def seconds_to_hms(s):
    """'H:MM:SS' for a number of seconds."""
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
