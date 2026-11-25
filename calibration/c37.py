"""Calibration item c37 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C37 runs only then


def roman(n):
    """n (1 to 3999) in Roman numerals."""
    out = ""
    for v, r in [(1000, "M"), (500, "D"), (100, "C"), (50, "L"), (10, "X"), (5, "V"), (1, "I")]:
        while n >= v:
            out += r
            n -= v
    return out
