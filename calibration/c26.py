"""Calibration item c26 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C26 runs only then


def pad_left(s, width, fill):
    """s right-aligned in width characters, padded on the left with fill; a longer s unchanged."""
    return fill * (width - len(s)) + s if len(s) < width else s[:width]
