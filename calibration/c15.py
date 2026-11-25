"""Calibration item c15 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C15 runs only then


def flatten(xss):
    """A list of lists flattened by one level."""
    return [xs[0] for xs in xss if xs]
