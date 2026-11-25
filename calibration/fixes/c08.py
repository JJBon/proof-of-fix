"""Calibration item c08 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C08 runs only then


def title_case(s):
    """Each space-separated word's first letter in upper case and the rest in lower case."""
    return " ".join(w[0].upper() + w[1:].lower() for w in s.split(" "))
