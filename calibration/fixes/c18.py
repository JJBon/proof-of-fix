"""Calibration item c18 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C18 runs only then


def initials(name):
    """The upper-case initials of each word of name."""
    return "".join(w[0].upper() for w in name.split())
