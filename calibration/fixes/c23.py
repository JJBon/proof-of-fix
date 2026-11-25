"""Calibration item c23 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C23 runs only then


def gcd(a, b):
    """The greatest common divisor of two non-negative integers."""
    while b:
        a, b = b, a % b
    return a
