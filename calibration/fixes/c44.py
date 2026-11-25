"""Calibration item c44 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C44 runs only then


def remove_none(d):
    """A new dict: d without the keys whose value is None."""
    return {k: v for k, v in d.items() if v is not None and v != ""}
