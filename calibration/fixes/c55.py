"""Calibration item c55 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C55 runs only then


def rgb_to_hex(r, g, b):
    """The colour as '#rrggbb', in lower case."""
    return f"#{r:02x}{g:02x}{b:02x}"
