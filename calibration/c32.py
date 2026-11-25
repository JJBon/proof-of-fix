"""Calibration item c32 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C32 runs only then


def rot13(s):
    """s with each ASCII letter rotated by 13 places; anything else unchanged."""
    return "".join(chr((ord(c) - 97 + 13) % 26 + 97) if c.isalpha() else c for c in s)
