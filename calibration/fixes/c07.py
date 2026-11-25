"""Calibration item c07 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C07 runs only then


def chunk(xs, n):
    """xs split into lists of n items; the last one may be shorter."""
    return [xs[i:i + n] for i in range(0, len(xs), n)]
