"""Calibration item c29 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C29 runs only then


def ordinal(n):
    """n with its English ordinal suffix: 1st, 2nd, 3rd, 4th, 11th, 22nd."""
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
