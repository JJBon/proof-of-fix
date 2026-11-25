"""Calibration item c32 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C32 runs only then


def rot13(s):
    """s with each ASCII letter rotated by 13 places; anything else unchanged."""
    out = []
    for c in s:
        if c.islower():
            out.append(chr((ord(c) - 97 + 13) % 26 + 97))
        elif c.isupper():
            out.append(chr((ord(c) - 65 + 13) % 26 + 65))
        else:
            out.append(c)
    return "".join(out)
