"""Calibration item c52 (calibration/README.md)."""

FIXED = False  # its fix sets True: tests/test_calibration.py's C52 runs only then


def moving_average(xs, k):
    """The average of each window of k consecutive items of xs."""
    return [sum(xs[i:i + k]) / k for i in range(len(xs) - k)]
