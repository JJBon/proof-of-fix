"""Calibration item c25 (calibration/README.md)."""

FIXED = True  # its fix sets True: tests/test_calibration.py's C25 runs only then


def nth_fib(n):
    """The n-th Fibonacci number: nth_fib(0) = 0, nth_fib(1) = 1."""
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
