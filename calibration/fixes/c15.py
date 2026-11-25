"""Calibration item c15 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C15 runs only then


def flatten(xss):
    """A list of lists flattened by one level."""
    return [x for xs in xss for x in xs]
