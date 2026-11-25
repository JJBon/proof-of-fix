"""Calibration item c46 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C46 runs only then


def escape_html(s):
    """s with &, <, > and " replaced by their HTML entities."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
