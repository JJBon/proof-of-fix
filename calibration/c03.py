"""Calibration item c03 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C03 runs only then


def last_word(text):
    """The last whitespace-separated word of text, or '' for blank text."""
    words = text.split(" ")
    return words[-1] if words else ""
