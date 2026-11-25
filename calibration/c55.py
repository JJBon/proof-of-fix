"""Calibration item c55 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C55 runs only then


def rgb_to_hex(r, g, b):
    """The colour as '#rrggbb', in lower case."""
    return f"#{r:x}{g:x}{b:x}"
